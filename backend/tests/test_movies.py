from datetime import UTC

import httpx
import pytest
import respx

from aarr.metadata.tmdb import BASE_URL

MOVIES = "/api/v1/movies"
DETAILS = {
    "id": 27205,
    "imdb_id": "tt1375666",
    "title": "Inception",
    "original_title": "Inception",
    "release_date": "2010-07-16",
    "overview": "Dreams.",
    "poster_path": "/p.jpg",
    "status": "Released",
    "runtime": 148,
    "release_dates": {
        "results": [
            {
                "iso_3166_1": "US",
                "release_dates": [{"type": 4, "release_date": "2010-12-07T00:00:00.000Z"}],
            }
        ]
    },
}


@pytest.fixture
def lib(authed, tmp_path):
    """A configured TMDB key, one movie root folder, and the seeded HD profile."""
    authed.put("/api/v1/settings/metadata", json={"tmdb_api_key": "k"})
    root = tmp_path / "movies"
    root.mkdir()
    folder = authed.post("/api/v1/root-folders", json={"path": str(root), "media_type": "movie"})
    tv_root = tmp_path / "tv"
    tv_root.mkdir()
    tv = authed.post("/api/v1/root-folders", json={"path": str(tv_root), "media_type": "tv"})
    profile_id = authed.get("/api/v1/quality-profiles").json()[1]["id"]
    authed.lib = {
        "root": folder.json(),
        "tv_root": tv.json(),
        "profile_id": profile_id,
        "body": {
            "tmdb_id": 27205,
            "quality_profile_id": profile_id,
            "root_folder_id": folder.json()["id"],
        },
    }
    return authed


def mock_details(tmdb_id=27205, **overrides):
    return respx.get(f"{BASE_URL}/movie/{tmdb_id}").mock(
        return_value=httpx.Response(200, json=DETAILS | overrides)
    )


def test_requires_api_key(client):
    assert client.get(MOVIES).status_code == 401


@respx.mock
def test_add_movie_populates_metadata_and_path(lib):
    mock_details()
    resp = lib.post(MOVIES, json=lib.lib["body"])
    assert resp.status_code == 201
    m = resp.json()
    assert (m["title"], m["year"], m["imdb_id"], m["runtime"]) == (
        "Inception",
        2010,
        "tt1375666",
        148,
    )
    assert m["digital_release"] == "2010-12-07" and m["in_cinemas"] == "2010-07-16"
    assert m["poster_url"] == "https://image.tmdb.org/t/p/w342/p.jpg"
    assert m["monitored"] is True and m["folder_name"] == "Inception (2010)"
    assert m["path"].endswith("Inception (2010)")
    assert m["path"].startswith(lib.lib["root"]["path"])
    assert m["added_at"].endswith("Z") or m["added_at"].endswith("+00:00")
    assert lib.get(f"{MOVIES}/{m['id']}").json() == m
    assert lib.get(MOVIES).json() == [m]


@respx.mock
def test_added_at_is_stored_as_utc(lib):
    mock_details()
    lib.post(MOVIES, json=lib.lib["body"])
    from sqlalchemy import select

    from aarr.models import Movie

    with lib.app.state.db.open_session() as s:
        movie = s.scalar(select(Movie))
    assert movie.added_at.tzinfo is UTC


@respx.mock
def test_duplicate_is_409_without_calling_tmdb(lib):
    route = mock_details()
    assert lib.post(MOVIES, json=lib.lib["body"]).status_code == 201
    assert lib.post(MOVIES, json=lib.lib["body"]).status_code == 409
    assert route.call_count == 1


@respx.mock
def test_folder_name_is_filesystem_safe(lib):
    mock_details(title="Mission: Impossible", release_date="1996-05-22")
    m = lib.post(MOVIES, json=lib.lib["body"]).json()
    assert m["folder_name"] == "Mission - Impossible (1996)"


@respx.mock
def test_add_validates_references(lib):
    body = lib.lib["body"]
    route = mock_details()
    assert lib.post(MOVIES, json=body | {"quality_profile_id": 999}).status_code == 400
    assert lib.post(MOVIES, json=body | {"root_folder_id": 999}).status_code == 400
    tv_id = lib.lib["tv_root"]["id"]
    assert lib.post(MOVIES, json=body | {"root_folder_id": tv_id}).status_code == 400
    assert route.call_count == 0


@respx.mock
def test_add_tmdb_errors(lib):
    respx.get(f"{BASE_URL}/movie/1").mock(return_value=httpx.Response(404))
    assert lib.post(MOVIES, json=lib.lib["body"] | {"tmdb_id": 1}).status_code == 404
    respx.get(f"{BASE_URL}/movie/2").mock(return_value=httpx.Response(401))
    assert lib.post(MOVIES, json=lib.lib["body"] | {"tmdb_id": 2}).status_code == 502
    assert lib.get(MOVIES).json() == []


def test_add_without_tmdb_key_is_400(authed):
    resp = authed.post(MOVIES, json={"tmdb_id": 1, "quality_profile_id": 1, "root_folder_id": 1})
    assert resp.status_code == 400


@respx.mock
def test_update_partial_and_filter(lib):
    mock_details()
    movie = lib.post(MOVIES, json=lib.lib["body"]).json()
    uhd = lib.get("/api/v1/quality-profiles").json()[2]["id"]

    resp = lib.patch(
        f"{MOVIES}/{movie['id']}", json={"monitored": False, "quality_profile_id": uhd}
    )
    assert resp.status_code == 200
    assert (resp.json()["monitored"], resp.json()["quality_profile_id"]) == (False, uhd)
    assert resp.json()["root_folder_id"] == movie["root_folder_id"]  # untouched

    assert lib.get(MOVIES, params={"monitored": True}).json() == []
    assert len(lib.get(MOVIES, params={"monitored": False}).json()) == 1

    assert lib.patch(f"{MOVIES}/{movie['id']}", json={"quality_profile_id": 999}).status_code == 400
    assert lib.patch(f"{MOVIES}/999", json={"monitored": True}).status_code == 404


@respx.mock
def test_refresh_updates_metadata_but_keeps_folder(lib):
    mock_details()
    movie = lib.post(MOVIES, json=lib.lib["body"]).json()
    respx.get(f"{BASE_URL}/movie/27205").mock(
        return_value=httpx.Response(
            200, json=DETAILS | {"title": "Inception Renamed", "runtime": 150}
        )
    )
    refreshed = lib.post(f"{MOVIES}/{movie['id']}/refresh").json()
    assert (refreshed["title"], refreshed["runtime"]) == ("Inception Renamed", 150)
    assert refreshed["folder_name"] == "Inception (2010)"
    assert refreshed["last_refreshed_at"] >= movie["last_refreshed_at"]
    assert lib.post(f"{MOVIES}/999/refresh").status_code == 404


@respx.mock
def test_delete_and_in_use_protection(lib):
    mock_details()
    movie = lib.post(MOVIES, json=lib.lib["body"]).json()

    profile = lib.delete(f"/api/v1/quality-profiles/{lib.lib['profile_id']}")
    folder = lib.delete(f"/api/v1/root-folders/{lib.lib['root']['id']}")
    assert profile.status_code == 409 and folder.status_code == 409

    assert lib.delete(f"{MOVIES}/{movie['id']}").status_code == 204
    assert lib.get(f"{MOVIES}/{movie['id']}").status_code == 404
    assert lib.delete(f"{MOVIES}/{movie['id']}").status_code == 404
    assert lib.delete(f"/api/v1/quality-profiles/{lib.lib['profile_id']}").status_code == 204


@respx.mock
def test_search_flags_movies_already_in_library(lib):
    mock_details()
    movie = lib.post(MOVIES, json=lib.lib["body"]).json()
    respx.get(f"{BASE_URL}/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 27205, "title": "Inception", "original_title": "Inception"},
                    {"id": 1, "title": "Other", "original_title": "Other"},
                ]
            },
        )
    )
    hits = lib.get("/api/v1/metadata/search", params={"q": "inception"}).json()
    assert [(h["tmdb_id"], h["library_id"]) for h in hits] == [(27205, movie["id"]), (1, None)]
