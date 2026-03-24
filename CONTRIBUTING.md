# Contributing to Imhotep Host

First off, thank you for considering contributing to Imhotep Host. Contributions are welcome across the orchestration engine, API design, templates, tests, and docs.

## Project Areas

| Area | Typical contributions |
| --- | --- |
| **API (`engine/api`)** | Endpoint improvements, validation, status/guardrail handling, response consistency. |
| **Deployment pipeline (`engine/services/deployment.py`)** | Build/redeploy logic, rollback behavior, state transitions, reliability hardening. |
| **Docker manager (`engine/services/docker_manager.py`)** | Network/container lifecycle, tunnel handling, template injection behavior. |
| **Templates (`engine/templates`)** | New framework Dockerfile templates and utilities. |
| **Testing (`engine/tests`)** | Integration edge cases, regression tests, fixture quality, CI stability. |
| **Documentation (`docs/`)** | Architecture, API reference, deployment behavior, troubleshooting. |

## Local Development

### Prerequisites

- Python 3.10+
- Docker daemon running locally

### Setup

```bash
cd engine
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pytest uvicorn
```

### Run API

```bash
cd engine
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Run tests

```bash
cd engine
pytest -v tests
```

## Contribution Workflow

1. Fork the repository and create a focused branch.
2. Keep changes scoped (one feature/fix/doc concern per PR).
3. Add or update tests for behavior changes.
4. Update documentation if API/behavior changes.
5. Open a PR with:
   - context/problem statement
   - implementation summary
   - testing evidence (commands + results)
   - follow-up items, if any

## Testing Expectations

- Add integration coverage for lifecycle changes (`deploy`, `redeploy`, `stop`, `execute`, `delete`).
- Prefer deterministic tests:
  - use existing fixtures/mocks in `engine/tests/conftest.py`
  - avoid external dependencies in CI
- Preserve or improve coverage of:
  - zero-downtime swap correctness
  - database preservation during redeploy
  - failure-state guardrails

## Coding Guidelines

- Follow existing naming conventions for Docker resources (`imhotep_*`).
- Keep status transitions explicit and intentional (`Building`, `Running`, `Updating`, `Stopped`, `Failed`, `Update Failed`).
- Avoid breaking API contracts without documenting the change in `docs/api_reference.md`.
- Favor clear failure handling and cleanup paths in orchestrator code.

## Documentation Checklist for PRs

If your change affects behavior, update at least one of:

- `docs/architecture.md`
- `docs/api_reference.md`
- `docs/deployment_guide.md`
- `docs/testing.md`

## Good First Issues

If you want a fast on-ramp, these are concrete starter tasks focused on the template system:

| Area | Starter task | Suggested files |
| --- | --- | --- |
| **Template coverage** | Add a `flask.Dockerfile` community template and confirm `stack="flask"` builds via template injection. | `engine/templates/flask.Dockerfile` |
| **Template coverage** | Add a `.NET` template (`dotnet.Dockerfile`) and validate `force_template=true` replaces native Dockerfiles when requested. | `engine/templates/dotnet.Dockerfile` |
| **Node hardening** | Improve `node.Dockerfile` for production defaults (cache-friendly layers, non-root user, slim runtime stage). | `engine/templates/node.Dockerfile` |
| **Django utility quality** | Expand `Django.py` utility checks (for example clearer warnings around static/proxy settings). | `engine/templates_utils/Django.py` |
| **Template docs** | Add a short contributor reference describing expected template conventions and naming (`<framework>.Dockerfile`). | `docs/deployment_guide.md` |
| **Template tests** | Add integration tests that verify template injection when Dockerfile is missing and when `force_template=true`. | `engine/tests/test_deployment_lifecycle.py` |

When opening a PR for one of these, include:

- the framework/template rationale
- a sample `AppCreate` payload used for validation
- relevant test output (`pytest -v tests`)

## Reporting Bugs and Requesting Features

- Open an issue with:
  - reproduction steps
  - expected vs actual behavior
  - logs/errors
  - environment details (OS, Python, Docker)

Thanks again for helping improve Imhotep Host.