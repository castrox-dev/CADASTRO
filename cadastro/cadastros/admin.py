from django.contrib import admin

from .forms_operacao import PlanoDefinicaoForm
from .models import Cadastro
from .operacao_models import (
    AppConfigOperacao,
    CidadeOperacao,
    FaixaVencimento,
    OpcaoVencimento,
    PlanoDefinicao,
    PlanoGrupo,
    VagaInstalacao,
)


@admin.register(Cadastro)
class CadastroAdmin(admin.ModelAdmin):
    list_display = ('nome_razao', 'documento', 'cidade', 'plano', 'status', 'consultor', 'data_cadastro')
    list_filter = ('status', 'cidade', 'plano', 'consultor')
    search_fields = ('nome_razao', 'documento', 'email', 'telefone')


class PlanoDefinicaoInline(admin.StackedInline):
    model = PlanoDefinicao
    form = PlanoDefinicaoForm
    extra = 0
    ordering = ('ordem', 'codigo')


@admin.register(PlanoGrupo)
class PlanoGrupoAdmin(admin.ModelAdmin):
    list_display = ('slug', 'nome')
    search_fields = ('slug', 'nome')
    inlines = [PlanoDefinicaoInline]


class OpcaoVencimentoInline(admin.TabularInline):
    model = OpcaoVencimento
    extra = 0
    ordering = ('ordem',)


class FaixaVencimentoInline(admin.TabularInline):
    model = FaixaVencimento
    extra = 0
    ordering = ('ordem',)


@admin.register(CidadeOperacao)
class CidadeOperacaoAdmin(admin.ModelAdmin):
    list_display = (
        'ordem',
        'nome_exibicao',
        'slug',
        'grupo_planos',
        'ativo',
        'skip_etapa_documentacao',
        'permite_opcao_termo',
        'sempre_exibir_pagamento_instalacao',
    )
    list_filter = ('ativo', 'grupo_planos')
    search_fields = ('slug', 'nome_exibicao', 'ixc_filial_id', 'ixc_cidade_id')
    ordering = ('ordem', 'nome_exibicao')
    fieldsets = (
        (None, {'fields': ('slug', 'nome_exibicao', 'uf_padrao', 'grupo_planos', 'ordem', 'ativo')}),
        (
            'Comportamento da ficha',
            {
                'fields': (
                    'skip_etapa_documentacao',
                    'permite_opcao_termo',
                    'sempre_exibir_pagamento_instalacao',
                    'exigir_fotos_documentacao',
                )
            },
        ),
        (
            'Taxa de instalação (valores exibidos ao cliente)',
            {
                'fields': (
                    'instalacao_com_fidelidade_gratis',
                    'instalacao_valor_com_fidel_reais',
                    'instalacao_valor_sem_fidel_reais',
                )
            },
        ),
        (
            'IXC (filial / cidade no ERP — vazio = usar mapa legado do código)',
            {'fields': ('ixc_filial_id', 'ixc_cidade_id')},
        ),
    )
    inlines = [FaixaVencimentoInline]


@admin.register(FaixaVencimento)
class FaixaVencimentoAdmin(admin.ModelAdmin):
    list_display = ('cidade', 'dia_inicio', 'dia_fim', 'ordem')
    list_filter = ('cidade',)
    inlines = [OpcaoVencimentoInline]


@admin.register(OpcaoVencimento)
class OpcaoVencimentoAdmin(admin.ModelAdmin):
    list_display = ('faixa', 'dia_str', 'ixc_id', 'ordem')


@admin.register(AppConfigOperacao)
class AppConfigOperacaoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'dias_antecedencia_minima_instalacao', 'exigir_fotos_documentacao')

    def has_add_permission(self, request):
        return not AppConfigOperacao.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VagaInstalacao)
class VagaInstalacaoAdmin(admin.ModelAdmin):
    list_display = ('data', 'periodo', 'vagas_max', 'ativo')
    list_filter = ('ativo', 'periodo')
