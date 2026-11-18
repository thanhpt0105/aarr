import os

import pytest

from aarr.security import Secrets


def test_health_is_public(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_status_requires_api_key(client):
    assert client.get("/api/v1/system/status").status_code == 401
    assert client.get("/api/v1/system/status", headers={"X-Api-Key": "wrong"}).status_code == 401


def test_status_with_api_key(authed):
    resp = authed.get("/api/v1/system/status")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_secrets_persist_and_encrypt(tmp_path):
    first = Secrets(tmp_path)
    token = first.encrypt("hunter2")
    assert token != "hunter2"
    second = Secrets(tmp_path)
    assert second.api_key == first.api_key
    assert second.decrypt(token) == "hunter2"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
def test_secret_files_are_owner_only(tmp_path):
    Secrets(tmp_path)
    for name in ("api_key", "secret.key"):
        assert (tmp_path / name).stat().st_mode & 0o777 == 0o600
