import pytest
from pydantic import ValidationError

from voxera.core.config import Settings


def test_production_rejects_default_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")


def test_test_environment_accepts_explicit_secrets() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        secret_key="test-secret-key",
        object_storage_secret_key="test-storage-secret",
    )

    assert settings.environment == "test"
    assert settings.debug is False

