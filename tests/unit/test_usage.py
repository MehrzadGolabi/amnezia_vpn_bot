import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.app.bot.usage import format_bytes, format_last_seen, usage_text
from src.app.integrations.provisioning.base import PeerStatus

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
SUB = SimpleNamespace(id=uuid.uuid4(), peer_external_id="user_abc")
SERVER = SimpleNamespace(slug="de-1")


class FakeProvisioner:
    def __init__(self, status=None, error=None, delay=0):
        self.status, self.error, self.delay = status, error, delay

    async def get_peer_status(self, *, server, peer_external_id):
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.status


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert format_bytes(2048) == "2 KB"
    assert format_bytes(5 * 1024 ** 2) == "5.0 MB"
    assert format_bytes(3 * 1024 ** 4) == "3072.0 GB"


def test_format_last_seen():
    assert format_last_seen(None, "en") == "never"
    assert format_last_seen(NOW - timedelta(seconds=30), "en", NOW) == "just now"
    assert "5" in format_last_seen(NOW - timedelta(minutes=5), "en", NOW)
    assert "3" in format_last_seen(NOW - timedelta(hours=3), "en", NOW)
    assert format_last_seen(NOW - timedelta(days=5), "en", NOW) == "2026-10-12 12:00 UTC"


async def test_usage_text_counts_from_the_client_side():
    status = PeerStatus(exists=True, is_active=True, last_handshake=None,
                        bytes_received=1024 ** 2, bytes_sent=3 * 1024 ** 2)
    text = await usage_text(FakeProvisioner(status), SERVER, SUB, "en")
    assert "4.0 MB" in text and "download 3.0 MB" in text and "upload 1.0 MB" in text


async def test_usage_text_when_server_is_unreachable():
    text = await usage_text(FakeProvisioner(error=RuntimeError("ssh down")), SERVER, SUB, "en")
    assert "not available" in text


async def test_usage_text_skips_missing_peer():
    assert await usage_text(FakeProvisioner(PeerStatus(exists=False, is_active=False)), SERVER, SUB, "en") == ""
    assert await usage_text(None, SERVER, SUB, "en") == ""
