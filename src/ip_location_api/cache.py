"""
缓存模块
提供高性能的内存缓存支持
"""

from typing import Optional, Any
from dataclasses import dataclass
import time
from cachetools import TTLCache

from ip_location_api.config import config


@dataclass
class CacheStats:
    """
    缓存统计数据
    
    Attributes:
        hits: 缓存命中次数
        misses: 缓存未命中次数
        size: 当前缓存大小
        max_size: 最大缓存大小
    """
    hits: int = 0
    misses: int = 0
    size: int = 0
    max_size: int = 0
    
    @property
    def hit_rate(self) -> float:
        """
        计算缓存命中率
        
        Returns:
            float: 命中率(0-1)
        """
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class IPQueryCache:
    """
    IP查询缓存
    
    使用TTL缓存策略，自动过期清理
    """
    
    def __init__(self, max_size: int = None, ttl: int = None):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存过期时间(秒)
        """
        self.max_size = max_size or config.CACHE_SIZE
        self.ttl = ttl or config.CACHE_TTL
        self._cache = TTLCache(maxsize=self.max_size, ttl=self.ttl)
        self._stats = CacheStats(max_size=self.max_size)
    
    def get(self, key: str) -> Optional[Any]:
        """
        从缓存获取值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，不存在返回None
        """
        try:
            value = self._cache[key]
            self._stats.hits += 1
            return value
        except KeyError:
            self._stats.misses += 1
            return None
    
    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        self._cache[key] = value
        self._stats.size = len(self._cache)
    
    def get_or_set(self, key: str, factory) -> Any:
        """
        获取缓存值，不存在则通过factory创建并缓存
        
        Args:
            key: 缓存键
            factory: 值工厂函数
            
        Returns:
            缓存值或新创建的值
        """
        value = self.get(key)
        if value is None:
            value = factory()
            if value is not None:
                self.set(key, value)
        return value
    
    def clear(self) -> None:
        """
        清空缓存
        """
        self._cache.clear()
        self._stats.size = 0
    
    def get_stats(self) -> CacheStats:
        """
        获取缓存统计信息
        
        Returns:
            CacheStats: 缓存统计数据
        """
        self._stats.size = len(self._cache)
        return self._stats


ip_cache = IPQueryCache()
