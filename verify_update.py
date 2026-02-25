import asyncio
from multiprocessing.util import get_logger
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

print(f"Current directory: {current_dir}")
print(f"Python path: {sys.path[:3]}")

from playwright.async_api import async_playwright
from utils.browser import BrowserManager
from parsers.shein import SheinParser
import logging

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

def print_step(step_num, message):
    print()
    print_colored(f"{'=' * 70}", Colors.OKCYAN)
    print_colored(f"📍 STEP {step_num}: {message}", Colors.BOLD)
    print_colored(f"{'=' * 70}", Colors.OKCYAN)
    print()

async def verify_stealth(page):
    try:
        print_colored("🔍 Navigating to bot detection site...", Colors.OKBLUE)
        await page.goto("https://bot.sannysoft.com/", timeout=60000, wait_until="load")
        
        print_colored("⏳ Waiting for page analysis...", Colors.OKBLUE)
        await asyncio.sleep(4)
        
        try:
            webdriver_result = await page.evaluate("""
                () => {
                    const webdriverElement = document.evaluate(
                        "//td[contains(text(), 'navigator.webdriver')]/following-sibling::td",
                        document,
                        null,
                        XPathResult.FIRST_ORDERED_NODE_TYPE,
                        null
                    ).singleNodeValue;
                    return webdriverElement ? webdriverElement.textContent.trim() : 'unknown';
                }
            """)
            
            if webdriver_result.lower() == 'false':
                print_colored(f"✅ WebDriver Detection: {webdriver_result} (PASS)", Colors.OKGREEN)
            else:
                print_colored(f"⚠️  WebDriver Detection: {webdriver_result} (NEEDS REVIEW)", Colors.WARNING)
        except:
            print_colored("⚠️  Could not parse webdriver value from page", Colors.WARNING)
        
        screenshot_path = "verify_1_stealth.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print_colored(f"📸 Screenshot saved: {screenshot_path}", Colors.OKGREEN)
        print_colored("   👉 Manually review screenshot to verify all checks", Colors.OKCYAN)
        
        return True
        
    except Exception as e:
        print_colored(f"❌ Stealth test failed: {str(e)}", Colors.FAIL)
        return False

async def verify_shein_parser(page):
    try:
        print_colored("🛍️  Navigating to Shein login page...", Colors.OKBLUE)
        await page.goto("https://www.shein.com/user/auth/login", timeout=30000)
        
        print_colored("⏳ Waiting for page load...", Colors.OKBLUE)
        await asyncio.sleep(3)
        
        parser = SheinParser(page=page)
        print_colored(f"✅ SheinParser initialized (Logger: {parser.logger.name})", Colors.OKGREEN)
        print()
        
        print_colored("⌨️  Testing human_type() method...", Colors.OKBLUE)
        
        email_selectors = [
            "input[type='email']",
            "input[name='email']",
            "input[placeholder*='mail' i]",
            "input[placeholder*='Email' i]",
            "#email",
            "[data-testid='email']"
        ]
        
        email_found = False
        used_selector = None
        
        for selector in email_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1000):
                    used_selector = selector
                    print_colored(f"   📧 Found email field: {selector}", Colors.OKCYAN)
                    
                    print_colored("   ⏱️  Typing with human-like delays...", Colors.OKBLUE)
                    test_email = "test_stealth@gmail.com"
                    await parser.human_type(selector, test_email)
                    
                    await asyncio.sleep(1)
                    
                    input_value = await element.input_value()
                    if test_email in input_value:
                        print_colored(f"   ✅ Successfully typed: {input_value}", Colors.OKGREEN)
                        email_found = True
                    else:
                        print_colored(f"   ⚠️  Value mismatch. Expected: {test_email}, Got: {input_value}", Colors.WARNING)
                    
                    break
            except Exception as e:
                continue
        
        if not email_found:
            print_colored("   ⚠️  Email field not found or hidden", Colors.WARNING)
            print_colored("   💡 This might be due to regional blocking or page structure change", Colors.WARNING)
        
        print()
        
        print_colored("🖱️  Testing human_click() method...", Colors.OKBLUE)
        
        click_test_selectors = [
            "input[type='password']",
            "input[name='password']",
            "#password",
            "button[type='submit']",
            ".she-btn-black"
        ]
        
        click_found = False
        
        for selector in click_test_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=1000):
                    print_colored(f"   🎯 Found clickable element: {selector}", Colors.OKCYAN)
                    print_colored("   🖱️  Executing human_click() with mouse movement...", Colors.OKBLUE)
                    
                    await parser.human_click(selector)
                    
                    await asyncio.sleep(1)
                    
                    is_focused = await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('{selector}');
                            return el === document.activeElement;
                        }}
                    """)
                    
                    if is_focused:
                        print_colored(f"   ✅ Element successfully clicked and focused", Colors.OKGREEN)
                    else:
                        print_colored(f"   ⚠️  Click executed but focus unclear", Colors.WARNING)
                    
                    click_found = True
                    break
            except Exception as e:
                continue
        
        if not click_found:
            print_colored("   ⚠️  No clickable element found for testing", Colors.WARNING)
        
        print()
        
        print_colored("🛡️  Testing defense detection methods...", Colors.OKBLUE)
        
        try:
            risk_detected = await parser.detect_risk_challenge()
            slider_detected = await parser.detect_slider_captcha()
            
            print_colored(f"   • Risk Challenge: {'⚠️  DETECTED' if risk_detected else '✅ Not detected'}", 
                         Colors.WARNING if risk_detected else Colors.OKGREEN)
            print_colored(f"   • Slider Captcha: {'⚠️  DETECTED' if slider_detected else '✅ Not detected'}", 
                         Colors.WARNING if slider_detected else Colors.OKGREEN)
            
        except Exception as e:
            print_colored(f"   ❌ Defense detection error: {str(e)}", Colors.FAIL)
        
        print()
        
        screenshot_path = "verify_2_shein_interaction.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print_colored(f"📸 Screenshot saved: {screenshot_path}", Colors.OKGREEN)
        print_colored("   👉 Review screenshot to verify typed text and interactions", Colors.OKCYAN)
        
        return True
        
    except Exception as e:
        print_colored(f"❌ Shein parser test failed: {str(e)}", Colors.FAIL)
        import traceback
        print_colored(traceback.format_exc(), Colors.FAIL)
        return False

async def main():
    print_colored("\n" + "=" * 70, Colors.HEADER)
    print_colored("🔬 STEALTH & PARSER VERIFICATION SCRIPT v1.0", Colors.HEADER + Colors.BOLD)
    print_colored("=" * 70 + "\n", Colors.HEADER)
    
    print_colored("📋 This script will verify:", Colors.OKCYAN)
    print_colored("   1. Browser stealth configuration (webdriver masking)", Colors.OKCYAN)
    print_colored("   2. Human-like typing simulation", Colors.OKCYAN)
    print_colored("   3. Human-like mouse movement and clicking", Colors.OKCYAN)
    print_colored("   4. Defense mechanism detection\n", Colors.OKCYAN)
    
    browser_manager = BrowserManager()
    context = None
    browser = None
    page = None
    
    results = {
        'stealth': False,
        'parser': False
    }
    
    try:
        print_step(1, "Launching Browser")
        
        async with async_playwright() as p:
            session_data = {
                'headless': False,
                'proxy': None
            }
            
            print_colored("🚀 Initializing browser with advanced stealth...", Colors.OKBLUE)
            
            context, browser = await browser_manager.get_context(
                p,
                session_data=session_data,
                simplified=False,
                block_images=False,
                block_resources=False
            )
            
            print_colored("✅ Browser launched successfully", Colors.OKGREEN)
            print_colored(f"   • Headless Mode: {session_data.get('headless', False)}", Colors.OKCYAN)
            print_colored(f"   • Stealth Mode: ENABLED", Colors.OKCYAN)
            
            page = await context.new_page()
            
            print_step(2, "Stealth Configuration Test")
            results['stealth'] = await verify_stealth(page)
            
            print_step(3, "Shein Parser Test")
            results['parser'] = await verify_shein_parser(page)
            
            print_step(4, "Final Summary")
            
            print_colored("📊 VERIFICATION RESULTS:", Colors.BOLD)
            print_colored(f"   • Stealth Test: {'✅ PASS' if results['stealth'] else '❌ FAIL'}", 
                         Colors.OKGREEN if results['stealth'] else Colors.FAIL)
            print_colored(f"   • Parser Test: {'✅ PASS' if results['parser'] else '❌ FAIL'}", 
                         Colors.OKGREEN if results['parser'] else Colors.FAIL)
            print()
            
            if all(results.values()):
                print_colored("🎉 ALL TESTS PASSED!", Colors.OKGREEN + Colors.BOLD)
            else:
                print_colored("⚠️  SOME TESTS NEED REVIEW", Colors.WARNING + Colors.BOLD)
            
            print()
            print_colored("📁 Generated Files:", Colors.OKCYAN)
            for filename in ["verify_1_stealth.png", "verify_2_shein_interaction.png"]:
                if os.path.exists(filename):
                    size = os.path.getsize(filename) / 1024
                    print_colored(f"   • {filename} ({size:.1f} KB)", Colors.OKGREEN)
            
            print()
            print_colored("💡 Next Steps:", Colors.OKCYAN)
            print_colored("   1. Review both screenshots manually", Colors.OKCYAN)
            print_colored("   2. Check that webdriver=false in verify_1_stealth.png", Colors.OKCYAN)
            print_colored("   3. Verify typed text appears in verify_2_shein_interaction.png", Colors.OKCYAN)
            print()
            
            print_colored("⏳ Keeping browser open for 5 seconds...\n", Colors.OKBLUE)
            await asyncio.sleep(5)
            
    except KeyboardInterrupt:
        print_colored("\n\n⚠️  Interrupted by user", Colors.WARNING)
        
    except Exception as e:
        print_colored(f"\n❌ CRITICAL ERROR: {str(e)}", Colors.FAIL)
        import traceback
        print_colored(traceback.format_exc(), Colors.FAIL)
        sys.exit(1)
        
    finally:
        print_colored("\n🧹 Cleaning up...", Colors.OKBLUE)
        
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
        
        print_colored("✅ Cleanup complete\n", Colors.OKGREEN)
        print_colored("=" * 70 + "\n", Colors.HEADER)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_colored("\n👋 Goodbye!\n", Colors.OKCYAN)
        sys.exit(0)