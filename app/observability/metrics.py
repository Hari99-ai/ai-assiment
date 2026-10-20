from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("amrutam_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "amrutam_http_seconds",
    "HTTP latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2, 5),
)
CACHE = Counter("amrutam_cache_total", "Public cache lookups", ["result"])
BOOKING = Counter("amrutam_booking_total", "Booking outcomes", ["result"])
JOBS = Counter("amrutam_jobs_total", "Job outcomes", ["result"])
PAYMENTS = Counter("amrutam_payment_total", "Webhook outcomes", ["result"])
POOL = Gauge("amrutam_db_checked_out", "Database checked-out connections")
QUERY = Histogram("amrutam_db_query_seconds", "Database query latency")
BACKLOG = Gauge("amrutam_outbox_backlog", "Unpublished outbox events")
