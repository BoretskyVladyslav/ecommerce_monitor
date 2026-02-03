import logging
from config.settings import settings
from database.db_manager import DatabaseManager

logger = logging.getLogger("ConfigManager")

class ConfigManager:
    """
    Manages loading and saving application settings to the database.
    """
    
    @staticmethod
    def load_settings():
        """
        Loads settings from the DB and updates the global settings object.
        SYNCHRONOUS version using pymysql to avoid event loop conflicts.
        """
        logger.info("📥 Loading settings from Database...")
        
        try:
            import pymysql
            
            # Create synchronous connection
            conn = pymysql.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                db=settings.DB_NAME,
                cursorclass=pymysql.cursors.DictCursor
            )
            
            with conn.cursor() as cursor:
                cursor.execute("SELECT setting_key, setting_value FROM settings")
                rows = cursor.fetchall()
                
                for row in rows:
                    key = row['setting_key']
                    value = row['setting_value']
                    
                    # Update global settings object based on key
                    if key == 'threads':
                        settings.THREADS = int(value)
                        settings.MAX_CONCURRENT_BROWSERS = int(value)
                        logger.info(f"   ⚙️ THREADS set to: {settings.THREADS}")
                        
                    elif key == 'headless':
                        is_headless = value.lower() in ['1', 'true', 'yes']
                        settings.HEADLESS = is_headless
                        logger.info(f"   ⚙️ HEADLESS set to: {settings.HEADLESS}")
                        
                    elif key == 'delay_min':
                        settings.DELAY_MIN = int(value)
                        logger.info(f"   ⚙️ DELAY_MIN set to: {settings.DELAY_MIN}")
                        
                    elif key == 'delay_max':
                        settings.DELAY_MAX = int(value)
                        logger.info(f"   ⚙️ DELAY_MAX set to: {settings.DELAY_MAX}")
            
            conn.close()
            logger.info("✅ Settings loaded successfully.")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load settings from DB: {e}")
            return False

    @staticmethod
    async def save_setting(key: str, value: str):
        """
        Updates a single setting in the DB using a fresh connection.
        Bypasses DatabaseManager singleton to avoid Event Loop conflicts in threads.
        """
        import aiomysql
        try:
            conn = await aiomysql.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                db=settings.DB_NAME,
                autocommit=True
            )
            async with conn.cursor() as cur:
                query = """
                    INSERT INTO settings (setting_key, setting_value) 
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
                """
                await cur.execute(query, (key, value))
            
            conn.close()
            logger.info(f"💾 Saved setting {key} = {value}")
        except Exception as e:
            logger.error(f"❌ Save failed for {key}: {e}")

    @staticmethod
    async def save_all_settings():
        """
        Saves current values from settings.py to DB.
        Useful when UI updates variables first.
        """
        # Convert types to strings for storage
        headless_val = '1' if settings.HEADLESS else '0'
        
        await ConfigManager.save_setting('threads', str(settings.THREADS))
        await ConfigManager.save_setting('headless', headless_val)
        await ConfigManager.save_setting('delay_min', str(settings.DELAY_MIN))
        await ConfigManager.save_setting('delay_max', str(settings.DELAY_MAX))
