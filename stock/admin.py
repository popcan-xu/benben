from django.contrib import admin
from .models import Broker,Market,Account,HistoricalRate

# Register your models here.
class brokerAdmin(admin.ModelAdmin):
    list_display = ('broker_name','broker_script')

class marketAdmin(admin.ModelAdmin):
    list_display = ('market_name','market_abbreviation')

class accountAdmin(admin.ModelAdmin):
    list_display = ('account_number','broker')


admin.site.register(Broker, brokerAdmin)
admin.site.register(Market, marketAdmin)
admin.site.register(Account, accountAdmin)
