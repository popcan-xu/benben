# -*- coding: UTF-8 -*-
#自定义过滤器，注意这里编码一定不要掉了，不然会报错啊~~~~
from django import template
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


register.filter(percent)

register.filter(text_color)

register.filter(get_type)

register.filter(truncate_end)

register.filter(div)

register.filter(absolute)

register.filter(key)

register.filter(get_index)