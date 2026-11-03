"""2027 presidential election: candidates (edited by hand) and their Fils.

A candidate's Fil gathers the news tagged with the candidate's tags since the
start of the campaign. The election Fil gathers the news about the campaign:
"présidentielle 2027" in the title or summary, or a candidate's tag with a
campaign word ("candidat", "présidentielle", "2027"…).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property

from .models import News, tag_slug
from .store import NewsStore

ELECTION_NAME = "Présidentielle 2027"
# First round, as announced; news are gathered from CAMPAIGN_START.
FIRST_ROUND = datetime(2027, 4, 11, tzinfo=UTC)
CAMPAIGN_START = datetime(2025, 1, 1, tzinfo=UTC)

DECLARED = "déclaré"
POTENTIAL = "pressenti"


@dataclass(frozen=True)
class Candidate:
    name: str
    party: str
    status: str  # DECLARED or POTENTIAL.
    # Tags whose news make the candidate's Fil (the name first).
    tags: tuple[str, ...] = field(default=())

    @property
    def slug(self) -> str:
        return tag_slug(self.name)

    @property
    def tag_names(self) -> tuple[str, ...]:
        return self.tags or (self.name,)

    @cached_property
    def tag_slugs(self) -> frozenset[str]:
        return frozenset(tag_slug(name) for name in self.tag_names)

    @property
    def is_declared(self) -> bool:
        return self.status == DECLARED


# Keep in sync with the news: status as of November 2026.
CANDIDATES: tuple[Candidate, ...] = (
    Candidate("Marine Le Pen", "Rassemblement national", DECLARED),
    Candidate("Jean-Luc Mélenchon", "La France insoumise", DECLARED),
    Candidate("Raphaël Glucksmann", "Place publique – Parti socialiste", DECLARED),
    Candidate("Édouard Philippe", "Horizons", DECLARED),
    Candidate("Fabien Roussel", "Parti communiste français", DECLARED),
    Candidate("Marine Tondelier", "Les Écologistes", DECLARED),
    Candidate("David Lisnard", "Nouvelle Énergie", DECLARED),
    Candidate("Gabriel Attal", "Renaissance", POTENTIAL),
    Candidate("Bruno Retailleau", "Les Républicains", POTENTIAL),
    Candidate("Jordan Bardella", "Rassemblement national", POTENTIAL),
    Candidate("Éric Zemmour", "Reconquête", POTENTIAL),
    Candidate("François Hollande", "Parti socialiste", POTENTIAL),
    Candidate("Dominique de Villepin", "La France humaniste", POTENTIAL),
    Candidate("Nathalie Arthaud", "Lutte ouvrière", POTENTIAL),
)

ELECTION_RE = re.compile(r"pr[ée]sidentielle\s+(?:de\s+)?2027", re.IGNORECASE)
CAMPAIGN_RE = re.compile(
    r"pr[ée]sidentiel|candidat|campagne|primaire|2027|[ÉE]lys[ée]e", re.IGNORECASE
)


def get_candidate(slug: str) -> Candidate | None:
    return next((c for c in CANDIDATES if c.slug == slug), None)


def candidate_news(store: NewsStore, candidate: Candidate) -> list[News]:
    """News of a candidate since the start of the campaign, newest first."""
    news = {
        entry.id: entry
        for slug in candidate.tag_slugs
        if (tag := store.tag(slug))
        for entry in tag.news
        if entry.created_at >= CAMPAIGN_START
    }
    return sorted(news.values(), key=lambda n: (n.created_at, n.id), reverse=True)


def is_campaign_news(news: News, candidate_slugs: frozenset[str]) -> bool:
    text = f"{news.title} {news.summary}"
    if ELECTION_RE.search(text):
        return True
    tagged = any(tag_slug(name) in candidate_slugs for name in news.tags)
    return tagged and bool(CAMPAIGN_RE.search(text))


def election_news(store: NewsStore) -> list[News]:
    """The Fil of the election, newest first."""
    slugs = frozenset().union(*(c.tag_slugs for c in CANDIDATES))
    return [
        news
        for news in store.all()
        if news.created_at >= CAMPAIGN_START and is_campaign_news(news, slugs)
    ]
