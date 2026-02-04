import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.browser import BrowserManager
from playwright.async_api import async_playwright

async def test_simplified_browser():
    bm = BrowserManager()
    
    print("🚀 Launching Simplified Browser (AliExpress Mode)...")
    
    async with async_playwright() as p:
        # Simulate MonitorEngine call
        context, browser = await bm.get_context(
            p, 
            session_data=None, 
            block_resources=True, 
            simplified=True,
            block_images=False
        )
        
        page = await context.new_page()
        
        print("🌍 Navigating to AliExpress...")
        try:
            await page.goto("https://www.aliexpress.com", timeout=60000)
            title = await page.title()
            print(f"✅ Page Loaded: {title}")
            
            # Check user agent
            ua = await page.evaluate("navigator.userAgent")
            print(f"🕵️ User Agent: {ua}")
            
            # Check for webdriver (should be present in simplified mode as we disabled the heavy stealth?)
            # Actually we just removed the *extra* definitions, but Playwright might still exist.
            # But the user script didn't care.
            
            await page.screenshot(path="verified_simplified_mode.png")
            print("📸 Screenshot saved to verified_simplified_mode.png")
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_simplified_browser())
