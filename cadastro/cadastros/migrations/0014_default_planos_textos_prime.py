# Textos de planos (grupo default), novo plano Prime 700 MEGA e ordem da ficha.

from django.db import migrations


DESC_ESSENCIAL = (
    'R$ 59,99/mês (pagando até o vencimento)<br>'
    'R$ 79,99/mês (após vencimento)<br><br>'
    'Este plano não inclui roteador Wi-Fi (você pode usar o seu próprio ou alugar por R$ 10,00/mês)<br><br>'
    'Instalação em até 48h<br>'
    'Permanência mínima de 12 meses'
)

DESC_RAPIDO = (
    'R$ 79,99/mês* (pagando até o vencimento)<br>'
    'R$ 99,99/mês* (após vencimento)<br><br>'
    'Suporte Especializado<br>'
    '100% Fibra Óptica<br>'
    '😍 Super Wi-Fi 5Ghz incluso<br><br>'
    '💨Velocidade na medida certa para toda a família navegar, assistir e conectar.<br><br>'
    'Permanência mínima de 12 meses'
)

DESC_ULTRA = (
    'R$ 119,99/mês* (pagando até o vencimento)<br>'
    'R$ 139,99/mês* (após vencimento)<br>'
    '😍 Super Wi-Fi 5Ghz incluso<br><br>'
    '🎁 Benefícios Exclusivos:<br><br>'
    '📺 Watch TV: filmes, séries e canais infantis<br>'
    '📽️ Paramount<br>'
    '🎓 Qualifica: +220 cursos on-line com certificado reconhecido pela ABED e Carteirinha do Estudante para meia-entrada<br>'
    '🩺 Mediquo: consultas médicas ilimitadas 24 h<br>'
    '🔰 McAfee antivírus<br><br>'
    'Permanência mínima de 12 meses'
)

DESC_PRIME = (
    '<strong>R$ 99,99/mês</strong> (pagando até o vencimento)<br><br>'
    '<strong>R$ 119,99/mês</strong> (após vencimento)<br><br>'
    '- Suporte Especializado<br><br>'
    '- Cursos Qualifica + Clube de vantagens<br><br>'
    '- 100% Fibra Óptica<br><br>'
    '- 😍 Super Wi-Fi 5Ghz incluso<br><br>'
    '🚀 <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>'
    '- Possui fidelidade de 12 meses'
)

DESC_1GIGA = (
    '📡 Velocidade: 1 GIGA<br>'
    '💰 Valor: R$ 169,99<br>'
    '➡️ Promoção: pagando até o vencimento, sai por apenas R$ 149,99<br>'
    '📶 Wi-Fi 6 incluso 🚀<br>'
    '📄 Contrato de fidelidade: 12 meses<br>'
    '🔗 Opcional: Repetidor Mesh por apenas R$ 29,99 mensais'
)


def forwards(apps, schema_editor):
    PlanoGrupo = apps.get_model('cadastros', 'PlanoGrupo')
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')

    g = PlanoGrupo.objects.filter(slug='default').first()
    if not g:
        return

    specs = [
        (
            'essencial',
            '📱 Plano Essencial – 240 MEGA',
            DESC_ESSENCIAL,
            'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?',
            0,
            '174',
        ),
        (
            'rapido',
            '🚀 Plano Rápido - 400 Mega',
            DESC_RAPIDO,
            '',
            1,
            '175',
        ),
        (
            'turbo',
            'Plano Turbo - 500 Mega',
            'R$ 99,99/mês* (até o vencimento)<br>R$ 119,99/mês* (após vencimento)<br>Super Wi-Fi 5Ghz incluso',
            '',
            2,
            '176',
        ),
        (
            'ultra',
            '🔥 Plano Ultra + Watch TV, Qualifica e Mediquo - 600 Mega',
            DESC_ULTRA,
            '',
            3,
            '124',
        ),
        (
            '1giga',
            'Plano Novo – 1 GIGA Fibramar Internet ✨',
            DESC_1GIGA,
            '',
            5,
            '560',
        ),
    ]

    for codigo, titulo, desc, opt, ordem, ixc in specs:
        PlanoDefinicao.objects.filter(grupo=g, codigo=codigo).update(
            titulo=titulo,
            descricao_html=desc,
            texto_opcional=opt or '',
            ordem=ordem,
            ixc_plano_venda_id=ixc,
        )

    PlanoDefinicao.objects.update_or_create(
        grupo=g,
        codigo='prime',
        defaults={
            'titulo': '⚡️ Plano Prime – 700 MEGA',
            'descricao_html': DESC_PRIME,
            'texto_opcional': '',
            'ordem': 4,
            'ixc_plano_venda_id': '',
        },
    )


def backwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    PlanoDefinicao.objects.filter(codigo='prime').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0013_alter_planodefinicao_texto_opcional'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
