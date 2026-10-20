# Verification report

Environment: Windows, Python 3.12.4, isolated .venv, SQLite local database. Docker, PostgreSQL/Redis servers and k6 were unavailable. Terraform 1.13.5 was downloaded locally for non-deploying validation. No cloud credentials, cloud provisioning, real money movement or external notification delivery were used.

## Actual executions

| Check | Result |
|---|---|
| pytest --cov=app --cov-report=term-missing --cov-report=xml -q | 28 passed, 2 skipped; 93% statement coverage |
| Critical concurrency tests | simultaneous different patients: one 201 and one 409; same key: two identical 201 responses, one stored booking |
| Forced failure after reservation | 500; no committed consultation/idempotency/audit; slot available; retry succeeds |
| Live Uvicorn startup | successful on 127.0.0.1:8000 |
| scripts.demo against live server | passed booking, replay, conflict, signed mock payment, confirmation, admin analytics |
| Alembic upgrade → downgrade base → upgrade; alembic check | passed on SQLite; no metadata drift |
| Ruff lint/format and mypy | passed; mypy checked 33 source files |
| pip check | no broken requirements |
| pip-audit resolved lockfile | no known vulnerabilities in scanned dependency set; rerun after lock changes |
| Terraform fmt/init/validate | passed with AWS provider 5.100.0; no plan/apply performed |
| YAML/JSON artifact parser | parsed 10 deployment/schema artifacts; no runtime semantic claim |
| OpenAPI export | generated docs/openapi.json from actual application routes |

One framework deprecation warning concerns Starlette TestClient's future httpx2 preference; HTTPX-based tests currently pass. Passing dependency scans describe the queried vulnerability database at execution time, not a guarantee of absence of vulnerabilities.

## Definition-of-done evaluation

| Requirement | Evaluation |
|---|---|
| Application starts with documented local instructions | Verified |
| PostgreSQL schema/migrations | Implemented; PostgreSQL execution pending |
| Authentication/RBAC | Verified locally |
| MFA/recovery | Verified locally |
| Doctor availability | Verified locally; PostgreSQL overlap guard pending |
| Transactional booking | Verified locally |
| Concurrent reservation uniqueness | Verified SQLite race tests; PostgreSQL rerun pending |
| Idempotency | Verified replay, concurrency, changed-payload conflict |
| State transitions | Verified lifecycle and invalid transitions |
| Doctor prescription issuance | Verified issuance/revision/history |
| Patient medical-record isolation | Verified including admin/support restrictions |
| Mock payment abstraction | Verified HTTP webhook and worker refund |
| Signature/duplicate webhook checks | Verified |
| Search/filters/pagination | Verified core filters and bounds; production query plans pending |
| Audit | Verified events; PostgreSQL immutability pending |
| Admin analytics authorization | Verified |
| Background jobs | Verified direct task execution/dedup/expiry; Redis broker runtime pending |
| Logs/metrics/traces | JSON logs and Prometheus endpoint verified; OTLP collector export pending |
| Compose startup | Configuration provided; Docker runtime unavailable |
| Automated tests | Passing locally; two service-specific skips |
| CI | Configured; remote GitHub run pending |
| IaC | Terraform provider-schema validation passed; cloud plan/deployment pending |
| OpenAPI | Export and live schema verified |
| Architecture diagrams | Written against implemented models/services |
| Threat model/security checklist | Written; independent assessment pending |
| Backup/recovery | Runbook provided; restore drill pending |
| Load tests | k6 scenarios provided; execution and target-scale measurements pending |
| README | Native setup/migration/test/demo path exercised; Compose path pending |
| Five-minute demo | Script and synthetic setup provided; no video generated |
| Limitations/unverified claims | Documented here and in README |

Production gates: run the PostgreSQL/Redis integration suite and migration round trip; test actual broker crash/redelivery and outbox replay; bring up Compose observability and verify real traces/alerts; validate container image and Kubernetes policies; plan the Terraform configuration in the target account; integrate actual notification/payment providers; implement consent/privacy operations; apply least-privilege database grants; configure TLS/secrets; run restore and incident drills; run representative load tests and review query plans. The 100k/day, latency and 99.95% availability targets remain unverified.
