"""Bounded HTTP downloads for article pages and images."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

import requests
from django.conf import settings

MAX_HTML_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024

WAYBACK_API = "https://archive.org/wayback/available"
# Statuses of an article that is gone or refuses robots: worth an archived copy.
DEAD_STATUSES = {401, 403, 404, 410, 451}


class FetchError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, unreachable=False):
        super().__init__(message)
        self.status = status
        self.unreachable = unreachable  # DNS, timeout, refused connection…

    @property
    def dead(self) -> bool:
        return self.unreachable or self.status in DEAD_STATUSES


def _download(session: requests.Session, url: str, max_bytes: int, accept: str):
    if urlparse(url).scheme not in {"http", "https"}:
        raise FetchError(f"Unsupported URL scheme: {url}")
    try:
        with session.get(
            url,
            headers={"User-Agent": settings.HTTP_USER_AGENT, "Accept": accept},
            timeout=settings.HTTP_TIMEOUT,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise FetchError(
                    f"HTTP {response.status_code} for {url}", response.status_code
                )
            chunks, size = [], 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError(f"Response too large: {url}")
                chunks.append(chunk)
            return response, b"".join(chunks)
    except requests.RequestException as exc:
        raise FetchError(str(exc), unreachable=True) from exc


def fetch_html(session: requests.Session, url: str) -> str:
    response, body = _download(session, url, MAX_HTML_BYTES, "text/html,*/*;q=0.8")
    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type:
        raise FetchError(f"Not an HTML page ({content_type}): {url}")
    encoding = response.encoding or "utf-8"
    if encoding.lower() == "iso-8859-1" and b"charset" not in body[:2048].lower():
        # requests' default for text/* without charset; most sites are UTF-8.
        encoding = "utf-8"
    return body.decode(encoding, errors="replace")


def fetch_image(session: requests.Session, url: str) -> bytes:
    response, body = _download(session, url, MAX_IMAGE_BYTES, "image/*")
    if not response.headers.get("Content-Type", "").startswith("image/"):
        raise FetchError(f"Not an image: {url}")
    return body


def wayback_snapshot(session: requests.Session, url: str, when: datetime) -> str:
    """Timestamp of the Wayback Machine copy of `url` closest to `when`, or ""."""
    try:
        response = session.get(
            WAYBACK_API,
            params={"url": url, "timestamp": when.strftime("%Y%m%d")},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT,
        )
        closest = response.json()["archived_snapshots"]["closest"]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return ""
    if not closest.get("available") or str(closest.get("status")) != "200":
        return ""
    return str(closest.get("timestamp", ""))


def wayback_url(timestamp: str, url: str, kind: str = "id_") -> str:
    """Raw archived content (`id_`: page, `im_`: image), without the toolbar."""
    return f"https://web.archive.org/web/{timestamp}{kind}/{url}"
