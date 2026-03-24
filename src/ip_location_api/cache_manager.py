"""
缓存管理模块
提供统一的缓存管理功能，支持TTL过期策略、键命名规范、错误处理等
"""

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Generic, TypeVar, Callable
from enum import Enum

from cachetools import TTLCache

from ip_location_api.logger import get_logger


logger = get_logger(__name__)


T = TypeVar('T')


class CacheError(Exception):
    """缓存操作异常基类"""
    pass


class CacheKeyError(CacheError):
    """缓存键错误"""
    pass


class CacheValueError(CacheError):
    """缓存值错误"""
    pass


class CacheFullError(CacheError):
    """缓存已满"""
    pass


class CacheKeyBuilder:
    """
    缓存键构建器
    
    提供统一的键命名规范，支持命名空间和分隔符配置
    """
    
    DEFAULT_SEPARATOR = ":"
    DEFAULT_NAMESPACE = "cache"
    
    def __init__(self, namespace: str = DEFAULT_NAMESPACE, separator: str = DEFAULT_SEPARATOR):
        """
        初始化键构建器
        
        Args:
            namespace: 命名空间前缀
            separator: 键分隔符
        """
        self.namespace = namespace
        self.separator = separator
    
    def build(self, *parts: str) -> str:
        """
        构建缓存键
        
        Args:
            *parts: 键的各个部分
            
        Returns:
            str: 完整的缓存键
            
        Example:
            >>> builder = CacheKeyBuilder(namespace="ip")
            >>> builder.build("location", "8.8.8.8")
            'ip:location:8.8.8.8'
        """
        if not parts:
            raise CacheKeyError("缓存键至少需要一个部分")
        
        key_parts = [self.namespace] + [str(p) for p in parts]
        return self.separator.join(key_parts)
    
    def parse(self, key: str) -> list[str]:
        """
        解析缓存键
        
        Args:
            key: 缓存键
            
        Returns:
            list[str]: 键的各个部分
        """
        return key.split(self.separator)
    
    @staticmethod
    def sanitize(value: str) -> str:
        """
        清理键值中的特殊字符
        
        Args:
            value: 原始值
            
        Returns:
            str: 清理后的值
        """
        return value.replace(" ", "_").replace(":", "_").replace("\n", "")


@dataclass
class CacheStats:
    """
    缓存统计数据
    
    Attributes:
        hits: 缓存命中次数
        misses: 缓存未命中次数
        hit_rate: 命中率
        size: 当前缓存大小
        max_size: 最大缓存大小
        evictions: 驱逐次数
    """
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    size: int = 0
    max_size: int = 0
    evictions: int = 0
    
    def to_dict(self) -> dict:
        """
        转换为字典格式
        
        Returns:
            dict: 统计数据字典
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "size": self.size,
            "max_size": self.max_size,
            "evictions": self.evictions,
        }


class EvictionPolicy(Enum):
    """
    缓存驱逐策略
    
    Attributes:
        LRU: 最近最少使用
        LFU: 最不经常使用
        FIFO: 先进先出
        TTL: 基于时间过期
    """
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    TTL = "ttl"


class CacheBackend(ABC, Generic[T]):
    """
    缓存后端抽象基类
    
    定义缓存操作的标准接口
    """
    
    @abstractmethod
    def get(self, key: str) -> Optional[T]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[T]: 缓存值，不存在返回None
        """
        pass
    
    @abstractmethod
    def set(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None表示使用默认TTL
        """
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否删除成功
        """
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """
        清空所有缓存
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> CacheStats:
        """
        获取缓存统计
        
        Returns:
            CacheStats: 统计数据
        """
        pass


class TTLCacheBackend(CacheBackend[T]):
    """
    基于TTL的内存缓存后端
    
    使用cachetools.TTLCache实现，支持自动过期
    """
    
    def __init__(
        self,
        maxsize: int = 10000,
        ttl: float = 3600,
        key_builder: Optional[CacheKeyBuilder] = None
    ):
        """
        初始化TTL缓存后端
        
        Args:
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            key_builder: 键构建器
        """
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()
        self._key_builder = key_builder or CacheKeyBuilder()
        
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._default_ttl = ttl
    
    def get(self, key: str) -> Optional[T]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[T]: 缓存值，不存在或已过期返回None
        """
        with self._lock:
            try:
                value = self._cache.get(key)
                if value is not None:
                    self._hits += 1
                    logger.debug_with_extra("缓存命中", key=key)
                    return value
                else:
                    self._misses += 1
                    logger.debug_with_extra("缓存未命中", key=key)
                    return None
            except Exception as e:
                logger.error_with_extra("缓存读取异常", key=key, error=str(e))
                self._misses += 1
                return None
    
    def set(self, key: str, value: T, ttl: Optional[float] = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None表示使用默认TTL
        """
        with self._lock:
            try:
                if ttl is not None and ttl != self._default_ttl:
                    self._cache.ttl = ttl
                self._cache[key] = value
                logger.debug_with_extra("缓存写入", key=key)
            except Exception as e:
                logger.error_with_extra("缓存写入异常", key=key, error=str(e))
                raise CacheError(f"缓存写入失败: {e}")
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否删除成功
        """
        with self._lock:
            try:
                if key in self._cache:
                    del self._cache[key]
                    logger.debug_with_extra("缓存删除", key=key)
                    return True
                return False
            except Exception as e:
                logger.error_with_extra("缓存删除异常", key=key, error=str(e))
                return False
    
    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        with self._lock:
            return key in self._cache
    
    def clear(self) -> None:
        """
        清空所有缓存
        """
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            logger.info("缓存已清空")
    
    def get_stats(self) -> CacheStats:
        """
        获取缓存统计
        
        Returns:
            CacheStats: 统计数据
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                hit_rate=hit_rate,
                size=len(self._cache),
                max_size=self._cache.maxsize,
                evictions=self._evictions,
            )
    
    def get_many(self, keys: list[str]) -> dict[str, Optional[T]]:
        """
        批量获取缓存值
        
        Args:
            keys: 缓存键列表
            
        Returns:
            dict[str, Optional[T]]: 键值对字典
        """
        result = {}
        with self._lock:
            for key in keys:
                result[key] = self.get(key)
        return result
    
    def set_many(self, items: dict[str, T], ttl: Optional[float] = None) -> None:
        """
        批量设置缓存值
        
        Args:
            items: 键值对字典
            ttl: 过期时间（秒）
        """
        with self._lock:
            for key, value in items.items():
                self.set(key, value, ttl)
    
    def delete_many(self, keys: list[str]) -> int:
        """
        批量删除缓存
        
        Args:
            keys: 缓存键列表
            
        Returns:
            int: 成功删除的数量
        """
        count = 0
        with self._lock:
            for key in keys:
                if self.delete(key):
                    count += 1
        return count


class CacheManager:
    """
    缓存管理器
    
    提供统一的缓存管理接口，支持多命名空间、统计监控等功能
    """
    
    _instances: dict[str, 'CacheManager'] = {}
    _lock = threading.Lock()
    
    def __init__(
        self,
        namespace: str = "default",
        maxsize: int = 10000,
        ttl: float = 3600,
        key_builder: Optional[CacheKeyBuilder] = None
    ):
        """
        初始化缓存管理器
        
        Args:
            namespace: 命名空间
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            key_builder: 键构建器
        """
        self.namespace = namespace
        self._backend = TTLCacheBackend(
            maxsize=maxsize,
            ttl=ttl,
            key_builder=key_builder or CacheKeyBuilder(namespace=namespace)
        )
        self._key_builder = self._backend._key_builder
    
    @classmethod
    def get_instance(
        cls,
        namespace: str = "default",
        maxsize: int = 10000,
        ttl: float = 3600
    ) -> 'CacheManager':
        """
        获取命名空间的缓存管理器实例（单例模式）
        
        Args:
            namespace: 命名空间
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            
        Returns:
            CacheManager: 缓存管理器实例
        """
        with cls._lock:
            if namespace not in cls._instances:
                cls._instances[namespace] = CacheManager(
                    namespace=namespace,
                    maxsize=maxsize,
                    ttl=ttl
                )
            return cls._instances[namespace]
    
    @classmethod
    def clear_all_instances(cls) -> None:
        """
        清空所有命名空间的缓存
        """
        with cls._lock:
            for instance in cls._instances.values():
                instance.clear()
            cls._instances.clear()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[Any]: 缓存值
        """
        full_key = self._key_builder.build(key)
        return self._backend.get(full_key)
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
        """
        full_key = self._key_builder.build(key)
        self._backend.set(full_key, value, ttl)
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否删除成功
        """
        full_key = self._key_builder.build(key)
        return self._backend.delete(full_key)
    
    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        full_key = self._key_builder.build(key)
        return self._backend.exists(full_key)
    
    def clear(self) -> None:
        """
        清空当前命名空间的缓存
        """
        self._backend.clear()
    
    def get_stats(self) -> CacheStats:
        """
        获取缓存统计
        
        Returns:
            CacheStats: 统计数据
        """
        return self._backend.get_stats()
    
    def get_or_set(
        self,
        key: str,
        factory: Callable[[], T],
        ttl: Optional[float] = None
    ) -> T:
        """
        获取缓存值，不存在则通过工厂函数创建并缓存
        
        Args:
            key: 缓存键
            factory: 值工厂函数
            ttl: 过期时间（秒）
            
        Returns:
            T: 缓存值或新创建的值
        """
        value = self.get(key)
        if value is not None:
            return value
        
        value = factory()
        if value is not None:
            self.set(key, value, ttl)
        
        return value
    
    def compute_if_absent(
        self,
        key: str,
        compute: Callable[[], T],
        ttl: Optional[float] = None
    ) -> T:
        """
        如果缓存不存在，计算并缓存结果
        
        Args:
            key: 缓存键
            compute: 计算函数
            ttl: 过期时间（秒）
            
        Returns:
            T: 缓存值或计算结果
        """
        return self.get_or_set(key, compute, ttl)


def create_ip_location_cache(maxsize: int = 50000, ttl: float = 3600) -> CacheManager:
    """
    创建IP定位专用缓存管理器
    
    Args:
        maxsize: 最大缓存条目数
        ttl: 过期时间（秒）
        
    Returns:
        CacheManager: 缓存管理器实例
    """
    return CacheManager.get_instance(
        namespace="ip_location",
        maxsize=maxsize,
        ttl=ttl
    )
