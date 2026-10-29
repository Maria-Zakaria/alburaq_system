from django.db import models
from django.utils.translation import gettext_lazy as _

class Customer(models.Model):
    """
    نموذج العملاء لمحل البراق
    الديون والمعاملات محسوبة ديناميكيًا من الفواتير والمدفوعات.
    """
    name = models.CharField(max_length=200, verbose_name=_('اسم العميل'))
    phone = models.CharField(max_length=30, db_index=True, blank=True, null=True, verbose_name=_('رقم الهاتف'))
    email = models.EmailField(blank=True, null=True, verbose_name=_('البريد الإلكتروني'))
    address = models.TextField(blank=True, null=True, verbose_name=_('العنوان / المدينة'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ التسجيل'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('عميل')
        verbose_name_plural = _('العملاء')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone or 'بدون هاتف'})"

    @property
    def outstanding_balance(self):
        from decimal import Decimal

        from django.db.models import Sum

        from payments.models import FinancialTransaction, TransactionType
        from sales.models import SaleInvoice, SaleStatus

        invoice_total = SaleInvoice.objects.filter(
            customer=self,
            status__in=[SaleStatus.COMPLETED, SaleStatus.PARTIALLY_RETURNED],
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
        collected_total = FinancialTransaction.objects.filter(
            customer=self,
            transaction_type__in=[
                TransactionType.SALE_PAYMENT,
                TransactionType.CUSTOMER_DEBT_PAYMENT,
            ],
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return invoice_total - collected_total
