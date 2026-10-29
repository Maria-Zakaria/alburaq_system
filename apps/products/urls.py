from django.urls import path
from . import views

urlpatterns = [
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/<int:pk>/edit/', views.category_update_view, name='category_update'),
    path('categories/<int:pk>/toggle-active/', views.category_toggle_active_view, name='category_toggle_active'),
    path('products/', views.product_list_view, name='product_list'),
    path('products/create/', views.product_create_view, name='product_create'),
    path('products/<int:pk>/', views.product_detail_view, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update_view, name='product_update'),
    path('products/<int:pk>/toggle-web/', views.product_toggle_web_view, name='product_toggle_web'),
    path('products/<int:pk>/barcode-print/', views.barcode_label_print_view, name='barcode_label_print'),
    path('api/barcode-search/', views.api_search_barcode_view, name='api_search_barcode'),
]
