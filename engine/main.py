from fastapi import FastAPI
from api.routes import apps, system
from db.database import engine, Base
import db.models

# Create tables
Base.metadata.create_all(bind=engine)

# Initialize the app
app = FastAPI(
    title="Imhotep Host API",
    description="The deployment engine for self-hosted PaaS.",
    version="1.0.0"
)

# Include your routers (like registering Django apps)
app.include_router(apps.router, prefix="/api/apps", tags=["Applications"])
app.include_router(system.router, prefix="/api/system", tags=["System Health"])

@app.get("/")
async def root():
    return {"message": "Imhotep Engine is running."}