import httpx
import respx

CAPS = (
    '<caps><server title="Idx"/><searching><search available="yes" supportedParams="q"/>'
    '<tv-search available="yes" supportedParams="q"/></searching>'
    '<categories><category id="2000" name="Movies"/></categories></caps>'
)
BODY = {"name": "idx", "protocol": "torrent", "url": "http://idx.test/api", "api_key": "k"}


def test_requires_api_key(client):
    assert client.get("/api/v1/indexers").status_code == 401


def test_create_list_get_hides_key(authed):
    created = authed.post("/api/v1/indexers", json=BODY)
    assert created.status_code == 201
    data = created.json()
    assert data["has_api_key"] is True and data["priority"] == 25
    assert "api_key" not in data and '"k"' not in created.text
    assert authed.get("/api/v1/indexers").json() == [data]
    assert authed.get(f"/api/v1/indexers/{data['id']}").json() == data


def test_key_encrypted_at_rest(authed):
    from sqlalchemy import select

    from aarr.models import IndexerConfig

    authed.post("/api/v1/indexers", json=BODY)
    row = next(authed.app.state.db.session()).scalar(select(IndexerConfig))
    assert row.api_key_encrypted and row.api_key_encrypted != "k"
    assert authed.app.state.secrets.decrypt(row.api_key_encrypted) == "k"


def test_duplicate_update_delete(authed):
    iid = authed.post("/api/v1/indexers", json=BODY).json()["id"]
    assert authed.post("/api/v1/indexers", json=BODY).status_code == 409

    update = {k: v for k, v in BODY.items() if k != "api_key"} | {"name": "renamed", "priority": 5}
    resp = authed.put(f"/api/v1/indexers/{iid}", json=update)
    assert resp.status_code == 200
    assert (resp.json()["name"], resp.json()["priority"], resp.json()["has_api_key"]) == (
        "renamed",
        5,
        True,
    )

    assert authed.delete(f"/api/v1/indexers/{iid}").status_code == 204
    assert authed.get(f"/api/v1/indexers/{iid}").status_code == 404


def test_validation(authed):
    assert authed.post("/api/v1/indexers", json=BODY | {"protocol": "x"}).status_code == 422
    assert authed.post("/api/v1/indexers", json=BODY | {"url": "nope"}).status_code == 422


@respx.mock
def test_test_saved_and_unsaved(authed):
    iid = authed.post("/api/v1/indexers", json=BODY).json()["id"]
    route = respx.get("http://idx.test/api").mock(return_value=httpx.Response(200, text=CAPS))

    saved = authed.post(f"/api/v1/indexers/{iid}/test").json()
    assert saved == {
        "ok": True,
        "title": "Idx",
        "search_modes": ["search", "tv-search"],
        "category_count": 1,
        "error": None,
    }
    assert route.calls.last.request.url.params["apikey"] == "k"
    assert authed.post("/api/v1/indexers/test", json=BODY).json()["ok"] is True


@respx.mock
def test_test_failure_is_reported(authed):
    respx.get("http://idx.test/api").mock(
        return_value=httpx.Response(200, text='<error code="100" description="Bad key"/>')
    )
    resp = authed.post("/api/v1/indexers/test", json=BODY)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False and "Bad key" in resp.json()["error"]
