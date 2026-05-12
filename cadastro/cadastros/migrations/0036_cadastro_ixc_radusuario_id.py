# ID radusuarios (PPPoE) IXC após lead.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0035_alter_historicalcadastro_ixc_candidato_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='cadastro',
            name='ixc_radusuario_id',
            field=models.CharField(
                blank=True,
                help_text='ID do registro radusuarios (PPPoE) no IXC, quando criado encadeado após o lead.',
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='historicalcadastro',
            name='ixc_radusuario_id',
            field=models.CharField(
                blank=True,
                help_text='ID do registro radusuarios (PPPoE) no IXC, quando criado encadeado após o lead.',
                max_length=50,
                null=True,
            ),
        ),
    ]
