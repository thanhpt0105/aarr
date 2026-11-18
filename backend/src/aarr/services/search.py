import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select

from aarr.db import Database
from aarr.indexers.models import IndexerError, Release, SearchQuery
from aarr.indexers.torznab import TorznabClient
from aarr.models import IndexerConfig
from aarr.security import Secrets

DEFAULT_CATEGORIES = {"movie": (2000,), "tv": (5000,)}


@dataclass
class SearchResult:
    releases: list[Release] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # indexer name -> error


def _load_indexers(db: Database, indexer_id: int | None) -> list[IndexerConfig]:
    session = next(db.session())
    try:
        query = select(IndexerConfig).where(IndexerConfig.enabled.is_(True))
        if indexer_id is not None:
            query = query.where(IndexerConfig.id == indexer_id)
        return list(session.scalars(query.order_by(IndexerConfig.priority, IndexerConfig.id)))
    finally:
        session.close()


async def _search_one(
    cfg: IndexerConfig, secrets: Secrets, query: SearchQuery
) -> tuple[IndexerConfig, list[Release] | IndexerError]:
    api_key = secrets.decrypt(cfg.api_key_encrypted) if cfg.api_key_encrypted else None
    client = TorznabClient(cfg.name, cfg.url, api_key, cfg.protocol)  # type: ignore[arg-type]
    try:
        return cfg, await client.search(query)
    except IndexerError as exc:
        return cfg, exc
    finally:
        await client.aclose()


def _dedupe(releases: list[Release]) -> list[Release]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for r in releases:
        key = (r.indexer, r.guid)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


async def search_all(
    db: Database, secrets: Secrets, query: SearchQuery, indexer_id: int | None = None
) -> SearchResult:
    """Query enabled indexers concurrently; a failing indexer is reported, not fatal."""
    if not query.categories and query.kind in DEFAULT_CATEGORIES:
        query = SearchQuery(**{**vars(query), "categories": DEFAULT_CATEGORIES[query.kind]})

    configs = _load_indexers(db, indexer_id)
    outcomes = await asyncio.gather(*(_search_one(c, secrets, query) for c in configs))

    result = SearchResult()
    ranked: list[tuple[int, Release]] = []
    for cfg, outcome in outcomes:
        if isinstance(outcome, IndexerError):
            result.errors[cfg.name] = str(outcome)
        else:
            ranked.extend((cfg.priority, r) for r in outcome)

    # Most seeders first, then lowest indexer priority number; usenet (no seeders) sorts last.
    ranked.sort(key=lambda pr: (-(pr[1].seeders or 0), pr[0]))
    result.releases = _dedupe([r for _, r in ranked])
    return result
