import uuid
from datetime import timedelta
from typing import Generator

from geo_track_analyzer import Track
from geo_track_analyzer.exceptions import GPXPointExtensionError
from geo_track_analyzer.processing import get_extension_value
from pyproj import Transformer
from sqlmodel import Session, insert, select

from verve_backend.api.common.locale import get_activity_name
from verve_backend.api.deps import SupportedLocale
from verve_backend.core.config import settings
from verve_backend.core.security import get_password_hash, verify_password
from verve_backend.enums import GoalAggregation, GoalType
from verve_backend.exceptions import InvalidCombinationError
from verve_backend.models import (
    Activity,
    ActivityCreate,
    ActivityType,
    ActivityTypeCreate,
    Goal,
    GoalCreate,
    TrackPoint,
    User,
    UserCreate,
    UserPublic,
    UserSettings,
)


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    defaults = settings.DEFAULTSETTINGS

    settings_obj = UserSettings(
        user_id=db_obj.id,
        default_type_id=defaults.activity_type,
        defautl_sub_type_id=defaults.activity_sub_type,
    )
    session.add(settings_obj)
    session.commit()
    return db_obj


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        return None
    if not verify_password(password, db_user.hashed_password):
        return None
    return db_user


def create_activity(
    *,
    session: Session,
    create: ActivityCreate,
    user: UserPublic,
    locale: SupportedLocale = SupportedLocale.DE,
) -> Activity:
    name = create.name
    if name is None:
        activity_type = session.get(ActivityType, create.type_id)
        assert activity_type is not None
        name = get_activity_name(
            activity_type.name.lower().replace(" ", "_"),
            create.start,
            locale,
        )
    db_obj = Activity.model_validate(create, update={"user_id": user.id, "name": name})
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    return db_obj


def create_activity_type(
    *, session: Session, create: ActivityTypeCreate
) -> ActivityType:
    db_obj = ActivityType.model_validate(create)
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def get_points(
    track: Track,
    activity_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    batch_size: int = 100,
    utm_srid: int = 32632,  # Default to UTM Zone 32N (Germany), adjust as needed
) -> Generator[list[TrackPoint], None, None]:
    """
    Generate track points with UTM geometry coordinates.

    Args:
        track: GPX track object
        activity_id: Activity UUID
        user_id: User UUID
        batch_size: Batch size for yielding points
        utm_srid: UTM SRID to transform coordinates to (e.g., 32632 for UTM Zone 32N)
    """
    extension_fields = [
        k
        for k, value in TrackPoint.model_fields.items()
        if "is_extension" in value.metadata
    ]

    avail_track_ext = track.extensions
    current_batch = []
    # Create transformer for WGS84 to UTM conversion
    # EPSG:4326 is WGS84 (lat/lon), utm_srid is your target UTM zone
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_srid}", always_xy=True)

    for i, segment in enumerate(track.track.segments):
        for point in segment.points:
            utm_x, utm_y = transformer.transform(point.longitude, point.latitude)
            point_model_data = {
                "activity_id": activity_id,
                "user_id": user_id,
                "segment_id": i,
                "geography": f"POINT({point.longitude} {point.latitude})",
                "geometry": f"SRID={utm_srid};POINT({utm_x} {utm_y})",  # UTM coordinates with SRID
                "elevation": point.elevation,
                "time": point.time,
                "extensions": {},
            }
            for extension in avail_track_ext:
                try:
                    value = float(get_extension_value(point, extension))
                except GPXPointExtensionError:
                    value = None
                if extension in extension_fields:
                    point_model_data[extension] = value
                else:
                    point_model_data["extensions"][extension] = value

            _point = TrackPoint.model_validate(point_model_data)
            current_batch.append(_point)
            if len(current_batch) >= batch_size:
                yield current_batch
                current_batch = []
    # Yield any remaining data points in the final batch
    if current_batch:
        yield current_batch


def get_utm_srid_for_track(track: Track) -> int:
    """
    Automatically determine the best UTM SRID for a track based on its center point.
    """
    # Collect all lat/lon points to find the center
    lats, lons = [], []
    for segment in track.track.segments:
        for point in segment.points:
            lats.append(point.latitude)
            lons.append(point.longitude)

    if not lats:
        return 32632  # Default fallback

    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    # Calculate UTM zone
    utm_zone = int((center_lon + 180) // 6) + 1

    # Return appropriate SRID
    if center_lat >= 0:
        return 32600 + utm_zone  # Northern Hemisphere
    else:
        return 32700 + utm_zone  # Southern Hemisphere


def get_points_auto_utm(
    track: Track,
    activity_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    batch_size: int = 100,
) -> Generator[list[TrackPoint], None, None]:
    """
    Generate track points with automatically determined UTM coordinates.
    """
    # Auto-detect the best UTM SRID for this track
    utm_srid = get_utm_srid_for_track(track)

    # Use the main function with the detected SRID
    yield from get_points(track, activity_id, user_id, batch_size, utm_srid)


def insert_track(
    *,
    session: Session,
    track: Track,
    activity_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    batch_size: int = 100,
    utm_srid: int | None = None,
) -> int:
    n_points = 0
    if utm_srid is None:
        batches = get_points_auto_utm(
            track, activity_id, user_id, batch_size=batch_size
        )
    else:
        batches = get_points(
            track, activity_id, user_id, batch_size=batch_size, utm_srid=utm_srid
        )
    for batch in batches:
        session.exec(insert(TrackPoint), params=batch)  # type: ignore
        session.commit()
        n_points += len(batch)

    return n_points


def update_activity_with_track_data(
    *,
    session: Session,
    track: Track,
    activity_id: uuid.UUID | str,
):
    activity = session.get(Activity, activity_id)
    assert activity is not None, (
        "Function expects that activity is valid (exists and belongs to user)"
    )

    overview = track.get_track_overview()
    first_point_time = track.track.segments[0].points[0].time
    if first_point_time:
        activity.start = first_point_time
    activity.distance = overview.total_distance_km
    activity.duration = timedelta(days=0, seconds=overview.total_time_seconds)
    activity.elevation_change_up = overview.uphill_elevation
    activity.elevation_change_down = overview.downhill_elevation
    activity.moving_duration = timedelta(days=0, seconds=overview.moving_time_seconds)
    activity.avg_speed = overview.avg_velocity_kmh
    activity.max_speed = overview.max_velocity_kmh
    session.add(activity)
    session.commit()
    session.refresh(activity)


def create_goal(
    *, session: Session, goal: GoalCreate, user_id: uuid.UUID | str
) -> Goal:
    # Validate GoalType / GoalAggregation combination
    match goal.type:
        case GoalType.LOCATION:
            if goal.aggregation != GoalAggregation.COUNT:
                raise InvalidCombinationError(
                    "Location goal only support count aggregation"
                )
        case GoalType.MANUAL:
            if goal.aggregation not in [
                GoalAggregation.COUNT,
                GoalAggregation.DURATION,
            ]:
                raise InvalidCombinationError(
                    "Manual goal only support count and duration aggregation"
                )
        case GoalType.ACTIVITY:
            pass
        case _:
            raise NotImplementedError(f"{goal.type} is not supported")

    db_obj = Goal.model_validate(goal, update={"user_id": user_id})
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj
