"""
Warmup All Marketplaces
Запускає warmup для всіх платформ послідовно або вибірково.

Usage:
    python warmup_all.py              # Warmup всіх платформ
    python warmup_all.py shein        # Warmup тільки Shein
    python warmup_all.py aliexpress   # Warmup тільки AliExpress
"""
import asyncio
import sys
from utils.auto_warmup import auto_warmup
from config.logger import setup_logger

logger = setup_logger("WarmupAll")

async def main():
    """Головна функція для warmup"""
    
    # Отримуємо аргументи командного рядку
    marketplaces = sys.argv[1:] if len(sys.argv) > 1 else ['shein', 'aliexpress']
    
    logger.info("=" * 60)
    logger.info("🔥 WARMUP ALL MARKETPLACES")
    logger.info("=" * 60)
    logger.info(f"📋 Target marketplaces: {', '.join(marketplaces)}")
    logger.info("=" * 60)
    
    results = {}
    
    for marketplace in marketplaces:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"🎯 Starting warmup for: {marketplace.upper()}")
        logger.info(f"{'=' * 60}\n")
        
        # Запускаємо warmup (force=True щоб обійти ліміти)
        success = await auto_warmup.handle_captcha(marketplace, force=True)
        results[marketplace] = success
        
        logger.info(f"\n{'=' * 60}")
        if success:
            logger.info(f"✅ {marketplace.upper()} warmup completed successfully!")
        else:
            logger.error(f"❌ {marketplace.upper()} warmup failed!")
        logger.info(f"{'=' * 60}\n")
        
        # Пауза між платформами
        if marketplace != marketplaces[-1]:
            logger.info("⏳ Waiting 10 seconds before next marketplace...\n")
            await asyncio.sleep(10)
    
    # Підсумки
    logger.info("\n" + "=" * 60)
    logger.info("📊 WARMUP SUMMARY")
    logger.info("=" * 60)
    for marketplace, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        logger.info(f"{marketplace.upper()}: {status}")
    logger.info("=" * 60)
    
    # Показуємо статистику
    logger.info("\n" + "=" * 60)
    logger.info("📈 WARMUP STATISTICS")
    logger.info("=" * 60)
    stats = auto_warmup.get_stats()
    for marketplace, data in stats.items():
        logger.info(f"\n{marketplace.upper()}:")
        logger.info(f"  Total warmups: {data.get('total_warmups', 0)}")
        logger.info(f"  Warmups in last hour: {len(data.get('warmups_last_hour', []))}")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
