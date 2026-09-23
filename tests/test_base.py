"""Tests for the rate-limit mixin (no network, no DB)."""

from __future__ import annotations

import asyncio
import time

import pytest

from dvs.api.base import RateLimit, RateLimitedMixin


class _Stub(RateLimitedMixin):
    """Minimal host class for the mixin (no DB / network deps)."""

    def __init__(self, rate_limit: RateLimit) -> None:
        super().__init__(rate_limit=rate_limit)


@pytest.mark.asyncio
async def test_no_wait_when_under_burst_cap() -> None:
    c = _Stub(RateLimit(burst=100, window_seconds=60.0))
    start = time.monotonic()
    for _ in range(10):
        await c.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5
    assert len(c._timestamps) == 10


@pytest.mark.asyncio
async def test_burst_cap_waits_for_window() -> None:
    # 5 requests per 0.2s -> 10 sequential acquires must wait for the
    # window to age out before the 6th can proceed (>= 0.15s total).
    c = _Stub(RateLimit(burst=5, window_seconds=0.2))
    start = time.monotonic()
    for _ in range(10):
        await c.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15, f"throttle did not engage, elapsed={elapsed:.3f}s"
    assert len(c._timestamps) == 10


@pytest.mark.asyncio
async def test_max_per_hour_blocks_extra_calls() -> None:
    # burst is generous, but the hourly cap kicks in after 3 calls
    c = _Stub(RateLimit(burst=1000, window_seconds=1.0, max_per_hour=3))
    # First three under cap.
    await c.acquire()
    await c.acquire()
    await c.acquire()
    # Patch sleep so the 4th call returns quickly: pretend an hour passed.
    sleeps: list[float] = []
    orig_sleep = asyncio.sleep

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)
        if s >= 60:
            # Drop the oldest timestamp; mixin will see the cap cleared.
            c._timestamps.popleft()
            await orig_sleep(0)

    asyncio.sleep = fake_sleep  # type: ignore[assignment]
    try:
        await c.acquire()
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]
    assert sleeps, "expected at least one throttle sleep"
    assert any(s >= 60 for s in sleeps)


@pytest.mark.asyncio
async def test_max_per_day_blocks_extra_calls() -> None:
    c = _Stub(RateLimit(burst=1000, window_seconds=1.0, max_per_day=2))
    # Two acquisitions should succeed immediately.
    await c.acquire()
    await c.acquire()
    # Third should not return without sleeping an entire day.
    # Patch the sleep so we don't actually wait 86400s.
    sleeps: list[float] = []
    orig_sleep = asyncio.sleep

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)
        if s >= 60:
            # Pretend a day passed: drop the timestamp.
            c._timestamps.popleft()
            await orig_sleep(0)

    asyncio.sleep = fake_sleep  # type: ignore[assignment]
    try:
        await c.acquire()
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]
    assert sleeps, "expected at least one throttle sleep"
    assert any(s >= 60 for s in sleeps)


@pytest.mark.asyncio
async def test_acquire_is_serializable() -> None:
    c = _Stub(RateLimit(burst=5, window_seconds=0.1))
    # Fire 20 acquires concurrently; the lock should still produce <= burst/window rate.
    await asyncio.gather(*(c.acquire() for _ in range(20)))
    assert len(c._timestamps) == 20
    # First 5 timestamps must be within the burst window of each other.
    head = list(c._timestamps)[:5]
    assert max(head) - min(head) < 0.5