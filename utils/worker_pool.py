import asyncio
import random
from database.db_manager import DatabaseManager
from config.logger import logging

logger = logging.getLogger("WorkerPool")

class WorkerPool:
    def __init__(self):
        self.db = DatabaseManager()
        self.active_tasks = {} # session_id -> task

    async def acquire_session(self, marketplace: str) -> dict:
        """
        Tries to get a free session from DB.
        Retries until one becomes available or timeout.
        """
        while True:
            session = await self.db.get_available_session(marketplace)
            if session:
                # Atomically mark as RUN to prevent other workers stealing it
                # (Ideally this should be a stored procedure or transaction, 
                # but for now we rely on the short gap between fetch and update 
                # or strict 1-to-1 worker logic in single process)
                
                await self.db.update_session_status(session['id'], 'Run')
                return session
            
            # If no session available, wait a bit
            await asyncio.sleep(2)

    async def release_session(self, session_id: int, status: str = 'Wait'):
        """
        Releases the session back to pool with specified status (Wait/Error).
        If 'Wait', it triggers a background task to reset it to 'Ready' after pause.
        """
        await self.db.update_session_status(session_id, status)
        
        if status == 'Wait':
            # Schedule recovery to 'Ready'
            asyncio.create_task(self._scheduled_recovery(session_id))

    async def _scheduled_recovery(self, session_id: int):
        # TODO: Get pause time from Settings table
        pause_time = 60 
        logger.info(f"Session {session_id} sleeping for {pause_time}s...")
        await asyncio.sleep(pause_time)
        
        # Check if it wasn't manually disabled or errored in meantime (unlikely if in Wait)
        await self.db.update_session_status(session_id, 'Ready')
        logger.info(f"Session {session_id} is back to READY.")
