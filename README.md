FilNews.fr
==========

**L'actualité vue par r/france.** FilNews sélectionne les liens d'actualité
qui font réagir r/france, les résume, les illustre et les relie entre eux par
des **fils** (personnalités politiques et grands thèmes) pour donner le
contexte d'un sujet dans le temps. Le code est ouvert, par souci de
transparence.

Le site est généré en **statique** par Django, puis servi par **nginx** dans un
conteneur Docker (port 8000). Il n'y a ni base de données ni Python en
production.

## Fonctionnalités

### Collecte des news (ingestion)

- Source : un subreddit, par défaut **r/france** (`FILNEWS_SUBREDDIT`).
- Seuil de votes : par défaut **250** (`FILNEWS_MIN_SCORE`). Un post à
  200 votes n'est pas ingéré.
- Commande `ingest_news` avec trois périodes : les 24 dernières heures
  (`--period day`, par défaut), la semaine (`week`) ou le mois précédent
  (`month`).
- Commande `backfill_news --from AAAA-MM [--to AAAA-MM]` pour importer
  l'historique mois par mois : les identifiants des posts viennent de
  l'archive [Arctic Shift](https://arctic-shift.photon-reddit.com), les
  données à jour (score, suppression) de l'API Reddit (`/api/info`).
  Un article est gardé s'il a **≥ 250 votes**, **ou** s'il est parmi les
  **60 meilleurs du mois** (`FILNEWS_BACKFILL_TOP`, `--top`), **ou** parmi les
  **2 meilleurs de son jour** avec au moins 20 votes
  (`FILNEWS_BACKFILL_DAY_TOP`, `FILNEWS_BACKFILL_DAY_MIN_SCORE`) : les
  scores d'avant 2020 sont bien plus faibles. `--dry-run` affiche seulement la
  répartition des scores.
- Exclus : posts texte, NSFW, épinglés, supprimés.
- **Sélection des médias** (`filnews/media.py`) : une liste de **médias
  autorisés** (presse nationale et régionale, audiovisuel, médias
  indépendants, presse étrangère, institutions) et une liste de **sites
  refusés** (YouTube, Twitter/X, réseaux sociaux, hébergeurs d'images,
  Wikipédia, blogs, satire…). Par défaut seuls les médias autorisés sont
  ingérés (`FILNEWS_MEDIA_WHITELIST=0` pour accepter tout site non refusé).
  `prune_news` liste les news déjà stockées hors de cette politique
  (`--apply` pour les supprimer).
- Une news déjà connue est mise à jour (score, commentaires, titre) sans perdre
  son analyse.
- **Un article = une news** : un second post vers le même article est ignoré,
  sauf s'il a un meilleur score (il remplace alors le premier).
- API Reddit en OAuth : secrets en variables d'environnement, callback sur
  `/auth/reddit/callback` (dev local uniquement).

### Analyse

- Commande `analyze_news` (8 téléchargements en parallèle, 2 au plus par site,
  `--workers`) : télécharge l'article et produit
  - jusqu'à **5 tags**, pris uniquement dans un **vocabulaire contrôlé**
    (`filnews/vocabulary.py`) : **personnalités politiques** (françaises et
    internationales) et **grands thèmes politiques et de société**
    (environnement, police, logement, immigration…) ;
  - un **résumé** d'environ 320 caractères ;
  - une **vignette** WebP 640×360.
- Deux analyseurs : `heuristic` (par défaut, sans dépendance lourde) et `local`
  (modèles CamemBERT/T5 exécutés en local). Aucune donnée n'est envoyée à un
  service tiers.
- Article disparu ou qui refuse les robots (404, 410, 403…) : on utilise sa
  copie de la **Wayback Machine** (`FILNEWS_WAYBACK=0` pour désactiver) ; à
  défaut, l'analyse se fait sur le titre et les données Reddit.
- `analyze_news --retag` recalcule les tags de toutes les news à partir des
  données stockées (titre, résumé, anciens tags, flair), sans rien télécharger.
- **Alias de tags** : `data/tag_aliases.json` (`{"Macron": "Emmanuel Macron"}`),
  appliqué au chargement, sans réanalyse.

### Site

- **Accueil** : bandeau « Chaque actu a une histoire. On vous donne le
  fil. », « À la une » (news la plus populaire des 24 dernières heures),
  **le fil du moment** (le fil qui compte le plus de news sur les 48 dernières
  heures : ses 5 dernières news sur une ligne chronologique, avec l'écart entre
  elles), les 5 dernières news avec leurs fils, les **7 fils du
  moment** (les plus présents sur 7 jours, avec leur sorte : personnalité ou
  thème), un encart vers la présidentielle 2027 et le flux RSS. Sur mobile :
  à la une, puis les dernières news, puis le fil du moment.
- **Présidentielle 2027** (`/presidentielle-2027/`) : les candidats déclarés
  et pressentis (`filnews/elections.py`, édité à la main) avec leurs fils
  associés, et **le fil de la campagne** ; une page par candidat
  (`/presidentielle-2027/<candidat>/`) avec toutes ses news depuis
  janvier 2025.
- **Fiche news** : résumé, vignette, liens vers l'article et la discussion
  Reddit, bloc **« Le contexte »** (rang de la news parmi celles du jour sur
  r/france, sa place dans chacun de ses fils et la news précédente), tags,
  jusqu'à 5 news liées (tags en commun).
- **Archives** : les mois par année, puis une page par mois
  (`/archives/AAAA/MM/`) avec les news jour par jour.
- **Fils (tags)** :
  - au **survol** (ou au focus) d'un tag, une carte affiche une **frise**
    chronologique (un point par news, ou une barre par période au-delà de 40
    news) dont l'échelle s'adapte à l'historique du tag (jours, mois ou
    années), puis ses 5 dernières news cliquables ; survoler un point met sa
    news en avant dans la liste ;
  - au **clic**, la page du tag commence par un **portrait chiffré** du sujet
    (période couverte, mois le plus actif, médias les plus cités, news la
    plus votée, fils voisins), puis présente **le Fil** : toutes ses news sur une
    ligne verticale, de la plus récente à la plus ancienne, avec l'écart de
    temps entre deux news ; la news au centre de l'écran est mise en avant ;
    au-delà de 60 news, le Fil est découpé par année ;
  - un tag n'a sa page qu'à partir de 2 news (sinon : texte simple) ;
  - un index alphabétique des tags, avec une barre de lettres.
- **Flux RSS** de toutes les news (les plus récentes d'abord), page « À
  propos », **mentions légales** (éditeur non professionnel, hébergeur, données
  personnelles, lien vers le code source sur GitHub), page 404.
- **Thème clair/sombre** : automatique, avec un bouton pour choisir.

### Qualité

- **SEO** : `<title>` et description uniques, canonical, Open Graph, JSON-LD
  (`WebSite`, `NewsArticle`, `BreadcrumbList`), `sitemap.xml` (index de
  sitemaps par section), `robots.txt`, vérification Bing Webmaster Tools
  (`BingSiteAuth.xml`, à la racine via `filnews/root/`). Les fiches news, qui reprennent
  surtout leur source, sont en `noindex, follow` et absentes du sitemap
  (`FILNEWS_INDEX_NEWS=1` pour les réindexer) : Google indexe les pages au
  contenu original (fils, présidentielle, archives).
- **Accessibilité** (WCAG AA) : HTML5 sémantique, landmarks, lien d'évitement,
  focus visible, contrastes, `prefers-reduced-motion`. Le site fonctionne sans
  JavaScript (amélioration progressive).
- **Performance et sécurité** : site rendu en parallèle (un processus par
  CPU), fichiers statiques pré-compressés, CSS/JS aux
  noms hashés (cache 1 an), CSP stricte, nginx non-root, aucun secret dans
  l'image.

## Démarrage rapide

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env               # renseigner REDDIT_CLIENT_ID / SECRET
python manage.py runserver         # http://localhost:8000
```

Mettre à jour le contenu puis construire l'image :

```bash
python manage.py ingest_news       # --period day|week|month
python manage.py backfill_news --from 2019-03 --dry-run   # historique
python manage.py analyze_news      # --analyzer heuristic|local, --force
docker build -t filnews .
docker run --rm -p 8000:8000 filnews
```

Ou publier le site statique sur la branche git `pages` (GitHub Pages…) :

```bash
python manage.py publish_pages --push   # build_site + commit sur `pages` + push
```

En production, un workflow GitHub Actions (`.github/workflows/nightly.yml`,
gratuit sur un dépôt public) le fait **4 fois par jour** : ingestion des dernières
24 h, analyse, commit de `data/news` sur `main`, puis publication sur `pages`.
Secrets à créer : `REDDIT_CLIENT_ID` et `REDDIT_CLIENT_SECRET`.

Tests et lint (obligatoires avant chaque commit) :

```bash
python manage.py test
ruff check . && ruff format --check .
```

## Technique

- Python 3.12, Django 5.2, SCSS compilé par libsass (sans Node.js), JavaScript
  vanilla en modules ES.
- **Base de données en fichiers** : `data/news/AAAA-MM.json` (un fichier par
  mois), chargés au démarrage et mis à jour par les commandes, versionnés et
  embarqués dans l'image Docker. Vignettes dans `data/media/`.
- `build_site` rend chaque page dans `dist/`. Docker en deux étapes : build
  Python, puis nginx qui sert `dist/` en HTTP sur le port 8000.
- `publish_pages` commite `dist/` sur une branche orpheline `pages` (avec
  `CNAME` et `.nojekyll`) pour un hébergement statique type GitHub Pages.
- Mise à jour nocturne par GitHub Actions (ingestion, analyse, publication).
- Code en anglais, maintenable et testé (tests unitaires sans réseau).

## Documentation

| Fichier | Contenu |
|---|---|
| [docs/technique.md](docs/technique.md) | Installation, configuration, commandes, Docker, déploiement |
| [docs/guide-utilisateur.md](docs/guide-utilisateur.md) | Guide utilisateur |
| [features/metier.md](features/metier.md) | Règles métier détaillées (ingestion, analyse, affichage) |
| [features/roadmap.md](features/roadmap.md) | Roadmap et idées |
| [claude/](claude/) | Directives de travail et architecture (pour Claude et les contributeurs) |

## Principes du projet

- Site en français ; code en anglais ; directives (`claude/`), base métier et
  roadmap (`features/`) et documentation (`docs/`) en français, tenues à jour.
- Bonnes pratiques HTML5, CSS/SCSS et JavaScript ; SEO et accessibilité soignés.
- Peu cher et performant : fichiers locaux plutôt qu'une base de données, site
  entièrement statique en production.
- En cas de doute ou de risque de casser quelque chose : poser la question au
  propriétaire avant d'agir.
