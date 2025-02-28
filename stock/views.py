from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from django.shortcuts import render, redirect, HttpResponse
from django.db import models
from .models import broker, market, account, industry, stock, position, trade, dividend, subscription, dividend_history, \
    funds, funds_details, historical_position
from utils.excel2db import *
from utils.statistics import *
from utils.utils import *
from django.template.defaulttags import register
import datetime
from decimal import Decimal

from django.db.models.functions import ExtractYear

import pathlib

import json

from django.db import transaction, IntegrityError, OperationalError
from django.db.models import Case, When, Sum, F, Q
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

    funds_details_list_TOP5 = funds_details.objects.filter(funds=funds_id).order_by("-date")[:5]

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
    return render(request, templates_path + 'market_value.html', locals())


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


# 关于
def about(request):
    return render(request, templates_path + 'about.html', locals())


# 测试
def test(request):
    # get_akshare()
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
    # echarts图表
    # data = []
    # funds_details_list = funds_details.objects.filter(funds=3).order_by("date")
    # for rs in funds_details_list:
    #     date = str(rs.date)
    #     value = float(rs.funds_net_value)
    #     data.append({
    #         "date": date,
    #         "value": value
    #     })
    # print(data)

    #trade_list = trade.objects.order_by("trade_date")

    try:
        result = reverse_generate_positions(
            start_date=datetime.date(2025, 2, 22),
            current_positions=[
                {'stock': '511880', 'currency': 1, 'quantity': 18500},
                {'stock': '00817', 'currency': 1, 'quantity': 8000}
            ]
        )
        print(result)
    except ValueError as e:
        print(f"输入错误: {e}")
    except RuntimeError as e:
        print(f"处理失败: {e}")

    return render(request, templates_path + 'test.html', locals())



def is_weekday(date_obj):
    """判断是否为工作日（周一至周五）"""
    return date_obj.weekday() < 5  # 0-4为周一到周五


def reverse_generate_positions(start_date, current_positions):
    """
    最终修复版逆向持仓生成（解决外键类型问题）

    :param start_date: datetime.date 终止日期
    :param current_positions: list格式示例：
        [{'stock': '511880', 'currency': 1, 'quantity': 18500}, ...]
    """
    logger.info("启动逆向持仓生成流程...")

    # ================== 参数校验阶段 ==================
    try:
        # 获取有效股票ID集合
        valid_stock_ids = set(stock.objects.values_list('id', flat=True))
        logger.debug(f"系统有效股票ID示例：{list(valid_stock_ids)[:5]}...（共{len(valid_stock_ids)}条）")

        # 创建股票代码到ID的映射
        stock_code_map = dict(stock.objects.values_list('stock_code', 'id'))
        logger.debug(f"股票代码映射表示例：{dict(list(stock_code_map.items())[:3])}...")

        # 动态获取货币类型
        currency_items = trade.SETTLEMENT_CURRENCY_ITEMS
        valid_currencies = {k for k, _ in currency_items}
        logger.debug(f"有效货币代码：{valid_currencies}")

        # 校验并转换持仓参数
        checked_positions = []
        for idx, pos in enumerate(current_positions, 1):
            # 字段完整性检查
            required_fields = {'stock', 'currency', 'quantity'}
            if missing := required_fields - pos.keys():
                raise ValueError(f"第{idx}条记录缺少字段：{missing}")

            stock_code = pos['stock']
            currency = pos['currency']
            quantity = pos['quantity']

            # 股票代码转换ID
            try:
                stock_id = stock_code_map[stock_code]
            except KeyError:
                valid_codes = list(stock_code_map.keys())[:5]
                raise ValueError(f"第{idx}条记录股票代码无效：{stock_code}，有效示例：{valid_codes}...")

            # 货币类型校验
            if currency not in valid_currencies:
                allowed = ', '.join([f"{v}({k})" for k, v in currency_items])
                raise ValueError(f"第{idx}条记录货币类型无效：{currency}，允许值：{allowed}")

            # 数量校验
            if not isinstance(quantity, int) or quantity < 0:
                raise ValueError(f"第{idx}条记录数量无效，必须为非负整数：{quantity}")

            checked_positions.append({
                'stock_id': stock_id,
                'currency': currency,
                'quantity': quantity
            })

        logger.info(f"参数校验通过，共转换{len(checked_positions)}条持仓记录")

    except Exception as e:
        logger.error("参数校验失败，错误详情：", exc_info=True)
        raise ValueError(f"输入参数错误：{str(e)}") from e

    # ================== 数据处理阶段 ==================
    create_buffer = []  # 批量创建缓存
    update_buffer = []  # 批量更新缓存
    delete_conditions = []  # 删除条件缓存
    position_dict = {
        (p['stock_id'], p['currency']): p['quantity']
        for p in checked_positions
    }

    try:
        with transaction.atomic():
            logger.info("事务启动，开始数据处理...")

            # 生成倒序日期序列
            end_date = timezone.now().date()
            date_sequence = []
            current_day = end_date
            while current_day >= start_date:
                if is_weekday(current_day):
                    date_sequence.append(current_day)
                current_day -= datetime.timedelta(days=1)
            logger.info("日期范围：%s 至 %s，共%d个工作日",
                        start_date, end_date, len(date_sequence))

            # 获取有效交易数据（使用股票ID过滤）
            valid_trades = trade.objects.filter(
                stock_id__in=valid_stock_ids,  # 使用整型ID过滤
                settlement_currency__in=valid_currencies
            ).select_related('stock')
            logger.info("加载有效交易记录：%d条", valid_trades.count())

            # 逆向处理每个工作日
            for idx, current_date in enumerate(date_sequence, 1):
                logger.debug("[%d/%d] 处理日期：%s", idx, len(date_sequence), current_date)

                # 获取当日交易数据
                daily_trans = (
                    valid_trades.filter(trade_date=current_date)
                        .values('stock_id', 'settlement_currency')
                        .annotate(
                        reverse_qty=Sum(
                            Case(
                                When(trade_type=trade.BUY, then=-F('trade_quantity')),
                                When(trade_type=trade.SELL, then=F('trade_quantity')),
                                output_field=models.IntegerField()
                            )
                        )
                    )
                )
                logger.debug("当日交易影响组合数：%d", len(daily_trans))

                # 处理交易影响
                processed_keys = set()
                for trans in daily_trans:
                    stock_id = trans['stock_id']
                    currency = trans['settlement_currency']
                    reverse_qty = trans['reverse_qty'] or 0
                    key = (stock_id, currency)

                    # 逆向计算持仓
                    current_qty = position_dict.get(key, 0)
                    new_qty = current_qty + reverse_qty
                    position_dict[key] = new_qty
                    processed_keys.add(key)
                    logger.debug("组合%s 持仓变化：%d → %d", key, current_qty, new_qty)

                # 处理延续持仓
                for key in list(position_dict.keys()):
                    if key not in processed_keys:
                        new_qty = position_dict[key]
                        logger.debug("组合%s 持仓延续：%d", key, new_qty)
                    else:
                        continue

                    # 零持仓处理
                    if new_qty == 0:
                        delete_conditions.append(
                            Q(date=current_date, stock_id=key[0], currency=key[1])
                        )
                        del position_dict[key]
                        logger.debug("标记零持仓组合：%s", key)
                        continue

                    # 准备数据库操作
                    exists = historical_position.objects.filter(
                        date=current_date,
                        stock_id=key[0],
                        currency=key[1]
                    ).exists()

                    if exists:
                        update_buffer.append({
                            'date': current_date,
                            'stock_id': key[0],
                            'currency': key[1],
                            'quantity': new_qty
                        })
                    else:
                        create_buffer.append(
                            historical_position(
                                date=current_date,
                                stock_id=key[0],
                                currency=key[1],
                                quantity=new_qty
                            )
                        )

                # 批量操作（每200条执行一次）
                if len(create_buffer) >= 200:
                    logger.info("执行批量创建：%d条", len(create_buffer))
                    historical_position.objects.bulk_create(create_buffer)
                    create_buffer = []

                if len(update_buffer) >= 200:
                    logger.info("执行批量更新：%d条", len(update_buffer))
                    update_queries = [
                        models.When(
                            Q(date=item['date']) &
                            Q(stock_id=item['stock_id']) &
                            Q(currency=item['currency']),
                            then=models.Value(item['quantity'])
                        ) for item in update_buffer
                    ]
                    historical_position.objects.update(
                        quantity=Case(*update_queries, default=F('quantity'))
                    )
                    update_buffer = []

            # 处理剩余缓存
            if create_buffer:
                logger.info("执行剩余创建：%d条", len(create_buffer))
                historical_position.objects.bulk_create(create_buffer)
            if update_buffer:
                logger.info("执行剩余更新：%d条", len(update_buffer))
                update_queries = [
                    models.When(
                        Q(date=item['date']) &
                        Q(stock_id=item['stock_id']) &
                        Q(currency=item['currency']),
                        then=models.Value(item['quantity'])
                    ) for item in update_buffer
                ]
                historical_position.objects.update(
                    quantity=Case(*update_queries, default=F('quantity'))
                )

            # 删除零持仓记录
            if delete_conditions:
                logger.info("删除零持仓记录：%d条", len(delete_conditions))
                combined_query = Q()
                for q in delete_conditions:
                    combined_query |= q
                historical_position.objects.filter(combined_query).delete()

            result = {
                "status": "success",
                "processed_days": len(date_sequence),
                "created": len(create_buffer),
                "updated": len(update_buffer),
                "deleted": len(delete_conditions)
            }
            logger.info("处理完成，结果：%s", result)
            return result

    except IntegrityError as e:
        logger.error("数据库完整性错误：%s", str(e))
        raise RuntimeError(f"数据冲突，请检查唯一性约束: {e}") from e
    except Exception as e:
        logger.exception("处理过程中发生未预期错误")
        raise RuntimeError(f"系统异常: {str(e)}") from e


# 用于在模板中用变量定位列表索引的值，支持列表组，访问方法：用{{ list|index:i|index:j }}访问list[i][j]的值
@register.filter
def get_index(mylist, i):
    return mylist[i]



