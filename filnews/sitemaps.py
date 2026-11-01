from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import News, TagSummary
from .store import get_store
from .timeline import thread_years


class StaticSitemap(Sitemap):
    changefreq = "hourly"

    def items(self):
        months = [
            ("archive_month", (f"{year:04d}", f"{month:02d}"))
            for year, month, _ in get_store().months()
        ]
        return [
            ("home", ()),
            ("archive", ()),
            ("tag_index", ()),
            ("about", ()),
            *months,
        ]

    def location(self, item):
        name, args = item
        return reverse(name, args=args)

    def priority(self, item):
        return 1.0 if item[0] == "home" else 0.5


class NewsSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return get_store().all()

    def location(self, item: News) -> str:
        return reverse("news_detail", args=[item.slug])

    def lastmod(self, item: News):
        return item.analyzed_at or item.ingested_at


class TagSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        """Tag pages, then the older years of tags split by year."""
        items = []
        for tag in get_store().page_tags():
            items.append((tag, None))
            items += [(tag, year) for year, _ in thread_years(tag)[1:]]
        return items

    def location(self, item: tuple[TagSummary, int | None]) -> str:
        tag, year = item
        if year is None:
            return reverse("tag_detail", args=[tag.slug])
        return reverse("tag_year", args=[tag.slug, year])

    def lastmod(self, item: tuple[TagSummary, int | None]):
        return item[0].last_seen


SITEMAPS = {"pages": StaticSitemap, "news": NewsSitemap, "tags": TagSitemap}
