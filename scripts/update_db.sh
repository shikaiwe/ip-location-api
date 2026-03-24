#!/bin/bash
#
# IP数据库自动更新脚本
# 定期检查并更新 qqwry.ipdb 数据库文件
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
QQWRY_REPO="https://github.com/nmgliangwei/qqwry.ipdb"
QQWRY_RAW="https://cdn.bili33.top/gh/nmgliangwei/qqwry.ipdb@main/qqwry.ipdb"

# 日志函数
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 创建必要目录
mkdir -p "$DATA_DIR" "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

# 获取远程文件信息
get_remote_size() {
    curl -sI "$1" | grep -i content-length | awk '{print $2}' | tr -d '\r'
}

get_remote_modified() {
    curl -sI "$1" | grep -i last-modified | cut -d: -f2- | xargs
}

# 检查并更新 qqwry.ipdb
update_qqwry() {
    local db_file="$DATA_DIR/qqwry.ipdb"
    local temp_file="$DATA_DIR/qqwry.ipdb.tmp"
    
    log "检查 qqwry.ipdb 更新..."
    
    # 获取远程文件大小
    remote_size=$(get_remote_size "$QQWRY_RAW")
    
    if [ -z "$remote_size" ]; then
        log "警告：无法获取远程文件大小，跳过检查"
        return 1
    fi
    
    # 获取本地文件大小
    if [ -f "$db_file" ]; then
        local_size=$(stat -c%s "$db_file" 2>/dev/null || stat -f%z "$db_file" 2>/dev/null)
        local_modified=$(stat -c%y "$db_file" 2>/dev/null || stat -f "%Sm" "$db_file" 2>/dev/null)
    else
        local_size=0
        local_modified="不存在"
    fi
    
    log "本地文件大小: $local_size bytes"
    log "远程文件大小: $remote_size bytes"
    
    # 比较文件大小
    if [ "$local_size" = "$remote_size" ]; then
        log "qqwry.ipdb 已是最新版本，无需更新"
        return 0
    fi
    
    log "发现新版本，开始下载..."
    
    # 备份旧文件
    if [ -f "$db_file" ]; then
        backup_file="$BACKUP_DIR/qqwry.ipdb.$(date '+%Y%m%d_%H%M%S')"
        cp "$db_file" "$backup_file"
        log "已备份旧文件到: $backup_file"
    fi
    
    # 下载新文件
    if curl -L --progress-bar -o "$temp_file" "$QQWRY_RAW"; then
        # 验证下载
        downloaded_size=$(stat -c%s "$temp_file" 2>/dev/null || stat -f%z "$temp_file" 2>/dev/null)
        
        if [ "$downloaded_size" = "$remote_size" ]; then
            mv "$temp_file" "$db_file"
            log "qqwry.ipdb 更新成功！"
            log "新文件大小: $downloaded_size bytes"
            
            # 清理旧备份（保留最近5个）
            cd "$BACKUP_DIR" && ls -t qqwry.ipdb.* 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
            
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

# 主函数
main() {
    log "========== 开始数据库更新检查 =========="
    
    # 更新 qqwry.ipdb
    update_qqwry
    
    log "========== 数据库更新检查完成 =========="
    log ""
}

main "$@"
