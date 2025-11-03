from datetime import timedelta
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


@registry.add(HighlightMetric.DURATION)
def calculate_duration(activity_id: UUID, session: Session) -> timedelta | float | None:
    # TODO: here we probanly want to min of duration and duration_moving
    return _get_value_from_acitivty_tabel(session, activity_id, Activity.duration)
