from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, path: Path) -> None:
        self.engine: Engine = create_engine(
            f"sqlite:///{path}", connect_args={"check_same_thread": False}
        )

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record) -> None:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self) -> None:
        """Upgrade the schema to the latest Alembic revision."""
        from alembic import command
        from alembic.config import Config

        cfg = Config()
        cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")

    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session

    def open_session(self) -> Session:
        """A session for use as a context manager outside request handling."""
        return self._sessions()
