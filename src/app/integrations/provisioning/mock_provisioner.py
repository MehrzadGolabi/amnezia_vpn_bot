import base64
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.base import PeerStatus, ProvisionedPeer, VPNProvisioner
from src.app.utils.amnezia_codec import encode_vpn_url


class MockProvisioner(VPNProvisioner):
    """
    Mock implementation of VPNProvisioner for testing and development environments.
    Simulates AmneziaWG configuration generation in memory without network/SSH dependencies.
    """

    def __init__(self):
        # In-memory storage: peer_external_id -> dict
        self._peers: Dict[str, dict] = {}

    def _generate_key(self) -> str:
        return base64.b64encode(secrets.token_bytes(32)).decode("ascii")

    async def create_peer(
        self,
        *,
        server: VPNServer,
        subscription_id: uuid.UUID,
        telegram_user_id: int,
        device_name: str = "default",
    ) -> ProvisionedPeer:
        external_id = f"peer_{uuid.uuid4().hex[:12]}"
        label = f"user_{telegram_user_id}_{server.slug}"
        filename = f"{label}.conf"

        priv_key = self._generate_key()
        pub_key = self._generate_key()
        psk = self._generate_key()
        server_pub_key = self._generate_key()

        # Simulated AmneziaWG 3.1 client config, shaped like what vpnctl produces
        config_content = (
            f"[Interface]\n"
            f"PrivateKey = {priv_key}\n"
            f"Address = 10.66.66.{secrets.randbelow(200) + 2}/32\n"
            f"DNS = 1.1.1.1, 9.9.9.9\n"
            f"MTU = 1280\n"
            f"Jc = 6\n"
            f"Jmin = 96\n"
            f"Jmax = 512\n"
            f"S1 = 15\n"
            f"S2 = 15\n"
            f"S3 = 15\n"
            f"S4 = 15\n"
            f"H1 = 1\n"
            f"H2 = 2\n"
            f"H3 = 3\n"
            f"H4 = 4\n"
            f"I1 = <r 64><t><rc 12>\n"
            f"HeaderProtectionKey = {self._generate_key()}\n"
            f"RandomTrailers = 1\n"
            f"DisableCookies = 1\n\n"
            f"[Peer]\n"
            f"PublicKey = {server_pub_key}\n"
            f"PresharedKey = {psk}\n"
            f"AllowedIPs = 0.0.0.0/0, ::/0\n"
            f"Endpoint = {server.host}:51820\n"
            f"PersistentKeepalive = 25\n"
        )
        config_bytes = config_content.encode("utf-8")
        now = datetime.now(timezone.utc)
        vpn_url = encode_vpn_url(config_content)

        self._peers[external_id] = {
            "external_id": external_id,
            "label": label,
            "filename": filename,
            "config_bytes": config_bytes,
            "is_active": True,
            "created_at": now,
            "vpn_url": vpn_url,
        }

        return ProvisionedPeer(
            external_id=external_id,
            label=label,
            config_filename=filename,
            config_bytes=config_bytes,
            created_at=now,
            vpn_url=vpn_url,
        )

    async def disable_peer(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> None:
        if peer_external_id in self._peers:
            self._peers[peer_external_id]["is_active"] = False

    async def remove_peer(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> None:
        self._peers.pop(peer_external_id, None)

    async def get_peer_status(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> PeerStatus:
        peer = self._peers.get(peer_external_id)
        if not peer:
            return PeerStatus(exists=False, is_active=False)

        return PeerStatus(
            exists=True,
            is_active=peer.get("is_active", True),
            last_handshake=datetime.now(timezone.utc),
            bytes_received=1024 * 1024 * 50,  # 50MB
            bytes_sent=1024 * 1024 * 120,     # 120MB
            raw_status="mock_online",
        )

    async def get_peer_config(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> bytes:
        peer = self._peers.get(peer_external_id)
        if not peer:
            raise KeyError(f"Peer {peer_external_id} not found")
        return peer["config_bytes"]
