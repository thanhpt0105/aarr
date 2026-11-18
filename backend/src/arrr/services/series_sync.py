import asyncio
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from arrr.db import utcnow
from arrr.metadata.models import EpisodeDetails, MetadataNotFound, SeriesDetails
from arrr.metadata.tmdb import TmdbClient
from arrr.models import Episode, Season, Series

MonitorRule = Literal["all", "future", "none"]
_SEASON_FETCH_CONCURRENCY = 5


async def fetch_series(
    tmdb: TmdbClient, tmdb_id: int
) -> tuple[SeriesDetails, dict[int, list[EpisodeDetails]]]:
    """Series details plus the episodes of every season, fetched concurrently."""
    details = await tmdb.series(tmdb_id)
    limit = asyncio.Semaphore(_SEASON_FETCH_CONCURRENCY)

    async def season(number: int) -> tuple[int, list[EpisodeDetails]]:
        async with limit:
            try:
                return number, await tmdb.season_episodes(tmdb_id, number)
            except MetadataNotFound:  # TMDB lists some seasons it has no data for
                return number, []

    results = await asyncio.gather(*(season(s.season_number) for s in details.seasons))
    return details, dict(results)


def apply_series_details(series: Series, details: SeriesDetails) -> None:
    series.imdb_id = details.imdb_id
    series.tvdb_id = details.tvdb_id
    series.title = details.title
    series.original_title = details.original_title
    series.year = details.year
    series.overview = details.overview
    series.poster_path = details.poster_path
    series.status = details.status
    series.first_air_date = details.first_air_date


def _initial_monitored(rule: MonitorRule, season_number: int, air_date: date | None) -> bool:
    if rule == "none" or season_number == 0:  # specials are opt-in
        return False
    if rule == "future":
        return air_date is None or air_date >= date.today()
    return True


def sync_seasons_and_episodes(
    session: Session,
    series: Series,
    details: SeriesDetails,
    episodes: dict[int, list[EpisodeDetails]],
    rule: MonitorRule | None = None,
) -> None:
    """Upsert seasons/episodes from TMDB.

    With `rule` (a new series) monitoring is decided by the rule. Without it (a refresh)
    existing flags are kept and new episodes inherit their season's flag.
    """
    seasons = {
        s.season_number: s
        for s in session.scalars(select(Season).where(Season.series_id == series.id))
    }
    for summary in details.seasons:
        if summary.season_number not in seasons:
            if rule is None:
                monitored = series.monitored and summary.season_number != 0
            else:
                monitored = _initial_monitored(rule, summary.season_number, None)
            seasons[summary.season_number] = Season(
                series_id=series.id, season_number=summary.season_number, monitored=monitored
            )
            session.add(seasons[summary.season_number])

    existing = {
        (e.season_number, e.episode_number): e
        for e in session.scalars(select(Episode).where(Episode.series_id == series.id))
    }
    seen: set[tuple[int, int]] = set()
    any_monitored: dict[int, bool] = {}
    for season_number, items in episodes.items():
        for item in items:
            key = (item.season_number, item.episode_number)
            seen.add(key)
            row = existing.get(key)
            if row is None:
                monitored = (
                    _initial_monitored(rule, season_number, item.air_date)
                    if rule is not None
                    else seasons[season_number].monitored
                )
                row = Episode(
                    series_id=series.id,
                    season_number=item.season_number,
                    episode_number=item.episode_number,
                    monitored=monitored,
                )
                session.add(row)
            row.title = item.title
            row.air_date = item.air_date
            row.overview = item.overview
            row.runtime = item.runtime
            any_monitored[season_number] = any_monitored.get(season_number, False) or row.monitored

    if rule is not None:  # a new series: a season is monitored if any of its episodes is
        for season_number, flag in any_monitored.items():
            seasons[season_number].monitored = flag

    for key, row in existing.items():
        if key not in seen:
            session.delete(row)
    series.last_refreshed_at = utcnow()
