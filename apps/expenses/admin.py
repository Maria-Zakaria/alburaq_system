from django.contrib import admin
from .models import ExpenseCategory, Expense, RentPayment

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'amount', 'payment_method', 'date', 'user']
    list_filter = ['category', 'payment_method', 'date']
    search_fields = ['title']

@admin.register(RentPayment)
class RentPaymentAdmin(admin.ModelAdmin):
    list_display = ['period_description', 'amount', 'due_date', 'paid_date', 'payment_method', 'is_paid']
    list_filter = ['is_paid', 'payment_method']
    search_fields = ['period_description']
