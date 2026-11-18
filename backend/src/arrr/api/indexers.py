from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from arrr.api.deps import SessionDep
from arrr.indexers.models import IndexerError
from arrr.indexers.torznab import TorznabClient
from arrr.models import IndexerConfig
from arrr.security import require_api_key


class IndexerIn(BaseModel):
    name: str
    protocol: Literal["torrent", "usenet"]
    url: HttpUrl
    api_key: str | None = None  # write-only; omit on update to keep the stored value
    enabled: bool = True
    priority: int = 25


class IndexerOut(BaseModel):
    id: int
    name: str
    protocol: str
    url: str
    has_api_key: bool
    enabled: bool
    priority: int


class IndexerTestResult(BaseModel):
    ok: bool
    title: str | None = None
    search_modes: list[str] = []
    category_count: int = 0
    error: str | None = None


router = APIRouter(
    prefix="/api/v1/indexers", tags=["indexers"], dependencies=[Depends(require_api_key)]
)


def _out(row: IndexerConfig) -> IndexerOut:
    return IndexerOut(
        id=row.id,
        name=row.name,
        protocol=row.protocol,
        url=row.url,
        has_api_key=bool(row.api_key_encrypted),
        enabled=row.enabled,
        priority=row.priority,
    )


def _get(session: Session, indexer_id: int) -> IndexerConfig:
    row = session.get(IndexerConfig, indexer_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Indexer not found")
    return row


def _ensure_unique_name(session: Session, name: str, exclude_id: int | None = None) -> None:
    existing = session.scalar(select(IndexerConfig).where(IndexerConfig.name == name))
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"An indexer named '{name}' already exists")


async def _probe(name: str, url: str, api_key: str | None, protocol: str) -> IndexerTestResult:
    client = TorznabClient(name, url, api_key, protocol)  # type: ignore[arg-type]
    try:
        caps = await client.caps()
        return IndexerTestResult(
            ok=True,
            title=caps.title,
            search_modes=sorted(caps.search_modes),
            category_count=len(caps.categories),
        )
    except IndexerError as exc:
        return IndexerTestResult(ok=False, error=str(exc))
    finally:
        await client.aclose()


@router.get("")
def list_indexers(session: SessionDep) -> list[IndexerOut]:
    return [_out(r) for r in session.scalars(select(IndexerConfig).order_by(IndexerConfig.id))]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_indexer(body: IndexerIn, request: Request, session: SessionDep) -> IndexerOut:
    _ensure_unique_name(session, body.name)
    row = IndexerConfig(
        name=body.name,
        protocol=body.protocol,
        url=str(body.url),
        api_key_encrypted=request.app.state.secrets.encrypt(body.api_key) if body.api_key else None,
        enabled=body.enabled,
        priority=body.priority,
    )
    session.add(row)
    session.commit()
    return _out(row)


@router.post("/test")
async def test_unsaved(body: IndexerIn) -> IndexerTestResult:
    return await _probe(body.name, str(body.url), body.api_key, body.protocol)


@router.get("/{indexer_id}")
def get_indexer(indexer_id: int, session: SessionDep) -> IndexerOut:
    return _out(_get(session, indexer_id))


@router.put("/{indexer_id}")
def update_indexer(
    indexer_id: int, body: IndexerIn, request: Request, session: SessionDep
) -> IndexerOut:
    row = _get(session, indexer_id)
    _ensure_unique_name(session, body.name, exclude_id=indexer_id)
    row.name = body.name
    row.protocol = body.protocol
    row.url = str(body.url)
    if body.api_key is not None:
        row.api_key_encrypted = (
            request.app.state.secrets.encrypt(body.api_key) if body.api_key else None
        )
    row.enabled = body.enabled
    row.priority = body.priority
    session.commit()
    return _out(row)


@router.delete("/{indexer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_indexer(indexer_id: int, session: SessionDep) -> None:
    session.delete(_get(session, indexer_id))
    session.commit()


@router.post("/{indexer_id}/test")
async def test_saved(indexer_id: int, request: Request, session: SessionDep) -> IndexerTestResult:
    row = _get(session, indexer_id)
    encrypted = row.api_key_encrypted
    api_key = request.app.state.secrets.decrypt(encrypted) if encrypted else None
    return await _probe(row.name, row.url, api_key, row.protocol)
