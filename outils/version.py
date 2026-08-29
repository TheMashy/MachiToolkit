"""Lit la version declaree dans guirlande_ambiante.py.

VERSION dans le source est la seule source de verite. Le workflow s'en sert
pour nommer la publication, et verifie qu'un tag pousse a la main dit bien
la meme chose : une publication v1.3.0 contenant un exe qui se croit en
1.2.0 se proposerait sa propre mise a jour en boucle.

    python outils/version.py            -> affiche 1.1.0
    python outils/version.py --verifier v1.1.0
"""

import io
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(RACINE, "guirlande_ambiante.py")


def version():
    texte = io.open(SOURCE, encoding="utf-8").read()
    trouve = re.search(r'^VERSION\s*=\s*"([^"]+)"', texte, re.M)
    if not trouve:
        sys.exit("VERSION introuvable dans %s" % SOURCE)
    return trouve.group(1)


def main():
    courante = version()
    if "--verifier" in sys.argv:
        attendue = sys.argv[sys.argv.index("--verifier") + 1].lstrip("vV")
        if attendue != courante:
            sys.exit(
                "Le tag dit %s mais VERSION dit %s.\n"
                "Corrige VERSION dans guirlande_ambiante.py, ou repose le tag."
                % (attendue, courante))
        print("tag et VERSION concordent : %s" % courante)
        return
    print(courante)


if __name__ == "__main__":
    main()
