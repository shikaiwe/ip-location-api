# Docker 部署指南

## 快速部署

```bash
# 1. 进入项目目录
cd /path/to/ip-location-api

# 2. 停止并删除旧容器
docker-compose down

# 3. 重新构建镜像
docker-compose build --no-cache

# 4. 启动服务
docker-compose up -d

# 5. 查看日志
docker-compose logs -f
```

## 更新部署

### 仅更新代码

```bash
git pull
docker-compose restart
```

### 更新数据库文件

```bash
# 直接替换数据目录下的文件
cp qqwry.ipdb ./data/

# 服务会自动检测变化并热重载，无需重启
```

### 完整重新部署

```bash
# 停止并清理
docker-compose down

# 删除旧镜像（可选）
docker rmi ip-location-api_ip-location-api

# 重新构建并启动
docker-compose up -d --build
```

## 常用命令

| 命令 | 说明 |
|------|------|
| `docker-compose up -d` | 后台启动 |
| `docker-compose down` | 停止并删除容器 |
| `docker-compose restart` | 重启服务 |
| `docker-compose logs -f` | 查看实时日志 |
| `docker-compose ps` | 查看运行状态 |
| `docker-compose build` | 重新构建镜像 |

## 健康检查

```bash
# 检查服务状态
curl http://localhost:30004/api/v1/health

# 测试查询
curl http://localhost:30004/api/v1/?ip=8.8.8.8
```

## 故障排查

### 容器无法启动

```bash
# 查看详细日志
docker-compose logs

# 检查端口占用
netstat -tlnp | grep 30004
```

### 数据库加载失败

```bash
# 检查数据目录
ls -la ./data/

# 确保文件存在
# - ip2region_v4.xdb
# - ip2region_v6.xdb
# - qqwry.ipdb
```

### 日志无法写入

```bash
# 检查日志目录权限
ls -la ./logs/

# 创建目录
mkdir -p logs
```

## 生产环境建议

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  ip-location-api:
    build: .
    ports:
      - "30004:8000"
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data:ro
    restart: always
    environment:
      - WORKERS=4
      - LOG_LEVEL=INFO
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
```

```bash
# 使用生产配置启动
docker-compose -f docker-compose.prod.yml up -d
```
