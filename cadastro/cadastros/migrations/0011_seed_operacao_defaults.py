# Dados iniciais equivalentes ao comportamento anterior da ficha (JS estático).

from django.db import migrations


def seed_forward(apps, schema_editor):
    AppConfigOperacao = apps.get_model('cadastros', 'AppConfigOperacao')
    PlanoGrupo = apps.get_model('cadastros', 'PlanoGrupo')
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    CidadeOperacao = apps.get_model('cadastros', 'CidadeOperacao')
    FaixaVencimento = apps.get_model('cadastros', 'FaixaVencimento')
    OpcaoVencimento = apps.get_model('cadastros', 'OpcaoVencimento')

    AppConfigOperacao.objects.get_or_create(
        pk=1,
        defaults={
            'dias_antecedencia_minima_instalacao': 1,
            'exigir_fotos_documentacao': True,
        },
    )

    g_default = PlanoGrupo.objects.create(slug='default', nome='Padrão (Maricá e similares)')
    g_muqui = PlanoGrupo.objects.create(slug='muqui_piuma', nome='Muqui / Piúma')
    g_mimoso = PlanoGrupo.objects.create(slug='mimoso', nome='Mimoso do Sul')

    planos_default = [
        ('essencial', 'Plano Essencial – 240 MEGA',
         'R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Contrato 12 meses',
         'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?', 0, '174'),
        ('rapido', 'Plano Rápido - 400 Mega',
         'R$ 79,99/mês* (até o vencimento)<br>R$ 99,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso',
         '', 1, '175'),
        ('turbo', 'Plano Turbo - 500 Mega',
         'R$ 99,99/mês* (até o vencimento)<br>R$ 119,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso',
         '', 2, '176'),
        ('ultra', 'Plano Ultra + Benefícios - 600 Mega',
         'R$ 119,99/mês* (até o vencimento)<br>R$ 139,99/mês* (após vencimento)<br>Watch TV, Paramount, Qualifica, Mediquo e McAfee inclusos',
         '', 3, '124'),
        ('1giga', 'Plano Novo – 1 GIGA',
         'R$ 149,99 (até o vencimento)<br>R$ 169,99 (valor normal)<br>Wi-Fi 6 incluso 🚀',
         'Deseja Repetidor Mesh por apenas R$ 29,99 mensais?', 4, '560'),
    ]
    for codigo, titulo, desc, opt, ordem, ixc in planos_default:
        PlanoDefinicao.objects.create(
            grupo=g_default, codigo=codigo, titulo=titulo, descricao_html=desc,
            texto_opcional=opt, ordem=ordem, ixc_plano_venda_id=ixc,
        )

    planos_muqui = [
        ('essencial', 'Plano Essencial – 100 MEGA',
         'R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Sem roteador incluso',
         'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?', 0, '174'),
        ('rapido', 'Plano Rápido – 300 MEGA',
         'R$ 89,99/mês (até o vencimento)<br>R$ 109,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso',
         '', 1, '175'),
        ('turbo', 'Plano Turbo – 500 MEGA',
         'R$ 99,99/mês (até o vencimento)<br>R$ 119,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso',
         '', 2, '176'),
        ('1giga', 'Plano 1 GIGA Fibramar',
         'R$ 149,99/mês (até o vencimento)<br>R$ 169,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Wi-Fi 6 incluso',
         'Deseja Repetidor Mesh por apenas R$ 29,99/mês?', 3, '560'),
    ]
    for codigo, titulo, desc, opt, ordem, ixc in planos_muqui:
        PlanoDefinicao.objects.create(
            grupo=g_muqui, codigo=codigo, titulo=titulo, descricao_html=desc,
            texto_opcional=opt, ordem=ordem, ixc_plano_venda_id=ixc,
        )

    planos_mimoso = [
        ('essencial', 'Plano Essencial – 240 MEGA',
         'R$ 59,99/mês (até o vencimento)<br>R$ 79,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Sem roteador incluso',
         'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?', 0, '174'),
        ('plano_300', 'Plano 300 Mega',
         'R$ 69,99/mês<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi incluso',
         '', 1, '174'),
        ('rapido', 'Plano Rápido – 400 MEGA',
         'R$ 79,99/mês (até o vencimento)<br>R$ 99,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso',
         '', 2, '175'),
        ('turbo', 'Plano Turbo – 500 MEGA',
         'R$ 99,99/mês (até o vencimento)<br>R$ 119,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi 5Ghz incluso',
         '', 3, '176'),
        ('ultra', 'Plano Ultra – 600 MEGA',
         'R$ 119,99/mês (até o vencimento)<br>R$ 139,99/mês (após vencimento)<br>Watch TV, Paramount+, Qualifica, Mediquo e McAfee inclusos',
         '', 4, '124'),
        ('plano_700', 'Plano 700 Mega',
         'R$ 89,99/mês<br>Instalação Grátis (Fidelidade)<br>Super Wi-Fi + Qualifica App incluso',
         '', 5, '176'),
        ('1giga', 'Plano 1 GIGA Fibramar',
         'R$ 149,99/mês (até o vencimento)<br>R$ 169,99/mês (após vencimento)<br>Instalação Grátis (Fidelidade)<br>Wi-Fi 6 incluso',
         'Deseja Repetidor Mesh por apenas R$ 29,99/mês?', 6, '560'),
    ]
    for codigo, titulo, desc, opt, ordem, ixc in planos_mimoso:
        PlanoDefinicao.objects.create(
            grupo=g_mimoso, codigo=codigo, titulo=titulo, descricao_html=desc,
            texto_opcional=opt, ordem=ordem, ixc_plano_venda_id=ixc,
        )

    def mk_cidade(slug, nome, uf, grupo, ordem, skip, termo, sempre_pag, com_gratis, vcom, vsem, filial, cidade_ixc):
        return CidadeOperacao.objects.create(
            slug=slug,
            nome_exibicao=nome,
            uf_padrao=uf,
            grupo_planos=grupo,
            ordem=ordem,
            skip_etapa_documentacao=skip,
            permite_opcao_termo=termo,
            sempre_exibir_pagamento_instalacao=sempre_pag,
            instalacao_com_fidelidade_gratis=com_gratis,
            instalacao_valor_com_fidel_reais=vcom,
            instalacao_valor_sem_fidel_reais=vsem,
            ixc_filial_id=filial or '',
            ixc_cidade_id=cidade_ixc or '',
            exigir_fotos_documentacao=None,
        )

    c_marica = mk_cidade(
        'marica', 'Maricá - RJ', 'RJ', g_default, 10,
        True, False, True, False, 100, 460, '2', '3214',
    )
    c_minas = mk_cidade(
        'minas_gerais', 'Minas Gerais - MG', 'MG', g_default, 20,
        True, False, False, True, 0, 360, '6', '2949',
    )
    mk_cidade('muqui', 'Muqui - ES', 'ES', g_muqui, 30, False, False, False, True, 0, 360, '8', '3147')
    mk_cidade('piuma', 'Piúma - ES', 'ES', g_muqui, 40, False, False, False, True, 0, 360, '9', '3147')
    mk_cidade('mimoso', 'Mimoso do Sul - ES', 'ES', g_mimoso, 50, False, False, False, True, 0, 360, '8', '3143')
    mk_cidade('cabo_frio', 'Cabo Frio - RJ', 'RJ', g_default, 60, False, True, False, True, 0, 360, '7', '3185')
    mk_cidade('unamar', 'Unamar - RJ', 'RJ', g_default, 70, False, True, False, True, 0, 360, '7', '3176')
    mk_cidade('sao_paulo', 'São Paulo - SP', 'SP', g_default, 80, False, True, False, True, 0, 360, '11', '3828')
    mk_cidade('outra', 'Outra cidade', 'RJ', g_default, 90, False, False, False, True, 0, 360, '', '')

    def faixa_marica_minas(cidade):
        f1 = FaixaVencimento.objects.create(cidade=cidade, dia_inicio=2, dia_fim=10, ordem=0)
        for d, ixc in [('03', '107'), ('06', '91'), ('09', '106')]:
            OpcaoVencimento.objects.create(faixa=f1, dia_str=d, ixc_id=ixc, ordem=0)
        f2 = FaixaVencimento.objects.create(cidade=cidade, dia_inicio=11, dia_fim=20, ordem=1)
        for d, ixc in [('13', '105'), ('18', '93')]:
            OpcaoVencimento.objects.create(faixa=f2, dia_str=d, ixc_id=ixc, ordem=0)
        f3 = FaixaVencimento.objects.create(cidade=cidade, dia_inicio=21, dia_fim=31, ordem=2)
        for d, ixc in [('22', '160'), ('26', '161'), ('01', '159')]:
            OpcaoVencimento.objects.create(faixa=f3, dia_str=d, ixc_id=ixc, ordem=0)
        f4 = FaixaVencimento.objects.create(cidade=cidade, dia_inicio=1, dia_fim=1, ordem=3)
        for d, ixc in [('22', '160'), ('26', '161'), ('01', '159')]:
            OpcaoVencimento.objects.create(faixa=f4, dia_str=d, ixc_id=ixc, ordem=0)

    faixa_marica_minas(c_marica)
    faixa_marica_minas(c_minas)

    padrao_dias = ['01', '03', '06', '07', '09', '13', '18']
    for cid in CidadeOperacao.objects.exclude(pk__in=[c_marica.pk, c_minas.pk]):
        fx = FaixaVencimento.objects.create(cidade=cid, dia_inicio=1, dia_fim=31, ordem=0)
        for i, d in enumerate(padrao_dias):
            OpcaoVencimento.objects.create(faixa=fx, dia_str=d, ixc_id='IXC', ordem=i)


def seed_reverse(apps, schema_editor):
    OpcaoVencimento = apps.get_model('cadastros', 'OpcaoVencimento')
    FaixaVencimento = apps.get_model('cadastros', 'FaixaVencimento')
    CidadeOperacao = apps.get_model('cadastros', 'CidadeOperacao')
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    PlanoGrupo = apps.get_model('cadastros', 'PlanoGrupo')
    AppConfigOperacao = apps.get_model('cadastros', 'AppConfigOperacao')

    OpcaoVencimento.objects.all().delete()
    FaixaVencimento.objects.all().delete()
    CidadeOperacao.objects.all().delete()
    PlanoDefinicao.objects.all().delete()
    PlanoGrupo.objects.all().delete()
    AppConfigOperacao.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0010_operacao_store'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_reverse),
    ]
