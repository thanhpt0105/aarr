import httpx
import respx

BODY = {
    "name": "qbit",
    "type": "qbittorrent",
    "url": "http://qbit:8080/",
    "username": "admin",
    "secret": "pw",
}


def test_requires_api_key(client):
    assert client.get("/api/v1/download-clients").status_code == 401


def test_create_list_get_never_returns_secret(authed):
    created = authed.post("/api/v1/download-clients", json=BODY)
    assert created.status_code == 201
    data = created.json()
    assert data["url"] == "http://qbit:8080"
    assert data["has_secret"] is True
    assert "secret" not in data and "pw" not in created.text

    assert authed.get("/api/v1/download-clients").json() == [data]
    assert authed.get(f"/api/v1/download-clients/{data['id']}").json() == data


def test_secret_is_encrypted_at_rest(authed):
    authed.post("/api/v1/download-clients", json=BODY)
    from sqlalchemy import select

    from arrr.models import DownloadClientConfig

    db = authed.app.state.db
    row = next(db.session()).scalar(select(DownloadClientConfig))
    assert row.secret_encrypted and row.secret_encrypted != "pw"
    assert authed.app.state.secrets.decrypt(row.secret_encrypted) == "pw"


def test_duplicate_name_conflicts(authed):
    assert authed.post("/api/v1/download-clients", json=BODY).status_code == 201
    assert authed.post("/api/v1/download-clients", json=BODY).status_code == 409


def test_update_keeps_secret_when_omitted(authed):
    cid = authed.post("/api/v1/download-clients", json=BODY).json()["id"]
    update = {k: v for k, v in BODY.items() if k != "secret"} | {"name": "renamed"}
    resp = authed.put(f"/api/v1/download-clients/{cid}", json=update)
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed"
    assert resp.json()["has_secret"] is True


def test_delete_and_404(authed):
    cid = authed.post("/api/v1/download-clients", json=BODY).json()["id"]
    assert authed.delete(f"/api/v1/download-clients/{cid}").status_code == 204
    assert authed.get(f"/api/v1/download-clients/{cid}").status_code == 404


def test_rejects_bad_type_and_url(authed):
    assert authed.post("/api/v1/download-clients", json=BODY | {"type": "x"}).status_code == 422
    assert authed.post("/api/v1/download-clients", json=BODY | {"url": "nope"}).status_code == 422


@respx.mock
def test_test_saved_client(authed):
    cid = authed.post("/api/v1/download-clients", json=BODY).json()["id"]
    login = respx.post("http://qbit:8080/api/v2/auth/login").mock(
        return_value=httpx.Response(200, text="Ok.")
    )
    respx.get("http://qbit:8080/api/v2/app/version").mock(
        return_value=httpx.Response(200, text="v5.0.0")
    )
    resp = authed.post(f"/api/v1/download-clients/{cid}/test")
    assert resp.json() == {"ok": True, "version": "v5.0.0", "error": None}
    assert b"password=pw" in login.calls.last.request.content


@respx.mock
def test_test_unsaved_reports_failure(authed):
    respx.post("http://qbit:8080/api/v2/auth/login").mock(
        return_value=httpx.Response(200, text="Fails.")
    )
    resp = authed.post("/api/v1/download-clients/test", json=BODY)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "login failed" in resp.json()["error"]
