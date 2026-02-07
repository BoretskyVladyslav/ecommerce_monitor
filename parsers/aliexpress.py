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
            await self.close_popups()
            
            # Додаткова затримка після закриття попапів
            await asyncio.sleep(5)
            
            # Ре-перевірка на капчу після попапів
            await self.check_for_captcha()
            
            # 🔥 REGIONAL CHECK (Enforce US/USD)
            if await self.enforce_us_region():
                self.logger.info("♻️ Region enforced/Page reloaded. Re-initializing checks...")
                # Re-run waiting and cleanup for the NEW page
                await asyncio.sleep(8) 
                await self.close_popups()
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

    async def close_popups(self):
        try:
            close_selectors = [
                "button[aria-label='Close']",
                ".close-btn", 
                ".next-dialog-close",
                "div[class*='close']",
                ".pop-close-btn",
                "img[src*='close']"
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = self.page.locator(selector).first
                    if await close_btn.is_visible(timeout=1000):
                        await close_btn.click(timeout=1000)
                        await asyncio.sleep(0.5)
                        self.logger.info(f"Closed popup: {selector}")
                except:
                    pass
        except Exception as e:
            self.logger.debug(f"Popup closing attempt: {e}")

    async def enforce_us_region(self):
        """
        Перевіряє, чи активний регіон США/USD. Якщо ні - встановлює його.
        """
        try:
            # 1. Check URL & Currency Indicator
            url = self.page.url
            currency_text = await self.page.locator(".currency-symbol, [class*='currency-symbol']").first.text_content() if await self.page.locator(".currency-symbol").count() > 0 else ""
            
            needs_fix = False
            
            if "us.aliexpress.com" not in url and "www.aliexpress.com" not in url:
                if "de.aliexpress" in url or "es.aliexpress" in url or "fr.aliexpress" in url:
                    self.logger.warning(f"⚠️ Wrong regional domain detected: {url}")
                    needs_fix = True
            
            if "$" not in str(currency_text) and "USD" not in str(currency_text):
                 # Also check cleaner selector
                 self.logger.warning(f"⚠️ Wrong currency detected: {currency_text}")
                 needs_fix = True

            if not needs_fix:
                return

            self.logger.info("🛠️ Enforcing US Regional Settings...")
            
            # Use AutoWarmup logic directly (copy-paste logic for self-containment/speed)
            # 1. Open Menu
            menu_selectors = [
                 # 1. Class based (common)
                "div[class*='ship-to']", 
                ".ship-to--menuItem--WdBDsYl",
                "#switcher-info", 
                "a.switcher-info",
                # 2. Visual/Image based
                "img[src*='flags/']",                 
                "span[class*='country-flag']",        
                "div[class*='nav-global'] img[src*='flag']"
            ]
            
            menu_opened = False
            for sel in menu_selectors:
                elements = await self.page.locator(sel).all()
                for el in elements:
                    if await el.is_visible():
                        try:
                            # Try clicking the ELEMENT itself
                            await el.scroll_into_view_if_needed()
                            await el.click(timeout=1000, force=True)
                            
                            # If it's a wrapper, try clicking the FLAG/BUTTON inside it
                            try:
                                interactive_child = el.locator("button, div[role='button'], img, span[class*='country-flag'], span[class*='flag']").first
                                if await interactive_child.count() > 0:
                                     await interactive_child.click(timeout=1000, force=True)
                            except: pass

                            # Check if popup appeared
                            try:
                                popup_selectors = ".ui-dialog, .switcher-shipto-body, .switcher-common, div[class*='es--contentWrap'], div[class*='contentWrap']"
                                await self.page.wait_for_selector(popup_selectors, timeout=2000, state="visible")
                                menu_opened = True
                                break
                            except: pass
                        except: continue
                if menu_opened: break
            
            if not menu_opened:
                # Last ditch fallback: specific button from MCP
                await self.page.click("button[class*='ship-to'], .nav-global-li.ship-to, #nav-global-location", timeout=2000)
                await asyncio.sleep(2)
            
            await asyncio.sleep(1)
                
            # --- 2. Set Country (First Dropdown) ---
            dropdowns = self.page.locator("div[class*='form-item--content'] div[class*='select--text'], .switcher-shipto-c .country-selector")
            
            if await dropdowns.count() > 0:
                country_drop = dropdowns.first
                await country_drop.click()
                await asyncio.sleep(1) 
                
                # 1. Select "United States" explicitly (User Request)
                # User provided: <span> United States</span>
                try:
                    # Look for United States text in list items or spans
                    us_item = self.page.locator("div[class*='select--item']:has-text('United States'), span:has-text('United States')").first
                    
                    if await us_item.count() > 0:
                        await us_item.scroll_into_view_if_needed()
                        await us_item.click(force=True)
                        self.logger.info("   🇺🇸 Selected 'United States' (Explicit Text match).")
                    else:
                        # Fallback: The first item in the list is usually US (under "Recommend")
                        self.logger.warning("   ⚠️ 'United States' text not found. Clicking first item...")
                        first_item = self.page.locator("div[class*='select--item'], li.select-item").first
                        if await first_item.count() > 0:
                            await first_item.click(force=True)
                            self.logger.info("   🇺🇸 Selected Top Item (Likely US).")
                        else:
                            self.logger.error("   ❌ List is empty!")
                except Exception as list_err:
                    self.logger.error(f"   ❌ Selection failed: {list_err}")
            
            await asyncio.sleep(1)

            # --- 3. Save ---
            # Dynamic selector: looks for 'save' in class names (Language Agnostic)
            save_btn_sel = (
                "div[class*='saveBtn' i], "      # Matches es--saveBtn, saveBtn, etc.
                "button[class*='save' i], "      # Matches button.save-btn
                "div[class*='save-btn' i], "
                ".switcher-save-btn, "
                "div[role='button'][class*='save' i]"
            )
            save_btn = self.page.locator(save_btn_sel).first
            
            if await save_btn.count() > 0:
                try:
                    await save_btn.scroll_into_view_if_needed()
                    await save_btn.click(force=True)
                except:
                    # Fallback: specific JS click if overlay issues
                    await self.page.evaluate("(btn) => btn.click()", await save_btn.element_handle())
                    
                self.logger.info("   💾 Settings Saved. Waiting for auto-reload...")
                await asyncio.sleep(5) 
                
                return True # Signal that we changed region/page
            else:
                self.logger.warning("   ⚠️ Save button not found")

        except Exception as e:
            self.logger.warning(f"Regional enforcement error: {e}")
        
        return False

