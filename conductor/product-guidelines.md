# Product Guidelines

## 1. User Experience & Telegram UX Principles

### 1.1 Customer Interactions
- **Clarity & Predictability:** Keep customer navigation clear and stateful using Telegram inline keyboards. Every step must clearly communicate what action is expected next.
- **Tone of Voice:** Professional, respectful, reassuring, and concise. Customer communication should clearly explain payment status, pending reviews, and delivery confirmations without technical jargon.
- **Order Tracking & Feedback:**
  - When a receipt is submitted, immediately confirm receipt and inform the customer that an administrator is reviewing their payment.
  - Inform users about expiration milestones with polite advance reminders (e.g., 7 days, 3 days, 1 day prior to expiration).
  - When access expires, clearly explain that the service is disabled and provide renewal instructions.
- **Zero Inline Secrets in Chat:** VPN configuration files (`.vpn` / `.conf`) must be delivered strictly as private Telegram documents (never dumped as raw text in chat messages).
- **Localization Readiness:** Format all user-facing strings through clean localization keys/templates, prepared for English (`en`) and Farsi (`fa`).

### 1.2 Administrator Interactions
- **Actionable Order Cards:** Format incoming receipt cards with comprehensive metadata (Order public code, user numeric ID, username if available, chosen server/plan, price, submitted timestamp, receipt note, and inline buttons).
- **Explicit Admin Confirmation:** Rejection and sensitive actions (disabling peers, manual extensions, retries) must confirm parameters clearly before execution.
- **Idempotent Controls:** Inline buttons (`Approve`, `Reject`, `Retry`) must provide immediate visual feedback (e.g., editing inline button states/text or answering callback queries) to prevent race conditions or double taps.

## 2. Security & Privacy Guardrails

- **Zero-Trust Input & Least Privilege:**
  - Rely exclusively on immutable numeric Telegram IDs (`user_id`), never usernames, for authentication and authorization.
  - Never execute unvalidated shell commands or interpolate user-supplied strings into OS commands.
- **Secret Isolation & Redaction:**
  - Never commit `.env`, private keys, SSH keys, bot tokens, or client credentials.
  - Redact all sensitive fields (tokens, SSH keys, raw VPN configs, receipt payloads) in structured application logs and exception traces.
  - Never store plaintext client private keys in the PostgreSQL database.
  - No direct Docker socket exposure or root SSH credentials within the bot container.
- **Auditability:**
  - Maintain an append-only `audit_events` trail for all order state transitions, admin decisions, peer lifecycle events, and support interactions.

## 3. Operational & Engineering Standards

- **Durable Asynchronous Outbox:** All provisioning, deprovisioning, and notification events must flow through transactional PostgreSQL outbox tables to prevent lost state during crashes or restarts.
- **Graceful Error Handling:** Classify failures into retryable (network hiccups, transient SSH timeout) vs. permanent (invalid config, host unreachable), alerting admins when manual intervention is required.
