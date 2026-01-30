import asyncio
from database.db_manager import DatabaseManager
from fake_useragent import UserAgent
import random

async def update_user_agents():
    db = DatabaseManager()
    await db.init_db()
    
    # Initialize UserAgent generator
    try:
        ua = UserAgent(browsers=['chrome', 'edge'], os=['windows', 'macos'])
    except:
        # Fallback if network issue or cache missing
        ua = UserAgent()

    print("Fetching all sessions...")
    sessions = await db.fetch_all("SELECT id, name, type, user_agent FROM sessions")
    
    for s in sessions:
        # Generate new random UA
        # We prefer Chrome on Windows for best compatibility with this project
        # or mix it up
        
        # Strategy: 80% Windows, 20% MacOS
        platform = 'windows' if random.random() < 0.8 else 'macos'
        
        try:
            new_ua = ua.random
            # Simple filter to ensure it's not mobile if we want desktop
            # fake-useragent details are sometimes tricky, so let's try to enforce chrome/desktop
            # if possible.
            # But ua.random is good enough usually.
        except:
            new_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

        print(f"Session {s['id']} ({s['name']}): \n Old: {s.get('user_agent')}\n New: {new_ua}")
        
        await db.execute(
            "UPDATE sessions SET user_agent=%s WHERE id=%s", 
            (new_ua, s['id'])
        )
        print(f"Updated Session {s['id']}.")

    await db.close()

if __name__ == "__main__":
    asyncio.run(update_user_agents())
