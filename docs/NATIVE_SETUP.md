# Setup

The bot, worker and scheduler run together as one systemd service, `vpnbot`, on one VPN host. The worker asks `vpnctl` on that host through a Unix socket, and reaches any other VPN hosts over Tailscale. The database is one SQLite file.

Run one bot only. A Telegram bot token can be used by one running bot at a time, so other servers are added to this bot (see [More servers](#more-servers)) instead of getting a bot of their own.

Before you start, `awg-quick@awg1` must be running and `awg --version` must show `v3.1.x`. Commands below are run as root.

## 1. Code and dependencies

```bash
apt install -y python3-venv git
git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot /opt/amnezia_vpn_bot
cd /opt/amnezia_vpn_bot
python3 -m venv .venv
.venv/bin/pip install .
```

The services expect the venv at `/opt/amnezia_vpn_bot/.venv`.

## 2. vpnctl and the service user

```bash
./scripts/provisioner/install-provisioner.sh
nano /etc/amnezia/vpnctl.conf        # set ENDPOINT_HOST to this server's public IP or hostname
```

The installer adds `/usr/local/sbin/vpnctl`, `/etc/amnezia/vpnctl.conf`, the `vpn-provisioner` user (no shell, no sudo), and `vpnctl.socket`, which lets that user ask `vpnctl` for the six things the bot needs. The bot runs as `vpn-provisioner`. Running the installer again is safe and keeps your `vpnctl.conf`.

If `CONF_DIR` in `vpnctl.conf` isn't `/etc/amnezia/amneziawg`, run the installer again after changing it, so the sandbox lets `vpnctl` write there.

Check that it works, first `vpnctl` itself, then through the socket the way the bot uses it:

```bash
vpnctl create-peer --subscription-id $(cat /proc/sys/kernel/random/uuid) --label smoke-test
cat /etc/amnezia/amneziawg/clients/smoke-test.conf    # import into a 3.1 app and connect
vpnctl remove-peer --peer-id smoke-test
sudo -u vpn-provisioner vpnctl-check                 # "exit_code": 0 and "exists": false
```

If `vpnctl-check` fails but `vpnctl` works, look at `journalctl -u 'vpnctl@*'`. A sandbox error there usually means the AmneziaWG control socket isn't where `vpnctl@.service` expects it: check `ls /run/amneziawg /run/wireguard`.

## 3. `.env`

```bash
cp .env.example .env
nano .env
```

Set these:

```ini
APP_ENV=production
TELEGRAM_BOT_TOKEN=<from @BotFather>
ADMIN_TELEGRAM_IDS=<your Telegram user ID>
ADMIN_CHAT_ID=<your user ID, or a group ID for receipts>
DATABASE_URL=sqlite+aiosqlite:////opt/amnezia_vpn_bot/data/bot.db
PROVISIONER_MODE=vpnctl
PAYMENT_INSTRUCTIONS_EN=...
PAYMENT_INSTRUCTIONS_FA=...
```

At the bottom, keep one server group for this host. Leave out `HOST`, so `vpnctl` runs locally:

```ini
VPN_SERVER_MAIN_1_SLUG=main-1
VPN_SERVER_MAIN_1_COUNTRY_CODE=DE
VPN_SERVER_MAIN_1_DISPLAY_NAME=Germany
VPN_SERVER_MAIN_1_ENABLED=true
```

Delete any other `VPN_SERVER_*` lines, such as example groups from an older `.env`. Each group is shown to customers as a location. The `POSTGRES_*` lines are only for Docker and can stay. Every setting is described in [Configuration](CONFIGURATION.md).

Keep the token private. If it is ever posted somewhere, run `/revoke` in @BotFather and put the new one in `.env`.

The code stays owned by root, and `vpn-provisioner` gets only the database folder and read access to `.env`. If the service user could change the code, a break-in to the bot would become root the next time you update, because root runs `install-provisioner.sh` from this folder.

```bash
mkdir -p data
chown -R vpn-provisioner:vpn-provisioner data
chown root:vpn-provisioner .env
chmod 640 .env
```

## 4. Start

```bash
cp deploy/systemd/vpnbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vpnbot
journalctl -u vpnbot -f
```

`vpnbot` creates the database tables on first start, along with three default plans (1, 3 and 6 months, in EUR). To test the whole flow, send `/start` to the bot, place an order, and approve it from the admin chat. The config should arrive within a few seconds.

## More servers

Each extra VPN host needs AmneziaWG and `vpnctl`, but not the bot. The bot reaches it over Tailscale, so nothing has to be open to the internet, and no SSH key or login account is involved.

Once, on the bot host, create the token the bot proves itself with, and print its hash for the other servers:

```bash
TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
echo "VPNCTL_TOKEN=$TOKEN" >> /opt/amnezia_vpn_bot/.env
printf '%s' "$TOKEN" | sha256sum | cut -d' ' -f1     # the hash, for --token-sha256
tailscale ip -4                                      # the bot host's Tailscale IP
```

Then on the new server, with `awg-quick@awg1` and Tailscale running:

```bash
apt install -y git
git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot /opt/amnezia_vpn_bot
cd /opt/amnezia_vpn_bot
./scripts/provisioner/install-provisioner.sh --tailnet <bot host tailscale IP> --token-sha256 <hash>
nano /etc/amnezia/vpnctl.conf        # ENDPOINT_HOST = this server's public IP
```

`vpnctl` now listens on this server's Tailscale address, port 7391, and answers only the bot host, and only with the token: the installer sets `ALLOWED_CLIENTS` and `CLIENT_TOKEN_SHA256` in `vpnctl.conf` and limits the socket to that address as well. The token itself never leaves the bot host's `.env`. Set up the Tailscale policy in [Security](ARCHITECTURE.md#how-the-bot-reaches-vpnctl) too, so other machines in your tailnet can't reach the port at all.

Run the `vpnctl create-peer` smoke test from step 2 on the new server. Then, on the bot host, check that the bot can reach it. The output should be JSON with `"exists": false`:

```bash
sudo -u vpn-provisioner vpnctl-check <new server tailscale IP>
```

Add a server group to `.env` and restart:

```ini
VPN_SERVER_TR_1_SLUG=tr-1
VPN_SERVER_TR_1_COUNTRY_CODE=TR
VPN_SERVER_TR_1_DISPLAY_NAME=Turkey
VPN_SERVER_TR_1_ENABLED=true
VPN_SERVER_TR_1_HOST=<new server tailscale IP>
```

```bash
systemctl restart vpnbot
```

Customers now see both locations. To stop selling a location without touching existing customers, set its `ENABLED=false` and restart.

## Your own clients

Keep using `awg-add-client.sh` and `awg-del-client.sh` for clients you don't sell, on any server. They work alongside the bot (see [vpnctl](VPNCTL.md#files)). Avoid names starting with `user_`, which the bot uses.

For updates, backups and changing plans, see [Operations](OPERATIONS.md).
