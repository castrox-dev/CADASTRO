# Textos de título e descrição (HTML) — grupos Muqui/Piúma e Mimoso.

from django.db import migrations


def forwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')

    MUQUI = {
        'essencial': (
            '📱 Plano Essencial – 100 MEGA',
            '<strong>R$ 59,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 79,99/mês</strong> (após vencimento)<br><br>'
            '- Instalação Grátis<br><br>'
            '- <strong>Este plano não inclui roteador Wi-Fi</strong> (você pode usar o seu próprio ou alugar por R$ 10,00/mês)<br><br>'
            '- Instalação em até 48h<br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        'rapido': (
            '🚀 Plano Rápido – 300 Mega',
            '<strong>300 Mega • R$ 89,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 109,99/mês</strong> (após vencimento)<br><br>'
            '- Suporte Especializado<br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi 5Ghz incluso<br><br>'
            '💨 <strong>Velocidade na medida certa para toda a família navegar, assistir e conectar.</strong><br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        'turbo': (
            '⚡️ Plano Turbo – 500 Mega',
            '<strong>500 Mega • R$ 99,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 119,99/mês</strong> (após vencimento)<br><br>'
            '- Suporte Especializado<br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi 5Ghz incluso<br><br>'
            '🚀 <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        '1giga': (
            '🚀 Plano 1 GIGA Fibramar',
            '<strong>1 GIGA • R$ 149,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 169,99/mês</strong> (após vencimento)<br><br>'
            '- Wi-Fi 6 incluso<br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br><br>'
            '⚡️ <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>'
            '🔗 Opcional: Repetidor Mesh por apenas R$ 29,99/mês<br><br>'
            '- Possui fidelidade de 12 meses',
        ),
    }

    MIMOSO = {
        'essencial': (
            '📱 Plano Essencial – 240 MEGA',
            '<strong>R$ 59,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 79,99/mês</strong> (após vencimento)<br><br>'
            '- Instalação Grátis<br><br>'
            '- <strong>Este plano não inclui roteador Wi-Fi</strong> (você pode usar o seu próprio ou alugar por R$ 10,00/mês)<br><br>'
            '- Instalação em até 48h<br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        'plano_300': (
            '⚡️ Plano 300 Mega',
            '<strong>300 Mega • R$ 69,99/mês</strong><br><br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi incluso<br><br>'
            '📄 Possui fidelidade de 12 meses<br><br>'
            '💨 <strong>Perfeito para navegar, assistir e usar redes sociais com estabilidade.</strong>',
        ),
        'rapido': (
            '🚀 Plano Rápido – 400 Mega',
            '<strong>400 Mega • R$ 79,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 99,99/mês</strong> (após vencimento)<br><br>'
            '- Suporte Especializado<br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi 5Ghz incluso<br><br>'
            '💨 <strong>Velocidade na medida certa para toda a família navegar, assistir e conectar.</strong><br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        'turbo': (
            '⚡️ Plano Turbo – 500 Mega',
            '<strong>500 Mega • R$ 99,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 119,99/mês</strong> (após vencimento)<br><br>'
            '- Suporte Especializado<br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi 5Ghz incluso<br><br>'
            '🚀 <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        'ultra': (
            '🔥 Plano Ultra + Watch TV, Qualifica e Mediquo – 600 Mega',
            '<strong>600 Mega • R$ 119,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 139,99/mês</strong> (após vencimento)<br><br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi 5Ghz incluso<br><br>'
            '🎁 <strong>Benefícios Exclusivos:</strong><br><br>'
            '- 📺 <strong>Watch TV</strong>: filmes, séries e canais infantis<br>'
            '- 📽️ Paramount+<br>'
            '- 🎓 <strong>Qualifica</strong>: +220 cursos on-line com certificado reconhecido pela ABED e Carteirinha do Estudante para meia-entrada<br>'
            '- 🩺 <strong>Mediquo</strong>: consultas médicas ilimitadas 24 h<br>'
            '- 🔰 McAfee antivírus<br><br>'
            '- Possui fidelidade de 12 meses',
        ),
        'plano_700': (
            '🚀 Plano 700 Mega',
            '<strong>700 Mega • R$ 89,99/mês</strong><br><br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br>'
            '- 😍 Super Wi-Fi incluso<br>'
            '- 🎓 Qualifica App (Aplicativo de cursos e clube de vantagens)<br><br>'
            '📄 Possui fidelidade de 12 meses<br><br>'
            '✨ <strong>Mais velocidade e benefícios para quem quer estudar, trabalhar e aproveitar o máximo da internet.</strong>',
        ),
        '1giga': (
            '🚀 Plano 1 GIGA Fibramar',
            '<strong>1 GIGA • R$ 149,99/mês</strong> (pagando até o vencimento)<br><br>'
            '<strong>R$ 169,99/mês</strong> (após vencimento)<br><br>'
            '- Wi-Fi 6 incluso<br>'
            '- 100% Fibra Óptica<br>'
            '- 🤩 Instalação Grátis<br><br>'
            '⚡️ <strong>Ideal para gamers, streamers e multitarefas que não podem ficar sem velocidade.</strong><br><br>'
            '🔗 Opcional: Repetidor Mesh por apenas R$ 29,99/mês<br><br>'
            '- Possui fidelidade de 12 meses',
        ),
    }

    for codigo, (titulo, desc) in MUQUI.items():
        PlanoDefinicao.objects.filter(grupo__slug='muqui_piuma', codigo=codigo).update(
            titulo=titulo,
            descricao_html=desc,
        )

    for codigo, (titulo, desc) in MIMOSO.items():
        PlanoDefinicao.objects.filter(grupo__slug='mimoso', codigo=codigo).update(
            titulo=titulo,
            descricao_html=desc,
        )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0015_texto_opcional_marica_mesh_muqui_mimoso'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
