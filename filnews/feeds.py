from django.conf import settings
from django.contrib.syndication.views import Feed
from django.urls import reverse
from django.utils.feedgenerator import Rss201rev2Feed

from .models import News
from .store import get_store


class NewsFeed(Feed):
    """Every news, newest first."""

    feed_type = Rss201rev2Feed
    title = f"{settings.SITE_NAME} — {settings.SITE_TAGLINE}"
    description = "L'actualité qui suscite le plus d'intérêt, résumée et remise dans son contexte."
    language = "fr"

    def link(self):
        return reverse("home")

    def items(self):
        return get_store().all()

    def item_title(self, item: News) -> str:
        return item.title

    def item_description(self, item: News) -> str:
        return item.summary or item.title

    def item_link(self, item: News) -> str:
        return reverse("news_detail", args=[item.slug])

    def item_guid(self, item: News) -> str:
        return f"{settings.SITE_URL}{self.item_link(item)}"

    item_guid_is_permalink = True

    def item_pubdate(self, item: News):
        return item.created_at

    def item_updateddate(self, item: News):
        return item.analyzed_at or item.ingested_at

    def item_categories(self, item: News) -> list[str]:
        return item.tags

    def item_author_name(self, item: News) -> str:
        return item.domain
