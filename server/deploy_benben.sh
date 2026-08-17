#!/usr/bin/env bash
# benben 部署脚本：从 GitHub main 拉取最新代码，有变更才重启服务。
# 由 benben-deploy.timer 每日 03:30 触发，也可手动执行。
# 注意：GitHub 仅作代码源，不出网失败时跳过本次部署，不中断服务。
set -euo pipefail

APP_DIR=/var/www/benben
cd "$APP_DIR"

BEFORE=$(git rev-parse HEAD)

# 腾讯云出网 GitHub 偶发阻塞，加 timeout 60 防止卡死
if ! timeout 60 git pull --ff-only origin main; then
    echo "$(date '+%F %T') git pull 失败或超时，跳过本次部署（服务保持运行）"
    exit 0
fi

AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" != "$AFTER" ]; then
    # 有 HEAD 变更才重启，避免无谓中断
    systemctl restart benben
    echo "$(date '+%F %T') 代码已更新（$BEFORE -> $AFTER），已重启 benben"
else
    echo "$(date '+%F %T') 无更新，无需重启"
fi
