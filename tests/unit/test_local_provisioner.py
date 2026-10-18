"""The bot's provisioner and worker, end to end against a sandboxed AWG 3.1 server."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.db.models.base import Base
from src.app.db.models.job import JobStatus, JobType
from src.app.db.models.order import OrderStatus
from src.app.db.models.server import VPNServer
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.repositories.job_repo import JobRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.db.repositories.user_repo import UserRepository
from src.app.integrations.provisioning import vpnctl_client
from src.app.integrations.provisioning.vpnctl_client import (
    PermanentProvisioningError,
    RetryableProvisioningError,
    VpnctlProvisioner,
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
    prov = VpnctlProvisioner(dev_command=awg_sandbox.vpnctl_command)
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
    prov = VpnctlProvisioner(dev_command=awg_sandbox.vpnctl_command)
    with pytest.raises(RetryableProvisioningError, match="Server config not found"):
        await prov.create_peer(server=server, subscription_id=uuid.uuid4(), telegram_user_id=1)

    missing = VpnctlProvisioner(dev_command="/nonexistent/vpnctl")
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
        provisioner=VpnctlProvisioner(dev_command=awg_sandbox.vpnctl_command),
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


async def test_other_hosts_are_reached_over_tcp(awg_sandbox, server, monkeypatch):
    prov = VpnctlProvisioner(dev_command=awg_sandbox.vpnctl_command)
    calls = []

    async def fake_open_connection(host, port):
        calls.append((host, port))
        raise OSError("no route")

    monkeypatch.setattr(vpnctl_client.asyncio, "open_connection", fake_open_connection)
    remote = VPNServer(slug="tr-1", display_name="Turkey", country_code="TR", host="100.64.0.2")
    with pytest.raises(RetryableProvisioningError, match="no route"):
        await prov.disable_peer(server=remote, peer_external_id="x")
    assert calls == [("100.64.0.2", 7391)]

    # The server with no remote HOST still runs vpnctl on this machine.
    await prov.create_peer(server=server, subscription_id=uuid.uuid4(), telegram_user_id=7)
    assert len(awg_sandbox.live_peers()) == 1
    assert len(calls) == 1


async def test_renewal_extends_the_same_peer(awg_sandbox, session):
    user = await UserRepository(session).upsert_user(telegram_user_id=778, username="renewer")
    server = await ServerRepository(session).create_or_update(
        slug="de-1", display_name="Germany", country_code="DE", host="localhost")
    product = await ProductRepository(session).create_or_update(
        code="vpn-1m", title="1 Month", duration_days=30, device_limit=1,
        price_amount=Decimal("5.00"), price_currency="EUR")
    order_repo = OrderRepository(session)
    first = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub, _ = await order_repo.approve_order_atomic(first.id, admin_telegram_id=1)
    await session.commit()

    worker = WorkerEngine(
        session_factory=lambda: session,
        provisioner=VpnctlProvisioner(dev_command=awg_sandbox.vpnctl_command),
        bot=AsyncMock(),
    )
    assert await worker.run_single_batch() == 1
    peers_before = dict(awg_sandbox.live_peers())

    # It runs out and the scheduler's disable job turns the peer off.
    sub = await SubscriptionRepository(session).get_by_id(sub.id)
    sub.status = SubscriptionStatus.EXPIRED
    sub.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    job_repo = JobRepository(session)
    await job_repo.enqueue_job(job_type=JobType.DISABLE_PEER, aggregate_type="subscription",
                               aggregate_id=sub.id, payload={"reason": "subscription_expired"})
    await session.commit()
    assert await worker.run_single_batch() == 1
    assert awg_sandbox.live_peers() == {}
    old_expiry = (await SubscriptionRepository(session).get_by_id(sub.id)).expires_at

    renewal = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay",
                                            renews_subscription_id=sub.id)
    ok, renewed, job = await order_repo.approve_order_atomic(renewal.id, admin_telegram_id=1)
    await session.commit()
    assert ok and renewed.id == sub.id and job.job_type == JobType.ENABLE_PEER
    assert renewed.status == SubscriptionStatus.ACTIVE
    assert renewed.expires_at.replace(tzinfo=None) > old_expiry.replace(tzinfo=None)
    assert (await order_repo.get_by_id(renewal.id)).status == OrderStatus.FULFILLED

    # Approving twice does nothing.
    again, _, _ = await order_repo.approve_order_atomic(renewal.id, admin_telegram_id=1)
    assert again is False

    assert await worker.run_single_batch() == 1
    assert awg_sandbox.live_peers() == peers_before  # same key, same address, no new config

    # A disable job the scheduler queued before the renewal doesn't undo it.
    await job_repo.enqueue_job(job_type=JobType.DISABLE_PEER, aggregate_type="subscription",
                               aggregate_id=sub.id, payload={"reason": "subscription_expired"})
    await session.commit()
    assert await worker.run_single_batch() == 1
    assert awg_sandbox.live_peers() == peers_before
