import importlib.resources
from functools import lru_cache
from typing import Literal

from sqlalchemy import Engine
from sqlmodel import create_engine

from verve_backend.core.config import settings


def _build_engine(rls: bool, echo: bool) -> Engine:
    """
    Private factory — only called once per (rls, echo) combination
    because get_engine() is cached below.
    Never call create_engine() outside of here.
    """
    _connect_args = {"options": f"-csearch_path={settings.POSTGRES_SCHEMA},public"}
    return create_engine(
        str(
            settings.SQLALCHEMY_RLS_DATABASE_URI
            if rls
            else settings.SQLALCHEMY_DATABASE_URI
        ),
        connect_args=_connect_args,
        echo=echo,
        pool_size=settings.ENGINE_POOL_SIZE,
        max_overflow=settings.ENGINE_MAX_OVERFLOW,
        pool_timeout=settings.ENGINE_POOL_TIMEOUT,
        pool_recycle=settings.ENGINE_POOL_RECYCLE,
        pool_pre_ping=settings.ENGINE_POOL_PRE_PING,
    )


@lru_cache(maxsize=4)  # caches by (rls, echo) args — at most 4 engine variants
def get_engine(echo: bool = False, rls: bool = False) -> Engine:
    """
    Returns a cached, application-wide Engine singleton.
    lru_cache guarantees create_engine() is called at most once
    per unique combination of arguments, for the entire process lifetime.
    """
    return _build_engine(rls=rls, echo=echo)


@lru_cache(maxsize=16)
def get_search_query(table_name: Literal["activity_tags"]) -> str:
    template = (
        importlib.resources.files("verve_backend.queries")
        .joinpath("search_name_fuzzy.sql")
        .read_text(encoding="utf-8")
    )
    return template.replace("{__table_name__}", table_name)
