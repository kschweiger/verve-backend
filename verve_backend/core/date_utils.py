from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def get_week_date_range(year: int, week: int) -> tuple[date, date]:
    """
    Get the start and end dates for an ISO week (exclusive range).
    """
    jan_4 = datetime(year, 1, 4)  # Always in first week in ISO 8601
    week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
    start_date = week_1_monday + timedelta(weeks=week - 1)
    end_date = start_date + timedelta(days=7)  # Exclusive end

    return start_date.date(), end_date.date()


def get_month_grid(year: int, month: int) -> list[list[date]]:
    first_day = date(year, month, 1)
    weekday_of_first = first_day.weekday()

    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    start_date = first_day - timedelta(days=weekday_of_first)

    grid = []
    current_date = start_date

    while current_date <= last_day or len(grid) == 0 or current_date.weekday() != 0:
        week = []
        for _ in range(7):
            week.append(current_date)
            current_date += timedelta(days=1)
        grid.append(week)

        if current_date > last_day and current_date.weekday() == 0:
            break

    return grid


def get_all_dates_in_month(year: int, month: int) -> list[date]:
    """
    Generate all dates for a given month.

    Args:
        year: The year
        month: The month (1-12)

    Returns:
        List of all dates in the month
    """
    first_day = date(year, month, 1)

    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    dates = []
    current_date = first_day
    while current_date <= last_day:
        dates.append(current_date)
        current_date += timedelta(days=1)

    return dates


def get_week_numbers_between_dates(start_date: date, end_date: date) -> list[int]:
    """
    Generate all ISO week numbers between two dates (inclusive).

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        List of week numbers for all weeks between the dates
    """
    weeks = []
    current_date = start_date

    while current_date <= end_date:
        week_number = current_date.isocalendar()[1]

        if not weeks or weeks[-1] != week_number:
            weeks.append(week_number)

        current_date += timedelta(days=1)

    return weeks


def iso_week_date_weeks_ago_berlin(weeks_back: int, iso_weekday: int = 1) -> date:
    if weeks_back < 0:
        raise ValueError("weeks_back must be >= 0")

    if not 1 <= iso_weekday <= 7:
        raise ValueError("iso_weekday must be in range 1..7")

    today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    target = today - timedelta(weeks=weeks_back)
    iso = target.isocalendar()

    return datetime.fromisocalendar(iso.year, iso.week, iso_weekday).date()


if __name__ == "__main__":
    from pprint import pprint

    pprint(get_month_grid(2025, 11))
