"""Tag history: horizontal timeline (hover card) and vertical thread (tag page)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Literal

from django.conf import settings
from django.utils import timezone
from django.utils.timesince import timesince

from .dates import format_date as date_format
from .models import News, TagSummary

TICK_COUNT = 5
MIN_SPAN = timedelta(days=2)  # Even a single news gets a readable axis.
PADDING = 0.08  # Share of the span kept empty on each side of the axis.
AXIS_Y = 20  # Bars stand on the axis (SVG pixels, see partials/timeline.html).
BAR_MAX_HEIGHT = 18


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    news: News
    position: float  # 0..100, percentage along the axis.


@dataclass(frozen=True, slots=True)
class TimelineTick:
    label: str
    position: float


@dataclass(frozen=True, slots=True)
class TimelineBar:
    """Number of news of a period, for tags with too many news for dots."""

    label: str
    count: int
    position: float  # Left edge, 0..100.
    width: float
    height: float  # SVG pixels, relative to the busiest period.

    @property
    def y(self) -> float:
        return AXIS_Y - self.height


@dataclass(frozen=True, slots=True)
class Timeline:
    start: datetime
    end: datetime
    points: list[TimelinePoint]
    ticks: list[TimelineTick]
    bars: list[TimelineBar]


def _next_boundary(moment: datetime, unit: str) -> datetime:
    """First year/month/day boundary strictly after `moment` (local time)."""
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == "day":
        return day + timedelta(days=1)
    if unit == "month":
        first = day.replace(day=1)
        return (
            first.replace(year=first.year + 1, month=1)
            if first.month == 12
            else first.replace(month=first.month + 1)
        )
    return day.replace(year=day.year + 1, month=1, day=1)


def _tick_unit(span: timedelta) -> tuple[str, str]:
    """Tick unit and date format suited to the axis length."""
    if span >= timedelta(days=3 * 365):
        return "year", "Y"
    if span >= timedelta(days=90):
        return "month", "N Y"
    return "day", "j N"


def _bucket_unit(span: timedelta) -> tuple[str, str]:
    """Period of a histogram bar: fine enough to show the rhythm of a tag."""
    if span > timedelta(days=5 * 365):
        return "year", "Y"
    if span >= timedelta(days=90):
        return "month", "F Y"
    return "day", "j F Y"


def _period_start(moment: datetime, unit: str) -> datetime:
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == "day":
        return day
    if unit == "month":
        return day.replace(day=1)
    return day.replace(month=1, day=1)


def build_timeline(tag: TagSummary) -> Timeline:
    """Axis fitted to the tag's history, so close news stay distinguishable.

    Up to FILNEWS_TIMELINE_MAX_DOTS news, one dot per news; beyond, a dot
    cloud is unreadable (and heavy): one bar per period instead.
    """
    first = timezone.localtime(tag.first_seen)
    span = max(tag.last_seen - tag.first_seen, MIN_SPAN)
    middle = first + (tag.last_seen - tag.first_seen) / 2
    start = middle - span * (0.5 + PADDING)
    end = middle + span * (0.5 + PADDING)
    total = end.timestamp() - start.timestamp()

    def position(moment: datetime) -> float:
        # Timestamps, not datetime subtraction: local boundaries span DST changes.
        return round((moment.timestamp() - start.timestamp()) / total * 100, 3)

    points: list[TimelinePoint] = []
    bars: list[TimelineBar] = []
    if tag.count <= settings.FILNEWS_TIMELINE_MAX_DOTS:
        points = [
            TimelinePoint(news=n, position=position(n.created_at)) for n in tag.news
        ]
    else:
        bars = _bars(tag, start, end, position)

    unit, label_format = _tick_unit(end - start)
    boundaries = []
    moment = _next_boundary(start, unit)
    while moment < end:
        boundaries.append(moment)
        moment = _next_boundary(moment, unit)
    step = max(ceil(len(boundaries) / TICK_COUNT), 1)
    ticks = [
        TimelineTick(label=date_format(moment, label_format), position=position(moment))
        for moment in boundaries[::step]
    ]
    return Timeline(start=start, end=end, points=points, ticks=ticks, bars=bars)


def _bars(
    tag: TagSummary, start: datetime, end: datetime, position
) -> list[TimelineBar]:
    unit, label_format = _bucket_unit(tag.last_seen - tag.first_seen)
    counts: dict[datetime, int] = {}
    for news in tag.news:
        period = _period_start(timezone.localtime(news.created_at), unit)
        counts[period] = counts.get(period, 0) + 1
    busiest = max(counts.values())
    bars = []
    for period, count in sorted(counts.items()):
        left = max(position(period), 0)
        right = min(position(_next_boundary(period, unit)), 100)
        bars.append(
            TimelineBar(
                label=date_format(period, label_format),
                count=count,
                position=left,
                width=round(max(right - left, 0.5), 3),
                height=round(max(count / busiest * BAR_MAX_HEIGHT, 2), 1),
            )
        )
    return bars


@dataclass(frozen=True, slots=True)
class ThreadEntry:
    news: News
    side: Literal["left", "right"]
    new_year: bool  # First entry of its year: the thread shows a year marker.
    gap: str  # Time since the previous (more recent) entry, e.g. "2 jours".


def _local_year(news: News) -> int:
    return timezone.localtime(news.created_at).year


def thread_years(tag: TagSummary) -> list[tuple[int, int]]:
    """(year, news count) newest first, when the tag's Fil is split by year."""
    if tag.count <= settings.FILNEWS_TAG_THREAD_SIZE:
        return []
    years: dict[int, int] = {}
    for news in tag.news:
        years[_local_year(news)] = years.get(_local_year(news), 0) + 1
    return list(years.items())


def build_thread(tag: TagSummary, year: int | None = None) -> list[ThreadEntry]:
    """News of the tag (of `year` only, if given), newest first, alternating
    sides of the thread."""
    return thread_entries(
        [n for n in tag.news if year is None or _local_year(n) == year]
    )


def thread_entries(news_list: list[News]) -> list[ThreadEntry]:
    """A Fil of news (newest first), alternating sides of the thread."""
    entries = []
    previous: News | None = None
    for index, news in enumerate(news_list):
        entries.append(
            ThreadEntry(
                news=news,
                side="left" if index % 2 == 0 else "right",
                new_year=previous is None or _local_year(previous) != _local_year(news),
                gap=timesince(news.created_at, previous.created_at, depth=1)
                if previous
                else "",
            )
        )
        previous = news
    return entries
