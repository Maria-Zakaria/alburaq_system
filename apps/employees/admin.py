from django.contrib import admin
from .models import Employee, SalaryRecord, EmployeeAdvance

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['name', 'job_title', 'phone', 'base_salary', 'is_active', 'hired_at']
    list_filter = ['is_active', 'job_title']
    search_fields = ['name', 'phone']

@admin.register(SalaryRecord)
class SalaryRecordAdmin(admin.ModelAdmin):
    list_display = ['employee', 'month', 'year', 'base_salary', 'net_salary', 'is_paid', 'paid_at']
    list_filter = ['month', 'year', 'is_paid']
    search_fields = ['employee__name']

@admin.register(EmployeeAdvance)
class EmployeeAdvanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'amount', 'date', 'is_settled', 'user']
    list_filter = ['is_settled', 'date']
    search_fields = ['employee__name']
