"""Tag groups: the history of a news through all its tags at once.

A news tagged "Police" and "Justice" belongs to the group "Police + Justice":
every news carrying both tags (and possibly others). Such a group says more
about the news than each of its tags alone, which can gather hundreds of news
on very different stories.

The group shown on a news page is the most specific one with a history: all
the tags of the news if another news carries them all, otherwise the largest
subset of its tags shared with other news. Other groups of its tags follow,
when they bring other news.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, pairwise

from django.utils.timesince import timesince

from .models import News, TagGroup, TagSummary, tag_slug
from .store import NewsStore
from .timeline import Timeline, build_timeline

WINDOW_SIZE = 5  # News of the group listed around the current one...
WINDOW_NEWER = 2  # ... of which at most this many newer ones (when possible).
OTHER_GROUP_COUNT = 3
# The group timeline sits in a narrow panel: fewer labels than in a tag card.
TICK_COUNT = 4


@dataclass(frozen=True, slots=True)
class GroupEntry:
    news: News
    current: bool  # The news of the page.
    gap_after: str  # Time between this news and the next (older) one listed.


@dataclass(frozen=True, slots=True)
class NewsGroups:
    tags: list[TagSummary]  # All the tags of the news.
    group: TagGroup  # The most specific group with a history.
    rank: int  # Place of the news in `group`, 1 for the oldest.
    entries: list[GroupEntry]  # News of `group` around the current one.
    timeline: Timeline
    others: list[TagGroup]  # Other groups of its tags, bringing other news.

    @property
    def complete(self) -> bool:
        """Whether `group` gathers every tag of the news."""
        return len(self.group.tags) == len(self.tags)

    @property
    def listed_ids(self) -> list[str]:
        return [entry.news.id for entry in self.entries]


def news_groups(store: NewsStore, news: News) -> NewsGroups | None:
    """Groups of tags of `news` that other news share, or None (fewer than 2
    tags, or no other news with 2 of its tags)."""
    tags = [tag for name in news.tags if (tag := store.tag(tag_slug(name)))]
    if len(tags) < 2:
        return None
    candidates = [
        TagGroup.of(list(subset), items)
        for size in range(len(tags), 1, -1)
        for subset in combinations(tags, size)  # Keeps the order of the news.
        if len(items := store.group(tag.slug for tag in subset)) >= 2
    ]
    if not candidates:
        return None
    # Most specific first, then the biggest.
    candidates.sort(key=lambda group: (len(group.tags), group.count), reverse=True)
    main, *rest = (group for group in candidates if not _redundant(group, candidates))
    index = next(i for i, item in enumerate(main.news) if item.id == news.id)
    return NewsGroups(
        tags=tags,
        group=main,
        rank=main.count - index,
        entries=_window(main.news, index),
        timeline=build_timeline(main, current=news, tick_count=TICK_COUNT),
        others=rest[:OTHER_GROUP_COUNT],
    )


def _redundant(group: TagGroup, candidates: list[TagGroup]) -> bool:
    """A group with the same news as a more specific one adds nothing."""
    return any(
        group.slugs < other.slugs and group.count == other.count for other in candidates
    )


def _window(items: list[News], index: int) -> list[GroupEntry]:
    """Up to WINDOW_SIZE news around `items[index]` (newest first): a few
    newer ones, then the older ones, i.e. the history before the news."""
    older = min(len(items) - index - 1, WINDOW_SIZE - 1 - min(index, WINDOW_NEWER))
    newer = min(index, WINDOW_SIZE - 1 - older)
    window = items[index - newer : index + older + 1]
    gaps = [
        timesince(older_news.created_at, newer_news.created_at, depth=1)
        for newer_news, older_news in pairwise(window)
    ]
    return [
        GroupEntry(news=item, current=item.id == items[index].id, gap_after=gap)
        for item, gap in zip(window, [*gaps, ""], strict=True)
    ]
