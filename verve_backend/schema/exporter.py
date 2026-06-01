from collections.abc import Callable
from typing import Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlmodel import Session, func, select

from verve_backend.core.meta_data import SwimmingMetaData
from verve_backend.models import (
    Activity,
    ActivitySubType,
    ActivityType,
    TrackPoint,
)
from verve_backend.schema.meta_data import (
    KnownMetaDataEnvelope,
    SwimLapDataV1,
    SwimmingMetaDataEnvelopeV1,
    SwimmingMetaDataV1,
    SwimSetDataV1,
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

MetaDataExport = KnownMetaDataEnvelope | dict[str, Any]
MetaDataExporter = Callable[[dict], MetaDataExport]


def _swimming_metadata_for_verve_export(meta_data: dict) -> SwimmingMetaDataEnvelopeV1:
    core_meta_data = SwimmingMetaData.model_validate(meta_data)
    return SwimmingMetaDataEnvelopeV1(
        data=SwimmingMetaDataV1(
            pool_length_meters=core_meta_data.pool_length_meters,
            total_stroke_count=core_meta_data.total_stroke_count,
            average_swolf=core_meta_data.avg_swofl,
            lap_count=core_meta_data.lap_count,
            set_count=core_meta_data.set_count,
            stroke_styles=core_meta_data.styles,
            laps=[
                SwimLapDataV1(
                    index=lap.index,
                    start_time=lap.start_time,
                    end_time=lap.end_time,
                    duration_seconds=None
                    if lap.durations is None
                    else lap.durations.total_seconds(),
                    distance_meters=lap.distance_meters,
                    stroke_style=lap.style,
                    stroke_count=lap.stroke_count,
                    swolf=lap.swolf,
                    rest_after_seconds=None
                    if lap.rest_after is None
                    else lap.rest_after.total_seconds(),
                )
                for lap in core_meta_data.laps or []
            ]
            or None,
            sets=[
                SwimSetDataV1(
                    index=set_data.index,
                    start_time=set_data.start_time,
                    end_time=set_data.end_time,
                    duration_seconds=None
                    if set_data.durations is None
                    else set_data.durations.total_seconds(),
                    lap_start_index=set_data.lap_start_index,
                    lap_end_index=set_data.lap_end_index,
                    lap_count=set_data.lap_count,
                    distance_meters=set_data.distance_meters,
                    stroke_style=set_data.style,
                    stroke_count=set_data.stroke_count,
                    average_swolf=set_data.avg_swofl,
                    rest_after_seconds=None
                    if set_data.rest_after is None
                    else set_data.rest_after.total_seconds(),
                )
                for set_data in core_meta_data.sets or []
            ]
            or None,
        )
    )


METADATA_EXPORTERS: dict[str, MetaDataExporter] = {
    "SwimmingMetaData": _swimming_metadata_for_verve_export,
}


def _metadata_for_verve_export(meta_data: dict) -> MetaDataExport:
    target = meta_data.get("target")
    if not isinstance(target, str):
        return meta_data

    exporter = METADATA_EXPORTERS.get(target)
    if exporter is None:
        return meta_data

    return exporter(meta_data)


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
        distance=None if activity.distance is None else activity.distance * 1000,
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
        metadata=_metadata_for_verve_export(activity.meta_data),
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
