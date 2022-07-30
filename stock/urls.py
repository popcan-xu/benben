from django.urls import path, include
from stock.views import *

from django.views.decorators.cache import cache_page

# django3的写法
# from django.conf.urls import url

# django4的写法
from django.urls import re_path as url

from . import views

urlpatterns = [
    path('add_broker/', add_broker),
    path('del_broker/<int:broker_id>/', del_broker),
    path('edit_broker/<int:broker_id>/', edit_broker),
    path('list_broker/', list_broker),

    path('add_market/', add_market),
    path('del_market/<int:market_id>/', del_market),
    path('edit_market/<int:market_id>/', edit_market),
    path('list_market/', list_market),

    path('add_account/', add_account),
    path('del_account/<int:account_id>/', del_account),
    path('edit_account/<int:account_id>/', edit_account),
    path('list_account/', list_account),

    path('add_industry/', add_industry),
    path('del_industry/<int:industry_id>/', del_industry),
    path('edit_industry/<int:industry_id>/', edit_industry),
    path('list_industry/', list_industry),

    path('add_stock/', add_stock),
    path('del_stock/<int:stock_id>/', del_stock),
    path('edit_stock/<int:stock_id>/', edit_stock),
    path('list_stock/', list_stock),

    path('add_position/', add_position),
    path('del_position/<int:position_id>/', del_position),
    path('edit_position/<int:position_id>/', edit_position),
    path('list_position/', list_position),

    path('add_trade/', add_trade),
    path('del_trade/<int:trade_id>/', del_trade),
    path('edit_trade/<int:trade_id>/', edit_trade),
    path('list_trade/', list_trade),

    path('add_dividend/', add_dividend),
    path('del_dividend/<int:dividend_id>/', del_dividend),
    path('edit_dividend/<int:dividend_id>/', edit_dividend),
    path('list_dividend/', list_dividend),

    path('add_subscription/', add_subscription),
    path('del_subscription/<int:subscription_id>/', del_subscription),
    path('edit_subscription/<int:subscription_id>/', edit_subscription),
    path('list_subscription/', list_subscription),

    path('add_dividend_history/', add_dividend_history),
    path('del_dividend_history/<int:dividend_history_id>/', del_dividend_history),
    path('edit_dividend_history/<int:dividend_history_id>/', edit_dividend_history),
    path('list_dividend_history/', list_dividend_history),

    path('index/', index),
    path('about/', about),

    path('batch_import/', batch_import),
    path('web_capture/', web_capture),

    path('foo/<int:code>/', cache_page(60 * 15)(statistics_value)),
    path('statistics_value/', statistics_value),
    path('statistics_position/', statistics_position),
    path('statistics_dividend/', statistics_dividend),
    path('statistics_subscription/', statistics_subscription),
    path('statistics_trade/', statistics_trade),
    path('statistics_account/', statistics_account),
    path('statistics_profit/', statistics_profit),

    path('input_trade/', input_trade),
    path('input_dividend/', input_dividend),
    path('input_subscription/', input_subscription),

    path('query_dividend_history/', query_dividend_history),
    path('query_dividend_date/', query_dividend_date),
    path('query_dividend_value/', query_dividend_value),

    # url(r'^pie/$', views.ChartView.as_view(), name='stock'),
    # url(r'^bar/$', views.ChartView.as_view(), name='stock'),
    # url(r'^statistics_dividend/$', views.IndexView.as_view(), name='stock'),
    # path('statistics_dividend/stock_bar/',views.ChartView_dividend_stock_bar.as_view(),name='stock_bar'),
    # path('statistics_dividend/stock_pie/',views.ChartView_dividend_stock_pie.as_view(),name='stock_pie'),
    # path('statistics_dividend/',views.IndexView.as_view()),

    path('dashboard/', dashboard),
    path('stats_view/', stats_view),
    path('list_view/', list_view),
    path('form_view/', form_view),
    path('card_view/', card_view),
    path('card_table_view/', card_table_view),
    path('card_bar_view/', card_bar_view),
    path('card_pie_view/', card_pie_view),
    path('charts/', charts),

    path('D_add_broker/', D_add_broker),
    path('D_del_broker/<int:broker_id>/', D_del_broker),
    path('D_edit_broker/<int:broker_id>/', D_edit_broker),
    path('D_list_broker/', D_list_broker),

    path('D_add_market/', D_add_market),
    path('D_del_market/<int:market_id>/', D_del_market),
    path('D_edit_market/<int:market_id>/', D_edit_market),
    path('D_list_market/', D_list_market),

    path('D_add_account/', D_add_account),
    path('D_del_account/<int:account_id>/', D_del_account),
    path('D_edit_account/<int:account_id>/', D_edit_account),
    path('D_list_account/', D_list_account),

    path('D_add_industry/', D_add_industry),
    path('D_del_industry/<int:industry_id>/', D_del_industry),
    path('D_edit_industry/<int:industry_id>/', D_edit_industry),
    path('D_list_industry/', D_list_industry),

    path('D_add_stock/', D_add_stock),
    path('D_del_stock/<int:stock_id>/', D_del_stock),
    path('D_edit_stock/<int:stock_id>/', D_edit_stock),
    path('D_list_stock/', D_list_stock),

    path('D_add_position/', D_add_position),
    path('D_del_position/<int:position_id>/', D_del_position),
    path('D_edit_position/<int:position_id>/', D_edit_position),
    path('D_list_position/', D_list_position),

    path('D_add_trade/', D_add_trade),
    path('D_del_trade/<int:trade_id>/', D_del_trade),
    path('D_edit_trade/<int:trade_id>/', D_edit_trade),
    path('D_list_trade/', D_list_trade),

    path('D_add_dividend/', D_add_dividend),
    path('D_del_dividend/<int:dividend_id>/', D_del_dividend),
    path('D_edit_dividend/<int:dividend_id>/', D_edit_dividend),
    path('D_list_dividend/', D_list_dividend),

    path('D_add_subscription/', D_add_subscription),
    path('D_del_subscription/<int:subscription_id>/', D_del_subscription),
    path('D_edit_subscription/<int:subscription_id>/', D_edit_subscription),
    path('D_list_subscription/', D_list_subscription),

    # path('D_add_dividend_history/', D_add_dividend_history),
    # path('D_del_dividend_history/<int:dividend_history_id>/', D_del_dividend_history),
    # path('D_edit_dividend_history/<int:dividend_history_id>/', D_edit_dividend_history),
    path('D_list_dividend_history/', D_list_dividend_history),

    path('D_stats_position/', D_stats_position),
    path('D_query_dividend_value/', D_query_dividend_value),

]
