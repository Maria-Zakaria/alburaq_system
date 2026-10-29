from django.contrib import admin
from .models import FinancialTransaction

@admin.register(FinancialTransaction)
class FinancialTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'transaction_type', 'amount', 'payment_method', 'user', 'customer', 'supplier', 'created_at']
    list_filter = ['transaction_type', 'payment_method', 'created_at']
    search_fields = ['reference', 'customer__name', 'supplier__name']
    readonly_fields = [
        'transaction_type', 'amount', 'payment_method', 'sale_invoice',
        'purchase_invoice', 'customer', 'supplier', 'shift', 'user',
        'reference', 'notes', 'created_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
