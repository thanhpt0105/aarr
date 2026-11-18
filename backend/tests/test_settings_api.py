def test_requires_api_key(client):
    assert client.get("/api/v1/settings/metadata").status_code == 401
    assert client.put("/api/v1/settings/metadata", json={}).status_code == 401


def test_defaults(authed):
    assert authed.get("/api/v1/settings/metadata").json() == {
        "has_tmdb_api_key": False,
        "tmdb_key_source": None,
        "tmdb_language": "en-US",
    }


def test_set_key_and_language_never_returns_key(authed):
    resp = authed.put(
        "/api/v1/settings/metadata", json={"tmdb_api_key": " secret-key ", "tmdb_language": "vi-VN"}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "has_tmdb_api_key": True,
        "tmdb_key_source": "settings",
        "tmdb_language": "vi-VN",
    }
    assert "secret-key" not in resp.text
    assert authed.app.state.settings_store.get("tmdb_api_key") == "secret-key"


def test_key_is_encrypted_at_rest(authed):
    from sqlalchemy import select

    from arrr.models import AppSetting

    authed.put("/api/v1/settings/metadata", json={"tmdb_api_key": "secret-key"})
    with authed.app.state.db.open_session() as s:
        row = s.scalar(select(AppSetting).where(AppSetting.key == "tmdb_api_key"))
    assert row.is_secret and "secret-key" not in row.value


def test_omit_keeps_and_empty_clears(authed):
    authed.put("/api/v1/settings/metadata", json={"tmdb_api_key": "k"})
    kept = authed.put("/api/v1/settings/metadata", json={"tmdb_language": "fr-FR"}).json()
    assert kept["has_tmdb_api_key"] is True and kept["tmdb_language"] == "fr-FR"
    cleared = authed.put("/api/v1/settings/metadata", json={"tmdb_api_key": ""}).json()
    assert cleared["has_tmdb_api_key"] is False


def test_env_key_is_fallback(tmp_path):
    from fastapi.testclient import TestClient

    from arrr.config import Settings
    from arrr.main import create_app

    app = create_app(Settings(data_dir=tmp_path, queue_poll_seconds=0, tmdb_api_key="env-key"))
    with TestClient(app) as c:
        c.headers["X-Api-Key"] = app.state.secrets.api_key
        assert c.get("/api/v1/settings/metadata").json()["tmdb_key_source"] == "env"
        c.put("/api/v1/settings/metadata", json={"tmdb_api_key": "saved"})
        assert c.get("/api/v1/settings/metadata").json()["tmdb_key_source"] == "settings"
        c.put("/api/v1/settings/metadata", json={"tmdb_api_key": ""})
        assert c.get("/api/v1/settings/metadata").json()["tmdb_key_source"] == "env"


def test_rejects_bad_language(authed):
    resp = authed.put("/api/v1/settings/metadata", json={"tmdb_language": "english"})
    assert resp.status_code == 422
