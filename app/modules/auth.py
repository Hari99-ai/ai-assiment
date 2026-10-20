import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyotp
from argon2.exceptions import VerificationError
from sqlalchemy import select, update

from app.core.config import settings
from app.core.errors import DomainError, require
from app.core.security import access, digest, opaque, passwords, seal, unseal
from app.db.models import Profile, Refresh, Reset, User, now
from app.db.repositories import Repository
from app.modules.audit import emit, record


def aware(value):
    from datetime import UTC

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class AuthService:
    def __init__(self, repo: Repository):
        self.repo, self.db = repo, repo.db

    def register(self, data):
        user = self.repo.add(
            User(email=str(data.email).lower(), password_hash=passwords.hash(data.password))
        )
        self.repo.add(Profile(user_id=user.id, full_name=data.full_name))
        record(self.db, user.id, "register", "user", user.id)
        self.db.commit()
        return {"id": user.id, "email": user.email, "role": user.role}

    def tokens(self, user, mfa=False, family=None):
        token = opaque()
        row = self.repo.add(
            Refresh(
                user_id=user.id,
                token_hash=digest(token),
                family=family or str(uuid4()),
                mfa=mfa,
                expires_at=now() + timedelta(days=settings().refresh_days),
            )
        )
        return {
            "access_token": access(user.id, row.id, mfa),
            "refresh_token": token,
            "token_type": "bearer",
            "expires_in": settings().access_minutes * 60,
        }

    def mfa_check(self, user, code):
        if not code or not user.mfa_secret:
            return False
        current = int(time.time()) // 30
        totp = pyotp.TOTP(unseal(user.mfa_secret))
        for counter in (current - 1, current, current + 1):
            if counter > user.mfa_counter and totp.verify(
                code, for_time=datetime.fromtimestamp(counter * 30, UTC)
            ):
                claimed = self.db.scalar(
                    update(User)
                    .where(User.id == user.id, User.mfa_counter < counter)
                    .values(mfa_counter=counter)
                    .returning(User.id)
                )
                return bool(claimed)
        hashes = list(user.recovery_hashes)
        if digest(code) in hashes:
            hashes.remove(digest(code))
            claimed = self.db.scalar(
                update(User)
                .where(User.id == user.id, User.recovery_hashes == user.recovery_hashes)
                .values(recovery_hashes=hashes)
                .returning(User.id)
            )
            return bool(claimed)
        return False

    def login(self, data):
        user = self.db.scalar(
            select(User).where(User.email == str(data.email).lower()).with_for_update()
        )
        valid = False
        try:
            valid = passwords.verify(user.password_hash if user else DUMMY_HASH, data.password)
        except VerificationError:
            pass
        if not user or not valid or user.status != "ACTIVE":
            record(
                self.db,
                user.id if user else None,
                "login",
                "user",
                user.id if user else "unknown",
                "failure",
            )
            self.db.commit()
            raise DomainError(401, "invalid_credentials")
        mfa = self.mfa_check(user, data.mfa_code) if user.mfa_enabled else False
        if user.mfa_enabled and not mfa:
            record(self.db, user.id, "login_mfa", "user", user.id, "failure")
            self.db.commit()
            raise DomainError(401, "mfa_required")
        # Privileged users without MFA may enroll, but receive no privileged permissions.
        result = self.tokens(user, mfa)
        record(self.db, user.id, "login", "user", user.id)
        self.db.commit()
        return result

    def refresh(self, token):
        row = self.db.scalar(
            select(Refresh).where(Refresh.token_hash == digest(token)).with_for_update()
        )
        if row is None:
            raise DomainError(401, "invalid_refresh")
        if row.revoked:
            self.db.execute(
                update(Refresh).where(Refresh.family == row.family).values(revoked=True)
            )
            record(self.db, row.user_id, "refresh_reuse", "session", row.id, "failure")
            self.db.commit()
            raise DomainError(401, "refresh_reuse")
        require(aware(row.expires_at) > now(), "expired_refresh", 401)
        claimed = self.db.scalar(
            update(Refresh)
            .where(Refresh.id == row.id, Refresh.revoked.is_(False))
            .values(revoked=True)
            .returning(Refresh.id)
        )
        require(claimed is not None, "refresh_reuse", 401)
        user = self.repo.get(User, row.user_id)
        require(user.status == "ACTIVE", "inactive_user", 401)
        result = self.tokens(user, row.mfa, row.family)
        self.db.commit()
        return result

    def logout(self, user, token):
        row = self.db.scalar(
            select(Refresh).where(Refresh.token_hash == digest(token), Refresh.user_id == user.id)
        )
        if row:
            self.db.execute(
                update(Refresh).where(Refresh.family == row.family).values(revoked=True)
            )
        record(self.db, user.id, "logout", "user", user.id)
        self.db.commit()
        return {"message": "Logged out"}

    def enroll(self, user):
        user = self.repo.get(User, user.id, lock=True)
        require(not user.mfa_enabled, "mfa_already_enabled", 409)
        secret = pyotp.random_base32()
        user.mfa_secret = seal(secret)
        user.mfa_counter = -1
        record(self.db, user.id, "mfa_enroll", "user", user.id)
        self.db.commit()
        return {
            "secret": secret,
            "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
                user.email, issuer_name="Amrutam"
            ),
        }

    def verify(self, user, code):
        user = self.repo.get(User, user.id, lock=True)
        require(not user.mfa_enabled, "mfa_already_enabled", 409)
        require(self.mfa_check(user, code), "invalid_mfa", 401)
        recovery = [opaque()[:24] for _ in range(8)]
        user.mfa_enabled = True
        user.recovery_hashes = [digest(item) for item in recovery]
        self.db.execute(update(Refresh).where(Refresh.user_id == user.id).values(revoked=True))
        record(self.db, user.id, "mfa_enabled", "user", user.id)
        result = self.tokens(user, True)
        self.db.commit()
        return {**result, "recovery_codes": recovery}

    def forgot(self, email):
        user = self.db.scalar(select(User).where(User.email == str(email).lower()))
        if user:
            token = opaque()
            self.repo.add(
                Reset(
                    user_id=user.id,
                    token_hash=digest(token),
                    expires_at=now() + timedelta(minutes=15),
                )
            )
            # Encrypted delivery payload; never return the reset token from this public API.
            emit(self.db, "password_reset", {"recipient": user.id, "secret": seal(token)})
            record(self.db, user.id, "password_forgot", "user", user.id)
            self.db.commit()
        return {"message": "If the account exists, reset instructions will be sent"}

    def reset(self, data):
        row = self.db.scalar(
            select(Reset).where(Reset.token_hash == digest(data.token)).with_for_update()
        )
        if row is None or row.used or aware(row.expires_at) <= now():
            raise DomainError(400, "invalid_reset")
        claimed = self.db.scalar(
            update(Reset)
            .where(Reset.id == row.id, Reset.used.is_(False))
            .values(used=True)
            .returning(Reset.id)
        )
        require(claimed is not None, "invalid_reset", 400)
        user = self.repo.get(User, row.user_id, lock=True)
        user.password_hash = passwords.hash(data.password)
        self.db.execute(update(Reset).where(Reset.user_id == user.id).values(used=True))
        self.db.execute(update(Refresh).where(Refresh.user_id == user.id).values(revoked=True))
        record(self.db, user.id, "password_reset", "user", user.id)
        self.db.commit()
        return {"message": "Password reset"}


DUMMY_HASH = passwords.hash("constant-time-nonexistent-user-password")
