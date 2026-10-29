from django.db import models
from django.utils.translation import gettext_lazy as _

class Supplier(models.Model):
    """
    نموذج الموردين
    رصيد المورد يتم حسابه ديناميكيًا عبر المعاملات وليس برقم جزافي.
    """
    name = models.CharField(max_length=200, verbose_name=_('اسم المورد / الشركة'))
    phone = models.CharField(max_length=30, blank=True, null=True, verbose_name=_('رقم الهاتف'))
    email = models.EmailField(blank=True, null=True, verbose_name=_('البريد الإلكتروني'))
    address = models.TextField(blank=True, null=True, verbose_name=_('العنوان'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات المورد'))
    is_active = models.BooleanField(default=True, verbose_name=_('مورد فعال'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإضافة'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('مورد')
        verbose_name_plural = _('الموردون')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone or 'No Phone'})"

    @property
    def outstanding_balance(self):
        from decimal import Decimal

        from django.db.models import Sum

        from payments.models import FinancialTransaction, TransactionType
        from purchases.models import PurchaseInvoiceStatus, PurchaseReturn, PurchaseReturnStatus

        invoice_total = self.purchases.filter(status=PurchaseInvoiceStatus.COMPLETED).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        returned_total = PurchaseReturn.objects.filter(
            purchase_invoice__supplier=self,
            status=PurchaseReturnStatus.COMPLETED,
        ).aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0.00')
        payments_total = FinancialTransaction.objects.filter(
            supplier=self,
            transaction_type__in=[
                TransactionType.PURCHASE_PAYMENT,
                TransactionType.SUPPLIER_DEBT_PAYMENT,
            ],
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return invoice_total - returned_total - payments_total
