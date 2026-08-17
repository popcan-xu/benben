#!/bin/bash
# 部署 benben 每日历史持仓市值更新定时任务
# 对应网页：工具 -> 更新历史持仓
set -e

APP_DIR=/var/www/benben
UNIT_DIR=/etc/systemd/system
SRC_SVC=benben.service

SERVICE_FILE=$UNIT_DIR/benben-historical.service
TIMER_FILE=$UNIT_DIR/benben-historical.timer

if [ ! -f "$UNIT_DIR/$SRC_SVC" ]; then
    echo "错误：找不到 $UNIT_DIR/$SRC_SVC，无法继承运行环境" >&2
    exit 1
fi

# 从现有 benben.service 继承运行身份、工作目录、环境变量文件
USER=$(grep -E '^User=' "$UNIT_DIR/$SRC_SVC" | head -1 | cut -d= -f2 || true)
[ -z "$USER" ] && USER=root
WORKDIR=$(grep -E '^WorkingDirectory=' "$UNIT_DIR/$SRC_SVC" | head -1 | cut -d= -f2 || true)
[ -z "$WORKDIR" ] && WORKDIR=$APP_DIR
ENV_FILE=$(grep -E '^EnvironmentFile=' "$UNIT_DIR/$SRC_SVC" | head -1 | cut -d= -f2 || true)

# 找到能 import django 的 python（优先项目 venv）
find_project_python() {
    for py in "$APP_DIR/venv/bin/python" "$APP_DIR/.venv/bin/python"; do
        if [ -x "$py" ] && "$py" -c "import django" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    if command -v python3 >/dev/null 2>&1 && python3 -c "import django" 2>/dev/null; then
        echo "$(command -v python3)"
        return 0
    fi
    echo "错误：找不到可用的 Django Python 解释器" >&2
    return 1
}

PYTHON=$(find_project_python)
echo "运行用户       : $USER"
echo "工作目录       : $WORKDIR"
echo "Python 路径    : $PYTHON"
echo "环境变量文件   : ${ENV_FILE:-<无>}"

# 写入 service 单元
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=benben daily historical market value update
After=network.target

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$WORKDIR
${ENV_FILE:+EnvironmentFile=$ENV_FILE}
ExecStart=$PYTHON manage.py update_historical_market_value
EOF

# 写入 timer 单元：每天 05:00 执行，含 5 分钟随机延迟避免固定时间拥堵
cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run benben daily historical market value update at 05:00

[Timer]
OnCalendar=*-*-* 05:00:00
RandomizedDelaySec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 重载并启用
systemctl daemon-reload
systemctl enable --now benben-historical.timer

echo ""
echo "=== benben-historical.timer 状态 ==="
systemctl status benben-historical.timer --no-pager | head -8

echo ""
echo "=== 下次触发时间 ==="
systemctl list-timers benben-historical.timer --no-pager

echo ""
echo "定时任务已配置完成。可立即手动触发一次验证："
echo "  systemctl start benben-historical.service"
echo "  journalctl -u benben-historical.service -f"
