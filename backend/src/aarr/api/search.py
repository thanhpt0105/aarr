from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from aarr.indexers.models import Release, SearchKind, SearchQuery
from aarr.security import require_api_key
from aarr.services.parser import ParsedRelease, parse_release
from aarr.services.search import search_all

router = APIRouter(
    prefix="/api/v1/search", tags=["search"], dependencies=[Depends(require_api_key)]
)


class ParsedOut(BaseModel):
    title: str
    year: int | None
    season: int | None
    episodes: list[int]
    season_pack: bool
    air_date: date | None
    resolution: int | None
    source: str | None
    codec: str | None
    group: str | None
    revision: int
    languages: list[str]


class ReleaseOut(BaseModel):
    indexer: str
    title: str
    guid: str
    download_url: str
    protocol: str
    size: int
    published: datetime | None
    seeders: int | None
    leechers: int | None
    infohash: str | None
    info_url: str | None
    categories: list[int]
    parsed: ParsedOut


class SearchOut(BaseModel):
    releases: list[ReleaseOut]
    errors: dict[str, str]


def _release_out(release: Release) -> ReleaseOut:
    parsed: ParsedRelease = parse_release(release.title)
    return ReleaseOut(**asdict(release), parsed=ParsedOut(**asdict(parsed)))


@router.get("")
async def search(
    request: Request,
    q: str | None = None,
    kind: SearchKind = "search",
    season: int | None = None,
    episode: int | None = None,
    imdb_id: str | None = None,
    tmdb_id: int | None = None,
    tvdb_id: int | None = None,
    indexer_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SearchOut:
    query = SearchQuery(
        kind=kind,
        q=q,
        season=season,
        episode=episode,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        limit=limit,
    )
    result = await search_all(request.app.state.db, request.app.state.secrets, query, indexer_id)
    return SearchOut(releases=[_release_out(r) for r in result.releases], errors=result.errors)
