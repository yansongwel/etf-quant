"""Tests for Redis cache layer — uses mocked Redis to avoid real connection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data.cache import redis_cache


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level client between tests."""
    redis_cache._client = None
    yield
    redis_cache._client = None


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    client = MagicMock()
    client.ping.return_value = True
    return client


class TestGetClient:
    @patch("data.cache.redis_cache.redis.from_url")
    def test_creates_client_on_first_call(self, mock_from_url, mock_redis):
        mock_from_url.return_value = mock_redis
        result = redis_cache.get_client()
        assert result is mock_redis
        mock_redis.ping.assert_called()

    @patch("data.cache.redis_cache.redis.from_url")
    def test_reuses_existing_client(self, mock_from_url, mock_redis):
        mock_from_url.return_value = mock_redis
        redis_cache.get_client()
        redis_cache.get_client()
        # from_url should only be called once
        mock_from_url.assert_called_once()

    @patch("data.cache.redis_cache.redis.from_url")
    def test_returns_none_on_connection_error(self, mock_from_url):
        import redis

        mock_from_url.side_effect = redis.ConnectionError("refused")
        result = redis_cache.get_client()
        assert result is None

    @patch("data.cache.redis_cache.redis.from_url")
    def test_existing_client_ping_fails_reconnects(self, mock_from_url, mock_redis):
        """Lines 30-31: existing client ping raises ConnectionError, resets _client."""
        import redis as _redis

        stale_client = MagicMock()
        stale_client.ping.side_effect = _redis.ConnectionError("lost")
        redis_cache._client = stale_client

        mock_from_url.return_value = mock_redis
        result = redis_cache.get_client()
        assert result is mock_redis
        mock_from_url.assert_called_once()

    @patch("data.cache.redis_cache.redis.from_url")
    def test_existing_client_ping_timeout_reconnects(self, mock_from_url, mock_redis):
        """Lines 30-31: existing client ping raises TimeoutError, resets _client."""
        import redis as _redis

        stale_client = MagicMock()
        stale_client.ping.side_effect = _redis.TimeoutError("timeout")
        redis_cache._client = stale_client

        mock_from_url.return_value = mock_redis
        result = redis_cache.get_client()
        assert result is mock_redis


class TestCacheGetSet:
    @patch("data.cache.redis_cache.get_client")
    def test_cache_set_and_get(self, mock_get_client, mock_redis):
        mock_get_client.return_value = mock_redis
        mock_redis.get.return_value = "hello"

        assert redis_cache.cache_set("key", "hello") is True
        mock_redis.setex.assert_called_once()

        result = redis_cache.cache_get("key")
        assert result == "hello"

    @patch("data.cache.redis_cache.get_client")
    def test_cache_get_returns_none_when_no_redis(self, mock_get_client):
        mock_get_client.return_value = None
        assert redis_cache.cache_get("key") is None

    @patch("data.cache.redis_cache.get_client")
    def test_cache_set_returns_false_when_no_redis(self, mock_get_client):
        mock_get_client.return_value = None
        assert redis_cache.cache_set("key", "val") is False

    @patch("data.cache.redis_cache.get_client")
    def test_cache_get_redis_error(self, mock_get_client, mock_redis):
        """Lines 56-58: RedisError during client.get()."""
        import redis as _redis

        mock_get_client.return_value = mock_redis
        mock_redis.get.side_effect = _redis.RedisError("read error")
        result = redis_cache.cache_get("key")
        assert result is None

    @patch("data.cache.redis_cache.get_client")
    def test_cache_set_redis_error(self, mock_get_client, mock_redis):
        """Lines 71-73: RedisError during client.setex()."""
        import redis as _redis

        mock_get_client.return_value = mock_redis
        mock_redis.setex.side_effect = _redis.RedisError("write error")
        result = redis_cache.cache_set("key", "val", ttl=60)
        assert result is False


class TestCacheJSON:
    @patch("data.cache.redis_cache.get_client")
    def test_json_roundtrip(self, mock_get_client, mock_redis):
        mock_get_client.return_value = mock_redis
        data = {"symbol": "510300", "price": 3.82}

        redis_cache.cache_json_set("etf:510300", data)
        mock_redis.setex.assert_called_once()

        # Simulate reading back
        import json

        mock_redis.get.return_value = json.dumps(data)
        result = redis_cache.cache_json_get("etf:510300")
        assert result == data

    @patch("data.cache.redis_cache.get_client")
    def test_json_get_invalid_json(self, mock_get_client, mock_redis):
        mock_get_client.return_value = mock_redis
        mock_redis.get.return_value = "not-json{"
        result = redis_cache.cache_json_get("bad_key")
        assert result is None

    @patch("data.cache.redis_cache.cache_get")
    def test_json_get_returns_none_when_cache_miss(self, mock_cache_get):
        """Line 80: cache_get returns None, cache_json_get returns None."""
        mock_cache_get.return_value = None
        result = redis_cache.cache_json_get("missing_key")
        assert result is None

    @patch("data.cache.redis_cache.cache_set")
    def test_json_set_serialization_error(self, mock_cache_set):
        """Lines 92-94: TypeError/ValueError during json.dumps."""

        # Create an object that json.dumps cannot serialize even with default=str
        class Unserializable:
            def __str__(self):
                raise ValueError("cannot convert")

        result = redis_cache.cache_json_set("key", Unserializable())
        assert result is False
        mock_cache_set.assert_not_called()


class TestCacheDelete:
    @patch("data.cache.redis_cache.get_client")
    def test_delete(self, mock_get_client, mock_redis):
        mock_get_client.return_value = mock_redis
        assert redis_cache.cache_delete("key") is True
        mock_redis.delete.assert_called_once_with("key")

    @patch("data.cache.redis_cache.get_client")
    def test_delete_returns_false_when_no_redis(self, mock_get_client):
        """Line 102: cache_delete returns False when client is None."""
        mock_get_client.return_value = None
        assert redis_cache.cache_delete("key") is False

    @patch("data.cache.redis_cache.get_client")
    def test_delete_redis_error(self, mock_get_client, mock_redis):
        """Lines 106-108: RedisError during client.delete()."""
        import redis as _redis

        mock_get_client.return_value = mock_redis
        mock_redis.delete.side_effect = _redis.RedisError("delete error")
        assert redis_cache.cache_delete("key") is False

    @patch("data.cache.redis_cache.get_client")
    def test_flush_pattern(self, mock_get_client, mock_redis):
        mock_get_client.return_value = mock_redis
        mock_redis.scan_iter.return_value = ["etf:1", "etf:2"]
        mock_redis.delete.return_value = 2

        count = redis_cache.cache_flush_pattern("etf:*")
        assert count == 2

    @patch("data.cache.redis_cache.get_client")
    def test_flush_pattern_returns_zero_when_no_redis(self, mock_get_client):
        """Line 115: cache_flush_pattern returns 0 when client is None."""
        mock_get_client.return_value = None
        assert redis_cache.cache_flush_pattern("etf:*") == 0

    @patch("data.cache.redis_cache.get_client")
    def test_flush_pattern_no_matching_keys(self, mock_get_client, mock_redis):
        """Line 120: scan_iter returns empty list, returns 0."""
        mock_get_client.return_value = mock_redis
        mock_redis.scan_iter.return_value = []
        assert redis_cache.cache_flush_pattern("nonexistent:*") == 0

    @patch("data.cache.redis_cache.get_client")
    def test_flush_pattern_redis_error(self, mock_get_client, mock_redis):
        """Lines 121-123: RedisError during scan_iter/delete."""
        import redis as _redis

        mock_get_client.return_value = mock_redis
        mock_redis.scan_iter.side_effect = _redis.RedisError("scan error")
        assert redis_cache.cache_flush_pattern("etf:*") == 0
