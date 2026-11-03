# Documentation technique

## Prérequis

- Python **3.12+** (virtualenv recommandé)
- Docker (pour l'image de production)
- Un compte Reddit (pour créer une application API)

## Installation locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # dépendances + ruff
cp .env.example .env             # puis compléter .env
```

Optionnel, pour l'analyseur à base de modèles locaux (~2 Go, torch) :

```bash
pip install --index-url https://download.pytorch.org/whl/cpu torch   # version CPU, plus légère
pip install -e ".[ml]"
```

## Configuration (`.env` / variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `DJANGO_DEBUG` | `0` | `1` en local |
| `DJANGO_SECRET_KEY` | clé de dev | Signe le cookie d'état OAuth (Django ne tourne qu'en local) |
| `SITE_URL` | `https://filnews.fr` | URL publique : canonical, sitemap, RSS, Open Graph |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | — | Identifiants de l'application Reddit (**secrets**) |
| `REDDIT_REDIRECT_URI` | `http://localhost:8000/auth/reddit/callback` | Doit correspondre à l'app Reddit |
| `REDDIT_USER_AGENT` | `web:fr.filnews:v1.0 (by /u/filnews)` | Format exigé par Reddit |
| `FILNEWS_SUBREDDIT` | `france` | Subreddit source |
| `FILNEWS_MIN_SCORE` | `250` | Seuil de votes |
| `FILNEWS_BACKFILL_TOP` | `60` | `backfill_news` : garde aussi les N meilleurs articles de chaque mois (0 = désactivé) |
| `FILNEWS_BACKFILL_DAY_TOP` | `2` | `backfill_news` : garde aussi les N meilleurs articles de chaque jour (0 = désactivé) |
| `FILNEWS_BACKFILL_DAY_MIN_SCORE` | `20` | … à condition qu'ils aient au moins ce score |
| `FILNEWS_MEDIA_WHITELIST` | `1` | N'ingère que les médias autorisés de `filnews/media.py` (`0` : tout site non refusé) |
| `FILNEWS_ANALYZER` | `heuristic` | `heuristic` ou `local` |
| `FILNEWS_MAX_TAGS` | `5` | Tags par news |
| `FILNEWS_ANALYZE_WORKERS` | `8` | Téléchargements parallèles d'`analyze_news` (2 au plus par site) |
| `FILNEWS_WAYBACK` | `1` | Copie Wayback Machine des articles morts (`0` pour désactiver) |
| `FILNEWS_KEYWORD_MODEL` / `FILNEWS_SUMMARY_MODEL` | voir `analyzers.py` | Modèles Hugging Face de l'analyseur local |
| `FILNEWS_DATA_DIR` | `./data` | Dossier de la base JSON |

## Accès à l'API Reddit

1. Sur <https://www.reddit.com/prefs/apps>, créer une application de type
   **web app** avec la redirect URI `http://localhost:8000/auth/reddit/callback`.
2. Renseigner `REDDIT_CLIENT_ID` et `REDDIT_CLIENT_SECRET` dans `.env`.
3. Deux modes :
   - **sans autre étape** : l'ingestion utilise l'OAuth « application only »
     (`client_credentials`), suffisant pour lire un subreddit public ;
   - **avec un compte** : lancer `python manage.py runserver`, ouvrir
     <http://localhost:8000/auth/reddit/login>, accepter. Reddit redirige vers
     `/auth/reddit/callback`, qui enregistre un refresh token dans
     `data/.secrets/reddit_token.json` (chmod 600, ignoré par git et Docker).

## Commandes

```bash
python manage.py runserver                 # http://localhost:8000, SCSS recompilé à chaque modification
python manage.py ingest_news               # news des dernières 24 h
python manage.py ingest_news --period month    # news du mois précédent
python manage.py ingest_news --min-score 200 --subreddit france
python manage.py backfill_news --from 2019-01 --to 2019-12  # historique, mois par mois (≥ 250, top 60/mois, top 2/jour)
python manage.py backfill_news --from 2016-01 --top 80 --day-top 3  # minimums plus élevés
python manage.py backfill_news --from 2019-03 --dry-run     # stats des scores, n'écrit rien
python manage.py analyze_news              # analyse les news pas encore analysées (8 en parallèle)
python manage.py analyze_news --workers 16 # plus de téléchargements en parallèle
python manage.py analyze_news --force --days 7 # ré-analyse la dernière semaine
python manage.py analyze_news --analyzer local # modèles locaux
python manage.py analyze_news abc123 def456    # news précises (ids Reddit)
python manage.py analyze_news --retag      # recalcule les tags (vocabulaire) sans téléchargement
python manage.py prune_news                # news hors politique des médias (--apply pour supprimer)
python manage.py build_site                # génère dist/ (un processus par CPU, --workers N)
python manage.py publish_pages             # build_site + commit de dist/ sur la branche git `pages`
python manage.py publish_pages --push      # … puis git push origin pages
python manage.py test                      # tests unitaires
ruff check . && ruff format .              # lint + format
```

Le serveur de dev recharge automatiquement la base JSON si une commande
d'ingestion ou d'analyse la modifie pendant qu'il tourne.

## Import de l'historique

L'API Reddit ne remonte qu'environ 1000 posts par listing : impossible d'aller
chercher des posts vieux de plusieurs années. `backfill_news` procède en deux
temps, pour chaque mois :

1. **Découverte** des identifiants via l'archive Arctic Shift
   (`filnews/archive.py`, pagination par date, environ 60 requêtes par mois).
2. **Hydratation** via `/api/info` (100 posts par requête) : score actuel,
   statut de suppression. Les scores de l'archive, capturés juste après la
   publication, sont sous-évalués et ne sont pas utilisés.

Le réseau est fait hors verrou ; seule l'écriture du mois est transactionnelle.
Compter environ 1 min 15 par mois (essentiellement Arctic Shift).

Arctic Shift répond parfois 422 (timeout côté serveur), 429 ou 5xx : la
requête est réessayée jusqu'à 5 fois. Si un mois échoue malgré tout, il est
sauté et l'import continue ; la commande se termine en erreur en listant les
mois à relancer avec `--from`/`--to`.

Mesures (articles hors self-posts, images, supprimés) :

| Mois | Posts | Articles | ≥ 100 | ≥ 250 | ≥ 500 |
|---|---|---|---|---|---|
| 2016-03 | 2838 | 1902 | 14 | 0 | 0 |
| 2019-03 | 5677 | 2897 | 151 | 33 | 16 |
| 2022-03 | 5937 | 1338 | 230 | 60 | 21 |
| 2026-10 (ingéré) | — | — | — | 344 | 218 |

Les scores ont fortement augmenté avec la taille du subreddit : un seuil fixe
de 250 ne garde presque rien avant 2020. `backfill_news` garde donc un article
s'il remplit **au moins une** de ces conditions (`select_backfill` dans
`ingestion.py`) :

- score ≥ `FILNEWS_MIN_SCORE` (250) ;
- parmi les `FILNEWS_BACKFILL_TOP` (60) meilleurs **du mois** ;
- parmi les `FILNEWS_BACKFILL_DAY_TOP` (2) meilleurs **de son jour** (heure de
  Paris), à condition d'avoir au moins `FILNEWS_BACKFILL_DAY_MIN_SCORE` (20)
  votes : sans ce plancher, les jours calmes de 2016 donnaient des news à 0 vote.

Chaque mois a donc au moins 60 news et chaque jour au moins 2 (s'il y a eu des
articles à 20 votes ou plus ce jour-là) ; il n'y a pas de maximum : les mois récents gardent tout
ce qui dépasse 250, comme l'ingestion quotidienne. `--top 0 --day-top 0`
revient au seuil fixe seul.

Analyse heuristique de 2019-03 (152 news ≥ 100) : 2 min 20 (≈ 0,9 s/news),
vignette 150/152, tags 146/152, résumé 103/152 (68 %, contre 84 % en
2026-10). Environ 7 % d'articles disparus (404/410), une dizaine de refus 403
(blocage des robots) ; 10 liens Twitter, sans contenu exploitable.

## Données

```
data/
├── news/2026-10.json          # une liste de news par mois (versionné)
├── tag_aliases.json           # alias de tags, édité à la main (versionné)
├── media/thumbnails/*.webp    # vignettes (ignoré par git, copié dans l'image)
├── .secrets/                  # refresh token Reddit (ignoré)
└── .lock                      # verrou d'écriture (ignoré)
```

Les fichiers sont écrits de façon atomique (fichier temporaire + renommage) et
les écritures sont sérialisées entre processus par un verrou `flock`. On peut
donc lancer `ingest_news` pendant `analyze_news`.

⚠️ Les **vignettes ne sont plus versionnées** (environ 200 Mo avec
l'historique) : elles restent dans `data/media/` sur la machine qui lance les
commandes et sont copiées dans l'image Docker. Les sauvegarder à part ; à
défaut, `analyze_news --force` les régénère (mais certains articles ou
images auront disparu entre-temps).

## Performances

| Étape | Mesure / ordre de grandeur |
|---|---|
| `backfill_news` | ≈ 1 min 15 par mois (Arctic Shift + `/api/info`) |
| `analyze_news` | ≈ 0,9 s par news en série ; 8 workers, 2 par site, écritures par lots de 25 |
| `build_site` | rendu parallèle (fork, un processus par CPU) |
| Docker | gzip parallèle (`xargs -P $(nproc)`) |

- `related()` ne parcourt que les 150 news les plus proches dans le temps de
  chaque tag : coût constant même pour un tag de milliers de news.
- Les tags d'une seule news n'ont pas de page (≈ 60 % des tags) : deux fois
  moins de fichiers à générer.
- `sitemap.xml` est un index : une section (`sitemap-pages.xml`,
  `sitemap-news.xml`, `sitemap-tags.xml`) par fichier statique. Le build échoue
  si une section dépasse 50 000 URL (il faudrait alors la découper).
- Côté navigateur : archives par mois en liste compacte, Fil des gros tags par
  année, frise en barres au-delà de 40 news.

## Tests

`python manage.py test` — tests sans réseau (Reddit et HTTP mockés), chaque test
utilise un dossier de données temporaire. Couvre : stockage, ingestion et seuil,
client Reddit/OAuth, historique (Arctic Shift), doublons, alias de tags,
heuristiques d'analyse, Wayback Machine, analyse parallèle, vignettes, pages
et SEO, RSS, sitemap, archives par mois, frise, Fil par année, build statique
(série et parallèle).

## Docker

L'image est construite en deux étapes :

1. `python:3.12-slim` installe `requirements.txt`, copie le code **et `data/`**,
   lance `build_site` puis pré-compresse les fichiers (gzip).
2. `nginxinc/nginx-unprivileged:1.27-alpine` (non-root) sert `dist/` sur le
   **port 8000** avec : `gzip_static`, cache d'un an sur `/static/` (noms
   hashés), en-têtes de sécurité (CSP stricte, `X-Frame-Options`, etc.), 404
   personnalisée, `/auth/*` désactivé, `/archives/page/*` redirigé (301) vers
   `/archives/`.

### Construire

```bash
docker build -t filnews:latest .
# URL publique différente (préproduction…) :
docker build -t filnews:staging --build-arg SITE_URL=https://staging.filnews.fr .
```

### Lancer

```bash
docker run --rm -p 8000:8000 filnews:latest
# http://localhost:8000
```

### Déployer

Le conteneur est sans état : chaque mise à jour du contenu = une nouvelle image.

```bash
# 1. Mettre à jour le contenu (en local)
python manage.py ingest_news
python manage.py analyze_news
git add data && git commit -m "Update news"   # data/media est ignoré par git

# 2. Construire et publier l'image
docker build -t registry.example.com/filnews:$(date +%Y%m%d%H%M) .
docker push registry.example.com/filnews:<tag>

# 3. Redéployer (Kubernetes, Docker Compose, Scaleway Serverless Containers…)
```

Placer le conteneur derrière un reverse proxy / load balancer qui termine TLS et
ajoute `Strict-Transport-Security`. Les redirections nginx sont relatives
(`absolute_redirect off`), donc compatibles avec un proxy. Healthcheck intégré :
`GET /`.

### Publier sur la branche `pages` (hébergement statique)

Alternative à Docker : `publish_pages` génère le site puis le commite sur une
branche git **orpheline** `pages` qui ne contient que les fichiers générés
(HTML, RSS, sitemaps, `static/`, `media/`), plus `CNAME` (domaine tiré de
`SITE_URL`) et `.nojekyll`. Le commit passe par un index git temporaire : la
copie de travail et la branche courante ne sont jamais modifiées. Si le contenu
n'a pas changé, aucun commit n'est créé.

```bash
python manage.py ingest_news && python manage.py analyze_news
git add data && git commit -m "Update news"
python manage.py publish_pages              # --skip-build pour réutiliser dist/
git push origin pages                       # ou : publish_pages --push
```

Options : `--branch` (défaut `pages`), `--remote` (défaut `origin`), `--push`,
`--skip-build`. Ne pas lancer pendant un `analyze_news` / `ingest_news` (le
build lirait des fichiers en cours d'écriture).

Mise en ligne avec **GitHub Pages** : dépôt GitHub → *Settings* → *Pages* →
*Source : Deploy from a branch* → branche `pages`, dossier `/ (root)`. Pour le
domaine apex `filnews.fr` (le fichier `CNAME` est généré depuis `SITE_URL`),
créer chez le registrar des enregistrements `A` vers `185.199.108.153`,
`185.199.109.153`, `185.199.110.153`, `185.199.111.153` (et `AAAA` vers
`2606:50c0:8000::153` à `8003::153`), plus un `CNAME www` →
`<utilisateur>.github.io` pour que GitHub redirige `www` vers l'apex, puis
cocher *Enforce HTTPS*. (Cloudflare Pages,
Netlify… savent aussi servir une branche.)

### Mise à jour automatique chaque nuit (GitHub Actions)

Le workflow [`.github/workflows/nightly.yml`](../.github/workflows/nightly.yml)
tourne chaque nuit à 04:17 UTC (et à la demande : onglet *Actions* →
*Nightly news update* → *Run workflow*) :

1. restaure les vignettes depuis la branche `pages` (`git archive pages media`),
   puisqu'elles ne sont pas versionnées sur `main` ;
2. `ingest_news --period day` puis `analyze_news` ;
3. commite `data/news` sur `main` (si changement) ;
4. `publish_pages --push`.

Gratuit : le dépôt est public, donc les minutes Actions des runners hébergés
par GitHub ne sont pas facturées (un dépôt privé aurait 2 000 min/mois
offertes ; un passage dure quelques minutes).

Configuration (dépôt → *Settings* → *Secrets and variables* → *Actions*) :

| Nom | Type | Rôle |
|---|---|---|
| `REDDIT_CLIENT_ID` | secret | Identifiant de l'application Reddit |
| `REDDIT_CLIENT_SECRET` | secret | Secret de l'application Reddit |
| `REDDIT_USER_AGENT` | variable (optionnelle) | User-Agent Reddit (défaut `web:fr.filnews:v1.0 (by /u/filnews)`) |

Sans refresh token, l'ingestion utilise l'OAuth `client_credentials`. Le
workflow a besoin de `contents: write` (déclaré dans le fichier) ; si une
règle de protection de `main` interdit le push, autoriser GitHub Actions.
Un échec (Reddit indisponible…) envoie l'e-mail habituel de GitHub.

Limites par rapport à l'image nginx : pas d'en-têtes personnalisés (CSP,
`X-Frame-Options`, `Cache-Control` immuable), pas de redirection
`/archives/page/N/` → `/archives/`, pas de gzip pré-calculé (GitHub compresse
lui-même). Les vignettes (`media/`, ~300 Mo) sont versionnées sur cette
branche : GitHub Pages limite un site à 1 Go.

## Front-end

- Templates : `filnews/templates/` (HTML5 sémantique, accessibles).
- SCSS : `filnews/static/scss/` → `filnews/static/css/main.css` (généré, ignoré
  par git). Compilé par libsass via `filnews/assets.py`.
- JS : `filnews/static/js/main.js` (module ES, sans dépendance), en
  amélioration progressive — cartes d'historique au survol des tags (survol
  d'un point de la frise ↔ news de la liste via `data-news`) et mise en avant
  de l'entrée du Fil la plus proche du centre de l'écran (page d'un tag).
- JS : `filnews/static/js/theme.js` (script classique bloquant dans `<head>`,
  compatible CSP `script-src 'self'`) — bouton clair/sombre. Le choix est
  stocké dans `localStorage` (`filnews-theme`) et posé en `data-theme` sur
  `<html>` avant le premier rendu ; sans choix, `prefers-color-scheme` s'applique.
- Polices Oswald et Lora auto-hébergées (`static/fonts/`, licence OFL).

## Sécurité

- Aucun secret dans le code ni dans l'image.
- ⚠️ D'anciens secrets (Reddit, S3 Scaleway, PostgreSQL, `SECRET_KEY`) figurent
  dans l'historique git d'avant la réécriture : ils doivent être **révoqués**.
- Production sans code exécutable côté serveur (fichiers statiques seulement).
