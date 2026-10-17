# AmneziaWG VPN sales bot

A Telegram bot that sells AmneziaWG 3.1 VPN subscriptions, in English or Farsi. Customers pick a plan and upload a payment receipt. An admin approves it, and the bot creates a client on the VPN server and sends the config. The bot sends renewal reminders, disables clients when they expire, and removes them after a grace period.

It has three parts:

- `bot`: the Telegram interface for customers and admins.
- `worker`: creates, disables and removes clients by calling `vpnctl` on the VPN server.
- `scheduler`: sends reminders and queues expiry jobs.

Without Docker they run together in one process (`python -m src.app.main`, about 200 MB of RAM). With Docker each runs in its own container.

The VPN server is a native `amneziawg-go` + `awg-quick@awg1` setup. `vpnctl` edits `/etc/amnezia/amneziawg/awg1.conf` in the same format as `awg-add-client.sh`, so you can keep adding your own clients with that script.

## Setup

- [Without Docker](docs/NATIVE_SETUP.md): systemd services on the VPN host with SQLite. This is the simplest option.
- [With Docker](docs/DOCKER_SETUP.md): containers with Postgres, reaching the VPN host over SSH.

Both need the AmneziaWG 3.1 server running first.

## Docs

- [Configuration](docs/CONFIGURATION.md): every `.env` setting.
- [vpnctl](docs/VPNCTL.md): what the server-side script does, its files, and testing without a VPS.
- [Operations](docs/OPERATIONS.md): admin commands, logs, backups, updates and troubleshooting.
- [Architecture](docs/ARCHITECTURE.md): how the pieces fit, the job queue, and security.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
make test
```

The tests run `vpnctl` and the worker against a fake AmneziaWG server (`scripts/dev/sandbox.sh`), so they don't need a VPS or root.
