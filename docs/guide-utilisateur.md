# Guide utilisateur

## Pour les lecteurs

### La page d'accueil

- **À la une** : l'actualité qui a reçu le plus de votes ces dernières 24 heures.
- **Le fil du moment** : le sujet le plus présent ces dernières 48 heures, avec
  ses dernières news sur une ligne chronologique et le temps écoulé entre
  elles ; « Remonter tout le fil » ouvre sa page.
- **Dernières news** : les 5 actualités les plus récentes, chacune avec sa
  source, sa date, un court résumé, son score Reddit et ses fils.
- **Historique de ce fil** : devant les fils d'une news (à la une ou parmi
  les dernières), cette pastille rouge indique combien de news compte le
  fil de ses tags (par exemple « Police + Justice », nom affiché au
  survol) et ouvre directement son historique sur sa fiche.
- **Fils du moment** : les 7 fils les plus présents cette semaine, avec leur
  sorte (personnalité ou thème).
- **Présidentielle 2027** : lien vers le fil de la campagne et les candidats.
- **Suivre FilNews** : les liens vers la newsletter et le flux RSS.

Sur mobile, la page se lit dans l'ordre : « À la une », « Dernières news »,
« Le fil du moment », puis les fils du moment, la présidentielle et
« Suivre FilNews ».

### La présidentielle 2027

La page **Présidentielle 2027** (menu) liste les candidats, déclarés ou
pressentis, avec leur parti et leurs fils. En dessous, **le fil de la
campagne** rassemble toutes les news de la campagne. Chaque candidat a sa
page : toutes ses news depuis janvier 2025, avec un lien vers son fil
complet.

### Les fils (tags) et leur historique

Chaque news est rattachée à des fils de deux sortes : les **personnalités
politiques** (silhouette) et les **grands thèmes** politiques et de société
(`#` : environnement, police, logement…).

- **Survolez** un tag (ou placez-y le focus au clavier) : une carte affiche son
  **historique** : une frise chronologique où chaque point est une news, puis
  la liste des dernières news liées à ce tag (cliquables). Survolez un point
  pour repérer sa news dans la liste. L'échelle de la frise s'adapte à
  l'historique du tag (jours, mois ou années), si bien que deux news à un jour
  d'écart restent bien distinctes.
- **Cliquez** sur un tag : sa page commence par un portrait du sujet (période
  couverte, mois le plus actif, médias les plus cités, news la plus votée,
  fils voisins), puis présente **le Fil**, une ligne verticale où
  toutes les news du sujet s'enchaînent de la plus récente à la plus ancienne,
  alternativement à gauche et à droite, avec leur date et le temps écoulé
  entre deux news. En faisant défiler, la news au centre de l'écran est mise
  en avant en rouge.
- La page **Tous les fils** liste les sujets suivis (au moins 2 news) par ordre
  alphabétique, avec une barre de lettres pour sauter à la bonne section. Un
  tag qui n'apparaît qu'une fois s'affiche en texte simple, sans lien.
- Un gros sujet (plus de 60 news) a son Fil découpé **par année** : une barre
  d'années en haut du Fil permet de remonter le temps.
- Les **Archives** se parcourent par mois, puis jour par jour.

### Une fiche news

Elle présente le titre, la source, le résumé, l'image, puis :

- **Lire l'article** : ouvre l'article original chez l'éditeur ;
- **Voir la discussion sur Reddit** : les commentaires de la communauté ;
- **Le fil de cette news** (news d'au moins 2 tags, à droite de l'article
  sur grand écran, sous les liens sur mobile) : un fil peut réunir
  plusieurs tags ; celui-ci rassemble les news qui portent **tous les
  mêmes tags** que celle-ci (« Police + Justice ») — combien il y en a et
  depuis quand, la place de la news, une frise où elle est marquée, les
  news qui l'entourent (dont celles d'avant), puis « Voir les N news de ce
  fil » pour la liste complète. Si aucune autre news ne porte tous ses
  tags, c'est le fil le plus proche qui s'affiche. En bas de l'encart,
  « Ses autres fils » déplie d'autres combinaisons de ses tags ;
- **Le contexte** : le rang de la news parmi celles du jour sur r/france, et
  pour ses principaux fils sa place dans le fil et la news qui l'a précédée ;
- **Dans le fil de l'actualité** : les tags de la news (survolez-en un pour
  son historique) ;
- **Sur les mêmes sujets** : jusqu'à 5 autres news qui partagent des tags.

### Le flux RSS

Ajoutez `https://filnews.fr/rss.xml` à votre lecteur de flux (Feedly,
NetNewsWire, Thunderbird…) pour recevoir toutes les news, des plus récentes aux
plus anciennes.

### La newsletter

Le lien **Newsletter** (en-tête et pied de page) ouvre la page d'inscription :
saisissez votre adresse e-mail pour recevoir les news par e-mail. La
newsletter est gratuite, sans publicité, et chaque e-mail contient un lien de
désinscription.

### Nous contacter

Le lien **Contact** (pied de page) ouvre un formulaire pour écrire à
l'éditeur : une question, une erreur dans une news, un média ou un fil à
suggérer, une demande de retrait d'un contenu, ou l'exercice de vos droits sur
vos données.

Les deux formulaires sont fournis par Sender et ont besoin de JavaScript. Si
le formulaire ne s'affiche pas, une extension (bloqueur de publicités ou de
traceurs) le bloque peut-être : autorisez `sender.net` sur la page, ou
utilisez l'alternative proposée (flux RSS, ticket GitHub).

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

### Modifier le vocabulaire des tags

Les tags possibles sont listés dans `filnews/vocabulary.py` :
`PERSONALITIES` (nom → expressions qui le désignent, sensibles à la casse) et
`THEMES` (thème → expressions, insensibles à la casse sauf sigles). Après une
modification, recalculer les tags sans rien télécharger :

```bash
python manage.py analyze_news --retag
```

### Mettre à jour les candidats à la présidentielle

Éditer `CANDIDATES` dans `filnews/elections.py` (nom, parti, `DECLARED` ou
`POTENTIAL`, et éventuellement `tags=(...)` si d'autres fils que le nom
doivent alimenter son fil), et mettre à jour la date du commentaire. Un
candidat qui se retire est simplement retiré de la liste : son tag reste
dans le vocabulaire tant qu'il s'agit d'une personnalité politique.

Le nom (et chaque tag) doit exister dans `PERSONALITIES`
(`filnews/vocabulary.py`) : `python manage.py test` échoue sinon. Pour un
nouveau venu, ajouter son entrée au vocabulaire, puis recalculer les tags des
news qui le citent (ou de tout l'historique, plus long) :

```bash
python manage.py analyze_news --retag <id> <id>…   # ids Reddit des news concernées
python manage.py analyze_news --retag              # tout l'historique
```

### Médias autorisés et refusés

`ALLOWED_DOMAINS` et `BLOCKED_DOMAINS` dans `filnews/media.py`. Un domaine
couvre ses sous-domaines. Pour lister (puis supprimer) les news déjà stockées
qui ne respectent plus la politique :

```bash
python manage.py prune_news            # liste, ne supprime rien
python manage.py prune_news --apply    # supprime ces news et leurs vignettes
```

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

### Newsletter et formulaire de contact (Sender)

Les formulaires se modifient dans l'interface de **Sender** (sender.net), pas
dans le code : champs, textes, message de confirmation, et l'envoi des
campagnes de la newsletter. Les inscrits et les messages de contact arrivent
dans Sender. Le design (polices, couleurs, thème sombre) est appliqué par le
site : inutile de le régler dans Sender. Le titre et l'introduction saisis
dans Sender ne s'affichent pas (la page a les siens, dans
`templates/newsletter.html` et `templates/contact.html`) : les garder
cohérents. Voir la documentation technique (« Formulaires Sender »).

Pour utiliser un autre formulaire Sender, changer son identifiant
(`SENDER_NEWSLETTER_FORM_ID`, `SENDER_CONTACT_FORM_ID`) dans
`filnews/settings.py`, puis republier le site.

### Analyse de meilleure qualité

Installer les modèles locaux (voir la documentation technique) puis :
`python manage.py analyze_news --analyzer local`. Plus lent, mais tags et
résumés plus précis. Rien n'est envoyé à un service externe.
