# Base de connaissance métier

## Concept

FilNews présente **l'actualité vue par r/france** (slogan du site) : pas
seulement l'actualité française, mais celle qui fait réagir r/france — qui ne
représente pas « les Français » dans leur ensemble. Il ne rédige pas d'articles : il
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
| **Flair** | Catégorie choisie sur Reddit (Politique, Société, Écologie…). Ne devient un tag que si elle correspond à un thème du vocabulaire (Écologie → Environnement, Covid-19, Santé, Élections). |
| **Tag (fil)** | Sujet d'une news, pris dans le **vocabulaire contrôlé** (`filnews/vocabulary.py`) : une **personnalité politique** ou un **grand thème politique ou de société**. Aucun autre tag n'est créé (ni lieux, ni organisations, ni médias). Identifié par son *slug* (`emmanuel-macron`) ; le libellé affiché est l'orthographe la plus fréquente. Un tag n'a sa page (et sa carte au survol) qu'à partir de **2 news** (`FILNEWS_TAG_MIN_NEWS`) ; en dessous, il s'affiche en texte simple. |
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
   supprimés.
4. **Sélection des médias** (`filnews/media.py`, comparaison sur le domaine et
   ses sous-domaines) :
   - **sites refusés**, toujours : Reddit, vidéos (**YouTube**, Dailymotion…),
     réseaux sociaux (**Twitter/X**, Facebook…), hébergeurs d'images,
     Wikipédia, blogs et plateformes d'autopublication, sites satiriques
     (Le Gorafi…) ;
   - **médias autorisés** : presse nationale et régionale, audiovisuel,
     médias indépendants, presse tech/science, presse étrangère, institutions ;
   - par défaut (`FILNEWS_MEDIA_WHITELIST=1`), seuls les médias autorisés
     sont ingérés ; sinon, tout site non refusé l'est. Un sous-domaine refusé
     l'emporte sur un domaine autorisé (`blogs.mediapart.fr`).
5. Une news déjà connue est **mise à jour** (score, commentaires, titre, flair)
   sans perdre son analyse.
6. **Un article = une news** : un post vers un article déjà connu est ignoré,
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
2. **Tags** (5 maximum, `FILNEWS_MAX_TAGS`), uniquement issus du
   **vocabulaire contrôlé** (`filnews/vocabulary.py`, édité à la main) :
   - **personnalités politiques** : noms complets et noms seuls non ambigus
     (« Mélenchon », mais pas « Hollande » ni « Philippe »), sensibles à la
     casse (« Poutine » ≠ « poutine ») ; le nom le plus long l'emporte
     (« Jean-Marie Le Pen » avant « Le Pen ») ;
   - **thèmes** (≈ 45) : environnement, police, justice, immigration,
     logement, retraites, extrême droite, présidentielle… reconnus par une
     liste d'expressions, sans tenir compte de la casse (sauf sigles : « IA »,
     « CRS ») ;
   - score : titre 4, chapô 2, mots-clés de l'éditeur 2, flair 3, texte 0,5
     par mention (6 au plus). Il faut **2** pour une personnalité et **3**
     pour un thème (dans le titre, ou confirmé par deux sources) ;
   - à score égal, les personnalités passent avant les thèmes ;
   - plus d'erreurs du type « Heures » (« 20 Heures »), « Rassemblement »
     (« Rassemblement national ») ou « Payant » (flair).
   - `analyze_news --retag` recalcule les tags à partir des données stockées
     (titre, résumé, anciens tags comme mots-clés, flair), sans
     téléchargement ; une ré-analyse complète (`--force`) profite en plus du
     texte des articles.
3. **Résumé** (≈ 320 caractères max, coupé en fin de phrase) : description de
   l'éditeur, sinon début de l'article, sinon texte du post Reddit.
4. **Vignette** : image `og:image`, sinon aperçu Reddit ; recadrée en 16:9,
   640×360, WebP.
5. Si l'article a disparu ou refuse les robots (404, 410, 401, 403, 451,
   serveur injoignable), on utilise sa **copie de la Wayback Machine**
   (archive.org) la plus proche de la date du post, image comprise
   (`FILNEWS_WAYBACK`). À défaut, l'analyse se fait sur le titre et les données
   Reddit ; la news reste publiée.
6. Analyseur `local` (optionnel) : les mots-clés du modèle CamemBERT
   *keyword-extractor* comptent comme mots-clés de l'éditeur (les tags restent
   pris dans le vocabulaire), résumé par un modèle T5
   français. Aucune donnée n'est envoyée à un service tiers.

## Règles d'affichage

- **Accueil** :
  - « À la une » : news au **plus haut score** publiée dans les 24 h précédant
    la génération du site ; à défaut, la news la plus récente.
  - Bandeau d'introduction : « Chaque actu a une histoire. On vous donne le
    fil. » et les trois étapes (une news remonte, on la rattache à ses fils,
    chaque fil est une chronologie).
  - **Le fil du moment** : à côté de « À la une », le fil (tag ayant une
    page) qui compte le **plus de news sur les 48 h** précédant la plus
    récente (à égalité : le plus récent). Affiche son nom, son nombre total
    d'articles et sa date de début, ses **5 dernières news**
    (`FILNEWS_HOME_THREAD_COUNT`) sur une ligne verticale avec l'écart de temps
    entre deux news (la news à la une marquée), et un bouton « Remonter tout le
    fil ».
  - **5 news** : les plus récentes (hors « À la une »), en liste, avec leurs
    fils.
  - **Fils du moment** : 7 maximum (`FILNEWS_HOME_TAG_COUNT`), les tags ayant
    une page qui comptent le plus de news sur les **7 derniers jours**, avec
    leur sorte (Personnalité / Thème).
  - Encart **Présidentielle 2027** (candidats déclarés), légende des deux
    sortes de fils, lien vers le flux RSS.
- **Présidentielle 2027** :
  - liste des candidats dans `filnews/elections.py` (nom, parti, candidature
    déclarée ou pressentie, tags associés — par défaut son nom), **à tenir à
    jour à la main** ;
  - **fil d'un candidat** : toutes les news portant un de ses tags depuis le
    **1er janvier 2025** (`CAMPAIGN_START`) ;
  - **fil de la campagne** : depuis la même date, les news dont le titre ou le
    résumé contient « présidentielle 2027 », ou qui portent le tag d'un
    candidat avec un mot de campagne (présidentiel, candidat, campagne,
    primaire, 2027, Élysée) ; une présidentielle étrangère n'y entre pas.
- **Tags** : une pastille par tag, avec une silhouette pour une personnalité
  et `#` pour un thème.
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
