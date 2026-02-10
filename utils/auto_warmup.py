"""
Auto Warmup Module
Автоматично запускає warmup для платформ коли потрібно пройти капчу.
Має захист від нескінченних циклів та повну логіку браузерної автоматизації.
Інтегровано з CaptchaDetector та CaptchaSolver для автоматичного вирішення.
"""
import asyncio
import time
import json
import os
import random
from pathlib import Path
from playwright.async_api import async_playwright, Page
from config.logger import setup_logger
from config.settings import settings
from utils.proxy_manager import ProxyManager
from utils.captcha_detector import captcha_detector, CaptchaInfo, CaptchaType
from utils.captcha_solver import captcha_solver, CaptchaSolution
from utils.slider_solver import slider_solver

logger = setup_logger("AutoWarmup")
print("✅ AutoWarmup Module Loaded with Setup Logger")

class AutoWarmup:
    """
    Автоматичний warmup при виявленні капчі.
    Містить повну логіку warmup з автоматичним вирішенням капчі.
    """
    
    # Файл для збереження історії warmup
    WARMUP_HISTORY_FILE = "warmup_history.json"
    
    # Ліміти (щоб не warmup-ити постійно)
    MAX_WARMUPS_PER_HOUR = 3          # Максимум 3 warmup на годину (збільшено для тестів)
    MIN_TIME_BETWEEN_WARMUPS = 600    # Мінімум 10 хвилин між warmup (зменшено)
    
    # Warmup URLs
    # Warmup URLs - SIMPLIFIED (Homepage only for Random Walker)
    WARMUP_URLS = {
        'shein': {
            'target': "https://us.shein.com/",
            'cookie_file': "shein_session_state.json",
            'proxy_file': "shein_session_proxy.json",
            # We don't need entry_points anymore, we will find them dynamically
        },
        'aliexpress': {
            'target': "https://www.aliexpress.com/",
            'cookie_file': "aliexpress_session_state.json",
            'proxy_file': "aliexpress_session_proxy.json",
        }
    }
    
    def __init__(self):
        self.history = self._load_history()
        self.proxy_manager = ProxyManager()
        logger.info(f"✅ ProxyManager loaded {self.proxy_manager.proxy_count} proxies")
    
    def _load_history(self):
        """Завантажує історію warmup з файлу"""
        try:
            if os.path.exists(self.WARMUP_HISTORY_FILE):
                with open(self.WARMUP_HISTORY_FILE, 'r') as f:
                    return json.load(f)
            return {}
        except:
            return {}
    
    def _save_history(self):
        """Зберігає історію warmup у файл"""
        try:
            with open(self.WARMUP_HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save warmup history: {e}")
    
    def can_warmup(self, marketplace):
        """Перевіряє чи можна warmup для платформи"""
        now = time.time()
        
        if marketplace not in self.history:
            return True
        
        last_warmup_time = self.history[marketplace].get('last_warmup', 0)
        time_since_last = now - last_warmup_time
        
        if time_since_last < self.MIN_TIME_BETWEEN_WARMUPS:
            remaining = self.MIN_TIME_BETWEEN_WARMUPS - time_since_last
            logger.warning(f"⏳ {marketplace}: Too soon. Wait {remaining/60:.0f} min.")
            return False
        
        one_hour_ago = now - 3600
        warmups_last_hour = self.history[marketplace].get('warmups_last_hour', [])
        warmups_last_hour = [t for t in warmups_last_hour if t > one_hour_ago]
        
        if len(warmups_last_hour) >= self.MAX_WARMUPS_PER_HOUR:
            logger.warning(f"🚫 {marketplace}: Limit reached ({self.MAX_WARMUPS_PER_HOUR}/hour).")
            return False
        
        return True
    
    def record_warmup(self, marketplace):
        """Записує warmup в історію"""
        now = time.time()
        
        if marketplace not in self.history:
            self.history[marketplace] = {
                'last_warmup': now,
                'warmups_last_hour': [now],
                'total_warmups': 1
            }
        else:
            self.history[marketplace]['last_warmup'] = now
            one_hour_ago = now - 3600
            warmups = self.history[marketplace].get('warmups_last_hour', [])
            warmups = [t for t in warmups if t > one_hour_ago]
            warmups.append(now)
            self.history[marketplace]['warmups_last_hour'] = warmups
            self.history[marketplace]['total_warmups'] = \
                self.history[marketplace].get('total_warmups', 0) + 1
        
        self._save_history()

    async def set_regional_settings(self, page: Page, marketplace: str):
        """
        Sets regional settings (Ship to US, English, USD) for proper warmup.
        Implementation based on User's Technical Task.
        """
        if marketplace != "aliexpress":
            return

        logger.info("🌍 Setting Regional Settings: US/EN/USD...")
        
        try:
            # 1. Open Menu (Flag/Settings)
            # Selectors for the top bar entry point - LANGUAGE AGNOSTIC
            entry_selectors = [
                 # 1. Class based (common)
                "div[class*='ship-to']", 
                "#switcher-info", 
                "a.switcher-info",
                
                # 2. Visual/Image based (The Flag is universal)
                "img[src*='flags/']",                 # Standard flag image
                "span[class*='country-flag']",        # CSS flag span
                "div[class*='nav-global'] img[src*='flag']", # Flag inside nav
                
                # 3. Fallback to English text only as last resort
                "text=Ship to" 
            ]
            
            menu_opened = False
            for sel in entry_selectors:
                elements = await page.locator(sel).all()
                # filter visible only
                for el in elements:
                    if await el.is_visible():
                        try:
                            logger.info(f"   👆 Possible settings menu found: {sel}")
                            # Scroll into view if needed
                            await el.scroll_into_view_if_needed()
                            
                            # Try clicking the ELEMENT itself
                            try:
                                await el.scroll_into_view_if_needed()
                                await el.click(timeout=2000, force=True)
                            except: pass

                            # If it's a wrapper, try clicking the FLAG or BUTTON inside it
                            try:
                                # Prioritize explicit interactive elements inside the found wrapper
                                interactive_child = el.locator("button, div[role='button'], img, span[class*='country-flag'], span[class*='flag']").first
                                if await interactive_child.count() > 0:
                                     await interactive_child.click(timeout=1000, force=True)
                            except: pass
                            
                            # Check if popup appeared
                            try:
                                # Updated selectors based on MCP findings (es--contentWrap)
                                popup_selectors = ".ui-dialog, .switcher-shipto-body, .switcher-common, div[class*='es--contentWrap'], div[class*='contentWrap']"
                                await page.wait_for_selector(popup_selectors, timeout=5000, state="visible")
                                logger.info("   ✅ Settings popup opened")
                                menu_opened = True
                                break
                            except:
                                logger.warning("   ⚠️ Clicked but popup didn't appear (Timeout). Trying next...")
                        except: continue
                if menu_opened: break
            
            if not menu_opened:
                logger.warning("⚠️ Could not open regional settings menu (Entry point not found). Skipping.")
                return
            
            # --- STRATEGY FOR MODERN UI (React/Dynamic) ---
            # The UI can have variable number of dropdowns (Country, State, City, Language, Currency).
            # HEURISTIC: Country is FIRST. Currency is LAST. Language is SECOND TO LAST.
            
            # 1. Detect Standard vs Modern UI
            dropdowns = page.locator("div[class*='form-item--content'] div[class*='select--text'], .switcher-shipto-c .country-selector, .switcher-common .country-selector")
            
            # --- 2. Set Country (First Dropdown) ---
            country_drop = dropdowns.first
            if await country_drop.count() > 0:
                logger.info("   🗺️ Opening Country Dropdown (Index 0)...")
                await country_drop.click()
                await asyncio.sleep(1) 
                
                # 1. Select "United States" explicitly (User Request)
                try:
                    # # Look for United States text in list items or spans (User provided snippet: <span> United States</span>)
                    # us_item = page.locator("div[class*='select--item']:has-text('United States'), span:has-text('United States')").first
                    
                    
                    us_item = country_drop.locator("div[class*='select--item'], li.select-item").first


                    if await us_item.count() > 0:
                         await us_item.scroll_into_view_if_needed()
                         await us_item.click(force=True)
                         logger.info("   🇺🇸 Selected 'United States' (Explicit Text match).")
                    else:
                         # Fallback to first item
                         logger.warning("   ⚠️ 'United States' text not found. Clicking first item...")
                         first_item = page.locator("div[class*='select--item'], li.select-item").first
                         if await first_item.count() > 0:
                             await first_item.click(force=True)
                             logger.info("   🇺🇸 Selected Top Item (Likely US).")
                         else:
                             logger.error("   ❌ List is empty!")
                except Exception as list_err:
                     logger.error(f"   ❌ Selection failed: {list_err}")
            
            await asyncio.sleep(0.5)

            # Check for generic "Save" button to close intermediate dialogs if any
            # (Sometimes selecting country opens a confirmation)

            # --- 3. Set Currency (Last Dropdown) ---
            dropdowns = page.locator("div[class*='form-item--content'] div[class*='select--text'], .switcher-currency-c .currency-selector")
            count = await dropdowns.count()
            
            if count > 1:
                # Last one is usually Currency
                curr_drop = dropdowns.last
                logger.info("   💲 Opening Currency Dropdown (Last)...")
                await curr_drop.click()
                await asyncio.sleep(1)
                
                # Try selecting USD
                usd_sel = "div[class*='select--item']:has-text('USD'), div[class*='select--item']:has-text('US Dollar'), a[data-currency='USD']"
                if await page.locator(usd_sel).count() > 0:
                    await page.locator(usd_sel).first.click()
                    logger.info("   ✅ Selected USD")
                else:
                    logger.warning("   ⚠️ USD Option not found")
                
                await asyncio.sleep(0.5)

            # --- 4. Set Language (Second to Last if > 2, else maybe included in others?) ---
            # If we only have Country and Currency, Language might be missing or merged.
            # Usually strict order: Country ... Language, Currency.
            # CRITICAL: Changing country updates the form (removes/adds fields). Re-fetch dropdowns.
            await asyncio.sleep(2) 
            dropdowns = page.locator("div[class*='form-item--content'] div[class*='select--text'], .switcher-shipto-c .country-selector, .switcher-common .country-selector")
            count = await dropdowns.count() # Re-fetch count after re-fetching dropdowns
            
            # --- LANGUAGE (Index: Second to Last) ---
            # Heuristic: Format is usually [Country, (State), (City), Language, Currency]
            # So Language is almost always the one before Currency (Last).
            # Using nth(-2) is safer than nth(1).
            lang_index = count - 2
            if lang_index > 0:
                lang_drop = dropdowns.nth(lang_index)
                if await lang_drop.count() > 0:
                    logger.info(f"   🗣️ Opening Language Dropdown (Index {lang_index})...")
                    await lang_drop.click()
                await asyncio.sleep(1)
                
                eng_sel = "div[class*='select--item']:has-text('English'), a[data-locale='en_US']"
                if await page.locator(eng_sel).count() > 0:
                     await page.locator(eng_sel).first.click()
                     logger.info("   ✅ Selected English")
                else:
                    logger.warning("   ⚠️ English Option not found")
                await asyncio.sleep(0.5)

            # 3. Save
            # Dynamic selector: looks for 'save' in class names (Language Agnostic)
            save_btn_sel = (
                "div[class*='saveBtn' i], "      # Matches es--saveBtn, saveBtn, etc.
                "button[class*='save' i], "      # Matches button.save-btn
                "div[class*='save-btn' i], "
                ".switcher-save-btn, "
                "div[role='button'][class*='save' i]"
            )
            save_btn = page.locator(save_btn_sel).first
            
            if await save_btn.count() > 0:
                try:
                    await save_btn.scroll_into_view_if_needed()
                    await save_btn.click(force=True)
                except:
                    # Fallback
                    await page.evaluate("(btn) => btn.click()", await save_btn.element_handle())
                    
                logger.info("   💾 Settings Saved. Waiting for auto-reload...")
                await asyncio.sleep(5) # Wait for page reload to complete
            else:
                logger.warning("   ⚠️ Save button not found")



        except Exception as e:
            logger.error(f"❌ Error setting regional settings: {e}")



    async def close_popups(self, page: Page, marketplace: str):
        """
        Closes known marketing popups (Shein coupons, etc).
        """
        if marketplace.lower() != 'shein':
            return

        try:
            # --- 1. HANDLE COOKIES (High Priority) ---
            # The modal in your screenshot: "Aceptar Todo" / "Accept All"
            cookie_selectors = [
                "button:has-text('Aceptar Todo')",  # Spanish (from your screenshot)
                "button:has-text('Accept All')",    # English
                "button:has-text('Agree')",
                "#onetrust-accept-btn-handler",     # Common ID for OneTrust banners
                ".onetrust-accept-btn-handler"
            ]
            
            for sel in cookie_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        logger.info(f"   🍪 Accepting Cookies: {sel}")
                        await btn.click()
                        await asyncio.sleep(1)
                        break # Found and clicked, stop looking for cookies
                except: pass

            # --- 2. HANDLE MARKETING POPUPS (Existing logic) ---
            close_selectors = [
                # NEW: Special Deals / Collect All Popup
                "div.wrapper-close",       # Often cross on banners
                "i.iconfont-close",        # Standard Shein cross
                "button.close-btn",
                
                # Text-based (if cross not found)
                "text=No thanks",
                "text=Not now",
                
                # New MCP findings
                ".dialog-header-v2__close-btn", 
                ".popup-dialog-couponPackage .close-btn",
                
                # Standard findings
                ".c-coupon-box .iconfont-close",
                ".she-modal .iconfont-close",
                "div[class*='close-btn']",
                "[aria-label='Close']"
            ]
            
            for sel in close_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        logger.info(f"   ❎ Closing popup: {sel}")
                        await btn.click()
                        await asyncio.sleep(1)
                except: pass
                
        except Exception as e:
            logger.warning(f"Error closing popups: {e}")

    async def check_and_solve_captcha(self, page: Page, marketplace: str, context: str = "unknown") -> bool:

        """
        Перевіряє наявність капчі та намагається її вирішити (Retry Loop).
        
        Args:
            context: Контекст перевірки - "entry" (блокуюча) або "browsing" (rate-limit)
        """
        max_attempts = 5
        
        # 1. Швидка перевірка (без скріншота)
        # Exception: Shein 'risk/challenge' URL is ALWAYS a captcha
        is_risk_url = 'shein' in marketplace.lower() and ('/risk/' in page.url or '/challenge/' in page.url)
        
        if not is_risk_url and not await captcha_detector.quick_check(page, marketplace):
            return True
        
        
        settings.HEADLESS = False # Force visible for debug if needed
        logger.warning(f"🛑 CAPTCHA DETECTED ({context})! Enabling images for solving...")
        
        
        # 🔥 DYNAMIC IMAGE TOGGLE (User Request)
        # Enable images for this page to allow captcha to render
        try:
            page.image_blocking_enabled = False
            logger.info("   🖼️ Images temporarily ENABLED for captcha")
            
            # Даємо час капчі завантажитися без reload (reload викликає більше капч!)
            await asyncio.sleep(3)
            
        except Exception as e:
            logger.warning(f"Error toggling images/reload: {e}")

        if marketplace.lower() == 'aliexpress':
            logger.warning("🚫 Captcha solving disabled for AliExpress (per user request). Skipping.")
            return False

        
        for attempt in range(max_attempts):
            logger.info(f"🧩 Warmup Captcha Auto-Solve Attempt {attempt + 1}/{max_attempts}")
            
            try:
                # 2. Детальна детекція зі скріншотом (кожного разу нова!)
                captcha_info = await captcha_detector.detect(page, marketplace, take_screenshot=True)
                
                if not captcha_info.detected:
                    logger.info("✅ False alarm (captcha disappeared)")
                    return True # Success
                
                logger.info(f"🧩 Solving captcha type: {captcha_info.captcha_type}")
                
                 # 3. Вирішуємо через API
                solution = await captcha_solver.solve(
                    captcha_type=captcha_info.captcha_type,
                    image_path=captcha_info.screenshot_path,
                    additional_params={"page_url": page.url}
                )
                
                if not solution.solved:
                    # Безпечна перевірка атрибуту error
                    error_msg = getattr(solution, 'error', 'Unknown error')
                    
                    if "UNSOLVABLE" in str(error_msg) or "unsolvable" in str(error_msg):
                         logger.warning("⚠️ API Error: UNSOLVABLE. Retrying with fresh screenshot...")
                         await asyncio.sleep(2)
                         continue
                    
                    logger.error(f"❌ Failed to solve captcha via API: {error_msg}")
                    await asyncio.sleep(2)
                    continue
                
                # 4. Застосовуємо рішення via Helper (Ported from BaseParser logic would be ideal, but inline is fine)
                logger.info(f"🛠️ Applying solution: Type={solution.solution_type}")
                
                if solution.solution_type == "coordinates":
                    # Це SLIDER або CLICK_POINTS
                    points = solution.data
                    if not points:
                        logger.error("❌ No coordinates provided for solution.")
                        await asyncio.sleep(2)
                        continue
                        
                    if captcha_info.captcha_type == CaptchaType.SLIDER:
                        # Це Слайдер. Потрібно знайти кнопку (knob).
                        # Спробуємо знайти кнопку слайдера, якщо detected element це контейнер
                        slider_btn = captcha_info.element_handle
                        
                        # Евристика: якщо елемент завеликий (>100px width), це трек, шукаємо кнопку всередині
                        box = await slider_btn.bounding_box()
                        if box and box['width'] > 100:
                            logger.info("🔎 Detected element seems to be a track. Searching for knob...")
                            # Спроба знайти стандарні кнопки
                            for btn_selector in [".btn_slide", ".slider-btn", "#nc_1_n1z", ".geetest_slider_button"]:
                                btn = await page.query_selector(btn_selector)
                                if btn:
                                    slider_btn = btn
                                    logger.info(f"✅ Found knob: {btn_selector}")
                                    break
                        
                        # Отримуємо X offset з першої точки
                        x_offset = int(points[0]['x'])
                        logger.info(f"🎢 Sliding to offset: {x_offset}")
                        
                        if await slider_solver.slide(page, slider_btn, x_offset):
                             logger.info("✅ Slide action executed")
                        else:
                             logger.error("❌ Failed to execute slide")
                             await asyncio.sleep(2)
                             continue
                            
                    else:
                        # Це Click Points (просто клікаємо по точках)
                        logger.info(f"📍 Clicking {len(points)} points...")
                        
                        # Якщо є елемент контейнера, координати відносні. Якщо ні - абсолютні?
                        # API CapMonster зазвичай повертає координати відносно зображення.
                        # Потрібно знайти координати зображення на сторінці.
                        
                        img_box = None
                        if captcha_info.element_handle:
                            img_box = await captcha_info.element_handle.bounding_box()
                        
                        for point in points:
                            x = point['x']
                            y = point['y']
                            
                            if img_box:
                                x += img_box['x']
                                y += img_box['y']
                                
                            await page.mouse.click(x, y)
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                
                # 4. ПІДТВЕРДЖЕННЯ (CONFIRM)
                    # На Shein кнопка Confirm часто з'являється після кліків
                    await asyncio.sleep(0.5)
                    
                    # Розширений пошук кнопки Confirm
                    selectors = [
                        "div[aria-label='Confirm']", 
                        ".geetest_commit_tip", 
                        ".geetest_commit", 
                        ".geetest_submit",
                        "text=Confirm",
                        "text=confirm",
                        "text=OK"
                    ]
                    
                    confirm_btn = None
                    
                    # 1. Шукаємо в контексті елемента (якщо це контейнер)
                    if captcha_info.element_handle:
                        try:
                            confirm_btn = await captcha_info.element_handle.query_selector("text=Confirm")
                            if not confirm_btn:
                                confirm_btn = await captcha_info.element_handle.query_selector(".geetest_commit")
                        except: pass
                    
                    # 2. Шукаємо на сторінці
                    if not confirm_btn:
                        for sel in selectors:
                            try:
                                confirm_btn = await page.query_selector(sel)
                                if confirm_btn and await confirm_btn.is_visible():
                                    break
                                confirm_btn = None
                            except: continue

                    # 3. Шукаємо у фреймах (якщо на сторінці нема)
                    if not confirm_btn:
                        for frame in page.frames:
                            for sel in selectors:
                                try:
                                    # remove text= prefix for frame locator if needed, but query_selector supports it
                                    btn = await frame.query_selector(sel)
                                    if btn:
                                        confirm_btn = btn
                                        break
                                except: continue
                            if confirm_btn: break
                    
                    if confirm_btn:
                        logger.info("✅ Found Confirm button, clicking...")
                        await confirm_btn.click()
                        await asyncio.sleep(3) # Wait for submission
                    else:
                        logger.warning("⚠️ Confirm button not found (auto-submitted?)")

                elif solution.solution_type == "token":
                    # GEETEST, FUNCAPTCHA, RECAPTCHA
                    data = solution.data
                    logger.info(f"🔑 Injecting token...")
                    
                    if captcha_info.captcha_type == CaptchaType.GEETEST:
                        # GeeTest v3 validate injection (приклад)
                        await page.evaluate(f"""
                            window.geetest_challenge = '{data.get("challenge", "")}';
                            window.geetest_validate = '{data.get("validate", "")}';
                            window.geetest_seccode = '{data.get("seccode", "")}';
                            if (typeof verify == 'function') verify();
                        """)
                        
                    elif captcha_info.captcha_type == CaptchaType.FUNCAPTCHA:
                        # FunCaptcha token
                        await page.evaluate(f"""
                            let input = document.getElementById('fc-token');
                            if (input) input.value = '{data}';
                        """)
                    
                
                # SMART WAIT: Чекаємо поки капча зникне (GeeTest потребує часу на анімацію!)
                captcha_disappeared = False
                for wait_attempt in range(15):  # max 15 seconds
                    await asyncio.sleep(1)
                    if not await captcha_detector.quick_check(page, marketplace):
                        captcha_disappeared = True
                        logger.info(f"✅ Captcha disappeared after {wait_attempt + 1}s!")
                        break
                
                if not captcha_disappeared:
                    logger.error("❌ Captcha still present after solving")
                    await asyncio.sleep(2)
                    continue # Failed attempt, try again
                
                logger.info("✅ Captcha solved successfully! Resuming warmup...")
                
                # 🔥 NEW: COOLDOWN після успішного вирішення (дати Shein "остигнути")
                cooldown_time = random.uniform(15, 25)
                logger.info(f"⏱️ Cooldown {cooldown_time:.1f}s to let {marketplace} settle...")
                await asyncio.sleep(cooldown_time)
                
                # 🔥 CRITICAL FIX: CHECK FOR "ACCESS TIMED OUT" & RELOAD
                # Якщо сторінка "померла" поки ми вирішували капчу
                try:
                    timed_out = await page.get_by_text("Access timed out").is_visible()
                    refresh_needed = await page.get_by_text("please refresh the page").is_visible()
                    
                    if timed_out or refresh_needed or context == "browsing":
                        logger.info("🔄 Page stale after captcha. Reloading to restore session...")
                        await page.reload(wait_until="domcontentloaded")
                        await asyncio.sleep(5)
                        
                        # Після релоаду може знову вилізти попап
                        await self.close_popups(page, marketplace)
                except Exception as e:
                    logger.warning(f"Error during post-captcha reload: {e}")
                
                # Restore image blocking
                if marketplace == 'aliexpress':
                    page.image_blocking_enabled = True
                    logger.info("   🚫 Images BLOCKED again (AliExpress)")
                else:
                    page.image_blocking_enabled = False
                    logger.info("   🖼️ Images left ENABLED")
                
                return True # Success
                
            except Exception as e:
                 logger.error(f"❌ Error in captcha handler attempt: {e}")
                 await asyncio.sleep(2)
                 continue # Try next attempt
        
        # Restore image blocking if failed
        if marketplace == 'aliexpress':
            page.image_blocking_enabled = True
        else:
            page.image_blocking_enabled = False
        
        # 🔥 Context-aware failure handling
        if context == "browsing":
            logger.warning(f"⚠️ Failed to solve captcha in {context} mode, but continuing (non-fatal)")
            return True  # Don't fail session for browsing captchas
        else:
            logger.error(f"❌ Failed to solve captcha in {context} mode")
            return False # Failed after all attempts


    async def _natural_scroll(self, page: Page):
        """Simulates human-like scrolling behavior."""
        try:
            # Safety check: ensure body exists
            if not await page.evaluate("() => !!document.body"):
                return

            total_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")
            current_y = 0
            
            # Randomly decide how much of the page to scroll (50% to 90%)
            target_y = int(total_height * random.uniform(0.5, 0.9))
            
            while current_y < target_y:
                # Random scroll distance
                scroll_step = random.randint(300, 700)
                current_y += scroll_step
                
                await page.mouse.wheel(0, scroll_step)
                await asyncio.sleep(random.uniform(0.5, 2.0))
                
                # Occasionally scroll up a bit (correction behavior)
                if random.random() < 0.2:
                    await page.mouse.wheel(0, -random.randint(50, 200))
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    
                # Occasionally stop to "read"
                if random.random() < 0.1:
                    await asyncio.sleep(random.uniform(2.0, 4.0))

        except Exception as e:
            logger.warning(f"Scroll error: {e}")

    async def _warmup_generic(self, marketplace, config, specific_proxy=None, specific_session_file=None):
        """
        True "Random Walker" Logic:
        1. Homepage -> 2. Click Random Banner/Menu -> 3. Scroll & Click Random Product
        """
        
        # Setup Proxy & Paths
        target_session_file = specific_session_file if specific_session_file else config['cookie_file']
        target_proxy_file = config['proxy_file']

        if specific_proxy:
            selected_proxies = [specific_proxy]
        else:
            self.proxy_manager.load_proxies()
            all_proxies = self.proxy_manager.get_all_proxies()
            if not all_proxies: return False
            random.shuffle(all_proxies)
            selected_proxies = all_proxies[:3] # Try up to 3 proxies

        async with async_playwright() as p:
            for proxy_dict in selected_proxies:
                session_valid = True
                logger.info(f"🚀 [RandomWalker] Trying proxy: {proxy_dict['server']}")
                
                # --- Browser Setup ---
                proxy_config = {"server": proxy_dict['server']}
                if proxy_dict.get('username'):
                    proxy_config['username'] = proxy_dict['username']
                    proxy_config['password'] = proxy_dict.get('password')

                try:
                    browser = await p.chromium.launch(
                        headless=settings.HEADLESS,
                        proxy=proxy_config,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US',
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    )
                    
                    # Apply Stealth & Route Images
                    try:
                        from playwright_stealth import Stealth
                        stealth = Stealth()
                        page = await context.new_page()
                        
                        # Images optimization:
                        async def image_route_handler(route):
                            if getattr(page, "image_blocking_enabled", False):
                                await route.abort()
                            else:
                                await route.continue_()

                        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", image_route_handler)
                        
                        if marketplace == 'aliexpress':
                            page.image_blocking_enabled = True
                            logger.info("   🚫 Images initially BLOCKED (AliExpress)")
                        else:
                            page.image_blocking_enabled = False 
                            logger.info("   🖼️ Images initially ENABLED")
                            
                        await stealth.apply_stealth_async(page)
                    except:
                        if 'page' not in locals(): page = await context.new_page()

                    # 1. Check IP
                    try:
                        await page.goto("https://api.ipify.org", timeout=15000)
                        logger.info("✅ Proxy connected")
                    except:
                        await browser.close()
                        continue

                    # --- STEP 1: LAND ON HOMEPAGE ---
                    target_url = config['target']
                    logger.info(f"1️⃣ Landing on Homepage: {target_url}")
                    
                    try:
                        await page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                    except:
                        logger.warning("   ⚠️ Timeout on entry, reloading...")
                        try: await page.reload()
                        except: pass

                    await asyncio.sleep(random.uniform(4, 7))

                    # 🛡️ CAPTCHA & POPUPS (Essential on Homepage)
                    if not await self.check_and_solve_captcha(page, marketplace, context="entry"):
                        logger.warning("   ❌ Failed entry captcha. Closing.")
                        session_valid = False # Fail session
                        await browser.close()
                        continue

                    # 🔥 CLOSE POPUPS & ACCEPT COOKIES IMMEDIATELY
                    await self.close_popups(page, marketplace)
                    await self.set_regional_settings(page, marketplace)

                    # --- STEP 2: FIND "INTERESTING" LINKS (Banners/Categories) ---
                    # We want to click what a human clicks (Images, Big text), NOT "Privacy Policy" or "Login"
                    logger.info("2️⃣ Looking for something interesting to click...")
                    await self._natural_scroll(page)
                    
                    interesting_links = await page.evaluate("""
                        () => {
                            const links = [];
                            const badKeywords = ['login', 'register', 'signin', 'signup', 'help', 'terms', 'privacy', 'about', 'contact', 'affiliate', 'app'];
                            
                            // Get all links
                            document.querySelectorAll('a').forEach(el => {
                                // Must be visible
                                const rect = el.getBoundingClientRect();
                                if (rect.width < 10 || rect.height < 10 || rect.top > window.innerHeight * 2) return;
                                
                                // Must be internal URL
                                if (!el.href.includes(window.location.hostname)) return;
                                
                                const href = el.href.toLowerCase();
                                const text = el.innerText.toLowerCase();
                                
                                // Filter out "utility" links
                                if (badKeywords.some(kw => href.includes(kw) || text.includes(kw))) return;
                                
                                // Prioritize links with images inside (Banners!)
                                const hasImg = el.querySelector('img') !== null;
                                
                                links.push({href: el.href, hasImg: hasImg});
                            });
                            
                            // Return mostly links with images, or just any valid link
                            const imgLinks = links.filter(l => l.hasImg);
                            return imgLinks.length > 0 ? imgLinks.map(l => l.href) : links.map(l => l.href);
                        }
                    """)

                    if not interesting_links:
                        logger.warning("   ⚠️ No interesting links found. Staying on homepage.")
                    else:
                        # Pick a random "Interest"
                        # Weight towards top results (usually main banners) but keep it random
                        # Take top 10 unique links
                        unique_links = list(set(interesting_links))
                        chosen_category = random.choice(unique_links[:12]) 
                        logger.info(f"   🖱️ User 'clicked': {chosen_category[:60]}...")
                        
                        try:
                            # Navigate to the chosen category/banner
                            await page.goto(chosen_category, wait_until="domcontentloaded")
                            await asyncio.sleep(random.uniform(3, 6))
                        except: pass

                    # --- STEP 3: FIND & CLICK PRODUCTS ---
                    # Now we are inside a category (or still on home), look for products
                    logger.info("3️⃣ Looking for products...")
                    await self._natural_scroll(page)
                    
                    product_links = await page.evaluate("""
                        () => {
                            const links = [];
                            const selectors = [
                                'a[href*="-p-"]',           // Shein
                                'a[href*="/p-"]',           // Shein
                                'a.S-product-item__link',   // Shein Class
                                'a[href*=".html"]',         // Ali/Temu
                                '.product-list a',          
                                '.product-card a'
                            ];
                            
                            for (let sel of selectors) {
                                document.querySelectorAll(sel).forEach(el => {
                                    if(el.href && el.href.startsWith('http') && !links.includes(el.href)) {
                                        links.push(el.href);
                                    }
                                });
                                if (links.length > 5) break; 
                            }
                            return links.slice(0, 15);
                        }
                    """)

                    if product_links:
                        # Visit 2-3 random products found in this flow
                        products_to_visit = random.sample(product_links, min(3, len(product_links)))
                        
                        for idx, prod_link in enumerate(products_to_visit):
                            logger.info(f"   👕 Viewing Product [{idx+1}]: {prod_link[:60]}...")
                            
                            try:
                                await page.goto(prod_link, wait_until="domcontentloaded")
                                
                                # Check for Rate Limit Captcha
                                if not await self.check_and_solve_captcha(page, marketplace, context="browsing"):
                                    logger.warning("   🛑 Rate Limit. Stopping session.")
                                    session_valid = False
                                    break 
                                
                                await self._natural_scroll(page)
                                await asyncio.sleep(random.uniform(5, 12)) # Longer read time
                                
                                # 50% chance to go back to category
                                if idx < len(products_to_visit) - 1 and random.random() < 0.5:
                                    logger.info("   🔙 Going back...")
                                    await page.go_back()
                                    await asyncio.sleep(2)
                                    
                            except Exception as e:
                                logger.warning(f"Error visiting product: {e}")
                                continue
                                
                    else:
                        logger.warning("   ⚠️ No products found in this category.")

                    # --- STEP 4: SAVE ---
                    if session_valid:
                        logger.info(f"✅ Random Walk Complete. Saving session to {target_session_file}")
                        try:
                            await context.storage_state(path=target_session_file)
                            
                            if not specific_proxy:
                                proxy_data = {
                                    "server": proxy_dict['server'],
                                    "username": proxy_dict.get('username'),
                                    "password": proxy_dict.get('password'),
                                    "updated": asyncio.get_event_loop().time()
                                }
                                with open(target_proxy_file, "w") as f: json.dump(proxy_data, f, indent=2)
                                logger.info(f"🎉 Saved session/proxy for {marketplace}")
                        except Exception as e:
                            logger.error(f"Failed to save session: {e}")
                        
                        await browser.close()
                        return True
                    else:
                        logger.warning("❌ Session invalid. Discarding.")
                        await browser.close()

                except Exception as e:
                    logger.error(f"❌ Error in Random Walker: {e}")
                    try: await browser.close()
                    except: pass
                    continue
            
            return False

    async def warmup_shein(self, specific_proxy=None, specific_session_file=None):
        """Warmup для Shein"""
        return await self._warmup_generic('shein', self.WARMUP_URLS['shein'], specific_proxy, specific_session_file)
    
    async def warmup_aliexpress(self, specific_proxy=None, specific_session_file=None):
        """Warmup для AliExpress"""
        return await self._warmup_generic('aliexpress', self.WARMUP_URLS['aliexpress'], specific_proxy, specific_session_file)
    
    async def warmup_temu(self):
        """Warmup для Temu"""
        logger.warning("Temu warmup not configured")
        return False
    
    async def run_warmup(self, marketplace, proxy_data=None, session_file=None):
        """Запуск warmup"""
        logger.info(f"🔥 Starting warmup for {marketplace}...")
        method = getattr(self, f"warmup_{marketplace.lower()}", None)
        if not method: return False
        
        # Pass optional args IF the method accepts them (it should now)
        try:
            success = await method(proxy_data, session_file)
        except TypeError:
             # Fallback for methods not yet updated (e.g. Temu if any)
             success = await method()

        if success: self.record_warmup(marketplace)
        return success
    
    async def handle_captcha(self, marketplace, force=False, proxy_data=None, session_file=None):
        """External usage point"""
        if force: logger.warning(f"⚠️ Force warmup for {marketplace}")
        if not force and not self.can_warmup(marketplace): return False
        return await self.run_warmup(marketplace, proxy_data, session_file)

    def get_stats(self, marketplace=None):
        if marketplace: return self.history.get(marketplace, {})
        return self.history

auto_warmup = AutoWarmup()
