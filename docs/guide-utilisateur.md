# Guide utilisateur

## Pour les lecteurs

### La page d'accueil

- **À la une** : l'actualité qui a reçu le plus de votes ces dernières 24 heures.
- **Dernières news** : les 5 actualités les plus récentes, chacune avec sa
  source, sa date, un court résumé, son score Reddit et ses tags.
- **Tags du moment** : les sujets les plus récents (10 au maximum).
- **Suivre FilNews** : le lien vers le flux RSS.

### Les tags et leur historique

Chaque news porte des tags (personnes, lieux, organisations, thèmes).

- **Survolez** un tag (ou placez-y le focus au clavier) : une carte affiche son
  **historique** : une frise chronologique où chaque point est une news, puis
  la liste des dernières news liées à ce tag (cliquables). Survolez un point
  pour repérer sa news dans la liste. L'échelle de la frise s'adapte à
  l'historique du tag (jours, mois ou années), si bien que deux news à un jour
  d'écart restent bien distinctes.
- **Cliquez** sur un tag : sa page présente **le Fil**, une ligne verticale où
  toutes les news du sujet s'enchaînent de la plus récente à la plus ancienne,
  alternativement à gauche et à droite, avec leur date et le temps écoulé
  entre deux news. En faisant défiler, la news au centre de l'écran est mise
  en avant en rouge.
- La page **Tags** liste les sujets suivis (au moins 2 news) par ordre
  alphabétique, avec une barre de lettres pour sauter à la bonne section. Un
  tag qui n'apparaît qu'une fois s'affiche en texte simple, sans lien.
- Un gros sujet (plus de 60 news) a son Fil découpé **par année** : une barre
  d'années en haut du Fil permet de remonter le temps.
- Les **Archives** se parcourent par mois, puis jour par jour.

### Une fiche news

Elle présente le titre, la source, le résumé, l'image, puis :

- **Lire l'article** : ouvre l'article original chez l'éditeur ;
- **Voir la discussion sur Reddit** : les commentaires de la communauté ;
- **Dans le fil de l'actualité** : les tags de la news ;
- **Sur les mêmes sujets** : jusqu'à 5 news qui partagent des tags.

### Le flux RSS

Ajoutez `https://www.filnews.fr/rss.xml` à votre lecteur de flux (Feedly,
NetNewsWire, Thunderbird…) pour recevoir toutes les news, des plus récentes aux
plus anciennes.

### Accessibilité

Le site est utilisable au clavier (lien « Aller au contenu principal », focus
visible), compatible lecteurs d'écran, respecte le mode sombre et la réduction
des animations de votre système.

### Thème clair / sombre

Par défaut, le site suit le thème de votre système. Le bouton lune / soleil
en haut à droite du menu permet de forcer le thème clair ou sombre ; ce choix
est mémorisé dans votre navigateur.

## Pour l'éditeur du site

### Mettre à jour les news (routine quotidienne)

```bash
source .venv/bin/activate
python manage.py ingest_news      # récupère les news des dernières 24 h (≥ 250 votes)
python manage.py analyze_news     # résumés, tags et vignettes des nouvelles news
python manage.py runserver        # vérifier le résultat sur http://localhost:8000
```

Puis publier (voir `docs/technique.md`, section Déployer) : commit de `data/`,
puis soit `docker build` et déploiement de la nouvelle image, soit
`python manage.py publish_pages --push` (branche `pages`, GitHub Pages…).

### Rattraper un mois

```bash
python manage.py ingest_news --period month
python manage.py analyze_news
```

### Importer l'historique

```bash
python manage.py backfill_news --from 2019-03 --dry-run   # combien de news selon le seuil ?
python manage.py backfill_news --from 2019-01 --to 2019-12
python manage.py analyze_news
```

Une news est gardée si elle a **250 votes ou plus**, **ou** si elle est parmi
les **60 meilleures du mois**, **ou** parmi les **2 meilleures de son jour**
(avec au moins 20 votes). Les anciennes années, aux scores bien plus faibles,
ne sont donc pas vides : au moins 60 news par mois et 2 par jour (sauf jour
sans article à 20 votes). Pas de maximum. Changer ces minimums :
`--top 80 --day-top 3 --day-min-score 30`, ou `FILNEWS_BACKFILL_TOP` /
`FILNEWS_BACKFILL_DAY_TOP` / `FILNEWS_BACKFILL_DAY_MIN_SCORE` dans `.env`.

### Fusionner deux tags (alias)

Créer ou compléter `data/tag_aliases.json` : à gauche l'alias, à droite le nom
à garder.

```json
{
  "Macron": "Emmanuel Macron",
  "LFI": "La France insoumise"
}
```

C'est pris en compte immédiatement (au prochain `runserver` / `build_site`),
sans réanalyse. Les alias ne s'enchaînent pas : viser directement le nom final.

### Corriger une news

- Relancer l'analyse d'une news : `python manage.py analyze_news <id_reddit> --force`
  (l'id est à la fin de l'URL de la fiche : `/news/titre-de-la-news-<id>/`).
- Correction manuelle (tags, résumé) : éditer le fichier
  `data/news/AAAA-MM.json` concerné **quand aucune commande ne tourne**, puis
  vérifier avec `runserver`.

### Changer le seuil ou la source

Dans `.env` : `FILNEWS_MIN_SCORE=150`, `FILNEWS_SUBREDDIT=france`. Ou ponctuellement :
`python manage.py ingest_news --min-score 150`.

### Analyse de meilleure qualité

Installer les modèles locaux (voir la documentation technique) puis :
`python manage.py analyze_news --analyzer local`. Plus lent, mais tags et
résumés plus précis. Rien n'est envoyé à un service externe.
