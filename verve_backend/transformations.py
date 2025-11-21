from collections import defaultdict
from datetime import date
from typing import Annotated, Sequence

from pydantic import BaseModel, Field

from verve_backend.models import Activity


class StatsMetric(BaseModel):
    """Base metric unit to reuse across subtypes, types, and totals."""

    count: int = 0
    distance: float = 0.0
    duration: int = 0  # seconds
    elevation_gain: float = 0.0

    def add_activity(self, activity: Activity) -> None:
        self.count += 1
        self.distance += activity.distance or 0.0
        self.duration += int(activity.duration.total_seconds())
        if activity.elevation_change_up:
            self.elevation_gain += activity.elevation_change_up


class TypeStats(StatsMetric):
    """Stats for a specific Activity Type (e.g. Cycling), broken down by subtype."""

    type_id: int
    # Key is sub_type_id. Using dict for O(1) lookup in frontend
    by_subtype: dict[int, StatsMetric] = Field(default_factory=dict)


class CalendarDay(BaseModel):
    date: date
    is_in_month: bool = True  # Helper to gray out padding days from prev/next month

    # -- For the "Simple View" --
    # Just the IDs present on this day (e.g., [1, 4] for Run, Swim)
    active_type_ids: list[int] = Field(default_factory=list)

    # -- For the "Complex View" --
    total: StatsMetric = Field(default_factory=StatsMetric)
    # Key is type_id (e.g., 1 for Cycling)
    activities: dict[int, TypeStats] = Field(default_factory=dict)


class CalendarWeek(BaseModel):
    days: Annotated[list[CalendarDay], Field(min_length=7, max_length=7)]
    week_summary: StatsMetric = Field(default_factory=StatsMetric)


def build_calendar_response(
    activities: Sequence[Activity], month_grid: list[list[date]], target_month: int
) -> list[CalendarWeek]:
    # 1. Pre-process activities into a fast lookup dictionary
    # Structure: date -> type_id -> list[Activity]
    mapped_activities = defaultdict(lambda: defaultdict(list))
    for act in activities:
        mapped_activities[act.start.date()][act.type_id].append(act)

    weeks_data = []

    for week_dates in month_grid:
        week_days_data = []
        week_total = StatsMetric()

        for current_date in week_dates:
            day_data = CalendarDay(
                date=current_date, is_in_month=(current_date.month == target_month)
            )

            # If we have activities for this date
            if current_date in mapped_activities:
                # Sort types for consistent icon ordering in Simple View
                present_types = sorted(mapped_activities[current_date].keys())
                day_data.active_type_ids = present_types

                for type_id in present_types:
                    # Initialize Type Stats
                    t_stats = TypeStats(type_id=type_id)

                    acts_of_type = mapped_activities[current_date][type_id]

                    for act in acts_of_type:
                        # Update Day Total
                        day_data.total.add_activity(act)

                        # Update Type Total
                        t_stats.add_activity(act)

                        # Update SubType Stats
                        sub_id = (
                            act.sub_type_id or 0
                        )  # Handle None as 0 or a specific 'Uncategorized' ID
                        if sub_id not in t_stats.by_subtype:
                            t_stats.by_subtype[sub_id] = StatsMetric()
                        t_stats.by_subtype[sub_id].add_activity(act)

                    # Assign the type stats to the day
                    day_data.activities[type_id] = t_stats

                # Add day totals to week totals
                week_total.count += day_data.total.count
                week_total.distance += day_data.total.distance
                week_total.duration += day_data.total.duration
                week_total.elevation_gain += day_data.total.elevation_gain

            week_days_data.append(day_data)

        weeks_data.append(CalendarWeek(days=week_days_data, week_summary=week_total))

    return weeks_data
