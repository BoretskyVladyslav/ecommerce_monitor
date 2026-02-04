"""
Captcha Detection Module
Централізована система детекції капчі для всіх платформ (AliExpress, Shein, Temu).
Визначає тип капчі, робить скріншоти, та надає уніфікований інтерфейс.
"""
import asyncio
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from playwright.async_api import Page
from config.logger import setup_logger

logger = setup_logger("CaptchaDetector")


class CaptchaType:
    """Типи капчі"""
    SLIDER = "slider"           # Слайдер (перетягування)
    PUZZLE = "puzzle"           # Пазл (розставити елементи)
    TEXT = "text"               # Текстова капча (введення символів)
    RECAPTCHA_V2 = "recaptcha_v2"  # Google reCaptcha v2 (checkbox)
    RECAPTCHA_V3 = "recaptcha_v3"  # Google reCaptcha v3 (invisible)
    GRID = "grid"               # Grid/ReCaptcha сітка (вибери всі світлофори)
    CLICK_POINTS = "click_points"  # GeeTest Icon (натисни точки/ієрогліфи в порядку)
    ROTATE = "rotate"           # FunCaptcha/Arkose Labs (поверни картинку)
    FUNCAPTCHA = "funcaptcha"   # Arkose Labs FunCaptcha (альтернативна назва)
    GEETEST = "geetest"         # GeeTest captcha (китайський сервіс)
    UNKNOWN = "unknown"         # Невизначений тип


class CaptchaInfo:
    """Інформація про виявлену капчу"""
    def __init__(
        self,
        detected: bool = False,
        captcha_type: str = CaptchaType.UNKNOWN,
        platform: str = "unknown",
        selector: str = "",
        screenshot_path: Optional[str] = None,
        element_handle: Any = None,
        additional_data: Optional[Dict] = None
    ):
        self.detected = detected
        self.captcha_type = captcha_type
        self.platform = platform
        self.selector = selector
        self.screenshot_path = screenshot_path
        self.element_handle = element_handle
        self.additional_data = additional_data or {}
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        """Конвертує в словник для логування"""
        return {
            "detected": self.detected,
            "type": self.captcha_type,
            "platform": self.platform,
            "selector": self.selector,
            "screenshot": self.screenshot_path,
            "timestamp": self.timestamp.isoformat(),
            "additional_data": self.additional_data
        }


class CaptchaDetector:
    """
    Централізований детектор капчі для всіх платформ.
    Виявляє різні типи капчі та робить скріншоти для подальшої обробки.
    """
    
    # Директорія для збереження скріншотів капчі
    SCREENSHOT_DIR = Path("captcha_screenshots")
    
    # Платформо-специфічні селектори капчі
    PLATFORM_SELECTORS = {
        "aliexpress": {
            # Slider captcha (найбільш поширена на AliExpress)
            "slider": [
                "#nc_1__scale_text",           # Основний слайдер AliExpress
                ".nc-lang-cnt",                # Контейнер слайдера
                "#nc_1_wrapper",               # Wrapper слайдера
                "div[id*='nc_'][id*='scale']", # Динамічні ID слайдерів
                ".slider-verify",              # Альтернативний селектор
            ],
            # GeeTest captcha (дуже поширений на AliExpress)
            "geetest": [
                ".geetest_holder",             # Основний контейнер GeeTest
                ".geetest_widget",
                ".geetest_panel",
                "div[class*='geetest']",
                ".gt_cut_fullbg",              # GeeTest slider background
                ".geetest_radar_tip",          # GeeTest click points
            ],
            # Click Points / Icon selection
            "click_points": [
                ".geetest_item_wrap",          # GeeTest icon grid
                "text='Click in sequence'",
                "text='Click on'",
                ".icon-select-captcha",
            ],
            # Generic captcha indicators
            "generic": [
                "iframe[src*='captcha']",
                "div[class*='captcha']",
                "#captcha",
                "text='Click to verify'",
                "text='Slide to verify'",
            ]
        },
        "shein": {
            # Shein використовує різні типи капчі
            "slider": [
                ".slider-verify",
                "text='Slide to verify'",
                ".risk-verify-slider",
            ],
            "puzzle": [
                ".puzzle-verify",
                "text='Complete the puzzle'",
            ],
            # FunCaptcha / Arkose Labs (часто на Shein)
            "funcaptcha": [
                "#FunCaptcha",
                "iframe[src*='arkoselabs']",
                "iframe[src*='funcaptcha']",
                ".arkose-captcha",
                "text='Verify to continue'",
            ],
            # Rotate captcha
            "rotate": [
                ".rotate-verify",
                "text='Rotate the image'",
                ".image-rotation-captcha",
            ],
            # Grid/ReCaptcha
            "grid": [
                ".recaptcha-checkbox",
                "iframe[src*='recaptcha/api2']",
                "text='Select all images'",
            ],
            "click_points": [
                ".geetest_item_wrap",
                "text=Please select the following graphics in order",
                "text=Click in order",
                ".geetest_widget",
                "div[class*='geetest']",
                "text=Confirm",
            ],
            "generic": [
                "#captcha-box",
                "iframe[src*='captcha']",
                "text='Risk Challenge'",
                "text='Quick Security Check'",
                "text='Verify you are human'",
                ".verify-code-container",
            ]
        },
        "temu": {
            # Temu captcha selectors
            "slider": [
                "div[class*='slider-verify']",
                "text='Drag the slider'",
                ".security-verify-slider",
            ],
            "puzzle": [
                "div[class*='puzzle']",
                ".jigsaw-verify",
            ],
            # FunCaptcha (Temu також використовує)
            "funcaptcha": [
                "iframe[src*='arkoselabs']",
                "iframe[src*='funcaptcha']",
                ".rotate-captcha",
            ],
            # GeeTest (можливо на Temu)
            "geetest": [
                ".geetest_holder",
                "div[class*='geetest']",
            ],
            "generic": [
                "#captcha",
                "iframe[src*='captcha']",
                "div[class*='captcha']",
                ".security-verify",
                "text='Security verification'",
            ]
        },
        # Generic selectors для всіх платформ
        "generic": {
            "recaptcha": [
                "iframe[src*='google.com/recaptcha']",
                "iframe[src*='recaptcha']",
                ".g-recaptcha",
                "#g-recaptcha",
            ],
            "cloudflare": [
                "iframe[src*='challenges.cloudflare.com']",
                "text='Verify you are human'",
                "text='Checking your browser'",
            ],
            "geetest": [
                ".geetest_holder",
                ".geetest_widget",
                "div[class*='geetest']",
            ],
            "funcaptcha": [
                "iframe[src*='arkoselabs.com']",
                "iframe[src*='funcaptcha.com']",
                "#FunCaptcha",
                ".arkose-captcha",
            ],
            "common": [
                "text='Enter the characters you see below'",
                "text='Please verify'",
                "text='Security check'",
                "text='Unusual activity'",
            ]
        }
    }
    
    def __init__(self):
        """Ініціалізація детектора"""
        # Створюємо директорію для скріншотів
        self.SCREENSHOT_DIR.mkdir(exist_ok=True)
        logger.info(f"✅ CaptchaDetector initialized. Screenshots: {self.SCREENSHOT_DIR}")
    
    async def detect(
        self,
        page: Page,
        platform: str = "unknown",
        take_screenshot: bool = True
    ) -> CaptchaInfo:
        """
        Основний метод детекції капчі.
        
        Args:
            page: Playwright Page об'єкт
            platform: Назва платформи (aliexpress, shein, temu)
            take_screenshot: Чи робити скріншот при виявленні
        
        Returns:
            CaptchaInfo об'єкт з результатами детекції
        """
        try:
            logger.debug(f"🔍 Checking for captcha on {platform}...")
            
            # Отримуємо селектори для платформи
            platform_lower = platform.lower()
            selectors = self.PLATFORM_SELECTORS.get(
                platform_lower,
                self.PLATFORM_SELECTORS.get("generic", {})
            )

            # 0. SPECIAL CHECK: AliExpress Security Check (ACS) / "Punish" page
            # This looks like Recaptcha (iframe) but is actually a Slider/Swipe challenge.
            # We MUST detect this as SLIDER to use the correct solver.
            if platform_lower == "aliexpress":
                # 1. Check for Recaptcha V2 (Priority over Slider on Security Page)
                # Some security pages use Recaptcha instead of the slider.
                recaptcha_frame = page.locator("iframe[src*='recaptcha'], .g-recaptcha, iframe[title*='reCAPTCHA']")
                if await recaptcha_frame.count() > 0:
                     if await recaptcha_frame.first.is_visible():
                        
                        print("type: recaptcha_v2")
                        logger.info("🚨 AliExpress Recaptcha V2 detected! (High Priority)")
                        element = await recaptcha_frame.first.element_handle()
                        print("type: ", type(element))
                        detection_result = ("recaptcha_v2", element, CaptchaType.RECAPTCHA_V2)
                        return await self._create_captcha_info(page, detection_result, platform, take_screenshot)

                # 2. Check for ACS Slider (Iframe based)
                acs_frame = page.locator("iframe[src*='acs.aliexpress'], iframe[src*='punish'], iframe[id*='baxia-dialog']")
                if await acs_frame.count() > 0:
                    if await acs_frame.first.is_visible():
                        logger.info("🚨 AliExpress Security Check (ACS) detected! Treating as SLIDER.")
                        
                        # Get element handle for screenshot/info logic
                        element = await acs_frame.first.element_handle()
                        
                        # Manually construct tuple to match signature: (selector, element, type)
                        detection_result = ("acs_frame", element, CaptchaType.SLIDER)
                        
                        return await self._create_captcha_info(
                            page, 
                            detection_result, 
                            platform, 
                            take_screenshot
                        )
            
            # Перевіряємо кожен тип капчі в порядку пріоритету
            
            # 1. GeeTest (дуже поширений на AliExpress)
            if "geetest" in selectors:
                result = await self._check_selectors(
                    page, selectors["geetest"], CaptchaType.GEETEST
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 2. FunCaptcha / Arkose Labs (Shein, Temu)
            if "funcaptcha" in selectors:
                result = await self._check_selectors(
                    page, selectors["funcaptcha"], CaptchaType.FUNCAPTCHA
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 3. Rotate captcha (часто частина FunCaptcha)
            if "rotate" in selectors:
                result = await self._check_selectors(
                    page, selectors["rotate"], CaptchaType.ROTATE
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 4. Click Points (GeeTest icon selection)
            if "click_points" in selectors:
                result = await self._check_selectors(
                    page, selectors["click_points"], CaptchaType.CLICK_POINTS
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 5. Grid captcha (ReCaptcha сітка)
            if "grid" in selectors:
                result = await self._check_selectors(
                    page, selectors["grid"], CaptchaType.GRID
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 6. Slider captcha (найпоширеніший на всіх платформах)
            if "slider" in selectors:
                result = await self._check_selectors(
                    page, selectors["slider"], CaptchaType.SLIDER
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 7. Puzzle captcha
            if "puzzle" in selectors:
                result = await self._check_selectors(
                    page, selectors["puzzle"], CaptchaType.PUZZLE
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 8. reCaptcha (generic)
            recaptcha_selectors = self.PLATFORM_SELECTORS["generic"]["recaptcha"]
            result = await self._check_selectors(
                page, recaptcha_selectors, CaptchaType.RECAPTCHA_V2
            )
            if result:
                return await self._create_captcha_info(
                    page, result, platform, take_screenshot
                )
            
            # 9. Generic captcha
            if "generic" in selectors:
                result = await self._check_selectors(
                    page, selectors["generic"], CaptchaType.UNKNOWN
                )
                if result:
                    return await self._create_captcha_info(
                        page, result, platform, take_screenshot
                    )
            
            # 10. Common indicators (текстові)
            common_selectors = self.PLATFORM_SELECTORS["generic"]["common"]
            result = await self._check_selectors(
                page, common_selectors, CaptchaType.TEXT
            )
            if result:
                return await self._create_captcha_info(
                    page, result, platform, take_screenshot
                )
            
            # Капчу не знайдено
            logger.debug(f"✅ No captcha detected on {platform}")
            return CaptchaInfo(detected=False, platform=platform)
            
        except Exception as e:
            logger.error(f"❌ Error during captcha detection: {e}")
            return CaptchaInfo(detected=False, platform=platform)
    
    async def _check_selectors(
        self,
        page: Page,
        selectors: list,
        captcha_type: str
    ) -> Optional[tuple]:
        """
        Перевіряє список селекторів на наявність.
        
        Returns:
            (selector, element) якщо знайдено, None якщо ні
        """
        for selector in selectors:
            try:
                # Обробка text= селекторів
                if selector.startswith("text="):
                    text_content = selector.replace("text=", "").strip("'\"")
                    locator = page.locator(f"text='{text_content}'")
                else:
                    locator = page.locator(selector)
                
                # Швидка перевірка на головній сторінці
                is_visible = await locator.is_visible(timeout=500)
                
                if is_visible:
                    element = await locator.first.element_handle()
                    
                    # FIX: If we found "Confirm" button, get the parent widget
                    if "Confirm" in selector and captcha_type == CaptchaType.CLICK_POINTS:
                         try:
                            logger.info("🔄 Found 'Confirm' button, looking for parent widget (Smart Search)...")
                            # Recursive search for a large container (likely the widget)
                            parent = await element.evaluate_handle("""el => {
                                let current = el;
                                for (let i = 0; i < 15; i++) {
                                    if (!current.parentElement) break;
                                    current = current.parentElement;
                                    const rect = current.getBoundingClientRect();
                                    // Check if it's big enough to be the full widget (width > 150px)
                                    if (rect.width > 150 && rect.height > 150) {
                                        return current;
                                    }
                                    // Or check specific classes
                                    if (current.classList && (
                                        current.classList.contains('geetest_widget') || 
                                        current.classList.contains('geetest_window') ||
                                        current.className.includes('geetest')
                                    )) {
                                        return current;
                                    }
                                }
                                // Fallback: return 5 levels up if nothing met criteria
                                return el.parentElement?.parentElement?.parentElement?.parentElement?.parentElement || el;
                            }""")
                             
                            if parent:
                                logger.info("✅ Found parent widget for 'Confirm' button")
                                element = parent
                         except Exception as e:
                             logger.warning(f"⚠️ Failed to find parent for confirm button: {e}")

                    logger.info(f"🚫 Captcha detected (Main Frame)! Type: {captcha_type}, Selector: {selector}")
                    return (selector, element, captcha_type)
                
                # --- IFRAME SCANNING ---
                # Якщо на головній не знайшли, шукаємо у всіх фреймах
                for frame in page.frames:
                    try:
                        frame_locator = None
                        if selector.startswith("text="):
                             text_content = selector.replace("text=", "").strip("'\"")
                             frame_locator = frame.locator(f"text='{text_content}'")
                        else:
                             frame_locator = frame.locator(selector)
                             
                        if await frame_locator.is_visible(timeout=100):
                             element = await frame_locator.first.element_handle()
                             
                             # FIX: If we found "Confirm" button in iframe, get the parent widget
                             if "Confirm" in selector and captcha_type == CaptchaType.CLICK_POINTS:
                                 try:
                                     logger.info(f"🔄 Found 'Confirm' button in iframe {frame.url}, looking for parent widget (Smart Search)...")
                                     parent = await element.evaluate_handle("""el => {
                                         let current = el;
                                         for (let i = 0; i < 15; i++) {
                                             if (!current.parentElement) break;
                                             current = current.parentElement;
                                             const rect = current.getBoundingClientRect();
                                             // Check if it's big enough to be the full widget
                                             if (rect.width > 150 && rect.height > 150) {
                                                 return current;
                                             }
                                             if (current.classList && (
                                                current.classList.contains('geetest_widget') || 
                                                current.classList.contains('geetest_window') ||
                                                current.className.includes('geetest')
                                             )) {
                                                return current;
                                             }
                                         }
                                         return el.parentElement?.parentElement?.parentElement?.parentElement?.parentElement || el;
                                     }""")
                                     
                                     if parent:
                                         logger.info("✅ Found parent widget for 'Confirm' button (in iframe)")
                                         element = parent
                                 except Exception as e:
                                     logger.warning(f"⚠️ Failed to find parent for confirm button in iframe: {e}")
                                     
                             logger.info(f"🚫 Captcha detected in IFRAME! Url: {frame.url}, Type: {captcha_type}")
                             return (selector, element, captcha_type)
                    except:
                        continue
                        
            except Exception:
                # Timeout або елемент не знайдено - продовжуємо
                continue
        
        return None
    
    async def _create_captcha_info(
        self,
        page: Page,
        detection_result: tuple,
        platform: str,
        take_screenshot: bool
    ) -> CaptchaInfo:
        """
        Створює CaptchaInfo об'єкт з результатів детекції.
        """
        selector, element, captcha_type = detection_result
        screenshot_path = None
        
        # Smart wait for Shein captchas to fully render
        if take_screenshot and platform.lower() == "shein":
            try:
                logger.info("⏳ Waiting for Shein captcha to load (network idle)...")
                await page.wait_for_load_state("networkidle", timeout=30000)
                logger.info("⏳ Safety sleep (50s) because we really want it to load...")
                await asyncio.sleep(50)
            except Exception as e:
                logger.warning(f"⚠️ Network idle timeout (proceeding anyway): {e}")
                # Failsafe: minimum wait even if networkidle times out
                await asyncio.sleep(3)
        
        # Робимо скріншот якщо потрібно
        if take_screenshot:
            screenshot_path = await self._take_screenshot(page, element, platform)
        
        # Додаткові дані в залежності від типу
        additional_data = {}
        if captcha_type == CaptchaType.SLIDER:
            additional_data = await self._get_slider_info(page, element)
        elif captcha_type == CaptchaType.RECAPTCHA_V2:
            additional_data = await self._get_recaptcha_info(page, element)
        
        return CaptchaInfo(
            detected=True,
            captcha_type=captcha_type,
            platform=platform,
            selector=selector,
            screenshot_path=screenshot_path,
            element_handle=element,
            additional_data=additional_data
        )
    
    async def _take_screenshot(
        self,
        page: Page,
        element: Any,
        platform: str
    ) -> Optional[str]:
        """
        Робить скріншот елемента капчі або всієї сторінки.
        
        Returns:
            Шлях до збереженого скріншоту
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"{platform}_{timestamp}.png"
            filepath = self.SCREENSHOT_DIR / filename
            
            # Спробуємо зробити скріншот елемента
            if element:
                try:
                    await element.screenshot(path=str(filepath))
                    logger.info(f"📸 Captcha element screenshot saved: {filepath}")
                    return str(filepath)
                except Exception as e:
                    logger.warning(f"⚠️ Could not screenshot element: {e}")
            
            # Fallback: скріншот всієї сторінки
            await page.screenshot(path=str(filepath))
            logger.info(f"📸 Full page screenshot saved: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"❌ Failed to take screenshot: {e}")
            return None
    
    async def _get_slider_info(self, page: Page, element: Any) -> Dict:
        """
        Отримує додаткову інформацію про slider captcha.
        """
        try:
            if not element:
                return {}
            
            # Отримуємо bounding box
            box = await element.bounding_box()
            if box:
                return {
                    "x": box["x"],
                    "y": box["y"],
                    "width": box["width"],
                    "height": box["height"]
                }
        except Exception as e:
            logger.debug(f"Could not get slider info: {e}")
        
        return {}

    async def _get_recaptcha_info(self, page: Page, element: Any) -> Dict:
        """
        Extracts site_key from reCAPTCHA iframe or element.
        """
        try:
            site_key = None
            
            # 1. Check if element is an Iframe and has 'k=' in src
            if element:
                src = await element.get_attribute("src")
                if src and "k=" in src:
                    # Extract 'k' parameter
                    import urllib.parse
                    parsed = urllib.parse.urlparse(src)
                    params = urllib.parse.parse_qs(parsed.query)
                    if "k" in params:
                        site_key = params["k"][0]
            
            # 2. If not found, look for data-sitekey anywhere nearby or on page
            if not site_key:
                # Common selectors for sitekey
                selectors = [
                    "[data-sitekey]",
                    ".g-recaptcha", 
                    ".recaptcha-checkbox"
                ]
                for sel in selectors:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        key = await el.get_attribute("data-sitekey")
                        if key:
                            site_key = key
                            break
            
            # 3. Last resort: Frame matching
            if not site_key:
                frames = page.frames
                for frame in frames:
                    if "recaptcha" in frame.url and "k=" in frame.url:
                        import urllib.parse
                        parsed = urllib.parse.urlparse(frame.url)
                        params = urllib.parse.parse_qs(parsed.query)
                        if "k" in params:
                            site_key = params["k"][0]
                            break
            
            if site_key:
                logger.info(f"🔑 Found SiteKey: {site_key}")
                return {"site_key": site_key}
                
        except Exception as e:
            logger.error(f"Failed to extract site_key: {e}")
        
        return {}
    
    async def quick_check(self, page: Page, platform: str = "unknown") -> bool:
        """
        Швидка перевірка на наявність капчі (без скріншотів).
        Використовується під час warmup для частих перевірок.
        
        Returns:
            True якщо капча знайдена, False якщо ні
        """
        result = await self.detect(page, platform, take_screenshot=False)
        return result.detected
    
    def cleanup_screenshots(self, days_old: int = 7) -> int:
        """
        Видаляє старі скріншоти.
        
        Args:
            days_old: Видалити файли старші за N днів
        
        Returns:
            Кількість видалених файлів
        """
        try:
            import time
            from pathlib import Path
            
            now = time.time()
            cutoff = now - (days_old * 86400)  # days to seconds
            deleted = 0
            
            for file in self.SCREENSHOT_DIR.glob("*.png"):
                if file.stat().st_mtime < cutoff:
                    file.unlink()
                    deleted += 1
            
            if deleted > 0:
                logger.info(f"🗑️ Cleaned up {deleted} old captcha screenshots")
            
            return deleted
            
        except Exception as e:
            logger.error(f"❌ Error cleaning up screenshots: {e}")
            return 0


# Глобальний інстанс для використання в інших модулях
captcha_detector = CaptchaDetector()
