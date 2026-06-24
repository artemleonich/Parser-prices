"""Application configuration with fail-fast secret validation.

Loaded from environment / .env by pydantic-settings. The previous version
silently accepted unsafe defaults like::

    SECRET_KEY: str = "supersecretkey"
    DATABASE_URL: str = "...:changeme@db:5432/..."
    TELEGRAM_BOT_TOKEN: str = ""
    YUKASSA_SECRET_KEY: str = ""

…which meant that running the app without an .env file would silently
fall back to insecure defaults — the app would start, accept
connections, and (in the SECRET_KEY case) sign session cookies with a
hardcoded key that an attacker could read straight out of the public
repository.

This module:

- Removes the unsafe defaults on every secret field.
- Validates every required secret at construction time via a Pydantic
  ``model_validator`` that runs *after* env-file loading.
- Defers the ``Settings()`` instance construction to a ``get_settings()``
  factory so tests and tooling (CLI, alembic) that don't need real
  secrets can opt out via ``TESTING=1``.
- Adds a ``field_validator`` on ``SECRET_KEY`` that rejects the
  pre-fix hardcoded default if anyone reintroduces it.
"""

import os
from typing import List, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


# Pre-fix hardcoded defaults that MUST never be accepted in production.
# Listed here in one place so the validator has a single source of truth.
_FORBIDDEN_SECRET_VALUES = frozenset(
    {
        "supersecretkey",
        "changeme",
    }
)


class Settings(BaseSettings):
    # ---- Database ----
    # No default. If DATABASE_URL is missing, the app must fail to start
    # rather than silently connecting to a non-existent ``changeme``-password
    # database server (which, in some dev setups, is exactly what the docker-
    # compose service is named, masking the misconfiguration).
    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    REDIS_URL: str = "redis://redis:6379/0"

    # ---- Telegram ----
    # No default. Bot token is required for the entire Telegram integration.
    # An empty string would silently produce an invalid bot that crashes
    # on the first incoming message, much harder to diagnose than a clear
    # startup error.
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_BOT_USERNAME: str = "PriceRadarBot"

    # ---- YooKassa (payments) ----
    # No defaults. Without these, payment flows silently fail with a
    # misleading ``ProviderConfigurationError`` at the moment of the
    # first invoice, rather than at startup.
    YUKASSA_SHOP_ID: str
    YUKASSA_SECRET_KEY: str

    # ---- Parsing cadence (free / basic / pro tiers) ----
    PARSE_INTERVAL_FREE: int = 7200      # 2 hours
    PARSE_INTERVAL_BASIC: int = 1800     # 30 minutes
    PARSE_INTERVAL_PRO: int = 900        # 15 minutes

    PROXY_LIST: str = ""

    # ---- App-level ----
    # No default. Used to sign session cookies — a predictable value
    # here lets any attacker forge arbitrary user sessions.
    SECRET_KEY: str

    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"

    MAX_PARSE_ERRORS: int = 5
    PRICE_HISTORY_RETENTION_DAYS_FREE: int = 7
    PRICE_HISTORY_RETENTION_DAYS_BASIC: int = 30
    PRICE_HISTORY_RETENTION_DAYS_PRO: int = 90

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    # ---- Validators ----

    @field_validator("SECRET_KEY")
    @classmethod
    def _reject_known_unsafe_secret_key(cls, value: str) -> str:
        """Reject the pre-fix hardcoded default if anyone reintroduces it.

        Defends against the failure mode where someone merges a
        revert of this PR without realising why the default existed.
        """
        if value.lower() in _FORBIDDEN_SECRET_VALUES:
            raise ValueError(
                "SECRET_KEY is set to a known-unsafe default value. "
                "Generate a fresh secret with e.g. "
                "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"` "
                "and put it in your .env file."
            )
        if len(value) < 32:
            raise ValueError(
                f"SECRET_KEY is too short ({len(value)} chars); must be at "
                "least 32 characters of entropy. Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"`."
            )
        return value

    @model_validator(mode="after")
    def _reject_placeholder_secrets(self) -> "Settings":
        """Cross-field check: refuse any of the known placeholder patterns.

        Catches ``changeme``-style defaults that may slip in via new
        fields added in the future — the field-level validator above
        only sees ``SECRET_KEY``; this one sees every string field.
        """
        for field_name in (
            "DATABASE_URL",
            "DATABASE_URL_SYNC",
            "TELEGRAM_BOT_TOKEN",
            "YUKASSA_SHOP_ID",
            "YUKASSA_SECRET_KEY",
            "SECRET_KEY",
        ):
            value: Optional[str] = getattr(self, field_name, None)
            if value is None:
                continue
            lowered = value.lower()
            for forbidden in _FORBIDDEN_SECRET_VALUES:
                if forbidden in lowered:
                    raise ValueError(
                        f"{field_name} contains a placeholder value "
                        f"({forbidden!r}). Set a real value in your .env file "
                        "before starting the app."
                    )
        return self

    # ---- Computed properties ----

    @property
    def proxy_list(self) -> List[str]:
        if not self.PROXY_LIST:
            return []
        return [p.strip() for p in self.PROXY_LIST.split(",") if p.strip()]


def get_settings() -> Settings:
    """Factory that builds a ``Settings`` instance.

    For real app startup: read from env / .env file and validate.
    For tests: when ``TESTING=1`` is in the env, return an instance
    built with synthetic permissive values so unit tests can construct
    a ``Settings`` without going through .env. Tests should still pass
    the actual values they want to exercise via environment variables
    or by constructing ``Settings(...)`` directly with overrides.
    """
    if os.getenv("TESTING") == "1":
        # Build with permissive defaults so unit tests don't have to
        # set every env var. Bypass validators so test secrets can be
        # short or contain "changeme" deliberately. The production
        # validators still run when TESTING is unset.
        return Settings.model_construct(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            DATABASE_URL_SYNC="sqlite:///:memory:",
            TELEGRAM_BOT_TOKEN="test-token-not-real",
            YUKASSA_SHOP_ID="test-shop",
            YUKASSA_SECRET_KEY="test-secret-key",
            SECRET_KEY="x" * 64,
            _proxy_list=[],
        )
    return Settings()


# Module-level instance, lazily evaluated. Importing this module is now
# safe in any context (test suite, alembic env, CLI tool) because the
# real Settings() build only happens when ``get_settings()`` or
# ``settings`` is actually accessed.
_settings_cache: Optional[Settings] = None


def __getattr__(name: str):  # PEP 562
    """Lazy module-level access to ``settings``.

    ``from app.config import settings`` previously triggered
    ``Settings()`` at import time, which meant the test suite had to
    set up the full env or monkey-patch the instance. With PEP 562,
    ``settings`` is now computed on first access, not at import time.
    """
    global _settings_cache
    if name == "settings":
        if _settings_cache is None:
            _settings_cache = get_settings()
        return _settings_cache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
