from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import UserRole
from accounts.permissions import role_required
from audit.models import AuditAction, AuditLog
from purchases.models import PurchaseInvoice

from .forms import SupplierForm
from .models import Supplier


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def supplier_list_view(request):
	query = request.GET.get('q', '').strip()
	status = request.GET.get('status', 'active')
	suppliers = Supplier.objects.all()
	if query:
		suppliers = suppliers.filter(
			Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query)
		)
	if status == 'active':
		suppliers = suppliers.filter(is_active=True)
	elif status == 'inactive':
		suppliers = suppliers.filter(is_active=False)
	page_obj = Paginator(suppliers.order_by('name'), 25).get_page(request.GET.get('page'))
	return render(request, 'suppliers/supplier_list.html', {
		'page_obj': page_obj,
		'query': query,
		'status': status,
		'title': 'الموردون — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def supplier_detail_view(request, pk):
	supplier = get_object_or_404(Supplier, pk=pk)
	invoices = PurchaseInvoice.objects.filter(supplier=supplier).order_by('-invoice_date', '-id')
	page_obj = Paginator(invoices, 20).get_page(request.GET.get('page'))
	return render(request, 'suppliers/supplier_detail.html', {
		'supplier': supplier,
		'page_obj': page_obj,
		'title': f'المورد {supplier.name} — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def supplier_create_view(request):
	if request.method == 'POST':
		form = SupplierForm(request.POST)
		if form.is_valid():
			supplier = form.save()
			AuditLog.objects.create(
				user=request.user,
				action=AuditAction.CREATE,
				model_name='Supplier',
				object_id=str(supplier.pk),
				object_repr=supplier.name,
				after_values={'name': supplier.name, 'phone': supplier.phone, 'is_active': supplier.is_active},
				ip_address=request.META.get('REMOTE_ADDR'),
			)
			messages.success(request, 'تمت إضافة المورد بنجاح.')
			return redirect('supplier_detail', pk=supplier.pk)
	else:
		form = SupplierForm()
	return render(request, 'suppliers/supplier_form.html', {
		'form': form,
		'title': 'إضافة مورد — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def supplier_update_view(request, pk):
	supplier = get_object_or_404(Supplier, pk=pk)
	before_values = {'name': supplier.name, 'phone': supplier.phone, 'email': supplier.email}
	if request.method == 'POST':
		form = SupplierForm(request.POST, instance=supplier)
		if form.is_valid():
			supplier = form.save()
			AuditLog.objects.create(
				user=request.user,
				action=AuditAction.UPDATE,
				model_name='Supplier',
				object_id=str(supplier.pk),
				object_repr=supplier.name,
				before_values=before_values,
				after_values={'name': supplier.name, 'phone': supplier.phone, 'email': supplier.email},
				ip_address=request.META.get('REMOTE_ADDR'),
			)
			messages.success(request, 'تم تحديث بيانات المورد.')
			return redirect('supplier_detail', pk=supplier.pk)
	else:
		form = SupplierForm(instance=supplier)
	return render(request, 'suppliers/supplier_form.html', {
		'form': form,
		'supplier': supplier,
		'title': f'تعديل المورد {supplier.name} — البراق',
	})


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
@require_POST
def supplier_toggle_active_view(request, pk):
	supplier = get_object_or_404(Supplier, pk=pk)
	previous = supplier.is_active
	supplier.is_active = not supplier.is_active
	supplier.save(update_fields=['is_active', 'updated_at'])
	AuditLog.objects.create(
		user=request.user,
		action=AuditAction.UPDATE,
		model_name='Supplier',
		object_id=str(supplier.pk),
		object_repr=supplier.name,
		before_values={'is_active': previous},
		after_values={'is_active': supplier.is_active},
		ip_address=request.META.get('REMOTE_ADDR'),
		notes='تغيير حالة المورد دون حذف سجله أو معاملاته.',
	)
	messages.success(request, 'تم تحديث حالة المورد دون حذف بياناته.')
	return redirect('supplier_detail', pk=supplier.pk)
