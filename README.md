# Amrutam Telemedicine Backend

Python 3.12/FastAPI modular backend for identity, verified doctors, scheduling, transactional consultations, encrypted prescriptions and mock payments. PostgreSQL is the deployment authority; Redis/Celery support rate limiting, caching and durable outbox delivery. This repository is a working engineering assignment, with production deployment and performance validation explicitly separated from local results.

## Start locally without Docker

Requires Python 3.12+ and pip. Commands below use an activated virtual environment. Windows activation is `.venv\Scripts\Activate.ps1`; bash uses `source .venv/bin/activate`.

```sh
python -m venv .venv
# Activate the environment, then:
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

With no .env, the explicit development fallback uses `sqlite:///./amrutam.db` and optional Redis. It supports the HTTP workflows and local concurrency tests; PostgreSQL-specific guarantees, distributed limiting, broker jobs and dashboard export require the full stack. No tables are created automatically at server startup: migrations are mandatory.

Swagger: http://127.0.0.1:8000/docs; ReDoc: http://127.0.0.1:8000/redoc; OpenAPI: http://127.0.0.1:8000/openapi.json. Liveness/readiness: `/health/live`, `/health/ready`; metrics: `/metrics`. Generate a static schema with `python -m scripts.export_openapi`.

In a second terminal with the same virtual environment:

```sh
python -m scripts.seed_demo --slots 100
python -m scripts.demo
```

Demo data is synthetic and disabled in production. It creates short-lived patient/doctor/MFA-admin sessions in `artifacts/demo.json`, which is ignored by Git. The demo asserts booking, replay, conflicts, signed payment, automatic confirmation and restricted analytics. Clinical issuance and revisions are exercised by the workflow tests. See [five-minute demo](docs/demo-script.md).

## Full local stack

Requires Docker Engine/Desktop with Compose v2. Copy `.env.example` to `.env` and choose GRAFANA_PASSWORD. The example database URL targets a host-published PostgreSQL for native development; Compose overrides it to its private service hostname.

```sh
docker compose up --build -d
docker compose logs -f api worker beat
docker compose exec api python -m alembic current
```

API binds loopback 8000, Grafana 3000 (`admin` / configured password), Prometheus 9090 and Jaeger 16686. Grafana provisions an application health/booking dashboard. PostgreSQL and Redis are private. Outbox publication runs every five seconds and reconciliation every minute. Notifications are a durable local inbox, not delivered email/SMS. Set OTEL_ENDPOINT to an OTLP HTTP collector when running outside Compose.

For demo scripts inside Compose, scripts are local developer tooling; run the native client against localhost after generating synthetic seed data with the same database, or mount the repository explicitly into a one-off container. A convenient command is `docker compose run --rm -v "${PWD}:/srv/app" api python -m scripts.seed_demo --slots 100`, then native `python -m scripts.demo` uses the generated artifact and matching WEBHOOK_SECRET. On Windows use the equivalent absolute workspace bind path. Do not seed a production environment.

## Tests and checks

```sh
python -m pytest --cov=app --cov-report=term-missing -q
python -m ruff check app tests scripts
python -m ruff format --check app tests scripts
python -m mypy app
python -m alembic check
python -m pip_audit -r requirements.lock
```

The lockfile pins the full resolved Python toolchain, including test tools. Tests cover security boundaries, refresh reuse, MFA, transaction rollback, simultaneous booking/key replay, prescriptions, signed webhooks and worker deduplication. PostgreSQL/Redis checks are skipped unless configured. To run against actual services:

```sh
docker compose exec postgres createdb -U amrutam amrutam_test
docker compose --profile test run --rm tests
```

**Tests erase the database specified by TEST_DATABASE_URL. Use a dedicated disposable test database.** CI uses PostgreSQL/Redis services, migration upgrade/check/downgrade, formatting, lint, mypy, coverage, pip-audit, container build/Trivy and Terraform validation. CI/cloud execution is not inferred from file presence. [Actual verification results](docs/verification-report.md) identify what ran here.

## Configuration

| Variable | Default / purpose |
|---|---|
| ENVIRONMENT | development; production rejects insecure defaults |
| DATABASE_URL | SQLite fallback; deploy with postgresql+psycopg TLS URL |
| REDIS_URL | localhost:6379/0; use authenticated rediss in production |
| REDIS_REQUIRED | false locally; must be true in production |
| JWT_SECRET | development only; independent random ≥32 characters for deployment |
| WEBHOOK_SECRET | mock development secret; independent signing secret for deployment |
| ENCRYPTION_KEY | Fernet key; required in production; back up securely |
| ACCESS_MINUTES / REFRESH_DAYS | 15 / 30 |
| AUTH_RATE_LIMIT | 20 per connecting IP per 60 seconds |
| OTEL_ENDPOINT | optional OTLP HTTP base URL, e.g. http://jaeger:4318 |
| GRAFANA_PASSWORD | required by Compose, no hardcoded default |
| TEST_DATABASE_URL / TEST_REDIS_URL | disposable integration services only |

Generate a Fernet key using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Never rotate a key without a tested re-encryption/multi-key plan. Keep .env, demo credentials, backups and Terraform state out of source control.

## Design and repository

`app/api/v1` contains HTTP adapters; `app/modules` contains domain services/schemas; `app/core` security/config/Redis; `app/db` models, repository and migrations; `app/workers` outbox jobs; `app/observability` telemetry. Tests are under `tests/api`, `tests/unit`, `tests/security` and `tests/integration`; infrastructure under `infra/terraform`, `infra/kubernetes`, `infra/monitoring`; runnable developer tools under `scripts` and `load-tests`.

Booking requires Idempotency-Key and commits reservation, consultation, response, audit, history and outbox atomically. PostgreSQL exclusion/unique constraints protect scheduling. Redis locks are not used for appointment integrity. Medical payloads and credentials use authenticated application encryption; access requires the patient or assigned verified clinician. Admins must use MFA and cannot browse arbitrary medical records.

## Load tests and deployment

Install k6, generate at least 100 fresh synthetic slots and run from the repository root:

```sh
k6 run --summary-export artifacts/k6-summary.json load-tests/scenarios.js
```

The scenario covers search, availability, bookings, detail/history, analytics and contention, reporting p50/p95/p99, throughput and conflicts. Capture Prometheus DB pool/query metrics and container CPU/memory (`docker stats`) concurrently. Tokens expire in 15 minutes; reseed before each run. Load tests target only your own environment. The 100k/day workload, read p95 <200ms, write p95 <500ms and 99.95% availability are design objectives, not established results.

Production references target AWS Mumbai with private EKS, multi-AZ PostgreSQL/Redis, ECR, KMS/Secrets Manager, CloudWatch and backup storage. Kubernetes includes probes/resources, pod security, rolling updates, HPA, workers and a migration job. See [deployment](docs/deployment.md) for validation, missing integrations, approved release and rollback. No cloud resources have been deployed.

## Documentation and limitations

Read [architecture and diagrams](docs/architecture.md), [data model/classification](docs/data-model.md), [API guide](docs/api-guide.md), [threat model](docs/threat-model.md), [security evaluation](docs/security-checklist.md), [backup/recovery](docs/backup-and-recovery.md), [decisions](docs/decisions/0001-modular-monolith.md) and [verification report](docs/verification-report.md).

Real payments, external notifications, account email/phone verification, recurring availability, video consultations, clinical decision support, consent/privacy-rights workflows, managed key rotation and regional recovery are not implemented. Terraform validates locally; Compose/Kubernetes/observability need runtime validation. Production requires independent security/legal review, managed secret injection, least-privilege grants, TLS ingress/network policy, backup drills and measured performance. No regulatory compliance or production readiness is claimed.
