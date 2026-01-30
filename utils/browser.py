import random
from typing import Optional
from playwright.async_api import Playwright, BrowserContext
from config.settings import settings

class BrowserManager:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]

    def __init__(self):
        pass

    async def get_context(self, playwright: Playwright) -> BrowserContext:
        """
        Creates and returns a new BrowserContext with anti-detection settings.
        """
        user_agent = random.choice(self.USER_AGENTS)
        
        args = [
            "--disable-blink-features=AutomationControlled",
        ]

        launch_options = {
            "headless": False, 
            "args": args
        }
        
        if settings.PROXY_URL:
             launch_options["proxy"] = {"server": settings.PROXY_URL}

        browser = await playwright.chromium.launch(**launch_options)
        
        context = await browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )

        async def safe_handler(route):
            try:
                await route.abort()
            except Exception:
                pass
                
        await context.route("**/*.{png,jpg,jpeg,gif,webp,svg,mp4,woff,woff2}", safe_handler)

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        return context
