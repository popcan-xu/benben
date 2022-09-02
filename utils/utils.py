import requests
from bs4 import BeautifulSoup
import bs4
import os
import json
import django
import datetime, time
import pathlib
import requests

# from lxml import etree
# from lxml import html
# etree = html.etree

# 从应用之外调用stock应用的models时，需要设置'DJANGO_SETTINGS_MODULE'变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benben.settings')
django.setup()
from stock.models import market, stock, trade, position, dividend, subscription


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


# 从http://qt.gtimg.cn/网站抓取股票价格数据
def get_stock_price(stock_code):
    stock_object = stock.objects.get(stock_code=stock_code)
    path = pathlib.Path("./templates/dashboard/price.json")
    if path.is_file(): # 若json文件存在，从json文件中读取price、increase、color、price_time、index
        # 读取price.json
        price_dict = FileOperate(filepath='./templates/dashboard/', filename='price.json').operation_file()
        price_array = price_dict['price_array']
        price, increase, color, price_time, index = search_price_array(price_array, stock_code)
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
        price_str = []
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
        # 写入json文件
        if index == -1:
            price_array.append((stock_code, price, increase, color, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        else:
            price_array[index] = (stock_code, price, increase, color, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        price_dict.update(price_array=price_array)
        price_dict.update(modified_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        FileOperate(dictData=price_dict, filepath='./templates/dashboard/', filename='price.json').operation_file()

    return price, increase, color


# 在二维列表price_array中用查找stock_code所在的位置，返回该位置对应子列表的price、increase、color、price_time、index，若查找失败，返回index=-1
def search_price_array(price_array, stock_code):
    i = 0
    index = -1
    price = -1.0
    increase = 0.0
    color = 'grey'
    price_time = datetime.datetime.now()
    while i < len(price_array):
        if price_array[i][0] == stock_code:
            price = float(price_array[i][1])
            increase = float(price_array[i][2])
            color = str(price_array[i][3])
            price_time = datetime.datetime.strptime(price_array[i][4], "%Y-%m-%d %H:%M:%S")
            index = i
            break
        i += 1
    return price, increase, color, price_time,  index


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


# 从http://qt.gtimg.cn/网站抓取股票价格数据
def get_stock_price_old(stock_code):
    stock_object = stock.objects.get(stock_code=stock_code)
    time1 = stock_object.price_time
    time2 = datetime.datetime.now()
    time3 = datetime.datetime(time1.year, time1.month, time1.day, 16, 29, 59)
    # 当前时间与数据库价格获取时间不是同一天 或 (当前时间与数据库价格获取时间间隔大于300秒 且 数据库价格获取时间早于当天的16点30分)
    if time1.date() != time2.date() or ((time2 - time1).total_seconds() >= 900 and (time1 - time3).total_seconds() <= 0):
        price = []
        market = stock_object.market.market_abbreviation
        if market == 'hk':
            url = 'http://qt.gtimg.cn/q=r_' + market + stock_code  # 在股票代码前面加上'r_'，用于获得实时港股行情
        else:
            url = 'http://qt.gtimg.cn/q=' + market + stock_code
        html = getHTMLText(url)
        x = html.count('~', 1, len(html))  # 获取返回字符串html中分隔符'~'的出现次数
        for i in range(0, x + 1):
            price.append(html.split('~')[i])  # 将html用'~'分隔后的值输出到列表price中
        stock_price = price[3]
        increase = price[32]
        stock_object.price = float(stock_price)
        stock_object.increase = float(increase)
        stock_object.price_time = time2.strftime("%Y-%m-%d %H:%M:%S")
        stock_object.save()
    else:
        stock_price = stock_object.price
        increase = stock_object.increase
    return float(stock_price), float(increase)


# 从https://qq.ip138.com/网站抓取汇率数据
def get_stock_rate():
    market1 = market.objects.get(market_name='港股')
    market2 = market.objects.get(market_name='美股')

    HKD_date = market1.modified_time
    if HKD_date.date() == datetime.datetime.today().date():
        # 从数据库取出港元汇率
        rate_HKD = market1.exchange_rate
    else:
        # 从网络获取港元汇率
        url_HKD = 'https://qq.ip138.com/hl.asp?from=HKD&to=CNY&q=100'
        html_HKD = getHTMLText(url_HKD)
        rate_HKD = getRate(html_HKD)
        # 网页爬虫抓取结果是否为‘暂无’？
        if rate_HKD == -1:
            rate_HKD = market1.exchange_rate
        else:
            market1.exchange_rate = rate_HKD
            market1.save()
            market3 = market.objects.get(market_name='深市B股')
            market3.exchange_rate = rate_HKD
            market3.save()

    USD_date = market2.modified_time
    if USD_date.date() == datetime.datetime.today().date():
        # 从数据库取出美元汇率
        rate_USD = market2.exchange_rate
    else:
        # 从网络获取美元汇率
        url_USD = 'https://qq.ip138.com/hl.asp?from=USD&to=CNY&q=100'
        html_USD = getHTMLText(url_USD)
        rate_USD = getRate(html_USD)
        # 网页爬虫抓取结果是否为‘暂无’？
        if rate_USD == -1:
            rate_USD = market2.exchange_rate
        else:
            market2.exchange_rate = rate_USD
            market2.save()
            market4 = market.objects.get(market_name='沪市B股')
            market4.exchange_rate = rate_USD
            market4.save()

    return float(rate_HKD), float(rate_USD)


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
        r = requests.get(url, headers=kv, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding
        # r.encoding = 'gb2312'
        r.encoding = 'gbk'
        # r.encoding = 'utf-8'
        return r.text
    except:
        # print('获取网页失败')
        return '获取网页失败'


def getRate(html):
    soup = BeautifulSoup(html, 'html.parser')
    mystr = ''
    for tr in soup.find('table').children:
        if isinstance(tr, bs4.element.Tag):
            tds = tr.find_all('td')
            mystr = mystr + str(tds)
    mystr = mystr.split('<td><p>')[5]
    mystr = mystr.split('</p>')[0]
    # 网页爬虫抓取结果是否为‘暂无’？
    if mystr == '鏆傛棤':
        rate = -1
    else:
        rate = float(mystr)
        # 保留7位（小数点后5位）后按保留小数点后4位并四舍五入
        rate = round(float('%.7f' % rate), 4)
    return rate


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


# 时间戳（10位）转日期格式
def timeStamp10_2_date(timeStamp):
    return time.strftime("%Y-%m-%d", time.localtime(timeStamp))


# 时间戳（13位）转日期格式
def timeStamp13_2_date(timeStamp):
    if str(timeStamp) != 'None':
        return time.strftime("%Y-%m-%d", time.localtime(timeStamp / 1000))
    else:
        return 'None'
