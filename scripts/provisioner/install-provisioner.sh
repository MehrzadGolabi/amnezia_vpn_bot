#!/usr/bin/env bash
set -euo pipefail

echo "==> Setting up vpn-provisioner service account on AmneziaWG host"

# Root installs these files as root programs and a sudoers rule. If anyone but root
# can change them, or the folders above them, a break-in to the bot becomes root here.
SRC_DIR="$(cd "$(dirname "$0")" && pwd -P)"
check_root_only() {
    local owner mode
    owner=$(stat -c %u "$1")
    mode=$(stat -c %a "$1")
    if [ "$owner" != 0 ] || (( 8#$mode & 8#022 )); then
        echo "Refusing to install: $1 is owned by uid $owner with mode $mode."
        echo "It must be owned by root and not writable by group or others. Fix it with:"
        echo "    chown -R root:root /opt/amnezia_vpn_bot && chmod -R go-w /opt/amnezia_vpn_bot"
        echo "then give vpn-provisioner its data folder back (see docs/OPERATIONS.md#updating)."
        exit 1
    fi
}
dir="$SRC_DIR"
while :; do
    check_root_only "$dir"
    [ "$dir" = / ] && break
    dir="$(dirname "$dir")"
done
for f in "$SRC_DIR"/*; do
    check_root_only "$f"
done

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

# 3b. Forced command for the bot's SSH key
WRAPPER_SRC="$(dirname "$0")/vpnctl-ssh"
if [ -f "$WRAPPER_SRC" ]; then
    install -m 755 -o root -g root "$WRAPPER_SRC" /usr/local/sbin/vpnctl-ssh
    echo "Installed /usr/local/sbin/vpnctl-ssh"
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

# 6. Limit SSH logins as vpn-provisioner to vpnctl-ssh
SSHD_SRC="$(dirname "$0")/sshd-vpn-provisioner.conf"
SSHD_DST=/etc/ssh/sshd_config.d/vpn-provisioner.conf
if [ -f "$SSHD_SRC" ] && [ -d /etc/ssh/sshd_config.d ]; then
    install -m 644 -o root -g root "$SSHD_SRC" "$SSHD_DST"
    mkdir -p /run/sshd    # sshd -t needs it, and socket-activated ssh may not have made it yet
    if sshd -t; then
        systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
        echo "Installed $SSHD_DST"
    else
        rm -f "$SSHD_DST"
        echo "WARNING: sshd rejected $SSHD_DST, so it was not installed"
    fi
fi

echo "==> Provisioner setup complete. Verify with:"
echo "    sudo -u vpn-provisioner sudo -n /usr/local/sbin/vpnctl peer-status --peer-id test"
