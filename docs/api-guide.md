# API guide

Base path `/api/v1`; Swagger `/docs`, ReDoc `/redoc`, schema `/openapi.json` (also checked in as `docs/openapi.json`). `Authorization: Bearer <access_token>` is required for private operations. Login takes JSON email/password plus optional MFA code; the architecture is bearer-token/OAuth2-compatible but does not implement a full OAuth authorization server or external identity provider.

```http
POST /api/v1/auth/register
Content-Type: application/json

{"email":"patient@example.com","password":"use-a-unique-long-password","full_name":"Example Patient"}
```

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email":"patient@example.com","password":"use-a-unique-long-password"}
```

```http
POST /api/v1/consultations
Authorization: Bearer ACCESS_TOKEN
Idempotency-Key: unique-client-operation-uuid
Content-Type: application/json

{"availability_slot_id":"SLOT_UUID","reason_for_visit":"Patient supplied reason"}
```

Only booking supports the Idempotency-Key contract: principal + booking + key, canonical request fingerprint, durable response after commit, identical replay, 409 on changed payload. Keys are retained for at least 24 hours; clients must never reuse them for a different operation. Payments are idempotent by unique consultation; webhooks by provider event ID. Other write endpoints do not claim idempotency.

Doctor search supports exact specialization, min/max fee, available_after/before; only verified doctors appear in search. Admin verification is `POST /admin/doctors/{id}/verify` with `{"status":"VERIFIED"}` or REJECTED. Admin credential access is audited. Doctor PATCH allows specialization/fee only. A doctor cannot verify themselves. Pending applications are available to their owner through the create response and to administrators through credential/verification endpoints; no public pending-doctor search is provided.

Lists use bounded limit 1..100 (default 20); public doctor/slot/prescription lists use offset 0..10000. Consultation history uses an exclusive UUID cursor in stable UUID order and returns `next_cursor`. UUID order is deterministic, not chronological. Analytics accepts start/end and limits a window to 93 days. All timestamps must include an offset; clients display UTC in their local zone.

Lifecycle: booked → payment-confirmed → clinician start during schedule → clinician complete. Cancellation is available before start; patients need at least two hours' notice. Completion does not automatically issue a prescription. Prescriptions require the assigned verified doctor and an in-progress/completed consultation; revisions append a new encrypted version and preserve history. Medication validation is structural and makes no judgment about clinical appropriateness.

Payment flow: POST `/payments` with consultation_id; GET `/payments/{id}`; POST `/payments/webhooks/mock` with X-Signature. See scripts/demo.py for exact HMAC signing, timestamp and event payload. Only the mock provider is implemented. No card data fields exist. Payment/refund processing may be asynchronous via the outbox.

Errors follow `{"error":{"code":"slot_conflict","request_id":"..."}}`. Common statuses: 401 invalid/missing authentication; 403 authorization/MFA boundary; 404 missing resource; 409 conflict/state mismatch; 422 validation; 429 limiter rejection (`Retry-After: 60`); 503 unavailable dependency. Validation responses omit echoed inputs. Request IDs are server-generated and returned in X-Request-ID. Auth endpoints are limited by a Redis fixed 60-second window per connecting IP; proxies require explicit trusted forwarding configuration. Development Redis-optional mode disables distributed limiting and is unsuitable for production. Version changes preserve v1 contracts or introduce v2.
