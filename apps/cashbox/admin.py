from django.contrib import admin
from .models import CashShift, ShiftAdjustment

class ShiftAdjustmentInline(admin.TabularInline):
    model = ShiftAdjustment
    extra = 0

@admin.register(CashShift)
class CashShiftAdmin(admin.ModelAdmin):
    list_display = ['id', 'cashier', 'opened_at', 'closed_at', 'opening_balance', 'expected_closing_balance', 'actual_closing_balance', 'difference', 'status']
    list_filter = ['status', 'opened_at']
    search_fields = ['cashier__username']
    inlines = [ShiftAdjustmentInline]
