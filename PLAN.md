# arrr - Implementation Plan

See [FEATURES.md](FEATURES.md) for scope and phases.

## Tech stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLite, APScheduler, httpx
- Frontend: React + Vite + TypeScript (served by the backend in production)
- Packaging: single Docker image; shared `/data` mount for hardlinks
- Tests: pytest, respx (HTTP mocking)

## Layout

```
arrr/
  backend/
    pyproject.toml
    src/arrr/
      main.py          # FastAPI app factory
      config.py        # settings (env / data dir)
      db.py            # engine, session
      models/          # SQLAlchemy models
      api/             # routers
      clients/         # download client adapters (base, qbittorrent, sabnzbd)
      indexers/        # torznab / newznab
      metadata/        # TMDB provider
      services/        # search, decision, import, naming
      jobs/            # scheduled jobs
    tests/
  frontend/
  Dockerfile
```

## Milestones

### M0 - Foundation
- Project scaffold, settings, SQLite + Alembic, health endpoint, API-key auth
- Credential encryption helper
- Scheduler wiring and job registry
- CI-style local checks: pytest, ruff
- Docker: multi-stage image (non-root, `/config` volume, healthcheck) and example `docker-compose.yml`; every milestone must keep the image building

### M1 - Download clients
- `DownloadClient` interface: `test()`, `add(release, category)`, `queue()`, `remove(id)`
- qBittorrent adapter (cookie auth, categories, torrent state mapping)
- SABnzbd adapter (API key, queue + history)
- Client config CRUD API; remote path mapping
- Queue poller job storing normalized queue items

### M2 - Indexers and search
- Torznab / Newznab client with caps and category parsing
- Indexer config CRUD with test
- Aggregated search returning normalized `Release` objects
- Release parser (title -> quality, source, codec, group, season/episode)

### M3 - Metadata and library
- TMDB provider (movie + series lookup)
- Models: Movie, Series, Season, Episode, QualityProfile, RootFolder
- CRUD APIs for adding / monitoring items

### M4 - Decision, grab, import
- Decision engine: profile match, size limits, scoring, rejections with reasons
- Grab flow: search -> decision -> client add -> tracked download
- Completed-download import: file detection, episode matching, naming templates, hardlink/copy/move, history
- Failure handling and retry

### M5 - Web UI (MVP)
- Library views, add/search flow, interactive release search, queue, history, settings

### M6 - v2 features
- Upgrades, calendar, missing lists, health checks, backup/restore
- Subtitles (language profiles, providers, scanner)
- Requests (users, roles, approval, notifications)
- Prowlarr / Jackett / FlareSolverr integration

### M7 - Hardening and release
- Path-mapping, duplicate-import, restart-recovery tests
- Publish image, docs, compose example that fits the media-stack setup

## MVP definition

Add a movie or series -> search indexers -> pick/auto-select a release -> send to qBittorrent or SABnzbd -> see queue progress -> import into the library with correct naming.

## Risks and decisions

- Release parsing and episode matching are the main correctness risk; build a large fixture-based test suite early.
- Native indexer definitions are costly; use Torznab/Newznab plus Prowlarr/Jackett upstream first.
- TVDB requires a key/licence; start with TMDB for both movies and TV.
- Hardlinks require source and library on the same filesystem; validate in a setup check.
