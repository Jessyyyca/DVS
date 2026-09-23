"""API importer interface + rate-limit mixin.

Every importer extends ApiImporter and implements async run.
RateLimitedMixin throttles HTTP calls to a burst window
(per-second or per-minute) with optional rolling hour/day caps.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True)
class RateLimit:
    """Rate-limit policy: burst per window, plus optional hour/day caps.

    burst / window_seconds == 60/60.0 == per minute, 10/1.0 == per second.
    """

    burst: int = 60
    window_seconds: float = 60.0
    max_per_hour: int | None = None
    max_per_day: int | None = None


class RateLimitedMixin:
    """Throttle calls to respect a burst window and rolling hour/day caps."""

    rate_limit: RateLimit = RateLimit()

    def __init__(self, *args, rate_limit: RateLimit | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limit = rate_limit if rate_limit is not None else self.rate_limit
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until the next request is allowed under all configured caps."""
        async with self._lock:
            now = time.monotonic()
            self._trim(now)

            while self._would_exceed(now):
                await asyncio.sleep(self._sleep_until(now))
                now = time.monotonic()
                self._trim(now)

            self._timestamps.append(now)

    def _trim(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= 86400.0:
            self._timestamps.popleft()

    def _would_exceed(self, now: float) -> bool:
        rl = self.rate_limit
        if rl.burst and sum(
            1 for t in self._timestamps if now - t < rl.window_seconds
        ) >= rl.burst:
            return True
        if rl.max_per_hour and sum(
            1 for t in self._timestamps if now - t < 3600.0
        ) >= rl.max_per_hour:
            return True
        if rl.max_per_day and len(self._timestamps) >= rl.max_per_day:
            return True
        return False

    def _sleep_until(self, now: float) -> float:
        rl = self.rate_limit
        waits: list[float] = []
        if rl.burst:
            oldest = next(
                (t for t in self._timestamps if now - t < rl.window_seconds), None
            )
            if oldest is not None:
                waits.append(rl.window_seconds - (now - oldest))
        if rl.max_per_hour:
            oldest = next(
                (t for t in self._timestamps if now - t < 3600.0), None
            )
            if oldest is not None:
                waits.append(3600.0 - (now - oldest))
        if rl.max_per_day and self._timestamps:
            waits.append(86400.0 - (now - self._timestamps[0]))
        return max(waits) if waits else 0.0


class ApiImporter(RateLimitedMixin, ABC):
    """Base class for every API importer.

    Subclasses implement async run (and optionally async setup_schema).
    get_json() throttles, retries on 429 and 5xx, and returns parsed JSON.
    Override api_probe_url() so async test() can hit the API cheaply.
    """

    name: str = ""
    api_base_url: str = ""

    def __init__(
        self,
        pool,
        rate_limit: RateLimit | None = None,
        logger: logging.Logger | None = None,
    ):
        self.pool = pool
        self.logger = logger or logging.getLogger(
            f"dvs.api.{self.__class__.__name__}"
        )
        RateLimitedMixin.__init__(self, rate_limit=rate_limit)

    async def setup_schema(self) -> None:
        """Create or migrate this importer's tables. Override per importer."""

    @abstractmethod
    async def run(self, **kwargs: Any) -> None:
        """Run the full import, persisting to self.pool.

        Named run instead of import because import is a Python keyword
        and async def import(...) would be a SyntaxError.
        """

    def api_probe_url(self) -> str:
        """Return the cheapest URL that proves the API is reachable.

        Default is the configured api_base_url. Subclasses can override.
        """
        return self.api_base_url

    async def test(
        self,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Smoke-test the API and the DB connection.

        Logs INFO on success and raises on any failure. Does not write to
        importer tables (setup_schema is intentionally skipped here so test()
        remains cheap and side-effect-free).
        """
        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession(
                headers={"User-Agent": "DVS/0.1 (test)"}
            )

        try:
            url = self.api_probe_url()
            if not url:
                raise RuntimeError(
                    f"{self.__class__.__name__} has no api_probe_url; "
                    "override the method."
                )

            self.logger.info("probing API at %s", url)
            await self.acquire()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                r.raise_for_status()
                self.logger.info("API reachable, status=%s", r.status)

            self.logger.info("pinging database")
            async with self.pool.acquire() as conn:
                pong = await conn.fetchval("SELECT 1")
                if pong != 1:
                    raise RuntimeError(f"unexpected SELECT 1 result: {pong!r}")
            self.logger.info("database reachable")
        finally:
            if own_session:
                await session.close()

    async def get_json(
        self,
        session: aiohttp.ClientSession,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """GET with rate-limit, retry on 429 and 5xx, returns parsed JSON."""
        await self.acquire()
        for attempt in range(6):
            async with session.get(url, params=params) as r:
                if r.status == 429:
                    wait = float(r.headers.get("Retry-After", "5"))
                    self.logger.warning(
                        "HTTP 429 from %s, sleeping %.1fs (attempt %d/6)",
                        url,
                        wait,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait)
                    continue
                if 500 <= r.status < 600:
                    wait = 2**attempt
                    self.logger.warning(
                        "HTTP %d from %s, sleeping %ds (attempt %d/6)",
                        r.status,
                        url,
                        wait,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return await r.json()
        raise RuntimeError(f"Failed after retries: {url}")