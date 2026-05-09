# Atualiza texto do opcional «combo» para deixar claro que as opções são independentes.

from django.db import migrations

OLD = (
    'Deseja alugar roteador Wi-Fi por R$ 10,00/mês ou repetidor Mesh por R$ 29,99/mês?'
)
NEW = (
    'Aluguel opcional — pode marcar um, os dois ou nenhum: '
    'roteador Wi-Fi R$ 10,00/mês; repetidor Mesh R$ 29,99/mês.'
)


def forwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    PlanoDefinicao.objects.filter(texto_opcional=OLD).update(texto_opcional=NEW)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0018_cadastro_aluguel_roteador_mesh'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
