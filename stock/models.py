from django.db import models
import datetime


# 货币数据模型
class Currency(models.Model):
    code = models.CharField(max_length=32, verbose_name='代码', unique=True, db_index=True)
    name = models.CharField(max_length=32, verbose_name='名称', db_index=True)
    unit = models.CharField(max_length=32, verbose_name='单位', null=True)
    script = models.CharField(max_length=32, verbose_name='备注', null=True)

    # 添加常量定义
    CNY_ID = 1
    HKD_ID = 2
    USD_ID = 3

    @classmethod
    def currency_ids(cls):
        return [cls.CNY_ID, cls.HKD_ID, cls.USD_ID]


# 券商数据模型
class Broker(models.Model):
    broker_name = models.CharField(max_length=32, verbose_name='券商名称', unique=True, db_index=True)
    broker_script = models.CharField(max_length=32, verbose_name='备注', null=True)


# 市场数据模型
class Market(models.Model):
    market_name = models.CharField(max_length=32, verbose_name='市场名称', unique=True, db_index=True)
    market_abbreviation = models.CharField(max_length=32, verbose_name='市场简称')
    currency = models.ForeignKey(to="stock.Currency", on_delete=models.CASCADE, verbose_name='货币', db_index=True, null=True,
                                 blank=True)


# 证券账户数据模型
class Account(models.Model):
    account_number = models.CharField(max_length=32, verbose_name='账号', unique=True, db_index=True)
    broker = models.ForeignKey(to="stock.Broker", on_delete=models.CASCADE, verbose_name='券商')
    account_abbreviation = models.CharField(max_length=32, verbose_name='账号简称')
    is_active = models.BooleanField(default=True, verbose_name='是否有效')  # 默认启用状态


# 行业数据模型
class Industry(models.Model):
    industry_code = models.CharField(max_length=32, verbose_name='行业代码', unique=True, db_index=True)
    industry_name = models.CharField(max_length=32, verbose_name='行业名称')
    industry_abbreviation = models.CharField(max_length=32, verbose_name='行业简称')


# 股票数据模型
class Stock(models.Model):
    stock_code = models.CharField(max_length=32, verbose_name='股票代码', unique=True, db_index=True)
    stock_name = models.CharField(max_length=32, verbose_name='股票名称', db_index=True)
    industry = models.ForeignKey(to="stock.Industry", on_delete=models.CASCADE, verbose_name='行业')
    market = models.ForeignKey(to="stock.Market", on_delete=models.CASCADE, verbose_name='市场')
    last_dividend_date = models.DateField(verbose_name='上次分红日期', null=True, blank=True)
    next_dividend_date = models.DateField(verbose_name='下次分红日期', null=True, blank=True)
    dividend_time = models.DateTimeField(default=datetime.datetime(1970, 1, 1, 0, 0, 0), verbose_name='分红获取时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 持仓数据模型
class Position(models.Model):
    account = models.ForeignKey(to="stock.Account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    stock = models.ForeignKey(to="stock.Stock", on_delete=models.CASCADE, verbose_name='股票', db_index=True)
    position_quantity = models.IntegerField(default=0, verbose_name='持仓数量')
    currency = models.ForeignKey(to="stock.Currency", on_delete=models.CASCADE, verbose_name='货币', db_index=True, null=True,
                                 blank=True)
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 交易数据模型
class Trade(models.Model):
    # 定义交易类型数据字典
    BUY = 1
    SELL = 2
    TRADE_TYPE_ITEMS = (
        (BUY, '买入'),
        (SELL, '卖出'),
    )
    account = models.ForeignKey(to="stock.Account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    stock = models.ForeignKey(to="stock.Stock", on_delete=models.CASCADE, verbose_name='股票', db_index=True)
    trade_date = models.DateField(verbose_name='交易日期')
    trade_type = models.PositiveIntegerField(default=BUY, choices=TRADE_TYPE_ITEMS, verbose_name='交易类型')
    trade_quantity = models.IntegerField(default=0, verbose_name='交易数量')
    trade_price = models.DecimalField(max_digits=8, decimal_places=3, verbose_name='交易价格')
    currency = models.ForeignKey(to="stock.Currency", on_delete=models.CASCADE, verbose_name='货币', db_index=True, null=True,
                                 blank=True)
    filed_time = models.DateTimeField(default=datetime.datetime(1970, 1, 1, 0, 0, 0), verbose_name='归档时间')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 分红数据模型
class Dividend(models.Model):
    account = models.ForeignKey(to="stock.Account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    stock = models.ForeignKey(to="stock.Stock", on_delete=models.CASCADE, verbose_name='股票', db_index=True)
    dividend_date = models.DateField(verbose_name='分红日期')
    position_quantity = models.IntegerField(default=0, verbose_name='持仓数量')
    dividend_per_share = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='每股分红')
    dividend_amount = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='分红金额（税后）')
    currency = models.ForeignKey(to="stock.Currency", on_delete=models.CASCADE, verbose_name='货币', db_index=True, null=True,
                                 blank=True)
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 打新数据模型
class Subscription(models.Model):
    # 定义打新类型数据字典
    STOCK = 1
    BOND = 2
    SUBSCRIPTION_TYPE_ITEMS = (
        (STOCK, '股票'),
        (BOND, '可转债'),
    )
    account = models.ForeignKey(to="stock.Account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    subscription_name = models.CharField(default='', max_length=32, verbose_name='申购名称')
    subscription_type = models.PositiveIntegerField(default=STOCK, choices=SUBSCRIPTION_TYPE_ITEMS, verbose_name='申购类型')
    subscription_date = models.DateField(verbose_name='申购日期')
    subscription_quantity = models.IntegerField(default=0, verbose_name='申购数量')
    buying_price = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='买入价格')
    selling_price = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='卖出价格')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 分红历史数据模型
class DividendHistory(models.Model):
    stock = models.ForeignKey(to="stock.Stock", on_delete=models.CASCADE, verbose_name='股票')
    reporting_period = models.CharField(max_length=64, verbose_name='报告期', null=True, blank=True)
    dividend_plan = models.CharField(max_length=256, verbose_name='分红方案')
    announcement_date = models.DateField(verbose_name='公告日', null=True, blank=True)
    registration_date = models.DateField(verbose_name='股权登记日', null=True, blank=True)
    ex_right_date = models.DateField(verbose_name='除权除息日', null=True, blank=True)
    dividend_date = models.DateField(verbose_name='派息日', null=True, blank=True)
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 基金数据模型
class Fund(models.Model):
    funds_name = models.CharField(max_length=32, verbose_name='基金名称', unique=True, db_index=True)
    funds_script = models.CharField(max_length=128, verbose_name='备注', null=True)
    currency = models.ForeignKey(to="stock.Currency", on_delete=models.CASCADE, verbose_name='货币', db_index=True, null=True,
                                 blank=True)
    baseline = models.ForeignKey(to="stock.Baseline", on_delete=models.CASCADE, verbose_name='比较基准', db_index=True, null=True,
                                 blank=True)
    funds_create_date = models.DateField(verbose_name='基金创立日期', null=True, blank=True)
    funds_value = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金价值')
    funds_principal = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金本金')
    funds_PHR = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金份数')
    funds_net_value = models.DecimalField(default=0.0, max_digits=12, decimal_places=4, verbose_name='基金净值')
    update_date = models.DateField(verbose_name='更新日期', null=True, blank=True)
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 基金详情数据模型
class FundHistory(models.Model):
    funds = models.ForeignKey(to="stock.Fund", on_delete=models.CASCADE, verbose_name='基金')
    date = models.DateField(verbose_name='记账日期', null=True, blank=True)
    funds_value = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金价值')
    funds_in_out = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='出入金')
    funds_principal = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金本金')
    funds_PHR = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金份数')
    funds_net_value = models.DecimalField(default=0.0, max_digits=12, decimal_places=4, verbose_name='基金净值')
    funds_current_profit = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金当期收益')
    funds_current_profit_rate = models.DecimalField(default=0.0, max_digits=12, decimal_places=4,
                                                    verbose_name='基金当期收益率')
    funds_profit = models.DecimalField(default=0.0, max_digits=12, decimal_places=2, verbose_name='基金收益')
    funds_profit_rate = models.DecimalField(default=0.0, max_digits=12, decimal_places=4, verbose_name='基金收益率')
    funds_annualized_profit_rate = models.DecimalField(default=0.0, max_digits=12, decimal_places=4,
                                                       verbose_name='基金年化收益率')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 比较基准数据模型
class Baseline(models.Model):
    code = models.CharField(max_length=32, verbose_name='代码', unique=True, db_index=True)
    name = models.CharField(max_length=32, verbose_name='名称', db_index=True)
    currency = models.ForeignKey(to="stock.Currency", on_delete=models.CASCADE, verbose_name='货币', db_index=True)
    script = models.CharField(max_length=32, verbose_name='备注', null=True)


# 历史持仓数据模型
class HistoricalPosition(models.Model):
    date = models.DateField(verbose_name='日期')
    stock = models.ForeignKey(to="stock.Stock", on_delete=models.CASCADE, verbose_name='股票')
    quantity = models.IntegerField(default=0, verbose_name='持仓数量')
    # 修改字段名 currency_type → currency
    currency = models.ForeignKey(
        to="stock.Currency",
        on_delete=models.CASCADE,
        verbose_name='货币',
        db_index=True,
        null=True,
        blank=True,
    )
    closing_price = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='收盘价格')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                # 更新约束中的字段名
                fields=['date', 'stock', 'currency'],
                name='unique_daily_position'
            )
        ]
        indexes = [
            # 更新索引中的字段名
            models.Index(fields=['stock', 'currency'], name='idx_stock_currency'),
        ]


# 历史汇率数据模型
class HistoricalRate(models.Model):
    date = models.DateField(verbose_name='日期')
    currency = models.ForeignKey(
        to="stock.Currency",
        on_delete=models.SET_NULL,
        verbose_name='货币外键',
        null=True,  # 关键：允许空值
        blank=True
    )
    rate = models.DecimalField(max_digits=8, decimal_places=4, verbose_name='汇率')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')

    class Meta:
        indexes = [
            models.Index(fields=['date', 'currency']),
        ]


# 历史持仓市值数据模型
class HistoricalMarketValue(models.Model):
    date = models.DateField(verbose_name='日期')
    currency = models.ForeignKey(  # 添加允许为空的临时外键字段
        to="stock.Currency",
        on_delete=models.SET_NULL,
        verbose_name='货币外键',
        null=True,  # 关键：允许空值
        blank=True
    )
    value = models.DecimalField(max_digits=16, decimal_places=4, verbose_name='市值')
    prev_value = models.DecimalField(max_digits=16, decimal_places=4, default=0, verbose_name='前一日市值')
    change_amount = models.DecimalField(max_digits=16, decimal_places=4, default=0, verbose_name='变化值')
    change_rate = models.DecimalField(max_digits=8, decimal_places=4, default=0, verbose_name='变化率(%)')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')

    class Meta:
        indexes = [
            models.Index(fields=['currency', '-date']),
            models.Index(fields=['date', 'currency'])
        ]
