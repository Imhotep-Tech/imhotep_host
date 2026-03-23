
import uuid
from db.models import Application
from db.database import SessionLocal
from schemas.app_schema import AppCreate
from services.docker_manager import create_app_network, deploy_app_container, deploy_cloudflare_tunnel, deploy_local_postgres, resolve_and_build
from services.git_manager import cleanup_build_dir, clone_public_repo

def run_deployment_pipeline(app_id: str, req: AppCreate):
    """This runs in the background. It needs its own DB session so it doesn't timeout."""
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
        
        #Start the Tunnel FIRST
        live_url = deploy_cloudflare_tunnel(
            app_id=app_id, network_name=network.name, 
            app_container_name=app_container.name,
            internal_port=8000 if req.stack.lower() == "django" else 3000
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
