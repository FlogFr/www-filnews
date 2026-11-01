import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from filnews.models import News
from filnews.store import NewsStore, get_store

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def make_news(news_id: str, hours_ago: float = 1, score: int = 150, **fields) -> News:
    values = {
        "id": news_id,
        "title": f"Titre de la news {news_id}",
        "url": f"https://example.org/articles/{news_id}",
        "permalink": f"/r/france/comments/{news_id}/titre/",
        "created_at": NOW - timedelta(hours=hours_ago),
        "score": score,
        "domain": "example.org",
    }
    values.update(fields)
    return News(**values)


def reddit_post(post_id: str, score: int, hours_ago: float = 1, **fields) -> dict:
    post = {
        "id": post_id,
        "title": f"Post {post_id}",
        "url": f"https://www.lemonde.fr/{post_id}.html",
        "permalink": f"/r/france/comments/{post_id}/post/",
        "created_utc": (NOW - timedelta(hours=hours_ago)).timestamp(),
        "score": score,
        "num_comments": 12,
        "subreddit": "france",
        "author": "someone",
        "link_flair_text": "Politique",
        "is_self": False,
        "over_18": False,
        "stickied": False,
    }
    post.update(fields)
    return post


class DataDirTestCase(SimpleTestCase):
    """Each test gets its own empty data directory."""

    def setUp(self):
        super().setUp()
        self.data_dir = Path(tempfile.mkdtemp(prefix="filnews-test-"))
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)
        overrides = override_settings(
            DATA_DIR=self.data_dir, MEDIA_ROOT=self.data_dir / "media"
        )
        overrides.enable()
        self.addCleanup(overrides.disable)

    @property
    def store(self) -> NewsStore:
        return get_store()

    def add_news(self, *entries: News) -> None:
        with self.store.transaction():
            for entry in entries:
                self.store.upsert(entry)
