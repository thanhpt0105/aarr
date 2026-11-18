from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from aarr import __version__
from aarr.api import (
    download_clients,
    indexers,
    library_settings,
    metadata,
    movies,
    path_mappings,
    queue,
    search,
    series,
    system,
)
from aarr.api import settings as settings_api
from aarr.config import Settings
from aarr.db import Database
from aarr.security import Secrets
from aarr.services.queue import QueueCache, poll_queues
from aarr.services.settings import SettingsStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db.migrate()
        scheduler = AsyncIOScheduler()
        if settings.queue_poll_seconds > 0:
            scheduler.add_job(
                poll_queues,
                "interval",
                seconds=settings.queue_poll_seconds,
                args=[app.state.db, app.state.secrets, app.state.queue_cache],
                id="poll_queues",
                max_instances=1,
                coalesce=True,
            )
        scheduler.start()
        app.state.scheduler = scheduler
        yield
        scheduler.shutdown(wait=False)

    app = FastAPI(title="aarr", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.data_dir / "aarr.db")
    app.state.secrets = Secrets(settings.data_dir)
    app.state.queue_cache = QueueCache()
    app.state.settings_store = SettingsStore(app.state.db, app.state.secrets)
    app.include_router(system.router)
    app.include_router(download_clients.router)
    app.include_router(indexers.router)
    app.include_router(metadata.router)
    app.include_router(library_settings.profiles_router)
    app.include_router(library_settings.folders_router)
    app.include_router(movies.router)
    app.include_router(series.router)
    app.include_router(path_mappings.router)
    app.include_router(queue.router)
    app.include_router(search.router)
    app.include_router(settings_api.router)
    return app


def run() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
