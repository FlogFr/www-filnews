"""French date formatting."""

from __future__ import annotations

import re
from datetime import date, datetime

from django.utils import timezone
from django.utils.dateformat import format as date_format

# "j" (day of the month) not escaped by a backslash.
_DAY_RE = re.compile(r"(?<!\\)j")


def format_date(value: date | datetime, fmt: str) -> str:
    """Django date format (local time), with "1er" for the first day of a
    month, as written in French ("1er novembre", not "1 novembre")."""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    if value.day == 1:
        fmt = _DAY_RE.sub(r"\\1\\e\\r", fmt)
    return date_format(value, fmt)
