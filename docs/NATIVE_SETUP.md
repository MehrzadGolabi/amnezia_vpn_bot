# Running the bot without Docker

This sets up the bot, worker and scheduler as three systemd services on the VPN host itself, next to the native AmneziaWG 3.1 server (`awg-quick@awg1`, from the migration guide). The worker calls `vpnctl` locally through sudo. No SSH, no Docker, and the database is a single SQLite file.

Before you start, `awg-quick@awg1` must be running and `awg --version` must report `v3.1.x`.

## 1. Get the code

```bash
sudo apt install -y python3-venv git
sudo git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot /opt/amnezia_vpn_bot
cd /opt/amnezia_vpn_bot
sudo python3 -m venv .venv
sudo .venv/bin/pip install .
```

## 2. Install vpnctl and the service user

```bash
sudo ./scripts/provisioner/install-provisioner.sh
```

This installs `/usr/local/sbin/vpnctl`, `/etc/amnezia/vpnctl.conf`, the `vpn-provisioner` user, and a sudoers entry that only lets that user run `vpnctl`. The three services run as `vpn-provisioner`.

Open `/etc/amnezia/vpnctl.conf` and set `ENDPOINT_HOST` to your server's public IP or hostname. Leave it empty to use the IP of the default route, which is what `awg-add-client.sh` does. The defaults (`INTERFACE=awg1`, DNS `1.1.1.1, 9.9.9.9`, MTU 1280) match the guide.

Test it as the service user:

```bash
sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl create-peer \
    --subscription-id $(cat /proc/sys/kernel/random/uuid) --label smoke-test
sudo cat /etc/amnezia/amneziawg/clients/smoke-test.conf    # import this into a 3.1 app and connect
sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl remove-peer --peer-id smoke-test
```

## 3. Configure `.env`

```bash
sudo cp .env.example .env
sudo mkdir -p data
sudo nano .env
```

Change these lines and delete the example `VPN_SERVER_DE_1_*` and `VPN_SERVER_TR_1_*` blocks:

```ini
APP_ENV=production
TELEGRAM_BOT_TOKEN=<from @BotFather>
ADMIN_TELEGRAM_IDS=<your Telegram user id>
ADMIN_CHAT_ID=<your user id, or a group/channel id for receipts>
DATABASE_URL=sqlite+aiosqlite:////opt/amnezia_vpn_bot/data/bot.db
PROVISIONER_MODE=local
VPNCTL_COMMAND=sudo -n /usr/local/sbin/vpnctl
PAYMENT_INSTRUCTIONS_EN=...
PAYMENT_INSTRUCTIONS_FA=...

# The one location customers can buy. HOST is only used for SSH, so any value works here.
VPN_SERVER_MAIN_1_SLUG=main-1
VPN_SERVER_MAIN_1_COUNTRY_CODE=DE
VPN_SERVER_MAIN_1_DISPLAY_NAME=Germany
VPN_SERVER_MAIN_1_HOST=localhost
VPN_SERVER_MAIN_1_MAX_ACTIVE_SUBSCRIPTIONS=200
```

Then lock it down:

```bash
sudo chown -R vpn-provisioner:vpn-provisioner /opt/amnezia_vpn_bot
sudo chmod 600 .env
```

The first start creates three default plans (1, 3 and 6 months, priced in EUR). Change them in the `products` table if you need to.

## 4. Start the services

```bash
sudo cp deploy/systemd/vpnbot-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vpnbot-bot vpnbot-worker vpnbot-scheduler
journalctl -u vpnbot-bot -u vpnbot-worker -u vpnbot-scheduler -f
```

`vpnbot-bot` runs the database migrations before it starts. Send `/start` to the bot, place an order, approve it from the admin chat, and the config should arrive within a few seconds.

## Adding your own clients with the guide's scripts

`awg-add-client.sh` and `awg-del-client.sh` work alongside the bot. Both use the same `# name` layout in `awg1.conf`, and `vpnctl` reads every peer in that file before it picks an address, so the bot never reuses an address the scripts handed out. Give your own clients names that don't start with `user_`, so they're easy to tell apart from the ones the bot sells.

There's one rule. The scripts only read `awg1.conf`, so they can reuse the address of a client the bot disabled after it expired. That doesn't matter, because the bot never turns an expired client back on. Renewing creates a new config, and the old one is deleted after `PEER_REMOVAL_GRACE_DAYS`. If you run `vpnctl enable-peer` by hand on an old client and its address has been taken in the meantime, `vpnctl` refuses rather than create a clash.

## Updating

```bash
cd /opt/amnezia_vpn_bot
sudo -u vpn-provisioner git pull
sudo -u vpn-provisioner .venv/bin/pip install .
sudo install -m 755 scripts/provisioner/vpnctl /usr/local/sbin/vpnctl
sudo systemctl restart vpnbot-bot vpnbot-worker vpnbot-scheduler
```

Back up `data/bot.db` and `/etc/amnezia/amneziawg/` together. One holds the subscriptions and the other holds the matching peers.
