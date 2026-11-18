from dataclasses import dataclass
from datetime import date
from typing import Literal

MediaType = Literal["movie", "tv"]


class MetadataError(Exception):
    """Failure talking to a metadata provider."""


class MetadataNotFound(MetadataError):
    pass


@dataclass(frozen=True)
class MetadataHit:
    tmdb_id: int
    media_type: MediaType
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_path: str | None


@dataclass(frozen=True)
class MovieDetails:
    tmdb_id: int
    imdb_id: str | None
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_path: str | None
    status: str | None
    runtime: int | None
    in_cinemas: date | None
    digital_release: date | None
    physical_release: date | None


@dataclass(frozen=True)
class SeasonSummary:
    season_number: int
    episode_count: int
    air_date: date | None


@dataclass(frozen=True)
class SeriesDetails:
    tmdb_id: int
    imdb_id: str | None
    tvdb_id: int | None
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_path: str | None
    status: str | None
    first_air_date: date | None
    seasons: tuple[SeasonSummary, ...]


@dataclass(frozen=True)
class EpisodeDetails:
    season_number: int
    episode_number: int
    title: str
    air_date: date | None
    overview: str
    runtime: int | None
