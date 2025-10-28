from datetime import date, datetime, timedelta


def get_week_date_range(year: int, week: int) -> tuple[date, date]:
    """
    Get the start and end dates for an ISO week (exclusive range).
    """
    jan_4 = datetime(year, 1, 4)  # Always in first week in ISO 8601
    week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
    start_date = week_1_monday + timedelta(weeks=week - 1)
    end_date = start_date + timedelta(days=7)  # Exclusive end

    return start_date.date(), end_date.date()
