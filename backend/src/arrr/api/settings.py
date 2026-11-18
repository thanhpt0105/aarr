from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from arrr.security import require_api_key
from arrr.services.settings import SettingsStore

TMDB_KEY = "tmdb_api_key"
TMDB_LANGUAGE = "tmdb_language"
DEFAULT_LANGUAGE = "en-US"

router = APIRouter(
    prefix="/api/v1/settings", tags=["settings"], dependencies=[Depends(require_api_key)]
)


class MetadataSettingsIn(BaseModel):
    tmdb_api_key: str | None = None  # omit to keep; empty string clears
    tmdb_language: str | None = Field(default=None, pattern=r"^[a-z]{2}-[A-Z]{2}$")  # en-US


class MetadataSettingsOut(BaseModel):
    has_tmdb_api_key: bool
    tmdb_key_source: Literal["settings", "env"] | None
    tmdb_language: str


def effective_tmdb_key(request: Request) -> str | None:
    store: SettingsStore = request.app.state.settings_store
    return store.get(TMDB_KEY) or request.app.state.settings.tmdb_api_key


def _out(request: Request) -> MetadataSettingsOut:
    store: SettingsStore = request.app.state.settings_store
    source = "settings" if store.get(TMDB_KEY) else None
    if source is None and request.app.state.settings.tmdb_api_key:
        source = "env"
    return MetadataSettingsOut(
        has_tmdb_api_key=source is not None,
        tmdb_key_source=source,
        tmdb_language=store.get(TMDB_LANGUAGE) or DEFAULT_LANGUAGE,
    )


@router.get("/metadata")
def get_metadata_settings(request: Request) -> MetadataSettingsOut:
    return _out(request)


@router.put("/metadata")
def put_metadata_settings(body: MetadataSettingsIn, request: Request) -> MetadataSettingsOut:
    store: SettingsStore = request.app.state.settings_store
    if body.tmdb_api_key is not None:
        store.set(TMDB_KEY, body.tmdb_api_key.strip(), secret=True)
    if body.tmdb_language is not None:
        store.set(TMDB_LANGUAGE, body.tmdb_language)
    return _out(request)
