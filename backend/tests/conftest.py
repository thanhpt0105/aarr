import pytest
from fastapi.testclient import TestClient

from aarr.config import Settings
from aarr.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, queue_poll_seconds=0))
    with TestClient(app) as c:
        c.api_key = app.state.secrets.api_key
        yield c


@pytest.fixture
def authed(client):
    client.headers["X-Api-Key"] = client.api_key
    return client
