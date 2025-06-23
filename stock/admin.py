from django.contrib import admin
from .models import broker,market,account,historical_rate

# Register your models here.
class brokerAdmin(admin.ModelAdmin):
    list_display = ('broker_name','broker_script')

class marketAdmin(admin.ModelAdmin):
    list_display = ('market_name','market_abbreviation')

class accountAdmin(admin.ModelAdmin):
    list_display = ('account_number','broker')


admin.site.register(broker,brokerAdmin)
admin.site.register(market,marketAdmin)
admin.site.register(account,accountAdmin)
