"""
API路由模块
定义所有HTTP接口端点
支持IPv4和IPv6双栈查询
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from ip_location_api.query import ip_engine, IPLocation
from ip_location_api.cache import ip_cache
from ip_location_api.logger import get_logger


logger = get_logger(__name__)


router = APIRouter()


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
                    "city": "0",
                    "isp": "Google LLC",
                    "country_code": "US",
                    "is_china": False,
                    "ip_version": 4
                }
            }
        }


class HealthResponse(BaseModel):
    """
    健康检查响应模型
    
    Attributes:
        status: 服务状态
        cache_stats: 缓存统计信息
        ipv4_available: IPv4数据库是否可用
        ipv6_available: IPv6数据库是否可用
    """
    status: str = "ok"
    cache_stats: Optional[dict] = None
    ipv4_available: bool = False
    ipv6_available: bool = False


class ErrorResponse(BaseModel):
    """
    错误响应模型
    
    Attributes:
        code: 错误码
        message: 错误消息
        data: 附加数据
    """
    code: int
    message: str
    data: Optional[dict] = None


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
    - 国内IP可精确到城市级别
    - 国外IP精确到国家/省份级别
    - 自动识别IPv4/IPv6并使用对应数据库查询
    - 不传ip参数时自动查询请求客户端的IP位置
    """
    query_ip_addr = ip
    
    if not query_ip_addr:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            query_ip_addr = forwarded_for.split(",")[0].strip()
        
        if not query_ip_addr:
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                query_ip_addr = real_ip.strip()
        
        if not query_ip_addr:
            query_ip_addr = request.client.host if request.client else None
        
        if not query_ip_addr:
            logger.warning("无法获取客户端IP地址")
            raise HTTPException(
                status_code=400,
                detail={"code": 400, "message": "无法获取客户端IP地址", "data": None}
            )
    
    if not ip_engine.is_valid_ip(query_ip_addr):
        logger.warning_with_extra("无效的IP地址格式", ip=query_ip_addr)
        raise HTTPException(
            status_code=400,
            detail={"code": 400, "message": "无效的IP地址格式", "data": {"ip": query_ip_addr}}
        )
    
    cached_result = ip_cache.get(query_ip_addr)
    if cached_result:
        logger.debug_with_extra("缓存命中", ip=query_ip_addr, cache_hit=True)
        return IPLocationResponse(data=cached_result.to_dict())
    
    result = ip_engine.query(query_ip_addr)
    if result is None:
        logger.error_with_extra("IP查询失败", ip=query_ip_addr)
        raise HTTPException(
            status_code=500,
            detail={"code": 500, "message": "IP查询失败", "data": {"ip": query_ip_addr}}
        )
    
    ip_cache.set(query_ip_addr, result)
    logger.info_with_extra("IP查询成功", ip=query_ip_addr, country=result.country, city=result.city)
    
    return IPLocationResponse(data=result.to_dict())


@router.get("/batch", response_model=IPLocationResponse, summary="批量查询IP地理位置")
async def batch_query_ip(
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
    """
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
    
    logger.debug_with_extra("开始批量查询", ip_count=len(ip_list))
    
    results = {}
    cache_hits = 0
    for ip in ip_list:
        if not ip_engine.is_valid_ip(ip):
            results[ip] = {"error": "无效的IP地址格式"}
            continue
        
        cached_result = ip_cache.get(ip)
        if cached_result:
            results[ip] = cached_result.to_dict()
            cache_hits += 1
            continue
        
        result = ip_engine.query(ip)
        if result:
            ip_cache.set(ip, result)
            results[ip] = result.to_dict()
        else:
            results[ip] = {"error": "查询失败"}
    
    logger.info_with_extra("批量查询完成", total=len(ip_list), cache_hits=cache_hits, success=len(results))
    
    return IPLocationResponse(data=results)


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health_check() -> HealthResponse:
    """
    服务健康检查接口
    
    返回服务运行状态、缓存统计信息和数据库可用性。
    """
    stats = ip_cache.get_stats()
    
    ipv4_available = ip_engine._get_db_path(4) is not None
    ipv6_available = ip_engine._get_db_path(6) is not None
    
    return HealthResponse(
        status="ok",
        cache_stats={
            "hits": stats.hits,
            "misses": stats.misses,
            "hit_rate": f"{stats.hit_rate:.2%}",
            "size": stats.size,
            "max_size": stats.max_size,
        },
        ipv4_available=ipv4_available,
        ipv6_available=ipv6_available,
    )


@router.get("/stats", response_model=IPLocationResponse, summary="缓存统计")
async def get_stats() -> IPLocationResponse:
    """
    获取缓存统计信息
    
    返回缓存命中率、缓存大小等统计数据。
    """
    stats = ip_cache.get_stats()
    
    ipv4_available = ip_engine._get_db_path(4) is not None
    ipv6_available = ip_engine._get_db_path(6) is not None
    
    return IPLocationResponse(
        data={
            "cache": {
                "hits": stats.hits,
                "misses": stats.misses,
                "hit_rate": stats.hit_rate,
                "size": stats.size,
                "max_size": stats.max_size,
            },
            "database": {
                "ipv4_available": ipv4_available,
                "ipv6_available": ipv6_available,
            }
        }
    )


@router.get("/clear-cache", response_model=IPLocationResponse, summary="清空缓存")
async def clear_cache() -> IPLocationResponse:
    """
    清空查询缓存
    
    清空所有已缓存的IP查询结果。
    """
    ip_cache.clear()
    logger.info("缓存已清空")
    return IPLocationResponse(message="缓存已清空")


@router.get("/myip", summary="获取客户端IP")
async def get_my_ip(request: Request):
    """
    获取请求客户端的IP地址和位置信息
    
    自动检测客户端真实IP（支持代理环境）并返回位置信息。
    """
    client_ip = None
    
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    if not client_ip:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip.strip()
    
    if not client_ip:
        client_ip = request.client.host if request.client else None
    
    if not client_ip:
        return {"your_ip": None, "location": None}
    
    location = None
    if ip_engine.is_valid_ip(client_ip):
        cached_result = ip_cache.get(client_ip)
        if cached_result:
            location = cached_result.to_dict()
        else:
            result = ip_engine.query(client_ip)
            if result:
                ip_cache.set(client_ip, result)
                location = result.to_dict()
    
    return {
        "your_ip": client_ip,
        "location": location
    }
