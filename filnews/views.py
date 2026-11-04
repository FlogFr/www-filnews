from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from . import elections
from .insights import news_context, tag_profile
from .models import TagSummary, tag_slug
from .reddit import RedditClient, RedditError
from .store import NewsStore, get_store
from .timeline import build_thread, build_timeline, thread_entries, thread_years

OAUTH_STATE_COOKIE = "reddit_oauth_state"
OAUTH_STATE_MAX_AGE = 600
RELATED_NEWS_COUNT = 5
# "Fils du moment": tags with the most news over this period.
TRENDING_PERIOD = timedelta(days=7)
# The Fil shown next to the headline: the busiest tag over this period.
FEATURED_PERIOD = timedelta(hours=48)


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    store = get_store()
    now = timezone.now()
    headline = store.most_popular(since=now - timedelta(hours=24))
    if headline is None:
        latest = store.latest(1)
        headline = latest[0] if latest else None
    exclude = [headline.id] if headline else []
    return render(
        request,
        "home.html",
        {
            "headline": headline,
            "featured": _featured_thread(store),
            "news_list": store.latest(settings.FILNEWS_HOME_NEWS_COUNT, exclude),
            "trending_tags": _trending_tags(store, now - TRENDING_PERIOD),
            "election_name": elections.ELECTION_NAME,
            "candidates": [c for c in elections.CANDIDATES if c.is_declared],
        },
    )


def _featured_thread(store: NewsStore) -> dict | None:
    """The Fil of the tag with the most news in the 48 hours before the
    latest news (the site may not have been updated today)."""
    latest = store.latest(1)
    if not latest:
        return None
    since = latest[0].created_at - FEATURED_PERIOD
    tag = next(iter(_busiest_tags(store, since)), None)
    if tag is None:
        return None
    entries = thread_entries(tag.news[: settings.FILNEWS_HOME_THREAD_COUNT])
    # Each news says how long before it the next (older) one came.
    gaps = [entry.gap for entry in entries[1:]] + [""]
    return {
        "tag": tag,
        "thread": [
            {"news": entry.news, "gap_after": gap}
            for entry, gap in zip(entries, gaps, strict=True)
        ],
    }


def _trending_tags(store: NewsStore, since: datetime) -> list[TagSummary]:
    return _busiest_tags(store, since)[: settings.FILNEWS_HOME_TAG_COUNT]


def _busiest_tags(store: NewsStore, since: datetime) -> list[TagSummary]:
    """Tags with a page, by number of news since `since` (then most recent)."""
    counts: dict[str, int] = {}
    for news in store.all():
        if news.created_at < since:
            break
        for name in news.tags:
            slug = tag_slug(name)
            counts[slug] = counts.get(slug, 0) + 1
    tags = [tag for slug in counts if (tag := store.tag_page(slug))]
    tags.sort(key=lambda tag: (counts[tag.slug], tag.last_seen), reverse=True)
    return tags


@require_GET
def news_detail(request: HttpRequest, slug: str) -> HttpResponse:
    store = get_store()
    news = store.get_by_slug(slug)
    if news is None:
        raise Http404("News not found")
    return render(
        request,
        "news/detail.html",
        {
            "news": news,
            "insight": news_context(store, news),
            "related": store.related(news, RELATED_NEWS_COUNT),
            "indexable": settings.FILNEWS_INDEX_NEWS,
        },
    )


def _month_date(year: int, month: int) -> datetime:
    return datetime(year, month, 1, tzinfo=timezone.get_current_timezone())


@require_GET
def archive(request: HttpRequest) -> HttpResponse:
    """Every month with news, grouped by year."""
    years: dict[int, list[dict]] = {}
    store = get_store()
    for year, month, count in store.months():
        years.setdefault(year, []).append(
            {
                "year": year,
                "month": month,
                "count": count,
                "date": _month_date(year, month),
            }
        )
    return render(
        request,
        "news/archive.html",
        {"years": list(years.items()), "total": len(store)},
    )


@require_GET
def archive_month(request: HttpRequest, year: str, month: str) -> HttpResponse:
    store = get_store()
    year_number, month_number = int(year), int(month)
    news_list = store.month(year_number, month_number)
    if not news_list:
        raise Http404("No news this month")
    months = [(y, m) for y, m, _ in store.months()]
    index = months.index((year_number, month_number))
    newer = months[index - 1] if index > 0 else None
    older = months[index + 1] if index + 1 < len(months) else None
    days: dict = {}
    for news in news_list:
        days.setdefault(timezone.localtime(news.created_at).date(), []).append(news)
    return render(
        request,
        "news/archive_month.html",
        {
            "month_date": _month_date(year_number, month_number),
            "news_count": len(news_list),
            "days": list(days.items()),
            "newer": newer and _month_link(*newer),
            "older": older and _month_link(*older),
        },
    )


def _month_link(year: int, month: int) -> dict:
    return {
        "url": reverse("archive_month", args=[f"{year:04d}", f"{month:02d}"]),
        "date": _month_date(year, month),
    }


@require_GET
def tag_index(request: HttpRequest) -> HttpResponse:
    """Tags with a page, grouped by initial letter."""
    tags = sorted(get_store().page_tags(), key=lambda t: t.name.casefold())
    letters: dict[str, list[TagSummary]] = {}
    for tag in tags:
        letters.setdefault(_initial(tag.name), []).append(tag)
    return render(
        request,
        "tags/index.html",
        {"tags": tags, "letters": sorted(letters.items(), key=lambda kv: kv[0] == "#")},
    )


def _initial(name: str) -> str:
    """Upper-case initial without accent ("É" -> "E"), "#" if not a letter."""
    letter = slugify(name[:1]).upper()
    return letter if letter.isalpha() else "#"


def _get_tag(slug: str) -> TagSummary:
    tag = get_store().tag_page(slug)
    if tag is None:
        raise Http404("Tag not found")
    return tag


@require_GET
def tag_detail(
    request: HttpRequest, slug: str, year: int | None = None
) -> HttpResponse:
    """The tag's Fil. Big tags are split by year; the main page shows the
    most recent year."""
    tag = _get_tag(slug)
    years = thread_years(tag)
    if year is not None:
        if not years or year == years[0][0]:  # Same content as the main page.
            return redirect("tag_detail", slug=slug, permanent=True)
        if year not in dict(years):
            raise Http404("No news this year")
    elif years:
        year = years[0][0]
    return render(
        request,
        "tags/detail.html",
        {
            "tag": tag,
            "profile": tag_profile(get_store(), tag),
            "thread": build_thread(tag, year if years else None),
            "years": years,
            "year": year if years else None,
            "is_latest_year": bool(years) and year == years[0][0],
        },
    )


@require_GET
def tag_timeline(request: HttpRequest, slug: str) -> HttpResponse:
    """HTML fragment loaded by the tag hover card."""
    tag = _get_tag(slug)
    context = {
        "tag": tag,
        "latest": tag.news[: settings.FILNEWS_TAG_CARD_NEWS_COUNT],
        "timeline": build_timeline(tag),
    }
    return render(request, "tags/timeline.html", context)


@require_GET
def election(request: HttpRequest) -> HttpResponse:
    """The Fil of the presidential election and the list of candidates."""
    store = get_store()
    candidates = [
        {
            "candidate": candidate,
            "count": len(elections.candidate_news(store, candidate)),
            "tags": [t for t in map(store.tag_page, candidate.tag_slugs) if t],
        }
        for candidate in elections.CANDIDATES
    ]
    return render(
        request,
        "elections/index.html",
        {
            "election_name": elections.ELECTION_NAME,
            "first_round": elections.FIRST_ROUND,
            "campaign_start": elections.CAMPAIGN_START,
            "candidates": candidates,
            "thread": thread_entries(elections.election_news(store)),
        },
    )


@require_GET
def election_candidate(request: HttpRequest, slug: str) -> HttpResponse:
    candidate = elections.get_candidate(slug)
    if candidate is None:
        raise Http404("Unknown candidate")
    store = get_store()
    return render(
        request,
        "elections/candidate.html",
        {
            "election_name": elections.ELECTION_NAME,
            "campaign_start": elections.CAMPAIGN_START,
            "candidate": candidate,
            "tags": [t for t in map(store.tag_page, candidate.tag_slugs) if t],
            "thread": thread_entries(elections.candidate_news(store, candidate)),
        },
    )


@require_GET
def legal(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "legal.html",
        {
            "source_url": settings.SITE_SOURCE_URL,
            "subreddit": settings.FILNEWS_SUBREDDIT,
        },
    )


@require_GET
def about(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "about.html",
        {
            "subreddit": settings.FILNEWS_SUBREDDIT,
            "source_url": settings.SITE_SOURCE_URL,
        },
    )


@require_GET
def robots_txt(request: HttpRequest) -> HttpResponse:
    return render(request, "robots.txt", content_type="text/plain; charset=utf-8")


@require_GET
def not_found(request: HttpRequest) -> HttpResponse:
    return render(request, "404.html", status=404)


# --- Reddit OAuth (local tooling only, never part of the static build) ------


@require_GET
def reddit_login(request: HttpRequest) -> HttpResponse:
    try:
        client = RedditClient.from_settings()
    except RedditError as exc:
        return HttpResponseBadRequest(str(exc))
    state = secrets.token_urlsafe(32)
    response = redirect(client.authorize_url(state))
    response.set_signed_cookie(
        OAUTH_STATE_COOKIE,
        state,
        salt="reddit-oauth",
        max_age=OAUTH_STATE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


@require_GET
def reddit_callback(request: HttpRequest) -> HttpResponse:
    expected = request.get_signed_cookie(
        OAUTH_STATE_COOKIE, default="", salt="reddit-oauth", max_age=OAUTH_STATE_MAX_AGE
    )
    state = request.GET.get("state", "")
    if not expected or not constant_time_compare(expected, state):
        return HttpResponseBadRequest("Invalid OAuth state.")
    if "error" in request.GET:
        return HttpResponseBadRequest(f"Reddit refused access: {request.GET['error']}")
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("Missing authorization code.")
    try:
        RedditClient.from_settings().exchange_code(code)
    except RedditError as exc:
        return HttpResponseBadRequest(str(exc))
    response = render(request, "auth/reddit_done.html")
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response
