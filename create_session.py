import asyncio
import sys
import os
from getpass import getpass
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

async def main():
    print_header("🔐 SHEIN SESSION CREATOR v1.0")
    
    print_colored("This script will help you create an authenticated Shein session.", Colors.OKCYAN)
    print_colored("You will need to manually solve any captcha or verification challenges.", Colors.OKCYAN)
    print()
    
    email = input(f"{Colors.OKBLUE}📧 Enter Shein Email: {Colors.ENDC}").strip()
    if not email:
        print_colored("❌ Email cannot be empty!", Colors.FAIL)
        return
    
    password = getpass(f"{Colors.OKBLUE}🔑 Enter Shein Password (hidden): {Colors.ENDC}")
    if not password:
        print_colored("❌ Password cannot be empty!", Colors.FAIL)
        return
    
    print()
    print_colored(f"✅ Credentials captured", Colors.OKGREEN)
    print_colored(f"   Email: {email}", Colors.OKCYAN)
    print_colored(f"   Password: {'*' * len(password)}", Colors.OKCYAN)
    print()
    
    session_filename = input(f"{Colors.OKBLUE}💾 Session filename (default: shein_account_1.json): {Colors.ENDC}").strip()
    if not session_filename:
        session_filename = "shein_account_1.json"
    
    if not session_filename.endswith('.json'):
        session_filename += '.json'
    
    session_path = os.path.join("data", "sessions", session_filename)
    
    os.makedirs(os.path.dirname(session_path), exist_ok=True)
    
    print()
    print_colored(f"📁 Session will be saved to: {session_path}", Colors.OKCYAN)
    print()
    
    input(f"{Colors.WARNING}⚠️  Press ENTER to launch browser and begin...{Colors.ENDC}")
    
    browser_manager = BrowserManager()
    session_manager = SessionManager()
    context = None
    browser = None
    page = None
    
    try:
        print_header("🚀 LAUNCHING BROWSER")
        
        async with async_playwright() as p:
            session_data = {
                'headless': False,
                'proxy': None
            }
            
            print_colored("🌐 Initializing stealth browser...", Colors.OKBLUE)
            
            context, browser = await browser_manager.get_context(
                p,
                session_data=session_data,
                simplified=False,
                block_images=False,
                block_resources=False
            )
            
            print_colored("✅ Browser launched successfully", Colors.OKGREEN)
            print()
            
            page = await context.new_page()
            
            print_header("🛍️  NAVIGATING TO SHEIN LOGIN")
            
            print_colored("📍 Loading https://www.shein.com/user/auth/login ...", Colors.OKBLUE)
            await page.goto("https://www.shein.com/user/auth/login", timeout=60000, wait_until="domcontentloaded")
            
            print_colored("⏳ Waiting for page to settle...", Colors.OKBLUE)
            await asyncio.sleep(3)
            
            print_colored("✅ Page loaded", Colors.OKGREEN)
            print()
            
            print_header("🤖 AUTOMATED LOGIN PROCESS")
            
            parser = SheinParser(page=page)
            
            print_colored("🧹 Closing popups and overlays...", Colors.OKBLUE)
            await parser.close_popups(aggressive=True, max_attempts=3)
            await parser.dismiss_overlays()
            await asyncio.sleep(2)
            
            print_colored("✅ Popups handled", Colors.OKGREEN)
            print()
            
            print_colored("📧 Attempting to enter email...", Colors.OKBLUE)
            
            email_selectors = [
                "input[type='email']",
                "input[name='email']",
                "input[placeholder*='mail' i]",
                "input[placeholder*='Email' i]",
                "#email",
                "[data-testid='email']",
                "input[autocomplete='email']"
            ]
            
            email_entered = False
            for selector in email_selectors:
                try:
                    if await page.locator(selector).is_visible(timeout=2000):
                        print_colored(f"   📝 Found email field: {selector}", Colors.OKCYAN)
                        success = await parser.human_type(selector, email, clear_first=True, validate=True)
                        
                        if success:
                            print_colored(f"   ✅ Email entered successfully: {email}", Colors.OKGREEN)
                            email_entered = True
                            break
                        else:
                            print_colored(f"   ⚠️  Failed to enter email in {selector}, trying next...", Colors.WARNING)
                except Exception as e:
                    continue
            
            if not email_entered:
                print_colored("   ⚠️  Could not automatically enter email", Colors.WARNING)
                print_colored("   💡 You may need to enter it manually in the browser", Colors.WARNING)
            
            print()
            await asyncio.sleep(1.5)
            
            print_colored("🔐 Attempting to enter password...", Colors.OKBLUE)
            
            password_selectors = [
                "input[type='password']",
                "input[name='password']",
                "#password",
                "[data-testid='password']",
                "input[autocomplete='current-password']"
            ]
            
            password_entered = False
            for selector in password_selectors:
                try:
                    if await page.locator(selector).is_visible(timeout=2000):
                        print_colored(f"   🔒 Found password field: {selector}", Colors.OKCYAN)
                        success = await parser.human_type(selector, password, clear_first=True, validate=False)
                        
                        if success:
                            print_colored(f"   ✅ Password entered successfully", Colors.OKGREEN)
                            password_entered = True
                            break
                        else:
                            print_colored(f"   ⚠️  Failed to enter password in {selector}, trying next...", Colors.WARNING)
                except Exception as e:
                    continue
            
            if not password_entered:
                print_colored("   ⚠️  Could not automatically enter password", Colors.WARNING)
                print_colored("   💡 You may need to enter it manually in the browser", Colors.WARNING)
            
            print()
            await asyncio.sleep(1.5)
            
            print_colored("🖱️  Attempting to click Sign In button...", Colors.OKBLUE)
            
            submit_selectors = [
                "button[type='submit']",
                "button[aria-label*='Sign' i]",
                "button[aria-label*='Log' i]",
                ".she-btn-black",
                "[class*='submit-btn']",
                "[class*='login-btn']",
                "[class*='sign-in']",
                "button:has-text('Sign In')",
                "button:has-text('Log In')",
                "button:has-text('Continue')"
            ]
            
            submit_clicked = False
            for selector in submit_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.is_visible(timeout=1000):
                        print_colored(f"   🎯 Found submit button: {selector}", Colors.OKCYAN)
                        await parser.human_click(selector)
                        print_colored(f"   ✅ Submit button clicked", Colors.OKGREEN)
                        submit_clicked = True
                        break
                except Exception as e:
                    continue
            
            if not submit_clicked:
                print_colored("   ⚠️  Could not automatically click submit button", Colors.WARNING)
                print_colored("   💡 You may need to click it manually in the browser", Colors.WARNING)
            
            print()
            await asyncio.sleep(3)
            
            print_header("⚡ MANUAL INTERVENTION REQUIRED")
            
            print_colored("🔔 The browser is now waiting for you to complete the login process.", Colors.WARNING)
            print_colored("", Colors.WARNING)
            print_colored("Please complete these steps in the browser window:", Colors.OKCYAN)
            print_colored("  1. ✅ Solve any CAPTCHA challenges (slider, images, etc.)", Colors.OKCYAN)
            print_colored("  2. ✅ Complete email verification if prompted", Colors.OKCYAN)
            print_colored("  3. ✅ Handle any 2FA or SMS codes", Colors.OKCYAN)
            print_colored("  4. ✅ Wait until you are FULLY LOGGED IN to the main Shein page", Colors.OKCYAN)
            print_colored("", Colors.WARNING)
            print_colored("⏸️  The script will wait indefinitely...", Colors.WARNING)
            print()
            
            input(f"{Colors.BOLD}{Colors.OKGREEN}✋ Press ENTER when you are fully logged in and see your account dashboard...{Colors.ENDC}")
            
            print()
            print_header("💾 SAVING SESSION")
            
            print_colored("📊 Capturing browser state...", Colors.OKBLUE)
            
            current_url = page.url
            print_colored(f"   Current URL: {current_url}", Colors.OKCYAN)
            
            if "/user/auth/login" in current_url:
                print_colored("", Colors.WARNING)
                print_colored("⚠️  WARNING: You appear to still be on the login page!", Colors.WARNING)
                print_colored("   This might mean login was not successful.", Colors.WARNING)
                print_colored("", Colors.WARNING)
                
                proceed = input(f"{Colors.WARNING}Continue saving session anyway? (y/N): {Colors.ENDC}").strip().lower()
                if proceed != 'y':
                    print_colored("❌ Session save cancelled", Colors.FAIL)
                    return
            
            storage_state = await context.storage_state()
            
            cookies_count = len(storage_state.get('cookies', []))
            origins_count = len(storage_state.get('origins', []))
            
            print_colored(f"   📦 Captured {cookies_count} cookies", Colors.OKCYAN)
            print_colored(f"   🌐 Captured {origins_count} origin states", Colors.OKCYAN)
            
            if cookies_count == 0:
                print_colored("", Colors.WARNING)
                print_colored("⚠️  WARNING: No cookies found!", Colors.WARNING)
                print_colored("   This likely means login was not successful.", Colors.WARNING)
                print_colored("", Colors.WARNING)
            
            print_colored(f"💾 Saving to {session_path}...", Colors.OKBLUE)
            
            success = session_manager.save_storage_state(session_path, storage_state)
            
            if success:
                print_colored("✅ Session saved successfully!", Colors.OKGREEN)
                print()
                
                file_size = os.path.getsize(session_path) / 1024
                print_colored(f"📁 Session file details:", Colors.OKCYAN)
                print_colored(f"   Path: {session_path}", Colors.OKCYAN)
                print_colored(f"   Size: {file_size:.2f} KB", Colors.OKCYAN)
                print_colored(f"   Cookies: {cookies_count}", Colors.OKCYAN)
                print_colored(f"   Origins: {origins_count}", Colors.OKCYAN)
                print()
                
                print_header("✅ SESSION CREATION COMPLETE")
                
                print_colored("🎉 Your Shein session has been saved successfully!", Colors.OKGREEN)
                print()
                print_colored("📋 Next steps:", Colors.OKCYAN)
                print_colored(f"   1. Use this session in your monitoring scripts:", Colors.OKCYAN)
                print_colored(f"      session_data = {{'storage_state': '{session_path}'}}", Colors.OKCYAN)
                print_colored(f"   2. Test the session validity periodically", Colors.OKCYAN)
                print_colored(f"   3. Re-run this script if the session expires", Colors.OKCYAN)
                print()
                
                print_colored("⏳ Keeping browser open for 5 seconds...", Colors.OKBLUE)
                await asyncio.sleep(5)
                
            else:
                print_colored("❌ Failed to save session!", Colors.FAIL)
                print_colored("   Check file permissions and disk space", Colors.FAIL)
        
    except KeyboardInterrupt:
        print()
        print_colored("⚠️  Session creation interrupted by user", Colors.WARNING)
        sys.exit(0)
        
    except Exception as e:
        print()
        print_colored(f"❌ ERROR: {str(e)}", Colors.FAIL)
        import traceback
        print_colored(traceback.format_exc(), Colors.FAIL)
        sys.exit(1)
        
    finally:
        print()
        print_colored("🧹 Cleaning up browser resources...", Colors.OKBLUE)
        
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
        
        print_colored("✅ Cleanup complete", Colors.OKGREEN)
        print()
        print_colored("=" * 70, Colors.OKCYAN)
        print()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print()
        print_colored("👋 Goodbye!", Colors.OKCYAN)
        sys.exit(0)