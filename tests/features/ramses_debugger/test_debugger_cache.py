"""Tests for debugger_cache module."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ramses_extras.features.ramses_debugger.debugger_cache import (
    CacheEntry,
    DebuggerCache,
    freeze_for_key,
)


class TestFreezeForKey:
    """Test the freeze_for_key function."""

    def test_freeze_none(self):
        """Test freezing None value."""
        assert freeze_for_key(None) is None

    def test_freeze_primitives(self):
        """Test freezing primitive types."""
        assert freeze_for_key("string") == "string"
        assert freeze_for_key(42) == 42
        assert freeze_for_key(3.14) == 3.14
        assert freeze_for_key(True) is True
        assert freeze_for_key(False) is False

    def test_freeze_tuple(self):
        """Test freezing tuple."""
        result = freeze_for_key((1, "test", None))
        assert result == (1, "test", None)

    def test_freeze_list(self):
        """Test freezing list (converted to tuple)."""
        result = freeze_for_key([1, "test", None])
        assert result == (1, "test", None)

    def test_freeze_dict(self):
        """Test freezing dict (converted to sorted tuple pairs)."""
        result = freeze_for_key({"b": 2, "a": 1, "c": "test"})
        expected = (("a", 1), ("b", 2), ("c", "test"))
        assert result == expected

    def test_freeze_nested_structures(self):
        """Test freezing nested structures."""
        nested = {"key": [1, {"inner": "value"}, None]}
        result = freeze_for_key(nested)
        expected = (("key", (1, (("inner", "value"),), None)),)
        assert result == expected

    def test_freeze_object_repr(self):
        """Test freezing arbitrary objects (uses repr)."""
        obj = object()
        result = freeze_for_key(obj)
        assert result == repr(obj)


class TestCacheEntry:
    """Test the CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test creating a CacheEntry."""
        entry = CacheEntry(value="test_value", expires_at=123.45)
        assert entry.value == "test_value"
        assert entry.expires_at == 123.45

    def test_cache_entry_frozen(self):
        """Test that CacheEntry is frozen."""
        entry = CacheEntry(value="test", expires_at=100.0)

        with pytest.raises(AttributeError):
            entry.value = "new_value"

        with pytest.raises(AttributeError):
            entry.expires_at = 200.0


class TestDebuggerCache:
    """Test the DebuggerCache class."""

    @pytest.fixture
    def cache(self):
        """Create a DebuggerCache instance."""
        return DebuggerCache()

    @pytest.fixture
    def cache_custom_max(self):
        """Create a DebuggerCache with custom max entries."""
        return DebuggerCache(max_entries=10)

    def test_init_default(self):
        """Test cache initialization with default values."""
        cache = DebuggerCache()
        assert cache._max_entries == 256
        assert len(cache._entries) == 0
        assert len(cache._inflight) == 0

    def test_init_custom_max_entries(self, cache_custom_max):
        """Test cache initialization with custom max entries."""
        assert cache_custom_max._max_entries == 10

    def test_init_max_entries_validation(self):
        """Test max_entries validation."""
        # Should handle zero or negative values
        cache = DebuggerCache(max_entries=0)
        assert cache._max_entries == 1

        cache = DebuggerCache(max_entries=-5)
        assert cache._max_entries == 1

        # Should handle float values by converting to int
        cache = DebuggerCache(max_entries=100.7)
        assert cache._max_entries == 100

    def test_clear(self, cache):
        """Test clearing the cache."""
        # Add some entries
        cache.set("key1", "value1", ttl_s=60)
        cache.set("key2", "value2", ttl_s=60)

        assert len(cache._entries) == 2

        cache.clear()

        assert len(cache._entries) == 0
        assert len(cache._inflight) == 0  # inflight should also be cleared

    def test_stats(self, cache):
        """Test getting cache statistics."""
        stats = cache.stats()

        expected_keys = {"max_entries", "entries", "inflight"}
        assert set(stats.keys()) == expected_keys
        assert stats["max_entries"] == 256
        assert stats["entries"] == 0
        assert stats["inflight"] == 0

    @pytest.mark.asyncio
    async def test_stats_with_data(self, cache):
        """Test statistics with actual data."""
        cache.set("key1", "value1", ttl_s=60)
        cache.set("key2", "value2", ttl_s=60)

        # Add an inflight task
        async def dummy_task():
            await asyncio.sleep(0.01)
            return "result"

        task = asyncio.create_task(dummy_task())
        cache._inflight["test_key"] = task

        stats = cache.stats()
        assert stats["entries"] == 2
        assert stats["inflight"] == 1

    def test_set_and_get_fresh(self, cache):
        """Test setting and getting fresh cache entries."""
        # Set a value
        cache.set("test_key", "test_value", ttl_s=60)

        # Should be able to retrieve it
        assert cache._get_fresh("test_key") == "test_value"
        assert len(cache._entries) == 1

    def test_get_fresh_expired(self, cache):
        """Test getting expired cache entries."""
        # Set with very short TTL
        cache.set("test_key", "test_value", ttl_s=0.001)

        # Wait for expiration
        time.sleep(0.01)

        # Should return None and remove expired entry
        assert cache._get_fresh("test_key") is None
        assert len(cache._entries) == 0

    def test_get_fresh_nonexistent(self, cache):
        """Test getting non-existent cache entries."""
        assert cache._get_fresh("nonexistent") is None

    def test_set_ttl_validation(self, cache):
        """Test TTL validation in set method."""
        # Test that negative TTL gets clamped to 0
        cache.set("key", "value", ttl_s=-10)
        # With ttl_s=0, entry should expire immediately
        result = cache._get_fresh("key")
        assert result is None  # Should be expired immediately

        # Test that string TTL gets converted to float
        cache.set("key2", "value", ttl_s="30")
        result = cache._get_fresh("key2")
        assert result == "value"  # Should work with string TTL

    def test_evict_on_max_entries(self, cache_custom_max):
        """Test eviction when max entries is reached."""
        cache = cache_custom_max  # max_entries = 10

        # Add exactly max_entries
        for i in range(10):
            cache.set(f"key{i}", f"value{i}", ttl_s=60)

        assert len(cache._entries) == 10

        # Add one more - should evict oldest
        cache.set("key10", "value10", ttl_s=60)

        assert len(cache._entries) == 10
        # Should not contain the first key anymore
        assert "key0" not in cache._entries
        # Should contain the new key
        assert "key10" in cache._entries

    def test_lru_behavior(self, cache):
        """Test LRU (Least Recently Used) behavior."""
        # Add entries
        cache.set("key1", "value1", ttl_s=60)
        cache.set("key2", "value2", ttl_s=60)
        cache.set("key3", "value3", ttl_s=60)

        # Access key1 to make it most recently used
        cache._get_fresh("key1")

        # Add one more to trigger eviction (assuming default max is 256, this won't
        # evict)
        # Let's use a small cache for this test
        small_cache = DebuggerCache(max_entries=3)
        small_cache.set("key1", "value1", ttl_s=60)
        small_cache.set("key2", "value2", ttl_s=60)
        small_cache.set("key3", "value3", ttl_s=60)

        # Access key1
        small_cache._get_fresh("key1")

        # Add fourth - should evict key2 (least recently used)
        small_cache.set("key4", "value4", ttl_s=60)

        assert "key1" in small_cache._entries  # Most recently used
        assert "key3" in small_cache._entries  # Recently used
        assert "key4" in small_cache._entries  # Just added
        assert "key2" not in small_cache._entries  # Should be evicted

    @pytest.mark.asyncio
    async def test_get_or_create_cached(self, cache):
        """Test get_or_create when value is already cached."""
        # Set a cached value
        cache.set("test_key", "cached_value", ttl_s=60)

        # Should return cached value without calling create_fn
        result = await cache.get_or_create(
            "test_key", ttl_s=60, create_fn=lambda: "new_value"
        )

        assert result == "cached_value"

    @pytest.mark.asyncio
    async def test_get_or_create_new_sync_function(self, cache):
        """Test get_or_create with synchronous create function."""

        def create_fn():
            return "created_value"

        result = await cache.get_or_create("test_key", ttl_s=60, create_fn=create_fn)

        assert result == "created_value"

        # Should be cached now
        assert cache._get_fresh("test_key") == "created_value"

    @pytest.mark.asyncio
    async def test_get_or_create_new_async_function(self, cache):
        """Test get_or_create with asynchronous create function."""

        async def create_fn():
            await asyncio.sleep(0.01)
            return "async_created_value"

        result = await cache.get_or_create("test_key", ttl_s=60, create_fn=create_fn)

        assert result == "async_created_value"

        # Should be cached now
        assert cache._get_fresh("test_key") == "async_created_value"

    @pytest.mark.asyncio
    async def test_get_or_create_inflight_deduplication(self, cache):
        """Test that multiple calls with same key share the same in-flight task."""
        call_count = 0

        async def slow_create_fn():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)
            return f"result_{call_count}"

        # Start multiple concurrent requests
        tasks = []
        for i in range(5):
            task = asyncio.create_task(
                cache.get_or_create("shared_key", ttl_s=60, create_fn=slow_create_fn)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should get the same result
        assert all(r == "result_1" for r in results)

        # create_fn should only be called once
        assert call_count == 1

        # Should be cached
        assert cache._get_fresh("shared_key") == "result_1"

    @pytest.mark.asyncio
    async def test_get_or_create_exception_handling(self, cache):
        """Test exception handling in get_or_create."""

        async def failing_create_fn():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await cache.get_or_create("test_key", ttl_s=60, create_fn=failing_create_fn)

        # Key should not be cached on failure
        assert cache._get_fresh("test_key") is None

        # Inflight task should be cleaned up
        assert len(cache._inflight) == 0

    @pytest.mark.asyncio
    async def test_get_or_create_exception_in_finally(self, cache):
        """Test that inflight task is cleaned up even if create_fn raises in finally."""

        async def create_fn():
            try:
                return "success"
            finally:
                # Simulate an exception in user code
                raise RuntimeError("Finally error")

        with pytest.raises(RuntimeError, match="Finally error"):
            await cache.get_or_create("test_key", ttl_s=60, create_fn=create_fn)

        # Inflight task should still be cleaned up
        assert len(cache._inflight) == 0

    def test_ttl_zero_means_expired_immediately(self, cache):
        """Test that TTL of 0 means entry expires immediately."""
        cache.set("key", "value", ttl_s=0)

        # Should be expired immediately
        assert cache._get_fresh("key") is None
        assert len(cache._entries) == 0

    def test_move_to_end_on_access(self, cache):
        """Test that accessing an entry moves it to the end (most recently used)."""
        cache.set("key1", "value1", ttl_s=60)
        cache.set("key2", "value2", ttl_s=60)
        cache.set("key3", "value3", ttl_s=60)

        # Access key1 - should move to end
        cache._get_fresh("key1")

        # Check order by popping from beginning
        first_key = next(iter(cache._entries.keys()))
        assert first_key == "key2"  # key1 should be at end

    def test_complex_keys(self, cache):
        """Test using complex objects as cache keys."""
        # Test with dict key - should work when frozen
        dict_key = {"param1": "value1", "param2": 42}
        cache.set(dict_key, "dict_result", ttl_s=60)

        # Should be able to retrieve with same dict (gets frozen to tuple)
        assert cache._get_fresh(dict_key) == "dict_result"

        # Should not match different dict
        different_dict = {"param1": "value1", "param2": 43}
        assert cache._get_fresh(different_dict) is None

        # Test with tuple key
        tuple_key = ("arg1", 123, None)
        cache.set(tuple_key, "tuple_result", ttl_s=60)

        assert cache._get_fresh(tuple_key) == "tuple_result"
