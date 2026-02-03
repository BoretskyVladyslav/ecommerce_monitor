from parsers.base import BaseParser
import asyncio

class AmazonParser(BaseParser):
    async def parse(self):
        """
        Parses Amazon page for availability and price.
        Returns:
            status (int): 1 if In Stock, 0 if Out of Stock
            data (dict): Additional data like price (optional)
        """
        try:
            # 1. Check for Captcha / Soft Ban
            await self.check_for_captcha()

            # 2. Check Availability
            # Amazon "Currently unavailable" selector
            unavailable_text = self.page.locator("#availability span:has-text('Currently unavailable')")
            if await unavailable_text.is_visible():
                self.logger.info("Amazon: Product is currently unavailable.")
                return 0

            # 3. Check "Add to Cart" or "Buy Now" button
            add_to_cart = self.page.locator("#add-to-cart-button")
            buy_now = self.page.locator("#buy-now-button")
            
            if await add_to_cart.is_visible() or await buy_now.is_visible():
                self.logger.info("Amazon: Product is In Stock.")
                return 1
            
            # 4. Check Price (sometimes available but no buy button?)
            # Usually if no buy button, it's OOS or 3rd party. 
            # Sticking to simple logic: No Buy Button = OOS for us.
            
            self.logger.info("Amazon: No 'Add to Cart' button found. Assuming OOS.")
            return 0

        except Exception as e:
            self.logger.error(f"Error parsing Amazon: {e}")
            raise e
