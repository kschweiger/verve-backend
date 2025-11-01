from datetime import datetime, timedelta
from typing import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select, text

from verve_backend import crud
from verve_backend.api.routes.equipment import ActivityEquipmentResponse
from verve_backend.models import (
    Activity,
    ActivityCreate,
    Equipment,
    EquipmentCreate,
    EquipmentPublic,
    EquipmentType,
    User,
)


def test_activity_equipment_relationship(db: Session) -> None:
    user = db.exec(select(User)).first()
    assert user is not None

    activity = crud.create_activity(
        session=db,
        create=ActivityCreate(
            start=datetime(year=2025, month=2, day=1, hour=12),
            duration=timedelta(days=0, seconds=60 * 60 * 2),
            distance=10.0,
            type_id=1,
            sub_type_id=1,
            name=None,
        ),
        user=user,  # type: ignore
    )

    data = dict(
        name="My Favorite Bike",
        equipment_type=EquipmentType.BIKE,
        brand="Trek",
        model="Domane SL 7",
        purchase_date=datetime(2023, 2, 1),
        user_id=user.id,
    )

    equipment = Equipment(**data)  # type: ignore

    db.add(equipment)
    activity.equipment.append(equipment)
    db.commit()

    reloaded_activity = db.get(Activity, activity.id)
    assert reloaded_activity is not None
    assert len(reloaded_activity.equipment) == 1
    del reloaded_activity

    rel_data = db.exec(text("SELECT *  FROM activity_equipment")).all()  # type: ignore
    activity_ids = [a for a, _ in rel_data]
    assert activity.id in activity_ids

    activity.equipment.remove(equipment)
    db.commit()

    reloaded_activity = db.get(Activity, activity.id)
    assert reloaded_activity is not None
    assert len(reloaded_activity.equipment) == 0
    del reloaded_activity

    rel_data = db.exec(text("SELECT *  FROM activity_equipment")).all()  # type: ignore
    activity_ids = [a for a, _ in rel_data]
    assert activity.id not in activity_ids

    db.delete(activity)
    db.delete(equipment)
    db.commit()


@pytest.fixture
def activity_with_equipment(
    db: Session,
) -> Generator[tuple[UUID, UUID], None, None]:
    user = db.exec(select(User)).first()
    assert user is not None
    activity = Activity(
        start=datetime(year=2025, month=3, day=1, hour=12),
        duration=timedelta(days=0, seconds=60 * 60 * 2),
        distance=15.0,
        type_id=1,
        sub_type_id=1,
        name="Activity for equipment testing",
        user_id=user.id,
    )

    equipment = Equipment(
        name="Road Bike",
        equipment_type=EquipmentType.BIKE,
        brand="Specialized",
        model="Allez",
        purchase_date=datetime(2022, 5, 1),
        user_id=user.id,
    )

    activity.equipment.append(equipment)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    db.refresh(equipment)

    yield activity.id, equipment.id

    activity.equipment.remove(equipment)
    db.delete(activity)
    db.delete(equipment)
    db.commit()


@pytest.fixture
def temp_equipment(db: Session) -> Generator[UUID, None, None]:
    user = db.exec(select(User)).first()
    assert user is not None
    equipment = Equipment(
        name="Mountain Bike",
        equipment_type=EquipmentType.BIKE,
        brand="Propain",
        model="Hugene",
        purchase_date=datetime(2023, 5, 1),
        user_id=user.id,
    )

    db.add(equipment)
    db.commit()

    yield equipment.id

    db.delete(equipment)
    db.commit()


def test_create_equipment(client: TestClient, user1_token: str) -> None:
    equipment_create = EquipmentCreate(
        name="Create Bike",
        equipment_type=EquipmentType.BIKE,
    )

    response = client.post(
        "/equipment",
        headers={"Authorization": f"Bearer {user1_token}"},
        json=equipment_create.model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200
    EquipmentPublic.model_validate(response.json())


def test_get_equipment_for_activity(
    client: TestClient,
    user1_token: str,
    activity_with_equipment: tuple[UUID, UUID],
) -> None:
    activity_id, _ = activity_with_equipment
    response = client.get(
        f"/equipment/activity/{activity_id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    print(response.json())
    assert response.status_code == 200
    data = ActivityEquipmentResponse.model_validate(response.json())
    assert len(data.equipment) == 1


def test_add_equipment(
    client: TestClient,
    user1_token: str,
    activity_with_equipment: tuple[UUID, UUID],
    temp_equipment: UUID,
) -> None:
    activity_id, _ = activity_with_equipment
    response = client.post(
        f"/equipment/{temp_equipment}/activity/{activity_id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    print(response.json())
    assert response.status_code == 200


def test_remove_equipment(
    client: TestClient,
    db: Session,
    user1_token: str,
) -> None:
    user = db.exec(select(User)).first()
    assert user is not None
    activity = Activity(
        start=datetime(year=2025, month=12, day=24, hour=12),
        duration=timedelta(days=0, seconds=60 * 60 * 2),
        distance=15.0,
        type_id=3,
        sub_type_id=13,
        name="Downhill Auf der schwarzen Alb",
        user_id=user.id,
    )

    equipment = Equipment(
        name="Skis",
        equipment_type=EquipmentType.SKIS,
        user_id=user.id,
    )

    activity.equipment.append(equipment)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    db.refresh(equipment)

    response = client.delete(
        f"/equipment/{equipment.id}/activity/{activity.id}",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    print(response.json())
    assert response.status_code == 200

    reloaded_activity = db.get(Activity, activity.id)
    assert reloaded_activity is not None
    assert len(reloaded_activity.equipment) == 0
