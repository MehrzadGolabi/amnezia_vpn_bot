import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.job import JobType
from src.app.db.models.user import User
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.job_repo import JobRepository

from src.app.bot.handlers.customer import (
    callback_menu_subs,
    cmd_my_vpn,
    callback_view_subscription,
    callback_redeliver_subscription,
    callback_renew_subscription,
)


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
async def test_my_subscriptions_empty(session: AsyncSession):
    user_repo = UserRepository(session)
    user = await user_repo.upsert_user(telegram_user_id=11111, username="empty_user", language_code="en")

    query = MagicMock(spec=CallbackQuery)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()

    data = {"db_user": user, "session": session}
    await callback_menu_subs(query, data)
    query.message.edit_text.assert_called_once()
    assert "do not have any active subscriptions" in query.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_my_subscriptions_with_active_sub(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=22222, username="sub_user", language_code="en")
    server = await server_repo.create_or_update(slug="nl-1", display_name="Netherlands", country_code="NL", country_name="Netherlands", host="nl.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(order.id, 111)
    await sub_repo.mark_active(sub.id, "peer-nl-1", "user_22222_nl1")

    data = {"db_user": user, "session": session}

    # 1. Menu subs
    query_subs = MagicMock(spec=CallbackQuery)
    query_subs.message = MagicMock(spec=Message)
    query_subs.message.edit_text = AsyncMock()
    query_subs.answer = AsyncMock()
    await callback_menu_subs(query_subs, data)
    query_subs.message.edit_text.assert_called_once()

    # 2. View sub detail
    query_view = MagicMock(spec=CallbackQuery)
    query_view.data = f"sub_view_{sub.id}"
    query_view.message = MagicMock(spec=Message)
    query_view.message.edit_text = AsyncMock()
    query_view.answer = AsyncMock()
    await callback_view_subscription(query_view, data)
    query_view.message.edit_text.assert_called_once()
    assert "Netherlands" in query_view.message.edit_text.call_args[0][0]

    # 3. Request redelivery
    query_redeliver = MagicMock(spec=CallbackQuery)
    query_redeliver.data = f"sub_redeliver_{sub.id}"
    query_redeliver.answer = AsyncMock()
    await callback_redeliver_subscription(query_redeliver, data)
    query_redeliver.answer.assert_called_once()

    # Check job queued
    pending = await job_repo.claim_pending_jobs("worker-test", 10)
    assert any(j.job_type == JobType.REDELIVER_CONFIG and j.aggregate_id == sub.id for j in pending)

    # 4. Renew subscription
    query_renew = MagicMock(spec=CallbackQuery)
    query_renew.data = f"renew_{sub.id}"
    query_renew.message = MagicMock(spec=Message)
    query_renew.message.edit_text = AsyncMock()
    query_renew.answer = AsyncMock()
    await callback_renew_subscription(query_renew, data)
    query_renew.message.edit_text.assert_called_once()
    assert "Select Subscription Plan" in query_renew.message.edit_text.call_args[0][0]
