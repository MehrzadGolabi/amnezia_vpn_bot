import json
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.ssh_provisioner import SSHCommandProvisioner, sanitize_identifier, ProvisioningError, RetryableProvisioningError


@pytest.fixture
def sample_server():
    return VPNServer(
        slug="de-prod",
        display_name="Germany Frankfurt",
        country_code="DE",
        country_name="Germany",
        host="de-prod.vpn.internal",
        ssh_port=22,
        ssh_username="vpn-provisioner",
    )


def test_sanitize_identifier_valid():
    assert sanitize_identifier("user_123456_de1") == "user_123456_de1"
    assert sanitize_identifier("client-device-01") == "client-device-01"


def test_sanitize_identifier_invalid_injection():
    with pytest.raises(ValueError):
        sanitize_identifier("user; rm -rf /")
    with pytest.raises(ValueError):
        sanitize_identifier("user`id`")
    with pytest.raises(ValueError):
        sanitize_identifier("user$(whoami)")
    with pytest.raises(ValueError):
        sanitize_identifier("user\nnewline")
    with pytest.raises(ValueError):
        sanitize_identifier("")


@pytest.mark.asyncio
async def test_ssh_provisioner_create_peer(sample_server):
    provisioner = SSHCommandProvisioner()
    sub_id = uuid.uuid4()

    mock_vpnctl_output = json.dumps({
        "status": "success",
        "peer_id": "peer_123456",
        "label": "user_123_de-prod",
        "filename": "user_123_de-prod.conf",
        "config_b64": "W0ludGVyZmFjZV0KUHJpdmF0ZUtleSA9IGFia2V5Cg==", # base64 for [Interface]\nPrivateKey = abkey\n
    })

    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (0, mock_vpnctl_output, "")
        
        peer = await provisioner.create_peer(
            server=sample_server,
            subscription_id=sub_id,
            telegram_user_id=123,
            device_name="phone",
        )

        assert peer.external_id == "peer_123456"
        assert peer.label == "user_123_de-prod"
        assert peer.config_filename == "user_123_de-prod.conf"
        assert b"[Interface]" in peer.config_bytes
        
        # Verify strict arguments passed
        mock_exec.assert_called_once()
        args = mock_exec.call_args[1]["command_args"]
        assert args[0] == "/usr/local/sbin/vpnctl"
        assert args[1] == "create-peer"
        assert args[2] == "--subscription-id"
        assert args[3] == str(sub_id)


@pytest.mark.asyncio
async def test_ssh_provisioner_disable_and_remove(sample_server):
    provisioner = SSHCommandProvisioner()

    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (0, json.dumps({"status": "success"}), "")
        
        await provisioner.disable_peer(
            server=sample_server,
            peer_external_id="peer_abc",
        )
        assert mock_exec.call_args[1]["command_args"][1] == "disable-peer"

        await provisioner.remove_peer(
            server=sample_server,
            peer_external_id="peer_abc",
        )
        assert mock_exec.call_args[1]["command_args"][1] == "remove-peer"


@pytest.mark.asyncio
async def test_ssh_provisioner_error_handling(sample_server):
    provisioner = SSHCommandProvisioner()

    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (1, "", "Connection to Docker container failed")
        
        with pytest.raises(RetryableProvisioningError):
            await provisioner.create_peer(
                server=sample_server,
                subscription_id=uuid.uuid4(),
                telegram_user_id=123,
            )


@pytest.mark.asyncio
async def test_ssh_provisioner_get_status_and_config(sample_server):
    provisioner = SSHCommandProvisioner()

    # Status success
    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (0, json.dumps({
            "exists": True,
            "is_active": True,
            "last_handshake": "2026-08-24T20:00:00+00:00",
            "bytes_received": 1000,
            "bytes_sent": 2000,
        }), "")
        status = await provisioner.get_peer_status(server=sample_server, peer_external_id="peer_xyz")
        assert status.exists is True
        assert status.is_active is True
        assert status.bytes_received == 1000

    # Status error
    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (1, "", "Peer not found")
        status = await provisioner.get_peer_status(server=sample_server, peer_external_id="peer_xyz")
        assert status.exists is False

    # Get config success
    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (0, json.dumps({
            "config_b64": "W0ludGVyZmFjZV0K", # [Interface]\n
        }), "")
        cfg = await provisioner.get_peer_config(server=sample_server, peer_external_id="peer_xyz")
        assert b"[Interface]" in cfg


@pytest.mark.asyncio
async def test_ssh_provisioner_permanent_error(sample_server):
    from src.app.integrations.provisioning.ssh_provisioner import PermanentProvisioningError
    provisioner = SSHCommandProvisioner()

    with patch.object(provisioner, "_execute_remote_command", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = (1, "", "Peer already exists")
        with pytest.raises(PermanentProvisioningError):
            await provisioner.create_peer(
                server=sample_server,
                subscription_id=uuid.uuid4(),
                telegram_user_id=999,
            )


@pytest.mark.asyncio
async def test_ssh_provisioner_sync_run_mocked_paramiko(sample_server):
    provisioner = SSHCommandProvisioner()
    
    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = 0
    
    mock_stdout = MagicMock()
    mock_stdout.channel = mock_channel
    mock_stdout.read.return_value = b'{"status": "ok"}'
    
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    with patch("paramiko.SSHClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        code, out, err = await provisioner._execute_remote_command(
            server=sample_server,
            command_args=["/usr/local/sbin/vpnctl", "peer-status", "--peer-id", "test1"],
        )
        assert code == 0
        assert "ok" in out
        mock_client.connect.assert_called_once()
        mock_client.close.assert_called_once()
