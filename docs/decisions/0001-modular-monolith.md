# ADR 0001: ACID modular monolith

Accepted. FastAPI modules share one PostgreSQL transaction boundary. A unique slot reservation, scoped idempotency record, medical state, audit and outbox commit together. Redis handles supporting coordination only. This minimizes failure modes in the appointment integrity path. Services can be extracted after profiling and ownership data identify a justified boundary; each extraction must preserve reservation uniqueness and explicit compensation.
