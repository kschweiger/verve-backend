import importlib.resources
import logging
from datetime import timedelta
from typing import Callable
from uuid import UUID

from numpy import argmax
from sqlmodel import Session, select, text

from verve_backend.highlights.registry import registry
from verve_backend.models import Activity, HighlightMetric

logger = logging.getLogger("uvicorn.error")


def _get_value_from_acitivty_tabel(
    session: Session, activity_id: UUID, col
) -> timedelta | float | None:
    data = session.exec(select(col).where(Activity.id == activity_id)).all()
    if len(data) == 1:
        return data[0]

    return None


def _create_numeric_calculator(column) -> Callable[[UUID, Session], float | None]:
    """
    Factory function to create calculators that retrieve numeric values fromActivity
    table.
    """

    def calculator(activity_id: UUID, session: Session) -> float | None:
        value = _get_value_from_acitivty_tabel(session, activity_id, column)
        assert not isinstance(value, timedelta)
        return value

    return calculator


def _get_window_metric_from_track(
    session: Session,
    activity_id: UUID,
    user_id: UUID,
    metric: str,
    minutes: int,
    avg_over_windows: int,
):
    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath(f"track_{metric}_window.sql")
        .read_text()
    )
    data = session.exec(
        text(stmt),  # type: ignore
        params=dict(
            activity_id=activity_id,
            user_id=user_id,
            minutes=minutes,
            avg_over_windows=avg_over_windows,
        ),
    ).one()
    value, windows_times, window_ids, windows_values = data
    _i_max = argmax(windows_values)
    return int(round(value, 0)), windows_times[_i_max], window_ids[_i_max]


@registry.add(HighlightMetric.DURATION)
def calculate_duration(activity_id: UUID, session: Session) -> timedelta | float | None:
    value = _get_value_from_acitivty_tabel(
        session, activity_id, Activity.moving_duration
    )
    if value is None:
        value = _get_value_from_acitivty_tabel(session, activity_id, Activity.duration)
    return value


for metric, col in [
    (HighlightMetric.DISTANCE, Activity.distance),
    (HighlightMetric.ELEVATION_CHANGE_UP, Activity.elevation_change_up),
    (HighlightMetric.AVG_SPEED, Activity.avg_speed),
    (HighlightMetric.MAX_SPEED, Activity.max_speed),
    (HighlightMetric.AVG_POWER, Activity.avg_power),
    (HighlightMetric.MAX_POWER, Activity.max_power),
]:
    registry.add(metric)(_create_numeric_calculator(col))
