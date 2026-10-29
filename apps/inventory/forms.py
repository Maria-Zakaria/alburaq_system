from django import forms

from products.models import Product

from .models import MovementType


class InventoryMovementForm(forms.Form):
    MOVEMENT_CHOICES = (
        (MovementType.INITIAL, 'إدخال رصيد أول المدة'),
        (MovementType.ADJUSTMENT, 'تسوية حسب الجرد الفعلي'),
        (MovementType.DAMAGE, 'تسجيل تلف أو فقد'),
    )

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True).order_by('name'),
        label='المنتج',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    movement_type = forms.ChoiceField(
        choices=MOVEMENT_CHOICES,
        label='نوع الحركة',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(
        min_value=0,
        label='الكمية / الرصيد الفعلي بعد الجرد',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
    )
    unit_cost = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label='تكلفة الوحدة التاريخية (للمالك والمشرف)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
    )
    reference = forms.CharField(
        required=False,
        max_length=100,
        label='رقم المرجع',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    notes = forms.CharField(
        label='السبب / الملاحظات',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


    def __init__(self, *args, can_edit_cost=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not can_edit_cost:
            self.fields.pop('unit_cost')