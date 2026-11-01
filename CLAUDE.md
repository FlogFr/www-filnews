# CLAUDE.md — FilNews.fr

Point d'entrée des directives pour Claude. **Toutes les directives détaillées
sont dans [`claude/`](claude/) (en français) et doivent être tenues à jour à
chaque changement significatif.**

| Fichier | Contenu |
|---|---|
| [claude/directives.md](claude/directives.md) | Règles de travail, conventions de code, ce qu'il faut demander avant d'agir |
| [claude/architecture.md](claude/architecture.md) | Architecture, modules, flux de données, décisions techniques |
| [features/](features/) | Base de connaissance métier et roadmap |
| [docs/technique.md](docs/technique.md) | Documentation technique (installation, commandes, Docker, déploiement) |
| [docs/guide-utilisateur.md](docs/guide-utilisateur.md) | Guide utilisateur |
| [README.md](README.md) | Présentation du projet : fonctionnalités, démarrage rapide, principes |

## Résumé en 30 secondes

- Site de news français : posts r/france ≥ 250 votes → résumés, tags, thumbnails.
- Django 5.2 **sans base de données** : JSON dans `data/news/AAAA-MM.json`.
- Le site est **pré-généré en statique** (`build_site`) et servi par **nginx**
  (Docker, port 8000). Django ne tourne jamais en production.
- Les commandes d'ingestion/analyse tournent **en local** ; on reconstruit
  ensuite l'image Docker.

## Commandes essentielles

```bash
source .venv/bin/activate
python manage.py runserver            # dev (compile le SCSS à la volée)
python manage.py ingest_news          # --period day|week|month
python manage.py analyze_news         # --analyzer heuristic|local, --force
python manage.py build_site           # -> dist/
python manage.py test                 # tests unitaires (obligatoires avant commit)
ruff check . && ruff format --check .
docker build -t filnews .
```

## Règles d'or

1. Code, noms et commentaires **en anglais** ; docs, directives et UI **en français**.
2. Ne jamais committer de secret : tout passe par des variables d'environnement (`.env`).
3. Lancer `python manage.py test` et `ruff check .` avant de terminer une tâche.
4. Mettre à jour `claude/`, `features/` et `docs/` quand le comportement change.
5. Garder `README.md` à jour : toute fonctionnalité ajoutée, modifiée ou
   supprimée (ou un défaut de configuration qui change) doit y être reflétée
   dans le même changement.
6. Poser des questions en cas de doute ou de risque de casse (voir `claude/directives.md`).
