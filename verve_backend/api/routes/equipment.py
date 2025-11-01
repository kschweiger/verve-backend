import logging
from typing import Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    Activity,
    Equipment,
    EquipmentCreate,
    EquipmentPublic,
)

T = TypeVar("T", int, float)


# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/equipment", tags=[Tag.EQUIPMENT])


@router.post("/", response_model=EquipmentPublic)
def create_equipment(
    *,
    user_session: UserSession,
    data: EquipmentCreate,
) -> Any:
    user_id, session = user_session

    equipment = Equipment.model_validate(data, update={"user_id": user_id})
    session.add(equipment)
    session.commit()

    return equipment


class ActivityEquipmentResponse(BaseModel):
    equipment: list[EquipmentPublic]


@router.get("/activity/{activity_id}", response_model=ActivityEquipmentResponse)
def get_equipment_for_activity(
    *,
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    return ActivityEquipmentResponse(
        equipment=[EquipmentPublic.model_validate(e) for e in activity.equipment]
    )


@router.post(
    "/{equipment_id}/activity/{activity_id}",
)
def add_equipment_to_activity(
    *,
    user_session: UserSession,
    equipment_id: UUID,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    equipment = session.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    activity.equipment.append(equipment)
    session.commit()

    return {"detail": "Equipment added to activity successfully"}


@router.delete(
    "/{equipment_id}/activity/{activity_id}",
)
def remove_equipment_to_activity(
    *,
    user_session: UserSession,
    equipment_id: UUID,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    equipment = session.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    activity.equipment.remove(equipment)
    session.commit()

    return {"detail": "Equipment removed from activity"}
