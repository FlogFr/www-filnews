from django.test import override_settings
from django.urls import reverse

from filnews.groups import news_groups
from filnews.models import TagGroup

from .helpers import DataDirTestCase, make_news


def ids(items) -> list[str]:
    return [item.id for item in items]


class StoreGroupTests(DataDirTestCase):
    def test_group_lists_news_carrying_every_tag(self):
        self.add_news(
            make_news("both", hours_ago=1, tags=["Police", "Justice"]),
            make_news("three", hours_ago=2, tags=["Justice", "Racisme", "police"]),
            make_news("one", hours_ago=3, tags=["Police"]),
            make_news("old", hours_ago=4, tags=["Police", "Justice"]),
        )
        # Any order of the tags; news with more tags belong to the group too.
        self.assertEqual(
            ids(self.store.group(["justice", "police"])), ["both", "three", "old"]
        )
        self.assertEqual(
            ids(self.store.group(["police", "justice"])), ["both", "three", "old"]
        )
        self.assertEqual(
            ids(self.store.group(["police", "racisme", "justice"])), ["three"]
        )
        self.assertEqual(self.store.group(["police", "logement"]), [])
        self.assertEqual(self.store.group(["police"]), [])  # Not a group.

    def test_related_can_exclude_news(self):
        self.add_news(
            make_news("a", hours_ago=1, tags=["Police"]),
            make_news("b", hours_ago=2, tags=["Police"]),
            make_news("c", hours_ago=3, tags=["Police"]),
        )
        news = self.store.get("a")
        self.assertEqual(ids(self.store.related(news, 5)), ["b", "c"])
        self.assertEqual(ids(self.store.related(news, 5, exclude=["b"])), ["c"])


class NewsGroupsTests(DataDirTestCase):
    def test_no_group_below_two_tags_or_without_history(self):
        self.add_news(
            make_news("single", hours_ago=1, tags=["Police"]),
            make_news("pair", hours_ago=2, tags=["Police", "Justice"]),
            make_news("other", hours_ago=3, tags=["Police"]),
            make_news("other2", hours_ago=4, tags=["Justice"]),
        )
        self.assertIsNone(news_groups(self.store, self.store.get("single")))
        # Both tags have a history, but never together.
        self.assertIsNone(news_groups(self.store, self.store.get("pair")))

    def test_complete_group(self):
        self.add_news(
            *(
                make_news(f"n{i}", hours_ago=24 * i, tags=["Police", "Justice"])
                for i in range(1, 9)
            ),
            make_news("police", hours_ago=30, tags=["Police"]),
        )
        groups = news_groups(self.store, self.store.get("n4"))
        self.assertIsInstance(groups.group, TagGroup)
        self.assertTrue(groups.complete)
        self.assertEqual(groups.group.name, "Police + Justice")
        self.assertEqual(groups.group.count, 8)
        self.assertEqual(groups.rank, 5)  # 5th of 8, oldest first.
        self.assertEqual(groups.others, [])
        # Around the news: 2 newer ones, then the history before it.
        self.assertEqual(
            ids(e.news for e in groups.entries), ["n2", "n3", "n4", "n5", "n6"]
        )
        self.assertEqual(
            [e.current for e in groups.entries], [False, False, True, False, False]
        )
        self.assertEqual(groups.entries[0].gap_after, "1\xa0jour")
        self.assertEqual(groups.entries[-1].gap_after, "")
        self.assertEqual(groups.listed_ids, ["n2", "n3", "n4", "n5", "n6"])
        # Its timeline marks the news, drawn last (on top).
        last = groups.timeline.points[-1]
        self.assertEqual((last.news.id, last.current), ("n4", True))
        self.assertEqual(sum(p.current for p in groups.timeline.points), 1)

        # The oldest news: the newer ones fill the window.
        oldest = news_groups(self.store, self.store.get("n8"))
        self.assertEqual(
            ids(e.news for e in oldest.entries), ["n4", "n5", "n6", "n7", "n8"]
        )
        self.assertEqual(oldest.rank, 1)

    def test_closest_group_and_other_groups(self):
        self.add_news(
            make_news(
                "news", hours_ago=1, tags=["Éric Zemmour", "Justice", "Élections"]
            ),
            make_news("a", hours_ago=2, tags=["Éric Zemmour", "Justice"]),
            make_news("b", hours_ago=3, tags=["Éric Zemmour", "Justice"]),
            make_news("c", hours_ago=4, tags=["Justice", "Élections"]),
            make_news("d", hours_ago=5, tags=["Éric Zemmour", "Élections", "Police"]),
        )
        groups = news_groups(self.store, self.store.get("news"))
        # No other news has the 3 tags: the biggest pair instead.
        self.assertFalse(groups.complete)
        self.assertEqual(groups.group.name, "Éric Zemmour + Justice")
        self.assertEqual(ids(groups.group.news), ["news", "a", "b"])
        self.assertEqual(
            [(g.name, g.count) for g in groups.others],
            [("Éric Zemmour + Élections", 2), ("Justice + Élections", 2)],
        )

    def test_groups_with_the_same_news_as_a_bigger_one_are_left_out(self):
        self.add_news(
            make_news("news", hours_ago=1, tags=["Police", "Justice", "Racisme"]),
            make_news("a", hours_ago=2, tags=["Police", "Justice", "Racisme"]),
            make_news("b", hours_ago=3, tags=["Police", "Justice"]),
        )
        groups = news_groups(self.store, self.store.get("news"))
        self.assertTrue(groups.complete)
        self.assertEqual(groups.group.name, "Police + Justice + Racisme")
        # "Police + Racisme" and "Justice + Racisme" hold the same 2 news.
        self.assertEqual([g.name for g in groups.others], ["Police + Justice"])

    @override_settings(FILNEWS_TIMELINE_MAX_DOTS=3)
    def test_big_group_timeline_marks_the_news_on_bars(self):
        self.add_news(
            *(
                make_news(f"n{i}", hours_ago=24 * i, tags=["Police", "Justice"])
                for i in range(1, 6)
            )
        )
        groups = news_groups(self.store, self.store.get("n3"))
        self.assertEqual(groups.timeline.points, [])
        self.assertTrue(groups.timeline.bars)
        self.assertGreater(groups.timeline.marker, 0)
        self.assertLess(groups.timeline.marker, 100)


class NewsPageGroupTests(DataDirTestCase):
    def page(self, news_id: str):
        return self.client.get(
            reverse("news_detail", args=[self.store.get(news_id).slug])
        )

    def test_news_page_shows_its_group(self):
        self.add_news(
            *(
                make_news(
                    f"n{i}",
                    hours_ago=24 * i,
                    tags=["Police", "Justice"],
                    title=f"Affaire {i}",
                )
                for i in range(1, 9)
            ),
            make_news("police", hours_ago=30, tags=["Police"], title="Autre affaire"),
        )
        response = self.page("n4")
        self.assertContains(response, 'class="article article--grouped"')
        self.assertContains(response, "Le groupe de fils")
        self.assertContains(response, '<a href="/tags/police/">Police</a>')
        self.assertContains(
            response, "8 news réunissent ces 2 fils depuis le 23 octobre 2026"
        )
        self.assertContains(response, "celle-ci est la 5e.")
        self.assertContains(response, "tag-thread__item--current", count=1)
        self.assertContains(response, "Cette news")
        self.assertContains(response, "timeline__dot--current", count=1)
        self.assertContains(response, "Voir les 8 news du groupe")
        # Breadcrumb, then the news in the panel's thread and in its full list.
        self.assertContains(response, 'aria-current="page"', count=3)
        self.assertNotContains(response, "Ses autres groupes de fils")
        # Mobile order: the panel comes right after the article's links.
        html = response.content.decode()
        self.assertLess(html.index("article__links"), html.index('id="groupe"'))
        self.assertLess(html.index('id="groupe"'), html.index("article__context"))
        # The per-tag context and hover cards stay.
        self.assertContains(response, 'data-timeline="/tags/police/timeline/"')
        self.assertContains(response, 'Fil <a href="/tags/police/">Police</a>')
        # "Sur les mêmes sujets" skips the news listed in the panel.
        related = {news.id for news in response.context["related"]}
        self.assertFalse(related & {"n2", "n3", "n5", "n6"})
        self.assertIn("n7", related)

    def test_news_page_with_closest_group(self):
        self.add_news(
            make_news("news", hours_ago=1, tags=["Police", "Justice", "Racisme"]),
            make_news("a", hours_ago=2, tags=["Police", "Justice"]),
            make_news("b", hours_ago=3, tags=["Police", "Racisme"]),
        )
        response = self.page("news")
        self.assertContains(
            response,
            "Aucune autre news ne réunit ses 3 fils (Police, Justice et Racisme)",
        )
        self.assertContains(response, "Ses autres groupes de fils")
        self.assertContains(response, "Police + Racisme")
        self.assertNotContains(response, "Voir les 2 news du groupe")

    def test_news_page_without_group(self):
        self.add_news(
            make_news("news", hours_ago=1, tags=["Police"]),
            make_news("other", hours_ago=2, tags=["Police"]),
        )
        response = self.page("news")
        self.assertIsNone(response.context["groups"])
        self.assertContains(response, '<article class="article">')
        self.assertNotContains(response, "Le groupe de fils")
