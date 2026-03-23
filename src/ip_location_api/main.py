"""
FastAPI主应用
IP定位API服务入口
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import time

from ip_location_api.config import config
from ip_location_api.routes import router as api_router
from ip_location_api.query import ip_engine
from ip_location_api.logger import LoggerManager, get_logger
from ip_location_api.logging_middleware import RequestLoggingMiddleware, SlowRequestMiddleware


LoggerManager.setup()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    
    启动时初始化资源，关闭时清理资源
    """
    logger.info_with_extra(
        "IP定位API服务启动中",
        db_path=str(config.DB_PATH),
        cache_size=config.CACHE_SIZE,
        cache_ttl=config.CACHE_TTL,
        workers=config.WORKERS,
        port=config.PORT
    )
    
    yield
    
    logger.info("IP定位API服务关闭中")
    ip_engine.close()


app = FastAPI(
    title="IP Location API",
    description="高性能IP地理位置查询服务",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware, exclude_paths=["/health", "/metrics"])
app.add_middleware(SlowRequestMiddleware, threshold_ms=1000)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    添加响应时间头的中间件
    """
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time * 1000:.2f}ms"
    return response


app.include_router(api_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse, tags=["Root"])
async def root():
    """
    根路径，返回服务状态页面
    """
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head><title>IP Location API</title></head>
    <body style="background:#0a0a0a;color:#e0e0e0;font-family:monospace;padding:2rem;">
        <h1>IP Location API</h1>
        <p>服务运行中</p>
    </body>
    </html>
    """)


@app.get("/api-info", tags=["Root"])
async def api_info():
    """
    API信息接口
    """
    return {
        "name": "IP定位API",
        "version": "1.0.0",
        "api": "/api/v1",
        "features": {
            "ipv4": True,
            "ipv6": True,
            "cache": True,
        }
    }
