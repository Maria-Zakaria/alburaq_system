from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class AuditAction(models.TextChoices):
    CREATE = 'CREATE', _('إنشاء عنصر')
    UPDATE = 'UPDATE', _('تعديل عنصر')
    DELETE = 'DELETE', _('حذف / تعطيل عنصر')
    PRICE_CHANGE = 'PRICE_CHANGE', _('تغيير سعر منتج')
    STOCK_ADJUST = 'STOCK_ADJUST', _('تعديل مخزون جردي')
    SHIFT_CLOSE = 'SHIFT_CLOSE', _('إغلاق وردية صندوق')
    RETURN = 'RETURN', _('تنفيذ عملية مرتجع')
    DEBT_ADJUST = 'DEBT_ADJUST', _('تعديل / تسوية دين')

class AuditLog(models.Model):
    """
    سجل التدقيق الأمني والمالي الشامل لمحل البراق (Audit Log)
    يوثق كل العمليات الحساسة مع القيم السابقة والجديدة وعنوان IP.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('المستخدم المنفذ')
    )
    action = models.CharField(
        max_length=30,
        choices=AuditAction.choices,
        verbose_name=_('نوع العملية')
    )
    model_name = models.CharField(max_length=100, verbose_name=_('اسم الموديل المتأثر'))
    object_id = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('معرف العنصر المتأثر'))
    object_repr = models.CharField(max_length=255, blank=True, null=True, verbose_name=_('وصف العنصر'))
    
    before_values = models.JSONField(blank=True, null=True, verbose_name=_('القيم قبل التعديل (JSON)'))
    after_values = models.JSONField(blank=True, null=True, verbose_name=_('القيم بعد التعديل (JSON)'))
    
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name=_('عنوان IP الجهاز'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('سبب التغيير / ملاحظات'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ ووقت العملية'))

    class Meta:
        verbose_name = _('سجل تدقيق')
        verbose_name_plural = _('سجل التدقيق الشامل')
        ordering = ['-created_at']

    def __str__(self):
        username = self.user.username if self.user else 'System'
        return f"[{self.get_action_display()}] {self.model_name} #{self.object_id} بواسطة {username}"
