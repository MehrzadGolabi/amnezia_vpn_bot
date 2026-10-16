#!/usr/bin/env bash
set -euo pipefail

echo "==> Setting up vpn-provisioner service account on AmneziaWG host"

command -v python3 >/dev/null || { echo "python3 is required for vpnctl"; exit 1; }
command -v awg >/dev/null || echo "WARNING: awg not found. Install amneziawg-tools 3.1 first (see the migration guide)."

# 1. Create dedicated system user
if ! id "vpn-provisioner" &>/dev/null; then
    useradd -r -s /bin/bash -m -d /home/vpn-provisioner vpn-provisioner
    echo "Created user vpn-provisioner"
fi

# 2. Setup SSH directory and permissions
SSH_DIR="/home/vpn-provisioner/.ssh"
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"

if [ ! -f "$SSH_DIR/authorized_keys" ]; then
    touch "$SSH_DIR/authorized_keys"
    chmod 600 "$SSH_DIR/authorized_keys"
    echo "Created $SSH_DIR/authorized_keys - please append the bot's public key."
fi
chown -R vpn-provisioner:vpn-provisioner "$SSH_DIR"

# 3. Install vpnctl script
SCRIPT_SRC="$(dirname "$0")/vpnctl"
if [ -f "$SCRIPT_SRC" ]; then
    cp "$SCRIPT_SRC" /usr/local/sbin/vpnctl
    chmod 755 /usr/local/sbin/vpnctl
    chown root:root /usr/local/sbin/vpnctl
    echo "Installed /usr/local/sbin/vpnctl"
fi

# 4. vpnctl settings (kept if they already exist)
CONF_SRC="$(dirname "$0")/vpnctl.conf.example"
if [ ! -f /etc/amnezia/vpnctl.conf ] && [ -f "$CONF_SRC" ]; then
    install -D -m 600 -o root -g root "$CONF_SRC" /etc/amnezia/vpnctl.conf
    echo "Installed /etc/amnezia/vpnctl.conf - check INTERFACE and ENDPOINT_HOST"
fi

# 5. Install Sudoers configuration
SUDOERS_SRC="$(dirname "$0")/sudoers.example"
if [ -f "$SUDOERS_SRC" ]; then
    visudo -cf "$SUDOERS_SRC" >/dev/null
    install -m 440 -o root -g root "$SUDOERS_SRC" /etc/sudoers.d/vpn-provisioner
    echo "Installed /etc/sudoers.d/vpn-provisioner"
fi

echo "==> Provisioner setup complete. Verify with:"
echo "    sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl peer-status --peer-id test"
