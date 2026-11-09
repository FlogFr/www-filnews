import json
import re
from datetime import timedelta
from unittest import mock
from xml.etree import ElementTree

from django.test import override_settings
from django.urls import reverse
from django.utils import translation

from filnews.models import TagSummary
from filnews.timeline import build_thread, build_timeline
from filnews.views import OAUTH_STATE_COOKIE

from .helpers import NOW, DataDirTestCase, make_news

LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


class ViewTestCase(DataDirTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("filnews.views.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)


class HomeTests(ViewTestCase):
    def test_home_layout(self):
        self.add_news(
            make_news("old", hours_ago=48, score=9000, tags=["Ancien", "Paris"]),
            make_news(
                "top", hours_ago=10, score=3000, title="La news du jour", tags=["Paris"]
            ),
            *[
                make_news(
                    f"n{i}", hours_ago=i, score=150, tags=[f"Tag {i}", f"Autre {i}"]
                )
                for i in range(1, 8)
            ],
        )
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

        # Headline: most popular of the last 24 hours (not the older 9000).
        self.assertEqual(response.context["headline"].id, "top")
        self.assertContains(response, '<h2 class="hero__title"', count=1)
        self.assertEqual(len(response.context["news_list"]), 5)
        self.assertNotIn("top", [n.id for n in response.context["news_list"]])
        # Fils du moment: tags of the last 7 days with a page, busiest first.
        self.assertEqual([t.slug for t in response.context["trending_tags"]], ["paris"])
        # Next to the headline: the Fil of the busiest tag of the last 48
        # hours ("Paris": 2 news, the "Tag i" have 1 and no page).
        featured = response.context["featured"]
        self.assertEqual(featured["tag"].slug, "paris")
        self.assertEqual([e["news"].id for e in featured["thread"]], ["top", "old"])
        self.assertEqual(featured["thread"][0]["gap_after"], "1\xa0jour")
        self.assertContains(response, "Le fil du moment")
        self.assertContains(response, "Remonter tout le fil Paris")
        self.assertContains(response, "tag-thread__item--current", count=1)
        # Source order is the mobile order: headline, latest news, featured
        # Fil, then the sidebar (wide screens rearrange it in CSS).
        html = response.content.decode()
        positions = [
            html.index(marker)
            for marker in (
                'class="headline"',
                'class="latest"',
                'class="tag-thread"',
                'class="sidebar"',
            )
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertContains(response, "On vous donne le fil.")
        self.assertContains(response, 'href="/presidentielle-2027/"')
        self.assertContains(response, 'href="/rss.xml"')
        self.assertContains(response, 'data-timeline="/tags/paris/timeline/"')
        # A tag seen once has no page: plain text, no link.
        self.assertContains(response, '<span class="tag tag--plain">Tag 1</span>')
        self.assertNotContains(response, "/tags/tag-1/")

    def test_home_falls_back_to_latest_news(self):
        self.add_news(make_news("old", hours_ago=72))
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["headline"].id, "old")

    def test_empty_home(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Aucune news pour le moment")


class SeoTests(ViewTestCase):
    def test_news_page_metadata(self):
        news = make_news(
            "abc",
            tags=["Paris"],
            summary="Un résumé <b>important</b> & utile.",
            thumbnail="thumbnails/abc.webp",
        )
        self.add_news(news)
        response = self.client.get(reverse("news_detail", args=[news.slug]))
        html = response.content.decode()

        self.assertIn('<html lang="fr"', html)
        self.assertIn(
            f'<link rel="canonical" href="https://filnews.fr/news/{news.slug}/">',
            html,
        )
        self.assertIn(
            '<meta property="og:image" content="https://filnews.fr/media/thumbnails/abc.webp">',
            html,
        )
        self.assertEqual(html.count("<h1"), 1)
        blocks = [json.loads(block) for block in LD_JSON_RE.findall(html)]
        article = next(b for b in blocks if b["@type"] == "NewsArticle")
        self.assertEqual(article["description"], "Un résumé <b>important</b> & utile.")
        self.assertEqual(article["keywords"], "Paris")
        # The page repeats its source: kept out of search results, links
        # still followed (FILNEWS_INDEX_NEWS).
        self.assertIn('<meta name="robots" content="noindex, follow', html)

    @override_settings(FILNEWS_INDEX_NEWS=True)
    def test_news_page_can_be_indexed(self):
        news = make_news("abc")
        self.add_news(news)
        response = self.client.get(reverse("news_detail", args=[news.slug]))
        self.assertContains(response, '<meta name="robots" content="index, follow')

    def test_news_page_context(self):
        self.add_news(
            make_news("first", hours_ago=24 * 3, tags=["Logement", "Macron"]),
            make_news("top", hours_ago=2, score=900, title="Plus votée"),
            make_news("news", hours_ago=1, score=300, tags=["Logement"]),
            make_news("other", hours_ago=24 * 3 + 1, tags=["Macron"]),
        )
        response = self.client.get(
            reverse("news_detail", args=[self.store.get("news").slug])
        )
        insight = response.context["insight"]
        self.assertEqual((insight.day_rank, insight.day_count), (2, 2))
        self.assertContains(response, "2e news la plus votée du 31 octobre 2026")
        [position] = insight.threads
        self.assertEqual((position.tag.slug, position.rank), ("logement", 2))
        self.assertEqual(position.previous.id, "first")
        self.assertContains(response, "la plus récente des 2 news depuis le 28 octobre")
        self.assertContains(response, "La précédente, 2\xa0jours plus tôt")

        first = self.client.get(
            reverse("news_detail", args=[self.store.get("first").slug])
        )
        self.assertContains(
            first, "c'est la première news de ce fil", count=1
        )  # Logement.
        self.assertContains(first, "la plus récente des 2 news depuis le 28 octobre")
        self.assertContains(first, "c'est la news la plus votée du 28 octobre 2026")

    def test_unknown_pages_are_404(self):
        self.assertEqual(self.client.get("/news/inconnue-xyz/").status_code, 404)
        self.assertEqual(self.client.get("/tags/inconnu/").status_code, 404)
        self.assertEqual(self.client.get("/archives/page/2/").status_code, 404)
        self.assertEqual(self.client.get("/archives/2019/03/").status_code, 404)

    def _locations(self, url: str) -> list[str]:
        response = self.client.get(url, HTTP_HOST="filnews.fr", secure=True)
        return [
            el.text
            for el in ElementTree.fromstring(response.content).iter()
            if el.tag.endswith("loc")
        ]

    def test_robots_and_sitemap(self):
        self.add_news(
            make_news("abc", tags=["Paris", "Unique"]),
            make_news("def", hours_ago=24 * 40, tags=["Paris"]),
        )
        robots = self.client.get(reverse("robots_txt"))
        self.assertContains(robots, "Sitemap: https://filnews.fr/sitemap.xml")

        # sitemap.xml is an index of one static file per section.
        self.assertEqual(
            self._locations(reverse("sitemap")),
            [
                "https://filnews.fr/sitemap-pages.xml",
                "https://filnews.fr/sitemap-tags.xml",
            ],
        )
        self.assertEqual(
            self._locations("/sitemap-tags.xml"), ["https://filnews.fr/tags/paris/"]
        )
        # News pages are "noindex" (FILNEWS_INDEX_NEWS): not in the sitemap.
        self.assertEqual(self.client.get("/sitemap-news.xml").status_code, 404)
        pages = self._locations("/sitemap-pages.xml")
        self.assertIn("https://filnews.fr/archives/2026/09/", pages)
        self.assertIn("https://filnews.fr/presidentielle-2027/", pages)
        self.assertIn(
            "https://filnews.fr/presidentielle-2027/jean-luc-melenchon/", pages
        )
        self.assertIn("https://filnews.fr/mentions-legales/", pages)

    def test_rss_lists_all_news_newest_first(self):
        self.add_news(*[make_news(f"n{i}", hours_ago=i * 10) for i in range(1, 4)])
        response = self.client.get(reverse("rss"))
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        titles = [
            el.text for el in ElementTree.fromstring(response.content).iter("title")
        ][1:]
        self.assertEqual(
            titles,
            ["Titre de la news n1", "Titre de la news n2", "Titre de la news n3"],
        )


class TagTests(ViewTestCase):
    def test_tag_page_and_timeline_fragment(self):
        self.add_news(
            make_news("a", tags=["Paris"]), make_news("b", hours_ago=50, tags=["Paris"])
        )
        page = self.client.get(reverse("tag_detail", args=["paris"]))
        self.assertContains(page, "2 news liées à ce sujet, du 29 octobre 2026")
        self.assertContains(page, "thread__item--left", count=1)
        self.assertContains(page, "thread__item--right", count=1)
        self.assertContains(page, "2\xa0jours plus tôt")

        fragment = self.client.get(reverse("tag_timeline", args=["paris"]))
        self.assertNotContains(fragment, "<html")
        # Two news: each one in the list and as a dot on the timeline.
        self.assertContains(fragment, 'href="/news/', count=4)
        # Dots and list items share `data-news` so main.js can pair them.
        self.assertContains(fragment, 'data-news="a"', count=2)
        html = fragment.content.decode()
        self.assertLess(html.index("timeline__chart"), html.index("tag-card__news"))
        self.assertNotContains(fragment, "Voir les")

    def test_tag_page_profile(self):
        self.add_news(
            make_news("a", tags=["Paris", "Logement"], domain="lemonde.fr"),
            make_news(
                "b", hours_ago=2, tags=["Paris", "Logement"], domain="lemonde.fr"
            ),
            make_news(
                "c",
                created_at=NOW - timedelta(days=60),
                score=5000,
                title="La plus votée",
                tags=["Paris", "Macron"],
            ),
            make_news("d", hours_ago=3, tags=["Macron"]),
        )
        page = self.client.get(reverse("tag_detail", args=["paris"]))
        profile = page.context["profile"]
        self.assertEqual(profile.peak_count, 2)
        self.assertEqual(profile.domains, [("lemonde.fr", 2)])
        self.assertEqual(profile.top_news.id, "c")
        self.assertEqual([t.slug for t in profile.neighbours], ["logement", "macron"])
        self.assertContains(page, "Le pic : 2 news en octobre 2026.")
        self.assertContains(page, "Les médias les plus cités : lemonde.fr (2).")
        self.assertContains(page, ">La plus votée</a> (5000 votes)")
        self.assertContains(page, 'Logement</a> et <a href="/tags/macron/">Macron</a>.')

    def test_single_news_tag_has_no_page(self):
        self.add_news(
            make_news("a", tags=["Unique", "Paris"]), make_news("b", tags=["Paris"])
        )
        self.assertEqual(self.client.get("/tags/unique/").status_code, 404)
        self.assertEqual(self.client.get("/tags/unique/timeline/").status_code, 404)
        index = self.client.get(reverse("tag_index"))
        self.assertContains(index, "1 fil suivi")
        self.assertContains(index, 'id="lettre-p"')

    def test_big_tag_is_split_by_year(self):
        news = [
            make_news(f"n{i}", created_at=NOW - timedelta(days=i * 20), tags=["Paris"])
            for i in range(70)  # About 4 years.
        ]
        self.add_news(*news)
        page = self.client.get(reverse("tag_detail", args=["paris"]))
        self.assertContains(page, 'class="year-nav"')
        self.assertContains(page, '<a href="/tags/paris/" aria-current="page">2026')
        self.assertContains(page, 'href="/tags/paris/2023/"')
        self.assertTrue(
            all(e.news.created_at.year == 2026 for e in page.context["thread"])
        )

        older = self.client.get("/tags/paris/2024/")
        self.assertContains(older, "<title>Paris : l'actualité en 2024")
        self.assertContains(
            older, 'Paris <span class="page-title__year">en 2024</span>'
        )
        self.assertTrue(
            all(e.news.created_at.year == 2024 for e in older.context["thread"])
        )
        latest = self.client.get("/tags/paris/2026/")
        self.assertRedirects(latest, "/tags/paris/", status_code=301)
        self.assertEqual(self.client.get("/tags/paris/2001/").status_code, 404)

        # Too many news for dots: one bar per month.
        fragment = self.client.get(reverse("tag_timeline", args=["paris"]))
        self.assertNotContains(fragment, "timeline__dot")
        self.assertContains(fragment, "timeline__bar")

    def test_timeline_card_lists_latest_news_only(self):
        self.add_news(
            *(make_news(f"n{i}", hours_ago=i * 24, tags=["Paris"]) for i in range(1, 8))
        )
        fragment = self.client.get(reverse("tag_timeline", args=["paris"]))
        self.assertContains(fragment, "Voir les 7 news")
        self.assertContains(fragment, "timeline__dot", count=7)

    def test_timeline_separates_news_one_day_apart(self):
        tag = TagSummary(
            "CRS", "crs", [make_news("a", hours_ago=1), make_news("b", hours_ago=25)]
        )
        timeline = build_timeline(tag)
        newest, oldest = (point.position for point in timeline.points)
        self.assertGreater(newest - oldest, 40)
        self.assertGreater(oldest, 0)
        self.assertLess(newest, 100)
        with translation.override("fr"):
            labels = [tick.label for tick in build_timeline(tag).ticks]
        self.assertEqual(labels, ["30 oct.", "31 oct.", "1er nov."])

    def test_timeline_single_news_is_centred(self):
        timeline = build_timeline(TagSummary("CRS", "crs", [make_news("a")]))
        self.assertEqual(timeline.points[0].position, 50)

    def test_timeline_ticks_follow_history_length(self):
        months = TagSummary(
            "Paris",
            "paris",
            [make_news("a"), make_news("b", created_at=NOW - timedelta(days=200))],
        )
        labels = [tick.label for tick in build_timeline(months).ticks]
        self.assertTrue(all(label.endswith(("2025", "2026")) for label in labels))
        self.assertLessEqual(len(labels), 5)

        ancient = make_news("b", created_at=NOW - timedelta(days=365 * 30))
        years = TagSummary("Paris", "paris", [make_news("a"), ancient])
        timeline = build_timeline(years)
        self.assertTrue(all(tick.label.isdigit() for tick in timeline.ticks))
        self.assertLessEqual(len(timeline.ticks), 5)
        self.assertGreater(timeline.points[-1].position, 0)

    def test_thread_alternates_sides_and_marks_years(self):
        tag = TagSummary(
            "Paris",
            "paris",
            [
                make_news("a"),
                make_news("b", hours_ago=26),
                make_news("c", created_at=NOW - timedelta(days=400)),
            ],
        )
        thread = build_thread(tag)
        self.assertEqual([e.side for e in thread], ["left", "right", "left"])
        self.assertEqual([e.new_year for e in thread], [True, False, True])
        self.assertEqual(thread[0].gap, "")
        self.assertEqual(thread[1].gap, "1\xa0jour")


class ArchiveTests(ViewTestCase):
    def test_archive_lists_months_by_year(self):
        self.add_news(
            make_news("a"),
            make_news("b", created_at=NOW - timedelta(days=40)),
            make_news("c", created_at=NOW.replace(year=2019, month=3, day=4)),
        )
        page = self.client.get(reverse("archive"))
        self.assertContains(page, "3 news, mois par mois")
        self.assertContains(page, 'href="/archives/2026/10/"')
        self.assertContains(page, 'href="/archives/2026/09/"')
        self.assertContains(page, 'href="/archives/2019/03/">Mars</a>')

    def test_month_page_groups_by_day_and_links_neighbours(self):
        self.add_news(
            make_news("a", created_at=NOW.replace(year=2019, month=4, day=2)),
            make_news("b", created_at=NOW.replace(year=2019, month=3, day=4)),
            make_news("c", created_at=NOW.replace(year=2019, month=3, day=4, hour=8)),
            make_news("d", created_at=NOW.replace(year=2018, month=12, day=24)),
        )
        page = self.client.get("/archives/2019/03/")
        self.assertContains(page, "Archives</span> Mars 2019")
        self.assertContains(page, "Lundi 4 mars 2019", count=1)
        self.assertContains(page, "archive-list__item", count=2)
        self.assertContains(page, 'href="/archives/2019/04/" rel="prev"')
        self.assertContains(page, 'href="/archives/2018/12/" rel="next"')
        self.assertEqual(self.client.get("/archives/2019/13/").status_code, 404)


class RedditOAuthTests(ViewTestCase):
    def test_callback_rejects_missing_or_wrong_state(self):
        url = reverse("reddit_callback")
        self.assertEqual(url, "/auth/reddit/callback")
        self.assertEqual(
            self.client.get(url, {"code": "c", "state": "x"}).status_code, 400
        )

    @mock.patch("filnews.views.RedditClient")
    def test_login_then_callback_exchanges_code(self, client_class):
        client = client_class.from_settings.return_value
        client.authorize_url.side_effect = lambda state: (
            f"https://www.reddit.com/api/v1/authorize?state={state}"
        )

        login = self.client.get(reverse("reddit_login"))
        self.assertEqual(login.status_code, 302)
        state = login.url.rsplit("=", 1)[1]
        self.assertIn(OAUTH_STATE_COOKIE, login.cookies)

        callback = self.client.get(
            reverse("reddit_callback"), {"code": "the-code", "state": state}
        )
        self.assertEqual(callback.status_code, 200)
        client.exchange_code.assert_called_once_with("the-code")


class ElectionTests(ViewTestCase):
    def test_election_thread_and_candidates(self):
        self.add_news(
            make_news(
                "camp",
                title="Présidentielle 2027 : le programme de Fabien Roussel",
                tags=["Fabien Roussel"],
            ),
            make_news(
                "cand",
                hours_ago=5,
                title="Jean-Luc Mélenchon candidat pour la troisième fois",
                tags=["Jean-Luc Mélenchon"],
            ),
            make_news(
                "other",
                hours_ago=6,
                title="Jean-Luc Mélenchon commente la météo",
                tags=["Jean-Luc Mélenchon"],
            ),
            make_news(
                "abroad",
                hours_ago=7,
                title="Présidentielle au Brésil : Lula réélu",
                tags=["Élection présidentielle"],
            ),
            make_news(
                "before",
                hours_ago=24 * 800,
                title="Mélenchon candidat en 2022",
                tags=["Jean-Luc Mélenchon"],
            ),
        )
        page = self.client.get(reverse("election"))
        self.assertEqual(
            [entry.news.id for entry in page.context["thread"]], ["camp", "cand"]
        )
        self.assertContains(page, 'href="/presidentielle-2027/fabien-roussel/"')
        self.assertContains(page, "Candidature déclarée")

        candidate = self.client.get(
            reverse("election_candidate", args=["jean-luc-melenchon"])
        )
        # Every news of the candidate since the start of the campaign.
        self.assertEqual(
            [entry.news.id for entry in candidate.context["thread"]],
            ["cand", "other"],
        )
        self.assertContains(candidate, 'href="/tags/jean-luc-melenchon/"')
        self.assertEqual(
            self.client.get("/presidentielle-2027/inconnu/").status_code, 404
        )


class LegalTests(ViewTestCase):
    def test_legal_notice_links_the_source_code(self):
        page = self.client.get(reverse("legal"))
        self.assertContains(
            page, '<h1 class="page-title">Mentions légales</h1>', html=False
        )
        self.assertContains(page, 'href="https://github.com/FlogFr/www-filnews"')
        self.assertContains(page, "GitHub, Inc.")
        self.assertNotContains(page, "mailto:")
        # Linked from every page.
        home = self.client.get(reverse("home"))
        self.assertContains(home, 'href="/mentions-legales/"')
        self.assertContains(home, "L&#x27;actualité vue par r/france")
