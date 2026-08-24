import asyncio
import base64
import json
import os
import re
import shlex
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import paramiko
from src.app.config.settings import get_settings
from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.base import PeerStatus, ProvisionedPeer, VPNProvisioner
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


class SSHCommandProvisioner(VPNProvisioner):
    """
    Production-grade SSH Provisioner that executes constrained commands via
    the narrow remote interface /usr/local/sbin/vpnctl using explicit arguments.
    """

    def __init__(self, connect_timeout: int = 15, command_timeout: int = 30):
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

        if key_path and not os.path.exists(key_path):
            raise PermanentProvisioningError(f"SSH private key file not found on filesystem at: {key_path}")

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
                    key_filename=key_path,
                    timeout=self.connect_timeout,
                    banner_timeout=self.connect_timeout,
                    auth_timeout=self.connect_timeout,
                    allow_agent=False,
                    look_for_keys=False if key_path else True,
                )
                stdin, stdout, stderr = client.exec_command(
                    escaped_cmd,
                    timeout=self.command_timeout,
                )
                exit_code = stdout.channel.recv_exit_status()
                out_text = stdout.read().decode("utf-8")
                err_text = stderr.read().decode("utf-8")
                return exit_code, out_text, err_text
            except (paramiko.SSHException, TimeoutError, OSError) as e:
                logger.error("ssh_connection_error", server=server.slug, error=str(e))
                raise RetryableProvisioningError(f"SSH connection failed to {server.slug}: {e}") from e
            finally:
                client.close()

        return await asyncio.to_thread(_sync_ssh_run)

    async def create_peer(
        self,
        *,
        server: VPNServer,
        subscription_id: uuid.UUID,
        telegram_user_id: int,
        device_name: str = "default",
    ) -> ProvisionedPeer:
        safe_sub_id = str(uuid.UUID(str(subscription_id)))
        raw_label = f"user_{telegram_user_id}_{server.slug}"
        safe_label = sanitize_identifier(raw_label)

        cmd = [
            "/usr/local/sbin/vpnctl",
            "create-peer",
            "--subscription-id",
            safe_sub_id,
            "--label",
            safe_label,
        ]

        exit_code, stdout, stderr = await self._execute_remote_command(server=server, command_args=cmd)

        if exit_code != 0:
            err_msg = stderr.strip() or stdout.strip() or f"Command failed with exit code {exit_code}"
            logger.error("provisioning_create_peer_failed", server=server.slug, error=err_msg)
            if "already exists" in err_msg.lower() or "invalid" in err_msg.lower():
                raise PermanentProvisioningError(err_msg)
            raise RetryableProvisioningError(err_msg)

        try:
            data = json.loads(stdout.strip())
            peer_id = sanitize_identifier(data["peer_id"])
            label = sanitize_identifier(data.get("label", safe_label))
            filename = data.get("filename", f"{label}.conf")
            config_b64 = data["config_b64"]
            config_bytes = base64.b64decode(config_b64)
        except Exception as e:
            logger.error("invalid_vpnctl_output", server=server.slug, stdout=stdout, error=str(e))
            raise RetryableProvisioningError(f"Malformed response from remote vpnctl: {e}") from e

        return ProvisionedPeer(
            external_id=peer_id,
            label=label,
            config_filename=filename,
            config_bytes=config_bytes,
            created_at=datetime.now(timezone.utc),
        )

    async def disable_peer(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> None:
        safe_peer_id = sanitize_identifier(peer_external_id)
        cmd = [
            "/usr/local/sbin/vpnctl",
            "disable-peer",
            "--peer-id",
            safe_peer_id,
        ]
        exit_code, stdout, stderr = await self._execute_remote_command(server=server, command_args=cmd)
        if exit_code != 0:
            err_msg = stderr.strip() or stdout.strip()
            logger.error("provisioning_disable_peer_failed", server=server.slug, error=err_msg)
            raise RetryableProvisioningError(err_msg)

    async def remove_peer(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> None:
        safe_peer_id = sanitize_identifier(peer_external_id)
        cmd = [
            "/usr/local/sbin/vpnctl",
            "remove-peer",
            "--peer-id",
            safe_peer_id,
        ]
        exit_code, stdout, stderr = await self._execute_remote_command(server=server, command_args=cmd)
        if exit_code != 0:
            err_msg = stderr.strip() or stdout.strip()
            logger.error("provisioning_remove_peer_failed", server=server.slug, error=err_msg)
            raise RetryableProvisioningError(err_msg)

    async def get_peer_status(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> PeerStatus:
        safe_peer_id = sanitize_identifier(peer_external_id)
        cmd = [
            "/usr/local/sbin/vpnctl",
            "peer-status",
            "--peer-id",
            safe_peer_id,
        ]
        exit_code, stdout, stderr = await self._execute_remote_command(server=server, command_args=cmd)
        if exit_code != 0:
            return PeerStatus(exists=False, is_active=False)

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
            return PeerStatus(exists=True, is_active=True, raw_status=stdout.strip())

    async def get_peer_config(
        self,
        *,
        server: VPNServer,
        peer_external_id: str,
    ) -> bytes:
        safe_peer_id = sanitize_identifier(peer_external_id)
        cmd = [
            "/usr/local/sbin/vpnctl",
            "get-config",
            "--peer-id",
            safe_peer_id,
        ]
        exit_code, stdout, stderr = await self._execute_remote_command(server=server, command_args=cmd)
        if exit_code != 0:
            raise PermanentProvisioningError(f"Failed to fetch config: {stderr.strip()}")

        data = json.loads(stdout.strip())
        return base64.b64decode(data["config_b64"])
