from pydantic import BaseModel
from typing import Optional, Dict

class AppCreate(BaseModel):
    name: str
    github_url: str
    branch: str = "main"
    stack: str = "django"
    root_directory: str = "/"
    include_db: bool = False
    env_vars: Optional[Dict[str, str]] = {}

class AppResponse(BaseModel):
    id: str
    name: str
    cloudflare_url: Optional[str] = None
    status: str

    class Config:
        from_attributes = True

class CommandRequest(BaseModel):
    command: str