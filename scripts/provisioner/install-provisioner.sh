#!/usr/bin/env bash
# Installs vpnctl and the systemd sockets the bot talks to it through.
#
#   install-provisioner.sh                      on the host the bot runs on: the bot
#                                               connects to /run/vpnctl/vpnctl.sock
#   install-provisioner.sh --tailnet <bot IP>   on every other VPN host: vpnctl listens
#                                               on this host's Tailscale address and
#                                               answers only <bot IP>, the bot host's
#                                               Tailscale address
#   ... --port <n>                              the Tailscale port (default 7391)
#   ... --remove-ssh                            after the bot is updated: remove the old
#                                               SSH and sudo setup (see docs/OPERATIONS.md)
#
# Running it again is safe. It keeps /etc/amnezia/vpnctl.conf.
set -euo pipefail

TAILNET_BOT_IP=""
PORT=7391
REMOVE_SSH=0
while [ $# -gt 0 ]; do
    case "$1" in
        --tailnet) TAILNET_BOT_IP="${2:?--tailnet needs the Tailscale IP of the bot host}"; shift 2 ;;
        --port) PORT="${2:?--port needs a number}"; shift 2 ;;
        --remove-ssh) REMOVE_SSH=1; shift ;;
        *) echo "Unknown option: $1"; exit 2 ;;
    esac
done

echo "==> Installing vpnctl"

# Root installs these files as root programs and systemd units. If anyone but root
# can change them, or the folders above them, a break-in to the bot becomes root here.
SRC_DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO_DIR="$(cd "$SRC_DIR/../.." && pwd -P)"
check_root_only() {
    local owner mode
    owner=$(stat -c %u "$1")
    mode=$(stat -c %a "$1")
    if [ "$owner" != 0 ] || (( 8#$mode & 8#022 )); then
        echo "Refusing to install: $1 is owned by uid $owner with mode $mode."
        echo "It must be owned by root and not writable by group or others. Fix it with:"
        echo "    chown -R root:root $REPO_DIR && chmod -R go-w $REPO_DIR"
        echo "then give vpn-provisioner its data folder back (see docs/OPERATIONS.md#updating)."
        echo "A clone inside a user's home folder can't pass this check; clone to /opt/amnezia_vpn_bot as root."
        exit 1
    fi
}
dir="$SRC_DIR"
while :; do
    check_root_only "$dir"
    [ "$dir" = / ] && break
    dir="$(dirname "$dir")"
done
for f in "$SRC_DIR"/* "$SRC_DIR"/systemd/*; do
    check_root_only "$f"
done

command -v python3 >/dev/null || { echo "python3 is required for vpnctl"; exit 1; }
command -v awg >/dev/null || echo "WARNING: awg not found. Install amneziawg-tools 3.1 first (see the migration guide)."
if [ -n "$TAILNET_BOT_IP" ]; then
    python3 -c 'import ipaddress, sys; ipaddress.ip_address(sys.argv[1])' "$TAILNET_BOT_IP" 2>/dev/null \
        || { echo "--tailnet needs an IP address, got: $TAILNET_BOT_IP"; exit 2; }
    command -v tailscale >/dev/null || { echo "tailscale is required for --tailnet"; exit 1; }
    LISTEN_IP="$(tailscale ip -4 | head -n1)"
    [ -n "$LISTEN_IP" ] || { echo "This host has no Tailscale IPv4 address. Run 'tailscale up' first."; exit 1; }
fi

# 1. vpnctl and its settings (settings are kept if they already exist)
install -m 755 -o root -g root "$SRC_DIR/vpnctl" /usr/local/sbin/vpnctl
echo "Installed /usr/local/sbin/vpnctl"
if [ ! -f /etc/amnezia/vpnctl.conf ]; then
    install -D -m 600 -o root -g root "$SRC_DIR/vpnctl.conf.example" /etc/amnezia/vpnctl.conf
    echo "Installed /etc/amnezia/vpnctl.conf - check INTERFACE and ENDPOINT_HOST"
fi
set_conf() {
    if grep -q "^$1=" /etc/amnezia/vpnctl.conf; then
        sed -i "s|^$1=.*|$1=$2|" /etc/amnezia/vpnctl.conf
    else
        printf '%s=%s\n' "$1" "$2" >> /etc/amnezia/vpnctl.conf
    fi
}

UNITS=/etc/systemd/system
install_service() {    # the sandboxed per-request unit, under the name its socket expects
    install -m 644 -o root -g root "$SRC_DIR/systemd/vpnctl@.service" "$UNITS/$1@.service"
    # The sandbox may write only the AmneziaWG folder; follow CONF_DIR if it was changed.
    conf_dir="$(sed -n 's/^CONF_DIR=//p' /etc/amnezia/vpnctl.conf | tail -n1)"
    rm -rf "$UNITS/$1@.service.d"
    if [ -n "$conf_dir" ] && [ "$conf_dir" != /etc/amnezia/amneziawg ]; then
        mkdir -p "$UNITS/$1@.service.d"
        printf '[Service]\nReadWritePaths=%s\n' "$conf_dir" > "$UNITS/$1@.service.d/conf-dir.conf"
    fi
}

if [ -z "$TAILNET_BOT_IP" ]; then
    # 2a. The bot runs here as vpn-provisioner and connects to the Unix socket.
    if ! id vpn-provisioner &>/dev/null; then
        useradd -r -s /usr/sbin/nologin -M -d /nonexistent vpn-provisioner
        echo "Created user vpn-provisioner"
    fi
    install_service vpnctl
    install -m 644 -o root -g root "$SRC_DIR/systemd/vpnctl.socket" "$UNITS/vpnctl.socket"
    systemctl daemon-reload
    systemctl enable --now vpnctl.socket
    systemctl restart vpnctl.socket
    echo "Listening on /run/vpnctl/vpnctl.sock for the vpn-provisioner group"
else
    # 2b. The bot runs elsewhere and connects over Tailscale.
    set_conf ALLOWED_CLIENTS "$TAILNET_BOT_IP"
    install_service vpnctl-tailnet
    sed -e "s|@LISTEN@|$LISTEN_IP:$PORT|" -e "s|@BOT_IP@|$TAILNET_BOT_IP|" \
        "$SRC_DIR/systemd/vpnctl-tailnet.socket.in" > "$UNITS/vpnctl-tailnet.socket"
    chmod 644 "$UNITS/vpnctl-tailnet.socket"
    systemctl daemon-reload
    systemctl enable --now vpnctl-tailnet.socket
    systemctl restart vpnctl-tailnet.socket
    echo "Listening on $LISTEN_IP:$PORT for $TAILNET_BOT_IP only"
fi

# 3. The SSH and sudo setup of older versions. Only on request, after the bot is updated,
#    because the old bot needs it until then.
if [ "$REMOVE_SSH" = 1 ]; then
    rm -f /etc/sudoers.d/vpn-provisioner /usr/local/sbin/vpnctl-ssh
    if [ -f /etc/ssh/sshd_config.d/vpn-provisioner.conf ]; then
        rm -f /etc/ssh/sshd_config.d/vpn-provisioner.conf
        systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
    fi
    if id vpn-provisioner &>/dev/null; then
        home="$(getent passwd vpn-provisioner | cut -d: -f6)"
        # The bot's key for other hosts, and other hosts' copies of it.
        rm -f "$home/.ssh/authorized_keys" "$home/.ssh/id_ed25519" "$home/.ssh/id_ed25519.pub"
        usermod -s /usr/sbin/nologin vpn-provisioner
        if [ -n "$TAILNET_BOT_IP" ]; then
            usermod -L vpn-provisioner    # no bot on this host, so nothing runs as it
        fi
    fi
    echo "Removed the SSH and sudo setup for vpn-provisioner"
fi

install -m 755 -o root -g root "$SRC_DIR/vpnctl-check" /usr/local/bin/vpnctl-check
echo "==> Done. Check it with:"
if [ -z "$TAILNET_BOT_IP" ]; then
    echo "    sudo -u vpn-provisioner vpnctl-check"
else
    echo "    on the bot host: sudo -u vpn-provisioner vpnctl-check $LISTEN_IP $PORT"
fi
