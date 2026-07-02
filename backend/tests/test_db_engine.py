"""Tests for database engine configuration and NullPool toggle."""

from sqlalchemy.pool import NullPool

from app.db import build_engine_kwargs


def test_build_engine_kwargs_default_has_no_poolclass():
    kwargs = build_engine_kwargs(use_nullpool=False)
    assert kwargs == {"echo": False}


def test_build_engine_kwargs_nullpool_enabled():
    kwargs = build_engine_kwargs(use_nullpool=True)
    assert kwargs["poolclass"] is NullPool
    assert kwargs["echo"] is False
