from arrr.clients.base import DownloadClient
from arrr.clients.qbittorrent import QBittorrentClient
from arrr.clients.sabnzbd import SabnzbdClient

CLIENT_TYPES = ("qbittorrent", "sabnzbd")


def build_client(
    client_type: str, url: str, username: str | None, secret: str | None
) -> DownloadClient:
    if client_type == "qbittorrent":
        return QBittorrentClient(url, username or "", secret or "")
    if client_type == "sabnzbd":
        return SabnzbdClient(url, secret or "")
    raise ValueError(f"Unsupported download client type: {client_type}")
