from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from arrr import __version__
from arrr.api import download_clients, indexers, path_mappings, queue, system
from arrr.config import Settings
from arrr.db import Database
from arrr.security import Secrets
from arrr.services.queue import QueueCache, poll_queues


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db.create_all()
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

    app = FastAPI(title="arrr", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.data_dir / "arrr.db")
    app.state.secrets = Secrets(settings.data_dir)
    app.state.queue_cache = QueueCache()
    app.include_router(system.router)
    app.include_router(download_clients.router)
    app.include_router(indexers.router)
    app.include_router(path_mappings.router)
    app.include_router(queue.router)
    return app


def run() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
