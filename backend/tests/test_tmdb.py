from datetime import date

import httpx
import pytest
import respx

from arrr.metadata.models import MetadataError, MetadataNotFound
from arrr.metadata.tmdb import BASE_URL, TmdbClient, poster_url

JWT = "eyJhbGciOiJIUzI1NiJ9." + "a" * 40 + ".sig"


@pytest.fixture
async def tmdb():
    c = TmdbClient("v3key", "vi-VN")
    yield c
    await c.aclose()


@respx.mock
async def test_v3_key_sent_as_query_param(tmdb):
    route = respx.get(f"{BASE_URL}/authentication").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    await tmdb.test()
    req = route.calls.last.request
    assert req.url.params["api_key"] == "v3key" and req.url.params["language"] == "vi-VN"
    assert "authorization" not in req.headers


@respx.mock
async def test_v4_read_token_sent_as_bearer():
    c = TmdbClient(JWT)
    route = respx.get(f"{BASE_URL}/authentication").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    await c.test()
    req = route.calls.last.request
    assert req.headers["authorization"] == f"Bearer {JWT}"
    assert "api_key" not in req.url.params
    await c.aclose()


@respx.mock
async def test_search_movies(tmdb):
    route = respx.get(f"{BASE_URL}/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={"results": [
                {"id": 27205, "title": "Inception", "original_title": "Inception",
                 "release_date": "2010-07-15", "overview": "Dreams.", "poster_path": "/p.jpg"},
                {"id": 1, "title": "No Date", "original_title": "No Date", "release_date": ""},
            ]},
        )
    )
    hits = await tmdb.search_movies("inception", year=2010)
    assert route.calls.last.request.url.params["query"] == "inception"
    assert route.calls.last.request.url.params["year"] == "2010"
    assert (hits[0].tmdb_id, hits[0].media_type, hits[0].year) == (27205, "movie", 2010)
    assert hits[1].year is None and hits[1].poster_path is None
    assert poster_url(hits[0].poster_path) == "https://image.tmdb.org/t/p/w342/p.jpg"
    assert poster_url(None) is None


@respx.mock
async def test_search_series_uses_tv_fields(tmdb):
    route = respx.get(f"{BASE_URL}/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": 5, "name": "Show", "original_name": "Orig",
                               "first_air_date": "2019-03-01", "overview": ""}]},
        )
    )
    [hit] = await tmdb.search_series("show", year=2019)
    assert route.calls.last.request.url.params["first_air_date_year"] == "2019"
    assert (hit.title, hit.original_title, hit.year, hit.media_type) == ("Show", "Orig", 2019, "tv")


@respx.mock
async def test_movie_details_picks_earliest_release_per_kind(tmdb):
    respx.get(f"{BASE_URL}/movie/27205").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 27205, "imdb_id": "tt1375666", "title": "Inception",
                "original_title": "Inception", "release_date": "2010-07-16",
                "overview": "x", "poster_path": "/p.jpg", "status": "Released", "runtime": 148,
                "release_dates": {"results": [
                    {"iso_3166_1": "US", "release_dates": [
                        {"type": 3, "release_date": "2010-07-16T00:00:00.000Z"},
                        {"type": 4, "release_date": "2010-12-07T00:00:00.000Z"},
                        {"type": 5, "release_date": "2010-12-07T00:00:00.000Z"},
                    ]},
                    {"iso_3166_1": "FR", "release_dates": [
                        {"type": 3, "release_date": "2010-07-21T00:00:00.000Z"},
                        {"type": 4, "release_date": "2010-11-30T00:00:00.000Z"},
                        {"type": 1, "release_date": "2010-07-01T00:00:00.000Z"},  # premiere ignored
                        {"type": 5, "release_date": ""},
                    ]},
                ]},
            },
        )
    )
    m = await tmdb.movie(27205)
    assert (m.imdb_id, m.title, m.year, m.runtime, m.status) == (
        "tt1375666", "Inception", 2010, 148, "Released",
    )
    assert m.in_cinemas == date(2010, 7, 16)
    assert m.digital_release == date(2010, 11, 30)
    assert m.physical_release == date(2010, 12, 7)


@respx.mock
async def test_movie_without_release_dates_falls_back(tmdb):
    respx.get(f"{BASE_URL}/movie/9").mock(
        return_value=httpx.Response(
            200, json={"id": 9, "title": "T", "release_date": "2021-05-05", "imdb_id": ""}
        )
    )
    m = await tmdb.movie(9)
    assert m.in_cinemas == date(2021, 5, 5)
    assert m.digital_release is None and m.imdb_id is None and m.runtime is None


@respx.mock
async def test_series_and_episodes(tmdb):
    respx.get(f"{BASE_URL}/tv/5").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 5, "name": "Show", "original_name": "Show", "first_air_date": "2019-03-01",
                "overview": "o", "poster_path": None, "status": "Returning Series",
                "external_ids": {"imdb_id": "tt1", "tvdb_id": 99},
                "seasons": [
                    {"season_number": 0, "episode_count": 2, "air_date": None},
                    {"season_number": 1, "episode_count": 10, "air_date": "2019-03-01"},
                ],
            },
        )
    )
    respx.get(f"{BASE_URL}/tv/5/season/1").mock(
        return_value=httpx.Response(
            200,
            json={"episodes": [
                {"episode_number": 1, "name": "Pilot", "air_date": "2019-03-01", "runtime": 45},
                {"episode_number": 2, "name": "TBA", "air_date": None, "runtime": 0},
            ]},
        )
    )
    s = await tmdb.series(5)
    assert (s.imdb_id, s.tvdb_id, s.year, s.status) == ("tt1", 99, 2019, "Returning Series")
    assert [(x.season_number, x.episode_count) for x in s.seasons] == [(0, 2), (1, 10)]
    assert s.seasons[0].air_date is None

    eps = await tmdb.season_episodes(5, 1)
    assert [(e.season_number, e.episode_number, e.title) for e in eps] == [
        (1, 1, "Pilot"), (1, 2, "TBA"),
    ]
    assert eps[0].air_date == date(2019, 3, 1) and eps[0].runtime == 45
    assert eps[1].air_date is None and eps[1].runtime is None


@respx.mock
@pytest.mark.parametrize(
    ("status_code", "exc", "text"),
    [
        (401, MetadataError, "rejected the API key"),
        (404, MetadataNotFound, "Not found"),
        (429, MetadataError, "rate limit"),
        (500, MetadataError, "500"),
    ],
)
async def test_http_errors(tmdb, status_code, exc, text):
    respx.get(f"{BASE_URL}/movie/1").mock(return_value=httpx.Response(status_code))
    with pytest.raises(exc, match=text):
        await tmdb.movie(1)


@respx.mock
async def test_network_and_invalid_json_errors(tmdb):
    respx.get(f"{BASE_URL}/movie/1").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(MetadataError, match="unreachable"):
        await tmdb.movie(1)

    respx.get(f"{BASE_URL}/movie/2").mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(MetadataError, match="invalid response"):
        await tmdb.movie(2)
