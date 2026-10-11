from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def source_files(root: Path) -> list[Path]:
    """Return fixture files in stable relative-path order."""
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def digest_sources(root: Path) -> str:
    """Hash normalized relative paths and file contents without ambiguity."""
    digest = hashlib.sha256()
    for path in source_files(root):
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(struct.pack(">Q", len(relative_path)))
        digest.update(relative_path)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
    return digest.hexdigest()


def build_archive(root: Path) -> bytes:
    """Build a reproducible ZIP with all source files under timezones/."""
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in source_files(root):
            relative_path = path.relative_to(root).as_posix()
            info = ZipInfo(
                f"timezones/{relative_path}", date_time=(1980, 1, 1, 0, 0, 0)
            )
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(
                info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9
            )
    return output.getvalue()


def _outputs(repository_root: Path) -> tuple[Path, Path, Path]:
    fixtures = repository_root / "tests/resources/timezones"
    return (
        fixtures,
        repository_root / "tests/resources/timezones.sha256",
        repository_root / "tests/resources/timezones.zip",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument(
        "--write", action="store_true", help="regenerate digest and ZIP"
    )
    operation.add_argument(
        "--check", action="store_true", help="check generated outputs"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        metavar="REPO_ROOT",
        help="repository root (defaults to the repository containing this script)",
    )
    args = parser.parse_args(argv)
    repository_root = args.root.resolve()
    fixtures, digest_path, archive_path = _outputs(repository_root)
    expected_digest = f"{digest_sources(fixtures)}\n".encode("ascii")
    expected_archive = build_archive(fixtures)

    if args.write:
        digest_path.write_bytes(expected_digest)
        archive_path.write_bytes(expected_archive)
        print(f"Updated {digest_path} and {archive_path}")
        return 0

    stale = [
        path
        for path, expected in (
            (digest_path, expected_digest),
            (archive_path, expected_archive),
        )
        if not path.is_file() or path.read_bytes() != expected
    ]
    if stale:
        print(
            "Timezone fixture outputs are stale: "
            + ", ".join(path.relative_to(repository_root).as_posix() for path in stale)
            + ". Regenerate them with: python scripts/timezone_fixtures.py --write",
            file=sys.stderr,
        )
        return 1
    print("Timezone fixture digest and ZIP are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
