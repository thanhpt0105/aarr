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


@pytest.fixture
def authed(client):
    client.headers["X-Api-Key"] = client.api_key
    return client
