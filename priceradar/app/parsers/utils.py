"""Shared utilities for marketplace parsers.

Provides HTTP helpers, custom exceptions, a retry decorator, and a
Redis-backed rate limiter.
"""

from __future__ import annotations

import asyncio
import functools
import itertools
import random
from typing import Any, Callable, Coroutine, TypeVar

import httpx
import redis.asyncio as aioredis
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# User-Agent rotation
# ---------------------------------------------------------------------------

USER_AGENTS: list[str] = [
    # Desktop – Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Desktop – Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Desktop – Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    # Desktop – Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    # Mobile – Chrome Android
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    # Mobile – Safari iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    # Mobile – Samsung Browser
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/122.0.0.0 Mobile Safari/537.36",
    # Mobile – Firefox Android
    "Mozilla/5.0 (Android 14; Mobile; rv:125.0) Gecko/125.0 Firefox/125.0",
]


def get_random_ua() -> str:
    """Return a random User-Agent string from the pool."""
    return random.choice(USER_AGENTS)


# ---------------------------------------------------------------------------
# Proxy rotation (round-robin)
# ---------------------------------------------------------------------------

_proxy_cycle: itertools.cycle[str] | None = None
_proxy_counter: int = 0


def get_proxy() -> str | None:
    """Return the next proxy URL from *settings.proxy_list* using round-robin.

    Returns ``None`` when no proxies are configured.
    """
    global _proxy_cycle, _proxy_counter

    proxies = settings.proxy_list
    if not proxies:
        return None

    if _proxy_cycle is None:
        _proxy_cycle = itertools.cycle(proxies)

    _proxy_counter += 1
    return next(_proxy_cycle)


# ---------------------------------------------------------------------------
# HTTP client factory
# ---------------------------------------------------------------------------


def create_http_client(**kwargs: Any) -> httpx.AsyncClient:
    """Create a pre-configured :class:`httpx.AsyncClient`.

    The client is set up with:
    * A random User-Agent header.
    * An optional proxy (round-robin from settings).
    * Timeouts: 30 s connect, 60 s read.

    Any extra *kwargs* are forwarded to :class:`httpx.AsyncClient`.
    """
    proxy = get_proxy()
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", get_random_ua())
    headers.setdefault("Accept", "application/json, text/html, */*")
    headers.setdefault("Accept-Language", "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7")

    timeout = httpx.Timeout(connect=30.0, read=60.0, write=30.0, pool=30.0)

    client_kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": timeout,
        "follow_redirects": True,
        **kwargs,
    }

    if proxy:
        client_kwargs.setdefault("proxy", proxy)

    return httpx.AsyncClient(**client_kwargs)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ParserError(Exception):
    """Base exception for all parser-related errors."""


class CaptchaError(ParserError):
    """Raised when the target site returns a CAPTCHA challenge."""


class BlockedError(ParserError):
    """Raised when the request is blocked (e.g. HTTP 403)."""


class NotFoundError(ParserError):
    """Raised when the requested product is not found (HTTP 404 or empty data)."""


class ParsingError(ParserError):
    """Raised when the response body cannot be parsed as expected."""


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

T = TypeVar("T")

_RETRY_DELAYS: tuple[int, ...] = (2, 5, 15)


def retry_request(
    fn: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Async decorator that retries up to 3 times with exponential backoff.

    Backoff delays: 2 s, 5 s, 15 s.

    :class:`NotFoundError` is **never** retried and re-raised immediately.
    All other exceptions trigger a retry.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        last_exc: BaseException | None = None
        for attempt, delay in enumerate((*_RETRY_DELAYS, 0), start=1):
            try:
                return await fn(*args, **kwargs)
            except NotFoundError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt <= len(_RETRY_DELAYS):
                    logger.warning(
                        "retry_request: attempt failed, retrying",
                        attempt=attempt,
                        delay=delay,
                        error=str(exc),
                        function=fn.__qualname__,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "retry_request: all attempts exhausted",
                        attempts=len(_RETRY_DELAYS),
                        error=str(exc),
                        function=fn.__qualname__,
                    )
        raise last_exc  # type: ignore[misc]

    return wrapper


# ---------------------------------------------------------------------------
# Redis-backed rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple per-marketplace rate limiter backed by Redis.

    Enforces at most **1 request per 3 seconds** for each marketplace key
    using ``SETNX`` with a TTL.
    """

    _KEY_PREFIX: str = "ratelimit:parser:"
    _COOLDOWN_SECONDS: int = 3

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Lazily create and return a Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def acquire(self, marketplace: str) -> None:
        """Wait until the rate limit for *marketplace* allows a new request.

        The method sets a Redis key with ``SETNX`` and a TTL of
        :attr:`_COOLDOWN_SECONDS`.  If the key already exists (i.e. another
        request was made recently), the method sleeps and retries until the
        key expires.

        Args:
            marketplace: Marketplace identifier (e.g. ``"wildberries"``).
        """
        r = await self._get_redis()
        key = f"{self._KEY_PREFIX}{marketplace}"

        while True:
            was_set: bool = await r.set(key, "1", nx=True, ex=self._COOLDOWN_SECONDS)  # type: ignore[assignment]
            if was_set:
                logger.debug("rate_limiter: acquired slot", marketplace=marketplace)
                return

            ttl = await r.ttl(key)
            wait = max(ttl, 1) if ttl > 0 else 1
            logger.debug(
                "rate_limiter: slot busy, waiting",
                marketplace=marketplace,
                wait_seconds=wait,
            )
            await asyncio.sleep(wait)

    async def close(self) -> None:
        """Close the underlying Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
