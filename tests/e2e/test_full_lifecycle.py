import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message, PhotoSize, User as TelegramUser, Chat
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.order import OrderStatus
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.models.ticket import TicketStatus, SenderType
from src.app.db.models.job import JobType, JobStatus
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.ticket_repo import TicketRepository
from src.app.integrations.provisioning.mock_provisioner import MockProvisioner

from src.app.bot.states.order_states import OrderFlowStates
from src.app.bot.states.support_states import SupportStates
from src.app.bot.states.admin_states import AdminTicketStates
from src.app.bot.handlers.customer import (
    cmd_start,
    callback_menu_buy,
    callback_select_server,
    callback_select_plan,
    handle_receipt_upload,
    callback_view_subscription,
    callback_redeliver_subscription,
)
from src.app.bot.handlers.support import (
    cmd_support,
    handle_support_message,
)
from src.app.bot.handlers.admin import (
    cmd_admin_dashboard,
    callback_admin_approve_order,
    handle_admin_ticket_reply,
    callback_admin_close_ticket,
)
from src.app.worker.engine import WorkerEngine
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


@pytest.fixture
def fsm_factory():
    storage = MemoryStorage()
    def _create(user_id: int):
        key = StorageKey(bot_id=123456, chat_id=user_id, user_id=user_id)
        return FSMContext(storage=storage, key=key)
    return _create


@pytest.mark.asyncio
async def test_complete_end_to_end_lifecycle(session: AsyncSession, fsm_factory):
    # Setup initial servers, products, and admin settings
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    user_repo = UserRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)
    job_repo = JobRepository(session)
    ticket_repo = TicketRepository(session)

    server = await server_repo.create_or_update(
        slug="nl-main",
        display_name="Netherlands High Speed",
        country_code="NL",
        country_name="Netherlands",
        host="nl.example.com",
        enabled=True,
    )
    product = await product_repo.create_or_update(
        code="vpn-30d",
        title="30 Days Standard",
        duration_days=30,
        device_limit=2,
        price_amount=Decimal("5.00"),
        price_currency="EUR",
    )
    await session.commit()

    from src.app.config.settings import get_settings
    settings = get_settings()
    admin_id = 999000
    customer_tg_id = 555000
    settings.ADMIN_TELEGRAM_IDS = [admin_id]
    settings.ADMIN_CHAT_ID = admin_id

    # 1. Customer registers and launches bot
    user = await user_repo.upsert_user(telegram_user_id=customer_tg_id, username="customer_e2e", language_code="en")
    await session.commit()

    cust_fsm = fsm_factory(customer_tg_id)
    admin_fsm = fsm_factory(admin_id)
    data_cust = {"db_user": user, "session": session}
    data_admin = {"session": session}

    # Customer sends /start
    msg_start = MagicMock(spec=Message)
    msg_start.answer = AsyncMock()
    await cmd_start(msg_start, data_cust, cust_fsm)
    msg_start.answer.assert_called_once()

    # 2. Customer selects Buy -> Server -> Plan
    query_buy = MagicMock(spec=CallbackQuery)
    query_buy.message = MagicMock(spec=Message)
    query_buy.message.edit_text = AsyncMock()
    query_buy.answer = AsyncMock()
    await callback_menu_buy(query_buy, data_cust)

    query_srv = MagicMock(spec=CallbackQuery)
    query_srv.data = f"srv_{server.slug}"
    query_srv.message = MagicMock(spec=Message)
    query_srv.message.edit_text = AsyncMock()
    query_srv.answer = AsyncMock()
    await callback_select_server(query_srv, data_cust)

    query_plan = MagicMock(spec=CallbackQuery)
    query_plan.data = f"plan_{server.slug}_{product.code}"
    query_plan.message = MagicMock(spec=Message)
    query_plan.message.edit_text = AsyncMock()
    query_plan.answer = AsyncMock()
    query_plan.from_user = TelegramUser(id=customer_tg_id, is_bot=False, first_name="Cust")
    await callback_select_plan(query_plan, data_cust, cust_fsm)

    # 3. Customer uploads payment receipt
    fsm_state = await cust_fsm.get_data()
    order_id = uuid.UUID(fsm_state["order_id"])

    msg_receipt = MagicMock(spec=Message)
    msg_receipt.photo = [PhotoSize(file_id="photo_e2e_receipt", file_unique_id="u_e2e", width=100, height=100)]
    msg_receipt.document = None
    msg_receipt.message_id = 101
    msg_receipt.chat = Chat(id=customer_tg_id, type="private")
    msg_receipt.caption = "Paid 5 EUR via Card"
    msg_receipt.answer = AsyncMock()
    msg_receipt.bot = AsyncMock()

    await handle_receipt_upload(msg_receipt, data_cust, cust_fsm)
    msg_receipt.answer.assert_called_once()
    assert await cust_fsm.get_state() is None

    order = await order_repo.get_by_id(order_id)
    assert order.status == OrderStatus.RECEIPT_SUBMITTED

    # 4. Admin reviews and approves receipt
    query_adm_app = MagicMock(spec=CallbackQuery)
    query_adm_app.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin", username="lead_admin")
    query_adm_app.data = f"adm_app_{order.id}"
    query_adm_app.message = MagicMock(spec=Message)
    query_adm_app.message.caption = "Receipt Card"
    query_adm_app.message.edit_caption = AsyncMock()
    query_adm_app.answer = AsyncMock()
    query_adm_app.bot = AsyncMock()

    await callback_admin_approve_order(query_adm_app, data_admin)
    query_adm_app.answer.assert_called_once()

    order = await order_repo.get_by_id(order_id)
    assert order.status == OrderStatus.PROVISIONING

    # 5. Outbox Worker Engine processes provisioning job
    mock_provisioner = MockProvisioner()
    bot_mock = AsyncMock()
    session_factory = async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession)

    worker = WorkerEngine(
        session_factory=session_factory,
        provisioner=mock_provisioner,
        bot=bot_mock,
        worker_id="e2e-worker",
    )
    processed_count = await worker.run_single_batch(limit=10)
    assert processed_count == 1

    # Verify subscription is now ACTIVE and config was delivered
    subscriptions = await sub_repo.get_all_by_user_id(user.id)
    assert len(subscriptions) == 1
    sub = subscriptions[0]
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.peer_external_id is not None
    assert bot_mock.send_document.call_count == 1

    # 6. Customer requests Config Redelivery
    query_redeliver = MagicMock(spec=CallbackQuery)
    query_redeliver.data = f"sub_redeliver_{sub.id}"
    query_redeliver.answer = AsyncMock()
    await callback_redeliver_subscription(query_redeliver, data_cust)
    query_redeliver.answer.assert_called_once()

    # Worker processes redelivery
    processed_redelivery = await worker.run_single_batch(limit=10)
    assert processed_redelivery == 1
    assert bot_mock.send_document.call_count == 2

    # 7. Customer Support Ticket Flow
    msg_supp = MagicMock(spec=Message)
    msg_supp.text = "How do I configure this on iOS?"
    msg_supp.photo = None
    msg_supp.document = None
    msg_supp.message_id = 202
    msg_supp.chat = Chat(id=customer_tg_id, type="private")
    msg_supp.answer = AsyncMock()
    msg_supp.bot = AsyncMock()

    await cust_fsm.set_state(SupportStates.writing_message)
    await handle_support_message(msg_supp, data_cust, cust_fsm)
    msg_supp.answer.assert_called_once()

    ticket = await ticket_repo.get_active_ticket_for_user(user.id)
    assert ticket is not None
    assert ticket.status == TicketStatus.WAITING_FOR_ADMIN

    # Admin replies to ticket
    await admin_fsm.set_state(AdminTicketStates.waiting_for_reply)
    await admin_fsm.update_data(ticket_id=str(ticket.id))

    msg_adm_reply = MagicMock(spec=Message)
    msg_adm_reply.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    msg_adm_reply.chat = Chat(id=admin_id, type="private")
    msg_adm_reply.message_id = 303
    msg_adm_reply.text = "Install the AmneziaWG app from App Store and import the .conf file."
    msg_adm_reply.photo = None
    msg_adm_reply.document = None
    msg_adm_reply.answer = AsyncMock()
    msg_adm_reply.bot = AsyncMock()

    await handle_admin_ticket_reply(msg_adm_reply, data_admin, admin_fsm)
    msg_adm_reply.bot.send_message.assert_called_once()

    # Admin closes ticket
    query_close_tck = MagicMock(spec=CallbackQuery)
    query_close_tck.from_user = TelegramUser(id=admin_id, is_bot=False, first_name="Admin")
    query_close_tck.data = f"adm_cls_tck_{ticket.id}"
    query_close_tck.message = MagicMock(spec=Message)
    query_close_tck.message.edit_text = AsyncMock()
    query_close_tck.answer = AsyncMock()
    query_close_tck.bot = AsyncMock()

    await callback_admin_close_ticket(query_close_tck, data_admin)
    closed_ticket = await ticket_repo.get_by_id(ticket.id)
    assert closed_ticket.status == TicketStatus.CLOSED

    # 8. Subscription Lifecycle: Expiration & Disabling via Scheduler
    scheduler = SchedulerService(session_factory=session_factory, bot=bot_mock)

    # Manually backdate subscription expiry to past
    now = datetime.now(timezone.utc)
    sub.expires_at = now - timedelta(hours=2)
    await session.commit()

    disabled_count = await scheduler.check_expired_subscriptions()
    assert disabled_count == 1

    # Worker executes the disabling outbox job
    processed_disable = await worker.run_single_batch(limit=10)
    assert processed_disable == 1

    # Peer is disabled on server
    peer_status = await mock_provisioner.get_peer_status(server=server, peer_external_id=sub.peer_external_id)
    assert peer_status.is_active is False
