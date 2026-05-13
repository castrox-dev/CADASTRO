# Restaura ixc_candidato_id (removido por engano na 0039; views ainda gravam após crm_canditados).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0039_remove_cadastro_ixc_candidato_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cadastro',
            name='ixc_candidato_id',
            field=models.CharField(
                blank=True,
                help_text='ID do registro crm_canditados/crm_candidatos no IXC, quando criado encadeado após o lead.',
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='historicalcadastro',
            name='ixc_candidato_id',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
