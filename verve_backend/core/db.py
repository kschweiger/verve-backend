# from app import crud
from sqlalchemy import Engine
from sqlmodel import create_engine

from verve_backend.core.config import settings


def get_engine(echo: bool = False, rls: bool = False) -> Engine:
    return create_engine(
        str(
            settings.SQLALCHEMY_RLS_DATABASE_URI
            if rls
            else settings.SQLALCHEMY_DATABASE_URI
        ),
        connect_args={"options": f"-csearch_path={settings.POSTGRES_SCHEMA},public"},
        echo=echo,
    )
