from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('admin-dash/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dash/manage/', views.manage_consultor, name='manage_consultor'),
    path('admin-dash/manage/<int:pk>/', views.manage_consultor, name='manage_consultor_pk'),
    path('reports/', views.reports_page, name='reports'),
    path('ficha/', views.client_form, name='client_form'),
    path('cadastro/<int:pk>/', views.cadastro_detail, name='cadastro_detail'),
    path('cadastro/<int:pk>/update-status/', views.update_status, name='update_status'),
    path('cadastro/<int:pk>/delete/', views.delete_cadastro, name='delete_cadastro'),
    path('cadastro/<int:pk>/send-ixc/', views.send_to_ixc, name='send_to_ixc'),
]
