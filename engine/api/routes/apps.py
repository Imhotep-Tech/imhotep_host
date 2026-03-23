from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Application
from schemas.app_schema import AppCreate, AppResponse
from services.git_manager import clone_public_repo, cleanup_build_dir
from services.docker_manager import (
    resolve_and_build, create_app_network, 
    deploy_local_postgres, deploy_app_container,
    deploy_cloudflare_tunnel, teardown_deployment
)
import uuid

router = APIRouter()

# Dependency to get the DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/deploy", response_model=AppResponse)
def deploy_application(req: AppCreate, db: Session = Depends(get_db)):
    # Generate a unique, short ID for this deployment (e.g., "a8f3b2")
    app_id = str(uuid.uuid4())[:6]
    
    repo_dir = None
    try:
    
        # Clone Code
        repo_dir = clone_public_repo(req.github_url, req.branch)
        
        # Build Image
        resolve_and_build(repo_dir, app_id, req.root_directory, req.stack)
        
        # Networking for teh connection between app and DB (if needed)
        network = create_app_network(app_id)
        
        # Database (Optional based on user input)
        db_url = None
        if req.include_db:
            # Generate a random password for the DB
            db_pass = str(uuid.uuid4())[:8]
            db_url = deploy_local_postgres(app_id, network.name, db_pass)
            req.env_vars["DATABASE_URL"] = db_url
            
        # Application Deployment
        app_container = deploy_app_container(
            app_id=app_id, 
            image_tag=f"imhotep_app_{app_id}", 
            network_name=network.name, 
            env_vars=req.env_vars
        )
        
        # Expose to Internet
        live_url = deploy_cloudflare_tunnel(
            app_id=app_id, 
            network_name=network.name, 
            app_container_name=app_container.name,
            # Assuming port 8000 for Django, 3000 for Node
            internal_port=8000 if req.stack.lower() == "django" else 3000 
        )
        
        # Database record creation
        new_app = Application(
            id=app_id,
            name=req.name,
            github_url=req.github_url,
            branch=req.branch,
            stack=req.stack,
            network_name=network.name,
            cloudflare_url=live_url,
            env_vars=req.env_vars
        )
        
        db.add(new_app)
        db.commit()
        db.refresh(new_app)
        
        return {
            "id": new_app.id,
            "name": new_app.name,
            "cloudflare_url": live_url,
            "status": "Running"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
        
    finally: #delete the cloned repo to save space
        if repo_dir:
            cleanup_build_dir(repo_dir)

# engine/api/routes/apps.py

@router.get("/apps", response_model=list[AppResponse]) # Notice 'list[]' here
def get_apps(db: Session = Depends(get_db)):           # Notice '= Depends(get_db)' here
    apps = db.query(Application).all()
    return apps

@router.get("/apps/{app_id}", response_model=AppResponse)
def get_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app

@router.put("/apps/{app_id}", response_model=AppResponse)
def update_app(app_id: int, req: AppCreate, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Update fields
    app.name = req.name
    app.github_url = req.github_url
    app.branch = req.branch
    app.stack = req.stack
    app.env_vars = req.env_vars
    
    db.commit()
    db.refresh(app)
    
    return app

@router.post("/apps/{app_id}/stop", response_model=AppResponse)
def stop_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Here you would add logic to stop the running Docker container associated with this app.
    
    return app

@router.post("/apps/{app_id}/redeploy", response_model=AppResponse)
def redeploy_app(app_id: int, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Here you would add logic to stop/remove existing Docker containers, networks, and tunnels associated with this app.
    # Then you would re-run the deployment logic similar to the /deploy endpoint using the existing app details.
    
    return app

@router.delete("/apps/{app_id}")
def delete_app(app_id: str, db: Session = Depends(get_db)): # Note the 'str'
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    #Nuke the Docker containers and network
    teardown_deployment(app_id)
    
    #Delete the record from the SQLite database
    db.delete(app)
    db.commit()
    
    return {"detail": f"Application {app.name} deleted completely."}