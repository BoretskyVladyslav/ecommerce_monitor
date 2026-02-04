import asyncio
import logging
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugCount")

async def analyze_products():
    db = DatabaseManager()
    
    # 1. Check schema of 'products' table to see if 'status' column exists
    try:
        columns = await db.fetch_all("DESCRIBE products")
        col_names = [c['Field'] for c in columns]
        logger.info(f"Columns in 'products' table: {col_names}")
    except Exception as e:
        logger.error(f"Could not describe products table: {e}")
        return

    # 2. Count total rows
    total = await db.fetch_one("SELECT COUNT(*) as c FROM products")
    logger.info(f"Total rows in 'products': {total['c']}")

    # 3. Count with original_url
    with_url = await db.fetch_one("SELECT COUNT(*) as c FROM products WHERE original_url IS NOT NULL")
    logger.info(f"Rows with original_url: {with_url['c']}")

    # 4. Check status distribution if column exists
    if 'status' in col_names:
        dist = await db.fetch_all("SELECT status, COUNT(*) as c FROM products GROUP BY status")
        logger.info(f"Status distribution: {dist}")
        
    # 5. Check duplicate URLs
    dupes = await db.fetch_all("""
        SELECT original_url, COUNT(*) as c 
        FROM products 
        WHERE original_url IS NOT NULL 
        GROUP BY original_url 
        HAVING c > 1
    """)
    logger.info(f"Duplicate URLs found: {len(dupes)}")
    if dupes:
        logger.info(f"Top 5 duplicates: {dupes[:5]}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(analyze_products())
