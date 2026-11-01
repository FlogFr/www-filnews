from datetime import UTC, datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from filnews.ingestion import PERIODS, ingest
from filnews.reddit import RedditClient, RedditError
from filnews.store import get_store


class Command(BaseCommand):
    help = (
        "Ingest the most upvoted posts of the subreddit. "
        "Default: the last 24 hours; use --period month for the last month."
    )

    def add_arguments(self, parser):
        parser.add_argument("--period", choices=PERIODS, default="day")
        parser.add_argument("--subreddit", default=settings.FILNEWS_SUBREDDIT)
        parser.add_argument(
            "--min-score",
            type=int,
            default=settings.FILNEWS_MIN_SCORE,
            help="Minimum upvotes (default: FILNEWS_MIN_SCORE).",
        )

    def handle(self, *args, period, subreddit, min_score, **options):
        try:
            client = RedditClient.from_settings()
        except RedditError as exc:
            raise CommandError(str(exc)) from exc

        since = datetime.now(UTC) - PERIODS[period]
        store = get_store()
        try:
            with store.transaction():
                report = ingest(
                    client.top_posts(subreddit, period), store, min_score, since
                )
        except RedditError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"r/{subreddit} ({period}, score >= {min_score}): "
                f"{report.created} new, {report.updated} updated, "
                f"{report.duplicates} duplicates, {report.skipped} skipped. "
                f"Total: {len(store)} news."
            )
        )
