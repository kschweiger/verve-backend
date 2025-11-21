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


if __name__ == "__main__":
    from pprint import pprint

    pprint(get_month_grid(2025, 11))
