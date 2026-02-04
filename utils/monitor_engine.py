import asyncio
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime
import random
from playwright.async_api import async_playwright

from database.db_manager import DatabaseManager
from utils.proxy_manager import ProxyManager
from utils.browser import BrowserManager
from utils.auto_warmup import auto_warmup
from config.settings import settings
from parsers.site_parsers import get_parser_for_url
from parsers.exceptions import SoftBanException, HardBanException

logger = logging.getLogger("MonitorEngine")

class MonitorEngine:
    def __init__(self, update_callback=None, log_callback=None):
        self.running = False
        self.db = DatabaseManager()
        self.proxy_manager = ProxyManager()
        self.browser_manager = BrowserManager()
        self.update_callback = update_callback 
        self.log_callback = log_callback       
        self.tasks = []
        self.loop_task = None

    async def start(self):
        """Starts the monitoring loop."""
        if self.running:
            return
        
        self.running = True
        self.log("🚀 Monitor Engine Started")
        
        # DB pool is already initialized by main.py, just ensure we have it
        await self.db.get_pool()
        
        # Start the main loop
        self.loop_task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stops the monitoring loop."""
        self.running = False
        self.log("🛑 Monitor Engine Stopping...")
        if self.loop_task:
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass
        
        # Close DB
        await self.db.close()
        self.log("✅ Engine Stopped")

    async def _run_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                # 1. Fetch Active Tasks
                self.log("Fetching active tasks from DB...")
                tasks = await self.db.fetch_active_products()
                
                # 2. PLATFORM FILTER (Kill Switch Logic)
                # Silently exclude disabled platforms without logging
                filtered_tasks = []
                for task in tasks:
                    url = task.get('url', '').lower()
                    
                    # Determine marketplace
                    if 'temu.com' in url and not settings.ENABLE_TEMU:
                        continue  # Skip Temu silently
                    elif 'shein.com' in url and not settings.ENABLE_SHEIN:
                        continue  # Skip Shein silently
                    elif 'aliexpress.com' in url and not settings.ENABLE_ALIEXPRESS:
                        continue  # Skip AliExpress silently
                    
                    # Task passed filter
                    filtered_tasks.append(task)
                
                tasks = filtered_tasks
                self.log(f"Found {len(tasks)} active tasks (after platform filter).")
                
                if not tasks:
                    await asyncio.sleep(5)
                    continue

                # 3. Process Batch (LIMITED concurrently to settings.THREADS)
                semaphore = asyncio.Semaphore(settings.THREADS)
                
                async def process_with_limit(task):
                    async with semaphore:
                        await self._process_task(task)

                workers = [process_with_limit(t) for t in tasks]
                await asyncio.gather(*workers)
                
                # Wait before next cycle if needed, or if we want continuous scraping
                # settings.DELAY_MIN is usually for inter-check delay. 
                # Since we processed all tasks, we should wait a bit.
                self.log(f"Batch finished. Waiting {settings.DELAY_MIN}s...")
                await asyncio.sleep(settings.DELAY_MIN)

            except Exception as e:
                self.log(f"Error in main loop: {e}")
                await asyncio.sleep(5)

    async def _process_task(self, task):
        """
        Processes a single task with retry logic.
        """
        if not self.running: return

        # Intelligent Delay to prevent "Machine Gun" effect
        # Sleep BEFORE doing anything with this task
        start_delay = random.uniform(settings.DELAY_MIN, settings.DELAY_MAX)
        # self.log(f"Delaying {start_delay:.2f}s for {task['option_id']}...") # Optional verbose log
        await asyncio.sleep(start_delay)

        option_id = task['option_id']
        url = task['url']
        
        # Оскільки в базі немає marketplace, визначаємо його для логів з URL
        marketplace = "unknown"
        # if "amazon" in url:
        #     marketplace = "amazon"
        # if "temu" in url:
        #     marketplace = "temu"
        if "shein" in url:
            marketplace = "shein"
        # if "aliexpress" in url:
        #     marketplace = "aliexpress"
        
        self.log(f"INFO: Processing Product ID: {option_id}, Market: {marketplace}") # LOG 4: Start Processing

        if marketplace == "unknown":
             self.log(f"WARNING: No handler for marketplace '{marketplace}' (URL: {url}). Skipping product {option_id}.") # LOG 5: Else/Skip
             # Decide if we return or try anyway? Assuming we want to skip if unknown parser
             # But let's proceed to see if get_parser_for_url handles it or fails
             return
        
        # Increased retries for Smart Retrier (Proxy Brute-Force)
        max_retries = 10 if marketplace in ["shein", "temu"] else 3
        attempt = 0
        success = False
        status_code = 0 # Default Sold Out / Error
        status_text = "Error"
        last_error = None
        
        # Provide base status Update
        self.update_gui(str(option_id), str(option_id), "Pending", "Queued")

        while attempt < max_retries and self.running:
            attempt += 1
            
            # БЛОК 1: STICKY PROXY для Temu (ОБОВ'ЯЗКОВО!)
            # Якщо це Temu - ОБОВ'ЯЗКОВО використовувати прив'язаний проксі
            if marketplace in ["temu", "shein", "aliexpress"]:
                import json
                import os
                # Для кожної платформи свій файл
                proxy_files = {
                    'temu': 'temu_session_proxy.json',
                    'shein': 'shein_session_proxy.json',
                    'aliexpress': 'aliexpress_session_proxy.json'
                }
                proxy_file = proxy_files[marketplace]
                
                if not os.path.exists(proxy_file):
                    # AUTO-CREATE: Якщо файлу немає - створюємо автоматично з випадковим proxy
                    self.log(f"⚠️ {marketplace.upper()} sticky proxy file not found: {proxy_file}")
                    create_new = True
                else:
                    try:
                        with open(proxy_file, 'r') as f:
                            sticky_data = json.load(f)
                        
                        # Check if this proxy is blacklisted
                        if sticky_data['server'] in self.proxy_manager.blacklisted_proxies:
                            self.log(f"🚫 Sticky proxy {sticky_data['server']} is BLACKLISTED. Rotating...")
                            create_new = True
                        else:
                            proxy = {
                                'server': sticky_data['server'],
                                'username': sticky_data.get('username'),
                                'password': sticky_data.get('password')
                            }
                            self.log(f"🔗 Using STICKY proxy for {marketplace}: {sticky_data['server']}")
                            create_new = False
                    except Exception as e:
                        self.log(f"❌ Failed to load {marketplace} sticky proxy: {e}")
                        create_new = True

                if create_new:
                    self.log(f"🤖 Assigning NEW sticky proxy...")
                    
                    # Беремо випадковий proxy (blacklist-aware)
                    random_proxy = self.proxy_manager.get_random_proxy()
                    if random_proxy:
                        # Зберігаємо як sticky proxy
                        proxy_data = {
                            'server': random_proxy['server'],
                            'username': random_proxy.get('username'),
                            'password': random_proxy.get('password')
                        }
                        try:
                            with open(proxy_file, 'w') as f:
                                json.dump(proxy_data, f, indent=2)
                            self.log(f"✅ Updated {proxy_file} with: {random_proxy['server']}")
                            proxy = random_proxy
                        except Exception as create_err:
                            self.log(f"❌ Failed to create proxy file: {create_err}")
                            proxy = random_proxy
                    else:
                        self.log(f"❌ No proxies available!")
                        proxy = None
            else:
                # Для інших маркетплейсів - випадковий проксі
                proxy = self.proxy_manager.get_random_proxy()
            
            if proxy:
                # Extract IP for display
                server = proxy.get('server', 'unknown')
                username = proxy.get('username', '')
                # Parse IP from server (format: http://ip:port)
                try:
                    proxy_ip = server.split('://')[-1].split(':')[0] if '://' in server else server.split(':')[0]
                    if username:
                        proxy_display = f"{proxy_ip} (user: {username[:8]}...)"
                    else:
                        proxy_display = f"{proxy_ip}"
                except:
                    proxy_display = server
            else:
                proxy_ip = "Direct"
                proxy_display = "No Proxy (Direct)"
            
            # ALWAYS log proxy for verification (critical for debugging)
            self.log(f"🔄 Attempt {attempt}/{max_retries} | Proxy: {proxy_display}")
            
            self.update_gui(str(option_id), str(option_id), proxy_ip, f"Checking ({attempt}/{max_retries})...")
            
            # Prepare Session Data for Browser
            proxy_url = None
            if proxy:
                if proxy.get('username') and proxy.get('password'):
                    # Construct http://user:pass@ip:port
                    # proxy['server'] is http://ip:port
                    try:
                        scheme, rest = proxy['server'].split("://", 1)
                        proxy_url = f"{scheme}://{proxy['username']}:{proxy['password']}@{rest}"
                    except ValueError:
                        # Fallback if server format is unexpected
                        proxy_url = proxy['server']
                else:
                    proxy_url = proxy['server']

            session_data = {
                "proxy": proxy_url,
                "user_agent": None, # Random will be picked
                "url": url  # For auto-detecting saved session files
            }

            try:
                async with async_playwright() as p:
                    # 1. ВИПРАВЛЕННЯ: Вмикаємо мобільний режим ТІЛЬКИ для Temu
                    # Shein працює на DESKTOP (як AliExpress)
                    use_mobile = marketplace == "temu"
                    
                    # Launch Browser with resource blocking
                    # Enable images for marketplaces with visual captchas (AliExpress, Shein, Temu)
                    should_block_images = True
                    if marketplace in ["aliexpress", "shein", "temu"]:
                        should_block_images = False
                        self.log(f"🖼️ Images ENABLED for {marketplace} (required for captcha solving)")

                    # Simplified mode for AliExpress (mimic user's script)
                    is_simplified = marketplace == "aliexpress"

                    context, browser = await self.browser_manager.get_context(
                        p, 
                        session_data, 
                        block_resources=True,
                        mobile_mode=use_mobile,
                        block_images=should_block_images,
                        simplified=is_simplified
                    )
                    
                    if use_mobile:
                        self.log(f"📱 Using mobile mode for {marketplace}")
                    else:
                        self.log(f"🖥️ Using desktop mode for {marketplace}")
                    
                    try:
                        page = await context.new_page()
                        
                        # Delay after opening tab
                        await asyncio.sleep(random.uniform(1, 2))
                        
                        # 🌍 RUNTIME LOCATION CHECK (User Request)
                        # Verify we are actually in US before proceeding
                        if proxy:
                            try:
                                self.log("🌍 Verifying proxy location via ip-api.com...")
                                # Fast check, strict timeout
                                check_response = await page.goto("http://ip-api.com/json", wait_until='domcontentloaded', timeout=10000)
                                if check_response:
                                    # Parse JSON content from body pre element or just text
                                    content = await page.content()
                                    if "countryCode" in content:
                                        # Simple string check or parse
                                        import json
                                        # content is html usually, let's get text
                                        text = await page.evaluate("document.body.innerText")
                                        try:
                                            geo_data = json.loads(text)
                                            country = geo_data.get('countryCode')
                                            if country != 'US':
                                                self.log(f"🚫 PROXY ERROR: Location is {country}, expected US. Rotating...")
                                                raise HardBanException(f"Wrong Country: {country}")
                                            else:
                                                self.log(f"✅ Proxy Location Verified: {country}")
                                        except json.JSONDecodeError:
                                            pass # If unexpected format, skip check to be safe/lenient
                                    else:
                                        pass
                            except HardBanException:
                                raise # Propagate to rotate
                            except Exception as e:
                                self.log(f"⚠️ Location check warning: {e}")
                                # Don't block flow if check fails, but log it
                        
                        # Apply stealth to this page (critical for Shein/Temu)
                        # SKIP for simplified mode (AliExpress uses standard browser)
                        if not is_simplified:
                            try:
                                try:
                                    from playwright_stealth import stealth_async
                                    await stealth_async(page)
                                except ImportError:
                                    # playwright-stealth 2.0.1+
                                    from playwright_stealth import Stealth
                                    stealth = Stealth()
                                    await stealth.apply_stealth_async(page)
                            except Exception as e:
                                self.log(f"⚠️ Stealth warning: {e}")

                        # 2. БЛОК 2 & 3: Human Search Flow + Robust Selectors
                        if marketplace == "temu":
                            # Helper function: Check for security challenges
                            async def check_security_verification():
                                """Перевіряє наявність капчі/бану на поточній сторінці"""
                                security_indicators = [
                                    "text='Verify you are human'",
                                    "text='Security verification'",
                                    "text='Security check'",
                                    "text='Access Denied'",
                                    "text='Unusual activity'",
                                    "#captcha",
                                    "iframe[src*='captcha']",
                                    "div[class*='captcha']",
                                    ".security-verify",
                                    "text='Please verify'"
                                ]
                                
                                for indicator in security_indicators:
                                    try:
                                        if indicator.startswith("text="):
                                            text = indicator.replace("text=", "").strip("'\"")
                                            if await page.locator(f"text='{text}'").count() > 0:
                                                self.log(f"🚫 Security Challenge: {text}")
                                                raise SoftBanException(f"Security verification required: {text}")
                                        else:
                                            if await page.locator(indicator).count() > 0:
                                                self.log(f"🚫 Security Challenge: {indicator}")
                                                raise SoftBanException(f"Security verification required: {indicator}")
                                    except SoftBanException:
                                        raise
                                    except:
                                        continue
                            
                            # КРОК 1: ВИБІР СТРАТЕГІЇ (ДО навігації!)
                            has_goods_id = "goods_id=" in url or "goods.html" in url
                            
                            if has_goods_id:
                                # ═══════════════════════════════════════════════════════════
                                # СТРАТЕГІЯ 1: ПРЯМИЙ ПЕРЕХІД (для URLs з goods_id)
                                # ═══════════════════════════════════════════════════════════
                                self.log("🔗 Direct Navigation: URL contains goods_id")
                                self.log(f"   📍 Target: {url}")
                                
                                # Встановлюємо Google Referer (як людина з пошуку)
                                await page.set_extra_http_headers({
                                    "Referer": "https://www.google.com/"
                                })
                                
                                # Йдемо ПРЯМО на товар (БЕЗ головної!)
                                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                                await asyncio.sleep(random.uniform(2, 4))
                                
                                # Перевірка безпеки
                                await check_security_verification()
                                
                                # Закриваємо попапи
                                try:
                                    self.log("   🔨 Closing popups...")
                                    close_btns = page.locator(
                                        "button[aria-label='Close'], "
                                        ".ps-btn-close, "
                                        "text='NO THANKS'"
                                    )
                                    count = await close_btns.count()
                                    if count > 0:
                                        for i in range(min(count, 3)):
                                            try:
                                                await close_btns.nth(i).click(timeout=1000)
                                                await asyncio.sleep(0.5)
                                            except:
                                                pass
                                except:
                                    pass
                                
                                self.log("   ✅ Product page loaded directly")
                                
                            else:
                                # ═══════════════════════════════════════════════════════════
                                # СТРАТЕГІЯ 2: ПОШУК (ТІЛЬКИ якщо немає goods_id)
                                # ═══════════════════════════════════════════════════════════
                                self.log("🔍 Search Strategy: No goods_id in URL")
                                
                                # Йдемо на головну
                                await page.set_extra_http_headers({
                                    "Referer": "https://www.google.com/"
                                })
                                await page.goto("https://m.temu.com", wait_until='domcontentloaded', timeout=30000)
                                await asyncio.sleep(random.uniform(2, 4))
                                
                                # Перевірка безпеки
                                await check_security_verification()
                                
                                # Витягуємо ID для пошуку
                                product_id = str(option_id)
                                self.log(f"   🔎 Searching for: {product_id}")
                                
                                # Закриваємо попапи
                                try:
                                    close_btns = page.locator(
                                        "button[aria-label='Close'], "
                                        ".ps-btn-close, "
                                        "text='NO THANKS'"
                                    )
                                    count = await close_btns.count()
                                    if count > 0:
                                        for i in range(min(count, 3)):
                                            try:
                                                await close_btns.nth(i).click(timeout=1000)
                                                await asyncio.sleep(0.5)
                                            except:
                                                pass
                                except:
                                    pass
                                
                                # Клік по кнопці пошуку
                                search_button_selectors = [
                                    "button[aria-label*='Search' i]",
                                    "div[role='button'][aria-label*='Search' i]",
                                    "header button:has-text('Search')",
                                    "div[class*='searchBar']:not(input)"
                                ]
                                
                                search_opened = False
                                for sel in search_button_selectors:
                                    try:
                                        btn = page.locator(sel).first
                                        if await btn.is_visible(timeout=1500):
                                            self.log(f"   👆 Opening search: {sel}")
                                            await btn.click()
                                            search_opened = True
                                            await asyncio.sleep(1.5)
                                            break
                                    except:
                                        continue
                                
                                # Вводимо в input
                                input_selectors = [
                                    "dialog input[type='search']",
                                    "div[role='dialog'] input[type='search']",
                                    "input[type='search']:visible"
                                ]
                                
                                input_found = False
                                for inp_sel in input_selectors:
                                    try:
                                        search_input = page.locator(inp_sel).first
                                        if await search_input.is_visible(timeout=1500):
                                            self.log(f"   ⌨️ Typing: {product_id}")
                                            await search_input.click()
                                            await asyncio.sleep(0.3)
                                            await search_input.fill(product_id)
                                            await asyncio.sleep(0.5)
                                            await page.keyboard.press("Enter")
                                            input_found = True
                                            await asyncio.sleep(random.uniform(3, 5))
                                            break
                                    except:
                                        continue
                                
                                if not input_found:
                                    raise Exception(f"Search input not found for product {product_id}")
                                
                                # Перевірка безпеки після пошуку
                                await check_security_verification()
                                
                                # Клікаємо на першу картку результату
                                current_url = page.url
                                if "goods.html" not in current_url:
                                    self.log("   👉 Clicking first result...")
                                    
                                    card_selectors = [
                                        "[data-goods-id]",
                                        "a[href*='goods.html']"
                                    ]
                                    
                                    clicked = False
                                    for card_sel in card_selectors:
                                        try:
                                            cards = page.locator(card_sel)
                                            if await cards.count() > 0:
                                                await cards.first.click()
                                                await asyncio.sleep(3)
                                                clicked = True
                                                break
                                        except:
                                            continue
                                    
                                    if not clicked:
                                        raise Exception(f"Product {product_id} not found in search results")
                                    
                                    # Перевірка безпеки після кліку
                                    await check_security_verification()
                            
                            await asyncio.sleep(random.uniform(1, 2))
                        
                        # Для інших маркетплейсів (Shein) - звичайна навігація
                        else:
                            parser = get_parser_for_url(url, page)
                            await parser.Maps(url)
                            
                            # CRITICAL: Wait for page to "settle" / render dynamic content
                            load_wait = random.uniform(settings.DELAY_MIN, settings.DELAY_MAX)
                            await asyncio.sleep(load_wait)

                        # 3. ПАРСИНГ
                        # Тепер ми ВЖЕ на сторінці товару, викликаємо парсер
                        parser = get_parser_for_url(url, page)
                        
                        # Parse (for Temu, we're already on the page after search navigation)
                        if marketplace == "temu":
                            # Парсер просто парсить поточну сторінку, original_url для логів
                            result = await parser.parse(original_url=url)
                        else:
                            result = await parser.parse()
                        
                        # If we got here, success
                        status_code = result
                        status_text = "In Stock" if status_code == 1 else "Sold Out"
                        success = True
                        
                        # Extra delay for Temu to avoid rate limiting
                        if marketplace == "temu":
                            temu_cooldown = random.uniform(5, 8)
                            self.log(f"⏳ Temu cooldown: {temu_cooldown:.1f}s")
                            await asyncio.sleep(temu_cooldown)
                        
                        # Close explicit (async context manager handles it too but to be safe/fast)
                        await context.close()
                        await browser.close()
                        break 

                    except SoftBanException as e:
                        self.log(f"🚫 SoftBan/Captcha for {option_id}: {e}")
                        last_error = f"Captcha: {e}"
                        
                        # 🔥 ВИКОНУЄМО ВИМОГУ КОРИСТУВАЧА: "ЗРАЗУ ЗАКРИВАЄМО І АВТОАВАРМ UP"
                        # Вважаємо будь-яку SoftBan помилку сигналом для негайного Warmup
                        self.log(f"🚨 CAPTCHA DETECTED! Stopping attempts and forcing Auto-Warmup...")
                        
                        # 1. Запускаємо Auto-Warmup (force=True щоб ігнорувати ліміти)
                        try:
                            warmup_triggered = await auto_warmup.handle_captcha(
                                marketplace, 
                                force=True  # ⚠️ FORCE: User wants immediate action regardless of history
                            )
                            
                            if warmup_triggered:
                                self.log(f"✅ Auto-warmup initiated for {marketplace}")
                                self.log(f"⏳ Waiting 90s for warmup to complete...")
                                await asyncio.sleep(90) # Чекаємо поки скрипт відпрацює
                            else:
                                self.log(f"❌ Auto-warmup failed to start (check logs). Cooling down 60s...")
                                await asyncio.sleep(60)
                                
                        except Exception as warmup_error:
                            self.log(f"❌ Critical Auto-warmup error: {warmup_error}")
                        
                        # 2. Видаляємо старі сесії (вони вже не робочі)
                        session_files = {
                            'shein': 'shein_session_state.json',
                            'aliexpress': 'aliexpress_session_state.json',
                            'temu': 'temu_session_state.json'
                        }
                        session_file = session_files.get(marketplace)
                        if session_file and os.path.exists(session_file):
                            try:
                                os.remove(session_file)
                                self.log(f"🗑️ Deleted compromised session: {session_file}")
                            except: pass
                            
                        # 3. НЕГАЙНО ВИХОДИМО з циклу спроб для ЦЬОГО товару
                        self.log(f"🛑 Breaking retry loop for current task")
                        
                        # Закриваємо браузер
                        try:
                            await context.close()
                            await browser.close()
                        except: pass
                        
                        break # <--- CRITICAL: Stop hammering the site


                    except HardBanException as e:
                        self.log(f"🚫 HardBan (Block) for {option_id}: {e}")
                        
                        # BLACKLIST PROXY because we got blocked
                        if session_data.get('proxy'):
                             # We can blacklist by URL or by the object if we still have it
                             # session_data['proxy'] is the URL string
                             # ProxyManager expects logic to handle this.
                             # But wait, ProxyManager.blacklist_proxy expects a dict usually? 
                             # Let's check implementation. 
                             # blacklist_proxy(self, proxy) -> checks proxy.get('server')
                             # We used `proxy` variable earlier!
                             if proxy:
                                 self.log(f"💀 Blacklisting bad proxy: {proxy.get('server')}")
                                 self.proxy_manager.blacklist_proxy(proxy)
                             
                        # Close browser
                        try:
                            await context.close()
                            await browser.close()
                        except: pass
                        
                        # Retry loop continues...
                        last_error = "HardBan"
                    except Exception as inner_e:
                        # self.log(f"Error checking {option_id}: {inner_e}")
                        last_error = str(inner_e)
                    finally:
                        await context.close()
                        await browser.close()

            except Exception as e:
                self.log(f"Browser launch error: {e}")
                last_error = str(e)
            
            # If not success, rotate proxy is implicit by calling get_next_proxy next loop
            if not success:
                retry_delay = random.uniform(settings.DELAY_MIN, settings.DELAY_MAX)
                self.log(f"Retry delay {retry_delay:.2f}s for {option_id}...")
                await asyncio.sleep(retry_delay)

        # End of Loop
        
        # Identify if we failed completely
        if not success:
            status_text = f"Fail: {last_error}" if last_error else "Failed"
            # Do NOT update status to 0 if it was failure to connect? 
            # User req: "Якщо після 3 спроб невдача -> Пише помилку в лог, але не змінює статус товару"
            # So we only update DB if success is True, OR if we result in clear "Sold Out" (which is success=True with result=0)
            # Wait, if parse() returns 0 (Sold Out), success is True.
            # If exception, success is False.
            
            self.log(f"Failed to check {option_id} after {max_retries} attempts.")
            await self.db.add_log_entry(option_id, 0, -1, -1, f"Check Failed: {last_error}")
            self.update_gui(str(option_id), str(option_id), "Failed", "Error")

        else:
            # Success (either In Stock or Sold Out found)
            await self.db.update_product_option_status(option_id, status_code)
            self.log(f"INFO: Updated status for ID {option_id} to '{status_text}' ({status_code})") # LOG 6: Success Update
            
            # We should probably fetch old status to log changes, but for now log result
            # Or only log on change? Current request: "Пише помилку в лог" (for error).
            # Let's log successful check too for history.
            log_msg = f"Checked {marketplace} - {status_text}"
            await self.db.add_log_entry(option_id, 0, -1, status_code, log_msg)
            
            self.update_gui(str(option_id), str(option_id), proxy_ip, status_text)


    def update_settings(self):
        """Reloads settings if they change during runtime (Global settings object is mutable)."""
        self.log(f"Settings Updated: Threads={settings.THREADS}, Headless={settings.HEADLESS}")

    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
        else:
            print(f"[Engine] {msg}")

    def update_gui(self, t_id, p_id, ip, status):
        if self.update_callback:
            self.update_callback(t_id, p_id, ip, status)
