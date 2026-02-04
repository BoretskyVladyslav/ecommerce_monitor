import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from playwright.async_api import async_playwright
from utils.browser import BrowserManager
import random

async def debug_recaptcha():
    print("🐞 Starting AliExpress Recaptcha Probe...")
    bm = BrowserManager()
    
    async with async_playwright() as p:
        # Enable images for visual captcha debugging
        context, browser = await bm.get_context(p, session_data=None, block_resources=True, block_images=False)
        page = await context.new_page()
        
        try:
            # URL that previously triggered captcha
            url = "https://www.aliexpress.us/item/3256803795063866.html"
            print(f"🌐 Navigating to {url}...")
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            
            # Check for captcha
            print("👀 Looking for Recaptcha...")
            is_present = await page.locator("iframe[src*='recaptcha'], .g-recaptcha").count() > 0
            
            if not is_present:
                print("⚠️ No Recaptcha found immediately. Scrolling to trigger...")
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(2)
                is_present = await page.locator("iframe[src*='recaptcha'], .g-recaptcha").count() > 0

            if not is_present:
                print("❌ Could not trigger Recaptcha. Exiting.")
                return

            print("✅ Recaptcha Found! analyzing structure...")
            
            # 1. Inspect Widget for data-callback
            print("\n--- Widget Attributes ---")
            info = await page.evaluate("""() => {
                const widget = document.querySelector('.g-recaptcha, .recaptcha-checkbox, iframe[title*="reCAPTCHA"], iframe[src*="recaptcha"]');
                if (!widget) return "Widget not found in DOM query";
                
                const parent = widget.closest('.g-recaptcha') || widget.parentElement;
                
                return {
                    tagName: widget.tagName,
                    src: widget.src,
                    dataSet: widget.dataset,
                    parentDataSet: parent ? parent.dataset : {},
                    parentHTML: parent ? parent.outerHTML.substring(0, 300) : "No parent"
                };
            }""")
            print(info)
            
            # 2. Inspect Global Scope for Callback functions
            print("\n--- Window / Global Scope Analysis ---")
            callbacks = await page.evaluate("""() => {
                const likelyCallbacks = [];
                for (const key in window) {
                    if (typeof window[key] === 'function') {
                        // filtering for common obfuscated names or recaptcha related
                        if (key.includes("recaptcha") || key.includes("callback") || key.length < 5) {
                           likelyCallbacks.push(key); 
                        }
                    }
                }
                return likelyCallbacks;
            }""")
            print(f"Potential global functions: {callbacks[:50]}") # limit output

            # 3. Check for specific hidden textareas
            print("\n--- Hidden Inputs ---")
            inputs = await page.evaluate("""() => {
                const els = document.querySelectorAll('textarea[name="g-recaptcha-response"], input[name="g-recaptcha-response"]');
                return Array.from(els).map(el => ({
                    tagName: el.tagName,
                    id: el.id,
                    className: el.className,
                    parentElement: el.parentElement.tagName
                }));
            }""")
            print(inputs)

            print("\n📸 Probe complete.")
            await page.pause() # Keep open to manually inspect if needed (in headed mode) but this is headless usually.
            
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_recaptcha())
