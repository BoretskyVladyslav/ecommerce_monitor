import asyncio
from database.db_manager import DatabaseManager

async def test_db():
    print("Testing Database...")
    db = DatabaseManager()
    
    # 1. Init (create tables)
    await db.init_db()
    print("✅ Init DB success")
    
    # 2. Clear old test session
    await db.execute("DELETE FROM sessions WHERE name='TestSession'")
    
    # 3. Create Session
    query = """
        INSERT INTO sessions (name, type, proxy, status, user_agent) 
        VALUES (%s, %s, %s, %s, %s)
    """
    await db.execute(query, ('TestSession', 'amazon', 'http://1.2.3.4:8080', 'Ready', 'TestUA/1.0'))
    print("✅ Insert Session success")
    
    # 4. Read Session
    s = await db.get_available_session('amazon')
    if s and s['name'] == 'TestSession':
         print(f"✅ Read Session success: {s['name']} - {s['status']}")
    else:
         print(f"❌ Read Session failed or mismatch: {s}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(test_db())
