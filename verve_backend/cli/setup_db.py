import argparse
import sys

from sqlmodel import Session, text

from verve_backend.core.db import get_engine
from verve_backend.models import (
    ActivitySubType,
    ActivityType,
    DistanceRequirement,
    UserCreate,
)
from verve_backend.result import Err, Ok

ACTIVITY_TYPES = {
    "Cycling": [
        "Road",
        "Mountain Bike",
        "Gravel",
        "Cyclocross",
        "Indoor",
        "E-Mountain Bike",
    ],
    "Foot Sports": ["Walk", "Run", "Hike", "Trail Run", "Nordic Walking", "Treadmill"],
    "Winter Sports": ["Cross-country Skiing", "Snowshoeing", "Downhill Skiing"],
    "Swimming": ["Indoor", "Outdoor Pool", "Open Water"],
    "Strength Training": [
        "Weight Training",
        "Bodyweight",
        "Powerlifting",
        "CrossFit",
        "Circuit Training",
    ],
    "Indoor Cardio": [
        "Elliptical",  # Cross Trainer
        "Stair Stepper",
        "Indoor Rowing",
    ],
    "Fitness & Flexibility": [
        "Yoga",
        "Pilates",
        "HIIT",
    ],
    "Climbing": [
        "Bouldering",
        "Sport Climbing",
        "Indoor Climbing",
        "Outdoor Climbing",
    ],
    "Other": ["Skateboarding", "Other"],
}

DISTANCE_FORBIDDEN_TYPES = ["Strength Training", "Fitness & Flexibility"]

DISTANCE_OPTIONAL_TYPES = ["Winter Sports", "Indoor Cardio", "Other"]

RSL_TABLES = [
    ("activity", "activities"),
    ("activity_highlights", "activity_highlights"),
    ("track_point", "track_points"),
    ("goal", "goals"),
    ("raw_track_data", "raw_track_data"),
    ("image", "image"),
    ("user_setting", "user_settings"),
    ("zone_interval", "zone_intervals"),
    ("equipment", "equipment"),
    ("equipment_set", "equipment_sets"),
    ("default_equipment_set", "default_equipment_sets"),
    ("location", "locations"),
]


def setup_activity_types(session: Session) -> None:
    """Set up activity types and subtypes in the database."""
    print("Setting up activity types and subtypes...")
    for _type, sub_types in ACTIVITY_TYPES.items():
        if _type in DISTANCE_FORBIDDEN_TYPES:
            req = DistanceRequirement.NOT_APPLICABLE
        elif _type in DISTANCE_OPTIONAL_TYPES:
            req = DistanceRequirement.OPTIONAL
        else:
            req = DistanceRequirement.REQUIRED

        atype = ActivityType(name=_type, distance_requirement=req)
        session.add(atype)
        session.commit()
        session.refresh(atype)
        print(f"  Created activity type: {_type}")

        for sub_type in sub_types:
            stype = ActivitySubType(name=sub_type, type_id=atype.id)
            session.add(stype)
            session.commit()
            print(f"    Created activity subtype: {sub_type}")
    print("Activity types setup complete!")


def setup_rls_policies(session: Session, schema: str = "verve") -> None:
    """Set up Row Level Security policies for tables."""
    print("Setting up Row Level Security policies...")
    for relation_prefix, table_name in RSL_TABLES:
        try:
            session.exec(  # type: ignore
                text(  # type: ignore
                    f"""
                ALTER TABLE {schema}.{table_name} ENABLE ROW LEVEL SECURITY;
                CREATE POLICY {relation_prefix}_isolation_policy
                ON {schema}.{table_name}
                FOR ALL USING (
                    user_id = current_setting('verve_user.curr_user')::uuid
                );
                """
                )
            )
            session.commit()
            print(f"  Enabled RLS for table: {table_name}")
        except Exception as e:
            print(f"  Warning: Failed to setup RLS for {table_name}: {e}")
            session.rollback()
    print("RLS policies setup complete!")


def create_admin_user(session: Session, password: str) -> None:
    from verve_backend.crud import create_user

    user = UserCreate(
        name="verve_admin",
        email="admin@verve-outdoors.com",
        password=password,
    )
    match create_user(
        session=session,
        user_create=user,
        is_admin=True,
    ):
        case Ok(user):
            print("Admin user created")
        case Err(_id):
            print("Creating admin user failed")


def setup_db(session: Session, admin_pw: str, schema: str = "verve") -> None:
    """Run full database setup (activity types + RLS)."""
    setup_activity_types(session)
    # setup_rls_policies(session, schema)
    create_admin_user(session, admin_pw)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Verve Backend Database Setup - Sets up activity types and the admin user"
        )
    )
    parser.add_argument(
        "--schema",
        type=str,
        default="verve",
        help="Database schema name (default: verve)",
    )
    parser.add_argument(
        "--admin-pw",
        type=str,
        help="Password for the admin user",
    )
    parser.add_argument(
        "--create-tables",
        action="store_true",
        help="Create all database tables",
    )
    args = parser.parse_args()

    if len(args.admin_pw) < 8:
        print("Please choose a admin password that is at least 8 characters long")
        sys.exit(1)

    try:
        print("Starting database setup...\n")
        engine = get_engine()

        with Session(engine) as session:
            if args.create_tables:
                print("Creating all database tables...")
                from sqlmodel import SQLModel

                from verve_backend import models  # noqa: F401

                SQLModel.metadata.create_all(engine)
                print("Database tables created successfully!\n")

            setup_db(session, schema=args.schema, admin_pw=args.admin_pw)

        print("\n✓ Database setup completed successfully!")

    except Exception as e:
        print(f"\n✗ Error during database setup: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
