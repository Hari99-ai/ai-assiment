from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import DomainError


@lru_cache
def client():
    return Redis.from_url(
        settings().redis_url, decode_responses=True, socket_connect_timeout=0.3, socket_timeout=0.5
    )


RATE_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


def rate_limit(identity):
    from app.core.security import digest

    try:
        count = client().eval(RATE_SCRIPT, 1, "auth-rate:" + digest(identity), 60)
        if int(count) > settings().auth_rate_limit:
            raise DomainError(429, "rate_limited")
    except RedisError:
        if settings().redis_required:
            raise DomainError(503, "rate_limiter_unavailable") from None
        # Explicit development mode only; tests cover production fail-closed behavior.


def cached_public(key, producer):
    """Immutable public profile projection; 30s bounded staleness. Never caches slots."""
    import json

    from app.observability.metrics import CACHE

    try:
        value = client().get(key)
        if value:
            CACHE.labels("hit").inc()
            return json.loads(value)
    except RedisError:
        pass
    CACHE.labels("miss").inc()
    value = producer()
    try:
        client().setex(key, 30, json.dumps(value))
    except RedisError:
        pass
    return value
