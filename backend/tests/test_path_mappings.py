from types import SimpleNamespace as M

from arrr.services.paths import map_path

CLIENT = {"name": "qbit", "type": "qbittorrent", "url": "http://qbit:8080"}


def test_no_mappings_or_no_path_is_unchanged():
    assert map_path("/downloads/a", []) == "/downloads/a"
    assert map_path(None, [M(remote_path="/downloads", local_path="/data")]) is None


def test_prefix_is_replaced():
    m = [M(remote_path="/downloads/", local_path="/data/downloads/")]
    assert map_path("/downloads/complete/Show", m) == "/data/downloads/complete/Show"
    assert map_path("/downloads", m) == "/data/downloads"


def test_partial_directory_name_does_not_match():
    m = [M(remote_path="/downloads", local_path="/data")]
    assert map_path("/downloads2/x", m) == "/downloads2/x"


def test_longest_prefix_wins():
    m = [
        M(remote_path="/downloads", local_path="/data/a"),
        M(remote_path="/downloads/tv", local_path="/data/tv"),
    ]
    assert map_path("/downloads/tv/Show", m) == "/data/tv/Show"


def test_windows_remote_paths():
    m = [M(remote_path="D:\\Downloads", local_path="/data/downloads")]
    assert map_path("D:\\Downloads\\Show\\ep.mkv", m) == "/data/downloads/Show/ep.mkv"


def test_api_crud_and_cascade(authed):
    cid = authed.post("/api/v1/download-clients", json=CLIENT).json()["id"]
    body = {"client_id": cid, "remote_path": "/downloads", "local_path": "/data/downloads"}
    created = authed.post("/api/v1/path-mappings", json=body)
    assert created.status_code == 201
    mid = created.json()["id"]

    assert authed.get("/api/v1/path-mappings", params={"client_id": cid}).json() == [created.json()]
    assert authed.get("/api/v1/path-mappings", params={"client_id": cid + 1}).json() == []

    assert authed.delete(f"/api/v1/path-mappings/{mid}").status_code == 204
    assert authed.delete(f"/api/v1/path-mappings/{mid}").status_code == 404

    authed.post("/api/v1/path-mappings", json=body)
    assert authed.delete(f"/api/v1/download-clients/{cid}").status_code == 204
    assert authed.get("/api/v1/path-mappings").json() == []


def test_mapping_requires_existing_client(authed):
    body = {"client_id": 99, "remote_path": "/a", "local_path": "/b"}
    assert authed.post("/api/v1/path-mappings", json=body).status_code == 404
    assert authed.post("/api/v1/path-mappings", json=body | {"remote_path": ""}).status_code == 422
