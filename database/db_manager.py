import sys
import os
import asyncio
import aiomysql
import logging
from typing import List, Dict, Any, Optional
from config.settings import settings

logger = logging.getLogger("DatabaseManager")

class DatabaseManager:
    _instance = None
    _pool: Optional[aiomysql.Pool] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
    
    def _get_resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

    async def get_pool(self) -> aiomysql.Pool:
        """Get or create the database connection pool."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
            
        # Check if we need to create a new pool
        need_new_pool = (
            self._pool is None or
            current_loop is None or
            (hasattr(self._pool, '_loop') and self._pool._loop != current_loop) or
            (hasattr(self._pool, '_loop') and self._pool._loop.is_closed())
        )
        
        if need_new_pool:
            async with self._lock:
                # Double-check after acquiring lock
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    raise RuntimeError("No running event loop")
                    
                if (self._pool is None or 
                    self._pool._loop != current_loop or 
                    self._pool._loop.is_closed()):
                    
                    # Close old pool if exists
                    if self._pool and not self._pool._loop.is_closed():
                        try:
                            self._pool.close()
                            await self._pool.wait_closed()
                        except:
                            pass
                    
                    try:
                        self._pool = await aiomysql.create_pool(
                            host=settings.DB_HOST,
                            port=settings.DB_PORT,
                            user=settings.DB_USER,
                            password=settings.DB_PASSWORD,
                            db=settings.DB_NAME,
                            cursorclass=aiomysql.DictCursor,
                            autocommit=True,
                            minsize=1,
                            maxsize=settings.MAX_CONCURRENT_BROWSERS + 2,
                            loop=current_loop
                        )
                        logger.info(f"Database pool created in event loop {id(current_loop)}")
                    except Exception as e:
                        logger.error(f"Failed to create database pool: {e}")
                        raise
        return self._pool

    async def init_db(self):
        """Initializes the database by running schema.sql."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    # Use absolute path resolving for PyInstaller compatibility
                    schema_path = self._get_resource_path(os.path.join('database', 'schema.sql'))
                    
                    # Fallback: if not found in _MEIPASS, maybe it's local
                    if not os.path.exists(schema_path):
                         schema_path = os.path.abspath(os.path.join('database', 'schema.sql'))
                    
                    logger.info(f"Loading schema from: {schema_path}")
                    
                    with open(schema_path, 'r') as f:
                        schema = f.read()
                    
                    # Split by semi-colon to execute multiple statements
                    statements = [s.strip() for s in schema.split(';') if s.strip()]
                    
                    for statement in statements:
                        await cursor.execute(statement)
                        
                    logger.info("Database initialized (schema updated).")
                except Exception as e:
                    logger.error(f"Failed to initialize database: {e}")
                    raise

    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Executes a SELECT query and returns a list of dictionaries."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchall()

    async def fetch_one(self, query: str, params: tuple = None):
        """Executes a SELECT query and returns a single row."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchone()

    async def execute(self, query: str, params: tuple = None):
        """Executes an INSERT/UPDATE/DELETE query and commits changes. Returns lastrowid."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(query, params)
                    return cursor.lastrowid
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")
                    raise

    async def fetch_active_products(self) -> List[Dict[str, Any]]:
        """
        Fetches active tasks. Prioritizes specific variants from `product_options`.
        Wrapper logic:
        1. Get products from `products` table.
        2. For each product, check `product_options` (variants).
        3. If variants exist -> Create tasks for each variant (updating `product_options` table).
        4. If NO variants -> Fallback to `monitored_product_options` (legacy/single item).
        """
        
        # 1. Get products
        products_query = """
            SELECT id, original_url, original_title 
            FROM products 
            WHERE original_url IS NOT NULL
        """
        logger.info(f"Fetch Query: {products_query.strip()}")
        products = await self.fetch_all(products_query)
        
        if not products:
             logger.info("No active products found in DB.")
             return []
        
        tasks = []

        for p in products:
            p_id = p['id']
            url = p['original_url']
            title = p.get('original_title') or 'New Option'
            if title and len(title) > 255: title = title[:255]
            
            # Determine marketplace
            marketplace = "unknown"
            if "amazon" in url: marketplace = "amazon"
            elif "ebay" in url: marketplace = "ebay"
            elif "temu" in url: marketplace = "temu"
            elif "shein" in url: marketplace = "shein"
            elif "aliexpress" in url: marketplace = "aliexpress"

            # --- CHECK FOR VARIANTS IN product_options ---
            # This is the PRIMARY source for Shein/Variants
            variants_query = """
                SELECT id, option_name_1, option_name_2, url 
                FROM product_options 
                WHERE product_id = %s
            """
            variants = await self.fetch_all(variants_query, (p_id,))
            
            if variants:
                # OPTION A: Product has specific variants defined
                for v in variants:
                    # Use variant-specific URL if available, else product URL
                    variant_url = v.get('url') if v.get('url') else url
                    
                    tasks.append({
                        "option_id": v['id'],             # ID from product_options
                        "url": variant_url,
                        "product_id": p_id,
                        "marketplace": marketplace,
                        "target_color": v.get('option_name_1'), # For Parser
                        "target_size": v.get('option_name_2'),  # For Parser
                        "table": "product_options"        # Signal to update THIS table
                    })
            else:
                # OPTION B: No variants, use LEGACY monitored_product_options
                # -----------------------------------------------------------
                
                # Sync parent monitored_products entry (Legacy req)
                check_parent = "SELECT id FROM monitored_products WHERE id = %s"
                if not await self.fetch_one(check_parent, (p_id,)):
                    await self.execute(
                        "INSERT INTO monitored_products (id, original_url, marketplace, status) VALUES (%s, %s, %s, 1)",
                        (p_id, url, marketplace)
                    )

                # Get/Create option in monitored_product_options
                check_option = "SELECT id FROM monitored_product_options WHERE product_id = %s"
                opt = await self.fetch_one(check_option, (p_id,))
                
                mpo_id = None
                if opt:
                    mpo_id = opt['id']
                else:
                    mpo_id = await self.execute(
                        "INSERT INTO monitored_product_options (product_id, option_name, status) VALUES (%s, %s, 1)",
                        (p_id, title)
                    )
                
                tasks.append({
                    "option_id": mpo_id,                  # ID from monitored_product_options
                    "url": url,
                    "product_id": p_id,
                    "marketplace": marketplace,
                    "target_color": None,
                    "target_size": None,
                    "table": "monitored_product_options"  # Legacy table
                })
        
        logger.info(f"Generated {len(tasks)} tasks.")
        return tasks

    async def update_product_option_status(self, option_id: int, status: int, table: str = "monitored_product_options"):
        """
        Updates status for a monitored option (1=In Stock, 0=Sold Out).
        Args:
            option_id: ID of the record
            status: New status
            table: 'product_options' or 'monitored_product_options' (legacy)
        """
        if table == "product_options":
            # For variants table, we don't have updated_at in all schemas, 
            # but usually good practice. If schema doesn't have it, SQL will ignore or optional?
            # User schema showed `created_at` but NOT `updated_at` for product_options in Step 90 output!
            # So I will NOT try to set updated_at for product_options to be safe, or check schema repeatedly.
            # Step 90 output: product_options structure: id, product_id, option_name_1/2, url, type, prices, status, created_at.
            # NO updated_at column in product_options.
            query = """
                UPDATE product_options 
                SET status = %s
                WHERE id = %s
            """
        else:
            # Legacy table has updated_at
            query = """
                UPDATE monitored_product_options 
                SET status = %s, updated_at = NOW()
                WHERE id = %s
            """
            
        await self.execute(query, (status, option_id))

    async def add_log_entry(self, option_id: int, session_id: int, old_status: int, new_status: int, note: str):
        """Inserts a record into the history log."""
        query = """
            INSERT INTO monitored_products_log 
            (option_id, session_id, old_status, new_status, note, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """
        await self.execute(query, (option_id, session_id, old_status, new_status, note))


    async def close(self):
        """Closes the connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None