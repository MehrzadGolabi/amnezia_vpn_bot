import asyncio
import base64
import json
import os
import re
import shlex
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

import paramiko
from src.app.config.settings import get_settings
from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.base import PeerStatus, ProvisionedPeer, VPNProvisioner
from src.app.utils.amnezia_codec import encode_vpn_url
from src.app.utils.logging import get_logger

logger = get_logger(__name__)

IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


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


DEFAULT_VPNCTL_COMMAND = "sudo -n /usr/local/sbin/vpnctl"
# vpnctl exits with 2 for bad input and 3 for an unknown client; retrying can't help.
VPNCTL_PERMANENT_EXITS = (2, 3)


def _vpnctl_prefix(command: Optional[str]) -> List[str]:
    if command is None:
        command = getattr(get_settings(), "VPNCTL_COMMAND", None) or DEFAULT_VPNCTL_COMMAND
    return shlex.split(command)


class VpnctlProvisioner(VPNProvisioner):
    """
    Talks to scripts/provisioner/vpnctl, which manages clients on a native
    amneziawg-go + awg-quick server. Subclasses decide where vpnctl runs.
    """

    def __init__(self, vpnctl_command: Optional[str] = None):
        self.vpnctl_prefix = _vpnctl_prefix(vpnctl_command)

    async def _execute_remote_command(
        self,
        *,
        server: VPNServer,
        command_args: List[str],
    ) -> Tuple[int, str, str]:
        raise NotImplementedError

    async def _vpnctl(self, server: VPNServer, *args: str) -> Tuple[int, str, str]:
        return await self._execute_remote_command(server=server, command_args=[*self.vpnctl_prefix, *args])

    @staticmethod
    def _classify_failure(exit_code: int, stdout: str, stderr: str) -> ProvisioningError:
        err_msg = stderr.strip() or stdout.strip() or f"vpnctl failed with exit code {exit_code}"
        if exit_code in VPNCTL_PERMANENT_EXITS or "already exists" in err_msg.lower():
            return PermanentProvisioningError(err_msg)
        return RetryableProvisioningError(err_msg)

    async def _run_checked(self, server: VPNServer, event: str, *args: str) -> dict:
        exit_code, stdout, stderr = await self._vpnctl(server, *args)
        if exit_code != 0:
            error = self._classify_failure(exit_code, stdout, stderr)
            logger.error(event, server=server.slug, error=str(error))
            raise error
        try:
            return json.loads(stdout.strip())
        except ValueError as e:
            logger.error("invalid_vpnctl_output", server=server.slug, stdout=stdout, error=str(e))
            raise RetryableProvisioningError(f"Malformed response from vpnctl: {e}") from e

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
            "create-peer", "--subscription-id", safe_sub_id, "--label", safe_label,
        )
        try:
            peer_id = sanitize_identifier(data["peer_id"])
            label = sanitize_identifier(data.get("label", safe_label))
            filename = data.get("filename", f"{label}.conf")
            config_bytes = base64.b64decode(data["config_b64"])
            vpn_url = data.get("vpn_url")
            if not vpn_url and config_bytes:
                vpn_url = encode_vpn_url(config_bytes.decode("utf-8", errors="ignore"))
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
            "disable-peer", "--peer-id", sanitize_identifier(peer_external_id),
        )

    async def remove_peer(self, *, server: VPNServer, peer_external_id: str) -> None:
        await self._run_checked(
            server, "provisioning_remove_peer_failed",
            "remove-peer", "--peer-id", sanitize_identifier(peer_external_id),
        )

    async def get_peer_status(self, *, server: VPNServer, peer_external_id: str) -> PeerStatus:
        exit_code, stdout, stderr = await self._vpnctl(
            server, "peer-status", "--peer-id", sanitize_identifier(peer_external_id)
        )
        if exit_code != 0:
            return PeerStatus(exists=False, is_active=False, raw_status=stderr.strip() or None)
        try:
            data = json.loads(stdout.strip())
            return PeerStatus(
                exists=data.get("exists", True),
                is_active=data.get("is_active", False),
                last_handshake=datetime.fromisoformat(data["last_handshake"]) if data.get("last_handshake") else None,
                bytes_received=data.get("bytes_received", 0),
                bytes_sent=data.get("bytes_sent", 0),
                raw_status=stdout.strip(),
            )
        except Exception:
            return PeerStatus(exists=True, is_active=False, raw_status=stdout.strip())

    async def get_peer_config(self, *, server: VPNServer, peer_external_id: str) -> bytes:
        exit_code, stdout, stderr = await self._vpnctl(
            server, "get-config", "--peer-id", sanitize_identifier(peer_external_id)
        )
        if exit_code != 0:
            raise self._classify_failure(exit_code, stdout, stderr)
        return base64.b64decode(json.loads(stdout.strip())["config_b64"])


class SSHCommandProvisioner(VpnctlProvisioner):
    """
    Runs vpnctl on the VPN host over SSH as the restricted vpn-provisioner user,
    whose sudoers entry allows only /usr/local/sbin/vpnctl.
    """

    def __init__(self, connect_timeout: int = 15, command_timeout: int = 30, vpnctl_command: Optional[str] = None):
        super().__init__(vpnctl_command)
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout

    async def _execute_remote_command(
        self,
        *,
        server: VPNServer,
        command_args: List[str],
    ) -> Tuple[int, str, str]:
        """
        Executes a remote command over SSH asynchronously using paramiko in a worker thread.
        """
        settings = get_settings()
        server_cfg = settings.vpn_servers.get(server.slug)

        key_path = server_cfg.ssh_private_key_path if server_cfg else None
        known_hosts = server_cfg.ssh_known_hosts_path if server_cfg else None
        username = server.ssh_username or "vpn-provisioner"
        host = server.host
        port = server.ssh_port or 22

        escaped_cmd = " ".join(shlex.quote(arg) for arg in command_args)

        resolved_key_path = key_path
        if key_path and not os.path.exists(key_path):
            basename = os.path.basename(key_path)
            candidates = [
                os.path.join("/app/secrets", basename),
                os.path.join("/app", key_path.lstrip("/")),
                os.path.join("secrets", basename),
            ]
            found = False
            for cand in candidates:
                if os.path.exists(cand):
                    resolved_key_path = cand
                    found = True
                    break
            if not found:
                raise PermanentProvisioningError(
                    f"SSH private key file not found on filesystem at: {key_path} (checked container paths: {candidates})"
                )

        def _sync_ssh_run() -> Tuple[int, str, str]:
            client = paramiko.SSHClient()
            if known_hosts:
                client.load_host_keys(known_hosts)
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    key_filename=resolved_key_path,
                    timeout=self.connect_timeout,
                    banner_timeout=self.connect_timeout,
                    auth_timeout=self.connect_timeout,
                    allow_agent=False,
                    look_for_keys=False if resolved_key_path else True,
                )
                stdin, stdout, stderr = client.exec_command(
                    escaped_cmd,
                    timeout=self.command_timeout,
                )
                # Read before waiting for the exit status so a large output can't fill
                # the channel window and deadlock.
                out_text = stdout.read().decode("utf-8")
                err_text = stderr.read().decode("utf-8")
                exit_code = stdout.channel.recv_exit_status()
                return exit_code, out_text, err_text
            except (paramiko.SSHException, TimeoutError, OSError) as e:
                logger.error("ssh_connection_error", server=server.slug, error=str(e))
                raise RetryableProvisioningError(f"SSH connection failed to {server.slug}: {e}") from e
            finally:
                client.close()

        return await asyncio.to_thread(_sync_ssh_run)


LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def is_local_host(host: Optional[str]) -> bool:
    return (host or "").strip().lower() in LOCAL_HOSTS


class LocalCommandProvisioner(VpnctlProvisioner):
    """
    Runs vpnctl as a local process. Use it when the bot runs on the VPN host itself
    (VPNCTL_COMMAND defaults to `sudo -n /usr/local/sbin/vpnctl`), or for development
    against scripts/dev/sandbox.sh, which needs no VPS at all.

    Servers whose HOST is set to another machine are reached over SSH instead, so one
    bot on a VPN host can also sell the other VPN hosts.
    """

    def __init__(self, command_timeout: int = 30, vpnctl_command: Optional[str] = None):
        super().__init__(vpnctl_command)
        self.command_timeout = command_timeout
        self._ssh = SSHCommandProvisioner(command_timeout=command_timeout, vpnctl_command=vpnctl_command)

    async def _execute_remote_command(
        self,
        *,
        server: VPNServer,
        command_args: Sequence[str],
    ) -> Tuple[int, str, str]:
        if not is_local_host(server.host):
            return await self._ssh._execute_remote_command(server=server, command_args=list(command_args))
        try:
            proc = await asyncio.create_subprocess_exec(
                *command_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            raise PermanentProvisioningError(f"Cannot run vpnctl ({command_args[0]}): {e}") from e
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.command_timeout)
        except asyncio.TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise RetryableProvisioningError(f"vpnctl timed out after {self.command_timeout}s") from e
        return proc.returncode, out.decode("utf-8"), err.decode("utf-8")
