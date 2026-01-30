import json
import os
import asyncio
from typing import Optional, Dict
from playwright.async_api import Playwright, BrowserContext, async_playwright
from config.settings import settings

class BrowserManager:
    def __init__(self):
        pass

    async def get_context(self, playwright: Playwright, session_data: Dict = None) -> BrowserContext:
        """
        Creates and returns a new BrowserContext.
        If session_data is provided, uses its Proxy, UA and loads Cookies.
        """
        # Default options
        launch_options = {
            "headless": False, 
            "args": ["--disable-blink-features=AutomationControlled"]
        }
        
        user_agent = None
        
        # Override with session settings
        if session_data:
            if session_data.get('proxy'):
                from urllib.parse import urlparse
                proxy_str = session_data['proxy']
                
                # Check for "user:pass@ip:port" vs "ip:port" vs "scheme://..."
                if "://" not in proxy_str:
                    # Provide default scheme if missing
                    proxy_str = f"http://{proxy_str}"

                try:
                    parsed = urlparse(proxy_str)
                    proxy_config = {
                        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
                    }
                    if parsed.username:
                        proxy_config["username"] = parsed.username
                    if parsed.password:
                        proxy_config["password"] = parsed.password
                    
                    launch_options["proxy"] = proxy_config
                except Exception as e:
                    print(f"Proxy parse error: {e}. using raw string.")
                    launch_options["proxy"] = {"server": session_data['proxy']}
            
            user_agent = session_data.get('user_agent')

        # Fallback to global setting if no session proxy but specific logic needed? 
        # Requirement says "1 session = 1 unique session", so we stick to session_data.
        
        browser = await playwright.chromium.launch(**launch_options)
        
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1,
        }
        
        if user_agent:
            context_args["user_agent"] = user_agent
            
        context = await browser.new_context(**context_args)

        # Load Cookies
        if session_data and session_data.get('cookies_path'):
            path = session_data['cookies_path']
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        cookies = json.load(f)
                        await context.add_cookies(cookies)
                except Exception as e:
                    print(f"Failed to load cookies: {e}")

        # Anti-detect script
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        return context, browser

    async def run_manual_login(self, session_data: Dict):
        """
        Launches browser for manual user interaction. 
        Waits for browser close to save cookies.
        """
        async with async_playwright() as p:
            context, browser = await self.get_context(p, session_data)
            
            # Additional error handler for page creation
            try:
                page = await context.new_page()
            except Exception as e:
                print(f"Error creating page: {e}")
                await browser.close()
                return

            urls = {
                'amazon': 'https://www.amazon.com',
                'shein': 'https://www.shein.com',
                'temu': 'https://www.temu.com',
                'aliexpress': 'https://www.aliexpress.com'
            }
            start_url = urls.get(session_data.get('type', ''), 'https://www.google.com')
            
            try:
                print(f"Navigating to {start_url} using proxy {session_data.get('proxy', 'direct')}...")
                # Increase timeout for proxy
                await page.goto(start_url, timeout=60000)
                print(f"Manual session started for {session_data.get('name')}. Close browser to save cookies.")
                
                # Wait for the browser to be closed by the user
                # Playwright doesn't have a direct "wait_until_closed" for the browser app window easily in this context
                # properly without hanging. 
                # A simple way is to poll execution or wait for a page close event.
                
                # We will wait indefinitely until page is closed.
                await page.wait_for_event("close", timeout=0) 
                
            except Exception as e:
                print(f"Session interrupted or closed: {e}")
            finally:
                # Save Cookies
                if session_data.get('cookies_path'):
                    try:
                        cookies = await context.cookies()
                        os.makedirs(os.path.dirname(session_data['cookies_path']), exist_ok=True)
                        with open(session_data['cookies_path'], 'w') as f:
                            json.dump(cookies, f)
                        print(f"Cookies saved to {session_data['cookies_path']}")
                    except Exception as e:
                        print(f"Failed to save cookies: {e}")
                
                await context.close()
                await browser.close()
