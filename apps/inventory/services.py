from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from audit.models import AuditAction, AuditLog
from core.models import ShopSetting
from products.models import Product

from .models import InventoryMovement, MovementType


POSITIVE_MOVEMENTS = {
    MovementType.PURCHASE,
    MovementType.SALE_RETURN,
    MovementType.INITIAL,
}
NEGATIVE_MOVEMENTS = {
    MovementType.SALE,
    MovementType.PURCHASE_RETURN,
    MovementType.DAMAGE,
    MovementType.SERVICE_CONSUMPTION,
}


def get_stock_quantity(product):
    """Return stock as the sum of its immutable movement ledger."""
    total = product.inventory_movements.aggregate(total=Sum('quantity'))['total']
    return total or 0


def get_weighted_average_cost(product):
    """Replay the movement ledger to derive the current moving-average cost."""
    quantity_on_hand = 0
    inventory_value = Decimal('0.00')
    last_average = Decimal('0.00')

    movements = product.inventory_movements.order_by('created_at', 'pk').values_list(
        'movement_type', 'quantity', 'unit_cost'
    )
    for movement_type, quantity_delta, unit_cost in movements:
        movement_cost = Decimal(unit_cost or 0)
        if quantity_delta > 0:
            if quantity_on_hand < 0:
                recovered_shortage = min(-quantity_on_hand, quantity_delta)
                quantity_on_hand += quantity_delta
                remaining_receipt = quantity_delta - recovered_shortage
                if quantity_on_hand <= 0:
                    inventory_value = Decimal(quantity_on_hand) * last_average
                else:
                    inventory_value = Decimal(remaining_receipt) * movement_cost
                    last_average = inventory_value / Decimal(quantity_on_hand)
            else:
                quantity_on_hand += quantity_delta
                inventory_value += Decimal(quantity_delta) * movement_cost
                if quantity_on_hand:
                    last_average = inventory_value / Decimal(quantity_on_hand)
            continue

        quantity_issued = -quantity_delta
        if movement_type == MovementType.PURCHASE_RETURN and movement_cost:
            issue_cost = movement_cost
        elif movement_cost:
            issue_cost = movement_cost
        else:
            issue_cost = last_average

        quantity_on_hand -= quantity_issued
        if quantity_on_hand > 0:
            inventory_value -= Decimal(quantity_issued) * issue_cost
            last_average = inventory_value / Decimal(quantity_on_hand)
        elif quantity_on_hand < 0:
            inventory_value = Decimal(quantity_on_hand) * last_average
        else:
            inventory_value = Decimal('0.00')

    return last_average if quantity_on_hand <= 0 else inventory_value / Decimal(quantity_on_hand)


def _negative_stock_allowed():
    settings = ShopSetting.objects.first()
    return bool(settings and settings.allow_negative_stock)


@transaction.atomic
def record_movement(
    *,
    product_id,
    movement_type,
    quantity_delta,
    actor,
    unit_cost=Decimal('0.00'),
    reference='',
    notes='',
    ip_address=None,
):
    """Append one signed movement after serializing updates for its product."""
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise ValidationError('يجب تسجيل الحركة بواسطة مستخدم فعال.')

    if movement_type not in MovementType.values:
        raise ValidationError('نوع حركة المخزون غير معروف.')

    notes = notes or ''
    reference = reference or ''

    try:
        quantity_value = Decimal(str(quantity_delta))
        unit_cost = Decimal(str(unit_cost))
    except (TypeError, ValueError, ArithmeticError):
        raise ValidationError('الكمية أو تكلفة الوحدة غير صحيحة.')

    if not quantity_value.is_finite() or quantity_value != quantity_value.to_integral_value():
        raise ValidationError('كمية الحركة يجب أن تكون عددًا صحيحًا.')
    quantity_delta = int(quantity_value)

    if quantity_delta == 0:
        raise ValidationError('يجب أن تكون كمية الحركة أكبر من صفر.')
    if not unit_cost.is_finite() or unit_cost < 0:
        raise ValidationError('تكلفة الوحدة لا يمكن أن تكون سالبة أو غير صالحة.')
    if movement_type in POSITIVE_MOVEMENTS and quantity_delta < 0:
        raise ValidationError('هذا النوع من الحركات يجب أن يضيف كمية إلى المخزون.')
    if movement_type in NEGATIVE_MOVEMENTS and quantity_delta > 0:
        raise ValidationError('هذا النوع من الحركات يجب أن يخصم كمية من المخزون.')
    if movement_type == MovementType.ADJUSTMENT and not notes.strip():
        raise ValidationError('سبب تسوية المخزون مطلوب للتدقيق.')

    product = Product.objects.select_for_update().get(pk=product_id)
    current_quantity = get_stock_quantity(product)

    if movement_type == MovementType.INITIAL and product.inventory_movements.exists():
        raise ValidationError('لا يمكن إدخال رصيد أول المدة بعد وجود حركات للمنتج.')

    new_quantity = current_quantity + quantity_delta
    if new_quantity < 0 and not _negative_stock_allowed():
        raise ValidationError('لا يمكن أن تصبح كمية المخزون سالبة حسب إعدادات المحل.')
    if new_quantity < 0 and not notes.strip():
        raise ValidationError('سبب تجاوز المخزون إلى رصيد سالب مطلوب للتوثيق.')

    movement = InventoryMovement.objects.create(
        product=product,
        movement_type=movement_type,
        quantity=quantity_delta,
        unit_cost=unit_cost,
        reference=reference.strip() or None,
        notes=notes.strip() or None,
        user=actor,
    )
    AuditLog.objects.create(
        user=actor,
        action=(
            AuditAction.STOCK_ADJUST
            if movement_type in {MovementType.INITIAL, MovementType.ADJUSTMENT, MovementType.DAMAGE}
            else AuditAction.CREATE
        ),
        model_name='InventoryMovement',
        object_id=str(movement.pk),
        object_repr=f'{product.name} ({movement.quantity:+d})',
        before_values={'stock_quantity': current_quantity},
        after_values={
            'stock_quantity': new_quantity,
            'movement_type': movement_type,
            'quantity': quantity_delta,
            'reference': movement.reference,
        },
        ip_address=ip_address,
        notes=movement.notes,
    )
    return movement


@transaction.atomic
def adjust_stock_to_count(
    *, product_id, counted_quantity, actor, notes, reference='', ip_address=None
):
    """Reconcile ledger quantity to a physical count by recording its delta."""
    try:
        counted_value = Decimal(str(counted_quantity))
    except (TypeError, ValueError):
        raise ValidationError('الكمية الناتجة عن الجرد يجب أن تكون عددًا صحيحًا.')

    if not counted_value.is_finite() or counted_value != counted_value.to_integral_value():
        raise ValidationError('الكمية الناتجة عن الجرد يجب أن تكون عددًا صحيحًا.')
    counted_quantity = int(counted_value)
    if counted_quantity < 0:
        raise ValidationError('كمية الجرد لا يمكن أن تكون سالبة.')
    if not notes or not notes.strip():
        raise ValidationError('سبب تسوية الجرد مطلوب.')

    product = Product.objects.select_for_update().get(pk=product_id)
    delta = counted_quantity - get_stock_quantity(product)
    if delta == 0:
        raise ValidationError('كمية الجرد مطابقة للرصيد الحالي، لا توجد تسوية مطلوبة.')

    return record_movement(
        product_id=product.pk,
        movement_type=MovementType.ADJUSTMENT,
        quantity_delta=delta,
        actor=actor,
        reference=reference,
        notes=notes,
        ip_address=ip_address,
    )