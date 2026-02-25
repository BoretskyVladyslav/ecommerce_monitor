import json
import os
import asyncio
import random
from typing import Optional, Dict
from playwright.async_api import Playwright, BrowserContext, async_playwright, Route
from config.settings import settings
from utils.stealth_config import get_fingerprint, get_stealth_script
from utils.session_manager import SessionManager

try:
    from playwright_stealth import stealth_async
except ImportError:
    try:
        from playwright_stealth import Stealth
        stealth_async = None
    except:
        Stealth = None
        stealth_async = None

class BrowserManager:
    
    def __init__(self):
        self.session_manager = SessionManager()
        self.mobile_user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
    
    async def get_context(
        self,
        playwright: Playwright,
        session_data: Dict = None,
        block_resources: bool = False,
        mobile_mode: bool = False,
        block_images: bool = True,
        simplified: bool = False,
        storage_state_path: str = None
    ):
        
        proxy_hash = None
        if session_data and session_data.get('proxy'):
            proxy_config = session_data.get('proxy')
            if isinstance(proxy_config, dict):
                proxy_hash = proxy_config.get('server', '')
            else:
                proxy_hash = str(proxy_config)
        
        fingerprint = get_fingerprint(seed=proxy_hash)
        
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-setuid-sandbox",
            "--no-first-run",
            "--no-zygote",
            "--disable-accelerated-2d-canvas",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list"
        ]
        
        if not simplified:
            launch_args.append("--mute-audio")
        
        launch_options = {
            "headless": session_data.get('headless', settings.HEADLESS) if session_data else settings.HEADLESS,
            "args": launch_args
        }

        # Add storage state if provided and valid
        if storage_state_path and os.path.exists(storage_state_path):
            try:
                # Validate JSON first
                with open(storage_state_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                # Playwright expects 'storageState' in context args, NOT launch options
                # Wait, storageState is an argument for new_context, not launch.
                # I will handle this when creating the context below.
                pass 
            except Exception as e:
                print(f"⚠️ Invalid session file {storage_state_path}: {e}")
                storage_state_path = None
        
        
        if simplified:
            launch_options["slow_mo"] = 100
        
        if session_data and session_data.get('proxy'):
            from urllib.parse import urlparse
            proxy_str = session_data['proxy']
            
            if "://" not in proxy_str:
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
            except:
                launch_options["proxy"] = {"server": session_data['proxy']}
        
        browser = await playwright.chromium.launch(**launch_options)
        
        try:
            cdp_session = await browser.new_browser_cdp_session()
            await cdp_session.send('Page.addScriptToEvaluateOnNewDocument', {
                'source': """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                        configurable: true
                    });
                    delete navigator.__proto__.webdriver;
                """
            })
        except:
            pass
        
        user_agent = fingerprint["user_agent"]
        if mobile_mode:
            user_agent = self.mobile_user_agent
        
        if simplified:
            context_args = {
                "viewport": {"width": 1280, "height": 720},
                "device_scale_factor": 1,
                "locale": "en-US",
                "ignore_https_errors": True,
                "user_agent": user_agent
            }
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
            
            context_args = {
                "viewport": fingerprint["viewport"],
                "device_scale_factor": 1,
                "user_agent": user_agent,
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "extra_http_headers": http_headers
            }
        
        storage_state_file = None
        if session_data and session_data.get('storage_state'):
            storage_state_file = session_data['storage_state']
            if os.path.exists(storage_state_file):
                storage_state = self.session_manager.load_storage_state(storage_state_file, validate=True)
                if storage_state:
                    context_args['storage_state'] = storage_state_file
        elif session_data and 'url' in session_data:
            url = session_data['url']
            marketplace = None
            if 'shein' in url:
                marketplace = 'shein'
            elif 'temu' in url:
                marketplace = 'temu'
            elif 'aliexpress' in url:
                marketplace = 'aliexpress'
            
            if marketplace:
                auto_state_path = f'{marketplace}_session_state.json'
                if os.path.exists(auto_state_path):
                    storage_state = self.session_manager.load_storage_state(auto_state_path, validate=True)
                    if storage_state:
                        context_args['storage_state'] = auto_state_path
        
                    if storage_state:
                        context_args['storage_state'] = auto_state_path
        
        # Explicit argument overrides everything
        if storage_state_path and os.path.exists(storage_state_path):
             context_args['storage_state'] = storage_state_path

        context = await browser.new_context(**context_args)
        
        async def route_handler(route: Route):
            try:
                resource_type = route.request.resource_type
                
                page_instance = None
                try:
                    if route.request.frame:
                        page_instance = route.request.frame.page
                except:
                    pass
                
                effective_block_images = block_images
                if page_instance:
                    effective_block_images = getattr(page_instance, "image_blocking_enabled", block_images)
                
                if effective_block_images and resource_type == "image":
                    await route.abort()
                elif block_resources and resource_type in ["media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()
            except:
                pass
        
        await context.route("**/*", route_handler)
        
        if session_data and session_data.get('cookies_path'):
            path = session_data['cookies_path']
            cookies = self.session_manager.load_cookies(path, validate=True)
            if cookies:
                try:
                    await context.add_cookies(cookies)
                except:
                    pass
        
        stealth_script = get_stealth_script(fingerprint)
        
        await context.add_init_script(stealth_script)
        
        try:
            temp_page = await context.new_page()
            
            try:
                cdp = await temp_page.context.new_cdp_session(temp_page)
                await cdp.send('Page.addScriptToEvaluateOnNewDocument', {
                    'source': stealth_script
                })
            except:
                pass
            
            if not simplified:
                if stealth_async is None and Stealth:
                    stealth = Stealth()
                    await stealth.apply_stealth_async(temp_page)
                elif stealth_async:
                    await stealth_async(temp_page)
            
            await temp_page.close()
        except:
            pass
        
        return context, browser
    
    async def run_manual_login(self, session_data: Dict):
        async with async_playwright() as p:
            context, browser = await self.get_context(
                p,
                session_data,
                block_resources=False,
                block_images=False
            )
            
            try:
                page = await context.new_page()
            except Exception as e:
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
                await page.goto(start_url, timeout=60000)
                await page.wait_for_event("close", timeout=0)
            except:
                pass
            finally:
                if session_data.get('storage_state'):
                    try:
                        storage_state = await context.storage_state()
                        self.session_manager.save_storage_state(
                            session_data['storage_state'],
                            storage_state
                        )
                    except:
                        pass
                
                if session_data.get('cookies_path'):
                    try:
                        cookies = await context.cookies()
                        self.session_manager.save_cookies(
                            session_data['cookies_path'],
                            cookies
                        )
                    except:
                        pass
                
                await context.close()
                await browser.close()