import os
import shutil
import docker
import re
import time

# Initialize your docker client
client = docker.from_env()

# Define the absolute path to the templates directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

def inject_dockerfile(build_path: str, framework: str):
    """
    Dynamically finds a community template file and copies it to the target directory.
    """
    framework_key = framework.lower()
    
    #look for the exact file
    source_template_path = os.path.join(TEMPLATES_DIR, f"{framework_key}.Dockerfile")
    
    #validate if the community has built this template yet
    if not os.path.exists(source_template_path):
        raise ValueError(f"Error: No community template found for '{framework}'. "
                         f"Please ensure {framework_key}.Dockerfile exists in the templates folder.")
    
    #define the destination
    dockerfile_destination = os.path.join(build_path, "Dockerfile")
    
    #copy the file directly
    shutil.copyfile(source_template_path, dockerfile_destination)
    print(f"Successfully injected {framework_key}.Dockerfile into {build_path}")
    
    return dockerfile_destination


def resolve_and_build(cloned_repo_path: str, app_id: str, root_directory: str = "/", framework: str = "django"):
    """
    Resolves the build path, checks for a Dockerfile, injects a template if missing,
    and builds the Docker image.
    """
    #path resolution
    clean_sub_dir = root_directory.strip("/")
    build_path = os.path.join(cloned_repo_path, clean_sub_dir)
    
    #ensure the directory the user requested actually exists
    if not os.path.isdir(build_path):
        raise ValueError(f"Directory not found: {build_path}")

    print(f"Build path resolved to: {build_path}")

    #the "Native Dockerfile" Check
    dockerfile_path = os.path.join(build_path, "Dockerfile")
    
    if os.path.exists(dockerfile_path):
        print("Native Dockerfile found. Skipping template injection.")
    else:
        #template injection
        print(f"No Dockerfile found. Injecting {framework} template...")
        inject_dockerfile(build_path, framework)
            
    #Image Compilation
    image_tag = f"imhotep_app_{app_id}"
    print(f"Starting Docker build for {image_tag}...")
    
    try:
        image, build_logs = client.images.build(
            path=build_path,
            tag=image_tag,
            rm=True
        )
        print(f"Successfully built image: {image_tag}")
        return image
        
    except docker.errors.BuildError as e:
        print(f"Docker Build Failed!")
        for log_line in e.build_log:
            if 'stream' in log_line:
                print(log_line['stream'].strip())
        raise e


def create_app_network(app_id: str):
    """
    Creates an isolated Docker bridge network for a specific app and its database.
    """
    network_name = f"imhotep_net_{app_id}"
    
    existing_networks = client.networks.list(names=[network_name])
    if existing_networks:
        print(f"Network {network_name} already exists.")
        return existing_networks
        
    print(f"Creating isolated network: {network_name}")
    return client.networks.create(network_name, driver="bridge")


def deploy_local_postgres(app_id: str, network_name: str, db_password: str):
    """
    Spins up a Postgres container and attaches it to the app's isolated network.
    """
    container_name = f"imhotep_db_{app_id}"
    
    env_vars = {
        "POSTGRES_USER": "imhotep_user",
        "POSTGRES_PASSWORD": db_password,
        "POSTGRES_DB": f"db_{app_id}"
    }

    print(f"Deploying local database: {container_name}...")
    
    try:
        db_container = client.containers.run(
            "postgres:15-alpine",
            name=container_name,
            network=network_name,
            environment=env_vars,
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        print(f"Database {container_name} is running.")
        
        internal_db_url = f"postgres://imhotep_user:{db_password}@{container_name}:5432/db_{app_id}"
        return internal_db_url
        
    except docker.errors.APIError as e:
        print(f"Failed to start database container: {e}")
        raise e
    

def deploy_app_container(app_id: str, image_tag: str, network_name: str, env_vars: dict = None):
    """
    Runs the compiled app image on the isolated network, injecting the environment variables.
    """
    if env_vars is None:
        env_vars = {}
        
    container_name = f"imhotep_run_{app_id}"
    
    print(f"Deploying app container: {container_name}...")
    
    try:
        app_container = client.containers.run(
            image=image_tag,
            name=container_name,
            network=network_name,
            environment=env_vars,
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        print(f"App {container_name} is running successfully on {network_name}.")
        return app_container
        
    except docker.errors.APIError as e:
        print(f"Failed to start app container: {e}")
        raise e

def deploy_cloudflare_tunnel(app_id: str, network_name: str, app_container_name: str, internal_port: int = 8000):
    """
    Deploys a Cloudflare sidecar, routes it to the app, and extracts the live URL.
    """
    tunnel_container_name = f"imhotep_tunnel_{app_id}"
    
    #routing & tunnel deployment
    #the command tells Cloudflare exactly which container and port to route traffic to
    routing_command = f"tunnel --url http://{app_container_name}:{internal_port}"
    
    print(f"Deploying Cloudflare sidecar for {app_container_name} on port {internal_port}...")
    
    try:
        tunnel_container = client.containers.run(
            image="cloudflare/cloudflared:latest",
            name=tunnel_container_name,
            network=network_name,
            command=routing_command,
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
    except docker.errors.APIError as e:
        print(f"Failed to start Cloudflare tunnel: {e}")
        raise e

    #Log Extraction (The Regex Hunt)
    print("Waiting for Cloudflare to generate URL...")
    
    # Regex pattern to find the free trycloudflare link
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    
    start_time = time.time()
    timeout = 15  # Give Cloudflare 15 seconds to negotiate the connection

    # Poll the logs every 1 second
    while time.time() - start_time < timeout:
        # Fetch the last 50 lines of logs
        logs = tunnel_container.logs(tail=50).decode("utf-8")
        
        # Search the logs for our Regex pattern
        match = url_pattern.search(logs)
        if match:
            live_url = match.group(0)
            print(f"Success! App is live at: {live_url}")
            return live_url
            
        time.sleep(1)

    #Timeout Fallback
    #If the loop finishes and we didn't return a URL, something went wrong
    print("Error: Cloudflare tunnel timed out.")
    raise TimeoutError("Failed to extract Cloudflare URL within 15 seconds. Check network connection.")

