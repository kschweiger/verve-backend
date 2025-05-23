from datetime import datetime, timedelta
from pathlib import Path

from geo_track_analyzer import FITTrack
from sqlalchemy import text
from sqlmodel import Session, SQLModel

from verve_backend import crud, models
from verve_backend.core.db import get_engine
from verve_backend.enums import GoalAggregation, GoalType, TemportalType

engine = get_engine(echo=True)
SQLModel.metadata.drop_all(engine)  # DANGERZONE:
SQLModel.metadata.create_all(engine)

activity_types = {
    "Cycling": [
        "Road",
        "Mountain Bike",
        "Gravel",
        "Cyclocross",
        "Indoor",
        "E-Mountain Bike",
    ],
    "Foot Sports": ["Run", "Hike", "Trail Run", "Nordic Walking"],
    "Winter Sports": ["Cross-country Skiing", "Snowshoeing", "Downhill Skiing"],
    "Other": ["Climbing", "Skateboarding", "Other"],
}

with Session(engine) as session:
    for _type, sub_types in activity_types.items():
        atype = models.ActivityType(name=_type)
        session.add(atype)
        session.commit()
        session.refresh(atype)
        for sub_type in sub_types:
            stype = models.ActivitySubType(name=sub_type, type_id=atype.id)
            session.add(stype)
            session.commit()

    for a, b in [
        ("activity", "activities"),
        ("track_point", "track_points"),
        ("goal", "goals"),
    ]:
        session.exec(
            text(f"""
            ALTER TABLE verve.{b} ENABLE ROW LEVEL SECURITY;
            CREATE POLICY {a}_isolation_policy ON verve.{b}
            FOR ALL USING (user_id = current_setting('verve_user.curr_user')::uuid);
            """)  # type: ignore
        )
        session.commit()

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
            )
        )
    activity_1 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=1, hour=12),
            duration=timedelta(days=0, seconds=60 * 60 * 2),
            distance=10.0,
            type_id=1,
            sub_type_id=1,
        ),
        user=created_users[0],
    )

    activity_2 = crud.create_activity(
        session=session,
        create=models.ActivityCreate(
            start=datetime(year=2025, month=1, day=2, hour=13),
            duration=timedelta(days=0, seconds=60 * 60 * 1),
            distance=30.0,
            type_id=1,
            sub_type_id=2,
        ),
        user=created_users[1],
    )

    crud.create_goal(
        session=session,
        goal=models.GoalCreate(
            name="Montly 500 km",
            target=500,
            temporal_type=TemportalType.MONTHLY,
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
            temporal_type=TemportalType.WEEKLY,
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
            temporal_type=TemportalType.YEARLY,
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
            temporal_type=TemportalType.WEEKLY,
            type=GoalType.ACTIVITY,
            aggregation=GoalAggregation.DURATION,
        ),
        user_id=created_users[1].id,
    )
    i_track_added = 1
    for _file in Path("scripts/tracks").iterdir():
        if i_track_added > 3:
            break
        if _file.is_file() and _file.name.endswith(".fit"):
            with open(_file, "rb") as f:
                track = FITTrack(f)

            overview = track.get_track_overview()

            _activity = crud.create_activity(
                session=session,
                create=models.ActivityCreate(
                    start=datetime(year=2025, month=1, day=i_track_added, hour=12),
                    duration=timedelta(days=0, seconds=overview.total_time_seconds),
                    distance=overview.total_distance,
                    type_id=1,
                    sub_type_id=1,
                ),
                user=created_users[0],
            )

            crud.insert_track(
                session=session,
                track=track,
                activity_id=_activity.id,
                user_id=created_users[0].id,
                batch_size=500,
            )
            print("Added track %s" % i_track_added)
            i_track_added += 1
