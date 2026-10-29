from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class UserRole(models.TextChoices):
    OWNER = 'OWNER', _('مدير النظام / المالك')
    SHIFT_SUPERVISOR = 'SHIFT_SUPERVISOR', _('مشرف الوردية')
    CASHIER = 'CASHIER', _('أمين الصندوق / الكاشير')
    INVENTORY_CLERK = 'INVENTORY_CLERK', _('موظف المخزون')
    TECHNICIAN = 'TECHNICIAN', _('فني الخدمات والتركيبات')

class User(AbstractUser):
    """
    نموذج المستخدم المخصص لمحل البراق
    يدعم تحديد الدور التشغيلي بدقة وسجل العمليات.
    """
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.CASHIER,
        verbose_name=_('الدور / الصلاحية')
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_('رقم الهاتف')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('مستخدم')
        verbose_name_plural = _('المستخدمون')
        ordering = ['-id']

    def __str__(self):
        full_name = self.get_full_name()
        name = full_name if full_name else self.username
        return f"{name} ({self.get_role_display()})"
