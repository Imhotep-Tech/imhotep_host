**[Home](../README.md)** · **[Architecture](architecture.md)** · **[API Reference](api_reference.md)** · **[Deployment Guide](deployment_guide.md)** · **Testing** (you are here) · **[Contributing](../CONTRIBUTING.md)**

> **Under development:** Test layout, fixtures, and CI steps may change. After pulling latest `main`, run `pytest -v tests` from `engine/` and read `engine/tests/conftest.py` for current mocking behavior.

# Testing Guide

Imhotep Host uses integration-style tests to validate the deployment lifecycle while keeping runtime fast and deterministic.

## Test Stack

| Tool | Role |
| --- | --- |
| **Pytest** | Test runner and fixture orchestration. |
| **FastAPI TestClient** | Calls API endpoints as a real client. |
| **SQLAlchemy (temp SQLite)** | Isolated per-test database state. |
| **Docker SDK** | Verifies actual Docker networks/containers/image tags. |
| **`unittest.mock.patch`** | Mocks expensive or external operations. |

## Fixture Strategy (`engine/tests/conftest.py`)

Core fixture behavior:

- Creates a temporary SQLite DB and overrides `SessionLocal` in:
  - `db.database`
  - `api.routes.apps`
  - `services.deployment`
- Forces FastAPI background tasks to run **inline** so tests can assert final state immediately.
- Mocks heavy/external deployment pieces:
  - `clone_public_repo` → temp directory
  - `resolve_and_build` → pulls lightweight image and tags `imhotep_app_{app_id}`
  - `deploy_cloudflare_tunnel` → static mock URL
  - `time.sleep` in deployment pipeline → no-op
- Auto-cleans all Docker resources prefixed with `imhotep_` after each test.

## Why Heavy Builds Are Mocked

Building real framework images (for example large Django repos) slows CI significantly and introduces non-determinism.

The suite preserves **orchestration realism** by still creating real containers/networks with Docker SDK, while replacing only:

- Git clone cost
- Image build cost
- External Cloudflare network dependency

## Lifecycle Coverage (`engine/tests/test_deployment_lifecycle.py`)

| Test Area | What is validated |
| --- | --- |
| **Full deploy flow** | Deploy endpoint, DB record transition, network + app + DB containers running. |
| **Redeploy swap** | Candidate-to-primary rename swap, old primary replaced, candidate removed. |
| **Teardown** | Full cleanup of app/db containers and network. |
| **DB preservation on redeploy** | DB container ID/timestamp unchanged across updates. |
| **Env var propagation** | New vars from `PUT` reach newly swapped primary container. |
| **Failed candidate protection** | Broken candidate aborts swap; live container stays serving; status `Update Failed`. |
| **Stop/execute behavior** | Command execution on running app and stop endpoint behavior. |
| **Partial deploy failure** | Fresh-deploy failure behavior and current rollback semantics are documented. |
| **Recovery and guardrails** | Redeploy from stopped state and API protection for invalid IDs/non-running execute calls. |

## Running Tests Locally

From repository root (after [cloning](../README.md#get-the-repository-and-run-locally-step-by-step)):

```bash
cd engine
pytest -v tests/test_deployment_lifecycle.py
```

Run full test tree:

```bash
cd engine
pytest -v tests
```

## CI Notes

GitHub Actions workflow (`.github/workflows/test.yml`) runs tests on pushes to `main`:

1. Set up Python
2. Install `engine/requirements.txt` and `pytest`
3. Execute `pytest -v tests` from `engine/`

Because Ubuntu GitHub runners include Docker, Docker SDK assertions run natively in CI.
