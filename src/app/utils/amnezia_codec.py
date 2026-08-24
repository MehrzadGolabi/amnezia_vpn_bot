"""
AmneziaVPN URL Codec: Encodes and decodes Amnezia configuration files to and from vpn:// format.
Uses Qt qCompress (zlib compression with 4-byte big-endian uncompressed size header) + URL-safe Base64.
"""

import base64
import struct
import zlib
from typing import Optional


def q_compress(data: bytes, level: int = 8) -> bytes:
    """Compress data using Qt's qCompress format."""
    compressed = zlib.compress(data, level)
    header = struct.pack(">I", len(data))
    return header + compressed


def q_uncompress(data: bytes) -> bytes:
    """Decompress data using Qt's qUncompress format."""
    if len(data) < 4:
        return b""
    uncompressed_size = struct.unpack(">I", data[:4])[0]
    compressed_data = data[4:]
    try:
        uncompressed = zlib.decompress(compressed_data)
        if len(uncompressed) == uncompressed_size:
            return uncompressed
    except Exception:
        pass
    return b""


def encode_vpn_url(config_text: str) -> str:
    """Encodes WireGuard/AmneziaWG config text into a one-click vpn:// URL."""
    compressed = q_compress(config_text.encode("utf-8"), level=8)
    b64 = base64.urlsafe_b64encode(compressed).rstrip(b"=").decode("ascii")
    return f"vpn://{b64}"


def decode_vpn_url(vpn_url: str) -> Optional[str]:
    """Decodes a vpn:// URL string back into original configuration text."""
    raw = vpn_url.strip()
    if raw.startswith("vpn://"):
        raw = raw[6:]
    padding = (4 - len(raw) % 4) % 4
    raw += "=" * padding
    try:
        data = base64.urlsafe_b64decode(raw.encode("ascii"))
        uncompressed = q_uncompress(data)
        if uncompressed:
            return uncompressed.decode("utf-8")
    except Exception:
        pass
    return None
