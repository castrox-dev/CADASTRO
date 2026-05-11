# Alinha modelo com bancos que já tinham ixc_envio_status NOT NULL.
#
# SeparateDatabaseAndState aplica database_operations ANTES de atualizar o
# estado do projeto: RunPython não pode usar ORM com ixc_envio_status até o
# fim da migração — por isso criação/backfill vão em SQL bruto.

from django.db import migrations, models


def _ensure_column(conn, table: str):
    """Cria a coluna apenas se ainda não existir (evita duplicate column)."""
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = 'ixc_envio_status'
                """,
                [table],
            )
            if cursor.fetchone():
                return
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN ixc_envio_status varchar(20) '
                f"DEFAULT 'pendente' NOT NULL"
            )
        elif vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info("{table}")')
            cols = [row[1] for row in cursor.fetchall()]
            if 'ixc_envio_status' in cols:
                return
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN ixc_envio_status varchar(20) '
                f"NOT NULL DEFAULT 'pendente'"
            )


def _backfill_ixc_envio_status_sql(conn, table: str):
    """Preenche vazios/nulos sem passar pelo ORM (estado ainda sem o campo)."""
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == 'postgresql':
            cursor.execute(
                f'UPDATE "{table}" SET ixc_envio_status = %s '
                f"WHERE ixc_envio_status IS NULL OR TRIM(ixc_envio_status) = ''",
                ['pendente'],
            )
        elif vendor == 'sqlite':
            cursor.execute(
                f'UPDATE "{table}" SET ixc_envio_status = ? '
                f'WHERE ixc_envio_status IS NULL OR TRIM(ixc_envio_status) = ?',
                ('pendente', ''),
            )


def add_ixc_envio_columns_and_backfill_sql(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor not in ('postgresql', 'sqlite'):
        return
    for table in ('cadastros_cadastro', 'cadastros_historicalcadastro'):
        _ensure_column(conn, table)
        _backfill_ixc_envio_status_sql(conn, table)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0025_cadastro_anonimizado_em_cadastro_consentimento_em_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_ixc_envio_columns_and_backfill_sql,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='cadastro',
                    name='ixc_envio_status',
                    field=models.CharField(
                        db_index=True,
                        default='pendente',
                        help_text='Último estado do envio ao IXC (histórico simple_history exige valor).',
                        max_length=20,
                    ),
                ),
                migrations.AddField(
                    model_name='historicalcadastro',
                    name='ixc_envio_status',
                    field=models.CharField(
                        db_index=True,
                        default='pendente',
                        help_text='Último estado do envio ao IXC (histórico simple_history exige valor).',
                        max_length=20,
                    ),
                ),
            ],
        ),
    ]
