import argparse
import tomllib
from enum import StrEnum
from pathlib import Path


class BumpMode(StrEnum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


def parse_mode(value) -> BumpMode:
    try:
        return BumpMode(value.lower())
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid version '{value}'. Choose from: major, minor, patch"
        )


def update_version(
    filename: Path, old_version: str, new_version: str, starts_with: str
) -> None:
    times_replaced = 0
    updated_lines = []
    with open(filename, "r", encoding="utf-8") as file:
        for line in file:
            if line.lstrip().startswith(starts_with):
                updated_lines.append(line.replace(old_version, new_version))
                times_replaced += 1
            else:
                updated_lines.append(line)
    assert times_replaced == 1, "Version needs to be replace exactly once"
    with open(filename, "w", encoding="utf-8") as file:
        file.writelines(updated_lines)


def update_version_file(filename: Path, old_version: str, new_version: str) -> None:
    with open(filename, "r", encoding="utf-8") as file:
        content = file.read().strip()

    if content != old_version:
        print(
            f"Warning: VERSION file contains '{content}' but expected '{old_version}'"
        )
        return

    with open(filename, "w", encoding="utf-8") as file:
        file.write(new_version + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI template with versioning and dry run support"
    )
    parser.add_argument("path", help="Input file or directory path")
    parser.add_argument(
        "mode",
        type=parse_mode,
        help="Bump mode: major, minor, or patch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no changes will be made)",
    )
    parser.add_argument(
        "--init",
        help="Replace the __version__ in the package init",
        action="store_true",
    )
    parser.add_argument(
        "--version-file",
        help="Replace version in the VERSION file",
        action="store_true",
    )
    parser.add_argument(
        "--package",
        help="Folder that contains the package",
        default=None,
    )
    args = parser.parse_args()

    print(args)

    if args.dry_run:
        print("Dry run mode enabled")

    if args.init and not args.package:
        print("If --init is passed, package must also be passed")
        exit(1)
    mode = args.mode
    pyproject = Path(f"{args.path}/pyproject.toml")
    if not pyproject.is_file():
        print(f"{pyproject} is no valid file")
        exit(1)

    init_file = None
    if args.init:
        init_file = Path(f"{args.path}/{args.package}/__init__.py")
        if not init_file.is_file():
            print(f"{init_file} does not exists")
            exit(1)

    version_file = None
    if args.version_file:
        version_file = Path(f"{args.path}/VERSION")
        if not version_file.is_file():
            print(f"{init_file} does not exists")
            exit(1)

    with open(pyproject, "rb") as f:
        pyproject_data = tomllib.load(f)

    version = pyproject_data["project"]["version"]
    version_parts = version.split(".")

    assert len(version_parts) == 3

    major_part = int(version_parts[0])
    minor_part = int(version_parts[1])
    patch_part = int(version_parts[2])

    if mode == BumpMode.MAJOR:
        new_version = f"{major_part + 1}.0.0"
    elif mode == BumpMode.MINOR:
        new_version = f"{major_part}.{minor_part + 1}.0"
    else:
        new_version = f"{major_part}.{minor_part}.{patch_part + 1}"

    print(f"New: {new_version}")
    if not args.dry_run:
        update_version(pyproject, version, new_version, "version")
        if init_file:
            update_version(init_file, version, new_version, "__version__")
        if version_file:
            update_version_file(version_file, version, new_version)


if __name__ == "__main__":
    main()
