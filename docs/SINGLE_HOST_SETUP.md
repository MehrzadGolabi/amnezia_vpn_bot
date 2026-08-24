# Single-Host Deployment Guide (Bot + AmneziaWG on Same Machine)

When hosting both the **Telegram Bot** and the **AmneziaWG Server** on the same VPS, the system maintains strict process and privilege separation:
- The bot and database run inside isolated, non-root Docker containers.
- The outbox worker container communicates with the host via local SSH (`host.docker.internal:22`) as a restricted `vpn-provisioner` user.
- The `vpn-provisioner` user has zero root privileges except executing `/usr/local/sbin/vpnctl` via sudoers.

---

## 🛠️ Step-by-Step Single-Host Setup

### Step 1: Install `vpnctl` & Provisioner on the Host

Run this on the host machine:
```bash
# 1. Install vpnctl
sudo cp scripts/provisioner/vpnctl /usr/local/sbin/vpnctl
sudo chmod 755 /usr/local/sbin/vpnctl

# 2. Run the provisioner user installer
sudo ./scripts/provisioner/install-provisioner.sh
```

---

### Step 2: Generate an SSH Keypair for the Bot

Generate a dedicated keypair that the bot container will use to communicate with the host's `vpn-provisioner` user:

```bash
# Create local secrets directory
mkdir -p secrets

# Generate Ed25519 SSH keypair inside secrets/
ssh-keygen -t ed25519 -f secrets/id_ed25519 -N ""

# Add the public key to vpn-provisioner's authorized_keys
cat secrets/id_ed25519.pub | sudo tee -a /home/vpn-provisioner/.ssh/authorized_keys

# Set proper permissions
sudo chown -R vpn-provisioner:vpn-provisioner /home/vpn-provisioner/.ssh
sudo chmod 600 /home/vpn-provisioner/.ssh/authorized_keys
chmod 600 secrets/id_ed25519
```

---

### Step 3: Configure `.env` for Local Host Provisioning

In your `.env` file, point the server definition to `host.docker.internal` and use `/app/secrets/id_ed25519`:

```ini
# --- Core Settings ---
APP_ENV=production
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_FROM_BOTFATHER
ADMIN_TELEGRAM_IDS=YOUR_TELEGRAM_USER_ID
ADMIN_CHAT_ID=YOUR_TELEGRAM_USER_ID

# --- Database ---
POSTGRES_USER=vpn_bot
POSTGRES_PASSWORD=vpn_bot_secret
POSTGRES_DB=vpn_bot
DATABASE_URL=postgresql+asyncpg://vpn_bot:vpn_bot_secret@postgres:5432/vpn_bot

# --- Live SSH Provisioning Mode ---
PROVISIONER_MODE=ssh

# --- Local Amnezia Server on Host ---
VPN_SERVER_LOCAL_1_ENABLED=true
VPN_SERVER_LOCAL_1_SLUG=local-1
VPN_SERVER_LOCAL_1_COUNTRY_CODE=DE
VPN_SERVER_LOCAL_1_DISPLAY_NAME=Main Germany Server
VPN_SERVER_LOCAL_1_HOST=host.docker.internal
VPN_SERVER_LOCAL_1_PORT=22
VPN_SERVER_LOCAL_1_USERNAME=vpn-provisioner
VPN_SERVER_LOCAL_1_SSH_PRIVATE_KEY_PATH=/app/secrets/id_ed25519
VPN_SERVER_LOCAL_1_MAX_ACTIVE_SUBSCRIPTIONS=200
```

---

### Step 4: Launch the Docker Stack

```bash
docker compose up -d --build
```

---

## 🔒 Why Use SSH to `host.docker.internal` instead of Docker Socket / Root Mounts?

1. **Defense in Depth**: If the bot container is ever breached, the attacker only has an SSH key to `vpn-provisioner` (which has no access to host files, root commands, or Docker daemon).
2. **Identical Codebase**: The bot codebase behaves identically whether managing 1 local server or 50 remote nodes across different countries.
