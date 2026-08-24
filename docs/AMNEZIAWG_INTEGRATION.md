# AmneziaWG Integration Reference

## 1. AmneziaWG Header Obfuscation Protocol

AmneziaWG extends WireGuard by introducing junk packets and variable message headers to prevent deep packet inspection (DPI) detection and SNI sniffing.

The parameters configured in `scripts/provisioner/vpnctl.conf` and used by `vpnctl`:

| Parameter | Meaning | Recommended Range | Description |
|---|---|---|---|
| `Jc` | Junk packet count | `1 - 128` | Number of unencrypted decoy packets sent before handshake |
| `Jmin` | Minimum junk packet size | `10 - 1200` | Lower byte boundary for decoy packet payload |
| `Jmax` | Maximum junk packet size | `50 - 1280` | Upper byte boundary for decoy packet payload |
| `S1` | Init packet padding | `15 - 150` | Byte padding prepended to handshake initiation |
| `S2` | Response packet padding | `15 - 150` | Byte padding prepended to handshake response |
| `H1` - `H4` | Custom Header IDs | `1 - 2147483647` | Custom 32-bit magic values replacing standard WireGuard header types |

## 2. Client Compatibility

Clients generated with `.conf` and `.vpn` formats are directly compatible with:
- **Amnezia VPN App** (Windows, macOS, iOS, Android, Linux)
- **AmneziaWG Client CLI** (`awg-quick up <file>`)

Files are delivered as attachments over Telegram and can be imported into the mobile and desktop apps with one click or QR code scan.
