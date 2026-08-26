import logging
from aiogram import Bot
from config import ADMIN_IDS, MANAGER_CHAT_ID

logger = logging.getLogger(__name__)

async def notify_admins(bot: Bot, text: str, reply_markup=None):
    recipients = set(ADMIN_IDS)
    if MANAGER_CHAT_ID:
        recipients.add(MANAGER_CHAT_ID)

    for chat_id in recipients:
        try:
            await bot.send_message(
                chat_id, text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=reply_markup
            )
        except Exception:
            logger.exception(f"Failed to notify {chat_id}")
