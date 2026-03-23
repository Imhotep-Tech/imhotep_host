from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Application
from schemas.app_schema import AppCreate, AppResponse
from services.docker_manager import teardown_deployment
from services.deployment import run_deployment_pipeline, run_redeploy_pipeline
import uuid
import docker

client = docker.from_env()

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

@router.get("/", response_model=list[AppResponse])
def get_apps(db: Session = Depends(get_db)):
    apps = db.query(Application).all()
    return apps

@router.get("/{app_id}", response_model=AppResponse)
def get_app(app_id: str, db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app

@router.put("/{app_id}", response_model=AppResponse)
def update_app_and_redeploy(
    app_id: str, 
    req: AppCreate, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Updates configuration (like Env Vars) and triggers a zero-downtime redeploy."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    #Update the database
    app.name = req.name
    app.github_url = req.github_url
    app.branch = req.branch
    app.stack = req.stack
    app.env_vars = req.env_vars
    app.status = "Updating"
    
    db.commit()
    db.refresh(app)

    #redeploy in the background with the new configuration (like env vars)
    background_tasks.add_task(run_redeploy_pipeline, app_id, req.root_directory)
    
    return app

@router.post("/{app_id}/stop", response_model=AppResponse)
def stop_app(app_id: str, db: Session = Depends(get_db)):
    """Instantly kills the running application container."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    try:
        container = client.containers.get(f"imhotep_run_{app_id}")
        container.stop()
    except docker.errors.NotFound:
        pass # Already stopped
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    app.status = "Stopped"
    db.commit()
    db.refresh(app)
    return app

@router.post("/{app_id}/redeploy", response_model=AppResponse)
def redeploy_app(
    app_id: str, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    root_directory: str = "/"
):
    """Triggers a zero-downtime build-then-swap pipeline to pull fresh code."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    app.status = "Updating"
    db.commit()
    db.refresh(app)
    
    # Fire off the background swap!
    background_tasks.add_task(run_redeploy_pipeline, app_id, root_directory)
    
    return app

@router.delete("/{app_id}")
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