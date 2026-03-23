"""
日志中间件模块
提供请求ID追踪、请求/响应日志记录等功能
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ip_location_api.logger import (
    get_logger, set_request_id, set_user_id, clear_context, LogContext
)


logger = get_logger(__name__)


def generate_request_id() -> str:
    """
    生成唯一的请求ID
    
    Returns:
        str: UUID格式的请求ID
    """
    return str(uuid.uuid4()).replace("-", "")[:16]


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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    
    功能：
    - 自动生成请求ID并注入上下文
    - 记录请求开始和结束日志
    - 记录请求耗时
    - 记录响应状态码
    - 异常自动记录堆栈
    """
    
    def __init__(self, app: ASGIApp, exclude_paths: list = None):
        """
        初始化中间件
        
        Args:
            app: ASGI应用
            exclude_paths: 排除的路径列表（不记录日志）
        """
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/favicon.ico"]
    
    def _should_skip_logging(self, path: str) -> bool:
        """
        判断是否跳过日志记录
        
        Args:
            path: 请求路径
            
        Returns:
            bool: 是否跳过
        """
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True
        return False
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求
        
        Args:
            request: 请求对象
            call_next: 下一个处理函数
            
        Returns:
            Response: 响应对象
        """
        if self._should_skip_logging(request.url.path):
            return await call_next(request)
        
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        client_ip = get_client_ip(request)
        
        set_request_id(request_id)
        
        start_time = time.time()
        
        logger.info_with_extra(
            f"请求开始: {request.method} {request.url.path}",
            request_method=request.method,
            request_path=request.url.path,
            request_query=str(request.query_params) if request.query_params else None,
            client_ip=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
            request_id=request_id
        )
        
        try:
            response = await call_next(request)
            
            duration_ms = (time.time() - start_time) * 1000
            
            log_level = "info" if response.status_code < 400 else "warning"
            
            getattr(logger, log_level + "_with_extra")(
                f"请求完成: {request.method} {request.url.path} - {response.status_code}",
                request_method=request.method,
                request_path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                client_ip=client_ip,
                request_id=request_id
            )
            
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            return response
            
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            
            logger.error_with_extra(
                f"请求异常: {request.method} {request.url.path} - {str(exc)}",
                exc_info=True,
                request_method=request.method,
                request_path=request.url.path,
                duration_ms=round(duration_ms, 2),
                client_ip=client_ip,
                request_id=request_id,
                error_type=type(exc).__name__,
                error_message=str(exc)
            )
            
            raise
        
        finally:
            clear_context()


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """
    慢请求监控中间件
    
    记录超过阈值的慢请求，用于性能监控
    """
    
    def __init__(self, app: ASGIApp, threshold_ms: float = 1000):
        """
        初始化中间件
        
        Args:
            app: ASGI应用
            threshold_ms: 慢请求阈值（毫秒）
        """
        super().__init__(app)
        self.threshold_ms = threshold_ms
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求
        
        Args:
            request: 请求对象
            call_next: 下一个处理函数
            
        Returns:
            Response: 响应对象
        """
        start_time = time.time()
        
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        
        if duration_ms > self.threshold_ms:
            client_ip = get_client_ip(request)
            
            logger.warning_with_extra(
                f"慢请求告警: {request.method} {request.url.path} 耗时 {duration_ms:.2f}ms",
                request_method=request.method,
                request_path=request.url.path,
                duration_ms=round(duration_ms, 2),
                threshold_ms=self.threshold_ms,
                client_ip=client_ip
            )
        
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    访问日志中间件
    
    记录所有HTTP请求的访问日志，类似Nginx access log格式
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求
        
        Args:
            request: 请求对象
            call_next: 下一个处理函数
            
        Returns:
            Response: 响应对象
        """
        start_time = time.time()
        client_ip = get_client_ip(request)
        
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        
        logger.info_with_extra(
            "access_log",
            client_ip=client_ip,
            request_method=request.method,
            request_path=request.url.path,
            request_query=str(request.query_params) if request.query_params else None,
            status_code=response.status_code,
            response_size=response.headers.get("content-length", "-"),
            duration_ms=round(duration_ms, 2),
            user_agent=request.headers.get("User-Agent", "-"),
            referer=request.headers.get("Referer", "-")
        )
        
        return response
