#!/usr/bin/env python3
"""T2/B2 异地备份接收端（独立服务，已从 benben Django 解耦）。

职责：接收 CloudBase dbBackup 云函数推送的备份清单（签名 URL + sha256），
原子落盘 manifest.json，供 /var/backups/stock_tracker/pull.py 定时拉取。

设计要点：
- 仅依赖 Python 标准库，不依赖 benben 的 venv / Django。
- 由 systemd 单元 stockbackup-receiver.service 托管，监听 127.0.0.1。
- 公网暴露经 Nginx 反代（location /benben/backup_webhook/），复用 benben 的 TLS。
- 鉴权 token 只从环境变量 BACKUP_WEBHOOK_TOKEN 读取（由 /etc/stockbackup.env 注入），
  绝不硬编码进仓库；缺失时服务照常启动但所有推送返回 401（日志明确告警）。
- manifest 路径与 pull.py 严格一致（默认 /var/backups/stock_tracker/manifest.json）。
"""
import json
import os
import hmac
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- 配置（环境变量，缺失时回退默认值；token 无默认值，缺失即拒绝）----
TOKEN = os.getenv('BACKUP_WEBHOOK_TOKEN', '')
MANIFEST_PATH = os.getenv(
    'STOCKBACKUP_MANIFEST',
    '/var/backups/stock_tracker/manifest.json',
)
LISTEN_HOST = os.getenv('STOCKBACKUP_HOST', '127.0.0.1')
LISTEN_PORT = int(os.getenv('STOCKBACKUP_PORT', '8731'))
MAX_BODY = 4 * 1024 * 1024  # 4MB 上限，清单通常很小

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('stockbackup-receiver')

if not TOKEN:
    log.error('BACKUP_WEBHOOK_TOKEN 未设置：服务启动但所有推送将被拒绝（401）')


class Handler(BaseHTTPRequestHandler):
    server_version = 'StockBackupReceiver/1.0'
    protocol_version = 'HTTP/1.1'

    def _send(self, code, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not TOKEN:
            self._send(401, {'ok': False, 'error': 'server_no_token'})
            return
        token = self.headers.get('X-Backup-Token', '')
        if not token or not hmac.compare_digest(token, TOKEN):
            self._send(401, {'ok': False, 'error': 'unauthorized'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(400, {'ok': False, 'error': 'bad_length'})
            return
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            self._send(400, {'ok': False, 'error': 'bad_json'})
            return
        files = payload.get('files')
        date = payload.get('date')
        if not isinstance(files, list) or not date:
            self._send(400, {'ok': False, 'error': 'bad_payload'})
            return
        try:
            d = os.path.dirname(MANIFEST_PATH)
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = MANIFEST_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, MANIFEST_PATH)
        except Exception:
            log.exception('write manifest failed')
            self._send(500, {'ok': False, 'error': 'write_failed'})
            return
        log.info('manifest written: %d files, date=%s', len(files), date)
        self._send(200, {'ok': True, 'files': len(files)})

    def do_GET(self):
        self._send(405, {'ok': False, 'error': 'method_not_allowed'})

    def log_message(self, *args):
        # 统一走 logging，避免重复写 stderr
        log.info(' '.join(str(a) for a in args))


def main():
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    log.info('listening on %s:%d', LISTEN_HOST, LISTEN_PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
