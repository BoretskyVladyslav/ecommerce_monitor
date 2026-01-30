import asyncio
import traceback
from playwright.async_api import async_playwright

from config.settings import settings
from config.logger import setup_logger
from database.db_manager import DatabaseManager
from utils.browser import BrowserManager
from utils.cleaners import kill_chrome_processes
from utils.reporter import ReportGenerator

from parsers.direct import AmazonParser
from parsers.interactive import TemuParser, AliexpressParser, SheinParser
from parsers.exceptions import SoftBanException, ProductNotFoundException
from parsers.base import BaseParser

logger = setup_logger("MainOrchestrator")

async def update_option_status(option_id: int, status: int):
    """
    Updates product_options.status for a given option_id.
    Status: 1 = Active, 0 = Sold Out
    """
    db = DatabaseManager()
    
    query = """
        UPDATE product_options 
        SET status = %s
        WHERE id = %s
    """
    
    try:
        await db.execute(query, (status, option_id))
        status_str = "Active" if status == 1 else "Sold Out"
        logger.info(f"Updated Option {option_id}: Status={status} ({status_str})")
    except Exception as e:
        logger.error(f"DB Update failed for option {option_id}: {e}")

def get_parser_for_marketplace(marketplace: str, page) -> BaseParser:
    """Factory to return specific parser instance based on marketplace type."""
    m_type = marketplace.lower().strip()
    if m_type == 'amazon':
        return AmazonParser(page)
    elif m_type == 'shein':
        return SheinParser(page)
    elif m_type == 'temu':
        return TemuParser(page)
    elif m_type == 'aliexpress':
        return AliexpressParser(page)
    else:
        raise ValueError(f"Unknown marketplace type: {marketplace}")

async def process_item(sem: asyncio.Semaphore, item: dict, idx: int, total: int):
    """
    Process a single product option with HARD 30s TIMEOUT.
    
    item dict contains:
        - option_id: PK from product_options
        - url: Product URL  
        - marketplace: 'aliexpress', 'shein', 'temu', 'amazon'
        - option_name_1: First option (e.g., "Red")
        - option_name_2: Second option (e.g., "XL") - can be empty
    """
    async with sem:
        option_id = item.get('option_id')
        url = item.get('url')
        marketplace = item.get('marketplace')
        
        if not marketplace:
            logger.warning(f"No marketplace for option {option_id}, URL: {url}")
            return

        browser_manager = BrowserManager()
        context = None
        
        logger.info(f"Processing {idx}/{total}: Option {option_id} [{marketplace}] - {item.get('option_name_1', '')} / {item.get('option_name_2', '')}")

        try:
            async with async_playwright() as p:
                context = await browser_manager.get_context(p)
                page = await context.new_page()
                
                parser = get_parser_for_marketplace(marketplace, page)

                try:
                    
                    status = await asyncio.wait_for(
                        parser.parse_product(item), 
                        timeout=30
                    )
                    
                    await update_option_status(option_id, status)

                except asyncio.TimeoutError:
                    logger.error(f"TIMEOUT (30s) for Option {option_id}. Skipping update.")
                    
        except SoftBanException as e:
            logger.warning(f"SoftBan for Option {option_id}: {e} -> Skipping update.")
        except ProductNotFoundException as e:
            logger.info(f"Product Not Found {option_id}: {e} -> Marking Sold Out.")
            await update_option_status(option_id, 0)
        except Exception as e:
            logger.error(f"Error processing Option {option_id}: {e}")
            logger.error(traceback.format_exc())
        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass

async def main():
    kill_chrome_processes()
    db = DatabaseManager()
    
    try:
        await db.get_pool()
    except Exception as e:
        logger.critical(f"Could not connect to DB: {e}")
        return

    items = []
    try:
        items = await db.fetch_active_products()
    except Exception as e:
        logger.error(f"Failed to fetch items: {e}")
    
    logger.info(f"Found {len(items)} items to process.")

    semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BROWSERS)
    
    total = len(items)
    tasks = []
    for i, item in enumerate(items):
        tasks.append(process_item(semaphore, item, i+1, total))
    
    if tasks:
        await asyncio.gather(*tasks)
    
    logger.info("Batch processing complete.")

    logger.info("📊 Generating Excel Report...")
    try:
        reporter = ReportGenerator()
        report_file = await reporter.generate()
        logger.info(f"✅ Report saved: {report_file}")
    except Exception as e:
        logger.error(f"❌ Failed to generate report: {e}")

    await db.close()

    kill_chrome_processes()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Graceful Shutdown requested.")
