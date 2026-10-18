# Running the bot with Docker

The bot, worker, scheduler and Postgres run in containers. They ask `vpnctl` on the Docker host through its Unix socket, mounted into the containers, and reach other VPN hosts over Tailscale through the Docker host. On a single VPS, [running without Docker](NATIVE_SETUP.md) is simpler.

The Docker setup hasn't been tested since the switch from SSH to sockets. Check each step's output.

## 1. On each VPN host

The AmneziaWG 3.1 server (`awg-quick@awg1`) must already be running.

On the Docker host, if it is a VPN host too:

```bash
sudo git clone https://github.com/MehrzadGolabi/amnezia_vpn_bot /opt/amnezia_vpn_bot
cd /opt/amnezia_vpn_bot
sudo ./scripts/provisioner/install-provisioner.sh
sudo nano /etc/amnezia/vpnctl.conf        # set ENDPOINT_HOST
getent group vpn-provisioner | cut -d: -f3   # put this in VPNCTL_GID in .env
```

On every other VPN host, as in [More servers](NATIVE_SETUP.md#more-servers), with the Docker host's Tailscale IP and the hash of a new `VPNCTL_TOKEN` for `.env`. Containers reach the tailnet through the Docker host, so `vpnctl` sees the Docker host's address:

```bash
sudo ./scripts/provisioner/install-provisioner.sh --tailnet <Docker host tailscale IP> --token-sha256 <hash>
```

Only the worker container gets the socket and the token. The `bot` container, which talks to Telegram, gets neither, so its subscription screens show no data usage.

The installer only runs from a folder that root owns, because it installs these files as root.

## 2. `.env`

```bash
cp .env.example .env
```

Set the Telegram settings, the Postgres password (in both `POSTGRES_PASSWORD` and `DATABASE_URL`), `PROVISIONER_MODE=vpnctl`, `VPNCTL_GID` from step 1, and `VPNCTL_TOKEN` if there are other VPN hosts. Then set up one server group per VPN host. Leave `HOST` out for the Docker host itself, and use the Tailscale IP for the others:

```ini
VPN_SERVER_DE_1_SLUG=de-1
VPN_SERVER_DE_1_COUNTRY_CODE=DE
VPN_SERVER_DE_1_DISPLAY_NAME=Germany

VPN_SERVER_TR_1_SLUG=tr-1
VPN_SERVER_TR_1_COUNTRY_CODE=TR
VPN_SERVER_TR_1_DISPLAY_NAME=Turkey
VPN_SERVER_TR_1_HOST=<tailscale IP>
```

See [Configuration](CONFIGURATION.md) for every setting.

## 3. Start


```bash
docker compose up -d --build
docker compose logs -f bot worker scheduler
```

The `migration` container creates the database tables before the other containers start.
