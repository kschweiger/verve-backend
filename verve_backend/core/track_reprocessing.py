import json
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from uuid import UUID

from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client
from sqlmodel import Session, col, delete, select, update

from verve_backend import crud
from verve_backend.api.common.track import parse_track
from verve_backend.api.common.utils import get_user_timezone, update_activity_with_track
from verve_backend.core.config import settings
from verve_backend.enums import GoalType
from verve_backend.exceptions import StoredTrackFileUnavailableError
from verve_backend.models import (
    Activity,
    Goal,
    RawTrackData,
    SegmentCut,
    SegmentSet,
    TrackPoint,
)
from verve_backend.schema.importer import sniff_verve_format

RAW_SEGMENTS_NAME = "Raw track segments"


def reprocess_activity_track(
    *,
    session: Session,
    object_store_client: S3Client,
    activity_id: UUID,
    user_id: UUID,
) -> tuple[int, int]:
    """Replace a stored track inside the caller's transaction, without committing."""
    activity = session.exec(
        select(Activity).where(Activity.id == activity_id).with_for_update()
    ).first()
    raw = session.get(RawTrackData, activity_id)
    if activity is None or raw is None:
        raise ValueError("Activity or stored source track not found")
    if activity.user_id != user_id or raw.user_id != user_id:
        raise ValueError("Activity and stored source must belong to the requested user")

    try:
        source = object_store_client.get_object(
            Bucket=settings.BOTO3_BUCKET, Key=raw.store_path
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "NoSuchKey",
            "NoSuchBucket",
            "NotFound",
            "404",
        }:
            raise StoredTrackFileUnavailableError(
                bucket=settings.BOTO3_BUCKET, key=raw.store_path
            ) from exc
        raise
    with closing(source["Body"]) as body:
        content = body.read()
    metadata = source.get("Metadata", {})
    file_type = (
        metadata.get("file_type")
        or metadata.get("original_filename", "").rsplit(".", 1)[-1]
    )
    file_type = file_type.lower().lstrip(".")
    if file_type not in {"fit", "gpx", "json"}:
        raise ValueError("Stored source metadata has no supported file type")
    verve_timezone = None
    if file_type == "json":
        data = json.loads(content)
        if sniff_verve_format(data):
            verve_timezone = data["properties"].get("timezone")
    parsed = parse_track(
        file_name=f"track.{file_type}",
        file_content=content,
        fallback_timezone=get_user_timezone(session, user_id),
        verve_timezone=verve_timezone,
    )
    track = parsed.track
    track.track.segments = [
        segment for segment in track.track.segments if segment.points
    ]
    if not track.track.segments:
        raise ValueError("Stored source contains no track points")

    new_times = [
        point.time for segment in track.track.segments for point in segment.points
    ]
    ids_by_time: dict[datetime, list[int]] = defaultdict(list)
    for point_id, point_time in enumerate(new_times):
        if point_time is not None:
            ids_by_time[point_time].append(point_id)

    raw_cut_ids = set()
    segment_end = -1
    for segment in track.track.segments[:-1]:
        segment_end += len(segment.points)
        raw_cut_ids.add(segment_end)

    segment_sets = session.exec(
        select(SegmentSet).where(
            SegmentSet.activity_id == activity_id, SegmentSet.user_id == user_id
        )
    ).all()
    removed_cuts = 0
    has_raw_set = False
    for segment_set in segment_sets:
        cuts = session.exec(
            select(SegmentCut).where(
                SegmentCut.set_id == segment_set.id, SegmentCut.user_id == user_id
            )
        ).all()
        old_times = dict(
            session.exec(
                select(TrackPoint.id, TrackPoint.time).where(
                    TrackPoint.activity_id == activity_id,
                    TrackPoint.user_id == user_id,
                    col(TrackPoint.id).in_([cut.point_id for cut in cuts]),
                )
            ).all()
        )
        resolved_ids = set()
        for cut in cuts:
            old_time = old_times.get(cut.point_id)
            if old_time is None:
                removed_cuts += 1
                continue
            if (
                0 <= cut.point_id < len(new_times)
                and new_times[cut.point_id] == old_time
            ):
                resolved_id = cut.point_id
            else:
                matches = ids_by_time.get(old_time, [])
                if len(matches) != 1:
                    removed_cuts += 1
                    continue
                resolved_id = matches[0]
            if resolved_id in resolved_ids:
                removed_cuts += 1
            resolved_ids.add(resolved_id)
        # Delete first so remapped cuts cannot conflict with old point IDs.
        session.exec(delete(SegmentCut).where(col(SegmentCut.set_id) == segment_set.id))
        if resolved_ids:
            # Names are editable: preserve every resolvable set, and reuse a raw
            # set only when its cuts already match the current source boundaries.
            if segment_set.name == RAW_SEGMENTS_NAME and resolved_ids == raw_cut_ids:
                has_raw_set = True
            session.add_all(
                SegmentCut(user_id=user_id, set_id=segment_set.id, point_id=point_id)
                for point_id in sorted(resolved_ids)
            )
        else:
            session.delete(segment_set)

    session.exec(
        delete(TrackPoint).where(
            col(TrackPoint.activity_id) == activity_id,
            col(TrackPoint.user_id) == user_id,
        )
    )
    number_of_points = 0
    for batch in crud.get_points_auto_utm(
        track, activity_id, user_id, no_geometry=parsed.no_geometry
    ):
        session.add_all(batch)
        session.flush()
        number_of_points += len(batch)

    if raw_cut_ids and not has_raw_set:
        raw_set = SegmentSet(
            user_id=user_id, activity_id=activity_id, name=RAW_SEGMENTS_NAME
        )
        session.add(raw_set)
        session.flush()
        for point_id in sorted(raw_cut_ids):
            session.add(
                SegmentCut(user_id=user_id, set_id=raw_set.id, point_id=point_id)
            )

    activity.timezone = parsed.timezone.key
    activity.avg_speed = activity.max_speed = None
    activity.avg_power = activity.max_power = None
    activity.avg_heartrate = activity.max_heartrate = None
    update_activity_with_track(activity, track)
    session.add(activity)
    session.exec(
        update(Goal)
        .where(
            col(Goal.user_id) == user_id,
            col(Goal.type) != GoalType.MANUAL,
        )
        .values(current=0, current_updated=None)
    )
    return number_of_points, removed_cuts
