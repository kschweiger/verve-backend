"""Import RepDB names and assignments; see https://github.com/RepDB/exercise-dataset."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path

import click
import httpx2
from sqlalchemy import text
from sqlmodel import Session

from verve_backend.core.exercise_catalog import import_repdb, validate_snapshot
from verve_backend.models import ExerciseCatalogImportState

LOCK_ID = 74823391012


def download(url: str) -> bytes:
    response = httpx2.get(url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    return response.content


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_language(path: Path) -> dict:
    data = json.loads(path.read_bytes()) if path.exists() else {}
    if not isinstance(data, dict) or not isinstance(data.get("exercises", {}), dict):
        raise ValueError(f"Invalid translation document: {path}")
    if any(not isinstance(v, str) for v in data.get("exercises", {}).values()):
        raise ValueError(f"Invalid exercise translations: {path}")
    return data


def outputs_match(directory: Path, revision: str) -> bool:
    try:
        manifest = json.loads((directory / "repdb-import.json").read_bytes())
        return (
            manifest["source"] == "repdb"
            and manifest["revision"] == revision
            and bool(re.fullmatch(r"[0-9a-f]{64}", manifest["source_checksum"]))
            and all(
                (directory / f"{language}.json").is_file()
                and manifest["sections"][language]
                == checksum(
                    canonical(
                        read_language(directory / f"{language}.json").get(
                            "exercises", {}
                        )
                    )
                )
                for language in ("en", "de")
            )
        )
    except OSError, ValueError, KeyError, TypeError:
        return False


@click.command()
@click.option(
    "--translations-dir",
    "directory",
    required=True,
    type=click.Path(path_type=Path, file_okay=False),
)
@click.option(
    "--revision", help="Full immutable commit SHA; defaults to upstream HEAD."
)
@click.option(
    "--input",
    "input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
)
@click.option("--dry-run", is_flag=True)
@click.option("--force", is_flag=True)
def main(
    directory: Path,
    revision: str | None,
    input_path: Path | None,
    dry_run: bool,
    force: bool,
) -> None:
    """Import RepDB exercises and merge English/German name files."""
    if input_path and not revision:
        raise click.UsageError("--input requires --revision")
    try:
        click.echo(
            json.dumps(
                run_import(directory, revision, input_path, dry_run, force),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    except Exception as error:
        raise click.ClickException(str(error)) from error


def run_import(
    directory: Path,
    revision: str | None,
    input_path: Path | None,
    dry_run: bool,
    force: bool,
) -> dict:
    from verve_backend.core.db import get_engine

    if revision is None:
        revision = json.loads(
            download("https://api.github.com/repos/RepDB/exercise-dataset/commits/HEAD")
        )["sha"]
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("Revision must be a full immutable commit SHA")
    revision = revision.lower()
    # Keep the same physical connection across commits for the session lock.
    with get_engine(rls=False).connect() as connection:
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_ID})
        try:
            connection.commit()
            with Session(connection) as session:
                state = session.get(ExerciseCatalogImportState, "repdb")
                if (
                    not input_path
                    and not force
                    and state is not None
                    and state.completed_revision == revision
                    and outputs_match(directory, revision)
                ):
                    return {"status": "unchanged", "revision": revision}
                languages = {
                    lang: read_language(directory / f"{lang}.json")
                    for lang in ("en", "de")
                }
                raw = (
                    input_path.read_bytes()
                    if input_path
                    else download(
                        f"https://raw.githubusercontent.com/RepDB/exercise-dataset/"
                        f"{revision}/exercises.json"
                    )
                )
                result = import_repdb(
                    session,
                    validate_snapshot(json.loads(raw)),
                    revision,
                    dry_run=dry_run,
                )
                for lang, names in result.names.items():
                    languages[lang].setdefault("exercises", {}).update(names)
                manifest = {
                    "source": "repdb",
                    "revision": revision,
                    "source_checksum": checksum(raw),
                    "sections": {
                        lang: checksum(canonical(data["exercises"]))
                        for lang, data in languages.items()
                    },
                }
                summary = {
                    "status": "dry_run" if dry_run else "imported",
                    "revision": revision,
                    "source_checksum": checksum(raw),
                    **asdict(result),
                    "outputs": [
                        str(directory / name)
                        for name in ("en.json", "de.json", "repdb-import.json")
                    ],
                }
                summary.pop("names")
                if dry_run:
                    session.rollback()
                    return summary
                state = state or ExerciseCatalogImportState(source="repdb")
                state.completed_revision = None
                session.add(state)
                directory.mkdir(parents=True, exist_ok=True)
                staged = []
                committed = False
                try:
                    documents = [
                        (f"{lang}.json", value) for lang, value in languages.items()
                    ]
                    documents.append(("repdb-import.json", manifest))
                    for name, data in documents:
                        with tempfile.NamedTemporaryFile(
                            dir=directory, delete=False
                        ) as f:
                            staged.append((Path(f.name), directory / name))
                            f.write(canonical(data))
                    session.commit()
                    committed = True
                    for temporary, destination in staged:
                        os.replace(temporary, destination)
                    state.completed_revision = revision
                    session.add(state)
                    session.commit()
                except Exception as error:
                    session.rollback()
                    if committed:
                        raise RuntimeError(
                            "Database import succeeded; output publication or "
                            "completion failed. Retry to repair."
                        ) from error
                    raise
                finally:
                    for temporary, _ in staged:
                        temporary.unlink(missing_ok=True)
                return summary
        finally:
            connection.rollback()
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID}
                )
                connection.commit()
            except Exception:
                connection.invalidate()
                raise


if __name__ == "__main__":
    main()
