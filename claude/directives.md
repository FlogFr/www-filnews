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

## Front-end

- HTML5 sémantique, `lang="fr"`, un seul `<h1>` par page, landmarks
  (`header`, `nav`, `main`, `footer`), lien d'évitement, `aria-current`.
- Accessibilité (RGAA/WCAG AA) : contrastes ≥ 4.5:1, focus visible, cibles
  tactiles ≥ 44 px, `prefers-reduced-motion`, images décoratives en `alt=""`.
- SEO : `<title>` et `meta description` uniques, `canonical`, Open Graph,
  JSON-LD (`WebSite`, `NewsArticle`, `BreadcrumbList`), `sitemap.xml`,
  `robots.txt`, flux RSS.
- SCSS dans `filnews/static/scss/` (compilé par libsass, sans Node.js). libsass
  ne comprend pas `min()`, `clamp()` ni `rgb(… / …)` : utiliser `unquote("…")`
  et `rgba()`.
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

## Quand poser une question au propriétaire

- Toute ambiguïté sur une fonctionnalité attendue (voir `README.md` et `features/`).
- Suppression de données, changement de format des fichiers JSON, réécriture
  d'historique git, changement d'URL publique (impact SEO).
- Ajout d'un service externe payant ou d'un envoi de données à un tiers.

## Préférences exprimées par le propriétaire

- Analyse : heuristique par défaut **et** modèle local optionnel (pas d'API
  externe).
- Pas de cron dans le conteneur : ingestion et analyse sont lancées en local,
  puis une nouvelle image Docker est construite.
- Les anciens templates du thème et l'ancien code Django ont été supprimés
  (récupérables dans l'historique git).

## Maintenance de ces fichiers

À chaque tâche qui change le comportement, l'architecture ou une règle métier :
mettre à jour `claude/architecture.md`, `features/` et `docs/` dans le même
changement.

`README.md` est la vitrine du projet (fonctionnalités, démarrage rapide,
principes) : le mettre à jour dans le même changement dès qu'une
fonctionnalité visible, une commande ou une valeur par défaut évolue.
