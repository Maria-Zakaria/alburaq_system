from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserRole
from accounts.permissions import role_required
from audit.models import AuditAction, AuditLog
from payments.models import FinancialTransaction, TransactionType
from sales.models import SaleInvoice, SaleStatus

from .forms import CustomerDebtPaymentForm, CustomerForm
from .models import Customer
from .services import register_customer_debt_payment


MONEY_FIELD = DecimalField(max_digits=12, decimal_places=2)
ELIGIBLE_SALE_STATUSES = [SaleStatus.COMPLETED, SaleStatus.PARTIALLY_RETURNED]
COLLECTION_TYPES = [TransactionType.SALE_PAYMENT, TransactionType.CUSTOMER_DEBT_PAYMENT]


def invoices_with_due(customer):
    collections = FinancialTransaction.objects.filter(
        sale_invoice_id=OuterRef('pk'),
        transaction_type__in=COLLECTION_TYPES,
    ).order_by().values('sale_invoice_id').annotate(total=Sum('amount')).values('total')[:1]
    return SaleInvoice.objects.filter(
        customer=customer,
        status__in=ELIGIBLE_SALE_STATUSES,
    ).annotate(
        collected_amount=Coalesce(Subquery(collections, output_field=MONEY_FIELD), Value(Decimal('0.00')), output_field=MONEY_FIELD),
    ).annotate(
        calculated_due=ExpressionWrapper(
            F('total_amount') - F('collected_amount'),
            output_field=MONEY_FIELD,
        )
    )


def customers_with_balances():
    invoice_totals = SaleInvoice.objects.filter(
        customer_id=OuterRef('pk'),
        status__in=ELIGIBLE_SALE_STATUSES,
    ).order_by().values('customer_id').annotate(total=Sum('total_amount')).values('total')[:1]
    collection_totals = FinancialTransaction.objects.filter(
        customer_id=OuterRef('pk'),
        transaction_type__in=COLLECTION_TYPES,
    ).order_by().values('customer_id').annotate(total=Sum('amount')).values('total')[:1]
    return Customer.objects.annotate(
        invoice_total=Coalesce(Subquery(invoice_totals, output_field=MONEY_FIELD), Value(Decimal('0.00')), output_field=MONEY_FIELD),
        collected_total=Coalesce(Subquery(collection_totals, output_field=MONEY_FIELD), Value(Decimal('0.00')), output_field=MONEY_FIELD),
    ).annotate(
        calculated_balance=ExpressionWrapper(
            F('invoice_total') - F('collected_total'),
            output_field=MONEY_FIELD,
        )
    )


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def customer_list_view(request):
    query = request.GET.get('q', '').strip()
    debt_filter = request.GET.get('debt', '')
    customers = customers_with_balances()
    if query:
        customers = customers.filter(
            Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query)
        )
    if debt_filter == 'positive':
        customers = customers.filter(calculated_balance__gt=0)
    elif debt_filter == 'zero':
        customers = customers.filter(calculated_balance=0)
    page_obj = Paginator(customers.order_by('name'), 25).get_page(request.GET.get('page'))
    return render(request, 'customers/customer_list.html', {
        'page_obj': page_obj,
        'query': query,
        'debt_filter': debt_filter,
        'title': 'العملاء — البراق',
    })


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def customer_detail_view(request, pk):
    customer = get_object_or_404(customers_with_balances(), pk=pk)
    invoices = Paginator(
        invoices_with_due(customer).select_related('cashier').order_by('-created_at'),
        15,
    ).get_page(request.GET.get('invoice_page'))
    transactions = Paginator(
        FinancialTransaction.objects.filter(customer=customer)
        .select_related('sale_invoice', 'user', 'shift')
        .order_by('-created_at'),
        15,
    ).get_page(request.GET.get('transaction_page'))
    return render(request, 'customers/customer_detail.html', {
        'customer': customer,
        'invoices': invoices,
        'transactions': transactions,
        'title': f'العميل {customer.name} — البراق',
    })


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def customer_create_view(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            AuditLog.objects.create(
                user=request.user,
                action=AuditAction.CREATE,
                model_name='Customer',
                object_id=str(customer.pk),
                object_repr=customer.name,
                after_values={
                    'name': customer.name,
                    'phone': customer.phone,
                    'email': customer.email,
                },
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'تم تسجيل العميل بنجاح.')
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerForm()
    return render(request, 'customers/customer_form.html', {
        'form': form,
        'title': 'إضافة عميل — البراق',
    })


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def customer_update_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    before_values = {
        'name': customer.name,
        'phone': customer.phone,
        'email': customer.email,
        'address': customer.address,
    }
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            customer = form.save()
            AuditLog.objects.create(
                user=request.user,
                action=AuditAction.UPDATE,
                model_name='Customer',
                object_id=str(customer.pk),
                object_repr=customer.name,
                before_values=before_values,
                after_values={
                    'name': customer.name,
                    'phone': customer.phone,
                    'email': customer.email,
                    'address': customer.address,
                },
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, 'تم تحديث بيانات العميل.')
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'customers/customer_form.html', {
        'form': form,
        'customer': customer,
        'title': f'تعديل العميل {customer.name} — البراق',
    })


@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def customer_debt_payment_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    invoices = invoices_with_due(customer).filter(calculated_due__gt=0).order_by('-created_at')
    if request.method == 'POST':
        form = CustomerDebtPaymentForm(request.POST, invoices=invoices)
        if form.is_valid():
            invoice = form.cleaned_data['sale_invoice']
            try:
                register_customer_debt_payment(
                    customer_id=customer.pk,
                    sale_invoice_id=invoice.pk,
                    amount=form.cleaned_data['amount'],
                    payment_method=form.cleaned_data['payment_method'],
                    reference=form.cleaned_data['reference'],
                    notes=form.cleaned_data['notes'],
                    actor=request.user,
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, 'تم تسجيل دفعة العميل وتحديث الرصيد.')
                return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerDebtPaymentForm(invoices=invoices)
    return render(request, 'customers/debt_payment_form.html', {
        'customer': customer,
        'form': form,
        'title': f'تحصيل دفعة من {customer.name} — البراق',
    })
