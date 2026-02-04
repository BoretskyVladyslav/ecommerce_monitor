import json
import os
import asyncio
import random
from typing import Optional, Dict
from playwright.async_api import Playwright, BrowserContext, async_playwright, Route
from config.settings import settings

try:
    from playwright_stealth import stealth_async
except ImportError:
    try:
        # Fallback for playwright-stealth 2.0.1+
        from playwright_stealth import Stealth
        stealth_async = None
    except Exception as e:
        print(f"⚠️ Playwright Stealth Import Error (Fallback): {e}")
        Stealth = None
        stealth_async = None
except Exception as e:
    print(f"⚠️ Playwright Stealth Import Error: {e}")
    Stealth = None
    stealth_async = None

class BrowserManager:
    def __init__(self):
        # "Golden Standard" - Chrome 121 on Windows 10
        # Fixed to avoid "IP Schizophrenia" and engine mismatch
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        
        # Critical: Client Hints headers that MUST match User-Agent
        self.client_hints = {
            'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
        
        # Mobile User Agent (iPhone with iOS 16.6) - matches cookie generation script
        self.mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"

    async def get_context(self, playwright: Playwright, session_data: Dict = None, block_resources: bool = False, mobile_mode: bool = False, block_images: bool = True, simplified: bool = False) -> BrowserContext:
        """
        Creates and returns a new BrowserContext.
        If session_data is provided, uses its Proxy, UA and loads Cookies.
        if block_resources is True, blocks images, fonts, media.
        if mobile_mode is True, emulates iPhone 13 Pro (for sites requiring login on desktop).
        if block_images is True (default), blocks all images to save traffic.
        if simplified is True, disables advanced stealth and complex headers (for AliExpress).
        """
        # Default options
        launch_options = {
            "headless": settings.HEADLESS, 
            "args": ["--disable-blink-features=AutomationControlled"]
        }
        
        if simplified:
            # Simplified mode mimics the user's successful script
            launch_options["slow_mo"] = 100
        
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
        
        # Use Fixed User Agent (from session or default Golden Standard)
        if not user_agent:
            user_agent = self.mobile_user_agent if mobile_mode else self.user_agent

        browser = await playwright.chromium.launch(**launch_options)
        
        if simplified:
             # SIMPLIFIED MODE (AliExpress Fix)
             # Use minimal overrides. Let Playwright be Playwright.
             context_args = {
                "viewport": {"width": 1280, "height": 720}, # Standard desktop
                "device_scale_factor": 1,
                "locale": "en-US",
                "ignore_https_errors": True, # Critical from user script
                # Do NOT force complex headers or specific timezone if not needed
             }
             if user_agent:
                 context_args["user_agent"] = user_agent
                 
        elif mobile_mode:
            context_args = {
                "viewport": {"width": 390, "height": 844},
                "device_scale_factor": 3,
                "user_agent": user_agent,
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "is_mobile": True,
                "has_touch": True,
                "extra_http_headers": {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': 'https://www.google.com/'
                }
            }
        else:
            # Desktop Mode: Complete HTTP Headers - "Golden Standard" matching Chrome 121
            http_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.com/'
            }
            # Add Client Hints
            http_headers.update(self.client_hints)
            
            context_args = {
                "viewport": {"width": 1920, "height": 1080},
                "device_scale_factor": 1,
                "user_agent": user_agent,
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "extra_http_headers": http_headers
            }
        
        # Check for pre-saved session state (cookies from manual captcha solving)
        storage_state_file = None
        if session_data and session_data.get('storage_state'):
            storage_state_file = session_data['storage_state']
        else:
            # Auto-detect based on URL if available
            import os
            if session_data and 'url' in session_data:
                url = session_data['url']
                if 'shein' in url and os.path.exists('shein_session_state.json'):
                    storage_state_file = 'shein_session_state.json'
                    self.log_debug("🔑 Using saved Shein session")
                elif 'temu' in url and os.path.exists('temu_session_state.json'):
                    storage_state_file = 'temu_session_state.json'
                    self.log_debug("🔑 Using saved Temu session")
        
        # Add storage_state to context args if available
        if storage_state_file:
            context_args['storage_state'] = storage_state_file
            
        context = await browser.new_context(**context_args)

        # Resource Blocking - ALWAYS block images to save traffic (unless block_images=False)
        # Optionally block other resources if block_resources=True
        # CSS (stylesheet) НЕ блокуємо - він потрібен для селекторів!
        async def route_handler(route: Route):
            try:
                resource_type = route.request.resource_type
                
                # Block images to save traffic (unless explicitly disabled)
                if block_images and resource_type == "image":
                    await route.abort()
                # Block other heavy resources only if block_resources=True
                # НЕ блокуємо stylesheet - він потрібен!
                elif block_resources and resource_type in ["media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()
            except Exception as e:
                # Ignore errors from already-handled requests or closed pages
                if "Invalid InterceptionId" not in str(e) and "Target page" not in str(e):
                    self.log_debug(f"Route handler error: {e}")
        
        # Apply route handler to all requests
        await context.route("**/*", route_handler)
        if block_images:
            self.log_debug("🚫 Image blocking enabled (traffic saving mode)")
        if block_resources:
            self.log_debug("🚫 Additional resources blocked: media, fonts (CSS залишено)")


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

        # Value add: simplified mode skips weird JS injections that might flag us
        if not simplified:
            # Enhanced Anti-detect script
            await context.add_init_script("""
                // Hide webdriver traces
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                
                // Spoof plugins (real Chrome has them, bots often don't)
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                
                // Spoof languages to match headers
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            """)
        
        # Apply playwright-stealth (CRITICAL for Shein/Temu)
        # This patches many more detection vectors automatically
        try:
            # Create a temporary page to apply stealth
            temp_page = await context.new_page()
            
            # playwright-stealth 2.0.1+ uses Stealth class
            if not simplified:
                if stealth_async is None:
                    from playwright_stealth import Stealth
                    stealth = Stealth()
                    await stealth.apply_stealth_async(temp_page)
                else:
                    await stealth_async(temp_page)
            
            await temp_page.close()
            self.log_debug("✅ Playwright-stealth applied successfully")
        except Exception as e:
            self.log_debug(f"⚠️ Stealth application warning: {e}")
        
        return context, browser
    
    def log_debug(self, msg):
        """Helper for debug logging"""
        try:
            print(f"[BrowserManager] {msg}")
        except:
            pass

    async def run_manual_login(self, session_data: Dict):
        """
        Launches browser for manual user interaction. 
        Waits for browser close to save cookies.
        """
        async with async_playwright() as p:
            context, browser = await self.get_context(p, session_data, block_resources=False, block_images=False)
            
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
