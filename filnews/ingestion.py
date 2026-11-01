"""Turn Reddit posts into News and store them."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from django.utils import timezone

from .models import News
from .store import NewsStore, UpsertResult

logger = logging.getLogger(__name__)

# Ingestion window for each Reddit `t=` period.
PERIODS = {
    "day": timedelta(hours=24),
    "week": timedelta(days=7),
    "month": timedelta(days=31),
}

# Links that are not news articles (images, videos, Reddit itself).
EXCLUDED_DOMAINS = {
    "reddit.com",
    "i.redd.it",
    "v.redd.it",
    "imgur.com",
    "i.imgur.com",
    # Tweets and videos: no article to summarize.
    "twitter.com",
    "mobile.twitter.com",
    "x.com",
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
}


@dataclass
class IngestionReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates: int = 0


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _preview_image(post: dict[str, Any]) -> str:
    try:
        return post["preview"]["images"][0]["source"]["url"]
    except (KeyError, IndexError, TypeError):
        thumbnail = post.get("thumbnail") or ""
        return thumbnail if thumbnail.startswith("https://") else ""


def is_news_post(post: dict[str, Any], min_score: int) -> bool:
    if post.get("score", 0) < min_score:
        return False
    if post.get("is_self") or post.get("over_18") or post.get("stickied"):
        return False
    # Removed by the moderators, Reddit or its author (old posts via /api/info).
    if post.get("removed_by_category"):
        return False
    url = post.get("url_overridden_by_dest") or post.get("url") or ""
    try:
        if urlparse(url).scheme not in {"http", "https"}:
            return False
        return _domain(url) not in EXCLUDED_DOMAINS
    except ValueError:  # Malformed URL (e.g. "Invalid IPv6 URL").
        return False


def post_to_news(post: dict[str, Any]) -> News:
    url = post.get("url_overridden_by_dest") or post["url"]
    return News(
        id=post["id"],
        title=post["title"].strip(),
        url=url,
        permalink=post["permalink"],
        created_at=datetime.fromtimestamp(post["created_utc"], tz=UTC),
        score=int(post["score"]),
        num_comments=int(post.get("num_comments", 0)),
        subreddit=post.get("subreddit", ""),
        author=post.get("author", ""),
        flair=(post.get("link_flair_text") or "").strip(),
        domain=_domain(url),
        selftext=post.get("selftext", ""),
        reddit_thumbnail=_preview_image(post),
    )


def ingest(
    posts: Iterable[dict[str, Any]],
    store: NewsStore,
    min_score: int,
    since: datetime,
) -> IngestionReport:
    """Store every news-worthy post created after `since`.

    `posts` must be sorted by score, descending (Reddit `top` listing): the
    iteration stops at the first post under the threshold.
    """
    report = IngestionReport()
    for post in posts:
        if post.get("score", 0) < min_score:
            break
        created_at = datetime.fromtimestamp(post["created_utc"], tz=UTC)
        if created_at < since:
            report.skipped += 1
            continue
        _store_post(post, store, min_score, report)
    logger.info(
        "Ingestion: %s created, %s updated, %s skipped",
        report.created,
        report.updated,
        report.skipped,
    )
    return report


def select_backfill(
    posts: Iterable[dict[str, Any]],
    min_score: int,
    top: int,
    day_top: int = 0,
    day_min_score: int = 0,
) -> list[dict[str, Any]]:
    """News-worthy posts of one month: score >= `min_score`, or among the `top`
    best of the month, or among the `day_top` best of their day (local time)
    if they have at least `day_min_score` votes (quiet days of old years had
    posts with no vote at all).

    Scores grew a lot with the subreddit, so a fixed threshold keeps almost
    nothing in old years: the minimums guarantee news every day and enough
    per month, while recent months keep everything above the usual threshold.
    """
    links = sorted(
        (post for post in posts if is_news_post(post, 0)),
        key=lambda post: post["score"],
        reverse=True,
    )
    per_day: dict[date, int] = {}
    selected = []
    for rank, post in enumerate(links):
        day = timezone.localtime(
            datetime.fromtimestamp(post["created_utc"], tz=UTC)
        ).date()
        day_rank = per_day.get(day, 0)
        per_day[day] = day_rank + 1
        best_of_day = day_rank < day_top and post["score"] >= day_min_score
        if post["score"] >= min_score or rank < top or best_of_day:
            selected.append(post)
    return selected


def backfill(
    posts: Iterable[dict[str, Any]],
    store: NewsStore,
    min_score: int,
    top: int = 0,
    day_top: int = 0,
    day_min_score: int = 0,
) -> IngestionReport:
    """Store the posts of one month kept by `select_backfill` (historical import)."""
    posts = list(posts)
    selected = select_backfill(posts, min_score, top, day_top, day_min_score)
    report = IngestionReport(skipped=len(posts) - len(selected))
    for post in selected:
        _store_post(post, store, 0, report)
    return report


def _store_post(
    post: dict[str, Any], store: NewsStore, min_score: int, report: IngestionReport
) -> None:
    if not is_news_post(post, min_score):
        report.skipped += 1
        return
    result = store.upsert(post_to_news(post))
    if result is UpsertResult.CREATED:
        report.created += 1
    elif result is UpsertResult.UPDATED:
        report.updated += 1
    else:
        report.duplicates += 1
