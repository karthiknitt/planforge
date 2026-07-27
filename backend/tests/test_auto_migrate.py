"""reconcile_nullable_columns must DROP NOT NULL only when the live DB still
has it set — never touch a DB that already matches the model, never require
a real Postgres to verify the decision."""

import pytest

from app.auto_migrate import reconcile_nullable_columns


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeConn:
    def __init__(self, is_nullable: str):
        self.is_nullable = is_nullable
        self.executed: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append(sql)
        if "information_schema.columns" in sql:
            return _FakeResult((self.is_nullable,))
        return _FakeResult(None)


class _FakeBeginCtx:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakeEngine:
    def __init__(self, conn: _FakeConn):
        self._conn = conn

    def begin(self):
        return _FakeBeginCtx(self._conn)


@pytest.mark.asyncio
async def test_reconcile_drops_not_null_when_db_still_has_it():
    conn = _FakeConn(is_nullable="NO")
    await reconcile_nullable_columns(_FakeEngine(conn))
    assert any("DROP NOT NULL" in sql for sql in conn.executed)


@pytest.mark.asyncio
async def test_reconcile_is_noop_when_already_nullable():
    conn = _FakeConn(is_nullable="YES")
    await reconcile_nullable_columns(_FakeEngine(conn))
    assert not any("DROP NOT NULL" in sql for sql in conn.executed)
