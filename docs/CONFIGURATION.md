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
| `PROVISIONER_MODE` | `mock` | `vpnctl` manages real servers: through `VPNCTL_SOCKET` for servers without a `HOST`, and over Tailscale for servers with one. `mock` makes fake configs, for trying the bot without a server. The old values `local` and `ssh` mean `vpnctl`. |
| `VPNCTL_SOCKET` | `/run/vpnctl/vpnctl.sock` | Where `vpnctl` on this host listens. |
| `VPNCTL_DEV_COMMAND` | | Development only: run this command with `serve` instead of using the socket, for the test sandbox (see [vpnctl](VPNCTL.md#testing-without-a-vps)). |
| `VPNCTL_TOKEN` | | Sent to `vpnctl` on other VPN hosts, which keep its SHA-256 as `CLIENT_TOKEN_SHA256`. Not sent over the local socket. See [More servers](NATIVE_SETUP.md#more-servers). |
| `VPNCTL_GID` | | Docker only: the `vpn-provisioner` group's ID on the host, so the containers can use the socket. |
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
| `VPN_SERVER_<NAME>_HOST` | `localhost` | Leave it out for the server the bot runs on. For another VPN host, its Tailscale IP. |
| `VPN_SERVER_<NAME>_VPNCTL_PORT` | `7391` | The port `vpnctl` listens on at that Tailscale IP (`install-provisioner.sh --port`). |

`PORT`, `USERNAME`, `SSH_PRIVATE_KEY_PATH` and `SSH_KNOWN_HOSTS_PATH` are left over from SSH. They are ignored, and the log warns about them at startup, so you can delete them.

The server-side settings (endpoint, DNS, MTU) are in `/etc/amnezia/vpnctl.conf` on the VPN host. See [vpnctl](VPNCTL.md).

## Other

| Setting | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | Label only. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
