from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class DownloadClientError(Exception):
    """Connection, authentication, or API failure talking to a download client."""


class DownloadState(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class QueueItem:
    id: str
    title: str
    state: DownloadState
    progress: float  # 0.0 - 1.0
    size_bytes: int
    category: str
    path: str | None  # client-side path of the content once available


class DownloadClient(ABC):
    @abstractmethod
    async def test(self) -> str:
        """Verify connectivity and credentials; return the client version."""

    @abstractmethod
    async def add(self, url: str, category: str) -> str | None:
        """Send a magnet/torrent/NZB URL. Return the client item id if known up front."""

    @abstractmethod
    async def queue(self, category: str | None = None) -> list[QueueItem]:
        """Active and recently completed items, optionally filtered by category."""

    @abstractmethod
    async def remove(self, item_id: str, delete_files: bool = False) -> None: ...

    @abstractmethod
    async def aclose(self) -> None: ...
