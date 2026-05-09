# Substitui cadastro.opcional por aluguel_roteador_wifi + aluguel_repetidor_mesh (marcação independente).

from django.db import migrations, models
from django.db.models import F


def forwards_copy_opcional(apps, schema_editor):
    Cadastro = apps.get_model('cadastros', 'Cadastro')
    HistoricalCadastro = apps.get_model('cadastros', 'HistoricalCadastro')
    Cadastro.objects.all().update(aluguel_repetidor_mesh=F('opcional'))
    HistoricalCadastro.objects.all().update(aluguel_repetidor_mesh=F('opcional'))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0017_default_essencial_opcional_roteador_mesh'),
    ]

    operations = [
        migrations.AddField(
            model_name='cadastro',
            name='aluguel_roteador_wifi',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='cadastro',
            name='aluguel_repetidor_mesh',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='historicalcadastro',
            name='aluguel_roteador_wifi',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='historicalcadastro',
            name='aluguel_repetidor_mesh',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(forwards_copy_opcional, noop_reverse),
        migrations.RemoveField(
            model_name='cadastro',
            name='opcional',
        ),
        migrations.RemoveField(
            model_name='historicalcadastro',
            name='opcional',
        ),
    ]
