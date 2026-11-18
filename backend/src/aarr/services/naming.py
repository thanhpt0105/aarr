import re

_ILLEGAL = re.compile(r'[<>"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10))} | {
    f"LPT{i}" for i in range(1, 10)
}


def safe_name(name: str) -> str:
    """Make a title safe to use as a single file or folder name on any platform."""
    cleaned = name.replace(":", " -")
    cleaned = _ILLEGAL.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return "Unknown"
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned += "_"
    return cleaned


def movie_folder_name(title: str, year: int | None) -> str:
    return safe_name(f"{title} ({year})" if year else title)


def series_folder_name(title: str, year: int | None) -> str:
    return movie_folder_name(title, year)
