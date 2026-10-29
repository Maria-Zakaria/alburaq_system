from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from products.models import Product

class MovementType(models.TextChoices):
    PURCHASE = 'PURCHASE', _('شراء / توريد')
    SALE = 'SALE', _('مبيعات')
    SALE_RETURN = 'SALE_RETURN', _('مرتجع مبيعات')
    PURCHASE_RETURN = 'PURCHASE_RETURN', _('مرتجع مشتريات')
    ADJUSTMENT = 'ADJUSTMENT', _('تعديل جرد')
    DAMAGE = 'DAMAGE', _('تلف / ضياع')
    INITIAL = 'INITIAL', _('إدخال رصيد أول المدة')
    SERVICE_CONSUMPTION = 'SERVICE_CONSUMPTION', _('استهلاك في خدمة تركيب')

class InventoryMovement(models.Model):
    """
    حركات المخزون القابلة للتتبع بنسبة 100%
    تعتبر مصدر الحقيقة الوحيد لكمية المخزون لمنتج معين.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='inventory_movements',
        verbose_name=_('المنتج')
    )
    movement_type = models.CharField(
        max_length=30,
        choices=MovementType.choices,
        verbose_name=_('نوع الحركة')
    )
    quantity = models.IntegerField(
        verbose_name=_('الكمية (موجبة للإضافة، سالبة للخصم)')
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name=_('تكلفة الوحدة التاريخية للحركة')
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_('رقم الفاتورة / المرجع')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('المستخدم المنفذ')
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_('سبب الحركة / ملاحظات'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الحركة'))

    class Meta:
        verbose_name = _('حركة مخزون')
        verbose_name_plural = _('حركات المخزون')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity=0),
                name='inv_move_qty_nonzero',
            ),
            models.CheckConstraint(
                condition=models.Q(unit_cost__gte=0),
                name='inv_move_cost_nonneg',
            ),
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(movement_type=MovementType.INITIAL),
                name='inv_one_initial_per_product',
            ),
        ]
        indexes = [
            models.Index(fields=['product', 'created_at'], name='inv_prod_created_idx'),
            models.Index(fields=['movement_type', 'created_at'], name='inv_type_created_idx'),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.product.name} ({self.quantity:+d})"
