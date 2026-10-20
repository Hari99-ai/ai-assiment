import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException

from app.api.v1.routes import router
from app.core.config import settings
from app.core.errors import DomainError
from app.core.redis import client
from app.db.models import Outbox
from app.db.session import engine, session
from app.modules.audit import request_id
from app.observability.metrics import BACKLOG, BOOKING, LATENCY, PAYMENTS, POOL, QUERY, REQUESTS
from app.observability.tracing import configure

logger = logging.getLogger("amrutam")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(app):
    yield
    engine().dispose()


app = FastAPI(
    title="Amrutam Telemedicine",
    version="1.0.0",
    lifespan=lifespan,
    description="UTC timestamps; Bearer access tokens; mock payments only.",
)
app.include_router(router)
configure(app, engine(), settings().otel_endpoint)


@event.listens_for(engine(), "before_cursor_execute")
def query_start(conn, cursor, statement, parameters, context, executemany):
    context._amrutam_start = time.perf_counter()
    from opentelemetry import trace

    context._amrutam_span = trace.get_tracer("amrutam.db").start_span(
        "database.query", attributes={"db.system.name": conn.dialect.name}
    )


@event.listens_for(engine(), "after_cursor_execute")
def query_end(conn, cursor, statement, parameters, context, executemany):
    QUERY.observe(time.perf_counter() - context._amrutam_start)
    context._amrutam_span.end()


@event.listens_for(engine(), "handle_error")
def query_failed(context):
    execution = context.execution_context
    if execution is not None and hasattr(execution, "_amrutam_span"):
        execution._amrutam_span.end()


def error(status, code):
    headers = {"Retry-After": "60"} if status == 429 else {}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "request_id": request_id.get()}},
        headers=headers,
    )


@app.exception_handler(DomainError)
async def domain_error(request, exc):
    return error(exc.status, exc.code)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return error(409, "resource_conflict")


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return error(exc.status_code, code)


@app.exception_handler(OperationalError)
async def dependency_error(request, exc):
    return error(503, "database_unavailable")


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(request, exc):
    # Pydantic's default details can echo passwords and medical input.
    return error(422, "validation_error")


@app.middleware("http")
async def telemetry(request: Request, call_next):
    correlation = str(uuid4())
    token = request_id.set(correlation)
    start = time.perf_counter()
    try:
        if int(request.headers.get("content-length", "0")) > 65536:
            response = error(413, "payload_too_large")
        else:
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 65536:
                    break
                chunks.append(chunk)
            if size > 65536:
                response = error(413, "payload_too_large")
            else:
                request._body = b"".join(chunks)
                response = await call_next(request)
    except Exception:
        # Do not serialize exception arguments, SQL parameters, or request contents.
        logger.error(json.dumps({"event": "unhandled_error", "request_id": correlation}))
        response = error(500, "internal_error")
    duration = time.perf_counter() - start
    route = getattr(request.scope.get("route"), "path", "unmatched")
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(duration)
    if route == "/api/v1/consultations" and request.method == "POST":
        BOOKING.labels(
            "success"
            if response.status_code == 201
            else "conflict"
            if response.status_code == 409
            else "error"
        ).inc()
    if route == "/api/v1/payments/webhooks/mock":
        PAYMENTS.labels("success" if response.status_code == 200 else "failure").inc()
    from opentelemetry import trace

    span = trace.get_current_span().get_span_context()
    logger.info(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "severity": "INFO",
                "request_id": correlation,
                "trace_id": format(span.trace_id, "032x"),
                "method": request.method,
                "route": route,
                "status": response.status_code,
                "latency_ms": round(duration * 1000, 2),
            }
        )
    )
    response.headers.update(
        {
            "X-Request-ID": correlation,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }
    )
    if settings().environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    request_id.reset(token)
    return response


@app.get("/health/live", tags=["Operations"])
def live():
    return {"status": "live"}


@app.get("/health/ready", tags=["Operations"])
def ready():
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        if settings().redis_required:
            client().ping()
        return {"status": "ready"}
    except Exception:
        return error(503, "dependency_unavailable")


@app.get("/metrics", include_in_schema=False)
def metrics():
    pool = engine().pool
    if hasattr(pool, "checkedout"):
        POOL.set(pool.checkedout())
    try:
        with session() as db:
            BACKLOG.set(
                db.scalar(
                    select(func.count()).select_from(Outbox).where(Outbox.published_at.is_(None))
                )
            )
    except Exception:
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
