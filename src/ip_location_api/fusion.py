"""
多数据源融合定位模块
整合ip2region、纯真等多个数据源，提供置信度评分和精度提示
支持缓存、故障降级、多源投票、数据库热重载等优化特性
"""

import ipaddress
import os
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict

from ip_location_api.config import config
from ip_location_api.logger import get_logger
from ip_location_api.cache_manager import create_ip_location_cache, CacheManager


logger = get_logger(__name__)


class AccuracyLevel(Enum):
    """
    定位精度等级
    
    Attributes:
        HIGH: 高精度（GPS/WiFi定位）
        MEDIUM: 中等精度（IP定位，非CGNAT）
        LOW: 低精度（IP定位，可能是CGNAT共享出口）
        UNKNOWN: 未知精度
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class LocationSource:
    """
    单数据源定位结果
    
    Attributes:
        source: 数据源名称
        country: 国家
        province: 省份
        city: 城市
        isp: 运营商
        country_code: 国家代码
        latitude: 纬度（可选）
        longitude: 经度（可选）
    """
    source: str
    country: str = ""
    province: str = ""
    city: str = ""
    isp: str = ""
    country_code: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class FusedLocation:
    """
    融合定位结果
    
    Attributes:
        ip: 查询的IP地址
        country: 融合后的国家
        province: 融合后的省份
        city: 融合后的城市
        isp: 融合后的运营商
        country_code: 国家代码
        is_china: 是否为中国IP
        ip_version: IP版本
        accuracy: 精度等级
        accuracy_note: 精度提示说明
        is_cgnat: 是否可能是CGNAT共享出口
        sources: 各数据源的原始结果
        cached: 是否来自缓存
    """
    ip: str
    country: str = ""
    province: str = ""
    city: str = ""
    isp: str = ""
    country_code: str = ""
    is_china: bool = False
    ip_version: int = 4
    accuracy: AccuracyLevel = AccuracyLevel.UNKNOWN
    accuracy_note: str = ""
    is_cgnat: bool = False
    sources: List[LocationSource] = field(default_factory=list)
    cached: bool = False
    
    def to_dict(self) -> dict:
        """
        转换为字典格式
        
        Returns:
            dict: 包含所有字段的字典
        """
        return {
            "ip": self.ip,
            "country": self.country,
            "province": self.province,
            "city": self.city,
            "isp": self.isp,
            "country_code": self.country_code,
            "is_china": self.is_china,
            "ip_version": self.ip_version,
            "accuracy": self.accuracy.value,
            "accuracy_note": self.accuracy_note,
            "is_cgnat": self.is_cgnat,
            "cached": self.cached,
        }


class LocationNormalizer:
    """
    定位结果标准化处理器
    
    清洗无效值，标准化省份名称
    """
    
    INVALID_VALUES = {"0", "", "未知", "unknown", "N/A", "*", "null", "none"}
    
    PROVINCE_ALIASES = {
        "北京": "北京市",
        "上海": "上海市",
        "天津": "天津市",
        "重庆": "重庆市",
        "内蒙古": "内蒙古自治区",
        "广西": "广西壮族自治区",
        "西藏": "西藏自治区",
        "宁夏": "宁夏回族自治区",
        "新疆": "新疆维吾尔自治区",
        "香港": "香港特别行政区",
        "澳门": "澳门特别行政区",
        "台湾": "台湾省",
    }
    
    @classmethod
    def normalize(cls, location: LocationSource) -> LocationSource:
        """
        标准化定位结果
        
        Args:
            location: 原始定位结果
            
        Returns:
            LocationSource: 标准化后的结果
        """
        return LocationSource(
            source=location.source,
            country=cls._clean(location.country),
            province=cls._normalize_province(location.province),
            city=cls._clean(location.city),
            isp=cls._clean(location.isp),
            country_code=location.country_code,
            latitude=location.latitude,
            longitude=location.longitude,
        )
    
    @classmethod
    def _clean(cls, value: str) -> str:
        """
        清洗无效值
        
        Args:
            value: 原始值
            
        Returns:
            str: 清洗后的值
        """
        if not value:
            return ""
        cleaned = value.strip()
        if cleaned.lower() in cls.INVALID_VALUES:
            return ""
        return cleaned
    
    @classmethod
    def _normalize_province(cls, province: str) -> str:
        """
        标准化省份名称
        
        Args:
            province: 原始省份名称
            
        Returns:
            str: 标准化后的省份名称
        """
        province = cls._clean(province)
        return cls.PROVINCE_ALIASES.get(province, province)


class CGNATDetector:
    """
    CGNAT共享出口检测器
    
    使用IP段匹配检测，支持高效查询
    """
    
    _initialized = False
    _mobile_networks: List[ipaddress.IPv4Network] = []
    _unicom_networks: List[ipaddress.IPv4Network] = []
    _telecom_networks: List[ipaddress.IPv4Network] = []
    _lock = threading.Lock()
    
    MOBILE_KEYWORDS = ["移动", "中国移动", "China Mobile", "CMCC"]
    UNICOM_KEYWORDS = ["联通", "中国联通", "China Unicom", "CNC", "UNICOM"]
    TELECOM_KEYWORDS = ["电信", "中国电信", "China Telecom", "CT", "CHINANET"]
    
    @classmethod
    def _init_networks(cls):
        """
        初始化运营商IP段（使用CIDR格式，更高效）
        """
        if cls._initialized:
            return
        
        with cls._lock:
            if cls._initialized:
                return
            
            # 中国移动主要IP段（CIDR格式）
            cls._mobile_networks = [
                ipaddress.ip_network("223.64.0.0/11"),
                ipaddress.ip_network("223.96.0.0/12"),
                ipaddress.ip_network("223.112.0.0/14"),
                ipaddress.ip_network("36.0.0.0/8"),
                ipaddress.ip_network("39.128.0.0/10"),
                ipaddress.ip_network("120.192.0.0/10"),
                ipaddress.ip_network("111.0.0.0/10"),
                ipaddress.ip_network("112.0.0.0/11"),
                ipaddress.ip_network("117.128.0.0/10"),
                ipaddress.ip_network("183.192.0.0/10"),
            ]
            
            # 中国联通主要IP段
            cls._unicom_networks = [
                ipaddress.ip_network("60.0.0.0/11"),
                ipaddress.ip_network("61.128.0.0/10"),
                ipaddress.ip_network("106.0.0.0/9"),
                ipaddress.ip_network("110.128.0.0/11"),
                ipaddress.ip_network("112.0.0.0/12"),
                ipaddress.ip_network("113.0.0.0/9"),
                ipaddress.ip_network("115.0.0.0/10"),
                ipaddress.ip_network("116.0.0.0/9"),
                ipaddress.ip_network("118.0.0.0/11"),
                ipaddress.ip_network("119.0.0.0/10"),
                ipaddress.ip_network("123.0.0.0/9"),
                ipaddress.ip_network("124.0.0.0/11"),
                ipaddress.ip_network("125.0.0.0/10"),
                ipaddress.ip_network("140.0.0.0/9"),
                ipaddress.ip_network("153.0.0.0/10"),
                ipaddress.ip_network("180.128.0.0/10"),
                ipaddress.ip_network("202.96.0.0/12"),
                ipaddress.ip_network("210.0.0.0/10"),
                ipaddress.ip_network("211.0.0.0/11"),
                ipaddress.ip_network("218.0.0.0/9"),
                ipaddress.ip_network("219.128.0.0/10"),
                ipaddress.ip_network("220.128.0.0/11"),
                ipaddress.ip_network("221.0.0.0/10"),
                ipaddress.ip_network("222.0.0.0/9"),
            ]
            
            # 中国电信主要IP段
            cls._telecom_networks = [
                ipaddress.ip_network("1.0.0.0/8"),
                ipaddress.ip_network("14.0.0.0/8"),
                ipaddress.ip_network("27.0.0.0/8"),
                ipaddress.ip_network("36.0.0.0/8"),
                ipaddress.ip_network("42.0.0.0/8"),
                ipaddress.ip_network("49.0.0.0/8"),
                ipaddress.ip_network("58.0.0.0/8"),
                ipaddress.ip_network("59.0.0.0/8"),
                ipaddress.ip_network("60.0.0.0/8"),
                ipaddress.ip_network("61.0.0.0/8"),
                ipaddress.ip_network("101.0.0.0/8"),
                ipaddress.ip_network("106.0.0.0/8"),
                ipaddress.ip_network("110.0.0.0/8"),
                ipaddress.ip_network("111.0.0.0/8"),
                ipaddress.ip_network("112.0.0.0/8"),
                ipaddress.ip_network("113.0.0.0/8"),
                ipaddress.ip_network("114.0.0.0/8"),
                ipaddress.ip_network("115.0.0.0/8"),
                ipaddress.ip_network("116.0.0.0/8"),
                ipaddress.ip_network("117.0.0.0/8"),
                ipaddress.ip_network("118.0.0.0/8"),
                ipaddress.ip_network("119.0.0.0/8"),
                ipaddress.ip_network("120.0.0.0/8"),
                ipaddress.ip_network("121.0.0.0/8"),
                ipaddress.ip_network("122.0.0.0/8"),
                ipaddress.ip_network("123.0.0.0/8"),
                ipaddress.ip_network("124.0.0.0/8"),
                ipaddress.ip_network("125.0.0.0/8"),
                ipaddress.ip_network("126.0.0.0/8"),
                ipaddress.ip_network("180.0.0.0/8"),
                ipaddress.ip_network("182.0.0.0/8"),
                ipaddress.ip_network("183.0.0.0/8"),
                ipaddress.ip_network("202.0.0.0/8"),
                ipaddress.ip_network("210.0.0.0/8"),
                ipaddress.ip_network("211.0.0.0/8"),
                ipaddress.ip_network("218.0.0.0/8"),
                ipaddress.ip_network("219.0.0.0/8"),
                ipaddress.ip_network("220.0.0.0/8"),
                ipaddress.ip_network("221.0.0.0/8"),
                ipaddress.ip_network("222.0.0.0/8"),
                ipaddress.ip_network("223.0.0.0/8"),
            ]
            
            cls._initialized = True
            logger.info_with_extra(
                "CGNAT检测器初始化完成",
                mobile_networks=len(cls._mobile_networks),
                unicom_networks=len(cls._unicom_networks),
                telecom_networks=len(cls._telecom_networks)
            )
    
    @classmethod
    def detect(cls, ip: str, isp: str = "") -> tuple[bool, str]:
        """
        检测IP是否可能是CGNAT共享出口
        
        Args:
            ip: IP地址
            isp: 运营商名称
            
        Returns:
            tuple[bool, str]: (是否可能是CGNAT, 检测原因)
        """
        cls._init_networks()
        
        try:
            ip_addr = ipaddress.ip_address(ip)
            if ip_addr.version != 4:
                return False, ""
        except ValueError:
            return False, ""
        
        # 检查私有IP
        if ip_addr.is_private:
            return True, "私有IP地址，位于NAT网关后"
        
        # 检查运营商关键词
        is_mobile_isp = any(kw in isp for kw in cls.MOBILE_KEYWORDS)
        is_unicom_isp = any(kw in isp for kw in cls.UNICOM_KEYWORDS)
        is_telecom_isp = any(kw in isp for kw in cls.TELECOM_KEYWORDS)
        
        # 检查IP段
        for network in cls._mobile_networks:
            if ip_addr in network:
                return True, "中国移动网络，可能使用CGNAT共享出口IP"
        
        for network in cls._unicom_networks:
            if ip_addr in network:
                return True, "中国联通网络，可能使用CGNAT共享出口IP"
        
        for network in cls._telecom_networks:
            if ip_addr in network:
                return True, "中国电信网络，可能使用CGNAT共享出口IP"
        
        # 根据运营商关键词判断
        if is_mobile_isp:
            return True, "中国移动网络，可能使用CGNAT共享出口IP"
        if is_unicom_isp:
            return True, "中国联通网络，可能使用CGNAT共享出口IP"
        if is_telecom_isp:
            return True, "中国电信网络，可能使用CGNAT共享出口IP"
        
        return False, ""


class FusionEngine:
    """
    多数据源融合引擎
    
    特性：
    - 查询缓存（TTLCache）
    - 数据库故障降级
    - 多数据源投票机制
    - 结果标准化处理
    - 数据库预加载
    - 数据库文件变化自动检测与热重载
    """
    
    def __init__(self):
        """
        初始化融合引擎
        """
        self._ip2region_v4 = None
        self._ip2region_v6 = None
        self._ip2region_v4_buffer = None
        self._ip2region_v6_buffer = None
        self._qqwry = None
        
        self._cache: CacheManager = create_ip_location_cache(maxsize=50000, ttl=3600)
        
        self._source_status = {
            "qqwry": {"available": False, "error": None},
            "ip2region_v4": {"available": False, "error": None},
            "ip2region_v6": {"available": False, "error": None},
        }
        
        self._db_mtimes: Dict[str, float] = {}
        self._reload_lock = threading.Lock()
    
    def _get_db_mtime(self, path: Path) -> float:
        """
        获取数据库文件修改时间
        
        Args:
            path: 文件路径
            
        Returns:
            float: 修改时间戳，文件不存在返回0
        """
        try:
            return os.path.getmtime(path) if path.exists() else 0
        except OSError:
            return 0
    
    def _check_db_changed(self) -> bool:
        """
        检查数据库文件是否有变化
        
        Returns:
            bool: 是否有变化
        """
        base_dir = Path(config.DB_PATH).parent
        db_files = [
            base_dir / "qqwry.ipdb",
            base_dir / "ip2region_v4.xdb",
            base_dir / "ip2region_v6.xdb",
        ]
        
        for db_file in db_files:
            current_mtime = self._get_db_mtime(db_file)
            stored_mtime = self._db_mtimes.get(str(db_file), 0)
            if current_mtime > 0 and current_mtime != stored_mtime:
                return True
        return False
    
    def _update_db_mtimes(self):
        """
        更新数据库文件修改时间记录
        """
        base_dir = Path(config.DB_PATH).parent
        db_files = [
            base_dir / "qqwry.ipdb",
            base_dir / "ip2region_v4.xdb",
            base_dir / "ip2region_v6.xdb",
        ]
        
        for db_file in db_files:
            self._db_mtimes[str(db_file)] = self._get_db_mtime(db_file)
    
    def _reload_if_changed(self):
        """
        检测数据库变化并自动重载
        """
        if self._check_db_changed():
            with self._reload_lock:
                if self._check_db_changed():
                    logger.info("检测到数据库文件变化，开始热重载...")
                    self._cache.clear()
                    self._init_qqwry()
                    self._init_ip2region(4)
                    self._init_ip2region(6)
                    self._update_db_mtimes()
                    logger.info("数据库热重载完成")
    
    def preload_all(self):
        """
        预加载所有数据库
        """
        logger.info("开始预加载数据库...")
        self._init_qqwry()
        self._init_ip2region(4)
        self._init_ip2region(6)
        self._update_db_mtimes()
        
        available_count = sum(1 for s in self._source_status.values() if s["available"])
        logger.info_with_extra(
            "数据库预加载完成",
            available_sources=available_count,
            status=self._source_status
        )
    
    def _init_qqwry(self):
        """
        初始化纯真IP数据库（ipdb格式，支持IPv4/IPv6）
        """
        try:
            import ipdb
            
            base_dir = Path(config.DB_PATH).parent
            qqwry_path = base_dir / "qqwry.ipdb"
            
            if qqwry_path.exists():
                self._qqwry = ipdb.City(str(qqwry_path))
                self._source_status["qqwry"]["available"] = True
                logger.info_with_extra(
                    "纯真IP数据库加载成功", 
                    db_path=str(qqwry_path),
                    is_ipv4=self._qqwry.is_ipv4(),
                    is_ipv6=self._qqwry.is_ipv6()
                )
            else:
                self._source_status["qqwry"]["error"] = "数据库文件不存在"
        except ImportError:
            self._source_status["qqwry"]["error"] = "ipip-ipdb库未安装"
            logger.warning("ipip-ipdb库未安装，纯真数据源不可用")
        except Exception as e:
            self._source_status["qqwry"]["error"] = str(e)
            logger.error_with_extra("纯真IP数据库加载失败", exc_info=True, error=str(e))
    
    def _init_ip2region(self, version: int = 4):
        """
        初始化ip2region搜索器
        
        Args:
            version: IP版本 (4 或 6)
        """
        key = f"ip2region_v{version}"
        
        if version == 4 and self._ip2region_v4 is None:
            try:
                import ip2region.util as util
                import ip2region.searcher as xdb
                
                base_dir = Path(config.DB_PATH).parent
                db_path = base_dir / "ip2region_v4.xdb"
                if not db_path.exists():
                    db_path = base_dir / "ip2region.xdb"
                
                if db_path.exists():
                    self._ip2region_v4_buffer = util.load_content_from_file(str(db_path))
                    self._ip2region_v4 = xdb.new_with_buffer(util.IPv4, self._ip2region_v4_buffer)
                    self._source_status[key]["available"] = True
                    logger.info_with_extra("ip2region IPv4数据库加载成功", db_path=str(db_path))
                else:
                    self._source_status[key]["error"] = "数据库文件不存在"
            except Exception as e:
                self._source_status[key]["error"] = str(e)
                logger.error_with_extra("ip2region IPv4数据库加载失败", exc_info=True, error=str(e))
        
        elif version == 6 and self._ip2region_v6 is None:
            try:
                import ip2region.util as util
                import ip2region.searcher as xdb
                
                base_dir = Path(config.DB_PATH).parent
                db_path = base_dir / "ip2region_v6.xdb"
                
                if db_path.exists():
                    self._ip2region_v6_buffer = util.load_content_from_file(str(db_path))
                    self._ip2region_v6 = xdb.new_with_buffer(util.IPv6, self._ip2region_v6_buffer)
                    self._source_status[key]["available"] = True
                    logger.info_with_extra("ip2region IPv6数据库加载成功", db_path=str(db_path))
                else:
                    self._source_status[key]["error"] = "数据库文件不存在"
            except Exception as e:
                self._source_status[key]["error"] = str(e)
                logger.error_with_extra("ip2region IPv6数据库加载失败", exc_info=True, error=str(e))
    
    def _query_ip2region(self, ip: str) -> Optional[LocationSource]:
        """
        从ip2region查询IP位置（带故障降级）
        
        Args:
            ip: IP地址
            
        Returns:
            LocationSource: 查询结果
        """
        try:
            ip_version = self._get_ip_version(ip)
            
            if ip_version == 4:
                self._init_ip2region(4)
                if self._ip2region_v4:
                    result = self._ip2region_v4.search(ip)
                    return self._parse_ip2region_result(ip, result, "ip2region")
            elif ip_version == 6:
                self._init_ip2region(6)
                if self._ip2region_v6:
                    result = self._ip2region_v6.search(ip)
                    return self._parse_ip2region_result(ip, result, "ip2region")
        except Exception as e:
            logger.debug_with_extra("ip2region查询失败", ip=ip, error=str(e))
            self._source_status[f"ip2region_v{self._get_ip_version(ip)}"]["available"] = False
        
        return None
    
    def _parse_ip2region_result(self, ip: str, result: str, source: str) -> LocationSource:
        """
        解析ip2region返回结果
        
        Args:
            ip: IP地址
            result: 原始结果字符串
            source: 数据源名称
            
        Returns:
            LocationSource: 解析后的结果
        """
        if not result:
            return LocationSource(source=source)
        
        parts = result.split("|")
        
        return LocationSource(
            source=source,
            country=parts[0] if len(parts) > 0 else "",
            province=parts[1] if len(parts) > 1 else "",
            city=parts[2] if len(parts) > 2 else "",
            isp=parts[3] if len(parts) > 3 else "",
            country_code=parts[4] if len(parts) > 4 else "",
        )
    
    def _query_qqwry(self, ip: str) -> Optional[LocationSource]:
        """
        从纯真IP数据库查询IP位置（带故障降级）
        支持 IPv4 和 IPv6
        
        Args:
            ip: IP地址
            
        Returns:
            LocationSource: 查询结果
        """
        try:
            self._init_qqwry()
            if self._qqwry:
                # 使用 find_map 获取字典格式结果
                result = self._qqwry.find_map(ip, "CN")
                if result:
                    return self._parse_qqwry_result(ip, result)
        except Exception as e:
            logger.debug_with_extra("纯真IP查询失败", ip=ip, error=str(e))
            self._source_status["qqwry"]["available"] = False
        
        return None
    
    def _parse_qqwry_result(self, ip: str, result: dict) -> LocationSource:
        """
        解析纯真IP数据库返回结果（ipdb格式）
        
        Args:
            ip: IP地址
            result: 纯真返回的字典
            
        Returns:
            LocationSource: 解析后的结果
        """
        if not result:
            return LocationSource(source="qqwry")
        
        return LocationSource(
            source="qqwry",
            country=result.get("country_name", ""),
            province=result.get("region_name", ""),
            city=result.get("city_name", ""),
            isp=result.get("isp_domain", ""),
            country_code=result.get("country_code", ""),
        )
    
    @staticmethod
    def _get_ip_version(ip: str) -> int:
        """
        获取IP版本
        
        Args:
            ip: IP地址
            
        Returns:
            int: IP版本 (4 或 6)
        """
        try:
            addr = ipaddress.ip_address(ip)
            return addr.version
        except ValueError:
            return 0
    
    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """
        验证IP地址格式
        
        Args:
            ip: IP地址
            
        Returns:
            bool: 是否有效
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    
    def _vote_fuse_results(self, ip: str, sources: List[LocationSource]) -> FusedLocation:
        """
        使用投票机制融合多个数据源的结果
        
        Args:
            ip: IP地址
            sources: 数据源列表
            
        Returns:
            FusedLocation: 融合后的结果
        """
        if not sources:
            return FusedLocation(ip=ip, accuracy=AccuracyLevel.UNKNOWN)
        
        normalized_sources = [LocationNormalizer.normalize(s) for s in sources]
        
        country_votes = Counter(s.country for s in normalized_sources if s.country)
        province_votes = Counter(s.province for s in normalized_sources if s.province)
        city_votes = Counter(s.city for s in normalized_sources if s.city)
        isp_votes = Counter(s.isp for s in normalized_sources if s.isp)
        
        country = country_votes.most_common(1)[0][0] if country_votes else ""
        province = province_votes.most_common(1)[0][0] if province_votes else ""
        city = city_votes.most_common(1)[0][0] if city_votes else ""
        isp = isp_votes.most_common(1)[0][0] if isp_votes else ""
        
        is_china = country == "中国" or any(s.country_code == "CN" for s in normalized_sources)
        
        country_code = "CN" if is_china else ""
        if not is_china:
            for s in normalized_sources:
                if s.country_code:
                    country_code = s.country_code
                    break
        
        is_cgnat, cgnat_reason = CGNATDetector.detect(ip, isp)
        
        has_city = city and city not in ["0", "", "未知"]
        sources_match = len(sources) >= 2 and all(
            s.country == normalized_sources[0].country for s in normalized_sources[1:]
        )
        
        if is_cgnat:
            accuracy = AccuracyLevel.LOW
            accuracy_note = cgnat_reason + "，定位结果可能存在偏差"
        elif sources_match and has_city:
            accuracy = AccuracyLevel.HIGH
            accuracy_note = ""
        elif has_city or sources_match:
            accuracy = AccuracyLevel.MEDIUM
            accuracy_note = ""
        else:
            accuracy = AccuracyLevel.LOW
            accuracy_note = "定位精度较低，结果仅供参考"
        
        return FusedLocation(
            ip=ip,
            country=country,
            province=province,
            city=city,
            isp=isp,
            country_code=country_code,
            is_china=is_china,
            ip_version=self._get_ip_version(ip),
            accuracy=accuracy,
            accuracy_note=accuracy_note,
            is_cgnat=is_cgnat,
            sources=sources,
        )
    
    def query(self, ip: str) -> Optional[FusedLocation]:
        """
        查询IP地址的融合定位结果
        
        Args:
            ip: IP地址
            
        Returns:
            FusedLocation: 融合定位结果
        """
        if not self._is_valid_ip(ip):
            logger.debug_with_extra("无效的IP地址", ip=ip)
            return None
        
        self._reload_if_changed()
        
        cached_result = self._cache.get(ip)
        if cached_result:
            cached_result.cached = True
            return cached_result
        
        sources: List[LocationSource] = []
        
        qqwry_result = self._query_qqwry(ip)
        if qqwry_result:
            sources.append(qqwry_result)
        
        ip2region_result = self._query_ip2region(ip)
        if ip2region_result:
            sources.append(ip2region_result)
        
        result = self._vote_fuse_results(ip, sources)
        
        if result:
            self._cache.set(ip, result)
        
        return result
    
    def get_cache_stats(self) -> dict:
        """
        获取缓存统计信息
        
        Returns:
            dict: 缓存统计信息
        """
        stats = self._cache.get_stats()
        return stats.to_dict()
    
    def clear_cache(self):
        """
        清空缓存
        """
        self._cache.clear()
        logger.info("缓存已清空")
    
    def get_source_status(self) -> dict:
        """
        获取数据源状态
        
        Returns:
            dict: 数据源状态
        """
        return self._source_status.copy()
    
    def close(self):
        """
        关闭所有数据库连接
        """
        if self._ip2region_v4:
            try:
                self._ip2region_v4.close()
            except:
                pass
            self._ip2region_v4 = None
        
        if self._ip2region_v6:
            try:
                self._ip2region_v6.close()
            except:
                pass
            self._ip2region_v6 = None


fusion_engine = FusionEngine()
