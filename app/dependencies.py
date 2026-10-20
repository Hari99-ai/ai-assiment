from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.errors import DomainError, require
from app.db.models import Refresh, User, now
from app.db.repositories import Repository
from app.db.session import get_db
from app.modules.auth import aware

bearer = HTTPBearer(auto_error=False)


def repository(db=Depends(get_db)):
    return Repository(db)


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    repo=Depends(repository),
):
    if credentials is None:
        raise DomainError(401, "authentication_required")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings().jwt_secret,
            algorithms=["HS256"],
            issuer="amrutam",
            audience="amrutam-api",
            options={"require": ["exp", "iat", "sub", "sid", "mfa"]},
        )
        user = repo.get(User, payload["sub"])
        session = repo.get(Refresh, payload["sid"])
        require(
            user.status == "ACTIVE"
            and session.user_id == user.id
            and not session.revoked
            and aware(session.expires_at) > now(),
            "session_revoked",
            401,
        )
        user._mfa_authenticated = bool(payload["mfa"] and session.mfa)
        return user
    except (jwt.InvalidTokenError, KeyError, DomainError):
        raise DomainError(401, "invalid_access_token") from None


def protected_user(user=Depends(current_user)):
    if user.role in {"ADMIN", "SUPPORT"}:
        require(user.mfa_enabled and user._mfa_authenticated, "privileged_mfa_required")
    return user


def admin_user(user=Depends(protected_user)):
    require(user.role == "ADMIN")
    return user
