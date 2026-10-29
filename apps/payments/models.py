from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from customers.models import Customer
from suppliers.models import Supplier
from sales.models import SaleInvoice
from purchases.models import PurchaseInvoice
from cashbox.models import CashShift

class TransactionType(models.TextChoices):
    SALE_PAYMENT = 'SALE_PAYMENT', _('تحصيل قيمة مبيعات')
    PURCHASE_PAYMENT = 'PURCHASE_PAYMENT', _('دفع فاتورة مشتريات')
    CUSTOMER_DEBT_PAYMENT = 'CUSTOMER_DEBT_PAYMENT', _('سداد دين عميل')
    SUPPLIER_DEBT_PAYMENT = 'SUPPLIER_DEBT_PAYMENT', _('سداد دين مورد')
    EXPENSE = 'EXPENSE', _('مصروف تشغيلي')
    SALARY = 'SALARY', _('دفع راتب موظف')
    ADVANCE = 'ADVANCE', _('سلفة موظف')
    CASH_DEPOSIT = 'CASH_DEPOSIT', _('إيداع نقدي بالصندوق')
    CASH_WITHDRAWAL = 'CASH_WITHDRAWAL', _('سحب نقدي من الصندوق')
    CASH_ADJUSTMENT = 'CASH_ADJUSTMENT', _('تسوية مالية')

class FinancialTransaction(models.Model):
    """
    سجل المعاملات المالية القابلة للتتبع بنسبة 100%
    مصدر الحقيقة لدفتر الصندوق، الشبكة، ديون العملاء، وديون الموردين.
    """
    transaction_type = models.CharField(
        max_length=35,
        choices=TransactionType.choices,
        verbose_name=_('نوع المعاملة')
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_('المبلغ')
    )
    payment_method = models.CharField(
        max_length=30,
        choices=[
            ('CASH', _('نقدًا')),
            ('CARD_NETWORK', _('شبكة / دفع إلكتروني')),
            ('BANK_TRANSFER', _('تحويل بنكي')),
        ],
        default='CASH',
        verbose_name=_('طريقة وسيلة الدفع')
    )
    
    # العلاقات المباشرة حسب نوع المعاملة
    sale_invoice = models.ForeignKey(SaleInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name=_('فاتورة المبيعات المرتبطة'))
    purchase_invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name=_('فاتورة المشتريات المرتبطة'))
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name=_('العميل'))
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name=_('المورد'))
    shift = models.ForeignKey(CashShift, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions', verbose_name=_('وردية الصندوق المرتبطة'))
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المستخدم المنفذ'))
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name=_('رقم المرجع / العملية'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('ملاحظات وتسوية'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ المعاملة'))

    class Meta:
        verbose_name = _('معاملة مالية')
        verbose_name_plural = _('المعاملات المالية')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} ر.س ({self.get_payment_method_display()})"
