"""
Popula nome_velocidade e preco_mensal_reais nos PlanoDefinicao existentes
e cria registros padrão em OrigemCanalVenda. Idempotente: roda uma única vez,
e o `update`/`get_or_create` não duplica nada.

Os valores vieram dos dicionários hardcoded em `cadastros/models.py`
(`os_formatada`, `ficha_formatada`) e em `cadastros/integrations.py`
(`ORIGENS_MAP`). Ajuste depois pelo painel /admin-dash/operacao/.
"""
from decimal import Decimal

from django.db import migrations


PLANOS_VELOCIDADE = {
    'essencial': '240 MEGA',
    'rapido': '400 MEGA',
    'turbo': '500 MEGA',
    'ultra': '600 MEGA',
    'prime': '700 MEGA',
    '1giga': '1 GIGA',
    'plano_300': '300 MEGA',
    'plano_700': '700 MEGA',
}

PLANOS_PRECO = {
    'essencial': Decimal('59.99'),
    'rapido': Decimal('79.99'),
    'turbo': Decimal('99.99'),
    'ultra': Decimal('119.99'),
    'prime': Decimal('99.99'),
    '1giga': Decimal('149.99'),
    'plano_300': Decimal('69.99'),
    'plano_700': Decimal('89.99'),
}

ORIGENS = [
    ('Instagram', '6', 1),
    ('Facebook', '9', 2),
    ('Google', '7', 3),
    ('Google Ads', '12', 4),
    ('Indicação', '4', 5),
    ('Site', '10', 6),
    ('WhatsApp', '1', 7),
    ('TikTok', '13', 8),
]


def populate_planos(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    for plano in PlanoDefinicao.objects.all():
        codigo = (plano.codigo or '').strip()
        velocidade = PLANOS_VELOCIDADE.get(codigo, '')
        preco = PLANOS_PRECO.get(codigo)

        changed = False
        if velocidade and not (plano.nome_velocidade or '').strip():
            plano.nome_velocidade = velocidade
            changed = True
        if preco is not None and (plano.preco_mensal_reais in (None, 0, Decimal('0'))):
            plano.preco_mensal_reais = preco
            changed = True
        if changed:
            plano.save(update_fields=['nome_velocidade', 'preco_mensal_reais'])


def populate_origens(apps, schema_editor):
    OrigemCanalVenda = apps.get_model('cadastros', 'OrigemCanalVenda')
    for label, ixc_id, ordem in ORIGENS:
        OrigemCanalVenda.objects.update_or_create(
            label=label,
            defaults={'ixc_id': ixc_id, 'ordem': ordem, 'ativo': True},
        )


def noop_reverse(apps, schema_editor):
    # Reversão deliberadamente sem efeito: dados podem ter sido editados após o seed.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0022_planodefinicao_preco_velocidade_origemcanalvenda'),
    ]

    operations = [
        migrations.RunPython(populate_planos, noop_reverse),
        migrations.RunPython(populate_origens, noop_reverse),
    ]
