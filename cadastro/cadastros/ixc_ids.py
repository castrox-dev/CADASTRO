"""
Hub central de IDs do IXC usados pelo sistema (filiais, setores, cidades,
planos de venda, vencimentos, carteiras de cobrança, tipos de documento, etc.).

Modelo de prioridade adotado em todos os `get_*`:

    1. Painel admin (`/admin-dash/operacao/`) — quando o usuário preencher.
    2. DEFAULTS abaixo — valores reais de produção fornecidos pela operação.
    3. ''  (string vazia) — IXC entende como "não informado".

A ideia é: o admin pode atualizar qualquer ID daqui pelo painel sem
precisar mexer no código. Este arquivo é só o fallback documentado.

Os defaults abaixo são os IDs reais da Fibramar fornecidos em 2026-05-14:

    Filiais:
        2  → Maricá
        6  → Minas Gerais
        7  → Jaconé / Unamar / Saquarema / Araruama
        8  → Muqui / Mimoso do Sul
        9  → Vila Velha / Piúma
        11 → São Paulo

    Setores (id_setor por região):
        1  → Maricá
        22 → Santos Dumont (MG)
        23 → Jaconé / Unamar / Saquarema / Araruama
        24 → Muqui / Mimoso
        21 → Vila Velha / Piúma
        26 → São Paulo

    Tabela de vencimentos (id de cobrança no IXC):
        Filial 2 e 6 (Maricá / MG): conjunto «A» — dias 01/03/06/09/13/18/22/26
        Filial 7, 8, 9, 11        : conjunto «B» — dias 01/03/06/07/09/13/18

    Plano de venda (vd_contrato): depende da filial; cada filial tem o
    seu set de planos disponíveis.

    Tipo de documento (id_tipo_documento):
        - Fatura:    sempre 501
        - Opcional (ativação / taxa de instalação): varia por filial
            • 702 → Filial 02
            • 703 → Filial 07
            • 704 → Filial 06
            • 705 → Filial 08
            • 706 → Filial 11
            • 707 → Filial 09

    Carteira de cobrança: varia por cidade (todas no padrão «COM DESCONTO»).

    Produto da taxa de ativação (id_produto_ativ) = 146 (instalação R$ 100,00).
"""
from __future__ import annotations

from decimal import Decimal

# --------------------------------------------------------------------------- #
# DEFAULTS — IDs reais da Fibramar. Edite aqui apenas quando o IXC mudar     #
# (ou prefira o painel /admin-dash/operacao/ — tem prioridade sobre estes). #
# --------------------------------------------------------------------------- #

# Filiais por slug de cidade do front (script.js / OPERACAO).
FILIAIS = {
    'marica':         '2',
    'minas_gerais':   '6',
    'santos_dumont':  '6',  # alias
    'jacone':         '7',
    'unamar':         '7',
    'saquarema':      '7',
    'araruama':       '7',
    'cabo_frio':      '7',  # mesma região cobrada por F7
    'muqui':          '8',
    'mimoso':         '8',
    'vila_velha':     '9',
    'piuma':          '9',
    'anchieta':       '9',  # mesma região comercial da Piúma
    'sao_paulo':      '11',
}

# Setores (id_setor) por slug de cidade.
SETORES = {
    'marica':         '1',
    'minas_gerais':   '22',
    'santos_dumont':  '22',
    'jacone':         '23',
    'unamar':         '23',
    'saquarema':      '23',
    'araruama':       '23',
    'cabo_frio':      '23',
    'muqui':          '24',
    'mimoso':         '24',
    'vila_velha':     '21',
    'piuma':          '21',
    'anchieta':       '21',
    'sao_paulo':      '26',
}

# IDs reais de cidade no banco do IXC. Mantidos do mapeamento original.
CIDADES_IXC = {
    'marica':        '3214',
    'minas_gerais':  '2949',  # Santos Dumont
    'santos_dumont': '2949',
    'araruama':      '3176',
    'jacone':        '3176',
    'unamar':        '3176',
    'saquarema':     '3254',
    'cabo_frio':     '3185',
    'muqui':         '3147',
    'mimoso':        '3143',
    'sao_paulo':     '3828',
    # vila_velha / piuma / anchieta: preencha o id IXC real no painel.
}

# Plano de venda (vd_contrato) por **código do plano** dentro de cada **filial**.
# Estrutura: { '<filial>': { '<plano_codigo>': '<id_vd_contrato>' } }
PLANOS_POR_FILIAL = {
    # Filial 2 — Maricá
    '2': {
        'essencial': '174',  # 240 MEGA
        'rapido':    '175',  # 400 MEGA
        'ultra':     '124',  # 600 MEGA
        'prime':     '537',  # 700 MEGA
        '1giga':     '560',  # 1 GIGA
    },
    # Filial 6 — Minas Gerais (Santos Dumont)
    '6': {
        'essencial': '174',
        'rapido':    '175',
        'turbo':     '176',  # 500 MEGA
        'ultra':     '124',  # 600 MEGA
        '1giga':     '560',
    },
    # Filial 7 — Jaconé / Unamar / Saquarema / Araruama
    '7': {
        'essencial': '174',
        'rapido':    '175',
        'turbo':     '176',
        'ultra':     '124',
        '1giga':     '560',
    },
    # Filial 8 — Muqui / Mimoso (catálogo completo)
    '8': {
        'plano_100':  '220',
        'essencial':  '174',
        'plano_300':  '562',
        'rapido':     '175',
        'turbo':      '176',
        'ultra':      '124',
        'plano_700':  '563',
        '1giga':      '560',
    },
    # Filial 9 — Vila Velha / Piúma (mesmo set «padrão»)
    '9': {
        'essencial': '174',
        'rapido':    '175',
        'turbo':     '176',
        'ultra':     '124',
        '1giga':     '560',
    },
    # Filial 11 — São Paulo
    '11': {
        'essencial': '174',
        'rapido':    '175',
        'turbo':     '176',
        'ultra':     '124',
        '1giga':     '560',
    },
}

# Tipo de documento opcional (id_tipo_doc_ativ) — usado quando o cliente paga
# instalação (taxa de ativação). Varia por filial.
TIPO_DOC_ATIV_POR_FILIAL = {
    '2':  '702',
    '6':  '704',
    '7':  '703',
    '8':  '705',
    '9':  '707',
    '11': '706',
}

# Carteira de cobrança (id_carteira_cobranca) por cidade — todas no padrão
# «COM DESCONTO». Configurável no painel Operação por cidade.
CARTEIRAS_POR_CIDADE = {
    'marica':         '108',
    'minas_gerais':   '109',
    'santos_dumont':  '109',
    'cabo_frio':      '112',
    'jacone':         '112',
    'unamar':         '112',
    'araruama':       '112',
    'saquarema':      '110',
    'muqui':          '121',
    'mimoso':         '123',
    'vila_velha':     '116',
    'piuma':          '114',
    'anchieta':       '114',
    'sao_paulo':      '120',
}

# Tabela de vencimentos por filial.
# Conjunto «A» — Filial 2 e 6 (Maricá / MG).
# Conjunto «B» — Filial 7, 8, 9, 11.
VENCIMENTOS_POR_FILIAL = {
    # dia (string com 2 dígitos) → id da cobrança no IXC
    '2': {
        '01': '159',
        '03': '107',
        '06': '91',
        '09': '106',
        '13': '105',
        '18': '93',
        '22': '160',
        '26': '161',
    },
    '6': {
        '01': '159',
        '03': '107',
        '06': '91',
        '09': '106',
        '13': '105',
        '18': '93',
        '22': '160',
        '26': '161',
    },
    '7': {
        '01': '32',
        '03': '34',
        '06': '37',
        '07': '38',
        '09': '40',
        '13': '44',
        '18': '49',
    },
    '8': {
        '01': '32',
        '03': '34',
        '06': '37',
        '07': '38',
        '09': '40',
        '13': '44',
        '18': '49',
    },
    '9': {
        '01': '32',
        '03': '34',
        '06': '37',
        '07': '38',
        '09': '40',
        '13': '44',
        '18': '49',
    },
    '11': {
        '01': '32',
        '03': '34',
        '06': '37',
        '07': '38',
        '09': '40',
        '13': '44',
        '18': '49',
    },
}

# Globais (1 valor pra todo o sistema; também sobrescritíveis no painel).
GLOBAIS = {
    # Tipo do documento da fatura (id_tipo_documento) — sempre 501.
    'tipo_documento_fatura_id': '501',
    # Produto cobrado na taxa de ativação quando o cliente paga R$ 100,00 de
    # instalação (id_produto_ativ no contrato).
    'produto_instalacao_id':    '146',
    # Valor padrão da taxa de instalação cobrada (R$). Quando o cliente paga,
    # mandamos taxa_instalacao + id_produto_ativ + id_tipo_doc_ativ no contrato.
    'instalacao_valor_padrao_reais': Decimal('100.00'),
    # Fidelidade em meses — vai para o campo `fidelidade` do contrato.
    'fidelidade_meses_padrao':  12,
}


# --------------------------------------------------------------------------- #
# HELPERS — tudo sempre passa pelos `get_*`. Eles olham o painel admin       #
# primeiro (banco de dados) e caem nestes defaults se nada estiver salvo.    #
# --------------------------------------------------------------------------- #

def _slug(value):
    return (value or '').strip().lower().replace('-', '_').replace(' ', '_')


def _cidade_operacao(cidade_slug):
    """Busca a `CidadeOperacao` correspondente; cache local da função.
    Retorna None se não houver (ainda) cadastro no painel.
    """
    slug = _slug(cidade_slug)
    if not slug:
        return None
    try:
        from .operacao_models import CidadeOperacao
        return CidadeOperacao.objects.filter(slug=slug).first()
    except Exception:
        return None


def _app_config():
    try:
        from .operacao_models import AppConfigOperacao
        return AppConfigOperacao.load()
    except Exception:
        return None


def get_filial_id(cidade_slug):
    cidade = _cidade_operacao(cidade_slug)
    if cidade and (cidade.ixc_filial_id or '').strip():
        return cidade.ixc_filial_id.strip()
    return FILIAIS.get(_slug(cidade_slug), '')


def get_setor_id(cidade_slug):
    cidade = _cidade_operacao(cidade_slug)
    if cidade and (getattr(cidade, 'ixc_setor_id', '') or '').strip():
        return cidade.ixc_setor_id.strip()
    return SETORES.get(_slug(cidade_slug), '')


def get_cidade_ixc_id(cidade_slug):
    cidade = _cidade_operacao(cidade_slug)
    if cidade and (cidade.ixc_cidade_id or '').strip():
        return cidade.ixc_cidade_id.strip()
    return CIDADES_IXC.get(_slug(cidade_slug), '')


def get_carteira_cobranca_id(cidade_slug):
    cidade = _cidade_operacao(cidade_slug)
    if cidade and (getattr(cidade, 'ixc_carteira_cobranca_id', '') or '').strip():
        return cidade.ixc_carteira_cobranca_id.strip()
    return CARTEIRAS_POR_CIDADE.get(_slug(cidade_slug), '')


def get_tipo_doc_ativ_id(cidade_slug):
    """Tipo de documento opcional (ativação) — varia por filial. Cidade tem
    prioridade se o usuário tiver fixado um override no painel.
    """
    cidade = _cidade_operacao(cidade_slug)
    if cidade and (getattr(cidade, 'ixc_tipo_doc_ativ_id', '') or '').strip():
        return cidade.ixc_tipo_doc_ativ_id.strip()
    filial = get_filial_id(cidade_slug)
    return TIPO_DOC_ATIV_POR_FILIAL.get(filial, '')


def get_plano_venda_id(cidade_slug, plano_codigo):
    """ID do plano de venda (vd_contrato). Estratégia:
       1) PlanoDefinicao para a cidade (campo `ixc_plano_venda_id`).
       2) DEFAULTS PLANOS_POR_FILIAL[filial][plano_codigo].
       3) ''.
    """
    slug = _slug(cidade_slug)
    codigo = _slug(plano_codigo)
    try:
        from .operacao_models import CidadeOperacao, PlanoDefinicao
        cidade = CidadeOperacao.objects.select_related('grupo_planos').filter(slug=slug).first()
        if cidade:
            d = PlanoDefinicao.objects.filter(grupo=cidade.grupo_planos, codigo=codigo).first()
            if d and (d.ixc_plano_venda_id or '').strip():
                return d.ixc_plano_venda_id.strip()
    except Exception:
        pass
    filial = get_filial_id(cidade_slug) or ''
    return (PLANOS_POR_FILIAL.get(filial, {}).get(codigo) or '').strip()


def get_vencimento_id(cidade_slug, dia_str):
    """ID da cobrança/carência (id_carencia) pelo dia escolhido (`'01'`–`'31'`).
       1) `OpcaoVencimento` da cidade (cobre a faixa correspondente).
       2) DEFAULTS VENCIMENTOS_POR_FILIAL[filial][dia].
    """
    slug = _slug(cidade_slug)
    dia = (dia_str or '').strip().zfill(2)
    try:
        from .operacao_models import CidadeOperacao
        cidade = CidadeOperacao.objects.prefetch_related('faixas_vencimento__opcoes').filter(slug=slug).first()
        if cidade:
            for fx in cidade.faixas_vencimento.all():
                for op in fx.opcoes.all():
                    if (op.dia_str or '').strip().zfill(2) == dia and (op.ixc_id or '').strip().isdigit():
                        return op.ixc_id.strip()
    except Exception:
        pass
    filial = get_filial_id(cidade_slug) or ''
    return (VENCIMENTOS_POR_FILIAL.get(filial, {}).get(dia) or '').strip()


def get_tipo_documento_fatura_id():
    cfg = _app_config()
    if cfg and (getattr(cfg, 'ixc_tipo_documento_fatura_id', '') or '').strip():
        return cfg.ixc_tipo_documento_fatura_id.strip()
    return GLOBAIS['tipo_documento_fatura_id']


def get_produto_instalacao_id():
    cfg = _app_config()
    if cfg and (getattr(cfg, 'ixc_produto_instalacao_id', '') or '').strip():
        return cfg.ixc_produto_instalacao_id.strip()
    return GLOBAIS['produto_instalacao_id']


def get_fidelidade_meses(cadastro_fidelidade_bool):
    """`12` se o cliente marcou fidelidade na ficha; `''` (vazio) caso contrário.
    O IXC entende `''` como «sem fidelidade».
    """
    if not cadastro_fidelidade_bool:
        return ''
    cfg = _app_config()
    if cfg and getattr(cfg, 'ixc_fidelidade_meses', None):
        return str(int(cfg.ixc_fidelidade_meses))
    return str(int(GLOBAIS['fidelidade_meses_padrao']))


def get_instalacao_taxa_reais(cadastro):
    """Valor da taxa de instalação em R$ aplicado a este cadastro.

    Estratégia:
      1) Cidade do cadastro com `pagamento_instalacao != 'gratis'`:
         usa o valor configurado (`instalacao_valor_com_fidel_reais` se o
         cliente marcou fidelidade, senão `instalacao_valor_sem_fidel_reais`).
      2) Pagamento `gratis` → 0.
      3) Fallback global `instalacao_valor_padrao_reais` (R$ 100,00).
    """
    pagamento = (getattr(cadastro, 'pagamento_instalacao', '') or '').strip().lower()
    if pagamento == 'gratis':
        return Decimal('0.00')
    cidade = _cidade_operacao(getattr(cadastro, 'cidade', ''))
    if cidade:
        if getattr(cadastro, 'fidelidade', False):
            val = cidade.instalacao_valor_com_fidel_reais or Decimal('0')
        else:
            val = cidade.instalacao_valor_sem_fidel_reais or Decimal('0')
        if val and val > 0:
            return val
    return GLOBAIS['instalacao_valor_padrao_reais']


# Exporta visão consolidada (útil para painel/admin debug).
__all__ = [
    'FILIAIS',
    'SETORES',
    'CIDADES_IXC',
    'PLANOS_POR_FILIAL',
    'TIPO_DOC_ATIV_POR_FILIAL',
    'CARTEIRAS_POR_CIDADE',
    'VENCIMENTOS_POR_FILIAL',
    'GLOBAIS',
    'get_filial_id',
    'get_setor_id',
    'get_cidade_ixc_id',
    'get_carteira_cobranca_id',
    'get_tipo_doc_ativ_id',
    'get_plano_venda_id',
    'get_vencimento_id',
    'get_tipo_documento_fatura_id',
    'get_produto_instalacao_id',
    'get_fidelidade_meses',
    'get_instalacao_taxa_reais',
]
