import asyncio
import sys
import os
import json
from datetime import datetime
from playwright.async_api import async_playwright

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from utils.browser import BrowserManager
from parsers.shein import SheinParser
from utils.session_manager import SessionManager

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_colored(message, color=Colors.OKGREEN):
    print(f"{color}{message}{Colors.ENDC}")

def print_header(message):
    print()
    print_colored("=" * 70, Colors.OKCYAN)
    print_colored(f"  {message}", Colors.BOLD + Colors.HEADER)
    print_colored("=" * 70, Colors.OKCYAN)
    print()

def print_progress(current, total, status="Processing"):
    """Display progress bar"""
    percentage = (current / total) * 100
    filled = int(percentage / 2)
    bar = "█" * filled + "░" * (50 - filled)
    print(f"\r{Colors.OKCYAN}[{bar}] {percentage:.1f}% ({current}/{total}) - {status}{Colors.ENDC}", end='', flush=True)

def load_accounts(accounts_file="data/accounts.json"):
    """Load accounts from JSON file"""
    if not os.path.exists(accounts_file):
        return None
    
    try:
        with open(accounts_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        
        if not isinstance(accounts, list):
            print_colored(f"❌ ERROR: {accounts_file} must contain a JSON array", Colors.FAIL)
            return None
        
        for i, acc in enumerate(accounts):
            if 'email' not in acc or 'password' not in acc:
                print_colored(f"❌ ERROR: Account {i+1} missing 'email' or 'password'", Colors.FAIL)
                return None
        
        return accounts
    
    except json.JSONDecodeError as e:
        print_colored(f"❌ ERROR: Invalid JSON in {accounts_file}: {e}", Colors.FAIL)
        return None
    except Exception as e:
        print_colored(f"❌ ERROR reading {accounts_file}: {e}", Colors.FAIL)
        return None

def create_sample_accounts_file(accounts_file="data/accounts.json"):
    """Create a sample accounts.json file"""
    sample_data = [
        {
            "email": "user1@example.com",
            "password": "SecurePassword123!",
            "proxy": None,
            "note": "Primary account"
        },
        {
            "email": "user2@example.com",
            "password": "AnotherPassword456!",
            "proxy": "http://username:password@proxy.example.com:8080",
            "note": "Secondary account with proxy"
        },
        {
            "email": "user3@example.com",
            "password": "ThirdPassword789!",
            "proxy": None,
            "note": "Backup account"
        }
    ]
    
    os.makedirs(os.path.dirname(accounts_file), exist_ok=True)
    
    with open(accounts_file, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, indent=4, ensure_ascii=False)
    
    return sample_data

async def detect_login_success(page, timeout=30):
    """
    Detect if login was successful by checking URL and page elements.
    Returns: (success: bool, needs_manual: bool, message: str)
    """
    try:
        # Wait a bit for navigation
        await asyncio.sleep(2)
        
        current_url = page.url
        
        # Check 1: URL changed from login page
        if "/user/auth/login" not in current_url and "/login" not in current_url.lower():
            # Check if we're on the main page or user dashboard
            if any(path in current_url for path in ["/user", "/account", "shein.com/"]):
                return (True, False, f"Login successful - navigated to {current_url}")
        
        # Check 2: Look for captcha or verification
        captcha_indicators = [
            ".geetest_slider_button",
            ".geetest_holder",
            "[class*='captcha']",
            "[class*='verification']",
            "[class*='slider-verify']"
        ]
        
        for selector in captcha_indicators:
            try:
                if await page.locator(selector).is_visible(timeout=1000):
                    return (False, True, "Captcha/verification detected - manual intervention needed")
            except:
                pass
        
        # Check 3: Look for error messages
        error_selectors = [
            "[class*='error']",
            "[class*='alert']",
            ".she-error-message",
            "[role='alert']"
        ]
        
        for selector in error_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=500):
                    error_text = await element.text_content()
                    if error_text and len(error_text) > 0:
                        return (False, False, f"Login error: {error_text[:100]}")
            except:
                pass
        
        # Check 4: Still on login page with no errors = might need more time
        if "/user/auth/login" in current_url:
            return (False, False, "Still on login page - no obvious error")
        
        # Default: assume success if not on login page
        return (True, False, "Login appears successful")
        
    except Exception as e:
        return (False, False, f"Error checking login status: {str(e)}")

async def create_session_for_account(
    account, 
    account_index, 
    total_accounts,
    browser_manager,
    session_manager,
    p
):
    """
    Create a session for a single account.
    Returns: (success: bool, session_path: str, message: str)
    """
    email = account['email']
    password = account['password']
    proxy = account.get('proxy')
    note = account.get('note', '')
    
    print_header(f"ACCOUNT {account_index + 1}/{total_accounts}")
    
    print_colored(f"📧 Email: {email}", Colors.OKCYAN)
    print_colored(f"🔑 Password: {'*' * len(password)}", Colors.OKCYAN)
    if proxy:
        print_colored(f"🌐 Proxy: {proxy}", Colors.OKCYAN)
    if note:
        print_colored(f"📝 Note: {note}", Colors.OKCYAN)
    print()
    
    # Generate unique session filename from email
    safe_email = email.replace('@', '_').replace('.', '_')
    session_filename = f"{safe_email}_session.json"
    session_path = os.path.join("data", "sessions", session_filename)
    
    os.makedirs(os.path.dirname(session_path), exist_ok=True)
    
    context = None
    browser = None
    page = None
    
    try:
        # Prepare session data with unique fingerprint
        session_data = {
            'headless': False,
            'proxy': proxy
        }
        
        print_colored("🚀 Launching browser with unique fingerprint...", Colors.OKBLUE)
        
        # Each account gets a fresh context with new fingerprint
        context, browser = await browser_manager.get_context(
            p,
            session_data=session_data,
            simplified=False,
            block_images=False,
            block_resources=False
        )
        
        print_colored("✅ Browser launched", Colors.OKGREEN)
        
        page = await context.new_page()
        
        print_colored("📍 Navigating to Shein login...", Colors.OKBLUE)
        await page.goto("https://www.shein.com/user/auth/login", timeout=60000, wait_until="domcontentloaded")
        
        await asyncio.sleep(3)
        print_colored("✅ Page loaded", Colors.OKGREEN)
        print()
        
        # Initialize parser
        parser = SheinParser(page=page)
        
        print_colored("🧹 Closing popups...", Colors.OKBLUE)
        await parser.close_popups(aggressive=True, max_attempts=3)
        await parser.dismiss_overlays()
        await asyncio.sleep(2)
        print_colored("✅ Popups handled", Colors.OKGREEN)
        print()
        
        # Auto-fill email
        print_colored("📧 Auto-filling email...", Colors.OKBLUE)
        email_selectors = [
            "input[type='email']",
            "input[name='email']",
            "input[placeholder*='mail' i]",
            "#email",
            "input[autocomplete='email']"
        ]
        
        email_entered = False
        for selector in email_selectors:
            try:
                if await page.locator(selector).is_visible(timeout=2000):
                    success = await parser.human_type(selector, email, clear_first=True, validate=True)
                    if success:
                        print_colored(f"✅ Email entered: {email}", Colors.OKGREEN)
                        email_entered = True
                        break
            except:
                continue
        
        if not email_entered:
            print_colored("⚠️  Could not auto-fill email", Colors.WARNING)
            return (False, session_path, "Failed to enter email")
        
        await asyncio.sleep(1.5)
        
        # Auto-fill password
        print_colored("🔐 Auto-filling password...", Colors.OKBLUE)
        password_selectors = [
            "input[type='password']",
            "input[name='password']",
            "#password",
            "input[autocomplete='current-password']"
        ]
        
        password_entered = False
        for selector in password_selectors:
            try:
                if await page.locator(selector).is_visible(timeout=2000):
                    success = await parser.human_type(selector, password, clear_first=True, validate=False)
                    if success:
                        print_colored(f"✅ Password entered", Colors.OKGREEN)
                        password_entered = True
                        break
            except:
                continue
        
        if not password_entered:
            print_colored("⚠️  Could not auto-fill password", Colors.WARNING)
            return (False, session_path, "Failed to enter password")
        
        await asyncio.sleep(1.5)
        print()
        
        # Click submit button
        print_colored("🖱️  Clicking Sign In button...", Colors.OKBLUE)
        submit_selectors = [
            "button[type='submit']",
            "button[aria-label*='Sign' i]",
            "button[aria-label*='Log' i]",
            ".she-btn-black",
            "[class*='submit-btn']",
            "[class*='login-btn']"
        ]
        
        submit_clicked = False
        for selector in submit_selectors:
            try:
                if await page.locator(selector).first.is_visible(timeout=1000):
                    await parser.human_click(selector)
                    print_colored(f"✅ Submit button clicked", Colors.OKGREEN)
                    submit_clicked = True
                    break
            except:
                continue
        
        if not submit_clicked:
            print_colored("⚠️  Could not click submit button", Colors.WARNING)
        
        print()
        await asyncio.sleep(3)
        
        # Smart detection loop
        print_colored("🔍 Detecting login result...", Colors.OKBLUE)
        
        success, needs_manual, message = await detect_login_success(page)
        
        print_colored(f"   {message}", Colors.OKCYAN)
        
        if needs_manual:
            print()
            print_colored("⚡ MANUAL INTERVENTION REQUIRED", Colors.WARNING)
            print_colored("   Please solve the captcha/verification in the browser", Colors.WARNING)
            print_colored("   Press ENTER when you are fully logged in...", Colors.WARNING)
            input()
            
            # Re-check after manual intervention
            success, _, message = await detect_login_success(page)
            print_colored(f"   {message}", Colors.OKCYAN)
        
        if not success:
            print()
            print_colored("⚠️  Login appears unsuccessful", Colors.WARNING)
            choice = input(f"{Colors.WARNING}Save session anyway? (y/N): {Colors.ENDC}").strip().lower()
            
            if choice != 'y':
                return (False, session_path, "Login unsuccessful, user chose not to save")
        
        # Save session
        print()
        print_colored("💾 Saving session...", Colors.OKBLUE)
        
        storage_state = await context.storage_state()
        
        cookies_count = len(storage_state.get('cookies', []))
        origins_count = len(storage_state.get('origins', []))
        
        print_colored(f"   📦 Captured {cookies_count} cookies", Colors.OKCYAN)
        print_colored(f"   🌐 Captured {origins_count} origin states", Colors.OKCYAN)
        
        if cookies_count == 0:
            print_colored("⚠️  WARNING: No cookies captured", Colors.WARNING)
            return (False, session_path, "No cookies captured - login likely failed")
        
        save_success = session_manager.save_storage_state(session_path, storage_state)
        
        if save_success:
            file_size = os.path.getsize(session_path) / 1024
            print_colored(f"✅ Session saved: {session_path} ({file_size:.2f} KB)", Colors.OKGREEN)
            
            # Countdown before closing
            print()
            for i in range(3, 0, -1):
                print(f"\r{Colors.OKCYAN}⏳ Closing browser in {i} seconds...{Colors.ENDC}", end='', flush=True)
                await asyncio.sleep(1)
            print()
            
            return (True, session_path, f"Session saved successfully with {cookies_count} cookies")
        else:
            return (False, session_path, "Failed to save session file")
    
    except Exception as e:
        import traceback
        error_msg = f"ERROR: {str(e)}"
        print_colored(f"❌ {error_msg}", Colors.FAIL)
        print_colored(traceback.format_exc(), Colors.FAIL)
        return (False, session_path, error_msg)
    
    finally:
        # Cleanup
        if page:
            try:
                await page.close()
            except:
                pass
        
        if context:
            try:
                await context.close()
            except:
                pass
        
        if browser:
            try:
                await browser.close()
            except:
                pass

async def main():
    print_header("🤖 AUTOMATED BULK SESSION CREATOR v1.0")
    
    accounts_file = "data/accounts.json"
    
    # Check if accounts file exists
    print_colored(f"📁 Looking for accounts file: {accounts_file}", Colors.OKCYAN)
    
    accounts = load_accounts(accounts_file)
    
    if accounts is None:
        print()
        print_colored(f"⚠️  Accounts file not found: {accounts_file}", Colors.WARNING)
        print()
        print_colored("Options:", Colors.OKCYAN)
        print_colored("  1. Create sample accounts.json file", Colors.OKCYAN)
        print_colored("  2. Enter details for a single account (manual mode)", Colors.OKCYAN)
        print_colored("  3. Exit and create the file manually", Colors.OKCYAN)
        print()
        
        choice = input(f"{Colors.BOLD}Choose option (1/2/3): {Colors.ENDC}").strip()
        
        if choice == '1':
            print()
            print_colored(f"📝 Creating sample file: {accounts_file}", Colors.OKBLUE)
            sample_accounts = create_sample_accounts_file(accounts_file)
            print_colored(f"✅ Sample file created with {len(sample_accounts)} accounts", Colors.OKGREEN)
            print()
            print_colored("Please edit this file with your real accounts and run the script again.", Colors.WARNING)
            print_colored(f"File location: {os.path.abspath(accounts_file)}", Colors.OKCYAN)
            return
        
        elif choice == '2':
            print()
            print_colored("🔧 Manual mode - single account", Colors.HEADER)
            
            email = input(f"{Colors.OKBLUE}📧 Enter email: {Colors.ENDC}").strip()
            if not email:
                print_colored("❌ Email cannot be empty", Colors.FAIL)
                return
            
            password = input(f"{Colors.OKBLUE}🔑 Enter password: {Colors.ENDC}").strip()
            if not password:
                print_colored("❌ Password cannot be empty", Colors.FAIL)
                return
            
            proxy = input(f"{Colors.OKBLUE}🌐 Enter proxy (optional, press Enter to skip): {Colors.ENDC}").strip()
            
            accounts = [{
                "email": email,
                "password": password,
                "proxy": proxy if proxy else None,
                "note": "Manual entry"
            }]
        
        else:
            print_colored("👋 Exiting. Please create accounts.json manually.", Colors.OKCYAN)
            print()
            print_colored("Expected format:", Colors.OKCYAN)
            print_colored("""
[
    {
        "email": "user@example.com",
        "password": "YourPassword123",
        "proxy": null,
        "note": "Optional description"
    }
]
            """, Colors.OKCYAN)
            return
    
    # Display accounts summary
    print()
    print_colored(f"✅ Loaded {len(accounts)} account(s)", Colors.OKGREEN)
    print()
    
    for i, acc in enumerate(accounts, 1):
        email = acc['email']
        proxy_status = "with proxy" if acc.get('proxy') else "no proxy"
        note = acc.get('note', '')
        print_colored(f"  {i}. {email} ({proxy_status}){' - ' + note if note else ''}", Colors.OKCYAN)
    
    print()
    proceed = input(f"{Colors.BOLD}Proceed with creating sessions? (y/N): {Colors.ENDC}").strip().lower()
    
    if proceed != 'y':
        print_colored("❌ Operation cancelled", Colors.WARNING)
        return
    
    # Initialize managers
    browser_manager = BrowserManager()
    session_manager = SessionManager()
    
    # Results tracking
    results = []
    successful = 0
    failed = 0
    
    print_header("🚀 STARTING BULK SESSION CREATION")
    
    async with async_playwright() as p:
        for i, account in enumerate(accounts):
            try:
                success, session_path, message = await create_session_for_account(
                    account,
                    i,
                    len(accounts),
                    browser_manager,
                    session_manager,
                    p
                )
                
                results.append({
                    'email': account['email'],
                    'success': success,
                    'session_path': session_path,
                    'message': message
                })
                
                if success:
                    successful += 1
                else:
                    failed += 1
                    
                    if i < len(accounts) - 1:  # Not the last account
                        print()
                        print_colored("❌ Session creation failed", Colors.FAIL)
                        retry = input(f"{Colors.WARNING}Retry this account? (y/N): {Colors.ENDC}").strip().lower()
                        
                        if retry == 'y':
                            print()
                            print_colored("🔄 Retrying...", Colors.OKBLUE)
                            success, session_path, message = await create_session_for_account(
                                account,
                                i,
                                len(accounts),
                                browser_manager,
                                session_manager,
                                p
                            )
                            
                            results[-1] = {
                                'email': account['email'],
                                'success': success,
                                'session_path': session_path,
                                'message': message
                            }
                            
                            if success:
                                successful += 1
                                failed -= 1
                        else:
                            skip = input(f"{Colors.WARNING}Skip to next account? (y/N): {Colors.ENDC}").strip().lower()
                            if skip != 'y':
                                print_colored("⚠️  Operation cancelled by user", Colors.WARNING)
                                break
                
                print()
                print_progress(i + 1, len(accounts), f"Completed - {successful} success, {failed} failed")
                print()
                
                # Brief pause between accounts
                if i < len(accounts) - 1:
                    print()
                    await asyncio.sleep(2)
            
            except KeyboardInterrupt:
                print()
                print_colored("⚠️  Operation interrupted by user", Colors.WARNING)
                break
    
    # Final summary
    print()
    print_header("📊 FINAL SUMMARY")
    
    print_colored(f"Total accounts processed: {len(results)}", Colors.BOLD)
    print_colored(f"✅ Successful: {successful}", Colors.OKGREEN)
    print_colored(f"❌ Failed: {failed}", Colors.FAIL)
    print()
    
    if len(results) > 0:
        print_colored("Detailed Results:", Colors.OKCYAN)
        print()
        
        for i, result in enumerate(results, 1):
            status_color = Colors.OKGREEN if result['success'] else Colors.FAIL
            status_icon = "✅" if result['success'] else "❌"
            
            print_colored(f"  {i}. {status_icon} {result['email']}", status_color)
            print_colored(f"     {result['message']}", Colors.OKCYAN)
            if result['success']:
                print_colored(f"     📁 {result['session_path']}", Colors.OKCYAN)
            print()
    
    # Save results to log file
    log_file = f"data/sessions/bulk_creation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total': len(results),
                'successful': successful,
                'failed': failed,
                'results': results
            }, f, indent=4, ensure_ascii=False)
        
        print_colored(f"📝 Log saved: {log_file}", Colors.OKGREEN)
    except Exception as e:
        print_colored(f"⚠️  Could not save log: {e}", Colors.WARNING)
    
    print()
    
    if successful > 0:
        print_colored("🎉 Session creation complete!", Colors.OKGREEN)
        print()
        print_colored("Next steps:", Colors.OKCYAN)
        print_colored("  1. Test sessions: python test_session.py", Colors.OKCYAN)
        print_colored("  2. Use sessions in your monitoring scripts", Colors.OKCYAN)
        print_colored("  3. Monitor session health periodically", Colors.OKCYAN)
    else:
        print_colored("⚠️  No sessions were created successfully", Colors.WARNING)
        print_colored("Check the error messages above and try again", Colors.WARNING)
    
    print()
    print_colored("=" * 70, Colors.OKCYAN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print()
        print_colored("👋 Goodbye!", Colors.OKCYAN)
        sys.exit(0)