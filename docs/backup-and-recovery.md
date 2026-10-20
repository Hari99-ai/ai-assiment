# Backup and disaster recovery

Design objectives, not tested guarantees: RPO ≤5 minutes, RTO ≤60 minutes for an AZ outage. RDS reference uses multi-AZ, encrypted storage, 35-day backup retention and PITR; Redis retains seven daily snapshots and AOF locally. Redis is not the authority for appointments. Medical encryption keys must be recoverable separately from data backups or encrypted records cannot be restored.

Local backup (Compose; contains synthetic or sensitive data, restrict access):

```sh
docker compose exec -T postgres pg_dump -U amrutam -d amrutam -Fc > amrutam.dump
docker compose exec -T postgres createdb -U amrutam restore_check
docker compose exec -T postgres pg_restore -U amrutam -d restore_check --no-owner < amrutam.dump
```

Use a shell supporting binary redirection; Windows PowerShell 5 redirects text differently, so run these binary dump commands in bash or use pg_dump's container file output and docker compose cp. A safer Windows path is `docker compose exec postgres pg_dump -U amrutam -d amrutam -Fc -f /tmp/amrutam.dump` followed by `docker compose cp postgres:/tmp/amrutam.dump ./amrutam.dump`. Encrypt before export to backup storage and remove transient copies under an approved handling procedure.

Quarterly drill: provision an isolated private database, restore a recent snapshot/PITR, inject the corresponding historical encryption key under dual control, apply only compatible migrations, compare table counts and reservation uniqueness, decrypt synthetic test records, verify histories and signed session invalidation, then exercise the application smoke suite. Record elapsed restore time and recovered timestamp; calculate observed RTO/RPO. Destroy drill data under the approved policy.

During an incident: stop booking traffic if consistency is uncertain, freeze worker publication, preserve logs/audit evidence, fail over PostgreSQL, restore Redis/broker as needed, run readiness, reconcile unpublished/unconsumed outbox entries, and check stale reservations/refunds. Broker data loss can occur after published markers are committed; reconciliation requeues old unconsumed events after ten minutes. Do not replay a real money operation without provider idempotency.

Regional loss is outside the implemented reference: configure cross-region encrypted snapshot replication, backup key access and private connectivity, document DNS/failover ownership and rehearse a regional restore before asserting a regional recovery objective. Medical and audit retention periods require legal approval and legal-hold handling. No automatic destructive cleanup of clinical records is included.
