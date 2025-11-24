from datetime import datetime, timedelta

from sqlmodel import Session, select, text

from verve_backend import crud
from verve_backend.models import (
    Activity,
    ActivityCreate,
    Equipment,
    EquipmentCreate,
    EquipmentType,
    User,
)
from verve_backend.result import is_ok


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
    ).unwrap()

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


def test_equipment_sets(db: Session) -> None:
    user = db.exec(select(User)).first()
    assert user is not None

    e1 = crud.create_equipment(
        session=db,
        data=EquipmentCreate(
            name="Equipment for set 1",
            equipment_type=EquipmentType.BIKE,
        ),
        user_id=user.id,
    )
    e2 = crud.create_equipment(
        session=db,
        data=EquipmentCreate(
            name="Equipment for set 2",
            equipment_type=EquipmentType.SHOES,
        ),
        user_id=user.id,
    )

    e_set = crud.create_equipment_set(
        session=db,
        name="Set 1",
        data=[e1.unwrap(), e2.unwrap()],
        user_id=user.id,
    )

    assert is_ok(e_set)
