import json
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files

import verve_backend.locales
from verve_backend.api.deps import SupportedLocale


class TimeOfDay(StrEnum):
    MORNING = "morning"  # 05:00 - 11:59
    AFTERNOON = "afternoon"  # 12:00 - 17:59
    EVENING = "evening"  # 18:00 - 21:59
    NIGHT = "night"  # 22:00 - 04:59


@lru_cache()
def load_translations(locale: SupportedLocale) -> dict:
    """Load translations using importlib.resources and cache in memory"""
    try:
        locale_file = files(verve_backend.locales).joinpath(f"{locale}.json")
        return json.loads(locale_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # Fallback to English
        locale_file = files(verve_backend.locales).joinpath("en.json")
        return json.loads(locale_file.read_text(encoding="utf-8"))


def get_time_of_day(timestamp: datetime) -> TimeOfDay:
    """Determine time of day from timestamp"""
    hour = timestamp.hour

    if 5 <= hour < 12:
        return TimeOfDay.MORNING
    elif 12 <= hour < 18:
        return TimeOfDay.AFTERNOON
    elif 18 <= hour < 22:
        return TimeOfDay.EVENING
    else:  # 22-04
        return TimeOfDay.NIGHT


def get_activity_name(
    activity_type: str, timestamp: datetime, locale: str = "en"
) -> str:
    """
    Get localized activity name based on type and time of day.

    Args:
        activity_type: Type of activity (e.g., "cycling", "foot_sports")
        timestamp: When the activity occurred
        locale: Language code (e.g., "en", "de")

    Returns:
        Localized activity name
    """
    translations = load_translations(locale)
    time_of_day = get_time_of_day(timestamp)

    # Try to get the specific activity type
    activity_names = translations["activity_name"]

    # First try the specific activity type
    if activity_type in activity_names:
        return activity_names[activity_type][time_of_day.value]

    # Fallback to default
    return activity_names["default"][time_of_day.value]
