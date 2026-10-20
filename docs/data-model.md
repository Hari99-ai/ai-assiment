# Data model and classification

| Class | Data | Controls |
|---|---|---|
| Public | doctor specialization, fee, experience, verification | bounded public API projections, 30s cache |
| Internal | infrastructure metrics, aggregate counts, event topic | internal network, restricted monitoring |
| Confidential | emails, profiles, payment references, audit actor IDs | authenticated access, encrypted storage, retention approval |
| Highly sensitive | medical reasons, prescriptions, credentials, TOTP secrets, reset tokens | application Fernet encryption, patient/assigned-clinician authorization, audited access |

Users have unique normalized email/optional phone. Public registration sets PATIENT; verification grants DOCTOR. Profiles store only a name and reserved metadata; date of birth is omitted because no implemented workflow requires it. No raw card data is accepted.

Slots have interval/status/version checks. Doctor/start/end index supports scheduling; GiST exclusion on PostgreSQL rejects intersecting non-closed intervals. Bookings have patient-history, doctor-schedule and status indexes, plus a partial unique slot index over booked, confirmed, in-progress and completed states. Cancellation permits a later historical booking attempt for the same slot. Prescription revisions have unique (prescription, version). Refresh token hashes, webhook event IDs, provider references and principal/operation/idempotency keys are unique. Database timestamps are UTC; SQLite loses timezone metadata and the local adapter restores UTC explicitly.

All business writes use explicit commits; services roll back through the request dependency on error. Booking atomicity includes the conditional slot update, idempotency, consultation, history, audit and outbox writes. APIs expose no audit deletion or generic record deletion. Foreign keys restrict destructive cascades.

Retention defaults to a proposed policy requiring legal approval: idempotency keys at least 24h; expired password resets 30 days; expired session hashes 30 additional days for incident review; consumed outbox/inbox 30 days after archival; operational logs 90 days; audit and medical records retained under approved medical/legal schedules and legal holds. Medical/audit deletion is deliberately not automated. Operators must archive immutable audit records outside the database. Backups follow the same approved retention and deletion obligations.

India is the deployment assumption, not a compliance determination. Review the [DPDP Act](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023-1), [official DPDP Rules](https://www.meity.gov.in/digital-personal-data-protection-rules), and [MoHFW telemedicine guidance](https://www.mohfw.gov.in/pdf/Telemedicine.pdf) with counsel, including phased commencement and practitioner-system applicability. Ayurvedic practice may require separate AYUSH guidance. Consent, guardian handling, grievance/contact workflows, data-subject requests, breach response and jurisdiction-specific prescribing rules remain deployment work. GDPR/HIPAA applicability depends on actual users, operators, contracts and geography; no such certification is claimed.
