"""
Приклади використання CaptchaDetector
Демонструє різні сценарії детекції та обробки капчі.
"""
import asyncio
from playwright.async_api import async_playwright
from utils.captcha_detector import captcha_detector, CaptchaType
from config.logger import setup_logger

logger = setup_logger("CaptchaExamples")


async def example_1_basic_detection():
    """
    Приклад 1: Базова детекція капчі
    """
    logger.info("=" * 60)
    logger.info("EXAMPLE 1: Basic Captcha Detection")
    logger.info("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Переходимо на AliExpress
        await page.goto("https://www.aliexpress.com/w/wholesale-phone-cases.html")
        await asyncio.sleep(5)
        
        # Детектуємо капчу
        captcha_info = await captcha_detector.detect(page, "aliexpress")
        
        if captcha_info.detected:
            logger.warning(f"🚫 Captcha detected!")
            logger.info(f"   Type: {captcha_info.captcha_type}")
            logger.info(f"   Screenshot: {captcha_info.screenshot_path}")
        else:
            logger.info("✅ No captcha detected")
        
        await asyncio.sleep(10)
        await browser.close()


async def example_2_quick_check_in_loop():
    """
    Приклад 2: Швидка перевірка в циклі (для warmup)
    """
    logger.info("=" * 60)
    logger.info("EXAMPLE 2: Quick Check in Warmup Loop")
    logger.info("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        warmup_urls = [
            "https://www.aliexpress.com/w/wholesale-phone-cases.html",
            "https://www.aliexpress.com/category/200003482/women-clothing.html",
        ]
        
        for idx, url in enumerate(warmup_urls, 1):
            logger.info(f"\n[{idx}/{len(warmup_urls)}] Visiting: {url}")
            
            # ПЕРЕВІРКА перед навігацією
            if await captcha_detector.quick_check(page, "aliexpress"):
                logger.warning("🚫 Captcha detected BEFORE navigation!")
                logger.warning("   In real scenario: call auto-solver here")
                break
            
            await page.goto(url, timeout=30000)
            await asyncio.sleep(3)
            
            # ПЕРЕВІРКА після навігації
            if await captcha_detector.quick_check(page, "aliexpress"):
                logger.warning("🚫 Captcha detected AFTER navigation!")
                logger.warning("   In real scenario: call auto-solver here")
                break
            
            # Імітуємо скрол
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(2)
            
            # ПЕРЕВІРКА після скролу
            if await captcha_detector.quick_check(page, "aliexpress"):
                logger.warning("🚫 Captcha detected AFTER scroll!")
                logger.warning("   In real scenario: call auto-solver here")
                break
            
            logger.info(f"✅ Product {idx} processed without captcha")
        
        await asyncio.sleep(5)
        await browser.close()


async def example_3_type_specific_handling():
    """
    Приклад 3: Обробка різних типів капчі
    """
    logger.info("=" * 60)
    logger.info("EXAMPLE 3: Type-Specific Captcha Handling")
    logger.info("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto("https://www.aliexpress.com/")
        await asyncio.sleep(5)
        
        captcha_info = await captcha_detector.detect(page, "aliexpress")
        
        if not captcha_info.detected:
            logger.info("✅ No captcha detected")
            await browser.close()
            return
        
        # Різна логіка для різних типів
        logger.warning(f"🚫 Captcha Type: {captcha_info.captcha_type}")
        
        if captcha_info.captcha_type == CaptchaType.SLIDER:
            logger.info("📌 Handler: Slider Captcha")
            logger.info("   → Would call: CapMonster ImageToCoordinates")
            logger.info("   → Would receive: {x_offset: 250}")
            logger.info("   → Would execute: Drag slider with Bezier curve")
            
        elif captcha_info.captcha_type == CaptchaType.GEETEST:
            logger.info("📌 Handler: GeeTest Captcha")
            logger.info("   → Would call: CapMonster GeeTestTask")
            logger.info("   → Would receive: {challenge, validate, seccode}")
            logger.info("   → Would execute: Submit solution to page")
            
        elif captcha_info.captcha_type == CaptchaType.CLICK_POINTS:
            logger.info("📌 Handler: Click Points Captcha")
            logger.info("   → Would call: CapMonster CoordinatesTask")
            logger.info("   → Would receive: [{x: 100, y: 50}, {x: 200, y: 80}]")
            logger.info("   → Would execute: Click each point in sequence")
            
        elif captcha_info.captcha_type == CaptchaType.FUNCAPTCHA:
            logger.info("📌 Handler: FunCaptcha (Arkose Labs)")
            logger.info("   → Would call: CapMonster FunCaptchaTask")
            logger.info("   → Would receive: {token: '...'}")
            logger.info("   → Would execute: Submit token to verification")
            
        elif captcha_info.captcha_type == CaptchaType.ROTATE:
            logger.info("📌 Handler: Rotate Captcha")
            logger.info("   → Would call: CapMonster RotateTask")
            logger.info("   → Would receive: {angle: 40}")
            logger.info("   → Would execute: Rotate image by 40 degrees")
            
        elif captcha_info.captcha_type == CaptchaType.GRID:
            logger.info("📌 Handler: Grid/ReCaptcha")
            logger.info("   → Would call: CapMonster RecaptchaV2Task")
            logger.info("   → Would receive: {token: 'g-recaptcha-response'}")
            logger.info("   → Would execute: Submit token to form")
        
        else:
            logger.warning(f"⚠️ Unknown captcha type: {captcha_info.captcha_type}")
            logger.info("   → Would fallback to manual solving")
        
        # Показуємо додаткові дані
        if captcha_info.additional_data:
            logger.info(f"\n📊 Additional Data:")
            for key, value in captcha_info.additional_data.items():
                logger.info(f"   {key}: {value}")
        
        await asyncio.sleep(30)
        await browser.close()


async def example_4_multi_platform():
    """
    Приклад 4: Тестування на різних платформах
    """
    logger.info("=" * 60)
    logger.info("EXAMPLE 4: Multi-Platform Detection")
    logger.info("=" * 60)
    
    platforms_urls = {
        "aliexpress": "https://www.aliexpress.com/w/wholesale-phone-cases.html",
        "shein": "https://us.shein.com/SHEIN-Frenchy-Letter-Graphic-Tee-p-22673044.html",
        "temu": "https://www.temu.com/",
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        for platform, url in platforms_urls.items():
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Testing: {platform.upper()}")
            logger.info(f"{'=' * 60}")
            
            page = await browser.new_page()
            
            try:
                await page.goto(url, timeout=30000)
                await asyncio.sleep(5)
                
                captcha_info = await captcha_detector.detect(page, platform)
                
                if captcha_info.detected:
                    logger.warning(f"🚫 {platform}: Captcha detected!")
                    logger.info(f"   Type: {captcha_info.captcha_type}")
                    logger.info(f"   Selector: {captcha_info.selector}")
                else:
                    logger.info(f"✅ {platform}: No captcha")
                
            except Exception as e:
                logger.error(f"❌ {platform}: Error - {e}")
            
            finally:
                await page.close()
                await asyncio.sleep(3)
        
        await browser.close()


async def example_5_screenshot_analysis():
    """
    Приклад 5: Аналіз скріншотів капчі
    """
    logger.info("=" * 60)
    logger.info("EXAMPLE 5: Screenshot Analysis")
    logger.info("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto("https://www.aliexpress.com/")
        await asyncio.sleep(5)
        
        # Робимо детекцію ЗІ скріншотом
        captcha_info = await captcha_detector.detect(
            page, 
            platform="aliexpress",
            take_screenshot=True  # Обов'язково зі скріншотом
        )
        
        if captcha_info.detected and captcha_info.screenshot_path:
            logger.info(f"📸 Screenshot saved to: {captcha_info.screenshot_path}")
            logger.info(f"   This screenshot would be sent to CapMonster API")
            logger.info(f"   Captcha type: {captcha_info.captcha_type}")
            
            # В реальному сценарії:
            # with open(captcha_info.screenshot_path, 'rb') as f:
            #     image_base64 = base64.b64encode(f.read()).decode()
            #     response = capmonster_api.solve(image_base64, type=captcha_info.captcha_type)
        
        # Cleanup старих скріншотів
        deleted = captcha_detector.cleanup_screenshots(days_old=7)
        logger.info(f"\n🗑️ Cleaned up {deleted} old screenshots")
        
        await asyncio.sleep(10)
        await browser.close()


async def main():
    """Запуск всіх прикладів"""
    
    examples = {
        "1": ("Basic Detection", example_1_basic_detection),
        "2": ("Quick Check in Loop", example_2_quick_check_in_loop),
        "3": ("Type-Specific Handling", example_3_type_specific_handling),
        "4": ("Multi-Platform", example_4_multi_platform),
        "5": ("Screenshot Analysis", example_5_screenshot_analysis),
    }
    
    logger.info("🎯 Captcha Detector Examples")
    logger.info("=" * 60)
    logger.info("Select example to run:")
    for key, (name, _) in examples.items():
        logger.info(f"{key}. {name}")
    logger.info("=" * 60)
    
    # За замовчуванням запускаємо приклад 3 (Type-Specific)
    choice = "3"
    
    if choice in examples:
        name, func = examples[choice]
        logger.info(f"\n▶️ Running: {name}\n")
        await func()
    else:
        logger.error("Invalid choice")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Examples completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
