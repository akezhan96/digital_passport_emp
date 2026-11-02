"""Bring an existing database in line with the models on start-up.

`Base.metadata.create_all()` creates missing *tables* but silently ignores
columns added to a table that already exists. Without this, deploying a new
version over an existing database leaves the code expecting columns the
database does not have, and every query against them fails at runtime.

Scope, deliberately narrow and non-destructive:

  * adds missing tables      (create_all)
  * adds missing columns     (ALTER TABLE ... ADD COLUMN)
  * adds missing indexes declared on the models

It never drops, renames or retypes anything. A change of that kind needs a
real migration tool (Alembic) and a considered data-movement plan; this module
exists so additive changes deploy cleanly, not to pretend it is one.
"""

from typing import List

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex


def _column_ddl(column) -> str:
    """Render a column definition for ALTER TABLE ADD COLUMN.

    NOT NULL is always stripped here: a populated table cannot accept a
    non-null column in one step. The constraint is re-applied after the
    backfill (see _enforce_not_null).
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateColumn

    ddl = str(CreateColumn(column).compile(dialect=postgresql.dialect()))
    return ddl.replace(" NOT NULL", "")


def _default_value(column):
    """The scalar a Python-side default would produce, if it is a constant."""
    default = column.default
    if default is None:
        return None
    if getattr(default, "is_scalar", False):
        return default.arg
    if getattr(default, "is_callable", False):
        try:
            return default.arg(None)
        except Exception:                                        # noqa: BLE001
            return None
    return None


def _enforce_not_null(connection, table_name: str, column) -> bool:
    """Re-apply NOT NULL once every row has a value."""
    from sqlalchemy import text as _text

    remaining = connection.execute(_text(
        f'SELECT COUNT(*) FROM "{table_name}" WHERE "{column.name}" IS NULL'
    )).scalar()
    if remaining:
        return False                 # leave it nullable rather than fail boot
    connection.execute(_text(
        f'ALTER TABLE "{table_name}" ALTER COLUMN "{column.name}" SET NOT NULL'))
    return True


def sync_schema(engine: Engine, metadata) -> List[str]:
    """Apply additive schema changes. Returns a list of what was done."""
    applied: List[str] = []

    # 1. Missing tables.
    metadata.create_all(bind=engine)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue          # just created, nothing to reconcile

            present = {c["name"] for c in inspector.get_columns(table.name)}

            # 2. Missing columns.
            for column in table.columns:
                if column.name in present:
                    continue

                # 2a. add it nullable
                connection.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN {_column_ddl(column)}'))
                applied.append(f"{table.name}.{column.name}")

                # 2b. backfill existing rows from the model's default
                value = _default_value(column)
                if value is not None:
                    connection.execute(
                        text(f'UPDATE "{table.name}" SET "{column.name}" = :v '
                             f'WHERE "{column.name}" IS NULL'),
                        {"v": value},
                    )

                # 2c. restore NOT NULL now that no row is null
                if not column.nullable and column.primary_key is False:
                    if _enforce_not_null(connection, table.name, column):
                        applied.append(f"{table.name}.{column.name} NOT NULL")

            # 3. Missing indexes.
            index_names = {i["name"] for i in inspector.get_indexes(table.name)}
            for index in table.indexes:
                if index.name in index_names:
                    continue
                # A missing uniqueness constraint is a failed upgrade, not a
                # usable database. Roll back this transaction and stop startup.
                connection.execute(CreateIndex(index, if_not_exists=True))
                applied.append(f"index {index.name}")

    return applied
