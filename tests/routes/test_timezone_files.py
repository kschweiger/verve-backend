import json
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from verve_backend.models import ActivityPublic, RawTrackData

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

FIXTURES = resources.files("tests.resources").joinpath("timezones")
CASES = json.loads(FIXTURES.joinpath("cases.json").read_text())["cases"]
pytestmark = pytest.mark.usefixtures("celery_eager")


def upload_case(
    client: TestClient,
    headers: dict[str, str],
    case: dict[str, Any],
    route: str,
    label: str | None = None,
) -> tuple[ActivityPublic, bytes]:
    response = client.get("/users/me/settings", headers=headers)
    assert response.status_code == 200
    assert response.json()["settings"]["timezone"] == case["user_timezone"]
    params = {}
    if case["timezone_name"] is not None:
        params["timezone_name"] = case["timezone_name"]
    is_gpx = case["file"].endswith(".gpx")
    if is_gpx:
        params.update(type_id=2, sub_type_id=7)
    content = FIXTURES.joinpath(case["file"]).read_bytes()
    response = client.post(
        route,
        headers=headers,
        params=params,
        files={
            "file": (
                case["file"],
                content,
                "application/gpx+xml" if is_gpx else "application/json",
            )
        },
    )
    assert response.status_code == 200
    activity = ActivityPublic.model_validate(response.json())
    named = client.patch(
        f"/activity/{activity.id}",
        headers=headers,
        json={"name": f"Timezone: {label or case['id']} [{route}]"},
    )
    assert named.status_code == 200
    return activity, content


def read_points(
    client: TestClient,
    headers: dict[str, str],
    activity_id: UUID,
) -> list[dict[str, Any]]:
    response = client.get(f"/track/{activity_id}", headers=headers)
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.parametrize(
    ("case", "route"),
    [
        pytest.param(
            case, route, id=f"{case['id']}-{route.strip('/').replace('/', '-')}"
        )
        for case in CASES
        for route in case["routes"]
    ],
)
def test_timezone_file_upload_persists_instants_and_heart_rates(
    client: TestClient,
    db: Session,
    timezone_user_tokens: dict[str, str],
    object_store: "S3Client",
    case: dict[str, Any],
    route: str,
) -> None:
    from verve_backend.core.config import settings

    token = timezone_user_tokens[case["user_timezone"]]
    headers = {"Authorization": f"Bearer {token}"}
    activity, content = upload_case(client, headers, case, route)
    expected = case["expected"]
    expected_start = datetime.fromisoformat(expected["start"])
    assert activity.timezone == expected["timezone"]
    assert activity.start == expected_start
    assert activity.duration == timedelta(seconds=expected["duration_seconds"])
    assert (
        activity.start.astimezone(ZoneInfo(activity.timezone))
        .replace(
            tzinfo=None,
        )
        .isoformat()
        == expected["local_start"]
    )

    detail = client.get(f"/activity/{activity.id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["timezone"] == expected["timezone"]
    listed = client.get("/activity/", headers=headers)
    assert listed.status_code == 200
    assert (
        next(a for a in listed.json()["data"] if a["id"] == str(activity.id))[
            "timezone"
        ]
        == expected["timezone"]
    )

    points = read_points(client, headers, activity.id)
    times = [datetime.fromisoformat(point["time"]) for point in points]
    assert times == [datetime.fromisoformat(time) for time in expected["point_times"]]
    assert [point["heartrate"] for point in points] == expected["heart_rates"]
    assert [(time - expected_start).total_seconds() for time in times] == expected[
        "elapsed_seconds"
    ]

    raw = db.get(RawTrackData, activity.id)
    assert raw is not None
    stored = object_store.get_object(Bucket=settings.BOTO3_BUCKET, Key=raw.store_path)
    with stored["Body"] as body:
        assert body.read() == content


def test_timezone_file_export_import_preserves_times_zone_and_heart_rates(
    client: TestClient,
    db: Session,
    timezone_user_tokens: dict[str, str],
) -> None:
    from verve_backend.schema.exporter import _cast

    case = next(case for case in CASES if case["id"] == "verve-declared-zone")
    token = timezone_user_tokens[case["user_timezone"]]
    headers = {"Authorization": f"Bearer {token}"}
    activity, _ = upload_case(
        client,
        headers,
        case,
        "/activity/import/",
        label="roundtrip-source",
    )
    before = read_points(client, headers, activity.id)
    exported = _cast(db, activity.id).to_json().encode()
    response = client.post(
        "/activity/import/",
        headers=headers,
        files={"file": ("roundtrip.json", exported, "application/json")},
    )
    assert response.status_code == 200
    imported = ActivityPublic.model_validate(response.json())
    assert imported.timezone == activity.timezone
    assert imported.start == activity.start
    assert imported.duration == activity.duration
    after = read_points(client, headers, imported.id)
    assert [(point["time"], point["heartrate"]) for point in after] == [
        (point["time"], point["heartrate"]) for point in before
    ]


def test_correcting_timezone_keeps_file_instants_and_heart_rates(
    client: TestClient,
    timezone_user_tokens: dict[str, str],
) -> None:
    case = next(case for case in CASES if case["id"] == "travelling-los-angeles")
    token = timezone_user_tokens[case["user_timezone"]]
    headers = {"Authorization": f"Bearer {token}"}
    activity, _ = upload_case(
        client,
        headers,
        case,
        "/activity/auto/",
        label="corrected-zone",
    )
    before = read_points(client, headers, activity.id)
    response = client.patch(
        f"/activity/{activity.id}",
        headers=headers,
        json={"timezone": "Europe/Berlin"},
    )
    assert response.status_code == 200
    corrected = ActivityPublic.model_validate(response.json())
    assert corrected.timezone == "Europe/Berlin"
    assert corrected.start == activity.start
    assert corrected.duration == activity.duration
    after = read_points(client, headers, activity.id)
    assert [(point["time"], point["heartrate"]) for point in after] == [
        (point["time"], point["heartrate"]) for point in before
    ]


@pytest.mark.parametrize("route", ["/activity/auto/", "/track/"])
def test_dst_upload_persists_elapsed_duration(
    client: TestClient,
    db: Session,
    temp_user_token: str,
    object_store: "S3Client",
    route: str,
) -> None:
    from verve_backend.core.config import settings

    content = (
        '<gpx version="1.1" creator="test"><trk><trkseg>'
        '<trkpt lat="52.52" lon="13.405"><time>2026-03-29T01:30:00</time></trkpt>'
        '<trkpt lat="52.53" lon="13.415"><time>2026-03-29T03:30:00</time></trkpt>'
        '<trkpt lat="52.54" lon="13.425"><time>2026-03-29T03:40:00</time></trkpt>'
        "</trkseg></trk></gpx>"
    ).encode()
    headers = {"Authorization": f"Bearer {temp_user_token}"}
    params = {"timezone_name": "Europe/Berlin"}
    files = {"file": ("spring.gpx", content, "application/gpx+xml")}
    if route == "/activity/auto/":
        response = client.post(
            route, headers=headers, params={**params, "type_id": 2}, files=files
        )
        assert response.status_code == 200
        activity_id = UUID(response.json()["id"])
    else:
        response = client.post(
            "/activity/",
            headers=headers,
            json={
                "start": "2026-03-29T00:00:00Z",
                "duration": "PT10M",
                "distance": 1.0,
                "type_id": 2,
                "sub_type_id": None,
                "name": "DST upload",
            },
        )
        assert response.status_code == 200
        activity_id = UUID(response.json()["id"])
        response = client.put(
            route,
            headers=headers,
            params={**params, "activity_id": str(activity_id)},
            files=files,
        )
        assert response.status_code == 201

    response = client.get(f"/activity/{activity_id}", headers=headers)
    assert response.status_code == 200
    activity = ActivityPublic.model_validate(response.json())
    assert activity.duration == timedelta(seconds=4200)
    assert activity.start == datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    assert activity.timezone == "Europe/Berlin"
    raw = db.get(RawTrackData, activity_id)
    assert raw is not None
    stored = object_store.get_object(Bucket=settings.BOTO3_BUCKET, Key=raw.store_path)
    with stored["Body"] as body:
        assert body.read() == content
