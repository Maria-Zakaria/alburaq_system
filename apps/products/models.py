from django.db import models
from django.utils.translation import gettext_lazy as _

class Category(models.Model):
    """
    تصنيفات المنتجات (إضاءة، شاشات، كاميرات، إكسسوارات، إلخ)
    """
    name = models.CharField(max_length=100, unique=True, verbose_name=_('اسم التصنيف'))
    description = models.TextField(blank=True, null=True, verbose_name=_('وصف التصنيف'))
    is_active = models.BooleanField(default=True, verbose_name=_('فعال'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        verbose_name = _('تصنيف')
        verbose_name_plural = _('التصنيفات')
        ordering = ['name']

    def __str__(self):
        return self.name

class Product(models.Model):
    """
    نموذج المنتجات الخاص بمحل البراق
    يدعم الباركود، SKU، الأسعار الشراء والبيع والكتلة، والحد الأدنى للمخزون والنشر.
    """
    category = models.ForeignKey(
        Category, 
        on_delete=models.PROTECT, 
        related_name='products',
        verbose_name=_('التصنيف')
    )
    name = models.CharField(max_length=200, verbose_name=_('اسم المنتج'))
    description = models.TextField(blank=True, null=True, verbose_name=_('وصف المنتج'))
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name=_('رمز SKU'))
    barcode = models.CharField(max_length=100, unique=True, db_index=True, blank=True, null=True, verbose_name=_('الباركود'))
    
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('سعر الشراء الحالي'))
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('سعر البيع الأساسي'))
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('سعر البيع بالجملة'))
    
    min_stock_level = models.PositiveIntegerField(default=5, verbose_name=_('الحد الأدنى للمخزون'))
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name=_('الصورة الرئيسية'))
    
    is_active = models.BooleanField(default=True, verbose_name=_('منتج فعال'))
    is_published_web = models.BooleanField(default=False, verbose_name=_('منشور على الموقع العام'))
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('منتج')
        verbose_name_plural = _('المنتجات')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.barcode or self.sku or 'No Code'})"

class ProductImage(models.Model):
    """
    صور إضافية للمنتج
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images', verbose_name=_('المنتج'))
    image = models.ImageField(upload_to='products/gallery/', verbose_name=_('صورة الإكسسوار'))
    caption = models.CharField(max_length=150, blank=True, null=True, verbose_name=_('تعليق على الصورة'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الرفع'))

    class Meta:
        verbose_name = _('صورة منتج')
        verbose_name_plural = _('صور المنتجات')
