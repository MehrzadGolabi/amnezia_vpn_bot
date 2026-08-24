import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message, User as TelegramUser, Chat
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.ticket import TicketStatus, SenderType
from src.app.db.models.user import User
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.ticket_repo import TicketRepository
from src.app.bot.states.admin_states import AdminTicketStates
from src.app.bot.handlers.admin import (
    callback_admin_reply_ticket,
    handle_admin_ticket_reply,
    callback_admin_close_ticket,
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


@pytest.fixture
def fsm_context():
    storage = MemoryStorage()
    key = StorageKey(bot_id=123456, chat_id=999111, user_id=999111)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_admin_ticket_reply_flow(session: AsyncSession, fsm_context: FSMContext):
    user_repo = UserRepository(session)
    ticket_repo = TicketRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=77777, username="ticket_user", language_code="en")
    ticket = await ticket_repo.create_ticket(
        user_id=user.id,
        subject="Connection help",
        initial_message="Need assistance",
        sender_telegram_user_id=user.telegram_user_id,
    )

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    data = {"session": session}

    # 1. Admin clicks Reply
    query = MagicMock(spec=CallbackQuery)
    query.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    query.data = f"adm_rep_tck_{ticket.id}"
    query.message = MagicMock(spec=Message)
    query.message.answer = AsyncMock()
    query.answer = AsyncMock()

    await callback_admin_reply_ticket(query, data, fsm_context)
    assert await fsm_context.get_state() == AdminTicketStates.waiting_for_reply.state
    query.message.answer.assert_called_once()

    # 2. Admin submits reply message
    msg = MagicMock(spec=Message)
    msg.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=999111, type="private")
    msg.message_id = 888
    msg.text = "Please download the Amnezia client from amnezia.org."
    msg.photo = None
    msg.document = None
    msg.answer = AsyncMock()
    msg.bot = AsyncMock()

    await handle_admin_ticket_reply(msg, data, fsm_context)
    assert await fsm_context.get_state() is None
    msg.answer.assert_called_once()

    # Customer received notification
    msg.bot.send_message.assert_called_once()
    assert "amnezia.org" in msg.bot.send_message.call_args[1]["text"]

    # Ticket status in DB is WAITING_FOR_CUSTOMER
    updated_ticket = await ticket_repo.get_by_id(ticket.id)
    assert updated_ticket.status == TicketStatus.WAITING_FOR_CUSTOMER


@pytest.mark.asyncio
async def test_admin_close_ticket(session: AsyncSession):
    user_repo = UserRepository(session)
    ticket_repo = TicketRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=77777, username="ticket_user", language_code="en")
    ticket = await ticket_repo.create_ticket(
        user_id=user.id,
        subject="Connection help",
        initial_message="Need assistance",
        sender_telegram_user_id=user.telegram_user_id,
    )

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999111
    settings.ADMIN_TELEGRAM_IDS = [admin_id]

    data = {"session": session}

    query = MagicMock(spec=CallbackQuery)
    query.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    query.data = f"adm_cls_tck_{ticket.id}"
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    query.bot = AsyncMock()

    await callback_admin_close_ticket(query, data)
    query.answer.assert_called_once()
    query.bot.send_message.assert_called_once()
    assert "closed" in query.bot.send_message.call_args[1]["text"].lower()

    # Ticket in DB is closed
    closed_ticket = await ticket_repo.get_by_id(ticket.id)
    assert closed_ticket.status == TicketStatus.CLOSED
