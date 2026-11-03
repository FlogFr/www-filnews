import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from filnews.analysis import ANALYZERS, get_analyzer
from filnews.models import News
from filnews.store import get_store

logger = logging.getLogger(__name__)

# Results are written by batches: one JSON write per batch, not per news.
SAVE_EVERY = 25
# Concurrent downloads allowed on the same site (politeness).
PER_DOMAIN = 2


class Command(BaseCommand):
    help = "Tag, summarize and generate a thumbnail for news not analyzed yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--analyzer",
            choices=ANALYZERS,
            help="Analysis backend (default: FILNEWS_ANALYZER).",
        )
        parser.add_argument(
            "--force", action="store_true", help="Re-analyze already analyzed news."
        )
        parser.add_argument(
            "--retag",
            action="store_true",
            help="Only recompute the tags of every news (or of the selected "
            "ones) from the stored data, without downloading anything.",
        )
        parser.add_argument(
            "--days", type=int, help="Only news created in the last N days."
        )
        parser.add_argument("--limit", type=int, help="Analyze at most N news.")
        parser.add_argument(
            "--workers",
            type=int,
            default=settings.FILNEWS_ANALYZE_WORKERS,
            help="Parallel downloads (default: FILNEWS_ANALYZE_WORKERS; "
            "the local models always use 1).",
        )
        parser.add_argument("ids", nargs="*", help="Only these Reddit post ids.")

    def handle(
        self, *args, analyzer, force, retag, days, limit, workers, ids, **options
    ):
        try:
            backend = get_analyzer(analyzer)
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        if backend.name != "heuristic":
            workers = 1  # Models are heavy: one instance, no threads.

        store = get_store()
        since = datetime.now(UTC) - timedelta(days=days) if days else None
        if ids:
            pending = [news for news in map(store.get, ids) if news]
        else:
            pending = store.to_analyze(force=force or retag, since=since)
        pending = pending[:limit] if limit else pending
        if retag:
            self._retag(store, backend, pending)
            return

        self.stdout.write(
            f"Analyzing {len(pending)} news with '{backend.name}' "
            f"({max(workers, 1)} worker{'s' if workers > 1 else ''})…"
        )
        analyze = _ThreadedAnalysis(backend, analyzer)
        batch: list[News] = []
        failures = 0
        # Network-bound work happens outside the lock; only the writes are
        # serialized, so ingestion can run at the same time.
        executor = ThreadPoolExecutor(max_workers=max(workers, 1))
        try:
            futures = {executor.submit(analyze, news): news for news in pending}
            for index, future in enumerate(as_completed(futures), start=1):
                news = futures[future]
                try:
                    analyzed = future.result()
                except Exception:
                    failures += 1
                    logger.exception("Analysis failed for %s", news.id)
                    continue
                batch.append(analyzed)
                self.stdout.write(
                    f"[{index}/{len(pending)}] {news.title[:70]} -> "
                    f"{', '.join(analyzed.tags) or 'no tags'}"
                )
                if len(batch) >= SAVE_EVERY:
                    _save(store, batch)
        finally:
            # Also on Ctrl-C: what is already analyzed is kept.
            executor.shutdown(wait=False, cancel_futures=True)
            _save(store, batch)

        message = "Analysis done."
        if failures:
            message += f" {failures} failure{'s' if failures > 1 else ''}, see logs."
        self.stdout.write(self.style.SUCCESS(message))

    def _retag(self, store, backend, pending: list[News]) -> None:
        # The heuristic vocabulary is enough here: no model, no network.
        retagger = get_analyzer("heuristic") if backend.name != "heuristic" else backend
        with store.transaction():
            changed = sum(
                store.set_tags(news.id, retagger.retag(news))
                for news in pending
                if store.get(news.id)
            )
        self.stdout.write(
            self.style.SUCCESS(f"Retagged {len(pending)} news, {changed} changed.")
        )


def _save(store, batch: list[News]) -> None:
    if not batch:
        return
    with store.transaction():
        for analyzed in batch:
            if store.get(analyzed.id):  # May have been removed as a duplicate.
                store.set_analysis(analyzed)
    batch.clear()


class _ThreadedAnalysis:
    """Callable run by the workers: one analyzer (HTTP session) per thread."""

    def __init__(self, backend, analyzer_name: str | None):
        self.backend = backend
        self.analyzer_name = analyzer_name
        self.local = threading.local()
        self.slots_lock = threading.Lock()
        self.slots: dict[str, threading.Semaphore] = defaultdict(
            lambda: threading.BoundedSemaphore(PER_DOMAIN)
        )

    def __call__(self, news: News) -> News:
        backend = getattr(self.local, "backend", None)
        if backend is None:
            is_main = self.backend.name != "heuristic"
            backend = self.backend if is_main else get_analyzer(self.analyzer_name)
            self.local.backend = backend
        with self.slots_lock:
            slot = self.slots[news.domain]
        with slot:
            return backend.analyze(replace(news))
