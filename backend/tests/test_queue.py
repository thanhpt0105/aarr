import httpx
import respx

QBIT = {
    "name": "qbit",
    "type": "qbittorrent",
    "url": "http://qbit:8080",
    "username": "admin",
    "secret": "pw",
}
SAB = {"name": "sab", "type": "sabnzbd", "url": "http://sab:8080", "secret": "key"}


def _mock_qbit():
    respx.post("http://qbit:8080/api/v2/auth/login").mock(
        return_value=httpx.Response(200, text="Ok.")
    )
    respx.get("http://qbit:8080/api/v2/torrents/info").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "hash": "h",
                    "name": "Show",
                    "state": "stalledUP",
                    "progress": 1.0,
                    "size": 10,
                    "category": "aarr-tv",
                    "content_path": "/downloads/Show",
                }
            ],
        )
    )


def test_requires_api_key(client):
    assert client.get("/api/v1/queue").status_code == 401
    assert client.post("/api/v1/queue/refresh").status_code == 401


def test_empty_before_any_poll(authed):
    assert authed.get("/api/v1/queue").json() == []


@respx.mock
def test_refresh_applies_path_mapping(authed):
    cid = authed.post("/api/v1/download-clients", json=QBIT).json()["id"]
    authed.post(
        "/api/v1/path-mappings",
        json={"client_id": cid, "remote_path": "/downloads", "local_path": "/data/downloads"},
    )
    _mock_qbit()

    resp = authed.post("/api/v1/queue/refresh")
    assert resp.status_code == 200
    [snap] = resp.json()
    assert snap["client_name"] == "qbit" and snap["error"] is None
    assert snap["updated_at"] is not None
    [item] = snap["items"]
    assert item["state"] == "completed"
    assert item["path"] == "/data/downloads/Show"
    assert authed.get("/api/v1/queue").json() == resp.json()


@respx.mock
def test_one_failing_client_does_not_break_others(authed):
    authed.post("/api/v1/download-clients", json=QBIT)
    authed.post("/api/v1/download-clients", json=SAB)
    _mock_qbit()
    respx.get("http://sab:8080/api").mock(
        return_value=httpx.Response(200, json={"status": False, "error": "API Key Incorrect"})
    )

    by_name = {s["client_name"]: s for s in authed.post("/api/v1/queue/refresh").json()}
    assert by_name["qbit"]["error"] is None and len(by_name["qbit"]["items"]) == 1
    assert "API Key Incorrect" in by_name["sab"]["error"]
    assert by_name["sab"]["items"] == []


@respx.mock
def test_disabled_clients_are_skipped(authed):
    authed.post("/api/v1/download-clients", json=QBIT | {"enabled": False})
    assert authed.post("/api/v1/queue/refresh").json() == []
