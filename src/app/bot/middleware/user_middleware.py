from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.bot.locales.strings import get_text
from src.app.db.repositories.user_repo import UserRepository
from src.app.utils.logging import get_logger

logger = get_logger(__name__)


class UserMiddleware(BaseMiddleware):
    def __init__(self, session_factory: Callable[[], AsyncSession], user_repo_cls=UserRepository):
        self.session_factory = session_factory
        self.user_repo_cls = user_repo_cls

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["data"] = data
        tg_user: TelegramUser = getattr(event, "from_user", None)
        if not tg_user:
            return await handler(event, data)

        session = self.session_factory()
        try:
            repo = self.user_repo_cls(session)
            db_user = await repo.upsert_user(
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                language_code=tg_user.language_code or "en",
            )
            await session.commit()
            data["db_user"] = db_user
            data["session"] = session

            if db_user.is_blocked:
                logger.warning("blocked_user_activity", user_id=tg_user.id)
                # Ignore blocked user
                return None

            return await handler(event, data)
        finally:
            if hasattr(session, "close"):
                await session.close()
