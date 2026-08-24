import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.app.db.models.base import Base
from src.app.db.models.user import User
from src.app.db.models.server import VPNServer
from src.app.db.models.product import Product
from src.app.db.models.order import Order, OrderStatus
from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.db.models.job import ProvisioningJob, JobType, JobStatus
from src.app.db.models.notification import Notification, NotificationType
from src.app.db.models.ticket import SupportTicket, SupportMessage, TicketStatus, SenderType
from src.app.db.models.audit import AuditEvent, ActorType


@pytest.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_creation_and_uniqueness(async_session: AsyncSession):
    user1 = User(
        telegram_user_id=123456789,
        username="testuser",
        first_name="Test",
        last_name="User",
        language_code="en",
    )
    async_session.add(user1)
    await async_session.commit()

    assert user1.id is not None
    assert user1.telegram_user_id == 123456789
    assert user1.is_blocked is False

    user2 = User(
        telegram_user_id=123456789,
        username="otheruser",
    )
    async_session.add(user2)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_order_and_subscription_lifecycle(async_session: AsyncSession):
    user = User(telegram_user_id=987654321, username="subscriber")
    server = VPNServer(
        slug="de-1",
        display_name="Germany",
        country_code="DE",
        country_name="Germany",
        host="de1.test.com",
    )
    product = Product(
        code="vpn-1m",
        title="1 Month Unlimited",
        duration_days=30,
        device_limit=1,
        price_amount=5.00,
        price_currency="EUR",
    )
    async_session.add_all([user, server, product])
    await async_session.commit()

    order = Order(
        public_order_code="ORD-123456",
        user_id=user.id,
        vpn_server_id=server.id,
        product_id=product.id,
        price_amount_snapshot=5.00,
        currency_snapshot="EUR",
        payment_instructions_snapshot="Pay via transfer",
        status=OrderStatus.AWAITING_RECEIPT,
    )
    async_session.add(order)
    await async_session.commit()
    assert order.id is not None
    assert order.status == OrderStatus.AWAITING_RECEIPT

    order.receipt_telegram_file_id = "file_abc_123"
    order.status = OrderStatus.APPROVED
    order.reviewed_by_telegram_user_id = 111222333
    order.reviewed_at = datetime.now(timezone.utc)
    await async_session.commit()

    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id,
        order_id=order.id,
        vpn_server_id=server.id,
        product_id=product.id,
        status=SubscriptionStatus.ACTIVE,
        peer_external_id="peer_uuid_123",
        peer_label="user_987654321_de1",
        starts_at=now,
        expires_at=now + timedelta(days=30),
    )
    async_session.add(sub)
    await async_session.commit()
    assert sub.id is not None
    assert sub.status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_provisioning_job_outbox(async_session: AsyncSession):
    job = ProvisioningJob(
        job_type=JobType.CREATE_PEER,
        aggregate_type="subscription",
        aggregate_id=uuid.uuid4(),
        status=JobStatus.PENDING,
        payload={"server_slug": "de-1", "user_id": 123},
    )
    async_session.add(job)
    await async_session.commit()
    assert job.attempt_count == 0
    assert job.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_notification_idempotency_constraint(async_session: AsyncSession):
    user = User(telegram_user_id=55555, username="notif_user")
    async_session.add(user)
    await async_session.commit()

    notif1 = Notification(
        user_id=user.id,
        notification_type=NotificationType.EXPIRES_1D,
        idempotency_key="sub_123_expires_1d",
        status="sent",
    )
    async_session.add(notif1)
    await async_session.commit()

    notif2 = Notification(
        user_id=user.id,
        notification_type=NotificationType.EXPIRES_1D,
        idempotency_key="sub_123_expires_1d",
        status="sent",
    )
    async_session.add(notif2)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


@pytest.mark.asyncio
async def test_support_ticket_and_messages(async_session: AsyncSession):
    user = User(telegram_user_id=777, username="ticket_user")
    async_session.add(user)
    await async_session.commit()

    ticket = SupportTicket(
        public_ticket_code="TCK-9999",
        user_id=user.id,
        status=TicketStatus.OPEN,
        subject="Connection issues",
    )
    async_session.add(ticket)
    await async_session.commit()

    msg1 = SupportMessage(
        ticket_id=ticket.id,
        sender_type=SenderType.CUSTOMER,
        sender_telegram_user_id=777,
        body="I cannot connect to DE-1",
    )
    msg2 = SupportMessage(
        ticket_id=ticket.id,
        sender_type=SenderType.ADMIN,
        sender_telegram_user_id=111,
        body="Please reinstall the config file.",
    )
    async_session.add_all([msg1, msg2])
    await async_session.commit()

    # Re-fetch ticket with selectinload
    stmt = select(SupportTicket).options(selectinload(SupportTicket.messages)).where(SupportTicket.id == ticket.id)
    res = await async_session.execute(stmt)
    fetched_ticket = res.scalar_one()

    assert fetched_ticket.id is not None
    assert len(fetched_ticket.messages) == 2
