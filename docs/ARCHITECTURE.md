# Architecture

```
Telegram  <-->  bot  ----writes---->  database  <----reads/writes----  scheduler
                                        ^   |
                                        |   v
                                       worker  --(local sudo or SSH)-->  vpnctl  -->  awg1.conf, awg set
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
- The bot processes never run as root. `vpn-provisioner` can run only `vpnctl`, and only with the subcommands listed in `sudoers.example`.
- `vpnctl` checks every argument: names must match `^[a-zA-Z0-9_-]{1,64}$`, and subscription IDs must be UUIDs. The SSH provisioner checks names too, and quotes every argument.
- The worker checks every VPN host's SSH key against `known_hosts` and refuses unknown or changed keys. With Docker, the SSH key and `known_hosts` are mounted read-only.
- The code in `/opt/amnezia_vpn_bot` is owned by root. `vpn-provisioner` can write only `data/`, and can read but not change `.env`. Root runs `install-provisioner.sh` from this folder, so a bot the service user could edit would give root to anyone who breaks into the bot. The installer refuses to run if the folder isn't root-owned.
- Customer text (receipt notes, support messages) is HTML-escaped before it reaches the admin chat. Alerts that carry `vpnctl` output are sent as plain text.
- Logs redact bot tokens, passwords, private keys, client configs and `vpn://` links.
- `ThrottlingMiddleware` drops messages and button presses sent less than 0.5 s apart by the same user. `/block` suspends a user.
- Button data comes from the client, so handlers check again that a server and plan are on sale, and that a subscription belongs to the user.

### More than one server

The bot host holds an SSH key that reaches `vpn-provisioner` on every other VPN host. On those hosts the key can only run `vpnctl` through `/usr/local/sbin/vpnctl-ssh`, which accepts the six commands the bot sends (create, disable, enable, remove, status, config) with checked arguments, and nothing else: no shell, file copy or port forwarding. `from=` in `authorized_keys` accepts the key only from the bot host's Tailscale IP.

What a break-in can reach:

- **Bot host:** the bot token, the database, and `vpnctl` on every server. The attacker can create, disable or remove customers and read their configs, but gets no shell or root on the other servers. Keep this host patched and backed up.
- **Any other server:** only that server's own customers. It can't use the bot's key, and with the Tailscale policy below it can't open connections to the bot host or other servers. The bot checks its host key and treats what `vpnctl` returns as data: it takes only the config and builds the file name and `vpn://` link itself.

Tailscale allows every device to reach every other one by default. To stop a server from reaching the others, tag the servers in the Tailscale admin console (Machines, Edit ACL tags) and set a policy (Access controls) like this:

```json
{
  "tagOwners": {
    "tag:bot": ["autogroup:admin"],
    "tag:vpn": ["autogroup:admin"]
  },
  "acls": [
    {"action": "accept", "src": ["autogroup:admin"], "dst": ["*:*"]},
    {"action": "accept", "src": ["tag:bot"], "dst": ["tag:vpn:22"]},
    {"action": "accept", "src": ["autogroup:member"], "dst": ["autogroup:internet:*"]}
  ]
}
```

Tag the bot host `tag:bot` and the other VPN hosts `tag:vpn`. Your own devices keep full access, the bot host can reach only SSH on the VPN hosts, other people in the tailnet can use exit nodes but reach no machine, and the servers can't open connections to any machine in the tailnet. Before saving, use the policy editor's preview to check that family and friends' devices still have exit node access.

