import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import RATE_LIMIT

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = RATE_LIMIT):
        super().__init__()
        self.limit = limit
        self.user_timestamps: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            now = time.time()
            last_time = self.user_timestamps.get(user_id, 0)
            if now - last_time < self.limit:
                # Anti-flood rate limit hit
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Не нажимайте так часто!", show_alert=False)
                return None
            self.user_timestamps[user_id] = now

        return await handler(event, data)
