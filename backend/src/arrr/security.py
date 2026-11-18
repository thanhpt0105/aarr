import os
import secrets
from collections.abc import Callable
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi import Header, HTTPException, Request, status


def _load_or_create(path: Path, generate: Callable[[], str]) -> str:
    if path.exists():
        return path.read_text().strip()
    value = generate()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    return value


class Secrets:
    """API key and credential-encryption key, persisted in the data dir."""

    def __init__(self, data_dir: Path) -> None:
        self.api_key = _load_or_create(data_dir / "api_key", lambda: secrets.token_hex(16))
        fernet_key = _load_or_create(
            data_dir / "secret.key", lambda: Fernet.generate_key().decode()
        )
        self._fernet = Fernet(fernet_key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()


def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected: str = request.app.state.secrets.api_key
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")
