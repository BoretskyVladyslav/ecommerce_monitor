from parsers.base import BaseParser
from parsers.exceptions import SoftBanException, HardBanException
import asyncio

class SheinParser(BaseParser):
    # BAN_TRIGGERS removed - using CaptchaDetector in BaseParser

    async def check_for_ban(self):
        """
        Alias for check_for_captcha (for backward compatibility).
        """
        await self.check_for_captcha()
    
    async def close_popups(self):
        """
        Closes mobile popups and banners on Shein.
        """
        popup_selectors = [
            "i.iconfont-close",
            "button[aria-label='Close']",
            "div.she-close",
            "text='NO THANKS'",
            "text='Continue to mobile site'",
            "text='Maybe Later'",
            ".popup-close",
            ".modal-close"
        ]
        
        for selector in popup_selectors:
            try:
                if selector.startswith("text="):
                    text_content = selector.replace("text=", "").strip("'\"")
                    locator = self.page.locator(f"text='{text_content}'")
                else:
                    locator = self.page.locator(selector)
                
                # Try to click if visible (short timeout)
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=1000)
                    self.logger.info(f"✅ Closed popup: {selector}")
                    await asyncio.sleep(0.5)
            except:
                continue
    
    async def parse(self):
        """
        Parses Shein mobile page for availability.
        Includes ban detection and popup handling.
        """
        try:
            self.logger.info("SHEIN PARSER LOADED V3 (Click-Fix)")
            
            # Step 1: Check for ban/captcha FIRST (Shein-specific)
            await self.check_for_ban()
            
            # Step 1.1: Check for generic captchas (from BaseParser)
            await self.check_for_captcha()
            
            # Step 1.5: Check if redirected to /risk/challenge
            current_url = self.page.url
            if "/risk/challenge" in current_url:
                self.logger.warning(f"🚫 Shein Risk Challenge detected: {current_url}")
                # Don't fail immediately - try to solve it first!
                self.logger.info("⚔️ Attempting to solve Risk Challenge...")
                
                # Explicitly wait for the captcha container to load
                try:
                    self.logger.info("⏳ Waiting 10s for captcha logic to load...")
                    await asyncio.sleep(10)
                    # Force check immediately
                    await self.check_for_captcha()
                except Exception as e:
                    self.logger.warning(f"Error in risk logic: {e}")
            
            # Step 2: Close any popups
            await self.close_popups()
            
            # Step 2.5: Re-check for captchas after popup closing
            await self.check_for_captcha()
            
            # Step 3: Wait for content to load
            await asyncio.sleep(1)
            
            # Step 4: Check for "Sold Out" and Error Pages
            sold_out_selectors = [
                "text='OOPS...'",  # Product removed/unavailable error page
                "text='Sold Out'",
                "text='SOLD OUT'",
                ".goods-sold-out",
                ".product-intro__sold-out"
            ]
            
            for selector in sold_out_selectors:
                try:
                    if selector.startswith("text="):
                        text_content = selector.replace("text=", "").strip("'\"")
                        locator = self.page.locator(f"text='{text_content}'")
                    else:
                        locator = self.page.locator(selector)
                    
                    if await locator.is_visible(timeout=1000):
                        self.logger.info("Shein: Product is Sold Out.")
                        return 0
                except:
                    continue
            
            # Step 5: Check for "Add to Cart" / "Add to Bag" button
            add_to_bag_selectors = [
                "button:has-text('ADD TO CART')",
                "button:has-text('Add to Cart')",
                "button:has-text('Add to Bag')",
                "button:has-text('ADD TO BAG')",
                ".bottom-action__btn",
                ".add-to-bag",
                ".she-btn-black",
                "[class*='add-to-cart']"
            ]
            
            for selector in add_to_bag_selectors:
                try:
                    locator = self.page.locator(selector)
                    if await locator.is_visible(timeout=1000):
                        # Check if disabled
                        is_disabled = await locator.get_attribute("disabled")
                        if is_disabled is not None:
                            self.logger.info("Shein: 'Add to Bag' button is disabled.")
                            return 0
                        
                        self.logger.info("Shein: Product is In Stock.")
                        return 1
                except:
                    continue
            
            # No clear indicators found
            self.logger.info("Shein: No status indicators found. Assuming OOS or Error.")
            return 0

        except SoftBanException:
            # Re-raise to trigger proxy rotation
            raise
        except Exception as e:
            self.logger.error(f"Error parsing Shein: {e}")
            raise e
