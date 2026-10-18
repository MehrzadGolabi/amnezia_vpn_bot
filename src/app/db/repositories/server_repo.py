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

    async def list_on_sale(self) -> List[VPNServer]:
        """Servers turned on in .env and not paused. Some may be full; see has_room()."""
        stmt = (
            select(VPNServer)
            .where(VPNServer.enabled.is_(True), VPNServer.paused.is_(False))
            .order_by(VPNServer.sort_order, VPNServer.slug)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def set_paused(self, slug: str, paused: bool) -> Optional[VPNServer]:
        server = await self.get_by_slug(slug)
        if server:
            server.paused = paused
            await self.session.flush()
        return server

    async def create_or_update(
        self,
        slug: str,
        display_name: str,
        country_code: str,
        country_name: str = "",
        host: str = "localhost",
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
            # `paused` is left alone: it belongs to the /servers button, not to .env.
            server.enabled = enabled
            server.sort_order = sort_order
            server.provisioner_type = provisioner_type
            server.max_active_subscriptions = max_active_subscriptions
        await self.session.flush()
        return server

    async def count_active_subscriptions(self, server_id: uuid.UUID) -> int:
        """Subscriptions that hold a slot: active ones, and ones whose peer is being made."""
        stmt = select(func.count(Subscription.id)).where(
            Subscription.vpn_server_id == server_id,
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PROVISIONING]),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one() or 0

    async def has_room(self, server: VPNServer) -> bool:
        """False once MAX_ACTIVE_SUBSCRIPTIONS is reached. No limit set means always room."""
        if not server.max_active_subscriptions:
            return True
        return await self.count_active_subscriptions(server.id) < server.max_active_subscriptions

    async def list_for_sale(self) -> List[VPNServer]:
        """What the buy menu offers: on sale and not full."""
        return [s for s in await self.list_on_sale() if await self.has_room(s)]
