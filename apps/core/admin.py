from django.contrib import admin
from .models import ShopSetting

@admin.register(ShopSetting)
class ShopSettingAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'whatsapp', 'allow_negative_stock', 'updated_at']
