"""Analyzers enrich a News with tags, a summary and a thumbnail.

- `HeuristicAnalyzer` (default): article metadata + French keyword heuristics.
- `LocalModelAnalyzer`: same pipeline, but tags and summary come from local
  Hugging Face models (`pip install -e .[ml]`). Nothing leaves the machine.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import requests
from django.conf import settings
from PIL import UnidentifiedImageError

from ..models import News, tag_slug
from .extract import ArticleMetadata, extract_metadata
from .fetch import (
    FetchError,
    fetch_html,
    fetch_image,
    wayback_snapshot,
    wayback_url,
)
from .text import (
    extract_tags,
    is_valid_tag,
    normalize_tag,
    summarize,
    truncate_sentences,
)
from .thumbnails import make_thumbnail

logger = logging.getLogger(__name__)


class HeuristicAnalyzer:
    name = "heuristic"

    def __init__(self, media_root: Path, session: requests.Session | None = None):
        self.media_root = Path(media_root)
        self.session = session or requests.Session()
        self.max_tags = settings.FILNEWS_MAX_TAGS

    def analyze(self, news: News) -> News:
        metadata = self._metadata(news)
        news.tags = self.tags(news, metadata)
        news.summary = self.summary(news, metadata)
        news.thumbnail = self.thumbnail(news, metadata) or news.thumbnail
        news.analyzed_at = datetime.now(UTC)
        return news

    def _metadata(self, news: News) -> ArticleMetadata:
        try:
            return extract_metadata(fetch_html(self.session, news.url), news.url)
        except FetchError as exc:
            logger.warning("Could not fetch %s: %s", news.url, exc)
            if exc.dead and settings.FILNEWS_WAYBACK:
                return self._archived_metadata(news)
            return ArticleMetadata()

    def _archived_metadata(self, news: News) -> ArticleMetadata:
        """Metadata of the Wayback Machine copy of a dead article."""
        timestamp = wayback_snapshot(self.session, news.url, news.created_at)
        if not timestamp:
            return ArticleMetadata()
        try:
            html = fetch_html(self.session, wayback_url(timestamp, news.url))
        except FetchError as exc:
            logger.warning("Could not fetch the archive of %s: %s", news.url, exc)
            return ArticleMetadata()
        metadata = extract_metadata(html, news.url)
        metadata.archived_at = timestamp
        logger.info("Used the Wayback Machine copy of %s", news.url)
        return metadata

    def tags(self, news: News, metadata: ArticleMetadata) -> list[str]:
        return extract_tags(
            title=news.title,
            description=metadata.description,
            text=metadata.text,
            publisher_keywords=metadata.keywords,
            flair=news.flair,
            limit=self.max_tags,
            excluded=[metadata.site_name] if metadata.site_name else [],
        )

    def summary(self, news: News, metadata: ArticleMetadata) -> str:
        return summarize(metadata.description, metadata.text, news.selftext)

    def thumbnail(self, news: News, metadata: ArticleMetadata) -> str:
        relative = f"thumbnails/{news.id}.webp"
        candidates = [metadata.image, news.reddit_thumbnail]
        if metadata.archived_at and metadata.image:
            # The image of a dead article is often gone too.
            candidates.insert(
                1, wayback_url(metadata.archived_at, metadata.image, "im_")
            )
        for url in candidates:
            if not url:
                continue
            try:
                make_thumbnail(
                    fetch_image(self.session, url), self.media_root / relative
                )
            except (FetchError, UnidentifiedImageError, OSError) as exc:
                logger.warning("Thumbnail failed for %s (%s): %s", news.id, url, exc)
                continue
            return relative
        return ""


class LocalModelAnalyzer(HeuristicAnalyzer):
    """Tags and summary from local transformers models."""

    name = "local"
    keyword_model = os.environ.get(
        "FILNEWS_KEYWORD_MODEL", "yanekyuk/camembert-keyword-extractor"
    )
    summary_model = os.environ.get(
        "FILNEWS_SUMMARY_MODEL", "plguillou/t5-base-fr-sum-cnndm"
    )

    def __init__(self, media_root: Path, session: requests.Session | None = None):
        super().__init__(media_root, session)
        try:
            from transformers import (
                AutoModelForSeq2SeqLM,
                AutoTokenizer,
                pipeline,
            )
        except ImportError as exc:
            raise RuntimeError(
                "The local analyzer needs the ML extras: pip install -e '.[ml]'"
            ) from exc
        self._keywords = pipeline(
            "token-classification",
            model=self.keyword_model,
            aggregation_strategy="simple",
        )
        # Called directly: the "summarization" pipeline was removed in
        # transformers 5.
        self._summary_tokenizer = AutoTokenizer.from_pretrained(self.summary_model)
        self._summarizer = AutoModelForSeq2SeqLM.from_pretrained(self.summary_model)

    def tags(self, news: News, metadata: ArticleMetadata) -> list[str]:
        source = " ".join(filter(None, [news.title, metadata.description]))
        source = f"{source}. {metadata.text[:1500]}"
        found = sorted(self._keywords(source), key=lambda e: e["score"], reverse=True)
        excluded = {tag_slug(metadata.site_name)} if metadata.site_name else set()
        # Slice the source text rather than using entity["word"], which holds
        # tokenizer artefacts ("<unk>", "d'-").
        model_tags = [
            normalize_tag(source[entity["start"] : entity["end"]])
            for entity in found
            if entity.get("start") is not None
        ]
        heuristic = super().tags(news, metadata)
        merged: list[str] = []
        for tag in [*model_tags, *heuristic]:
            slugs = {tag_slug(t) for t in merged}
            if is_valid_tag(tag, excluded) and tag_slug(tag) not in slugs:
                merged.append(tag)
        return merged[: self.max_tags]

    def summary(self, news: News, metadata: ArticleMetadata) -> str:
        source = metadata.text or metadata.description
        if len(source) < 400:
            return super().summary(news, metadata)
        inputs = self._summary_tokenizer(
            source[:4000], return_tensors="pt", truncation=True, max_length=512
        )
        output = self._summarizer.generate(
            **inputs, max_new_tokens=120, min_new_tokens=30, num_beams=4
        )
        text = self._summary_tokenizer.decode(output[0], skip_special_tokens=True)
        return truncate_sentences(text.strip(), 320)


ANALYZERS = {cls.name: cls for cls in (HeuristicAnalyzer, LocalModelAnalyzer)}


def get_analyzer(name: str | None = None, **kwargs) -> HeuristicAnalyzer:
    name = name or settings.FILNEWS_ANALYZER
    try:
        analyzer_class = ANALYZERS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown analyzer {name!r}; choose one of {', '.join(ANALYZERS)}."
        ) from exc
    return analyzer_class(media_root=settings.MEDIA_ROOT, **kwargs)
