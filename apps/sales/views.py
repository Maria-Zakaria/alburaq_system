import json
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from accounts.models import UserRole
from accounts.permissions import role_required
from customers.models import Customer
from inventory.models import MovementType
from products.models import Product

from .models import SaleInvoice, SaleStatus
from .services import create_sale


SALES_ROLES = (UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.CASHIER)


def _pos_context(
	request,
	*,
	initial_lines=None,
	initial_tenders=None,
	can_discount=False,
	initial_discount='0.00',
	initial_customer_id='',
	initial_cash_received='',
	initial_notes='',
	initial_idempotency_key='',
):
	selected_customer = None
	if initial_customer_id:
		selected_customer = Customer.objects.filter(pk=initial_customer_id).first()
	return {
		'initial_lines': initial_lines or [],
		'initial_tenders': initial_tenders or [],
		'can_discount': can_discount,
		'initial_discount': initial_discount,
		'initial_customer_id': initial_customer_id,
		'selected_customer': selected_customer,
		'initial_cash_received': initial_cash_received,
		'initial_notes': initial_notes,
		'initial_idempotency_key': initial_idempotency_key,
		'title': 'نقطة البيع — البراق',
	}


@login_required
@role_required(*SALES_ROLES)
@require_http_methods(['GET', 'POST'])
def pos_view(request):
	can_discount = request.user.is_superuser or request.user.role in {
		UserRole.OWNER,
		UserRole.SHIFT_SUPERVISOR,
	}
	initial_lines = []
	initial_tenders = []
	initial_discount = '0.00'
	initial_customer_id = ''
	initial_cash_received = ''
	initial_notes = ''
	initial_idempotency_key = str(uuid4())
	if request.method == 'POST':
		try:
			if len(request.body) > 200_000:
				raise ValidationError('بيانات نقطة البيع أكبر من الحجم المسموح.')
			raw_lines = request.POST.get('items_json', '[]')
			raw_tenders = request.POST.get('tenders_json', '[]')
			initial_lines = json.loads(raw_lines)
			initial_tenders = json.loads(raw_tenders)
			initial_discount = request.POST.get('discount_amount', '0.00')
			initial_customer_id = request.POST.get('customer_id', '')
			initial_cash_received = request.POST.get('cash_received', '')
			initial_notes = request.POST.get('notes', '')
			initial_idempotency_key = request.POST.get('idempotency_key', '')
			if not isinstance(initial_lines, list) or not isinstance(initial_tenders, list):
				raise ValidationError('بيانات السلة أو الدفعات غير صحيحة.')
			if not can_discount and request.POST.get('discount_amount', '0').strip() not in {'', '0', '0.0', '0.00'}:
				raise ValidationError('تطبيق الخصم يتطلب صلاحية المالك أو مشرف الوردية.')
			invoice = create_sale(
				lines=initial_lines,
				tenders=initial_tenders,
				customer_id=request.POST.get('customer_id') or None,
				discount_amount=request.POST.get('discount_amount', '0'),
				cash_received=request.POST.get('cash_received') or None,
				idempotency_key=initial_idempotency_key,
				notes=request.POST.get('notes', ''),
				actor=request.user,
				ip_address=request.META.get('REMOTE_ADDR'),
			)
		except (json.JSONDecodeError, TypeError, ValidationError) as error:
			if isinstance(error, ValidationError):
				error_messages = error.messages
			elif isinstance(error, json.JSONDecodeError):
				error_messages = ['بيانات السلة أو الدفعات غير صالحة. أعد إدخالها وحاول مجددًا.']
			else:
				error_messages = ['تعذر قراءة بيانات عملية البيع.']
			for error_message in error_messages:
				messages.error(request, error_message)
			if isinstance(initial_lines, list):
				product_ids = [
					line.get('product_id')
					for line in initial_lines
					if isinstance(line, dict) and line.get('product_id')
				]
				products = {
					product.pk: product
					for product in Product.objects.filter(pk__in=product_ids)
				}
				for line in initial_lines:
					if not isinstance(line, dict) or not line.get('product_id'):
						continue
					product = products.get(line['product_id'])
					if product:
						line['name'] = product.name
						line['sale_price'] = str(product.sale_price)
		else:
			messages.success(request, f'تم إتمام فاتورة البيع {invoice.invoice_number}.')
			return redirect('sale_detail', pk=invoice.pk)

	return render(request, 'sales/pos.html', _pos_context(
		request,
		initial_lines=initial_lines,
		initial_tenders=initial_tenders,
		can_discount=can_discount,
		initial_discount=initial_discount,
		initial_customer_id=initial_customer_id,
		initial_cash_received=initial_cash_received,
		initial_notes=initial_notes,
		initial_idempotency_key=initial_idempotency_key,
	))


@login_required
@role_required(*SALES_ROLES)
@require_GET
def pos_product_search_view(request):
	query = request.GET.get('q', '').strip()
	if len(query) < 2:
		return JsonResponse({'results': []})
	products = Product.objects.filter(is_active=True).filter(
		Q(name__icontains=query) | Q(barcode__icontains=query) | Q(sku__icontains=query)
	).select_related('category').annotate(
		stock=Sum('inventory_movements__quantity')
	).order_by('name')[:20]
	return JsonResponse({
		'results': [
			{
				'id': product.pk,
				'name': product.name,
				'barcode': product.barcode or '',
				'sku': product.sku or '',
				'sale_price': str(product.sale_price),
				'stock': product.stock or 0,
			}
			for product in products
		]
	})


@login_required
@role_required(*SALES_ROLES)
@require_GET
def pos_customer_search_view(request):
	query = request.GET.get('q', '').strip()
	if len(query) < 2:
		return JsonResponse({'results': []})
	customers = Customer.objects.filter(
		Q(name__icontains=query) | Q(phone__icontains=query)
	).order_by('name')[:20]
	return JsonResponse({
		'results': [
			{'id': customer.pk, 'name': customer.name, 'phone': customer.phone or ''}
			for customer in customers
		]
	})


@login_required
@role_required(*SALES_ROLES)
def sale_list_view(request):
	query = request.GET.get('q', '').strip()
	invoices = SaleInvoice.objects.select_related('customer', 'cashier')
	if request.user.role == UserRole.CASHIER and not request.user.is_superuser:
		invoices = invoices.filter(cashier=request.user)
	if query:
		invoices = invoices.filter(
			Q(invoice_number__icontains=query) |
			Q(customer__name__icontains=query) |
			Q(customer__phone__icontains=query)
		)
	status = request.GET.get('status', '')
	if status in SaleStatus.values:
		invoices = invoices.filter(status=status)
	page_obj = Paginator(invoices.order_by('-created_at'), 25).get_page(request.GET.get('page'))
	return render(request, 'sales/sale_list.html', {
		'page_obj': page_obj,
		'query': query,
		'status': status,
		'statuses': SaleStatus.choices,
		'title': 'فواتير المبيعات — البراق',
	})


@login_required
@role_required(*SALES_ROLES)
def sale_detail_view(request, pk):
	invoice = get_object_or_404(
		SaleInvoice.objects.select_related('customer', 'cashier', 'shift'),
		pk=pk,
	)
	if request.user.role == UserRole.CASHIER and not request.user.is_superuser and invoice.cashier_id != request.user.pk:
		from django.core.exceptions import PermissionDenied

		raise PermissionDenied('لا يمكنك عرض فاتورة بيع لم ينفذها حسابك.')
	return render(request, 'sales/sale_detail.html', {
		'invoice': invoice,
		'items': invoice.items.select_related('product').all(),
		'payments': invoice.transactions.select_related('user', 'shift').all(),
		'title': f'فاتورة البيع {invoice.invoice_number} — البراق',
	})


@login_required
@role_required(*SALES_ROLES)
def sale_print_view(request, pk):
	invoice = get_object_or_404(SaleInvoice.objects.select_related('customer', 'cashier'), pk=pk)
	if request.user.role == UserRole.CASHIER and not request.user.is_superuser and invoice.cashier_id != request.user.pk:
		from django.core.exceptions import PermissionDenied

		raise PermissionDenied('لا يمكنك طباعة فاتورة بيع لم ينفذها حسابك.')
	return render(request, 'sales/sale_print.html', {
		'invoice': invoice,
		'items': invoice.items.select_related('product').all(),
		'payments': invoice.transactions.all(),
		'title': f'فاتورة {invoice.invoice_number} — البراق',
	})

# Create your views here.
