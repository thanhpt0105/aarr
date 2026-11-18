import os
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from aarr.api.deps import SessionDep
from aarr.api.tmdb_dep import TmdbDep, metadata_http_error
from aarr.db import utcnow
from aarr.metadata.models import MetadataError, MovieDetails
from aarr.metadata.tmdb import poster_url
from aarr.models import Movie, QualityProfile, RootFolder
from aarr.security import require_api_key
from aarr.services.naming import movie_folder_name

router = APIRouter(
    prefix="/api/v1/movies", tags=["movies"], dependencies=[Depends(require_api_key)]
)


class MovieAdd(BaseModel):
    tmdb_id: int
    quality_profile_id: int
    root_folder_id: int
    monitored: bool = True


class MovieUpdate(BaseModel):
    monitored: bool | None = None
    quality_profile_id: int | None = None
    root_folder_id: int | None = None


class MovieOut(BaseModel):
    id: int
    tmdb_id: int
    imdb_id: str | None
    title: str
    original_title: str
    year: int | None
    overview: str
    poster_url: str | None
    status: str | None
    runtime: int | None
    in_cinemas: date | None
    digital_release: date | None
    physical_release: date | None
    monitored: bool
    quality_profile_id: int
    root_folder_id: int
    folder_name: str
    path: str
    added_at: datetime
    last_refreshed_at: datetime | None


def _out(movie: Movie) -> MovieOut:
    return MovieOut(
        id=movie.id,
        tmdb_id=movie.tmdb_id,
        imdb_id=movie.imdb_id,
        title=movie.title,
        original_title=movie.original_title,
        year=movie.year,
        overview=movie.overview,
        poster_url=poster_url(movie.poster_path),
        status=movie.status,
        runtime=movie.runtime,
        in_cinemas=movie.in_cinemas,
        digital_release=movie.digital_release,
        physical_release=movie.physical_release,
        monitored=movie.monitored,
        quality_profile_id=movie.quality_profile_id,
        root_folder_id=movie.root_folder_id,
        folder_name=movie.folder_name,
        path=os.path.join(movie.root_folder.path, movie.folder_name),
        added_at=movie.added_at,
        last_refreshed_at=movie.last_refreshed_at,
    )


def _get(session: Session, movie_id: int) -> Movie:
    movie = session.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie not found")
    return movie


def _check_refs(session: Session, profile_id: int | None, root_folder_id: int | None) -> None:
    if profile_id is not None and session.get(QualityProfile, profile_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quality profile not found")
    if root_folder_id is not None:
        folder = session.get(RootFolder, root_folder_id)
        if folder is None or folder.media_type != "movie":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Root folder not found for movies")


def _apply_details(movie: Movie, details: MovieDetails) -> None:
    movie.imdb_id = details.imdb_id
    movie.title = details.title
    movie.original_title = details.original_title
    movie.year = details.year
    movie.overview = details.overview
    movie.poster_path = details.poster_path
    movie.status = details.status
    movie.runtime = details.runtime
    movie.in_cinemas = details.in_cinemas
    movie.digital_release = details.digital_release
    movie.physical_release = details.physical_release


@router.get("")
def list_movies(session: SessionDep, monitored: bool | None = None) -> list[MovieOut]:
    query = select(Movie).order_by(Movie.title, Movie.id)
    if monitored is not None:
        query = query.where(Movie.monitored.is_(monitored))
    return [_out(m) for m in session.scalars(query)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_movie(body: MovieAdd, tmdb: TmdbDep, session: SessionDep) -> MovieOut:
    if session.scalar(select(Movie.id).where(Movie.tmdb_id == body.tmdb_id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Movie is already in the library")
    _check_refs(session, body.quality_profile_id, body.root_folder_id)
    try:
        details = await tmdb.movie(body.tmdb_id)
    except MetadataError as exc:
        raise metadata_http_error(exc) from exc

    movie = Movie(
        tmdb_id=body.tmdb_id,
        monitored=body.monitored,
        quality_profile_id=body.quality_profile_id,
        root_folder_id=body.root_folder_id,
        folder_name=movie_folder_name(details.title, details.year),
        last_refreshed_at=utcnow(),
    )
    _apply_details(movie, details)
    session.add(movie)
    session.commit()
    return _out(movie)


@router.get("/{movie_id}")
def get_movie(movie_id: int, session: SessionDep) -> MovieOut:
    return _out(_get(session, movie_id))


@router.patch("/{movie_id}")
def update_movie(movie_id: int, body: MovieUpdate, session: SessionDep) -> MovieOut:
    movie = _get(session, movie_id)
    _check_refs(session, body.quality_profile_id, body.root_folder_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(movie, field, value)
    session.commit()
    session.refresh(movie)
    return _out(movie)


@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movie(movie_id: int, session: SessionDep) -> None:
    session.delete(_get(session, movie_id))
    session.commit()


@router.post("/{movie_id}/refresh")
async def refresh_movie(movie_id: int, tmdb: TmdbDep, session: SessionDep) -> MovieOut:
    movie = _get(session, movie_id)
    try:
        details = await tmdb.movie(movie.tmdb_id)
    except MetadataError as exc:
        raise metadata_http_error(exc) from exc
    _apply_details(movie, details)  # folder_name is kept so existing files stay put
    movie.last_refreshed_at = utcnow()
    session.commit()
    return _out(movie)
