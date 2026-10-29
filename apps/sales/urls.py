from django.urls import path

from . import views


urlpatterns = [
    path('pos/', views.pos_view, name='pos'),
    path('api/products/search/', views.pos_product_search_view, name='pos_product_search'),
    path('api/customers/search/', views.pos_customer_search_view, name='pos_customer_search'),
    path('', views.sale_list_view, name='sale_list'),
    path('<int:pk>/', views.sale_detail_view, name='sale_detail'),
    path('<int:pk>/print/', views.sale_print_view, name='sale_print'),
]