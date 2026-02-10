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
from utils.session_manager import SessionManager
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
        self.session_manager = SessionManager()
        self.worker_ids = asyncio.Queue()
        # Initialize worker IDs (1-based)
        for i in range(1, settings.THREADS + 1):
             self.worker_ids.put_nowait(i)

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
                self.log(f"Found {len(tasks)} active tasks")
                
                if not tasks:
                    await asyncio.sleep(5)
                    continue

                # 🔥 ENABLE SMART GROUPING (Optimization: 1 page load for N variants)
                url_groups = {}
                for task in tasks:
                    # GROUP BY PRODUCT_ID (or failover to URL)
                    # This fixes the issue where different color URLs spawned multiple workers for the same product
                    p_id = task.get('product_id')
                    key = str(p_id) if p_id else task['url']
                    
                    if key not in url_groups:
                        url_groups[key] = []
                    url_groups[key].append(task)
                
                self.log(f"📦 Grouped into {len(url_groups)} unique URLs (was {len(tasks)} tasks)")

                # 3. Process groups (LIMITED concurrency to settings.THREADS)
                # RESET Worker IDs queue to match current settings
                self.worker_ids = asyncio.Queue()
                for i in range(1, settings.THREADS + 1):
                    self.worker_ids.put_nowait(i)

                semaphore = asyncio.Semaphore(settings.THREADS)
                
                async def process_group_with_limit(url, group_tasks):
                    async with semaphore:
                        worker_id = await self.worker_ids.get()
                        try:
                            await self._process_task_group(url, group_tasks, worker_id)
                        finally:
                            self.worker_ids.put_nowait(worker_id)

                # Sort groups by ID to respect order
                sorted_groups = sorted(url_groups.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0])
                
                workers = [process_group_with_limit(group[0]['url'], group) for key, group in sorted_groups]
                await asyncio.gather(*workers)
                
                # Wait before next cycle
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
        if "amazon" in url:
            marketplace = "amazon"
        # if "temu" in url:
        #     marketplace = "temu"
        if "shein" in url:
            marketplace = "shein"
        if "aliexpress" in url:
            marketplace = "aliexpress"
        
        self.log(f"INFO: Processing Product ID: {option_id}, Market: {marketplace}") # LOG 4: Start Processing

        if marketplace == "unknown":
             self.log(f"WARNING: No handler for marketplace '{marketplace}' (URL: {url}). Skipping product {option_id}.") # LOG 5: Else/Skip
             # Decide if we return or try anyway? Assuming we want to skip if unknown parser
             # But let's proceed to see if get_parser_for_url handles it or fails
             return
        
        # Increased retries for Smart Retrier (Proxy Brute-Force)
        max_retries = 10  # UPDATED per User Request: "if cookies don't pass more than 10 times"
        attempt = 0
        success = False
        status_code = 0 # Default Sold Out / Error
        status_text = "Error"
        last_error = None
        
        # Provide base status Update
        self.update_gui(str(option_id), self._get_task_display_name(task), "Pending", "Queued")

        while attempt < max_retries and self.running:
            attempt += 1
            
            # 1. STICKY PROXY & SESSION CHECK
            if marketplace in ["temu", "shein", "aliexpress"]:
                import json
                import os
                
                # Files mapping
                proxy_files = {
                    'temu': 'temu_session_proxy.json',
                    'shein': 'shein_session_proxy.json',
                    'aliexpress': 'aliexpress_session_proxy.json'
                }
                session_files = {
                    'temu': 'temu_session_state.json',
                    'shein': 'shein_session_state.json',
                    'aliexpress': 'aliexpress_session_state.json'
                }
                
                proxy_file = proxy_files[marketplace]
                session_file = session_files[marketplace]
                
                # 🔥 CRITICAL: Check if we have a valid session (cookies)
                # User request: "If we don't have cookies, maybe make them?" -> Force Warmup
                if not os.path.exists(session_file):
                    self.log(f"⚠️ Missing session cookies for {marketplace}. forcing Auto-Warmup to create them...")
                    try:
                        # Force warmup logic to generate session
                        await auto_warmup.handle_captcha(marketplace, force=True)
                        self.log(f"⏳ Waiting for warmup to generate session...")
                        await asyncio.sleep(10) # Give it a moment to sync file system
                        
                        if not os.path.exists(session_file):
                             self.log(f"❌ Warmup failed to create session file. Will try naked request.")
                        else:
                             self.log(f"✅ Session created successfully! Proceeding.")
                             # Reload potentially new proxy file if warmup rotated it
                    except Exception as e:
                        self.log(f"❌ Error during forced session creation: {e}")

                if not os.path.exists(proxy_file):
                    # AUTO-CREATE: If file missing - create with random proxy
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
                
                # Check again if we need to rotate (e.g. if forced warmup happened, we might want to ensure we use the NEW proxy)
                # If warmup ran, it likely updated the proxy file. So we should re-read it or rely on the next loop?
                # Actually, if warmup ran, we should probably RESTART the loop logic to pick up the new proxy cleanly.
                if not os.path.exists(proxy_file):
                     create_new = True 
                     
                if create_new:
                    self.log(f"🤖 Assigning NEW sticky proxy...")
                    
                    random_proxy = self.proxy_manager.get_random_proxy()
                    if random_proxy:
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
            
            self.update_gui(str(option_id), self._get_task_display_name(task), proxy_ip, f"Checking ({attempt}/{max_retries})...")
            
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
                    # Enable images for marketplaces with visual captchas (AliExpress, Temu)
                    # Shein: User requested to BLOCK images during work (Step 1412)
                    # Enable images for marketplaces with visual captchas (Temu)
                    # AliExpress: User requested to BLOCK images (Performance Mode)
                    should_block_images = True
                    if marketplace == "temu":
                        should_block_images = False
                        self.log(f"🖼️ Images ENABLED for {marketplace} (required for captcha solving)")
                    else:
                        should_block_images = True
                        self.log(f"🚫 Images BLOCKED for {marketplace} (Performance Mode)")

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
                            # Pass target variants if available (Shein smart matching)
                            target_color = task.get('target_color')
                            target_size = task.get('target_size')
                            
                            # Check if parser accepts arguments to avoid TypeError
                            if target_color or target_size:
                                try:
                                    result = await parser.parse(target_color=target_color, target_size=target_size)
                                except TypeError:
                                    # Fallback for parsers that haven't been updated yet
                                    self.log(f"⚠️ Parser {type(parser).__name__} does not support variant args. Using default parse.")
                                    result = await parser.parse()
                            else:
                                result = await parser.parse()
                        
                        # If we got here, success
                        status_code = result
                        status_text = "In Stock" if status_code == 1 else "Sold Out"
                        success = True
                        
                        # 🔥 SAVE SESSION ("Appetite" Save Point)
                        # Save cookies/storage after successful navigation
                        try:
                            await parser.save_session()
                        except Exception as save_e:
                            self.log(f"⚠️ Failed to save final session: {save_e}")
                        
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
                        
                        # 🔥 AMAZON EXCEPTION: FORCE ROTATION, NO WARMUP
                        if marketplace == 'amazon':
                            self.log(f"🔄 Amazon SoftBan detected. Skipping warmup, forcing PROXY ROTATION...")
                            # Clean cleanup
                            try:
                                await context.close()
                                await browser.close()
                            except: pass
                            
                            # Just 'continue' will hit the loop again, picking a NEW proxy (since Amazon doesn't use sticky session file)
                            continue

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
                                self.log(f"🔄 Restarting task with fresh session/cookies...")
                                attempt = 0 
                                continue
                                
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
            
            # 🔥 USER REQ: "If cookies don't pass more than 10 times, change everything"
            # We reached max_retries (10), so we Nuke the session/proxy to force rotation.
            if marketplace in ["shein", "temu", "aliexpress"]:
                self.log(f"⚠️ Failed {max_retries} times for {marketplace}. Nuking session & proxy to force UPDATE.")
                
                files_to_delete = []
                # Session files
                if marketplace == 'shein': files_to_delete.extend(['shein_session_state.json', 'shein_session_proxy.json'])
                elif marketplace == 'aliexpress': files_to_delete.extend(['aliexpress_session_state.json', 'aliexpress_session_proxy.json'])
                elif marketplace == 'temu': files_to_delete.extend(['temu_session_state.json', 'temu_session_proxy.json'])
                
                for f_name in files_to_delete:
                    if os.path.exists(f_name):
                        try:
                            os.remove(f_name)
                            self.log(f"   🗑️ Deleted {f_name}")
                        except Exception as del_err:
                            self.log(f"   ❌ Failed to delete {f_name}: {del_err}")

            self.log(f"Failed to check {option_id} after {max_retries} attempts.")
            await self.db.add_log_entry(option_id, 0, -1, -1, f"Check Failed: {last_error}")
            self.update_gui(str(option_id), self._get_task_display_name(task), "Failed", "Error")

        else:
            # Success (either In Stock or Sold Out found)
            table_to_update = task.get('table', 'monitored_product_options')
            await self.db.update_product_option_status(option_id, status_code, table=table_to_update)
            self.log(f"INFO: Updated status for ID {option_id} to '{status_text}' ({status_code})") # LOG 6: Success Update
            
            # We should probably fetch old status to log changes, but for now log result
            # Or only log on change? Current request: "Пише помилку в лог" (for error).
            # Let's log successful check too for history.
            log_msg = f"Checked {marketplace} - {status_text}"
            await self.db.add_log_entry(option_id, 0, -1, status_code, log_msg)
            
            self.update_gui(str(option_id), self._get_task_display_name(task), proxy_ip, status_text)

    async def _process_task_group(self, url: str, group_tasks: List[Dict], worker_id: int):
        """
        🔥 CRITICAL OPTIMIZATION: Process multiple variants of the same product in ONE browser session.
        This prevents the "machine gun" effect where 10 size variants = 10 browser launches.
        
        Args:
            url: The product URL
            group_tasks: Tasks list
            worker_id: The ID of the worker/thread (for sticky sessions)
        """
        if not self.running or not group_tasks:
            return
        
        # Intelligent delay
        start_delay = random.uniform(settings.DELAY_MIN, settings.DELAY_MAX)
        await asyncio.sleep(start_delay)
        
        # Extract marketplace from URL
        marketplace = "unknown"
        if "shein" in url.lower():
            marketplace = "shein"
        elif "aliexpress" in url.lower():
            marketplace = "aliexpress"
        elif "temu" in url.lower():
            marketplace = "temu"
        elif "amazon" in url.lower():
            marketplace = "amazon"
        
        self.log(f"📦 Processing GROUP: {len(group_tasks)} variants on {marketplace} ({url[:50]}...) [Worker {worker_id}]")
        
        if marketplace == "unknown":
            self.log(f"⚠️ Unknown marketplace for URL: {url}. Skipping group.")
            return
        
        import json
        import os

        # 1. Get Sticky Proxy File for this Thread
        proxy_file = self.session_manager.get_thread_proxy_path(marketplace, worker_id)
        
        # Load proxy if exists
        proxy = None
        proxy_data = None
        
        if os.path.exists(proxy_file):
            try:
                with open(proxy_file, 'r') as f:
                    proxy_data = json.load(f)
                proxy = {
                    'server': proxy_data['server'],
                    'username': proxy_data.get('username'),
                    'password': proxy_data.get('password')
                }
                self.log(f"🔗 [Worker {worker_id}] Using sticky proxy: {proxy['server']}")
            except Exception as e:
                self.log(f"❌ [Worker {worker_id}] Failed to load proxy: {e}")
        
        # If no sticky proxy, get new random one
        if not proxy:
            proxy = self.proxy_manager.get_random_proxy()
            if not proxy:
                self.log(f"❌ [Worker {worker_id}] No proxies available. Skipping group.")
                return
            # Save as sticky for next time
            proxy_data = {
                'server': proxy['server'],
                'username': proxy.get('username'),
                'password': proxy.get('password')
            }
            try:
                with open(proxy_file, 'w') as f:
                    json.dump(proxy_data, f, indent=2)
            except: pass

        # 2. Get Session File unique to this Proxy
        session_file = self.session_manager.get_session_path(marketplace, proxy_data)
        
        # Ensure session exists (warmup if needed)
        if not os.path.exists(session_file):
            self.log(f"⚠️ [Worker {worker_id}] Missing session {os.path.basename(session_file)}. Forcing warmup...")
            try:
                await auto_warmup.handle_captcha(
                    marketplace, 
                    force=True, 
                    proxy_data=proxy_data, 
                    session_file=session_file
                )
                await asyncio.sleep(10)
            except Exception as e:
                self.log(f"❌ Warmup failed: {e}")

        
        # Try to process the group with retry logic
        max_retries = 3
        attempt = 0
        
        while attempt < max_retries and self.running:
            attempt += 1
            self.log(f"🔄 Group attempt {attempt}/{max_retries}")
            
            try:
                # Launch browser ONCE for the entire group
                async with async_playwright() as p:
                    # Prepare session data
                    proxy_url = None
                    if proxy:
                        if proxy.get('username') and proxy.get('password'):
                            try:
                                scheme, rest = proxy['server'].split("://", 1)
                                proxy_url = f"{scheme}://{proxy['username']}:{proxy['password']}@{rest}"
                            except ValueError:
                                proxy_url = proxy['server']
                        else:
                            proxy_url = proxy['server']
                    
                    session_data = {
                        "proxy": proxy_url,
                        "user_agent": None,
                        "url": url,
                        "storage_state": session_file  # Pass the unique session file
                    }
                    
                    # Determine mobile mode and image blocking
                    use_mobile = marketplace == "temu"
                    
                    # 🔥 ENABLE IMAGES FOR SHEIN to fix broken captchas/white window
                    # Also helps with stealth as real users load images
                    should_block_images = marketplace not in ["temu", "shein", "aliexpress"] 
                    
                    is_simplified = marketplace == "aliexpress"
                    
                    # Create browser context
                    context, browser = await self.browser_manager.get_context(
                        p,
                        session_data,
                        block_resources=True,
                        mobile_mode=use_mobile,
                        block_images=should_block_images,
                        simplified=is_simplified
                    )
                    
                    page = await context.new_page()
                    
                    try:
                        # Navigate to URL ONCE
                        self.log(f"🌐 Loading {url[:60]}...")
                        
                        # Special handling for Temu (search-based)
                        if marketplace == "temu":
                            from parsers.site_parsers import get_parser_for_url
                            parser = get_parser_for_url(url, page)
                            await parser.Maps(url)
                        else:
                            await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                        
                        # Wait for page to settle
                        await asyncio.sleep(random.uniform(settings.DELAY_MIN, settings.DELAY_MAX))
                        
                        # Get parser
                        from parsers.site_parsers import get_parser_for_url
                        parser = get_parser_for_url(url, page)
                        # 3. ПАРСИНГ: SMART BATCH PROCESSING
                        
                        # Set of option_ids that have been successfully updated in this batch
                        updated_option_ids = set()
                        
                        # --- ATTLEMPT 1: BULK UPDATE via JSON-LD (Fastest) ---
                        try:
                            if hasattr(parser, 'get_availability_from_json_ld'):
                                self.log("🚀 Attempting BULK update via JSON-LD...")
                                variant_matrix = await parser.get_availability_from_json_ld()
                                
                                if variant_matrix:
                                    self.log(f"✅ JSON-LD Matrix found with {len(variant_matrix)} variants.")
                                    
                                    # Check each task against the matrix
                                    for task in group_tasks:
                                        t_color = task.get('target_color')
                                        t_size = task.get('target_size')
                                        opt_id = task['option_id']
                                        
                                        # Find status in matrix
                                        status = None
                                        
                                        # Try exact match first
                                        if (t_color, t_size) in variant_matrix:
                                            status = variant_matrix[(t_color, t_size)]
                                        else:
                                            # Fuzzy match
                                            for (c, s), st in variant_matrix.items():
                                                c_match = t_color and c.lower().strip() == t_color.lower().strip() if t_color else True
                                                
                                                if t_size:
                                                    s_item = s.lower().strip()
                                                    s_target = t_size.lower().strip()
                                                    # Strict match for short sizes
                                                    if len(s_target) <= 3 or len(s_item) <= 3:
                                                        s_match = s_item == s_target
                                                    else:
                                                        s_match = s_item == s_target or s_target in s_item
                                                else:
                                                    s_match = True

                                                if c_match and s_match:
                                                    status = st
                                                    break
                                        
                                        if status is not None:
                                            # Update DB immediately
                                            status_text = "In Stock" if status == 0 else "Sold Out"
                                            await self.db.update_product_option_status(opt_id, status, table="product_options")
                                            self.log(f"   ✅ Bulk updated {opt_id} ({t_color}/{t_size}): {status_text}")
                                            self.update_gui(str(worker_id), task, proxy['server'], status_text)
                                            updated_option_ids.add(opt_id)

                        except Exception as json_e:
                            self.log(f"⚠️ Bulk JSON-LD update failed (continuing to individual): {json_e}")

                        # --- ATTEMPT 2: INDIVIDUAL PROCESSING (Fallback for missing/complex items) ---
                        remaining_tasks = [t for t in group_tasks if t['option_id'] not in updated_option_ids]
                        
                        if remaining_tasks:
                            if updated_option_ids:
                                self.log(f"📋 Falling back to individual check for {len(remaining_tasks)} remaining items...")
                            else:
                                self.log(f"📋 JSON-LD failed/empty. Checking {len(remaining_tasks)} items individually...")

                            # 🐢 STRATEGY B: SMART DOM FALLBACK (One Click -> All Sizes)
                            dom_matrix_success = False
                            
                            # Try to get DOM matrix if we have a target color
                            target_color = remaining_tasks[0].get('target_color')
                            
                            if hasattr(parser, 'get_dom_matrix') and target_color:
                                self.log(f"📋 JSON-LD incomplete. Switching to SMART DOM scan for color '{target_color}'...")
                                dom_matrix = await parser.get_dom_matrix(target_color)
                                
                                if dom_matrix:
                                    self.log(f"✅ DOM Matrix success! Updating group...")
                                    dom_matrix_success = True
                                    
                                    for task in remaining_tasks:
                                        t_color = task.get('target_color')
                                        t_size = task.get('target_size')
                                        opt_id = task['option_id']
                                        
                                        # Default to OOS (2) if not found
                                        status = 2
                                        
                                        # Strict matching in DOM matrix
                                        if (t_color, t_size) in dom_matrix:
                                            status = dom_matrix[(t_color, t_size)]
                                        else:
                                            # Fuzzy size match specifically for this color key
                                            for (k_color, k_size), k_status in dom_matrix.items():
                                                if k_color != t_color: continue
                                                
                                                # Size matching
                                                if t_size and k_size:
                                                    if t_size.lower() == k_size.lower():
                                                        status = k_status
                                                        break
                                        
                                        status_text = "In Stock" if status == 0 else "Sold Out"
                                        await self.db.update_product_option_status(opt_id, status, table="product_options")
                                        self.log(f"   ✓ (DOM) {t_color}/{t_size} -> {status_text}")
                                        self.update_gui(str(worker_id), task, proxy['server'], status_text)

                            if not dom_matrix_success:
                                self.log(f"⚠️ DOM Matrix failed/skipped. Checking {len(remaining_tasks)} items individually...")
                                
                                for i, task in enumerate(remaining_tasks):
                                    option_id = task['option_id']
                                    target_color = task.get('target_color')
                                    target_size = task.get('target_size')
                                    
                                    self.log(f"   [{i+1}/{len(remaining_tasks)}] Processing {target_color}/{target_size}...")
                                    self.update_gui(str(worker_id), task, proxy_url, "Checking...")
                                    
                                    # Call Parse with specific target
                                    try:
                                        if target_color or target_size:
                                            result = await parser.parse(target_color=target_color, target_size=target_size)
                                        else:
                                            result = await parser.parse()
                                            
                                        status_code = result
                                        status_text = "In Stock" if status_code == 0 else "Sold Out"
                                        
                                        await self.db.update_product_option_status(option_id, status_code, table="product_options")
                                        self.log(f"   ✅ Updated {option_id}: {status_text}")
                                        self.update_gui(str(worker_id), task, proxy_url, status_text)
                                        
                                        # Human delay between variants
                                        if i < len(remaining_tasks) - 1:
                                            await asyncio.sleep(random.uniform(2, 5))
                                            
                                    except SoftBanException:
                                        # 🔥 RE-RAISE so the outer loop catches it and triggers Warmup!
                                        raise
                                    except HardBanException:
                                        raise
                                    except Exception as e:
                                        self.log(f"   ❌ Failed {option_id}: {e}")
                                        self.update_gui(str(worker_id), task, proxy_url, "Error")

                        # 🔥 SAVE SESSION
                        try:
                            await parser.save_session()
                        except: pass
                        
                        # Close browser
                        await context.close()
                        await browser.close()
                        
                        self.log(f"✅ Group processed successfully")
                        return  # Success!
                        
                    except SoftBanException as e:
                        self.log(f"🚫 SoftBan/Captcha detected: {e}")
                        await context.close()
                        await browser.close()
                        
                        # 🔥 KILL COOKIES IMMEDIATELY (as requested by user)
                        try:
                            if session_file and os.path.exists(session_file):
                                os.remove(session_file)
                                self.log(f"🗑️ Deleted compromised session file: {session_file}")
                        except: pass
                        
                        # 🔥 TRIGGER WARMUP with fresh start
                        try:
                            self.log(f"🔥 Starting Warmup for {marketplace}...")
                            self.log(f"🔥 Starting Warmup for {marketplace}...")
                            await auto_warmup.handle_captcha(
                                marketplace, 
                                force=True,
                                proxy_data=proxy_data,
                                session_file=session_file
                            )
                            self.log(f"✅ Warmup finished. Waiting 60s before retry...")
                            await asyncio.sleep(60)
                        except Exception as warmup_err:
                            self.log(f"❌ Warmup failed: {warmup_err}")
                        
                        continue  # Retry with fresh cookies (or no cookies)
                        
                    except Exception as e:
                        self.log(f"❌ Error processing group: {e}")
                        try:
                            await context.close()
                            await browser.close()
                        except:
                            pass
                        continue  # Retry
                        
            except Exception as e:
                self.log(f"❌ Fatal error in group processing: {e}")
                break
        
        self.log(f"❌ Failed to process group after {max_retries} attempts")

    def _get_task_display_name(self, task):
        """Helper to format task name for GUI"""
        title = task.get('product_title') or str(task['option_id'])
        # Truncate title if too long
        if len(title) > 40:
            title = title[:37] + "..."
            
        color = task.get('target_color')
        size = task.get('target_size')
        
        extras = []
        if color: extras.append(color)
        if size: extras.append(size)
        
        if extras:
            return f"{title} ({'/'.join(extras)})"
        return title



    def update_settings(self):
        """Reloads settings if they change during runtime (Global settings object is mutable)."""
        self.log(f"Settings Updated: Threads={settings.THREADS}, Headless={settings.HEADLESS}")

    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
        else:
            print(f"[Engine] {msg}")

    def update_gui(self, t_id, task_data, ip, status):
        if self.update_callback:
            # Pass full task data or just specific fields?
            # Let's pass (t_id, product_id, product_title/option_name, ip, status)
            # But the signature in main_window is fixed.
            # Let's change the signature there too.
            p_id = task_data.get('product_id', 'N/A')
            p_name = self._get_task_display_name(task_data)
            self.update_callback(t_id, p_id, p_name, ip, status)
