from arrr.db import Database
from arrr.models import AppSetting
from arrr.security import Secrets


class SettingsStore:
    """Key/value app settings; secret values are encrypted at rest."""

    def __init__(self, db: Database, secrets: Secrets) -> None:
        self._db = db
        self._secrets = secrets

    def get(self, key: str) -> str | None:
        with self._db.open_session() as session:
            row = session.get(AppSetting, key)
            if row is None or row.value is None:
                return None
            return self._secrets.decrypt(row.value) if row.is_secret else row.value

    def set(self, key: str, value: str | None, *, secret: bool = False) -> None:
        """Store a value; None or empty deletes the key."""
        with self._db.open_session() as session:
            row = session.get(AppSetting, key)
            if not value:
                if row is not None:
                    session.delete(row)
            else:
                stored = self._secrets.encrypt(value) if secret else value
                if row is None:
                    session.add(AppSetting(key=key, value=stored, is_secret=secret))
                else:
                    row.value, row.is_secret = stored, secret
            session.commit()
