"""Original content computed from FilNews' own data, so that pages say more
than their sources: the context of a news (its rank on r/france that day, its
place in each Fil) and the profile of a tag (peak, media, most voted news,
neighbouring Fils)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from django.utils import timezone
from django.utils.timesince import timesince

from .models import News, TagSummary, tag_slug
from .store import NewsStore

NEWS_THREAD_COUNT = 3  # Fils described on a news page, biggest first.
TOP_DOMAIN_COUNT = 3
NEIGHBOUR_COUNT = 3
# Below this, "most cited media" or a peak month says nothing.
MIN_NEWS_FOR_STATS = 3


@dataclass(frozen=True, slots=True)
class ThreadPosition:
    """Where a news stands in the Fil of one of its tags."""

    tag: TagSummary
    rank: int  # 1 for the first (oldest) news of the Fil.
    previous: News | None  # The news before it in the Fil.
    gap: str  # Time since `previous`, e.g. "3 jours".


@dataclass(frozen=True, slots=True)
class NewsContext:
    day_rank: int  # 1 for the most voted news of its day.
    day_count: int
    threads: list[ThreadPosition]


@dataclass(frozen=True, slots=True)
class TagProfile:
    peak_month: date | None  # First day of the busiest month.
    peak_count: int
    domains: list[tuple[str, int]]  # Most cited media, with their news count.
    top_news: News
    neighbours: list[TagSummary]  # Fils that most often share its news.


def news_context(store: NewsStore, news: News) -> NewsContext:
    day = sorted(store.same_day(news), key=lambda n: n.score, reverse=True)
    day_rank = next((i for i, n in enumerate(day, 1) if n.id == news.id), 1)
    threads = []
    for name in news.tags:
        tag = store.tag_page(tag_slug(name))
        if tag is None:
            continue
        index = store.indexes.positions[tag.slug][news.id]
        previous = tag.news[index + 1] if index + 1 < tag.count else None
        threads.append(
            ThreadPosition(
                tag=tag,
                rank=tag.count - index,
                previous=previous,
                gap=timesince(previous.created_at, news.created_at, depth=1)
                if previous
                else "",
            )
        )
    threads.sort(key=lambda position: position.tag.count, reverse=True)
    return NewsContext(
        day_rank=day_rank,
        day_count=max(len(day), 1),
        threads=threads[:NEWS_THREAD_COUNT],
    )


def tag_profile(store: NewsStore, tag: TagSummary) -> TagProfile:
    months: Counter[date] = Counter()
    domains: Counter[str] = Counter()
    neighbours: Counter[str] = Counter()
    for news in tag.news:
        months[timezone.localdate(news.created_at).replace(day=1)] += 1
        if news.domain:
            domains[news.domain] += 1
        neighbours.update(
            slug for name in news.tags if (slug := tag_slug(name)) != tag.slug
        )

    peak_month, peak_count = None, 0
    if tag.count >= MIN_NEWS_FOR_STATS and len(months) > 1:
        # Ties: the most recent month.
        peak_month, peak_count = max(months.items(), key=lambda kv: (kv[1], kv[0]))
        if peak_count < 2:
            peak_month, peak_count = None, 0

    top_domains = []
    if tag.count >= MIN_NEWS_FOR_STATS:
        top_domains = [
            (domain, count)
            for domain, count in domains.most_common(TOP_DOMAIN_COUNT)
            if count >= 2
        ]

    neighbour_pages = [
        page for slug, _ in neighbours.most_common() if (page := store.tag_page(slug))
    ][:NEIGHBOUR_COUNT]

    return TagProfile(
        peak_month=peak_month,
        peak_count=peak_count,
        domains=top_domains,
        top_news=max(tag.news, key=lambda n: (n.score, n.created_at)),
        neighbours=neighbour_pages,
    )
