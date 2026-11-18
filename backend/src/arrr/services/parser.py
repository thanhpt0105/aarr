import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Source(StrEnum):
    CAM = "cam"
    TELESYNC = "telesync"
    DVD = "dvd"
    HDTV = "hdtv"
    WEBRIP = "webrip"
    WEBDL = "webdl"
    BLURAY = "bluray"
    REMUX = "remux"


@dataclass(frozen=True)
class ParsedRelease:
    title: str
    year: int | None = None
    season: int | None = None
    episodes: tuple[int, ...] = ()
    season_pack: bool = False
    air_date: date | None = None
    resolution: int | None = None  # vertical lines: 480, 576, 720, 1080, 2160
    source: Source | None = None
    codec: str | None = None
    group: str | None = None
    revision: int = 1  # 2 for PROPER / REPACK
    languages: tuple[str, ...] = ()


_EXT = re.compile(r"\.(mkv|mp4|avi|m4v|nzb|torrent)$", re.I)
_LEADING_GROUP = re.compile(r"^\[([^\]]+)\]\s*")
_TRAILING_BRACKETS = re.compile(r"(\s*[\[(][^\])]*[\])])+$")
_GROUP = re.compile(r"-([A-Za-z0-9]+)$")
_NOT_GROUPS = {"dl", "rip", "ray", "hd", "ma", "x", "hdma", "es"}

_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_RESOLUTION = re.compile(r"\b(2160p|4k|1080[pi]|720p|576p|480p)\b", re.I)
_SXXEXX = re.compile(r"\bS(\d{1,2})E(\d{1,3})(?!\d)", re.I)
_EP_TAIL = re.compile(r"(-E?|E)(\d{1,3})(?!\d)", re.I)
_NXNN = re.compile(r"\b(\d{1,2})x(\d{2,3})\b", re.I)
_SEASON_ONLY = re.compile(r"\b(?:S|Season ?)(\d{1,2})\b(?![ -]?E\d)", re.I)
_DATE = re.compile(r"\b(\d{4})[ -](\d{2})[ -](\d{2})\b")
_REVISION = re.compile(r"\b(proper|repack)\d?\b", re.I)
_EXTRAS = re.compile(r"\b(complete|internal|limited|extended|unrated|remastered)\b", re.I)

# Checked in priority order; the first source that matches wins.
_SOURCES: tuple[tuple[Source, re.Pattern[str]], ...] = (
    (Source.REMUX, re.compile(r"\bremux\b", re.I)),
    (Source.BLURAY, re.compile(r"\b(blu-?ray|bdrip|brrip|bd)\b", re.I)),
    (Source.WEBRIP, re.compile(r"\bweb-?rip\b", re.I)),
    (Source.WEBDL, re.compile(r"\b(web-?dl|webhd|web)\b", re.I)),
    (Source.HDTV, re.compile(r"\b(hdtv|pdtv|dsr)\b", re.I)),
    (Source.DVD, re.compile(r"\bdvd(rip|scr)?\b", re.I)),
    (Source.TELESYNC, re.compile(r"\b(telesync|hdts|ts)\b", re.I)),
    (Source.CAM, re.compile(r"\b(cam|hdcam)\b", re.I)),
)
_CODECS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("x265", re.compile(r"\b(x265|h ?265|hevc)\b", re.I)),
    ("x264", re.compile(r"\b(x264|h ?264|avc)\b", re.I)),
    ("av1", re.compile(r"\bav1\b", re.I)),
    ("xvid", re.compile(r"\b(xvid|divx)\b", re.I)),
)
_LANGUAGES = {
    "vi": re.compile(r"\b(vietnamese|vie)\b", re.I),
    "fr": re.compile(r"\b(french|truefrench)\b", re.I),
    "de": re.compile(r"\bgerman\b", re.I),
    "es": re.compile(r"\b(spanish|castellano)\b", re.I),
    "it": re.compile(r"\bitalian\b", re.I),
    "ja": re.compile(r"\bjapanese\b", re.I),
    "ko": re.compile(r"\bkorean\b", re.I),
    "zh": re.compile(r"\b(chinese|mandarin)\b", re.I),
    "multi": re.compile(r"\bmulti\b", re.I),
}
_RESOLUTION_LINES = {"4k": 2160, "1080i": 1080}


def _parse_episodes(text: str, first: re.Match[str]) -> tuple[int, ...]:
    episodes = [int(first.group(2))]
    pos = first.end()
    while m := _EP_TAIL.match(text, pos):
        number = int(m.group(2))
        if m.group(1).startswith("-") and number > episodes[-1]:
            episodes.extend(range(episodes[-1] + 1, number + 1))
        else:
            episodes.append(number)
        pos = m.end()
    return tuple(episodes)


def _valid_date(m: re.Match[str]) -> date | None:
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _clean_title(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip(" -[]()")


def parse_release(name: str) -> ParsedRelease:
    name = _EXT.sub("", name.strip())

    group = None
    if m := _LEADING_GROUP.match(name):
        group = m.group(1)
        name = name[m.end() :]
    name = _TRAILING_BRACKETS.sub("", name)
    if group is None and (m := _GROUP.search(name)) and m.group(1).lower() not in _NOT_GROUPS:
        group = m.group(1)
        name = name[: m.start()]

    text = re.sub(r"[._]", " ", name)  # 1:1 replacement keeps match offsets valid
    cuts: list[int] = []

    season: int | None = None
    episodes: tuple[int, ...] = ()
    season_pack = False
    air_date: date | None = None

    if m := _SXXEXX.search(text):
        season, episodes = int(m.group(1)), _parse_episodes(text, m)
        cuts.append(m.start())
    elif m := _NXNN.search(text):
        season, episodes = int(m.group(1)), _parse_episodes(text, m)
        cuts.append(m.start())
    elif (m := _DATE.search(text)) and (air_date := _valid_date(m)):
        cuts.append(m.start())
    elif m := _SEASON_ONLY.search(text):
        season, season_pack = int(m.group(1)), True
        cuts.append(m.start())

    resolution = None
    if m := _RESOLUTION.search(text):
        key = m.group(1).lower()
        resolution = _RESOLUTION_LINES.get(key) or int(key.rstrip("pi"))
        cuts.append(m.start())

    source = None
    for candidate, pattern in _SOURCES:
        if m := pattern.search(text):
            source = candidate
            cuts.append(m.start())
            break

    codec = None
    for candidate_codec, pattern in _CODECS:
        if m := pattern.search(text):
            codec = candidate_codec
            cuts.append(m.start())
            break

    revision = 1
    if m := _REVISION.search(text):
        revision = 2
        cuts.append(m.start())
    if m := _EXTRAS.search(text):
        cuts.append(m.start())

    languages = []
    for code, pattern in _LANGUAGES.items():
        if m := pattern.search(text):
            languages.append(code)
            cuts.append(m.start())

    # The release year is the last year before any other marker; earlier ones belong to the title.
    year = None
    limit = min(cuts) if cuts else len(text)
    years = [y for y in _YEAR.finditer(text) if 0 < y.start() < limit]
    if years:
        year = int(years[-1].group(1))
        cuts.append(years[-1].start())

    title = _clean_title(text[: min(cuts)] if cuts else text)
    return ParsedRelease(
        title=title,
        year=year,
        season=season,
        episodes=episodes,
        season_pack=season_pack,
        air_date=air_date,
        resolution=resolution,
        source=source,
        codec=codec,
        group=group,
        revision=revision,
        languages=tuple(languages),
    )
