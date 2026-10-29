from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from suppliers.models import Supplier
from products.models import Product

class PurchaseInvoiceStatus(models.TextChoices):
    DRAFT = 'DRAFT', _('مسودة')
    COMPLETED = 'COMPLETED', _('معتمدة ومستلمة')
    CANCELLED = 'CANCELLED', _('ملغاة')

class PurchaseInvoice(models.Model):
    """
    فاتورة المشتريات من المورد
    """
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True, verbose_name=_('رقم الفاتورة بالنظام'))
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchases', verbose_name=_('المورد'))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المستخدم المستلم'))
    
    supplier_invoice_number = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('رقم فاتورة المورد الخارجي'))
    invoice_date = models.DateField(verbose_name=_('تاريخ الفاتورة'))
    
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('الإجمالي قبل الخصم والضريبة'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('صافي المستحق'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('الخصم'))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المبلغ المدفوع للمورد'))
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name=_('المبلغ المتبقي (الدين)'))
    
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name=_('الضريبة'))
    status = models.CharField(max_length=20, choices=PurchaseInvoiceStatus.choices, default=PurchaseInvoiceStatus.DRAFT, verbose_name=_('حالة الفاتورة'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات الشراء'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))

    class Meta:
        verbose_name = _('فاتورة مشتريات')
        verbose_name_plural = _('فواتير المشتريات')
        ordering = ['-invoice_date', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='purchase_total_nonneg'),
            models.CheckConstraint(condition=models.Q(subtotal_amount__gte=0), name='purchase_subtotal_nonneg'),
            models.CheckConstraint(condition=models.Q(discount_amount__gte=0), name='purchase_discount_nonneg'),
            models.CheckConstraint(condition=models.Q(tax_amount__gte=0), name='purchase_tax_nonneg'),
            models.CheckConstraint(condition=models.Q(paid_amount__gte=0), name='purchase_paid_nonneg'),
            models.CheckConstraint(condition=models.Q(paid_amount__lte=models.F('total_amount')), name='purchase_paid_lte_total'),
            models.CheckConstraint(condition=models.Q(remaining_amount__gte=0), name='purchase_due_nonneg'),
            models.CheckConstraint(condition=models.Q(discount_amount__lte=models.F('subtotal_amount')), name='purchase_discount_lte_subtotal'),
            models.UniqueConstraint(
                fields=['supplier', 'supplier_invoice_number'],
                condition=(
                    models.Q(supplier_invoice_number__isnull=False)
                    & ~models.Q(supplier_invoice_number='')
                ),
                name='purchase_supplier_invoice_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['supplier', 'status', 'invoice_date'], name='purchase_supp_status_date_idx'),
        ]

    def __str__(self):
        return f"فاتورة مشتريات #{self.invoice_number} - {self.supplier.name}"

class PurchaseItem(models.Model):
    """
    عنصر داخل فاتورة المشتريات
    """
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='items', verbose_name=_('الفاتورة'))
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name=_('المنتج'))
    quantity = models.PositiveIntegerField(verbose_name=_('الكمية المشتراة'))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر شراء الوحدة'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('الإجمالي'))

    class Meta:
        verbose_name = _('بند شراء')
        verbose_name_plural = _('بنود المشتريات')
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='purchase_item_qty_positive'),
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name='purchase_item_cost_nonneg'),
            models.CheckConstraint(condition=models.Q(total_cost__gte=0), name='purchase_item_total_nonneg'),
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity} @ {self.unit_cost}"


class PurchaseReturnStatus(models.TextChoices):
    COMPLETED = 'COMPLETED', _('معتمد ومرتجع للمورد')
    CANCELLED = 'CANCELLED', _('ملغى')


class PurchaseReturn(models.Model):
    return_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم مرتجع الشراء'))
    purchase_invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.PROTECT,
        related_name='returns',
        verbose_name=_('فاتورة الشراء الأصلية'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('المستخدم المنفذ'),
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('قيمة المرتجع'))
    reason = models.TextField(verbose_name=_('سبب المرتجع'))
    status = models.CharField(
        max_length=20,
        choices=PurchaseReturnStatus.choices,
        default=PurchaseReturnStatus.COMPLETED,
        verbose_name=_('الحالة'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ المرتجع'))

    class Meta:
        verbose_name = _('مرتجع مشتريات')
        verbose_name_plural = _('مرتجعات المشتريات')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='purchase_return_total_nonneg'),
        ]
        indexes = [models.Index(fields=['purchase_invoice', 'status'], name='pur_ret_invoice_status_idx')]

    def __str__(self):
        return f"مرتجع #{self.return_number} — {self.purchase_invoice.invoice_number}"


class PurchaseReturnItem(models.Model):
    purchase_return = models.ForeignKey(
        PurchaseReturn,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('مرتجع الشراء'),
    )
    purchase_item = models.ForeignKey(
        PurchaseItem,
        on_delete=models.PROTECT,
        related_name='return_items',
        verbose_name=_('بند الشراء الأصلي'),
    )
    quantity = models.PositiveIntegerField(verbose_name=_('الكمية المرتجعة'))
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('تكلفة الوحدة التاريخية'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('قيمة البند'))

    class Meta:
        verbose_name = _('بند مرتجع مشتريات')
        verbose_name_plural = _('بنود مرتجعات المشتريات')
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='purchase_return_item_qty_positive'),
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name='purchase_return_item_cost_nonneg'),
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name='purchase_return_item_total_nonneg'),
            models.UniqueConstraint(fields=['purchase_return', 'purchase_item'], name='purchase_return_item_unique'),
        ]

    def __str__(self):
        return f"{self.purchase_item.product.name} × {self.quantity}"
