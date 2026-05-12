# Generated manually — ID crm_candidatos IXC após lead.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0033_widen_ixc_envio_audit_columns_pg'),
    ]

    operations = [
        migrations.AddField(
            model_name='cadastro',
            name='ixc_candidato_id',
            field=models.CharField(
                blank=True,
                help_text='ID do registro crm_candidatos no IXC, quando criado encadeado após o lead.',
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
