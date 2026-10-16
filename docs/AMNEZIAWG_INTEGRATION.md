# AmneziaWG Integration Reference

The bot manages clients on a **native AmneziaWG 3.1 server**: `amneziawg-go` (or the 3.1 kernel module) driven by `awg-quick@awg1`, with no Docker container. Everything server-side goes through one script, `scripts/provisioner/vpnctl`, installed as `/usr/local/sbin/vpnctl`.

## 1. What vpnctl does

| Command | Effect on the server |
|---|---|
| `create-peer --subscription-id <uuid> --label <name>` | Picks the first free address in the server's subnet, generates keys with `awg`, appends a `[Peer]` block to `awg1.conf`, applies it live with `awg set`, and writes `clients/<name>.conf`. Running it again with the same label returns the existing config instead of making a second peer. |
| `disable-peer --peer-id <name>` | Removes the peer from `awg1.conf` and from the live interface, keeping its config so it can come back. Its address stays reserved. |
| `enable-peer --peer-id <name>` | Puts a disabled peer back, live and in `awg1.conf`. |
| `remove-peer --peer-id <name>` | Removes the peer everywhere and deletes its files. |
| `peer-status --peer-id <name>` | Last handshake and transfer counters from `awg show`. |
| `get-config --peer-id <name>` | Returns the stored client config (used for "Redeliver"). |

Each prints one JSON object. Exit codes: `0` ok, `1` server-side failure (the worker retries), `2` bad input and `3` unknown client (not retried).

Files, compatible with `awg-add-client.sh` / `awg-del-client.sh` from the migration guide:

```
/etc/amnezia/amneziawg/awg1.conf            [Peer] blocks, each starting with "# <name>"
/etc/amnezia/amneziawg/clients/<name>.conf  client config as delivered
/etc/amnezia/amneziawg/clients/<name>.peer  server-side [Peer] block, so disable/enable works
```

You can mix the bot with the shell scripts, with one caveat: `awg-add-client.sh` picks the next address after the highest one in `awg1.conf`, so it can't see the reserved address of a client the bot has disabled. Add manual clients with `vpnctl create-peer` if you also sell through the bot.

## 2. AWG 3.1 parameters in client configs

`vpnctl` copies **every** obfuscation line from the server's `[Interface]` into each client config, verbatim: `Jc`, `Jmin`, `Jmax`, `S1-S4`, `H1-H4`, `I1-I5`, `HeaderProtectionKey`, `ContentPaddingAddition`, `RekeyAfterTime`, `RekeyTimeout`, `RejectAfterTime`, `KeepaliveTimeout`, `MaxHandshakeAttempts`, `RandomTrailers` and `DisableCookies`. That keeps the values that must match on both sides (H1-H4, S1-S4, `HeaderProtectionKey`, `RandomTrailers`) in sync. Client configs also get `MTU = 1280`, as the 3.1 guide recommends.

If you change any of the matching values on the server, every client config has to be reissued.

Clients need a 3.1-capable app: AmneziaWG 3.1.x (Windows 3.1.0, Android/iOS/macOS 3.1.4) or AmneziaVPN 5.0.2.1+. Older apps can't parse these configs.

## 3. Delivery

The worker sends the `.conf` file as a Telegram document, then the `vpn://` key as a separate message. A 3.1 config with a SIP-style `I1` produces a `vpn://` key of about 1,100 characters, which is over Telegram's 1,024-character caption limit, so it can't ride in the caption.

## 4. Testing without a VPS

`scripts/dev/sandbox.sh` builds a throwaway 3.1 server config in a folder and points `vpnctl` at `scripts/dev/fake-awg`, a stand-in for the `awg` binary that keeps the "live interface" in a JSON file. No root, no network.

```bash
scripts/dev/sandbox.sh                 # creates ./.sandbox and prints the settings below
VPNCTL_CONFIG=.sandbox/vpnctl.conf scripts/provisioner/vpnctl create-peer \
    --subscription-id $(python3 -c 'import uuid; print(uuid.uuid4())') --label test1
```

To run the whole bot against it, put the two lines it prints into `.env`:

```ini
PROVISIONER_MODE=local
VPNCTL_COMMAND=env VPNCTL_CONFIG=/path/to/.sandbox/vpnctl.conf python3 /path/to/scripts/provisioner/vpnctl
```

The test suite uses the same sandbox (`tests/conftest.py`), so `make test` covers `vpnctl` and the worker end to end.
