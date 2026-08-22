import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN
from database import init_db
from handlers import start, catalog, admin
from middlewares import ThrottlingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню VANTA Shop"),
        BotCommand(command="admin", description="Админ-панель (для владельца)"),
    ]
    await bot.set_my_commands(commands)

async def main():
    if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN:
        logger.error("BOT_TOKEN is not set correctly in config.py / .env!")
        return

    logger.info("Initializing database...")
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Attach security middleware (anti-flood rate limiter)
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    # Include routers
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(admin.router)

    await setup_bot_commands(bot)

    logger.info("Starting VANTA Shop Telegram Bot...")
    # Delete webhook to prevent conflicts before polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
