# Imhotep Host

**Imhotep Host** is a FastAPI-based zero-downtime PaaS orchestrator that deploys Git-backed applications into isolated Docker networks, optionally provisions a PostgreSQL sidecar, and exposes apps through Cloudflare tunnels.

## What It Does

| Capability | Description |
| --- | --- |
| **Deploy from GitHub** | Clones a public repo, resolves Docker build context, and builds image tag `imhotep_app_{app_id}`. |
| **Template injection** | Injects framework templates (for example `django.Dockerfile`) when a native Dockerfile is missing or when forced. |
| **Per-app isolation** | Creates an isolated Docker bridge network `imhotep_net_{app_id}` for app and sidecars. |
| **Optional database sidecar** | Provisions `postgres:15-alpine` as `imhotep_db_{app_id}` and injects runtime DB environment variables. |
| **Public tunnel** | Starts `cloudflare/cloudflared` as `imhotep_tunnel_{app_id}` and extracts a live `trycloudflare.com` URL. |
| **Zero-downtime redeploy** | Starts candidate container, health-checks it, then swaps it into the primary container name. |

## Quick Start

### 1) Engine prerequisites

- **Python 3.10+**
- **Docker daemon running**

### 2) Install dependencies

```bash
cd engine
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install uvicorn
```

### 3) Run the API locally

```bash
cd engine
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4) Verify health

```bash
curl http://localhost:8000/
curl http://localhost:8000/api/system/health
```

## Documentation

Use this as the landing page for deeper docs:

- [Architecture](docs/architecture.md)
- [API Reference](docs/api_reference.md)
- [Deployment Guide](docs/deployment_guide.md)
- [Testing Guide](docs/testing.md)

## Contributing

Contributions are welcome. See the contributor guide:

- [Contributing Guide](CONTRIBUTING.md)