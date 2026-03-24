import tempfile
from pathlib import Path
from unittest.mock import patch

import docker
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db.database as db_database
from db.models import Base


@pytest.fixture(scope="session")
def docker_client():
    return docker.from_env()


@pytest.fixture(autouse=True)
def cleanup_imhotep_docker_resources(docker_client):
    yield

    for container in docker_client.containers.list(all=True):
        if container.name.startswith("imhotep_"):
            try:
                container.remove(force=True)
            except Exception:
                pass

    for network in docker_client.networks.list():
        if network.name.startswith("imhotep_"):
            try:
                network.remove()
            except Exception:
                pass


@pytest.fixture(scope="session")
def test_db_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir) / "test_imhotep.db"


@pytest.fixture(scope="session")
def session_local_for_tests(test_db_path):
    test_engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)
    yield testing_session_local
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(autouse=True)
def override_database_session(monkeypatch, session_local_for_tests):
    import api.routes.apps as apps_routes
    import services.deployment as deployment_service

    monkeypatch.setattr(db_database, "SessionLocal", session_local_for_tests)
    monkeypatch.setattr(apps_routes, "SessionLocal", session_local_for_tests)
    monkeypatch.setattr(deployment_service, "SessionLocal", session_local_for_tests)


@pytest.fixture(autouse=True)
def run_background_tasks_inline(monkeypatch):
    def _run_inline(self, func, *args, **kwargs):
        func(*args, **kwargs)

    monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", _run_inline)


@pytest.fixture(autouse=True)
def mock_repo_build_and_tunnel():
    with tempfile.TemporaryDirectory() as temp_repo_dir:
        client = docker.from_env()

        def _mock_clone_public_repo(_github_url, _branch):
            return temp_repo_dir

        def _mock_resolve_and_build(
            _cloned_repo_path,
            app_id,
            root_directory="/",
            framework="django",
            force_template=False,
        ):
            del root_directory, framework, force_template
            base_image = "traefik/whoami:latest"
            client.images.pull(base_image)
            image = client.images.get(base_image)
            image.tag(repository=f"imhotep_app_{app_id}", tag="latest")
            return image

        with (
            patch("services.deployment.clone_public_repo", side_effect=_mock_clone_public_repo),
            patch("services.deployment.resolve_and_build", side_effect=_mock_resolve_and_build),
            patch(
                "services.deployment.deploy_cloudflare_tunnel",
                return_value="https://mock-tunnel.trycloudflare.com",
            ),
            patch("services.deployment.time.sleep", return_value=None),
        ):
            yield


@pytest.fixture
def client():
    from main import app

    return TestClient(app)
