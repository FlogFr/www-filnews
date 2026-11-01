"""Language heuristics for French news: keywords and summaries."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from ..models import tag_slug

SUMMARY_MAX_CHARS = 320
MIN_SUMMARY_CHARS = 60

# Capitalised words that are not entities (sentence starts, function words…).
STOPWORDS = frozenset(
    [
        "a",
        "à",
        "afin",
        "ai",
        "alors",
        "après",
        "au",
        "aucun",
        "aujourd",
        "aussi",
        "autre",
        "aux",
        "avant",
        "avec",
        "avoir",
        "bien",
        "c",
        "ça",
        "car",
        "ce",
        "cela",
        "celle",
        "celui",
        "ces",
        "cet",
        "cette",
        "chaque",
        "chez",
        "ci",
        "comme",
        "comment",
        "d",
        "dans",
        "de",
        "depuis",
        "des",
        "deux",
        "doit",
        "donc",
        "dont",
        "du",
        "elle",
        "elles",
        "en",
        "encore",
        "entre",
        "est",
        "et",
        "été",
        "être",
        "eux",
        "face",
        "fait",
        "faut",
        "hier",
        "il",
        "ils",
        "j",
        "je",
        "jusqu",
        "l",
        "la",
        "le",
        "les",
        "leur",
        "leurs",
        "lors",
        "lui",
        "m",
        "ma",
        "mais",
        "me",
        "même",
        "mes",
        "moins",
        "mon",
        "n",
        "ne",
        "ni",
        "non",
        "nos",
        "notre",
        "nous",
        "on",
        "ont",
        "ou",
        "où",
        "par",
        "parce",
        "pas",
        "pendant",
        "peu",
        "peut",
        "plus",
        "pour",
        "pourquoi",
        "qu",
        "quand",
        "que",
        "quel",
        "quelle",
        "quelles",
        "quels",
        "qui",
        "quoi",
        "s",
        "sa",
        "sans",
        "se",
        "selon",
        "ses",
        "si",
        "son",
        "sont",
        "sous",
        "sur",
        "ta",
        "te",
        "tes",
        "ton",
        "tous",
        "tout",
        "toute",
        "toutes",
        "très",
        "trop",
        "tu",
        "un",
        "une",
        "vers",
        "via",
        "voici",
        "voilà",
        "vos",
        "votre",
        "vous",
        "y",
        "lundi",
        "mardi",
        "mercredi",
        "jeudi",
        "vendredi",
        "samedi",
        "dimanche",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
        "selon",
        "exclusif",
        "vidéo",
        "direct",
        "live",
        "info",
        "infos",
        "photo",
        "photos",
        "article",
        "the",
        "of",
        "and",
        "to",
        "in",
        "for",
        "on",
        "with",
    ]
)

# Words allowed inside a multi-word entity: "Banque de France", "Jean-Luc".
CONNECTORS = frozenset({"de", "du", "des", "d'", "la", "le", "et"})

# Generic Reddit flairs that make poor tags.
GENERIC_FLAIRS = frozenset(
    {"actus", "actualité", "actualités", "paywall", "meta", "forum libre", "news"}
)

# Publisher keywords that are too broad to be useful.
GENERIC_KEYWORDS = frozenset(
    {"actualité", "actualités", "actu", "news", "info", "infos", "france", "article"}
)

TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ0-9][\wÀ-ÖØ-öø-ÿŒœ'’-]*")
SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+")
# Punctuation that always ends an entity.
CLAUSE_BREAK_RE = re.compile(r"[:;,()\[\]«»\"“”!?…|/]|\s[-–—]\s")
ACRONYM_RE = re.compile(r"^[A-ZÀ-Ý]{2,6}$")


def _is_capitalised(word: str) -> bool:
    return word[:1].isupper()


def _clean_token(token: str) -> str:
    token = token.replace("’", "'")
    # Strip elisions: "l'Assemblée" -> "Assemblée", "d'Emmanuel" -> "Emmanuel".
    if len(token) > 2 and token[1] == "'" and token[0].lower() in "cdjlmnst":
        token = token[2:]
    return token.strip("'-")


def candidate_entities(text: str) -> list[str]:
    """Return capitalised word sequences and acronyms found in `text`.

    A lone capitalised word opening a clause is ignored: it is usually a
    sentence start rather than a proper noun.
    """
    entities: list[str] = []
    clauses = (
        clause
        for sentence in SENTENCE_END_RE.split(text)
        for clause in CLAUSE_BREAK_RE.split(sentence)
    )
    for clause in clauses:
        tokens = [_clean_token(t) for t in TOKEN_RE.findall(clause)]
        current: list[str] = []
        for index, token in enumerate(tokens):
            lower = token.lower()
            if token and _is_capitalised(token) and lower not in STOPWORDS:
                if index == 0 and not ACRONYM_RE.match(token):
                    nxt = tokens[1] if len(tokens) > 1 else ""
                    if not (nxt and _is_capitalised(nxt)):
                        continue
                current.append(token)
            elif current and lower in CONNECTORS:
                current.append(lower)
            elif current and token.isdigit() and len(token) <= 4:
                # "Ligue 1", "Paris 2024".
                current.append(token)
                entities.extend(_flush(current))
                current = []
            else:
                entities.extend(_flush(current))
                current = []
        entities.extend(_flush(current))
    return entities


def _flush(words: list[str]) -> list[str]:
    while words and words[-1] in CONNECTORS:
        words = words[:-1]
    if not words:
        return []
    entity = " ".join(words)
    if len(entity) < 2 or entity.isdigit():
        return []
    return [entity]


def normalize_tag(value: str) -> str:
    value = " ".join(value.replace("#", " ").split()).strip(" .,:;-")
    if value.islower():
        value = value[:1].upper() + value[1:]
    return value


def is_valid_tag(
    name: str, excluded_slugs: set[str] | frozenset[str] = frozenset()
) -> bool:
    slug = tag_slug(name)
    return (
        bool(slug)
        and len(name) <= 40
        and name.lower() not in GENERIC_KEYWORDS
        and slug not in excluded_slugs
    )


def extract_tags(
    title: str,
    description: str = "",
    text: str = "",
    publisher_keywords: Iterable[str] = (),
    flair: str = "",
    limit: int = 5,
    excluded: Iterable[str] = (),
) -> list[str]:
    """Rank candidate tags by where and how often they appear.

    `excluded` names (e.g. the publisher's own name) are never returned.
    """
    excluded_slugs = {tag_slug(name) for name in excluded}
    scores: Counter[str] = Counter()
    names: dict[str, str] = {}
    # Words also written in lowercase are common nouns ("Union", "Centre"),
    # not proper nouns, when they appear alone.
    common_words = {
        token
        for token in TOKEN_RE.findall(f"{title} {description} {text}")
        if token.islower()
    }

    def add(name: str, weight: float) -> None:
        name = normalize_tag(name)
        slug = tag_slug(name)
        if not is_valid_tag(name, excluded_slugs):
            return
        if (
            " " not in name
            and not ACRONYM_RE.match(name)
            and name.lower() in common_words
        ):
            return
        names.setdefault(slug, name)
        scores[slug] += weight

    for entity in candidate_entities(title):
        add(entity, 4)
    for entity in candidate_entities(description):
        add(entity, 2)
    for entity in candidate_entities(text[:5000]):
        add(entity, 0.5)
    # Publisher keywords are a strong signal when the entity also shows up
    # in the article, and a decent one on their own.
    for keyword in list(publisher_keywords)[:15]:
        add(keyword, 2.5 if tag_slug(keyword) in scores else 1.5)

    # Single mentions in the body only are noise.
    ranked = [slug for slug, score in scores.most_common() if score >= 1.5]
    tags = [names[slug] for slug in ranked[: max(limit - 1, 1)]]

    if flair and flair.lower() not in GENERIC_FLAIRS:
        flair_tag = normalize_tag(flair)
        if tag_slug(flair_tag) not in {tag_slug(t) for t in tags}:
            tags.append(flair_tag)
    if len(tags) < limit:
        extra = [names[s] for s in ranked if names[s] not in tags]
        tags.extend(extra[: limit - len(tags)])
    return tags[:limit]


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
