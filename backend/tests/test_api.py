import pytest
from fastapi.testclient import TestClient

from arrr.config import Settings
from arrr.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as c:
        c.api_key = app.state.secrets.api_key
        yield c


def test_health_is_public(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_status_requires_api_key(client):
    assert client.get("/api/v1/system/status").status_code == 401
    assert client.get("/api/v1/system/status", headers={"X-Api-Key": "wrong"}).status_code == 401


def test_status_with_api_key(client):
    resp = client.get("/api/v1/system/status", headers={"X-Api-Key": client.api_key})
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_secrets_persist_and_encrypt(tmp_path):
    from arrr.security import Secrets

    first = Secrets(tmp_path)
    token = first.encrypt("hunter2")
    assert token != "hunter2"
    second = Secrets(tmp_path)
    assert second.api_key == first.api_key
    assert second.decrypt(token) == "hunter2"
