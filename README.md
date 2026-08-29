# MachiToolkit

Boite a outils personnelle pour piloter la workstation. Chaque outil est une
application Windows autonome, portable, qui vit dans la barre des taches et
se met a jour toute seule depuis les publications de ce depot.

Pour l'instant elle en contient un.

## Guirlande ambiante

Un brin d'ampoules Bluetooth (protocole HiLighting) dont la couleur suit ce
qui se passe a l'ecran.

| Mode | Ce qui pilote la couleur |
|---|---|
| Applications | une regle par programme ou par site : Netflix en rouge, GitHub en vert... |
| Ecran | la couleur dominante de l'ecran, luminance suivie |
| Son | ce qui sort des haut-parleurs : bande de frequences et brillance du spectre |
| Mixte | moitie regle, moitie ecran |

Une passerelle HTTP locale, fermee par defaut, permet en plus a une page web
de prendre la main sur les lumieres.

## Installation

1. Telecharger `GuirlandeAmbiante.exe` depuis la
   [derniere publication](https://github.com/TheMashy/MachiToolkit/releases/latest).
2. Double-cliquer.

L'exe est son propre installeur : il se copie dans
`%LOCALAPPDATA%\GuirlandeAmbiante`, s'ajoute au demarrage de Windows et se
lance. Son icone apparait pres de l'horloge.

Windows SmartScreen affichera un avertissement au premier lancement : l'exe
n'est pas signe, une signature de code coute quelques centaines d'euros par
an. « Informations complementaires » puis « Executer quand meme ».

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
2. Monter `VERSION` dans `guirlande_ambiante.py` — c'est la seule source de
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
python guirlande_ambiante.py --icone
pyinstaller --noconfirm --clean GuirlandeAmbiante.spec
```

Ou, sans rien connaitre a Python, double-cliquer `Compiler.bat` : il installe
Python si besoin, puis les dependances, puis compile. Les deux chemins
passent par `GuirlandeAmbiante.spec`, donc sortent le meme exe que la CI.

Le resultat est dans `dist\`, qui n'est pas versionne : un exe de 34 Mo par
version n'a rien a faire dans l'historique du depot.

## En mode script

```bash
python guirlande_ambiante.py               # lance sans installer
python guirlande_ambiante.py --version     # affiche le numero de version
python guirlande_ambiante.py --verifier-maj  # interroge GitHub, affiche le resultat
python guirlande_ambiante.py --icone       # regenere icone.ico
python guirlande_ambiante.py --lanceur     # ajoute au demarrage de Windows
python guirlande_ambiante.py --retirer     # retire du demarrage
```

Lance ainsi, la configuration reste a cote du script et l'installation
automatique ne se declenche pas.

## Ou vivent les fichiers

| Chemin | Contenu |
|---|---|
| `%LOCALAPPDATA%\GuirlandeAmbiante\GuirlandeAmbiante.exe` | l'application installee |
| `%LOCALAPPDATA%\GuirlandeAmbiante\config.json` | tous les reglages |
| `%LOCALAPPDATA%\GuirlandeAmbiante\journal.log` | le journal, a lire quand ca coince |
| `%LOCALAPPDATA%\GuirlandeAmbiante\maj\` | l'exe telecharge, efface au demarrage suivant |
| `%APPDATA%\...\Startup\guirlande_ambiante.vbs` | l'entree de demarrage Windows |

## Ajouter un outil au toolkit

Le mecanisme de mise a jour ne sait rien de la guirlande. Il tient dans la
section « Mises a jour depuis GitHub » de `guirlande_ambiante.py` et ne
depend que de trois choses :

- `DEPOT_GITHUB`, le depot a interroger ;
- `VERSION`, comparee au tag de la derniere publication ;
- un `.exe` joint a cette publication, retrouve par son extension et non par
  son nom — un futur outil peut donc s'appeler autrement.

Pour un deuxieme outil : reprendre cette section telle quelle, lui donner son
propre `.spec` et son propre job dans `release.yml`. Reste a trancher, le jour
ou il y en aura deux, si chacun garde sa publication ou si une seule les porte
tous les deux.
