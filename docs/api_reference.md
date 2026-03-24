# API Reference

This reference is based on the current FastAPI routes in `engine/api/routes/apps.py`.

## Schemas

### `AppCreate` request body

```json
{
  "name": "my-app",
  "github_url": "https://github.com/example/repo.git",
  "branch": "main",
  "stack": "django",
  "root_directory": "/",
  "include_db": false,
  "force_template": false,
  "env_vars": {
    "DJANGO_DEBUG": "true"
  }
}
```

### `AppResponse` shape

```json
{
  "id": "a1b2c3",
  "name": "my-app",
  "cloudflare_url": "https://example.trycloudflare.com",
  "status": "Running"
}
```

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| **POST** | `/api/apps/deploy` | Create app record and trigger background deployment pipeline. |
| **PUT** | `/api/apps/{app_id}` | Update app metadata/env vars and trigger redeploy pipeline. |
| **POST** | `/api/apps/{app_id}/redeploy` | Trigger zero-downtime redeploy without changing metadata. |
| **POST** | `/api/apps/{app_id}/execute` | Run one-off command in running app container. |
| **POST** | `/api/apps/{app_id}/stop` | Stop running app container and set status `Stopped`. |
| **DELETE** | `/api/apps/{app_id}` | Remove all Docker resources and delete DB record. |

---

## `POST /api/apps/deploy`

Creates a new app row with status `Building`, then schedules `run_deployment_pipeline`.

### Request

`AppCreate` JSON body.

### Success response (`200`)

```json
{
  "id": "a1b2c3",
  "name": "my-app",
  "cloudflare_url": null,
  "status": "Building"
}
```

---

## `PUT /api/apps/{app_id}`

Updates app metadata/env vars and schedules redeploy. Existing infra vars are preserved (DB/tunnel-related keys).

### Request

`AppCreate` JSON body.

### Success response (`200`)

Returns `AppResponse` (typically `status: "Updating"` immediately after call).

### Error responses

- `404` if app does not exist.

---

## `POST /api/apps/{app_id}/redeploy`

Triggers the zero-downtime redeploy pipeline for an existing app.

### Query parameters

- `root_directory` (optional, default `/`)

### Success response (`200`)

Returns current app state (status set to `Updating` before background job runs).

### Error responses

- `404` if app does not exist.

---

## `POST /api/apps/{app_id}/execute`

Runs a shell command in the running app container (`imhotep_run_{app_id}`) with working directory `/app`.

### Request

```json
{
  "command": "python manage.py migrate"
}
```

### Success response (`200`)

```json
{
  "exit_code": 0,
  "output": "..."
}
```

### Error responses

- `404` if app record does not exist.
- `400` if app status is not `Running`.
- `404` if container is not found.
- `500` for unexpected runtime errors.

---

## `POST /api/apps/{app_id}/stop`

Stops the running app container and marks app status as `Stopped`.

### Success response (`200`)

Returns `AppResponse` with status `Stopped`.

### Error responses

- `404` if app does not exist.
- `500` if Docker stop operation fails unexpectedly.

---

## `DELETE /api/apps/{app_id}`

Performs full teardown:

- tunnel container
- app container
- database container
- isolated network
- application record in SQLite

### Success response (`200`)

```json
{
  "detail": "Application my-app deleted completely."
}
```

### Error responses

- `404` if app does not exist.
