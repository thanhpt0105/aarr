import httpx
import respx

A = "http://a.test/api"
B = "http://b.test/api"


def feed(*items: tuple[str, str, int | None]) -> str:
    body = "".join(
        f"<item><title>{title}</title><guid>{guid}</guid><link>http://dl/{guid}</link>"
        + (f'<torznab:attr name="seeders" value="{seeders}"/>' if seeders is not None else "")
        + "</item>"
        for title, guid, seeders in items
    )
    return (
        '<rss xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel>'
        + body
        + "</channel></rss>"
    )


def add(authed, name, url, **extra):
    body = {"name": name, "protocol": "torrent", "url": url} | extra
    return authed.post("/api/v1/indexers", json=body).json()["id"]


def test_requires_api_key(client):
    assert client.get("/api/v1/search").status_code == 401


def test_no_indexers_returns_empty(authed):
    assert authed.get("/api/v1/search", params={"q": "x"}).json() == {"releases": [], "errors": {}}


@respx.mock
def test_aggregates_sorts_dedupes_and_parses(authed):
    add(authed, "a", A)
    add(authed, "b", B, priority=1)
    respx.get(A).mock(
        return_value=httpx.Response(
            200,
            text=feed(
                ("Show.S01E01.1080p.WEB-DL.x264-GRP", "a1", 5),
                ("Show.S01E01.720p.HDTV.x264-GRP", "a2", 50),
                ("Show.S01E01.1080p.WEB-DL.x264-GRP", "a1", 5),  # duplicate guid
            ),
        )
    )
    respx.get(B).mock(
        return_value=httpx.Response(
            200,
            text=feed(
                ("Show.S01E01.2160p.WEB-DL.x265-GRP", "b1", 5),
                ("NoSeeders", "b2", None),
            ),
        )
    )

    data = authed.get("/api/v1/search", params={"q": "show"}).json()
    assert data["errors"] == {}
    assert [(r["indexer"], r["guid"]) for r in data["releases"]] == [
        ("a", "a2"),  # 50 seeders
        ("b", "b1"),  # 5 seeders, better priority than a1
        ("a", "a1"),
        ("b", "b2"),  # no seeders last
    ]
    top = data["releases"][0]
    assert top["parsed"]["title"] == "Show"
    assert (top["parsed"]["season"], top["parsed"]["episodes"], top["parsed"]["resolution"]) == (
        1, [1], 720,
    )
    assert top["parsed"]["source"] == "hdtv" and top["parsed"]["codec"] == "x264"


@respx.mock
def test_failing_indexer_is_reported_not_fatal(authed):
    add(authed, "good", A)
    add(authed, "bad", B)
    respx.get(A).mock(return_value=httpx.Response(200, text=feed(("Good.2020.1080p", "g1", 1))))
    respx.get(B).mock(return_value=httpx.Response(500))

    data = authed.get("/api/v1/search", params={"q": "x"}).json()
    assert [r["guid"] for r in data["releases"]] == ["g1"]
    assert "500" in data["errors"]["bad"]


@respx.mock
def test_disabled_and_filtered_indexers(authed):
    add(authed, "off", A, enabled=False)
    on_id = add(authed, "on", B)
    route_a = respx.get(A).mock(return_value=httpx.Response(200, text=feed()))
    route_b = respx.get(B).mock(return_value=httpx.Response(200, text=feed()))

    authed.get("/api/v1/search", params={"q": "x"})
    assert not route_a.called and route_b.call_count == 1

    authed.get("/api/v1/search", params={"q": "x", "indexer_id": on_id + 100})
    assert route_b.call_count == 1  # unknown indexer id queries nothing


@respx.mock
def test_kind_selects_function_and_default_categories(authed):
    add(authed, "a", A)
    route = respx.get(A).mock(return_value=httpx.Response(200, text=feed()))

    authed.get("/api/v1/search", params={"kind": "tv", "q": "x", "season": 1, "episode": 2})
    p = route.calls.last.request.url.params
    assert (p["t"], p["cat"], p["season"], p["ep"]) == ("tvsearch", "5000", "1", "2")

    authed.get("/api/v1/search", params={"kind": "movie", "imdb_id": "tt1"})
    p = route.calls.last.request.url.params
    assert (p["t"], p["cat"], p["imdbid"]) == ("movie", "2000", "1")

    authed.get("/api/v1/search", params={"q": "x"})
    assert "cat" not in route.calls.last.request.url.params


def test_validates_parameters(authed):
    assert authed.get("/api/v1/search", params={"kind": "bogus"}).status_code == 422
    assert authed.get("/api/v1/search", params={"limit": 0}).status_code == 422
    assert authed.get("/api/v1/search", params={"limit": 501}).status_code == 422
