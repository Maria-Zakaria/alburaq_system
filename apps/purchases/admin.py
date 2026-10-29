from django.contrib import admin
from .models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem

class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1

@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'supplier', 'total_amount', 'paid_amount', 'remaining_amount', 'status', 'invoice_date']
    list_filter = ['status', 'invoice_date']
    search_fields = ['invoice_number', 'supplier__name', 'supplier_invoice_number']
    inlines = [PurchaseItemInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'purchase_invoice', 'total_amount', 'user', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['return_number', 'purchase_invoice__invoice_number', 'purchase_invoice__supplier__name']
    readonly_fields = [
        'return_number', 'purchase_invoice', 'user', 'total_amount', 'reason', 'status', 'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
