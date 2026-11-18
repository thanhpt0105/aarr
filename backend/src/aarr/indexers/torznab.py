from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import Element

import httpx
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from aarr.indexers.models import Caps, IndexerError, Protocol, Release, SearchQuery

_SEARCH_FN = {"search": "search", "movie": "movie", "tv": "tvsearch"}


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


class TorznabClient:
    """Client for Torznab (torrent) and Newznab (usenet) feeds.

    `url` is the full API endpoint, e.g. a Prowlarr or Jackett Torznab feed URL.
    """

    def __init__(
        self,
        name: str,
        url: str,
        api_key: str | None,
        protocol: Protocol,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.protocol = protocol
        self._url = url
        self._api_key = api_key
        self._http = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def _get(self, **params: str | int) -> Element:
        query = {k: v for k, v in params.items() if v is not None}
        if self._api_key:
            query["apikey"] = self._api_key
        try:
            resp = await self._http.get(self._url, params=query)
            resp.raise_for_status()
            root = SafeET.fromstring(resp.content)
        except httpx.HTTPStatusError as exc:
            raise IndexerError(f"{self.name} returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise IndexerError(f"{self.name} unreachable: {exc}") from exc
        except (SafeET.ParseError, DefusedXmlException) as exc:
            raise IndexerError(f"{self.name} returned an invalid response") from exc
        if _local(root.tag) == "error":
            raise IndexerError(f"{self.name}: {root.get('description', 'unknown error')}")
        return root

    async def caps(self) -> Caps:
        root = await self._get(t="caps")
        modes: dict[str, frozenset[str]] = {}
        searching = root.find("searching")
        if searching is not None:
            for el in searching:
                if el.get("available") == "yes":
                    params = (p.strip() for p in el.get("supportedParams", "").split(","))
                    modes[el.tag] = frozenset(p for p in params if p)
        categories: dict[int, str] = {}
        for el in root.iter():
            if el.tag in ("category", "subcat") and (cat_id := _int(el.get("id"))) is not None:
                categories[cat_id] = el.get("name", "")
        server = root.find("server")
        return Caps(server.get("title") if server is not None else None, modes, categories)

    async def search(self, query: SearchQuery) -> list[Release]:
        root = await self._get(
            t=_SEARCH_FN[query.kind],
            q=query.q,
            cat=",".join(map(str, query.categories)) or None,
            season=query.season,
            ep=query.episode,
            imdbid=query.imdb_id.removeprefix("tt") if query.imdb_id else None,
            tmdbid=query.tmdb_id,
            tvdbid=query.tvdb_id,
            limit=query.limit,
            extended=1,
        )
        releases = (self._parse_item(item) for item in root.iter("item"))
        return [r for r in releases if r is not None]

    def _parse_item(self, item: Element) -> Release | None:
        title = item.findtext("title")
        if not title:
            return None
        attrs: dict[str, list[str]] = {}
        for el in item:
            if _local(el.tag) == "attr":
                attrs.setdefault(el.get("name", ""), []).append(el.get("value", ""))

        def attr(name: str) -> str | None:
            return attrs[name][0] if name in attrs else None

        enclosure = item.find("enclosure")
        url = (
            (enclosure.get("url") if enclosure is not None else None)
            or item.findtext("link")
            or attr("magneturl")
        )
        if not url:
            return None

        size = (
            _int(attr("size"))
            or _int(item.findtext("size"))
            or _int(enclosure.get("length") if enclosure is not None else None)
            or 0
        )
        seeders = _int(attr("seeders"))
        peers = _int(attr("peers"))
        leechers = _int(attr("leechers"))
        if leechers is None and peers is not None and seeders is not None:
            leechers = max(peers - seeders, 0)  # Torznab "peers" includes seeders

        published = None
        if pub := item.findtext("pubDate"):
            try:
                published = parsedate_to_datetime(pub)
            except (TypeError, ValueError):
                published = None

        categories = tuple(c for c in map(_int, attrs.get("category", [])) if c is not None)
        return Release(
            indexer=self.name,
            title=title.strip(),
            guid=item.findtext("guid") or url,
            download_url=url,
            protocol=self.protocol,
            size=size,
            published=published,
            seeders=seeders,
            leechers=leechers,
            infohash=attr("infohash"),
            info_url=item.findtext("comments"),
            categories=categories,
        )

    async def aclose(self) -> None:
        await self._http.aclose()
