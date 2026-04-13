from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('ficha/', views.client_form, name='client_form'),
    path('cadastro/<int:pk>/', views.cadastro_detail, name='cadastro_detail'),
    path('cadastro/<int:pk>/update-status/', views.update_status, name='update_status'),
]
