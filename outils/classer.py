# -*- coding: utf-8 -*-
"""
POURQUOI 89 % DE CE QUE TU REGARDES N'EST CLASSE NULLE PART.

    python outils/classer.py

Cet outil ne change rien et n'envoie rien. Il lit `activite.jsonl`, sur CETTE
machine, il rejoue plusieurs facons de classer les memes titres, et il dit
laquelle couvre quoi. Les titres ne sortent pas d'ici -- c'est la meme regle
que pour le reste du produit, et un outil de diagnostic n'est pas une raison
de la desserrer.

---------------------------------------------------------------------------
CE QUE J'AI PU MESURER AVANT DE L'ECRIRE, ET CE QUE JE N'AI PAS PU.

Je n'avais AUCUN titre reel : l'export envoye etait une page d'erreur 502, et
la route d'export ne sert de toute facon que 4 des 21 tables -- `activite_jours`
n'en fait pas partie. Les seules chaines vraies dont je disposais sont les cinq
lisibles sur une capture d'ecran. Passees dans le classeur actuel :

    reddit - the heart of the internet   -> rien
    youtube                              -> rien
    #ecriture-de-sinj | pti' marchand…   -> rien
    wardogs                              -> rien
    adobe premiere pro 2023 - d:\…       -> creation

Quatre sur cinq. C'est trop peu pour conclure, et bien assez pour voir la
forme du probleme : ce ne sont pas des mots-cles qui manquent, c'est que ces
titres NE PARLENT DE RIEN. « reddit » n'est pas un sujet, c'est un endroit ;
« #ecriture-de-sinj » n'est pas un sujet, c'est une conversation. Une table de
mots-cles sur le CONTENU ne peut rien en faire, quelle que soit sa longueur.

D'ou cet outil plutot qu'une rallonge de mots-cles : la seule facon honnete de
choisir entre plusieurs facons de classer est de les mesurer sur TES titres,
et eux sont ici.

---------------------------------------------------------------------------
LES QUATRE FACONS, ET CE QU'ELLES ADMETTENT.

0. ACTUELLE — le sujet, par mots-cles. Ce qui tourne aujourd'hui.

1. LE GESTE — pas de quoi ca parlait, mais ce que tu faisais : lire, regarder,
   parler, chercher, faire, acheter, defiler. Tout onglet est l'un des sept, donc
   la couverture est haute par construction. Ce n'est PAS un meilleur classement
   du sujet : c'est une autre question, a laquelle on peut repondre.

2. L'ENDROIT, EN SECOND — on garde les sujets d'abord ; quand rien ne prend, on
   nomme la FAMILLE DU LIEU (forum, video, messagerie, recherche, boutique,
   outil) et on l'ecrit comme telle. « video » et « social » avaient ete retires
   parce que, dans la meme liste, ils raflaient ce que les familles precises
   n'avaient pas pris. En SECONDE passe, explicitement etiquetee « faute de
   mieux », ils ne peuvent plus voler de sujet a personne.

3. DEUX AXES — le geste ET le sujet, jamais l'un a la place de l'autre.
   « 40 min · regarder · guerre », « 90 min · defiler · — ». C'est le seul qui
   ne demande pas a une etiquette de faire deux metiers, et ma lecture du
   probleme est que c'est de la que vient le 89 %.

Ce fichier ne tranche pas. Il compte.
"""
import json
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)


# =========================================================================
#  LES TABLES DE L'APPLICATION, CHARGEES SANS LA DEMARRER
# =========================================================================
def _tables():
    """`theme_activite` et ses dependances, sans ouvrir de fenetre.

    Importer `machi_tool` lancerait tkinter, les fils, la surveillance. On
    extrait donc le bloc des tables et on l'execute seul : c'est le MEME code
    que celui qui tourne, pas une copie -- une copie divergerait, et le
    diagnostic mesurerait alors autre chose que l'application.
    """
    src = open(os.path.join(RACINE, "machi_tool.py"), encoding="utf-8").read()
    lignes = src.split("\n")
    debut = next(i for i, l in enumerate(lignes) if l.startswith("QUEUES_NAV"))
    fin = next(i for i, l in enumerate(lignes) if l.startswith("def sous_theme_activite"))
    # jusqu'a la fin de cette fonction : la premiere ligne suivante en colonne 0
    j = fin + 1
    while j < len(lignes) and (not lignes[j].strip() or lignes[j][0].isspace()
                               or lignes[j].startswith(('"""', "'''"))):
        j += 1
    ns = {"re": re}
    exec(compile("\n".join(lignes[debut:j]), "machi_tool.py(tables)", "exec"), ns)
    return ns


T = _tables()
theme_actuel = T["theme_activite"]
lieu_actuel = T.get("lieu_activite")
titre_onglet = T["_titre_onglet"]


# =========================================================================
#  1. LE GESTE
# =========================================================================
"""Ce que tu FAISAIS, pas de quoi ca parlait.

L'ordre compte comme partout : le premier qui correspond gagne, et les plus
precis sont en haut. « defiler » est le DERNIER a dessein -- c'est celui qui
attrape les coquilles, les titres qui ne sont qu'un nom de plateforme, et il
ne doit prendre que ce dont personne d'autre n'a voulu.

« defiler » n'est pas un reproche. C'est le nom du geste : une page d'accueil
ouverte sans sujet. L'appeler autrement serait mentir, l'appeler « perdu » ou
« inutile » serait juger -- et ce produit montre, il ne qualifie pas.
"""
GESTES = [
    ("parler",   ("discord", "whatsapp", "messenger", "telegram", "signal", "slack",
                  "teams", "messages prives", "dm ", "#", "conversation")),
    ("chercher", ("google search", " - recherche google", "recherche google",
                  "duckduckgo", "qwant", " - bing", "comment faire", "how to ",
                  "stack overflow", "stackoverflow")),
    ("faire",    ("github", "gitlab", "localhost", "figma", "notion", "google docs",
                  "google drive", "overleaf", "colab", "jupyter", "codepen",
                  "replit", "canva", "trello", "obsidian")),
    ("acheter",  ("amazon", "leboncoin", "aliexpress", "vinted", "cdiscount", "fnac",
                  "panier", "checkout", "commande", "livraison", "ebay", "etsy")),
    ("regarder", ("youtube", "twitch", "netflix", "prime video", "disney", "crunchyroll",
                  "dailymotion", "vimeo", "arte", "replay", "episode", "saison ",
                  " s0", " e0", "streaming", "film complet")),
    ("lire",     ("wikipedia", "wikipédia", "reddit", "medium", "substack", "hacker news",
                  " - forum", "thread", "commentaires", "comments", "article",
                  "documentation", "docs.", "wiki", "blog", "pdf")),
    # Ce qui reste et qui porte un nom de plateforme SANS sujet : une page
    # d'accueil, un fil, une appli ouverte. C'est un geste, et c'en est un seul.
    ("defiler",  ("x.com", "twitter", "instagram", "tiktok", "facebook", "snapchat",
                  "pinterest", "linkedin", "9gag", "imgur", "tumblr")),
]

"""LES COQUILLES : un titre qui n'est QUE le nom de l'endroit.

« reddit - the heart of the internet », « youtube », « x », « discord » : la
page d'accueil, avant d'avoir clique sur quoi que ce soit. Elles pesent lourd
et ne peuvent RIEN dire d'un sujet -- c'est la premiere chose que le classeur
actuel devrait admettre au lieu de les laisser tomber dans le silence.
"""
COQUILLES = {
    "reddit": "defiler", "reddit - the heart of the internet": "defiler",
    "youtube": "regarder", "x": "defiler", "twitter": "defiler",
    "discord": "parler", "facebook": "defiler", "instagram": "defiler",
    "tiktok": "defiler", "gmail": "lire", "google": "chercher",
    "nouvel onglet": "defiler", "new tab": "defiler", "accueil": "defiler",
}


def _plein(contexte):
    proc, _, titre = (contexte or "").strip().lower().partition("|")
    return " " + " ".join((titre_onglet(titre) + " " + proc.strip()).split()) + " "


def geste(contexte):
    """Le geste, ou None. None doit rester possible : un classeur qui ne rate
    jamais rien est un classeur qui range de force."""
    if not (contexte or "").strip():
        return None
    plein = _plein(contexte)
    nu = plein.strip()
    if nu in COQUILLES:
        return COQUILLES[nu]
    for nom, mots in GESTES:
        for mot in mots:
            if mot in plein:
                return nom
    return None


# =========================================================================
#  2. L'ENDROIT, EN SECOND
# =========================================================================
"""La FAMILLE du lieu, jamais a la place d'un sujet.

Elle ne se consulte que si aucun sujet n'a pris. C'est toute la difference
avec « video » et « social », qui vivaient dans la meme liste que « guerre » et
« science » et gagnaient par simple position. Ici, ils ne peuvent structurellement
pas voler un sujet : ils ne sont interroges qu'apres son echec.
"""
LIEUX = [
    ("messagerie", ("discord", "whatsapp", "messenger", "telegram", "signal", "slack", "teams")),
    ("forum",      ("reddit", "hacker news", "forum", "stack overflow", "stackoverflow",
                    "quora", "4chan", "jeuxvideo.com")),
    ("video",      ("youtube", "twitch", "netflix", "dailymotion", "vimeo", "prime video",
                    "crunchyroll", "disney", "arte")),
    ("reseau",     ("x.com", "twitter", "instagram", "tiktok", "facebook", "linkedin",
                    "snapchat", "pinterest", "tumblr")),
    ("recherche",  ("recherche google", "google search", "duckduckgo", "qwant", "bing")),
    ("boutique",   ("amazon", "leboncoin", "aliexpress", "vinted", "ebay", "etsy",
                    "cdiscount", "fnac")),
    ("outil",      ("github", "gitlab", "figma", "notion", "google docs", "google drive",
                    "localhost", "canva", "trello")),
    ("encyclo",    ("wikipedia", "wikipédia", "wiki", "documentation", "docs.")),
]


def lieu(contexte):
    """Le lieu tel que l'APPLICATION le calcule desormais.

    Ce fichier en portait sa propre copie, du temps ou la chose n'existait que
    comme proposition. Elle est dans `machi_tool.py` maintenant : une seconde
    table ici divergerait, et le diagnostic mesurerait autre chose que ce qui
    tourne. La copie reste en secours, pour une version de l'application qui
    n'a pas encore la fonction.
    """
    if lieu_actuel:
        return lieu_actuel(contexte)
    plein = _plein(contexte)
    for nom, mots in LIEUX:
        for mot in mots:
            if mot in plein:
                return nom
    return None


def theme_ou_lieu(contexte):
    """Le sujet d'abord ; le lieu seulement s'il n'y en a pas.

    Rend `(etiquette, sur_quoi)` — `sur_quoi` vaut « sujet » ou « lieu », et
    c'est ce mot qui doit arriver a l'ecran avec l'etiquette. Sans lui, « video »
    se lirait comme un sujet, et l'ecran raconterait qu'on sait de quoi ca
    parlait alors qu'on sait seulement ou c'etait.
    """
    t = theme_actuel(contexte)
    if t:
        return (t, "sujet")
    l = lieu(contexte)
    return (l, "lieu") if l else (None, None)


# =========================================================================
#  LA MESURE
# =========================================================================
def _digests(chemin):
    """Les journees enregistrees, une par ligne."""
    out = []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    return out


def _titres_avec_temps(digests, web_seul=True):
    """(titre, secondes) pour tout ce qui a ete garde, toutes journees confondues.

    LE NAVIGATEUR SEUL, PAR DEFAUT. Le « 89 % que rien ne classe » de l'ecran
    porte sur `temps_par_theme_web_s`, et le web se reconnait a une seule chose
    dans ce produit : `cat.startswith("web:")`. Compter les applications ici
    mesurerait autre chose que ce que l'ecran affiche -- Discord, Premiere et
    les jeux gonfleraient le denominateur sans jamais avoir eu vocation a etre
    classes par sujet web.

    On additionne par titre : le meme onglet revient d'un jour a l'autre, et ce
    qui nous interesse est le POIDS d'une facon de classer, pas le nombre de
    chaines distinctes. Une table qui range mille titres vus une seconde et
    laisse tomber celui de six heures n'a rien range.
    """
    poids = {}
    for d in digests:
        for cat, par_titre in (d.get("titres") or {}).items():
            if web_seul and not str(cat).startswith("web:"):
                continue
            for titre, sec in (par_titre or {}).items():
                if isinstance(sec, (int, float)) and sec > 0:
                    poids[str(titre)] = poids.get(str(titre), 0.0) + float(sec)
    return poids


def _pct(part, tout):
    return 0.0 if tout <= 0 else 100.0 * part / tout


def mesurer(poids):
    tout = sum(poids.values())
    schemas = {
        "0 · actuelle (sujet)": lambda c: theme_actuel(c),
        "1 · le geste":         lambda c: geste(c),
        "2 · sujet, sinon lieu": lambda c: theme_ou_lieu(c)[0],
    }
    lignes = []
    for nom, f in schemas.items():
        couvert = sum(s for t, s in poids.items() if f("chrome.exe|" + t))
        lignes.append((nom, _pct(couvert, tout)))

    # 3 · deux axes : on compte les deux colonnes separement, jamais additionnees.
    g = sum(s for t, s in poids.items() if geste("chrome.exe|" + t))
    su = sum(s for t, s in poids.items() if theme_actuel("chrome.exe|" + t))
    deux = sum(s for t, s in poids.items()
               if geste("chrome.exe|" + t) and theme_actuel("chrome.exe|" + t))
    return tout, lignes, (_pct(g, tout), _pct(su, tout), _pct(deux, tout))


def orphelins(poids, f, combien=25):
    """Ce qu'un schema laisse tomber, du plus lourd au plus leger.

    C'est la partie qui sert VRAIMENT : un pourcentage dit qu'il reste du
    travail, cette liste dit lequel. Elle ne sort pas de la machine.
    """
    restes = [(t, s) for t, s in poids.items() if not f("chrome.exe|" + t)]
    restes.sort(key=lambda x: -x[1])
    return restes[:combien]


def main():
    chemin = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            chemin = arg
    if not chemin:
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        for essai in (os.path.join(local, "MachiTool", "activite.jsonl"),
                      os.path.join(RACINE, "activite.jsonl")):
            if os.path.exists(essai):
                chemin = essai
                break
    if not chemin or not os.path.exists(chemin):
        print("Je ne trouve pas activite.jsonl.")
        print("Donne-moi son chemin :  python outils/classer.py C:\\...\\activite.jsonl")
        return 1

    digests = _digests(chemin)
    tout_court = "--tout" in sys.argv
    poids = _titres_avec_temps(digests, web_seul=not tout_court)
    if not poids and not tout_court:
        hors = _titres_avec_temps(digests, web_seul=False)
        if hors:
            print(f"{len(digests)} journees lues, des titres oui — mais AUCUN sur le web.")
            print("Tout est en application. Relance avec --tout pour les voir quand meme.")
            return 1
    if not poids:
        print(f"{len(digests)} journees lues, mais AUCUN titre garde.")
        print("Sans titre, aucun classement n'est possible — c'est le reglage")
        print("« garder le titre des onglets » qui decide, dans Reglages.")
        return 1

    tout, lignes, (pg, ps, pd) = mesurer(poids)
    h = int(tout // 3600)
    print()
    champ = "tout (web + applications)" if tout_court else "le navigateur seul"
    print(f"  {len(digests)} journees · {len(poids)} titres distincts · {h} h · {champ}")
    print("  " + "-" * 56)
    for nom, pct in lignes:
        barre = "#" * int(round(pct / 2.5))
        print(f"  {nom:24} {pct:5.1f} %  {barre}")
    print()
    print("  3 · deux axes — deux colonnes, jamais additionnees")
    print(f"      un geste connu      {pg:5.1f} %")
    print(f"      un sujet connu      {ps:5.1f} %")
    print(f"      les deux a la fois  {pd:5.1f} %")
    print()
    print("  CE QUE LE SUJET LAISSE TOMBER — le plus lourd d'abord")
    print("  (reste sur cette machine)")
    print("  " + "-" * 56)
    for titre, sec in orphelins(poids, theme_actuel):
        print(f"  {int(sec // 60):5d} min  {titre[:64]}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
