from django.urls import path

from . import views


urlpatterns = [
    path('', views.stock_list_view, name='inventory_stock_list'),
    path('movements/new/', views.inventory_movement_create_view, name='inventory_movement_create'),
    path('products/<int:product_id>/history/', views.product_stock_history_view, name='inventory_product_history'),
    path(
        'products/<int:product_id>/movements/new/',
        views.inventory_movement_create_view,
        name='inventory_product_movement_create',
    ),
]