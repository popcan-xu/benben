import logging
import threading

from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db import transaction
from django.db.models import Case, When, Window, IntegerField, DecimalField, Prefetch, Q
from django.db.models.functions import Lag
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from utils.excel2db import *
from utils.statistics import *
from utils.utils import *
from .models import Industry, DividendHistory, Baseline, HistoricalPosition

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import pandas as pd
import akshare as ak
import datetime
import time

logger = logging.getLogger(__name__)

templates_path = 'dashboard/'


# 总览
def overview1(request):
    rate = get_rate()
    path = pathlib.Path("./templates/dashboard/overview.json")

    # 若json文件不存在or点击了刷新按钮，则重写json文件（文件不存在则创建文件）
    if not path.is_file() or request.method == 'POST':
        # 重新生成数据并写入文件
        overview_data = _generate_overview_data(rate)
        FileOperate(dictData=overview_data,
                    filepath='./templates/dashboard/',
                    filename='overview.json').operation_file()

    # 统一读取文件数据（无论是否重新生成）
    with open('./templates/dashboard/overview.json', 'r', encoding='utf-8') as f:
        overview_data = json.load(f)

    updating_time = datetime.datetime.now()

    context = {
        "overview": overview_data,
        "rate": rate,
        "updating_time": updating_time
    }
    return render(request, templates_path + 'overview.html', context)


def _generate_overview_data1(rate):
    current_year = datetime.datetime.now().year
    colors = ['#4c6ef5', '#ff922b', '#40c057', '#fab005', '#e64980', '#adb5bd']
    currencies = Currency.objects.all()  # 只查询一次数据库
    # 创建一个字典，格式为 {货币ID: {'code': 代码, 'name': 名称}}
    currency_dict = {c.id: {'code': c.code, 'name': c.name} for c in currencies}

    # 计算基金价值总和
    fund_value_sum = 0
    fund_list = Fund.objects.all()
    # 获得资产占比数据，用于生成chart图表
    fund_value_array = []
    for rs in fund_list:
        fund_value_array.append(round(float(rs.fund_value) * rate[rs.currency.code]))
        # fund_principal_array.append(round(float(rs.fund_principal) * rate[rs.currency.code]))
        fund_value_sum += round(float(rs.fund_value) * rate[rs.currency.code])

    # 计算基金价值占比和加权净值
    fund_percent_dict = {1: 0, 2: 0, 3: 0}
    fund_net_value_weighting = 0
    for key in currency_dict:
        fund_percent_dict[key] = float(fund_list.get(currency_id=key).fund_value) / fund_value_sum
        fund_net_value_weighting += float(fund_list.get(currency_id=key).fund_net_value) * fund_percent_dict[key]

    # 计算人民币持仓市值总和，用于进一步计算人民币基金的持仓比例
    stock_dict = Position.objects.values("stock").annotate(
        count=Count("stock")).values('stock__stock_code').order_by('stock__stock_code')
    stock_code_array = []
    for d in stock_dict:
        stock_code = d['stock__stock_code']
        stock_code_array.append(stock_code)
    price_array = get_stock_array_price(stock_code_array)
    content_CNY, amount_sum_CNY, name_array_CNY, value_array_CNY = get_value_stock_content(1, price_array, rate['HKD'],
                                                                                           rate['USD'])

    # 计算仓位
    position_percent_dict = {}
    fund_value_dict = {}
    market_value_dict = {}

    # 获取所有fund同时存在记录的最大有效日期
    # 获取所有不同的基金数量
    total_fund = FundHistory.objects.values('fund').distinct().count()
    # 查找所有日期及其对应的基金数量，并筛选出基金数等于总基金数的日期
    valid_dates = FundHistory.objects.values('date').annotate(
        fund_count=Count('fund', distinct=True)
    ).filter(fund_count=total_fund).order_by('-date')
    if valid_dates.exists():
        max_date_fund = valid_dates.first()['date']
    else:
        # 根据问题描述，其他逻辑确保存在有效日期，此处无需处理
        max_date_fund = None

    for key, value in currency_dict.items():
        fund_id = Fund.objects.get(currency_id=key).id
        fund_value_dict[key] = FundHistory.objects.get(fund_id=fund_id, date=max_date_fund).fund_value
        market_value_dict[key] = HistoricalMarketValue.objects.get(currency_id=key, date=max_date_fund).value
        position_percent_dict[key] = market_value_dict[key] / fund_value_dict[key]
    # 人民币基金的持仓比例通过511880的市值占比计算
    current_price, increase, color = get_quote_snowball('511880')  # 银华日利
    positions = Position.objects.filter(stock=93)  # 银华日利
    quantity = 0
    for pos in positions:
        quantity += pos.position_quantity
    cash_like_assets_CNY = current_price * quantity
    position_percent_dict[1] = 1 - cash_like_assets_CNY / amount_sum_CNY

    # 计算加权仓位
    position_percent_weighting = 0
    for key in currency_dict:
        position_percent_weighting += float(position_percent_dict[key]) * fund_percent_dict[key]

    total_dividend = []
    current_dividend = []
    total_dividend_sum = 0
    current_dividend_sum = 0
    for key in currency_dict:
        result = {'value': float(
            Dividend.objects.filter(
                currency_id=key
            ).aggregate(amount=Sum('dividend_amount'))['amount'] or 0.0
        ) * rate[currency_dict[key]['code']], 'name': currency_dict[key]['name'], 'color': colors[key - 1]}
        total_dividend.append(result)
        total_dividend_sum += result['value']
        result = {'value': float(
            Dividend.objects.filter(
                currency_id=key,
                dividend_date__year=current_year
            ).aggregate(amount=Sum('dividend_amount'))['amount'] or 0.0
        ) * rate[currency_dict[key]['code']], 'name': currency_dict[key]['name'], 'color': colors[key - 1]}
        current_dividend.append(result)
        current_dividend_sum += result['value']

    # 获得新股、新债总收益、中签数量
    subscription_sum = float(Subscription.objects.aggregate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity")))['amount'])
    subscription_stock_num = Subscription.objects.filter(subscription_type=1).count()
    subscription_band_num = Subscription.objects.filter(subscription_type=2).count()
    # 获得当年新股、新债总收益、中签数量
    current_subscription_sum = Subscription.objects.filter(subscription_date__year=current_year).aggregate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity")))['amount']
    if current_subscription_sum is None:
        current_subscription_sum = 0
    current_subscription_sum = float(current_subscription_sum)
    current_subscription_stock_num = Subscription.objects.filter(subscription_date__year=current_year,
                                                                 subscription_type=1).count()
    current_subscription_band_num = Subscription.objects.filter(subscription_date__year=current_year,
                                                                subscription_type=2).count()
    # 获取持仓股票数量
    holding_stock_number = Position.objects.values("stock").annotate(count=Count("stock")).count()
    # 获得总市值、持仓股票一览数据、持仓前五占比数据
    # price_array = []  # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_array中，以提高性能
    # stock_dict = Position.objects.values("stock").annotate(count=Count("stock")).values('stock__stock_code')

    # stock_code_array = []
    # for d in stock_dict:
    #     stock_code = d['stock__stock_code']
    #     stock_code_array.append(stock_code)
    # price_array = get_stock_array_price(stock_code_array)

    # position_currency=0时，get_value_stock_content返回人民币、港元、美元计价的所有股票的人民币市值汇总
    content, market_value_sum, name_array, value_array = get_value_stock_content(0, price_array, rate['HKD'],
                                                                                 rate['USD'])
    # 计算当年分红占总市值的百分比
    current_dividend_percent = float(current_dividend_sum / market_value_sum) * 100
    # 计算前五大持仓百分比之和
    top5_content = content[:5]
    top5_percent = 0.0
    i = 0
    while i < len(top5_content):
        top5_percent += float(top5_content[i][6][:-1])  # [:-1]用于截去百分比字符串的最后一位（百分号）
        i += 1
    # 获得持仓市场占比数据，用于生成chart图表
    market_name_array, market_value_array = get_value_market_sum(price_array, rate['HKD'], rate['USD'])

    # 获得近期交易列表
    top5_trade_list = Trade.objects.all().order_by('-trade_date', '-modified_time')[:5]
    # 获得近期分红列表
    top5_dividend_list = Dividend.objects.all().order_by('-dividend_date', '-modified_time')[:5]
    # 获得近期打新列表
    top5_subscription_list = Subscription.objects.all().order_by('-subscription_date', '-modified_time')[:5]
    # 持仓股票一览
    holding_stock_array = []
    for i in content:
        holding_stock_array.append((i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7]))
    top5_array = []
    index = 0
    for i in top5_content:
        top5_array.append((i[0], i[5], i[6], colors[index], i[7]))
        index += 1
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
            # str(i.get_settlement_currency_display()),
            str(i.currency.name),
            i.account.account_abbreviation,
            i.stock_id
        ))
    # 近期分红
    dividend_array = []
    for i in top5_dividend_list:
        dividend_array.append((
            i.dividend_date.strftime("%Y-%m-%d"),
            str(i.stock.stock_name) + '（' + str(i.stock.stock_code) + '）',
            float(i.dividend_amount),
            i.account.account_abbreviation,
            i.stock_id
        ))
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

    # 写入overview.json
    overview_data = {}
    # 总市值、分红收益、当年分红、当年分红率、打新收益、当年打新、持股数量
    overview_data.update(fund_value_sum=fund_value_sum)
    overview_data.update(fund_net_value_weighting=fund_net_value_weighting)
    overview_data.update(market_value_sum=market_value_sum)
    overview_data.update(position_percent_weighting=position_percent_weighting)
    overview_data.update(total_dividend_sum=total_dividend_sum)
    overview_data.update(current_dividend_sum=current_dividend_sum)
    overview_data.update(current_dividend_percent=current_dividend_percent)
    overview_data.update(total_dividend=total_dividend)
    overview_data.update(current_dividend=current_dividend)
    overview_data.update(subscription_sum=subscription_sum)
    overview_data.update(subscription_stock_num=subscription_stock_num)
    overview_data.update(subscription_band_num=subscription_band_num)
    overview_data.update(current_subscription_sum=current_subscription_sum)
    overview_data.update(current_subscription_stock_num=current_subscription_stock_num)
    overview_data.update(current_subscription_band_num=current_subscription_band_num)
    overview_data.update(holding_stock_number=holding_stock_number)
    overview_data.update(fund_value_array=fund_value_array)
    # overview_data.update(fund_principal_array=fund_principal_array)
    # overview_data.update(fund_currency_array=fund_currency_array)
    overview_data.update(holding_stock_array=holding_stock_array)

    overview_data.update(top5_percent=top5_percent)
    overview_data.update(top5_array=top5_array)

    overview_data.update(market_name_array=market_name_array)
    overview_data.update(market_value_array=market_value_array)

    overview_data.update(trade_array=trade_array)
    overview_data.update(dividend_array=dividend_array)
    overview_data.update(subscription_array=subscription_array)

    overview_data.update(colors=colors)

    overview_data.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return overview_data


def overview(request):
    rate = get_rate()

    # 使用内存缓存键
    cache_key = 'overview_data'

    # 若缓存不存在或点击了刷新按钮，则重新生成数据
    if cache.get(cache_key) is None or request.method == 'POST':
        # 重新生成数据并存入缓存
        overview_data = _generate_overview_data(rate)
        # 设置缓存，过期时间为1小时（3600秒）
        cache.set(cache_key, overview_data, 300)
    else:
        # 从缓存获取数据
        overview_data = cache.get(cache_key)

    updating_time = datetime.datetime.now()

    context = {
        "overview": overview_data,
        "rate": rate,
        "updating_time": updating_time
    }
    return render(request, templates_path + 'overview.html', context)


def _generate_overview_data(rate):
    """生成总览数据

    参数:
        rate: 汇率字典

    返回:
        overview_data: 包含所有总览数据的字典
    """
    current_year = datetime.datetime.now().year
    colors = ['#4c6ef5', '#ff922b', '#40c057', '#fab005', '#e64980', '#adb5bd']

    # 获取货币信息
    currency_dict = _get_currency_dict()

    # 计算基金相关数据
    fund_data = _calculate_fund_data(rate, currency_dict)

    # 获取持仓股票代码和价格数据
    stock_code_array, price_array = _get_stock_data()

    # 计算人民币持仓数据
    cny_data = _calculate_cny_position_data(price_array, rate)

    # 计算仓位数据
    position_data = _calculate_position_data(currency_dict, cny_data['amount_sum_CNY'])

    # 计算分红数据
    dividend_data = _calculate_dividend_data(rate, currency_dict, current_year, colors)

    # 计算打新数据
    subscription_data = _calculate_subscription_data(current_year)

    # 计算所有货币的持仓市值数据
    market_data = _calculate_market_data(price_array, rate)

    # 获取持仓股票数量
    holding_stock_number = _get_holding_stock_count()

    # 计算前五大持仓数据
    top5_data = _calculate_top5_data(market_data['content'], colors)

    # 获取市场占比数据
    market_sum_data = _get_market_sum_data(price_array, rate)

    # 获取近期活动数据
    recent_activities = _get_recent_activities()

    # 构建最终结果
    overview_data = _build_overview_data(
        fund_data, position_data, dividend_data, subscription_data,
        market_data, holding_stock_number, top5_data, market_sum_data,
        recent_activities, colors, current_year
    )

    return overview_data


def _get_currency_dict():
    """获取货币字典"""
    currencies = Currency.objects.all()
    return {c.id: {'code': c.code, 'name': c.name} for c in currencies}


def _calculate_fund_data(rate, currency_dict):
    """计算基金相关数据"""
    fund_list = Fund.objects.all()
    fund_value_array = []
    fund_value_sum = 0

    for fund in fund_list:
        value = round(float(fund.fund_value) * rate[fund.currency.code])
        fund_value_array.append(value)
        fund_value_sum += value

    # 计算基金价值占比和加权净值
    fund_percent_dict = {}
    fund_net_value_weighting = 0

    for key in currency_dict:
        fund = fund_list.get(currency_id=key)
        percent = float(fund.fund_value) / fund_value_sum
        fund_percent_dict[key] = percent
        fund_net_value_weighting += float(fund.fund_net_value) * percent

    return {
        'fund_value_sum': fund_value_sum,
        'fund_value_array': fund_value_array,
        'fund_percent_dict': fund_percent_dict,
        'fund_net_value_weighting': fund_net_value_weighting
    }


def _get_stock_data():
    """获取持仓股票代码和价格数据"""
    stock_dict = Position.objects.values("stock").annotate(
        count=Count("stock")
    ).values('stock__stock_code').order_by('stock__stock_code')

    stock_code_array = [d['stock__stock_code'] for d in stock_dict]
    price_array = get_stock_array_price(stock_code_array)

    return stock_code_array, price_array


def _calculate_cny_position_data(price_array, rate):
    """计算人民币持仓数据"""
    content_CNY, amount_sum_CNY, name_array_CNY, value_array_CNY = get_value_stock_content(
        1, price_array, rate['HKD'], rate['USD']
    )

    return {
        'content_CNY': content_CNY,
        'amount_sum_CNY': amount_sum_CNY,
        'name_array_CNY': name_array_CNY,
        'value_array_CNY': value_array_CNY
    }


def _calculate_position_data(currency_dict, amount_sum_CNY):
    """计算仓位数据"""
    # 获取所有fund同时存在记录的最大有效日期
    total_fund = FundHistory.objects.values('fund').distinct().count()
    valid_dates = FundHistory.objects.values('date').annotate(
        fund_count=Count('fund', distinct=True)
    ).filter(fund_count=total_fund).order_by('-date')

    max_date_fund = valid_dates.first()['date'] if valid_dates.exists() else None

    position_percent_dict = {}
    fund_value_dict = {}
    market_value_dict = {}

    for key, value in currency_dict.items():
        fund_id = Fund.objects.get(currency_id=key).id
        fund_value_dict[key] = FundHistory.objects.get(fund_id=fund_id, date=max_date_fund).fund_value
        market_value_dict[key] = HistoricalMarketValue.objects.get(currency_id=key, date=max_date_fund).value
        position_percent_dict[key] = market_value_dict[key] / fund_value_dict[key]

    # 人民币基金的持仓比例通过511880的市值占比计算
    current_price, increase, color = get_quote_snowball('511880')  # 银华日利
    positions = Position.objects.filter(stock=93)  # 银华日利
    quantity = sum(pos.position_quantity for pos in positions)
    cash_like_assets_CNY = current_price * quantity
    position_percent_dict[1] = 1 - cash_like_assets_CNY / amount_sum_CNY

    return position_percent_dict


def _calculate_dividend_data(rate, currency_dict, current_year, colors):
    """计算分红数据"""
    total_dividend = []
    current_dividend = []
    total_dividend_sum = 0
    current_dividend_sum = 0

    for key in currency_dict:
        # 总分红
        total_amount = Dividend.objects.filter(
            currency_id=key
        ).aggregate(amount=Sum('dividend_amount'))['amount'] or 0.0

        total_value = float(total_amount) * rate[currency_dict[key]['code']]
        total_item = {
            'value': total_value,
            'name': currency_dict[key]['name'],
            'color': colors[key - 1]
        }
        total_dividend.append(total_item)
        total_dividend_sum += total_value

        # 当年分红
        current_amount = Dividend.objects.filter(
            currency_id=key,
            dividend_date__year=current_year
        ).aggregate(amount=Sum('dividend_amount'))['amount'] or 0.0

        current_value = float(current_amount) * rate[currency_dict[key]['code']]
        current_item = {
            'value': current_value,
            'name': currency_dict[key]['name'],
            'color': colors[key - 1]
        }
        current_dividend.append(current_item)
        current_dividend_sum += current_value

    return {
        'total_dividend': total_dividend,
        'current_dividend': current_dividend,
        'total_dividend_sum': total_dividend_sum,
        'current_dividend_sum': current_dividend_sum
    }


def _calculate_subscription_data(current_year):
    """计算打新数据"""
    # 总打新收益
    subscription_sum = Subscription.objects.aggregate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity"))
    )['amount'] or 0
    subscription_sum = float(subscription_sum)

    # 打新数量
    subscription_stock_num = Subscription.objects.filter(subscription_type=1).count()
    subscription_band_num = Subscription.objects.filter(subscription_type=2).count()

    # 当年打新收益
    current_subscription_sum = Subscription.objects.filter(
        subscription_date__year=current_year
    ).aggregate(
        amount=Sum((F("selling_price") - F("buying_price")) * F("subscription_quantity"))
    )['amount'] or 0
    current_subscription_sum = float(current_subscription_sum)

    # 当年打新数量
    current_subscription_stock_num = Subscription.objects.filter(
        subscription_date__year=current_year, subscription_type=1
    ).count()
    current_subscription_band_num = Subscription.objects.filter(
        subscription_date__year=current_year, subscription_type=2
    ).count()

    return {
        'subscription_sum': subscription_sum,
        'subscription_stock_num': subscription_stock_num,
        'subscription_band_num': subscription_band_num,
        'current_subscription_sum': current_subscription_sum,
        'current_subscription_stock_num': current_subscription_stock_num,
        'current_subscription_band_num': current_subscription_band_num
    }


def _calculate_market_data(price_array, rate):
    """计算市场数据"""
    content, market_value_sum, name_array, value_array = get_value_stock_content(
        0, price_array, rate['HKD'], rate['USD']
    )

    return {
        'content': content,
        'market_value_sum': market_value_sum,
        'name_array': name_array,
        'value_array': value_array
    }


def _get_holding_stock_count():
    """获取持仓股票数量"""
    return Position.objects.values("stock").annotate(count=Count("stock")).count()


def _calculate_top5_data(content, colors):
    """计算前五大持仓数据"""
    if not content or len(content) < 5:
        return {'top5_percent': 0, 'top5_array': [], 'holding_stock_array': []}

    top5_content = content[:5]
    top5_percent = 0.0

    for i, item in enumerate(top5_content):
        if len(item) > 6:
            # 提取百分比并去掉百分号
            percent_str = item[6]
            if percent_str and percent_str.endswith('%'):
                top5_percent += float(percent_str[:-1])

    # 持仓股票一览
    holding_stock_array = []
    for item in content:
        if len(item) >= 8:
            holding_stock_array.append(tuple(item[:8]))

    # 前五大持仓数组
    top5_array = []
    for i, item in enumerate(top5_content):
        if len(item) >= 8:
            top5_array.append((item[0], item[5], item[6], colors[i], item[7]))

    return {
        'top5_percent': top5_percent,
        'top5_array': top5_array,
        'holding_stock_array': holding_stock_array,
        'holding_stock_json': json.dumps(holding_stock_array) #因为holding_stock_array为包含元组的列表，需要将数据转换为JSON字符串
    }


def _get_market_sum_data(price_array, rate):
    """获取市场占比数据"""
    market_name_array, market_value_array = get_value_market_sum(price_array, rate['HKD'], rate['USD'])

    return {
        'market_name_array': market_name_array,
        'market_value_array': market_value_array
    }


def _get_recent_activities():
    """获取近期活动数据"""
    # 近期交易
    top5_trade_list = Trade.objects.all().order_by('-trade_date', '-modified_time')[:5]
    trade_array = []
    for trade in top5_trade_list:
        trade_array.append((
            trade.trade_date.strftime("%Y-%m-%d"),
            f"{trade.stock.stock_name}（{trade.stock.stock_code}）",
            trade.get_trade_type_display(),
            float(trade.trade_price),
            trade.trade_quantity,
            float(trade.trade_price * trade.trade_quantity),
            trade.currency.name,
            trade.account.account_abbreviation,
            trade.stock_id
        ))

    # 近期分红
    top5_dividend_list = Dividend.objects.all().order_by('-dividend_date', '-modified_time')[:5]
    dividend_array = []
    for dividend in top5_dividend_list:
        dividend_array.append((
            dividend.dividend_date.strftime("%Y-%m-%d"),
            f"{dividend.stock.stock_name}（{dividend.stock.stock_code}）",
            float(dividend.dividend_amount),
            dividend.account.account_abbreviation,
            dividend.stock_id
        ))

    # 近期打新
    top5_subscription_list = Subscription.objects.all().order_by('-subscription_date', '-modified_time')[:5]
    subscription_array = []
    for subscription in top5_subscription_list:
        profit = (subscription.selling_price - subscription.buying_price) * subscription.subscription_quantity
        profit_percent = ((subscription.selling_price / subscription.buying_price) - 1) * 100
        subscription_array.append((
            subscription.subscription_date.strftime("%Y-%m-%d"),
            subscription.subscription_name,
            subscription.get_subscription_type_display(),
            subscription.subscription_quantity,
            float(profit),
            float(profit_percent),
            subscription.account.account_abbreviation
        ))

    return {
        'trade_array': trade_array,
        'dividend_array': dividend_array,
        'subscription_array': subscription_array
    }


def _build_overview_data(fund_data, position_data, dividend_data, subscription_data,
                         market_data, holding_stock_number, top5_data, market_sum_data,
                         recent_activities, colors, current_year):
    """构建最终的总览数据字典"""
    # 计算当年分红占总市值的百分比
    current_dividend_percent = 0
    if market_data['market_value_sum'] > 0:
        current_dividend_percent = (dividend_data['current_dividend_sum'] / market_data['market_value_sum']) * 100

    # 计算加权仓位
    position_percent_weighting = 0
    for key in position_data:
        position_percent_weighting += float(position_data[key]) * fund_data['fund_percent_dict'].get(key, 0)

    overview_data = {
        # 基金数据
        'fund_value_sum': fund_data['fund_value_sum'],
        'fund_net_value_weighting': fund_data['fund_net_value_weighting'],
        'fund_value_array': fund_data['fund_value_array'],

        # 市场数据
        'market_value_sum': market_data['market_value_sum'],
        'position_percent_weighting': position_percent_weighting,

        # 分红数据
        'total_dividend_sum': dividend_data['total_dividend_sum'],
        'current_dividend_sum': dividend_data['current_dividend_sum'],
        'current_dividend_percent': current_dividend_percent,
        'total_dividend': dividend_data['total_dividend'],
        'current_dividend': dividend_data['current_dividend'],

        # 打新数据
        'subscription_sum': subscription_data['subscription_sum'],
        'subscription_stock_num': subscription_data['subscription_stock_num'],
        'subscription_band_num': subscription_data['subscription_band_num'],
        'current_subscription_sum': subscription_data['current_subscription_sum'],
        'current_subscription_stock_num': subscription_data['current_subscription_stock_num'],
        'current_subscription_band_num': subscription_data['current_subscription_band_num'],

        # 持仓数据
        'holding_stock_number': holding_stock_number,
        'holding_stock_array': top5_data['holding_stock_array'],
        'holding_stock_json': top5_data['holding_stock_json'],

        # 前五大持仓数据
        'top5_percent': top5_data['top5_percent'],
        'top5_array': top5_data['top5_array'],

        # 市场占比数据
        'market_name_array': market_sum_data['market_name_array'],
        'market_value_array': market_sum_data['market_value_array'],

        # 近期活动数据
        'trade_array': recent_activities['trade_array'],
        'dividend_array': recent_activities['dividend_array'],
        'subscription_array': recent_activities['subscription_array'],

        # 其他数据
        'colors': colors,
        'modified_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    return overview_data





# 资产概览
def view_fund(request):
    fund_list = Fund.objects.all()
    rate = get_rate()
    currency_dict = {c.id: {'code': c.code, 'name': c.name} for c in Currency.objects.all()}
    asset_distribution = {}
    for key in currency_dict:
        asset_distribution[key] = float(Fund.objects.get(currency_id=key).fund_value) * rate[
            currency_dict[key]['code']]

    updating_time = datetime.datetime.now()

    context = {
        "fund_list": fund_list,
        "rate": rate,
        "asset_distribution": asset_distribution,
        "updating_time": updating_time
    }
    return render(request, templates_path + 'view_fund.html', context)


# 资产详情
def view_fund_details(request, fund_id):
    fund_net_value_list = []
    baseline_net_value_list = []
    fund_profit_rate_list = []
    baseline_profit_rate_list = []
    fund_annualized_profit_rate_list = []
    baseline_annualized_profit_rate_list = []
    year_end_date_list = []

    fund_history_list = FundHistory.objects.filter(fund=fund_id).order_by("date")
    fund_name = Fund.objects.get(id=fund_id).fund_name
    baseline_name = Fund.objects.get(id=fund_id).baseline.name
    name_list = [fund_name, baseline_name]

    max_date = get_max_date(fund_id)
    min_date = get_min_date(fund_id)
    years = max_date.year - min_date.year
    second_max_date = get_second_max_date(fund_id)
    current_fund_history_object = fund_history_list.get(date=max_date)  # 生成概要数据
    profit_rate = current_fund_history_object.fund_profit / current_fund_history_object.fund_principal
    last_period_value = current_fund_history_object.fund_value - current_fund_history_object.fund_current_profit
    last_year_max_date = FundHistory.objects.filter(
        date__year=datetime.date.today().year - 1,
        fund=fund_id
    ).aggregate(
        max_date=Max('date')
    )['max_date']
    last_year_value = fund_history_list.get(date=last_year_max_date).fund_value
    year_change_amount = current_fund_history_object.fund_value - last_year_value
    if last_year_value != Decimal('0.0000') and year_change_amount != Decimal('0.0000'):
        year_change_rate = year_change_amount / last_year_value
    else:
        year_change_rate = 0
    last_year_net_value = fund_history_list.get(date=last_year_max_date).fund_net_value
    if last_year_net_value != Decimal('0.0000'):
        year_change_net_value_rate = current_fund_history_object.fund_net_value / last_year_net_value - 1
    else:
        year_change_net_value_rate = 0

    # 定义文件路径
    path = pathlib.Path("./templates/dashboard/baseline.json")

    # 如果文件不存在，则创建文件
    if not path.is_file():
        get_his_index()
    else:
        # 读取当前文件中的修改时间
        with open(path, 'r', encoding='utf-8') as f:
            baseline_data = json.load(f)

        # 获取文件中的修改时间
        file_modified_time_str = baseline_data.get("modified_time", "")

        # 检查是否需要更新数据
        need_update = False
        if not file_modified_time_str:
            need_update = True
        else:
            try:
                # 将字符串时间转换为datetime对象
                file_modified_time = datetime.datetime.strptime(file_modified_time_str, "%Y-%m-%d %H:%M:%S")
                current_time = datetime.datetime.now()

                # 计算当前时间与文件修改时间的差值（秒）
                time_diff = (current_time - file_modified_time).total_seconds()
                is_same_day = file_modified_time.date() == current_time.date()

                # 如果不是同一天或时间差超过3600秒（60分钟），则需要更新
                need_update = not is_same_day or time_diff > 3600
            except ValueError:
                need_update = True

        # 如果需要更新，则执行更新操作
        if need_update:
            baseline_name_array = [rs.baseline.name for rs in Fund.objects.all()]
            get_current_index(baseline_name_array)

    # 读取baseline.json文件
    with open(path, 'r', encoding='utf-8') as f:
        baseline = json.load(f)

    min_date_baseline_value = get_baseline_closing_price(baseline[baseline_name], int(min_date.year))

    # 生成收益率比对数据compare_data_group
    compare_data_group = []
    year_list = list(
        fund_history_list.annotate(year=ExtractYear('date')).values_list('year', flat=True).distinct().order_by('year')
    )
    pre_fund_net_value = 1
    pre_baseline_net_value = 1
    fund_temp = []
    baseline_temp = []
    for year in year_list:
        year_end_date = get_year_end_date(fund_id, year)

        fund_value = float(fund_history_list.get(date=year_end_date).fund_value)
        fund_net_value = float(fund_history_list.get(date=year_end_date).fund_net_value)
        fund_temp.append(fund_net_value)
        fund_profit_rate = (fund_net_value / pre_fund_net_value - 1) * 100
        pre_fund_net_value = fund_net_value

        baseline_value = float(get_baseline_closing_price(baseline[baseline_name], year))
        baseline_net_value = float(baseline_value / min_date_baseline_value)
        baseline_temp.append(baseline_net_value)
        baseline_profit_rate = (baseline_net_value / pre_baseline_net_value - 1) * 100
        pre_baseline_net_value = baseline_net_value

        earliest_date = Fund.objects.get(id=fund_id).fund_create_date  # 计算年化收益率的起始日期为基金的创立日期
        years_value = float((year_end_date - earliest_date).days / 365)
        fund_annualized_profit_rate = 0 if years_value == 0 else (float(fund_net_value) ** (1 / years_value) - 1) *100
        baseline_annualized_profit_rate = 0 if years_value == 0 else (float(baseline_net_value) **  (1 / years_value) - 1) *100

        # 初始化默认值
        fund_annualized_profit_rate_3years = 0
        baseline_annualized_profit_rate_3years = 0
        fund_annualized_profit_rate_5years = 0
        baseline_annualized_profit_rate_5years = 0

        # 计算3年年化收益率（当数据点足够时）
        if len(fund_temp) > 3:
            fund_annualized_profit_rate_3years = ((fund_temp[-1] / fund_temp[-4]) ** (1 / 3) - 1) * 100
            baseline_annualized_profit_rate_3years = ((baseline_temp[-1] / baseline_temp[-4]) ** (1 / 3) - 1) * 100

        # 计算5年年化收益率（当数据点足够时）
        if len(fund_temp) > 5:
            fund_annualized_profit_rate_5years = ((fund_temp[-1] / fund_temp[-6]) ** (1 / 5) - 1) * 100
            baseline_annualized_profit_rate_5years = ((baseline_temp[-1] / baseline_temp[-6]) ** (1 / 5) - 1) * 100

        compare_net_value = (fund_net_value - baseline_net_value) * 100
        compare_profit_rate = fund_profit_rate - baseline_profit_rate
        compare_annualized_profit_rate = fund_annualized_profit_rate - baseline_annualized_profit_rate
        compare_annualized_profit_rate_3years = fund_annualized_profit_rate_3years - baseline_annualized_profit_rate_3years
        compare_annualized_profit_rate_5years = fund_annualized_profit_rate_5years - baseline_annualized_profit_rate_5years

        # 生成收益率对比数据
        compare_data = [str(year_end_date.year), fund_value, baseline_value, fund_net_value, baseline_net_value,
                        compare_net_value, fund_profit_rate, baseline_profit_rate, compare_profit_rate,
                        fund_annualized_profit_rate, baseline_annualized_profit_rate, compare_annualized_profit_rate,
                        fund_annualized_profit_rate_3years, baseline_annualized_profit_rate_3years,
                        compare_annualized_profit_rate_3years, fund_annualized_profit_rate_5years,
                        baseline_annualized_profit_rate_5years, compare_annualized_profit_rate_5years]
        compare_data_group.append(compare_data)

        # 生成年度收益率数据，用于图表
        year_end_date_list.append(float(year_end_date.year))
        fund_net_value_list.append(float(Decimal(fund_net_value).quantize(Decimal('0.0000'))))
        baseline_net_value_list.append(float(Decimal(baseline_net_value).quantize(Decimal('0.0000'))))
        fund_profit_rate_list.append(float(Decimal(fund_profit_rate).quantize(Decimal('0.00'))))
        baseline_profit_rate_list.append(float(Decimal(baseline_profit_rate).quantize(Decimal('0.00'))))


        # 生成年化收益率数据，用于图表
        fund_annualized_profit_rate_list.append(
            float(Decimal(fund_annualized_profit_rate).quantize(Decimal('0.00'))))
        baseline_annualized_profit_rate_list.append(
            float(Decimal(baseline_annualized_profit_rate).quantize(Decimal('0.00'))))

    # 生成年度收益率柱图和净值折线图数据
    line_year_end_date_list = year_end_date_list
    line_fund_net_value_list = fund_net_value_list
    line_baseline_net_value_list = baseline_net_value_list
    # bar_year_end_date_list = year_end_date_list[1:]  # 柱图第一列去掉
    # bar_fund_profit_rate_list = fund_profit_rate_list[1:]  # 柱图第一列去掉
    # bar_baseline_profit_rate_list = baseline_profit_rate_list[1:]  # 柱图第一列去掉
    bar_year_end_date_list = year_end_date_list  # 柱图第一列去掉
    bar_fund_profit_rate_list = fund_profit_rate_list # 柱图第一列去掉
    bar_baseline_profit_rate_list = baseline_profit_rate_list  # 柱图第一列去掉

    # 生成资产变化日历字典数据assetChanges
    assetChanges = {}
    for rs in fund_history_list:
        date = rs.date.strftime("%Y-%m-%d")
        # amount = float(rs.fund_current_profit) - float(rs.fund_in_out)
        amount = float(rs.fund_current_profit)
        assetChanges[date] = amount

    # 生成净值、资产、收益曲线数据
    fund_data = []
    for rs in fund_history_list:
        date = str(rs.date)
        net_value = float(rs.fund_net_value)
        value = float(rs.fund_value / 10000)
        principal = float(rs.fund_principal / 10000)
        profit = float(rs.fund_profit / 10000)
        fund_data.append({
            "date": date,
            "net_value": net_value,
            "value": value,
            "principal": principal,
            "profit": profit
        })

    # 近期资产、收益、年度收益列表
    fund_history_list_TOP = FundHistory.objects.filter(fund=fund_id).order_by("-date")[:12]
    yearly_profit_list = FundHistory.objects.filter(fund=fund_id).values('date__year').annotate(
        yearly_profit=Sum('fund_current_profit')
    ).order_by('-date__year')
    profit_total = sum(entry['yearly_profit'] for entry in yearly_profit_list)

    yearly_profit_data = []
    for rs in yearly_profit_list:
        year = str(rs['date__year'])
        amount = float(rs['yearly_profit'] / 10000)
        yearly_profit_data.append({
            "year": year,
            "amount": amount
        })

    # 近期、年度出入金列表
    recent_in_out_list = FundHistory.objects.filter(fund=fund_id).exclude(fund_in_out=0).order_by('-date')[:12]
    yearly_in_out_list = FundHistory.objects.filter(fund=fund_id).values('date__year').annotate(
        yearly_in_out=Sum('fund_in_out')
    ).order_by('-date__year')
    in_out_total = sum(entry['yearly_in_out'] for entry in yearly_in_out_list)

    # 生成年度出入金图表数据
    yearly_in_out_data = []
    for rs in yearly_in_out_list:
        year = str(rs['date__year'])
        amount = float(rs['yearly_in_out'] / 10000)
        yearly_in_out_data.append({
            "year": year,
            "amount": amount
        })

    updating_time = datetime.datetime.now()

    return render(request, templates_path + 'view_fund_details.html', locals())


# 市值概览
def view_market_value(request):
    rate = get_rate()
    currency_dict = {c.id: {'code': c.code, 'name': c.name} for c in Currency.objects.all()}

    # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_array中，以提高性能
    stock_dict = Position.objects.values("stock").annotate(
        count=Count("stock")).values('stock__stock_code').order_by('stock__stock_code')
    stock_code_array = []
    for d in stock_dict:
        stock_code = d['stock__stock_code']
        stock_code_array.append(stock_code)
    price_array = get_stock_array_price(stock_code_array)

    content_CNY, amount_sum_CNY, name_array_CNY, value_array_CNY = get_value_stock_content(1, price_array, rate['HKD'],
                                                                                           rate['USD'])
    content_HKD, amount_sum_HKD, name_array_HKD, value_array_HKD = get_value_stock_content(2, price_array, rate['HKD'],
                                                                                           rate['USD'])
    content_USD, amount_sum_USD, name_array_USD, value_array_USD = get_value_stock_content(3, price_array, rate['HKD'],
                                                                                           rate['USD'])

    value_dict = {}
    value_dict_toCNY = {}
    result = HistoricalMarketValue.objects.aggregate(
        max_date=Max('date')  # 最大值（最新日期）
    )
    current_date = result['max_date']

    for key in currency_dict:
        if HistoricalMarketValue.objects.filter(currency_id=key, date=current_date).exists():
            value_dict[key] = HistoricalMarketValue.objects.get(currency_id=key, date=current_date).value
            value_dict_toCNY[key] = float(value_dict[key]) * rate[currency_dict[key]['code']]
        else:
            value_dict[key] = 0
            value_dict_toCNY[key] = 0

    # 仓位计算
    position_percent_dict = {}
    fund_value_dict = {}
    market_value_dict = {}

    # 获取所有fund同时存在记录的最大有效日期
    # 获取所有不同的基金数量
    total_fund = FundHistory.objects.values('fund').distinct().count()
    # 查找所有日期及其对应的基金数量，并筛选出基金数等于总基金数的日期
    valid_dates = FundHistory.objects.values('date').annotate(
        fund_count=Count('fund', distinct=True)
    ).filter(fund_count=total_fund).order_by('-date')
    if valid_dates.exists():
        max_date_fund = valid_dates.first()['date']
    else:
        max_date_fund = None

    for key in currency_dict:
        fund_id = Fund.objects.get(currency_id=key).id
        fund_value_dict[key] = FundHistory.objects.get(fund_id=fund_id, date=max_date_fund).fund_value
        market_value_dict[key] = HistoricalMarketValue.objects.get(currency_id=key, date=max_date_fund).value
        position_percent_dict[key] = market_value_dict[key] / fund_value_dict[key]

    # 人民币基金的持仓比例通过511880的市值占比计算
    current_price, increase, color = get_quote_snowball('511880')  # 银华日利
    positions = Position.objects.filter(stock=93)  # 银华日利
    quantity = 0
    for pos in positions:
        quantity += pos.position_quantity
    cash_like_assets_CNY = current_price * quantity
    position_percent_dict[1] = 1 - cash_like_assets_CNY / amount_sum_CNY

    # updating_time = current_date
    updating_time = datetime.datetime.now()
    return render(request, templates_path + 'view_market_value.html', locals())


# 市值详情
def view_market_value_details(request, currency_id):
    currency_name = Currency.objects.get(id=currency_id).name
    # currency_dict = {1: '人民币', 2: '港元', 3: '美元'}
    # currency_dict = {}
    # keys = []
    # values = []
    # for rs in currency.objects.all():
    #     keys.append(rs.id)
    #     values.append(rs.name)
    # currency_dict = dict(zip(keys, values))

    result = HistoricalMarketValue.objects.aggregate(
        max_date=Max('date')  # 最大值（最新日期）
    )
    current_date = result['max_date']
    # if historical_market_value.objects.filter(currency=currency_dict[currency_id], date=current_date).exists():
    #     value = historical_market_value.objects.get(currency=currency_dict[currency_id], date=current_date).value
    # else:
    #     value = 0
    market_value_obj = HistoricalMarketValue.objects.get(currency_id=currency_id, date=current_date)

    today = datetime.date.today()  # 假设当前日期
    last_day_of_last_month = today.replace(day=1) - relativedelta(days=1)  # 上月最后一天
    last_day_of_last_year = datetime.date(today.year - 1, 12, 31)  # 上年最后一天

    # 获取上月最大日期
    last_month_max_date = HistoricalMarketValue.objects.filter(
        date__month=last_day_of_last_month.month,
        date__year=last_day_of_last_month.year,
        currency_id=currency_id
    ).aggregate(
        max_date=Max('date')
    )['max_date']

    # 按货币分组获取上年最大日期
    last_year_max_date = HistoricalMarketValue.objects.filter(
        date__year=last_day_of_last_year.year,
        currency_id=currency_id
    ).aggregate(
        max_date=Max('date')
    )['max_date']

    last_month_value = HistoricalMarketValue.objects.get(date=last_month_max_date, currency_id=currency_id).value
    month_change_amount = market_value_obj.value - last_month_value
    if last_month_value != Decimal('0.0000') and month_change_amount != Decimal('0.0000'):
        month_change_rate = month_change_amount / last_month_value
    else:
        month_change_rate = 0
    last_year_value = HistoricalMarketValue.objects.get(date=last_year_max_date, currency_id=currency_id).value
    year_change_amount = market_value_obj.value - last_year_value
    if last_year_value != Decimal('0.0000') and year_change_amount != Decimal('0.0000'):
        year_change_rate = year_change_amount / last_year_value
    else:
        year_change_rate = 0

    # 生成持仓市值曲线数据data
    data_market_value = []
    market_value_list = HistoricalMarketValue.objects.filter(currency_id=currency_id).order_by("date")
    for rs in market_value_list:
        date = str(rs.date)
        value = float(rs.value)
        data_market_value.append({
            "date": date,
            "value": value / 10000
        })

    # 生成市值变化日历字典数据assetChanges
    assetChanges = {}
    for rs in market_value_list:
        date = rs.date.strftime("%Y-%m-%d")
        amount = float(rs.change_amount)
        assetChanges[date] = amount

    # 获得近期市值列表
    market_value_list_TOP = HistoricalMarketValue.objects.filter(currency_id=currency_id).order_by("-date")[:12]
    # 获得近期交易列表
    # trade_list_TOP = trade.objects.filter(settlement_currency=currency_id).order_by('-trade_date', '-modified_time')[:10]
    trade_list_TOP = Trade.objects.filter(
        currency_id=currency_id
    ).select_related('stock').values(
        'trade_date',
        'stock_id',
        'stock__stock_code',
        'stock__stock_name'
    ).annotate(
        # 计算净交易金额（买入为负，卖出为正）
        net_amount=Sum(
            Case(
                When(trade_type=Trade.BUY, then=-F('trade_quantity') * F('trade_price')),
                When(trade_type=Trade.SELL, then=F('trade_quantity') * F('trade_price')),
                output_field=DecimalField(max_digits=12, decimal_places=3)
            )
        ),
        # 计算净交易量（买入增加，卖出减少）
        net_quantity=Sum(
            Case(
                When(trade_type=Trade.BUY, then=F('trade_quantity')),
                When(trade_type=Trade.SELL, then=-F('trade_quantity')),
                output_field=IntegerField()
            )
        ),
        # 获取组内最新修改时间
        latest_modified=Max('modified_time')
    ).order_by('-trade_date', '-latest_modified')[:12]

    updating_time = datetime.datetime.now()
    return render(request, templates_path + 'view_market_value_details.html', locals())


# 交易详情
def view_trade_details(request, currency_id):
    return render(request, templates_path + 'view_trade_details.html', locals())


# 分红概览
def view_dividend(request):
    rate = get_rate()
    currencies = Currency.objects.all()
    currency_dict = {c.id: {'code': c.code, 'name': c.name} for c in currencies}
    dividend_summary = []
    dividend_chart_data = []
    for key in currency_dict:
        currency_id = key
        currency_code = currency_dict[key]['code']
        currency_name = currency_dict[key]['name']
        total_amount = get_dividend_summary(currency_id)
        year_amount = get_dividend_current_year(currency_id)
        total_amount_toCNY = float(total_amount) * rate[currency_code]
        year_amount_toCNY = float(year_amount) * rate[currency_code]
        result = Dividend.objects.filter(currency=currency_id).aggregate(
            max_date=Max('dividend_date')  # 最大值（最新日期）
        )
        max_date = result['max_date']

        dividend_summary.append({
            'currency_id': currency_id,
            'currency_code': currency_code,
            'currency_name': currency_name,
            'total_amount': total_amount,
            'year_amount': year_amount,
            'max_date': max_date
        })
        dividend_chart_data.append({
            'currency_name': currency_name,
            'total_amount': total_amount_toCNY,
            'year_amount': year_amount_toCNY
        })

    result = calculate_dividend_data(0)
    year_array = result['year']  # 有效年份列表
    dividend_yearly_total_array = result['dividend_yearly_total']  # 各年合计分红列表
    market_value_yearly_avg_array = result['market_value_yearly_avg']  # 各年平均市值列表
    dividend_rate_yearly_array = [x * 100 for x in result['dividend_rate_yearly']]  # 各年分红率列表
    total_dividends = result['total_dividends']  # 总分红
    overall_avg_market_value = result['overall_avg_market_value']  # 整体平均市值
    avg_dividend_rate = result['avg_dividend_rate']  # 平均分红率（各年分红率的算术平均）

    updating_time = datetime.datetime.now()

    context = {
        "rate": rate,
        "dividend_summary": dividend_summary,
        "dividend_chart_data": dividend_chart_data,
        "year_array": year_array,
        "dividend_yearly_total_array": dividend_yearly_total_array,
        "market_value_yearly_avg_array": market_value_yearly_avg_array,
        "dividend_rate_yearly_array": dividend_rate_yearly_array,
        "total_dividends": total_dividends,
        "overall_avg_market_value": overall_avg_market_value,
        "avg_dividend_rate": avg_dividend_rate,
        "updating_time": updating_time
    }
    return render(request, templates_path + 'view_dividend.html', context)


# 分红详情
def view_dividend_details(request, currency_id):
    currency_name = Currency.objects.get(id=currency_id).name
    result = Dividend.objects.aggregate(
        max_date=Max('dividend_date')  # 最大值（最新日期）
    )
    current_date = result['max_date']

    # 1. 累计分红
    total_dividends = get_dividend_summary(currency_id)

    # 2. 年内分红
    year_dividends = get_dividend_current_year(currency_id)

    # 3. 上年分红
    dividends_avg_amount_1 = get_dividend_annual_average(currency_id, 1)
    dividends_in_past_year = get_dividend_in_past_year(currency_id)

    # 4. 近三年平均分红
    dividends_avg_amount_3 = get_dividend_annual_average(currency_id, 3)

    # 5. 近五年平均分红
    dividends_avg_amount_5 = get_dividend_annual_average(currency_id, 5)

    # 6. 近七年平均分红
    dividends_avg_amount_7 = get_dividend_annual_average(currency_id, 7)

    # 7.总分红率、平均分红率
    result = calculate_dividend_data(currency_id)
    # 正确计算总分红率
    if result['overall_avg_market_value']:
        # 总分红率 = 所有年份分红总额 ÷ 整体加权平均市值
        # 这里考虑了不同时间市值的权重分配
        dividend_rate_total = result['total_dividends'] / result['overall_avg_market_value']
    else:
        dividend_rate_total = Decimal('0.0')

    year_array = []
    dividend_yearly_total_array = []
    market_value_yearly_avg_array = []
    dividend_rate_yearly_array = []
    year_array = result['year']  # 有效年份列表
    dividend_yearly_total_array = result['dividend_yearly_total']  # 各年合计分红列表
    market_value_yearly_avg_array = result['market_value_yearly_avg']  # 各年平均市值列表
    dividend_rate_yearly_array = [x * 100 for x in result['dividend_rate_yearly']]  # 各年分红率列表
    total_dividends = result['total_dividends']  # 总分红
    overall_avg_market_value = result['overall_avg_market_value']  # 整体平均市值
    avg_dividend_rate = result['avg_dividend_rate']  # 平均分红率（各年分红率的算术平均）

    # 8.年内分红率
    dividend_rate_current_year = result['dividend_rate_yearly'][-1]

    # 9.上年分红率
    dividend_rate_pre_year = result['dividend_rate_yearly'][-2]

    # 获得近期分红列表
    dividend_list_TOP = Dividend.objects.filter(
        currency_id=currency_id
    ).select_related('stock').values(
        'dividend_date',
        'stock_id',  # 使用stock_id分组（或直接使用'stock'获取股票对象ID）
        'stock__stock_code',  # 股票代码
        'stock__stock_name'  # 股票名称
    ).annotate(
        total_dividend=Sum('dividend_amount'),  # 汇总分红金额
        latest_modified=Max('modified_time')  # 取组内最新修改时间
    ).order_by(
        '-dividend_date',
        '-latest_modified'  # 按最新修改时间倒序
    )[:10]

    # 获得分红图表数据
    current_year = datetime.datetime.now().year
    dividend_current_year = Dividend.objects.filter(
        dividend_date__year=current_year,
        currency_id=currency_id,
        currency__isnull=False  # 排除货币为空的记录
    ).values(
        stock_name=F('stock__stock_name')  # 股票名称
    ).annotate(
        total_dividend=Sum('dividend_amount'),  # 合并分红金额
    ).order_by(
        '-total_dividend'
    )
    name_current_year_list = []
    dividend_current_year_list = []
    for item in dividend_current_year:
        name_current_year_list.append(item['stock_name'])
        dividend_current_year_list.append(round(item['total_dividend']))

    dividend_total = Dividend.objects.filter(
        currency_id=currency_id,
        currency__isnull=False  # 排除货币为空的记录
    ).values(
        stock_name=F('stock__stock_name')  # 股票名称
    ).annotate(
        total_dividend=Sum('dividend_amount'),  # 合并分红金额
    ).order_by(
        '-total_dividend'
    )[:20]
    name_total_list = []
    dividend_total_list = []
    for item in dividend_total:
        name_total_list.append(item['stock_name'])
        dividend_total_list.append(round(item['total_dividend']))

    updating_time = datetime.datetime.now()

    return render(request, templates_path + 'view_dividend_details.html', locals())


# 股票详情
def view_stock_details(request, stock_id):
    # 1. 缓存汇率数据
    rate_key = f"exchange_rates_{stock_id}"
    rate_dict = cache.get(rate_key)
    if not rate_dict:
        # rate_HKD, rate_USD = get_rate()
        rate = get_rate()
        rate_HKD = rate['HKD']
        rate_USD = rate['USD']

        rate_dict = {1: 1, 2: rate_HKD, 3: rate_USD}
        cache.set(rate_key, rate_dict, 3600)  # 缓存1小时

    # 2. 预取相关对象，减少查询次数
    stock_obj = Stock.objects.select_related(
        'market', 'market__currency'
    ).prefetch_related(
        Prefetch('position_set', queryset=Position.objects.all()),
        Prefetch('trade_set', queryset=Trade.objects.all().order_by('-trade_date', '-modified_time')),
        Prefetch('dividend_set', queryset=Dividend.objects.all().order_by('-dividend_date', '-modified_time'))
    ).get(id=stock_id)

    # 3. 提取常用属性
    stock_name = stock_obj.stock_name
    stock_code = stock_obj.stock_code
    stock_market = stock_obj.market.market_name
    currency_id = stock_obj.market.currency_id
    currency_name = stock_obj.market.currency.name
    currency_unit = stock_obj.market.currency.unit

    # 4. 批量计算持仓量（单次查询替代多次查询）
    positions = stock_obj.position_set.all()
    position_quantity = positions.aggregate(total=Sum('position_quantity'))['total'] or 0

    # 5. 获取股票价格（考虑缓存）
    price, increase, color = get_stock_price(stock_code)
    increase_per = increase / 100

    # 6. 计算市值
    market_value = position_quantity * price * rate_dict[currency_id]

    # 7. 计算分红数据
    dividend_data = get_dividend_summary_by_currency(stock_id)
    dividend_CNY = float(dividend_data.get(1, 0))
    dividend_HKD = float(dividend_data.get(2, 0)) * rate_dict[2]
    dividend_USD = float(dividend_data.get(3, 0)) * rate_dict[3]
    dividend_total = calculate_total_dividend(dividend_data, rate_dict)

    # 8. 计算交易汇总（单次获取代替多次函数调用）
    trade_summary = calculate_stock_trade_summary(stock_id)

    def get_amount(cid, trade_type):
        return float(trade_summary.get(cid, {}).get(trade_type, 0.0))

    # 计算各种金额
    buy_amount_CNY = get_amount(1, 'buy')
    sell_amount_CNY = get_amount(1, 'sell')
    buy_amount_HKD = get_amount(2, 'buy')
    sell_amount_HKD = get_amount(2, 'sell')
    buy_amount_USD = get_amount(3, 'buy')
    sell_amount_USD = get_amount(3, 'sell')

    cost_CNY = buy_amount_CNY - sell_amount_CNY
    cost_HKD = buy_amount_HKD - sell_amount_HKD
    cost_USD = buy_amount_USD - sell_amount_USD
    cost_total = cost_CNY + cost_HKD + cost_USD

    buy_amount_total = buy_amount_CNY + buy_amount_HKD + buy_amount_USD
    sell_amount_total = sell_amount_CNY + sell_amount_HKD + sell_amount_USD

    profit = market_value - cost_total + dividend_total
    profit_rate = profit / buy_amount_total if buy_amount_total > 0 else 0

    # 9. 获取交易和分红列表（已通过预取）
    trade_list = stock_obj.trade_set.all()
    dividend_list = stock_obj.dividend_set.all()

    # 10. 获取年度分红金额列表
    # 初始化一个字典存储每年分红总额（人民币）
    annual_dividends = defaultdict(Decimal)

    # 遍历分红记录
    for dividend_obj in dividend_list:
        # 获取分红年份
        year = dividend_obj.dividend_date.year

        # 获取货币ID（如果currency为空则跳过）
        currency_id = dividend_obj.currency_id
        if currency_id is None:
            continue  # 跳过无货币的记录

        # 从汇率字典获取汇率（如果不存在则跳过）
        exchange_rate = rate_dict.get(currency_id)
        if exchange_rate is None:
            continue  # 跳过无汇率的记录

        # 将分红金额转换为人民币
        amount_rmb = dividend_obj.dividend_amount * Decimal(str(exchange_rate))

        # 累加到对应年份
        annual_dividends[year] += amount_rmb

    # 转换为按年份排序的列表
    sorted_annual_dividends = [
        {"year": year, "total_dividend_rmb": total}
        for year, total in sorted(annual_dividends.items())
    ]

    # 按年份排序并生成结构化数据
    sorted_annual_dividends = sorted([
        {"year": year, "total_dividend_rmb": total}
        for year, total in annual_dividends.items()
    ], key=lambda x: x['year'])

    # 生成两个独立列表（仅包括有分红的年度）
    years = [item['year'] for item in sorted_annual_dividends]
    dividends_rmb = [float(item['total_dividend_rmb']) for item in sorted_annual_dividends]

    # 从原始数据中获取最小和最大年份
    min_year = min(
        item['year'] for item in sorted_annual_dividends) if sorted_annual_dividends else datetime.datetime.today().year
    max_year = max(
        item['year'] for item in sorted_annual_dividends) if sorted_annual_dividends else datetime.datetime.today().year

    # 创建年份范围列表（连续年份）
    years_range = list(range(min_year, max_year + 1))

    # 创建字典映射年份到分红额
    dividend_dict = {item['year']: item['total_dividend_rmb'] for item in sorted_annual_dividends}

    # 生成完整年份列表（已排序）和对应分红额列表（缺失年份为0）
    years_complete = []
    years_complete = years_range
    dividends_complete = []
    dividends_complete = [float(dividend_dict.get(year, Decimal(0))) for year in years_range]

    updating_time = datetime.datetime.now()

    return render(request, templates_path + 'view_stock_details.html', locals())


# 交易录入
def input_trade(request):
    trade_type_items = (
        (1, '买'),
        (2, '卖'),
    )
    # settlement_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_active = Account.objects.filter(is_active=True)
    account_not_active = Account.objects.filter(is_active=False)
    stock_hold, stock_not_hold = get_stock_hold_or_not()

    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        trade_date = request.POST.get('trade_date')
        trade_type = request.POST.get('trade_type')
        trade_price = request.POST.get('trade_price')
        trade_quantity = request.POST.get('trade_quantity')
        currency_value = request.POST.get('currency')
        if stock_id.strip() == '':
            error_info = "股票不能为空！"
            return render(request, templates_path + 'input/input_trade.html', locals())
        try:
            # 新增一条交易记录
            p = Trade.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                trade_date=trade_date,
                trade_type=trade_type,
                trade_price=trade_price,
                trade_quantity=trade_quantity,
                currency_id=currency_value,
                filed_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            # 更新（删除）或新增一条仓位记录
            position_objects = Position.objects.filter(stock_id=stock_id, account_id=account_id)
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
                q = Position.objects.create(
                    account_id=account_id,
                    stock_id=stock_id,
                    position_quantity=trade_quantity,
                    # position_currency=settlement_currency
                    currency_id=currency_value
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
    # dividend_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_active = Account.objects.filter(is_active=True)
    account_not_active = Account.objects.filter(is_active=False)
    stock_hold, stock_not_hold = get_stock_hold_or_not()

    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        dividend_date = request.POST.get('dividend_date')
        dividend_amount = request.POST.get('dividend_amount')
        currency_value = request.POST.get('currency')
        if stock_id.strip() == '':
            return render(request, templates_path + 'input/input_dividend.html', locals())
        try:
            p = Dividend.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                dividend_date=dividend_date,
                dividend_amount=dividend_amount,
                currency_id=currency_value
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
    account_active = Account.objects.filter(is_active=True)
    account_not_active = Account.objects.filter(is_active=False)
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
            p = Subscription.objects.create(
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
    # 获取汇率（使用缓存）
    rate_cache_key = 'exchange_rates'
    rates = cache.get(rate_cache_key)
    if not rates:
        rates = {
            # 'HKD': get_single_rate('HKD'),
            # 'USD': get_single_rate('USD')
            # 'HKD': get_rate()[0],
            # 'USD': get_rate()[1]
            'HKD': get_rate()['HKD'],
            'USD': get_rate()['USD']
        }
        cache.set(rate_cache_key, rates, 3600)  # 缓存1小时

    rate_dict = {
        Currency.CNY_ID: 1,
        Currency.HKD_ID: rates['HKD'],
        Currency.USD_ID: rates['USD']
    }

    # 顺序处理三种货币
    results = {}
    positions = []
    currencies = [
        Currency.CNY_ID,
        Currency.HKD_ID,
        Currency.USD_ID
    ]

    for currency_id in currencies:
        currency_obj = Currency.objects.get(id=currency_id)
        try:
            # 直接调用仓位处理函数
            results[currency_id] = get_position_content(currency_id, rate_dict)
        except Exception as e:
            # 记录错误并创建空数据集
            logger.error(f"Error processing currency {currency_id}: {str(e)}")
            logger.exception("Details:")  # 记录完整堆栈信息

            # 返回空数据集避免页面崩溃
            results[currency_id] = {
                'position_content': [],
                'abbreviation_array': ["数据加载失败"],
                'account_num': 0,
                'stock_num': 0,
                'error': True
            }
        positions.append(
            {'code': currency_obj.code, 'name': currency_obj.name, 'data': results[currency_id]}
        )
    # 准备上下文
    # context = {
    #     'currencies': [
    #         {'code': 'CNY', 'name': '人民币', 'data': results.get(currency.CNY_ID)},
    #         {'code': 'HKD', 'name': '港元', 'data': results.get(currency.HKD_ID)},
    #         {'code': 'USD', 'name': '美元', 'data': results.get(currency.USD_ID)}
    #     ]
    # }
    context = {
        'positions': positions
    }

    return render(request, templates_path + 'stats/stats_position.html', context)


'''
def stats_position1(request):
    currency_CNY = 1
    currency_HKD = 2
    currency_USD = 3
    position_content_CNY, abbreviation_array_CNY, account_num_CNY, stock_num_CNY = get_position_content(currency_CNY)
    position_content_HKD, abbreviation_array_HKD, account_num_HKD, stock_num_HKD = get_position_content(currency_HKD)
    position_content_USD, abbreviation_array_USD, account_num_USD, stock_num_USD = get_position_content(currency_USD)
    cols_CNY = range(1, account_num_CNY + 3)
    cols_HKD = range(1, account_num_HKD + 3)
    cols_USD = range(1, account_num_USD + 3)
    return render(request, templates_path + 'stats/stats_position.html', locals())
'''


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
    currency_name = currency_items[currency - 1][1]
    condition_id = '11'
    price_array = []
    # rate_HKD, rate_USD = get_rate()
    rate = get_rate()
    rate_HKD = rate['HKD']
    rate_USD = rate['USD']

    if request.method == 'POST':
        caliber = int(request.POST.get('caliber'))
        currency = int(request.POST.get('currency'))
        currency_name = currency_items[currency - 1][1]
        condition_id = str(caliber) + str(currency)
        # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_increase_array中，以提高性能
        # stock_dict = position.objects.filter(position_currency=currency).values("stock").annotate(count=Count("stock")).values('stock__stock_code')
        stock_dict = Position.objects.filter(currency_id=currency).values("stock").annotate(
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
            content, amount_sum, name_array, value_array = get_value_stock_content(currency, price_array, rate_HKD,
                                                                                   rate_USD)
        elif caliber == 2:
            content, amount_sum, name_array, value_array = get_value_industry_content(currency, price_array, rate_HKD,
                                                                                      rate_USD)
        elif caliber == 3:
            content, amount_sum, name_array, value_array = get_value_market_content(currency, price_array, rate_HKD,
                                                                                    rate_USD)
        elif caliber == 4:
            content, amount_sum, name_array, value_array = get_value_account_content(currency, price_array, rate_HKD,
                                                                                     rate_USD)
        else:
            pass

    return render(request, templates_path + 'stats/stats_value.html', locals())


# 账户统计
def stats_account(request):
    domestic_accounts = Account.objects.all().filter(broker__broker_script='境内券商', is_active=True)
    overseas_accounts = Account.objects.all().filter(broker__broker_script='境外券商', is_active=True)
    account_abbreviation = '银河6811'
    # rate_HKD, rate_USD = get_rate()
    rate = get_rate()
    rate_HKD = rate['HKD']
    rate_USD = rate['USD']

    if request.method == 'POST':
        account_abbreviation = request.POST.get('account')
        account_id = Account.objects.get(account_abbreviation=account_abbreviation).id
        price_array = []
        # 将仓位表中涉及的股票的价格和涨跌幅一次性从数据库取出，存放在元组列表price_increase_array中，以提高性能
        stock_dict = Position.objects.filter(account=account_id).values("stock").annotate(
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
        stock_content, amount_sum, name_array, value_array = get_account_stock_content(account_id, price_array,
                                                                                       rate_HKD, rate_USD)
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
    # dividend_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    caliber = 1
    currency_value = 1
    currency_name = currency_items[currency_value - 1][1]
    condition_id = '11'
    if request.method == 'POST':
        caliber = int(request.POST.get('caliber'))
        currency_value = int(request.POST.get('currency'))
        currency_name = currency_items[currency_value - 1][1]
        condition_id = str(caliber) + str(currency_value)
        if caliber == 1:
            content, amount_sum, name_array, value_array = get_dividend_stock_content(currency_value)
        elif caliber == 2:
            content, amount_sum, name_array, value_array = get_dividend_year_content(currency_value)
        elif caliber == 3:
            content, amount_sum, name_array, value_array = get_dividend_industry_content(currency_value)
        elif caliber == 4:
            content, amount_sum, name_array, value_array = get_dividend_market_content(currency_value)
        elif caliber == 5:
            content, amount_sum, name_array, value_array = get_dividend_account_content(currency_value)
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
    type_name = subscription_type_items[subscription_type - 1][1]
    condition_id = '11'
    if request.method == 'POST':
        caliber = int(request.POST.get('caliber'))
        subscription_type = int(request.POST.get('subscription_type'))
        type_name = subscription_type_items[subscription_type - 1][1]
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
    # rate_HKD, rate_USD = get_rate()
    rate = get_rate()
    rate_HKD = rate['HKD']
    rate_USD = rate['USD']

    holding_profit_array = []
    cleared_profit_array = []
    holding_profit_sum = 0
    cleared_profit_sum = 0
    holding_value_sum = 0
    holding_stock_list = Stock.objects.filter(position__stock_id__isnull=False).distinct().order_by('stock_code')
    cleared_stock_list = Stock.objects.filter(position__stock_id__isnull=True,
                                              trade__stock_id__isnull=False).distinct().order_by('stock_code')
    for rs in holding_stock_list:
        stock_id = rs.id
        stock_code = rs.stock_code
        stock_name = rs.stock_name
        # transaction_currency = rs.market.transaction_currency
        currency_value = rs.market.currency
        trade_list = Trade.objects.all().filter(stock=stock_id)
        trade_array, amount_sum, value, quantity_sum, price_avg, price, profit, profit_margin, cost_sum = get_holding_stock_profit(
            stock_code)
        if currency_value == 2:
            profit *= rate_HKD
            value *= rate_HKD
        elif currency_value == 3:
            profit *= rate_USD
            value *= rate_USD
        holding_profit_sum += profit
        holding_value_sum += value
        holding_profit_array.append((stock_name, stock_code, profit, value))
    holding_profit_array.sort(key=lambda x: x[3], reverse=True)  # 对account_content列表按第3列（金额）降序排序
    for rs in cleared_stock_list:
        stock_id = rs.id
        stock_code = rs.stock_code
        stock_name = rs.stock_name
        # transaction_currency = rs.market.transaction_currency
        currency_value = rs.market.currency
        trade_list = Trade.objects.all().filter(stock=stock_id)
        if trade_list.exists() and stock_code != '-1':
            trade_array, profit, profit_margin, cost_sum = get_cleared_stock_profit(stock_code)
            if currency_value == 2:
                profit *= rate_HKD
            elif currency_value == 3:
                profit *= rate_USD
            cleared_profit_sum += profit
            cleared_profit_array.append((stock_name, stock_code, profit))
    return render(request, templates_path + 'stats/stats_profit.html', locals())


# 交易查询
def query_trade(request):
    stock_list = Stock.objects.all().values('stock_name', 'stock_code').order_by('stock_code')
    holding_stock_list = Stock.objects.filter(position__stock_id__isnull=False).distinct().values('stock_name',
                                                                                                  'stock_code').order_by(
        'stock_code')
    cleared_stock_list = Stock.objects.filter(position__stock_id__isnull=True,
                                              trade__stock_id__isnull=False).distinct().values('stock_name',
                                                                                               'stock_code').order_by(
        'stock_code')
    if request.method == 'POST':
        form_type = request.POST.get("form_type")
        form = None
        if form_type == 'holding_stock':
            stock_code = request.POST.get('stock_code')
            stock_name = Stock.objects.get(stock_code=stock_code).stock_name
            market = Stock.objects.get(stock_code=stock_code).market
            trade_array_1, amount_sum_1, value_1, quantity_sum_1, price_avg_1, price_1, profit_1, profit_margin_1, cost_sum_1 = get_holding_stock_profit(
                stock_code)
        elif form_type == 'cleared_stock':
            stock_code = request.POST.get('stock_code')
            stock_name = Stock.objects.get(stock_code=stock_code).stock_name
            market = Stock.objects.get(stock_code=stock_code).market
            trade_array_2, profit_2, profit_margin_2, cost_sum_2 = get_cleared_stock_profit(stock_code)
    return render(request, templates_path + 'query/query_trade.html', locals())


# 分红金额查询
def query_dividend_value(request):
    # dividend_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    stock_list = Stock.objects.all().values('stock_code', 'stock_name', 'last_dividend_date', 'next_dividend_date')
    # 持仓股票列表，通过.filter(dividend__stock_id__isnull = False)，过滤出在dividend表中存在的stock_id所对应的stock表记录
    dividends_stock_list = stock_list.filter(dividend__stock_id__isnull=False).distinct()
    # 分红年份列表，通过.dates('dividend_date', 'year')，过滤出dividend表中存在的dividend_date所对应的年份列表
    year_list = Dividend.objects.dates('dividend_date', 'year')
    # 按账号对应的券商备注（境内券商或境外券商）排序
    account_list = Account.objects.all().order_by('broker__broker_script')
    # 第一次进入页面，默认货币为人民币，账户全选、年份全选为否。
    currency_value = 1
    # 根据dividend_currency的值从dividend_currency_items中生成dividend_currency_name
    currency_name = currency_items[currency_value - 1][1]
    is_all_account_checked = "false"
    is_all_year_checked = "false"
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        # 由于stock_code为select列表而非文本框text，如果不选择则返回None而非空，所以不能使用stock_code.strip() == ''
        if stock_code is None:
            error_info = '股票不能为空！'
            return render(request, templates_path + 'query/query_dividend_value.html', locals())
        stock_object = Stock.objects.get(stock_code=stock_code)
        stock_id = stock_object.id
        stock_name = stock_object.stock_name
        dividend_year_list = request.POST.getlist('dividend_year_list')
        # 将列表中的字符串变成数字，方法一：
        dividend_year_list = [int(x) for x in dividend_year_list]
        dividend_account_list = request.POST.getlist('dividend_account_list')
        # 将列表中的字符串变成数字，方法二：使用内置map返回一个map对象，再用list将其转换为列表
        dividend_account_list = list(map(int, dividend_account_list))
        currency_value = int(request.POST.get('currency'))
        is_all_account_checked = request.POST.get('all_account')
        is_all_year_checked = request.POST.get('all_year')
        conditions = dict()
        conditions['stock'] = stock_id
        conditions['dividend_date__year__in'] = dividend_year_list
        conditions['account__in'] = dividend_account_list
        conditions['currency_id'] = currency_value
        dividend_list = Dividend.objects.all().filter(**conditions).order_by('-dividend_date')
        amount_sum = 0
        for i in dividend_list:
            amount_sum += i.dividend_amount
    # 根据dividend_currency的值从dividend_currency_items中生成dividend_currency_name
    currency_name = currency_items[currency_value - 1][1]
    return render(request, templates_path + 'query/query_dividend_value.html', locals())


# 分红日期查询
def query_dividend_date(request):
    current_year = datetime.datetime.today().year

    stock_list = Stock.objects.all().values('stock_name', 'stock_code', 'last_dividend_date',
                                            'next_dividend_date').order_by('stock_code')
    # 持仓股票列表，通过.filter(position__stock_id__isnull = False)，过滤出在position表中存在的stock_id所对应的stock表记录
    position_stock_list = stock_list.filter(position__stock_id__isnull=False).distinct().order_by('-next_dividend_date',
                                                                                                  '-last_dividend_date')
    # 当年已分红股票列表
    current_year_dividend_list = position_stock_list.filter(last_dividend_date__year=current_year).order_by(
        '-next_dividend_date', '-last_dividend_date')
    # 当年未分红股票列表
    current_year_no_dividend_list = position_stock_list.filter(next_dividend_date__year=current_year).order_by(
        '-next_dividend_date', '-last_dividend_date')

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
    stock_list = Stock.objects.all().values('stock_name', 'stock_code').order_by('stock_code')
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        stock_dividend_dict = get_stock_dividend_history(stock_code)
        stock_name = Stock.objects.get(stock_code=stock_code).stock_name
    return render(request, templates_path + 'query/query_dividend_history.html', locals())


# 货币表的增删改查
def add_currency(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        name = request.POST.get('name')
        unit = request.POST.get('unit')
        script = request.POST.get('script')
        if code.strip() == '':
            error_info = '货币代码不能为空！'
            return render(request, templates_path + 'backstage/add_currency.html', locals())
        try:
            p = Currency.objects.create(
                code=code,
                name=name,
                unit=unit,
                script=script
            )
            return redirect('/benben/list_currency/')
        except Exception as e:
            error_info = '输入货币代码重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_currency.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_currency.html', locals())


def del_currency(request, currency_id):
    currency_object = Currency.objects.get(id=currency_id)
    currency_object.delete()
    return redirect('/benben/list_currency/')


def edit_currency(request, currency_id):
    if request.method == 'POST':
        id = request.POST.get('id')
        code = request.POST.get('code')
        name = request.POST.get('name')
        unit = request.POST.get('unit')
        script = request.POST.get('script')
        currency_object = Currency.objects.get(id=id)
        try:
            currency_object.code = code
            currency_object.name = name
            currency_object.unit = unit
            currency_object.script = script
            currency_object.save()
        except Exception as e:
            error_info = '输入货币代码重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_currency.html', locals())
        finally:
            pass
        return redirect('/benben/list_currency/')
    else:
        currency_object = Currency.objects.get(id=currency_id)
        return render(request, templates_path + 'backstage/edit_currency.html', locals())


def list_currency(request):
    currency_list = Currency.objects.all()
    return render(request, templates_path + 'backstage/list_currency.html', locals())


# 券商表的增删改查
def add_broker(request):
    if request.method == 'POST':
        broker_name = request.POST.get('broker_name')
        broker_script = request.POST.get('broker_script')
        if broker_name.strip() == '':
            error_info = '券商名称不能为空！'
            return render(request, templates_path + 'backstage/add_broker.html', locals())
        try:
            p = Broker.objects.create(
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
    broker_object = Broker.objects.get(id=broker_id)
    broker_object.delete()
    return redirect('/benben/list_broker/')


def edit_broker(request, broker_id):
    if request.method == 'POST':
        id = request.POST.get('id')
        broker_name = request.POST.get('broker_name')
        broker_script = request.POST.get('broker_script')
        broker_object = Broker.objects.get(id=id)
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
        broker_object = Broker.objects.get(id=broker_id)
        return render(request, templates_path + 'backstage/edit_broker.html', locals())


def list_broker(request):
    broker_list = Broker.objects.all()
    return render(request, templates_path + 'backstage/list_broker.html', locals())


# 市场表的增删改查
def add_market(request):
    # transaction_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        market_name = request.POST.get('market_name')
        market_abbreviation = request.POST.get('market_abbreviation')
        currency_value = request.POST.get('currency')
        if market_name.strip() == '':
            error_info = '市场名称不能为空！'
            return render(request, templates_path + 'backstage/add_market.html', locals())
        try:
            p = Market.objects.create(
                market_name=market_name,
                market_abbreviation=market_abbreviation,
                currency_id=currency_value
            )
            return redirect('/benben/list_market/')
        except Exception as e:
            error_info = '输入市场名称重复或信息有错误！'
            return render(request, templates_path + 'backstage/add_market.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_market.html', locals())


def del_market(request, market_id):
    market_object = Market.objects.get(id=market_id)
    market_object.delete()
    return redirect('/benben/list_market/')


def edit_market(request, market_id):
    # transaction_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        id = request.POST.get('id')
        market_name = request.POST.get('market_name')
        market_abbreviation = request.POST.get('market_abbreviation')
        # transaction_currency = request.POST.get('transaction_currency')
        currency_value = request.POST.get('currency')  # 变量名为currency_value，以避免和表名currency混淆
        market_object = Market.objects.get(id=id)
        try:
            market_object.market_name = market_name
            market_object.market_abbreviation = market_abbreviation
            # market_object.transaction_currency = transaction_currency
            market_object.currency_id = currency_value  # 使用主键赋值（但需要通过赋值给currency_id字段，这是Django自动为ForeignKey字段创建的隐藏字段）
            market_object.save()
        except Exception as e:
            error_info = '输入市场名称重复或信息有错误！'
            return render(request, templates_path + 'backstage/edit_market.html', locals())
        finally:
            pass
        return redirect('/benben/list_market/')
    else:
        market_object = Market.objects.get(id=market_id)
        return render(request, templates_path + 'backstage/edit_market.html', locals())


def list_market(request):
    market_list = Market.objects.all()
    return render(request, templates_path + 'backstage/list_market.html', locals())


# 账户表的增删改查
def add_account(request):
    broker_list = Broker.objects.all().order_by('broker_script')
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
                p = Account.objects.create(
                    account_number=account_number,
                    broker_id=broker_id,
                    account_abbreviation=account_abbreviation,
                    is_active=True
                )
            else:
                p = Account.objects.create(
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
    account_object = Account.objects.get(id=account_id)
    account_object.delete()
    return redirect('/benben/list_account/')


def edit_account(request, account_id):
    broker_list = Broker.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_number = request.POST.get('account_number')
        broker_id = request.POST.get('broker_id')
        account_abbreviation = request.POST.get('account_abbreviation')
        is_active = request.POST.get('is_active')
        # print(is_active)
        account_object = Account.objects.get(id=id)
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
        account_object = Account.objects.get(id=account_id)
        return render(request, templates_path + 'backstage/edit_account.html', locals())


def list_account(request):
    account_list = Account.objects.all().order_by("-is_active", "broker")
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
            p = Industry.objects.create(
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
    industry_object = Industry.objects.get(id=industry_id)
    industry_object.delete()
    return redirect('/benben/list_industry/')


def edit_industry(request, industry_id):
    if request.method == 'POST':
        id = request.POST.get('id')
        industry_code = request.POST.get('industry_code')
        industry_name = request.POST.get('industry_name')
        industry_abbreviation = request.POST.get('industry_abbreviation')
        industry_object = Industry.objects.get(id=id)
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
        industry_object = Industry.objects.get(id=industry_id)
        return render(request, templates_path + 'backstage/edit_industry.html', locals())


def list_industry(request):
    industry_list = Industry.objects.all()
    return render(request, templates_path + 'backstage/list_industry.html', locals())


# 股票表的增删改查
def add_stock(request):
    market_list = Market.objects.all()
    industry_list = Industry.objects.all()
    if request.method == 'POST':
        stock_code = request.POST.get('stock_code')
        stock_name = request.POST.get('stock_name')
        industry_id = request.POST.get('industry_id')
        market_id = request.POST.get('market_id')
        if stock_code.strip() == '':
            error_info = '股票代码不能为空！'
            return render(request, templates_path + 'backstage/add_stock.html', locals())
        try:
            p = Stock.objects.create(
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
    stock_object = Stock.objects.get(id=stock_id)
    stock_object.delete()
    return redirect('/benben/list_stock/')


def edit_stock(request, stock_id):
    market_list = Market.objects.all()
    industry_list = Industry.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        stock_code = request.POST.get('stock_code')
        stock_name = request.POST.get('stock_name')
        industry_id = request.POST.get('industry_id')
        market_id = request.POST.get('market_id')
        stock_object = Stock.objects.get(id=id)
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
        stock_object = Stock.objects.get(id=stock_id)
        return render(request, templates_path + 'backstage/edit_stock.html', locals())


def list_stock(request):
    stock_list = Stock.objects.all()
    return render(request, templates_path + 'backstage/list_stock.html', locals())


# 持仓表增删改查
def add_position(request):
    account_list = Account.objects.all()
    stock_list = Stock.objects.all().order_by('stock_code')
    # position_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        position_quantity = request.POST.get('position_quantity')
        # position_currency = request.POST.get('position_currency')
        currency_value = request.POST.get('currency')
        if stock_id.strip() == '':
            error_info = '股票不能为空！'
            return render(request, templates_path + 'backstage/add_position.html', locals())
        try:
            p = Position.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                position_quantity=position_quantity,
                # position_currency=position_currency
                currency_id=currency_value
            )
            return redirect('/benben/list_position/')
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/add_position.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_position.html', locals())


def del_position(request, position_id):
    position_object = Position.objects.get(id=position_id)
    position_object.delete()
    return redirect('/benben/list_position/')


def edit_position(request, position_id):
    # position_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_list = Account.objects.all()
    stock_list = Stock.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        position_quantity = request.POST.get('position_quantity')
        # position_currency = request.POST.get('position_currency')
        currency_value = request.POST.get('currency')
        position_object = Position.objects.get(id=id)
        try:
            position_object.account_id = account_id
            position_object.stock_id = stock_id
            position_object.position_quantity = position_quantity
            # position_object.position_currency = position_currency
            position_object.currency_id = currency_value
            position_object.save()
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/edit_position.html', locals())
        finally:
            pass
        return redirect('/benben/list_position/')
    else:
        position_object = Position.objects.get(id=position_id)
        return render(request, templates_path + 'backstage/edit_position.html', locals())


def list_position(request):
    position_list = Position.objects.all()
    return render(request, templates_path + 'backstage/list_position.html', locals())


def add_historical_position(request):
    return render(request, templates_path + 'backstage/add_historical_position.html', locals())


def del_historical_position(request, historical_position_id):
    return redirect('/benben/list_historical_position/')


def edit_historical_position(request, historical_position_id):
    return render(request, templates_path + 'backstage/edit_historical_position.html', locals())


def list_historical_position(request):
    # historical_position_list = historical_position.objects.filter(date='2025-02-27')
    # historical_position_list = historical_position.objects.all()
    historical_position_list = HistoricalPosition.objects.order_by('-date')[:200]
    return render(request, templates_path + 'backstage/list_historical_position.html', locals())


# 交易表增删改查
def add_trade(request):
    trade_type_items = (
        (1, '买'),
        (2, '卖'),
    )
    # settlement_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_list = Account.objects.all()
    stock_list = Stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        trade_date = request.POST.get('trade_date')
        trade_type = request.POST.get('trade_type')
        trade_price = request.POST.get('trade_price')
        trade_quantity = request.POST.get('trade_quantity')
        currency_value = request.POST.get('currency')
        if stock_id.strip() == '':
            error_info = "股票不能为空！"
            return render(request, templates_path + 'backstage/add_trade.html', locals())
        try:
            p = Trade.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                trade_date=trade_date,
                trade_type=trade_type,
                trade_price=trade_price,
                trade_quantity=trade_quantity,
                currency_id=currency_value,
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
    trade_object = Trade.objects.get(id=trade_id)
    trade_object.delete()
    return redirect('/benben/list_trade/')


def edit_trade(request, trade_id):
    trade_type_items = (
        (1, '买'),
        (2, '卖'),
    )
    # settlement_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_list = Account.objects.all()
    stock_list = Stock.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        trade_date = request.POST.get('trade_date')
        trade_type = request.POST.get('trade_type')
        trade_price = request.POST.get('trade_price')
        trade_quantity = request.POST.get('trade_quantity')
        currency_value = request.POST.get('currency')
        trade_object = Trade.objects.get(id=id)
        try:
            trade_object.account_id = account_id
            trade_object.stock_id = stock_id
            trade_object.trade_date = trade_date
            trade_object.trade_type = trade_type
            trade_object.trade_price = trade_price
            trade_object.trade_quantity = trade_quantity
            trade_object.currency_id = currency_value
            trade_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_trade.html', locals())
        finally:
            pass
        return redirect('/benben/list_trade/')
    else:
        trade_object = Trade.objects.get(id=trade_id)
        return render(request, templates_path + 'backstage/edit_trade.html', locals())


def list_trade(request):
    trade_list = Trade.objects.all().order_by('-trade_date', '-modified_time')[:100]
    return render(request, templates_path + 'backstage/list_trade.html', locals())


# 分红表增删改查
def add_dividend(request):
    # dividend_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_list = Account.objects.all()
    stock_list = Stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        dividend_date = request.POST.get('dividend_date')
        dividend_amount = request.POST.get('dividend_amount')
        currency_value = request.POST.get('currency')
        if stock_id.strip() == '':
            error_info = '股票不能为空！'
            return render(request, templates_path + 'backstage/add_dividend.html', locals())
        try:
            p = Dividend.objects.create(
                account_id=account_id,
                stock_id=stock_id,
                dividend_date=dividend_date,
                dividend_amount=dividend_amount,
                currency_id=currency_value
            )
            return redirect('/benben/list_dividend/')
        except Exception as e:
            error_info = '输入信息有误！'
            return render(request, templates_path + 'backstage/add_dividend.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_dividend.html', locals())


def del_dividend(request, dividend_id):
    dividend_object = Dividend.objects.get(id=dividend_id)
    dividend_object.delete()
    return redirect('/benben/list_dividend/')


def edit_dividend(request, dividend_id):
    # dividend_currency_items = (
    #     (1, '人民币'),
    #     (2, '港元'),
    #     (3, '美元'),
    # )
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    account_list = Account.objects.all()
    stock_list = Stock.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        stock_id = request.POST.get('stock_id')
        dividend_date = request.POST.get('dividend_date')
        dividend_amount = request.POST.get('dividend_amount')
        currency_value = request.POST.get('currency')
        dividend_object = Dividend.objects.get(id=id)
        try:
            dividend_object.account_id = account_id
            dividend_object.stock_id = stock_id
            dividend_object.dividend_date = dividend_date
            dividend_object.dividend_amount = dividend_amount
            dividend_object.currency_id = currency_value
            dividend_object.save()
        except Exception as e:
            error_info = '输入信息有错误！'
            return render(request, templates_path + 'backstage/edit_dividend.html', locals())
        finally:
            pass
        return redirect('/benben/list_dividend/')
    else:
        dividend_object = Dividend.objects.get(id=dividend_id)
        return render(request, templates_path + 'backstage/edit_dividend.html', locals())


def list_dividend(request):
    dividend_list = Dividend.objects.all().order_by('-dividend_date', '-modified_time')
    return render(request, templates_path + 'backstage/list_dividend.html', locals())


# 打新表增删改查
def add_subscription(request):
    subscription_type_items = (
        (1, '股票'),
        (2, '可转债'),
    )
    account_list = Account.objects.all()
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
            p = Subscription.objects.create(
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
    subscription_object = Subscription.objects.get(id=subscription_id)
    subscription_object.delete()
    return redirect('/benben/list_subscription/')


def edit_subscription(request, subscription_id):
    subscription_type_items = (
        (1, '股票'),
        (2, '可转债'),
    )
    account_list = Account.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        account_id = request.POST.get('account_id')
        subscription_name = request.POST.get('subscription_name')
        subscription_date = request.POST.get('subscription_date')
        subscription_type = request.POST.get('subscription_type')
        subscription_quantity = request.POST.get('subscription_quantity')
        buying_price = request.POST.get('buying_price')
        selling_price = request.POST.get('selling_price')
        subscription_object = Subscription.objects.get(id=id)
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
        subscription_object = Subscription.objects.get(id=subscription_id)
        return render(request, templates_path + 'backstage/edit_subscription.html', locals())


def list_subscription(request):
    subscription_list = Subscription.objects.all().order_by('-subscription_date', '-modified_time')
    return render(request, templates_path + 'backstage/list_subscription.html', locals())


# 分红历史表增删改查
def add_dividend_history(request):
    stock_list = Stock.objects.all().order_by('stock_code')
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
            p = DividendHistory.objects.create(
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
    dividend_history_object = DividendHistory.objects.get(id=dividend_history_id)
    dividend_history_object.delete()
    return redirect('/benben/list_dividend_history/')


def edit_dividend_history(request, dividend_history_id):
    stock_list = Stock.objects.all().order_by('stock_code')
    if request.method == 'POST':
        id = request.POST.get('id')
        stock_id = request.POST.get('stock_id')
        reporting_period = request.POST.get('reporting_period')
        dividend_plan = request.POST.get('dividend_plan')
        announcement_date = request.POST.get('announcement_date')
        registration_date = request.POST.get('registration_date')
        ex_right_date = request.POST.get('ex_right_date')
        dividend_date = request.POST.get('dividend_date')
        dividend_history_object = DividendHistory.objects.get(id=id)
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
        dividend_history_object = DividendHistory.objects.get(id=dividend_history_id)
        return render(request, templates_path + 'backstage/edit_dividend_history.html', locals())


def list_dividend_history(request):
    dividend_history_list = DividendHistory.objects.all()
    return render(request, templates_path + 'backstage/list_dividend_history.html', locals())


# 基金表增删改查
def add_fund(request):
    baseline_list = Baseline.objects.all().order_by('currency_id', 'code')
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        fund_name = request.POST.get('fund_name')
        # fund_currency = request.POST.get('fund_currency')
        currency_value = request.POST.get('currency')
        fund_create_date = request.POST.get('fund_create_date')
        fund_value = request.POST.get('fund_value')
        fund_principal = request.POST.get('fund_principal')
        fund_PHR = request.POST.get('fund_PHR')
        fund_net_value = request.POST.get('fund_net_value')
        baseline_value = request.POST.get('baseline')
        fund_script = request.POST.get('fund_script')
        if fund_name.strip() == '':
            error_info = "基金名称不能为空！"
            return render(request, templates_path + 'backstage/add_fund.html', locals())
        try:
            p = Fund.objects.create(
                fund_name=fund_name,
                # fund_currency=fund_currency,
                currency_id=currency_value,
                fund_create_date=fund_create_date,
                fund_value=fund_value,
                fund_principal=fund_principal,
                fund_PHR=fund_PHR,
                fund_net_value=fund_net_value,
                baseline_id=baseline_value,
                fund_script=fund_script
            )
            return redirect('/benben/list_fund/')
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/add_fund.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_fund.html', locals())


def del_fund(request, fund_id):
    fund_object = Fund.objects.get(id=fund_id)
    fund_object.delete()
    return redirect('/benben/list_fund/')


def edit_fund(request, fund_id):
    baseline_list = Baseline.objects.all().order_by('currency_id', 'code')
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        id = request.POST.get('id')
        fund_name = request.POST.get('fund_name')
        # fund_currency = request.POST.get('fund_currency')
        currency_value = request.POST.get('currency')
        fund_create_date = request.POST.get('fund_create_date')
        fund_value = request.POST.get('fund_value')
        fund_principal = request.POST.get('fund_principal')
        fund_PHR = request.POST.get('fund_PHR')
        fund_net_value = request.POST.get('fund_net_value')
        baseline_value = request.POST.get('baseline')
        fund_script = request.POST.get('fund_script')
        fund_object = Fund.objects.get(id=id)
        try:
            fund_object.fund_name = fund_name
            # fund_object.fund_currency = fund_currency
            fund_object.currency_id = currency_value
            fund_object.fund_create_date = fund_create_date
            fund_object.fund_value = fund_value
            fund_object.fund_principal = fund_principal
            fund_object.fund_PHR = fund_PHR
            fund_object.fund_net_value = fund_net_value
            fund_object.baseline_id = baseline_value
            fund_object.fund_script = fund_script
            fund_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_fund.html', locals())
        finally:
            pass
        return redirect('/benben/list_fund/')
    else:
        fund_object = Fund.objects.get(id=fund_id)
        return render(request, templates_path + 'backstage/edit_fund.html', locals())


def list_fund(request):
    fund_list = Fund.objects.all().order_by('id')
    return render(request, templates_path + 'backstage/list_fund.html', locals())


# 基金明细表增删改查
def add_fund_history(request, fund_id):
    fund_list = Fund.objects.all()
    if request.method == 'POST':
        fund_id = request.POST.get('fund_id')
        date = datetime.datetime.strptime(request.POST.get('date'), "%Y-%m-%d").date()
        fund_value = request.POST.get('fund_value')
        fund_in_out = request.POST.get('fund_in_out')
        # fund_principal = request.POST.get('fund_principal')
        # fund_PHR = request.POST.get('fund_PHR')
        # fund_net_value = request.POST.get('fund_net_value')
        # fund_profit = request.POST.get('fund_profit')
        # fund_profit_rate = request.POST.get('fund_profit_rate')
        # fund_annualized_profit_rate = request.POST.get('fund_annualized_profit_rate')
        # print(fund_id,date,fund_value,fund_in_out)
        if fund_id.strip() == '':
            error_info = "基金名称不能为空！"
            return render(request, templates_path + 'backstage/add_fund_history.html', locals())
        try:
            fund_value = float(fund_value)
            fund_in_out = float(fund_in_out)
            latest_date = get_max_date(fund_id)
            earliest_date = Fund.objects.get(id=fund_id).fund_create_date  # 计算年化收益率的起始日期为基金的创立日期
            # earliest_date = get_min_date(fund_id)
            years = float((latest_date - earliest_date).days / 365)
            # print(latest_date,earliest_date,years)
            latest_fund_value = float(FundHistory.objects.get(fund_id=fund_id, date=latest_date).fund_value)
            latest_fund_principal = float(
                FundHistory.objects.get(fund_id=fund_id, date=latest_date).fund_principal)
            latest_fund_PHR = float(FundHistory.objects.get(fund_id=fund_id, date=latest_date).fund_PHR)
            latest_fund_net_value = float(
                FundHistory.objects.get(fund_id=fund_id, date=latest_date).fund_net_value)
            latest_fund_profit_rate = float(
                FundHistory.objects.get(fund_id=fund_id, date=latest_date).fund_profit_rate)
            # print(latest_date,earliest_date,years,latest_fund_principal,latest_fund_PHR)

            fund_principal = latest_fund_principal + fund_in_out
            if latest_fund_PHR == 0:  # 如果份数为0，则基金已经关闭，净值保持不变
                fund_net_value = latest_fund_net_value
            else:
                fund_net_value = (fund_value - fund_in_out) / latest_fund_PHR
            fund_PHR = fund_value / fund_net_value
            fund_current_profit = fund_value - fund_in_out - latest_fund_value
            fund_current_profit_rate = (fund_net_value - latest_fund_net_value) / latest_fund_net_value
            fund_profit = fund_value - fund_principal
            if latest_fund_PHR == 0:  # 如果份数为0，则基金已经关闭，累计收益率保持不变
                fund_profit_rate = latest_fund_profit_rate
            else:
                fund_profit_rate = fund_profit / fund_principal

            # print(latest_date,earliest_date,years,latest_fund_principal,latest_fund_PHR,fund_principal,fund_net_value,fund_PHR,fund_profit,fund_profit_rate)
            # print(date, earliest_date)
            years = float((date - earliest_date).days / 365)
            # print(years)
            fund_annualized_profit_rate = fund_net_value ** (1 / years) - 1
            # print(fund_annualized_profit_rate)
            # fund_annualized_profit_rate = (fund_net_value ** (1 / float(((latest_date - earliest_date).days) / 365)) - 1) * 100
            # print(latest_date,earliest_date,years,latest_fund_principal,latest_fund_PHR,fund_principal,fund_net_value,fund_PHR,fund_profit,fund_profit_rate,fund_annualized_profit_rate)
            # 插入一条基金明细记录
            p = FundHistory.objects.create(
                fund_id=fund_id,
                date=date,
                fund_value=fund_value,
                fund_in_out=fund_in_out,
                fund_principal=fund_principal,
                fund_PHR=fund_PHR,
                fund_net_value=fund_net_value,
                fund_current_profit=fund_current_profit,
                fund_current_profit_rate=fund_current_profit_rate,
                fund_profit=fund_profit,
                fund_profit_rate=fund_profit_rate,
                fund_annualized_profit_rate=fund_annualized_profit_rate
            )

            # 更新一条基金记录
            fund_object = Fund.objects.get(id=fund_id)
            fund_object.fund_value = fund_value
            fund_object.fund_principal = fund_principal
            fund_object.fund_PHR = fund_PHR
            fund_object.fund_net_value = fund_net_value
            fund_object.update_date = date
            fund_object.save()

            return redirect('/benben/list_fund_history/')
        except Exception as e:
            error_info = "输入信息有错误！"
            print(latest_date, earliest_date, latest_fund_principal, latest_fund_PHR, fund_principal,
                  fund_net_value, fund_PHR, fund_profit, fund_profit_rate, fund_annualized_profit_rate)
            return render(request, templates_path + 'backstage/add_fund_history.html', locals())
        finally:
            pass
    else:
        if fund_id != 0:
            fund_object = Fund.objects.get(id=fund_id)
        else:
            fund_object = Fund.objects.all()
    return render(request, templates_path + 'backstage/add_fund_history.html', locals())


def del_fund_history(request, fund_history_id):
    fund_history_object = FundHistory.objects.get(id=fund_history_id)
    fund_history_object.delete()
    return redirect('/benben/list_fund_history/')


def edit_fund_history(request, fund_history_id):
    fund_list = Fund.objects.all()
    if request.method == 'POST':
        id = request.POST.get('id')
        date = request.POST.get('date')
        fund_value = request.POST.get('fund_value')
        fund_in_out = request.POST.get('fund_in_out')
        fund_principal = request.POST.get('fund_principal')
        fund_PHR = request.POST.get('fund_PHR')
        fund_net_value = request.POST.get('fund_net_value')
        fund_profit = request.POST.get('fund_profit')
        fund_profit_rate = request.POST.get('fund_profit_rate')
        fund_annualized_profit_rate = request.POST.get('fund_annualized_profit_rate')
        fund_history_object = FundHistory.objects.get(id=id)
        try:
            fund_history_object.date = date
            fund_history_object.fund_value = fund_value
            fund_history_object.fund_in_out = fund_in_out
            fund_history_object.fund_principal = fund_principal
            fund_history_object.fund_PHR = fund_PHR
            fund_history_object.fund_net_value = fund_net_value
            fund_history_object.fund_profit = fund_profit
            fund_history_object.fund_profit_rate = fund_profit_rate
            fund_history_object.fund_annualized_profit_rate = fund_annualized_profit_rate
            fund_history_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_fund_history.html', locals())
        finally:
            pass
        return redirect('/benben/list_fund_history/')
    else:
        fund_history_object = FundHistory.objects.get(id=fund_history_id)
        return render(request, templates_path + 'backstage/edit_fund_history.html', locals())


def list_fund_history(request):
    fund_history_list = FundHistory.objects.all()
    return render(request, templates_path + 'backstage/list_fund_history.html', locals())


# 比较基准表增删改查
def add_baseline(request):
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        baseline_code = request.POST.get('code')
        baseline_name = request.POST.get('name')
        baseline_currency = request.POST.get('currency')
        baseline_script = request.POST.get('script')
        if baseline_code.strip() == '':
            error_info = " 代码不能为空！"
            return render(request, templates_path + 'backstage/add_baseline.html', locals())
        try:
            p = Baseline.objects.create(
                code=baseline_code,
                name=baseline_name,
                currency_id=baseline_currency,
                script=baseline_script
            )
            return redirect('/benben/list_baseline/')
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/add_baseline.html', locals())
        finally:
            pass
    return render(request, templates_path + 'backstage/add_baseline.html', locals())


def del_baseline(request, baseline_id):
    baseline_object = Baseline.objects.get(id=baseline_id)
    baseline_object.delete()
    return redirect('/benben/list_baseline/')


def edit_baseline(request, baseline_id):
    currency_items = ()
    keys = []
    values = []
    for rs in Currency.objects.all():
        keys.append(rs.id)
        values.append(rs.name)
    currency_items = tuple(zip(keys, values))
    if request.method == 'POST':
        id = request.POST.get('id')
        baseline_code = request.POST.get('code')
        baseline_name = request.POST.get('name')
        baseline_currency = request.POST.get('currency')
        baseline_script = request.POST.get('script')
        baseline_object = Baseline.objects.get(id=id)
        try:
            baseline_object.code = baseline_code
            baseline_object.name = baseline_name
            baseline_object.currency_id = baseline_currency
            baseline_object.script = baseline_script
            baseline_object.save()
        except Exception as e:
            error_info = "输入信息有错误！"
            return render(request, templates_path + 'backstage/edit_baseline.html', locals())
        finally:
            pass
        return redirect('/benben/list_baseline/')
    else:
        baseline_object = Baseline.objects.get(id=baseline_id)
        return render(request, templates_path + 'backstage/edit_baseline.html', locals())


def list_baseline(request):
    baseline_list = Baseline.objects.all().order_by('id')
    return render(request, templates_path + 'backstage/list_baseline.html', locals())


# 从网站中抓取数据导入数据库
def capture_dividend_history(request):
    stock_list = Stock.objects.all().values('stock_code', 'stock_name').order_by('stock_code')
    holding_stock_list = Position.objects.values("stock").annotate(count=Count("stock")).values('stock__stock_code')
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
            stock_object = Stock.objects.get(stock_code=stock_code)
            stock_id = stock_object.id
            stock_dividend_dict = get_stock_dividend_history(stock_code)
            next_dividend_date, last_dividend_date = get_dividend_date(stock_dividend_dict)
            count = 0
            try:
                # 删除dividend_history表中的相关记录
                # dividend_history_object = dividend_history.objects.get(stock_id = stock_id)
                DividendHistory.objects.filter(stock_id=stock_id).delete()

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
                    p = DividendHistory.objects.create(
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
    fund_list = Fund.objects.all()
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
            fund_id = request.POST.get('fund_id')
            fund_name = Fund.objects.get(id=fund_id).fund_name
            file_name = 'c:/gp/GP（' + fund_name + '）.xls'
            excel2fund(file_name, fund_name, -1, -1)
            print(form_name, fund_id, fund_name)
        else:
            pass
    return render(request, templates_path + 'other/batch_import.html', locals())  # 这里用'/'，‘//’或者‘/’代替'\'，防止'\b'被转义


# 更新历史持仓市值数据（historical_position、historical_rate、historical_market_value表）

# 全局变量，用于存储任务状态
task_status = {
    "current_step": 0,
    "total_steps": 8,
    "status": "idle",
    "message": "",
    "start_time": None,
    "end_time": None
}


def update_historical_market_value(request):
    # 获取初始日期范围
    result = HistoricalPosition.objects.aggregate(max_date=Max('date'))
    start_date = result['max_date'] - datetime.timedelta(days=30)
    end_date = datetime.date.today()

    steps = [
        ("生成历史持仓", generate_historical_positions, (start_date, end_date)),
        ("获取历史收盘价", get_historical_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
        ("补全历史收盘价", fill_missing_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
        ("获取今日价格", get_today_price, ()),
        ("获取历史汇率", get_historical_rate, (start_date, end_date)),
        ("补全历史汇率", fill_missing_historical_rates, ()),
        ("计算市场价值", calculate_market_value, (start_date, end_date)),
        ("计算并填充历史数据", calculate_and_fill_historical_data, (start_date, end_date))
    ]

    initial_steps = []
    for step in steps:
        initial_steps.append({
            "name": step[0],
            "start_time": None,
            "end_time": None,
            "status": "pending"
        })

    cache.set('task_status', {
        "current_step": 0,
        "total_steps": len(steps),
        "status": "running",
        "message": "任务开始执行",
        "start_time": timezone.now().isoformat(),
        "end_time": None,
        "steps": initial_steps  # 添加步骤时间记录
    }, timeout=3600)

    # 后台任务线程
    def background_task():
        steps = [
            ("生成历史持仓", generate_historical_positions, (start_date, end_date)),
            ("获取历史收盘价", get_historical_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
            ("补全历史收盘价", fill_missing_closing_price, (start_date, end_date - datetime.timedelta(days=1))),
            ("获取今日价格", get_today_price, ()),
            ("获取历史汇率", get_historical_rate, (start_date, end_date)),
            ("补全历史汇率", fill_missing_historical_rates, ()),
            ("计算市场价值", calculate_market_value, (start_date, end_date)),
            ("计算并填充历史数据", calculate_and_fill_historical_data, (start_date, end_date))
        ]

        try:
            for step_idx, (step_name, func, args) in enumerate(steps, 1):
                # 更新任务状态
                current_status = cache.get('task_status')
                # 记录步骤开始时间
                current_status['steps'][step_idx - 1]['start_time'] = timezone.now().isoformat()
                current_status['steps'][step_idx - 1]['status'] = 'running'
                cache.set('task_status', current_status)

                current_status.update({
                    "current_step": step_idx,
                    "current_step_name": step_name,
                    "step_status": "running",
                    "message": f"{step_name} - 执行中"
                })
                cache.set('task_status', current_status)

                # 模拟执行步骤（替换为实际函数调用）
                # time.sleep(0.1)
                func(*args)  # 实际执行任务步骤

                # 记录步骤结束时间
                current_status = cache.get('task_status')
                current_status['steps'][step_idx - 1]['end_time'] = timezone.now().isoformat()
                current_status['steps'][step_idx - 1]['status'] = 'completed'
                cache.set('task_status', current_status)

                # 更新步骤状态为"完成"
                current_status.update({
                    "step_status": "completed",
                    "message": f"{step_name} - 完成"
                })
                cache.set('task_status', current_status)

            # 新增：所有步骤完成后更新任务状态为completed
            current_status = cache.get('task_status')
            current_status.update({
                "status": "completed",
                "message": "所有步骤执行完成",
                "end_time": timezone.now().isoformat()
            })
            cache.set('task_status', current_status)

        except Exception as e:
            # 任务失败处理
            current_status = cache.get('task_status')
            current_status.update({
                "status": "failed",
                "message": f"任务失败: {str(e)}",
                "end_time": timezone.now().isoformat()
            })
            cache.set('task_status', current_status)

    # 启动后台线程
    threading.Thread(target=background_task).start()

    return render(request, templates_path + 'other/update_historical_market_value.html')


def get_task_status(request):
    status = cache.get('task_status', {})
    # print("[DEBUG] 当前任务状态:", status)  # 查看后端实际数据
    # 添加状态终结判断
    if status.get('current_step', 0) >= status.get('total_steps', 8):
        status['status'] = 'completed'
    # 从缓存获取状态，不存在则返回默认
    status = cache.get('task_status', {
        "current_step": 0,
        "total_steps": 8,
        "status": "idle",
        "message": "",
        "start_time": None,
        "end_time": None
    })

    # 计算总耗时
    total_duration = 0
    if status.get('start_time'):
        start_time = timezone.datetime.fromisoformat(status['start_time'])
        if status.get('end_time'):
            end_time = timezone.datetime.fromisoformat(status['end_time'])
            total_duration = (end_time - start_time).total_seconds()
        else:
            total_duration = (timezone.now() - start_time).total_seconds()

    # 新增：计算每个步骤的持续时间
    steps = status.get('steps', [])
    for step in steps:
        start = step.get('start_time')
        end = step.get('end_time')
        duration = 0
        if start:
            start_dt = timezone.datetime.fromisoformat(start)
            if end:
                end_dt = timezone.datetime.fromisoformat(end)
                duration = (end_dt - start_dt).total_seconds()
            else:
                duration = (timezone.now() - start_dt).total_seconds()
        step['duration'] = duration

    return JsonResponse({
        "current_step": status["current_step"],
        "total_steps": status["total_steps"],
        "status": status["status"],
        "message": status["message"],
        "duration": total_duration,
        "steps": steps  # 新增步骤数据
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
        # 初始化持仓缓存 {(stock_id, currency_id): quantity}
        position_cache = defaultdict(int)
        process_start = start_date
        date_sequence = []

        # 1. 检查并加载初始持仓
        initial_positions = HistoricalPosition.objects.filter(date=start_date)
        if initial_positions.exists():
            # 加载初始持仓（过滤零持仓）
            for pos in initial_positions.exclude(quantity=0):
                # 修改点1：使用 currency_id 替代 currency
                key = (pos.stock_id, pos.currency_id)
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
        relevant_trades = Trade.objects.filter(
            trade_date__gte=process_start,
            trade_date__lte=end_date
        ).order_by('trade_date').values(
            'trade_date', 'stock_id',
            'currency_id', 'trade_type',  # 修改点2：使用 currency_id
            'trade_quantity'
        )

        # 4. 按日期处理交易生成持仓
        new_positions = []
        for processing_date in date_sequence:
            # 当日交易分组汇总
            daily_trades = defaultdict(lambda: {'buy': 0, 'sell': 0})
            for t in relevant_trades:
                if t['trade_date'] == processing_date:
                    # 修改点3：使用 currency_id
                    key = (t['stock_id'], t['currency_id'])
                    if t['trade_type'] == Trade.BUY:
                        daily_trades[key]['buy'] += t['trade_quantity']
                    else:
                        daily_trades[key]['sell'] += t['trade_quantity']

            # 计算当日持仓变化
            temp_cache = defaultdict(int)
            temp_cache.update(position_cache)  # 继承前一日持仓

            # 处理每个股票+货币组合
            for (stock_id, currency_id), amounts in daily_trades.items():
                net_change = amounts['buy'] - amounts['sell']
                new_quantity = temp_cache[(stock_id, currency_id)] + net_change

                if new_quantity != 0:
                    temp_cache[(stock_id, currency_id)] = new_quantity
                else:
                    # 清除零持仓
                    del temp_cache[(stock_id, currency_id)]

            # 更新持仓缓存
            position_cache = temp_cache

            # 生成当日记录（过滤零持仓）
            for (stock_id, currency_id), quantity in position_cache.items():
                # 修改点4：使用 currency_id 替代 currency
                new_positions.append(HistoricalPosition(
                    date=processing_date,
                    stock_id=stock_id,
                    currency_id=currency_id,
                    quantity=quantity,
                    created_time=timezone.now(),
                    modified_time=timezone.now()
                ))

        # 5. 清理旧数据并保存新记录
        if date_sequence:
            # 删除可能存在的旧记录
            HistoricalPosition.objects.filter(
                date__gte=process_start,
                date__lte=end_date
            ).delete()

            # 批量插入新记录
            HistoricalPosition.objects.bulk_create(new_positions)
            print(f"[SUCCESS] 生成 {len(new_positions)} 条记录（{process_start} 至 {end_date}）")
            return len(new_positions)

        print("[INFO] 没有需要处理的日期范围")
        return 0


# 从akshare获取股票历史收盘价
def get_historical_closing_price(start_date, end_date):
    """获取并更新历史收盘价"""
    print(f"开始获取历史收盘价: {start_date} 至 {end_date}")
    start_time = time.time()

    # 获取所有需要更新的日期和股票
    positions = HistoricalPosition.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).select_related('stock', 'stock__market')

    # 按股票分组
    stock_groups = defaultdict(list)
    for position in positions:
        stock_groups[position.stock].append(position.date)

    # 获取所有唯一股票和日期
    all_stocks = list(stock_groups.keys())
    all_dates = set(date for dates in stock_groups.values() for date in dates)

    if not all_stocks:
        print("没有需要更新的记录")
        return

    # 按市场分组股票
    market_groups = defaultdict(list)
    for stock in all_stocks:
        market_groups[stock.market.market_name].append(stock)

    # 准备存储所有价格数据
    all_price_data = {}

    # 处理港股 - 使用多线程
    if '港股' in market_groups:
        print(f"处理 {len(market_groups['港股'])} 只港股")
        hk_stocks = market_groups['港股']
        hk_price_data = get_hk_historical_prices(hk_stocks, min(all_dates), max(all_dates))
        all_price_data.update(hk_price_data)

    # 处理美股
    if '美股' in market_groups:
        print(f"处理 {len(market_groups['美股'])} 只美股")
        us_stocks = market_groups['美股']
        us_price_data = get_us_historical_prices(us_stocks, min(all_dates), max(all_dates))
        all_price_data.update(us_price_data)

    # 处理其他市场
    other_markets = [m for m in market_groups.keys() if m not in ['港股', '美股']]
    for market in other_markets:
        print(f"处理 {len(market_groups[market])} 只{market}股票")
        stocks = market_groups[market]
        other_price_data = get_other_historical_prices(stocks, min(all_dates), max(all_dates))
        all_price_data.update(other_price_data)

    # 批量更新所有记录
    update_all_closing_prices(all_price_data)

    end_time = time.time()
    print(f"历史收盘价更新完成，耗时: {(end_time - start_time):.2f}秒")


def get_hk_historical_prices(stocks, start_date, end_date):
    """获取港股历史价格 - 使用多线程"""
    price_data = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for stock in stocks:
            futures.append(executor.submit(
                get_single_hk_stock_price,
                stock,
                start_date,
                end_date
            ))

        # 处理完成的任务
        for future in as_completed(futures):
            stock_code, prices = future.result()
            if prices:
                price_data[stock_code] = prices

    return price_data


def get_single_hk_stock_price(stock, start_date, end_date):
    """获取单只港股历史价格"""
    prices = {}
    stock_code = stock.stock_code

    try:
        # 港股历史行情接口
        df = ak.stock_hk_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust=""
        )

        if not df.empty:
            df['日期'] = pd.to_datetime(df['日期'])
            for _, row in df.iterrows():
                date = row['日期'].date()
                price = row['收盘']
                prices[date] = price
        print(f"获取港股 {stock_code} 价格成功！")
    except Exception as e:
        print(f"获取港股 {stock_code} 价格失败: {str(e)}")

    return stock_code, prices


def get_us_historical_prices(stocks, start_date, end_date):
    """获取美股历史价格"""
    price_data = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for stock in stocks:
            futures.append(executor.submit(
                get_single_us_stock_price,
                stock,
                start_date,
                end_date
            ))

        # 处理完成的任务
        for future in as_completed(futures):
            stock_code, prices = future.result()
            if prices:
                price_data[stock_code] = prices

    return price_data


def get_single_us_stock_price(stock, start_date, end_date):
    """获取单个美股历史价格"""
    prices = {}
    stock_code = stock.stock_code

    try:
        df = ak.stock_us_daily(symbol=stock_code, adjust="")
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])

            # 修复日期比较问题：将日期转换为相同的类型
            start_date_pd = pd.Timestamp(start_date)
            end_date_pd = pd.Timestamp(end_date)

            # 过滤日期范围
            df = df[(df['date'] >= start_date_pd) & (df['date'] <= end_date_pd)]

            for _, row in df.iterrows():
                date = row['date'].date()
                price = row['close']
                prices[date] = price
        print(f"获取美股 {stock_code} 价格成功！")
    except Exception as e:
        print(f"获取美股 {stock_code} 价格失败: {str(e)}")

    return stock_code, prices


def get_other_historical_prices(stocks, start_date, end_date):
    """获取其他市场历史价格"""
    price_data = {}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for stock in stocks:
            futures.append(executor.submit(
                get_single_other_stock_price,
                stock,
                start_date,
                end_date
            ))

        # 处理完成的任务
        for future in as_completed(futures):
            stock_code, prices = future.result()
            if prices:
                price_data[stock_code] = prices

    return price_data


def get_single_other_stock_price(stock, start_date, end_date):
    """获取单个其他市场股票历史价格"""
    prices = {}
    market_name = stock.market.market_name
    market_abbreviation = stock.market.market_abbreviation
    stock_code = stock.stock_code

    try:
        if market_name in ['沪市B股', '深市B股']:
            symbol = market_abbreviation + stock_code
            df = ak.stock_zh_b_daily(
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=""
            )
        elif classify_stock_code(stock_code) == 'ETF':
            symbol = market_abbreviation + stock_code
            df = ak.stock_zh_index_daily(symbol=symbol)
        elif classify_stock_code(stock_code) == '企业债':
            symbol = market_abbreviation + stock_code
            df = ak.bond_zh_hs_daily(symbol=symbol)
        else:
            symbol = market_abbreviation + stock_code
            df = ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust=""
            )

        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])

            # 修复日期比较问题：将日期转换为相同的类型
            start_date_pd = pd.Timestamp(start_date)
            end_date_pd = pd.Timestamp(end_date)

            # 过滤日期范围
            df = df[(df['date'] >= start_date_pd) & (df['date'] <= end_date_pd)]

            for _, row in df.iterrows():
                date = row['date'].date()
                price = row['close']
                prices[date] = price
        print(f"获取股票 {stock_code} 价格成功！")
    except Exception as e:
        print(f"获取股票 {stock_code} 价格失败: {str(e)}")

    return stock_code, prices


def update_all_closing_prices(price_data):
    """批量更新所有收盘价"""
    if not price_data:
        print("没有获取到价格数据")
        return

    # 准备所有需要更新的记录
    records_to_update = []
    updated_count = 0

    # 按日期和股票分组价格数据
    date_stock_map = defaultdict(dict)
    for stock_code, prices in price_data.items():
        for date, price in prices.items():
            date_stock_map[date][stock_code] = price

    # 按日期批量查询和更新
    for date, stock_prices in date_stock_map.items():
        stock_codes = list(stock_prices.keys())
        positions = HistoricalPosition.objects.filter(
            date=date,
            stock__stock_code__in=stock_codes
        ).select_related('stock')

        for position in positions:
            stock_code = position.stock.stock_code
            if stock_code in stock_prices:
                position.closing_price = stock_prices[stock_code]
                records_to_update.append(position)
                updated_count += 1

    # 批量更新
    if records_to_update:
        try:
            with transaction.atomic():
                HistoricalPosition.objects.bulk_update(records_to_update, ['closing_price'])
                print(f"成功更新 {updated_count} 条历史收盘价格记录")
        except Exception as e:
            print(f"历史收盘价格更新失败: {str(e)}")
    else:
        print("没有需要更新的记录")


# 补充akshare数据中缺失的收盘价
def fill_missing_closing_price(start_date, end_date):
    with transaction.atomic():
        # 获取指定日期范围内收盘价为0的所有记录
        records = HistoricalPosition.objects.filter(
            date__range=(start_date, end_date),
            closing_price=0
        )

        updates = []
        count = 0

        for record in records:
            # 查找同一股票和货币的最近有效收盘价记录
            prev_entry = HistoricalPosition.objects.filter(
                stock=record.stock,
                currency_id=record.currency_id,
                date__lt=record.date,
                closing_price__gt=0
            ).order_by('-date').first()

            if prev_entry:
                record.closing_price = prev_entry.closing_price
                updates.append(record)
                count += 1

        # 批量更新记录
        if updates:
            HistoricalPosition.objects.bulk_update(updates, ['closing_price'])

        print(f"补全了 {count} 条缺失的收盘价格")

        return


def get_today_price():
    current_date = datetime.date.today()
    # 找到最近的工作日
    while current_date.weekday() >= 5:
        current_date -= datetime.timedelta(days=1)

    # 一次性获取所有需要更新的股票信息
    positions = HistoricalPosition.objects.filter(date=current_date).select_related('stock')

    # 按股票分组
    stock_groups = defaultdict(list)
    stock_codes = set()

    for position in positions:
        stock_groups[position.stock.stock_code].append(position)
        stock_codes.add(position.stock.stock_code)

    # 批量获取所有股票价格 - 使用批量查询函数
    stock_code_list = list(stock_codes)
    quote_results = get_quote_array_snowball(stock_code_list)

    # 创建股票代码到价格的映射字典
    stock_prices = {result[0]: result[1] for result in quote_results}

    # 准备批量更新
    records_to_update = []
    for stock_code, positions_list in stock_groups.items():
        price = stock_prices.get(stock_code)
        if price is None:
            continue

        for position in positions_list:
            position.closing_price = price
            records_to_update.append(position)

    # 一次性批量更新所有记录
    if records_to_update:
        try:
            with transaction.atomic():
                HistoricalPosition.objects.bulk_update(records_to_update, ['closing_price'])
                print(f"成功更新 {len(records_to_update)} 条当日价格数据！")
        except Exception as e:
            print(f"当日价格更新失败: {str(e)}")
    else:
        print("没有需要更新的记录")


# 从akshare获取历史汇率
def get_historical_rate(start_date, end_date):
    start_date_str = start_date.strftime("%Y%m%d") if start_date else ""
    end_date_str = end_date.strftime("%Y%m%d") if end_date else ""

    # +++ 修改点1：获取货币对象 +++
    currency_hkd = Currency.objects.get(name='港元')
    currency_usd = Currency.objects.get(name='美元')

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
        # +++ 修改点2：传递货币对象代替货币名称 +++
        update_historical_rate(df_hkd, currency_hkd, start_date, end_date)
        print("历史汇率（港元）写入成功！")
        update_historical_rate(df_usd, currency_usd, start_date, end_date)
        print("历史汇率（美元）写入成功！")
    except Exception as e:
        print(f"历史汇率写入失败: {str(e)}")

    return


# +++ 修改点3：update_historical_rate 函数参数改为货币对象 +++
def update_historical_rate(df: pd.DataFrame, currency_obj, start_date, end_date) -> None:
    required_columns = ['日期', '中行汇买价']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"DataFrame 必须包含列: {required_columns}")

    # 转换日期列为 datetime.date 类型
    df['日期'] = pd.to_datetime(df['日期']).dt.date

    # 准备模型实例列表
    instances = [
        HistoricalRate(
            date=row['日期'],
            # +++ 修改点4：使用货币对象而不是名称 +++
            currency=currency_obj,
            rate=row['中行汇买价'] / 100
        )
        for _, row in df.iterrows()
    ]

    # 原子操作：删除旧数据 + 插入新数据
    with transaction.atomic():
        # 删除该货币所有旧数据
        HistoricalRate.objects.filter(
            # +++ 修改点5：使用货币对象替代名称 +++
            currency=currency_obj,
            date__gte=start_date,
            date__lte=end_date
        ).delete()
        # 批量写入新数据
        HistoricalRate.objects.bulk_create(instances)


# 补充akshare数据中缺失的日期
def fill_missing_historical_rates():
    """
    自动补全historical_rate表中缺失的汇率记录
    返回补全记录数量和错误信息列表
    """
    # --- 删除以下部分 ---
    # 获取所有货币及其ID映射 {currency_id: currency_name}
    # currency_map = {
    #     currency_obj.id: currency_obj.name
    #     for currency_obj in currency.objects.all()
    # }

    # 获取需要补全的日期和货币组合
    # +++ 修改点1：直接查询 currency_id 不转换为名称 +++
    positions = HistoricalPosition.objects.values('date', 'currency_id').distinct()

    # 获取已存在的汇率记录
    existing_rates = HistoricalRate.objects.filter(
        # +++ 修改点2：直接使用 currency_id 过滤 +++
        Q(date__in=[pos['date'] for pos in positions]) &
        Q(currency_id__in=[pos['currency_id'] for pos in positions])
    ).values_list('date', 'currency_id')  # +++ 修改点3：获取 currency_id +++

    existing_set = set(existing_rates)

    # 确定需要补全的组合
    missing_combinations = [
        (pos['date'], pos['currency_id'])
        for pos in positions
        # +++ 修改点4：直接使用 date 和 currency_id 组合 +++
        if (pos['date'], pos['currency_id']) not in existing_set
    ]

    # 按货币分组处理
    currency_date_map = defaultdict(list)
    for date, currency_id in missing_combinations:
        currency_date_map[currency_id].append(date)

    # 补全记录存储
    new_rates = []
    errors = []

    # 为每个货币处理缺失日期
    for currency_id, dates in currency_date_map.items():
        # 获取该货币所有历史记录
        # +++ 修改点5：按 currency_id 而不是名称查询 +++
        currency_rates = HistoricalRate.objects.filter(currency_id=currency_id) \
            .order_by('-date').values('date', 'rate')

        if not currency_rates:
            # +++ 修改点6：错误信息显示货币ID +++
            errors.append(f"货币ID {currency_id} 没有历史汇率记录")
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
                    new_rates.append(HistoricalRate(
                        date=target_date,
                        # +++ 修改点7：直接设置 currency_id +++
                        currency_id=currency_id,
                        rate=rate_dict[current_date],
                        modified_time=timezone.now()
                    ))
                    found = True
                    break
                # 没有则继续向前查找
                current_date -= timezone.timedelta(days=1)

            if not found:
                # +++ 修改点8：错误信息显示货币ID +++
                errors.append(f"货币ID {currency_id} 在 {target_date} 前30天无可用汇率")

    # 批量插入新记录
    if new_rates:
        HistoricalRate.objects.bulk_create(new_rates)

    print(f"补全了 {len(new_rates)} 条记录")
    return len(new_rates), errors


# 计算历史持仓市值
def calculate_market_value(start_date, end_date):
    """
    生成历史市值数据并写入 historical_market_value 表
    """
    try:
        # 使用原子事务保证数据一致性
        with transaction.atomic():
            # 1. 清空历史市值表
            HistoricalMarketValue.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).delete()

            # 2. 预加载汇率数据（日期范围 + 货币）
            rate_records = HistoricalRate.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).values('date', 'currency_id', 'rate')  # +++ 修改点1：添加 currency_id +++

            # +++ 修改点2：构建 {(date, currency_id): rate} 的快速查询字典 +++
            rate_dict = {
                (r['date'], r['currency_id']): r['rate']
                for r in rate_records
            }

            # 4. 获取所有持仓记录并按日期分组
            positions = HistoricalPosition.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).select_related('stock')

            # 构建日期到持仓记录的映射
            date_positions = defaultdict(list)
            for pos in positions:
                date_positions[pos.date].append(pos)

            # 6. 计算每日市值
            market_values = []
            current_date = start_date
            while current_date <= end_date:

                # 获取当日所有持仓记录
                daily_positions = date_positions.get(current_date, [])

                # 按货币计算市值总和
                # +++ 修改点3：使用 currency_id 作为键 +++
                currency_totals = defaultdict(Decimal)
                for pos in daily_positions:
                    # 使用货币ID
                    currency_id = pos.currency_id

                    # 6.2 获取汇率（人民币特殊处理）
                    # 如持仓货币为人民币且股票市场为港股，则为港股通持仓，需按港元汇率计算人民币市值
                    # +++ 修改点4：直接比较 currency_id +++
                    if currency_id == Currency.objects.get(name='人民币').id and pos.stock.market.currency_id == 2:
                        # +++ 修改点5：使用港元 currency_id 获取汇率 +++
                        hkd_currency_id = Currency.objects.get(name='港元').id
                        exchange_rate = rate_dict.get((current_date, hkd_currency_id), Decimal(1))
                    else:
                        exchange_rate = Decimal(1)

                    # 6.3 计算单股票市值
                    stock_value = pos.quantity * pos.closing_price * exchange_rate
                    # +++ 修改点6：使用 currency_id 累加 +++
                    currency_totals[currency_id] += stock_value

                # 7. 生成该日期的所有货币记录
                # +++ 修改点7：使用 currency_id 而不是名称 +++
                for currency_id, total in currency_totals.items():
                    market_values.append(
                        HistoricalMarketValue(
                            date=current_date,
                            # 直接设置 currency_id
                            currency_id=currency_id,
                            value=total
                        )
                    )

                # 移至下一天
                current_date += datetime.timedelta(days=1)

            # 8. 批量写入数据库
            HistoricalMarketValue.objects.bulk_create(market_values)
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
        currencies = HistoricalMarketValue.objects.values_list(
            'currency', flat=True
        ).distinct()

        # 逐货币补全数据
        for currency in currencies:
            # 获取该货币在指定范围内的现有日期
            existing_dates = set(
                HistoricalMarketValue.objects.filter(
                    currency=currency,
                    date__range=(start_date, end_date)
                ).values_list('date', flat=True)
            )

            # 计算缺失日期
            missing_dates = [day for day in workdays if day not in existing_dates]

            # 批量创建记录（新补全记录的初始值后续会更新）
            if missing_dates:
                HistoricalMarketValue.objects.bulk_create([
                    HistoricalMarketValue(
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
        queryset = HistoricalMarketValue.objects.annotate(
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
                has_previous = HistoricalMarketValue.objects.filter(
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
                            prev_val = HistoricalMarketValue.objects.get(
                                currency=obj.currency,
                                date=current_date
                            ).value
                            break
                        except HistoricalMarketValue.DoesNotExist:
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
                HistoricalMarketValue.objects.bulk_update(
                    update_buffer,
                    ['prev_value', 'change_amount', 'change_rate'],
                    batch_size=BATCH_SIZE
                )
                update_buffer = []

        # 提交剩余数据
        if update_buffer:
            HistoricalMarketValue.objects.bulk_update(
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
    # 手动执行更新历史持仓功能，用于调试
    # result = HistoricalPosition.objects.aggregate(max_date=Max('date'))
    # start_date = result['max_date'] - datetime.timedelta(days=7)
    # end_date = datetime.date.today()
    #
    # generate_historical_positions(start_date, end_date)
    # get_historical_closing_price(start_date, end_date - datetime.timedelta(days=1))
    # fill_missing_closing_price(start_date, end_date - datetime.timedelta(days=1))
    # get_today_price()
    # get_historical_rate(start_date, end_date)
    # fill_missing_historical_rates()
    # calculate_market_value(start_date, end_date)
    # calculate_and_fill_historical_data(start_date, end_date)

    return render(request, templates_path + 'about.html', locals())


# 测试
def test(request):
    # get_akshare()

    # df = ak.stock_hk_daily(symbol='00700', adjust="")
    # print(df)
    # stock_hk_hist_df = ak.stock_hk_hist(symbol="00700", period="daily", start_date="19700101", end_date="22220101",
    #                                     adjust="")
    # print(stock_hk_hist_df)

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
    # fund_history_list = fund_history.objects.filter(fund=3).order_by("date")
    # for rs in fund_history_list:
    #     date = str(rs.date)
    #     value = float(rs.fund_net_value)
    #     data.append({
    #         "date": date,
    #         "value": value
    #     })
    # # print(data)

    data = []
    market_value_list = HistoricalMarketValue.objects.filter(currency=1).order_by("date")
    for rs in market_value_list:
        date = str(rs.date)
        value = float(rs.value)
        data.append({
            "date": date,
            "value": value / 10000
        })

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

    # currency_boc_sina_df = ak.currency_boc_sina(symbol="港币", start_date="20250425", end_date="20250430")
    # print(currency_boc_sina_df)

    current_date = pd.to_datetime(datetime.date.today())
    current_date_str = current_date.strftime("%Y%m%d") if current_date else ""

    # df = ak.fx_spot_quote()
    # rate_HKD = float(df[df['货币对'] == 'HKD/CNY']['买报价'].iloc[0])
    # rate_USD = float(df[df['货币对'] == 'USD/CNY']['买报价'].iloc[0])
    # updating_time = datetime.datetime.now()
    #
    # df = ak.currency_boc_sina(symbol="港币", start_date=current_date_str, end_date=current_date_str)
    # df['日期'] = pd.to_datetime(df['日期'])
    # hkd = float(df[df['日期'] == current_date_str]['中行汇买价'].iloc[0] / 100)
    # df = ak.currency_boc_sina(symbol="美元", start_date=current_date_str, end_date=current_date_str)
    # df['日期'] = pd.to_datetime(df['日期'])
    # usd = float(df[df['日期'] == current_date_str]['中行汇买价'].iloc[0] / 100)

    # 美股实时行情接口
    # stock_us_spot_em_df = ak.stock_us_spot_em()
    # print(stock_us_spot_em_df)

    # 美股实时行情接口，数据量太大
    # us_stock_current_df = ak.stock_us_spot()
    # print(us_stock_current_df)

    # 美股的历史行情数据接口
    # stock_us_hist_df = ak.stock_us_hist(symbol='105.MSFT', period="daily", start_date="20250505", end_date="20250506", adjust="")
    # print(stock_us_hist_df)
    # stock_us_hist_df = ak.stock_us_hist(symbol='106.DQ', period="daily", start_date="20250505", end_date="20250506", adjust="")
    # print(stock_us_hist_df)
    # stock_us_hist_df = ak.stock_us_hist(symbol='105.AAPL', period="daily", start_date="20250505", end_date="20250506", adjust="")
    # print(stock_us_hist_df)
    # stock_us_hist_df = ak.stock_us_hist(symbol='106.KO', period="daily", start_date="20250505", end_date="20250506", adjust="")
    # print(stock_us_hist_df)

    # 美股的分时数据接口
    # stock_us_hist_min_em_df = ak.stock_us_hist_min_em(symbol="105.AAPL")
    # print(stock_us_hist_min_em_df)

    # 美股股票名称代码接口，数据量太大
    # df = ak.get_us_stock_name()
    # print(df)

    # 美股指数历史行情接口
    # index_us_stock_sina_df = ak.index_us_stock_sina(symbol=".INX")
    # print(index_us_stock_sina_df)

    # 美股历史行情接口
    # stock_us_daily_df = ak.stock_us_daily(symbol="DQ", adjust="")
    # print(stock_us_daily_df)

    # df = ak.stock_zh_a_daily(
    #     symbol='sh601318',
    #     start_date='20250505',
    #     end_date="20250505",
    #     adjust=""
    # )
    # print(df)
    # df = ak.stock_hk_hist(
    #     symbol='00700',
    #     period="daily",
    #     start_date='20250505',
    #     end_date="20250522",
    #     adjust=""
    # )
    # print(df)

    # A股指数历史行情数据-东财 截止当前日期
    # df = ak.stock_zh_index_daily_em(symbol="sh000300").sort_values(by='date', ascending=False)
    # print(df)
    # A股指数历史行情数据-新浪 截至前一天
    # stock_zh_index_daily_df = ak.stock_zh_index_daily(symbol="sh000300")
    # print(stock_zh_index_daily_df)
    # A股指数历史行情数据-腾讯 截止前一天 速度慢
    # stock_zh_index_daily_tx_df = ak.stock_zh_index_daily_tx(symbol="sh000300")
    # print(stock_zh_index_daily_tx_df)
    # 港股指数历史行情数据-东财 只返回前100条，无HSI
    # df = ak.stock_hk_index_daily_em(symbol="HSI").sort_values(by='date', ascending=False)
    # print(df)
    # 港股指数历史行情数据-新浪
    # stock_hk_index_daily_sina_df = ak.stock_hk_index_daily_sina(symbol="HSI")
    # print(stock_hk_index_daily_sina_df)
    # 美股指数行情数据-新浪
    # df = ak.index_us_stock_sina(symbol=".INX").sort_values(by='date', ascending=False)
    # print(df)
    # A股指数实时行情数据-东财
    # df = ak.stock_zh_index_daily_em(symbol="sh000300").sort_values(by='date',ascending=False).head(1)
    # current_year_HS300 = datetime.datetime.strptime(df['date'].iloc[0], "%Y-%m-%d").year
    # current_HS300 = float(df['close'].iloc[0])
    # print(current_HS300)
    # A股指数实时行情数据-新浪
    # df = ak.stock_zh_index_spot_sina()
    # current_HS300 = float(df[df['代码'] == 'sh000300']['最新价'].iloc[0])
    # print(current_HS300)
    # 港股指数实时行情数据-东财 只返回前100条，无HSI
    # df = ak.stock_hk_index_spot_em()
    # current_HSI = float(df[df['代码'] == 'HSI']['最新价'].iloc[0])
    # print(current_HSI)
    # 港股指数实时行情数据-新浪
    # df = ak.stock_hk_index_spot_sina()
    # current_HSI = float(df[df['代码'] == 'HSI']['最新价'].iloc[0])
    # print(current_HSI)

    # # 指数接口
    # # A股指数实时行情数据-新浪
    # df = ak.stock_zh_index_spot_sina()
    # current_HS300 = float(df[df['代码'] == 'sh000300']['最新价'].iloc[0])
    # print(current_HS300)
    # print(df)
    # # 港股指数实时行情数据-新浪
    # df = ak.stock_hk_index_spot_sina()
    # current_HSI = float(df[df['代码'] == 'HSI']['最新价'].iloc[0])
    # print(current_HSI)
    # # A股指数历史行情数据-新浪 截至前一天
    # stock_zh_index_daily_df = ak.stock_zh_index_daily(symbol="sh000300")
    # print(stock_zh_index_daily_df)
    # # 港股指数历史行情数据-新浪
    # stock_hk_index_daily_sina_df = ak.stock_hk_index_daily_sina(symbol="HSI")
    # print(stock_hk_index_daily_sina_df)
    # # 美股指数行情数据-新浪
    # df = ak.index_us_stock_sina(symbol=".INX").sort_values(by='date', ascending=False)
    # print(df)

    # df = ak.stock_hk_index_daily_em(symbol="HSI").sort_values(by='date',ascending=False)
    # df = ak.stock_hk_index_daily_sina(symbol="HSI").sort_values(by='date',ascending=False)
    # current_year = df.head(1)['date'].iloc[0].year
    # current_latest = float(df.head(1)['close'].iloc[0])
    # print(df)
    # print(current_year)
    # print(current_latest)
    #
    # stock_hk_fhpx_detail_ths_df = ak.stock_hk_fhpx_detail_ths(symbol="0700")
    # print(stock_hk_fhpx_detail_ths_df)

    # 沪深300全收益指数，截至前一天
    # df = ak.stock_zh_index_hist_csindex(symbol="H00300", start_date="20120101", end_date="20250610")
    # print(df)
    # df['日期'] = pd.to_datetime(df['日期'])
    # current_H000300 = float(df[df['日期'] == '2012-12-31']['收盘'].iloc[0])
    # print(current_H000300)

    # migrate_market_currencies()
    # migrate_position_currencies()
    # migrate_fund_currencies()
    # migrate_dividend_currencies()
    # migrate_trade_currencies()

    df = ak.stock_zh_index_daily(symbol="sz399006").sort_values(by='date', ascending=False)
    current_latest = float(df.head(1)['close'].iloc[0])
    # print(current_latest)

    # migrate_historical_position_currencies()
    # migrate_historical_rate_currencies()
    # migrate_historical_market_value_currencies()

    return render(request, templates_path + 'test.html', locals())


'''
def migrate_market_currencies():
    """
    迁移market表中货币字段的数据
    根据transaction_currency值设置currency外键字段
    """
    from .models import market, currency
    # 创建货币映射字典
    currency_mapping = {
        market.CNY: 'CNY',
        market.HKD: 'HKD',
        market.USD: 'USD',
    }

    # 获取所有未迁移的市场记录
    markets_to_migrate = market.objects.filter(currency__isnull=True)
    total_count = markets_to_migrate.count()
    migrated_count = 0

    if total_count == 0:
        print("没有需要迁移的市场记录")
        return

    print(f"发现 {total_count} 条需要迁移货币字段的市场记录")

    # 处理每条市场记录
    for market_record in markets_to_migrate.iterator():
        # 获取原字段值对应的货币代码
        currency_code = currency_mapping.get(market_record.transaction_currency)

        if not currency_code:
            print(f"警告: 市场 {market_record.market_name} 有未知的货币ID: {market_record.transaction_currency}")
            continue

        try:
            # 获取对应的货币对象
            currency_obj = currency.objects.get(code=currency_code)

            # 更新currency字段
            market_record.currency = currency_obj
            market_record.save(update_fields=['currency'])

            migrated_count += 1

        except currency.DoesNotExist:
            print(f"错误: 找不到代码为 {currency_code} 的货币记录")
            continue

    # 统计结果
    remaining = market.objects.filter(currency__isnull=True).count()

    print(f"\n迁移完成!")
    print(f"成功迁移记录: {migrated_count}")
    print(f"迁移失败记录: {total_count - migrated_count}")
    print(f"仍需处理的记录: {remaining}")

    if remaining > 0:
        print("\n处理失败的可能原因:")
        print("1. 市场记录中有未知的transaction_currency值")
        print("2. 缺少对应的currency记录")
        print("3. 需要扩展currency_mapping字典以覆盖更多货币类型")


def migrate_position_currencies():
    """
    迁移position表中货币字段的数据
    根据position_currency值设置currency外键字段
    """
    from .models import position, currency
    # 创建货币映射字典
    currency_mapping = {
        position.CNY: 'CNY',
        position.HKD: 'HKD',
        position.USD: 'USD',
    }

    # 获取所有未迁移的市场记录
    positions_to_migrate = position.objects.filter(currency__isnull=True)
    total_count = positions_to_migrate.count()
    migrated_count = 0

    if total_count == 0:
        print("没有需要迁移的记录")
        return

    print(f"发现 {total_count} 条需要迁移货币字段的记录")

    # 处理每条记录
    for position_record in positions_to_migrate.iterator():
        # 获取原字段值对应的货币代码
        currency_code = currency_mapping.get(position_record.position_currency)

        if not currency_code:
            print(f"警告: 有未知的货币ID: {position_record.position_currency}")
            continue

        try:
            # 获取对应的货币对象
            currency_obj = currency.objects.get(code=currency_code)

            # 更新currency字段
            position_record.currency = currency_obj
            position_record.save(update_fields=['currency'])

            migrated_count += 1

        except currency.DoesNotExist:
            print(f"错误: 找不到代码为 {currency_code} 的货币记录")
            continue

    # 统计结果
    remaining = position.objects.filter(currency__isnull=True).count()

    print(f"\n迁移完成!")
    print(f"成功迁移记录: {migrated_count}")
    print(f"迁移失败记录: {total_count - migrated_count}")
    print(f"仍需处理的记录: {remaining}")

    if remaining > 0:
        print("\n处理失败的可能原因:")
        print("1. 市场记录中有未知的position_currency值")
        print("2. 缺少对应的currency记录")
        print("3. 需要扩展currency_mapping字典以覆盖更多货币类型")


def migrate_fund_currencies():
    """
    迁移fund表中货币字段的数据
    根据fund_currency值设置currency外键字段
    """
    from .models import fund, currency
    # 创建货币映射字典
    currency_mapping = {
        fund.CNY: 'CNY',
        fund.HKD: 'HKD',
        fund.USD: 'USD',
    }

    # 获取所有未迁移的市场记录
    fund_to_migrate = Fund.objects.filter(currency__isnull=True)
    total_count = fund_to_migrate.count()
    migrated_count = 0

    if total_count == 0:
        print("没有需要迁移的记录")
        return

    print(f"发现 {total_count} 条需要迁移货币字段的记录")

    # 处理每条记录
    for fund_record in fund_to_migrate.iterator():
        # 获取原字段值对应的货币代码
        currency_code = currency_mapping.get(fund_record.fund_currency)

        if not currency_code:
            print(f"警告: 有未知的货币ID: {fund_record.fund_currency}")
            continue

        try:
            # 获取对应的货币对象
            currency_obj = currency.objects.get(code=currency_code)

            # 更新currency字段
            fund_record.currency = currency_obj
            fund_record.save(update_fields=['currency'])

            migrated_count += 1

        except currency.DoesNotExist:
            print(f"错误: 找不到代码为 {currency_code} 的货币记录")
            continue

    # 统计结果
    remaining = Fund.objects.filter(currency__isnull=True).count()

    print(f"\n迁移完成!")
    print(f"成功迁移记录: {migrated_count}")
    print(f"迁移失败记录: {total_count - migrated_count}")
    print(f"仍需处理的记录: {remaining}")

    if remaining > 0:
        print("\n处理失败的可能原因:")
        print("1. 市场记录中有未知的fund_currency值")
        print("2. 缺少对应的currency记录")
        print("3. 需要扩展currency_mapping字典以覆盖更多货币类型")


def migrate_dividend_currencies():
    """
    迁移dividend表中货币字段的数据
    根据dividend_currency值设置currency外键字段
    """
    from .models import dividend, currency
    # 创建货币映射字典
    currency_mapping = {
        dividend.CNY: 'CNY',
        dividend.HKD: 'HKD',
        dividend.USD: 'USD',
    }

    # 获取所有未迁移的市场记录
    dividend_to_migrate = dividend.objects.filter(currency__isnull=True)
    total_count = dividend_to_migrate.count()
    migrated_count = 0

    if total_count == 0:
        print("没有需要迁移的记录")
        return

    print(f"发现 {total_count} 条需要迁移货币字段的记录")

    # 处理每条记录
    for dividend_record in dividend_to_migrate.iterator():
        # 获取原字段值对应的货币代码
        currency_code = currency_mapping.get(dividend_record.dividend_currency)

        if not currency_code:
            print(f"警告: 有未知的货币ID: {dividend_record.dividend_currency}")
            continue

        try:
            # 获取对应的货币对象
            currency_obj = currency.objects.get(code=currency_code)

            # 更新currency字段
            dividend_record.currency = currency_obj
            dividend_record.save(update_fields=['currency'])

            migrated_count += 1

        except currency.DoesNotExist:
            print(f"错误: 找不到代码为 {currency_code} 的货币记录")
            continue

    # 统计结果
    remaining = Fund.objects.filter(currency__isnull=True).count()

    print(f"\n迁移完成!")
    print(f"成功迁移记录: {migrated_count}")
    print(f"迁移失败记录: {total_count - migrated_count}")
    print(f"仍需处理的记录: {remaining}")

    if remaining > 0:
        print("\n处理失败的可能原因:")
        print("1. 市场记录中有未知的dividend_currency值")
        print("2. 缺少对应的currency记录")
        print("3. 需要扩展currency_mapping字典以覆盖更多货币类型")


def migrate_trade_currencies():
    """
    迁移trade表中货币字段的数据
    根据settlement_currency值设置currency外键字段
    """
    from .models import trade, currency
    # 创建货币映射字典
    currency_mapping = {
        trade.CNY: 'CNY',
        trade.HKD: 'HKD',
        trade.USD: 'USD',
    }

    # 获取所有未迁移的市场记录
    trade_to_migrate = trade.objects.filter(currency__isnull=True)
    total_count = trade_to_migrate.count()
    migrated_count = 0

    if total_count == 0:
        print("没有需要迁移的记录")
        return

    print(f"发现 {total_count} 条需要迁移货币字段的记录")

    # 处理每条记录
    for trade_record in trade_to_migrate.iterator():
        # 获取原字段值对应的货币代码
        currency_code = currency_mapping.get(trade_record.settlement_currency)

        if not currency_code:
            print(f"警告: 有未知的货币ID: {trade_record.settlement_currency}")
            continue

        try:
            # 获取对应的货币对象
            currency_obj = currency.objects.get(code=currency_code)

            # 更新currency字段
            trade_record.currency = currency_obj
            trade_record.save(update_fields=['currency'])

            migrated_count += 1

        except currency.DoesNotExist:
            print(f"错误: 找不到代码为 {currency_code} 的货币记录")
            continue

    # 统计结果
    remaining = Fund.objects.filter(currency__isnull=True).count()

    print(f"\n迁移完成!")
    print(f"成功迁移记录: {migrated_count}")
    print(f"迁移失败记录: {total_count - migrated_count}")
    print(f"仍需处理的记录: {remaining}")

    if remaining > 0:
        print("\n处理失败的可能原因:")
        print("1. 市场记录中有未知的settlement_currency值")
        print("2. 缺少对应的currency记录")
        print("3. 需要扩展currency_mapping字典以覆盖更多货币类型")


def migrate_historical_position_currencies():
    """
    迁移trade表中货币字段的数据
    根据settlement_currency值设置currency外键字段
    """
    from .models import historical_position, currency
    # 创建货币映射字典
    currency_mapping = {
        historical_position.CNY: 'CNY',
        historical_position.HKD: 'HKD',
        historical_position.USD: 'USD',
    }

    # 获取所有未迁移的市场记录
    historical_position_to_migrate = historical_position.objects.filter(currency_type__isnull=True)
    total_count = historical_position_to_migrate.count()
    migrated_count = 0

    if total_count == 0:
        print("没有需要迁移的记录")
        return

    print(f"发现 {total_count} 条需要迁移货币字段的记录")

    # 处理每条记录
    for historical_position_record in historical_position_to_migrate.iterator():
        # 获取原字段值对应的货币代码
        currency_code = currency_mapping.get(historical_position_record.currency)

        if not currency_code:
            print(f"警告: 有未知的货币ID: {historical_position_record.currency}")
            continue

        try:
            # 获取对应的货币对象
            currency_obj = currency.objects.get(code=currency_code)

            # 更新currency字段
            historical_position_record.currency_type = currency_obj
            historical_position_record.save(update_fields=['currency_type'])

            migrated_count += 1

        except currency.DoesNotExist:
            print(f"错误: 找不到代码为 {currency_code} 的货币记录")
            continue

    # 统计结果
    remaining = historical_position.objects.filter(currency_type__isnull=True).count()

    print(f"\n迁移完成!")
    print(f"成功迁移记录: {migrated_count}")
    print(f"迁移失败记录: {total_count - migrated_count}")
    print(f"仍需处理的记录: {remaining}")

    if remaining > 0:
        print("\n处理失败的可能原因:")
        print("1. 市场记录中有未知的settlement_currency值")
        print("2. 缺少对应的currency记录")
        print("3. 需要扩展currency_mapping字典以覆盖更多货币类型")


def migrate_historical_rate_currencies():
    print("开始迁移货币数据...")

    with transaction.atomic():
        # 查询所有需要迁移的记录
        rates = historical_rate.objects.filter(currency_temp__isnull=True)
        total = rates.count()
        print(f"找到 {total} 条需要迁移的记录")

        batch_size = 1000
        for i in range(0, total, batch_size):
            batch = rates[i:i + batch_size]
            print(f"处理批次 {i // batch_size + 1}/{(total - 1) // batch_size + 1}")

            for rate in batch:
                # 根据货币名称查找对应货币对象
                try:
                    curr = currency.objects.get(name=rate.currency)
                    rate.currency_temp = curr
                    rate.save(update_fields=['currency_temp'])
                except currency.DoesNotExist:
                    print(f"警告：找不到对应货币 '{rate.currency}'，记录ID: {rate.id}")

    # 验证完整性
    missing = historical_rate.objects.filter(currency_temp__isnull=True).count()
    if missing:
        print(f"警告：仍有 {missing} 条记录未成功迁移")
    else:
        print("迁移成功完成！所有记录均已完成迁移")


def migrate_historical_market_value_currencies():
    print("开始迁移货币数据...")

    with transaction.atomic():
        # 查询所有需要迁移的记录
        rates = historical_market_value.objects.filter(currency_temp__isnull=True)
        total = rates.count()
        print(f"找到 {total} 条需要迁移的记录")

        batch_size = 20000
        for i in range(0, total, batch_size):
            batch = rates[i:i + batch_size]
            print(f"处理批次 {i // batch_size + 1}/{(total - 1) // batch_size + 1}")

            for rate in batch:
                # 根据货币名称查找对应货币对象
                try:
                    curr = currency.objects.get(name=rate.currency)
                    rate.currency_temp = curr
                    rate.save(update_fields=['currency_temp'])
                except currency.DoesNotExist:
                    print(f"警告：找不到对应货币 '{rate.currency}'，记录ID: {rate.id}")

    # 验证完整性
    missing = historical_market_value.objects.filter(currency_temp__isnull=True).count()
    if missing:
        print(f"警告：仍有 {missing} 条记录未成功迁移")
    else:
        print("迁移成功完成！所有记录均已完成迁移")
'''

'''
def generate_historical_positions_bak0622(start_date, end_date):
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
        # 初始化持仓缓存 {(stock_id, currency_type_id): quantity}
        position_cache = defaultdict(int)
        process_start = start_date
        date_sequence = []

        # 1. 检查并加载初始持仓
        initial_positions = historical_position.objects.filter(date=start_date)
        if initial_positions.exists():
            # 加载初始持仓（过滤零持仓）
            for pos in initial_positions.exclude(quantity=0):
                # 修改点1：使用 currency_type_id 替代 currency
                key = (pos.stock_id, pos.currency_type_id)
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
            'currency_id', 'trade_type',  # 修改点2：使用 currency_id
            'trade_quantity'
        )

        # 4. 按日期处理交易生成持仓
        new_positions = []
        for processing_date in date_sequence:
            # 当日交易分组汇总
            daily_trades = defaultdict(lambda: {'buy': 0, 'sell': 0})
            for t in relevant_trades:
                if t['trade_date'] == processing_date:
                    # 修改点3：使用 currency_id
                    key = (t['stock_id'], t['currency_id'])
                    if t['trade_type'] == trade.BUY:
                        daily_trades[key]['buy'] += t['trade_quantity']
                    else:
                        daily_trades[key]['sell'] += t['trade_quantity']

            # 计算当日持仓变化
            temp_cache = defaultdict(int)
            temp_cache.update(position_cache)  # 继承前一日持仓

            # 处理每个股票+货币组合
            for (stock_id, currency_id), amounts in daily_trades.items():
                net_change = amounts['buy'] - amounts['sell']
                new_quantity = temp_cache[(stock_id, currency_id)] + net_change

                if new_quantity != 0:
                    temp_cache[(stock_id, currency_id)] = new_quantity
                else:
                    # 清除零持仓
                    del temp_cache[(stock_id, currency_id)]

            # 更新持仓缓存
            position_cache = temp_cache

            # 生成当日记录（过滤零持仓）
            for (stock_id, currency_id), quantity in position_cache.items():
                # 修改点4：使用 currency_type_id 替代 currency
                new_positions.append(historical_position(
                    date=processing_date,
                    stock_id=stock_id,
                    currency_type_id=currency_id,
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


def generate_historical_positions_bak(start_date, end_date):
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
            'currency_id', 'trade_type',
            'trade_quantity'
        )

        # 4. 按日期处理交易生成持仓
        new_positions = []
        for processing_date in date_sequence:
            # 当日交易分组汇总
            daily_trades = defaultdict(lambda: {'buy': 0, 'sell': 0})
            for t in relevant_trades:
                if t['trade_date'] == processing_date:
                    key = (t['stock_id'], t['currency_id'])
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


def fill_missing_closing_price_bak0622(start_date, end_date):
    with transaction.atomic():
        # 获取指定日期范围内收盘价为0的所有记录
        records = historical_position.objects.filter(
            date__range=(start_date, end_date),
            closing_price=0
        )

        updates = []
        count = 0

        for record in records:
            # 查找同一股票和货币的最近有效收盘价记录
            prev_entry = historical_position.objects.filter(
                stock=record.stock,
                currency_type_id=record.currency_type_id,
                date__lt=record.date,
                closing_price__gt=0
            ).order_by('-date').first()

            if prev_entry:
                record.closing_price = prev_entry.closing_price
                updates.append(record)
                count += 1

        # 批量更新记录
        if updates:
            historical_position.objects.bulk_update(updates, ['closing_price'])

        print(f"补全了 {count} 条缺失的收盘价格")

        return


def fill_missing_closing_price_bak(start_date, end_date):
    with transaction.atomic():
        # 获取指定日期范围内收盘价为0的所有记录
        records = historical_position.objects.filter(
            date__range=(start_date, end_date),
            closing_price=0
        )

        updates = []
        count = 0

        for record in records:
            # 查找同一股票和货币的最近有效收盘价记录
            prev_entry = historical_position.objects.filter(
                stock=record.stock,
                currency=record.currency,
                date__lt=record.date,
                closing_price__gt=0
            ).order_by('-date').first()

            if prev_entry:
                record.closing_price = prev_entry.closing_price
                updates.append(record)
                count += 1

        # 批量更新记录
        if updates:
            historical_position.objects.bulk_update(updates, ['closing_price'])

        print(f"补全了 {count} 条缺失的收盘价格")

        return


def fill_missing_historical_rates_bak0622():
    from .models import currency
    """
    自动补全historical_rate表中缺失的汇率记录
    返回补全记录数量和错误信息列表
    """
    # +++ 修改点1：使用 Currency 模型映射 +++
    # 获取所有货币及其ID映射 {currency_id: currency_name}
    currency_map = {
        currency_obj.id: currency_obj.name
        for currency_obj in currency.objects.all()
    }

    # 获取需要补全的日期和货币组合
    # +++ 修改点2：使用 currency_type_id 替代 currency +++
    positions = historical_position.objects.values('date', 'currency_type_id').distinct()

    # 转换货币ID为货币名称
    required_combinations = [
        (pos['date'], currency_map[pos['currency_type_id']])
        for pos in positions
        if pos['currency_type_id'] in currency_map
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
    return len(new_rates), errors


def fill_missing_historical_rates_bak():
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


def calculate_market_value_bak0622(start_date, end_date):
    """
    生成历史市值数据并写入 historical_market_value 表
    """
    try:
        # 使用原子事务保证数据一致性
        with transaction.atomic():
            # 1. 清空历史市值表
            historical_market_value.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).delete()

            # 2. 预加载汇率数据（日期范围 + 货币）
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
            # +++ 修改点3：预取关联的 currency_type +++
            positions = historical_position.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).select_related('stock', 'currency_type')

            # 构建日期到持仓记录的映射
            date_positions = defaultdict(list)
            for pos in positions:
                date_positions[pos.date].append(pos)

            # 6. 计算每日市值
            market_values = []
            current_date = start_date
            while current_date <= end_date:

                # 获取当日所有持仓记录
                daily_positions = date_positions.get(current_date, [])

                # 按货币计算市值总和
                currency_totals = defaultdict(Decimal)
                for pos in daily_positions:
                    # +++ 修改点4：通过外键关系获取货币名称 +++
                    currency_name = pos.currency_type.name
                    if not currency_name:
                        raise ValueError(f'无效货币ID: {pos.currency_type_id}')

                    # 6.2 获取汇率（人民币特殊处理）
                    # 如持仓货币为人民币且股票市场为港股，则为港股通持仓，需按港元汇率计算人民币市值
                    # if currency_name == '人民币' and pos.stock.market.currency_id == 2:
                    if currency_name == '人民币' and pos.stock.market.currency_id == 2:
                        exchange_rate = rate_dict.get((current_date, '港元'))
                        if exchange_rate is None:
                            exchange_rate = Decimal(1)
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


def calculate_market_value_bak(start_date, end_date):
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
                    # if currency_name == '人民币' and pos.stock.market.transaction_currency == 2:
                    if currency_name == '人民币' and pos.stock.market.currency_id == 2:  # 不能用pos.stock.market.currency,应该用pos.stock.market.currency_id
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


def get_historical_rate_bak(start_date, end_date):
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


def update_historical_rate_bak(df: pd.DataFrame, currency_name: str, start_date, end_date) -> None:
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
            rate=row['中行汇买价'] / 100
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


def fill_missing_historical_rates_bak0623():
    from .models import currency
    """
    自动补全historical_rate表中缺失的汇率记录
    返回补全记录数量和错误信息列表
    """
    # +++ 修改点1：使用 Currency 模型映射 +++
    # 获取所有货币及其ID映射 {currency_id: currency_name}
    currency_map = {
        currency_obj.id: currency_obj.name
        for currency_obj in currency.objects.all()
    }

    # 获取需要补全的日期和货币组合
    # +++ 修改点2：使用 currency_id 替代 currency +++
    positions = historical_position.objects.values('date', 'currency_id').distinct()

    # 转换货币ID为货币名称
    required_combinations = [
        (pos['date'], currency_map[pos['currency_id']])
        for pos in positions
        if pos['currency_id'] in currency_map
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
    return len(new_rates), errors


def calculate_market_value_bak0623(start_date, end_date):
    """
    生成历史市值数据并写入 historical_market_value 表
    """
    try:
        # 使用原子事务保证数据一致性
        with transaction.atomic():
            # 1. 清空历史市值表
            historical_market_value.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).delete()

            # 2. 预加载汇率数据（日期范围 + 货币）
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
            # +++ 修改点3：预取关联的 currency +++
            positions = historical_position.objects.filter(
                date__gte=start_date,
                date__lte=end_date
            ).select_related('stock', 'currency')

            # 构建日期到持仓记录的映射
            date_positions = defaultdict(list)
            for pos in positions:
                date_positions[pos.date].append(pos)

            # 6. 计算每日市值
            market_values = []
            current_date = start_date
            while current_date <= end_date:

                # 获取当日所有持仓记录
                daily_positions = date_positions.get(current_date, [])

                # 按货币计算市值总和
                currency_totals = defaultdict(Decimal)
                for pos in daily_positions:
                    # +++ 修改点4：通过外键关系获取货币名称 +++
                    currency_name = pos.currency.name
                    if not currency_name:
                        raise ValueError(f'无效货币ID: {pos.currency_id}')

                    # 6.2 获取汇率（人民币特殊处理）
                    # 如持仓货币为人民币且股票市场为港股，则为港股通持仓，需按港元汇率计算人民币市值
                    # if currency_name == '人民币' and pos.stock.market.currency_id == 2:
                    if currency_name == '人民币' and pos.stock.market.currency_id == 2:
                        exchange_rate = rate_dict.get((current_date, '港元'))
                        if exchange_rate is None:
                            exchange_rate = Decimal(1)
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
'''

"""
def get_historical_closing_price_bak20250906(start_date, end_date):
    # while end_date.weekday() >= 5:
    #     end_date -= datetime.timedelta(days=1)

    # start_date_str = (start_date - datetime.timedelta(days=10)).strftime("%Y%m%d") if start_date else ""
    start_date_str = start_date.strftime("%Y%m%d") if start_date else ""
    end_date_str = end_date.strftime("%Y%m%d") if end_date else ""
    date_list = list(HistoricalPosition.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).values_list('date', flat=True).distinct())
    # 获取stock字段的去重值列表
    stock_list = list(HistoricalPosition.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).values_list('stock', flat=True).distinct())
    for i in stock_list:
        stock_code = Stock.objects.get(id=i).stock_code
        market_name = Stock.objects.get(id=i).market.market_name
        market_abbreviation = Stock.objects.get(id=i).market.market_abbreviation
        price_dict = {}
        if market_name == '港股':
            stock_code_str = stock_code
            # df = ak.stock_hk_hist(symbol=stock_code_str, period="daily", start_date=start_date_str, end_date=end_date_str, adjust="")
            # 如果df为空，则把start_date_str往前一天继续获得df，直至df不为空
            attempts = 0
            # 将初始日期转为datetime对象以便调整
            current_start_date = datetime.datetime.strptime(start_date_str, "%Y%m%d")
            while attempts < 10:
                df = ak.stock_hk_hist(
                    symbol=stock_code_str,
                    period="daily",
                    start_date=current_start_date.strftime("%Y%m%d"),
                    end_date=end_date_str,
                    adjust=""
                )
                # 如果数据不为空，退出循环
                if not df.empty:
                    break
                # 否则：将日期提前一天，增加尝试次数
                current_start_date -= datetime.timedelta(days=1)
                attempts += 1
            else:
                # 循环正常结束（达到最大尝试次数仍无数据）
                raise ValueError(f"在 30 天内未找到有效数据，请检查股票代码或日期范围")
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
        elif market_name == '美股':
            stock_code_str = stock_code
            # 美股历史行情接口
            df = ak.stock_us_daily(symbol=stock_code_str, adjust="")
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
        else:
            if market_name == '沪市B股' or market_name == '深市B股':
                stock_code_str = market_abbreviation + stock_code
                df = ak.stock_zh_b_daily(symbol=stock_code_str, start_date=start_date_str, end_date=end_date_str,
                                         adjust="")
            elif classify_stock_code(stock_code) == 'ETF':
                stock_code_str = market_abbreviation + stock_code
                df = ak.stock_zh_index_daily(symbol=stock_code_str)
            elif classify_stock_code(stock_code) == '企业债':
                stock_code_str = market_abbreviation + stock_code
                df = ak.bond_zh_hs_daily(symbol=stock_code_str)
            else:
                stock_code_str = market_abbreviation + stock_code
                df = ak.stock_zh_a_daily(symbol=stock_code_str, start_date=start_date_str, end_date=end_date_str,
                                         adjust="")
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


def update_closing_prices_bak20250906(stock_code, price_dict):
    # 转换为日期索引的字典
    # price_dict = {item['date']: item['price'] for item in price_list}

    # 筛选需要更新的记录
    dates = price_dict.keys()
    records = HistoricalPosition.objects.filter(date__in=dates, stock__stock_code=stock_code)

    # 批量赋值并更新
    for record in records:
        record.closing_price = price_dict[record.date]

    try:
        with transaction.atomic():
            HistoricalPosition.objects.bulk_update(records, ['closing_price'])
            print(stock_code)
            print("历史收盘价格更新成功！")
    except Exception as e:
        print(stock_code)
        print(f"历史收盘价格更新失败: {str(e)}")


"""

"""
def get_today_price1():
    current_date = datetime.date.today()
    while current_date.weekday() >= 5:
        current_date -= datetime.timedelta(days=1)
    # 获取stock字段的去重值列表
    stock_list = list(HistoricalPosition.objects.filter(date=current_date).values_list('stock', flat=True).distinct())
    for i in stock_list:
        stock_code = Stock.objects.get(id=i).stock_code
        price_dict = {}
        current_price, increase, color = get_quote_snowball(stock_code)
        price_dict[current_date] = current_price
        update_today_prices(current_date, stock_code, price_dict)
    return


def get_today_price2():
    current_date = datetime.date.today()
    # 找到最近的工作日
    while current_date.weekday() >= 5:
        current_date -= datetime.timedelta(days=1)

    # 一次性获取所有需要更新的股票信息
    positions = HistoricalPosition.objects.filter(date=current_date).select_related('stock')

    # 按股票分组
    stock_groups = defaultdict(list)
    stock_codes = set()

    for position in positions:
        stock_groups[position.stock.stock_code].append(position)
        stock_codes.add(position.stock.stock_code)

    # 批量获取所有股票价格
    stock_prices = {}
    for stock_code in stock_codes:
        current_price, _, _ = get_quote_snowball(stock_code)
        stock_prices[stock_code] = current_price

    # 准备批量更新
    records_to_update = []
    for stock_code, positions_list in stock_groups.items():
        price = stock_prices.get(stock_code)
        if price is None:
            continue

        for position in positions_list:
            position.closing_price = price
            records_to_update.append(position)

    # 一次性批量更新所有记录
    if records_to_update:
        try:
            with transaction.atomic():
                HistoricalPosition.objects.bulk_update(records_to_update, ['closing_price'])
                print(f"成功更新 {len(records_to_update)} 条当日价格记录")
        except Exception as e:
            print(f"当日价格更新失败: {str(e)}")
    else:
        print("没有需要更新的记录")
        
        
def update_today_prices1(current_date, stock_code, price_dict):
    # 筛选需要更新的记录
    # dates = price_dict.keys()
    # current_date = datetime.date.today()

    records = HistoricalPosition.objects.filter(date=current_date, stock__stock_code=stock_code)

    # 批量赋值并更新
    for record in records:
        record.closing_price = price_dict[record.date]

    try:
        with transaction.atomic():
            HistoricalPosition.objects.bulk_update(records, ['closing_price'])
            print(stock_code)
            print("当日价格更新成功！")
    except Exception as e:
        print(stock_code)
        print(f"当日价格更新失败: {str(e)}")
        
"""
