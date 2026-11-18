from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from arrr import __version__
from arrr.api import system
from arrr.config import Settings
from arrr.db import Database
from arrr.security import Secrets


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db.create_all()
        scheduler = AsyncIOScheduler()
        scheduler.start()
        app.state.scheduler = scheduler
        yield
        scheduler.shutdown(wait=False)

    app = FastAPI(title="arrr", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.data_dir / "arrr.db")
    app.state.secrets = Secrets(settings.data_dir)
    app.include_router(system.router)
    return app


def run() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
