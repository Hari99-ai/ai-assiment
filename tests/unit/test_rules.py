from unittest.mock import Mock

import pytest
from hypothesis import given
from hypothesis import strategies as st
from redis.exceptions import ConnectionError

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import seal, unseal
from app.modules.consultations import transition


@given(st.text(max_size=1000))
def test_encryption_roundtrip(value):
    encrypted = seal(value)
    assert unseal(encrypted) == value
    assert encrypted != value


@pytest.mark.parametrize("status", ["COMPLETED", "CANCELLED", "PAYMENT_FAILED", "EXPIRED"])
def test_terminal_state(status):
    with pytest.raises(DomainError):
        transition(Mock(), Mock(status=status), "BOOKED")


def test_rate_limit_and_failure(monkeypatch):
    from app.core import redis

    monkeypatch.setattr(redis, "client", lambda: Mock(eval=Mock(return_value=21)))
    with pytest.raises(DomainError) as exc:
        redis.rate_limit("test")
    assert exc.value.status == 429
    monkeypatch.setattr(redis, "settings", lambda: Settings(redis_required=True))
    monkeypatch.setattr(redis, "client", lambda: Mock(eval=Mock(side_effect=ConnectionError)))
    with pytest.raises(DomainError) as exc:
        redis.rate_limit("test")
    assert exc.value.status == 503


def test_production_secret_validation():
    with pytest.raises(ValueError):
        Settings(environment="production")
