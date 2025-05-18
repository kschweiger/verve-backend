from sqlmodel import SQLModel

from verve_backend.core.db import get_engine

engine = get_engine(echo=True)
SQLModel.metadata.create_all(engine)
