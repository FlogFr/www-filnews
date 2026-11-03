from django.conf import settings
from django.contrib.sitemaps.views import index as sitemap_index
from django.contrib.sitemaps.views import sitemap
from django.urls import path, re_path
from django.views.static import serve

from . import views
from .feeds import NewsFeed
from .sitemaps import SITEMAPS

urlpatterns = [
    path("", views.home, name="home"),
    path("news/<slug:slug>/", views.news_detail, name="news_detail"),
    path("archives/", views.archive, name="archive"),
    re_path(
        r"^archives/(?P<year>[0-9]{4})/(?P<month>0[1-9]|1[0-2])/$",
        views.archive_month,
        name="archive_month",
    ),
    path("tags/", views.tag_index, name="tag_index"),
    path("tags/<slug:slug>/", views.tag_detail, name="tag_detail"),
    path("tags/<slug:slug>/timeline/", views.tag_timeline, name="tag_timeline"),
    path("tags/<slug:slug>/<int:year>/", views.tag_detail, name="tag_year"),
    path("presidentielle-2027/", views.election, name="election"),
    path(
        "presidentielle-2027/<slug:slug>/",
        views.election_candidate,
        name="election_candidate",
    ),
    path("a-propos/", views.about, name="about"),
    path("mentions-legales/", views.legal, name="legal"),
    path("rss.xml", NewsFeed(), name="rss"),
    path(
        "sitemap.xml",
        sitemap_index,
        {"sitemaps": SITEMAPS, "sitemap_url_name": "sitemap_section"},
        name="sitemap",
    ),
    path(
        "sitemap-<section>.xml",
        sitemap,
        {"sitemaps": SITEMAPS},
        name="sitemap_section",
    ),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("404.html", views.not_found, name="not_found"),
    # Reddit OAuth: only used locally through `runserver`.
    path("auth/reddit/login", views.reddit_login, name="reddit_login"),
    path("auth/reddit/callback", views.reddit_callback, name="reddit_callback"),
]

# Django never serves production traffic (nginx serves the static build), so
# serving thumbnails from here is only ever used by the local `runserver`.
urlpatterns += [
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]
