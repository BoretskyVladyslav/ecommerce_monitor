from abc import ABC
from playwright.async_api import Page
import asyncio
from config.logger import setup_logger

class BaseParser(ABC):
    def __init__(self, page: Page):
        self.page = page
        self.logger = setup_logger(self.__class__.__name__)

    async def Maps(self, url: str):
        """
         robust navigation with retry logic.
        """
        max_retries = 3
        for i in range(max_retries):
            try:
                self.logger.info(f"Navigating to {url} (Attempt {i+1})")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(2) 
                return True
            except Exception as e:
                self.logger.warning(f"Navigation failed: {e}")
                if i == max_retries - 1:
                    self.logger.error("Max retries reached for navigation.")
                    raise e
                await asyncio.sleep(3)

    async def smart_click_option(self, text: str) -> bool:
        """
        Finds and clicks a button/option by text, ignoring case and whitespace.
        Returns True if clicked successfully, False otherwise.
        """
        
        if not text or not text.strip():
            return False
            
        clean_text = text.strip().lower()
        
        xpath = (
            f"//*[contains(translate(normalize-space(.), "
            f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{clean_text}')]"
        )
        
        try:
            element = self.page.locator(xpath).first
            if await element.count() > 0 and await element.is_visible():
                await element.click()
                self.logger.info(f"Clicked option: {text}")
                return True
            else:
                self.logger.warning(f"Option not found: {text}")
                return False
        except Exception as e:
            self.logger.warning(f"Failed to click option '{text}': {e}")
            return False

