import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message, PhotoSize, User as TelegramUser, Chat
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.order import OrderStatus
from src.app.db.models.user import User
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.bot.states.order_states import OrderFlowStates
from src.app.bot.handlers.customer import (
    cmd_start,
    callback_main_menu,
    callback_menu_buy,
    callback_select_server,
    callback_select_plan,
    handle_receipt_upload,
    callback_cancel_order,
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
    key = StorageKey(bot_id=123456, chat_id=55555, user_id=55555)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_cmd_start():
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    db_user = User(id=uuid.uuid4(), telegram_user_id=12345, language_code="en")
    data = {"db_user": db_user}

    await cmd_start(message, data)
    message.answer.assert_called_once()
    assert "AmneziaWG" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_callback_main_menu():
    query = MagicMock(spec=CallbackQuery)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    data = {"db_user": User(id=uuid.uuid4(), telegram_user_id=12345, language_code="en")}

    await callback_main_menu(query, data)
    query.message.edit_text.assert_called_once()
    query.answer.assert_called_once()


@pytest.mark.asyncio
async def test_purchase_flow(session: AsyncSession, fsm_context: FSMContext):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=55555, username="flow_user", language_code="en")
    server = await server_repo.create_or_update(slug="de-1", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-1m", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    data = {"db_user": user, "session": session}

    # 1. Buy menu clicked
    query_buy = MagicMock(spec=CallbackQuery)
    query_buy.message = MagicMock(spec=Message)
    query_buy.message.edit_text = AsyncMock()
    query_buy.answer = AsyncMock()
    await callback_menu_buy(query_buy, data)
    query_buy.message.edit_text.assert_called_once()

    # 2. Server selected
    query_srv = MagicMock(spec=CallbackQuery)
    query_srv.data = "srv_de-1"
    query_srv.message = MagicMock(spec=Message)
    query_srv.message.edit_text = AsyncMock()
    query_srv.answer = AsyncMock()
    await callback_select_server(query_srv, data)
    query_srv.message.edit_text.assert_called_once()

    # 3. Plan selected
    query_plan = MagicMock(spec=CallbackQuery)
    query_plan.data = "plan_de-1_vpn-1m"
    query_plan.message = MagicMock(spec=Message)
    query_plan.message.edit_text = AsyncMock()
    query_plan.answer = AsyncMock()
    query_plan.from_user = TelegramUser(id=55555, is_bot=False, first_name="Flow")

    await callback_select_plan(query_plan, data, fsm_context)
    query_plan.message.edit_text.assert_called_once()
    assert await fsm_context.get_state() == OrderFlowStates.awaiting_receipt.state

    state_data = await fsm_context.get_data()
    order_id = uuid.UUID(state_data["order_id"])
    created_order = await order_repo.get_by_id(order_id)
    assert created_order is not None
    assert created_order.status == OrderStatus.AWAITING_RECEIPT

    # 4. Receipt upload
    msg_receipt = MagicMock(spec=Message)
    msg_receipt.photo = [PhotoSize(file_id="photo_xyz", file_unique_id="u_xyz", width=100, height=100)]
    msg_receipt.document = None
    msg_receipt.message_id = 999
    msg_receipt.chat = Chat(id=55555, type="private")
    msg_receipt.caption = "Receipt transaction 123"
    msg_receipt.answer = AsyncMock()
    msg_receipt.bot = AsyncMock()

    await handle_receipt_upload(msg_receipt, data, fsm_context)
    msg_receipt.answer.assert_called_once()
    assert await fsm_context.get_state() is None

    # Check order updated to RECEIPT_SUBMITTED
    updated_order = await order_repo.get_by_id(order_id)
    assert updated_order.status == OrderStatus.RECEIPT_SUBMITTED
    assert updated_order.receipt_telegram_file_id == "photo_xyz"


@pytest.mark.asyncio
async def test_cancel_order_flow(fsm_context: FSMContext):
    await fsm_context.set_state(OrderFlowStates.awaiting_receipt)
    query = MagicMock(spec=CallbackQuery)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    data = {"db_user": User(id=uuid.uuid4(), telegram_user_id=123, language_code="en")}

    await callback_cancel_order(query, data, fsm_context)
    assert await fsm_context.get_state() is None
    query.message.edit_text.assert_called_once()
