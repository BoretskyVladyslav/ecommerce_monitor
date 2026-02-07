from abc import ABC
from playwright.async_api import Page
import asyncio
import random
from config.logger import setup_logger
from parsers.exceptions import SoftBanException, HardBanException
from utils.captcha_detector import captcha_detector
from utils.captcha_solver import captcha_solver

class BaseParser(ABC):
    def __init__(self, page: Page):
        self.page = page
        self.logger = setup_logger(self.__class__.__name__)
        # Визначаємо платформу на основі класу
        if "AliExpress" in self.__class__.__name__:
            self.marketplace = "aliexpress"
        elif "Shein" in self.__class__.__name__:
            self.marketplace = "shein"
        elif "Temu" in self.__class__.__name__:
            self.marketplace = "temu"
        else:
            self.marketplace = "unknown"
            
        # Session path for saving state
        self.session_path = f"{self.marketplace}_session_state.json"

    async def save_session(self):
        """Saves values (cookies/storage) to the session file."""
        if self.marketplace == "unknown": return

        try:
            await self.page.context.storage_state(path=self.session_path)
            self.logger.info(f"💾 Session saved to {self.session_path}")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to save session: {e}")

    async def check_for_captcha(self):
        """
        🔥 WORK MODE: Immediately trigger warmup instead of solving in the main flow.
        """
        is_captcha = await captcha_detector.quick_check(self.page, self.marketplace)
        
        if is_captcha:
            self.logger.warning(f"🚫 Captcha detected on {self.marketplace} during work process!")
            
            # --- DEBUG: Introspect Recaptcha Widget (optional but kept) ---
            try:
                self.logger.info("🐞 DEBUG: Inspecting Recaptcha Widget...")
                frames = self.page.frames
                for f in frames:
                    if "acs.aliexpress" in f.url or "recaptcha" in f.url:
                        self.logger.info(f"🐞 Frame found: {f.url}")
            except: pass
            
            # --- FAIL FAST ---
            # Raise SoftBan to trigger MonitorEngine's cookie deletion and warmup trigger
            raise SoftBanException(f"Captcha detected on {self.marketplace} - Yielding to Warmup")

    async def wait_for_captcha_or_element(self, selector: str, timeout: int = 20) -> bool:
        """
        🔥 SMART WAIT: Waits for an element to appear, but periodically checks for captchas.
        Returns True if element is found.
        Raises SoftBanException if captcha is found.
        Returns False if timeout reached.
        """
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            # 1. Check for Captcha
            is_captcha = await captcha_detector.quick_check(self.page, self.marketplace)
            if is_captcha:
                self.logger.warning(f"🚨 Captcha detected while waiting for {selector}!")
                raise SoftBanException(f"Captcha detected on {self.marketplace} - Yielding to Warmup")
            
            # 2. Check for Element
            try:
                if await self.page.locator(selector).is_visible(timeout=1000): # Short timeout for element check
                    return True
            except:
                pass
                
            # Wait a bit before next check
            await asyncio.sleep(2)
            
        return False


    async def solve_captcha(self, max_attempts: int = 5) -> bool:
        """
        Attempts to solve the detected captcha using CaptchaSolver and SliderSolver.
        Includes retry logic for unstable captchas (UNSOLVABLE errors).
        """
        if self.marketplace.lower() == 'aliexpress':
            self.logger.warning("🚫 Captcha solving disabled for AliExpress (per user request). Failing immediately.")
            return False

        for attempt in range(max_attempts):
            self.logger.info(f"🧩 Captcha Solve Attempt {attempt + 1}/{max_attempts}")
            
            try:
                # 1. Full detection with screenshot
                info = await captcha_detector.detect(self.page, self.marketplace, take_screenshot=True)
                
                if not info.detected:
                    self.logger.info("✅ Captcha disappeared during detailed check.")
                    return True
                    
                self.logger.info(f"🧩 Solving {info.captcha_type}...")
                
                # 2. Get solution from API
                solve_params = {"page_url": self.page.url}
                if info.additional_data:
                    solve_params.update(info.additional_data)
                    
                solution = await captcha_solver.solve(
                    captcha_type=info.captcha_type,
                    image_path=info.screenshot_path,
                    additional_params=solve_params
                )
                
                if not solution.solved:
                    # Fix: solution.data contains error message if solved is False
                    err_msg = str(solution.data) if solution.data else "Unknown error"
                    
                    if "UNSOLVABLE" in err_msg.upper():
                        self.logger.warning("⚠️ Captcha marked UNSOLVABLE by API. Retrying with new screenshot...")
                        await asyncio.sleep(2)
                        continue 
                    
                    self.logger.error(f"❌ Auto-solver failed: {err_msg}")
                    await asyncio.sleep(2)
                    continue

                # 3. Apply solution
                self.logger.info(f"🛠️ Applying solution ({solution.solution_type})...")
                
                applied_success = await self._apply_solution(solution, info)
                if applied_success:
                    return True
                else:
                    self.logger.warning("⚠️ Failed to apply solution. Retrying...")
                    await asyncio.sleep(2)
                    continue

            except Exception as e:
                self.logger.error(f"⚠️ Error during solve attempt {attempt+1}: {e}")
                await asyncio.sleep(2)
        
        self.logger.error("❌ Failed to solve captcha after all attempts.")
        return False

    async def _apply_solution(self, solution, info) -> bool:
        """Helper to apply solution (extracted from original solve_captcha)"""
        if solution.solution_type == "coordinates":
                # Імпорт тут, щоб уникнути циклічних імпортів
                from utils.slider_solver import slider_solver 
                
                points = solution.data
                if not points: 
                    self.logger.error("❌ No coordinates received.")
                    return False

                # ---------------------------------------------------
                # ВАРІАНТ 1: SLIDER (AliExpress)
                # ---------------------------------------------------
                if info.captcha_type == "slider":
                    slider_btn = info.element_handle
                    # Перестраховка: шукаємо кнопку, якщо хендл застарів
                    if not slider_btn:
                        slider_btn = await self.page.query_selector("#nc_1_n1z, .btn_slide, .slider-btn")
                    
                    if slider_btn:
                        # Для слайдера нам потрібна тільки X координата першої точки
                        # Але тут теж важливий масштаб!
                        # Зазвичай API повертає дистанцію у фізичних пікселях.
                        # Якщо слайдер "пролітає" занадто далеко - додайте ділення на DPR (див. нижче)
                        x_offset = int(points[0]['x'])
                        await slider_solver.slide(self.page, slider_btn, x_offset)
                    else:
                        self.logger.error("❌ Slider button not found.")

                # ---------------------------------------------------
                # ВАРІАНТ 2: CLICKS (Shein / Geetest / Icons)
                # ---------------------------------------------------
                else:
                    self.logger.info(f"📍 Coordinates task for {self.marketplace}. Handling PIXELS & OFFSETS...")
                    
                    target_element = info.element_handle
                    if not target_element:
                        # Резервний пошук для Shein
                        target_element = await self.page.query_selector(".geetest_window, .geetest_widget, .geetest_item_wrap")

                    if target_element:
                        # 1. ОТРИМУЄМО КОЕФІЦІЄНТ МАСШТАБУВАННЯ (DPR)
                        # Це те, що ви просили не забути!
                        dpr = await self.page.evaluate("window.devicePixelRatio")
                        self.logger.info(f"🖥️ Device Pixel Ratio (DPR): {dpr}")

                        # 2. Отримуємо позицію картинки на сторінці (CSS пікселі)
                        box = await target_element.bounding_box()
                        
                        if box:
                            offset_x = box['x']
                            offset_y = box['y']
                            width_css = box['width']
                            
                            self.logger.info(f"📐 CSS Box: X={offset_x}, Y={offset_y}, W={width_css}")
                            
                            # 3. МАТЕМАТИКА КЛІКУ
                            for i, p in enumerate(points):
                                api_x = float(p['x'])
                                api_y = float(p['y'])

                                # Логіка перевірки масштабу:
                                # API зазвичай працює з картинкою, яку ми йому надіслали.
                                # Якщо скріншот був зроблений з урахуванням DPR, він у DPR разів більший за CSS.
                                # Тому координати від API треба поділити на DPR.
                                
                                # УВАГА: Якщо ви використовуєте стандартний screenshot() у Playwright,
                                # він зберігає розмір як у CSS (автоматично даунскейлить), 
                                # АБО як фізичні пікселі залежно від налаштувань.
                                # Найкращий спосіб перевірити - просто поділити на DPR. 
                                # Якщо API часто "маже", спробуйте прибрати ділення (scale_x = api_x).
                                
                                final_x = (api_x / dpr) + offset_x
                                final_y = (api_y / dpr) + offset_y
                                
                                self.logger.info(f"🖱️ Click {i+1}: API({api_x},{api_y}) -> PAGE({final_x:.1f},{final_y:.1f})")
                                
                                await self.page.mouse.click(final_x, final_y)
                                await asyncio.sleep(random.uniform(0.3, 0.6))
                            
                            # 4. ПІДТВЕРДЖЕННЯ (CONFIRM)
                            # На Shein кнопка Confirm часто з'являється після кліків
                            await asyncio.sleep(0.5)
                            
                            # Розширений пошук кнопки Confirm
                            selectors = [
                                "div[aria-label='Confirm']", 
                                ".geetest_commit_tip", 
                                ".geetest_commit", 
                                ".geetest_submit",
                                ".captcha_click_confirm", # User Recommendation
                                "text=Confirm",
                                "text=confirm",
                                "text=OK"
                            ]
                            
                            confirm_btn = None
                            
                            # 1. Шукаємо в контексті елемента (якщо це контейнер)
                            if info.element_handle:
                                try:
                                    confirm_btn = await info.element_handle.query_selector("text=Confirm")
                                    if not confirm_btn:
                                         confirm_btn = await info.element_handle.query_selector(".geetest_commit")
                                except: pass
                            
                            # 2. Шукаємо на сторінці
                            if not confirm_btn:
                                for sel in selectors:
                                    try:
                                        confirm_btn = await self.page.query_selector(sel)
                                        if confirm_btn and await confirm_btn.is_visible():
                                            break
                                        confirm_btn = None
                                    except: continue

                            # 3. Шукаємо у фреймах (якщо на сторінці нема)
                            if not confirm_btn:
                                for frame in self.page.frames:
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
                                self.logger.info("✅ Found Confirm button, clicking...")
                                await confirm_btn.click()
                                await asyncio.sleep(1) # Wait for submission
                            else:
                                self.logger.warning("⚠️ Confirm button not found (auto-submitted?)")
                                
                # End of "coordinates" block
        
        elif solution.solution_type == "token":
                # Inject token
                data = solution.data
                if info.captcha_type == "geetest":
                     await self.page.evaluate(f"""
                        window.geetest_challenge = '{data.get("challenge", "")}';
                        window.geetest_validate = '{data.get("validate", "")}';
                        window.geetest_seccode = '{data.get("seccode", "")}';
                    """)
                elif info.captcha_type == "funcaptcha":
                     await self.page.evaluate(f"document.getElementById('fc-token').value = '{data}';")
                
                elif info.captcha_type == "recaptcha_v2":
                    # === ВИПРАВЛЕНА ЛОГІКА ДЛЯ IFRAME ===
                    try:
                        # JS скрипт, який ми будемо виконувати (всередині фрейму або на сторінці)
                        injection_script = f"""(token) => {{
                            console.log("Starting robust injection logic...");
                            let tokenValue = '{data}';
                            
                            // 1. Fill textarea (Create if missing - vital for AliExpress)
                            let el = document.getElementById("g-recaptcha-response");
                            if (!el) el = document.querySelector('[name="g-recaptcha-response"]');
                            if (!el) {{
                                console.log("Creating missing g-recaptcha-response element...");
                                el = document.createElement('textarea');
                                el.id = 'g-recaptcha-response';
                                el.name = 'g-recaptcha-response';
                                el.style.display = 'none';
                                document.body.appendChild(el);
                            }}
                            
                            el.style.display = 'block';
                            el.value = tokenValue;
                            el.innerHTML = tokenValue;
                            console.log("Token injected into textarea.");

                            // 2. Callback execution
                            let callbackCalled = false;
                            
                            // A. Check for 'clients' in global grecaptcha object (Power Move)
                            try {{
                                if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {{
                                    for (let i in window.___grecaptcha_cfg.clients) {{
                                        let client = window.___grecaptcha_cfg.clients[i];
                                        for (let key in client) {{
                                            if (client[key] && client[key].callback) {{
                                                    if (typeof client[key].callback === 'function') {{
                                                        client[key].callback(tokenValue);
                                                        callbackCalled = true;
                                                        console.log("Called grecaptcha client callback via cfg");
                                                    }}
                                            }}
                                        }}
                                    }}
                                }}
                            }} catch(e) {{ console.error("Error checking grecaptcha cfg: " + e); }}

                            // B. Data-callback attribute
                            if (!callbackCalled) {{
                                let widget = document.querySelector('.g-recaptcha, .recaptcha-checkbox, iframe[src*="recaptcha"]');
                                if(widget) {{
                                    let cbName = widget.getAttribute('data-callback');
                                    if(!cbName) {{
                                         let parent = widget.closest('.g-recaptcha');
                                         if(parent) cbName = parent.getAttribute('data-callback');
                                    }}
                                    
                                    if (cbName && typeof window[cbName] === 'function') {{
                                        window[cbName](tokenValue);
                                        callbackCalled = true;
                                        console.log("Called data-callback: " + cbName);
                                    }}
                                }}
                            }}

                            // C. Fallback: Click buttons
                            if (!callbackCalled) {{
                                    console.log("No callback found. Trying submit buttons.");
                                    let btn = document.querySelector('#recaptcha-demo-submit, #nc_1_n1z, [type="submit"], .btn_slide, .slider-btn');
                                    if(btn) {{
                                        btn.click();
                                        console.log("Clicked fallback button");
                                    }}
                            }}
                        }}"""

                        # --- КРОК 1: Шукаємо Iframe (Специфічно для AliExpress) ---
                        # Шукаємо фрейм, в URL якого є 'acs.aliexpress.com' або 'punish'
                        captcha_frame_element = await self.page.query_selector("iframe[src*='acs.aliexpress.com'], iframe[src*='punish']")
                        
                        executed_in_frame = False
                        if captcha_frame_element:
                            self.logger.info("Found AliExpress Security Iframe. Injecting inside frame...")
                            frame = await captcha_frame_element.content_frame()
                            if frame:
                                await frame.evaluate(injection_script, data)
                                executed_in_frame = True
                            else:
                                self.logger.warning("Found iframe element but content_frame is None.")

                        # --- КРОК 2: Якщо фрейм не знайшли або не спрацювало, пробуємо на головній ---
                        if not executed_in_frame:
                            self.logger.info("Injecting in Main Page context (Fallback)...")
                            await self.page.evaluate(injection_script, data)

                        self.logger.info("Executed reCAPTCHA solution script.")
                    except Exception as e:
                        self.logger.warning(f"Error executing reCAPTCHA script: {e}")
            
        elif solution.solution_type == "text":
            # Text captcha (Amazon style)
            text_solution = solution.data
            # Amazon input field
            input_field = self.page.locator("#captchacharacters")
            if await input_field.is_visible():
                await input_field.fill(text_solution)
                await asyncio.sleep(0.5)
                # Click button
                await self.page.click("button.a-button-text")
                self.logger.info(f"Entered captcha text: {text_solution}")
            
            # 4. Wait and verify
            await asyncio.sleep(5)
            if await captcha_detector.quick_check(self.page, self.marketplace):
                self.logger.error("❌ Captcha still present.")
                return False
                
            return True


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
                
                # Check for Immediate Block / Access Denied
                title = await self.page.title()
                content = await self.page.content()
                
                # Common Block Indicators
                if "Access Denied" in title or "Access Denied" in content:
                    self.logger.warning(f"🚫 PROXY BLOCKED: Access Denied on {url}")
                    raise HardBanException("Access Denied - Proxy Blocked")
                
                # AliExpress Specific "Slider" on blank page (User Screenshot)
                # Usually has title "Slider" or specific iframe
                if "Slider" in title and "aliexpress" in url:
                     self.logger.warning(f"🚫 PROXY BLOCKED: Slider Page on {url}")
                     raise HardBanException("AliExpress Slider Block - Proxy Blocked")

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