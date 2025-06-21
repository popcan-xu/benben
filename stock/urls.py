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

    path('investment_accounting/', investment_accounting),
    path('view_funds_details/<int:funds_id>/', view_funds_details),

    path('market_value/', market_value),
    path('view_market_value_details/<int:currency_id>/', view_market_value_details),
    # path('trade_overview/', trade_overview),
    path('view_trade_details/<int:currency_id>/', view_trade_details),

    path('view_dividend/', view_dividend),
    path('view_dividend_details/<int:currency_id>/', view_dividend_details),

    path('input_trade/', input_trade),
    path('input_dividend/', input_dividend),
    path('input_subscription/', input_subscription),

    path('stats_position/', stats_position),
    path('stats_value/', stats_value),
    path('stats_account/', stats_account),
    path('stats_dividend/', stats_dividend),
    path('stats_subscription/', stats_subscription),
    # path('stats_trade/', stats_trade),
    path('stats_profit/', stats_profit),
    path('query_trade/', query_trade),
    path('query_dividend_value/', query_dividend_value),
    path('query_dividend_date/', query_dividend_date),
    path('query_dividend_history/', query_dividend_history),

    path('add_currency/', add_currency),
    path('del_currency/<int:currency_id>/', del_currency),
    path('edit_currency/<int:currency_id>/', edit_currency),
    path('list_currency/', list_currency),

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

    path('add_historical_position/', add_historical_position),
    path('del_historical_position/<int:historical_position_id>/', del_historical_position),
    path('edit_historical_position/<int:historical_position_id>/', edit_historical_position),
    path('list_historical_position/', list_historical_position),

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

    path('add_funds/', add_funds),
    path('del_funds/<int:funds_id>/', del_funds),
    path('edit_funds/<int:funds_id>/', edit_funds),
    path('list_funds/', list_funds),

    path('add_funds_details/<int:funds_id>/', add_funds_details),
    path('del_funds_details/<int:funds_details_id>/', del_funds_details),
    path('edit_funds_details/<int:funds_details_id>/', edit_funds_details),
    path('list_funds_details/', list_funds_details),

    path('add_baseline/', add_baseline),
    path('del_baseline/<int:baseline_id>/', del_baseline),
    path('edit_baseline/<int:baseline_id>/', edit_baseline),
    path('list_baseline/', list_baseline),

    path('capture_dividend_history/', capture_dividend_history),

    path('batch_import/', batch_import),
    path('update_historical_market_value/', update_historical_market_value,
         name='update_historical_market_value'),
    path('get_task_status/', get_task_status, name='get_task_status'),

    path('about/', about),
    path('test/', test),

]
