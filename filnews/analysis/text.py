"""Language heuristics for French news: tags and summaries."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from ..vocabulary import entries, flair_theme

SUMMARY_MAX_CHARS = 320
MIN_SUMMARY_CHARS = 60

# Weight of a match by where it is found. A person needs MIN_SCORE; a theme,
# whose words are common, THEME_MIN_SCORE (in the title, or confirmed twice).
TITLE_WEIGHT = 4
DESCRIPTION_WEIGHT = 2
KEYWORD_WEIGHT = 2
FLAIR_WEIGHT = 3
BODY_WEIGHT = 0.5
BODY_MAX_MENTIONS = 6
MIN_SCORE = 2
THEME_MIN_SCORE = 3
BODY_MAX_CHARS = 8000

SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")


def _clean(text: str) -> str:
    return " ".join(text.replace("’", "'").replace("\u00a0", " ").split())


def extract_tags(
    title: str,
    description: str = "",
    text: str = "",
    publisher_keywords: Iterable[str] = (),
    flair: str = "",
    limit: int = 5,
) -> list[str]:
    """Political figures and themes of the controlled vocabulary
    (`filnews.vocabulary`) found in the article, best scored first.

    Nothing outside the vocabulary is ever returned: a capitalised word is
    not a topic ("Heures" from "20 Heures"), nor is a Reddit flair such as
    "Paywall".
    """
    title, description = _clean(title), _clean(description)
    body = _clean(text[:BODY_MAX_CHARS])
    keywords = _clean(" | ".join(publisher_keywords))
    flair_tag = flair_theme(flair)
    scores: Counter[str] = Counter()
    kinds: dict[str, str] = {}
    for entry in entries():
        score = 0.0
        if entry.pattern.search(title):
            score += TITLE_WEIGHT
        if description and entry.pattern.search(description):
            score += DESCRIPTION_WEIGHT
        if keywords and entry.pattern.search(keywords):
            score += KEYWORD_WEIGHT
        if body:
            score += BODY_WEIGHT * min(entry.count(body), BODY_MAX_MENTIONS)
        if entry.name == flair_tag:
            score += FLAIR_WEIGHT
        if score >= (MIN_SCORE if entry.kind == "personnalite" else THEME_MIN_SCORE):
            scores[entry.name] = score
            kinds[entry.name] = entry.kind
    # Best score first; on a tie, people before themes (more specific).
    ranked = sorted(
        scores, key=lambda name: (-scores[name], kinds[name] != "personnalite")
    )
    return ranked[:limit]


def summarize(*candidates: str, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """Pick the first meaningful candidate and cut it on a sentence boundary."""
    for candidate in candidates:
        text = " ".join((candidate or "").split())
        if len(text) >= MIN_SUMMARY_CHARS:
            return truncate_sentences(text, max_chars)
    return ""


def truncate_sentences(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    summary = ""
    for sentence in SENTENCE_END_RE.split(text):
        if len(summary) + len(sentence) + 1 > max_chars:
            break
        summary = f"{summary} {sentence}".strip()
    if summary:
        return summary
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut}…"
