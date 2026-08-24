import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit_seconds: float = 0.5):
        self.rate_limit_seconds = rate_limit_seconds
        self._last_seen: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TelegramUser = getattr(event, "from_user", None)
        if not tg_user:
            return await handler(event, data)

        now = time.time()
        last_time = self._last_seen.get(tg_user.id, 0.0)

        if now - last_time < self.rate_limit_seconds:
            # Throttled
            return None

        self._last_seen[tg_user.id] = now
        return await handler(event, data)
