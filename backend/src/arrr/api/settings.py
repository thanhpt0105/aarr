from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from arrr.metadata.models import MetadataError
from arrr.metadata.tmdb import TmdbClient
from arrr.security import require_api_key
from arrr.services.settings import TMDB_KEY, TMDB_LANGUAGE, SettingsStore, tmdb_config

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


class KeyTestResult(BaseModel):
    ok: bool
    error: str | None = None


def _config(request: Request) -> tuple[str | None, str, str | None]:
    return tmdb_config(request.app.state.settings_store, request.app.state.settings.tmdb_api_key)


def _out(request: Request) -> MetadataSettingsOut:
    key, language, source = _config(request)
    return MetadataSettingsOut(
        has_tmdb_api_key=key is not None, tmdb_key_source=source, tmdb_language=language
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


@router.post("/metadata/test")
async def test_metadata_settings(request: Request) -> KeyTestResult:
    key, language, _ = _config(request)
    if key is None:
        return KeyTestResult(ok=False, error="TMDB API key is not configured")
    client = TmdbClient(key, language)
    try:
        await client.test()
        return KeyTestResult(ok=True)
    except MetadataError as exc:
        return KeyTestResult(ok=False, error=str(exc))
    finally:
        await client.aclose()
