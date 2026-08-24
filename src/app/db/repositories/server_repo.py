import uuid
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.server import VPNServer
from src.app.db.models.subscription import Subscription, SubscriptionStatus


class ServerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, server_id: uuid.UUID) -> Optional[VPNServer]:
        return await self.session.get(VPNServer, server_id)

    async def get_by_slug(self, slug: str) -> Optional[VPNServer]:
        stmt = select(VPNServer).where(VPNServer.slug == slug)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_all(self) -> List[VPNServer]:
        stmt = select(VPNServer).order_by(VPNServer.sort_order, VPNServer.slug)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_enabled(self) -> List[VPNServer]:
        stmt = select(VPNServer).where(VPNServer.enabled.is_(True)).order_by(VPNServer.sort_order, VPNServer.slug)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def set_enabled(self, slug: str, enabled: bool) -> Optional[VPNServer]:
        server = await self.get_by_slug(slug)
        if server:
            server.enabled = enabled
            await self.session.flush()
        return server

    async def create_or_update(
        self,
        slug: str,
        display_name: str,
        country_code: str,
        country_name: str = "",
        host: str = "localhost",
        ssh_port: int = 22,
        ssh_username: str = "vpn-provisioner",
        enabled: bool = True,
        sort_order: int = 0,
        provisioner_type: str = "mock",
        max_active_subscriptions: Optional[int] = None,
    ) -> VPNServer:
        server = await self.get_by_slug(slug)
        if server is None:
            server = VPNServer(
                slug=slug,
                display_name=display_name,
                country_code=country_code,
                country_name=country_name,
                host=host,
                ssh_port=ssh_port,
                ssh_username=ssh_username,
                enabled=enabled,
                sort_order=sort_order,
                provisioner_type=provisioner_type,
                max_active_subscriptions=max_active_subscriptions,
            )
            self.session.add(server)
        else:
            server.display_name = display_name
            server.country_code = country_code
            server.country_name = country_name
            server.host = host
            server.ssh_port = ssh_port
            server.ssh_username = ssh_username
            server.enabled = enabled
            server.sort_order = sort_order
            server.provisioner_type = provisioner_type
            server.max_active_subscriptions = max_active_subscriptions
        await self.session.flush()
        return server

    async def count_active_subscriptions(self, server_id: uuid.UUID) -> int:
        stmt = select(func.count(Subscription.id)).where(
            Subscription.vpn_server_id == server_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0
