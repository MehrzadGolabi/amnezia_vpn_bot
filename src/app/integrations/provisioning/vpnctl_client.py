import asyncio
import base64
import json
import re
import shlex
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from src.app.config.settings import get_settings
from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.base import PeerStatus, ProvisionedPeer, VPNProvisioner
from src.app.utils.amnezia_codec import encode_vpn_url
from src.app.utils.logging import get_logger

logger = get_logger(__name__)

IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
DEFAULT_SOCKET_PATH = "/run/vpnctl/vpnctl.sock"
DEFAULT_VPNCTL_PORT = 7391
# A client config is a few hundred bytes; anything near this is not a vpnctl reply.
MAX_RESPONSE_BYTES = 1024 * 1024
# vpnctl answers 2 for bad input, 3 for an unknown client and 4 for a caller it
# doesn't allow. Retrying can't help with any of them.
VPNCTL_PERMANENT_EXITS = (2, 3, 4)
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


class ProvisioningError(Exception):
    """Base error for provisioning operations."""
    pass


class RetryableProvisioningError(ProvisioningError):
    """Temporary or network error that can be retried."""
    pass


class PermanentProvisioningError(ProvisioningError):
    """Fatal configuration or validation error that should not be retried automatically."""
    pass


def sanitize_identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_REGEX.match(value):
        raise ValueError(f"Invalid identifier: {value!r}. Must match regex {IDENTIFIER_REGEX.pattern}")
    return value


def is_local_host(host: Optional[str]) -> bool:
    return (host or "").strip().lower() in LOCAL_HOSTS


class VpnctlProvisioner(VPNProvisioner):
    """
    Talks to scripts/provisioner/vpnctl, which manages clients on a native
    amneziawg-go + awg-quick server. Each call is one JSON request and one JSON
    response, answered by `vpnctl serve`:

    - on this host, over the Unix socket systemd keeps at /run/vpnctl/vpnctl.sock;
    - on another VPN host, over TCP to its Tailscale address (VPN_SERVER_<NAME>_HOST),
      with VPNCTL_TOKEN, because the address alone proves only which machine is calling;
    - in development, by running `dev_command` (for example against scripts/dev/sandbox.sh)
      with the request on stdin.

    No SSH and no sudo: the socket's permissions, or vpnctl's ALLOWED_CLIENTS and token,
    decide who may ask, and systemd runs vpnctl as root in a sandbox.
    """

    def __init__(
        self,
        *,
        socket_path: Optional[str] = None,
        dev_command: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30,
    ):
        settings = get_settings()
        if token is None:
            secret = getattr(settings, "VPNCTL_TOKEN", None)
            token = secret.get_secret_value() if secret is not None else ""
        self.token = token
        self.socket_path = socket_path or getattr(settings, "VPNCTL_SOCKET", None) or DEFAULT_SOCKET_PATH
        command = dev_command if dev_command is not None else getattr(settings, "VPNCTL_DEV_COMMAND", "")
        self.dev_command: List[str] = shlex.split(command) if command else []
        self.timeout = timeout

    # --- transports ---

    async def _exchange(self, server: VPNServer, request: bytes) -> bytes:
        if is_local_host(server.host):
            if self.dev_command:
                return await self._exchange_command(request)
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
        else:
            server_cfg = get_settings().vpn_servers.get(server.slug)
            port = server_cfg.vpnctl_port if server_cfg else DEFAULT_VPNCTL_PORT
            reader, writer = await asyncio.open_connection(server.host, port)
        try:
            writer.write(request)
            await writer.drain()
            writer.write_eof()
            response = b""
            while len(response) <= MAX_RESPONSE_BYTES:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                response += chunk
            return response
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _exchange_command(self, request: bytes) -> bytes:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.dev_command, "serve",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as e:
            raise PermanentProvisioningError(f"Cannot run vpnctl ({self.dev_command[0]}): {e}") from e
        try:
            out, _ = await proc.communicate(request)
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        return out

    async def _call(self, server: VPNServer, command: str, **args: str) -> Tuple[int, dict, str]:
        """Returns (exit_code, result, error) from vpnctl on the server."""
        body = {"command": command, "args": args}
        if not is_local_host(server.host) and self.token:
            body["token"] = self.token  # only over TCP; the local socket checks permissions
        request = (json.dumps(body) + "\n").encode("utf-8")
        try:
            raw = await asyncio.wait_for(self._exchange(server, request), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise RetryableProvisioningError(f"vpnctl on {server.slug} timed out after {self.timeout}s") from e
        except OSError as e:
            logger.error("vpnctl_connection_error", server=server.slug, error=str(e))
            raise RetryableProvisioningError(f"Cannot reach vpnctl on {server.slug}: {e}") from e

        if len(raw) > MAX_RESPONSE_BYTES:
            raise RetryableProvisioningError(f"Response from vpnctl on {server.slug} is too large")
        try:
            response = json.loads(raw.decode("utf-8"))
            exit_code = int(response["exit_code"])
            result = response.get("result", {})
            error = str(response.get("error") or "")
            if not isinstance(result, dict):
                raise ValueError("result is not an object")
        except (UnicodeDecodeError, ValueError, KeyError, TypeError) as e:
            # Not the response itself: it can hold config_b64, the client's private key.
            logger.error("invalid_vpnctl_output", server=server.slug, response_bytes=len(raw), error=str(e))
            raise RetryableProvisioningError(f"Malformed response from vpnctl: {e}") from e
        return exit_code, result, error

    @staticmethod
    def _classify_failure(exit_code: int, error: str) -> ProvisioningError:
        err_msg = error.strip() or f"vpnctl failed with exit code {exit_code}"
        if exit_code in VPNCTL_PERMANENT_EXITS or "already exists" in err_msg.lower():
            return PermanentProvisioningError(err_msg)
        return RetryableProvisioningError(err_msg)

    async def _run_checked(self, server: VPNServer, event: str, command: str, **args: str) -> dict:
        exit_code, result, error = await self._call(server, command, **args)
        if exit_code != 0:
            failure = self._classify_failure(exit_code, error)
            logger.error(event, server=server.slug, error=str(failure))
            raise failure
        return result

    # --- VPNProvisioner ---

    async def create_peer(
        self,
        *,
        server: VPNServer,
        subscription_id: uuid.UUID,
        telegram_user_id: int,
        device_name: str = "default",
    ) -> ProvisionedPeer:
        safe_sub_id = str(uuid.UUID(str(subscription_id)))
        safe_label = sanitize_identifier(f"user_{telegram_user_id}_{safe_sub_id[:8]}_{server.slug}")

        data = await self._run_checked(
            server, "provisioning_create_peer_failed",
            "create-peer", subscription_id=safe_sub_id, label=safe_label,
        )
        try:
            # A VPN host may be compromised, so only the config itself is taken from it.
            # The filename and vpn:// link are built here, never copied from its reply.
            peer_id = sanitize_identifier(data["peer_id"])
            label = sanitize_identifier(data.get("label", safe_label))
            filename = f"{label}.conf"
            config_bytes = base64.b64decode(data["config_b64"], validate=True)
            vpn_url = encode_vpn_url(config_bytes.decode("utf-8")) if config_bytes else None
        except Exception as e:
            logger.error("invalid_vpnctl_output", server=server.slug, error=str(e))
            raise RetryableProvisioningError(f"Malformed response from vpnctl: {e}") from e

        return ProvisionedPeer(
            external_id=peer_id,
            label=label,
            config_filename=filename,
            config_bytes=config_bytes,
            created_at=datetime.now(timezone.utc),
            vpn_url=vpn_url,
        )

    async def disable_peer(self, *, server: VPNServer, peer_external_id: str) -> None:
        await self._run_checked(
            server, "provisioning_disable_peer_failed",
            "disable-peer", peer_id=sanitize_identifier(peer_external_id),
        )

    async def enable_peer(self, *, server: VPNServer, peer_external_id: str) -> None:
        await self._run_checked(
            server, "provisioning_enable_peer_failed",
            "enable-peer", peer_id=sanitize_identifier(peer_external_id),
        )

    async def remove_peer(self, *, server: VPNServer, peer_external_id: str) -> None:
        await self._run_checked(
            server, "provisioning_remove_peer_failed",
            "remove-peer", peer_id=sanitize_identifier(peer_external_id),
        )

    async def get_peer_status(self, *, server: VPNServer, peer_external_id: str) -> PeerStatus:
        exit_code, data, error = await self._call(
            server, "peer-status", peer_id=sanitize_identifier(peer_external_id)
        )
        if exit_code != 0:
            return PeerStatus(exists=False, is_active=False, raw_status=error.strip() or None)
        try:
            return PeerStatus(
                exists=data.get("exists", True),
                is_active=data.get("is_active", False),
                last_handshake=datetime.fromisoformat(data["last_handshake"]) if data.get("last_handshake") else None,
                bytes_received=int(data.get("bytes_received", 0)),
                bytes_sent=int(data.get("bytes_sent", 0)),
                raw_status=json.dumps(data),
            )
        except Exception:
            return PeerStatus(exists=True, is_active=False, raw_status=json.dumps(data))

    async def get_peer_config(self, *, server: VPNServer, peer_external_id: str) -> bytes:
        data = await self._run_checked(
            server, "provisioning_get_config_failed",
            "get-config", peer_id=sanitize_identifier(peer_external_id),
        )
        try:
            return base64.b64decode(data["config_b64"], validate=True)
        except Exception as e:
            raise RetryableProvisioningError(f"Malformed response from vpnctl: {e}") from e
