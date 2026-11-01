# Architecture

## Vue d'ensemble

```
            (local, machine du propriétaire)                         (production)
┌──────────────────────────────────────────────────────┐     ┌────────────────────────┐
│ ingest_news ──► Reddit API (OAuth)                    │     │  Docker (nginx, :8000) │
│      │                                                │     │                        │
│      ▼                                                │     │  dist/ statique :      │
│ data/news/AAAA-MM.json ◄── analyze_news ──► articles  │     │  HTML, RSS, sitemap,   │
│      │                         │  (og:*, texte, image)│     │  CSS/JS hashés, media  │
│      │                         ▼                      │     │                        │
│      │               data/media/thumbnails/*.webp     │     └───────────▲────────────┘
│      ▼                                                │                 │
│ build_site (Django rend chaque URL) ──► dist/ ────────┼── docker build ─┘
└──────────────────────────────────────────────────────┘
```

Django sert uniquement à **produire** le site (et au serveur de dev local). En
production, nginx sert des fichiers statiques : pas de Python, pas de base de
données, coût et surface d'attaque minimaux.

## Modules (`filnews/`)

| Module | Rôle |
|---|---|
| `settings.py` | Configuration unique, alimentée par variables d'env (`.env` chargé via python-dotenv) |
| `models.py` | Dataclasses `News`, `Tag`, `TagSummary` (+ sérialisation JSON) |
| `store.py` | `NewsStore` : base fichiers JSON (1 fichier/mois), chargée au démarrage, rechargée si les fichiers (ou les alias) changent, écritures atomiques + `flock` ; doublons par URL canonique (`canonical_url`, `UpsertResult`), alias de tags (`apply_aliases`), index par mois, pages de tag, `related` borné |
| `reddit.py` | Client OAuth2 Reddit minimal (`requests`) : refresh token si présent, sinon `client_credentials` ; `posts_by_id` (`/api/info`) |
| `archive.py` | Client Arctic Shift : découverte des ids de posts historiques par plage de dates (`backfill_news`) |
| `ingestion.py` | Filtrage des posts (seuil, liens d'articles uniquement, ni Twitter/X ni YouTube) et conversion en `News` ; `select_backfill` (≥ seuil, top N du mois ou top N du jour) |
| `analysis/` | `fetch` (HTTP borné, Wayback Machine), `extract` (métadonnées HTML), `text` (tags/résumé heuristiques), `thumbnails` (WebP 640×360), `analyzers` (heuristique / modèle local) |
| `timeline.py` | Historique d'un tag : frise horizontale ajustée à l'historique (`build_timeline`, points ou barres, carte au survol) et Fil vertical (`build_thread`, découpé par année via `thread_years`, page du tag) |
| `views.py`, `urls.py` | Pages, fragment de frise, OAuth Reddit (local uniquement) |
| `feeds.py`, `sitemaps.py` | RSS et sitemaps (index + une section par fichier) |
| `templatetags/filnews_tags.py` | URLs absolues, médias, JSON-LD, `has_tag_page` |
| `assets.py` | Compilation SCSS → CSS (libsass) |
| `management/commands/` | `ingest_news`, `backfill_news`, `analyze_news`, `build_site`, `publish_pages`, `runserver` (surcharge) |

## Données

- `data/news/AAAA-MM.json` : liste de news du mois (plus récentes d'abord),
  JSON indenté pour des diffs git lisibles.
- `data/media/thumbnails/<id>.webp` : vignettes générées (ignorées par git,
  copiées dans l'image Docker).
- `data/tag_aliases.json` : alias de tags édités à la main (`{"alias": "nom"}`).
- `data/.secrets/` : refresh token Reddit (jamais versionné ni copié dans Docker).
- `data/.lock` : verrou inter-processus.

Les index dérivés (par date, slug, URL, mois, tags, position dans chaque tag)
sont recalculés paresseusement en mémoire après chaque mutation.

## URLs publiques

| URL | Contenu |
|---|---|
| `/` | Accueil : news la plus populaire des 24 h, 5 dernières news, 10 tags récents, lien RSS |
| `/news/<slug>-<id>/` | Fiche news (résumé, liens source/Reddit, tags, news liées) |
| `/archives/` | Mois par année (nombre de news) |
| `/archives/<AAAA>/<MM>/` | News du mois, jour par jour (`/archives/page/<n>/` → 301 vers `/archives/`, nginx) |
| `/tags/`, `/tags/<slug>/` | Index des tags (par lettre, tags d'au moins 2 news), page tag avec le Fil (année la plus récente si > 60 news) |
| `/tags/<slug>/<AAAA>/` | Fil d'une année précédente d'un gros tag (l'année courante redirige vers `/tags/<slug>/`) |
| `/tags/<slug>/timeline/` | Fragment HTML de la carte au survol (dernières news + frise) |
| `/sitemap.xml`, `/sitemap-<section>.xml` | Index de sitemaps, sections `pages`, `news`, `tags` |
| `/rss.xml`, `/robots.txt`, `/a-propos/`, `/404.html` | — |
| `/auth/reddit/login`, `/auth/reddit/callback` | OAuth Reddit, **dev local uniquement** (404 en prod) |

## Build statique

`build_site` : compile le SCSS (compressé) → `collectstatic` avec
`ManifestStaticFilesStorage` (noms hashés, cache 1 an) → rend chaque URL avec le
client de test Django en se faisant passer pour `SITE_URL` (URLs absolues
correctes) → copie `data/media`. Le rendu est réparti entre des processus
forkés (`--workers`, un par CPU par défaut) qui héritent du store déjà chargé.
Le Dockerfile pré-compresse ensuite en gzip (`gzip_static`, `xargs -P`).

`publish_pages` (alternative à Docker) : `build_site`, ajoute `CNAME` et
`.nojekyll`, puis commite `dist/` sur la branche orpheline `pages` via la
plomberie git (`GIT_INDEX_FILE` temporaire, `write-tree`, `commit-tree`,
`update-ref`) sans toucher la copie de travail ; `--push` pousse la branche.
Sur un hébergeur statique, la CSP et les en-têtes de `docker/` ne s'appliquent
pas.

`.github/workflows/nightly.yml` enchaîne chaque nuit, sur un runner GitHub :
restauration de `data/media` depuis `pages` (vignettes hors git), `ingest_news
--period day`, `analyze_news`, commit de `data/news` sur `main`, puis
`publish_pages --push`. Secrets : `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`.

## Décisions

- **Pas de base relationnelle** (exigence) : JSON par mois, tout en mémoire.
  Suffisant pour des dizaines de milliers de news.
- **Site 100 % statique** : performance et coût ; la callback OAuth n'existe que
  sur le serveur de dev local, où tournent les commandes.
- **libsass** plutôt que Dart Sass : pas de Node.js dans la chaîne ; contrepartie,
  certaines fonctions CSS modernes doivent être protégées par `unquote()`.
- **Polices auto-hébergées** (Oswald, Lora, OFL) : CSP stricte et RGPD.
- **Analyse** : heuristique par défaut (gratuite, rapide) ; modèles Hugging Face
  locaux en option (`[ml]`), jamais dans l'image Docker. Parallèle par threads
  (un analyseur, donc une session HTTP, par thread) ; le modèle local reste en
  série.
- **Historique** (octobre 2026) : Arctic Shift pour découvrir les ids, API
  Reddit pour les données ; en plus du seuil, top 60 du mois et top 2 du jour (≥ 20 votes). Wayback Machine
  pour les articles morts (seul envoi à un tiers : l'URL de l'article).
- **Pas de build incrémental** : avec ~10 000 pages, rendre tout en parallèle
  prend environ une minute, et l'image Docker est reconstruite de zéro de
  toute façon ; le suivi des dépendances entre pages ne vaut pas sa complexité.
- **Vignettes hors git** : ~200 Mo ; copiées dans l'image, régénérables.
