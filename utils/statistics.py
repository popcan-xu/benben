import os
import json
import django

# 从应用之外调用stock应用的models时，需要设置'DJANGO_SETTINGS_MODULE'变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benben.settings')
django.setup()
from stock.models import market, stock, trade, position, dividend, subscription
from django.db.models import Avg, Max, Min, Count, Sum, F

from utils.utils import *


def get_position_content1(currency):
    rate_HKD, rate_USD = get_rate()
    rate_dict = {1: 1, 2: rate_HKD, 3: rate_USD}

    position_content = []
    account_array = []
    abbreviation_array = []
    stock_array = []
    account_dict = position.objects.filter(currency_id=currency).values("account").annotate(count=Count("account")).values('account_id', 'account__account_abbreviation')
    for dict in account_dict:
        account_id = dict['account_id']
        account_abbreviation = dict['account__account_abbreviation']
        account_array.append(account_id)
        abbreviation_array.append(account_abbreviation)
    account_num = len(account_array)
    stock_dict = position.objects.filter(currency_id=currency).values("stock").annotate(count=Count("stock")).values('stock_id').order_by('stock__stock_code')
    for dict in stock_dict:
        stock_id = dict['stock_id']
        stock_array.append(stock_id)
    stock_num = len(stock_array)
    for i in stock_array:
        stock_name = stock.objects.get(id=i).stock_name
        stock_code = stock.objects.get(id=i).stock_code
        stock_currency = stock.objects.get(id=i).market.currency_id
        stock_nc = stock_name + '（' + stock_code + '）'
        row = []
        quantity_sum = 0
        row.append(stock_nc)
        for j in account_array:
            try:
                quantity = position.objects.filter(currency_id=currency).get(stock=i, account=j).position_quantity
            except:
                quantity = 0
            row.append(quantity)
            quantity_sum += quantity
        row.append(quantity_sum)
        # 按持仓数量和当前价格计算每只股票的市值，并加入到当前行的隐藏列（市值）中
        price, increase, color = get_quote_snowball(stock_code)
        row.append(quantity_sum * price * rate_dict[stock_currency])
        # 增加股票对应的行
        position_content.append(row)
    # 对position_content列表按市值(quantity_sum * price * rate_dict[stock_currency])降序排序，市值所在列的序号为：第account_num + 2列（即每个账户的quantity列，加上stock_nc列和quantity_sum列）
    position_content.sort(key=lambda x: x[account_num + 2], reverse=True)

    return position_content, abbreviation_array, account_num, stock_num


def get_position_content2(currency):
    # 1. 合并汇率获取，减少函数调用次数
    rate_HKD, rate_USD = get_rate()
    rate_dict = {1: 1, 2: rate_HKD, 3: rate_USD}
    position_content = []

    # 2. 一次性获取所有账户及其缩写
    accounts = list(position.objects
                    .filter(currency_id=currency)
                    .values_list('account_id', 'account__account_abbreviation')
                    .distinct())

    # 3. 预取所有需要计算的股票信息
    stock_data = list(
        position.objects
            .filter(currency_id=currency)
            .prefetch_related('stock', 'stock__market')  # 预取关联数据
            .values('stock_id')
            .annotate(total_quantity=Sum('position_quantity'))
            .values('stock_id', 'stock__stock_name', 'stock__stock_code',
                    'stock__market__currency_id', 'total_quantity')
    )

    # 4. 创建股票字典提高查找效率
    stock_dict = {
        item['stock_id']: {
            'name': item['stock__stock_name'],
            'code': item['stock__stock_code'],
            'currency': item['stock__market__currency_id'],
            'quantity': item['total_quantity']
        }
        for item in stock_data
    }

    # 5. 批量获取所有持仓数据（账户×股票）
    all_positions = list(
        position.objects
            .filter(currency_id=currency)
            .values_list('stock_id', 'account_id', 'position_quantity')
    )

    # 6. 创建快速查找持仓的字典
    position_lookup = {(s, a): q for s, a, q in all_positions}

    # 7. 按市值预排序股票ID
    sorted_stock_ids = sorted(
        stock_dict.keys(),
        key=lambda i: stock_dict[i]['quantity'] * rate_dict[stock_dict[i]['currency']] *
                      (get_quote_snowball(stock_dict[i]['code'])[0] if stock_dict[i]['quantity'] > 0 else 0),
        reverse=True
    )

    # 8. 批量获取股票行情（避免重复调用）
    stock_quotes = {}
    for stock_id in sorted_stock_ids:
        code = stock_dict[stock_id]['code']
        if stock_dict[stock_id]['quantity'] > 0:  # 只为有持仓的股票获取行情
            stock_quotes[code] = get_quote_snowball(code)[0]  # 只保留价格

    # 9. 构建最终结果集
    account_ids = [a[0] for a in accounts]
    account_num = len(accounts)
    abbreviation_array = [a[1] for a in accounts]

    for stock_id in sorted_stock_ids:
        stock_info = stock_dict[stock_id]
        stock_nc = f"{stock_info['name']}（{stock_info['code']}）"
        quantity_total = stock_info['quantity']
        row = [stock_nc]

        # 添加账户持仓量
        for acc_id in account_ids:
            row.append(position_lookup.get((stock_id, acc_id), 0))

        # 添加该股票总量
        row.append(quantity_total)

        # 添加市值（隐藏列）
        market_value = 0
        if quantity_total > 0:
            price = stock_quotes.get(stock_info['code'], 0)
            market_value = quantity_total * price * rate_dict[stock_info['currency']]
        row.append(market_value)

        position_content.append(row)

    stock_num = len(position_content)

    # 已预先排序，无需再次排序
    return position_content, abbreviation_array, account_num, stock_num


def get_position_content(currency):
    # 获取汇率
    rate_HKD, rate_USD = get_rate()
    rate_dict = {1: 1, 2: rate_HKD, 3: rate_USD}

    # 预取所有需要的数据
    # 获取所有账户及缩写
    accounts = list(
        position.objects
            .filter(currency_id=currency)
            .values_list('account_id', 'account__account_abbreviation')
            .distinct()
    )
    account_ids = [a[0] for a in accounts]
    abbreviation_array = [a[1] for a in accounts]
    account_num = len(accounts)

    # 获取所有涉及股票的相关信息
    stock_data = list(
        position.objects
            .filter(currency_id=currency)
            .select_related('stock', 'stock__market')
            .values('stock_id')
            .annotate(total_quantity=Sum('position_quantity'))
            .values('stock_id', 'stock__stock_name', 'stock__stock_code',
                    'stock__market__currency_id', 'total_quantity')
    )

    # 准备批量获取股票价格
    stock_codes = [data['stock__stock_code'] for data in stock_data]

    # 批量获取股票价格（重点优化）
    # 返回格式：[(股票代码, 价格, 涨跌幅, 颜色), ...]
    price_array = get_stock_array_price(stock_codes)

    # 创建价格查找字典
    price_dict = {str(item[0]): item[1] for item in price_array}

    # 创建股票数据字典
    stock_dict = {}
    for data in stock_data:
        stock_id = data['stock_id']
        stock_dict[stock_id] = {
            'name': data['stock__stock_name'],
            'code': data['stock__stock_code'],
            'currency_id': data['stock__market__currency_id'],
            'total_quantity': data['total_quantity']
        }

    # 获取所有持仓数据
    all_positions = list(
        position.objects
            .filter(currency_id=currency)
            .values_list('stock_id', 'account_id', 'position_quantity')
    )

    # 创建持仓数据查找字典
    position_lookup = {(s, a): q for s, a, q in all_positions}

    # 准备最终结果集
    position_content = []

    # 按市值排序股票ID
    sorted_stock_ids = sorted(
        stock_dict.keys(),
        key=lambda sid: stock_dict[sid]['total_quantity']
                        * price_dict.get(stock_dict[sid]['code'], 0)
                        * rate_dict[stock_dict[sid]['currency_id']],
        reverse=True
    )

    # 构建表格行
    for stock_id in sorted_stock_ids:
        stock_info = stock_dict[stock_id]
        stock_nc = f"{stock_info['name']}（{stock_info['code']}）"
        row = [stock_nc]

        # 添加各账户持仓量
        total_quantity = 0
        for acc_id in account_ids:
            quantity = position_lookup.get((stock_id, acc_id), 0)
            row.append(quantity)
            total_quantity += quantity
        row.append(total_quantity)  # 总持仓量

        # 计算并添加市值（隐藏列）
        price = price_dict.get(stock_info['code'], 0)
        market_value = total_quantity * price * rate_dict[stock_info['currency_id']]
        row.append(market_value)

        position_content.append(row)

    stock_num = len(position_content)
    return position_content, abbreviation_array, account_num, stock_num


def get_value_stock_content1(currency_value, price_increase_array, HKD_rate, USD_rate):
    stock_id_array = []
    stock_table_array = []
    stock_chart_array = []
    price_array = []
    increase_array = []
    color_array = []
    quantity_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0

    if currency_value == 0:
        stock_dict = position.objects.values("stock").annotate(
            quantity=Sum("position_quantity")).values(
            'stock_id',
            'stock__stock_name',
            'stock__stock_code',
            'quantity',
            'stock__market__currency'
        )
    else:
        stock_dict = position.objects.filter(currency_id=currency_value).values("stock").annotate(
            quantity=Sum("position_quantity")).values(
            'stock_id',
            'stock__stock_name',
            'stock__stock_code',
            'quantity',
            'stock__market__currency'
        )
    for dict in stock_dict:
        stock_id = dict['stock_id']
        stock_name = dict['stock__stock_name']
        stock_code = dict['stock__stock_code']
        quantity = dict['quantity']
        currency = dict['stock__market__currency']
        price = list(filter(lambda x: stock_code in x, price_increase_array))[0][1]
        increase = list(filter(lambda x: stock_code in x, price_increase_array))[0][2]
        color = list(filter(lambda x: stock_code in x, price_increase_array))[0][3]
        if currency_value == 1 or currency_value == 0:
            if currency == 2:
                rate = HKD_rate
            elif currency == 3:
                rate = USD_rate
            else:
                rate = 1.0
        else:
            rate = 1.0
        amount = quantity * price * rate
        stock_nc = stock_name + '（' + stock_code + '）'
        increase = format(increase / 100, '.2%')
        amount_sum += amount

        stock_table_array.append(stock_nc)
        stock_chart_array.append(stock_name)
        price_array.append(price)
        increase_array.append(increase)
        color_array.append(color)
        quantity_array.append(quantity)
        amount_array.append(amount)
        stock_id_array.append(stock_id)
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    stock_table_content = list(
        zip(stock_table_array, price_array, increase_array, color_array, quantity_array, amount_array, percent_array, stock_id_array))
    stock_chart_content = list(
        zip(stock_chart_array, price_array, increase_array, color_array, quantity_array, amount_array, percent_array))
    stock_table_content.sort(key=lambda x: x[5], reverse=True)  # 对stock_content列表按第6列（金额）降序排序
    stock_chart_content.sort(key=lambda x: x[5], reverse=True)  # 对stock_content列表按第6列（金额）降序排序
    name_array, value_array = get_chart_array(stock_chart_content, 11, 0, 5) # 取前十位，剩下的并入其他
    return stock_table_content, amount_sum, json.dumps(name_array), value_array


def get_value_stock_content(currency_value, price_increase_array, HKD_rate, USD_rate):
    # 构建快速查找字典：股票代码 -> (价格, 涨幅, 颜色)
    price_dict = {item[0]: (item[1], item[2], item[3]) for item in price_increase_array}

    # 构建查询集
    if currency_value == 0:
        stock_data = position.objects.values("stock").annotate(
            quantity=Sum("position_quantity")
        ).values(
            'stock_id', 'stock__stock_name', 'stock__stock_code',
            'quantity', 'stock__market__currency'
        )
    else:
        stock_data = position.objects.filter(currency_id=currency_value).values("stock").annotate(
            quantity=Sum("position_quantity")
        ).values(
            'stock_id', 'stock__stock_name', 'stock__stock_code',
            'quantity', 'stock__market__currency'
        )

    stock_table_content = []
    stock_chart_content = []
    amount_sum = 0.0
    valid_stocks = []  # 存储有效股票数据

    for item in stock_data:
        stock_id = item['stock_id']
        stock_code = item['stock__stock_code']

        # 跳过缺失价格数据的股票
        if stock_code not in price_dict:
            continue

        price, increase, color = price_dict[stock_code]
        quantity = item['quantity']
        currency = item['stock__market__currency']

        # 确定汇率
        if currency_value in (0, 1):
            rate = {
                2: HKD_rate,  # 港元
                3: USD_rate,  # 美元
            }.get(currency, 1.0)
        else:
            rate = 1.0

        # 计算金额
        amount = quantity * price * rate
        amount_sum += amount

        # 格式化显示文本
        stock_nc = f"{item['stock__stock_name']}（{stock_code}）"
        increase_pct = f"{increase / 100:.2%}"

        valid_stocks.append((
            stock_nc, price, increase_pct, color,
            quantity, amount, stock_id
        ))

    # 计算百分比并排序
    sorted_stocks = sorted(
        valid_stocks,
        key=lambda x: x[5],  # 按金额排序
        reverse=True
    )

    # 构建最终数据
    for stock_nc, price, inc, color, qty, amt, stock_id in sorted_stocks:
        percent = f"{amt / amount_sum:.2%}" if amount_sum else "0.00%"

        # 表格数据：包含股票ID
        stock_table_content.append((
            stock_nc, price, inc, color, qty, amt, percent, stock_id
        ))

        # 图表数据：不包含股票ID
        stock_chart_content.append((
            stock_nc.split('（')[0],  # 只取股票名称
            price, inc, color, qty, amt, percent
        ))

    # 获取图表数据
    name_array, value_array = get_chart_array(stock_chart_content, 11, 0, 5)

    return stock_table_content, amount_sum, json.dumps(name_array), value_array


# def get_value_industry_content(position_currency, price_array, HKD_rate, USD_rate):
def get_value_industry_content(currency_value, price_array, HKD_rate, USD_rate):
    industry_table_array = []
    industry_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按stock、industry跨表字段分组，返回每个分组的id（通过双下划线取得多级关联表的字段值）和每个分组的quantity个数
    # industry_dict = position.objects.filter(position_currency=position_currency).values("stock__industry").annotate(
    industry_dict = position.objects.filter(currency_id=currency_value).values("stock__industry").annotate(
        count=Count("stock")).values(
        'stock__industry__id',
        'stock__industry__industry_name'
    )
    for dict in industry_dict:
        amount = 0.0
        name_array1 = []
        name_list = ''
        # 从字典dict中取出’stock__industry__industry_name‘的值
        industry_id = dict['stock__industry__id']
        industry_name = dict['stock__industry__industry_name']
        # 对position表进行跨表过滤，使用双下划线取得多级关联表的字段名
        # record_list = position.objects.filter(stock__industry=industry_id, position_currency=position_currency).values(
        record_list = position.objects.filter(stock__industry=industry_id, currency_id=currency_value).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            # 'stock__market__transaction_currency'
            'stock__market__currency'
        )
        for record in record_list:
            stock_code = record['stock__stock_code']
            stock_name = record['stock__stock_name']
            position_quantity = record['position_quantity']
            # currency = record['stock__market__transaction_currency']
            currency = record['stock__market__currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            # if position_currency == 1:
            if currency_value == 1:
                if currency == 2:
                    rate = HKD_rate
                elif currency == 3:
                    rate = USD_rate
                else:
                    rate = 1.0
            else:
                rate = 1.0
            amount += position_quantity * price * rate
            # 将同一行业对应的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        industry_table_array.append(industry_name + '（' + name_list + '）')
        industry_chart_array.append(industry_name)
        amount_array.append(amount)
        amount_sum += amount
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    industry_table_content = list(zip(industry_table_array, amount_array, percent_array))
    industry_chart_content = list(zip(industry_chart_array, amount_array, percent_array))
    industry_table_content.sort(key=lambda x: x[1], reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    industry_chart_content.sort(key=lambda x: x[1], reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(industry_chart_content, -1, 0, 1)
    return industry_table_content, amount_sum, json.dumps(name_array), value_array


def get_value_market_sum(price_array, HKD_rate, USD_rate):
    market_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按stock、industry跨表字段分组，返回每个分组的id（通过双下划线取得多级关联表的字段值）和每个分组的quantity个数
    market_dict = position.objects.values("stock__market").annotate(
        count=Count("stock")).values(
        'stock__market__id',
        'stock__market__market_name'
    )
    for dict in market_dict:
        amount = 0.0
        # 从字典dict中取出’stock__market__id‘的值
        market_id = dict['stock__market__id']
        market_name = dict['stock__market__market_name']
        # 对position表进行跨表过滤，使用双下划线取得多级关联表的字段名
        record_list = position.objects.filter(stock__market=market_id).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            # 'stock__market__transaction_currency'
            'stock__market__currency'
        )
        for record in record_list:
            stock_code = record['stock__stock_code']
            position_quantity = record['position_quantity']
            # currency = record['stock__market__transaction_currency']
            currency = record['stock__market__currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            if currency == 2:
                rate = HKD_rate
            elif currency == 3:
                rate = USD_rate
            else:
                rate = 1.0
            amount += position_quantity * price * rate
        market_chart_array.append(market_name)
        amount_array.append(amount)
        amount_sum += amount
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    market_chart_content = list(zip(market_chart_array, amount_array, percent_array))
    market_chart_content.sort(key=lambda x: x[1], reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(market_chart_content, -1, 0, 1)
    return json.dumps(name_array), value_array


# def get_value_market_content(position_currency, price_array, HKD_rate, USD_rate):
def get_value_market_content(currency_value, price_array, HKD_rate, USD_rate):
    market_table_array = []
    market_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按stock、industry跨表字段分组，返回每个分组的id（通过双下划线取得多级关联表的字段值）和每个分组的quantity个数
    # market_dict = position.objects.filter(position_currency=position_currency).values("stock__market").annotate(
    market_dict = position.objects.filter(currency_id=currency_value).values("stock__market").annotate(
        count=Count("stock")).values(
        'stock__market__id',
        'stock__market__market_name'
    )
    print(market_dict)
    for dict in market_dict:
        amount = 0.0
        name_array1 = []
        name_list = ''
        # 从字典dict中取出’stock__market__id‘的值
        market_id = dict['stock__market__id']
        market_name = dict['stock__market__market_name']
        # 对position表进行跨表过滤，使用双下划线取得多级关联表的字段名
        # record_list = position.objects.filter(stock__market=market_id, position_currency=position_currency).values(
        record_list = position.objects.filter(stock__market=market_id, currency_id=currency_value).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            # 'stock__market__transaction_currency'
            'stock__market__currency'
        )
        print(record_list)
        for record in record_list:
            stock_code = record['stock__stock_code']
            stock_name = record['stock__stock_name']
            position_quantity = record['position_quantity']
            # currency = record['stock__market__transaction_currency']
            currency = record['stock__market__currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            # if position_currency == 1:
            if currency_value == 1:
                if currency == 2:
                    rate = HKD_rate
                elif currency == 3:
                    rate = USD_rate
                else:
                    rate = 1.0
            else:
                rate = 1.0
            amount += position_quantity * price * rate
            # 将同一行业对应的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        market_table_array.append(market_name + '（' + name_list + '）')
        market_chart_array.append(market_name)
        amount_array.append(amount)
        amount_sum += amount
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    market_table_content = list(zip(market_table_array, amount_array, percent_array))
    market_chart_content = list(zip(market_chart_array, amount_array, percent_array))
    market_table_content.sort(key=lambda x: x[1], reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    market_chart_content.sort(key=lambda x: x[1], reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(market_chart_content, -1, 0, 1)
    return market_table_content, amount_sum, json.dumps(name_array), value_array


# def get_value_account_content(position_currency, price_array, HKD_rate, USD_rate):
def get_value_account_content(currency_value, price_array, HKD_rate, USD_rate):
    account_table_array = []
    account_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按account字段分组，返回每个分组的id（通过双下划线取得关联表的字段值）和每个分组的quantity个数
    # account_dict = position.objects.filter(position_currency=position_currency).values("account").annotate(
    account_dict = position.objects.filter(currency_id=currency_value).values("account").annotate(
        count=Count("account")).values(
        'account__id',
        'account__account_abbreviation'
    )
    for dict in account_dict:
        amount = 0.0
        name_array1 = []
        name_list = ''
        # 从字典tmp中取出’account__id‘的值
        account_id = dict['account__id']
        account_abbreviation = dict['account__account_abbreviation']
        # record_list = position.objects.filter(account=account_id, position_currency=position_currency).values(
        record_list = position.objects.filter(account=account_id, currency_id=currency_value).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            # 'stock__market__transaction_currency'
            'stock__market__currency'
        )
        for record in record_list:
            stock_code = record['stock__stock_code']
            stock_name = record['stock__stock_name']
            position_quantity = record['position_quantity']
            # currency = record['stock__market__transaction_currency']
            currency = record['stock__market__currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            # if position_currency == 1:
            if currency_value == 1:
                if currency == 2:
                    rate = HKD_rate
                elif currency == 3:
                    rate = USD_rate
                else:
                    rate = 1.0
            else:
                rate = 1.0
            amount += position_quantity * price * rate
            # 将同一账号下的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        account_table_array.append(account_abbreviation + '（' + name_list + '）')
        account_chart_array.append(account_abbreviation)
        amount_array.append(amount)
        amount_sum += amount
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    account_table_content = list(zip(account_table_array, amount_array, percent_array))
    account_chart_content = list(zip(account_chart_array, amount_array, percent_array))
    account_table_content.sort(key=lambda x: x[1], reverse=True)  # 对account_content列表按第二列（金额）降序排序
    account_chart_content.sort(key=lambda x: x[1], reverse=True)  # 对account_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(account_chart_content, -1, 0, 1)
    return account_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_stock_content(currency):
    stock_content = []
    amount_sum = 0.0
    stock_code_array = []
    stock_name_array = []
    amount_array = []
    percent_array = []
    stock_dict = dividend.objects.filter(currency_id=currency).values("stock").annotate(
        amount=Sum("dividend_amount")).values('stock__stock_code', 'stock__stock_name', 'amount')
    for dict in stock_dict:
        amount = 0.0
        stock_code = dict['stock__stock_code']
        stock_name = dict['stock__stock_name']
        amount = dict['amount']
        amount_sum += float(amount)
        stock_code_array.append(stock_code)
        stock_name_array.append(stock_name)
        amount_array.append(float(amount))
        # stock_content.append((stock_code,stock_name,amount))
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    stock_content = list(zip(stock_code_array, stock_name_array, amount_array, percent_array))
    stock_content.sort(key=lambda x: x[2], reverse=True)  # 对account_content列表按第3列（金额）降序排序
    name_array, value_array = get_chart_array(stock_content, 11, 1, 2) # 取前十位，剩下的并入其他
    return stock_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_year_content(currency):
    amount_sum = 0.0
    year_content = []
    year_table_array = []
    year_chart_array = []
    amount_array = []
    percent_array = []
    # 通过dividend_date__year按年份分组
    year_dict = dividend.objects.filter(currency_id=currency).values("dividend_date__year").annotate(
        amount=Sum("dividend_amount")).values('dividend_date__year', 'amount')
    for dict in year_dict:
        name_array1 = []
        name_list = ''
        year = dict['dividend_date__year']
        amount = dict['amount']
        amount_sum += float(amount)
        record_list = dividend.objects.filter(dividend_date__year=year, currency_id=currency).values(
            'stock__stock_name')
        for record in record_list:
            stock_name = record['stock__stock_name']
            # 将同一账号下的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        year_table_array.append(str(year) + '（' + name_list + '）')
        year_chart_array.append(year)
        amount_array.append(float(amount))
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    year_table_content = list(zip(year_table_array, amount_array, percent_array))
    year_chart_content = list(zip(year_chart_array, amount_array, percent_array))
    # year_content.sort(key=take_col1, reverse=True)  # 对stock_content列表按第1列（年份）降序排序
    name_array, value_array = get_chart_array(year_chart_content, -1, 0, 1)
    return year_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_industry_content(currency):
    amount_sum = 0.0
    industry_table_array = []
    industry_chart_array = []
    amount_array = []
    percent_array = []
    # 通过stock__industry按股票所属行业分组
    industry_dict = dividend.objects.filter(currency_id=currency).values("stock__industry").annotate(
        amount=Sum("dividend_amount")).values(
        'stock__industry__id',
        'stock__industry__industry_name',
        'amount'
    )
    for dict in industry_dict:
        name_array1 = []
        name_list = ''
        industry_id = dict['stock__industry__id']
        industry_name = dict['stock__industry__industry_name']
        amount = dict['amount']
        amount_sum += float(amount)
        #percent = format(float(amount) / amount_sum, '.2%')
        record_list = dividend.objects.filter(stock__industry=industry_id, currency_id=currency).values(
            'stock__stock_name')
        for record in record_list:
            stock_name = record['stock__stock_name']
            # 将同一账号下的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        industry_table_array.append(industry_name + '（' + name_list + '）')
        industry_chart_array.append(industry_name)
        amount_array.append(float(amount))
        #percent_array.append(percent)
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    industry_table_content = list(zip(industry_table_array, amount_array, percent_array))
    industry_chart_content = list(zip(industry_chart_array, amount_array, percent_array))
    industry_table_content.sort(key=lambda x: x[1], reverse=True)
    industry_chart_content.sort(key=lambda x: x[1], reverse=True)
    name_array, value_array = get_chart_array(industry_chart_content, -1, 0, 1)
    return industry_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_market_content(currency):
    amount_sum = 0.0
    market_table_array = []
    market_chart_array = []
    amount_array = []
    percent_array = []
    # 通过stock__industry按股票所属行业分组
    market_dict = dividend.objects.filter(currency_id=currency).values("stock__market").annotate(
        amount=Sum("dividend_amount")).values(
        'stock__market__id',
        'stock__market__market_name',
        'amount'
    )
    for dict in market_dict:
        name_array1 = []
        name_list = ''
        market_id = dict['stock__market__id']
        market_name = dict['stock__market__market_name']
        amount = dict['amount']
        amount_sum += float(amount)
        #percent = format(float(amount) / amount_sum, '.2%')
        record_list = dividend.objects.filter(stock__market=market_id, currency_id=currency).values(
            'stock__stock_name')
        for record in record_list:
            stock_name = record['stock__stock_name']
            # 将同一账号下的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        market_table_array.append(market_name + '（' + name_list + '）')
        market_chart_array.append(market_name)
        amount_array.append(float(amount))
        #percent_array.append(percent)
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    market_table_content = list(zip(market_table_array, amount_array, percent_array))
    market_chart_content = list(zip(market_chart_array, amount_array, percent_array))
    market_table_content.sort(key=lambda x: x[1], reverse=True)
    market_chart_content.sort(key=lambda x: x[1], reverse=True)
    name_array, value_array = get_chart_array(market_chart_content, -1, 0, 1)
    return market_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_account_content(currency):
    amount_sum = 0.0
    account_table_array = []
    account_chart_array = []
    amount_array = []
    percent_array = []
    # 通过stock__account按股票所属账号分组
    account_dict = dividend.objects.filter(currency_id=currency).values("account").annotate(
        amount=Sum("dividend_amount")).values(
        'account__id',
        'account__account_abbreviation',
        'amount'
    )
    for dict in account_dict:
        name_array1 = []
        name_list = ''
        account_id = dict['account__id']
        account_abbreviation = dict['account__account_abbreviation']
        amount = dict['amount']
        amount_sum += float(amount)
        #percent = format(float(amount) / amount_sum, '.2%')
        record_list = dividend.objects.filter(account=account_id, currency_id=currency).values(
            'stock__stock_name')
        for record in record_list:
            stock_name = record['stock__stock_name']
            # 将同一账号下的持仓股票名称写入name_array1列表
            name_array1.append(stock_name)
        # 列表去重，存入name_array2
        name_array2 = list(set(name_array1))
        name_array2.sort(key=name_array1.index)
        # 将name_array2中的每个列表值合并成字符串name_list，并用‘/’分隔
        i = 0
        while i < len(name_array2):
            name_list = name_list + name_array2[i] + '/'
            i += 1
        # 将字符串的最后一个'/'截掉
        name_list = name_list[:-1]
        account_table_array.append(account_abbreviation + '（' + name_list + '）')
        account_chart_array.append(account_abbreviation)
        amount_array.append(float(amount))
        #percent_array.append(percent)
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    account_table_content = list(zip(account_table_array, amount_array, percent_array))
    account_chart_content = list(zip(account_chart_array, amount_array, percent_array))
    account_table_content.sort(key=lambda x: x[1], reverse=True)
    account_chart_content.sort(key=lambda x: x[1], reverse=True)
    name_array, value_array = get_chart_array(account_chart_content, -1, 0, 1)
    return account_table_content, amount_sum, json.dumps(name_array), value_array


def get_subscription_year_content(subscription_type):
    year_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    year_dict = subscription.objects.filter(subscription_type=subscription_type).values(
        "subscription_date__year"
    ).annotate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity"))
    ).values(
        'subscription_date__year',
        'amount'
    )
    for dict in year_dict:
        year = dict['subscription_date__year']
        amount = dict['amount']
        amount_sum += float(amount)
        year_array.append(year)
        amount_array.append(int(amount))
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1

    year_content = list(zip(year_array, amount_array, percent_array))
    # year_content.sort(key=take_col1, reverse=True)  # 对stock_content列表按第1列（年份）降序排序

    return year_content, amount_sum, json.dumps(year_array), amount_array


def get_subscription_account_content(subscription_type):
    account_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    account_dict = subscription.objects.filter(subscription_type=subscription_type).values(
        "account"
    ).annotate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity"))
    ).values(
        'account__account_abbreviation',
        'amount'
    )
    for dict in account_dict:
        account = dict['account__account_abbreviation']
        amount = dict['amount']
        amount_sum += float(amount)
        account_array.append(account)
        amount_array.append(int(amount))
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    account_content = list(zip(account_array, amount_array, percent_array))
    # account_content.sort(key=take_col2, reverse=True)  # 对account_content列表按第2列（金额）降序排序

    return account_content, amount_sum, json.dumps(account_array), amount_array


def get_subscription_name_content(subscription_type):
    subscription_name_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    subscription_dict = subscription.objects.filter(subscription_type=subscription_type).values(
        "subscription_name"
    ).annotate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity"))
    ).values(
        'subscription_name',
        'amount'
    )
    for dict in subscription_dict:
        subscription_name = dict['subscription_name']
        amount = dict['amount']
        amount_sum += float(amount)
        subscription_name_array.append(subscription_name)
        amount_array.append(int(amount))
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    name_content = list(zip(subscription_name_array, amount_array, percent_array))
    name_content.sort(key=lambda x: x[1], reverse=True)
    name_array, value_array = get_chart_array(name_content, 51, 0, 1)
    return name_content, amount_sum, json.dumps(name_array), value_array


def get_account_stock_content(account_id, price_increase_array, HKD_rate, USD_rate):
    stock_table_array = []
    stock_chart_array = []
    price_array = []
    increase_array = []
    color_array = []
    quantity_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0

    # 对position表分组查询，按stock字段分组，返回每个分组的id（通过双下划线取得关联表的字段值）和每个分组的quantity个数
    stock_dict = position.objects.filter(account=account_id).values("stock").annotate(
        quantity=Sum("position_quantity")).values(
        'stock__stock_name',
        'stock__stock_code',
        'quantity',
        # 'stock__market__transaction_currency'
        'stock__market__currency'
    )
    for dict in stock_dict:
        # 从字典tmp中取出’stock__stock_name‘的值
        stock_name = dict['stock__stock_name']
        stock_code = dict['stock__stock_code']
        quantity = dict['quantity']
        # currency = dict['stock__market__transaction_currency']
        currency = dict['stock__market__currency']
        price = list(filter(lambda x: stock_code in x, price_increase_array))[0][1]
        # increase = list(filter(lambda x: stock_code in x, price_increase_array))[0][2]
        # color = list(filter(lambda x: stock_code in x, price_increase_array))[0][3]
        if currency == 2:
            rate = HKD_rate
        elif currency == 3:
            rate = USD_rate
        else:
            rate = 1.0
        amount = quantity * price * rate
        stock_nc = stock_name + '（' + stock_code + '）'
        # increase = format(increase / 100, '.2%')
        amount_sum += amount

        stock_table_array.append(stock_nc)
        stock_chart_array.append(stock_name)
        # price_array.append(price)
        # increase_array.append(increase)
        # color_array.append(color)
        quantity_array.append(quantity)
        amount_array.append(amount)
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    # stock_content = list(zip(stock_array, price_array, increase_array, color_array, quantity_array, amount_array, percent_array))
    # stock_content.sort(key=take_col6, reverse=True)  # 对stock_content列表按第6列（金额）降序排序
    stock_table_content = list(zip(stock_table_array, amount_array, percent_array))
    stock_chart_content = list(zip(stock_chart_array, amount_array, percent_array))
    stock_table_content.sort(key=lambda x: x[1], reverse=True)  # 对stock_content列表按第2列（金额）降序排序
    stock_chart_content.sort(key=lambda x: x[1], reverse=True)  # 对stock_content列表按第2列（金额）降序排序
    name_array, value_array = get_chart_array(stock_chart_content, -1, 0, 1)
    return stock_table_content, amount_sum, json.dumps(name_array), value_array


def get_holding_stock_profit(stock_code):
    amount_sum = 0
    quantity_sum = 0
    cost_sum = 0
    trade_array = []
    stock_id = stock.objects.all().get(stock_code=stock_code).id
    trade_list = trade.objects.all().filter(stock=stock_id).order_by('trade_date')
    price, increase, color = get_stock_price(stock_code)
    for rs in trade_list:
        if rs.trade_type == 2:
            trade_quantity = -1 * rs.trade_quantity
        else:
            trade_quantity = rs.trade_quantity
        trade_amount = rs.trade_price * trade_quantity
        cost_sum += trade_amount
        trade_array.append((
            rs.trade_date,
            rs.account.account_abbreviation,
            rs.stock.stock_name,
            rs.stock.stock_code,
            rs.trade_price,
            trade_quantity,
            trade_amount
        ))
        amount_sum += trade_amount
        quantity_sum += trade_quantity
    value = price * quantity_sum
    if quantity_sum == 0:
        price_avg = 0  # 负无穷大
    else:
        price_avg = amount_sum / quantity_sum
    profit = price * quantity_sum - float(amount_sum)
    if amount_sum > 0:
        profit_margin = profit / float(cost_sum) * 100
    else:
        profit_margin = 9999.99  # 正无穷大
    return trade_array, amount_sum, value, quantity_sum, price_avg, price, profit, profit_margin, cost_sum


def get_cleared_stock_profit(stock_code):
    amount_sum = 0
    cost_sum = 0
    trade_array = []
    stock_id = stock.objects.all().get(stock_code=stock_code).id
    trade_list = trade.objects.all().filter(stock=stock_id).order_by('trade_date')
    for rs in trade_list:
        if rs.trade_type == 2:
            trade_quantity = -1 * rs.trade_quantity
        else:
            trade_quantity = rs.trade_quantity
            cost_sum += rs.trade_price * trade_quantity
        trade_amount = rs.trade_price * trade_quantity
        trade_array.append((
            rs.trade_date,
            rs.account.account_abbreviation,
            rs.stock.stock_name,
            rs.stock.stock_code,
            rs.trade_price,
            trade_quantity,
            trade_amount
        ))
        amount_sum += trade_amount
    profit = - float(amount_sum)
    if amount_sum > 0 and cost_sum != 0:
        profit_margin = profit / float(amount_sum) * 100
    else:
        profit_margin = 9999.99  # 正无穷大
    return trade_array, profit, profit_margin, cost_sum
