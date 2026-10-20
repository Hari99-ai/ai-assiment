import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

from app.core.config import settings

passwords = PasswordHasher()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def opaque() -> str:
    return secrets.token_urlsafe(48)


def cipher() -> Fernet:
    key = settings().encryption_key
    if not key:
        # Development only: deterministic key avoids losing local encrypted records on restart.
        import base64

        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings().jwt_secret.encode()).digest()
        ).decode()
    return Fernet(key.encode())


def seal(value: str) -> str:
    return cipher().encrypt(value.encode()).decode()


def unseal(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()


def access(user_id: str, session_id: str, mfa: bool) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "mfa": mfa,
            "iss": "amrutam",
            "aud": "amrutam-api",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=settings().access_minutes),
        },
        settings().jwt_secret,
        algorithm="HS256",
    )
