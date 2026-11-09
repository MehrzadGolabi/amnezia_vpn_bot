"""Broadcast audiences and delivery, and /configs."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import CopyMessage
from aiogram.types import Chat, Message, User as TelegramUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.bot.handlers.admin import cmd_admin_user_configs
from src.app.bot.handlers.admin_broadcast import send_broadcast
from src.app.db.models.audit import AuditEvent
from src.app.db.models.base import Base, utc_now
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.user_repo import Audience, UserRepository

ADMIN_ID = 700001


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def admin(monkeypatch):
    from src.app.config.settings import get_settings
    monkeypatch.setattr(get_settings(), "ADMIN_TELEGRAM_IDS", [ADMIN_ID])


async def _subscription(s, telegram_id, *, status=SubscriptionStatus.ACTIVE, expires_in_days=30,
                        label=None, slug="de-1"):
    user = await UserRepository(s).upsert_user(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    server = await ServerRepository(s).create_or_update(
        slug=slug, display_name=f"Server {slug}", country_code="DE", host="localhost")
    product = await ProductRepository(s).create_or_update(
        code="vpn-1m", title="1 Month", duration_days=30, device_limit=1,
        price_amount=Decimal("5.00"), price_currency="EUR")
    order = await OrderRepository(s).create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await OrderRepository(s).approve_order_atomic(order.id, admin_telegram_id=ADMIN_ID)
    label = label or f"user_{telegram_id}_{sub.id.hex[:8]}"
    await SubscriptionRepository(s).mark_active(sub.id, peer_external_id=label, peer_label=label)
    sub.status = status
    sub.expires_at = utc_now() + timedelta(days=expires_in_days)
    await s.flush()
    return user, sub


async def test_audiences_split_users_by_running_subscription(session):
    await _subscription(session, 1)                                          # active
    await _subscription(session, 2, expires_in_days=-1)                      # active status, but expired
    await _subscription(session, 3, status=SubscriptionStatus.DISABLED, expires_in_days=-5)
    await UserRepository(session).upsert_user(telegram_user_id=4)            # never bought
    blocked, _ = await _subscription(session, 5)                             # active but blocked
    blocked.is_blocked = True
    # One active and one expired subscription: still active.
    await _subscription(session, 6, expires_in_days=-10)
    await _subscription(session, 6, slug="tr-1")
    await session.flush()

    repo = UserRepository(session)
    assert sorted(await repo.list_audience_telegram_ids(Audience.ACTIVE)) == [1, 6]
    assert sorted(await repo.list_audience_telegram_ids(Audience.INACTIVE)) == [2, 3, 4]
    assert sorted(await repo.list_audience_telegram_ids(Audience.ALL)) == [1, 2, 3, 4, 6]


async def test_send_broadcast_survives_blocked_users_and_rate_limits():
    method = CopyMessage(chat_id=1, from_chat_id=99, message_id=5)
    attempts = {}

    async def copy_message(chat_id, from_chat_id, message_id):
        attempts[chat_id] = attempts.get(chat_id, 0) + 1
        if chat_id == 2:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if chat_id == 3 and attempts[chat_id] == 1:
            raise TelegramRetryAfter(method=method, message="Too Many Requests", retry_after=0)

    bot = MagicMock()
    bot.copy_message = AsyncMock(side_effect=copy_message)
    sent, failed = await send_broadcast(bot, [1, 2, 3, 4], from_chat_id=99, message_id=5, interval=0)
    assert (sent, failed) == (3, 1)
    assert attempts == {1: 1, 2: 1, 3: 2, 4: 1}


def _message(text, chat_id=ADMIN_ID, chat_type="private"):
    msg = MagicMock(spec=Message)
    msg.from_user = TelegramUser(id=ADMIN_ID, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=chat_id, type=chat_type)
    msg.text = text
    msg.answer = AsyncMock()
    msg.bot = MagicMock()
    msg.bot.send_document = AsyncMock()
    msg.bot.send_message = AsyncMock()
    return msg


async def test_configs_sends_every_config_privately(session, admin):
    user, live = await _subscription(session, 42, label="user_42_live")
    _, removed = await _subscription(session, 42, slug="tr-1", label="user_42_gone")
    removed.removed_at = utc_now()
    _, broken = await _subscription(session, 42, slug="us-1", label="user_42_broken")
    await session.commit()

    async def get_peer_config(server, peer_external_id):
        if peer_external_id == "user_42_broken":
            raise RuntimeError("vpnctl on us-1 timed out after 30s")
        return b"[Interface]\nPrivateKey = abc\n"

    provisioner = MagicMock()
    provisioner.get_peer_config = AsyncMock(side_effect=get_peer_config)
    msg = _message("/configs 42", chat_id=-100555, chat_type="supergroup")  # used in the receipts group
    await cmd_admin_user_configs(msg, {"session": session, "provisioner": provisioner})

    # Only the live one is fetched and sent, to the admin's private chat, never the group.
    assert provisioner.get_peer_config.await_count == 2
    docs = msg.bot.send_document.await_args_list
    assert len(docs) == 1
    assert docs[0].kwargs["chat_id"] == ADMIN_ID
    assert docs[0].kwargs["document"].filename == "user_42_live.conf"
    texts = [c.kwargs["text"] for c in msg.bot.send_message.await_args_list]
    assert all(c.kwargs["chat_id"] == ADMIN_ID for c in msg.bot.send_message.await_args_list)
    assert any("vpn://" in t for t in texts)
    summary = texts[-1]
    assert "1 sent of 3" in summary
    assert "user_42_gone" in summary and "no config on a server" in summary
    assert "user_42_broken" in summary and "timed out" in summary
    assert "private chat" in msg.answer.await_args.args[0]

    events = (await session.execute(select(AuditEvent).where(AuditEvent.event_type == "user.configs_viewed"))).scalars().all()
    assert len(events) == 1 and events[0].entity_id == user.id


async def test_configs_usage_and_unknown_user(session, admin):
    msg = _message("/configs")
    await cmd_admin_user_configs(msg, {"session": session})
    assert "Usage" in msg.answer.await_args.args[0]

    msg = _message("/configs 12345")
    await cmd_admin_user_configs(msg, {"session": session})
    assert "not found" in msg.answer.await_args.args[0]


async def test_configs_ignores_non_admins(session, admin):
    msg = _message("/configs 42")
    msg.from_user = TelegramUser(id=1, is_bot=False, first_name="Nope")
    await cmd_admin_user_configs(msg, {"session": session})
    msg.answer.assert_not_called()
    msg.bot.send_document.assert_not_called()


async def test_configs_summary_stays_under_telegram_limit(session, admin):
    for n in range(20):
        await _subscription(session, 43, slug=f"s-{n}", label=f"user_43_{n:02d}")
    await session.commit()
    provisioner = MagicMock()
    provisioner.get_peer_config = AsyncMock(side_effect=RuntimeError("x" * 300))
    msg = _message("/configs 43")
    await cmd_admin_user_configs(msg, {"session": session, "provisioner": provisioner})
    summary = msg.bot.send_message.await_args.kwargs["text"]
    assert len(summary) <= 4096 and summary.endswith("…")


async def test_uncopyable_broadcast_message_resets_the_flow(session, admin):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from src.app.bot.handlers.admin_broadcast import handle_broadcast_message
    from src.app.bot.states.admin_states import AdminBroadcastStates

    await UserRepository(session).upsert_user(telegram_user_id=50)
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=ADMIN_ID, user_id=ADMIN_ID))
    await state.set_state(AdminBroadcastStates.waiting_for_message)
    await state.update_data(audience="all")

    msg = _message("poll")
    msg.message_id = 7
    msg.bot.copy_message = AsyncMock(side_effect=TelegramBadRequest(
        method=CopyMessage(chat_id=ADMIN_ID, from_chat_id=ADMIN_ID, message_id=7),
        message="Bad Request: message can't be copied"))
    await handle_broadcast_message(msg, {"session": session}, state)
    assert await state.get_state() is None
    assert "can't be broadcast" in msg.answer.await_args.args[0]
