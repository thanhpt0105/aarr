from datetime import date, timedelta

import httpx
import pytest
import respx

from arrr.metadata.tmdb import BASE_URL

SERIES = "/api/v1/series"
TV_ID = 5
FUTURE = (date.today() + timedelta(days=30)).isoformat()


def series_json(**overrides):
    return {
        "id": TV_ID,
        "name": "The Show",
        "original_name": "The Show",
        "first_air_date": "2019-03-01",
        "overview": "o",
        "poster_path": "/s.jpg",
        "status": "Returning Series",
        "external_ids": {"imdb_id": "tt9", "tvdb_id": 99},
        "seasons": [
            {"season_number": 0, "episode_count": 1, "air_date": None},
            {"season_number": 1, "episode_count": 2, "air_date": "2019-03-01"},
            {"season_number": 2, "episode_count": 2, "air_date": "2020-03-01"},
        ],
    } | overrides


SEASONS = {
    0: [{"episode_number": 1, "name": "Special", "air_date": "2019-01-01"}],
    1: [
        {"episode_number": 1, "name": "Pilot", "air_date": "2019-03-01", "runtime": 45},
        {"episode_number": 2, "name": "Two", "air_date": "2019-03-08"},
    ],
    2: [
        {"episode_number": 1, "name": "Return", "air_date": "2020-03-01"},
        {"episode_number": 2, "name": "Upcoming", "air_date": FUTURE},
    ],
}


def mock_tv(series=None, seasons=None):
    route = respx.get(f"{BASE_URL}/tv/{TV_ID}").mock(
        return_value=httpx.Response(200, json=series or series_json())
    )
    for number, episodes in (seasons or SEASONS).items():
        respx.get(f"{BASE_URL}/tv/{TV_ID}/season/{number}").mock(
            return_value=httpx.Response(200, json={"episodes": episodes})
        )
    return route


@pytest.fixture
def lib(authed, tmp_path):
    authed.put("/api/v1/settings/metadata", json={"tmdb_api_key": "k"})
    tv_root = tmp_path / "tv"
    tv_root.mkdir()
    movie_root = tmp_path / "movies"
    movie_root.mkdir()
    tv = authed.post("/api/v1/root-folders", json={"path": str(tv_root), "media_type": "tv"})
    movie = authed.post(
        "/api/v1/root-folders", json={"path": str(movie_root), "media_type": "movie"}
    )
    profile_id = authed.get("/api/v1/quality-profiles").json()[1]["id"]
    authed.lib = {
        "tv_root": tv.json(),
        "movie_root": movie.json(),
        "profile_id": profile_id,
        "body": {
            "tmdb_id": TV_ID,
            "quality_profile_id": profile_id,
            "root_folder_id": tv.json()["id"],
        },
    }
    return authed


def episodes(lib, series_id, **params):
    return lib.get(f"{SERIES}/{series_id}/episodes", params=params).json()


def test_requires_api_key(client):
    assert client.get(SERIES).status_code == 401


@respx.mock
def test_add_series_imports_seasons_and_episodes(lib):
    mock_tv()
    resp = lib.post(SERIES, json=lib.lib["body"])
    assert resp.status_code == 201
    s = resp.json()
    assert (s["title"], s["year"], s["imdb_id"], s["tvdb_id"]) == ("The Show", 2019, "tt9", 99)
    assert s["folder_name"] == "The Show (2019)" and s["path"].endswith("The Show (2019)")
    assert s["poster_url"] == "https://image.tmdb.org/t/p/w342/s.jpg"
    assert (s["season_count"], s["episode_count"]) == (2, 4)  # specials excluded from counts
    assert [x["season_number"] for x in s["seasons"]] == [0, 1, 2]

    eps = episodes(lib, s["id"])
    assert [(e["season_number"], e["episode_number"]) for e in eps] == [
        (0, 1), (1, 1), (1, 2), (2, 1), (2, 2),
    ]  # fmt: skip
    pilot = eps[1]
    assert (pilot["title"], pilot["air_date"], pilot["runtime"]) == ("Pilot", "2019-03-01", 45)
    assert lib.get(f"{SERIES}/{s['id']}").json() == s
    assert [x["id"] for x in lib.get(SERIES).json()] == [s["id"]]


@respx.mock
def test_monitor_all_skips_specials(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"] | {"monitor": "all"}).json()
    monitored = {
        (e["season_number"], e["episode_number"]): e["monitored"] for e in episodes(lib, s["id"])
    }
    assert monitored == {
        (0, 1): False, (1, 1): True, (1, 2): True, (2, 1): True, (2, 2): True,
    }  # fmt: skip
    assert s["monitored"] is True
    assert [(x["season_number"], x["monitored"]) for x in s["seasons"]] == [
        (0, False), (1, True), (2, True),
    ]  # fmt: skip


@respx.mock
def test_monitor_future_only(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"] | {"monitor": "future"}).json()
    monitored = {
        (e["season_number"], e["episode_number"]): e["monitored"] for e in episodes(lib, s["id"])
    }
    assert monitored == {
        (0, 1): False, (1, 1): False, (1, 2): False, (2, 1): False, (2, 2): True,
    }  # fmt: skip
    # Season 1 has nothing monitored; season 2 has the upcoming episode.
    seasons = [
        (x["season_number"], x["monitored"], x["monitored_episode_count"]) for x in s["seasons"]
    ]
    assert seasons == [(0, False, 0), (1, False, 0), (2, True, 1)]


@respx.mock
def test_monitor_none(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"] | {"monitor": "none"}).json()
    assert s["monitored"] is False
    assert not any(e["monitored"] for e in episodes(lib, s["id"]))


@respx.mock
def test_season_without_tmdb_data_is_tolerated(lib):
    mock_tv()
    respx.get(f"{BASE_URL}/tv/{TV_ID}/season/2").mock(return_value=httpx.Response(404))
    s = lib.post(SERIES, json=lib.lib["body"]).json()
    assert s["episode_count"] == 2
    assert [x["episode_count"] for x in s["seasons"]] == [1, 2, 0]


@respx.mock
def test_duplicate_and_validation_and_errors(lib):
    route = mock_tv()
    body = lib.lib["body"]
    assert lib.post(SERIES, json=body).status_code == 201
    assert lib.post(SERIES, json=body).status_code == 409

    assert (
        lib.post(SERIES, json=body | {"tmdb_id": 6, "quality_profile_id": 999}).status_code == 400
    )
    assert lib.post(SERIES, json=body | {"tmdb_id": 6, "root_folder_id": 999}).status_code == 400
    movie_root = lib.lib["movie_root"]["id"]
    assert (
        lib.post(SERIES, json=body | {"tmdb_id": 6, "root_folder_id": movie_root}).status_code
        == 400
    )
    assert lib.post(SERIES, json=body | {"monitor": "bogus"}).status_code == 422

    respx.get(f"{BASE_URL}/tv/404").mock(return_value=httpx.Response(404))
    assert lib.post(SERIES, json=body | {"tmdb_id": 404}).status_code == 404
    respx.get(f"{BASE_URL}/tv/401").mock(return_value=httpx.Response(401))
    assert lib.post(SERIES, json=body | {"tmdb_id": 401}).status_code == 502
    assert len(lib.get(SERIES).json()) == 1
    assert route.call_count == 1


@respx.mock
def test_episode_and_season_monitoring(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"]).json()
    eps = {(e["season_number"], e["episode_number"]): e for e in episodes(lib, s["id"])}

    resp = lib.patch(f"{SERIES}/{s['id']}/episodes/{eps[(1, 1)]['id']}", json={"monitored": False})
    assert resp.status_code == 200 and resp.json()["monitored"] is False
    detail = lib.get(f"{SERIES}/{s['id']}").json()
    assert detail["seasons"][1]["monitored_episode_count"] == 1

    season = lib.patch(f"{SERIES}/{s['id']}/seasons/1", json={"monitored": False}).json()
    assert (season["monitored"], season["monitored_episode_count"], season["episode_count"]) == (
        False, 0, 2,
    )  # fmt: skip
    assert [e["monitored"] for e in episodes(lib, s["id"], season=1)] == [False, False]
    assert [e["monitored"] for e in episodes(lib, s["id"], season=2)] == [True, True]

    lib.patch(f"{SERIES}/{s['id']}/seasons/0", json={"monitored": True})
    assert episodes(lib, s["id"], season=0)[0]["monitored"] is True

    assert lib.patch(f"{SERIES}/{s['id']}/seasons/9", json={"monitored": True}).status_code == 404
    assert lib.patch(f"{SERIES}/999/seasons/1", json={"monitored": True}).status_code == 404
    assert (
        lib.patch(f"{SERIES}/{s['id']}/episodes/999999", json={"monitored": True}).status_code
        == 404
    )
    assert lib.get(f"{SERIES}/999/episodes").status_code == 404


@respx.mock
def test_episode_must_belong_to_series(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"]).json()
    episode_id = episodes(lib, s["id"])[0]["id"]
    assert (
        lib.patch(f"{SERIES}/999/episodes/{episode_id}", json={"monitored": True}).status_code
        == 404
    )


@respx.mock
def test_update_delete_cascade_and_in_use(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"]).json()
    uhd = lib.get("/api/v1/quality-profiles").json()[2]["id"]

    resp = lib.patch(f"{SERIES}/{s['id']}", json={"monitored": False, "quality_profile_id": uhd})
    assert resp.status_code == 200
    assert (resp.json()["monitored"], resp.json()["quality_profile_id"]) == (False, uhd)
    assert (
        lib.patch(
            f"{SERIES}/{s['id']}", json={"root_folder_id": lib.lib["movie_root"]["id"]}
        ).status_code
        == 400
    )
    assert lib.get(SERIES, params={"monitored": True}).json() == []

    assert lib.delete(f"/api/v1/root-folders/{lib.lib['tv_root']['id']}").status_code == 409
    assert lib.delete(f"{SERIES}/{s['id']}").status_code == 204
    assert lib.get(f"{SERIES}/{s['id']}").status_code == 404
    assert lib.delete(f"{SERIES}/{s['id']}").status_code == 404

    from sqlalchemy import func, select

    from arrr.models import Episode, Season

    with lib.app.state.db.open_session() as session:
        assert session.scalar(select(func.count()).select_from(Episode)) == 0
        assert session.scalar(select(func.count()).select_from(Season)) == 0


@respx.mock
def test_refresh_keeps_choices_and_syncs_changes(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"]).json()
    eps = {(e["season_number"], e["episode_number"]): e for e in episodes(lib, s["id"])}
    lib.patch(f"{SERIES}/{s['id']}/episodes/{eps[(1, 1)]['id']}", json={"monitored": False})
    lib.patch(f"{SERIES}/{s['id']}/seasons/2", json={"monitored": False})

    changed_seasons = {
        **SEASONS,
        1: [
            {"episode_number": 1, "name": "Pilot (renamed)", "air_date": "2019-03-01"},
            {"episode_number": 3, "name": "Brand new", "air_date": "2019-03-15"},
        ],  # episode 2 disappeared upstream
        2: SEASONS[2] + [{"episode_number": 3, "name": "Added later", "air_date": FUTURE}],
    }
    changed_series = series_json(
        name="The Show Renamed",
        seasons=series_json()["seasons"] + [{"season_number": 3, "episode_count": 1}],
    )
    mock_tv(changed_series, changed_seasons | {3: [{"episode_number": 1, "name": "S3E1"}]})

    refreshed = lib.post(f"{SERIES}/{s['id']}/refresh")
    assert refreshed.status_code == 200
    data = refreshed.json()
    assert data["title"] == "The Show Renamed"
    assert data["folder_name"] == "The Show (2019)"  # unchanged so files stay put

    after = {(e["season_number"], e["episode_number"]): e for e in episodes(lib, s["id"])}
    assert after[(1, 1)]["title"] == "Pilot (renamed)"
    assert after[(1, 1)]["monitored"] is False  # user's choice preserved
    assert (1, 2) not in after  # removed upstream
    assert after[(1, 3)]["monitored"] is True  # new episode inherits season 1 (monitored)
    assert after[(2, 3)]["monitored"] is False  # season 2 was switched off
    assert after[(3, 1)]["monitored"] is True  # new season follows the series flag
    assert [x["season_number"] for x in data["seasons"]] == [0, 1, 2, 3]
    assert lib.post(f"{SERIES}/999/refresh").status_code == 404


@respx.mock
def test_search_flags_series_in_library(lib):
    mock_tv()
    s = lib.post(SERIES, json=lib.lib["body"]).json()
    respx.get(f"{BASE_URL}/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": TV_ID, "name": "The Show", "original_name": "The Show"},
                    {"id": 77, "name": "Other", "original_name": "Other"},
                ]
            },
        )
    )
    hits = lib.get("/api/v1/metadata/search", params={"q": "show", "type": "tv"}).json()
    assert [(h["tmdb_id"], h["library_id"]) for h in hits] == [(TV_ID, s["id"]), (77, None)]
