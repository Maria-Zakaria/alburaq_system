from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import role_required
from products.models import Product

from .forms import InventoryMovementForm
from .models import InventoryMovement, MovementType
from .services import adjust_stock_to_count, get_stock_quantity, record_movement


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK)
def stock_list_view(request):
	query = request.GET.get('q', '').strip()
	stock_filter = request.GET.get('stock', '')
	products = Product.objects.select_related('category').annotate(
		stock_quantity=Sum('inventory_movements__quantity')
	)

	if query:
		products = products.filter(
			Q(name__icontains=query) |
			Q(barcode__icontains=query) |
			Q(sku__icontains=query)
		)
	if stock_filter == 'low':
		products = products.filter(stock_quantity__gt=0, stock_quantity__lte=F('min_stock_level'))
	elif stock_filter == 'out':
		products = products.filter(Q(stock_quantity__isnull=True) | Q(stock_quantity__lte=0))

	page_obj = Paginator(products.order_by('name'), 25).get_page(request.GET.get('page'))
	return render(request, 'inventory/stock_list.html', {
		'page_obj': page_obj,
		'query': query,
		'stock_filter': stock_filter,
		'title': 'إدارة المخزون — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK)
def product_stock_history_view(request, product_id):
	product = get_object_or_404(Product, pk=product_id)
	movements = product.inventory_movements.select_related('user')
	page_obj = Paginator(movements, 30).get_page(request.GET.get('page'))
	return render(request, 'inventory/product_history.html', {
		'product': product,
		'page_obj': page_obj,
		'stock_quantity': get_stock_quantity(product),
		'title': f'حركة مخزون {product.name} — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK)
def inventory_movement_create_view(request, product_id=None):
	can_edit_cost = request.user.is_superuser or request.user.role in [
		UserRole.OWNER,
		UserRole.SHIFT_SUPERVISOR,
	]
	initial = {}
	if product_id is not None:
		initial['product'] = get_object_or_404(Product, pk=product_id, is_active=True)

	if request.method == 'POST':
		form = InventoryMovementForm(request.POST, can_edit_cost=can_edit_cost)
		if form.is_valid():
			movement_type = form.cleaned_data['movement_type']
			product = form.cleaned_data['product']
			quantity = form.cleaned_data['quantity']
			notes = form.cleaned_data['notes']
			reference = form.cleaned_data['reference']
			unit_cost = form.cleaned_data.get('unit_cost') or 0

			if movement_type == MovementType.INITIAL and not can_edit_cost:
				form.add_error(None, 'إدخال الرصيد الافتتاحي يتطلب صلاحية المالك أو مشرف الوردية.')
			else:
				try:
					if movement_type == MovementType.ADJUSTMENT:
						movement = adjust_stock_to_count(
							product_id=product.pk,
							counted_quantity=quantity,
							actor=request.user,
							notes=notes,
							reference=reference,
							ip_address=request.META.get('REMOTE_ADDR'),
						)
					else:
						delta = -quantity if movement_type == MovementType.DAMAGE else quantity
						movement = record_movement(
							product_id=product.pk,
							movement_type=movement_type,
							quantity_delta=delta,
							actor=request.user,
							unit_cost=unit_cost,
							reference=reference,
							notes=notes,
							ip_address=request.META.get('REMOTE_ADDR'),
						)
				except ValidationError as error:
					form.add_error(None, error)
				else:
					messages.success(request, 'تم تسجيل حركة المخزون بنجاح.')
					return redirect('inventory_product_history', product_id=movement.product_id)
	else:
		form = InventoryMovementForm(initial=initial, can_edit_cost=can_edit_cost)

	return render(request, 'inventory/movement_form.html', {
		'form': form,
		'title': 'تسجيل حركة مخزون — البراق',
	})
