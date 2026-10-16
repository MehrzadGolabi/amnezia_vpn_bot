"""vpnctl against a sandboxed native AWG 3.1 server (scripts/dev/sandbox.sh + fake-awg)."""
import base64
import json
import os
import re
import stat
import tempfile
import time
import uuid

OBFUSCATION_KEYS = [
    "Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4", "I1", "I2", "I3",
    "HeaderProtectionKey", "ContentPaddingAddition", "RekeyAfterTime", "RekeyTimeout",
    "RejectAfterTime", "KeepaliveTimeout", "MaxHandshakeAttempts", "RandomTrailers", "DisableCookies",
]


def create(sb, label):
    res = sb.vpnctl("create-peer", "--subscription-id", str(uuid.uuid4()), "--label", label)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout)
    data["config"] = base64.b64decode(data["config_b64"]).decode()
    return data


def value(text, key):
    m = re.search(rf"^{key} = (.+)$", text, re.MULTILINE)
    return m.group(1) if m else None


def test_create_peer_writes_awg31_client_config(awg_sandbox):
    data = create(awg_sandbox, "user_1_abcd1234_de-1")
    server = awg_sandbox.server_conf.read_text()
    client = data["config"]

    assert data["peer_id"] == data["label"] == "user_1_abcd1234_de-1"
    assert data["filename"] == "user_1_abcd1234_de-1.conf"
    assert data["address"] == "10.66.66.2/32"
    assert data["vpn_url"].startswith("vpn://")

    # Every obfuscation value is copied verbatim from the server's [Interface].
    for key in OBFUSCATION_KEYS:
        assert value(client, key) is not None, key
        assert value(client, key) == value(server, key), key
    assert value(client, "MTU") == "1280"
    assert value(client, "Endpoint") == "203.0.113.10:51888"
    assert value(client, "AllowedIPs") == "0.0.0.0/0, ::/0"

    # Server side uses the same "# name" layout as awg-add-client.sh / awg-del-client.sh.
    assert "[Peer]\n# user_1_abcd1234_de-1\nPublicKey = " in server
    assert "AllowedIPs = 10.66.66.2/32" in server

    # Applied live with the same preshared key.
    live = awg_sandbox.live_peers()
    assert len(live) == 1
    (pub, peer), = live.items()
    assert f"PublicKey = {pub}" in server
    assert peer["allowed_ips"] == "10.66.66.2/32"
    assert peer["psk"] == value(client, "PresharedKey")

    client_file = awg_sandbox.clients / "user_1_abcd1234_de-1.conf"
    assert client_file.read_text() == client
    assert stat.S_IMODE(os.stat(client_file).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(awg_sandbox.server_conf).st_mode) == 0o600


def test_create_peer_is_idempotent_per_label(awg_sandbox):
    first = create(awg_sandbox, "dup")
    second = create(awg_sandbox, "dup")
    assert second["config"] == first["config"]
    assert second["existing"] is True
    assert len(awg_sandbox.live_peers()) == 1
    assert awg_sandbox.server_conf.read_text().count("# dup\n") == 1


def test_addresses_skip_disabled_peers_and_reuse_removed_ones(awg_sandbox):
    assert create(awg_sandbox, "a")["address"] == "10.66.66.2/32"
    assert create(awg_sandbox, "b")["address"] == "10.66.66.3/32"
    assert awg_sandbox.vpnctl("disable-peer", "--peer-id", "a").returncode == 0
    assert create(awg_sandbox, "c")["address"] == "10.66.66.4/32"
    assert awg_sandbox.vpnctl("remove-peer", "--peer-id", "b").returncode == 0
    assert create(awg_sandbox, "d")["address"] == "10.66.66.3/32"


def test_disable_enable_remove_cycle(awg_sandbox):
    created = create(awg_sandbox, "cycle")
    create(awg_sandbox, "other")
    pub = next(p for p, v in awg_sandbox.live_peers().items() if v["allowed_ips"] == "10.66.66.2/32")

    res = awg_sandbox.vpnctl("disable-peer", "--peer-id", "cycle")
    assert json.loads(res.stdout) == {"status": "success", "peer_id": "cycle", "found": True, "enabled": False}
    assert "# cycle" not in awg_sandbox.server_conf.read_text()
    assert pub not in awg_sandbox.live_peers()
    assert "# other" in awg_sandbox.server_conf.read_text()

    # Config stays retrievable while disabled, and disabling twice is harmless.
    assert awg_sandbox.vpnctl("disable-peer", "--peer-id", "cycle").returncode == 0
    got = json.loads(awg_sandbox.vpnctl("get-config", "--peer-id", "cycle").stdout)
    assert base64.b64decode(got["config_b64"]).decode() == created["config"]

    res = awg_sandbox.vpnctl("enable-peer", "--peer-id", "cycle")
    assert res.returncode == 0, res.stderr
    assert awg_sandbox.server_conf.read_text().count("# cycle\n") == 1
    assert awg_sandbox.live_peers()[pub]["allowed_ips"] == "10.66.66.2/32"

    res = awg_sandbox.vpnctl("remove-peer", "--peer-id", "cycle")
    assert json.loads(res.stdout)["found"] is True
    assert "# cycle" not in awg_sandbox.server_conf.read_text()
    assert pub not in awg_sandbox.live_peers()
    assert not (awg_sandbox.clients / "cycle.conf").exists()
    assert not (awg_sandbox.clients / "cycle.peer").exists()
    assert awg_sandbox.vpnctl("get-config", "--peer-id", "cycle").returncode == 3


def test_remove_of_disabled_peer_and_unknown_peer(awg_sandbox):
    create(awg_sandbox, "gone")
    awg_sandbox.vpnctl("disable-peer", "--peer-id", "gone")
    assert json.loads(awg_sandbox.vpnctl("remove-peer", "--peer-id", "gone").stdout)["found"] is True
    assert list(awg_sandbox.clients.iterdir()) == []

    for cmd in ("remove-peer", "disable-peer"):
        res = awg_sandbox.vpnctl(cmd, "--peer-id", "never_existed")
        assert res.returncode == 0
        assert json.loads(res.stdout)["found"] is False
    assert awg_sandbox.vpnctl("enable-peer", "--peer-id", "never_existed").returncode == 3


def test_disable_keeps_peers_added_by_the_shell_script(awg_sandbox):
    """A peer added by awg-add-client.sh has no .peer file; disable must save one so enable works."""
    with open(awg_sandbox.server_conf, "a") as f:
        f.write("\n[Peer]\n# phone\nPublicKey = cGhvbmVwaG9uZXBob25lcGhvbmVwaG9uZXBob25lcGg=\n"
                "PresharedKey = cHNrcHNrcHNrcHNrcHNrcHNrcHNrcHNrcHNrcHNrcHM=\nAllowedIPs = 10.66.66.2/32\n")
    assert create(awg_sandbox, "next")["address"] == "10.66.66.3/32"
    assert awg_sandbox.vpnctl("disable-peer", "--peer-id", "phone").returncode == 0
    assert (awg_sandbox.clients / "phone.peer").exists()
    assert awg_sandbox.vpnctl("enable-peer", "--peer-id", "phone").returncode == 0
    assert "# phone\n" in awg_sandbox.server_conf.read_text()


def test_peer_status_reads_live_counters(awg_sandbox):
    create(awg_sandbox, "stat")
    (pub,) = awg_sandbox.live_peers()
    data = json.loads(awg_sandbox.vpnctl("peer-status", "--peer-id", "stat").stdout)
    assert data["exists"] and data["enabled"]
    assert data["is_active"] is False and data["last_handshake"] is None

    awg_sandbox.set_live(pub, latest_handshake=int(time.time()) - 30, rx=1500, tx=4200)
    data = json.loads(awg_sandbox.vpnctl("peer-status", "--peer-id", "stat").stdout)
    assert data["is_active"] is True
    assert data["bytes_received"] == 1500 and data["bytes_sent"] == 4200
    assert data["last_handshake"] is not None

    awg_sandbox.vpnctl("disable-peer", "--peer-id", "stat")
    data = json.loads(awg_sandbox.vpnctl("peer-status", "--peer-id", "stat").stdout)
    assert data["exists"] is True and data["enabled"] is False and data["is_active"] is False

    data = json.loads(awg_sandbox.vpnctl("peer-status", "--peer-id", "nobody").stdout)
    assert data["exists"] is False


def test_create_fails_cleanly_when_interface_is_down(awg_sandbox):
    before = awg_sandbox.server_conf.read_text()
    res = awg_sandbox.vpnctl("create-peer", "--subscription-id", str(uuid.uuid4()), "--label", "down",
                             env={"FAKE_AWG_DOWN": "1"})
    assert res.returncode == 1
    assert "No such device" in res.stderr
    assert awg_sandbox.server_conf.read_text() == before
    assert list(awg_sandbox.clients.iterdir()) == []


def test_invalid_input_exits_2(awg_sandbox):
    res = awg_sandbox.vpnctl("create-peer", "--subscription-id", str(uuid.uuid4()), "--label", "user;rm -rf /")
    assert res.returncode == 2
    res = awg_sandbox.vpnctl("create-peer", "--subscription-id", "not-a-uuid", "--label", "ok")
    assert res.returncode == 2
    res = awg_sandbox.vpnctl("disable-peer", "--peer-id", "../../etc/passwd")
    assert res.returncode == 2
    assert awg_sandbox.live_peers() == {}


def test_missing_server_config_is_an_error(awg_sandbox):
    awg_sandbox.server_conf.unlink()
    res = awg_sandbox.vpnctl("create-peer", "--subscription-id", str(uuid.uuid4()), "--label", "x")
    assert res.returncode == 1
    assert "Server config not found" in res.stderr


def test_encode_decode_cli(awg_sandbox):
    content = "[Interface]\nAddress = 10.66.66.5/32\nPrivateKey = 12345\n\n[Peer]\nPublicKey = abcde\n"
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".conf") as f:
        f.write(content)
    vpn_url = awg_sandbox.vpnctl("encode", "-i", f.name).stdout.strip()
    assert vpn_url.startswith("vpn://")
    res = awg_sandbox.vpnctl("decode", "-u", vpn_url)
    assert res.returncode == 0
    assert res.stdout.strip() == content.strip()


def test_enable_refuses_an_address_taken_while_disabled(awg_sandbox):
    """awg-add-client.sh only looks at awg1.conf, so it can reuse a disabled peer's address."""
    create(awg_sandbox, "old")
    awg_sandbox.vpnctl("disable-peer", "--peer-id", "old")
    with open(awg_sandbox.server_conf, "a") as f:
        f.write("\n[Peer]\n# laptop\nPublicKey = bGFwdG9wbGFwdG9wbGFwdG9wbGFwdG9wbGFwdG9wbGE=\n"
                "PresharedKey = cHNrcHNrcHNrcHNrcHNrcHNrcHNrcHNrcHNrcHNrcHM=\nAllowedIPs = 10.66.66.2/32\n")
    res = awg_sandbox.vpnctl("enable-peer", "--peer-id", "old")
    assert res.returncode == 1
    assert "10.66.66.2 is now used by another peer" in res.stderr
    assert "# old" not in awg_sandbox.server_conf.read_text()
