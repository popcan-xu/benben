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
    # 有 HEAD 变更才执行依赖同步与服务重启，避免无谓中断
    VENV="$APP_DIR/venv"

    # 1) 同步 Python 依赖：新增/变更 pip 包时，保证 venv 与代码一致（防止拉到新代码却缺包 500）
    if [ -x "$VENV/bin/pip" ]; then
        "$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"
    else
        echo "$(date '+%F %T') 警告：未找到 venv（$VENV），跳过 pip install"
    fi

    # 2) 收集静态文件：STATIC_ROOT 已在 settings.py 配置，确保 Nginx 托管的前端资源同步
    if [ -x "$VENV/bin/python" ]; then
        "$VENV/bin/python" "$APP_DIR/manage.py" collectstatic --noinput
    fi

    # 3) 重启服务（依赖/静态已就位）
    systemctl restart benben
    echo "$(date '+%F %T') 代码已更新（$BEFORE -> $AFTER），已同步依赖并重启 benben"
else
    echo "$(date '+%F %T') 无更新，无需重启"
fi
