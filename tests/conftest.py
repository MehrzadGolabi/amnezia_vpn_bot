import json
import os
import subprocess
import sys
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

    def vpnctl(self, *args: str, env: dict = None) -> subprocess.CompletedProcess:
        full_env = {**os.environ, "VPNCTL_CONFIG": str(self.vpnctl_config), **(env or {})}
        return subprocess.run([sys.executable, str(VPNCTL), *args], capture_output=True, text=True, env=full_env)


@pytest.fixture
def awg_sandbox(tmp_path) -> AwgSandbox:
    subprocess.run(["bash", str(REPO / "scripts" / "dev" / "sandbox.sh"), str(tmp_path)],
                   check=True, capture_output=True)
    return AwgSandbox(tmp_path)
