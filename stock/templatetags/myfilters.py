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

register.filter(percent)

register.filter(text_color)

register.filter(get_type)