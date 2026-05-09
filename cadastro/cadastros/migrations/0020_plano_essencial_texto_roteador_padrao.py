# Essencial: texto no BD volta ao roteador só; combo roteador+Mesh nas filiais 7 é só no front (script.js).

from django.db import migrations

TEXTO_OPCIONAL_ROTEADOR_ESSENCIAL = 'Deseja alugar roteador Wi-Fi por R$ 10,00/mês?'


def forwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')
    for slug in ('default', 'muqui_piuma', 'mimoso'):
        PlanoDefinicao.objects.filter(grupo__slug=slug, codigo='essencial').update(
            texto_opcional=TEXTO_OPCIONAL_ROTEADOR_ESSENCIAL
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0019_plano_texto_opcional_combo_independent'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
