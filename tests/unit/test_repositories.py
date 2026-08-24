import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.order import OrderStatus
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.models.job import JobType, JobStatus
from src.app.db.models.notification import NotificationType
from src.app.db.models.ticket import TicketStatus, SenderType
from src.app.db.models.audit import ActorType

from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.ticket_repo import TicketRepository
from src.app.db.repositories.audit_repo import AuditRepository, NotificationRepository


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
async def test_user_repository(session: AsyncSession):
    repo = UserRepository(session)
    user = await repo.upsert_user(
        telegram_user_id=12345,
        username="john_doe",
        first_name="John",
        last_name="Doe",
        language_code="en",
    )
    assert user.id is not None
    assert user.username == "john_doe"

    # Update user
    user2 = await repo.upsert_user(
        telegram_user_id=12345,
        username="john_new",
        first_name="John",
        last_name="Smith",
    )
    assert user2.id == user.id
    assert user2.username == "john_new"

    fetched = await repo.get_by_telegram_id(12345)
    assert fetched is not None
    assert fetched.username == "john_new"

    by_id = await repo.get_by_id(user.id)
    assert by_id is not None
    assert by_id.id == user.id

    blocked = await repo.set_blocked(12345, True)
    assert blocked is True
    assert (await repo.get_by_telegram_id(12345)).is_blocked is True
    assert (await repo.set_blocked(99999, True)) is False


@pytest.mark.asyncio
async def test_server_and_product_repository(session: AsyncSession):
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)

    server = await server_repo.create_or_update(
        slug="de-1",
        display_name="Germany",
        country_code="DE",
        country_name="Germany",
        host="de.vpn.test",
        enabled=True,
    )
    # Update server
    await server_repo.create_or_update(
        slug="de-1",
        display_name="Germany Frankfurt",
        country_code="DE",
        country_name="Germany",
        host="de.vpn.test",
        enabled=True,
    )
    product = await product_repo.create_or_update(
        code="vpn-1m",
        title="1 Month",
        duration_days=30,
        device_limit=1,
        price_amount=Decimal("5.00"),
        price_currency="EUR",
        enabled=True,
    )
    # Update product
    await product_repo.create_or_update(
        code="vpn-1m",
        title="1 Month Pro",
        duration_days=30,
        device_limit=2,
        price_amount=Decimal("6.00"),
        price_currency="EUR",
        enabled=True,
    )

    servers = await server_repo.list_enabled()
    assert len(servers) == 1
    assert servers[0].slug == "de-1"
    assert servers[0].display_name == "Germany Frankfurt"

    all_servers = await server_repo.list_all()
    assert len(all_servers) == 1

    by_id = await server_repo.get_by_id(server.id)
    assert by_id is not None

    count = await server_repo.count_active_subscriptions(server.id)
    assert count == 0

    await server_repo.set_enabled("de-1", False)
    assert len(await server_repo.list_enabled()) == 0

    products = await product_repo.list_enabled()
    assert len(products) == 1
    assert products[0].code == "vpn-1m"
    assert products[0].price_amount == Decimal("6.00")

    prod_by_id = await product_repo.get_by_id(product.id)
    assert prod_by_id is not None


@pytest.mark.asyncio
async def test_order_lifecycle_and_rejection(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=999, username="buyer")
    server = await server_repo.create_or_update(slug="tr-1", display_name="Turkey", country_code="TR", country_name="Turkey", host="tr.test")
    product = await product_repo.create_or_update(code="vpn-3m", title="3 Months", duration_days=90, device_limit=2, price_amount=Decimal("12.00"), price_currency="EUR")

    order = await order_repo.create_order(
        user_id=user.id,
        vpn_server_id=server.id,
        product_id=product.id,
        price_amount=product.price_amount,
        price_currency=product.price_currency,
        payment_instructions="Send to card XYZ",
    )
    assert order.status == OrderStatus.AWAITING_RECEIPT

    by_code = await order_repo.get_by_code(order.public_order_code)
    assert by_code is not None
    assert by_code.id == order.id

    # Submit Receipt
    await order_repo.submit_receipt(
        order_id=order.id,
        file_id="receipt_file_123",
        message_id=555,
        chat_id=999,
        media_type="photo",
        note="Paid via ATM",
    )
    submitted_order = await order_repo.get_by_id(order.id)
    assert submitted_order.status == OrderStatus.RECEIPT_SUBMITTED

    pending = await order_repo.list_pending_orders()
    assert len(pending) == 1
    assert pending[0].id == order.id

    recent = await order_repo.list_recent_orders(10)
    assert len(recent) == 1

    # Atomic Approve
    success, subscription, job = await order_repo.approve_order_atomic(
        order_id=order.id,
        admin_telegram_id=111,
    )
    assert success is True
    assert subscription is not None
    assert subscription.status == SubscriptionStatus.PROVISIONING
    assert job is not None
    assert job.job_type == JobType.CREATE_PEER

    # Idempotent second approval attempt must return success=False
    success2, sub2, job2 = await order_repo.approve_order_atomic(
        order_id=order.id,
        admin_telegram_id=111,
    )
    assert success2 is False
    assert sub2 is not None
    assert sub2.id == subscription.id

    # Reject another order
    order2 = await order_repo.create_order(
        user_id=user.id,
        vpn_server_id=server.id,
        product_id=product.id,
        price_amount=product.price_amount,
        price_currency=product.price_currency,
        payment_instructions="Send to card XYZ",
    )
    rejected_ok, rej_order = await order_repo.reject_order(order2.id, admin_telegram_id=111, reason="Fake receipt")
    assert rejected_ok is True
    assert rej_order.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_subscription_lifecycle(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=101, username="sub_user")
    server = await server_repo.create_or_update(slug="de-sub", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-sub", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")

    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(order.id, 111)

    # Mark active
    await sub_repo.mark_active(sub.id, peer_external_id="peer-123", peer_label="user-101-de")
    active_subs = await sub_repo.get_active_by_user_id(user.id)
    assert len(active_subs) == 1
    assert active_subs[0].peer_external_id == "peer-123"

    by_order = await sub_repo.get_by_order_id(order.id)
    assert by_order is not None

    all_user_subs = await sub_repo.get_all_by_user_id(user.id)
    assert len(all_user_subs) == 1

    # Redelivery count
    count = await sub_repo.increment_redelivery_count(sub.id)
    assert count == 1

    # Extend
    extended = await sub_repo.extend_subscription(sub.id, 10)
    assert extended is not None

    # Expiring check
    future_time = datetime.now(timezone.utc) + timedelta(days=50)
    expiring = await sub_repo.list_expiring_soon(future_time)
    assert len(expiring) == 1

    # Mark disabled & removed
    await sub_repo.mark_disabled(sub.id)
    disabled_sub = await sub_repo.get_by_id(sub.id)
    assert disabled_sub.status == SubscriptionStatus.DISABLED

    # Re-extend disabled sub restores ACTIVE
    await sub_repo.extend_subscription(sub.id, 5)
    restored_sub = await sub_repo.get_by_id(sub.id)
    assert restored_sub.status == SubscriptionStatus.ACTIVE

    await sub_repo.mark_removed(sub.id)
    removed_sub = await sub_repo.get_by_id(sub.id)
    assert removed_sub.status == SubscriptionStatus.EXPIRED


@pytest.mark.asyncio
async def test_job_locking_failure_and_retries(session: AsyncSession):
    job_repo = JobRepository(session)
    job = await job_repo.enqueue_job(
        job_type=JobType.CREATE_PEER,
        aggregate_type="subscription",
        aggregate_id=uuid.uuid4(),
        payload={"foo": "bar"},
    )
    assert job.status == JobStatus.PENDING

    # Claim job
    claimed = await job_repo.claim_pending_jobs(worker_id="worker-1", limit=10)
    assert len(claimed) == 1
    assert claimed[0].id == job.id

    # Mark retryable failure
    failed_job = await job_repo.mark_failed(job.id, "SSH timeout", is_retryable=True, max_retries=3)
    assert failed_job.status == JobStatus.RETRYABLE_FAILURE
    assert failed_job.attempt_count == 1

    # Exceed max retries
    await job_repo.mark_failed(job.id, "SSH timeout", is_retryable=True, max_retries=1)
    perm_failed = await job_repo.get_by_id(job.id)
    assert perm_failed.status == JobStatus.PERMANENT_FAILURE


@pytest.mark.asyncio
async def test_support_ticket_repository(session: AsyncSession):
    user_repo = UserRepository(session)
    ticket_repo = TicketRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=888, username="support_seeker")
    ticket = await ticket_repo.create_ticket(
        user_id=user.id,
        subject="VPN setup help",
        initial_message="How do I import into Amnezia app?",
        sender_telegram_user_id=888,
    )
    assert ticket.public_ticket_code.startswith("TCK-")
    assert ticket.status == TicketStatus.WAITING_FOR_ADMIN

    by_code = await ticket_repo.get_by_code(ticket.public_ticket_code)
    assert by_code is not None

    active_ticket = await ticket_repo.get_active_ticket_for_user(user.id)
    assert active_ticket is not None

    open_tickets = await ticket_repo.list_open_tickets()
    assert len(open_tickets) == 1

    # Admin reply
    msg = await ticket_repo.add_message(
        ticket_id=ticket.id,
        sender_type=SenderType.ADMIN,
        sender_telegram_user_id=111,
        body="Download the .vpn file attached and click + in the app.",
    )
    assert msg.id is not None
    
    updated_ticket = await ticket_repo.get_by_id(ticket.id)
    assert updated_ticket.status == TicketStatus.WAITING_FOR_CUSTOMER

    # Close & Reopen
    await ticket_repo.close_ticket(ticket.id)
    closed = await ticket_repo.get_by_id(ticket.id)
    assert closed.status == TicketStatus.CLOSED

    await ticket_repo.reopen_ticket(ticket.id)
    reopened = await ticket_repo.get_by_id(ticket.id)
    assert reopened.status == TicketStatus.OPEN


@pytest.mark.asyncio
async def test_audit_and_notification_repository(session: AsyncSession):
    audit_repo = AuditRepository(session)
    notif_repo = NotificationRepository(session)
    user_repo = UserRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=333, username="notif_user")
    entity_id = uuid.uuid4()
    await audit_repo.record_event(
        actor_type=ActorType.ADMIN,
        actor_telegram_user_id=111,
        event_type="order.approved",
        entity_type="order",
        entity_id=entity_id,
        metadata={"order_code": "ORD-123", "secret_key": "MUST_NOT_BE_HERE"},
    )

    events = await audit_repo.list_for_entity("order", entity_id)
    assert len(events) == 1
    assert events[0].event_type == "order.approved"

    # Notification
    notif, created = await notif_repo.create_notification_if_not_exists(
        user_id=user.id,
        notification_type=NotificationType.EXPIRES_3D,
        idempotency_key="sub_999_3d",
    )
    assert created is True
    assert notif.idempotency_key == "sub_999_3d"

    # Duplicate
    notif2, created2 = await notif_repo.create_notification_if_not_exists(
        user_id=user.id,
        notification_type=NotificationType.EXPIRES_3D,
        idempotency_key="sub_999_3d",
    )
    assert created2 is False
    assert notif2 is None
