# Initial Concept

Production-minded Telegram sales and subscription-management bot for AmneziaWG / AmneziaVPN-style deployments with manual receipt-verification flow, idempotent admin approvals, modular asynchronous worker/scheduler architecture, PostgreSQL outbox pattern, and secured SSH command-based provisioning.

# Product Guide: AmneziaWG Telegram Sales & Subscription Bot

## 1. Vision & Purpose
A secure, scalable, production-grade Telegram bot ecosystem designed to sell and manage AmneziaWG VPN subscriptions. The system pairs automated peer lifecycle management with a human-in-the-loop receipt verification workflow, ensuring that no active VPN peers are provisioned without explicit administrator validation while keeping sensitive server credentials and Docker sockets strictly isolated from the Telegram bot interface.

## 2. Target Users & Personas
- **Customers / VPN Users:**
  - Browse available server locations (e.g., Germany, Turkey) and subscription duration tiers.
  - Review clear payment instructions and upload receipt proofs (photos/documents).
  - Receive delivered `.vpn` / `.conf` configuration files directly via Telegram document upon admin approval.
  - Check subscription status, expiry dates, and safely request configuration redelivery.
  - Open support tickets and exchange messages/attachments with admins directly within Telegram.
- **System Administrators:**
  - Receive real-time notification cards with receipt proofs for pending orders.
  - Approve or reject orders via inline buttons with strict idempotency protection.
  - Manage server capacities, enable/disable servers, and manually extend or disable subscriptions.
  - Handle support tickets by replying directly to Telegram messages or using dedicated admin commands.
  - Monitor system health, worker/scheduler heartbeats, and audit events.

## 3. Core Capabilities & Flows

### 3.1 Customer Subscription Lifecycle
1. **Catalog & Order Creation:** User selects country/server and product duration; reviews pricing and snapshot payment instructions; confirms order creation (`awaiting_receipt`).
2. **Receipt Submission:** User uploads payment receipt (photo/doc + optional note); metadata is captured (`receipt_submitted`) without downloading binary payloads locally.
3. **Admin Verification:** Admin reviews receipt card in private admin chat and approves or rejects with reason.
4. **Automated Provisioning:** On approval, an outbox provisioning job (`create_peer`) is durably enqueued; worker invokes the provisioning adapter; on success, VPN configuration document is delivered to the customer and the subscription is marked `active`.
5. **Monitoring & Expiry Reminders:** Customer receives timely expiration notices (e.g., 7d, 3d, 1d before expiry).
6. **Graceful Deactivation & Cleanup:** At expiry, worker triggers `disable_peer`; after a configurable grace period, `remove_peer` is scheduled.

### 3.2 Secure Multi-Server Provisioning Layer
- **Decoupled Architecture:** Telegram bot never connects to Docker sockets or stores root SSH credentials.
- **Provider Abstraction (`VPNProvisioner`):** Supports `MockProvisioner` for CI/testing/local dev and `SSHCommandProvisioner` for production nodes.
- **Narrow Remote Interface (`vpnctl`):** Remote VPS executes only an audited CLI tool via strict non-root SSH key authorization with restricted `sudoers` rules.
- **Ephemeral Config Handling:** Config private keys are never stored plaintext in PostgreSQL; configs are streamed in-memory to Telegram and discarded.

### 3.3 Support Ticketing System
- Bi-directional ticket bridge between customer chat and admin chat.
- Customers open tickets with messages/attachments; admins reply via message reply or `/reply <code_or_id>`.
- Full audit trails and state tracking (`open`, `waiting_for_admin`, `waiting_for_customer`, `closed`).

### 3.4 Observability, Audit & Operations
- Immutable `audit_events` log for all state transitions, approvals, rejections, extensions, and errors.
- Structured JSON / structlog logging with sensitive data redaction (tokens, SSH keys, receipts, configs).
- Container healthchecks (`/healthz`), admin `/admin` dashboard, and non-destructive peer reconciliation tools.

## 4. Key Non-Functional & Safety Requirements
- **Strict Idempotency:** Double-tapping approval/rejection never generates duplicate peers, subscriptions, or jobs.
- **Zero-Trust Input & Least Privilege:** Numeric Telegram IDs for identity, strict callback query authorization, parameterized shell execution with zero client-controlled string interpolation.
- **Reliable Outbox Pattern:** Background workers poll and lock durable PostgreSQL jobs with exponential backoff and error classification (retryable vs. permanent).
