from datetime import datetime, timedelta
from uuid import UUID

from geo_track_analyzer import PyTrack, Track
from sqlmodel import Session, select

from verve_backend.api.common.track import update_activity_with_track
from verve_backend.crud import insert_track
from verve_backend.highlights.crud import update_top_n_highlights
from verve_backend.highlights.registry import registry
from verve_backend.models import (
    Activity,
    ActivityHighlight,
    HighlightMetric,
    HighlightTimeScope,
    User,
)
from verve_backend.tasks import process_activity_highlights


# Helper function to create dummy activities for tests
def create_dummy_activity(
    session: Session,
    user_id: UUID,
    start: datetime,
    distance: float,
    type_id: int = 1,
    track: Track | None = None,
    name: str | None = None,
) -> Activity:
    """Creates a simple activity, saves it to the DB, and returns it."""
    activity = Activity(
        user_id=user_id,
        start=start,
        distance=distance,
        duration=timedelta(minutes=60),
        type_id=type_id,
        sub_type_id=None,
        name=f"Test Activity {distance}km" if name is None else name,
    )
    session.add(activity)
    session.commit()
    session.refresh(activity)

    if track:
        insert_track(
            session=session,
            track=track,
            activity_id=activity.id,
            user_id=user_id,
        )
        update_activity_with_track(activity=activity, track=track)

        overview = track.get_track_overview()
        activity.distance = overview.moving_distance_km
        session.add(activity)
        session.commit()
        session.refresh(activity)

    return activity


def test_update_highlights_first_entry(db: Session, temp_user_id: UUID) -> None:
    """
    Tests that the first activity processed correctly creates rank 1 highlights
    for both YEARLY and LIFETIME scopes.
    """
    # ARRANGE: Create a user and one activity
    user = db.get(User, temp_user_id)
    assert user is not None
    activity1 = create_dummy_activity(db, user.id, datetime(2024, 1, 1), 100.0)

    # ACT: Run the highlight update function
    update_top_n_highlights(
        session=db,
        user_id=user.id,
        activity=activity1,
        metric=HighlightMetric.DISTANCE,
        value=100.0,
    )
    db.commit()

    # ASSERT: Check that the highlights were created correctly
    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.user_id == user.id)
    ).all()
    assert len(highlights) == 2, (
        "Should create one highlight for YEARLY and one for LIFETIME"
    )

    yearly_hl = next(h for h in highlights if h.scope == HighlightTimeScope.YEARLY)
    assert yearly_hl.rank == 1
    assert yearly_hl.value == 100.0
    assert yearly_hl.activity_id == activity1.id
    assert yearly_hl.year == 2024

    lifetime_hl = next(h for h in highlights if h.scope == HighlightTimeScope.LIFETIME)
    assert lifetime_hl.rank == 1
    assert lifetime_hl.value == 100.0
    assert lifetime_hl.activity_id == activity1.id
    assert lifetime_hl.year is None


def test_update_highlights_ranking_logic(db: Session, temp_user_id: UUID) -> None:
    """
    Tests that the top 3 ranking is correctly maintained when multiple
    activities are processed.
    """
    # ARRANGE: Create a user and 4 activities with distances out of order
    user = db.get(User, temp_user_id)
    assert user is not None

    act1 = create_dummy_activity(db, user.id, datetime(2024, 1, 1), 50.0)  # 3rd place
    act2 = create_dummy_activity(db, user.id, datetime(2024, 1, 2), 200.0)  # 1st place
    act3 = create_dummy_activity(
        db, user.id, datetime(2024, 1, 3), 20.0
    )  # Should not rank
    act4 = create_dummy_activity(db, user.id, datetime(2024, 1, 4), 100.0)  # 2nd place

    # ACT: Process all activities
    for act in [act1, act2, act3, act4]:
        print(act)
        update_top_n_highlights(
            session=db,
            user_id=user.id,
            activity=act,
            metric=HighlightMetric.DISTANCE,
            value=act.distance,
        )
        db.commit()

    # ASSERT: Check the final state of the LIFETIME highlights
    stmt = (
        select(ActivityHighlight)
        .where(ActivityHighlight.scope == HighlightTimeScope.LIFETIME)
        .where(ActivityHighlight.user_id == user.id)
        .order_by(ActivityHighlight.rank)
    )
    highlights = db.exec(stmt).all()

    assert len(highlights) == 3, "Should only store the top 3 highlights"

    # Check Rank 1
    assert highlights[0].activity_id == act2.id
    assert highlights[0].value == 200.0
    assert highlights[0].rank == 1

    # Check Rank 2
    assert highlights[1].activity_id == act4.id
    assert highlights[1].value == 100.0
    assert highlights[1].rank == 2

    # Check Rank 3
    assert highlights[2].activity_id == act1.id
    assert highlights[2].value == 50.0
    assert highlights[2].rank == 3


def test_update_highlights_across_different_years(
    db: Session, temp_user_id: UUID
) -> None:
    """
    Tests that YEARLY scope is respected and does not interfere with LIFETIME.
    """
    user = db.get(User, temp_user_id)
    assert user is not None

    act2023_best = create_dummy_activity(
        db, user.id, datetime(2023, 1, 1), 500.0
    )  # Best of all time
    act2024_best = create_dummy_activity(
        db, user.id, datetime(2024, 1, 1), 200.0
    )  # Best of 2024
    act2024_second = create_dummy_activity(
        db, user.id, datetime(2024, 2, 1), 100.0
    )  # Second best of 2024

    # ACT: Process all activities
    for act in [act2023_best, act2024_best, act2024_second]:
        update_top_n_highlights(
            session=db,
            user_id=user.id,
            activity=act,
            metric=HighlightMetric.DISTANCE,
            value=act.distance,
        )
        db.commit()

    # ASSERT LIFETIME: The best of all time should be from 2023
    stmt_lifetime = (
        select(ActivityHighlight)
        .where(ActivityHighlight.scope == HighlightTimeScope.LIFETIME)
        .where(ActivityHighlight.user_id == user.id)
        .order_by(ActivityHighlight.rank)  # type: ignore
    )
    lifetime_highlights = db.exec(stmt_lifetime).all()

    assert len(lifetime_highlights) == 3
    assert lifetime_highlights[0].activity_id == act2023_best.id
    assert lifetime_highlights[0].value == 500.0
    assert lifetime_highlights[1].activity_id == act2024_best.id
    assert lifetime_highlights[1].value == 200.0

    # ASSERT 2024 YEARLY: The 2023 activity should not be present
    stmt_2024 = (
        select(ActivityHighlight)
        .where(ActivityHighlight.scope == HighlightTimeScope.YEARLY)
        .where(ActivityHighlight.year == 2024)
        .order_by(ActivityHighlight.rank)  # type: ignore
    )
    yearly_2024_highlights = db.exec(stmt_2024).all()

    assert len(yearly_2024_highlights) == 2
    assert yearly_2024_highlights[0].activity_id == act2024_best.id
    assert yearly_2024_highlights[0].value == 200.0
    assert yearly_2024_highlights[1].activity_id == act2024_second.id
    assert yearly_2024_highlights[1].value == 100.0


def test_process_activity_highlights_task(
    db: Session, temp_user_id: UUID, dummy_track: Track
) -> None:
    """
    Tests the task's logic by calling it directly as a Python function.
    """
    activity = create_dummy_activity(
        db,
        temp_user_id,
        datetime(2024, 1, 1),
        500.0,
        track=dummy_track,
        name="Pytrack activity",
    )
    db.commit()

    # ACT: Call the task function directly, not with .delay()
    process_activity_highlights(activity_id=activity.id, user_id=temp_user_id)

    highlights = db.exec(
        select(ActivityHighlight).where(ActivityHighlight.user_id == temp_user_id)
    ).all()
    assert (
        len(highlights) == len(registry.calculators.keys()) * 2
    )  # Yearly and Lifetime

    lifetime_hl = next(h for h in highlights if h.scope == "lifetime")
    assert lifetime_hl.rank == 1
    assert lifetime_hl.activity_id == activity.id


def test_process_activity_highlights_no_movement(
    db: Session,
    # temp_user_id: UUID,
    user2_id: UUID,
) -> None:
    times = []
    heartrates = []
    powers = []
    for i in range(100):
        times.append(datetime(2024, 1, 1) + timedelta(seconds=i * 10))
        heartrates.append(100 + i % 5)
        powers.append(150 + i % 10)

    track = PyTrack(
        points=[(1, 1)] * len(times),
        times=times,
        elevations=None,
        extensions={
            "heartrate": heartrates,
            "power": powers,
        },
    )

    activity = create_dummy_activity(
        db,
        user2_id,
        datetime(2024, 1, 1),
        500.0,
        track=track,
        name="Stationary activity",
        type_id=6,  # Indoor cardio
    )
    db.commit()

    process_activity_highlights(activity_id=activity.id, user_id=user2_id)
    highlights = db.exec(
        select(ActivityHighlight)
        .where(ActivityHighlight.user_id == user2_id)
        .where(ActivityHighlight.type_id == 6)
    ).all()

    assert len(highlights) > 0, (
        "Should compute highlights even for no-movement activities"
    )
