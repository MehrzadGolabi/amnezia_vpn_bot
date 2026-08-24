import asyncio
from datetime import datetime, timezone, timedelta
from typing import Callable, List, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.base import utc_now
from src.app.db.models.job import JobType, JobStatus
from src.app.db.models.notification import NotificationType
from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.db.repositories.audit_repo import NotificationRepository
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.user_repo import UserRepository
from src.app.utils.logging import get_logger

logger = get_logger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SchedulerService:
    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        bot: Bot,
        reminder_days: Optional[List[int]] = None,
        peer_removal_grace_days: int = 30,
        interval_seconds: int = 300,
    ):
        self.session_factory = session_factory
        self.bot = bot
        self.reminder_days = sorted(reminder_days or [7, 3, 1], reverse=True)
        self.peer_removal_grace_days = peer_removal_grace_days
        self.interval_seconds = interval_seconds
        self.scheduler = AsyncIOScheduler()

    async def check_expiring_subscriptions(self) -> int:
        session = self.session_factory()
        sub_repo = SubscriptionRepository(session)
        user_repo = UserRepository(session)
        server_repo = ServerRepository(session)
        notif_repo = NotificationRepository(session)

        now = utc_now()
        max_reminder_window = now + timedelta(days=max(self.reminder_days))
        notifications_sent = 0

        try:
            expiring_subs = await sub_repo.list_expiring_soon(max_reminder_window)
            for sub in expiring_subs:
                expires_at_utc = _to_utc(sub.expires_at)
                time_left = expires_at_utc - now
                if time_left.total_seconds() <= 0:
                    continue  # Handled by check_expired_subscriptions

                days_left = time_left.days
                # Find matching threshold
                matched_day = None
                for threshold in sorted(self.reminder_days):
                    if days_left <= threshold:
                        matched_day = threshold
                        break

                if matched_day is None:
                    continue

                type_map = {
                    1: NotificationType.EXPIRES_1D,
                    3: NotificationType.EXPIRES_3D,
                    7: NotificationType.EXPIRES_7D,
                }
                notif_type = type_map.get(matched_day, NotificationType.EXPIRES_1D)
                idempotency_key = f"sub_{sub.id}_reminder_{matched_day}d"

                notif, created = await notif_repo.create_notification_if_not_exists(
                    user_id=sub.user_id,
                    notification_type=notif_type,
                    idempotency_key=idempotency_key,
                )

                if created:
                    user = await user_repo.get_by_id(sub.user_id)
                    server = await server_repo.get_by_id(sub.vpn_server_id)
                    if user and server:
                        expiry_str = expires_at_utc.strftime("%Y-%m-%d %H:%M UTC")
                        kb = InlineKeyboardMarkup(
                            inline_keyboard=[[
                                InlineKeyboardButton(text="💳 Renew Subscription", callback_data=f"renew_{sub.id}")
                            ]]
                        )
                        text = (
                            f"⚠️ <b>VPN Subscription Expiring Soon</b>\n\n"
                            f"📍 <b>Location:</b> {server.display_name}\n"
                            f"⏳ <b>Expires:</b> <code>{expiry_str}</code> (~{matched_day} day(s) left)\n\n"
                            f"Click below to renew and maintain uninterrupted connection."
                        )
                        try:
                            await self.bot.send_message(
                                chat_id=user.telegram_user_id,
                                text=text,
                                reply_markup=kb,
                                parse_mode="HTML",
                            )
                            notifications_sent += 1
                        except Exception as e:
                            logger.error("failed_to_send_reminder", user_id=user.telegram_user_id, error=str(e))

            await session.commit()
            return notifications_sent
        finally:
            if hasattr(session, "close"):
                await session.close()

    async def check_expired_subscriptions(self) -> int:
        session = self.session_factory()
        sub_repo = SubscriptionRepository(session)
        job_repo = JobRepository(session)
        user_repo = UserRepository(session)
        server_repo = ServerRepository(session)
        notif_repo = NotificationRepository(session)

        now = utc_now()
        disabled_count = 0

        try:
            stmt = select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
            )
            result = await session.execute(stmt)
            expired_subs = result.scalars().all()

            for sub in expired_subs:
                # Enqueue disable job
                await job_repo.enqueue_job(
                    job_type=JobType.DISABLE_PEER,
                    aggregate_type="subscription",
                    aggregate_id=sub.id,
                    payload={"reason": "subscription_expired"},
                )

                idempotency_key = f"sub_{sub.id}_expired"
                notif, created = await notif_repo.create_notification_if_not_exists(
                    user_id=sub.user_id,
                    notification_type=NotificationType.EXPIRED,
                    idempotency_key=idempotency_key,
                )

                if created:
                    user = await user_repo.get_by_id(sub.user_id)
                    server = await server_repo.get_by_id(sub.vpn_server_id)
                    if user and server:
                        kb = InlineKeyboardMarkup(
                            inline_keyboard=[[
                                InlineKeyboardButton(text="💳 Reactivate / Renew", callback_data=f"renew_{sub.id}")
                            ]]
                        )
                        text = (
                            f"❌ <b>VPN Subscription Expired</b>\n\n"
                            f"📍 <b>Location:</b> {server.display_name}\n\n"
                            f"Your VPN peer has been disabled. Renew now to restore access."
                        )
                        try:
                            await self.bot.send_message(
                                chat_id=user.telegram_user_id,
                                text=text,
                                reply_markup=kb,
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            logger.error("failed_to_send_expired_alert", user_id=user.telegram_user_id, error=str(e))

                disabled_count += 1

            await session.commit()
            return disabled_count
        finally:
            if hasattr(session, "close"):
                await session.close()

    async def cleanup_removed_peers(self) -> int:
        session = self.session_factory()
        job_repo = JobRepository(session)

        now = utc_now()
        cutoff_date = now - timedelta(days=self.peer_removal_grace_days)
        removed_count = 0

        try:
            stmt = select(Subscription).where(
                Subscription.status == SubscriptionStatus.DISABLED,
                Subscription.disabled_at.is_not(None),
                Subscription.disabled_at <= cutoff_date,
            )
            result = await session.execute(stmt)
            cleanup_subs = result.scalars().all()

            for sub in cleanup_subs:
                await job_repo.enqueue_job(
                    job_type=JobType.REMOVE_PEER,
                    aggregate_type="subscription",
                    aggregate_id=sub.id,
                    payload={"reason": "grace_period_expired"},
                )
                removed_count += 1

            await session.commit()
            return removed_count
        finally:
            if hasattr(session, "close"):
                await session.close()

    def start(self) -> None:
        self.scheduler.add_job(
            self.check_expiring_subscriptions,
            "interval",
            seconds=self.interval_seconds,
            id="expiring_subs_check",
        )
        self.scheduler.add_job(
            self.check_expired_subscriptions,
            "interval",
            seconds=self.interval_seconds,
            id="expired_subs_check",
        )
        self.scheduler.add_job(
            self.cleanup_removed_peers,
            "interval",
            seconds=self.interval_seconds * 6,
            id="cleanup_removed_peers",
        )
        self.scheduler.start()
        logger.info("scheduler_started", interval=self.interval_seconds)

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("scheduler_stopped")
