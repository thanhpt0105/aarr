# aarr - Progress and handoff

Single source of truth for "where are we". Read this first on a new device, then [PLAN.md](PLAN.md) (milestones) and [FEATURES.md](FEATURES.md) (scope).

Last updated: 2026-11-18 | Status: **M0-M3 done, M4 next** | Tests: 187 passing, 1 skipped (POSIX-only) | Repo: https://github.com/thanhpt0105/aarr

`arrr.md` is the original one-line brief. The project was renamed arrr -> aarr; the package is `aarr`, env prefix `AARR_`.

## Resume on a new device

```powershell
git clone https://github.com/thanhpt0105/aarr.git
cd aarr/backend
py -3.12 -m venv .venv            # Linux/macOS: python3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1      # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

pytest -q                         # expect all green
ruff check src tests; ruff format --check src tests

$env:AARR_DATA_DIR = "./data"; aarr   # serves on :8686, API key is written to data/api_key
```

Docker (from the repo root): `docker build -t aarr:dev .` or `docker compose up -d --build`.
The image is multi-stage, runs as uid 1000 (override with `user:`), stores everything in `/config`, and has a healthcheck.

To continue with an AI agent: "Read PROGRESS.md and PLAN.md, then continue with M4."

## What is implemented

| Milestone | State | Contents |
|---|---|---|
| M0 Foundation | done | FastAPI app factory, settings (`AARR_*` env), SQLite + SQLAlchemy 2, Alembic migrations applied on startup, API-key auth (`X-Api-Key`), Fernet-encrypted secrets, APScheduler, Docker image + compose |
| M1 Download clients | done | qBittorrent and SABnzbd adapters, client config CRUD + connection test, remote path mappings, queue poller job and queue API |
| M2 Indexers and search | done | Release title parser, Torznab/Newznab client (safe XML), indexer CRUD + test, concurrent multi-indexer search with parsed release info |
| M3 Metadata and library | done | TMDB client, settings store (TMDB key/language), quality profiles (3 seeded), root folders, movies, series/seasons/episodes with monitor rules |
| M4 Decision, grab, import | **not started** | see "Next steps" |
| M5 Web UI | not started | |
| M6 v2 features | not started | upgrades, calendar, subtitles, requests, Prowlarr/Jackett |
| M7 Hardening and release | not started | |

### API surface (all under `/api/v1`, all need `X-Api-Key` except `health`)

- `GET health` (public), `GET system/status`
- `download-clients` CRUD, `POST download-clients/test`, `POST download-clients/{id}/test`
- `path-mappings` list/create/delete
- `queue`, `POST queue/refresh`
- `indexers` CRUD, `POST indexers/test`, `POST indexers/{id}/test`
- `search` (query params: `q, kind=search|movie|tv, season, episode, imdb_id, tmdb_id, tvdb_id, indexer_id, limit`)
- `settings/metadata` GET/PUT, `POST settings/metadata/test`
- `metadata/search?type=movie|tv&q=` (results include `library_id` when already added)
- `quality-profiles` CRUD, `root-folders` list/create/delete
- `movies` list/add/get/patch/delete, `POST movies/{id}/refresh`
- `series` list/add/get/patch/delete, `POST series/{id}/refresh`, `GET series/{id}/episodes`, `PATCH series/{id}/seasons/{n}`, `PATCH series/{id}/episodes/{episode_id}`

### Code map (`backend/src/aarr`)

- `main.py` app factory + lifespan (migrate, scheduler). `config.py` env settings. `db.py` engine, `UTCDateTime`, `Database.migrate()`. `security.py` API key + encryption.
- `api/` routers. `clients/` download client adapters. `indexers/` Torznab client. `metadata/` TMDB client and provider-neutral models.
- `services/` parser, search, queue poller, path mapping, naming, series sync, settings store.
- `models/` SQLAlchemy models. `migrations/` Alembic (0001-0005).

## Working conventions

- **Commit after each finished feature**, with tests in the same commit. Message style: `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`.
- Before committing: `pytest -q`, `ruff check src tests`, `ruff format src tests`. Line length is 100.
- HTTP is mocked with `respx`; API tests use the `client` (no auth) and `authed` fixtures from `tests/conftest.py`.
- **Schema changes need a migration** (a test fails if models and migrations drift):
  ```powershell
  cd backend
  Remove-Item alembic-dev.db -ErrorAction SilentlyContinue
  alembic -c alembic.ini upgrade head
  alembic -c alembic.ini revision --autogenerate -m "what changed" --rev-id 0006
  Remove-Item alembic-dev.db
  ```
  Review the generated file; `UTCDateTime` is rendered as `sa.DateTime()` automatically. Data seeding belongs in the migration (see 0003).
- Secrets (client passwords, indexer keys, TMDB key) are encrypted at rest and never returned by the API. On update, omitting the secret keeps the stored value.
- In `main.py` the settings router is imported as `settings_api` because `create_app` has a `settings` parameter.
- Keep Docker building after every milestone (rebuild and smoke-test the container).

## Design decisions

- **Metadata:** TMDB only for now (key via `PUT /settings/metadata` or `AARR_TMDB_API_KEY`). Keyless providers (IMDb datasets, TVmaze) were evaluated and deferred; IMDb datasets are personal/non-commercial and must be downloaded at runtime, not bundled.
- **Indexer URL** is the full Torznab/Newznab endpoint (e.g. a Prowlarr or Jackett feed URL). Native indexer definitions are out of scope for now.
- **qBittorrent behind Gluetun:** use the `gluetun` host in the client URL. Default categories are `aarr-movies` / `aarr-tv`.
- **Hardlinks** require the download client and aarr to share one `/data` mount; use path mappings when the client reports different paths.
- Series refresh keeps user monitoring choices, adds new episodes, and deletes episodes removed upstream. **Revisit this once episodes can have files (M4).**
- Folder names come from `services/naming.py` (`safe_name`): colon becomes ` -`, illegal characters removed, path separators impossible.

## Known gaps and caveats

- Everything external is tested against mocks only: no live qBittorrent, SABnzbd, indexer, or real-TMDB-key run yet.
- Quality profiles only filter by resolution; source, codec, size, language and custom scoring are not modelled.
- The queue snapshot is in memory; there is no persisted download tracking yet.
- Search ordering is a placeholder (seeders, then indexer priority).
- No web UI, no users/roles (single API key), no CI workflow yet.
- Windows: the secret-file permission test is skipped (POSIX only); it passes in the Linux image.

## Next steps: M4 (decision, grab, import)

1. **Decision engine** (`services/decision.py`): given a release and a target (movie, episode(s), or season pack) plus the quality profile, return accept/reject with reasons and a score. Rules: resolution allowed, title and year match, season/episode match, size limits, minimum seeders, protocol has an enabled client, PROPER/REPACK preference.
2. **Interactive search per item:** `GET /movies/{id}/releases` and `GET /series/{id}/episodes/{episode_id}/releases` (and season), returning decisions.
3. **Grab flow + tracking:** `Download` model/migration (client, client item id, target, status, release info, error), `POST /grab`, sync status from the queue poller.
4. **Importer:** detect completed downloads (apply path mappings), find video files, match episodes, rename via templates, hardlink/copy/move, `MovieFile` / `EpisodeFile` models, history table.
5. **Failure handling:** failed download -> blocklist the release and retry with the next best.
6. Then an automatic search job for monitored items (RSS sync), and M5 (web UI).
