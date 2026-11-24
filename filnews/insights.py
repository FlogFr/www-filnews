"""Original content computed from FilNews' own data, so that pages say more
than their sources: the context of a news (its rank on r/france that day, its
place in each Fil), the profile of a tag (peak, media, most voted news,
neighbouring Fils) and its critical reading (rhythm, plurality of sources,
angles, reception on r/france), each fact measured against the whole site.

Everything is computed: no external service, no language model, no opinion
on the content of the articles."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

from django.utils import timezone
from django.utils.timesince import timesince

from .media import MEDIA_FAMILY_LABELS, media_family
from .models import News, TagSummary, tag_slug
from .store import NewsStore, _Indexes

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


# --- Critical reading of a Fil ----------------------------------------------

# Below this, percentages on a Fil would mean little.
MIN_NEWS_FOR_READING = 10
# Rhythm: no news for this long (before the site's latest news) = dormant,
# started this recently = new.
DORMANT_DAYS = 180
NEW_DAYS = 90
# A wave: this share of the Fil's news, or of its weight, in the busiest
# window of consecutive months (and at least WAVE_MIN_RAW_SHARE of its news).
# Each news weighs the inverse of the site's tag count that month: the site
# keeps far more news now than in 2016, and news analysed since November 2026
# (on the article's text) get about twice as many tags as the retagged
# history. For the same reason, there is no "recent trend": it would mostly
# measure that change.
WAVE_MONTHS = 3
WAVE_SHARE = 0.4
WAVE_MIN_RAW_SHARE = 0.25
WAVE_MIN_SPAN = 12  # Months covered by the Fil, for a wave to stand out.
# A background subject: present at least this share of the months it covers.
BACKGROUND_PRESENCE = 0.5
BACKGROUND_MIN_SPAN = 24
# Sources: one media or three media providing this share of the news.
TOP_MEDIA_SHARE = 0.35
TOP3_MEDIA_SHARE = 0.65
# A media family over-represented by this many points (and at least this
# share of the Fil), or under-represented: a third of its site share or less.
FAMILY_GAP = 0.15
FAMILY_MIN_SHARE = 0.25
FAMILY_MIN_SITE_SHARE = 0.10
# Angles: Fils sharing at least this share of the news.
ANGLE_COUNT = 2
ANGLE_MIN_SHARE = 0.15
# Angle shift: last 12 months against before, each period with enough news.
SHIFT_DAYS = 365
SHIFT_MIN_NEWS = 8
SHIFT_MIN_SHARE = 0.2
# Reception: comments per vote and votes, relative to the news of the same
# month on the site (scores grew a lot over ten years).
DEBATE_HIGH = 1.4
DEBATE_LOW = 0.7
VOTES_HIGH = 1.15
VOTES_LOW = 0.87


@dataclass(frozen=True, slots=True)
class SiteBaseline:
    """Reference values of the whole site, to compare a Fil with. Monthly,
    since volumes, scores and tags per news changed a lot over ten years."""

    latest: datetime  # The site's most recent news.
    month_tags: dict[int, int]  # Tags given in each month (`_month_index`).
    month_votes: dict[int, float]  # Median score of each month.
    month_debate: dict[int, float]  # Median comments per vote of each month.
    families: dict[str, float]  # Share of the site's news by media family.


@dataclass(frozen=True, slots=True)
class Rhythm:
    kind: str  # "dormant", "new", "wave", "background" or "intermittent".
    span_months: int  # Calendar months from the first to the last news.
    active_months: int  # Months with at least one news.
    wave_start: date | None  # First month of the busiest window, if a wave.
    wave_end: date | None
    wave_count: int  # News in that window.
    wave_share: int  # Percentage of the Fil's news in that window.
    idle_months: int  # Since the last news (meaningful if dormant)…
    idle_years: int  # … or in whole years.


@dataclass(frozen=True, slots=True)
class FamilyShare:
    label: str  # "presse régionale".
    share: int  # Percentage of the Fil's news.
    site_share: int  # Percentage of the site's news.


@dataclass(frozen=True, slots=True)
class Sources:
    count: int  # Distinct media.
    top: str  # Most cited media.
    top_share: int  # Percentage of the news from `top`.
    top3_share: int  # Percentage of the news from the 3 most cited media.
    concentrated: bool
    over: FamilyShare | None  # Family much more present than on the site.
    under: FamilyShare | None  # Family much less present than on the site.


@dataclass(frozen=True, slots=True)
class Angle:
    tag: TagSummary
    share: int  # Percentage of the Fil's news also in `tag`.


@dataclass(frozen=True, slots=True)
class TagReading:
    rhythm: Rhythm
    sources: Sources
    angles: list[Angle]  # Fils sharing many of its news, biggest first.
    max_angle_share: int  # When `angles` is empty: the biggest share.
    recent_angle: Angle | None  # Main angle over the last 12 months…
    former_angle: Angle | None  # … when it differs from the one before.
    # Comments per vote and votes of its median news, relative to the median
    # news of the same month on the site: "high", "low" or "average", the
    # ratio (1.4) and the gap as a percentage (40).
    debate: str
    debate_factor: float
    debate_percent: int
    votes: str
    votes_factor: float
    votes_percent: int


def _month_index(day: date) -> int:
    return day.year * 12 + day.month - 1


def _from_month_index(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def _news_month(news: News) -> int:
    return _month_index(timezone.localdate(news.created_at))


def _debate(news: News) -> float:
    return news.num_comments / max(news.score, 1)


def _percent(part: float, whole: float) -> int:
    return round(100 * part / whole) if whole else 0


@lru_cache(maxsize=1)
def _baseline(indexes: _Indexes) -> SiteBaseline:
    """Computed once per state of the store (indexes are rebuilt after each
    change, so they identify it)."""
    news = indexes.by_date
    families = Counter(media_family(n.domain) or "" for n in news)
    months: dict[int, list[News]] = {}
    for entry in news:
        months.setdefault(_news_month(entry), []).append(entry)
    return SiteBaseline(
        latest=news[0].created_at,
        month_tags={
            key: sum(len(n.tags) for n in items) or 1 for key, items in months.items()
        },
        month_votes={
            key: statistics.median(n.score for n in items) or 1
            for key, items in months.items()
        },
        month_debate={
            key: statistics.median(map(_debate, items)) or 1
            for key, items in months.items()
        },
        families={family: count / len(news) for family, count in families.items()},
    )


def _rhythm(tag: TagSummary, baseline: SiteBaseline) -> Rhythm:
    months = Counter(map(_news_month, tag.news))
    first, last = min(months), max(months)
    span = last - first + 1

    # The busiest window of WAVE_MONTHS consecutive months (ties: the latest).
    weights = {m: count / baseline.month_tags[m] for m, count in months.items()}
    window = min(WAVE_MONTHS, span)
    wave_weight, wave_first = max(
        (sum(weights.get(m, 0) for m in range(start, start + window)), start)
        for start in range(first, last - window + 2)
    )
    wave_count = sum(months[m] for m in range(wave_first, wave_first + window))
    raw_share = wave_count / tag.count
    is_wave = (
        span >= WAVE_MIN_SPAN
        and raw_share >= WAVE_MIN_RAW_SHARE
        and max(raw_share, wave_weight / sum(weights.values())) >= WAVE_SHARE
    )

    idle = baseline.latest - tag.last_seen
    if idle >= timedelta(days=DORMANT_DAYS):
        kind = "dormant"
    elif baseline.latest - tag.first_seen <= timedelta(days=NEW_DAYS):
        kind = "new"
    elif is_wave:
        kind = "wave"
    elif span >= BACKGROUND_MIN_SPAN and len(months) / span >= BACKGROUND_PRESENCE:
        kind = "background"
    else:
        kind = "intermittent"

    show_wave = is_wave and kind in ("wave", "dormant")
    return Rhythm(
        kind=kind,
        span_months=span,
        active_months=len(months),
        wave_start=_from_month_index(wave_first) if show_wave else None,
        wave_end=_from_month_index(wave_first + window - 1) if show_wave else None,
        wave_count=wave_count,
        wave_share=_percent(wave_count, tag.count),
        idle_months=idle.days * 12 // 365,
        idle_years=idle.days // 365,
    )


def _sources(tag: TagSummary, site_families: dict[str, float]) -> Sources:
    domains = Counter(news.domain or "" for news in tag.news)
    domains.pop("", None)
    top3 = domains.most_common(3)
    top, top_count = top3[0] if top3 else ("", 0)
    top3_count = sum(count for _, count in top3)
    concentrated = (
        top_count / tag.count >= TOP_MEDIA_SHARE
        or top3_count / tag.count >= TOP3_MEDIA_SHARE
    )

    # The most over-represented family and the biggest under-represented one.
    families = Counter(media_family(news.domain) for news in tag.news)
    over = under = None
    best_gap = FAMILY_GAP
    under_site_share = 0.0
    for family, label in MEDIA_FAMILY_LABELS.items():
        share = families[family] / tag.count
        site_share = site_families.get(family, 0.0)
        found = FamilyShare(label, _percent(share, 1), _percent(site_share, 1))
        if share >= FAMILY_MIN_SHARE and share - site_share >= best_gap:
            over, best_gap = found, share - site_share
        if (
            site_share >= FAMILY_MIN_SITE_SHARE
            and share <= site_share / 3
            and site_share > under_site_share
        ):
            under, under_site_share = found, site_share
    return Sources(
        count=len(domains),
        top=top,
        top_share=_percent(top_count, tag.count),
        top3_share=_percent(top3_count, tag.count),
        concentrated=concentrated,
        over=over,
        under=under,
    )


def _main_angle(store: NewsStore, tag: TagSummary, news: list[News]) -> Angle | None:
    counts = Counter(
        slug for entry in news for name in entry.tags if (slug := tag_slug(name))
    )
    counts.pop(tag.slug, None)
    for slug, count in counts.most_common():
        if page := store.tag_page(slug):
            if count / len(news) < SHIFT_MIN_SHARE:
                return None
            return Angle(page, _percent(count, len(news)))
    return None


def _level(value: float, low: float, high: float) -> str:
    return "high" if value >= high else "low" if value <= low else "average"


def tag_reading(store: NewsStore, tag: TagSummary) -> TagReading | None:
    """Critical reading of a Fil, or None if it is too small."""
    if tag.count < MIN_NEWS_FOR_READING:
        return None
    baseline = _baseline(store.indexes)

    neighbours: Counter[str] = Counter(
        slug
        for news in tag.news
        for name in news.tags
        if (slug := tag_slug(name)) != tag.slug
    )
    pages = [
        (page, count)
        for slug, count in neighbours.most_common()
        if (page := store.tag_page(slug))
    ]
    angles = [
        Angle(page, _percent(count, tag.count))
        for page, count in pages[:ANGLE_COUNT]
        if count / tag.count >= ANGLE_MIN_SHARE
    ]

    shift_start = baseline.latest - timedelta(days=SHIFT_DAYS)
    recent = [n for n in tag.news if n.created_at > shift_start]
    former = [n for n in tag.news if n.created_at <= shift_start]
    recent_angle = former_angle = None
    if len(recent) >= SHIFT_MIN_NEWS and len(former) >= SHIFT_MIN_NEWS:
        recent_angle = _main_angle(store, tag, recent)
        former_angle = _main_angle(store, tag, former)
        if (
            recent_angle is None
            or former_angle is None
            or recent_angle.tag.slug == former_angle.tag.slug
        ):
            recent_angle = former_angle = None

    debate = statistics.median(
        _debate(n) / baseline.month_debate[_news_month(n)] for n in tag.news
    )
    votes = statistics.median(
        n.score / baseline.month_votes[_news_month(n)] for n in tag.news
    )

    return TagReading(
        rhythm=_rhythm(tag, baseline),
        sources=_sources(tag, baseline.families),
        angles=angles,
        max_angle_share=_percent(pages[0][1], tag.count) if pages else 0,
        recent_angle=recent_angle,
        former_angle=former_angle,
        debate=_level(debate, DEBATE_LOW, DEBATE_HIGH),
        debate_factor=round(debate, 1),
        debate_percent=round(abs(1 - debate) * 100),
        votes=_level(votes, VOTES_LOW, VOTES_HIGH),
        votes_factor=round(votes, 1),
        votes_percent=round(abs(1 - votes) * 100),
    )
