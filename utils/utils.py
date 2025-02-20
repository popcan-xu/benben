import random

import requests
from bs4 import BeautifulSoup
import bs4
import os
import json
import django
import datetime, time
import pathlib
import requests
from django.db.models import Max, Min

# import tushare as ts
import akshare as ak
import pandas as pd

import re

# import pysnowball as ball

# from lxml import etree
# from lxml import html
# etree = html.etree

# 从应用之外调用stock应用的models时，需要设置'DJANGO_SETTINGS_MODULE'变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benben.settings')
django.setup()
from stock.models import market, stock, trade, position, dividend, subscription, funds_details


# 将字典类型数据写入json文件或读取json文件并转为字典格式输出，若json文件不存在则创建文件再写入
class FileOperate:
    '''
    需要传入文件所在目录，完整文件名。
    默认为只读，并将json文件转换为字典类型输出
    若为写入，需向dictData传入字典类型数据
    默认为utf-8格式
    '''
    def __init__(self,filepath,filename,way='r',dictData = None,encoding='utf-8'):
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
                #print(self.dictData)
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
def get_chart_array(content, max_rows, name_col, value_col):
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
    return (name_array, value_array)


# 抓取单一股票实时行情
def get_stock_price(stock_code):
    # stock_object = stock.objects.get(stock_code=stock_code)
    path = pathlib.Path("./templates/dashboard/price.json")
    if path.is_file(): # 若json文件存在，从json文件中读取price、increase、color、price_time、index
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
    else: # 若json文件不存在，创建json文件
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
    if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 900 and (time1 - time3).total_seconds() <= 0) or index == -1:
    # if (time2 - time1).total_seconds() >= 0: # 用于调试
        # 1.从雪球网抓取实时行情
        # price, increase, color = get_quote_snowball(stock_code)

        # 2.通过pysnowball API抓取雪球网实时行情
        # price, increase, color = get_quote_pysnowball(stock_code)

        # 3.从http://qt.gtimg.cn/抓取实时行情
        # price, increase, color = get_quote_gtimg(stock_code)

        # 4.从akshare抓取实时行情
        price, increase, color = get_quote_akshare(stock_code)

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
def get_stock_array_price(stock_code_array):
    # stock_object = stock.objects.get(stock_code=stock_code)
    path = pathlib.Path("./templates/dashboard/price.json")
    if path.is_file(): # 若json文件存在，从json文件中读取price、increase、color、price_time、index
        # 读取price.json
        price_dict = FileOperate(filepath='./templates/dashboard/', filename='price.json').operation_file()
        price_array = price_dict['price_array']
        price_time = datetime.datetime.strptime(price_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
        # price, increase, color, price_time, index = search_price_array(price_array, stock_code)
    else: # 若json文件不存在，创建json文件
        price_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
        # index = -1
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
    # if (time2 - time1).total_seconds() >= 0: # 用于调试
        # 1.从雪球网抓取实时行情
        # price, increase, color = get_quote_snowball(stock_code)

        # 2.通过pysnowball API抓取雪球网实时行情
        # price, increase, color = get_quote_pysnowball(stock_code)

        # 3.从http://qt.gtimg.cn/抓取实时行情
        # price, increase, color = get_quote_gtimg(stock_code)

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

        # if index == -1:
        #     price_array.append((stock_code, price, increase, color, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        # else:
        #     price_array[index] = (stock_code, price, increase, color, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        price_dict.update(price_array=price_array)
        price_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=price_dict, filepath='./templates/dashboard/', filename='price.json').operation_file()

    return price_array_current


# 从akshare获取单一股票实时行情
def get_quote_akshare(stock_code):
    stock_object = stock.objects.get(stock_code=stock_code)
    market_name = stock_object.market.market_name
    if market_name == '港股':
        df = ak.stock_hk_spot_em()
        price = float(df.query('代码=="' + stock_code + '"')['最新价'].iloc[0])
        increase = float(df.query('代码=="' + stock_code + '"')['涨跌幅'].iloc[0])
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
    stock_object = stock.objects.get(stock_code=stock_code)
    market = stock_object.market.market_abbreviation
    if market == 'hk':
        code = stock_code
    else:
        code = market.upper() + stock_code
    url = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol=' + code
    quote_json = json.loads(getHTMLText(url)) # 将getHTMLText()返回的字符串转换为json格式的list
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
        stock_object = stock.objects.get(stock_code=i)
        market = stock_object.market.market_abbreviation
        if market == 'hk':
            code = i
        else:
            code = market.upper() + i
        code_array.append(code)
        code_str = ','.join(code_array)
    url = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol=' + code_str
    quote_json = json.loads(getHTMLText(url)) # 将getHTMLText()返回的字符串转换为json格式的list
    data = quote_json['data']
    for i in data:
        stock_code = i['symbol']
        price = i['current']
        increase = i['percent']
        if increase > 0:
            color = 'red'
        elif increase < 0:
            color = 'green'
        else:
            color = 'grey'
        quote_array.append((remove_prefix(stock_code), price, increase, color))
    return quote_array


# 格式化股票代码（去掉前缀SH、SZ）
def remove_prefix(stock_code):
    stock_code = stock_code.replace('SH', '')
    stock_code = stock_code.replace('SZ', '')
    return stock_code


# 通过pysnowball API抓取雪球网实时行情
# def get_quote_pysnowball(stock_code):
#     stock_object = stock.objects.get(stock_code=stock_code)
#     market = stock_object.market.market_abbreviation
#     ball.set_token('xq_a_token=a8d434ddd975f5752965fa782596bd0b5b008376;')
#     if market == 'hk':
#         code = stock_code
#     else:
#         code = market.upper() + stock_code
#     quote_json = ball.quotec(code)
#     price = quote_json['data'][0]['current']
#     increase = quote_json['data'][0]['percent']
#     if increase > 0:
#         color = 'red'
#     elif increase < 0:
#         color = 'green'
#     else:
#         color = 'grey'
#     return price, increase, color


# 从http://qt.gtimg.cn/抓取实时行情
def get_quote_gtimg(stock_code):
    price_str = []
    stock_object = stock.objects.get(stock_code=stock_code)
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

# 从akshare获取汇率数据
def get_rate():
    path = pathlib.Path("./templates/dashboard/rate.json")
    if path.is_file() == True: # 若json文件存在
        # 1. 读取JSON文件
        with open('./templates/dashboard/rate.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        time1 = datetime.datetime.strptime(data['modified_time'], "%Y-%m-%d %H:%M:%S")
        time2 = datetime.datetime.now()
        if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 3600):
            df = ak.fx_quote_baidu(symbol="人民币")
            temp_HKD = float(df.query('代码=="CNYHKD"')['最新价'].iloc[0])
            if temp_HKD != 0:
                rate_HKD = 1 / temp_HKD
                data["rate_HKD"] = rate_HKD
            else:
                rate_HKD = data["rate_HKD"]
            temp_USD = float(df.query('代码=="CNYUSD"')['最新价'].iloc[0])
            if temp_USD != 0:
                rate_USD = 1 / temp_USD
                data["rate_USD"] = rate_USD
            else:
                rate_USD = data["rate_USD"]
            #rate_HKD = 1 / float(df.query('代码=="CNYHKD"')['最新价'].iloc[0])
            #rate_USD = 1 / float(df.query('代码=="CNYUSD"')['最新价'].iloc[0])
            # 2. 修改汇率数据
            data["modified_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 3. 写回JSON文件（保留原有格式）
            with open('./templates/dashboard/rate.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)  # 保持中文可读性
        else:
            rate_HKD = data["rate_HKD"]
            rate_USD = data["rate_USD"]
    else:
        df = ak.fx_quote_baidu(symbol="人民币")
        temp_HKD = float(df.query('代码=="CNYHKD"')['最新价'].iloc[0])
        temp_USD = float(df.query('代码=="CNYUSD"')['最新价'].iloc[0])
        rate_HKD = 1 / temp_HKD if temp_HKD != 0 else 1
        rate_USD = 1 / temp_USD if temp_HKD != 0 else 1
        #rate_HKD = 1 / float(df.query('代码=="CNYHKD"')['最新价'].iloc[0])
        #rate_USD = 1 / float(df.query('代码=="CNYUSD"')['最新价'].iloc[0])
        rate = {}
        rate.update(rate_HKD=rate_HKD)
        rate.update(rate_USD=rate_USD)
        rate.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # 写入json文件
        FileOperate(dictData=rate, filepath='./templates/dashboard/',
                    filename='rate.json').operation_file()
    return rate_HKD, rate_USD

# 从https://wocha.cn/网站抓取汇率数据
# def get_rate_wocha():
#     rate_HKD = 1.0
#     rate_USD = 1.0
#     path = pathlib.Path("./templates/dashboard/rate.json")
#     if path.is_file(): # 若json文件存在，从json文件中读取rate_HKD、rate_USD
#         # 读取rate.json
#         rate_dict = FileOperate(filepath='./templates/dashboard/', filename='rate.json').operation_file()
#         rate_HKD = float(rate_dict['rate_HKD'])
#         rate_USD = float(rate_dict['rate_USD'])
#         rate_time = datetime.datetime.strptime(rate_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
#     else: # 若json文件不存在，创建json文件
#         rate_dict = {}
#         rate_dict.update(rate_HKD=1.0)
#         rate_dict.update(rate_USD=1.0)
#         rate_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
#         rate_dict.update(modified_time=rate_time.strftime("%Y-%m-%d %H:%M:%S"))
#         FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()
#
#     d = datetime.date(datetime.datetime.now().year, datetime.datetime.now().month, datetime.datetime.now().day)
#     # 若json文件中的rate_time与当前不为同一天，从https://wocha.cn/获取汇率
#     if rate_time.date() != datetime.datetime.today().date():
#     # if 1 == 1:
#         # 获取港元汇率
#         rate_HKD = getDateRate_hkd(d.strftime("%Y-%m-%d"))
#         if rate_HKD != -1:
#             rate_dict.update(rate_HKD=rate_HKD)
#         # 获取美元汇率
#         rate_USD = getDateRate_usd(d.strftime("%Y-%m-%d"))
#         if rate_USD != -1:
#             rate_dict.update(rate_USD=rate_USD)
#         rate_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
#         FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()
#
#     return rate_HKD, rate_USD


# 从https://qq.ip138.com/网站抓取汇率数据
# def get_rate_ip138():
#     rate_HKD = 1.0
#     rate_USD = 1.0
#     path = pathlib.Path("./templates/dashboard/rate.json")
#     if path.is_file():  # 若json文件存在，从json文件中读取rate_HKD、rate_USD
#         # 读取rate.json
#         rate_dict = FileOperate(filepath='./templates/dashboard/', filename='rate.json').operation_file()
#         rate_HKD = float(rate_dict['rate_HKD'])
#         rate_USD = float(rate_dict['rate_USD'])
#         rate_time = datetime.datetime.strptime(rate_dict['modified_time'], "%Y-%m-%d %H:%M:%S")
#     else:  # 若json文件不存在，创建json文件
#         rate_dict = {}
#         rate_dict.update(rate_HKD=1.0)
#         rate_dict.update(rate_USD=1.0)
#         rate_time = datetime.datetime(1970, 1, 1, 0, 0, 0)
#         rate_dict.update(modified_time=rate_time.strftime("%Y-%m-%d %H:%M:%S"))
#         FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()
#     # 若json文件中的rate_time与当前不为同一天，从https://qq.ip138.com/获取汇率
#     # if rate_time.date() != datetime.datetime.today().date():
#     if 1 == 1:
#         # 获取港元汇率
#         url_HKD = 'https://qq.ip138.com/hl.asp?from=HKD&to=CNY&q=100'
#         html_HKD = getHTMLText(url_HKD)
#         rate_HKD = getRate(html_HKD)
#         # 网页爬虫抓取结果是否为‘暂无’？
#         # if rate_HKD != -1:
#         if rate_HKD > 0:
#             rate_dict.update(rate_HKD=rate_HKD)
#         # 以下两行用于汇率获取失败后的临时补救
#         # else:
#         #     rate_dict.update(rate_HKD=1)
#         # 获取美元汇率
#         url_USD = 'https://qq.ip138.com/hl.asp?from=USD&to=CNY&q=100'
#         html_USD = getHTMLText(url_USD)
#         rate_USD = getRate(html_USD)
#         # 网页爬虫抓取结果是否为‘暂无’？
#         # if rate_USD != -1:
#         if rate_USD > 0:
#             rate_dict.update(rate_USD=rate_USD)
#         rate_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
#         FileOperate(dictData=rate_dict, filepath='./templates/dashboard/', filename='rate.json').operation_file()
#
#     # 调式   按日期抓取港币和美元历史汇率
#     begin = datetime.date(2024, 12, 17)
#     end = datetime.date(2024, 12, 19)
#     d = begin
#     delta = datetime.timedelta(days=1)
#     while d <= end:
#         print(d.strftime("%Y-%m-%d"))
#         hkd_rate = getDateRate_hkd(d.strftime("%Y-%m-%d"))
#         usd_rate = getDateRate_usd(d.strftime("%Y-%m-%d"))
#         print(hkd_rate, usd_rate)
#         # print("Start : %s" % time.ctime())
#         # time.sleep(random.random()*0.2)
#         # print("End : %s" % time.ctime())
#         d += delta
#
#     d = datetime.date(datetime.datetime.now().year, datetime.datetime.now().month, datetime.datetime.now().day)
#     hkd_rate = getDateRate_hkd(d.strftime("%Y-%m-%d"))
#     usd_rate = getDateRate_usd(d.strftime("%Y-%m-%d"))
#     print(hkd_rate, usd_rate)
#
#     return rate_HKD, rate_USD


# 从https://stock.xueqiu.com/网站抓取股票历史分红数据
def get_stock_dividend_history(stock_code):
    stock_object = stock.objects.get(stock_code=stock_code)
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
        url = 'https://stock.xueqiu.com/v5/stock/f10/cn/bonus.json?symbol=' + market.upper() + stock_code + '&size=10000&page=1&extend=true'
        # page_json = requests.get(url=url, headers=headers, timeout=30).json()
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
        url = 'https://stock.xueqiu.com/v5/stock/f10/us/bonus.json?symbol=' + stock_code + '&size=1000&page=1&extend=true'
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


def get_stock_dividend_history_2lines(stock_code):
    stock_object = stock.objects.get(stock_code=stock_code)
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

# 从指数历史数据生成json文件
def get_his_index():
    # 沪深300指数
    item = []
    data = []
    df = ak.stock_zh_index_daily_em(symbol="sh000300").sort_values(by='date',ascending=False)
    current_year = datetime.datetime.strptime(df.head(1)['date'].iloc[0], "%Y-%m-%d").year
    current_latest = float(df.head(1)['close'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['close']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_HS300 = df.to_dict(orient='records')


    # 恒生指数
    item = []
    data = []
    df = ak.stock_hk_index_daily_em(symbol="HSI").sort_values(by='date',ascending=False)
    current_year = datetime.datetime.strptime(df.head(1)['date'].iloc[0], "%Y-%m-%d").year
    current_latest = float(df.head(1)['latest'].iloc[0])
    item.append(current_year)
    item.append(current_latest)
    data.append(item)
    item = []
    for index in df.index:
        row = df.loc[index]
        year = datetime.datetime.strptime(row['date'], "%Y-%m-%d").year
        if year != current_year:
            current_year = year
            item.append(year)
            item.append(float(row['latest']))
            data.append(item)
            item = []
    df = pd.DataFrame(data, columns=['Year', 'ClosingPrice']).sort_values(by='Year')
    dict_data_HSI = df.to_dict(orient='records')

    # 标普500指数
    item = []
    data = []
    df = ak.index_us_stock_sina(symbol=".INX").sort_values(by='date',ascending=False) #标普500指数历史
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

    baseline = {}
    baseline.update(沪深300指数=dict_data_HS300)
    baseline.update(恒生指数=dict_data_HSI)
    baseline.update(标普500指数=dict_data_INX)
    # 打时间戳
    baseline.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    # 写入json文件
    FileOperate(dictData=baseline, filepath='./templates/dashboard/', filename='baseline.json').operation_file()

    return

# 从指数当年数据更新json文件
def get_current_index():
    # 沪深300指数
    df = ak.stock_zh_index_daily_em(symbol="sh000300").sort_values(by='date',ascending=False).head(1)
    current_year_HS300 = datetime.datetime.strptime(df['date'].iloc[0], "%Y-%m-%d").year
    current_HS300 = float(df['close'].iloc[0])


    # 恒生指数
    # df = ak.stock_hk_index_daily_em(symbol="HSI").sort_values(by='date',ascending=False).head(1)
    # current_year_HSI = datetime.datetime.strptime(df['date'].iloc[0], "%Y-%m-%d").year
    # current_HSI = float(df['latest'].iloc[0])

    # df = ak.stock_hk_index_daily_sina(symbol="HSI").sort_values(by='date',ascending=False).head(1)
    # current_year_HSI = df['date'].iloc[0].year
    # current_HSI = float(df['close'].iloc[0])

    df = ak.stock_hk_index_spot_sina()
    current_HSI = float(df[df['代码'] == 'HSI']['最新价'].iloc[0])
    current_year_HSI = datetime.datetime.now().year


    # 标普500指数
    df = ak.index_us_stock_sina(symbol=".INX").sort_values(by='date',ascending=False).head(1)
    current_year_INX = df['date'].iloc[0].year
    current_INX = float(df['close'].iloc[0])

    # 1. 读取JSON文件
    #baseline = FileOperate(filepath='./templates/dashboard/', filename='baseline.json').operation_file()
    with open('./templates/dashboard/baseline.json', 'r', encoding='utf-8') as f:
        baseline = json.load(f)

    # 2. 查找并修改当年数据
    for item in baseline["沪深300指数"]:
        if item["Year"] == current_year_HS300:
            item["ClosingPrice"] = current_HS300  # 替换成你的新数值
            break  # 找到后立即退出循环
    for item in baseline["恒生指数"]:
        if item["Year"] == current_year_HSI:
            item["ClosingPrice"] = current_HSI  # 替换成你的新数值
            break  # 找到后立即退出循环
    for item in baseline["标普500指数"]:
        if item["Year"] == current_year_INX:
            item["ClosingPrice"] = current_INX  # 替换成你的新数值
            break  # 找到后立即退出循环
    baseline["modified_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 3. 写回JSON文件（保留原有格式）
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
def get_max_date(funds_id):
    max_date = funds_details.objects.filter(funds_id=funds_id).aggregate(max_date=Max('date'))['max_date']
    return max_date

# 从基金明细表获取当前基金的最小记账日期
def get_min_date(funds_id):
    min_date = funds_details.objects.filter(funds_id=funds_id).aggregate(min_date=Min('date'))['min_date']
    return min_date

# 从基金明细表获取当前基金的第二大记账日期
def get_second_max_date(funds_id):
    max_date = funds_details.objects.filter(funds_id=funds_id).aggregate(max_date=Max('date'))['max_date']
    second_max_date = funds_details.objects.filter(funds_id=funds_id).exclude(date=max_date).order_by('-date').values_list('date', flat=True)[0]
    # second_max_date = funds_details.objects.filter(funds_id=funds_id).order_by('-date').values_list('date', flat=True)[1]
    # third_max_date = funds_details.objects.filter(funds_id=funds_id).order_by('-date').values_list('date', flat=True)[2]
    return second_max_date

# 从基金明细表获取指定年份的年末日期
def get_year_end_date(funds_id, year):
    year_end_date = None
    year_end_date = funds_details.objects.filter(funds_id=funds_id, date__year=year).aggregate(max_date=Max('date'))['max_date']
    return year_end_date



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
def take_col11(list):
    return float(list[10])


# 时间戳（10位）转日期格式
def timeStamp10_2_date(timeStamp):
    return time.strftime("%Y-%m-%d", time.localtime(timeStamp))


# 时间戳（13位）转日期格式
def timeStamp13_2_date(timeStamp):
    if str(timeStamp) != 'None':
        return time.strftime("%Y-%m-%d", time.localtime(timeStamp / 1000))
    else:
        return 'None'



# 从tushare获取股票行情
# def get_quote_tushare():
#     # 设置 Tushare Pro token
#     ts.set_token('02b13d21dd01b2682f10173d8003b92e1a8ff778695b8cf929169250')
#
#     # 初始化 Tushare Pro API
#     pro = ts.pro_api()
#
#     # 拉取数据
#     data = pro.hk_daily(**{
#         "ts_code": "00700.HK",  # 股票代码
#         "start_date": 20250115,  # 开始日期
#         "end_date": 20250120,  # 结束日期
#     }, fields=[
#         "ts_code",  # 交易日期
#         "open",  # 开盘价
#         "high",  # 最高价
#         "low",  # 最低价
#         "close",  # 收盘价
#         "pct_chg",  # 涨跌幅
#         "vol",  # 成交量
#         "trade_date"  # 交易日期
#     ])
#
#     # 显示数据
#     print(data)
#     print(data.iloc[0].iloc[4])
#     print(data.iloc[0,4])
#
#
#     df = pro.daily(ts_code='600519.SH', start_date='20230103', end_date='20230105')
#     print("pro.daily(ts_code='600519.SH', start_date='20230103', end_date='20230105')")
#     print(df.tail())
#     print(df['close'])
#
#     df = pro.hk_daily(ts_code='00700.HK', start_date='20190904', end_date='20190905')
#     print("pro.hk_daily(ts_code='00700.HK', start_date='20190904', end_date='20190905')")
#     print(df)
#     print(df['close'])
#
#     # sina数据
#     df = ts.realtime_quote(ts_code='511880.SH,200596.SZ,000001.SZ,000300.SH')
#     print("ts.realtime_quote(ts_code='600000.SH,600036.SH,000001.SZ,000300.SH')")
#     print(df.iloc[0,6])
#
#     # 东财数据
#     df = ts.realtime_quote(ts_code='511880.SH', src='dc')
#     print("ts.realtime_quote(ts_code='600000.SH', src='dc')")
#     print(df.iloc[0].iloc[6])
#
#
#     df = ts.get_realtime_quotes('200596')[['name', 'price', 'pre_close', 'date', 'time']]
#     #df1 = pd.DataFrame(df)
#     print("ts.get_realtime_quotes('600000')[['name', 'price', 'pre_close', 'date', 'time']]")
#     print(df['name'].iloc[0])
#     print(df['date'].iloc[0])
#     print(df['price'].iloc[0])
#     #print(df)
#
#     #stock_basic = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
#     #print(stock_basic.head())
#     return



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

    #currency_boc_safe_df = ak.currency_boc_safe(start_date="20250101", end_date="20250120")
    #print(currency_boc_safe_df['美元'])

    #stock_zh_index_spot_em_df = ak.stock_zh_index_spot_em(symbol="深证系列指数")
    #print(stock_zh_index_spot_em_df)

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

    #df = ak.currency_convert(base="USD", to="CNY", amount="100")
    #print(df)

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
    elif code.startswith(('51', '15')):
        return "ETF"
    elif code.startswith('01'):
        return "国债"
    elif code.startswith(('12', '13')):
        return "企业债"
    else:
        return "未知类型"

# 从股票表中获取持仓股票和未持仓股票集合
def get_stock_hold_or_not():
    stock_list = stock.objects.all().order_by('stock_code')
    stock_hold = []
    stock_not_hold = []
    code_hold = []
    code_not_hold = []
    for rs in stock_list:
        if position.objects.filter(stock=rs.id).exists():
            code_hold.append(rs.stock_code)
        else:
            code_not_hold.append(rs.stock_code)
    for code in code_hold:
        stock_hold.append(stock.objects.get(stock_code=code))
    for code in code_not_hold:
        stock_not_hold.append(stock.objects.get(stock_code=code))
    return stock_hold, stock_not_hold

# 从账户表中获取在用账户和未用账户集合
def get_account_used_or_not():
    stock_list = stock.objects.all().order_by('stock_code')
    stock_hold = []
    stock_not_hold = []
    code_hold = []
    code_not_hold = []
    for rs in stock_list:
        if position.objects.filter(stock=rs.id).exists():
            code_hold.append(rs.stock_code)
        else:
            code_not_hold.append(rs.stock_code)
    #codes = code_hold + code_not_hold
    for code in code_hold:
        stock_hold.append(stock.objects.get(stock_code=code))
    for code in code_not_hold:
        stock_not_hold.append(stock.objects.get(stock_code=code))
    return stock_hold, stock_not_hold
