import logging
import sys

from sqlmodel import Session, text

from verve_backend.core.config import settings
from verve_backend.core.db import get_engine

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rls_guard")


def get_tables_with_user_id(session: Session, schema: str) -> list[str]:
    """
    Dynamically find all tables in the schema that contain a 'user_id' column.
    """
    stmt = text("""
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND column_name = 'user_id'
    """)
    results = session.exec(  # type: ignore
        stmt,
        params={"schema": schema},
    ).all()
    # results is a list of tuples like [('activities',), ('goals',)]
    return [r[0] for r in results]


def check_rls_configuration() -> None:
    engine = get_engine()
    schema = settings.POSTGRES_SCHEMA

    logger.info(f"🔒 Verifying RLS for schema: '{schema}'")

    with Session(engine) as session:
        # 1. Discovery Phase
        target_tables = get_tables_with_user_id(session, schema)

        if not target_tables:
            logger.warning(
                "⚠️ No tables with 'user_id' found. Is the database initialized?"
            )
            # If DB is empty, maybe we shouldn't crash, but for a backend that expects
            # data, this is suspicious. Let's allow it to pass (deployment of empty app)
            # or fail. Given this runs AFTER migrations, tables should exist.
            sys.exit(0)

        logger.info(f"   Found {len(target_tables)} sensitive tables: {target_tables}")

        # 2. Verification Phase
        # Check if RLS is actually enabled (relrowsecurity = true)
        stmt_enabled = text("""
            SELECT relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema
              AND c.relname = ANY(:tables)
              AND c.relrowsecurity = true;
        """)

        enabled_tables_result = session.exec(  # type: ignore
            stmt_enabled,
            params={"schema": schema, "tables": target_tables},
        ).all()
        # Flatten results
        enabled_tables = {r[0] for r in enabled_tables_result}

        # 3. Policy Verification Phase
        # Check if active policies exist
        stmt_policies = text("""
            SELECT tablename
            FROM pg_policies
            WHERE schemaname = :schema
              AND tablename = ANY(:tables);
        """)

        tables_with_policies_result = session.exec(  # type: ignore
            stmt_policies,
            params={"schema": schema, "tables": target_tables},
        ).all()
        tables_with_policies = {r[0] for r in tables_with_policies_result}

    # --- Logic & Reporting ---

    errors = []

    # Check A: Is RLS enabled?
    target_set = set(target_tables)
    missing_rls = target_set - enabled_tables

    if missing_rls:
        errors.append(f"❌ RLS NOT ENABLED on: {', '.join(missing_rls)}")

    # Check B: Do policies exist?
    # (Enabling RLS without a policy implies 'Default Deny All', which usually
    # breaks the app for legitimate users, so we flag it as a configuration error)
    missing_policies = target_set - tables_with_policies
    if missing_policies:
        errors.append(
            f"❌ RLS enabled but NO POLICY defined on: {', '.join(missing_policies)}"
        )

    if errors:
        logger.critical("🚨 CRITICAL SECURITY MISCONFIGURATION DETECTED 🚨")
        for error in errors:
            logger.critical(error)
        logger.critical("Stopping container startup to prevent data leakage.")
        sys.exit(1)

    logger.info("✅ Security Check Passed: All user-data tables are protected.")


def main() -> None:
    try:
        check_rls_configuration()
    except Exception as e:
        logger.critical(f"❌ Script failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
