from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from aarr.api.deps import SessionDep
from aarr.clients.base import DownloadClientError
from aarr.clients.factory import build_client
from aarr.models import DownloadClientConfig
from aarr.security import require_api_key


class ClientIn(BaseModel):
    name: str
    type: Literal["qbittorrent", "sabnzbd"]
    url: HttpUrl
    username: str | None = None
    secret: str | None = None  # write-only; omit on update to keep the stored value
    movie_category: str = "aarr-movies"
    tv_category: str = "aarr-tv"
    enabled: bool = True


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    url: str
    username: str | None
    has_secret: bool
    movie_category: str
    tv_category: str
    enabled: bool


class TestResult(BaseModel):
    ok: bool
    version: str | None = None
    error: str | None = None


router = APIRouter(
    prefix="/api/v1/download-clients",
    tags=["download-clients"],
    dependencies=[Depends(require_api_key)],
)


def _out(row: DownloadClientConfig) -> ClientOut:
    return ClientOut(
        id=row.id,
        name=row.name,
        type=row.type,
        url=row.url,
        username=row.username,
        has_secret=bool(row.secret_encrypted),
        movie_category=row.movie_category,
        tv_category=row.tv_category,
        enabled=row.enabled,
    )


def _get(session: Session, client_id: int) -> DownloadClientConfig:
    row = session.get(DownloadClientConfig, client_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Download client not found")
    return row


def _ensure_unique_name(session: Session, name: str, exclude_id: int | None = None) -> None:
    existing = session.scalar(select(DownloadClientConfig).where(DownloadClientConfig.name == name))
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A client named '{name}' already exists")


async def _probe(
    client_type: str, url: str, username: str | None, secret: str | None
) -> TestResult:
    client = build_client(client_type, url, username, secret)
    try:
        return TestResult(ok=True, version=await client.test())
    except DownloadClientError as exc:
        return TestResult(ok=False, error=str(exc))
    finally:
        await client.aclose()


@router.get("")
def list_clients(session: SessionDep) -> list[ClientOut]:
    rows = session.scalars(select(DownloadClientConfig).order_by(DownloadClientConfig.id))
    return [_out(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(body: ClientIn, request: Request, session: SessionDep) -> ClientOut:
    _ensure_unique_name(session, body.name)
    secrets = request.app.state.secrets
    row = DownloadClientConfig(
        name=body.name,
        type=body.type,
        url=str(body.url).rstrip("/"),
        username=body.username,
        secret_encrypted=secrets.encrypt(body.secret) if body.secret else None,
        movie_category=body.movie_category,
        tv_category=body.tv_category,
        enabled=body.enabled,
    )
    session.add(row)
    session.commit()
    return _out(row)


@router.post("/test")
async def test_unsaved(body: ClientIn) -> TestResult:
    return await _probe(body.type, str(body.url).rstrip("/"), body.username, body.secret)


@router.get("/{client_id}")
def get_client(client_id: int, session: SessionDep) -> ClientOut:
    return _out(_get(session, client_id))


@router.put("/{client_id}")
def update_client(
    client_id: int, body: ClientIn, request: Request, session: SessionDep
) -> ClientOut:
    row = _get(session, client_id)
    _ensure_unique_name(session, body.name, exclude_id=client_id)
    row.name = body.name
    row.type = body.type
    row.url = str(body.url).rstrip("/")
    row.username = body.username
    if body.secret is not None:
        row.secret_encrypted = (
            request.app.state.secrets.encrypt(body.secret) if body.secret else None
        )
    row.movie_category = body.movie_category
    row.tv_category = body.tv_category
    row.enabled = body.enabled
    session.commit()
    return _out(row)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: int, session: SessionDep) -> None:
    session.delete(_get(session, client_id))
    session.commit()


@router.post("/{client_id}/test")
async def test_saved(client_id: int, request: Request, session: SessionDep) -> TestResult:
    row = _get(session, client_id)
    encrypted = row.secret_encrypted
    secret = request.app.state.secrets.decrypt(encrypted) if encrypted else None
    return await _probe(row.type, row.url, row.username, secret)
