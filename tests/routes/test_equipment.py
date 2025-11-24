from datetime import datetime, timedelta
from typing import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from verve_backend.api.routes.equipment import EquipmentSetCreate
from verve_backend.models import (
    Activity,
    ActivityCreate,
    ActivityPublic,
    DefaultEquipmentSet,
    Equipment,
    EquipmentCreate,
    EquipmentPublic,
    EquipmentSetPublic,
    EquipmentType,
    ListResponse,
    User,
)


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
    data = ListResponse.model_validate(response.json())
    assert len(data.data) == 1


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


@pytest.fixture
def equipment_for_set(client: TestClient, temp_user_token: str) -> list[UUID]:
    eq_ids = []
    for i in range(1, 4):
        res_eq = client.post(
            "/equipment",
            headers={"Authorization": f"Bearer {temp_user_token}"},
            json=EquipmentCreate(
                name=f"Set Test Equipment {i}",
                equipment_type=EquipmentType.SKIS,
            ).model_dump(exclude_unset=True, mode="json"),
        )
        eq_1 = EquipmentPublic.model_validate(res_eq.json())
        eq_ids.append(eq_1.id)

    return eq_ids


def test_equipment_set_base_operation(
    client: TestClient, temp_user_token: str, equipment_for_set: list[UUID]
) -> None:
    # Create some equipment
    eq_ids = equipment_for_set

    # Create the set
    set_create = EquipmentSetCreate(
        name="Test Set 1", equipment_ids=[eq_ids[0], eq_ids[1]]
    )
    response = client.post(
        "/equipment/set/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=set_create.model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200

    created_set = EquipmentSetPublic.model_validate(response.json())
    assert len(created_set.items) == 2

    # Get the set
    response = client.get(
        f"/equipment/set/{created_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200

    get_set = EquipmentSetPublic.model_validate(response.json())
    assert get_set == created_set

    # Add equipment to the set
    response = client.post(
        f"/equipment/set/{created_set.id}/equipment/{eq_ids[2]}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200

    set_after_add = EquipmentSetPublic.model_validate(response.json())
    assert len(set_after_add.items) == 3

    # Delete equipment from the set
    response = client.delete(
        f"/equipment/set/{created_set.id}/equipment/{eq_ids[0]}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204

    response = client.get(
        f"/equipment/set/{created_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200

    set_after_delete = EquipmentSetPublic.model_validate(response.json())
    assert eq_ids[0] not in set_after_delete.items

    # Make sure that deleting the equipment from the set does not delete the equipment
    response = client.get(
        "/equipment/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200

    user_equipment = ListResponse[EquipmentPublic].model_validate(response.json())
    assert eq_ids[0] in [e.id for e in user_equipment.data]

    # Delete the set
    response = client.delete(
        f"/equipment/set/{created_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204

    response = client.get(
        f"/equipment/set/{created_set.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 404

    # Make sure that deleting the set does not delete the equipment
    response = client.get(
        "/equipment/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200

    user_equipment = ListResponse[EquipmentPublic].model_validate(response.json())
    assert set([e.id for e in user_equipment.data]) == set(eq_ids)


def test_equipment_set_activity_integration(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    equipment_for_set: list[UUID],
) -> None:
    response = client.post(
        "/activity/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=ActivityCreate(
            start=datetime.now(),
            duration=timedelta(minutes=10),
            distance=10,
            type_id=1,
            sub_type_id=None,
            name="Set Test id",
        ).model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200
    activity = ActivityPublic.model_validate(response.json())
    client.post(
        f"/equipment/{equipment_for_set[0]}/activity/{activity.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    set_create = EquipmentSetCreate(
        name="Test Set 1", equipment_ids=[equipment_for_set[2], equipment_for_set[1]]
    )
    response = client.post(
        "/equipment/set/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=set_create.model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200

    created_set = EquipmentSetPublic.model_validate(response.json())

    response = client.post(
        f"/equipment/set/{created_set.id}/activity/{activity.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200

    _activity = db.get(Activity, activity.id)
    assert _activity is not None
    assert len(_activity.equipment) == 3
    del _activity

    response = client.delete(
        f"/equipment/set/{created_set.id}/activity/{activity.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204

    _activity = db.get(Activity, activity.id)
    assert _activity is not None
    assert len(_activity.equipment) == 1


@pytest.mark.parametrize(
    ("type_id", "sub_type_id"),
    [
        (1, None),
        (1, 1),
    ],
)
def test_create_default_set(
    db: Session,
    client: TestClient,
    temp_user_token: str,
    equipment_for_set: list[UUID],
    type_id: int,
    sub_type_id: int | None,
) -> None:
    eq_ids = equipment_for_set

    # Create the set
    set_create = EquipmentSetCreate(
        name="Test Set 1", equipment_ids=[eq_ids[0], eq_ids[1]]
    )
    response = client.post(
        "/equipment/set/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=set_create.model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200
    created_set = EquipmentSetPublic.model_validate(response.json())

    params = {"activity_type_id": type_id}
    if sub_type_id is not None:
        params["activity_sub_type_id"] = sub_type_id
    response = client.put(
        f"/equipment/set/default/{created_set.id}",
        params=params,
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 204

    default_sets = db.exec(
        select(DefaultEquipmentSet).where(DefaultEquipmentSet.set_id == created_set.id)
    ).all()

    assert len(default_sets) == 1


def test_get_defautl_sets(
    client: TestClient,
    temp_user_token: str,
    equipment_for_set: list[UUID],
) -> None:
    eq_ids = equipment_for_set

    # Create the sets
    response = client.post(
        "/equipment/set/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=EquipmentSetCreate(
            name="Test Set 1", equipment_ids=[eq_ids[0], eq_ids[1]]
        ).model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200
    set_1 = EquipmentSetPublic.model_validate(response.json())
    response = client.post(
        "/equipment/set/",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        json=EquipmentSetCreate(
            name="Test Set 1", equipment_ids=[eq_ids[2]]
        ).model_dump(exclude_unset=True, mode="json"),
    )
    assert response.status_code == 200
    set_2 = EquipmentSetPublic.model_validate(response.json())

    # Make the default sets
    client.put(
        f"/equipment/set/default/{set_1.id}",
        params={"activity_type_id": 1},
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    # Same set can be default for multiple types
    client.put(
        f"/equipment/set/default/{set_1.id}",
        params={"activity_type_id": 1, "activity_sub_type_id": 1},
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    client.put(
        f"/equipment/set/default/{set_2.id}",
        params={"activity_type_id": 1, "activity_sub_type_id": 2},
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    response = client.get(
        "/equipment/set/default/all",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 3
