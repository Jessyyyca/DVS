"""Tests for the importer-level async test() and db.ping()."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import pytest

from dvs.api.base import ApiImporter, RateLimit
from dvs.db import ping

from ._fakepg import make_pool


class _StubSession:
    """Minimal aiohttp.ClientSession substitute for test()."""

    def __init__(self, *, ok: bool = True):
        self.ok = ok
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, *, params=None, **_more):
        self.calls.append((url, params))
        return _StubGet(self.ok)


class _StubGet:
    def __init__(self, ok: bool):
        self._resp = _FakeResponse(ok)

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return None


class _FakeResponse:
    def __init__(self, ok: bool):
        self.status = 200 if ok else 500

    def raise_for_status(self):
        if not 200 <= self.status < 300:
            raise RuntimeError(f"status {self.status}")


class _DummyImporter(ApiImporter):
    name = "dummy"
    api_base_url = "https://example.test/"

    async def setup_schema(self) -> None:  # pragma: no cover
        pass

    async def run(self, **kwargs) -> None:  # pragma: no cover
        pass


def _rate_limit() -> RateLimit:
    return RateLimit(burst=1000, window_seconds=1.0)


@pytest.mark.asyncio
async def test_db_ping_succeeds_with_fake_pool() -> None:
    pool = make_pool()
    await ping(pool)


@pytest.mark.asyncio
async def test_db_ping_fails_if_select1_returns_wrong_value() -> None:
    pool = make_pool()

    async def bad_fetchval(query: str, *args):
        return 99  # not 1

    # We patch the pool's connection class via a custom pool wrapper.
    class BadConn:
        def __init__(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def fetchval(self, query, *args):
            return 99

    class BadPool:
        @asynccontextmanager
        async def acquire(self):
            yield BadConn()

    with pytest.raises(RuntimeError):
        await ping(BadPool())


@pytest.mark.asyncio
async def test_importer_test_succeeds_when_api_and_db_ok() -> None:
    pool = make_pool()
    imp = _DummyImporter(pool, rate_limit=_rate_limit())
    session = _StubSession(ok=True)
    await imp.test(session=session)  # type: ignore[arg-type]
    assert len(session.calls) == 1
    assert session.calls[0][0] == "https://example.test/"


@pytest.mark.asyncio
async def test_importer_test_fails_when_api_returns_5xx() -> None:
    pool = make_pool()
    imp = _DummyImporter(pool, rate_limit=_rate_limit())
    session = _StubSession(ok=False)
    with pytest.raises(RuntimeError):
        await imp.test(session=session)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_importer_test_logs_at_info_level(caplog) -> None:
    pool = make_pool()
    imp = _DummyImporter(
        pool,
        rate_limit=_rate_limit(),
        logger=logging.getLogger("dvs.test.dummy"),
    )
    session = _StubSession(ok=True)
    with caplog.at_level(logging.INFO, logger="dvs.test.dummy"):
        await imp.test(session=session)  # type: ignore[arg-type]
    messages = [r.message for r in caplog.records]
    assert any("probing API" in m for m in messages)
    assert any("API reachable" in m for m in messages)
    assert any("pinging database" in m for m in messages)
    assert any("database reachable" in m for m in messages)


@pytest.mark.asyncio
async def test_importer_without_api_probe_url_raises() -> None:
    class _NoApi(ApiImporter):
        name = "noapi"
        # intentionally no api_base_url

        async def setup_schema(self) -> None:  # pragma: no cover
            pass

        async def run(self, **kwargs) -> None:  # pragma: no cover
            pass

    pool = make_pool()
    imp = _NoApi(pool, rate_limit=_rate_limit())
    with pytest.raises(RuntimeError, match="api_probe_url"):
        await imp.test()


@pytest.mark.asyncio
async def test_importer_default_logger_name_per_class() -> None:
    pool = make_pool()
    imp = _DummyImporter(pool, rate_limit=_rate_limit())
    assert imp.logger.name == "dvs.api._DummyImporter"


@pytest.mark.asyncio
async def test_importer_accepts_injected_logger() -> None:
    pool = make_pool()
    custom = logging.getLogger("dvs.custom")
    imp = _DummyImporter(pool, rate_limit=_rate_limit(), logger=custom)
    assert imp.logger is custom


def test_rate_limit_dataclass_is_immutable() -> None:
    rl = RateLimit(burst=10, window_seconds=1.0)
    with pytest.raises(Exception):
        rl.burst = 20  # type: ignore[misc]