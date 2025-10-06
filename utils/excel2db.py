# xlrd版本只能是1.2.0,升级到2.0.1后无法支持xlsm文件
import xlrd
import datetime
from xlrd import xldate_as_tuple, xldate_as_datetime
import os
import django

# 从应用之外调用stock应用的models时，需要设置'DJANGO_SETTINGS_MODULE'变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'benben.settings')
django.setup()
from stock.models import Broker, Market, Account, Stock, Trade, Dividend, Subscription, Fund, FundHistory
import re
from django.contrib import messages


def excel2trade(file_name, sheet_name, start_row, end_row):
    count = 0
    workbook = xlrd.open_workbook(file_name)
    sht = workbook.sheet_by_name(sheet_name)
    if sheet_name == '香港1' or sheet_name == '香港2' or sheet_name == '中银' or sheet_name == '盈透':
        currency_value = 2
    else:
        currency_value = 1
    if sheet_name != '打新':
        trade_account_id = Account.objects.get(account_abbreviation=sheet_name).id
    # 获取总行数
    nrows = sht.nrows  # 包括标题
    # 获取总列数
    ncols = sht.ncols
    if start_row == -1:
        start_row = 1
    if end_row == -1:
        end_row = nrows
    # 计算出合并的单元格有哪些
    colspan = {}
    if sht.merged_cells:
        for item in sht.merged_cells:
            for row in range(item[0], item[1]):
                for col in range(item[2], item[3]):
                    # 合并单元格的首格是有值的，所以在这里进行了去重
                    if (row, col) != (item[0], item[2]):
                        colspan.update({(row, col): (item[0], item[2])})
    for i in range(start_row, end_row):
        if sht.cell(i, 2).ctype == 3:  # 判断单元格内容是否为日期类型
            trade_stock = sht.cell(i, 1).value
            for j in range(ncols):
                # 假如碰见合并的单元格坐标，取合并的首格的值即可
                if colspan.get((i, j)):
                    if j == 0:
                        if sheet_name == '打新':
                            trade_account_id = Account.objects.get(
                                account_abbreviation=sht.cell_value(*colspan.get((i, j)))).id
                    elif j == 1:
                        trade_stock = sht.cell_value(*colspan.get((i, j)))
                else:
                    if j == 0:
                        if sheet_name == '打新':
                            trade_account_id = Account.objects.get(account_abbreviation=sht.cell_value(i, j)).id
                    elif j == 1:
                        trade_stock = sht.cell_value(i, j)
            trade_date = xldate_as_datetime(sht.cell(i, 2).value, 0)
            trade_price = sht.cell(i, 3).value
            trade_quantity = sht.cell(i, 4).value
            if trade_quantity > 0:
                trade_type = 1
            else:
                trade_type = 2
                trade_quantity = abs(trade_quantity)
            # 取出字符串里括号中的内容
            p1 = re.compile(r'[（](.*?)[）]', re.S)  # 最小匹配
            p2 = re.compile(r'[(](.*)[)]', re.S)  # 贪婪匹配
            list1 = re.findall(p1, trade_stock)
            trade_stock_code = list1[0]
            try:
                stock_object = Stock.objects.get(stock_code=trade_stock_code)
            except:
                trade_stock_code = -1
                stock_object = Stock.objects.get(stock_code=trade_stock_code)
            else:
                pass
            trade_stock_id = stock_object.id
            print(trade_account_id, trade_stock_id, trade_date, trade_type, trade_price, trade_quantity)
            count += 1

            try:
                p = Trade.objects.create(
                    account_id=trade_account_id,
                    stock_id=trade_stock_id,
                    trade_date=trade_date,
                    trade_type=trade_type,
                    trade_price=trade_price,
                    trade_quantity=trade_quantity,
                    currency_id=currency_value,
                    filed_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            except:
                print(sheet_name + '插入' + str(trade_stock_id) + '记录失败！')

    print(sheet_name + '插入' + str(count) + '条记录成功！')
    return count


def excel2dividend(file_name, sheet_name, start_row, end_row):
    workbook = xlrd.open_workbook(file_name)
    sht = workbook.sheet_by_name(sheet_name)
    # 获取总行数
    nrows = sht.nrows  # 包括标题
    # 获取总列数
    ncols = sht.ncols
    if start_row == -1:
        start_row = 1
    if end_row == -1:
        end_row = nrows
    for i in range(start_row, end_row):
        account_id = 0
        dividend_amount = 0
        if sht.cell(i, 1).value != '':
            dividend_date = xldate_as_datetime(sht.cell(i, 0).value, 0)
            stock_code = sht.cell(i, 1).value
            stock_id = Stock.objects.get(stock_code=stock_code).id
            stock_name = sht.cell(i, 2).value
            for j in range(3, ncols):
                if sht.cell(i, j).value != '':
                    account_abbreviation = sht.cell(0, j).value
                    dividend_amount = sht.cell(i, j).value
                    if account_abbreviation[-2:] != '小计':  # 判断字符串后两位
                        if account_abbreviation[0:3] == '银河1':  # 判断字符串前三位
                            account_abbreviation = '银河1'
                        account_id = Account.objects.get(account_abbreviation=account_abbreviation).id
                        if j < 13:
                            currency_value = 1  # 人民币分红
                        elif j < 19:
                            currency_value = 2  # 港元分红
                        else:
                            currency_value = 3  # 美元分虹
                        try:
                            p = Dividend.objects.create(
                                dividend_date=dividend_date,
                                stock_id=stock_id,
                                account_id=account_id,
                                dividend_amount=dividend_amount,
                                currency_id=currency_value
                            )
                            print('导入记录成功！', dividend_date, stock_id, stock_name, account_id, dividend_amount,
                                  currency_value)
                        except:
                            print('失败！', dividend_date, stock_id, stock_name, account_id, dividend_amount,
                                  currency_value)
    return ()


def excel2subscription(file_name, sheet_name, start_row, end_row):
    workbook = xlrd.open_workbook(file_name)
    sht = workbook.sheet_by_name(sheet_name)
    if sheet_name == '新债':
        subscription_type = 2
    else:
        subscription_type = 1
    # 获取总行数
    nrows = sht.nrows  # 包括标题
    # 获取总列数
    ncols = sht.ncols
    if start_row == -1:
        start_row = 1
    if end_row == -1:
        end_row = nrows
    for i in range(start_row, end_row):
        if sht.cell(i, 1).value != '' and sht.cell(i, 1).value != '小计':
            subscription_date = xldate_as_datetime(sht.cell(i, 0).value, 0)
            account_abbreviation = sht.cell(i, 1).value
            if account_abbreviation[0:3] == '银河1':  # 判断字符串前三位
                account_abbreviation = '银河1'
            account_id = Account.objects.get(account_abbreviation=account_abbreviation).id
            subscription_name = sht.cell(i, 2).value
            subscription_quantity = sht.cell(i, 3).value
            buying_price = sht.cell(i, 4).value
            selling_price = sht.cell(i, 5).value
            try:
                p = Subscription.objects.create(
                    subscription_date=subscription_date,
                    account_id=account_id,
                    subscription_name=subscription_name,
                    subscription_type=subscription_type,
                    subscription_quantity=subscription_quantity,
                    buying_price=buying_price,
                    selling_price=selling_price
                )
                print('导入记录成功！', subscription_date, account_id, subscription_name, subscription_type)
            except:
                print('失败！', subscription_date, account_id, subscription_name, subscription_type)
    return ()


def excel2fund(file_name, sheet_name, start_row, end_row):
    workbook = xlrd.open_workbook(file_name)
    sht = workbook.sheet_by_name(sheet_name)
    fund_id = Fund.objects.get(fund_name=sheet_name).id
    # 获取总行数
    nrows = sht.nrows  # 包括标题
    # 获取总列数
    # ncols = sht.ncols
    if start_row == -1:
        start_row = 0
    if end_row == -1:
        end_row = nrows
    for i in range(start_row, end_row):
        if sht.cell(i, 0).ctype == 3:  # 判断单元格内容是否为日期类型
            if fund_id == 3: # 人民币账户
                date = xldate_as_datetime(sht.cell(i, 0).value, 0)
                fund_value = sht.cell(i, 12).value
                fund_in_out = sht.cell(i, 13).value
                fund_principal = sht.cell(i, 14).value
                fund_PHR = sht.cell(i, 15).value
                fund_net_value = sht.cell(i, 16).value
                fund_current_profit = sht.cell(i, 17).value
                fund_current_profit_rate = sht.cell(i, 18).value
                fund_profit = sht.cell(i, 19).value
                fund_profit_rate = sht.cell(i, 20).value
                fund_annualized_profit_rate = sht.cell(i, 21).value
            elif fund_id == 4: # 港元账户
                date = xldate_as_datetime(sht.cell(i, 0).value, 0)
                fund_value = sht.cell(i, 6).value
                fund_in_out = sht.cell(i, 7).value
                fund_principal = sht.cell(i, 8).value
                fund_PHR = sht.cell(i, 9).value
                fund_net_value = sht.cell(i, 10).value
                fund_current_profit = sht.cell(i, 11).value
                fund_current_profit_rate = sht.cell(i, 12).value
                fund_profit = sht.cell(i, 13).value
                fund_profit_rate = sht.cell(i, 14).value
                fund_annualized_profit_rate = sht.cell(i, 15).value
            elif fund_id == 5: # 美元账户
                date = xldate_as_datetime(sht.cell(i, 0).value, 0)
                fund_value = sht.cell(i, 3).value
                fund_in_out = sht.cell(i, 4).value
                fund_principal = sht.cell(i, 5).value
                fund_PHR = sht.cell(i, 6).value
                fund_net_value = sht.cell(i, 7).value
                fund_current_profit = sht.cell(i, 8).value
                fund_current_profit_rate = sht.cell(i, 9).value
                fund_profit = sht.cell(i, 10).value
                fund_profit_rate = sht.cell(i, 11).value
                fund_annualized_profit_rate = sht.cell(i, 12).value

            try:
                # 更新或新增一条记录
                print(fund_id,date)
                rs = FundHistory.objects.filter(fund_id=fund_id, date=date)
                print(rs)
                if rs.exists():
                    # 删除一条记录
                    for r in rs:
                        r.delete()
                        print('删除记录成功！', fund_id, date, fund_value, fund_in_out, fund_principal, fund_PHR, fund_net_value, fund_profit, fund_profit_rate, fund_annualized_profit_rate)
                    '''
                    # 更新一条记录
                    for r in rs:
                        r.fund_id = fund_id,
                        r.date = date,
                        r.fund_value = fund_value,
                        r.fund_in_out = fund_in_out,
                        r.fund_principal = fund_principal,
                        r.fund_PHR = fund_PHR,
                        r.fund_net_value = fund_net_value,
                        r.fund_current_profit = fund_current_profit,
                        r.fund_current_profit_rate = fund_current_profit_rate,
                        r.fund_profit = fund_profit,
                        r.fund_profit_rate = fund_profit_rate,
                        r.fund_annualized_profit_rate = fund_annualized_profit_rate
                        r.save()
                    print('更新记录成功！', fund_id, date, fund_value, fund_in_out, fund_principal, fund_PHR, fund_net_value, fund_profit, fund_profit_rate, fund_annualized_profit_rate)
                    '''
                # 新增一条记录
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
                print('新增记录成功！', fund_id, date, fund_value, fund_in_out, fund_principal, fund_PHR, fund_net_value, fund_profit, fund_profit_rate, fund_annualized_profit_rate)
            except:
                print('失败！', fund_id, date, fund_value, fund_in_out, fund_principal, fund_PHR, fund_net_value, fund_profit, fund_profit_rate, fund_annualized_profit_rate)
    return ()


