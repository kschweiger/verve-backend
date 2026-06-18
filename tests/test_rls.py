from sqlmodel import SQLModel

from verve_backend import models  # noqa: F401
from verve_backend.cli.setup_db import RSL_TABLES


def test_all_user_owned_tables_are_in_rls_setup_list() -> None:
    user_owned_tables = {
        table.name
        for table in SQLModel.metadata.tables.values()
        if "user_id" in table.c
    }
    rls_tables = {table_name for _, table_name in RSL_TABLES}

    assert user_owned_tables <= rls_tables
