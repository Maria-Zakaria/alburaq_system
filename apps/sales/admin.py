from django.contrib import admin
from .models import SaleInvoice, SaleItem

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    readonly_fields = [
        'invoice', 'product', 'service_name', 'quantity',
        'historical_sale_price', 'historical_cost_price', 'discount', 'total_price',
    ]

@admin.register(SaleInvoice)
class SaleInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'cashier', 'total_amount', 'paid_amount', 'remaining_amount', 'payment_method', 'status', 'created_at']
    list_filter = ['payment_method', 'status', 'created_at']
    search_fields = ['invoice_number', 'customer__name', 'customer__phone']
    inlines = [SaleItemInline]
    readonly_fields = [
        'invoice_number', 'customer', 'cashier', 'shift', 'subtotal',
        'discount_amount', 'total_amount', 'paid_amount', 'remaining_amount',
        'change_given', 'payment_method', 'status', 'notes', 'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
