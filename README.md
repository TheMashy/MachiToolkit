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

## Publier une nouvelle version

Le workflow `.github/workflows/release.yml` compile sous Windows et joint
l'exe a une publication GitHub. C'est cette publication que les exemplaires
deja installes viennent lire.

1. Faire ses modifications.
2. Monter `VERSION` dans `machi_tool.py` — c'est la seule source de
   verite pour le numero de version.
3. Commiter, puis poser le tag correspondant :

   ```bash
   git commit -am "ce qui a change"
   git tag v1.2.0
   git push origin main --tags
   ```

Le workflow verifie que le tag et `VERSION` disent la meme chose, compile,
calcule l'empreinte SHA-256 et cree la publication `v1.2.0` avec des notes
generees a partir des commits. Compter six a dix minutes. Les exemplaires
installes la proposeront a leur prochaine verification.

Sans tag, l'onglet **Actions > Publication > Run workflow** fait la meme
chose en prenant le numero directement dans le source.

Se tromper de numero est sans gravite : le workflow refuse un tag qui ne
concorde pas, plutot que de publier un exe qui se croirait plus ancien que
sa propre publication et se proposerait sa mise a jour en boucle.

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
