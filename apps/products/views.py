from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from products.models import Category, Product, ProductImage
from products.forms import CategoryForm, ProductForm
from accounts.models import UserRole
from accounts.permissions import role_required

@login_required
@role_required(UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK)
def category_list_view(request):
    """
    عرض وإدارة تصنيفات المنتجات
    """
    categories = Category.objects.all().order_by('name')
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم إضافة التصنيف بنجاح.")
            return redirect('category_list')
        messages.error(request, "تعذر إضافة التصنيف. تحقق من البيانات المدخلة.")
    else:
        form = CategoryForm()
    
    return render(request, 'products/category_list.html', {
        'categories': categories,
        'form': form,
        'title': 'تصنيفات المنتجات — البراق'
    })


@login_required
@role_required(UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK)
def category_update_view(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث التصنيف بنجاح.")
            return redirect('category_list')
        messages.error(request, "تعذر تحديث التصنيف. تحقق من البيانات المدخلة.")
    else:
        form = CategoryForm(instance=category)

    categories = Category.objects.all().order_by('name')
    return render(request, 'products/category_list.html', {
        'categories': categories,
        'form': form,
        'editing_category': category,
        'title': f'تعديل التصنيف {category.name} — البراق'
    })


@login_required
@role_required(UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK)
@require_POST
def category_toggle_active_view(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=['is_active'])
    status_text = "تفعيل" if category.is_active else "تعطيل"
    messages.success(request, f"تم {status_text} التصنيف '{category.name}' دون حذف سجله.")
    return redirect('category_list')

@login_required
def product_list_view(request):
    """
    استعراض المنتجات مع دعم البحث بالباركود والاسم وSKU، التصفية بالحد الأدنى، والتصفح Paginator
    """
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '')
    stock_filter = request.GET.get('stock', '')
    
    products = Product.objects.select_related('category').annotate(
        current_stock_calculated=Sum('inventory_movements__quantity')
    ).order_by('-id')

    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(barcode__icontains=query) |
            Q(sku__icontains=query) |
            Q(description__icontains=query)
        )
    
    if category_id:
        products = products.filter(category_id=category_id)
        
    categories = Category.objects.filter(is_active=True)
    
    paginator = Paginator(products, 15) # 15 منتج في الصفحة
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # حجب سعر التكلفة التنافسي عن الكاشير والفني بحسب الصلاحيات الإدارية
    can_view_cost = request.user.is_superuser or request.user.role in [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR]
    can_manage_products = request.user.is_superuser or request.user.role in [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR]
    can_manage_categories = can_manage_products or request.user.role == UserRole.INVENTORY_CLERK

    return render(request, 'products/product_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'query': query,
        'category_id': category_id,
        'can_view_cost': can_view_cost,
        'can_manage_products': can_manage_products,
        'can_manage_categories': can_manage_categories,
        'title': 'دليل المنتجات والباركود — البراق'
    })

@login_required
def product_detail_view(request, pk):
    """
    عرض تفاصيل المنتج، الصور، رصيد المخزون المحسوب من حركات المخزون، ورسم الباركود
    """
    product = get_object_or_404(Product, pk=pk)
    
    # حساب رصيد المخزون الحالي الفعلي المستند إلى حركات المخزون القابلة للتتبع
    total_stock = product.inventory_movements.aggregate(total=Sum('quantity'))['total'] or 0
    can_view_cost = request.user.is_superuser or request.user.role in [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR]
    can_manage_products = request.user.is_superuser or request.user.role in [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR]

    return render(request, 'products/product_detail.html', {
        'product': product,
        'total_stock': total_stock,
        'can_view_cost': can_view_cost,
        'can_manage_products': can_manage_products,
        'title': f'تفاصيل {product.name} — البراق'
    })

@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def product_create_view(request):
    """
    إضافة منتج جديد وتوليد باركود وSKU تلقائياً إذا رغب المستخدم
    """
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"تم إضافة المنتج '{product.name}' بالباركود #{product.barcode} بنجاح.")
            return redirect('product_detail', pk=product.pk)
        else:
            messages.error(request, "حدث خطأ أثناء إضافة المنتج. تحقق من الحقول المطلوبة والباركود.")
    else:
        form = ProductForm()

    return render(request, 'products/product_form.html', {
        'form': form,
        'action': 'create',
        'title': 'إضافة منتج جديد — البراق'
    })

@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
def product_update_view(request, pk):
    """
    تعديل أسعار وبيانات المنتج
    """
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save()
            messages.success(request, f"تم تحديث المنتج '{product.name}' بنجاح.")
            return redirect('product_detail', pk=product.pk)
        else:
            messages.error(request, "خطأ في التعديل. تأكد من أن الباركود أو SKU غير مكرر مع منتج آخر.")
    else:
        form = ProductForm(instance=product)

    return render(request, 'products/product_form.html', {
        'form': form,
        'action': 'update',
        'product': product,
        'title': f'تعديل المنتج {product.name} — البراق'
    })

@login_required
@role_required(UserRole.OWNER, UserRole.SHIFT_SUPERVISOR)
@require_POST
def product_toggle_web_view(request, pk):
    """
    نشر / إلغاء نشر المنتج على الموقع العام للمحل
    """
    product = get_object_or_404(Product, pk=pk)
    product.is_published_web = not product.is_published_web
    product.save()
    status_text = "نشر" if product.is_published_web else "إلغاء نشر"
    messages.success(request, f"تم {status_text} المنتج '{product.name}' على الموقع العام.")
    return redirect('product_detail', pk=product.pk)

@login_required
def barcode_label_print_view(request, pk):
    """
    صفحة مخصصة لطباعة ملصق الباركود الحراري على طابعات الاستيكرات 80mm / A4
    """
    product = get_object_or_404(Product, pk=pk)
    quantity = int(request.GET.get('qty', 1))
    return render(request, 'products/barcode_label.html', {
        'product': product,
        'quantity': range(quantity),
        'title': f'طباعة ملصق الباركود — {product.name}'
    })

@login_required
def api_search_barcode_view(request):
    """
    API JSON سريعة لبحث الباركود لشاشة الكاشير POS
    """
    code = request.GET.get('code', '').strip()
    if not code:
        return JsonResponse({'success': False, 'error': 'لم يتم تزويد الباركود'}, status=400)
    
    try:
        product = Product.objects.get(Q(barcode=code) | Q(sku=code), is_active=True)
        total_stock = product.inventory_movements.aggregate(total=Sum('quantity'))['total'] or 0
        return JsonResponse({
            'success': True,
            'id': product.id,
            'name': product.name,
            'barcode': product.barcode,
            'sale_price': str(product.sale_price),
            'current_stock': total_stock,
            'category': product.category.name,
        })
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'المنتج غير موجود أو غير فعال في المحل'}, status=404)
