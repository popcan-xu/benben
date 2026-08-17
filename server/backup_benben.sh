#!/usr/bin/env bash
# benben 数据库备份脚本：复制 SQLite 数据库到 /var/backups/benben，保留最近 14 份。
# 由 benben-backup.timer 每日 03:00 触发。
# 注：此为三档备份中的「服务器本地档」；另有 PC 端 04:00 回传与本机云快照。
set -euo pipefail

SRC=/var/www/benben/benben.db
DEST_DIR=/var/backups/benben
KEEP=14

mkdir -p "$DEST_DIR"

if [ ! -f "$SRC" ]; then
    echo "$(date '+%F %T') 找不到 $SRC，跳过备份"
    exit 0
fi

TS=$(date +%Y%m%d_%H%M%S)
cp "$SRC" "$DEST_DIR/benben_$TS.db"
echo "$(date '+%F %T') 已备份到 $DEST_DIR/benben_$TS.db"

# 仅保留最近 KEEP 份
ls -1t "$DEST_DIR"/benben_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "$(date '+%F %T') 已清理旧备份，保留最近 $KEEP 份"
