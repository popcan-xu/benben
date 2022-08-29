from django.urls import path, include
from stock.views import *

from django.views.decorators.cache import cache_page

# django3的写法
# from django.conf.urls import url

# django4的写法
from django.urls import re_path as url

from . import views

urlpatterns = [
    path('index/', overview),
    path('overview/', overview),

    path('market_value/', market_value),

    path('input_trade/', input_trade),
    path('input_dividend/', input_dividend),
    path('input_subscription/', input_subscription),

    path('stats_position/', stats_position),
    path('stats_value/', stats_value),
    path('stats_account/', stats_account),
    path('stats_dividend/', stats_dividend),
    path('stats_subscription/', stats_subscription),
    path('stats_trade/', stats_trade),
    path('stats_profit/', stats_profit),
    path('query_dividend_value/', query_dividend_value),
    path('query_dividend_date/', query_dividend_date),
    path('query_dividend_history/', query_dividend_history),

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

    path('capture_dividend_history/', capture_dividend_history),

    path('batch_import/', batch_import),

    path('about/', about),

]
