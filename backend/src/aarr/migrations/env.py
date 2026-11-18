from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from aarr import models  # noqa: F401  (registers tables on Base)
from aarr.db import Base, UTCDateTime

config = context.config


def _render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    # Keep migrations independent of application code.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite needs batch mode for most ALTERs
        compare_type=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.connect() as conn:
        _run(conn)
