from uuid import UUID

from geoalchemy2 import Geometry
from sqlmodel import Session, func, select

from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
    TrackPoint,
)
from verve_backend.schema.verve_file import (
    ActivityStats,
    EquipmentExport,
    LineFeature,
    LineProperties,
    LineStringGeometry,
    MetricSummary,
    VerveFeature,
    VerveProperties,
)


def _cast(session: Session, activity_id: UUID) -> VerveFeature:
    activity = session.get(Activity, activity_id)
    assert activity is not None, "Activity not found"

    _type_name = session.get(ActivityType, activity.type_id)
    assert _type_name is not None
    _sub_type = None
    if activity.sub_type_id is not None:
        _sub_type = session.get(ActivitySubType, activity.sub_type_id)
        assert _type_name is not None

    props = VerveProperties(
        name=activity.name,
        activity_type=_type_name.name,
        activity_sub_type=_sub_type.name if _sub_type else None,
        start_time=activity.start,
        duration=activity.duration.total_seconds(),
        moving_duration=activity.moving_duration.total_seconds()
        if activity.moving_duration
        else None,
        distance=activity.distance,
        energy=activity.energy,
        elevation_gain=activity.elevation_change_up,
        elevation_loss=activity.elevation_change_down,
        stats=ActivityStats(
            speed=MetricSummary(avg=activity.avg_speed, max=activity.max_speed),
            heart_rate=MetricSummary(
                avg=activity.avg_heartrate, max=activity.max_heartrate
            ),
            power=MetricSummary(avg=activity.avg_power, max=activity.max_power),
        ),
        metadata=activity.meta_data,
        equipment=[
            EquipmentExport(
                name=e.name,
                type=str(e.equipment_type),
                brand=e.brand,
                model=e.model,
            )
            for e in activity.equipment
        ],
    )

    stmt = (
        select(TrackPoint.segment_id)
        .distinct()
        .where(TrackPoint.activity_id == activity_id)
    )
    segment_ids = session.exec(stmt).all()
    _features = []
    for _id in segment_ids:
        stmt = (
            select(
                TrackPoint,
                func.ST_Y(func.ST_AsText(TrackPoint.geography).cast(Geometry)).label(
                    "latitude"
                ),
                func.ST_X(func.ST_AsText(TrackPoint.geography).cast(Geometry)).label(
                    "longitude"
                ),
            )
            .where(TrackPoint.activity_id == activity_id)
            .where(TrackPoint.segment_id == _id)
        )
        _points = session.exec(stmt).all()
        _coordinates = []
        _times = []
        _heart_rates = []
        _cadences = []
        _powers = []
        for point, latitude, longitude in _points:
            _coordinates.append((longitude, latitude, point.elevation))

            _times.append(point.time)
            _heart_rates.append(point.heartrate)
            _cadences.append(point.cadence)
            _powers.append(point.power)

        _features.append(
            LineFeature(
                geometry=LineStringGeometry(coordinates=_coordinates),
                properties=LineProperties(
                    coord_times=_times,
                    heart_rates=_heart_rates if any(_heart_rates) else None,
                    cadences=_cadences if any(_cadences) else None,
                    powers=_powers if any(_powers) else None,
                ),
            )
        )
    return VerveFeature(properties=props, features=_features)
