# Environment Configuration Guide (`.env`)

This guide provides a comprehensive reference for configuring all environment variables required to run the **AmneziaWG Telegram Sales & Subscription Bot** in development and production environments.

---

## 1. Quick Example (`.env`)

```ini
# --- General Application Settings ---
APP_ENV=production
LOG_LEVEL=INFO

# --- Telegram Bot & Administration ---
TELEGRAM_BOT_TOKEN=123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ1234567
ADMIN_TELEGRAM_IDS=71905073,12345678
ADMIN_CHAT_ID=71905073

# --- Database (PostgreSQL) ---
POSTGRES_USER=vpn_bot
POSTGRES_PASSWORD=my_strong_db_password_123!
POSTGRES_DB=vpn_bot
DATABASE_URL=postgresql+asyncpg://vpn_bot:my_strong_db_password_123!@postgres:5432/vpn_bot

# --- Provisioning Engine & Operations ---
PROVISIONER_MODE=mock
PROVISIONING_JOB_POLL_SECONDS=5
EXPIRY_CHECK_INTERVAL_SECONDS=300
REMINDER_DAYS_BEFORE_EXPIRY=7,3,1
CONFIG_REDELIVERY_LIMIT=3
PEER_REMOVAL_GRACE_DAYS=30

# --- Payment Instructions ---
PAYMENT_INSTRUCTIONS_EN=Please transfer payment to Card 1234-5678-9012-3456 (John Doe) and upload your receipt photo or document.
PAYMENT_INSTRUCTIONS_FA=لطفا مبلغ را به کارت ۶۰۳۷۹۹۱۸۰۰۰۰۰۰۰۰ بنام دارنده حساب واریز نموده و رسید را ارسال فرمایید.

# --- VPN Server Node: Germany (de-1) ---
VPN_SERVER_DE_1_ENABLED=true
VPN_SERVER_DE_1_SLUG=de-1
VPN_SERVER_DE_1_COUNTRY_CODE=DE
VPN_SERVER_DE_1_DISPLAY_NAME=Germany Frankfurt
VPN_SERVER_DE_1_HOST=de1.yourdomain.com
VPN_SERVER_DE_1_PORT=22
VPN_SERVER_DE_1_USERNAME=vpn-provisioner
VPN_SERVER_DE_1_SSH_PRIVATE_KEY_PATH=/app/secrets/id_ed25519
VPN_SERVER_DE_1_MAX_ACTIVE_SUBSCRIPTIONS=100

# --- VPN Server Node: Turkey (tr-1) ---
VPN_SERVER_TR_1_ENABLED=true
VPN_SERVER_TR_1_SLUG=tr-1
VPN_SERVER_TR_1_COUNTRY_CODE=TR
VPN_SERVER_TR_1_DISPLAY_NAME=Turkey Istanbul
VPN_SERVER_TR_1_HOST=tr1.yourdomain.com
VPN_SERVER_TR_1_PORT=22
VPN_SERVER_TR_1_USERNAME=vpn-provisioner
VPN_SERVER_TR_1_SSH_PRIVATE_KEY_PATH=/app/secrets/id_ed25519
VPN_SERVER_TR_1_MAX_ACTIVE_SUBSCRIPTIONS=100
```

---

## 2. Detailed Variable Dictionary

### 🔹 Section A: Telegram Bot & Admins

| Variable | Required | Default | Description & Instructions |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **Yes** | - | Token issued by `@BotFather` on Telegram when creating the bot. |
| `ADMIN_TELEGRAM_IDS` | **Yes** | - | Comma-separated list of numeric Telegram User IDs allowed to access `/admin`, approve receipts, and manage users. Use `@userinfobot` to find your ID. |
| `ADMIN_CHAT_ID` | **Yes** | - | Numeric Chat or Channel ID where order receipts and support ticket notifications are forwarded. For direct DMs to you, use your user ID. For a group or channel, use `-100...`. |

---

### 🔹 Section B: Database (PostgreSQL)

| Variable | Required | Default | Description & Instructions |
|---|---|---|---|
| `POSTGRES_USER` | **Yes** | `vpn_bot` | Database user created in the PostgreSQL container. |
| `POSTGRES_PASSWORD` | **Yes** | `vpn_bot_secret` | Password for the database user. |
| `POSTGRES_DB` | **Yes** | `vpn_bot` | Name of the PostgreSQL database. |
| `DATABASE_URL` | **Yes** | - | Asyncpg database connection URL: `postgresql+asyncpg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@postgres:5432/<POSTGRES_DB>`. |

---

### 🔹 Section C: Provisioning & Lifecycle Engine

| Variable | Required | Default | Description & Instructions |
|---|---|---|---|
| `PROVISIONER_MODE` | No | `mock` | Set to `mock` for local/offline testing without real VPN servers. Set to `ssh` for live production provisioning over SSH. |
| `PROVISIONING_JOB_POLL_SECONDS` | No | `5` | Polling frequency (seconds) for the background Outbox worker to pick up and process new peer provisioning jobs. |
| `EXPIRY_CHECK_INTERVAL_SECONDS` | No | `300` | Frequency (seconds) for the scheduler daemon to check for expiring subscriptions. |
| `REMINDER_DAYS_BEFORE_EXPIRY` | No | `7,3,1` | Tiered reminder intervals (in days before expiration) when renewal reminders are sent to users. |
| `CONFIG_REDELIVERY_LIMIT` | No | `3` | Maximum number of times a customer can request in-app redelivery of their AmneziaWG configuration file. |
| `PEER_REMOVAL_GRACE_DAYS` | No | `30` | Number of days an expired peer is kept disabled on the server before permanent cleanup. |

---

### 🔹 Section D: Payment Instructions

| Variable | Required | Description |
|---|---|---|
| `PAYMENT_INSTRUCTIONS_EN` | No | Text displayed to English-speaking customers after selecting a plan, explaining card/crypto payment details. |
| `PAYMENT_INSTRUCTIONS_FA` | No | Text displayed to Persian-speaking customers with Iranian bank card / Sheba details. |

---

### 🔹 Section E: Dynamic VPN Server Nodes

You can add **as many VPN servers as you want** simply by adding variables prefixed with `VPN_SERVER_<SLUG_NAME>_`.

For every server node, configure:
- `VPN_SERVER_<NAME>_ENABLED`: `true` or `false` to make it available for new sales.
- `VPN_SERVER_<NAME>_SLUG`: Short unique identifier (e.g. `de-1`, `nl-1`, `tr-1`).
- `VPN_SERVER_<NAME>_COUNTRY_CODE`: ISO 2-letter country code (`DE`, `NL`, `TR`, `US`, etc.).
- `VPN_SERVER_<NAME>_DISPLAY_NAME`: Human-readable label displayed on buttons (e.g. `Germany Frankfurt`).
- `VPN_SERVER_<NAME>_HOST`: Domain or public IP of the VPS host.
- `VPN_SERVER_<NAME>_PORT`: SSH port on the remote host (default: `22`).
- `VPN_SERVER_<NAME>_USERNAME`: Dedicated SSH provisioner user on the host (`vpn-provisioner`).
- `VPN_SERVER_<NAME>_SSH_PRIVATE_KEY_PATH`: Absolute path to the private SSH key file on the bot host.
- `VPN_SERVER_<NAME>_MAX_ACTIVE_SUBSCRIPTIONS`: Maximum peer capacity limit (e.g. `100`).
