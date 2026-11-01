# Base de connaissance métier

## Concept

FilNews présente **l'actualité vue par les Français** (slogan du site) : pas
seulement l'actualité française, mais celle qui fait réagir r/france. Il ne rédige pas d'articles : il
**sélectionne** les liens d'actualité qui font réagir la communauté Reddit
francophone, les **résume**, les **illustre** et les **relie entre eux** par des
tags, pour donner le contexte d'un sujet dans le temps. Le but affiché sur le
site : **remettre du contexte à chaque article** en suivant ses tags, chaque
tag formant un **fil** (la frise de toutes les news du sujet). La sélection est
présentée aux lecteurs comme un **algorithme objectif** qui retient les articles
suscitant le plus d'intérêt (le détail des seuils reste dans la doc technique).

## Glossaire

| Terme | Définition |
|---|---|
| **News** | Un post Reddit qui pointe vers un article externe, avec son score, sa date, sa source (domaine), et après analyse : résumé, tags, vignette. Identifiant : l'id Reddit du post. |
| **Score** | Nombre de votes (upvotes) du post Reddit au moment de la dernière ingestion. |
| **Seuil** | Score minimum pour qu'un post soit ingéré. Défaut : **250** (`FILNEWS_MIN_SCORE`). Un post à 200 votes n'est jamais ingéré. |
| **Subreddit** | Source des news. Défaut : **r/france** (`FILNEWS_SUBREDDIT`). |
| **Flair** | Catégorie choisie sur Reddit (Politique, Société, Écologie…). Utilisée comme tag sauf si elle est générique. |
| **Tag** | Sujet d'une news : personne, lieu, organisation, thème. Identifié par son *slug* (`emmanuel-macron`) ; le libellé affiché est l'orthographe la plus fréquente. Un tag n'a sa page (et sa carte au survol) qu'à partir de **2 news** (`FILNEWS_TAG_MIN_NEWS`) ; en dessous, il s'affiche en texte simple. |
| **Alias de tag** | Autre nom d'un même sujet (« Macron » → « Emmanuel Macron »), déclaré à la main dans `data/tag_aliases.json`. |
| **Doublon** | Deux posts qui pointent vers le même article (même URL, hors `www`, protocole, `/amp` et paramètres de suivi). |
| **Historique d'un tag** | Frise chronologique de toutes les news d'un tag (carte au survol). |
| **Le Fil** | Sur la page d'un tag, l'historique en version verticale : un encart par news, alternativement à gauche et à droite de la ligne. |
| **À la une** | News la plus populaire des dernières 24 h. |

## Règles d'ingestion

1. Source : listing `top` du subreddit sur la période demandée :
   - `day` (défaut) : news des **24 dernières heures** ;
   - `week` : 7 jours ;
   - `month` : **le mois précédent** (31 jours glissants).
2. Seuls les posts avec **score ≥ seuil** sont retenus. Le listing étant trié
   par score décroissant, la lecture s'arrête au premier post sous le seuil.
3. Sont exclus : posts texte (`self`), posts NSFW, posts épinglés, posts
   supprimés, liens qui ne sont pas des articles (images/vidéos Reddit, imgur,
   reddit.com, **Twitter/X, YouTube**).
4. Une news déjà connue est **mise à jour** (score, commentaires, titre, flair)
   sans perdre son analyse.
5. **Un article = une news** : un post vers un article déjà connu est ignoré,
   sauf s'il a un meilleur score ; il remplace alors l'ancien post et reprend
   son analyse.

## Historique (`backfill_news`)

1. Mois par mois : identifiants des posts via l'archive Arctic Shift, puis
   données actuelles (score, suppression) via l'API Reddit.
2. Un article est gardé s'il remplit **au moins une** condition : score
   **≥ seuil** (250), **ou** parmi les **60 meilleurs du mois**
   (`FILNEWS_BACKFILL_TOP`), **ou** parmi les **2 meilleurs de son jour**
   (heure de Paris, `FILNEWS_BACKFILL_DAY_TOP`) s'il a au moins **20 votes**
   (`FILNEWS_BACKFILL_DAY_MIN_SCORE`). Les scores d'avant 2020 sont bien plus
   faibles (aucun article ≥ 250 en mars 2016). Minimums : 60 news par mois,
   2 par jour (si le jour a des articles à 20 votes ou plus) ; pas de maximum.

## Règles d'analyse

1. On télécharge la page de l'article et on lit ses métadonnées (`og:title`,
   `og:description`, `og:image`, mots-clés éditeur) et ses paragraphes.
2. **Tags** (5 maximum, `FILNEWS_MAX_TAGS`) :
   - entités du titre (poids 4), du chapô (2), du texte (0,5) : suites de mots
     à majuscule (« Emmanuel Macron », « État de Palestine »), sigles (« SNCF »),
     nom + nombre (« Ligue 1 ») ;
   - mots-clés de l'éditeur (bonus s'ils apparaissent aussi dans l'article) ;
   - le flair Reddit, sauf flairs génériques (Actus, Paywall, Meta, Forum Libre…) ;
   - exclus : mots isolés écrits aussi en minuscule dans l'article (noms
     communs), mots-clés génériques (« actualité », « France »…).
3. **Résumé** (≈ 320 caractères max, coupé en fin de phrase) : description de
   l'éditeur, sinon début de l'article, sinon texte du post Reddit.
4. **Vignette** : image `og:image`, sinon aperçu Reddit ; recadrée en 16:9,
   640×360, WebP.
5. Si l'article a disparu ou refuse les robots (404, 410, 401, 403, 451,
   serveur injoignable), on utilise sa **copie de la Wayback Machine**
   (archive.org) la plus proche de la date du post, image comprise
   (`FILNEWS_WAYBACK`). À défaut, l'analyse se fait sur le titre et les données
   Reddit ; la news reste publiée.
6. Analyseur `local` (optionnel) : tags par le modèle CamemBERT
   *keyword-extractor* fusionnés avec l'heuristique, résumé par un modèle T5
   français. Aucune donnée n'est envoyée à un service tiers.

## Règles d'affichage

- **Accueil** :
  - « À la une » : news au **plus haut score** publiée dans les 24 h précédant
    la génération du site ; à défaut, la news la plus récente.
  - **5 news** : les plus récentes (hors « À la une »), avec leurs tags sous
    chaque encart.
  - **Tags du moment** : 10 maximum, triés par date de la news la plus récente
    qui les porte (à égalité : nombre de news).
  - Lien vers le flux RSS.
- **Survol / focus d'un tag** : carte avec l'historique du tag. **Clic** : page du tag.
- **Carte au survol d'un tag**, de haut en bas : nom et nombre de news, la
  frise, puis la liste des **5 news les plus récentes** (date + titre,
  cliquables ; lien « Voir les N news » vers la page du tag s'il y en a plus).
  Survoler un point de la frise met sa news en rouge dans la liste (et
  inversement).
- **Frise d'un tag** : axe du temps **ajusté à l'historique du tag**, de la
  première à la dernière news (marge de 8 % de chaque côté, durée minimale de
  2 jours) ; un point par news (cliquable). Au-delà de **40 news**
  (`FILNEWS_TIMELINE_MAX_DOTS`), une **barre par période** à la place (par
  année si l'historique dépasse 5 ans, par mois au-delà de 3 mois, sinon par
  jour), hauteur proportionnelle au nombre de news. Graduations en années
  (≥ 3 ans), en mois (≥ 3 mois) ou en jours, 5 au maximum.
- **Le Fil (page d'un tag)** : ligne verticale, de la news la plus récente à la
  plus ancienne, sans échelle de temps (chaque news a sa place, même si deux
  news sont à quelques heures d'écart). Chaque encart porte sa date et l'écart
  avec la news précédente (« 2 jours plus tôt ») ; un repère marque chaque
  année. Les encarts alternent gauche/droite (à partir de 48rem ; en dessous,
  ligne à gauche et encarts à droite). Avec JavaScript, seule la news la plus
  proche du centre de l'écran est mise en avant (point, date et bordure en
  rouge) ; les autres ont un point et une date neutres (blancs en mode
  sombre). Sans JavaScript, tout reste en rouge.
- **Fil d'un gros tag** (plus de **60 news**, `FILNEWS_TAG_THREAD_SIZE`) :
  découpé **par année**. `/tags/<slug>/` montre l'année la plus récente,
  `/tags/<slug>/<année>/` les précédentes ; une barre d'années (avec le nombre
  de news) permet de naviguer.
- **Index des tags** : tags qui ont une page, classés par lettre (barre de
  lettres en haut de page).
- **Archives** : `/archives/` liste les mois par année (avec le nombre de news) ;
  `/archives/AAAA/MM/` liste les news du mois **jour par jour**, en liste
  compacte (titre, source, score), avec liens vers les mois voisins.
  L'ancienne pagination `/archives/page/N/` redirige vers `/archives/` (301).
- **News liées** : jusqu'à 5 news partageant le plus de tags, parmi les 150
  news les plus proches dans le temps de chaque tag.
- **RSS** : toutes les news, de la plus récente à la plus ancienne.

## Fraîcheur

Le site est statique : son contenu correspond au dernier `build_site` (donc à la
dernière image Docker). « Les 24 dernières heures » s'entendent par rapport à
l'heure de génération.
