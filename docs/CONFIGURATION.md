# Configuration

All settings live in `.env` in the repository root. Start from `.env.example`.

## Telegram

| Setting | Default | Meaning |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | | Token from @BotFather. |
| `ADMIN_TELEGRAM_IDS` | | Comma-separated Telegram user IDs that can use admin commands. Get yours from @userinfobot. |
| `ADMIN_CHAT_ID` | | Where receipts, tickets and alerts go. Use your user ID, or a group/channel ID (`-100...`). This ID also counts as an admin. |

## Database

| Setting | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | Postgres in Docker | Without Docker: `sqlite+aiosqlite:////opt/amnezia_vpn_bot/data/bot.db`. With Docker: `postgresql+asyncpg://USER:PASSWORD@postgres:5432/DB`. |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `vpn_bot`, `vpn_bot_secret`, `vpn_bot` | Docker only. Used to create the Postgres container. They must match `DATABASE_URL`. |

## Provisioning

| Setting | Default | Meaning |
|---|---|---|
| `PROVISIONER_MODE` | `mock` | `local` runs `vpnctl` on this machine for servers without a `HOST`, and over SSH for servers with one (no Docker). `ssh` runs it on every server over SSH (Docker). `mock` makes fake configs, for trying the bot without a server. |
| `VPNCTL_COMMAND` | `sudo -n /usr/local/sbin/vpnctl` | How `vpnctl` is called. Change it only for the test sandbox. |
| `PROVISIONING_JOB_POLL_SECONDS` | `5` | How often the worker checks for new jobs. |

## Subscriptions

| Setting | Default | Meaning |
|---|---|---|
| `EXPIRY_CHECK_INTERVAL_SECONDS` | `300` | How often the scheduler checks for expiring subscriptions. |
| `REMINDER_DAYS_BEFORE_EXPIRY` | `7,3,1` | Days before expiry to remind customers. |
| `PEER_REMOVAL_GRACE_DAYS` | `30` | Days an expired client stays disabled before it is deleted from the server. |
| `CONFIG_REDELIVERY_LIMIT` | `3` | How many times a customer can ask for their config again. |
| `PAYMENT_INSTRUCTIONS_EN`, `PAYMENT_INSTRUCTIONS_FA` | placeholder | Payment details shown after a customer picks a plan. |

## Servers

Each location customers can buy is a group of `VPN_SERVER_<NAME>_*` settings. `<NAME>` is any label, such as `MAIN_1` or `DE_1`. Add as many groups as you need. A server needs at least `COUNTRY_CODE` and `DISPLAY_NAME`.

| Setting | Default | Meaning |
|---|---|---|
| `VPN_SERVER_<NAME>_SLUG` | from `<NAME>` | Short unique ID, such as `main-1`. It becomes part of client names. |
| `VPN_SERVER_<NAME>_DISPLAY_NAME` | | Shown on buttons, such as `Germany`. |
| `VPN_SERVER_<NAME>_COUNTRY_CODE` | | Two-letter code, such as `DE`. |
| `VPN_SERVER_<NAME>_ENABLED` | `true` | `false` hides it from new orders. |
| `VPN_SERVER_<NAME>_MAX_ACTIVE_SUBSCRIPTIONS` | none | Capacity shown in `/servers`. It is displayed only and does not stop sales. |
| `VPN_SERVER_<NAME>_HOST` | `localhost` | SSH host. In `local` mode, leave it out (or `localhost`) for the bot's own server. |
| `VPN_SERVER_<NAME>_PORT` | `22` | SSH port. |
| `VPN_SERVER_<NAME>_USERNAME` | `vpn-provisioner` | SSH user. |
| `VPN_SERVER_<NAME>_SSH_PRIVATE_KEY_PATH` | | SSH key, for example `/app/secrets/id_ed25519` in Docker. |
| `VPN_SERVER_<NAME>_SSH_KNOWN_HOSTS_PATH` | | If set, the host key is checked against this file, for example `/home/vpn-provisioner/.ssh/known_hosts`. If not, any host key is accepted. |

The server-side settings (endpoint, DNS, MTU) are in `/etc/amnezia/vpnctl.conf` on the VPN host. See [vpnctl](VPNCTL.md).

## Other

| Setting | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | Label only. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
