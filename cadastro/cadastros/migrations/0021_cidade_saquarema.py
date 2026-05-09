# Cidade Saquarema - RJ (filial 7 / IXC), lista da ficha e regras de vencimento padrão.

from django.db import migrations


def forwards(apps, schema_editor):
    PlanoGrupo = apps.get_model('cadastros', 'PlanoGrupo')
    CidadeOperacao = apps.get_model('cadastros', 'CidadeOperacao')
    FaixaVencimento = apps.get_model('cadastros', 'FaixaVencimento')
    OpcaoVencimento = apps.get_model('cadastros', 'OpcaoVencimento')

    g_default = PlanoGrupo.objects.filter(slug='default').first()
    if not g_default:
        return

    cidade, created = CidadeOperacao.objects.get_or_create(
        slug='saquarema',
        defaults={
            'nome_exibicao': 'Saquarema - RJ',
            'uf_padrao': 'RJ',
            'grupo_planos': g_default,
            'ordem': 65,
            'ativo': True,
            'skip_etapa_documentacao': False,
            'permite_opcao_termo': True,
            'sempre_exibir_pagamento_instalacao': False,
            'instalacao_com_fidelidade_gratis': True,
            'instalacao_valor_com_fidel_reais': 0,
            'instalacao_valor_sem_fidel_reais': 360,
            'ixc_filial_id': '7',
            'ixc_cidade_id': '3254',
            'exigir_fotos_documentacao': None,
        },
    )

    if not FaixaVencimento.objects.filter(cidade=cidade).exists():
        fx = FaixaVencimento.objects.create(cidade=cidade, dia_inicio=1, dia_fim=31, ordem=0)
        padrao_dias = ['01', '03', '06', '07', '09', '13', '18']
        for i, d in enumerate(padrao_dias):
            OpcaoVencimento.objects.create(faixa=fx, dia_str=d, ixc_id='IXC', ordem=i)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0020_plano_essencial_texto_roteador_padrao'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
