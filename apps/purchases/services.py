from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from accounts.models import UserRole
from audit.models import AuditAction, AuditLog
from cashbox.models import CashShift, ShiftStatus
from inventory.models import MovementType
from payments.models import FinancialTransaction, TransactionType
from inventory.services import record_movement
from products.models import Product
from suppliers.models import Supplier

from .models import (
    PurchaseInvoice,
    PurchaseInvoiceStatus,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
    PurchaseReturnStatus,
)


CENT = Decimal('0.01')
ZERO = Decimal('0.00')
MAX_MONEY = Decimal('9999999999.99')
MAX_QUANTITY = 2147483647
PURCHASE_ROLES = {UserRole.OWNER, UserRole.SHIFT_SUPERVISOR}


def _money(value, label):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f'{label} غير صحيح.')
    if not amount.is_finite() or amount < 0:
        raise ValidationError(f'{label} يجب أن يكون مبلغًا صالحًا غير سالب.')
    try:
        quantized = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValidationError(f'{label} يتجاوز الدقة المالية المسموحة.')
    if amount != quantized:
        raise ValidationError(f'{label} لا يقبل أكثر من منزلتين عشريتين.')
    if quantized > MAX_MONEY:
        raise ValidationError(f'{label} يتجاوز الحد الأقصى المسموح به.')
    return quantized


def _quantity(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('الكمية يجب أن تكون عددًا صحيحًا موجبًا.')
    if (
        not amount.is_finite()
        or amount != amount.to_integral_value()
        or amount <= 0
        or amount > MAX_QUANTITY
    ):
        raise ValidationError('الكمية يجب أن تكون عددًا صحيحًا موجبًا.')
    return int(amount)


def _validate_actor(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise ValidationError('يجب تنفيذ العملية بواسطة مستخدم فعال.')
    if not actor.is_superuser and actor.role not in PURCHASE_ROLES:
        raise ValidationError('ليس لديك صلاحية اعتماد المشتريات أو مرتجعاتها.')


@transaction.atomic
def create_purchase_invoice(
    *,
    supplier_id,
    invoice_date,
    lines,
    actor,
    supplier_invoice_number='',
    discount_amount=ZERO,
    tax_amount=ZERO,
    paid_amount=ZERO,
    payment_method='CASH',
    payment_reference='',
    notes='',
    ip_address=None,
):
    """Create and receive a purchase invoice as one inventory-safe operation."""
    _validate_actor(actor)
    supplier = Supplier.objects.select_for_update().get(pk=supplier_id, is_active=True)
    supplier_invoice_number = (supplier_invoice_number or '').strip()
    if supplier_invoice_number and PurchaseInvoice.objects.filter(
        supplier=supplier,
        supplier_invoice_number=supplier_invoice_number,
    ).exists():
        raise ValidationError('رقم فاتورة المورد مسجل مسبقًا لهذا المورد.')
    discount = _money(discount_amount, 'الخصم')
    tax = _money(tax_amount, 'الضريبة')
    paid = _money(paid_amount, 'المبلغ المدفوع')

    normalized_lines = []
    for line in lines:
        quantity = _quantity(line.get('quantity'))
        unit_cost = _money(line.get('unit_cost'), 'تكلفة الوحدة')
        normalized_lines.append({
            'product_id': int(line.get('product_id')),
            'quantity': quantity,
            'unit_cost': unit_cost,
            'total_cost': unit_cost * quantity,
        })
    if not normalized_lines:
        raise ValidationError('يجب إضافة بند منتج واحد على الأقل إلى فاتورة الشراء.')

    product_ids = sorted({line['product_id'] for line in normalized_lines})
    locked_products = list(
        Product.objects.select_for_update().filter(pk__in=product_ids, is_active=True).order_by('pk')
    )
    product_by_id = {product.pk: product for product in locked_products}
    if len(product_by_id) != len(product_ids):
        raise ValidationError('يوجد منتج غير موجود أو غير فعال ضمن بنود الشراء.')

    subtotal = sum((line['total_cost'] for line in normalized_lines), ZERO)
    if subtotal > MAX_MONEY:
        raise ValidationError('إجمالي بنود الشراء يتجاوز الحد المالي المسموح به.')
    if discount > subtotal:
        raise ValidationError('الخصم لا يمكن أن يتجاوز إجمالي البنود قبل الخصم.')
    total = subtotal - discount + tax
    if total > MAX_MONEY:
        raise ValidationError('صافي فاتورة الشراء يتجاوز الحد المالي المسموح به.')
    if paid > total:
        raise ValidationError('المبلغ المدفوع لا يمكن أن يتجاوز صافي الفاتورة.')
    invoice = PurchaseInvoice.objects.create(
        invoice_number=f'PUR-{uuid4().hex[:12].upper()}',
        supplier=supplier,
        user=actor,
        supplier_invoice_number=supplier_invoice_number or None,
        invoice_date=invoice_date,
        subtotal_amount=subtotal,
        total_amount=total,
        discount_amount=discount,
        tax_amount=tax,
        paid_amount=paid,
        remaining_amount=total - paid,
        status=PurchaseInvoiceStatus.DRAFT,
        notes=notes.strip() or None,
    )

    for line in normalized_lines:
        product = product_by_id[line['product_id']]
        item = PurchaseItem.objects.create(
            invoice=invoice,
            product=product,
            quantity=line['quantity'],
            unit_cost=line['unit_cost'],
            total_cost=line['total_cost'],
        )
        record_movement(
            product_id=product.pk,
            movement_type=MovementType.PURCHASE,
            quantity_delta=item.quantity,
            unit_cost=item.unit_cost,
            reference=invoice.invoice_number,
            notes=f'استلام فاتورة شراء من المورد {supplier.name}',
            actor=actor,
            ip_address=ip_address,
        )

    invoice.status = PurchaseInvoiceStatus.COMPLETED
    invoice.save(update_fields=['status'])
    if paid:
        shift = None
        if payment_method == 'CASH':
            open_shifts = list(
                CashShift.objects.select_for_update()
                .filter(status=ShiftStatus.OPEN)
                .order_by('pk')[:2]
            )
            if len(open_shifts) != 1:
                raise ValidationError(
                    'يتطلب الدفع النقدي وجود وردية صندوق مفتوحة واحدة بالضبط لربط الحركة بها.'
                )
            shift = open_shifts[0]
        elif payment_method not in {'CARD_NETWORK', 'BANK_TRANSFER'}:
            raise ValidationError('طريقة دفع فاتورة الشراء غير معروفة.')
        payment = FinancialTransaction.objects.create(
            transaction_type=TransactionType.PURCHASE_PAYMENT,
            amount=paid,
            payment_method=payment_method,
            purchase_invoice=invoice,
            supplier=supplier,
            shift=shift,
            user=actor,
            reference=payment_reference.strip() or invoice.invoice_number,
            notes='دفعة عند اعتماد فاتورة الشراء.',
        )
        AuditLog.objects.create(
            user=actor,
            action=AuditAction.CREATE,
            model_name='FinancialTransaction',
            object_id=str(payment.pk),
            object_repr=f'دفعة شراء {invoice.invoice_number}',
            after_values={
                'transaction_type': payment.transaction_type,
                'amount': str(payment.amount),
                'payment_method': payment.payment_method,
                'purchase_invoice_id': invoice.pk,
                'supplier_id': supplier.pk,
                'shift_id': shift.pk if shift else None,
                'reference': payment.reference,
            },
            ip_address=ip_address,
            notes=payment.notes,
        )
    AuditLog.objects.create(
        user=actor,
        action=AuditAction.CREATE,
        model_name='PurchaseInvoice',
        object_id=str(invoice.pk),
        object_repr=invoice.invoice_number,
        after_values={
            'supplier_id': supplier.pk,
            'subtotal_amount': str(subtotal),
            'discount_amount': str(discount),
            'tax_amount': str(tax),
            'total_amount': str(total),
            'paid_amount': str(paid),
            'remaining_amount': str(total - paid),
            'status': invoice.status,
        },
        ip_address=ip_address,
        notes=invoice.notes,
    )
    return invoice


@transaction.atomic
def create_purchase_return(
    *,
    purchase_invoice_id,
    lines,
    actor,
    reason,
    ip_address=None,
):
    """Return received goods without changing or deleting the original invoice."""
    _validate_actor(actor)
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError('سبب إرجاع البضاعة إلى المورد مطلوب.')

    invoice = PurchaseInvoice.objects.select_for_update().select_related('supplier').get(
        pk=purchase_invoice_id
    )
    if invoice.status != PurchaseInvoiceStatus.COMPLETED:
        raise ValidationError('لا يمكن إرجاع بنود فاتورة غير معتمدة ومستلمة.')

    requested = {}
    for line in lines:
        item_id = int(line.get('purchase_item_id'))
        requested[item_id] = requested.get(item_id, 0) + _quantity(line.get('quantity'))
    if not requested:
        raise ValidationError('يجب تحديد بند واحد على الأقل لإرجاعه.')

    items = list(
        PurchaseItem.objects.select_for_update()
        .filter(invoice=invoice, pk__in=sorted(requested))
        .select_related('product')
        .order_by('pk')
    )
    if len(items) != len(requested):
        raise ValidationError('يوجد بند لا يتبع فاتورة الشراء المحددة.')

    normalized = []
    gross_return = ZERO
    for item in items:
        already_returned = item.return_items.filter(
            purchase_return__status=PurchaseReturnStatus.COMPLETED
        ).aggregate(total=Sum('quantity'))['total'] or 0
        return_quantity = requested[item.pk]
        if return_quantity > item.quantity - already_returned:
            raise ValidationError(
                f'الكمية المرتجعة من {item.product.name} تتجاوز الكمية المتبقية للإرجاع.'
            )
        line_gross = item.unit_cost * return_quantity
        gross_return += line_gross
        normalized.append((item, return_quantity, line_gross))

    if invoice.subtotal_amount:
        net_ratio = invoice.total_amount / invoice.subtotal_amount
        return_total = (gross_return * net_ratio).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        return_total = ZERO

    purchase_return = PurchaseReturn.objects.create(
        return_number=f'PR-{uuid4().hex[:12].upper()}',
        purchase_invoice=invoice,
        user=actor,
        total_amount=return_total,
        reason=reason,
        status=PurchaseReturnStatus.COMPLETED,
    )

    allocated_total = ZERO
    for index, (item, quantity, line_gross) in enumerate(normalized):
        if index == len(normalized) - 1:
            line_total = return_total - allocated_total
        elif invoice.subtotal_amount:
            line_total = (line_gross * net_ratio).quantize(CENT, rounding=ROUND_HALF_UP)
            allocated_total += line_total
        else:
            line_total = ZERO
        PurchaseReturnItem.objects.create(
            purchase_return=purchase_return,
            purchase_item=item,
            quantity=quantity,
            unit_cost=item.unit_cost,
            total_amount=line_total,
        )
        record_movement(
            product_id=item.product_id,
            movement_type=MovementType.PURCHASE_RETURN,
            quantity_delta=-quantity,
            unit_cost=item.unit_cost,
            reference=purchase_return.return_number,
            notes=f'مرتجع للمورد: {reason}',
            actor=actor,
            ip_address=ip_address,
        )

    paid_for_invoice = invoice.transactions.filter(
        transaction_type=TransactionType.PURCHASE_PAYMENT
    ).aggregate(total=Sum('amount'))['total'] or ZERO
    prior_returns = invoice.returns.filter(status=PurchaseReturnStatus.COMPLETED).exclude(
        pk=purchase_return.pk
    ).aggregate(total=Sum('total_amount'))['total'] or ZERO
    invoice.paid_amount = paid_for_invoice
    invoice.remaining_amount = max(ZERO, invoice.total_amount - paid_for_invoice - prior_returns - return_total)
    invoice.save(update_fields=['paid_amount', 'remaining_amount'])

    AuditLog.objects.create(
        user=actor,
        action=AuditAction.RETURN,
        model_name='PurchaseReturn',
        object_id=str(purchase_return.pk),
        object_repr=purchase_return.return_number,
        before_values={'purchase_invoice_id': invoice.pk},
        after_values={
            'purchase_invoice_id': invoice.pk,
            'total_amount': str(return_total),
            'status': purchase_return.status,
        },
        ip_address=ip_address,
        notes=reason,
    )
    return purchase_return