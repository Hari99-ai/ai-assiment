# STRIDE threat model

Assets: credentials and session families, medical records, doctor credentials, money-state records, slots, encryption keys, immutable histories and service availability. Entry points: public REST/Swagger, authenticated REST, payment webhook, broker, migrations, CI/CD and cloud control plane. Trust boundaries: client/ingress, API/database, API/Redis, worker/broker, provider/webhook and operator/cloud.

| STRIDE | Scenario | Implemented mitigation | Residual risk / required action |
|---|---|---|---|
| Spoofing | credential theft, brute force, token replay | Argon2id, 15m JWT, server-side session check, rotation/reuse revocation, TOTP and one-use recovery, Redis rate limiter | add account/device anomaly controls; proxy must preserve trusted source IP |
| Tampering | slot race or overlapping intervals | conditional SQL reservation, transaction, partial unique index; PostgreSQL exclusion | PostgreSQL race/constraint verification required; DBA can bypass controls |
| Tampering | forged/replayed payment event | constant-time HMAC, five-minute timestamp window, amount/currency/reference match, unique event ID + fingerprint | real provider signing and reconciliation contract pending |
| Repudiation | insider changes clinical or money records | transactional audit/history, PostgreSQL append-only triggers, revision versions | DB owners remain powerful; add immutable external archive and access reviews |
| Information disclosure | IDOR/BOLA, support/admin medical browsing | ownership checks on every consultation/prescription, no generic admin medical bypass, bounded public projections | penetration testing and break-glass policy pending |
| Information disclosure | PHI in logs/traces/cache or SQL errors | allowlisted JSON logs, generic validation/errors, encrypted medical fields, public-only caching, bounded metric labels | configure collector sanitization, storage encryption and retention |
| Denial of service | API abuse, huge queries, dependency failure | auth limits, bounded pagination/report windows, 64 KiB streaming body cap including chunked requests, DB deadlines/pool caps, readiness | ingress must apply timeouts and rate-limit all public routes; DDoS controls pending |
| Elevation | self-assigned privileged role or unverified doctor | strict extra-field rejection, server-owned roles, verified workflow, privileged MFA | bootstrap admin custody and MFA recovery procedures need operational controls |
| Tampering | SQL injection | SQLAlchemy bound queries; no user SQL construction | migration operator permissions must be separated |
| Spoofing/tampering | compromised dependencies or CI | locked dependency set, pip-audit/Trivy CI, immutable tags | action/image digests and signed SBOM/artifact provenance before production |
| Information disclosure | SSRF and XSS | no user-supplied outbound URLs; JSON API, nosniff and no raw HTML | future rendering clients must escape strings; ingress CSP policy must permit Swagger |
| Information disclosure | leaked or stolen keys/backups | Fernet library, production secret validation, cloud KMS references, no secrets committed | secret injection/rotation, TLS termination, backup access and restore tests pending |

OWASP API concerns are addressed through object-level authorization, property allowlists, role checks, bounded resource use and endpoint inventory in OpenAPI. This is an engineering threat model, not a completed security assessment. Commission independent review before handling real medical records.
