#!/bin/bash
#
# IP数据库自动更新脚本
# 定期检查并更新 qqwry.ipdb 和 ip2region 数据库文件
#
# 使用方法：
#   chmod +x scripts/update_db.sh
#   ./scripts/update_db.sh
#
# 添加到 crontab（每天凌晨3点执行）：
#   0 3 * * * /path/to/ip-location-api/scripts/update_db.sh >> /var/log/ip-location-db-update.log 2>&1
#

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
BACKUP_DIR="$PROJECT_DIR/data/backup"
LOG_FILE="$PROJECT_DIR/logs/update.log"

# 数据库仓库配置
QQWRY_RAW="https://cdn.bili33.top/gh/nmgliangwei/qqwry.ipdb@main/qqwry.ipdb"
IP2REGION_V4_RAW="https://raw.githubusercontent.com/lionsoul2014/ip2region/master/data/ip2region_v4.xdb"
IP2REGION_V6_RAW="https://raw.githubusercontent.com/lionsoul2014/ip2region/master/data/ip2region_v6.xdb"

# CDN备用地址
IP2REGION_V4_CDN="https://cdn.jsdelivr.net/gh/lionsoul2014/ip2region@master/data/ip2region_v4.xdb"
IP2REGION_V6_CDN="https://cdn.jsdelivr.net/gh/lionsoul2014/ip2region@master/data/ip2region_v6.xdb"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 创建必要目录
mkdir -p "$DATA_DIR" "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

# 获取远程文件大小
get_remote_size() {
    curl -sI "$1" 2>/dev/null | grep -i content-length | awk '{print $2}' | tr -d '\r'
}

# 通用数据库更新函数
# 参数: $1=数据库名称, $2=远程URL, $3=本地文件名, $4=备用URL(可选)
update_database() {
    local db_name="$1"
    local remote_url="$2"
    local db_file="$DATA_DIR/$3"
    local temp_file="$DATA_DIR/$3.tmp"
    local backup_url="${4:-}"
    
    log "检查 $db_name 更新..."
    
    # 获取远程文件大小
    local remote_size=$(get_remote_size "$remote_url")
    
    # 如果主地址失败，尝试备用地址
    if [ -z "$remote_size" ] && [ -n "$backup_url" ]; then
        log "主地址无法访问，尝试备用地址..."
        remote_size=$(get_remote_size "$backup_url")
        remote_url="$backup_url"
    fi
    
    if [ -z "$remote_size" ]; then
        log "警告：无法获取远程文件大小，跳过 $db_name 检查"
        return 1
    fi
    
    # 获取本地文件大小
    local local_size=0
    if [ -f "$db_file" ]; then
        local_size=$(stat -c%s "$db_file" 2>/dev/null || stat -f%z "$db_file" 2>/dev/null)
    fi
    
    log "本地文件大小: $local_size bytes"
    log "远程文件大小: $remote_size bytes"
    
    # 比较文件大小
    if [ "$local_size" = "$remote_size" ]; then
        log "$db_name 已是最新版本，无需更新"
        return 0
    fi
    
    log "发现新版本，开始下载..."
    
    # 备份旧文件
    if [ -f "$db_file" ]; then
        local backup_file="$BACKUP_DIR/$3.$(date '+%Y%m%d_%H%M%S')"
        cp "$db_file" "$backup_file"
        log "已备份旧文件到: $backup_file"
    fi
    
    # 下载新文件
    if curl -L --progress-bar -o "$temp_file" "$remote_url" 2>/dev/null; then
        # 验证下载
        local downloaded_size=$(stat -c%s "$temp_file" 2>/dev/null || stat -f%z "$temp_file" 2>/dev/null)
        
        if [ "$downloaded_size" = "$remote_size" ]; then
            mv "$temp_file" "$db_file"
            log "$db_name 更新成功！"
            log "新文件大小: $downloaded_size bytes"
            
            # 清理旧备份（保留最近5个）
            cd "$BACKUP_DIR" && ls -t "$3".* 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
            
            return 0
        else
            log "错误：下载文件大小不匹配，已回滚"
            rm -f "$temp_file"
            return 1
        fi
    else
        log "错误：下载失败"
        rm -f "$temp_file"
        return 1
    fi
}

# 更新 qqwry.ipdb
update_qqwry() {
    update_database "qqwry.ipdb" "$QQWRY_RAW" "qqwry.ipdb"
}

# 更新 ip2region IPv4 数据库
update_ip2region_v4() {
    update_database "ip2region_v4.xdb" "$IP2REGION_V4_RAW" "ip2region_v4.xdb" "$IP2REGION_V4_CDN"
}

# 更新 ip2region IPv6 数据库
update_ip2region_v6() {
    update_database "ip2region_v6.xdb" "$IP2REGION_V6_RAW" "ip2region_v6.xdb" "$IP2REGION_V6_CDN"
}

# 主函数
main() {
    log "========== 开始数据库更新检查 =========="
    
    # 更新各个数据库
    update_qqwry
    update_ip2region_v4
    update_ip2region_v6
    
    log "========== 数据库更新检查完成 =========="
    log ""
}

main "$@"
