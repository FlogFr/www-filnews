from datetime import UTC, datetime
from statistics import median

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from filnews.archive import ArchiveError, ArcticShiftClient
from filnews.ingestion import backfill, is_news_post, select_backfill
from filnews.reddit import RedditClient, RedditError
from filnews.store import get_store

# Thresholds shown by --dry-run to help choose FILNEWS_MIN_SCORE for old years.
STAT_THRESHOLDS = (100, 150, 200, 250, 500, 1000)


def parse_month(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC)
    except ValueError as exc:
        raise CommandError(f"Invalid month '{value}' (expected YYYY-MM).") from exc


def next_month(moment: datetime) -> datetime:
    if moment.month == 12:
        return moment.replace(year=moment.year + 1, month=1)
    return moment.replace(month=moment.month + 1)


class Command(BaseCommand):
    help = (
        "Import the history of the subreddit month by month: post ids come from "
        "the Arctic Shift archive, current data from the Reddit API."
    )

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", required=True, help="YYYY-MM")
        parser.add_argument("--to", dest="end", help="YYYY-MM (default: --from)")
        parser.add_argument("--subreddit", default=settings.FILNEWS_SUBREDDIT)
        parser.add_argument(
            "--min-score",
            type=int,
            default=settings.FILNEWS_MIN_SCORE,
            help="Minimum upvotes (default: FILNEWS_MIN_SCORE).",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=settings.FILNEWS_BACKFILL_TOP,
            help=(
                "Also keep the N best articles of each month, whatever their "
                "score (default: FILNEWS_BACKFILL_TOP, 0 disables)."
            ),
        )
        parser.add_argument(
            "--day-top",
            type=int,
            default=settings.FILNEWS_BACKFILL_DAY_TOP,
            help=(
                "Also keep the N best articles of each day, whatever their "
                "score (default: FILNEWS_BACKFILL_DAY_TOP, 0 disables)."
            ),
        )
        parser.add_argument(
            "--day-min-score",
            type=int,
            default=settings.FILNEWS_BACKFILL_DAY_MIN_SCORE,
            help="Minimum score of the best articles of a day "
            "(default: FILNEWS_BACKFILL_DAY_MIN_SCORE).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print statistics (score distribution), write nothing.",
        )

    def handle(
        self,
        *args,
        start,
        end,
        subreddit,
        min_score,
        top,
        day_top,
        day_min_score,
        dry_run,
        **options,
    ):
        month = parse_month(start)
        last = parse_month(end) if end else month
        if last < month:
            raise CommandError("--to must not be before --from.")
        try:
            archive = ArcticShiftClient.from_settings()
            reddit = RedditClient.from_settings()
        except RedditError as exc:
            raise CommandError(str(exc)) from exc

        store = get_store()
        rule = (min_score, top, day_top, day_min_score)
        failed: list[str] = []
        while month <= last:
            label = month.strftime("%Y-%m")
            try:
                ids = list(archive.post_ids(subreddit, month, next_month(month)))
                posts = list(reddit.posts_by_id(ids))
            except (ArchiveError, RedditError) as exc:
                # A transient outage must not abort a multi-year import.
                self.stderr.write(f"{label}: {exc} Skipped.")
                failed.append(label)
                month = next_month(month)
                continue

            self.stdout.write(self._stats(label, ids, posts, rule))
            if not dry_run:
                # Network work is done: only the write holds the lock.
                with store.transaction():
                    report = backfill(posts, store, *rule)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{label} ({_describe(*rule)}): "
                        f"{report.created} new, "
                        f"{report.updated} updated, {report.duplicates} duplicates. "
                        f"Total: {len(store)} news."
                    )
                )
            month = next_month(month)

        if failed:
            raise CommandError(
                f"{len(failed)} month(s) failed, retry them with --from/--to: "
                + ", ".join(failed)
            )

    @staticmethod
    def _stats(
        label: str,
        ids: list[str],
        posts: list[dict],
        rule: tuple[int, int, int, int],
    ) -> str:
        links = [post for post in posts if is_news_post(post, 0)]
        scores = sorted(post["score"] for post in links)
        lines = [
            f"{label}: {len(ids)} archived posts, {len(posts)} known by Reddit, "
            f"{len(links)} article links.",
        ]
        if scores:
            p90 = scores[int(len(scores) * 0.9)]
            lines.append(
                f"  article scores: median {median(scores):g}, p90 {p90}, "
                f"max {scores[-1]}"
            )
        counts = ", ".join(
            f">= {threshold}: {sum(score >= threshold for score in scores)}"
            for threshold in STAT_THRESHOLDS
        )
        lines.append(f"  article links by threshold: {counts}")
        kept = select_backfill(links, *rule)
        lowest = f", lowest score {min(p['score'] for p in kept)}" if kept else ""
        lines.append(f"  kept ({_describe(*rule)}): {len(kept)}{lowest}")
        return "\n".join(lines)


def _describe(min_score: int, top: int, day_top: int, day_min_score: int) -> str:
    return (
        f"score >= {min_score} or top {top}/month "
        f"or top {day_top}/day with score >= {day_min_score}"
    )
