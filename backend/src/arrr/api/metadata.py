from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from arrr.api.deps import SessionDep
from arrr.api.tmdb_dep import TmdbDep, metadata_http_error
from arrr.metadata.models import MediaType, MetadataError
from arrr.metadata.tmdb import poster_url
from arrr.models import Movie
from arrr.security import require_api_key

router = APIRouter(
    prefix="/api/v1/metadata", tags=["metadata"], dependencies=[Depends(require_api_key)]
)


class HitOut(BaseModel):
    tmdb_id: int
    media_type: MediaType
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_url: str | None
    library_id: int | None  # id in the library when already added


@router.get("/search")
async def search_metadata(
    tmdb: TmdbDep,
    session: SessionDep,
    q: Annotated[str, Query(min_length=1)],
    type: MediaType = "movie",
    year: int | None = None,
) -> list[HitOut]:
    try:
        hits = (
            await tmdb.search_movies(q, year)
            if type == "movie"
            else await tmdb.search_series(q, year)
        )
    except MetadataError as exc:
        raise metadata_http_error(exc) from exc

    in_library: dict[int, int] = {}
    if type == "movie" and hits:
        rows = session.execute(
            select(Movie.tmdb_id, Movie.id).where(Movie.tmdb_id.in_([h.tmdb_id for h in hits]))
        )
        in_library = {tmdb_id: movie_id for tmdb_id, movie_id in rows}

    return [
        HitOut(
            tmdb_id=h.tmdb_id,
            media_type=h.media_type,
            title=h.title,
            original_title=h.original_title,
            year=h.year,
            overview=h.overview,
            poster_url=poster_url(h.poster_path),
            library_id=in_library.get(h.tmdb_id),
        )
        for h in hits
    ]
