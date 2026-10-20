# Deployment

## Local Compose

Copy .env.example to .env and set GRAFANA_PASSWORD. `docker compose up --build -d` starts PostgreSQL and Redis privately, runs Alembic as a one-shot job, then starts API/worker/beat and observability. PostgreSQL and Redis have no host ports. API/monitoring ports bind to loopback. These local secrets are synthetic development defaults. Use `docker compose logs -f api worker beat` for logs.

Create an isolated integration database with `docker compose exec postgres createdb -U amrutam amrutam_test`, then run `docker compose --profile test run --rm tests`. Tests erase and recreate tables **only in the explicitly configured test database**. Never point TEST_DATABASE_URL at an application database. Run once at a time. Windows Celery uses a solo pool for manual local development; the Compose workers run Linux prefork.

## Production reference: AWS Mumbai

AWS ap-south-1 is a concrete reference for a candidate India deployment. EKS, multi-AZ RDS PostgreSQL, private ElastiCache, ECR, KMS, Secrets Manager, CloudWatch and encrypted backup storage demonstrate the resource boundaries. Hosting location alone does not establish data-localization or healthcare compliance. Terraform resources incur costs when applied; no provisioning/deployment is automatic.

```sh
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
# Choose a currently supported EKS version in the configured region.
terraform -chdir=infra/terraform plan -var='kubernetes_version=YOUR_APPROVED_VERSION'
```

Before apply: configure encrypted remote state/locking and least-privilege OIDC roles, review cost and plan in a change process, verify KMS service permissions, workload IAM and restricted network routes. The EKS endpoint is private; operators/CI require approved VPC connectivity. Node group security-group connectivity and RDS privileges must be checked in the deployed account. Set TF_VAR_redis_auth_token from a secret manager and inject the same token in the application's rediss URL; the sensitive Terraform value is retained in state, so encrypted restricted remote state is mandatory. Terraform validates locally but is a reference, not a complete one-command production installer.

Inject `DATABASE_URL` (TLS, non-owner runtime role), `REDIS_URL` (TLS and authentication), independent JWT_SECRET/WEBHOOK_SECRET, Fernet ENCRYPTION_KEY and OTEL_ENDPOINT via a managed secret controller. Never store plaintext secrets in Git. Migration credentials need DDL/extension privileges; runtime credentials must have SELECT/INSERT on immutable audit/history tables and no UPDATE/DELETE/TRUNCATE/DDL rights. Use a narrowly scoped migration owner; restrict all other tables to necessary DML.

Replace image placeholders with immutable commit SHA tags (prefer verified digests), render/review manifests, create namespace/service account and secret references, run the migration job and wait for successful completion **before** rolling API and workers. Namespace uses restricted pod security. API has resource bounds, startup/readiness/liveness probes, HPA, rolling updates and a disruption budget; workers use late acknowledgements and beat has one Recreate replica.

Add a TLS ingress with body-size/time limits, trusted client-IP policy and global rate limits. `/metrics`, admin monitoring and databases must remain private. Apply environment-specific NetworkPolicies for ingress/API, DNS, database, Redis and collector endpoints; external managed-service IP ranges are intentionally not guessed. Configure cluster logging, collectors, metrics-server, worker exporters and alert routing. Account-specific CSI/external secret controllers and ingress are required integrations.

## Release and rollback

CI tests, scans and builds; it never deploys. Require branch protection for quality/infrastructure jobs, reviewed lockfile changes and production environment approval. A separate approved release job should authenticate using OIDC, push the scanned immutable image, run a migration job, then roll workloads. No static cloud credentials are included.

Roll back the application to a prior digest only when the migration is backward compatible. Prefer expand/contract migrations. Do not automatically downgrade production medical schemas: restore a tested backup or ship a reviewed forward fix if destructive changes occurred. Verify health, error rates, latency, conflicts, outbox backlog and payment reconciliation after every rollout. Preserve incident evidence.
