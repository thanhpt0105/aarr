from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Protocol = Literal["torrent", "usenet"]
SearchKind = Literal["search", "movie", "tv"]


class IndexerError(Exception):
    """Connection, authentication, or response failure talking to an indexer."""


@dataclass(frozen=True)
class SearchQuery:
    kind: SearchKind = "search"
    q: str | None = None
    season: int | None = None
    episode: int | None = None
    imdb_id: str | None = None
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    categories: tuple[int, ...] = ()
    limit: int = 100


@dataclass(frozen=True)
class Release:
    indexer: str
    title: str
    guid: str
    download_url: str
    protocol: Protocol
    size: int
    published: datetime | None = None
    seeders: int | None = None
    leechers: int | None = None
    infohash: str | None = None
    info_url: str | None = None
    categories: tuple[int, ...] = ()


@dataclass(frozen=True)
class Caps:
    title: str | None
    search_modes: dict[str, frozenset[str]]  # available modes -> supported params
    categories: dict[int, str]
