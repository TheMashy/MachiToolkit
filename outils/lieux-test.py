# -*- coding: utf-8 -*-
"""
OU L'ON EST, QUAND LE TITRE NE DIT PAS DE QUOI IL PARLE.

    python outils/lieux-test.py

MESURE, PAS ARGUMENT. Onze titres reels -- les seuls dont on dispose, relus sur
deux captures d'ecran. Avant : NEUF n'etaient classes nulle part, ce qui colle au
« 95 % que rien ne classe » de l'ecran. Ces tests tiennent les trois formes qui
se reconnaissent SANS deviner, et disent lesquelles resteront dehors.

CE QUI NE SE REGLE PAS ICI, et il faut que ce soit ecrit quelque part : les noms
propres. « portal 2, but it's poorly translated », « wardogs », « the merchant's
ledger » sont des choses que cette personne fait, pas des sujets qu'une table
generique contiendra jamais. Il faudra les lui demander -- ou les apprendre de
ce qu'elle ecrit.
"""
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from classer import theme_actuel, lieu_actuel          # noqa: E402

passe = fail = 0


def verifie(ce_quon_attend, contexte, quoi):
    global passe, fail
    eu = (theme_actuel(contexte), lieu_actuel(contexte))
    ok = (eu[0] if quoi == "sujet" else eu[1]) == ce_quon_attend
    if ok:
        passe += 1
        print("  ok   %-11s %s" % (str(ce_quon_attend), contexte.split("|", 1)[-1][:52]))
    else:
        fail += 1
        print("  NON  attendu %-9s eu sujet=%s lieu=%s  ← %s"
              % (str(ce_quon_attend), eu[0], eu[1], contexte.split("|", 1)[-1][:46]))


print("\nUNE COQUILLE EST UN ENDROIT, PAS UN SUJET")
# Le titre est le nom de la plateforme et rien d'autre : une page d'accueil.
# Ils se lisent sur le titre NU -- `_plein` colle le nom du programme derriere,
# et « x » y devient « x chrome.exe », qui ne ressemble plus a une coquille.
verifie("forum",     "chrome.exe|reddit - the heart of the internet", "lieu")
verifie("video",     "chrome.exe|youtube", "lieu")
verifie("reseau",    "chrome.exe|x", "lieu")
verifie("recherche", "chrome.exe|google", "lieu")

print("\nUN SALON EST UNE CONVERSATION -- PAR LE NOM DU CLIENT")
# Ces deux-la passent par la table, sur « discord ». J'avais d'abord ecrit une
# regle sur le diese, en me disant qu'un client qu'on n'aurait pas nomme
# resterait reconnaissable. Ces deux fixtures ne l'ont jamais exercee : la table
# les prenait avant. Les deux lignes d'en dessous disent ce que cette regle
# faisait reellement, et pourquoi elle n'est plus la.
verifie("messagerie", "Discord.exe|#\U0001F3ACecriture-de-sinj\U0001F3AC | pti' marchand de sable", "lieu")
verifie("messagerie", "Discord.exe|\U0001F417 chier sur le sol \U0001F417 | pti' marvin", "lieu")

print("\nQUAND LE SITE SE NOMME LUI-MEME, IL A RAISON CONTRE LES MOTS-CLES")
# X met « / X » au bout de chacune de ses pages. Un message poste sur X qui parle
# de YouTube reste un message sur X. Tant que cette lecture passait APRES la
# table, celle-ci repondait « video » -- elle voyait le mot, pas l'endroit.
verifie("reseau", "chrome.exe|Marques Brownlee sur X : \u00ab youtube vient de casser \u00bb / X", "lieu")
verifie("reseau", "chrome.exe|Accueil / X", "lieu")

print("\nUN DIESE N'EST PAS UN SALON")
# GARDE-FOU. Une regle « un diese suffit » passait avant la table et lui volait :
# ces deux titres devenaient des messageries. Si l'un des deux redevient
# « messagerie », c'est qu'on l'a remise.
verifie("reseau", "chrome.exe|#skyrim - Recherche / X", "lieu")
verifie(None,     "chrome.exe|Bug #1203 - Mozilla Bugzilla", "lieu")

print("\nLE LIEU NE VOLE JAMAIS UN SUJET")
# Il n'est interroge qu'APRES l'echec du sujet -- c'est ce qui avait coule
# « video » et « social », places dans la meme liste que « guerre ».
verifie("guerre", "chrome.exe|Ukraine drone strike frontline - YouTube", "sujet")
verifie(None,     "chrome.exe|Ukraine drone strike frontline - YouTube", "lieu")
verifie("creation", "chrome.exe|how to rig a character in blender - YouTube", "sujet")
verifie(None,       "chrome.exe|how to rig a character in blender - YouTube", "lieu")

print("\nCE QUI RESTE DEHORS, ET QUI DOIT Y RESTER")
# Des noms propres. Les ranger d'office demanderait d'inventer, et une table de
# mots-cles qui invente est une autorite qu'on ne peut pas contredire.
for titre in ("portal 2, but it's poorly translated",
              "wardogs",
              "the merchant's ledger - skyrim market tracker"):
    verifie(None, "chrome.exe|" + titre, "sujet")
    verifie(None, "chrome.exe|" + titre, "lieu")

print("\nLE COMPTE, SUR LES ONZE VRAIS TITRES")
REELS = [
    "chrome.exe|portal 2, but it's poorly translated",
    "Adobe Premiere Pro.exe|adobe premiere pro 2023 - d:\\montage\\derush_to_05-01",
    "FL64.exe|fl studio 21",
    "Discord.exe|\U0001F417 chier sur le sol \U0001F417 | pti' marvin",
    "chrome.exe|the merchant's ledger - skyrim market tracker",
    "chrome.exe|reddit - the heart of the internet",
    "chrome.exe|youtube",
    "chrome.exe|wardogs",
    "Discord.exe|#\U0001F3ACecriture-de-sinj\U0001F3AC | pti' marchand de sable",
    "chrome.exe|x",
    "chrome.exe|google",
]
dehors = [c for c in REELS if not theme_actuel(c) and not lieu_actuel(c)]
if len(dehors) == 3:
    passe += 1
    print("  ok   3 sur 11 restent sans rien — c'etait 9")
else:
    fail += 1
    print("  NON  %d restent dehors, on en attendait 3 : %s"
          % (len(dehors), [c.split("|", 1)[-1][:28] for c in dehors]))

print("\n%d passes, %d echoues\n" % (passe, fail))
raise SystemExit(1 if fail else 0)
