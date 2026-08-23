import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voxera.api.app import create_app
from voxera.core.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        secret_key="test-secret-key",
        object_storage_secret_key="test-storage-secret",
        check_database_readiness=False,
    )


@pytest.fixture
def app(test_settings: Settings) -> FastAPI:
    return create_app(test_settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
