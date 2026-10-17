# Operations

## Admin commands

Send these to the bot from an account listed in `ADMIN_TELEGRAM_IDS`.

| Command | What it does |
|---|---|
| `/admin` | Shows pending receipts and open tickets. |
| `/servers` | Shows each server's active subscriptions, and lets you turn a server on or off for new orders. |
| `/products` | Lists the plans. |
| `/user <telegram_id>` | Shows a customer and their subscriptions, with data used and last connection. |
| `/extend <config name> <days>` | Adds days to a subscription and turns it back on if it had expired. A negative number takes days off. |
| `/block <telegram_id>`, `/unblock <telegram_id>` | Suspends or restores a customer. |

Receipts arrive in `ADMIN_CHAT_ID` with Approve and Reject buttons. Approving queues a job, and the worker creates the client and sends the config.

Turning a server off in `/servers` lasts until the bot restarts. On startup the bot reloads servers from `.env`, so use `VPN_SERVER_<NAME>_ENABLED=false` to turn one off permanently.

## Languages

Customers can use the bot in English or Farsi. New users start in Farsi if their Telegram app is set to Farsi, and in English otherwise. They can switch at any time with the Language button in the menu or `/language`, and the choice is kept. Admin screens stay in English.

In Farsi, plan names are built from the plan's length and device limit (for example "3 ماهه (2 کاربر)"), and locations use the Farsi name of their `COUNTRY_CODE`. Payment instructions come from `PAYMENT_INSTRUCTIONS_FA`.

## Subscription lifecycle

1. The admin approves the order, and the worker creates the client and sends the `.conf` file and a `vpn://` key.
2. Reminders go out `REMINDER_DAYS_BEFORE_EXPIRY` days before expiry.
3. At expiry, the scheduler queues a disable job. The client is removed from `awg1.conf` and the interface, but its files are kept.
4. After `PEER_REMOVAL_GRACE_DAYS`, the client is deleted.

Renewing from a subscription's page adds time to the same config, so the customer doesn't need a new one. Once a client has been deleted after the grace period, renewing creates a new config.

Data used and last connection come from the VPN server's live counters. They start again from zero when the interface restarts or the client is turned off and on.

## Logs

Without Docker:

```bash
journalctl -u vpnbot -f
```

With Docker:

```bash
docker compose logs -f bot worker scheduler
```

When a job fails for good, or the bot can't send a config, an alert goes to `ADMIN_CHAT_ID`.

## Changing plans

There's no admin command for editing plans yet, so change them in the database. Without Docker (`sudo apt install sqlite3` first):

```bash
sudo -u vpn-provisioner sqlite3 /opt/amnezia_vpn_bot/data/bot.db \
  "UPDATE products SET price_amount = 7.00, price_currency = 'EUR' WHERE code = 'vpn-1m';"
```

The default plan codes are `vpn-1m`, `vpn-3m` and `vpn-6m`. The `enabled` column hides a plan.

## Backups

Back up the database and the AmneziaWG folder together. One holds the subscriptions, the other the matching peers.

Without Docker:

```bash
sudo sqlite3 /opt/amnezia_vpn_bot/data/bot.db ".backup /root/bot-$(date +%F).db"
sudo tar czf /root/amneziawg-$(date +%F).tgz /etc/amnezia
```

With Docker:

```bash
docker compose exec -T postgres pg_dump -U vpn_bot vpn_bot | gzip > bot-$(date +%F).sql.gz
```

## Updating

Without Docker:

```bash
cd /opt/amnezia_vpn_bot
sudo -u vpn-provisioner git pull
sudo -u vpn-provisioner .venv/bin/pip install .
sudo install -m 755 scripts/provisioner/vpnctl /usr/local/sbin/vpnctl
sudo systemctl restart vpnbot
```

If the server still has the older three services (`vpnbot-bot`, `vpnbot-worker`, `vpnbot-scheduler`), replace them with the single `vpnbot` service once:

```bash
sudo systemctl disable --now vpnbot-bot vpnbot-worker vpnbot-scheduler
sudo rm /etc/systemd/system/vpnbot-bot.service /etc/systemd/system/vpnbot-worker.service /etc/systemd/system/vpnbot-scheduler.service
sudo cp deploy/systemd/vpnbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vpnbot
```

On each extra VPN host, run `git pull` in `/opt/amnezia_vpn_bot`, then `sudo ./scripts/provisioner/install-provisioner.sh`. It updates `vpnctl` and `vpnctl-ssh` and keeps `vpnctl.conf`. If the bot's key in `/home/vpn-provisioner/.ssh/authorized_keys` doesn't start with `restrict,from=...`, add that part as shown in [More servers](NATIVE_SETUP.md#more-servers).

With Docker, run `git pull`, then `docker compose up -d --build`. Copy the new `vpnctl` to each VPN host as well.

## Troubleshooting

| Symptom | Check |
|---|---|
| Order approved but no config arrives | Worker log. A `vpnctl` error there names the cause. Run the same `vpnctl` command by hand as `vpn-provisioner`. |
| `sudo: a password is required` | `/etc/sudoers.d/vpn-provisioner` is missing, or the service isn't running as `vpn-provisioner`. |
| `Unable to modify interface` | `awg-quick@awg1` is down. Start it, and the worker retries on its own. |
| Client gets no handshake | Make sure the client app is 3.1 (AmneziaWG 3.1.x, AmneziaVPN 5.0.2.1+). Check `ENDPOINT_HOST` in `vpnctl.conf` and that ufw allows the port. |
| `SSH connection failed to <server>` | Run the `ssh` test from [More servers](NATIVE_SETUP.md#more-servers) as `vpn-provisioner` on the bot host. Check the Tailscale IP and `authorized_keys`. |
| `vpnctl-ssh: command not allowed` | The bot sent a command the VPN host's `vpnctl-ssh` doesn't know. Update both to the same version. |
| `database is locked` | Something else is holding the SQLite file, such as an open `sqlite3` shell. Close it. |
