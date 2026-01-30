import asyncio
import logging
from gui.app import Application
from database.db_manager import DatabaseManager
from config.logger import setup_logger

# Setup logger
logger = setup_logger("Main")

async def init_services():
    """Initialize DB and other async services"""
    try:
        db = DatabaseManager()
        await db.init_db()
        await db.close() # Close pool to reset for other threads
        logger.info("Database initialized.")
    except Exception as e:
        logger.critical(f"Failed to init services: {e}")

def main():
    # Run async init in a way that doesn't conflict with mainloop if possible
    # Or just run it before GUI starts.
    # Since init_db is async, we can run it using asyncio.run() briefly.
    
    try:
        asyncio.run(init_services())
    except Exception as e:
        print(f"Init Error: {e}")

    # Launch GUI
    app = Application()
    app.run()

if __name__ == "__main__":
    main()
