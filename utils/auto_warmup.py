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
    WARMUP_URLS = {
        'shein': {
            'target': "https://us.shein.com/pdsearch/Wonka",
            'cookie_file': "shein_session_state.json",
            'proxy_file': "shein_session_proxy.json",
            'warmup_products': [
                "https://us.shein.com/SHEIN-Frenchy-Letter-Graphic-Tee-p-22673044.html",
                "https://us.shein.com/Women-Handbags-c-1764.html",
                "https://us.shein.com/Women-Dresses-c-1727.html",
                "https://us.shein.com/SHEIN-Basics-Women-Crop-Tank-Top-p-11466685.html",
                "https://us.shein.com/Women-Shoes-c-1750.html"
            ]
        },
        'aliexpress': {
            'target': "https://www.aliexpress.com/w/wholesale-phone-cases.html",
            'cookie_file': "aliexpress_session_state.json",
            'proxy_file': "aliexpress_session_proxy.json",
            'warmup_products': [
                "https://www.aliexpress.com/item/1005001234567890.html",
                "https://www.aliexpress.com/category/200003482/women-clothing.html",
                "https://www.aliexpress.com/category/202001292/shoes.html",
                "https://www.aliexpress.com/w/wholesale-phone-cases.html",
                "https://www.aliexpress.com/w/wholesale-watches.html"
            ]
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

    async def check_and_solve_captcha(self, page: Page, marketplace: str) -> bool:
        """
        Перевіряє наявність капчі та намагається її вирішити.
        Повертає True якщо капчі немає або вона вирішена успішно.
        Повертає False якщо вирішити не вдалося.
        """
        try:
            # 1. Швидка перевірка (без скріншота)
            if not await captcha_detector.quick_check(page, marketplace):
                return True  # Капчі немає
            
            logger.warning(f"🛑 CAPTCHA DETECTED! Pausing warmup...")
            
            # 2. Детальна детекція зі скріншотом
            captcha_info = await captcha_detector.detect(page, marketplace, take_screenshot=True)
            
            if not captcha_info.detected:
                logger.info("✅ False alarm (captcha disappeared)")
                return True
            
            logger.info(f"🧩 Solving captcha type: {captcha_info.captcha_type}")
            
            # 3. Вирішуємо через API
            solution = await captcha_solver.solve(
                captcha_type=captcha_info.captcha_type,
                image_path=captcha_info.screenshot_path,
                additional_params={"page_url": page.url}
            )
            
            if not solution.solved:
                logger.error("❌ Failed to solve captcha via API")
                return False
            
            # 4. Застосовуємо рішення
            logger.info(f"🛠️ Applying solution: Type={solution.solution_type}")
            
            if solution.solution_type == "coordinates":
                # Це SLIDER або CLICK_POINTS
                points = solution.data
                if not points:
                    return False
                    
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
                        return False
                        
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
                 
            # Чекаємо результату
            await asyncio.sleep(5)
            
            # Перевіряємо чи зникла капча
            if await captcha_detector.quick_check(page, marketplace):
                logger.error("❌ Captcha still present after solving")
                return False
            
            logger.info("✅ Captcha solved successfully! Resuming warmup...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error in captcha handler: {e}")
            return False

    async def _warmup_generic(self, marketplace, config):
        """Універсальна логіка warmup для будь-якої платформи з Interruptions"""
        self.proxy_manager.load_proxies()
        all_proxies = self.proxy_manager.get_all_proxies()
        
        if not all_proxies:
            logger.error("❌ No proxies available")
            return False
        
        selected_proxies = random.sample(all_proxies, min(100, len(all_proxies)))
        
        async with async_playwright() as p:
            for proxy_dict in selected_proxies:
                proxy_config = {"server": proxy_dict['server']}
                if proxy_dict.get('username'):
                    proxy_config['username'] = proxy_dict['username']
                    proxy_config['password'] = proxy_dict.get('password')
                
                logger.info(f"🚀 Trying proxy: {proxy_dict['server']}")
                
                try:
                    browser = await p.chromium.launch(
                        headless=False,
                        proxy=proxy_config,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US',
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    )
                    
                    # Stealth
                    try:
                        from playwright_stealth import Stealth
                        stealth = Stealth()
                        page = await context.new_page()
                        if marketplace != 'shein':
                            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", lambda route: route.abort())
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
                    
                    # 2. Navigation with CAPTCHA CHECK
                    logger.info(f"🎯 Navigating to {marketplace}...")
                    try:
                        await page.goto(config['target'], timeout=30000)
                    except:
                        logger.warning("Main page timeout, but trying to continue...")

                    await asyncio.sleep(5)
                    
                    # 🔥 CHECK 1: After initial load
                    if not await self.check_and_solve_captcha(page, marketplace):
                        logger.warning("⚠️ Failed to solve captcha on entry. Closing browser.")
                        await browser.close()
                        continue
                    
                    # Scroll logic
                    logger.info("📜 Scrolling...")
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 300)")
                        await asyncio.sleep(2)
                        # 🔥 CHECK 2: During scroll
                        if not await self.check_and_solve_captcha(page, marketplace):
                            break
                    
                    # 🔥 ADDITIONAL WARM-UP PRODUCTS
                    logger.info("🔥 Visiting products...")
                    selected_warmup = random.sample(
                        config['warmup_products'], 
                        min(3, len(config['warmup_products']))
                    )
                    
                    for idx, warmup_url in enumerate(selected_warmup, 1):
                        try:
                            # 🔥 CHECK 3: Before visiting product
                            if not await self.check_and_solve_captcha(page, marketplace):
                                logger.warning("Captcha blocking warmup. Stopping.")
                                break
                                
                            logger.info(f"  [{idx}] Visiting product...")
                            await page.goto(warmup_url, timeout=30000)
                            await asyncio.sleep(5)
                            
                            # 🔥 CHECK 4: On product page
                            if not await self.check_and_solve_captcha(page, marketplace):
                                break
                                
                            await page.evaluate("window.scrollBy(0, 500)")
                            await asyncio.sleep(3)
                            
                        except Exception as e:
                            logger.warning(f"  Error on product: {e}")
                            continue

                    # Success - save cookies
                    logger.info("✅ Warmup cycle finished.")
                    await context.storage_state(path=config['cookie_file'])
                    
                    proxy_data = {
                        'server': proxy_dict['server'],
                        'username': proxy_dict.get('username'),
                        'password': proxy_dict.get('password')
                    }
                    with open(config['proxy_file'], 'w') as f:
                        json.dump(proxy_data, f, indent=2)
                        
                    logger.info(f"🎉 Saved session/proxy for {marketplace}")
                    await browser.close()
                    return True
                    
                except Exception as e:
                    logger.error(f"❌ Proxy failed: {e}")
                    try: await browser.close()
                    except: pass
                    continue
            
            return False
    
    async def warmup_shein(self):
        """Warmup для Shein"""
        return await self._warmup_generic('shein', self.WARMUP_URLS['shein'])
    
    async def warmup_aliexpress(self):
        """Warmup для AliExpress"""
        return await self._warmup_generic('aliexpress', self.WARMUP_URLS['aliexpress'])
    
    async def warmup_temu(self):
        """Warmup для Temu"""
        logger.warning("Temu warmup not configured")
        return False
    
    async def run_warmup(self, marketplace):
        """Запуск warmup"""
        logger.info(f"🔥 Starting warmup for {marketplace}...")
        method = getattr(self, f"warmup_{marketplace.lower()}", None)
        if not method: return False
        
        success = await method()
        if success: self.record_warmup(marketplace)
        return success
    
    async def handle_captcha(self, marketplace, force=False):
        """External usage point"""
        if force: logger.warning(f"⚠️ Force warmup for {marketplace}")
        if not force and not self.can_warmup(marketplace): return False
        return await self.run_warmup(marketplace)

    def get_stats(self, marketplace=None):
        if marketplace: return self.history.get(marketplace, {})
        return self.history

auto_warmup = AutoWarmup()
