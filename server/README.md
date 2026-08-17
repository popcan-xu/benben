# benben 服务器迁移 / 重建指南

本目录 `server/` 收纳了**原本散落在服务器本地、未进 git** 的全部运维资产，使换服务器做到「clone → 填密钥 → 一行脚本」。

## 收录内容

| 文件 | 作用 | 来源说明 |
|---|---|---|
| `benben.service` | 基础 Django(Gunicorn) 服务单元 | 重建自现服务器，迁移前请 `cat /etc/systemd/system/benben.service` 核对 ExecStart/workers |
| `benben.service.d/override.conf` | 注入 `/etc/benben/env` 环境变量 | 现服务器通过 drop-in 提供，基础 unit 已同时含 EnvironmentFile 以兼容解析 |
| `benben-deploy.service` / `.timer` | 每日 03:30 自动 git pull + 重启 | 重建 |
| `benben-backup.service` / `.timer` | 每日 03:00 本地数据库备份 | 重建（保留最近 14 份） |
| `nginx-benben.conf` | Nginx 反代配置（80→127.0.0.1:8000） | 重建，HTTPS 前为 80 |
| `deploy_benben.sh` | 部署逻辑（pull + 按需重启） | 重建自记忆，含 `timeout 60` 防 GitHub 出网阻塞 |
| `backup_benben.sh` | 数据库备份逻辑 | 重建 |
| `setup_https.sh` | Let's Encrypt HTTPS 申请（certbot） | ⚠️ **未从现服务器逐字核对**，迁移前请修正 |
| `bootstrap.sh` | 一键引导：安装上述全部 unit/脚本/配置并启用定时器 | 新增 |
| `env.example` | `/etc/benben/env` 模板（仅键名，无密钥） | 新增 |

> 说明：仓库根目录已有的 `setup_weekly_capture.sh` / `setup_daily_historical.sh`（每周分红 / 每日历史持仓定时器）不在本目录，由 `bootstrap.sh` 第 7 步直接调用。

## 换服务器完整步骤

1. **准备新机**（Ubuntu 24.04 为例）：
   ```bash
   apt-get update && apt-get install -y git nginx python3-venv
   ```
2. **部署代码**：
   ```bash
   git clone <your-repo> /var/www/benben
   cd /var/www/benben
   python3 -m venv venv
   venv/bin/pip install -r requirements.txt
   ```
3. **准备密钥**（真实值不进 git）：
   ```bash
   install -d -m 700 /etc/benben
   cp server/env.example /etc/benben/env
   vi /etc/benben/env          # 填入真实 ALPHAVANTAGE_API_KEY
   chmod 600 /etc/benben/env
   ```
4. **恢复数据库**（从三档备份任一：服务器 03:00 / PC 04:00 / 云快照）：
   ```bash
   cp <备份的 benben.db> /var/www/benben/benben.db
   chown root:root /var/www/benben/benben.db
   ```
5. **一键引导**：
   ```bash
   sudo bash server/bootstrap.sh
   ```
   脚本会安装全部 unit、运维脚本、Nginx 配置，启用三个基础定时器，并自动运行每周/每日定时器部署脚本。
6. **（可选）HTTPS**：
   ```bash
   sudo bash /usr/local/bin/setup_https.sh <你的域名>
   ```
   并将 `nginx-benben.conf` 的 `server_name` 改为真实域名后 `systemctl reload nginx`。
7. **验证**：
   ```bash
   systemctl status benben --no-pager
   systemctl list-timers 'benben-*' --no-pager
   curl -I http://127.0.0.1/
   ```

## 注意事项
- 现服务器若在 **2026-09-15** Lighthouse 到期前续费/换实例，直接按本指南重建即可，数据靠备份恢复，无丢失风险。
- 重建的 unit / 脚本已按已知约定填写，但 **ExecStart、workers、HTTPS 细节** 可能与现服务器存在出入，`setup_https.sh` 更是未逐字核对——首次使用前请对照现服务器相关文件 `cat` 核对。
- `/etc/benben/env` 真实密钥切勿提交；`.gitignore` 已排除 `server/env`、`server/.env`。
