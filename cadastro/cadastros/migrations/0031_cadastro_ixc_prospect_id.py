# IXC crm_prospect — coluna pode já existir no banco (ADD manual / migração parcial).

from django.db import migrations, models


def _column_exists(connection, table: str, column: str) -> bool:
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s AND column_name = %s
                """,
                [table, column],
            )
            return cursor.fetchone() is not None
        if connection.vendor == 'sqlite':
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
                [table],
            )
            if not cursor.fetchone():
                return False
            safe = table.replace('"', '')
            cursor.execute(f'PRAGMA table_info("{safe}")')
            return any(row[1] == column for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
            """,
            [table, column],
        )
        return cursor.fetchone() is not None


def add_ixc_prospect_id_columns(apps, schema_editor):
    connection = schema_editor.connection
    for model_name in ('Cadastro', 'HistoricalCadastro'):
        Model = apps.get_model('cadastros', model_name)
        table = Model._meta.db_table
        if _column_exists(connection, table, 'ixc_prospect_id'):
            continue
        qtable = connection.ops.quote_name(table)
        qcol = connection.ops.quote_name('ixc_prospect_id')
        schema_editor.execute(f'ALTER TABLE {qtable} ADD COLUMN {qcol} VARCHAR(50) NULL')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cadastros', '0030_alter_origemcanalvenda_ixc_id'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='cadastro',
                    name='ixc_prospect_id',
                    field=models.CharField(
                        blank=True,
                        help_text='ID do registro crm_prospect (prospecção) no IXC, quando criado pelo envio da ficha.',
                        max_length=50,
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name='historicalcadastro',
                    name='ixc_prospect_id',
                    field=models.CharField(blank=True, max_length=50, null=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_ixc_prospect_id_columns, noop_reverse),
            ],
        ),
    ]
