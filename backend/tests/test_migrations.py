from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from aarr import models  # noqa: F401
from aarr.db import Base, Database


def test_migrations_create_schema_matching_models(tmp_path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        tables = set(inspect(conn).get_table_names())
    assert diff == []
    assert set(Base.metadata.tables) <= tables


def test_migrate_is_idempotent(tmp_path):
    db = Database(tmp_path / "t.db")
    db.migrate()
    db.migrate()
