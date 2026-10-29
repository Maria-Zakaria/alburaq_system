from django import forms

from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'dir': 'ltr'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'name': 'اسم العميل',
            'phone': 'رقم الهاتف',
            'email': 'البريد الإلكتروني',
            'address': 'العنوان / المدينة',
            'notes': 'ملاحظات',
        }


class CustomerDebtPaymentForm(forms.Form):
    sale_invoice = forms.ModelChoiceField(
        queryset=None,
        label='فاتورة البيع المستحقة',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    amount = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        label='مبلغ الدفعة',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
    )
    payment_method = forms.ChoiceField(
        choices=[
            ('CASH', 'نقدًا'),
            ('CARD_NETWORK', 'شبكة / دفع إلكتروني'),
            ('BANK_TRANSFER', 'تحويل بنكي'),
        ],
        label='طريقة الدفع',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    reference = forms.CharField(
        required=False,
        max_length=100,
        label='مرجع العملية',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    notes = forms.CharField(
        required=False,
        label='ملاحظات',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )

    def __init__(self, *args, invoices, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sale_invoice'].queryset = invoices

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount.as_tuple().exponent < -2:
            raise forms.ValidationError('مبلغ الدفعة لا يقبل أكثر من منزلتين عشريتين.')
        return amount