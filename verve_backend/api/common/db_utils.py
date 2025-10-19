import uuid
from typing import Type, TypeVar

from fastapi import HTTPException
from sqlmodel import Session, SQLModel
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from verve_backend.models import ActivitySubType

T = TypeVar("T", bound=SQLModel)


def check_and_raise_primary_key(
    session: Session, obj: Type[T], id: int | uuid.UUID | None
) -> None:
    if id is not None and session.get(obj, id) is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"{obj.__name__} with id {id} not found",
        )


def validate_sub_type_id(session: Session, type_id: int, sub_type_id: int) -> None:
    sub_type = session.get(ActivitySubType, sub_type_id)
    if sub_type is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"ActivitySubType with id {id} not found",
        )
    if type_id != sub_type.type_id:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"sub_type {sub_type_id} does not belong to type {type_id}",
        )
