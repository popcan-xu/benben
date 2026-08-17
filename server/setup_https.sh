#!/usr/bin/env bash
# ⚠️ 重建参考脚本（未从现服务器逐字核对，迁移前请对照现服务器 /usr/local/bin/setup_https.sh 修正）
# 用途：为 benben 域名申请/续期 Let's Encrypt 证书，并将 Nginx 切换为 443 + HTTPS。
# 前置：已配置 DNS A 记录指向本机；80 端口可访问（certbot standalone 需临时占用）。
# 用法：sudo bash setup_https.sh benben.example.com
set -euo pipefail

DOMAIN="${1:-}"
[ -z "$DOMAIN" ] && { echo "用法: $0 <域名>"; exit 1; }

# 安装 certbot（如未安装）
if ! command -v certbot >/dev/null 2>&1; then
    apt-get update && apt-get install -y certbot python3-certbot-nginx
fi

# 申请证书并自动改 Nginx 配置
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@example.com" || {
    echo "certbot 失败，请手动排查（常见：80 端口被占用 / DNS 未生效）"
    exit 1
}

# 自动续期（certbot 安装后会自带 timer，此处仅确认）
systemctl enable --now certbot.timer 2>/dev/null || true

echo "HTTPS 已配置：https://$DOMAIN"
echo "请随后将 server/nginx-benben.conf 中的 server_name 改为 $DOMAIN，并 reload nginx。"
