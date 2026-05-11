# Coluna ixc_envio_logs no histórico — em alguns bancos já existe como json/jsonb (não aceita '').

from django.db import migrations, models


def _pg_column_type(cursor, table: str, column: str):
    cursor.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        """,
        [table, column],
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _ensure_logs_column(conn, table: str):
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == 'postgresql':
            if _pg_column_type(cursor, table, 'ixc_envio_logs'):
                return
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN ixc_envio_logs jsonb '
                f"DEFAULT '{{}}'::jsonb NOT NULL"
            )
        elif vendor == 'sqlite':
            cursor.execute(f'PRAGMA table_info("{table}")')
            cols = [row[1] for row in cursor.fetchall()]
            if 'ixc_envio_logs' in cols:
                return
            cursor.execute(
                f'ALTER TABLE "{table}" ADD COLUMN ixc_envio_logs text '
                f"NOT NULL DEFAULT '{{}}'"
            )


def _backfill_logs_sql(conn, table: str):
    vendor = conn.vendor
    with conn.cursor() as cursor:
        if vendor == 'postgresql':
            dt = _pg_column_type(cursor, table, 'ixc_envio_logs')
            if dt in ('json', 'jsonb'):
                cursor.execute(
                    f'UPDATE "{table}" SET ixc_envio_logs = %s::jsonb '
                    f'WHERE ixc_envio_logs IS NULL',
                    ['{}'],
                )
            else:
                cursor.execute(
                    f'UPDATE "{table}" SET ixc_envio_logs = %s '
                    f'WHERE ixc_envio_logs IS NULL',
                    [''],
                )
        elif vendor == 'sqlite':
            cursor.execute(
                f'UPDATE "{table}" SET ixc_envio_logs = ? '
                f'WHERE ixc_envio_logs IS NULL',
                ('{}',),
            )


def add_ixc_envio_logs_sql(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor not in ('postgresql', 'sqlite'):
        return
    for table in ('cadastros_cadastro', 'cadastros_historicalcadastro'):
        _ensure_logs_column(conn, table)
        _backfill_logs_sql(conn, table)


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0027_cadastro_ixc_envio_mensagem'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_ixc_envio_logs_sql,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='cadastro',
                    name='ixc_envio_logs',
                    field=models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Auditoria do envio IXC; ex.: {"text": "…linhas de log…"}.',
                    ),
                ),
                migrations.AddField(
                    model_name='historicalcadastro',
                    name='ixc_envio_logs',
                    field=models.JSONField(
                        blank=True,
                        default=dict,
                        help_text='Auditoria do envio IXC; ex.: {"text": "…linhas de log…"}.',
                    ),
                ),
            ],
        ),
    ]
