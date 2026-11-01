"""Extract metadata and readable text from an article page."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

MAX_TEXT_CHARS = 20_000
MIN_PARAGRAPH_CHARS = 60


@dataclass
class ArticleMetadata:
    title: str = ""
    description: str = ""
    image: str = ""
    keywords: list[str] = field(default_factory=list)
    text: str = ""
    site_name: str = ""
    archived_at: str = ""  # Wayback Machine timestamp when the page was dead.


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content", "").strip():
            return " ".join(tag["content"].split())
    return ""


def _keywords(soup: BeautifulSoup) -> list[str]:
    values = [
        tag.get("content", "")
        for tag in soup.find_all("meta", attrs={"property": "article:tag"})
    ]
    values.append(_meta(soup, "news_keywords", "keywords"))
    keywords: list[str] = []
    for value in values:
        keywords.extend(part.strip() for part in re.split(r"[,;|]", value))
    return [k for k in keywords if k]


def _text(soup: BeautifulSoup) -> str:
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = []
    total = 0
    for paragraph in root.find_all("p"):
        content = " ".join(paragraph.get_text(" ", strip=True).split())
        if len(content) < MIN_PARAGRAPH_CHARS:
            continue
        paragraphs.append(content)
        total += len(content)
        if total > MAX_TEXT_CHARS:
            break
    return "\n".join(paragraphs)


def extract_metadata(html: str, base_url: str) -> ArticleMetadata:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "nav", "footer", "aside"]):
        node.decompose()
    image = _meta(soup, "og:image", "og:image:url", "twitter:image")
    return ArticleMetadata(
        title=_meta(soup, "og:title", "twitter:title")
        or (soup.title.get_text(strip=True) if soup.title else ""),
        description=_meta(soup, "og:description", "description", "twitter:description"),
        image=urljoin(base_url, image) if image else "",
        keywords=_keywords(soup),
        text=_text(soup),
        site_name=_meta(soup, "og:site_name", "application-name"),
    )
