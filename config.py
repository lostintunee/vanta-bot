import os
import logging
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEFAULT_MANAGER = os.getenv("MANAGER_USERNAME", "@vanta_mg")

raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
for item in raw_admins.split(","):
    item_str = item.strip()
    if item_str.isdigit():
        ADMIN_IDS.append(int(item_str))

raw_manager_chat_id = os.getenv("MANAGER_CHAT_ID", "").strip()
MANAGER_CHAT_ID = int(raw_manager_chat_id) if raw_manager_chat_id.isdigit() else None

DB_PATH = "bot_database.db"
RATE_LIMIT = 0.5
