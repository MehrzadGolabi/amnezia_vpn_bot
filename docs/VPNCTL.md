# vpnctl

`vpnctl` is the only code that changes the VPN server. It's a Python script at `scripts/provisioner/vpnctl`, installed as `/usr/local/sbin/vpnctl`. The bot never runs it: it connects to a socket, and systemd starts `vpnctl serve` as root, in a sandbox, for each connection. You can also run the commands by hand as root.

## Commands

| Command | What it does |
|---|---|
| `create-peer --subscription-id <uuid> --label <name>` | Takes the first free address in the server's subnet, generates keys, adds the peer to `awg1.conf`, applies it live with `awg set`, and saves the client config. If a client with that label already exists, it returns the existing config instead. |
| `disable-peer --peer-id <name>` | Removes the peer from `awg1.conf` and the live interface. The config is kept, so it can be re-enabled. |
| `enable-peer --peer-id <name>` | Puts a disabled peer back. It refuses if another peer has taken the address in the meantime. |
| `remove-peer --peer-id <name>` | Deletes the peer and its files. |
| `peer-status --peer-id <name>` | Shows the last handshake and the bytes sent and received. |
| `get-config --peer-id <name>` | Prints the saved client config. |
| `encode < <file>` / `decode -u <vpn://...>` | Converts between a `.conf` file and a `vpn://` key. `encode` reads the config on stdin. |
| `serve` | Answers one request on stdin. systemd runs it; see below. |

Run by hand, every command prints one JSON object. The exit code tells the worker whether a retry can help:

| Exit code | Meaning | Worker retries? |
|---|---|---|
| `0` | Success | |
| `1` | Server-side error, such as the interface being down | Yes |
| `2` | Bad input | No |
| `3` | No client with that name | No |
| `4` | The caller isn't allowed (`ALLOWED_CLIENTS`) | No |

## Requests from the bot

The bot sends one line of JSON per connection and reads one line back:

```
{"command": "peer-status", "args": {"peer_id": "user_1_3f2b8c1e_de-1"}}
{"exit_code": 0, "result": {"exists": true, "enabled": true, ...}}
{"exit_code": 3, "error": "No client config for x"}
```

`command` is one of the six commands above, from `create-peer` to `get-config`, and `args` holds exactly their options, with `-` written as `_` (`subscription_id`, `label`, `peer_id`). Anything else, including `encode`, `decode` and `serve`, is refused with exit code 2. A request may be at most 4 KB and must arrive within 10 seconds.

| Unit | Listens on | Who can connect |
|---|---|---|
| `vpnctl.socket` | `/run/vpnctl/vpnctl.sock` | root and the `vpn-provisioner` group: the bot on this host |
| `vpnctl-tailnet.socket` | this host's Tailscale IP, port 7391 (`--tailnet`) | the addresses in `ALLOWED_CLIENTS`, which `vpnctl` checks itself |

Each connection starts `vpnctl@.service` (or `vpnctl-tailnet@.service`). It keeps only `CAP_NET_ADMIN`, can write only `/etc/amnezia/amneziawg`, and can't open network connections. Its log is in `journalctl -u 'vpnctl@*'`.

`vpnctl-check [<host> [port]]` sends a `peer-status` request the way the bot does, and prints the answer.

## Files

```
/etc/amnezia/vpnctl.conf                     settings
/etc/amnezia/amneziawg/awg1.conf             server config; each client is a [Peer] that starts with "# <name>"
/etc/amnezia/amneziawg/clients/<name>.conf   client config
/etc/amnezia/amneziawg/clients/<name>.peer   the [Peer] block, kept so disable/enable works
```

This is the same layout `awg-add-client.sh` and `awg-del-client.sh` use, so the scripts and the bot can manage the same server. `vpnctl` reads every peer in `awg1.conf` before it picks an address. The scripts don't read `.peer` files, so they can reuse a disabled client's address. That's harmless, because the bot never re-enables expired clients, and `enable-peer` refuses if the address is taken.

## Settings (`/etc/amnezia/vpnctl.conf`)

| Setting | Default | Meaning |
|---|---|---|
| `INTERFACE` | `awg1` | The `awg-quick` interface. |
| `CONF_DIR` | `/etc/amnezia/amneziawg` | Where `<INTERFACE>.conf` and `clients/` live. |
| `ENDPOINT_HOST` | IP of the default route | Address clients connect to. Set it if the server is behind NAT, or to use a hostname. |
| `ENDPOINT_PORT` | server's `ListenPort` | |
| `CLIENT_DNS` | `1.1.1.1, 9.9.9.9` | |
| `CLIENT_MTU` | `1280` | |
| `CLIENT_ALLOWED_IPS` | `0.0.0.0/0, ::/0` | |
| `PERSISTENT_KEEPALIVE` | `25` | |
| `AWG_BIN` | `awg` | The `awg` binary from amneziawg-tools 3.1. |
| `ALLOWED_CLIENTS` | | Comma-separated IPs that may connect over TCP: the bot host's Tailscale IP. Empty refuses everyone. Set by `install-provisioner.sh --tailnet`. |

Keys, port, subnet and obfuscation values are read from `awg1.conf`, so they never need to be copied here.

## AWG 3.1 parameters

Every obfuscation line in the server's `[Interface]` is copied into each client config unchanged. That covers `Jc`, `Jmin`, `Jmax`, `S1`-`S4`, `H1`-`H4`, `I1`-`I5`, `HeaderProtectionKey`, `ContentPaddingAddition`, `RekeyAfterTime`, `RekeyTimeout`, `RejectAfterTime`, `KeepaliveTimeout`, `MaxHandshakeAttempts`, `RandomTrailers` and `DisableCookies`. If you change H1-H4, S1-S4, `HeaderProtectionKey` or `RandomTrailers` on the server, every client config has to be issued again.

Clients need AmneziaWG 3.1.x or AmneziaVPN 5.0.2.1 or later.

## Testing without a VPS

`scripts/dev/sandbox.sh` builds a fake 3.1 server in a folder. `scripts/dev/fake-awg` stands in for `awg` and stores the "live" peers in a JSON file. It needs no root and no network.

```bash
scripts/dev/sandbox.sh            # creates ./.sandbox and prints the settings below
VPNCTL_CONFIG=.sandbox/vpnctl.conf scripts/provisioner/vpnctl create-peer \
    --subscription-id $(python3 -c 'import uuid; print(uuid.uuid4())') --label test1
```

To run the whole bot against the sandbox, put the two lines the script prints into `.env`. The bot then runs `vpnctl serve` itself for each request, instead of connecting to the socket:

```ini
PROVISIONER_MODE=vpnctl
VPNCTL_DEV_COMMAND=env VPNCTL_CONFIG=/path/to/.sandbox/vpnctl.conf python3 /path/to/scripts/provisioner/vpnctl
```

The test suite uses the same sandbox. It also runs `vpnctl serve` behind real Unix and TCP sockets, the way systemd does, to test the bot's connections and the `ALLOWED_CLIENTS` check.
