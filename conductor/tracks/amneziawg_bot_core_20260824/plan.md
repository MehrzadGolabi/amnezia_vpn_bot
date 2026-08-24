# Implementation Plan: AmneziaWG Telegram Sales & Subscription Bot

## Phase 1: Project Scaffolding, Configuration & Data Layer

- [x] Task: Project Layout & Configuration Management (a0ac99c)
    - [x] Write unit tests for configuration loading and validation in `tests/unit/test_config.py`
    - [x] Implement Pydantic Settings in `src/app/config/settings.py` supporting bot tokens, admin IDs, database URLs, and server configurations
    - [x] Create `.env.example` and base project setup (`pyproject.toml`, Makefile, logging config with secret redaction)
- [x] Task: Database Engine & SQLAlchemy Async Models (b6ac501)
    - [x] Write unit tests for database schemas, constraints, and models in `tests/unit/test_models.py`
    - [x] Implement SQLAlchemy 2.0 declarative models in `src/app/db/models/` (`User`, `VPNServer`, `Product`, `Order`, `Subscription`, `ProvisioningJob`, `Notification`, `SupportTicket`, `SupportMessage`, `AuditEvent`)
    - [x] Set up async database session management and engine in `src/app/db/session.py`
- [x] Task: Alembic Migrations Setup (c8170e5)
    - [x] Configure Alembic async environment in `src/app/db/migrations/`
    - [x] Generate and verify initial migration script covering all required tables and indexes
- [x] Task: Data Repositories & Base Services (1f581a1)
    - [x] Write unit tests for repository operations in `tests/unit/test_repositories.py`
    - [x] Implement repository classes in `src/app/db/repositories/` (`UserRepository`, `OrderRepository`, `SubscriptionRepository`, `JobRepository`, `TicketRepository`, `AuditRepository`)
- [x] Task: Conductor - User Manual Verification 'Phase 1: Project Scaffolding, Configuration & Data Layer' (Protocol in workflow.md)

## Phase 2: Provisioning Abstraction & Server-Side Tools

- [x] Task: Provisioning Protocol & Mock Provisioner (15847f1)
    - [x] Write unit tests for `VPNProvisioner` protocol and `MockProvisioner` in `tests/unit/test_mock_provisioner.py`
    - [x] Implement `VPNProvisioner` interface and `MockProvisioner` returning structured in-memory configs in `src/app/integrations/provisioning/`
- [x] Task: SSH Command Provisioner (28816cf)
    - [x] Write unit tests for `SSHCommandProvisioner` with mocked SSH client and command validation in `tests/unit/test_ssh_provisioner.py`
    - [x] Implement `SSHCommandProvisioner` with strict argument validation, timeout handling, and host-key verification in `src/app/integrations/provisioning/ssh_provisioner.py`
- [x] Task: Remote Provisioning Tooling (`vpnctl`) & Setup Scripts (daf0966)
    - [x] Write unit and validation tests for `vpnctl` CLI parsing and argument safety in `tests/unit/test_vpnctl.py`
    - [x] Create `scripts/provisioner/vpnctl` supporting `create-peer`, `disable-peer`, `remove-peer`, `peer-status`, and `--dry-run`
    - [x] Create `scripts/provisioner/install-provisioner.sh` and scoped `sudoers` configuration example
- [x] Task: Conductor - User Manual Verification 'Phase 2: Provisioning Abstraction & Server-Side Tools' (Protocol in workflow.md)

## Phase 3: Asynchronous Outbox Worker & Scheduler Engine

- [x] Task: Outbox Worker Engine (0cd7bda)
    - [x] Write unit tests for durable job locking, retries, and error classification in `tests/unit/test_worker.py`
    - [x] Implement transactional outbox worker loop in `src/app/worker/engine.py` for handling `create_peer`, `disable_peer`, `remove_peer`, and `redeliver_config`
    - [x] Implement error classification (retryable vs. permanent) and backoff calculation
- [x] Task: Scheduler Service for Expiry & Reminders (559b9cc)
    - [x] Write unit tests for reminder checks, idempotency keys, and expiry transitions in `tests/unit/test_scheduler.py`
    - [x] Implement APScheduler service in `src/app/scheduler/service.py` to evaluate expiring subscriptions and queue notifications/disable jobs
    - [x] Implement grace-period cleanup for peer removal (`PEER_REMOVAL_GRACE_DAYS`)
- [x] Task: Conductor - User Manual Verification 'Phase 3: Asynchronous Outbox Worker & Scheduler Engine' (Protocol in workflow.md)

## Phase 4: Telegram Bot - Customer Flows & Support System

- [x] Task: Bot Core, Middleware & Keyboard Builders (c4b1124)
    - [x] Write unit tests for user registration middleware, rate limiter, and keyboard builders in `tests/unit/test_bot_core.py`
    - [x] Implement user upsert middleware, rate-limiting middleware, and localization strings in `src/app/bot/middleware/`
    - [x] Implement inline keyboard builders for server selection, plan selection, subscriptions, and support in `src/app/bot/keyboards/`
- [x] Task: Main Navigation & Purchase Flow (fea315d)
    - [x] Write unit tests for `/start`, catalog selection, order drafting, and receipt upload in `tests/unit/test_customer_flow.py`
    - [x] Implement handlers for `/start`, server selection, product plan selection, and order summary in `src/app/bot/handlers/customer.py`
    - [x] Implement receipt upload FSM handler (photos/documents + note) and transition to `receipt_submitted`
- [x] Task: Subscriptions Management & Config Delivery (aae0d2c)
    - [x] Write unit tests for subscription listing, redelivery rate limits, and document delivery in `tests/unit/test_subscription_delivery.py`
    - [x] Implement `My Subscriptions` handler with config redelivery and private document sending
- [x] Task: Customer Support Ticketing Flow (6556836)
    - [x] Write unit tests for support ticket creation and message forwarding in `tests/unit/test_support_customer.py`
    - [x] Implement support handlers allowing customers to submit ticket messages and attachments in `src/app/bot/handlers/support.py`
- [x] Task: Conductor - User Manual Verification 'Phase 4: Telegram Bot - Customer Flows & Support System' (Protocol in workflow.md)

## Phase 5: Telegram Bot - Admin Dashboard, Verification & Management

- [x] Task: Admin Receipt Verification & Idempotent Approvals (62f08ab)
    - [x] Write unit tests for admin order approval, rejection with reason, and idempotency in `tests/unit/test_admin_approvals.py`
    - [x] Implement admin receipt verification handlers (`/admin`, `adm_app_<order_id>`, `adm_rej_<order_id>`) in `src/app/bot/handlers/admin.py`
    - [x] Implement notification dispatch to customer upon approval (with pending provisioning notice) or rejection (with reason)
- [x] Task: Admin Support Ticket Reply & Resolution (9d5caa9)
    - [x] Write unit tests for admin ticket replies, message routing, and ticket closing in `tests/unit/test_admin_support.py`
    - [x] Implement admin ticket conversation handlers (`adm_rep_tck_<id>`, `adm_cls_tck_<id>`) and message delivery to customers
- [x] Task: Admin Server, Product, and User Management (ac38808)
    - [x] Write unit tests for server toggling, product management, user lookup, and blocking in `tests/unit/test_admin_management.py`
    - [x] Implement admin management commands (`/servers`, `/products`, `/user <id>`, `/block <id>`, `/unblock <id>`)
- [x] Task: Conductor - User Manual Verification 'Phase 5: Telegram Bot - Admin Dashboard, Verification & Management' (Protocol in workflow.md)

## Phase 6: Containerization, Operational Tooling & Documentation

- [x] Task: Operational Utilities & Health Monitoring (c0ea47e)
    - [x] Write tests for health checks, audit logging, and peer reconciliation in `tests/unit/test_operations.py`
    - [x] Implement `/healthz` container healthcheck and non-destructive peer reconciliation script in `src/app/utils/`
- [ ] Task: Docker & Deployment Scaffolding
    - [ ] Create `Dockerfile` with multi-stage build for `bot`, `worker`, and `scheduler`
    - [ ] Create `docker-compose.yml` defining `postgres`, `bot`, `worker`, and `scheduler` services
- [ ] Task: Comprehensive Documentation
    - [ ] Create `docs/ARCHITECTURE.md` detailing system topology, outbox pattern, and security boundaries
    - [ ] Create `docs/OPERATIONS.md` covering setup, backup, restoration, and incident response
    - [ ] Create `docs/AMNEZIAWG_INTEGRATION.md` documenting AmneziaWG VPS assumptions and configuration
    - [ ] Create `docs/SECURITY.md` detailing threat model and secret hygiene
    - [ ] Create `README.md` with quick-start instructions and Makefile commands
- [ ] Task: End-to-End Mock Integration Test Suite
    - [ ] Write complete end-to-end flow test in `tests/e2e/test_full_lifecycle.py` verifying mock order, receipt submission, admin approval, worker delivery, expiry, and support ticket reply
- [ ] Task: Conductor - User Manual Verification 'Phase 6: Containerization, Operational Tooling & Documentation' (Protocol in workflow.md)
