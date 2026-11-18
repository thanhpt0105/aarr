import httpx
import pytest
import respx

from aarr.clients.base import DownloadClientError, DownloadState
from aarr.clients.qbittorrent import QBittorrentClient, _magnet_hash

BASE = "http://qbit:8080"
HASH = "a" * 40


@pytest.fixture
async def client():
    c = QBittorrentClient(BASE, "admin", "pw")
    yield c
    await c.aclose()


def test_magnet_hash_hex_and_base32():
    assert _magnet_hash(f"magnet:?xt=urn:btih:{HASH.upper()}&dn=x") == HASH
    assert _magnet_hash("magnet:?xt=urn:btih:" + "A" * 32) == "00" * 20
    assert _magnet_hash("http://example.com/x.torrent") is None


@respx.mock
async def test_test_returns_version(client):
    respx.post(f"{BASE}/api/v2/auth/login").mock(return_value=httpx.Response(200, text="Ok."))
    respx.get(f"{BASE}/api/v2/app/version").mock(return_value=httpx.Response(200, text="v5.0.0"))
    assert await client.test() == "v5.0.0"


@respx.mock
async def test_login_failure(client):
    respx.post(f"{BASE}/api/v2/auth/login").mock(return_value=httpx.Response(200, text="Fails."))
    with pytest.raises(DownloadClientError, match="login failed"):
        await client.test()


@respx.mock
async def test_relogin_on_403(client):
    login = respx.post(f"{BASE}/api/v2/auth/login").mock(
        return_value=httpx.Response(200, text="Ok.")
    )
    respx.get(f"{BASE}/api/v2/app/version").mock(
        side_effect=[httpx.Response(403), httpx.Response(200, text="v5.0.0")]
    )
    assert await client.test() == "v5.0.0"
    assert login.call_count == 2


@respx.mock
async def test_add_magnet_returns_hash(client):
    respx.post(f"{BASE}/api/v2/auth/login").mock(return_value=httpx.Response(200, text="Ok."))
    respx.post(f"{BASE}/api/v2/torrents/createCategory").mock(return_value=httpx.Response(409))
    add = respx.post(f"{BASE}/api/v2/torrents/add").mock(
        return_value=httpx.Response(200, text="Ok.")
    )
    assert await client.add(f"magnet:?xt=urn:btih:{HASH}", "radarr") == HASH
    assert b"category=radarr" in add.calls.last.request.content


@respx.mock
async def test_queue_maps_states(client):
    respx.post(f"{BASE}/api/v2/auth/login").mock(return_value=httpx.Response(200, text="Ok."))
    respx.get(f"{BASE}/api/v2/torrents/info").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "hash": "1",
                    "name": "a",
                    "state": "downloading",
                    "progress": 0.5,
                    "size": 100,
                    "category": "sonarr",
                    "content_path": "/data/a",
                },
                {
                    "hash": "2",
                    "name": "b",
                    "state": "stalledUP",
                    "progress": 1.0,
                    "size": 200,
                    "category": "sonarr",
                    "content_path": "/data/b",
                },
                {
                    "hash": "3",
                    "name": "c",
                    "state": "error",
                    "progress": 0.1,
                    "size": 300,
                    "category": "sonarr",
                    "content_path": "/data/c",
                },
            ],
        )
    )
    items = await client.queue("sonarr")
    assert [i.state for i in items] == [
        DownloadState.DOWNLOADING,
        DownloadState.COMPLETED,
        DownloadState.FAILED,
    ]
    assert [i.path for i in items] == [None, "/data/b", None]
