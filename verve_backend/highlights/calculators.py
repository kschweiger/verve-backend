from datetime import timedelta
from typing import Callable
from uuid import UUID

from sqlmodel import Session, select

from verve_backend.highlights.registry import registry
from verve_backend.models import Activity, HighlightMetric


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
        return value  # type: ignore[return-value]

    return calculator


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
