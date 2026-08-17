# -*- coding: utf-8 -*-
"""每周定时抓取持仓股票的分红历史数据。

逻辑与网页「持仓股票 → 抓取」按钮一致：
  - A股/港股 用线程池并行抓取（网络 I/O 瓶颈）
  - 美股 串行一只一只取（避免并发消耗 Alpha Vantage 额度）
  - 三源（AV → securitiesdb → Nasdaq）都失败时不删不写，保留数据库旧记录

定时任务由 systemd timer（benben-capture.timer）每周调用；也可手动执行：
  python manage.py capture_dividend            # 真实抓取并写库
  python manage.py capture_dividend --dry-run  # 只抓取打印，不写库（用于验证）
"""
import datetime

from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db.models import Count
from django.core.management.base import BaseCommand

from stock.models import Stock, Position, DividendHistory
from utils.utils import get_stock_dividend_history, get_dividend_date


def _fetch_one(stock_code):
    """抓取单只股票分红，返回统一结构。异常被兜底，不向上抛。"""
    try:
        stock_dividend_dict = get_stock_dividend_history(stock_code)
        next_dividend_date, last_dividend_date = get_dividend_date(stock_dividend_dict)
        return {
            'stock_code': stock_code,
            'stock_dividend_dict': stock_dividend_dict,
            'next_dividend_date': next_dividend_date,
            'last_dividend_date': last_dividend_date,
            'error': None,
        }
    except Exception as e:
        print('抓取股票（' + stock_code + '）历史分红失败：', e.__class__.__name__, e)
        return {
            'stock_code': stock_code,
            'stock_dividend_dict': None,
            'next_dividend_date': None,
            'last_dividend_date': None,
            'error': e,
        }


class Command(BaseCommand):
    help = '每周定时抓取持仓股票的分红历史数据（A股港股并行、美股串行；三源失败保留旧数据）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只抓取并打印结果，不删除/写入数据库',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # 收集持仓股票代码 + 市场（区分 A股/港股 与 美股）
        stocks = list(
            Position.objects.values('stock').annotate(c=Count('stock'))
            .values_list('stock__stock_code', 'stock__market__market_abbreviation')
        )
        if not stocks:
            self.stdout.write(self.style.WARNING('当前没有持仓股票，退出。'))
            return

        cn_hk_codes = [c for c, m in stocks if m in ('sh', 'sz', 'hk')]
        us_codes = [c for c, m in stocks if m not in ('sh', 'sz', 'hk')]

        fetch_results = []
        # A股/港股：线程池并行取数（网络 I/O 瓶颈）
        if cn_hk_codes:
            max_workers = min(5, len(cn_hk_codes))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_code = {executor.submit(_fetch_one, code): code for code in cn_hk_codes}
                for future in as_completed(future_to_code):
                    fetch_results.append(future.result())
        # 美股：串行一只一只取
        for code in us_codes:
            fetch_results.append(_fetch_one(code))

        success = skipped = failed = 0
        for result in fetch_results:
            stock_code = result['stock_code']
            stock_dividend_dict = result['stock_dividend_dict']
            if stock_dividend_dict is None:
                failed += 1
                self.stderr.write('[失败] %s: 抓取阶段异常 %s' % (stock_code, result['error']))
                continue
            meta = stock_dividend_dict
            if meta.get('unavailable'):
                skipped += 1
                self.stderr.write('[跳过] %s: 三源均失败，保留数据库旧记录（%s）'
                                  % (stock_code, meta.get('note', '')))
                continue
            records = meta.get('data') or []
            if dry_run:
                self.stdout.write('[DRY-RUN 成功] %s: 将从 %s 写入 %d 条'
                                  % (stock_code, meta.get('source_label', '—'), len(records)))
                success += 1
                continue
            try:
                stock_object = Stock.objects.get(stock_code=stock_code)
                stock_id = stock_object.id
                # 删除该股票旧的分红历史，再批量写入（幂等）
                DividendHistory.objects.filter(stock_id=stock_id).delete()
                objs = []
                for i in records:
                    for f in ('announcement_date', 'registration_date', 'ex_right_date', 'dividend_date'):
                        if i.get(f) in ('', 'None'):
                            i[f] = None
                    objs.append(DividendHistory(
                        stock_id=stock_id,
                        reporting_period=i.get('reporting_period'),
                        dividend_plan=i.get('dividend_plan'),
                        announcement_date=i.get('announcement_date'),
                        registration_date=i.get('registration_date'),
                        ex_right_date=i.get('ex_right_date'),
                        dividend_date=i.get('dividend_date'),
                    ))
                DividendHistory.objects.bulk_create(objs)
                stock_object.next_dividend_date = result['next_dividend_date']
                stock_object.last_dividend_date = result['last_dividend_date']
                stock_object.dividend_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                stock_object.save()
                success += 1
                self.stdout.write('[成功] %s: 写入 %d 条' % (stock_code, len(objs)))
            except Exception as e:
                failed += 1
                self.stderr.write('[失败] %s: 写库异常 %s' % (stock_code, e))

        self.stdout.write(self.style.SUCCESS(
            '持仓分红抓取完成：成功 %d 只，跳过(保留旧数据) %d 只，失败 %d 只'
            % (success, skipped, failed)))
