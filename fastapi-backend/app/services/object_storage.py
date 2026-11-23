"""Object storage for uploaded files (RustFS / any S3-compatible store).

Two buckets: ``photos`` (public images, served by the backend at /storage/...)
and ``documents`` (private, served only through signed links).

Methods are synchronous (boto3); call them from async code with
``asyncio.to_thread``. Tests use ``MemoryObjectStorage`` (OBJECT_STORAGE=memory).
"""
import threading
from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings


class ObjectNotFoundError(Exception):
    """The object (or its bucket) does not exist."""


@dataclass
class StoredObject:
    data: bytes
    content_type: str


class ObjectStorage:
    def put(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def get(self, bucket: str, key: str) -> StoredObject:
        raise NotImplementedError

    def exists(self, bucket: str, key: str) -> bool:
        raise NotImplementedError

    def delete(self, bucket: str, key: str) -> None:
        raise NotImplementedError

    def ensure_buckets(self) -> None:
        raise NotImplementedError

    def ping(self) -> None:
        raise NotImplementedError


class MemoryObjectStorage(ObjectStorage):
    """In-process stand-in used by the test suite."""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], StoredObject] = {}
        self._lock = threading.Lock()

    def put(self, bucket, key, data, content_type):
        with self._lock:
            self._objects[(bucket, key)] = StoredObject(bytes(data), content_type)

    def get(self, bucket, key):
        with self._lock:
            try:
                return self._objects[(bucket, key)]
            except KeyError:
                raise ObjectNotFoundError(f"{bucket}/{key}") from None

    def exists(self, bucket, key):
        with self._lock:
            return (bucket, key) in self._objects

    def delete(self, bucket, key):
        with self._lock:
            self._objects.pop((bucket, key), None)

    def ensure_buckets(self):
        return None

    def ping(self):
        return None

    def clear(self) -> None:
        with self._lock:
            self._objects.clear()


class S3ObjectStorage(ObjectStorage):
    def __init__(self, settings: Settings) -> None:
        import boto3
        from botocore.config import Config

        self._buckets = (settings.s3_photos_bucket, settings.s3_documents_bucket)
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(
                s3={"addressing_style": "path"},
                signature_version="s3v4",
                connect_timeout=3,
                read_timeout=30,
                retries={"max_attempts": 2},
            ),
        )

    @staticmethod
    def _is_missing(exc: Exception) -> bool:
        from botocore.exceptions import ClientError

        if not isinstance(exc, ClientError):
            return False
        code = exc.response.get("Error", {}).get("Code", "")
        return code in ("404", "NoSuchKey", "NoSuchBucket", "NotFound")

    def put(self, bucket, key, data, content_type):
        self._client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, bucket, key):
        try:
            obj = self._client.get_object(Bucket=bucket, Key=key)
        except Exception as exc:
            if self._is_missing(exc):
                raise ObjectNotFoundError(f"{bucket}/{key}") from None
            raise
        return StoredObject(obj["Body"].read(), obj.get("ContentType") or "application/octet-stream")

    def exists(self, bucket, key):
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception as exc:
            if self._is_missing(exc):
                return False
            raise

    def delete(self, bucket, key):
        self._client.delete_object(Bucket=bucket, Key=key)

    def ensure_buckets(self):
        for bucket in self._buckets:
            try:
                self._client.head_bucket(Bucket=bucket)
            except Exception as exc:
                if not self._is_missing(exc):
                    raise
                self._client.create_bucket(Bucket=bucket)

    def ping(self):
        for bucket in self._buckets:
            self._client.head_bucket(Bucket=bucket)


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = Settings()
    if settings.object_storage == "memory":
        return MemoryObjectStorage()
    return S3ObjectStorage(settings)


def reset_object_storage() -> None:
    """Forget the cached instance (tests)."""
    get_object_storage.cache_clear()


def photos_bucket() -> str:
    return Settings().s3_photos_bucket


def documents_bucket() -> str:
    return Settings().s3_documents_bucket
