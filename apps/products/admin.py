from django.contrib import admin
from .models import Category, Product, ProductImage

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    search_fields = ['name']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'sku', 'barcode', 'cost_price', 'sale_price', 'wholesale_price', 'min_stock_level', 'is_active', 'is_published_web']
    list_filter = ['category', 'is_active', 'is_published_web']
    search_fields = ['name', 'sku', 'barcode']
    inlines = [ProductImageInline]
