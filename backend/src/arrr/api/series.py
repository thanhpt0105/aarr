import os
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arrr.api.deps import SessionDep
from arrr.api.tmdb_dep import TmdbDep, metadata_http_error
from arrr.metadata.models import MetadataError
from arrr.metadata.tmdb import poster_url
from arrr.models import Episode, QualityProfile, RootFolder, Season, Series
from arrr.security import require_api_key
from arrr.services.naming import series_folder_name
from arrr.services.series_sync import (
    MonitorRule,
    apply_series_details,
    fetch_series,
    sync_seasons_and_episodes,
)

router = APIRouter(
    prefix="/api/v1/series", tags=["series"], dependencies=[Depends(require_api_key)]
)


class SeriesAdd(BaseModel):
    tmdb_id: int
    quality_profile_id: int
    root_folder_id: int
    monitored: bool = True
    monitor: MonitorRule = "all"  # which existing episodes to monitor


class SeriesUpdate(BaseModel):
    monitored: bool | None = None
    quality_profile_id: int | None = None
    root_folder_id: int | None = None


class MonitoredUpdate(BaseModel):
    monitored: bool


class SeasonOut(BaseModel):
    season_number: int
    monitored: bool
    episode_count: int
    monitored_episode_count: int


class EpisodeOut(BaseModel):
    id: int
    season_number: int
    episode_number: int
    title: str
    air_date: date | None
    overview: str
    runtime: int | None
    monitored: bool


class SeriesOut(BaseModel):
    id: int
    tmdb_id: int
    imdb_id: str | None
    tvdb_id: int | None
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_url: str | None
    status: str | None
    first_air_date: date | None
    monitored: bool
    quality_profile_id: int
    root_folder_id: int
    folder_name: str
    path: str
    added_at: datetime
    last_refreshed_at: datetime | None
    season_count: int
    episode_count: int


class SeriesDetailOut(SeriesOut):
    seasons: list[SeasonOut]


def _counts(session: Session, series_ids: list[int]) -> dict[int, tuple[int, int]]:
    """series_id -> (seasons excluding specials, episodes excluding specials)."""
    rows = session.execute(
        select(
            Episode.series_id,
            func.count(func.distinct(Episode.season_number)),
            func.count(Episode.id),
        )
        .where(Episode.series_id.in_(series_ids), Episode.season_number > 0)
        .group_by(Episode.series_id)
    )
    return {sid: (seasons, episodes) for sid, seasons, episodes in rows}


def _out(series: Series, counts: tuple[int, int]) -> dict:
    return {
        "id": series.id,
        "tmdb_id": series.tmdb_id,
        "imdb_id": series.imdb_id,
        "tvdb_id": series.tvdb_id,
        "title": series.title,
        "original_title": series.original_title,
        "year": series.year,
        "overview": series.overview,
        "poster_url": poster_url(series.poster_path),
        "status": series.status,
        "first_air_date": series.first_air_date,
        "monitored": series.monitored,
        "quality_profile_id": series.quality_profile_id,
        "root_folder_id": series.root_folder_id,
        "folder_name": series.folder_name,
        "path": os.path.join(series.root_folder.path, series.folder_name),
        "added_at": series.added_at,
        "last_refreshed_at": series.last_refreshed_at,
        "season_count": counts[0],
        "episode_count": counts[1],
    }


def _detail(session: Session, series: Series) -> SeriesDetailOut:
    counts = _counts(session, [series.id]).get(series.id, (0, 0))
    stats = session.execute(
        select(
            Episode.season_number,
            func.count(Episode.id),
            func.coalesce(func.sum(Episode.monitored), 0),
        )
        .where(Episode.series_id == series.id)
        .group_by(Episode.season_number)
    )
    totals = {n: (total, int(monitored)) for n, total, monitored in stats}
    seasons = session.scalars(
        select(Season).where(Season.series_id == series.id).order_by(Season.season_number)
    )
    return SeriesDetailOut(
        **_out(series, counts),
        seasons=[
            SeasonOut(
                season_number=s.season_number,
                monitored=s.monitored,
                episode_count=totals.get(s.season_number, (0, 0))[0],
                monitored_episode_count=totals.get(s.season_number, (0, 0))[1],
            )
            for s in seasons
        ],
    )


def _get(session: Session, series_id: int) -> Series:
    series = session.get(Series, series_id)
    if series is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Series not found")
    return series


def _check_refs(session: Session, profile_id: int | None, root_folder_id: int | None) -> None:
    if profile_id is not None and session.get(QualityProfile, profile_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quality profile not found")
    if root_folder_id is not None:
        folder = session.get(RootFolder, root_folder_id)
        if folder is None or folder.media_type != "tv":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Root folder not found for TV")


@router.get("")
def list_series(session: SessionDep, monitored: bool | None = None) -> list[SeriesOut]:
    query = select(Series).order_by(Series.title, Series.id)
    if monitored is not None:
        query = query.where(Series.monitored.is_(monitored))
    rows = list(session.scalars(query))
    counts = _counts(session, [s.id for s in rows])
    return [SeriesOut(**_out(s, counts.get(s.id, (0, 0)))) for s in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_series(body: SeriesAdd, tmdb: TmdbDep, session: SessionDep) -> SeriesDetailOut:
    if session.scalar(select(Series.id).where(Series.tmdb_id == body.tmdb_id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Series is already in the library")
    _check_refs(session, body.quality_profile_id, body.root_folder_id)
    try:
        details, episodes = await fetch_series(tmdb, body.tmdb_id)
    except MetadataError as exc:
        raise metadata_http_error(exc) from exc

    series = Series(
        tmdb_id=body.tmdb_id,
        monitored=body.monitored and body.monitor != "none",
        quality_profile_id=body.quality_profile_id,
        root_folder_id=body.root_folder_id,
        folder_name=series_folder_name(details.title, details.year),
    )
    apply_series_details(series, details)
    session.add(series)
    session.flush()
    sync_seasons_and_episodes(session, series, details, episodes, rule=body.monitor)
    session.commit()
    return _detail(session, series)


@router.get("/{series_id}")
def get_series(series_id: int, session: SessionDep) -> SeriesDetailOut:
    return _detail(session, _get(session, series_id))


@router.patch("/{series_id}")
def update_series(series_id: int, body: SeriesUpdate, session: SessionDep) -> SeriesDetailOut:
    series = _get(session, series_id)
    _check_refs(session, body.quality_profile_id, body.root_folder_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(series, field, value)
    session.commit()
    session.refresh(series)
    return _detail(session, series)


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(series_id: int, session: SessionDep) -> None:
    session.delete(_get(session, series_id))
    session.commit()


@router.post("/{series_id}/refresh")
async def refresh_series(series_id: int, tmdb: TmdbDep, session: SessionDep) -> SeriesDetailOut:
    series = _get(session, series_id)
    try:
        details, episodes = await fetch_series(tmdb, series.tmdb_id)
    except MetadataError as exc:
        raise metadata_http_error(exc) from exc
    apply_series_details(series, details)  # folder_name is kept so existing files stay put
    sync_seasons_and_episodes(session, series, details, episodes)
    session.commit()
    return _detail(session, series)


@router.get("/{series_id}/episodes")
def list_episodes(
    series_id: int, session: SessionDep, season: int | None = None
) -> list[EpisodeOut]:
    _get(session, series_id)
    query = select(Episode).where(Episode.series_id == series_id)
    if season is not None:
        query = query.where(Episode.season_number == season)
    rows = session.scalars(query.order_by(Episode.season_number, Episode.episode_number))
    return [EpisodeOut.model_validate(e, from_attributes=True) for e in rows]


@router.patch("/{series_id}/seasons/{season_number}")
def update_season(
    series_id: int, season_number: int, body: MonitoredUpdate, session: SessionDep
) -> SeasonOut:
    _get(session, series_id)
    season = session.scalar(
        select(Season).where(Season.series_id == series_id, Season.season_number == season_number)
    )
    if season is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Season not found")
    season.monitored = body.monitored
    episodes = session.scalars(
        select(Episode).where(
            Episode.series_id == series_id, Episode.season_number == season_number
        )
    ).all()
    for episode in episodes:
        episode.monitored = body.monitored
    session.commit()
    return SeasonOut(
        season_number=season_number,
        monitored=season.monitored,
        episode_count=len(episodes),
        monitored_episode_count=len(episodes) if body.monitored else 0,
    )


@router.patch("/{series_id}/episodes/{episode_id}")
def update_episode(
    series_id: int, episode_id: int, body: MonitoredUpdate, session: SessionDep
) -> EpisodeOut:
    episode = session.get(Episode, episode_id)
    if episode is None or episode.series_id != series_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Episode not found")
    episode.monitored = body.monitored
    session.commit()
    return EpisodeOut.model_validate(episode, from_attributes=True)
