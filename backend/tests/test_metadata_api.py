import httpx
import respx

from arrr.metadata.tmdb import BASE_URL


def configure(authed, key="k"):
    authed.put("/api/v1/settings/metadata", json={"tmdb_api_key": key})


def test_requires_api_key(client):
    assert client.get("/api/v1/metadata/search", params={"q": "x"}).status_code == 401


def test_search_without_key_is_400(authed):
    resp = authed.get("/api/v1/metadata/search", params={"q": "x"})
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"]


@respx.mock
def test_search_movie_and_tv(authed):
    configure(authed)
    movie = respx.get(f"{BASE_URL}/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": 1, "title": "M", "original_title": "M",
                               "release_date": "2020-01-02", "poster_path": "/m.jpg"}]},
        )
    )
    tv = respx.get(f"{BASE_URL}/search/tv").mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": 2, "name": "S", "original_name": "S"}]}
        )
    )

    [hit] = authed.get("/api/v1/metadata/search", params={"q": "m"}).json()
    assert hit == {
        "tmdb_id": 1, "media_type": "movie", "title": "M", "original_title": "M", "year": 2020,
        "overview": "", "poster_url": "https://image.tmdb.org/t/p/w342/m.jpg",
    }
    assert movie.call_count == 1 and tv.call_count == 0

    [hit] = authed.get("/api/v1/metadata/search", params={"q": "s", "type": "tv"}).json()
    assert (hit["tmdb_id"], hit["media_type"], hit["poster_url"]) == (2, "tv", None)


@respx.mock
def test_search_uses_configured_language(authed):
    authed.put(
        "/api/v1/settings/metadata", json={"tmdb_api_key": "k", "tmdb_language": "vi-VN"}
    )
    route = respx.get(f"{BASE_URL}/search/movie").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    authed.get("/api/v1/metadata/search", params={"q": "x"})
    assert route.calls.last.request.url.params["language"] == "vi-VN"


@respx.mock
def test_provider_failure_is_502(authed):
    configure(authed, "bad")
    respx.get(f"{BASE_URL}/search/movie").mock(return_value=httpx.Response(401))
    resp = authed.get("/api/v1/metadata/search", params={"q": "x"})
    assert resp.status_code == 502
    assert "rejected the API key" in resp.json()["detail"]


def test_validates_parameters(authed):
    configure(authed)
    assert authed.get("/api/v1/metadata/search").status_code == 422
    assert authed.get("/api/v1/metadata/search", params={"q": ""}).status_code == 422
    assert authed.get("/api/v1/metadata/search", params={"q": "x", "type": "x"}).status_code == 422


@respx.mock
def test_settings_key_test_endpoint(authed):
    assert authed.post("/api/v1/settings/metadata/test").json() == {
        "ok": False, "error": "TMDB API key is not configured",
    }
    configure(authed)
    respx.get(f"{BASE_URL}/authentication").mock(return_value=httpx.Response(401))
    bad = authed.post("/api/v1/settings/metadata/test").json()
    assert bad["ok"] is False and "rejected" in bad["error"]

    respx.get(f"{BASE_URL}/authentication").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    assert authed.post("/api/v1/settings/metadata/test").json() == {"ok": True, "error": None}
