import aiohttp
import asyncio
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

async def send_telegram_notification(message):
    """
    Sends a message to the configured Telegram chat asynchronously.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram Not Configured: Message skipped")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    print(f"✅ Telegram Notification Sent: {message.splitlines()[0]}")
                else:
                    print(f"❌ Telegram Error {response.status}: {await response.text()}")
    except Exception as e:
        print(f"❌ Telegram Notification Failed: {e}")
