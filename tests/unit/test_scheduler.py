import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base, utc_now
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.models.job import JobType, JobStatus
from src.app.db.models.notification import NotificationType
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.job_repo import JobRepository

from src.app.scheduler.service import SchedulerService


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as s:
        yield s

    await engine.dispose()


@pytest.mark.asyncio
async def test_scheduler_reminders_and_idempotency(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=88888, username="renew_user")
    server = await server_repo.create_or_update(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(order.id, 111)
    await sub_repo.mark_active(sub.id, "peer-rem-1", "label-rem-1")

    # Set expiry to 2 days from now (within 3 days window)
    sub.expires_at = utc_now() + timedelta(days=2)
    await session.commit()

    mock_bot = AsyncMock()
    scheduler_service = SchedulerService(
        session_factory=lambda: session,
        bot=mock_bot,
        reminder_days=[7, 3, 1],
    )

    # First check triggers 3-day reminder
    sent_count = await scheduler_service.check_expiring_subscriptions()
    assert sent_count == 1
    assert mock_bot.send_message.call_count == 1

    # Second run is idempotent (no duplicate message)
    sent_count2 = await scheduler_service.check_expiring_subscriptions()
    assert sent_count2 == 0
    assert mock_bot.send_message.call_count == 1


@pytest.mark.asyncio
async def test_scheduler_expired_subscription_disabling(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=77777, username="expired_user")
    server = await server_repo.create_or_update(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(order.id, 111)
    await sub_repo.mark_active(sub.id, "peer-exp-1", "label-exp-1")

    # Set expiry in the past
    sub.expires_at = utc_now() - timedelta(hours=2)
    await session.commit()

    mock_bot = AsyncMock()
    scheduler_service = SchedulerService(
        session_factory=lambda: session,
        bot=mock_bot,
    )

    # Check expired subscriptions
    disabled_count = await scheduler_service.check_expired_subscriptions()
    assert disabled_count == 1

    # Verify disable job enqueued
    pending_jobs = await job_repo.claim_pending_jobs(worker_id="test", limit=10)
    assert any(j.job_type == JobType.DISABLE_PEER and j.aggregate_id == sub.id for j in pending_jobs)

    # Verify notification sent to customer
    mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_grace_period_peer_cleanup(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=66666, username="cleanup_user")
    server = await server_repo.create_or_update(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(order.id, 111)
    await sub_repo.mark_active(sub.id, "peer-clean-1", "label-clean-1")
    await sub_repo.mark_disabled(sub.id)

    # Set disabled_at to 35 days ago (grace period is 30 days)
    sub.disabled_at = utc_now() - timedelta(days=35)
    await session.commit()

    mock_bot = AsyncMock()
    scheduler_service = SchedulerService(
        session_factory=lambda: session,
        bot=mock_bot,
        peer_removal_grace_days=30,
    )

    removed_count = await scheduler_service.cleanup_removed_peers()
    assert removed_count == 1

    # Verify remove job enqueued
    pending_jobs = await job_repo.claim_pending_jobs(worker_id="test", limit=10)
    assert any(j.job_type == JobType.REMOVE_PEER and j.aggregate_id == sub.id for j in pending_jobs)
