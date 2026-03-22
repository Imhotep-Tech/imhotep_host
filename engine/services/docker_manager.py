import docker

def get_docker_client():
    """
    Connects to the local Docker socket and returns a Docker client instance.
    """
    try:
        # This automatically uses the local Docker socket (/var/run/docker.sock by default on Linux)
        client = docker.from_env()
        
        # Test the connection to ensure it's successful
        client.ping()
        print("Successfully connected to the local Docker daemon.")
        return client
    except docker.errors.DockerException as e:
        print(f"Failed to connect to Docker: {e}")
        return None

def list_containers(client):
    """Lists all currently running containers."""
    containers = client.containers.list()
    print("Running containers:")
    if not containers:
        print("  No running containers.")
    for c in containers:
        print(f" - {c.name} ({c.id[:10]}): {c.status}")
    return containers

def start_nginx_container(client, name="test_nginx"):
    """Starts an nginx container in detached mode."""
    print(f"Starting nginx container named '{name}'...")
    try:
        container = client.containers.run(
            "nginx:latest",
            name=name,
            detach=True,
            ports={'80/tcp': 8080}
        )
        print(f"Started container {container.name} with ID {container.id[:10]}")
        return container
    except docker.errors.APIError as e:
        print(f"Failed to start container: {e}")
        return None

def stop_and_remove_container(client, name="test_nginx"):
    """Stops and removes the specified container programmatically."""
    print(f"Stopping and removing container '{name}'...")
    try:
        container = client.containers.get(name)
        container.stop()
        container.remove()
        print(f"Successfully stopped and removed '{name}'.")
    except docker.errors.NotFound:
        print(f"Container '{name}' not found.")
    except docker.errors.APIError as e:
        print(f"Failed to stop/remove container: {e}")

if __name__ == "__main__":
    # Simple test script when running this file directly
    client = get_docker_client()
    if client:
        print(f"Docker Engine Version: {client.version().get('Version')}\n")
        
        # 1. List running containers initially
        list_containers(client)
        print()
        
        # 2. Start an nginx container
        start_nginx_container(client)
        print()
        
        # 3. List running containers again to verify
        list_containers(client)
        print()
        
        # 4. Stop and remove the nginx container programmatically
        stop_and_remove_container(client)
        print()
        
        # 5. List running containers final check
        list_containers(client)
