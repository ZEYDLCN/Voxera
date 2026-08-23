from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VOXERA_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Voxera API"
    environment: Environment = "local"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool = True

    secret_key: SecretStr = SecretStr("local-development-key-change-me")
    database_url: str = (
        "postgresql+asyncpg://voxera_app:voxera-app-local@localhost:5432/voxera"
    )
    database_echo: bool = False
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0)
    check_database_readiness: bool = True
    redis_url: str = "redis://localhost:6379/0"

    object_storage_endpoint: str = "http://localhost:9000"
    object_storage_access_key: str = "voxera"
    object_storage_secret_key: SecretStr = SecretStr("voxera-local-secret")
    object_storage_bucket: str = "voxera-raw"

    # Pins which trained model version /analytics/sentiment serves and writes results
    # under. None (the default) disables the sentiment endpoints entirely rather than
    # silently falling back to "whatever was last trained" -- see
    # voxera.ml.sentiment.train for publishing a version.
    sentiment_model_version: str | None = None

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> Self:
        if self.environment == "production":
            if self.debug:
                raise ValueError("debug must be disabled in production")
            if self.secret_key.get_secret_value() == "local-development-key-change-me":
                raise ValueError("VOXERA_SECRET_KEY must be changed in production")
            if self.object_storage_secret_key.get_secret_value() == "voxera-local-secret":
                raise ValueError("object storage credentials must be changed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
