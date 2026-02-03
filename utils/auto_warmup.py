"""
Auto Warmup Module
Автоматично запускає warmup для платформ коли потрібно пройти капчу.
Має захист від нескінченних циклів та повну логіку браузерної автоматизації.
"""
import asyncio
import time
import json
import os
import random
from pathlib import Path
from playwright.async_api import async_playwright
from config.logger import setup_logger
from utils.proxy_manager import ProxyManager

logger = setup_logger("AutoWarmup")

class AutoWarmup:
    """
    Автоматичний warmup при виявленні капчі.
    Містить повну логіку warmup для кожної платформи.
    """
    
    # Файл для збереження історії warmup
    WARMUP_HISTORY_FILE = "warmup_history.json"
    
    # Ліміти (щоб не warmup-ити постійно)
    MAX_WARMUPS_PER_HOUR = 2          # Максимум 2 warmup на годину для кожної платформи
    MIN_TIME_BETWEEN_WARMUPS = 1800   # Мінімум 30 хвилин між warmup
    
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
        """
        Перевіряє чи можна warmup для платформи.
        Повертає True якщо можна, False якщо занадто рано.
        """
        now = time.time()
        
        # Отримуємо історію для цієї платформи
        if marketplace not in self.history:
            return True
        
        last_warmup_time = self.history[marketplace].get('last_warmup', 0)
        time_since_last = now - last_warmup_time
        
        # Перевіряємо мінімальний інтервал
        if time_since_last < self.MIN_TIME_BETWEEN_WARMUPS:
            remaining = self.MIN_TIME_BETWEEN_WARMUPS - time_since_last
            logger.warning(
                f"⏳ {marketplace}: Too soon for warmup. "
                f"Wait {remaining/60:.0f} more minutes."
            )
            return False
        
        # Перевіряємо ліміт за годину
        one_hour_ago = now - 3600
        warmups_last_hour = self.history[marketplace].get('warmups_last_hour', [])
        # Видаляємо старі записи
        warmups_last_hour = [t for t in warmups_last_hour if t > one_hour_ago]
        
        if len(warmups_last_hour) >= self.MAX_WARMUPS_PER_HOUR:
            logger.warning(
                f"🚫 {marketplace}: Warmup limit reached "
                f"({self.MAX_WARMUPS_PER_HOUR}/hour). Skipping."
            )
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
            # Оновлюємо останній warmup
            self.history[marketplace]['last_warmup'] = now
            
            # Додаємо до списку за годину
            one_hour_ago = now - 3600
            warmups = self.history[marketplace].get('warmups_last_hour', [])
            warmups = [t for t in warmups if t > one_hour_ago]  # Чистимо старі
            warmups.append(now)
            self.history[marketplace]['warmups_last_hour'] = warmups
            
            # Інкремент загальної кількості
            self.history[marketplace]['total_warmups'] = \
                self.history[marketplace].get('total_warmups', 0) + 1
        
        self._save_history()
    
    async def _warmup_generic(self, marketplace, config):
        """
        Універсальна логіка warmup для будь-якої платформи.
        
        Args:
            marketplace: Назва платформи (shein, aliexpress, etc.)
            config: Конфіг з URLs та файлами
            
        Returns:
            bool: True якщо успішно, False якщо помилка
        """
        # Отримуємо всі проксі та вибираємо випадкові
        all_proxies = self.proxy_manager.get_all_proxies()
        if not all_proxies:
            logger.error("❌ No proxies available")
            return False
        
        selected_proxies = random.sample(all_proxies, min(100, len(all_proxies)))
        
        async with async_playwright() as p:
            # Пробуємо проксі по черзі
            for proxy_dict in selected_proxies:
                proxy_config = {
                    "server": proxy_dict['server']
                }
                if proxy_dict.get('username'):
                    proxy_config['username'] = proxy_dict['username']
                if proxy_dict.get('password'):
                    proxy_config['password'] = proxy_dict['password']
                
                # Extract IP for display
                try:
                    display_ip = proxy_dict['server'].split('://')[-1].split(':')[0]
                except:
                    display_ip = proxy_dict['server']
                
                logger.info(f"🚀 Trying show full proxy: {proxy_dict}")
                
                try:
                    # Запускаємо браузер
                    browser = await p.chromium.launch(
                        headless=False,
                        proxy=proxy_config,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    
                    # Desktop емуляція
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US',
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                        is_mobile=False,
                        has_touch=False
                    )
                    
                    # Apply stealth if available
                    try:
                        from playwright_stealth import Stealth
                        stealth = Stealth()
                        page = await context.new_page()
                        
                        # 🚫 DISABLE IMAGES (Requested by user)
                        # Але для Shein залишаємо, бо там візуальна капча
                        if marketplace != 'shein':
                            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", lambda route: route.abort())
                        
                        await stealth.apply_stealth_async(page)
                        logger.info(f"✅ Stealth applied ({'Images allowed' if marketplace == 'shein' else 'Images blocked'})")
                    except Exception as e:
                        logger.warning(f"⚠️ Stealth warning: {e}")
                        page = await context.new_page()
                        
                        # 🚫 DISABLE IMAGES (Fallback)
                        if marketplace != 'shein':
                            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico}", lambda route: route.abort())
                    
                    # 1. Перевірка IP
                    logger.info("🕵️ Checking IP...")
                    try:
                        await page.goto("https://api.ipify.org", timeout=15000)
                        ip_text = await page.text_content("body", timeout=5000)
                        logger.info(f"✅ IP changed to: {ip_text}")
                    except Exception as e:
                        logger.warning(f"⚠️ IP check failed: {e}")
                        raise Exception("Proxy connection failed")
                    
                    # 2. Перехід на цільову сторінку
                    logger.info(f"🎯 Navigating to {marketplace}: {config['target']}")
                    logger.info("⏳ Waiting for load...")
                    
                    try:
                        await page.goto(config['target'], timeout=30000, wait_until='domcontentloaded')
                        logger.info("✅ Initial page loaded")
                    except Exception as e:
                        logger.warning(f"⚠️ Timeout: {e}")
                        raise Exception("Failed to load initial page")
                    
                    # Чекаємо редірект та стабілізацію
                    logger.info("⏳ Waiting for redirect and stabilization...")
                    await asyncio.sleep(15)
                    
                    try:
                        await page.wait_for_load_state('networkidle', timeout=60000)
                        logger.info("✅ Real page loaded!")
                    except:
                        logger.warning("⚠️ Network didn't stabilize, but continuing...")
                    
                    await asyncio.sleep(5)
                    
                    # Інформуємо користувача
                    logger.info("=" * 60)
                    logger.warning("🛑 STOP! CHECK THE BROWSER!")
                    logger.info("=" * 60)
                    logger.info("👉 If you see captcha - solve it!")
                    logger.info("👉 If you see login - login!")
                    logger.info("👉 If everything is clean - just wait.")
                    logger.info("⏳ You have 90 seconds...")
                    logger.info("=" * 60)
                    
                    # Чекаємо 90 секунд для ручного втручання
                    await asyncio.sleep(90)
                    
                    # 🔥 ДОДАТКОВИЙ WARM-UP: відвідуємо продукти
                    logger.info("=" * 60)
                    logger.info("🔥 ADDITIONAL WARM-UP: Visiting products...")
                    logger.info("=" * 60)
                    logger.warning("⚠️ If captcha appears during warm-up - solve it!")
                    logger.info("   Script waits 15 sec on each page\n")
                    
                    # Випадково вибираємо 3 продукти
                    selected_warmup = random.sample(
                        config['warmup_products'], 
                        min(3, len(config['warmup_products']))
                    )
                    
                    for idx, warmup_url in enumerate(selected_warmup, 1):
                        try:
                            logger.info(f"  [{idx}/{len(selected_warmup)}] Visiting: {warmup_url[:60]}...")
                            await page.goto(warmup_url, timeout=30000, wait_until='domcontentloaded')
                            
                            # Чекаємо 8 секунд
                            await asyncio.sleep(8)
                            
                            # Скролимо для природності
                            try:
                                await page.evaluate("window.scrollBy(0, 500)")
                                await asyncio.sleep(2)
                                await page.evaluate("window.scrollBy(0, 500)")
                                await asyncio.sleep(2)
                            except:
                                pass
                            
                            # Ще 5 секунд на можливу капчу
                            await asyncio.sleep(5)
                            
                            logger.info(f"  ✅ Product {idx} processed")
                        except Exception as e:
                            logger.warning(f"  ⚠️ Error on product {idx}: {e}")
                            await asyncio.sleep(10)
                            continue
                    
                    logger.info("=" * 60)
                    logger.info("✅ Warm-up complete!")
                    logger.info("=" * 60)
                    
                    # 3. Зберігаємо результат
                    logger.info(f"💾 Saving cookies to {config['cookie_file']}...")
                    await context.storage_state(path=config['cookie_file'])
                    
                    # Зберігаємо proxy для sticky session
                    proxy_data = {
                        'server': proxy_dict['server'],
                        'username': proxy_dict.get('username'),
                        'password': proxy_dict.get('password')
                    }
                    try:
                        with open(config['proxy_file'], 'w') as f:
                            json.dump(proxy_data, f, indent=2)
                        logger.info(f"🔗 Saved sticky proxy to {config['proxy_file']}")
                        logger.info(f"   IP: {display_ip}")
                        logger.warning("   ⚠️ Production must use THE SAME proxy!")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to save proxy: {e}")
                    
                    logger.info("=" * 60)
                    logger.info("🎉 DONE! Files created.")
                    logger.info("=" * 60)
                    logger.info(f"📁 Cookies: {config['cookie_file']}")
                    logger.info(f"🔗 Proxy: {config['proxy_file']}")
                    logger.info("Bot can now work without captcha for some time.")
                    logger.info("=" * 60)
                    
                    await browser.close()
                    return True
                    
                except Exception as e:
                    logger.error(f"❌ This proxy didn't work: {e}")
                    logger.info("Trying next proxy...\n")
                    try:
                        await browser.close()
                    except:
                        pass
                    continue
            
            logger.warning("\n⚠️ All proxies tested. If files not created - try other proxies.")
            return False
    
    async def warmup_shein(self):
        """Warmup для Shein"""
        logger.info("🔥 Starting SHEIN warmup...")
        config = self.WARMUP_URLS['shein']
        return await self._warmup_generic('shein', config)
    
    async def warmup_aliexpress(self):
        """Warmup для AliExpress"""
        logger.info("🔥 Starting ALIEXPRESS warmup...")
        config = self.WARMUP_URLS['aliexpress']
        return await self._warmup_generic('aliexpress', config)
    
    async def warmup_temu(self):
        """Warmup для Temu (якщо потрібно)"""
        logger.warning("⚠️ Temu warmup not implemented yet")
        return False
    
    async def run_warmup(self, marketplace):
        """
        Запускає warmup для платформи.
        Повертає True якщо успішно, False якщо помилка.
        """
        logger.info(f"🔥 Starting warmup for {marketplace}...")
        
        # Викликаємо відповідний метод
        warmup_method = {
            'shein': self.warmup_shein,
            'aliexpress': self.warmup_aliexpress,
            'temu': self.warmup_temu
        }.get(marketplace.lower())
        
        if not warmup_method:
            logger.error(f"❌ No warmup method for {marketplace}")
            return False
        
        try:
            success = await warmup_method()
            
            if success:
                # Записуємо в історію
                self.record_warmup(marketplace)
                logger.info(f"✅ Warmup completed for {marketplace}")
            else:
                logger.error(f"❌ Warmup failed for {marketplace}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Warmup error for {marketplace}: {e}")
            return False
    
    async def handle_captcha(self, marketplace, force=False):
        """
        Обробляє ситуацію з капчею.
        Головна точка входу для auto-warmup.
        
        Args:
            marketplace: Назва платформи
            force: Якщо True - ігнорує ліміти (для critical captchas)
        
        Returns:
            bool: True якщо warmup запущено, False якщо ні
        """
        logger.warning(f"🚫 CAPTCHA DETECTED on {marketplace}")
        
        # Якщо force - логуємо це
        if force:
            logger.warning(f"⚠️ FORCE WARMUP for {marketplace} (critical captcha - bypassing limits)")
        else:
            logger.info(f"🤖 Auto-warmup available for {marketplace}")
        
        # Запускаємо warmup
        success = await self.run_warmup(marketplace)
        
        if success:
            logger.info(f"✅ Auto-warmup completed for {marketplace}")
        else:
            logger.error(f"❌ Auto-warmup failed for {marketplace}")
        
        return success
    
    def get_stats(self, marketplace=None):
        """Отримує статистику warmup"""
        if marketplace:
            return self.history.get(marketplace, {})
        return self.history

# Глобальний інстанс
auto_warmup = AutoWarmup()
