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
        if self._pool is None:
            async with self._lock:
                if self._pool is None:
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
                        )
                        logger.info("Database pool created.")
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

    async def execute(self, query: str, params: tuple = None):
        """Executes an INSERT/UPDATE/DELETE query and commits changes."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    await cursor.execute(query, params)
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")
                    raise

    async def fetch_active_products(self) -> List[Dict[str, Any]]:
        """
        Fetches active product options to be scraped.
        Joins products and product_options tables.
        
        Returns rows with: option_id, url, marketplace, option_name_1, option_name_2
        Status mapping: 1 = Active, 0 = Sold Out
        """
        query = """
            SELECT 
                po.id as option_id,
                p.original_url as url,
                po.type as marketplace,
                po.option_name_1,
                po.option_name_2
            FROM product_options po
            JOIN products p ON po.product_id = p.id
            WHERE po.status != 0
        """
        return await self.fetch_all(query)

    async def get_available_session(self, marketplace: str) -> Optional[Dict[str, Any]]:
        """
        Finds a 'Ready' session for the given marketplace.
        """
        query = """
            SELECT * FROM sessions 
            WHERE type = %s AND status = 'Ready'
            ORDER BY last_active ASC
            LIMIT 1
        """
        sessions = await self.fetch_all(query, (marketplace,))
        return sessions[0] if sessions else None

    async def update_session_status(self, session_id: int, status: str):
        """Updates status and last_active for a session."""
        query = """
            UPDATE sessions 
            SET status = %s, last_active = NOW()
            WHERE id = %s
        """
        await self.execute(query, (status, session_id))


    async def close(self):
        """Closes the connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None