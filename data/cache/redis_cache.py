"""Redis cache layer for ETF data.

Caches spot snapshots, factor calculations, and backtest results.
Gracefully degrades: if Redis is unavailable, operations return None/False
and callers fall back to direct computation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from config.settings import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_client() -> redis.Redis | None:
    """Get or create a Redis client. Returns None if connection fails."""
    global _client
    if _client is not None:
        try:
            _client.ping()
            return _client
        except (redis.ConnectionError, redis.TimeoutError):
            _client = None

    try:
        _client = redis.from_url(
            settings.redis.url,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
        )
        _client.ping()
        logger.info("Redis connected: %s", settings.redis.url.split("@")[-1])
        return _client
    except (redis.ConnectionError, redis.TimeoutError, redis.AuthenticationError) as e:
        logger.warning("Redis unavailable: %s — cache disabled", e)
        _client = None
        return None


def cache_get(key: str) -> str | None:
    """Get a value from cache. Returns None on miss or connection failure."""
    client = get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except redis.RedisError as e:
        logger.warning("Redis GET error for %s: %s", key, e)
        return None


def cache_set(key: str, value: str, ttl: int | None = None) -> bool:
    """Set a value in cache. Returns False on failure."""
    client = get_client()
    if client is None:
        return False
    if ttl is None:
        ttl = settings.redis.default_ttl
    try:
        client.setex(key, ttl, value)
        return True
    except redis.RedisError as e:
        logger.warning("Redis SET error for %s: %s", key, e)
        return False


def cache_json_get(key: str) -> Any | None:
    """Get a JSON-serialized value from cache."""
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in cache key %s", key)
        return None


def cache_json_set(key: str, value: Any, ttl: int | None = None) -> bool:
    """Set a JSON-serializable value in cache."""
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        logger.warning("Cannot serialize value for cache key %s: %s", key, e)
        return False
    return cache_set(key, raw, ttl)


def cache_delete(key: str) -> bool:
    """Delete a cache key."""
    client = get_client()
    if client is None:
        return False
    try:
        client.delete(key)
        return True
    except redis.RedisError as e:
        logger.warning("Redis DELETE error for %s: %s", key, e)
        return False


def cache_flush_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns count of deleted keys."""
    client = get_client()
    if client is None:
        return 0
    try:
        keys = list(client.scan_iter(match=pattern, count=100))
        if keys:
            return client.delete(*keys)
        return 0
    except redis.RedisError as e:
        logger.warning("Redis FLUSH error for pattern %s: %s", pattern, e)
        return 0
