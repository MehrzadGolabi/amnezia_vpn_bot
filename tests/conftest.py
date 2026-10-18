import json
import os
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VPNCTL = REPO / "scripts" / "provisioner" / "vpnctl"


@dataclass
class AwgSandbox:
    """A throwaway AWG 3.1 server built by scripts/dev/sandbox.sh, with fake-awg as `awg`."""
    root: Path

    @property
    def vpnctl_config(self) -> Path:
        return self.root / "vpnctl.conf"

    @property
    def server_conf(self) -> Path:
        return self.root / "amneziawg" / "awg1.conf"

    @property
    def clients(self) -> Path:
        return self.root / "amneziawg" / "clients"

    @property
    def vpnctl_command(self) -> str:
        return f"env VPNCTL_CONFIG={self.vpnctl_config} {sys.executable} {VPNCTL}"

    def live_peers(self) -> dict:
        state = self.root / "awg-state.json"
        return json.loads(state.read_text()).get("awg1", {}) if state.exists() else {}

    def set_live(self, pubkey: str, **fields) -> None:
        state = self.root / "awg-state.json"
        data = json.loads(state.read_text())
        data["awg1"][pubkey].update(fields)
        state.write_text(json.dumps(data))

    def allow_clients(self, value: str, token_sha256: str = "", **settings: str) -> None:
        with open(self.vpnctl_config, "a") as f:
            f.write(f"ALLOWED_CLIENTS={value}\n")
            if token_sha256:
                f.write(f"CLIENT_TOKEN_SHA256={token_sha256}\n")
            for key, val in settings.items():
                f.write(f"{key}={val}\n")

    def vpnctl(self, *args: str, env: dict = None) -> subprocess.CompletedProcess:
        full_env = {**os.environ, "VPNCTL_CONFIG": str(self.vpnctl_config), **(env or {})}
        return subprocess.run([sys.executable, str(VPNCTL), *args], capture_output=True, text=True, env=full_env)


@pytest.fixture
def awg_sandbox(tmp_path) -> AwgSandbox:
    subprocess.run(["bash", str(REPO / "scripts" / "dev" / "sandbox.sh"), str(tmp_path)],
                   check=True, capture_output=True)
    return AwgSandbox(tmp_path)


class SocketActivator:
    """Does what systemd does for vpnctl.socket with Accept=yes: for each connection,
    start `vpnctl serve` with the connection as its stdin and stdout."""

    def __init__(self, listener: socket.socket, sandbox: AwgSandbox):
        self.listener = listener
        self.sandbox = sandbox
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        env = {**os.environ, "VPNCTL_CONFIG": str(self.sandbox.vpnctl_config)}
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            with conn:
                subprocess.run([sys.executable, str(VPNCTL), "serve"], stdin=conn.fileno(),
                               stdout=conn.fileno(), stderr=subprocess.DEVNULL, env=env, timeout=30)

    def close(self):
        self.listener.close()


@pytest.fixture
def vpnctl_unix_socket(awg_sandbox, tmp_path):
    path = str(tmp_path / "vpnctl.sock")
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(path)
    listener.listen()
    activator = SocketActivator(listener, awg_sandbox)
    yield path
    activator.close()


@pytest.fixture
def vpnctl_tcp_port(awg_sandbox):
    listener = socket.socket(socket.AF_INET)
    # Not 127.0.0.1, which the bot treats as this host. Callers still come from 127.0.0.1.
    listener.bind(("127.0.0.2", 0))
    listener.listen()
    activator = SocketActivator(listener, awg_sandbox)
    yield listener.getsockname()[1]
    activator.close()
