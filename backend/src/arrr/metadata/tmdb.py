from datetime import date
from typing import Any

import httpx

from arrr.metadata.models import (
    EpisodeDetails,
    MetadataError,
    MetadataHit,
    MetadataNotFound,
    MovieDetails,
    SeasonSummary,
    SeriesDetails,
)

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"

# TMDB release_dates types: 2/3 theatrical, 4 digital, 5 physical
_RELEASE_KIND = {2: "cinema", 3: "cinema", 4: "digital", 5: "physical"}


def poster_url(poster_path: str | None) -> str | None:
    return f"{IMAGE_BASE}{poster_path}" if poster_path else None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def _year(value: str | None) -> int | None:
    parsed = _date(value)
    return parsed.year if parsed else None


def _is_read_token(key: str) -> bool:
    """v4 'API Read Access Token' is a JWT; a v3 key is a short hex string."""
    return key.count(".") == 2 and len(key) > 40


class TmdbClient:
    def __init__(
        self,
        api_key: str,
        language: str = "en-US",
        *,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if _is_read_token(api_key) else {}
        self._params = {} if headers else {"api_key": api_key}
        self._language = language
        self._http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout)

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        query = {**self._params, "language": self._language}
        query.update({k: v for k, v in params.items() if v is not None})
        try:
            resp = await self._http.get(path, params=query)
        except httpx.HTTPError as exc:
            raise MetadataError(f"TMDB unreachable: {exc}") from exc
        if resp.status_code == 401:
            raise MetadataError("TMDB rejected the API key")
        if resp.status_code == 404:
            raise MetadataNotFound("Not found on TMDB")
        if resp.status_code == 429:
            raise MetadataError("TMDB rate limit reached; try again shortly")
        if resp.status_code >= 400:
            raise MetadataError(f"TMDB returned {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise MetadataError("TMDB returned an invalid response") from exc

    async def test(self) -> None:
        await self._get("/authentication")

    async def search_movies(self, query: str, year: int | None = None) -> list[MetadataHit]:
        data = await self._get("/search/movie", query=query, year=year)
        return [
            MetadataHit(
                tmdb_id=r["id"],
                media_type="movie",
                title=r.get("title", ""),
                original_title=r.get("original_title", ""),
                year=_year(r.get("release_date")),
                overview=r.get("overview", ""),
                poster_path=r.get("poster_path"),
            )
            for r in data.get("results", [])
        ]

    async def search_series(self, query: str, year: int | None = None) -> list[MetadataHit]:
        data = await self._get("/search/tv", query=query, first_air_date_year=year)
        return [
            MetadataHit(
                tmdb_id=r["id"],
                media_type="tv",
                title=r.get("name", ""),
                original_title=r.get("original_name", ""),
                year=_year(r.get("first_air_date")),
                overview=r.get("overview", ""),
                poster_path=r.get("poster_path"),
            )
            for r in data.get("results", [])
        ]

    async def movie(self, tmdb_id: int) -> MovieDetails:
        r = await self._get(f"/movie/{tmdb_id}", append_to_response="release_dates")
        earliest: dict[str, date] = {}
        for country in r.get("release_dates", {}).get("results", []):
            for rel in country.get("release_dates", []):
                when = _date(rel.get("release_date"))
                if when is None:
                    continue
                kind = _RELEASE_KIND.get(rel.get("type"))
                if kind and (kind not in earliest or when < earliest[kind]):
                    earliest[kind] = when
        return MovieDetails(
            tmdb_id=r["id"],
            imdb_id=r.get("imdb_id") or None,
            title=r.get("title", ""),
            original_title=r.get("original_title", ""),
            year=_year(r.get("release_date")),
            overview=r.get("overview", ""),
            poster_path=r.get("poster_path"),
            status=r.get("status"),
            runtime=r.get("runtime") or None,
            in_cinemas=earliest.get("cinema") or _date(r.get("release_date")),
            digital_release=earliest.get("digital"),
            physical_release=earliest.get("physical"),
        )

    async def series(self, tmdb_id: int) -> SeriesDetails:
        r = await self._get(f"/tv/{tmdb_id}", append_to_response="external_ids")
        ext = r.get("external_ids") or {}
        return SeriesDetails(
            tmdb_id=r["id"],
            imdb_id=ext.get("imdb_id") or None,
            tvdb_id=ext.get("tvdb_id") or None,
            title=r.get("name", ""),
            original_title=r.get("original_name", ""),
            year=_year(r.get("first_air_date")),
            overview=r.get("overview", ""),
            poster_path=r.get("poster_path"),
            status=r.get("status"),
            first_air_date=_date(r.get("first_air_date")),
            seasons=tuple(
                SeasonSummary(
                    season_number=s["season_number"],
                    episode_count=s.get("episode_count", 0),
                    air_date=_date(s.get("air_date")),
                )
                for s in r.get("seasons", [])
            ),
        )

    async def season_episodes(self, tmdb_id: int, season_number: int) -> list[EpisodeDetails]:
        r = await self._get(f"/tv/{tmdb_id}/season/{season_number}")
        return [
            EpisodeDetails(
                season_number=season_number,
                episode_number=e["episode_number"],
                title=e.get("name", ""),
                air_date=_date(e.get("air_date")),
                overview=e.get("overview", ""),
                runtime=e.get("runtime") or None,
            )
            for e in r.get("episodes", [])
        ]

    async def aclose(self) -> None:
        await self._http.aclose()
