from parsers.base import BaseParser
import asyncio

class AliExpressParser(BaseParser):
    async def parse(self):
        """
        Parses AliExpress page for availability.
        """
        try:
            # AliExpress має багато lazy loading та динамічного контенту
            # Даємо час на повне завантаження
            self.logger.info("AliExpress: Waiting for page to fully load...")
            await asyncio.sleep(8)  # Базова затримка для завантаження
            
            # Перевірка на капчу після початкового завантаження
            await self.check_for_captcha()
            
            # Спроба закрити попапи/модалки
            try:
                close_selectors = [
                    "button[aria-label='Close']",
                    ".close-btn", 
                    ".next-dialog-close",
                    "div[class*='close']"
                ]
                
                for selector in close_selectors:
                    try:
                        close_btn = self.page.locator(selector).first
                        if await close_btn.is_visible(timeout=2000):
                            await close_btn.click(timeout=2000)
                            await asyncio.sleep(1)
                            self.logger.info(f"Closed popup: {selector}")
                    except:
                        pass
            except Exception as e:
                self.logger.debug(f"Popup closing attempt: {e}")
            
            # Додаткова затримка після закриття попапів
            await asyncio.sleep(5)
            
            # Ре-перевірка на капчу після попапів
            await self.check_for_captcha()
            
            # Common text indicators
            # "Sorry, this item is no longer available!"
            if await self.page.locator("text='no longer available'").is_visible(timeout=3000):
                 self.logger.info("AliExpress: Item no longer available.")
                 return 0
            
            # "Cannot ship to..." might be treated as OOS for us if we care about shipping location,
            # but usually we just want to know if it's generally in stock.

            # Check for Cart/Buy buttons
            # Selectors vary remarkably. Text search is safest.
            add_to_cart = self.page.locator("button:has-text('Add to Cart')")
            buy_now = self.page.locator("button:has-text('Buy Now')")
            
            # Sometimes they use "Add to cart" (lowercase c)
            # convert to case insensitive search using xpath in base if needed, 
            # or just multiple locators.
            
            if await add_to_cart.is_visible() or await buy_now.is_visible():
                self.logger.info("AliExpress: Product is In Stock.")
                return 1

            # Specific "Sold Out" badge
            # often class "sku-item-soldout" or text "Sold Out"
            if await self.page.locator("text='Sold Out'").is_visible():
                self.logger.info("AliExpress: Product is Sold Out.")
                return 0

            # Fallback
            # If we don't see buttons but also don't see "Sold Out", it might be a page structure change or 
            # region lock. 
            self.logger.info("AliExpress: No clear status. Assuming OOS/Error.")
            return 0

        except Exception as e:
            self.logger.error(f"Error parsing AliExpress: {e}")
            raise e
