import httpx

from aarr.clients.base import DownloadClient, DownloadClientError, DownloadState, QueueItem

_QUEUE_STATE_MAP = {
    "Paused": DownloadState.PAUSED,
    "Queued": DownloadState.QUEUED,
}
_HISTORY_STATE_MAP = {
    "Completed": DownloadState.COMPLETED,
    "Failed": DownloadState.FAILED,
}


class SabnzbdClient(DownloadClient):
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)
        self._api_key = api_key

    async def _api(self, **params: str | int) -> dict:
        query = {**params, "apikey": self._api_key, "output": "json"}
        try:
            resp = await self._http.get("/api", params=query)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise DownloadClientError(f"SABnzbd returned {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DownloadClientError(f"SABnzbd request failed: {exc}") from exc
        if isinstance(data, dict) and data.get("status") is False:
            raise DownloadClientError(f"SABnzbd error: {data.get('error', 'unknown')}")
        return data

    async def test(self) -> str:
        version = (await self._api(mode="version"))["version"]
        await self._api(mode="queue", limit=1)  # version is unauthenticated; this checks the key
        return version

    async def add(self, url: str, category: str) -> str | None:
        data = await self._api(mode="addurl", name=url, cat=category)
        ids = data.get("nzo_ids") or []
        return ids[0] if ids else None

    async def queue(self, category: str | None = None) -> list[QueueItem]:
        queue = (await self._api(mode="queue"))["queue"]["slots"]
        history = (await self._api(mode="history"))["history"]["slots"]
        items = []
        for slot in queue:
            items.append(
                QueueItem(
                    id=slot["nzo_id"],
                    title=slot["filename"],
                    state=_QUEUE_STATE_MAP.get(slot["status"], DownloadState.DOWNLOADING),
                    progress=float(slot.get("percentage", 0)) / 100,
                    size_bytes=int(float(slot.get("mb", 0)) * 1024 * 1024),
                    category=slot.get("cat", ""),
                    path=None,
                )
            )
        for slot in history:
            state = _HISTORY_STATE_MAP.get(slot["status"], DownloadState.DOWNLOADING)
            items.append(
                QueueItem(
                    id=slot["nzo_id"],
                    title=slot["name"],
                    state=state,
                    progress=1.0 if state is DownloadState.COMPLETED else 0.99,
                    size_bytes=int(slot.get("bytes", 0)),
                    category=slot.get("category", ""),
                    path=slot.get("storage") if state is DownloadState.COMPLETED else None,
                )
            )
        if category:
            items = [i for i in items if i.category == category]
        return items

    async def remove(self, item_id: str, delete_files: bool = False) -> None:
        flag = int(delete_files)
        await self._api(mode="queue", name="delete", value=item_id, del_files=flag)
        await self._api(mode="history", name="delete", value=item_id, del_files=flag)

    async def aclose(self) -> None:
        await self._http.aclose()
