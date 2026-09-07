import hashlib
import json
import time
from typing import Any, Callable, Optional
from functools import wraps
import redis

class QueryCache:

    def __init__(self, redis_url="redis://localhost:6379", default_ttl=3600):
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            print("✅ 缓存服务连接成功")
            self.enabled = True
        except:
            print("⚠️ 缓存服务不可用，将绕过缓存")
            self.enabled = False
            self.redis = None

    def _generate_key(self, tool_name: str, arguments: dict) -> str:
        sorted_args = json.dumps(arguments, sort_keys=True)
        content = f"{tool_name}:{sorted_args}"
        return f"cache:{hashlib.md5(content.encode()).hexdigest()}"

    def get(self, tool_name: str, arguments: dict) -> Optional[Any]:
        if not self.enabled:
            return None
        key = self._generate_key(tool_name, arguments)
        cached = self.redis.get(key)
        if cached:
            self.hits += 1
            print(f"📦 缓存命中: {tool_name}")
            return json.loads(cached)
        self.misses += 1
        return None

    def set(self, tool_name: str, arguments: dict, value: Any, ttl: int = None):
        if not self.enabled:
            return
        key = self._generate_key(tool_name, arguments)
        ttl = ttl or self.default_ttl
        self.redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        print(f"💾 缓存写入: {tool_name} (TTL: {ttl}s)")

    def clear(self, pattern: str = None):
        if not self.enabled:
            return
        if pattern:
            for key in self.redis.scan_iter(f"cache:{pattern}*"):
                self.redis.delete(key)
        else:
            for key in self.redis.scan_iter("cache:*"):
                self.redis.delete(key)
        print("🗑️  缓存已清除")

    def get_stats(self) -> dict:
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {"hits": self.hits, "misses": self.misses,
                "total_quaries": total,"hit_rate": f"{hit_rate:.1f}%",
                "enabled": self.enabled}

    def cache_result(self, ttl: int = None):
        """
        @cache.cache_result(ttl=300)
        async def expensive_operation(param):
            return result
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                tool_name = func.__name__
                cached = self.get(tool_name, kwargs)
                if cached is not None:
                    return cached
                result = await func(*args, **kwargs)
                self.set(tool_name, kwargs, result, ttl)
                return result
            return wrapper
        return decorator

_cache_instance = None

def get_cache():
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = QueryCache()
    return _cache_instance
