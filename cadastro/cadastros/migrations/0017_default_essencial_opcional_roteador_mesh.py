# Essencial (Maricá / grupo default): opcional único menciona roteador em aluguel E repetidor Mesh.

from django.db import migrations

TEXTO_COMBO = (
    'Deseja alugar roteador Wi-Fi por R$ 10,00/mês ou repetidor Mesh por R$ 29,99/mês?'
)


def forwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    PlanoDefinicao.objects.filter(grupo__slug='default', codigo='essencial').update(
        texto_opcional=TEXTO_COMBO,
    )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0016_muqui_mimoso_planos_textos'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
