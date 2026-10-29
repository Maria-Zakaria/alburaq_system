from django.urls import path

from . import views


urlpatterns = [
    path('', views.customer_list_view, name='customer_list'),
    path('new/', views.customer_create_view, name='customer_create'),
    path('<int:pk>/', views.customer_detail_view, name='customer_detail'),
    path('<int:pk>/edit/', views.customer_update_view, name='customer_update'),
    path('<int:pk>/payments/new/', views.customer_debt_payment_view, name='customer_debt_payment'),
]