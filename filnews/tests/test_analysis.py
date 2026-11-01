import io
from unittest import mock

from django.test import SimpleTestCase
from PIL import Image

from filnews.analysis import HeuristicAnalyzer, LocalModelAnalyzer
from filnews.analysis.extract import ArticleMetadata, extract_metadata
from filnews.analysis.fetch import FetchError
from filnews.analysis.text import candidate_entities, extract_tags, summarize

from .helpers import DataDirTestCase, make_news

ARTICLE_HTML = """
<html><head>
  <title>Fallback title</title>
  <meta property="og:title" content="Législatives : Mathilde Panot promet une reconnaissance">
  <meta property="og:description" content="Mathilde Panot, députée LFI élue dans le Val-de-Marne, a fait cette annonce après les résultats des législatives.">
  <meta property="og:image" content="/img/photo.jpg">
  <meta property="article:tag" content="Palestine">
  <meta name="keywords" content="politique, LFI">
</head><body>
  <nav><p>Menu de navigation qui ne doit jamais apparaître dans le texte extrait.</p></nav>
  <article>
    <p>La présidente du groupe insoumis Mathilde Panot s'exprimait après le second tour des élections.</p>
    <p>Court.</p>
  </article>
</body></html>
"""


def _jpeg(size=(1200, 800)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, "JPEG")
    return buffer.getvalue()


class ExtractionTests(SimpleTestCase):
    def test_extract_metadata(self):
        meta = extract_metadata(
            ARTICLE_HTML, "https://www.example.fr/politique/article"
        )
        self.assertTrue(meta.title.startswith("Législatives"))
        self.assertIn("Val-de-Marne", meta.description)
        self.assertEqual(meta.image, "https://www.example.fr/img/photo.jpg")
        self.assertEqual(meta.keywords, ["Palestine", "politique", "LFI"])
        self.assertIn("Mathilde Panot", meta.text)
        self.assertNotIn("Menu", meta.text)
        self.assertNotIn("Court.", meta.text)


class TextHeuristicsTests(SimpleTestCase):
    def test_candidate_entities(self):
        entities = candidate_entities(
            "Législatives : Mathilde Panot promet une reconnaissance de l'État de Palestine"
        )
        self.assertEqual(entities, ["Mathilde Panot", "État de Palestine"])
        self.assertEqual(
            candidate_entities("Le PSG gagne en Ligue 1"), ["PSG", "Ligue 1"]
        )

    def test_extract_tags_ranks_entities_and_adds_flair(self):
        tags = extract_tags(
            title="La SNCF annonce une grève, Emmanuel Macron réagit",
            description="Emmanuel Macron a commenté la grève de la SNCF.",
            publisher_keywords=["actualité", "transports"],
            flair="Société",
            limit=5,
        )
        self.assertEqual(tags[:2], ["SNCF", "Emmanuel Macron"])
        self.assertIn("Société", tags)
        self.assertIn("Transports", tags)
        self.assertNotIn("Actualité", tags)  # Generic keyword.

    def test_extract_tags_drops_common_nouns(self):
        tags = extract_tags(
            title="Union européenne : accord trouvé",
            text="Cette union est historique. Union Pacifique.",
        )
        self.assertNotIn("Union", tags)

    def test_generic_flair_is_ignored(self):
        self.assertNotIn("Paywall", extract_tags(title="Une news", flair="Paywall"))

    def test_summarize_cuts_on_sentence_boundary(self):
        text = "Première phrase assez longue pour être un résumé correct. " * 10
        summary = summarize("trop court", text, max_chars=130)
        self.assertLessEqual(len(summary), 130)
        self.assertTrue(summary.endswith("."))
        self.assertEqual(summarize("", "court"), "")


class HeuristicAnalyzerTests(DataDirTestCase):
    def test_analyze_fills_tags_summary_and_thumbnail(self):
        analyzer = HeuristicAnalyzer(media_root=self.data_dir / "media")
        news = make_news(
            "abc",
            title="Législatives : Mathilde Panot promet une reconnaissance de l'État de Palestine",
            flair="Politique",
        )
        with (
            mock.patch(
                "filnews.analysis.analyzers.fetch_html", return_value=ARTICLE_HTML
            ),
            mock.patch("filnews.analysis.analyzers.fetch_image", return_value=_jpeg()),
        ):
            analyzer.analyze(news)

        self.assertIn("Mathilde Panot", news.tags)
        self.assertIn("Politique", news.tags)
        self.assertIn("Val-de-Marne", news.summary)
        self.assertEqual(news.thumbnail, "thumbnails/abc.webp")
        self.assertIsNotNone(news.analyzed_at)
        with Image.open(self.data_dir / "media" / news.thumbnail) as thumb:
            self.assertEqual((thumb.format, thumb.size), ("WEBP", (640, 360)))

    def test_analyze_survives_unreachable_article(self):
        analyzer = HeuristicAnalyzer(media_root=self.data_dir / "media")
        news = make_news(
            "abc", title="Emmanuel Macron en visite à Marseille", selftext=""
        )
        with (
            mock.patch(
                "filnews.analysis.analyzers.fetch_html", side_effect=FetchError("403")
            ),
            mock.patch(
                "filnews.analysis.analyzers.fetch_image", side_effect=FetchError("403")
            ),
        ):
            analyzer.analyze(news)
        self.assertEqual(news.tags, ["Emmanuel Macron", "Marseille"])
        self.assertEqual(news.thumbnail, "")
        self.assertIsNotNone(news.analyzed_at)

    def test_dead_article_uses_wayback_machine_copy(self):
        analyzer = HeuristicAnalyzer(media_root=self.data_dir / "media")
        news = make_news("abc", url="https://www.lemonde.fr/vieux.html")
        fetched = []

        def fetch_html(session, url):
            fetched.append(url)
            if "web.archive.org" not in url:
                raise FetchError("HTTP 404", status=404)
            return ARTICLE_HTML

        def fetch_image(session, url):
            if "web.archive.org" not in url:
                raise FetchError("HTTP 404", status=404)
            return _jpeg()

        with (
            mock.patch("filnews.analysis.analyzers.fetch_html", fetch_html),
            mock.patch("filnews.analysis.analyzers.fetch_image", fetch_image),
            mock.patch(
                "filnews.analysis.analyzers.wayback_snapshot",
                return_value="20190301120000",
            ),
        ):
            analyzer.analyze(news)

        self.assertEqual(
            fetched[1],
            "https://web.archive.org/web/20190301120000id_/https://www.lemonde.fr/vieux.html",
        )
        self.assertIn("Val-de-Marne", news.summary)
        self.assertEqual(news.thumbnail, "thumbnails/abc.webp")

    def test_wayback_is_skipped_for_live_errors_or_when_disabled(self):
        analyzer = HeuristicAnalyzer(media_root=self.data_dir / "media")
        with (
            mock.patch(
                "filnews.analysis.analyzers.fetch_html",
                side_effect=FetchError("HTTP 500", status=500),
            ),
            mock.patch("filnews.analysis.analyzers.wayback_snapshot") as wayback,
        ):
            analyzer._metadata(make_news("a"))
            with self.settings(FILNEWS_WAYBACK=False):
                analyzer._metadata(make_news("b"))
        wayback.assert_not_called()


class LocalModelAnalyzerTests(DataDirTestCase):
    def test_model_tags_use_source_spans_and_shared_filters(self):
        # Bypass __init__: no transformers/torch needed to test the merging.
        analyzer = LocalModelAnalyzer.__new__(LocalModelAnalyzer)
        analyzer.max_tags = 4

        def fake_keywords(source):
            start = source.index("Nuñez")
            return [
                {"word": "Nu<unk>ez", "start": start, "end": start + 5, "score": 0.9},
                {"word": "France", "start": 0, "end": 6, "score": 0.8},
                {"word": "franceinfo", "start": None, "end": None, "score": 0.7},
            ]

        analyzer._keywords = fake_keywords
        news = make_news("x", title="France : Laurent Nuñez réagit à Marseille")
        tags = analyzer.tags(news, ArticleMetadata(site_name="franceinfo"))
        self.assertEqual(tags, ["Nuñez", "Laurent Nuñez", "Marseille"])
