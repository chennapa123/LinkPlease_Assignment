import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app import models  # noqa: F401
from app.database import Base, engine

Base.metadata.create_all(bind=engine)
