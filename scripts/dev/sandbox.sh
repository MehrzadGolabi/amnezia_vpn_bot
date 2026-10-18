#!/usr/bin/env bash
# Builds a throwaway AmneziaWG 3.1 "server" in a folder so vpnctl and the bot can
# provision real client configs on your laptop, with scripts/dev/fake-awg standing
# in for the awg binary. Nothing here touches the network or needs root.
#
# usage: scripts/dev/sandbox.sh [dir]     (default: ./.sandbox)
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
DIR=$(mkdir -p "${1:-$REPO/.sandbox}" && cd "${1:-$REPO/.sandbox}" && pwd)
FAKE="python3 $REPO/scripts/dev/fake-awg --state $DIR/awg-state.json"
mkdir -p -m 700 "$DIR/amneziawg/clients"

if [ ! -f "$DIR/amneziawg/awg1.conf" ]; then
  umask 077
  cat > "$DIR/amneziawg/awg1.conf" <<CONF
[Interface]
PrivateKey = $($FAKE genkey)
Address = 10.66.66.1/24
ListenPort = 51888
MTU = 1280
Jc = 6
Jmin = 96
Jmax = 512
S1 = 15
S2 = 15
S3 = 15
S4 = 15
H1 = 1
H2 = 2
H3 = 3
H4 = 4
I1 = <r 64><t><rc 12>
I2 = <t><b 0x$(openssl rand -hex 6 2>/dev/null || echo 0a1b2c3d4e5f)><r 30><rc 8>
I3 = <r 200><rc 8><t>
HeaderProtectionKey = $($FAKE genkey)
ContentPaddingAddition = 8-24
RekeyAfterTime = 100-125
RekeyTimeout = 5-8
RejectAfterTime = 175-185
KeepaliveTimeout = 11-14
MaxHandshakeAttempts = 17-20
RandomTrailers = 1
DisableCookies = 1
CONF
fi

cat > "$DIR/vpnctl.conf" <<CONF
INTERFACE=awg1
CONF_DIR=$DIR/amneziawg
AWG_BIN=$FAKE
ENDPOINT_HOST=203.0.113.10
CONF

cat <<MSG
Sandbox ready in $DIR

Try vpnctl directly:
  VPNCTL_CONFIG=$DIR/vpnctl.conf $REPO/scripts/provisioner/vpnctl create-peer --subscription-id \$(python3 -c 'import uuid;print(uuid.uuid4())') --label test1

Or run the bot against it (add to .env, then make run-bot / run-worker / run-scheduler):
  PROVISIONER_MODE=vpnctl
  VPNCTL_DEV_COMMAND=env VPNCTL_CONFIG=$DIR/vpnctl.conf python3 $REPO/scripts/provisioner/vpnctl
MSG
