# IP Location API

为 <https://github.com/shikaiwe/pc-declaration-system> 项目开发的高性能 IP 地理位置查询服务，支持 IPv4/IPv6 双栈，基于 ip2region 离线数据库。

## 特性

- **极速查询** - 10μs 级查询延迟，离线数据库无需联网
- **高准确率** - 国内 IP 精确到城市级别，准确率 99.9%+
- **双栈支持** - 同时支持 IPv4 和 IPv6 地址查询
- **多源融合** - 纯真 + ip2region 双数据源投票融合
- **智能缓存** - TTL 缓存机制 + msgpack 二进制序列化，缓存体积减少 40%
- **热重载** - 数据库文件更新自动检测，无需重启
- **完善日志** - 结构化日志、按行分割、压缩归档
- **高性能响应** - orjson 序列化，速度提升 9.6x
- **内存优化** - 整数范围存储 + dataclass slots，减少内存占用
- **开箱即用** - Docker 一键部署，无需复杂配置

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 克隆项目
git clone https://github.com/your-repo/ip-location-api.git
cd ip-location-api

# 启动服务
docker-compose up -d

# 访问服务
# http://localhost:30004
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

# 安装依赖（包含性能优化库）
pip install -e .

# 启动服务
python -m uvicorn ip_location_api.main:app --host 0.0.0.0 --port 8000 --app-dir src
```

## API 接口

### 查询单个 IP

```bash
GET /api/v1/?ip=8.8.8.8
```

**响应示例：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "ip": "8.8.8.8",
    "country": "美国",
    "province": "加利福尼亚州",
    "city": "圣克拉拉",
    "isp": "谷歌公司DNS服务器",
    "country_code": "US",
    "is_china": false,
    "ip_version": 4,
    "accuracy": "medium",
    "accuracy_note": "",
    "is_cgnat": false,
    "cached": false
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

### 内存使用统计

```bash
GET /api/v1/memory
```

**响应示例：**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "process": {
      "rss_mb": 125.5,
      "vms_mb": 234.1,
      "percent": 2.5
    },
    "tracemalloc": {
      "available": true,
      "current_mb": 45.2,
      "peak_mb": 67.8
    },
    "cache": {
      "size": 1234,
      "max_size": 50000,
      "hit_rate": 0.85,
      "usage_percent": 2.47
    },
    "rate_limiter": {
      "tracked_ips": 156
    }
  }
}
```

### 清空缓存

```bash
GET /api/v1/clear-cache
```

## 配置项

通过环境变量或 `.env` 文件配置：

### 基础配置

| 变量        | 默认值       | 说明    |
| --------- | --------- | ----- |
| `HOST`    | `0.0.0.0` | 监听地址  |
| `PORT`    | `8000`    | 监听端口  |
| `WORKERS` | `4`       | 工作进程数 |

### 日志配置

| 变量                 | 默认值       | 说明                                   |
| ------------------ | --------- | ------------------------------------ |
| `LOG_LEVEL`        | `INFO`    | 日志级别（DEBUG/INFO/WARNING/ERROR/FATAL） |
| `LOG_DIR`          | `logs`    | 日志存储目录                               |
| `LOG_FILE_NAME`    | `app.log` | 日志文件名                                |
| `LOG_BACKUP_COUNT` | `365`     | 日志保留天数（默认一年）                         |
| `LOG_FORMAT`       | `json`    | 日志格式（json/text）                      |
| `LOG_TO_CONSOLE`   | `true`    | 是否输出到控制台                             |
| `LOG_TO_FILE`      | `true`    | 是否输出到文件                              |

## 日志系统

### 日志格式

采用简洁的 JSON 结构化格式：

```json
{"time": "2026-03-24 00:50:16", "level": "INFO", "logger": "routes", "msg": "IP查询成功", "req": "91961740", "ip": "8.8.8.8", "country": "United States"}
```

### 日志分割与归档

**分割策略**：

- 单文件最大 500KB
- 按行分割，不截断完整日志
- 文件命名：`app.log` → `app1.log` → `app2.log`...

**归档策略**：

- 每天午夜自动归档
- 整合所有分割文件压缩为 `.zip` 格式
- 目录结构：`logs/年份/月份/日期/`

### 日志目录结构

```
logs/
├── app.log                      # 当前日志（最大500KB）
├── app1.log                     # 分割文件1
├── app2.log                     # 分割文件2
├── error.log                    # 当前错误日志
├── error1.log                   # 错误分割文件1
└── 2026/                        # 年份
    └── 03/                      # 月份
        └── 24/                  # 日期
            ├── archive.log.zip      # 整合压缩的历史日志
            └── archive_error.log.zip
```

### 日志查询

```bash
# 查看当天日志
tail -f logs/app.log

# 按请求ID查询
cat logs/app.log | jq 'select(.req == "91961740")'

# 按级别过滤
cat logs/app.log | jq 'select(.level == "ERROR")'

# 解压查看历史日志
gunzip -c logs/2026/03/23/archive.log.zip | jq .
```

详细使用说明请参考 [日志使用规范](docs/LOG_GUIDE.md)。

## 数据库热重载

数据库文件更新后自动检测并重载，无需重启服务：

```bash
# 直接替换数据库文件
cp qqwry.ipdb ./data/

# 下次查询自动检测变化并重载
# 日志输出：检测到数据库文件变化，开始热重载...
```

## 部署

### Docker Compose

```yaml
version: '3.8'
services:
  ip-location-api:
    build: .
    ports:
      - "30004:8000"
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data:ro
    restart: unless-stopped
```

## 项目结构

```
ip-location-api/
├── data/                        # IP 数据库目录
│   ├── ip2region_v4.xdb         # IPv4 数据库
│   ├── ip2region_v6.xdb         # IPv6 数据库
│   └── qqwry.ipdb               # 纯真数据库
├── docs/
│   ├── LOG_GUIDE.md            # 日志使用规范
│   └── MEMORY_OPTIMIZATION.md  # 内存优化设计文档
├── src/
│   └── ip_location_api/
│       ├── main.py              # 应用入口
│       ├── routes.py            # API 路由
│       ├── fusion.py            # 多源融合引擎
│       ├── cache_manager.py     # 缓存管理模块
│       ├── json_response.py     # orjson 高性能响应
│       ├── config.py            # 配置管理
│       ├── exceptions.py        # 业务异常
│       ├── logger.py            # 日志核心模块
│       └── logging_middleware.py # 日志中间件
├── logs/                        # 日志目录（运行时生成）
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 技术栈

- **FastAPI** - 高性能异步 Web 框架
- **ip2region** - 离线 IP 地理位置数据库
- **ipip-ipdb** - 纯真 IP 数据库解析
- **cachetools** - TTL 缓存实现
- **orjson** - 高性能 JSON 序列化（9.6x 提升）
- **msgpack** - 高性能二进制序列化（40% 体积优化）
- **Uvicorn** - ASGI 服务器

## 数据来源

### ip2region

[ip2region](https://github.com/lionsoul2014/ip2region) 开源项目：

- 数据准确率 99.9%+
- 国内 IP 精确到城市
- 国外 IP 精确到国家/省份

### 纯真 IP 库

[纯真 IP 库](https://www.cz88.com/) 是国内历史最悠久的 IP 地理位置库之一，自 2005 年起为广大社区用户提供社区版 IP 地址库。

- **官网**：[https://www.cz88.com/](https://www.cz88.com/)
- **社区版**：免费使用，只要获得授权即可不断获取后续更新的版本
- **商业版**：提供数据更加准确、服务更加周全的商业版 IP 地址查询数据

纯真围绕 IP 地址，基于网络空间拓扑测绘 + 移动位置大数据方案，对 IP 地址定位、IP 网络风险、IP 使用场景、IP 网络类型、秒拨侦测、VPN 侦测、代理侦测、爬虫侦测、真人度等均有近 20 年丰富的数据沉淀。

## License

MIT License
