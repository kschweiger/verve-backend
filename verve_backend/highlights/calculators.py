import importlib.resources
import logging
from datetime import timedelta
from functools import partial
from typing import Callable
from uuid import UUID

from numpy import argmax
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select, text

from verve_backend.highlights.registry import CalculatorResult, registry
from verve_backend.models import Activity, HighlightMetric

logger = logging.getLogger(__name__)


def _get_value_from_acitivty_tabel(
    session: Session, activity_id: UUID, col
) -> timedelta | float | None:
    data = session.exec(select(col).where(Activity.id == activity_id)).all()
    if len(data) == 1:
        return data[0]

    return None


def _create_numeric_calculator(
    column,
) -> Callable[[UUID, UUID, Session], CalculatorResult | None]:
    """
    Factory function to create calculators that retrieve numeric values fromActivity
    table.
    """

    def calculator(
        activity_id: UUID, user_id: UUID, session: Session
    ) -> CalculatorResult | None:
        value = _get_value_from_acitivty_tabel(session, activity_id, column)
        assert not isinstance(value, timedelta)
        if value is None:
            return None
        return CalculatorResult(value=value)

    return calculator


@registry.add(HighlightMetric.DURATION)
def calculate_duration(
    activity_id: UUID, user_id: UUID, session: Session
) -> CalculatorResult | None:
    value = _get_value_from_acitivty_tabel(
        session, activity_id, Activity.moving_duration
    )
    if value is None:
        value = _get_value_from_acitivty_tabel(session, activity_id, Activity.duration)
    assert isinstance(value, timedelta)
    return CalculatorResult(value=value.total_seconds()) if value else None


for metric, col in [
    (HighlightMetric.DISTANCE, Activity.distance),
    (HighlightMetric.ELEVATION_CHANGE_UP, Activity.elevation_change_up),
    (HighlightMetric.AVG_SPEED, Activity.avg_speed),
    (HighlightMetric.MAX_SPEED, Activity.max_speed),
    (HighlightMetric.AVG_POWER, Activity.avg_power),
    (HighlightMetric.MAX_POWER, Activity.max_power),
]:
    registry.add(metric)(_create_numeric_calculator(col))


def _get_window_metric_from_track(
    activity_id: UUID,
    user_id: UUID,
    session: Session,
    metric: str,
    minutes: int,
    avg_over_windows: int,
) -> CalculatorResult | None:
    stmt = (
        importlib.resources.files("verve_backend.queries")
        .joinpath(f"track_{metric}_window.sql")
        .read_text()
    )
    try:
        data = session.exec(
            text(stmt),  # type: ignore
            params=dict(
                activity_id=activity_id,
                user_id=user_id,
                minutes=minutes,
                avg_over_windows=avg_over_windows,
            ),
        ).one()
    except NoResultFound:
        return None
    value, _, window_ids, windows_values = data
    _i_max = argmax(windows_values)
    return CalculatorResult(value=int(round(value, 0)), track_id=window_ids[_i_max])


for hl_metric, metric, minutes, avg_over in [
    (HighlightMetric.AVG_POWER1MIN, "power", 1, 10),
    (HighlightMetric.AVG_POWER2MIN, "power", 2, 10),
    (HighlightMetric.AVG_POWER5MIN, "power", 5, 3),
    (HighlightMetric.AVG_POWER10MIN, "power", 10, 3),
    (HighlightMetric.AVG_POWER20MIN, "power", 20, 1),
    (HighlightMetric.AVG_POWER30MIN, "power", 30, 1),
    (HighlightMetric.AVG_POWER60MIN, "power", 60, 1),
]:
    registry.add(hl_metric)(
        partial(
            _get_window_metric_from_track,
            metric=metric,
            minutes=minutes,
            avg_over_windows=avg_over,
        )
    )
