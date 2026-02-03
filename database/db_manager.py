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
                    with open('database/schema.sql', 'r') as f:
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
        1. Беремо товари з нової таблиці products.
        2. Перевіряємо, чи існують вони в СТАРІЙ батьківській таблиці (monitored_products).
        3. Якщо ні — створюємо їх там (легально, звичайним INSERT).
        4. Створюємо запис у monitored_product_options.
        """
        
        # КРОК 1: Отримуємо товари з НОВОЇ таблиці
        products_query = """
            SELECT id, original_url, original_title 
            FROM products 
            WHERE status = 1 AND original_url IS NOT NULL
        """
        logger.info(f"Executing Fetch Query: {products_query.strip()}") # LOG 1: SQL
        products = await self.fetch_all(products_query)
        
        if not products:
             logger.info("No active products found in DB.")
             return []
        
        logger.info(f"Fetch Found: {len(products)} products.") # LOG 2: Count 


        tasks = []

        # КРОК 2: Обробляємо кожен товар окремо
        for p in products:
            p_id = p['id']
            url = p['original_url']
            title = p.get('original_title') or 'New Option'
            
            # --- ЕТАП А: Задовольняємо батьківську таблицю (monitored_products) ---
            # Перевіряємо, чи є такий ID у старій таблиці
            check_parent_query = "SELECT id, marketplace FROM monitored_products WHERE id = %s"
            parent_exists = await self.fetch_one(check_parent_query, (p_id,))
            
            marketplace = "unknown"
            if parent_exists:
                 marketplace = parent_exists.get("marketplace", "unknown")
            else:
                # Визначаємо маркетплейс для старої таблиці (вона цього вимагає)
                if "amazon" in url: marketplace = "amazon"
                elif "ebay" in url: marketplace = "ebay"
                elif "temu" in url: marketplace = "temu"
                elif "shein" in url: marketplace = "shein"
                elif "aliexpress" in url: marketplace = "aliexpress"

                # Вставляємо запис у monitored_products, щоб заспокоїти Foreign Key
                logger.info(f"Syncing parent table for ID {p_id}...")
                insert_parent_query = """
                    INSERT INTO monitored_products (id, original_url, marketplace, status)
                    VALUES (%s, %s, %s, 1)
                """
                # Ми примусово вставляємо той самий ID
                await self.execute(insert_parent_query, (p_id, url, marketplace))

            # --- ЕТАП Б: Тепер безпечно працюємо з monitored_product_options ---
            # Перевіряємо, чи є запис опції
            check_option_query = "SELECT id FROM monitored_product_options WHERE product_id = %s"
            option_exists = await self.fetch_one(check_option_query, (p_id,))
            
            mpo_id = None
            if option_exists:
                mpo_id = option_exists['id']
            else:
                # Тепер цей INSERT пройде без помилки 1452, бо батько існує!
                logger.info(f"Creating monitor option for ID {p_id}...")
                insert_option_query = """
                    INSERT INTO monitored_product_options (product_id, option_name, status)
                    VALUES (%s, %s, 1)
                """
                mpo_id = await self.execute(insert_option_query, (p_id, title))
            
            tasks.append({
                "option_id": mpo_id,
                "url": url,
                "product_id": p_id,
                "marketplace": marketplace 
            })
            
        marketplaces_found = [t['marketplace'] for t in tasks]
        logger.info(f"Marketplaces in batch: {list(set(marketplaces_found))}") # LOG 3: Marketplaces list
        return tasks

    async def update_product_option_status(self, option_id: int, status: int):
        """Updates status for a monitored product option (1=In Stock, 0=Sold Out)."""
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