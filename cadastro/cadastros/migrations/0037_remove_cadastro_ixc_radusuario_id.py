# Remove vínculo PPPoE (radusuarios) — integração descontinuada no portal.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0036_cadastro_ixc_radusuario_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='historicalcadastro',
            name='ixc_radusuario_id',
        ),
        migrations.RemoveField(
            model_name='cadastro',
            name='ixc_radusuario_id',
        ),
    ]
