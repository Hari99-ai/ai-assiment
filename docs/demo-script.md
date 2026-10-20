# Five-minute demonstration

Prepare a synthetic local database. Run migrations, start the API, then `python -m scripts.seed_demo --slots 100`. Seeded tokens expire in 15 minutes; regenerate the seed shortly before recording. `artifacts/demo.json` contains synthetic bearer credentials: keep the file private and out of the recording. Use Swagger's Authorize dialog, a local environment variable, or the scripted demo. Do not show real credentials.

| Time | Demonstration |
|---|---|
| 0:00–0:30 | Show architecture.md component/sequence diagrams; explain the single ACID booking transaction and outbox. |
| 0:30–1:10 | Swagger register/login as a new patient. Attempt an admin analytics call and show 403. Explain that privileged seed accounts are synthetic and cannot be self-assigned. |
| 1:10–2:00 | Show doctors search/availability and `python -m scripts.demo`. It makes real HTTP calls, books one synthetic slot and processes a signed mock payment. |
| 2:00–2:40 | Run `pytest tests/integration/test_concurrency.py tests/api/test_workflows.py::test_booking_isolation_and_idempotency -q`; show actual results for simultaneous claims and changed idempotency payload. Explain SQLite vs PostgreSQL test environments. |
| 2:40–3:15 | Run `pytest tests/api/test_workflows.py::test_payments_prescriptions -q`. This test advances the synthetic schedule into the active window, starts/completes the consultation with its doctor, issues/revises a prescription, and rejects another patient's access. Explain the time fixture rather than claiming the demo's tomorrow appointment completed early. |
| 3:15–3:45 | Show payment event schema, HMAC verification test, duplicate-delivery test and mock refund path. State clearly that no real money moves. |
| 3:45–4:20 | Show `alembic current`, test coverage report and CI workflow. Only display real command outcomes. |
| 4:20–4:45 | Open /metrics and inspect JSON server logs. If Compose is running, open Grafana 3000, Prometheus 9090 and Jaeger 16686; otherwise explain these are provisioned and not locally verified. |
| 4:45–5:00 | Mention verification-report.md: production load/SLOs, cloud deployment, real notifications/payments and legal review remain pending. |

Run `python -m scripts.demo` once against fresh seed data; subsequent runs target the same occupied slot and correctly conflict, so reseed before repeating. The script asserts the responses and fails on errors. The architecture, demo script and tests are the deliverables; no video recording has been fabricated or generated.
