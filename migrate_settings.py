import asyncio
from database.db_manager import DatabaseManager

async def migrate():
    print("🚀 Starting Settings Migration...")
    db = DatabaseManager()
    
    # 1. Drop old table if existing format is column-based
    # We can detect this by trying to select 'threads' column
    pool = await db.get_pool()
    
    need_migration = False
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute("SHOW COLUMNS FROM settings LIKE 'threads'")
                if await cur.fetchone():
                    print("⚠️ Old column-based 'settings' table detected.")
                    need_migration = True
            except Exception as e:
                # Table might not exist
                pass

    if need_migration:
        print("🗑️ Dropping old table...")
        await db.execute("DROP TABLE settings")

    # 2. Create new Key-Value table
    print("🔨 Creating new 'settings' table (Key-Value)...")
    create_query = """
    CREATE TABLE IF NOT EXISTS settings (
        setting_key VARCHAR(50) PRIMARY KEY,
        setting_value TEXT
    );
    """
    await db.execute(create_query)

    # 3. Insert Defaults
    print("📥 Inserting default values...")
    defaults = [
        ('threads', '1'),
        ('headless', '0'), # 0 = False
        ('delay_min', '2'),
        ('delay_max', '5')
    ]
    
    for k, v in defaults:
        await db.execute(
            "INSERT IGNORE INTO settings (setting_key, setting_value) VALUES (%s, %s)",
            (k, v)
        )
    
    print("✅ Migration Complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
