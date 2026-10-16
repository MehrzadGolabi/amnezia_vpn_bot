"""The bot's provisioner and worker, end to end against a sandboxed AWG 3.1 server."""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.db.models.base import Base
from src.app.db.models.job import JobStatus, JobType
from src.app.db.models.server import VPNServer
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.user_repo import UserRepository
from src.app.integrations.provisioning.ssh_provisioner import (
    LocalCommandProvisioner,
    PermanentProvisioningError,
    RetryableProvisioningError,
)
from src.app.utils.amnezia_codec import decode_vpn_url
from src.app.worker.engine import WorkerEngine


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def server():
    return VPNServer(slug="de-1", display_name="Germany", country_code="DE", host="localhost")


async def test_local_provisioner_lifecycle(awg_sandbox, server):
    prov = LocalCommandProvisioner(vpnctl_command=awg_sandbox.vpnctl_command)
    sub_id = uuid.uuid4()

    peer = await prov.create_peer(server=server, subscription_id=sub_id, telegram_user_id=42)
    assert peer.external_id == peer.label == f"user_42_{str(sub_id)[:8]}_de-1"
    config = peer.config_bytes.decode()
    assert "HeaderProtectionKey = " in config and "RandomTrailers = 1" in config
    assert decode_vpn_url(peer.vpn_url) == config

    # A retried create returns the same peer instead of making a second one.
    again = await prov.create_peer(server=server, subscription_id=sub_id, telegram_user_id=42)
    assert again.config_bytes == peer.config_bytes
    assert len(awg_sandbox.live_peers()) == 1

    assert await prov.get_peer_config(server=server, peer_external_id=peer.external_id) == peer.config_bytes
    status = await prov.get_peer_status(server=server, peer_external_id=peer.external_id)
    assert status.exists is True

    await prov.disable_peer(server=server, peer_external_id=peer.external_id)
    assert awg_sandbox.live_peers() == {}
    await prov.remove_peer(server=server, peer_external_id=peer.external_id)
    status = await prov.get_peer_status(server=server, peer_external_id=peer.external_id)
    assert status.exists is False
    with pytest.raises(PermanentProvisioningError):
        await prov.get_peer_config(server=server, peer_external_id=peer.external_id)


async def test_local_provisioner_error_classes(awg_sandbox, server):
    awg_sandbox.server_conf.unlink()
    prov = LocalCommandProvisioner(vpnctl_command=awg_sandbox.vpnctl_command)
    with pytest.raises(RetryableProvisioningError, match="Server config not found"):
        await prov.create_peer(server=server, subscription_id=uuid.uuid4(), telegram_user_id=1)

    missing = LocalCommandProvisioner(vpnctl_command="/nonexistent/vpnctl")
    with pytest.raises(PermanentProvisioningError):
        await missing.disable_peer(server=server, peer_external_id="x")


async def test_worker_provisions_and_expires_on_sandbox(awg_sandbox, session):
    user = await UserRepository(session).upsert_user(telegram_user_id=777, username="buyer")
    server = await ServerRepository(session).create_or_update(
        slug="de-1", display_name="Germany", country_code="DE", host="localhost")
    product = await ProductRepository(session).create_or_update(
        code="vpn-1m", title="1 Month", duration_days=30, device_limit=1,
        price_amount=Decimal("5.00"), price_currency="EUR")
    order_repo = OrderRepository(session)
    order = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(order.id, admin_telegram_id=1)

    bot = AsyncMock()
    worker = WorkerEngine(
        session_factory=lambda: session,
        provisioner=LocalCommandProvisioner(vpnctl_command=awg_sandbox.vpnctl_command),
        bot=bot,
    )
    assert await worker.run_single_batch() == 1

    sub = await SubscriptionRepository(session).get_by_id(sub.id)
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.config_delivery_status == "delivered"
    sent_doc = bot.send_document.call_args.kwargs
    assert sent_doc["chat_id"] == 777
    assert b"HeaderProtectionKey" in sent_doc["document"].data
    assert len(sent_doc["caption"]) < 1024
    assert "vpn://" in bot.send_message.call_args.kwargs["text"]
    assert f"# {sub.peer_external_id}\n" in awg_sandbox.server_conf.read_text()

    job_repo = JobRepository(session)
    for job_type in (JobType.DISABLE_PEER, JobType.REMOVE_PEER):
        job = await job_repo.enqueue_job(job_type=job_type, aggregate_type="subscription",
                                         aggregate_id=sub.id, payload={})
        await session.commit()
        assert await worker.run_single_batch() == 1
        assert (await job_repo.get_by_id(job.id)).status == JobStatus.SUCCEEDED

    assert awg_sandbox.live_peers() == {}
    assert f"# {sub.peer_external_id}" not in awg_sandbox.server_conf.read_text()
    assert list(awg_sandbox.clients.iterdir()) == []
