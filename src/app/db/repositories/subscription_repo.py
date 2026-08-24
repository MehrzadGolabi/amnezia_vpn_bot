import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.db.models.base import utc_now


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, subscription_id: uuid.UUID) -> Optional[Subscription]:
        stmt = (
            select(Subscription)
            .options(selectinload(Subscription.user), selectinload(Subscription.order))
            .where(Subscription.id == subscription_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_order_id(self, order_id: uuid.UUID) -> Optional[Subscription]:
        stmt = select(Subscription).where(Subscription.order_id == order_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_by_user_id(self, user_id: uuid.UUID) -> List[Subscription]:
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .order_by(Subscription.expires_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_all_by_user_id(self, user_id: uuid.UUID) -> List[Subscription]:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_expiring_soon(self, before_time: datetime) -> List[Subscription]:
        stmt = (
            select(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= before_time,
                Subscription.expires_at > utc_now(),
            )
            .order_by(Subscription.expires_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_expired_unprocessed(self) -> List[Subscription]:
        now = utc_now()
        stmt = (
            select(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
            )
            .order_by(Subscription.expires_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_active(
        self,
        subscription_id: uuid.UUID,
        peer_external_id: str,
        peer_label: str,
    ) -> Optional[Subscription]:
        sub = await self.get_by_id(subscription_id)
        if sub:
            sub.status = SubscriptionStatus.ACTIVE
            sub.peer_external_id = peer_external_id
            sub.peer_label = peer_label
            sub.config_delivery_status = "delivered"
            await self.session.flush()
        return sub

    async def mark_disabled(self, subscription_id: uuid.UUID) -> Optional[Subscription]:
        sub = await self.get_by_id(subscription_id)
        if sub:
            sub.status = SubscriptionStatus.DISABLED
            sub.disabled_at = utc_now()
            await self.session.flush()
        return sub

    async def mark_removed(self, subscription_id: uuid.UUID) -> Optional[Subscription]:
        sub = await self.get_by_id(subscription_id)
        if sub:
            sub.status = SubscriptionStatus.EXPIRED
            sub.removed_at = utc_now()
            await self.session.flush()
        return sub

    async def extend_subscription(self, subscription_id: uuid.UUID, days: int) -> Optional[Subscription]:
        sub = await self.get_by_id(subscription_id)
        if sub:
            base_time = max(sub.expires_at, utc_now())
            sub.expires_at = base_time + timedelta(days=days)
            if sub.status in (SubscriptionStatus.DISABLED, SubscriptionStatus.EXPIRED):
                sub.status = SubscriptionStatus.ACTIVE
                sub.disabled_at = None
            await self.session.flush()
        return sub

    async def increment_redelivery_count(self, subscription_id: uuid.UUID) -> int:
        sub = await self.get_by_id(subscription_id)
        if sub:
            sub.config_redelivery_count += 1
            await self.session.flush()
            return sub.config_redelivery_count
        return 0
