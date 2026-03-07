# 服务器部署指南

本文档详细说明 IP Location API 的完整部署流程。

## 环境要求

- 操作系统：Ubuntu 20.04+ / CentOS 7+ / Debian 10+
- 内存：512MB+
- 磁盘：1GB+
- 端口：30004（可自定义）
- 域名：api.gznfpc.cn（已解析到服务器IP）

---

## 第一步：服务器环境准备

### 1.1 更新系统

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS
sudo yum update -y
```

### 1.2 安装必要工具

```bash
# Ubuntu/Debian
sudo apt install -y curl wget git

# CentOS
sudo yum install -y curl wget git
```

---

## 第二步：安装 Docker

### 2.1 安装 Docker

```bash
# 使用官方脚本安装（推荐）
curl -fsSL https://get.docker.com | sh

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
docker --version
```

### 2.2 安装 Docker Compose

```bash
# 下载 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# 添加执行权限
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker-compose --version
```

---

## 第三步：上传项目文件

### 3.1 创建项目目录

```bash
sudo mkdir -p /opt/ip-location-api
cd /opt/ip-location-api
```

### 3.2 上传文件（从本地执行）

```bash
# 方式一：使用 scp 上传整个项目
scp -r e:\项目\ip-location-api/* user@your-server-ip:/opt/ip-location-api/

# 方式二：使用 rsync（推荐，支持断点续传）
rsync -avz -e ssh e:\项目\ip-location-api/ user@your-server-ip:/opt/ip-location-api/
```

### 3.3 设置目录权限

```bash
sudo chown -R $USER:$USER /opt/ip-location-api
cd /opt/ip-location-api
```

---

## 第四步：配置并启动服务

### 4.1 检查配置文件

```bash
# 查看端口配置
cat docker-compose.yml
```

确认端口配置为：
```yaml
ports:
  - "30004:8000"
```

### 4.2 构建并启动服务

```bash
cd /opt/ip-location-api

# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看运行状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 4.3 验证服务

```bash
# 健康检查
curl http://localhost:30004/api/v1/health

# IP 查询测试
curl http://localhost:30004/api/v1/query?ip=8.8.8.8
```

---

## 第五步：配置防火墙

### 5.1 Ubuntu/Debian (UFW)

```bash
# 开放端口
sudo ufw allow 30004/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 查看状态
sudo ufw status
```

### 5.2 CentOS/RHEL (Firewalld)

```bash
# 开放端口
sudo firewall-cmd --permanent --add-port=30004/tcp
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --permanent --add-port=443/tcp

# 重载配置
sudo firewall-cmd --reload

# 查看状态
sudo firewall-cmd --list-ports
```

---

## 第六步：安装配置 Nginx

### 6.1 安装 Nginx

```bash
# Ubuntu/Debian
sudo apt install -y nginx

# CentOS
sudo yum install -y nginx

# 启动服务
sudo systemctl start nginx
sudo systemctl enable nginx
```

### 6.2 创建站点配置

```bash
sudo nano /etc/nginx/sites-available/ip-location-api.conf
```

写入以下内容：

```nginx
server {
    listen 80;
    server_name api.gznfpc.cn;

    # 访问日志
    access_log /var/log/nginx/ip-location-api.access.log;
    error_log /var/log/nginx/ip-location-api.error.log;

    # 反向代理
    location / {
        proxy_pass http://127.0.0.1:30004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时配置
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;

        # 缓冲配置
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
}
```

### 6.3 启用站点配置

```bash
# 创建软链接
sudo ln -s /etc/nginx/sites-available/ip-location-api.conf /etc/nginx/sites-enabled/

# 删除默认站点（可选）
sudo rm /etc/nginx/sites-enabled/default

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

### 6.4 验证 HTTP 访问

```bash
# 测试域名访问
curl http://api.gznfpc.cn/api/v1/health
```

---

## 第七步：配置 HTTPS 证书

### 7.1 安装 Certbot

```bash
# Ubuntu/Debian
sudo apt install -y certbot python3-certbot-nginx

# CentOS
sudo yum install -y certbot python3-certbot-nginx
```

### 7.2 申请证书

```bash
# 自动申请并配置证书
sudo certbot --nginx -d api.gznfpc.cn

# 按提示输入邮箱地址
# 选择是否接收新闻邮件（可选 N）
# 选择是否重定向 HTTP 到 HTTPS（推荐选择 2 - 重定向）
```

### 7.3 验证 HTTPS

```bash
# 测试 HTTPS 访问
curl https://api.gznfpc.cn/api/v1/health
```

### 7.4 设置自动续期

```bash
# 测试续期命令
sudo certbot renew --dry-run

# Certbot 会自动添加定时任务，无需手动配置
```

---

## 第八步：DNS 解析配置

在域名服务商控制台添加 DNS 记录：

| 类型 | 主机记录 | 记录值 | TTL |
|------|----------|--------|-----|
| A | api | 你的服务器IP | 600 |

等待 DNS 生效（通常 10 分钟内）：

```bash
# 验证 DNS 解析
nslookup api.gznfpc.cn
# 或
dig api.gznfpc.cn
```

---

## 第九步：最终验证

### 9.1 服务状态检查

```bash
# Docker 容器状态
docker-compose ps

# Nginx 状态
sudo systemctl status nginx

# 端口监听
sudo netstat -tlnp | grep -E "30004|80|443"
```

### 9.2 API 功能测试

```bash
# 健康检查
curl https://api.gznfpc.cn/api/v1/health

# 单个 IP 查询
curl https://api.gznfpc.cn/api/v1/query?ip=8.8.8.8

# 批量查询
curl https://api.gznfpc.cn/api/v1/batch?ips=8.8.8.8,114.114.114.114

# 获取客户端 IP
curl https://api.gznfpc.cn/api/v1/myip
```

### 9.3 Web 界面测试

浏览器访问：`https://api.gznfpc.cn/`

---

## 常用运维命令

### 服务管理

```bash
# 进入项目目录
cd /opt/ip-location-api

# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 查看容器状态
docker-compose ps
```

### 更新部署

```bash
cd /opt/ip-location-api

# 拉取最新代码（如果使用 Git）
git pull

# 重新构建并启动
docker-compose down
docker-compose build
docker-compose up -d
```

### 数据库更新

```bash
# 下载最新 IP 数据库
cd /opt/ip-location-api/data

# IPv4 数据库
wget https://github.com/lionsoul2014/ip2region/raw/master/data/ip2region.xdb -O ip2region_v4.xdb

# 重启服务生效
docker-compose restart
```

---

## 故障排查

### 服务无法启动

```bash
# 查看详细日志
docker-compose logs

# 检查端口占用
sudo netstat -tlnp | grep 30004

# 检查 Docker 状态
sudo systemctl status docker
```

### 域名无法访问

```bash
# 检查 DNS 解析
nslookup api.gznfpc.cn

# 检查 Nginx 状态
sudo systemctl status nginx
sudo nginx -t

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log
```

### HTTPS 证书问题

```bash
# 查看证书状态
sudo certbot certificates

# 手动续期
sudo certbot renew

# 重新申请证书
sudo certbot --nginx -d api.gznfpc.cn --force-renewal
```

---

## 安全建议

1. **定期更新系统**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **配置防火墙**，只开放必要端口

3. **定期备份数据库文件**
   ```bash
   cp /opt/ip-location-api/data/*.xdb /backup/
   ```

4. **监控服务状态**，可使用 systemd 或监控工具

5. **定期查看日志**，及时发现异常
   ```bash
   docker-compose logs --tail=100
   ```
