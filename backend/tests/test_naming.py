import pytest

from aarr.services.naming import movie_folder_name, safe_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Inception", "Inception"),
        ("Star Wars: A New Hope", "Star Wars - A New Hope"),
        ("AC/DC: Let There Be Rock", "ACDC - Let There Be Rock"),
        ('What "If"?', "What If"),
        ("  Spaced   out  ", "Spaced out"),
        ("Trailing dots...", "Trailing dots"),
        ("a\\b|c*d<e>f", "abcdef"),
        ("..", "Unknown"),
        ("", "Unknown"),
        ("???", "Unknown"),
        ("CON", "CON_"),
        ("nul.txt", "nul.txt_"),
        ("Phim Việt: Tập 1", "Phim Việt - Tập 1"),
    ],
)
def test_safe_name(raw, expected):
    assert safe_name(raw) == expected


def test_result_never_contains_path_separators():
    for raw in ["../../etc/passwd", "..\\..\\windows", "/abs/path", "C:\\x"]:
        out = safe_name(raw)
        assert "/" not in out and "\\" not in out and not out.startswith(".")


def test_movie_folder_name():
    assert movie_folder_name("Inception", 2010) == "Inception (2010)"
    assert movie_folder_name("Inception", None) == "Inception"
    assert movie_folder_name("Mission: Impossible", 1996) == "Mission - Impossible (1996)"
