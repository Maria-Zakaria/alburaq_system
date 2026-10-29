from django.contrib import admin
from .models import TechnicalService, StickerOrder

@admin.register(TechnicalService)
class TechnicalServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'base_price', 'is_active', 'created_at']
    search_fields = ['name']

@admin.register(StickerOrder)
class StickerOrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_name', 'car_type', 'car_plate', 'sticker_type', 'price', 'paid_amount', 'remaining_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['customer_name', 'customer_phone', 'car_plate', 'sticker_type']
