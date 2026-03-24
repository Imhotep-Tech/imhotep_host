import uuid
import docker
import time
from urllib.parse import urlparse
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
from sqlalchemy.orm.attributes import flag_modified

client = docker.from_env()

def _to_bool(value):
    '''Converts various truthy string representations to a boolean True, else False.'''
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def run_deployment_pipeline(app_id: str, req: AppCreate):
    """This runs in the background to handle the heavy lifting."""
    db = SessionLocal()
    repo_dir = None
    try:
        req.env_vars = req.env_vars or {}
        req.env_vars["FORCE_TEMPLATE"] = "true" if req.force_template else "false"
        req.env_vars["RELATIVE_ROOT"] = req.root_directory

        #Clone & Build
        repo_dir = clone_public_repo(req.github_url, req.branch)
        force_template = _to_bool(req.env_vars.get("FORCE_TEMPLATE", "false"))
        resolve_and_build(repo_dir, app_id, req.root_directory, req.stack, force_template)
        
        #Network & DB Setup
        network = create_app_network(app_id)
        if req.include_db:
            # We combine the logic into one block to avoid redundant container deployments
            db_user = "imhotep_user"
            db_name = f"db_{app_id}"
            db_pass = str(uuid.uuid4())[:12]
            db_host = f"imhotep_db_{app_id}"
            db_port = "5432"
            
            # Deploy Postgres
            db_url = deploy_local_postgres(app_id, network.name, db_pass)
            
            # Shotgun Inject Database Env Vars
            req.env_vars["DATABASE_URL"] = db_url
            req.env_vars["DATABASE_NAME"] = db_name
            req.env_vars["DATABASE_USER"] = db_user
            req.env_vars["DATABASE_PASSWORD"] = db_pass
            req.env_vars["DATABASE_HOST"] = db_host
            req.env_vars["DATABASE_PORT"] = db_port
            
            # Framework-specific keys
            req.env_vars["POSTGRES_DB"] = db_name
            req.env_vars["POSTGRES_USER"] = db_user
            req.env_vars["POSTGRES_PASSWORD"] = db_pass
            req.env_vars["POSTGRES_HOST"] = db_host
            req.env_vars["POSTGRES_PORT"] = db_port
            
            print(f"[{app_id}] Postgres deployed. Waiting 10s for initialization...")
            time.sleep(10) # Give Postgres time to start before Django tries to migrate
        
        #Setup Networking names
        internal_port = 8000 if req.stack.lower() == "django" else 3000
        app_container_name = f"imhotep_run_{app_id}"

        #Start Tunnel (to get the URL first)
        live_url = deploy_cloudflare_tunnel(
            app_id=app_id, 
            network_name=network.name, 
            app_container_name=app_container_name,
            internal_port=internal_port
        )

        clean_host = live_url.replace("https://", "").replace("http://", "").strip("/")
        existing_hosts = req.env_vars.get("ALLOWED_HOSTS", "")
        
        if existing_hosts:
            req.env_vars["ALLOWED_HOSTS"] = f"{existing_hosts},{clean_host}"
        else:
            req.env_vars["ALLOWED_HOSTS"] = clean_host

        req.env_vars["SITE_DOMAIN"] = live_url
        req.env_vars["CSRF_TRUSTED_ORIGINS"] = live_url

        #Deploy App Container
        deploy_app_container(
            app_id=app_id, 
            image_tag=f"imhotep_app_{app_id}", 
            network_name=network.name, 
            env_vars=req.env_vars
        )
        
        #Success! Update DB
        app_record = db.query(Application).filter(Application.id == app_id).first()
        if app_record:
            app_record.cloudflare_url = live_url
            app_record.env_vars = req.env_vars
            flag_modified(app_record, "env_vars")
            app_record.status = "Running"
            db.commit()

    except Exception as e:
        print(f"Deployment Failed for {app_id}: {e}")
        app_record = db.query(Application).filter(Application.id == app_id).first()
        if app_record:
            app_record.status = "Failed"
            db.commit()
            
    finally:
        if repo_dir:
            cleanup_build_dir(repo_dir)
        db.close()

def run_redeploy_pipeline(app_id: str, root_directory: str = "/"):
    """Zero-downtime swap: Builds new image, then replaces container using the exact saved env_vars."""
    db = SessionLocal()
    app_record = db.query(Application).filter(Application.id == app_id).first()
    
    if not app_record:
        db.close()
        return

    repo_dir = None
    candidate_container = None
    try:
        #Clone & Build (App stays live during this)
        repo_dir = clone_public_repo(app_record.github_url, app_record.branch)
        
        # Just grab the exact dictionary from the database
        exact_env_vars = app_record.env_vars or {}
        
        runtime_root = exact_env_vars.get("RELATIVE_ROOT", root_directory)
        force_template = str(exact_env_vars.get("FORCE_TEMPLATE", "")).strip().lower() in {"1", "true", "yes", "on"}
        
        resolve_and_build(repo_dir, app_id, runtime_root, app_record.stack, force_template)
        
        #Start candidate container
        print(f"Build successful. Starting candidate container for {app_id}...")
        container_name = f"imhotep_run_{app_id}"
        candidate_name = f"{container_name}_candidate"
        
        #Clean up any old failed candidates just in case
        try:
            stale_candidate = client.containers.get(candidate_name)
            stale_candidate.remove(force=True)
        except docker.errors.NotFound:
            pass

        #Boot the new container with the exact same variables
        candidate_container = deploy_app_container(
            app_id=app_id, 
            image_tag=f"imhotep_app_{app_id}", 
            network_name=app_record.network_name, 
            env_vars=exact_env_vars,
            container_name=candidate_name
        )

        #Health check (Wait 6 seconds, see if it crashed)
        time.sleep(6)
        candidate_container.reload()
        if candidate_container.status != "running":
            logs = candidate_container.logs(tail=120).decode("utf-8", errors="ignore")
            raise RuntimeError(f"Candidate container failed to stay running.\n{logs}")

        #The Swap
        print(f"Candidate healthy. Swapping containers for {app_id}...")
        try:
            old_container = client.containers.get(container_name)
            old_container.stop()
            old_container.remove()
        except docker.errors.NotFound:
            pass

        # Rename candidate so the Cloudflare tunnel seamlessly connects to it
        candidate_container.rename(container_name)
        
        app_record.status = "Running"
        db.commit()

    except Exception as e:
        print(f"Redeploy Failed for {app_id}: {e}")
        if candidate_container:
            try:
                candidate_container.remove(force=True)
            except Exception:
                pass
        app_record.status = "Update Failed" 
        db.commit()
        
    finally:
        if repo_dir:
            cleanup_build_dir(repo_dir)
        db.close()