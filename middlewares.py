import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from config import RATE_LIMIT, STAFF_IDS

class ThrottlingMiddleware(BaseMiddleware):
    # Timestamps older than this are useless — drop them so the dict cannot grow
    # without bound over a long uptime.
    EVICT_AFTER = 60.0
    EVICT_EVERY = 500

    def __init__(self, limit: float = RATE_LIMIT):
        super().__init__()
        self.limit = limit
        self.user_timestamps: Dict[int, float] = {}
        self._since_evict = 0

    def _maybe_evict(self, now: float):
        self._since_evict += 1
        if self._since_evict < self.EVICT_EVERY:
            return
        self._since_evict = 0
        cutoff = now - self.EVICT_AFTER
        self.user_timestamps = {
            uid: ts for uid, ts in self.user_timestamps.items() if ts > cutoff
        }

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

        # Staff send order contents as bursts of files; throttling would drop them.
        if user_id and user_id not in STAFF_IDS:
            now = time.time()
            last_time = self.user_timestamps.get(user_id, 0)
            if now - last_time < self.limit:
                # Anti-flood rate limit hit
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Не нажимайте так часто!", show_alert=False)
                return None
            self.user_timestamps[user_id] = now
            self._maybe_evict(now)

        return await handler(event, data)
