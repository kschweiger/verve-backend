import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from verve_backend.core.elevation import (
    ElevationConversionError,
    ElevationConverter,
    grid_path,
)


@pytest.fixture
def converter() -> ElevationConverter:
    if not grid_path().is_file():
        pytest.skip(
            "Install the EGM2008 grid with: "
            "python -m verve_backend.cli.download_elevation_grid"
        )
    return ElevationConverter()


@pytest.mark.parametrize(
    ("longitude", "latitude", "undulation"),
    [
        (0, 0, 17.22508430480957),
        (11.5, 48, 46.019107818603516),
        (-74, 40, -33.96613693237305),
    ],
)
def test_egm2008_conversion_matches_published_grid_nodes(
    converter: ElevationConverter,
    longitude: float,
    latitude: float,
    undulation: float,
) -> None:
    # Independently read physical grid node values from the NGA/PROJ GeoTIFF,
    # rather than deriving expected values through the conversion code.
    assert converter.to_ellipsoidal(longitude, latitude, 0) == pytest.approx(
        undulation, abs=1e-7
    )
    assert converter.to_sea_level(longitude, latitude, undulation) == pytest.approx(
        0, abs=1e-7
    )


@pytest.mark.parametrize("height", [-100.0, 0.0, 520.0])
def test_egm2008_height_round_trip_preserves_sea_level(
    converter: ElevationConverter, height: float
) -> None:
    ellipsoidal = converter.to_ellipsoidal(11.582, 48.135, height)
    assert abs(ellipsoidal - height) > 10
    assert converter.to_sea_level(11.582, 48.135, ellipsoidal) == pytest.approx(
        height, abs=1e-8
    )


def test_missing_grid_cannot_silently_leave_heights_unchanged(tmp_path: Path) -> None:
    with pytest.raises(ElevationConversionError, match="grid"):
        ElevationConverter(tmp_path / "missing.tif")


@pytest.mark.parametrize(
    ("longitude", "latitude"), [(0, 91), (181, 0), (0, float("nan"))]
)
def test_invalid_coordinates_fail_conversion(
    converter: ElevationConverter, longitude: float, latitude: float
) -> None:
    with pytest.raises(ElevationConversionError):
        converter.to_ellipsoidal(longitude, latitude, 0)


def test_corrupt_grid_fails_checksum_validation(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.tif"
    path.write_bytes(b"not a geoid grid")
    with pytest.raises(ElevationConversionError, match="checksum"):
        ElevationConverter(path)


def test_grid_downloader_installs_verified_data(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from verve_backend.cli import download_elevation_grid

    content = b"verified test grid"
    destination = tmp_path / "grids" / "egm2008.tif"
    mocker.patch.dict("os.environ", {"VERVE_EGM2008_GRID": str(destination)})
    mocker.patch.object(
        download_elevation_grid, "urlopen", return_value=BytesIO(content)
    )
    mocker.patch.object(
        download_elevation_grid, "GRID_SHA256", hashlib.sha256(content).hexdigest()
    )
    download_elevation_grid.main()
    assert destination.read_bytes() == content
    assert list(destination.parent.iterdir()) == [destination]


def test_grid_downloader_keeps_existing_grid_when_checksum_fails(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from verve_backend.cli import download_elevation_grid

    destination = tmp_path / "egm2008.tif"
    destination.write_bytes(b"existing verified grid")
    mocker.patch.dict("os.environ", {"VERVE_EGM2008_GRID": str(destination)})
    mocker.patch.object(
        download_elevation_grid, "urlopen", return_value=BytesIO(b"corrupt download")
    )
    with pytest.raises(ValueError, match="checksum"):
        download_elevation_grid.main()
    assert destination.read_bytes() == b"existing verified grid"
    assert list(tmp_path.iterdir()) == [destination]
