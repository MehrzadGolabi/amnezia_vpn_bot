from dataclasses import dataclass, field
from typing import List, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.server import VPNServer
from src.app.db.models.subscription import Subscription, SubscriptionStatus
from src.app.integrations.provisioning.base import VPNProvisioner


@dataclass
class ReconciliationReport:
    server_slug: str
    total_db_active: int
    total_server_peers: int
    matched_peers: List[str] = field(default_factory=list)
    missing_on_server: List[str] = field(default_factory=list)
    orphaned_on_server: List[str] = field(default_factory=list)


async def reconcile_server_peers(
    session: AsyncSession,
    server_slug: str,
    provisioner: VPNProvisioner,
) -> ReconciliationReport:
    # Fetch server
    stmt_server = select(VPNServer).where(VPNServer.slug == server_slug)
    res_server = await session.execute(stmt_server)
    server = res_server.scalar_one_or_none()
    if not server:
        raise ValueError(f"Server with slug '{server_slug}' not found.")

    # Fetch all active subscriptions for this server
    stmt_subs = select(Subscription).where(
        Subscription.vpn_server_id == server.id,
        Subscription.status == SubscriptionStatus.ACTIVE,
    )
    res_subs = await session.execute(stmt_subs)
    active_subs = list(res_subs.scalars().all())

    db_peer_ids: Set[str] = {s.peer_external_id for s in active_subs if s.peer_external_id}

    # Query provisioner peers
    server_peer_ids: Set[str] = set()
    if hasattr(provisioner, "_peers"):
        server_peer_ids = set(provisioner._peers.keys())
    elif hasattr(provisioner, "peers"):
        server_peer_ids = set(provisioner.peers.keys())

    matched = sorted(list(db_peer_ids.intersection(server_peer_ids)))
    missing = sorted(list(db_peer_ids - server_peer_ids))
    orphaned = sorted(list(server_peer_ids - db_peer_ids))

    return ReconciliationReport(
        server_slug=server_slug,
        total_db_active=len(db_peer_ids),
        total_server_peers=len(server_peer_ids),
        matched_peers=matched,
        missing_on_server=missing,
        orphaned_on_server=orphaned,
    )
