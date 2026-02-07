
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = "https://us.shein.com/SHEIN-Teen-Girls-Black-Knit-Halter-Neck-Sleeveless-Cinched-Waist-A-Line-Party-Dress-Suitable-For-Christmas-And-New-Year-p-327889620.html"
        print(f"Navigating to {url}...")
        
        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_timeout(5000) # Wait for JS to init
            
            # Check for common Shein data variables
            results = await page.evaluate("""() => {
                const vars = ['productIntroData', 'gbProductData', 'gbProduct', 'detail', 'product_intro_data'];
                const found = {};
                for (const v of vars) {
                    if (window[v]) {
                        found[v] = {
                            keys: Object.keys(window[v]),
                            sample: JSON.stringify(window[v]).substring(0, 200)
                        };
                    }
                }
                
                // Also search for script tags with product info
                const scripts = Array.from(document.querySelectorAll('script')).map(s => s.textContent);
                const likelyJSON = scripts.filter(s => s && s.includes('productIntroData'));
                
                return {
                    foundVars: found,
                    scriptsCount: likelyJSON.length
                };
            }""")
            
            print("Extraction Results:")
            print(json.dumps(results, indent=2))
            
        except Exception as e:
            print(f"Error: {e}")
            # Take screenshot on error
            await page.screenshot(path="debug_error.png")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
