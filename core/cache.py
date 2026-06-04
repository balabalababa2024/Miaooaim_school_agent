"""
Redis 缓存模块
==============
提供 Redis 连接管理和通用缓存装饰器。
Redis 不可用时自动降级，不影响正常功能。
"""
import json
import hashlib
import functools
import logging

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = None  # None=未检测, True/False=已检测


def get_redis():
    """获取 Redis 客户端（单例，连接池）。不可用时返回 None。"""
    global _redis_client, _redis_available

    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        import redis
        from .config import REDIS_CONFIG
        pool = redis.ConnectionPool(**REDIS_CONFIG)
        _redis_client = redis.Redis(connection_pool=pool)
        _redis_client.ping()
        _redis_available = True
        logger.info(f"Redis 连接成功: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
        return _redis_client
    except Exception as e:
        _redis_available = False
        logger.warning(f"Redis 不可用，缓存功能已禁用: {e}")
        return None


def cache_get(key: str):
    """从 Redis 获取缓存值。失败返回 None。"""
    r = get_redis()
    if r is None:
        return None
    try:
        val = r.get(key)
        if val is not None:
            logger.info(f"[Cache] HIT: {key}")
            return json.loads(val)
        logger.info(f"[Cache] MISS: {key}")
        return None
    except Exception as e:
        logger.warning(f"[Cache] GET 失败 {key}: {e}")
        return None


def cache_set(key: str, value, ttl: int = 600):
    """写入 Redis 缓存。失败静默忽略。"""
    r = get_redis()
    if r is None:
        return
    try:
        r.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        logger.info(f"[Cache] SET: {key} (TTL={ttl}s)")
    except Exception as e:
        logger.warning(f"[Cache] SET 失败 {key}: {e}")


def cache_clear(prefix: str = ""):
    """按前缀清除缓存。"""
    r = get_redis()
    if r is None:
        return
    try:
        pattern = f"{prefix}*" if prefix else "*"
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
            logger.info(f"[Cache] CLEAR: {prefix}* ({len(keys)} keys)")
    except Exception as e:
        logger.warning(f"[Cache] CLEAR 失败: {e}")


def _make_hash(*args, **kwargs) -> str:
    """将函数参数生成稳定的短 hash。"""
    parts = []
    for a in args:
        if isinstance(a, str):
            parts.append(a)
        elif isinstance(a, (int, float, bool)):
            parts.append(str(a))
        else:
            parts.append(json.dumps(a, sort_keys=True, ensure_ascii=False, default=str))
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}={v}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cached(prefix: str, ttl: int = 600):
    """
    通用缓存装饰器。

    用法:
        @cached("llm", ttl=600)
        def llm(prompt: str) -> str:
            ...

    缓存 key 格式: {prefix}:{hash(args)}
    Redis 不可用时静默降级，直接执行原函数。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存 key
            h = _make_hash(*args, **kwargs)
            key = f"{prefix}:{h}"

            # 尝试读缓存
            cached_val = cache_get(key)
            if cached_val is not None:
                return cached_val

            # 执行原函数
            result = func(*args, **kwargs)

            # 写缓存（只缓存有效结果）
            if result is not None and result != "":
                cache_set(key, result, ttl)

            return result
        return wrapper
    return decorator
