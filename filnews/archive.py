"""Client for the Arctic Shift archive of Reddit (historical post ids).

The Reddit API listings stop around 1000 items, so they cannot reach posts that
are several years old. Arctic Shift (https://arctic-shift.photon-reddit.com)
archives every post of a subreddit; we only use it to *discover* post ids for
a date range. The actual data (current score, removal status…) is then fetched
from the official Reddit API (`RedditClient.posts_by_id`), because archived
scores were captured shortly after posting and are underestimated.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SEARCH_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
PAGE_SIZE = 100
MAX_RETRIES = 5


class ArchiveError(RuntimeError):
    pass


class ArcticShiftClient:
    def __init__(self, user_agent: str, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent

    @classmethod
    def from_settings(cls, session: requests.Session | None = None):
        return cls(user_agent=settings.REDDIT_USER_AGENT, session=session)

    def post_ids(self, subreddit: str, start: datetime, end: datetime) -> Iterator[str]:
        """Yield the id of every post created in [start, end), oldest first."""
        after = int(start.timestamp())
        before = int(end.timestamp())
        seen: set[str] = set()
        while after < before:
            page = self._search(
                {
                    "subreddit": subreddit,
                    "after": after,
                    "before": before,
                    "limit": PAGE_SIZE,
                    "sort": "asc",
                    "fields": "id,created_utc",
                }
            )
            fresh = [post for post in page if post["id"] not in seen]
            if not fresh:
                return
            for post in fresh:
                seen.add(post["id"])
                yield post["id"]
            if len(page) < PAGE_SIZE:
                return
            # Restart from the last timestamp (not after it): several posts may
            # share the same second; duplicates are filtered by `seen`.
            after = int(page[-1]["created_utc"])

    def _search(self, params: dict) -> list[dict]:
        for attempt in range(MAX_RETRIES):
            response = self.session.get(
                SEARCH_URL, params=params, timeout=settings.HTTP_TIMEOUT
            )
            # 422 is what Arctic Shift answers on a server-side timeout.
            if response.status_code in {422, 429} or response.status_code >= 500:
                delay = int(response.headers.get("x-ratelimit-reset", 0)) or 2**attempt
                logger.warning(
                    "Arctic Shift %s, retrying in %ss", response.status_code, delay
                )
                time.sleep(min(delay, 60))
                continue
            if response.status_code != 200:
                raise ArchiveError(
                    f"Arctic Shift search failed ({response.status_code})."
                )
            payload = response.json()
            if payload.get("error"):
                raise ArchiveError(f"Arctic Shift search failed: {payload['error']}")
            return payload.get("data") or []
        raise ArchiveError("Arctic Shift search failed: too many retries.")
