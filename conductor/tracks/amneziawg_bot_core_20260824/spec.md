# Specification: AmneziaWG Telegram Sales & Subscription Bot

## 1. Overview
A production-ready Telegram sales and subscription-management bot built for AmneziaWG / AmneziaVPN deployments. The bot enables customers to purchase VPN subscriptions via manual receipt verification, receives delivered VPN configuration files upon admin approval, receives expiration notifications, and interacts with support. Background operations run via an asynchronous transactional outbox worker and database-driven scheduler, decoupled from the Telegram-facing bot and remote provisioning hosts.

---

## 2. Functional Requirements

### 2.1 Customer Experience
- **Navigation & Profile:** `/start` command registers or updates user profile (using immutable numeric `telegram_user_id`), displays main menu (Buy VPN, My Subscriptions, Support, Help).
- **Purchase Flow:**
  1. Select from active VPN servers/countries (e.g., Germany, Turkey).
  2. Select from active product plans (e.g., 1 Month, 3 Months).
  3. View order summary and snapshot payment instructions (English / Farsi ready).
  4. Confirm order to transition to `awaiting_receipt`.
  5. Upload payment receipt (photo or document + optional note).
  6. Order transitions to `receipt_submitted` and receipt metadata is captured.
- **Config Delivery:**
  - Upon admin approval and worker provisioning, customer receives `.vpn` / `.conf` configuration document directly via private Telegram message.
  - Expiration dates clearly displayed.
- **My Subscriptions:**
  - View active/expired subscriptions with status and expiry.
  - Request configuration redelivery (subject to `CONFIG_REDELIVERY_LIMIT`).
- **Support System:**
  - Open support ticket with message and optional photo/document attachment.
  - Receive admin replies forwarded directly through the bot.

### 2.2 Administrator Capabilities
- **Receipt Verification:**
  - Forwarded order cards in designated `ADMIN_CHAT_ID` with receipt preview and metadata.
  - Inline action buttons: `Approve`, `Reject`, `View User Subscriptions`.
  - Strict idempotency: Prevent concurrent or duplicate execution on repeated clicks.
- **Admin Management Commands:**
  - `/admin`: Interactive dashboard showing system status, pending orders, and server stats.
  - `/orders pending` & `/orders recent`: View and process orders.
  - `/subscriptions expiring` & `/subscriptions user <telegram_user_id>`: Audit customer subscriptions.
  - `/servers`, `/server enable <slug>`, `/server disable <slug>`: Manage server routing.
  - `/extend <subscription_id_or_code> <days>`: Extend active subscription expiry without recreating peers.
  - `/disable <subscription_id_or_code>`: Disable VPN peer access immediately.
  - `/retry <order_code_or_subscription_id>`: Retry failed provisioning job.
  - `/reply <ticket_code> <message>` or Telegram message reply in admin chat.

### 2.3 Provisioning Layer & Server Isolation
- **Provider Protocol (`VPNProvisioner`):**
  - Methods: `create_peer`, `disable_peer`, `remove_peer`, `get_peer_status`.
  - `MockProvisioner`: Default mock provider for testing and local development.
  - `SSHCommandProvisioner`: Production provider using non-root SSH keys and strict argument validation calling remote `/usr/local/sbin/vpnctl`.
- **Remote `vpnctl` CLI & Setup (`scripts/provisioner/`):**
  - Standalone script running on VPN host with restricted `sudoers` privileges.
  - Manages AmneziaWG Docker container (`amnezia-awg`) peer configurations without exposing root shell or Docker socket to the bot.
  - Supports `--dry-run` validation mode.

### 2.4 Asynchronous Worker & Scheduler
- **Transactional Outbox Engine (`provisioning_jobs`):**
  - Durable job tracking for `create_peer`, `disable_peer`, `remove_peer`, `redeliver_config`.
  - Atomic database locks, retry counters, backoff intervals, and error classification (retryable vs. permanent).
- **Scheduled Expiry & Reminders:**
  - Expiry evaluation and automated queuing of `disable_peer` jobs.
  - Scheduled reminder notifications at 7, 3, and 1 day prior to expiration (with idempotency guards).
  - Grace period peer cleanup (`PEER_REMOVAL_GRACE_DAYS`).

---

## 3. Data Model (PostgreSQL 16+)
- `users`: User profiles, numeric `telegram_user_id`, language code, blocked status.
- `vpn_servers`: Server nodes, country details, host/port, SSH username, enabled flag, capacity limits.
- `products`: Plan codes, durations (days), device limits, prices, currencies, enabled status.
- `orders`: Public codes, snapshots of pricing/payment instructions, status lifecycle, receipt Telegram metadata (`file_id`, `message_id`, `chat_id`).
- `subscriptions`: User/order/server linkage, status, peer external ID, safe label, start/expire timestamps, delivery metadata.
- `provisioning_jobs`: Outbox jobs, job type, aggregate linkage, status, attempt counts, lock tokens, JSONB payloads, error history.
- `notifications`: Delivery tracking, notification type, unique idempotency keys, sent timestamps.
- `support_tickets` & `support_messages`: Ticketing system with message threading and Telegram message mappings.
- `audit_events`: Immutable audit trail recording actor, event type, entity ID, and sanitized metadata.

---

## 4. Acceptance Criteria
1. Project builds and runs cleanly via Docker Compose (`bot`, `worker`, `scheduler`, `postgres`).
2. Full automated test suite passes with >80% code coverage.
3. In `PROVISIONER_MODE=mock`:
   - Customer can order, upload receipt, admin receives card.
   - Admin approval enqueues outbox job and delivers mock config document to customer.
   - Idempotency verified: Duplicate approval callbacks do not create duplicate peers.
   - Expired subscriptions trigger `disable_peer` and notify customer.
   - Support ticket creation and admin reply routing verified.
4. Comprehensive documentation provided in `docs/` (`ARCHITECTURE.md`, `OPERATIONS.md`, `AMNEZIAWG_INTEGRATION.md`, `SECURITY.md`).
5. Provisioning scripts in `scripts/provisioner/` with `vpnctl`, `install-provisioner.sh`, and `sudoers` example.
