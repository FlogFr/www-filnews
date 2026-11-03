"""Controlled tag vocabulary: political figures and major political and
societal themes. Tags are only ever picked from this list (edited by hand).

Each entry maps a tag name to the patterns that reveal it:
- `PERSONALITIES`: case-sensitive regular expressions (names are proper
  nouns: "Poutine" the man, not "poutine" the dish).
- `THEMES`: regular expressions matched case-insensitively, unless they
  contain an upper-case letter (acronyms: "IA", "CRS").

Patterns only match whole words. Keep surnames alone out when they are
common words or ambiguous ("Hollande", "Philippe", "Borne").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Literal

from .models import tag_slug

Kind = Literal["personnalite", "theme"]

KIND_LABELS: dict[str, str] = {"personnalite": "Personnalité", "theme": "Thème"}

PERSONALITIES: dict[str, tuple[str, ...]] = {
    # Presidents and prime ministers.
    "Emmanuel Macron": ("Emmanuel Macron", "Macron"),
    "François Hollande": ("Fran[çc]ois Hollande", "président Hollande"),
    "Nicolas Sarkozy": ("Nicolas Sarkozy", "Sarkozy"),
    "Jacques Chirac": ("Jacques Chirac", "Chirac"),
    "Édouard Philippe": ("[ÉE]douard Philippe",),
    "Jean Castex": ("Jean Castex", "Castex"),
    "Élisabeth Borne": ("[ÉE]lisabeth Borne",),
    "Gabriel Attal": ("Gabriel Attal", "Attal"),
    "Michel Barnier": ("Michel Barnier", "Barnier"),
    "François Bayrou": ("Fran[çc]ois Bayrou", "Bayrou"),
    "Sébastien Lecornu": ("S[ée]bastien Lecornu", "Lecornu"),
    "Manuel Valls": ("Manuel Valls", "Valls"),
    "Bernard Cazeneuve": ("Bernard Cazeneuve", "Cazeneuve"),
    "François Fillon": ("Fran[çc]ois Fillon", "Fillon"),
    "Dominique de Villepin": ("Dominique de Villepin", "Villepin"),
    # Ministers and government figures.
    "Gérald Darmanin": ("G[ée]rald Darmanin", "Darmanin"),
    "Bruno Retailleau": ("Bruno Retailleau", "Retailleau"),
    "Laurent Nuñez": ("Laurent Nu[ñn]ez",),
    "Christophe Castaner": ("Christophe Castaner", "Castaner"),
    "Gérard Collomb": ("G[ée]rard Collomb",),
    "Bruno Le Maire": ("Bruno Le Maire",),
    "Rachida Dati": ("Rachida Dati", "Dati"),
    "Éric Dupond-Moretti": ("[ÉE]ric Dupond-Moretti", "Dupond-Moretti"),
    "Olivier Véran": ("Olivier V[ée]ran", "V[ée]ran"),
    "Marlène Schiappa": ("Marl[èe]ne Schiappa", "Schiappa"),
    "Jean-Michel Blanquer": ("Jean-Michel Blanquer", "Blanquer"),
    "Aurore Bergé": ("Aurore Berg[ée]",),
    "Amélie Oudéa-Castéra": ("Am[ée]lie Oud[ée]a-Cast[ée]ra", "Oud[ée]a-Cast[ée]ra"),
    "Catherine Vautrin": ("Catherine Vautrin",),
    "Nicolas Hulot": ("Nicolas Hulot",),
    "François de Rugy": ("Fran[çc]ois de Rugy",),
    "Agnès Pannier-Runacher": ("Agn[èe]s Pannier-Runacher", "Pannier-Runacher"),
    "Yaël Braun-Pivet": ("Ya[ëe]l Braun-Pivet", "Braun-Pivet"),
    "Gérard Larcher": ("G[ée]rard Larcher",),
    "Jérôme Cahuzac": ("J[ée]r[ôo]me Cahuzac", "Cahuzac"),
    "Alexandre Benalla": ("Alexandre Benalla", "Benalla"),
    # Left.
    "Jean-Luc Mélenchon": ("Jean-Luc M[ée]lenchon", "M[ée]lenchon"),
    "François Ruffin": ("Fran[çc]ois Ruffin", "Ruffin"),
    "Raphaël Glucksmann": ("Rapha[ëe]l Glucksmann", "Glucksmann"),
    "Olivier Faure": ("Olivier Faure",),
    "Fabien Roussel": ("Fabien Roussel",),
    "Marine Tondelier": ("Marine Tondelier", "Tondelier"),
    "Yannick Jadot": ("Yannick Jadot", "Jadot"),
    "Sandrine Rousseau": ("Sandrine Rousseau",),
    "Mathilde Panot": ("Mathilde Panot", "Panot"),
    "Manuel Bompard": ("Manuel Bompard", "Bompard"),
    "Clémentine Autain": ("Cl[ée]mentine Autain", "Autain"),
    "Adrien Quatennens": ("Adrien Quatennens", "Quatennens"),
    "Louis Boyard": ("Louis Boyard",),
    "Éric Coquerel": ("[ÉE]ric Coquerel", "Coquerel"),
    "Rima Hassan": ("Rima Hassan",),
    "Sébastien Delogu": ("S[ée]bastien Delogu", "Delogu"),
    "Lucie Castets": ("Lucie Castets",),
    "Anne Hidalgo": ("Anne Hidalgo", "Hidalgo"),
    "Ségolène Royal": ("S[ée]gol[èe]ne Royal",),
    "Benoît Hamon": ("Beno[îi]t Hamon",),
    "Arnaud Montebourg": ("Arnaud Montebourg", "Montebourg"),
    "Christiane Taubira": ("Christiane Taubira", "Taubira"),
    "Nathalie Arthaud": ("Nathalie Arthaud",),
    "Philippe Poutou": ("Philippe Poutou", "Poutou"),
    # Right and far right.
    "Marine Le Pen": (
        "Marine Le Pen",
        "(?<!Jean-Marie )(?<!Mar[ée]chal-)(?<!Marion )Le Pen",
    ),
    "Jean-Marie Le Pen": ("Jean-Marie Le Pen",),
    "Marion Maréchal": ("Marion Mar[ée]chal(?:-Le Pen)?",),
    "Jordan Bardella": ("Jordan Bardella", "Bardella"),
    "Sébastien Chenu": ("S[ée]bastien Chenu",),
    "Éric Zemmour": ("[ÉE]ric Zemmour", "Zemmour"),
    "Sarah Knafo": ("Sarah Knafo", "Knafo"),
    "Éric Ciotti": ("[ÉE]ric Ciotti", "Ciotti"),
    "Laurent Wauquiez": ("Laurent Wauquiez", "Wauquiez"),
    "Valérie Pécresse": ("Val[ée]rie P[ée]cresse", "P[ée]cresse"),
    "Xavier Bertrand": ("Xavier Bertrand",),
    "David Lisnard": ("David Lisnard", "Lisnard"),
    "Nicolas Dupont-Aignan": ("Nicolas Dupont-Aignan", "Dupont-Aignan"),
    "Jean Lassalle": ("Jean Lassalle",),
    "Patrick Balkany": ("Patrick Balkany", "Balkany"),
    # International.
    "Donald Trump": ("Donald Trump", "Trump"),
    "Joe Biden": ("Joe Biden", "Biden"),
    "Kamala Harris": ("Kamala Harris",),
    "Barack Obama": ("Barack Obama", "Obama"),
    "Elon Musk": ("Elon Musk", "Musk"),
    "Vladimir Poutine": ("Vladimir Poutine", "Poutine"),
    "Volodymyr Zelensky": ("Volodymyr Zelensky", "Zelensky", "Zelenski"),
    "Benyamin Netanyahou": ("Benyamin Netanyahou", "Netanyahou", "Netanyahu"),
    "Xi Jinping": ("Xi Jinping",),
    "Recep Tayyip Erdoğan": ("Recep Tayyip Erdo[ğg]an", "Erdo[ğg]an"),
    "Angela Merkel": ("Angela Merkel", "Merkel"),
    "Olaf Scholz": ("Olaf Scholz", "Scholz"),
    "Friedrich Merz": ("Friedrich Merz",),
    "Giorgia Meloni": ("Giorgia Meloni", "Meloni"),
    "Viktor Orbán": ("Viktor Orb[áa]n", "Orb[áa]n"),
    "Ursula von der Leyen": ("Ursula von der Leyen", "von der Leyen"),
    "Boris Johnson": ("Boris Johnson",),
    "Keir Starmer": ("Keir Starmer", "Starmer"),
    "Javier Milei": ("Javier Milei", "Milei"),
    "Jair Bolsonaro": ("Jair Bolsonaro",),
}

# Plural and feminine endings: "policier", "policiers", "policière(s)".
THEMES: dict[str, tuple[str, ...]] = {
    "Environnement": (
        r"environnement(?:al|ale|aux|ales)?",
        r"[ée]cologi(?:e|que|ques|ste|stes)",
        r"climat(?:ique|iques)?",
        r"r[ée]chauffement climatique",
        r"biodiversit[ée]",
        r"pollution",
        r"pesticides?",
        r"glyphosate",
        r"m[ée]ga-?bassines?",
        r"GIEC",
        r"COP ?\d{2}",
    ),
    "Énergie": (
        r"[ée]nergie",
        r"[ée]nerg[ée]tique",
        r"nucl[ée]aire civil",
        r"centrales? nucl[ée]aires?",
        r"EDF",
        r"prix de l'[ée]lectricit[ée]",
        r"carburants?",
    ),
    "Agriculture": (
        r"agricult(?:ure|eurs?|rices?)",
        r"agricoles?",
        r"FNSEA",
        r"[ée]leveurs?",
    ),
    "Police": (
        r"polic(?:e|es|ier|iers|i[èe]re|i[èe]res)",
        r"gendarm(?:e|es|erie)",
        r"forces de l'ordre",
        r"IGPN",
        r"CRS",
        r"violences polici[èe]res",
        r"maintien de l'ordre",
    ),
    "Justice": (
        r"justice",
        r"tribunal",
        r"tribunaux",
        r"proc[èe]s",
        r"magistrats?",
        r"cour d'appel",
        r"cour de cassation",
        r"mise? en examen",
        r"condamn[ée]e?s?",
    ),
    "Prisons": (
        r"prisons",
        r"maisons? d'arr[êe]t",
        r"surpopulation carc[ée]rale",
        r"d[ée]tenus?",
        r"p[ée]nitentiaires?",
        r"(?:milieu|univers) carc[ée]ral",
    ),
    "Corruption": (
        r"corruption",
        r"emplois fictifs",
        r"d[ée]tournement de fonds",
        r"prise ill[ée]gale d'int[ée]r[êe]ts",
        r"conflits? d'int[ée]r[êe]ts",
        r"trafic d'influence",
        r"favoritisme",
        r"financement libyen",
    ),
    "Immigration": (
        r"immigr(?:ation|[ée]s?|[ée]es?)",
        r"migr(?:ants?|antes?|atoire|atoires)",
        r"r[ée]fugi[ée]s?",
        r"demandeurs? d'asile",
        r"droit d'asile",
        r"sans-papiers",
        r"OQTF",
    ),
    "Racisme": (
        r"racis(?:me|tes?)",
        r"discriminations? raciales?",
        r"islamophob(?:e|es|ie)",
    ),
    "Antisémitisme": (r"antis[ée]mit(?:isme|es?)",),
    "Laïcité": (
        r"la[ïi]cit[ée]",
        r"voile islamique",
        r"port du voile",
        r"abayas?",
        r"burkinis?",
        r"islamisme",
        r"s[ée]paratisme",
    ),
    "Terrorisme": (
        r"terroris(?:me|tes?)",
        r"attentats?",
        r"djihadist(?:e|es)",
        r"jihadist(?:e|es)",
    ),
    "Narcotrafic": (
        r"narcotrafi(?:c|cs|quants?)",
        r"trafic de drogues?",
        r"trafiquants? de drogue",
        r"points? de deal",
        r"stup[ée]fiants",
    ),
    "Extrême droite": (
        r"extr[êe]me[- ]droite",
        r"ultra-?droite",
        r"n[ée]o-?nazis?",
        r"identitaires",
    ),
    "Extrême gauche": (r"extr[êe]me[- ]gauche", r"ultra-?gauche"),
    "Droits des femmes": (
        r"f[ée]minis(?:me|tes?)",
        r"f[ée]minicides?",
        r"droits des femmes",
        r"[ée]galit[ée] (?:femmes-hommes|hommes-femmes|salariale)",
        r"IVG",
        r"avortement",
    ),
    "Violences sexuelles": (
        r"violences sexuelles",
        r"agressions? sexuelles?",
        r"harc[èe]lement sexuel",
        r"viols?",
        r"MeToo",
        r"p[ée]docriminalit[ée]",
        r"inceste",
    ),
    "LGBT+": (
        r"LGBT\w*",
        r"homophob(?:e|es|ie)",
        r"transphob(?:e|es|ie)",
        r"mariage pour tous",
        r"homosexuel(?:le|s|les)?",
    ),
    "Santé": (
        r"sant[ée] publique",
        r"h[ôo]pita(?:l|ux)",
        r"m[ée]decins?",
        r"urgences",
        r"soignants?",
        r"d[ée]serts? m[ée]dicaux",
        r"m[ée]dicaments?",
    ),
    "Covid-19": (
        r"covid(?:-19)?",
        r"coronavirus",
        r"confinement",
        r"pass sanitaire",
        r"pass vaccinal",
    ),
    "Fin de vie": (
        r"fin de vie",
        r"euthanasie",
        r"suicide assist[ée]",
        r"aide (?:active )?[àa] mourir",
    ),
    "Handicap": (r"handicap(?:s|[ée]s?|[ée]es?)?", r"AAH"),
    "Éducation": (
        r"[ée]ducation nationale",
        r"[ée]coles?",
        r"enseignants?",
        r"professeurs?",
        r"lyc[ée]es?",
        r"coll[èe]ges?",
        r"[ée]l[èe]ves",
        r"baccalaur[ée]at",
        r"Parcoursup",
        r"universit[ée]s?",
        r"[ée]tudiants?",
    ),
    "Logement": (
        r"logements?",
        r"loyers?",
        r"locataires?",
        r"HLM",
        r"expulsions? locatives?",
        r"mal-logement",
        r"sans-abri",
        r"SDF",
        r"immobilier",
    ),
    "Pauvreté": (
        r"pauvret[ée]",
        r"pr[ée]carit[ée]",
        r"in[ée]galit[ée]s",
        r"RSA",
        r"minima sociaux",
        r"Restos du c(?:œ|oe)ur",
        r"aide alimentaire",
    ),
    "Protection sociale": (
        r"s[ée]curit[ée] sociale",
        r"assurance[- ]ch[ôo]mage",
        r"allocations?",
        r"APL",
        r"CAF",
        r"mutuelles?",
    ),
    "Retraites": (r"retraites?", r"retrait[ée]s", r"pensions? de retraite"),
    "Travail": (
        r"ch[ôo]mage",
        r"ch[ôo]meurs?",
        r"emploi",
        r"salari[ée]s",
        r"licenciements?",
        r"SMIC",
        r"Smic",
        r"salaires?",
        r"France Travail",
        r"P[ôo]le emploi",
    ),
    "Grèves et syndicats": (
        r"gr[èe]ves?",
        r"gr[ée]vistes?",
        r"syndica(?:ts?|les?|listes?)",
        r"intersyndicale",
        r"CGT",
        r"CFDT",
    ),
    "Manifestations": (
        r"manifestations?",
        r"manifestants?",
        r"gilets jaunes",
        r"mobilisations?",
    ),
    "Économie": (
        r"[ée]conomi(?:e|que|ques)",
        r"inflation",
        r"croissance",
        r"r[ée]cession",
        r"PIB",
        r"pouvoir d'achat",
    ),
    "Budget et fiscalité": (
        r"budg[ée]t(?:s|aire|aires)?",
        r"dette publique",
        r"d[ée]ficits?",
        r"imp[ôo]ts?",
        r"fiscal(?:e|es|it[ée])",
        r"taxes?",
        r"[ée]vasion fiscale",
        r"fraude fiscale",
        r"ISF",
    ),
    "Transports": (
        r"SNCF",
        r"RATP",
        r"transports? en commun",
        r"TGV",
        r"TER",
        r"ferroviaires?",
    ),
    "Médias": (
        r"m[ée]dias",
        r"journalistes?",
        r"libert[ée] de la presse",
        r"audiovisuel public",
        r"Arcom",
        r"CNews",
    ),
    "Numérique": (
        r"num[ée]rique",
        r"r[ée]seaux sociaux",
        r"donn[ée]es personnelles",
        r"CNIL",
        r"cyberattaques?",
        r"cybers[ée]curit[ée]",
        r"GAFAM",
    ),
    "Intelligence artificielle": (
        r"intelligence artificielle",
        r"IA",
        r"ChatGPT",
        r"OpenAI",
    ),
    "Libertés publiques": (
        r"libert[ée]s? publiques?",
        r"libert[ée] d'expression",
        r"libert[ée] de manifester",
        r"reconnaissance faciale",
        r"vid[ée]osurveillance",
        r"[ée]tat d'urgence",
        r"surveillance de masse",
    ),
    "Institutions": (
        r"Assembl[ée]e nationale",
        r"S[ée]nat",
        r"d[ée]put[ée]e?s?",
        r"s[ée]nat(?:eur|eurs|rice|rices)",
        r"49\.3",
        r"motion de censure",
        r"dissolution",
        r"Constitution",
        r"Conseil constitutionnel",
        r"r[ée]f[ée]rendum",
    ),
    "Élections": (
        r"[ée]lections?(?! pr[ée]sidentielle)",
        r"[ée]lectora(?:l|le|ux|les)",
        r"scrutins?",
        r"l[ée]gislatives",
        r"municipales",
        r"europ[ée]ennes",
        r"sondages?",
    ),
    "Élection présidentielle": (
        r"pr[ée]sidentielles?",
        r"[ée]lection pr[ée]sidentielle",
        r"candidat(?:e|s|es)? [àa] l'[ÉE]lys[ée]e",
    ),
    "Défense": (
        r"arm[ée]e fran[çc]aise",
        r"militaires?",
        r"d[ée]fense nationale",
        r"OTAN",
        r"Rafale",
        r"dissuasion nucl[ée]aire",
    ),
    "Union européenne": (
        r"Union europ[ée]enne",
        r"UE",
        r"Commission europ[ée]enne",
        r"Parlement europ[ée]en",
        r"Bruxelles",
    ),
    "Guerre en Ukraine": (
        r"Ukraine",
        r"ukrainien(?:ne|s|nes)?",
        r"Kiev",
        r"Kyiv",
    ),
    "Conflit israélo-palestinien": (
        r"Gaza",
        r"Isra[ëe]l",
        r"isra[ée]lien(?:ne|s|nes)?",
        r"Palestine",
        r"palestinien(?:ne|s|nes)?",
        r"Hamas",
        r"Cisjordanie",
    ),
    "Outre-mer": (
        r"outre-mer",
        r"ultramarins?",
        r"Nouvelle-Cal[ée]donie",
        r"Mayotte",
        r"Guadeloupe",
        r"Martinique",
        r"Guyane",
        r"La R[ée]union",
    ),
    "Cause animale": (
        r"bien-[êe]tre animal",
        r"maltraitance animale",
        r"cause animale",
        r"corridas?",
        r"chasse",
        r"chasseurs?",
    ),
}

# Reddit flairs that are themes ("Politique", "Société"… are too broad).
FLAIR_THEMES: dict[str, str] = {
    "écologie": "Environnement",
    "covid-19": "Covid-19",
    "santé": "Santé",
    "elections": "Élections",
    "élections": "Élections",
}


@dataclass(frozen=True, slots=True)
class Entry:
    name: str
    kind: Kind
    pattern: re.Pattern[str]

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind]

    def count(self, text: str) -> int:
        return sum(1 for _ in self.pattern.finditer(text))


def _compile(patterns: tuple[str, ...], case_sensitive: bool) -> re.Pattern[str]:
    def one(pattern: str) -> str:
        if case_sensitive or re.search(r"[A-ZÀ-Ý]", pattern):
            return f"(?:{pattern})"
        return f"(?i:{pattern})"

    alternatives = "|".join(one(p) for p in patterns)
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])")


@cache
def entries() -> tuple[Entry, ...]:
    personalities = (
        Entry(name, "personnalite", _compile(patterns, case_sensitive=True))
        for name, patterns in PERSONALITIES.items()
    )
    themes = (
        Entry(name, "theme", _compile(patterns, case_sensitive=False))
        for name, patterns in THEMES.items()
    )
    return (*personalities, *themes)


@cache
def by_slug() -> dict[str, Entry]:
    return {tag_slug(entry.name): entry for entry in entries()}


def lookup(name: str) -> Entry | None:
    """The vocabulary entry of a tag name, if any."""
    return by_slug().get(tag_slug(name))


def flair_theme(flair: str) -> str | None:
    return FLAIR_THEMES.get(flair.strip().lower())
