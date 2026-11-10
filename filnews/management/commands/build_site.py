"""Render the whole site to static files, ready to be served by nginx.

Pages are rendered in parallel by forked worker processes: they inherit the
already loaded store and settings, each one renders a share of the URLs with
its own test client.
"""

import multiprocessing
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse

from filnews.assets import compile_scss
from filnews.elections import CANDIDATES
from filnews.sitemaps import SITEMAPS
from filnews.store import get_store
from filnews.timeline import thread_years

MANIFEST_STORAGE = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}


def site_paths() -> list[str]:
    """Every URL of the public site."""
    store = get_store()
    paths = [
        reverse("home"),
        reverse("archive"),
        reverse("tag_index"),
        reverse("election"),
        reverse("about"),
        reverse("legal"),
        reverse("rss"),
        reverse("sitemap"),
        reverse("robots_txt"),
    ]
    paths += [reverse("sitemap_section", args=[section]) for section in SITEMAPS]
    paths += [
        reverse("archive_month", args=[f"{year:04d}", f"{month:02d}"])
        for year, month, _ in store.months()
    ]
    paths += [reverse("election_candidate", args=[c.slug]) for c in CANDIDATES]
    paths += [reverse("news_detail", args=[news.slug]) for news in store.all()]
    for tag in store.page_tags():
        paths += [
            reverse("tag_detail", args=[tag.slug]),
            reverse("tag_timeline", args=[tag.slug]),
        ]
        # The most recent year is the tag page itself.
        paths += [
            reverse("tag_year", args=[tag.slug, year])
            for year, _ in thread_years(tag)[1:]
        ]
    return paths


def _check_sitemap_sizes() -> None:
    """A static file cannot serve `?p=2`: every sitemap section is one page."""
    for name, sitemap_class in SITEMAPS.items():
        if sitemap_class().paginator.num_pages > 1:
            raise CommandError(
                f"Sitemap section '{name}' exceeds {sitemap_class.limit} URLs: "
                "split it into several sections."
            )


def output_file(output_dir: Path, url_path: str) -> Path:
    relative = url_path.lstrip("/")
    if not relative or relative.endswith("/"):
        relative += "index.html"
    target = (output_dir / relative).resolve()
    if not target.is_relative_to(output_dir.resolve()):
        raise CommandError(f"Refusing to write outside the output dir: {url_path}")
    return target


class Command(BaseCommand):
    help = "Build the static site (HTML, RSS, sitemap, assets, thumbnails) into dist/."

    def add_arguments(self, parser):
        parser.add_argument("--output", type=Path, default=settings.DIST_DIR)
        parser.add_argument(
            "--workers",
            type=int,
            default=os.cpu_count() or 1,
            help="Rendering processes (default: number of CPUs).",
        )

    def handle(self, *args, output: Path, workers: int, **options):
        output = output.resolve()
        if output in {settings.BASE_DIR.resolve(), Path("/")}:
            raise CommandError(f"Unsafe output directory: {output}")
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)

        compile_scss(compressed=True)
        static_root = output / "static"
        with override_settings(
            DEBUG=False, STATIC_ROOT=static_root, STORAGES=MANIFEST_STORAGE
        ):
            call_command(
                "collectstatic",
                interactive=False,
                verbosity=0,
                ignore_patterns=["scss", "README.md"],
            )
            count = self._render_pages(output, workers)

        if settings.MEDIA_ROOT.is_dir():
            shutil.copytree(settings.MEDIA_ROOT, output / "media")
        if settings.ROOT_FILES_DIR.is_dir():
            shutil.copytree(settings.ROOT_FILES_DIR, output, dirs_exist_ok=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Built {count} pages into {output} ({settings.SITE_URL})."
            )
        )

    def _render_pages(self, output: Path, workers: int) -> int:
        _check_sitemap_sizes()
        paths = site_paths()
        workers = max(min(workers, len(paths) // 200), 1)  # Forks cost too.
        if workers == 1:
            _render_chunk(output, paths)
        else:
            chunks = [paths[index::workers] for index in range(workers)]
            context = multiprocessing.get_context("fork")
            with context.Pool(workers) as pool:
                pool.starmap(_render_chunk, [(output, chunk) for chunk in chunks])

        client, secure = _client()
        not_found = client.get(reverse("not_found"), secure=secure)
        Command._write(output / "404.html", not_found.content)
        return len(paths) + 1

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def _client() -> tuple[Client, bool]:
    client = Client(HTTP_HOST=settings.SITE_HOST, headers={"Accept-Language": "fr"})
    return client, settings.SITE_URL.startswith("https://")


def _render_chunk(output: Path, paths: list[str]) -> None:
    """Render some URLs (in a worker process, or inline)."""
    client, secure = _client()
    for url_path in paths:
        response = client.get(url_path, secure=secure)
        if response.status_code != 200:
            raise CommandError(f"{url_path} returned {response.status_code}")
        Command._write(output_file(output, url_path), response.content)
