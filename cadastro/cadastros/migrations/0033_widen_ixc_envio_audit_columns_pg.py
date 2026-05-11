# Corrige PostgreSQL onde ixc_envio_mensagem / ixc_envio_logs ficaram varchar(255)
# e estouram ao salvar logs longos da integração IXC (vários fallbacks de prospect).

from django.db import migrations


def _pg_column_type(cursor, table: str, column: str):
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        """,
        [table, column],
    )
    row = cursor.fetchone()
    return row[0] if row else None


def widen_ixc_audit_columns(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != 'postgresql':
        return
    with conn.cursor() as cursor:
        for table in ('cadastros_cadastro', 'cadastros_historicalcadastro'):
            dt = _pg_column_type(cursor, table, 'ixc_envio_mensagem')
            if dt == 'character varying':
                cursor.execute(
                    f'ALTER TABLE "{table}" ALTER COLUMN ixc_envio_mensagem TYPE text '
                    f'USING COALESCE(ixc_envio_mensagem::text, \'\')'
                )

            dt = _pg_column_type(cursor, table, 'ixc_envio_logs')
            if not dt or dt == 'jsonb':
                continue
            sql = (
                f'ALTER TABLE "{table}" ALTER COLUMN ixc_envio_logs TYPE jsonb USING ('
                f'CASE WHEN ixc_envio_logs IS NULL OR trim(ixc_envio_logs::text) = \'\' '
                f'THEN \'{{}}\'::jsonb ELSE trim(ixc_envio_logs::text)::jsonb END)'
            )
            try:
                cursor.execute(sql)
            except Exception:
                cursor.execute(
                    f'ALTER TABLE "{table}" ALTER COLUMN ixc_envio_logs TYPE jsonb '
                    f'USING \'{{}}\'::jsonb'
                )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0032_alter_historicalcadastro_ixc_prospect_id'),
    ]

    operations = [
        migrations.RunPython(widen_ixc_audit_columns, noop_reverse),
    ]
