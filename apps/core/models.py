from django.db import models
from django.utils.translation import gettext_lazy as _

class ShopSetting(models.Model):
    """
    إعدادات المحل العامة - المحل الرسمي: البراق
    مفردة داخل النظام لإتاحة تعديل الإعدادات دون تعديل الكود.
    """
    name = models.CharField(max_length=100, default='البراق', verbose_name=_('اسم المحل الرسمي والتجاري'))
    tagline = models.CharField(max_length=255, default='إكسسوارات، زينة، وخدمات السيارات الفنية والملصقات', verbose_name=_('الوصف / الشعار'))
    phone = models.CharField(max_length=20, default='0500000000', verbose_name=_('رقم الهاتف'))
    whatsapp = models.CharField(max_length=20, blank=True, null=True, verbose_name=_('رقم الواتساب'))
    address = models.TextField(blank=True, null=True, verbose_name=_('عنوان المحل'))
    tax_number = models.CharField(max_length=50, blank=True, null=True, verbose_name=_('الرقم الضريبي إن وجد'))
    logo = models.ImageField(upload_to='shop/', blank=True, null=True, verbose_name=_('شعار المحل'))
    allow_negative_stock = models.BooleanField(default=False, verbose_name=_('السماح بالمخزون السالب'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('إعدادات المحل')
        verbose_name_plural = _('إعدادات المحل')

    def __str__(self):
        return f"إعدادات محل {self.name}"
