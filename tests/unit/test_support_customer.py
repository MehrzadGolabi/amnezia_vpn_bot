import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message, User as TelegramUser, Chat
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.ticket import TicketStatus
from src.app.db.models.user import User
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.ticket_repo import TicketRepository
from src.app.bot.states.support_states import SupportStates
from src.app.bot.handlers.support import (
    cmd_support,
    callback_menu_support,
    handle_support_message,
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
    key = StorageKey(bot_id=123456, chat_id=77777, user_id=77777)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_support_prompt(fsm_context: FSMContext):
    query = MagicMock(spec=CallbackQuery)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()

    data = {"db_user": User(id=uuid.uuid4(), telegram_user_id=77777, language_code="en")}

    await callback_menu_support(query, data, fsm_context)
    assert await fsm_context.get_state() == SupportStates.writing_message.state
    query.message.edit_text.assert_called_once()
    assert "Support" in query.message.edit_text.call_args[0][0]


@pytest.mark.asyncio
async def test_support_ticket_creation(session: AsyncSession, fsm_context: FSMContext):
    user_repo = UserRepository(session)
    ticket_repo = TicketRepository(session)
    user = await user_repo.upsert_user(telegram_user_id=77777, username="ticket_user", language_code="en")

    await fsm_context.set_state(SupportStates.writing_message)

    msg = MagicMock(spec=Message)
    msg.text = "How do I connect from Windows?"
    msg.photo = None
    msg.document = None
    msg.message_id = 456
    msg.chat = Chat(id=77777, type="private")
    msg.answer = AsyncMock()
    msg.bot = AsyncMock()

    data = {"db_user": user, "session": session}

    await handle_support_message(msg, data, fsm_context)
    msg.answer.assert_called_once()
    assert "TCK-" in msg.answer.call_args[0][0]
    assert await fsm_context.get_state() is None

    # Check ticket created in DB
    ticket = await ticket_repo.get_active_ticket_for_user(user.id)
    assert ticket is not None
    assert ticket.status == TicketStatus.WAITING_FOR_ADMIN

    # Send second message to same open ticket
    await fsm_context.set_state(SupportStates.writing_message)
    msg2 = MagicMock(spec=Message)
    msg2.text = "Also from iOS?"
    msg2.photo = None
    msg2.document = None
    msg2.message_id = 457
    msg2.chat = Chat(id=77777, type="private")
    msg2.answer = AsyncMock()
    msg2.bot = AsyncMock()

    await handle_support_message(msg2, data, fsm_context)
    ticket2 = await ticket_repo.get_active_ticket_for_user(user.id)
    assert ticket2.id == ticket.id
