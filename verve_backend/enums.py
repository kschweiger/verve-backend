from enum import StrEnum


class GoalType(StrEnum):
    ACTIVITY = "activity"
    MANUAL = "manual"
    LOCATION = "location"


class GoalAggregation(StrEnum):
    COUNT = "count"
    TOTAL_DISTANCE = "total_distance"
    AVG_DISTANCE = "avg_distance"
    MAX_DISTANCE = "max_distance"
    DURATION = "duration"


class TemportalType(StrEnum):
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
