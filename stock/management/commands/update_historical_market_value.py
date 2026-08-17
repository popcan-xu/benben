import datetime
import logging
import time

from django.core.management.base import BaseCommand
from django.db.models import Max
from stock.models import HistoricalPosition
from stock.views import (
    generate_historical_positions,
    get_historical_closing_price,
    fill_missing_closing_price,
    get_today_price,
    get_historical_rate,
    fill_missing_historical_rates,
    calculate_market_value,
    calculate_and_fill_historical_data,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "每日自动更新历史持仓市值数据（对应网页「更新历史持仓」按钮）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-date",
            type=str,
            default=None,
            help="起始日期，格式 YYYY-MM-DD；默认取 HistoricalPosition 最大日期前 30 天",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default=None,
            help="结束日期，格式 YYYY-MM-DD；默认今天",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只计算日期范围并打印步骤清单，不实际执行",
        )

    def handle(self, *args, **options):
        # 计算默认日期范围
        result = HistoricalPosition.objects.aggregate(max_date=Max("date"))
        max_date = result["max_date"]
        if max_date is None:
            self.stdout.write(self.style.ERROR("HistoricalPosition 表为空，无法确定起始日期"))
            return

        today = datetime.date.today()
        if options["start_date"]:
            start_date = datetime.datetime.strptime(options["start_date"], "%Y-%m-%d").date()
        else:
            start_date = max_date - datetime.timedelta(days=30)

        if options["end_date"]:
            end_date = datetime.datetime.strptime(options["end_date"], "%Y-%m-%d").date()
        else:
            end_date = today

        self.stdout.write(
            f"日期范围: {start_date} ~ {end_date} (HistoricalPosition 最大日期: {max_date})"
        )

        steps = [
            ("生成历史持仓", generate_historical_positions, (start_date, end_date)),
            ("获取历史收盘价", get_historical_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
            ("补全历史收盘价", fill_missing_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
            ("获取今日价格", get_today_price, ()),
            ("获取历史汇率", get_historical_rate, (start_date, end_date)),
            ("补全历史汇率", fill_missing_historical_rates, ()),
            ("计算市场价值", calculate_market_value, (start_date, end_date)),
            ("计算并填充历史数据", calculate_and_fill_historical_data, (start_date, end_date)),
        ]

        if options["dry_run"]:
            self.stdout.write(self.style.NOTICE("[DRY-RUN] 以下步骤将被执行:"))
            for idx, (name, _, args) in enumerate(steps, 1):
                self.stdout.write(f"  {idx}. {name} args={args}")
            return

        overall_start = time.time()
        has_error = False

        for step_idx, (step_name, func, args) in enumerate(steps, 1):
            step_start = time.time()
            self.stdout.write(f"[{step_idx}/{len(steps)}] {step_name} ... ", ending="")
            self.stdout.flush()

            try:
                func(*args)
                elapsed = time.time() - step_start
                self.stdout.write(self.style.SUCCESS(f"完成 ({elapsed:.2f}s)"))
            except Exception as e:
                elapsed = time.time() - step_start
                has_error = True
                self.stdout.write(self.style.ERROR(f"失败 ({elapsed:.2f}s): {e}"))
                logger.exception("%s 执行失败", step_name)
                # 关键步骤失败后中断，避免后续基于错误数据继续计算
                self.stdout.write(self.style.ERROR("后续步骤已中止"))
                break

        total_elapsed = time.time() - overall_start
        if has_error:
            self.stdout.write(self.style.ERROR(f"任务执行失败，总耗时 {total_elapsed:.2f}s"))
            raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS(f"所有步骤执行完成，总耗时 {total_elapsed:.2f}s"))
