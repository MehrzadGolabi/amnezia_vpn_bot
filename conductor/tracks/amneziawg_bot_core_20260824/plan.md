# Implementation Plan: AmneziaWG Telegram Sales & Subscription Bot

## Phase 1: Project Scaffolding, Configuration & Data Layer

- [ ] Task: Project Layout & Configuration Management
    - [ ] Write unit tests for configuration loading and validation in `tests/unit/test_config.py`
    - [ ] Implement Pydantic Settings in `src/app/config/settings.py` supporting bot tokens, admin IDs, database URLs, and server configurations
    - [ ] Create `.env.example` and base project setup (`pyproject.toml`, Makefile, logging config with secret redaction)
- [ ] Task: Database Engine & SQLAlchemy Async Models
    - [ ] Write unit tests for database schemas, constraints, and models in `tests/unit/test_models.py`
    - [ ] Implement SQLAlchemy 2.0 declarative models in `src/app/db/models/` (`User`, `VPNServer`, `Product`, `Order`, `Subscription`, `ProvisioningJob`, `Notification`, `SupportTicket`, `SupportMessage`, `AuditEvent`)
    - [ ] Set up async database session management and engine in `src/app/db/session.py`
- [ ] Task: Alembic Migrations Setup
    - [ ] Configure Alembic async environment in `src/app/db/migrations/`
    - [ ] Generate and verify initial migration script covering all required tables and indexes
- [ ] Task: Data Repositories & Base Services
    - [ ] Write unit tests for repository operations in `tests/unit/test_repositories.py`
    - [ ] Implement repository classes in `src/app/db/repositories/` (`UserRepository`, `OrderRepository`, `SubscriptionRepository`, `JobRepository`, `TicketRepository`, `AuditRepository`)
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Project Scaffolding, Configuration & Data Layer' (Protocol in workflow.md)

## Phase 2: Provisioning Abstraction & Server-Side Tools

- [ ] Task: Provisioning Protocol & Mock Provisioner
    - [ ] Write unit tests for `VPNProvisioner` protocol and `MockProvisioner` in `tests/unit/test_mock_provisioner.py`
    - [ ] Implement `VPNProvisioner` interface and `MockProvisioner` returning structured in-memory configs in `src/app/integrations/provisioning/`
- [ ] Task: SSH Command Provisioner
    - [ ] Write unit tests for `SSHCommandProvisioner` with mocked SSH client and command validation in `tests/unit/test_ssh_provisioner.py`
    - [ ] Implement `SSHCommandProvisioner` with strict argument validation, timeout handling, and host-key verification in `src/app/integrations/provisioning/ssh_provisioner.py`
- [ ] Task: Remote Provisioning Tooling (`vpnctl`) & Setup Scripts
    - [ ] Write unit and validation tests for `vpnctl` CLI parsing and argument safety in `tests/unit/test_vpnctl.py`
    - [ ] Create `scripts/provisioner/vpnctl` supporting `create-peer`, `disable-peer`, `remove-peer`, `peer-status`, and `--dry-run`
    - [ ] Create `scripts/provisioner/install-provisioner.sh` and scoped `sudoers` configuration example
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Provisioning Abstraction & Server-Side Tools' (Protocol in workflow.md)

## Phase 3: Asynchronous Outbox Worker & Scheduler Engine

- [ ] Task: Outbox Worker Engine
    - [ ] Write unit tests for durable job locking, retries, and error classification in `tests/unit/test_worker.py`
    - [ ] Implement transactional outbox worker loop in `src/app/worker/engine.py` for handling `create_peer`, `disable_peer`, `remove_peer`, and `redeliver_config`
    - [ ] Implement error classification (retryable vs. permanent) and backoff calculation
- [ ] Task: Scheduler Service for Expiry & Reminders
    - [ ] Write unit tests for reminder checks, idempotency keys, and expiry transitions in `tests/unit/test_scheduler.py`
    - [ ] Implement APScheduler service in `src/app/scheduler/service.py` to evaluate expiring subscriptions and queue notifications/disable jobs
    - [ ] Implement grace-period cleanup for peer removal (`PEER_REMOVAL_GRACE_DAYS`)
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Asynchronous Outbox Worker & Scheduler Engine' (Protocol in workflow.md)

## Phase 4: Telegram Bot - Customer Flows & Support System

- [ ] Task: Bot Core, Middleware & Localization Setup
    - [ ] Write unit tests for bot initialization, authentication middleware, and error handling in `tests/unit/test_bot_middlewares.py`
    - [ ] Set up aiogram 3.x Dispatcher, routers, structured logging middleware, and i18n text dictionaries in `src/app/bot/`
- [ ] Task: Main Navigation & Purchase Flow
    - [ ] Write unit tests for `/start`, catalog selection, order drafting, and receipt upload in `tests/unit/test_customer_flow.py`
    - [ ] Implement handlers for `/start`, server selection, product plan selection, and order summary in `src/app/bot/handlers/customer.py`
    - [ ] Implement receipt upload FSM handler (photos/documents + note) and transition to `receipt_submitted`
- [ ] Task: Subscriptions Management & Config Delivery
    - [ ] Write unit tests for subscription listing, redelivery rate limits, and document delivery in `tests/unit/test_subscription_delivery.py`
    - [ ] Implement `My Subscriptions` handler with config redelivery and private document sending
- [ ] Task: Customer Support Ticketing Flow
    - [ ] Write unit tests for support ticket creation and message forwarding in `tests/unit/test_support_customer.py`
    - [ ] Implement support handlers allowing customers to submit ticket messages and attachments in `src/app/bot/handlers/support.py`
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Telegram Bot - Customer Flows & Support System' (Protocol in workflow.md)

## Phase 5: Telegram Bot - Admin Dashboard, Verification & Management

- [ ] Task: Admin Receipt Verification & Idempotent Approvals
    - [ ] Write unit tests for admin authorization, receipt card formatting, and idempotent approval/rejection in `tests/unit/test_admin_verification.py`
    - [ ] Implement admin receipt forwarding, inline action buttons (`Approve`, `Reject`, `User Subscriptions`), and atomic state transitions in `src/app/bot/handlers/admin_orders.py`
- [ ] Task: Admin Commands & Dashboard
    - [ ] Write unit tests for `/admin`, `/orders`, `/servers`, `/extend`, `/disable`, and `/retry` in `tests/unit/test_admin_commands.py`
    - [ ] Implement admin management handlers in `src/app/bot/handlers/admin_mgmt.py`
- [ ] Task: Admin Support Ticket Bridge
    - [ ] Write unit tests for admin ticket replies (message reply and `/reply`) in `tests/unit/test_admin_support.py`
    - [ ] Implement admin support response routing and ticket resolution handlers in `src/app/bot/handlers/admin_support.py`
- [ ] Task: Conductor - User Manual Verification 'Phase 5: Telegram Bot - Admin Dashboard, Verification & Management' (Protocol in workflow.md)

## Phase 6: Containerization, Operational Tooling & Documentation

- [ ] Task: Operational Utilities & Health Monitoring
    - [ ] Write tests for health checks, audit logging, and peer reconciliation in `tests/unit/test_operations.py`
    - [ ] Implement `/healthz` container healthcheck and non-destructive peer reconciliation script in `src/app/utils/`
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
