import json
import os
import pathlib
import re
import time
from decimal import Decimal
import datetime
import time
import threading

# import tushare as ts
import akshare as ak
import bs4
import django
import pandas as pd
import requests
from bs4 import BeautifulSoup
from django.db.models import Sum, Avg, Min, Max
from django.db.models.functions import ExtractYear
from collections import defaultdict

# import pysnowball as ball

# from lxml import etree
# from lxml import html
# etree = html.etree

# 从应用之外调用stock应用的models时，需要设置'DJANGO_SETTINGS_MODULE'变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benben.settings')
django.setup()
from stock.models import Stock, Trade, Position, Dividend, FundHistory, Currency, HistoricalMarketValue, HistoricalRate


# 将字典类型数据写入json文件或读取json文件并转为字典格式输出，若json文件不存在则创建文件再写入
class FileOperate:
    '''
    需要传入文件所在目录，完整文件名。
    默认为只读，并将json文件转换为字典类型输出
    若为写入，需向dictData传入字典类型数据
    默认为utf-8格式
    '''

    def __init__(self, filepath, filename, way='r', dictData=None, encoding='utf-8'):
        self.filepath = filepath
        self.filename = filename
        self.way = way
        self.dictData = dictData
        self.encoding = encoding

    def operation_file(self):
        if self.dictData:
            self.way = 'w'
        with open(self.filepath + self.filename, self.way, encoding=self.encoding) as f:
            if self.dictData:
                # print(self.dictData)
                f.write(json.dumps(self.dictData, ensure_ascii=False, indent=2))
            else:
                if '.json' in self.filename:
                    data = json.loads(f.read())
                else:
                    data = f.read()
                return data


# 在二维列表price_array中用查找stock_code所在的位置，返回该位置对应子列表的index，若查找失败，返回index=-1
def search_price_array(price_array, stock_code):
    i = 0
    index = -1
    while i < len(price_array):
        if price_array[i][0] == stock_code:
            index = i
            break
        i += 1
    return index


# 获取图表数据队列函数
def get_chart_array1(content, max_rows, name_col, value_col):
    name_array = []
    value_array = []
    content_num = len(content)
    if max_rows == -1:
        max_rows = content_num
    if content_num <= max_rows:
        for i in range(0, content_num):
            name_array.append(content[i][name_col])
            value_array.append(int(content[i][value_col]))
    else:
        for i in range(0, max_rows):
            name_array.append(content[i][name_col])
            value_array.append(int(content[i][value_col]))
        other = 0
        for i in range(max_rows, content_num):
            other += content[i][value_col]
        name_array.append('其他')
        value_array.append(int(other))
    return name_array, value_array


def get_chart_array(content, max_rows, name_col, value_col):
    if not content:
        return [], []

    if len(content) <= max_rows or max_rows == -1:
        names = [item[name_col] for item in content]
        values = [int(item[value_col]) for item in content]
    else:
        # 前N-1个股票
        names = [item[name_col] for item in content[:max_rows - 1]]
        values = [int(item[value_col]) for item in content[:max_rows - 1]]

        # 合并剩余股票为"其他"
        other_value = sum(item[value_col] for item in content[max_rows - 1:])
        names.append('其他')
        values.append(int(other_value))

    return names, values


'''
# 抓取单一股票实时行情
def get_stock_price1(stock_code):
    # stock_object = stock.objects.get(stock_code=stock_code)
    path = pathlib.Path("./templates/dashboard/price.json")
    if path.is_file():  # 若json文件存在，从json文件中读取price、increase、color、price_time、index
        # 读取price.json
        price_dict = FileOperate(filepath='./templates/dashboard/', filename='price.json').operation_file()
        price_array = price_dict['price_array']
        price_time = datetime.datetime.strptime(price_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
        # price, increase, color, price_time, index = search_price_array(price_array, stock_code)
        index = search_price_array(price_array, stock_code)
        if index != -1:
            price = float(price_array[index][1])
            increase = float(price_array[index][2])
            color = str(price_array[index][3])
    else:  # 若json文件不存在，创建json文件
        price_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
        index = -1
        price_array = []
        price_dict = {}
        price_dict.update(price_array=price_array)
        price_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=price_dict, filepath='./templates/dashboard/', filename='price.json').operation_file()
    time1 = price_time
    time2 = datetime.datetime.now()
    time3 = datetime.datetime(time1.year, time1.month, time1.day, 16, 29, 59)
    # 当前时间与数据库价格获取时间不是同一天 或 (当前时间与数据库价格获取时间间隔大于900秒 且 数据库价格获取时间早于当天的16点30分)
    if time1.date() != time2.date() or (
            (time2 - time1).total_seconds() >= 900 and (time1 - time3).total_seconds() <= 0) or index == -1:
        # if (time2 - time1).total_seconds() >= 0: # 用于调试
        # 1.从雪球网抓取实时行情
        price, increase, color = get_quote_snowball(stock_code)

        # 2.通过pysnowball API抓取雪球网实时行情
        # price, increase, color = get_quote_pysnowball(stock_code)

        # 3.从http://qt.gtimg.cn/抓取实时行情
        # price, increase, color = get_quote_gtimg(stock_code)

        # 4.从akshare抓取实时行情 东财和新浪接口都只返回前100条数据
        # price, increase, color = get_quote_akshare(stock_code)

        # 写入json文件
        if index == -1:
            price_array.append((stock_code, price, increase, color))
        else:
            price_array[index] = (stock_code, price, increase, color)
        price_dict.update(price_array=price_array)
        price_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=price_dict, filepath='./templates/dashboard/', filename='price.json').operation_file()

    return price, increase, color


# 抓取股票列表实时行情
def get_stock_array_price1(stock_code_array):
    path = pathlib.Path("./templates/dashboard/price.json")
    if path.is_file():  # 若json文件存在，从json文件中读取price、increase、color、price_time、index
        price_dict = FileOperate(filepath='./templates/dashboard/', filename='price.json').operation_file()
        price_array = price_dict['price_array']
        price_time = datetime.datetime.strptime(price_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
    else:  # 若json文件不存在，创建json文件
        price_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
        price_array = []
        price_dict = {}
        price_dict.update(price_array=price_array)
        price_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=price_dict, filepath='./templates/dashboard/', filename='price.json').operation_file()
    time1 = price_time
    time2 = datetime.datetime.now()
    time3 = datetime.datetime(time1.year, time1.month, time1.day, 16, 29, 59)
    price_array_current = price_array
    # 当前时间与数据库价格获取时间不是同一天 或 (当前时间与price.json文件价格获取时间间隔大于60秒 且 price.json文件价格获取时间早于当天的16点30分)
    if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 60 and (time1 - time3).total_seconds() <= 0):
        price_array_current = get_quote_array_snowball(stock_code_array)
        # 写入json文件
        # 从price_array_current中依次取出每组元素，与price_array对比，不存在则追加，存在则覆盖
        for i in price_array_current:
            stock_code = str(i[0])
            price = float(i[1])
            increase = float(i[2])
            color = str(i[3])
            # 在price_array中用查找stock_code所在的位置，返回该位置对应子列表的index，若查找失败，返回index=-1
            index = search_price_array(price_array, stock_code)
            if index == -1:
                price_array.append((stock_code, price, increase, color))
            else:
                price_array[index] = (stock_code, price, increase, color)

        price_dict.update(price_array=price_array)
        price_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=price_dict, filepath='./templates/dashboard/', filename='price.json').operation_file()

    return price_array_current


# 全局内存缓存
_PRICE_CACHE = {
    'data': {},  # 股票数据字典 {code: (price, increase, color)}
    'last_updated': 0,  # 最后更新时间戳
    'expiry': 0  # 缓存过期时间戳
}
CACHE_TTL = 60  # 缓存有效期60秒


def get_stock_price(stock_code):
    """获取单一股票实时行情数据，基于全局内存缓存"""
    global _PRICE_CACHE

    current_time = time.time()
    str_code = str(stock_code)

    # 检查是否需要刷新缓存
    need_refresh = False

    # 情况1：缓存为空（首次运行）
    if not _PRICE_CACHE['data']:
        print(f"缓存为空，需要初始化，请求股票: {str_code}")
        need_refresh = True

    # 情况2：缓存已过期且在交易时间内
    elif current_time > _PRICE_CACHE['expiry'] and _is_trading_time():
        print(f"缓存已过期且在交易时间内，需要刷新，请求股票: {str_code}")
        need_refresh = True

    # 情况3：请求的股票不在缓存中
    elif str_code not in _PRICE_CACHE['data']:
        print(f"股票 {str_code} 不在缓存中，需要刷新")
        need_refresh = True

    # 如果需要刷新，获取最新数据
    if need_refresh:
        # 获取所有需要缓存的股票代码（包括请求的股票）
        # 这里可以根据实际情况扩展，如果需要缓存更多股票
        stock_codes_to_fetch = [str_code]

        print(f"开始刷新缓存，股票数量: {len(stock_codes_to_fetch)}")
        _refresh_cache(stock_codes_to_fetch)

    # 从缓存中获取请求的股票数据
    if str_code in _PRICE_CACHE['data']:
        price, increase, color = _PRICE_CACHE['data'][str_code]
        print(f"从缓存返回股票 {str_code}: 价格={price}, 涨幅={increase}, 颜色={color}")
        return price, increase, color
    else:
        # 如果缓存中没有该股票，返回默认值
        print(f"股票 {str_code} 不在缓存中，返回默认值")
        return 0.0, 0.0, 'gray'


def get_stock_array_price(stock_code_array):
    """获取股票实时行情数据，完全基于内存缓存"""
    global _PRICE_CACHE

    current_time = time.time()
    print(f"当前时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 检查是否需要刷新缓存
    need_refresh = False

    # 情况1：缓存为空（首次运行）
    if not _PRICE_CACHE['data']:
        print("缓存为空，需要初始化")
        need_refresh = True

    # 情况2：缓存已过期且在交易时间内
    elif current_time > _PRICE_CACHE['expiry'] and _is_trading_time():
        print("缓存已过期且在交易时间内，需要刷新")
        need_refresh = True

    # 如果需要刷新，获取最新数据
    if need_refresh and stock_code_array:
        print(f"开始刷新缓存，股票数量: {len(stock_code_array)}")
        _refresh_cache(stock_code_array)

    # 返回请求的股票数据
    return _get_requested_prices(stock_code_array)


def _refresh_cache(stock_codes):
    """刷新缓存数据"""
    global _PRICE_CACHE

    print("调用 get_quote_array_snowball...")
    new_prices = get_quote_array_snowball(stock_codes)
    print(f"从雪球获取到 {len(new_prices)} 条数据")

    # 清空缓存
    _PRICE_CACHE['data'] = {}

    # 更新缓存
    for item in new_prices:
        try:
            # 确保数据格式正确
            if len(item) < 4:
                print(f"数据格式错误: {item}")
                continue

            code = str(item[0])
            price = float(item[1])
            increase = float(item[2])
            color = str(item[3])

            _PRICE_CACHE['data'][code] = (price, increase, color)
            print(f"缓存股票: {code} - 价格: {price}, 涨幅: {increase}, 颜色: {color}")
        except Exception as e:
            print(f"处理股票数据错误: {item}, 错误: {e}")
            _PRICE_CACHE['data'][str(item[0])] = (0.0, 0.0, 'gray')

    # 更新缓存时间
    current_time = int(time.time())
    _PRICE_CACHE['last_updated'] = current_time
    _PRICE_CACHE['expiry'] = current_time + CACHE_TTL

    print(f"缓存更新完成，包含 {len(_PRICE_CACHE['data'])} 只股票")
    print(f"缓存过期时间: {datetime.datetime.fromtimestamp(_PRICE_CACHE['expiry']).strftime('%Y-%m-%d %H:%M:%S')}")


def _get_requested_prices(stock_codes):
    """从缓存中提取请求的股票数据"""
    result = []

    for code in stock_codes:
        str_code = str(code)
        if str_code in _PRICE_CACHE['data']:
            price, increase, color = _PRICE_CACHE['data'][str_code]
            result.append((str_code, price, increase, color))
        else:
            # 缓存中没有的股票返回默认值
            print(f"股票 {str_code} 不在缓存中")
            result.append((str_code, 0.0, 0.0, 'gray'))

    print(f"返回 {len(result)} 只股票数据")
    print(f"前3条结果: {result[:3]}")
    return result

# 初始化缓存 - 强制首次刷新
# _PRICE_CACHE['expiry'] = 0
# print("缓存初始化完成，强制首次刷新")

'''

# 全局内存缓存 - 用于单支股票
_SINGLE_PRICE_CACHE = {
    'data': {},  # 股票数据字典 {code: (price, increase, color)}
    'last_updated': 0,  # 最后更新时间戳
    'expiry': 0  # 缓存过期时间戳
}

# 全局内存缓存 - 用于多支股票
_ARRAY_PRICE_CACHE = {
    'data': {},  # 股票数据字典 {code: (price, increase, color)}
    'last_updated': 0,  # 最后更新时间戳
    'expiry': 0  # 缓存过期时间戳
}

CACHE_TTL = 60  # 缓存有效期60秒


def get_stock_price(stock_code):
    """获取单一股票实时行情数据，使用独立缓存"""
    global _SINGLE_PRICE_CACHE

    current_time = time.time()
    str_code = str(stock_code)

    # 检查是否需要刷新缓存
    need_refresh = False

    # 情况1：缓存为空（首次运行）
    if not _SINGLE_PRICE_CACHE['data']:
        print(f"单支股票缓存为空，需要初始化，请求股票: {str_code}")
        need_refresh = True

    # 情况2：缓存已过期且在交易时间内
    elif current_time > _SINGLE_PRICE_CACHE['expiry'] and _is_trading_time():
        print(f"单支股票缓存已过期且在交易时间内，需要刷新，请求股票: {str_code}")
        need_refresh = True

    # 情况3：请求的股票不在缓存中
    elif str_code not in _SINGLE_PRICE_CACHE['data']:
        print(f"股票 {str_code} 不在单支股票缓存中，需要刷新")
        need_refresh = True

    # 如果需要刷新，获取最新数据
    if need_refresh:
        # 只获取请求的单一股票数据
        print(f"开始刷新单支股票缓存，股票: {str_code}")
        _refresh_single_cache(str_code)

    # 从缓存中获取请求的股票数据
    if str_code in _SINGLE_PRICE_CACHE['data']:
        price, increase, color = _SINGLE_PRICE_CACHE['data'][str_code]
        print(f"从单支股票缓存返回股票 {str_code}: 价格={price}, 涨幅={increase}, 颜色={color}")
        print(f"缓存内容:{_SINGLE_PRICE_CACHE}")
        return price, increase, color
    else:
        # 如果缓存中没有该股票，返回默认值
        print(f"股票 {str_code} 不在单支股票缓存中，返回默认值")
        return 0.0, 0.0, 'gray'


def _refresh_single_cache(stock_code):
    """刷新单支股票缓存数据"""
    global _SINGLE_PRICE_CACHE

    # 从雪球获取单一股票数据
    price, increase, color = get_quote_snowball(stock_code)

    # 清空缓存
    _SINGLE_PRICE_CACHE['data'] = {}

    # 更新缓存
    _SINGLE_PRICE_CACHE['data'][stock_code] = (price, increase, color)

    # 更新缓存时间
    current_time = int(time.time())
    _SINGLE_PRICE_CACHE['last_updated'] = current_time
    _SINGLE_PRICE_CACHE['expiry'] = current_time + CACHE_TTL

    print(f"单支股票缓存更新完成，股票: {stock_code}")
    print(f"单支股票缓存过期时间: {datetime.datetime.fromtimestamp(_SINGLE_PRICE_CACHE['expiry']).strftime('%Y-%m-%d %H:%M:%S')}")


def get_stock_array_price(stock_code_array):
    """获取股票实时行情数据，使用独立的多支股票缓存"""
    global _ARRAY_PRICE_CACHE

    current_time = time.time()
    print(f"当前时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 检查是否需要刷新缓存
    need_refresh = False

    # 情况1：缓存为空（首次运行）
    if not _ARRAY_PRICE_CACHE['data']:
        print("多支股票缓存为空，需要初始化")
        need_refresh = True

    # 情况2：缓存已过期且在交易时间内
    elif current_time > _ARRAY_PRICE_CACHE['expiry'] and _is_trading_time():
        print("多支股票缓存已过期且在交易时间内，需要刷新")
        need_refresh = True

    # 如果需要刷新，获取最新数据
    if need_refresh and stock_code_array:
        print(f"开始刷新多支股票缓存，股票数量: {len(stock_code_array)}")
        _refresh_array_cache(stock_code_array)

    # 返回请求的股票数据
    return _get_requested_prices_from_array_cache(stock_code_array)


def _refresh_array_cache(stock_codes):
    """刷新多支股票缓存数据"""
    global _ARRAY_PRICE_CACHE

    print("调用 get_quote_array_snowball...")
    new_prices = get_quote_array_snowball(stock_codes)
    print(f"从雪球获取到 {len(new_prices)} 条数据")

    # 清空缓存
    _ARRAY_PRICE_CACHE['data'] = {}

    # 更新缓存
    for item in new_prices:
        try:
            # 确保数据格式正确
            if len(item) < 4:
                print(f"数据格式错误: {item}")
                continue

            code = str(item[0])
            price = float(item[1])
            increase = float(item[2])
            color = str(item[3])

            _ARRAY_PRICE_CACHE['data'][code] = (price, increase, color)
            print(f"缓存股票: {code} - 价格: {price}, 涨幅: {increase}, 颜色: {color}")
        except Exception as e:
            print(f"处理股票数据错误: {item}, 错误: {e}")
            _ARRAY_PRICE_CACHE['data'][str(item[0])] = (0.0, 0.0, 'gray')

    # 更新缓存时间
    current_time = int(time.time())
    _ARRAY_PRICE_CACHE['last_updated'] = current_time
    _ARRAY_PRICE_CACHE['expiry'] = current_time + CACHE_TTL

    print(f"多支股票缓存更新完成，包含 {len(_ARRAY_PRICE_CACHE['data'])} 只股票")
    print(f"多支股票缓存过期时间: {datetime.datetime.fromtimestamp(_ARRAY_PRICE_CACHE['expiry']).strftime('%Y-%m-%d %H:%M:%S')}")


def _get_requested_prices_from_array_cache(stock_codes):
    """从多支股票缓存中提取请求的股票数据"""
    result = []

    for code in stock_codes:
        str_code = str(code)
        if str_code in _ARRAY_PRICE_CACHE['data']:
            price, increase, color = _ARRAY_PRICE_CACHE['data'][str_code]
            result.append((str_code, price, increase, color))
        else:
            # 缓存中没有的股票返回默认值
            print(f"股票 {str_code} 不在多支股票缓存中")
            result.append((str_code, 0.0, 0.0, 'gray'))

    print(f"返回 {len(result)} 只股票数据")
    print(f"前3条结果: {result[:3]}")
    return result


def _is_trading_time():
    """检查当前是否在交易时间内"""
    now = datetime.datetime.now()

    # 检查是否为交易日（周一至周五）
    if now.weekday() > 4:  # 周六日
        return False

    hour = now.hour
    minute = now.minute

    # A股、港股交易时段 (9:00-16:15)
    cn_trading = (9 <= hour <= 15) or (hour == 16 and minute < 15)

    # 美股交易时段 (21:30-5:15)
    us_trading = (21 <= hour <= 24) or (0 <= hour <= 4) or (hour == 5 and minute < 15)

    return cn_trading or us_trading




# 从akshare获取单一股票实时行情
def get_quote_akshare(stock_code):
    stock_object = Stock.objects.get(stock_code=stock_code)
    market_name = stock_object.market.market_name
    if market_name == '港股':
        # df = ak.stock_hk_spot_em()
        # price = float(df.query('代码=="' + stock_code + '"')['最新价'].iloc[0])
        # increase = float(df.query('代码=="' + stock_code + '"')['涨跌幅'].iloc[0])
        df = ak.stock_hk_spot()
        price = float(df.query('symbol=="' + stock_code + '"')['lasttrade'].iloc[0])
        increase = float(df.query('symbol=="' + stock_code + '"')['changepercent'].iloc[0])
    elif market_name == '沪市B股' or market_name == '深市B股':
        df = ak.stock_zh_b_spot_em()
        price = float(df.query('代码=="' + stock_code + '"')['最新价'].iloc[0])
        increase = float(df.query('代码=="' + stock_code + '"')['涨跌幅'].iloc[0])
    elif classify_stock_code(stock_code) == 'ETF':
        df = ak.fund_etf_spot_em()
        price = float(df.query('代码=="' + stock_code + '"')['最新价'].iloc[0])
        increase = float(df.query('代码=="' + stock_code + '"')['涨跌幅'].iloc[0])
    else:
        df = ak.stock_zh_a_spot_em()
        price = float(df.query('代码=="' + stock_code + '"')['最新价'].iloc[0])
        increase = float(df.query('代码=="' + stock_code + '"')['涨跌幅'].iloc[0])
    if increase > 0:
        color = 'red'
    elif increase < 0:
        color = 'green'
    else:
        color = 'grey'

    # df = ak.stock_bid_ask_em(symbol="600519")
    # price = df.query('item=="最新"')['value'].iloc[0]
    # print(price)
    #
    # stock_zh_a_spot_em_df = ak.stock_zh_a_spot_em()
    # print(stock_zh_a_spot_em_df.query('代码=="600036"')['最新价'].iloc[0])
    #
    # df = ak.stock_zh_b_spot_em()
    # price = df.query('代码=="200596"')['最新价'].iloc[0]
    # print(price)
    #
    # df = ak.stock_hk_spot_em()
    # price1 = df.query('代码=="00700"')['最新价'].iloc[0]
    # print(price1)
    #
    # df = ak.fund_etf_spot_em()
    # print(df.query('代码=="511880"')['最新价'].iloc[0])

    return price, increase, color


# 从雪球抓取单一股票实时行情
def get_quote_snowball(stock_code):
    stock_object = Stock.objects.get(stock_code=stock_code)
    market = stock_object.market.market_abbreviation
    if market == 'hk':
        code = stock_code
    else:
        code = market.upper() + stock_code
    url = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol=' + code
    quote_json = json.loads(getHTMLText(url))  # 将getHTMLText()返回的字符串转换为json格式的list
    price = quote_json['data'][0]['current']
    increase = quote_json['data'][0]['percent']
    if increase > 0:
        color = 'red'
    elif increase < 0:
        color = 'green'
    else:
        color = 'grey'
    return price, increase, color


# 从雪球抓取股票列表实时行情
def get_quote_array_snowball(stock_code_array):
    code_array = []
    quote_array = []
    code_str = ''
    for i in stock_code_array:
        stock_object = Stock.objects.get(stock_code=i)
        market = stock_object.market.market_abbreviation
        if market == 'hk':
            code = i
        else:
            code = market.upper() + i
        code_array.append(code)
        code_str = ','.join(code_array)
    url = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol=' + code_str
    quote_json = json.loads(getHTMLText(url))  # 将getHTMLText()返回的字符串转换为json格式的list
    data = quote_json['data']
    for i in data:
        stock_code = i['symbol']
        price = i['current']
        increase = i['percent'] / 100 if i['percent'] != None else 0
        if increase > 0:
            color = '#ef4444'  # 红色
        elif increase < 0:
            color = '#10b981'  # 绿色
        else:
            color = '#6b7280'  # 深灰色
        quote_array.append((remove_prefix(stock_code), price, increase, color))
    return quote_array


# 格式化股票代码（去掉前缀SH、SZ）
def remove_prefix(stock_code):
    stock_code = stock_code.replace('SH', '')
    stock_code = stock_code.replace('SZ', '')
    return stock_code


# 从http://qt.gtimg.cn/抓取实时行情
def get_quote_gtimg(stock_code):
    price_str = []
    stock_object = Stock.objects.get(stock_code=stock_code)
    market = stock_object.market.market_abbreviation
    if market == 'hk':
        url = 'http://qt.gtimg.cn/q=r_' + market + stock_code  # 在股票代码前面加上'r_'，用于获得实时港股行情
    else:
        url = 'http://qt.gtimg.cn/q=' + market + stock_code
    html = getHTMLText(url)
    x = html.count('~', 1, len(html))  # 获取返回字符串html中分隔符'~'的出现次数
    for i in range(0, x + 1):
        price_str.append(html.split('~')[i])  # 将html用'~'分隔后的值输出到列表price中
    price = float(price_str[3])
    increase = float(price_str[32])
    if increase > 0:
        color = 'red'
    elif increase < 0:
        color = 'green'
    else:
        color = 'grey'
    return price, increase, color


# 从http://qt.gtimg.cn/获取汇率数据
def get_rate():
    # 使用统一路径变量
    file_path = pathlib.Path("./templates/dashboard/rate.json")

    # 尝试从缓存获取数据
    if file_path.is_file():
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 检查缓存是否过期
        last_modified = datetime.datetime.strptime(data['modified_time'], "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()

        # 使用更清晰的时间判断逻辑
        if last_modified.date() != now.date() or (now - last_modified).total_seconds() >= 60:
            try:
                # 封装汇率获取逻辑
                data.update({
                    "rate_HKD": fetch_exchange_rate("whHKDCNY"),
                    "rate_USD": fetch_exchange_rate("whUSDCNY"),
                    "modified_time": now.strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as e:
                print(f"汇率更新失败: {e}")
                # 失败时保留原值，不更新修改时间
            else:
                # 只有成功时才更新文件
                save_rate_data(file_path, data)
        return format_rate_data(data)

    # 缓存文件不存在时
    try:
        rate_data = {
            "rate_HKD": fetch_exchange_rate("whHKDCNY"),
            "rate_USD": fetch_exchange_rate("whUSDCNY"),
            "modified_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"汇率初始化失败: {e}")
        rate_data = {"rate_HKD": 1, "rate_USD": 1}

    save_rate_data(file_path, rate_data)
    return format_rate_data(rate_data)


# 辅助函数：获取汇率
def fetch_exchange_rate(symbol):
    url = f"http://qt.gtimg.cn/q={symbol}"
    html = getHTMLText(url)
    return extract_rate(html)


# 辅助函数：保存数据
def save_rate_data(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 辅助函数：格式化返回数据
def format_rate_data(data):
    return {
        'CNY': 1,
        'HKD': data["rate_HKD"],
        'USD': data["rate_USD"]
    }


def extract_rate(input_str: str) -> float or None:
    """
    从输入字符串中提取HKDCNY后的汇率值。

    参数:
        input_str (str): 格式为 "字段1~字段2~HKDCNY~汇率~...~更新时间~无效内容..."

    返回:
        float or None: 解析成功的汇率值，失败返回None
    """
    # try:
    # 使用正则表达式匹配双引号之间的内容
    match = re.search(r'"(.*?)"', input_str).group(1)

    # 按分隔符拆分字符串
    fields = match.split("~")

    # 找到"HKDCNY"的位置（假设是第三个字段，索引为2）
    # if len(fields) < 4 or fields[2] != "HKDCNY":
    #     return None

    # 截断到更新时间字段（第六个字段，索引5），保留前6个字段
    valid_fields = fields[:6]

    # 提取汇率值（第四个字段，索引3）
    rate_str = valid_fields[3]
    return float(rate_str)

    # except (IndexError, ValueError, TypeError):
    #     return None


'''
def get_rate1():
    path = pathlib.Path("./templates/dashboard/rate.json")
    if path.is_file() == True:  # 若json文件存在
        # 1. 读取JSON文件
        with open('./templates/dashboard/rate.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        time1 = datetime.datetime.strptime(data['modified_time'], "%Y-%m-%d %H:%M:%S")
        time2 = datetime.datetime.now()
        # if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 3600):
        if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 60):
            # df = ak.fx_quote_baidu(symbol="人民币")
            # try:
            #     temp_HKD = float(df.query('代码=="CNYHKD"')['最新价'].iloc[0])
            # except Exception as e:
            #     temp_HKD = 0
            #     print(f"查询报错: {e}")
            # if temp_HKD != 0:
            #     rate_HKD = 1 / temp_HKD
            #     data["rate_HKD"] = rate_HKD
            # else:
            #     rate_HKD = data["rate_HKD"]
            # try:
            #     temp_USD = float(df.query('代码=="CNYUSD"')['最新价'].iloc[0])
            # except Exception as e:
            #     temp_USD = 0
            #     print(f"查询报错: {e}")
            # if temp_USD != 0:
            #     rate_USD = 1 / temp_USD
            #     data["rate_USD"] = rate_USD
            # else:
            #     rate_USD = data["rate_USD"]
            try:
                # http://qt.gtimg.cn/接口
                url = "http://qt.gtimg.cn/q=whHKDCNY"
                html = getHTMLText(url)
                rate_HKD = extract_rate(html)
                data["rate_HKD"] = rate_HKD
                url = "http://qt.gtimg.cn/q=whUSDCNY"
                html = getHTMLText(url)
                rate_USD = extract_rate(html)
                data["rate_USD"] = rate_USD

                # ak.currency_boc_sina接口
                # current_date = pd.to_datetime(datetime.date.today())
                # current_date_str = current_date.strftime("%Y%m%d") if current_date else ""
                # df = ak.currency_boc_sina(symbol="港币", start_date=current_date_str, end_date=current_date_str)
                # df['日期'] = pd.to_datetime(df['日期'])
                # rate_HKD = float(df[df['日期'] == current_date]['中行汇买价'].iloc[0] / 100)
                # data["rate_HKD"] = rate_HKD
                # df = ak.currency_boc_sina(symbol="美元", start_date=current_date_str, end_date=current_date_str)
                # df['日期'] = pd.to_datetime(df['日期'])
                # rate_USD = float(df[df['日期'] == current_date]['中行汇买价'].iloc[0] / 100)
                # data["rate_USD"] = rate_USD

                # ak.fx_spot_quote接口
                # df = ak.fx_spot_quote()
                # rate_HKD = float(df[df['货币对'] == 'HKD/CNY']['买报价'].iloc[0])
                # rate_USD = float(df[df['货币对'] == 'USD/CNY']['买报价'].iloc[0])
                # data["rate_HKD"] = rate_HKD
                # data["rate_USD"] = rate_USD

            except Exception as e:
                print(f"查询报错: {e}")
                rate_HKD = data["rate_HKD"]
                rate_USD = data["rate_USD"]

            # 2. 修改汇率数据
            data["modified_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 3. 写回JSON文件（保留原有格式）
            with open('./templates/dashboard/rate.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)  # 保持中文可读性
        else:
            rate_HKD = data["rate_HKD"]
            rate_USD = data["rate_USD"]
    else:
        # df = ak.fx_quote_baidu(symbol="人民币")
        # temp_HKD = float(df.query('代码=="CNYHKD"')['最新价'].iloc[0])
        # temp_USD = float(df.query('代码=="CNYUSD"')['最新价'].iloc[0])
        # rate_HKD = 1 / temp_HKD if temp_HKD != 0 else 1
        # rate_USD = 1 / temp_USD if temp_HKD != 0 else 1
        try:
            # http://qt.gtimg.cn/接口
            url = "http://qt.gtimg.cn/q=whHKDCNY"
            html = getHTMLText(url)
            rate_HKD = extract_rate(html)
            url = "http://qt.gtimg.cn/q=whUSDCNY"
            html = getHTMLText(url)
            rate_USD = extract_rate(html)

            # ak.currency_boc_sina接口
            # current_date = pd.to_datetime(datetime.date.today())
            # current_date_str = current_date.strftime("%Y%m%d") if current_date else ""
            # df = ak.currency_boc_sina(symbol="港币", start_date=current_date_str, end_date=current_date_str)
            # df['日期'] = pd.to_datetime(df['日期'])
            # rate_HKD = float(df[df['日期'] == current_date]['中行汇买价'].iloc[0] / 100)
            # df = ak.currency_boc_sina(symbol="美元", start_date=current_date_str, end_date=current_date_str)
            # df['日期'] = pd.to_datetime(df['日期'])
            # rate_USD = float(df[df['日期'] == current_date]['中行汇买价'].iloc[0] / 100)

            # ak.fx_spot_quote接口
            # df = ak.fx_spot_quote()
            # rate_HKD = float(df[df['货币对'] == 'HKD/CNY']['买报价'].iloc[0])
            # rate_USD = float(df[df['货币对'] == 'USD/CNY']['买报价'].iloc[0])

            rate = {}
            rate.update(rate_HKD=rate_HKD)
            rate.update(rate_USD=rate_USD)
            rate.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            # 写入json文件
            FileOperate(dictData=rate, filepath='./templates/dashboard/',
                        filename='rate.json').operation_file()
        except Exception as e:
            print(f"查询报错: {e}")
            rate_HKD = 1
            rate_USD = 1
    return rate_HKD, rate_USD


def get_rate2():
    path = pathlib.Path("./templates/dashboard/rate.json")
    if path.is_file() == True:  # 若json文件存在
        with open('./templates/dashboard/rate.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        time1 = datetime.datetime.strptime(data['modified_time'], "%Y-%m-%d %H:%M:%S")
        time2 = datetime.datetime.now()
        if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 60):
            try:
                url = "http://qt.gtimg.cn/q=whHKDCNY"
                html = getHTMLText(url)
                rate_HKD = extract_rate(html)
                data["rate_HKD"] = rate_HKD
                url = "http://qt.gtimg.cn/q=whUSDCNY"
                html = getHTMLText(url)
                rate_USD = extract_rate(html)
                data["rate_USD"] = rate_USD
            except Exception as e:
                print(f"查询报错: {e}")
                rate_HKD = data["rate_HKD"]
                rate_USD = data["rate_USD"]
            data["modified_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open('./templates/dashboard/rate.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)  # 保持中文可读性
        else:
            rate_HKD = data["rate_HKD"]
            rate_USD = data["rate_USD"]
    else:
        try:
            url = "http://qt.gtimg.cn/q=whHKDCNY"
            html = getHTMLText(url)
            rate_HKD = extract_rate(html)
            url = "http://qt.gtimg.cn/q=whUSDCNY"
            html = getHTMLText(url)
            rate_USD = extract_rate(html)
            rate = {}
            rate.update(rate_HKD=rate_HKD)
            rate.update(rate_USD=rate_USD)
            rate.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            FileOperate(dictData=rate, filepath='./templates/dashboard/',
                        filename='rate.json').operation_file()
        except Exception as e:
            print(f"查询报错: {e}")
            rate_HKD = 1
            rate_USD = 1

    rate_CNY = 1
    rate = {}
    rate['CNY'] = rate_CNY
    rate['HKD'] = rate_HKD
    rate['USD'] = rate_USD
    return rate





# 从https://wocha.cn/网站抓取汇率数据
def get_rate_wocha():
    rate_HKD = 1.0
    rate_USD = 1.0
    path = pathlib.Path("./templates/dashboard/rate.json")
    if path.is_file(): # 若json文件存在，从json文件中读取rate_HKD、rate_USD
        # 读取rate.json
        rate_dict = FileOperate(filepath='./templates/dashboard/', filename='rate.json').operation_file()
        rate_HKD = float(rate_dict['rate_HKD'])
        rate_USD = float(rate_dict['rate_USD'])
        rate_time = datetime.datetime.strptime(rate_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
    else: # 若json文件不存在，创建json文件
        rate_dict = {}
        rate_dict.update(rate_HKD=1.0)
        rate_dict.update(rate_USD=1.0)
        rate_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
        rate_dict.update(modified_time=rate_time.strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()

    d = datetime.date(datetime.datetime.now().year, datetime.datetime.now().month, datetime.datetime.now().day)
    # 若json文件中的rate_time与当前不为同一天，从https://wocha.cn/获取汇率
    if rate_time.date() != datetime.datetime.today().date():
    # if 1 == 1:
        # 获取港元汇率
        rate_HKD = getDateRate_hkd(d.strftime("%Y-%m-%d"))
        if rate_HKD != -1:
            rate_dict.update(rate_HKD=rate_HKD)
        # 获取美元汇率
        rate_USD = getDateRate_usd(d.strftime("%Y-%m-%d"))
        if rate_USD != -1:
            rate_dict.update(rate_USD=rate_USD)
        rate_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()

    return rate_HKD, rate_USD


# 从https://qq.ip138.com/网站抓取汇率数据
def get_rate_ip138():
    rate_HKD = 1.0
    rate_USD = 1.0
    path = pathlib.Path("./templates/dashboard/rate.json")
    if path.is_file():  # 若json文件存在，从json文件中读取rate_HKD、rate_USD
        # 读取rate.json
        rate_dict = FileOperate(filepath='./templates/dashboard/', filename='rate.json').operation_file()
        rate_HKD = float(rate_dict['rate_HKD'])
        rate_USD = float(rate_dict['rate_USD'])
        rate_time = datetime.datetime.strptime(rate_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
    else:  # 若json文件不存在，创建json文件
        rate_dict = {}
        rate_dict.update(rate_HKD=1.0)
        rate_dict.update(rate_USD=1.0)
        rate_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
        rate_dict.update(modified_time=rate_time.strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()
    # 若json文件中的rate_time与当前不为同一天，从https://qq.ip138.com/获取汇率
    # if rate_time.date() != datetime.datetime.today().date():
    if 1 == 1:
        # 获取港元汇率
        url_HKD = 'https://qq.ip138.com/hl.asp?from=HKD&to=CNY&q=100'
        html_HKD = getHTMLText(url_HKD)
        rate_HKD = getRate(html_HKD)
        # 网页爬虫抓取结果是否为‘暂无’？
        # if rate_HKD != -1:
        if rate_HKD > 0:
            rate_dict.update(rate_HKD=rate_HKD)
        # 以下两行用于汇率获取失败后的临时补救
        # else:
        #     rate_dict.update(rate_HKD=1)
        # 获取美元汇率
        url_USD = 'https://qq.ip138.com/hl.asp?from=USD&to=CNY&q=100'
        html_USD = getHTMLText(url_USD)
        rate_USD = getRate(html_USD)
        # 网页爬虫抓取结果是否为‘暂无’？
        # if rate_USD != -1:
        if rate_USD > 0:
            rate_dict.update(rate_USD=rate_USD)
        rate_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()

    # 调式   按日期抓取港币和美元历史汇率
    begin = datetime.date(2024, 12, 17)
    end = datetime.date(2024, 12, 19)
    d = begin
    delta = datetime.timedelta(days=1)
    while d <= end:
        print(d.strftime("%Y-%m-%d"))
        hkd_rate = getDateRate_hkd(d.strftime("%Y-%m-%d"))
        usd_rate = getDateRate_usd(d.strftime("%Y-%m-%d"))
        print(hkd_rate, usd_rate)
        # print("Start : %s" % time.ctime())
        # time.sleep(random.random()*0.2)
        # print("End : %s" % time.ctime())
        d += delta

    d = datetime.date(datetime.datetime.now().year, datetime.datetime.now().month, datetime.datetime.now().day)
    hkd_rate = getDateRate_hkd(d.strftime("%Y-%m-%d"))
    usd_rate = getDateRate_usd(d.strftime("%Y-%m-%d"))
    print(hkd_rate, usd_rate)

    return rate_HKD, rate_USD

def getRate(html):
    # print(html)
    soup = BeautifulSoup(html, 'html.parser')
    mystr = ''
    for tr in soup.find('table').children:
        if isinstance(tr, bs4.element.Tag):
            tds = tr.find_all('td')
            # print('tds=',tds)
            mystr = mystr + str(tds)
            # print('mystr=',mystr)
    # print('mystr=', mystr)
    mystr = mystr.split('<td><p>')[5]
    # print('mystr-5=',mystr)
    mystr = mystr.split('</p>')[0]
    # print('mystr-0=',mystr)
    # 网页爬虫抓取结果是否为‘暂无’？
    if mystr == '鏆傛棤' or mystr == '暂无':
        rate = -1
    else:
        rate = float(mystr)
        # 保留7位（小数点后5位）后按保留小数点后4位并四舍五入
        rate = round(float('%.7f' % rate), 4)
    # print(rate)
    return rate


def getDateRate_hkd(date):
    # url = 'https://wocha.cn/huilv/?jinri'
    # url = 'https://wocha.cn/huilv/?2024-6-1'
    url = 'https://wocha.cn/huilv/?' + date
    html = getHTMLText(url)

    # res = r'<table>(.*?)</table>'
    # n = re.findall(res, html, re.S | re.M)
    # print('n=', n)
    # res = r'<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>'
    # m = re.findall(res, html, re.S | re.M)
    # print('m=', m)

    # res = r'<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>'
    # list = re.findall(res, html, re.S | re.M)
    # print(list[2][1])

    # 正则表达式'港币</a></td><td>(.*?)</td>'取'港币</a></td><td>'和'</td>'之间的内容
    res = r'港币</a></td><td>(.*?)</td>'
    hkd_list = re.findall(res, html, re.S | re.M)
    hkd_str = ''.join(hkd_list)
    if hkd_str == '':
        hkd_rate = -1
    else:
        hkd_rate = float(hkd_str) / 100
        hkd_rate = round(float('%.7f' % hkd_rate), 4)

    # res = r'美元</a></td><td>(.*?)</td>'
    # usd_list = re.findall(res, html, re.S | re.M)
    # usd_str = ''.join(usd_list)
    # if usd_str == '':
    #    usd_rate = -1
    # else:
    #    usd_rate = float(usd_str) / 100
    #    usd_rate = round(float('%.7f' % usd_rate), 4)

    return hkd_rate


def getDateRate_usd(date):
    # url = 'https://wocha.cn/huilv/?jinri'
    # url = 'https://wocha.cn/huilv/?2024-6-1'
    url = 'https://wocha.cn/huilv/?' + date
    html = getHTMLText(url)

    # res = r'<table>(.*?)</table>'
    # n = re.findall(res, html, re.S | re.M)
    # print('n=', n)
    # res = r'<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>'
    # m = re.findall(res, html, re.S | re.M)
    # print('m=', m)

    # res = r'<td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td>'
    # list = re.findall(res, html, re.S | re.M)
    # print(list[2][1])

    # 正则表达式'港币</a></td><td>(.*?)</td>'取'港币</a></td><td>'和'</td>'之间的内容
    # res = r'港币</a></td><td>(.*?)</td>'
    # hkd_list = re.findall(res, html, re.S | re.M)
    # hkd_str = ''.join(hkd_list)
    # if hkd_str == '':
    #    hkd_rate = -1
    # else:
    #    hkd_rate = float(hkd_str) / 100
    #    hkd_rate = round(float('%.7f' % hkd_rate), 4)

    res = r'美元</a></td><td>(.*?)</td>'
    usd_list = re.findall(res, html, re.S | re.M)
    usd_str = ''.join(usd_list)
    if usd_str == '':
        usd_rate = -1
    else:
        usd_rate = float(usd_str) / 100
        usd_rate = round(float('%.7f' % usd_rate), 4)

    return usd_rate



'''


# 从https://stock.xueqiu.com/网站抓取股票历史分红数据
def get_stock_dividend_history(stock_code):
    stock_object = Stock.objects.get(stock_code=stock_code)
    market = stock_object.market.market_abbreviation
    stock_dividend_history_list = []

    # 使用雪球账号登录后的cookie，只需替换xq_a_token
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36",
        "Cookie": "xq_a_token=8d6d5dcdfd4fa6e92ede143ee82276bc107c9fd4;"
    }
    # headers = {
    #     "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36",
    #     'Cookie':   'cookiesu=491738051267842; '
    #                 'device_id=b043d2601995dbbb5aa7312b27832e20; '
    #                 'Hm_lvt_1db88642e346389874251b5a1eded6e3=1742526598; '
    #                 'HMACCOUNT=B120DF9442E09CC4; '
    #                 'remember=1; '
    #                 'xq_a_token=f266c9393dc766b17cb5694f0510606e7e7f9256; '
    #                 'xqat=f266c9393dc766b17cb5694f0510606e7e7f9256; '
    #                 'xq_id_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOjE2ODI2NjI4MjAsImlzcyI6InVjIiwiZXhwIjoxNzQ5NDQzNTM1LCJjdG0iOjE3NDcyNjc5NTc0MjgsImNpZCI6ImQ5ZDBuNEFadXAifQ.S38DWHfWAvd4s-kUzjBvc9aeDe6QRDMBtI51bwqakXdamdQtsyQVmQOmR8h1jSHtTJO9I72qsX5aF02H6Bb0c-e6qFAfoIRhJrbLtic4ik3UcASlR-L7p1Is6Ix9YDR0h0AgFx3cMdzzZEivzO-y8k8emXrU0CJUtDWy2fPdTEDUbHxt0b2wvftofluo5BY0DjLi9CVEPTIuU6FqbWldMR_4gZVPbDTq4UIB7yeRXM-EYvM8T_sLj3EKZhPpTXJizQHTp-06qqfDzM9rxoSsdjWkZmgWcPKb5Qa4a_rVFDWtm22JgfolTDXZkndRC7UR_dVeKn54O1LjhhT0YTWGOw;'
    #                 'xq_r_token=7fcdd7f2e943a91f55daee0fb28c2e36cfc7f482; '
    #                 'xq_is_login=1; '
    #                 'u=1682662820; '
    #                 'is_overseas=0; '
    #                 'Hm_lpvt_1db88642e346389874251b5a1eded6e3=1745808363; '
    # }

    session = requests.Session()

    if market == 'sh' or market == 'sz':
        url = 'https://stock.xueqiu.com/v5/stock/f10/cn/bonus.json?symbol=' + market.upper() + stock_code + '&size=10000&page=1&extend=true'
        page_json = session.get(url=url, headers=headers, timeout=30).json()
        stock_dividend_dict = page_json['data']['items']
        for i in stock_dividend_dict:
            dict_tmp = {}
            dict_tmp['reporting_period'] = i['dividend_year']
            dict_tmp['dividend_plan'] = i['plan_explain']
            dict_tmp['announcement_date'] = ''
            dict_tmp['registration_date'] = timeStamp13_2_date(i['equity_date'])
            dict_tmp['ex_right_date'] = timeStamp13_2_date(i['ashare_ex_dividend_date'])
            dict_tmp['dividend_date'] = timeStamp13_2_date(i['ex_dividend_date'])
            stock_dividend_history_list.append(dict_tmp)
    elif market == 'hk':
        url = 'https://stock.xueqiu.com/v5/stock/f10/hk/bonus.json?symbol=' + stock_code + '&size=1000&page=1&extend=true'
        page_json = session.get(url=url, headers=headers, timeout=30).json()
        stock_dividend_dict = page_json['data']['items']
        for i in stock_dividend_dict:
            dict_tmp = {}
            dict_tmp['reporting_period'] = ''
            dict_tmp['dividend_plan'] = i['divdstep']
            dict_tmp['announcement_date'] = ''
            dict_tmp['registration_date'] = ''
            dict_tmp['ex_right_date'] = timeStamp13_2_date(i['dertsdiv'])
            dict_tmp['dividend_date'] = timeStamp13_2_date(i['datedivpy'])
            stock_dividend_history_list.append(dict_tmp)
    else:
        url = 'https://stock.xueqiu.com/v5/stock/f10/us/bonus.json?symbol=' + stock_code + '&size=1000&page=1&extend=true'
        page_json = session.get(url=url, headers=headers, timeout=30).json()
        stock_dividend_dict = page_json['data']['items']
        for i in stock_dividend_dict:
            dict_tmp = {}
            dict_tmp['reporting_period'] = ''
            dict_tmp['dividend_plan'] = i['explain']
            dict_tmp['announcement_date'] = timeStamp13_2_date(i['announcement_date'])
            dict_tmp['registration_date'] = ''
            dict_tmp['ex_right_date'] = timeStamp13_2_date(i['exright_date'])
            dict_tmp['dividend_date'] = timeStamp13_2_date(i['dividend_date'])
            stock_dividend_history_list.append(dict_tmp)
    return stock_dividend_history_list


def get_stock_dividend_history_2lines(stock_code):
    stock_object = Stock.objects.get(stock_code=stock_code)
    market = stock_object.market.market_abbreviation
    stock_dividend_history_list = []

    # 使用雪球账号登录后的cookie
    # headers = {
    #     "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36",
    #     'Cookie': 'device_id=79ed3ae94c7946784a708f25b6aebcbc; '
    #               'Hm_lvt_1db88642e346389874251b5a1eded6e3=1649310073; '
    #               's=bx171kn59d; '
    #               'remember=1; '
    #               'xq_a_token=e346c88419efc81408e75d9d84ea652027032bda; '
    #               'xqat=e346c88419efc81408e75d9d84ea652027032bda; '
    #               'xq_id_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOjE2ODI2NjI4MjAsImlzcyI6InVjIiwi'
    #               'ZXhwIjoxNjUxODg5NDc2LCJjdG0iOjE2NDkzODQ4OTQyMDMsImNpZCI6ImQ5ZDBuNEFadXAifQ.mTaEjcPN2L0Ohd'
    #               '2idDsrekbmYddMR8bUak2FgDXbi27JdYOeKubiMiYi2fIEvBJ9ekxi4rshi6JpuqWv10Zy0FLxU8sVLDJYRl2dE6K'
    #               'BmhuGgEkVUuQyOHDpZbIX4BDQzozucipmD3l2L48wtNY6mHMeWJ2KWAK1PVLiRAvnulk4kDbOPoe7DNmmqMrkazb6'
    #               'scWzRRxqLhLEBJvteKeRd-HoMCDc49AKI_W6Uf39QUCr_k4Kc7c2tWy0EWI5DA-S_gnn9hoEqvO6VfEANW2_nTD-p'
    #               'UOUsfFvr-a4IfEaONaODlvenelTaHWnwBiKHNT--VASqNPtJJqOyPrapysiaQ; '
    #               'xq_r_token=cac1abdcce297edbd7c9dda7c5a7c35167270cdc; '
    #               'xq_is_login=1; '
    #               'u=1682662820; '
    #               'Hm_lpvt_1db88642e346389874251b5a1eded6e3=1649384895'
    # }

    # 使用未登录雪球的cookie，只保留_token的值， 一段时间后会失效？？
    # headers = {
    #     "User-Agent": "Mozilla/5.0",
    #     "Cookie": "xq_a_token=f1e4545cb0f3cfb17acc98ad7a298b8106f55e86; "
    #               "xq_r_token=f5d9f889384a1b3b886c6a67f79bd30c74aaeb1c; "
    #               "xq_id_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOi0xLCJpc3MiOiJ1YyIsImV4cCI6MTY1MTQ"
    #               "0NzY3MywiY3RtIjoxNjQ5MzkwMDI4MjY4LCJjaWQiOiJkOWQwbjRBWnVwIn0.PoJMwn3BsuM4BIyMbtsioTXIdMZDa75"
    #               "DOLgyL-dyqahufvDcnsv9xH_mKmx54PRGQ1qUZPj_gzhhIqAFoaNqQnb305FvVr6VmZ-6Dzgjmt9lS4C2up6zdlgg9BC"
    #               "MU5cltTM21yx49VtyIJz1Pvgpn75o6Ydsr4vWayG8sIlDx0SC2Kaynrc0F_5cHLANE6uYkchwWAA6ULi21odD4ZI4Oj4"
    #               "0yvOolgo5XzUS878g7bcLQcewvSOTrqXUmA87LvO21nZ2Q2CNr-Ux2Zz5wg7ud7EE7tJmQMQ2gfVo0Zhvob2Nm68F7tT"
    #               "r03_T2KU9ddJtII2Leha7sX_5RjswPIKSaA"
    # }

    # 使用未登录雪球的完整cookie
    # headers = {
    #     "User-Agent": "Mozilla/5.0",
    #     "Cookie": "device_id=79ed3ae94c7946784a708f25b6aebcbc; "
    #               "s=bx171kn59d; bid=b336830f120a0f7d04d425a0e3c3455f_l1q98uis; "
    #               "Hm_lvt_1db88642e346389874251b5a1eded6e3=1649407616,1649410023,1649472317,1650003400; "
    #               "snbim_minify=true; "
    #               "xq_a_token=7a84ec3929cd1e60abe21a2c26b9292767c1bd62; "
    #               "xqat=7a84ec3929cd1e60abe21a2c26b9292767c1bd62; "
    #               "xq_r_token=1b89b595a3ae0881d42538acf4948a94fd506777; "
    #               "xq_id_token=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1aWQiOi0xLCJpc3MiOiJ1YyIsImV4cCI6MTY1Mjc0Mzcw"
    #               "MywiY3RtIjoxNjUwMTcxOTc0NzcyLCJjaWQiOiJkOWQwbjRBWnVwIn0.X1af2x-iOamO8UNvMnCDFFR9GDlnOB87hVzsVXi-n"
    #               "CrePKUqVP7F1MRPVntas3XKBfJbkBz2E09HxujvQpa53rpsqQZljGrrd8hmBJortsEvoRMo9KvgoI6USsKusvpjB9xtdDkOQu"
    #               "rzdwtA5IJ0XS4--TTM2VD15JgvJ6flAQUobqazcQXonUI65JERbzfgdjYv1VASFYK6Yr9vAyrgjpkKtEIZ33wAyGZHGFfu-y8"
    #               "bSJhJDvKkGHkJ4lDYyw45NcBcZdgISzbmUbVu1qOzhRgYNEfO0DV9QWcLgtRlW1SvbFhB4SOJ2GWJMmXGJkCsXLe3tKzJfomc"
    #               "KOpIfG8SwQ; "
    #               "u=681650171995983; "
    #               "is_overseas=0; "
    #               "Hm_lpvt_1db88642e346389874251b5a1eded6e3=1650172044"
    # }

    # 自动处理cookie爬取雪球网
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36"
    }
    # 第一步,向雪球网首页发送一条请求,获取cookie
    session.get(url="https://xueqiu.com", headers=headers)
    # 第二步,获取动态加载的数据
    # page_json = session.get(url=url, headers=headers).json()
    # print(page_json)

    if market == 'sh' or market == 'sz':
        url = 'https://stock.xueqiu.com/v5/stock/f10/cn/bonus.json?symbol=' + market.upper() + stock_code + '&size=2&page=1&extend=true'
        # page_json = requests.get(url=url, headers=headers, timeout=30).json()
        page_json = session.get(url=url, headers=headers, timeout=30).json()
        stock_dividend_dict = page_json['data']['items']
        # print(stock_dividend_dict)
        for i in stock_dividend_dict:
            dict_tmp = {}
            dict_tmp['reporting_period'] = i['dividend_year']
            dict_tmp['dividend_plan'] = i['plan_explain']
            dict_tmp['announcement_date'] = ''
            dict_tmp['registration_date'] = timeStamp13_2_date(i['equity_date'])
            dict_tmp['ex_right_date'] = timeStamp13_2_date(i['ashare_ex_dividend_date'])
            dict_tmp['dividend_date'] = timeStamp13_2_date(i['ex_dividend_date'])
            stock_dividend_history_list.append(dict_tmp)
    elif market == 'hk':
        url = 'https://stock.xueqiu.com/v5/stock/f10/hk/bonus.json?symbol=' + stock_code + '&size=2&page=1&extend=true'
        # page_json = requests.get(url=url, headers=headers, timeout=30).json()
        page_json = session.get(url=url, headers=headers, timeout=30).json()
        stock_dividend_dict = page_json['data']['items']
        for i in stock_dividend_dict:
            dict_tmp = {}
            dict_tmp['reporting_period'] = ''
            dict_tmp['dividend_plan'] = i['divdstep']
            dict_tmp['announcement_date'] = ''
            dict_tmp['registration_date'] = ''
            dict_tmp['ex_right_date'] = timeStamp13_2_date(i['dertsdiv'])
            dict_tmp['dividend_date'] = timeStamp13_2_date(i['datedivpy'])
            stock_dividend_history_list.append(dict_tmp)
    else:
        url = 'https://stock.xueqiu.com/v5/stock/f10/us/bonus.json?symbol=' + stock_code + '&size=2&page=1&extend=true'
        # page_json = requests.get(url=url, headers=headers, timeout=30).json()
        page_json = session.get(url=url, headers=headers, timeout=30).json()
        stock_dividend_dict = page_json['data']['items']
        for i in stock_dividend_dict:
            dict_tmp = {}
            dict_tmp['reporting_period'] = ''
            dict_tmp['dividend_plan'] = i['explain']
            dict_tmp['announcement_date'] = timeStamp13_2_date(i['announcement_date'])
            dict_tmp['registration_date'] = ''
            dict_tmp['ex_right_date'] = timeStamp13_2_date(i['exright_date'])
            dict_tmp['dividend_date'] = timeStamp13_2_date(i['dividend_date'])
            stock_dividend_history_list.append(dict_tmp)
    return stock_dividend_history_list


# 从雪球网抓取股票分红日期
def get_dividend_date(stock_dividend_dict):
    # date_now = datetime.datetime.strptime(datetime.datetime.now().strftime('%Y-%m-%d'), '%Y-%m-%d')
    date_now = datetime.datetime.now().strftime('%Y-%m-%d')
    if len(stock_dividend_dict) == 0:
        last_dividend_date = None
        next_dividend_date = None
    elif len(stock_dividend_dict) == 1:
        date_0 = stock_dividend_dict[0]['dividend_date']
        if date_0 == 'None':
            next_dividend_date = None
            last_dividend_date = None
        elif date_0 > date_now:
            next_dividend_date = date_0
            last_dividend_date = None
        else:
            next_dividend_date = None
            last_dividend_date = date_0
    else:
        # date_0 = datetime.datetime.strptime(stock_dividend_dict[0]['dividend_date'], '%Y-%m-%d')
        date_0 = stock_dividend_dict[0]['dividend_date']
        date_1 = stock_dividend_dict[1]['dividend_date']
        if date_0 == 'None':
            next_dividend_date = None
            last_dividend_date = date_1
        else:
            if date_0 > date_now:
                next_dividend_date = date_0
                last_dividend_date = date_1
            else:
                next_dividend_date = None
                last_dividend_date = date_0
    return next_dividend_date, last_dividend_date


def getHTMLText(url):
    try:
        kv = {'user-agent': 'Mozilla/5.0'}
        # start = time.time() # 用于调试性能
        s = requests.Session()
        r = s.get(url, headers=kv, timeout=30)
        # r = requests.get(url, headers=kv, timeout=30)
        # print(url) # 用于调试性能
        # print(f'it took {time.time() - start} seconds to process the request') # 用于调试性能
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        # r.encoding = 'gb2312'
        # r.encoding = 'gbk'
        r.encoding = 'utf-8'
        return r.text
    except:
        print('获取网页失败')
        return '获取网页失败'


# 从指数历史数据生成json文件
def get_his_index1():
    # 上证指数
    item = []
    data = []
    df = ak.stock_zh_index_daily(symbol="sh000001").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_sh000001 = df.to_dict(orient='records')

    # 深证成份指数
    item = []
    data = []
    df = ak.stock_zh_index_daily(symbol="sz399001").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_sz399001 = df.to_dict(orient='records')

    # 创业板指数
    item = []
    data = []
    df = ak.stock_zh_index_daily(symbol="sz399006").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    # 添加akshare缺失年份的新数据
    new_years_data = [2009, 1000.00]
    data.append(new_years_data)
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_sz399006 = df.to_dict(orient='records')

    # 沪深300指数
    item = []
    data = []
    # df = ak.stock_zh_index_daily_em(symbol="sh000300").sort_values(by='date',ascending=False)
    # current_year = datetime.datetime.strptime(df.head(1)['date'].iloc[0], "%Y-%m-%d").year
    df = ak.stock_zh_index_daily(symbol="sh000300").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        # year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_sh000300 = df.to_dict(orient='records')

    # 沪深300全收益指数
    item = []
    data = []
    df = ak.stock_zh_index_hist_csindex(symbol="H00300", start_date="20120101", end_date="20250610").sort_values(
        by='日期', ascending=False)
    # df['日期'] = pd.to_datetime(df['日期'])
    # current_H00300 = float(df[df['日期'] == '2025-06-09']['收盘'].iloc[0])
    current_year = df.head(1)['日期'].iloc[0].year
    current_latest = float(df.head(1)['收盘'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        # year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        year = row['日期'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['收盘']))
            data.append(item)
            item = []
    # 添加akshare缺失年份的新数据
    data.extend([
        [2009, 3739.99],
        [2010, 3306.94],
        [2011, 2511.63]
    ])

    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_H00300 = df.to_dict(orient='records')

    # 恒生指数
    item = []
    data = []
    # df = ak.stock_hk_index_daily_em(symbol="HSI").sort_values(by='date',ascending=False)
    # current_year = datetime.datetime.strptime(df.head(1)['date'].iloc[0], "%Y-%m-%d").year
    # current_latest = float(df.head(1)['latest'].iloc[0])
    df = ak.stock_hk_index_daily_sina(symbol="HSI").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        # year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_HSI = df.to_dict(orient='records')

    # 国企指数
    item = []
    data = []
    df = ak.stock_hk_index_daily_sina(symbol="HSCEI").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        # year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_HSCEI = df.to_dict(orient='records')

    # 恒生科技指数
    item = []
    data = []
    df = ak.stock_hk_index_daily_sina(symbol="HSTECH").sort_values(by='date', ascending=False)
    current_year = df.head(1)['date'].iloc[0].year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        # year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    # 添加akshare缺失年份的新数据
    data.extend([
        [2015, 3309.53],
        [2016, 3668.26],
        [2017, 5549.89],
        [2018, 3460.42],
        [2019, 4714.81]
    ])
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_HSTECH = df.to_dict(orient='records')

    # 标普500指数
    item = []
    data = []
    df = ak.index_us_stock_sina(symbol=".INX").sort_values(by='date', ascending=False)  # 标普500指数历史
    current_year = df.head(1)['date'].iloc[0].year
    current_close = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_close)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_INX = df.to_dict(orient='records')

    # 道琼斯指数
    item = []
    data = []
    df = ak.index_us_stock_sina(symbol=".DJI").sort_values(by='date', ascending=False)  # 标普500指数历史
    current_year = df.head(1)['date'].iloc[0].year
    current_close = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_close)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_DJI = df.to_dict(orient='records')

    # 纳斯达克指数
    item = []
    data = []
    df = ak.index_us_stock_sina(symbol=".IXIC").sort_values(by='date', ascending=False)  # 标普500指数历史
    current_year = df.head(1)['date'].iloc[0].year
    current_close = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_close)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = row['date'].year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_IXIC = df.to_dict(orient='records')

    baseline = {}
    baseline.update(上证指数=dict_data_sh000001)
    baseline.update(深证成份指数=dict_data_sz399001)
    baseline.update(创业板指数=dict_data_sz399006)
    baseline.update(沪深300指数=dict_data_sh000300)
    baseline.update(沪深300全收益指数=dict_data_H00300)
    baseline.update(恒生指数=dict_data_HSI)
    baseline.update(国企指数=dict_data_HSCEI)
    baseline.update(恒生科技指数=dict_data_HSTECH)
    baseline.update(标普500指数=dict_data_INX)
    baseline.update(道琼斯指数=dict_data_DJI)
    baseline.update(纳斯达克指数=dict_data_IXIC)
    # 打时间戳
    baseline.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # 写入json文件
    FileOperate(dictData=baseline, filepath='./templates/dashboard/', filename='baseline.json').operation_file()

    return


def get_his_index():
    # 定义指数配置
    index_configs = [
        {
            'name': '上证指数',
            'symbol': 'sh000001',
            'func': ak.stock_zh_index_daily,
            'manual_data': []
        },
        {
            'name': '深证成份指数',
            'symbol': 'sz399001',
            'func': ak.stock_zh_index_daily,
            'manual_data': []
        },
        {
            'name': '创业板指数',
            'symbol': 'sz399006',
            'func': ak.stock_zh_index_daily,
            'manual_data': [[2009, 1000.00]]
        },
        {
            'name': '沪深300指数',
            'symbol': 'sh000300',
            'func': ak.stock_zh_index_daily,
            'manual_data': []
        },
        {
            'name': '沪深300全收益指数',
            'symbol': 'H00300',
            'func': ak.stock_zh_index_hist_csindex,
            'func_kwargs': {
                'start_date': "20120101",
                'end_date': datetime.datetime.now().strftime("%Y%m%d")  # 使用当前日期
            },
            'date_col': '日期',
            'close_col': '收盘',
            'manual_data': [
                [2009, 3739.99],
                [2010, 3306.94],
                [2011, 2511.63]
            ]
        },
        {
            'name': '恒生指数',
            'symbol': 'HSI',
            'func': ak.stock_hk_index_daily_sina,
            'manual_data': []
        },
        {
            'name': '国企指数',
            'symbol': 'HSCEI',
            'func': ak.stock_hk_index_daily_sina,
            'manual_data': []
        },
        {
            'name': '恒生科技指数',
            'symbol': 'HSTECH',
            'func': ak.stock_hk_index_daily_sina,
            'manual_data': [
                [2015, 3309.53],
                [2016, 3668.26],
                [2017, 5549.89],
                [2018, 3460.42],
                [2019, 4714.81]
            ]
        },
        {
            'name': '标普500指数',
            'symbol': '.INX',
            'func': ak.index_us_stock_sina,
            'manual_data': []
        },
        {
            'name': '道琼斯指数',
            'symbol': '.DJI',
            'func': ak.index_us_stock_sina,
            'manual_data': []
        },
        {
            'name': '纳斯达克指数',
            'symbol': '.IXIC',
            'func': ak.index_us_stock_sina,
            'manual_data': []
        }
    ]

    baseline = {}

    for config in index_configs:
        try:
            print(f"\nProcessing {config['name']} ({config['symbol']})...")

            # 获取数据
            func_kwargs = config.get('func_kwargs', {})
            if not func_kwargs:
                df = config['func'](symbol=config['symbol'])
                print(f"Data shape: {df.shape}")
            else:
                df = config['func'](symbol=config['symbol'], **func_kwargs)
                print(f"Data shape: {df.shape}")

            # 检查数据是否为空
            if df.empty:
                print(f"Warning: No data for {config['name']}")
                baseline[config['name']] = []
                continue

            # 排序数据
            date_col = config.get('date_col', 'date')
            close_col = config.get('close_col', 'close')

            print(f"Date column: {date_col}, Close column: {close_col}")
            print(f"Columns in DataFrame: {list(df.columns)}")

            # 确保日期列是datetime类型
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(by=date_col, ascending=False)

            # 提取年份和收盘价
            data = []

            # 添加最新数据
            current_year = df.iloc[0][date_col].year
            current_close = float(df.iloc[0][close_col])
            data.append([current_year, current_close])
            print(f"Latest data: {current_year}, {current_close}")

            # 提取每年数据
            for index, row in df.iterrows():
                year = row[date_col].year
                if year != current_year:
                    current_year = year
                    data.append([year, float(row[close_col])])

            # 添加手动数据
            data.extend(config['manual_data'])

            # 转换为DataFrame并排序
            df_result = pd.DataFrame(data, columns=['Year', 'ClosingPrice'])
            df_result = df_result.drop_duplicates(subset='Year', keep='first')  # 确保每年只有一条记录
            df_result = df_result.sort_values(by='Year')

            dict_data = df_result.to_dict(orient='records')
            baseline[config['name']] = dict_data

            print(f"Successfully processed {config['name']} with {len(dict_data)} records")

        except Exception as e:
            print(f"Error processing {config['name']}: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印完整的错误堆栈
            baseline[config['name']] = []

    # 添加时间戳
    baseline['modified_time'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 打印baseline内容以调试
    print("\nBaseline content:")
    for key, value in baseline.items():
        if key != 'modified_time':
            print(f"{key}: {len(value)} records")
        else:
            print(f"{key}: {value}")

    # 写入JSON文件
    try:
        FileOperate(dictData=baseline, filepath='./templates/dashboard/', filename='baseline.json').operation_file()
        print("JSON file written successfully")
    except Exception as e:
        print(f"Error writing JSON file: {str(e)}")
        # 尝试直接使用json模块写入文件
        try:
            with open('./templates/dashboard/baseline.json', 'w', encoding='utf-8') as f:
                json.dump(baseline, f, ensure_ascii=False, indent=4)
            print("JSON file written using json module")
        except Exception as e2:
            print(f"Error writing JSON file with json module: {str(e2)}")

    return


# 从指数当年数据更新json文件
def get_current_index(baseline_name_array):
    # 1. 读取JSON文件
    # baseline = FileOperate(filepath='./templates/dashboard/', filename='baseline.json').operation_file()
    with open('./templates/dashboard/baseline.json', 'r', encoding='utf-8') as f:
        baseline = json.load(f)
    current_year = datetime.datetime.now().year
    for baseline_name in baseline_name_array:
        if baseline_name == '上证指数':
            # 上证指数
            df = ak.stock_zh_index_spot_sina()
            current_price = float(df[df['代码'] == 'sh000001']['最新价'].iloc[0])
        elif baseline_name == '深证成份指数':
            # 深证成份指数
            df = ak.stock_zh_index_spot_sina()
            current_price = float(df[df['代码'] == 'sz399001']['最新价'].iloc[0])
        elif baseline_name == '创业板指数':
            # 创业板指数
            df = ak.stock_zh_index_spot_sina()
            current_price = float(df[df['代码'] == 'sz399006']['最新价'].iloc[0])
        elif baseline_name == '沪深300指数':
            # 沪深300指数
            df = ak.stock_zh_index_spot_sina()
            current_price = float(df[df['代码'] == 'sh000300']['最新价'].iloc[0])
        elif baseline_name == '沪深300全收益指数':
            # 沪深300全收益指数
            end_date_str = datetime.datetime.now().strftime('%Y%m%d')
            start_date_str = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y%m%d')
            df = ak.stock_zh_index_hist_csindex(symbol="H00300", start_date=start_date_str,
                                                end_date=end_date_str).sort_values(by='日期', ascending=False)
            current_price = float(df.head(1)['收盘'].iloc[0])
        elif baseline_name == '恒生指数':
            # 恒生指数
            df = ak.stock_hk_index_spot_sina()
            current_price = float(df[df['代码'] == 'HSI']['最新价'].iloc[0])
        elif baseline_name == '国企指数':
            # 国企指数
            df = ak.stock_hk_index_spot_sina()
            current_price = float(df[df['代码'] == 'HSCEI']['最新价'].iloc[0])
        elif baseline_name == '恒生科技指数':
            # 恒生科技指数
            df = ak.stock_hk_index_spot_sina()
            current_price = float(df[df['代码'] == 'HSTECH']['最新价'].iloc[0])
        elif baseline_name == '标普500指数':
            # 标普500指数
            df = ak.index_us_stock_sina(symbol=".INX").sort_values(by='date', ascending=False).head(1)
            current_price = float(df['close'].iloc[0])
        elif baseline_name == '道琼斯指数':
            # 道琼斯指数
            df = ak.index_us_stock_sina(symbol=".DJI").sort_values(by='date', ascending=False).head(1)
            current_price = float(df['close'].iloc[0])
        elif baseline_name == '纳斯达克指数':
            # 纳斯达克指数
            df = ak.index_us_stock_sina(symbol=".IXIC").sort_values(by='date', ascending=False).head(1)
            current_price = float(df['close'].iloc[0])
        else:
            current_price = 0
        for item in baseline[baseline_name]:
            if item["Year"] == current_year:
                item["ClosingPrice"] = current_price  # 替换成你的新数值
                # print(baseline_name,current_year,current_price)
                break  # 找到后立即退出循环
    baseline["modified_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. 写回JSON文件（保留原有格式）
    with open('./templates/dashboard/baseline.json', 'w', encoding='utf-8') as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)  # 保持中文可读性

    return


def get_baseline_closing_price(baseline_object, target_year):
    closing_price = 0
    for r in baseline_object:
        if r['Year'] == target_year:
            closing_price = r['ClosingPrice']
            break
    return float(closing_price)


# 从基金明细表获取当前基金的最大记账日期
def get_max_date(fund_id):
    max_date = FundHistory.objects.filter(fund_id=fund_id).aggregate(max_date=Max('date'))['max_date']
    return max_date


# 从基金明细表获取当前基金的最小记账日期
def get_min_date(fund_id):
    min_date = FundHistory.objects.filter(fund_id=fund_id).aggregate(min_date=Min('date'))['min_date']
    return min_date


# 从基金明细表获取当前基金的第二大记账日期
def get_second_max_date(fund_id):
    max_date = FundHistory.objects.filter(fund_id=fund_id).aggregate(max_date=Max('date'))['max_date']
    second_max_date = \
        FundHistory.objects.filter(fund_id=fund_id).exclude(date=max_date).order_by('-date').values_list('date',
                                                                                                            flat=True)[
            0]
    # second_max_date = fund_history.objects.filter(fund_id=fund_id).order_by('-date').values_list('date', flat=True)[1]
    # third_max_date = fund_history.objects.filter(fund_id=fund_id).order_by('-date').values_list('date', flat=True)[2]
    return second_max_date


# 从基金明细表获取指定年份的年末日期
def get_year_end_date(fund_id, year):
    year_end_date = None
    year_end_date = FundHistory.objects.filter(fund_id=fund_id, date__year=year).aggregate(max_date=Max('date'))[
        'max_date']
    return year_end_date


'''
# 返回二维列表的第1列，用于二维列表按第1列排序
def take_col1(list):
    return float(list[0])


# 返回二维列表的第2列，用于二维列表按第2列排序
def take_col2(list):
    return float(list[1])


# 返回二维列表的第3列，用于二维列表按第3列排序
def take_col3(list):
    return float(list[2])


# 返回二维列表的第4列，用于二维列表按第4列排序
def take_col4(list):
    return float(list[3])


# 返回二维列表的第6列，用于二维列表按第6列排序
def take_col6(list):
    return float(list[5])

# 返回二维列表的第7列，用于二维列表按第7列排序
def take_col8(list):
    return float(list[7])


# 返回二维列表的第10列，用于二维列表按第10列排序
def take_col7(list):
    return float(list[6])
'''


# 时间戳（10位）转日期格式
def timeStamp10_2_date(timeStamp):
    return time.strftime("%Y-%m-%d", time.localtime(timeStamp))


# 时间戳（13位）转日期格式
def timeStamp13_2_date(timeStamp):
    if str(timeStamp) != 'None':
        return time.strftime("%Y-%m-%d", time.localtime(timeStamp / 1000))
    else:
        return 'None'


'''
# 从tushare获取股票行情
def get_quote_tushare():
    # 设置 Tushare Pro token
    ts.set_token('02b13d21dd01b2682f10173d8003b92e1a8ff778695b8cf929169250')

    # 初始化 Tushare Pro API
    pro = ts.pro_api()

    # 拉取数据
    data = pro.hk_daily(**{
        "ts_code": "00700.HK",  # 股票代码
        "start_date": 20250115,  # 开始日期
        "end_date": 20250120,  # 结束日期
    }, fields=[
        "ts_code",  # 交易日期
        "open",  # 开盘价
        "high",  # 最高价
        "low",  # 最低价
        "close",  # 收盘价
        "pct_chg",  # 涨跌幅
        "vol",  # 成交量
        "trade_date"  # 交易日期
    ])

    # 显示数据
    print(data)
    print(data.iloc[0].iloc[4])
    print(data.iloc[0,4])


    df = pro.daily(ts_code='600519.SH', start_date='20230103', end_date='20230105')
    print("pro.daily(ts_code='600519.SH', start_date='20230103', end_date='20230105')")
    print(df.tail())
    print(df['close'])

    df = pro.hk_daily(ts_code='00700.HK', start_date='20190904', end_date='20190905')
    print("pro.hk_daily(ts_code='00700.HK', start_date='20190904', end_date='20190905')")
    print(df)
    print(df['close'])

    # sina数据
    df = ts.realtime_quote(ts_code='511880.SH,200596.SZ,000001.SZ,000300.SH')
    print("ts.realtime_quote(ts_code='600000.SH,600036.SH,000001.SZ,000300.SH')")
    print(df.iloc[0,6])

    # 东财数据
    df = ts.realtime_quote(ts_code='511880.SH', src='dc')
    print("ts.realtime_quote(ts_code='600000.SH', src='dc')")
    print(df.iloc[0].iloc[6])


    df = ts.get_realtime_quotes('200596')[['name', 'price', 'pre_close', 'date', 'time']]
    #df1 = pd.DataFrame(df)
    print("ts.get_realtime_quotes('600000')[['name', 'price', 'pre_close', 'date', 'time']]")
    print(df['name'].iloc[0])
    print(df['date'].iloc[0])
    print(df['price'].iloc[0])
    #print(df)

    #stock_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
    #print(stock_basic.head())
    return
'''


def get_akshare():
    # https://finance.sina.com.cn/realstock/company/shh00300/nc.shtml
    '''
    stock_zh_a_hist_df = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20250101", end_date="20250120", adjust="")
    print(stock_zh_a_hist_df)
    print(stock_zh_a_hist_df['收盘'])

    stock_hk_hist_df = ak.stock_hk_hist(symbol="00700", start_date="20250101", end_date="20250120", adjust="")
    print(stock_hk_hist_df)
    print(stock_hk_hist_df['收盘'])

    stock_zh_b_daily_df = ak.stock_zh_b_daily(symbol='sz200596', start_date='20250101', end_date='20250120', adjust='')
    print(stock_zh_b_daily_df)

    fund_etf_hist_em_df = ak.fund_etf_hist_em(symbol="000300", period="daily", start_date="20250101", end_date="20250120", adjust="")
    print(fund_etf_hist_em_df)

    fund_etf_hist_em_df = ak.fund_etf_hist_em(symbol="511880", period="daily", start_date="20250101", end_date="20250120", adjust="")
    print(fund_etf_hist_em_df)

    #index_investing_global_df = ak.index_investing_global(country="美国", index_name="VIX恐慌指数", period="每月", start_date="2005-01-01", end_date="2020-06-05")
    #print(index_investing_global_df)

    df = ak.stock_zh_index_spot_sina()
    print(df[df['代码'] == 'sh000300'])
    print(df[df['名称'] == '沪深300全收益'])


    df = ak.stock_zh_index_daily_em(symbol="h00300")
    print(df)

    df = ak.stock_hk_index_spot_sina() # 恒生指数实时行情新浪
    print(df[df['代码'] == 'HSI']['最新价'])

    index_us_stock_sina_df = ak.index_us_stock_sina(symbol=".INX") #标普500指数历史
    print(index_us_stock_sina_df)

    stock_hk_index_daily_sina_df = ak.stock_hk_index_daily_sina(symbol="HSI") # 恒生指数历史行情
    print(stock_hk_index_daily_sina_df)

    stock_zh_index_daily_em_df = ak.stock_hk_index_daily_em(symbol="HSI")
    print(stock_zh_index_daily_em_df)

    df = ak.stock_hk_index_spot_em() # 恒生指数实时行情东财 延时短
    print(df[df['代码'] == 'HSI']['最新价'])
    '''

    # currency_boc_safe_df = ak.currency_boc_safe(start_date="20250101", end_date="20250120")
    # print(currency_boc_safe_df['美元'])

    # stock_zh_index_spot_em_df = ak.stock_zh_index_spot_em(symbol="深证系列指数")
    # print(stock_zh_index_spot_em_df)

    # df = ak.fx_quote_baidu(symbol="人民币")
    # print(df)
    # print(df[df['名称'] == '人民币港元']['最新价'].iloc[0])
    # print(df.query('名称=="人民币港元"')['最新价'].iloc[0])
    # print(df.query('名称=="人民币美元"')['最新价'].iloc[0])
    #
    # df = ak.currency_boc_safe() #所有汇率历史数据
    # print(df)
    #
    # df = ak.fx_spot_quote()
    # print(df[df['货币对'] == 'USD/CNY']['卖报价'].iloc[0])
    # print(df[df['货币对'] == 'HKD/CNY']['卖报价'].iloc[0])
    #
    # df = ak.currency_boc_sina(symbol="美元", start_date="20250125", end_date="20250204")
    # print(df)

    # df = ak.currency_convert(base="USD", to="CNY", amount="100")
    # print(df)

    # df = ak.stock_bid_ask_em(symbol="600519")
    # print(df)
    #
    # df = ak.stock_zh_a_spot_em()
    # print(df)
    #
    # df = ak.stock_zh_b_spot_em()
    # print(df)
    #
    # df = ak.stock_hk_spot_em()
    # print(df)
    #
    # df = ak.fund_etf_spot_em()
    # print(df)
    #
    # df = ak.stock_hk_index_daily_em(symbol="HSI").sort_values(by='date', ascending=False).head(1)
    # stock_hk_index_spot_em_df = ak.stock_hk_index_spot_em()
    # print(stock_hk_index_spot_em_df)
    # stock_hk_index_daily_sina_df = ak.stock_hk_index_daily_sina(symbol="CES100")
    # print(stock_hk_index_daily_sina_df)
    # df = ak.stock_hk_index_daily_sina(symbol="HSI").sort_values(by='date',ascending=False).head(1)
    # # df = ak.stock_hk_index_daily_em(symbol="HSI")
    # print(df)
    # current_year_HSI = df['date'].iloc[0].year
    # current_HSI = float(df['close'].iloc[0])
    df = ak.stock_hk_index_spot_sina()
    print(df)
    print(df[df['代码'] == 'HSI']['最新价'])

    return


def classify_stock_code(code):
    if code.startswith(('600', '601', '603', '605')):
        return "沪市A股"
    elif code.startswith(('000', '001', '002', '003', '004')):
        return "深市A股"
    elif code.startswith('300') or code.startswith('301'):
        return "创业板"
    elif code.startswith('688'):
        return "科创板"
    elif code.startswith('8'):
        return "北交所"
    elif code.startswith(('400', '430', '830')):
        return "新三板"
    elif code == '000001':
        return "上证指数"
    elif code == '399001':
        return "深证成指"
    elif code.startswith(('51', '150', '159')):  # 恒生ETF（sz159920）、H股B（sz150176）
        return "ETF"
    elif code.startswith('01'):
        return "国债"
    elif code.startswith(('12', '13', '112', '155')):  # 19恒大01（sh155406）、16冀中01（sz112292）
        return "企业债"
    else:
        return "未知类型"


# 从股票表中获取持仓股票和未持仓股票集合
def get_stock_hold_or_not():
    stock_list = Stock.objects.all().order_by('stock_code')
    stock_hold = []
    stock_not_hold = []
    code_hold = []
    code_not_hold = []
    for rs in stock_list:
        if Position.objects.filter(stock=rs.id).exists():
            code_hold.append(rs.stock_code)
        else:
            code_not_hold.append(rs.stock_code)
    for code in code_hold:
        stock_hold.append(Stock.objects.get(stock_code=code))
    for code in code_not_hold:
        stock_not_hold.append(Stock.objects.get(stock_code=code))
    return stock_hold, stock_not_hold


'''
# 从账户表中获取在用账户和未用账户集合
def get_account_used_or_not():
    stock_list = Stock.objects.all().order_by('stock_code')
    stock_hold = []
    stock_not_hold = []
    code_hold = []
    code_not_hold = []
    for rs in stock_list:
        if Position.objects.filter(stock=rs.id).exists():
            code_hold.append(rs.stock_code)
        else:
            code_not_hold.append(rs.stock_code)
    # codes = code_hold + code_not_hold
    for code in code_hold:
        stock_hold.append(Stock.objects.get(stock_code=code))
    for code in code_not_hold:
        stock_not_hold.append(Stock.objects.get(stock_code=code))
    return stock_hold, stock_not_hold
'''


def get_dividend_summary(currency_id):
    result = Dividend.objects.filter(
        currency_id=currency_id
    ).aggregate(
        total_amount=Sum('dividend_amount')
    )
    return result['total_amount'] or Decimal('0.00')


def get_dividend_current_year(currency_id):
    current_year = datetime.datetime.now().year
    result = Dividend.objects.filter(
        currency_id=currency_id,
        dividend_date__year=current_year
    ).aggregate(
        total_amount=Sum('dividend_amount')
    )
    return result['total_amount'] or Decimal('0.00')


def get_dividend_in_past_year(currency_id):
    # 计算日期范围
    today = datetime.datetime.now().date()
    one_year_ago = today - datetime.timedelta(days=365)
    # 查询近一年的分红总额
    result = Dividend.objects.filter(
        currency_id=currency_id,
        dividend_date__gte=one_year_ago,
        dividend_date__lte=today
    ).aggregate(
        total_amount=Sum('dividend_amount')
    )
    return result['total_amount'] or Decimal('0.00')


def get_dividend_annual_average(currency_id, years):
    """按年度统计平均分红金额（每年总分红再平均）"""
    current_year = datetime.datetime.now().year
    start_year = current_year - years  # 近五年（不含当年）
    end_year = current_year - 1

    # 获取每年总分红
    annual_totals = Dividend.objects.filter(
        currency_id=currency_id,
        dividend_date__year__gte=start_year,
        dividend_date__year__lte=end_year
    ).values('dividend_date__year').annotate(
        annual_total=Sum('dividend_amount')
    )

    # 计算years年平均值
    total_amount = Decimal('0.00')
    for entry in annual_totals:
        total_amount += entry['annual_total'] or Decimal('0.00')

    # 即使某些年份无分红，分母仍为years
    avg_amount = total_amount / years

    return avg_amount.quantize(Decimal('0.00'))


def get_year_span(currency_id):
    """
    获取指定货币类型的分红记录年份跨度
    :param currency_id: 货币ID
    :return: (最早年份, 最晚年份, 年份跨度) 元组
    """
    # 获取该货币的所有分红记录中的最早和最晚日期
    result = Dividend.objects.filter(currency_id=currency_id).aggregate(
        min_date=Min('dividend_date'),
        max_date=Max('dividend_date')
    )

    min_date = result['min_date']
    max_date = result['max_date']

    if min_date is None or max_date is None:
        # 没有分红记录时返回 (0, 0, 0)
        return 0, 0, 0

    # 计算年份数
    min_year = min_date.year
    max_year = max_date.year
    year_span = max_year - min_year + 1  # 包括起始和结束年份

    return min_year, max_year, year_span


def calculate_market_value_yearly_avg(currency_id):
    # 验证货币是否存在
    if not Currency.objects.filter(id=currency_id).exists():
        return []

    # 获取指定货币的记录
    records = HistoricalMarketValue.objects.filter(currency_id=currency_id)

    # 如果没有记录，返回空列表
    if not records.exists():
        return []

    # 获取最小和最大年份
    min_date = records.aggregate(min_date=Min('date'))['min_date']
    max_date = records.aggregate(max_date=Max('date'))['max_date']

    # 获取有记录且value不为0的最小日期
    # min_date = records.exclude(value=0).aggregate(min_date=Min('date'))['min_date']
    # max_date = records.exclude(value=0).aggregate(max_date=Max('date'))['max_date']

    min_year = min_date.year
    max_year = max_date.year
    print(min_year, max_year)

    # 计算每个年份的平均值
    yearly_avg = records.annotate(
        year=ExtractYear('date')
    ).values('year').annotate(
        avg_value=Avg('value')
    ).order_by('year')
    print('yearly_avg=', yearly_avg)

    # 转换为字典
    avg_dict = {item['year']: item['avg_value'] for item in yearly_avg}
    print('avg_dict=', avg_dict)

    # 单独检查每个年份是否全为零
    for year in range(min_year, max_year + 1):
        # 如果该年份在结果中但值不为零，跳过
        if year in avg_dict and avg_dict[year] != 0:
            continue

        # 检查该年份是否所有记录都为零
        year_records = records.filter(date__year=year)
        print('year_records=', year_records)
        if year_records.exists() and year_records.exclude(value=0).count() == 0:
            avg_dict[year] = 0.0
        elif year not in avg_dict:
            avg_dict[year] = 0.0
    print('avg_dict=', avg_dict)

    # 构建最终结果
    result = [
        {'year': year, 'average_value': avg_dict.get(year, 0.0)}
        for year in range(min_year, max_year + 1)
    ]
    print('result=', result)
    # 过滤掉 value = 0 的条目
    result = [item for item in result if item['average_value'] != 0]
    print('result=', result)

    return result


def calculate_overall_average(yearly_results):
    """
    计算所有年份平均值的总平均值

    参数:
        yearly_results (list): 每年平均值列表，格式如：
            [{'year': int, 'average_value': Decimal}, ...]

    返回:
        Decimal: 所有年份平均值的平均
    """
    # 确保有数据
    if not yearly_results:
        return Decimal(0.0)

    # 提取所有年份的平均值并求和
    total = Decimal(0.0)
    for entry in yearly_results:
        # 确保值类型正确
        if isinstance(entry['average_value'], Decimal):
            total += entry['average_value']
        else:
            # 如果不是Decimal类型则转换为Decimal
            total += Decimal(str(entry['average_value']))

    # 计算平均值
    overall_avg = total / Decimal(len(yearly_results))
    print('overall_avg=', overall_avg, 'years=', len(yearly_results))
    return overall_avg


def calculate_dividend_data(currency_id):
    # 如果currency_id不为0，按原逻辑处理单个货币
    if currency_id != 0:
        return calculate_single_currency_dividend_data(currency_id)

    # 如果currency_id为0，汇总所有货币的数据
    else:
        # 获取所有货币
        currencies = Currency.objects.all()
        currency_dict = {c.id: {'code': c.code, 'name': c.name} for c in currencies}

        # 获取汇率
        rate_dict = get_rate()  # 假设返回格式为 {'USD': 6.5, 'EUR': 7.2, 'GBP': 8.5}

        # 获取所有货币的年份范围
        all_years = set()
        currency_data = {}

        # 先收集所有货币的数据和年份
        for currency_id in currency_dict:
            # 获取单个货币的数据
            data = calculate_dividend_data(currency_id)
            currency_data[currency_id] = data

            # 收集所有年份
            for year in data['year']:
                all_years.add(year)

        # 如果没有有效数据，返回空结果
        if not all_years:
            return {'year': [], 'dividend_yearly_total': [], 'market_value_yearly_avg': [], 'dividend_rate_yearly': []}

        # 排序年份
        sorted_years = sorted(all_years)

        # 初始化汇总数据
        dividend_yearly_total = [0.0] * len(sorted_years)
        market_value_yearly_avg = [0.0] * len(sorted_years)
        dividend_rate_yearly = [0.0] * len(sorted_years)

        total_dividends = 0.0
        overall_avg_market_value = 0.0

        # 对每个货币的数据进行汇总（考虑汇率转换）
        for currency_id, data in currency_data.items():
            currency_code = currency_dict[currency_id]['code']
            exchange_rate = rate_dict.get(currency_code, 1.0)  # 如果没有找到汇率，默认使用1.0

            # 累加总分红和总市值
            total_dividends += data['total_dividends'] * exchange_rate
            overall_avg_market_value += data['overall_avg_market_value'] * exchange_rate

            # 按年份累加数据
            for i, year in enumerate(data['year']):
                year_index = sorted_years.index(year)
                dividend_yearly_total[year_index] += data['dividend_yearly_total'][i] * exchange_rate
                market_value_yearly_avg[year_index] += data['market_value_yearly_avg'][i] * exchange_rate

        # 计算每年的分红率
        for i in range(len(sorted_years)):
            if market_value_yearly_avg[i] > 0:
                dividend_rate_yearly[i] = dividend_yearly_total[i] / market_value_yearly_avg[i]

        # 计算平均分红率（只考虑有市值的年份）
        valid_rates = [rate for rate in dividend_rate_yearly if rate > 0]
        avg_dividend_rate = sum(valid_rates) / len(valid_rates) if valid_rates else 0

        return {
            'year': sorted_years,
            'dividend_yearly_total': dividend_yearly_total,
            'market_value_yearly_avg': market_value_yearly_avg,
            'dividend_rate_yearly': dividend_rate_yearly,
            'total_dividends': total_dividends,
            'overall_avg_market_value': overall_avg_market_value,
            'avg_dividend_rate': avg_dividend_rate
        }


def calculate_single_currency_dividend_data(currency_id):
    # 步骤1：获取所有有效日期范围
    date_range = HistoricalMarketValue.objects.filter(currency_id=currency_id, value__gt=0).aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )

    if not date_range['min_date'] or not date_range['max_date']:
        return {'year': [], 'dividend_yearly_total': [], 'market_value_yearly_avg': [], 'dividend_rate_yearly': []}

    min_date = date_range['min_date']
    max_date = date_range['max_date']
    total_days = (max_date - min_date).days + 1

    # 步骤2：计算整体加权平均市值
    overall_avg_value = HistoricalMarketValue.objects.filter(
        currency_id=currency_id,
        value__gt=0
    ).aggregate(avg_value=Avg('value'))['avg_value'] or Decimal('0.0')

    # 步骤3：生成有效年份列表
    years = list(range(min_date.year, max_date.year + 1))
    valid_years = []
    dividend_yearly_total = []
    market_value_yearly_avg = []
    dividend_rate_yearly = []

    # 步骤4：遍历每个年份计算年度数据
    for year in years:
        # 检查年份有效性 (存在非零市值)
        year_data = HistoricalMarketValue.objects.filter(
            currency_id=currency_id,
            date__year=year,
        )
        if not year_data.exists():
            continue

        valid_years.append(year)

        # 计算年度分红总额
        yearly_dividends = Dividend.objects.filter(
            currency_id=currency_id,
            dividend_date__year=year
        ).aggregate(sum=Sum('dividend_amount'))['sum'] or Decimal('0.0')
        dividend_yearly_total.append(float(yearly_dividends))

        # 计算年度平均市值
        yearly_avg = year_data.aggregate(avg=Avg('value'))['avg'] or Decimal('0.0')
        market_value_yearly_avg.append(float(yearly_avg))

        # 计算年度分红率
        if yearly_avg:
            dividend_rate_yearly.append(float(yearly_dividends / yearly_avg))
        else:
            dividend_rate_yearly.append(0)

    n = len([x for x in market_value_yearly_avg if x != 0])
    avg_dividend_rate = 0
    if n > 0:
        avg_dividend_rate = sum(dividend_rate_yearly) / n

    return {
        'year': valid_years,
        'dividend_yearly_total': dividend_yearly_total,
        'market_value_yearly_avg': market_value_yearly_avg,
        'dividend_rate_yearly': dividend_rate_yearly,
        'total_dividends': float(sum(dividend_yearly_total)) if dividend_yearly_total else 0,
        'overall_avg_market_value': float(overall_avg_value),
        'avg_dividend_rate': float(avg_dividend_rate)
    }


def get_dividend_summary_by_currency(stock_id):
    """
    获取指定股票在不同货币类型下的累计分红金额

    参数:
        stock_id (int): 要查询的股票ID

    返回:
        dict: 货币ID为键，累计分红金额为值的字典
              格式: {currency_id: total_dividend_amount}
              包含汇总无货币记录的键为None的条目
    """
    summary = {
        1: Decimal('0.0'),  # 基准货币
        2: Decimal('0.0'),  # 港元
        3: Decimal('0.0'),  # 美元
        # 可以添加更多货币
    }
    # 分组聚合查询
    results = Dividend.objects.filter(
        stock_id=stock_id
    ).values('currency_id').annotate(
        total_dividend=Sum('dividend_amount')
    )

    for item in results:
        summary[item['currency_id']] = item['total_dividend']

    # 将查询结果转换为字典
    # summary = {
    #     item['currency_id']: item['total_dividend']
    #     for item in results
    # }

    # 处理没有货币记录的情况（默认Decimal(0.0)）
    return summary if summary else {}


def calculate_total_dividend(dividend_dict, exchange_rates):
    """
    将不同货币的分红金额按汇率转换为基准货币并求和

    参数:
        dividend_dict (dict): 分红字典 {currency_id: 分红金额}
        exchange_rates (dict): 汇率字典 {currency_id: 汇率}

    返回:
        Decimal: 转换后的总分红金额（基准货币）

    说明:
        - 当货币ID在汇率字典中不存在时，该货币的分红将被忽略
        - 当分红字典为空时返回0
    """
    total = Decimal('0.0')
    for currency_id, amount in dividend_dict.items():
        # 跳过无货币记录的情况
        if currency_id is None:
            continue

        # 检查该货币是否有汇率
        if currency_id in exchange_rates:
            rate = exchange_rates[currency_id]

            # 确保汇率是Decimal类型
            if not isinstance(rate, Decimal):
                rate = Decimal(str(rate))
            total += amount * rate

    return float(total)


def calculate_stock_trade_summary(stock_id):
    # 1. 获取股票信息并判断是否为港股
    try:
        stock_obj = Stock.objects.select_related('market').get(id=stock_id)
        is_hk_stock = (stock_obj.market_id == 5)  # 假设港股市场ID为5
    except Stock.DoesNotExist:
        return {}

    # 2. 获取目标股票的所有交易记录
    trades = Trade.objects.filter(stock_id=stock_id).select_related('currency')

    # 3. 准备汇率查询数据
    date_currency_pairs = []
    hk_rate_dates = set()  # 存储需要查询港元汇率的日期

    for t in trades:
        # 判断是否港股通交易（港股且交易货币为基准货币）
        if is_hk_stock and t.currency_id == 1:
            # 标记需要查询港元汇率（假设港元currency_id=2）
            date_currency_pairs.append((t.trade_date, 2))
            hk_rate_dates.add(t.trade_date)
        elif t.currency_id != 1:  # 非基准货币
            date_currency_pairs.append((t.trade_date, t.currency_id))

    # 4. 查询所需的历史汇率
    rate_dict = {}
    if date_currency_pairs:
        # 去重处理
        unique_pairs = set(date_currency_pairs)
        dates = [pair[0] for pair in unique_pairs]
        currency_ids = [pair[1] for pair in unique_pairs]

        rate_records = HistoricalRate.objects.filter(
            date__in=dates,
            currency_id__in=currency_ids
        ).values('date', 'currency_id', 'rate')

        # 构建汇率字典 {(日期, 货币ID): 汇率}
        rate_dict = {
            (record['date'], record['currency_id']): record['rate']
            for record in rate_records
        }

    # 5. 初始化汇总字典
    # summary = defaultdict(lambda: {'buy': Decimal('0.0'), 'sell': Decimal('0.0')})
    summary = {
        1: {'buy': Decimal('0.0'), 'sell': Decimal('0.0')},  # 基准货币
        2: {'buy': Decimal('0.0'), 'sell': Decimal('0.0')},  # 港元
        3: {'buy': Decimal('0.0'), 'sell': Decimal('0.0')},  # 美元
        # 可以添加更多货币
    }

    # 6. 处理每笔交易
    for t in trades:
        # 确定汇率逻辑
        rate_val = None
        target_currency_id = t.currency_id

        # 处理港股通交易（港股且交易货币为基准货币）
        if is_hk_stock and t.currency_id == 1:
            # 使用港元汇率（2）进行计算，但最终归类到基准货币（1）
            key = (t.trade_date, 2)
            rate_val = rate_dict.get(key)
            # 保持目标货币为基准货币
            target_currency_id = 1
        else:
            # 非港股通交易
            if t.currency_id == 1:
                rate_val = Decimal('1.0')
            else:
                key = (t.trade_date, t.currency_id)
                rate_val = rate_dict.get(key)

        # 如果无法确定汇率则跳过该交易
        if rate_val is None:
            continue

        # 计算交易金额
        amount = t.trade_price * t.trade_quantity * rate_val

        # 确保target_currency_id在summary中存在
        if target_currency_id not in summary:
            summary[target_currency_id] = {'buy': Decimal('0.0'), 'sell': Decimal('0.0')}

        # 按交易类型分类累加到目标货币
        if t.trade_type == Trade.BUY:
            summary[target_currency_id]['buy'] += amount
        elif t.trade_type == Trade.SELL:
            summary[target_currency_id]['sell'] += amount

    return dict(summary)
