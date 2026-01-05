"""
Natural language date parsing for GA Multi MCP.

Supports various date formats and relative date expressions
commonly used when querying analytics data.
"""

import re
from datetime import datetime, timedelta
from typing import Tuple


class DateParseError(Exception):
    """Raised when a date string cannot be parsed."""
    pass


def parse_date(date_str: str) -> str:
    """
    Parse a date string into YYYY-MM-DD format.

    Supports:
        - ISO format: "2024-01-15"
        - US format: "01/15/2024"
        - Relative: "today", "yesterday"
        - Days ago: "7daysAgo", "30daysago"
        - Weeks ago: "1weekAgo", "2weeksago"
        - Months ago: "1monthAgo", "3monthsago"
        - Named: "last week", "last month", "this week", "this month"

    Args:
        date_str: The date string to parse

    Returns:
        str: Date in YYYY-MM-DD format

    Raises:
        DateParseError: If the date string cannot be parsed
    """
    if not date_str:
        raise DateParseError("Date string cannot be empty")

    date_str = date_str.strip().lower()
    today = datetime.now()

    # ISO format (YYYY-MM-DD)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # US format (MM/DD/YYYY)
    if match := re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", date_str):
        month, day, year = match.groups()
        try:
            parsed = datetime(int(year), int(month), int(day))
            return parsed.strftime("%Y-%m-%d")
        except ValueError as e:
            raise DateParseError(f"Invalid date: {date_str}. {e}")

    # Relative dates
    if date_str == "today":
        return today.strftime("%Y-%m-%d")

    if date_str == "yesterday":
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # N days ago
    if match := re.match(r"^(\d+)\s*days?\s*ago$", date_str):
        days = int(match.group(1))
        return (today - timedelta(days=days)).strftime("%Y-%m-%d")

    # N weeks ago
    if match := re.match(r"^(\d+)\s*weeks?\s*ago$", date_str):
        weeks = int(match.group(1))
        return (today - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

    # N months ago (approximate - 30 days per month)
    if match := re.match(r"^(\d+)\s*months?\s*ago$", date_str):
        months = int(match.group(1))
        return (today - timedelta(days=months * 30)).strftime("%Y-%m-%d")

    # Last week (start of previous week - Monday)
    if date_str in ("last week", "lastweek"):
        # Go to start of current week, then back 7 days
        days_since_monday = today.weekday()
        start_of_week = today - timedelta(days=days_since_monday)
        last_week_start = start_of_week - timedelta(days=7)
        return last_week_start.strftime("%Y-%m-%d")

    # Last month (first day of previous month)
    if date_str in ("last month", "lastmonth"):
        first_of_current_month = today.replace(day=1)
        last_month = first_of_current_month - timedelta(days=1)
        return last_month.replace(day=1).strftime("%Y-%m-%d")

    # This week (start of current week - Monday)
    if date_str in ("this week", "thisweek"):
        days_since_monday = today.weekday()
        start_of_week = today - timedelta(days=days_since_monday)
        return start_of_week.strftime("%Y-%m-%d")

    # This month (first day of current month)
    if date_str in ("this month", "thismonth"):
        return today.replace(day=1).strftime("%Y-%m-%d")

    # Start of year
    if date_str in ("this year", "thisyear", "ytd"):
        return today.replace(month=1, day=1).strftime("%Y-%m-%d")

    # Last year
    if date_str in ("last year", "lastyear"):
        return today.replace(year=today.year - 1, month=1, day=1).strftime("%Y-%m-%d")

    raise DateParseError(
        f"Could not parse date: '{date_str}'. "
        f"Supported formats: YYYY-MM-DD, MM/DD/YYYY, today, yesterday, "
        f"NdaysAgo, NweeksAgo, NmonthsAgo, last week, last month, "
        f"this week, this month, ytd"
    )


def parse_date_range(
    start_date: str,
    end_date: str
) -> Tuple[str, str]:
    """
    Parse a date range with validation.

    Args:
        start_date: Start date string
        end_date: End date string

    Returns:
        Tuple[str, str]: (start_date, end_date) in YYYY-MM-DD format

    Raises:
        DateParseError: If dates cannot be parsed or range is invalid
    """
    start = parse_date(start_date)
    end = parse_date(end_date)

    # Validate range
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    if start_dt > end_dt:
        raise DateParseError(
            f"Start date ({start}) must be before or equal to end date ({end})"
        )

    return start, end


def get_date_range_description(start_date: str, end_date: str) -> str:
    """
    Generate a human-readable description of a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        str: Human-readable description
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    days = (end_dt - start_dt).days + 1

    # Check for common ranges
    if start_dt == end_dt:
        if end_dt.date() == today.date():
            return "Today"
        elif end_dt.date() == (today - timedelta(days=1)).date():
            return "Yesterday"
        else:
            return start_dt.strftime("%B %d, %Y")

    if end_dt.date() == today.date():
        if days == 7:
            return "Last 7 days"
        elif days == 14:
            return "Last 14 days"
        elif days == 28:
            return "Last 28 days"
        elif days == 30:
            return "Last 30 days"
        elif days == 90:
            return "Last 90 days"

    return f"{start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')} ({days} days)"
