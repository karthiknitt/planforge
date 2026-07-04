import pytest
from pydantic import ValidationError


def test_settings_requires_internal_auth_secret(monkeypatch):
    monkeypatch.delenv("INTERNAL_AUTH_SECRET", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reads_internal_auth_secret_from_env(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "test-secret-value-0123456789abcdefgh")
    from app.config.settings import Settings

    settings = Settings(_env_file=None)
    assert settings.internal_auth_secret == "test-secret-value-0123456789abcdefgh"


def test_settings_rejects_short_internal_auth_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "too-short")
    from app.config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
