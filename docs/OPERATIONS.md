# Operations

## Admin commands

Send these to the bot from an account listed in `ADMIN_TELEGRAM_IDS`.

| Command | What it does |
|---|---|
| `/admin` | Shows pending receipts and open tickets. |
| `/servers` | Shows each server's state and active subscriptions, and pauses or resumes a server for new orders. |
| `/products` | Lists the plans. |
| `/user <telegram_id>` | Shows a customer and their subscriptions, with data used and last connection. |
| `/extend <config name> <days>` | Adds days to a subscription and turns it back on if it had expired. A negative number takes days off. |
| `/block <telegram_id>`, `/unblock <telegram_id>` | Suspends or restores a customer. |
| `/retry` | Lists jobs that failed for good, with their last error, and queues one or all of them again. |
| `/audit` | The latest 20 admin and system actions: approvals, rejections, blocks, pauses, extensions, retries, and peers created, disabled or removed. |

Receipts arrive in `ADMIN_CHAT_ID` with Approve and Reject buttons. Approving queues a job, and the worker creates the client and sends the config.

A server is on sale when `VPN_SERVER_<NAME>_ENABLED` is `true`, it isn't paused in `/servers`, and it is below `MAX_ACTIVE_SUBSCRIPTIONS`. A pause stays after a restart. A server turned off in `.env` can only be turned on there. None of this stops renewals of existing subscriptions.

When a job fails for good, the alert in the admin chat has a Retry button. `/retry` does the same for every failed job. It won't queue a job again when that could do harm: a create job whose subscription is no longer waiting for a peer, an enable job for a subscription that has run out, or a job that is already queued.

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
sudo git pull
sudo .venv/bin/pip install .
sudo ./scripts/provisioner/install-provisioner.sh
sudo systemctl restart vpnbot
```

Older versions of the setup guide made `vpn-provisioner` the owner of the whole folder. If `ls -ld /opt/amnezia_vpn_bot` shows `vpn-provisioner`, the installer will refuse to run. Fix it once before updating.

Before running any `git` command as root, check that the service user didn't plant something that git would run: `cat .git/config` should show only the `core`, `remote "origin"` and `branch` sections, with no `hooksPath`, `fsmonitor` or other command, and `ls .git/hooks` should list only `*.sample` files. Then:

```bash
cd /opt/amnezia_vpn_bot
sudo chown -R root:root .
sudo chmod -R go-w .
sudo chown -R vpn-provisioner:vpn-provisioner data
sudo chown root:vpn-provisioner .env
sudo chmod 640 .env
sudo git status        # should show no changed files
```

If the server still has the older three services (`vpnbot-bot`, `vpnbot-worker`, `vpnbot-scheduler`), replace them with the single `vpnbot` service once:

```bash
sudo systemctl disable --now vpnbot-bot vpnbot-worker vpnbot-scheduler
sudo rm /etc/systemd/system/vpnbot-bot.service /etc/systemd/system/vpnbot-worker.service /etc/systemd/system/vpnbot-scheduler.service
sudo cp deploy/systemd/vpnbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vpnbot
```

On each extra VPN host, run `sudo git pull` in `/opt/amnezia_vpn_bot`, then the installer with `--tailnet <bot host tailscale IP>`. The token hash is kept, so `--token-sha256` is only needed when it changes. It updates `vpnctl` and the systemd units and keeps `vpnctl.conf`.

With Docker, run `git pull`, then `docker compose up -d --build`. On each VPN host, update the root-owned clone and run the installer as above. A clone in a user's home folder must be moved to `/opt/amnezia_vpn_bot` (`sudo git clone`), because the installer refuses to run from a folder that user can change.

### Moving from SSH and sudo to vpnctl sockets

Older versions ran `vpnctl` through sudo, and reached other VPN hosts over SSH. Switch over in this order, so provisioning keeps working at every step. The installer only adds things until step 4.

1. **Bot host, token only:** create the bot's token as in [More servers](NATIVE_SETUP.md#more-servers) and note its hash. The running bot ignores it until step 3.

2. **Each extra VPN host:** update the clone, then start the Tailscale listener. The old SSH access keeps working meanwhile. Add `tag:vpn:7391` for `tag:bot` to the Tailscale policy, next to the old `tag:vpn:22` (see [Security](ARCHITECTURE.md#how-the-bot-reaches-vpnctl)).

   ```bash
   cd /opt/amnezia_vpn_bot && sudo git pull
   sudo ./scripts/provisioner/install-provisioner.sh --tailnet <bot host tailscale IP> --token-sha256 <hash>
   ```

3. **Bot host:** update, install the socket and the new service file, and check every server the way the new bot will reach it, before switching the bot over:

   ```bash
   cd /opt/amnezia_vpn_bot
   sudo git pull
   sudo .venv/bin/pip install .
   sudo ./scripts/provisioner/install-provisioner.sh
   sudo cp deploy/systemd/vpnbot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo -u vpn-provisioner vpnctl-check                     # this host
   sudo -u vpn-provisioner vpnctl-check <tailscale IP>      # each extra host
   ```

   In `.env`, set `PROVISIONER_MODE=vpnctl`, delete `VPNCTL_COMMAND`, and delete every server's `PORT`, `USERNAME`, `SSH_PRIVATE_KEY_PATH` and `SSH_KNOWN_HOSTS_PATH`. Keep `HOST` (the Tailscale IP). If you used a port other than 7391, set `VPN_SERVER_<NAME>_VPNCTL_PORT`. Then `sudo systemctl restart vpnbot`. The log names any old setting it still finds (`ignored_setting`). Approve a test order, or open a subscription's page, to see each server answer.

   With Docker, also delete `HOST=host.docker.internal` from the Docker host's own server group, which would now mean a TCP connection nothing answers, and set `VPNCTL_GID`. Then `docker compose up -d --build`.

4. **Clean up**, on the bot host and then every extra host. This deletes the sudoers rule, `vpnctl-ssh`, the sshd drop-in, the bot's SSH key and `authorized_keys`, and turns off logins for `vpn-provisioner`:

   ```bash
   sudo ./scripts/provisioner/install-provisioner.sh --remove-ssh                       # bot host
   sudo ./scripts/provisioner/install-provisioner.sh --tailnet <bot IP> --remove-ssh    # extra hosts
   ```

   Then remove `tag:vpn:22` for `tag:bot` from the Tailscale policy.

## Changing the bot's token

Every VPN host accepts a list of token hashes, so the token can be changed without a moment where the bot is refused. Every host must already run a `vpnctl` that understands the list, so update and re-run the installer on all of them first.

1. On the bot host, make a new token and its hash, but don't put it in `.env` yet:

   ```bash
   NEW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))'); echo "$NEW"; printf '%s' "$NEW" | sha256sum | cut -d' ' -f1
   ```

2. On each extra VPN host, accept both the old and the new token:

   ```bash
   sudo /opt/amnezia_vpn_bot/scripts/provisioner/install-provisioner.sh --tailnet <bot host tailscale IP> --token-sha256 <old hash>,<new hash>
   ```

3. On the bot host, replace `VPNCTL_TOKEN` in `.env` with the new token (keep a single line), restart `vpnbot`, and check every host with `sudo -u vpn-provisioner vpnctl-check <tailscale IP>`.
4. On each extra VPN host, run the installer again with only `--token-sha256 <new hash>`.

## Checking the caller's Tailscale tag (optional)

On top of the address and the token, `vpnctl` can ask Tailscale whether the caller's machine carries a tag. It is off by default and hasn't been tried on a real host yet, so test it on one host first.

1. On the VPN host, check that whois shows the bot host's tag: `tailscale whois --json <bot host tailscale IP>` should print a `"Tags"` list containing `tag:bot`.
2. Add `REQUIRED_TAILSCALE_TAGS=tag:bot` to `/etc/amnezia/vpnctl.conf`.
3. From the bot host, `sudo -u vpn-provisioner vpnctl-check <tailscale IP>` should still answer, and `journalctl -u 'vpnctl-tailnet@*' -b --no-pager -p warning` should show nothing.

A caller without the tag is refused for good. If whois itself fails, for example while tailscaled restarts, the request is refused as retryable and the worker tries again. If it keeps failing inside `vpnctl`'s sandbox, delete the setting and tell me what the journal says.

## Troubleshooting

| Symptom | Check |
|---|---|
| Order approved but no config arrives | Worker log. A `vpnctl` error there names the cause. `sudo -u vpn-provisioner vpnctl-check [<tailscale IP>]` tests the same path the bot uses, and `journalctl -u 'vpnctl@*' -u 'vpnctl-tailnet@*'` on the VPN host shows `vpnctl`'s side. |
| `Cannot reach vpnctl on <server>` | On this host: is `vpnctl.socket` running (`systemctl status vpnctl.socket`), and is the bot running as `vpn-provisioner`? On another host: is `vpnctl-tailnet.socket` running there, is Tailscale up on both, and does the Tailscale policy allow `tag:bot` to `tag:vpn:7391`? |
| `Wrong or missing token` or `CLIENT_TOKEN_SHA256 is not set` | `VPNCTL_TOKEN` in the bot's `.env` doesn't match the hash on that VPN host. Print the hash on the bot host (`grep '^VPNCTL_TOKEN=' .env \| cut -d= -f2- \| tr -d '\\n' \| sha256sum`) and run the installer there again with `--token-sha256 <hash>`. |
| `<IP> is not in ALLOWED_CLIENTS` | The VPN host doesn't know the bot host's Tailscale IP. Run the installer there again with `--tailnet <bot host tailscale IP>`. |
| `Unable to modify interface` | `awg-quick@awg1` is down. Start it, and the worker retries on its own. |
| Client gets no handshake | Make sure the client app is 3.1 (AmneziaWG 3.1.x, AmneziaVPN 5.0.2.1+). Check `ENDPOINT_HOST` in `vpnctl.conf` and that ufw allows the port. |
| Jobs failed for good while a server was unreachable | Once it answers `vpnctl-check` again, press Retry on the alert, or use `/retry`. Paid orders then get their configs. |
| `Refusing to install: ... is owned by uid ...` | The folder must be owned by root. See [Updating](#updating). |
| `database is locked` | Something else is holding the SQLite file, such as an open `sqlite3` shell. Close it. |
