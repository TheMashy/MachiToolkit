"""Lit la version declaree dans machi_tool.py.

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
SOURCE = os.path.join(RACINE, "machi_tool.py")


def version():
    texte = io.open(SOURCE, encoding="utf-8").read()
    trouve = re.search(r'^VERSION\s*=\s*"([^"]+)"', texte, re.M)
    if not trouve:
        sys.exit("VERSION introuvable dans %s" % SOURCE)
    return trouve.group(1)


def version_dev(numero_build):
    """Numero d'une version de developpement, publiee a chaque fusion.

    Le correctif est incremente : une pre-version se compare AVANT la
    version finale du meme numero, donc 1.6.0-dev.7 passerait pour plus
    ancienne que la 1.6.0 deja installee et ne serait jamais proposee.
    C'est de la 1.6.1 qu'elle annonce l'approche.
    """
    morceaux = version().split("-")[0].split(".")
    while len(morceaux) < 3:
        morceaux.append("0")
    majeur, mineur, correctif = (int(x or 0) for x in morceaux[:3])
    return "%d.%d.%d-dev.%s" % (majeur, mineur, correctif + 1, numero_build)


def poser(nouvelle):
    """Grave un numero dans le source, juste avant de compiler.

    Sans ca, un exe de developpement se croirait a la version stable dont
    il est issu, et se proposerait sa propre mise a jour en boucle. Rien
    n'est commite : seule la copie de travail du runner change.
    """
    texte = io.open(SOURCE, encoding="utf-8").read()
    remplace, combien = re.subn(r'^VERSION = "[^"]+"',
                                'VERSION = "%s"' % nouvelle, texte,
                                count=1, flags=re.M)
    if not combien:
        sys.exit("VERSION introuvable dans %s" % SOURCE)
    io.open(SOURCE, "w", encoding="utf-8").write(remplace)
    print(nouvelle)


def main():
    courante = version()
    if "--dev" in sys.argv:
        print(version_dev(sys.argv[sys.argv.index("--dev") + 1]))
        return
    if "--poser" in sys.argv:
        poser(sys.argv[sys.argv.index("--poser") + 1])
        return
    if "--verifier" in sys.argv:
        attendue = sys.argv[sys.argv.index("--verifier") + 1].lstrip("vV")
        if attendue != courante:
            sys.exit(
                "Le tag dit %s mais VERSION dit %s.\n"
                "Corrige VERSION dans machi_tool.py, ou repose le tag."
                % (attendue, courante))
        print("tag et VERSION concordent : %s" % courante)
        return
    print(courante)


if __name__ == "__main__":
    main()
