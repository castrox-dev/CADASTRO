# Generated manually — ID do contrato IXC após teste cliente_contrato.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0033_widen_ixc_envio_audit_columns_pg'),
    ]

    operations = [
        migrations.AddField(
            model_name='cadastro',
            name='ixc_contrato_id',
            field=models.CharField(
                blank=True,
                help_text='ID do contrato (cliente_contrato) no IXC, quando criado pelo teste ou integração.',
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='historicalcadastro',
            name='ixc_contrato_id',
            field=models.CharField(
                blank=True,
                help_text='ID do contrato (cliente_contrato) no IXC, quando criado pelo teste ou integração.',
                max_length=50,
                null=True,
            ),
        ),
    ]
