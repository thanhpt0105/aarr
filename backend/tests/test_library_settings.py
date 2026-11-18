import pytest

PROFILES = "/api/v1/quality-profiles"
FOLDERS = "/api/v1/root-folders"


def test_requires_api_key(client):
    assert client.get(PROFILES).status_code == 401
    assert client.get(FOLDERS).status_code == 401


def test_default_profiles_are_seeded(authed):
    profiles = authed.get(PROFILES).json()
    assert [p["name"] for p in profiles] == ["Any", "HD", "UHD"]
    hd = profiles[1]
    assert (hd["allowed_resolutions"], hd["cutoff_resolution"]) == ([720, 1080], 1080)


def test_profile_crud(authed):
    body = {"name": "Mine", "allowed_resolutions": [1080, 720, 720], "cutoff_resolution": 1080}
    created = authed.post(PROFILES, json=body)
    assert created.status_code == 201
    data = created.json()
    assert data["allowed_resolutions"] == [720, 1080]  # sorted, de-duplicated
    assert data["upgrades_allowed"] is True
    assert authed.get(f"{PROFILES}/{data['id']}").json() == data

    updated = authed.put(
        f"{PROFILES}/{data['id']}",
        json={"name": "Renamed", "allowed_resolutions": [2160], "cutoff_resolution": None},
    )
    assert updated.status_code == 200
    assert (updated.json()["name"], updated.json()["allowed_resolutions"]) == ("Renamed", [2160])

    assert authed.delete(f"{PROFILES}/{data['id']}").status_code == 204
    assert authed.get(f"{PROFILES}/{data['id']}").status_code == 404
    assert authed.delete(f"{PROFILES}/{data['id']}").status_code == 404
    assert authed.put(f"{PROFILES}/{data['id']}", json=body).status_code == 404


def test_profile_duplicate_name_conflicts(authed):
    assert (
        authed.post(PROFILES, json={"name": "HD", "allowed_resolutions": [720]}).status_code == 409
    )
    mine = authed.post(PROFILES, json={"name": "Mine", "allowed_resolutions": [720]}).json()
    clash = authed.put(
        f"{PROFILES}/{mine['id']}", json={"name": "HD", "allowed_resolutions": [720]}
    )
    assert clash.status_code == 409
    # Session must remain usable after the failed write.
    assert authed.get(PROFILES).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "allowed_resolutions": []},
        {"name": "x", "allowed_resolutions": [999]},
        {"name": "x", "allowed_resolutions": [720], "cutoff_resolution": 1080},
        {"name": "", "allowed_resolutions": [720]},
    ],
)
def test_profile_validation(authed, body):
    assert authed.post(PROFILES, json=body).status_code == 422


def test_root_folder_crud(authed, tmp_path):
    movies = tmp_path / "movies"
    movies.mkdir()
    created = authed.post(FOLDERS, json={"path": str(movies), "media_type": "movie"})
    assert created.status_code == 201
    data = created.json()
    assert data["accessible"] is True and data["free_space_bytes"] > 0
    assert authed.get(FOLDERS).json() == [data]

    assert (
        authed.post(FOLDERS, json={"path": str(movies), "media_type": "movie"}).status_code == 409
    )
    assert authed.delete(f"{FOLDERS}/{data['id']}").status_code == 204
    assert authed.delete(f"{FOLDERS}/{data['id']}").status_code == 404


def test_root_folder_path_is_normalized(authed, tmp_path):
    (tmp_path / "tv").mkdir()
    resp = authed.post(
        FOLDERS, json={"path": str(tmp_path / "tv" / "..") + "/tv", "media_type": "tv"}
    )
    assert resp.status_code == 201
    assert resp.json()["path"] == str(tmp_path / "tv")


def test_root_folder_validation(authed, tmp_path):
    missing = authed.post(FOLDERS, json={"path": str(tmp_path / "nope"), "media_type": "movie"})
    assert missing.status_code == 400
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    assert (
        authed.post(FOLDERS, json={"path": str(a_file), "media_type": "movie"}).status_code == 400
    )
    assert (
        authed.post(FOLDERS, json={"path": "relative/dir", "media_type": "movie"}).status_code
        == 400
    )
    assert authed.post(FOLDERS, json={"path": str(tmp_path), "media_type": "x"}).status_code == 422


def test_removed_folder_is_reported_inaccessible(authed, tmp_path):
    folder = tmp_path / "gone"
    folder.mkdir()
    authed.post(FOLDERS, json={"path": str(folder), "media_type": "movie"})
    folder.rmdir()
    [data] = authed.get(FOLDERS).json()
    assert data["accessible"] is False and data["free_space_bytes"] is None
