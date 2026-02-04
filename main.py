import asyncio
import logging
import subprocess
import sys
import os
import atexit
from pathlib import Path

# 🔧 Налаштування постійної папки для браузерів (поруч із .exe)
if getattr(sys, 'frozen', False):
    # Якщо це .exe — папка поруч із виконуваним файлом
    BASE_DIR = Path(sys.executable).parent
else:
    # Якщо це звичайний Python — папка проекту
    BASE_DIR = Path(__file__).parent

BROWSERS_DIR = BASE_DIR / "browsers"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_DIR)

from gui.app import Application
from database.db_manager import DatabaseManager
from config.logger import setup_logger

# Setup logger
logger = setup_logger("Main")

def cleanup_browsers():
    """🧹 Вбиває всі Chrome/Chromium процеси при завершенні програми"""
    print("🧹 Cleaning up browser processes...")
    try:
        # Windows: taskkill
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"], 
                      capture_output=True, timeout=5)
        subprocess.run(["taskkill", "/F", "/IM", "chromium.exe", "/T"], 
                      capture_output=True, timeout=5)
        print("✅ Browser cleanup complete.")
    except Exception as e:
        print(f"⚠️ Browser cleanup failed: {e}")

# Реєструємо cleanup при виході
atexit.register(cleanup_browsers)

def ensure_browsers_installed():
    """Автоматично встановлює Chromium, якщо його немає (працює в EXE)"""
    
    # Перевірка: чи браузер вже встановлено?
    chromium_path = BROWSERS_DIR / "chromium-1097" / "chrome-win"
    if chromium_path.exists():
        print("✅ Browsers already installed. Skipping download.")
        return
    
    print("⚙️ Browsers not found. Installing...")
    
    # Перевіряємо, чи ми працюємо як EXE файл
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        # 🛑 МИ В EXE: Не можна використовувати subprocess(sys.executable)!
        # Викликаємо внутрішню функцію Playwright напряму.
        try:
            from playwright.__main__ import main as pw_cli
            
            # Зберігаємо старі аргументи запуску
            backup_argv = sys.argv
            
            # Підміняємо аргументи, ніби ми в консолі написали "playwright install chromium"
            sys.argv = ["playwright", "install", "chromium"]
            
            print("📦 Installing Chromium (Internal)...")
            try:
                pw_cli() # Запускаємо установку
            except SystemExit:
                pass # Playwright намагатиметься закрити програму після успіху, ми це ловимо
            
            print("✅ Internal install check finished.")
            
            # Повертаємо аргументи як було
            sys.argv = backup_argv
            
        except Exception as e:
            print(f"⚠️ Internal install failed: {e}")
            print("Please install browsers manually if needed.")
            
    else:
        # ✅ МИ В PYTHON: Тут subprocess працює нормально
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            print("✅ Browsers are ready.")
        except Exception as e:
            print(f"⚠️ Dev install failed: {e}")

async def init_services():
    """Initialize DB and other async services"""
    try:
        db = DatabaseManager()
        await db.init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.critical(f"Failed to init services: {e}")

def main():
    # Load Settings from DB BEFORE starting async services
    # This is now synchronous and safe
    from utils.config_manager import ConfigManager
    ConfigManager.load_settings()
    
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
    # Спочатку фікс шляху (щоб браузери ставилися в папку користувача, а не системи)
    # os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0" # Можна розкоментувати для локальної установки
    
    # Спробувати довстановити браузери
    ensure_browsers_installed() 
    
    main()
