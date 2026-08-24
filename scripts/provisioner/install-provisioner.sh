#!/usr/bin/env bash
set -euo pipefail

echo "==> Setting up vpn-provisioner service account on AmneziaWG host"

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

# 4. Install Sudoers configuration
SUDOERS_SRC="$(dirname "$0")/sudoers.example"
if [ -f "$SUDOERS_SRC" ]; then
    cp "$SUDOERS_SRC" /etc/sudoers.d/vpn-provisioner
    chmod 440 /etc/sudoers.d/vpn-provisioner
    echo "Installed /etc/sudoers.d/vpn-provisioner"
fi

echo "==> Provisioner setup complete. Verify with: sudo -u vpn-provisioner /usr/local/sbin/vpnctl --help"
