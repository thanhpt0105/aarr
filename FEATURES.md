# aarr - Features

aarr is a standalone app combining the roles of Sonarr, Radarr, Bazarr, Prowlarr, and Seerr. It talks to external download clients (qBittorrent, SABnzbd) and hands finished media to a media server (Jellyfin).

Legend: **MVP** = first release, **v2** = after MVP, **later** = optional / needs a decision.

## 1. Movies (Radarr role)

| Feature | Phase |
|---|---|
| Add movie by metadata lookup (TMDB) | MVP |
| Monitored flag, quality profile, root folder per movie | MVP |
| Manual and automatic release search | MVP |
| Release scoring (quality, size, language, keywords, seeders) | MVP |
| Send release to download client | MVP |
| Completed-download import (hardlink / copy / move) | MVP |
| Naming templates and folder structure | MVP |
| Quality upgrades (cutoff) | v2 |
| Calendar (releases) and missing / cutoff-unmet lists | v2 |
| Collections, lists import (Trakt, IMDb) | later |

## 2. TV (Sonarr role)

| Feature | Phase |
|---|---|
| Add series by metadata lookup (TMDB / TVDB) | MVP |
| Seasons and episodes, per-season / per-episode monitoring | MVP |
| Quality profile and root folder per series | MVP |
| Episode and season-pack search, release selection | MVP |
| Completed-download import with episode matching | MVP |
| Naming templates (standard, daily, anime) | MVP |
| Upgrades, calendar, missing-episode list | v2 |
| Series types (standard / daily / anime), absolute numbering | v2 |
| Alternate titles and scene mapping | later |

## 3. Subtitles (Bazarr role)

| Feature | Phase |
|---|---|
| Language profiles (languages, forced, hearing-impaired) | v2 |
| Subtitle providers (OpenSubtitles, others) | v2 |
| Detect missing subtitles for library items | v2 |
| Automatic search, scoring, download, and save next to media | v2 |
| Embedded-subtitle detection (ffprobe) | v2 |
| Subtitle sync / timing fix, history, manual search | later |

## 4. Indexers (Prowlarr role)

| Feature | Phase |
|---|---|
| Torznab / Newznab indexer definitions with test | MVP |
| Category mapping (movies, TV) | MVP |
| Aggregated search across indexers | MVP |
| Indexer health, rate limits, and disable-on-failure | v2 |
| FlareSolverr proxy support | v2 |
| Prowlarr / Jackett as upstream source | v2 |
| Native indexer definitions (Cardigann-style) | later |

## 5. Requests (Seerr role)

| Feature | Phase |
|---|---|
| Discover / search movies and series | v2 |
| Users and roles, request permissions | v2 |
| Request approval workflow and auto-approve rules | v2 |
| Availability status per request | v2 |
| Notifications (email, Discord, webhook) | v2 |
| Jellyfin login / library sync | later |

## 6. Download clients

| Feature | Phase |
|---|---|
| qBittorrent adapter (WebUI API) | MVP |
| SABnzbd adapter | MVP |
| Connection test, category per media type | MVP |
| Queue polling: progress, state, errors | MVP |
| Remote path mapping (e.g. `/data` vs host path) | MVP |
| Pause / resume / remove | v2 |
| Failed-download handling and retry with next release | v2 |
| Additional clients (Transmission, NZBGet, Deluge) | later |

## 7. Shared platform

| Feature | Phase |
|---|---|
| Web UI and REST API with API key | MVP |
| SQLite persistence and migrations | MVP |
| Encrypted storage of integration credentials | MVP |
| Background scheduler (RSS sync, queue poll, scans) | MVP |
| Activity / history log, health checks | MVP |
| Media-server notify (Jellyfin library refresh) | v2 |
| Backup / restore | v2 |
| Import from existing Sonarr / Radarr / Bazarr config | later |
| PostgreSQL support | later |
| Docker image | MVP |
