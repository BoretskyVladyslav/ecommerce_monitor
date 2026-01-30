import asyncio
from database.db_manager import DatabaseManager

async def update_proxies():
    db = DatabaseManager()
    await db.init_db()

    # Proxy 1 (EU/Lithuania/Romania): 195.123.210.138:43201 (http)
    proxy_eu = "http://dimasrap5:tp6WPEheHC@195.123.210.138:43201"
    
    # Proxy 2 (USA): 209.145.57.39:44048 (http)
    proxy_usa = "http://dimasrap5:tp6WPEheHC@209.145.57.39:44048"

    print("Checking existing sessions...")
    
    # Update Session 1 (Amazon) -> USA
    await db.execute("UPDATE sessions SET proxy=%s, type='amazon', status='Ready' WHERE id=1", (proxy_usa,))
    print(f"Updated Session 1 (Amazon) with USA Proxy: {proxy_usa}")

    # Update Session 2 (Shein) -> USA
    await db.execute("UPDATE sessions SET proxy=%s, type='shein', status='Ready' WHERE id=2", (proxy_usa,))
    print(f"Updated Session 2 (Shein) with USA Proxy: {proxy_usa}")
    
    # Update Session 3 (Temu) -> EU
    await db.execute("UPDATE sessions SET proxy=%s, type='temu', status='Ready' WHERE id=3", (proxy_eu,))
    print(f"Updated Session 3 (Temu) with EU Proxy: {proxy_eu}")

    # Read back to confirm
    sessions = await db.fetch_all("SELECT id, name, type, proxy FROM sessions WHERE id IN (1, 2, 3)")
    for s in sessions:
        print(f"Session {s['id']}: {s['type']} -> {s['proxy']}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(update_proxies())
