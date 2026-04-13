from django.contrib import admin
from .models import Cadastro

@admin.register(Cadastro)
class CadastroAdmin(admin.ModelAdmin):
    list_display = ('nome_razao', 'documento', 'cidade', 'plano', 'status', 'consultor', 'data_cadastro')
    list_filter = ('status', 'cidade', 'plano', 'consultor')
    search_fields = ('nome_razao', 'documento', 'email', 'telefone')
