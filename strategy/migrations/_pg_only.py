"""Postgres-only variant of RunSQL.

These strategy migrations convert `integer[]` columns to `jsonb`, which is
PostgreSQL syntax. Production runs on Postgres so they apply normally there,
but on any other backend - notably the sqlite database Django's test runner
creates - they abort with `OperationalError: near "ALTER": syntax error`,
which made the whole test suite unrunnable without a live Postgres instance.

Skipping them off-Postgres is correct as well as safe: a fresh database builds
these tables from the current model state, where the columns are already
JSONField, so there is nothing to convert.

Files beginning with an underscore are ignored by Django's migration loader,
so this module is a helper rather than a migration.
"""

from django.db import migrations


class PostgresOnlyRunSQL(migrations.RunSQL):
    """RunSQL that silently no-ops on non-PostgreSQL backends."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != 'postgresql':
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor != 'postgresql':
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)
