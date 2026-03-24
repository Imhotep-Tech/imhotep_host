# Architecture

This document describes how **Imhotep Host** orchestrates deployments using FastAPI, SQLAlchemy, Docker, PostgreSQL sidecars, and Cloudflare tunnels.

## Core Components

| Component | Responsibility |
| --- | --- |
| **FastAPI API Layer** | Exposes deployment and lifecycle endpoints under `/api/apps` and health endpoints under `/api/system`. |
| **SQLAlchemy + SQLite** | Persists app metadata and status (`Building`, `Running`, `Updating`, `Stopped`, `Failed`, `Update Failed`). |
| **Deployment Service** | Runs asynchronous deployment and redeploy pipelines via FastAPI `BackgroundTasks`. |
| **Docker Manager** | Handles image build/template injection, network creation, app/db/tunnel container lifecycle, and teardown. |
| **Cloudflare Tunnel Sidecar** | Creates dynamic public ingress URL for each app network via `cloudflared`. |

## Runtime Topology (Per App)

For app id `abc123`, the engine uses:

- **Network:** `imhotep_net_abc123`
- **App container:** `imhotep_run_abc123`
- **Database container (optional):** `imhotep_db_abc123`
- **Tunnel container:** `imhotep_tunnel_abc123`
- **Image tag:** `imhotep_app_abc123`

All sidecars are attached to the same isolated bridge network.

## Fresh Deployment Lifecycle

1. API writes app record with status **Building**.
2. Background pipeline clones repo and resolves build context.
3. Image is built/tagged as `imhotep_app_{app_id}`.
4. Per-app network is created.
5. Optional PostgreSQL sidecar is launched and DB env vars are injected.
6. Cloudflare tunnel sidecar is launched and live URL is extracted from logs.
7. App env vars are enriched (`ALLOWED_HOSTS`, `SITE_DOMAIN`, `CSRF_TRUSTED_ORIGINS`).
8. App container is launched.
9. App record is updated to status **Running** with `cloudflare_url`.

If any exception occurs, status is set to **Failed**.

## Zero-Downtime Redeploy Lifecycle

Redeploy is intentionally designed as a **build-then-swap** flow:

1. Clone + build new image while current app stays live.
2. Start candidate container `imhotep_run_{app_id}_candidate` on same network with existing env vars.
3. Wait and health-check candidate container state.
4. If candidate is healthy:
   - stop/remove old primary `imhotep_run_{app_id}`
   - rename candidate to `imhotep_run_{app_id}`
   - mark app as **Running**
5. If candidate fails:
   - remove candidate
   - keep original primary untouched
   - mark app as **Update Failed**

This is the key zero-downtime protection mechanism validated by integration tests.

## Current Failure Semantics

Based on current implementation and tests:

- **Redeploy failure:** candidate is cleaned up and old live container remains.
- **Fresh deploy partial failure:** app status becomes `Failed`; current behavior may leave DB/network resources until explicit teardown.

The testing suite intentionally documents this behavior so rollback policy can be tightened in future iterations.
