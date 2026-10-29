from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class ExpenseCategory(models.Model):
    """
    تصنيفات المصروفات (كهرباء، ماء، صيانة، أدوات، إيجار، إلخ)
    """
    name = models.CharField(max_length=150, unique=True, verbose_name=_('اسم التصنيف'))
    description = models.TextField(blank=True, null=True, verbose_name=_('وصف التصنيف'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإضافة'))

    class Meta:
        verbose_name = _('تصنيف مصروفات')
        verbose_name_plural = _('تصنيفات المصروفات')
        ordering = ['name']

    def __str__(self):
        return self.name

class Expense(models.Model):
    """
    المصروفات اليومية التشغيلية للمحل
    """
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses', verbose_name=_('التصنيف'))
    title = models.CharField(max_length=200, verbose_name=_('عنوان المصروف'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('المبلغ'))
    payment_method = models.CharField(
        max_length=30,
        choices=[
            ('CASH', _('نقداً من الصندوق')),
            ('CARD_NETWORK', _('شبكة / دفع إلكتروني')),
            ('BANK_TRANSFER', _('تحويل بنكي')),
        ],
        default='CASH',
        verbose_name=_('طريقة الدفع')
    )
    date = models.DateField(verbose_name=_('تاريخ المصروف'))
    receipt_image = models.ImageField(upload_to='expenses/receipts/', blank=True, null=True, verbose_name=_('صورة الإيصال / الفاتورة'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات إضافية'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المستخدم المسجل'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))

    class Meta:
        verbose_name = _('مصروف تشغيلي')
        verbose_name_plural = _('المصروفات التشغيلية')
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.amount} ر.س ({self.category.name})"

class RentPayment(models.Model):
    """
    إيجار محل البراق (مدفوعات الإيجار الدورية)
    """
    period_description = models.CharField(max_length=200, verbose_name=_('وصف الفترة (مثال: إيجار النصف الأول 2026)'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('مبلغ الإيجار'))
    due_date = models.DateField(verbose_name=_('تاريخ الاستحقاق'))
    paid_date = models.DateField(blank=True, null=True, verbose_name=_('تاريخ الدفع التعليقي/الفعلي'))
    payment_method = models.CharField(
        max_length=30,
        choices=[
            ('CASH', _('نقداً')),
            ('BANK_TRANSFER', _('تحويل بنكي')),
            ('CHECK', _('شيك بنكي')),
        ],
        default='BANK_TRANSFER',
        verbose_name=_('طريقة الدفع')
    )
    is_paid = models.BooleanField(default=False, verbose_name=_('تم الدفع بالكامل'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات العقد والإيجار'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المستخدم المسجل'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))

    class Meta:
        verbose_name = _('دفعة إيجار')
        verbose_name_plural = _('دفوعات الإيجار')
        ordering = ['-due_date']

    def __str__(self):
        return f"{self.period_description} - {self.amount} ر.س ({'تم الدفع' if self.is_paid else 'مستحق'})"
