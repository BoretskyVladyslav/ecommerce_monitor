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
            raise RuntimeError("No running event loop")

        # Handle Lock per Loop to avoid "Future attached to different loop" errors
        if not hasattr(self, '_locks'):
            self._locks = {}
        
        if current_loop not in self._locks:
            self._locks[current_loop] = asyncio.Lock()
        
        loop_lock = self._locks[current_loop]

        # Check if we need to create a new pool
        need_new_pool = False
        if self._pool is None:
            need_new_pool = True
        elif self._pool._loop != current_loop:
            need_new_pool = True
        elif self._pool.closed: # Check if pool is closed
             need_new_pool = True

        if need_new_pool:
            async with loop_lock:
                # Double-check
                if (self._pool is None or 
                    self._pool._loop != current_loop or 
                    self._pool.closed):
                    
                    # Handle old pool cleanup SAFELY
                    if self._pool:
                        if self._pool._loop != current_loop:
                            # ⚠️ Different loop! Cannot await wait_closed()
                            # Just close and forget.
                            try:
                                self._pool.close()
                                logger.info("Closed old database pool (from different loop)")
                            except: pass
                            self._pool = None
                        elif not self._pool.closed:
                            # Same loop, clean close
                            try:
                                self._pool.close()
                                await self._pool.wait_closed()
                            except: pass
                            self._pool = None

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
            ORDER BY id ASC
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
                WHERE product_id = %s AND status != -1
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
                        "product_title": title,           # Added Title
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
                    "product_title": title,               # Added Title
                    "marketplace": marketplace,
                    "target_color": None,
                    "target_size": None,
                    "table": "monitored_product_options"  # Legacy table
                })
        
        logger.info(f"Generated {len(tasks)} tasks.")
        return tasks

    async def update_product_option_status(
        self,
        option_id: int,
        status: int,
        table: str = "monitored_product_options",
        price: float = None,
        original_price: float = None
    ):
        """
        Updates status (and optionally prices) for a monitored option.
        status: 1=In Stock, 0=Sold Out, -1=Excluded by user
        price: current sale price scraped from page
        original_price: original/strikethrough price scraped from page
        """
        if table == "product_options":
            if price is not None and original_price is not None:
                query = """
                    UPDATE product_options 
                    SET status = %s, price_sale = %s, price_orig = %s, updated_at = NOW()
                    WHERE id = %s
                """
                await self.execute(query, (status, price, original_price, option_id))
            elif price is not None:
                query = """
                    UPDATE product_options 
                    SET status = %s, price_sale = %s, updated_at = NOW()
                    WHERE id = %s
                """
                await self.execute(query, (status, price, option_id))
            else:
                query = """
                    UPDATE product_options 
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                """
                await self.execute(query, (status, option_id))
        else:
            # Legacy monitored_product_options table
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

    async def fetch_products_with_variants(self) -> list:
        """
        Fetches all products with their variants for the Variant Manager UI.
        Returns a list of dicts: {product_id, title, url, variants: [...]}
        """
        products = await self.fetch_all(
            "SELECT id, original_title, original_url FROM products ORDER BY id ASC"
        )
        result = []
        for p in products:
            variants = await self.fetch_all(
                """
                SELECT id, option_name_1, option_name_2, status, price_sale, price_orig, updated_at
                FROM product_options
                WHERE product_id = %s
                ORDER BY option_name_1, option_name_2
                """,
                (p['id'],)
            )
            result.append({
                'product_id': p['id'],
                'title': p.get('original_title') or f"Product #{p['id']}",
                'url': p.get('original_url') or '',
                'variants': variants
            })
        return result

    async def fetch_product_list(self) -> list:
        """Lightweight fetch — products only, no variants. Used for the UI product header list."""
        return await self.fetch_all(
            "SELECT id, original_title, original_url FROM products ORDER BY id ASC"
        )

    async def fetch_variants_for_product(self, product_id: int) -> list:
        """Fetch variants for a single product on demand (lazy loading)."""
        return await self.fetch_all(
            """
            SELECT id, option_name_1, option_name_2, status,
                   price_sale, price_orig, updated_at
            FROM product_options
            WHERE product_id = %s
            ORDER BY option_name_1, option_name_2
            """,
            (product_id,)
        )

    async def toggle_variant_active(self, option_id: int, active: bool):
        """
        Sets variant active (status stays/becomes its last real value)
        or inactive (status = -1, excluded from monitoring by user).
        """
        if active:
            # Restore to 1 (In Stock assumed, engine will check correctly next cycle)
            query = "UPDATE product_options SET status = 1, updated_at = NOW() WHERE id = %s AND status = -1"
        else:
            # Set to -1 = user-excluded
            query = "UPDATE product_options SET status = -1, updated_at = NOW() WHERE id = %s"
        await self.execute(query, (option_id,))


    async def close(self):
        """Closes the connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None