# Coluna ixc_envio_mensagem NOT NULL no histórico — alinha ORM (mesmo padrão da 0026).

from django.db import migrations, models


def _ensure_mensagem_column(conn, table: str):
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = 'ixc_envio_mensagem'
                """,
                [table],
            )
            if cursor.fetchone():
                return
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN ixc_envio_mensagem text '
                f"DEFAULT '' NOT NULL"
            )
        elif vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info("{table}")')
            cols = [row[1] for row in cursor.fetchall()]
            if 'ixc_envio_mensagem' in cols:
                return
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN ixc_envio_mensagem text '
                f"NOT NULL DEFAULT ''"
            )


def _backfill_mensagem_sql(conn, table: str):
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(
                f'UPDATE "{table}" SET ixc_envio_mensagem = %s '
                f'WHERE ixc_envio_mensagem IS NULL',
                [''],
            )
        elif vendor == 'sqlite':
            cursor.execute(
                f'UPDATE "{table}" SET ixc_envio_mensagem = ? '
                f'WHERE ixc_envio_mensagem IS NULL',
                ('',),
            )


def add_ixc_envio_mensagem_sql(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor not in ('postgresql', 'sqlite'):
        return
    for table in ('cadastros_cadastro', 'cadastros_historicalcadastro'):
        _ensure_mensagem_column(conn, table)
        _backfill_mensagem_sql(conn, table)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0026_cadastro_ixc_envio_status'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_ixc_envio_mensagem_sql,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='cadastro',
                    name='ixc_envio_mensagem',
                    field=models.TextField(
                        blank=True,
                        default='',
                        help_text='Última mensagem da API IXC ou resumo do envio (auditoria).',
                    ),
                ),
                migrations.AddField(
                    model_name='historicalcadastro',
                    name='ixc_envio_mensagem',
                    field=models.TextField(
                        blank=True,
                        default='',
                        help_text='Última mensagem da API IXC ou resumo do envio (auditoria).',
                    ),
                ),
            ],
        ),
    ]
