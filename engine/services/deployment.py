import uuid
from db.models import Application
from db.database import SessionLocal
from schemas.app_schema import AppCreate
from services.docker_manager import (
    create_app_network,
    deploy_app_container,
    deploy_cloudflare_tunnel, 
    deploy_local_postgres, 
    resolve_and_build
)
from services.git_manager import cleanup_build_dir, clone_public_repo
import docker

client = docker.from_env()

def run_deployment_pipeline(app_id: str, req: AppCreate):
    """This runs in the background."""
    db = SessionLocal()
    repo_dir = None
    try:
        #Clone & Build
        repo_dir = clone_public_repo(req.github_url, req.branch)
        resolve_and_build(repo_dir, app_id, req.root_directory, req.stack)
        
        #Network & DB
        network = create_app_network(app_id)
        if req.include_db:
            db_pass = str(uuid.uuid4())[:8]
            db_url = deploy_local_postgres(app_id, network.name, db_pass)
            req.env_vars["DATABASE_URL"] = db_url
        
        #App Container & port
        internal_port = 8000 if req.stack.lower() == "django" else 3000
        app_container_name = f"imhotep_run_{app_id}"

        #Start the Tunnel FIRST
        live_url = deploy_cloudflare_tunnel(
            app_id=app_id, network_name=network.name, 
            app_container_name=app_container_name,
            internal_port=internal_port
        )

        #Dynamically inject the new URL into the environment variables!
        req.env_vars["SITE_DOMAIN"] = live_url
        req.env_vars["CSRF_TRUSTED_ORIGINS"] = live_url

        #Django's ALLOWED_HOSTS doesn't want the 'https://' part, so we strip it out
        clean_host = live_url.replace("https://", "")
        req.env_vars["ALLOWED_HOSTS"] = clean_host

        #deploy the app container with the final environment variables
        app_container = deploy_app_container(
            app_id=app_id, image_tag=f"imhotep_app_{app_id}", 
            network_name=network.name, env_vars=req.env_vars
        )
        
        #Success! Update the database record
        app_record = db.query(Application).filter(Application.id == app_id).first()
        if app_record:
            app_record.cloudflare_url = live_url
            app_record.status = "Running"
            db.commit()

    except Exception as e:
        print(f"Deployment Failed for {app_id}: {e}")
        # Mark as failed in the database
        app_record = db.query(Application).filter(Application.id == app_id).first()
        if app_record:
            app_record.status = "Failed"
            db.commit()
            
    finally:
        if repo_dir:
            cleanup_build_dir(repo_dir)
        db.close()

def run_redeploy_pipeline(app_id: str, root_directory: str = "/"):
    """Builds the new image, and ONLY swaps it if the build succeeds."""
    db = SessionLocal()
    app_record = db.query(Application).filter(Application.id == app_id).first()
    
    if not app_record:
        db.close()
        return

    repo_dir = None
    try:
        #Clone & Build (The old app is still live and running during this!)
        repo_dir = clone_public_repo(app_record.github_url, app_record.branch)
        resolve_and_build(repo_dir, app_id, root_directory, app_record.stack)
        
        #The Swap (Build succeeded, now we swap them!)
        print(f"Build successful. Swapping containers for {app_id}...")
        container_name = f"imhotep_run_{app_id}"
        
        #Safely stop and remove the old container
        try:
            old_container = client.containers.get(container_name)
            old_container.stop()
            old_container.remove()
        except docker.errors.NotFound:
            pass #It was already stopped or deleted
            
        #start the new container with the LATEST env vars from the database
        deploy_app_container(
            app_id=app_id, 
            image_tag=f"imhotep_app_{app_id}", 
            network_name=app_record.network_name, 
            env_vars=app_record.env_vars
        )
        
        #Success!
        app_record.status = "Running"
        db.commit()

    except Exception as e:
        print(f"Redeploy Failed for {app_id}: {e}")
        # If it fails, the old container is still running safely!
        app_record.status = "Update Failed" 
        db.commit()
        
    finally:
        if repo_dir:
            cleanup_build_dir(repo_dir)
        db.close()