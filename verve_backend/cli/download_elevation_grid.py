"""Install the pinned grid for local development; never runs during a request."""

import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from verve_backend.core.elevation import GRID_SHA256, GRID_URL, grid_path


def main() -> None:
    destination = grid_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            with urlopen(GRID_URL, timeout=60) as source:
                while block := source.read(1024 * 1024):
                    output.write(block)
        with temporary.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != GRID_SHA256:
                raise ValueError("Downloaded EGM2008 grid checksum mismatch")
        temporary.chmod(0o644)
        temporary.replace(destination)
        print(f"Installed pinned EGM2008 grid: {destination}")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
