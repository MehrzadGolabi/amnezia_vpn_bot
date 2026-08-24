# Security Architecture & Threat Model

## 1. Threat Model & Mitigations

| Threat | Impact | Mitigation in System |
|---|---|---|
| Compromised Bot Container | Attacker gains shell in bot container | Container runs as non-root `appuser`. SSH key is limited to `vpn-provisioner` with no sudo rights except `/usr/local/sbin/vpnctl`. Database secrets are protected via environment variables. |
| Malicious Telegram Input | Attacker injects shell characters in order / username / ticket | Strict regex validation (`^[a-zA-Z0-9_-]{1,64}$`) on all peer identifiers passed to Paramiko SSH. ORM parameterized queries across all database repositories. |
| Double Spend / Race Condition | User clicks approve or receipt submission concurrently | Atomic database transactions with row-level locks (`SELECT FOR UPDATE`), outbox idempotency keys, and explicit status guards. |
| Database Leak / Dump Exposure | Database snapshot is leaked or accessed | AmneziaWG private keys and full `.conf` files are never persisted plaintext in the database. Only external IDs and metadata are stored. |
| Flood / DoS on Telegram Bot | Attacker spams `/start` or receipt uploads | `ThrottlingMiddleware` with in-memory sliding window rate-limiting, message size limits, and admin blocklist capabilities (`/block <id>`). |

## 2. Secret Hygiene
- Sensitive configuration variables (`BOT_TOKEN`, `POSTGRES_PASSWORD`, `SSH_PRIVATE_KEY_PASSPHRASE`) are strictly redacted from logs using custom logging formatters.
- SSH keys are mounted read-only (`:ro`) into the worker container.
