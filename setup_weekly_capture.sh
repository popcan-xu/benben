#!/usr/bin/env bash
# 在 benben 服务器上一次性配置「每周日 04:00 自动抓取持仓股票分红历史」。
# 用法（在 /var/www/benben 已 git pull 新代码后执行）：
#   sudo bash setup_weekly_capture.sh
#
# 脚本会：
#   1. 从现有 benben.service 自动继承 运行用户 / 工作目录 / 环境变量文件(含 AV Key)
#   2. 生成 benben-capture.service (Type=oneshot) 与 benben-capture.timer (Sun 04:00)
#   3. daemon-reload 并 enable --now 启用定时器
#   4. 立即手动跑一次验证（可选，默认开启）
set -euo pipefail

APP_DIR=/var/www/benben
UNIT_DIR=/etc/systemd/system
SRC_SVC=benben.service

# 解析 benben 实际使用的 python：优先 venv，并验证能 import django
resolve_python() {
  for c in "$APP_DIR/venv/bin/python" "$APP_DIR/.venv/bin/python" "$(command -v python3)"; do
    [ -x "$c" ] && "$c" -c 'import django' >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  echo "$(command -v python3)"
}
PY_BIN=$(resolve_python)
echo ">>> 解析到 python: $PY_BIN"

echo ">>> 读取现有 $SRC_SVC 的运行配置（自动继承，无需手填）..."
USER_VAL=$(systemctl show "$SRC_SVC" -p User --value 2>/dev/null || true)
[ -z "$USER_VAL" ] && USER_VAL=root
WORKDIR=$(systemctl show "$SRC_SVC" -p WorkingDirectory --value 2>/dev/null || true)
[ -z "$WORKDIR" ] && WORKDIR="$APP_DIR"
# EnvironmentFile 可能带 "-" 前缀（表示可选），去掉
ENV_FILE=$(systemctl show "$SRC_SVC" -p EnvironmentFile --value 2>/dev/null || true)
ENV_FILE=${ENV_FILE#-}
ENV_DIRECTIVE=""
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  ENV_DIRECTIVE="EnvironmentFile=$ENV_FILE"
else
  # 兜底：已知 benben 的 AV Key 放在 /etc/benben/env
  if [ -f /etc/benben/env ]; then
    ENV_DIRECTIVE="EnvironmentFile=/etc/benben/env"
    ENV_FILE=/etc/benben/env
  fi
fi

echo "    运行用户      : $USER_VAL"
echo "    工作目录      : $WORKDIR"
echo "    环境变量文件  : ${ENV_FILE:-（无）}"

echo ">>> 生成 $UNIT_DIR/benben-capture.service ..."
cat > "$UNIT_DIR/benben-capture.service" <<EOF
[Unit]
Description=benben 每周持仓分红历史抓取
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER_VAL
WorkingDirectory=$WORKDIR
$ENV_DIRECTIVE
ExecStart=/bin/bash -lc 'cd $APP_DIR && exec "$PY_BIN" manage.py capture_dividend'
EOF

echo ">>> 生成 $UNIT_DIR/benben-capture.timer (每周日 04:00) ..."
cat > "$UNIT_DIR/benben-capture.timer" <<EOF
[Unit]
Description=benben 每周日 04:00 持仓分红抓取定时任务

[Timer]
OnCalendar=Sun 04:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

echo ">>> systemctl daemon-reload ..."
systemctl daemon-reload

echo ">>> 启用并启动定时器 ..."
systemctl enable --now benben-capture.timer

echo ">>> 定时器状态："
systemctl status benben-capture.timer --no-pager || true
echo ">>> 下次执行时间："
systemctl list-timers benben-capture.timer --no-pager || true

echo ""
echo ">>> 立即手动跑一次验证（约几十秒，可观察美股是否走 AV 正常抓取）..."
systemd-run --quiet --unit=benben-capture-test.service \
  /bin/bash -lc "cd $WORKDIR && exec \"$PY_BIN\" manage.py capture_dividend" \
  && echo "手动验证已触发，可用 'journalctl -u benben-capture-test.service -f' 查看进度" \
  || echo "（手动验证触发失败，可忽略；定时器已配置完成）"

echo ""
echo "完成。每周日 04:00 将自动抓取持仓股票分红历史并写库。"
