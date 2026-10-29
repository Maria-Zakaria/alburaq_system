from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import UserRole
from audit.models import AuditAction, AuditLog
from cashbox.models import CashShift, ShiftStatus
from customers.models import Customer
from core.models import ShopSetting
from inventory.models import MovementType
from inventory.services import get_stock_quantity, get_weighted_average_cost, record_movement
from payments.models import FinancialTransaction, TransactionType
from products.models import Product

from .models import PaymentMethod, SaleInvoice, SaleItem, SaleStatus


CENT = Decimal('0.01')
ZERO = Decimal('0.00')
MAX_AMOUNT = Decimal('9999999999.99')
SALE_ROLES = {UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.CASHIER}
TENDER_METHODS = {
    'CASH': ('CASH', PaymentMethod.CASH),
    'CARD_NETWORK': ('CARD_NETWORK', PaymentMethod.CARD_NETWORK),
    'TRANSFER': ('BANK_TRANSFER', PaymentMethod.TRANSFER),
}


def _money(value, label, *, allow_zero=True):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f'{label} غير صحيح.')
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise ValidationError(f'{label} يجب أن يكون مبلغًا صالحًا موجبًا.')
    try:
        rounded = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValidationError(f'{label} يتجاوز الدقة المالية المسموحة.')
    if amount != rounded:
        raise ValidationError(f'{label} لا يقبل أكثر من منزلتين عشريتين.')
    if rounded > MAX_AMOUNT:
        raise ValidationError(f'{label} يتجاوز الحد المالي المسموح به.')
    return rounded


def _quantity(value):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('كمية المنتج يجب أن تكون عددًا صحيحًا موجبًا.')
    if not quantity.is_finite() or quantity != quantity.to_integral_value() or quantity <= 0:
        raise ValidationError('كمية المنتج يجب أن تكون عددًا صحيحًا موجبًا.')
    if quantity > 2147483647:
        raise ValidationError('الكمية تتجاوز الحد الأعلى المسموح به.')
    return int(quantity)


def _validate_actor(actor):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise ValidationError('يجب تسجيل الدخول بمستخدم فعال لإتمام البيع.')
    if not actor.is_superuser and actor.role not in SALE_ROLES:
        raise ValidationError('ليس لديك صلاحية إتمام عملية البيع.')


def _normalize_lines(lines):
    if not isinstance(lines, list) or not lines:
        raise ValidationError('أضف منتجًا أو خدمة واحدة على الأقل إلى الفاتورة.')

    normalized = []
    for line in lines:
        if not isinstance(line, dict):
            raise ValidationError('بيانات أحد بنود الفاتورة غير صحيحة.')
        quantity = _quantity(line.get('quantity', 1))
        product_id = line.get('product_id')
        if product_id:
            try:
                product_id = int(product_id)
            except (TypeError, ValueError):
                raise ValidationError('معرف المنتج في أحد البنود غير صحيح.')
            normalized.append({
                'product_id': product_id,
                'quantity': quantity,
                'service_name': '',
                'unit_price': None,
            })
            continue

        service_name = str(line.get('service_name', '')).strip()
        if not service_name or len(service_name) > 200:
            raise ValidationError('اسم الخدمة مطلوب ولا يتجاوز 200 حرف.')
        normalized.append({
            'product_id': None,
            'quantity': quantity,
            'service_name': service_name,
            'unit_price': _money(line.get('unit_price'), 'سعر الخدمة'),
        })
    return normalized


def _normalize_tenders(tenders):
    if tenders is None:
        tenders = []
    if not isinstance(tenders, list):
        raise ValidationError('طرق الدفع المرسلة غير صحيحة.')

    normalized = []
    cash_count = 0
    for tender in tenders:
        if not isinstance(tender, dict):
            raise ValidationError('بيانات إحدى وسائل الدفع غير صحيحة.')
        method = str(tender.get('method', '')).strip()
        if method not in TENDER_METHODS:
            raise ValidationError('طريقة الدفع غير مدعومة.')
        amount = _money(tender.get('amount'), 'مبلغ الدفعة', allow_zero=False)
        reference = str(tender.get('reference', '') or '').strip()
        if len(reference) > 100:
            raise ValidationError('مرجع الدفعة لا يتجاوز 100 حرف.')
        normalized.append({
            'method': method,
            'amount': amount,
            'reference': reference,
        })
        cash_count += method == 'CASH'

    if cash_count > 1:
        raise ValidationError('أدخل دفعة نقدية واحدة فقط، ويمكن إضافة وسائل دفع أخرى.')
    return normalized


@transaction.atomic
def create_sale(
    *,
    lines,
    actor,
    tenders=None,
    customer_id=None,
    discount_amount=ZERO,
    cash_received=None,
    idempotency_key=None,
    notes='',
    ip_address=None,
):
    """Commit invoice, tenders, stock movements, and audit records atomically."""
    _validate_actor(actor)
    try:
        idempotency_key = UUID(str(idempotency_key)) if idempotency_key else uuid4()
    except (TypeError, ValueError, AttributeError):
        raise ValidationError('رمز طلب البيع غير صالح.')
    existing_invoice = SaleInvoice.objects.filter(idempotency_key=idempotency_key).first()
    if existing_invoice:
        if existing_invoice.cashier_id != actor.pk:
            raise ValidationError('رمز الطلب مستخدم مسبقًا لعملية أخرى.')
        return existing_invoice

    normalized_lines = _normalize_lines(lines)
    normalized_tenders = _normalize_tenders(tenders)
    discount = _money(discount_amount, 'الخصم')
    if discount and not actor.is_superuser and actor.role not in {
        UserRole.OWNER,
        UserRole.SHIFT_SUPERVISOR,
    }:
        raise ValidationError('تطبيق الخصم يتطلب صلاحية المالك أو مشرف الوردية.')

    customer = None
    if customer_id:
        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            raise ValidationError('بيانات العميل المحدد غير صحيحة.')
        customer = Customer.objects.select_for_update().filter(pk=customer_id).first()
        if customer is None:
            raise ValidationError('العميل المحدد غير موجود.')

    product_ids = sorted({line['product_id'] for line in normalized_lines if line['product_id']})
    products = list(
        Product.objects.select_for_update()
        .filter(pk__in=product_ids, is_active=True)
        .order_by('pk')
    )
    product_by_id = {product.pk: product for product in products}
    if len(product_by_id) != len(product_ids):
        raise ValidationError('يوجد منتج غير موجود أو غير فعال ضمن السلة.')
    existing_invoice = SaleInvoice.objects.filter(idempotency_key=idempotency_key).first()
    if existing_invoice:
        if existing_invoice.cashier_id != actor.pk:
            raise ValidationError('رمز الطلب مستخدم مسبقًا لعملية أخرى.')
        return existing_invoice

    requested_quantities = {}
    for line in normalized_lines:
        if line['product_id']:
            requested_quantities[line['product_id']] = (
                requested_quantities.get(line['product_id'], 0) + line['quantity']
            )
    shop_settings = ShopSetting.objects.first()
    allow_negative_stock = bool(shop_settings and shop_settings.allow_negative_stock)
    for product_id, quantity in requested_quantities.items():
        product = product_by_id[product_id]
        if get_stock_quantity(product) < quantity and not allow_negative_stock:
            raise ValidationError(f'الكمية المطلوبة من {product.name} غير متوفرة في المخزون.')

    prepared_lines = []
    subtotal = ZERO
    for line in normalized_lines:
        if line['product_id']:
            product = product_by_id[line['product_id']]
            unit_price = _money(product.sale_price, f'سعر المنتج {product.name}')
            unit_cost = get_weighted_average_cost(product).quantize(CENT, rounding=ROUND_HALF_UP)
            if unit_cost == ZERO:
                unit_cost = _money(product.cost_price, f'تكلفة المنتج {product.name}')
        else:
            product = None
            unit_price = line['unit_price']
            unit_cost = ZERO
        line_subtotal = unit_price * line['quantity']
        subtotal += line_subtotal
        prepared_lines.append({
            **line,
            'product': product,
            'unit_price': unit_price,
            'unit_cost': unit_cost,
            'line_subtotal': line_subtotal,
        })

    if subtotal > MAX_AMOUNT:
        raise ValidationError('إجمالي السلة يتجاوز الحد المالي المسموح به.')
    if discount > subtotal:
        raise ValidationError('الخصم لا يمكن أن يتجاوز إجمالي الفاتورة.')
    total = subtotal - discount

    paid_total = sum((tender['amount'] for tender in normalized_tenders), ZERO)
    if paid_total > total:
        raise ValidationError('مجموع الدفعات يتجاوز إجمالي الفاتورة.')
    due_total = total - paid_total
    if due_total and customer is None:
        raise ValidationError('اختر العميل لتسجيل المبلغ المتبقي كدين.')

    cash_tender = next((tender for tender in normalized_tenders if tender['method'] == 'CASH'), None)
    change_given = ZERO
    if cash_tender:
        received = _money(
            cash_received if cash_received not in (None, '') else cash_tender['amount'],
            'المبلغ النقدي المستلم',
        )
        if received < cash_tender['amount']:
            raise ValidationError('المبلغ النقدي المستلم أقل من المبلغ المحتسب على الفاتورة.')
        change_given = received - cash_tender['amount']
        shifts = list(
            CashShift.objects.select_for_update()
            .filter(status=ShiftStatus.OPEN)
            .order_by('pk')[:2]
        )
        if len(shifts) != 1:
            raise ValidationError('يتطلب البيع النقدي وجود وردية صندوق مفتوحة واحدة بالضبط.')
        shift = shifts[0]
    else:
        shift = None

    if not normalized_tenders:
        payment_method = PaymentMethod.CREDIT_DEBT
    elif due_total or len(normalized_tenders) > 1:
        payment_method = PaymentMethod.MIXED
    else:
        payment_method = TENDER_METHODS[normalized_tenders[0]['method']][1]

    invoice_number = f'SAL-{uuid4().hex[:12].upper()}'
    try:
        with transaction.atomic():
            invoice = SaleInvoice.objects.create(
                invoice_number=invoice_number,
                idempotency_key=idempotency_key,
                customer=customer,
                cashier=actor,
                shift=shift,
                subtotal=subtotal,
                discount_amount=discount,
                total_amount=total,
                paid_amount=paid_total,
                remaining_amount=due_total,
                change_given=change_given,
                payment_method=payment_method,
                status=SaleStatus.COMPLETED,
                notes=(notes or '').strip() or None,
            )
    except IntegrityError:
        existing_invoice = SaleInvoice.objects.filter(
            idempotency_key=idempotency_key,
            cashier=actor,
        ).first()
        if existing_invoice:
            return existing_invoice
        raise

    allocated_discount = ZERO
    for index, line in enumerate(prepared_lines):
        if index == len(prepared_lines) - 1:
            line_discount = discount - allocated_discount
        elif subtotal:
            line_discount = (discount * line['line_subtotal'] / subtotal).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            allocated_discount += line_discount
        else:
            line_discount = ZERO
        SaleItem.objects.create(
            invoice=invoice,
            product=line['product'],
            service_name=line['service_name'] or None,
            quantity=line['quantity'],
            historical_sale_price=line['unit_price'],
            historical_cost_price=line['unit_cost'],
            discount=line_discount,
            total_price=line['line_subtotal'] - line_discount,
        )
        if line['product']:
            record_movement(
                product_id=line['product'].pk,
                movement_type=MovementType.SALE,
                quantity_delta=-line['quantity'],
                unit_cost=line['unit_cost'],
                reference=invoice.invoice_number,
                notes=f'بيع ضمن فاتورة {invoice.invoice_number}',
                actor=actor,
                ip_address=ip_address,
            )

    for tender in normalized_tenders:
        transaction_method, _ = TENDER_METHODS[tender['method']]
        payment = FinancialTransaction.objects.create(
            transaction_type=TransactionType.SALE_PAYMENT,
            amount=tender['amount'],
            payment_method=transaction_method,
            sale_invoice=invoice,
            customer=customer,
            shift=shift,
            user=actor,
            reference=tender['reference'] or invoice.invoice_number,
            notes='دفعة مستلمة عند إتمام فاتورة البيع.',
        )
        AuditLog.objects.create(
            user=actor,
            action=AuditAction.CREATE,
            model_name='FinancialTransaction',
            object_id=str(payment.pk),
            object_repr=f'تحصيل فاتورة {invoice.invoice_number}',
            after_values={
                'amount': str(payment.amount),
                'payment_method': payment.payment_method,
                'sale_invoice_id': invoice.pk,
                'customer_id': customer.pk if customer else None,
                'shift_id': shift.pk if shift else None,
                'reference': payment.reference,
            },
            ip_address=ip_address,
            notes=payment.notes,
        )

    AuditLog.objects.create(
        user=actor,
        action=AuditAction.CREATE,
        model_name='SaleInvoice',
        object_id=str(invoice.pk),
        object_repr=invoice.invoice_number,
        after_values={
            'customer_id': customer.pk if customer else None,
            'subtotal': str(subtotal),
            'discount_amount': str(discount),
            'total_amount': str(total),
            'paid_amount': str(paid_total),
            'remaining_amount': str(due_total),
            'change_given': str(change_given),
            'payment_method': payment_method,
            'item_count': len(prepared_lines),
        },
        ip_address=ip_address,
        notes=invoice.notes,
    )
    return invoice