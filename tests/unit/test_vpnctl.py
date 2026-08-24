import json
import subprocess
import sys
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


def test_vpnctl_injection_rejected():
    res = run_vpnctl("create-peer", "--subscription-id", str(uuid.uuid4()), "--label", "user;rm -rf /", "--dry-run")
    assert res.returncode != 0
