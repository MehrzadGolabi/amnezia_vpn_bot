# Production AmneziaWG Telegram Sales & Subscription Bot

A high-performance, asynchronous Telegram bot for automated sales, manual receipt verification, and zero-root provisioning of obfuscated **AmneziaWG** (anti-censorship WireGuard) VPN subscriptions.

---

## 🌟 Key Features

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
PYTHONPATH=. .venv/bin/pytest tests/unit/ -v --cov=src/app
```

---

## 📚 Documentation Reference

- 📐 [Architecture Reference](docs/ARCHITECTURE.md)
- 🛠️ [Operations & Runbook](docs/OPERATIONS.md)
- 🔒 [Security & Threat Model](docs/SECURITY.md)
- 🌐 [AmneziaWG Integration Guide](docs/AMNEZIAWG_INTEGRATION.md)
