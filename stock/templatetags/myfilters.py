# -*- coding: UTF-8 -*-
#自定义过滤器，注意这里编码一定不要掉了，不然会报错啊~~~~
from django import template
register = template.Library()

def percent(value):
    return "{:.2f}".format(float(value) * 100)


def text_color(value):
    if float(value) < 0 :
        return 'red'
    else:
        return ''


@register.filter
def get_type(value):
    return type(value).__name__


@register.filter
def truncate_end(value, num_chars):
    if not value:
        return value
    return value[:-num_chars] if len(value) > num_chars else value

@register.filter
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

@register.filter
def absolute(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value

register.filter(percent)

register.filter(text_color)

register.filter(get_type)

register.filter(truncate_end)

register.filter(div)

register.filter(absolute)