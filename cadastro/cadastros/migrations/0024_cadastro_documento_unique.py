"""
Adiciona unique=True ao campo Cadastro.documento.

Antes de aplicar a constraint, executa uma checagem defensiva: se houver
documentos duplicados no banco, a migration aborta com mensagem clara
listando os documentos em conflito. Isso evita falha silenciosa de
IntegrityError durante o ALTER TABLE.

Para resolver eventuais duplicatas:
  1) Identifique-as (a mensagem mostra os primeiros 10 documentos duplicados);
  2) Decida quais cadastros manter (geralmente o mais recente ou o que tem
     ixc_lead_id preenchido) e remova/anonimize os demais;
  3) Rode `python manage.py migrate` novamente.
"""
from django.core.exceptions import ValidationError
from django.db import migrations, models
from django.db.models import Count


def assert_no_duplicates(apps, schema_editor):
    Cadastro = apps.get_model('cadastros', 'Cadastro')
    duplicates = (
        Cadastro.objects.values('documento')
        .annotate(n=Count('id'))
        .filter(n__gt=1)
        .order_by('-n')[:10]
    )
    duplicates = list(duplicates)
    if duplicates:
        linhas = ', '.join(f"{d['documento']} ({d['n']}x)" for d in duplicates)
        raise ValidationError(
            'Não foi possível aplicar unique=True em Cadastro.documento '
            f'porque existem documentos duplicados no banco: {linhas}. '
            'Resolva as duplicatas e rode `python manage.py migrate` novamente. '
            'Veja docstring desta migration para o passo a passo.'
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0023_seed_precos_velocidades_origens'),
    ]

    operations = [
        migrations.RunPython(assert_no_duplicates, noop_reverse),
        migrations.AlterField(
            model_name='cadastro',
            name='documento',
            field=models.CharField(db_index=True, max_length=20, unique=True),
        ),
    ]
