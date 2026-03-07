"""
IP查询核心模块
封装ip2region库实现高性能IP地理位置查询
支持IPv4和IPv6双栈查询
"""

import ipaddress
from dataclasses import dataclass
from typing import Optional, Literal
from pathlib import Path

from ip_location_api.config import config


@dataclass
class IPLocation:
    """
    IP定位结果数据类
    
    Attributes:
        ip: 查询的IP地址
        country: 国家
        province: 省份
        city: 城市
        isp: 运营商
        country_code: 国家代码
        is_china: 是否为中国IP
        ip_version: IP版本 (4 或 6)
    """
    ip: str
    country: str = ""
    province: str = ""
    city: str = ""
    isp: str = ""
    country_code: str = ""
    is_china: bool = False
    ip_version: int = 4
    
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
        }


class IPQueryEngine:
    """
    IP查询引擎
    
    使用ip2region库实现高性能IP地理位置查询，
    支持IPv4和IPv6双栈查询，内存缓存加速，实现10微秒级查询性能
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化查询引擎
        
        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        self.db_path = db_path or str(config.DB_PATH)
        self._ipv4_searcher = None
        self._ipv6_searcher = None
        self._ipv4_buffer = None
        self._ipv6_buffer = None
    
    def _get_db_path(self, version: Literal[4, 6]) -> Path:
        """
        获取指定版本的数据库路径
        
        Args:
            version: IP版本 (4 或 6)
            
        Returns:
            Path: 数据库文件路径
        """
        base_dir = Path(self.db_path).parent
        
        if version == 4:
            v4_path = base_dir / "ip2region_v4.xdb"
            if v4_path.exists():
                return v4_path
            legacy_path = base_dir / "ip2region.xdb"
            if legacy_path.exists():
                return legacy_path
        else:
            v6_path = base_dir / "ip2region_v6.xdb"
            if v6_path.exists():
                return v6_path
        
        return None
    
    def _init_ipv4_searcher(self):
        """
        初始化IPv4搜索器
        """
        if self._ipv4_searcher is None:
            try:
                import ip2region.util as util
                import ip2region.searcher as xdb
                
                db_path = self._get_db_path(4)
                if db_path and db_path.exists():
                    self._ipv4_buffer = util.load_content_from_file(str(db_path))
                    self._ipv4_searcher = xdb.new_with_buffer(util.IPv4, self._ipv4_buffer)
            except Exception as e:
                pass
    
    def _init_ipv6_searcher(self):
        """
        初始化IPv6搜索器
        """
        if self._ipv6_searcher is None:
            try:
                import ip2region.util as util
                import ip2region.searcher as xdb
                
                db_path = self._get_db_path(6)
                if db_path and db_path.exists():
                    self._ipv6_buffer = util.load_content_from_file(str(db_path))
                    self._ipv6_searcher = xdb.new_with_buffer(util.IPv6, self._ipv6_buffer)
            except Exception as e:
                pass
    
    def _parse_result(self, ip: str, result: str, ip_version: int) -> IPLocation:
        """
        解析查询结果
        
        ip2region返回格式: 国家|省份|城市|运营商|国家代码
        
        Args:
            ip: 查询的IP地址
            result: ip2region返回的原始结果字符串
            ip_version: IP版本
            
        Returns:
            IPLocation: 解析后的定位结果
        """
        if not result:
            return IPLocation(ip=ip, ip_version=ip_version)
        
        parts = result.split("|")
        
        country = parts[0] if len(parts) > 0 else ""
        province = parts[1] if len(parts) > 1 else ""
        city = parts[2] if len(parts) > 2 else ""
        isp = parts[3] if len(parts) > 3 else ""
        country_code = parts[4] if len(parts) > 4 else ""
        
        is_china = country == "中国"
        
        return IPLocation(
            ip=ip,
            country=country,
            province=province,
            city=city,
            isp=isp,
            country_code=country_code,
            is_china=is_china,
            ip_version=ip_version,
        )
    
    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """
        验证IP地址格式是否有效
        
        Args:
            ip: 待验证的IP地址字符串
            
        Returns:
            bool: IP地址是否有效
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def get_ip_version(ip: str) -> int:
        """
        获取IP地址版本
        
        Args:
            ip: IP地址字符串
            
        Returns:
            int: IP版本 (4 或 6)
        """
        try:
            addr = ipaddress.ip_address(ip)
            return addr.version
        except ValueError:
            return 0
    
    def query(self, ip: str) -> Optional[IPLocation]:
        """
        查询IP地址的地理位置
        
        自动识别IPv4/IPv6并使用对应数据库查询
        
        Args:
            ip: 要查询的IP地址
            
        Returns:
            IPLocation: 定位结果，查询失败返回None
        """
        if not self.is_valid_ip(ip):
            return None
        
        ip_version = self.get_ip_version(ip)
        
        try:
            if ip_version == 4:
                self._init_ipv4_searcher()
                if self._ipv4_searcher:
                    result = self._ipv4_searcher.search(ip)
                    return self._parse_result(ip, result, 4)
            elif ip_version == 6:
                self._init_ipv6_searcher()
                if self._ipv6_searcher:
                    result = self._ipv6_searcher.search(ip)
                    return self._parse_result(ip, result, 6)
            
            return IPLocation(ip=ip, ip_version=ip_version)
            
        except Exception as e:
            return None
    
    def close(self):
        """
        关闭搜索器，释放资源
        """
        if self._ipv4_searcher:
            try:
                self._ipv4_searcher.close()
            except:
                pass
            self._ipv4_searcher = None
        
        if self._ipv6_searcher:
            try:
                self._ipv6_searcher.close()
            except:
                pass
            self._ipv6_searcher = None


ip_engine = IPQueryEngine()
