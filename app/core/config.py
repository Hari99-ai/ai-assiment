from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./amrutam.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = False
    jwt_secret: str = "development-only-change-this-secret-before-deploying"
    encryption_key: str = ""
    webhook_secret: str = "development-only-webhook-secret"
    access_minutes: int = Field(default=15, ge=1, le=30)
    refresh_days: int = Field(default=30, ge=1, le=90)
    auth_rate_limit: int = Field(default=20, ge=1, le=1000)
    otel_endpoint: str = ""

    @model_validator(mode="after")
    def production(self):
        if self.environment == "production":
            if (
                self.jwt_secret.startswith("development")
                or len(self.jwt_secret) < 32
                or self.webhook_secret.startswith("development")
                or len(self.webhook_secret) < 32
                or self.webhook_secret == self.jwt_secret
                or not self.encryption_key
                or not self.database_url.startswith("postgresql")
                or not self.redis_required
            ):
                raise ValueError("Production requires PostgreSQL, Redis and independent secrets")
            from cryptography.fernet import Fernet

            Fernet(self.encryption_key.encode())
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
