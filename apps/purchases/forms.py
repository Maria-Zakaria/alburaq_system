from django import forms
from django.forms import BaseFormSet, formset_factory

from products.models import Product
from suppliers.models import Supplier
from payments.models import FinancialTransaction

from .models import PurchaseItem


class PurchaseInvoiceForm(forms.Form):
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True).order_by('name'),
        label='المورد',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    supplier_invoice_number = forms.CharField(
        required=False,
        max_length=100,
        label='رقم فاتورة المورد',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    invoice_date = forms.DateField(
        label='تاريخ الشراء',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    discount_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label='الخصم',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
    )
    tax_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label='الضريبة',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
    )
    paid_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label='المدفوع عند الشراء',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
    )
    payment_method = forms.ChoiceField(
        required=False,
        choices=FinancialTransaction._meta.get_field('payment_method').choices,
        label='طريقة الدفع',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=100,
        label='مرجع الدفع',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    notes = forms.CharField(
        required=False,
        label='ملاحظات الشراء',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class PurchaseItemForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by('name'),
        label='المنتج',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        label='الكمية',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
    )
    unit_cost = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label='تكلفة الوحدة',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
    )


PurchaseItemFormSet = formset_factory(PurchaseItemForm, extra=1, min_num=1, validate_min=True)


class PurchaseReturnForm(forms.Form):
    reason = forms.CharField(
        label='سبب الإرجاع',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class PurchaseReturnItemForm(forms.Form):
    purchase_item = forms.ModelChoiceField(
        queryset=PurchaseItem.objects.none(),
        label='بند فاتورة الشراء',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        label='الكمية المرتجعة',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
    )

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        if invoice is not None:
            self.fields['purchase_item'].queryset = PurchaseItem.objects.filter(
                invoice=invoice
            ).select_related('product')


class BasePurchaseReturnItemFormSet(BaseFormSet):
    def __init__(self, *args, invoice, **kwargs):
        self.invoice = invoice
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['invoice'] = self.invoice
        return kwargs


PurchaseReturnItemFormSet = formset_factory(
    PurchaseReturnItemForm,
    formset=BasePurchaseReturnItemFormSet,
    extra=1,
    min_num=1,
    validate_min=True,
)