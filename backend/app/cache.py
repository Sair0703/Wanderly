"""Cache abstraction: Redis when REDIS_URL is set, in-memory dict otherwise.

The recommendation engine and search endpoints cache results here to support
the "scalable search and personalization flows" from the spec.
"""
from __future__ import annotations

import json
import time
from threading import Lock
from typing import Any, Optional

from .config import settings


class _MemoryCache:
    """Thread-safe TTL cache used when Redis is unavailable."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at and expires_at < time.time():
                self._store.pop(key, None)
                return None
            return value

    def setex(self, key: str, ttl: int, value: str) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl if ttl else 0, value)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            for k in [k for k in self._store if k.startswith(prefix)]:
                self._store.pop(k, None)

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            now = time.time()
            item = self._store.get(key)
            if not item or (item[0] and item[0] < now):
                self._store[key] = (now + ttl, "1")
                return 1
            count = int(item[1]) + 1
            self._store[key] = (item[0], str(count))
            return count


class Cache:
    def __init__(self) -> None:
        self._redis = None
        self._mem = _MemoryCache()
        if settings.redis_url:
            try:
                import redis  # type: ignore

                self._redis = redis.from_url(
                    settings.redis_url, decode_responses=True
                )
                self._redis.ping()
            except Exception:  # pragma: no cover - graceful fallback
                self._redis = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    def get_json(self, key: str) -> Optional[Any]:
        raw = self._redis.get(key) if self._redis else self._mem.get(key)
        return json.loads(raw) if raw else None

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else settings.cache_ttl_seconds
        raw = json.dumps(value, default=str)
        if self._redis:
            self._redis.setex(key, ttl, raw)
        else:
            self._mem.setex(key, ttl, raw)

    def invalidate_prefix(self, prefix: str) -> None:
        if self._redis:
            for k in self._redis.scan_iter(match=f"{prefix}*"):
                self._redis.delete(k)
        else:
            self._mem.delete_prefix(prefix)

    def incr(self, key: str, ttl: int) -> int:
        """Atomic-ish increment with TTL on first write. Used for rate limiting."""
        if self._redis:
            count = self._redis.incr(key)
            if count == 1:
                self._redis.expire(key, ttl)
            return int(count)
        return self._mem.incr(key, ttl)


cache = Cache()
