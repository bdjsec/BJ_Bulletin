import os
import urllib.request
import json
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")
url = f"https://api.telegram.org/bot{token}/getUpdates"

with urllib.request.urlopen(url) as response:
    data = json.loads(response.read())

if not data["result"]:
    print("No messages yet. Send any message to your bot in Telegram, then run this again.")
else:
    for update in data["result"]:
        chat = update["message"]["chat"]
        print(f"Chat ID: {chat['id']}  |  Name: {chat.get('first_name', '')} {chat.get('last_name', '')}")
