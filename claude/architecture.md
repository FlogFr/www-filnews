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
| `models.py` | Dataclasses `News`, `Tag`, `TagSummary`, `TagGroup` (un `TagSummary` nommé « A + B », avec ses `tags`) (+ sérialisation JSON) |
| `store.py` | `NewsStore` : base fichiers JSON (1 fichier/mois), chargée au démarrage, rechargée si les fichiers (ou les alias) changent, écritures atomiques + `flock` ; doublons par URL canonique (`canonical_url`, `UpsertResult`), alias de tags (`apply_aliases`), index par mois, pages de tag, index des groupes de tags (`group` : news portant tous les tags d'un groupe, pour chaque combinaison d'au moins 2 tags d'une news), `related` borné (avec `exclude`) |
| `reddit.py` | Client OAuth2 Reddit minimal (`requests`) : refresh token si présent, sinon `client_credentials` ; `posts_by_id` (`/api/info`) |
| `archive.py` | Client Arctic Shift : découverte des ids de posts historiques par plage de dates (`backfill_news`) |
| `media.py` | Politique des médias : `ALLOWED_DOMAINS` (liste blanche, active par défaut via `FILNEWS_MEDIA_WHITELIST`) et `BLOCKED_DOMAINS` (toujours refusés : YouTube, réseaux sociaux, satire…), comparaison domaine + sous-domaines |
| `ingestion.py` | Filtrage des posts (seuil, politique des médias) et conversion en `News` ; `select_backfill` (≥ seuil, top N du mois ou top N du jour) |
| `vocabulary.py` | Vocabulaire contrôlé des tags : `PERSONALITIES` (regex sensibles à la casse) et `THEMES` (insensibles sauf sigles), `lookup()` donne la sorte d'un tag |
| `elections.py` | Présidentielle 2027 : `CANDIDATES` (édité à la main), fil d'un candidat (`candidate_news`), fil de la campagne (`election_news`) |
| `analysis/` | `fetch` (HTTP borné, Wayback Machine), `extract` (métadonnées HTML), `text` (tags par score sur le vocabulaire, résumé), `thumbnails` (WebP 640×360), `analyzers` (heuristique / modèle local) |
| `groups.py` | Groupe de fils d'une news (`news_groups`) : groupe le plus spécifique qui a un historique (tous ses tags, sinon le plus grand sous-ensemble partagé), rang, fil de 5 news autour d'elle, frise (`build_timeline(current=…)`), autres groupes non redondants |
| `insights.py` | Contenu original calculé : contexte d'une news (`news_context` : rang du jour, place dans ses fils) et portrait d'un fil (`tag_profile` : pic, médias, news la plus votée, fils voisins) |
| `dates.py` | `format_date` : format de date Django en heure locale, avec « 1er » pour le premier du mois (filtre de template `date_fr`) |
| `timeline.py` | Historique d'un tag (ou d'un groupe de fils) : frise horizontale ajustée à l'historique (`build_timeline`, points ou barres, news courante marquée, carte au survol et encart de groupe) et Fil vertical (`build_thread`, découpé par année via `thread_years`, page du tag) |
| `views.py`, `urls.py` | Pages, fragment de frise, pages newsletter et contact (identifiants `SENDER_*` des réglages), OAuth Reddit (local uniquement) |
| `feeds.py`, `sitemaps.py` | RSS et sitemaps (index + une section par fichier) |
| `templatetags/filnews_tags.py` | URLs absolues, médias, JSON-LD, `has_tag_page` |
| `assets.py` | Compilation SCSS → CSS (libsass) : `main.css` et `sender-frame.css` (habillage des iframes Sender) |
| `management/commands/` | `ingest_news`, `backfill_news`, `analyze_news` (`--retag` : tags seuls, hors ligne), `prune_news`, `build_site`, `publish_pages`, `runserver` (surcharge) |

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
| `/` | Accueil : bandeau, news la plus populaire des 24 h, fil du tag le plus actif sur 48 h, 5 dernières news, 7 fils du moment (7 jours), encart présidentielle, lien RSS. Ordre du HTML = ordre mobile (une, dernières news, fil du moment, compléments) ; la grille `.home-layout--front` replace le fil à côté de la une sur grand écran |
| `/presidentielle-2027/`, `/presidentielle-2027/<candidat>/` | Candidats et fil de la campagne ; fil d'un candidat depuis 2025 |
| `/mentions-legales/` | Mentions légales, lien vers le code source |
| `/newsletter/`, `/contact/` | Formulaires Sender.net (inscription à la newsletter, contact), chargés par `static/js/sender.js` ; seules pages avec une CSP ouverte à `*.sender.net` |
| `/news/<slug>-<id>/` | Fiche news (résumé, liens source/Reddit, encart du groupe de fils, contexte par tag, tags, news liées) |
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
correctes) → copie `data/media` → copie tel quel le contenu de
`filnews/root/` (`ROOT_FILES_DIR`) à la racine de `dist/` (fichiers de
vérification des moteurs de recherche, ex. `BingSiteAuth.xml`). Le rendu est réparti entre des processus
forkés (`--workers`, un par CPU par défaut) qui héritent du store déjà chargé.
Le Dockerfile pré-compresse ensuite en gzip (`gzip_static`, `xargs -P`).

`publish_pages` (alternative à Docker) : `build_site`, ajoute `CNAME` et
`.nojekyll`, puis commite `dist/` sur la branche orpheline `pages` via la
plomberie git (`GIT_INDEX_FILE` temporaire, `write-tree`, `commit-tree`,
`update-ref`) sans toucher la copie de travail ; `--push` pousse la branche.
Sur un hébergeur statique, la CSP et les en-têtes de `docker/` ne s'appliquent
pas.

`.github/workflows/nightly.yml` enchaîne toutes les 6 heures (cron
`17 */6 * * *`), sur un runner GitHub :
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
- **Tags en vocabulaire contrôlé** (novembre 2026) : l'extraction d'entités
  à majuscule produisait des erreurs visibles (« Heures », « Rassemblement »,
  « Payant »). Les tags sont désormais limités aux personnalités politiques et
  aux grands thèmes listés à la main ; moins de tags, mais tous pertinents.
- **Politique des médias en liste blanche** : crédibilité ; `prune_news`
  supprime les news stockées hors liste (lancé en novembre 2026 : 2 186 news).
- **SEO, contenu original** (novembre 2026) : les fiches news reprennent la
  description de l'article source ; pour ne pas être jugé « contenu mince »,
  elles sont en `noindex, follow` et hors sitemap (`FILNEWS_INDEX_NEWS`), et
  les pages (fiches et fils) gagnent des blocs calculés à partir des données
  du site (`insights.py`).
- **Vignettes hors git** : ~200 Mo ; copiées dans l'image, régénérables.
- **Groupes de fils** (novembre 2026, demande du propriétaire) : le
  contexte d'une news passe d'abord par la **combinaison** de ses tags
  (« Police + Justice ») plutôt que tag par tag, les gros tags mélangeant
  des centaines d'histoires. Sémantique « contient tous les tags » (une news
  à 3 tags appartient aussi aux groupes de 2). Calculé au build depuis un
  index en mémoire (≈ 3 400 combinaisons, 2^n - n - 1 par news), donc
  appliqué d'un coup à tout l'historique, sans champ stocké ni migration du
  JSON. Pas de page de groupe (pas de nouvelles URL) : l'encart déplie la
  liste complète. L'encart reprend le style du « fil du moment » de
  l'accueil (`.tag-thread`) ; sur grand écran, il occupe une 2e colonne de
  la grille de l'article sur toutes ses lignes, la dernière en `1fr`
  absorbant sa hauteur.
- **Newsletter et contact par Sender.net** (novembre 2026, demande du
  propriétaire) : le site reste statique, Sender reçoit et stocke les
  données. Pages dédiées plutôt qu'un formulaire sur l'accueil : le script
  tiers et la CSP élargie (`docker/security-headers-sender.conf`, styles
  inline compris) restent confinés à `/newsletter/` et `/contact/`. Le
  snippet inline de Sender est déplacé dans `static/js/sender.js`. Sender
  rendant ses formulaires dans une iframe `about:blank` de même origine,
  `sender.js` y injecte `css/sender-frame.css` (polices, couleurs et thème
  du site) et cale sa hauteur sur le formulaire ; le titre, le texte du bas
  et le badge reCAPTCHA de Sender sont masqués au profit des textes de la
  page. Cette iframe héritant de la CSP de la page, la CSP des deux pages
  admet aussi les scripts inline et reCAPTCHA (Google).
