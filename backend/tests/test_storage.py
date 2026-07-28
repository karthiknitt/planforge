"""Storage seam: R2 when configured, a no-op backend when not.

The no-op path matters — CI and local dev have no R2 credentials and must
still pass without network access.
"""

from io import BytesIO
from types import SimpleNamespace

import pytest

from app.services.storage import NullStorage, R2Storage, build_storage


class _Settings:
    def __init__(self, **kw):
        self.r2_account_id = kw.get("account", "")
        self.r2_access_key_id = kw.get("key", "")
        self.r2_secret_access_key = kw.get("secret", "")
        self.r2_bucket = kw.get("bucket", "")


def test_unconfigured_settings_yield_null_storage():
    assert isinstance(build_storage(_Settings()), NullStorage)


def test_partial_config_yields_null_storage():
    s = _Settings(account="abc", key="k")  # missing secret + bucket
    assert isinstance(build_storage(s), NullStorage)


def test_full_config_yields_r2_storage():
    s = _Settings(account="abc", key="k", secret="s", bucket="b")
    assert isinstance(build_storage(s), R2Storage)


@pytest.mark.asyncio
async def test_null_storage_is_a_safe_no_op():
    st = NullStorage()
    await st.put_bytes("k", b"data", "application/pdf")
    assert await st.get_bytes("k") is None
    assert st.signed_url("k", 900) == ""


def test_r2_endpoint_url_is_account_scoped():
    s = _Settings(account="abc123", key="k", secret="s", bucket="b")
    assert build_storage(s).endpoint_url == "https://abc123.r2.cloudflarestorage.com"


class _NoSuchKey(Exception):
    pass


class _FakeS3:
    """Stands in for the boto3 S3 client — no network, ever."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.exceptions = SimpleNamespace(NoSuchKey=_NoSuchKey)

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803 - boto3 kwargs
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 kwargs
        if (Bucket, Key) not in self.objects:
            raise _NoSuchKey()
        return {"Body": BytesIO(self.objects[(Bucket, Key)][0])}

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803 - boto3 kwargs
        return f"https://signed/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


def _fake_r2() -> tuple[R2Storage, _FakeS3]:
    st = R2Storage("acct", "key", "secret", "bucket")
    fake = _FakeS3()
    st._client = fake
    return st, fake


@pytest.mark.asyncio
async def test_r2_put_then_get_round_trips():
    st, fake = _fake_r2()
    await st.put_bytes("exports/a.pdf", b"%PDF-1.4", "application/pdf")
    assert fake.objects[("bucket", "exports/a.pdf")] == (b"%PDF-1.4", "application/pdf")
    assert await st.get_bytes("exports/a.pdf") == b"%PDF-1.4"


@pytest.mark.asyncio
async def test_r2_get_returns_none_on_missing_key():
    st, _ = _fake_r2()
    assert await st.get_bytes("exports/absent.pdf") is None


def test_r2_signed_url_targets_the_configured_bucket():
    st, _ = _fake_r2()
    assert st.signed_url("exports/a.pdf", 60) == (
        "https://signed/bucket/exports/a.pdf?exp=60"
    )
