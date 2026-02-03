import asyncio
import pymysql
from config.settings import settings

async def list_all_products():
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
            print("\n--- MONITORED PRODUCTS (Parent Table) ---")
            cursor.execute("SELECT id, name, original_url FROM monitored_products")
            products = cursor.fetchall()
            for p in products:
                print(p)
                
            print("\n--- MONITORED PROJECT OPTIONS (Variations/Tasks) ---")
            # Showing all, including status 0
            cursor.execute("""
                SELECT mpo.id, mpo.product_id, mpo.option_name, mpo.status, mp.marketplace 
                FROM monitored_product_options mpo
                JOIN monitored_products mp ON mpo.product_id = mp.id
            """)
            options = cursor.fetchall()
            for o in options:
                print(o)

            print(f"\nTotal Parent Products: {len(products)}")
            print(f"Total Options (Tasks): {len(options)}")
            
            # Count active
            active = [o for o in options if o['status'] == 1]
            print(f"Active Tasks (Status=1): {len(active)}")

        conn.close()
        
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(list_all_products())
