from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Application
from schemas.app_schema import AppCreate, AppResponse, CommandRequest
from services.docker_manager import teardown_deployment
from services.deployment import run_deployment_pipeline, run_redeploy_pipeline
import uuid
import docker
from sqlalchemy.orm.attributes import flag_modified

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
    req.env_vars = req.env_vars or {}
    req.env_vars["FORCE_TEMPLATE"] = "true" if req.force_template else "false"
    
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
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    #Capture the existing "Enriched" variables
    infra_keys = [
        "DATABASE_URL", "DATABASE_NAME", "DATABASE_USER", 
        "DATABASE_PASSWORD", "DATABASE_HOST", "DATABASE_PORT",
        "ALLOWED_HOSTS", "SITE_DOMAIN", "CSRF_TRUSTED_ORIGINS",
        "RELATIVE_ROOT", "FORCE_TEMPLATE"
    ]
    
    enriched_vars = {k: v for k, v in app.env_vars.items() if k in infra_keys}
    
    #Update with the new user variables from the request
    new_vars = (req.env_vars or {}).copy()
    new_vars["FORCE_TEMPLATE"] = "true" if req.force_template else "false"
    
    #Merge them (User variables win, but Infra variables are preserved)
    final_vars = {**new_vars, **enriched_vars}
    
    #Update the DB record
    app.name = req.name
    app.github_url = req.github_url
    app.branch = req.branch
    app.env_vars = final_vars
    app.status = "Updating"
    
    #Tell SQLAlchemy the dictionary changed
    flag_modified(app, "env_vars")
    db.commit()
    db.refresh(app)

    #Trigger the redeploy using the merged variables
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


@router.post("/{app_id}/execute")
def execute_command(app_id: str, req: CommandRequest, db: Session = Depends(get_db)):
    """Executes a one-off command inside the running container and returns the logs."""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if app.status != "Running":
        raise HTTPException(status_code=400, detail="App must be running to execute commands.")

    try:
        # Find the running app container
        container = client.containers.get(f"imhotep_run_{app_id}")
        
        # Execute the command inside the container
        print(f"Executing '{req.command}' in {app_id}...")
        exit_code, output = container.exec_run(
            cmd=req.command,
            workdir="/app" # Ensure it runs in the root
        )
        
        # Return the terminal output back to the frontend!
        return {
            "exit_code": exit_code,
            "output": output.decode("utf-8") # Decode the raw bytes into a readable string
        }
        
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container is not currently running.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))