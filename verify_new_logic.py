import asyncio
from database.db_manager import DatabaseManager
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestLogic")

async def test_fetch_active_products():
    db = DatabaseManager()
    
    logger.info("--- Testing fetch_active_products Logic ---")
    tasks = await db.fetch_active_products()
    
    if not tasks:
        logger.warning("No active products/tasks found. Cannot verify variant logic without data.")
        return

    variant_tasks = [t for t in tasks if t.get('table') == 'product_options']
    
    if variant_tasks:
        logger.info(f"✅ Found {len(variant_tasks)} tasks targeting specific variants!")
        sample = variant_tasks[0]
        logger.info(f"Sample Task: Option ID={sample['option_id']}, Color='{sample.get('target_color')}', Size='{sample.get('target_size')}'")
        
        if sample.get('target_color') or sample.get('target_size'):
            logger.info("✅ SUCCESS: Engine is correctly passing target variant parameters.")
        else:
            logger.warning("⚠️ WARNING: Variant task found, but target parameters are missing/empty.")
    else:
        logger.info("ℹ️ No specific variant tasks found (only legacy/monitored_product_options tasks).")
        logger.info("To fully test, verify that the 'product_options' table has entries for mapped products.")
        
    monitored_tasks = [t for t in tasks if t.get('table') == 'monitored_product_options']
    logger.info(f"Found {len(monitored_tasks)} legacy tasks.")

if __name__ == "__main__":
    asyncio.run(test_fetch_active_products())
