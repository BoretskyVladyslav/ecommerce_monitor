import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    print("Importing MainWindow...")
    from gui.windows.main_window import MainWindow
    print("✅ MainWindow imported successfully.")

    print("Importing SessionModal...")
    from gui.components.session_modal import SessionModal
    print("✅ SessionModal imported successfully.")

    print("Checking dependencies...")
    from utils.browser import BrowserManager
    from parsers.shein import SheinParser
    from utils.session_manager import SessionManager
    print("✅ Dependencies imported successfully.")

except Exception as e:
    print(f"❌ Verification Failed: {e}")
    sys.exit(1)
