import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, TelegramObject, User as TelegramUser

# Forget users who have been quiet this long, so the table can't grow without bound.
FORGET_AFTER_SECONDS = 60.0
PRUNE_AT_SIZE = 10_000


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit_seconds: float = 0.5):
        self.rate_limit_seconds = rate_limit_seconds
        self._last_seen: Dict[int, float] = {}

    def _prune(self, now: float) -> None:
        cutoff = now - max(FORGET_AFTER_SECONDS, self.rate_limit_seconds)
        self._last_seen = {uid: t for uid, t in self._last_seen.items() if t >= cutoff}

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
            # Throttled. Answer a button press anyway so it doesn't keep spinning.
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except TelegramBadRequest:
                    pass  # already answered, or too old to answer
            return None

        if len(self._last_seen) >= PRUNE_AT_SIZE:
            self._prune(now)
        self._last_seen[tg_user.id] = now
        return await handler(event, data)
