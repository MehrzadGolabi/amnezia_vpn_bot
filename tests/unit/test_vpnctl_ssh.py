"""The forced command that limits the bot's SSH key to vpnctl on other VPN hosts."""
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/provisioner/vpnctl-ssh"
SUB_ID = "3f2b8c1e-9d4a-4e7b-8a21-5c6d7e8f9a0b"


@pytest.fixture
def wrapper():
    loader = importlib.machinery.SourceFileLoader("vpnctl_ssh", str(PATH))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("vpnctl_ssh", loader))
    loader.exec_module(module)
    return module


def run(wrapper, monkeypatch, command):
    calls = []
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", command)
    monkeypatch.setattr(wrapper.os, "execve", lambda path, argv, env: calls.append(argv))
    code = wrapper.main()
    return code, calls


@pytest.mark.parametrize("command", [
    f"sudo -n /usr/local/sbin/vpnctl create-peer --subscription-id {SUB_ID} --label user_1_3f2b8c1e_tr-1",
    "sudo -n /usr/local/sbin/vpnctl peer-status --peer-id user_1_3f2b8c1e_tr-1",
    "sudo -n /usr/local/sbin/vpnctl get-config --peer-id 'user_1'",
    "/usr/local/sbin/vpnctl disable-peer --peer-id a",
    "vpnctl enable-peer --peer-id a",
    "vpnctl remove-peer --peer-id a",
])
def test_bot_commands_run_vpnctl(wrapper, monkeypatch, command):
    code, calls = run(wrapper, monkeypatch, command)
    assert code is None
    assert calls[0][:3] == ["/usr/bin/sudo", "-n", "/usr/local/sbin/vpnctl"]
    assert calls[0][3] == command.split("vpnctl ")[1].split()[0]


@pytest.mark.parametrize("command", [
    "",
    "bash",
    "id; cat /etc/shadow",
    "sudo -n /usr/local/sbin/vpnctl peer-status --peer-id 'x;id'",
    "sudo -n /usr/local/sbin/vpnctl peer-status --peer-id x --help",
    "sudo -n /usr/local/sbin/vpnctl create-peer --subscription-id nope --label x",
    "sudo -n /usr/local/sbin/vpnctl encode",
    "sudo -n /bin/sh -c id",
    "sudo /usr/local/sbin/vpnctl peer-status --peer-id x",
    "sudo -n /usr/local/sbin/vpnctl peer-status --peer-id 'unterminated",
    "scp -t /tmp",
])
def test_anything_else_is_refused(wrapper, monkeypatch, command):
    code, calls = run(wrapper, monkeypatch, command)
    assert code == 2 and calls == []


def test_environment_is_not_passed_on(wrapper, monkeypatch):
    monkeypatch.setenv("VPNCTL_CONFIG", "/tmp/evil.conf")
    envs = []
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", "vpnctl peer-status --peer-id a")
    monkeypatch.setattr(wrapper.os, "execve", lambda path, argv, env: envs.append(env))
    wrapper.main()
    assert envs == [{"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}]
