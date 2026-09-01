# benben 服务器迁移 / 重建指南

本目录 `server/` 收纳了**原本散落在服务器本地、未进 git** 的全部运维资产，使换服务器做到「clone → 填密钥 → 一行脚本」。

## 收录内容

| 文件 | 作用 | 来源说明 |
|---|---|---|
| `benben.service` | 基础 Django(Gunicorn) 服务单元 | 重建自现服务器，迁移前请 `cat /etc/systemd/system/benben.service` 核对 ExecStart/workers |
| `benben.service.d/override.conf` | 注入 `/etc/benben/env` 环境变量 | 现服务器通过 drop-in 提供，基础 unit 已同时含 EnvironmentFile 以兼容解析 |
| `benben-deploy.service` / `.timer` | 每日 03:30 自动 git pull + 同步依赖 + 收集静态 + 按需重启 | 重建 |
| `benben-backup.service` / `.timer` | 每日 03:00 本地数据库备份 | 重建（保留最近 14 份） |
| `nginx-benben.conf` | Nginx 反代配置（80→127.0.0.1:8000） | 重建，HTTPS 前为 80 |
| `deploy_benben.sh` | 部署逻辑（pull + pip 依赖同步 + collectstatic + 按需重启） | 重建自记忆，含 `timeout 60` 防 GitHub 出网阻塞 |
| `backup_benben.sh` | 数据库备份逻辑 | 重建 |
| `setup_https.sh` | Let's Encrypt HTTPS 申请（certbot） | ⚠️ **未从现服务器逐字核对**，迁移前请修正 |
| `bootstrap.sh` | 一键引导：安装上述全部 unit/脚本/配置并启用定时器 | 新增 |
| `env.example` | `/etc/benben/env` 模板（仅键名，无密钥） | 新增 |
| `stockbackup/receiver.py` | **T2 异地备份独立接收端**：接收 CloudBase 推送的备份清单并落盘 manifest.json | 新增（从 benben `stock/views.py` 的 `backup_webhook` 视图解耦而出） |
| `stockbackup/stockbackup-receiver.service` | 接收端的 systemd 单元（独立托管，不依赖 benben） | 新增 |
| `stockbackup/nginx-stockbackup.conf` | Nginx 反代片段（`/benben/backup_webhook/` → 127.0.0.1:8731） | 新增 |
| `stockbackup/env.example` | 接收端环境变量模板（`BACKUP_WEBHOOK_TOKEN`，不进 git） | 新增 |

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
- **线上部署脚本需手动同步一次**：`benben-deploy.timer` 每天跑的是 `/usr/local/bin/deploy_benben.sh`，而 git pull 只会更新仓库内的 `server/deploy_benben.sh`，**不会**自动覆盖 `/usr/local/bin/` 那份。本次新增的「pip 依赖同步 + collectstatic」逻辑要生效，需在本提交 push 且服务器 pull 之后，手动执行一次：
  ```bash
  sudo cp /var/www/benben/server/deploy_benben.sh /usr/local/bin/deploy_benben.sh
  sudo chmod 755 /usr/local/bin/deploy_benben.sh
  ```
  新服务器（用 `bootstrap.sh` 安装）则无需此步，已直接装对版本。

## 异地备份接收端（独立服务，与 benben 解耦）

T2 异地备份的「接收推送」环节**曾经写在 benben 的 `stock/views.py`（`backup_webhook` 视图）里**——这是个耦合坏味道：project B（微信小程序云开发）的备份逻辑寄生在 project A（benben）的应用代码中，且当时只在服务器上改、没进 git。现已重构为 **Lighthouse 上的独立 HTTP 接收服务**，与 benben 完全无关：

- `stockbackup/receiver.py`：纯标准库 HTTP 服务，复刻原视图逻辑（校验 `X-Backup-Token` → 解析 `{files,date}` → 原子写 `manifest.json`）。**token 只从 `/etc/stockbackup.env` 读取，绝不硬编码进仓库**。
- `stockbackup/stockbackup-receiver.service`：独立 systemd 单元，监听 `127.0.0.1:8731`。
- `stockbackup/nginx-stockbackup.conf`：Nginx 反代片段，把公网 `/benben/backup_webhook/`（沿用 CloudBase 函数既有推送 URL，零改动）反代到接收端，复用 benben 的 TLS。
- 真正的下载 / sha256 校验 / 留存仍由 `/var/backups/stock_tracker/pull.py`（root crontab `0 8 * * *`）完成，未改动。

**部署到现服务器**（手动步骤，未纳入 bootstrap.sh）：

```bash
# 1) 放脚本 + 单元
install -d -m 755 /var/backups/stock_tracker
cp server/stockbackup/receiver.py /var/backups/stock_tracker/receiver.py
chmod 755 /var/backups/stock_tracker/receiver.py
cp server/stockbackup/stockbackup-receiver.service /etc/systemd/system/
# 2) 注入 token（值须与 CloudBase dbBackup 函数发送的 X-Backup-Token 一致）
install -d -m 700 /etc/stockbackup
cp server/stockbackup/env.example /etc/stockbackup/env
vi /etc/stockbackup/env          # 填入真实 BACKUP_WEBHOOK_TOKEN
chmod 600 /etc/stockbackup/env
# 3) Nginx：把 nginx-stockbackup.conf 的 location 插入 benben_ssl.conf 的 server 块（Django location / 之前）
systemctl daemon-reload
systemctl enable --now stockbackup-receiver
nginx -t && systemctl reload nginx
# 4) 回收 benben 里残留的未提交 webhook（使服务器工作树回归 git HEAD，彻底解耦）
cd /var/www/benben && git checkout -- stock/views.py stock/urls.py
```

> 接收端监听 `127.0.0.1`，公网不可直连；若 `BACKUP_WEBHOOK_TOKEN` 缺失，服务照常启动但所有推送返回 401（日志告警），不会静默吞错。
