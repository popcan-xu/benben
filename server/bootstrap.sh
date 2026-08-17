#!/usr/bin/env bash
# benben 服务器一键引导：在全新 Ubuntu 服务器上重建全部 systemd / Nginx / 定时任务。
#
# 前置（需手动完成）：
#   1. 系统：Ubuntu 24.04，已装 git / nginx；Python 用项目 venv（见 README）
#   2. 已 git clone 到 /var/www/benben
#   3. 已建 venv 并 pip install -r requirements.txt
#   4. 已从备份恢复 benben.db 到 /var/www/benben/benben.db
#   5. 已准备环境变量：
#        sudo install -d -m 700 /etc/benben
#        sudo cp server/env.example /etc/benben/env && sudo vi /etc/benben/env
#        sudo chmod 600 /etc/benben/env
#
# 用法（在仓库根目录 /var/www/benben 下以 root 执行）：
#   sudo bash server/bootstrap.sh
set -euo pipefail

APP_DIR=/var/www/benben
UNIT_DIR=/etc/systemd/system
ETC_BENBEN=/etc/benben
SRV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ">>> benben 服务器引导开始"
echo "    仓库 server 目录: $SRV_DIR"
echo "    应用目录        : $APP_DIR"

# 0. 前置检查
command -v systemctl >/dev/null 2>&1 || { echo "错误：非 systemd 系统，无法继续" >&2; exit 1; }
[ -d "$APP_DIR" ] || { echo "错误：未找到 $APP_DIR，请先 git clone" >&2; exit 1; }
[ -f "$ETC_BENBEN/env" ] || { echo "错误：未找到 $ETC_BENBEN/env，请先按 README 创建并填入 ALPHAVANTAGE_API_KEY" >&2; exit 1; }

# 1. 基础服务 unit + 环境变量 drop-in
install -d "$UNIT_DIR/benben.service.d"
install -m 644 "$SRV_DIR/benben.service" "$UNIT_DIR/benben.service"
install -m 644 "$SRV_DIR/benben.service.d/override.conf" "$UNIT_DIR/benben.service.d/override.conf"
echo ">>> 已安装 benben.service + override.conf"

# 2. 部署 / 备份 定时器
install -m 644 "$SRV_DIR/benben-deploy.service" "$UNIT_DIR/benben-deploy.service"
install -m 644 "$SRV_DIR/benben-deploy.timer"    "$UNIT_DIR/benben-deploy.timer"
install -m 644 "$SRV_DIR/benben-backup.service"  "$UNIT_DIR/benben-backup.service"
install -m 644 "$SRV_DIR/benben-backup.timer"    "$UNIT_DIR/benben-backup.timer"
echo ">>> 已安装 benben-deploy.* / benben-backup.*"

# 3. 运维脚本
install -m 755 "$SRV_DIR/deploy_benben.sh" /usr/local/bin/deploy_benben.sh
install -m 755 "$SRV_DIR/backup_benben.sh" /usr/local/bin/backup_benben.sh
install -m 755 "$SRV_DIR/setup_https.sh"  /usr/local/bin/setup_https.sh
echo ">>> 已安装 /usr/local/bin/{deploy,backup,setup_https}_benben.sh"

# 4. Nginx
install -m 644 "$SRV_DIR/nginx-benben.conf" /etc/nginx/conf.d/benben.conf
# 关闭默认站点（若存在），避免与 benben 冲突
if [ -e /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
    echo ">>> 已移除默认 nginx 站点"
fi
nginx -t
echo ">>> 已安装 Nginx 配置 /etc/nginx/conf.d/benben.conf"

# 5. 启用基础服务与定时器
systemctl daemon-reload
systemctl enable --now benben.service
systemctl enable --now benben-deploy.timer
systemctl enable --now benben-backup.timer
echo ">>> 已启用 benben.service / benben-deploy.timer / benben-backup.timer"

# 6. 收集静态文件
"$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput >/dev/null 2>&1 || echo "（collectstatic 失败，可稍后手动执行）"

# 7. 运行仓库根目录已有的两个定时任务部署脚本（生成 capture / historical 定时器）
#    这两个脚本会自动从 benben.service 继承 用户/目录/环境变量
bash "$APP_DIR/setup_weekly_capture.sh"
bash "$APP_DIR/setup_daily_historical.sh"

# 8. 重载 Nginx
systemctl reload nginx || systemctl restart nginx
echo ">>> Nginx 已重载"

echo ""
echo "✅ benben 服务器引导完成。"
echo "检查：systemctl status benben --no-pager"
echo "      systemctl list-timers 'benben-*' --no-pager"
echo "HTTPS（可选）：sudo bash /usr/local/bin/setup_https.sh <你的域名>"
