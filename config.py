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

# Everyone who processes orders: owners plus the manager who receives notifications.
STAFF_IDS = set(ADMIN_IDS)
if MANAGER_CHAT_ID:
    STAFF_IDS.add(MANAGER_CHAT_ID)

# Point this at a mounted volume in production — a container's own filesystem is
# wiped on every deploy, taking users, orders and settings with it.
DB_PATH = os.getenv("DB_PATH", "bot_database.db")

RATE_LIMIT = 0.5

# Telegram tolerates ~30 messages/sec; stay well under it during broadcasts.
BROADCAST_DELAY = 0.05
