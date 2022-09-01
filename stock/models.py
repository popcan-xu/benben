from django.db import models
import datetime


# 券商数据模型
class broker(models.Model):
    broker_name = models.CharField(max_length=32, verbose_name='券商名称', unique=True, db_index=True)
    broker_script = models.CharField(max_length=32, verbose_name='备注', null=True)


# 市场数据模型
class market(models.Model):
    # 定义交易货币数据字典
    CNY = 1
    HKD = 2
    USD = 3
    TRANSACTION_CURRENCY_ITEMS = (
        (CNY, '人民币'),
        (HKD, '港元'),
        (USD, '美元'),
    )
    market_name = models.CharField(max_length=32, verbose_name='市场名称', unique=True, db_index=True)
    market_abbreviation = models.CharField(max_length=32, verbose_name='市场简称')
    transaction_currency = models.PositiveIntegerField(default=CNY, choices=TRANSACTION_CURRENCY_ITEMS, verbose_name='交易货币')
    exchange_rate = models.DecimalField(default=1.0000, max_digits=8, decimal_places=4, verbose_name='汇率')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 证券账户数据模型
class account(models.Model):
    account_number = models.CharField(max_length=32, verbose_name='账号', unique=True, db_index=True)
    broker = models.ForeignKey(to="broker", on_delete=models.CASCADE, verbose_name='券商')
    account_abbreviation = models.CharField(max_length=32, verbose_name='账号简称')


# 行业数据模型
class industry(models.Model):
    industry_code = models.CharField(max_length=32, verbose_name='行业代码', unique=True, db_index=True)
    industry_name = models.CharField(max_length=32, verbose_name='行业名称')
    industry_abbreviation = models.CharField(max_length=32, verbose_name='行业简称')


# 股票数据模型
class stock(models.Model):
    stock_code = models.CharField(max_length=32, verbose_name='股票代码', unique=True, db_index=True)
    stock_name = models.CharField(max_length=32, verbose_name='股票名称', db_index=True)
    industry = models.ForeignKey(to="industry", on_delete=models.CASCADE, verbose_name='行业')
    market = models.ForeignKey(to="market", on_delete=models.CASCADE, verbose_name='市场')
    last_dividend_date = models.DateField(verbose_name='上次分红日期', null=True, blank=True)
    next_dividend_date = models.DateField(verbose_name='下次分红日期', null=True, blank=True)
    dividend_time = models.DateTimeField(default=datetime.datetime(1970, 1, 1, 0, 0, 0), verbose_name='分红获取时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 持仓数据模型
class position(models.Model):
    # 定义持仓货币数据字典
    CNY = 1
    HKD = 2
    USD = 3
    POSITION_CURRENCY_ITEMS = (
        (CNY, '人民币'),
        (HKD, '港元'),
        (USD, '美元'),
    )
    account = models.ForeignKey(to="account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    stock = models.ForeignKey(to="stock", on_delete=models.CASCADE, verbose_name='股票', db_index=True)
    position_quantity = models.IntegerField(default=0, verbose_name='持仓数量')
    position_currency = models.PositiveIntegerField(default=CNY, choices=POSITION_CURRENCY_ITEMS, verbose_name='持仓货币')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 交易数据类型
class trade(models.Model):
    # 定义交易类型数据字典
    BUY = 1
    SELL = 2
    TRADE_TYPE_ITEMS = (
        (BUY, '买入'),
        (SELL, '卖出'),
    )
    # 定义结算货币数据字典
    CNY = 1
    HKD = 2
    USD = 3
    SETTLEMENT_CURRENCY_ITEMS = (
        (CNY, '人民币'),
        (HKD, '港元'),
        (USD, '美元'),
    )
    account = models.ForeignKey(to="account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    stock = models.ForeignKey(to="stock", on_delete=models.CASCADE, verbose_name='股票', db_index=True)
    trade_date = models.DateField(verbose_name='交易日期')
    trade_type = models.PositiveIntegerField(default=BUY, choices=TRADE_TYPE_ITEMS, verbose_name='交易类型')
    trade_quantity = models.IntegerField(default=0, verbose_name='交易数量')
    trade_price = models.DecimalField(max_digits=8, decimal_places=3, verbose_name='交易价格')
    settlement_currency = models.PositiveIntegerField(default=CNY, choices=SETTLEMENT_CURRENCY_ITEMS, verbose_name='结算货币')
    filed_time = models.DateTimeField(default=datetime.datetime(1970, 1, 1, 0, 0, 0), verbose_name='归档时间')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 分红数据模型
class dividend(models.Model):
    # 定义交易货币数据字典
    CNY = 1
    HKD = 2
    USD = 3
    DIVIDEND_CURRENCY_ITEMS = (
        (CNY, '人民币'),
        (HKD, '港元'),
        (USD, '美元'),
    )
    account = models.ForeignKey(to="account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    stock = models.ForeignKey(to="stock", on_delete=models.CASCADE, verbose_name='股票', db_index=True)
    dividend_date = models.DateField(verbose_name='分红日期')
    position_quantity = models.IntegerField(default=0, verbose_name='持仓数量')
    dividend_per_share = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='每股分红')
    dividend_amount = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='分红金额（税后）')
    dividend_currency = models.PositiveIntegerField(default=CNY, choices=DIVIDEND_CURRENCY_ITEMS, verbose_name='分红货币')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 打新数据模型
class subscription(models.Model):
    # 定义打新类型数据字典
    STOCK = 1
    BOND = 2
    SUBSCRIPTION_TYPE_ITEMS = (
        (STOCK, '股票'),
        (BOND, '可转债'),
    )
    account = models.ForeignKey(to="account", on_delete=models.CASCADE, verbose_name='证券账户', db_index=True)
    subscription_name = models.CharField(default='', max_length=32, verbose_name='申购名称')
    subscription_type = models.PositiveIntegerField(default=STOCK, choices=SUBSCRIPTION_TYPE_ITEMS, verbose_name='申购类型')
    subscription_date = models.DateField(verbose_name='申购日期')
    subscription_quantity = models.IntegerField(default=0, verbose_name='申购数量')
    buying_price = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='买入价格')
    selling_price = models.DecimalField(default=0.0, max_digits=8, decimal_places=3, verbose_name='卖出价格')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')


# 分红历史数据模型
class dividend_history(models.Model):
    stock = models.ForeignKey(to="stock", on_delete=models.CASCADE, verbose_name='股票')
    reporting_period = models.CharField(max_length=64, verbose_name='报告期', null=True, blank=True)
    dividend_plan = models.CharField(max_length=256, verbose_name='分红方案')
    announcement_date = models.DateField(verbose_name='公告日', null=True, blank=True)
    registration_date = models.DateField(verbose_name='股权登记日', null=True, blank=True)
    ex_right_date = models.DateField(verbose_name='除权除息日', null=True, blank=True)
    dividend_date = models.DateField(verbose_name='派息日', null=True, blank=True)
    modified_time = models.DateTimeField(auto_now=True, verbose_name='修改时间')
