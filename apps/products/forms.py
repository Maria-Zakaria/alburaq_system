from django import forms
from products.models import Category, Product, ProductImage
from services.barcode_service import BarcodeService

class CategoryForm(forms.ModelForm):
    """
    نموذج إضافة وتعديل التصنيفات
    """
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم التصنيف (مثال: إضاءة، شاشات)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'وصف اختياري للتصنيف'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'اسم التصنيف',
            'description': 'الوصف',
            'is_active': 'تصنيف نشط',
        }

class ProductForm(forms.ModelForm):
    """
    نموذج إضافة وتعديل المنتجات لمحل البراق
    """
    class Meta:
        model = Product
        fields = [
            'category', 'name', 'description', 'sku', 'barcode',
            'cost_price', 'sale_price', 'wholesale_price',
            'min_stock_level', 'image', 'is_active', 'is_published_web'
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المنتج (مثال: شاشة سيارة 9 بوصة)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'المواصفات والتفاصيل'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اتركه فارغاً للتوليد التلقائي'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أمسح الباركود أو اتركه للتوليد التلقائي'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'wholesale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'min_stock_level': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_published_web': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'category': 'التصنيف الرئيسية',
            'name': 'اسم المنتج',
            'description': 'الوصف والتفاصيل',
            'sku': 'رمز SKU',
            'barcode': 'الباركود',
            'cost_price': 'سعر الشراء (التكلفة الحالية)',
            'sale_price': 'سعر البيع الأساسي',
            'wholesale_price': 'سعر الجملة',
            'min_stock_level': 'الحد الأدنى للمخزون (لتنبيهات النقص)',
            'image': 'الصورة الرئيسية',
            'is_active': 'منتج فعال',
            'is_published_web': 'نشر المنتج على الموقع العام',
        }

    def clean(self):
        cleaned_data = super().clean()
        barcode = cleaned_data.get('barcode')
        sku = cleaned_data.get('sku')

        # توليد تلقائي للباركود والـ SKU إذا لم يتم إدخالهما
        if not barcode:
            cleaned_data['barcode'] = BarcodeService.generate_unique_barcode()
        if not sku:
            cleaned_data['sku'] = BarcodeService.generate_unique_sku()

        return cleaned_data
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('حجم صورة المنتج يجب ألا يتجاوز 5 ميغابايت.')
        return image
