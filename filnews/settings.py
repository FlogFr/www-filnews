"""FilNews settings.

Every value that differs between machines comes from an environment variable
(optionally loaded from a `.env` file at the project root). Secrets are never
hard-coded here.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR / "filnews"

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# --- Core ------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", default=False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        # Only the build and the local OAuth flow ever run Django: the
        # production container is plain nginx serving static files.
        SECRET_KEY = "filnews-static-build-only"  # noqa: S105
    else:
        SECRET_KEY = "filnews-insecure-dev-key"  # noqa: S105

INSTALLED_APPS = [
    # First, so that its `runserver` overrides the staticfiles one.
    "filnews.apps.FilNewsConfig",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

# Public URL of the site, used for canonical links, sitemap and RSS.
SITE_URL = os.environ.get("SITE_URL", "https://filnews.fr").rstrip("/")
SITE_HOST = urlparse(SITE_URL).netloc

# The static build renders pages as if requested on SITE_HOST.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver", SITE_HOST]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "filnews.urls"
WSGI_APPLICATION = "filnews.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PROJECT_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "filnews.context_processors.site",
            ],
        },
    },
]

# No relational database: news live in JSON files (see filnews/store.py).
DATABASES = {}

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# --- Static files ----------------------------------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [PROJECT_DIR / "static"]
STATIC_ROOT = BASE_DIR / "dist" / "static"
# Copied as-is at the root of the built site (e.g. search engine verification).
ROOT_FILES_DIR = PROJECT_DIR / "root"
STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

MEDIA_URL = "/media/"

# --- FilNews ---------------------------------------------------------------

SITE_NAME = "FilNews"
SITE_TAGLINE = "L'actualité vue par r/france"
# Public source code (transparency), linked from the legal notice.
SITE_SOURCE_URL = "https://github.com/FlogFr/www-filnews"

# Local file "database".
DATA_DIR = Path(os.environ.get("FILNEWS_DATA_DIR", BASE_DIR / "data"))
MEDIA_ROOT = DATA_DIR / "media"
DIST_DIR = Path(os.environ.get("FILNEWS_DIST_DIR", BASE_DIR / "dist"))

# Ingestion: only posts with at least FILNEWS_MIN_SCORE upvotes are kept.
FILNEWS_SUBREDDIT = os.environ.get("FILNEWS_SUBREDDIT", "france")
FILNEWS_MIN_SCORE = env_int("FILNEWS_MIN_SCORE", 250)
# History import: also keep the N best articles of each month and of each day
# (scores were much lower in old years).
FILNEWS_BACKFILL_TOP = env_int("FILNEWS_BACKFILL_TOP", 60)
FILNEWS_BACKFILL_DAY_TOP = env_int("FILNEWS_BACKFILL_DAY_TOP", 2)
# ... but only if they have at least this score.
FILNEWS_BACKFILL_DAY_MIN_SCORE = env_int("FILNEWS_BACKFILL_DAY_MIN_SCORE", 20)

# Media policy (filnews/media.py): only recognised news media are ingested;
# set to false to accept any site that is not explicitly blocked.
FILNEWS_MEDIA_WHITELIST = env_bool("FILNEWS_MEDIA_WHITELIST", True)

# Analysis backend: "heuristic" or "local" (transformers model).
FILNEWS_ANALYZER = os.environ.get("FILNEWS_ANALYZER", "heuristic")
FILNEWS_MAX_TAGS = env_int("FILNEWS_MAX_TAGS", 5)
# Parallel downloads of `analyze_news` (at most 2 at a time per site).
FILNEWS_ANALYZE_WORKERS = env_int("FILNEWS_ANALYZE_WORKERS", 8)
# Dead articles (404, 410, 403…): use their Wayback Machine copy (archive.org).
FILNEWS_WAYBACK = env_bool("FILNEWS_WAYBACK", True)

# Tag hover card: number of news listed above the timeline.
FILNEWS_TAG_CARD_NEWS_COUNT = 5

# Home page.
FILNEWS_HOME_NEWS_COUNT = 5
FILNEWS_HOME_TAG_COUNT = 7  # "Fils du moment".
FILNEWS_HOME_THREAD_COUNT = 5  # News of the featured Fil, next to the headline.

# Tags: a page (and a hover card) only from this number of news; the Fil of
# a bigger tag is split by year; its timeline shows bars instead of dots.
FILNEWS_TAG_MIN_NEWS = 2
FILNEWS_TAG_THREAD_SIZE = 60
FILNEWS_TIMELINE_MAX_DOTS = 40

# SEO: news pages mostly repeat their source (title, description), so they
# are "noindex, follow" and left out of the sitemap; the Fils carry the
# original content. Set to true to index them again.
FILNEWS_INDEX_NEWS = env_bool("FILNEWS_INDEX_NEWS", False)

# Reddit API — secrets come from the environment only.
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_REDIRECT_URI = os.environ.get(
    "REDDIT_REDIRECT_URI", "http://localhost:8000/auth/reddit/callback"
)
REDDIT_USER_AGENT = os.environ.get(
    "REDDIT_USER_AGENT", "web:fr.filnews:v1.0 (by /u/filnews)"
)
REDDIT_TOKEN_FILE = DATA_DIR / ".secrets" / "reddit_token.json"

# HTTP client used for article fetching.
HTTP_TIMEOUT = 15
HTTP_USER_AGENT = "Mozilla/5.0 (compatible; FilNewsBot/1.0; +https://filnews.fr)"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"filnews": {"handlers": ["console"], "level": "INFO"}},
}
