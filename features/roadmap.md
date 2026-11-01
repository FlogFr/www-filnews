# Roadmap

Statuts : ✅ fait · 🚧 en cours · 💡 idée / à valider avec le propriétaire.

## v1.0 — Réécriture (octobre 2026) ✅

- ✅ Base de données fichiers JSON (1 fichier par mois), chargée au démarrage.
- ✅ Ingestion Reddit OAuth (`ingest_news --period day|week|month`), seuil configurable.
- ✅ Callback OAuth `/auth/reddit/callback` (refresh token stocké localement).
- ✅ Analyse : tags, résumé, vignette WebP ; heuristique + modèle local optionnel.
- ✅ Accueil (à la une, 5 news, 10 tags, RSS), fiches news, archives, tags avec
  historique (Fil vertical + frise dans la carte au survol), à propos, 404.
- ✅ SEO : canonical, Open Graph, JSON-LD, sitemap, robots, RSS.
- ✅ Accessibilité : landmarks, lien d'évitement, focus visible, contrastes, mode sombre (automatique + bouton clair/sombre).
- ✅ Site 100 % statique, Docker nginx non-root (port 8000), gzip, cache immuable, CSP stricte.
- ✅ Tests unitaires, ruff.

## v1.3 — Carte des tags (octobre 2026) ✅

- ✅ Frise ajustée à l'historique du tag (graduations jours / mois / années) :
  deux news à un jour d'écart ne se superposent plus.
- ✅ Liste cliquable des 5 dernières news dans la carte au survol, sous la
  frise ; survoler un point met sa news en avant.
- ✅ Le Fil met en avant la news la plus proche du centre de l'écran.
- ✅ Seuil d'ingestion par défaut relevé à 250 votes.

## Historique sur 10 ans 🚧

- ✅ Lot 1 : `backfill_news` (ids Arctic Shift + données Reddit `/api/info`),
  `--dry-run` avec répartition des scores. Mesuré sur 2016, 2019, 2022.
- ✅ Seuil pour l'historique : ≥ `FILNEWS_MIN_SCORE` **ou** top 60 du mois
  **ou** top 2 du jour avec ≥ 20 votes (`FILNEWS_BACKFILL_TOP`,
  `FILNEWS_BACKFILL_DAY_TOP`, `FILNEWS_BACKFILL_DAY_MIN_SCORE`).
- ✅ Lot 2 : dédoublonnage par URL, alias de tags (`data/tag_aliases.json`),
  exclusion de Twitter/X et YouTube.
- ✅ Lot 3 : `analyze_news` en parallèle (8 workers, 2 par site, écritures par
  lots de 25), repli sur la Wayback Machine.
- ✅ Lot 4 : `related` borné, rendu parallèle du build, sitemap index, archives
  par mois, pages de tag dès 2 news, gzip parallèle dans Docker.
- ✅ Lot 5 : Fil des gros tags par année, frise en barres, index des tags par
  lettre.
- ✅ Lot 6 : vignettes hors git (toujours dans l'image), import 2016-11 → 2026-09.

## Prochaines étapes

- 💡 **Rafraîchir les scores** : réingérer périodiquement la semaine passée
  pour mettre à jour les scores.
- 💡 **Flux RSS par tag** (`/tags/<slug>/rss.xml`).
- 💡 **Recherche** côté client (index JSON statique).
- 💡 **Images responsives** : `srcset` 320/640 px, AVIF.
- 💡 **CI** GitHub Actions : tests + ruff + build Docker à chaque push.
- 💡 **Déploiement automatisé** (registre + redéploiement) après ingestion.
- 💡 Mesure d'audience respectueuse de la vie privée (sans cookie), si besoin.
