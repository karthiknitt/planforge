"""NullPool + a direct (non-pooler) Neon endpoint means a fresh TLS handshake
per request and a hard ceiling on Neon connections."""

from app.db import is_pooled_url


def test_pooler_hostname_is_detected():
    assert is_pooled_url(
        "postgresql+asyncpg://u:p@ep-x-123-pooler.us-east-2.aws.neon.tech/db"
    )


def test_direct_hostname_is_not_pooled():
    assert not is_pooled_url(
        "postgresql+asyncpg://u:p@ep-x-123.us-east-2.aws.neon.tech/db"
    )


def test_local_dev_url_is_not_pooled():
    assert not is_pooled_url("postgresql+asyncpg://planforge@localhost:5432/planforge")
