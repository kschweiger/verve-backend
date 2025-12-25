from datetime import datetime, timedelta
from pathlib import Path

from geo_track_analyzer import FITTrack
from sqlmodel import Session, SQLModel

from verve_backend import crud, models
from verve_backend.cli.setup_db import setup_db
from verve_backend.core.db import get_engine
from verve_backend.enums import GoalAggregation, GoalType, TemporalType
from verve_backend.tasks import process_activity_highlights

engine = get_engine(echo=True)
SQLModel.metadata.drop_all(engine)  # DANGERZONE:
SQLModel.metadata.create_all(engine)

print("---------------------------------------")
print("---------------------------------------")
print("---------------------------------------")
print("---------------------------------------")
print("---------------------------------------")
print("---------------------------------------")
with Session(engine) as session:
    setup_db(session, admin_pw="changeme")

# Testing data.
with Session(engine) as session:
    created_users = []
    for name, pw, email, full_name in [
        ("username1", "12345678", "user1@mail.com", "User Name"),
        ("username2", "12345678", "user2@mail.com", None),
    ]:
        created_users.append(
            crud.create_user(
                session=session,
                user_create=models.UserCreate(
                    name=name, password=pw, email=email, full_name=full_name
                ),
            ).unwrap()
        )
    activity_1 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=1, hour=12),
            duration=timedelta(days=0, seconds=60 * 60 * 2),
            distance=10.0,
            type_id=1,
            sub_type_id=1,
            name=None,
        ),
        user=created_users[0],
    ).unwrap()

    activity_2 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=2, hour=13),
            duration=timedelta(days=0, seconds=60 * 60 * 1),
            distance=30.0,
            type_id=1,
            sub_type_id=2,
            name=None,
        ),
        user=created_users[1],
    ).unwrap()

    crud.create_equipment(
        session=session,
        data=models.EquipmentCreate(
            name="Road Bike",
            equipment_type=models.EquipmentType.BIKE,
            brand="Trek",
            model="Domane 5 (2024)",
        ),
        user_id=created_users[0].id,
        activity_ids=[activity_1.id],
    )
    crud.create_equipment(
        session=session,
        data=models.EquipmentCreate(
            name="Road Shoes",
            equipment_type=models.EquipmentType.SHOES,
        ),
        user_id=created_users[0].id,
        activity_ids=None,  # [activity_1.id],
    )
    crud.create_equipment(
        session=session,
        data=models.EquipmentCreate(
            name="Cross-Country skies",
            equipment_type=models.EquipmentType.SKIS,
            brand="Fischer",
            model="Speedmax 3D",
        ),
        user_id=created_users[1].id,
    )

    crud.create_goal(
        session=session,
        goal=models.GoalCreate(
            name="Montly 500 km",
            target=500,
            temporal_type=TemporalType.MONTHLY,
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.TOTAL_DISTANCE,
        ),
        user_id=created_users[0].id,
    )
    crud.create_goal(
        session=session,
        goal=models.GoalCreate(
            name="3 Activities per week",
            target=3,
            temporal_type=TemporalType.WEEKLY,
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.COUNT,
        ),
        user_id=created_users[0].id,
    )
    crud.create_goal(
        session=session,
        goal=models.GoalCreate(
            name="Counting goal",
            target=5,
            temporal_type=TemporalType.YEARLY,
            type=GoalType.MANUAL,
            aggregation=GoalAggregation.COUNT,
        ),
        user_id=created_users[0].id,
    )
    crud.create_goal(
        session=session,
        goal=models.GoalCreate(
            name="2 hours per week",
            target=60 * 60 * 2,
            temporal_type=TemporalType.WEEKLY,
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.DURATION,
        ),
        user_id=created_users[1].id,
    )
    i_track_added = 1

    session.add_all(
        [
            models.ZoneInterval(
                name="Zone 1",
                metric="heart_rate",
                start=None,
                end=100,
                user_id=created_users[0].id,
                color="#FF0000",
            ),
            models.ZoneInterval(
                name="Zone 2",
                metric="heart_rate",
                start=100,
                end=150,
                user_id=created_users[0].id,
                color="#00FF00",
            ),
            models.ZoneInterval(
                name="Zone 3",
                metric="heart_rate",
                start=150,
                end=None,
                user_id=created_users[0].id,
                color="#0000FF",
            ),
        ]
    )
    session.commit()
    _path = "/Users/korbinian/iCloud/Cycling Tracks/2025/Road"
    # _path = "scripts/tracks"
    _month = 1
    _day = 0
    for _file in Path(_path).iterdir():
        if i_track_added > 2:
            break
        if _file.is_file() and _file.name.endswith(".fit"):
            with open(_file, "rb") as f:
                track = FITTrack(f)

            if _day > 20:
                _day = 1
                _month += 1
            else:
                _day += 1
            overview = track.get_track_overview()

            _activity = crud.create_activity(
                session=session,
                create=models.ActivityCreate(
                    start=datetime(year=2025, month=_month, day=_day, hour=12),
                    duration=timedelta(days=0, seconds=overview.total_time_seconds),
                    distance=overview.total_distance_km,
                    type_id=1,
                    sub_type_id=1,
                    name=None,
                ),
                user=created_users[0],
            ).unwrap()

            crud.insert_track(
                session=session,
                track=track,
                activity_id=_activity.id,
                user_id=created_users[0].id,
                batch_size=500,
            )
            crud.update_activity_with_track_data(
                session=session,
                activity_id=_activity.id,
                track=track,
            )

            process_activity_highlights(_activity.id, created_users[0].id)
            print("Added track %s" % i_track_added)
            i_track_added += 1
