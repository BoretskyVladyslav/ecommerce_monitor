from parsers.base import BaseParser
from parsers.exceptions import SoftBanException, ProductNotFoundException
import asyncio
from typing import Dict, Any

class AmazonParser(BaseParser):
    async def parse_product(self, item: Dict[str, Any]) -> int:
        """
        Parse Amazon product. Ignores options - just checks availability.
        Returns: 1 (Active) or 0 (Sold Out)
        """
        url = item.get('url')

        await self.Maps(url)

        try:
            title = await self.page.title()
            content = await self.page.content()
        except Exception:
            
            await asyncio.sleep(1)
            title = await self.page.title()
            content = await self.page.content()
        
        if "robot check" in title.lower() or "enter the characters you see below" in content.lower():
            raise SoftBanException("Amazon Captcha detected")

        if await self.page.locator("img[alt*='dogs of Amazon']").count() > 0:
            return 0  

        is_available = True
        
        try:
             await self.page.wait_for_selector(
                 "#availability, #outOfStock, #priceblock_ourprice, .a-price, #corePriceDisplay_desktop_feature_div", 
                 timeout=5000
             )
        except:
            pass

        if await self.page.locator("#availability, #outOfStock").count() > 0:
            text = await self.page.locator("#availability, #outOfStock").first.inner_text()
            text = text.lower()
            if "currently unavailable" in text or "out of stock" in text or "unavailable" in text:
                is_available = False
        
        return 1 if is_available else 0
