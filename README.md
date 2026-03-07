# IP Location API

为 https://github.com/shikaiwe/pc-declaration-system 项目开发的高性能 IP 地理位置查询服务，支持 IPv4/IPv6 双栈，基于 ip2region 离线数据库。

## 特性

- **极速查询** - 10μs 级查询延迟，离线数据库无需联网
- **高准确率** - 国内 IP 精确到城市级别，准确率 99.9%+
- **双栈支持** - 同时支持 IPv4 和 IPv6 地址查询
- **智能缓存** - TTL 缓存机制，提升重复查询性能
- **开箱即用** - Docker 一键部署，无需复杂配置
- **轻量纯净** - 无外部依赖，数据完全离线

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 克隆项目
git clone https://github.com/your-repo/ip-location-api.git
cd ip-location-api

# 启动服务
docker-compose up -d

# 访问服务
# http://localhost:8000
```

### 方式二：直接运行

```bash
# 克隆项目
git clone https://github.com/your-repo/ip-location-api.git
cd ip-location-api

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m uvicorn ip_location_api.main:app --host 0.0.0.0 --port 8000 --app-dir src
```

## API 接口

### 查询单个 IP

```bash
GET /api/v1/query?ip=8.8.8.8
```

**响应示例：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "ip": "8.8.8.8",
    "country": "美国",
    "province": "加利福尼亚",
    "city": "芒廷维尤",
    "isp": "Google LLC",
    "country_code": "US",
    "is_china": false,
    "ip_version": 4
  }
}
```

### 批量查询

```bash
GET /api/v1/batch?ips=8.8.8.8,114.114.114.114
```

### 获取客户端 IP

```bash
GET /api/v1/myip
```

**响应示例：**

```json
{
  "your_ip": "192.168.1.1",
  "location": {
    "country": "中国",
    "province": "北京",
    "city": "北京",
    "isp": "中国电信"
  }
}
```

### 健康检查

```bash
GET /api/v1/health
```

### 缓存统计

```bash
GET /api/v1/stats
```

## 配置项

通过环境变量或 `.env` 文件配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8000` | 监听端口 |
| `WORKERS` | `4` | 工作进程数 |
| `CACHE_SIZE` | `10000` | 缓存容量 |
| `CACHE_TTL` | `3600` | 缓存过期时间（秒） |

## 部署

### Docker Compose

```yaml
version: '1.0'
services:
  ip-location-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - CACHE_SIZE=10000
      - CACHE_TTL=3600
    restart: unless-stopped
```

### Systemd 服务

```bash
# 复制服务文件
sudo cp ip-location-api.service /etc/systemd/system/

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable ip-location-api
sudo systemctl start ip-location-api
```

## 项目结构

```
ip-location-api/
├── data/                    # IP 数据库目录
│   ├── ip2region_v4.xdb     # IPv4 数据库
│   └── ip2region_v6.xdb     # IPv6 数据库
├── src/
│   └── ip_location_api/
│       ├── main.py          # 应用入口
│       ├── routes.py        # API 路由
│       ├── query.py         # 查询引擎
│       ├── cache.py         # 缓存模块
│       ├── config.py        # 配置管理
│       └── static/
│           └── index.html   # Web 界面
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 技术栈

- **FastAPI** - 高性能异步 Web 框架
- **ip2region** - 离线 IP 地理位置数据库
- **cachetools** - TTL 缓存实现
- **Uvicorn** - ASGI 服务器

## 数据来源

IP 数据库来自 [ip2region](https://github.com/lionsoul2014/ip2region) 开源项目：

- 数据准确率 99.9%+
- 国内 IP 精确到城市
- 国外 IP 精确到国家/省份
- 定期更新数据库以保持准确性

## License

MIT License
