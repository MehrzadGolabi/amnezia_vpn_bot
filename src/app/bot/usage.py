import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.app.bot.locales.strings import get_text
from src.app.utils.logging import get_logger

logger = get_logger(__name__)

# Long enough for vpnctl over SSH to answer, short enough that a down server doesn't stall the menu.
STATUS_TIMEOUT_SECONDS = 8


def format_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_last_seen(when: Optional[datetime], lang: Optional[str], now: Optional[datetime] = None) -> str:
    if when is None:
        return get_text("never_connected", lang)
    now = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - when).total_seconds()))
    if seconds < 120:
        return get_text("just_now", lang)
    if seconds < 3600:
        return get_text("minutes_ago", lang, n=seconds // 60)
    if seconds < 48 * 3600:
        return get_text("hours_ago", lang, n=seconds // 3600)
    return when.strftime("%Y-%m-%d %H:%M UTC")


async def usage_text(provisioner, server, sub, lang: Optional[str]) -> str:
    """Data used and last connection for one subscription, read live from the VPN server.

    The server keeps these counters in memory, so they start again from zero when the
    interface restarts or the peer is disabled and enabled.
    """
    if provisioner is None or server is None or not sub.peer_external_id:
        return ""
    try:
        status = await asyncio.wait_for(
            provisioner.get_peer_status(server=server, peer_external_id=sub.peer_external_id),
            timeout=STATUS_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.warning("peer_status_unavailable", subscription_id=str(sub.id), error=str(e))
        return get_text("usage_unavailable", lang)
    if not status.exists:
        return ""
    # The server's "received" is what the client uploaded, and "sent" is what it downloaded.
    return get_text(
        "usage",
        lang,
        total=format_bytes(status.bytes_received + status.bytes_sent),
        down=format_bytes(status.bytes_sent),
        up=format_bytes(status.bytes_received),
        last_seen=format_last_seen(status.last_handshake, lang),
    )
