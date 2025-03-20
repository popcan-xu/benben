from asyncio import tasks

from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import render, redirect, HttpResponse
from django.db import models, connection
from .models import broker, market, account, industry, stock, position, trade, dividend, subscription, dividend_history, \
    funds, funds_details, historical_position, historical_rate, historical_market_value
from utils.excel2db import *
from utils.statistics import *
from utils.utils import *
from django.template.defaulttags import register
import datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal

from django.db.models.functions import ExtractYear
from django.core.cache import cache

import pathlib

import json
import pandas as pd

from django.db import transaction
from django.db.models import Sum, Q, Window, F, Min, Max
from django.db.models.functions import Lag
from collections import defaultdict


#from django.db import transaction, IntegrityError, OperationalError
#from django.db.models import Case, When, Sum, F, Q
import logging
logger = logging.getLogger(__name__)

templates_path = 'dashboard/'

# 总览
def overview(request):
    rate_HKD, rate_USD = get_rate()
    path = pathlib.Path("./templates/dashboard/overview.json")
    if path.is_file() and request.method != 'POST': # 若json文件存在and未点击刷新按钮，从json文件中读取overview页面需要的数据以提高性能
        # 读取overview.json
        # overview = FileOperate(filepath='./templates/dashboard/', filename='overview.json').operation_file()
        with open('./templates/dashboard/overview.json', 'r', encoding='utf-8') as f:
            overview = json.load(f)
    else: # 若json文件不存在or点击了刷新按钮，重写json文件（文件不存在则创建文件），再从json文件中读取overview页面需要的数据
        current_year = datetime.datetime.now().year
        # current_year = 2021
        # 获得汇率数据
        # rate_HKD, rate_USD = get_rate()
        # 获得人民币、港元、美元分红总收益
        dividend_sum_CNY = dividend.objects.filter(dividend_currency=1).aggregate(amount=Sum('dividend_amount'))['amount']
        dividend_sum_HKD = dividend.objects.filter(dividend_currency=2).aggregate(amount=Sum('dividend_amount'))['amount']
        dividend_sum_USD = dividend.objects.filter(dividend_currency=3).aggregate(amount=Sum('dividend_amount'))['amount']
        dividend_sum = float(dividend_sum_CNY) + float(dividend_sum_HKD) * rate_HKD + float(dividend_sum_USD) * rate_USD
        # 获得当年人民币、港元、美元分红总收益
        current_dividend_sum_CNY = dividend.objects.filter(dividend_currency=1, dividend_date__year=current_year).aggregate(amount=Sum('dividend_amount'))['amount']
        current_dividend_sum_HKD = dividend.objects.filter(dividend_currency=2, dividend_date__year=current_year).aggregate(amount=Sum('dividend_amount'))['amount']
        current_dividend_sum_USD = dividend.objects.filter(dividend_currency=3, dividend_date__year=current_year).aggregate(amount=Sum('dividend_amount'))['amount']
        # print(current_dividend_sum_CNY)
        if current_dividend_sum_CNY == None:
            current_dividend_sum_CNY = 0
        if current_dividend_sum_HKD == None:
            current_dividend_sum_HKD = 0
        if current_dividend_sum_USD == None:
            current_dividend_sum_USD = 0
        current_dividend_sum = float(current_dividend_sum_CNY) + float(current_dividend_sum_HKD) * rate_HKD + float(current_dividend_sum_USD) * rate_USD
        # 获得新股、新债总收益、中签数量
        subscription_sum = float(subscription.objects.aggregate(amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity")))['amount'])
        subscription_stock_num = subscription.objects.filter(subscription_type=1).count()
        subscription_band_num = subscription.objects.filter(subscription_type=2).count()
        # 获得当年新股、新债总收益、中签数量
        current_subscription_sum = subscription.objects.filter(subscription_date__year=current_year).aggregate(
            amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity")))['amount']
        if current_subscription_sum == None:
            current_subscription_sum = 0
        current_subscription_sum = float(current_subscription_sum)
        current_subscription_stock_num = subscription.objects.filter(subscription_date__year=current_year, subscription_type=1).count()
        current_subscription_band_num = subscription.objects.filter(subscription_date__year=current_year, subscription_type=2).count()
        # 获取持仓股票数量
        holding_stock_number = position.objects.values("stock").annotate(count=Count("stock")).count()
        # 获得总市值、持仓股票一览数据、持仓前五占比数据
        price_array = []  # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_array中，以提高性能
        stock_dict = position.objects.values("stock").annotate(count=Count("stock")).values('stock__stock_code')

        # for dict in stock_dict:
        #     stock_code = dict['stock__stock_code']
        #     price, increase, color = get_stock_price(stock_code)
        #     price_array.append((stock_code, price, increase, color))
        stock_code_array = []
        for dict in stock_dict:
            stock_code = dict['stock__stock_code']
            stock_code_array.append(stock_code)
        price_array = get_stock_array_price(stock_code_array)

        # position_currency=0时，get_value_stock_content返回人民币、港元、美元计价的所有股票的人民币市值汇总
        content, value_sum, name_array, value_array = get_value_stock_content(0, price_array, rate_HKD, rate_USD)
        # 计算当年分红占总市值的百分比
        current_dividend_percent = float(current_dividend_sum / value_sum) * 100
        # 计算前五大持仓百分比之和
        top5_content = content[:5]
        top5_percent = 0.0
        i = 0
        while i < len(top5_content):
            top5_percent += float(top5_content[i][6][:-1])  # [:-1]用于截去百分比字符串的最后一位（百分号）
            i += 1
        # 获得持仓币种占比数据，用于生成chart图表
        market_name_array, market_value_array = get_value_market_sum(price_array, rate_HKD, rate_USD)
        # 获得近期交易列表
        top5_trade_list = trade.objects.all().order_by('-trade_date', '-modified_time')[:5]
        # 获得近期分红列表
        top5_dividend_list = dividend.objects.all().order_by('-dividend_date', '-modified_time')[:5]
        # 获得近期打新列表
        top5_subscription_list = subscription.objects.all().order_by('-subscription_date', '-modified_time')[:5]

        # 写入overview.json
        overview = {}
        # 汇率
        #overview.update(rate_HKD=rate_HKD, rate_USD=rate_USD)
        # 总市值、分红收益、当年分红、当年分红率、打新收益、当年打新、持股数量
        overview.update(value_sum=value_sum)
        overview.update(dividend_sum=dividend_sum)
        overview.update(current_dividend_sum=current_dividend_sum)
        overview.update(current_dividend_percent=current_dividend_percent)
        overview.update(subscription_sum=subscription_sum)
        overview.update(subscription_stock_num=subscription_stock_num)
        overview.update(subscription_band_num=subscription_band_num)
        overview.update(current_subscription_sum=current_subscription_sum)
        overview.update(current_subscription_stock_num=current_subscription_stock_num)
        overview.update(current_subscription_band_num=current_subscription_band_num)
        overview.update(holding_stock_number=holding_stock_number)
        # 持藏股票一览
        holding_stock_array = []
        for i in content:
            holding_stock_array.append((i[0], i[1], i[2], i[3]))
        overview.update(holding_stock_array=holding_stock_array)
        # 持仓前五占比
        overview.update(top5_percent=top5_percent)
        top5_array = []
        index = 0
        progress_bar_bg = ['primary', 'secondary', 'success', 'info', 'warning', 'danger']
        # progress_bar_bg = ['primary', 'secondary', 'success', 'info', 'warning']
        for i in top5_content:
            top5_array.append((i[0], i[5], i[6], progress_bar_bg[index]))
            index += 1
        overview.update(top5_array=top5_array)
        # 持仓币种占比
        overview.update(market_name_array=market_name_array)
        overview.update(market_value_array=market_value_array)
        # 近期交易
        trade_array = []
        for i in top5_trade_list:
            trade_array.append((
                i.trade_date.strftime("%Y-%m-%d"),
                str(i.stock.stock_name) + '（' + str(i.stock.stock_code) + '）',
                str(i.get_trade_type_display()),
                float(i.trade_price),
                i.trade_quantity,
                float(i.trade_price * i.trade_quantity),
                str(i.get_settlement_currency_display()),
                i.account.account_abbreviation
            ))
        overview.update(trade_array=trade_array)
        # 近期分红
        dividend_array = []
        for i in top5_dividend_list:
            dividend_array.append((
                i.dividend_date.strftime("%Y-%m-%d"),
                str(i.stock.stock_name) + '（' + str(i.stock.stock_code) + '）',
                float(i.dividend_amount),
                i.account.account_abbreviation
            ))
        overview.update(dividend_array=dividend_array)
        # 近期打新
        subscription_array = []
        for i in top5_subscription_list:
            subscription_array.append((
                i.subscription_date.strftime("%Y-%m-%d"),
                str(i.subscription_name),
                str(i.get_subscription_type_display()),
                i.subscription_quantity,
                float((i.selling_price - i.buying_price) * i.subscription_quantity),
                float(((i.selling_price / i.buying_price) - 1) * 100),
                i.account.account_abbreviation
            ))
        overview.update(subscription_array=subscription_array)
        # 打时间戳
        overview.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # 写入json文件
        FileOperate(dictData=overview, filepath='./templates/dashboard/',
                    filename='overview.json').operation_file()


    #rate = FileOperate(filepath='./templates/dashboard/', filename='rate.json').operation_file()
    #path = pathlib.Path("./templates/dashboard/rate.json")
    #if path.is_file() == True and request.method != 'POST': # 若json文件存在and未点击刷新按钮，从json文件中读取overview页面需要的数据以提高性能
    #    with open('./templates/dashboard/rate.json', 'r', encoding='utf-8') as f:
    #        rate = json.load(f)
    #else:
    #    pass
    # return render(request, templates_path + 'overview.html', {'overview':overview})
    return render(request, templates_path + 'overview.html', locals())


# 投资记账
def investment_accounting(request):
    funds_list = funds.objects.all()
    rate_HKD, rate_USD = get_rate()

    path = pathlib.Path("./templates/dashboard/baseline.json")
    if path.is_file() == True and request.method != 'POST': # 若json文件存在and未点击刷新按钮，从json文件中读取overview页面需要的数据以提高性能
        pass
    elif path.is_file() == False : # json文件不存在，则创建文件
        # 获取指数历史数据
        get_his_index()
    else: #点击刷新按钮
        # 获得汇率数据
        rate_HKD, rate_USD = get_rate()
        # 更新当年指数数据
        get_current_index()
    #rate = FileOperate(filepath='./templates/dashboard/', filename='rate.json').operation_file()
    #with open('./templates/dashboard/rate.json', 'r', encoding='utf-8') as f:
    #    rate = json.load(f)
    # baseline = FileOperate(filepath='./templates/dashboard/', filename='baseline.json').operation_file()
    with open('./templates/dashboard/baseline.json', 'r', encoding='utf-8') as f:
        baseline = json.load(f)


    return render(request, templates_path + 'investment_accounting.html', locals())


def view_funds_details(request, funds_id):
    annual_data_group = []
    name_list = []
    funds_net_value_list = []
    baseline_net_value_list = []
    funds_profit_rate_list = []
    baseline_profit_rate_list = []
    year_end_date_list = []
    list1 = []
    list2 = []

    funds_details_list = funds_details.objects.filter(funds=funds_id).order_by("date")
    funds_name = funds.objects.get(id=funds_id).funds_name
    funds_baseline_name = funds.objects.get(id=funds_id).funds_baseline
    max_date = get_max_date(funds_id)
    min_date = get_min_date(funds_id)
    second_max_date = get_second_max_date(funds_id)
    current_funds_details_object = funds_details_list.get(date=max_date) #生成概要数据
    last_period_value = current_funds_details_object.funds_value - current_funds_details_object.funds_current_profit
    last_year_max_date = funds_details.objects.filter(
        date__year=datetime.date.today().year - 1,
        funds=funds_id
    ).aggregate(
        max_date=Max('date')
    )['max_date']
    last_year_value = funds_details_list.get(date=last_year_max_date).funds_value
    year_change_amount = current_funds_details_object.funds_value - last_year_value
    if last_year_value != Decimal('0.0000') and year_change_amount != Decimal('0.0000'):
        year_change_rate = year_change_amount / last_year_value
    else:
        year_change_rate = 0
    last_year_net_value = funds_details_list.get(date=last_year_max_date).funds_net_value
    if last_year_net_value != Decimal('0.0000'):
        year_change_net_value_rate = current_funds_details_object.funds_net_value / last_year_net_value -1
    else:
        year_change_net_value_rate = 0

    name_list.append(funds_name)
    name_list.append(funds_baseline_name)
    path = pathlib.Path("./templates/dashboard/baseline.json")
    if path.is_file(): # 若json文件存，从json文件中读取页面需要的数据以提高性能
        # 读取baseline.json
        with open('./templates/dashboard/baseline.json', 'r', encoding='utf-8') as f:
            baseline = json.load(f)

    min_date_baseline_value = get_baseline_closing_price(baseline[funds_baseline_name], int(min_date.year))

    # 按年份分组并计数
    rs = funds_details_list.annotate(year=ExtractYear('date')).values('year').annotate(count=Count('id')).order_by('year')
    pre_funds_net_value = 1
    pre_baseline_net_value = 1
    for r in rs:
        year_end_date = get_year_end_date(funds_id, r['year'])

        funds_value = funds_details_list.get(date=year_end_date).funds_value
        funds_net_value = funds_details_list.get(date=year_end_date).funds_net_value
        list1.append(funds_net_value)
        funds_profit_rate = funds_net_value / pre_funds_net_value - 1
        pre_funds_net_value = funds_net_value

        baseline_value = get_baseline_closing_price(baseline[funds_baseline_name], int(r['year']))
        baseline_net_value = baseline_value / min_date_baseline_value
        list2.append(baseline_net_value)
        baseline_profit_rate = baseline_net_value / pre_baseline_net_value -1
        pre_baseline_net_value = baseline_net_value

        earliest_date = get_min_date(funds_id)
        years = float((year_end_date - earliest_date).days / 365)
        if years == 0:
            funds_annualized_profit_rate = 0
            baseline_annualized_profit_rate = 0
        else:
            funds_annualized_profit_rate = float(funds_net_value) ** (1 / years) - 1
            baseline_annualized_profit_rate = float(baseline_net_value) ** (1 / years) - 1

        if len(list1) <= 3:
            funds_annualized_profit_rate_3years = 0
            baseline_annualized_profit_rate_3years = 0
            funds_annualized_profit_rate_5years = 0
            baseline_annualized_profit_rate_5years = 0
        elif len(list1) <= 5:
            funds_annualized_profit_rate_3years = (float(list1[-1]) / float(list1[-4])) ** (1 / 3) - 1
            baseline_annualized_profit_rate_3years = (float(list2[-1]) / float(list2[-4])) ** (1 / 3) - 1
            funds_annualized_profit_rate_5years = 0
            baseline_annualized_profit_rate_5years = 0
        else:
            funds_annualized_profit_rate_3years = (float(list1[-1]) / float(list1[-4])) ** (1 / 3) - 1
            baseline_annualized_profit_rate_3years = (float(list2[-1]) / float(list2[-4])) ** (1 / 3) - 1
            funds_annualized_profit_rate_5years = (float(list1[-1]) / float(list1[-6])) ** (1 / 5) - 1
            baseline_annualized_profit_rate_5years = (float(list2[-1]) / float(list2[-6])) ** (1 / 5) - 1

        compare_profit_rate = float(funds_profit_rate) - float(baseline_profit_rate)
        compare_annualized_profit_rate = float(funds_annualized_profit_rate) - float(baseline_annualized_profit_rate)
        compare_annualized_profit_rate_3years = float(funds_annualized_profit_rate_3years) - float(baseline_annualized_profit_rate_3years)
        compare_annualized_profit_rate_5years = float(funds_annualized_profit_rate_5years) - float(baseline_annualized_profit_rate_5years)

        # 生成收益率对比数据
        item = []
        item.append(str(year_end_date.year)) # 年份
        item.append(Decimal(funds_value).quantize(Decimal('0'))) # 基金价值
        item.append(Decimal(baseline_value).quantize(Decimal('0.00'))) # 比较基准点数
        item.append(Decimal(funds_net_value).quantize(Decimal('0.0000'))) # 基金净值
        item.append(Decimal(baseline_net_value).quantize(Decimal('0.0000'))) # 比较基准净值
        item.append(Decimal(funds_profit_rate * 100).quantize(Decimal('0.00'))) # 基金收益率
        item.append(Decimal(baseline_profit_rate * 100).quantize(Decimal('0.00'))) # 比较基准收益率
        item.append(Decimal(compare_profit_rate * 100).quantize(Decimal('0.00'))) # 收益率对比
        item.append(Decimal(funds_annualized_profit_rate * 100).quantize(Decimal('0.00'))) # 基金年化
        item.append(Decimal(baseline_annualized_profit_rate * 100).quantize(Decimal('0.00'))) # 比较基准年化
        item.append(Decimal(compare_annualized_profit_rate * 100).quantize(Decimal('0.00'))) # 年化对比
        item.append(Decimal(funds_annualized_profit_rate_3years * 100).quantize(Decimal('0.00'))) # 基金连续3年年化
        item.append(Decimal(baseline_annualized_profit_rate_3years * 100).quantize(Decimal('0.00'))) #比较基准连续3年年化
        item.append(Decimal(compare_annualized_profit_rate_3years * 100).quantize(Decimal('0.00'))) #连续3年年化对比
        item.append(Decimal(funds_annualized_profit_rate_5years * 100).quantize(Decimal('0.00'))) # 基金连续5年年化
        item.append(Decimal(baseline_annualized_profit_rate_5years * 100).quantize(Decimal('0.00'))) # 比较基准连续5年年化
        item.append(Decimal(compare_annualized_profit_rate_5years * 100).quantize(Decimal('0.00'))) # 连续5年年化对比
        annual_data_group.append(item)

        # 生成净值曲线（折线图）和年度收益率（柱图数据）
        year_end_date_list.append(float(year_end_date.year))
        funds_net_value_list.append(float(Decimal(funds_net_value).quantize(Decimal('0.0000'))))
        baseline_net_value_list.append(float(Decimal(baseline_net_value).quantize(Decimal('0.0000'))))
        funds_profit_rate_list.append(float(Decimal(funds_profit_rate * 100).quantize(Decimal('0.00'))))
        baseline_profit_rate_list.append(float(Decimal(baseline_profit_rate * 100).quantize(Decimal('0.00'))))

    line_value = [funds_net_value_list, baseline_net_value_list]
    bar_value = [funds_profit_rate_list[1:], baseline_profit_rate_list[1:]] # 柱图第一列去掉
    line_data = [name_list, line_value, year_end_date_list]
    bar_data = [name_list, bar_value, year_end_date_list[1:]] # 柱图第一列去掉

    # 生成资产变化日历字典数据assetChanges
    assetChanges = {}
    for rs in funds_details_list:
        date = rs.date.strftime("%Y-%m-%d")
        amount = float(rs.funds_current_profit)
        assetChanges[date] = amount

    data = []
    #funds_details_list = funds_details.objects.filter(funds=3)
    for rs in funds_details_list:
        date = str(rs.date)
        value = float(rs.funds_net_value)
        data.append({
            "date": date,
            "value": value
        })

    funds_details_list_TOP = funds_details.objects.filter(funds=funds_id).order_by("-date")[:10]

    updating_time = datetime.datetime.now()

    return render(request,  templates_path + 'view_funds_details.html', locals())


# 持仓市值
def market_value(request):
    currency_CNY = '人民币'
    currency_HKD = '港元'
    currency_USD = '美元'
    rate_HKD, rate_USD = get_rate()
    # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_array中，以提高性能
    stock_dict = position.objects.values("stock").annotate(
        count=Count("stock")).values('stock__stock_code').order_by('stock__stock_code')
    stock_code_array = []
    for dict in stock_dict:
        stock_code = dict['stock__stock_code']
        stock_code_array.append(stock_code)
    price_array = get_stock_array_price(stock_code_array)
    content_CNY, amount_sum_CNY, name_array_CNY, value_array_CNY = get_value_stock_content(1, price_array, rate_HKD, rate_USD)
    content_HKD, amount_sum_HKD, name_array_HKD, value_array_HKD = get_value_stock_content(2, price_array, rate_HKD, rate_USD)
    content_USD, amount_sum_USD, name_array_USD, value_array_USD = get_value_stock_content(3, price_array, rate_HKD, rate_USD)

    currency_dict = {1: '人民币', 2: '港元', 3: '美元'}
    value_dict = {}
    result = historical_market_value.objects.aggregate(
        max_date=Max('date')  # 最大值（最新日期）
    )
    current_date = result['max_date']

    for key in currency_dict:
        if historical_market_value.objects.filter(currency=currency_dict[key], date=current_date).exists():
            value_dict[key] = historical_market_value.objects.get(currency=currency_dict[key], date=current_date).value
        else:
            value_dict[key] = 0

    # 类现金市值计算
    cash_assets_rate_dict = {1: 0, 2: 0, 3: 0}
    current_price, increase, color = get_quote_snowball('511880') #银华日利
    positions = position.objects.filter(stock=93) #银华日利
    quantity = 0
    for pos in positions:
        quantity += pos.position_quantity
    cash_like_assets_CNY = current_price * quantity
    cash_assets_rate_dict[1] = cash_like_assets_CNY / amount_sum_CNY

    updating_time = current_date
    return render(request, templates_path + 'market_value.html', locals())


def view_market_value_details(request, currency_id):
    currency_dict = {1: '人民币', 2: '港元', 3: '美元'}
    result = historical_market_value.objects.aggregate(
        max_date=Max('date')  # 最大值（最新日期）
    )
    current_date = result['max_date']
    # if historical_market_value.objects.filter(currency=currency_dict[currency_id], date=current_date).exists():
    #     value = historical_market_value.objects.get(currency=currency_dict[currency_id], date=current_date).value
    # else:
    #     value = 0
    market_value_obj = historical_market_value.objects.get(currency=currency_dict[currency_id], date=current_date)

    today = datetime.date.today()  # 假设当前日期
    last_day_of_last_month = today.replace(day=1) - relativedelta(days=1)  # 上月最后一天
    last_day_of_last_year = datetime.date(today.year - 1, 12, 31)  # 上年最后一天

    # 获取上月最大日期
    last_month_max_date = historical_market_value.objects.filter(
        date__month=last_day_of_last_month.month,
        date__year=last_day_of_last_month.year,
        currency=currency_dict[currency_id]
    ).aggregate(
        max_date=Max('date')
    )['max_date']

    # 按货币分组获取上年最大日期
    last_year_max_date = historical_market_value.objects.filter(
        date__year=last_day_of_last_year.year,
        currency=currency_dict[currency_id]
    ).aggregate(
        max_date=Max('date')
    )['max_date']

    last_month_value = historical_market_value.objects.get(date=last_month_max_date, currency=currency_dict[currency_id]).value
    month_change_amount = market_value_obj.value - last_month_value
    if last_month_value != Decimal('0.0000') and month_change_amount != Decimal('0.0000'):
        month_change_rate = month_change_amount / last_month_value
    else:
        month_change_rate = 0
    last_year_value = historical_market_value.objects.get(date=last_year_max_date, currency=currency_dict[currency_id]).value
    year_change_amount = market_value_obj.value - last_year_value
    if last_year_value != Decimal('0.0000') and year_change_amount != Decimal('0.0000'):
        year_change_rate = year_change_amount / last_year_value
    else:
        year_change_rate = 0


    # 生成持仓市值曲线数据data
    data = []
    market_value_list = historical_market_value.objects.filter(currency=currency_dict[currency_id]).order_by("date")
    for rs in market_value_list:
        date = str(rs.date)
        value = float(rs.value)
        data.append({
            "date": date,
            "value": value / 10000
        })

    # 生成市值变化日历字典数据assetChanges
    assetChanges = {}
    for rs in market_value_list:
        date = rs.date.strftime("%Y-%m-%d")
        amount = float(rs.change_amount)
        assetChanges[date] = amount

    market_value_list_TOP = historical_market_value.objects.filter(currency=currency_dict[currency_id]).order_by("-date")[:10]
    updating_time = current_date
    return render(request, templates_path + 'view_market_value_details.html', locals())


# 交易录入
def input_trade(request):
    trade_type_items = (
        (1, '买'),
        (2, '卖'),
    )
    settlement_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_active = account.objects.filter(is_active=True)
    account_not_active = account.objects.filter(is_active=False)
    stock_hold, stock_not_hold = get_stock_hold_or_not()

    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        trade_date = request.POST.get('trade_date')
        trade_type = request.POST.get('trade_type')
        trade_price = request.POST.get('trade_price')
        trade_quantity = request.POST.get('trade_quantity')
        settlement_currency = request.POST.get('settlement_currency')
        if stock_id.strip() == '':
            error_info = "股票不能为空！"
            return render(request, templates_path + 'input/input_trade.html', locals())
        try:
            # 新增一条交易记录
            p = trade.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                trade_date=trade_date,
                trade_type=trade_type,
                trade_price=trade_price,
                trade_quantity=trade_quantity,
                settlement_currency=settlement_currency,
                filed_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            # 更新（删除）或新增一条仓位记录
            position_objects = position.objects.filter(stock_id=stock_id, account_id=account_id)
            if position_objects.exists():
                # 更新一条仓位记录
                if trade_type == '2':
                    trade_quantity = -1 * int(trade_quantity)
                else:
                    trade_quantity = int(trade_quantity)
                for position_object in position_objects:
                    position_object.position_quantity += trade_quantity
                    position_object.save()
                    if position_object.position_quantity == 0:
                        position_object.delete()
            else:
                # 新增一条仓位记录
                q = position.objects.create(
                    account_id=account_id,
                    stock_id=stock_id,
                    position_quantity=trade_quantity,
                    position_currency=settlement_currency
                )
            return redirect('/benben/list_trade/')
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'input/input_trade.html', locals())
        finally:
            pass
    return render(request, templates_path + 'input/input_trade.html', locals())


# 分红录入
def input_dividend(request):
    dividend_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_active = account.objects.filter(is_active=True)
    account_not_active = account.objects.filter(is_active=False)
    stock_hold, stock_not_hold = get_stock_hold_or_not()

    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        dividend_date = request.POST.get('dividend_date')
        dividend_amount = request.POST.get('dividend_amount')
        dividend_currency = request.POST.get('dividend_currency')
        if stock_id.strip() == '':
            return render(request, templates_path + 'input/input_dividend.html', locals())
        try:
            p = dividend.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                dividend_date=dividend_date,
                dividend_amount=dividend_amount,
                dividend_currency=dividend_currency
            )
            return redirect('/benben/list_dividend/')
        except Exception as e:
            return render(request, templates_path + 'input/input_dividend.html', locals())
        finally:
            pass
    return render(request, templates_path + 'input/input_dividend.html', locals())


# 打新录入
def input_subscription(request):
    subscription_type_items = (
        (1, '股票'),
        (2, '可转债'),
    )
    account_active = account.objects.filter(is_active=True)
    account_not_active = account.objects.filter(is_active=False)
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        subscription_name = request.POST.get('subscription_name')
        subscription_date = request.POST.get('subscription_date')
        subscription_type = request.POST.get('subscription_type')
        subscription_quantity = request.POST.get('subscription_quantity')
        buying_price = request.POST.get('buying_price')
        selling_price = request.POST.get('selling_price')
        if account_id.strip() == '':
            return render(request, templates_path + 'input/input_subscription.html', locals())
        try:
            p = subscription.objects.create(
                account_id=account_id,
                subscription_name=subscription_name,
                subscription_date=subscription_date,
                subscription_type=subscription_type,
                subscription_quantity=subscription_quantity,
                buying_price=buying_price,
                selling_price=selling_price
            )
            return redirect('/benben/list_subscription/')
        except Exception as e:
            return render(request, templates_path + 'input/input_subscription.html', locals())
        finally:
            pass
    return render(request, templates_path + 'input/input_subscription.html', locals())


# 仓位统计
def stats_position(request):
    currency_CNY = 1
    currency_HKD = 2
    currency_USD = 3
    position_content_CNY, abbreviation_array_CNY, account_num_CNY, stock_num_CNY = get_position_content(currency_CNY)
    position_content_HKD, abbreviation_array_HKD, account_num_HKD, stock_num_HKD = get_position_content(currency_HKD)
    position_content_USD, abbreviation_array_USD, account_num_USD, stock_num_USD = get_position_content(currency_USD)
    cols_CNY = range(1, account_num_CNY + 2)
    cols_HKD = range(1, account_num_HKD + 2)
    cols_USD = range(1, account_num_USD + 2)
    return render(request, templates_path + 'stats/stats_position.html', locals())


# 市值统计
def stats_value(request):
    caliber_items = (
        (1, '股票'),
        (2, '行业'),
        (3, '市场'),
        (4, '账户'),
    )
    currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    caliber = 1
    currency = 1
    currency_name = currency_items[currency-1][1]
    condition_id = '11'
    price_array = []
    rate_HKD, rate_USD = get_rate()

    if request.method == 'POST':
        caliber = int(request.POST.get('caliber'))
        currency = int(request.POST.get('currency'))
        currency_name = currency_items[currency-1][1]
        condition_id = str(caliber) + str(currency)
        # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_increase_array中，以提高性能
        stock_dict = position.objects.filter(position_currency=currency).values("stock").annotate(
            count=Count("stock")).values('stock__stock_code')
        # for dict in stock_dict:
        #     stock_code = dict['stock__stock_code']
        #     price, increase, color = get_stock_price(stock_code)
        #     price_array.append((stock_code, price, increase, color))
        stock_code_array = []
        for dict in stock_dict:
            stock_code = dict['stock__stock_code']
            stock_code_array.append(stock_code)
        price_array = get_stock_array_price(stock_code_array)
        if caliber == 1:
            content, amount_sum, name_array, value_array = get_value_stock_content(currency, price_array, rate_HKD, rate_USD)
        elif caliber == 2:
            content, amount_sum, name_array, value_array = get_value_industry_content(currency, price_array, rate_HKD, rate_USD)
        elif caliber == 3:
            content, amount_sum, name_array, value_array = get_value_market_content(currency, price_array, rate_HKD, rate_USD)
        elif caliber == 4:
            content, amount_sum, name_array, value_array = get_value_account_content(currency, price_array, rate_HKD, rate_USD)
        else:
            pass

    return render(request, templates_path + 'stats/stats_value.html', locals())


# 账户统计
def stats_account(request):
    account_list1 = account.objects.all().filter(broker__broker_script='境内券商')
    account_list2 = account.objects.all().filter(broker__broker_script='境外券商')
    account_abbreviation = '银河6811'
    rate_HKD, rate_USD = get_rate()
    if request.method == 'POST':
        account_abbreviation = request.POST.get('account')
        account_id = account.objects.get(account_abbreviation=account_abbreviation).id
        price_array = []
        # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_increase_array中，以提高性能
        stock_dict = position.objects.filter(account=account_id).values("stock").annotate(
            count=Count("stock")).values('stock__stock_code')
        # for dict in stock_dict:
        #     stock_code = dict['stock__stock_code']
        #     price, increase, color = get_stock_price(stock_code)
        #     price_array.append((stock_code, price))
        stock_code_array = []
        for dict in stock_dict:
            stock_code = dict['stock__stock_code']
            stock_code_array.append(stock_code)
        price_array = get_stock_array_price(stock_code_array)
        stock_content, amount_sum, name_array, value_array = get_account_stock_content(account_id, price_array, rate_HKD, rate_USD)
    return render(request, templates_path + 'stats/stats_account.html', locals())


# 分红统计
def stats_dividend(request):
    caliber_items = (
        (1, '股票'),
        (2, '年份'),
        (3, '行业'),
        (4, '市场'),
        (5, '账户'),
    )
    dividend_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    caliber = 1
    dividend_currency = 1
    currency_name = dividend_currency_items[dividend_currency-1][1]
    condition_id = '11'
    if request.method == 'POST':
        caliber = int(request.POST.get('caliber'))
        dividend_currency = int(request.POST.get('dividend_currency'))
        currency_name = dividend_currency_items[dividend_currency - 1][1]
        condition_id = str(caliber) + str(dividend_currency)
        if caliber == 1:
            content, amount_sum, name_array, value_array = get_dividend_stock_content(dividend_currency)
        elif caliber == 2:
            content, amount_sum, name_array, value_array = get_dividend_year_content(dividend_currency)
        elif caliber == 3:
            content, amount_sum, name_array, value_array = get_dividend_industry_content(dividend_currency)
        elif caliber == 4:
            content, amount_sum, name_array, value_array = get_dividend_market_content(dividend_currency)
        elif caliber == 5:
            content, amount_sum, name_array, value_array = get_dividend_account_content(dividend_currency)
        else:
            pass

    return render(request, templates_path + 'stats/stats_dividend.html', locals())


# 打新统计
def stats_subscription(request):
    caliber_items = (
        (1, '年份'),
        (2, '账户'),
        (3, '名称'),
    )
    subscription_type_items = (
        (1, '股票'),
        (2, '可转债'),
    )
    caliber = 1
    subscription_type = 1
    type_name = subscription_type_items[subscription_type-1][1]
    condition_id = '11'
    if request.method == 'POST':
        caliber = int(request.POST.get('caliber'))
        subscription_type = int(request.POST.get('subscription_type'))
        type_name = subscription_type_items[subscription_type-1][1]
        condition_id = str(caliber) + str(subscription_type)
        if caliber == 1:
            content, amount_sum, name_array, value_array = get_subscription_year_content(subscription_type)
        elif caliber == 2:
            content, amount_sum, name_array, value_array = get_subscription_account_content(subscription_type)
        elif caliber == 3:
            content, amount_sum, name_array, value_array = get_subscription_name_content(subscription_type)
        else:
            pass

    return render(request, templates_path + 'stats/stats_subscription.html', locals())


# 盈亏统计
def stats_profit(request):
    rate_HKD, rate_USD = get_rate()
    holding_profit_array = []
    cleared_profit_array = []
    holding_profit_sum = 0
    cleared_profit_sum = 0
    holding_value_sum = 0
    holding_stock_list = stock.objects.filter(position__stock_id__isnull=False).distinct().order_by('stock_code')
    cleared_stock_list = stock.objects.filter(position__stock_id__isnull=True, trade__stock_id__isnull=False).distinct().order_by('stock_code')
    for rs in holding_stock_list:
        stock_id = rs.id
        stock_code = rs.stock_code
        stock_name = rs.stock_name
        transaction_currency = rs.market.transaction_currency
        trade_list = trade.objects.all().filter(stock=stock_id)
        trade_array, amount_sum, value, quantity_sum, price_avg, price, profit, profit_margin, cost_sum = get_holding_stock_profit(
            stock_code)
        if transaction_currency == 2:
            profit *= rate_HKD
            value *= rate_HKD
        elif transaction_currency == 3:
            profit *= rate_USD
            value *= rate_USD
        holding_profit_sum += profit
        holding_value_sum += value
        holding_profit_array.append((stock_name, stock_code, profit, value))
    holding_profit_array.sort(key=take_col4, reverse=True)  # 对account_content列表按第3列（金额）降序排序
    for rs in cleared_stock_list:
        stock_id = rs.id
        stock_code = rs.stock_code
        stock_name = rs.stock_name
        transaction_currency = rs.market.transaction_currency
        trade_list = trade.objects.all().filter(stock=stock_id)
        if trade_list.exists() and stock_code != '-1':
            trade_array, profit, profit_margin, cost_sum = get_cleared_stock_profit(stock_code)
            if transaction_currency == 2:
                profit *= rate_HKD
            elif transaction_currency == 3:
                profit *= rate_USD
            cleared_profit_sum += profit
            cleared_profit_array.append((stock_name, stock_code, profit))
    return render(request, templates_path + 'stats/stats_profit.html', locals())


# 交易查询
def query_trade(request):
    stock_list = stock.objects.all().values('stock_name', 'stock_code').order_by('stock_code')
    holding_stock_list = stock.objects.filter(position__stock_id__isnull=False).distinct().values('stock_name', 'stock_code').order_by('stock_code')
    cleared_stock_list = stock.objects.filter(position__stock_id__isnull=True, trade__stock_id__isnull=False).distinct().values('stock_name', 'stock_code').order_by('stock_code')
    if request.method == 'POST':
        form_type = request.POST.get("form_type")
        form = None
        if form_type == 'holding_stock':
            stock_code = request.POST.get('stock_code')
            stock_name = stock.objects.get(stock_code=stock_code).stock_name
            market = stock.objects.get(stock_code=stock_code).market
            trade_array_1, amount_sum_1, value_1, quantity_sum_1, price_avg_1, price_1, profit_1, profit_margin_1, cost_sum_1 = get_holding_stock_profit(stock_code)
        elif form_type == 'cleared_stock':
            stock_code = request.POST.get('stock_code')
            stock_name = stock.objects.get(stock_code=stock_code).stock_name
            market = stock.objects.get(stock_code=stock_code).market
            trade_array_2, profit_2, profit_margin_2, cost_sum_2 = get_cleared_stock_profit(stock_code)
    return render(request, templates_path + 'query/query_trade.html', locals())


# 分红金额查询
def query_dividend_value(request):
    dividend_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    stock_list = stock.objects.all().values('stock_code', 'stock_name', 'last_dividend_date', 'next_dividend_date')
    # 持仓股票列表，通过.filter(dividend__stock_id__isnull = False)，过滤出在dividend表中存在的stock_id所对应的stock表记录
    dividends_stock_list = stock_list.filter(dividend__stock_id__isnull=False).distinct()
    # 分红年份列表，通过.dates('dividend_date', 'year')，过滤出dividend表中存在的dividend_date所对应的年份列表
    year_list = dividend.objects.dates('dividend_date', 'year')
    # 按账号对应的券商备注（境内券商或境外券商）排序
    account_list = account.objects.all().order_by('broker__broker_script')
    # 第一次进入页面，默认货币为人民币，账户全选、年份全选为否。
    dividend_currency = 1
    # 根据dividend_currency的值从dividend_currency_items中生成dividend_currency_name
    dividend_currency_name = dividend_currency_items[dividend_currency-1][1]
    is_all_account_checked = "false"
    is_all_year_checked = "false"
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        # 由于stock_code为select列表而非文本框text，如果不选择则返回None而非空，所以不能使用stock_code.strip() == ''
        if stock_code is None:
            error_info = '股票不能为空！'
            return render(request, templates_path + 'stats/query_dividend_value.html', locals())
        stock_object = stock.objects.get(stock_code=stock_code)
        stock_id = stock_object.id
        stock_name = stock_object.stock_name
        dividend_year_list = request.POST.getlist('dividend_year_list')
        # 将列表中的字符串变成数字，方法一：
        dividend_year_list = [int(x) for x in dividend_year_list]
        dividend_account_list = request.POST.getlist('dividend_account_list')
        # 将列表中的字符串变成数字，方法二：使用内置map返回一个map对象，再用list将其转换为列表
        dividend_account_list = list(map(int, dividend_account_list))
        dividend_currency = int(request.POST.get('dividend_currency'))
        is_all_account_checked = request.POST.get('all_account')
        is_all_year_checked = request.POST.get('all_year')
        conditions = dict()
        conditions['stock'] = stock_id
        conditions['dividend_date__year__in'] = dividend_year_list
        conditions['account__in'] = dividend_account_list
        conditions['dividend_currency'] = dividend_currency
        dividend_list = dividend.objects.all().filter(**conditions).order_by('-dividend_date')
        amount_sum = 0
        for i in dividend_list:
            amount_sum += i.dividend_amount
    # 根据dividend_currency的值从dividend_currency_items中生成dividend_currency_name
    dividend_currency_name = dividend_currency_items[dividend_currency-1][1]
    return render(request, templates_path + 'query/query_dividend_value.html', locals())


# 分红日期查询
def query_dividend_date(request):
    current_year = datetime.datetime.today().year

    stock_list = stock.objects.all().values('stock_name', 'stock_code', 'last_dividend_date', 'next_dividend_date').order_by('stock_code')
    # 持仓股票列表，通过.filter(position__stock_id__isnull = False)，过滤出在position表中存在的stock_id所对应的stock表记录
    position_stock_list = stock_list.filter(position__stock_id__isnull=False).distinct().order_by('-next_dividend_date', '-last_dividend_date')
    # 当年已分红股票列表
    current_year_dividend_list = position_stock_list.filter(last_dividend_date__year=current_year).order_by('-next_dividend_date', '-last_dividend_date')
    # 当年未分红股票列表
    current_year_no_dividend_list = position_stock_list.filter(next_dividend_date__year=current_year).order_by('-next_dividend_date', '-last_dividend_date')

    # stock_name_array = []
    # stock_code_array = []
    # next_dividend_date_array = []
    # last_dividend_date_array = []
    # dividend_date_array = []
    # next_dividend_date = None
    # last_dividend_date = None
    # for rs in position_stock_list:
    #     stock_code = rs.stock_code
    #     stock_name = rs.stock_name
    #     #stock_dividend_dict = get_stock_dividend_history_2lines(stock_code)
    #     #next_dividend_date, last_dividend_date = get_dividend_date(stock_dividend_dict)
    #     stock_name_array.append(stock_name)
    #     stock_code_array.append(stock_code)
    #     next_dividend_date_array.append(next_dividend_date)
    #     last_dividend_date_array.append(last_dividend_date)
    # dividend_date_array = list(zip(stock_name_array, stock_code_array, last_dividend_date_array, next_dividend_date_array))

    return render(request, templates_path + 'query/query_dividend_date.html', locals())


# 分红历史查询
def query_dividend_history(request):
    stock_list = stock.objects.all().values('stock_name', 'stock_code').order_by('stock_code')
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        stock_dividend_dict = get_stock_dividend_history(stock_code)
        stock_name = stock.objects.get(stock_code=stock_code).stock_name
    return render(request, templates_path + 'query/query_dividend_history.html', locals())


# 券商表的增删改查
def add_broker(request):
    if request.method == 'POST':
        broker_name = request.POST.get('broker_name')
        broker_script = request.POST.get('broker_script')
        if broker_name.strip() == '':
            error_info = '券商名称不能为空！'
            return render(request, templates_path + 'backstage/add_broker.html', locals())
        try:
            p = broker.objects.create(
                broker_name=broker_name,
                broker_script=broker_script
            )
            return redirect('/benben/list_broker/')
        except Exception as e:
            error_info = '输入券商名称重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_broker.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_broker.html', locals())


def del_broker(request, broker_id):
    broker_object = broker.objects.get(id=broker_id)
    broker_object.delete()
    return redirect('/benben/list_broker/')


def edit_broker(request, broker_id):
    if request.method == 'POST':
        id = request.POST.get('id')
        broker_name = request.POST.get('broker_name')
        broker_script = request.POST.get('broker_script')
        broker_object = broker.objects.get(id=id)
        try:
            broker_object.broker_name = broker_name
            broker_object.broker_script = broker_script
            broker_object.save()
        except Exception as e:
            error_info = '输入券商名称重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_broker.html', locals())
        finally:
            pass
        return redirect('/benben/list_broker/')
    else:
        broker_object = broker.objects.get(id=broker_id)
        return render(request, templates_path + 'backstage/edit_broker.html', locals())


def list_broker(request):
    broker_list = broker.objects.all()
    return render(request, templates_path + 'backstage/list_broker.html', locals())


# 市场表的增删改查
def add_market(request):
    transaction_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    if request.method == 'POST':
        market_name = request.POST.get('market_name')
        market_abbreviation = request.POST.get('market_abbreviation')
        transaction_currency = request.POST.get('transaction_currency')
        if market_name.strip() == '':
            error_info = '市场名称不能为空！'
            return render(request, templates_path + 'backstage/add_market.html', locals())
        try:
            p = market.objects.create(
                market_name=market_name,
                market_abbreviation=market_abbreviation,
                transaction_currency=transaction_currency
            )
            return redirect('/benben/list_market/')
        except Exception as e:
            error_info = '输入市场名称重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_market.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_market.html', locals())


def del_market(request, market_id):
    market_object = market.objects.get(id=market_id)
    market_object.delete()
    return redirect('/benben/list_market/')


def edit_market(request, market_id):
    transaction_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    if request.method == 'POST':
        id = request.POST.get('id')
        market_name = request.POST.get('market_name')
        market_abbreviation = request.POST.get('market_abbreviation')
        transaction_currency = request.POST.get('transaction_currency')
        market_object = market.objects.get(id=id)
        try:
            market_object.market_name = market_name
            market_object.market_abbreviation = market_abbreviation
            market_object.transaction_currency = transaction_currency
            market_object.save()
        except Exception as e:
            error_info = '输入市场名称重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_market.html', locals())
        finally:
            pass
        return redirect('/benben/list_market/')
    else:
        market_object = market.objects.get(id=market_id)
        return render(request, templates_path + 'backstage/edit_market.html', locals())


def list_market(request):
    market_list = market.objects.all()
    return render(request, templates_path + 'backstage/list_market.html', locals())


# 账户表的增删改查
def add_account(request):
    broker_list = broker.objects.all().order_by('broker_script')
    if request.method == 'POST':
        account_number = request.POST.get('account_number')
        broker_id = request.POST.get('broker_id')
        account_abbreviation = request.POST.get('account_abbreviation')
        is_active = request.POST.get('is_active')
        if account_number.strip() == '':
            error_info = '账号不能为空！'
            return render(request, templates_path + 'backstage/add_account.html', locals())
        try:
            if is_active == 'TRUE':
                p = account.objects.create(
                    account_number=account_number,
                    broker_id=broker_id,
                    account_abbreviation=account_abbreviation,
                    is_active=True
                )
            else:
                p = account.objects.create(
                    account_number=account_number,
                    broker_id=broker_id,
                    account_abbreviation=account_abbreviation,
                    is_active=False
                )
            return redirect('/benben/list_account/')
        except Exception as e:
            error_info = '输入账号重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_account.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_account.html', locals())


def del_account(request, account_id):
    account_object = account.objects.get(id=account_id)
    account_object.delete()
    return redirect('/benben/list_account/')


def edit_account(request, account_id):
    broker_list = broker.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_number = request.POST.get('account_number')
        broker_id = request.POST.get('broker_id')
        account_abbreviation = request.POST.get('account_abbreviation')
        is_active = request.POST.get('is_active')
        print(is_active)
        account_object = account.objects.get(id=id)
        try:
            account_object.account_number = account_number
            account_object.broker_id = broker_id
            account_object.account_abbreviation = account_abbreviation
            if is_active == 'TRUE':
                account_object.is_active = True
            else:
                account_object.is_active = False
            account_object.save()
        except Exception as e:
            error_info = '输入账号重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_account.html', locals())
        finally:
            pass
        return redirect('/benben/list_account/')
    else:
        account_object = account.objects.get(id=account_id)
        return render(request, templates_path + 'backstage/edit_account.html', locals())


def list_account(request):
    account_list = account.objects.all().order_by("-is_active", "broker")
    return render(request, templates_path + 'backstage/list_account.html', locals())


# 行业表的增删改查
def add_industry(request):
    if request.method == 'POST':
        industry_code = request.POST.get('industry_code')
        industry_name = request.POST.get('industry_name')
        industry_abbreviation = request.POST.get('industry_abbreviation')
        if industry_code.strip() == '':
            error_info = '行业代码不能为空！'
            return render(request, templates_path + 'backstage/add_industry.html', locals())
        try:
            p = industry.objects.create(
                industry_code=industry_code,
                industry_name=industry_name,
                industry_abbreviation=industry_abbreviation
            )
            return redirect('/benben/list_industry/')
        except Exception as e:
            error_info = '输入行业代码重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_industry.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_industry.html', locals())


def del_industry(request, industry_id):
    industry_object = industry.objects.get(id=industry_id)
    industry_object.delete()
    return redirect('/benben/list_industry/')


def edit_industry(request, industry_id):
    if request.method == 'POST':
        id = request.POST.get('id')
        industry_code = request.POST.get('industry_code')
        industry_name = request.POST.get('industry_name')
        industry_abbreviation = request.POST.get('industry_abbreviation')
        industry_object = industry.objects.get(id=id)
        try:
            industry_object.industry_code = industry_code
            industry_object.industry_name = industry_name
            industry_object.industry_abbreviation = industry_abbreviation
            industry_object.save()
        except Exception as e:
            error_info = '输入行业代码重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_industry.html', locals())
        finally:
            pass
        return redirect('/benben/list_industry/')
    else:
        industry_object = industry.objects.get(id=industry_id)
        return render(request, templates_path + 'backstage/edit_industry.html', locals())


def list_industry(request):
    industry_list = industry.objects.all()
    return render(request,  templates_path + 'backstage/list_industry.html', locals())


# 股票表的增删改查
def add_stock(request):
    market_list = market.objects.all()
    industry_list = industry.objects.all()
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        stock_name = request.POST.get('stock_name')
        industry_id = request.POST.get('industry_id')
        market_id = request.POST.get('market_id')
        if stock_code.strip() == '':
            error_info = '股票代码不能为空！'
            return render(request, templates_path + 'backstage/add_stock.html', locals())
        try:
            p = stock.objects.create(
                stock_code=stock_code,
                stock_name=stock_name,
                industry_id=industry_id,
                market_id=market_id
            )
            return redirect('/benben/list_stock/')
        except Exception as e:
            error_info = '输入股票代码重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_stock.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_stock.html', locals())


def del_stock(request, stock_id):
    stock_object = stock.objects.get(id=stock_id)
    stock_object.delete()
    return redirect('/benben/list_stock/')


def edit_stock(request, stock_id):
    market_list = market.objects.all()
    industry_list = industry.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        stock_code = request.POST.get('stock_code')
        stock_name = request.POST.get('stock_name')
        industry_id = request.POST.get('industry_id')
        market_id = request.POST.get('market_id')
        stock_object = stock.objects.get(id=id)
        try:
            stock_object.stock_code = stock_code
            stock_object.stock_name = stock_name
            stock_object.industry_id = industry_id
            stock_object.market_id = market_id
            stock_object.save()
        except Exception as e:
            error_info = '输入股票代码重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_stock.html', locals())
        finally:
            pass
        return redirect('/benben/list_stock/')
    else:
        stock_object = stock.objects.get(id=stock_id)
        return render(request, templates_path + 'backstage/edit_stock.html', locals())


def list_stock(request):
    stock_list = stock.objects.all()
    return render(request,  templates_path + 'backstage/list_stock.html', locals())


# 持仓表增删改查
def add_position(request):
    account_list = account.objects.all()
    stock_list = stock.objects.all().order_by('stock_code')
    position_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        position_quantity = request.POST.get('position_quantity')
        position_currency = request.POST.get('position_currency')
        if stock_id.strip() == '':
            error_info = '股票不能为空！'
            return render(request, templates_path + 'backstage/add_position.html', locals())
        try:
            p = position.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                position_quantity=position_quantity,
                position_currency=position_currency
            )
            return redirect('/benben/list_position/')
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/add_position.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_position.html', locals())


def del_position(request, position_id):
    position_object = position.objects.get(id=position_id)
    position_object.delete()
    return redirect('/benben/list_position/')


def edit_position(request, position_id):
    position_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_list = account.objects.all()
    stock_list = stock.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        position_quantity = request.POST.get('position_quantity')
        position_currency = request.POST.get('position_currency')
        position_object = position.objects.get(id=id)
        try:
            position_object.account_id = account_id
            position_object.stock_id = stock_id
            position_object.position_quantity = position_quantity
            position_object.position_currency = position_currency
            position_object.save()
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/edit_position.html', locals())
        finally:
            pass
        return redirect('/benben/list_position/')
    else:
        position_object = position.objects.get(id=position_id)
        return render(request, templates_path + 'backstage/edit_position.html', locals())


def list_position(request):
    position_list = position.objects.all()
    return render(request,  templates_path + 'backstage/list_position.html', locals())

def add_historical_position(request):
    return render(request, templates_path + 'backstage/add_historical_position.html', locals())

def del_historical_position(request, historical_position_id):
    return redirect('/benben/list_historical_position/')

def edit_historical_position(request, historical_position_id):
    return render(request, templates_path + 'backstage/edit_historical_position.html', locals())

def list_historical_position(request):
    # historical_position_list = historical_position.objects.filter(date='2025-02-27')
    historical_position_list = historical_position.objects.all()
    return render(request,  templates_path + 'backstage/list_historical_position.html', locals())

# 交易表增删改查
def add_trade(request):
    trade_type_items = (
        (1, '买'),
        (2, '卖'),
    )
    settlement_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_list = account.objects.all()
    stock_list = stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        trade_date = request.POST.get('trade_date')
        trade_type = request.POST.get('trade_type')
        trade_price = request.POST.get('trade_price')
        trade_quantity = request.POST.get('trade_quantity')
        settlement_currency = request.POST.get('settlement_currency')
        if stock_id.strip() == '':
            error_info = "股票不能为空！"
            return render(request, templates_path + 'backstage/add_trade.html', locals())
        try:
            p = trade.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                trade_date=trade_date,
                trade_type=trade_type,
                trade_price=trade_price,
                trade_quantity=trade_quantity,
                settlement_currency=settlement_currency,
                filed_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            return redirect('/benben/list_trade/')
        except Exception as e:
            # print(str(e))
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/add_trade.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_trade.html', locals())


def del_trade(request, trade_id):
    trade_object = trade.objects.get(id=trade_id)
    trade_object.delete()
    return redirect('/benben/list_trade/')


def edit_trade(request, trade_id):
    trade_type_items = (
        (1, '买'),
        (2, '卖'),
    )
    settlement_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_list = account.objects.all()
    stock_list = stock.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        trade_date = request.POST.get('trade_date')
        trade_type = request.POST.get('trade_type')
        trade_price = request.POST.get('trade_price')
        trade_quantity = request.POST.get('trade_quantity')
        settlement_currency = request.POST.get('settlement_currency')
        trade_object = trade.objects.get(id=id)
        try:
            trade_object.account_id = account_id
            trade_object.stock_id = stock_id
            trade_object.trade_date = trade_date
            trade_object.trade_type = trade_type
            trade_object.trade_price = trade_price
            trade_object.trade_quantity = trade_quantity
            trade_object.settlement_currency = settlement_currency
            trade_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_trade.html', locals())
        finally:
            pass
        return redirect('/benben/list_trade/')
    else:
        trade_object = trade.objects.get(id=trade_id)
        return render(request, templates_path + 'backstage/edit_trade.html', locals())


def list_trade(request):
    trade_list = trade.objects.all().order_by('-trade_date', '-modified_time')
    return render(request, templates_path + 'backstage/list_trade.html', locals())


# 分红表增删改查
def add_dividend(request):
    dividend_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_list = account.objects.all()
    stock_list = stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        dividend_date = request.POST.get('dividend_date')
        dividend_amount = request.POST.get('dividend_amount')
        dividend_currency = request.POST.get('dividend_currency')
        if stock_id.strip() == '':
            error_info = '股票不能为空！'
            return render(request, templates_path + 'backstage/add_dividend.html', locals())
        try:
            p = dividend.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                dividend_date=dividend_date,
                dividend_amount=dividend_amount,
                dividend_currency=dividend_currency
            )
            return redirect('/benben/list_dividend/')
        except Exception as e:
            error_info = '输入信息有误！'
            return render(request, templates_path + 'backstage/add_dividend.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_dividend.html', locals())


def del_dividend(request, dividend_id):
    dividend_object = dividend.objects.get(id=dividend_id)
    dividend_object.delete()
    return redirect('/benben/list_dividend/')


def edit_dividend(request, dividend_id):
    dividend_currency_items = (
        (1, '人民币'),
        (2, '港元'),
        (3, '美元'),
    )
    account_list = account.objects.all()
    stock_list = stock.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        dividend_date = request.POST.get('dividend_date')
        dividend_amount = request.POST.get('dividend_amount')
        dividend_currency = request.POST.get('dividend_currency')
        dividend_object = dividend.objects.get(id=id)
        try:
            dividend_object.account_id = account_id
            dividend_object.stock_id = stock_id
            dividend_object.dividend_date = dividend_date
            dividend_object.dividend_amount = dividend_amount
            dividend_object.dividend_currency = dividend_currency
            dividend_object.save()
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/edit_dividend.html', locals())
        finally:
            pass
        return redirect('/benben/list_dividend/')
    else:
        dividend_object = dividend.objects.get(id=dividend_id)
        return render(request, templates_path + 'backstage/edit_dividend.html', locals())


def list_dividend(request):
    dividend_list = dividend.objects.all().order_by('-dividend_date', '-modified_time')
    return render(request,  templates_path + 'backstage/list_dividend.html', locals())


# 打新表增删改查
def add_subscription(request):
    subscription_type_items = (
        (1, '股票'),
        (2, '可转债'),
    )
    account_list = account.objects.all()
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        subscription_name = request.POST.get('subscription_name')
        subscription_date = request.POST.get('subscription_date')
        subscription_type = request.POST.get('subscription_type')
        subscription_quantity = request.POST.get('subscription_quantity')
        buying_price = request.POST.get('buying_price')
        selling_price = request.POST.get('selling_price')
        if account_id.strip() == '':
            error_info = '证券账户不能为空！'
            return render(request, templates_path + 'backstage/add_subscription.html', locals())
        try:
            p = subscription.objects.create(
                account_id=account_id,
                subscription_name=subscription_name,
                subscription_date=subscription_date,
                subscription_type=subscription_type,
                subscription_quantity=subscription_quantity,
                buying_price=buying_price,
                selling_price=selling_price
            )
            return redirect('/benben/list_subscription/')
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/add_subscription.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_subscription.html', locals())


def del_subscription(request, subscription_id):
    subscription_object = subscription.objects.get(id=subscription_id)
    subscription_object.delete()
    return redirect('/benben/list_subscription/')


def edit_subscription(request, subscription_id):
    subscription_type_items = (
        (1, '股票'),
        (2, '可转债'),
    )
    account_list = account.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        subscription_name = request.POST.get('subscription_name')
        subscription_date = request.POST.get('subscription_date')
        subscription_type = request.POST.get('subscription_type')
        subscription_quantity = request.POST.get('subscription_quantity')
        buying_price = request.POST.get('buying_price')
        selling_price = request.POST.get('selling_price')
        subscription_object = subscription.objects.get(id=id)
        try:
            subscription_object.account_id = account_id
            subscription_object.subscription_name = subscription_name
            subscription_object.subscription_date = subscription_date
            subscription_object.subscription_type = subscription_type
            subscription_object.subscription_quantity = subscription_quantity
            subscription_object.buying_price = buying_price
            subscription_object.selling_price = selling_price
            subscription_object.save()
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/edit_subscription.html', locals())
        finally:
            pass
        return redirect('/benben/list_subscription/')
    else:
        subscription_object = subscription.objects.get(id=subscription_id)
        return render(request, templates_path + 'backstage/edit_subscription.html', locals())


def list_subscription(request):
    subscription_list = subscription.objects.all().order_by('-subscription_date', '-modified_time')
    return render(request,  templates_path + 'backstage/list_subscription.html', locals())


# 分红历史表增删改查
def add_dividend_history(request):
    stock_list = stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        stock_id = request.POST.get('stock_id')
        reporting_period = request.POST.get('reporting_period')
        dividend_plan = request.POST.get('dividend_plan')
        announcement_date = request.POST.get('announcement_date')
        registration_date = request.POST.get('registration_date')
        ex_right_date = request.POST.get('ex_right_date')
        dividend_date = request.POST.get('dividend_date')
        if stock_id.strip() == '':
            error_info = "股票不能为空！"
            return render(request, templates_path + 'backstage/add_dividend_history.html', locals())
        try:
            p = dividend_history.objects.create(
                stock_id=stock_id,
                reporting_period=reporting_period,
                dividend_plan=dividend_plan,
                announcement_date=announcement_date,
                registration_date=registration_date,
                ex_right_date=ex_right_date,
                dividend_date=dividend_date
            )
            return redirect('/benben/list_dividend_history/')
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/add_dividend_history.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_dividend_history.html', locals())


def del_dividend_history(request, dividend_history_id):
    dividend_history_object = dividend_history.objects.get(id=dividend_history_id)
    dividend_history_object.delete()
    return redirect('/benben/list_dividend_history/')


def edit_dividend_history(request, dividend_history_id):
    stock_list = stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        id = request.POST.get('id')
        stock_id = request.POST.get('stock_id')
        reporting_period = request.POST.get('reporting_period')
        dividend_plan = request.POST.get('dividend_plan')
        announcement_date = request.POST.get('announcement_date')
        registration_date = request.POST.get('registration_date')
        ex_right_date = request.POST.get('ex_right_date')
        dividend_date = request.POST.get('dividend_date')
        dividend_history_object = dividend_history.objects.get(id=id)
        try:
            dividend_history_object.stock_id = stock_id
            dividend_history_object.reporting_period = reporting_period
            dividend_history_object.dividend_plan = dividend_plan
            dividend_history_object.announcement_date = announcement_date
            dividend_history_object.registration_date = registration_date
            dividend_history_object.ex_right_date = ex_right_date
            dividend_history_object.dividend_date = dividend_date
            dividend_history_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_dividend_history.html', locals())
        finally:
            pass
        return redirect('/benben/list_dividend_history/')
    else:
        dividend_history_object = dividend_history.objects.get(id=dividend_history_id)
        return render(request, templates_path + 'backstage/edit_dividend_history.html', locals())


def list_dividend_history(request):
    dividend_history_list = dividend_history.objects.all()
    return render(request,  templates_path + 'backstage/list_dividend_history.html', locals())


# 基金表增删改查
def add_funds(request):
    if request.method == 'POST':
        funds_name = request.POST.get('funds_name')
        funds_create_date = request.POST.get('funds_create_date')
        funds_value = request.POST.get('funds_value')
        funds_principal = request.POST.get('funds_principal')
        funds_PHR = request.POST.get('funds_PHR')
        funds_net_value = request.POST.get('funds_net_value')
        funds_baseline = request.POST.get('funds_baseline')
        funds_script = request.POST.get('funds_script')
        if funds_name.strip() == '':
            error_info = "基金名称不能为空！"
            return render(request, templates_path + 'backstage/add_funds.html', locals())
        try:
            p = funds.objects.create(
                funds_name=funds_name,
                funds_create_date=funds_create_date,
                funds_value=funds_value,
                funds_principal=funds_principal,
                funds_PHR=funds_PHR,
                funds_net_value=funds_net_value,
                funds_baseline=funds_baseline,
                funds_script=funds_script
            )
            return redirect('/benben/list_funds/')
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/add_funds.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_funds.html', locals())


def del_funds(request, funds_id):
    funds_object = funds.objects.get(id=funds_id)
    funds_object.delete()
    return redirect('/benben/list_funds/')


def edit_funds(request, funds_id):
    if request.method == 'POST':
        id = request.POST.get('id')
        funds_name = request.POST.get('funds_name')
        funds_create_date = request.POST.get('funds_create_date')
        funds_value = request.POST.get('funds_value')
        funds_principal = request.POST.get('funds_principal')
        funds_PHR = request.POST.get('funds_PHR')
        funds_net_value = request.POST.get('funds_net_value')
        funds_baseline = request.POST.get('funds_baseline')
        funds_script = request.POST.get('funds_script')
        funds_object = funds.objects.get(id=id)
        try:
            funds_object.funds_name = funds_name
            funds_object.funds_create_date = funds_create_date
            funds_object.funds_value = funds_value
            funds_object.funds_principal = funds_principal
            funds_object.funds_PHR = funds_PHR
            funds_object.funds_net_value = funds_net_value
            funds_object.funds_baseline = funds_baseline
            funds_object.funds_script = funds_script
            funds_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_funds.html', locals())
        finally:
            pass
        return redirect('/benben/list_funds/')
    else:
        funds_object = funds.objects.get(id=funds_id)
        return render(request, templates_path + 'backstage/edit_funds.html', locals())


def list_funds(request):
    funds_list = funds.objects.all().order_by('id')
    return render(request,  templates_path + 'backstage/list_funds.html', locals())


# 基金明细表增删改查
def add_funds_details(request, funds_id):
    funds_list = funds.objects.all()
    if request.method == 'POST':
        funds_id = request.POST.get('funds_id')
        date = datetime.datetime.strptime(request.POST.get('date'), "%Y-%m-%d").date()
        funds_value = request.POST.get('funds_value')
        funds_in_out = request.POST.get('funds_in_out')
        #funds_principal = request.POST.get('funds_principal')
        #funds_PHR = request.POST.get('funds_PHR')
        #funds_net_value = request.POST.get('funds_net_value')
        #funds_profit = request.POST.get('funds_profit')
        #funds_profit_rate = request.POST.get('funds_profit_rate')
        #funds_annualized_profit_rate = request.POST.get('funds_annualized_profit_rate')
        #print(funds_id,date,funds_value,funds_in_out)
        if funds_id.strip() == '':
            error_info = "基金名称不能为空！"
            return render(request, templates_path + 'backstage/add_funds_details.html', locals())
        try:
            funds_value = float(funds_value)
            funds_in_out = float(funds_in_out)
            latest_date = get_max_date(funds_id)
            earliest_date = get_min_date(funds_id)
            years = float((latest_date - earliest_date).days / 365)
            #print(latest_date,earliest_date,years)
            latest_funds_value = float(funds_details.objects.get(funds_id=funds_id, date = latest_date).funds_value)
            latest_funds_principal = float(funds_details.objects.get(funds_id=funds_id, date = latest_date).funds_principal)
            latest_funds_PHR = float(funds_details.objects.get(funds_id=funds_id, date = latest_date).funds_PHR)
            latest_funds_net_value = float(funds_details.objects.get(funds_id=funds_id, date = latest_date).funds_net_value)
            latest_funds_profit_rate = float(funds_details.objects.get(funds_id=funds_id, date = latest_date).funds_profit_rate)
            #print(latest_date,earliest_date,years,latest_funds_principal,latest_funds_PHR)

            funds_principal = latest_funds_principal + funds_in_out
            if latest_funds_PHR == 0: # 如果份数为0，则基金已经关闭，净值保持不变
                funds_net_value = latest_funds_net_value
            else:
                funds_net_value = (funds_value - funds_in_out) / latest_funds_PHR
            funds_PHR = funds_value / funds_net_value
            funds_current_profit = funds_value - funds_in_out - latest_funds_value
            funds_current_profit_rate = (funds_net_value - latest_funds_net_value) / latest_funds_net_value
            funds_profit = funds_value - funds_principal
            if latest_funds_PHR == 0: # 如果份数为0，则基金已经关闭，累计收益率保持不变
                funds_profit_rate = latest_funds_profit_rate
            else:
                funds_profit_rate = funds_profit / funds_principal

            #print(latest_date,earliest_date,years,latest_funds_principal,latest_funds_PHR,funds_principal,funds_net_value,funds_PHR,funds_profit,funds_profit_rate)
            #print(date, earliest_date)
            years = float((date - earliest_date).days / 365)
            #print(years)
            funds_annualized_profit_rate = funds_net_value ** (1 / years) - 1
            #print(funds_annualized_profit_rate)
            #funds_annualized_profit_rate = (funds_net_value ** (1 / float(((latest_date - earliest_date).days) / 365)) - 1) * 100
            #print(latest_date,earliest_date,years,latest_funds_principal,latest_funds_PHR,funds_principal,funds_net_value,funds_PHR,funds_profit,funds_profit_rate,funds_annualized_profit_rate)
            # 插入一条基金明细记录
            p = funds_details.objects.create(
                funds_id=funds_id,
                date=date,
                funds_value=funds_value,
                funds_in_out=funds_in_out,
                funds_principal=funds_principal,
                funds_PHR=funds_PHR,
                funds_net_value=funds_net_value,
                funds_current_profit=funds_current_profit,
                funds_current_profit_rate=funds_current_profit_rate,
                funds_profit=funds_profit,
                funds_profit_rate=funds_profit_rate,
                funds_annualized_profit_rate=funds_annualized_profit_rate
            )

            # 更新一条基金记录
            funds_object = funds.objects.get(id=funds_id)
            funds_object.funds_value = funds_value
            funds_object.funds_principal = funds_principal
            funds_object.funds_PHR = funds_PHR
            funds_object.funds_net_value = funds_net_value
            funds_object.update_date = date
            funds_object.save()

            return redirect('/benben/list_funds_details/')
        except Exception as e:
            error_info = "输入信息有错误！"
            print(latest_date, earliest_date, latest_funds_principal, latest_funds_PHR, funds_principal,funds_net_value, funds_PHR, funds_profit, funds_profit_rate, funds_annualized_profit_rate)
            return render(request, templates_path + 'backstage/add_funds_details.html', locals())
        finally:
            pass
    else:
        if funds_id != 0:
            funds_object = funds.objects.get(id=funds_id)
        else:
            funds_object = funds.objects.all()
    return render(request, templates_path + 'backstage/add_funds_details.html', locals())


def del_funds_details(request, funds_details_id):
    funds_details_object = funds_details.objects.get(id=funds_details_id)
    funds_details_object.delete()
    return redirect('/benben/list_funds_details/')


def edit_funds_details(request, funds_details_id):
    funds_list = funds.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        date = request.POST.get('date')
        funds_value = request.POST.get('funds_value')
        funds_in_out = request.POST.get('funds_in_out')
        funds_principal = request.POST.get('funds_principal')
        funds_PHR = request.POST.get('funds_PHR')
        funds_net_value = request.POST.get('funds_net_value')
        funds_profit = request.POST.get('funds_profit')
        funds_profit_rate = request.POST.get('funds_profit_rate')
        funds_annualized_profit_rate = request.POST.get('funds_annualized_profit_rate')
        funds_details_object = funds_details.objects.get(id=id)
        try:
            funds_details_object.date = date
            funds_details_object.funds_value = funds_value
            funds_details_object.funds_in_out = funds_in_out
            funds_details_object.funds_principal = funds_principal
            funds_details_object.funds_PHR = funds_PHR
            funds_details_object.funds_net_value = funds_net_value
            funds_details_object.funds_profit = funds_profit
            funds_details_object.funds_profit_rate = funds_profit_rate
            funds_details_object.funds_annualized_profit_rate = funds_annualized_profit_rate
            funds_details_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_funds_details.html', locals())
        finally:
            pass
        return redirect('/benben/list_funds_details/')
    else:
        funds_details_object = funds_details.objects.get(id=funds_details_id)
        return render(request, templates_path + 'backstage/edit_funds_details.html', locals())


def list_funds_details(request):
    funds_details_list = funds_details.objects.all()
    return render(request,  templates_path + 'backstage/list_funds_details.html', locals())


# 从网站中抓取数据导入数据库
def capture_dividend_history(request):
    stock_list = stock.objects.all().values('stock_code', 'stock_name').order_by('stock_code')
    holding_stock_list = position.objects.values("stock").annotate(count=Count("stock")).values('stock__stock_code')
    if request.method == 'POST':
        stock_code_list = []
        stock_code_POST = request.POST.get('stock_code')
        # print(tab_name, stock_code_POST)
        if stock_code_POST == '全部':
            for rs in stock_list:
                stock_code_list.append(rs['stock_code'])
        elif stock_code_POST == '持仓股票':
            for rs in holding_stock_list:
                stock_code_list.append(rs['stock__stock_code'])
        else:
            stock_code_list.append(stock_code_POST)
        # print("stock_code_list=", stock_code_list)
        for stock_code in stock_code_list:
            stock_object = stock.objects.get(stock_code=stock_code)
            stock_id = stock_object.id
            stock_dividend_dict = get_stock_dividend_history(stock_code)
            next_dividend_date, last_dividend_date = get_dividend_date(stock_dividend_dict)
            count = 0
            try:
                # 删除dividend_history表中的相关记录
                # dividend_history_object = dividend_history.objects.get(stock_id = stock_id)
                dividend_history.objects.filter(stock_id=stock_id).delete()

                # 在dividend_history表中增加相关记录
                for i in stock_dividend_dict:
                    # print(stock_code, i['dividend_plan'], i['dividend_date'])
                    # 若日期字段的值为‘’或‘None’，则将该字段的值赋为 None，以防止插入数据库时报错
                    if i['announcement_date'] == '' or i['announcement_date'] == 'None':
                        i['announcement_date'] = None
                    if i['registration_date'] == '' or i['registration_date'] == 'None':
                        i['registration_date'] = None
                    if i['ex_right_date'] == '' or i['ex_right_date'] == 'None':
                        i['ex_right_date'] = None
                    if i['dividend_date'] == '' or i['dividend_date'] == 'None':
                        i['dividend_date'] = None
                    p = dividend_history.objects.create(
                        stock_id=stock_id,
                        reporting_period=i['reporting_period'],
                        dividend_plan=i['dividend_plan'],
                        announcement_date=i['announcement_date'],
                        registration_date=i['registration_date'],
                        ex_right_date=i['ex_right_date'],
                        dividend_date=i['dividend_date']
                    )
                    count += 1

                # 更新stock表相关记录的next_dividend_date和last_dividend_date字段
                # stock_object.update(next_dividend_date=next_dividend_date, last_dividend_date=last_dividend_date)
                stock_object.next_dividend_date = next_dividend_date
                stock_object.last_dividend_date = last_dividend_date
                stock_object.dividend_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                stock_object.save()

            except Exception as e:
                print('插入第' + str(count) + '条记录失败！')
                print('错误明细是', e.__class__.__name__, e)
            print('插入' + '股票（' + stock_code + '）的历史分红记录' + str(count) + '条！')

    return render(request, templates_path + 'capture/capture_dividend_history.html', locals())


# 从excel表读取数据导入数据库
def batch_import(request):
    funds_list = funds.objects.all()
    if request.method == 'POST':
        form_name = request.POST.get('form_name')
        if form_name == '交易':
            account_abbreviation = request.POST.get('account_abbreviation')
            if not account_abbreviation is None:
                print(form_name, account_abbreviation)
                # count = excel2trade('D:/gp/GP_操作.xlsm', account_abbreviation, -1, -1)
                # messages.success(request, account_abbreviation + "成功插入" + str(count) + "条记录！")
        elif form_name == '打新':
            subscription_type = request.POST.get('subscription_type')
            print(form_name, subscription_type)
            # excel2subscription('D:/gp/GP_操作.xlsm', '新股', -1, -1)
            # excel2subscription('D:/gp/GP_操作.xlsm', '新债', -1, -1)
        elif form_name == '分红':
            account_type = request.POST.get('account_type')
            print(form_name, account_type)
            # excel2dividend('D:/gp/GP_操作.xlsm', '分红', -1, -1)
        elif form_name == '基金明细':
            funds_id = request.POST.get('funds_id')
            funds_name = funds.objects.get(id=funds_id).funds_name
            file_name = 'c:/gp/GP（' + funds_name + '）.xls'
            excel2funds(file_name, funds_name, -1, -1)
            print(form_name, funds_id, funds_name)
        else:
            pass
    return render(request, templates_path + 'other/batch_import.html', locals())  # 这里用'/'，‘//’或者‘/’代替'\'，防止'\b'被转义





# 更新历史持仓市值数据（historical_position、historical_rate、historical_market_value表）

# 全局变量，用于存储任务状态
task_status = {
    "current_step": 0,
    "total_steps": 7,
    "status": "idle",
    "message": "",
    "start_time": None,
    "end_time": None
}

def update_historical_market_value(request):
    global task_status
    task_status = {
        "current_step": 0,
        "total_steps": 7,
        "status": "running",
        "message": "任务开始执行",
        "start_time": timezone.now(),
        "end_time": None
    }

    # 获取初始日期范围
    result = historical_position.objects.aggregate(max_date=Max('date'))
    start_date = result['max_date'] - datetime.timedelta(days=1)
    end_date = datetime.date.today()

    # 任务步骤列表
    steps = [
        ("生成历史持仓", generate_historical_positions, (start_date, end_date)),
        ("获取历史收盘价", get_historical_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
        ("获取今日价格", get_today_price, ()),
        ("获取历史汇率", get_historical_rate, (start_date, end_date)),
        ("填充缺失的历史汇率", fill_missing_historical_rates, ()),
        ("计算市场价值", calculate_market_value, (start_date, end_date)),
        ("计算并填充历史数据", calculate_and_fill_historical_data, (start_date, end_date))
    ]

    for step_name, func, args in steps:
        task_status["current_step"] += 1
        task_status["message"] = f"正在执行: {step_name}"
        # 模拟任务执行时间
        time.sleep(1)
        func(*args)  # 执行任务步骤

    task_status["status"] = "completed"
    task_status["message"] = "任务执行完成"
    task_status["end_time"] = timezone.now()

    return render(request, templates_path + 'other/update_historical_market_value.html')

def get_task_status(request):
    global task_status
    # 计算耗时
    duration = None
    if task_status["status"] == "completed" and task_status["end_time"] and task_status["start_time"]:
        duration = (task_status["end_time"] - task_status["start_time"]).total_seconds()

    return JsonResponse({
        "current_step": task_status["current_step"],
        "total_steps": task_status["total_steps"],
        "status": task_status["status"],
        "message": task_status["message"],
        "duration": duration
    })



# 正向遍历trade表生成historical_position表
def generate_historical_positions(start_date, end_date):
    """
    生成历史持仓记录（支持从已有持仓初始化）

    参数：
    start_date : datetime.date - 开始日期（包含）
    end_date : datetime.date - 结束日期（包含）

    返回：
    int - 新生成的记录数量
    """
    while start_date.weekday() >= 5:
        start_date -= datetime.timedelta(days=1)
    with transaction.atomic():
        # 初始化持仓缓存 {(stock_id, currency): quantity}
        position_cache = defaultdict(int)
        process_start = start_date
        date_sequence = []

        # 1. 检查并加载初始持仓
        initial_positions = historical_position.objects.filter(date=start_date)
        if initial_positions.exists():
            # 加载初始持仓（过滤零持仓）
            for pos in initial_positions.exclude(quantity=0):
                key = (pos.stock_id, pos.currency)
                position_cache[key] = pos.quantity

            # 调整处理起始日期为次日
            process_start = start_date + datetime.timedelta(days=1)
            print(f"[INFO] 使用 {start_date} 已有持仓作为初始状态，从 {process_start} 开始处理")
        else:
            print(f"[INFO] 无初始持仓，从 {start_date} 开始生成")

        # 2. 生成有效日期序列（跳过周末）
        current_date = process_start
        while current_date <= end_date:
            if current_date.weekday() < 5:  # 0-4为工作日
                date_sequence.append(current_date)
            current_date += datetime.timedelta(days=1)

        # 3. 获取需要处理的交易数据（排除已初始化的日期）
        relevant_trades = trade.objects.filter(
            trade_date__gte=process_start,
            trade_date__lte=end_date
        ).order_by('trade_date').values(
            'trade_date', 'stock_id',
            'settlement_currency', 'trade_type',
            'trade_quantity'
        )

        # 4. 按日期处理交易生成持仓
        new_positions = []
        for processing_date in date_sequence:
            # 当日交易分组汇总
            daily_trades = defaultdict(lambda: {'buy': 0, 'sell': 0})
            for t in relevant_trades:
                if t['trade_date'] == processing_date:
                    key = (t['stock_id'], t['settlement_currency'])
                    if t['trade_type'] == trade.BUY:
                        daily_trades[key]['buy'] += t['trade_quantity']
                    else:
                        daily_trades[key]['sell'] += t['trade_quantity']

            # 计算当日持仓变化
            temp_cache = defaultdict(int)
            temp_cache.update(position_cache)  # 继承前一日持仓

            # 处理每个股票+货币组合
            for (stock_id, currency), amounts in daily_trades.items():
                net_change = amounts['buy'] - amounts['sell']
                new_quantity = temp_cache[(stock_id, currency)] + net_change

                if new_quantity != 0:
                    temp_cache[(stock_id, currency)] = new_quantity
                else:
                    # 清除零持仓
                    del temp_cache[(stock_id, currency)]

            # 更新持仓缓存
            position_cache = temp_cache

            # 生成当日记录（过滤零持仓）
            for (stock_id, currency), quantity in position_cache.items():
                new_positions.append(historical_position(
                    date=processing_date,
                    stock_id=stock_id,
                    currency=currency,
                    quantity=quantity,
                    created_time=timezone.now(),
                    modified_time=timezone.now()
                ))

        # 5. 清理旧数据并保存新记录
        if date_sequence:
            # 删除可能存在的旧记录
            historical_position.objects.filter(
                date__gte=process_start,
                date__lte=end_date
            ).delete()

            # 批量插入新记录
            historical_position.objects.bulk_create(new_positions)
            print(f"[SUCCESS] 生成 {len(new_positions)} 条记录（{process_start} 至 {end_date}）")
            return len(new_positions)

        print("[INFO] 没有需要处理的日期范围")
        return 0

# 从akshare获取股票历史收盘价
def get_historical_closing_price(start_date, end_date):
    # while end_date.weekday() >= 5:
    #     end_date -= datetime.timedelta(days=1)

    # start_date_str = (start_date - datetime.timedelta(days=10)).strftime("%Y%m%d") if start_date else ""
    start_date_str = start_date.strftime("%Y%m%d") if start_date else ""
    end_date_str = end_date.strftime("%Y%m%d") if end_date else ""
    date_list = list(historical_position.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).values_list('date', flat=True).distinct())
    # 获取stock字段的去重值列表
    stock_list = list(historical_position.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).values_list('stock', flat=True).distinct())
    for i in stock_list:
        stock_code = stock.objects.get(id=i).stock_code
        market_name = stock.objects.get(id=i).market.market_name
        market_abbreviation = stock.objects.get(id=i).market.market_abbreviation
        price_dict = {}
        if market_name == '港股':
            stock_code_str = stock_code
            #df = ak.stock_hk_daily(symbol=stock_code_str, adjust="")
            df = ak.stock_hk_hist(symbol=stock_code_str, period="daily", start_date=start_date_str, end_date=end_date_str, adjust="")
            df['日期'] = pd.to_datetime(df['日期'])
            current_date = pd.to_datetime(start_date)
            # while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
            while (not (current_date in df['日期'].values)) and (current_date > pd.to_datetime(start_date)):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['日期'].values:
                current_price = float(df[df['日期'] == current_date]['收盘'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['日期'].values
                if date_exists:
                    current_price = float(df[df['日期'] == item_datetime]['收盘'].iloc[0])
                price_dict[item] = current_price
        else:
            if market_name == '沪市B股' or market_name == '深市B股':
                stock_code_str = market_abbreviation + stock_code
                df = ak.stock_zh_b_daily(symbol=stock_code_str, start_date=start_date_str, end_date=end_date_str, adjust="")
            elif classify_stock_code(stock_code) == 'ETF':
                stock_code_str = market_abbreviation + stock_code
                df = ak.stock_zh_index_daily(symbol=stock_code_str)
            elif classify_stock_code(stock_code) == '企业债':
                stock_code_str = market_abbreviation + stock_code
                df = ak.bond_zh_hs_daily(symbol=stock_code_str)
            else:
                stock_code_str = market_abbreviation + stock_code
                df = ak.stock_zh_a_daily(symbol=stock_code_str, start_date=start_date_str, end_date=end_date_str, adjust="")
            df['date'] = pd.to_datetime(df['date'])
            current_date = pd.to_datetime(start_date)
            # while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
            while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date)):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['date'].values:
                current_price = float(df[df['date'] == current_date]['close'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['date'].values
                if date_exists:
                    current_price = float(df[df['date'] == item_datetime]['close'].iloc[0])
                price_dict[item] = current_price

        update_closing_prices(stock_code, price_dict)
    return

def get_today_price():
    current_date = datetime.date.today()
    while current_date.weekday() >= 5:
        current_date -= datetime.timedelta(days=1)
    # 获取stock字段的去重值列表
    stock_list = list(historical_position.objects.filter(date=current_date).values_list('stock', flat=True).distinct())
    for i in stock_list:
        stock_code = stock.objects.get(id=i).stock_code
        price_dict = {}
        current_price, increase, color = get_quote_snowball(stock_code)
        price_dict[current_date] = current_price
        update_today_prices(current_date, stock_code, price_dict)
    return

def update_closing_prices(stock_code, price_dict):
    # 转换为日期索引的字典
    #price_dict = {item['date']: item['price'] for item in price_list}

    # 筛选需要更新的记录
    dates = price_dict.keys()
    records = historical_position.objects.filter(date__in=dates, stock__stock_code=stock_code)

    # 批量赋值并更新
    for record in records:
        record.closing_price = price_dict[record.date]

    try:
        with transaction.atomic():
            historical_position.objects.bulk_update(records, ['closing_price'])
            print(stock_code)
            print("历史收盘价格更新成功！")
    except Exception as e:
        print(stock_code)
        print(f"历史收盘价格更新失败: {str(e)}")

def update_today_prices(current_date, stock_code, price_dict):
    # 筛选需要更新的记录
    #dates = price_dict.keys()
    #current_date = datetime.date.today()

    records = historical_position.objects.filter(date=current_date, stock__stock_code=stock_code)

    # 批量赋值并更新
    for record in records:
        record.closing_price = price_dict[record.date]

    try:
        with transaction.atomic():
            historical_position.objects.bulk_update(records, ['closing_price'])
            print(stock_code)
            print("当日价格更新成功！")
    except Exception as e:
        print(stock_code)
        print(f"当日价格更新失败: {str(e)}")

# 从akshare获取历史汇率
def get_historical_rate(start_date, end_date):
    # 查询日期范围
    # result = historical_position.objects.aggregate(
    #     min_date=Min('date'),  # 最小值（最早日期）
    #     max_date=Max('date')  # 最大值（最新日期）
    # )
    # start_date = result['min_date']
    # end_date = result['max_date']
    # 转换为 "YYYYMMDD" 格式字符串
    start_date_str = start_date.strftime("%Y%m%d") if start_date else ""
    end_date_str = end_date.strftime("%Y%m%d") if end_date else ""
    try:
        df = ak.currency_boc_sina(symbol="港币", start_date=start_date_str, end_date=end_date_str)
        df['日期'] = pd.to_datetime(df['日期'])
        df_hkd = df.loc[:, ['日期', '中行汇买价']]
        df = ak.currency_boc_sina(symbol="美元", start_date=start_date_str, end_date=end_date_str)
        df['日期'] = pd.to_datetime(df['日期'])
        df_usd = df.loc[:, ['日期', '中行汇买价']]
    except Exception as e:
        print(f"查询报错: {e}")

    # 示例调用（带异常处理）
    try:
        update_historical_rate(df_hkd, "港元", start_date, end_date)
        print("历史汇率（港元）写入成功！")
        update_historical_rate(df_usd, "美元", start_date, end_date)
        print("历史汇率（美元）写入成功！")
    except Exception as e:
        print(f"历史汇率写入失败: {str(e)}")


    return

def update_historical_rate(df: pd.DataFrame, currency_name: str, start_date, end_date) -> None:
    """
    先删除表中该货币的旧数据，再批量写入新数据
    :param df: 输入 DataFrame，需包含 '日期' 和 '中行汇买价' 列
    :param currency_name: 货币名称（如 "港元" 或 "美元"）
    """
    # 检查 DataFrame 列是否存在
    required_columns = ['日期', '中行汇买价']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"DataFrame 必须包含列: {required_columns}")

    # 转换日期列为 datetime.date 类型
    df['日期'] = pd.to_datetime(df['日期']).dt.date

    # 准备模型实例列表
    instances = [
        historical_rate(
            date=row['日期'],
            currency=currency_name,
            rate=row['中行汇买价']/100
        )
        for _, row in df.iterrows()
    ]
    # 原子操作：删除旧数据 + 插入新数据
    with transaction.atomic():
        # 删除该货币所有旧数据
        historical_rate.objects.filter(
                currency=currency_name,
                date__gte=start_date,
                date__lte=end_date
            ).delete()
        # 批量写入新数据
        historical_rate.objects.bulk_create(instances)

# 补充akshare数据中缺失的日期
def fill_missing_historical_rates():
    """
    自动补全historical_rate表中缺失的汇率记录
    返回补全记录数量和错误信息列表
    """
    # 货币代码映射（根据historical_position定义）
    CURRENCY_MAPPING = {
        1: "人民币",
        2: "港元",
        3: "美元"
    }

    # 获取需要补全的日期和货币组合
    positions = historical_position.objects.values('date', 'currency').distinct()

    # 转换货币代码为字符串格式
    required_combinations = [
        (pos['date'], CURRENCY_MAPPING[pos['currency']])
        for pos in positions
        if pos['currency'] in CURRENCY_MAPPING
    ]

    # 获取已存在的汇率记录
    existing_rates = historical_rate.objects.filter(
        Q(date__in=[d for d, _ in required_combinations]) &
        Q(currency__in=[c for _, c in required_combinations])
    ).values_list('date', 'currency')

    existing_set = set(existing_rates)

    # 确定需要补全的组合
    missing_combinations = [
        (date, currency)
        for date, currency in required_combinations
        if (date, currency) not in existing_set
    ]

    # 按货币分组处理
    currency_date_map = defaultdict(list)
    for date, currency in missing_combinations:
        currency_date_map[currency].append(date)

    # 补全记录存储
    new_rates = []
    errors = []

    # 为每个货币处理缺失日期
    for currency, dates in currency_date_map.items():
        # 获取该货币所有历史记录
        currency_rates = historical_rate.objects.filter(currency=currency) \
            .order_by('-date').values('date', 'rate')

        if not currency_rates:
            errors.append(f"货币 {currency} 没有历史汇率记录")
            continue

        # 转换为按日期索引的字典
        rate_dict = {r['date']: r['rate'] for r in currency_rates}
        sorted_dates = sorted(rate_dict.keys(), reverse=True)

        # 处理每个缺失日期
        for target_date in sorted(dates):
            found = False
            # 从目标日期前一天开始查找
            current_date = target_date - timezone.timedelta(days=1)

            # 最多向前查找30天防止无限循环
            for _ in range(30):
                if current_date in rate_dict:
                    new_rates.append(historical_rate(
                        date=target_date,
                        currency=currency,
                        rate=rate_dict[current_date],
                        modified_time=timezone.now()
                    ))
                    found = True
                    break
                # 没有则继续向前查找
                current_date -= timezone.timedelta(days=1)

            if not found:
                errors.append(f"货币 {currency} 在 {target_date} 前30天无可用汇率")

    # 批量插入新记录
    if new_rates:
        historical_rate.objects.bulk_create(new_rates)

    print(f"补全了 {len(new_rates)} 条记录")
    # if errors:
    #     print("发生错误：", "\n".join(errors))


# 计算历史持仓市值
def calculate_market_value(start_date, end_date):
    """
    生成历史市值数据并写入 historical_market_value 表
    步骤：
    1. 清空 historical_market_value 表
    2. 获取持仓数据的日期范围
    3. 预加载汇率数据到内存字典
    4. 按日期+货币计算市值总和
    5. 批量写入结果
    """
    try:
        # 使用原子事务保证数据一致性
        with transaction.atomic():
            # 1. 清空历史市值表
            historical_market_value.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).delete()

            # 2. 获取持仓日期范围
            # date_range = historical_position.objects.aggregate(
            #     min_date=Min('date'),
            #     max_date=Max('date')
            # )
            # min_date, max_date = date_range['min_date'], date_range['max_date']

            # 如果没有持仓数据直接返回
            # if not min_date or not max_date:
            #     return

            # 3. 预加载汇率数据（日期范围 + 货币）
            rate_records = historical_rate.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).values('date', 'currency', 'rate')

            # 构建 {(date, currency): rate} 的快速查询字典
            rate_dict = {
                (r['date'], r['currency']): r['rate']
                for r in rate_records
            }

            # 4. 获取所有持仓记录并按日期分组
            positions = historical_position.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).select_related('stock')  # 如果关联股票表需要字段可添加

            # 构建日期到持仓记录的映射
            date_positions = defaultdict(list)
            for pos in positions:
                date_positions[pos.date].append(pos)

            # 5. 准备货币类型映射字典（代码 -> 中文名）
            CURRENCY_MAP = {
                historical_position.CNY: '人民币',
                historical_position.HKD: '港元',
                historical_position.USD: '美元',
            }

            # 6. 计算每日市值
            market_values = []
            current_date = start_date
            while current_date <= end_date:

                # 获取当日所有持仓记录
                daily_positions = date_positions.get(current_date, [])

                # 按货币计算市值总和
                currency_totals = defaultdict(Decimal)
                for pos in daily_positions:
                    # 6.1 获取货币中文名称
                    currency_name = CURRENCY_MAP.get(pos.currency)
                    if not currency_name:
                        raise ValueError(f'无效货币代码: {pos.currency}')

                    # 6.2 获取汇率（人民币特殊处理）
                    # 如持仓货币为人民币且股票市场为港股，则为港股通持仓，需按港元汇率计算人民币市值
                    if currency_name == '人民币' and pos.stock.market.transaction_currency == 2:
                        exchange_rate = rate_dict.get((current_date, '港元'))
                        if exchange_rate is None:
                            raise ValueError(
                                f'缺失汇率数据: {current_date} {currency_name}'
                            )
                    else:
                        exchange_rate = Decimal(1)

                    # 6.3 计算单股票市值
                    stock_value = pos.quantity * pos.closing_price * exchange_rate
                    currency_totals[currency_name] += stock_value

                # 7. 生成该日期的所有货币记录
                for currency, total in currency_totals.items():
                    market_values.append(
                        historical_market_value(
                            date=current_date,
                            currency=currency,
                            value=total
                        )
                    )

                # 移至下一天
                current_date += datetime.timedelta(days=1)

            # 8. 批量写入数据库
            historical_market_value.objects.bulk_create(market_values)
        print("历史持仓市值写入成功！")
    except Exception as e:
        print(f"历史持仓市值写入失败: {e}")

# 补全变化值和变化率数据
def calculate_and_fill_historical_data(start_date, end_date):
    """
    增量数据计算函数，执行以下操作：
    1. 补全指定日期范围内所有货币的工作日记录
    2. 批量计算指定日期范围内记录的市值变化指标
    """
    with transaction.atomic():
        # ================== 阶段1：数据补全 ==================
        workdays = generate_workdays(start_date, end_date)

        # 获取所有货币种类（包括新增数据可能包含的新货币）
        currencies = historical_market_value.objects.values_list(
            'currency', flat=True
        ).distinct()

        # 逐货币补全数据
        for currency in currencies:
            # 获取该货币在指定范围内的现有日期
            existing_dates = set(
                historical_market_value.objects.filter(
                    currency=currency,
                    date__range=(start_date, end_date)
                ).values_list('date', flat=True)
            )

            # 计算缺失日期
            missing_dates = [day for day in workdays if day not in existing_dates]

            # 批量创建记录（新补全记录的初始值后续会更新）
            if missing_dates:
                historical_market_value.objects.bulk_create([
                    historical_market_value(
                        currency=currency,
                        date=day,
                        value=0,
                        prev_value=0,
                        change_amount=0,
                        change_rate=0
                    ) for day in missing_dates
                ], batch_size=1000)
                print(f"Currency:{currency} 补全{len(missing_dates)}条记录")

        # ================== 阶段2：指标计算 ==================
        # 关键修改：先注释前值再过滤日期范围
        queryset = historical_market_value.objects.annotate(
            prev_value_calc=Window(
                expression=Lag('value', 1),
                partition_by=[F('currency')],
                order_by=F('date').asc()
            )
        ).order_by('currency', 'date').filter(
            date__gte=start_date,
            date__lte=end_date
        )

        # 批量更新容器
        BATCH_SIZE = 1000
        update_buffer = []

        for obj in queryset:
            # 智能获取前日值逻辑
            if obj.prev_value_calc is None:  # 没有前日记录
                # 检查是否真的是首条记录
                has_previous = historical_market_value.objects.filter(
                    currency=obj.currency,
                    date__lt=obj.date
                ).exists()

                # prev_val = 0 if not has_previous else historical_market_value.objects.get(
                #     currency=obj.currency,
                #     date=obj.date - datetime.timedelta(days=1)
                # ).value

                prev_val = 0
                if has_previous:
                    current_date = obj.date
                    max_days_back = 7  # 可根据实际情况调整最大尝试天数
                    for _ in range(max_days_back):
                        current_date -= datetime.timedelta(days=1)
                        # 跳过周末
                        while current_date.weekday() >= 5:  # 5=周六,6=周日
                            current_date -= datetime.timedelta(days=1)
                        # 尝试获取记录
                        try:
                            prev_val = historical_market_value.objects.get(
                                currency=obj.currency,
                                date=current_date
                            ).value
                            break
                        except historical_market_value.DoesNotExist:
                            continue  # 继续向前查找
            else:
                prev_val = obj.prev_value_calc

            # 计算变化指标
            change_amount = obj.value - prev_val
            try:
                change_rate = (change_amount / prev_val) if prev_val != 0 else 0
            except ZeroDivisionError:
                change_rate = 0

            # 更新对象字段
            obj.prev_value = prev_val
            obj.change_amount = change_amount
            obj.change_rate = change_rate
            update_buffer.append(obj)

            # 批量提交
            if len(update_buffer) >= BATCH_SIZE:
                historical_market_value.objects.bulk_update(
                    update_buffer,
                    ['prev_value', 'change_amount', 'change_rate'],
                    batch_size=BATCH_SIZE
                )
                update_buffer = []

        # 提交剩余数据
        if update_buffer:
            historical_market_value.objects.bulk_update(
                update_buffer,
                ['prev_value', 'change_amount', 'change_rate'],
                batch_size=BATCH_SIZE
            )

    print(f"批量更新完成，本次处理{len(update_buffer)}条记录")


def generate_workdays(start_date, end_date):
    """
    生成指定日期范围内的工作日列表
    Args:
        start_date (date): 开始日期
        end_date (date): 结束日期
    Returns:
        list: 工作日日期对象列表
    """
    workdays = []
    current_day = start_date
    while current_day <= end_date:
        if current_day.weekday() < 5:  # 0-4对应周一到周五
            workdays.append(current_day)
        current_day += datetime.timedelta(days=1)
    return workdays



# 关于
def about(request):
    return render(request, templates_path + 'about.html', locals())


# 测试
def test(request):
    # get_akshare()

    df = ak.stock_hk_daily(symbol='00700', adjust="")
    print(df)
    stock_hk_hist_df = ak.stock_hk_hist(symbol="00700", period="daily", start_date="19700101", end_date="22220101",
                                        adjust="")
    print(stock_hk_hist_df)

    # price, increase, color = get_quote_akshare('00700')
    # print(price, increase, color)
    # price, increase, color = get_quote_akshare("511880")
    # print(price, increase, color)
    # price, increase, color = get_quote_akshare("200596")
    # print(price, increase, color)
    # price, increase, color = get_quote_akshare("600519")
    # print(price, increase, color)
    # price, increase, color = get_quote_akshare("000002")
    # print(price, increase, color)

    # echarts图表--净值曲线
    # data = []
    # funds_details_list = funds_details.objects.filter(funds=3).order_by("date")
    # for rs in funds_details_list:
    #     date = str(rs.date)
    #     value = float(rs.funds_net_value)
    #     data.append({
    #         "date": date,
    #         "value": value
    #     })
    # # print(data)

    # data = []
    # market_value_list = historical_market_value.objects.filter(currency='人民币').order_by("date")
    # for rs in market_value_list:
    #     date = str(rs.date)
    #     value = float(rs.value)
    #     data.append({
    #         "date": date,
    #         "value": value / 10000
    #     })

    # # 更新历史持仓市值数据（historical_position、historical_rate、historical_market_value表）
    # start_date = datetime.date(2007, 8, 15)

    # 获取初始日期范围
    # result = historical_position.objects.aggregate(max_date=Max('date'))
    # start_date = result['max_date'] - datetime.timedelta(days=6)
    # end_date = datetime.date.today() - datetime.timedelta(days=1)
    #
    # # 任务步骤列表
    # generate_historical_positions(start_date, datetime.date.today())
    # get_historical_closing_price(start_date, end_date)
    # get_today_price()
    # get_historical_rate(start_date, datetime.date.today())
    # fill_missing_historical_rates()
    # calculate_market_value(start_date, datetime.date.today())
    # calculate_and_fill_historical_data()





    return render(request, templates_path + 'test.html', locals())



# 用于在模板中用变量定位列表索引的值，支持列表组，访问方法：用{{ list|index:i|index:j }}访问list[i][j]的值
@register.filter
def get_index(mylist, i):
    return mylist[i]


# 反向遍历trade表更新historical_position表
def reverse_generate_positions(start_date, end_date):
    try:
        # Step 0: 删除现有历史数据
        # current_date = datetime.date.today()
        # # 确定有效结束日期（排除周末）
        # while current_date.weekday() >= 5:
        #     current_date -= datetime.timedelta(days=1)
        # end_date = current_date

        # 确定有效结束日期（排除周末）
        while end_date.weekday() >= 5:
            end_date -= datetime.timedelta(days=1)

        # 使用事务保证原子性
        with transaction.atomic():
            # 删除目标日期范围内的所有历史记录
            historical_position.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).delete()

        # Step 1: 汇总当前持仓数据
        positions = position.objects.values('stock', 'position_currency').annotate(total=Sum('position_quantity'))
        current_positions = {
            (pos['stock'], pos['position_currency']): pos['total']
            for pos in positions
            if pos['total'] != 0
        }

        # Step 2: 确定初始日期并调整到最近的周五（如果是周末）
        initial_date = end_date  # 使用已计算的end_date

        # Step 3: 写入初始持仓到historical_position表（如果非周末）
        if initial_date.weekday() < 5:
            with transaction.atomic():
                entries = [
                    historical_position(
                        date=initial_date,
                        stock_id=stock_id,
                        currency=currency,
                        quantity=qty
                    )
                    for (stock_id, currency), qty in current_positions.items()
                    if qty != 0
                ]
                historical_position.objects.bulk_create(entries)

        # Step 4: 反向生成历史持仓
        processing_date = initial_date - datetime.timedelta(days=1)
        while processing_date >= start_date:
            if processing_date.weekday() >= 5:
                processing_date -= datetime.timedelta(days=1)
                continue

            # 写入当天持仓（与后一天相同）
            with transaction.atomic():
                entries = [
                    historical_position(
                        date=processing_date,
                        stock_id=stock_id,
                        currency=currency,
                        quantity=qty
                    )
                    for (stock_id, currency), qty in current_positions.items()
                    if qty != 0
                ]
                historical_position.objects.bulk_create(entries)

            # 处理交易记录
            trades = trade.objects.filter(trade_date=processing_date)
            delta_dict = defaultdict(int)
            for t in trades:
                key = (t.stock_id, t.settlement_currency)
                delta = t.trade_quantity if t.trade_type == trade.BUY else -t.trade_quantity
                delta_dict[key] += delta

            # 计算前一日持仓
            prev_positions = {}
            # 处理现有持仓
            for (stock, currency), qty in current_positions.items():
                delta = delta_dict.get((stock, currency), 0)
                prev_qty = qty - delta
                if prev_qty != 0:
                    prev_positions[(stock, currency)] = prev_qty
            # 处理新增持仓
            for (stock, currency) in delta_dict:
                if (stock, currency) not in current_positions:
                    delta = delta_dict[(stock, currency)]
                    prev_qty = 0 - delta
                    if prev_qty != 0:
                        prev_positions[(stock, currency)] = prev_qty

            current_positions = prev_positions
            processing_date -= datetime.timedelta(days=1)
        print("历史持仓写入成功！")
    except ValueError as e:
        print(f"输入错误: {e}")
    except RuntimeError as e:
        print(f"处理失败: {e}")




def generate_historical_positions_111(start_date, end_date):
    """
    生成指定日期范围内的历史持仓记录
    :param start_date: 开始日期（date类型）
    :param end_date: 结束日期（date类型）
    :return: 生成记录数量
    """
    with transaction.atomic():
        # 初始化持仓缓存 { (stock_id, currency): quantity }
        position_cache = defaultdict(int)

        # 获取所有交易日数据（按日期升序）
        trades = trade.objects.filter(
            trade_date__gte=start_date,
            trade_date__lte=end_date
        ).order_by('trade_date').values(
            'trade_date', 'stock_id',
            'settlement_currency', 'trade_type',
            'trade_quantity'
        )

        # 预先生成所有工作日日期序列
        date_sequence = []
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:  # 0-4为周一到周五
                date_sequence.append(current_date)
            current_date += datetime.timedelta(days=1)

        # 按日期处理持仓
        new_positions = []
        for processing_date in date_sequence:
            # 获取当日交易数据（按股票和货币分组汇总）
            daily_trades = defaultdict(lambda: {'buy': 0, 'sell': 0})
            for t in trades:
                if t['trade_date'] == processing_date:
                    key = (t['stock_id'], t['settlement_currency'])
                    if t['trade_type'] == trade.BUY:
                        daily_trades[key]['buy'] += t['trade_quantity']
                    else:
                        daily_trades[key]['sell'] += t['trade_quantity']

            # 生成当日持仓
            temp_cache = position_cache.copy()
            for (stock_id, currency), amounts in daily_trades.items():
                net_change = amounts['buy'] - amounts['sell']
                new_quantity = temp_cache.get((stock_id, currency), 0) + net_change
                if new_quantity != 0:
                    temp_cache[(stock_id, currency)] = new_quantity
                else:
                    temp_cache.pop((stock_id, currency), None)

            # 判断是否需要更新持仓
            if daily_trades or processing_date == start_date:
                position_cache = temp_cache

                # 生成持仓记录
                for (stock_id, currency), quantity in position_cache.items():
                    new_positions.append(historical_position(
                        date=processing_date,
                        stock_id=stock_id,
                        quantity=quantity,
                        currency=currency,
                    ))

            # 无交易日继承前一日持仓
            else:
                # 仅生成记录，持仓缓存保持不变
                for (stock_id, currency), quantity in position_cache.items():
                    new_positions.append(historical_position(
                        date=processing_date,
                        stock_id=stock_id,
                        quantity=quantity,
                        currency=currency,
                    ))

        # 批量插入并过滤零持仓
        valid_records = [
            p for p in new_positions
            if p.quantity != 0
        ]
        historical_position.objects.bulk_create(valid_records)

        return len(valid_records)



def get_historical_closing_price_111(start_date, end_date):
    # 转换为 "YYYYMMDD" 格式字符串
    start_date_str = (start_date - datetime.timedelta(days=10)).strftime("%Y%m%d") if start_date else ""
    end_date_str = end_date.strftime("%Y%m%d") if end_date else ""
    date_list = list(historical_position.objects.values_list('date', flat=True).distinct())
    # 获取stock字段的去重值列表
    stock_list = list(historical_position.objects.values_list('stock', flat=True).distinct())
    for i in stock_list:
        stock_code = stock.objects.get(id=i).stock_code
        market_name = stock.objects.get(id=i).market.market_name
        market_abbreviation = stock.objects.get(id=i).market.market_abbreviation
        price_dict = {}
        if market_name == '港股':
            stock_code_str = stock_code
            # df = ak.stock_hk_hist(symbol=stock_code_str, period="daily", start_date=start_date_str, end_date=end_date_str, adjust="")
            df = ak.stock_hk_daily(symbol=stock_code_str, adjust="")
            df['date'] = pd.to_datetime(df['date'])
            current_date = pd.to_datetime(start_date)
            while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['date'].values:
                current_price = float(df[df['date'] == current_date]['close'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['date'].values
                if date_exists:
                    current_price = float(df[df['date'] == item_datetime]['close'].iloc[0])
                price_dict[item] = current_price
        elif market_name == '沪市B股' or market_name == '深市B股':
            stock_code_str = market_abbreviation + stock_code
            df = ak.stock_zh_b_daily(symbol=stock_code_str, start_date=start_date_str, end_date=end_date_str, adjust="")
            df['date'] = pd.to_datetime(df['date'])
            current_date = pd.to_datetime(start_date)
            while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['date'].values:
                current_price = float(df[df['date'] == current_date]['close'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['date'].values
                if date_exists:
                    current_price = float(df[df['date'] == item_datetime]['close'].iloc[0])
                price_dict[item] = current_price
        elif classify_stock_code(stock_code) == 'ETF':
            stock_code_str = market_abbreviation + stock_code
            df = ak.stock_zh_index_daily(symbol=stock_code_str)
            df['date'] = pd.to_datetime(df['date'])
            current_date = pd.to_datetime(start_date)
            while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['date'].values:
                current_price = float(df[df['date'] == current_date]['close'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['date'].values
                if date_exists:
                    current_price = float(df[df['date'] == item_datetime]['close'].iloc[0])
                price_dict[item] = current_price
        elif classify_stock_code(stock_code) == '企业债':
            stock_code_str = market_abbreviation + stock_code
            df = ak.bond_zh_hs_daily(symbol=stock_code_str)
            df['date'] = pd.to_datetime(df['date'])
            current_date = pd.to_datetime(start_date)
            while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['date'].values:
                current_price = float(df[df['date'] == current_date]['close'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['date'].values
                if date_exists:
                    current_price = float(df[df['date'] == item_datetime]['close'].iloc[0])
                price_dict[item] = current_price
        else:
            stock_code_str = market_abbreviation + stock_code
            df = ak.stock_zh_a_daily(symbol=stock_code_str, start_date=start_date_str, end_date=end_date_str, adjust="")
            df['date'] = pd.to_datetime(df['date'])
            current_date = pd.to_datetime(start_date)
            while (not (current_date in df['date'].values)) and (current_date > pd.to_datetime(start_date - datetime.timedelta(days=10))):
                current_date = current_date - datetime.timedelta(days=1)
            if current_date in df['date'].values:
                current_price = float(df[df['date'] == current_date]['close'].iloc[0])
            else:
                current_price = 0
            for item in date_list:
                item_datetime = pd.to_datetime(item)
                date_exists = item_datetime in df['date'].values
                if date_exists:
                    current_price = float(df[df['date'] == item_datetime]['close'].iloc[0])
                price_dict[item] = current_price

        update_closing_prices(stock_code, price_dict)

    return



def calculate_and_fill_historical_data_111(start_date, end_date):
    """
    全量数据计算函数，执行以下操作：
    1. 补全全表日期范围内所有货币的工作日记录
    2. 批量计算市值变化指标
    """
    with transaction.atomic():
        # ================== 阶段1：数据补全 ==================
        # 获取全表日期范围
        date_range = historical_market_value.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).aggregate(
            min_date=Min('date'),
            max_date=Max('date')
        )

        # 处理空表情况
        if not date_range['min_date'] or not date_range['max_date']:
            return

        # 生成全量工作日列表
        workdays = generate_workdays(date_range['min_date'], date_range['max_date'])

        # 获取所有货币种类
        currencies = historical_market_value.objects.values_list(
            'currency', flat=True
        ).distinct()

        # 逐货币补全数据
        for currency in currencies:
            # 获取该货币现有日期
            existing_dates = set(
                historical_market_value.objects.filter(currency=currency)
                    .values_list('date', flat=True)
            )

            # 计算缺失日期
            missing_dates = [day for day in workdays if day not in existing_dates]

            # 批量创建记录
            if missing_dates:
                historical_market_value.objects.bulk_create([
                    historical_market_value(
                        currency=currency,
                        date=day,
                        value=0,
                        prev_value=0,
                        change_amount=0,
                        change_rate=0
                    ) for day in missing_dates
                ], batch_size=1000)

        # ================== 阶段2：指标计算 ==================
        # 获取全表最早日期（判断基准日）
        # 获取全表日期范围
        date_all_range = historical_market_value.objects.aggregate(
            min_date=Min('date'),
        )
        base_date = date_all_range['min_date']

        # 使用窗口函数获取前值
        queryset = historical_market_value.objects.annotate(
            prev_value_calc=Window(
                expression=Lag('value', 1),
                partition_by=[F('currency')],
                order_by=F('date').asc()
            )
        ).order_by('currency', 'date')

        # 批量更新容器
        BATCH_SIZE = 1000
        update_buffer = []

        for obj in queryset:
            # 基准日特殊处理
            if obj.date == base_date:
                prev_val = 0
                change_amount = 0
                change_rate = 0
            else:
                prev_val = obj.prev_value_calc or 0
                change_amount = obj.value - prev_val
                change_rate = (change_amount / prev_val) if prev_val else 0

            # 更新对象字段
            obj.prev_value = prev_val
            obj.change_amount = change_amount
            obj.change_rate = change_rate
            update_buffer.append(obj)

            # 批量提交
            if len(update_buffer) >= BATCH_SIZE:
                historical_market_value.objects.bulk_update(
                    update_buffer,
                    ['prev_value', 'change_amount', 'change_rate'],
                    batch_size=BATCH_SIZE
                )
                update_buffer = []

        # 提交剩余数据
        if update_buffer:
            historical_market_value.objects.bulk_update(
                update_buffer,
                ['prev_value', 'change_amount', 'change_rate'],
                batch_size=BATCH_SIZE
            )

    # 记录补全情况
    print(f"Currency:{currency} 补全{len(missing_dates)}条记录")

    # 记录计算性能
    print(f"批量更新完成，本次处理{len(update_buffer)}条记录")


