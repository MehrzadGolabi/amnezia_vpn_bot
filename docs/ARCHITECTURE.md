# Architecture

```
Telegram  <-->  bot  ----writes---->  database  <----reads/writes----  scheduler
                                        ^   |
                                        |   v
                                       worker  --(Unix socket, or TCP over Tailscale)-->  vpnctl  -->  awg1.conf, awg set
```

- **bot** (`src/app/bot`) is the aiogram interface. Customers order, upload receipts, read their subscriptions and open tickets. Admins approve, reject and manage things.
- **worker** (`src/app/worker`) runs provisioning jobs from the `provisioning_jobs` table: create, disable and remove peers, and resend configs.
- **scheduler** (`src/app/scheduler`) sends expiry reminders, and queues disable jobs at expiry and remove jobs after the grace period.
- **vpnctl** (`scripts/provisioner/vpnctl`) is the only code that changes the VPN server. See [vpnctl](VPNCTL.md).

Without Docker, `src/app/main.py` runs all three in one process and shares one Telegram connection. Each process that loads aiogram costs about 150 MB of RAM, so one process uses about a third of the memory of three. With Docker, each part has its own entry point (`src.app.bot.main`, `src.app.worker.main`, `src.app.scheduler.main`) and container.

The database is SQLite without Docker, or Postgres with Docker. Migrations live in `src/app/db/migrations`.

## Job queue

Approving an order creates the subscription and its `create_peer` job in one transaction, so an approval never loses its job.

The worker polls every `PROVISIONING_JOB_POLL_SECONDS`. It claims a batch and commits the claim, then runs each job in its own transaction:

- On success, the job is marked `succeeded`.
- On an error, the job's partial changes are rolled back and the job is retried, after 10 s, 30 s, 90 s and then 270 s. It's marked `permanent_failure` after 5 attempts, or immediately if `vpnctl` says the input is bad or the client doesn't exist. The admin chat gets an alert.
- A job left in `processing` for more than 5 minutes (for example, after a crash) is picked up again.

Jobs are safe to repeat. `create-peer` with an existing label returns the existing client, and disable and remove succeed when there's nothing left to do. The scheduler doesn't queue a job if the same one is already pending.

The worker assumes it is the only worker running. Claims don't lock rows, so don't start two workers.

## States

Order: `awaiting_receipt` -> `receipt_submitted` -> `provisioning` -> `fulfilled`, or `rejected`.

Subscription: `provisioning` -> `active` -> `disabled` (expired, peer off) -> `expired` (peer deleted).

## Security

- Client private keys and configs live only on the VPN server, in `/etc/amnezia/amneziawg/clients/`, readable by root only. The database stores the client name, not the keys.
- The bot never runs as root, never uses sudo, and has no SSH key. `vpnbot.service` runs it as `vpn-provisioner` with no capabilities, a read-only file system except `data/`, and a system call filter.
- The bot changes a VPN server only by sending one JSON request to `vpnctl`, which accepts six commands (create, disable, enable, remove, status, config) and nothing else. `vpnctl` checks every argument: names must match `^[a-zA-Z0-9_-]{1,64}$`, and subscription IDs must be UUIDs.
- systemd starts a fresh `vpnctl serve` for each request (`vpnctl@.service`). It runs as root, because changing the interface needs it, but can write only the AmneziaWG folder, keeps only `CAP_NET_ADMIN`, and can't open network connections of its own.
- The code in `/opt/amnezia_vpn_bot` is owned by root. `vpn-provisioner` can write only `data/`, and can read but not change `.env`. Root runs `install-provisioner.sh` from this folder, so a bot the service user could edit would give root to anyone who breaks into the bot. The installer refuses to run if the folder isn't root-owned.
- Customer text (receipt notes, support messages) is HTML-escaped before it reaches the admin chat. Alerts that carry `vpnctl` output are sent as plain text.
- Logs redact bot tokens, passwords, private keys, client configs and `vpn://` links.
- `ThrottlingMiddleware` drops messages and button presses sent less than 0.5 s apart by the same user. `/block` suspends a user.
- Button data comes from the client, so handlers check again that a server and plan are on sale, and that a subscription belongs to the user.

### How the bot reaches vpnctl

On the bot's own host, `vpnctl.socket` listens on `/run/vpnctl/vpnctl.sock`. Only root and the `vpn-provisioner` group can connect.

On every other VPN host, `vpnctl-tailnet.socket` listens on that host's Tailscale address, port 7391. Three things have to agree before a request runs:

1. The Tailscale policy below lets only the bot host (`tag:bot`) reach that port.
2. systemd's `IPAddressAllow` accepts connections only from the bot host's Tailscale IP.
3. `vpnctl` itself refuses any caller not listed in `ALLOWED_CLIENTS` in `/etc/amnezia/vpnctl.conf`. This is the check that doesn't depend on anything else being set up right.

A Tailscale address can't be faked: traffic from 100.x.y.z arrives through WireGuard, signed by that machine's key, and Tailscale drops packets claiming a 100.x address that come in any other way. That makes the address a real identity, so the bot needs no SSH key or password of its own. The connection is encrypted by WireGuard.

This is not automatically safer than SSH with a forced command. A root service listening on the network is a target of its own. What it removes is the bot's SSH key, a login account with sudo on every VPN host, and an unsandboxed `vpnctl`. What it adds is a small, sandboxed process per request, and a dependency on Tailscale being set up right, which is why `vpnctl` checks the caller itself.

What a break-in can reach:

- **Bot host:** the bot token, the database, and `vpnctl` on every server. The attacker can create, disable or remove customers and read their configs, but gets no shell or root on the other servers. Keep this host patched and backed up.
- **Any other server:** only that server's own customers. It has no key to the others, and with the Tailscale policy below it can't open connections to the bot host or other servers. The bot treats what `vpnctl` returns as data: it takes only the config and builds the file name and `vpn://` link itself.

Tailscale allows every device to reach every other one by default. To stop a server from reaching the others, tag the servers in the Tailscale admin console (Machines, Edit ACL tags) and set a policy (Access controls) like this:

```json
{
  "tagOwners": {
    "tag:bot": ["autogroup:admin"],
    "tag:vpn": ["autogroup:admin"]
  },
  "acls": [
    {"action": "accept", "src": ["autogroup:admin"], "dst": ["*:*"]},
    {"action": "accept", "src": ["tag:bot"], "dst": ["tag:vpn:7391"]},
    {"action": "accept", "src": ["autogroup:member"], "dst": ["autogroup:internet:*"]}
  ]
}
```

Tag the bot host `tag:bot` and the other VPN hosts `tag:vpn`. Your own devices keep full access, the bot host can reach only `vpnctl` on the VPN hosts, other people in the tailnet can use exit nodes but reach no machine, and the servers can't open connections to any machine in the tailnet. Before saving, use the policy editor's preview to check that family and friends' devices still have exit node access.
