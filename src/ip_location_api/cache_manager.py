"""
缓存管理模块
提供统一的缓存管理功能，支持TTL过期策略、键命名规范、错误处理等
性能优化：使用msgpack二进制序列化，提升缓存读写效率
"""

import threading
import time
import msgpack
from abc import ABC, abstractmethod
from dataclasses import dataclass, is_dataclass
from typing import Any, Optional, Generic, TypeVar, Callable, Dict, Type
from enum import Enum

from cachetools import TTLCache

from ip_location_api.logger import get_logger


logger = get_logger(__name__)


T = TypeVar('T')


class TypeRegistry:
    """
    类型注册表
    
    用于在反序列化时动态解析类型，避免硬编码依赖
    """
    
    _dataclass_registry: Dict[str, Type] = {}
    _enum_registry: Dict[str, Type] = {}
    
    @classmethod
    def register_dataclass(cls, type_class: Type) -> None:
        """
        注册数据类
        
        Args:
            type_class: 数据类类型
        """
        cls._dataclass_registry[type_class.__name__] = type_class
    
    @classmethod
    def register_enum(cls, type_class: Type) -> None:
        """
        注册枚举类
        
        Args:
            type_class: 枚举类类型
        """
        cls._enum_registry[type_class.__name__] = type_class
    
    @classmethod
    def get_dataclass(cls, name: str) -> Optional[Type]:
        """
        获取已注册的数据类
        
        Args:
            name: 类名
            
        Returns:
            Optional[Type]: 数据类类型
        """
        return cls._dataclass_registry.get(name)
    
    @classmethod
    def get_enum(cls, name: str) -> Optional[Type]:
        """
        获取已注册的枚举类
        
        Args:
            name: 类名
            
        Returns:
            Optional[Type]: 枚举类类型
        """
        return cls._enum_registry.get(name)


def _serialize_value(value: Any) -> Any:
    """
    序列化值以便msgpack存储
    
    Args:
        value: 待序列化的值
        
    Returns:
        Any: 序列化后的值
    """
    if value is None:
        return None
    
    if is_dataclass(value):
        return ("__dataclass__", type(value).__name__, _dataclass_to_dict(value))
    
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    
    if isinstance(value, Enum):
        return ("__enum__", type(value).__name__, value.value)
    
    return value


def _dataclass_to_dict(obj: Any) -> dict:
    """
    将 dataclass 递归转换为字典
    
    Args:
        obj: dataclass 对象
        
    Returns:
        dict: 转换后的字典
    """
    if is_dataclass(obj):
        result = {}
        for field_name in obj.__dataclass_fields__:
            field_value = getattr(obj, field_name)
            result[field_name] = _serialize_value(field_value)
        return result
    return obj


def _deserialize_value(value: Any) -> Any:
    """
    反序列化msgpack数据
    
    使用类型注册表动态解析类型，避免硬编码依赖
    
    Args:
        value: 待反序列化的值
        
    Returns:
        Any: 反序列化后的值
    """
    if value is None:
        return None
    
    if isinstance(value, list):
        if len(value) == 3:
            first = value[0]
            if isinstance(first, str) and first in ("__dataclass__", "__enum__"):
                if value[0] == "__dataclass__":
                    cls_name = value[1]
                    data = value[2]
                    
                    type_class = TypeRegistry.get_dataclass(cls_name)
                    if type_class is not None:
                        return type_class(**_deserialize_value(data))
                    
                    logger.error_with_extra("未注册的数据类类型", type_name=cls_name)
                    raise CacheValueError(
                        f"未注册的数据类类型: {cls_name}。"
                        f"请确保在应用启动时调用 register_fusion_types() 或手动注册该类型。"
                    )
                
                if value[0] == "__enum__":
                    cls_name = value[1]
                    enum_value = value[2]
                    
                    enum_class = TypeRegistry.get_enum(cls_name)
                    if enum_class is not None:
                        return enum_class(enum_value)
                    
                    logger.error_with_extra("未注册的枚举类型", type_name=cls_name)
                    raise CacheValueError(
                        f"未注册的枚举类型: {cls_name}。"
                        f"请确保在应用启动时调用 register_fusion_types() 或手动注册该类型。"
                    )
        
        return [_deserialize_value(item) for item in value]
    
    if isinstance(value, dict):
        return {k: _deserialize_value(v) for k, v in value.items()}
    
    return value


def register_fusion_types():
    """
    注册融合模块的类型
    
    由 fusion.py 在初始化时调用，避免循环导入
    """
    from ip_location_api.fusion import FusedLocation, LocationSource, AccuracyLevel
    
    TypeRegistry.register_dataclass(FusedLocation)
    TypeRegistry.register_dataclass(LocationSource)
    TypeRegistry.register_enum(AccuracyLevel)


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


@dataclass(slots=True)
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
    性能优化：
    - 使用__slots__减少实例内存占用
    - 使用msgpack紧凑二进制格式减小缓存体积
    版本管理：
    - 支持缓存格式版本，自动检测和迁移
    """
    
    __slots__ = ('_cache', '_lock', '_key_builder', '_hits', '_misses', '_evictions', '_default_ttl', '_use_msgpack', '_fallback_to_raw')
    
    _MSGPACK_MAGIC_PREFIX = b'\x00MSGPACK\x00'
    _CACHE_VERSION = b'\x01'
    
    def __init__(
        self,
        maxsize: int = 10000,
        ttl: float = 3600,
        key_builder: Optional[CacheKeyBuilder] = None,
        use_msgpack: bool = True,
        fallback_to_raw: bool = True
    ):
        """
        初始化TTL缓存后端
        
        Args:
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            key_builder: 键构建器
            use_msgpack: 是否使用msgpack格式存储
            fallback_to_raw: 当格式错误时是否降级返回原始数据而非抛出异常
        """
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()
        self._key_builder = key_builder or CacheKeyBuilder()
        
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._default_ttl = ttl
        self._use_msgpack = use_msgpack
        self._fallback_to_raw = fallback_to_raw
    
    def _pack(self, value: T) -> bytes:
        """
        打包值为msgpack格式
        
        Args:
            value: 待打包的值
            
        Returns:
            bytes: 带版本前缀的msgpack格式二进制数据
        """
        serialized = _serialize_value(value)
        packed = msgpack.packb(serialized, use_bin_type=True)
        return self._MSGPACK_MAGIC_PREFIX + self._CACHE_VERSION + packed
    
    def _unpack(self, data: bytes) -> T:
        """
        解包msgpack数据
        
        Args:
            data: 带版本前缀的msgpack格式二进制数据
            
        Returns:
            T: 反序列化后的值
            
        Raises:
            CacheValueError: 当格式无效且fallback_to_raw=False时
        """
        if not data.startswith(self._MSGPACK_MAGIC_PREFIX):
            if self._fallback_to_raw:
                logger.warning("缓存格式无效，尝试降级处理")
                try:
                    unpacked = msgpack.unpackb(data, raw=False)
                    return _deserialize_value(unpacked)
                except Exception:
                    pass
            raise CacheValueError("无效的msgpack数据格式")
        
        offset = len(self._MSGPACK_MAGIC_PREFIX)
        version = data[offset:offset + 1]
        
        if version != self._CACHE_VERSION:
            logger.warning_with_extra("缓存版本不匹配", expected=self._CACHE_VERSION, got=version)
            if self._fallback_to_raw:
                try:
                    unpacked = msgpack.unpackb(data[offset + 1:], raw=False)
                    return _deserialize_value(unpacked)
                except Exception as e:
                    logger.error_with_extra("降级处理失败", error=str(e))
            raise CacheValueError(
                f"缓存格式版本不匹配: expected={self._CACHE_VERSION}, got={version}。"
                f"请清除旧缓存。"
            )
        
        unpacked = msgpack.unpackb(data[offset + 1:], raw=False)
        return _deserialize_value(unpacked)
    
    def _is_msgpack_data(self, data: bytes) -> bool:
        """
        检查数据是否为msgpack格式
        
        Args:
            data: 二进制数据
            
        Returns:
            bool: 是否为msgpack格式
        """
        return isinstance(data, bytes) and data.startswith(self._MSGPACK_MAGIC_PREFIX)
    
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
                    if self._use_msgpack:
                        if self._is_msgpack_data(value):
                            return self._unpack(value)
                        if self._fallback_to_raw:
                            logger.warning_with_extra("缓存格式无效，尝试降级读取", key=key)
                            try:
                                unpacked = msgpack.unpackb(value, raw=False)
                                return _deserialize_value(unpacked)
                            except Exception:
                                logger.debug_with_extra("降级读取失败，返回原始值", key=key)
                                return None
                        raise CacheValueError(
                            f"缓存格式错误: 期望msgpack格式但收到原始数据。"
                            f"请清除缓存或使用 use_msgpack=False。"
                        )
                    logger.debug_with_extra("缓存命中", key=key)
                    return value
                else:
                    self._misses += 1
                    logger.debug_with_extra("缓存未命中", key=key)
                    return None
            except CacheValueError:
                raise
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
                
                if self._use_msgpack:
                    value = self._pack(value)
                
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
    性能优化：使用msgpack二进制序列化
    """
    
    _instances: dict[str, 'CacheManager'] = {}
    _lock = threading.Lock()
    
    def __init__(
        self,
        namespace: str = "default",
        maxsize: int = 10000,
        ttl: float = 3600,
        key_builder: Optional[CacheKeyBuilder] = None,
        use_msgpack: bool = True,
        fallback_to_raw: bool = True
    ):
        """
        初始化缓存管理器
        
        Args:
            namespace: 命名空间
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            key_builder: 键构建器
            use_msgpack: 是否使用msgpack格式存储
            fallback_to_raw: 当格式错误时是否降级返回原始数据
        """
        self.namespace = namespace
        self._backend = TTLCacheBackend(
            maxsize=maxsize,
            ttl=ttl,
            key_builder=key_builder or CacheKeyBuilder(namespace=namespace),
            use_msgpack=use_msgpack,
            fallback_to_raw=fallback_to_raw
        )
        self._key_builder = self._backend._key_builder
    
    @classmethod
    def get_instance(
        cls,
        namespace: str = "default",
        maxsize: int = 10000,
        ttl: float = 3600,
        use_msgpack: bool = True,
        fallback_to_raw: bool = True
    ) -> 'CacheManager':
        """
        获取命名空间的缓存管理器实例（单例模式）
        
        Args:
            namespace: 命名空间
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            use_msgpack: 是否使用msgpack格式存储
            fallback_to_raw: 当格式错误时是否降级返回原始数据
            
        Returns:
            CacheManager: 缓存管理器实例
        """
        with cls._lock:
            if namespace not in cls._instances:
                cls._instances[namespace] = CacheManager(
                    namespace=namespace,
                    maxsize=maxsize,
                    ttl=ttl,
                    use_msgpack=use_msgpack,
                    fallback_to_raw=fallback_to_raw
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


def create_ip_location_cache(
    namespace: str = "ip_location",
    maxsize: int = 50000,
    ttl: float = 3600,
    use_msgpack: bool = True,
    fallback_to_raw: bool = True
) -> CacheManager:
    """
    创建IP定位专用缓存管理器
    
    Args:
        namespace: 命名空间
        maxsize: 最大缓存条目数
        ttl: 过期时间（秒）
        use_msgpack: 是否使用msgpack格式存储
        fallback_to_raw: 当格式错误时是否降级返回原始数据
        
    Returns:
        CacheManager: 缓存管理器实例
    """
    return CacheManager.get_instance(
        namespace=namespace,
        maxsize=maxsize,
        ttl=ttl,
        use_msgpack=use_msgpack,
        fallback_to_raw=fallback_to_raw
    )
