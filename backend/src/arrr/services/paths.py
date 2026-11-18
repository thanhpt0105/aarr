from collections.abc import Iterable
from typing import Protocol


class PathMapping(Protocol):
    remote_path: str
    local_path: str


def map_path(path: str | None, mappings: Iterable[PathMapping]) -> str | None:
    """Translate a client-reported path to a local one; the longest matching remote prefix wins."""
    if path is None:
        return None
    normalized = path.replace("\\", "/")
    for m in sorted(mappings, key=lambda m: len(m.remote_path.rstrip("/\\")), reverse=True):
        remote = m.remote_path.replace("\\", "/").rstrip("/")
        if normalized == remote or normalized.startswith(remote + "/"):
            return m.local_path.rstrip("/\\") + normalized[len(remote) :]
    return path
