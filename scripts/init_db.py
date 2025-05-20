from datetime import datetime, timedelta

from sqlalchemy import text
from sqlmodel import Session, SQLModel

from verve_backend import crud, models
from verve_backend.core.db import get_engine

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

    session.exec(
        text(f"""
    ALTER TABLE verve.activities ENABLE ROW LEVEL SECURITY;
    CREATE POLICY activity_isolation_policy ON verve.activities
        FOR ALL USING (user_id = current_setting('verve_user.curr_user')::uuid);
    """)
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
            type_id=1,
            sub_type_id=2,
        ),
        user=created_users[1],
    )
