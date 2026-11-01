import json
import os
from datetime import UTC, datetime

from filnews.store import NewsStore, UpsertResult, apply_aliases, canonical_url

from .helpers import NOW, DataDirTestCase, make_news


class NewsStoreTests(DataDirTestCase):
    def test_saves_one_file_per_month_and_reloads(self):
        self.add_news(
            make_news("a", hours_ago=1),
            make_news("b", created_at=datetime(2026, 9, 15, tzinfo=UTC)),
        )
        files = sorted(p.name for p in (self.data_dir / "news").iterdir())
        self.assertEqual(files, ["2026-09.json", "2026-10.json"])

        reloaded = NewsStore(self.data_dir)
        self.assertEqual([n.id for n in reloaded.all()], ["a", "b"])
        self.assertEqual(
            reloaded.get("b").created_at, datetime(2026, 9, 15, tzinfo=UTC)
        )

    def test_upsert_refreshes_reddit_data_but_keeps_analysis(self):
        self.add_news(make_news("a", score=120, tags=["Paris"], summary="Résumé"))
        with self.store.transaction():
            result = self.store.upsert(make_news("a", score=900))
        self.assertEqual(result, UpsertResult.UPDATED)
        entry = self.store.get("a")
        self.assertEqual(entry.score, 900)
        self.assertEqual(entry.tags, ["Paris"])
        self.assertEqual(entry.summary, "Résumé")

    def test_get_store_reloads_when_files_change_on_disk(self):
        self.add_news(make_news("a"))
        path = self.data_dir / "news" / "2026-10.json"
        payload = json.loads(path.read_text())
        payload.append(make_news("z", hours_ago=3).to_dict())
        path.write_text(json.dumps(payload))
        os.utime(path, ns=(1, 1))  # Guarantee a different mtime.

        self.assertIsNotNone(self.store.get("z"))  # get_store() checked mtimes.

    def test_queries(self):
        self.add_news(
            make_news("old", hours_ago=30, score=5000, tags=["Paris", "Climat"]),
            make_news("top", hours_ago=5, score=800, tags=["Paris"]),
            make_news("new", hours_ago=1, score=200, tags=["Climat", "paris"]),
        )
        self.assertEqual(
            self.store.most_popular(NOW.replace(day=30, hour=12)).id, "top"
        )
        self.assertEqual(
            [n.id for n in self.store.latest(2, exclude=["new"])], ["top", "old"]
        )

        # Most recently used first; ties broken by number of news.
        tags = self.store.tags()
        self.assertEqual([t.slug for t in tags], ["paris", "climat"])
        paris = self.store.tag("paris")
        self.assertEqual(paris.count, 3)
        self.assertEqual(paris.name, "Paris")  # Most frequent spelling wins.

        related = self.store.related(self.store.get("old"), limit=5)
        self.assertEqual([n.id for n in related], ["new", "top"])

    def test_to_analyze(self):
        self.add_news(make_news("a"), make_news("b", analyzed_at=NOW))
        self.assertEqual([n.id for n in self.store.to_analyze()], ["a"])
        self.assertEqual(len(self.store.to_analyze(force=True)), 2)

    def test_same_article_keeps_best_scored_post_and_its_analysis(self):
        url = "https://www.lemonde.fr/politique/article.html"
        self.add_news(make_news("a", score=300, url=url, tags=["Paris"]))
        with self.store.transaction():
            low = self.store.upsert(
                make_news("b", score=100, url=url + "?utm_source=x")
            )
            high = self.store.upsert(
                make_news(
                    "c", score=900, url="http://lemonde.fr/politique/article.html/"
                )
            )

        self.assertEqual((low, high), (UpsertResult.DUPLICATE, UpsertResult.CREATED))
        self.assertEqual([n.id for n in NewsStore(self.data_dir).all()], ["c"])
        self.assertEqual(self.store.get("c").tags, ["Paris"])

    def test_tag_aliases_apply_on_load_and_analysis(self):
        self.add_news(make_news("a", tags=["Macron", "Emmanuel Macron", "Paris"]))
        (self.data_dir / "tag_aliases.json").write_text(
            json.dumps({"macron": "Emmanuel Macron", "Ville de Paris": "Paris"})
        )
        self.assertEqual(self.store.get("a").tags, ["Emmanuel Macron", "Paris"])

        with self.store.transaction():
            self.store.set_analysis(make_news("a", tags=["Ville de Paris", "RN"]))
        self.assertEqual(self.store.get("a").tags, ["Paris", "RN"])

    def test_remove_deletes_news_and_thumbnail(self):
        thumbnail = self.data_dir / "media" / "thumbnails" / "a.webp"
        thumbnail.parent.mkdir(parents=True)
        thumbnail.write_bytes(b"webp")
        self.add_news(make_news("a", thumbnail="thumbnails/a.webp"), make_news("b"))
        with self.store.transaction():
            self.assertTrue(self.store.remove("a"))
            self.assertFalse(self.store.remove("unknown"))

        self.assertEqual([n.id for n in NewsStore(self.data_dir).all()], ["b"])
        self.assertFalse(thumbnail.exists())
        # The URL is free again.
        with self.store.transaction():
            result = self.store.upsert(
                make_news("c", url="https://example.org/articles/a")
            )
        self.assertEqual(result, UpsertResult.CREATED)


class UrlAndAliasHelpersTests(DataDirTestCase):
    def test_canonical_url(self):
        self.assertEqual(
            canonical_url("https://m.lefigaro.fr/a/b/amp/?xtor=RSS&id=3#top"),
            "lefigaro.fr/a/b?id=3",
        )
        self.assertNotEqual(
            canonical_url("https://youtube.com/watch?v=1"),
            canonical_url("https://youtube.com/watch?v=2"),
        )

    def test_apply_aliases_dedupes(self):
        self.assertEqual(
            apply_aliases(
                ["LFI", "La France insoumise"], {"lfi": "La France insoumise"}
            ),
            ["La France insoumise"],
        )
