# -*- coding: UTF-8 -*-
#自定义过滤器，注意这里编码一定不要掉了，不然会报错啊~~~~
from django import template
from django.utils.safestring import mark_safe

from stock.models import currency
register = template.Library()

@register.filter
def percent(value):
    return "{:.2f}".format(float(value) * 100)


def text_color(value):
    if float(value) < 0 :
        return 'red'
    else:
        return ''


def get_type(value):
    return type(value).__name__


def truncate_end(value, num_chars):
    if not value:
        return value
    return value[:-num_chars] if len(value) > num_chars else value


def div(value, arg):
    """将value除以arg"""
    try:
        value = float(value)
        arg = float(arg)
        if arg == 0:
            return 0
        return value / arg
    except (ValueError, ZeroDivisionError, TypeError):
        return 0


def absolute(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value


def key(d, key_name):
    return d.get(key_name)


def get_index(mylist, i):
    return mylist[i]


def value_display(value, format_type):
    try:
        num = float(value)
    except (ValueError, TypeError):
        return value  # 处理错误值

    # 根据值设置颜色和图标
    if num > 0:
        color = '#10b981'
        icon = '<i class="fas fa-arrow-up"></i> '
    elif num < 0:
        color = '#ef4444'
        icon = '<i class="fas fa-arrow-down"></i> '
        num = abs(num)  # 取绝对值
    else:
        color = '#6b7280'
        icon = ''

    # 根据请求的格式类型格式化值
    if format_type == 'percent':
        formatted_value = f"{num * 100:.2f}"  # 格式化为百分比
    else:
        formatted_value = f"{num:,.0f}"  # 数值格式化：加千分位

    # 创建安全的HTML输出
    html = f'<span style="color: {color}">{icon}{formatted_value}</span>'
    return mark_safe(html)


register.filter(percent)

register.filter(text_color)

register.filter(get_type)

register.filter(truncate_end)

register.filter(div)

register.filter(absolute)

register.filter(key)

register.filter(get_index)

register.filter(value_display)