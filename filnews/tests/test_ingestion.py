import json
from datetime import timedelta
from unittest import mock

from filnews.ingestion import ingest, is_news_post, post_to_news
from filnews.reddit import RedditClient

from .helpers import NOW, DataDirTestCase, reddit_post


class IngestionTests(DataDirTestCase):
    def test_only_posts_above_threshold_are_ingested(self):
        posts = [
            reddit_post("p1", score=450),
            reddit_post("p2", score=100),
            reddit_post("p3", score=70),  # Below the threshold: stops there.
            reddit_post("p4", score=500),  # Never reached (listing is sorted).
        ]
        with self.store.transaction():
            report = ingest(
                posts, self.store, min_score=100, since=NOW - timedelta(days=1)
            )
        self.assertEqual(report.created, 2)
        self.assertEqual({n.id for n in self.store.all()}, {"p1", "p2"})

    def test_skips_old_and_non_news_posts(self):
        posts = [
            reddit_post("old", score=900, hours_ago=30),
            reddit_post("self", score=800, is_self=True),
            reddit_post("img", score=700, url="https://i.redd.it/abc.jpg"),
            reddit_post("nsfw", score=600, over_18=True),
            reddit_post("ok", score=500),
        ]
        with self.store.transaction():
            report = ingest(
                posts, self.store, min_score=100, since=NOW - timedelta(days=1)
            )
        self.assertEqual(report.skipped, 4)
        self.assertEqual([n.id for n in self.store.all()], ["ok"])

    def test_reingesting_updates_score(self):
        since = NOW - timedelta(days=1)
        with self.store.transaction():
            ingest([reddit_post("p1", score=150)], self.store, 100, since)
        with self.store.transaction():
            report = ingest([reddit_post("p1", score=600)], self.store, 100, since)
        self.assertEqual((report.created, report.updated), (0, 1))
        self.assertEqual(self.store.get("p1").score, 600)

    def test_post_to_news_mapping(self):
        news = post_to_news(
            reddit_post(
                "p1",
                score=300,
                url="https://www.lemonde.fr/x.html",
                preview={
                    "images": [{"source": {"url": "https://preview.redd.it/x.jpg"}}]
                },
            )
        )
        self.assertEqual(news.domain, "lemonde.fr")
        self.assertEqual(news.flair, "Politique")
        self.assertEqual(news.reddit_thumbnail, "https://preview.redd.it/x.jpg")
        self.assertEqual(
            news.reddit_url, "https://www.reddit.com/r/france/comments/p1/post/"
        )
        self.assertFalse(is_news_post(reddit_post("x", score=99), min_score=100))
        for url in (
            "https://twitter.com/user/status/1",
            "https://x.com/user/status/1",
            "https://www.youtube.com/watch?v=abc",
            "https://youtu.be/abc",
        ):
            self.assertFalse(is_news_post(reddit_post("x", score=900, url=url), 100))


def _response(status=200, payload=None):
    response = mock.Mock(status_code=status)
    response.json.return_value = payload or {}
    return response


class RedditClientTests(DataDirTestCase):
    def reddit(self, session):
        return RedditClient(
            client_id="id",
            client_secret="secret",
            user_agent="test",
            redirect_uri="http://localhost:8000/auth/reddit/callback",
            token_file=self.data_dir / ".secrets" / "token.json",
            session=session,
        )

    def test_top_posts_paginates_with_client_credentials(self):
        session = mock.Mock(headers={})
        session.post.return_value = _response(
            payload={"access_token": "t", "expires_in": 3600}
        )
        session.get.side_effect = [
            _response(
                payload={"data": {"children": [{"data": {"id": "a"}}], "after": "t3_a"}}
            ),
            _response(
                payload={"data": {"children": [{"data": {"id": "b"}}], "after": None}}
            ),
        ]
        posts = list(self.reddit(session).top_posts("france", "day"))

        self.assertEqual([p["id"] for p in posts], ["a", "b"])
        self.assertEqual(
            session.post.call_args.kwargs["data"], {"grant_type": "client_credentials"}
        )
        self.assertEqual(session.post.call_count, 1)  # Token is cached.
        self.assertEqual(session.get.call_args.kwargs["params"]["after"], "t3_a")

    def test_authorization_code_flow_stores_refresh_token(self):
        session = mock.Mock(headers={})
        session.post.return_value = _response(
            payload={"access_token": "t", "refresh_token": "r", "expires_in": 3600}
        )
        client = self.reddit(session)
        self.assertIn(
            "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Freddit%2Fcallback",
            client.authorize_url("s"),
        )

        client.exchange_code("code")
        token_file = self.data_dir / ".secrets" / "token.json"
        self.assertEqual(json.loads(token_file.read_text()), {"refresh_token": "r"})
        self.assertEqual(token_file.stat().st_mode & 0o777, 0o600)

        # A new client now uses the refresh token.
        fresh = self.reddit(session)
        fresh.access_token()
        self.assertEqual(
            session.post.call_args.kwargs["data"],
            {"grant_type": "refresh_token", "refresh_token": "r"},
        )
