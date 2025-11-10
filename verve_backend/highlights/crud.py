from uuid import UUID

from sqlmodel import Session, delete, select

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
    metric: HighlightMetric,
    value: float | int,
    n: int = 3,
):
    """
    Updates the top N highlights for a given metric, handling both
    YEARLY and LIFETIME scopes.
    """
    for scope in [HighlightTimeScope.YEARLY, HighlightTimeScope.LIFETIME]:
        year = activity.start.year if scope == HighlightTimeScope.YEARLY else None

        # 1. Get current highlights (still needed to determine the new ranking)
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
        )
        all_candidates = list(current_highlights) + [candidate]
        all_candidates.sort(key=lambda h: (h.value, h.activity_id), reverse=True)
        top_candidates = all_candidates[:n]

        # 3. If the new activity didn't make the cut, we're done for this scope.
        if not any(c.activity_id == activity.id for c in top_candidates):
            continue

        # 4. Delete all existing highlights for this specific scope in one command.
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
