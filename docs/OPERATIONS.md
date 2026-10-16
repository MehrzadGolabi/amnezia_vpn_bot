# Operations

## Admin commands

Send these to the bot from an account listed in `ADMIN_TELEGRAM_IDS`.

| Command | What it does |
|---|---|
| `/admin` | Shows pending receipts and open tickets. |
| `/servers` | Shows each server's active subscriptions, and lets you turn a server on or off for new orders. |
| `/products` | Lists the plans. |
| `/user <telegram_id>` | Shows a customer and how many subscriptions they have. |
| `/block <telegram_id>`, `/unblock <telegram_id>` | Suspends or restores a customer. |

Receipts arrive in `ADMIN_CHAT_ID` with Approve and Reject buttons. Approving queues a job, and the worker creates the client and sends the config.

Turning a server off in `/servers` lasts until the bot restarts. On startup the bot reloads servers from `.env`, so use `VPN_SERVER_<NAME>_ENABLED=false` to turn one off permanently.

## Subscription lifecycle

1. The admin approves the order, and the worker creates the client and sends the `.conf` file and a `vpn://` key.
2. Reminders go out `REMINDER_DAYS_BEFORE_EXPIRY` days before expiry.
3. At expiry, the scheduler queues a disable job. The client is removed from `awg1.conf` and the interface, but its files are kept.
4. After `PEER_REMOVAL_GRACE_DAYS`, the client is deleted.

Renewing is a new order with a new config. It does not extend the old one.

## Logs

Without Docker:

```bash
journalctl -u vpnbot-bot -u vpnbot-worker -u vpnbot-scheduler -f
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
sudo systemctl restart vpnbot-bot vpnbot-worker vpnbot-scheduler
```

On each extra VPN host, update `vpnctl` the same way: `git pull` in `/opt/amnezia_vpn_bot`, then the `install` line.

With Docker, run `git pull`, then `docker compose up -d --build`. Copy the new `vpnctl` to each VPN host as well.

## Troubleshooting

| Symptom | Check |
|---|---|
| Order approved but no config arrives | Worker log. A `vpnctl` error there names the cause. Run the same `vpnctl` command by hand as `vpn-provisioner`. |
| `sudo: a password is required` | `/etc/sudoers.d/vpn-provisioner` is missing, or the service isn't running as `vpn-provisioner`. |
| `Unable to modify interface` | `awg-quick@awg1` is down. Start it, and the worker retries on its own. |
| Client gets no handshake | Make sure the client app is 3.1 (AmneziaWG 3.1.x, AmneziaVPN 5.0.2.1+). Check `ENDPOINT_HOST` in `vpnctl.conf` and that ufw allows the port. |
| `SSH connection failed to <server>` | Run the `ssh` test from [More servers](NATIVE_SETUP.md#more-servers) as `vpn-provisioner` on the bot host. Check the Tailscale IP and `authorized_keys`. |
| `database is locked` | Something else is holding the SQLite file, such as an open `sqlite3` shell. Close it. |
