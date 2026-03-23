# 日志系统使用规范

## 概述

本文档定义了 IP Location API 项目的日志使用规范，确保开发团队能够统一、高效地使用日志功能进行问题排查和系统监控。

---

## 1. 日志级别使用规范

### 1.1 级别定义

| 级别 | 用途 | 示例场景 |
|------|------|----------|
| DEBUG | 调试信息，详细的程序运行状态 | 缓存命中/未命中、详细参数值 |
| INFO | 正常业务流程日志 | 服务启动、请求处理完成、业务操作成功 |
| WARNING | 警告信息，不影响系统运行但需要关注 | 慢请求、参数校验失败、降级处理 |
| ERROR | 错误信息，影响业务流程但系统可继续运行 | 查询失败、外部服务异常 |
| FATAL | 严重错误，导致系统无法继续运行 | 数据库连接失败、关键配置缺失 |

### 1.2 级别选择原则

```python
# ✅ 正确示例
logger.debug_with_extra("缓存命中", key=ip)  # 调试细节
logger.info_with_extra("IP查询成功", ip=ip, country=result.country)  # 业务成功
logger.warning_with_extra("慢请求告警", duration_ms=1500)  # 需要关注
logger.error_with_extra("查询失败", exc_info=True, ip=ip)  # 错误但可恢复
logger.fatal_with_extra("数据库连接失败", exc_info=True)  # 致命错误

# ❌ 错误示例
logger.error("缓存未命中")  # 不应该是ERROR级别
logger.info("发生异常")  # 异常应该是ERROR或WARNING
```

---

## 2. 结构化日志规范

### 2.1 日志字段说明

每条日志自动包含以下字段：

| 字段 | 说明 | 来源 |
|------|------|------|
| time | 本地时间（年-月-日 时:分:秒） | 自动生成 |
| level | 日志级别 | 自动生成 |
| logger | 日志器名称（简短） | 自动生成 |
| msg | 日志消息 | 必填 |
| req | 请求ID（前8位） | 中间件自动注入 |
| 其他字段 | 业务数据 | 手动传入 |

### 2.2 使用额外数据

```python
# ✅ 推荐：使用结构化数据
logger.info_with_extra(
    "IP查询成功",
    ip="8.8.8.8",
    country="美国",
    city="芒廷维尤",
    duration_ms=0.5
)

# ❌ 不推荐：字符串拼接
logger.info(f"IP查询成功: ip=8.8.8.8, country=美国")
```

### 2.3 输出示例

```json
{"time": "2026-03-24 00:50:16", "level": "INFO", "logger": "routes", "msg": "IP查询成功", "req": "91961740", "ip": "8.8.8.8", "country": "United States", "city": "0"}
```

---

## 3. 敏感信息脱敏

### 3.1 自动脱敏字段

系统自动脱敏以下字段：

- password / passwd / pwd
- token / access_token / refresh_token
- api_key / apikey
- secret
- authorization
- credential
- private_key
- session_id
- credit_card

### 3.2 手动脱敏

```python
from ip_location_api.logger import SensitiveDataFilter

# 字典脱敏
data = {"username": "admin", "password": "secret123"}
safe_data = SensitiveDataFilter.filter_dict(data)
# 结果: {"username": "admin", "password": "******"}

# 字符串脱敏
text = "password=admin123"
safe_text = SensitiveDataFilter.filter_string(text)
# 结果: "password=******"
```

### 3.3 个人信息脱敏

```python
from ip_location_api.logger import SensitiveDataFilter

# 邮箱脱敏
email = SensitiveDataFilter.mask_email("user@example.com")
# 结果: "us***@example.com"

# 手机号脱敏
phone = SensitiveDataFilter.mask_phone("13812345678")
# 结果: "138****5678"

# 身份证脱敏
id_card = SensitiveDataFilter.mask_id_card("110101199001011234")
# 结果: "110101********1234"
```

---

## 4. 异常日志规范

### 4.1 记录异常堆栈

```python
try:
    result = ip_engine.query(ip)
except Exception as e:
    # ✅ 正确：自动记录完整堆栈
    logger.error_with_extra(
        "IP查询异常",
        exc_info=True,
        ip=ip,
        error_type=type(e).__name__
    )

# 或使用便捷方法
try:
    result = ip_engine.query(ip)
except Exception as e:
    logger.exception_with_extra("IP查询异常", ip=ip)
```

### 4.2 异常日志输出示例

```json
{
  "time": "2026-03-24 00:50:16",
  "level": "ERROR",
  "logger": "query",
  "msg": "IP查询异常",
  "error": "Invalid IP address format",
  "trace": "Traceback (most recent call last):\n  File ...",
  "ip": "invalid_ip"
}
```

---

## 5. 请求追踪

### 5.1 请求ID自动注入

中间件自动为每个请求生成唯一ID，并在响应头返回：

```
X-Request-ID: 91961740be804459
X-Response-Time: 20.21ms
```

### 5.2 手动设置上下文

```python
from ip_location_api.logger import set_request_id, set_user_id, LogContext

# 方式一：直接设置
set_request_id("custom-request-id")
set_user_id("user-123")

# 方式二：使用上下文管理器（推荐）
with LogContext(request_id="req-001", user_id="user-123"):
    logger.info("处理用户请求")
    # 此范围内所有日志自动包含request_id和user_id
```

---

## 6. 日志配置

### 6.1 环境变量配置

```env
# 日志级别 (DEBUG/INFO/WARNING/ERROR/FATAL)
LOG_LEVEL=INFO

# 日志存储目录
LOG_DIR=logs

# 日志文件名
LOG_FILE_NAME=app.log

# 保留的日志文件数量（天数），默认365天（一年）
LOG_BACKUP_COUNT=365

# 日志格式 (json/text)
LOG_FORMAT=json

# 是否输出到控制台
LOG_TO_CONSOLE=true

# 是否输出到文件
LOG_TO_FILE=true
```

### 6.2 日志文件轮转与归档

- **按日期轮转**：每天午夜自动切割，生成新日志文件
- **目录结构**：年份/月份/日期 三级目录
- **保留策略**：最多保留 `LOG_BACKUP_COUNT` 天的日志（默认365天，即一年）
- **自动清理**：超过保留期限的日志自动删除
- **错误日志**：ERROR及以上级别单独存储到 `error.log`

### 6.3 日志目录结构

```
logs/
├── app.log                      # 当天全量日志
├── error.log                    # 当天错误日志
└── 2026/                        # 年份
    └── 03/                      # 月份
        ├── 23/                  # 日期
        │   ├── app.log
        │   └── error.log
        └── 24/
            ├── app.log
            └── error.log
```

---

## 7. 性能监控日志

### 7.1 慢请求告警

系统自动记录超过阈值的慢请求（默认1000ms）：

```json
{"time": "2026-03-24 00:50:16", "level": "WARNING", "logger": "logging_middleware", "msg": "慢请求告警: GET /api/v1/batch 耗时 1500.23ms", "request_method": "GET", "request_path": "/api/v1/batch", "duration_ms": 1500.23, "threshold_ms": 1000}
```

### 7.2 自定义性能日志

```python
import time

start_time = time.time()
# ... 业务逻辑 ...
duration_ms = (time.time() - start_time) * 1000

logger.info_with_extra(
    "业务处理完成",
    duration_ms=round(duration_ms, 2),
    operation="batch_query"
)
```

---

## 8. 日志查询与分析

### 8.1 按请求ID查询

```bash
# 查询特定请求的所有日志
cat logs/app.log | jq 'select(.req == "91961740")'
```

### 8.2 按级别过滤

```bash
# 查询所有错误日志
cat logs/app.log | jq 'select(.level == "ERROR")'

# 查询错误日志文件
cat logs/error.log | jq .
```

### 8.3 按时间范围查询

```bash
# 查询特定时间段日志
cat logs/app.log | jq 'select(.time >= "2026-03-24 10:00:00" and .time <= "2026-03-24 11:00:00")'
```

### 8.4 查询历史日志

```bash
# 查询指定日期的日志
cat logs/2026/03/23/app.log | jq .
```

---

## 9. 最佳实践

### 9.1 日志内容规范

```python
# ✅ 好的日志：包含上下文和关键数据
logger.info_with_extra(
    "用户登录成功",
    user_id="user-123",
    login_method="password",
    client_ip="192.168.1.100"
)

# ❌ 不好的日志：信息不足
logger.info("登录成功")
```

### 9.2 避免日志滥用

```python
# ❌ 不要在循环中大量记录日志
for ip in ip_list:
    logger.debug(f"处理IP: {ip}")  # 可能产生大量日志

# ✅ 批量处理后汇总记录
logger.info_with_extra("批量处理完成", total=len(ip_list), success=success_count)
```

### 9.3 异常处理规范

```python
# ✅ 正确：记录异常并继续处理
try:
    result = process_ip(ip)
except Exception as e:
    logger.error_with_extra("处理失败，跳过", exc_info=True, ip=ip)
    continue  # 继续处理下一个

# ❌ 错误：捕获异常但不记录
try:
    result = process_ip(ip)
except:
    pass  # 吞掉异常，无法排查问题
```

---

## 10. 监控系统集成

### 10.1 ELK Stack 集成

日志格式为JSON，可直接导入Elasticsearch：

```yaml
# Logstash 配置示例
input {
  file {
    path => "/app/logs/app.log"
    codec => json
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "ip-location-api-%{+YYYY.MM.dd}"
  }
}
```

### 10.2 Prometheus 指标提取

可从日志中提取指标：

```python
# 在关键业务点记录指标
logger.info_with_extra(
    "业务指标",
    metric_type="query_count",
    metric_value=1,
    labels={"country": "中国", "ip_version": 4}
)
```

---

## 11. 常见问题

### Q1: 如何临时开启DEBUG日志？

```env
LOG_LEVEL=DEBUG
```

### Q2: 如何只输出到控制台？

```env
LOG_TO_CONSOLE=true
LOG_TO_FILE=false
```

### Q3: 日志丢失request_id？

确保请求经过 `RequestLoggingMiddleware` 中间件。

### Q4: 如何查看历史日志？

历史日志按日期存储在 `logs/年份/月份/日期/` 目录下。

---

## 12. 快速参考

```python
from ip_location_api.logger import get_logger

logger = get_logger(__name__)

# 基础日志
logger.debug("调试信息")
logger.info("普通信息")
logger.warning("警告信息")
logger.error("错误信息")

# 结构化日志
logger.info_with_extra("操作成功", key="value")

# 异常日志
logger.error_with_extra("错误", exc_info=True)
logger.exception_with_extra("异常")

# 上下文设置
from ip_location_api.logger import set_request_id, LogContext
set_request_id("req-001")

with LogContext(request_id="req-001"):
    logger.info("带上下文的日志")
```
