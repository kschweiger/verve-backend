"""Convert between stored RPM and activity-specific cadence at boundaries."""


def is_running_activity(activity_type: str, activity_sub_type: str | None) -> bool:
    return activity_type == "Foot Sports" and activity_sub_type in {
        "Run",
        "Trail Run",
        "Treadmill",
    }


def cadence_from_verve(value: int | None, *, running: bool) -> float | None:
    """Convert Verve running steps/min to RPM before storage."""
    if value is None:
        return None
    return value / 2 if running else float(value)


def cadence_for_activity(value: float | None, *, running: bool) -> float | None:
    """Convert stored RPM to running steps/min when returning an activity."""
    if value is None:
        return None
    return value * 2 if running else value
