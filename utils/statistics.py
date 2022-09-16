import os
import json
import django

# 从应用之外调用stock应用的models时，需要设置'DJANGO_SETTINGS_MODULE'变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benben.settings')
django.setup()
from stock.models import market, stock, trade, position, dividend, subscription
from django.db.models import Avg, Max, Min, Count, Sum, F

from utils.utils import *


def get_position_content(currency):
    position_content = []
    account_array = []
    abbreviation_array = []
    stock_array = []
    account_dict = position.objects.filter(position_currency=currency).values("account").annotate(
        count=Count("account")).values('account_id', 'account__account_abbreviation')
    for dict in account_dict:
        account_id = dict['account_id']
        account_abbreviation = dict['account__account_abbreviation']
        account_array.append(account_id)
        abbreviation_array.append(account_abbreviation)
    account_num = len(account_array)
    stock_dict = position.objects.filter(position_currency=currency).values("stock").annotate(
        count=Count("stock")).values('stock_id').order_by('stock__stock_code')
    for dict in stock_dict:
        stock_id = dict['stock_id']
        stock_array.append(stock_id)
    stock_num = len(stock_array)
    for i in stock_array:
        stock_name = stock.objects.get(id=i).stock_name
        stock_code = stock.objects.get(id=i).stock_code
        stock_nc = stock_name + '（' + stock_code + '）'
        row = []
        quantity_sum = 0
        row.append(stock_nc)
        # row.append(stock_code)
        # row.append(stock_name)
        for j in account_array:
            try:
                quantity = position.objects.get(stock=i, account=j).position_quantity
            except:
                quantity = 0
            row.append(quantity)
            quantity_sum += quantity
        row.append(quantity_sum)
        position_content.append(row)
    # position_content.sort(key=take_col1)  # 对stock_content列表按第1列（股票名称）降序排序
    return position_content, abbreviation_array, account_num, stock_num


def get_value_stock_content(position_currency, price_increase_array, HKD_rate, USD_rate):
    stock_table_array = []
    stock_chart_array = []
    price_array = []
    increase_array = []
    color_array = []
    quantity_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0

    if position_currency == 0:
        # 对position表分组查询，按stock字段分组，返回每个分组的id（通过双下划线取得关联表的字段值）和每个分组的quantity个数
        stock_dict = position.objects.values("stock").annotate(
            quantity=Sum("position_quantity")).values(
            'stock__stock_name',
            'stock__stock_code',
            'quantity',
            'stock__market__transaction_currency'
        )
    else:
        # 对position表分组查询，按stock字段分组，返回每个分组的id（通过双下划线取得关联表的字段值）和每个分组的quantity个数
        stock_dict = position.objects.filter(position_currency=position_currency).values("stock").annotate(
            quantity=Sum("position_quantity")).values(
            'stock__stock_name',
            'stock__stock_code',
            'quantity',
            'stock__market__transaction_currency'
        )
    for dict in stock_dict:
        # 从字典tmp中取出’stock__stock_name‘的值
        stock_name = dict['stock__stock_name']
        stock_code = dict['stock__stock_code']
        quantity = dict['quantity']
        currency = dict['stock__market__transaction_currency']
        price = list(filter(lambda x: stock_code in x, price_increase_array))[0][1]
        increase = list(filter(lambda x: stock_code in x, price_increase_array))[0][2]
        color = list(filter(lambda x: stock_code in x, price_increase_array))[0][3]
        if position_currency == 1 or position_currency == 0:
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
    i = 0
    while i < len(amount_array):
        percent = format(float(amount_array[i]) / amount_sum, '.2%')
        percent_array.append(percent)
        i += 1
    stock_table_content = list(
        zip(stock_table_array, price_array, increase_array, color_array, quantity_array, amount_array, percent_array))
    stock_chart_content = list(
        zip(stock_chart_array, price_array, increase_array, color_array, quantity_array, amount_array, percent_array))
    stock_table_content.sort(key=take_col6, reverse=True)  # 对stock_content列表按第6列（金额）降序排序
    stock_chart_content.sort(key=take_col6, reverse=True)  # 对stock_content列表按第6列（金额）降序排序
    name_array, value_array = get_chart_array(stock_chart_content, 11, 0, 5) # 取前十位，剩下的并入其他
    return stock_table_content, amount_sum, json.dumps(name_array), value_array


def get_value_industry_content(position_currency, price_array, HKD_rate, USD_rate):
    industry_table_array = []
    industry_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按stock、industry跨表字段分组，返回每个分组的id（通过双下划线取得多级关联表的字段值）和每个分组的quantity个数
    industry_dict = position.objects.filter(position_currency=position_currency).values("stock__industry").annotate(
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
        record_list = position.objects.filter(stock__industry=industry_id, position_currency=position_currency).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            'stock__market__transaction_currency'
        )
        for record in record_list:
            stock_code = record['stock__stock_code']
            stock_name = record['stock__stock_name']
            position_quantity = record['position_quantity']
            currency = record['stock__market__transaction_currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            if position_currency == 1:
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
    industry_table_content.sort(key=take_col2, reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    industry_chart_content.sort(key=take_col2, reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(industry_chart_content, -1, 0, 1)
    return industry_table_content, amount_sum, json.dumps(name_array), value_array


def get_value_market_content(position_currency, price_array, HKD_rate, USD_rate):
    market_table_array = []
    market_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按stock、industry跨表字段分组，返回每个分组的id（通过双下划线取得多级关联表的字段值）和每个分组的quantity个数
    market_dict = position.objects.filter(position_currency=position_currency).values("stock__market").annotate(
        count=Count("stock")).values(
        'stock__market__id',
        'stock__market__market_name'
    )
    for dict in market_dict:
        amount = 0.0
        name_array1 = []
        name_list = ''
        # 从字典dict中取出’stock__market__id‘的值
        market_id = dict['stock__market__id']
        market_name = dict['stock__market__market_name']
        # 对position表进行跨表过滤，使用双下划线取得多级关联表的字段名
        record_list = position.objects.filter(stock__market=market_id, position_currency=position_currency).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            'stock__market__transaction_currency'
        )
        for record in record_list:
            stock_code = record['stock__stock_code']
            stock_name = record['stock__stock_name']
            position_quantity = record['position_quantity']
            currency = record['stock__market__transaction_currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            if position_currency == 1:
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
    market_table_content.sort(key=take_col2, reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    market_chart_content.sort(key=take_col2, reverse=True)  # 对industry_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(market_chart_content, -1, 0, 1)
    return market_table_content, amount_sum, json.dumps(name_array), value_array


def get_value_account_content(position_currency, price_array, HKD_rate, USD_rate):
    account_table_array = []
    account_chart_array = []
    amount_array = []
    percent_array = []
    amount_sum = 0.0
    # 对position表分组查询，按account字段分组，返回每个分组的id（通过双下划线取得关联表的字段值）和每个分组的quantity个数
    account_dict = position.objects.filter(position_currency=position_currency).values("account").annotate(
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
        record_list = position.objects.filter(account=account_id, position_currency=position_currency).values(
            'stock__stock_code',
            'stock__stock_name',
            'position_quantity',
            'stock__market__transaction_currency'
        )
        for record in record_list:
            stock_code = record['stock__stock_code']
            stock_name = record['stock__stock_name']
            position_quantity = record['position_quantity']
            currency = record['stock__market__transaction_currency']
            price = list(filter(lambda x: stock_code in x, price_array))[0][1]
            if position_currency == 1:
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
    account_table_content.sort(key=take_col2, reverse=True)  # 对account_content列表按第二列（金额）降序排序
    account_chart_content.sort(key=take_col2, reverse=True)  # 对account_content列表按第二列（金额）降序排序
    name_array, value_array = get_chart_array(account_chart_content, -1, 0, 1)
    return account_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_stock_content(currency):
    stock_content = []
    amount_sum = 0.0
    stock_code_array = []
    stock_name_array = []
    amount_array = []
    percent_array = []
    stock_dict = dividend.objects.filter(dividend_currency=currency).values("stock").annotate(
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
    stock_content.sort(key=take_col3, reverse=True)  # 对account_content列表按第3列（金额）降序排序
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
    year_dict = dividend.objects.filter(dividend_currency=currency).values("dividend_date__year").annotate(
        amount=Sum("dividend_amount")).values('dividend_date__year', 'amount')
    for dict in year_dict:
        name_array1 = []
        name_list = ''
        year = dict['dividend_date__year']
        amount = dict['amount']
        amount_sum += float(amount)
        record_list = dividend.objects.filter(dividend_date__year=year, dividend_currency=currency).values(
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
    industry_dict = dividend.objects.filter(dividend_currency=currency).values("stock__industry").annotate(
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
        record_list = dividend.objects.filter(stock__industry=industry_id, dividend_currency=currency).values(
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
    industry_table_content.sort(key=take_col2, reverse=True)
    industry_chart_content.sort(key=take_col2, reverse=True)
    name_array, value_array = get_chart_array(industry_chart_content, -1, 0, 1)
    return industry_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_market_content(currency):
    amount_sum = 0.0
    market_table_array = []
    market_chart_array = []
    amount_array = []
    percent_array = []
    # 通过stock__industry按股票所属行业分组
    market_dict = dividend.objects.filter(dividend_currency=currency).values("stock__market").annotate(
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
        record_list = dividend.objects.filter(stock__market=market_id, dividend_currency=currency).values(
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
    market_table_content.sort(key=take_col2, reverse=True)
    market_chart_content.sort(key=take_col2, reverse=True)
    name_array, value_array = get_chart_array(market_chart_content, -1, 0, 1)
    return market_table_content, amount_sum, json.dumps(name_array), value_array


def get_dividend_account_content(currency):
    amount_sum = 0.0
    account_table_array = []
    account_chart_array = []
    amount_array = []
    percent_array = []
    # 通过stock__account按股票所属账号分组
    account_dict = dividend.objects.filter(dividend_currency=currency).values("account").annotate(
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
        record_list = dividend.objects.filter(account=account_id, dividend_currency=currency).values(
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
    account_table_content.sort(key=take_col2, reverse=True)
    account_chart_content.sort(key=take_col2, reverse=True)
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
    name_content.sort(key=take_col2, reverse=True)
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
        'stock__market__transaction_currency'
    )
    for dict in stock_dict:
        # 从字典tmp中取出’stock__stock_name‘的值
        stock_name = dict['stock__stock_name']
        stock_code = dict['stock__stock_code']
        quantity = dict['quantity']
        currency = dict['stock__market__transaction_currency']
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
    stock_table_content.sort(key=take_col2, reverse=True)  # 对stock_content列表按第2列（金额）降序排序
    stock_chart_content.sort(key=take_col2, reverse=True)  # 对stock_content列表按第2列（金额）降序排序
    name_array, value_array = get_chart_array(stock_chart_content, -1, 0, 1)
    return stock_table_content, amount_sum, json.dumps(name_array), value_array


def get_stock_profit(stock_code):
    amount_sum = 0
    quantity_sum = 0
    trade_array = []
    stock_id = stock.objects.all().get(stock_code=stock_code).id
    trade_list = trade.objects.all().filter(stock=stock_id).order_by('trade_date')
    # stock_code = trade_list[0].stock.stock_code
    price, increase, color = get_stock_price(stock_code)
    for rs in trade_list:
        if rs.trade_type == 2:
            trade_quantity = -1 * rs.trade_quantity
        else:
            trade_quantity = rs.trade_quantity
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
        quantity_sum += trade_quantity
    value = price * quantity_sum
    if quantity_sum == 0:
        price_avg = 0  # 负无穷大
    else:
        price_avg = amount_sum / quantity_sum
    # profit = (price - float(price_avg)) * quantity_sum
    profit = price * quantity_sum - float(amount_sum)
    if amount_sum > 0:
        profit_margin = profit / float(amount_sum) * 100
    else:
        profit_margin = 9999.99  # 正无穷大
    # trade_array.sort(key=take_col1, reverse=True)
    return trade_array, amount_sum, value, quantity_sum, price_avg, price, profit, profit_margin
