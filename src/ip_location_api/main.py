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


API_DOCS_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IP Location API - 文档</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0a;
            color: #e0e0e0;
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            line-height: 1.6;
        }
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: 
                radial-gradient(ellipse at 20% 20%, rgba(0, 255, 136, 0.03) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 80%, rgba(0, 200, 255, 0.02) 0%, transparent 50%);
            pointer-events: none;
            z-index: -1;
        }
        .container { max-width: 1000px; margin: 0 auto; padding: 2rem; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 3rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .logo {
            font-family: 'Space Mono', monospace;
            font-size: 1.5rem;
            color: #00ff88;
            text-decoration: none;
        }
        .logo span { color: #e0e0e0; }
        nav a {
            color: #888;
            text-decoration: none;
            margin-left: 2rem;
            font-size: 0.9rem;
            transition: color 0.2s;
        }
        nav a:hover { color: #00ff88; }
        h1 {
            font-family: 'Space Mono', monospace;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #00ff88, #00ccff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .subtitle { color: #666; margin-bottom: 3rem; font-size: 1.1rem; }
        .section { margin-bottom: 3rem; }
        .section-title {
            font-family: 'Space Mono', monospace;
            font-size: 1.2rem;
            color: #00ff88;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .section-title::before { content: '//'; color: #444; }
        .endpoint {
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            margin-bottom: 1rem;
            overflow: hidden;
            transition: border-color 0.2s;
        }
        .endpoint:hover { border-color: rgba(0, 255, 136, 0.3); }
        .endpoint-header {
            display: flex;
            align-items: center;
            padding: 1rem 1.5rem;
            gap: 1rem;
            cursor: pointer;
        }
        .method {
            font-family: 'Space Mono', monospace;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.3rem 0.6rem;
            border-radius: 4px;
            min-width: 50px;
            text-align: center;
        }
        .method.get { background: rgba(0, 255, 136, 0.15); color: #00ff88; }
        .method.post { background: rgba(0, 136, 255, 0.15); color: #0088ff; }
        .path {
            font-family: 'Space Mono', monospace;
            color: #e0e0e0;
            flex: 1;
        }
        .endpoint-desc { color: #666; font-size: 0.9rem; }
        .endpoint-body {
            padding: 0 1.5rem 1.5rem;
            border-top: 1px solid rgba(255,255,255,0.05);
            display: none;
        }
        .endpoint.open .endpoint-body { display: block; }
        .params { margin-top: 1rem; }
        .param {
            display: flex;
            gap: 1rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }
        .param:last-child { border-bottom: none; }
        .param-name {
            font-family: 'Space Mono', monospace;
            color: #00ff88;
            min-width: 100px;
        }
        .param-info { color: #888; font-size: 0.9rem; }
        .param-type { color: #0088ff; font-size: 0.8rem; }
        .response-box {
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 1rem;
            margin-top: 1rem;
            overflow-x: auto;
        }
        .response-box pre {
            font-family: 'Space Mono', monospace;
            font-size: 0.85rem;
            color: #e0e0e0;
            white-space: pre-wrap;
        }
        .try-btn {
            background: linear-gradient(135deg, #00ff88, #00cc6a);
            color: #0a0a0a;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            font-size: 0.85rem;
            margin-top: 1rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .try-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(0, 255, 136, 0.3);
        }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 3rem;
        }
        .feature {
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
        }
        .feature-value {
            font-family: 'Space Mono', monospace;
            font-size: 1.5rem;
            color: #00ff88;
            margin-bottom: 0.5rem;
        }
        .feature-label { color: #666; font-size: 0.9rem; }
        code {
            background: rgba(0, 255, 136, 0.1);
            color: #00ff88;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-family: 'Space Mono', monospace;
            font-size: 0.85rem;
        }
        .note {
            background: rgba(0, 136, 255, 0.1);
            border-left: 3px solid #0088ff;
            padding: 1rem 1.5rem;
            border-radius: 0 8px 8px 0;
            margin: 1rem 0;
            color: #aaa;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <a href="/" class="logo">IP<span>.loc</span></a>
            <nav>
                <a href="/">首页</a>
                <a href="/docs">文档</a>
                <a href="/api/v1/health">健康检查</a>
            </nav>
        </header>
        
        <h1>API 文档</h1>
        <p class="subtitle">高性能IP地理位置查询服务，支持IPv4/IPv6双栈</p>
        
        <div class="features">
            <div class="feature">
                <div class="feature-value">10μs</div>
                <div class="feature-label">查询延迟</div>
            </div>
            <div class="feature">
                <div class="feature-value">99.9%</div>
                <div class="feature-label">定位准确率</div>
            </div>
            <div class="feature">
                <div class="feature-value">离线</div>
                <div class="feature-label">无需联网</div>
            </div>
            <div class="feature">
                <div class="feature-value">双栈</div>
                <div class="feature-label">IPv4/IPv6</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">接口列表</h2>
            
            <div class="endpoint" onclick="toggleEndpoint(this)">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="path">/api/v1/query</span>
                    <span class="endpoint-desc">查询单个IP位置</span>
                </div>
                <div class="endpoint-body">
                    <p>根据IP地址返回地理位置信息，支持IPv4和IPv6。</p>
                    <div class="params">
                        <div class="param">
                            <span class="param-name">ip</span>
                            <span class="param-info">IP地址（可选，不传则查询客户端IP）</span>
                            <span class="param-type">string</span>
                        </div>
                    </div>
                    <div class="response-box">
                        <pre>{
  "ip": "8.8.8.8",
  "country": "美国",
  "region": "加利福尼亚",
  "province": "加利福尼亚",
  "city": "芒廷维尤",
  "isp": "Google LLC",
  "latitude": 37.4056,
  "longitude": -122.0775,
  "timezone": "America/Los_Angeles",
  "ip_version": 4,
  "query_time_ms": 0.05
}</pre>
                    </div>
                    <button class="try-btn" onclick="tryApi('/api/v1/query?ip=8.8.8.8')">立即测试</button>
                </div>
            </div>

            <div class="endpoint" onclick="toggleEndpoint(this)">
                <div class="endpoint-header">
                    <span class="method post">POST</span>
                    <span class="path">/api/v1/batch</span>
                    <span class="endpoint-desc">批量查询IP位置</span>
                </div>
                <div class="endpoint-body">
                    <p>批量查询多个IP地址的地理位置信息，单次最多100个。</p>
                    <div class="params">
                        <div class="param">
                            <span class="param-name">ips</span>
                            <span class="param-info">IP地址数组（Body参数）</span>
                            <span class="param-type">array[string]</span>
                        </div>
                    </div>
                    <div class="response-box">
                        <pre>{
  "results": [
    {"ip": "8.8.8.8", "country": "美国", ...},
    {"ip": "1.1.1.1", "country": "澳大利亚", ...}
  ],
  "total": 2,
  "query_time_ms": 0.12
}</pre>
                    </div>
                    <button class="try-btn" onclick="tryBatch()">立即测试</button>
                </div>
            </div>

            <div class="endpoint" onclick="toggleEndpoint(this)">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="path">/api/v1/health</span>
                    <span class="endpoint-desc">健康检查</span>
                </div>
                <div class="endpoint-body">
                    <p>检查服务运行状态和数据库加载情况。</p>
                    <div class="response-box">
                        <pre>{
  "status": "healthy",
  "database": {
    "ipv4_loaded": true,
    "ipv6_loaded": true
  },
  "cache": {
    "size": 128,
    "max_size": 10000
  }
}</pre>
                    </div>
                    <button class="try-btn" onclick="tryApi('/api/v1/health')">立即测试</button>
                </div>
            </div>

            <div class="endpoint" onclick="toggleEndpoint(this)">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="path">/api/v1/stats</span>
                    <span class="endpoint-desc">缓存统计</span>
                </div>
                <div class="endpoint-body">
                    <p>获取缓存命中率和查询统计信息。</p>
                    <div class="response-box">
                        <pre>{
  "cache_hits": 1024,
  "cache_misses": 256,
  "hit_rate": "80.00%",
  "total_queries": 1280
}</pre>
                    </div>
                    <button class="try-btn" onclick="tryApi('/api/v1/stats')">立即测试</button>
                </div>
            </div>

            <div class="endpoint" onclick="toggleEndpoint(this)">
                <div class="endpoint-header">
                    <span class="method get">GET</span>
                    <span class="path">/api/v1/myip</span>
                    <span class="endpoint-desc">查询本机IP</span>
                </div>
                <div class="endpoint-body">
                    <p>获取请求客户端的IP地址和位置信息。</p>
                    <div class="response-box">
                        <pre>{
  "your_ip": "192.168.1.1",
  "location": {
    "country": "中国",
    "province": "北京",
    "city": "北京"
  }
}</pre>
                    </div>
                    <button class="try-btn" onclick="tryApi('/api/v1/myip')">立即测试</button>
                </div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">调用示例</h2>
            <div class="note">
                <strong>curl</strong><br>
                <code>curl "http://localhost:8000/api/v1/query?ip=8.8.8.8"</code>
            </div>
            <div class="note">
                <strong>Python</strong><br>
                <code>import requests; r = requests.get('http://localhost:8000/api/v1/query?ip=8.8.8.8')</code>
            </div>
            <div class="note">
                <strong>JavaScript</strong><br>
                <code>fetch('/api/v1/query?ip=8.8.8.8').then(r => r.json())</code>
            </div>
        </div>
    </div>

    <script>
        function toggleEndpoint(el) {
            el.classList.toggle('open');
        }
        function tryApi(url) {
            event.stopPropagation();
            window.open(url, '_blank');
        }
        function tryBatch() {
            event.stopPropagation();
            fetch('/api/v1/batch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ips: ['8.8.8.8', '1.1.1.1']})
            }).then(r => r.json()).then(console.log);
            alert('已发送批量请求，请查看控制台');
        }
    </script>
</body>
</html>
"""


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


@app.get("/docs", include_in_schema=False)
async def api_docs():
    """
    API文档页面 - 纯HTML
    """
    return HTMLResponse(content=API_DOCS_HTML)


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
        <p><a href="/docs" style="color:#00ff88">API文档</a></p>
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
        "docs": "/docs",
        "api": "/api/v1",
        "features": {
            "ipv4": True,
            "ipv6": True,
            "cache": True,
        }
    }
