from parsers.base import BaseParser
from parsers.exceptions import SoftBanException
import asyncio

class TemuParser(BaseParser):
    """
    Оптимізований парсер для Temu Mobile (m.temu.com).
    Розрахований на роботу в режимі авторизованого користувача (iPhone emulation).
    """

    # Тригери, які означають, що акаунт "вилетів", забанений або вимагає перевірки
    BAN_TRIGGERS = [
        # Captcha/Security Challenges
        "text='Verify you are human'",
        "text='Security Check'",
        "text='Security verification'",
        "text='Please verify'",
        "text='Unusual activity'",
        "#captcha",
        "iframe[src*='captcha']",
        "div[class*='captcha']",
        ".security-verify",
        # Ban messages
        "text='Access Denied'",
        "text='System is busy'",
        # Специфічні для логіну (якщо сесія злетіла)
        "text='Login to continue'",
        "text='Sign in / Register'", 
        ".login-container",
        "#login_close"
    ]
    
    def extract_product_name_from_url(self, url):
        """Зберігаємо допоміжний метод для сумісності"""
        try:
            if 'temu.com/' in url:
                path = url.split('temu.com/')[-1]
            else:
                path = url
            if path.endswith('.html'):
                path = path[:-5]
            if '-g-' in path:
                product_slug = path.split('-g-')[0]
            else:
                product_slug = path
            return product_slug.replace('-', ' ').strip()
        except:
            return None

    async def check_for_ban(self):
        """
        Перевіряє, чи не викинуло нас з акаунту або чи не дали капчу.
        """
        try:
            current_url = self.page.url
            
            # 1. Перевірка на редірект логіну (Смерть сесії)
            if "login.html" in current_url or "login/index" in current_url:
                self.logger.warning(f"🚫 Redirected to Login Page: {current_url}")
                raise SoftBanException("Session Expired: Redirected to Login")

            # 2. Перевірка на стандартні бани
            for trigger in self.BAN_TRIGGERS:
                try:
                    if trigger.startswith("text="):
                        text = trigger.replace("text=", "").strip("'\"")
                        if await self.page.locator(f"text='{text}'").first.is_visible(timeout=100):
                            self.logger.warning(f"🚫 Ban Trigger: {text}")
                            raise SoftBanException(f"Ban Detected: {text}")
                    else:
                        if await self.page.locator(trigger).first.is_visible(timeout=100):
                            self.logger.warning(f"🚫 Ban Trigger: {trigger}")
                            raise SoftBanException(f"Ban Detected: {trigger}")
                except Exception as e:
                    if "SoftBanException" in str(type(e).__name__): raise e
                    continue
        except SoftBanException:
            raise
        except Exception:
            pass 

    async def close_popups(self):
        """
        Закриває набридливі попапи для залогінених (Купони, додаток, спіннери).
        """
        close_selectors = [
            "div[role='button']:has(svg)",  # Універсальні хрестики
            "div[data-action='close']",     # Стандартний Temu close
            ".ps-btn-close",                # Popup close
            "button[aria-label='Close']",
            "text='NO THANKS'",
            "text='No thanks'",
            "text='Maybe later'",
            ".un-draw-mask",                # Маска купонів
            "#mess-close",
            "div[class*='close-btn']"
        ]
        
        for sel in close_selectors:
            try:
                locator = self.page.locator(sel).first
                if await locator.is_visible(timeout=200):
                    self.logger.info(f"🔨 Closing popup: {sel}")
                    await locator.click()
                    await asyncio.sleep(0.5)
            except:
                continue

    async def parse(self, original_url=None):
        """
        Основний метод парсингу.
        """
        try:
            # 1. Швидка перевірка: чи ми все ще залогінені/не забанені (Temu-specific)
            await self.check_for_ban()
            
            #1.1. Перевірка на generic captchas (from BaseParser)
            await self.check_for_captcha()
            
            # 2. Чистимо екран від купонів
            await self.close_popups()
            
            # 2.5. Re-check for captchas after popup closing
            await self.check_for_captcha()
            
            # 3. Чекаємо завантаження важливих елементів (ціна або статус)
            try:
                # Чекаємо або ціни, або повідомлення про sold out
                await self.page.wait_for_selector("text=$", timeout=5000)
            except:
                pass # Якщо не дочекалися, перевіримо sold out нижче

            # 4. ПЕРЕВІРКА: SOLD OUT (Немає в наявності)
            sold_out_indicators = [
                "text='Sold Out'",
                "text='SOLD OUT'",
                "text='Out of stock'",
                "text='Discontinued'",
                "text='Item unavailable'",
                "button[disabled]:has-text('Add to Cart')",
                "div:has-text('This item is currently unavailable')"
            ]
            
            for ind in sold_out_indicators:
                if await self.page.locator(ind).first.is_visible(timeout=500):
                    self.logger.info("❌ Status: SOLD OUT")
                    return 0 # Немає в наявності

            # 5. ПЕРЕВІРКА: IN STOCK (В наявності)
            in_stock_indicators = [
                "text='Add to cart'",
                "text='Add to Cart'",
                "text='Buy now'",
                "div[role='button']:has-text('Add to cart')",
                ".goods-bottom-bar",  # Нижня панель (є тільки якщо товар активний)
                ".quantity-selector", # Вибір кількості
                "text='Low stock'",
                "text='Almost sold out'"
            ]

            for ind in in_stock_indicators:
                if await self.page.locator(ind).first.is_visible(timeout=500):
                    self.logger.info("✅ Status: IN STOCK")
                    return 1 # Є в наявності
            
            # 6. Fallback (Якщо не знайшли явних кнопок, але є ціна)
            # На мобільній версії іноді кнопка "Add to cart" прилипає знизу і її важко знайти селектором,
            # але якщо є ціна і немає напису "Sold Out" - товар скоріше за все доступний.
            if await self.page.locator("text=$").count() > 0:
                self.logger.warning("⚠️ No 'Add' button found, but Price is visible -> Assuming IN STOCK")
                return 1
            
            # 7. Якщо сторінка порожня (ні ціни, ні статусу)
            # Це може бути білий екран бану, який пропустив check_for_ban
            self.logger.error("❌ Page Empty or Unknown Status")
            raise SoftBanException("Unknown Page State (White screen?)")

        except SoftBanException:
            raise
        except Exception as e:
            self.logger.error(f"Temu Parse Error: {e}")
            raise e
