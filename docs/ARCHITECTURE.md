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
- With Docker, the SSH key is mounted read-only. Set `SSH_KNOWN_HOSTS_PATH` to have the host key checked. Without it, any host key is accepted.
- Logs redact bot tokens, passwords and private keys.
- `ThrottlingMiddleware` drops messages sent less than 0.5 s apart by the same user. `/block` suspends a user.
