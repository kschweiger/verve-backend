"""Synchronize the bundled exercise catalog without network or file writes."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click
from sqlalchemy import text
from sqlmodel import Session, select

from verve_backend.core.exercise_catalog import sync_catalog
from verve_backend.core.exercise_catalog_data import load_catalog
from verve_backend.models import ExerciseCatalogSyncState

LOCK_ID = 74823391012
SYNC_VERSION = 1


@click.command()
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
)
@click.option("--dry-run", is_flag=True)
@click.option("--force", is_flag=True)
def main(input_path: Path | None, dry_run: bool, force: bool) -> None:
    """Apply the bundled catalog, or validate and preview a local JSON file."""
    try:
        summary = run_import(input_path, dry_run=dry_run, force=force)
    except Exception as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def run_import(
    input_path: Path | None = None, *, dry_run: bool = False, force: bool = False
) -> dict[str, Any]:
    snapshot = load_catalog(input_path)
    # Invalid input must fail even when the database is unavailable or up to date.
    from verve_backend.core.db import get_engine

    summary = {
        "catalog_code": snapshot.catalog_code,
        "content_hash": snapshot.content_hash,
    }
    with Session(get_engine(rls=False)) as session:
        try:
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_ID}
            )
            states = session.exec(select(ExerciseCatalogSyncState)).all()
            state = next(
                (row for row in states if row.catalog_code == snapshot.catalog_code),
                None,
            )
            if (
                not dry_run
                and not force
                and len(states) == 1
                and state is not None
                and state.content_hash == snapshot.content_hash
                and state.sync_version == SYNC_VERSION
            ):
                session.rollback()
                return {"status": "unchanged", **summary}
            result = sync_catalog(session, snapshot, dry_run=dry_run)
            if dry_run:
                session.rollback()
                return {"status": "dry_run", **summary, **asdict(result)}
            # Group definitions are global; only the currently applied catalog
            # can have a valid checkpoint after replacing them.
            for previous in states:
                if previous is not state:
                    session.delete(previous)
            if state is None:
                state = ExerciseCatalogSyncState(
                    catalog_code=snapshot.catalog_code,
                    content_hash=snapshot.content_hash,
                    sync_version=SYNC_VERSION,
                )
            else:
                state.content_hash = snapshot.content_hash
                state.sync_version = SYNC_VERSION
            session.add(state)
            session.commit()
            return {"status": "imported", **summary, **asdict(result)}
        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    main()
