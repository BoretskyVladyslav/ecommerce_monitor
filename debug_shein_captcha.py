
import asyncio
from playwright.async_api import async_playwright
import sys
import os

# Add parent dir to path so we can import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.captcha_detector import captcha_detector

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Visual debugging
        context = await browser.new_context()
        page = await context.new_page()
        
        url = "https://us.shein.com/pdsearch/Wonka" # Search page often triggers captcha
        print(f"Navigating to {url}...")
        
        try:
            await page.goto(url, timeout=60000)
            
            print(" वेटing for potential captcha...")
            await asyncio.sleep(10) # Let typical captcha load
            
            # 1. Run Detector
            print("\n----- RUNNING DETECTOR -----")
            result = await captcha_detector.detect(page, platform="shein", take_screenshot=True)
            print(f"Result: {result.to_dict()}")
            
            # 2. Deep Frame Inspection
            print("\n----- INSPECTING FRAMES -----")
            for frame in page.frames:
                print(f"Frame: {frame.url}")
                try:
                    # Check for keywords in frame content
                    content = await frame.content()
                    if "geetest" in content:
                        print("  [!] Found 'geetest' in content")
                    if "Please select" in content:
                         print("  [!] Found 'Please select' text")
                except:
                    print("  (Error reading content)")
                    
            # 3. Dump HTML of relevant parts
            print("\n----- DUMPING HTML SNIPPETS -----")
            # Check main page for geetest containers
            geetest_containers = await page.locator(".geetest_holder, .geetest_widget, .geetest_panel_box").all()
            print(f"Found {len(geetest_containers)} main page geetest containers.")
            
        except Exception as e:
            print(f"Error: {e}")
            
        finally:
            print("Done. Closing in 5s...")
            await asyncio.sleep(5)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
