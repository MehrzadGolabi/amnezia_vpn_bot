import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from src.app.db.models.server import VPNServer


@dataclass
class ProvisionedPeer:
    external_id: str
    label: str
    config_filename: str
    config_bytes: bytes
    created_at: datetime
    vpn_url: Optional[str] = None


@dataclass
class PeerStatus:
    exists: bool
    is_active: bool
    last_handshake: Optional[datetime] = None
    bytes_received: int = 0
    bytes_sent: int = 0
    raw_status: Optional[str] = None


@runtime_checkable
class VPNProvisioner(Protocol):
    async def create_peer(
        self,
        *,
        server: VPNServer,
        subscription_id: uuid.UUID,
        telegram_user_id: int,
        device_name: str = "default",
    ) -> ProvisionedPeer:
        ...

    async def disable_peer(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> None:
        ...

    async def remove_peer(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> None:
        ...

    async def get_peer_status(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> PeerStatus:
        ...

    async def get_peer_config(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> bytes:
        ...
