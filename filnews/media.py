"""Which sites a news may link to.

Two hand-edited lists, matched on the domain and all its subdomains
(`lemonde.fr` covers `abonnes.lemonde.fr`):

- `BLOCKED_DOMAINS`: never ingested, whatever the settings (videos, social
  networks, image hosts, Reddit itself, satire…): there is no article to
  summarize, or it is not news.
- `ALLOWED_DOMAINS`: recognised news media. With `FILNEWS_MEDIA_WHITELIST`
  (default), only these are ingested; otherwise any unblocked site is.

A blocked subdomain wins over an allowed parent (`blogs.mediapart.fr`).
"""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings

BLOCKED_DOMAINS = frozenset(
    {
        # Reddit itself.
        "reddit.com",
        "redd.it",
        "reddituploads.com",
        # Videos and streams.
        "youtube.com",
        "youtu.be",
        "dailymotion.com",
        "vimeo.com",
        "twitch.tv",
        "streamable.com",
        "gfycat.com",
        "tiktok.com",
        # Social networks and messaging.
        "twitter.com",
        "x.com",
        "twimg.com",
        "threadreaderapp.com",
        "facebook.com",
        "fbcdn.net",
        "instagram.com",
        "linkedin.com",
        "bsky.app",
        "mastodon.social",
        "framapiaf.org",
        "framasphere.org",
        "t.me",
        "discordapp.com",
        "discord.com",
        # Image hosts.
        "imgur.com",
        "staticflickr.com",
        "flickr.com",
        "pinimg.com",
        "wikimedia.org",
        # Encyclopedias, blogs and self-publishing.
        "wikipedia.org",
        "blogspot.com",
        "medium.com",
        "substack.com",
        "blogs.mediapart.fr",
        "change.org",
        # Satire: not news.
        "legorafi.fr",
        "nordpresse.be",
        "secretnews.fr",
        "complots-faciles.com",
    }
)

ALLOWED_DOMAINS = frozenset(
    {
        # National press.
        "lemonde.fr",
        "lefigaro.fr",
        "liberation.fr",
        "leparisien.fr",
        "humanite.fr",
        "la-croix.com",
        "lopinion.fr",
        "lesechos.fr",
        "latribune.fr",
        "20minutes.fr",
        "lejdd.fr",
        "mediapart.fr",
        "huffingtonpost.fr",
        "slate.fr",
        "marianne.net",
        "lepoint.fr",
        "lexpress.fr",
        "nouvelobs.com",
        "challenges.fr",
        "capital.fr",
        "courrierinternational.com",
        "telerama.fr",
        "lesinrocks.com",
        "parismatch.com",
        "politis.fr",
        "lecanardenchaine.fr",
        "charliehebdo.fr",
        "monde-diplomatique.fr",
        "alternatives-economiques.fr",
        "atlantico.fr",
        "valeursactuelles.com",
        "usinenouvelle.com",
        "businessinsider.fr",
        "legrandcontinent.eu",
        "lesjours.fr",
        # Public and private broadcasters.
        "francetvinfo.fr",
        "franceinfo.fr",
        "radiofrance.fr",
        "franceinter.fr",
        "franceculture.fr",
        "francebleu.fr",
        "ici.fr",
        "france24.com",
        "rfi.fr",
        "arte.tv",
        "tv5monde.com",
        "publicsenat.fr",
        "lcp.fr",
        "bfmtv.com",
        "rmc.fr",
        "tf1info.fr",
        "lci.fr",
        "europe1.fr",
        "rtl.fr",
        "cnews.fr",
        "lequipe.fr",
        "eurosport.fr",
        # Regional press.
        "ouest-france.fr",
        "sudouest.fr",
        "ladepeche.fr",
        "lavoixdunord.fr",
        "midilibre.fr",
        "lindependant.fr",
        "ledauphine.com",
        "laprovence.com",
        "nicematin.com",
        "varmatin.com",
        "leprogres.fr",
        "estrepublicain.fr",
        "dna.fr",
        "lalsace.fr",
        "republicain-lorrain.fr",
        "letelegramme.fr",
        "charentelibre.fr",
        "lamontagne.fr",
        "lanouvellerepublique.fr",
        "paris-normandie.fr",
        "courrier-picard.fr",
        "actu.fr",
        "lyonmag.com",
        "rue89strasbourg.com",
        "marsactu.fr",
        "mediacites.fr",
        # Independent and investigative media.
        "streetpress.com",
        "arretsurimages.net",
        "reporterre.net",
        "blast-info.fr",
        "bastamag.net",
        "basta.media",
        "lareleveetlapeste.fr",
        "disclose.ngo",
        "rapportsdeforce.fr",
        "frustrationmagazine.fr",
        "acrimed.org",
        "contre-attaque.net",
        "bonpote.com",
        "vert.eco",
        "theconversation.com",
        "usbeketrica.com",
        "mrmondialisation.org",
        # Tech and science.
        "numerama.com",
        "next.ink",
        "nextinpact.com",
        "frandroid.com",
        "lesnumeriques.com",
        "clubic.com",
        "01net.com",
        "developpez.com",
        "zdnet.fr",
        "presse-citron.net",
        "phonandroid.com",
        "korii.slate.fr",
        "futura-sciences.com",
        "sciencesetavenir.fr",
        "geo.fr",
        "quechoisir.org",
        "egora.fr",
        "opex360.com",
        "meta-defense.fr",
        "euractiv.fr",
        "euractiv.com",
        "politico.eu",
        "euronews.com",
        "afp.com",
        # French-speaking foreign media.
        "lalibre.be",
        "lesoir.be",
        "rtbf.be",
        "rtl.be",
        "7sur7.be",
        "rts.ch",
        "letemps.ch",
        "20min.ch",
        "ledevoir.com",
        "lapresse.ca",
        "radio-canada.ca",
        "lorientlejour.com",
        "jeuneafrique.com",
        # International media.
        "theguardian.com",
        "bbc.com",
        "bbc.co.uk",
        "nytimes.com",
        "washingtonpost.com",
        "reuters.com",
        "apnews.com",
        "bloomberg.com",
        "economist.com",
        "ft.com",
        "telegraph.co.uk",
        "independent.co.uk",
        "cnn.com",
        "politico.com",
        "thehill.com",
        "newsweek.com",
        "arstechnica.com",
        "spiegel.de",
        "elpais.com",
        "aljazeera.com",
        "timesofisrael.com",
        # Institutions (primary sources).
        "assemblee-nationale.fr",
        "senat.fr",
        "legifrance.gouv.fr",
        "gouvernement.fr",
        "elysee.fr",
        "conseil-constitutionnel.fr",
        "conseil-etat.fr",
        "courdecassation.fr",
        "ccomptes.fr",
        "insee.fr",
        "diplomatie.gouv.fr",
        "news.un.org",
        "amnesty.fr",
        "laquadrature.net",
    }
)


def url_domain(url: str) -> str:
    """Host of `url`, lowercased, without `www.`."""
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _matches(domain: str, domains: frozenset[str]) -> bool:
    """`domain` is one of `domains` or a subdomain of one of them."""
    parts = domain.split(".")
    return any(".".join(parts[i:]) in domains for i in range(len(parts)))


def is_blocked(domain: str) -> bool:
    return _matches(domain, BLOCKED_DOMAINS)


def is_allowed(domain: str) -> bool:
    return _matches(domain, ALLOWED_DOMAINS)


def is_accepted(domain: str, whitelist: bool | None = None) -> bool:
    """Whether a news may link to `domain` under the current media policy."""
    if whitelist is None:
        whitelist = settings.FILNEWS_MEDIA_WHITELIST
    if not domain or is_blocked(domain):
        return False
    return is_allowed(domain) or not whitelist
