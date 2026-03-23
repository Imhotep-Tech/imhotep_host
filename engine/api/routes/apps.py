from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Application
from schemas.app_schema import AppCreate, AppResponse
from services.git_manager import clone_public_repo, cleanup_build_dir
from services.docker_manager import (
    resolve_and_build, create_app_network, 
    deploy_local_postgres, deploy_app_container, deploy_cloudflare_tunnel, teardown_deployment
)
from services.deployment import run_deployment_pipeline
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
def deploy_application(
    req: AppCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    app_id = str(uuid.uuid4())[:6]
    
    #Save the initial "Building" state to the database instantly
    new_app = Application(
        id=app_id,
        name=req.name,
        github_url=req.github_url,
        branch=req.branch,
        stack=req.stack,
        network_name=f"imhotep_net_{app_id}",
        status="Building",
        env_vars=req.env_vars
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    
    #Hand the heavy lifting off to the background thread
    background_tasks.add_task(run_deployment_pipeline, app_id, req)
    
    # 3. Return a success message to the browser in milliseconds!
    return {
        "id": new_app.id,
        "name": new_app.name,
        "cloudflare_url": None,
        "status": "Building"
    }

@router.get("/apps", response_model=list[AppResponse])
def get_apps(db: Session = Depends(get_db)):
    apps = db.query(Application).all()
    return apps

@router.get("/apps/{app_id}", response_model=AppResponse)
def get_app(app_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app

@router.put("/apps/{app_id}", response_model=AppResponse)
def update_app(app_id: str, req: AppCreate, db: Session = Depends(get_db)):
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
def stop_app(app_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Here you would add logic to stop the running Docker container associated with this app.
    
    return app

@router.post("/apps/{app_id}/redeploy", response_model=AppResponse)
def redeploy_app(app_id: str, db: Session = Depends(get_db)):
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