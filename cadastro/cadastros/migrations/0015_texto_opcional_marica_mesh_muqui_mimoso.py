# Regras de opcional na ficha:
# - Maricá (grupo default): todos os planos com opção de repetidor Mesh (texto padrão global).
# - Muqui e Mimoso: plano essencial (100/240) com texto combinado roteador + Mesh; demais planos só Mesh (vazio → padrão).

from django.db import migrations

TEXTO_COMBO_ESSENCIAL = (
    'Deseja alugar roteador Wi-Fi por R$ 10,00/mês ou repetidor Mesh por R$ 29,99/mês?'
)


def forwards(apps, schema_editor):
    PlanoDefinicao = apps.get_model('cadastros', 'PlanoDefinicao')

    # Maricá e cidades do grupo "default": mesh padrão em todos (campo vazio)
    PlanoDefinicao.objects.filter(grupo__slug='default').update(texto_opcional='')

    # Muqui / Piúma: essencial = roteador ou mesh; restante = mesh padrão
    PlanoDefinicao.objects.filter(grupo__slug='muqui_piuma', codigo='essencial').update(
        texto_opcional=TEXTO_COMBO_ESSENCIAL
    )
    PlanoDefinicao.objects.filter(grupo__slug='muqui_piuma').exclude(codigo='essencial').update(
        texto_opcional=''
    )

    # Mimoso: essencial = roteador ou mesh; restante = mesh padrão
    PlanoDefinicao.objects.filter(grupo__slug='mimoso', codigo='essencial').update(
        texto_opcional=TEXTO_COMBO_ESSENCIAL
    )
    PlanoDefinicao.objects.filter(grupo__slug='mimoso').exclude(codigo='essencial').update(
        texto_opcional=''
    )


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0014_default_planos_textos_prime'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
