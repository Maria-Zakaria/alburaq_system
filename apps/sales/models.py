from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from customers.models import Customer
from products.models import Product
from cashbox.models import CashShift

class SaleStatus(models.TextChoices):
    COMPLETED = 'COMPLETED', _('مكتملة')
    PARTIALLY_RETURNED = 'PARTIALLY_RETURNED', _('مرتجع جزئي')
    RETURNED = 'RETURNED', _('مرتجع كامل')
    CANCELLED = 'CANCELLED', _('ملغاة')

class PaymentMethod(models.TextChoices):
    CASH = 'CASH', _('نقدًا (كاش)')
    CARD_NETWORK = 'CARD_NETWORK', _('شبكة / دفع إلكتروني')
    TRANSFER = 'TRANSFER', _('تحويل بنكي')
    CREDIT_DEBT = 'CREDIT_DEBT', _('آجل (دين على العميل)')
    MIXED = 'MIXED', _('دفع مختلط (نقد + شبكة/آجل)')

class SaleInvoice(models.Model):
    """
    فاتورة مبيعات محل البراق (نقطة البيع POS)
    تحفظ الإجمالي، الخصم، طرق الدفع، والربط مع العميل والوردية.
    """
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True, verbose_name=_('رقم الفاتورة'))
    idempotency_key = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name=_('مفتاح منع تكرار الطلب'),
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales',
        verbose_name=_('العميل')
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('الكاشير')
    )
    shift = models.ForeignKey(
        CashShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales',
        verbose_name=_('الوردية')
    )
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المجموع الفرعي'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('مبلغ الخصم'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('صافي الإجمالي'))
    
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المبلغ المدفوع'))
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المبلغ المتبقي (آجل)'))
    change_given = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الباقي للعميل'))
    
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        verbose_name=_('طريقة الدفع الرئيسية')
    )
    status = models.CharField(
        max_length=30,
        choices=SaleStatus.choices,
        default=SaleStatus.COMPLETED,
        verbose_name=_('حالة الفاتورة')
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات الفاتورة'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ ووقت الفاتورة'))

    class Meta:
        verbose_name = _('فاتورة مبيعات')
        verbose_name_plural = _('فواتير المبيعات')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(subtotal__gte=0), name='sale_subtotal_nonneg'),
            models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name='sale_discount_nonneg'),
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='sale_total_nonneg'),
            models.CheckConstraint(condition=models.Q(paid_amount__gte=0), name='sale_paid_nonneg'),
            models.CheckConstraint(condition=models.Q(remaining_amount__gte=0), name='sale_due_nonneg'),
            models.CheckConstraint(condition=models.Q(change_given__gte=0), name='sale_change_nonneg'),
            models.CheckConstraint(condition=models.Q(discount_amount__lte=models.F('subtotal')), name='sale_discount_lte_subtotal'),
            models.CheckConstraint(condition=models.Q(total_amount__lte=models.F('subtotal')), name='sale_total_lte_subtotal'),
            models.CheckConstraint(condition=models.Q(paid_amount__lte=models.F('total_amount')), name='sale_paid_lte_total'),
            models.CheckConstraint(
                condition=models.Q(remaining_amount=models.F('total_amount') - models.F('paid_amount')),
                name='sale_due_matches_paid',
            ),
        ]
        indexes = [
            models.Index(fields=['customer', 'status', 'created_at'], name='sale_customer_status_date_idx'),
            models.Index(fields=['cashier', 'created_at'], name='sale_cashier_created_idx'),
        ]

    def __str__(self):
        return f"فاتورة مبيعات #{self.invoice_number} ({self.total_amount} ر.س)"

class SaleItem(models.Model):
    """
    بند الفاتورة - يحفظ الأسعار والتكلفة التاريخية لحظة البيع
    يمكن أن يكون بند منتج مخزني أو بند خدمة تركيب.
    """
    invoice = models.ForeignKey(SaleInvoice, on_delete=models.CASCADE, related_name='items', verbose_name=_('الفاتورة'))
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('المنتج (إن وجد)'))
    service_name = models.CharField(max_length=200, blank=True, null=True, verbose_name=_('اسم الخدمة (إن وجدت)'))
    
    quantity = models.PositiveIntegerField(default=1, verbose_name=_('الكمية'))
    
    # الأسعار التاريخية المحفوظة لحماية الأرباح عند تغير الأسعار المستقبلية
    historical_sale_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر البيع التاريخي للوحدة'))
    historical_cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('تكلفة الشراء التاريخية للوحدة'))
    
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('خصم البند'))
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('إجمالي البند'))

    class Meta:
        verbose_name = _('بند مبيعات')
        verbose_name_plural = _('بنود المبيعات')
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='sale_item_qty_positive'),
            models.CheckConstraint(condition=models.Q(historical_sale_price__gte=0), name='sale_item_price_nonneg'),
            models.CheckConstraint(condition=models.Q(historical_cost_price__gte=0), name='sale_item_cost_nonneg'),
            models.CheckConstraint(condition=models.Q(discount__gte=0), name='sale_item_discount_nonneg'),
            models.CheckConstraint(condition=models.Q(total_price__gte=0), name='sale_item_total_nonneg'),
            models.CheckConstraint(
                condition=(
                    models.Q(product__isnull=False, service_name__isnull=True)
                    | (
                        models.Q(product__isnull=True)
                        & models.Q(service_name__isnull=False)
                        & ~models.Q(service_name='')
                    )
                ),
                name='sale_item_product_or_service',
            ),
        ]

    def __str__(self):
        name = self.product.name if self.product else (self.service_name or 'بند خدمة')
        return f"{name} x {self.quantity} @ {self.historical_sale_price}"
