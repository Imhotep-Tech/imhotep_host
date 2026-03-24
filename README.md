# Imhotep Host

**[Home](README.md)** · **[Architecture](docs/architecture.md)** · **[API Reference](docs/api_reference.md)** · **[Deployment Guide](docs/deployment_guide.md)** · **[Testing](docs/testing.md)** · **[Contributing](CONTRIBUTING.md)**

> **Under development:** Imhotep Host is **actively under development**. APIs, deployment behavior, and documentation may change without a major-version bump. Treat this repository as early-stage software; validate behavior against the current codebase and tests before relying on it in production.

**Imhotep Host** is a FastAPI-based zero-downtime PaaS orchestrator that deploys Git-backed applications into isolated Docker networks, optionally provisions a PostgreSQL sidecar, and exposes apps through Cloudflare tunnels.

## Get the repository and run locally (step by step)

Follow these steps from a clean machine to get the **engine API** running. The UI and one-click production installs are still evolving—see **[Contributing](CONTRIBUTING.md)** and the docs below for the current scope.

1. **Clone the repository** (use your fork URL or the upstream URL you were given):

   ```bash
   git clone https://github.com/<owner>/imhotep_host.git
   cd imhotep_host
   ```

2. **Create a virtual environment** (recommended):

   ```bash
   cd engine
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies** and **uvicorn**:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   pip install uvicorn
   ```

4. **Start Docker** on your machine (Docker Desktop or your OS daemon). The engine uses the Docker API for deployments.

5. **Run the FastAPI server**:

   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

6. **Verify** the API is up:

   ```bash
   curl http://localhost:8000/
   curl http://localhost:8000/api/system/health
   ```

7. **Optional — run integration tests** (requires Docker; see [Testing](docs/testing.md)):

   ```bash
   pip install pytest
   pytest -v tests
   ```

## What It Does

| Capability | Description |
| --- | --- |
| **Deploy from GitHub** | Clones a public repo, resolves build context, and builds image tag `imhotep_app_{app_id}`. |
| **Template injection** | Injects framework templates (for example `django.Dockerfile`) when a native Dockerfile is missing or when forced. |
| **Per-app isolation** | Creates an isolated Docker bridge network `imhotep_net_{app_id}` for app and sidecars. |
| **Optional database sidecar** | Provisions `postgres:15-alpine` as `imhotep_db_{app_id}` and injects runtime DB environment variables. |
| **Public tunnel** | Starts `cloudflare/cloudflared` as `imhotep_tunnel_{app_id}` and extracts a live `trycloudflare.com` URL. |
| **Zero-downtime redeploy** | Starts candidate container, health-checks it, then swaps it into the primary container name. |

## Quick start (summary)

If you already cloned the repo and are in `engine/`:

| Step | Action |
| --- | --- |
| **Prerequisites** | **Python 3.10+**, **Docker daemon running** |
| **Install** | `pip install -r requirements.txt && pip install uvicorn` |
| **Run** | `uvicorn main:app --reload --host 0.0.0.0 --port 8000` |
| **Health** | `curl http://localhost:8000/api/system/health` |

## Documentation

In-depth guides (each page includes the same navigation and a development notice):

- [Architecture](docs/architecture.md)
- [API Reference](docs/api_reference.md)
- [Deployment Guide](docs/deployment_guide.md)
- [Testing Guide](docs/testing.md)

## Contributing

Contributions are welcome. See **[Contributing](CONTRIBUTING.md)**.
