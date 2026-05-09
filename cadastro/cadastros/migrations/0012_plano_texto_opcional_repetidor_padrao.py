# Unifica texto do opcional (repetidor Mesh) para todos os planos quando já havia valor divergente.

from django.db import migrations

TEXTO = 'Deseja alugar repetidor Mesh por R$ 29,99/mês?'


def forwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    PlanoDefinicao.objects.all().update(texto_opcional=TEXTO)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0011_seed_operacao_defaults'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
