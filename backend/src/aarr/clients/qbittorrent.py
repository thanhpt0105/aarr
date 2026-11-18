import base64
import re
from urllib.parse import parse_qs, urlparse

import httpx

from aarr.clients.base import DownloadClient, DownloadClientError, DownloadState, QueueItem

_STATE_MAP = {
    "error": DownloadState.FAILED,
    "missingFiles": DownloadState.FAILED,
    "pausedDL": DownloadState.PAUSED,
    "stoppedDL": DownloadState.PAUSED,
    "queuedDL": DownloadState.QUEUED,
    "pausedUP": DownloadState.COMPLETED,
    "stoppedUP": DownloadState.COMPLETED,
    "uploading": DownloadState.COMPLETED,
    "stalledUP": DownloadState.COMPLETED,
    "queuedUP": DownloadState.COMPLETED,
    "forcedUP": DownloadState.COMPLETED,
    "checkingUP": DownloadState.COMPLETED,
}


def _magnet_hash(url: str) -> str | None:
    if not url.startswith("magnet:"):
        return None
    for xt in parse_qs(urlparse(url).query).get("xt", []):
        match = re.fullmatch(r"urn:btih:([A-Za-z0-9]+)", xt)
        if not match:
            continue
        value = match.group(1)
        if len(value) == 40:
            return value.lower()
        if len(value) == 32:
            return base64.b32decode(value.upper()).hex()
    return None


class QBittorrentClient(DownloadClient):
    def __init__(
        self, base_url: str, username: str, password: str, *, timeout: float = 15.0
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._username = username
        self._password = password
        self._logged_in = False

    async def _login(self) -> None:
        try:
            resp = await self._http.post(
                "/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise DownloadClientError(f"qBittorrent unreachable: {exc}") from exc
        if resp.status_code != 200 or resp.text.strip() != "Ok.":
            raise DownloadClientError("qBittorrent login failed")
        self._logged_in = True

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self._logged_in:
            await self._login()
        try:
            resp = await self._http.request(method, path, **kwargs)
            if resp.status_code == 403:  # session expired
                await self._login()
                resp = await self._http.request(method, path, **kwargs)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise DownloadClientError(
                f"qBittorrent returned {exc.response.status_code} for {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DownloadClientError(f"qBittorrent unreachable: {exc}") from exc
        return resp

    async def test(self) -> str:
        return (await self._request("GET", "/api/v2/app/version")).text.strip()

    async def add(self, url: str, category: str) -> str | None:
        try:
            await self._request(
                "POST", "/api/v2/torrents/createCategory", data={"category": category}
            )
        except DownloadClientError:
            pass  # 409 when the category already exists
        resp = await self._request(
            "POST", "/api/v2/torrents/add", data={"urls": url, "category": category}
        )
        if resp.text.strip() != "Ok.":
            raise DownloadClientError("qBittorrent rejected the torrent")
        return _magnet_hash(url)

    async def queue(self, category: str | None = None) -> list[QueueItem]:
        params = {"category": category} if category else None
        resp = await self._request("GET", "/api/v2/torrents/info", params=params)
        items = []
        for t in resp.json():
            progress = float(t.get("progress", 0.0))
            state = _STATE_MAP.get(t.get("state", ""), DownloadState.DOWNLOADING)
            if state is DownloadState.COMPLETED and progress < 1.0:
                state = DownloadState.DOWNLOADING
            items.append(
                QueueItem(
                    id=t["hash"],
                    title=t["name"],
                    state=state,
                    progress=progress,
                    size_bytes=int(t.get("size", 0)),
                    category=t.get("category", ""),
                    path=t.get("content_path") if state is DownloadState.COMPLETED else None,
                )
            )
        return items

    async def remove(self, item_id: str, delete_files: bool = False) -> None:
        await self._request(
            "POST",
            "/api/v2/torrents/delete",
            data={"hashes": item_id, "deleteFiles": str(delete_files).lower()},
        )

    async def aclose(self) -> None:
        await self._http.aclose()
