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

    def create_all(self) -> None:
        from arrr import models  # noqa: F401  (registers tables on Base)

        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self._sessions() as session:
            yield session
