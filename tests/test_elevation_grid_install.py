import hashlib
import shutil
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from verve_backend.core.elevation import GRID_NAME, GRID_SHA256, grid_path


def test_grid_install_reuses_verified_cache(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from verve_backend.cli import install_elevation_grid

    cached = tmp_path / GRID_NAME
    shutil.copyfile(grid_path(), cached)
    destination = tmp_path / "runtime" / GRID_NAME
    mocker.patch.dict("os.environ", {"VERVE_EGM2008_GRID": str(cached)})
    download = mocker.spy(install_elevation_grid, "download_grid")

    install_elevation_grid.install(destination)

    with destination.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == GRID_SHA256
    assert destination.stat().st_mode & 0o777 == 0o644
    download.assert_not_called()


@pytest.mark.parametrize("corrupt", [False, True], ids=["missing", "corrupt"])
def test_grid_install_replaces_invalid_cache(
    tmp_path: Path, mocker: MockerFixture, corrupt: bool
) -> None:
    from verve_backend.cli import install_elevation_grid

    verified = grid_path()
    cached = tmp_path / GRID_NAME
    if corrupt:
        cached.write_bytes(b"invalid grid")
    destination = tmp_path / "runtime" / GRID_NAME
    mocker.patch.dict("os.environ", {"VERVE_EGM2008_GRID": str(cached)})
    # Replace only the network downloader; real checksums and PROJ still execute.
    mocker.patch.object(
        install_elevation_grid,
        "download_grid",
        side_effect=lambda: shutil.copyfile(verified, cached),
    )

    install_elevation_grid.install(destination)

    with destination.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == GRID_SHA256


def test_grid_install_preserves_destination_when_download_fails(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from verve_backend.cli import install_elevation_grid

    cached = tmp_path / GRID_NAME
    cached.write_bytes(b"invalid cache")
    destination = tmp_path / "runtime.tif"
    destination.write_bytes(b"previous installation")
    mocker.patch.dict("os.environ", {"VERVE_EGM2008_GRID": str(cached)})
    mocker.patch.object(
        install_elevation_grid, "download_grid", side_effect=OSError("offline")
    )

    with pytest.raises(OSError, match="offline"):
        install_elevation_grid.install(destination)

    assert destination.read_bytes() == b"previous installation"
