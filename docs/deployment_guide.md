**[Home](../README.md)** · **[Architecture](architecture.md)** · **[API Reference](api_reference.md)** · **Deployment Guide** (you are here) · **[Testing](testing.md)** · **[Contributing](../CONTRIBUTING.md)**

> **Under development:** Build steps, template names, and env injection follow the current engine. Expect adjustments as templates and rollback behavior mature.

# Deployment Guide

This guide explains how Imhotep Host builds and runs applications using the deployment pipeline in `engine/services/deployment.py` and `engine/services/docker_manager.py`.

## Build Resolution and Template Injection

`resolve_and_build(...)` performs:

1. **Root path resolution** from `root_directory`.
2. **Dockerfile detection** in the selected build path.
3. **Template injection** if needed:
   - If no native `Dockerfile` exists, inject `<framework>.Dockerfile` from `engine/templates`.
   - If `force_template=true`, overwrite native Dockerfile with template.
4. **Optional template utility injection** from `engine/templates_utils/<Framework>.py`.
5. **Docker build** with image tag `imhotep_app_{app_id}`.

## Environment Variable Lifecycle

Environment variables are layered and enriched during deployment.

| Stage | Behavior |
| --- | --- |
| **Initial request** | User-supplied `env_vars` accepted from `AppCreate`. |
| **Normalization** | `FORCE_TEMPLATE` and `RELATIVE_ROOT` are persisted in env vars. |
| **DB provisioning (optional)** | Injects `DATABASE_URL`, `DATABASE_*`, and `POSTGRES_*` keys. |
| **Tunnel resolution** | Adds/extends `ALLOWED_HOSTS` and sets `SITE_DOMAIN`, `CSRF_TRUSTED_ORIGINS`. |
| **Redeploy** | Reuses saved env vars for candidate startup; `PUT` preserves infra keys while merging user changes. |

### DB-related injected keys

- `DATABASE_URL`
- `DATABASE_NAME`
- `DATABASE_USER`
- `DATABASE_PASSWORD`
- `DATABASE_HOST`
- `DATABASE_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

### Tunnel-related injected keys

- `ALLOWED_HOSTS` (appended with generated host)
- `SITE_DOMAIN`
- `CSRF_TRUSTED_ORIGINS`

## Deployment Stages (Fresh Deploy)

| Stage | Action |
| --- | --- |
| **Clone** | Clone public Git repo and checkout branch. |
| **Build** | Resolve Dockerfile and build image. |
| **Network** | Create isolated bridge network `imhotep_net_{app_id}`. |
| **DB (optional)** | Launch PostgreSQL sidecar and wait for initialization. |
| **Tunnel** | Launch cloudflared sidecar and parse live URL from logs. |
| **App launch** | Start main app container with enriched env vars. |
| **Persist** | Update app record to `Running` with cloudflare URL and final env vars. |

## Zero-Downtime Redeploy Details

`run_redeploy_pipeline(...)` keeps the current app live while preparing the replacement:

1. Build new image.
2. Launch candidate container (`imhotep_run_{app_id}_candidate`).
3. Wait and verify candidate stays `running`.
4. If healthy, remove old primary and rename candidate to primary name.
5. If unhealthy, remove candidate and keep old primary running.

This ensures traffic continuity because the tunnel continues targeting the stable container name `imhotep_run_{app_id}`.

## Requirements for User Applications

Imhotep Host can run any containerized app, but Django projects should be production-ready for reverse-proxy deployment:

| Requirement | Why it matters |
| --- | --- |
| **Static files strategy** (for example `whitenoise`) | Prevents static asset failures when no external static server is used. |
| **`STATIC_ROOT` configured** | Needed for proper static collection in production images. |
| **Proxy-aware HTTPS handling** (`SECURE_PROXY_SSL_HEADER`) | Correctly identifies HTTPS requests behind Cloudflare tunnel. |
| **Host/origin config** (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) | Engine injects tunnel host/origin; app must honor these settings. |

## Operational Notes

- Fresh deployment failures currently mark app status `Failed`; partial resources (DB/network) may remain until teardown.
- Redeploy failures are safer by design: failed candidate is removed and original live container remains active.
