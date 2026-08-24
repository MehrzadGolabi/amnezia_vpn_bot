import json
import subprocess
import sys
import tempfile
import uuid
import pytest


def run_vpnctl(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "scripts/provisioner/vpnctl", *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_vpnctl_create_peer_dry_run():
    sub_id = str(uuid.uuid4())
    res = run_vpnctl("create-peer", "--subscription-id", sub_id, "--label", "user_123_de1", "--dry-run")
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "success"
    assert data["label"] == "user_123_de1"
    assert "peer_id" in data
    assert "config_b64" in data
    assert "vpn_url" in data
    assert data["vpn_url"].startswith("vpn://")


def test_vpnctl_disable_peer_dry_run():
    res = run_vpnctl("disable-peer", "--peer-id", "peer_test123", "--dry-run")
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "success"


def test_vpnctl_remove_peer_dry_run():
    res = run_vpnctl("remove-peer", "--peer-id", "peer_test123", "--dry-run")
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "success"


def test_vpnctl_peer_status_dry_run():
    res = run_vpnctl("peer-status", "--peer-id", "peer_test123", "--dry-run")
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "success"
    assert data["exists"] is True


def test_vpnctl_get_config_dry_run():
    res = run_vpnctl("get-config", "--peer-id", "peer_test123", "--dry-run")
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "success"
    assert "config_b64" in data
    assert "vpn_url" in data


def test_vpnctl_encode_decode_cli():
    content = "[Interface]\nAddress = 10.8.1.5/32\nPrivateKey = 12345\n\n[Peer]\nPublicKey = abcde\n"
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".conf") as f:
        f.write(content)
        temp_path = f.name

    res_enc = run_vpnctl("encode", "-i", temp_path)
    assert res_enc.returncode == 0
    vpn_url = res_enc.stdout.strip()
    assert vpn_url.startswith("vpn://")

    res_dec = run_vpnctl("decode", "-u", vpn_url)
    assert res_dec.returncode == 0
    assert res_dec.stdout.strip() == content.strip()


def test_vpnctl_injection_rejected():
    res = run_vpnctl("create-peer", "--subscription-id", str(uuid.uuid4()), "--label", "user;rm -rf /", "--dry-run")
    assert res.returncode != 0
