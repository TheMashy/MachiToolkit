# MachiToolkit

**Machi Tool** est une boite a outils personnelle pour piloter la
workstation : une application Windows portable, logee dans la barre des
taches, qui se met a jour toute seule depuis les publications de ce depot.

Elle s'ouvre sur un accueil qui porte une tuile par module. Il y en a une
pour l'instant ; les suivantes viendront s'aligner a cote.

## Module Lumiere

Un brin d'ampoules Bluetooth (protocole HiLighting) dont la couleur suit ce
qui se passe a l'ecran.

| Mode | Ce qui pilote la couleur |
|---|---|
| Applications | une regle par programme ou par site : Netflix en rouge, GitHub en vert... |
| Ecran | la couleur dominante de l'ecran, luminance suivie |
| Son | ce qui sort des haut-parleurs : bande de frequences et brillance du spectre |
| Mixte | moitie regle, moitie ecran |

En mode Ecran, la capture passe par une vignette : Windows reduit lui-meme
l'ecran a une douzaine de pixels et l'application ne relit que ceux-la, au
lieu de recopier puis reduire l'image entiere. C'est ce qui permet de monter
a 30 images par seconde. Trois reglages etalonnent la reponse — niveau de
noir, niveau de blanc, courbe — pour qu'un ecran qui ne descend jamais au
noir absolu ni ne monte au blanc pur utilise quand meme toute la dynamique
de la guirlande. Comme en mode Son, on choisit ce que la luminosite de
l'ecran fait bouger, et une luminosite de base est tenue quand elle ne
pilote pas l'eclat.

En mode Son, on choisit ce que la musique fait bouger : la **luminosite**
(la couleur reste franche en permanence, seul l'eclat suit le rythme), la
**saturation** (eclat constant, la couleur palit dans les passages calmes),
ou les deux. Ce que le son ne pilote pas est tenu a une valeur fixe, reglee
au curseur. Deux jauges montrent en direct la luminosite et la saturation
reellement envoyees, et laquelle des deux le son est en train de piloter.

Une passerelle HTTP locale, fermee par defaut, permet en plus a une page web
de prendre la main sur les lumieres.

## Installation

1. Telecharger `MachiTool.exe` depuis la
   [derniere publication](https://github.com/TheMashy/MachiToolkit/releases/latest).
2. Double-cliquer.

L'exe est son propre installeur : il se copie dans
`%LOCALAPPDATA%\MachiTool`, s'ajoute au demarrage de Windows et se lance.
Son icone apparait pres de l'horloge.

Si Guirlande ambiante (le nom de l'application jusqu'a la 1.1) est deja
installee, Machi Tool reprend ses reglages au premier lancement : guirlande
appairee, regles, preferences. L'ancien dossier est laisse en place, on peut
le supprimer a la main une fois rassure.

Windows SmartScreen affichera un avertissement au premier lancement : l'exe
n'est pas signe, une signature de code coute quelques centaines d'euros par
an. « Informations complementaires » puis « Executer quand meme ».

### Sans publication

Tant qu'aucune publication n'existe, le lien ci-dessus ne mene nulle part.
L'exe est quand meme la : chaque poussee sur `main` en compile un.

Onglet **Actions** > dernier passage de **Publication** > section
**Artifacts** en bas de page > `MachiTool-<version>`. C'est un zip qui
contient le meme exe, garde trente jours. Meme chemin pour essayer un build
plus recent que la derniere publication.

## Mises a jour

Une fois installee, l'application n'a plus besoin qu'on s'occupe d'elle.

Toutes les six heures elle lit l'API publique de GitHub pour savoir si une
publication plus recente existe. Si oui, une bulle apparait et l'entree
« Mettre a jour vers la version X » s'ajoute au menu de son icone. Un clic
telecharge le nouvel exe et le lance : il arrete l'ancienne version, se copie
par-dessus et redemarre. `config.json` n'est jamais touche, aucun reglage
n'est perdu.

Trois cases dans l'onglet **Mises a jour** du panneau :

- **Verifier automatiquement** — decocher pour ne plus rien verifier.
- **Poser la mise a jour sans rien demander** — cochee, plus aucun clic :
  l'application se ferme et redemarre seule sur la nouvelle version.
  Decochee par defaut, pour ne pas couper les lumieres en pleine soiree.
- **Accepter aussi les pre-versions** — pour tester avant tout le monde.

Rien ne sort de la machine : la verification est une lecture, pas un envoi.
Le numero de version installe lui-meme n'est pas transmis.

## Le pont avec BrainDebugger

Machi Tool sait dialoguer avec [BrainDebugger](https://braindebugger-production.up.railway.app).
Deux chemins, parce que deux situations.

**Un onglet du site est ouvert.** Le site tourne sur Internet, l'application
ecoute sur `127.0.0.1` — et c'est le navigateur, sur cette machine, qui fait
le lien. Une page en HTTPS peut appeler l'adresse locale : les navigateurs la
traitent comme sure et l'exemptent du blocage de contenu mixte. Le site pose
alors une couleur, une humeur, un rappel, sans delai.

    POST /couleur          {"couleur": "#7C3AED", "duree": 30}
    POST /humeur           {"humeur": "Musique"}
    POST /rappel           {"id": "...", "titre": "...", "texte": "..."}
    POST /humeur-du-jour   {"valeur": 3, "libelle": "...", "couleur": "..."}
    POST /journal          {"jours": [...], "reperes": [...]}

**Aucun onglet ouvert.** Plus rien ne peut joindre cette machine depuis
Internet : elle est derriere un routeur, sans adresse publique. C'est donc
l'application qui va demander, toutes les dix minutes par defaut :

    GET <site>/api/machitool/attente
    -> {"rappels": [...], "humeur": {...}, "jours": [...], "reperes": [...]}

Toutes les cles sont facultatives. Tant que cette route n'existe pas cote
site, le 404 est avale sans bruit et rien ne casse — la page Passerelle le
dit simplement.

Les pages **Calendrier** et **Moi** affichent ce que le site a envoye. Elles
n'inventent rien et ne conservent rien : sans donnees, elles le disent.

## Ecrans haute resolution

L'interface se met a l'echelle de l'ecran **qui porte la fenetre**, et s'y
refait quand on la deplace : passer d'un 4K a 150 % a un 1080p a 100 % la
ramene a sa taille, au lieu de garder celle du premier ecran. Sans le flou
qu'on obtient en laissant Windows agrandir l'image.

Les reglages non enregistres repartent du fichier a ce moment-la : refaire
l'interface est la seule facon de changer la taille des caracteres, que
tkinter fige a la creation de chaque widget.

Si la detection se trompe, **Reglages > Affichage > Echelle de l'interface**
force une valeur : 1.00 pour un ecran classique, 1.50 pour un 4K a 150 %,
2.00 pour un 4K a 200 %. Zero rend la main a la detection. Le changement
prend effet au lancement suivant.

## Publier une nouvelle version

La regle tient en une phrase : **une publication nait des que `VERSION`
porte un numero encore jamais publie.**

1. Faire ses modifications.
2. Monter `VERSION` dans `machi_tool.py` — seule source de verite pour le
   numero de version.
3. Fusionner sur `main`.

C'est tout. Le workflow compile sous Windows, calcule l'empreinte SHA-256,
cree la publication `v1.4.0` avec des notes generees a partir des commits
et y joint `MachiTool.exe`. Compter deux minutes. Les exemplaires installes
la proposeront a leur prochaine verification.

Une poussee sur `main` qui ne change pas `VERSION` ne fait qu'un build de
controle : l'exe part en artefact, la publication existante n'est pas
touchee.

Poser un tag `v1.4.0` a la main, ou lancer **Actions > Publication > Run
workflow**, remplace les fichiers d'une publication deja sortie — utile
pour rattraper un binaire rate sans changer de numero. Un tag qui ne
concorde pas avec `VERSION` est refuse, plutot que de publier un exe qui se
croirait plus ancien que sa propre publication et se proposerait sa mise a
jour en boucle.

Le nom du tag n'est pas decoratif : c'est lui que l'application compare a
son propre `VERSION`. Il lui faut la forme `v1.4.0`. Un tag `v01` serait lu
comme la version 1.0.0 et ignore par toute installation plus recente.

## Compiler a la main

Utile seulement pour tester une version pas encore publiee.

```bash
pip install -r requirements.txt pyinstaller
python machi_tool.py --icone
pyinstaller --noconfirm --clean MachiTool.spec
```

Ou, sans rien connaitre a Python, double-cliquer `Compiler.bat` : il installe
Python si besoin, puis les dependances, puis compile. Les deux chemins
passent par `MachiTool.spec`, donc sortent le meme exe que la CI.

Le resultat est dans `dist\`, qui n'est pas versionne : un exe de 34 Mo par
version n'a rien a faire dans l'historique du depot.

## En mode script

```bash
python machi_tool.py               # lance sans installer
python machi_tool.py --version     # affiche le numero de version
python machi_tool.py --verifier-maj  # interroge GitHub, affiche le resultat
python machi_tool.py --icone       # regenere icone.ico
python machi_tool.py --lanceur     # ajoute au demarrage de Windows
python machi_tool.py --retirer     # retire du demarrage
```

Lance ainsi, la configuration reste a cote du script et l'installation
automatique ne se declenche pas.

## Ou vivent les fichiers

| Chemin | Contenu |
|---|---|
| `%LOCALAPPDATA%\MachiTool\MachiTool.exe` | l'application installee |
| `%LOCALAPPDATA%\MachiTool\config.json` | tous les reglages |
| `%LOCALAPPDATA%\MachiTool\journal.log` | le journal, a lire quand ca coince |
| `%LOCALAPPDATA%\MachiTool\maj\` | l'exe telecharge, efface au demarrage suivant |
| `%APPDATA%\...\Startup\machitool.vbs` | l'entree de demarrage Windows |

## Ajouter un outil au toolkit

Le mecanisme de mise a jour ne sait rien de la guirlande. Il tient dans la
section « Mises a jour depuis GitHub » de `machi_tool.py` et ne depend que
de trois choses :

- `DEPOT_GITHUB`, le depot a interroger ;
- `VERSION`, comparee au tag de la derniere publication ;
- un `.exe` joint a cette publication, retrouve par son extension et non par
  son nom — un futur outil peut donc s'appeler autrement.

Cote interface, l'accueil est deja une grille : ajouter un outil, c'est
ajouter une tuile a cote de `tuile_lumiere`, un intitule de groupe dans
`SECTIONS` (une entree dont la cle est vide) et les pages qui vont avec.
Une tuile fantome marque la place en attendant.

Reste a trancher, le jour ou un deuxieme outil arrivera pour de bon : tout
garder dans un seul exe — c'est ce que fait le decoupage actuel, et ca
simplifie la mise a jour — ou un exe par outil, avec une publication qui les
porte tous.
