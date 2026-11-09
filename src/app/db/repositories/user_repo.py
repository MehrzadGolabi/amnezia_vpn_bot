import uuid
from enum import Enum
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.base import utc_now
from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.db.models.user import User


class Audience(str, Enum):
    """Who a broadcast goes to. Blocked users are never included."""
    ACTIVE = "active"      # at least one subscription that is active and not yet expired
    INACTIVE = "inactive"  # everyone else, including users who never bought anything
    ALL = "all"


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        stmt = select(User).where(User.telegram_user_id == telegram_user_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def upsert_user(
        self,
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = "en",
    ) -> User:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code="fa" if (language_code or "").lower().startswith("fa") else "en",
            )
            self.session.add(user)
        else:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            # language_code is only set on first contact; after that it is the customer's own
            # choice from the language menu, so Telegram's setting must not overwrite it.
        await self.session.flush()
        return user

    async def set_blocked(self, telegram_user_id: int, blocked: bool) -> bool:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user:
            user.is_blocked = blocked
            await self.session.flush()
            return True
        return False

    async def list_audience_telegram_ids(self, audience: Audience) -> List[int]:
        """Telegram IDs of the users in a broadcast audience, oldest account first."""
        active_user_ids = select(Subscription.user_id).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.expires_at > utc_now(),
        )
        stmt = select(User.telegram_user_id).where(User.is_blocked.is_(False))
        if audience == Audience.ACTIVE:
            stmt = stmt.where(User.id.in_(active_user_ids))
        elif audience == Audience.INACTIVE:
            stmt = stmt.where(User.id.not_in(active_user_ids))
        res = await self.session.execute(stmt.order_by(User.created_at.asc()))
        return list(res.scalars().all())
