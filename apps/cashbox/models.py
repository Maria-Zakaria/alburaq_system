from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class ShiftStatus(models.TextChoices):
    OPEN = 'OPEN', _('مفتوحة')
    CLOSED = 'CLOSED', _('مغلقة')

class CashShift(models.Model):
    """
    سجل وردية الصندوق للكاشير
    يدعم تتبع المبلغ الافتتاحي، المتوقع، الفعلي، والفرق (عجز/زيادة).
    """
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='shifts',
        verbose_name=_('الكاشير / المستخدم')
    )
    opened_at = models.DateTimeField(auto_now_add=True, verbose_name=_('وقت فتح الوردية'))
    closed_at = models.DateTimeField(blank=True, null=True, verbose_name=_('وقت إغلاق الوردية'))
    
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الرصيد الافتتاحي النقدي'))
    expected_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الرصيد النقدي المتوقع'))
    actual_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الرصيد النقدي الفعلي المستلم'))
    difference = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الفرق (عجز بالسالب / زيادة بالموجب)'))
    
    status = models.CharField(max_length=20, choices=ShiftStatus.choices, default=ShiftStatus.OPEN, verbose_name=_('حالة الوردية'))
    closing_notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات الإغلاق والتسوية'))

    class Meta:
        verbose_name = _('وردية صندوق')
        verbose_name_plural = _('ورديات الصندوق')
        ordering = ['-opened_at']

    def __str__(self):
        return f"وردية #{self.id} - {self.cashier.username} ({self.get_status_display()})"

class ShiftAdjustment(models.Model):
    """
    تسويات نقدية استثنائية أثناء الوردية (إيداع/سحب طارئ)
    """
    shift = models.ForeignKey(CashShift, on_delete=models.CASCADE, related_name='adjustments', verbose_name=_('الوردية'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('المبلغ'))
    reason = models.CharField(max_length=255, verbose_name=_('سبب التسوية'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المستخدم المعتمد'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسوية'))

    class Meta:
        verbose_name = _('تسوية وردية')
        verbose_name_plural = _('تسويات الورديات')
