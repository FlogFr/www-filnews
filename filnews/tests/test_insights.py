from datetime import UTC, date, datetime

from django.urls import reverse

from filnews.insights import tag_reading
from filnews.media import ALLOWED_DOMAINS, MEDIA_FAMILIES, media_family
from filnews.models import News

from .helpers import DataDirTestCase, make_news

LATEST = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def news(
    news_id: str,
    year: int,
    month: int,
    tags: list[str],
    *,
    day: int = 10,
    score: int = 100,
    comments: int = 10,
    domain: str = "lemonde.fr",
) -> News:
    return make_news(
        news_id,
        created_at=datetime(year, month, day, 12, 0, tzinfo=UTC),
        tags=tags,
        score=score,
        num_comments=comments,
        domain=domain,
        url=f"https://{domain}/{news_id}",
    )


NATIONAL = [
    "lemonde.fr",
    "lefigaro.fr",
    "liberation.fr",
    "leparisien.fr",
    "humanite.fr",
    "la-croix.com",
]


def monthly(prefix: str, months, count: int, tags, **fields) -> list[News]:
    """`count` news per month; by default from 6 national newspapers in turn."""
    entries = []
    for year, month in months:
        for i in range(count):
            values = {"domain": NATIONAL[len(entries) % len(NATIONAL)], **fields}
            entries.append(
                news(
                    f"{prefix}{year}{month:02}{i}",
                    year,
                    month,
                    tags,
                    day=1 + i,
                    **values,
                )
            )
    return entries


def months_between(start: tuple[int, int], end: tuple[int, int]):
    year, month = start
    while (year, month) <= end:
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


class MediaFamilyTests(DataDirTestCase):
    def test_families_cover_the_allowed_media_once(self):
        domains = [d for family in MEDIA_FAMILIES.values() for d in family]
        self.assertEqual(len(domains), len(set(domains)))
        self.assertEqual(set(domains), ALLOWED_DOMAINS)

    def test_most_specific_family_wins(self):
        self.assertEqual(media_family("abonnes.lemonde.fr"), "national")
        self.assertEqual(media_family("korii.slate.fr"), "specialized")
        self.assertEqual(media_family("slate.fr"), "national")
        self.assertEqual(media_family("bfmtv.com"), "broadcast")
        self.assertIsNone(media_family("example.org"))


class TagReadingTests(DataDirTestCase):
    def setUp(self):
        super().setUp()
        # Background news, every month from 2022 to the latest: the site's
        # reference (national press, 10 comments per 100 votes).
        self.add_news(
            *monthly("bg", list(months_between((2022, 1), (2026, 9))), 3, ["Police"]),
            news("latest", 2026, 10, ["Police"], day=15),
        )

    def reading(self, slug: str):
        return tag_reading(self.store, self.store.tag_page(slug))

    def test_small_fil_has_no_reading(self):
        self.add_news(*monthly("s", [(2026, 1)], 9, ["Petit"]))
        self.assertIsNone(self.reading("petit"))
        page = self.client.get(reverse("tag_detail", args=["petit"]))
        self.assertIsNone(page.context["reading"])
        self.assertNotContains(page, "Lecture critique")

    def test_background_fil(self):
        reading = self.reading("police")
        self.assertEqual(reading.rhythm.kind, "background")
        self.assertEqual(reading.rhythm.span_months, 58)
        self.assertEqual(reading.rhythm.active_months, 58)
        self.assertFalse(reading.sources.concentrated)
        self.assertEqual((reading.sources.count, reading.sources.top_share), (6, 17))
        self.assertIsNone(reading.sources.over)
        self.assertEqual((reading.angles, reading.max_angle_share), ([], 0))
        self.assertEqual((reading.debate, reading.votes), ("average", "average"))

    def test_dormant_wave_with_concentrated_sources(self):
        # 10 news on pensions in early 2023 (a wave), 2 others before and
        # after, then nothing: dormant. Half of them from one TV channel,
        # much more debated than the other news of their month.
        wave = [
            news(
                f"r{i}",
                2023,
                1 + i % 3,
                ["Retraites", "Grèves"],
                day=20 + i,
                comments=40,
                domain="bfmtv.com" if i % 2 else "lemonde.fr",
            )
            for i in range(10)
        ]
        wave_months = [(2022, 1), (2023, 1), (2023, 2), (2023, 3), (2023, 12)]
        self.add_news(
            *monthly("more", wave_months, 6, ["Police"]),
            *wave,
            news("r-first", 2022, 1, ["Retraites"], day=20, comments=40),
            news("r-last", 2023, 12, ["Retraites"], day=20, comments=40),
            news("bfm", 2023, 12, ["Retraites"], day=21, domain="bfmtv.com"),
        )
        reading = self.reading("retraites")
        rhythm = reading.rhythm
        self.assertEqual(rhythm.kind, "dormant")
        self.assertEqual(
            (rhythm.wave_start, rhythm.wave_end), (date(2023, 1, 1), date(2023, 3, 1))
        )
        self.assertEqual((rhythm.wave_count, rhythm.wave_share), (10, 77))
        self.assertEqual((rhythm.idle_months, rhythm.idle_years), (33, 2))

        sources = reading.sources
        self.assertEqual((sources.top, sources.top_share), ("lemonde.fr", 54))
        self.assertTrue(sources.concentrated)
        self.assertEqual(sources.over.label, "radio et télévision")
        self.assertEqual(sources.over.share, 46)

        [angle] = reading.angles
        self.assertEqual((angle.tag.slug, angle.share), ("greves", 77))
        self.assertEqual(reading.debate, "high")
        self.assertEqual(reading.debate_factor, 4.0)

        page = self.client.get(reverse("tag_detail", args=["retraites"]))
        self.assertContains(page, "Lecture critique")
        self.assertContains(
            page,
            "Un sujet retombé qui a fait débat sur r/france, raconté par peu de "
            "médias, souvent lié au fil Grèves.",
        )
        self.assertContains(page, "plus aucune news depuis plus de 2 ans")
        self.assertContains(page, "entre janvier et mars 2023")
        self.assertContains(page, "radio et télévision (46&nbsp;% des news")

    def test_votes_are_compared_within_the_month(self):
        # Scores grew a lot over ten years: each news is compared to the
        # median news of its own month (here 100 votes).
        months = list(months_between((2022, 4), (2022, 8)))
        self.add_news(*monthly("vote", months, 2, ["Vote"], score=300))
        reading = self.reading("vote")
        self.assertEqual((reading.votes, reading.votes_percent), ("high", 200))

    def test_angle_shift(self):
        # Before the last 12 months, the Fil goes with "Justice"; since, with
        # "Institutions".
        self.add_news(
            *monthly("old", [(2023, 1), (2023, 6)], 4, ["Corruption", "Justice"]),
            *monthly("new", [(2026, 1), (2026, 6)], 4, ["Corruption", "Institutions"]),
        )
        reading = self.reading("corruption")
        self.assertEqual(reading.recent_angle.tag.slug, "institutions")
        self.assertEqual(reading.former_angle.tag.slug, "justice")
        self.assertEqual(
            [(a.tag.slug, a.share) for a in reading.angles],
            [("institutions", 50), ("justice", 50)],
        )
