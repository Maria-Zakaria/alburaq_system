from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class TechnicalService(models.Model):
    """
    قائمة الخدمات الفنية والتركيبية المتاحة بمحل البراق (مثل: تركيب شاشة، تركيب LED H7، فك وتركيب)
    """
    name = models.CharField(max_length=200, unique=True, verbose_name=_('اسم الخدمة'))
    description = models.TextField(blank=True, null=True, verbose_name=_('وصف الخدمة'))
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('السعر الأساسي للخدمة'))
    is_active = models.BooleanField(default=True, verbose_name=_('فعال'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإضافة'))

    class Meta:
        verbose_name = _('خدمة فنية')
        verbose_name_plural = _('الخدمات الفنية')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.base_price} ر.س)"

class StickerStatus(models.TextChoices):
    NEW = 'NEW', _('جديد')
    DESIGNING = 'DESIGNING', _('قيد التصميم')
    PRINTING = 'PRINTING', _('قيد الطباعة')
    INSTALLING = 'INSTALLING', _('قيد التركيب')
    COMPLETED = 'COMPLETED', _('مكتمل وجاهز')
    CANCELLED = 'CANCELLED', _('ملغى')

class StickerOrder(models.Model):
    """
    طلب خدمة طباعة وتركيب استيكر ملصق للسيارة
    """
    customer_name = models.CharField(max_length=200, verbose_name=_('اسم العميل'))
    customer_phone = models.CharField(max_length=30, blank=True, null=True, verbose_name=_('رقم هاتف العميل'))
    
    car_type = models.CharField(max_length=100, verbose_name=_('نوع وتفاصيل السيارة'))
    car_plate = models.CharField(max_length=50, blank=True, null=True, verbose_name=_('رقم لوحة السيارة'))
    
    sticker_type = models.CharField(max_length=150, verbose_name=_('نوع الملصق / الاستيكر'))
    length_cm = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name=_('الطول (سم)'))
    width_cm = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name=_('العرض (سم)'))
    material_type = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('نوع مادة الملصق'))
    
    design_image = models.ImageField(upload_to='stickers/designs/', blank=True, null=True, verbose_name=_('صورة التصميم'))
    
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('السعر الإجمالي'))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المبلغ المدفوع'))
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المتبقي'))
    
    status = models.CharField(max_length=20, choices=StickerStatus.choices, default=StickerStatus.NEW, verbose_name=_('حالة الطلب'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات وتفاصيل الاستيكر'))
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('الموظف المسؤول'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ إنشاء الطلب'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('طلب استيكر وطباعة')
        verbose_name_plural = _('طلبات الاستيكرات والطباعة')
        ordering = ['-created_at']

    def __str__(self):
        return f"طلب استيكر #{self.id} - {self.customer_name} ({self.get_status_display()})"
