from django.contrib import admin

from .forms_operacao import PlanoDefinicaoForm
from .models import AcessoDadoSensivel, Cadastro
from .operacao_models import (
    AppConfigOperacao,
    CidadeOperacao,
    FaixaVencimento,
    OpcaoVencimento,
    OrigemCanalVenda,
    PlanoDefinicao,
    PlanoGrupo,
    VagaInstalacao,
)


@admin.register(Cadastro)
class CadastroAdmin(admin.ModelAdmin):
    list_display = ('nome_razao', 'documento', 'cidade', 'plano', 'status', 'consultor', 'data_cadastro', 'consentimento_lgpd', 'anonimizado_em')
    list_filter = ('status', 'cidade', 'plano', 'consultor', 'consentimento_lgpd', ('anonimizado_em', admin.EmptyFieldListFilter))
    search_fields = ('nome_razao', 'documento', 'email', 'telefone')
    readonly_fields = ('consentimento_em', 'consentimento_ip', 'anonimizado_em')


@admin.register(AcessoDadoSensivel)
class AcessoDadoSensivelAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'user', 'acao', 'cadastro', 'ip')
    list_filter = ('acao', 'criado_em')
    search_fields = ('user__username', 'cadastro__documento', 'cadastro__nome_razao', 'ip')
    date_hierarchy = 'criado_em'
    readonly_fields = ('user', 'cadastro', 'acao', 'criado_em', 'motivo', 'ip')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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


@admin.register(OrigemCanalVenda)
class OrigemCanalVendaAdmin(admin.ModelAdmin):
    list_display = ('label', 'ixc_id', 'ordem', 'ativo')
    list_editable = ('ixc_id', 'ordem', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('label', 'ixc_id')
    ordering = ('ordem', 'label')
