"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class DataSettings:
    """Data collection configuration."""

    request_delay: float = float(_env("AKSHARE_REQUEST_DELAY", "0.2"))
    max_retries: int = int(_env("AKSHARE_MAX_RETRIES", "3"))
    data_dir: Path = _PROJECT_ROOT / "data_store"


@dataclass(frozen=True)
class BacktestSettings:
    """Backtest default parameters."""

    commission: float = float(_env("DEFAULT_COMMISSION", "0.0002"))
    slippage: float = float(_env("DEFAULT_SLIPPAGE", "0.001"))
    benchmark: str = _env("DEFAULT_BENCHMARK", "510300")


@dataclass(frozen=True)
class RedisSettings:
    """Redis connection configuration."""

    url: str = _env("REDIS_URL", "redis://localhost:6379/0")
    default_ttl: int = int(_env("REDIS_DEFAULT_TTL", "3600"))  # 1 hour


DEFAULT_API_SECRET_KEY = "changeme-use-random-string"


@dataclass(frozen=True)
class APISettings:
    """API server configuration."""

    host: str = _env("API_HOST", "0.0.0.0")
    port: int = int(_env("API_PORT", "8000"))
    secret_key: str = _env("API_SECRET_KEY", DEFAULT_API_SECRET_KEY)


@dataclass(frozen=True)
class Settings:
    """Top-level application settings (immutable)."""

    project_root: Path = _PROJECT_ROOT
    data: DataSettings = field(default_factory=DataSettings)
    backtest: BacktestSettings = field(default_factory=BacktestSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)
    api: APISettings = field(default_factory=APISettings)


# Singleton — import this everywhere
settings = Settings()
