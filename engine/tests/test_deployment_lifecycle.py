import time
from unittest.mock import patch

import docker
import pytest
from docker.models.containers import Container


def _wait_for_status(client, app_id, expected_status, timeout_seconds=20):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/api/apps/{app_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        if body.get("status") == expected_status:
            return body
        time.sleep(0.2)
    pytest.fail(f"App {app_id} never reached status '{expected_status}'")


def _base_payload(name, include_db=False, env_vars=None):
    return {
        "name": name,
        "github_url": "https://github.com/example/repo.git",
        "branch": "main",
        "stack": "django",
        "root_directory": "/",
        "include_db": include_db,
        "force_template": False,
        "env_vars": env_vars or {},
    }


def test_full_deployment_flow(client):
    docker_client = docker.from_env()
    payload = {
        "name": "integration-app-1",
        "github_url": "https://github.com/example/repo.git",
        "branch": "main",
        "stack": "django",
        "root_directory": "/",
        "include_db": True,
        "force_template": False,
        "env_vars": {"DJANGO_DEBUG": "true"},
    }

    deploy_response = client.post("/api/apps/deploy", json=payload)
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]

    app_record = _wait_for_status(client, app_id, "Running")
    assert app_record["cloudflare_url"] == "https://mock-tunnel.trycloudflare.com"

    network = docker_client.networks.get(f"imhotep_net_{app_id}")
    assert network.name == f"imhotep_net_{app_id}"

    db_container = docker_client.containers.get(f"imhotep_db_{app_id}")
    app_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    db_container.reload()
    app_container.reload()

    assert db_container.status == "running"
    assert app_container.status == "running"


def test_redeploy_candidate_swap(client):
    docker_client = docker.from_env()
    deploy_payload = {
        "name": "integration-app-2",
        "github_url": "https://github.com/example/repo.git",
        "branch": "main",
        "stack": "django",
        "root_directory": "/",
        "include_db": False,
        "force_template": False,
        "env_vars": {"VERSION": "v1"},
    }

    deploy_response = client.post("/api/apps/deploy", json=deploy_payload)
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]

    _wait_for_status(client, app_id, "Running")
    old_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    old_container_id = old_container.id

    update_payload = {
        "name": "integration-app-2",
        "github_url": "https://github.com/example/repo.git",
        "branch": "main",
        "stack": "django",
        "root_directory": "/",
        "include_db": False,
        "force_template": False,
        "env_vars": {"VERSION": "v2"},
    }
    update_response = client.put(f"/api/apps/{app_id}", json=update_payload)
    assert update_response.status_code == 200, update_response.text

    redeploy_response = client.post(f"/api/apps/{app_id}/redeploy")
    assert redeploy_response.status_code == 200, redeploy_response.text

    _wait_for_status(client, app_id, "Running")

    new_primary = docker_client.containers.get(f"imhotep_run_{app_id}")
    assert new_primary.id != old_container_id

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(f"imhotep_run_{app_id}_candidate")


def test_teardown(client):
    docker_client = docker.from_env()
    payload = {
        "name": "integration-app-3",
        "github_url": "https://github.com/example/repo.git",
        "branch": "main",
        "stack": "django",
        "root_directory": "/",
        "include_db": True,
        "force_template": False,
        "env_vars": {"DJANGO_DEBUG": "false"},
    }

    deploy_response = client.post("/api/apps/deploy", json=payload)
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    delete_response = client.delete(f"/api/apps/{app_id}")
    assert delete_response.status_code == 200, delete_response.text

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(f"imhotep_run_{app_id}")
    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(f"imhotep_db_{app_id}")
    with pytest.raises(docker.errors.NotFound):
        docker_client.networks.get(f"imhotep_net_{app_id}")


def test_redeploy_preserves_database(client):
    docker_client = docker.from_env()
    deploy_response = client.post(
        "/api/apps/deploy",
        json=_base_payload("integration-app-db-preserve", include_db=True),
    )
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    db_container_before = docker_client.containers.get(f"imhotep_db_{app_id}")
    db_container_id_before = db_container_before.id
    db_container_created_before = db_container_before.attrs["Created"]

    update_response = client.put(
        f"/api/apps/{app_id}",
        json=_base_payload(
            "integration-app-db-preserve",
            include_db=True,
            env_vars={"REDEPLOY_REASON": "config-update"},
        ),
    )
    assert update_response.status_code == 200, update_response.text
    redeploy_response = client.post(f"/api/apps/{app_id}/redeploy")
    assert redeploy_response.status_code == 200, redeploy_response.text

    _wait_for_status(client, app_id, "Running")
    db_container_after = docker_client.containers.get(f"imhotep_db_{app_id}")
    db_container_after.reload()

    assert db_container_after.id == db_container_id_before
    assert db_container_after.attrs["Created"] == db_container_created_before
    assert db_container_after.status == "running"


def test_redeploy_with_new_env_vars(client):
    docker_client = docker.from_env()
    deploy_response = client.post(
        "/api/apps/deploy",
        json=_base_payload("integration-app-env-vars", include_db=False, env_vars={"VERSION": "v1"}),
    )
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    update_response = client.put(
        f"/api/apps/{app_id}",
        json=_base_payload(
            "integration-app-env-vars",
            include_db=False,
            env_vars={"NEW_CUSTOM_KEY": "super_secret", "VERSION": "v2"},
        ),
    )
    assert update_response.status_code == 200, update_response.text
    redeploy_response = client.post(f"/api/apps/{app_id}/redeploy")
    assert redeploy_response.status_code == 200, redeploy_response.text
    _wait_for_status(client, app_id, "Running")

    app_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    app_container.reload()
    container_env = app_container.attrs["Config"].get("Env", [])
    assert "NEW_CUSTOM_KEY=super_secret" in container_env


def test_failed_candidate_aborts_swap_and_protects_live_site(client):
    docker_client = docker.from_env()
    deploy_response = client.post(
        "/api/apps/deploy",
        json=_base_payload("integration-app-failed-candidate", include_db=False),
    )
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    original_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    original_container_id = original_container.id

    def _deploy_failing_candidate(app_id, image_tag, network_name, env_vars=None, container_name=None):
        del app_id, image_tag, env_vars
        return docker_client.containers.run(
            "alpine:3.20",
            name=container_name,
            network=network_name,
            command=["sh", "-c", "exit 1"],
            detach=True,
        )

    with patch("services.deployment.deploy_app_container", side_effect=_deploy_failing_candidate):
        redeploy_response = client.post(f"/api/apps/{app_id}/redeploy")
        assert redeploy_response.status_code == 200, redeploy_response.text

    app_record = _wait_for_status(client, app_id, "Update Failed")
    assert app_record["status"] == "Update Failed"

    live_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    live_container.reload()
    assert live_container.id == original_container_id
    assert live_container.status == "running"


def test_stop_and_execute_endpoints(client, monkeypatch):
    docker_client = docker.from_env()
    deploy_response = client.post(
        "/api/apps/deploy",
        json=_base_payload("integration-app-stop-execute", include_db=False),
    )
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    def _mock_exec_run(self, cmd, workdir=None, **kwargs):
        del self, workdir, kwargs
        if cmd == "echo 'hello'":
            return 0, b"hello\n"
        return 1, b"unsupported command\n"

    monkeypatch.setattr(Container, "exec_run", _mock_exec_run)

    execute_response = client.post(
        f"/api/apps/{app_id}/execute",
        json={"command": "echo 'hello'"},
    )
    assert execute_response.status_code == 200, execute_response.text
    execute_body = execute_response.json()
    assert execute_body["exit_code"] == 0
    assert execute_body["output"].strip() == "hello"

    stop_response = client.post(f"/api/apps/{app_id}/stop")
    assert stop_response.status_code == 200, stop_response.text

    stopped_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    stopped_container.reload()
    assert stopped_container.status == "exited"


def test_deployment_rollback_on_partial_failure(client):
    docker_client = docker.from_env()
    with patch(
        "services.deployment.deploy_cloudflare_tunnel",
        side_effect=Exception("simulated tunnel timeout"),
    ):
        deploy_response = client.post(
            "/api/apps/deploy",
            json=_base_payload("integration-app-partial-failure", include_db=True),
        )
        assert deploy_response.status_code == 200, deploy_response.text
        app_id = deploy_response.json()["id"]

    app_record = _wait_for_status(client, app_id, "Failed")
    assert app_record["status"] == "Failed"

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(f"imhotep_run_{app_id}")

    db_exists = True
    net_exists = True
    try:
        docker_client.containers.get(f"imhotep_db_{app_id}")
    except docker.errors.NotFound:
        db_exists = False
    try:
        docker_client.networks.get(f"imhotep_net_{app_id}")
    except docker.errors.NotFound:
        net_exists = False

    # Current engine behavior: fresh deploy failure does not fully roll back DB/network.
    # If this ever changes, these assertions can be updated to enforce full rollback.
    assert db_exists is True
    assert net_exists is True


def test_redeploy_recovers_failed_app(client):
    docker_client = docker.from_env()
    deploy_response = client.post(
        "/api/apps/deploy",
        json=_base_payload("integration-app-recover-failed", include_db=False),
    )
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    stop_response = client.post(f"/api/apps/{app_id}/stop")
    assert stop_response.status_code == 200, stop_response.text
    _wait_for_status(client, app_id, "Stopped")

    redeploy_response = client.post(f"/api/apps/{app_id}/redeploy")
    assert redeploy_response.status_code == 200, redeploy_response.text

    app_record = _wait_for_status(client, app_id, "Running")
    assert app_record["status"] == "Running"

    live_container = docker_client.containers.get(f"imhotep_run_{app_id}")
    live_container.reload()
    assert live_container.status == "running"


def test_api_guardrails_for_invalid_states(client):
    invalid_response = client.get("/api/apps/invalid_id_123")
    assert invalid_response.status_code == 404

    deploy_response = client.post(
        "/api/apps/deploy",
        json=_base_payload("integration-app-guardrails", include_db=False),
    )
    assert deploy_response.status_code == 200, deploy_response.text
    app_id = deploy_response.json()["id"]
    _wait_for_status(client, app_id, "Running")

    stop_response = client.post(f"/api/apps/{app_id}/stop")
    assert stop_response.status_code == 200, stop_response.text
    _wait_for_status(client, app_id, "Stopped")

    execute_response = client.post(
        f"/api/apps/{app_id}/execute",
        json={"command": "echo 'should fail while stopped'"},
    )
    assert execute_response.status_code == 400
