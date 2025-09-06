import uuid
from typing import Type, TypeVar

from fastapi import HTTPException
from sqlmodel import Session, SQLModel
from starlette.status import (
    HTTP_404_NOT_FOUND,
)

T = TypeVar("T", bound=SQLModel)


def check_and_raise_primary_key(
    session: Session, obj: Type[T], id: int | uuid.UUID | None
) -> None:
    if id is not None and session.get(obj, id) is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"{obj.__name__} with id {id} not found",
        )
