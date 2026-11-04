"""File-based news database.

News are stored as JSON, one file per month (`data/news/YYYY-MM.json`), which
keeps files small and git diffs readable. The whole dataset is loaded in memory
at bootstrap and transparently reloaded when a file changes on disk (e.g. when
an ingestion command runs while the dev server is up).

Writes are atomic (temp file + rename) and serialized across processes with an
exclusive lock on `data/.lock`.

Two rules keep the data clean:
- one news per article: a post linking to an already known URL (see
  `canonical_url`) is a duplicate, only the best scored post is kept;
- tag aliases (`data/tag_aliases.json`, edited by hand) are applied when
  loading and when storing an analysis.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from django.conf import settings
from django.utils import timezone

from .models import News, TagSummary, tag_slug

ALIASES_FILE = "tag_aliases.json"
# Query parameters that only track the visitor: ignored to compare URLs.
TRACKING_PARAMS = ("utm_", "xtor", "fbclid", "gclid", "at_", "amp")
# `related()` only looks at the news closest in time within each tag: cheap
# even for tags with thousands of news, and recent context is what matters.
RELATED_WINDOW = 150


class UpsertResult(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DUPLICATE = "duplicate"  # Same article as a better scored news: ignored.


def canonical_url(url: str) -> str:
    """URL reduced to what identifies the article (no scheme, www, tracking)."""
    parts = urlparse(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path = parts.path.rstrip("/").removesuffix("/amp") or "/"
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query)
        if not key.lower().startswith(TRACKING_PARAMS)
    )
    return f"{host}{path}?{urlencode(query)}" if query else f"{host}{path}"


def apply_aliases(tags: Iterable[str], aliases: dict[str, str]) -> list[str]:
    """Replace aliased tags by their canonical name, without duplicates."""
    result: list[str] = []
    seen: set[str] = set()
    for name in tags:
        name = aliases.get(tag_slug(name), name)
        slug = tag_slug(name)
        if slug not in seen:
            seen.add(slug)
            result.append(name)
    return result


class NewsStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.news_dir = self.data_dir / "news"
        self.aliases_file = self.data_dir / ALIASES_FILE
        self._lock = threading.RLock()
        self._news: dict[str, News] = {}
        self._by_url: dict[str, str] = {}
        self.aliases: dict[str, str] = {}
        self._signature: dict[str, int] = {}
        self._dirty_months: set[str] = set()
        self._indexes: _Indexes | None = None
        self.load()

    # --- Persistence -------------------------------------------------------

    def _files(self) -> list[Path]:
        if not self.news_dir.is_dir():
            return []
        return sorted(self.news_dir.glob("*.json"))

    def _current_signature(self) -> dict[str, int]:
        signature = {path.name: path.stat().st_mtime_ns for path in self._files()}
        if self.aliases_file.is_file():
            signature[ALIASES_FILE] = self.aliases_file.stat().st_mtime_ns
        return signature

    def _load_aliases(self) -> dict[str, str]:
        """`{"Macron": "Emmanuel Macron"}` -> `{"macron": "Emmanuel Macron"}`."""
        if not self.aliases_file.is_file():
            return {}
        raw = json.loads(self.aliases_file.read_text(encoding="utf-8"))
        return {tag_slug(alias): name for alias, name in raw.items()}

    def load(self) -> None:
        with self._lock:
            news: dict[str, News] = {}
            signature = self._current_signature()
            self.aliases = self._load_aliases()
            for path in self._files():
                raw = json.loads(path.read_text(encoding="utf-8"))
                for item in raw:
                    entry = News.from_dict(item)
                    entry.tags = apply_aliases(entry.tags, self.aliases)
                    news[entry.id] = entry
            self._news = news
            self._by_url = {canonical_url(n.url): n.id for n in news.values()}
            self._signature = signature
            self._dirty_months.clear()
            self._invalidate()

    def refresh_if_changed(self) -> bool:
        """Reload from disk if another process modified the files."""
        with self._lock:
            if self._current_signature() == self._signature:
                return False
            self.load()
            return True

    def save(self) -> None:
        with self._lock:
            self.news_dir.mkdir(parents=True, exist_ok=True)
            by_month: dict[str, list[News]] = defaultdict(list)
            for entry in self._news.values():
                if entry.month_key in self._dirty_months:
                    by_month[entry.month_key].append(entry)
            for month in self._dirty_months:
                entries = sorted(
                    by_month.get(month, []), key=lambda n: (n.created_at, n.id)
                )
                payload = [entry.to_dict() for entry in reversed(entries)]
                _atomic_write_json(self.news_dir / f"{month}.json", payload)
            self._dirty_months.clear()
            self._signature = self._current_signature()

    @contextmanager
    def transaction(self) -> Iterator[NewsStore]:
        """Lock the data dir, reload, let the caller mutate, then save."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with (self.data_dir / ".lock").open("w") as lock_file, self._lock:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                self.refresh_if_changed()
                yield self
                self.save()
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    # --- Mutations ---------------------------------------------------------

    def upsert(self, entry: News) -> UpsertResult:
        """Insert or update a news item.

        Updating keeps the analysis results and only refreshes Reddit data. A
        new post linking to a known article replaces the known news only if
        it has a better score (and inherits its analysis), otherwise it is
        ignored.
        """
        with self._lock:
            existing = self._news.get(entry.id)
            if existing is not None:
                existing.title = entry.title
                existing.score = entry.score
                existing.num_comments = entry.num_comments
                existing.flair = entry.flair
                existing.reddit_thumbnail = entry.reddit_thumbnail
                self._mark_dirty(existing)
                return UpsertResult.UPDATED

            url = canonical_url(entry.url)
            twin = self._news.get(self._by_url.get(url, ""))
            if twin is not None:
                if twin.score >= entry.score:
                    return UpsertResult.DUPLICATE
                entry.tags, entry.summary = twin.tags, twin.summary
                entry.thumbnail, entry.analyzed_at = twin.thumbnail, twin.analyzed_at
                del self._news[twin.id]
                self._mark_dirty(twin)
            self._news[entry.id] = entry
            self._by_url[url] = entry.id
            self._mark_dirty(entry)
            return UpsertResult.CREATED

    def remove(self, news_id: str) -> bool:
        """Delete a news and its thumbnail. Returns False if it was unknown."""
        with self._lock:
            entry = self._news.pop(news_id, None)
            if entry is None:
                return False
            if self._by_url.get(canonical_url(entry.url)) == news_id:
                del self._by_url[canonical_url(entry.url)]
            if entry.thumbnail:
                (Path(settings.MEDIA_ROOT) / entry.thumbnail).unlink(missing_ok=True)
            self._mark_dirty(entry)
            return True

    def set_analysis(self, analyzed: News) -> None:
        """Copy analysis results onto the stored news (keeps fresh Reddit data)."""
        with self._lock:
            entry = self._news[analyzed.id]
            entry.tags = apply_aliases(analyzed.tags, self.aliases)
            entry.summary = analyzed.summary
            entry.thumbnail = analyzed.thumbnail
            entry.analyzed_at = analyzed.analyzed_at
            self._mark_dirty(entry)

    def set_tags(self, news_id: str, tags: list[str]) -> bool:
        """Replace the tags of a news. Returns True if they changed."""
        with self._lock:
            entry = self._news[news_id]
            tags = apply_aliases(tags, self.aliases)
            if entry.tags == tags:
                return False
            entry.tags = tags
            self._mark_dirty(entry)
            return True

    def _mark_dirty(self, entry: News) -> None:
        self._dirty_months.add(entry.month_key)
        self._invalidate()

    def _invalidate(self) -> None:
        self._indexes = None

    # --- Queries -----------------------------------------------------------

    @property
    def indexes(self) -> _Indexes:
        with self._lock:
            if self._indexes is None:
                self._indexes = _Indexes(list(self._news.values()))
            return self._indexes

    def __len__(self) -> int:
        return len(self._news)

    def all(self) -> list[News]:
        """All news, newest first."""
        return self.indexes.by_date

    def get(self, news_id: str) -> News | None:
        return self._news.get(news_id)

    def get_by_slug(self, slug: str) -> News | None:
        return self.indexes.by_slug.get(slug)

    def most_popular(self, since: datetime) -> News | None:
        candidates = [n for n in self.all() if n.created_at >= since]
        return max(candidates, key=lambda n: n.score, default=None)

    def latest(self, limit: int, exclude: Iterable[str] = ()) -> list[News]:
        excluded = set(exclude)
        return [n for n in self.all() if n.id not in excluded][:limit]

    def tags(self) -> list[TagSummary]:
        """All tags, most recently used first."""
        return self.indexes.tags

    def tag(self, slug: str) -> TagSummary | None:
        return self.indexes.tags_by_slug.get(slug)

    def page_tags(self) -> list[TagSummary]:
        """Tags that have their own page (enough news), most recent first."""
        return self.indexes.page_tags

    def tag_page(self, slug: str) -> TagSummary | None:
        tag = self.tag(slug)
        return tag if tag and tag.count >= settings.FILNEWS_TAG_MIN_NEWS else None

    def recent_tags(self, limit: int) -> list[TagSummary]:
        return self.page_tags()[:limit]

    def months(self) -> list[tuple[int, int, int]]:
        """(year, month, news count) of every month with news, newest first."""
        return [
            (year, month, len(items))
            for (year, month), items in self.indexes.by_month.items()
        ]

    def month(self, year: int, month: int) -> list[News]:
        """News of a month (local time), newest first."""
        return self.indexes.by_month.get((year, month), [])

    def same_day(self, news: News) -> list[News]:
        """News of the same (local) day as `news`, newest first."""
        return self.indexes.by_day.get(timezone.localdate(news.created_at), [])

    def related(self, news: News, limit: int) -> list[News]:
        """Other news sharing tags with `news`, most shared tags then newest."""
        shared: Counter[str] = Counter()
        for name in news.tags:
            slug = tag_slug(name)
            tag = self.tag(slug)
            if tag is None:
                continue
            index = self.indexes.positions[slug][news.id]
            start = max(index - RELATED_WINDOW, 0)
            for other in tag.news[start : index + RELATED_WINDOW + 1]:
                if other.id != news.id:
                    shared[other.id] += 1
        ranked = sorted(
            shared,
            key=lambda news_id: (shared[news_id], self._news[news_id].created_at),
            reverse=True,
        )
        return [self._news[news_id] for news_id in ranked[:limit]]

    def to_analyze(self, force: bool = False, since: datetime | None = None):
        return [
            n
            for n in self.all()
            if (force or n.analyzed_at is None)
            and (since is None or n.created_at >= since)
        ]


class _Indexes:
    """Derived read-only views, rebuilt lazily after each mutation."""

    def __init__(self, news: list[News]):
        self.by_date = sorted(news, key=lambda n: (n.created_at, n.id), reverse=True)
        self.by_slug = {n.slug: n for n in self.by_date}

    @cached_property
    def tags(self) -> list[TagSummary]:
        grouped: dict[str, list[News]] = defaultdict(list)
        names: dict[str, Counter[str]] = defaultdict(Counter)
        for entry in self.by_date:
            for name in entry.tags:
                slug = tag_slug(name)
                if not slug:
                    continue
                if not grouped[slug] or grouped[slug][-1] is not entry:
                    grouped[slug].append(entry)
                names[slug][name] += 1
        summaries = [
            TagSummary(name=names[slug].most_common(1)[0][0], slug=slug, news=items)
            for slug, items in grouped.items()
        ]
        summaries.sort(key=lambda t: (t.last_seen, t.count), reverse=True)
        return summaries

    @cached_property
    def tags_by_slug(self) -> dict[str, TagSummary]:
        return {tag.slug: tag for tag in self.tags}

    @cached_property
    def page_tags(self) -> list[TagSummary]:
        minimum = settings.FILNEWS_TAG_MIN_NEWS
        return [tag for tag in self.tags if tag.count >= minimum]

    @cached_property
    def positions(self) -> dict[str, dict[str, int]]:
        """Index of each news inside the (newest first) list of each tag."""
        return {
            tag.slug: {entry.id: index for index, entry in enumerate(tag.news)}
            for tag in self.tags
        }

    @cached_property
    def by_month(self) -> dict[tuple[int, int], list[News]]:
        months: dict[tuple[int, int], list[News]] = {}
        for entry in self.by_date:
            local = timezone.localtime(entry.created_at)
            months.setdefault((local.year, local.month), []).append(entry)
        return months

    @cached_property
    def by_day(self) -> dict[date, list[News]]:
        days: dict[date, list[News]] = defaultdict(list)
        for entry in self.by_date:
            days[timezone.localdate(entry.created_at)].append(entry)
        return days


def _atomic_write_json(path: Path, payload: object) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


_stores: dict[Path, NewsStore] = {}
_stores_lock = threading.Lock()


def get_store(refresh: bool = True) -> NewsStore:
    """Return the process-wide store for the configured DATA_DIR.

    The first call loads every JSON file; later calls only check whether the
    files changed on disk (unless `refresh` is False: template filters called
    many times per page).
    """
    data_dir = Path(settings.DATA_DIR).resolve()
    with _stores_lock:
        store = _stores.get(data_dir)
        if store is None:
            store = _stores[data_dir] = NewsStore(data_dir)
            return store
    if refresh:
        store.refresh_if_changed()
    return store
