from sqlalchemy import Column, Integer, String, JSON
from .database import Base

class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    github_url = Column(String)
    branch = Column(String)
    stack = Column(String)
    network_name = Column(String)
    cloudflare_url = Column(String)
    env_vars = Column(JSON)
