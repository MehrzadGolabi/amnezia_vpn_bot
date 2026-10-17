"""Security checks: untrusted text in HTML messages, replies from VPN hosts, SSH host
keys, throttling, forged button data and the provisioner installer."""
import base64
import json
import os
import subprocess
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import paramiko
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.app.bot.handlers.customer import callback_select_plan, callback_select_server
from src.app.bot.handlers.support import handle_support_message
from src.app.bot.middleware.throttling_middleware import ThrottlingMiddleware
from src.app.bot.states.support_states import SupportStates
from src.app.config.settings import get_settings
from src.app.db.models.base import Base
from src.app.db.models.server import VPNServer
from src.app.db.repositories.product_repo import ProductRepository
from src.app.db.repositories.server_repo import ServerRepository
from src.app.db.repositories.user_repo import UserRepository
from src.app.integrations.provisioning.ssh_provisioner import (
    PermanentProvisioningError,
    SSHCommandProvisioner,
)
from src.app.utils.amnezia_codec import decode_vpn_url
from src.app.utils.logging import redact_sensitive_text

INSTALLER = Path(__file__).resolve().parents[2] / "scripts/provisioner/install-provisioner.sh"
CONFIG = "[Interface]\nPrivateKey = abc\n"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def fsm_context():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=4242, user_id=4242))


@pytest.fixture
def remote_server():
    return VPNServer(slug="tr-1", display_name="Turkey", country_code="TR", country_name="Turkey",
                     host="100.64.0.2", ssh_port=22, ssh_username="vpn-provisioner")


def callback(data):
    query = MagicMock(spec=CallbackQuery)
    query.data = data
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()
    query.from_user = TelegramUser(id=4242, is_bot=False, first_name="C")
    return query


# --- Untrusted text in HTML messages ---

async def test_support_message_is_escaped_for_admins(session, fsm_context, monkeypatch):
    monkeypatch.setattr(get_settings(), "ADMIN_CHAT_ID", 999)
    user = await UserRepository(session).upsert_user(telegram_user_id=4242, username="c", language_code="en")
    await fsm_context.set_state(SupportStates.writing_message)

    msg = MagicMock(spec=Message)
    msg.text = '<a href="https://evil.example">Approve here</a>'
    msg.photo = msg.document = None
    msg.message_id = 1
    msg.chat = Chat(id=4242, type="private")
    msg.answer = AsyncMock()
    msg.bot = AsyncMock()

    await handle_support_message(msg, {"db_user": user, "session": session}, fsm_context)
    sent = msg.bot.send_message.call_args.kwargs["text"]
    assert "<a href" not in sent
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in sent


async def test_worker_alerts_are_plain_text():
    from src.app.worker.engine import WorkerEngine
    worker = WorkerEngine.__new__(WorkerEngine)
    worker.admin_chat_id = 999
    worker.bot = AsyncMock()
    await worker._alert_admin("Error: <b>from a VPN host</b>")
    assert worker.bot.send_message.call_args.kwargs["parse_mode"] is None


# --- Replies from VPN hosts ---

async def test_create_peer_builds_filename_and_link_itself(remote_server):
    provisioner = SSHCommandProvisioner()
    reply = json.dumps({
        "peer_id": "user_1_abcd_tr-1",
        "label": "user_1_abcd_tr-1",
        "filename": "../../evil.exe",
        "config_b64": base64.b64encode(CONFIG.encode()).decode(),
        "vpn_url": "https://evil.example/phish",
    })
    with patch.object(provisioner, "_execute_remote_command", new=AsyncMock(return_value=(0, reply, ""))):
        peer = await provisioner.create_peer(server=remote_server, subscription_id=uuid.uuid4(), telegram_user_id=1)
    assert peer.config_filename == "user_1_abcd_tr-1.conf"
    assert decode_vpn_url(peer.vpn_url) == CONFIG


def test_logs_redact_configs_and_vpn_links():
    text = redact_sensitive_text('{"config_b64": "W0ludGVyZmFjZV0=", "vpn_url": "vpn://AAAAeJzLSM3JyQcABiwCFQ"}')
    assert "W0ludGVyZmFjZV0=" not in text
    assert "AAAAeJzLSM3JyQcABiwCFQ" not in text


# --- SSH host keys ---

def ssh_client_raising(exc):
    client = MagicMock()
    client.connect.side_effect = exc
    return client


async def test_ssh_never_accepts_unknown_host_keys(remote_server):
    client = ssh_client_raising(paramiko.SSHException("Server '100.64.0.2' not found in known_hosts"))
    with patch("paramiko.SSHClient", return_value=client):
        with pytest.raises(PermanentProvisioningError, match="not in known_hosts"):
            await SSHCommandProvisioner()._execute_remote_command(server=remote_server, command_args=["x"])
    policy = client.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, paramiko.RejectPolicy)
    client.load_system_host_keys.assert_called_once()


async def test_ssh_changed_host_key_is_permanent(remote_server):
    key = MagicMock()
    key.get_base64.return_value = "AAAA"
    client = ssh_client_raising(paramiko.BadHostKeyException("100.64.0.2", key, key))
    with patch("paramiko.SSHClient", return_value=client):
        with pytest.raises(PermanentProvisioningError, match="has changed"):
            await SSHCommandProvisioner()._execute_remote_command(server=remote_server, command_args=["x"])


# --- Throttling ---

async def test_throttled_button_press_is_still_answered():
    middleware = ThrottlingMiddleware(rate_limit_seconds=10)
    query = MagicMock(spec=CallbackQuery)
    query.from_user = TelegramUser(id=1, is_bot=False, first_name="S")
    query.answer = AsyncMock()
    handler = AsyncMock(return_value="ok")
    assert await middleware(handler, query, {}) == "ok"
    assert await middleware(handler, query, {}) is None
    handler.assert_called_once()
    query.answer.assert_called_once()


async def test_throttle_table_forgets_quiet_users(monkeypatch):
    from src.app.bot.middleware import throttling_middleware as tm
    monkeypatch.setattr(tm, "PRUNE_AT_SIZE", 3)
    middleware = ThrottlingMiddleware(rate_limit_seconds=0.5)
    middleware._last_seen = {1: 0.0, 2: 0.0, 3: 0.0}
    event = MagicMock(spec=Message)
    event.from_user = TelegramUser(id=4, is_bot=False, first_name="N")
    await middleware(AsyncMock(), event, {})
    assert set(middleware._last_seen) == {4}


# --- Forged button data ---

async def test_disabled_server_and_product_cannot_be_ordered(session, fsm_context):
    user = await UserRepository(session).upsert_user(telegram_user_id=4242, username="c", language_code="en")
    await ServerRepository(session).create_or_update(
        slug="off-1", display_name="Off", country_code="DE", country_name="Off", host="x", enabled=False)
    await ServerRepository(session).create_or_update(
        slug="on-1", display_name="On", country_code="DE", country_name="On", host="y")
    await ProductRepository(session).create_or_update(
        code="old", title="Old", duration_days=30, device_limit=1,
        price_amount=Decimal("1.00"), price_currency="EUR", enabled=False)
    data = {"db_user": user, "session": session}

    query = callback("srv_off-1")
    await callback_select_server(query, data)
    query.message.edit_text.assert_not_called()

    for forged in ("plan_off-1_old", "plan_on-1_old"):
        query = callback(forged)
        await callback_select_plan(query, data, fsm_context)
        query.message.edit_text.assert_not_called()
        assert await fsm_context.get_state() is None


# --- Installer ---

def run_installer(tmp_path, stat_output):
    """Run the installer with a fake `stat`, so the test means the same as root or not."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_stat = bin_dir / "stat"
    fake_stat.write_text(f"#!/bin/sh\n{stat_output}\n")
    fake_stat.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(INSTALLER)], capture_output=True, text=True, env=env)


@pytest.mark.parametrize("stat_output", [
    # Owned by the service user, as the old setup guide left it.
    'case "$2" in %u) echo 999;; *) echo 755;; esac',
    # Owned by root but group-writable.
    'case "$2" in %u) echo 0;; *) echo 775;; esac',
])
def test_installer_refuses_files_others_can_change(tmp_path, stat_output):
    result = run_installer(tmp_path, stat_output)
    assert result.returncode == 1
    assert "Refusing to install" in result.stdout
    assert "Created user" not in result.stdout


def test_vpnctl_ignores_config_path_under_sudo(tmp_path, monkeypatch):
    import importlib.machinery
    import importlib.util
    path = str(Path(__file__).resolve().parents[2] / "scripts/provisioner/vpnctl")
    loader = importlib.machinery.SourceFileLoader("vpnctl_mod", path)
    vpnctl = importlib.util.module_from_spec(importlib.util.spec_from_loader("vpnctl_mod", loader))
    loader.exec_module(vpnctl)

    evil = tmp_path / "evil.conf"
    evil.write_text("AWG_BIN=/tmp/evil\n")
    monkeypatch.setattr(vpnctl, "DEFAULT_CONFIG_PATH", str(tmp_path / "missing.conf"))
    monkeypatch.setenv("VPNCTL_CONFIG", str(evil))
    assert vpnctl.load_settings()["AWG_BIN"] == "/tmp/evil"
    monkeypatch.setenv("SUDO_USER", "vpn-provisioner")
    assert vpnctl.load_settings()["AWG_BIN"] == "awg"
