# Directives de travail

Directives à suivre par Claude (et tout contributeur) sur FilNews. À mettre à
jour dès qu'une règle change ou qu'une préférence du propriétaire est exprimée.

## Langues

- **Code** (noms, commentaires, docstrings, messages de commit) : anglais.
- **Interface du site**, **documentation** (`docs/`), **directives** (`claude/`),
  **base métier** (`features/`) : français.

## Qualité du code

- Python ≥ 3.12, Django 5.2 LTS. Code lisible, typé quand c'est utile, sans
  sur-ingénierie.
- Lint/format : `ruff check .` et `ruff format .` (config dans `pyproject.toml`).
  Pas de hook pre-commit : lancer ruff à la main avant de committer.
- Tests : `python manage.py test`. Toute nouvelle règle métier ou correction de
  bug s'accompagne d'un test dans `filnews/tests/`. Les tests ne font **aucun
  appel réseau** (mock de `requests` / Reddit).
- Pas de nouvelle dépendance lourde dans le runtime : les dépendances ML vont
  dans l'extra `[ml]`, jamais dans `requirements.txt`.
- Garder `requirements.txt` (versions épinglées pour Docker) synchronisé avec
  `pyproject.toml`.

## Sécurité

- Aucun secret dans le dépôt. Secrets via variables d'environnement / `.env`
  (ignoré par git). Le refresh token Reddit est stocké dans
  `data/.secrets/reddit_token.json` (ignoré par git et par Docker, chmod 600).
- ⚠️ L'historique git contient d'anciens secrets (avant la réécriture d'octobre
  2026) : ils doivent être considérés comme compromis et révoqués.
- Les téléchargements (articles, images) sont bornés en taille et en durée, et
  limités à http/https.
- nginx envoie une CSP stricte (`'self'` uniquement) : **pas de script/style
  inline**, pas de CDN, pas de ressource tierce (polices auto-hébergées).
  L'attribut `style=""` est donc interdit dans les templates.
- Seule exception : `/newsletter/` et `/contact/` chargent les formulaires
  Sender.net et reCAPTCHA (`docker/security-headers-sender.conf` : scripts
  inline, `*.sender.net`, API Sender sur CloudFront, Google). Ne pas
  élargir cette CSP aux autres pages ni intégrer un formulaire Sender
  ailleurs sans l'accord du propriétaire ; un snippet tiers inline se
  déplace dans un fichier JS de `static/js/`.
- Design des formulaires Sender : dans `static/scss/sender-frame.scss`
  (injecté dans l'iframe), pas dans l'éditeur Sender ; vérifier le rendu
  réel (iframe de Sender) après chaque changement.

## Front-end

- HTML5 sémantique, `lang="fr"`, un seul `<h1>` par page, landmarks
  (`header`, `nav`, `main`, `footer`), lien d'évitement, `aria-current`.
- Accessibilité (RGAA/WCAG AA) : contrastes ≥ 4.5:1, focus visible, cibles
  tactiles ≥ 44 px, `prefers-reduced-motion`, images décoratives en `alt=""`.
- SEO : `<title>` et `meta description` uniques, `canonical`, Open Graph,
  JSON-LD (`WebSite`, `NewsArticle`, `BreadcrumbList`), `sitemap.xml`,
  `robots.txt`, flux RSS. Les fiches news sont en `noindex, follow` (contenu
  repris des sources, voir `FILNEWS_INDEX_NEWS`) : tout nouveau contenu
  original va de préférence sur les pages de fils.
- SCSS dans `filnews/static/scss/` (compilé par libsass, sans Node.js). libsass
  ne comprend pas `min()`, `clamp()` ni `rgb(… / …)` : utiliser `unquote("…")`
  et `rgba()`.
- Dates affichées : filtre `date_fr` (et `filnews.dates.format_date` en Python)
  plutôt que `date` dès que le format contient le jour (`j`), pour écrire
  « 1er novembre » et non « 1 novembre ».
- JavaScript : modules ES natifs, vanilla, en amélioration progressive (le site
  doit fonctionner sans JS).

## Données

- Les vignettes (`data/media/`) ne sont **pas** versionnées (trop lourdes) mais
  sont copiées dans l'image Docker.
- Alias de tags : `data/tag_aliases.json`, édité à la main (versionné).
- La « base de données » est `data/news/*.json` : elle est versionnée et embarquée
  dans l'image Docker. Ne jamais la modifier à la main sans passer par le
  `NewsStore` (écritures atomiques + verrou).
- Ne pas committer de données de démo/test dans `data/`.

## Git et publication

- **Autorisation permanente du propriétaire** : Claude peut **pousser
  directement sur `main`** et **publier le site** lui-même, sans redemander,
  une fois `python manage.py test` et `ruff check .` au vert. Les cas de la
  section suivante (suppression de données, changement d'URL publique…)
  demandent toujours une question avant d'agir.
- Avant de pousser : `git fetch origin main` et intégrer les commits du
  workflow (« Update news »). Jamais de force-push sur `main` ni sur `pages`.
- Publier en local :

  ```bash
  git fetch origin pages:pages                  # base de la branche pages
  git archive pages media | tar -x -C data      # vignettes (non versionnées sur main)
  python manage.py publish_pages --push
  ```

  Sans la branche `pages` locale, `publish_pages` créerait un commit sans
  parent ; sans les vignettes, le site publié les perdrait. Ne pas publier
  pendant un passage du workflow (toutes les 6 h à xx:17 UTC) : à défaut,
  le lancer à la demande (*Actions* → *Nightly news update* → *Run
  workflow*), qui publie aussi.

## Quand poser une question au propriétaire

- Toute ambiguïté sur une fonctionnalité attendue (voir `README.md` et `features/`).
- Suppression de données, changement de format des fichiers JSON, réécriture
  d'historique git, changement d'URL publique (impact SEO).
- Ajout d'un service externe payant ou d'un envoi de données à un tiers.

## Préférences exprimées par le propriétaire

- Analyse : heuristique par défaut **et** modèle local optionnel (pas d'API
  externe).
- Pas de cron dans le conteneur. L'ingestion et l'analyse tournent 4 fois par
  jour dans GitHub Actions (`.github/workflows/nightly.yml`, qui publie sur `pages`)
  et peuvent toujours être lancées en local. Le workflow doit rester **gratuit**
  (runners hébergés, dépôt public, pas de service payant).
- Tags : uniquement **personnalités politiques** et **grands thèmes politiques
  et sociétaux** (`filnews/vocabulary.py`) ; pas de lieux, organisations ni
  flairs génériques.
- Médias : liste blanche de médias autorisés + liste de sites refusés
  (`filnews/media.py`) ; mettre la doc à jour à chaque changement de liste.
- Slogan : « L'actualité vue par r/france » (r/france ne représente pas « les
  Français »).
- Mentions légales sans identité de l'éditeur ni adresse e-mail publiée
  (éditeur non professionnel, LCEN art. 6-III-2) ; le contact passe par le
  formulaire Sender de `/contact/` ; le code source reste public sur GitHub.
- Newsletter et contact : formulaires **Sender.net** (compte et formulaires
  dans `SENDER_*` de `settings.py`) ; leurs champs et textes se règlent dans
  Sender. Toute collecte de données doit être décrite dans les mentions
  légales (section `#donnees-personnelles`).
- Design : suivre les maquettes de `design/*.png` en gardant l'identité
  actuelle (couleurs, polices, mode sombre).
- Les anciens templates du thème et l'ancien code Django ont été supprimés
  (récupérables dans l'historique git).

## Maintenance de ces fichiers

À chaque tâche qui change le comportement, l'architecture ou une règle métier :
mettre à jour `claude/architecture.md`, `features/` et `docs/` dans le même
changement.

`README.md` est la vitrine du projet (fonctionnalités, démarrage rapide,
principes) : le mettre à jour dans le même changement dès qu'une
fonctionnalité visible, une commande ou une valeur par défaut évolue.
