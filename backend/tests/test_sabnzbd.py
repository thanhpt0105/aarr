import httpx
import pytest
import respx

from aarr.clients.base import DownloadClientError, DownloadState
from aarr.clients.sabnzbd import SabnzbdClient

BASE = "http://sab:8080"
API = f"{BASE}/api"


@pytest.fixture
async def client():
    c = SabnzbdClient(BASE, "key")
    yield c
    await c.aclose()


@respx.mock
async def test_test_checks_key(client):
    respx.get(API, params={"mode": "version"}).mock(
        return_value=httpx.Response(200, json={"version": "4.3.0"})
    )
    respx.get(API, params={"mode": "queue"}).mock(
        return_value=httpx.Response(200, json={"status": False, "error": "API Key Incorrect"})
    )
    with pytest.raises(DownloadClientError, match="API Key Incorrect"):
        await client.test()


@respx.mock
async def test_add_returns_nzo_id(client):
    respx.get(API, params={"mode": "addurl"}).mock(
        return_value=httpx.Response(200, json={"status": True, "nzo_ids": ["SABnzbd_nzo_1"]})
    )
    assert await client.add("http://x/y.nzb", "tv") == "SABnzbd_nzo_1"


@respx.mock
async def test_queue_combines_queue_and_history(client):
    respx.get(API, params={"mode": "queue"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "slots": [
                        {
                            "nzo_id": "q1",
                            "filename": "Show.S01E01",
                            "status": "Downloading",
                            "percentage": "50",
                            "mb": "100.0",
                            "cat": "tv",
                        },
                        {
                            "nzo_id": "q2",
                            "filename": "Other",
                            "status": "Paused",
                            "percentage": "0",
                            "mb": "10.0",
                            "cat": "movies",
                        },
                    ]
                }
            },
        )
    )
    respx.get(API, params={"mode": "history"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "history": {
                    "slots": [
                        {
                            "nzo_id": "h1",
                            "name": "Done",
                            "status": "Completed",
                            "bytes": 500,
                            "category": "tv",
                            "storage": "/data/done",
                        },
                        {
                            "nzo_id": "h2",
                            "name": "Bad",
                            "status": "Failed",
                            "bytes": 500,
                            "category": "tv",
                            "storage": "/data/bad",
                        },
                    ]
                }
            },
        )
    )
    items = await client.queue("tv")
    assert [(i.id, i.state, i.path) for i in items] == [
        ("q1", DownloadState.DOWNLOADING, None),
        ("h1", DownloadState.COMPLETED, "/data/done"),
        ("h2", DownloadState.FAILED, None),
    ]
    assert items[0].progress == 0.5
