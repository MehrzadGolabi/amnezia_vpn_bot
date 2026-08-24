import pytest
import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.app.db.models.base import Base
from src.app.db.models.subscription import SubscriptionStatus
from src.app.db.repositories.user_repo import UserRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.order_repo import OrderRepository
from src.app.db.repositories.subscription_repo import SubscriptionRepository
from src.app.integrations.provisioning.mock_provisioner import MockProvisioner
from src.app.utils.health import check_system_health
from src.app.utils.reconciliation import reconcile_server_peers, ReconciliationReport


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
async def test_system_health_check(session: AsyncSession):
    health = await check_system_health(session)
    assert health["status"] == "ok"
    assert health["db_healthy"] is True
    assert "timestamp" in health


@pytest.mark.asyncio
async def test_peer_reconciliation(session: AsyncSession):
    user_repo = UserRepository(session)
    server_repo = ServerRepository(session)
    product_repo = ProductRepository(session)
    order_repo = OrderRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.upsert_user(telegram_user_id=123, username="recon_user")
    server = await server_repo.create_or_update(
        slug="nl-recon",
        display_name="NL Recon",
        country_code="NL",
        country_name="Netherlands",
        host="localhost",
        enabled=True,
    )
    product = await product_repo.create_or_update(
        code="vpn-1m",
        title="1 Month",
        duration_days=30,
        device_limit=1,
        price_amount=Decimal("5.00"),
        price_currency="EUR",
    )

    # Sub 1: Active
    order1 = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub1, _ = await order_repo.approve_order_atomic(order1.id, 111)
    await sub_repo.mark_active(sub1.id, "peer-1", "user_123_nl1")

    # Sub 2: Active in DB, but missing on server
    order2 = await order_repo.create_order(user.id, server.id, product.id, product.price_amount, "EUR", "Pay")
    _, sub2, _ = await order_repo.approve_order_atomic(order2.id, 111)
    await sub_repo.mark_active(sub2.id, "peer-2", "user_123_nl2")

    # Mock provisioner has peer-1 and an orphaned peer-999
    provisioner = MockProvisioner()
    provisioner._peers["peer-1"] = {"is_active": True}
    provisioner._peers["peer-orphan"] = {"is_active": True}

    report: ReconciliationReport = await reconcile_server_peers(
        session=session,
        server_slug=server.slug,
        provisioner=provisioner,
    )

    assert "peer-1" in report.matched_peers
    assert "peer-2" in report.missing_on_server
    assert "peer-orphan" in report.orphaned_on_server
    assert report.total_db_active == 2
    assert report.total_server_peers == 2
