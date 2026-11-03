import json

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import SafeString, mark_safe

from ..models import News
from ..store import get_store
from ..vocabulary import lookup

register = template.Library()

_JSON_ESCAPES = {ord(">"): "\\u003E", ord("<"): "\\u003C", ord("&"): "\\u0026"}


@register.filter
def absolute(path: str) -> str:
    """Turn a site-relative path into an absolute URL on SITE_URL."""
    return f"{settings.SITE_URL}{path}"


@register.filter
def has_tag_page(tag) -> bool:
    """Whether a tag (Tag or TagSummary) has enough news for its own page."""
    # No refresh: called for every tag of every card; the view already did.
    return get_store(refresh=False).tag_page(tag.slug) is not None


@register.filter
def tag_kind(tag) -> str:
    """ "personnalite" or "theme" for a tag of the vocabulary, else ""."""
    entry = lookup(tag.name)
    return entry.kind if entry else ""


@register.filter
def tag_kind_label(tag) -> str:
    entry = lookup(tag.name)
    return entry.kind_label if entry else ""


@register.filter
def media_url(relative_path: str) -> str:
    return f"{settings.MEDIA_URL}{relative_path}" if relative_path else ""


def _ld_script(data: dict) -> SafeString:
    # Same approach as Django's json_script: escaping <, > and & makes the
    # JSON safe inside <script>; HTML-escaping it would corrupt the JSON.
    payload = json.dumps(data, ensure_ascii=False).translate(_JSON_ESCAPES)
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')  # noqa: S308


@register.simple_tag
def website_ld() -> SafeString:
    return _ld_script(
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": settings.SITE_NAME,
            "url": f"{settings.SITE_URL}/",
            "inLanguage": "fr-FR",
            "description": settings.SITE_TAGLINE,
        }
    )


@register.simple_tag
def news_article_ld(news: News) -> SafeString:
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": news.title[:110],
        "datePublished": news.created_at.isoformat(),
        "dateModified": (news.analyzed_at or news.ingested_at).isoformat(),
        "mainEntityOfPage": absolute(reverse("news_detail", args=[news.slug])),
        "url": absolute(reverse("news_detail", args=[news.slug])),
        "isBasedOn": news.url,
        "inLanguage": "fr-FR",
        "keywords": ", ".join(news.tags),
        "publisher": {
            "@type": "Organization",
            "name": settings.SITE_NAME,
            "url": f"{settings.SITE_URL}/",
            "logo": {"@type": "ImageObject", "url": absolute(static("img/logo.png"))},
        },
        "author": {"@type": "Organization", "name": news.domain or settings.SITE_NAME},
    }
    if news.summary:
        data["description"] = news.summary
    if news.thumbnail:
        data["image"] = [absolute(media_url(news.thumbnail))]
    return _ld_script(data)


@register.simple_tag
def breadcrumb_ld(*crumbs: str) -> SafeString:
    """Usage: {% breadcrumb_ld "Accueil" "/" "Tags" "/tags/" %}"""
    pairs = list(zip(crumbs[::2], crumbs[1::2], strict=True))
    return _ld_script(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": name,
                    "item": absolute(path),
                }
                for index, (name, path) in enumerate(pairs, start=1)
            ],
        }
    )
