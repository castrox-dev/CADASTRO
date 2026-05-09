from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0021_cidade_saquarema'),
    ]

    operations = [
        migrations.AddField(
            model_name='planodefinicao',
            name='nome_velocidade',
            field=models.CharField(
                blank=True,
                help_text='Texto curto exibido em listagens / OS (ex.: «240 MEGA», «1 GIGA»). Vazio = usar o "titulo".',
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name='planodefinicao',
            name='preco_mensal_reais',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Mensalidade em R$ usada na geração da OS / ficha automática.',
                max_digits=10,
            ),
        ),
        migrations.CreateModel(
            name='OrigemCanalVenda',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(
                    help_text='Nome exibido na ficha (ex.: Instagram, Facebook, Indicação).',
                    max_length=80,
                    unique=True,
                )),
                ('ixc_id', models.CharField(
                    help_text='ID correspondente em CRM > Configurações > Origens no IXC.',
                    max_length=32,
                )),
                ('ordem', models.PositiveSmallIntegerField(default=0)),
                ('ativo', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Origem / canal de venda',
                'verbose_name_plural': 'Origens / canais de venda',
                'ordering': ['ordem', 'label'],
            },
        ),
    ]
