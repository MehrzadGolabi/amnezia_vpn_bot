# Running the bot without Docker

The bot, worker and scheduler run together as one systemd service, `vpnbot`, on one VPN host. The worker runs `vpnctl` on that host through sudo, and reaches any other VPN hosts over SSH. The database is one SQLite file.

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

The installer adds `/usr/local/sbin/vpnctl`, `/etc/amnezia/vpnctl.conf`, the `vpn-provisioner` user, and a sudoers rule that lets that user run only `vpnctl`. The services run as `vpn-provisioner`. Running the installer again is safe and keeps your `vpnctl.conf`.

Check that it works:

```bash
sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl create-peer \
    --subscription-id $(cat /proc/sys/kernel/random/uuid) --label smoke-test
cat /etc/amnezia/amneziawg/clients/smoke-test.conf    # import into a 3.1 app and connect
sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl remove-peer --peer-id smoke-test
```

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
PROVISIONER_MODE=local
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

Each extra VPN host needs AmneziaWG and `vpnctl`, but not the bot. The bot host reaches it over SSH as `vpn-provisioner`. Use the host's Tailscale IP so SSH does not have to be open to the internet.

On the new server, with `awg-quick@awg1` running:

```bash
apt install -y git
git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot /opt/amnezia_vpn_bot
cd /opt/amnezia_vpn_bot
./scripts/provisioner/install-provisioner.sh
nano /etc/amnezia/vpnctl.conf        # ENDPOINT_HOST = this server's public IP
```

Run the smoke test from step 2 there as well.

On the bot host, create an SSH key for `vpn-provisioner` once:

```bash
sudo -u vpn-provisioner ssh-keygen -t ed25519 -N '' -f /home/vpn-provisioner/.ssh/id_ed25519
cat /home/vpn-provisioner/.ssh/id_ed25519.pub
```

On the new server, add that public key, limited to the bot host's Tailscale IP and to `vpnctl`:

```bash
echo 'restrict,from="<bot host tailscale IP>",command="/usr/local/sbin/vpnctl-ssh" <the public key>' \
    >> /home/vpn-provisioner/.ssh/authorized_keys
```

`restrict` turns off port forwarding, terminals and agent forwarding, `from` refuses the key from any other address, and `command` runs `vpnctl-ssh`, which allows only the `vpnctl` commands the bot sends. The installer also adds `/etc/ssh/sshd_config.d/vpn-provisioner.conf`, which applies the same limits to any key for this user. See [Security](ARCHITECTURE.md#more-than-one-server) for what this protects against.

Back on the bot host, connect once. This saves the server's host key and checks that `vpnctl` runs. The output should be JSON with `"exists": false`. The worker trusts only the key saved here, so check the fingerprint `ssh` shows against the server's own (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the server).

```bash
sudo -u vpn-provisioner ssh vpn-provisioner@<tailscale IP> sudo -n /usr/local/sbin/vpnctl peer-status --peer-id test
```

Add a server group to `.env` and restart:

```ini
VPN_SERVER_TR_1_SLUG=tr-1
VPN_SERVER_TR_1_COUNTRY_CODE=TR
VPN_SERVER_TR_1_DISPLAY_NAME=Turkey
VPN_SERVER_TR_1_ENABLED=true
VPN_SERVER_TR_1_HOST=<tailscale IP>
VPN_SERVER_TR_1_SSH_PRIVATE_KEY_PATH=/home/vpn-provisioner/.ssh/id_ed25519
VPN_SERVER_TR_1_SSH_KNOWN_HOSTS_PATH=/home/vpn-provisioner/.ssh/known_hosts
```

```bash
systemctl restart vpnbot
```

Customers now see both locations. To stop selling a location without touching existing customers, set its `ENABLED=false` and restart.

## Your own clients

Keep using `awg-add-client.sh` and `awg-del-client.sh` for clients you don't sell, on any server. They work alongside the bot (see [vpnctl](VPNCTL.md#files)). Avoid names starting with `user_`, which the bot uses.

For updates, backups and changing plans, see [Operations](OPERATIONS.md).
