from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from accounts.models import UserRole
from audit.models import AuditAction, AuditLog
from cashbox.models import CashShift, ShiftStatus
from payments.models import FinancialTransaction, TransactionType
from sales.models import SaleInvoice, SaleStatus


PAYMENT_METHODS = {'CASH', 'CARD_NETWORK', 'BANK_TRANSFER'}
COLLECTION_TYPES = [TransactionType.SALE_PAYMENT, TransactionType.CUSTOMER_DEBT_PAYMENT]
ZERO = Decimal('0.00')
MAX_PAYMENT = Decimal('9999999999.99')


def _validate_actor(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise ValidationError('يجب تنفيذ العملية بواسطة مستخدم فعال.')
    if not actor.is_superuser and actor.role not in {
        UserRole.OWNER,
        UserRole.SHIFT_SUPERVISOR,
    }:
        raise ValidationError('ليس لديك صلاحية تسجيل دفعات ديون العملاء.')


@transaction.atomic
def register_customer_debt_payment(
    *,
    customer_id,
    sale_invoice_id,
    amount,
    payment_method,
    actor,
    reference='',
    notes='',
    ip_address=None,
):
    _validate_actor(actor)

    try:
        payment_amount = Decimal(str(amount))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError('مبلغ الدفعة غير صحيح.')
    if not payment_amount.is_finite() or payment_amount <= 0:
        raise ValidationError('مبلغ الدفعة يجب أن يكون أكبر من صفر.')
    if payment_amount.as_tuple().exponent < -2:
        raise ValidationError('مبلغ الدفعة لا يقبل أكثر من منزلتين عشريتين.')
    if payment_amount > MAX_PAYMENT:
        raise ValidationError('مبلغ الدفعة يتجاوز الحد المالي المسموح به.')
    if payment_method not in PAYMENT_METHODS:
        raise ValidationError('طريقة الدفع غير معروفة.')

    from customers.models import Customer

    customer = Customer.objects.select_for_update().get(pk=customer_id)
    invoice = SaleInvoice.objects.select_for_update().get(
        pk=sale_invoice_id,
        customer=customer,
    )
    if invoice.status not in {SaleStatus.COMPLETED, SaleStatus.PARTIALLY_RETURNED}:
        raise ValidationError('لا يمكن تحصيل دين فاتورة غير مكتملة أو ملغاة.')

    already_collected = invoice.transactions.filter(
        transaction_type__in=COLLECTION_TYPES
    ).aggregate(total=Sum('amount'))['total'] or ZERO
    due_amount = invoice.total_amount - already_collected
    if due_amount <= 0:
        raise ValidationError('هذه الفاتورة مسددة بالكامل ولا يوجد مبلغ مستحق.')
    if payment_amount > due_amount:
        raise ValidationError('مبلغ الدفعة يتجاوز المبلغ المستحق على الفاتورة.')

    shift = None
    if payment_method == 'CASH':
        open_shifts = list(
            CashShift.objects.select_for_update()
            .filter(status=ShiftStatus.OPEN)
            .order_by('pk')[:2]
        )
        if len(open_shifts) != 1:
            raise ValidationError(
                'يتطلب التحصيل النقدي وجود وردية صندوق مفتوحة واحدة بالضبط.'
            )
        shift = open_shifts[0]

    payment_reference = (reference or '').strip() or f'CUSTPAY-{uuid4().hex[:12].upper()}'
    payment = FinancialTransaction.objects.create(
        transaction_type=TransactionType.CUSTOMER_DEBT_PAYMENT,
        amount=payment_amount,
        payment_method=payment_method,
        sale_invoice=invoice,
        customer=customer,
        shift=shift,
        user=actor,
        reference=payment_reference,
        notes=(notes or '').strip() or 'تحصيل دفعة من دين العميل.',
    )

    paid_total = invoice.transactions.filter(
        transaction_type__in=COLLECTION_TYPES
    ).aggregate(total=Sum('amount'))['total'] or ZERO
    invoice.paid_amount = paid_total
    invoice.remaining_amount = max(ZERO, invoice.total_amount - paid_total)
    invoice.save(update_fields=['paid_amount', 'remaining_amount'])

    AuditLog.objects.create(
        user=actor,
        action=AuditAction.DEBT_ADJUST,
        model_name='FinancialTransaction',
        object_id=str(payment.pk),
        object_repr=f'تحصيل دين العميل {customer.name}',
        before_values={
            'customer_balance': str(customer.outstanding_balance + payment_amount),
            'invoice_due': str(due_amount),
        },
        after_values={
            'customer_balance': str(customer.outstanding_balance),
            'invoice_due': str(invoice.remaining_amount),
            'amount': str(payment_amount),
            'payment_method': payment_method,
            'reference': payment_reference,
            'shift_id': shift.pk if shift else None,
        },
        ip_address=ip_address,
        notes=payment.notes,
    )
    return payment