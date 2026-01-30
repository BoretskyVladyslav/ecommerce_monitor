import psutil
import logging
from config.logger import setup_logger

logger = setup_logger("Cleaners")

def kill_chrome_processes():
    """Kills all orphan chrome/chromedriver processes to free RAM."""
    logger.info("Cleaning up Chrome processes...")
    killed = 0
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'chrome' in proc.info['name'].lower() or 'playwright' in proc.info['name'].lower():
                proc.kill()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    logger.info(f"Killed {killed} orphan processes.")
