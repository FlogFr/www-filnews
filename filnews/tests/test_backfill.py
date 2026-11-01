from datetime import UTC, datetime
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command

from filnews.archive import PAGE_SIZE, ArchiveError, ArcticShiftClient
from filnews.ingestion import backfill, select_backfill
from filnews.reddit import RedditClient

from .helpers import DataDirTestCase, reddit_post
from .test_ingestion import _response

MARCH = datetime(2019, 3, 1, tzinfo=UTC)
APRIL = datetime(2019, 4, 1, tzinfo=UTC)


def _page(*posts):
    return _response(payload={"data": [{"id": i, "created_utc": t} for i, t in posts]})


class ArcticShiftClientTests(DataDirTestCase):
    def test_paginates_from_last_timestamp_and_skips_duplicates(self):
        start = int(MARCH.timestamp())
        full_page = [(f"p{n}", start + n) for n in range(PAGE_SIZE)]
        session = mock.Mock(headers={})
        session.get.side_effect = [
            _page(*full_page),
            # Restarts at the last timestamp: p99 comes back once more.
            _page(full_page[-1], ("last", start + PAGE_SIZE)),
        ]
        ids = list(ArcticShiftClient("test", session).post_ids("france", MARCH, APRIL))

        self.assertEqual(len(ids), PAGE_SIZE + 1)
        self.assertEqual(ids[-1], "last")
        self.assertEqual(
            session.get.call_args.kwargs["params"]["after"], start + PAGE_SIZE - 1
        )

    @mock.patch("filnews.archive.time.sleep")
    def test_retries_when_rate_limited(self, sleep):
        session = mock.Mock(headers={})
        limited = _response(status=429)
        limited.headers = {"x-ratelimit-reset": "3"}
        timeout = _response(status=422)
        timeout.headers = {}
        session.get.side_effect = [limited, timeout, _page(("a", 1))]
        ids = list(ArcticShiftClient("test", session).post_ids("france", MARCH, APRIL))

        self.assertEqual(ids, ["a"])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [3, 2])


class BackfillTests(DataDirTestCase):
    def test_posts_by_id_batches_requests(self):
        session = mock.Mock(headers={})
        session.post.return_value = _response(
            payload={"access_token": "t", "expires_in": 3600}
        )
        session.get.return_value = _response(
            payload={"data": {"children": [{"data": {"id": "x"}}]}}
        )
        client = RedditClient(
            "id", "secret", "test", "", self.data_dir / "token.json", session
        )
        list(client.posts_by_id([f"p{n}" for n in range(150)]))

        self.assertEqual(session.get.call_count, 2)
        first = session.get.call_args_list[0].kwargs["params"]["id"].split(",")
        self.assertEqual((len(first), first[0]), (100, "t3_p0"))

    def test_backfill_keeps_unsorted_news_above_threshold(self):
        posts = [
            reddit_post("low", score=100, hours_ago=24 * 365 * 7),
            reddit_post("old", score=900, hours_ago=24 * 365 * 7),
            reddit_post("removed", score=900, removed_by_category="moderator"),
            reddit_post("ok", score=300),
        ]
        with self.store.transaction():
            report = backfill(posts, self.store, min_score=250)

        self.assertEqual((report.created, report.skipped), (2, 2))
        self.assertEqual({n.id for n in self.store.all()}, {"old", "ok"})

    def test_backfill_keeps_top_n_or_above_threshold(self):
        posts = [
            reddit_post("p40", score=40),
            reddit_post("img", score=900, url="https://i.redd.it/abc.jpg"),
            reddit_post("p90", score=90),
            reddit_post("p10", score=10),
            reddit_post("p300", score=300),
            reddit_post("p260", score=260),
        ]
        self.assertEqual(
            [p["id"] for p in select_backfill(posts, min_score=250, top=1)],
            ["p300", "p260"],  # Above the threshold: kept beyond the top 1.
        )
        with self.store.transaction():
            report = backfill(posts, self.store, min_score=250, top=4)
        self.assertEqual((report.created, report.skipped), (4, 2))
        self.assertEqual(
            {n.id for n in self.store.all()}, {"p300", "p260", "p90", "p40"}
        )

    def test_backfill_keeps_the_best_posts_of_each_day(self):
        march = [  # Three news on 4 March, one on 5 March, all below 250.
            reddit_post(
                f"d4-{score}",
                score=score,
                created_utc=MARCH.timestamp() + 3 * 86400 + 3600,
            )
            for score in (30, 20, 10)
        ] + [
            reddit_post("d5", score=5, created_utc=MARCH.timestamp() + 4 * 86400 + 3600)
        ]
        march.append(reddit_post("bad", score=900, url="https://[broken/"))

        kept = select_backfill(march, min_score=250, top=0, day_top=2)
        self.assertEqual([p["id"] for p in kept], ["d4-30", "d4-20", "d5"])
        kept = select_backfill(march, min_score=250, top=3, day_top=1)
        self.assertEqual([p["id"] for p in kept], ["d4-30", "d4-20", "d4-10", "d5"])
        # Floor: the best of a quiet day is not kept with too few votes.
        kept = select_backfill(march, min_score=250, top=0, day_top=2, day_min_score=20)
        self.assertEqual([p["id"] for p in kept], ["d4-30", "d4-20"])

    @mock.patch("filnews.management.commands.backfill_news.RedditClient")
    @mock.patch("filnews.management.commands.backfill_news.ArcticShiftClient")
    def test_command_dry_run_writes_nothing(self, archive, reddit):
        archive.from_settings.return_value.post_ids.return_value = ["a", "b"]
        reddit.from_settings.return_value.posts_by_id.return_value = [
            reddit_post("a", score=300),
            reddit_post("b", score=50),
        ]
        out = StringIO()
        call_command("backfill_news", "--from", "2019-03", "--dry-run", stdout=out)

        self.assertIn("2 article links", out.getvalue())
        self.assertIn(">= 250: 1", out.getvalue())
        self.assertIn(
            "kept (score >= 250 or top 60/month or top 2/day with score >= 20): 2, "
            "lowest score 50",
            out.getvalue(),
        )
        self.assertEqual(len(self.store), 0)

    @mock.patch("filnews.management.commands.backfill_news.RedditClient")
    @mock.patch("filnews.management.commands.backfill_news.ArcticShiftClient")
    def test_command_walks_each_month(self, archive, reddit):
        post_ids = archive.from_settings.return_value.post_ids
        post_ids.return_value = []
        reddit.from_settings.return_value.posts_by_id.return_value = []
        call_command(
            "backfill_news", "--from", "2019-11", "--to", "2020-02", stdout=StringIO()
        )

        months = [call.args[1].strftime("%Y-%m") for call in post_ids.call_args_list]
        self.assertEqual(months, ["2019-11", "2019-12", "2020-01", "2020-02"])

    @mock.patch("filnews.management.commands.backfill_news.RedditClient")
    @mock.patch("filnews.management.commands.backfill_news.ArcticShiftClient")
    def test_command_skips_failed_months_and_reports_them(self, archive, reddit):
        def post_ids(subreddit, start, end):
            if start.month == 12:
                raise ArchiveError("Arctic Shift search failed: too many retries.")
            return []

        archive.from_settings.return_value.post_ids.side_effect = post_ids
        reddit.from_settings.return_value.posts_by_id.return_value = []
        out, err = StringIO(), StringIO()
        with self.assertRaisesMessage(
            CommandError, "retry them with --from/--to: 2019-12"
        ):
            call_command(
                "backfill_news",
                "--from",
                "2019-11",
                "--to",
                "2020-01",
                stdout=out,
                stderr=err,
            )

        self.assertIn("2019-12: Arctic Shift search failed", err.getvalue())
        self.assertIn("2019-11 (", out.getvalue())
        self.assertIn("2020-01 (", out.getvalue())
