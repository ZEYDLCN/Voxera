from typing import Protocol, cast

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from voxera.core.config import Settings


class ObjectStorageError(Exception):
    """Raised when an object storage operation fails for a reason other than a missing key."""


class ObjectNotFoundError(ObjectStorageError):
    """Raised when a requested object key does not exist in the bucket."""


class ObjectStorage(Protocol):
    """S3-shaped storage for raw import files. Implemented by `S3ObjectStorage`."""

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...


class S3ObjectStorage:
    """boto3-based object storage client, compatible with AWS S3 and MinIO.

    boto3 is synchronous, so callers on the request path must offload calls to a
    thread (`starlette.concurrency.run_in_threadpool`); the Celery worker calls it
    directly since Celery tasks already run outside the API's event loop.
    """

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.object_storage_bucket
        self._client = boto3.client(
            "s3",
            # Empty/unset -> boto3's default AWS resolution. Real deployments point
            # this at MinIO; leaving it unset also lets moto's mock_aws intercept
            # requests in tests, since it does not recognize arbitrary custom hosts.
            endpoint_url=settings.object_storage_endpoint or None,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key.get_secret_value(),
            config=BotoConfig(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        """Create the configured bucket if it does not already exist. Idempotent."""

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except ClientError as exc:
            raise ObjectStorageError(f"failed to upload object {key!r}") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                raise ObjectNotFoundError(key) from exc
            raise ObjectStorageError(f"failed to download object {key!r}") from exc
        return cast(bytes, response["Body"].read())
