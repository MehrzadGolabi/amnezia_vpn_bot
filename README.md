# Production AmneziaWG Telegram Sales & Subscription Bot

A high-performance, asynchronous Telegram bot for automated sales, manual receipt verification, and zero-root provisioning of obfuscated **AmneziaWG** (anti-censorship WireGuard) VPN subscriptions.

---

## 🌟 Key Features

- **🧬 Native AmneziaWG 3.1**: Manages clients on an `amneziawg-go` + `awg-quick` server (no Docker container), with every 3.1 obfuscation value copied into client configs.
- **🛡️ Secure Zero-Root Provisioning**:
  - Outbox worker communicates with VPN nodes via SSH running as non-root `vpn-provisioner`.
  - Node sudo privileges restricted strictly to `/usr/local/sbin/vpnctl`.
  - Obfuscated AmneziaWG `.conf` files delivered in-memory; private keys never stored plaintext in database.
- **⚡ Transactional Outbox Pattern**:
  - Zero dropped jobs, automatic exponential backoff retries, and row-level locking.
- **🌐 Bilingual UI**: Full English (`EN`) and Persian (`FA`) localization for Iranian anti-censorship users.
- **🧾 Administrator Verification**: Real-time receipt forwarding to admin channel with one-click interactive approval/rejection.
- **⏱️ Automated Expiry & Grace Period**:
  - Scheduled renewal reminders at 7-day, 3-day, and 1-day intervals.
  - Automatic peer disabling upon expiration and cleanup after grace period.
- **💬 Customer Support Bridge**: Threaded customer ticketing with bidirectional admin replies.
- **🐳 Production Ready**: Multi-stage `Dockerfile`, healthchecks, Alembic migrations, and `docker-compose.yml`.

---

## 🚀 Quick Start

### 1. Configure `.env`
```bash
cp .env.example .env
# Edit .env and supply BOT_TOKEN, ADMIN_CHAT_ID, and ADMIN_TELEGRAM_IDS
```

Not using Docker? Follow [Running the bot without Docker](docs/NATIVE_SETUP.md) instead.

### 2. Launch with Docker Compose
```bash
docker compose up -d --build
```

### 3. Verify System Health
```bash
docker compose ps
docker compose logs -f bot worker scheduler
```

---

## 🧪 Testing

Run test suite with code coverage:
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
make test
```

The tests run `vpnctl` and the worker against a sandboxed AmneziaWG 3.1 server (`scripts/dev/sandbox.sh` with a fake `awg`), so no VPS is needed. To click through the bot itself against that sandbox, see [Testing without a VPS](docs/AMNEZIAWG_INTEGRATION.md#4-testing-without-a-vps).

---

## 📚 Documentation Reference

- 📐 [Architecture Reference](docs/ARCHITECTURE.md)
- 🛠️ [Operations & Runbook](docs/OPERATIONS.md)
- 🔒 [Security & Threat Model](docs/SECURITY.md)
- 🌐 [AmneziaWG Integration Guide](docs/AMNEZIAWG_INTEGRATION.md)
