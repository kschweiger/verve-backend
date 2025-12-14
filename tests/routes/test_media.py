import io
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage
from sqlmodel import Session

from verve_backend.models import Activity, Image


@pytest.fixture
def activity_fixture(
    db: Session,
    temp_user_id: UUID,
) -> Activity:
    """Create a test activity for image uploads."""
    activity = Activity(
        start=datetime.now(),
        duration=timedelta(minutes=30),
        distance=10.0,
        type_id=1,
        sub_type_id=1,
        name="Test Activity for Images",
        user_id=temp_user_id,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    return activity


@pytest.fixture
def image_file_fixture() -> tuple[io.BytesIO, str]:
    img = PILImage.new("RGB", (1, 1), color="white")

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    return buf, "test_image.jpg"


def test_add_image(
    client: TestClient,
    temp_user_token: str,
    activity_fixture: Activity,
    image_file_fixture: tuple[io.BytesIO, str],
) -> None:
    file_data, filename = image_file_fixture

    response = client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (filename, file_data, "image/jpeg")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Image uploaded successfully"
    assert data["activity_id"] == str(activity_fixture.id)
    assert "id" in data


def test_add_image_png(
    client: TestClient,
    temp_user_token: str,
    activity_fixture: Activity,
) -> None:
    # Minimal PNG file (1x1 pixel)
    png_data = bytes.fromhex(
        "89504E470D0A1A0A0000000D494844520000000100000001080200000090"
        "77530E0000000C49444154089963000000020001E221BC330000000049454E44AE426082"
    )

    response = client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": ("test.png", io.BytesIO(png_data), "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Image uploaded successfully"


def test_add_image_activity_not_found(
    client: TestClient,
    temp_user_token: str,
    image_file_fixture: tuple[io.BytesIO, str],
) -> None:
    file_data, filename = image_file_fixture
    fake_activity_id = "00000000-0000-0000-0000-000000000000"

    response = client.put(
        f"/media/image/activity/{fake_activity_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (filename, file_data, "image/jpeg")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"


def test_add_image_unsupported_format(
    client: TestClient,
    temp_user_token: str,
    activity_fixture: Activity,
) -> None:
    # Create a fake PDF file
    pdf_data = b"%PDF-1.4\n%EOF"

    response = client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": ("test.pdf", io.BytesIO(pdf_data), "application/pdf")},
    )

    assert response.status_code == 415
    assert "Only .jpg, .jpeg and .png files are supported" in response.json()["detail"]


def test_get_image(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    temp_user_id: UUID,
    activity_fixture: Activity,
    image_file_fixture: tuple[io.BytesIO, str],
) -> None:
    # First upload an image
    file_data, filename = image_file_fixture
    upload_response = client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (filename, file_data, "image/jpeg")},
    )
    image_id = upload_response.json()["id"]

    # Now get the image
    response = client.get(
        f"/media/image/{image_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == image_id
    assert "url" in data
    assert isinstance(data["url"], str)


def test_get_image_not_found(
    client: TestClient,
    temp_user_token: str,
) -> None:
    fake_image_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(
        f"/media/image/{fake_image_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"


def test_delete_image(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    activity_fixture: Activity,
    image_file_fixture: tuple[io.BytesIO, str],
) -> None:
    # First upload an image
    file_data, filename = image_file_fixture
    upload_response = client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (filename, file_data, "image/jpeg")},
    )
    image_id = upload_response.json()["id"]

    # Now delete the image
    response = client.delete(
        f"/media/image/{image_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 204

    # Verify image is deleted from DB
    image = db.get(Image, image_id)
    assert image is None


def test_delete_image_not_found(
    client: TestClient,
    temp_user_token: str,
) -> None:
    fake_image_id = "00000000-0000-0000-0000-000000000000"

    response = client.delete(
        f"/media/image/{fake_image_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"


def test_get_activity_images(
    client: TestClient,
    temp_user_token: str,
    activity_fixture: Activity,
    image_file_fixture: tuple[io.BytesIO, str],
) -> None:
    # Upload multiple images
    file_data1, filename = image_file_fixture
    client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": (filename, file_data1, "image/jpeg")},
    )

    # Upload second image (need to reset BytesIO)
    file_data2, _ = image_file_fixture
    client.put(
        f"/media/image/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
        files={"file": ("test2.jpg", file_data2, "image/jpeg")},
    )

    # Get all images for activity
    response = client.get(
        f"/media/images/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) == 2

    for image in data["data"]:
        assert "id" in image
        assert "url" in image


def test_get_activity_images_empty(
    client: TestClient,
    temp_user_token: str,
    activity_fixture: Activity,
) -> None:
    response = client.get(
        f"/media/images/activity/{activity_fixture.id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []


def test_get_activity_images_activity_not_found(
    client: TestClient,
    temp_user_token: str,
) -> None:
    fake_activity_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(
        f"/media/images/activity/{fake_activity_id}",
        headers={"Authorization": f"Bearer {temp_user_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"
