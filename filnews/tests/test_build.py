import json
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError

from filnews.management.commands.build_site import output_file

from .helpers import DataDirTestCase, make_news


class BuildSiteTests(DataDirTestCase):
    def test_builds_every_page_as_static_files(self):
        news = make_news("abc", tags=["Paris", "Unique"])
        self.add_news(news, make_news("def", tags=["Paris"]))
        output = Path(tempfile.mkdtemp(prefix="filnews-dist-"))
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)

        call_command("build_site", output=output, workers=1, stdout=StringIO())

        for relative in [
            "index.html",
            "404.html",
            "rss.xml",
            "sitemap.xml",
            "sitemap-pages.xml",
            "sitemap-tags.xml",
            "archives/2026/10/index.html",
            "robots.txt",
            "archives/index.html",
            "a-propos/index.html",
            "tags/index.html",
            "tags/paris/index.html",
            "tags/paris/timeline/index.html",
            f"news/{news.slug}/index.html",
        ]:
            self.assertTrue((output / relative).is_file(), relative)
        # News pages are "noindex": no sitemap section for them.
        self.assertFalse((output / "sitemap-news.xml").exists())

        # Assets are fingerprinted and the SCSS sources are not published.
        manifest = json.loads((output / "static" / "staticfiles.json").read_text())
        css = manifest["paths"]["css/main.css"]
        self.assertIn(f"/static/{css}", (output / "index.html").read_text())
        self.assertFalse((output / "static" / "scss").exists())
        # Absolute URLs point to the public site.
        self.assertIn(
            "https://filnews.fr/tags/paris/",
            (output / "sitemap-tags.xml").read_text(),
        )
        self.assertFalse((output / "tags" / "unique").exists())

    def test_parallel_build_renders_the_same_pages(self):
        self.add_news(
            *[make_news(f"n{i}", hours_ago=i, tags=["Paris"]) for i in range(220)]
        )
        output = Path(tempfile.mkdtemp(prefix="filnews-dist-"))
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)

        out = StringIO()
        call_command("build_site", output=output, workers=2, stdout=out)
        pages = list((output / "news").glob("*/index.html"))
        self.assertEqual(len(pages), 220)
        self.assertIn("Built", out.getvalue())

    def test_output_file_mapping(self):
        root = Path("/srv/dist")
        self.assertEqual(output_file(root, "/"), root / "index.html")
        self.assertEqual(output_file(root, "/tags/x/"), root / "tags/x/index.html")
        self.assertEqual(output_file(root, "/rss.xml"), root / "rss.xml")
        with self.assertRaises(CommandError):
            output_file(root, "/../etc/passwd")
