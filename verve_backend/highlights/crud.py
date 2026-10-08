from uuid import UUID
from zoneinfo import ZoneInfo

from sqlmodel import Session, col, delete, select

from verve_backend.api.common.utils import get_user_timezone
from verve_backend.highlights.registry import registry
from verve_backend.models import (
    Activity,
    ActivityHighlight,
    HighlightMetric,
    HighlightTimeScope,
)


def update_top_n_highlights(
    session: Session,
    user_id: UUID,
    *,
    activity: Activity,
    timezone: ZoneInfo,
    metric: HighlightMetric,
    value: float | int,
    track_id: int | None = None,
    n: int = 3,
) -> None:
    """
    Updates the top N highlights for a given metric, handling both
    YEARLY and LIFETIME scopes.
    """
    for scope in [HighlightTimeScope.YEARLY, HighlightTimeScope.LIFETIME]:
        year = (
            activity.start.astimezone(timezone).year
            if scope == HighlightTimeScope.YEARLY
            else None
        )

        # 1. Get current highlights
        stmt = select(ActivityHighlight).where(
            ActivityHighlight.user_id == user_id,
            ActivityHighlight.metric == metric,
            ActivityHighlight.scope == scope,
            ActivityHighlight.year == year,
            ActivityHighlight.type_id == activity.type_id,
        )
        current_highlights = session.exec(stmt).all()

        # 2. Create candidate and determine the new top N
        candidate = ActivityHighlight(
            user_id=user_id,
            activity_id=activity.id,
            metric=metric,
            scope=scope,
            year=year,
            value=value,
            rank=-1,
            type_id=activity.type_id,
            track_id=track_id,
        )
        all_candidates = list(current_highlights) + [candidate]
        all_candidates.sort(key=lambda h: (h.value, h.activity_id), reverse=True)
        top_candidates = all_candidates[:n]

        # 3. If the new activity didn't make the cut, we're done for this scope.
        if not any(c.activity_id == activity.id for c in top_candidates):
            continue

        # 4. Delete all existing highlights for this specific scope
        del_stmt = delete(ActivityHighlight).where(
            ActivityHighlight.user_id == user_id,  # type: ignore
            ActivityHighlight.metric == metric,  # type: ignore
            ActivityHighlight.scope == scope,  # type: ignore
            ActivityHighlight.year == year,  # type: ignore
            ActivityHighlight.type_id == activity.type_id,  # type: ignore
        )
        session.exec(del_stmt)

        # 5. Insert the new top N as fresh objects.
        for i, high_score in enumerate(top_candidates):
            new_highlight = ActivityHighlight(
                user_id=high_score.user_id,
                activity_id=high_score.activity_id,
                type_id=high_score.type_id,
                metric=high_score.metric,
                scope=high_score.scope,
                year=high_score.year,
                value=high_score.value,
                track_id=high_score.track_id,
                rank=i + 1,
            )
            session.add(new_highlight)


def rebuild_user_highlights(*, session: Session, user_id: UUID) -> int:
    """Replace a user's rankings inside the caller's transaction without committing."""
    timezone = get_user_timezone(session, user_id)
    session.exec(
        delete(ActivityHighlight).where(col(ActivityHighlight.user_id) == user_id)
    )
    activities = session.exec(
        select(Activity).where(Activity.user_id == user_id).order_by(Activity.id)  # type: ignore
    ).all()
    for activity in activities:
        for metric, calculator in registry.calculators.items():
            result = calculator(activity.id, user_id, session)
            if result is not None:
                update_top_n_highlights(
                    session=session,
                    user_id=user_id,
                    activity=activity,
                    timezone=timezone,
                    metric=metric,
                    value=result.value,
                    track_id=result.track_id,
                )
    return len(activities)
