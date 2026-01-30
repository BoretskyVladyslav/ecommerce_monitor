from parsers.base import BaseParser
from parsers.exceptions import SoftBanException, ProductNotFoundException
import asyncio
from typing import Dict, Any

class TemuParser(BaseParser):
    async def _close_popups(self):
        """Aggressive Temu popup closer."""
        try:
            selectors = [
                "div[data-action='close']",
                "div[role='button'][aria-label='Close']",
                "img[alt='close']",
                ".c-icon-close",
                "div[class*='close']"
            ]
            for sel in selectors:
                if await self.page.locator(sel).count() > 0:
                    try:
                        await self.page.locator(sel).first.click()
                        await asyncio.sleep(0.5)
                    except:
                        pass
        except:
            pass

    async def parse_product(self, item: Dict[str, Any]) -> int:
        """
        Parse product with two-step option selection.
        Returns: 1 (Active) or 0 (Sold Out)
        """
        url = item.get('url')
        opt1 = item.get('option_name_1')
        opt2 = item.get('option_name_2')

        await self.Maps(url)

        if "verify" in (await self.page.title()).lower():
            raise SoftBanException("Temu Verification detected")
            
        await self._close_popups()

        if opt1:
            await self.smart_click_option(opt1)
            await asyncio.sleep(1)  
            await self._close_popups()
            
        if opt2:
            await self.smart_click_option(opt2)
            await asyncio.sleep(0.5)
            await self._close_popups()

        is_available = False
        
        add_btn = self.page.locator("button:has-text('Add to Cart'), button:has-text('Add to cart')")
        
        if await add_btn.count() > 0:
            if await add_btn.first.is_enabled():
                is_available = True

        if await self.page.locator("text=Sold Out").count() > 0:
            is_available = False
            
        return 1 if is_available else 0

class AliexpressParser(BaseParser):
    async def _close_popups(self):
        """Attempts to close common AliExpress popups (Welcome banners etc)."""
        try:
            selectors = [
                ".pop-close-btn", 
                ".rax-close", 
                ".next-dialog-close",
                "img.close-layer",
                "div[data-role='dialog-close']",
                ".ui-window-close",
                ".close-btn",
                "a.close-layer"
            ]
            for sel in selectors:
                if await self.page.locator(sel).count() > 0:
                    if await self.page.locator(sel).first.is_visible():
                        try:
                            await self.page.locator(sel).first.click()
                            self.logger.info(f"Closed popup: {sel}")
                            await asyncio.sleep(0.2)
                        except:
                            pass
        except:
            pass
            
    async def parse_product(self, item: Dict[str, Any]) -> int:
        """
        Parse product with two-step option selection.
        Returns: 1 (Active) or 0 (Sold Out)
        """
        url = item.get('url')
        opt1 = item.get('option_name_1')
        opt2 = item.get('option_name_2')

        await self.Maps(url)

        title = await self.page.title()
        if "security" in title.lower() or "slide" in title.lower():
            raise SoftBanException("AliExpress Security Check")
            
        await self._close_popups()

        if opt1:
            await self.smart_click_option(opt1)
            await asyncio.sleep(1)  
            await self._close_popups()
            
        if opt2:
            await self.smart_click_option(opt2)
            await asyncio.sleep(0.5)
            await self._close_popups()

        is_available = True

        if await self.page.locator("text=Sold Out").count() > 0:
             is_available = False

        buy_btns = self.page.locator("button:has-text('Add to Cart'), button:has-text('Buy Now')")
        if await buy_btns.count() == 0:
            is_available = False

        return 1 if is_available else 0

class SheinParser(BaseParser):
    async def parse_product(self, item: Dict[str, Any]) -> int:
        """
        Parse product with two-step option selection.
        Returns: 1 (Active) or 0 (Sold Out)
        """
        url = item.get('url')
        opt1 = item.get('option_name_1')
        opt2 = item.get('option_name_2')

        await self.Maps(url)

        if "security check" in (await self.page.title()).lower():
            raise SoftBanException("Shein Security Check detected")

        if opt1:
            await self.smart_click_option(opt1)
            await asyncio.sleep(1)  
            
        if opt2:
            await self.smart_click_option(opt2)
            await asyncio.sleep(0.5)

        is_available = False
        
        add_btn = self.page.locator("button:has-text('Add to Bag'), button:has-text('Add to Cart')")
        
        if await add_btn.count() > 0:
             if await add_btn.first.is_enabled():
                 is_available = True

        if await self.page.locator("text=Sold Out").count() > 0:
            is_available = False
            
        return 1 if is_available else 0
