from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select
from starlette.status import (
    HTTP_204_NO_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from verve_backend import crud
from verve_backend.api.common.utils import validate_sub_type_id
from verve_backend.api.definitions import Tag
from verve_backend.api.deps import UserSession
from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
    DefaultEquipmentSet,
    DictResponse,
    Equipment,
    EquipmentCreate,
    EquipmentPublic,
    EquipmentSet,
    EquipmentSetPublic,
    EquipmentType,
    ListResponse,
)
from verve_backend.result import Err, Ok

router = APIRouter(prefix="/equipment", tags=[Tag.EQUIPMENT])


class EquipmentSetCreate(BaseModel):
    name: str = Field(description="Name of the equipment set")
    equipment_ids: list[UUID] = Field(
        description="Optional equipment ids that should be added to the set",
        default_factory=list,
    )


@router.get("/types", response_model=ListResponse[EquipmentType])
def get_equipment_types() -> Any:
    return ListResponse(data=[e for e in EquipmentType])


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


@router.get("/", response_model=ListResponse[EquipmentPublic])
def get_equipment(*, user_session: UserSession) -> Any:
    _, session = user_session

    all_equipment = session.exec(select(Equipment)).all()

    return ListResponse(data=[EquipmentPublic.model_validate(e) for e in all_equipment])


@router.get("/activity/{activity_id}", response_model=ListResponse[EquipmentPublic])
def get_equipment_for_activity(
    *,
    user_session: UserSession,
    activity_id: UUID,
) -> Any:
    _, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    return ListResponse(
        data=[EquipmentPublic.model_validate(e) for e in activity.equipment]
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


@router.get("/set/", response_model=ListResponse[EquipmentSetPublic])
def get_sets(
    *,
    user_session: UserSession,
) -> Any:
    _, session = user_session

    user_sets = session.exec(select(EquipmentSet)).all()

    return ListResponse(
        data=[
            EquipmentSetPublic(
                id=equip_set.id,
                name=equip_set.name,
                items=[item.id for item in equip_set.items],
            )
            for equip_set in user_sets
        ]
    )


@router.post("/set/", response_model=EquipmentSetPublic)
def create_set(
    *,
    user_session: UserSession,
    data: EquipmentSetCreate,
) -> Any:
    _user_id, session = user_session
    user_id = UUID(_user_id)

    items = []
    for eid in data.equipment_ids:
        item = session.get(Equipment, eid)

        if item is None:
            raise HTTPException(status_code=404, detail=f"Equipment {eid} not found")

        items.append(item)

    equipment_set = crud.create_equipment_set(
        session=session,
        name=data.name,
        data=items,
        user_id=user_id,
    )

    match equipment_set:
        case Ok(equip_set):
            return EquipmentSetPublic(
                id=equip_set.id,
                name=equip_set.name,
                items=[item.id for item in equip_set.items],
            )
        case Err(err):
            raise HTTPException(status_code=400, detail=str(err))


@router.delete(
    "/set/{set_id}",
    status_code=HTTP_204_NO_CONTENT,
)
def delete_set(
    *,
    user_session: UserSession,
    set_id: UUID,
) -> None:
    _, session = user_session
    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    session.delete(equipment_set)
    session.commit()


@router.get("/set/{set_id}", response_model=EquipmentSetPublic)
def get_set(
    *,
    user_session: UserSession,
    set_id: UUID,
) -> Any:
    _, session = user_session
    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    return EquipmentSetPublic(
        id=equipment_set.id,
        name=equipment_set.name,
        items=[item.id for item in equipment_set.items],
    )


@router.post(
    "/set/{set_id}/equipment/{equipment_id}", response_model=EquipmentSetPublic
)
def add_equipment_to_set(
    *,
    user_session: UserSession,
    set_id: UUID,
    equipment_id: UUID,
) -> Any:
    _, session = user_session
    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    equipment = session.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    if equipment in equipment_set.items:
        raise HTTPException(status_code=400, detail="Equipment already in set")

    equipment_set.items.append(equipment)
    session.commit()
    session.refresh(equipment_set)

    return EquipmentSetPublic(
        id=equipment_set.id,
        name=equipment_set.name,
        items=[item.id for item in equipment_set.items],
    )


@router.delete(
    "/set/{set_id}/equipment/{equipment_id}",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_equipment_from_set(
    *,
    user_session: UserSession,
    set_id: UUID,
    equipment_id: UUID,
) -> None:
    _, session = user_session
    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    equipment = session.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    if equipment not in equipment_set.items:
        raise HTTPException(status_code=400, detail="Equipment not in set")

    equipment_set.items.remove(equipment)
    session.commit()


@router.post(
    "/set/{set_id}/activity/{activity_id}",
)
def add_set_to_activity(
    *,
    user_session: UserSession,
    set_id: UUID,
    activity_id: UUID,
) -> None:
    _, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    # Add all equipment from the set to the activity
    for equipment in equipment_set.items:
        if equipment not in activity.equipment:
            activity.equipment.append(equipment)

    session.commit()


@router.delete(
    "/set/{set_id}/activity/{activity_id}",
    status_code=HTTP_204_NO_CONTENT,
)
def remove_set_from_activity(
    *,
    user_session: UserSession,
    set_id: UUID,
    activity_id: UUID,
) -> None:
    _, session = user_session
    activity = session.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    # Remove all equipment from the set from the activity
    for equipment in equipment_set.items:
        if equipment in activity.equipment:
            activity.equipment.remove(equipment)

    session.commit()


@router.put(
    "/set/default/{set_id}",
    status_code=HTTP_204_NO_CONTENT,
)
def set_default_set(
    *,
    user_session: UserSession,
    set_id: UUID,
    activity_type_id: int,
    activity_sub_type_id: int | None = None,
) -> None:
    _user_id, session = user_session
    user_id = UUID(_user_id)

    equipment_set = session.get(EquipmentSet, set_id)
    if not equipment_set:
        raise HTTPException(status_code=404, detail="Equipment set not found")

    activity_type = session.get(ActivityType, activity_type_id)
    if not activity_type:
        raise HTTPException(status_code=404, detail="Activity type not found")
    if activity_sub_type_id:
        validate_sub_type_id(
            session, ActivitySubType, activity_type_id, activity_sub_type_id
        )

    match crud.put_default_equipment_set(
        session=session,
        user_id=user_id,
        set_id=set_id,
        activity_type_id=activity_type_id,
        activity_sub_type_id=activity_sub_type_id,
    ):
        case Ok(_):
            return
        case Err(err_id):
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to set default equipment set. Error code: {err_id}",
            )


@router.get(
    "/set/default/all", response_model=DictResponse[tuple[int, int | None], UUID]
)
def get_default_sets(
    *,
    user_session: UserSession,
) -> Any:
    _, session = user_session

    all_sets = session.exec(select(DefaultEquipmentSet)).all()

    resp = {}
    for _set in all_sets:
        resp[(_set.type_id, _set.sub_type_id)] = _set.set_id

    return DictResponse(data=resp)
