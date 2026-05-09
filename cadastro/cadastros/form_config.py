"""
Monta o JSON da ficha pública para o JS (planDetails, cidades, regras de vencimento).
"""
from django.db.models import Prefetch

from .operacao_models import CidadeOperacao, OpcaoVencimento, PlanoDefinicao, PlanoGrupo, AppConfigOperacao

# Texto exibido para o opcional quando o admin deixa o campo em branco
TEXTO_OPCIONAL_REPETIDOR_PADRAO = 'Deseja alugar repetidor Mesh por R$ 29,99/mês?'

# Plano sem roteador (ex.: Essencial): duas opções independentes no front
TEXTO_OPCIONAL_COMBO_ROTEADOR_MESH = (
    'Aluguel opcional — pode marcar um, os dois ou nenhum: '
    'roteador Wi-Fi R$ 10,00/mês; repetidor Mesh R$ 29,99/mês.'
)

# Texto padrão do Essencial no BD (uma opção). A UI «roteador + mesh» independente só na filial 7 (Jacone, Saquarema, Araruama, Unamar), via JS.
TEXTO_OPCIONAL_ROTEADOR_ESSENCIAL = 'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?'

# Sem 700 MEGA (prime) nestas cidades — oferta vai até 500 MEGA (turbo).
CIDADES_SEM_PLANO_PRIME = frozenset({'araruama', 'jacone', 'saquarema', 'unamar'})


def _excluded_plan_codes_cidade(slug: str):
    if slug == 'marica':
        return ['turbo']
    if slug in CIDADES_SEM_PLANO_PRIME:
        return ['prime']
    return []


def _plan_details_by_grupo():
    result = {}
    for grupo in PlanoGrupo.objects.prefetch_related(
        Prefetch('planos', queryset=PlanoDefinicao.objects.order_by('ordem'))
    ):
        plans = {}
        for p in grupo.planos.all():
            entry = {'name': p.titulo, 'desc': p.descricao_html}
            tx = (p.texto_opcional or '').strip()
            entry['opcional'] = tx or TEXTO_OPCIONAL_REPETIDOR_PADRAO
            plans[p.codigo] = entry
        result[grupo.slug] = plans
    return result


def _vencimento_rules(cidade):
    rules = []
    for faixa in cidade.faixas_vencimento.prefetch_related(
        Prefetch('opcoes', queryset=OpcaoVencimento.objects.order_by('ordem'))
    ).order_by('ordem'):
        rules.append(
            {
                'fromDay': faixa.dia_inicio,
                'toDay': faixa.dia_fim,
                'options': [
                    {'day': o.dia_str, 'id': o.ixc_id}
                    for o in faixa.opcoes.all()
                ],
            }
        )
    return rules


def get_form_config_dict():
    """
    Estrutura consumida pelo script.js via window.__FORM_CONFIG__.
    """
    app = AppConfigOperacao.load()

    plan_details = _plan_details_by_grupo()

    cities_out = []
    for cidade in (
        CidadeOperacao.objects.filter(ativo=True)
        .select_related('grupo_planos')
        .order_by('ordem', 'nome_exibicao')
    ):
        ef = cidade.exigir_fotos_documentacao
        if ef is None:
            ef = app.exigir_fotos_documentacao

        cities_out.append(
            {
                'slug': cidade.slug,
                'label': cidade.nome_exibicao,
                'uf': cidade.uf_padrao,
                'planGroup': cidade.grupo_planos.slug,
                'excludedPlanCodes': _excluded_plan_codes_cidade(cidade.slug),
                'skipDocs': cidade.skip_etapa_documentacao,
                'termoOption': cidade.permite_opcao_termo,
                'alwaysShowPagamento': cidade.sempre_exibir_pagamento_instalacao,
                'instalacao': {
                    'comFidelGratis': cidade.instalacao_com_fidelidade_gratis,
                    'valorComFidel': float(cidade.instalacao_valor_com_fidel_reais),
                    'valorSemFidel': float(cidade.instalacao_valor_sem_fidel_reais),
                },
                'exigirFotos': ef,
                'vencimentoRules': _vencimento_rules(cidade),
            }
        )

    labels_map = {c['slug']: c['label'] for c in cities_out}

    return {
        'planDetails': plan_details,
        'cities': cities_out,
        'cityLabels': labels_map,
        'app': {
            'minInstallDaysAhead': app.dias_antecedencia_minima_instalacao,
            'textoAjudaDocumentos': app.texto_ajuda_documentos or '',
            'exigirFotosPadrao': app.exigir_fotos_documentacao,
        },
    }
