# Operations & Maintenance Guide

## 1. Remote VPN Host Setup

To prepare a new Linux VPS host for AmneziaWG provisioning:

### Step 1: Install `vpnctl`
Copy `scripts/provisioner/vpnctl` to `/usr/local/sbin/vpnctl` on the host:
```bash
sudo cp scripts/provisioner/vpnctl /usr/local/sbin/vpnctl
sudo chmod 755 /usr/local/sbin/vpnctl
```

### Step 2: Configure Server Interface Defaults
Create `/etc/amnezia/vpnctl.conf`:
```ini
INTERFACE=awg0
SERVER_HOST=203.0.113.10
SERVER_PORT=51820
SERVER_PUBKEY=YOUR_SERVER_PUBLIC_KEY
SUBNET_PREFIX=10.8.0
DNS_SERVERS=1.1.1.1,8.8.8.8
JC=4
JMIN=40
JMAX=70
S1=15
S2=30
H1=1
H2=2
H3=3
H4=4
```

### Step 3: Create Dedicated Provisioner User & Sudoers Entry
Execute the automated installer script:
```bash
sudo ./scripts/provisioner/install-provisioner.sh
```
Or configure manually:
```bash
sudo useradd -r -m -s /bin/bash vpn-provisioner
sudo cp scripts/provisioner/sudoers.example /etc/sudoers.d/vpn-provisioner
sudo chmod 440 /etc/sudoers.d/vpn-provisioner
```

Install the bot's public SSH key in `/home/vpn-provisioner/.ssh/authorized_keys`.

---

## 2. Deployment with Docker Compose

### Prerequisites
- Docker Engine 24+ & Docker Compose v2+
- Valid Telegram Bot Token from `@BotFather`
- Dedicated Admin Chat / Telegram Channel ID

### Step 1: Configure Environment
Copy `.env.example` to `.env` and fill in secrets:
```bash
cp .env.example .env
nano .env
```

### Step 2: Launch Stack
```bash
docker compose up -d --build
```

### Step 3: Verify Status & Logs
```bash
docker compose ps
docker compose logs -f bot worker scheduler
```

---

## 3. Database Migrations & Backups

### Run Migrations Manually
```bash
docker compose run --rm migration alembic upgrade head
```

### Database Backup
```bash
docker compose exec -t postgres pg_dump -U vpn_user vpn_bot | gzip > backup_$(date +%F_%T).sql.gz
```

### Database Restore
```bash
gunzip < backup_2026-08-24_12:00:00.sql.gz | docker compose exec -T postgres psql -U vpn_user -d vpn_bot
```

---

## 4. Peer Reconciliation & Health Checks

### Check System Health
Run within container:
```bash
python -c "import asyncio; from src.app.db.session import async_session_maker; from src.app.utils.health import check_system_health; print(asyncio.run(check_system_health(async_session_maker())))"
```

### Run Non-Destructive Reconciliation Report
```bash
python -m src.app.utils.reconciliation --server nl-1
```
