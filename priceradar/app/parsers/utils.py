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

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/24.0 Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 14; Mobile; rv:125.0) Gecko/125.0 Firefox/125.0",
]


def get_random_ua() -> str:
    return random.choice(USER_AGENTS)


_proxy_cycle: itertools.cycle[str] | None = None
_proxy_counter: int = 0


def get_proxy() -> str | None:
    global _proxy_cycle, _proxy_counter

    proxies = settings.proxy_list
    if not proxies:
        return None

    if _proxy_cycle is None:
        _proxy_cycle = itertools.cycle(proxies)

    _proxy_counter += 1
    return next(_proxy_cycle)


def create_http_client(**kwargs: Any) -> httpx.AsyncClient:
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


class ParserError(Exception):
    """Base exception for all parser-related errors."""


class CaptchaError(ParserError):
    pass


class BlockedError(ParserError):
    pass


class NotFoundError(ParserError):
    pass


class ParsingError(ParserError):
    pass


T = TypeVar("T")

_RETRY_DELAYS: tuple[int, ...] = (2, 5, 15)


def retry_request(
    fn: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
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


class RateLimiter:
    """Per-marketplace rate limiter backed by Redis (1 req / 3s)."""

    _KEY_PREFIX: str = "ratelimit:parser:"
    _COOLDOWN_SECONDS: int = 3

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def acquire(self, marketplace: str) -> None:
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
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
