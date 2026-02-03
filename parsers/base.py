from abc import ABC
from playwright.async_api import Page
import asyncio
from config.logger import setup_logger
from parsers.exceptions import SoftBanException, HardBanException

class BaseParser(ABC):
    def __init__(self, page: Page):
        self.page = page
        self.logger = setup_logger(self.__class__.__name__)

    async def check_for_captcha(self):
        """
        Scenario B: Error Handling
        Checks for typical captcha/block indicators across all platforms.
        Raises SoftBanException for recoverable captchas.
        Raises HardBanException for critical blocks.
        """
        # Comprehensive captcha/ban indicators
        indicators = {
            # Generic captchas
            "text='Enter the characters you see below'": "SoftBan",  # Amazon
            "text='Verify you are human'": "SoftBan",                # Cloudflare
            "text='Please verify'": "SoftBan",
            "text='Security verification'": "SoftBan",
            "text='Security check'": "SoftBan",
            "text='Unusual activity'": "SoftBan",
            
            # Shein specific
            "text='Slide to verify'": "SoftBan",
            "text='Verify to continue'": "SoftBan",
            "#captcha": "SoftBan",
            "iframe[src*='captcha']": "SoftBan",
            "div[class*='captcha']": "SoftBan",
            
            # Temu specific
            ".security-verify": "SoftBan",
            "text='Drag the slider'": "SoftBan",
            "div[class*='slider-verify']": "SoftBan",
            
            # AliExpress specific
            "text='Click to verify'": "SoftBan",
            "#nc_1__scale_text": "SoftBan",  # AliExpress slider
            
            # Hard bans
            "text='Access Denied'": "HardBan",
            "text='banned'": "HardBan",
            "text='Your account has been suspended'": "HardBan",
            "text='403 Forbidden'": "HardBan",
        }

        for selector, ban_type in indicators.items():
            try:
                is_visible = await self.page.locator(selector).is_visible(timeout=1000)
                if is_visible:
                    if ban_type == "SoftBan":
                        self.logger.warning(f"🚫 Captcha detected: {selector}")
                        raise SoftBanException(f"Captcha: {selector}")
                    
                    elif ban_type == "HardBan":
                        self.logger.error(f"❌ Hard Ban detected: {selector}")
                        raise HardBanException(f"Access Denied: {selector}")
            except Exception as e:
                # Якщо помилка не від нашого raise - ігноруємо
                if isinstance(e, (SoftBanException, HardBanException)):
                    raise
                # Інші помилки (timeout тощо) - пропускаємо
                continue


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

