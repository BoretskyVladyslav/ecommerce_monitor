import asyncio
import pymysql
from config.settings import settings

async def list_products_table():
    """
    Показує дані з НОВОЇ таблиці 'products' (яку використовує бот).
    Це ПРАВИЛЬНА таблиця, а не стара 'monitored_products'.
    """
    print(f"Connecting to {settings.DB_HOST}...")
    try:
        conn = pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            db=settings.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with conn.cursor() as cursor:
            print("\n" + "="*80)
            print("PRODUCTS TABLE (Real Data - Used by Bot)")
            print("="*80)
            
            # Загальна кількість
            cursor.execute("SELECT COUNT(*) as total FROM products")
            total = cursor.fetchone()['total']
            print(f"\n📊 TOTAL PRODUCTS IN DATABASE: {total}")
            
            # Кількість з URL
            cursor.execute("SELECT COUNT(*) as total FROM products WHERE original_url IS NOT NULL")
            with_url = cursor.fetchone()['total']
            print(f"📊 Products with URL (will be processed): {with_url}")
            
            # Розбивка по платформах
            print("\n" + "-"*80)
            print("BREAKDOWN BY PLATFORM:")
            print("-"*80)
            
            platforms = [
                ('Amazon', '%amazon%'),
                ('AliExpress', '%aliexpress%'),
                ('Temu', '%temu%'),
                ('Shein', '%shein%'),
                ('Etsy', '%etsy%'),
                ('eBay', '%ebay%'),
            ]
            
            platform_counts = {}
            for platform_name, pattern in platforms:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM products WHERE original_url LIKE %s",
                    (pattern,)
                )
                count = cursor.fetchone()['count']
                platform_counts[platform_name] = count
                if count > 0:
                    print(f"  {platform_name:15} : {count:3} products")
            
            # Розбивка по статусу
            print("\n" + "-"*80)
            print("BREAKDOWN BY STATUS:")
            print("-"*80)
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM products 
                WHERE original_url IS NOT NULL
                GROUP BY status
            """)
            statuses = cursor.fetchall()
            for s in statuses:
                status_name = "Active" if s['status'] == 1 else "Inactive/Other"
                print(f"  Status {s['status']} ({status_name:15}): {s['count']:3} products")
            
            # Показати перші 10 товарів як приклад
            print("\n" + "-"*80)
            print("SAMPLE PRODUCTS (First 10):")
            print("-"*80)
            cursor.execute("""
                SELECT id, original_title, original_url, status
                FROM products 
                WHERE original_url IS NOT NULL
                LIMIT 10
            """)
            samples = cursor.fetchall()
            for p in samples:
                # Визначаємо платформу з URL
                url = p['original_url'].lower()
                if 'amazon' in url:
                    platform = 'Amazon'
                elif 'aliexpress' in url:
                    platform = 'AliExpress'
                elif 'temu' in url:
                    platform = 'Temu'
                elif 'shein' in url:
                    platform = 'Shein'
                elif 'etsy' in url:
                    platform = 'Etsy'
                else:
                    platform = 'Other'
                
                title = (p['original_title'][:50] + '...') if p['original_title'] and len(p['original_title']) > 50 else p['original_title']
                print(f"  ID {p['id']:3} | {platform:10} | Status: {p['status']} | {title}")
            
            print("\n" + "="*80)
            print(f"✅ VERIFICATION COMPLETE")
            print(f"   Bot will process: {with_url} products")
            print(f"   Platform filtering will be applied by monitor_engine.py")
            print("="*80 + "\n")

        conn.close()
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(list_products_table())
