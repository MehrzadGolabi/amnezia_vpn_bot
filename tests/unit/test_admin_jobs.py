"""Job claims that two workers can't both win, /retry, and /audit."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.bot.handlers.admin_jobs import RETRY_ALL, callback_retry, cmd_audit, cmd_retry
from src.app.bot.ui import RETRY_PREFIX
from src.app.config.settings import get_settings
from src.app.db.models.base import Base, utc_now
from src.app.db.models.job import JobStatus, JobType
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.user_repo import UserRepository

ADMIN_ID = 424242


@pytest.fixture
async def factory(tmp_path):
    # A file, not :memory:, so two sessions see the same database like two workers would.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


@pytest.fixture
async def session(factory):
    async with factory() as s:
        yield s


@pytest.fixture(autouse=True)
def admin(monkeypatch):
    monkeypatch.setattr(get_settings(), "ADMIN_TELEGRAM_IDS", [ADMIN_ID])


async def approved_subscription(session):
    user = await UserRepository(session).upsert_user(telegram_user_id=777, username="buyer")
    server = await ServerRepository(session).create_or_update(
        slug="de-1", display_name="Germany", country_code="DE", host="")
    product = await ProductRepository(session).create_or_update(
        code="vpn-1m", title="1 Month", duration_days=30, device_limit=1,
        price_amount=Decimal("5.00"), price_currency="EUR")
    order_repo = OrderRepository(session)
    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, job = await order_repo.approve_order_atomic(order.id, admin_telegram_id=ADMIN_ID)
    await session.commit()
    return sub, job


async def fail_for_good(session, job):
    await JobRepository(session).mark_failed(job.id, "Cannot reach vpnctl on de-1: <timeout>", is_retryable=False)
    await session.commit()


def press(data):
    query = MagicMock(spec=CallbackQuery)
    query.data = data
    query.from_user = TelegramUser(id=ADMIN_ID, is_bot=False, first_name="A")
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    return query


def command(text):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = TelegramUser(id=ADMIN_ID, is_bot=False, first_name="A")
    msg.answer = AsyncMock()
    return msg


# --- Claims ---

async def test_second_worker_cannot_claim_a_claimed_job(factory):
    async with factory() as a, factory() as b:
        job = await JobRepository(a).enqueue_job(JobType.CREATE_PEER, "subscription", uuid.uuid4(), {})
        await a.commit()

        claimed = await JobRepository(a).claim_pending_jobs("worker-a")
        await a.commit()
        assert [j.id for j in claimed] == [job.id]
        assert claimed[0].status == JobStatus.PROCESSING and claimed[0].locked_by == "worker-a"

        # Worker b saw the job as pending a moment ago; its claim must now match nothing.
        assert await JobRepository(b).claim_one(job.id, "worker-b", utc_now()) is False
        assert await JobRepository(b).claim_pending_jobs("worker-b") == []


async def test_job_left_by_a_crashed_worker_is_claimed_again(session):
    repo = JobRepository(session)
    job = await repo.enqueue_job(JobType.CREATE_PEER, "subscription", uuid.uuid4(), {})
    await repo.claim_pending_jobs("crashed")
    job.locked_at = utc_now() - timedelta(minutes=6)
    await session.commit()
    claimed = await repo.claim_pending_jobs("worker-b")
    assert [j.locked_by for j in claimed] == ["worker-b"]


# --- /retry ---

async def test_retry_lists_failed_jobs_and_escapes_errors(session):
    _, job = await approved_subscription(session)
    await fail_for_good(session, job)
    msg = command("/retry")
    await cmd_retry(msg, {"session": session})
    text = msg.answer.call_args.args[0]
    assert job.id.hex[:8] in text
    assert "&lt;timeout&gt;" in text and "<timeout>" not in text
    buttons = [b.callback_data for row in msg.answer.call_args.kwargs["reply_markup"].inline_keyboard for b in row]
    assert f"{RETRY_PREFIX}{job.id.hex}" in buttons and RETRY_ALL in buttons


async def test_retry_requeues_and_records_who_did_it(session):
    sub, job = await approved_subscription(session)
    await fail_for_good(session, job)

    await callback_retry(press(f"{RETRY_PREFIX}{job.id.hex}"), {"session": session})
    job = await JobRepository(session).get_by_id(job.id)
    assert job.status == JobStatus.PENDING and job.attempt_count == 0 and job.last_error is None

    msg = command("/audit")
    await cmd_audit(msg, {"session": session})
    assert "job.requeued" in msg.answer.call_args.args[0]
    assert str(ADMIN_ID) in msg.answer.call_args.args[0]


async def test_retry_refuses_a_create_for_a_subscription_no_longer_waiting(session):
    sub, job = await approved_subscription(session)
    await fail_for_good(session, job)
    sub = await SubscriptionRepository(session).get_by_id(sub.id)
    sub.status = SubscriptionStatus.REVOKED
    await session.commit()

    query = press(RETRY_ALL)
    await callback_retry(query, {"session": session})
    assert (await JobRepository(session).get_by_id(job.id)).status == JobStatus.PERMANENT_FAILURE
    assert "revoked" in query.answer.call_args.args[0]


async def test_retry_refuses_an_enable_for_an_expired_subscription(session):
    sub, create_job = await approved_subscription(session)
    sub = await SubscriptionRepository(session).get_by_id(sub.id)
    sub.status = SubscriptionStatus.DISABLED
    sub.expires_at = utc_now() - timedelta(days=1)
    job_repo = JobRepository(session)
    await job_repo.mark_completed(create_job.id)
    job = await job_repo.enqueue_job(JobType.ENABLE_PEER, "subscription", sub.id, {})
    await session.commit()
    await fail_for_good(session, job)

    query = press(f"{RETRY_PREFIX}{job.id.hex}")
    await callback_retry(query, {"session": session})
    assert (await job_repo.get_by_id(job.id)).status == JobStatus.PERMANENT_FAILURE
    assert "isn't active" in query.answer.call_args.args[0]


async def test_retry_needs_an_admin(session):
    _, job = await approved_subscription(session)
    await fail_for_good(session, job)
    query = press(f"{RETRY_PREFIX}{job.id.hex}")
    query.from_user = TelegramUser(id=1, is_bot=False, first_name="X")
    await callback_retry(query, {"session": session})
    assert (await JobRepository(session).get_by_id(job.id)).status == JobStatus.PERMANENT_FAILURE


async def test_failure_alert_has_a_retry_button():
    from src.app.worker.engine import WorkerEngine
    worker = WorkerEngine.__new__(WorkerEngine)
    worker.admin_chat_id = 999
    worker.bot = AsyncMock()
    job_id = uuid.uuid4()
    await worker._alert_admin("failed", retry_job_id=job_id)
    markup = worker.bot.send_message.call_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == f"{RETRY_PREFIX}{job_id.hex}"


# --- Audit records for admin actions ---

async def audit_events(session):
    from sqlalchemy import select
    from src.app.db.models.audit import AuditEvent
    rows = (await session.execute(select(AuditEvent))).scalars().all()
    return {(e.event_type, e.actor_telegram_user_id) for e in rows}


async def test_admin_actions_are_recorded(session):
    from src.app.bot.handlers.admin import (
        callback_admin_approve_order, callback_admin_reject_order,
        callback_admin_toggle_server, cmd_admin_block_user, cmd_admin_unblock_user,
    )
    user = await UserRepository(session).upsert_user(telegram_user_id=777, username="buyer")
    server = await ServerRepository(session).create_or_update(
        slug="de-1", display_name="Germany", country_code="DE", host="")
    product = await ProductRepository(session).create_or_update(
        code="vpn-1m", title="1 Month", duration_days=30, device_limit=1,
        price_amount=Decimal("5.00"), price_currency="EUR")
    order_repo = OrderRepository(session)
    approve_me = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    reject_me = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    await session.commit()

    data = {"session": session}
    for handler, query_data in ((callback_admin_approve_order, f"adm_app_{approve_me.id}"),
                                (callback_admin_reject_order, f"adm_rej_{reject_me.id}"),
                                (callback_admin_toggle_server, f"adm_tgl_srv_{server.id}")):
        query = press(query_data)
        query.from_user = TelegramUser(id=ADMIN_ID, is_bot=False, first_name="A", username="boss")
        query.bot = AsyncMock()
        query.message.caption = None
        query.message.html_text = "receipt"
        query.message.edit_text = AsyncMock()
        query.message.answer = AsyncMock()
        await handler(query, data)
    for handler, text in ((cmd_admin_block_user, "/block 777"), (cmd_admin_unblock_user, "/unblock 777")):
        await handler(command(text), data)

    events = await audit_events(session)
    for event in ("order.approved", "order.rejected", "user.blocked", "user.unblocked"):
        assert (event, ADMIN_ID) in events, event
    assert {e for e, _ in events} & {"server.disabled", "server.paused", "server.enabled", "server.resumed"}


# --- Capacity ---

async def test_full_server_is_not_offered_and_cannot_be_ordered(session):
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from src.app.bot.handlers.customer import callback_menu_buy, callback_select_plan, callback_select_server

    sub, _ = await approved_subscription(session)  # one subscription on de-1, still provisioning
    server_repo = ServerRepository(session)
    server = await server_repo.get_by_slug("de-1")
    server.max_active_subscriptions = 1
    await session.commit()
    assert await server_repo.has_room(server) is False
    assert await server_repo.list_for_sale() == []

    user = await UserRepository(session).get_by_telegram_id(777)
    data = {"db_user": user, "session": session}
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=777, user_id=777))
    for handler, query_data in ((callback_select_server, "srv_de-1"), (callback_select_plan, "plan_de-1_vpn-1m")):
        query = press(query_data)
        args = (query, data, state) if handler is callback_select_plan else (query, data)
        await handler(*args)
        query.message.edit_text.assert_not_called()
        assert "full" in query.answer.call_args.args[0]
    assert await state.get_state() is None

    # Raising the limit puts it back on sale.
    server.max_active_subscriptions = 2
    await session.commit()
    assert [s.slug for s in await server_repo.list_for_sale()] == ["de-1"]
    menu = press("menu_buy")
    await callback_menu_buy(menu, data)
    assert "de-1" in str(menu.message.edit_text.call_args)
