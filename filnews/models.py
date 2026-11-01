"""Domain objects. They are plain dataclasses persisted as JSON (see store.py)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from django.utils.text import slugify

SLUG_MAX_LENGTH = 80


def tag_slug(name: str) -> str:
    return slugify(name)[:SLUG_MAX_LENGTH].strip("-")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(slots=True)
class News:
    """A news item, ingested from a Reddit post linking to an article."""

    id: str
    title: str
    url: str
    permalink: str
    created_at: datetime
    score: int
    num_comments: int = 0
    subreddit: str = ""
    author: str = ""
    flair: str = ""
    domain: str = ""
    selftext: str = ""
    reddit_thumbnail: str = ""
    ingested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Filled by the analysis step.
    summary: str = ""
    thumbnail: str = ""  # Path relative to MEDIA_ROOT.
    tags: list[str] = field(default_factory=list)
    analyzed_at: datetime | None = None

    @property
    def slug(self) -> str:
        base = slugify(self.title)[:SLUG_MAX_LENGTH].strip("-") or "news"
        return f"{base}-{self.id}"

    @property
    def reddit_url(self) -> str:
        return f"https://www.reddit.com{self.permalink}"

    @property
    def tag_items(self) -> list[Tag]:
        return [Tag(name=name) for name in self.tags]

    @property
    def month_key(self) -> str:
        return self.created_at.strftime("%Y-%m")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("created_at", "ingested_at", "analyzed_at"):
            value = data[key]
            data[key] = value.isoformat() if value else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> News:
        known = set(cls.__dataclass_fields__)
        values = {key: value for key, value in data.items() if key in known}
        values["created_at"] = _parse_dt(values["created_at"])
        values["ingested_at"] = _parse_dt(values.get("ingested_at")) or datetime.now(
            UTC
        )
        values["analyzed_at"] = _parse_dt(values.get("analyzed_at"))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class Tag:
    name: str

    @property
    def slug(self) -> str:
        return tag_slug(self.name)


@dataclass(slots=True)
class TagSummary:
    """A tag with all its news, newest first."""

    name: str
    slug: str
    news: list[News]

    @property
    def count(self) -> int:
        return len(self.news)

    @property
    def last_seen(self) -> datetime:
        return self.news[0].created_at

    @property
    def first_seen(self) -> datetime:
        return self.news[-1].created_at
