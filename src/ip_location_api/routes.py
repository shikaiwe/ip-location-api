"""
API路由模块
定义所有HTTP接口端点
支持IPv4和IPv6双栈查询，多数据源融合定位
"""

import asyncio
import ipaddress
import time
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from ip_location_api.fusion import fusion_engine
from ip_location_api.logger import get_logger


logger = get_logger(__name__)


router = APIRouter()


def is_valid_ip(ip: str) -> bool:
    """
    验证IP地址格式是否有效
    
    Args:
        ip: IP地址字符串
        
    Returns:
        bool: 是否为有效的IPv4或IPv6地址
    """
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False


class IPLocationResponse(BaseModel):
    """
    IP定位API响应模型
    
    Attributes:
        code: 状态码，0表示成功
        message: 状态消息
        data: 定位数据
    """
    code: int = Field(default=0, description="状态码，0表示成功")
    message: str = Field(default="success", description="状态消息")
    data: Optional[dict] = Field(default=None, description="定位数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": 0,
                "message": "success",
                "data": {
                    "ip": "8.8.8.8",
                    "country": "United States",
                    "province": "California",
                    "city": "",
                    "isp": "Google LLC",
                    "country_code": "US",
                    "is_china": False,
                    "ip_version": 4,
                    "accuracy": "medium",
                    "is_cgnat": False,
                    "cached": False
                }
            }
        }


class HealthResponse(BaseModel):
    """
    健康检查响应模型
    
    Attributes:
        status: 服务状态
        databases: 数据库状态
        cache: 缓存状态
        timestamp: 时间戳
    """
    status: str = "ok"
    databases: dict = {}
    cache: dict = {}
    timestamp: float = 0


class RateLimiter:
    """
    请求限流器
    
    基于滑动窗口算法实现IP级别的请求限流
    """
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        """
        初始化限流器
        
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        """
        检查请求是否允许
        
        Args:
            client_ip: 客户端IP
            
        Returns:
            tuple[bool, int]: (是否允许, 剩余请求数)
        """
        async with self._lock:
            now = time.time()
            
            # 清理过期请求
            self.requests[client_ip] = [
                t for t in self.requests[client_ip]
                if now - t < self.window
            ]
            
            current_count = len(self.requests[client_ip])
            remaining = self.max_requests - current_count
            
            if current_count >= self.max_requests:
                return False, 0
            
            self.requests[client_ip].append(now)
            return True, remaining - 1
    
    def get_stats(self) -> dict:
        """
        获取限流统计信息
        
        Returns:
            dict: 统计信息
        """
        return {
            "tracked_ips": len(self.requests),
            "max_requests": self.max_requests,
            "window_seconds": self.window,
        }


limiter = RateLimiter(max_requests=200, window_seconds=60)


def get_client_ip(request: Request) -> str:
    """
    获取客户端真实IP地址
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        str: 客户端IP地址
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    if request.client:
        return request.client.host
    
    return "unknown"


@router.get("/", response_model=IPLocationResponse, summary="查询IP地理位置")
async def query_ip(
    request: Request,
    ip: Optional[str] = Query(
        None, 
        description="要查询的IP地址，支持IPv4和IPv6。不传则自动查询客户端IP", 
        examples=["8.8.8.8", "114.114.114.114", "240e:3b7:3272:d8d0:db09:c067:8d59:539e"]
    )
) -> IPLocationResponse:
    """
    查询指定IP地址的地理位置信息
    
    - **ip**: 要查询的IP地址，支持IPv4和IPv6格式（可选，不传则自动查询客户端IP）
    
    返回IP所属的国家、省份、城市、运营商等信息。
    - 国内IP可精确到城市级别（使用纯真数据库）
    - 国外IP精确到国家/省份级别
    - 自动识别IPv4/IPv6并使用对应数据库查询
    - 不传ip参数时自动查询请求客户端的IP位置
    - 包含精度提示和置信度评分
    """
    query_ip_addr = ip
    
    if not query_ip_addr:
        query_ip_addr = get_client_ip(request)
        
        if not query_ip_addr or query_ip_addr == "unknown":
            logger.warning("无法获取客户端IP地址")
            raise HTTPException(
                status_code=400,
                detail={"code": 400, "message": "无法获取客户端IP地址", "data": None}
            )
    
    if not is_valid_ip(query_ip_addr):
        logger.warning_with_extra("IP地址格式无效", ip=query_ip_addr)
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "IP地址格式无效", "data": {"ip": query_ip_addr}}
        )
    
    result = fusion_engine.query(query_ip_addr)
    if result is None:
        logger.error_with_extra("IP查询失败", ip=query_ip_addr)
        raise HTTPException(
            status_code=500,
            detail={"code": 500, "message": "IP查询失败", "data": {"ip": query_ip_addr}}
        )
    
    logger.info_with_extra(
        "IP查询成功", 
        ip=query_ip_addr, 
        country=result.country, 
        city=result.city,
        accuracy=result.accuracy.value,
        is_cgnat=result.is_cgnat,
        cached=result.cached
    )
    
    return IPLocationResponse(data=result.to_dict())


@router.get("/batch", response_model=IPLocationResponse, summary="批量查询IP地理位置")
async def batch_query_ip(
    request: Request,
    ips: str = Query(
        ..., 
        description="要查询的IP地址列表，逗号分隔，支持IPv4和IPv6混合", 
        examples=["8.8.8.8,114.114.114.114", "240e:3b7:3272:d8d0:db09:c067:8d59:539e,2001:4860:4860::8888"]
    )
) -> IPLocationResponse:
    """
    批量查询多个IP地址的地理位置信息
    
    - **ips**: 要查询的IP地址列表，多个IP用逗号分隔，最多支持100个
    - 支持IPv4和IPv6混合查询
    
    返回每个IP所属的国家、省份、城市、运营商等信息。
    包含精度提示和置信度评分。
    """
    # 限流检查
    client_ip = get_client_ip(request)
    allowed, remaining = await limiter.is_allowed(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"code": 429, "message": "请求过于频繁，请稍后重试", "data": {"retry_after": 60}}
        )
    
    ip_list = [ip.strip() for ip in ips.split(",") if ip.strip()]
    
    if not ip_list:
        logger.warning("批量查询IP列表为空")
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "IP地址列表不能为空"}
        )
    
    if len(ip_list) > 100:
        logger.warning_with_extra("批量查询IP数量超限", count=len(ip_list))
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "单次最多查询100个IP地址"}
        )
    
    valid_ips = []
    invalid_ips = []
    for ip in ip_list:
        if is_valid_ip(ip):
            valid_ips.append(ip)
        else:
            invalid_ips.append(ip)
    
    if invalid_ips:
        logger.warning_with_extra("批量查询包含无效IP", invalid_count=len(invalid_ips), invalid_ips=invalid_ips[:5])
    
    if not valid_ips:
        return IPLocationResponse(
            code=400,
            message="所有IP地址格式无效",
            data={"invalid_ips": invalid_ips}
        )
    
    logger.debug_with_extra("开始批量查询", ip_count=len(valid_ips), invalid_count=len(invalid_ips))
    
    async def query_one(ip: str) -> tuple[str, Optional[dict]]:
        """
        异步查询单个IP
        
        Args:
            ip: IP地址
            
        Returns:
            tuple[str, Optional[dict]]: (IP地址, 查询结果)
        """
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, fusion_engine.query, ip)
        return ip, result.to_dict() if result else {"error": "查询失败"}
    
    tasks = [query_one(ip) for ip in valid_ips]
    results_list = await asyncio.gather(*tasks)
    
    results = dict(results_list)
    
    for ip in invalid_ips:
        results[ip] = {"error": "无效的IP地址格式"}
    
    success_count = len([r for r in results.values() if "error" not in r])
    logger.info_with_extra("批量查询完成", total=len(ip_list), valid=len(valid_ips), success=success_count)
    
    return IPLocationResponse(data=results)


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health_check() -> HealthResponse:
    """
    服务健康检查接口
    
    返回服务运行状态、数据库可用性和缓存统计。
    包含探测查询验证数据库实际可用性。
    """
    # 探测查询验证数据库可用性
    test_results = {}
    
    try:
        test_result = fusion_engine.query("114.114.114.114")
        test_results["qqwry"] = test_result is not None and test_result.country == "中国"
    except:
        test_results["qqwry"] = False
    
    try:
        test_result = fusion_engine.query("8.8.8.8")
        test_results["ip2region"] = test_result is not None
    except:
        test_results["ip2region"] = False
    
    source_status = fusion_engine.get_source_status()
    all_healthy = all(test_results.values()) and any(source_status[s]["available"] for s in source_status)
    
    return HealthResponse(
        status="ok" if all_healthy else "degraded",
        databases={
            "qqwry": source_status.get("qqwry", {}),
            "ip2region_v4": source_status.get("ip2region_v4", {}),
            "ip2region_v6": source_status.get("ip2region_v6", {}),
            "test_results": test_results,
        },
        cache=fusion_engine.get_cache_stats(),
        timestamp=time.time()
    )


@router.get("/stats", response_model=IPLocationResponse, summary="服务统计")
async def get_stats() -> IPLocationResponse:
    """
    获取服务统计信息
    
    返回数据库状态、缓存统计、限流统计等信息。
    """
    return IPLocationResponse(
        data={
            "database": fusion_engine.get_source_status(),
            "cache": fusion_engine.get_cache_stats(),
            "rate_limiter": limiter.get_stats(),
        }
    )


@router.get("/clear-cache", response_model=IPLocationResponse, summary="清空缓存")
async def clear_cache() -> IPLocationResponse:
    """
    清空查询缓存
    
    清空所有已缓存的IP查询结果。
    """
    fusion_engine.clear_cache()
    logger.info("缓存清空请求")
    return IPLocationResponse(message="缓存已清空")


@router.get("/myip", summary="获取客户端IP")
async def get_my_ip(request: Request):
    """
    获取请求客户端的IP地址和位置信息
    
    自动检测客户端真实IP（支持代理环境）并返回位置信息。
    包含精度提示和置信度评分。
    """
    client_ip = get_client_ip(request)
    
    if not client_ip or client_ip == "unknown":
        return {"your_ip": None, "location": None}
    
    if not is_valid_ip(client_ip):
        logger.warning_with_extra("客户端IP格式无效", ip=client_ip)
        return {"your_ip": client_ip, "location": None, "error": "IP地址格式无效"}
    
    location = None
    result = fusion_engine.query(client_ip)
    if result:
        location = result.to_dict()
    
    return {
        "your_ip": client_ip,
        "location": location
    }
