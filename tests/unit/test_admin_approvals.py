import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.order import OrderStatus
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.models.job import JobType
from src.app.db.models.user import User
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.job_repo import JobRepository

from src.app.bot.handlers.admin import (
    cmd_admin_dashboard,
    callback_admin_approve_order,
    callback_admin_reject_order,
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
async def test_admin_dashboard_authorization(session: AsyncSession):
    # Non-admin
    msg_user = MagicMock(spec=Message)
    msg_user.from_user = TelegramUser(id=99999, is_bot=False, first_name="NormalUser")
    msg_user.answer = AsyncMock()

    data = {"session": session}
    await cmd_admin_dashboard(msg_user, data)
    assert msg_user.answer.call_count == 0  # Ignored or unauthorized

    # Admin
    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = settings.ADMIN_TELEGRAM_IDS[0] if settings.ADMIN_TELEGRAM_IDS else 123456789
    if not settings.ADMIN_TELEGRAM_IDS:
        settings.ADMIN_TELEGRAM_IDS = [admin_id]

    msg_admin = MagicMock(spec=Message)
    msg_admin.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg_admin.answer = AsyncMock()

    await cmd_admin_dashboard(msg_admin, data)
    msg_admin.answer.assert_called_once()
    assert "Admin Dashboard" in msg_admin.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_approve_and_idempotency(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=12345, username="buyer")
    server = await server_repo.create_or_update(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    await order_repo.submit_receipt(order.id, "file_receipt_1", 101, 12345, "photo")

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    query = MagicMock(spec=CallbackQuery)
    query.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin", username="superadmin")
    query.data = f"adm_app_{order.id}"
    query.message = MagicMock(spec=Message)
    query.message.text = "Order Receipt Card"
    query.message.caption = "Order Receipt Card"
    query.message.edit_caption = AsyncMock()
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    query.bot = AsyncMock()

    data = {"session": session}

    # 1. First approval
    await callback_admin_approve_order(query, data)
    assert query.answer.call_count == 1
    query.bot.send_message.assert_called_once()
    assert "approved" in query.bot.send_message.call_args[1]["text"].lower()

    # Check order in DB is in PROVISIONING state
    updated_order = await order_repo.get_by_id(order.id)
    assert updated_order.status == OrderStatus.PROVISIONING

    # Check job enqueued in DB
    jobs = await job_repo.claim_pending_jobs("worker-test", 10)
    assert any(j.job_type == JobType.CREATE_PEER for j in jobs)

    # 2. Idempotent second approval attempt
    query2 = MagicMock(spec=CallbackQuery)
    query2.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    query2.data = f"adm_app_{order.id}"
    query2.answer = AsyncMock()
    query2.bot = AsyncMock()

    await callback_admin_approve_order(query2, data)
    assert "already" in query2.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_admin_reject_order(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=12345, username="buyer")
    server = await server_repo.create_or_update(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    await order_repo.submit_receipt(order.id, "file_receipt_2", 102, 12345, "photo")

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    query = MagicMock(spec=CallbackQuery)
    query.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin", username="superadmin")
    query.data = f"adm_rej_{order.id}"
    query.message = MagicMock(spec=Message)
    query.message.caption = "Order Receipt Card"
    query.message.edit_caption = AsyncMock()
    query.answer = AsyncMock()
    query.bot = AsyncMock()

    data = {"session": session}

    await callback_admin_reject_order(query, data)
    assert query.answer.call_count == 1
    query.bot.send_message.assert_called_once()
    assert "rejected" in query.bot.send_message.call_args[1]["text"].lower()

    # Check order in DB is rejected
    updated_order = await order_repo.get_by_id(order.id)
    assert updated_order.status == OrderStatus.REJECTED
