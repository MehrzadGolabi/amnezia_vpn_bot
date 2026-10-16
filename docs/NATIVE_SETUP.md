# Running the bot without Docker

The bot, worker and scheduler run as systemd services on the VPN host. The worker calls `vpnctl` locally through sudo, and the database is one SQLite file. Nothing goes over SSH.

Before you start, `awg-quick@awg1` must be running and `awg --version` must show `v3.1.x`.

## 1. Code and dependencies

```bash
sudo apt install -y python3-venv git
sudo git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot /opt/amnezia_vpn_bot
cd /opt/amnezia_vpn_bot
sudo python3 -m venv .venv
sudo .venv/bin/pip install .
```

The services expect the venv at `/opt/amnezia_vpn_bot/.venv`.

## 2. vpnctl and the service user

```bash
sudo ./scripts/provisioner/install-provisioner.sh
sudo nano /etc/amnezia/vpnctl.conf        # set ENDPOINT_HOST to the server's public IP or hostname
```

The installer adds `/usr/local/sbin/vpnctl`, `/etc/amnezia/vpnctl.conf`, the `vpn-provisioner` user, and a sudoers rule that lets that user run only `vpnctl`. The services run as `vpn-provisioner`.

Check that it works:

```bash
sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl create-peer \
    --subscription-id $(cat /proc/sys/kernel/random/uuid) --label smoke-test
sudo cat /etc/amnezia/amneziawg/clients/smoke-test.conf    # import into a 3.1 app and connect
sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl remove-peer --peer-id smoke-test
```

## 3. `.env`

```bash
sudo cp .env.example .env
sudo mkdir -p data
sudo nano .env
```

Change these lines. The `POSTGRES_*` lines are only for Docker and can stay or go.

```ini
TELEGRAM_BOT_TOKEN=<from @BotFather>
ADMIN_TELEGRAM_IDS=<your Telegram user ID>
ADMIN_CHAT_ID=<your user ID, or a group ID for receipts>
DATABASE_URL=sqlite+aiosqlite:////opt/amnezia_vpn_bot/data/bot.db
PROVISIONER_MODE=local
PAYMENT_INSTRUCTIONS_EN=...
PAYMENT_INSTRUCTIONS_FA=...
VPN_SERVER_MAIN_1_DISPLAY_NAME=Germany
VPN_SERVER_MAIN_1_COUNTRY_CODE=DE
```

Every setting is described in [Configuration](CONFIGURATION.md).

```bash
sudo chown -R vpn-provisioner:vpn-provisioner /opt/amnezia_vpn_bot
sudo chmod 600 .env
```

## 4. Start

```bash
sudo cp deploy/systemd/vpnbot-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vpnbot-bot vpnbot-worker vpnbot-scheduler
journalctl -u vpnbot-bot -u vpnbot-worker -u vpnbot-scheduler -f
```

`vpnbot-bot` creates the database tables on first start, along with three default plans (1, 3 and 6 months, in EUR). To test the whole flow, send `/start` to the bot, place an order, and approve it from the admin chat. The config should arrive within a few seconds.

## Your own clients

Keep using `awg-add-client.sh` and `awg-del-client.sh` for clients you don't sell. They work alongside the bot (see [vpnctl](VPNCTL.md#files)). Avoid names starting with `user_`, which the bot uses.

For updates, backups and changing plans, see [Operations](OPERATIONS.md).
