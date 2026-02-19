"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """PriceRadar application settings."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://priceradar:changeme@db:5432/priceradar"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://priceradar:changeme@db:5432/priceradar"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = "PriceRadarBot"

    # YooKassa
    YUKASSA_SHOP_ID: str = ""
    YUKASSA_SECRET_KEY: str = ""

    # Parsing intervals (seconds)
    PARSE_INTERVAL_FREE: int = 7200
    PARSE_INTERVAL_BASIC: int = 1800
    PARSE_INTERVAL_PRO: int = 900

    # Proxy list (comma-separated)
    PROXY_LIST: str = ""

    # App
    SECRET_KEY: str = "supersecretkey"
    DEBUG: bool = False
    BASE_URL: str = "http://localhost:8000"

    # Limits
    MAX_PARSE_ERRORS: int = 5
    PRICE_HISTORY_RETENTION_DAYS_FREE: int = 7
    PRICE_HISTORY_RETENTION_DAYS_BASIC: int = 30
    PRICE_HISTORY_RETENTION_DAYS_PRO: int = 90

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def proxy_list(self) -> list[str]:
        """Return parsed list of proxy URLs."""
        if not self.PROXY_LIST:
            return []
        return [p.strip() for p in self.PROXY_LIST.split(",") if p.strip()]


settings = Settings()
