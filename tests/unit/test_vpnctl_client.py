"""The bot's vpnctl client, and `vpnctl serve` behind real Unix and TCP sockets."""
import base64
import json
import socket
import subprocess
import sys
import uuid
from unittest.mock import AsyncMock

import pytest

from src.app.config.settings import ServerConfig, get_settings
from src.app.db.models.server import VPNServer
from src.app.integrations.provisioning.vpnctl_client import (
    PermanentProvisioningError,
    RetryableProvisioningError,
    VpnctlProvisioner,
    sanitize_identifier,
)
from src.app.utils.amnezia_codec import decode_vpn_url

LOCAL = VPNServer(slug="de-1", display_name="Germany", country_code="DE", host="")
REMOTE = VPNServer(slug="tr-1", display_name="Turkey", country_code="TR", host="127.0.0.2")
CONFIG = "[Interface]\nPrivateKey = abc\n"


def reply(exit_code=0, result=None, error=None) -> bytes:
    body = {"exit_code": exit_code}
    if result is not None:
        body["result"] = result
    if error is not None:
        body["error"] = error
    return (json.dumps(body) + "\n").encode()


def fake(response: bytes) -> VpnctlProvisioner:
    prov = VpnctlProvisioner(socket_path="/nonexistent", dev_command="")
    prov._exchange = AsyncMock(return_value=response)
    return prov


def sent(prov) -> dict:
    return json.loads(prov._exchange.await_args.args[1])


@pytest.fixture
def remote_port(monkeypatch, vpnctl_tcp_port):
    monkeypatch.setitem(get_settings().vpn_servers, "tr-1",
                        ServerConfig(slug="tr-1", country_code="TR", display_name="Turkey",
                                     host="127.0.0.2", vpnctl_port=vpnctl_tcp_port))
    return vpnctl_tcp_port


# --- Requests and responses ---

def test_sanitize_identifier():
    assert sanitize_identifier("user_123456_de1") == "user_123456_de1"
    for bad in ("user; rm -rf /", "user`id`", "user$(whoami)", "user\nnewline", ""):
        with pytest.raises(ValueError):
            sanitize_identifier(bad)


async def test_create_peer_request_and_result():
    sub_id = uuid.uuid4()
    prov = fake(reply(result={
        "peer_id": "user_1_x_de-1", "label": "user_1_x_de-1", "filename": "../../evil.exe",
        "config_b64": base64.b64encode(CONFIG.encode()).decode(), "vpn_url": "https://evil.example",
    }))
    peer = await prov.create_peer(server=LOCAL, subscription_id=sub_id, telegram_user_id=1)
    assert sent(prov) == {"command": "create-peer", "args": {
        "subscription_id": str(sub_id), "label": f"user_1_{str(sub_id)[:8]}_de-1"}}
    assert peer.config_filename == "user_1_x_de-1.conf"
    assert decode_vpn_url(peer.vpn_url) == CONFIG


async def test_disable_and_remove_requests():
    prov = fake(reply(result={"status": "success"}))
    await prov.disable_peer(server=LOCAL, peer_external_id="peer_abc")
    assert sent(prov) == {"command": "disable-peer", "args": {"peer_id": "peer_abc"}}
    await prov.remove_peer(server=LOCAL, peer_external_id="peer_abc")
    assert sent(prov)["command"] == "remove-peer"


@pytest.mark.parametrize("exit_code,error_class", [
    (1, RetryableProvisioningError),
    (2, PermanentProvisioningError),
    (3, PermanentProvisioningError),
    (4, PermanentProvisioningError),
])
async def test_exit_codes(exit_code, error_class):
    with pytest.raises(error_class):
        await fake(reply(exit_code, error="nope")).disable_peer(server=LOCAL, peer_external_id="p")


@pytest.mark.parametrize("raw", [b"", b"not json", b'{"no_exit_code": 1}', b'{"exit_code": 0, "result": []}'])
async def test_malformed_responses_are_retried(raw):
    with pytest.raises(RetryableProvisioningError):
        await fake(raw).disable_peer(server=LOCAL, peer_external_id="p")


async def test_status_and_config():
    status = await fake(reply(result={
        "exists": True, "is_active": True, "last_handshake": "2026-08-24T20:00:00+00:00",
        "bytes_received": 1000, "bytes_sent": 2000,
    })).get_peer_status(server=LOCAL, peer_external_id="p")
    assert status.exists and status.is_active and status.bytes_received == 1000

    status = await fake(reply(3, error="No client")).get_peer_status(server=LOCAL, peer_external_id="p")
    assert status.exists is False

    config = await fake(reply(result={"config_b64": "W0ludGVyZmFjZV0K"})).get_peer_config(
        server=LOCAL, peer_external_id="p")
    assert config == b"[Interface]\n"


async def test_unreachable_socket_is_retried():
    prov = VpnctlProvisioner(socket_path="/nonexistent/vpnctl.sock", dev_command="")
    with pytest.raises(RetryableProvisioningError, match="Cannot reach"):
        await prov.disable_peer(server=LOCAL, peer_external_id="p")


async def test_missing_dev_command_is_permanent():
    prov = VpnctlProvisioner(dev_command="/nonexistent/vpnctl")
    with pytest.raises(PermanentProvisioningError):
        await prov.disable_peer(server=LOCAL, peer_external_id="p")


# --- Through real sockets ---

async def test_unix_socket_lifecycle(awg_sandbox, vpnctl_unix_socket):
    prov = VpnctlProvisioner(socket_path=vpnctl_unix_socket, dev_command="")
    peer = await prov.create_peer(server=LOCAL, subscription_id=uuid.uuid4(), telegram_user_id=7)
    assert "HeaderProtectionKey = " in peer.config_bytes.decode()
    assert len(awg_sandbox.live_peers()) == 1

    status = await prov.get_peer_status(server=LOCAL, peer_external_id=peer.external_id)
    assert status.exists
    await prov.remove_peer(server=LOCAL, peer_external_id=peer.external_id)
    assert awg_sandbox.live_peers() == {}


async def test_tcp_caller_in_allowed_clients(awg_sandbox, remote_port):
    awg_sandbox.allow_clients("100.64.0.1, 127.0.0.1")
    prov = VpnctlProvisioner(dev_command="")
    peer = await prov.create_peer(server=REMOTE, subscription_id=uuid.uuid4(), telegram_user_id=7)
    assert peer.external_id.endswith("_tr-1")
    assert len(awg_sandbox.live_peers()) == 1


@pytest.mark.parametrize("allowed", ["", "100.64.0.1", "not-an-ip"])
async def test_tcp_caller_not_in_allowed_clients_is_refused(awg_sandbox, remote_port, allowed):
    if allowed:
        awg_sandbox.allow_clients(allowed)
    prov = VpnctlProvisioner(dev_command="")
    with pytest.raises(PermanentProvisioningError, match="ALLOWED_CLIENTS"):
        await prov.create_peer(server=REMOTE, subscription_id=uuid.uuid4(), telegram_user_id=7)
    assert awg_sandbox.live_peers() == {}


def raw_request(port: int, data: bytes) -> dict:
    with socket.create_connection(("127.0.0.2", port), timeout=15) as s:
        s.sendall(data)
        s.shutdown(socket.SHUT_WR)
        out = b""
        while chunk := s.recv(65536):
            out += chunk
    return json.loads(out)


@pytest.mark.parametrize("data,message", [
    (b'{"command": "encode", "args": {}}\n', "Unknown command"),
    (b'{"command": "serve", "args": {}}\n', "Unknown command"),
    (b'{"command": "get-config", "args": {"peer_id": "a", "input": "/etc/shadow"}}\n', "takes exactly"),
    (b'{"command": "get-config", "args": {"peer_id": ["a"]}}\n', "takes exactly"),
    (b'{"command": "get-config", "args": {"peer_id": "../../x"}}\n', "Invalid peer_id"),
    (b"x" * 4097, "too large"),
    (b"[1, 2]\n", "must be an object"),
])
def test_serve_rejects_bad_requests(awg_sandbox, vpnctl_tcp_port, data, message):
    awg_sandbox.allow_clients("127.0.0.1")
    response = raw_request(vpnctl_tcp_port, data)
    assert response["exit_code"] == 2
    assert message in response["error"]


def test_encode_reads_stdin_only(awg_sandbox):
    from tests.conftest import VPNCTL
    assert awg_sandbox.vpnctl("encode", "-i", "/etc/passwd").returncode != 0
    encoded = subprocess.run([sys.executable, str(VPNCTL), "encode"], input=CONFIG,
                             capture_output=True, text=True, check=True).stdout.strip()
    assert decode_vpn_url(encoded) == CONFIG
