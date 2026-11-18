from datetime import date

import pytest

from aarr.services.parser import Source, parse_release


@pytest.mark.parametrize(
    ("name", "title", "season", "episodes"),
    [
        ("The.Lament.of.Autumn.S01E29.1080p.WEB-DL.x264-GRP", "The Lament of Autumn", 1, (29,)),
        ("Show Name - S02E05 - Episode Title 720p HDTV", "Show Name", 2, (5,)),
        ("Show.Name.S01E01E02.720p.HDTV.x264-GRP", "Show Name", 1, (1, 2)),
        ("Show.Name.S01E01-E03.720p.HDTV.x264-GRP", "Show Name", 1, (1, 2, 3)),
        ("Show.Name.S01E01-03.720p.HDTV.x264-GRP", "Show Name", 1, (1, 2, 3)),
        ("Show.Name.1x05.DVDRip.XviD-GRP", "Show Name", 1, (5,)),
        ("show_name_s10e100_1080p", "show name", 10, (100,)),
    ],
)
def test_episode_numbering(name, title, season, episodes):
    r = parse_release(name)
    assert (r.title, r.season, r.episodes, r.season_pack) == (title, season, episodes, False)


@pytest.mark.parametrize(
    ("name", "season"),
    [
        ("Show.Name.S03.1080p.BluRay.x265-GRP", 3),
        ("Show Name Season 2 Complete 720p WEB-DL", 2),
    ],
)
def test_season_packs(name, season):
    r = parse_release(name)
    assert r.title == "Show Name"
    assert (r.season, r.episodes, r.season_pack) == (season, (), True)


def test_daily_show_air_date():
    r = parse_release("Late.Show.2024.01.15.720p.WEB.h264-GRP")
    assert (r.title, r.air_date, r.episodes, r.year) == ("Late Show", date(2024, 1, 15), (), None)


def test_invalid_date_is_not_an_air_date():
    assert parse_release("Movie.2020.13.45.1080p.BluRay").air_date is None


@pytest.mark.parametrize(
    ("name", "title", "year"),
    [
        ("Inception.2010.1080p.BluRay.x264-GRP", "Inception", 2010),
        ("The.Movie.Title.(2019).720p.WEB-DL", "The Movie Title", 2019),
        ("Blade.Runner.2049.2017.1080p.BluRay.x264-GRP", "Blade Runner 2049", 2017),
        ("2012.2009.1080p.BluRay.x264-GRP", "2012", 2009),
        ("2012.1080p.BluRay.x264-GRP", "2012", None),
        ("Some.Movie.1080p.WEB-DL", "Some Movie", None),
    ],
)
def test_movie_title_and_year(name, title, year):
    r = parse_release(name)
    assert (r.title, r.year) == (title, year)
    assert r.season is None and r.episodes == ()


@pytest.mark.parametrize(
    ("name", "resolution"),
    [
        ("A.S01E01.2160p.WEB-DL", 2160),
        ("A.S01E01.4K.WEB-DL", 2160),
        ("A.S01E01.1080p.WEB-DL", 1080),
        ("A.S01E01.1080i.HDTV", 1080),
        ("A.S01E01.720P.HDTV", 720),
        ("A.S01E01.480p.DVDRip", 480),
        ("A.S01E01.HDTV", None),
    ],
)
def test_resolution(name, resolution):
    assert parse_release(name).resolution == resolution


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("A.2010.1080p.BluRay.Remux.AVC-GRP", Source.REMUX),
        ("A.2010.1080p.BluRay.x264-GRP", Source.BLURAY),
        ("A.2010.BDRip.x264-GRP", Source.BLURAY),
        ("A.S01E01.1080p.WEB-DL.DDP5.1.H.264-GRP", Source.WEBDL),
        ("A.S01E01.1080p.WEB.H264-GRP", Source.WEBDL),
        ("A.S01E01.1080p.WEBRip.x265-GRP", Source.WEBRIP),
        ("A.S01E01.720p.HDTV.x264-GRP", Source.HDTV),
        ("A.2001.DVDRip.XviD-GRP", Source.DVD),
        ("A.2023.HDCAM.x264", Source.CAM),
        ("A.2023.TELESYNC.x264", Source.TELESYNC),
        ("A.2023.1080p", None),
    ],
)
def test_source(name, source):
    assert parse_release(name).source == source


@pytest.mark.parametrize(
    ("name", "codec"),
    [
        ("A.S01E01.1080p.x265-GRP", "x265"),
        ("A.S01E01.1080p.H.265-GRP", "x265"),
        ("A.S01E01.1080p.HEVC-GRP", "x265"),
        ("A.S01E01.1080p.H264-GRP", "x264"),
        ("A.S01E01.1080p.AVC-GRP", "x264"),
        ("A.S01E01.1080p.AV1-GRP", "av1"),
        ("A.S01E01.DVDRip.XviD-GRP", "xvid"),
        ("A.S01E01.1080p", None),
    ],
)
def test_codec(name, codec):
    assert parse_release(name).codec == codec


@pytest.mark.parametrize(
    ("name", "group"),
    [
        ("Show.S01E01.1080p.WEB-DL.x264-NTb", "NTb"),
        ("Show.S01E01.1080p.WEB-DL", None),
        ("Show.S01E01.1080p.BluRay.DTS-HD.MA.5.1.x264-GRP", "GRP"),
        ("[SubsPlease] Show - Title (1080p)", "SubsPlease"),
        ("Show.S01E01.1080p.WEB-DL.x264-GRP.mkv", "GRP"),
        ("Show.S01E01.1080p.WEB-DL.x264-GRP [rarbg]", "GRP"),
    ],
)
def test_release_group(name, group):
    assert parse_release(name).group == group


def test_revision_and_languages():
    assert parse_release("Show.S01E01.PROPER.720p.HDTV").revision == 2
    assert parse_release("Show.S01E01.REPACK.720p.HDTV").revision == 2
    assert parse_release("Show.S01E01.720p.HDTV").revision == 1
    r = parse_release("Show.S01E01.MULTi.French.1080p.WEB")
    assert r.languages == ("fr", "multi")
    assert r.title == "Show"
    assert parse_release("Phim.Hay.2020.Vietnamese.1080p.WEB-DL").languages == ("vi",)


def test_title_with_hyphen_and_numbers():
    r = parse_release("Spider-Man.No.Way.Home.2021.1080p.BluRay.x264-GRP")
    assert (r.title, r.year) == ("Spider-Man No Way Home", 2021)
    r = parse_release("Mr.Robot.S01E01.1080p.WEB-DL-GRP")
    assert (r.title, r.group) == ("Mr Robot", "GRP")


def test_unparseable_name_falls_back_to_whole_title():
    r = parse_release("Just Some Words")
    assert r.title == "Just Some Words"
    assert (r.year, r.season, r.resolution, r.source, r.codec, r.group) == (None,) * 6
