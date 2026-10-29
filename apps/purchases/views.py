from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserRole
from accounts.permissions import role_required
from suppliers.models import Supplier

from .forms import (
	PurchaseInvoiceForm,
	PurchaseItemFormSet,
	PurchaseReturnForm,
	PurchaseReturnItemFormSet,
)
from .models import PurchaseInvoice, PurchaseInvoiceStatus
from .services import create_purchase_invoice, create_purchase_return


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def purchase_list_view(request):
	query = request.GET.get('q', '').strip()
	status = request.GET.get('status', '')
	invoices = PurchaseInvoice.objects.select_related('supplier', 'user')
	if query:
		invoices = invoices.filter(
			Q(invoice_number__icontains=query) |
			Q(supplier_invoice_number__icontains=query) |
			Q(supplier__name__icontains=query)
		)
	if status in PurchaseInvoiceStatus.values:
		invoices = invoices.filter(status=status)
	page_obj = Paginator(invoices, 25).get_page(request.GET.get('page'))
	return render(request, 'purchases/purchase_list.html', {
		'page_obj': page_obj,
		'query': query,
		'status': status,
		'statuses': PurchaseInvoiceStatus.choices,
		'title': 'فواتير المشتريات — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def purchase_detail_view(request, pk):
	invoice = get_object_or_404(
		PurchaseInvoice.objects.select_related('supplier', 'user'),
		pk=pk,
	)
	return render(request, 'purchases/purchase_detail.html', {
		'invoice': invoice,
		'items': invoice.items.select_related('product').all(),
		'returns': invoice.returns.select_related('user').prefetch_related('items__purchase_item__product'),
		'title': f'فاتورة شراء {invoice.invoice_number} — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def purchase_create_view(request):
	if request.method == 'POST':
		form = PurchaseInvoiceForm(request.POST)
		item_formset = PurchaseItemFormSet(request.POST, prefix='items')
		if form.is_valid() and item_formset.is_valid():
			lines = [
				{
					'product_id': item.cleaned_data['product'].pk,
					'quantity': item.cleaned_data['quantity'],
					'unit_cost': item.cleaned_data['unit_cost'],
				}
				for item in item_formset
				if item.cleaned_data
			]
			try:
				invoice = create_purchase_invoice(
					supplier_id=form.cleaned_data['supplier'].pk,
					supplier_invoice_number=form.cleaned_data['supplier_invoice_number'],
					invoice_date=form.cleaned_data['invoice_date'],
					discount_amount=form.cleaned_data['discount_amount'] or 0,
					tax_amount=form.cleaned_data['tax_amount'] or 0,
					paid_amount=form.cleaned_data['paid_amount'] or 0,
					payment_method=form.cleaned_data['payment_method'] or 'CASH',
					payment_reference=form.cleaned_data['payment_reference'],
					notes=form.cleaned_data['notes'],
					lines=lines,
					actor=request.user,
					ip_address=request.META.get('REMOTE_ADDR'),
				)
			except ValidationError as error:
				form.add_error(None, error)
			else:
				messages.success(request, 'تم اعتماد فاتورة الشراء واستلام الأصناف وتحديث المخزون.')
				return redirect('purchase_detail', pk=invoice.pk)
	else:
		form = PurchaseInvoiceForm()
		item_formset = PurchaseItemFormSet(prefix='items')
	return render(request, 'purchases/purchase_form.html', {
		'form': form,
		'item_formset': item_formset,
		'title': 'تسجيل فاتورة شراء — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def purchase_return_create_view(request, pk):
	invoice = get_object_or_404(PurchaseInvoice.objects.select_related('supplier'), pk=pk)
	if request.method == 'POST':
		form = PurchaseReturnForm(request.POST)
		item_formset = PurchaseReturnItemFormSet(request.POST, prefix='items', invoice=invoice)
		if form.is_valid() and item_formset.is_valid():
			lines = [
				{
					'purchase_item_id': item.cleaned_data['purchase_item'].pk,
					'quantity': item.cleaned_data['quantity'],
				}
				for item in item_formset
				if item.cleaned_data
			]
			try:
				purchase_return = create_purchase_return(
					purchase_invoice_id=invoice.pk,
					lines=lines,
					actor=request.user,
					reason=form.cleaned_data['reason'],
					ip_address=request.META.get('REMOTE_ADDR'),
				)
			except ValidationError as error:
				form.add_error(None, error)
			else:
				messages.success(request, 'تم اعتماد المرتجع وتحديث المخزون ورصيد المورد.')
				return redirect('purchase_detail', pk=purchase_return.purchase_invoice_id)
	else:
		form = PurchaseReturnForm()
		item_formset = PurchaseReturnItemFormSet(prefix='items', invoice=invoice)
	return render(request, 'purchases/return_form.html', {
		'invoice': invoice,
		'form': form,
		'item_formset': item_formset,
		'title': f'مرتجع فاتورة {invoice.invoice_number} — البراق',
	})
