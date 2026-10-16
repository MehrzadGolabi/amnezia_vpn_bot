# Running the bot with Docker

The bot, worker, scheduler and Postgres run in containers. The worker reaches the VPN host over SSH as `vpn-provisioner`, which can only run `vpnctl` through sudo. Use this when the bot runs on a different machine from the VPN server, or when you want the bot isolated in containers. On a single VPS, [running without Docker](NATIVE_SETUP.md) is simpler.

## 1. On each VPN host

The AmneziaWG 3.1 server (`awg-quick@awg1`) must already be running.

```bash
git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot
cd amnezia_vpn_bot
sudo ./scripts/provisioner/install-provisioner.sh
sudo nano /etc/amnezia/vpnctl.conf        # set ENDPOINT_HOST
```

## 2. SSH key for the worker

On the machine running Docker, in the repository:

```bash
mkdir -p secrets
ssh-keygen -t ed25519 -f secrets/id_ed25519 -N ""
chmod 600 secrets/id_ed25519
```

Add `secrets/id_ed25519.pub` to `/home/vpn-provisioner/.ssh/authorized_keys` on each VPN host. Check that the key works:

```bash
ssh -i secrets/id_ed25519 vpn-provisioner@<host> sudo -n /usr/local/sbin/vpnctl peer-status --peer-id test
```

## 3. `.env`

```bash
cp .env.example .env
```

Set the Telegram settings, the Postgres password (in both `POSTGRES_PASSWORD` and `DATABASE_URL`), and `PROVISIONER_MODE=ssh`. Then set up one server group per VPN host. The example group already points at the Docker host:

```ini
VPN_SERVER_DE_1_SLUG=de-1
VPN_SERVER_DE_1_COUNTRY_CODE=DE
VPN_SERVER_DE_1_DISPLAY_NAME=Germany
VPN_SERVER_DE_1_HOST=de1.example.com
VPN_SERVER_DE_1_SSH_PRIVATE_KEY_PATH=/app/secrets/id_ed25519
```

If the bot runs on the VPN host itself, use `HOST=host.docker.internal`. See [Configuration](CONFIGURATION.md) for every setting.

## 4. Start

```bash
docker compose up -d --build
docker compose logs -f bot worker scheduler
```

The `migration` container creates the database tables before the other containers start.
