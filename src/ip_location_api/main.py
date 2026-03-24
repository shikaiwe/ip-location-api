"""
FastAPI主应用
IP定位API服务入口
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import time

from ip_location_api.config import config
from ip_location_api.routes import router as api_router
from ip_location_api.fusion import fusion_engine
from ip_location_api.logger import LoggerManager, get_logger
from ip_location_api.logging_middleware import RequestLoggingMiddleware, SlowRequestMiddleware
from ip_location_api.exceptions import IPQueryException


LoggerManager.setup()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    
    启动时预加载数据库，关闭时清理资源
    """
    logger.info_with_extra(
        "IP定位API服务启动中",
        db_path=str(config.DB_PATH),
        workers=config.WORKERS,
        port=config.PORT
    )
    
    # 预加载所有数据库
    fusion_engine.preload_all()
    
    yield
    
    logger.info("IP定位API服务关闭中")
    fusion_engine.close()


app = FastAPI(
    title="IP地理位置查询API",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SlowRequestMiddleware, threshold_ms=500)


@app.exception_handler(IPQueryException)
async def ip_query_exception_handler(request: Request, exc: IPQueryException):
    """
    IP查询业务异常处理器
    """
    logger.warning_with_extra(
        f"业务异常: {exc.message}",
        code=exc.code,
        path=request.url.path
    )
    return JSONResponse(
        status_code=exc.code if exc.code < 500 else 500,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": exc.data
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    
    捕获所有未处理的异常，返回统一格式
    """
    logger.error_with_extra(
        f"未处理的异常: {str(exc)}",
        exc_info=True,
        path=request.url.path,
        error_type=type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None
        }
    )


app.include_router(api_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """
    根路径欢迎页面
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>IP地理位置查询API</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 16px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 { color: #333; margin-bottom: 10px; }
            p { color: #666; margin-bottom: 10px; }
            .endpoint { color: #888; font-size: 14px; margin-top: 20px; }
            code { background: #f5f5f5; padding: 2px 8px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌍 IP地理位置查询API</h1>
            <p>高性能IP定位服务，支持IPv4/IPv6</p>
            <div class="endpoint">
                <p><code>GET /api/v1/?ip=8.8.8.8</code> 查询单个IP</p>
                <p><code>GET /api/v1/batch?ips=...</code> 批量查询</p>
                <p><code>GET /api/v1/myip</code> 获取客户端IP</p>
                <p><code>GET /api/v1/health</code> 健康检查</p>
            </div>
        </div>
    </body>
    </html>
    """
