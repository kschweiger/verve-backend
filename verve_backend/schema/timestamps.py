"""Offset-qualified timestamps at the Verve file boundary."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BeforeValidator


def _parse_file_timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value
    raise ValueError("File timestamps must be datetime strings or datetime values")


FileTimestamp = Annotated[AwareDatetime, BeforeValidator(_parse_file_timestamp)]
