# Architecture & Technical Design

## 1. High-Level Architecture Overview

The AmneziaWG Telegram Sales & Subscription Bot is designed as a decoupled, multi-process architecture consisting of three dedicated containerized daemons and an outbox pattern for fault-tolerant background provisioning:

```
                  +----------------------------------------------+
                  |               Telegram Clients               |
                  +----------------------+-----------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  |               Bot Daemon (AIOGram 3)         |
                  |  - Bilingual Menus (EN/FA)                   |
                  |  - Catalog & Order FSM                       |
                  |  - Receipt Submissions                       |
                  |  - Customer Support Ticket Bridge            |
                  |  - Admin Dashboard & Approvals               |
                  +----------------------+-----------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  |               PostgreSQL 16                  |
                  |  - Orders & Subscriptions (State Machines)   |
                  |  - Transactional Outbox (Jobs Queue)         |
                  |  - Tickets & Messages                        |
                  |  - Notifications & Audit Log                 |
                  +-----------+----------------------+-----------+
                              ^                      ^
                              |                      |
            +-----------------+                      +-----------------+
            |                                                          |
+-----------+------------------+                   +-------------------+--------------------+
|  Outbox Worker Engine        |                   |  Scheduler Lifecycle Daemon            |
|  - Idempotent Job Processing |                   |  - Expiry Reminders (7d, 3d, 1d)       |
|  - SSH Command Provisioner   |                   |  - Automatic Peer Disabling on Expiry  |
|  - In-Memory Config Delivery |                   |  - Grace-Period Peer Removal           |
|  - Exponential Backoff       |                   +----------------------------------------+
+-----------+------------------+
            | SSH (Port 22, Non-Root `vpn-provisioner`)
            v
+------------------------------+
|  Remote VPN Server Nodes     |
|  - `/usr/local/sbin/vpnctl`  |
|  - AmneziaWG Interface       |
+------------------------------+
```

---

## 2. Key Subsystems & Design Patterns

### 2.1 Transactional Outbox Pattern
When an administrator approves an order or when a peer status changes, the database state mutation (`subscriptions`, `orders`) and the provisioning task (`provisioning_jobs`) are committed atomically within a single SQL transaction.
- The `WorkerEngine` polls for pending jobs using row locking (`FOR UPDATE SKIP LOCKED`).
- If an SSH error or network hiccup occurs, the job state is updated with exponential backoff (`next_retry_at = now + 2^attempts * 15s`).
- Permanent errors trigger administrative alerts without hanging the worker process.

### 2.2 Security Architecture & Zero-Root Principle
- **Zero Root in Bot Container**: The bot daemon and worker run inside non-root container environments as `appuser` (UID 1000).
- **Dedicated VPN Provisioner User**: On remote VPN servers, SSH access is strictly limited to the `vpn-provisioner` system account using dedicated SSH public keys.
- **Sudoers Whitelist**: The `vpn-provisioner` user only has sudo permission to execute `/usr/local/sbin/vpnctl` with no other privileged system access.
- **Paramiko Parameter Sanitization**: All peer identifiers and labels are strictly validated against `^[a-zA-Z0-9_-]{1,64}$` before SSH execution, preventing command injection.

### 2.3 Ephemeral Configuration Delivery
- AmneziaWG configuration files (`.conf`) and `.vpn` profiles are generated and transmitted **in-memory as private Telegram document attachments**.
- Plaintext configuration files and private keys are **never stored plaintext in PostgreSQL**, eliminating data leak risks if the database backup is compromised.

### 2.4 State Machines

#### Order Lifecycle:
`DRAFT` -> `AWAITING_RECEIPT` -> `RECEIPT_SUBMITTED` -> `PROVISIONING` -> `FULFILLED` (or `REJECTED` / `CANCELLED`)

#### Subscription Lifecycle:
`PROVISIONING` -> `ACTIVE` -> `EXPIRED` -> `DISABLED` -> `REVOKED`
