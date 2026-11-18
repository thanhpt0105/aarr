from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from arrr.metadata.tmdb import TmdbClient
from arrr.services.settings import tmdb_config


async def get_tmdb(request: Request) -> AsyncIterator[TmdbClient]:
    key, language, _ = tmdb_config(
        request.app.state.settings_store, request.app.state.settings.tmdb_api_key
    )
    if key is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TMDB API key is not configured")
    client = TmdbClient(key, language)
    try:
        yield client
    finally:
        await client.aclose()


TmdbDep = Annotated[TmdbClient, Depends(get_tmdb)]
