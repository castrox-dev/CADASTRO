"""
Seed: aplica os IDs reais de produção fornecidos pela Fibramar (2026-05-14).

Atualiza apenas registros já existentes — não cria cidades/planos novos.
Os defaults completos ficam em ``cadastros/ixc_ids.py`` (também consultado
em runtime caso o registro do painel esteja vazio).

Para reaplicar em ambiente novo: rode ``python manage.py migrate cadastros``.
A migration é idempotente: pode rodar quantas vezes precisar.
"""
from django.db import migrations


# Espelha cadastros/ixc_ids.py (FILIAIS, SETORES, CARTEIRAS, TIPO_DOC_ATIV).
FILIAIS = {
    'marica': '2', 'minas_gerais': '6', 'santos_dumont': '6',
    'jacone': '7', 'unamar': '7', 'saquarema': '7', 'araruama': '7', 'cabo_frio': '7',
    'muqui': '8', 'mimoso': '8',
    'vila_velha': '9', 'piuma': '9', 'anchieta': '9',
    'sao_paulo': '11',
}

SETORES = {
    'marica': '1', 'minas_gerais': '22', 'santos_dumont': '22',
    'jacone': '23', 'unamar': '23', 'saquarema': '23', 'araruama': '23', 'cabo_frio': '23',
    'muqui': '24', 'mimoso': '24',
    'vila_velha': '21', 'piuma': '21', 'anchieta': '21',
    'sao_paulo': '26',
}

CIDADES_IXC = {
    'marica': '3214', 'minas_gerais': '2949', 'santos_dumont': '2949',
    'araruama': '3176', 'jacone': '3176', 'unamar': '3176',
    'saquarema': '3254', 'cabo_frio': '3185',
    'muqui': '3147', 'mimoso': '3143',
    'sao_paulo': '3828',
}

CARTEIRAS = {
    'marica': '108', 'minas_gerais': '109', 'santos_dumont': '109',
    'cabo_frio': '112', 'jacone': '112', 'unamar': '112', 'araruama': '112',
    'saquarema': '110', 'muqui': '121', 'mimoso': '123',
    'vila_velha': '116', 'piuma': '114', 'anchieta': '114',
    'sao_paulo': '120',
}

TIPO_DOC_ATIV_POR_FILIAL = {
    '2': '702', '6': '704', '7': '703',
    '8': '705', '9': '707', '11': '706',
}

# Plano de venda: PlanoDefinicao.codigo -> id_vd_contrato por filial.
# Aplicamos por grupo_planos.slug (as cidades estão ligadas a um grupo).
PLANOS_POR_FILIAL = {
    '2': {'essencial': '174', 'rapido': '175', 'ultra': '124', 'prime': '537', '1giga': '560'},
    '6': {'essencial': '174', 'rapido': '175', 'turbo': '176', 'ultra': '124', '1giga': '560'},
    '7': {'essencial': '174', 'rapido': '175', 'turbo': '176', 'ultra': '124', '1giga': '560'},
    '8': {
        'plano_100': '220', 'essencial': '174', 'plano_300': '562',
        'rapido': '175', 'turbo': '176', 'ultra': '124',
        'plano_700': '563', '1giga': '560',
    },
    '9': {'essencial': '174', 'rapido': '175', 'turbo': '176', 'ultra': '124', '1giga': '560'},
    '11': {'essencial': '174', 'rapido': '175', 'turbo': '176', 'ultra': '124', '1giga': '560'},
}

# Vencimentos: por filial, dia('01'..) -> id_carencia. Sobrescreve `OpcaoVencimento.ixc_id`.
VENCIMENTOS_POR_FILIAL = {
    '2':  {'01': '159', '03': '107', '06': '91', '09': '106', '13': '105', '18': '93', '22': '160', '26': '161'},
    '6':  {'01': '159', '03': '107', '06': '91', '09': '106', '13': '105', '18': '93', '22': '160', '26': '161'},
    '7':  {'01': '32', '03': '34', '06': '37', '07': '38', '09': '40', '13': '44', '18': '49'},
    '8':  {'01': '32', '03': '34', '06': '37', '07': '38', '09': '40', '13': '44', '18': '49'},
    '9':  {'01': '32', '03': '34', '06': '37', '07': '38', '09': '40', '13': '44', '18': '49'},
    '11': {'01': '32', '03': '34', '06': '37', '07': '38', '09': '40', '13': '44', '18': '49'},
}


def apply_ids(apps, schema_editor):
    CidadeOperacao = apps.get_model('cadastros', 'CidadeOperacao')
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    OpcaoVencimento = apps.get_model('cadastros', 'OpcaoVencimento')
    AppConfigOperacao = apps.get_model('cadastros', 'AppConfigOperacao')

    # --- Cidades (filial / setor / cidade IXC / carteira / tipo doc ativação)
    for cidade in CidadeOperacao.objects.all():
        slug = (cidade.slug or '').strip()
        if not slug:
            continue
        filial_id = FILIAIS.get(slug, '')
        if filial_id:
            cidade.ixc_filial_id = filial_id
        if SETORES.get(slug):
            cidade.ixc_setor_id = SETORES[slug]
        if CIDADES_IXC.get(slug):
            cidade.ixc_cidade_id = CIDADES_IXC[slug]
        if CARTEIRAS.get(slug):
            cidade.ixc_carteira_cobranca_id = CARTEIRAS[slug]
        if filial_id and TIPO_DOC_ATIV_POR_FILIAL.get(filial_id):
            cidade.ixc_tipo_doc_ativ_id = TIPO_DOC_ATIV_POR_FILIAL[filial_id]
        cidade.save(update_fields=[
            'ixc_filial_id', 'ixc_setor_id', 'ixc_cidade_id',
            'ixc_carteira_cobranca_id', 'ixc_tipo_doc_ativ_id',
        ])

    # --- Planos de venda (por filial das cidades vinculadas ao grupo do plano)
    for plano in PlanoDefinicao.objects.select_related('grupo').all():
        codigo = (plano.codigo or '').strip()
        if not codigo:
            continue
        # Filial do plano = filial da primeira cidade do grupo (Operação).
        cidade = CidadeOperacao.objects.filter(grupo_planos=plano.grupo).first()
        if not cidade:
            continue
        filial = (cidade.ixc_filial_id or '').strip() or FILIAIS.get(cidade.slug or '', '')
        if not filial:
            continue
        novo_id = PLANOS_POR_FILIAL.get(filial, {}).get(codigo, '')
        if novo_id:
            plano.ixc_plano_venda_id = novo_id
            plano.save(update_fields=['ixc_plano_venda_id'])

    # --- Opções de vencimento (id da cobrança no IXC) por filial da cidade
    for op in OpcaoVencimento.objects.select_related('faixa__cidade').all():
        cidade = op.faixa.cidade if op.faixa_id else None
        if not cidade:
            continue
        filial = (cidade.ixc_filial_id or '').strip() or FILIAIS.get(cidade.slug or '', '')
        if not filial:
            continue
        dia = (op.dia_str or '').strip().zfill(2)
        novo_id = VENCIMENTOS_POR_FILIAL.get(filial, {}).get(dia, '')
        if novo_id:
            op.ixc_id = novo_id
            op.save(update_fields=['ixc_id'])

    # --- AppConfig: garante defaults globais (501/146/12).
    cfg, _ = AppConfigOperacao.objects.get_or_create(pk=1)
    changed = False
    if not (cfg.ixc_tipo_documento_fatura_id or '').strip():
        cfg.ixc_tipo_documento_fatura_id = '501'
        changed = True
    if not (cfg.ixc_produto_instalacao_id or '').strip():
        cfg.ixc_produto_instalacao_id = '146'
        changed = True
    if not cfg.ixc_fidelidade_meses:
        cfg.ixc_fidelidade_meses = 12
        changed = True
    if changed:
        cfg.save()


def revert_ids(apps, schema_editor):
    """No-op: não revertemos os IDs aplicados (segurança de produção)."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0043_ids_ixc_operacao'),
    ]

    operations = [
        migrations.RunPython(apply_ids, revert_ids),
    ]
