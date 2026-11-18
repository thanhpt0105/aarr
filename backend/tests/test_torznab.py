import httpx
import pytest
import respx

from arrr.indexers.models import IndexerError, SearchQuery
from arrr.indexers.torznab import TorznabClient

URL = "http://idx.test/api"

CAPS = """<?xml version="1.0"?>
<caps>
  <server title="Test Indexer"/>
  <searching>
    <search available="yes" supportedParams="q"/>
    <tv-search available="yes" supportedParams="q,season,ep,tvdbid"/>
    <movie-search available="no" supportedParams="q"/>
  </searching>
  <categories>
    <category id="2000" name="Movies"><subcat id="2040" name="Movies/HD"/></category>
    <category id="5000" name="TV"/>
  </categories>
</caps>"""

FEED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
 <channel>
  <item>
   <title>Show.S01E01.1080p.WEB-DL.x264-GRP</title>
   <guid>guid-1</guid>
   <link>http://idx.test/dl/1</link>
   <comments>http://idx.test/details/1</comments>
   <pubDate>Sat, 14 Nov 2026 10:00:00 +0000</pubDate>
   <size>1500000000</size>
   <enclosure url="http://idx.test/dl/1.torrent" length="1500000000"
              type="application/x-bittorrent"/>
   <torznab:attr name="seeders" value="10"/>
   <torznab:attr name="peers" value="15"/>
   <torznab:attr name="infohash" value="abc123"/>
   <torznab:attr name="category" value="5000"/>
   <torznab:attr name="category" value="5040"/>
  </item>
  <item>
   <title>Magnet.Only.2020.1080p</title>
   <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:abc"/>
   <torznab:attr name="size" value="42"/>
   <pubDate>not a date</pubDate>
  </item>
  <item><title>No.Download.Link</title></item>
  <item><link>http://idx.test/dl/3</link></item>
 </channel>
</rss>"""


@pytest.fixture
async def client():
    c = TorznabClient("idx", URL, "key", "torrent")
    yield c
    await c.aclose()


@respx.mock
async def test_caps(client):
    route = respx.get(URL, params={"t": "caps"}).mock(return_value=httpx.Response(200, text=CAPS))
    caps = await client.caps()
    assert caps.title == "Test Indexer"
    assert caps.search_modes == {
        "search": frozenset({"q"}),
        "tv-search": frozenset({"q", "season", "ep", "tvdbid"}),
    }
    assert caps.categories == {2000: "Movies", 2040: "Movies/HD", 5000: "TV"}
    assert route.calls.last.request.url.params["apikey"] == "key"


@respx.mock
async def test_search_parses_items_and_skips_unusable(client):
    respx.get(URL).mock(return_value=httpx.Response(200, text=FEED))
    releases = await client.search(SearchQuery(q="show"))
    titles = [r.title for r in releases]
    assert titles == ["Show.S01E01.1080p.WEB-DL.x264-GRP", "Magnet.Only.2020.1080p"]

    first, second = releases
    assert first.download_url == "http://idx.test/dl/1.torrent"
    assert first.guid == "guid-1"
    assert first.size == 1_500_000_000
    assert (first.seeders, first.leechers) == (10, 5)
    assert first.infohash == "abc123"
    assert first.info_url == "http://idx.test/details/1"
    assert first.categories == (5000, 5040)
    assert first.published is not None and first.published.year == 2026
    assert first.protocol == "torrent" and first.indexer == "idx"

    assert second.download_url == "magnet:?xt=urn:btih:abc"
    assert second.guid == second.download_url
    assert second.size == 42
    assert second.published is None
    assert second.seeders is None


@respx.mock
async def test_search_sends_expected_params(client):
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=FEED))
    await client.search(
        SearchQuery(
            kind="tv", q="show", season=2, episode=5, tvdb_id=99, categories=(5000, 5040), limit=50
        )
    )
    p = route.calls.last.request.url.params
    assert dict(p) == {
        "t": "tvsearch",
        "q": "show",
        "season": "2",
        "ep": "5",
        "tvdbid": "99",
        "cat": "5000,5040",
        "limit": "50",
        "extended": "1",
        "apikey": "key",
    }


@respx.mock
async def test_movie_search_strips_imdb_prefix(client):
    route = respx.get(URL).mock(return_value=httpx.Response(200, text=FEED))
    await client.search(SearchQuery(kind="movie", imdb_id="tt0123456", tmdb_id=7))
    p = route.calls.last.request.url.params
    assert (p["t"], p["imdbid"], p["tmdbid"]) == ("movie", "0123456", "7")


@respx.mock
async def test_error_document_is_raised(client):
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, text='<error code="100" description="Incorrect user credentials"/>'
        )
    )
    with pytest.raises(IndexerError, match="Incorrect user credentials"):
        await client.caps()


@respx.mock
async def test_http_and_network_and_parse_errors(client):
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(IndexerError, match="503"):
        await client.caps()

    respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(IndexerError, match="unreachable"):
        await client.caps()

    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>not xml"))
    with pytest.raises(IndexerError, match="invalid response"):
        await client.caps()


@respx.mock
async def test_entity_expansion_is_rejected(client):
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><caps>&a;</caps>'
    respx.get(URL).mock(return_value=httpx.Response(200, text=bomb))
    with pytest.raises(IndexerError, match="invalid response"):
        await client.caps()


@respx.mock
async def test_newznab_protocol_is_propagated():
    c = TorznabClient("nzb", URL, None, "usenet")
    respx.get(URL).mock(return_value=httpx.Response(200, text=FEED))
    releases = await c.search(SearchQuery(q="x"))
    assert {r.protocol for r in releases} == {"usenet"}
    assert "apikey" not in respx.calls.last.request.url.params
    await c.aclose()
