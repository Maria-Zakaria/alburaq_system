from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Employee(models.Model):
    """
    نموذج بيانات الموظفين الفنيين والعمال بمحل البراق
    """
    name = models.CharField(max_length=200, verbose_name=_('اسم الموظف'))
    phone = models.CharField(max_length=30, blank=True, null=True, verbose_name=_('رقم الهاتف'))
    job_title = models.CharField(max_length=100, verbose_name=_('المسمى الوظيفي'))
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الراتب الأساسي'))
    hired_at = models.DateField(blank=True, null=True, verbose_name=_('تاريخ التعيين'))
    is_active = models.BooleanField(default=True, verbose_name=_('على رأس العمل'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات الموظف'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإضافة'))

    class Meta:
        verbose_name = _('موظف')
        verbose_name_plural = _('الموظفون')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.job_title}"

class SalaryRecord(models.Model):
    """
    سجل الرواتب الشهرية والمسحوبات والخصومات للإدارة
    """
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='salaries', verbose_name=_('الموظف'))
    month = models.PositiveIntegerField(verbose_name=_('الشهر (1-12)'))
    year = models.PositiveIntegerField(verbose_name=_('السنة'))
    
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('الراتب الأساسي'))
    bonuses = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الإضافات / المكافآت'))
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الخصومات'))
    advances_deducted = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('السحوبات المستقطعة'))
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('صافي الراتب الـمستحق'))
    
    is_paid = models.BooleanField(default=False, verbose_name=_('تم دفع الراتب'))
    paid_at = models.DateTimeField(blank=True, null=True, verbose_name=_('تاريخ التسليم'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        verbose_name = _('مسير راتب')
        verbose_name_plural = _('مسيرات الرواتب')
        unique_together = ('employee', 'month', 'year')

    def __str__(self):
        return f"راتب {self.employee.name} - {self.month}/{self.year} ({self.net_salary} ر.س)"

class EmployeeAdvance(models.Model):
    """
    سحوبات وسلف الموظفين
    """
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='advances', verbose_name=_('الموظف'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('مبلغ السلفة / السحب'))
    reason = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('السبب / ملاحظة'))
    date = models.DateField(verbose_name=_('تاريخ السحب'))
    is_settled = models.BooleanField(default=False, verbose_name=_('تم خصمها من الراتب'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المسؤول المعتمد'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))

    class Meta:
        verbose_name = _('سلفة / سحب موظف')
        verbose_name_plural = _('سحوبات وسلف الموظفين')
