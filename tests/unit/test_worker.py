import pytest
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base, utc_now
from src.app.db.models.order import OrderStatus
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.models.job import JobType, JobStatus
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.job_repo import JobRepository

from src.app.integrations.provisioning.mock_provisioner import MockProvisioner
from src.app.integrations.provisioning.ssh_provisioner import RetryableProvisioningError, PermanentProvisioningError
from src.app.worker.engine import WorkerEngine


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
async def test_worker_process_create_peer(session: AsyncSession):
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
    _, sub, job = await order_repo.approve_order_atomic(order.id, admin_telegram_id=111)

    mock_bot = AsyncMock()
    mock_provisioner = MockProvisioner()

    worker = WorkerEngine(
        session_factory=lambda: session,
        provisioner=mock_provisioner,
        bot=mock_bot,
        worker_id="test-worker",
    )

    # Process job
    processed_count = await worker.run_single_batch()
    assert processed_count == 1

    # Verify job status
    updated_job = await job_repo.get_by_id(job.id)
    assert updated_job.status == JobStatus.SUCCEEDED

    # Verify subscription status
    updated_sub = await sub_repo.get_by_id(sub.id)
    assert updated_sub.status == SubscriptionStatus.ACTIVE
    assert updated_sub.peer_external_id is not None

    # Verify order fulfilled
    updated_order = await order_repo.get_by_id(order.id)
    assert updated_order.status == OrderStatus.FULFILLED

    # Verify bot sent document
    mock_bot.send_document.assert_called_once()


@pytest.mark.asyncio
async def test_worker_process_disable_and_remove(session: AsyncSession):
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
    _, sub, _ = await order_repo.approve_order_atomic(order.id, 111)
    await sub_repo.mark_active(sub.id, "peer_123", "user_12345_de1")

    mock_bot = AsyncMock()
    mock_provisioner = MockProvisioner()

    worker = WorkerEngine(
        session_factory=lambda: session,
        provisioner=mock_provisioner,
        bot=mock_bot,
        worker_id="test-worker",
    )

    # Enqueue disable job
    disable_job = await job_repo.enqueue_job(
        job_type=JobType.DISABLE_PEER,
        aggregate_type="subscription",
        aggregate_id=sub.id,
        payload={"server_slug": "de-1", "peer_external_id": "peer_123"},
    )

    # Claim & process (first job was create_peer, second is disable_peer)
    await worker.run_single_batch()
    updated_disable_job = await job_repo.get_by_id(disable_job.id)
    assert updated_disable_job.status == JobStatus.SUCCEEDED
    assert (await sub_repo.get_by_id(sub.id)).status == SubscriptionStatus.DISABLED

    # Enqueue remove job
    remove_job = await job_repo.enqueue_job(
        job_type=JobType.REMOVE_PEER,
        aggregate_type="subscription",
        aggregate_id=sub.id,
        payload={"server_slug": "de-1", "peer_external_id": "peer_123"},
    )

    await worker.run_single_batch()
    updated_remove_job = await job_repo.get_by_id(remove_job.id)
    assert updated_remove_job.status == JobStatus.SUCCEEDED
    assert (await sub_repo.get_by_id(sub.id)).status == SubscriptionStatus.EXPIRED


@pytest.mark.asyncio
async def test_worker_process_redeliver_config(session: AsyncSession):
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
    _, sub, create_job = await order_repo.approve_order_atomic(order.id, 111)

    mock_provisioner = MockProvisioner()
    mock_bot = AsyncMock()
    worker = WorkerEngine(
        session_factory=lambda: session,
        provisioner=mock_provisioner,
        bot=mock_bot,
        worker_id="test-worker",
    )

    # First process the create_job
    await worker.run_single_batch()
    assert mock_bot.send_document.call_count == 1

    # Now enqueue redeliver job
    redeliver_job = await job_repo.enqueue_job(
        job_type=JobType.REDELIVER_CONFIG,
        aggregate_type="subscription",
        aggregate_id=sub.id,
        payload={},
    )

    await worker.run_single_batch()
    updated_job = await job_repo.get_by_id(redeliver_job.id)
    assert updated_job.status == JobStatus.SUCCEEDED
    assert mock_bot.send_document.call_count == 2


@pytest.mark.asyncio
async def test_worker_retryable_and_permanent_errors(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    job_repo = JobRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=54321, username="retry_user")
    server = await server_repo.create_or_update(slug="de-err", display_name="Germany", country_code="DE", country_name="Germany", host="de.test")
    product = await product_repo.create_or_update(code="vpn-err", title="1 Month", duration_days=30, device_limit=1, price_amount=Decimal("5.00"), price_currency="EUR")
    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, job = await order_repo.approve_order_atomic(order.id, 111)

    mock_provisioner = MagicMock()
    mock_provisioner.create_peer = AsyncMock(side_effect=RetryableProvisioningError("Connection timeout"))
    mock_bot = AsyncMock()

    worker = WorkerEngine(
        session_factory=lambda: session,
        provisioner=mock_provisioner,
        bot=mock_bot,
        worker_id="test-worker",
        admin_chat_id=-100123,
    )

    # Retryable error
    await worker.run_single_batch()
    updated_job = await job_repo.get_by_id(job.id)
    assert updated_job.status == JobStatus.RETRYABLE_FAILURE
    assert updated_job.attempt_count == 1

    # Permanent error
    mock_provisioner.create_peer = AsyncMock(side_effect=PermanentProvisioningError("Invalid peer configuration"))
    updated_job.status = JobStatus.PENDING
    updated_job.available_at = utc_now()
    await session.commit()

    await worker.run_single_batch()
    perm_job = await job_repo.get_by_id(job.id)
    assert perm_job.status == JobStatus.PERMANENT_FAILURE
    mock_bot.send_message.assert_called_once()
