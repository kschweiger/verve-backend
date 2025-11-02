import argparse
import sys

from sqlmodel import Session, text

from verve_backend.core.db import get_engine
from verve_backend.models import ActivitySubType, ActivityType

ACTIVITY_TYPES = {
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

RSL_TABLES = [
    ("activity", "activities"),
    ("track_point", "track_points"),
    ("goal", "goals"),
    ("raw_track_data", "raw_track_data"),
    ("image", "image"),
    ("user_setting", "user_settings"),
    ("zone_interval", "zone_intervals"),
    ("activity_name", "activity_names"),
    ("equipment", "equipment"),
]


def setup_activity_types(session: Session) -> None:
    """Set up activity types and subtypes in the database."""
    print("Setting up activity types and subtypes...")
    for _type, sub_types in ACTIVITY_TYPES.items():
        atype = ActivityType(name=_type)
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
            session.exec(
                text(
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


def setup_db(session: Session, schema: str = "verve") -> None:
    """Run full database setup (activity types + RLS)."""
    setup_activity_types(session)
    setup_rls_policies(session, schema)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Verve Backend Database Setup - Sets up activity types and RLS policies"
    )
    parser.add_argument(
        "--schema",
        type=str,
        default="verve",
        help="Database schema name (default: verve)",
    )

    args = parser.parse_args()

    try:
        print("Starting database setup...\n")
        engine = get_engine()

        with Session(engine) as session:
            setup_db(session, schema=args.schema)

        print("\n✓ Database setup completed successfully!")

    except Exception as e:
        print(f"\n✗ Error during database setup: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
