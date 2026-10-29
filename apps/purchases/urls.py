from django.urls import path

from . import views


urlpatterns = [
    path('', views.purchase_list_view, name='purchase_list'),
    path('new/', views.purchase_create_view, name='purchase_create'),
    path('<int:pk>/', views.purchase_detail_view, name='purchase_detail'),
    path('<int:pk>/returns/new/', views.purchase_return_create_view, name='purchase_return_create'),
]