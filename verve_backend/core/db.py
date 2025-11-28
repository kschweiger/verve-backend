# from app import crud
import logging

from sqlalchemy import Engine
from sqlmodel import create_engine

from verve_backend.core.config import settings

# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")


def get_engine(echo: bool = False, rls: bool = False) -> Engine:
    _connect_args = {"options": f"-csearch_path={settings.POSTGRES_SCHEMA},public"}
    return create_engine(
        str(
            settings.SQLALCHEMY_RLS_DATABASE_URI
            if rls
            else settings.SQLALCHEMY_DATABASE_URI
        ),
        connect_args=_connect_args,
        echo=echo,
    )
