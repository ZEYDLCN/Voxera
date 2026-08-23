import boto3
import pytest
from moto import mock_aws

from voxera.core.config import Settings
from voxera.storage.object_storage import ObjectNotFoundError, S3ObjectStorage


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        secret_key="test-secret-key",
        object_storage_secret_key="test-storage-secret",
        object_storage_bucket="voxera-test-bucket",
        # Blank so boto3 falls back to default AWS endpoint resolution, which moto's
        # mock_aws intercepts. A real MinIO endpoint would bypass the mock entirely.
        object_storage_endpoint="",
    )


@mock_aws
def test_put_and_get_bytes_roundtrip(settings: Settings) -> None:
    storage = S3ObjectStorage(settings)
    storage.ensure_bucket()

    storage.put_bytes("imports/example.csv", b"text,rating\nGreat,5\n", content_type="text/csv")

    assert storage.get_bytes("imports/example.csv") == b"text,rating\nGreat,5\n"


@mock_aws
def test_get_bytes_raises_not_found_for_missing_key(settings: Settings) -> None:
    storage = S3ObjectStorage(settings)
    storage.ensure_bucket()

    with pytest.raises(ObjectNotFoundError):
        storage.get_bytes("does/not/exist.csv")


@mock_aws
def test_ensure_bucket_is_idempotent(settings: Settings) -> None:
    storage = S3ObjectStorage(settings)
    storage.ensure_bucket()
    storage.ensure_bucket()  # must not raise on the second call

    client = boto3.client("s3", region_name="us-east-1")
    buckets = {bucket["Name"] for bucket in client.list_buckets()["Buckets"]}
    assert "voxera-test-bucket" in buckets
