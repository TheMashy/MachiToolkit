"""
Machi Tool — boite a outils pour la workstation, logee dans la barre des
taches de Windows.

Un seul module pour l'instant, Lumiere : une guirlande Bluetooth dont la
couleur suit ce qui se passe a l'ecran. L'accueil porte un bouton par
module ; les suivants viendront s'y ajouter.

Compile en un seul .exe portable. Cet exe fait tout :
  - lance depuis n'importe ou    -> s'installe dans %LOCALAPPDATA%, se lance
  - relance depuis n'importe ou  -> met a jour la version installee
  - lance depuis l'installation  -> tourne normalement

Une fois installee, l'application surveille les publications du depot
GitHub et se met a jour seule : elle telecharge le nouvel exe et le lance,
qui reprend le premier cas ci-dessus. config.json n'est jamais touche.

Modes de couleur :
  applications  couleur par regle (programme ou site web)
  ecran         couleur dominante de l'ecran, luminance suivie
  mixte         moitie regle, moitie ecran
"""

import asyncio
import base64
import sys
import os
import atexit
import json
import re
import time
import math
import shutil
import secrets
import colorsys
import threading
import traceback
import subprocess
import http.server
import io
import socket
import struct
import wave
import concurrent.futures
import random
from collections import deque
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.57.0"

NOM_APP = "Machi Tool"          # ce que lit l'utilisateur
NOM_COURT = "MachiTool"         # dossiers et fichiers, sans espace ni accent
NOM_EXE = NOM_COURT + ".exe"

# L'application s'appelait GuirlandeAmbiante jusqu'a la 1.1. Une installation
# de cette epoque doit retrouver ses reglages sous le nouveau nom, sinon la
# mise a jour ressemble a une perte de configuration.
ANCIEN_NOM = "GuirlandeAmbiante"

# Depot d'ou viennent les mises a jour. Une seule ligne a changer si le
# projet demenage ou si une autre application du toolkit reprend ce module.
DEPOT_GITHUB = "TheMashy/MachiToolkit"

# Fige = lance depuis l'exe compile. Les donnees vont alors dans LOCALAPPDATA,
# pour qu'une mise a jour de l'exe n'efface jamais la configuration.
FIGE = getattr(sys, "frozen", False)

# Pose par la mise a jour automatique : l'exe telecharge s'installe alors
# sans afficher la moindre fenetre.
SILENCIEUX = "--maj-silencieuse" in sys.argv

_LOCAL = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))

if FIGE:
    DOSSIER = os.path.join(_LOCAL, NOM_COURT)
else:
    DOSSIER = os.path.dirname(os.path.abspath(__file__))

ANCIEN_DOSSIER = os.path.join(_LOCAL, ANCIEN_NOM)
ANCIEN_EXE = os.path.join(ANCIEN_DOSSIER, ANCIEN_NOM + ".exe")

try:
    os.makedirs(DOSSIER, exist_ok=True)
except Exception:
    pass

FICHIER_CONFIG = os.path.join(DOSSIER, "config.json")
FICHIER_JOURNAL = os.path.join(DOSSIER, "journal.log")
CIBLE_EXE = os.path.join(DOSSIER, NOM_EXE)
FICHIER_VERSION = os.path.join(DOSSIER, "version_installee.txt")

# Sans console, sys.stdout vaut None et le moindre print() leverait une
# exception. On redirige tout vers un fichier journal.
_JOURNAL = None
try:
    if sys.stdout is None or not hasattr(sys.stdout, "write"):
        # LA SEULE PLACE POSSIBLE POUR FAIRE TOURNER CE FICHIER : ICI.
        # faulthandler garde CE descripteur pour la vie du processus (plus
        # bas) ; le renommer ensuite enverrait la pile d'un plantage natif --
        # la seule chose qui puisse le nommer -- dans un fichier orphelin.
        # Une capture qui echouait en boucle y ecrivait 4 Mo par heure.
        try:
            if os.path.getsize(FICHIER_JOURNAL) > 2_000_000:
                os.replace(FICHIER_JOURNAL, FICHIER_JOURNAL + ".1")
        except OSError:
            pass
        _JOURNAL = open(FICHIER_JOURNAL, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = _JOURNAL
        print(f"\n--- demarrage {time.strftime('%Y-%m-%d %H:%M:%S')} v{VERSION} ---")
except Exception:
    pass

"""
TROIS FILETS POUR QU'UNE DISPARITION S'EXPLIQUE.

L'application peut s'arreter de trois facons, et deux d'entre elles ne
laissaient AUCUNE trace -- ce qui rend « ca a plante » impossible a
diagnostiquer, et impossible a distinguer d'un redemarrage voulu.

  1. UNE EXCEPTION DANS UN FIL. Elle ne tue pas le processus : elle tue le fil,
     en silence. Le pilote de la guirlande s'arrete alors sur sa derniere
     couleur, la fenetre continue de repondre, et rien nulle part ne dit qu'un
     morceau de l'application est mort. `threading.excepthook` l'ecrit.

  2. UN PLANTAGE NATIF. win32, PIL, la pile Bluetooth : une faute de segment
     dans une extension C tue le processus instantanement, sans exception
     Python, sans boite de dialogue, sans un mot. C'est exactement ce qu'on
     voit de l'exterieur -- la fenetre disparait. `faulthandler` ecrit la pile
     C au moment de la faute, et c'est la seule chose qui puisse la nommer.

  3. UN ARRET PROPRE. `atexit` pose une derniere ligne. Son ABSENCE est alors
     une information : le journal se termine sans elle exactement quand le
     processus a ete tue de l'exterieur.
"""
try:
    import faulthandler
    faulthandler.enable(file=_JOURNAL or sys.stderr, all_threads=True)
except Exception:
    pass


def _fil_a_saute(args):
    try:
        print("--- FIL MORT %s : %s dans %s ---"
              % (time.strftime("%Y-%m-%d %H:%M:%S"),
                 getattr(args.exc_type, "__name__", args.exc_type),
                 getattr(args.thread, "name", "?")))
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass


try:
    threading.excepthook = _fil_a_saute
except Exception:
    pass


def _derniere_ligne():
    try:
        print("--- fin %s v%s ---" % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION))
    except Exception:
        pass


# Seulement quand le journal existe : sa raison d'etre est qu'une derniere
# ligne MANQUE quand le processus a ete tue, et sans journal il n'y a rien
# ou la lire. En mode script, elle ne ferait que salir la console.
if _JOURNAL:
    try:
        atexit.register(_derniere_ligne)
    except Exception:
        pass

# ==========================================================================
#  Reglages par defaut
#  L'ordre des regles compte : la premiere qui correspond gagne.
#  Les sites sont donc places avant les navigateurs.
# ==========================================================================

CONFIG_DEFAUT = {
    "adresse": "",

    "mode": "applications",          # applications | ecran | mixte
    "ecran_source": "actif",         # "actif" ou numero d'ecran (1, 2, ...)
    "ecran_saturation": 1.5,
    "ecran_finesse": 4,              # colonnes de la vignette : 4 -> ~12 pixels
    "douceur_ecran": 0.35,

    # Ce que la luminance de l'ecran fait bouger, meme logique qu'en mode Son.
    "ecran_cible": "luminosite",     # luminosite | saturation | les_deux | rien
    "ecran_luminosite_base": 1.0,    # tenue quand l'ecran ne pilote pas l'eclat
    "ecran_luminance_min": 0.15,     # plancher de sortie : jamais tout a fait noir

    # Etalonnage de l'entree. Un ecran ne va jamais du noir absolu au blanc
    # pur : sans ces bornes, la guirlande n'utilise qu'une tranche etroite de
    # sa dynamique. Les valeurs par defaut reproduisent l'ancien calcul.
    "ecran_noir": 0.0,
    "ecran_blanc": 0.62,
    "ecran_gamma": 0.5,              # 0.5 = lineaire

    # La guirlande suit ce que l'oeil VOIT, pas ce que la carte graphique stocke.
    # f.lux (et les filtres qui ecrivent la rampe gamma : Redshift, SunsetScreen)
    # jaunissent l'ecran par cette rampe du GPU, APRES le tampon d'image que la
    # capture lit : sans compensation, l'ecran est jaune le soir et la guirlande
    # reste blanche. On relit la rampe et on l'applique a la couleur echantillonnee.
    # (Windows Night Light passe par un autre pipeline et n'est pas vu par cette
    # lecture.)
    "ecran_suit_filtre_bleu": True,
    # Etalonnage manuel de la balance, par-dessus. Deux axes, comme un boitier
    # photo : temperature (froid <-> chaud) et teinte (vert <-> magenta). 0 = neutre.
    "ecran_balance_temp": 0.0,       # -1 plus froid (bleu), +1 plus chaud (ambre)
    "ecran_balance_tint": 0.0,       # -1 plus vert, +1 plus magenta
    # Le blanc de la guirlande elle-meme. Une LED « blanche » n'est pas neutre :
    # la plupart tirent au bleu (7000-8500 K). Une couleur d'ecran envoyee telle
    # quelle y parait donc plus froide qu'a l'ecran -- meme quand f.lux est bien
    # lu. On lui donne son point blanc, et on corrige. 6500 = neutre.
    "led_blanc_kelvin": 7500,
    # De combien on pousse la compensation du filtre (1 = telle quelle). Une
    # guirlande de trente diodes vue de cote rend le chaud moins que l'ecran :
    # 1,3 est ce qui, a l'oeil, met les deux d'accord.
    "ecran_filtre_force": 1.3,

    "regles": [
        {"nom": "Netflix",    "couleur": "#E50914", "mots": ["netflix"]},
        {"nom": "YouTube",    "couleur": "#FF0033", "mots": ["youtube"]},
        {"nom": "Twitch",     "couleur": "#9146FF", "mots": ["twitch"]},
        {"nom": "GitHub",     "couleur": "#2DBA4E", "mots": ["github"]},
        {"nom": "Claude",     "couleur": "#D97757", "mots": ["claude.ai", "chatgpt"]},
        {"nom": "Messagerie", "couleur": "#EA4335", "mots": ["gmail", "outlook.", "proton mail"]},
        {"nom": "Docs",       "couleur": "#4285F4", "mots": ["google docs", "google sheets", "notion.so"]},
        {"nom": "Reseaux",    "couleur": "#1D9BF0", "mots": ["twitter", " / x", "reddit", "instagram", "linkedin"]},

        {"nom": "Code",       "couleur": "#2563EB", "mots": ["code.exe", "devenv.exe", "pycharm", "sublime_text"]},
        {"nom": "Terminal",   "couleur": "#0EA5E9", "mots": ["powershell", "cmd.exe", "wt.exe", "windowsterminal"]},
        {"nom": "Jeu",        "couleur": "#DC2626", "mots": ["steam", "epicgames", "battle.net", "riotclient"]},
        {"nom": "Video",      "couleur": "#7C3AED", "mots": ["vlc.exe", "mpc-hc", "potplayer"]},
        {"nom": "Musique",    "couleur": "#16A34A", "mots": ["spotify", "deezer", "foobar"]},
        {"nom": "Discussion", "couleur": "#6366F1", "mots": ["discord", "slack", "teams", "telegram"]},
        {"nom": "Creation",   "couleur": "#DB2777", "mots": ["photoshop", "figma", "blender", "davinci", "premiere"]},
        {"nom": "Bureau",     "couleur": "#F59E0B", "mots": ["excel", "winword", "powerpnt", "obsidian"]},
        {"nom": "Web",        "couleur": "#06B6D4", "mots": ["chrome.exe", "firefox.exe", "msedge.exe", "brave.exe"]},
    ],

    "couleur_defaut": "#8B5CF6",
    "veille_minutes": 6,
    "couleur_veille": "#3B1F0B",
    "veille_luminosite": 0.18,
    "reaction_processeur": True,
    "luminosite_min": 0.45,
    "luminosite_max": 1.00,
    "amplitude_respiration": 0.10,
    "periode_respiration": 11.0,
    "douceur": 0.06,
    "images_par_seconde": 8,

    # 0 = deduite de l'ecran. Une valeur forcee sert quand la detection se
    # trompe : ecran 4K declare a tort en 96 ppp, ou gout personnel.
    "echelle_interface": 0.0,

    # Sans ca, la guirlande reste allumee sur sa derniere couleur quand
    # Windows s'eteint : l'application est tuee avant d'avoir rien envoye.
    "eteindre_en_partant": True,

    "son_bande": "graves",           # graves | mediums | aigus | tout
    "son_palette": "chaud_froid",    # chaud_froid | arc | regle
    "son_sensibilite": 1.0,
    "son_plancher": 0.06,
    "son_attaque": 0.55,             # montee : eleve = coup sec
    "son_chute": 0.12,               # descente : bas = trainee douce

    # Ce que le son fait bouger. Ce qu'il ne pilote pas garde sa valeur
    # fixe : saturer en permanence et ne laisser respirer que la
    # luminosite donne une couleur franche, la ou tout piloter delave les
    # passages calmes en blanc.
    "son_cible": "luminosite",       # luminosite | saturation | les_deux
    "son_saturation_fixe": 0.92,
    "son_luminosite_fixe": 1.0,

    # Passerelle HTTP locale : permet a un site web de piloter la guirlande.
    # Fermee par defaut — sans jeton ni liste d'origines, n'importe quelle page
    # ouverte dans le navigateur pourrait allumer les lumieres du salon.
    "api_active": True,              # 127.0.0.1 seulement, cle exigee : le site synchronise sans attendre
    "api_port": 7373,
    "api_jeton": "",
    "api_origines": ["https://braindebugger-production.up.railway.app",
                     "http://localhost:3000"],

    # Pont avec BrainDebugger. Le site tourne sur Internet et l'application
    # ecoute en local : c'est le navigateur, sur cette machine, qui fait le
    # lien. Onglet ouvert, le site pousse directement. Onglet ferme, plus
    # personne ne peut joindre l'application depuis l'exterieur — c'est
    # alors elle qui va demander au site s'il a quelque chose a dire.
    "pont_site": "https://braindebugger-production.up.railway.app",
    # Le raccourci de demarrage se REPARE tout seul. Une entree effacee (un
    # nettoyeur, une reinstallation de Windows, un profil recree) ne se voit
    # pas : l'application ne se relance simplement plus jamais, et le journal
    # s'arrete sans un mot. On retient donc le choix ici, et on repose le
    # raccourci a chaque lancement quand il manque ou pointe ailleurs.
    "demarrage_auto": True,
    "pont_releve": True,             # aller chercher les rappels en attente
    "pont_intervalle": 3,            # minutes entre deux releves (une demande deposee sur le site attend au plus ca)
    "pont_cle": "",                  # cle transmise au site, s'il en veut une
    "pont_notifie": True,            # afficher les rappels recus

    # Interrupteur maitre : BrainDebugger a-t-il le droit de piloter la
    # guirlande ? Il couvre TOUT ce que le site peut faire a la lumiere -- la
    # couleur qu'il force (/couleur, /humeur) et la couleur de presence. Coche
    # par defaut. Decoche, le site n'a plus aucune prise : un forcage en cours
    # est relache aussitot et la guirlande revient au mode normal.
    "pont_affecte_leds": True,

    # Bascule pendant qu'on est sur le site. Deux facons de s'en rendre
    # compte, cumulees : le titre de la fenetre active, qui ne demande rien
    # au site, et un battement que le site peut envoyer — le seul a marcher
    # quand l'onglet est ouvert mais qu'on regarde ailleurs.
    "pont_presence": True,
    "pont_presence_indice": "braindebugger",
    "pont_presence_couleur": "#7C3AED",
    "pont_presence_suit_humeur": True,   # prefere la couleur d'humeur recue
    "pont_presence_grace": 20,           # secondes gardees apres la sortie

    # Journal d'activite facon ActivityWatch : temps par app/site, bascules,
    # plages actives. Aucun contenu, aucun clavier. Faux par defaut.
    "collecte_active": False,
    "collecte_titres_complets": True,    # garder le titre des onglets (voir migration v4)
    "collecte_envoi": False,             # pousser le digest au site
    "collecte_intervalle_heures": 6,

    # Jarvis : « Jarvis, ... » et il ecoute. ETEINT PAR DEFAUT : c'est un micro
    # ouvert en permanence, ca se decide, ca ne s'impose pas. Voir la section
    # JARVIS plus bas pour ce qui sort (rien avant le mot d'eveil) et ce qui
    # reste (tout, sauf ce qui est pour le compagnon).
    "jarvis_actif": False,
    "jarvis_sensibilite": 0.5,        # 0 strict .. 1 permissif (le mot appris)
    "jarvis_hey": True,               # « Hey Jarvis », le modele anglais d'openWakeWord
    "jarvis_auto_etalonnage": True,   # garder seul les facons de l'appeler qu'il ratait de peu
    "jarvis_tolerant": True,          # un « Jarvis » pas net : verifie par transcription (voir TOLERANCE_FACTEUR)
    "jarvis_son": True,               # le petit son quand il s'allume
    "jarvis_leds": True,              # la guirlande dit ou il en est
    "jarvis_voix": True,              # il repond a voix haute
    "jarvis_voix_modele": "fr_FR-tom-medium",   # la voix FRANCAISE (Piper) : le mode psy, ou "windows"
    # « And in English as well » : Jarvis repond en anglais, avec Kokoro -- une
    # voix d'homme britannique, pas celle d'un acteur. Le mode psy reste en
    # francais, avec la voix du dessus. "fr" remet Jarvis en francais.
    "jarvis_langue": "en",
    "jarvis_micro": "",
    # SES MAINS SUR LE PC (dossiers, fichiers, Spotify) et SES YEUX (un ecran,
    # sur demande) : fermes tant qu'on ne les ouvre pas, et derriere un code
    # d'acces dit a voix haute. Du code, on ne garde qu'une empreinte.
    "jarvis_pc": False,
    "jarvis_ecran": False,
    # « Faire en sorte qu'il n'y ait plus de code d'acces a demander » : il agit
    # directement. Le code reste possible, si on coche la case qui le demande.
    "jarvis_code_actif": False,
    # CE QU'IL RETIENT DE TOI : des phrases courtes, dictees (« retiens que... »),
    # envoyees avec chaque question. Reglages > Jarvis les montre et les efface.
    "jarvis_preferences": [],
    # SES SOUVENIRS DE VOS CONVERSATIONS : une phrase par conversation en mode
    # Jarvis, ecrite a la fin de celle-ci. Jamais le mode psychologue.
    "jarvis_souvenirs": [],
    # L'HISTORIQUE DU NAVIGATEUR, pour retrouver une video ou un lien : lu sur
    # le poste a la demande ; seules les pages qui correspondent partent.
    "jarvis_historique": False,
    # SPOTIFY, par l'API officielle : le Client ID d'une app developpeur de la
    # personne, et le jeton de renouvellement que Spotify donne a la connexion.
    "spotify_client_id": "",
    # LES ONGLETS DE CHROME : la cle de l'extension de Machi Tool (a part du
    # jeton du serveur local : elle ne sert qu'aux onglets).
    "onglets_cle": "",
    # LA BOULE DE JARVIS a l'ecran quand il est reveille ; sa place en
    # fractions de l'ecran principal (la meme a toutes les resolutions).
    "jarvis_boule": True,
    # LE PANNEAU DE JARVIS : le contenu « Jarvis » du panneau LED 64 x 64, en
    # haut au milieu de l'ecran quand il est actif. Avec lui, la boule ne sort
    # plus que pour aller sur l'ecran qu'il regarde.
    "jarvis_panneau": True,
    "jarvis_boule_x": 0.97,
    "jarvis_boule_y": 0.90,
    "spotify_refresh": "",
    "jarvis_code_sel": "",
    "jarvis_code_empreinte": "",               # l'identifiant Windows du micro ; vide = celui de Windows
    "jarvis_voix_kokoro": "jarvis",   # sa voix anglaise, voir VOIX_KOKORO dans jarvis.py
    "jarvis_voix_fr": "fr_jarvis",    # sa voix francaise : VOIX_KOKORO_FR, ou "piper" (jarvis_voix_modele)
    "jarvis_astuce_voix": False,      # il a deja dit comment l'appeler par « Jarvis » tout seul
    "jarvis_lenteur": 0.95,           # > 1 plus pose, < 1 plus vif (Piper et Kokoro)
    "jarvis_appellation": "",         # comment Jarvis vous appelle ; vide = ni Monsieur ni Madame
    "jarvis_debit": 0,                # voix de Windows : -10 .. 10
    "jarvis_suite": True,             # apres sa reponse, il ecoute encore 5 s sans mot d'eveil
    # « Une discussion a double transmission, comme ChatGPT, pour pouvoir
    # couper la parole » : on parle par-dessus, il se tait et ecoute -- et si
    # personne ne parlait (un clavier, une porte), il reprend sa phrase.
    "jarvis_couper": True,
    # Raccourcis a soi : [{"dit": "ouvre spotify", "ouvre": "spotify:"}] -- une
    # phrase, et ce qu'elle ouvre (programme, dossier ou adresse).
    "jarvis_raccourcis": [],
    "jarvis_couleurs": {},            # {"pense": "#FF00AA"} pour changer une couleur d'etat
    # SES ROUTINES DE LUMIERE : des habitudes et des running gags qu'il pose
    # lui-meme (voir routine_propre dans jarvis.py) -- un declencheur, une
    # petite animation, une replique.
    "routines_lumiere": [],

    # Mises a jour depuis les publications GitHub du depot.
    "config_version": 5,              # sert aux migrations, voir charger_config
    "derniere_version": "",           # la version du dernier demarrage : dit au
                                      # retour qu'une mise a jour est passee, et
                                      # qu'il ne s'agissait pas d'un plantage
    "maj_verifier": True,             # regarder si une version plus recente existe
    "maj_installation_auto": True,    # poser la mise a jour sans rien demander
    # Chaque fusion sur main sort une pre-version : la refuser reviendrait
    # a ne rien voir passer entre deux versions stables.
    "maj_prereleases": True,
    "maj_intervalle_heures": 1,       # delai entre deux verifications
}

# ==========================================================================
#  Protocole HiLighting (port serie BLE, service Nordic UART)
#  Une seule couleur pour tout le brin : le controleur n'a aucune commande
#  d'adressage par segment.
# ==========================================================================

UUID_ECRITURE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TRAME_ON  = bytearray([0x55, 0x01, 0x02, 0x01])
TRAME_OFF = bytearray([0x55, 0x01, 0x02, 0x00])
def trame_rgb(r, g, b): return bytearray([0x55, 0x07, 0x01, r, g, b])
def trame_lum(n):       return bytearray([0x55, 0x03, 0x01, 0xFF, n])

# ==========================================================================

ETAT = {
    "connecte": False,
    "message": "Demarrage...",
    "couleur": (0, 0, 0),
    "regle": "-",
    "contexte": "",
    "pause": False,
    "en_marche": True,
    "demande": None,
    "adresse_test": "",
    "appareils": [],
    "occupe": False,
    "resultat": "",
    "ecrans": 0,
    "ecran_luminance": 0.0,   # ce que l'ecran renvoie, avant etalonnage
    "ecran_gain": 0.0,        # luminosite finalement envoyee
    "ecran_sat": 0.0,         # saturation finalement envoyee
    "forcage": None,     # {"couleur", "nom", "expire"}
    "api": "arretee",
    # Echecs de connexion Bluetooth d'affilee. Sert a espacer les tentatives :
    # une guirlande qui tombe aussitot connectee clignote toutes les dix
    # secondes, et martele la pile Bluetooth pour rien.
    "echecs_ble": 0,
    # Etat de la capture d'ecran. Sans lui, une capture qui echoue n'a nulle
    # part ou se dire : le panneau montrait « Connectee » -- le message du
    # Bluetooth -- pendant que l'ecran n'etait plus lu du tout.
    "ecran": {"echecs": 0, "suspendue": False, "reprise": 0.0, "depuis": 0.0},
    "rappel_neuf": False,
    "presence": None,      # battement envoye par le site
    "presence_vu": 0.0,    # jusqu'a quand la presence reste acquise
}

# Ce que le site a envoye. Rien n'est invente ici : tant que BrainDebugger
# ne pousse rien, ces listes restent vides et les pages le disent.
PONT = {
    "etat": "inactif",        # inactif | releve | ok | erreur
    "message": "Aucun echange avec le site pour l'instant.",
    "vu_le": 0.0,
    "humeur": None,           # {"valeur", "libelle", "couleur", "date"}
    "jours": [],              # [{"date", "note", "humeur", "couleur"}]
    "reperes": [],            # [{"date", "titre", "couleur"}]
    "rappels": [],            # [{"id", "titre", "texte", "recu"}]
}

CFG = {}

ACCENT_DEPART = "#F2C94C"   # accent au repos, avant la premiere couleur


"""
CE QUE LA GUIRLANDE MONTRE, ET CE QUE L'ECRAN DOIT AFFICHER POUR LE DIRE.

Le panneau peignait la couleur ENVOYEE telle quelle -- et paraissait beaucoup
plus sombre que la guirlande. Les deux ne parlent pas la meme langue :

  - une LED emet une lumiere PROPORTIONNELLE a la valeur recue (modulation de
    largeur d'impulsion) : 24 sur 255, c'est 9 % de sa lumiere ;
  - un ecran, lui, applique une courbe (sRVB) : la valeur 24 n'y donne que
    0,9 % de sa lumiere -- dix fois moins.

Pour montrer a l'ecran ce que la LED emet, il faut donc ENCODER la valeur
envoyee comme une lumiere lineaire : 24 devient 87. C'est le seul calcul juste ;
tout le reste (halos, melanges au fond) ne faisait qu'assombrir encore.
"""


def vu_a_l_oeil(rgb):
    """La couleur a peindre a l'ecran pour montrer ce que la LED emet."""
    def canal(c):
        x = max(0.0, min(1.0, float(c) / 255.0))
        v = 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
        return int(round(v * 255))
    return tuple(canal(c) for c in rgb)


def eclat(rgb):
    """L'intensite percue de ce que la LED emet, de 0 a 1 : la luminance de sa
    lumiere (lineaire), encodee comme l'oeil la sent."""
    r, v, b = (max(0.0, min(1.0, float(c) / 255.0)) for c in rgb)
    y = 0.2126 * r + 0.7152 * v + 0.0722 * b
    return 12.92 * y if y <= 0.0031308 else 1.055 * y ** (1 / 2.4) - 0.055


"""
LES IMAGES REELLEMENT ENVOYEES, A LA CADENCE DE LA GUIRLANDE.

La bande d'historique du panneau prenait une mesure toutes les 400 ms, quelle
que soit la cadence reglee : a 30 images par seconde, elle en montrait moins
d'une sur dix. La boucle Bluetooth note maintenant CHAQUE image qu'elle fixe,
avec son instant ; le graphe du panneau les dessine une par une, et dit la
cadence reellement tenue a cote de celle qui est reglee.
"""

IMAGES_LED = deque(maxlen=2400)      # (numero, instant, (r, v, b))
_IMAGES_N = [0]


def noter_image_led(rgb, instant=None):
    _IMAGES_N[0] += 1
    IMAGES_LED.append((_IMAGES_N[0], time.time() if instant is None else instant,
                       tuple(int(c) for c in rgb)))


def images_depuis(numero):
    """Les images posterieures a `numero`, dans l'ordre."""
    nouvelles = []
    for im in reversed(IMAGES_LED):
        if im[0] <= numero:
            break
        nouvelles.append(im)
    nouvelles.reverse()
    return nouvelles


def cadence_reelle(fenetre=2.0, maintenant=None):
    """Images par seconde reellement fixees sur les `fenetre` dernieres
    secondes. 0 si la guirlande ne recoit plus rien."""
    t = time.time() if maintenant is None else maintenant
    n, premier = 0, None
    for _, instant, _ in reversed(IMAGES_LED):
        if t - instant > fenetre:
            break
        n += 1
        premier = instant
    if n < 2 or premier is None:
        return 0.0
    duree = max(1e-6, t - premier)
    return (n - 1) / duree if duree < fenetre * 1.01 else n / fenetre


def entier(valeur, defaut):
    """Un nombre lu dans un fichier ecrit par quelqu'un d'autre.

    `int(cfg.get(...))` levait sur null, sur "" et sur "trois" — et ces
    conversions sont dans le chemin de demarrage, hors de tout filet : une
    seule valeur de travers dans config.json (une ecriture interrompue, une
    modification a la main, un reglage venu d'une version future) tuait
    l'application avant meme son icone, sans un mot.
    """
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def charger_config():
    cfg = json.loads(json.dumps(CONFIG_DEFAUT))
    enregistre = {}
    if os.path.exists(FICHIER_CONFIG):
        try:
            with open(FICHIER_CONFIG, encoding="utf-8") as f:
                enregistre = json.load(f)
            if not isinstance(enregistre, dict):
                raise ValueError("le fichier ne contient pas un objet")
            cfg.update(enregistre)
        except Exception as e:
            # On repart des valeurs par defaut plutot que de refuser de
            # demarrer : une application qui s'ouvre avec ses reglages d'usine
            # se repare en trois clics, une qui ne s'ouvre pas ne se repare pas.
            enregistre = {}
            print("config.json illisible, reglages par defaut :", e)

    # ecran_suit_luminance a ete remplace par ecran_cible en 1.3. Une case
    # decochee doit le rester apres la mise a jour. La question se pose sur
    # ce qui est ecrit dans le fichier, pas sur cfg : les valeurs par defaut
    # y sont deja, ecran_cible y serait donc toujours present.
    if "ecran_cible" not in enregistre and \
            enregistre.get("ecran_suit_luminance") is False:
        cfg["ecran_cible"] = "rien"
    cfg.pop("ecran_suit_luminance", None)

    # Version 2 : les pre-versions deviennent le canal normal, puisque
    # chaque fusion en produit une. Une configuration ecrite avant ce
    # changement porte un « non » qui ne repondait pas a la meme question ;
    # on la fait passer une fois, sans y revenir ensuite.
    if enregistre and entier(enregistre.get("config_version", 1), 1) < 2:
        cfg["maj_prereleases"] = True
        cfg["maj_intervalle_heures"] = min(
            entier(cfg.get("maj_intervalle_heures", 1), 1), 2)
        print("Configuration migree : les nouveaux builds seront proposes.")
    # Version 3 : l'application se tient a jour SEULE. C'est ce que promet le
    # message d'installation, et c'est la seule issue quand l'icone a disparu
    # de la barre -- sans elle, personne ne peut cliquer « Installer ». Elle
    # releve le site toutes les trois minutes plutot que dix (une demande de
    # synchro deposee depuis le site attendait jusqu'a dix minutes), et tient
    # son serveur local (127.0.0.1, cle exigee) pour que « synchroniser »
    # depuis ce poste soit immediat. Une fois, sans y revenir ensuite.
    if enregistre and entier(enregistre.get("config_version", 1), 1) < 3:
        cfg["maj_installation_auto"] = True
        if entier(cfg.get("pont_intervalle", 3), 3) >= 10:
            cfg["pont_intervalle"] = 3
        cfg["api_active"] = True
        print("Configuration migree (v3) : mise a jour automatique, releve "
              "toutes les 3 min, serveur local allume.")
    # Version 4 : LE TITRE DES ONGLETS EST GARDE, ET C'EST UN CHOIX ASSUME.
    #
    # Jusqu'ici ce reglage etait eteint par defaut, et la regle du fichier etait
    # « on garde OU on etait, jamais QUOI » : le site ne recevait que « youtube,
    # 249 min ». Depuis que chaque instant est aussi range par SUJET, ce silence
    # coute plus qu'il ne protege — un camembert qui annonce « 40 min de guerre »
    # sans pouvoir montrer sur quoi il se fonde est une autorite qu'on ne peut
    # pas contredire, et une table de mots-cles se trompe forcement quelque part.
    #
    # Ce qui part au site, desormais : les DIX titres les plus longs par sujet,
    # au-dela de trente secondes chacun. Ce qui ne part toujours pas : l'adresse
    # visitee, le contenu de la page, ce qui est tape au clavier. Et la case
    # reste dans les reglages — c'est le sens d'un reglage qu'on puisse le
    # rendre a zero.
    if enregistre and entier(enregistre.get("config_version", 1), 1) < 4:
        cfg["collecte_titres_complets"] = True
        print("Configuration migree (v4) : les titres d'onglets sont gardes, "
              "pour que les sujets soient verifiables. Reglages > Site web pour "
              "revenir en arriere.")
    # Version 5 : la voix de Jarvis parle plus vite. L'ancien reglage (1,08)
    # avait ete ecrit dans le fichier par n'importe quel enregistrement : on ne
    # le change que s'il vaut encore exactement ca.
    if enregistre and entier(enregistre.get("config_version", 1), 1) < 5:
        try:
            if abs(float(cfg.get("jarvis_lenteur", 0.95)) - 1.08) < 1e-6:
                cfg["jarvis_lenteur"] = 0.95
        except (TypeError, ValueError):
            cfg["jarvis_lenteur"] = 0.95
    cfg["config_version"] = 5
    """
    ET ON SE SOUVIENT DE LA VERSION QU'ON ETAIT LA FOIS D'AVANT.

    L'application se met a jour seule : elle disparait, se remplace, revient.
    Vue de l'exterieur, cette disparition ressemble a un plantage -- et rien,
    au retour, ne disait qu'il ne s'en etait pas produit un. Une ligne suffit a
    lever le doute, et elle se lit au premier coup d'oeil sur le panneau.
    """
    vue = str(enregistre.get("derniere_version", "") or "")
    cfg["derniere_version"] = VERSION
    if vue and vue != VERSION:
        MAJ["etat"] = "a_jour"
        MAJ["message"] = "Mise a jour posee : %s vers %s." % (vue, VERSION)
        print("Mise a jour posee : %s vers %s." % (vue, VERSION))
    return cfg


def sauver_config(cfg):
    """Ecrit config.json. Renvoie faux si ca n'a pas pu se faire.

    NE LEVE PLUS. Un fichier verrouille par une synchronisation cloud, un
    dossier passe en lecture seule, un disque plein : l'ecriture echoue, et
    elle echouait EN LEVANT. L'appel le plus precoce vient de `jeton_courant`,
    dans le demarrage du serveur local — allume chez tout le monde depuis la
    1.20 — donc avant meme que l'icone existe. L'application mourait sans
    fenetre, sans icone et sans un mot : « ca plante quand je l'ouvre ».

    Ne pas garder un reglage est ennuyeux ; ne pas demarrer est fatal. On ecrit
    d'abord a cote puis on remplace, pour ne pas laisser un fichier a moitie
    ecrit derriere une coupure — c'est ce fichier-la qu'on relit au demarrage
    suivant.
    """
    propre = {k: v for k, v in cfg.items() if not k.startswith("_")}
    provisoire = FICHIER_CONFIG + ".part"
    try:
        with open(provisoire, "w", encoding="utf-8") as f:
            json.dump(propre, f, indent=2, ensure_ascii=False)
        os.replace(provisoire, FICHIER_CONFIG)
        return True
    except Exception as e:
        print("config.json non enregistre :", e)
        try:
            if os.path.exists(provisoire):
                os.remove(provisoire)
        except Exception:
            pass
        return False


def hex_vers_rgb(h):
    h = str(h).lstrip("#")
    if len(h) != 6:
        return (139, 92, 246)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (139, 92, 246)


def rgb_vers_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, int(c))):02X}" for c in rgb)


def _chemin_du_processus(pid):
    """Le chemin complet de l'executable d'un PID (meme derriere un anti-triche,
    comme _nom_du_processus), ou ""."""
    try:
        import psutil
        return psutil.Process(pid).exe()
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(32768)
            n = wintypes.DWORD(len(buf))
            k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return buf.value
        finally:
            k.CloseHandle(h)
    except Exception:
        pass
    return ""


def _nom_du_processus(pid):
    """Le nom de l'executable d'un PID, meme quand psutil se heurte a un mur.

    Beaucoup de jeux -- ceux de Steam en tete -- tournent avec un anti-triche
    ou des droits eleves : psutil.Process(pid).name() leve alors AccessDenied,
    et le jeu passait pour du temps 'inconnu'. On retombe sur l'API Win32
    QueryFullProcessImageName, qui ne demande que PROCESS_QUERY_LIMITED_INFORMATION
    et repond a travers les niveaux d'integrite -- exactement le cas d'un jeu.
    """
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(32768)
            n = wintypes.DWORD(len(buf))
            k.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD,
                wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return os.path.basename(buf.value)
        finally:
            k.CloseHandle(h)
    except Exception:
        pass
    return ""


def fenetre_active():
    """'processus.exe | titre', en minuscules. Le titre d'un navigateur
    contient le nom du site, ce qui suffit a distinguer Netflix de GitHub
    sans avoir a lire la barre d'adresse."""
    try:
        import win32gui, win32process
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ""
        titre = win32gui.GetWindowText(hwnd) or ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        nom = _nom_du_processus(pid)
        return f"{nom} | {titre}".lower()
    except Exception:
        return ""


def rectangle_fenetre_active():
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowRect(hwnd) if hwnd else None
    except Exception:
        return None


def secondes_inactivite():
    try:
        import win32api
        return (win32api.GetTickCount() - win32api.GetLastInputInfo()) / 1000.0
    except Exception:
        return 0.0


# ==========================================================================
#  Journal d'activite  (facon ActivityWatch)
#
#  Ce que fait ce module : mesurer le temps passe par application et par
#  site, compter les bascules entre fenetres, et suivre les plages d'activite
#  de la journee. Tout repose sur ce que l'application lit deja a chaque
#  image pour piloter la lumiere — la fenetre au premier plan et le temps
#  depuis la derniere frappe. Aucun hook clavier, aucune touche interceptee.
#
#  Ce que ce module ne fait PAS, et ne fera pas ici : lire ce qui est tape.
#  Le texte des messages — les tiens, ceux des autres, les mots de passe —
#  n'est jamais vu. Comme ActivityWatch, on note l'enveloppe de l'activite,
#  pas son contenu. Le rythme d'ecriture se mesure ailleurs, dans le site
#  lui-meme, sur les seuls champs ou c'est toi qui ecris.
#
#  Rien ne se collecte tant qu'on ne l'a pas demande ; rien ne quitte la
#  machine tant que l'envoi n'est pas coche et la cle du site renseignee.
# ==========================================================================

FICHIER_ACTIVITE = os.path.join(DOSSIER, "activite.jsonl")

ACTIVITE = {
    "active": False,
    "jour": "",
    "contexte": "",       # categorie de la fenetre courante
    "titre_courant": "",   # titre brut, garde seulement si l'option est cochee
    "depuis": 0.0,
    "temps": {},          # categorie -> secondes cumulees
    "titres": {},         # categorie -> {titre: secondes}, si titres complets
    "bascules": 0,
    "actif_s": 0.0,       # secondes reellement actives (hors inactivite)
    "themes": {},         # secondes par thematique, tout confondu
    "themes_web": {},     # secondes par thematique, NAVIGATEUR seulement
    "titres_theme": {},   # thematique -> {titre: secondes}, si titres complets
    "sous_themes_web": {},  # thematique -> {sous-categorie: secondes}, NAVIGATEUR seulement
    "lieux_web": {},      # secondes par LIEU, quand le sujet n'a rien su dire
    "sites_seuls": {},    # secondes par SITE, quand meme le lieu n'a rien su dire
    "titres_lieu": {},    # lieu -> {titre: secondes}, si titres complets
    "theme_courant": None,
    "sous_courant": None,
    "lieu_courant": None,
    "web_courant": False,
    "premiere": "",       # premiere activite de la journee (HH:MM)
    "derniere": "",
    "trous": [],          # absences > SEUIL_TROU pendant la journee
    "trou_depuis": 0.0,   # debut de l'absence en cours, 0 = present
    "reprise": False,     # journee reprise (relance, minuit) et personne encore vu au clavier
    "message": "arretee",
}

MOTEUR_ACTIVITE = {"marche": False}
SYNC = {"dernier": 0.0, "reussi": 0.0,   # derniere synchro poussee ; dernier envoi reussi
        "poste_envoye": None,            # json du `poste` parti en dernier : on renvoie quand il change
        "tout_a_pousser": False}         # l'historique entier au prochain envoi (migration)
TRAY = {"icone": None, "reposer": False}  # l'icone de la barre, reposee si elle disparait

# Le mot laisse par une seconde instance lancee via machitool://sync pendant
# que la premiere tourne : le mutex la renvoie aussitot, et sans ce fichier la
# demande du site tombait dans le vide. La premiere le lit toutes les cinq
# secondes (voir veille_activite).
FICHIER_DEMANDE = os.path.join(DOSSIER, "synchro_demandee")

# Le meme mecanisme pour « montre-toi » : un exe telecharge qu'on double-clique
# alors que l'application tourne deja se fait renvoyer par le mutex, et l'ecran
# ne bouge pas. Il laisse donc un mot avant de partir.
FICHIER_PANNEAU = os.path.join(DOSSIER, "panneau_demande")


def deposer_demande_synchro(origine="site"):
    try:
        with open(FICHIER_DEMANDE, "w", encoding="utf-8") as f:
            f.write("%s %s" % (origine, time.strftime("%Y-%m-%d %H:%M:%S")))
    except Exception as e:
        print("Demande de synchro non deposee :", e)


def demander_panneau():
    try:
        with open(FICHIER_PANNEAU, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        return True
    except Exception as e:
        print("Demande d'ouverture non deposee :", e)
        return False


def relever_demande_panneau():
    try:
        if not os.path.exists(FICHIER_PANNEAU):
            return False
        os.remove(FICHIER_PANNEAU)
        return True
    except Exception:
        return False


def relever_demande_synchro():
    """Vrai une seule fois par demande : le mot est efface en le lisant."""
    try:
        if not os.path.exists(FICHIER_DEMANDE):
            return False
        os.remove(FICHIER_DEMANDE)
        return True
    except Exception:
        return False
FICHIER_ENVOI = os.path.join(DOSSIER, "dernier_envoi.txt")  # survit au redemarrage
SEUIL_TROU = 20 * 60          # une absence n'est notee qu'au-dela de 20 min
# La nuit, memes constantes que nuits.js sur le site : les deux cotes doivent
# elire la meme nuit sur le meme digest, sinon « le poste dit X h, le clavier Y h ».
MIN_NUIT_MIN = 120            # sous deux heures, une coupure, pas une nuit
MAX_NUIT_MIN = 16 * 60        # au-dela de seize heures, un week-end sans ordinateur
FENETRE_NUIT = (-12 * 60, 24 * 60)   # midi la veille -> minuit qui ferme le jour
FUSION_MIN = 30               # deux silences separes par moins : un verre d'eau
RYTHME_MIN_NUITS = 7          # en dessous, une mediane n'est pas un rythme
RYTHME_JOURS = 90             # le rythme se lit sur les trois derniers mois
RYTHME_PART = 0.5             # un silence deux fois plus court que le plus long n'est pas candidat
FICHIER_SESSIONS = os.path.join(DOSSIER, "sessions.jsonl")
SESSION = {"notee": False}    # une seule entree de demarrage par lancement
FICHIER_BATTEMENT = os.path.join(DOSSIER, "battement.txt")  # dernier instant vivant
BATTEMENT = {"dernier": 0.0}  # anti-ecriture a chaque image


def noter_session(genre, quand_ts=None, extra=None):
    """Journalise un allumage ou une extinction du poste. C'est ce qui
    donne le lever et le coucher : l'application demarre avec Windows et
    recoit son ordre d'arret, donc demarrage vaut reveil, extinction vaut
    coucher. Fichier a part, une ligne par evenement.

    `quand_ts` force l'horodatage (pour poser apres coup un coucher deduit du
    dernier battement, quand la machine s'est eteinte sans prevenir)."""
    try:
        ts = round(quand_ts if quand_ts is not None else time.time())
        evenement = {"genre": genre,
                     "quand": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                     "ts": ts}
        if extra:
            evenement.update(extra)
        lignes = []
        if os.path.exists(FICHIER_SESSIONS):
            with open(FICHIER_SESSIONS, encoding="utf-8") as f:
                lignes = [l for l in f if l.strip()]
        # Le meme evenement deux fois a quelques secondes (WM_QUERYENDSESSION
        # puis WM_ENDSESSION, un double lancement) n'est qu'un evenement.
        if lignes:
            try:
                precedent = json.loads(lignes[-1])
                if (precedent.get("genre") == genre
                        and abs(ts - float(precedent.get("ts", 0))) < 120):
                    return
            except Exception:
                pass
        lignes.append(json.dumps(evenement, ensure_ascii=False) + "\n")
        with open(FICHIER_SESSIONS, "w", encoding="utf-8") as f:
            f.writelines(lignes[-400:])
    except Exception as e:
        print("Journal des sessions impossible :", e)


def battre():
    """Poser l'instant present sur le disque : « l'app etait vivante jusqu'ici ».

    Ecrit au plus une fois par minute. C'est le filet du coucher : quand la
    machine s'eteint ou s'endort sans que l'app recoive son ordre d'arret (arret
    brutal, batterie, capot rabattu), aucune extinction n'est notee et le coucher
    manquait. Le dernier battement dit alors, a la minute pres, quand la vie s'est
    arretee -- donc quand on s'est couche."""
    maintenant = time.time()
    if maintenant - BATTEMENT["dernier"] < 55:
        return
    BATTEMENT["dernier"] = maintenant
    try:
        with open(FICHIER_BATTEMENT, "w", encoding="utf-8") as f:
            f.write(str(round(maintenant)))
    except Exception:
        pass


def lire_battement():
    try:
        with open(FICHIER_BATTEMENT, encoding="utf-8") as f:
            return float(f.read().strip())
    except Exception:
        return None


def fermer_session_perdue():
    """Au demarrage : reparer un coucher que personne n'a note.

    Si le dernier evenement du journal est un demarrage (donc la session
    precedente ne s'est jamais close proprement) et qu'un battement lui est
    posterieur, la machine a vecu jusqu'a ce battement puis s'est arretee sans
    rien dire. On pose alors une extinction A L'HEURE DU BATTEMENT -- le coucher
    reel de cette nuit-la -- marquee `deduit` pour ne pas la confondre avec un
    arret franc."""
    try:
        bat = lire_battement()
        if not bat:
            return
        evts = []
        if os.path.exists(FICHIER_SESSIONS):
            with open(FICHIER_SESSIONS, encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        evts.append(json.loads(l))
        if not evts:
            return
        dernier = max(evts, key=lambda e: e.get("ts", 0))
        # Deja clos (arret franc note), ou battement anterieur : rien a reparer.
        if dernier.get("genre") == "extinction":
            return
        if bat <= dernier.get("ts", 0):
            return
        noter_session("extinction", quand_ts=bat, extra={"deduit": True})
    except Exception as e:
        print("Cloture de session perdue impossible :", e)


def _hhmm(ts):
    return time.strftime("%H:%M", time.localtime(ts))


def _digest_enregistre(date):
    """Le digest d'un jour passe, tel qu'ecrit sur le disque (None sinon)."""
    try:
        if not os.path.exists(FICHIER_ACTIVITE):
            return None
        with open(FICHIER_ACTIVITE, encoding="utf-8") as f:
            for l in f:
                if _date_de_ligne(l) == date:
                    return json.loads(l)
    except Exception:
        pass
    return None


def _minutes(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _jour_avant(date):
    t = time.strptime(date, "%Y-%m-%d")
    return time.strftime("%Y-%m-%d", time.localtime(time.mktime(t) - 86400))


def _vers_l_avant(de, a):
    """Minutes de `de` a `a` en tournant dans le sens des aiguilles, sur 24 h."""
    return (a - de) % 1440


def _ecart_circulaire(a, b):
    return min(_vers_l_avant(a, b), _vers_l_avant(b, a))


def _mediane_horaire(minutes):
    """La mediane d'heures-minutes SUR LE CERCLE -- port de medianeHoraire (nuits.js).

    Une mediane ordinaire de 23:30 et 00:30 donne midi. On cherche le plus grand
    vide entre deux heures consecutives, on deroule le cercle a partir de ce qui
    le suit, et la mediane se prend la-dessus : 00:00.
    """
    h = sorted(x for x in minutes if x is not None)
    if not h:
        return None
    trou, apres = -1, h[0]
    for i in range(len(h)):
        g = _vers_l_avant(h[i], h[(i + 1) % len(h)])
        if g > trou:
            trou, apres = g, h[(i + 1) % len(h)]
    rel = sorted(_vers_l_avant(apres, x) for x in h)
    n = len(rel)
    m = rel[(n - 1) // 2] if n % 2 else (rel[n // 2 - 1] + rel[n // 2]) / 2.0
    return (apres + m) % 1440


def _rythme_connu(jour):
    """(coucher median, lever median) de la personne, ou (None, None).

    Lu dans les nuits SURES ET COMPLETES des RYTHME_JOURS jours qui precedent
    `jour`, sur le journal local. Deux exclusions, meme raison : un `poste` sans
    coucher (le vieux repli sur plage.de) et un `poste` marque `incertain` (le
    plus long silence d'un jour ambigu, faute de rythme -- voir _choisir_nuit).
    Les laisser entrer ferait du rythme le miroir de ses propres devinettes :
    il confirmerait les horaires de bureau au lieu de les ecarter, et plus il y
    aurait de jours, plus il serait faux. En dessous de RYTHME_MIN_NUITS, on n'a
    pas de rythme, et on le dit.
    """
    try:
        if not os.path.exists(FICHIER_ACTIVITE):
            return (None, None)
        midi = time.mktime(time.strptime(jour + " 12:00", "%Y-%m-%d %H:%M"))
        debut = time.strftime("%Y-%m-%d", time.localtime(midi - RYTHME_JOURS * 86400))
        couchers, levers = [], []
        with open(FICHIER_ACTIVITE, encoding="utf-8") as f:
            for l in f:
                if not l.strip():
                    continue
                try:
                    d = json.loads(l)
                except Exception:
                    continue
                date = str(d.get("date") or "")
                if not (debut <= date < jour):
                    continue
                poste = d.get("poste") or {}
                if poste.get("incertain"):
                    continue
                c, r = _minutes(poste.get("coucher")), _minutes(poste.get("reveil"))
                if c is None or r is None:
                    continue
                couchers.append(c)
                levers.append(r)
        if len(levers) < RYTHME_MIN_NUITS:
            return (None, None)
        return (_mediane_horaire(couchers), _mediane_horaire(levers))
    except Exception:
        return (None, None)


def _choisir_nuit(cands, rythme):
    """Parmi des silences recevables [fin, reprise, duree, source] : (nuit, incertaine).

    LE PLUS LONG N'EST PAS LA NUIT, LE PREMIER L'EST. Une absence est toujours
    plus longue qu'une nuit : qui laisse son fixe allume en partant au bureau
    produit un silence de 09:00 a 19:00, dix heures, contre sept heures trois
    quarts de sommeil reel. En elisant sur la duree, on prenait la journee de
    travail pour la nuit -- vingt jours ouvres sur trente, chez un salarie.

    Or la nuit qui OUVRE le jour D est, par construction, le PREMIER sommeil de
    D : ce qui vient apres est du jour, pas de la nuit. On prend donc le silence
    le plus TOT, et la duree ne sert plus qu'a ecarter les miettes -- en dessous
    de la moitie du plus long, un assoupissement de deux heures et demie n'a pas
    a evincer les huit heures qui suivent.

    Le meme filtre sert AVEC LE RYTHME, ou le depart se fait sur la proximite
    aux medianes de la personne plutot que sur l'heure : chez quelqu'un qui dort
    de 05:30 a 16:00, une absence de 12:00 a 21:00 n'est pas sa nuit. Sur les
    cas ou les deux regles s'appliquent, elles disent la meme chose -- ce qui
    est le seul argument valable pour la premiere.

    ET ON DIT QUAND ON A DEVINE. Sans rythme, si plusieurs silences recevables
    ont des REPRISES DIFFERENTES, le choix est un pari : `incertaine`. Deux fins
    pour la MEME reprise (derniere touche 05:20, extinction 05:26) sont deux
    lectures d'une seule nuit, il n'y a rien a departager.

    Cette marque n'est pas cosmetique, elle casse une BOUCLE. Une nuit devinee
    ne nourrit pas le rythme (_rythme_connu la saute) : sans cela, la journee de
    bureau elue faute de mieux partait dans l'historique, le rythme se calculait
    ENSUITE dessus, et confirmait l'erreur au lieu de la corriger -- plus il y
    avait de jours, plus c'etait faux. Le rythme se batit donc sur les seuls
    jours sans ambiguite (un week-end, un jour ou l'on n'a pas quitte la
    maison), et resout ensuite les jours ambigus.

    Poser une heure « ou tout le monde dort » aurait ete plus simple et faux :
    03:30 vaut pour un couche-tot et exclut quelqu'un qui se couche a 05:26 --
    c'est-a-dire l'hypothese que ce fichier vient justement de retirer.
    """
    plus_long = max(cands, key=lambda s_: s_[2])
    recevables = [s_ for s_ in cands if s_[2] >= RYTHME_PART * plus_long[2]]
    m_c, m_l = rythme if rythme else (None, None)
    if m_c is None or m_l is None:
        return (min(recevables, key=lambda s_: s_[0]),
                len(set(s_[1] for s_ in recevables)) > 1)

    def score(s_):
        return (_ecart_circulaire(s_[1] % 1440, m_l)
                + _ecart_circulaire(s_[0] % 1440, m_c))
    return (min(recevables, key=lambda s_: (score(s_), -s_[2])), False)


def sommeil_estime(jour=None, plage=None, trous=None, rythme="auto"):
    """La nuit qui se TERMINE dans `jour` : coucher, reveil, duree.

    Une nuit est le plus long silence -- toutes sources confondues : derniere
    touche, trou, extinction franche ou deduite du battement -- qui finit par
    une reprise du clavier dans la journee civile, cherche sur trente-six
    heures (midi la veille -> minuit qui ferme le jour). Seule la DUREE borne,
    de 2 h a 16 h : un lever a 16:15 vaut un lever a 08:00. L'ancienne borne
    « fin avant 16:00 » jetait une nuit sur deux chez quelqu'un qui se leve
    l'apres-midi, et le repli sur plage.de rendait alors « reveil 00:00 » :
    la premiere minute d'un fichier civil n'est pas un lever.

    Quand plusieurs silences sont recevables, le rythme de la personne (ses
    medianes de coucher et de lever, voir _rythme_connu) departage ; sans
    rythme, le PREMIER gagne -- la nuit qui ouvre le jour est son premier
    sommeil, pas son plus long silence. Sans nuit recevable : None, jamais un
    reveil sans coucher.

    Le poste : une extinction est une fin de plus, elle ne « coupe » jamais un
    silence (un Windows qui redemarre seul a 00:30 n'est pas un lever, un
    reboot de mise a jour a 09:00 ne reveille personne). Un demarrage ne sert
    que si le clavier n'a rien dit du tout (journaux d'avant le suivi clavier).
    Deux silences separes par moins de trente minutes debout -- un verre
    d'eau a 4 h -- sont une seule nuit.
    """
    try:
        jour = jour or _jour_courant()
        veille = _jour_avant(jour)
        d_jour = {"plage": plage or {}, "trous": trous or []}
        if plage is None:
            if jour == ACTIVITE.get("jour"):
                d_jour = {"plage": {"de": ACTIVITE["premiere"], "a": ACTIVITE["derniere"]},
                          "trous": list(ACTIVITE["trous"])}
            else:
                d_jour = _digest_enregistre(jour) or d_jour
        d_veille = _digest_enregistre(veille) or {}
        # Sur un axe en minutes : 0 = minuit qui ouvre `jour`, le soir de la veille est negatif.
        fins, debuts = [], []
        a = _minutes((d_veille.get("plage") or {}).get("a"))
        if a is not None:
            fins.append(a - 1440)
        for tr in d_veille.get("trous") or []:
            de, ta = _minutes(tr.get("de")), _minutes(tr.get("a"))
            if de is not None and de >= 12 * 60:
                fins.append(de - 1440)
                if ta is not None and ta > de:
                    debuts.append(ta - 1440)
        de = _minutes((d_jour.get("plage") or {}).get("de"))
        if de is not None:
            debuts.append(de)
        for tr in d_jour.get("trous") or []:
            d0, d1 = _minutes(tr.get("de")), _minutes(tr.get("a"))
            if d0 is not None and d1 is not None and d1 > d0:
                fins.append(d0)
                debuts.append(d1)
        # Un silence ne CONTIENT aucune activite connue : « derniere touche a
        # 23:50, premiere a 11:00 » n'est pas une nuit de onze heures si on sait
        # qu'il y a eu du clavier a 03:30. Seul le CLAVIER en temoigne : une
        # extinction ne prouve pas qu'on etait debout, elle ne coupe rien.
        connus = list(fins) + list(debuts)
        clavier = bool(connus)
        fins = [(t, "clavier") for t in fins]
        evts = []
        if os.path.exists(FICHIER_SESSIONS):
            with open(FICHIER_SESSIONS, encoding="utf-8") as f:
                for l in f:
                    if l.strip():
                        evts.append(json.loads(l))
        minuit = time.mktime(time.strptime(jour, "%Y-%m-%d"))
        for e in evts:
            t = (e.get("ts", 0) - minuit) / 60.0
            if not (FENETRE_NUIT[0] <= t < FENETRE_NUIT[1]):
                continue
            if e.get("genre") == "extinction":
                fins.append((t, "poste"))
            elif e.get("genre") == "demarrage" and not clavier:
                debuts.append(t)
        fins.sort()
        debuts.sort()
        # Les silences : de chaque fin a la premiere reprise qui la suit.
        silences = []
        for f_, src in fins:
            suiv = [d for d in debuts if d > f_]
            if not suiv:
                continue
            d = suiv[0]
            if any(f_ + 1 < t < d - 1 for t in connus):
                continue
            # Deux fins pour la meme reprise (derniere touche 05:20, extinction
            # 05:26) : on garde les deux candidats, le choix tranche.
            silences.append([f_, d, d - f_, src])
        fondus = []
        for s_ in silences:
            if fondus and 0 <= s_[0] - fondus[-1][1] < FUSION_MIN:
                fondus[-1][1] = s_[1]
                fondus[-1][2] += s_[2]
            else:
                fondus.append(list(s_))
        # ON NE PLACE LA NUIT DE D QUE SI ON VOIT OU LA VEILLE S'EST ARRETEE.
        # Sans digest de la veille, il ne reste que le silence du soir :
        # « journee 09:00 -> 23:59, trou de 19:00 a 23:00 » sortait comme une
        # nuit de quatre heures, couche a 19:00 -- une soiree dehors lue comme
        # un sommeil. Rien dans le jour D ne permet de trancher. On exige donc
        # qu'une fin existe AVANT la premiere activite connue de D : chez un
        # couche-tard, la derniere touche de la veille est la et sa nuit de
        # 05:26 a 16:20 passe ; sur un jour isole, rien ne passe -- « je ne
        # sais pas » vaut mieux qu'un coucher a 19:00 dans un journal de
        # sommeil. Aucune heure n'est posee : ce serait la norme qu'on refuse.
        premiere = de
        avant_le_jour = premiere is None or any(f_ <= premiere for f_, _ in fins)
        nuits = [s_ for s_ in fondus
                 if 0 <= s_[1] < 1440 and s_[0] >= FENETRE_NUIT[0]
                 and MIN_NUIT_MIN <= s_[2] <= MAX_NUIT_MIN
                 and (avant_le_jour or s_[0] <= premiere)]
        if not nuits:
            return None
        if rythme == "auto":
            rythme = _rythme_connu(jour)
        nuit, incertaine = _choisir_nuit(nuits, rythme)
        if nuit is None:
            return None
        poste = {"reveil": _hhmm(minuit + nuit[1] * 60),
                 "coucher": _hhmm(minuit + nuit[0] * 60),
                 "sommeil_h": round(nuit[2] / 60.0, 1),
                 "source": "poste" if nuit[3] == "poste" else "clavier"}
        if incertaine:
            poste["incertain"] = True
        return poste
    except Exception:
        return None


def _jour_courant():
    return time.strftime("%Y-%m-%d")


NAVIGATEURS = ("chrome", "chromium", "firefox", "msedge", "edge", "brave", "opera", "vivaldi")

# Ce que Windows colle DERRIERE le titre de l'onglet : le nom du navigateur, et
# chez Edge le nom du profil. Ce ne sont pas des sites.
QUEUES_NAV = ("google chrome", "chrome", "mozilla firefox", "firefox", "microsoft edge",
              "edge", "brave", "opera", "vivaldi", "chromium", "navigateur web")

SEPARATEURS = (" - ", " \u2014 ", " \u2013 ", " | ", " \u00b7 ")

# LES SITES QU'ON SAIT NOMMER. Un titre d'onglet ne dit pas ou l'on est de facon
# reguliere : « Voices of the Void - Kerfur Acquired - YouTube » met le site a la
# fin, « Reddit - Dive into anything » le met au debut. On cherche donc un nom
# connu N'IMPORTE OU dans le titre avant de se rabattre sur le dernier morceau.
SITES_CONNUS = (
    "youtube", "reddit", "twitch", "discord", "github", "stack overflow", "stackoverflow",
    "wikipedia", "wikipedia", "twitter", "instagram", "tiktok", "facebook", "linkedin",
    "amazon", "leboncoin", "aliexpress", "netflix", "disney+", "prime video", "spotify",
    "soundcloud", "bandcamp", "steam", "itch.io", "artstation", "deviantart", "pinterest",
    "gmail", "google docs", "google drive", "google maps", "notion", "figma",
    "chatgpt", "claude", "paypal", "wise", "coinbase", "binance", "le monde", "bfmtv",
)

def _titre_onglet(titre):
    """Le titre de l'ONGLET AU PREMIER PLAN, sans le nom du navigateur.

    Windows ne rend que le titre de la fenetre de premier plan -- mais chez un
    navigateur, c'est exactement le titre de l'onglet actif suivi du nom du
    programme. « Compter le temps de l'onglet qui a le focus » ne demande donc
    aucune extension : il suffit de retirer ce qu'on a colle derriere.
    """
    t = " ".join(str(titre or "").split())
    # Le compteur de notifications que Gmail et consorts collent devant.
    while t.startswith("(") and ")" in t[:8]:
        t = t[t.index(")") + 1:].strip()
    for _ in range(3):                     # « … - Profil 1 - Microsoft Edge »
        coupe = None
        for sep in SEPARATEURS:
            i = t.rfind(sep)
            if i > 0 and (coupe is None or i > coupe[0]):
                coupe = (i, len(sep))
        if not coupe:
            break
        queue = t[coupe[0] + coupe[1]:].strip()
        if queue in QUEUES_NAV or (queue.startswith("profil") or queue.startswith("profile")):
            t = t[:coupe[0]].strip()
        else:
            break
    return t


def _site_du_titre(titre, proc):
    """Ou l'on etait. Un nom connu s'il est la, sinon le dernier morceau du titre.

    L'ancienne version prenait LE PREMIER MOT, en affirmant qu'il « porte le
    site ». Il ne le porte pas : « Voices of the Void - Kerfur Acquired -
    YouTube » donnait « voices », et un journal se remplissait de « my », « i »,
    « they » -- les premiers mots de phrases de titres. Des heures de YouTube
    comptees sous cinq noms differents, dont aucun ne voulait rien dire.
    """
    t = _titre_onglet(titre)
    if not t:
        return proc
    for nom in SITES_CONNUS:
        if nom in t:
            return nom.replace(" ", "")[:24]
    bouts = [t]
    for sep in SEPARATEURS:
        bouts = [x for b in bouts for x in b.split(sep)]
    bouts = [b.strip() for b in bouts if b.strip()]
    dernier = bouts[-1] if bouts else t
    # ET UN SITE INCONNU NE DEVIENT PAS UNE PHRASE. « i think they are wrong
    # about this » est un titre de page, pas un endroit : le garder ferait
    # entrer dans le journal -- et de la, dans ce qui part au site -- le contenu
    # meme de ce qu'on lisait. Un nom de site tient en trois mots ; au-dela, on
    # dit « autre », ce qui est vrai et ne raconte rien.
    if len(dernier.split()) > 3 or len(dernier) > 24:
        return "autre"
    return dernier[:24]


"""LES THEMATIQUES : DE QUOI PARLE CE QU'ON REGARDE, PAS OU ON LE REGARDE.

« 249 min web » ne dit rien : trois heures de documentaires et trois heures de
doomscroll sont le meme chiffre. Le SITE ne le dit pas non plus -- YouTube porte
aussi bien un cours de maths qu'une nuit de guerre en Ukraine.

Ce sont des MOTS-CLES sur le titre de l'onglet, pas une comprehension. Un titre
qui ne correspond a rien n'est classe nulle part, et c'est la bonne reponse :
inventer une thematique serait pire que ne rien dire. L'ordre compte -- la
premiere famille qui correspond gagne.

LE SUPPORT N'EST PAS UN SUJET, et « video » / « social » ont ete retires pour
ca. Savoir qu'on etait sur YouTube ne dit rien de plus que la premiere barre de
l'ecran, qui l'affiche deja ; et places en fin de liste, ces deux-la raflaient
tout ce que les familles precises n'avaient pas pris — une heure d'urbex mal
orthographiee finissait en « video », c'est-a-dire nulle part, en ayant l'air
d'etre quelque part. Ce qui n'est pas classe doit se voir comme non classe.

ET LE TITRE NE QUITTE JAMAIS LA MACHINE. C'est ici, en local, que le theme est
calcule ; seul le theme part au site. Le nom de la video, le canal, le pseudo
de la personne d'en face restent sur le poste -- c'est la meme regle que pour
`categorie_activite` depuis le debut, et l'ajout des thematiques ne la desserre
pas d'un cran.
"""
THEMES_ACTIVITE = [
    # -- ce qu'on REGARDE, du plus precis au plus large -------------------
    ("guerre",       ("war footage", "combat footage", "frontline", "front line", "ukraine",
                      "gaza", "guerre", "drone strike", "bodycam", "conflit arme", "russie",
                      "soldat", "militaire", "artillerie", "tranchee", "kherson", "bakhmut")),
    ("politique",    ("politique", "election", "élection", "assemblee nationale", "senat",
                      "gouvernement", "ministre", "president", "président", "macron", "melenchon",
                      "rn ", "sondage", "debat politique", "reforme", "greve", "grève",
                      "manifestation", "syndicat", "loi ", "parlement")),
    ("influenceurs", ("vlog", "storytime", "story time", "drama", "clash", "react", "reaction",
                      "podcast", "interview", "streamer", "influenceur", "influenceuse",
                      "tiktokeur", "youtubeur", "youtubeuse", "unboxing", "grwm", "q&a",
                      "ma journee", "ma journée", "je teste", "j ai teste")),
    ("urbex",        ("urbex", "abandoned", "abandonne", "abandonné", "exploration urbaine",
                      "lieu abandonne", "lost place", "derelict", "friche", "souterrain")),
    ("rp",           ("roleplay", "role play", " rp ", "jdr", "dungeons", "donjons", "dnd", "d&d",
                      "campagne rp", "one shot rp", "murder party")),
    ("jeu",          ("gameplay", "speedrun", "let's play", "lets play", "walkthrough",
                      "no commentary", "steam", "minecraft", "fortnite", "valorant",
                      "league of legends", "elden ring", "boss fight", "modded", "playthrough",
                      "soluce", "tier list", "patch note", "esport", "e-sport",
                      # AJOUTES SUR DES TITRES REELS, pas par anticipation : une
                      # journee ou 35 min de Garry's Mod ne se rangeaient nulle
                      # part. Un nom de jeu tres connu se cherche sans risque ;
                      # un nom obscur remplirait la table de faux.
                      "gmod", "garry's mod", "garrys mod", "backrooms")),
    # « showreel », « epidemic sound » : chercher de la musique libre de droits
    # et des bruitages pour un montage EST du travail de creation. Vu sur une
    # journee reelle a cote de Premiere et FL Studio, pas devine.
    ("creation",     ("showreel", "demoreel", "epidemic sound", "royalty free",
                      "sound effect", "artstation", "deviantart", "blender", "photoshop", "after effects",
                      "davinci", "tutorial", "tuto", "speedpaint", "timelapse", "fl studio",
                      "substance", "zbrush", "rigging", "sculpt", "concept art", "making of",
                      "breakdown vfx", "montage video")),
    # « ost » avec un espace devant attrapait « osteo » : il en faut un derriere.
    ("musique",      ("spotify", "soundcloud", "bandcamp", "playlist", "album", " ost ",
                      "official video", "live session", "concert", "remix", "lofi", "clip",
                      "audio hq", "full album")),
    ("science",      ("documentaire", "espace", "nasa", "astronomie", "physique", "biologie",
                      "neuroscience", "cerveau", "histoire de", "archeologie", "vulgarisation",
                      "conference", "conférence", "these", "étude")),
    ("sante",        ("psy ", "psychologue", "psychiatre", "therapie", "thérapie", "tdah", "adhd",
                      "autisme", "anxiete", "anxiété", "depression", "dépression", "burn out",
                      "sommeil", "symptome", "symptôme", "medecin", "médecin", "diagnostic")),
    # « nba » et « mma » sont cherches ENTOURES D'ESPACES : en sous-chaine, ils
    # rangeaient « do-nba-ss » et « co-nba-se » et « co-mma-nde » dans le sport.
    # Trois lettres suffisent a un sigle et ne suffisent jamais a une recherche
    # en sous-chaine — c'est vrai de tous les sigles de ce tableau.
    ("sport",        ("match", "ligue 1", "premier league", " nba ", "ufc", " mma ", "formule 1",
                      "f1 ", "tennis", "roland garros", "tour de france", "musculation",
                      "entrainement", "entraînement", "workout", "course a pied")),
    ("cuisine",      ("recette", "cuisine", "patisserie", "pâtisserie", "restaurant", "chef ",
                      "marmiton", "batch cooking", "vegan")),
    # « meme » nu attrapait « même » ecrit sans accent, omnipresent dans les
    # titres francais : tout ce qui portait le mot devenait de l'humour.
    ("humour",       ("humour", "sketch", "stand up", "stand-up", "parodie", "memes",
                      "best of", "fail", "compilation drole", "compilation drôle")),
    ("voyage",       ("voyage", "roadtrip", "road trip", "randonnee", "randonnée", "itineraire",
                      "billet d avion", "airbnb", "booking", "guide de voyage")),
    ("adulte",       ("porn", "pornhub", "xvideos", "xhamster", "onlyfans", "nsfw", "hentai",
                      "camgirl", "escort")),
    ("actu",         ("actualite", "actualité", "le monde", "bfm", "france info", "franceinfo",
                      "news", "reportage", "journal televise", "20 minutes", "mediapart",
                      "liberation", "le figaro")),
    ("achat",        ("amazon", "leboncoin", "aliexpress", "panier", "checkout", "commande",
                      "livraison", "vinted", "cdiscount", "fnac")),
    ("argent",       ("paypal", "banque", "assurance", "impots", "impôts", "coinbase", "binance",
                      "virement", "facture", "mutuelle", "caf ", "pole emploi", "pôle emploi")),
    ("dev",          ("github", "stack overflow", "stackoverflow", " npm", "pypi", "documentation",
                      "docs.", "localhost", "pull request", "commit", "python", "javascript",
                      "api ", "typescript", "docker", "regex")),
]


# UN MOT-CLE EST UN MOT, PAS UNE SUITE DE LETTRES.
#
# Mesure sur une vraie journee : « leo kiner demoreel 2026 » etait range dans
# SANTE, parce que « kine » se trouve dans « kiner ». Un nom de famille lu comme
# une profession medicale, dans le journal de quelqu'un -- et la table qui dit
# ailleurs, noir sur blanc, qu'elle ne nommera jamais un trouble. Meme maladie :
# « scamming the police department » range en faits-divers.
#
# Le projet avait deja nomme cette maladie une fois, pour les sigles de trois
# lettres (« donbass » contient « nba »), et l'avait soignee mot par mot, en
# bordant d'espaces ceux qu'on avait vus rater. 276 mots courts sont restes nus.
# Les soigner un par un, c'est exactement ce qui a laisse passer « kine ».
#
# LA REGLE, DONC : un mot fait de LETTRES SEULES doit commencer et finir sur une
# frontiere de mot -- un « s » final tolere, pour que « drone » prenne
# « drones » sans que « kine » prenne « kiner ». Un mot qui porte de la
# ponctuation ou une espace garde la recherche en sous-chaine : « docs. » doit
# attraper « docs.python.org », « d&d » et « 100% » ne se bordent pas, et une
# expression de deux mots ne se perd pas au milieu d'un mot.
_LETTRES = "abcdefghijklmnopqrstuvwxyz0123456789àâäçéèêëîïôöùûüÿœæ"
_MOTS_BORNES = {}


def _dit(plein, mot):
    """`plein` contient-il `mot` EN TANT QUE MOT."""
    nu = mot.strip()
    if not nu:
        return False
    if not nu.isalpha():
        # Ponctuation, chiffres, espaces : la sous-chaine est deja sans risque,
        # et c'est parfois le comportement voulu (« docs. »).
        return mot in plein
    motif = _MOTS_BORNES.get(nu)
    if motif is None:
        motif = _MOTS_BORNES[nu] = re.compile(
            "(?<![%s])%ss?(?![%s])" % (_LETTRES, re.escape(nu), _LETTRES))
    return bool(motif.search(plein))


def _plein(contexte):
    """Le titre de l'onglet et le programme, en une chaine bordee d'espaces."""
    proc, _, titre = (contexte or "").strip().lower().partition("|")
    return " " + " ".join((_titre_onglet(titre) + " " + proc.strip()).split()) + " "


"""OU L'ON EST, QUAND LE TITRE NE DIT PAS DE QUOI IL PARLE.

MESURE SUR ONZE TITRES REELS -- les seuls dont on dispose, relus sur deux
captures d'ecran : NEUF ne sont classes nulle part. Et en les regardant, ce ne
sont pas des mots-cles qui manquent. Trois formes reviennent, et aucune ne parle
d'un sujet :

  « reddit - the heart of the internet », « youtube », « x », « google »
      une page d'accueil. Le titre est le nom de l'endroit, et rien d'autre.
  « #ecriture-de-sinj | pti' marchand de sable »
      un salon et un serveur. C'est une conversation, pas un sujet.
  « portal 2, but it's poorly translated », « wardogs », « the merchant's
    ledger - skyrim market tracker »
      un NOM PROPRE. Aucune table generique ne les contiendra jamais.

Les deux premieres se reconnaissent a leur FORME, pas a leur contenu : c'est
pour ca qu'on peut les traiter ici sans deviner. La troisieme ne se traite pas
par une table du tout -- c'est le vocabulaire de quelqu'un, et il faudra le lui
demander.

CE QU'ON REND N'EST PAS UN SUJET, ET L'ECRAN DOIT LE DIRE. « video » et
« social » avaient ete retires parce que, dans la meme liste que « guerre » et
« science », ils raflaient tout ce que les familles precises n'avaient pas
pris. Ici ils ne sont interroges qu'APRES l'echec du sujet : ils ne peuvent
structurellement plus en voler un. Mais un lieu affiche comme un sujet
raconterait qu'on sait de quoi ca parlait alors qu'on sait seulement ou
c'etait -- d'ou `lieu_activite`, a part, et un champ a part dans le digest.
"""
# Un titre qui n'est QUE le nom de l'endroit : la page d'accueil, avant d'avoir
# clique sur quoi que ce soit.
COQUILLES = {
    "reddit": "forum", "reddit the heart of the internet": "forum",
    "youtube": "video", "twitch": "video", "netflix": "video",
    "x": "reseau", "twitter": "reseau", "facebook": "reseau",
    "instagram": "reseau", "tiktok": "reseau", "linkedin": "reseau",
    "google": "recherche", "gmail": "courrier", "discord": "messagerie",
    "nouvel onglet": "accueil", "new tab": "accueil", "accueil": "accueil",
}

LIEUX = (
    ("messagerie", ("discord", "whatsapp", "messenger", "telegram", "signal", "slack", "teams")),
    ("forum",      ("reddit", "hacker news", "stack overflow", "stackoverflow", "quora",
                    "jeuxvideo.com", " forum")),
    ("video",      ("youtube", "twitch", "netflix", "dailymotion", "vimeo", "prime video",
                    "crunchyroll", "disney", "arte")),
    ("reseau",     ("x.com", "twitter", "instagram", "tiktok", "facebook", "linkedin",
                    "snapchat", "pinterest", "tumblr")),
    ("recherche",  ("recherche google", "google search", "duckduckgo", "qwant", " bing")),
    ("boutique",   ("amazon", "leboncoin", "aliexpress", "vinted", "ebay", "etsy",
                    "cdiscount", "fnac")),
    ("encyclo",    ("wikipedia", "wikipédia", " wiki", "documentation", "docs.")),
)

# LA SIGNATURE QU'UN SITE MET DANS SON PROPRE TITRE, lue AVANT les mots-cles.
# « <n'importe quoi> / X » est la forme que X donne a toutes ses pages. Le mot
# « x » est trop court pour entrer dans la table des lieux -- il rafferait la
# moitie du web -- mais en fin de titre, derriere une barre oblique, il ne
# designe que ca.
#
# ELLE PASSE AVANT LA TABLE, et il faut dire pourquoi, parce qu'une autre regle
# generale a ete retiree d'ici pour avoir fait exactement l'inverse. Le diese ne
# disait rien du site : n'importe qui en tape un, et la regle prenait « Bug
# #1203 » pour une conversation. Une fin de titre en « / X », personne ne la
# tape : c'est X qui la met. Un site qui se nomme lui-meme sait mieux ou l'on est
# qu'un mot qui traine dans le titre -- « <quelqu'un> sur X : "youtube vient de
# casser" / X » est un message sur X, pas une video, et c'est « video » que la
# table repondait tant que cette lecture venait apres elle.
#
# MESURE : zero change sur les onze vrais titres -- leur seul X est la coquille
# nue, deja prise plus haut. C'est une generalisation, pas un gain constate.
SUFFIXES_WEB = (
    ("reseau", (" / x",)),
)

# « on ne m'a pas dit le theme » n'est pas « il n'y a pas de theme » : None est
# une reponse valable de `theme_activite`, et la confondre avec l'absence
# d'argument ferait recalculer a chaque fois chez qui l'a deja.
_INCONNU = object()


def lieu_activite(contexte, theme=_INCONNU):
    """L'ENDROIT, jamais a la place d'un sujet. None si on ne sait pas.

    LA REGLE TIENT ICI, PAS AU POINT D'APPEL. Elle y etait -- « le lieu n'est lu
    que si le sujet s'est tu » -- et un point d'appel est exactement l'endroit
    ou une regle se perd : il suffit d'un second appelant qui l'ignore pour que
    « video » se remette a rafler ce que « guerre » aurait pris. Le second
    argument evite seulement de recalculer le theme a qui le connait deja.
    """
    if not (contexte or "").strip():
        return None
    if theme is _INCONNU:
        theme = theme_activite(contexte)
    if theme:
        return None
    plein = _plein(contexte)
    # LA COQUILLE SE LIT SUR LE TITRE SEUL. `_plein` colle le nom du programme
    # derriere le titre pour que les mots-cles le voient aussi ; « x » y devient
    # « x chrome.exe » et ne ressemble plus a une page d'accueil. On compare donc
    # au titre nu, lui, avant tout le reste.
    proc, _, titre = (contexte or "").strip().lower().partition("|")
    nu = " ".join(_titre_onglet(titre).split())
    if nu in COQUILLES:
        return COQUILLES[nu]
    # PAS DE REGLE SUR LE DIESE. Elle y etait -- « un salon se reconnait a son
    # dieze » -- et elle passait AVANT la table, donc elle lui volait : « #skyrim
    # - Recherche / X » devenait une messagerie, « Bug #1203 - Bugzilla » aussi.
    # Elle ne gagnait rien en echange : tout client de discussion met son nom
    # dans le titre, et la table le prend deja. Mesure sur les onze vrais
    # titres : zero change en la retirant, deux faux en la gardant.
    for nom, fins in SUFFIXES_WEB:
        for fin in fins:
            if titre.strip().endswith(fin):
                return nom
    for nom, mots in LIEUX:
        for mot in mots:
            if _dit(plein, mot):
                return nom
    return None



# CE QUI N'EST PAS UN NOM. `_site_du_titre` ecrit « autre » quand il n'a pas
# reconnu le site -- c'est honnete la-bas, et ce serait un mensonge ici : le
# dernier palier existe pour DIRE le nom qu'on a, pas pour habiller un trou. Un
# onglet sans titre non plus n'a pas de nom. Ces minutes-la restent du vide, et
# l'ecran doit continuer a les compter comme du vide.
SANS_NOM = ("autre", "sans titre", "inconnu", "")


def _lieux_depuis_titres(titres):
    """Les lieux, les sites seuls ET les titres derriere, depuis les titres.

    LE COMPTEUR NE PEUT PAS SAVOIR CE QUI S'EST PASSE AVANT LUI. `lieux_web`
    court pendant la journee : une version qui apprend a situer un onglet a
    midi ne sait rien des heures du matin, et la journee se termine en disant
    beaucoup moins que ce qu'elle a vu. Mesure sur une vraie journee : le
    digest portait 30 min de lieux la ou ses propres titres en justifiaient
    141. Le reste n'etait pas du temps qu'on ne savait pas situer -- c'etait
    du temps ou personne n'avait encore essaye.

    Les titres, eux, sont la depuis le matin, et c'est LA MEME MESURE vue
    autrement : la meme seconde, rangee sous un titre au lieu d'un lieu.

    Le contexte est reconstruit en « |titre » : sans la barre, `_plein` prend
    le titre pour un nom de programme et la coquille ne se lit plus. Le nom du
    programme manque, lui, et c'est sans effet -- aucun mot des tables de lieux
    n'est un nom de programme, et seuls les contextes web sont rejoues.
    """
    lieux, seuls, par_titre = {}, {}, {}
    for cat, d in (titres or {}).items():
        if not str(cat).startswith("web:"):
            continue
        site = str(cat)[4:]
        for t, sec in (d or {}).items():
            try:
                sec = float(sec)
            except (TypeError, ValueError):
                continue
            if sec <= 0:
                continue
            contexte = "|" + str(t)
            ou = lieu_activite(contexte)
            if ou:
                lieux[ou] = lieux.get(ou, 0.0) + sec
                par = par_titre.setdefault(ou, {})
                par[str(t)] = par.get(str(t), 0.0) + sec
            elif not theme_activite(contexte) and site not in SANS_NOM:
                seuls[site] = seuls.get(site, 0.0) + sec
    return lieux, seuls, par_titre


def theme_activite(contexte):
    """La thematique de ce qu'on regarde, ou None quand rien ne correspond."""
    if not (contexte or "").strip():
        return None
    plein = _plein(contexte)
    for nom, mots in THEMES_ACTIVITE:
        for mot in mots:
            if _dit(plein, mot):
                return nom
    # UNE SOUS-CATEGORIE RECONNUE IMPLIQUE SON THEME.
    #
    # Les deux tables sont ecrites separement, et la seconde connait des mots
    # que la premiere ignore : « donbass » est de la guerre, « exoplanete » de
    # la science, « urssaf » de l'argent -- mais le theme ne se declenchait pas,
    # donc la sous-categorie n'etait jamais consultee et le titre finissait non
    # classe. Onze sous-categories etaient ainsi inatteignables toutes seules.
    #
    # On repasse dans l'ordre des THEMES pour garder leur priorite : ce second
    # tour ne change pas qui gagne, il rattrape ce que personne ne prenait.
    for nom, _ in THEMES_ACTIVITE:
        for _, mots in SOUS_THEMES.get(nom, ()):
            for mot in mots:
                if _dit(plein, mot):
                    return nom
    return None


"""LES SOUS-CATEGORIES : DANS UN SUJET, DE QUOI IL S'AGIT.

« 40 min de guerre » est deja plus utile que « 249 min web ». Mais la guerre
en Ukraine suivie sur des cartes et une nuit de bodycams ne sont pas la meme
soiree, et le theme les compte pareil. La sous-categorie est une SECONDE
passe, a l'interieur d'un theme deja trouve : elle affine, elle ne reclasse
pas. Un titre qu'aucune sous-categorie ne reconnait reste dans son theme, sans
sous-categorie -- et c'est la bonne reponse, pas un trou a boucher.

TROIS REGLES QUI NE SE NEGOCIENT PAS.

1. UNE SOUS-CATEGORIE EST UN SUJET, JAMAIS QUELQU'UN. Pas de nom de chaine, pas
   de pseudo, pas de nom de personne. Le theme protegeait deja ca ; le raffiner
   au point de nommer QUI on regardait ferait exactement ce que la regle du
   produit interdit depuis le debut.

2. « SANTE » NE SE SOUS-CATEGORISE PAS EN DIAGNOSTICS. Ses sous-categories
   nomment un DOMAINE -- le sommeil, le corps, le soin -- jamais un trouble.
   « sante/tdah » qui remonte au site serait une etiquette clinique posee par
   une table de mots-clefs, c'est-a-dire la chose precise que ce produit refuse
   de faire.

3. « ADULTE » N'A PAS DE SOUS-CATEGORIE, ET C'EST DELIBERE. Le theme dit deja
   tout ce qui est utile a quelqu'un qui regarde ou passe son temps. Le
   detailler transformerait un compteur grossier en un releve des gouts
   sexuels de quelqu'un, range dans son journal, et aucune lecture de soi ne
   vaut ce prix.

L'ordre compte, comme pour les themes : la premiere sous-categorie qui
correspond gagne. Les plus precises sont donc en haut.
"""
SOUS_THEMES = {
    "guerre": (
        ("ukraine",     ("ukraine", "ukrainien", "kherson", "bakhmut", "donbass", "kharkiv",
                         "zaporijia", "avdiivka", "koursk", "kiev", "kyiv")),
        ("proche-orient", ("gaza", "israel", "israël", "palestine", "liban", "hezbollah",
                         "houthi", "yemen", "syrie", "tsahal")),
        ("analyse",     ("analyse", "carte du front", "strategie", "stratégie", "doctrine",
                         "osint", "geopolitique", "géopolitique", "renseignement", "briefing")),
        ("materiel",    ("drone", "fpv", "artillerie", "char ", "missile", "himars", "javelin",
                         "blinde", "blindé", "obus", "f-16", "systeme d arme")),
        ("archives",    ("39-45", "1939", "1944", "seconde guerre", "wwii", "ww2", "vietnam",
                         "indochine", "algerie", "algérie", "14-18", "grande guerre")),
    ),
    "politique": (
        ("elections",   ("election", "élection", "sondage", "scrutin", "campagne", "candidat",
                         "second tour", "legislative", "législative", "presidentielle")),
        ("france",      ("assemblee nationale", "assemblée", "senat", "sénat", "gouvernement",
                         "ministre", "matignon", "elysee", "élysée", "motion de censure",
                         "conseil des ministres")),
        ("social",      ("greve", "grève", "manifestation", "syndicat", "retraite", "salaire",
                         "cgt", "mouvement social", "blocage")),
        ("international", ("otan", "onu", "union europeenne", "union européenne", "bruxelles",
                         "sommet", "diplomatie", "sanctions", "traite", "traité")),
        ("debat",       ("debat", "débat", "editorial", "éditorial", "tribune", "chronique",
                         "plateau", "face a face")),
    ),
    "influenceurs": (
        ("drama",       ("drama", "clash", "cancel", "polemique", "polémique", "accusation",
                         "mise au point", "reponse a", "réponse à", "je m explique")),
        ("react",       ("react", "reaction", "réaction", "je regarde", "on regarde", "tier list",
                         "je note", "je teste")),
        ("recit",       ("mon histoire", "je raconte", "mon quotidien", "ma semaine",
                         "une journee avec", "ce qui m est arrive", "get ready", "routine")),
        ("entretien",   ("podcast", "interview", "entretien", "invite", "invité", "q&a",
                         "questions reponses")),
        ("marque",      ("unboxing", "haul", "code promo", "sponsorise", "sponsorisé",
                         "collab", "ma collection")),
    ),
    "urbex": (
        ("souterrain",  ("souterrain", "catacombe", "carriere", "carrière", "tunnel", "bunker",
                         "egout", "égout", "mine ")),
        ("batiment",    ("hopital", "hôpital", "asile", "sanatorium", "ecole abandonnee",
                         "usine", "chateau abandonne", "château abandonné", "manoir", "hotel abandonne")),
        ("epave",       ("epave", "épave", "wreck", "navire abandonne", "avion abandonne",
                         "cimetiere de", "cimetière de", "train abandonne")),
        ("catastrophe", ("tchernobyl", "chernobyl", "pripyat", "fukushima", "zone d exclusion",
                         "ville fantome", "ville fantôme", "ghost town")),
    ),
    "rp": (
        ("table",       ("jdr", "dungeons", "donjons", "dnd", "d&d", "pathfinder", "maitre du jeu",
                         "maître du jeu", "one shot", "campagne", "fiche de personnage")),
        ("serveur",     ("gta rp", "fivem", "serveur rp", "whitelist", "minecraft rp", "arma",
                         "dayz", "garry s mod")),
        ("ecrit",       ("forum rp", "rp ecrit", "rp écrit", "roleplay ecrit", "fiche rp",
                         "contexte rp", "intrigue")),
        ("murder",      ("murder party", "enquete grandeur", "enquête grandeur", "escape game",
                         "grandeur nature", "gn ")),
    ),
    "jeu": (
        # « classe » et « ligue » nus attrapaient du francais ordinaire.
        ("competitif",  ("ranked", "classement", "esport", "e-sport", "tournoi", "scrim",
                         "valorant", "league of legends", "counter", "rocket league", "montee elo")),
        ("solo",        ("fin du jeu", "100%", "sans mourir", "sans degats", "sans dégâts",
                         "premiere partie", "première partie", "nouvelle partie", "difficulte max",
                         "run complete")),
        ("bac-a-sable", ("minecraft", "modded", "moddé", "terraria", "factorio", "survie",
                         "base building", "seed ", "farm ")),
        # « sortie » et « annonce » nus : trop de francais ordinaire.
        ("actualite",   ("patch note", "trailer", "bande annonce", "gameplay reveal",
                         "roadmap", "mise a jour du jeu", "date de sortie")),
        ("retro",       ("retro", "rétro", "speedrun", "any%", "nes ", "snes", "ps1", "n64",
                         "emulateur", "émulateur", "abandonware")),
    ),
    "creation": (
        ("3d",          ("blender", "zbrush", "substance", "maya ", "cinema 4d", "houdini",
                         "sculpt", "rigging", "topologie", "shader", "render")),
        ("2d",          ("photoshop", "krita", "procreate", "clip studio", "speedpaint",
                         "line art", "concept art", "illustration", "palette", "perspective")),
        ("video",       ("after effects", "davinci", "premiere", "montage video", "montage vidéo",
                         "etalonnage", "étalonnage", "vfx", "compositing", "motion design")),
        ("son",         ("fl studio", "ableton", "reaper", "cubase", "mixage", "mastering",
                         "sound design", "synthese", "synthèse", "vst")),
        ("ecriture",    ("scenario", "scénario", "worldbuilding", "structure du recit",
                         "structure du récit", "dialogue", "personnage", "storyboard")),
    ),
    "musique": (
        ("live",        ("live session", "concert", "en direct", "boiler room", "tiny desk",
                         "unplugged", "festival", "set live")),
        # « ost » demande ses deux espaces ici aussi : sans le second il attrapait
        # « osteo », et depuis que la sous-categorie implique son theme, ca
        # rangeait un rendez-vous chez le kine dans la musique.
        ("album",       ("full album", "album complet", " ost ", "bande originale", "soundtrack",
                         "deluxe", "ep ", "lp ")),
        ("playlist",    ("playlist", "mix ", "lofi", "radio", "compilation", "ambient",
                         "pour travailler", "pour dormir")),
        ("clip",        ("official video", "clip officiel", "music video", "visualizer", "lyrics",
                         "paroles")),
        ("remix",       ("remix", "mashup", "cover", "reprise", "edit ", "nightcore", "slowed")),
    ),
    "science": (
        ("espace",      ("nasa", "espace", "astronomie", "galaxie", "trou noir", "exoplanete",
                         "exoplanète", "fusee", "fusée", "spacex", "james webb", "mars ")),
        ("vivant",      ("biologie", "neuroscience", "cerveau", "adn", "evolution", "évolution",
                         "cellule", "microbe", "animal", "espece", "espèce", "ecosysteme")),
        ("physique",    ("physique", "quantique", "relativite", "relativité", "particule",
                         "thermodynamique", "mathematique", "mathématique", "theoreme", "théorème")),
        ("histoire",    ("histoire de", "archeologie", "archéologie", "antiquite", "antiquité",
                         "moyen age", "moyen âge", "civilisation", "empire", "prehistoire")),
        ("terre",       ("geologie", "géologie", "volcan", "climat", "ocean", "océan", "seisme",
                         "séisme", "meteo", "météo", "glacier")),
    ),
    # « sante » nomme un DOMAINE, jamais un trouble : voir la regle 2 en tete.
    "sante": (
        ("sommeil",     ("sommeil", "insomnie", "dormir", "reveil nocturne", "réveil nocturne",
                         "sieste", "rythme circadien", "apnee", "apnée")),
        ("psy",         ("psy ", "psychologue", "psychiatre", "therapie", "thérapie", "tcc",
                         "consultation", "emdr", "mindfulness", "meditation", "méditation")),
        ("corps",       ("douleur", "dos ", "articulation", "migraine", "digestion", "peau",
                         "kine", "kiné", "osteo", "ostéo", "posture")),
        ("soin",        ("medecin", "médecin", "ordonnance", "pharmacie", "urgence", "hopital",
                         "hôpital", "specialiste", "spécialiste", "rendez vous medical")),
        ("hygiene",     ("alimentation", "nutrition", "vitamine", "hydratation", "sevrage",
                         "arreter de", "arrêter de", "addiction")),
    ),
    "sport": (
        # Un seul sport collectif laissait le basket, le rugby et le handball
        # dehors : « resume nba » tombait dans « sport » sans plus de precision.
        ("collectif",   ("liga", "champions league", "coupe du monde", "psg", "ballon d or",
                         "mercato", "football", "basket", "rugby", "handball", "volley",
                         "top 14", "euroligue")),
        ("combat",      ("ufc", "mma", "boxe", "judo", "lutte", "kickboxing", "grappling",
                         "combat ", "ko ")),
        # « endurance » est le NOM de la sous-categorie suivante : le garder ici
        # faisait tomber « sport d'endurance » dans « moteur », qui vient avant.
        ("moteur",      ("formule 1", "f1 ", "motogp", "rallye", "wrc", "24h du mans", "le mans",
                         "grand prix", "qualifications")),
        ("endurance",   ("marathon", "course a pied", "trail", "triathlon", "cyclisme",
                         "tour de france", "natation", "chrono")),
        ("muscu",       ("musculation", "entrainement", "entraînement", "workout", "programme",
                         "seche", "sèche", "prise de masse", "squat", "developpe")),
    ),
    "cuisine": (
        ("patisserie",  ("patisserie", "pâtisserie", "gateau", "gâteau", "tarte", "brioche",
                         "chocolat", "creme", "crème", "levain", "pain ")),
        ("recette",     ("recette", "marmiton", "plat ", "sauce", "mijote", "mijoté", "four ",
                         "poele", "poêle", "en 20 minutes")),
        ("restaurant",  ("restaurant", "chef ", "etoile", "étoile", "bistrot", "carte du",
                         "critique culinaire", "food")),
        ("regime",      ("vegan", "vegetarien", "végétarien", "batch cooking", "meal prep",
                         "sans gluten", "proteine", "protéine", "calories")),
    ),
    "humour": (
        ("sketch",      ("sketch", "stand up", "stand-up", "one man show", "spectacle",
                         "improvisation", "parodie", "sketch comique")),
        # « meme » nu attrapait « même » ecrit sans accent, omnipresent dans les
        # titres francais : la sous-categorie aurait double de taille pour rien.
        ("meme",        ("memes", "shitpost", "cursed", "brainrot", "copypasta", "meme drole")),
        # « rate » attrapait « pirate », « separate ».
        ("fail",        ("moments genants", "moments gênants", "bloopers", "ca tourne mal",
                         "ça tourne mal", "loupe la marche", "gag", "malaise")),
    ),
    "voyage": (
        ("preparation", ("billet d avion", "airbnb", "booking", "itineraire", "itinéraire",
                         "budget voyage", "visa", "assurance voyage", "vol pas cher")),
        ("randonnee",   ("randonnee", "randonnée", "gr ", "bivouac", "refuge", "sentier",
                         "trek", "sac a dos", "camping")),
        ("recit",       ("roadtrip", "road trip", "carnet de voyage", "jour 1", "vlog voyage",
                         "on est arrive", "j ai visite")),
        ("ville",       ("que faire a", "guide de", "week end a", "48h a", "city guide",
                         "quartier", "musee", "musée")),
    ),
    # « adulte » reste sans sous-categorie : voir la regle 3 en tete.
    "actu": (
        # « police » ET « justice » SONT SORTIS D'ICI. Ce sont de vrais mots, pas
        # des sous-chaines -- la regle du mot entier ne les sauve pas. Ils sont
        # simplement anglais autant que francais : « scamming the police
        # department by selling them boots » est une video de Garry's Mod, et
        # elle etait rangee en faits-divers, 8 minutes. Le reste de la liste est
        # du francais qui ne se trompe pas de langue. Et un faux SUJET coute
        # deux fois : il prend la place, et il empeche le LIEU de repondre.
        ("faits-divers", ("fait divers", "proces", "procès", "enquete", "enquête",
                         "disparition", "accident", "incendie")),
        ("monde",       ("international", "etats unis", "états unis", "chine", "russie", "afrique",
                         "moyen orient", "correspondant", "a l etranger")),
        ("economie",    ("inflation", "chomage", "chômage", "bourse", "croissance", "pouvoir d achat",
                         "budget de l etat", "dette", "entreprise", "licenciement")),
        # PAS DE « actu/france ». Ses mots-clefs seraient exactement ceux qui
        # declenchent le theme « actu » : presque tout ce qui entre dans actu
        # sans avoir matche faits-divers en ressortirait, quel que soit le sujet
        # lu. Une sous-categorie qui reprend les mots de son theme est un
        # SUPPORT deguise en sujet, et elle ne dit rien de plus que le theme.
    ),
    "achat": (
        ("commande",    ("panier", "checkout", "commande", "livraison", "suivi de colis",
                         "retour produit", "facture d achat", "paiement")),
        ("occasion",    ("leboncoin", "vinted", "occasion", "seconde main", "annonce", "negociation",
                         "négociation", "reconditionne", "reconditionné")),
        ("recherche",   ("comparatif", "avis ", "test ", "meilleur ", "guide d achat", "promo",
                         "soldes", "black friday", "prix ")),
    ),
    "argent": (
        ("banque",      ("banque", "compte courant", "virement", "rib", "decouvert", "découvert",
                         "carte bancaire", "livret", "epargne", "épargne")),
        ("impots",      ("impots", "impôts", "declaration", "déclaration", "urssaf", "tva",
                         "avis d imposition", "prelevement", "prélèvement")),
        ("crypto",      ("coinbase", "binance", "bitcoin", "ethereum", "crypto", "wallet",
                         "blockchain", "staking")),
        ("charges",     ("loyer", "abonnement", "edf", "engie", "resiliation", "résiliation",
                         "prelevement automatique", "echeance", "échéance", "relance de paiement")),
    ),
    "dev": (
        ("erreur",      ("stack overflow", "stackoverflow", "error", "erreur", "traceback",
                         "exception", "debug", "ne marche pas", "fix ", "issue ")),
        ("depot",       ("github", "gitlab", "pull request", "commit", "merge", "branche",
                         "diff ", "review", "ci ")),
        ("doc",         ("documentation", "docs.", "reference", "référence", "api ", "guide",
                         "getting started", "changelog", "man ")),
        ("outil",       ("docker", " npm", "pypi", "webpack", "vite", "cli ", "config",
                         "deploiement", "déploiement", "localhost")),
        ("langage",     ("python", "javascript", "typescript", "rust", "golang", " go ", "sql ",
                         "regex", "css ", "html")),
    ),
}


def sous_theme_activite(theme, contexte):
    """La sous-categorie DANS un theme deja trouve, ou None.

    Deuxieme passe et deuxieme table : on ne cherche une sous-categorie que si
    le theme est deja tombe. Un titre qui a donne « guerre » sans donner
    « ukraine » ni « analyse » reste de la guerre sans plus de precision -- et
    c'est plus honnete que de le ranger dans la sous-categorie la plus large
    pour que la barre soit pleine.
    """
    sous = SOUS_THEMES.get(theme or "")
    if not sous or not (contexte or "").strip():
        return None
    plein = _plein(contexte)
    for nom, mots in sous:
        for mot in mots:
            if _dit(plein, mot):
                return nom
    return None


def categorie_activite(contexte):
    """'chrome.exe | voices of the void - youtube' -> 'web:youtube', 'code.exe' -> 'code'.

    On garde le programme, et pour un navigateur LE SITE lu dans le titre de
    l'onglet au premier plan (voir `_site_du_titre`). On ne conserve donc ni le
    canal, ni le nom de la personne, ni le titre de la video : juste ou on
    etait, pas avec qui. Le sujet, lui, passe par `theme_activite` -- un mot,
    calcule ici, jamais le titre.
    """
    contexte = (contexte or "").strip()
    if not contexte:
        return "inconnu"
    proc, _, titre = contexte.partition("|")
    proc = proc.strip().replace(".exe", "")
    titre = titre.strip()
    if any(n in proc for n in NAVIGATEURS) and titre:
        return "web:" + _site_du_titre(titre, proc)
    if proc:
        return proc[:32]
    # Sans nom de processus (un jeu qui refuse qu'on lise le sien), on ne jette
    # pas ce temps dans 'inconnu' : le titre de sa fenetre le nomme encore --
    # « bodycam » vaut mieux qu'un trou.
    if titre:
        return titre.split(" - ")[0].split(" | ")[0][:32]
    return "inconnu"


def _reinit_jour(reprendre=False, maintenant=None):
    """Ouvre une journee vide -- ou REPREND celle qui est deja sur le disque.

    Au demarrage, une journee en cours existe presque toujours : l'application
    vient d'etre relancee (mise a jour, redemarrage, plantage) et le disque
    porte deja son temps d'ecran. Repartir de zero le REECRASAIT : `sauver_activite`
    remplace la ligne du jour, donc six heures d'ecran devenaient « 0 min » a
    chaque relance. Trois mises a jour dans la journee, et la journee etait vide.

    On relit donc les compteurs et on continue de compter dessus. Au changement
    de jour (minuit), `reprendre` reste faux : c'est bien une journee neuve.

    LA REPRISE EST UN TROU. Entre la derniere minute active sur le disque et la
    premiere touche apres la relance, personne n'a mesure : l'application etait
    morte. Sans ce trou, un PC eteint a 05:26 et rallume a 16:15 ne laissait
    AUCUNE reprise au clavier, et le lever etait invisible -- le repli rendait
    « reveil 00:00 ». On ouvre donc le trou a plage.a du disque ; le premier
    echantillon actif le ferme, et lui seul : `reprise` empeche un echantillon
    inactif d'ouvrir un trou artefact a l'heure de la relance ou a 00:00:02
    (quelqu'un d'inactif a minuit dort deja, et sa nuit vient de veille.plage.a).
    """
    jour = _jour_courant()
    ACTIVITE.update(jour=jour, contexte="", titre_courant="",
                    depuis=maintenant if maintenant is not None else time.time(),
                    temps={}, titres={}, themes={}, themes_web={},
                    titres_theme={}, sous_themes_web={}, lieux_web={}, sites_seuls={},
                    titres_lieu={},
                    theme_courant=None, sous_courant=None, lieu_courant=None,
                    web_courant=False, bascules=0,
                    actif_s=0.0, premiere="", derniere="", trous=[],
                    trou_depuis=0.0, reprise=True)
    if not reprendre:
        return
    try:
        d = _digest_enregistre(jour)
        if not isinstance(d, dict):
            return
        temps = d.get("temps_par_contexte_s") or {}
        ACTIVITE["temps"] = {str(k): float(v) for k, v in temps.items()
                             if isinstance(v, (int, float)) and v > 0}
        ACTIVITE["titres"] = {str(k): {str(t): float(x) for t, x in (v or {}).items()}
                              for k, v in (d.get("titres") or {}).items()}
        themes = d.get("temps_par_theme_s") or {}
        ACTIVITE["themes"] = {str(k): float(v) for k, v in themes.items()
                              if isinstance(v, (int, float)) and v > 0}
        web = d.get("temps_par_theme_web_s") or {}
        ACTIVITE["themes_web"] = {str(k): float(v) for k, v in web.items()
                                  if isinstance(v, (int, float)) and v > 0}
        ACTIVITE["titres_theme"] = {str(k): {str(t): float(x) for t, x in (v or {}).items()}
                                    for k, v in (d.get("titres_par_theme") or {}).items()}
        # Sans ca, un redemarrage en milieu de journee remet les lieux a zero et
        # la journee se termine en disant moins que ce qu'elle a vu.
        ACTIVITE["lieux_web"] = {str(k): float(v)
                                 for k, v in (d.get("temps_par_lieu_web_s") or {}).items()
                                 if isinstance(v, (int, float)) and v > 0}
        # ET ON REJOUE LES TITRES, quand ils en disent plus que le compteur.
        #
        # LE PLUS GRAND DES DEUX, ET DANS CE SENS-LA SEULEMENT. Les titres sont
        # le releve du jour ; le compteur ne peut qu'en retard sur eux -- une
        # mise a jour en cours de journee, une table qui apprend un site. Il ne
        # peut pas legitimement les depasser. Quand il les depasse quand meme,
        # c'est que les titres manquent (ils ne sont gardes que si la personne
        # l'a demande) : on garde alors ce qu'on avait, plutot que d'effacer une
        # mesure vraie avec un rejeu vide.
        ACTIVITE["titres_lieu"] = {str(k): {str(t): float(x) for t, x in (v or {}).items()}
                                   for k, v in (d.get("titres_par_lieu") or {}).items()}
        ACTIVITE["sites_seuls"] = {str(k): float(v)
                                   for k, v in (d.get("temps_par_site_seul_s") or {}).items()
                                   if isinstance(v, (int, float)) and v > 0}
        rejoue, seuls, par_titre = _lieux_depuis_titres(ACTIVITE["titres"])
        if sum(rejoue.values()) > sum(ACTIVITE["lieux_web"].values()):
            ACTIVITE["lieux_web"] = rejoue
            # LES TITRES SUIVENT LEUR LIEU. Les separer laisserait « 97 min de
            # video » avec, dessous, les seuls titres d'apres la mise a jour --
            # une liste qui ne fait pas son total, et qu'on lirait comme la
            # liste complete.
            ACTIVITE["titres_lieu"] = par_titre
        if sum(seuls.values()) > sum(ACTIVITE["sites_seuls"].values()):
            ACTIVITE["sites_seuls"] = seuls
        ACTIVITE["sous_themes_web"] = {str(k): {str(t): float(x) for t, x in (v or {}).items()}
                                       for k, v in (d.get("temps_par_sous_theme_web_s") or {}).items()}
        ACTIVITE["bascules"] = int(d.get("bascules_fenetre") or 0)
        ACTIVITE["actif_s"] = float(d.get("actif_minutes") or 0) * 60.0
        plage = d.get("plage") or {}
        ACTIVITE["premiere"] = str(plage.get("de") or "")
        ACTIVITE["derniere"] = str(plage.get("a") or "")
        ACTIVITE["trous"] = [t for t in (d.get("trous") or []) if isinstance(t, dict)][:40]
        a = _minutes(plage.get("a"))
        if a is not None:
            ACTIVITE["trou_depuis"] = time.mktime(time.strptime(jour, "%Y-%m-%d")) + a * 60
        if ACTIVITE["temps"]:
            minutes = round(sum(ACTIVITE["temps"].values()) / 60)
            print("Journee du %s reprise : %d min deja comptees." % (jour, minutes))
    except Exception as e:
        print("Reprise de la journee impossible :", e)


def activite_note(contexte, actif, titres_complets=False, maintenant=None):
    """Verse le temps de la fenetre precedente et ouvre la nouvelle.

    'actif' dit si l'utilisateur touchait clavier ou souris pendant la
    plage : une fenetre laissee ouverte sans personne devant ne gonfle pas
    son total, et les plages horaires ne s'etirent pas pendant les pauses.
    """
    if not ACTIVITE["active"]:
        return
    maintenant = maintenant if maintenant is not None else time.time()
    if ACTIVITE["jour"] != _jour_courant():
        sauver_activite()
        _reinit_jour(maintenant=maintenant)   # minuit : une journee neuve, rien a reprendre

    cat = categorie_activite(contexte)
    titre = (contexte or "").partition("|")[2].strip()
    avant = ACTIVITE["contexte"]
    # LE TEMPS VA AU THEME DE LA FENETRE QU'ON QUITTE, pas de celle qu'on ouvre.
    # C'est le meme raisonnement que `avant` pour la categorie, et le confondre
    # ferait glisser chaque minute d'un cran : les cinq heures de YouTube
    # atterriraient sous le theme de l'onglet ouvert juste apres.
    theme_avant = ACTIVITE.get("theme_courant")
    sous_avant = ACTIVITE.get("sous_courant")
    lieu_avant = ACTIVITE.get("lieu_courant")
    web_avant = ACTIVITE.get("web_courant", False)
    if avant:
        ecoule = min(max(0.0, maintenant - ACTIVITE["depuis"]), 180.0)
        ACTIVITE["temps"][avant] = ACTIVITE["temps"].get(avant, 0.0) + ecoule
        if theme_avant:
            ACTIVITE.setdefault("themes", {})
            ACTIVITE["themes"][theme_avant] = ACTIVITE["themes"].get(theme_avant, 0.0) + ecoule
            # CE QU'ON CONSULTE SUR INTERNET, COMPTE A PART. Une heure de
            # « creation » passee dans Blender et une heure passee a regarder un
            # tuto de Blender ne sont pas la meme heure : l'une est du travail,
            # l'autre de la consultation. Melangees, la question « de quoi parle
            # ce que je regarde » n'a plus de reponse.
            if web_avant:
                ACTIVITE.setdefault("themes_web", {})
                ACTIVITE["themes_web"][theme_avant] = ACTIVITE["themes_web"].get(theme_avant, 0.0) + ecoule
                # ET LA SOUS-CATEGORIE, quand il y en a une. Elle est rangee SOUS
                # son theme et non a plat : « recit » existe dans « influenceurs »
                # comme dans « voyage », et deux totaux additionnes sous le meme
                # nom ne voudraient plus rien dire. Le total des sous-categories
                # d'un theme est toujours <= au theme : ce qui n'a pas ete affine
                # reste compte une fois, dans le theme, et nulle part ailleurs.
                if sous_avant:
                    par_sous = ACTIVITE.setdefault("sous_themes_web", {}).setdefault(theme_avant, {})
                    par_sous[sous_avant] = par_sous.get(sous_avant, 0.0) + ecoule
            # LE TITRE DERRIERE LE THEME, quand la personne l'a demande. Un
            # camembert de themes dit « 40 min de guerre » et laisse seul devant
            # le chiffre : c'est le TITRE qui rend la mesure verifiable, et
            # verifiable veut dire refutable — on doit pouvoir regarder la liste
            # et dire « ca, ce n'etait pas de la guerre ». Sans elle, une table
            # de mots-cles devient une autorite qu'on ne peut pas contredire.
            if titres_complets and ACTIVITE["titre_courant"]:
                par = ACTIVITE.setdefault("titres_theme", {}).setdefault(theme_avant, {})
                t = _titre_onglet(ACTIVITE["titre_courant"])[:120] or ACTIVITE["titre_courant"][:120]
                par[t] = par.get(t, 0.0) + ecoule
        # LE LIEU, QUAND LE SUJET N'A RIEN SU DIRE. A part du theme et jamais
        # additionne avec lui : les deux ne repondent pas a la meme question, et
        # un total qui les melangerait raconterait qu'on sait de quoi ca parlait
        # alors qu'on sait seulement ou c'etait.
        #
        # PAS DE « and not theme_avant » ICI. Il y etait, et aucun test ne
        # faisait la difference quand on le retirait : `lieu_activite` rend deja
        # None des qu'un sujet a repondu, donc `lieu_avant` est vide dans ce cas.
        # Une deuxieme copie de la regle ne la renforce pas -- elle en fait une
        # qu'on peut changer a un endroit sans que l'autre le dise.
        if web_avant and lieu_avant:
            ACTIVITE.setdefault("lieux_web", {})
            ACTIVITE["lieux_web"][lieu_avant] = ACTIVITE["lieux_web"].get(lieu_avant, 0.0) + ecoule
            # ET LE TITRE DERRIERE LE LIEU, pour la meme raison que derriere le
            # theme : « 97 min de video » laisse seul devant le chiffre. Le
            # titre est ce qui rend la mesure REFUTABLE -- et ici il fait plus
            # que ca, il repond a la question que le lieu n'a pas su repondre.
            # « forum, 60 min » ne dit rien ; « reddit - the heart of the
            # internet, 48 min » dit qu'on a scrolle le fil, ce qui EST la
            # reponse, meme si ce n'est pas un sujet.
            if titres_complets and ACTIVITE["titre_courant"]:
                par = ACTIVITE.setdefault("titres_lieu", {}).setdefault(lieu_avant, {})
                t = _titre_onglet(ACTIVITE["titre_courant"])[:120] or ACTIVITE["titre_courant"][:120]
                par[t] = par.get(t, 0.0) + ecoule
        # ET LE SITE TOUT SEUL, quand meme le lieu n'a rien su dire.
        #
        # DERNIER PALIER DE CE QU'ON SAIT, et il n'est pas vide. « irontide »,
        # « e621 », « the registry of trades » n'ont pas de type -- mais ils ont
        # un NOM, et c'est nous qui l'avons trouve. Les compter comme « rien »
        # transformait 17 % d'une journee en trou alors qu'on pouvait les citer.
        #
        # On ne les range pas parmi les lieux : « forum » est une categorie,
        # « irontide » est un nom propre, et melanger les deux ferait croire que
        # la liste des lieux est une taxonomie ou il y aurait « irontide ».
        elif web_avant and avant:
            nom = avant[4:] if avant.startswith("web:") else avant
            if nom not in SANS_NOM:
                ACTIVITE.setdefault("sites_seuls", {})
                ACTIVITE["sites_seuls"][nom] = ACTIVITE["sites_seuls"].get(nom, 0.0) + ecoule
        if actif:
            ACTIVITE["actif_s"] += ecoule
        if titres_complets and ACTIVITE["titre_courant"]:
            # ON NETTOIE D'ABORD, ON COUPE ENSUITE. L'inverse detruit ce dont
            # le nettoyage a besoin : a 80 caracteres, « … - youtube - google
            # chrome » devient « … - youtube - g », et « g » n'est plus un nom
            # de navigateur reconnaissable. `resume_activite` renettoie a
            # l'emission, mais trop tard -- le nom coupe reste colle au titre
            # pour toujours, sur chaque ligne affichee. Meme ordre et meme
            # plafond que pour les titres d'un theme, dix lignes plus haut.
            par_titre = ACTIVITE["titres"].setdefault(avant, {})
            t = (_titre_onglet(ACTIVITE["titre_courant"])[:120]
                 or ACTIVITE["titre_courant"][:120])
            par_titre[t] = par_titre.get(t, 0.0) + ecoule
    avant_depuis = ACTIVITE["depuis"]
    ACTIVITE["depuis"] = maintenant

    # UN GEL EST UN TROU. Veille, hibernation, capot rabattu, processus fige :
    # les echantillons s'arretent sans que rien ne soit note, et au reveil
    # GetLastInputInfo dit « trois secondes d'inactivite » -- la nuit n'avait
    # laisse aucune trace. Si le precedent echantillon date de plus que le
    # seuil, l'absence a commence a cet echantillon-la. Un trou deja ouvert
    # (inactif avant la mise en veille) est garde tel quel ; et tant que
    # personne n'a ete vu au clavier depuis la reprise, l'absence est deja
    # connue (veille.plage.a, trou de reprise) : un gel n'ouvre rien, sinon sa
    # fin « couperait » la vraie nuit.
    if (avant_depuis and maintenant - avant_depuis >= SEUIL_TROU
            and not ACTIVITE["trou_depuis"] and not ACTIVITE.get("reprise")):
        ACTIVITE["trou_depuis"] = avant_depuis

    # Trou : une absence prolongee pendant que le poste reste allume. Le
    # debut est marque a la premiere mesure inactive, ferme au retour, et
    # n'est retenu qu'au-dela du seuil.
    if actif:
        ACTIVITE["reprise"] = False
        if ACTIVITE["trou_depuis"]:
            duree = maintenant - ACTIVITE["trou_depuis"]
            if duree >= SEUIL_TROU:
                ACTIVITE["trous"].append({
                    "de": _hhmm(ACTIVITE["trou_depuis"]), "a": _hhmm(maintenant),
                    "minutes": round(duree / 60.0)})
                del ACTIVITE["trous"][40:]
            ACTIVITE["trou_depuis"] = 0.0
        h = _hhmm(maintenant)
        if not ACTIVITE["premiere"]:
            ACTIVITE["premiere"] = h
        ACTIVITE["derniere"] = h
    elif not ACTIVITE["trou_depuis"] and not ACTIVITE.get("reprise"):
        ACTIVITE["trou_depuis"] = maintenant

    if cat != avant:
        if avant:
            ACTIVITE["bascules"] += 1
        ACTIVITE["contexte"] = cat
    # Le theme se lit sur la MEME fenetre que la categorie, au meme instant :
    # le temps versé plus bas doit aller au theme de ce qu'on regardait, pas de
    # ce qu'on regardait avant.
    ACTIVITE["theme_courant"] = theme_activite(contexte)
    # La sous-categorie se lit DANS le theme qu'on vient de trouver : deuxieme
    # passe, meme fenetre, meme instant. Pas de theme, pas de sous-categorie --
    # il n'y a rien a affiner.
    ACTIVITE["sous_courant"] = sous_theme_activite(ACTIVITE["theme_courant"], contexte)
    # LE LIEU, troisieme passe. La regle « il n'est lu que si le sujet s'est tu »
    # est DANS la fonction, pas ici ; on lui passe seulement le theme qu'on vient
    # de calculer, pour qu'elle ne rescanne pas les tables a chaque seconde.
    ACTIVITE["lieu_courant"] = lieu_activite(contexte, ACTIVITE["theme_courant"])
    ACTIVITE["web_courant"] = cat.startswith("web:")
    ACTIVITE["titre_courant"] = titre


def _fermer_plage(maintenant=None):
    maintenant = maintenant if maintenant is not None else time.time()
    if ACTIVITE["contexte"]:
        ecoule = min(max(0.0, maintenant - ACTIVITE["depuis"]), 180.0)
        ACTIVITE["temps"][ACTIVITE["contexte"]] = \
            ACTIVITE["temps"].get(ACTIVITE["contexte"], 0.0) + ecoule
        # Le meme temps, range une seconde fois par SUJET. Ce n'est pas un
        # doublon : « 249 min web » ne dit pas si c'etait trois heures de
        # documentaires ou trois heures de doomscroll, et le site n'a que ce
        # chiffre-la. Un instant sans theme reconnu ne compte nulle part --
        # les totaux des deux tables n'ont donc aucune raison d'etre egaux, et
        # c'est voulu : ce qui n'est pas classe ne doit pas l'etre de force.
        theme = ACTIVITE.get("theme_courant")
        if theme:
            ACTIVITE.setdefault("themes", {})
            ACTIVITE["themes"][theme] = ACTIVITE["themes"].get(theme, 0.0) + ecoule
        ACTIVITE["depuis"] = maintenant


def resume_activite():
    """Digest de la journee. C'est lui qui part au site — jamais de contenu."""
    _fermer_plage()
    temps = {k: round(v) for k, v in sorted(
        ACTIVITE["temps"].items(), key=lambda kv: -kv[1]) if v >= 1}
    resume = {
        "date": ACTIVITE["jour"] or _jour_courant(),
        "temps_par_contexte_s": temps,
        "bascules_fenetre": ACTIVITE["bascules"],
        "actif_minutes": round(ACTIVITE["actif_s"] / 60.0, 1),
        "plage": {"de": ACTIVITE["premiere"], "a": ACTIVITE["derniere"]},
        "trous": list(ACTIVITE["trous"]),
    }
    veille = sommeil_estime(ACTIVITE["jour"] or _jour_courant())
    if veille:
        resume["poste"] = veille
    # LE NOM DE L'ONGLET, PAS CELUI DE LA FENETRE. Ces titres partaient bruts,
    # avec « - Profil 1 - Microsoft Edge » colle derriere -- ce qui, a l'ecran,
    # fait tenir le nom du navigateur et pas la page. Le meme nettoyage que pour
    # `titres_par_theme` est applique ici, ET les entrees d'une journee reprise
    # (ecrites brutes par une version d'avant) se replient sur la version propre
    # au lieu de compter deux fois la meme page.
    if ACTIVITE["titres"]:
        propres = {}
        for cat, d in ACTIVITE["titres"].items():
            par = propres.setdefault(cat, {})
            for t, sec in d.items():
                nom = _titre_onglet(t) or t
                par[nom] = par.get(nom, 0.0) + sec
        resume["titres"] = {cat: {t: round(sec) for t, sec in d.items()}
                            for cat, d in propres.items()}
    themes = {k: round(v) for k, v in sorted(
        (ACTIVITE.get("themes") or {}).items(), key=lambda kv: -kv[1]) if v >= 1}
    if themes:
        resume["temps_par_theme_s"] = themes
    web = {k: round(v) for k, v in sorted(
        (ACTIVITE.get("themes_web") or {}).items(), key=lambda kv: -kv[1]) if v >= 1}
    if web:
        resume["temps_par_theme_web_s"] = web
    # LE LIEU EST UN CHAMP A PART, ET C'EST TOUT L'ENJEU. Verse dans
    # `temps_par_theme_web_s`, « video » se lirait comme « guerre » ou
    # « science » : on saurait OU c'etait et l'ecran dirait DE QUOI ca parlait.
    # C'est exactement ce qui avait coule « video » et « social » la premiere
    # fois. Un nom different oblige l'ecran a les montrer differemment.
    lieux = {k: round(v) for k, v in sorted(
        (ACTIVITE.get("lieux_web") or {}).items(), key=lambda kv: -kv[1]) if v >= 1}
    if lieux:
        resume["temps_par_lieu_web_s"] = lieux
    # ET LE SITE SEUL, dernier palier : un nom propre, pas une categorie.
    seuls = {k: round(v) for k, v in sorted(
        (ACTIVITE.get("sites_seuls") or {}).items(), key=lambda kv: -kv[1]) if v >= 1}
    if seuls:
        resume["temps_par_site_seul_s"] = seuls
    # Les titres : les DIX plus longs par theme, jamais toute la liste. Cent
    # onglets ouverts trois secondes ne disent rien de ce qu'on a regarde, et
    # les envoyer ferait grossir chaque journee sans rien apprendre a personne.
    titres = {}
    for theme, d in (ACTIVITE.get("titres_theme") or {}).items():
        gardes = sorted(d.items(), key=lambda kv: -kv[1])[:10]
        gardes = [(t, round(sec)) for t, sec in gardes if sec >= 30]
        if gardes:
            titres[theme] = dict(gardes)
    if titres:
        resume["titres_par_theme"] = titres
    # ET LES MEMES DERRIERE LES LIEUX. Meme plafond, meme plancher : ce qui
    # vaut pour verifier un sujet vaut pour savoir ce qu'il y avait dans « video ».
    parlieu = {}
    for ou, d in (ACTIVITE.get("titres_lieu") or {}).items():
        gardes = sorted(d.items(), key=lambda kv: -kv[1])[:10]
        gardes = [(t, round(sec)) for t, sec in gardes if sec >= 30]
        if gardes:
            parlieu[ou] = dict(gardes)
    if parlieu:
        resume["titres_par_lieu"] = parlieu
    # LES SOUS-CATEGORIES, rangees sous leur theme. Le meme plancher d'une
    # seconde que partout ailleurs : une sous-categorie effleuree n'est pas une
    # sous-categorie, c'est un onglet ouvert par erreur.
    sous = {}
    for theme, d in (ACTIVITE.get("sous_themes_web") or {}).items():
        gardes = {k: round(v) for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v >= 1}
        if gardes:
            sous[theme] = gardes
    if sous:
        resume["temps_par_sous_theme_web_s"] = sous
    return resume


def _date_de_ligne(ligne):
    try:
        return json.loads(ligne).get("date")
    except Exception:
        return None


def _ecrire_lignes(chemin, lignes):
    """Ecrit un fichier de lignes ENTIEREMENT OU PAS DU TOUT, comme sauver_config.

    `open(chemin, "w")` tronque d'abord et ecrit ensuite : entre les deux, le
    fichier existe et il est vide ou coupe au milieu d'une ligne. Or trois
    choses lisent activite.jsonl pendant que le fil l'ecrit -- l'envoi au site,
    le calcul des nuits, la migration -- et sur un tir de sept mille lectures
    concurrentes, presque toutes tombaient sur un fichier incomplet : une
    journee perdue, un rythme calcule sur rien, silencieusement. On ecrit a
    cote, puis on remplace : un lecteur voit l'ancien fichier ou le nouveau,
    jamais un entre-deux.
    """
    provisoire = chemin + ".part"
    try:
        with open(provisoire, "w", encoding="utf-8") as f:
            f.writelines(lignes)
        os.replace(provisoire, chemin)
        return True
    except Exception:
        try:
            if os.path.exists(provisoire):
                os.remove(provisoire)
        except Exception:
            pass
        raise


def sauver_activite():
    """Ecrit le digest du jour, une entree par jour, reecrite a chaque flush."""
    try:
        resume = resume_activite()
        lignes = []
        if os.path.exists(FICHIER_ACTIVITE):
            with open(FICHIER_ACTIVITE, encoding="utf-8") as f:
                lignes = [l for l in f if l.strip()]
        lignes = [l for l in lignes if _date_de_ligne(l) != resume["date"]]
        lignes.append(json.dumps(resume, ensure_ascii=False) + "\n")
        _ecrire_lignes(FICHIER_ACTIVITE, lignes[-90:])   # trois mois d'historique local
        return resume
    except Exception as e:
        print("Ecriture du journal d'activite impossible :", e)
        return None


def tous_les_jours_activite():
    """Tous les digests connus, un par jour, le jour courant en version vive.

    Le site en tire un seul appel de quoi remettre a jour TOUT le quantified
    self : chaque jour a deja son lever et son coucher sur disque, celui
    d'aujourd'hui est recalcule a la volee pour ne pas etre en retard sur la
    session en cours. Rendus tries par date, du plus ancien au plus recent."""
    par_date = {}
    if os.path.exists(FICHIER_ACTIVITE):
        try:
            with open(FICHIER_ACTIVITE, encoding="utf-8") as f:
                for l in f:
                    if not l.strip():
                        continue
                    try:
                        d = json.loads(l)
                    except Exception:
                        continue
                    if isinstance(d, dict) and d.get("date"):
                        par_date[d["date"]] = d
        except Exception as e:
            print("Lecture du journal d'activite impossible :", e)
    # Aujourd'hui vient de la session vive, pas de la derniere ecriture.
    vif = resume_activite()
    par_date[vif.get("date") or _jour_courant()] = vif
    return [par_date[k] for k in sorted(par_date)]


def envoyer_activite_au_site(cfg):
    """Pousse la veille et le jour a BrainDebugger. Metriques d'enveloppe
    seulement : temps, bascules, plage horaire. Aucun texte.

    La veille part AVEC le jour, relue sur le disque : la nuit qui se termine
    aujourd'hui commence par la derniere touche d'hier, et la copie d'hier sur
    le site datait du dernier envoi de la journee -- souvent des heures avant
    le coucher. Sur cette veille figee, le site fabriquait une nuit qui n'existait
    pas. Apres la migration, l'historique entier part une fois (`tout_a_pousser`).
    """
    base = str(cfg.get("pont_site", "")).strip().rstrip("/")
    if not base:
        ACTIVITE["message"] = "Aucune adresse de site."
        return False
    resume = sauver_activite() or resume_activite()
    if SYNC.get("tout_a_pousser"):
        jours = tous_les_jours_activite()
    else:
        d_veille = _digest_enregistre(_jour_avant(resume["date"]))
        jours = [d for d in (d_veille, resume) if d]
    url = base + "/api/machitool/activite"
    cle = str(cfg.get("pont_cle", "")).strip()
    entetes = {"User-Agent": "MachiToolkit/" + VERSION, "Content-Type": "application/json"}
    if cle:
        entetes["Authorization"] = "Bearer " + cle
        entetes["X-Machitool-Cle"] = cle
    try:
        # La version part avec le digest : c'est ce qui permet au site de dire
        # « ta version ne sait pas encore lire les demandes » au lieu de
        # « Machi Tool ne repond pas », qui ne dit rien de ce qu'il faut faire.
        corps = json.dumps({"jours": [dict(d, version=VERSION) for d in jours]},
                           ensure_ascii=False).encode("utf-8")
        requete = urllib.request.Request(url, data=corps, headers=entetes)
        with urllib.request.urlopen(requete, timeout=15,
                                    context=_contexte_ssl()) as reponse:
            reponse.read()
        ACTIVITE["message"] = "Journee envoyee au site."
        if SYNC.get("tout_a_pousser") and cfg.get("historique_a_pousser"):
            cfg["historique_a_pousser"] = False
            sauver_config(cfg)
        SYNC["tout_a_pousser"] = False
        SYNC["poste_envoye"] = json.dumps(resume.get("poste"), sort_keys=True)
        marquer_envoi_reussi()
        return True
    except urllib.error.HTTPError as e:
        ACTIVITE["message"] = (
            "Le site n'expose pas /api/machitool/activite." if e.code == 404
            else "Le site demande une cle (%s)." % e.code if e.code in (401, 403)
            else "Le site a repondu %s." % e.code)
        return False
    except Exception as e:
        ACTIVITE["message"] = "Envoi impossible : %s" % str(e)[:60]
        return False


def marquer_envoi_reussi():
    """Retient l'instant du dernier envoi reussi, en memoire et sur disque, pour
    que « dernier envoi » survive au redemarrage."""
    SYNC["reussi"] = time.time()
    try:
        with open(FICHIER_ENVOI, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M"))
    except Exception:
        pass


def dernier_envoi_texte():
    """La date du dernier envoi reussi, lisible, ou None si rien n'est encore parti."""
    if SYNC["reussi"]:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(SYNC["reussi"]))
    try:
        if os.path.exists(FICHIER_ENVOI):
            with open(FICHIER_ENVOI, encoding="utf-8") as f:
                return f.read().strip() or None
    except Exception:
        pass
    return None


def apercu_activite():
    """Une preview courte de ce qui partira aujourd'hui — pas un journal, juste
    de quoi reconnaitre sa journee. Rend (date, lignes)."""
    r = resume_activite()
    lignes = []
    plage = r.get("plage") or {}
    if plage.get("de"):
        lignes.append("Actif de %s a %s" % (plage["de"], plage.get("a") or "…"))
    lignes.append("%s min actives · %s bascules"
                  % (r.get("actif_minutes", 0), r.get("bascules_fenetre", 0)))
    tp = r.get("temps_par_contexte_s") or {}
    for i, (contexte, secondes) in enumerate(tp.items()):
        if i >= 3:
            break
        lignes.append("  %s — %d min" % (contexte, round(secondes / 60)))
    if len(lignes) <= 1 and not (tp or plage.get("de")):
        lignes = ["Rien encore aujourd'hui."]
    return r.get("date", ""), "\n".join(lignes)


def synchroniser_activite(cfg, minimum=120):
    """Pousse le digest du jour au site, au plus une fois par 'minimum'
    secondes. Appele quand on detecte qu'on utilise BrainDebugger : la
    donnee du jour arrive a jour sans attendre l'ecriture horaire."""
    if not (ACTIVITE["active"] and cfg.get("collecte_envoi", False)):
        return
    if time.time() - SYNC["dernier"] < minimum:
        return
    SYNC["dernier"] = time.time()
    threading.Thread(target=lambda: envoyer_activite_au_site(cfg),
                     daemon=True).start()


def _fil_activite(cfg):
    """Echantillonne la fenetre au premier plan toutes les deux secondes.

    C'est la meme lecture que pour la lumiere — GetForegroundWindow et le
    delai depuis la derniere entree — pas une captation de plus.
    """
    while MOTEUR_ACTIVITE["marche"]:
        try:
            if ACTIVITE["active"]:
                actif = secondes_inactivite() < 60
                activite_note(fenetre_active(), actif,
                              cfg.get("collecte_titres_complets", False))
                battre()   # « vivant jusqu'ici » : le filet du coucher
                # Le digest du jour sur le disque toutes les cinq minutes : c'est
                # lui qui porte la derniere touche du soir, et un arret brutal
                # ne doit pas en perdre six heures (l'envoi au site en attend six).
                if time.time() - MOTEUR_ACTIVITE.get("sauve_le", 0) > 300:
                    MOTEUR_ACTIVITE["sauve_le"] = time.time()
                    r = sauver_activite()
                    # Le lever vient d'etre mesure (le trou de reprise s'est ferme
                    # sur la premiere touche) : le site doit le savoir maintenant,
                    # pas dans six heures. On ne renvoie que si `poste` a change.
                    if (cfg.get("collecte_envoi", False)
                            and json.dumps((r or {}).get("poste"), sort_keys=True)
                            != SYNC.get("poste_envoye")):
                        synchroniser_activite(cfg, minimum=120)
        except Exception as e:
            print("Journal d'activite interrompu :", e)
        fin = time.time() + 2.0
        while MOTEUR_ACTIVITE["marche"] and time.time() < fin:
            time.sleep(0.5)


def fil_activite_vivant():
    """Le fil d'echantillonnage tourne-t-il vraiment ? Ce que le chien de garde
    interroge : un drapeau ne suffit pas, il faut que le THREAD soit la."""
    t = MOTEUR_ACTIVITE.get("fil")
    return bool(t and t.is_alive())


def demarrer_activite(cfg):
    arreter_activite()
    ACTIVITE["active"] = bool(cfg.get("collecte_active", False))
    if not ACTIVITE["active"]:
        ACTIVITE["message"] = "arretee"
        return
    _reinit_jour(reprendre=True)   # une relance ne doit pas effacer la journee
    MOTEUR_ACTIVITE["marche"] = True
    ACTIVITE["message"] = "journal en cours"
    fil = threading.Thread(target=_fil_activite, args=(cfg,), daemon=True)
    MOTEUR_ACTIVITE["fil"] = fil
    fil.start()


FICHIER_MIGRATION = os.path.join(DOSSIER, "postes_v2")


# QUAND LES TABLES CHANGENT, LE PASSE EST FAUX -- ET IL RESTE FAUX.
#
# Un digest est ecrit une fois, le soir, avec les tables de ce soir-la. Une
# table qui apprend « gmod » demain ne dira jamais rien des 35 minutes d'hier :
# elles resteront « rien ne classe » pour toujours, et l'ecran racontera un
# passe ou la personne ne faisait rien d'identifiable. Pire, une table qui se
# CORRIGE -- « kine » qui rangeait un nom de famille dans « sante » -- laisse
# l'erreur en place sur chaque jour deja ecrit.
#
# Les titres, eux, sont sur le disque depuis le premier jour. Rejouer les
# tables dessus n'invente rien : c'est la meme seconde, relue.
#
# LE NUMERO MONTE QUAND LES TABLES CHANGENT. C'est lui qui declenche la
# relecture, une fois, et pas a chaque demarrage.
CLASSEMENT_VERSION = 2


def reclasser_le_passe(cfg=None):
    """Rejoue les tables de classement sur toutes les journees gardees en local.

    LE PLUS GRAND DES DEUX, PAR CHAMP, comme pour la reprise du jour : les
    titres sont le releve, le compteur ne peut qu'etre en retard sur eux -- et
    quand il les depasse, c'est que les titres manquent (ils ne sont gardes que
    si la personne l'a demande), et on garde alors la mesure vraie.

    CE QUI N'EST PAS RETROACTIF, et il faut que ce soit ecrit : une journee
    passee SANS titres collectes ne sera jamais reclassee. On n'a pas jete
    l'information -- on ne l'a jamais eue. La relecture ne la fabriquera pas.
    """
    reglages = cfg if isinstance(cfg, dict) else CFG
    if int(reglages.get("classement_vu") or 0) >= CLASSEMENT_VERSION:
        return False
    try:
        lignes = []
        if os.path.exists(FICHIER_ACTIVITE):
            with open(FICHIER_ACTIVITE, encoding="utf-8") as f:
                lignes = [l for l in f if l.strip()]
        neuves, touchees = [], 0
        for l in lignes:
            try:
                d = json.loads(l)
            except Exception:
                neuves.append(l)
                continue
            titres = d.get("titres") or {}
            if not isinstance(titres, dict) or not titres:
                neuves.append(l)
                continue
            lieux, seuls, par_titre = _lieux_depuis_titres(titres)
            themes = {}
            for cat, dd in titres.items():
                if not str(cat).startswith("web:"):
                    continue
                for t, sec in (dd or {}).items():
                    th = theme_activite("|" + str(t))
                    if th and isinstance(sec, (int, float)) and sec > 0:
                        themes[th] = themes.get(th, 0.0) + float(sec)
            avant = json.dumps(d, sort_keys=True, ensure_ascii=False)
            for cle, calcule in (("temps_par_theme_web_s", themes),
                                 ("temps_par_lieu_web_s", lieux),
                                 ("temps_par_site_seul_s", seuls)):
                garde = {k: round(v) for k, v in sorted(calcule.items(), key=lambda kv: -kv[1])
                         if v >= 1}
                # UN THEME QUI DISPARAIT EST UNE CORRECTION, PAS UNE PERTE :
                # c'est tout l'interet de relire (« kine » qui s'en va). On
                # remplace donc des que les titres ont quelque chose a dire,
                # sans exiger que ce soit PLUS -- la regle du plus grand vaut
                # pour la reprise d'un jour en cours, ou le compteur court
                # encore, pas pour une journee close dont les titres sont le
                # releve complet.
                if garde:
                    d[cle] = garde
                else:
                    d.pop(cle, None)
            pt = {}
            for ou, dd in par_titre.items():
                gardes = [(t, round(sec)) for t, sec in
                          sorted(dd.items(), key=lambda kv: -kv[1])[:10] if sec >= 30]
                if gardes:
                    pt[ou] = dict(gardes)
            if pt:
                d["titres_par_lieu"] = pt
            else:
                d.pop("titres_par_lieu", None)
            if json.dumps(d, sort_keys=True, ensure_ascii=False) != avant:
                touchees += 1
            neuves.append(json.dumps(d, ensure_ascii=False) + "\n")
        if touchees:
            _ecrire_lignes(FICHIER_ACTIVITE, neuves)
            SYNC["tout_a_pousser"] = True
            reglages["historique_a_pousser"] = True
        reglages["classement_vu"] = CLASSEMENT_VERSION
        sauver_config(reglages)
        if touchees:
            print("Classement relu sur %d journee(s)." % touchees)
        return bool(touchees)
    except Exception as e:
        print("Relecture du classement impossible :", e)
        return False


def migrer_postes(cfg=None):
    """Une fois par installation : recalculer `poste` de tout l'historique local.

    Les digests d'avant portaient {reveil: '00:00'} sans coucher -- le repli sur
    la premiere minute du fichier civil. Laisses tels quels, ils amorceraient le
    rythme sur des nuits inventees et resteraient en base avec un lever 00:00.

    Deux passes : sans rythme, puis avec le rythme que la premiere vient de
    rendre lisible. La seconde passe ne relit PAS les devinettes de la premiere
    -- celles-ci sortent marquees `incertain` et _rythme_connu les saute -- donc
    elle corrige la premiere au lieu de la confirmer. Sans cette marque, la
    boucle etait fermee : la journee de bureau elue en passe 1 devenait le
    rythme lu en passe 2, qui reelisait la journee de bureau.

    Puis tout part au site en un envoi, qui purge les mesures fantomes de
    chaque date.
    """
    if os.path.exists(FICHIER_MIGRATION):
        return False
    try:
        lignes = []
        if os.path.exists(FICHIER_ACTIVITE):
            with open(FICHIER_ACTIVITE, encoding="utf-8") as f:
                lignes = [l for l in f if l.strip()]
        for rythme in (None, "auto"):
            digests = []
            for l in lignes:
                try:
                    d = json.loads(l)
                except Exception:
                    continue
                if not isinstance(d, dict) or not d.get("date"):
                    continue
                poste = sommeil_estime(d["date"], plage=d.get("plage") or {},
                                       trous=d.get("trous") or [], rythme=rythme)
                d.pop("poste", None)
                if poste:
                    d["poste"] = poste
                digests.append(d)
            lignes = [json.dumps(d, ensure_ascii=False) + "\n" for d in digests]
            if lignes:
                _ecrire_lignes(FICHIER_ACTIVITE, lignes)
        with open(FICHIER_MIGRATION, "w", encoding="utf-8") as f:
            f.write(VERSION)
        print("Nuits recalculees sur %d journees." % len(lignes))
        if lignes:
            # LE MARQUEUR DIT « C'EST RECALCULE », PAS « C'EST ARRIVE AU SITE ».
            # `tout_a_pousser` ne vivait qu'en memoire : le fichier postes_v2
            # etant deja ecrit, une fermeture avant le premier envoi reussi
            # perdait la consigne pour toujours -- le recalcul ne repartait
            # plus, et le site gardait ses vieilles nuits fausses sans que rien
            # ne le signale. La consigne va donc sur le disque, avec les
            # reglages, et ne s'efface qu'a l'envoi reussi.
            SYNC["tout_a_pousser"] = True
            reglages = cfg if isinstance(cfg, dict) else CFG
            reglages["historique_a_pousser"] = True
            sauver_config(reglages)
        return True
    except Exception as e:
        print("Recalcul des nuits impossible :", e)
        return False


def ouvrir_journal_du_poste(cfg):
    """Le lancement du journal, DANS CET ORDRE : le coucher perdu, ce
    demarrage, puis seulement le fil d'echantillonnage.

    Le fil ecrit battement.txt a son premier tour. Lance avant, il pouvait
    ecraser le dernier battement de la nuit pendant que fermer_session_perdue
    le lisait : l'extinction deduite tombait a l'heure de l'allumage (le
    coucher devenait le lever), ou nulle part (fichier vide). Intermittent,
    donc invisible jusqu'au jour ou une nuit manque.

    Puis un premier envoi tout de suite -- la veille complete et le jour, ou
    tout l'historique la premiere fois (migrer_postes) -- pour que le site
    n'attende pas six heures ; le fil renverra des que le lever est mesure, et
    veille_activite repasse deux minutes plus tard.
    """
    if cfg.get("collecte_active", False) and not SESSION["notee"]:
        SESSION["notee"] = True
        fermer_session_perdue()
        noter_session("demarrage")     # l'app demarre avec Windows
    # La migration reecrit activite.jsonl : avant le fil, qui l'ecrit aussi.
    if cfg.get("collecte_active", False):
        migrer_postes(cfg)
        # Apres la migration des postes, qui reecrit le meme fichier.
        reclasser_le_passe(cfg)
    # Une migration d'un lancement precedent dont l'envoi n'a jamais abouti :
    # la consigne a survecu sur le disque, elle repart ici.
    if cfg.get("historique_a_pousser"):
        SYNC["tout_a_pousser"] = True
    demarrer_activite(cfg)
    if ACTIVITE["active"]:
        synchroniser_activite(cfg, minimum=0)


def arreter_activite():
    if MOTEUR_ACTIVITE["marche"]:
        sauver_activite()
    MOTEUR_ACTIVITE["marche"] = False
    MOTEUR_ACTIVITE["fil"] = None
    ACTIVITE["active"] = False


def veiller_sur_activite(cfg):
    """LE CHIEN DE GARDE. Le journal doit tourner tant que l'application vit.

    Le fil attrape ses exceptions a chaque tour, mais il n'attrape pas tout :
    une erreur hors du try (l'import d'un module qui manque a chaud, une
    coupure memoire) tuerait le thread en silence. La collecte s'arreterait
    sans que rien ne le dise -- et on ne le verrait que des semaines plus tard,
    devant un mois de journal vide.

    On le relance donc, et on le NOTE : `redemarrages` se lit dans les reglages.
    """
    if not cfg.get("collecte_active", False) or not ACTIVITE["active"]:
        return False
    if fil_activite_vivant():
        return False
    MOTEUR_ACTIVITE["redemarrages"] = MOTEUR_ACTIVITE.get("redemarrages", 0) + 1
    MOTEUR_ACTIVITE["marche"] = True
    fil = threading.Thread(target=_fil_activite, args=(cfg,), daemon=True)
    MOTEUR_ACTIVITE["fil"] = fil
    fil.start()
    ACTIVITE["message"] = "journal repris (%d)" % MOTEUR_ACTIVITE["redemarrages"]
    print("Fil d'activite relance par le chien de garde.")
    return True



def couleur_cible(cfg, contexte):
    for regle in cfg.get("regles", []):
        for mot in regle.get("mots", []):
            if mot and mot.lower() in contexte:
                return hex_vers_rgb(regle["couleur"]), regle.get("nom", "?")
    return hex_vers_rgb(cfg.get("couleur_defaut", "#8B5CF6")), "Defaut"


# ==========================================================================
#  Capture d'ecran
# ==========================================================================

_local = threading.local()

# Un seul fil pour la capture. La boucle de la guirlande attend chaque image
# avant de demander la suivante : le pool par defaut n'accelere donc rien, il
# multiplie seulement les contextes de peripherique -- les caches de capture
# sont thread-local, un jeu par fil, et personne ne les rend jamais.
EXECUTEUR_CAPTURE = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="capture")


def objets_gdi():
    """(objets GDI, objets USER) du processus, ou (-1, -1) hors Windows.

    Le plafond par defaut est de 10 000 de chaque. C'est la seule mesure qui
    tranche entre « le bureau a disparu » et « le processus n'a plus un seul
    handle » : les libelles d'erreur, eux, mentent (pywin32 rend NULL sans
    poser d'erreur, et mss affiche un code perime que ctypes a restaure).
    """
    try:
        import ctypes
        # Prototypes poses ICI, sur des WinDLL a nous : ctypes passerait sinon
        # le pseudo-handle du processus (-1) sur 32 bits, et la mesure serait
        # fausse sur un Windows 64 bits -- c'est-a-dire partout. Meme raison
        # que dans `_apis_ecran` : on ne regle jamais les prototypes du
        # `ctypes.windll.*` partage, un autre appel de l'application s'en sert.
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.GetCurrentProcess.argtypes = []
        u32.GetGuiResources.restype = ctypes.c_uint
        u32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        moi = k32.GetCurrentProcess()
        return int(u32.GetGuiResources(moi, 0)), int(u32.GetGuiResources(moi, 1))
    except Exception:
        return -1, -1


_CAPTURE_DIT = set()


def signaler_capture(quoi, e):
    """Une ligne par panne, pas une par image.

    UN ENSEMBLE, ET PAS LA DERNIERE PHRASE : dans le journal reel, DEUX
    phrases alternaient -- le chemin GDI echouait, puis le repli mss
    echouait a son tour, image apres image. Se souvenir seulement de la
    precedente ne deduplique donc rien du tout : chacune differe toujours de
    celle d'avant, et les deux repartent huit fois par seconde.

    L'ensemble se vide au retablissement (voir `echec_capture`) : une panne
    qui revient plus tard se redit, elle ne se tait pas pour la vie du
    processus.

    Et le compte d'objets du processus part avec. C'est la seule mesure qui
    tranche entre « le bureau a disparu » et « il n'y a plus un handle » --
    les libelles d'erreur, eux, mentent.
    """
    ligne = "%s : %s" % (quoi, e)
    if ligne in _CAPTURE_DIT:
        return
    _CAPTURE_DIT.add(ligne)
    g, u = objets_gdi()
    print("%s | objets du processus : GDI %s, USER %s (plafond 10000)"
          % (ligne, g, u))


def _capteur():
    import mss
    if not hasattr(_local, "sct"):
        _local.sct = mss.mss()
    return _local.sct


def nombre_ecrans():
    try:
        return max(0, len(_capteur().monitors) - 1)
    except Exception:
        return 0


def _ecran_actif(sct):
    rect = rectangle_fenetre_active()
    if not rect:
        return 1
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    for i, m in enumerate(sct.monitors[1:], start=1):
        if m["left"] <= cx < m["left"] + m["width"] and \
           m["top"] <= cy < m["top"] + m["height"]:
            return i
    return 1


def _vignette_gdi(zone, colonnes, lignes):
    """Reduit une zone de l'ecran a colonnes x lignes pixels, cote Windows.

    C'est ce qui separe 30 images par seconde de 5. Recopier un ecran 4K,
    c'est 33 Mo par image a faire transiter puis a moyenner en Python. Ici
    GDI fait la reduction dans le pilote et on ne relit que la vignette,
    quelques centaines d'octets. Le mode HALFTONE moyenne vraiment les
    pixels au lieu d'en prelever un sur mille : sans lui, un curseur qui
    passe suffirait a faire sauter la couleur.

    Les contextes de peripherique sont gardes d'une image sur l'autre :
    les recreer coute plus cher que la capture elle-meme.

    Renvoie une liste de (r, v, b), ou None si GDI n'est pas disponible.
    """
    try:
        import win32gui, win32ui, win32con
    except ImportError:
        return None

    garde = getattr(_local, "gdi", None)
    if garde is None or garde["taille"] != (colonnes, lignes):
        if garde is not None:
            _liberer_gdi(garde)
        # La garde se remplit AU FUR ET A MESURE : ce qui a ete obtenu avant
        # l'echec doit pouvoir etre rendu. L'ancienne version ne rattrapait
        # que le contexte d'ecran ; un echec plus tardif -- le bitmap qui ne
        # s'alloue plus -- laissait le contexte memoire derriere lui, un par
        # image, jusqu'a epuisement du quota du processus.
        neuf = {"taille": (colonnes, lignes)}
        try:
            neuf["fenetre"] = win32gui.GetDesktopWindow()
            neuf["dc"] = win32gui.GetWindowDC(neuf["fenetre"])
            neuf["source"] = source = win32ui.CreateDCFromHandle(neuf["dc"])
            neuf["memoire"] = memoire = source.CreateCompatibleDC()
            neuf["image"] = image = win32ui.CreateBitmap()
            image.CreateCompatibleBitmap(source, colonnes, lignes)
            memoire.SelectObject(image)
            garde = neuf
            _local.gdi = garde
        except Exception as e:
            _liberer_gdi(neuf)
            signaler_capture("Capture GDI indisponible", e)
            _local.gdi = None
            return None

    try:
        try:
            garde["memoire"].SetStretchBltMode(win32con.HALFTONE)
        except Exception:
            garde["memoire"].SetStretchBltMode(win32con.COLORONCOLOR)
        garde["memoire"].StretchBlt(
            (0, 0), (colonnes, lignes),
            garde["source"], (zone["left"], zone["top"]),
            (zone["width"], zone["height"]), win32con.SRCCOPY)
        octets = garde["image"].GetBitmapBits(True)
    except Exception as e:
        # Un changement de resolution ou une session verrouillee invalide
        # les contextes : on les jette, la prochaine image les refera.
        signaler_capture("Capture GDI perdue", e)
        _liberer_gdi(garde)
        _local.gdi = None
        return None

    # GetBitmapBits rend du BGRA, ligne par ligne.
    return [(octets[i + 2], octets[i + 1], octets[i])
            for i in range(0, len(octets), 4)]


def _liberer_gdi(garde):
    """Rend les TROIS ressources de la garde, et dans cet ordre-la.

    LE BITMAP N'ETAIT RENDU PAR PERSONNE. On rendait le contexte memoire et
    le contexte d'ecran, jamais l'objet bitmap. Chaque garde refaite en
    laissait donc un derriere elle -- huit par seconde quand la capture rate
    en boucle. Le quota de 10 000 objets GDI du processus se vide en vingt
    minutes, et ensuite plus AUCUN contexte ne s'obtient nulle part : tkinter
    compris, qui ne verifie pas ses retours GDI, ouvre alors une fenetre
    qu'il ne peut pas peindre et meurt dessus. C'est la panne rapportee, et
    la pile C du journal la nomme -- violation d'acces dans mainloop.

    CE QUI RESTE UNE HYPOTHESE, ET QU'ON NE PEUT PAS VERIFIER D'ICI : que le
    ramasse-miettes de pywin32 ne rende pas ce handle tout seul. S'il le
    rendait deja, ce DeleteObject-ci porterait sur un handle deja libere et
    se contenterait d'echouer. Le risque est donc dissymetrique -- ne rien
    faire tue l'application, en faire trop ne coute qu'un appel refuse -- et
    c'est ce qui tranche. Le compteur d'objets pose dans le journal dira
    lequel des deux mondes est le vrai.

    L'ordre : un bitmap encore selectionne dans un contexte ne se detruit
    pas, donc apres DeleteDC. La garde peut etre incomplete (echec en cours
    de construction), d'ou les .get.
    """
    if not garde:
        return
    try:
        garde["memoire"].DeleteDC()
    except Exception:
        pass
    try:
        import win32gui
        win32gui.DeleteObject(garde["image"].GetHandle())
    except Exception:
        pass
    try:
        import win32gui
        if garde.get("dc"):
            win32gui.ReleaseDC(garde["fenetre"], garde["dc"])
    except Exception:
        pass


def _vignette_mss(zone, colonnes, lignes):
    """Repli portable : capture complete puis reduction par Pillow."""
    from PIL import Image
    brut = _capteur().grab(zone)
    im = Image.frombytes("RGB", brut.size, brut.rgb).resize(
        (colonnes, lignes), Image.BILINEAR)
    return list(im.getdata())


_RAMPE = {"ts": 0.0, "lut": None}
_APIS = {"gdi": None, "user": None, "pret": False}


def _apis_ecran():
    """Handles GDI/User32 A NOUS (WinDLL prives), avec leurs prototypes reglons
    UNE fois. On ne touche jamais a ctypes.windll.* partage : regler les
    prototypes de ces fonctions-la globalement pourrait deranger un autre appel
    de l'application. Rend (gdi, user) ou (None, None) hors Windows / en echec."""
    if _APIS["pret"]:
        return _APIS["gdi"], _APIS["user"]
    _APIS["pret"] = True
    if os.name != "nt":
        return None, None
    try:
        import ctypes
        gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        user = ctypes.WinDLL("user32", use_last_error=True)
        # Handles = pointeurs : sans ces types, ctypes tronque a 32 bits en 64
        # bits et l'appel echoue (un HDC tronque n'est plus valide).
        gdi.CreateDCW.restype = ctypes.c_void_p
        gdi.CreateDCW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                  ctypes.c_wchar_p, ctypes.c_void_p]
        gdi.DeleteDC.restype = ctypes.c_int
        gdi.DeleteDC.argtypes = [ctypes.c_void_p]
        gdi.GetDeviceGammaRamp.restype = ctypes.c_int
        gdi.GetDeviceGammaRamp.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user.GetDC.restype = ctypes.c_void_p
        user.GetDC.argtypes = [ctypes.c_void_p]
        user.ReleaseDC.restype = ctypes.c_int
        user.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user.FindWindowW.restype = ctypes.c_void_p
        user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        _APIS["gdi"], _APIS["user"] = gdi, user
    except Exception:
        _APIS["gdi"], _APIS["user"] = None, None
    return _APIS["gdi"], _APIS["user"]


def rampe_gamma():
    """Les trois tables (256 entrees, 0-255) de la rampe gamma de l'affichage.

    C'est par elle que f.lux et les filtres qui ecrivent la rampe (Redshift,
    SunsetScreen...) jaunissent l'ecran : ils n'ecrivent pas des pixels jaunes,
    ils inflechissent la rampe du GPU, APRES le tampon d'image que la capture lit.
    La relire permet de teinter la couleur echantillonnee comme l'oeil la voit.
    (Windows Night Light, lui, passe par un pipeline d'affichage separe : il n'ecrit
    pas cette rampe et n'est donc pas suivi ici.)

    Relue au plus une fois par seconde -- elle bouge lentement. None hors Windows
    ou si le pilote la refuse.

    POURQUOI CreateDC("DISPLAY") ET PAS SEULEMENT GetDC(0).

    GetDC(0) rend un contexte d'ecran « commun » qui, tant que personne n'a
    re-pose la rampe, renvoie souvent la rampe IDENTITE -- meme quand f.lux
    jaunit deja l'ecran. C'est le fameux « rien ne bouge tant que je ne redemarre
    pas f.lux » : au redemarrage f.lux rappelle SetDeviceGammaRamp, et l'espace
    d'un instant GetDC(0) reflete enfin la vraie rampe. CreateDC("DISPLAY"), lui,
    ouvre un contexte SUR LE PILOTE d'affichage : il rend la rampe ACTIVE, celle
    que f.lux tient, qu'il vienne de demarrer ou qu'il tourne depuis des heures.
    On l'essaie donc en premier, et GetDC(0) ne sert plus que de repli.

    Limite connue : on lit la rampe de l'ecran PRINCIPAL. Sur plusieurs ecrans
    aux filtres differents, la teinte suivie est celle du principal, pas forcement
    celle de l'ecran capture. Cas rare (un filtre couvre en general tous les
    ecrans pareil) et sans regression : au pire, pas de compensation."""
    if os.name != "nt":
        return None
    maintenant = time.time()
    # Le cache porte sur l'HORODATAGE, pas sur la presence d'une LUT : un echec
    # (rampe illisible : HDR, RDP, certains pilotes) doit lui aussi tenir une
    # seconde, sinon on refait des appels GDI a chaque image, en continu.
    if _RAMPE["ts"] and maintenant - _RAMPE["ts"] < 1.0:
        return _RAMPE["lut"]
    _RAMPE["ts"] = maintenant
    try:
        import ctypes
        gdi32, user32 = _apis_ecran()
        if not gdi32 or not user32:
            _RAMPE["lut"] = None
            return None

        brut = (ctypes.c_uint16 * 256 * 3)()
        ok = 0

        # 1) Le contexte du pilote d'affichage : la rampe ACTIVE de f.lux.
        hdc = gdi32.CreateDCW("DISPLAY", None, None, None)
        if hdc:
            try:
                ok = gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(brut))
            finally:
                gdi32.DeleteDC(hdc)

        # 2) Repli : le contexte d'ecran commun, quand CreateDC est refuse.
        if not ok:
            hdc = user32.GetDC(None)
            if hdc:
                try:
                    ok = gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(brut))
                finally:
                    user32.ReleaseDC(None, hdc)

        if not ok:
            _RAMPE["lut"] = None
            return None
        lut = tuple([brut[c][i] >> 8 for i in range(256)] for c in range(3))
        _RAMPE["lut"] = lut
        return lut
    except Exception:
        _RAMPE["lut"] = None
        return None


def _kelvin_rgb(k):
    """Le blanc d'un corps noir a k kelvin, en (r, v, b) 0-1 (Tanner Helland).
    6500 K vaut a peu pres (1, 1, 1) ; 3400 K, (1, 0.71, 0.42)."""
    t = max(1000.0, min(40000.0, float(k))) / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    v = (99.4708025861 * math.log(t) - 161.1195681661) if t <= 66 \
        else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255.0 if t >= 66 else 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    return tuple(max(0.0, min(255.0, x)) / 255.0 for x in (r, v, b))


def gains_kelvin(k_ecran, k_led=6500.0, force=1.0):
    """Les gains (r, v, b) qui, sur une guirlande dont le blanc est a k_led,
    montrent le blanc de l'ecran a k_ecran. Jamais au-dessus de 1 : on retire du
    bleu, on n'invente pas de rouge. `force` exagere (> 1) ou attenue (< 1)."""
    e, l = _kelvin_rgb(k_ecran), _kelvin_rgb(k_led)
    g = [e[i] / max(0.02, l[i]) for i in range(3)]
    m = max(g) or 1.0
    return tuple((x / m) ** max(0.1, float(force)) for x in g)


_FLUX = {"ts": 0.0, "val": None}


def _flux_reglages():
    """Ce que f.lux dit de lui-meme dans le registre (HKCU\\Software\\Michael
    Herf\\flux\\Preferences) : ses temperatures et sa position. Les noms exacts
    changent d'une version a l'autre, alors on lit TOUTES les valeurs et on
    reconnait par le nom (night/day/late, lat/long) et par la plage. Au moindre
    doute, la valeur manque, et les defauts de f.lux (6500 le jour, 3400 la
    nuit) prennent le relais."""
    out = {"nuit": None, "jour": None, "tard": None, "lat": None, "lon": None}
    if os.name != "nt":
        return out
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Michael Herf\flux\Preferences") as cle:
            i = 0
            while True:
                try:
                    nom, val, _t = winreg.EnumValue(cle, i)
                except OSError:
                    break
                i += 1
                n = str(nom).lower()
                try:
                    x = float(val)
                except Exception:
                    continue
                if "lat" in n and -90 <= x <= 90:
                    out["lat"] = x
                elif ("lon" in n or "lng" in n) and -180 <= x <= 180:
                    out["lon"] = x
                elif 1000 <= x <= 6600 and "bri" not in n:
                    if "night" in n or "nuit" in n:
                        out["nuit"] = x
                    elif "day" in n or "jour" in n:
                        out["jour"] = x
                    elif "late" in n or "bed" in n:
                        out["tard"] = x
    except Exception:
        pass
    return out


def _elevation_soleil(lat, lon, quand=None):
    """Hauteur du soleil en degres, approximation NOAA (a un degre pres) :
    assez pour savoir si c'est le jour, la nuit, ou entre les deux."""
    quand = quand if quand is not None else time.time()
    jours = quand / 86400.0 - 10957.5                 # depuis J2000
    g = math.radians((357.529 + 0.98560028 * jours) % 360)
    q = (280.459 + 0.98564736 * jours) % 360
    lon_sol = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    obl = math.radians(23.439 - 0.00000036 * jours)
    decl = math.asin(math.sin(obl) * math.sin(lon_sol))
    ra = math.degrees(math.atan2(math.cos(obl) * math.sin(lon_sol), math.cos(lon_sol)))
    gmst = (18.697374558 + 24.06570982441908 * jours) % 24
    ha = math.radians((gmst * 15 + lon - ra) % 360)
    la = math.radians(lat)
    h = math.asin(math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha))
    return math.degrees(h)


def kelvin_attendu_flux():
    """La temperature que f.lux DOIT tenir maintenant, d'apres ses reglages et
    l'heure -- quand sa rampe est illisible et qu'on ne peut plus la mesurer.
    None si f.lux ne tourne pas. Cache dix secondes."""
    maintenant = time.time()
    if _FLUX["val"] is not None and maintenant - _FLUX["ts"] < 10.0:
        return _FLUX["val"]
    _FLUX["ts"] = maintenant
    k = None
    try:
        if _flux_tourne():
            p = _flux_reglages()
            jour = p["jour"] or 6500.0
            nuit = p["nuit"] or 3400.0
            tard = p["tard"]
            heure = time.localtime().tm_hour + time.localtime().tm_min / 60.0
            if p["lat"] is not None and p["lon"] is not None:
                el = _elevation_soleil(p["lat"], p["lon"], maintenant)
                # Plein jour au-dessus de 6 degres, pleine nuit sous -6 : entre les deux, la transition.
                part = max(0.0, min(1.0, (6.0 - el) / 12.0))
            else:
                # Sans position : jour de 7 h a 19 h, nuit de 21 h a 6 h, une heure de transition.
                if 7 <= heure < 19:
                    part = 0.0
                elif heure >= 20 or heure < 6:
                    part = 1.0
                elif 19 <= heure < 20:
                    part = heure - 19
                else:
                    part = 1.0 - (heure - 6)
            k = jour + (nuit - jour) * part
            if tard and (heure >= 23 or heure < 5):
                k = min(k, tard)
    except Exception:
        k = None
    _FLUX["val"] = k
    return k


def kelvin_ecran(cfg):
    """La temperature de ce que l'ecran montre, et d'ou on la tient :
    ('rampe', K) quand la rampe gamma le dit, ('flux', K) quand f.lux tourne
    sans rampe lisible, (None, 6500) sinon."""
    if cfg.get("ecran_suit_filtre_bleu", True):
        lut = rampe_gamma()
        if lut:
            r, b = max(1, lut[0][255]), lut[2][255]
            if b / r < 0.97:
                return "rampe", _kelvin_du_blanc(lut[0][255], lut[1][255], lut[2][255])
        k = kelvin_attendu_flux()
        if k:
            return "flux", k
    return None, 6500.0


def adapter_couleur_ecran(rgb, cfg):
    """Teinte une couleur (0-255) comme l'OEIL la voit sur la guirlande.

    Trois choses, dans l'ordre : le filtre de lumiere bleue (la rampe gamma
    quand elle se lit, sinon ce que f.lux doit tenir d'apres ses reglages et
    l'heure), le blanc de la guirlande elle-meme (une LED tire au bleu : a
    couleur egale, elle parait plus froide que l'ecran), et la balance manuelle.
    Tout passe par des kelvins et un seul jeu de gains, pousse par
    `ecran_filtre_force`."""
    r, v, b = rgb
    source, k = kelvin_ecran(cfg)
    k_led = float(cfg.get("led_blanc_kelvin", 7500) or 6500)
    force = float(cfg.get("ecran_filtre_force", 1.3) or 1.0)
    if source or abs(k_led - 6500.0) > 50:
        gr, gv, gb = gains_kelvin(k, k_led, force if source else 1.0)
        r, v, b = r * gr, v * gv, b * gb
    temp = float(cfg.get("ecran_balance_temp", 0.0) or 0.0)
    tint = float(cfg.get("ecran_balance_tint", 0.0) or 0.0)
    if temp or tint:
        # Chaud monte le rouge et baisse le bleu ; magenta monte rouge et bleu et
        # baisse le vert. Gains doux : au plus +-30 %.
        gr = 1.0 + 0.30 * temp + 0.15 * tint
        gv = 1.0 - 0.15 * tint
        gb = 1.0 - 0.30 * temp + 0.15 * tint
        r, v, b = r * gr, v * gv, b * gb
    return (int(max(0, min(255, round(r)))),
            int(max(0, min(255, round(v)))),
            int(max(0, min(255, round(b)))))


# --------------------------------------------------------------------------
#  CE QUE MACHI TOOL VOIT DU FILTRE DE LUMIERE BLEUE.
#
#  De quoi rendre lisible « est-ce qu'il trouve f.lux, est-ce qu'il s'adapte,
#  et de combien ». Trois sources, du plus sur au moins sur :
#    - la RAMPE GAMMA (f.lux, Redshift, SunsetScreen) : la seule qu'on sait
#      COMPENSER, parce qu'elle porte la vraie teinte de l'affichage ;
#    - le PROCESSUS f.lux (sa fenetre cachee de classe « flux ») : s'il tourne
#      mais que la rampe est neutre, c'est le pilote qui ne la rend pas, et il
#      faut le DIRE plutot que laisser croire a une panne ;
#    - Windows NIGHT LIGHT (registre) : autre pipeline, non compense — on le
#      signale pour que la balance manuelle prenne le relais.
# --------------------------------------------------------------------------

_DIAG_FILTRE = {"ts": 0.0, "val": None}


def _kelvin_du_blanc(r, v, b):
    """Temperature approximative du blanc que la rampe produit. Neutre (~6500 K)
    quand le bleu tient le rouge ; plus le bleu tombe, plus c'est chaud. Estimation
    d'indicateur, arrondie a 50 K — pas une mesure colorimetrique."""
    r = max(1, r)
    bl = max(0.0, min(1.0, b / r))          # 1 = neutre, plus bas = plus chaud
    k = 2500 + bl * 4000.0
    return int(round(max(1900.0, min(6600.0, k)) / 50.0) * 50)


def _flux_tourne():
    """Vrai si f.lux tourne : sa fenetre cachee de classe « flux », ou, plus
    surement, son processus (flux.exe) -- la classe de fenetre a change d'une
    version a l'autre, le nom du processus non. Cache cinq secondes : on ne
    parcourt pas la liste des processus a chaque image."""
    maintenant = time.time()
    if _FLUX_PROC["ts"] and maintenant - _FLUX_PROC["ts"] < 30.0:
        return _FLUX_PROC["val"]
    _FLUX_PROC["ts"] = maintenant
    trouve = False
    try:
        _gdi, user = _apis_ecran()
        if user and user.FindWindowW("flux", None):
            trouve = True
    except Exception:
        pass
    if not trouve and os.name == "nt":
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info.get("name") or "").lower() in ("flux.exe", "flux"):
                    trouve = True
                    break
        except Exception:
            pass
    _FLUX_PROC["val"] = trouve
    return trouve


_FLUX_PROC = {"ts": 0.0, "val": False}


def _nightlight_actif():
    """Best-effort : Windows Night Light est-il ALLUME ? Il vit dans un blob du
    registre (CloudStore). Quand il est actif, le blob insere la paire 0x10 0x00
    juste apres l'horodatage. Au moindre doute on rend False — mieux vaut ne rien
    dire que mentir sur un signe."""
    if os.name != "nt":
        return False
    try:
        import winreg
        chemin = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\CloudStore\Store\Cache"
                  r"\DefaultAccount\$$windows.data.bluelightreduction."
                  r"bluelightreductionstate\Current")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin) as cle:
            data, _ = winreg.QueryValueEx(cle, "Data")
        data = bytes(data)
        return data[18:28].find(b"\x10\x00") != -1
    except Exception:
        return False


def diag_filtre_ecran(cfg):
    """Ce que Machi Tool detecte du filtre de lumiere bleue, pour l'afficher.

    Rend un dict : suivi (option cochee), source ('filtre'|'nightlight'|None),
    kelvin (approx), chaud_pct (de combien on rechauffe), compense (adapte-t-on
    vraiment la LED), flux (f.lux tourne), nightlight. Cache une seconde : pas
    d'appel registre a chaque image."""
    maintenant = time.time()
    if _DIAG_FILTRE["val"] is not None and maintenant - _DIAG_FILTRE["ts"] < 1.0:
        return _DIAG_FILTRE["val"]
    _DIAG_FILTRE["ts"] = maintenant
    d = {"suivi": bool(cfg.get("ecran_suit_filtre_bleu", True)),
         "source": None, "kelvin": None, "chaud_pct": 0,
         "compense": False, "flux": False, "nightlight": False}
    try:
        lut = rampe_gamma()
        if lut:
            r = max(1, lut[0][255])
            b = lut[2][255]
            if b / r < 0.97:                 # le bleu est abaisse : un filtre agit
                d["source"] = "filtre"
                d["chaud_pct"] = int(round((1 - b / r) * 100))
                d["kelvin"] = _kelvin_du_blanc(lut[0][255], lut[1][255], lut[2][255])
                d["compense"] = d["suivi"]
        d["flux"] = _flux_tourne()
        d["nightlight"] = _nightlight_actif()
        if d["source"] is None and d["flux"]:
            k = kelvin_attendu_flux()
            if k:
                d["source"] = "flux"
                d["kelvin"] = int(round(k / 50.0) * 50)
                g = gains_kelvin(k, 6500.0)
                d["chaud_pct"] = int(round((1 - g[2]) * 100))
                d["compense"] = d["suivi"]
        if d["source"] is None and d["nightlight"]:
            d["source"] = "nightlight"
        d["led_kelvin"] = int(cfg.get("led_blanc_kelvin", 7500) or 6500)
        d["force"] = float(cfg.get("ecran_filtre_force", 1.3) or 1.0)
    except Exception:
        pass
    _DIAG_FILTRE["val"] = d
    return d


def texte_filtre_ecran(d):
    """Une phrase pour l'indicateur, et vrai si Machi Tool compense vraiment."""
    if not d.get("suivi"):
        return ("Suivi des filtres desactive.", False)
    suffixe = " (x%.1f, guirlande a %d K)" % (float(d.get("force") or 1.0), int(d.get("led_kelvin") or 6500))
    if d.get("source") == "filtre":
        t = "Filtre ecran suivi (rampe lue) - ~%d K, rechauffe %d%%%s" % (
            d.get("kelvin") or 0, d.get("chaud_pct") or 0, suffixe)
        return (t, bool(d.get("compense")))
    if d.get("source") == "flux":
        t = "f.lux tourne, rampe illisible : suivi d'apres ses reglages et l'heure - ~%d K, rechauffe %d%%%s" % (
            d.get("kelvin") or 0, d.get("chaud_pct") or 0, suffixe)
        return (t, bool(d.get("compense")))
    if d.get("flux"):
        return ("f.lux tourne, mais ni sa rampe ni ses reglages ne se lisent - "
                "teinte non suivie (regle la balance a la main).", False)
    if d.get("nightlight"):
        return ("Windows Night Light actif - autre pipeline, non suivi "
                "(regle la balance a la main).", False)
    return ("Aucun filtre de lumiere bleue detecte.", False)


def couleur_ecran(source, boost, colonnes=4):
    """((r, v, b), luminance 0-1, numero d'ecran) ou None.

    La moyenne brute d'un ecran donne toujours un gris sale. On fait donc une
    moyenne circulaire des teintes ponderee par saturation x valeur : les
    pixels ternes et le noir ne votent presque pas, les zones colorees
    dominent. La luminance reste une moyenne simple."""
    try:
        sct = _capteur()
        index = _ecran_actif(sct) if source == "actif" else int(source)
        index = max(1, min(index, len(sct.monitors) - 1))
        zone = sct.monitors[index]

        colonnes = max(2, min(32, int(colonnes)))
        lignes = max(2, int(round(colonnes * zone["height"] / max(1, zone["width"]))))

        pixels = _vignette_gdi(zone, colonnes, lignes)
        if not pixels:
            pixels = _vignette_mss(zone, colonnes, lignes)

        sx = sy = poids = sat_tot = val_tot = 0.0
        for r, v, b in pixels:
            h, s, val = colorsys.rgb_to_hsv(r / 255, v / 255, b / 255)
            w = (s ** 1.5) * val
            angle = 2 * math.pi * h
            sx += math.cos(angle) * w
            sy += math.sin(angle) * w
            sat_tot += s * w
            poids += w
            val_tot += val

        luminance = val_tot / len(pixels)
        # Le seuil porte sur la moyenne par pixel, pas sur la somme : la
        # vignette est passee de 1296 pixels a une douzaine, et un total
        # calibre pour l'ancienne taille condamnait un editeur sombre ou un
        # bureau neutre au blanc chaud fige. Une moyenne ne bouge pas avec
        # le curseur de finesse.
        if poids / len(pixels) < 0.0003:       # ecran quasi gris ou noir
            teinte, saturation = 0.09, 0.12    # blanc chaud
        else:
            teinte = (math.atan2(sy, sx) / (2 * math.pi)) % 1.0
            saturation = min(1.0, (sat_tot / poids) * boost)

        r, v, b = colorsys.hsv_to_rgb(teinte, saturation, 1.0)
        return (int(r * 255), int(v * 255), int(b * 255)), luminance, index
    except Exception as e:
        signaler_capture("Capture ecran impossible", e)
        return None


# Trois images d'affilee avant de suspendre : aucune des causes reelles ne se
# resout entre deux images. La premiere attente, courte, sert de rattrapage si
# on s'est trompe ; le plafond vaut celui du Bluetooth, pour que la couleur
# revienne dans la minute qui suit un deverrouillage.
ECHECS_ECRAN = 3
ATTENTE_ECRAN = [5.0, 15.0, 60.0]


def echec_capture(rate):
    """UNE CAPTURE QUI ECHOUE ECHOUE POUR UN MOMENT, PAS POUR UNE IMAGE.

    Session verrouillee, bureau securise, changement de resolution, quota
    graphique epuise : rien de tout cela ne se repare en un huitieme de
    seconde. Sans compteur, la meme operation impossible etait retentee huit
    fois par seconde pendant des heures -- ce qui remplissait le journal et,
    surtout, entretenait la fuite qui vidait le quota du processus.

    On ne renonce JAMAIS, comme pour la guirlande : une session verrouillee
    se deverrouille, un ecran en veille se rallume.
    """
    e = ETAT["ecran"]
    if not rate:
        # Le cas de loin le plus frequent : tout va bien, et il ne doit rien
        # couter. Sans ce retour, on reconstruisait ce dictionnaire huit fois
        # par seconde pour n'y rien changer.
        #
        # ET L'ENSEMBLE DES PHRASES DEJA DITES COMPTE DANS « rien a faire ».
        # Une capture peut echouer par le chemin GDI puis reussir par le repli
        # mss : la phrase est alors dite sans qu'aucun echec ne soit compte.
        # Sortir sans vider l'ensemble condamnait cette panne-la au silence
        # pour la vie du processus, alors qu'elle doit se redire si elle revient.
        if not e["echecs"] and not e["suspendue"] and not _CAPTURE_DIT:
            return
        if e["suspendue"]:
            print("Capture ecran retablie apres %d s et %d essais rates."
                  % (time.monotonic() - e["depuis"], e["echecs"]))
        ETAT["ecran"] = {"echecs": 0, "suspendue": False,
                         "reprise": 0.0, "depuis": 0.0}
        _CAPTURE_DIT.clear()
        return
    e["echecs"] += 1
    if e["echecs"] < ECHECS_ECRAN:
        return
    if not e["suspendue"]:
        e["suspendue"] = True
        e["depuis"] = time.monotonic()
    rang = min(e["echecs"] - ECHECS_ECRAN, len(ATTENTE_ECRAN) - 1)
    e["reprise"] = time.monotonic() + ATTENTE_ECRAN[rang]


def capture_autorisee():
    return not ETAT["ecran"]["suspendue"] or \
        time.monotonic() >= ETAT["ecran"]["reprise"]


# ==========================================================================
#  Analyse du son
#
#  On capte ce qui sort des haut-parleurs (boucle WASAPI), pas le micro.
#  Trois mesures en sortent :
#    - l'energie de chaque bande, graves / mediums / aigus ;
#    - le centroide spectral, centre de gravite du spectre. Un morceau sourd
#      le pousse vers le bas, des cymbales vers le haut. C'est lui qui donne
#      la teinte : rouge quand ca pese, cyan quand ca brille.
#
#  Deux precautions font toute la difference a l'oreille comme a l'oeil :
#    - un gain automatique par bande, sinon un morceau doux n'allume rien
#      et un morceau fort sature en permanence ;
#    - une enveloppe asymetrique, montee rapide et descente lente. C'est ce
#      qui donne le coup sec sur la grosse caisse au lieu d'une bouillie.
# ==========================================================================

AUDIO = {
    "graves": 0.0, "mediums": 0.0, "aigus": 0.0, "tout": 0.0,
    "centroide": 0.5,
    "actif": False,
    "message": "arrete",
    # Dernieres valeurs posees par couleur_son, pour que le panneau montre
    # exactement ce que le son est en train de faire.
    "niveau": 0.0,
    "saturation": 0.0,
    "gain": 0.0,
}

BANDES = (("graves", 30, 250), ("mediums", 250, 2000), ("aigus", 2000, 16000))
SON = {"marche": False}


def fil_audio(cfg):
    """Tourne dans son propre fil : la capture est bloquante."""
    try:
        import numpy as np
        import soundcard as sc
    except Exception as e:
        # Pas seulement ImportError : soundcard s'appuie sur cffi, qui
        # echoue autrement qu'en module introuvable. Et e.name vaut None
        # des que l'erreur vient de l'interieur d'un module — le message
        # ne disait alors rien d'exploitable.
        AUDIO["message"] = "capture indisponible : %s: %s" % (
            type(e).__name__, str(e)[:90])
        print("Chargement audio impossible :", type(e).__name__, e)
        return

    taille = 2048                      # ~43 ms a 48 kHz, soit environ 23 mesures/s
    fenetre = np.hanning(taille)
    plafonds = {nom: 1e-3 for nom, _, _ in BANDES}
    plafonds["tout"] = 1e-3
    lisses = {nom: 0.0 for nom in list(plafonds)}

    while SON["marche"]:
        try:
            haut_parleur = sc.default_speaker()
            micro = sc.get_microphone(haut_parleur.name, include_loopback=True)
            AUDIO["message"] = f"ecoute {haut_parleur.name[:28]}"
            with micro.recorder(samplerate=48000, blocksize=taille) as source:
                AUDIO["actif"] = True
                while SON["marche"]:
                    bloc = source.record(numframes=taille)
                    mono = bloc.mean(axis=1) if bloc.ndim > 1 else bloc
                    if len(mono) < taille:
                        continue

                    spectre = np.abs(np.fft.rfft(mono[:taille] * fenetre))
                    freqs = np.fft.rfftfreq(taille, 1 / 48000)

                    mesures = {}
                    for nom, bas, haut in BANDES:
                        masque = (freqs >= bas) & (freqs < haut)
                        mesures[nom] = float(np.sqrt(
                            (spectre[masque] ** 2).mean())) if masque.any() else 0.0
                    mesures["tout"] = float(np.sqrt((spectre ** 2).mean()))

                    # Centroide calcule sur les trois bandes plutot que sur le
                    # spectre brut : un centroide classique est tire vers le haut
                    # par les aigus residuels, et un morceau a grosse basse
                    # ressortait vert. Ici graves = 0, mediums = 0.5, aigus = 1,
                    # ponderes par leur energie. Lisse a part pour que la teinte
                    # ne clignote pas au rythme des transitoires.
                    poids = mesures["graves"] + mesures["mediums"] + mesures["aigus"]
                    if poids > 1e-6:
                        brut_centre = (0.0 * mesures["graves"]
                                       + 0.5 * mesures["mediums"]
                                       + 1.0 * mesures["aigus"]) / poids
                        AUDIO["centroide"] += (brut_centre - AUDIO["centroide"]) * 0.18

                    sensibilite = float(cfg.get("son_sensibilite", 1.0))
                    attaque = float(cfg.get("son_attaque", 0.55))
                    chute = float(cfg.get("son_chute", 0.12))

                    for nom, brut in mesures.items():
                        # gain automatique : le plafond suit les pics et retombe
                        plafonds[nom] = max(brut, plafonds[nom] * 0.9992, 1e-4)
                        valeur = min(1.0, (brut / plafonds[nom]) * sensibilite)
                        k = attaque if valeur > lisses[nom] else chute
                        lisses[nom] += (valeur - lisses[nom]) * k
                        AUDIO[nom] = lisses[nom]

        except Exception as e:
            AUDIO["actif"] = False
            AUDIO["message"] = f"capture impossible : {str(e)[:44]}"
            print("Audio :", e)
            for _ in range(30):
                if not SON["marche"]:
                    break
                time.sleep(0.1)

    AUDIO["actif"] = False
    AUDIO["message"] = "arrete"


def demarrer_audio(cfg):
    if SON["marche"]:
        return
    SON["marche"] = True
    threading.Thread(target=fil_audio, args=(cfg,), daemon=True).start()


def arreter_audio():
    SON["marche"] = False


def appliquer_niveaux(valeur, noir, blanc, gamma=None):
    """Etale [noir, blanc] sur [0, 1], avec une courbe optionnelle.

    Meme calcul que les niveaux d'un logiciel d'image : on decide ce qui
    compte comme noir, ce qui compte comme blanc, et comment se repartit ce
    qu'il y a entre les deux. gamma vaut 0.5 pour une reponse lineaire ;
    en dessous les valeurs faibles sont relevees, au dessus elles sont
    ecrasees et seules les pointes ressortent.
    """
    if blanc - noir < 1e-4:
        return 1.0 if valeur >= blanc else 0.0
    x = (valeur - noir) / (blanc - noir)
    x = max(0.0, min(1.0, x))
    if gamma is not None:
        x = x ** (4.0 ** ((float(gamma) - 0.5) * 2.0))
    return x


def resaturer(rgb, saturation):
    """Repose une couleur a la saturation voulue, teinte et valeur gardees."""
    t, _, v = colorsys.rgb_to_hsv(*[c / 255.0 for c in rgb])
    r, g, b = colorsys.hsv_to_rgb(t, max(0.0, min(1.0, saturation)), v)
    return (r * 255, g * 255, b * 255)


def resaturer_vers(rgb, facteur):
    """Module la saturation deja presente, au lieu de la remplacer.

    L'ecran a deja une saturation qui veut dire quelque chose — une scene
    verte est verte. La poser a une valeur absolue effacerait cette
    information ; on la met a l'echelle.
    """
    t, sat, v = colorsys.rgb_to_hsv(*[c / 255.0 for c in rgb])
    r, g, b = colorsys.hsv_to_rgb(t, max(0.0, min(1.0, sat * facteur)), v)
    return (r * 255, g * 255, b * 255)


def presence_du_site(cfg, contexte):
    """La couleur a poser tant qu'on utilise BrainDebugger, ou None.

    Deux sources se cumulent. Le titre de la fenetre active suffit dans le
    cas courant — on lit le site, il est devant — et ne demande rien au
    site. Le battement, lui, couvre le cas ou l'onglet reste ouvert
    pendant qu'on travaille ailleurs : le titre ne dit alors plus rien.

    Un delai de grace evite le clignotement quand on passe une seconde sur
    une autre fenetre.
    """
    # L'interrupteur maitre coupe aussi la couleur de presence : « BrainDebugger
    # n'affecte pas les LEDs » veut dire aucune prise, presence comprise.
    if not cfg.get("pont_affecte_leds", True):
        return None
    if not cfg.get("pont_presence", True):
        return None

    maintenant = time.time()
    indice = str(cfg.get("pont_presence_indice", "")).strip().lower()
    vu = bool(indice) and indice in (contexte or "")

    battement = ETAT.get("presence")
    if battement and maintenant >= battement.get("jusqu_a", 0):
        battement = ETAT["presence"] = None
    if battement:
        vu = True

    if vu:
        grace = max(0.0, float(cfg.get("pont_presence_grace", 20)))
        ETAT["presence_vu"] = maintenant + grace
    elif maintenant >= ETAT.get("presence_vu", 0):
        return None

    humeur = (PONT.get("humeur") or {}).get("couleur", "")
    if cfg.get("pont_presence_suit_humeur", True) and \
            str(humeur).startswith("#"):
        return hex_vers_rgb(humeur), "BrainDebugger \u00b7 humeur"
    return hex_vers_rgb(cfg.get("pont_presence_couleur", "#7C3AED")), "BrainDebugger"


def couleur_son(cfg, couleur_regle):
    """((r, v, b), gain) a partir de la derniere analyse.

    Le son pilote la luminosite, la saturation, ou les deux. Ce qu'il ne
    pilote pas reste a sa valeur fixe : c'est ce qui permet de garder la
    guirlande franchement saturee en permanence et de ne laisser respirer
    que la luminosite.
    """
    bande = cfg.get("son_bande", "graves")
    niveau = AUDIO.get(bande, AUDIO["tout"])
    palette = cfg.get("son_palette", "chaud_froid")
    cible = cfg.get("son_cible", "luminosite")

    plancher = float(cfg.get("son_plancher", 0.06))
    module = plancher + (1.0 - plancher) * niveau     # 0..1, colle au son

    sat_fixe = float(cfg.get("son_saturation_fixe", 0.92))
    lum_fixe = float(cfg.get("son_luminosite_fixe", 1.0))
    sat_pilotee = cible in ("saturation", "les_deux")
    lum_pilotee = cible in ("luminosite", "les_deux")

    # Pilotee, la saturation va de zero a la valeur fixe : celle-ci sert
    # alors de plafond plutot que de consigne.
    saturation = module * sat_fixe if sat_pilotee else sat_fixe
    gain = module if lum_pilotee else lum_fixe

    if palette == "regle":
        # Sans pilotage de la saturation, la couleur de la regle est
        # rendue telle quelle : on ne redresse que ce qui doit bouger.
        rvb = resaturer(couleur_regle, saturation) if sat_pilotee else couleur_regle
    else:
        if palette == "arc":
            teinte = AUDIO["centroide"]
        else:                                   # chaud vers froid
            teinte = 0.02 + 0.52 * AUDIO["centroide"]
        r, v, b = colorsys.hsv_to_rgb(teinte % 1.0,
                                      max(0.0, min(1.0, saturation)), 1.0)
        rvb = (r * 255, v * 255, b * 255)

    AUDIO["niveau"] = niveau
    AUDIO["saturation"] = saturation
    AUDIO["gain"] = gain
    return rvb, gain


# ==========================================================================
#  Passerelle HTTP locale
#
#  Un site web ne peut pas parler Bluetooth. Il parle a ce petit serveur,
#  qui pose une couleur forcee avec une date de peremption : si le site
#  arrete d'emettre, la guirlande revient d'elle-meme au mode normal.
#
#  Deux obstacles cotes navigateur, traites ici :
#   - une page HTTPS qui appelle une adresse locale doit recevoir
#     Access-Control-Allow-Private-Network sur le prevol OPTIONS ;
#   - l'origine doit etre explicitement autorisee, sinon n'importe quelle
#     page ouverte pourrait piloter les lumieres.
# ==========================================================================

SERVEUR = {"http": None}


def jeton_courant(cfg):
    """La cle du serveur local. Tiree une fois, gardee dans la configuration.

    Si l'enregistrement echoue, la cle vaut quand meme pour cette session : le
    site en recevra une neuve au prochain demarrage, ce qui demande un nouvel
    appairage. C'est genant. Refuser de demarrer l'etait bien plus.
    """
    if not cfg.get("api_jeton"):
        cfg["api_jeton"] = secrets.token_urlsafe(12)
        if not sauver_config(cfg):
            print("Cle du serveur local non enregistree : valable pour cette "
                  "session seulement.")
    return cfg["api_jeton"]


def couleur_de_regle(cfg, nom):
    """Retrouve la couleur d'une regle par son nom, sans tenir compte de la casse."""
    cible = (nom or "").strip().lower()
    for regle in cfg.get("regles", []):
        if regle.get("nom", "").strip().lower() == cible:
            return hex_vers_rgb(regle["couleur"])
    return None


# =====================================================================
#  LA DICTEE — LA VOIX DEVIENT DU TEXTE, SUR CE POSTE ET NULLE PART AILLEURS.
#
#  Le meme moteur que Handy (github.com/cjpais/Handy, licence MIT) : Parakeet
#  V3 de NVIDIA, exporte en ONNX et quantifie en int8, qui lit le francais et
#  tourne sur le processeur. Handy l'appelle depuis Rust ; ici c'est onnx-asr,
#  qui lit exactement les memes fichiers.
#
#  CE QUI EST PROMIS, ET QUE CE CODE TIENT :
#    - le son n'est JAMAIS ecrit sur le disque : il arrive en memoire par la
#      passerelle locale, devient du texte, et disparait ;
#    - il ne quitte pas la machine : le site l'envoie a 127.0.0.1, pas au
#      serveur, et le texte repart vers la page qui l'a demande ;
#    - rien n'ecoute tant qu'on n'a pas appuye sur le micro — c'est la page
#      qui tient le micro, avec l'autorisation du navigateur, pas Machi Tool.
#      Pas de raccourci global : Machi Tool n'installe AUCUN crochet clavier.
#
#  LE MODELE (456 Mo) N'EST PAS DANS L'EXE. Si Handy l'a deja telecharge,
#  on le reprend tel quel (liens durs : zero octet de plus) ; sinon on le
#  telecharge une fois, a la demande explicite de la personne.
# =====================================================================

DICTEE_MODELE = "parakeet-tdt-0.6b-v3-int8"
DICTEE_NOM = "nemo-parakeet-tdt-0.6b-v3"          # le nom que connait onnx-asr
DICTEE_FICHIERS = ("encoder-model.int8.onnx", "decoder_joint-model.int8.onnx", "vocab.txt")
# Parakeet lit 128 bandes de frequence, pas les 80 que suppose onnx-asr sans
# config. Sans ce fichier le modele se charge — et rend du charabia.
DICTEE_CONFIG = {"model_type": "nemo-conformer-tdt", "features_size": 128,
                 "subsampling_factor": 8}
DICTEE_SOURCE = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main/"
DICTEE_MAX_OCTETS = 20 * 1024 * 1024     # ~10 min de parole en 16 kHz mono
DICTEE_DECHARGER_S = 10 * 60             # le modele occupe ~1 Go de memoire

DICTEE = {"etat": "absent", "progres": 0.0, "source": None, "message": ""}
_DICTEE_VERROU = threading.Lock()


_DICTEE_POSSIBLE = []


def dictee_possible():
    """Le moteur est-il installe ? (Faux en CI, et sur une version sans lui.)

    SANS L'IMPORTER. `import onnx_asr` charge numpy et onnxruntime (ses DLL) :
    dans l'exe, plusieurs secondes au premier appel — et la page, qui
    n'attendait que quatre secondes la reponse a « es-tu la ? », concluait
    « Machi Tool ne repond pas ». Savoir qu'il est la suffit ici ; le charger
    attendra la premiere phrase."""
    if not _DICTEE_POSSIBLE:
        try:
            import importlib.util
            _DICTEE_POSSIBLE.append(importlib.util.find_spec("onnx_asr") is not None)
        except Exception:
            _DICTEE_POSSIBLE.append(False)
    return _DICTEE_POSSIBLE[0]


def dossier_dictee():
    return os.path.join(DOSSIER, "dictee", DICTEE_MODELE)


def dossier_modele_handy():
    """Le modele que Handy a telecharge, s'il y en a un sur ce poste.

    Handy le range sous %APPDATA%\\com.pais.handy\\models\\. L'archive peut
    avoir un dossier de plus a l'interieur : on regarde deux niveaux."""
    base = os.environ.get("APPDATA", "")
    if not base:
        return None
    racine = os.path.join(base, "com.pais.handy", "models", DICTEE_MODELE)
    if not os.path.isdir(racine):
        return None
    for dossier, sous, _ in os.walk(racine):
        if dossier_complet(dossier):
            return dossier
        if dossier.count(os.sep) - racine.count(os.sep) >= 2:
            sous[:] = []
    return None


def dossier_complet(d):
    return bool(d) and all(os.path.isfile(os.path.join(d, f)) and
                           os.path.getsize(os.path.join(d, f)) > 0
                           for f in DICTEE_FICHIERS)


def _ecrire_config_dictee(d):
    chemin = os.path.join(d, "config.json")
    if not os.path.isfile(chemin):
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(DICTEE_CONFIG, f)


def _reprendre_de_handy(source, cible):
    """Liens durs vers les fichiers de Handy : meme disque, zero octet de plus.
    Sur un autre disque le lien est impossible — on copie, une fois."""
    for nom in DICTEE_FICHIERS:
        dst = os.path.join(cible, nom)
        if os.path.isfile(dst):
            continue
        src = os.path.join(source, nom)
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst + ".part")
            os.replace(dst + ".part", dst)


def _telecharger_dictee(cible, ouvrir=None):
    """Les trois fichiers, un par un, avec la progression pour l'ecran.
    `.part` puis renommage : un telechargement coupe ne passe jamais pour un
    modele complet."""
    ouvrir = ouvrir or (lambda url: urllib.request.urlopen(url, timeout=60, context=_contexte_ssl()))
    for i, nom in enumerate(DICTEE_FICHIERS):
        dst = os.path.join(cible, nom)
        if os.path.isfile(dst) and os.path.getsize(dst) > 0:
            continue
        with ouvrir(DICTEE_SOURCE + nom) as r, open(dst + ".part", "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            recu = 0
            while True:
                bout = r.read(1 << 20)
                if not bout:
                    break
                f.write(bout)
                recu += len(bout)
                if total:
                    DICTEE["progres"] = (i + recu / total) / len(DICTEE_FICHIERS)
        os.replace(dst + ".part", dst)
    DICTEE["progres"] = 1.0


def preparer_dictee(ouvrir=None):
    """Rend le modele disponible sur le disque. A lancer dans un fil a part."""
    with _DICTEE_VERROU:
        if DICTEE["etat"] in ("preparation", "pret"):
            return DICTEE["etat"]
        DICTEE.update(etat="preparation", progres=0.0, message="")
    try:
        cible = dossier_dictee()
        os.makedirs(cible, exist_ok=True)
        if not dossier_complet(cible):
            handy = dossier_modele_handy()
            if handy:
                DICTEE["source"] = "handy"
                _reprendre_de_handy(handy, cible)
            else:
                DICTEE["source"] = "telechargement"
                _telecharger_dictee(cible, ouvrir)
        _ecrire_config_dictee(cible)
        if not dossier_complet(cible):
            raise RuntimeError("modele incomplet")
        DICTEE.update(etat="pret", progres=1.0)
    except Exception as e:
        DICTEE.update(etat="erreur", message=str(e)[:200])
        print("Dictee : preparation impossible (%s)" % e)
    return DICTEE["etat"]


def etat_dictee():
    """Ce que la page doit savoir pour afficher le bon bouton."""
    if DICTEE["etat"] == "absent" and dossier_complet(dossier_dictee()):
        DICTEE["etat"] = "pret"
    return {"moteur": dictee_possible(), "etat": DICTEE["etat"],
            "progres": round(DICTEE["progres"], 3), "source": DICTEE["source"],
            "handy": bool(dossier_modele_handy()), "message": DICTEE["message"],
            "taille_mo": 456}


def son_depuis_wav(octets):
    """WAV PCM 16 bits -> (echantillons float32 mono, frequence). En memoire."""
    import wave
    import numpy as np
    with wave.open(io.BytesIO(octets)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("WAV 16 bits attendu")
        canaux, frequence = w.getnchannels(), w.getframerate()
        brut = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if canaux > 1:
        brut = brut.reshape(-1, canaux).mean(axis=1)
    return brut.astype(np.float32) / 32768.0, frequence


def _options_onnx():
    """La moitie des coeurs, et pas d'arene memoire gardee apres usage.

    Par defaut onnxruntime prend TOUS les coeurs : pendant le chargement et
    la transcription, le reste du PC ne repondait plus — jusqu'a faire
    tomber d'autres applications."""
    import onnxruntime as rt
    o = rt.SessionOptions()
    o.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
    o.inter_op_num_threads = 1
    o.enable_cpu_mem_arena = False
    return o


def _charger_modele_dictee():
    import onnx_asr
    return onnx_asr.load_model(DICTEE_NOM, dossier_dictee(), quantization="int8",
                               sess_options=_options_onnx())


# ---------------------------------------------------------------------
#  LE MOTEUR VIT DANS SON PROPRE PROCESSUS.
#
#  Vu en vrai : a la premiere dictee, le PC a gele, Claude a plante, et
#  Machi Tool s'est ETEINT (« Failed to fetch » cote page). Le modele de
#  456 Mo se chargeait DANS Machi Tool : une panne de memoire ou du moteur
#  natif emportait l'application entiere — ses LEDs, sa passerelle, son
#  journal d'activite. Rien de facultatif ne doit pouvoir faire ca.
#
#  Le moteur tourne donc dans un processus enfant (le meme exe, lance avec
#  DICTEE_ENFANT_ARG), en priorite basse, sur la moitie des coeurs. S'il
#  tombe, Machi Tool reste debout et dit pourquoi ; s'il ne sert plus, il
#  s'en va, et sa memoire revient VRAIMENT au systeme — ce qu'un modele
#  decharge a l'interieur d'un processus Python ne garantit pas.
# ---------------------------------------------------------------------

DICTEE_ENFANT_ARG = "--moteur-dictee"
DICTEE_MEMOIRE_MIN_MO = 1500        # en dessous, charger 1 Go gelerait le PC
DICTEE_DEMARRAGE_S = 90             # l'exe se decompresse avant de repondre
DICTEE_REPONSE_S = 300              # premier chargement + transcription
_MOTEUR = {"proc": None, "sock": None, "vu": 0.0}


class DicteeImpossible(RuntimeError):
    """Une raison qu'on peut dire telle quelle a la personne."""


def memoire_libre_mo():
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 * 1024)
    except Exception:
        return None


def _envoyer_trame(s, octets):
    s.sendall(struct.pack(">I", len(octets)) + octets)


def _recevoir_trame(s, plafond=DICTEE_MAX_OCTETS + 4096):
    def exactement(n):
        buf = bytearray()
        while len(buf) < n:
            bout = s.recv(min(1 << 20, n - len(buf)))
            if not bout:
                raise ConnectionError("connexion fermee")
            buf += bout
        return bytes(buf)
    n = struct.unpack(">I", exactement(4))[0]
    if n > plafond:
        raise ValueError("trame trop longue")
    return exactement(n)


def _commande_moteur(port, secret):
    if FIGE:
        return [sys.executable, DICTEE_ENFANT_ARG, str(port), secret]
    return [sys.executable, os.path.abspath(__file__), DICTEE_ENFANT_ARG, str(port), secret]


def _arreter_moteur():
    sock, proc = _MOTEUR["sock"], _MOTEUR["proc"]
    _MOTEUR.update(sock=None, proc=None)
    if sock is not None:
        try:
            _envoyer_trame(sock, b"")                 # « c'est fini »
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass
    if proc is not None and proc.poll() is None:
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


atexit.register(_arreter_moteur)


def _moteur_vivant():
    """La connexion au moteur, en le lancant s'il le faut."""
    proc = _MOTEUR["proc"]
    if proc is not None and proc.poll() is None and _MOTEUR["sock"] is not None:
        return _MOTEUR["sock"]
    _arreter_moteur()
    libre = memoire_libre_mo()
    if libre is not None and libre < DICTEE_MEMOIRE_MIN_MO:
        raise DicteeImpossible(
            "pas assez de memoire libre pour la dictee (%d Mo, il en faut %d) — "
            "ferme des applications ; Handy garde peut-etre le meme modele ouvert"
            % (libre, DICTEE_MEMOIRE_MIN_MO))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(DICTEE_DEMARRAGE_S)
        secret = secrets.token_hex(16)
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                   | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        # Ses erreurs, et la pile d'un plantage natif, vont au meme journal.
        sortie = _JOURNAL if _JOURNAL is not None else None
        proc = subprocess.Popen(_commande_moteur(srv.getsockname()[1], secret),
                                stdin=subprocess.DEVNULL, stdout=sortie, stderr=sortie, **kw)
        try:
            sock, _ = srv.accept()
        except socket.timeout:
            proc.kill()
            raise DicteeImpossible("le moteur de dictee n'a pas demarre")
        sock.settimeout(DICTEE_REPONSE_S)
        try:
            ok = secrets.compare_digest(_recevoir_trame(sock, 64), secret.encode())
        except Exception:
            ok = False
        if not ok:
            sock.close()
            proc.kill()
            raise DicteeImpossible("le moteur de dictee n'a pas repondu comme prevu")
    finally:
        srv.close()
    _MOTEUR.update(proc=proc, sock=sock, vu=time.time())
    return sock


def entete_wav(octets):
    """(canaux, frequence, echantillons, largeur) — sans numpy, sans rien charger."""
    with wave.open(io.BytesIO(octets)) as w:
        return w.getnchannels(), w.getframerate(), w.getnframes(), w.getsampwidth()


def transcrire(octets):
    """Le texte dit dans ce WAV. Le son ne touche jamais le disque."""
    if etat_dictee()["etat"] != "pret":
        raise RuntimeError("le modele de dictee n'est pas pret")
    try:
        _, frequence, n, largeur = entete_wav(octets)
    except (wave.Error, EOFError) as e:
        raise ValueError("WAV illisible (%s)" % e)
    if largeur != 2:
        raise ValueError("WAV 16 bits attendu")
    if frequence not in (8000, 16000, 22050, 24000, 32000, 44100, 48000):
        raise ValueError("frequence non prise en charge : %s" % frequence)
    if n < frequence * 0.2:
        return ""                                   # un clic, pas une phrase
    with _DICTEE_VERROU:
        sock = _moteur_vivant()
        try:
            _envoyer_trame(sock, octets)
            reponse = json.loads(_recevoir_trame(sock).decode("utf-8"))
        except (OSError, ConnectionError, ValueError):
            proc = _MOTEUR["proc"]
            code = proc.poll() if proc is not None else None
            _arreter_moteur()
            libre = memoire_libre_mo()
            conseil = (" — il ne restait que %d Mo de memoire libre" % libre
                       if libre is not None and libre < 3 * DICTEE_MEMOIRE_MIN_MO else "")
            print("Dictee : le moteur s'est arrete (code %s)" % code)
            raise DicteeImpossible("le moteur de dictee s'est arrete en pleine transcription%s. "
                                   "Machi Tool, lui, tourne toujours." % conseil)
        _MOTEUR["vu"] = time.time()
    _programmer_dechargement()
    if "erreur" in reponse:
        raise DicteeImpossible("le moteur de dictee a echoue : %s" % reponse["erreur"])
    return str(reponse.get("texte") or "").strip()


def moteur_dictee_enfant(port, secret, charger=None):
    """Ce que fait le processus du moteur : attendre un son, rendre un texte.

    Il s'en va de lui-meme quand Machi Tool ferme la connexion, disparait, ou
    l'oublie plus longtemps que DICTEE_DECHARGER_S."""
    if os.name != "nt":
        try:
            os.nice(10)
        except Exception:
            pass
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=30)
    _envoyer_trame(s, str(secret).encode())
    s.settimeout(DICTEE_DECHARGER_S + 60)
    modele = None
    try:
        while True:
            try:
                wav = _recevoir_trame(s)
            except (OSError, ConnectionError, ValueError):
                break
            if not wav:
                break
            try:
                if modele is None:
                    modele = (charger or _charger_modele_dictee)()
                son, frequence = son_depuis_wav(wav)
                reponse = {"texte": str(modele.recognize(son, sample_rate=frequence) or "").strip()}
            except Exception as e:
                reponse = {"erreur": "%s : %s" % (type(e).__name__, str(e)[:200])}
            wav = None
            _envoyer_trame(s, json.dumps(reponse).encode("utf-8"))
    finally:
        try:
            s.close()
        except Exception:
            pass


_DICTEE_MINUTEUR = [None]


def _programmer_dechargement():
    ancien = _DICTEE_MINUTEUR[0]
    if ancien is not None:
        ancien.cancel()
    t = threading.Timer(DICTEE_DECHARGER_S + 5, decharger_dictee_si_oubliee)
    t.daemon = True
    t.start()
    _DICTEE_MINUTEUR[0] = t


def decharger_dictee_si_oubliee(maintenant=None):
    """Un moteur de 1 Go ne reste pas en memoire pour une dictee par jour :
    on arrete son processus, et le systeme recupere tout."""
    maintenant = time.time() if maintenant is None else maintenant
    with _DICTEE_VERROU:
        if _MOTEUR["proc"] is not None and maintenant - _MOTEUR["vu"] > DICTEE_DECHARGER_S:
            _arreter_moteur()
            return True
    return False


# =====================================================================
#  JARVIS — « JARVIS, ... » : IL S'ALLUME, IL ECOUTE, IL FAIT OU IL REPOND.
#
#  Le detecteur, la fin de phrase, les commandes et les sons sont dans
#  jarvis.py ; ici, ce qui touche le reste de Machi Tool : le processus de
#  l'oreille, la transcription (le moteur de la dictee), la guirlande, la
#  voix de Windows, le compagnon de BrainDebugger.
#
#  CE QUI EST PROMIS, ET QUE CE CODE TIENT :
#    - rien n'ecoute tant que « Ecouter Jarvis » n'est pas coche (page Jarvis,
#      ou clic droit sur l'icone) ; decoche, le processus du micro s'arrete ;
#    - avant le mot d'eveil, rien ne quitte le processus de l'oreille : pas de
#      son, pas de texte -- seulement « on m'a appele » ;
#    - apres, la phrase est transcrite SUR CE POSTE ; une commande (lumiere,
#      minuteur, heure...) reste ici. Seul ce qui est pour le compagnon part a
#      BrainDebugger -- exactement comme si on l'avait tape dans le chat ;
#    - le son n'est jamais ecrit sur le disque, et le journal ne garde jamais
#      ce qui a ete dit (« commande lumiere_couleur », pas la phrase) ;
#    - aucun crochet clavier, aucun raccourci global.
# =====================================================================

# A cote de ce fichier : en script, le dossier du script n'est pas toujours
# dans le chemin (les tests chargent ce module par son chemin).
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jarvis as _jv  # noqa: E402

JARVIS_ENFANT_ARG = "--oreille"
JARVIS_RELANCE_S = (3, 10, 30, 60)

JARVIS = {
    "etat": "eteint",        # eteint | preparation | demarrage | attente | ecoute |
                             # comprend | pense | parle | erreur
    "message": "",
    "db": None,               # niveau du micro, pour montrer qu'il vit
    "led": None, "led_t0": 0.0, "led_fin": 0.0,
    "modeles": "absent", "progres": 0.0,
    "apprentissage": None,    # {"n", "total", "message", "fini"}
    "minuteurs": [],          # [{"fin", "quoi", "minuteur"}]
    # Deux modes : « jarvis » (orange, le majordome du PC) et « psy » (bleu, le
    # compagnon de BrainDebugger). Le mode psy se referme sur « non rien »,
    # « oublie », « degage »... ou apres PSY_DUREE_S sans un mot.
    "mode": "jarvis", "mode_vu": 0.0,
    "historique": [],         # la conversation en cours avec le majordome
    "vu": 0.0,                # dernier echange
    "propose_psy": False,     # il vient de proposer le mode psy : « oui » y passe
    # La seance en cours avec le psychologue, en memoire seulement (jamais sur
    # le disque) : a l'« au revoir », Jarvis se tait si c'etait lourd.
    "psy_echange": [],
    "psy_grave": False,       # un message grave y est passe : alors il se tait, toujours
}
_OREILLE = {"proc": None, "sock": None, "echecs": 0, "prochain": 0.0}
_OREILLE_VERROU = threading.Lock()
_GABARIT_RECU = {"evt": None, "signal": threading.Event()}
JARVIS_CROCHETS = {}          # « ouvrir_panneau », « notifier » : poses par lancer()
_JARVIS_TRAVAIL = []          # file de phrases a traiter, un seul fil a la fois
_JARVIS_TRAVAIL_SIGNAL = threading.Event()


def dossier_jarvis():
    return os.path.join(DOSSIER, "jarvis")


def modeles_jarvis_prets():
    d = dossier_jarvis()
    return all(os.path.isfile(os.path.join(d, n)) and os.path.getsize(os.path.join(d, n)) > 0
               for n in _jv.MODELES)


def preparer_jarvis(ouvrir=None):
    """Les trois petits modeles d'openWakeWord (3,6 Mo), une fois. `.part`
    puis renommage : un telechargement coupe ne passe jamais pour complet."""
    if modeles_jarvis_prets():
        JARVIS.update(modeles="pret", progres=1.0)
        return True
    JARVIS.update(modeles="preparation", progres=0.0)
    ouvrir = ouvrir or (lambda url: urllib.request.urlopen(url, timeout=60, context=_contexte_ssl()))
    try:
        d = dossier_jarvis()
        os.makedirs(d, exist_ok=True)
        for i, nom in enumerate(_jv.MODELES):
            dst = os.path.join(d, nom)
            if os.path.isfile(dst) and os.path.getsize(dst) > 0:
                continue
            with ouvrir(_jv.MODELES_SOURCE + nom) as r, open(dst + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
            os.replace(dst + ".part", dst)
            JARVIS["progres"] = (i + 1) / len(_jv.MODELES)
        JARVIS.update(modeles="pret", progres=1.0)
        return True
    except Exception as e:
        JARVIS.update(modeles="erreur", message="modeles du mot d'eveil introuvables : %s" % str(e)[:120])
        print("Jarvis : modeles non telecharges (%s)" % e)
        return False


def _fichier_gabarits():
    return os.path.join(dossier_jarvis(), "voix.json")


def gabarits_jarvis():
    """Les empreintes de « Jarvis » dit par la personne. Des vecteurs, pas du
    son : on ne peut pas reconstruire la voix a partir d'eux."""
    try:
        with open(_fichier_gabarits(), encoding="utf-8") as f:
            g = json.load(f).get("gabarits", [])
        return [x for x in g if isinstance(x, list) and len(x) >= _jv.GABARIT_MIN]
    except Exception:
        return []


def gabarits_auto():
    """Les facons de l'appeler qu'il a gardees seul (voir AUTO_* dans jarvis.py)."""
    try:
        with open(_fichier_gabarits(), encoding="utf-8") as f:
            g = json.load(f).get("auto", [])
        return [x for x in g if isinstance(x, list) and len(x) >= _jv.GABARIT_MIN]
    except Exception:
        return []


def ajouter_gabarit_auto(vecteurs):
    """Une facon de plus, gardee seule apres un vrai appel. Refusee si elle ne
    ressemble a aucune de celles apprises (ce serait un autre mot) ; au plus
    AUTO_PLAFOND, les plus anciennes s'en vont. Rend True si gardee."""
    if not CFG.get("jarvis_auto_etalonnage", True):
        return False
    if not isinstance(vecteurs, list) or len(vecteurs) < _jv.GABARIT_MIN or len(vecteurs) > _jv.GABARIT_MAX:
        return False
    try:
        v = _jv.normer(vecteurs)
        if v.shape[1] != 96:
            return False
    except Exception:
        return False
    connus = gabarits_jarvis()
    if connus and min(_jv.distance_gabarit(_jv.normer(g), v) for g in connus) > _jv.AUTO_ECART_MAX:
        return False
    auto = gabarits_auto()
    # deja connue a peu pres telle quelle : rien a ajouter
    if any(_jv.distance_gabarit(_jv.normer(g), v) < 0.01 for g in connus + auto):
        return False
    auto = (auto + [[[round(float(x), 5) for x in ligne] for ligne in v]])[-_jv.AUTO_PLAFOND:]
    _ecrire_voix(connus, auto)
    return True


def _ecrire_voix(gabarits, auto):
    os.makedirs(dossier_jarvis(), exist_ok=True)
    chemin = _fichier_gabarits()
    ancien = {}
    try:
        with open(chemin, encoding="utf-8") as f:
            ancien = json.load(f)
    except Exception:
        pass
    with open(chemin + ".part", "w", encoding="utf-8") as f:
        json.dump({"gabarits": gabarits, "auto": auto,
                   "appris_le": ancien.get("appris_le") or time.strftime("%Y-%m-%d %H:%M"),
                   "micro": ancien.get("micro") or str(JARVIS.get("micro") or "")}, f)
    os.replace(chemin + ".part", chemin)


def oublier_gabarits_auto():
    _ecrire_voix(gabarits_jarvis(), [])
    envoyer_oreille(config_oreille(CFG))


def micro_des_gabarits():
    """Le micro avec lequel la voix a ete apprise ('' si inconnu : avant 1.35)."""
    try:
        with open(_fichier_gabarits(), encoding="utf-8") as f:
            return str(json.load(f).get("micro") or "")
    except Exception:
        return ""


def sauver_gabarits(gabarits, garder_auto=False):
    """`garder_auto` : une facon de plus ; sinon (tout reappris : une autre
    voix, un autre micro), ce qu'il avait garde seul s'en va aussi."""
    auto = gabarits_auto() if garder_auto else []
    os.makedirs(dossier_jarvis(), exist_ok=True)
    chemin = _fichier_gabarits()
    with open(chemin + ".part", "w", encoding="utf-8") as f:
        # le micro avec lequel on l'a appris : un autre micro entend une autre voix
        json.dump({"gabarits": gabarits, "auto": auto, "appris_le": time.strftime("%Y-%m-%d %H:%M"),
                   "micro": str(JARVIS.get("micro") or "")}, f)
    os.replace(chemin + ".part", chemin)


def oublier_voix():
    try:
        os.remove(_fichier_gabarits())
    except OSError:
        pass
    envoyer_oreille(config_oreille(CFG))


# ---------- ses animations et ses routines de lumiere ----------
# « Jarvis a tous les droits au niveau de l'application : il peut controler et
# rajouter des petites sous-routines de lumieres, avec des habitudes / running
# gags. » Une animation joue PAR-DESSUS tout (elle est courte et voulue) ;
# « tenir » laisse sa derniere couleur, comme une couleur choisie a la main.

ANIMATION = {"etapes": [], "t0": 0.0, "repetitions": 1, "nom": "", "tenir": False}
ROUTINES_VUES = {"dernieres": {}, "minute": "", "contexte": "", "demarrage": False}


def jouer_animation(etapes, repetitions=1, nom="Jarvis", tenir=False):
    etapes = _jv.etapes_propres(etapes)
    if not etapes:
        raise ValueError("Aucune etape de lumiere lisible.")
    ANIMATION.update(etapes=etapes, t0=time.time(), repetitions=max(1, min(int(repetitions or 1), 20)),
                     nom=str(nom)[:40], tenir=bool(tenir))
    return _jv.duree_animation(etapes, ANIMATION["repetitions"])


def couleur_de_l_animation(maintenant=None):
    """La couleur de l'animation en cours (deja dosee), ou None."""
    if not ANIMATION["etapes"]:
        return None
    t = (time.time() if maintenant is None else maintenant) - ANIMATION["t0"]
    c = _jv.couleur_animation(ANIMATION["etapes"], t, ANIMATION["repetitions"])
    if c is None:
        fin = ANIMATION["etapes"][-1]
        if ANIMATION["tenir"]:
            couleur = tuple(int(round(v * fin["luminosite"])) for v in hex_vers_rgb(fin["couleur"]))
            ETAT["forcage"] = {"couleur": couleur, "nom": "%s (Jarvis)" % ANIMATION["nom"], "manuel": True,
                               "expire": 0}
        ANIMATION["etapes"] = []
    return c


def declencher_routines(genre, valeur, cfg, maintenant=None, alea=None):
    """Joue la premiere routine que ceci declenche (et que sa chance et sa pause
    laissent passer) ; dit sa replique si Jarvis peut parler. Rend la routine, ou None."""
    t = time.time() if maintenant is None else maintenant
    for r in _jv.routines_declenchees(cfg.get("routines_lumiere") or [], genre, valeur):
        derniere = ROUTINES_VUES["dernieres"].get(r["nom"], 0.0)
        if not _jv.peut_jouer(r, derniere, t, random.random() if alea is None else alea):
            continue
        ROUTINES_VUES["dernieres"][r["nom"]] = t
        try:
            jouer_animation(r["etapes"], r.get("repetitions", 1), r["nom"], r.get("tenir"))
        except ValueError:
            continue
        print("Jarvis : routine « %s » (%s)" % (r["nom"], genre))
        if r.get("replique") and genre != "phrase" and cfg.get("jarvis_actif") \
                and JARVIS.get("etat") in ("attente", "eteint", None):
            dire(r["replique"], suite=False, langue=langue_jarvis(cfg))
        return r
    return None


def veiller_routines(cfg, contexte, maintenant=None):
    """Depuis la boucle de la guirlande : l'heure (une fois par minute) et
    l'appli au premier plan (quand elle change)."""
    t = time.time() if maintenant is None else maintenant
    if not ROUTINES_VUES["demarrage"]:
        ROUTINES_VUES["demarrage"] = True
        declencher_routines("evenement", "demarrage", cfg, t)
    lt = time.localtime(t)
    minute = time.strftime("%Y-%m-%d %H:%M", lt)
    if minute != ROUTINES_VUES["minute"]:
        ROUTINES_VUES["minute"] = minute
        declencher_routines("heure", lt, cfg, t)
    if contexte and contexte != ROUTINES_VUES["contexte"]:
        ROUTINES_VUES["contexte"] = contexte
        declencher_routines("appli", contexte, cfg, t)


# ---------- la guirlande ----------

def poser_led(etat, duree=None):
    JARVIS["led"] = etat
    JARVIS["led_t0"] = time.time()
    JARVIS["led_fin"] = time.time() + duree if duree else 0.0


def couleur_jarvis(cfg, maintenant=None):
    """((r, v, b), gain) quand Jarvis a quelque chose a montrer, sinon None.
    Passe devant tout le reste : quand on lui parle, on doit le voir."""
    if not cfg.get("jarvis_leds", True):
        return None
    etat = JARVIS.get("led")
    if not etat:
        return None
    t = time.time() if maintenant is None else maintenant
    if JARVIS["led_fin"] and t > JARVIS["led_fin"]:
        JARVIS["led"] = None
        return None
    return _jv.couleur_etat(etat, t - JARVIS["led_t0"], cfg.get("jarvis_couleurs") or {},
                            JARVIS.get("mode", "jarvis"))


# ---------- la voix ----------

PIPER = {"etat": "absent", "progres": 0.0, "message": ""}
_PIPER_VERROU = threading.Lock()


def dossier_piper():
    return os.path.join(dossier_jarvis(), "piper")


def bibli_espeak():
    """espeak-ng, livre dans l'archive de Piper avec ses donnees : c'est lui
    qui transforme le texte en phonemes."""
    nom = "espeak-ng.dll" if os.name == "nt" else "libespeak-ng.so.1"
    return os.path.join(dossier_piper(), "piper", nom)


def fichier_voix(nom):
    return os.path.join(dossier_jarvis(), "voix", nom + ".onnx")


def voix_presente(nom):
    f = fichier_voix(nom)
    return os.path.isfile(f) and os.path.getsize(f) > 0 and os.path.isfile(f + ".json")


def voix_choisie(cfg):
    nom = str(cfg.get("jarvis_voix_modele", _jv.VOIX_DEFAUT) or _jv.VOIX_DEFAUT)
    return nom if nom == "windows" or nom in _jv.VOIX_PIPER else _jv.VOIX_DEFAUT


def piper_pret(cfg):
    """De quoi charger la voix neuronale, ou None. La voix choisie d'abord ;
    a defaut, celle de secours si elle est la."""
    nom = voix_choisie(cfg)
    if nom == "windows" or not os.path.isfile(bibli_espeak()):
        return None
    for n in (nom, _jv.VOIX_SECOURS):
        if voix_presente(n):
            f = fichier_voix(n)
            try:
                with open(f + ".json", encoding="utf-8") as fj:
                    conf = json.load(fj)
            except Exception:
                continue
            locuteur = _jv.VOIX_PIPER.get(n, {}).get("locuteur")
            ids = conf.get("speaker_id_map") or {}
            return {"nom": n, "bibliotheque": bibli_espeak(),
                    "donnees": os.path.join(dossier_piper(), "piper"),
                    "modele": f, "frequence": _jv.frequence_du_modele(f + ".json"),
                    "espeak": str((conf.get("espeak") or {}).get("voice") or "fr"),
                    "locuteur": int(ids.get(locuteur, 0)) if locuteur else 0}
    return None


def _telecharger(url, dst, ouvrir, part=None, etat=None):
    etat = PIPER if etat is None else etat
    with ouvrir(url) as r, open(dst + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        recu = 0
        while True:
            bout = r.read(1 << 20)
            if not bout:
                break
            f.write(bout)
            recu += len(bout)
            if part and total:
                etat["progres"] = part[0] + (part[1] - part[0]) * recu / total
    os.replace(dst + ".part", dst)


def _preparer_espeak(ouvrir, part=(0.0, 0.3), etat=None):
    """espeak-ng et ses donnees : l'archive du moteur Piper (21 Mo). Les deux
    voix en ont besoin -- c'est lui qui fait les phonemes."""
    if os.path.isfile(bibli_espeak()):
        return
    import zipfile
    os.makedirs(dossier_piper(), exist_ok=True)
    archive = os.path.join(dossier_piper(), "piper.zip")
    _telecharger(_jv.PIPER_MOTEUR, archive, ouvrir, part, etat)
    with zipfile.ZipFile(archive) as z:
        z.extractall(dossier_piper())
    os.remove(archive)


def preparer_piper(cfg, ouvrir=None):
    """Le moteur (21 Mo) et la voix choisie (20 a 60 Mo), une fois. Hugging
    Face d'abord ; les voix qui existent aussi sur GitHub y sont reprises si
    Hugging Face ne repond pas ; en dernier recours, la voix de secours."""
    nom = voix_choisie(cfg)
    if nom == "windows":
        return False
    with _PIPER_VERROU:
        if piper_pret(cfg) and voix_presente(nom):
            PIPER.update(etat="pret", progres=1.0, message="")
            return True
        ouvrir = ouvrir or (lambda url: urllib.request.urlopen(url, timeout=60, context=_contexte_ssl()))
        PIPER.update(etat="preparation", progres=0.0, message="")
        try:
            import tarfile
            os.makedirs(dossier_piper(), exist_ok=True)
            os.makedirs(os.path.dirname(fichier_voix(nom)), exist_ok=True)
            with _ESPEAK_VERROU:
                _preparer_espeak(ouvrir, (0.0, 0.3))
            for n in (nom, _jv.VOIX_SECOURS):
                if voix_presente(n):
                    break
                entree = _jv.VOIX_PIPER[n]
                dst = fichier_voix(n)
                try:
                    base = _jv.PIPER_VOIX_HF + entree["hf"] + n
                    _telecharger(base + ".onnx.json", dst + ".json", ouvrir)
                    _telecharger(base + ".onnx", dst, ouvrir, (0.3, 1.0))
                    break
                except Exception as e:
                    print("Jarvis : voix %s absente de Hugging Face (%s)" % (n, e))
                if entree.get("github"):
                    try:
                        archive = dst + ".tar.gz"
                        _telecharger(_jv.PIPER_VOIX_GITHUB + entree["github"] + ".tar.gz", archive,
                                     ouvrir, (0.3, 1.0))
                        with tarfile.open(archive) as t:
                            for m in t.getmembers():
                                if m.name.endswith(".onnx") or m.name.endswith(".onnx.json"):
                                    bout = t.extractfile(m).read()
                                    cible = dst + (".json" if m.name.endswith(".json") else "")
                                    with open(cible + ".part", "wb") as f:
                                        f.write(bout)
                                    os.replace(cible + ".part", cible)
                        os.remove(archive)
                        if voix_presente(n):
                            break
                    except Exception as e:
                        print("Jarvis : voix %s absente de GitHub (%s)" % (n, e))
            if not piper_pret(cfg):
                raise RuntimeError("aucune voix n'a pu etre telechargee")
            PIPER.update(etat="pret", progres=1.0,
                         message="" if voix_presente(nom) else
                         "La voix choisie n'a pas pu venir : Jarvis parle avec la voix de secours.")
            return True
        except Exception as e:
            PIPER.update(etat="erreur", message="Voix non telechargee : %s" % str(e)[:120])
            print("Jarvis : voix neuronale indisponible (%s)" % e)
            return False


# ---------- la voix anglaise de Jarvis : Kokoro ----------

KOKORO = {"etat": "absent", "progres": 0.0, "message": ""}
_KOKORO_VERROU = threading.Lock()
_ESPEAK_VERROU = threading.Lock()     # les deux preparations peuvent vouloir l'archive en meme temps


def langue_jarvis(cfg):
    return "fr" if str(cfg.get("jarvis_langue", "en")) == "fr" else "en"


def dossier_kokoro():
    return os.path.join(dossier_jarvis(), "kokoro")


def fichier_kokoro(nom):
    return os.path.join(dossier_kokoro(), nom)


def kokoro_present():
    """Les deux fichiers, a l'octet pres : un telechargement coupe ne passe
    jamais pour complet."""
    return all(os.path.isfile(fichier_kokoro(n)) and os.path.getsize(fichier_kokoro(n)) == taille
               for n, taille in _jv.KOKORO_TAILLES.items())


def voix_kokoro_choisie(cfg):
    v = str(cfg.get("jarvis_voix_kokoro") or _jv.KOKORO_DEFAUT)
    return v if v in _jv.VOIX_KOKORO else _jv.KOKORO_DEFAUT


def fils_kokoro():
    """La moitie des coeurs, entre deux et six : la phrase suivante se calcule
    pendant que la premiere se dit, sans prendre le PC."""
    return max(2, min(6, (os.cpu_count() or 4) // 2))


def voix_fr_choisie(cfg):
    """Sa voix francaise : une voix Kokoro (VOIX_KOKORO_FR), ou « piper » --
    alors c'est `jarvis_voix_modele`, une voix Piper ou celle de Windows."""
    v = str(cfg.get("jarvis_voix_fr") or _jv.KOKORO_FR_DEFAUT)
    return v if v == "piper" or v in _jv.VOIX_KOKORO_FR else _jv.KOKORO_FR_DEFAUT


def kokoro_voulu(cfg):
    """Kokoro sert-il ? Pour parler anglais, ou pour sa voix francaise."""
    return langue_jarvis(cfg) == "en" or voix_fr_choisie(cfg) != "piper"


def kokoro_fr_pret(cfg):
    """De quoi charger sa voix francaise par Kokoro, ou None (pas choisie, ou
    pas encore la : Piper parle en attendant)."""
    v = voix_fr_choisie(cfg)
    if v == "piper" or not kokoro_present() or not os.path.isfile(bibli_espeak()):
        return None
    return {"cle": "fr", "moteur": "kokoro", "langue": "fr", "bibliotheque": bibli_espeak(),
            "donnees": os.path.join(dossier_piper(), "piper"), "espeak": _jv.KOKORO_ESPEAK_FR,
            "modele": fichier_kokoro(_jv.KOKORO_MODELE), "voix_fichier": fichier_kokoro(_jv.KOKORO_VOIX),
            "voix": v, "fils": fils_kokoro()}


def kokoro_pret(cfg):
    """De quoi charger la voix anglaise, ou None."""
    if langue_jarvis(cfg) != "en" or not kokoro_present() or not os.path.isfile(bibli_espeak()):
        return None
    return {"cle": "en", "moteur": "kokoro", "bibliotheque": bibli_espeak(),
            "donnees": os.path.join(dossier_piper(), "piper"), "espeak": _jv.KOKORO_ESPEAK,
            "modele": fichier_kokoro(_jv.KOKORO_MODELE), "voix_fichier": fichier_kokoro(_jv.KOKORO_VOIX),
            "voix": voix_kokoro_choisie(cfg), "fils": fils_kokoro()}


def preparer_kokoro(cfg, ouvrir=None):
    """Le modele (310 Mo) et les voix (27 Mo), une fois, depuis GitHub -- et
    espeak-ng, l'archive de Piper, s'il n'est pas deja la."""
    with _KOKORO_VERROU:
        if kokoro_present() and os.path.isfile(bibli_espeak()):
            KOKORO.update(etat="pret", progres=1.0, message="")
            return True
        ouvrir = ouvrir or (lambda url: urllib.request.urlopen(url, timeout=60, context=_contexte_ssl()))
        KOKORO.update(etat="preparation", progres=0.0, message="")
        try:
            os.makedirs(dossier_kokoro(), exist_ok=True)
            with _ESPEAK_VERROU:
                _preparer_espeak(ouvrir, (0.0, 0.06), KOKORO)
            for nom, part in ((_jv.KOKORO_VOIX, (0.06, 0.14)), (_jv.KOKORO_MODELE, (0.14, 1.0))):
                dst = fichier_kokoro(nom)
                if os.path.isfile(dst) and os.path.getsize(dst) == _jv.KOKORO_TAILLES[nom]:
                    continue
                _telecharger(_jv.KOKORO_SOURCE + nom, dst, ouvrir, part, KOKORO)
                if os.path.getsize(dst) != _jv.KOKORO_TAILLES[nom]:
                    os.remove(dst)
                    raise RuntimeError("%s : pas la taille attendue" % nom)
            KOKORO.update(etat="pret", progres=1.0, message="")
            return True
        except Exception as e:
            KOKORO.update(etat="erreur", message="Voix Kokoro non telechargee : %s" % str(e)[:120])
            print("Jarvis : voix Kokoro indisponible (%s)" % e)
            return False


def charges_voix(cfg):
    """Ce que porte le processus de la voix : l'anglais de Jarvis (Kokoro) et
    son francais -- celui du mode psy aussi -- par Kokoro s'il est choisi et
    la, sinon par Piper. Chacun s'il est la."""
    out = []
    k = kokoro_pret(cfg)
    if k:
        out.append(k)
    f = kokoro_fr_pret(cfg)
    if f:
        out.append(f)
    else:
        p = piper_pret(cfg)
        if p:
            out.append(dict(p, cle="fr", moteur="piper", fils=2))
    return out


def signature_voix(charges):
    return "|".join("%s:%s:%s" % (c["cle"], c["modele"], c.get("voix", c.get("locuteur", "")))
                    for c in charges)


VOIX_ENFANT_ARG = "--voix"
_VOIX_ENFANT = {"proc": None, "sock": None, "pret": False, "pretes": set(), "charge": None,
                "echecs": 0, "prochain": 0.0}
_VOIX_VERROU = threading.Lock()


def _commande_voix(port, secret):
    base = [sys.executable] if FIGE else [sys.executable, os.path.abspath(__file__)]
    return base + [VOIX_ENFANT_ARG, str(port), secret]


def voix_prete(cle=None):
    """Une voix chargee -- celle de cette langue, si on la nomme."""
    p = _VOIX_ENFANT["proc"]
    if not (p is not None and p.poll() is None and _VOIX_ENFANT["sock"] is not None
            and _VOIX_ENFANT["pret"]):
        return False
    return cle is None or cle in _VOIX_ENFANT["pretes"]


def envoyer_voix(objet):
    sock = _VOIX_ENFANT["sock"]
    if sock is None:
        return False
    try:
        _jv.envoyer(sock, objet, _VOIX_VERROU)
        return True
    except Exception:
        return False


def demarrer_voix(cfg):
    """Le processus de la voix, avec ses voix chargees UNE fois : l'anglais
    de Jarvis d'abord (c'est lui qui parle le plus), le francais ensuite."""
    arreter_voix()
    charges = charges_voix(cfg)
    if not charges:
        return False
    proc, sock = _lancer_enfant(lambda port, secret: _commande_voix(port, secret), "de la voix")
    _VOIX_ENFANT.update(proc=proc, sock=sock, pret=False, pretes=set(), charge=signature_voix(charges))
    threading.Thread(target=_lire_voix, args=(sock,), daemon=True).start()
    for c in charges:
        envoyer_voix(dict({"cmd": "charger", "silence": 0.2}, **c))
    return True


def arreter_voix():
    sock, proc = _VOIX_ENFANT["sock"], _VOIX_ENFANT["proc"]
    _VOIX_ENFANT.update(sock=None, proc=None, pret=False, pretes=set(), charge=None)
    _fermer_enfant(sock, proc)
    VOIX.enfant_perdu()


atexit.register(arreter_voix)


# LES SOUS-TITRES DU PANNEAU : ce que dit chaque texte envoye a la voix, et
# ou elle en est (l'evenement « dit » : telle phrase commence, elle dure tant).
SOUS_TITRES = {}


def sous_titre_courant(maintenant=None):
    """Ce que Jarvis a deja prononce, a l'instant."""
    st = JARVIS.get("sous_titre")
    if not st:
        return ""
    t = time.time() if maintenant is None else maintenant
    if st.get("k", -1) < 0:
        if not st.get("estime") or not st.get("t0"):
            return ""
        # la voix de Windows ne dit pas ou elle en est : au debit moyen d'une voix
        tout = " ".join(st["phrases"])
        return _jv.texte_dit([tout], 0, (t - st["t0"]) * _jv.LETTRES_PAR_S / max(1, len(tout)))
    return _jv.texte_dit(st["phrases"], st["k"], (t - st["t0"]) / max(0.1, st.get("duree") or 0.1))


def _lire_voix(sock):
    while True:
        try:
            ev = _jv.recevoir(sock)
        except Exception:
            ev = None
        if ev is None:
            break
        quoi = ev.get("evt")
        if quoi == "dit":
            st = SOUS_TITRES.get(ev.get("id"))
            if st is not None:
                st.update(k=int(ev.get("phrase") or 0), t0=time.time(), duree=float(ev.get("duree") or 0.0))
                JARVIS["sous_titre"] = st
        elif quoi == "debut":
            # IL PARLE : l'oreille guette qu'on lui coupe la parole
            envoyer_oreille({"cmd": "parole", "actif": True})
            if ev.get("id") in SOUS_TITRES:
                JARVIS["sous_titre"] = SOUS_TITRES[ev.get("id")]
        elif quoi == "pret":
            _VOIX_ENFANT["pretes"].add(str(ev.get("cle") or "fr"))
            _VOIX_ENFANT.update(pret=True, echecs=0)
            if ev.get("cle") == "en" or (ev.get("cle") == "fr" and kokoro_fr_pret(CFG)):
                KOKORO.update(etat="pret", message="")
        elif quoi == "fini":
            envoyer_oreille({"cmd": "parole", "actif": False})
            VOIX.fini(ev.get("id"), bool(ev.get("coupe")), ev.get("reste"))
        elif quoi == "erreur":
            print("Jarvis : voix : %s" % str(ev.get("message"))[:200])
            # La voix anglaise n'a pas pu se charger : on le DIT, au lieu de
            # laisser Jarvis parler avec la voix de Windows sans explication.
            if ev.get("cle") == "en":
                KOKORO.update(etat="erreur", message="Voix anglaise impossible a charger : %s"
                              % str(ev.get("message"))[:120])
    if _VOIX_ENFANT["sock"] is sock:
        # Tombee sans qu'on l'arrete : la voix de Windows prend le relais, et
        # celle-ci repart plus tard, de plus en plus lentement.
        n = _VOIX_ENFANT["echecs"]
        _VOIX_ENFANT.update(sock=None, pret=False, charge=None, echecs=n + 1,
                            prochain=time.time() + JARVIS_RELANCE_S[min(n, len(JARVIS_RELANCE_S) - 1)])
        VOIX.enfant_perdu()


class Voix:
    """Ce que Jarvis dit. La voix neuronale (Piper) vit dans son processus, le
    modele charge une fois : la premiere phrase sonne en quelques dizaines de
    millisecondes, les suivantes se calculent pendant qu'elle se dit, et
    `taire()` coupe au dixieme de seconde -- « Jarvis, stop ».

    Si elle n'est pas la (pas encore telechargee, ou tombee), c'est la voix de
    Windows (SAPI), dans un fil a part : mieux vaut une voix de GPS que pas de
    reponse du tout."""

    def __init__(self):
        self.file = []
        self.signal = threading.Event()
        self.couper = threading.Event()
        self.parle = False
        self.fil = None
        self.sapi = None
        self.disponible = os.name == "nt"      # la voix de Windows
        self.attentes = {}
        self.en_cours = {}          # ident -> (texte, fin, langue) : ce qu'il est en train de dire
        self.reprise = None         # ce qu'on lui a coupe, s'il faut le reprendre
        self.n = 0

    def peut_parler(self):
        return voix_prete() or self.disponible

    def dire(self, texte, fin=None, langue="fr"):
        """UNE VOIX PAR LANGUE : l'anglais par Kokoro, le francais par Piper.
        Si celle de la langue n'est pas chargee, la voix de Windows DANS CETTE
        LANGUE -- une voix francaise qui lit de l'anglais est pire qu'un GPS."""
        langue = "en" if langue == "en" else "fr"
        texte = _jv.texte_pour_piper(texte, langue)
        if not texte:
            if fin:
                fin()
            return
        cle = langue if voix_prete(langue) else (None if self.disponible else
                                                  ("fr" if voix_prete("fr") else "en" if voix_prete("en") else None))
        if cle:
            self.n += 1
            ident = self.n
            self.attentes[ident] = fin
            self.en_cours[ident] = (texte, fin, langue)
            SOUS_TITRES[ident] = {"phrases": _jv.decouper_phrases(texte) or [texte], "k": -1}
            for vieux in sorted(SOUS_TITRES)[:-6]:
                SOUS_TITRES.pop(vieux, None)
            self.parle = True
            if envoyer_voix({"cmd": "dire", "id": ident, "texte": texte, "cle": cle,
                             "lenteur": float(CFG.get("jarvis_lenteur", 0.95))}):
                return
            self.attentes.pop(ident, None)
            self.en_cours.pop(ident, None)
        if not self.disponible:
            if fin:
                fin()
            return
        JARVIS["sous_titre"] = {"phrases": [texte], "k": -1, "estime": True, "t0": time.time()}
        self.file.append((texte, fin, langue))
        self.signal.set()
        if self.fil is None or not self.fil.is_alive():
            self.fil = threading.Thread(target=self._tourner, daemon=True)
            self.fil.start()

    def fini(self, ident, coupe, reste=None):
        self.en_cours.pop(ident, None)
        if coupe and reste and self.reprise and self.reprise["id"] == ident:
            self.reprise["texte"] = reste       # a partir de la phrase coupee
        fin = self.attentes.pop(ident, None)
        if not self.attentes:
            self.parle = False
        if fin and not coupe:
            try:
                fin()
            except Exception:
                pass

    def enfant_perdu(self):
        """La voix est tombee en pleine phrase : on ne laisse pas la suite
        (la guirlande, l'ecoute d'apres) attendre une fin qui ne viendra pas."""
        attentes, self.attentes = self.attentes, {}
        self.en_cours, self.reprise = {}, None
        self.parle = False
        for fin in attentes.values():
            if fin:
                try:
                    fin()
                except Exception:
                    pass

    def taire(self, garder=False):
        """Il se tait. `garder` : on vient de lui couper la parole -- on garde
        ce qu'il disait, pour le reprendre si personne ne parlait en fait."""
        self.reprise = None
        if garder and self.en_cours:
            # la voix dit ses textes dans l'ordre : celui qui sonne est le plus
            # ancien ; ceux qui attendaient, « taire » les jette (sans « fini »)
            ident = min(self.en_cours)
            texte, fin, langue = self.en_cours[ident]
            self.reprise = {"id": ident, "texte": texte, "fin": fin, "langue": langue, "t": time.time()}
        self.en_cours.clear()
        self.file.clear()
        self.attentes.clear()
        envoyer_voix({"cmd": "taire"})
        self.couper.set()
        self.parle = False

    def reprendre(self):
        """Reprend ce qu'on lui a coupe (a partir de la phrase coupee), avec la
        meme suite qu'avant -- l'ecoute d'apres, la guirlande."""
        r, self.reprise = self.reprise, None
        if not r or not r.get("texte") or time.time() - r["t"] > 30.0:
            return False
        self.dire(r["texte"], r["fin"], r["langue"])
        return True

    def oublier_reprise(self):
        self.reprise = None

    # Les voix de Windows a essayer, par langue : l'anglais britannique d'abord
    # (809), puis l'americain (409) ; le francais (40C).
    _SAPI_LANGUES = {"fr": ("Language=40C",),
                     "en": ("Language=809;Gender=Male", "Language=409;Gender=Male", "Language=809",
                            "Language=409")}

    def _sapi(self, texte, langue="fr"):
        if self.sapi is None:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self.sapi = win32com.client.Dispatch("SAPI.SpVoice")
            self.sapi_voix = {}
            self.sapi_langue = None
        v = self.sapi
        if self.sapi_langue != langue:
            if langue not in self.sapi_voix:
                self.sapi_voix[langue] = None
                for requete in self._SAPI_LANGUES.get(langue, ()):
                    try:
                        trouvees = v.GetVoices(requete)
                        if trouvees.Count:
                            self.sapi_voix[langue] = trouvees.Item(0)
                            break
                    except Exception:
                        pass
            if self.sapi_voix[langue] is not None:
                v.Voice = self.sapi_voix[langue]
            self.sapi_langue = langue
        v.Rate = max(-10, min(10, entier(CFG.get("jarvis_debit", 0), 0)))
        v.Speak(texte, 1)                          # SVSFlagsAsync
        while not v.WaitUntilDone(100):
            if self.couper.is_set():
                v.Speak("", 3)                     # asynchrone + purge
                return False
        return True

    def _tourner(self):
        while True:
            self.signal.wait()
            self.signal.clear()
            while self.file:
                texte, fin, langue = self.file.pop(0)
                self.couper.clear()
                self.parle = True
                dit = True
                envoyer_oreille({"cmd": "parole", "actif": True})
                try:
                    dit = self._sapi(texte, langue)
                except Exception as e:
                    print("Jarvis : voix de Windows impossible (%s)" % type(e).__name__)
                finally:
                    self.parle = False
                    envoyer_oreille({"cmd": "parole", "actif": False})
                if fin and dit:
                    try:
                        fin()
                    except Exception:
                        pass


VOIX = Voix()


def jouer_son(genre):
    if CFG.get("jarvis_son", True):
        _jv.jouer(genre)


# ---------- le processus de l'oreille ----------

def _commande_oreille(port, secret):
    base = [sys.executable] if FIGE else [sys.executable, os.path.abspath(__file__)]
    return base + [JARVIS_ENFANT_ARG, str(port), secret, dossier_jarvis()]


def config_oreille(cfg):
    auto = bool(cfg.get("jarvis_auto_etalonnage", True))
    return {"cmd": "config", "gabarits": gabarits_jarvis() + (gabarits_auto() if auto else []),
            "auto": auto,
            "tolerant": bool(cfg.get("jarvis_tolerant", True)),
            "sensibilite": float(cfg.get("jarvis_sensibilite", 0.5)),
            "hey": bool(cfg.get("jarvis_hey", True)),
            "son": bool(cfg.get("jarvis_son", True)),
            "couper": bool(cfg.get("jarvis_couper", True)),
            "micro": str(cfg.get("jarvis_micro", "") or "")}


def liste_micros():
    """[(identifiant, nom)] des micros branches, sans les boucles des
    haut-parleurs. Vide hors de Windows ou si la liste n'est pas lisible."""
    try:
        import soundcard as sc
        return [(str(m.id), str(m.name)) for m in sc.all_microphones()]
    except Exception:
        return []


def envoyer_oreille(objet):
    sock = _OREILLE["sock"]
    if sock is None:
        return False
    try:
        _jv.envoyer(sock, objet, _OREILLE_VERROU)
        return True
    except Exception:
        return False


def oreille_vivante():
    p = _OREILLE["proc"]
    return p is not None and p.poll() is None and _OREILLE["sock"] is not None


def _lancer_enfant(commande, quoi):
    """Relance cet exe en processus enfant et attend sa poignee de main : un
    secret a usage unique, sur une socket locale. Rend (processus, socket)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(DICTEE_DEMARRAGE_S)
        secret = secrets.token_hex(16)
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                   | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        sortie = _JOURNAL if _JOURNAL is not None else None
        proc = subprocess.Popen(commande(srv.getsockname()[1], secret),
                                stdin=subprocess.DEVNULL, stdout=sortie, stderr=sortie, **kw)
        try:
            sock, _ = srv.accept()
        except socket.timeout:
            proc.kill()
            raise RuntimeError("le processus %s n'a pas demarre" % quoi)
        sock.settimeout(30)
        try:
            ok = secrets.compare_digest(_recevoir_trame(sock, 64), secret.encode())
        except Exception:
            ok = False
        if not ok:
            sock.close()
            proc.kill()
            raise RuntimeError("le processus %s n'a pas repondu comme prevu" % quoi)
        sock.settimeout(None)
    finally:
        srv.close()
    return proc, sock


def _fermer_enfant(sock, proc):
    if sock is not None:
        try:
            _envoyer_trame(sock, b"")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass
    if proc is not None and proc.poll() is None:
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def demarrer_oreille(cfg):
    arreter_oreille()
    JARVIS.update(etat="demarrage", message="Ouverture du micro...")
    proc, sock = _lancer_enfant(lambda port, secret: _commande_oreille(port, secret), "du micro")
    _OREILLE.update(proc=proc, sock=sock)
    envoyer_oreille(config_oreille(cfg))
    threading.Thread(target=_lire_oreille, args=(sock,), daemon=True).start()


def arreter_oreille():
    sock, proc = _OREILLE["sock"], _OREILLE["proc"]
    _OREILLE.update(sock=None, proc=None)
    _fermer_enfant(sock, proc)


atexit.register(arreter_oreille)


def _lire_oreille(sock):
    while True:
        try:
            ev = _jv.recevoir(sock)
        except Exception:
            ev = None
        if ev is None:
            break
        try:
            traiter_evenement(ev)
        except Exception as e:
            print("Jarvis : evenement non traite (%s: %s)" % (type(e).__name__, str(e)[:120]))
    if _OREILLE["sock"] is sock:
        # Tombe sans qu'on l'ait arrete : on le relance, de plus en plus
        # lentement -- un processus qui meurt au demarrage ne doit pas etre
        # relance chaque seconde (l'exe se decompresse a chaque fois).
        n = _OREILLE["echecs"]
        _OREILLE["echecs"] = n + 1
        _OREILLE["prochain"] = time.time() + JARVIS_RELANCE_S[min(n, len(JARVIS_RELANCE_S) - 1)]
        JARVIS.update(etat="erreur", message="Le micro s'est arrete ; il repart tout seul.")


def traiter_evenement(ev):
    quoi = ev.get("evt")
    if quoi == "pret":
        _OREILLE["echecs"] = 0
        JARVIS.update(etat="attente", message=message_attente())
        if "micro" in ev:
            # Le micro qu'il ecoute vraiment -- et s'il n'est pas celui choisi
            # (debranche), on le dit plutot que d'ecouter ailleurs en silence.
            JARVIS["micro"] = str(ev.get("micro") or "")
            JARVIS["micro_absent"] = not ev.get("trouve", True)
            if JARVIS["micro_absent"]:
                print("Jarvis : le micro choisi est introuvable, j'ecoute celui de Windows")
    elif quoi == "presque":
        # « Jarvis » passe pres du seuil sans le franchir : on le garde pour
        # l'afficher, avec de quoi y remedier.
        JARVIS["presque"] = (float(ev.get("distance") or 0), float(ev.get("seuil") or 0), time.time())
    elif quoi == "niveau":
        JARVIS["db"] = ev.get("db")
        JARVIS["coupure"] = ev.get("coupure")
    elif quoi == "coupure":
        # ON LUI COUPE LA PAROLE : il se tait net, et l'oreille ecoute deja la
        # suite -- elle fera une phrase comme une autre.
        print("Jarvis : on lui coupe la parole")
        VOIX.taire(garder=True)
        poser_led("ecoute")
        JARVIS.update(etat="ecoute", message="Je vous ecoute.")
        threading.Thread(target=prechauffer_dictee, daemon=True).start()
    elif quoi == "reveil":
        print("Jarvis : eveil (%s)" % ev.get("par"))
        VOIX.taire()
        mode_courant()
        # « Quand Jarvis s'allume, il doit toujours etre en mode Jarvis (meme
        # s'il etait en psychologue avant). » La seance continue tant qu'on se
        # repond sans le rappeler ; l'appeler, c'est revenir au majordome.
        JARVIS["reveil_par"] = ev.get("par")
        poser_mode("jarvis")
        poser_led("ecoute")
        declencher_routines("evenement", "reveil", CFG)
        JARVIS.update(etat="ecoute", message="Je vous ecoute.")
        # Le moteur de transcription se reveille PENDANT qu'on parle : sa
        # premiere phrase apres un long silence ne paie pas son chargement.
        threading.Thread(target=prechauffer_dictee, daemon=True).start()
    elif quoi == "vide":
        # Personne n'a parle apres la coupure (un clavier, une porte) : il
        # reprend sa phrase -- l'oreille, elle, a deja appris que c'etait de l'echo.
        if ev.get("apres_coupure") and reprendre_apres_coupure():
            return
        if JARVIS["etat"] == "ecoute":
            if JARVIS.get("suite_active"):
                JARVIS["suite_active"] = False
                if JARVIS.get("attend_veille"):
                    JARVIS["attend_veille"] = False       # toujours rien : il se rendort
                else:
                    return silence_apres_suite(CFG)
            poser_led(None)
            JARVIS.update(etat="attente", message=message_attente())
    elif quoi == "phrase":
        _JARVIS_TRAVAIL.append((ev.get("wav") or "", bool(ev.get("apres_coupure"))))
        _JARVIS_TRAVAIL_SIGNAL.set()
    elif quoi == "gabarit":
        _GABARIT_RECU["evt"] = ev
        _GABARIT_RECU["signal"].set()
    elif quoi == "verifier":
        # UN « JARVIS » PAS NET : l'oreille ecoute en silence ; on transcrit ces
        # quelques secondes, et il ne se reveille que si on y lit son nom
        threading.Thread(target=verifier_appel, args=(ev.get("wav") or "",), daemon=True).start()
    elif quoi == "gabarit_auto":
        # un appel qu'il avait rate de peu, puis une vraie conversation : il le garde
        try:
            if ajouter_gabarit_auto(ev.get("vecteurs")):
                print("Jarvis : une facon de plus de l'appeler, gardee seule (%d)" % len(gabarits_auto()))
                envoyer_oreille(config_oreille(CFG))
        except Exception as e:
            print("Jarvis : facon non gardee (%s)" % type(e).__name__)
    elif quoi == "erreur":
        print("Jarvis : %s" % str(ev.get("message"))[:200])
        JARVIS.update(etat="erreur", message=str(ev.get("message") or "")[:200])


def verifier_appel(wav64):
    """Tranche un appel pas net : « Jarvis » (meme ecorche) dans la
    transcription -> il se reveille ; sinon, il se rendort sans un bruit."""
    ok = False
    try:
        if etat_dictee()["etat"] == "pret":
            texte = transcrire(base64.b64decode(wav64))
            ok = _jv.contient_nom(texte)
    except Exception as e:
        print("Jarvis : verification impossible (%s)" % type(e).__name__)
    print("Jarvis : appel pas net %s" % ("confirme" if ok else "ecarte"))
    envoyer_oreille({"cmd": "verifie", "ok": ok})
    return ok


def reprendre_apres_coupure():
    """On lui avait coupe la parole pour rien : il reprend ou il en etait."""
    if not VOIX.reprise:
        return False
    print("Jarvis : coupe pour rien, il reprend")
    poser_led("parle")
    JARVIS.update(etat="parle", message="Je reprends.")
    if VOIX.reprendre():
        return True
    poser_led(None)
    JARVIS.update(etat="attente", message=message_attente())
    return False


def message_attente():
    if gabarits_jarvis():
        return "A l'ecoute : dis « Jarvis »."
    if CFG.get("jarvis_hey", True):
        return ("A l'ecoute : dis « Hey Jarvis » (a l'anglaise). Pour « Jarvis » tout "
                "seul, apprends-lui ta voix.")
    return "Apprends-lui ta voix pour qu'il reconnaisse « Jarvis »."


def veiller_sur_jarvis(cfg):
    """Tourne dans son fil : tient l'oreille ouverte quand on l'a demande,
    la ferme sinon, et la relance si elle tombe (de plus en plus lentement)."""
    while ETAT["en_marche"]:
        try:
            voulu = bool(cfg.get("jarvis_actif", False))
            vivant = oreille_vivante()
            if voulu and not vivant and time.time() >= _OREILLE["prochain"]:
                if not modeles_jarvis_prets():
                    JARVIS.update(etat="preparation", message="Telechargement du mot d'eveil (3,6 Mo)...")
                    if not preparer_jarvis():
                        _OREILLE["prochain"] = time.time() + 60
                        continue
                if (cfg.get("jarvis_voix", True) and voix_choisie(cfg) != "windows"
                        and PIPER["etat"] in ("absent",) and not piper_pret(cfg)):
                    threading.Thread(target=preparer_piper, args=(cfg,), daemon=True).start()
                if dictee_possible() and etat_dictee()["etat"] == "absent":
                    # La transcription est celle de la dictee : on la prepare
                    # (reprise de Handy, ou telechargement unique de 456 Mo).
                    threading.Thread(target=preparer_dictee, daemon=True).start()
                try:
                    demarrer_oreille(cfg)
                except Exception as e:
                    n = _OREILLE["echecs"]
                    _OREILLE["echecs"] = n + 1
                    _OREILLE["prochain"] = time.time() + JARVIS_RELANCE_S[min(n, len(JARVIS_RELANCE_S) - 1)]
                    JARVIS.update(etat="erreur", message="Micro indisponible : %s" % str(e)[:120])
                    print("Jarvis : oreille impossible (%s)" % e)
            elif not voulu and (vivant or _OREILLE["proc"] is not None):
                arreter_oreille()
                VOIX.taire()
                poser_led(None)
                JARVIS.update(etat="eteint", message="")
            elif voulu and not vivant and _OREILLE["proc"] is not None:
                # Tombe en route : on nettoie, la prochaine boucle relance.
                arreter_oreille()
                n = _OREILLE["echecs"]
                _OREILLE["echecs"] = n + 1
                _OREILLE["prochain"] = time.time() + JARVIS_RELANCE_S[min(n, len(JARVIS_RELANCE_S) - 1)]
            if not voulu and JARVIS["etat"] != "eteint" and _OREILLE["proc"] is None:
                JARVIS.update(etat="eteint", message="")
            # LA VOIX : un processus a part, ses voix chargees tant qu'il ecoute.
            # Relancee si elle tombe, rechargee si on en change.
            veut_voix = voulu and cfg.get("jarvis_voix", True)
            # La voix anglaise se telecharge des qu'elle manque, pas seulement
            # au demarrage de l'oreille : passer Jarvis en anglais la fait venir.
            if (veut_voix and kokoro_voulu(cfg) and KOKORO["etat"] == "absent"
                    and not kokoro_present()):
                KOKORO["etat"] = "preparation"
                threading.Thread(target=preparer_kokoro, args=(cfg,), daemon=True).start()
            charges = charges_voix(cfg) if veut_voix else []
            if charges and time.time() >= _VOIX_ENFANT["prochain"] and (
                    _VOIX_ENFANT["proc"] is None or _VOIX_ENFANT["proc"].poll() is not None
                    or _VOIX_ENFANT["charge"] != signature_voix(charges)):
                try:
                    demarrer_voix(cfg)
                except Exception as e:
                    n = _VOIX_ENFANT["echecs"]
                    _VOIX_ENFANT.update(echecs=n + 1, prochain=time.time()
                                        + JARVIS_RELANCE_S[min(n, len(JARVIS_RELANCE_S) - 1)])
                    print("Jarvis : voix neuronale impossible (%s)" % e)
            elif not charges and _VOIX_ENFANT["proc"] is not None:
                arreter_voix()
        except Exception as e:
            print("Jarvis : veille (%s)" % e)
        time.sleep(1.0)


def fil_jarvis_travail(cfg):
    """Les phrases, une a la fois, dans l'ordre."""
    while ETAT["en_marche"]:
        _JARVIS_TRAVAIL_SIGNAL.wait(1.0)
        _JARVIS_TRAVAIL_SIGNAL.clear()
        while _JARVIS_TRAVAIL:
            wav64, apres_coupure = _JARVIS_TRAVAIL.pop(0)
            try:
                traiter_phrase(wav64, cfg, apres_coupure)
            except Exception as e:
                print("Jarvis : phrase non traitee (%s)" % type(e).__name__)
                signaler_erreur("Un incident de mon côté, je le crains.")


def demarrer_jarvis(cfg):
    threading.Thread(target=veiller_sur_jarvis, args=(cfg,), daemon=True).start()
    threading.Thread(target=fil_jarvis_travail, args=(cfg,), daemon=True).start()


# ---------- ce qu'on fait d'une phrase ----------

def prechauffer_dictee():
    """Charge le moteur de transcription s'il dort, avec une phrase de
    silence (qui ne rend rien). Ne fait rien s'il est deja la."""
    if etat_dictee()["etat"] != "pret":
        return
    with _DICTEE_VERROU:
        if _MOTEUR["proc"] is not None and _MOTEUR["proc"].poll() is None:
            return
        try:
            sock = _moteur_vivant()
            silence = _jv.wav_de(__import__("numpy").zeros(int(_jv.FREQ * 0.4), dtype="int16"))
            _envoyer_trame(sock, silence)
            _recevoir_trame(sock)
            _MOTEUR["vu"] = time.time()
        except Exception as e:
            print("Jarvis : prechauffage impossible (%s)" % type(e).__name__)
            _arreter_moteur()
            return
    _programmer_dechargement()


PSY_DUREE_S = 180            # le mode psy se referme apres trois minutes sans un mot
CONVERSATION_S = 300         # au-dela, le majordome oublie la conversation d'avant
_OUI = {"oui", "ouais", "oui vas y", "vas y", "d'accord", "ok", "okay", "volontiers", "allez",
        "oui merci", "oui s'il te plait", "oui s'il vous plait", "oui stp", "carrement", "bien sur",
        "oui oui", "ouais vas y", "go", "oui volontiers", "oui je veux bien", "je veux bien",
        "yes", "yeah", "yep", "sure", "yes please", "please", "please do", "go ahead", "do it",
        "of course", "absolutely", "certainly", "yes do", "why not", "sounds good", "ok go ahead"}

# CE QUE JARVIS DIT DE LUI-MEME, dans ses deux langues. Le mode psy parle
# francais (le compagnon est francais) ; le majordome parle la langue choisie.
_PHRASES = {
    "code_demande": ("Code d'accès ?", "Access code, please."),
    "code_faux": ("Ce n'est pas le bon code. Encore une fois ?", "That's not the code. Once more?"),
    "code_refuse": ("Accès refusé.", "Access denied."),
    "verrouille": ("Accès verrouillé.", "Access locked."),
    "rester": ("Je reste à l'écoute, ou je me mets en veille ?", "Shall I keep listening, or go on standby?"),
    "j_ecoute": ("Je vous écoute.", "I'm listening."),
    "mains_fermees": ("Mes mains sur le PC sont fermées : Réglages, Jarvis.",
                      "My hands on the PC are closed: Settings, Jarvis."),
    "youtube_video": ("C'est lancé.", "Here you go."),
    "youtube_resultats": ("Les résultats de YouTube sont à l'écran.", "I've opened the YouTube results."),
    "youtube_rate": ("YouTube ne répond pas.", "YouTube isn't answering."),
    "son_rate": ("Je ne parviens pas à régler le son.", "I can't set the volume."),
    "oui": ("Oui ?", "Yes?"),
    "mode_psy": ("Mode psychologue. Je vous écoute.", None),
    "mode_jarvis": ("Mode Jarvis. À votre service.", "At your service."),
    "retour": ("Content de vous revoir.", "Welcome back."),
    "lecture": ("Je n'ai pas pu lire ce que le micro m'a donné.", "I couldn't read what the microphone gave me."),
    "transcription_absente": ("La transcription n'est pas encore prête. Jetez un œil à la page Jarvis de Machi Tool.",
                              "Transcription isn't ready yet. Have a look at the Jarvis page in Machi Tool."),
    "transcription_ratee": ("Je vous demande pardon, je n'ai pas saisi.", "Sorry, I couldn't make that out."),
    "commande_ratee": ("Je crains de ne pas avoir pu le faire.", "I'm afraid I couldn't do that."),
    "rate": ("Un incident de mon côté, je le crains.", "Something went wrong on my side, I'm afraid."),
    "cle_absente": ("Pour vous répondre, il me faut la clé de BrainDebugger : page Passerelle de Machi Tool.",
                    "To answer you, I need the BrainDebugger key. It's on the Passerelle page of Machi Tool."),
    "cle_refusee": ("BrainDebugger refuse ma clé.", "BrainDebugger is refusing my key."),
    "bd_ancien_psy": ("Votre version de BrainDebugger ne sait pas encore m'écouter.", None),
    "bd_ancien_jarvis": ("Votre version de BrainDebugger ne connaît pas encore le mode Jarvis.",
                         "Your BrainDebugger doesn't know Jarvis mode yet."),
    "bd_sans_cle": ("BrainDebugger n'a pas de clé Claude pour me faire parler.",
                    "BrainDebugger has no Claude key to let me speak."),
    "bd_erreur": ("BrainDebugger a répondu par une erreur %s.", "BrainDebugger answered with error %s."),
    "api_cle": ("Anthropic refuse la clé API de BrainDebugger : vérifiez-la dans ses réglages, ou la variable "
                "ANTHROPIC_API_KEY sur Railway.",
                "Anthropic is refusing BrainDebugger's API key: check it in its settings, or ANTHROPIC_API_KEY on Railway."),
    "api_credit": ("Le crédit de la clé API Claude est épuisé.", "The Claude API key has run out of credit."),
    "api_surcharge": ("Claude est surchargé en ce moment. Réessayez dans un instant.",
                      "Claude is overloaded right now. Try again in a moment."),
    "api_limite": ("Trop de demandes à Claude d'un coup. Réessayez dans une minute.",
                   "Too many requests to Claude at once. Try again in a minute."),
    "bd_injoignable": ("Je n'arrive pas à joindre BrainDebugger.", "I can't reach BrainDebugger."),
    "compagnon_muet": ("Le compagnon n'a rien répondu.", None),
    "sans_reponse": ("Je n'ai rien à répondre à cela, curieusement.", "Curiously, I have nothing to say to that."),
    "dormir": ("Très bien. Je cesse d'écouter ; vous me réveillerez depuis Machi Tool.",
               "Very well. I'll stop listening; you can wake me from Machi Tool."),
    "annule": ("Annulé.", "Cancelled."),
    "aucun_minuteur": ("Il n'y avait aucun minuteur en cours.", "There were no timers running."),
    "synchro_coupee": ("L'envoi de votre journée est coupé dans Machi Tool.",
                       "Sending your day is switched off in Machi Tool."),
    "synchro": ("J'envoie votre journée à BrainDebugger.", "Sending your day to BrainDebugger."),
    "minuteur": ("Minuteur de %s, lancé.", "Timer set for %s."),
    "rappel_pose": ("Entendu. Je vous le rappelle dans %s.", "Very well. I'll remind you in %s."),
    "rappel": ("Je vous rappelle : %s.", "A reminder: %s."),
    "minuteur_fini": ("Le minuteur de %s est terminé.", "Your timer for %s is up."),
    "apprendre": ("Très bien. Chaque fois que la guirlande s'allume, dites mon nom, comme vous "
                  "m'appellerez. Huit fois : cinq normalement, puis comme une question, plus fort, "
                  "et plus bas. L'écran vous guide.",
                  "Very well. Each time the lights come on, say my name, the way you'll call me. "
                  "Eight times: five normally, then as a question, louder, and softer. The screen "
                  "will guide you."),
    "appris": ("C'est noté. Mon nom suffit, désormais.", "Noted. My name alone will do from now on."),
    "pas_appris": ("Je n'ai pas réussi à retenir votre voix. Nous réessaierons au calme.",
                   "I couldn't quite learn your voice. Let's try again somewhere quieter."),
    "astuce_voix": ("Oui ? Pour m'appeler juste par mon nom, dites : apprends ma voix.",
                    "Yes? By the way, to call me by my name alone, just say: learn my voice."),
}


def langue_du_mode(cfg=None):
    """Le mode psy parle francais ; le majordome, la langue choisie."""
    return "fr" if JARVIS.get("mode") == "psy" else langue_jarvis(cfg if cfg is not None else CFG)


def phrase(cle, langue, *args):
    fr, en = _PHRASES[cle]
    t = en if langue == "en" and en else fr
    return t % args if args else t


SOUVENIRS_MAX = 30          # gardes sur le PC
SOUVENIRS_ENVOYES = 15      # envoyes avec chaque question


def _en_fond(f):
    threading.Thread(target=f, daemon=True).start()


def resumer_conversation(historique, cfg):
    """Une phrase sur la conversation qui vient de finir, ecrite par
    BrainDebugger, gardee dans la config. Rien si c'etait une commande, un
    bonjour, ou si quelque chose de grave y est passe (BrainDebugger le voit)."""
    if not _cle_presente(cfg) or not any(h.get("role") == "user" for h in historique):
        return None
    try:
        donnees = _requete_bd("/api/machitool/jarvis", {"transition": "resume", "historique": historique[-12:],
                                                        "langue": langue_jarvis(cfg)}, cfg, 60)
    except Exception:
        return None
    texte = " ".join(str((donnees or {}).get("texte") or "").split())[:200]
    if not texte:
        return None
    souvenir = {"date": time.strftime("%Y-%m-%d"), "texte": texte}
    cfg["jarvis_souvenirs"] = (list(cfg.get("jarvis_souvenirs") or []) + [souvenir])[-SOUVENIRS_MAX:]
    sauver_config(cfg)
    return souvenir


def clore_historique(cfg=None):
    """La conversation en mode Jarvis se termine : on s'en souvient en une
    phrase (en arriere-plan), et on repart de zero."""
    historique = list(JARVIS.get("historique") or [])
    JARVIS["historique"] = []
    JARVIS["veille_demandee"] = False
    if historique and JARVIS.get("mode", "jarvis") == "jarvis":
        cfg = CFG if cfg is None else cfg
        _en_fond(lambda: resumer_conversation(historique, cfg))


def souvenirs_a_envoyer(cfg):
    return ["%s : %s" % (time.strftime("%d/%m", time.strptime(s_["date"], "%Y-%m-%d")), s_["texte"])
            for s_ in (cfg.get("jarvis_souvenirs") or [])[-SOUVENIRS_ENVOYES:]
            if isinstance(s_, dict) and s_.get("texte") and s_.get("date")]


def poser_mode(mode):
    if mode != JARVIS.get("mode"):
        clore_historique()
        if mode == "psy":
            # ce qui se dit au psychologue, gardé en memoire le temps de la
            # seance -- pour savoir, a l'au revoir, s'il faut se taire
            JARVIS["psy_echange"] = []
            JARVIS["psy_grave"] = False
    JARVIS.update(mode=mode, mode_vu=time.time(), propose_psy=False)


def mode_courant(maintenant=None):
    t = time.time() if maintenant is None else maintenant
    if JARVIS.get("mode") == "psy" and t - JARVIS.get("mode_vu", 0.0) > PSY_DUREE_S:
        poser_mode("jarvis")
    if t - JARVIS.get("vu", 0.0) > CONVERSATION_S and JARVIS.get("historique"):
        clore_historique()
        JARVIS["propose_psy"] = False
    return JARVIS.get("mode", "jarvis")


def terminer_conversation():
    """« Non rien », « oublie », « degage » : on se tait, on n'ecoute plus la
    suite, le mode psy se referme, la guirlande rend la main."""
    VOIX.taire()
    envoyer_oreille({"cmd": "annuler"})
    poser_mode("jarvis")
    clore_historique()
    JARVIS["attente_code"] = None
    poser_led(None)
    JARVIS.update(etat="attente", message=message_attente())
    jouer_son("fin")
    declencher_routines("evenement", "au_revoir", CFG)


_ADIEUX = {
    "bonne nuit": ("Bonne nuit", "Good night"), "good night": ("Bonne nuit", "Good night"),
    "goodnight": ("Bonne nuit", "Good night"), "a demain": ("À demain", "Until tomorrow"),
    "bonne soiree": ("Bonne soirée", "Have a good evening"),
    "bonne journee": ("Bonne journée", "Have a good day"),
}


def dire_adieu(mot, cfg):
    """IL REPOND, PUIS IL S'ETEINT : « À bientôt », « Au revoir », « Bonne nuit »
    -- suivi de la facon dont il vous appelle, si on la lui a donnee (Reglages
    > Jarvis > « Il t'appelle ») : jamais « Monsieur » d'office. Pas de suite :
    l'oreille retourne a la veille, il faudra le rappeler."""
    L = langue_jarvis(cfg)
    envoyer_oreille({"cmd": "annuler"})
    poser_mode("jarvis")
    clore_historique(cfg)
    if mot in _ADIEUX:
        fr, en = _ADIEUX[mot]
    else:
        fr, en = random.choice((("À bientôt", "See you soon"), ("Au revoir", "Goodbye")))
    base = en if L == "en" else fr
    qui = str(cfg.get("jarvis_appellation", "") or "").strip()
    texte = base + (", " + qui if qui else "") + "."
    dire(texte, suite=False, langue=L)
    jouer_son("fin")
    return texte


def quitter_psy(cfg):
    """« AU REVOIR » AU PSYCHOLOGUE : retour au majordome, qui a demande en
    toutes lettres « il peut ne pas parler si la discussion etait intense, il
    peut aussi rebondir sur un sujet de maniere humoristique mais pas lourde ».

    C'est BrainDebugger qui en decide, avec la seance sous les yeux (elle est
    deja dans son journal : rien de neuf ne sort d'ici) -- et qui se tait
    TOUJOURS si un message grave y est passe. Ici aussi : `psy_grave` coupe
    avant meme de demander."""
    echange = list(JARVIS.get("psy_echange") or [])[-12:]
    grave = bool(JARVIS.get("psy_grave"))
    VOIX.taire()
    envoyer_oreille({"cmd": "annuler"})
    poser_mode("jarvis")
    JARVIS["historique"] = []
    JARVIS.update(psy_echange=[], psy_grave=False)
    retour = ""
    if echange and not grave and _cle_presente(cfg):
        poser_led("pense")
        JARVIS.update(etat="pense", message="Retour au majordome...")
        try:
            d = _requete_bd("/api/machitool/jarvis",
                            {"texte": "au revoir", "transition": "fin_psy", "psy": echange,
                             "langue": langue_jarvis(cfg),
                             "appellation": str(cfg.get("jarvis_appellation", "") or "")[:40]}, cfg, 30)
            if (d or {}).get("mode") == "jarvis":
                retour = str((d or {}).get("texte") or "").strip()
        except Exception:
            retour = ""
    poser_led(None)
    JARVIS.update(etat="attente", message=message_attente())
    if retour:
        dire(retour, langue=langue_jarvis(cfg))
    else:
        jouer_son("fin")


def echanges_en_cours():
    """Combien de fois la personne a parle dans cette conversation."""
    if JARVIS.get("mode") == "psy":
        return sum(1 for h in JARVIS.get("psy_echange") or [] if h.get("role") == "user")
    return sum(1 for h in JARVIS.get("historique") or [] if h.get("role") == "user")


def silence_apres_suite(cfg):
    """Personne n'a parle pendant l'ecoute d'apres sa reponse. Une vraie
    conversation qui retombe : il demande, une fois, s'il reste a l'ecoute.
    Sinon il se rendort."""
    if _jv.doit_demander_veille(echanges_en_cours(), JARVIS.get("veille_demandee")):
        JARVIS.update(veille_demandee=True, attend_veille=True)
        L = langue_du_mode(cfg)
        return dire(phrase("rester", L), suite=True, langue=L)
    JARVIS["attend_veille"] = False
    poser_led(None)
    JARVIS.update(etat="attente", message=message_attente())


def dire(texte, suite=False, langue=None):
    """Repond : a voix haute si on l'a voulu, sinon en notification. Ensuite,
    s'il y a une suite possible, on ecoute encore un peu -- sans mot d'eveil.
    La langue est celle du mode, sauf si on la donne."""
    langue = langue or langue_du_mode()
    JARVIS["reponse_affichee"] = str(texte or "")

    def fin():
        poser_led(None)
        JARVIS.update(etat="attente", message=message_attente())
        if suite and CFG.get("jarvis_suite", True) and oreille_vivante():
            jouer_son("eveil")
            poser_led("ecoute")
            JARVIS.update(etat="ecoute", message="Je vous ecoute encore un instant.", suite_active=True)
            envoyer_oreille({"cmd": "ecouter", "attente": _jv.attente_suite(texte, echanges_en_cours(),
                                                                            JARVIS.get("mode", "jarvis"))})
    if CFG.get("jarvis_voix", True) and VOIX.peut_parler():
        poser_led("parle")
        JARVIS.update(etat="parle", message="Je reponds.")
        VOIX.dire(texte, fin, langue)
    else:
        notifier = JARVIS_CROCHETS.get("notifier")
        if notifier and texte:
            notifier("Jarvis", _jv.pour_la_voix(texte, 240))
        fin()


def dire_et_attendre(texte, langue=None, delai=30.0):
    """Dit, et rend la main quand c'est dit (ou apres `delai`)."""
    fini = threading.Event()
    langue = langue or langue_du_mode()
    if CFG.get("jarvis_voix", True) and VOIX.peut_parler():
        VOIX.dire(texte, fini.set, langue)
        fini.wait(delai)
    return fini.is_set()


def signaler_erreur(texte):
    poser_led("erreur", 1.6)
    jouer_son("erreur")
    JARVIS.update(etat="erreur", message=texte)
    if CFG.get("jarvis_voix", True) and VOIX.peut_parler():
        VOIX.dire(texte, lambda: JARVIS.update(etat="attente", message=message_attente()),
                  langue_du_mode())


def traiter_phrase(wav64, cfg, apres_coupure=False):
    poser_led("comprend")
    JARVIS.update(etat="comprend", message="Je transcris...")
    L = langue_du_mode(cfg)
    try:
        octets = base64.b64decode(wav64)
    except Exception:
        return signaler_erreur(phrase("lecture", L))
    if etat_dictee()["etat"] != "pret":
        return signaler_erreur(phrase("transcription_absente", L))
    try:
        texte = transcrire(octets)
    except DicteeImpossible as e:
        return signaler_erreur(str(e)[:160])
    except Exception as e:
        print("Jarvis : transcription impossible (%s)" % type(e).__name__)
        return signaler_erreur(phrase("transcription_ratee", L))
    finally:
        octets = None
    brut = texte
    texte = _jv.retirer_mot_eveil(texte)
    JARVIS["suite_active"] = False
    if JARVIS.pop("attend_veille", False):
        # la reponse a « Je reste a l'ecoute ? »
        choix = _jv.reponse_veille(texte)
        if choix == "reste":
            return dire(phrase("j_ecoute", langue_du_mode(cfg)), suite=True, langue=langue_du_mode(cfg))
        if choix == "veille":
            return terminer_conversation()
    att = JARVIS.get("attente_code")
    if att:
        # LA REPONSE A « CODE D'ACCES ? » -- comparee ici, jamais journalisee
        # ni envoyee. « Annule », « degage » : on laisse tomber.
        if time.time() > float(att.get("expire") or 0):
            JARVIS["attente_code"] = None
        elif _jv.renvoi(texte) or _jv.fin_de_conversation(texte):
            JARVIS["attente_code"] = None
            return terminer_conversation()
        elif not texte:
            return dire(phrase("code_demande", langue_jarvis(cfg)), suite=True, langue=langue_jarvis(cfg))
        else:
            return repondre_au_code(texte, cfg)
    if apres_coupure:
        if not texte:
            # Le micro a entendu quelque chose, mais pas des mots : c'etait
            # pour rien. L'oreille l'apprend, et il reprend sa phrase.
            envoyer_oreille({"cmd": "fausse_coupure"})
            if reprendre_apres_coupure():
                return
        else:
            VOIX.oublier_reprise()
    if not texte and _jv.renvoi(brut):
        # « Degage, Jarvis » : le nom vient APRES, et tout ce qui le precede est
        # coupe -- il ne restait rien, et il repondait « Oui ? ».
        print("Jarvis : renvoye")
        return terminer_conversation()
    if not texte and JARVIS.get("mode") != "psy" and _jv.adieu(brut):
        # « Bonne nuit, Jarvis » : le nom vient APRES l'au revoir, et tout ce
        # qui precede le mot d'eveil est coupe -- mais la phrase entiere n'est
        # que ca.
        print("Jarvis : au revoir")
        return dire_adieu(_jv.adieu(brut), cfg)
    if not texte:
        # « Jarvis. » tout court : il attend la suite -- et, UNE fois, s'il
        # a ete reveille par « Hey Jarvis » sans connaitre la voix, il dit
        # comment l'appeler par son nom seul.
        if (JARVIS.get("reveil_par") == "hey" and JARVIS.get("mode") == "jarvis"
                and not gabarits_jarvis() and not cfg.get("jarvis_astuce_voix")):
            cfg["jarvis_astuce_voix"] = True
            sauver_config(cfg)
            return dire(phrase("astuce_voix", L), suite=True)
        return dire(phrase("oui", L), suite=True)
    if _jv.renvoi(texte):
        # « Degage », « pars », « stop » : il part, sans un mot, quel que soit
        # le mode -- meme au psychologue, qui n'a pas le mot de la fin ici.
        print("Jarvis : renvoye")
        JARVIS.update(psy_echange=[], psy_grave=False)
        return terminer_conversation()
    mot = _jv.adieu(texte)
    if mot and JARVIS.get("mode") != "psy":
        # « Salut », « au revoir » : il repond sur le meme ton, puis s'eteint.
        # (Au psychologue, c'est `quitter_psy` : le majordome decide s'il dit
        # un mot ou se tait.)
        print("Jarvis : au revoir")
        return dire_adieu(mot, cfg)
    if _jv.fin_de_conversation(texte):
        print("Jarvis : fin de conversation")
        # « Au revoir » au psychologue : retour au majordome, qui se tait si
        # c'etait lourd -- voir `quitter_psy`.
        if JARVIS.get("mode") == "psy":
            return quitter_psy(cfg)
        return terminer_conversation()
    changement = _jv.changement_de_mode(texte)
    if changement and JARVIS.get("mode") != "psy" and cfg.get("jarvis_pc") and _jv.note_a_ecrire(texte):
        changement = None        # « note que... » : Jarvis l'ecrit lui-meme (et la passe au psy)
    if (changement is None and JARVIS.get("propose_psy")
            and _jv.normaliser(texte).replace("-", " ").strip(" '") in _OUI):
        changement = ("psy", "")
    JARVIS["propose_psy"] = False
    if changement:
        mode, reste = changement
        revient = JARVIS.get("mode") == "psy" and mode == "jarvis"
        poser_mode(mode)
        if revient:
            JARVIS.update(psy_echange=[], psy_grave=False)
        print("Jarvis : mode %s" % mode)
        if not reste:
            if mode == "psy":
                return dire(phrase("mode_psy", "fr"), suite=True, langue="fr")
            # « Jarvis ? Re ! » : de retour aupres du majordome
            return dire(phrase("retour" if revient else "mode_jarvis", langue_jarvis(cfg)), suite=True,
                        langue=langue_jarvis(cfg))
        texte = reste
    L = langue_du_mode(cfg)
    JARVIS["vu"] = time.time()
    # SES ROUTINES : « je vais me coucher » -> la lumiere du soir. Avec une
    # replique, c'est tout (un running gag se suffit) ; sans, la phrase suit
    # son chemin.
    if mode_courant() != "psy":
        r = declencher_routines("phrase", texte, cfg)
        if r and r.get("replique"):
            return dire(r["replique"], suite=False, langue=langue_jarvis(cfg))
    action = _jv.comprendre(texte, cfg.get("jarvis_raccourcis") or [])
    if action:
        print("Jarvis : commande %s" % action["action"])
        if action["action"] == "fin":
            return terminer_conversation()
        if action["action"] == "apprendre":
            threading.Thread(target=apprendre_a_voix_haute, args=(cfg,), daemon=True).start()
            return
        try:
            reponse = executer_commande(action, cfg)
        except Exception as e:
            print("Jarvis : commande ratee (%s)" % e)
            return signaler_erreur(phrase("commande_ratee", L))
        if action["action"] == "silence":
            poser_led(None)
            JARVIS.update(etat="attente", message=message_attente())
            jouer_son("fin")
            return
        poser_led("fait", 1.4)
        if reponse:
            dire(reponse)
        else:
            jouer_son("fait")
            JARVIS.update(etat="attente", message=message_attente())
        return
    if mode_courant() == "psy":
        JARVIS["mode_vu"] = time.time()
        return parler_au_compagnon(texte, cfg)
    return parler_a_jarvis(texte, cfg)


def _requete_bd(chemin, charge, cfg, delai):
    """POST a BrainDebugger avec la cle de la passerelle (GET si `charge` est
    None). Rend le JSON, leve urllib.error.HTTPError ou une erreur reseau."""
    base = str(cfg.get("pont_site", "")).strip().rstrip("/")
    cle = str(cfg.get("pont_cle", "")).strip()
    decalage = -(time.altzone if time.localtime().tm_isdst > 0 else time.timezone) // 3600
    entetes = {"User-Agent": "MachiToolkit/" + VERSION, "Content-Type": "application/json",
               "Authorization": "Bearer " + cle, "X-Machitool-Cle": cle,
               # Sa journee, pas celle du serveur : un fuseau a heure fixe suffit
               # pour dater MAINTENANT.
               "X-Fuseau": "UTC" if not decalage else "Etc/GMT%+d" % -decalage}
    corps = None if charge is None else json.dumps(charge, ensure_ascii=False).encode("utf-8")
    requete = urllib.request.Request(base + chemin, data=corps, headers=entetes)
    with urllib.request.urlopen(requete, timeout=delai, context=_contexte_ssl()) as r:
        return json.loads(r.read().decode("utf-8"))


def _cle_presente(cfg):
    return bool(str(cfg.get("pont_site", "")).strip() and str(cfg.get("pont_cle", "")).strip())


def _detail_http(e):
    return str(_corps_http(e).get("error") or "")


def _corps_http(e):
    """Le JSON d'une reponse d'erreur, lu une fois (la lecture vide le flux)."""
    if getattr(e, "_corps_lu", None) is None:
        try:
            e._corps_lu = json.loads(e.read().decode("utf-8")) or {}
        except Exception:
            e._corps_lu = {}
        if not isinstance(e._corps_lu, dict):
            e._corps_lu = {}
    return e._corps_lu


def erreur_bd(e, L, pour="jarvis"):
    """Ce qu'il dit quand BrainDebugger repond une erreur -- la CAUSE, quand on
    la connait (« BrainDebugger a repondu par une erreur 502 » ne disait pas
    quoi faire). Le detail va aussi au panneau et au journal."""
    corps = _corps_http(e)
    detail, raison = str(corps.get("error") or ""), str(corps.get("raison") or "")
    if detail:
        print("Jarvis : BrainDebugger %d -- %s" % (e.code, detail[:200]))
    if e.code in (401, 403):
        return phrase("cle_refusee", L)
    if e.code == 404:
        return phrase("bd_ancien_psy" if pour == "psy" else "bd_ancien_jarvis", L)
    if raison in ("cle", "credit", "surcharge", "limite"):
        return phrase("api_" + raison, L)
    if "clé API" in detail:
        return phrase("bd_sans_cle", L)
    return phrase("bd_erreur", L, e.code) + ((" " + detail[:160]) if detail and L == "fr" else "")


def parler_au_compagnon(texte, cfg):
    """Le mode psychologue : le compagnon de BrainDebugger, son fil, son journal."""
    if not _cle_presente(cfg):
        return signaler_erreur(phrase("cle_absente", "fr"))
    poser_led("pense")
    JARVIS.update(etat="pense", message="Le compagnon reflechit...")
    print("Jarvis : message au compagnon (%d signes)" % len(texte))
    try:
        donnees = _requete_bd("/api/machitool/parler", {"texte": texte}, cfg, 180)
    except urllib.error.HTTPError as e:
        return signaler_erreur(erreur_bd(e, "fr", pour="psy"))
    except Exception:
        return signaler_erreur(phrase("bd_injoignable", "fr"))
    reponse = str((donnees or {}).get("texte") or "").strip()
    if not reponse:
        return signaler_erreur(phrase("compagnon_muet", "fr"))
    JARVIS["mode_vu"] = time.time()
    JARVIS["psy_echange"] = (list(JARVIS.get("psy_echange") or []) + [
        {"role": "user", "texte": texte}, {"role": "assistant", "texte": reponse}])[-12:]
    dire(reponse, suite=True, langue="fr")


# ---------- ses mains sur le PC ----------
#
# « Donne l'acces total a Jarvis... lorsqu'il doit interagir il demande un
# code d'acces a l'oral avant d'effectuer l'operation. » BrainDebugger dit a
# Jarvis ce qu'il peut faire ; quand il veut un outil, la reponse revient ICI,
# on l'execute sur le poste, et on renvoie le resultat. Avant les dossiers, les
# fichiers et l'ecran, Jarvis demande le code a voix haute : la phrase qui suit
# est comparee a l'empreinte gardee dans la config, sur le poste -- elle n'est
# ni transcrite dans un journal, ni envoyee, ni ecrite nulle part. Juste, les
# mains restent ouvertes dix minutes ; trois faux, elles se ferment cinq.

OUTILS_SANS_CODE = {"musique", "spotify", "rechercher_google", "lien", "retenir", "oublier",
                    "lancer_appli", "fenetre", "son", "pc", "youtube", "onglets", "temperatures",
                    "spotify_jouer", "spotify_en_cours", "spotify_aimer", "montrer_agenda"}
# Ce qu'il retient de toi : toujours permis, meme sans ses mains sur le PC.
OUTILS_MEMOIRE = {"retenir", "oublier"}
ACCES_DUREE_S = 600
VERROU_DUREE_S = 300
OUTILS_TOURS_MAX = 5
OUVRIR_MAX = 10          # « ouvre-les » : dix au plus d'un coup
_TOUCHES_MEDIA = {"lecture_pause": 0xB3, "suivant": 0xB0, "precedent": 0xB1,
                  "volume_plus": 0xAF, "volume_moins": 0xAE, "muet": 0xAD}


def code_regle(cfg):
    return bool(cfg.get("jarvis_code_sel") and cfg.get("jarvis_code_empreinte"))


def poser_code(cfg, code):
    """Le code choisi dans les reglages : on n'en garde que l'empreinte."""
    if not _jv.normaliser_code(code):
        cfg["jarvis_code_sel"] = cfg["jarvis_code_empreinte"] = ""
        return False
    sel = os.urandom(16).hex()
    cfg["jarvis_code_sel"], cfg["jarvis_code_empreinte"] = sel, _jv.empreinte_code(code, sel)
    return True


def acces_ouvert():
    return time.time() < float(JARVIS.get("acces_jusqua") or 0)


def bases_dossiers():
    """Les dossiers qu'on nomme : Documents, Bureau, Telechargements..."""
    home = os.path.expanduser("~")
    bases = {"home": home}
    for cle, nom in (("documents", "Documents"), ("desktop", "Desktop"), ("downloads", "Downloads"),
                     ("pictures", "Pictures"), ("music", "Music"), ("videos", "Videos")):
        bases[cle] = os.path.join(home, nom)
    if os.name == "nt":
        try:
            # les vrais emplacements, meme deplaces (OneDrive, un autre disque)
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion"
                                r"\Explorer\User Shell Folders") as k:
                for cle, val in (("documents", "Personal"), ("desktop", "Desktop"),
                                 ("downloads", "{374DE290-123F-4565-9164-39C4925E467B}"),
                                 ("pictures", "My Pictures"), ("music", "My Music"), ("videos", "My Video")):
                    try:
                        bases[cle] = os.path.expandvars(winreg.QueryValueEx(k, val)[0])
                    except OSError:
                        pass
        except Exception:
            pass
    return bases


def dossiers_proteges():
    env = os.environ
    return [env.get("SystemRoot") or env.get("windir"), env.get("ProgramFiles"),
            env.get("ProgramFiles(x86)"), env.get("ProgramData")]


def touche_media(action):
    """Les touches multimedia du clavier, ENVOYEES (pas ecoutees) : Spotify et
    tout lecteur y repondent. Aucun crochet clavier : on n'ecoute rien."""
    vk = _TOUCHES_MEDIA.get(str(action))
    if vk is None:
        raise ValueError("action inconnue : %s" % action)
    if os.name != "nt":
        raise OSError("les touches multimedia ne se pilotent que sous Windows")
    import ctypes
    user = ctypes.WinDLL("user32")
    user.keybd_event(vk, 0, 0, 0)
    user.keybd_event(vk, 0, 2, 0)          # KEYEVENTF_KEYUP
    return {"lecture_pause": "Lecture ou pause.", "suivant": "Piste suivante.",
            "precedent": "Piste precedente.", "volume_plus": "Volume monte.",
            "volume_moins": "Volume baisse.", "muet": "Son coupe ou remis."}[action]


def ouvrir_spotify(recherche):
    q = str(recherche or "").strip()
    uri = "spotify:search:" + urllib.parse.quote(q) if q else "spotify:"
    try:
        os.startfile(uri)                  # l'application, si elle est installee
        return "Spotify ouvert" + (" sur « %s »." % q if q else ".")
    except Exception:
        import webbrowser
        webbrowser.open("https://open.spotify.com/search/" + urllib.parse.quote(q) if q
                        else "https://open.spotify.com")
        return "Spotify ouvert dans le navigateur" + (" sur « %s »." % q if q else ".")


def creer_fichier(chemin, contenu, protegees=()):
    """Un fichier texte NEUF (jarvis.preparer_fichier dit ou et quoi). Rend
    le chemin reellement ecrit."""
    ch, texte, encodage = _jv.preparer_fichier(chemin, contenu, protegees)
    os.makedirs(os.path.dirname(ch) or ".", exist_ok=True)
    with open(ch, "x", encoding=encodage, newline="") as f:
        f.write(texte)
    return ch


def ecrire_note(dossier, texte, titre="", ajouter_a="", maintenant=None):
    """Une note dans le dossier de Jarvis. Rend (chemin, neuve)."""
    ch, contenu, mode, encodage = _jv.preparer_note(dossier, texte, titre, ajouter_a, maintenant)
    os.makedirs(dossier, exist_ok=True)
    with open(ch, mode, encoding=encodage, newline="") as f:
        f.write(contenu)
    return ch, mode == "x"


def lire_historique_copie(genre, chemin, depuis):
    """Le navigateur tient son historique ouvert : on en lit une copie, dans
    un dossier temporaire efface en sortant."""
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory(prefix="machi-") as d:
        copie = os.path.join(d, "h.sqlite")
        shutil.copyfile(chemin, copie)
        if os.path.isfile(chemin + "-wal"):
            shutil.copyfile(chemin + "-wal", copie + "-wal")
        return _jv.lire_historique(genre, copie, depuis)


def chemin_chrome():
    """chrome.exe, s'il est installe : le registre (App Paths), puis les
    emplacements habituels."""
    if os.name != "nt":
        return None
    try:
        import winreg
        for racine in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(racine, r"Software\Microsoft\Windows\CurrentVersion\App Paths"
                                    r"\chrome.exe") as k:
                    p = winreg.QueryValueEx(k, "")[0]
                    if p and os.path.isfile(p):
                        return p
            except OSError:
                pass
    except Exception:
        pass
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA")):
        p = os.path.join(base or "", "Google", "Chrome", "Application", "chrome.exe")
        if base and os.path.isfile(p):
            return p
    return None


def ouvrir_dans_chrome(url):
    """Une adresse web dans Chrome (ou, sans Chrome, le navigateur par defaut)."""
    chrome = chemin_chrome()
    if chrome:
        subprocess.Popen([chrome, url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Chrome"
    import webbrowser
    webbrowser.open(url)
    return "le navigateur"


# --- APPLIS ET JEUX ----------------------------------------------------
# « Lance Discord », « lance Elden Ring » : le menu Demarrer (les raccourcis
# qu'on y voit) et les jeux Steam installes. Relus toutes les cinq minutes.

_APPLIS = {"liste": [], "quand": 0.0}


def racine_steam():
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                p = winreg.QueryValueEx(k, "SteamPath")[0]
                if p and os.path.isdir(p):
                    return os.path.normpath(p)
        except Exception:
            pass
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        p = os.path.join(base or "", "Steam")
        if base and os.path.isdir(p):
            return p
    return None


def applis_installees(frais=False):
    if frais or not _APPLIS["liste"] or time.time() - _APPLIS["quand"] > 300:
        menus = [os.path.join(os.environ[v], "Microsoft", "Windows", "Start Menu", "Programs")
                 for v in ("APPDATA", "ProgramData") if os.environ.get(v)]
        _APPLIS["liste"] = _jv.jeux_steam(racine_steam()) + _jv.raccourcis_menu(menus)
        _APPLIS["quand"] = time.time()
    return _APPLIS["liste"]


def lancer_appli(nom):
    trouves = _jv.choisir(nom, applis_installees())
    if not trouves:
        trouves = _jv.choisir(nom, applis_installees(frais=True))
    if not trouves:
        raise LookupError("Aucune appli ni aucun jeu installe ne s'appelle « %s »." % nom)
    if len({c for _, c, _ in trouves}) > 1:
        return "Plusieurs correspondent, lequel ? " + " ; ".join(n for n, _, _ in trouves[:6])
    n, cible, genre = trouves[0]
    startfile_sur(cible)
    return ("Jeu lance par Steam : %s." if genre == "jeu" else "Lance : %s.") % n


# --- FENETRES ----------------------------------------------------------
# Par les fonctions de Windows (ShowWindow, SetForegroundWindow, WM_CLOSE) :
# rien n'est clique ni tape. « Fermer » demande poliment : l'appli peut
# proposer d'enregistrer.

def fenetres_ouvertes():
    """[(hwnd, titre, processus)] des fenetres visibles de la barre des taches."""
    import ctypes
    import win32gui
    import win32process
    import psutil
    dwm = ctypes.WinDLL("dwmapi")
    out = []

    def voir(h, _):
        if not win32gui.IsWindowVisible(h) or win32gui.GetWindow(h, 4):     # GW_OWNER
            return True
        titre = win32gui.GetWindowText(h)
        if not titre or titre in ("Program Manager", "Machi Tool"):
            return True
        cache = ctypes.c_int(0)
        dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(cache), ctypes.sizeof(cache))   # DWMWA_CLOAKED
        if cache.value:
            return True
        try:
            proc = psutil.Process(win32process.GetWindowThreadProcessId(h)[1]).name()
        except Exception:
            proc = ""
        out.append((h, titre, proc))
        return True
    win32gui.EnumWindows(voir, None)
    return out


def agir_fenetre(action, cible="", tout=False):
    import win32gui
    import win32con
    fen = fenetres_ouvertes()
    if action == "lister":
        if not fen:
            return "Aucune fenetre ouverte."
        return "%d fenetres : %s" % (len(fen), " ; ".join("%s (%s)" % (t[:80], p.replace(".exe", ""))
                                                         for _, t, p in fen[:25]))
    if tout and action == "reduire":
        for h, _, _ in fen:
            win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
        return "Toutes les fenetres sont reduites."
    trouves = _jv.choisir(cible, fen, nom=lambda f: f[1] + " " + f[2].replace(".exe", ""), seuil=40)
    if not trouves:
        raise LookupError("Aucune fenetre ouverte ne correspond a « %s »." % cible)
    h, titre, _ = trouves[0]
    if action == "premier_plan":
        if win32gui.IsIconic(h):
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(h)
        except Exception:
            # Windows refuse parfois de donner le premier plan a qui ne l'a pas :
            # reduire puis restaurer, c'est l'y mettre sans rien simuler.
            win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
        return "Au premier plan : %s." % titre
    geste = {"reduire": win32con.SW_MINIMIZE, "agrandir": win32con.SW_MAXIMIZE,
             "restaurer": win32con.SW_RESTORE}.get(action)
    if geste is not None:
        win32gui.ShowWindow(h, geste)
        return {"reduire": "Reduite", "agrandir": "Agrandie", "restaurer": "Restauree"}[action] + " : %s." % titre
    if action == "fermer":
        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
        return "Fermeture demandee : %s (elle peut proposer d'enregistrer)." % titre
    raise ValueError("action inconnue : %s" % action)


# --- LE SON ------------------------------------------------------------
# Le volume general, ou celui d'une appli (« baisse Discord ») : le melangeur
# de Windows, par pycaw.

def _volume_general():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    haut_parleurs = AudioUtilities.GetSpeakers()
    ev = getattr(haut_parleurs, "EndpointVolume", None)
    if ev is not None:
        return ev
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    return cast(haut_parleurs.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))


def sessions_audio():
    """[(session pycaw, nom de l'exe, chemin)] des applis qui ont du son --
    y compris les jeux qu'un anti-triche cache a psutil (la session garde son
    PID : on lit son nom autrement)."""
    from pycaw.pycaw import AudioUtilities
    out = []
    for sess in AudioUtilities.GetAllSessions():
        pid = int(getattr(sess, "ProcessId", 0) or 0)
        if not pid:
            continue                                   # les sons du systeme
        try:
            nom = sess.Process.name() if sess.Process else ""
        except Exception:
            nom = ""
        nom = nom or _nom_du_processus(pid)
        if nom:
            out.append((sess, nom, _chemin_du_processus(pid)))
    return out


def _joli(nom):
    base = os.path.splitext(os.path.basename(nom))[0]
    return {"msedge": "Edge", "chrome": "Chrome", "firefox": "Firefox"}.get(base.lower(),
                                                                          base[:1].upper() + base[1:])


def regler_son(action, appli="", niveau=None):
    """Le volume general (sans appli) ou celui d'applis precises -- « le jeu »,
    « le navigateur », « la musique » compris. Rend une phrase."""
    if os.name != "nt":
        raise OSError("le volume ne se regle que sous Windows")
    if not appli:
        v = _volume_general()
        if action in ("couper", "remettre"):
            v.SetMute(1 if action == "couper" else 0, None)
            return "Son coupé." if action == "couper" else "Son remis."
        n = _jv.nouveau_niveau(v.GetMasterVolumeLevelScalar() * 100, action, niveau)
        v.SetMasterVolumeLevelScalar(n / 100.0, None)
        v.SetMute(0, None)
        return "Volume général à %d %%." % n
    sessions = sessions_audio()
    indices = _jv.cibles_son(appli, [(nom, chemin) for _, nom, chemin in sessions])
    if not indices:
        ouvertes = sorted({_joli(nom) for _, nom, _ in sessions})
        raise LookupError("Rien ne fait du son sous ce nom (%s) ; en ce moment : %s."
                          % (appli, ", ".join(ouvertes) or "aucune appli"))
    noms, faits = [], []
    for i in indices:
        sess, nom, _ = sessions[i]
        vol = sess.SimpleAudioVolume
        if action in ("couper", "remettre"):
            vol.SetMute(1 if action == "couper" else 0, None)
        else:
            n = _jv.nouveau_niveau(vol.GetMasterVolume() * 100, action, niveau)
            vol.SetMasterVolume(n / 100.0, None)
            vol.SetMute(0, None)
            faits.append(n)
        if _joli(nom) not in noms:
            noms.append(_joli(nom))
    qui = " et ".join(noms)
    if action == "couper":
        return "Son de %s coupé." % qui
    if action == "remettre":
        return "Son de %s remis." % qui
    return "Volume de %s à %d %%." % (qui, faits[0])


def lister_sons():
    """« Qu'est-ce qui fait du son ? » : chaque appli et son volume."""
    if os.name != "nt":
        raise OSError("le volume ne se lit que sous Windows")
    vus = {}
    for sess, nom, chemin in sessions_audio():
        vol = sess.SimpleAudioVolume
        cle = _joli(nom) + (" (jeu)" if _jv.est_un_jeu(chemin, nom) else "")
        vus.setdefault(cle, "coupé" if vol.GetMute() else "%d %%" % round(vol.GetMasterVolume() * 100))
    if not vus:
        return "Aucune appli ne fait de son."
    return "En ce moment : " + ", ".join("%s %s" % (k, v) for k, v in vus.items()) + "."


# --- LE PC : VERROUILLER, LUMINOSITE ------------------------------------
# « Qu'il ne puisse pas eteindre, redemarrer ou mettre en veille l'ordinateur,
# ni fermer la session » : il n'y a pas de fonction pour ca, et
# `startfile_sur` refuse ce qui le ferait par la bande (voir
# touche_a_l_alimentation dans jarvis.py). Verrouiller ne ferme rien.

def verrouiller_pc():
    import ctypes
    ctypes.WinDLL("user32").LockWorkStation()
    return "PC verrouille."


def startfile_sur(chemin):
    """os.startfile, sauf ce qui eteindrait, redemarrerait, mettrait en veille
    le PC ou fermerait la session."""
    if _jv.touche_a_l_alimentation(chemin):
        raise PermissionError(_jv.REFUS_ALIMENTATION)
    os.startfile(chemin)


def _dxva2():
    """dxva2, avec ses types : sans eux, ctypes passerait les handles en entier
    32 bits, et un handle 64 bits serait tronque."""
    import ctypes
    from ctypes import wintypes

    class MONITEUR(ctypes.Structure):
        _fields_ = [("h", wintypes.HANDLE), ("nom", wintypes.WCHAR * 128)]
    d = ctypes.WinDLL("dxva2")
    P = ctypes.POINTER
    d.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, P(wintypes.DWORD)]
    d.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, P(MONITEUR)]
    d.GetMonitorBrightness.argtypes = [wintypes.HANDLE, P(wintypes.DWORD), P(wintypes.DWORD), P(wintypes.DWORD)]
    d.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    d.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, P(MONITEUR)]
    return d, MONITEUR


def luminosites():
    """Les ecrans qui se reglent par le cable (DDC/CI) : ([(handle physique,
    mini, actuel, maxi)], tableaux a rendre a DestroyPhysicalMonitors)."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")
    dxva2, MONITEUR = _dxva2()
    hmons = []
    Rappel = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    rappel = Rappel(lambda hm, hdc, r, lp: hmons.append(hm) or True)
    user32.EnumDisplayMonitors(None, None, rappel, 0)
    ecrans, tableaux = [], []
    for hm in hmons:
        n = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hm, ctypes.byref(n)) or not n.value:
            continue
        tab = (MONITEUR * n.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(hm, n.value, tab):
            continue
        tableaux.append((n.value, tab))
        for m in tab:
            mini, cour, maxi = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
            if dxva2.GetMonitorBrightness(m.h, ctypes.byref(mini), ctypes.byref(cour), ctypes.byref(maxi)):
                ecrans.append((m.h, mini.value, cour.value, maxi.value))
    return ecrans, tableaux


def regler_luminosite(action, niveau=None):
    """Tous les ecrans : par le cable (DDC/CI) pour les ecrans externes, par
    Windows (WMI) pour celui d'un portable."""
    if os.name != "nt":
        raise OSError("la luminosite ne se regle que sous Windows")
    dxva2, _ = _dxva2()
    ecrans, tableaux = luminosites()
    faits = []
    try:
        for h, mini, cour, maxi in ecrans:
            pct = 100.0 * (cour - mini) / max(1, maxi - mini)
            n = _jv.nouveau_niveau(pct, action, niveau)
            if dxva2.SetMonitorBrightness(h, int(round(mini + (maxi - mini) * n / 100.0))):
                faits.append(n)
    finally:
        for n, tab in tableaux:
            dxva2.DestroyPhysicalMonitors(n, tab)
    if faits:
        return "Luminosite a %d %% (%d ecran%s)." % (faits[0], len(faits), "s" if len(faits) > 1 else "")
    if action != "regler":
        raise OSError("Aucun ecran ne dit sa luminosite : donne un niveau precis, par exemple 50 %.")
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods) | "
                        "Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{Timeout=1;Brightness=%d}"
                        % _jv.nouveau_niveau(0, "regler", niveau)],
                       capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise OSError("Ces ecrans ne se reglent pas depuis Windows (DDC/CI coupe dans le menu de l'ecran ?).")
    return "Luminosite a %d %%." % _jv.nouveau_niveau(0, "regler", niveau)


# --- LES ONGLETS DE CHROME ---------------------------------------------
# « Il faut qu'il puisse fermer ou ouvrir des onglets. » Par une petite
# extension de Machi Tool, installee dans Chrome (ou Edge, Brave) : elle
# demande a Machi Tool s'il a quelque chose pour elle (127.0.0.1, sa propre
# cle), fait ce qu'on lui dit avec les fonctions d'onglets de Chrome, et
# repond. Rien n'est clique ni tape. Vers Jarvis ne partent que les titres et
# les domaines, jamais les adresses entieres.

ONGLETS = {"file": [], "resultats": {}, "vu": 0.0, "cond": threading.Condition()}
ONGLETS_VIVANTE_S = 45.0
ONGLETS_ATTENTE_S = 20.0


def extension_branchee():
    return time.time() - ONGLETS["vu"] < ONGLETS_VIVANTE_S


def commande_onglets(action, delai=6.0, **args):
    """Une commande a l'extension, et sa reponse (un dict)."""
    if not extension_branchee():
        raise LookupError("L'extension Chrome de Machi Tool n'est pas branchee (Reglages > Jarvis > "
                          "les onglets de Chrome), ou Chrome est ferme.")
    ident = os.urandom(6).hex()
    c = ONGLETS["cond"]
    with c:
        ONGLETS["file"].append(dict(args, id=ident, action=action))
        c.notify_all()
        fin = time.time() + delai
        while ident not in ONGLETS["resultats"] and time.time() < fin:
            c.wait(max(0.05, fin - time.time()))
        r = ONGLETS["resultats"].pop(ident, None)
        ONGLETS["file"] = [x for x in ONGLETS["file"] if x["id"] != ident]
    if r is None:
        raise TimeoutError("Chrome n'a pas repondu.")
    if r.get("erreur"):
        raise OSError("Chrome : %s" % str(r["erreur"])[:200])
    return r


def prochaine_commande_onglets(attente=None):
    """Pour l'extension : la commande suivante, ou None apres `attente`."""
    attente = ONGLETS_ATTENTE_S if attente is None else attente
    c = ONGLETS["cond"]
    with c:
        ONGLETS["vu"] = time.time()
        fin = time.time() + attente
        while not ONGLETS["file"] and time.time() < fin:
            c.wait(max(0.05, fin - time.time()))
        ONGLETS["vu"] = time.time()
        return ONGLETS["file"].pop(0) if ONGLETS["file"] else None


def resultat_onglets(r):
    c = ONGLETS["cond"]
    with c:
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            ONGLETS["resultats"][r["id"]] = r
            c.notify_all()


def _domaine(url):
    try:
        return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def nom_onglet(o):
    """Ce a quoi on reconnait un onglet : son titre, son site, sa famille
    (« ferme les Reddit »)."""
    d = _domaine(o.get("url", ""))
    return "%s %s %s" % (o.get("titre") or "", d, _jv.site_de(d))


def agir_onglets(action, cible="", url="", recherche="", tous=False):
    """Ce que Jarvis demande aux onglets. Rend un texte pour lui."""
    if action == "ouvrir":
        adresse = url.strip() if url else (_jv.adresse_google(recherche) if recherche else "")
        if not _jv.lien_permis(adresse):
            raise ValueError("Une adresse web http(s), ou une recherche.")
        commande_onglets("ouvrir", url=adresse)
        return "Nouvel onglet : %s." % (_domaine(adresse) or adresse)
    onglets = commande_onglets("lister").get("onglets") or []
    onglets = [o for o in onglets if isinstance(o, dict) and "id" in o]
    if action == "lister":
        return liste_onglets(onglets) or "Aucun onglet ouvert."
    if action in ("fermer_gauche", "fermer_droite", "garder"):
        gardes = None
        if action == "garder" and cible:
            gardes = _jv.choisir(cible, onglets, nom=nom_onglet, seuil=40, tous=True)
            if not gardes:
                raise LookupError("Aucun onglet ne correspond a « %s » : je n'en ferme aucun." % cible)
        ids = _jv.onglets_a_fermer(onglets, action, gardes)
        if not ids:
            return "Rien a fermer."
        commande_onglets("fermer", ids=ids)
        return "%d onglet%s ferme%s." % (len(ids), "s" if len(ids) > 1 else "", "s" if len(ids) > 1 else "")
    trouves = _jv.choisir(cible, onglets, nom=nom_onglet, seuil=40, tous=tous)
    if not trouves:
        raise LookupError("Aucun onglet ne correspond a « %s »." % cible)
    vises = trouves[:20] if tous else trouves[:1]
    ids = [o["id"] for o in vises]
    noms = " ; ".join((o.get("titre") or _domaine(o.get("url", "")))[:60] for o in vises)
    if action == "fermer":
        commande_onglets("fermer", ids=ids)
        return "Ferme : %s." % noms
    if action == "aller":
        commande_onglets("aller", ids=ids[:1])
        return "Onglet affiche : %s." % noms
    if action in ("couper_son", "remettre_son"):
        commande_onglets("muet", ids=ids, muet=action == "couper_son")
        return ("Son coupe : %s." if action == "couper_son" else "Son remis : %s.") % noms
    raise ValueError("action inconnue : %s" % action)


def liste_onglets(onglets, par_famille=12, titre_max=80):
    """Les onglets rangés par site : « 9 onglets. YouTube (2) : « ... » ; ...
    Reddit (1) : ... » -- titres et domaines, jamais l'adresse entiere."""
    if not onglets:
        return ""
    bouts = []
    for famille, liste in _jv.ranger_onglets(onglets, domaine=lambda o: _domaine(o.get("url", ""))):
        items = ["« %s »%s%s%s" % ((o.get("titre") or "")[:titre_max],
                                   "" if famille not in ("Autres", "Mails") else " (%s)" % _domaine(o.get("url", "")),
                                   " -- affiche" if o.get("actif") else "", " -- joue du son" if o.get("son") else "")
                 for o in liste[:par_famille]]
        reste = len(liste) - par_famille
        bouts.append("%s (%d) : %s%s" % (famille, len(liste), " ; ".join(items),
                                        " ; et %d autres" % reste if reste > 0 else ""))
    return "%d onglets. %s" % (len(onglets), " | ".join(bouts))


def onglets_du_moment():
    """La liste rangée, pour chaque question a Jarvis -- si l'extension est
    branchee et repond vite. Sinon rien : on ne fait pas attendre Jarvis."""
    if not extension_branchee():
        return ""
    try:
        onglets = commande_onglets("lister", delai=1.5).get("onglets") or []
    except Exception:
        return ""
    return liste_onglets([o for o in onglets if isinstance(o, dict)], par_famille=6, titre_max=60)


EXTENSION_MANIFESTE = {
    "manifest_version": 3,
    "name": "Machi Tool - les onglets pour Jarvis",
    "description": "Laisse Jarvis (Machi Tool, sur ce PC) lister, ouvrir, afficher, couper et fermer des onglets.",
    "version": "1.1",
    "permissions": ["tabs", "alarms"],
    "host_permissions": ["http://127.0.0.1/*"],
    "background": {"service_worker": "fond.js"},
}

EXTENSION_FOND = r"""// Machi Tool - les onglets pour Jarvis.
// Demande a Machi Tool (127.0.0.1) s'il a une commande, l'execute avec les
// fonctions d'onglets de Chrome, et repond. Rien d'autre.
importScripts('config.js');
const BASE = 'http://127.0.0.1:' + MACHI.port + '/onglets/';
const ENTETES = { 'X-Onglets-Cle': MACHI.cle };
const pause = ms => new Promise(r => setTimeout(r, ms));
let enCours = false;

async function executer(c) {
  if (c.action === 'lister') {
    const t = await chrome.tabs.query({});
    let courante = null;
    try { courante = (await chrome.windows.getLastFocused()).id; } catch (e) {}
    return { onglets: t.map(o => ({ id: o.id, titre: o.title || '', url: o.url || '', actif: !!o.active,
                                    son: !!o.audible, muet: !!(o.mutedInfo && o.mutedInfo.muted),
                                    position: o.index, epingle: !!o.pinned,
                                    fenetre_courante: o.windowId === courante })) };
  }
  if (c.action === 'ouvrir') {
    if (!/^https?:\/\//.test(String(c.url || ''))) throw new Error('adresse refusee');
    const o = await chrome.tabs.create({ url: c.url, active: true });
    await chrome.windows.update(o.windowId, { focused: true });
    return { texte: 'ouvert' };
  }
  const ids = (c.ids || []).filter(Number.isInteger);
  if (!ids.length) throw new Error('aucun onglet');
  if (c.action === 'fermer') { await chrome.tabs.remove(ids); return { texte: 'ferme' }; }
  if (c.action === 'aller') {
    const o = await chrome.tabs.update(ids[0], { active: true });
    await chrome.windows.update(o.windowId, { focused: true });
    return { texte: 'affiche' };
  }
  if (c.action === 'muet') {
    for (const id of ids) await chrome.tabs.update(id, { muted: !!c.muet });
    return { texte: 'fait' };
  }
  throw new Error('action inconnue');
}

async function boucle() {
  if (enCours) return;
  enCours = true;
  try {
    for (;;) {
      chrome.runtime.getPlatformInfo(() => {});      // garde le service worker eveille
      let r;
      try {
        r = await fetch(BASE + 'attente', { headers: ENTETES, signal: AbortSignal.timeout(25000) });
      } catch (e) { await pause(5000); continue; }
      if (r.status === 204) continue;
      if (r.status !== 200) { await pause(10000); continue; }
      const c = await r.json();
      let rep;
      try { rep = await executer(c); } catch (e) { rep = { erreur: String((e && e.message) || e) }; }
      await fetch(BASE + 'resultat', { method: 'POST', headers: { ...ENTETES, 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ ...rep, id: c.id }) }).catch(() => {});
    }
  } finally { enCours = false; }
}

chrome.runtime.onStartup.addListener(boucle);
chrome.runtime.onInstalled.addListener(boucle);
chrome.alarms.create('machi', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(boucle);
boucle();
"""


def preparer_extension(cfg, dossier=None):
    """Ecrit l'extension dans le dossier de Machi Tool (avec le port et sa cle)
    et rend son chemin."""
    if not cfg.get("onglets_cle"):
        cfg["onglets_cle"] = secrets.token_urlsafe(18)
        sauver_config(cfg)
    dossier = dossier or os.path.join(DOSSIER, "extension-chrome")
    os.makedirs(dossier, exist_ok=True)
    port = entier(cfg.get("api_port", 7373), 7373)
    fichiers = {"manifest.json": json.dumps(EXTENSION_MANIFESTE, indent=2, ensure_ascii=False),
                "fond.js": EXTENSION_FOND,
                "config.js": "const MACHI = %s;\n" % json.dumps({"port": port, "cle": cfg["onglets_cle"]})}
    for nom, contenu in fichiers.items():
        with open(os.path.join(dossier, nom), "w", encoding="utf-8") as f:
            f.write(contenu)
    return dossier


# --- LES TEMPERATURES --------------------------------------------------

def memoire_coretemp():
    """Les octets que Core Temp partage (s'il tourne), ou None. Lecture
    seule, en memoire."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenFileMappingW.restype = wintypes.HANDLE
    k.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.MapViewOfFile.restype = ctypes.c_void_p
    k.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    for nom in ("CoreTempMappingObjectEx", "CoreTempMappingObject"):
        h = k.OpenFileMappingW(0x0004, False, nom)            # FILE_MAP_READ
        if not h:
            continue
        try:
            vue = k.MapViewOfFile(h, 0x0004, 0, 0, _jv.CT_TAILLE)
            if not vue:
                continue
            try:
                return ctypes.string_at(vue, _jv.CT_TAILLE)
            finally:
                k.UnmapViewOfFile(vue)
        finally:
            k.CloseHandle(h)
    return None


def sortie_nvidia_smi():
    """Ce que dit nvidia-smi (installe avec le pilote NVIDIA), ou "". Une
    commande fixe : rien de ce que dit le modele n'y entre."""
    exe = shutil.which("nvidia-smi") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32",
                                                     "nvidia-smi.exe")
    if not os.path.isfile(exe) and not shutil.which("nvidia-smi"):
        return ""
    try:
        r = subprocess.run([exe, "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=6,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def capteurs_wmi():
    """[(materiel, capteur, °C)] de LibreHardwareMonitor ou OpenHardwareMonitor,
    s'ils tournent."""
    if os.name != "nt":
        return []
    out = []
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        for espace in ("root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor"):
            try:
                w = win32com.client.GetObject("winmgmts:" + espace)
            except Exception:
                continue
            materiels = {str(m.Identifier): str(m.Name) for m in w.ExecQuery("SELECT Identifier, Name FROM Hardware")}
            for c in w.ExecQuery("SELECT Name, Value, Parent FROM Sensor WHERE SensorType = 'Temperature'"):
                out.append((materiels.get(str(c.Parent), str(c.Parent)), str(c.Name), float(c.Value)))
            if out:
                break
    except Exception:
        pass
    return out


def lire_temperatures():
    return _jv.resume_temperatures(_jv.lire_coretemp(memoire_coretemp()),
                                   _jv.lire_nvidia_smi(sortie_nvidia_smi()), capteurs_wmi())


# --- L'AGENDA -----------------------------------------------------------

AGENDA_JOURS = 14
AGENDA_PASSE = 7        # la frise montre aussi la semaine ecoulee : sommeil, note


def lire_agenda(cfg, jours=AGENDA_JOURS, depuis=None, bilan=False):
    """Les rendez-vous de `depuis` (aujourd'hui) sur `jours`, depuis
    BrainDebugger (les reperes « agenda » ; jamais un « psy ») -- et, avec
    `bilan`, les chiffres des derniers jours : nuits et note de la journee."""
    return _requete_bd("/api/machitool/agenda?depuis=%s&jours=%d%s" % (
        depuis or time.strftime("%Y-%m-%d"), int(jours), "&bilan=1&bilan_jours=%d" % AGENDA_PASSE if bilan else ""),
        None, cfg, 15)


def poser_agenda(cfg, titre, date, fin=None, heure=None):
    """Un rappel dans l'agenda de BrainDebugger : un jour, ou du `date` au `fin`."""
    return _requete_bd("/api/machitool/agenda", {"titre": titre, "date": date, "fin": fin, "heure": heure}, cfg, 15)


def bilan_local(aujourdhui, jours=AGENDA_PASSE):
    """Le bilan quand BrainDebugger ne le donne pas (plus ancien, injoignable) :
    les nuits que Machi Tool a mesurees lui-meme ; pas de note."""
    out = []
    for k in range(jours - 1, -1, -1):
        d = _jv.plus_jours(aujourdhui, -k)
        try:
            n = sommeil_estime(d) or {}
        except Exception:
            n = {}
        out.append({"date": d, "note": None, "sommeil_h": n.get("sommeil_h"),
                    "coucher": n.get("coucher"), "lever": n.get("reveil")})
    return {"jours": out, "sommeil_mediane": None}


# --- YOUTUBE -----------------------------------------------------------

def ouvrir_youtube(recherche):
    """La premiere video pour cette recherche, ouverte dans Chrome : elle se
    lance toute seule. A defaut, la page des resultats."""
    q = " ".join(str(recherche or "").split())[:200]
    if not q:
        raise ValueError("rien a chercher")
    resultats = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(q)
    video = None
    try:
        req = urllib.request.Request(resultats, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8", "Cookie": "SOCS=CAI; CONSENT=YES+"})
        with urllib.request.urlopen(req, timeout=8, context=_contexte_ssl()) as r:
            video = _jv.premiere_video_youtube(r.read(3_000_000).decode("utf-8", "replace"))
    except Exception:
        video = None
    if video:
        ou = ouvrir_dans_chrome("https://www.youtube.com/watch?v=" + video[0])
        return "Video ouverte dans %s : « %s »." % (ou, video[1] or q)
    ou = ouvrir_dans_chrome(resultats)
    return "Resultats YouTube ouverts dans %s (la video n'a pas pu etre choisie seule)." % ou


# --- SPOTIFY -----------------------------------------------------------

_SPOTIFY = {"client": None, "cle": None, "connexion": None}


def spotify_connecte(cfg):
    return bool(str(cfg.get("spotify_client_id") or "").strip() and cfg.get("spotify_refresh"))


def spotify_de(cfg):
    cle = (str(cfg.get("spotify_client_id") or "").strip(), cfg.get("spotify_refresh"))
    if _SPOTIFY["cle"] != cle or _SPOTIFY["client"] is None:
        def sauver(refresh):
            cfg["spotify_refresh"] = refresh
            _SPOTIFY["cle"] = (cle[0], refresh)
            sauver_config(cfg)
        _SPOTIFY["client"], _SPOTIFY["cle"] = _jv.Spotify(cle[0], cle[1], sauver=sauver), cle
    return _SPOTIFY["client"]


def diagnostic_spotify(cfg):
    """« Pourquoi il ne peut pas acceder a l'API Spotify » : pas a pas, en clair."""
    if not str(cfg.get("spotify_client_id") or "").strip():
        return "Pas de Client ID : colle celui de ton app Spotify, puis « Connecter »."
    if not cfg.get("spotify_refresh"):
        return "Pas encore connecte : clique « Connecter » et accepte dans le navigateur."
    try:
        ok, lignes = spotify_de(cfg).diagnostic()
    except Exception as e:
        ok, lignes = False, ["%s : %s" % (type(e).__name__, str(e)[:200])]
    if not cfg.get("jarvis_pc"):
        lignes.append("« Il peut agir sur le PC » est decoche : Jarvis ne peut pas s'en servir.")
        ok = False
    texte = " ".join(lignes)
    print("Spotify : %s" % texte)
    return ("OK. " if ok else "") + texte


def ouvrir_appli_spotify():
    try:
        os.startfile("spotify:")
    except Exception:
        pass


def attendre_retour_oauth(etat, echanger, rappel, delai=180, service="Spotify"):
    """Le retour d'une connexion (Spotify) sur 127.0.0.1:8765/callback,
    une fois : verifie `state`, appelle `echanger(code)` (qui garde le jeton)
    et rend la main. `rappel(message)` dit ou on en est."""
    fini = threading.Event()

    class Retour(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            q = dict(urllib.parse.parse_qsl(u.query))
            if u.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            ok, message = False, "%s n'a pas ete connecte." % service
            if q.get("state") != etat:
                message = "Reponse inattendue : recommence depuis Machi Tool."
            elif q.get("error"):
                message = "Connexion refusee sur %s (%s)." % (service, q["error"])
            else:
                try:
                    echanger(q.get("code", ""))
                    ok, message = True, "%s est connecte a Machi Tool. Tu peux fermer cet onglet." % service
                except Exception as e:
                    message = str(e)
            corps = ("<!doctype html><meta charset=utf-8><title>Machi Tool</title>"
                     "<body style='font:16px system-ui;padding:40px'>%s</body>" % message).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(corps)
            rappel(message)
            if ok or q.get("error"):
                fini.set()

    serveur = http.server.HTTPServer(("127.0.0.1", _jv.SPOTIFY_PORT), Retour)
    serveur.timeout = 1.0

    def servir():
        limite = time.time() + delai
        try:
            while not fini.is_set() and time.time() < limite:
                serveur.handle_request()
            if not fini.is_set():
                rappel("Pas de retour de %s : recommence." % service)
        finally:
            serveur.server_close()
    t = threading.Thread(target=servir, daemon=True)
    t.start()
    return t


def connecter_spotify(cfg, rappel=None, delai=180):
    """Ouvre la page de connexion de Spotify dans le navigateur et attend son
    retour sur 127.0.0.1:8765, une fois."""
    client_id = str(cfg.get("spotify_client_id") or "").strip()
    if not client_id:
        raise ValueError("Colle d'abord le Client ID de ton app Spotify.")
    verif, defi = _jv.pkce_paire()
    etat = os.urandom(12).hex()
    rappel = rappel or (lambda m: None)

    def echanger(code):
        r = _jv.Spotify.echanger_code(client_id, code, verif)
        cfg["spotify_refresh"] = r["refresh_token"]
        sauver_config(cfg)
        _SPOTIFY["client"] = None
    _SPOTIFY["connexion"] = attendre_retour_oauth(etat, echanger, rappel, delai, "Spotify")
    ouvrir_dans_chrome(_jv.spotify_url_autorisation(client_id, defi, etat))
    rappel("Connecte-toi a Spotify dans le navigateur...")


def capturer_ecran(numero):
    """UNE capture de l'ecran 1 ou 2, en memoire, reduite (1280 px de large au
    plus) et en JPEG : rendue en base64 pour Jarvis, jamais ecrite sur le
    disque. Rien a voir avec la lumiere d'ecran, qui ne garde qu'une couleur."""
    image, n, total = capturer_ecrans([numero])[0]
    return image, n, total


def capturer_ecrans(numeros=None):
    """[(base64, numero, total)] : les ecrans demandes, ou tous (`None`, 0).
    En memoire seulement, comme capturer_ecran. La boule de Jarvis va sur
    chacun le temps de le regarder (JARVIS["regard"])."""
    import mss
    from PIL import Image
    out = []
    with mss.mss() as sct:
        ecrans = sct.monitors[1:]
        if not ecrans:
            raise OSError("aucun ecran")
        voulus = [int(x or 0) for x in (numeros or [0])]
        liste = list(range(1, len(ecrans) + 1)) if 0 in voulus else \
            sorted({max(1, min(len(ecrans), n)) for n in voulus})
        for n in liste:
            JARVIS["regard"] = {"ecran": dict(ecrans[n - 1]), "jusqua": time.time() + 2.5}
            brut = sct.grab(ecrans[n - 1])
            im = Image.frombytes("RGB", brut.size, brut.rgb)
            if im.width > 1280:
                im = im.resize((1280, max(1, im.height * 1280 // im.width)), Image.BILINEAR)
            tampon = io.BytesIO()
            im.save(tampon, "JPEG", quality=70)
            out.append((base64.b64encode(tampon.getvalue()).decode("ascii"), n, len(ecrans)))
    return out


def executer_outil(outil, cfg):
    """Un outil demande par Jarvis, sur le poste. Rend {"id", "texte"} (ou
    "image"), ou {"id", "erreur"} -- jamais d'exception."""
    ident, nom, e = outil.get("id"), outil.get("nom"), outil.get("entree") or {}
    try:
        if nom == "retenir":
            cfg["jarvis_preferences"] = _jv.ajouter_preference(cfg.get("jarvis_preferences"), e.get("preference"))
            sauver_config(cfg)
            return {"id": ident, "texte": "Retenu : %s" % cfg["jarvis_preferences"][-1]}
        if nom == "oublier" and e.get("conversations"):
            n = len(cfg.get("jarvis_souvenirs") or [])
            cfg["jarvis_souvenirs"] = []
            sauver_config(cfg)
            return {"id": ident, "texte": "Oublie : %d souvenir%s de conversations." % (n, "s" if n > 1 else "")}
        if nom == "oublier":
            reste, retirees = _jv.retirer_preference(cfg.get("jarvis_preferences"), e.get("preference", ""),
                                                     tout=bool(e.get("tout")))
            if not retirees:
                return {"id": ident, "texte": "Aucune preference retenue ne correspond."}
            cfg["jarvis_preferences"] = reste
            sauver_config(cfg)
            return {"id": ident, "texte": "Oublie : %s" % " ; ".join(retirees)}
        # MACHI TOOL LUI-MEME : la guirlande, ses routines, les reglages -- a lui,
        # sans les mains sur le PC (« il a tous les droits au niveau de l'application »)
        if nom in ("lumiere", "routine_lumiere", "reglages_machi"):
            return {"id": ident, "texte": outil_application(nom, e, cfg)}
        if not cfg.get("jarvis_pc"):
            return {"id": ident, "erreur": "Les mains de Jarvis sur le PC sont fermees (Machi Tool > Reglages > Jarvis)."}
        if nom == "rechercher_google":
            ou = ouvrir_dans_chrome(_jv.adresse_google(e.get("recherche")))
            return {"id": ident, "texte": "Recherche Google ouverte dans %s." % ou}
        if nom == "lien":
            url = str(e.get("url") or "").strip()
            if not _jv.lien_permis(url):
                return {"id": ident, "erreur": "Adresse refusee : seulement une adresse web http(s)."}
            if e.get("action") == "copier":
                if not copier_presse_papiers(url):
                    return {"id": ident, "erreur": "Le presse-papiers n'a pas pu etre rempli."}
                return {"id": ident, "texte": "Lien copie dans le presse-papiers."}
            return {"id": ident, "texte": "Ouvert dans %s." % ouvrir_dans_chrome(url)}
        if nom == "lancer_appli":
            return {"id": ident, "texte": lancer_appli(e.get("nom"))}
        if nom == "fenetre":
            return {"id": ident, "texte": agir_fenetre(e.get("action") or "lister", e.get("cible") or "",
                                                       bool(e.get("tout")))}
        if nom == "son":
            if e.get("action") == "lister":
                return {"id": ident, "texte": lister_sons()}
            return {"id": ident, "texte": regler_son(e.get("action"), e.get("appli") or "", e.get("niveau"))}
        if nom == "pc":
            a = e.get("action")
            if a == "verrouiller":
                return {"id": ident, "texte": verrouiller_pc()}
            if a in ("veille", "eteindre", "redemarrer", "deconnecter", "fermer_session", "hibernation"):
                return {"id": ident, "erreur": _jv.REFUS_ALIMENTATION}
            if a == "luminosite":
                return {"id": ident, "texte": regler_luminosite(e.get("sens") or "regler", e.get("niveau"))}
            return {"id": ident, "erreur": "action inconnue : %s" % a}
        if nom == "youtube":
            return {"id": ident, "texte": ouvrir_youtube(e.get("recherche"))}
        if nom == "temperatures":
            return {"id": ident, "texte": lire_temperatures()}
        if nom == "onglets":
            return {"id": ident, "texte": agir_onglets(e.get("action") or "lister", e.get("cible") or "",
                                                       e.get("url") or "", e.get("recherche") or "",
                                                       bool(e.get("tous")))}
        if nom == "montrer_agenda":
            # la fenetre s'ouvre dans le fil de l'interface, a son prochain passage
            JARVIS["montrer_agenda"] = time.time()
            return {"id": ident, "texte": "Agenda ouvert a l'ecran."}
        if nom.startswith("spotify_"):
            if not spotify_connecte(cfg):
                return {"id": ident, "erreur": "Spotify n'est pas connecte a Machi Tool (Reglages > Jarvis > Spotify)."}
            sp = spotify_de(cfg)
            if nom == "spotify_jouer":
                return {"id": ident, "texte": sp.jouer(e.get("recherche"), e.get("genre") or "titre",
                                                       bool(e.get("file")), ouvrir_appli_spotify)}
            if nom == "spotify_en_cours":
                c = sp.en_cours()
                return {"id": ident, "texte": ("%s : « %s » de %s." % ("En lecture" if c["lecture"] else "En pause",
                                                                       c["titre"], c["artistes"])) if c
                        else "Rien ne joue sur Spotify."}
            if nom == "spotify_aimer":
                return {"id": ident, "texte": sp.aimer()}
        if nom == "chercher_historique":
            if not cfg.get("jarvis_historique"):
                return {"id": ident, "erreur": "L'historique du navigateur n'est pas permis dans Machi Tool."}
            return {"id": ident, "texte": _jv.chercher_historique(
                e.get("recherche"), _jv.fichiers_historique(), e.get("jours") or 90, lire=lire_historique_copie)}
        if nom == "musique":
            return {"id": ident, "texte": touche_media(e.get("action"))}
        if nom == "spotify":
            return {"id": ident, "texte": ouvrir_spotify(e.get("recherche"))}
        if nom == "regarder_ecran":
            if not cfg.get("jarvis_ecran"):
                return {"id": ident, "erreur": "Regarder l'ecran n'est pas permis dans Machi Tool."}
            vus = capturer_ecrans([e.get("ecran", 0)])
            if len(vus) == 1:
                image, n, total = vus[0]
                return {"id": ident, "image": image, "texte": "Ecran %d sur %d." % (n, total)}
            return {"id": ident, "images": [v[0] for v in vus],
                    "texte": "Les %d ecrans, dans l'ordre : %s." % (len(vus), ", ".join("ecran %d" % v[1] for v in vus))}
        bases = bases_dossiers()
        if nom == "lister_dossier":
            ch = _jv.resoudre_chemin(e.get("chemin"), bases)
            return {"id": ident, "texte": _jv.lister_dossier(ch, max(1, min(2, int(e.get("profondeur") or 1))))}
        if nom == "chercher_fichiers":
            ch = _jv.resoudre_chemin(e.get("dans") or "~", bases)
            crit = _jv.criteres(e.get("mots") or e.get("nom") or "", e.get("type"), e.get("jours"))
            res, coupe = _jv.trouver_fichiers(ch, crit)
            JARVIS["recherche"] = {"racine": ch, "criteres": crit, "resultats": res, "coupe": coupe}
            return {"id": ident, "texte": _jv.resume_recherche(ch, crit, res, coupe)}
        if nom == "affiner_recherche":
            r = JARVIS.get("recherche")
            if not r:
                return {"id": ident, "erreur": "Aucune recherche en cours : commence par chercher_fichiers."}
            racine = _jv.resoudre_chemin(e["dans"], bases) if e.get("dans") else r["racine"]
            crit, garde = _jv.affiner(r, e.get("ajouter") or "", e.get("retirer") or "",
                                      e.get("type"), e.get("jours"))
            coupe = False if garde is not None else r["coupe"]
            if garde is None or racine != r["racine"]:
                garde, coupe = _jv.trouver_fichiers(racine, crit)
            JARVIS["recherche"] = {"racine": racine, "criteres": crit, "resultats": garde, "coupe": coupe}
            return {"id": ident, "texte": _jv.resume_recherche(racine, crit, garde, coupe)}
        if nom == "ouvrir_resultats":
            r = JARVIS.get("recherche")
            if not r or not r["resultats"]:
                return {"id": ident, "erreur": "Aucun resultat de recherche a ouvrir."}
            res = r["resultats"]
            if e.get("numeros"):
                choisis = []
                for n in e["numeros"]:
                    if not (1 <= int(n) <= len(res)):
                        return {"id": ident, "erreur": "Il n'y a pas de numero %s (de 1 a %d)." % (n, len(res))}
                    choisis.append(res[int(n) - 1])
            elif len(res) > OUVRIR_MAX:
                return {"id": ident, "erreur": "Il y en a %d : c'est trop pour tout ouvrir d'un coup (%d au plus). "
                                               "Affine, ou dis lesquels." % (len(res), OUVRIR_MAX)}
            else:
                choisis = res
            for chemin, _, _ in choisis[:OUVRIR_MAX]:
                if _jv.touche_a_l_alimentation(chemin):
                    return {"id": ident, "erreur": _jv.REFUS_ALIMENTATION}
            for chemin, _, _ in choisis[:OUVRIR_MAX]:
                startfile_sur(chemin)
            return {"id": ident, "texte": "Ouverts : %s." % " ; ".join(os.path.basename(c) for c, _, _ in choisis[:OUVRIR_MAX])}
        if nom == "creer_fichier":
            if _jv.touche_a_l_alimentation(e.get("chemin") or "", e.get("contenu") or ""):
                return {"id": ident, "erreur": _jv.REFUS_ALIMENTATION}
            ch = creer_fichier(_jv.resoudre_chemin(e.get("chemin"), bases), e.get("contenu"), dossiers_proteges())
            if e.get("ouvrir"):
                startfile_sur(ch)
            return {"id": ident, "texte": "Cree : %s" % ch}
        if nom == "ecrire_note":
            dossier = os.path.join(bases.get("documents") or os.path.join(bases["home"], "Documents"),
                                   "Notes de Jarvis")
            ch, neuve = ecrire_note(dossier, e.get("texte"), e.get("titre") or "", e.get("ajouter_a") or "")
            if e.get("ouvrir", True):
                startfile_sur(ch)
            return {"id": ident, "texte": ("Note ecrite : %s" if neuve else "Ajoute a la note : %s") % ch}
        if nom == "creer_dossier":
            ch = _jv.resoudre_chemin(e.get("chemin"), bases)
            return {"id": ident, "texte": _jv.creer_dossier(ch, dossiers_proteges())}
        if nom == "ouvrir":
            ch = _jv.resoudre_chemin(e.get("chemin"), bases)
            if not os.path.exists(ch):
                return {"id": ident, "erreur": "Rien a cet endroit : %s" % ch}
            if _jv.touche_a_l_alimentation(ch):
                return {"id": ident, "erreur": _jv.REFUS_ALIMENTATION}
            startfile_sur(ch)
            return {"id": ident, "texte": "Ouvert : %s" % ch}
        return {"id": ident, "erreur": "outil inconnu : %s" % nom}
    except Exception as ex:
        return {"id": ident, "erreur": "%s : %s" % (type(ex).__name__, str(ex)[:300])}


def outils_de_jarvis(etat, cfg):
    """Les outils d'un tour : ceux qui touchent aux fichiers ou a l'ecran
    attendent le code (ou une session ouverte) ; ceux-la mis a part, on
    execute, on renvoie, et Jarvis continue -- cinq tours au plus."""
    L = langue_jarvis(cfg)
    outils = etat["outils"]
    # mains fermees : ces outils seront refuses, inutile de demander le code
    besoin = [o for o in outils if o.get("nom") not in OUTILS_SANS_CODE] if cfg.get("jarvis_pc") else []
    if besoin and cfg.get("jarvis_code_actif") and not acces_ouvert():
        if time.time() < float(JARVIS.get("verrou_jusqua") or 0):
            refus = "Acces verrouille apres trois codes faux : reessayer dans quelques minutes."
            return continuer_jarvis(etat, [executer_outil(o, cfg) if o not in besoin
                                           else {"id": o.get("id"), "erreur": refus} for o in outils], cfg)
        if not code_regle(cfg):
            refus = ("Aucun code d'acces n'est regle dans Machi Tool (Reglages > Jarvis) : les dossiers, "
                     "les fichiers et l'ecran restent fermes.")
            return continuer_jarvis(etat, [executer_outil(o, cfg) if o not in besoin
                                           else {"id": o.get("id"), "erreur": refus} for o in outils], cfg)
        JARVIS["attente_code"] = dict(etat, expire=time.time() + 30, essais=0)
        print("Jarvis : code d'acces demande")
        return dire(phrase("code_demande", L), suite=True, langue=L)
    return continuer_jarvis(etat, [executer_outil(o, cfg) for o in outils], cfg)


def repondre_au_code(texte, cfg):
    """La phrase qui suit « Code d'acces ? ». Ni journalisee, ni envoyee."""
    att = JARVIS.get("attente_code") or {}
    L = langue_jarvis(cfg)
    if _jv.code_juste(texte, cfg.get("jarvis_code_sel"), cfg.get("jarvis_code_empreinte")):
        JARVIS["attente_code"] = None
        JARVIS["acces_jusqua"] = time.time() + ACCES_DUREE_S
        print("Jarvis : code d'acces juste")
        jouer_son("fait")
        return outils_de_jarvis(att, cfg)
    att["essais"] = int(att.get("essais") or 0) + 1
    print("Jarvis : code d'acces faux (%d)" % att["essais"])
    if att["essais"] >= 3:
        JARVIS["attente_code"] = None
        JARVIS["verrou_jusqua"] = time.time() + VERROU_DUREE_S
        poser_led("erreur", 1.2)
        return dire(phrase("code_refuse", L), langue=L)
    att["expire"] = time.time() + 30
    JARVIS["attente_code"] = att
    return dire(phrase("code_faux", L), suite=True, langue=L)


def outil_application(nom, e, cfg):
    """La guirlande, les routines de lumiere, les reglages de Machi Tool. Rend
    le texte du resultat ; ValueError/LookupError disent ce qui ne va pas."""
    a = e.get("action")
    if nom == "lumiere":
        if a == "couleur":
            c = _jv.couleur_lue(e.get("couleur"))
            if not c:
                raise ValueError("Couleur illisible : %s" % e.get("couleur"))
            ETAT["forcage"] = {"couleur": hex_vers_rgb(c), "nom": "%s (Jarvis)" % c, "manuel": True, "expire": 0}
            return "Guirlande en %s." % c
        if a == "eteindre":
            ETAT["forcage"] = {"couleur": (0, 0, 0), "nom": "Eteinte (Jarvis)", "manuel": True, "expire": 0}
            return "Guirlande eteinte."
        if a == "normale":
            ANIMATION["etapes"] = []
            f = ETAT.get("forcage")
            if f and f.get("manuel"):
                ETAT["forcage"] = None
            ETAT["pause"] = False
            return "La guirlande reprend son mode (%s)." % cfg.get("mode", "applications")
        if a == "animation":
            d = jouer_animation(e.get("etapes"), e.get("repetitions", 1), "Jarvis", bool(e.get("tenir")))
            return "Animation lancee (%.0f s)." % d
        if a == "mode":
            m = _jv.valeur_reglage("mode", CONFIG_DEFAUT, e.get("mode"))
            executer_commande({"action": "mode", "mode": m}, cfg)
            return "La guirlande suit maintenant : %s." % m
        raise ValueError("action inconnue : %s" % a)
    if nom == "routine_lumiere":
        routines = [r for r in cfg.get("routines_lumiere") or [] if isinstance(r, dict)]
        if a == "lister":
            return _jv.resume_routines(routines) or "Aucune routine pour l'instant."
        if a == "creer":
            r = _jv.routine_propre(e, par_jarvis=True)
            cfg["routines_lumiere"] = _jv.ranger_routine(routines, r)
            sauver_config(cfg)
            return "Routine gardee : " + _jv.decrire_routine(r)
        i = _jv.trouver_routine(routines, e.get("nom") or "")
        if i is None:
            raise LookupError("Aucune routine ne s'appelle « %s »." % (e.get("nom") or ""))
        r = routines[i]
        if a == "supprimer":
            cfg["routines_lumiere"] = routines[:i] + routines[i + 1:]
            sauver_config(cfg)
            return "Routine supprimee : %s." % r["nom"]
        if a in ("activer", "desactiver"):
            r["actif"] = a == "activer"
            cfg["routines_lumiere"] = routines
            sauver_config(cfg)
            return "Routine %s : %s." % ("activee" if r["actif"] else "desactivee", r["nom"])
        if a == "essayer":
            d = jouer_animation(r["etapes"], r.get("repetitions", 1), r["nom"], r.get("tenir"))
            return "Routine jouee (%.0f s) : %s." % (d, r["nom"])
        raise ValueError("action inconnue : %s" % a)
    if nom == "reglages_machi":
        if a == "lire":
            return _jv.lire_reglages(cfg, CONFIG_DEFAUT, e.get("cle") or "")
        if a == "couleur_appli":
            cfg["regles"], texte = _jv.poser_couleur_appli(cfg.get("regles"), e.get("nom"), e.get("couleur"),
                                                           e.get("mots"))
            sauver_config(cfg)
            return texte
        if a == "changer":
            cle = str(e.get("cle") or "").strip()
            if not _jv.reglage_modifiable(cle, CONFIG_DEFAUT):
                raise ValueError("« %s » n'est pas un reglage que je peux changer." % cle)
            v = _jv.valeur_reglage(cle, CONFIG_DEFAUT, e.get("valeur"))
            if cle == "mode":
                executer_commande({"action": "mode", "mode": v}, cfg)
            else:
                cfg[cle] = v
                sauver_config(cfg)
            if cle.startswith("jarvis_"):
                envoyer_oreille(config_oreille(cfg))
            return "%s = %s." % (cle, v)
        raise ValueError("action inconnue : %s" % a)
    raise ValueError("outil inconnu : %s" % nom)


def capacites_jarvis(cfg):
    """Ce que Jarvis peut faire ici, dit a BrainDebugger a chaque question :
    ses mains, ses yeux, l'historique -- et ce qu'il retient de toi."""
    pc = bool(cfg.get("jarvis_pc"))
    return {"outils": pc, "ecran": pc and bool(cfg.get("jarvis_ecran")),
            "navigation": pc and bool(cfg.get("jarvis_historique")),
            "spotify": pc and spotify_connecte(cfg),
            "onglets": pc and extension_branchee(),
            "fenetre_agenda": pc,
            # Machi Tool lui-meme : la guirlande, ses routines, les reglages
            "application": True, "routines": _jv.resume_routines(cfg.get("routines_lumiere") or []),
            "souvenirs": souvenirs_a_envoyer(cfg),
            "memoire": True, "preferences": [str(p)[:_jv.PREFERENCE_LONGUEUR]
                                             for p in (cfg.get("jarvis_preferences") or [])][-_jv.PREFERENCES_MAX:]}


def continuer_jarvis(etat, resultats, cfg):
    """Renvoie a BrainDebugger ce que les outils ont fait ; Jarvis continue."""
    L = langue_jarvis(cfg)
    poser_led("pense")
    JARVIS.update(etat="pense", message="Jarvis agit...")
    try:
        donnees = _requete_bd("/api/machitool/jarvis",
                              dict({"suite": etat["suite"], "resultats": resultats, "langue": L,
                                    "appellation": str(cfg.get("jarvis_appellation", "") or "")[:40]},
                                   **capacites_jarvis(cfg)), cfg, 180)
    except urllib.error.HTTPError as e:
        return signaler_erreur(erreur_bd(e, L))
    except Exception:
        return signaler_erreur(phrase("bd_injoignable", L))
    return recevoir_jarvis(etat["texte"], donnees, cfg, int(etat.get("tour") or 1) + 1)


def copier_presse_papiers(texte):
    """Le texte dans le presse-papiers de Windows (clip.exe, en UTF-16 avec sa
    marque, pour les accents). Rend False hors de Windows ou en echec."""
    if os.name != "nt" or not texte:
        return False
    try:
        subprocess.run(["clip"], input=texte.encode("utf-16"), check=True, timeout=5,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def recevoir_jarvis(texte, donnees, cfg, tour=1):
    """Ce que BrainDebugger renvoie : une reponse a dire, le compagnon (grave),
    ou des outils a executer ici."""
    L = langue_jarvis(cfg)
    donnees = donnees or {}
    if donnees.get("detail"):
        # CE QUE CLAUDE A REPONDU EN ENTIER, quand Jarvis l'a consulte : il en
        # dit l'essentiel, le texte complet va dans le presse-papiers.
        JARVIS["derniere_reponse_complete"] = str(donnees["detail"])
        if copier_presse_papiers(str(donnees["detail"])):
            notifier = JARVIS_CROCHETS.get("notifier")
            if notifier:
                notifier("Jarvis", "La réponse complète de Claude est dans le presse-papiers.")
    if donnees.get("outils"):
        # executer_outil refuse lui-meme ce que les reglages ne permettent pas
        if tour > OUTILS_TOURS_MAX:
            return signaler_erreur(phrase("sans_reponse", L))
        return outils_de_jarvis({"texte": texte, "suite": donnees.get("suite") or [],
                                 "outils": list(donnees["outils"]), "tour": tour}, cfg)
    reponse = str(donnees.get("texte") or "").strip()
    if not reponse:
        return signaler_erreur(phrase("sans_reponse", L))
    if donnees.get("fin"):
        # CONGEDIE, POUR DE BON : il dit sa formule, puis n'ecoute plus -- il
        # disait « je m'efface » et restait a l'ecoute.
        print("Jarvis : congedie")
        JARVIS["historique"] = (JARVIS["historique"] + [
            {"role": "user", "texte": texte}, {"role": "assistant", "texte": reponse}])[-12:]
        clore_historique(cfg)
        JARVIS["attente_code"] = None
        envoyer_oreille({"cmd": "annuler"})
        return dire(reponse, suite=False, langue=L)
    if donnees.get("mode") == "psy":
        # C'est le compagnon qui a repondu, et on reste avec lui : parce que
        # c'etait grave (a l'au revoir, Jarvis se taira : `psy_grave`), ou
        # parce que Jarvis a compris qu'on voulait le psychologue (« demande »).
        grave = donnees.get("raison") != "demande"
        print("Jarvis : bascule en mode psychologue (%s)" % ("grave" if grave else "demande"))
        if grave:
            JARVIS["historique"] = []      # grave : cette conversation-la, on ne la resume pas
        else:
            clore_historique(cfg)
        poser_mode("psy")
        JARVIS.update(psy_grave=grave, psy_echange=[{"role": "user", "texte": texte},
                                                    {"role": "assistant", "texte": reponse}])
        JARVIS["vu"] = time.time()
        return dire(reponse, suite=True, langue="fr")
    JARVIS["historique"] = (JARVIS["historique"] + [
        {"role": "user", "texte": texte}, {"role": "assistant", "texte": reponse}])[-12:]
    n = _jv.normaliser(reponse)
    JARVIS["propose_psy"] = "mode psychologue" in n or "therapist mode" in n
    JARVIS["vu"] = time.time()
    dire(reponse, suite=True, langue=L)


def parler_a_jarvis(texte, cfg):
    """Le mode Jarvis : le majordome du PC, par BrainDebugger (qui tient la cle
    Claude) -- Sonnet, effort bas. Rien n'entre dans le journal, sauf un
    message grave : BrainDebugger l'envoie alors au compagnon, et on passe en
    mode psychologue."""
    L = langue_jarvis(cfg)
    if not _cle_presente(cfg):
        return signaler_erreur(phrase("cle_absente", L))
    poser_led("pense")
    JARVIS.update(etat="pense", message="Jarvis reflechit...")
    print("Jarvis : question au majordome (%d signes)" % len(texte))
    try:
        donnees = _requete_bd("/api/machitool/jarvis",
                              dict({"texte": texte, "historique": JARVIS["historique"][-12:], "langue": L,
                                    "appellation": str(cfg.get("jarvis_appellation", "") or "")[:40],
                                    "onglets_ouverts": onglets_du_moment() if cfg.get("jarvis_pc") else ""},
                                   **capacites_jarvis(cfg)), cfg, 180)
    except urllib.error.HTTPError as e:
        return signaler_erreur(erreur_bd(e, L))
    except Exception:
        return signaler_erreur(phrase("bd_injoignable", L))
    return recevoir_jarvis(texte, donnees, cfg)


_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
         "septembre", "octobre", "novembre", "décembre")


_JOURS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MOIS_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December")


def heure_en(t):
    """« It's 6:30 in the evening. » -- espeak lit « 6:30 » comme on le dit."""
    h, m = t.tm_hour, t.tm_min
    moment = ("in the morning" if 5 <= h < 12 else "in the afternoon" if 12 <= h < 18
              else "in the evening" if 18 <= h < 22 else "at night")
    h12 = h % 12 or 12
    return ("It's %d o'clock %s." % (h12, moment)) if not m else ("It's %d:%02d %s." % (h12, m, moment))


def date_en(t):
    d = t.tm_mday
    suffixe = "th" if 11 <= d % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    return "It's %s, the %d%s of %s." % (_JOURS_EN[t.tm_wday], d, suffixe, _MOIS_EN[t.tm_mon - 1])


def executer_commande(a, cfg, maintenant=None):
    """Fait la commande. Rend la phrase a dire, ou None (un son suffit)."""
    quoi = a["action"]
    t = time.localtime(maintenant) if maintenant is not None else time.localtime()
    L = langue_du_mode(cfg)
    if quoi == "verrouiller":
        JARVIS["acces_jusqua"] = 0.0
        JARVIS["attente_code"] = None
        return phrase("verrouille", langue_jarvis(cfg))
    if quoi == "silence":
        VOIX.taire()
        return None
    if quoi in ("volume", "sons"):
        if not cfg.get("jarvis_pc"):
            return phrase("mains_fermees", langue_jarvis(cfg))
        try:
            if quoi == "sons":
                return lister_sons()
            return regler_son(a.get("sens"), a.get("cible") or "", a.get("niveau"))
        except Exception as e:
            return str(e) if isinstance(e, LookupError) else phrase("son_rate", langue_jarvis(cfg))
    if quoi == "youtube":
        if not cfg.get("jarvis_pc"):
            return phrase("mains_fermees", langue_jarvis(cfg))
        try:
            fait = ouvrir_youtube(a.get("recherche"))
        except Exception as e:
            print("Jarvis : YouTube impossible (%s)" % type(e).__name__)
            return phrase("youtube_rate", langue_jarvis(cfg))
        return phrase("youtube_video" if fait.startswith("Video") else "youtube_resultats", langue_jarvis(cfg))
    if quoi in ("annuler", "fin"):
        return None
    if quoi == "dormir":
        cfg["jarvis_actif"] = False
        sauver_config(cfg)
        return phrase("dormir", L)
    if quoi == "heure":
        if L == "en":
            return heure_en(t)
        return "Il est %d heure%s %02d." % (t.tm_hour, "s" if t.tm_hour > 1 else "", t.tm_min) \
            if t.tm_min else "Il est %d heure%s pile." % (t.tm_hour, "s" if t.tm_hour > 1 else "")
    if quoi == "date":
        if L == "en":
            return date_en(t)
        return "Nous sommes le %s %d %s." % (_JOURS[t.tm_wday], t.tm_mday, _MOIS[t.tm_mon - 1])
    if quoi == "mode":
        cfg["mode"] = a["mode"]
        sauver_config(cfg)
        if a["mode"] == "son":
            demarrer_audio(cfg)
        else:
            arreter_audio()
        return None
    if quoi == "lumiere_off":
        ETAT["forcage"] = {"couleur": (0, 0, 0), "nom": "Eteinte (Jarvis)", "manuel": True, "expire": 0}
        return None
    if quoi == "lumiere_couleur":
        ETAT["forcage"] = {"couleur": hex_vers_rgb(a["couleur"]), "nom": "%s (Jarvis)" % a["nom"],
                           "manuel": True, "expire": 0}
        return None
    if quoi in ("lumiere_on", "lumiere_normale"):
        f = ETAT.get("forcage")
        if f and f.get("manuel"):
            ETAT["forcage"] = None
        ETAT["pause"] = False
        return None
    if quoi == "minuteur":
        return poser_minuteur(a["secondes"], a.get("quoi") or "", L)
    if quoi == "minuteurs_annuler":
        n = len(JARVIS["minuteurs"])
        for m in JARVIS["minuteurs"]:
            m["minuteur"].cancel()
        JARVIS["minuteurs"] = []
        return phrase("annule" if n else "aucun_minuteur", L)
    if quoi == "ouvrir_site":
        import webbrowser
        adresse = str(cfg.get("pont_site", "")).strip()
        if adresse:
            webbrowser.open(adresse)
        return None
    if quoi == "ouvrir_panneau":
        f = JARVIS_CROCHETS.get("ouvrir_panneau")
        if f:
            f()
        return None
    if quoi == "synchro":
        if not (ACTIVITE["active"] and cfg.get("collecte_envoi", False)):
            return phrase("synchro_coupee", L)
        threading.Thread(target=lambda: envoyer_activite_au_site(cfg), daemon=True).start()
        return phrase("synchro", L)
    if quoi == "ouvrir":
        cible = a["cible"]
        if os.name == "nt":
            startfile_sur(cible)
        else:
            import webbrowser
            webbrowser.open(cible)
        return None
    return None


def poser_minuteur(secondes, quoi="", langue="fr"):
    secondes = max(1.0, min(24 * 3600.0, float(secondes)))
    entree = {"fin": time.time() + secondes, "quoi": quoi, "duree": secondes}

    def sonner():
        if entree in JARVIS["minuteurs"]:
            JARVIS["minuteurs"].remove(entree)
        jouer_son("minuteur")
        poser_led("minuteur", 5)
        texte = (phrase("rappel", langue, quoi) if quoi
                 else phrase("minuteur_fini", langue, _jv.dire_duree(secondes, langue)))
        notifier = JARVIS_CROCHETS.get("notifier")
        if notifier:
            notifier("Jarvis", texte)
        if CFG.get("jarvis_voix", True) and VOIX.peut_parler():
            VOIX.dire(texte, None, langue)

    entree["minuteur"] = threading.Timer(secondes, sonner)
    entree["minuteur"].daemon = True
    entree["minuteur"].start()
    JARVIS["minuteurs"].append(entree)
    if quoi:
        return phrase("rappel_pose", langue, _jv.dire_duree(secondes, langue))
    return phrase("minuteur", langue, _jv.dire_duree(secondes, langue))


# ---------- apprendre la voix ----------

def apprendre_a_voix_haute(cfg):
    """« Apprends ma voix » / « learn my voice », dit a Jarvis -- demande :
    « fait en sorte qu'on puisse juste Jarvis pour lui parler ». Le modele
    d'openWakeWord ne connait que « Hey Jarvis » ; « Jarvis » tout seul, c'est
    la voix de la personne, apprise. Il l'explique a voix haute, se TAIT, et
    ecoute quatre fois son nom, la guirlande allumee a chaque fois : sa propre
    voix dans l'empreinte serait une empreinte de lui-meme."""
    a = JARVIS.get("apprentissage")
    if a and not a.get("fini"):
        return False
    L = langue_jarvis(cfg)
    dire_et_attendre(phrase("apprendre", L), L)
    time.sleep(0.8)                        # que l'echo de sa voix se taise
    ok = apprendre_voix()
    dire(phrase("appris" if ok else "pas_appris", L), langue=L)
    return ok


GABARITS_PLAFOND = 12         # au-dela, chaque mot entendu coute trop a comparer
# « L'APPELER AVEC BEAUCOUP DE TONS DIFFERENTS », et « plus de tests pour que
# ma voix soit reconnue le plus justement possible ». Cinq fois normalement
# (le noyau de la voix : voir choisir_gabarits dans jarvis.py), puis les tons
# qui s'en ecartent le plus : la question, de loin et fort, bas et en passant.
TONS_APPRENTISSAGE = (
    None, None, None, None, None,
    "Comme une question : « Jarvis ? »",
    "Plus fort, comme depuis l'autre bout de la piece : « JARVIS ! »",
    "Plus bas, en passant, comme dans une phrase : « ...jarvis... »",
)
N_NORMAUX = sum(1 for t in TONS_APPRENTISSAGE if t is None)


def apprendre_voix(total=len(TONS_APPRENTISSAGE), essais_max=16, ajouter=False):
    """« Jarvis », huit fois, dit par la personne -- cinq fois a plat, puis
    sur les tons de TONS_APPRENTISSAGE : « Jarvis ? » monte et traine, et trois
    « Jarvis » dits a plat ne le reconnaissaient pas (voir GABARIT_SAUT dans
    jarvis.py) ; fort ou bas, c'est la meme chose. A lancer dans un fil.

    `ajouter` : une seule facon de plus, gardee avec celles deja apprises --
    « Ajouter une facon de l'appeler », pour celle qui ne passe pas."""
    if not oreille_vivante():
        JARVIS["apprentissage"] = {"n": 0, "total": total, "fini": True,
                                   "message": "Coche d'abord « Ecouter Jarvis » : il faut le micro."}
        return False
    appris, essais = [], 0
    JARVIS["apprentissage"] = {"n": 0, "total": total, "fini": False, "message": ""}
    while len(appris) < total and essais < essais_max:
        essais += 1
        ton = TONS_APPRENTISSAGE[len(appris)] if len(appris) < len(TONS_APPRENTISSAGE) else None
        if ajouter:
            consigne = "Dis-le maintenant, de la facon qu'il ne reconnait pas."
        elif ton:
            consigne = "%s (%d/%d)." % (ton, len(appris) + 1, total)
        else:
            consigne = "Dis « Jarvis » maintenant, comme tu l'appelleras (%d/%d)." % (len(appris) + 1, total)
        JARVIS["apprentissage"].update(n=len(appris), message=consigne)
        poser_led("apprend")
        _GABARIT_RECU["signal"].clear()
        _GABARIT_RECU["evt"] = None
        envoyer_oreille({"cmd": "apprendre"})
        if not _GABARIT_RECU["signal"].wait(7.0):
            envoyer_oreille({"cmd": "annuler"})
            JARVIS["apprentissage"]["message"] = "Je n'ai rien recu du micro. On recommence."
            time.sleep(1.2)
            continue
        ev = _GABARIT_RECU["evt"] or {}
        if ev.get("vecteurs"):
            appris.append(ev["vecteurs"])
            poser_led("fait", 0.5)
            time.sleep(0.8)
        else:
            poser_led("erreur", 0.8)
            JARVIS["apprentissage"]["message"] = "Rate (%s). On recommence." % (ev.get("erreur") or "?")
            time.sleep(1.4)
    if len(appris) < total:
        poser_led(None)
        JARVIS["apprentissage"].update(fini=True, message="Pas assez d'essais reussis. Reessaie au calme.")
        return False
    if ajouter:
        deja = gabarits_jarvis()
        # Une facon de plus, mais du meme mot : loin de toutes celles apprises,
        # c'est un autre mot (ou un bruit), et il se reveillerait dessus.
        if deja and min(_jv.distance_gabarit(_jv.normer(g), _jv.normer(appris[0])) for g in deja) > _jv.ESSAI_ECART_MAX:
            poser_led("erreur", 1.2)
            JARVIS["apprentissage"].update(
                fini=True, message="Ca ne ressemble a aucune des facons apprises. Reessaie, "
                                   "ou reapprends tout.")
            return False
        appris = (deja + appris)[-GABARITS_PLAFOND:]
        sauver_gabarits(appris, garder_auto=True)
    else:
        # le plus grand groupe coherent des essais normaux, puis tout essai
        # assez proche de lui (voir choisir_gabarits) : un essai rate ne fait
        # plus tout jeter
        gardes, ecart, ecartes = _jv.choisir_gabarits(appris, min(N_NORMAUX, total))
        if gardes is None:
            poser_led("erreur", 1.2)
            JARVIS["apprentissage"].update(
                fini=True, message="Tes « Jarvis » ne se ressemblent pas du tout (%.2f) : le micro "
                                   "entend-il bien ta voix ? Rapproche-toi et reessaie au calme." % ecart)
            return False
        appris = gardes[:GABARITS_PLAFOND]
        sauver_gabarits(appris)
    envoyer_oreille(config_oreille(CFG))
    poser_led("fait", 1.2)
    jouer_son("fait")
    fin = "Appris (%d facons%s). Dis « Jarvis » pour essayer." % (
        len(appris), "" if ajouter or not ecartes else ", %d essai%s ecarte%s : du bruit" % (
            ecartes, "s" if ecartes > 1 else "", "s" if ecartes > 1 else ""))
    JARVIS["apprentissage"].update(n=total, fini=True, message=fin)
    JARVIS["message"] = message_attente()
    return True


def oreille_enfant_depuis_argv():
    i = sys.argv.index(JARVIS_ENFANT_ARG)
    _jv.oreille_enfant(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3])


class Passerelle(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass                                   # pas de bruit dans le journal

    # ---------- entetes ----------

    def entetes_cors(self):
        origine = self.headers.get("Origin", "")
        autorisees = CFG.get("api_origines", [])
        if "*" in autorisees:
            self.send_header("Access-Control-Allow-Origin", origine or "*")
        elif origine and origine in autorisees:
            self.send_header("Access-Control-Allow-Origin", origine)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers",
                         "content-type, x-jeton, x-machitool-cle")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")

    def repondre(self, code, charge):
        corps = json.dumps(charge).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.entetes_cors()
        self.end_headers()
        self.wfile.write(corps)

    def do_OPTIONS(self):
        self.send_response(204)
        self.entetes_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- lecture de la requete ----------

    def origine_permise(self):
        origine = self.headers.get("Origin", "")
        autorisees = CFG.get("api_origines", [])
        return ("*" in autorisees) or (not origine) or (origine in autorisees)

    def jeton_permis(self, corps):
        attendu = CFG.get("api_jeton", "")
        if not attendu:
            return True
        fourni = self.headers.get("X-Jeton", "") or (corps.get("jeton", "")
                                                     if isinstance(corps, dict) else "")
        return secrets.compare_digest(str(fourni), str(attendu))

    def cle_pont_permise(self):
        """La cle du pont, acceptee UNIQUEMENT pour lire /activite.

        Le site tient deja cette cle (pont_cle cote app == passerelleCle cote
        site) : il tire donc le digest sans nouveau secret a recopier. On la
        cantonne a la lecture d'enveloppe — jamais au controle de la lumiere, qui
        reste derriere le jeton local — et la liste d'origines reste le garde-fou."""
        pont = str(CFG.get("pont_cle", "")).strip()
        cle_site = self.headers.get("X-Machitool-Cle", "")
        return bool(pont) and bool(cle_site) and \
            secrets.compare_digest(str(cle_site), pont)

    def lire_corps(self):
        try:
            taille = int(self.headers.get("Content-Length", 0))
            if not taille:
                return {}
            return json.loads(self.rfile.read(taille).decode("utf-8"))
        except Exception:
            return {}

    # ---------- la dictee ----------

    def route_dictee(self, chemin):
        """Le site envoie le son, Machi Tool rend le texte. Meme cle que la
        lecture de l'activite : le site la tient deja."""
        if not (self.jeton_permis({}) or self.cle_pont_permise()):
            return self.repondre(401, {"erreur": "jeton invalide"})
        if not dictee_possible():
            return self.repondre(501, {"erreur": "moteur de dictee absent de cette version"})
        if chemin == "/dictee/preparer":
            if DICTEE["etat"] not in ("preparation", "pret"):
                threading.Thread(target=preparer_dictee, daemon=True).start()
            return self.repondre(202, etat_dictee())
        try:
            taille = int(self.headers.get("Content-Length", 0))
        except ValueError:
            taille = 0
        if taille <= 0 or taille > DICTEE_MAX_OCTETS:
            return self.repondre(413, {"erreur": "son vide ou trop long"})
        octets = self.rfile.read(taille)
        if etat_dictee()["etat"] != "pret":
            return self.repondre(409, etat_dictee())
        try:
            texte = transcrire(octets)
        except ValueError as e:
            return self.repondre(400, {"erreur": str(e)[:200]})
        except DicteeImpossible as e:
            return self.repondre(503, {"erreur": str(e)[:300]})
        except Exception as e:
            print("Dictee : transcription impossible (%s)" % type(e).__name__)
            return self.repondre(500, {"erreur": "transcription impossible (%s)" % type(e).__name__})
        finally:
            octets = None                          # le son ne survit pas a la requete
        # Le texte n'est PAS journalise : c'est ce que la personne vient de dire.
        return self.repondre(200, {"texte": texte})

    # ---------- routes ----------

    def cle_onglets_permise(self):
        """L'extension de Machi Tool : sa propre cle, et une origine
        d'extension (ou aucune). Pas le jeton du serveur local."""
        attendue = str(CFG.get("onglets_cle", "") or "")
        origine = self.headers.get("Origin", "")
        return bool(attendue) and (not origine or origine.startswith("chrome-extension://")) and \
            secrets.compare_digest(str(self.headers.get("X-Onglets-Cle", "")), attendue)

    def route_onglets(self, chemin):
        if not self.cle_onglets_permise():
            return self.repondre(401, {"erreur": "cle d'extension invalide"})
        if chemin == "/onglets/attente" and self.command == "GET":
            c = prochaine_commande_onglets()
            if c is None:
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            return self.repondre(200, c)
        if chemin == "/onglets/resultat" and self.command == "POST":
            resultat_onglets(self.lire_corps())
            return self.repondre(200, {"ok": True})
        return self.repondre(404, {"erreur": "route inconnue"})

    def do_GET(self):
        chemin = self.path.split("?")[0].rstrip("/") or "/"
        if chemin.startswith("/onglets/"):
            return self.route_onglets(chemin)
        if not self.origine_permise():
            return self.repondre(403, {"erreur": "origine non autorisee"})
        if chemin == "/etat":
            r, v, b = ETAT["couleur"]
            forcage = ETAT.get("forcage")
            return self.repondre(200, {
                "version": VERSION,
                "connecte": ETAT["connecte"],
                "couleur": rgb_vers_hex((r, v, b)),
                "rvb": [r, v, b],
                "source": ETAT["regle"],
                "mode": CFG.get("mode", "applications"),
                "force": bool(forcage and time.time() < forcage["expire"]),
                "humeurs": [r_["nom"] for r_ in CFG.get("regles", [])],
            })
        if chemin == "/dictee":
            if not (self.jeton_permis({}) or self.cle_pont_permise()):
                return self.repondre(401, {"erreur": "jeton invalide"})
            return self.repondre(200, etat_dictee())
        if chemin == "/activite":
            # Le site tire le digest du jour quand il veut, avec le jeton de
            # la passerelle locale — pas la cle du pont. Aucune dependance a
            # l'authentification du site : c'est lui qui appelle 127.0.0.1.
            if not (self.jeton_permis({}) or self.cle_pont_permise()):
                return self.repondre(401, {"erreur": "jeton invalide"})
            params = urllib.parse.parse_qs(self.path.partition("?")[2])
            if params.get("tout", ["0"])[0] in ("1", "true", "oui"):
                # Tout l'historique d'un coup : de quoi remettre a jour chaque
                # jour (lever, coucher, ecran) en un seul appel.
                return self.repondre(200, {
                    "jours": tous_les_jours_activite(),
                    "journal_actif": ACTIVITE["active"]})
            digest = dict(resume_activite())
            digest["journal_actif"] = ACTIVITE["active"]
            return self.repondre(200, digest)
        return self.repondre(404, {"erreur": "route inconnue"})

    def do_POST(self):
        chemin = self.path.split("?")[0].rstrip("/") or "/"
        if chemin.startswith("/onglets/"):
            return self.route_onglets(chemin)
        if not self.origine_permise():
            return self.repondre(403, {"erreur": "origine non autorisee"})
        # La dictee AVANT la lecture JSON : son corps est du son, pas du JSON.
        if chemin in ("/dictee", "/dictee/preparer"):
            return self.route_dictee(chemin)
        corps = self.lire_corps()
        if not self.jeton_permis(corps):
            return self.repondre(401, {"erreur": "jeton invalide"})

        duree = float(corps.get("duree", 30))
        duree = max(1.0, min(3600.0, duree))

        # Interrupteur maitre : si BrainDebugger n'a pas le droit de piloter la
        # guirlande, ses ordres de couleur sont recus poliment mais sans effet.
        # On ne pose aucun forcage, et le site le sait par la reponse.
        if chemin in ("/couleur", "/humeur") and not CFG.get("pont_affecte_leds", True):
            return self.repondre(200, {"ok": False, "desactive": True,
                                       "raison": "BrainDebugger n'affecte pas les LEDs"})

        if chemin == "/couleur":
            brut = corps.get("couleur")
            if isinstance(brut, str):
                rvb = hex_vers_rgb(brut)
            elif isinstance(brut, (list, tuple)) and len(brut) == 3:
                rvb = tuple(max(0, min(255, int(c))) for c in brut)
            else:
                return self.repondre(400, {"erreur": "couleur manquante"})
            ETAT["forcage"] = {"couleur": rvb, "expire": time.time() + duree,
                               "nom": corps.get("nom") or "Site web"}
            return self.repondre(200, {"ok": True, "couleur": rgb_vers_hex(rvb),
                                       "duree": duree})

        if chemin == "/humeur":
            nom = corps.get("humeur") or corps.get("nom")
            rvb = couleur_de_regle(CFG, nom)
            if not rvb:
                return self.repondre(404, {
                    "erreur": f"aucune regle nommee {nom!r}",
                    "humeurs": [r_["nom"] for r_ in CFG.get("regles", [])]})
            ETAT["forcage"] = {"couleur": rvb, "expire": time.time() + duree,
                               "nom": str(nom)}
            return self.repondre(200, {"ok": True, "humeur": nom,
                                       "couleur": rgb_vers_hex(rvb), "duree": duree})

        if chemin == "/presence":
            # Le site declare qu'on l'utilise. La duree est courte a
            # dessein : un onglet ferme brutalement ne doit pas laisser la
            # guirlande bloquee sur sa couleur.
            duree_p = max(5.0, min(300.0, float(corps.get("duree", 60))))
            if corps.get("actif", True):
                ETAT["presence"] = {"jusqu_a": time.time() + duree_p}
            else:
                ETAT["presence"] = None
                ETAT["presence_vu"] = 0.0
            # Present sur le site : bonne occasion de lui pousser la
            # journee a jour, sans attendre l'ecriture horaire.
            synchroniser_activite(CFG)
            return self.repondre(200, {"ok": True, "duree": duree_p})

        if chemin == "/relacher":
            ETAT["forcage"] = None
            return self.repondre(200, {"ok": True})

        # ---- BrainDebugger ----

        if chemin == "/rappel":
            titre = str(corps.get("titre") or "BrainDebugger")[:64]
            texte = str(corps.get("texte") or "")[:220]
            if not texte:
                return self.repondre(400, {"erreur": "texte manquant"})
            deposer_rappel(corps.get("id"), titre, texte)
            return self.repondre(200, {"ok": True})

        if chemin == "/humeur-du-jour":
            PONT["humeur"] = {
                "valeur": corps.get("valeur"),
                "libelle": str(corps.get("libelle") or "")[:60],
                "couleur": str(corps.get("couleur") or "")[:9],
                "date": str(corps.get("date") or "")[:32],
            }
            PONT["etat"] = "ok"
            PONT["vu_le"] = time.time()
            PONT["message"] = "Humeur recue du site."
            return self.repondre(200, {"ok": True})

        if chemin == "/journal":
            # Le site est maitre de ses donnees : on remplace, on ne fusionne
            # pas. Une entree effacee la-bas doit disparaitre ici aussi.
            jours = corps.get("jours")
            reperes = corps.get("reperes")
            if isinstance(jours, list):
                PONT["jours"] = [j for j in jours if isinstance(j, dict)][:400]
            if isinstance(reperes, list):
                PONT["reperes"] = [r for r in reperes if isinstance(r, dict)][:400]
            PONT["etat"] = "ok"
            PONT["vu_le"] = time.time()
            PONT["message"] = "Journal recu du site."
            return self.repondre(200, {"ok": True,
                                       "jours": len(PONT["jours"]),
                                       "reperes": len(PONT["reperes"])})

        return self.repondre(404, {"erreur": "route inconnue"})


def deposer_rappel(identifiant, titre, texte):
    """Range un rappel et le signale. Les doublons sont ignores : le site
    peut reemettre le meme tant qu'il n'a pas ete acquitte."""
    identifiant = str(identifiant or (titre + texte))[:80]
    if any(r["id"] == identifiant for r in PONT["rappels"]):
        return False
    PONT["rappels"].insert(0, {"id": identifiant, "titre": titre,
                               "texte": texte, "recu": time.time()})
    del PONT["rappels"][20:]
    PONT["etat"] = "ok"
    PONT["vu_le"] = time.time()
    PONT["message"] = titre
    ETAT["rappel_neuf"] = True     # la boucle du panneau le notifiera
    return True


def _plus_vieux_qu_un_jour(iso):
    """Vrai si cet horodatage ISO date de plus de 24 h (ou ne se lit pas)."""
    try:
        t = time.mktime(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
        # strptime rend une heure locale : l'ISO du site est en UTC.
        return (time.time() - (t - time.timezone)) > 86400
    except Exception:
        return False


def relever_le_site(cfg):
    """Demande au site ce qu'il a en attente.

    Necessaire parce que le site ne peut rien pousser quand aucun onglet
    n'est ouvert : cette machine n'a pas d'adresse joignable depuis
    Internet. C'est donc l'application qui va voir.

    Contrat attendu cote site, en GET sur <pont_site>/api/machitool/attente :
        {"rappels":  [{"id": "...", "titre": "...", "texte": "..."}],
         "humeur":   {"valeur": 3, "libelle": "...", "couleur": "#RRGGBB"},
         "jours":    [{"date": "2026-08-29", "note": "...", "couleur": "..."}],
         "reperes":  [{"date": "...", "titre": "...", "couleur": "..."}]}
    Toutes les cles sont facultatives. Tant que la route n'existe pas, le
    404 est avale sans bruit.
    """
    base = str(cfg.get("pont_site", "")).strip().rstrip("/")
    if not base:
        return False
    url = base + "/api/machitool/attente?version=" + urllib.parse.quote(VERSION)
    cle = str(cfg.get("pont_cle", "")).strip()
    entetes = {"User-Agent": "MachiToolkit/" + VERSION, "Accept": "application/json"}
    if cle:
        # La cle part de trois facons a la fois : le site n'a qu'a lire
        # celle qui l'arrange, sans qu'on ait a s'accorder d'avance.
        url += "&cle=" + urllib.parse.quote(cle)
        entetes["Authorization"] = "Bearer " + cle
        entetes["X-Machitool-Cle"] = cle

    PONT["etat"] = "releve"
    try:
        requete = urllib.request.Request(url, headers=entetes)
        with urllib.request.urlopen(requete, timeout=12,
                                    context=_contexte_ssl()) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        PONT["etat"] = "erreur"
        if e.code == 404:
            PONT["message"] = ("Le site ne propose pas encore de route "
                               "/api/machitool/attente.")
        elif e.code in (401, 403):
            PONT["message"] = (
                "Le site demande une authentification (%s). La route existe "
                "donc bien. Renseigne la cle dans Passerelle : elle part en "
                "Authorization: Bearer, en X-Machitool-Cle et en ?cle=."
                % e.code) if not cle else (
                "Le site refuse la cle (%s). Verifie qu'il attend la meme, "
                "et qu'il la lit dans l'un des trois emplacements envoyes."
                % e.code)
        else:
            PONT["message"] = "Le site a repondu %s." % e.code
        return False
    except Exception as e:
        PONT["etat"] = "erreur"
        PONT["message"] = "Site injoignable : %s" % str(e)[:60]
        return False

    if not isinstance(donnees, dict):
        PONT["etat"] = "erreur"
        PONT["message"] = "Reponse du site illisible."
        return False

    neufs = 0
    for rappel in (donnees.get("rappels") or []):
        if isinstance(rappel, dict) and rappel.get("texte"):
            if deposer_rappel(rappel.get("id"),
                              str(rappel.get("titre") or "BrainDebugger")[:64],
                              str(rappel["texte"])[:220]):
                neufs += 1
    if isinstance(donnees.get("humeur"), dict):
        PONT["humeur"] = donnees["humeur"]
    if isinstance(donnees.get("jours"), list):
        PONT["jours"] = [j for j in donnees["jours"] if isinstance(j, dict)][:400]
    if isinstance(donnees.get("reperes"), list):
        PONT["reperes"] = [r for r in donnees["reperes"] if isinstance(r, dict)][:400]

    # LA DEMANDE DE SYNCHRO. Le site ne peut rien pousser vers cette machine :
    # c'est ici, au releve, qu'on apprend qu'on la lui doit. Deux raisons de
    # partir : quelqu'un l'a demandee depuis le site (« synchroniser », meme
    # depuis un telephone), ou le site n'a rien recu depuis plus d'un jour alors
    # qu'on collecte -- une passerelle muette qui se repare toute seule.
    syn = donnees.get("synchro") if isinstance(donnees.get("synchro"), dict) else {}
    demande = str(syn.get("demande_le") or "")
    if demande and demande != SYNC.get("demande_vue"):
        SYNC["demande_vue"] = demande
        PONT["message"] = "Le site demande la journee : envoi en cours."
        synchroniser_activite(cfg, minimum=0)
    elif syn.get("recu_le") is None or _plus_vieux_qu_un_jour(syn.get("recu_le")):
        synchroniser_activite(cfg, minimum=6 * 3600)

    PONT["etat"] = "ok"
    PONT["vu_le"] = time.time()
    if neufs:
        PONT["message"] = "%d rappel(s) recu(s)." % neufs
    else:
        PONT["message"] = "Site joint, rien de neuf."
    return True


def demarrer_api(cfg):
    arreter_api()
    if not cfg.get("api_active"):
        ETAT["api"] = "arretee"
        return
    try:
        # DANS le try, pas devant : `jeton_courant` ecrit la configuration, et
        # une ecriture qui echoue remontait jusqu'a tuer le demarrage entier.
        jeton_courant(cfg)
        port = entier(cfg.get("api_port", 7373), 7373)
        serveur = http.server.ThreadingHTTPServer(("127.0.0.1", port), Passerelle)
        serveur.daemon_threads = True
        SERVEUR["http"] = serveur
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        ETAT["api"] = f"a l'ecoute sur 127.0.0.1:{port}"
        print("Passerelle HTTP demarree sur le port", port)
    except Exception as e:
        ETAT["api"] = f"echec : {str(e)[:40]}"
        print("Passerelle HTTP impossible :", e)


def arreter_api():
    if SERVEUR.get("http"):
        try:
            SERVEUR["http"].shutdown()
            SERVEUR["http"].server_close()
        except Exception:
            pass
        SERVEUR["http"] = None
    ETAT["api"] = "arretee"


# ==========================================================================
#  Fil Bluetooth
# ==========================================================================

async def lister_appareils(duree=8.0):
    from bleak import BleakScanner
    trouves = await BleakScanner.discover(timeout=duree)
    return sorted(trouves, key=lambda d: (d.name is None, d.name or "", d.address))


async def essai_connexion(adresse):
    from bleak import BleakClient
    async with BleakClient(adresse, timeout=20.0) as client:
        await client.write_gatt_char(UUID_ECRITURE, TRAME_ON, response=False)
        await asyncio.sleep(0.2)
        await client.write_gatt_char(UUID_ECRITURE, trame_lum(15), response=False)
        for c in [(0, 255, 90), (0, 0, 0), (0, 255, 90), (0, 0, 0), (0, 255, 90)]:
            await client.write_gatt_char(UUID_ECRITURE, trame_rgb(*c), response=False)
            await asyncio.sleep(0.35)
        await client.write_gatt_char(UUID_ECRITURE, trame_rgb(139, 92, 246), response=False)


async def une_session(cfg):
    from bleak import BleakClient
    import psutil

    adresse = str(cfg.get("adresse", "")).strip()
    boucle = asyncio.get_event_loop()
    r_a = v_a = b_a = 0.0
    dernier = (-9, -9, -9)
    psutil.cpu_percent(interval=None)

    try:
        ETAT["message"] = "Connexion..."
        async with BleakClient(adresse, timeout=20.0) as client:
            ETAT["connecte"] = True
            ETAT["message"] = "Connectee"
            BLE["client"] = client
            await client.write_gatt_char(UUID_ECRITURE, TRAME_ON, response=False)
            await asyncio.sleep(0.15)
            # Luminosite materielle au maximum : la modulation se fait dans les
            # valeurs RGB, ce qui donne des fondus continus au lieu des 15
            # paliers du controleur.
            await client.write_gatt_char(UUID_ECRITURE, trame_lum(15), response=False)

            depart = time.time()
            echeance = time.monotonic()
            while ETAT["en_marche"] and client.is_connected and not ETAT["demande"]:
                intervalle = 1.0 / max(1, int(cfg.get("images_par_seconde", 8)))

                if ETAT["pause"]:
                    ETAT["message"] = "En pause"
                    await asyncio.sleep(0.3)
                    continue

                contexte = fenetre_active()
                ETAT["contexte"] = contexte[:90]
                ETAT["message"] = "Connectee"
                mode = cfg.get("mode", "applications")

                (ra, va, ba), nom = couleur_cible(cfg, contexte)
                rc, vc, bc = ra, va, ba
                douceur = float(cfg.get("douceur", 0.06))
                gain = None

                forcage = ETAT.get("forcage")
                # Un forcage manuel (couleur choisie a la main) ne peremptore pas :
                # il tient jusqu'a ce qu'on relache. Le forcage du site, lui, a une
                # date d'expiration et rend la main tout seul.
                if forcage and (forcage.get("manuel") or time.time() < forcage["expire"]):
                    rc, vc, bc = forcage["couleur"]
                    nom = forcage["nom"]
                    mode = "force"
                elif forcage:
                    ETAT["forcage"] = None
                else:
                    # Passe devant l'ecran et le son, mais jamais devant une
                    # couleur que le site a explicitement posee. Des que la
                    # presence retombe, le mode normal reprend de lui-meme :
                    # il n'y a rien a restaurer.
                    site = presence_du_site(cfg, contexte)
                    if site:
                        (rc, vc, bc), nom = site
                        mode = "site"
                        douceur = float(cfg.get("douceur", 0.06))

                # JARVIS PASSE DEVANT TOUT : quand on lui parle, la guirlande dit
                # ou il en est -- il ecoute, il transcrit, il reflechit, il parle.
                jv = couleur_jarvis(cfg)
                if jv:
                    (rc, vc, bc), gain_jarvis = jv
                    nom = "Jarvis \u00b7 " + str(JARVIS.get("led"))
                    mode = "jarvis"
                    douceur = 0.5
                # ...sauf une de SES animations (une routine, un running gag) :
                # courte, voulue, elle se joue par-dessus.
                try:
                    veiller_routines(cfg, contexte)
                except Exception as e:
                    print("Routines : %s" % e)
                anim = couleur_de_l_animation()
                if anim is not None:
                    rc, vc, bc = anim
                    nom = "Routine \u00b7 " + ANIMATION["nom"]
                    mode = "routine"
                    douceur = 1.0

                if mode == "son":
                    if AUDIO["actif"]:
                        (rc, vc, bc), gain = couleur_son(cfg, (ra, va, ba))
                        nom = "Son \u00b7 " + cfg.get("son_bande", "graves")
                        douceur = 1.0      # l'enveloppe est deja faite cote audio
                    else:
                        nom = "Son indisponible"

                if mode in ("ecran", "mixte") and capture_autorisee():
                    resultat = await boucle.run_in_executor(
                        EXECUTEUR_CAPTURE, couleur_ecran,
                        cfg.get("ecran_source", "actif"),
                        float(cfg.get("ecran_saturation", 1.5)),
                        int(cfg.get("ecran_finesse", 4)))
                    # La degradation existe deja : quand resultat vaut None,
                    # la couleur de regle et le gain processeur reprennent la
                    # main plus bas. Il suffit donc de cesser d'appeler.
                    echec_capture(resultat is None)
                    if resultat:
                        (re, ve, be), luminance, index = resultat
                        # Suivre ce que l'oeil voit : filtre de lumiere bleue
                        # (rampe gamma) puis balance manuelle.
                        (re, ve, be) = adapter_couleur_ecran((re, ve, be), cfg)
                        if mode == "mixte":
                            rc, vc, bc = (re + ra) / 2, (ve + va) / 2, (be + ba) / 2
                            nom = f"{nom} + ecran {index}"
                        else:
                            rc, vc, bc = re, ve, be
                            nom = f"Ecran {index}"
                        douceur = float(cfg.get("douceur_ecran", 0.35))

                        cible = cfg.get("ecran_cible", "luminosite")
                        module = appliquer_niveaux(
                            luminance,
                            float(cfg.get("ecran_noir", 0.0)),
                            float(cfg.get("ecran_blanc", 0.62)),
                            float(cfg.get("ecran_gamma", 0.5)))
                        base = float(cfg.get("ecran_luminosite_base", 1.0))
                        plancher = float(cfg.get("ecran_luminance_min", 0.15))

                        if cible in ("luminosite", "les_deux"):
                            gain = plancher + (1 - plancher) * module
                        else:
                            gain = base
                        if cible in ("saturation", "les_deux"):
                            rc, vc, bc = resaturer_vers(
                                (rc, vc, bc), plancher + (1 - plancher) * module)

                        ETAT["ecran_luminance"] = luminance
                        ETAT["ecran_gain"] = gain
                        ETAT["ecran_sat"] = colorsys.rgb_to_hsv(
                            rc / 255.0, vc / 255.0, bc / 255.0)[1]

                ETAT["regle"] = nom

                inactif = (mode not in ("jarvis", "routine") and
                           secondes_inactivite() > float(cfg.get("veille_minutes", 6)) * 60)
                if mode == "jarvis":
                    gain = gain_jarvis
                elif mode == "routine":
                    gain = 1.0                 # l'animation est deja dosee
                elif inactif:
                    rc, vc, bc = hex_vers_rgb(cfg.get("couleur_veille", "#3B1F0B"))
                    gain = float(cfg.get("veille_luminosite", 0.18))
                    douceur = float(cfg.get("douceur", 0.06))
                    ETAT["regle"] = "Veille"
                elif gain is None:
                    if cfg.get("reaction_processeur", True):
                        charge = psutil.cpu_percent(interval=None) / 100.0
                        lo = float(cfg.get("luminosite_min", 0.45))
                        hi = float(cfg.get("luminosite_max", 1.0))
                        gain = lo + charge * (hi - lo)
                    else:
                        gain = float(cfg.get("luminosite_max", 1.0))

                amp = float(cfg.get("amplitude_respiration", 0.1))
                if amp > 0 and not inactif and mode == "applications":
                    per = max(1.0, float(cfg.get("periode_respiration", 11.0)))
                    gain *= 1.0 + amp * math.sin(2 * math.pi * (time.time() - depart) / per)

                gain = max(0.03, min(1.0, gain))
                rc, vc, bc = rc * gain, vc * gain, bc * gain

                k = max(0.005, min(1.0, douceur))
                r_a += (rc - r_a) * k
                v_a += (vc - v_a) * k
                b_a += (bc - b_a) * k

                envoi = (int(r_a), int(v_a), int(b_a))
                ETAT["couleur"] = envoi
                # L'image que la guirlande tient pendant ce tour -- envoyee ou
                # non (un changement de moins de 2 n'est pas renvoye, elle garde
                # la precedente, qui en differe a peine).
                noter_image_led(envoi)
                if max(abs(x - y) for x, y in zip(envoi, dernier)) >= 2:
                    try:
                        await client.write_gatt_char(
                            UUID_ECRITURE, trame_rgb(*envoi), response=False)
                        dernier = envoi
                    except Exception as e:
                        ETAT["message"] = f"Ecriture perdue : {str(e)[:50]}"
                        break

                # Dormir un intervalle plein apres le travail ajouterait la
                # duree de ce travail a chaque tour : a 60 images par
                # seconde la cadence reelle s'effondrerait. On vise une
                # echeance et on ne dort que ce qui reste.
                echeance += intervalle
                reste = echeance - time.monotonic()
                if reste < -intervalle:
                    echeance = time.monotonic()   # retard franc : on repart
                    reste = 0
                await asyncio.sleep(max(0.0, reste))

    except Exception as e:
        ETAT["message"] = f"Deconnectee ({str(e)[:55]})"
        """
        ET ON L'ECRIT DANS LE JOURNAL, pas seulement dans le panneau.

        Ce message ne vivait que dans `ETAT`, c'est-a-dire dans une fenetre
        qu'il faut avoir ouverte au bon moment pour le lire. Une guirlande qui
        se deconnecte et se reconnecte toutes les dix secondes CLIGNOTE, et
        c'est tout ce qu'on en voyait -- aucune trace, nulle part, de ce qui la
        faisait tomber.
        """
        print("Session Bluetooth tombee : %s : %s"
              % (type(e).__name__, str(e)[:160]))
    BLE["client"] = None
    ETAT["connecte"] = False


async def superviseur(cfg):
    while ETAT["en_marche"]:
        demande = ETAT["demande"]

        if demande == "scan":
            ETAT["demande"] = None
            ETAT["occupe"] = True
            ETAT["message"] = "Recherche Bluetooth (8 s)..."
            try:
                trouves = await lister_appareils()
                ETAT["appareils"] = [(a.name or "(sans nom)", a.address) for a in trouves]
                ETAT["message"] = f"{len(trouves)} appareil(s) trouve(s)"
            except Exception as e:
                ETAT["appareils"] = []
                ETAT["message"] = f"Recherche impossible : {str(e)[:55]}"
            ETAT["occupe"] = False

        elif demande == "test":
            ETAT["demande"] = None
            ETAT["occupe"] = True
            adr = ETAT["adresse_test"]
            ETAT["message"] = f"Test de {adr}..."
            try:
                await essai_connexion(adr)
                cfg["adresse"] = adr
                sauver_config(cfg)
                ETAT["resultat"] = "ok"
                ETAT["message"] = "Guirlande enregistree"
            except Exception as e:
                ETAT["resultat"] = "echec"
                ETAT["message"] = f"Echec : {str(e)[:55]}"
            ETAT["occupe"] = False

        elif demande == "reconnecter":
            ETAT["demande"] = None

        elif str(cfg.get("adresse", "")).strip():
            """
            UNE ATTENTE QUI GRANDIT QUAND LA SESSION NE TIENT PAS.

            Dix secondes fixes entre deux tentatives : une guirlande qui tombe
            aussitot connectee se rallume et s'eteint toutes les dix secondes,
            sans fin. C'est ce qu'on voit -- elle clignote -- et c'est aussi ce
            qui martele la pile Bluetooth de Windows, la ou les plantages sans
            exception Python se produisent.

            Une session qui a TENU remet le compteur a zero : le cas normal ne
            paie rien. Ce sont les echecs consecutifs qui s'espacent, jusqu'a
            une minute. On ne renonce jamais -- une guirlande eteinte parce
            qu'elle etait hors de portee doit revenir quand elle rentre.
            """
            debut = time.monotonic()
            await une_session(cfg)
            attente = attente_apres_session(time.monotonic() - debut)
            for _ in range(int(attente * 10)):
                if not ETAT["en_marche"] or ETAT["demande"]:
                    break
                await asyncio.sleep(0.1)

        else:
            ETAT["message"] = "Aucune guirlande appairee"
            await asyncio.sleep(0.4)


# ==========================================================================
#  Resolution de l'ecran
#
#  Une fenetre tkinter est dessinee pour du 96 points par pouce. Sur un 4K
#  a 150 ou 200 %, Windows a deux facons de s'en sortir, et les deux sont
#  mauvaises tant qu'on ne fait rien :
#
#    - processus inconscient de la resolution : Windows agrandit l'image de
#      la fenetre. Rien n'est coupe, mais tout est flou ;
#    - processus conscient : la fenetre est nette, mais 780 pixels restent
#      780 pixels physiques. Sur un 4K, c'est un timbre-poste, et les
#      caracteres deviennent illisibles.
#
#  On prend donc la deuxieme voie et on remet l'echelle a la main : tk
#  scaling pour les caracteres, un facteur pour tout ce qui est exprime en
#  pixels. Le resultat est net ET a la bonne taille.
# ==========================================================================

# La boucle Bluetooth vit dans son propre fil. Pour lui faire envoyer une
# trame depuis un autre fil — la fermeture de Windows, le bouton Quitter —
# il faut passer par elle, d'ou cette reference.
BLE = {"boucle": None, "client": None}

# Une session qui a dure au moins ca a « tenu » : ce n'est pas un echec de
# connexion, c'est une session normale qui s'est terminee.
SESSION_TENUE = 20.0
# L'attente avant la tentative suivante, par nombre d'echecs consecutifs.
ATTENTE_BLE = [10.0, 10.0, 25.0, 60.0]


def attente_apres_session(tenue):
    """Combien attendre avant de retenter, d'apres la duree de la session.

    Une session qui a TENU remet le compteur a zero : le cas normal ne paie
    rien. Ce sont les echecs consecutifs qui s'espacent, jusqu'a une minute.
    On ne renonce jamais -- une guirlande eteinte parce qu'elle etait hors de
    portee doit revenir quand elle rentre.
    """
    if tenue >= SESSION_TENUE:
        ETAT["echecs_ble"] = 0
    else:
        ETAT["echecs_ble"] = min(ETAT.get("echecs_ble", 0) + 1, len(ATTENTE_BLE) - 1)
        if ETAT["echecs_ble"] >= 2:
            ETAT["message"] = ("Guirlande injoignable, nouvelle tentative dans %d s"
                               % int(ATTENTE_BLE[ETAT["echecs_ble"]]))
    return ATTENTE_BLE[ETAT.get("echecs_ble", 0)]


def eteindre_guirlande(delai=2.5):
    """Envoie la trame d'extinction et attend qu'elle parte.

    Bloquant volontairement : appelee pendant l'arret de Windows, elle n'a
    que quelques secondes avant que le processus soit tue, et rendre la
    main trop tot laisserait la guirlande allumee.
    """
    boucle = BLE.get("boucle")
    client = BLE.get("client")
    if not boucle or not client:
        return False
    try:
        if not client.is_connected:
            return False
    except Exception:
        return False

    async def envoyer():
        await client.write_gatt_char(UUID_ECRITURE, trame_rgb(0, 0, 0),
                                     response=False)
        await client.write_gatt_char(UUID_ECRITURE, TRAME_OFF, response=False)

    try:
        travail = asyncio.run_coroutine_threadsafe(envoyer(), boucle)
        travail.result(timeout=delai)
        print("Guirlande eteinte.")
        return True
    except Exception as e:
        print("Extinction impossible :", e)
        return False


def surveiller_arret_windows():
    """Fenetre cachee qui ecoute la fermeture de session.

    Windows previent les applications par WM_QUERYENDSESSION avant de les
    tuer. Sans fenetre pour recevoir ce message, l'application disparait
    sans un mot et la guirlande garde sa derniere couleur jusqu'a ce qu'on
    la debranche.
    """
    if os.name != "nt":
        return
    try:
        import win32gui
    except ImportError:
        return

    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016
    # Quand l'Explorateur redemarre (plantage, mise a jour, ou simplement
    # trop lent a l'ouverture de session), Windows retire TOUTES les icones
    # de la barre et diffuse « TaskbarCreated » : a chaque application de
    # reposer la sienne. pystray ne l'ecoute pas ; cette fenetre-ci, si.
    try:
        import ctypes
        MSG_BARRE = ctypes.windll.user32.RegisterWindowMessageW("TaskbarCreated")
    except Exception:
        MSG_BARRE = 0

    def traiter(fenetre, message, wparam, lparam):
        if MSG_BARRE and message == MSG_BARRE:
            TRAY["reposer"] = True
            print("Barre des taches recreee : l'icone sera reposee.")
            return 0
        if message in (WM_QUERYENDSESSION, WM_ENDSESSION):
            if CFG.get("eteindre_en_partant", True):
                eteindre_guirlande()
            if CFG.get("collecte_active", False):
                noter_session("extinction")    # vaut coucher : Windows s'arrete
                sauver_activite()
            # Repondre vrai a QUERYENDSESSION : on ne bloque pas l'arret.
            return True
        return win32gui.DefWindowProc(fenetre, message, wparam, lparam)

    def fil():
        try:
            classe = win32gui.WNDCLASS()
            classe.lpszClassName = "MachiToolArret"
            classe.lpfnWndProc = traiter
            atome = win32gui.RegisterClass(classe)
            fenetre = win32gui.CreateWindow(
                atome, "MachiTool", 0, 0, 0, 0, 0, 0, 0,
                win32gui.GetModuleHandle(None), None)
            try:
                # Sans cela, Windows peut arreter le processus avant de
                # poster le message aux applications sans interface.
                import ctypes
                ctypes.windll.user32.ShutdownBlockReasonCreate(
                    fenetre, "Extinction de la guirlande")
            except Exception:
                pass
            win32gui.PumpMessages()
        except Exception as e:
            print("Surveillance de l'arret impossible :", e)

    threading.Thread(target=fil, daemon=True).start()


def chemin_icone():
    """Le .ico a poser sur la fenetre, ecrit si besoin.

    --icon de PyInstaller ne fait qu'une chose : graver l'icone dans le
    fichier .exe. Il n'en depose aucune copie sur le disque. La fenetre,
    elle, reclame un vrai fichier — sans quoi Tk met sa plume par defaut.
    On embarque donc le .ico comme donnee, et on le regenere si jamais il
    manque.
    """
    candidats = []
    interne = getattr(sys, "_MEIPASS", None)     # depaquetage de l'exe
    if interne:
        candidats.append(os.path.join(interne, "icone.ico"))
    candidats.append(os.path.join(DOSSIER, "icone.ico"))
    if not FIGE:
        candidats.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "icone.ico"))
    for chemin in candidats:
        if os.path.exists(chemin):
            return chemin

    depose = os.path.join(DOSSIER, "icone.ico")
    try:
        ecrire_icone(depose)
        return depose
    except Exception as e:
        print("Icone indisponible :", e)
        return None


def identite_barre_taches():
    """Sans identite propre, Windows range la fenetre sous celle de Python
    et lui prete son icone. Une chaine a nous suffit a la detacher."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TheMashy.MachiTool")
    except Exception:
        pass


# Une fois pose, Windows refuse de changer d'avis : un second appel echouerait
# et ferait ecrire au journal un mode qui n'est pas celui en vigueur.
DPI = {"pose": False}


def activer_dpi():
    """A appeler avant la premiere fenetre, sinon Windows l'ignore.

    ON REGARDE CE QUE WINDOWS REPOND, PAS SEULEMENT S'IL A REPONDU.

    Ces trois fonctions ne LEVENT pas quand elles echouent : elles rendent
    faux. La boucle attrapait donc l'exception qui ne venait jamais, et
    sortait sur la premiere — meme quand celle-ci avait refuse. Le processus
    restait alors aveugle a la finesse des ecrans, GetDpiForWindow renvoyait
    partout celle du principal, et la fenetre gardait la taille du 4K en
    passant sur le 1080p : trop grande, tronquee par le bas.

    On lit maintenant la reponse, on passe a la suivante si elle est
    negative, et on ecrit dans le journal ce qui a fini par prendre.
    """
    if os.name != "nt" or DPI["pose"]:
        return
    DPI["pose"] = True
    import ctypes
    user32, shcore = ctypes.windll.user32, None
    try:
        shcore = ctypes.windll.shcore
    except Exception:
        pass

    def par_ecran_v2():
        # -4 = par ecran, version 2 : suit le facteur de chaque moniteur, y
        # compris quand la fenetre est deplacee de l'un a l'autre.
        return bool(user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)))

    def par_ecran():
        if shcore is None:
            return False
        # HRESULT : 0 = pose, 0x80070005 = deja pose par quelqu'un d'autre.
        r = shcore.SetProcessDpiAwareness(2)
        return r in (0, -2147024891)

    def systeme():
        return bool(user32.SetProcessDPIAware())

    for nom, tentative in (("par ecran v2", par_ecran_v2),
                           ("par ecran", par_ecran),
                           ("systeme", systeme)):
        try:
            if tentative():
                print("Finesse d'ecran : mode « %s ». %s" % (nom, _dit_la_finesse()))
                return
        except Exception:
            continue
    print("Finesse d'ecran : aucun mode accepte. %s" % _dit_la_finesse())


def _dit_la_finesse():
    """Ce que Windows dit VRAIMENT du processus, une fois les appels passes.

    Sans cette relecture, un journal qui annonce « par ecran v2 » ne prouve
    rien : c'est ce qui manquait pour voir que la fenetre restait a l'echelle
    du 4K sur le 1080p.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        contexte = user32.GetThreadDpiAwarenessContext()
        niveau = user32.GetAwarenessFromDpiAwarenessContext(contexte)
        return "Windows repond : %s." % {0: "aveugle", 1: "systeme",
                                         2: "par ecran"}.get(niveau, "inconnu (%s)" % niveau)
    except Exception:
        return "Windows ne sait pas le dire (version trop ancienne)."


def dpi_de_la_fenetre(racine):
    """Points par pouce de l'ecran ou se trouve reellement la fenetre.

    winfo_fpixels ne connait que l'ecran sur lequel Tk a demarre. Sur un
    poste a deux ecrans de finesse differente — un 4K et un 1080p — il
    renvoie donc toujours le meme chiffre, et la fenetre garde la taille du
    premier ecran en passant sur le second. GetDpiForWindow, lui, repond
    pour le moniteur qui porte la fenetre a cet instant.
    """
    if os.name == "nt":
        try:
            import ctypes
            poignee = racine.winfo_id()
            # La fenetre Tk est un enfant : c'est son ancetre de plus haut
            # niveau qui porte la resolution.
            racine_win = ctypes.windll.user32.GetAncestor(poignee, 2)
            ppp = ctypes.windll.user32.GetDpiForWindow(racine_win or poignee)
            if ppp:
                return float(ppp)
        except Exception:
            pass
    try:
        return float(racine.winfo_fpixels("1i"))
    except Exception:
        return 96.0


# La fenetre, en pixels a l'echelle 1. Tout le reste s'en deduit : c'est ce
# couple que l'echelle multiplie, et c'est donc lui qu'il faut comparer a la
# place disponible sur l'ecran.
FENETRE_BASE = (780, 700)
FENETRE_MINI = (720, 640)


def _ecran_de_la_fenetre(racine):
    """(ecran, zone de travail) du moniteur qui porte la fenetre, en pixels.

    La zone de travail exclut la barre des taches : c'est elle qui dit la
    place reellement disponible, pas la resolution.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        poignee = user32.GetAncestor(racine.winfo_id(), 2) or racine.winfo_id()

        class INFOS_MONITEUR(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        moniteur = user32.MonitorFromWindow(poignee, 2)   # 2 = le plus proche
        if not moniteur:
            return None
        infos = INFOS_MONITEUR()
        infos.cbSize = ctypes.sizeof(INFOS_MONITEUR)
        if not user32.GetMonitorInfoW(moniteur, ctypes.byref(infos)):
            return None
        cadre = wintypes.RECT()
        if not user32.GetWindowRect(poignee, ctypes.byref(cadre)):
            cadre = None
        return infos.rcMonitor, infos.rcWork, cadre
    except Exception:
        return None


def fenetre_a_cheval(racine):
    """Vrai si la fenetre deborde du moniteur qui la porte.

    C'EST LA CAUSE DE LA BOUCLE. Rebatir l'interface la REDIMENSIONNE ; a
    cheval sur un 4K et un 1080p, la nouvelle taille change le moniteur qui en
    porte le plus, donc la reponse de GetDpiForWindow, donc l'echelle voulue —
    et on repart. Deux fois et demie par seconde, la fenetre coincee entre les
    deux ecrans, sautant d'un rapport a l'autre sans fin.

    Tant qu'elle deborde, on ne touche a rien : la mesure ne veut rien dire
    tant que la fenetre n'est pas posee quelque part.
    """
    lu = _ecran_de_la_fenetre(racine)
    if not lu:
        return False
    e, _, cadre = lu
    if cadre is None:
        return False
    return (cadre.left < e.left or cadre.top < e.top
            or cadre.right > e.right or cadre.bottom > e.bottom)


def echelle_tenable(racine, voulue, marge=0.92):
    """Rabaisse l'echelle jusqu'a ce que la fenetre TIENNE sur l'ecran.

    LA FINESSE N'EST PAS LA PLACE, et c'est le defaut qu'on repare ici.
    L'echelle ne se deduisait que des points par pouce : un 4K a 180 ppp donne
    1,875, soit une fenetre de 1443 par 1295. Elle tient largement sur le 4K.
    Sur le 1080p d'a cote, la meme fenetre est plus haute que l'ecran — on la
    voyait deborder, tronquee par le bas, avec des caracteres enormes.

    Deux moniteurs peuvent avoir la meme finesse et pas du tout la meme
    surface. On borne donc par la zone de travail — celle qui exclut la barre
    des taches, la seule qui dise la place vraiment disponible.
    """
    lu = _ecran_de_la_fenetre(racine)
    if not lu:
        return voulue
    zone = lu[1]
    largeur = max(1, zone.right - zone.left)
    hauteur = max(1, zone.bottom - zone.top)
    tenable = min(largeur * marge / FENETRE_BASE[0], hauteur * marge / FENETRE_BASE[1])
    # Jamais en dessous de 1 : sous cette taille l'interface ne se lit plus, et
    # une fenetre trop grande qu'on peut deplacer vaut mieux qu'illisible.
    return max(1.0, min(voulue, tenable))


def echelle_ecran(racine, forcee=0.0):
    """Facteur a appliquer aux tailles en pixels. 1.0 = ecran 96 ppp."""
    try:
        if forcee and float(forcee) > 0:
            # Meme un reglage manuel est borne : personne ne veut d'une fenetre
            # plus grande que son ecran, et c'est reglable dans l'autre sens.
            return echelle_tenable(racine, max(0.75, min(4.0, float(forcee))))
    except (TypeError, ValueError):
        pass
    return echelle_tenable(racine, max(1.0, min(4.0, dpi_de_la_fenetre(racine) / 96.0)))


# ==========================================================================
#  Panneau
#
#  Direction : un ciel de nuit gris-bleu, calme, ou une seule chose bouge --
#  le graphe de ce que la guirlande montre, en tete, image par image. Le rail
#  ne porte plus que des icones, une par page, sur un semis de petites etoiles
#  jaunes ; la page ouverte a la sienne. Le reste se tait.
# ==========================================================================

NUIT    = "#171C26"   # fond : gris-bleu de nuit
VELOURS = "#1F2633"   # panneaux
ENCRE   = "#131821"   # champs et creux
FIL     = "#2B3445"   # filets
CRAIE   = "#E4E9F1"   # texte
BRUME   = "#8A95A8"   # texte secondaire
ETOILE  = "#F2C94C"   # les petites etoiles jaunes
VIF     = "#5CE6A4"   # connecte
ALERTE  = "#FF8A6B"   # deconnecte
SOURD   = (92, 104, 124)   # une lumiere eteinte, un objet au repos

NUIT_RGB = hex_vers_rgb(NUIT)

# UNE PAGE = UNE ICONE. Plus de groupes a deplier : on voit tout d'un coup
# d'oeil, et le nom de la page apparait au survol. Le groupe ne sert plus qu'a
# deux choses : un petit ecart entre les icones, et savoir quelles pages le
# bandeau de la lampe (ou du pont) coiffe.
MENU = [
    # (cle, nom, icone, groupe)
    ("accueil",    "Accueil",         "\u2302", None),
    ("etat",       "Lampe",           "\u2600", "lampe"),
    ("ecran",      "Ecran",           "\u25ad", "lampe"),
    ("son",        "Son",             "\u266a", "lampe"),
    ("appairage",  "Appairage",       "\u21c4", "lampe"),
    ("jarvis",     "Jarvis",          "\u25ce", "jarvis"),
    ("passerelle", "BrainDebugger",   "\u25c8", "pont"),
    ("activite",   "Quantified Self", "\u25a4", "pont"),
    ("reglages",   "Reglages",        "\u2699", "app"),
    ("maj",        "Mises a jour",    "\u21bb", "app"),
]

# Ou se range chaque page : le bandeau de la lampe coiffe les pages du groupe
# « lampe », et la page Regles, sans icone, en fait partie.
GROUPE_DE = {cle: groupe for cle, _, _, groupe in MENU if groupe}
GROUPE_DE["regles"] = "lampe"


def melange(avant, arriere, part):
    """Simule une transparence : tkinter ne connait pas le canal alpha."""
    return rgb_vers_hex(tuple(avant[i] * part + arriere[i] * (1 - part) for i in range(3)))


def lisible(rgb):
    """Remonte la valeur d'une couleur trop sombre pour servir d'accent."""
    h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in rgb])
    r, g, b = colorsys.hsv_to_rgb(h, s, max(0.72, v))
    return rgb_vers_hex((r * 255, g * 255, b * 255))


RAIL_LARGEUR = 64          # le rail d'icones, en pixels a l'echelle 1
GRAPHE_HAUTEUR = 74       # le graphe de la guirlande, en tete
GRAPHE_PAS = 3            # largeur d'une image dans le graphe


AIDE_LONGUE = 150         # au-dela, une explication ne montre que sa premiere phrase


def aide_courte(txt, limite=AIDE_LONGUE):
    """La premiere phrase d'une longue explication, et « plus › » ; None si
    elle est deja courte (on la montre entiere)."""
    t = " ".join(str(txt or "").split())
    if len(t) <= limite:
        return None
    m = re.match(r"(.+?[.!?\u00bb])(?=\s+[A-Z\u00ab(\"]|\s+--\s)", t)
    premiere = m.group(1) if m else t
    if len(premiere) > limite:
        coupe = t[:limite].rsplit(" ", 1)[0].rstrip(" ,;:-")
        premiere = coupe + "\u2026"
    if len(premiere) >= len(t) - 3:
        return None
    return premiere + "   plus \u203a"


class Panneau:
    def __init__(self, cfg, quitter_tout):
        import tkinter as tk
        from tkinter import ttk, font as tkfont
        self.tk, self.ttk = tk, ttk
        self.cfg = cfg
        self.quitter_tout = quitter_tout
        self.lignes = []
        self.pages = {}
        self.onglets = {}
        self.section = "accueil"
        # Lampe deplie au demarrage : c'est le module qu'on ouvre le plus.
        self.groupes = {"lampe": True, "pont": False, "app": False}
        self.apercus = []      # pastilles de couleur a repeindre
        self.reglettes = []
        self.accent = ACCENT_DEPART
        self.phase = 0.0
        # Remplace par lancer() : le panneau demande, la boucle principale agit.
        self.declencher_maj = lambda quoi="verifier": None
        # Incremente a chaque reconstruction : les boucles differees d'une
        # generation precedente s'arretent au lieu de se dedoubler.
        self.generation = 0

        self.root = tk.Tk()
        self.echelle = echelle_ecran(self.root, self.cfg.get("echelle_interface", 0.0))
        # Ce qu'a vu `suivre_ecran` au dernier passage, et depuis combien de
        # passages. Voir cette methode : c'est ce qui empeche la fenetre de
        # sauter d'un rapport a l'autre pendant qu'on la traine entre deux
        # ecrans de finesse differente.
        self._ech_vue, self._ech_tics = None, 0
        # tk scaling est le nombre de pixels par point : il fait grandir les
        # caracteres, dont la taille est donnee en points.
        try:
            self.root.tk.call("tk", "scaling", self.echelle * 96.0 / 72.0)
        except Exception:
            pass

        self.root.title(NOM_APP)
        self.root.geometry("%dx%d" % (self.px(FENETRE_BASE[0]), self.px(FENETRE_BASE[1])))
        self.root.minsize(self.px(FENETRE_MINI[0]), self.px(FENETRE_MINI[1]))
        self.root.configure(bg=NUIT)
        self.root.protocol("WM_DELETE_WINDOW", self.cacher)
        try:
            ico = chemin_icone()
            if ico:
                # default : vaut aussi pour les fenetres ouvertes ensuite.
                self.root.iconbitmap(default=ico)
        except Exception as e:
            print("Icone de fenetre refusee :", e)

        familles = {f.lower() for f in tkfont.families(self.root)}
        def choisir(*noms):
            for n in noms:
                if n.lower() in familles:
                    return n
            return "Segoe UI"
        self.f_titre = choisir("Bahnschrift", "Segoe UI Semibold", "Segoe UI")
        self.f_ui    = choisir("Segoe UI", "Tahoma")
        self.f_mono  = choisir("Cascadia Mono", "Consolas", "Courier New")
        # Les glyphes de symboles manquent aux polices de texte courantes.
        self.f_icone = choisir("Segoe UI Symbol", "Segoe UI", "Tahoma")

        self.construire_tout()

    def construire_tout(self):
        """Tout ce qui depend de l'echelle. Rejoue tel quel quand la
        fenetre change d'ecran."""
        tk = self.tk
        self.construire_entete()
        self.construire_pied()

        corps = tk.Frame(self.root, bg=NUIT)
        corps.pack(fill="both", expand=True)

        self.rail = tk.Frame(corps, bg=NUIT, width=self.px(RAIL_LARGEUR))
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)
        self.construire_rail()

        tk.Frame(corps, bg=FIL, width=1).pack(side="left", fill="y")

        self.zone = tk.Frame(corps, bg=NUIT)
        self.zone.pack(side="left", fill="both", expand=True)
        self.construire_bandeau()

        self.page_accueil()
        self.page_etat()
        self.page_regles()
        self.page_ecran()
        self.page_son()
        self.page_reglages()
        self.page_maj()
        self.page_passerelle()
        self.page_activite()
        self.page_appairage()
        self.page_jarvis()
        self.aller(self.section if self.section in self.pages else "accueil")

        self.animer()
        self.rafraichir()
        self.boule = None
        self.boule_etat = {"x": None, "y": None, "phase": 0.0, "alpha": 0.0}
        self.root.after(500, self.boule_tic)

    def refaire_interface(self, echelle):
        """Refait l'interface a l'echelle du nouvel ecran.

        tkinter fige la taille des caracteres a la creation du widget :
        changer tk scaling ensuite ne les redessine pas. Il faut donc tout
        rebatir. Les reglages non enregistres repartent du fichier — c'est
        le prix, et changer d'ecran reste rare.
        """
        self.generation += 1
        self.echelle = echelle
        try:
            self.root.tk.call("tk", "scaling", echelle * 96.0 / 72.0)
        except Exception:
            pass

        # La position est gardee, la taille repart de la mesure de base :
        # c'est justement elle qui doit changer d'echelle.
        position = ""
        try:
            morceaux = self.root.geometry().split("+", 1)
            if len(morceaux) > 1:
                position = "+" + morceaux[1]
        except Exception:
            pass

        for enfant in list(self.root.winfo_children()):
            try:
                enfant.destroy()
            except Exception:
                pass

        self.lignes = []
        self.pages = {}
        self.onglets = {}
        self.reglettes = []
        self.apercus = []

        self.root.minsize(self.px(FENETRE_MINI[0]), self.px(FENETRE_MINI[1]))
        self.root.geometry("%dx%d%s" % (self.px(FENETRE_BASE[0]), self.px(FENETRE_BASE[1]), position))
        self.construire_tout()
        print("Interface refaite a l'echelle %.2f" % echelle)

    def px(self, n):
        """Convertit une mesure pensee en 96 ppp vers l'ecran reel."""
        return max(1, int(round(n * self.echelle)))

    def interface_visible(self):
        """La fenetre est-elle vraiment a l'ecran ?

        Rangee dans la barre des taches (withdraw) ou reduite, elle n'a rien a
        redessiner. On le demande a Tk plutot qu'a un drapeau a nous : c'est
        l'etat reel, y compris quand Windows a retire la fenetre sous nos pieds.
        """
        try:
            if not self.root.winfo_exists():
                return False
            if self.root.state() in ("withdrawn", "iconic"):
                return False
            return bool(self.root.winfo_viewable())
        except Exception:
            return False

    # ------------------------------------------------------------------
    #  Signature : le graphe de ce que la guirlande montre
    #
    #  Il remplace le brin d'ampoules decoratif : une colonne par image que la
    #  guirlande a reellement tenue, a sa cadence -- sa couleur est celle que la
    #  LED emet (vu_a_l_oeil), sa hauteur son intensite (eclat). Il defile donc
    #  exactement a la vitesse reglee, et le coin dit la cadence tenue.
    # ------------------------------------------------------------------

    def construire_entete(self):
        tk = self.tk
        self.graphe = tk.Canvas(self.root, height=self.px(GRAPHE_HAUTEUR), bg=NUIT,
                                highlightthickness=0)
        self.graphe.pack(fill="x")
        self.graphe_vu = 0
        self.graphe_barres = deque()
        self.graphe_largeur = 0
        self.cadence_vue = 0.0
        self.graphe.bind("<Configure>", lambda e: self.redessiner_graphe(e.width))
        # Des maintenant, pas au premier <Configure> : sans image (guirlande pas
        # encore connectee), le compteur de cadence doit deja exister.
        self.redessiner_graphe(self.px(FENETRE_BASE[0]))

        ligne = tk.Frame(self.root, bg=NUIT, padx=self.px(18))
        ligne.pack(fill="x", pady=(self.px(4), self.px(10)))
        self.txt_titre = tk.Label(ligne, text="M A C H I   T O O L", bg=NUIT, fg=CRAIE,
                                  font=(self.f_titre, 14), anchor="w")
        self.txt_titre.pack(side="left")
        self.txt_trame = tk.Label(ligne, text="", bg=NUIT, fg=BRUME,
                                  font=(self.f_mono, 8), anchor="e")
        self.txt_trame.pack(side="right")
        self.txt_statut = tk.Label(ligne, text="", bg=NUIT, fg=BRUME,
                                   font=(self.f_ui, 9), anchor="w")
        self.txt_statut.pack(side="left", padx=(12, 0))

        tk.Frame(self.root, bg=FIL, height=1).pack(fill="x")

    def _geometrie_graphe(self):
        h = self.px(GRAPHE_HAUTEUR)
        return h - self.px(10), h - self.px(24)          # ligne de base, hauteur utile

    def _barre(self, x, rgb):
        base, utile = self._geometrie_graphe()
        haut = base - max(self.px(2), eclat(rgb) * utile)
        return self.graphe.create_rectangle(x, haut, x + self.px(GRAPHE_PAS), base, outline="",
                                            fill=rgb_vers_hex(vu_a_l_oeil(rgb)), tags=("barre",))

    def redessiner_graphe(self, largeur=None):
        """Tout redessiner depuis l'historique : au redimensionnement, et quand
        la fenetre revient apres avoir ete cachee (les images ont continue)."""
        g = self.graphe
        largeur = largeur or g.winfo_width()
        self.graphe_largeur = largeur
        g.delete("all")
        self.graphe_barres = deque()
        base, _ = self._geometrie_graphe()
        g.create_line(self.px(18), base + self.px(1), largeur - self.px(18), base + self.px(1),
                      fill=FIL, tags=("socle",))
        self.graphe_cadence = g.create_text(largeur - self.px(18), self.px(10), text="",
                                            anchor="ne", fill=BRUME, font=(self.f_mono, 8))
        self.graphe_absent = g.create_text(self.px(18), self.px(10), text="", anchor="nw",
                                           fill=BRUME, font=(self.f_ui, 8))
        pas = self.px(GRAPHE_PAS)
        capacite = max(1, (largeur - 2 * self.px(18)) // pas)
        images = list(IMAGES_LED)[-capacite:]
        x = largeur - self.px(18) - len(images) * pas
        for _, _, rgb in images:
            self.graphe_barres.append(self._barre(x, rgb))
            x += pas
        g.tag_raise(self.graphe_cadence)
        self.graphe_vu = images[-1][0] if images else _IMAGES_N[0]

    def avancer_graphe(self):
        """Les images arrivees depuis le dernier tour, une colonne chacune : le
        graphe avance au pas de la guirlande, pas a celui du panneau."""
        nouvelles = images_depuis(self.graphe_vu)
        pas = self.px(GRAPHE_PAS)
        largeur = self.graphe_largeur or self.graphe.winfo_width()
        capacite = max(1, (largeur - 2 * self.px(18)) // pas)
        if len(nouvelles) >= capacite or (nouvelles and not self.graphe_barres):
            self.redessiner_graphe(largeur)
        elif nouvelles:
            self.graphe.move("barre", -pas * len(nouvelles), 0)
            x = largeur - self.px(18) - len(nouvelles) * pas
            for _, _, rgb in nouvelles:
                self.graphe_barres.append(self._barre(x, rgb))
                x += pas
            while len(self.graphe_barres) > capacite:
                self.graphe.delete(self.graphe_barres.popleft())
            self.graphe_vu = nouvelles[-1][0]
        # La cadence tenue, a cote de celle qui est reglee -- deux fois par seconde.
        if time.time() - self.cadence_vue > 0.5:
            self.cadence_vue = time.time()
            reelle = cadence_reelle()
            reglee = entier(self.cfg.get("images_par_seconde", 8), 8)
            self.graphe.itemconfig(
                self.graphe_cadence,
                text=("%.0f im/s  \u00b7  reglee %d" % (reelle, reglee)) if reelle
                else "reglee %d im/s" % reglee)
            self.graphe.itemconfig(
                self.graphe_absent,
                text="" if reelle else ("en pause" if ETAT.get("pause") else
                                        "la guirlande ne recoit rien"))

    # ------------------------------------------------------------------
    #  La boule de Jarvis : une petite fenetre ronde, toujours devant, que
    #  les clics traversent. Elle ne vit que pendant qu'il est reveille --
    #  rien ne se dessine le reste du temps (voir animer() : derriere un
    #  jeu plein ecran, redessiner sans raison peut tuer Tk).

    # ------------------------------------------------------------------
    #  L'agenda : les rendez-vous des prochains jours, tenus dans
    #  BrainDebugger. Une fenetre a part, que Jarvis ouvre (« montre-moi mon
    #  agenda »), comme le menu de l'icone.

    # ------------------------------------------------------------------
    #  L'AGENDA. « Rends l'interface des rappels beaucoup plus belle, avec un
    #  mode frise ; inspire-toi de BrainDebugger ; des infos de quantified
    #  self : temps de sommeil, note, frise avec ce qui arrive ; des rappels
    #  pouvant durer plusieurs jours. »
    #
    #  En tete, quatre tuiles : la derniere nuit, les sept dernieres nuits, la
    #  note de la journee, ce qui arrive. Dessous, au choix : la LISTE, jour par
    #  jour, ou la FRISE -- la semaine ecoulee et les deux qui viennent sur un
    #  meme axe, les periodes etalees sur leurs jours, le sommeil et la note en
    #  bas. En pied, poser un rappel (un jour, ou du ... au ...).

    AGENDA_FOND_CARTE = "#1B2230"
    AGENDA_WEEKEND = "#1A1F2A"
    AGENDA_AUJOURDHUI = "#22304A"
    AGENDA_SOMMEIL = "#8FB8FF"

    def _arrondi(self, c, x0, y0, x1, y1, r, **kw):
        r = max(0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        pts = (x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0)
        return c.create_polygon(pts, smooth=True, **kw)

    def _champ_indice(self, parent, indice, largeur):
        """Un champ avec son indice en gris, qui s'efface quand on y entre."""
        e = self.tk.Entry(parent, bg=ENCRE, fg=BRUME, insertbackground=CRAIE, relief="flat", bd=6,
                          width=largeur, font=(self.f_ui, 10), highlightthickness=1,
                          highlightbackground=FIL, highlightcolor=self.accent)
        e.indice = indice
        e.insert(0, indice)

        def entrer(_):
            if e.get() == e.indice and e.cget("fg") == BRUME:
                e.delete(0, "end")
                e.configure(fg=CRAIE)

        def sortir(_):
            if not e.get():
                e.insert(0, e.indice)
                e.configure(fg=BRUME)
        e.bind("<FocusIn>", entrer)
        e.bind("<FocusOut>", sortir)
        return e

    def _valeur(self, e):
        return "" if e.cget("fg") == BRUME and e.get() == e.indice else e.get().strip()

    def _vider(self, e):
        e.delete(0, "end")
        e.insert(0, e.indice)
        e.configure(fg=BRUME)

    def ouvrir_agenda(self):
        tk = self.tk
        f = getattr(self, "fen_agenda", None)
        if f is not None and f.winfo_exists():
            f.deiconify()
            f.lift()
            f.focus_force()
            return self.remplir_agenda()
        f = tk.Toplevel(self.root, bg=NUIT)
        f.title("Agenda -- Machi Tool")
        f.geometry("%dx%d" % (self.px(820), self.px(680)))
        f.minsize(self.px(560), self.px(460))
        f.attributes("-topmost", True)
        f.after(1500, lambda: f.winfo_exists() and f.attributes("-topmost", False))
        self.fen_agenda = f
        self.__dict__.setdefault("agenda_mode", self.cfg.get("agenda_mode", "liste"))
        self.agenda_donnees = {"etat": "lecture", "rdv": [], "bilan": None,
                               "aujourdhui": time.strftime("%Y-%m-%d"), "message": ""}
        marge = self.px(20)

        tete = tk.Frame(f, bg=NUIT)
        tete.pack(fill="x", padx=marge, pady=(self.px(18), self.px(10)))
        titres = tk.Frame(tete, bg=NUIT)
        titres.pack(side="left")
        tk.Label(titres, text="Agenda", bg=NUIT, fg=CRAIE, font=(self.f_ui, 17, "bold")).pack(anchor="w")
        self.agenda_sous_titre = tk.Label(titres, text="", bg=NUIT, fg=BRUME, font=(self.f_ui, 9))
        self.agenda_sous_titre.pack(anchor="w")
        droite = tk.Frame(tete, bg=NUIT)
        droite.pack(side="right")
        self.bouton(droite, "↻", self.remplir_agenda, compact=True).pack(side="right", padx=(self.px(8), 0))
        bascule = tk.Frame(droite, bg=ENCRE, highlightthickness=1, highlightbackground=FIL)
        bascule.pack(side="right")
        self.agenda_boutons_mode = {}
        for cle, nom in (("liste", "Liste"), ("frise", "Frise")):
            b = tk.Label(bascule, text=nom, bg=ENCRE, fg=BRUME, font=(self.f_ui, 9, "bold"),
                         padx=self.px(14), pady=self.px(5), cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda _e, c=cle: self._agenda_mode(c))
            self.agenda_boutons_mode[cle] = b

        self.agenda_tuiles = tk.Canvas(f, bg=NUIT, highlightthickness=0, bd=0, height=self.px(118))
        self.agenda_tuiles.pack(fill="x", padx=marge)

        corps = tk.Frame(f, bg=NUIT)
        corps.pack(fill="both", expand=True, padx=marge, pady=(self.px(12), 0))
        barre = tk.Scrollbar(corps, orient="vertical")
        barre.pack(side="right", fill="y")
        c = tk.Canvas(corps, bg=NUIT, highlightthickness=0, bd=0, yscrollcommand=barre.set)
        c.pack(side="left", fill="both", expand=True)
        barre.config(command=c.yview)
        c.bind("<MouseWheel>", lambda e: c.yview_scroll(int(-e.delta / 120), "units"))
        c.bind("<Button-4>", lambda e: c.yview_scroll(-2, "units"))
        c.bind("<Button-5>", lambda e: c.yview_scroll(2, "units"))
        self.agenda_toile = c

        pied = tk.Frame(f, bg=VELOURS)
        pied.pack(fill="x", padx=marge, pady=(self.px(12), self.px(16)))
        ligne = tk.Frame(pied, bg=VELOURS)
        ligne.pack(fill="x", padx=self.px(12), pady=(self.px(10), self.px(4)))
        tk.Label(ligne, text="NOUVEAU RAPPEL", bg=VELOURS, fg=BRUME, font=(self.f_mono, 8)).pack(side="left")
        self.agenda_retour = tk.Label(ligne, text="", bg=VELOURS, fg=BRUME, font=(self.f_ui, 9))
        self.agenda_retour.pack(side="right")
        champs = tk.Frame(pied, bg=VELOURS)
        champs.pack(fill="x", padx=self.px(12), pady=(0, self.px(12)))
        self.agenda_titre = self._champ_indice(champs, "Dentiste, vacances, anniversaire...", 26)
        self.agenda_titre.pack(side="left", fill="x", expand=True)
        petit = lambda t: tk.Label(champs, text=t, bg=VELOURS, fg=BRUME, font=(self.f_ui, 9))
        petit("le").pack(side="left", padx=(self.px(8), self.px(4)))
        self.agenda_date = self._champ_indice(champs, "demain", 11)
        self.agenda_date.pack(side="left")
        petit("au").pack(side="left", padx=(self.px(6), self.px(4)))
        self.agenda_fin = self._champ_indice(champs, "(un seul jour)", 12)
        self.agenda_fin.pack(side="left")
        petit("a").pack(side="left", padx=(self.px(6), self.px(4)))
        self.agenda_heure = self._champ_indice(champs, "14h30", 6)
        self.agenda_heure.pack(side="left")
        self.bouton(champs, "Ajouter", self.ajouter_rappel, principal=True, compact=True).pack(
            side="left", padx=(self.px(10), 0))
        for e in (self.agenda_titre, self.agenda_date, self.agenda_fin, self.agenda_heure):
            e.bind("<Return>", lambda _e: self.ajouter_rappel())

        c.bind("<Configure>", lambda _e: self._agenda_redessiner_bientot())
        self.agenda_tuiles.bind("<Configure>", lambda _e: self._agenda_redessiner_bientot())
        self._agenda_mode(self.agenda_mode, relire=False)
        self.remplir_agenda()

    def _agenda_mode(self, mode, relire=False):
        self.agenda_mode = "frise" if mode == "frise" else "liste"
        self.cfg["agenda_mode"] = self.agenda_mode
        for cle, b in getattr(self, "agenda_boutons_mode", {}).items():
            actif = cle == self.agenda_mode
            b.configure(bg=self.accent if actif else ENCRE, fg=NUIT if actif else BRUME)
        self._agenda_redessiner_bientot()

    def _agenda_redessiner_bientot(self):
        if getattr(self, "_agenda_attente", None):
            return
        f = getattr(self, "fen_agenda", None)
        if f is None or not f.winfo_exists():
            return

        def faire():
            self._agenda_attente = None
            self._agenda_dessiner()
        self._agenda_attente = f.after(30, faire)

    def remplir_agenda(self):
        """Va chercher l'agenda et le bilan hors du fil de l'interface."""
        f = getattr(self, "fen_agenda", None)
        if f is None or not f.winfo_exists():
            return
        self.agenda_sous_titre.configure(text="Lecture...")
        cfg = self.cfg

        def chercher():
            aujourdhui = time.strftime("%Y-%m-%d")
            d = {"etat": "ok", "rdv": [], "bilan": None, "aujourdhui": aujourdhui, "message": ""}
            try:
                if not _cle_presente(cfg):
                    raise ValueError("Relie Machi Tool a BrainDebugger (Reglages > le pont) pour voir l'agenda.")
                r = lire_agenda(cfg, AGENDA_PASSE + AGENDA_JOURS, depuis=_jv.plus_jours(aujourdhui, -AGENDA_PASSE),
                                bilan=True)
                d["rdv"] = r.get("rendezVous") or []
                d["bilan"] = r.get("bilan")
            except urllib.error.HTTPError as e:
                d.update(etat="erreur", message="BrainDebugger a repondu %d%s." % (
                    e.code, " : mets-le a jour" if e.code == 404 else ""))
            except Exception as e:
                d.update(etat="erreur", message=str(e) if isinstance(e, ValueError) else "BrainDebugger injoignable.")
            if not d["bilan"]:
                d["bilan"] = bilan_local(aujourdhui)          # un BrainDebugger plus ancien : nos nuits a nous
            self.root.after(0, lambda: self._agenda_recu(d))
        threading.Thread(target=chercher, daemon=True).start()

    def _agenda_recu(self, d):
        self.agenda_donnees = d
        f = getattr(self, "fen_agenda", None)
        if f is None or not f.winfo_exists():
            return
        self._agenda_dessiner()

    # --- le dessin --------------------------------------------------------

    def _agenda_dessiner(self):
        f = getattr(self, "fen_agenda", None)
        if f is None or not f.winfo_exists():
            return
        d = self.agenda_donnees
        auj = d["aujourdhui"]
        jour = _jv._jour_iso(auj)
        long = "%s %d %s" % (_jv._JOURS_AG[jour.weekday()], jour.day, _jv._MOIS_AG[jour.month - 1])
        a_venir = [r for r in _jv.en_cours_ou_a_venir(d["rdv"], auj)
                   if str(r["date"]) <= _jv.plus_jours(auj, AGENDA_JOURS - 1)]
        self.agenda_sous_titre.configure(
            text=long[0].upper() + long[1:] + ("  ·  " + d["message"] if d["etat"] != "ok" else
                                               "  ·  %d a venir sur %d jours" % (len(a_venir), AGENDA_JOURS)))
        self._agenda_tuiles(d, a_venir)
        if self.agenda_mode == "frise":
            self._agenda_frise(d)
        else:
            self._agenda_liste(d, a_venir)

    def _agenda_tuiles(self, d, a_venir):
        c = self.agenda_tuiles
        c.delete("all")
        W, H = max(c.winfo_width(), self.px(400)), self.px(118)
        b = _jv.resume_bilan(d["bilan"], d["aujourdhui"])
        ecart = self.px(10)
        l = (W - 3 * ecart) / 4.0
        petit, moyen, gros = (self.f_mono, 8), (self.f_ui, 9), (self.f_ui, 20, "bold")
        p = self.px(12)
        for i in range(4):
            x0 = i * (l + ecart)
            self._arrondi(c, x0, 0, x0 + l, H, self.px(10), fill=VELOURS, outline="")
        # 1. la derniere nuit
        x = p
        c.create_text(x, p, text="DERNIERE NUIT", fill=BRUME, font=petit, anchor="nw")
        nuit = b["nuit"]
        c.create_text(x, p + self.px(16), text=_jv.duree_lisible(nuit and nuit["h"]), fill=CRAIE, font=gros,
                      anchor="nw")
        if nuit:
            bornes = "%s → %s" % (nuit.get("coucher") or "?", nuit.get("lever") or "?")
            c.create_text(x, p + self.px(52), text=bornes, fill=BRUME, font=moyen, anchor="nw")
            if b["mediane"]:
                diff = nuit["h"] - b["mediane"]
                sens = "▲" if diff > 0.25 else "▼" if diff < -0.25 else "●"
                c.create_text(x, p + self.px(72), anchor="nw", font=moyen, fill=self.AGENDA_SOMMEIL,
                              text="%s habitude %s" % (sens, _jv.duree_lisible(b["mediane"])))
        else:
            c.create_text(x, p + self.px(52), text="pas encore mesuree", fill=BRUME, font=moyen, anchor="nw")
        # 2. les sept nuits
        x0 = l + ecart
        c.create_text(x0 + p, p, text="SOMMEIL · %d NUITS" % AGENDA_PASSE, fill=BRUME, font=petit, anchor="nw")
        serie = b["serie"][-AGENDA_PASSE:]
        haut, bas = p + self.px(22), H - p - self.px(16)
        n = max(1, len(serie))
        pas = (l - 2 * p) / float(max(n, AGENDA_PASSE))
        plafond = max([12.0] + [h for _, h, _ in serie if h])
        for k, (dt, h, _) in enumerate(serie):
            cx = x0 + p + pas * k
            self._arrondi(c, cx + pas * 0.18, haut, cx + pas * 0.82, bas, self.px(3), fill=ENCRE, outline="")
            if h:
                y = bas - (bas - haut) * h / plafond
                self._arrondi(c, cx + pas * 0.18, y, cx + pas * 0.82, bas, self.px(3), outline="",
                              fill=self.AGENDA_SOMMEIL if dt == d["aujourdhui"] else "#5E7FB8")
            c.create_text(cx + pas / 2, bas + self.px(3), text=_jv._JOURS_AG[_jv._jour_iso(dt).weekday()][0].upper(),
                          fill=BRUME, font=(self.f_mono, 7), anchor="n")
        if b["mediane"]:
            y = bas - (bas - haut) * b["mediane"] / plafond
            c.create_line(x0 + p, y, x0 + l - p, y, fill=ETOILE, dash=(2, 3))
        # 3. la note
        x0 = 2 * (l + ecart)
        c.create_text(x0 + p, p, text="NOTE DE LA JOURNEE", fill=BRUME, font=petit, anchor="nw")
        note = b["note"]
        t = c.create_text(x0 + p, p + self.px(16), text=_jv.note_lisible(note and note["n"]), fill=CRAIE,
                          font=gros, anchor="nw")
        bx = c.bbox(t)
        c.create_text(bx[2] + self.px(3), bx[3] - self.px(6), text="/10", fill=BRUME, font=moyen, anchor="sw")
        if note:
            quand = {0: "aujourd'hui", -1: "hier"}.get(
                (_jv._jour_iso(note["date"]) - _jv._jour_iso(d["aujourdhui"])).days, _jv.jour_court(note["date"]))
            c.create_text(x0 + p, p + self.px(52), text=quand + (
                "  ·  moy. %s" % _jv.note_lisible(b["moy_note"]) if b["moy_note"] is not None else ""),
                fill=BRUME, font=moyen, anchor="nw")
        pts = [(k, n_) for k, (_, _, n_) in enumerate(serie) if n_ is not None]
        if pts:
            y0n, y1n = p + self.px(74), H - p
            xy = []
            for k, n_ in pts:
                xy += [x0 + p + pas * k + pas / 2, y1n - (y1n - y0n) * n_ / 10.0]
            if len(xy) >= 4:
                c.create_line(*xy, fill="#6A5A2A", width=self.px(2), smooth=True)
            for j in range(0, len(xy), 2):
                c.create_oval(xy[j] - self.px(3), xy[j + 1] - self.px(3), xy[j] + self.px(3), xy[j + 1] + self.px(3),
                              fill=ETOILE, outline="")
        # 4. ce qui arrive
        x0 = 3 * (l + ecart)
        c.create_text(x0 + p, p, text="A VENIR · %d JOURS" % AGENDA_JOURS, fill=BRUME, font=petit, anchor="nw")
        c.create_text(x0 + p, p + self.px(16), text=str(len(a_venir)), fill=CRAIE, font=gros, anchor="nw")
        prochain = _jv.prochain_rendez_vous(d["rdv"], d["aujourdhui"], time.strftime("%H:%M"))
        largeur = int(l - 2 * p)
        if prochain:
            c.create_text(x0 + p, p + self.px(52), text=prochain[0], fill=CRAIE, font=(self.f_ui, 10, "bold"),
                          anchor="nw", width=largeur)
            c.create_text(x0 + p, p + self.px(72), text=prochain[1], fill=VIF, font=moyen, anchor="nw",
                          width=largeur)
        else:
            c.create_text(x0 + p, p + self.px(52), text="rien de prevu", fill=BRUME, font=moyen, anchor="nw")

    def _agenda_liste(self, d, a_venir):
        c = self.agenda_toile
        c.delete("all")
        W = max(c.winfo_width(), self.px(400)) - self.px(4)
        auj = d["aujourdhui"]
        y = self.px(4)
        if d["etat"] != "ok" and not a_venir:
            c.create_text(W / 2, self.px(60), text=d["message"], fill=BRUME, font=(self.f_ui, 10), width=W - 40)
            c.configure(scrollregion=(0, 0, W, self.px(120)))
            return
        if not a_venir:
            c.create_text(W / 2, self.px(50), text="Rien a l'agenda pour les %d prochains jours." % AGENDA_JOURS,
                          fill=CRAIE, font=(self.f_ui, 11))
            c.create_text(W / 2, self.px(74), fill=BRUME, font=(self.f_ui, 9),
                          text="Pose un rappel ci-dessous, dans BrainDebugger (Annee > Reperes), ou demande a Jarvis.")
            c.configure(scrollregion=(0, 0, W, self.px(120)))
            return
        for titre, items in _jv.agenda_par_jour(a_venir, auj):
            aujourdhui = titre.startswith("Aujourd'hui")
            t = c.create_text(0, y, text=titre.replace(" -- ", "  \u00b7  "), fill=self.accent if aujourdhui else CRAIE,
                              font=(self.f_ui, 10, "bold"), anchor="nw")
            bx = c.bbox(t)
            c.create_line(bx[2] + self.px(10), (bx[1] + bx[3]) / 2, W, (bx[1] + bx[3]) / 2, fill=FIL)
            y = bx[3] + self.px(8)
            for heure, libelle, fin in items:
                r = next((x for x in a_venir if str(x["label"]) == libelle and str(x.get("heure") or "") == heure),
                         {"date": auj, "label": libelle})
                h = self.px(44)
                self._arrondi(c, 0, y, W, y + h, self.px(9), fill=self.AGENDA_FOND_CARTE, outline="")
                teinte = _jv.teinte_rendez_vous(libelle)
                c.create_oval(self.px(14), y + h / 2 - self.px(4), self.px(22), y + h / 2 + self.px(4),
                              fill=teinte, outline="")
                c.create_text(self.px(34), y + h / 2, text=heure or "journee", anchor="w",
                              fill=CRAIE if heure else BRUME, font=(self.f_mono, 9))
                c.create_text(self.px(104), y + h / 2, text=libelle, anchor="w", fill=CRAIE,
                              font=(self.f_ui, 11), width=W - self.px(104) - self.px(210))
                if r.get("fin"):
                    d0, d1 = _jv._jour_iso(r["date"]), _jv._jour_iso(r["fin"])
                    total = (d1 - d0).days + 1
                    fait = max(0, min(total, (_jv._jour_iso(auj) - d0).days))
                    c.create_text(W - self.px(14), y + h / 2 - self.px(1), anchor="e", fill=BRUME,
                                  font=(self.f_ui, 9), text="%d jours · jusqu'au %s" % (total, _jv.jour_court(r["fin"])))
                    # la periode : ou l'on en est
                    x0, x1 = self.px(104), W - self.px(14)
                    yb = y + h - self.px(6)
                    c.create_line(x0, yb, x1, yb, fill=FIL, width=self.px(3), capstyle="round")
                    if fait:
                        c.create_line(x0, yb, x0 + (x1 - x0) * fait / float(total), yb, fill=teinte,
                                      width=self.px(3), capstyle="round")
                else:
                    c.create_text(W - self.px(14), y + h / 2, anchor="e", fill=BRUME, font=(self.f_ui, 9),
                                  text=_jv.quand_lisible(r["date"], "", auj))
                y += h + self.px(6)
            y += self.px(10)
        c.configure(scrollregion=(0, 0, W, y))

    def _agenda_frise(self, d):
        c = self.agenda_toile
        c.delete("all")
        W = max(c.winfo_width(), self.px(400)) - self.px(4)
        auj = d["aujourdhui"]
        debut = _jv.plus_jours(auj, -AGENDA_PASSE)
        n = AGENDA_PASSE + AGENDA_JOURS
        gauche = self.px(70)
        col = (W - gauche) / float(n)
        police = (self.f_ui, 9)
        try:
            import tkinter.font as tkfont
            mesure = tkfont.Font(root=self.root, family=self.f_ui, size=9)
            largeur_px = mesure.measure
        except Exception:
            largeur_px = lambda t: len(t) * self.px(7)
        cols = lambda lib, h: 1 + int((self.px(14) + largeur_px((h + " " if h else "") + lib)) // max(1, col))
        voies = _jv.voies_frise(d["rdv"], debut, n, cols)
        nvoies = max(1, 1 + max([v[0] for v in voies] or [0]))
        entete, voie_h = self.px(40), self.px(28)
        y_rdv = entete + self.px(8)
        y_som = y_rdv + nvoies * voie_h + self.px(24)
        h_som = self.px(60)
        y_note = y_som + h_som + self.px(30)
        h_note = self.px(54)
        bas = y_note + h_note + self.px(10)
        # les colonnes : fin de semaine un peu plus sombre, aujourd'hui en clair
        for k in range(n):
            dt = _jv._jour_iso(_jv.plus_jours(debut, k))
            x = gauche + k * col
            if dt.isoformat() == auj:
                self._arrondi(c, x + 1, 0, x + col - 1, bas, self.px(6), fill=self.AGENDA_AUJOURDHUI, outline="")
            elif dt.weekday() >= 5:
                c.create_rectangle(x, entete - self.px(4), x + col, bas, fill=self.AGENDA_WEEKEND, outline="")
            passe = dt.isoformat() < auj
            c.create_text(x + col / 2, self.px(8), text=_jv._JOURS_AG[dt.weekday()][0].upper(),
                          fill=BRUME, font=(self.f_mono, 7))
            c.create_text(x + col / 2, self.px(24), text=str(dt.day),
                          fill=self.accent if dt.isoformat() == auj else (BRUME if passe else CRAIE),
                          font=(self.f_ui, 10, "bold" if dt.isoformat() == auj else "normal"))
            if dt.day == 1 or k == 0:
                c.create_text(x + self.px(2), entete - self.px(2), text=_jv._MOIS_COURTS[dt.month - 1].upper(),
                              fill=ETOILE, font=(self.f_mono, 7), anchor="w")
        # les etiquettes des rangees
        for y, nom in ((y_rdv, "RAPPELS"), (y_som, "SOMMEIL"), (y_note, "NOTE")):
            c.create_text(0, y + self.px(2), text=nom, fill=BRUME, font=(self.f_mono, 8), anchor="nw")
            c.create_line(gauche, y - self.px(8), W, y - self.px(8), fill=FIL)
        # les rappels
        for v, i0, i1, heure, libelle, date, fin in voies:
            teinte = _jv.teinte_rendez_vous(libelle)
            y0 = y_rdv + v * voie_h
            y1 = y0 + voie_h - self.px(6)
            passe = (fin or date) < auj
            texte = (heure + " " if heure else "") + libelle
            if i1 > i0:
                x0, x1 = gauche + i0 * col + 2, gauche + (i1 + 1) * col - 2
                self._arrondi(c, x0, y0, x1, y1, self.px(7), fill=FIL if passe else teinte, outline="")
                place = int((x1 - x0 - self.px(12)) / max(1, largeur_px("m") * 0.62))
                court = texte if len(texte) <= place else texte[:max(1, place - 1)] + "…"
                c.create_text(x0 + self.px(8), (y0 + y1) / 2, text=court, anchor="w",
                              fill=BRUME if passe else NUIT, font=(self.f_ui, 9, "bold"))
            else:
                cx = gauche + i0 * col + col / 2
                r = self.px(5)
                c.create_oval(cx - r, (y0 + y1) / 2 - r, cx + r, (y0 + y1) / 2 + r,
                              fill=FIL if passe else teinte, outline="")
                c.create_text(cx + r + self.px(5), (y0 + y1) / 2, text=texte, anchor="w",
                              fill=BRUME if passe else CRAIE, font=police)
        if not voies:
            c.create_text(gauche + self.px(8), y_rdv + voie_h / 2 - self.px(3), anchor="w", fill=BRUME,
                          font=police, text=d["message"] if d["etat"] != "ok" else "Rien sur ces trois semaines.")
        # le sommeil et la note, jour par jour
        b = _jv.resume_bilan(d["bilan"], auj)
        par_jour = {dt: (h, n_) for dt, h, n_ in b["serie"]}
        plafond = max([12.0] + [h for h, _ in par_jour.values() if h])
        base = y_som + h_som
        if b["mediane"]:
            ym = base - h_som * b["mediane"] / plafond
            c.create_line(gauche, ym, gauche + (AGENDA_PASSE + 1) * col, ym, fill=ETOILE, dash=(2, 3))
        points = []
        for k in range(AGENDA_PASSE + 1):
            dt = _jv.plus_jours(debut, k)
            h, n_ = par_jour.get(dt, (None, None))
            x = gauche + k * col
            if h:
                y = base - h_som * h / plafond
                self._arrondi(c, x + col * 0.22, y, x + col * 0.78, base, self.px(3), outline="",
                              fill=self.AGENDA_SOMMEIL if dt == auj else "#5E7FB8")
                c.create_text(x + col / 2, y - self.px(3), text=_jv.note_lisible(h), anchor="s", fill=BRUME,
                              font=(self.f_mono, 7))
            if n_ is not None:
                points.append((x + col / 2, y_note + h_note - h_note * n_ / 10.0, n_))
        if len(points) >= 2:
            xy = [v for p_ in points for v in p_[:2]]
            c.create_line(*xy, fill="#6A5A2A", width=self.px(2), smooth=True)
        for x, y, n_ in points:
            c.create_oval(x - self.px(4), y - self.px(4), x + self.px(4), y + self.px(4), fill=ETOILE, outline="")
            c.create_text(x, y - self.px(7), text=_jv.note_lisible(n_), anchor="s", fill=CRAIE,
                          font=(self.f_mono, 7))
        xa = gauche + (AGENDA_PASSE + 1) * col
        c.create_text(xa + self.px(10), y_som + h_som / 2, anchor="w", fill=BRUME, font=police,
                      text="le sommeil et la note se remplissent au fil des jours")
        c.configure(scrollregion=(0, 0, W, bas + self.px(8)))

    def ajouter_rappel(self):
        titre = self._valeur(self.agenda_titre)
        auj = time.strftime("%Y-%m-%d")
        date = _jv.date_saisie(self._valeur(self.agenda_date) or "", auj)
        texte_fin = self._valeur(self.agenda_fin)
        fin = _jv.date_saisie(texte_fin, auj) if texte_fin else None
        heure = _jv.heure_saisie(self._valeur(self.agenda_heure))
        dire = lambda t, c=ALERTE: self.agenda_retour.configure(text=t, fg=c)
        if not titre:
            return dire("Il faut un titre.")
        if date is None:
            return dire("Date illisible (ex. demain, lundi, 12/10).")
        if texte_fin and (fin is None or fin < date):
            return dire("Fin illisible, ou avant le debut.")
        if heure is None:
            return dire("Heure illisible (ex. 14h30).")
        if not _cle_presente(self.cfg):
            return dire("Relie d'abord Machi Tool a BrainDebugger.")
        dire("Envoi...", BRUME)
        cfg = self.cfg

        def envoyer():
            try:
                r = poser_agenda(cfg, titre, date, fin if fin and fin != date else None, heure or None)
                resultat = (True, r.get("texte") or "Ajoute.")
            except urllib.error.HTTPError as e:
                resultat = (False, _detail_http(e) or "BrainDebugger a repondu %d." % e.code)
            except Exception:
                resultat = (False, "BrainDebugger injoignable.")

            def fini():
                ok, texte = resultat
                if not self.agenda_retour.winfo_exists():
                    return
                dire(texte, VIF if ok else ALERTE)
                if ok:
                    for e in (self.agenda_titre, self.agenda_date, self.agenda_fin, self.agenda_heure):
                        self._vider(e)
                    self.remplir_agenda()
            self.root.after(0, fini)
        threading.Thread(target=envoyer, daemon=True).start()

    BOULE_TAILLE = 44
    BOULE_CLE = "#010203"            # la couleur rendue transparente

    # ------------------------------------------------------------------
    #  Le panneau de Jarvis : « le meme qu'ici » -- le contenu Jarvis du
    #  panneau LED, en haut au milieu de l'ecran, fixe, sans bordure, que les
    #  clics traversent. Il vit le temps que Jarvis est actif ; sa reponse y
    #  defile pendant qu'il parle.

    def _panneau_creer(self, taille, attribut="fen_led"):
        tk = self.tk
        f = tk.Toplevel(self.root)
        f.overrideredirect(True)
        f.configure(bg="#08090C")
        f.attributes("-topmost", True)
        lab = tk.Label(f, bg="#08090C", bd=0, highlightthickness=0)
        lab.pack()
        f.geometry("%dx%d+-10000+-10000" % (taille, taille))
        f.update_idletasks()
        if os.name == "nt":
            import ctypes
            u = ctypes.WinDLL("user32")
            h = int(f.wm_frame(), 16)
            u.SetWindowLongW(h, -20, u.GetWindowLongW(h, -20) | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000)
        f.withdraw()
        setattr(self, attribut, f)
        setattr(self, attribut + "_image", lab)

    def _panneau_tic(self):
        f = getattr(self, "fen_led", None)
        def cache():
            if f is not None and f.winfo_exists() and f.state() != "withdrawn":
                f.withdraw()
        if not self.cfg.get("jarvis_panneau", True) or not self.cfg.get("jarvis_actif"):
            cache()
            return 500
        maintenant = time.time()
        st = self.__dict__.setdefault("panneau_etat", {"prev": None, "fait": 0.0, "alpha": 0.0})
        etat = JARVIS.get("etat")
        if st["prev"] == "parle" and etat not in ("parle", "erreur"):
            st["fait"] = maintenant + 1.4                 # DONE, un instant
        st["prev"] = etat
        montre = etat in _jv.BOULE_ETATS or etat == "erreur"
        if not montre and maintenant < st["fait"]:
            montre, etat = True, "fait"
        if not montre and (f is None or not f.winfo_exists() or f.state() == "withdrawn"):
            st["alpha"] = 0.0
            return 300
        pas = max(3, min(8, int(round(4 * getattr(self, "echelle", 1.0)))))
        taille = pas * _jv.LED_N
        if f is None or not f.winfo_exists():
            self._panneau_creer(taille)
            f = self.fen_led
        st["alpha"] = min(1.0, st["alpha"] + 0.2) if montre else max(0.0, st["alpha"] - 0.15)
        if st["alpha"] <= 0.0:
            cache()
            return 300
        from PIL import Image, ImageTk
        # ce qu'il dit s'ecrit au fil de sa voix, DANS le panneau
        texte = sous_titre_courant(maintenant) if etat == "parle" else ""
        img = _jv.dalle_led(_jv.image_jarvis(etat, maintenant, "", JARVIS.get("mode", "jarvis"), texte), pas)
        photo = ImageTk.PhotoImage(Image.fromarray(img))
        self.fen_led_image.configure(image=photo)
        self.fen_led_image.image = photo
        x0, y0, l, _ = self._boule_zone()
        haut = y0 + max(8, int(12 * getattr(self, "echelle", 1.0)))
        f.geometry("%dx%d+%d+%d" % (taille, taille, x0 + (l - taille) // 2, haut))
        try:
            f.attributes("-alpha", 0.96 * st["alpha"])
        except Exception:
            pass
        if f.state() == "withdrawn":
            f.deiconify()
            f.attributes("-topmost", True)
        return 50

    def boule_tic(self):
        delai = 400
        try:
            delai = min(delai, self._panneau_tic())
        except Exception as e:
            if not getattr(self, "_panneau_erreur", False):
                print("Jarvis : panneau impossible (%s)" % e)
                self._panneau_erreur = True
        demande = JARVIS.get("montrer_agenda") or 0
        if demande > getattr(self, "_agenda_montre", 0):
            self._agenda_montre = demande
            try:
                self.ouvrir_agenda()
            except Exception as e:
                print("Agenda : fenetre impossible (%s)" % e)
        try:
            delai = min(delai, self._boule_tic())
        except Exception as e:
            if not getattr(self, "_boule_erreur", False):
                print("Jarvis : boule impossible (%s)" % e)
                self._boule_erreur = True
        self.root.after(max(20, delai), self.boule_tic)

    def _boule_creer(self, taille):
        tk = self.tk
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.configure(bg=self.BOULE_CLE)
        b.attributes("-topmost", True)
        try:
            b.attributes("-transparentcolor", self.BOULE_CLE)
        except Exception:
            pass
        toile = tk.Canvas(b, width=taille, height=taille, bg=self.BOULE_CLE, highlightthickness=0, bd=0)
        toile.pack()
        b.geometry("%dx%d+-10000+-10000" % (taille, taille))
        b.update_idletasks()
        if os.name == "nt":
            # les clics la traversent ; pas de bouton dans la barre des taches ;
            # elle ne prend jamais le focus
            import ctypes
            u = ctypes.WinDLL("user32")
            h = int(b.wm_frame(), 16)
            GWL_EXSTYLE = -20
            u.SetWindowLongW(h, GWL_EXSTYLE, u.GetWindowLongW(h, GWL_EXSTYLE)
                             | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000)
        b.withdraw()
        self.boule, self.boule_toile = b, toile

    def _boule_zone(self):
        """La zone de travail de l'ecran principal (sans la barre des taches)."""
        if os.name == "nt":
            try:
                import win32api
                x0, y0, x1, y1 = win32api.GetMonitorInfo(win32api.MonitorFromPoint((0, 0), 1))["Work"]
                return x0, y0, x1 - x0, y1 - y0
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _boule_tic(self):
        if not self.cfg.get("jarvis_boule", True) or not self.cfg.get("jarvis_actif"):
            if self.boule is not None and self.boule.winfo_exists() and self.boule.state() != "withdrawn":
                self.boule.withdraw()
            return 500
        taille = max(24, int(self.BOULE_TAILLE * getattr(self, "echelle", 1.0)))
        etat_boule = "attente" if self.cfg.get("jarvis_panneau", True) else JARVIS.get("etat")
        visible, x, y, couleur, rythme = _jv.cible_boule(
            etat_boule, JARVIS.get("mode"), JARVIS.get("regard"), self._boule_zone(), time.time(),
            self.cfg.get("jarvis_boule_x", 0.97), self.cfg.get("jarvis_boule_y", 0.90), taille)
        st = self.boule_etat
        if not visible and (self.boule is None or not self.boule.winfo_exists() or self.boule.state() == "withdrawn"):
            st["x"] = None
            return 300                                     # rien a l'ecran : rien a dessiner
        if self.boule is None or not self.boule.winfo_exists():
            self._boule_creer(taille)
        # elle glisse vers sa cible ; elle apparait et s'efface en douceur
        if st["x"] is None:
            st["x"], st["y"] = float(x), float(y)
        st["x"] += (x - st["x"]) * 0.25
        st["y"] += (y - st["y"]) * 0.25
        st["alpha"] = min(1.0, st["alpha"] + 0.15) if visible else max(0.0, st["alpha"] - 0.12)
        if st["alpha"] <= 0.0:
            self.boule.withdraw()
            st["x"] = None
            return 300
        st["phase"] += 0.08 * rythme
        try:
            self.boule.attributes("-alpha", 0.92 * st["alpha"])
        except Exception:
            pass
        c = self.boule_toile
        c.delete("all")
        r0 = taille / 2.0
        souffle = 0.5 + 0.5 * math.sin(st["phase"])
        for k, frac in ((3, 1.0), (2, 0.82), (1, 0.64)):
            r = r0 * (frac - 0.08 * (1 - souffle) * k / 3)
            c.create_oval(r0 - r, r0 - r, r0 + r, r0 + r, fill=melange(couleur, "#000000", 0.25 * k), outline="")
        r = r0 * (0.34 + 0.06 * souffle)
        c.create_oval(r0 - r, r0 - r, r0 + r, r0 + r, fill=melange(couleur, "#FFFFFF", 0.45), outline="")
        self.boule.geometry("%dx%d+%d+%d" % (taille, taille, int(st["x"]), int(st["y"])))
        if self.boule.state() == "withdrawn":
            self.boule.deiconify()
            self.boule.attributes("-topmost", True)
        return 40

    def animer(self):
        g = self.generation
        # RIEN NE SE DESSINE DERRIERE UN JEU.
        #
        # Rangee dans la barre des taches, la fenetre n'a pas besoin de son
        # animation. Ce n'est pas qu'une economie de processeur : Tk continuait
        # de redessiner ses toiles pendant qu'une application plein ecran
        # changeait la resolution de l'ecran, et demandait alors un pixmap de
        # taille invalide. CreateDIBSection repondait « parametre incorrect »,
        # et Tk_GetPixmap appelle Tcl_Panic -- qui tue l'application d'un coup,
        # sans qu'aucun try/except Python ne puisse l'attraper. On ne peut donc
        # pas rattraper cette panne : il faut ne pas la provoquer.
        if not self.interface_visible():
            return self.root.after(400, lambda: g == self.generation and self.animer())
        self.phase += 0.09
        self.avancer_graphe()
        self.scintiller()
        self.peindre_vumetre()
        self.root.after(50, lambda: g == self.generation and self.animer())

    # ------------------------------------------------------------------
    #  Rail de navigation : une icone par page, sur un semis d'etoiles
    # ------------------------------------------------------------------

    def construire_rail(self):
        tk = self.tk
        c = self.rail_toile = tk.Canvas(self.rail, bg=NUIT, highlightthickness=0,
                                        width=self.px(RAIL_LARGEUR))
        c.pack(fill="both", expand=True)
        self.etoiles = []
        cx, r = self.px(RAIL_LARGEUR) // 2, self.px(17)
        y, groupe_avant = self.px(26), "debut"
        self.onglets = {}
        for cle, nom, icone, groupe in MENU:
            if groupe_avant != "debut" and groupe != groupe_avant:
                y += self.px(12)          # un ecart entre deux groupes, rien de plus
            groupe_avant = groupe
            fond = c.create_oval(cx - r, y - r, cx + r, y + r, outline="", fill=NUIT)
            signe = c.create_text(cx, y, text=icone, fill=BRUME, font=(self.f_icone, 13))
            marque = c.create_text(cx + self.px(15), y - self.px(14), text="\u2726",
                                   fill=ETOILE, font=(self.f_icone, 7), state="hidden")
            for item in (fond, signe):
                c.tag_bind(item, "<Button-1>", lambda e, k=cle: self.aller(k))
                c.tag_bind(item, "<Enter>", lambda e, k=cle, n=nom: self.survol(k, n, True))
                c.tag_bind(item, "<Leave>", lambda e, k=cle, n=nom: self.survol(k, n, False))
            self.onglets[cle] = (fond, signe, marque, y)
            y += self.px(42)
        # Une mise a jour qui attend : un point vert sur l'icone des mises a jour.
        _, _, _, ym = self.onglets["maj"]
        self.badge_maj = c.create_oval(cx + self.px(8), ym - self.px(13), cx + self.px(14),
                                       ym - self.px(7), outline="", fill=VIF, state="hidden")
        c.tag_bind(self.badge_maj, "<Button-1>", lambda e: self.aller("maj"))
        self.bulle = tk.Label(self.root, text="", bg=VELOURS, fg=CRAIE, font=(self.f_ui, 9),
                              padx=self.px(8), pady=self.px(3))
        c.bind("<Configure>", lambda e: self.semer_etoiles(e.width, e.height))

    def semer_etoiles(self, largeur, hauteur):
        """De petites etoiles jaunes, toujours au meme endroit (graine fixe), plus
        rares pres des icones pour ne jamais les gener."""
        c = self.rail_toile
        c.delete("etoile")
        self.etoiles = []
        des = random.Random(7)
        cx = largeur / 2.0
        centres = [y_ for _, _, _, y_ in self.onglets.values()]
        for _ in range(max(16, int(hauteur / 11))):
            x = des.uniform(self.px(5), largeur - self.px(5))
            y = des.uniform(self.px(6), hauteur - self.px(6))
            # Jamais sur une icone : un peu d'air autour de chacune.
            if any(math.hypot(x - cx, y - yc) < self.px(22) for yc in centres):
                continue
            eclat_ = des.uniform(0.25, 0.9)
            if des.random() < 0.18:
                item = c.create_text(x, y, text="\u2726", font=(self.f_icone, des.choice((5, 6, 7))),
                                     fill=melange(hex_vers_rgb(ETOILE), NUIT_RGB, eclat_), tags=("etoile",))
            else:
                t = self.px(1) * des.choice((0.6, 1.0, 1.4))
                item = c.create_oval(x - t, y - t, x + t, y + t, outline="",
                                     fill=melange(hex_vers_rgb(ETOILE), NUIT_RGB, eclat_), tags=("etoile",))
            self.etoiles.append((item, eclat_))
        c.tag_lower("etoile")

    def scintiller(self):
        """Une etoile a la fois change d'eclat : le ciel vit sans rien distraire."""
        if not self.etoiles or int(self.phase * 10) % 3:
            return
        item, base = random.choice(self.etoiles)
        part = max(0.15, min(1.0, base + random.uniform(-0.35, 0.35)))
        try:
            self.rail_toile.itemconfig(item, fill=melange(hex_vers_rgb(ETOILE), NUIT_RGB, part))
        except Exception:
            pass

    def survol(self, cle, nom, dedans):
        c = self.rail_toile
        fond, signe, _, y = self.onglets[cle]
        if dedans:
            c.configure(cursor="hand2")
            if cle != self.section:
                c.itemconfig(fond, fill=VELOURS)
                c.itemconfig(signe, fill=CRAIE)
            # Le nom de la page, a cote de l'icone : l'icone suffit une fois
            # apprise, le nom est la pour la premiere fois.
            self.bulle.configure(text=nom)
            self.root.update_idletasks()
            haut = c.winfo_rooty() - self.root.winfo_rooty() + y - self.bulle.winfo_reqheight() // 2
            self.bulle.place(x=self.px(RAIL_LARGEUR) + self.px(6), y=haut)
            self.bulle.lift()
        else:
            c.configure(cursor="")
            self.bulle.place_forget()
            if cle != self.section:
                c.itemconfig(fond, fill=NUIT)
                c.itemconfig(signe, fill=BRUME)

    def aller(self, cle):
        self.section = cle
        c = self.rail_toile
        for k, (fond, signe, marque, _) in self.onglets.items():
            actif = k == cle
            c.itemconfig(fond, fill=VELOURS if actif else NUIT)
            c.itemconfig(signe, fill=self.accent if actif else BRUME)
            c.itemconfig(marque, state="normal" if actif else "hidden")
        for p in self.pages.values():
            p.pack_forget()
        # Le bandeau ne concerne que la lampe, et doit rester au-dessus.
        self.bandeau.pack_forget()
        if GROUPE_DE.get(cle) == "lampe":
            self.bandeau.pack(fill="x")
        self.pages[cle].pack(fill="both", expand=True)

    def nouvelle_page(self, cle, marge_x=24, marge_y=18, defilante=False):
        if not defilante:
            cadre = self.tk.Frame(self.zone, bg=NUIT, padx=marge_x, pady=marge_y)
            self.pages[cle] = cadre
            return cadre
        exterieur = self.tk.Frame(self.zone, bg=NUIT)
        self.pages[cle] = exterieur
        return self.zone_defilante(exterieur, marge_x, marge_y)

    def zone_defilante(self, parent, marge_x=24, marge_y=18):
        """Renvoie un cadre interieur qui defile si le contenu deborde.
        La molette est branchee a l'entree du pointeur et debranchee a sa
        sortie : un bind_all volerait la molette aux autres pages."""
        tk = self.tk
        toile = tk.Canvas(parent, bg=NUIT, highlightthickness=0)
        barre = tk.Scrollbar(parent, orient="vertical", command=toile.yview,
                             bg=VELOURS, troughcolor=NUIT, bd=0, relief="flat",
                             activebackground=FIL, width=10)
        interieur = tk.Frame(toile, bg=NUIT, padx=marge_x, pady=marge_y)
        fenetre = toile.create_window((0, 0), window=interieur, anchor="nw")
        interieur.bind("<Configure>",
                       lambda e: toile.configure(scrollregion=toile.bbox("all")))
        toile.bind("<Configure>", lambda e: toile.itemconfig(fenetre, width=e.width))
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")

        def rouler(evenement):
            if toile.bbox("all") and toile.bbox("all")[3] > toile.winfo_height():
                toile.yview_scroll(int(-evenement.delta / 120), "units")
        parent.bind("<Enter>", lambda e: toile.bind_all("<MouseWheel>", rouler))
        parent.bind("<Leave>", lambda e: toile.unbind_all("<MouseWheel>"))
        return interieur

    # ------------------------------------------------------------------
    #  Briques
    # ------------------------------------------------------------------

    def bouton(self, parent, texte, action, principal=False, compact=False):
        b = self.tk.Button(
            parent, text=texte, command=action, relief="flat", bd=0,
            bg=(self.accent if principal else ENCRE),
            fg=(NUIT if principal else CRAIE),
            activebackground=(self.accent if principal else FIL),
            activeforeground=(NUIT if principal else CRAIE),
            font=(self.f_ui, 9, "bold" if principal else "normal"),
            padx=(12 if compact else 18), pady=(6 if compact else 8),
            cursor="hand2", highlightthickness=1,
            highlightbackground=NUIT, highlightcolor=self.accent)
        if principal:
            self.bouton_principal = b
        return b

    def titre(self, parent, texte):
        return self.tk.Label(parent, text=texte.upper(), bg=parent["bg"], fg=BRUME,
                             font=(self.f_mono, 8), anchor="w")

    def texte(self, parent, txt, couleur=BRUME, taille=9, gras=False, largeur=520):
        # largeur est pensee en 96 ppp comme le reste : sans mise a l'echelle,
        # les paragraphes se replieraient beaucoup trop tot sur un 4K.
        lab = self.tk.Label(parent, text=txt, bg=parent["bg"], fg=couleur,
                            font=(self.f_ui, taille, "bold" if gras else "normal"),
                            anchor="w", justify="left", wraplength=self.px(largeur))
        # « UNE PASSE DE SIMPLICITE PARTOUT » : une longue explication ne montre
        # que sa premiere phrase ; « plus › » deplie le reste, « moins ‹ » le replie.
        court = aide_courte(txt) if couleur == BRUME and not gras else None
        if court:
            etat = {"long": False}

            def basculer(_=None):
                etat["long"] = not etat["long"]
                lab.configure(text=(txt + "   moins \u2039") if etat["long"] else court)
            lab.configure(text=court, cursor="hand2")
            lab.bind("<Button-1>", basculer)
        return lab

    def repli(self, parent, titre, ouvert=False):
        """Une section repliee : son titre, cliquable, et ce qu'elle contient
        (le cadre rendu), cache tant qu'on ne l'ouvre pas. Reste ouverte ou
        fermee d'une reconstruction a l'autre."""
        tk = self.tk
        memo = self.__dict__.setdefault("replis_ouverts", {})
        ouvert = memo.get(titre, ouvert)
        bloc = tk.Frame(parent, bg=parent["bg"])
        bloc.pack(fill="x", pady=(self.px(10), 0))
        tete = tk.Label(bloc, bg=parent["bg"], fg=BRUME, font=(self.f_mono, 8), anchor="w", cursor="hand2")
        tete.pack(fill="x")
        tk.Frame(bloc, bg=FIL, height=1).pack(fill="x", pady=(self.px(4), 0))
        corps = tk.Frame(bloc, bg=parent["bg"])

        def montrer(o):
            memo[titre] = o
            tete.configure(text=("\u25be  " if o else "\u25b8  ") + titre.upper())
            if o:
                corps.pack(fill="x", pady=(self.px(6), 0))
            else:
                corps.pack_forget()
        tete.bind("<Button-1>", lambda _e: montrer(not memo.get(titre, False)))
        montrer(ouvert)
        return corps

    def champ(self, parent, valeur, largeur=18):
        e = self.tk.Entry(parent, bg=ENCRE, fg=CRAIE, insertbackground=CRAIE,
                          relief="flat", bd=6, width=largeur, font=(self.f_ui, 9),
                          highlightthickness=1, highlightbackground=ENCRE,
                          highlightcolor=self.accent)
        e.insert(0, valeur)
        return e

    def case(self, parent, texte, variable, action=None):
        return self.tk.Checkbutton(
            parent, text="  " + texte, variable=variable, command=action,
            bg=parent["bg"], fg=CRAIE, selectcolor=ENCRE, activebackground=parent["bg"],
            activeforeground=CRAIE, relief="flat", bd=0, font=(self.f_ui, 9),
            anchor="w", highlightthickness=0, wraplength=self.px(470),
            justify="left")

    def radio(self, parent, texte, variable, valeur):
        return self.tk.Radiobutton(
            parent, text="  " + texte, variable=variable, value=valeur,
            bg=parent["bg"], fg=CRAIE, selectcolor=ENCRE, activebackground=parent["bg"],
            activeforeground=CRAIE, relief="flat", bd=0, font=(self.f_ui, 9),
            anchor="w", highlightthickness=0)

    def reglette(self, parent, cle, libelle, mini, maxi, pas, aide, entier=False):
        """Curseur dessine a la main : tk.Scale peint sa poignee avec la
        couleur de fond du widget, donc elle disparait sur un theme sombre."""
        tk = self.tk
        bloc = tk.Frame(parent, bg=NUIT)
        bloc.pack(fill="x", pady=(0, 7))
        haut = tk.Frame(bloc, bg=NUIT)
        haut.pack(fill="x")
        self.texte(haut, libelle, CRAIE, 9, True).pack(side="left")
        val = tk.Label(haut, bg=NUIT, fg=BRUME, font=(self.f_mono, 9))
        val.pack(side="right")
        self.texte(bloc, aide, BRUME, 8, largeur=460).pack(fill="x", pady=(0, 2))

        v = tk.DoubleVar(value=float(self.cfg.get(cle, mini)))
        toile = tk.Canvas(bloc, height=self.px(22), bg=NUIT, highlightthickness=0,
                          cursor="hand2", takefocus=1)
        toile.pack(fill="x")
        marge, y = self.px(11), self.px(11)
        epais = self.px(6)
        rail = toile.create_line(0, y, 0, y, fill=ENCRE, width=epais, capstyle="round")
        plein = toile.create_line(0, y, 0, y, fill=self.accent, width=epais,
                                  capstyle="round")
        poignee = toile.create_oval(0, 0, 0, 0, fill=CRAIE, outline="")

        def peindre(*_):
            largeur = max(self.px(60), toile.winfo_width())
            part = (v.get() - mini) / float(maxi - mini)
            x = marge + part * (largeur - 2 * marge)
            r = self.px(7)
            toile.coords(rail, marge, y, largeur - marge, y)
            toile.coords(plein, marge, y, max(marge, x), y)
            toile.coords(poignee, x - r, y - r, x + r, y + r)
            toile.itemconfig(plein, fill=self.accent)
            val.configure(text=f"{int(v.get())}" if entier else f"{v.get():.2f}")

        def poser(evenement):
            largeur = max(self.px(60), toile.winfo_width())
            part = (evenement.x - marge) / float(largeur - 2 * marge)
            brut = mini + max(0.0, min(1.0, part)) * (maxi - mini)
            v.set(round(brut / pas) * pas)

        def flecher(evenement):
            delta = pas if evenement.keysym in ("Right", "Up") else -pas
            v.set(max(mini, min(maxi, round((v.get() + delta) / pas) * pas)))

        v.trace_add("write", peindre)
        toile.bind("<Configure>", peindre)
        toile.bind("<Button-1>", lambda e: (toile.focus_set(), poser(e)))
        toile.bind("<B1-Motion>", poser)
        toile.bind("<Key>", flecher)
        toile.bind("<FocusIn>", lambda e: toile.itemconfig(poignee, outline=self.accent,
                                                          width=self.px(3)))
        toile.bind("<FocusOut>", lambda e: toile.itemconfig(poignee, outline=""))
        self.reglettes.append(peindre)
        peindre()
        return v

    def jauge(self, parent, libelle):
        """Barre horizontale 0..1 avec sa valeur chiffree. Renvoie de quoi
        la repeindre : la valeur seule ne dit pas si elle bouge parce que
        le son la pilote ou parce qu'on l'a fixee, d'ou la mention a
        droite."""
        tk = self.tk
        bloc = tk.Frame(parent, bg=NUIT)
        bloc.pack(fill="x", pady=(0, 9))
        haut = tk.Frame(bloc, bg=NUIT)
        haut.pack(fill="x")
        self.texte(haut, libelle, CRAIE, 9, True).pack(side="left")
        val = tk.Label(haut, text="", bg=NUIT, fg=BRUME, font=(self.f_mono, 9))
        val.pack(side="right")
        source = tk.Label(haut, text="", bg=NUIT, fg=BRUME, font=(self.f_ui, 8))
        source.pack(side="right", padx=(0, 10))

        toile = tk.Canvas(bloc, height=self.px(14), bg=NUIT, highlightthickness=0)
        toile.pack(fill="x", pady=(3, 0))
        rail = toile.create_rectangle(0, 0, 0, 0, outline="", fill=ENCRE)
        plein = toile.create_rectangle(0, 0, 0, 0, outline="", fill=self.accent)
        return {"toile": toile, "rail": rail, "plein": plein,
                "val": val, "source": source}

    def poser_jauge(self, j, valeur, pilotee, source="le son"):
        """source nomme ce qui pilote : la meme jauge sert au son et a
        l'ecran, elle ne peut pas supposer l'un ou l'autre."""
        largeur = max(self.px(20), j["toile"].winfo_width())
        valeur = max(0.0, min(1.0, float(valeur)))
        haut, bas = self.px(4), self.px(12)
        j["toile"].coords(j["rail"], 0, haut, largeur, bas)
        j["toile"].coords(j["plein"], 0, haut, largeur * valeur, bas)
        j["toile"].itemconfig(j["plein"], fill=self.accent if pilotee else FIL)
        j["val"].configure(text="%3d %%" % round(valeur * 100))
        j["source"].configure(text=("pilotee par " + source) if pilotee else "fixe",
                              fg=CRAIE if pilotee else BRUME)

    def separateur(self, parent, haut=14, bas=14):
        self.tk.Frame(parent, bg=FIL, height=1).pack(fill="x", pady=(haut, bas))

    # ------------------------------------------------------------------
    #  Bandeau du module Lampe
    #
    #  Ce que fait la guirlande a l'instant present interesse autant qu'on
    #  regle l'ecran, le son ou l'appairage. Le laisser dans la seule page
    #  Etat obligeait a y revenir pour verifier l'effet d'un reglage. Il
    #  coiffe donc toutes les pages du module.
    # ------------------------------------------------------------------

    def construire_bandeau(self):
        tk = self.tk
        self.bandeau = tk.Frame(self.zone, bg=NUIT, padx=self.px(24),
                                pady=self.px(14))

        carte = tk.Frame(self.bandeau, bg=VELOURS, padx=self.px(16),
                         pady=self.px(13))
        carte.pack(fill="x")

        haut = tk.Frame(carte, bg=VELOURS)
        haut.pack(fill="x")
        self.titre(haut, "source de la couleur").pack(side="left")
        self.txt_mode = tk.Label(haut, text="", bg=ENCRE, fg=CRAIE,
                                 font=(self.f_mono, 8),
                                 padx=self.px(8), pady=self.px(2))
        self.txt_mode.pack(side="right")

        ligne = tk.Frame(carte, bg=VELOURS)
        ligne.pack(fill="x", pady=(self.px(4), 0))
        self.txt_regle = tk.Label(ligne, text="", bg=VELOURS, fg=CRAIE,
                                  font=(self.f_titre, 17), anchor="w")
        self.txt_regle.pack(side="left")
        self.apercu_couleur(ligne, 40, VELOURS).pack(side="right")

        self.txt_contexte = tk.Label(carte, text="", bg=VELOURS, fg=BRUME,
                                     font=(self.f_mono, 8), anchor="w")
        self.txt_contexte.pack(fill="x", pady=(self.px(4), 0))

        # Reconnecter ne concerne que la guirlande : il n'avait rien a
        # faire dans le pied, ou il suivait jusqu'aux pages du site.
        self.bouton(self.bandeau, "Reconnecter", self.reconnecter,
                    compact=True).pack(anchor="w", pady=(self.px(8), 0))

    # ------------------------------------------------------------------
    #  Page Accueil
    #
    #  L'entree du toolkit : une tuile par module. Il n'y en a qu'une pour
    #  l'instant, mais la grille est deja faite pour en aligner d'autres,
    #  et une tuile fantome montre ou elles se poseront.
    # ------------------------------------------------------------------

    def page_accueil(self):
        tk = self.tk
        f = self.nouvelle_page("accueil", marge_x=30, marge_y=26)

        self.texte(f, NOM_APP.upper(), CRAIE, 9).pack(fill="x")
        tk.Label(f, text="Mes outils", bg=NUIT, fg=CRAIE,
                 font=(self.f_titre, 24), anchor="w").pack(fill="x", pady=(2, 2))
        self.texte(f, "De quoi veux-tu t'occuper ?", BRUME, 9).pack(fill="x")

        grille = tk.Frame(f, bg=NUIT)
        grille.pack(fill="both", expand=True, pady=(22, 0))
        grille.grid_columnconfigure(0, weight=1, uniform="tuile")
        grille.grid_columnconfigure(1, weight=1, uniform="tuile")

        self.tuile_lumiere(grille).grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        self.tuile_a_venir(grille).grid(row=0, column=1, sticky="nsew", padx=(9, 0))

        self.texte(f, "Version %s — %s" % (VERSION, DOSSIER), BRUME, 8).pack(
            fill="x", side="bottom", pady=(18, 0))

    def tuile_lumiere(self, parent):
        """Le gros bouton du module Lumiere. L'ampoule est dessinee plutot
        qu'importee : pas de fichier image a embarquer, et elle peut
        s'allumer a la couleur reelle de la guirlande."""
        tk = self.tk
        carte = tk.Frame(parent, bg=VELOURS, cursor="hand2",
                         highlightthickness=1, highlightbackground=VELOURS)

        dedans = tk.Frame(carte, bg=VELOURS, padx=22, pady=24)
        dedans.pack(fill="both", expand=True)

        self._fond_ampoule = VELOURS
        self.ampoule = tk.Canvas(dedans, width=self.px(96), height=self.px(112),
                                 bg=VELOURS, highlightthickness=0)
        self.ampoule.pack()
        self._dessiner_ampoule()

        titre = tk.Label(dedans, text="Lumiere", bg=VELOURS, fg=CRAIE,
                         font=(self.f_titre, 18))
        titre.pack(pady=(14, 4))
        detail = tk.Label(
            dedans, text="Guirlande ambiante\nLa couleur suit l'ecran, le son\n"
                         "ou l'application active",
            bg=VELOURS, fg=BRUME, font=(self.f_ui, 9), justify="center")
        detail.pack()
        self.etat_tuile = tk.Label(dedans, text="", bg=VELOURS, fg=BRUME,
                                   font=(self.f_mono, 8))
        self.etat_tuile.pack(pady=(12, 0))

        cibles = [carte, dedans, self.ampoule, titre, detail, self.etat_tuile]
        for w in cibles:
            w.bind("<Button-1>", lambda e: self.aller("etat"))
            w.bind("<Enter>", lambda e: self._survol_tuile(carte, cibles, True))
            w.bind("<Leave>", lambda e: self._survol_tuile(carte, cibles, False))
        return carte

    def _survol_tuile(self, carte, cibles, dedans):
        fond = ENCRE if dedans else VELOURS
        carte.configure(bg=fond,
                        highlightbackground=self.accent if dedans else VELOURS)
        for w in cibles[1:]:
            try:
                w.configure(bg=fond)
            except Exception:
                pass
        self._fond_ampoule = fond
        self._dessiner_ampoule(fond)

    def _dessiner_ampoule(self, fond=VELOURS):
        """Verre, culot, halo. Le halo prend la couleur courante de la
        guirlande quand elle est connectee, gris quand elle ne l'est pas."""
        c = self.ampoule
        c.delete("all")
        c.configure(bg=fond)
        vif = ETAT["connecte"] and max(ETAT["couleur"]) > 8
        teinte = vu_a_l_oeil(ETAT["couleur"]) if vif else hex_vers_rgb(self.accent)
        sourd = SOURD
        corps = teinte if vif else sourd
        arriere = hex_vers_rgb(fond)

        e = self.px          # tout le dessin est pense en 96 ppp
        cx, cy = e(48), e(46)

        for rayon, part in ((44, 0.10), (36, 0.16), (29, 0.26)):
            r = e(rayon)
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline="", fill=melange(corps, arriere, part))
        r = e(23)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="",
                      fill=melange(corps, arriere, 0.85 if vif else 0.45))
        # filament
        c.create_line(e(40), e(50), e(44), e(40), cx, e(50), e(52), e(40),
                      e(56), e(50),
                      fill=melange((255, 255, 255), corps, 0.55 if vif else 0.2),
                      width=e(2), smooth=True)
        # culot
        c.create_rectangle(e(39), e(68), e(57), e(74), outline="",
                           fill=melange(corps, arriere, 0.35))
        for y in (78, 84, 90):
            c.create_line(e(39), e(y), e(57), e(y),
                          fill=melange((178, 188, 206), arriere, 0.5), width=e(3))
        c.create_arc(e(39), e(92), e(57), e(102), start=180, extent=180,
                     outline="", fill=melange((178, 188, 206), arriere, 0.4))

    def tuile_a_venir(self, parent):
        """Place tenue pour le prochain outil. Une grille a une seule tuile
        se lit comme une page ratee ; avec ce fantome elle se lit comme une
        collection qui commence."""
        tk = self.tk
        carte = tk.Frame(parent, bg=NUIT, highlightthickness=1,
                         highlightbackground=FIL)
        dedans = tk.Frame(carte, bg=NUIT, padx=22, pady=24)
        dedans.pack(fill="both", expand=True)
        tk.Frame(dedans, bg=NUIT, height=34).pack()
        tk.Label(dedans, text="+", bg=NUIT, fg=FIL,
                 font=(self.f_titre, 40)).pack()
        tk.Label(dedans, text="Prochain outil", bg=NUIT, fg=BRUME,
                 font=(self.f_ui, 11)).pack(pady=(14, 4))
        tk.Label(dedans, text="La place est prete", bg=NUIT, fg=FIL,
                 font=(self.f_ui, 9)).pack()
        return carte

    # ------------------------------------------------------------------
    #  Page Etat
    # ------------------------------------------------------------------

    def page_etat(self):
        tk = self.tk
        f = self.nouvelle_page("etat")

        info = tk.Frame(f, bg=NUIT)
        info.pack(fill="x")
        self.titre(info, "guirlande").pack(fill="x")
        self.txt_adresse = tk.Label(info, text="", bg=NUIT, fg=CRAIE,
                                    font=(self.f_mono, 10), anchor="w")
        self.txt_adresse.pack(fill="x", pady=(3, 0))
        self.txt_detail = self.texte(info, "", BRUME, 8)
        self.txt_detail.pack(fill="x", pady=(3, 0))

        self.separateur(f)

        self.var_pause = tk.IntVar(value=0)
        self.case(f, "Mettre en pause — fige la couleur actuelle",
                  self.var_pause, self.basculer_pause).pack(fill="x")
        self.var_demarrage = tk.IntVar(value=1 if os.path.exists(chemin_demarrage()) else 0)
        self.case(f, "Lancer au demarrage de Windows",
                  self.var_demarrage, self.basculer_demarrage).pack(fill="x", pady=(4, 0))

        # ------- Couleur manuelle : forcer une teinte, par-dessus tout -------
        self.separateur(f)
        self.titre(f, "couleur manuelle").pack(fill="x", pady=(0, 4))
        self.texte(f, "Impose une couleur fixe, par-dessus l'ecran, le son et les "
                      "regles. Elle tient jusqu'a ce que tu reviennes a l'automatique.",
                   BRUME, 8, largeur=490).pack(fill="x", pady=(0, 8))
        rang = tk.Frame(f, bg=NUIT)
        rang.pack(fill="x")
        self.boite_manuelle = tk.Frame(rang, bg=self.cfg.get("couleur_manuelle", "#B79CF5"),
                                       width=self.px(26), height=self.px(26), cursor="hand2")
        self.boite_manuelle.pack(side="left")
        self.boite_manuelle.pack_propagate(False)
        self.boite_manuelle.bind("<Button-1>", lambda e: self.poser_couleur_manuelle())
        self.bouton(rang, "Choisir et forcer", self.poser_couleur_manuelle,
                    compact=True).pack(side="left", padx=8)
        self.bouton(rang, "Revenir a l'automatique", self.relacher_manuel,
                    compact=True).pack(side="left")
        self.txt_manuel = self.texte(f, "", BRUME, 8)
        self.txt_manuel.pack(fill="x", pady=(6, 0))

        self.texte(f, f"Version {VERSION} — {DOSSIER}", BRUME, 8).pack(
            fill="x", side="bottom", pady=(12, 0))

    def poser_couleur_manuelle(self):
        from tkinter import colorchooser
        depart = self.cfg.get("couleur_manuelle", "#B79CF5")
        res = colorchooser.askcolor(color=depart, parent=self.root,
                                    title="Couleur de la guirlande")
        if not (res and res[1]):
            return
        hexa = res[1].upper()
        self.cfg["couleur_manuelle"] = hexa
        sauver_config(self.cfg)
        self.boite_manuelle.configure(bg=hexa)
        ETAT["forcage"] = {"couleur": hex_vers_rgb(hexa), "nom": "Couleur manuelle",
                           "manuel": True, "expire": time.time() + 3650 * 86400}
        ETAT["message"] = "Couleur manuelle " + hexa

    def relacher_manuel(self):
        f = ETAT.get("forcage")
        # Ne relache que le forcage MANUEL : une couleur posee par le site garde
        # sa propre expiration.
        if f and f.get("manuel"):
            ETAT["forcage"] = None
        ETAT["message"] = "Retour a l'automatique"

    # ------------------------------------------------------------------
    #  Page Regles
    # ------------------------------------------------------------------

    def page_regles(self):
        tk = self.tk
        f = self.nouvelle_page("regles", marge_x=0, marge_y=0)

        haut = tk.Frame(f, bg=NUIT, padx=24, pady=16)
        haut.pack(fill="x")
        self.titre(haut, "premiere correspondance gagnante").pack(fill="x")
        self.texte(haut, "Les mots sont cherches dans le nom du programme et dans le "
                         "titre de la fenetre. Le titre d'un navigateur contient le nom "
                         "du site : \"netflix\" suffit. Garde les sites au-dessus des "
                         "navigateurs, la fleche les fait remonter.",
                   BRUME, 8, largeur=490).pack(fill="x", pady=(5, 0))

        bas = tk.Frame(f, bg=NUIT, padx=24, pady=12)
        bas.pack(fill="x", side="bottom")
        self.bouton(bas, "Ajouter une regle", self.nouvelle_regle, compact=True).pack(side="left")
        self.bouton(bas, "Detecter la fenetre active", self.detecter,
                    compact=True).pack(side="left", padx=8)

        conteneur = tk.Frame(f, bg=NUIT)
        conteneur.pack(fill="both", expand=True, padx=(24, 8))
        toile = tk.Canvas(conteneur, bg=NUIT, highlightthickness=0)
        barre = tk.Scrollbar(conteneur, orient="vertical", command=toile.yview,
                             bg=VELOURS, troughcolor=NUIT, bd=0, relief="flat",
                             activebackground=FIL, width=10)
        self.liste = tk.Frame(toile, bg=NUIT)
        self.liste.bind("<Configure>",
                        lambda e: toile.configure(scrollregion=toile.bbox("all")))
        self.fenetre_liste = toile.create_window((0, 0), window=self.liste, anchor="nw")
        toile.bind("<Configure>",
                   lambda e: toile.itemconfig(self.fenetre_liste, width=e.width))
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        def rouler(evenement):
            toile.yview_scroll(int(-evenement.delta / 120), "units")
        conteneur.bind("<Enter>", lambda e: toile.bind_all("<MouseWheel>", rouler))
        conteneur.bind("<Leave>", lambda e: toile.unbind_all("<MouseWheel>"))

        self.reconstruire(self.cfg.get("regles", []))

    def regles_courantes(self):
        return [{"nom": l["nom"].get().strip() or "?",
                 "couleur": l["couleur"]["v"],
                 "mots": [m.strip().lower() for m in l["mots"].get().split(",") if m.strip()]}
                for l in self.lignes]

    def reconstruire(self, regles):
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        self.lignes = []
        for r in regles:
            self.ajouter_ligne(r)

    def nouvelle_regle(self):
        self.ajouter_ligne({"nom": "Nouveau", "couleur": "#FFFFFF", "mots": []})

    def ajouter_ligne(self, regle):
        tk = self.tk
        rang = tk.Frame(self.liste, bg=VELOURS, padx=8, pady=7)
        rang.pack(fill="x", pady=2)

        def monter():
            regles = self.regles_courantes()
            i = self.lignes.index(ligne)
            if i > 0:
                regles[i - 1], regles[i] = regles[i], regles[i - 1]
                self.reconstruire(regles)
        tk.Label(rang, text="\u2191", bg=VELOURS, fg=BRUME, font=(self.f_ui, 9),
                 cursor="hand2", padx=6).pack(side="left")
        rang.winfo_children()[-1].bind("<Button-1>", lambda e: monter())

        couleur = {"v": regle.get("couleur", "#FFFFFF")}
        boite = tk.Frame(rang, bg=couleur["v"], width=self.px(22),
                         height=self.px(22), cursor="hand2")
        boite.pack(side="left", padx=(0, 10))
        boite.pack_propagate(False)

        def choisir(*_):
            from tkinter import colorchooser
            res = colorchooser.askcolor(color=couleur["v"], parent=self.root)
            if res and res[1]:
                couleur["v"] = res[1].upper()
                boite.configure(bg=couleur["v"])
        boite.bind("<Button-1>", choisir)

        nom = self.champ(rang, regle.get("nom", ""), 11)
        nom.pack(side="left")

        mots = self.champ(rang, ", ".join(regle.get("mots", [])), 24)
        mots.pack(side="left", fill="x", expand=True, padx=(8, 0))

        ligne = {"nom": nom, "couleur": couleur, "mots": mots}

        def supprimer():
            rang.destroy()
            if ligne in self.lignes:
                self.lignes.remove(ligne)
        tk.Button(rang, text="\u00d7", command=supprimer, relief="flat", bd=0, width=2,
                  bg=VELOURS, fg=BRUME, activebackground=FIL, activeforeground=ALERTE,
                  font=(self.f_ui, 11), cursor="hand2").pack(side="left", padx=(8, 0))

        self.lignes.append(ligne)

    def detecter(self):
        self.root.withdraw()
        def relever():
            ctx = fenetre_active()
            proc, _, titre = ctx.partition("|")
            self.root.deiconify()
            self.root.lift()
            indice = titre.strip()[:28] or proc.strip()
            if indice:
                self.ajouter_ligne({"nom": indice[:14].title(),
                                    "couleur": "#FFFFFF", "mots": [indice]})
                self.aller("regles")
        g = self.generation
        self.root.after(4000, lambda: g == self.generation and relever())

    # ------------------------------------------------------------------
    #  Page Ecran
    # ------------------------------------------------------------------

    def page_ecran(self):
        tk = self.tk
        # l'essentiel en haut (le mode, l'ecran, deux reglettes) ; l'etalonnage replie
        page = self.nouvelle_page("ecran", defilante=True)
        f = page
        self.titre(f, "mode").pack(fill="x", pady=(0, 4))
        self.var_mode = tk.StringVar(value=self.cfg.get("mode", "applications"))
        self.radio(f, "Regles — couleur fixe par programme ou site",
                   self.var_mode, "applications").pack(fill="x")
        self.radio(f, "Ecran — couleur dominante de l'ecran, en direct",
                   self.var_mode, "ecran").pack(fill="x")
        self.radio(f, "Mixte — moitie regle, moitie ecran",
                   self.var_mode, "mixte").pack(fill="x")
        self.txt_etat_ecran = self.texte(f, "", BRUME, 8, largeur=490)
        self.txt_etat_ecran.pack(fill="x", pady=(4, 0))
        self.bouton(f, "Modifier les regles par application",
                    lambda: self.aller("regles"),
                    compact=True).pack(anchor="w", pady=(8, 0))

        self.separateur(f, 14, 10)
        rang_apercu = tk.Frame(f, bg=NUIT)
        rang_apercu.pack(fill="x")
        gauche = tk.Frame(rang_apercu, bg=NUIT)
        gauche.pack(side="left", fill="x", expand=True)
        self.titre(gauche, "couleur envoyee").pack(fill="x")
        self.txt_apercu_ecran = tk.Label(gauche, text="", bg=NUIT, fg=CRAIE,
                                         font=(self.f_mono, 11), anchor="w")
        self.txt_apercu_ecran.pack(fill="x", pady=(4, 0))
        self.apercu_couleur(rang_apercu, 58, NUIT).pack(side="right")

        self.separateur(f, 14, 10)
        self.titre(f, "quel ecran").pack(fill="x", pady=(0, 4))
        self.var_source = tk.StringVar(value=str(self.cfg.get("ecran_source", "actif")))
        self.radio(f, "Celui de la fenetre active — suit ton attention",
                   self.var_source, "actif").pack(fill="x")
        n = nombre_ecrans()
        ETAT["ecrans"] = n
        for i in range(1, max(1, n) + 1):
            self.radio(f, f"Toujours l'ecran {i}", self.var_source, str(i)).pack(fill="x")

        self.separateur(f, 14, 10)
        self.var_sat = self.reglette(f, "ecran_saturation", "Saturation", 1.0, 2.5, 0.1,
                                     "1.0 = couleur brute, souvent fade. 1.5 a 2.0 "
                                     "donne des couleurs franches.")
        self.var_douceur_ecran = self.reglette(f, "douceur_ecran", "Reactivite",
                                               0.05, 1.0, 0.05,
                                               "Haut = colle a l'image. Bas = fondu doux.")

        f = self.repli(page, "ce que la luminosite de l'ecran fait bouger")
        self.var_cible_ecran = tk.StringVar(
            value=self.cfg.get("ecran_cible", "luminosite"))
        for cle, libelle in (
                ("luminosite", "La luminosite — scene sombre, guirlande sombre"),
                ("saturation", "La saturation — eclat constant, couleur qui palit "
                               "sur les scenes sombres"),
                ("les_deux",   "Les deux"),
                ("rien",       "Rien — la guirlande garde la luminosite de base")):
            self.radio(f, libelle, self.var_cible_ecran, cle).pack(fill="x")
        self.var_finesse = self.reglette(
            f, "ecran_finesse", "Finesse de la capture", 2, 16, 1,
            "Colonnes de la vignette lue sur l'ecran ; 4 suffit pour une couleur dominante.",
            entier=True)

        f = self.repli(page, "etalonnage de l'ecran")
        self.texte(f, "Un ecran ne descend jamais au noir absolu ni ne monte au "
                      "blanc pur. Ces trois reglages disent ce qui compte comme "
                      "noir, ce qui compte comme blanc, et comment se repartit "
                      "ce qu'il y a entre les deux.", BRUME, 8,
                   largeur=490).pack(fill="x", pady=(0, 10))
        self.var_ecran_noir = self.reglette(
            f, "ecran_noir", "Niveau de noir", 0.0, 0.6, 0.02,
            "En dessous, l'ecran est considere comme eteint.")
        self.var_ecran_blanc = self.reglette(
            f, "ecran_blanc", "Niveau de blanc", 0.2, 1.0, 0.02,
            "Au dessus, l'ecran est considere comme a fond. Baisse-le si tes "
            "scenes claires n'allument jamais la guirlande a pleine puissance.")
        self.var_ecran_gamma = self.reglette(
            f, "ecran_gamma", "Courbe", 0.1, 0.9, 0.05,
            "0.50 = reponse lineaire. En dessous, les scenes sombres sont "
            "relevees. Au dessus, seules les scenes vraiment claires sortent.")
        self.var_ecran_plancher = self.reglette(
            f, "ecran_luminance_min", "Plancher de sortie", 0.0, 0.6, 0.05,
            "Luminosite minimale envoyee : la guirlande ne s'eteint jamais "
            "completement.")
        self.var_ecran_base = self.reglette(
            f, "ecran_luminosite_base", "Luminosite de base", 0.05, 1.0, 0.05,
            "Luminosite tenue quand l'ecran ne pilote pas l'eclat — quand "
            "seule la saturation le suit, ou quand il ne pilote rien.")

        f = self.repli(page, "balance des blancs")
        self.texte(f, "Le soir, un filtre de lumiere bleue comme f.lux jaunit "
                      "l'ecran sans que la capture le voie : la guirlande resterait "
                      "blanche devant un ecran ambre. On relit alors la teinte "
                      "reelle de l'affichage pour qu'elle suive. (Night Light de "
                      "Windows passe par un autre chemin et n'est pas suivi ; regle "
                      "la balance a la main si besoin.)", BRUME, 8,
                   largeur=490).pack(fill="x", pady=(0, 8))
        self.var_filtre_bleu = tk.IntVar(
            value=1 if self.cfg.get("ecran_suit_filtre_bleu", True) else 0)
        self.case(f, "Suivre les filtres de lumiere bleue de l'ecran",
                  self.var_filtre_bleu).pack(fill="x")
        # L'indicateur : ce que Machi Tool DETECTE, et de combien il adapte. De
        # quoi voir tout de suite si f.lux est trouve et suivi, sans deviner.
        # Blinde : un pepin ici ne doit JAMAIS empecher la page (donc l'app) de
        # se construire -- au pire, pas d'indicateur.
        self.txt_filtre = None
        try:
            self.txt_filtre = self.texte(f, "Detection du filtre en cours...",
                                         BRUME, 8, largeur=490)
            self.txt_filtre.pack(fill="x", pady=(4, 0))
        except Exception as e:
            print("Indicateur de filtre indisponible :", e)
        self.var_balance_temp = self.reglette(
            f, "ecran_balance_temp", "Temperature", -1.0, 1.0, 0.05,
            "Reglage manuel par-dessus : negatif refroidit (bleu), positif "
            "rechauffe (ambre). 0 = neutre.")
        self.var_balance_tint = self.reglette(
            f, "ecran_balance_tint", "Teinte", -1.0, 1.0, 0.05,
            "Negatif vire au vert, positif au magenta. 0 = neutre.")
        self.var_led_kelvin = self.reglette(
            f, "led_blanc_kelvin", "Blanc de la guirlande (K)", 4000, 9500, 250,
            "Le blanc de tes LED elles-memes. La plupart tirent au bleu (7000-8500) : "
            "a couleur egale elles paraissent plus froides que l'ecran, et on corrige. "
            "6500 = neutre. Monte si la guirlande reste trop bleue le soir.", entier=True)
        self.var_filtre_force = self.reglette(
            f, "ecran_filtre_force", "Force de la compensation", 0.5, 2.5, 0.05,
            "De combien on pousse le rechauffement quand un filtre agit. 1 = tel que "
            "l'ecran ; 1,3 met en general la guirlande d'accord avec lui ; plus, "
            "pour une guirlande vue de cote.")

        f = self.repli(page, "effet de l'ecran en direct")
        self.jauge_ecran_entree = self.jauge(f, "Luminosite lue sur l'ecran")
        self.jauge_ecran_lum = self.jauge(f, "Luminosite envoyee")
        self.jauge_ecran_sat = self.jauge(f, "Saturation envoyee")
        self.texte(f, "Barre en couleur : l'ecran la pilote. Barre sourde : "
                      "elle est tenue.", BRUME, 8, largeur=490).pack(fill="x")

    # ------------------------------------------------------------------
    #  Page Son
    # ------------------------------------------------------------------

    def page_son(self):
        tk = self.tk
        page = self.nouvelle_page("son", defilante=True)
        f = page

        self.radio(f, "Son \u2014 la musique pilote la guirlande",
                   self.var_mode, "son").pack(fill="x")
        self.txt_audio = self.texte(f, "", BRUME, 8)
        self.txt_audio.pack(fill="x", pady=(4, 0))
        self.texte(f, "Ecoute la sortie des haut-parleurs, pas le micro.", BRUME, 8,
                   largeur=500).pack(fill="x", pady=(4, 0))

        self.separateur(f, 12, 8)
        self.titre(f, "niveaux en direct").pack(fill="x", pady=(0, 5))
        self.vumetre = tk.Canvas(f, height=self.px(66), bg=ENCRE, highlightthickness=0)
        self.vumetre.pack(fill="x")
        self.barres = []
        for i in range(3):
            fond = self.vumetre.create_rectangle(0, 0, 0, 0, outline="", fill=NUIT)
            barre = self.vumetre.create_rectangle(0, 0, 0, 0, outline="", fill=self.accent)
            nom = self.vumetre.create_text(0, 0, text="", fill=BRUME,
                                           font=(self.f_mono, 8), anchor="w")
            self.barres.append((fond, barre, nom))
        self.curseur_centroide = self.vumetre.create_line(0, 0, 0, 0, fill=CRAIE, width=2)

        self.separateur(f, 12, 8)
        self.titre(f, "ce qui fait reagir la luminosite").pack(fill="x", pady=(0, 4))
        self.var_bande = tk.StringVar(value=self.cfg.get("son_bande", "graves"))
        for cle, libelle in (("graves",  "Graves \u2014 30 a 250 Hz, la grosse caisse et la basse"),
                             ("mediums", "Mediums \u2014 250 Hz a 2 kHz, voix et guitares"),
                             ("aigus",   "Aigus \u2014 2 a 16 kHz, cymbales et souffle"),
                             ("tout",    "Tout le spectre \u2014 suit le volume general")):
            self.radio(f, libelle, self.var_bande, cle).pack(fill="x")

        self.separateur(f, 12, 8)
        self.titre(f, "d'ou vient la couleur").pack(fill="x", pady=(0, 4))
        self.var_palette = tk.StringVar(value=self.cfg.get("son_palette", "chaud_froid"))
        for cle, libelle in (
                ("chaud_froid", "Chaud vers froid \u2014 morceau sourd rouge, morceau brillant cyan"),
                ("arc",         "Arc-en-ciel \u2014 toute la roue des teintes"),
                ("regle",       "Couleur de la regle \u2014 le son ne fait que la luminosite")):
            self.radio(f, libelle, self.var_palette, cle).pack(fill="x")

        self.separateur(f, 12, 6)
        self.var_sens = self.reglette(f, "son_sensibilite", "Sensibilite", 0.3, 3.0, 0.1,
                                      "Plus haut : la guirlande reagit a des sons plus faibles.")

        f = self.repli(page, "ce que le son fait bouger")
        self.var_cible = tk.StringVar(value=self.cfg.get("son_cible", "luminosite"))
        for cle, libelle in (
                ("luminosite", "La luminosite \u2014 couleur franche en permanence, "
                               "seul l'eclat suit la musique"),
                ("saturation", "La saturation \u2014 eclat constant, la couleur palit "
                               "dans les passages calmes"),
                ("les_deux",   "Les deux \u2014 la guirlande s'eteint et se delave "
                               "ensemble")):
            self.radio(f, libelle, self.var_cible, cle).pack(fill="x")

        self.var_sat_fixe = self.reglette(
            f, "son_saturation_fixe", "Saturation", 0.0, 1.0, 0.02,
            "Valeur tenue quand le son ne pilote pas la saturation. Quand il "
            "la pilote, elle sert de plafond. 0 = blanc, 1 = couleur pure.")
        self.var_lum_fixe = self.reglette(
            f, "son_luminosite_fixe", "Luminosite", 0.05, 1.0, 0.05,
            "Valeur tenue quand le son ne pilote pas la luminosite.")

        f = self.repli(page, "effet du son en direct")
        self.jauge_lum = self.jauge(f, "Luminosite envoyee")
        self.jauge_sat = self.jauge(f, "Saturation envoyee")
        self.texte(f, "Barre en couleur : le son la pilote. Barre sourde : "
                      "elle est tenue a sa valeur fixe.", BRUME, 8,
                   largeur=500).pack(fill="x")

        f = self.repli(page, "rythme")
        self.texte(f, "Pour coller au rythme, monte aussi les images par seconde (15-20) dans Reglages.",
                   BRUME, 8, largeur=500).pack(fill="x")
        self.var_attaque = self.reglette(f, "son_attaque", "Attaque", 0.1, 1.0, 0.05,
                                         "Vitesse de montee. Eleve = coup sec sur le beat.")
        self.var_chute = self.reglette(f, "son_chute", "Chute", 0.02, 0.6, 0.02,
                                       "Vitesse de descente. Bas = trainee douce.")
        self.var_plancher = self.reglette(f, "son_plancher", "Plancher", 0.0, 0.4, 0.02,
                                          "Luminosite gardee dans les silences.")

    def peindre_vumetre(self):
        if not hasattr(self, "vumetre"):
            return
        largeur = max(60, self.vumetre.winfo_width())
        hauteur = 66
        marge, ecart = 10, 8
        colonne = (largeur - 2 * marge - 2 * ecart) / 3
        for i, (cle, _, _) in enumerate(BANDES):
            fond, barre, nom = self.barres[i]
            x = marge + i * (colonne + ecart)
            self.vumetre.coords(fond, x, 10, x + colonne, hauteur - 18)
            niveau = AUDIO.get(cle, 0.0)
            haut = (hauteur - 28) * (1 - niveau)
            self.vumetre.coords(barre, x, 10 + haut, x + colonne, hauteur - 18)
            self.vumetre.itemconfig(barre, fill=self.accent)
            self.vumetre.coords(nom, x, hauteur - 9)
            self.vumetre.itemconfig(nom, text=f"{cle} {niveau:4.2f}")
        x = marge + AUDIO.get("centroide", 0.5) * (largeur - 2 * marge)
        self.vumetre.coords(self.curseur_centroide, x, 4, x, hauteur - 20)


    # ------------------------------------------------------------------
    #  Page Jarvis
    # ------------------------------------------------------------------

    def page_jarvis(self):
        # « UNE PASSE DE SIMPLICITE » : en haut ce qui sert tous les jours -- l'ecouter,
        # ta voix, ses mains ; le reste est replie, une section a la fois.
        tk = self.tk
        page = self.nouvelle_page("jarvis", defilante=True)
        f = page
        self.var_jarvis = tk.IntVar(value=1 if self.cfg.get("jarvis_actif") else 0)
        self.case(f, "Ecouter « Jarvis » — le micro reste ouvert, sur ce PC",
                  self.var_jarvis, self.basculer_jarvis).pack(fill="x")
        self.txt_jarvis = self.texte(f, "", CRAIE, 10, True)
        self.txt_jarvis.pack(fill="x", pady=(6, 0))
        self.txt_jarvis_detail = self.texte(f, "", BRUME, 8, largeur=500)
        self.txt_jarvis_detail.pack(fill="x", pady=(2, 0))
        self.texte(f, "Dis « Jarvis », puis ta demande -- ou a la fin : « baisse le son, Jarvis ». Avant son nom, "
                      "rien ne sort du micro : un petit modele compare chaque instant a ton « Jarvis », sans "
                      "transcrire. Apres, la phrase est transcrite sur ce PC (le moteur de la dictee, telecharge "
                      "une fois, 456 Mo) ; le son n'est jamais enregistre. Clic droit sur l'icone › « Jarvis "
                      "ecoute » pour couper en un geste.", BRUME, 8, largeur=500).pack(fill="x", pady=(8, 0))

        self.separateur(f, 12, 8)
        self.titre(f, "ta voix").pack(fill="x", pady=(0, 4))
        self.texte(f, "Dis « Jarvis » huit fois quand la guirlande s'allume : l'ecran te guide (normal, en "
                      "question, fort, bas). Une facon ne passe pas ? « Ajouter une facon ». S'il te rate de peu "
                      "puis t'entend juste apres, il garde seul la facon ratee. On garde des nombres, pas le son.",
                   BRUME, 8, largeur=500).pack(fill="x")
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(6, 0))
        self.bouton(ligne, "Apprendre ma voix", self.apprendre_jarvis, compact=True).pack(side="left")
        self.bouton(ligne, "Ajouter une facon", self.ajouter_facon_jarvis,
                    compact=True).pack(side="left", padx=(8, 0))
        self.bouton(ligne, "Oublier ma voix", self.oublier_jarvis, compact=True).pack(side="left", padx=(8, 0))
        self.txt_jarvis_appris = self.texte(f, "", CRAIE, 9, largeur=500)
        self.txt_jarvis_appris.pack(fill="x", pady=(6, 4))
        self.var_jarvis_sens = self.reglette(
            f, "jarvis_sensibilite", "Sensibilite", 0.0, 1.0, 0.05,
            "Il ne t'entend pas : monte. Il se reveille tout seul : descends.")

        self.separateur(f, 12, 8)
        self.titre(f, "ses mains sur le pc").pack(fill="x", pady=(0, 4))
        self.texte(f, "Musique, Spotify, applis et jeux, fenetres, son, luminosite, onglets, notes, dossiers et "
                      "fichiers. Il ne supprime, ne deplace ni ne modifie jamais un fichier existant, et ne peut "
                      "ni eteindre, ni redemarrer, ni mettre en veille le PC, ni fermer ta session. Il agit sans "
                      "code : quiconque l'appelle dans la piece peut lui demander tes dossiers (le code d'acces, "
                      "plus bas, l'evite). Noms de dossiers et captures partent le temps de la reponse, sans "
                      "etre gardes.", BRUME, 8, largeur=500).pack(fill="x")
        self.var_jarvis_pc = tk.IntVar(value=1 if self.cfg.get("jarvis_pc") else 0)
        self.case(f, "Il peut agir sur le PC",
                  self.var_jarvis_pc, lambda: self.regler_mains("jarvis_pc", self.var_jarvis_pc)).pack(fill="x")
        self.var_jarvis_ecran = tk.IntVar(value=1 if self.cfg.get("jarvis_ecran") else 0)
        self.case(f, "Il peut regarder tes ecrans",
                  self.var_jarvis_ecran, lambda: self.regler_mains("jarvis_ecran", self.var_jarvis_ecran)).pack(fill="x")
        self.var_jarvis_historique = tk.IntVar(value=1 if self.cfg.get("jarvis_historique") else 0)
        self.case(f, "Il peut chercher dans l'historique du navigateur (lu sur le PC, seules les pages trouvees partent)",
                  self.var_jarvis_historique,
                  lambda: self.regler_mains("jarvis_historique", self.var_jarvis_historique)).pack(fill="x")
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(8, 0))
        self.bouton(ligne, "Ouvrir l'agenda", self.ouvrir_agenda, compact=True).pack(side="left")
        self.texte(ligne, "« mets-moi dentiste jeudi a 14 h », « qu'est-ce que j'ai demain ? »", BRUME, 8,
                   largeur=380).pack(side="left", padx=(10, 0))

        f = self.repli(page, "le micro")
        self.texte(f, "Celui qu'il ecoute ; le niveau s'affiche en haut (« micro -40 dB ») et doit monter quand "
                      "tu parles.", BRUME, 8, largeur=500).pack(fill="x")
        self.var_jarvis_micro = tk.StringVar(value=str(self.cfg.get("jarvis_micro", "") or ""))
        self.boite_micros = tk.Frame(f, bg=NUIT)
        self.boite_micros.pack(fill="x")
        self.remplir_micros()
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(6, 0))
        self.bouton(ligne, "Actualiser la liste", self.remplir_micros, compact=True).pack(side="left")
        self.var_jarvis_micro.trace_add("write", lambda *_: self.choisir_micro())

        f = self.repli(page, "sa langue et sa voix")
        self.texte(f, "Il comprend le francais et l'anglais ; il repond dans la langue choisie. Ses voix sont "
                      "calculees sur ce PC (Kokoro, 340 Mo une fois) ; le mode psychologue parle francais.",
                   BRUME, 8, largeur=500).pack(fill="x")
        self.var_jarvis_langue = tk.StringVar(value=langue_jarvis(self.cfg))
        self.radio(f, "English", self.var_jarvis_langue, "en").pack(fill="x")
        self.radio(f, "Francais", self.var_jarvis_langue, "fr").pack(fill="x")
        self.var_jarvis_langue.trace_add("write", lambda *_: self.choisir_langue())
        self.titre(f, "voix anglaise").pack(fill="x", pady=(8, 2))
        self.var_voix_kokoro = tk.StringVar(value=voix_kokoro_choisie(self.cfg))
        for cle, entree in _jv.VOIX_KOKORO.items():
            self.radio(f, entree["nom"], self.var_voix_kokoro, cle).pack(fill="x")
        self.var_voix_kokoro.trace_add("write", lambda *_: self.choisir_voix_kokoro())
        self.txt_kokoro = self.texte(f, "", BRUME, 8, largeur=500)
        self.txt_kokoro.pack(fill="x", pady=(4, 0))
        self.titre(f, "voix francaise").pack(fill="x", pady=(8, 2))
        v_fr = voix_fr_choisie(self.cfg)
        self.var_voix_modele = tk.StringVar(value=v_fr if v_fr != "piper" else voix_choisie(self.cfg))
        for cle, entree in _jv.VOIX_KOKORO_FR.items():
            self.radio(f, entree["nom"], self.var_voix_modele, cle).pack(fill="x")
        for cle, entree in _jv.VOIX_PIPER.items():
            self.radio(f, "Piper : " + entree["nom"], self.var_voix_modele, cle).pack(fill="x")
        self.radio(f, "Voix de Windows", self.var_voix_modele, "windows").pack(fill="x")
        self.var_voix_modele.trace_add("write", lambda *_: self.choisir_voix())
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(6, 0))
        self.bouton(ligne, "Ecouter un essai", self.essai_voix, compact=True).pack(side="left")
        self.txt_piper = self.texte(ligne, "", BRUME, 8, largeur=380)
        self.txt_piper.pack(side="left", padx=(10, 0))
        self.var_jarvis_lenteur = self.reglette(
            f, "jarvis_lenteur", "Debit", 0.8, 1.4, 0.02, "Plus haut = plus pose.")

        f = self.repli(page, "code d'acces")
        self.var_jarvis_code_actif = tk.IntVar(value=1 if self.cfg.get("jarvis_code_actif") else 0)
        self.case(f, "Le demander a voix haute avant les dossiers, les fichiers et l'ecran",
                  self.var_jarvis_code_actif,
                  lambda: self.regler_mains("jarvis_code_actif", self.var_jarvis_code_actif)).pack(fill="x")
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(6, 0))
        self.texte(ligne, "Code", CRAIE, 9).pack(side="left")
        self.champ_code = self.champ(ligne, "", 14)
        self.champ_code.configure(show="•")
        self.champ_code.pack(side="left", padx=(8, 0))
        self.bouton(ligne, "Enregistrer le code", self.enregistrer_code, compact=True).pack(side="left", padx=(8, 0))
        self.bouton(ligne, "Retirer", self.retirer_code, compact=True).pack(side="left", padx=(8, 0))
        self.txt_code = self.texte(f, "", BRUME, 8, largeur=500)
        self.txt_code.pack(fill="x", pady=(4, 0))
        self.afficher_code()

        f = self.repli(page, "spotify")
        self.texte(f, "Pour qu'il lance le titre, l'album ou la playlist exact (Spotify Premium). Une fois : sur "
                      "developer.spotify.com/dashboard, « Create app », Redirect URI http://127.0.0.1:%d/callback, "
                      "coche « Web API » ; copie le Client ID ici, puis « Connecter ». Sans Spotify, il passe par "
                      "YouTube." % _jv.SPOTIFY_PORT, BRUME, 8, largeur=500).pack(fill="x")
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(6, 0))
        self.texte(ligne, "Client ID", CRAIE, 9).pack(side="left")
        self.champ_spotify = self.champ(ligne, self.cfg.get("spotify_client_id", ""), 34)
        self.champ_spotify.pack(side="left", padx=(8, 0))
        self.bouton(ligne, "Connecter", self.connecter_spotify, compact=True).pack(side="left", padx=(8, 0))
        self.bouton(ligne, "Deconnecter", self.deconnecter_spotify, compact=True).pack(side="left", padx=(8, 0))
        self.bouton(ligne, "Tester", self.tester_spotify, compact=True).pack(side="left", padx=(8, 0))
        self.txt_spotify = self.texte(f, "", BRUME, 8, largeur=500)
        self.txt_spotify.pack(fill="x", pady=(4, 0))

        f = self.repli(page, "les onglets de chrome")
        self.texte(f, "Pour lister, ouvrir, fermer et couper des onglets. Une extension a installer une fois : "
                      "« Preparer l'extension », puis dans la page des extensions : « Mode developpeur » et "
                      "« Charger l'extension non empaquetee » sur ce dossier (aussi Edge et Brave). Seuls les "
                      "titres et les sites des onglets partent vers Jarvis.", BRUME, 8, largeur=500).pack(fill="x")
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(6, 0))
        self.bouton(ligne, "Preparer l'extension", self.preparer_extension, compact=True).pack(side="left")
        self.txt_onglets = self.texte(ligne, "", BRUME, 8, largeur=360)
        self.txt_onglets.pack(side="left", padx=(10, 0))

        f = self.repli(page, "ce qu'il retient")
        self.texte(f, "« Jarvis, retiens que... », « oublie que... » : ces phrases restent sur le PC et partent "
                      "avec chaque question. Rien de ton journal n'y entre.", BRUME, 8, largeur=500).pack(fill="x")
        self.boite_preferences = tk.Frame(f, bg=NUIT)
        self.boite_preferences.pack(fill="x", pady=(4, 0))
        self.remplir_preferences()
        self.texte(f, "Vos conversations : une phrase par conversation (jamais le psychologue, rien d'intime) ; "
                      "les %d dernieres partent avec chaque question." % SOUVENIRS_ENVOYES,
                   BRUME, 8, largeur=500).pack(fill="x", pady=(8, 0))
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(4, 0))
        self.bouton(ligne, "Oublier les conversations", self.oublier_souvenirs, compact=True).pack(side="left")
        self.txt_souvenirs = self.texte(ligne, "", BRUME, 8, largeur=360)
        self.txt_souvenirs.pack(side="left", padx=(10, 0))
        self.texte(f, "Ses routines de lumiere : des habitudes et des running gags qu'il pose lui-meme.",
                   BRUME, 8, largeur=500).pack(fill="x", pady=(8, 0))
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(4, 0))
        self.bouton(ligne, "Effacer ses routines", self.oublier_routines, compact=True).pack(side="left")
        self.txt_routines = self.texte(ligne, "", BRUME, 8, largeur=360)
        self.txt_routines.pack(side="left", padx=(10, 0))

        f = self.repli(page, "options")
        self.vars_jarvis = {}
        for cle, libelle in (
                ("jarvis_voix", "Repondre a voix haute (sinon : une notification)"),
                ("jarvis_son", "Un petit son quand il s'allume"),
                ("jarvis_leds", "La guirlande montre ou il en est (ecoute, reflechit, parle, fait)"),
                ("jarvis_suite", "Il ecoute encore apres sa reponse, sans qu'on redise « Jarvis »"),
                ("jarvis_couper", "Lui couper la parole en parlant par-dessus"),
                ("jarvis_hey", "Reconnaitre aussi « Hey Jarvis » (modele anglais)"),
                ("jarvis_tolerant", "Tres tolerant : un « Jarvis » pas net est verifie en le transcrivant"),
                ("jarvis_auto_etalonnage", "S'etalonner seul sur les appels rates de peu"),
                ("jarvis_panneau", "Son panneau en haut de l'ecran quand il est actif"),
                ("jarvis_boule", "Une petite boule sur l'ecran qu'il regarde")):
            v = tk.IntVar(value=1 if self.cfg.get(cle, True) else 0)
            self.vars_jarvis[cle] = v
            self.case(f, libelle, v, lambda c=cle: self.regler_jarvis(c)).pack(fill="x")
        ligne = tk.Frame(f, bg=NUIT)
        ligne.pack(fill="x", pady=(8, 0))
        self.texte(ligne, "Il t'appelle", CRAIE, 9).pack(side="left")
        self.champ_appellation = self.champ(ligne, self.cfg.get("jarvis_appellation", ""), 16)
        self.champ_appellation.pack(side="left", padx=(8, 0))
        self.texte(ligne, "vide = ni Monsieur ni Madame", BRUME, 8, largeur=260).pack(side="left", padx=(8, 0))

        f = self.repli(page, "ce qu'on peut lui dire")
        self.texte(f, "Deux modes : JARVIS (orange), le majordome du PC ; PSYCHOLOGUE (bleu), le compagnon de "
                      "BrainDebugger, avec ton journal -- « psychologue », ou il y passe seul s'il comprend que "
                      "tu veux parler. Pour revenir : « Jarvis ? Re ! », ou le rappeler. Un message grave part "
                      "toujours au compagnon. « Non rien », « oublie », « degage » : fin de la conversation.",
                   BRUME, 8, largeur=500).pack(fill="x")
        self.texte(f, "Sans passer par Internet : « allume / eteins la lumiere », « mets la lumiere en bleu », "
                      "« mode ecran / son / applications », « minuteur de 10 minutes », « rappelle-moi dans 20 "
                      "minutes de... », « quelle heure est-il », « ouvre BrainDebugger », « stop », « arrete "
                      "d'ecouter », « apprends ma voix ». Tout le reste va a Jarvis.",
                   BRUME, 8, largeur=500).pack(fill="x", pady=(8, 0))

    def basculer_jarvis(self):
        self.cfg["jarvis_actif"] = bool(self.var_jarvis.get())
        sauver_config(self.cfg)

    def regler_jarvis(self, cle):
        self.cfg[cle] = bool(self.vars_jarvis[cle].get())
        sauver_config(self.cfg)
        if cle in ("jarvis_son", "jarvis_hey", "jarvis_couper", "jarvis_auto_etalonnage", "jarvis_tolerant"):
            envoyer_oreille(config_oreille(self.cfg))
        if cle == "jarvis_leds" and not self.cfg[cle]:
            poser_led(None)

    def apprendre_jarvis(self):
        a = JARVIS.get("apprentissage")
        if a and not a.get("fini"):
            return
        threading.Thread(target=apprendre_voix, daemon=True).start()

    def ajouter_facon_jarvis(self):
        a = JARVIS.get("apprentissage")
        if a and not a.get("fini"):
            return
        if not gabarits_jarvis():
            return self.apprendre_jarvis()
        threading.Thread(target=apprendre_voix, kwargs={"total": 1, "ajouter": True}, daemon=True).start()

    def oublier_jarvis(self):
        oublier_voix()
        JARVIS["apprentissage"] = {"n": 0, "total": 4, "fini": True,
                                   "message": "Oublie. Seul « Hey Jarvis » le reveille."}

    def preparer_extension(self):
        try:
            dossier = preparer_extension(self.cfg)
            os.startfile(dossier)
            chrome = chemin_chrome()
            if chrome:
                subprocess.Popen([chrome, "chrome://extensions"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            JARVIS["onglets_message"] = "Dossier pret : %s" % dossier
        except Exception as e:
            JARVIS["onglets_message"] = "Impossible : %s" % e

    def connecter_spotify(self):
        self.cfg["spotify_client_id"] = self.champ_spotify.get().strip()
        sauver_config(self.cfg)
        try:
            connecter_spotify(self.cfg, rappel=lambda m: JARVIS.__setitem__("spotify_message", m))
        except Exception as e:
            JARVIS["spotify_message"] = str(e)

    def tester_spotify(self):
        def tester():
            JARVIS["spotify_message"] = "Test en cours..."
            JARVIS["spotify_message"] = diagnostic_spotify(self.cfg)
        threading.Thread(target=tester, daemon=True).start()

    def deconnecter_spotify(self):
        self.cfg["spotify_refresh"] = ""
        sauver_config(self.cfg)
        _SPOTIFY["client"] = None
        JARVIS["spotify_message"] = "Deconnecte."

    def remplir_preferences(self):
        """Une ligne par preference, avec son bouton « Oublier » ; relue a
        chaque ouverture de la page (Jarvis en ajoute pendant qu'elle est fermee)."""
        tk = self.tk
        for w in self.boite_preferences.winfo_children():
            w.destroy()
        prefs = list(self.cfg.get("jarvis_preferences") or [])
        if not prefs:
            self.texte(self.boite_preferences, "Rien pour l'instant.", BRUME, 8).pack(fill="x")
            return
        for i, p in enumerate(prefs):
            ligne = tk.Frame(self.boite_preferences, bg=NUIT)
            ligne.pack(fill="x", pady=(2, 0))
            self.bouton(ligne, "Oublier", lambda i=i: self.oublier_preference(i), compact=True).pack(side="left")
            self.texte(ligne, p, CRAIE, 9, largeur=420).pack(side="left", padx=(8, 0))
        self.bouton(self.boite_preferences, "Tout oublier", lambda: self.oublier_preference(None),
                    compact=True).pack(anchor="w", pady=(6, 0))

    def oublier_routines(self):
        self.cfg["routines_lumiere"] = []
        sauver_config(self.cfg)

    def oublier_souvenirs(self):
        self.cfg["jarvis_souvenirs"] = []
        sauver_config(self.cfg)

    def oublier_preference(self, i):
        prefs = list(self.cfg.get("jarvis_preferences") or [])
        self.cfg["jarvis_preferences"] = [] if i is None else prefs[:i] + prefs[i + 1:]
        sauver_config(self.cfg)
        self.remplir_preferences()

    def regler_mains(self, cle, var):
        self.cfg[cle] = bool(var.get())
        sauver_config(self.cfg)
        if not self.cfg.get("jarvis_pc"):
            JARVIS["acces_jusqua"] = 0.0          # fermees : plus de session ouverte
        self.afficher_code()

    def enregistrer_code(self):
        code = self.champ_code.get()
        self.champ_code.delete(0, "end")
        if not poser_code(self.cfg, code):
            self.txt_code.configure(text="Un code, des chiffres ou un mot : « 4 8 1 5 », « abricot ».")
            return
        sauver_config(self.cfg)
        JARVIS["acces_jusqua"] = 0.0
        self.afficher_code("Code enregistre. Dis-le comme tu l'as tape : chiffre par chiffre, ou le mot.")

    def retirer_code(self):
        poser_code(self.cfg, "")
        sauver_config(self.cfg)
        JARVIS["acces_jusqua"] = 0.0
        self.afficher_code()

    def afficher_code(self, message=""):
        if message:
            t = message
        elif not self.cfg.get("jarvis_pc"):
            t = "Fermees : Jarvis ne touche a rien sur le PC."
        elif not self.cfg.get("jarvis_code_actif"):
            t = "Sans code : il agit directement."
        elif code_regle(self.cfg):
            t = "Code regle. La musique et Spotify marchent sans ; le reste le demande."
        else:
            t = "Aucun code : la musique et Spotify marchent, les dossiers, fichiers et l'ecran restent fermes."
        self.txt_code.configure(text=t)

    def remplir_micros(self):
        """Les micros branches, un bouton chacun ; « celui de Windows » d'abord.
        Un micro choisi puis debranche reste dans la liste, marque comme tel,
        pour qu'on voie pourquoi il ecoute ailleurs."""
        for w in self.boite_micros.winfo_children():
            w.destroy()
        micros = liste_micros()
        choisi = self.var_jarvis_micro.get()
        self.radio(self.boite_micros, "Celui de Windows (par defaut)", self.var_jarvis_micro,
                   "").pack(fill="x")
        for ident, nom in micros:
            self.radio(self.boite_micros, nom, self.var_jarvis_micro, ident).pack(fill="x")
        if choisi and choisi not in {i for i, _ in micros}:
            self.radio(self.boite_micros, "Le micro choisi, debranche -- il ecoute celui de Windows",
                       self.var_jarvis_micro, choisi).pack(fill="x")
        if not micros:
            self.texte(self.boite_micros, "Aucun micro trouve (ou la liste n'est pas lisible ici).",
                       BRUME, 8, largeur=500).pack(fill="x")

    def choisir_micro(self):
        self.cfg["jarvis_micro"] = self.var_jarvis_micro.get()
        sauver_config(self.cfg)
        envoyer_oreille(config_oreille(self.cfg))

    def choisir_voix(self):
        v = self.var_voix_modele.get()
        if v in _jv.VOIX_KOKORO_FR:
            # la veille recharge la voix (sa signature change) et, s'il le
            # faut, fait venir Kokoro
            self.cfg["jarvis_voix_fr"] = v
            sauver_config(self.cfg)
            if not kokoro_present() and KOKORO["etat"] != "preparation":
                KOKORO["etat"] = "absent"
            return
        self.cfg["jarvis_voix_fr"] = "piper"
        self.cfg["jarvis_voix_modele"] = v
        sauver_config(self.cfg)
        if self.cfg["jarvis_voix_modele"] != "windows" and not voix_presente(self.cfg["jarvis_voix_modele"]):
            PIPER["etat"] = "absent"
            threading.Thread(target=preparer_piper, args=(self.cfg,), daemon=True).start()

    def choisir_langue(self):
        self.cfg["jarvis_langue"] = self.var_jarvis_langue.get()
        sauver_config(self.cfg)
        if kokoro_voulu(self.cfg) and not kokoro_present() and KOKORO["etat"] != "preparation":
            KOKORO["etat"] = "absent"        # la veille le fait venir

    def choisir_voix_kokoro(self):
        self.cfg["jarvis_voix_kokoro"] = self.var_voix_kokoro.get()
        sauver_config(self.cfg)             # la veille recharge la voix : sa signature a change

    def essai_voix(self):
        if langue_jarvis(self.cfg) == "en":
            VOIX.dire("Good evening. All systems are operational. How may I help?", None, "en")
        else:
            VOIX.dire("Bonjour. Tous les systèmes sont opérationnels. Que puis-je faire pour vous ?")

    def peindre_jarvis(self):
        etat = JARVIS.get("etat", "eteint")
        titres = {"eteint": "Eteint — le micro est ferme.",
                  "preparation": "Preparation...", "demarrage": "Ouverture du micro...",
                  "attente": "A l'ecoute.", "ecoute": "Il t'ecoute.",
                  "comprend": "Il transcrit.", "pense": "Il reflechit.",
                  "parle": "Il repond.", "erreur": "Un souci."}
        self.txt_jarvis.configure(
            text=titres.get(etat, etat) + ("  " + JARVIS["message"] if JARVIS.get("message") else ""),
            fg=ALERTE if etat == "erreur" else VIF if etat not in ("eteint", "preparation", "demarrage") else BRUME)
        details = ["mode " + ("psychologue" if JARVIS.get("mode") == "psy" else "Jarvis")]
        if hasattr(self, "txt_souvenirs"):
            sv = self.cfg.get("jarvis_souvenirs") or []
            etat_sv = ("%d conversation%s en memoire ; la derniere : %s" % (
                len(sv), "s" if len(sv) > 1 else "", sv[-1].get("texte", "")[:90]) if sv else "Aucune pour l'instant.")
            if self.txt_souvenirs.cget("text") != etat_sv:
                self.txt_souvenirs.configure(text=etat_sv)
        if hasattr(self, "txt_routines"):
            rt = [r for r in self.cfg.get("routines_lumiere") or [] if isinstance(r, dict)]
            etat_rt = ("\n".join(_jv.decrire_routine(r)[:140] for r in rt[:8]) + (
                "\n... et %d autres" % (len(rt) - 8) if len(rt) > 8 else "")) if rt else "Aucune pour l'instant."
            if self.txt_routines.cget("text") != etat_rt:
                self.txt_routines.configure(text=etat_rt)
        if hasattr(self, "txt_onglets"):
            etat_on = "Branchee." if extension_branchee() else (JARVIS.get("onglets_message") or "Pas branchee.")
            if self.txt_onglets.cget("text") != etat_on:
                self.txt_onglets.configure(text=etat_on)
        if hasattr(self, "txt_spotify"):
            etat_sp = ("Connecte." if spotify_connecte(self.cfg) else "Pas connecte.")
            if spotify_connecte(self.cfg) and not self.cfg.get("jarvis_pc"):
                etat_sp += " Mais « Il peut agir sur le PC » est decoche : Jarvis ne s'en sert pas."
            if JARVIS.get("spotify_message"):
                etat_sp += "  " + JARVIS["spotify_message"]
            if self.txt_spotify.cget("text") != etat_sp:
                self.txt_spotify.configure(text=etat_sp)
        prefs = tuple(self.cfg.get("jarvis_preferences") or [])
        if getattr(self, "_prefs_peintes", None) != prefs and hasattr(self, "boite_preferences"):
            self._prefs_peintes = prefs          # Jarvis vient d'en retenir ou d'en oublier une
            self.remplir_preferences()
        if JARVIS.get("db") is not None and etat != "eteint":
            details.append("micro %.0f dB" % JARVIS["db"])
        pr = JARVIS.get("presque")
        if pr and time.time() - pr[2] < 120 and etat != "eteint":
            details.append("« Jarvis » presque reconnu (%.3f pour un seuil de %.3f) : monte la sensibilite, "
                           "ou reapprends ta voix" % (pr[0], pr[1]))
        appris_avec, ecoute = micro_des_gabarits(), str(JARVIS.get("micro") or "")
        if appris_avec and ecoute and appris_avec != ecoute and etat != "eteint":
            details.append("ta voix a ete apprise avec « %s » et il ecoute « %s » : reapprends-la avec ce micro"
                           % (appris_avec, ecoute))
        if JARVIS.get("micro_absent") and etat != "eteint":
            details.append("le micro choisi est debranche : j'ecoute celui de Windows")
        d = etat_dictee()
        details.append("transcription : " + {"pret": "prete", "preparation": "preparation %d %%" % (d["progres"] * 100),
                                             "absent": "pas encore installee", "erreur": "erreur"}.get(d["etat"], d["etat"]))
        n_voix, n_auto = len(gabarits_jarvis()), len(gabarits_auto())
        details.append(("voix apprise (%d facons%s)" % (n_voix, ", + %d gardees seul" % n_auto if n_auto else ""))
                       if n_voix else "voix pas encore apprise")
        if JARVIS.get("coupure") and etat != "eteint":
            details.append("couper la parole : " + str(JARVIS["coupure"]))
        n = len(JARVIS.get("minuteurs") or [])
        if n:
            details.append("%d minuteur(s)" % n)
        self.txt_jarvis_detail.configure(text=" · ".join(details))
        a = JARVIS.get("apprentissage")
        self.txt_jarvis_appris.configure(text=(a or {}).get("message", ""))
        if voix_fr_choisie(self.cfg) != "piper":
            if voix_prete("fr") and kokoro_fr_pret(self.cfg):
                piper = "Voix Kokoro chargee : elle repond tout de suite."
            elif KOKORO["etat"] == "preparation":
                piper = "Telechargement de Kokoro : %d %% (Piper parle en attendant)." % (
                    KOKORO["progres"] * 100)
            elif KOKORO["etat"] == "erreur":
                piper = KOKORO.get("message") or "Kokoro n'a pas pu venir : Piper parle a sa place."
            elif kokoro_present():
                piper = "Voix Kokoro telechargee ; elle se charge quand Jarvis ecoute."
            else:
                piper = "Kokoro se telecharge quand Jarvis ecoute (340 Mo, une fois)."
        elif voix_choisie(self.cfg) == "windows":
            piper = "Voix de Windows."
        elif PIPER["etat"] == "preparation":
            piper = "Telechargement de la voix : %d %%" % (PIPER["progres"] * 100)
        elif voix_prete("fr"):
            piper = PIPER.get("message") or "Voix chargee : elle repond tout de suite."
        elif piper_pret(self.cfg):
            piper = "Voix telechargee ; elle se charge quand Jarvis ecoute."
        else:
            piper = PIPER.get("message") or "La voix se telecharge quand Jarvis ecoute."
        self.txt_piper.configure(text=piper)
        if langue_jarvis(self.cfg) != "en":
            kokoro = "Jarvis parle francais : la voix anglaise ne sert pas."
        elif KOKORO["etat"] == "preparation":
            kokoro = "Telechargement de la voix anglaise : %d %%" % (KOKORO["progres"] * 100)
        elif KOKORO["etat"] == "erreur":
            kokoro = KOKORO.get("message") or "La voix anglaise n'a pas pu venir."
        elif voix_prete("en"):
            kokoro = "Voix anglaise chargee : elle repond tout de suite."
        elif kokoro_present():
            kokoro = "Voix anglaise telechargee ; elle se charge quand Jarvis ecoute."
        else:
            kokoro = "La voix anglaise se telecharge quand Jarvis ecoute (340 Mo, une fois)."
        self.txt_kokoro.configure(text=kokoro)

    # ------------------------------------------------------------------
    #  Page Reglages
    # ------------------------------------------------------------------

    def page_reglages(self):
        # l'essentiel en haut ; le reglage fin de la lumiere et l'affichage, replies
        tk = self.tk
        page = self.nouvelle_page("reglages", defilante=True)
        f = page
        self.curseurs = {}
        self.var_eteindre = tk.IntVar(
            value=1 if self.cfg.get("eteindre_en_partant", True) else 0)
        self.case(f, "Eteindre la guirlande en quittant et a l'arret de Windows",
                  self.var_eteindre).pack(fill="x", pady=(0, 4))
        self.var_cpu = tk.IntVar(value=1 if self.cfg.get("reaction_processeur", True) else 0)
        self.case(f, "Plus le processeur travaille, plus elle brille (mode Regles)",
                  self.var_cpu).pack(fill="x", pady=(0, 10))
        self.curseurs["veille_minutes"] = self.reglette(
            f, "veille_minutes", "Veille apres", 1, 60, 1,
            "Minutes sans clavier ni souris avant la braise sourde.", entier=True)

        f = self.repli(page, "la lumiere, en detail")
        self.curseurs["douceur"] = self.reglette(
            f, "douceur", "Douceur du fondu", 0.01, 0.4, 0.01,
            "Bas = transition lente, haut = changement sec.")
        self.curseurs["luminosite_min"] = self.reglette(
            f, "luminosite_min", "Luminosite au repos", 0.05, 1.0, 0.05,
            "Quand le processeur ne fait rien.")
        self.curseurs["luminosite_max"] = self.reglette(
            f, "luminosite_max", "Luminosite a pleine charge", 0.1, 1.0, 0.05,
            "Quand le processeur est a 100 %.")
        self.curseurs["amplitude_respiration"] = self.reglette(
            f, "amplitude_respiration", "Respiration", 0.0, 0.4, 0.02,
            "Oscillation lente permanente (pas en mode Ecran).")
        self.curseurs["images_par_seconde"] = self.reglette(
            f, "images_par_seconde", "Images par seconde", 2, 60, 1,
            "Le Bluetooth plafonne souvent vers 30 : au-dela, la guirlande retarde. Monte "
            "doucement, redescends si ca saccade.",
            entier=True)

        f = self.repli(page, "affichage")
        self.var_echelle = self.reglette(
            f, "echelle_interface", "Echelle de l'interface", 0.0, 3.0, 0.25,
            "0 = automatique (detectee ici : %.2f). A forcer seulement si l'interface sort trop "
            "petite ou trop grande ; effet au prochain lancement." % self.echelle)

    # ------------------------------------------------------------------
    #  Apercu de la couleur — le meme objet sur l'accueil et sur Ecran
    # ------------------------------------------------------------------

    def apercu_couleur(self, parent, cote=64, fond=VELOURS):
        """Pastille ronde qui prend la couleur reellement envoyee."""
        toile = self.tk.Canvas(parent, width=self.px(cote), height=self.px(cote),
                               bg=fond, highlightthickness=0)
        self.apercus.append((toile, fond, cote))
        return toile

    def peindre_apercus(self):
        for toile, fond, cote in self.apercus:
            try:
                toile.delete("all")
                c = self.px(cote)
                arriere = hex_vers_rgb(fond)
                couleur = vu_a_l_oeil(ETAT["couleur"])
                vif = ETAT["connecte"] and max(ETAT["couleur"]) > 6
                corps = couleur if vif else SOURD
                for part, marge in ((0.16, 0), (0.30, 6), (0.60, 12)):
                    m = self.px(marge)
                    toile.create_oval(m, m, c - m, c - m, outline="",
                                      fill=melange(corps, arriere, part))
                m = self.px(19)
                toile.create_oval(m, m, c - m, c - m, outline="",
                                  fill=melange(corps, arriere, 0.95 if vif else 0.5))
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  Page Calendrier
    # ------------------------------------------------------------------
    #  Page Mises a jour
    # ------------------------------------------------------------------

    def page_maj(self):
        tk = self.tk
        page = f = self.nouvelle_page("maj", defilante=True)

        carte = tk.Frame(f, bg=VELOURS, padx=18, pady=16)
        carte.pack(fill="x")
        self.titre(carte, "version installee").pack(fill="x")
        tk.Label(carte, text=VERSION, bg=VELOURS, fg=CRAIE,
                 font=(self.f_titre, 17), anchor="w").pack(fill="x", pady=(4, 6))
        self.txt_maj = tk.Label(carte, text="", bg=VELOURS, fg=BRUME,
                                font=(self.f_ui, 9), anchor="w", justify="left",
                                wraplength=self.px(460))
        self.txt_maj.pack(fill="x")

        barre = tk.Frame(f, bg=NUIT)
        barre.pack(fill="x", pady=(14, 0))
        # Deux boutons pour un seul geste : on verifie, puis on installe ce
        # qu'on vient de trouver. Un seul suffit, a condition qu'il dise
        # lequel des deux il fera.
        self.btn_maj = self.bouton(barre, "Verifier maintenant",
                                   self.action_maj, compact=True)
        self.btn_maj.pack(side="left")

        self.separateur(f)

        self.titre(f, "notes de la publication").pack(fill="x", pady=(0, 5))
        self.txt_notes = self.texte(f, "-", BRUME, 8, largeur=460)
        self.txt_notes.pack(fill="x")

        self.separateur(f)

        self.var_maj_verifier = tk.IntVar(
            value=1 if self.cfg.get("maj_verifier", True) else 0)
        self.case(f, "Verifier automatiquement toutes les %s heures"
                  % self.cfg.get("maj_intervalle_heures", 6),
                  self.var_maj_verifier, self.options_maj).pack(fill="x")
        self.var_maj_auto = tk.IntVar(
            value=1 if self.cfg.get("maj_installation_auto", True) else 0)
        self.case(f, "L'installer toute seule (tes reglages sont gardes)",
                  self.var_maj_auto, self.options_maj).pack(fill="x", pady=(4, 0))
        self.var_maj_pre = tk.IntVar(
            value=1 if self.cfg.get("maj_prereleases", False) else 0)
        self.case(f, "Recevoir aussi les versions de developpement",
                  self.var_maj_pre, self.options_maj).pack(fill="x", pady=(4, 0))

        f = self.repli(page, "depannage")
        """
        LE JOURNAL, A PORTEE DE CLIC.

        Quand l'application a disparu sous les doigts de quelqu'un, la seule
        chose qui puisse le dire est ce fichier -- c'est lui qui a nomme la
        violation d'acces de la v1.24.4, et il a fallu expliquer un chemin
        entre %LOCALAPPDATA% et un dossier cache pour l'obtenir. Le prochain
        rapport ne doit pas demander ca.

        Deux gestes, parce qu'ils ne servent pas au meme moment : LIRE (on
        regarde soi-meme ce qui s'est passe) et ENVOYER (on en donne une copie
        a quelqu'un). La copie est datee et posee sur le Bureau, avec le
        journal precedent s'il existe -- une panne d'avant le dernier
        demarrage n'est plus dans le fichier courant, et c'est souvent
        celle-la qu'on cherche.
        """
        self.titre(f, "journal de l'application").pack(fill="x", pady=(0, 5))
        self.txt_journal = self.texte(f, "", BRUME, 8, largeur=460)
        self.txt_journal.pack(fill="x", pady=(0, 8))
        rang_j = tk.Frame(f, bg=NUIT)
        rang_j.pack(fill="x")
        self.bouton(rang_j, "Ouvrir le journal",
                    self.action_ouvrir_journal, compact=True).pack(side="left")
        self.bouton(rang_j, "En poser une copie sur le Bureau",
                    self.action_copier_journal, compact=True).pack(side="left", padx=(8, 0))
        self.bouton(rang_j, "Ouvrir le dossier",
                    self.action_ouvrir_dossier, compact=True).pack(side="left", padx=(8, 0))
        self.peindre_journal()

        self.texte(f, "Les versions viennent des publications de github.com/"
                      + DEPOT_GITHUB + ". La verification est une simple lecture "
                      "de l'API publique de GitHub : rien de la machine n'est "
                      "envoye. Le nouvel exe remplace l'ancien dans "
                      + DOSSIER + " et config.json n'est jamais touche.",
                   BRUME, 8, largeur=460).pack(fill="x", pady=(10, 0))

    def peindre_journal(self):
        """Ce que pese le journal, et depuis quand. Sans ca, « ouvrir le
        journal » sur un fichier vide ne dit pas s'il est vide parce que tout
        va bien ou parce qu'il n'a jamais rien ecrit."""
        if not getattr(self, "txt_journal", None):
            return
        try:
            n = os.path.getsize(FICHIER_JOURNAL)
            quand = time.strftime("%d/%m a %H:%M",
                                  time.localtime(os.path.getmtime(FICHIER_JOURNAL)))
            taille = ("%d ko" % (n // 1024)) if n >= 1024 else ("%d octets" % n)
            aussi = (" Le journal precedent est garde a cote."
                     if os.path.exists(FICHIER_JOURNAL + ".1") else "")
            texte = ("%s, derniere ligne le %s.%s C'est ce fichier qu'il faut "
                     "envoyer quand l'application se ferme toute seule : il porte "
                     "la raison." % (taille, quand, aussi))
        except OSError:
            texte = ("Aucun journal pour l'instant. Il se remplit tout seul des "
                     "que l'application tourne sans console.")
        self.txt_journal.configure(text=texte)

    def action_ouvrir_journal(self):
        souci = ouvrir_dans_l_explorateur(FICHIER_JOURNAL)
        ETAT["message"] = ("Journal ouvert" if not souci
                           else "Journal illisible : %s" % souci)

    def action_ouvrir_dossier(self):
        souci = ouvrir_dans_l_explorateur(DOSSIER)
        ETAT["message"] = ("Dossier ouvert" if not souci
                           else "Dossier illisible : %s" % souci)

    def action_copier_journal(self):
        poses, souci = journal_pour_partage()
        if souci:
            ETAT["message"] = "Copie impossible : %s" % souci
            return
        # On ouvre le dossier sur la copie : il ne reste plus qu'a la glisser.
        ouvrir_dans_l_explorateur(os.path.dirname(poses[0]))
        ETAT["message"] = ("%d fichier%s pose%s sur le Bureau"
                           % (len(poses), "s" if len(poses) > 1 else "",
                              "s" if len(poses) > 1 else ""))
        self.peindre_journal()

    def action_maj(self):
        if MAJ["etat"] == "a_poser":
            # Rien a declencher : la pose attend deja. On referme la fenetre, et
            # la boucle de surveillance s'en charge au prochain tour -- un seul
            # chemin vers l'installeur, pas deux qui pourraient partir ensemble.
            self.cacher()
            return
        self.declencher_maj("installer" if MAJ["etat"] in ("disponible", "prete")
                            else "verifier")

    def options_maj(self):
        self.cfg["maj_verifier"] = bool(self.var_maj_verifier.get())
        self.cfg["maj_installation_auto"] = bool(self.var_maj_auto.get())
        self.cfg["maj_prereleases"] = bool(self.var_maj_pre.get())
        sauver_config(self.cfg)

    # ------------------------------------------------------------------
    #  Page Site web
    # ------------------------------------------------------------------

    def page_activite(self):
        tk = self.tk
        f = self.nouvelle_page("activite", defilante=True)

        self.titre(f, "quantified self").pack(fill="x", pady=(0, 6))
        self.texte(f, "Le temps passe par application et par site, tes plages "
                      "actives, ton lever et ton coucher — jamais ce que tu "
                      "tapes. Envoye a BrainDebugger pour situer une journee.",
                   BRUME, 9, largeur=460).pack(fill="x")

        self.separateur(f)
        self.var_act = tk.IntVar(value=1 if self.cfg.get("collecte_active", False) else 0)
        self.case(f, "Envoyer mon activite a BrainDebugger",
                  self.var_act).pack(fill="x")

        # La preview : ce qui partira aujourd'hui, en clair, pas un journal.
        carte = tk.Frame(f, bg=VELOURS, padx=self.px(14), pady=self.px(12))
        carte.pack(fill="x", pady=(12, 0))
        self.txt_apercu_titre = tk.Label(carte, text="Ce qu'il envoie",
                 bg=VELOURS, fg=CRAIE, font=(self.f_ui, 9, "bold"), anchor="w")
        self.txt_apercu_titre.pack(fill="x")
        self.txt_apercu_act = tk.Label(carte, text="", bg=VELOURS, fg=BRUME,
                 font=(self.f_mono, 9), anchor="w", justify="left")
        self.txt_apercu_act.pack(fill="x", pady=(6, 0))

        self.txt_dernier_envoi = self.texte(f, "", BRUME, 9, largeur=460)
        self.txt_dernier_envoi.pack(fill="x", pady=(12, 0))

        barre = tk.Frame(f, bg=NUIT)
        barre.pack(fill="x", pady=(10, 0))
        self.bouton(barre, "Envoyer maintenant",
                    self.envoyer_activite, compact=True).pack(side="left")
        self.txt_activite = self.texte(f, "", BRUME, 9, largeur=460)
        self.txt_activite.pack(fill="x", pady=(10, 0))

        # Reglages fins gardes vivants mais hors de vue : ils tournent avec ce
        # qui est deja enregistre. La page reste juste l'onglet qui envoie.
        self.var_act_titres = tk.IntVar(
            value=1 if self.cfg.get("collecte_titres_complets", False) else 0)
        self.var_act_intervalle = tk.IntVar(
            value=int(self.cfg.get("collecte_intervalle_heures", 6)))

    def envoyer_activite(self):
        self.enregistrer()
        threading.Thread(target=lambda: envoyer_activite_au_site(self.cfg),
                         daemon=True).start()

    def page_passerelle(self):
        tk = self.tk
        f = self.nouvelle_page("passerelle", defilante=True)

        self.titre(f, "passerelle").pack(fill="x", pady=(0, 8))

        # L'ETAT DE LA CONNEXION, EN PREMIER. C'est la seule question qu'on se
        # pose en ouvrant cette page : est-ce que l'app parle au site, oui ou
        # non. Une pastille, un mot, une ligne de detail — le reste vit sans
        # qu'on ait a le regarder.
        etatc = tk.Frame(f, bg=VELOURS, padx=self.px(14), pady=self.px(12))
        etatc.pack(fill="x")
        ligne = tk.Frame(etatc, bg=VELOURS)
        ligne.pack(fill="x")
        self.pont_pastille = tk.Label(ligne, text="●", bg=VELOURS, fg=BRUME,
                                      font=(self.f_ui, 13))
        self.pont_pastille.pack(side="left")
        self.txt_pont_etat = tk.Label(ligne, text="", bg=VELOURS, fg=CRAIE,
                                      font=(self.f_ui, 11, "bold"), anchor="w")
        self.txt_pont_etat.pack(side="left", padx=(8, 0))
        self.txt_pont_detail = self.texte(etatc, "", BRUME, 9, largeur=460)
        self.txt_pont_detail.pack(fill="x", pady=(6, 0))

        # De quoi se connecter, et rien d'autre : l'adresse du site et la cle.
        rang = tk.Frame(f, bg=NUIT)
        rang.pack(fill="x", pady=(16, 0))
        self.texte(rang, "Adresse du site", CRAIE, 9, True).pack(side="left")
        self.champ_pont = self.champ(rang, self.cfg.get("pont_site", ""), 30)
        self.champ_pont.pack(side="right")

        rang2 = tk.Frame(f, bg=NUIT)
        rang2.pack(fill="x", pady=(8, 0))
        self.texte(rang2, "Cle envoyee au site", CRAIE, 9, True).pack(side="left")
        self.champ_pont_cle = self.champ(rang2, self.cfg.get("pont_cle", ""), 24)
        self.champ_pont_cle.pack(side="right")
        self.texte(f, "La meme cle que celle creee sur le site, dans "
                      "Reglages › La passerelle.",
                   BRUME, 8, largeur=460).pack(fill="x", pady=(6, 0))

        # L'interrupteur maitre : BrainDebugger pilote-t-il la guirlande ?
        self.var_affecte_leds = tk.IntVar(
            value=1 if self.cfg.get("pont_affecte_leds", True) else 0)
        self.case(f, "BrainDebugger affecte les LEDs",
                  self.var_affecte_leds).pack(fill="x", pady=(16, 0))
        self.texte(f, "Decoche : le site ne touche plus a la guirlande, et une "
                      "couleur qu'il a posee revient aussitot au mode normal "
                      "(ecran / son / regles).",
                   BRUME, 8, largeur=460).pack(fill="x", pady=(4, 0))

        # ------------------------------------------------------------------
        # TOUT LE RESTE VIT ENCORE, MAIS NE SE MONTRE PLUS.
        #
        # Le serveur local (127.0.0.1), la bascule pendant l'usage du site, le
        # relevé des rappels, l'extrait JS : ces réglages continuent de tourner
        # avec ce qui est déjà enregistré, mais ils encombraient une page dont
        # la seule question utile est « connecté ou pas ». On garde donc leurs
        # champs — l'enregistrement et l'extrait s'appuient dessus — dans un
        # cadre qu'on ne pose jamais. Invisibles, vivants.
        # ------------------------------------------------------------------
        cache = tk.Frame(f, bg=NUIT)   # jamais .pack() : hors de l'ecran

        self.var_pont_releve = tk.IntVar(value=1 if self.cfg.get("pont_releve", True) else 0)
        self.var_pont_notifie = tk.IntVar(value=1 if self.cfg.get("pont_notifie", True) else 0)
        self.var_pont_intervalle = tk.IntVar(value=int(self.cfg.get("pont_intervalle", 3)))
        self.var_presence = tk.IntVar(value=1 if self.cfg.get("pont_presence", True) else 0)
        self.var_presence_humeur = tk.IntVar(
            value=1 if self.cfg.get("pont_presence_suit_humeur", True) else 0)
        self.var_presence_grace = tk.IntVar(value=int(self.cfg.get("pont_presence_grace", 30)))
        self.champ_presence = self.champ(cache, self.cfg.get("pont_presence_indice", ""), 22)
        self.champ_presence_couleur = self.champ(
            cache, self.cfg.get("pont_presence_couleur", "#7C3AED"), 12)

        self.var_api = tk.IntVar(value=1 if self.cfg.get("api_active") else 0)
        self.champ_port = self.champ(cache, str(self.cfg.get("api_port", 7373)), 7)
        self.champ_jeton = self.champ(
            cache, self.cfg.get("api_jeton") or secrets.token_urlsafe(12), 20)
        self.champ_origines = self.champ(cache, ", ".join(self.cfg.get("api_origines", [])), 10)
        self.txt_api = self.texte(cache, "", BRUME, 8)
        self.code = tk.Text(cache, height=8, bg=ENCRE, fg=BRUME, relief="flat", bd=8,
                            font=(self.f_mono, 8), wrap="none", highlightthickness=0,
                            insertbackground=CRAIE)
        self.ecrire_extrait()

    def extrait_js(self):
        port = self.champ_port.get().strip() or "7373"
        jeton = self.champ_jeton.get().strip()
        return (
            "const GUIRLANDE = `http://127.0.0.1:%s`;\n"
            "const JETON = \"%s\";\n"
            "\n"
            "async function humeur(nom, duree = 30) {\n"
            "  try {\n"
            "    await fetch(`${GUIRLANDE}/humeur`, {\n"
            "      method: \"POST\",\n"
            "      headers: { \"Content-Type\": \"application/json\", \"X-Jeton\": JETON },\n"
            "      body: JSON.stringify({ humeur: nom, duree }),\n"
            "    });\n"
            "  } catch (e) { /* guirlande eteinte ou app fermee : on ignore */ }\n"
            "}\n"
            "\n"
            "// humeur(\"Focus\")            -> couleur de la regle nommee Focus\n"
            "// couleur(\"#22D3EE\")         -> couleur libre\n"
            "async function couleur(hex, duree = 30) {\n"
            "  try {\n"
            "    await fetch(`${GUIRLANDE}/couleur`, {\n"
            "      method: \"POST\",\n"
            "      headers: { \"Content-Type\": \"application/json\", \"X-Jeton\": JETON },\n"
            "      body: JSON.stringify({ couleur: hex, duree }),\n"
            "    });\n"
            "  } catch (e) {}\n"
            "}\n" % (port, jeton))

    def ecrire_extrait(self):
        self.code.configure(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", self.extrait_js())

    def copier_code(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.code.get("1.0", "end-1c"))
        ETAT["message"] = "Code copie"

    def copier_jeton(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.champ_jeton.get().strip())
        ETAT["message"] = "Jeton copie"

    def regenerer_jeton(self):
        nouveau = secrets.token_urlsafe(12)
        self.champ_jeton.delete(0, "end")
        self.champ_jeton.insert(0, nouveau)
        self.ecrire_extrait()

    # ------------------------------------------------------------------
    #  Page Appairage
    # ------------------------------------------------------------------

    def page_appairage(self):
        tk = self.tk
        f = self.nouvelle_page("appairage")

        self.texte(f, "Ferme l'application HiLighting sur ton telephone avant de "
                      "chercher : le controleur n'accepte qu'une seule connexion "
                      "a la fois.", BRUME, 8, largeur=490).pack(fill="x", pady=(0, 12))

        self.bouton(f, "Rechercher les appareils", self.lancer_scan,
                    principal=True).pack(anchor="w")
        self.txt_scan = self.texte(f, "Aucune recherche lancee pour l'instant.",
                                   BRUME, 9)
        self.txt_scan.pack(fill="x", pady=(10, 6))

        self.boite = tk.Listbox(f, bg=ENCRE, fg=CRAIE, relief="flat", bd=0, height=9,
                                font=(self.f_mono, 9), selectbackground=self.accent,
                                selectforeground=NUIT, highlightthickness=0,
                                activestyle="none")
        self.boite.pack(fill="both", expand=True, pady=(0, 12))

        self.bouton(f, "Tester et utiliser", self.tester_choix).pack(anchor="w")
        self.texte(f, "L'appareil selectionne doit clignoter en vert trois fois.",
                   BRUME, 8).pack(fill="x", pady=(6, 0))

    def lancer_scan(self):
        if ETAT["occupe"]:
            return
        self.boite.delete(0, "end")
        ETAT["appareils"] = []
        ETAT["demande"] = "scan"

    def tester_choix(self):
        sel = self.boite.curselection()
        if not sel or ETAT["occupe"]:
            return
        ETAT["adresse_test"] = ETAT["appareils"][sel[0]][1]
        ETAT["resultat"] = ""
        ETAT["demande"] = "test"

    # ------------------------------------------------------------------
    #  Pied
    # ------------------------------------------------------------------

    def construire_pied(self):
        tk = self.tk
        tk.Frame(self.root, bg=FIL, height=1).pack(fill="x", side="bottom")
        pied = tk.Frame(self.root, bg=NUIT, padx=22, pady=12)
        pied.pack(fill="x", side="bottom")
        self.bouton(pied, "Enregistrer", self.enregistrer, principal=True).pack(side="left")
        # Pas de « Quitter » ici : fermer ou reduire la fenetre ne fait que la
        # cacher, et l'application continue de tourner derriere. Le seul arret
        # franc est le clic droit « Quitter » sur l'icone de la barre des
        # taches — un geste delibere, jamais un reflexe de fermeture.
        self.bouton(pied, "Reduire", self.cacher, compact=True).pack(side="right")

    # ------------------------------------------------------------------
    #  Actions
    # ------------------------------------------------------------------

    def basculer_pause(self):
        ETAT["pause"] = bool(self.var_pause.get())

    def basculer_demarrage(self):
        # Le choix est RETENU, pas seulement applique : c'est lui que la
        # reparation au lancement relit. Sans ca, un raccourci efface par un
        # tiers ne se distinguerait pas d'un raccourci retire volontairement.
        voulu = bool(self.var_demarrage.get())
        self.cfg["demarrage_auto"] = voulu
        try:
            sauver_config(self.cfg)
        except Exception:
            pass
        if voulu:
            installer_demarrage()
        else:
            retirer_demarrage()

    def reconnecter(self):
        ETAT["demande"] = "reconnecter"

    def enregistrer(self):
        self.cfg["regles"] = [r for r in self.regles_courantes() if r["mots"]]
        for cle, var in self.curseurs.items():
            val = var.get()
            self.cfg[cle] = int(val) if cle in ("veille_minutes", "images_par_seconde") else round(val, 3)
        self.cfg["reaction_processeur"] = bool(self.var_cpu.get())
        self.cfg["echelle_interface"] = round(self.var_echelle.get(), 2)
        self.cfg["eteindre_en_partant"] = bool(self.var_eteindre.get())
        self.cfg["pont_site"] = self.champ_pont.get().strip().rstrip("/")
        self.cfg["pont_cle"] = self.champ_pont_cle.get().strip()
        self.cfg["pont_releve"] = bool(self.var_pont_releve.get())
        self.cfg["pont_notifie"] = bool(self.var_pont_notifie.get())
        self.cfg["pont_intervalle"] = int(self.var_pont_intervalle.get())
        self.cfg["pont_presence"] = bool(self.var_presence.get())
        self.cfg["pont_presence_suit_humeur"] = bool(self.var_presence_humeur.get())
        self.cfg["pont_presence_indice"] = self.champ_presence.get().strip().lower()
        couleur = self.champ_presence_couleur.get().strip()
        self.cfg["pont_presence_couleur"] = (
            couleur if couleur.startswith("#") and len(couleur) == 7 else "#7C3AED")
        self.cfg["pont_presence_grace"] = int(self.var_presence_grace.get())
        self.cfg["pont_affecte_leds"] = bool(self.var_affecte_leds.get())
        # Coupe a l'instant : on relache le forcage POSE PAR LE SITE (jamais le
        # forcage manuel, une couleur choisie a la main) et on oublie la
        # presence, pour que la guirlande revienne aussitot au mode normal --
        # sans attendre la peremption du forcage en cours.
        if not self.cfg["pont_affecte_leds"]:
            f_site = ETAT.get("forcage")
            if f_site and not f_site.get("manuel"):
                ETAT["forcage"] = None
            ETAT["presence"] = None
            ETAT["presence_vu"] = 0.0
        avant_act = self.cfg.get("collecte_active")
        # Un seul interrupteur : « Envoyer mon activite » tient le journal ET
        # l'envoie. Rien a cocher en plus, rien a oublier.
        envoyer = bool(self.var_act.get())
        self.cfg["collecte_active"] = envoyer
        self.cfg["collecte_envoi"] = envoyer
        self.cfg["collecte_titres_complets"] = bool(self.var_act_titres.get())
        self.cfg["collecte_intervalle_heures"] = int(self.var_act_intervalle.get())
        if self.cfg["collecte_active"] != avant_act:
            demarrer_activite(self.cfg)
        self.cfg["mode"] = self.var_mode.get()
        source = self.var_source.get()
        self.cfg["ecran_source"] = source if source == "actif" else int(source)
        self.cfg["ecran_saturation"] = round(self.var_sat.get(), 2)
        self.cfg["douceur_ecran"] = round(self.var_douceur_ecran.get(), 2)
        self.cfg["ecran_finesse"] = int(self.var_finesse.get())
        self.cfg["ecran_cible"] = self.var_cible_ecran.get()
        self.cfg["ecran_noir"] = round(self.var_ecran_noir.get(), 2)
        self.cfg["ecran_blanc"] = round(self.var_ecran_blanc.get(), 2)
        self.cfg["ecran_gamma"] = round(self.var_ecran_gamma.get(), 2)
        self.cfg["ecran_luminance_min"] = round(self.var_ecran_plancher.get(), 2)
        self.cfg["ecran_luminosite_base"] = round(self.var_ecran_base.get(), 2)
        self.cfg["ecran_suit_filtre_bleu"] = bool(self.var_filtre_bleu.get())
        self.cfg["ecran_balance_temp"] = round(self.var_balance_temp.get(), 2)
        self.cfg["ecran_balance_tint"] = round(self.var_balance_tint.get(), 2)
        self.cfg["led_blanc_kelvin"] = int(round(self.var_led_kelvin.get() / 250.0) * 250)
        self.cfg["ecran_filtre_force"] = round(self.var_filtre_force.get(), 2)
        self.cfg["son_bande"] = self.var_bande.get()
        self.cfg["son_palette"] = self.var_palette.get()
        self.cfg["son_sensibilite"] = round(self.var_sens.get(), 2)
        self.cfg["son_attaque"] = round(self.var_attaque.get(), 2)
        self.cfg["son_chute"] = round(self.var_chute.get(), 2)
        self.cfg["son_plancher"] = round(self.var_plancher.get(), 2)
        self.cfg["son_cible"] = self.var_cible.get()
        self.cfg["son_saturation_fixe"] = round(self.var_sat_fixe.get(), 2)
        self.cfg["son_luminosite_fixe"] = round(self.var_lum_fixe.get(), 2)
        self.cfg["jarvis_sensibilite"] = round(self.var_jarvis_sens.get(), 2)
        self.cfg["jarvis_lenteur"] = round(self.var_jarvis_lenteur.get(), 2)
        self.cfg["jarvis_appellation"] = self.champ_appellation.get().strip()[:40]
        envoyer_oreille(config_oreille(self.cfg))
        self.cfg["api_active"] = bool(self.var_api.get())
        try:
            self.cfg["api_port"] = max(1024, min(65535, int(self.champ_port.get())))
        except ValueError:
            self.cfg["api_port"] = 7373
        self.cfg["api_jeton"] = self.champ_jeton.get().strip()
        self.cfg["api_origines"] = [o.strip() for o in
                                    self.champ_origines.get().split(",") if o.strip()]
        sauver_config(self.cfg)
        if self.cfg["mode"] == "son":
            demarrer_audio(self.cfg)
        else:
            arreter_audio()
        demarrer_api(self.cfg)
        self.champ_jeton.delete(0, "end")
        self.champ_jeton.insert(0, self.cfg.get("api_jeton", ""))
        self.ecrire_extrait()
        ETAT["message"] = "Reglages enregistres"

    def cacher(self):
        self.root.withdraw()

    def afficher(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def peindre_etat_pont(self):
        """La seule question de la page Passerelle : connecte, ou pas.

        On est connecte des qu'un echange recent a reussi — un releve de
        rappels (PONT ok) ou un envoi d'activite parti sans erreur. Le detail
        redit le dernier message du site et l'heure du dernier contact."""
        etat = PONT.get("etat", "inactif")
        envoi_ok = SYNC.get("reussi", 0) and (time.time() - SYNC["reussi"]) < 2 * 3600
        if etat == "ok" or envoi_ok:
            couleur, mot = VIF, "Connecte"
        elif etat == "erreur":
            couleur, mot = ALERTE, "Probleme de connexion"
        else:
            couleur, mot = FIL, "Pas encore connecte"
        self.pont_pastille.configure(fg=couleur)
        self.txt_pont_etat.configure(text=mot)
        detail = PONT.get("message", "")
        vu = PONT.get("vu_le", 0)
        if vu:
            detail += "  ·  dernier contact " + time.strftime("%H:%M", time.localtime(vu))
        self.txt_pont_detail.configure(text=detail)

    # ------------------------------------------------------------------
    #  Rafraichissement
    # ------------------------------------------------------------------

    # Quatre passages de 400 ms : le temps de poser une fenetre qu'on deplace,
    # et pas au-dela — au-dessus, changer d'ecran donnerait une interface qui
    # tarde a se remettre a la bonne taille.
    ECHELLE_TICS = 4

    def suivre_ecran(self):
        """L'echelle du moniteur qui porte la fenetre, une fois qu'elle y est.

        LA BOUCLE. Rebatir l'interface la redimensionne ; a cheval sur un 4K et
        un 1080p, la nouvelle taille change le moniteur majoritaire, donc la
        mesure, donc l'echelle voulue — et on repart, deux fois et demie par
        seconde. C'est le « coince entre les deux ecrans » qu'on voyait.

        Deux verrous, et il faut les deux. Tant que la fenetre DEBORDE de son
        moniteur, la mesure ne veut rien dire : on ne touche a rien. Et une
        fois posee, on attend que la meme valeur revienne plusieurs fois de
        suite — un deplacement a la souris traverse les deux ecrans, et
        redessiner a chaque instant traverse ferait clignoter l'interface tout
        le long du trajet.
        """
        try:
            voulue = echelle_ecran(self.root, 0.0)
        except Exception:
            return False
        if abs(voulue - self.echelle) <= 0.05 or fenetre_a_cheval(self.root):
            self._ech_vue = None
            self._ech_tics = 0
            return False
        if self._ech_vue is None or abs(voulue - self._ech_vue) > 0.05:
            self._ech_vue = voulue
            self._ech_tics = 1
            return False
        self._ech_tics += 1
        if self._ech_tics < self.ECHELLE_TICS:
            return False
        self._ech_vue = None
        self._ech_tics = 0
        self.refaire_interface(voulue)
        return True

    def rafraichir(self):
        g = self.generation
        # Meme raison que dans animer() : cachee, la fenetre ne redessine rien.
        # L'etat continue de vivre dans ETAT ; il se lira a la reouverture.
        if not self.interface_visible():
            return self.root.after(600, lambda: g == self.generation and self.rafraichir())
        r, v, b = ETAT["couleur"]
        hexa = rgb_vers_hex((r, v, b))
        accent = lisible(vu_a_l_oeil((r, v, b))) if max(r, v, b) > 8 else ACCENT_DEPART
        if accent != self.accent:
            self.accent = accent
            self.appliquer_accent()

        self.txt_statut.configure(text=ETAT["message"],
                                  fg=VIF if ETAT["connecte"] else ALERTE)
        # une pastille de la couleur envoyee, plutot que les octets de la trame
        self.txt_trame.configure(text="\u25cf", fg=hexa if max(r, v, b) > 8 else FIL)
        self.txt_titre.configure(fg=CRAIE)
        self.txt_regle.configure(text=ETAT["regle"])
        self.txt_contexte.configure(text=(ETAT["contexte"] or "aucune fenetre detectee")[:64])
        self.txt_adresse.configure(
            text=self.cfg.get("adresse", "") or "aucune guirlande appairee")
        mode = {"applications": "mode Regles", "ecran": "mode Ecran",
                "son": "mode Son",
                "mixte": "mode Mixte"}.get(self.cfg.get("mode", "applications"), "")
        self.txt_mode.configure(text=mode.upper())
        self.txt_detail.configure(
            text=f"{mode} — {ETAT['ecrans']} ecran(s) — "
                 f"{self.cfg.get('images_par_seconde', 8)} images par seconde")

        # Deplacer la fenetre d'un 4K vers un 1080p doit la ramener a la
        # taille du 1080p — mais seulement une fois qu'elle y est posee.
        if not self.cfg.get("echelle_interface", 0.0) and self.suivre_ecran():
            return

        self.peindre_apercus()
        self.txt_apercu_ecran.configure(text=hexa)
        if self.section == "passerelle":
            self.peindre_etat_pont()
        if self.section == "jarvis":
            self.peindre_jarvis()
        if self.section == "activite":
            _, apercu = apercu_activite()
            self.txt_apercu_act.configure(text=apercu)
            quand = dernier_envoi_texte()
            self.txt_dernier_envoi.configure(
                text=("Dernier envoi automatique : " + quand) if quand
                else "Aucun envoi automatique pour l'instant.")
            self.txt_activite.configure(
                text=ACTIVITE.get("message", "arrete"),
                fg=ALERTE if "impossible" in ACTIVITE.get("message", "")
                or "demande" in ACTIVITE.get("message", "") else BRUME)

        if self.section == "ecran":
            # Sans cette phrase, le mode Ecran suspendu est indiscernable
            # d'un mode Ecran qui marche : le panneau affichait le message du
            # Bluetooth, « Connectee », pendant que l'ecran n'etait plus lu.
            suspendue = ETAT["ecran"]["suspendue"]
            self.txt_etat_ecran.configure(
                text=("La capture est en pause : Windows ne rend plus l'image "
                      "de l'ecran. La guirlande suit tes regles en attendant, "
                      "et la couleur reviendra toute seule.") if suspendue else "",
                fg=ALERTE if suspendue else BRUME)

        if self.section == "accueil":
            # Repeindre hors de l'accueil ne servirait a rien : la tuile
            # n'est pas a l'ecran.
            self._dessiner_ampoule(self._fond_ampoule)
            self.etat_tuile.configure(
                text=("connectee \u2014 " + hexa) if ETAT["connecte"]
                else "hors ligne",
                fg=VIF if ETAT["connecte"] else ALERTE)

        """
        ET LE PANNEAU DIT CE QUI VA SE PASSER, PARCE QUE C'EST LUI QU'ON REGARDE.

        Une pose de mise a jour tue l'application. Tant que ca ne se disait que
        dans une bulle de notification -- avalee par l'assistant de
        concentration a l'ouverture de session -- la fenetre disparaissait sans
        un mot, et ca se rapportait comme un plantage. Le message est ici
        maintenant, a l'endroit ou quelqu'un vient justement de cliquer.
        """
        a_poser = MAJ["etat"] == "a_poser"
        if a_poser and MAJ.get("differee"):
            texte_maj = ("Version %s prete. Elle se pose des que tu fermes "
                         "cette fenetre, et l'application revient seule."
                         % MAJ["version"])
        elif a_poser:
            texte_maj = "Pose de la version %s..." % MAJ["version"]
        else:
            texte_maj = MAJ["message"]
        self.txt_maj.configure(
            text=texte_maj,
            fg=VIF if MAJ["etat"] in ("disponible", "prete", "a_poser") else BRUME)
        pret = MAJ["etat"] in ("disponible", "prete")
        occupe = MAJ["etat"] in ("verification", "telechargement")
        self.btn_maj.configure(
            text=("Poser maintenant" if a_poser
                  else ("Installer " + MAJ["version"]) if pret
                  else ("En cours..." if occupe else "Verifier maintenant")),
            state="disabled" if occupe else "normal")
        # La pastille du rail s'allume des qu'une maj attend, meme groupe replie.
        self.rail_toile.itemconfig(self.badge_maj,
                                   state="normal" if (pret or a_poser) else "hidden")

        forc = ETAT.get("forcage")
        if forc and forc.get("manuel"):
            self.txt_manuel.configure(
                text="Forcee : " + rgb_vers_hex(tuple(forc["couleur"])), fg=VIF)
        else:
            self.txt_manuel.configure(
                text="Automatique — l'ecran, le son ou les regles decident.", fg=BRUME)
        notes = (MAJ.get("notes") or "").strip()
        self.txt_notes.configure(text=notes[:1500] if notes else "-")

        self.txt_audio.configure(text="Capture " + AUDIO.get("message", "arretee"))

        cible_ecran = self.cfg.get("ecran_cible", "luminosite")
        en_ecran = self.cfg.get("mode") in ("ecran", "mixte")
        self.poser_jauge(self.jauge_ecran_entree,
                         ETAT["ecran_luminance"] if en_ecran else 0.0,
                         en_ecran, "l'ecran")
        self.poser_jauge(
            self.jauge_ecran_lum,
            ETAT["ecran_gain"] if en_ecran
            else self.cfg.get("ecran_luminosite_base", 1.0),
            en_ecran and cible_ecran in ("luminosite", "les_deux"), "l'ecran")
        self.poser_jauge(
            self.jauge_ecran_sat, ETAT["ecran_sat"] if en_ecran else 0.0,
            en_ecran and cible_ecran in ("saturation", "les_deux"), "l'ecran")
        # L'indicateur de filtre : detecte-t-on f.lux/Night Light, et de combien
        # on rechauffe ? En vert quand on compense vraiment, sourd sinon.
        if getattr(self, "txt_filtre", None):
            try:
                phrase, compense = texte_filtre_ecran(diag_filtre_ecran(self.cfg))
                self.txt_filtre.configure(text=phrase, fg=(VIF if compense else BRUME))
            except Exception:
                pass

        cible = self.cfg.get("son_cible", "luminosite")
        en_son = self.cfg.get("mode") == "son" and AUDIO.get("actif")
        self.poser_jauge(
            self.jauge_lum,
            AUDIO["gain"] if en_son else self.cfg.get("son_luminosite_fixe", 1.0),
            en_son and cible in ("luminosite", "les_deux"))
        self.poser_jauge(
            self.jauge_sat,
            AUDIO["saturation"] if en_son else self.cfg.get("son_saturation_fixe", 0.92),
            en_son and cible in ("saturation", "les_deux"))
        self.txt_api.configure(text="Passerelle " + ETAT.get("api", "arretee"))

        self.txt_scan.configure(
            text=ETAT["message"] if ETAT["occupe"] or ETAT["appareils"]
            else "Aucune recherche lancee pour l'instant.")
        if len(ETAT["appareils"]) != self.boite.size():
            self.boite.delete(0, "end")
            for nom, adr in ETAT["appareils"]:
                marque = "   probablement" if nom.upper().startswith("L") else ""
                self.boite.insert("end", f" {nom[:22]:24} {adr}{marque}")
        if ETAT["resultat"] == "ok":
            ETAT["resultat"] = ""
            self.aller("etat")

        self.root.after(400, lambda: g == self.generation and self.rafraichir())

    def appliquer_accent(self):
        try:
            self.bouton_principal.configure(bg=self.accent, activebackground=self.accent)
            self.boite.configure(selectbackground=self.accent)
            _, signe, _, _ = self.onglets[self.section]
            self.rail_toile.itemconfig(signe, fill=self.accent)
            for peindre in self.reglettes:
                peindre()
        except Exception:
            pass


# ==========================================================================
#  Mises a jour depuis GitHub
#
#  L'exe publie est deja son propre installeur : lance depuis n'importe ou
#  il se copie sur l'installation, garde la configuration et se relance
#  (voir installer_ou_mettre_a_jour). Se mettre a jour revient donc a
#  telecharger le .exe joint a la derniere publication et a l'executer.
#
#  Cote reseau, rien ne part d'ici : une requete GET anonyme sur l'API
#  publique de GitHub, au plus une fois par intervalle. Aucune donnee de la
#  machine n'est transmise, pas meme le numero de version installe.
# ==========================================================================

API_GITHUB = "https://api.github.com/repos/" + DEPOT_GITHUB
PAGE_PUBLICATIONS = "https://github.com/" + DEPOT_GITHUB + "/releases"
DOSSIER_MAJ = os.path.join(DOSSIER, "maj")

MAJ = {
    # repos | verification | a_jour | disponible | telechargement | prete |
    # a_poser | erreur
    #
    # « a_poser » : la version est telechargee ET la decision de l'installer est
    # prise. L'installation elle-meme TUE cette instance, et c'est pour ca
    # qu'elle ne se fait plus ici : voir `differer_la_pose`.
    "etat": "repos",
    "message": "Aucune verification depuis le demarrage.",
    "version": "",
    "notes": "",
    "page": PAGE_PUBLICATIONS,
    "url": "",
    "taille": 0,
    "progression": 0.0,
    "fichier": "",
    "verifie_le": 0.0,
    # L'heure a laquelle la pose a ete demandee, et si elle attend que la
    # fenetre se referme. Le panneau les lit pour dire ce qui va se passer.
    "demande_le": 0.0,
    "differee": False,
}


def version_en_tuple(texte):
    """Ordonne des versions du style 1.2.0 ou v1.2.0-beta.3.

    Une pre-version passe avant la version finale portant le meme numero :
    1.2.0-beta est plus ancienne que 1.2.0.
    """
    base = str(texte).strip().lstrip("vV").split("+")[0]
    pre = ""
    if "-" in base:
        base, pre = base.split("-", 1)
    nombres = []
    for morceau in base.split("."):
        chiffres = "".join(c for c in morceau if c.isdigit())
        nombres.append(int(chiffres) if chiffres else 0)
    while len(nombres) < 3:
        nombres.append(0)

    # Le suffixe se compare morceau par morceau, les chiffres comme des
    # nombres : compare comme du texte, beta.10 passerait avant beta.2.
    rang = []
    for morceau in (pre.split(".") if pre else []):
        if morceau.isdigit():
            rang.append((0, int(morceau), ""))
        else:
            rang.append((1, 0, morceau))
    return (tuple(nombres[:3]), 0 if pre else 1, tuple(rang))


def est_build(version):
    """Une pre-version issue d'une fusion, par opposition a une stable."""
    return "-dev." in str(version)


def plus_recente(candidate, reference):
    return version_en_tuple(candidate) > version_en_tuple(reference)


def _contexte_ssl():
    """Le magasin de Windows passe en premier : c'est lui qui contient les
    autorites ajoutees par un antivirus ou un proxy d'entreprise, sans
    lesquelles la connexion echouerait. certifi ne sert que si ce magasin
    ressort vide, ce qui arrive sur certaines compilations."""
    try:
        import ssl
    except Exception:
        return None
    try:
        contexte = ssl.create_default_context()
        if contexte.cert_store_stats().get("x509_ca", 0) > 0:
            return contexte
    except Exception:
        contexte = None
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return contexte


_jv.CONTEXTE_SSL = _contexte_ssl          # Spotify (http_json) : le meme magasin de certificats


def _ouvrir(url, delai=20):
    requete = urllib.request.Request(url, headers={
        # Sans numero de version : la page « Mises a jour » et le README
        # promettent que rien de la machine n'est transmis, l'en-tete doit
        # tenir cette promesse.
        "User-Agent": "MachiToolkit",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return urllib.request.urlopen(requete, timeout=delai, context=_contexte_ssl())


def derniere_publication(prereleases=False):
    """Renvoie la publication GitHub la plus recente, ou None.

    Le .exe est retrouve par son extension et non par son nom exact : le
    jour ou une autre application du toolkit prend le relais, le nom du
    fichier peut changer sans casser la mise a jour des exemplaires deja
    installes.
    """
    url = (API_GITHUB + "/releases?per_page=20") if prereleases \
        else (API_GITHUB + "/releases/latest")
    with _ouvrir(url) as reponse:
        donnees = json.loads(reponse.read().decode("utf-8"))

    if isinstance(donnees, list):
        publiees = [p for p in donnees if not p.get("draft")]
        if not publiees:
            return None
        publiees.sort(key=lambda p: version_en_tuple(p.get("tag_name", "")),
                      reverse=True)
        donnees = publiees[0]

    actif = None
    for piece in donnees.get("assets", []):
        if str(piece.get("name", "")).lower().endswith(".exe"):
            actif = piece
            break

    return {
        "version": str(donnees.get("tag_name", "")).lstrip("vV"),
        "notes": donnees.get("body") or "",
        "page": donnees.get("html_url") or PAGE_PUBLICATIONS,
        "url": (actif or {}).get("browser_download_url", ""),
        "nom": (actif or {}).get("name", ""),
        "taille": int((actif or {}).get("size") or 0),
    }


def verifier_maj(cfg):
    """Interroge GitHub. Renvoie la publication si elle est plus recente."""
    MAJ["etat"] = "verification"
    MAJ["message"] = "Recherche d'une mise a jour..."
    try:
        publication = derniere_publication(bool(cfg.get("maj_prereleases", False)))
    except urllib.error.HTTPError as e:
        MAJ["etat"] = "erreur"
        MAJ["message"] = ("Aucune publication sur le depot pour l'instant."
                          if e.code == 404 else
                          "GitHub a repondu %s. Nouvel essai plus tard." % e.code)
        return None
    except Exception as e:
        MAJ["etat"] = "erreur"
        MAJ["message"] = "Verification impossible : %s" % e
        return None

    MAJ["verifie_le"] = time.time()
    if not publication or not publication["version"]:
        MAJ["etat"] = "a_jour"
        MAJ["message"] = "Aucune publication trouvee sur le depot."
        return None

    MAJ["page"] = publication["page"]
    if not plus_recente(publication["version"], VERSION):
        MAJ["etat"] = "a_jour"
        MAJ["message"] = "Version %s — a jour." % VERSION
        return None

    MAJ["version"] = publication["version"]
    MAJ["notes"] = publication["notes"]
    MAJ["url"] = publication["url"]
    MAJ["taille"] = publication["taille"]

    if not publication["url"]:
        MAJ["etat"] = "erreur"
        MAJ["message"] = ("Version %s publiee, mais sans .exe joint. "
                          "A recuperer a la main." % publication["version"])
        return None

    MAJ["etat"] = "disponible"
    MAJ["message"] = "%s %s disponible (installee : %s)." % (
        "Nouveau build" if est_build(publication["version"]) else "Version",
        publication["version"], VERSION)
    return publication


def telecharger_maj(publication):
    """Ecrit le nouvel exe dans DOSSIER_MAJ. Leve en cas d'echec."""
    os.makedirs(DOSSIER_MAJ, exist_ok=True)
    cible = os.path.join(DOSSIER_MAJ,
                         "%s-%s.exe" % (NOM_COURT, publication["version"]))
    partiel = cible + ".part"

    MAJ["etat"] = "telechargement"
    MAJ["progression"] = 0.0
    MAJ["message"] = "Telechargement de la version %s..." % publication["version"]

    recu = 0
    with _ouvrir(publication["url"], delai=60) as flux:
        total = int(flux.headers.get("Content-Length") or publication["taille"] or 0)
        with open(partiel, "wb") as sortie:
            while True:
                bloc = flux.read(262144)
                if not bloc:
                    break
                sortie.write(bloc)
                recu += len(bloc)
                if total:
                    MAJ["progression"] = recu / float(total)
                    MAJ["message"] = "Telechargement %d %%" % (recu * 100 // total)

    if total and recu < total:
        os.remove(partiel)
        raise IOError("telechargement interrompu")

    os.replace(partiel, cible)
    MAJ["fichier"] = cible
    MAJ["etat"] = "prete"
    MAJ["message"] = ("Version %s telechargee, prete a etre posee."
                      % publication["version"])
    return cible


def lancer_installeur_maj():
    """Passe la main a l'exe telecharge : il arrete cette instance, se copie
    sur l'installation et la relance. L'appelant doit quitter ensuite."""
    chemin = MAJ.get("fichier")
    if not FIGE:
        MAJ["etat"] = "erreur"
        MAJ["message"] = ("En mode script, la mise a jour se fait par "
                          "git pull. Rien n'a ete touche.")
        return False
    if not chemin or not os.path.exists(chemin):
        MAJ["etat"] = "erreur"
        MAJ["message"] = "Le fichier telecharge a disparu."
        return False
    try:
        subprocess.Popen([chemin, "--maj-silencieuse"], close_fds=True)
        return True
    except Exception as e:
        MAJ["etat"] = "erreur"
        MAJ["message"] = "Lancement de l'installeur impossible : %s" % e
        return False


def nettoyer_maj():
    """Efface les exe telecharges une fois la mise a jour posee."""
    try:
        if not os.path.isdir(DOSSIER_MAJ):
            return
        for nom in os.listdir(DOSSIER_MAJ):
            chemin = os.path.join(DOSSIER_MAJ, nom)
            try:
                if os.path.isfile(chemin):
                    os.remove(chemin)
            except Exception:
                pass
    except Exception:
        pass


# ==========================================================================
#  Installation, mise a jour, demarrage
# ==========================================================================

def version_installee():
    """Numero de la version actuellement installee, ou '' si inconnu.

    Ecrit par l'exe installe a chaque demarrage : c'est ce qui permet de
    refuser qu'un vieux fichier telecharge s'ecrase par-dessus une version
    plus recente."""
    try:
        with open(FICHIER_VERSION, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def ecrire_version_installee():
    try:
        with open(FICHIER_VERSION, "w", encoding="utf-8") as f:
            f.write(VERSION)
    except Exception:
        pass


def installer_raccourci():
    """Raccourci dans le menu Demarrer, pour relancer sans chercher l'exe.

    Apres avoir quitte depuis l'icone, plus besoin de retrouver le fichier :
    'Machi Tool' se tape dans la recherche Windows. Sans pywin32/COM, on
    laisse tomber en silence — l'entree de demarrage suffit au lancement
    automatique."""
    if os.name != "nt":
        return
    try:
        import win32com.client
        dossier = os.path.join(os.environ.get("APPDATA", ""), "Microsoft",
                               "Windows", "Start Menu", "Programs")
        os.makedirs(dossier, exist_ok=True)
        lien = os.path.join(dossier, NOM_APP + ".lnk")
        shell = win32com.client.Dispatch("WScript.Shell")
        raccourci = shell.CreateShortcut(lien)
        raccourci.TargetPath = CIBLE_EXE
        raccourci.WorkingDirectory = DOSSIER
        ico = os.path.join(DOSSIER, "icone.ico")
        if os.path.exists(ico):
            raccourci.IconLocation = ico
        raccourci.Description = NOM_APP
        raccourci.Save()
    except Exception as e:
        print("Raccourci menu Demarrer non cree :", e)


def installer_protocole():
    """Enregistre le schema d'URL machitool:// .

    Sans ca, un site ne peut pas relancer l'application quand elle est eteinte :
    un navigateur ne demarre aucun programme local, et un fetch vers 127.0.0.1
    echoue simplement si personne n'ecoute. Avec le schema, le site ouvre
    machitool://sync et Windows lance « CIBLE_EXE machitool://sync ». L'URL n'est
    pas une commande reconnue par main(), donc l'app demarre normalement — ou ne
    fait rien si elle tourne deja (le mutex la garde en un seul exemplaire), ce
    qui suffit : le serveur local est alors la, et le site retire son digest.
    """
    if os.name != "nt":
        return
    cible = CIBLE_EXE
    if not os.path.exists(cible):
        return   # pas d'exe installe (mode script) : rien a lancer par le schema
    try:
        import winreg
        base = r"Software\Classes\machitool"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:Machi Tool")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'"{cible}" "%1"')
    except Exception as e:
        print("Enregistrement du schema machitool:// impossible :", e)


def commande_lancement():
    """Ce qu'il faut executer pour demarrer l'application."""
    if FIGE:
        return f'"{CIBLE_EXE}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{pythonw}" "{os.path.abspath(__file__)}"'


def _dossier_demarrage():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup")


def chemin_demarrage():
    return os.path.join(_dossier_demarrage(), "machitool.vbs")


def ancien_chemin_demarrage():
    return os.path.join(_dossier_demarrage(), "guirlande_ambiante.vbs")


def installer_demarrage():
    try:
        cmd = commande_lancement().replace('"', '""')
        with open(chemin_demarrage(), "w", encoding="utf-8") as f:
            f.write(f'CreateObject("WScript.Shell").Run "{cmd}", 0, False\n')
        return True
    except Exception as e:
        print("Ecriture dans Demarrage impossible :", e)
        return False


def retirer_demarrage():
    p = chemin_demarrage()
    if os.path.exists(p):
        os.remove(p)


def assurer_demarrage(cfg):
    """Repose le raccourci de demarrage s'il manque ou s'il pointe ailleurs.

    Sans ca, une entree effacee (nettoyeur, profil recree, mise a jour de
    Windows) ou laissee sur un ancien chemin apres une reinstallation ne se
    voit pas : l'application ne se relance plus au demarrage, et le journal
    s'arrete sans un mot. On ne la repose QUE si elle etait voulue --
    `demarrage_auto` retient le choix, la seule presence du fichier ne
    distinguant pas « retire par l'utilisateur » de « efface par un tiers ».
    """
    if os.name != "nt" or not FIGE or not cfg.get("demarrage_auto", True):
        return None
    p = chemin_demarrage()
    voulu = commande_lancement().replace('"', '""')
    try:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                if voulu in f.read():
                    return None            # deja bon
            raison = "raccourci de demarrage repointe"
        else:
            raison = "raccourci de demarrage repose"
        if installer_demarrage():
            print(raison.capitalize(), ":", p)
            return raison
    except Exception as e:
        print("Verification du demarrage impossible :", e)
    return None


def creer_lanceur():
    """Pour le mode script uniquement."""
    cmd = commande_lancement().replace('"', '""')
    with open(os.path.join(DOSSIER, "Lancer.vbs"), "w", encoding="utf-8") as f:
        f.write(f'CreateObject("WScript.Shell").Run "{cmd}", 0, False\n')


def dialogue(titre, texte):
    if SILENCIEUX:
        print(titre, ":", texte)
        return
    try:
        import tkinter as tk
        from tkinter import messagebox
        racine = tk.Tk()
        racine.withdraw()
        messagebox.showinfo(titre, texte)
        racine.destroy()
    except Exception:
        print(titre, ":", texte)


def arreter_instances(chemin):
    """Termine les copies deja lancees de l'application installee."""
    try:
        import psutil
    except ImportError:
        return
    moi = os.getpid()
    vises = []
    for p in psutil.process_iter(["pid", "exe"]):
        try:
            if p.info["pid"] != moi and p.info["exe"] and \
               os.path.normcase(p.info["exe"]) == os.path.normcase(chemin):
                vises.append(p)
        except Exception:
            continue
    for p in vises:
        try:
            p.terminate()
        except Exception:
            pass
    if vises:
        psutil.wait_procs(vises, timeout=6)
        for p in vises:
            try:
                if p.is_running():
                    p.kill()
            except Exception:
                pass


def reprendre_ancienne_installation():
    """Recupere les reglages de GuirlandeAmbiante, nom de l'app avant la 1.2.

    Sans ca, la mise a jour ouvrirait une installation vierge a cote de
    l'ancienne : guirlande a reappairer, regles a resaisir. On copie plutot
    que deplacer, pour qu'un retour en arriere reste possible.
    """
    reprise = False
    try:
        if os.path.isdir(ANCIEN_DOSSIER) and not os.path.exists(FICHIER_CONFIG):
            ancien_config = os.path.join(ANCIEN_DOSSIER, "config.json")
            if os.path.exists(ancien_config):
                os.makedirs(DOSSIER, exist_ok=True)
                shutil.copy2(ancien_config, FICHIER_CONFIG)
                reprise = True
                print("Reglages repris depuis", ANCIEN_DOSSIER)
    except Exception as e:
        print("Reprise des anciens reglages impossible :", e)

    # L'ancienne entree de demarrage relancerait l'ancien exe en parallele.
    try:
        ancienne = ancien_chemin_demarrage()
        if os.path.exists(ancienne):
            os.remove(ancienne)
    except Exception as e:
        print("Ancienne entree de demarrage non retiree :", e)

    try:
        if os.path.exists(ANCIEN_EXE):
            arreter_instances(ANCIEN_EXE)
    except Exception:
        pass
    return reprise


def installer_ou_mettre_a_jour():
    """Renvoie True si on a agi comme installeur et qu'il faut sortir."""
    moi = os.path.abspath(sys.executable)
    if os.path.normcase(moi) == os.path.normcase(CIBLE_EXE):
        return False                       # on EST l'application installee

    deja = os.path.exists(CIBLE_EXE)

    """
    UN EXE TELECHARGE EST UN LANCEUR, PAS UN INSTALLEUR PERIME.

    Le fichier qu'on garde sur le bureau vieillit : l'application se met a jour
    seule, et ce fichier-la reste a la version du jour ou on l'a telecharge.
    Il montrait alors une boite « une version plus recente est deja installee »
    a chaque double-clic — un reproche, pour un geste qui n'a rien de fautif —
    et un fichier de meme version se reinstallait par-dessus lui-meme, en
    annoncant une mise a jour qui n'en etait pas une.

    La regle tient en une ligne : ce qui n'apporte rien de neuf OUVRE
    simplement l'application installee. Le raccourci du bureau pointe donc
    toujours vers la derniere version, quel que soit son age.

    Et si elle tourne deja, le mutex renverrait cette copie sans un mot : on
    laisse d'abord le mot qui lui demande de se montrer.
    """
    installee = version_installee()
    if deja and installee and not plus_recente(VERSION, installee):
        demander_panneau()
        try:
            subprocess.Popen([CIBLE_EXE], close_fds=True)
        except Exception as e:
            print("Lancement de la version installee impossible :", e)
            dialogue(NOM_APP,
                     "Impossible de demarrer la version installee.\n\n%s\n\n%s"
                     % (CIBLE_EXE, e))
        else:
            print("Version installee %s ouverte (ce fichier est la %s)."
                  % (installee, VERSION))
        return True

    try:
        os.makedirs(DOSSIER, exist_ok=True)
        reprise = reprendre_ancienne_installation()
        arreter_instances(CIBLE_EXE)
        for essai in range(10):            # le fichier peut rester verrouille
            try:
                shutil.copy2(moi, CIBLE_EXE)
                break
            except PermissionError:
                time.sleep(0.6)
        else:
            dialogue(NOM_APP,
                     "Impossible de remplacer la version installee.\n"
                     "Quitte l'application depuis son icone, puis relance ce fichier.")
            return True

        installer_demarrage()
        installer_raccourci()
        installer_protocole()
        ecrire_version_installee()
        subprocess.Popen([CIBLE_EXE], close_fds=True)
        if deja:
            texte = (f"Mise a jour vers la version {VERSION} terminee.\n\n"
                     "Tes reglages ont ete conserves.")
        elif reprise:
            texte = (f"{NOM_APP} {VERSION} remplace Guirlande ambiante.\n\n"
                     "Tes reglages ont ete repris : guirlande appairee, "
                     "regles, preferences.\n\n"
                     f"Nouvel emplacement :\n{DOSSIER}\n\n"
                     "L'ancien dossier peut etre supprime a la main.")
        else:
            texte = (f"Installation terminee ({NOM_APP} {VERSION}).\n\n"
                     f"Installee dans :\n{DOSSIER}\n\n"
                     "Elle demarre avec Windows, et se met a jour seule.\n"
                     "Son icone est en bas a droite, pres de l'horloge.\n\n"
                     "Pour la relancer apres l'avoir quittee : tape "
                     "\"Machi Tool\" dans le menu Demarrer. Ton ancien "
                     "fichier telecharge n'est plus utile.")
        dialogue(NOM_APP, texte)
        return True
    except Exception as e:
        print("Installation impossible :", e)
        dialogue(NOM_APP, f"Installation impossible :\n{e}")
        return True


def deja_lance():
    """Empeche deux copies simultanees."""
    try:
        import win32event, win32api, winerror
        _mutex = win32event.CreateMutex(None, False, "MachiToolMutex")
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            return True
        globals()["_mutex_garde"] = _mutex   # garde une reference vivante
    except Exception:
        pass
    return False


# ==========================================================================

def image_icone(rgb):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), NUIT_RGB)
    d = ImageDraw.Draw(img)
    r, v, b = [max(30, int(c)) for c in rgb]
    for i, x in enumerate(range(9, 60, 11)):
        y = 26 + int(10 * math.sin(i * 1.1))
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(r, v, b))
    return img


def ecrire_icone(chemin):
    """Genere icone.ico pour la compilation."""
    from PIL import Image, ImageDraw
    grand = Image.new("RGB", (256, 256), NUIT_RGB)
    d = ImageDraw.Draw(grand)
    for i, x in enumerate(range(30, 240, 42)):
        y = 105 + int(42 * math.sin(i * 1.1))
        c = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(i / 5.5, 0.8, 1))
        d.ellipse([x - 24, y - 24, x + 24, y + 24], fill=c)
    grand.save(chemin, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Icone ecrite :", chemin)


def sans_faute(quoi, faire, *args, **kw):
    """Fait tourner une etape de demarrage sans qu'elle puisse tout emporter.

    RIEN DE CE QUI EST FACULTATIF NE DOIT EMPECHER L'ICONE DE PARAITRE. Elle
    porte « Quitter », « Installer la mise a jour » et l'acces au panneau :
    sans elle, une application qui tourne est une application qu'on ne peut ni
    arreter, ni reparer, ni mettre a jour. Une guirlande qui ne s'allume pas se
    voit et se rattrape ; un demarrage qui meurt en silence, non.
    """
    try:
        return faire(*args, **kw)
    except Exception as e:
        print("Demarrage — %s a echoue : %s" % (quoi, e))
        print(traceback.format_exc())
        return None


def lancer():
    global CFG
    if FIGE:
        sans_faute("marquage de version", ecrire_version_installee)
        sans_faute("schema machitool://", installer_protocole)
    sans_faute("identite de la barre", identite_barre_taches)
    sans_faute("mise a l'echelle", activer_dpi)
    CFG = sans_faute("lecture de la configuration", charger_config)
    if CFG is None:
        CFG = json.loads(json.dumps(CONFIG_DEFAUT))
    premiere_fois = not str(CFG.get("adresse", "")).strip()
    sans_faute("nettoyage des telechargements", nettoyer_maj)

    boucle = asyncio.new_event_loop()
    BLE["boucle"] = boucle
    sans_faute("ecoute de l'arret de Windows", surveiller_arret_windows)

    def fil_ble():
        asyncio.set_event_loop(boucle)
        try:
            boucle.run_until_complete(superviseur(CFG))
        except Exception as e:
            print("Fil Bluetooth arrete :", e)

    threading.Thread(target=fil_ble, daemon=True).start()
    sans_faute("serveur local", demarrer_api, CFG)
    if CFG.get("mode") == "son":
        sans_faute("capture du son", demarrer_audio, CFG)

    demande_ouverture = threading.Event()
    demande_arret = threading.Event()

    import pystray
    panneau = Panneau(CFG, lambda: demande_arret.set())

    # L'icone vit dans TRAY, pas dans une variable locale : elle peut etre
    # REPOSEE en cours de route (voir fil_icone), et tout ce qui la touche --
    # notifications, couleur, menu, arret -- doit trouver la nouvelle.
    TRAY["icone"] = pystray.Icon("machitool", image_icone(hex_vers_rgb(ACCENT_DEPART)), NOM_APP)

    # ---- mise a jour -------------------------------------------------
    # Tout passe par un fil separe : une requete reseau dans le fil de
    # tkinter figerait la fenetre, et dans celui de pystray le menu.

    def notifier(titre, texte):
        try:
            TRAY["icone"].notify(texte, titre)
        except Exception:
            print(titre, ":", texte)

    # Jarvis : ce qu'il peut demander au reste de l'application.
    JARVIS_CROCHETS["notifier"] = notifier
    JARVIS_CROCHETS["ouvrir_panneau"] = lambda: demande_ouverture.set()
    sans_faute("Jarvis", demarrer_jarvis, CFG)

    def basculer_jarvis(*_):
        CFG["jarvis_actif"] = not CFG.get("jarvis_actif", False)
        sauver_config(CFG)
        try:
            panneau.var_jarvis.set(CFG["jarvis_actif"])
        except Exception:
            pass

    def travail_maj(quoi):
        if quoi == "installer":
            if MAJ["etat"] != "prete":
                publication = verifier_maj(CFG)
                if not publication:
                    if MAJ["etat"] == "a_jour":
                        notifier(NOM_APP, MAJ["message"])
                    return
                try:
                    telecharger_maj(publication)
                except Exception as e:
                    MAJ["etat"] = "erreur"
                    MAJ["message"] = "Telechargement impossible : %s" % e
                    return
            """
            ON NE QUITTE PLUS D'ICI, ET C'EST TOUT LE CORRECTIF.

            Ce fil posait l'installeur puis tuait l'application, deux secondes
            apres une bulle de notification. Au demarrage de Windows, cette
            bulle n'arrive nulle part -- l'assistant de concentration l'avale a
            l'ouverture de session -- et quelqu'un qui cliquait l'icone a cet
            instant precis voyait sa fenetre s'ouvrir PUIS le processus mourir
            dessous. De l'exterieur, c'est un plantage, et c'est ce qui a ete
            rapporte. L'application faisait exactement ce qu'on lui avait
            demande, sans que rien ne le dise.

            La pose est donc DEMANDEE ici, et executee par la boucle de
            surveillance -- la seule qui sache si une fenetre est ouverte
            devant quelqu'un.
            """
            MAJ["etat"] = "a_poser"
            MAJ["demande_le"] = time.time()
            MAJ["message"] = ("Version %s prete a etre posee." % MAJ["version"])
            return

        publication = verifier_maj(CFG)
        if not publication:
            return
        if CFG.get("maj_installation_auto", True):
            travail_maj("installer")
        else:
            notifier(
                "Nouveau build detecte" if est_build(publication["version"])
                else "Mise a jour disponible",
                "%s. Clic droit sur l'icone pour l'installer."
                % publication["version"])

    verrou_maj = threading.Lock()

    def travail_maj_exclusif(quoi):
        """Un seul travail a la fois, quelle qu'en soit l'origine.

        Le menu de l'icone, le panneau et le fil de veille peuvent
        declencher en meme temps. Deux telechargements ecriraient le meme
        fichier .part : chacun verrait une taille complete, et l'exe
        entrelace serait renomme puis lance comme installeur.
        """
        if not verrou_maj.acquire(blocking=False):
            return
        try:
            travail_maj(quoi)
        finally:
            verrou_maj.release()

    def declencher_maj(quoi="verifier"):
        threading.Thread(target=travail_maj_exclusif, args=(quoi,),
                         daemon=True).start()

    def veille_maj():
        """Premiere verification peu apres le demarrage, puis a intervalle."""
        attente = 30.0
        while ETAT["en_marche"]:
            fin = time.time() + attente
            while ETAT["en_marche"] and time.time() < fin:
                time.sleep(2)
            if not ETAT["en_marche"]:
                return
            if FIGE and CFG.get("maj_verifier", True):
                travail_maj_exclusif("verifier")
            attente = max(1, int(CFG.get("maj_intervalle_heures", 6))) * 3600

    panneau.declencher_maj = declencher_maj
    threading.Thread(target=veille_maj, daemon=True).start()

    def veille_pont():
        """Va demander au site ce qu'il a en attente. Sans onglet ouvert,
        c'est le seul chemin : rien depuis Internet ne peut joindre cette
        machine."""
        attente = 45.0
        while ETAT["en_marche"]:
            fin = time.time() + attente
            while ETAT["en_marche"] and time.time() < fin:
                time.sleep(2)
            if not ETAT["en_marche"]:
                return
            if CFG.get("pont_releve", True):
                try:
                    relever_le_site(CFG)
                except Exception as e:
                    print("Releve du pont impossible :", e)
            attente = max(1, int(CFG.get("pont_intervalle", 3))) * 60

    threading.Thread(target=veille_pont, daemon=True).start()

    sans_faute("journal du poste", ouvrir_journal_du_poste, CFG)   # coucher perdu, demarrage, PUIS le fil

    assurer_demarrage(CFG)     # le raccourci de demarrage, repose s'il a disparu

    def veille_activite():
        # Premier tour a deux minutes : la session est posee, la premiere
        # touche a ferme le trou de reprise, le lever du jour est mesurable.
        # Les suivants au pas des reglages (six heures), le filet.
        attente = 120
        while ETAT["en_marche"]:
            fin = time.time() + attente
            attente = max(1, int(CFG.get("collecte_intervalle_heures", 6))) * 3600
            while ETAT["en_marche"] and time.time() < fin:
                # Le chien de garde passe toutes les trente secondes : si le fil
                # d'echantillonnage est mort, il repart. Une collecte arretee ne
                # se voit pas autrement qu'a un mois de journal vide.
                # Une seconde, pas cinq : c'est le delai entre un double-clic
                # sur l'exe et la fenetre qui parait. Cinq secondes de rien,
                # apres un clic, se lisent comme « ca ne marche pas ».
                time.sleep(1)
                if relever_demande_panneau():
                    demande_ouverture.set()
                if relever_demande_synchro():
                    print("Synchro demandee par machitool://sync : envoi.")
                    synchroniser_activite(CFG, minimum=0)
                if int(time.time()) % 30 < 1:
                    try:
                        veiller_sur_activite(CFG)
                    except Exception as e:
                        print("Chien de garde :", e)
            if not ETAT["en_marche"]:
                return
            if ACTIVITE["active"]:
                try:
                    if CFG.get("collecte_envoi", False):
                        envoyer_activite_au_site(CFG)
                    else:
                        sauver_activite()
                except Exception as e:
                    print("Veille d'activite :", e)

    threading.Thread(target=veille_activite, daemon=True).start()

    def libelle_maj(*_):
        quoi = "le build" if est_build(MAJ["version"]) else "la version"
        if MAJ["etat"] == "prete":
            return "Installer %s %s" % (quoi, MAJ["version"])
        if MAJ["etat"] == "disponible":
            return "Passer a %s %s" % (quoi, MAJ["version"])
        if MAJ["etat"] == "telechargement":
            return "Telechargement en cours..."
        if MAJ["etat"] == "verification":
            return "Verification en cours..."
        return "Rechercher une mise a jour"

    def construire_menu():
        return pystray.Menu(
        pystray.MenuItem("Ouvrir le panneau", lambda *_: demande_ouverture.set(), default=True),
        pystray.MenuItem("Pause", lambda *_: ETAT.update(pause=not ETAT["pause"]),
                         checked=lambda i: ETAT["pause"]),
        pystray.MenuItem("Reconnecter", lambda *_: ETAT.update(demande="reconnecter")),
        # Le micro de Jarvis, a un clic : couper l'ecoute ne doit jamais
        # demander d'ouvrir une fenetre.
        pystray.MenuItem("Jarvis ecoute", basculer_jarvis,
                         checked=lambda i: bool(CFG.get("jarvis_actif", False))),
        pystray.MenuItem("Agenda", lambda *_: JARVIS.__setitem__("montrer_agenda", time.time())),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(libelle_maj,
                         lambda *_: declencher_maj(
                             "installer" if MAJ["etat"] in ("disponible", "prete")
                             else "verifier"),
                         enabled=lambda *_: MAJ["etat"] not in ("verification",
                                                                "telechargement")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter",
                         lambda *_: (journaliser_arret("quitte depuis la barre"),
                                     demande_arret.set())),
        )

    TRAY["icone"].menu = construire_menu()

    def fil_icone():
        """L'icone, reposee tant que l'application tourne.

        Deux facons de la perdre sans que rien ne s'arrete : pystray rend la
        main SANS LEVER quand sa boucle de messages casse, et Windows retire
        toutes les icones quand l'Explorateur redemarre (TaskbarCreated, lu
        par la fenetre cachee). Dans les deux cas l'application tournait --
        elle eclairait, elle collectait -- mais n'avait plus d'icone, donc plus
        de menu, plus de « Quitter », plus de « Installer la mise a jour ».
        Ici, le fil ne meurt jamais : il repose une icone neuve et repart.
        """
        premiere = True
        while ETAT["en_marche"] and not demande_arret.is_set():
            if not premiere:
                time.sleep(3)
                if not ETAT["en_marche"] or demande_arret.is_set():
                    return
                TRAY["icone"] = pystray.Icon("machitool", image_icone(vu_a_l_oeil(ETAT["couleur"])), NOM_APP)
                TRAY["icone"].menu = construire_menu()
                print("Icone reposee dans la barre.")
            premiere = False
            try:
                TRAY["icone"].run()
            except Exception as e:
                print("Icone de la barre tombee :", e)

    threading.Thread(target=fil_icone, daemon=True).start()

    if premiere_fois:
        panneau.aller("appairage")
        panneau.afficher()
    else:
        panneau.root.withdraw()

    dernier = [0.0]
    dernier_etat_maj = [MAJ["etat"]]

    def surveiller():
        if demande_arret.is_set():
            ETAT["en_marche"] = False
            if CFG.get("eteindre_en_partant", True):
                eteindre_guirlande()
            arreter_activite()
            arreter_api()
            arreter_audio()
            arreter_oreille()
            # Un StretchBlt en vol retarderait la fermeture : l'interpreteur
            # joint les fils de ce pool en sortant.
            EXECUTEUR_CAPTURE.shutdown(wait=False)
            try:
                TRAY["icone"].stop()
            except Exception:
                pass
            panneau.root.destroy()
            return
        if TRAY.get("reposer"):
            # La barre a ete recreee : on arrete l'icone en place, et fil_icone
            # en repose une neuve des que run() a rendu la main.
            TRAY["reposer"] = False
            try:
                TRAY["icone"].stop()
            except Exception:
                pass
        if demande_ouverture.is_set():
            demande_ouverture.clear()
            panneau.afficher()
        """
        LA POSE D'UNE MISE A JOUR ATTEND QUE LA FENETRE SOIT REFERMEE.

        Poser une version tue cette instance : la fenetre se ferme, le
        processus meurt, et l'exe telecharge relance l'application quelques
        secondes plus tard. C'est correct quand personne ne regarde ; c'est
        indiscernable d'un plantage quand quelqu'un vient d'ouvrir le panneau.

        La regle est donc simple : tant que la fenetre est VISIBLE, on ne pose
        rien, et le panneau dit ce qui attend. Des qu'elle est refermee -- ou
        tout de suite si elle ne l'etait pas -- la pose part, apres avoir ecrit
        dans le journal POURQUOI l'application s'arrete. Sans cette ligne, un
        redemarrage pour mise a jour et un plantage laissent la meme trace :
        aucune.
        """
        if poser_la_maj(panneau.interface_visible()):
            if lancer_installeur_maj():
                # La trace APRES le depart de l'installeur, pas avant : un
                # « ARRET » ecrit pour un arret qui n'a pas eu lieu rendrait le
                # journal moins fiable que pas de journal du tout.
                journaliser_arret("mise a jour vers %s" % MAJ["version"])
                demande_arret.set()
            else:
                # L'installeur n'est pas parti : on ne quitte surtout pas, et le
                # message d'erreur pose par `lancer_installeur_maj` reste a
                # l'ecran. Il a aussi bascule l'etat en « erreur », donc on ne
                # reessaie pas toutes les cent cinquante millisecondes.
                MAJ["differee"] = False
        if time.time() - dernier[0] > 2.0:
            dernier[0] = time.time()
            try:
                TRAY["icone"].icon = image_icone(vu_a_l_oeil(ETAT["couleur"]))
            except Exception:
                pass
        if ETAT.get("rappel_neuf") and PONT["rappels"]:
            ETAT["rappel_neuf"] = False
            if CFG.get("pont_notifie", True):
                dernier_rappel = PONT["rappels"][0]
                notifier(dernier_rappel["titre"], dernier_rappel["texte"])
        if MAJ["etat"] != dernier_etat_maj[0]:
            dernier_etat_maj[0] = MAJ["etat"]
            try:
                TRAY["icone"].update_menu()
            except Exception:
                pass
        panneau.root.after(150, surveiller)

    panneau.root.after(150, surveiller)
    panneau.root.mainloop()


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    # AVANT TOUTE FENETRE, y compris celles de l'installeur : Windows fige la
    # finesse au premier affichage, et « Installation terminee » sur un 4K
    # suffisait a la poser de travers pour la suite.
    activer_dpi()
    if "--verifier-maj" in sys.argv:
        cfg = charger_config()
        verifier_maj(cfg)
        print(MAJ["message"])
        return
    if "--icone" in sys.argv:
        ecrire_icone(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone.ico"))
        return
    if "--lanceur" in sys.argv:
        creer_lanceur()
        installer_demarrage()
        print("Lanceur cree et entree de demarrage installee.")
        return
    if "--retirer" in sys.argv:
        retirer_demarrage()
        print("Retire du demarrage.")
        return

    # Le site ouvre machitool://sync pour reveiller l'application. Windows
    # lance alors « MachiTool.exe machitool://sync » : si elle tourne deja, le
    # mutex renvoie cette seconde copie -- on lui laisse d'abord un mot, que
    # la premiere lit dans les cinq secondes et honore en envoyant la journee.
    # Si elle ne tournait pas, le mot est lu par celle qui demarre.
    lien = next((a for a in sys.argv[1:] if a.startswith("machitool://")), None)
    if lien:
        deposer_demande_synchro("lien")
    if FIGE:
        if installer_ou_mettre_a_jour():
            return
        if deja_lance():
            return
    lancer()


def poser_la_maj(fenetre_visible):
    """Faut-il poser la mise a jour maintenant ? Et sinon, le dire.

    POSER UNE VERSION TUE CETTE INSTANCE. La fenetre se ferme, le processus
    meurt, et l'exe telecharge relance l'application quelques secondes plus
    tard. C'est correct quand personne ne regarde ; c'est indiscernable d'un
    plantage quand quelqu'un vient d'ouvrir le panneau -- et c'est exactement ce
    qui a ete rapporte : « la fenetre s'est ouverte puis l'app s'est eteinte
    toute seule, sans rien afficher ».

    Tant que la fenetre est VISIBLE, on ne pose donc rien, et `differee` dit au
    panneau d'expliquer ce qui attend. Une fenetre reduite ou rangee dans la
    barre ne compte pas comme visible : personne ne la regarde.
    """
    if MAJ["etat"] != "a_poser":
        MAJ["differee"] = False
        return False
    MAJ["differee"] = bool(fenetre_visible)
    return not fenetre_visible


def journaliser_arret(pourquoi):
    """Pourquoi l'application s'arrete, ecrit avant qu'elle ne le fasse.

    Un redemarrage pour mise a jour et un plantage laissaient la meme trace :
    aucune. Vu de l'exterieur les deux se ressemblent -- la fenetre disparait
    -- et sans cette ligne il n'y a rien pour les departager le lendemain.
    """
    try:
        with open(FICHIER_JOURNAL, "a", encoding="utf-8") as f:
            f.write("--- ARRET %s v%s : %s ---\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, pourquoi))
    except Exception:
        pass
    print("Arret :", pourquoi)


def ouvrir_dans_l_explorateur(chemin):
    """Ouvre un fichier ou un dossier avec ce que le systeme propose.

    Rend None si ca a marche, sinon la raison -- l'appelant l'affiche. Une
    ouverture qui echoue en silence laisse quelqu'un cliquer trois fois avant
    de comprendre qu'il ne se passera rien.
    """
    try:
        if not os.path.exists(chemin):
            return "rien a cet endroit pour l'instant"
        if os.name == "nt":
            os.startfile(chemin)                       # noqa: S606 -- chemin a nous
        else:
            subprocess.Popen(["xdg-open", chemin], close_fds=True)
        return None
    except Exception as e:
        return str(e)[:120]


def journal_pour_partage(destination=None):
    """Une COPIE du journal, datee, posee la ou on peut la retrouver.

    POURQUOI UNE COPIE ET PAS LE FICHIER LUI-MEME. Le journal est ouvert en
    ecriture pendant toute la vie du processus : l'envoyer tel quel, c'est
    envoyer un fichier qui bouge encore, et sous Windows certains outils
    refusent de le lire pendant qu'il est tenu. La copie est figee, elle porte
    sa date dans son nom, et elle atterrit sur le Bureau -- l'endroit d'ou on
    glisse un fichier dans une conversation sans avoir a le chercher.

    Le journal precedent (journal.log.1, garde a la rotation) part avec quand
    il existe : une panne qui s'est produite avant le dernier demarrage n'est
    plus dans le fichier courant, et c'est justement celle qu'on cherche.
    """
    import shutil
    dossier = destination or os.path.join(
        os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop"))
    if not os.path.isdir(dossier):
        dossier = os.path.expanduser("~")
    quand = time.strftime("%Y%m%d-%H%M")
    poses = []
    for source, suffixe in ((FICHIER_JOURNAL, ""), (FICHIER_JOURNAL + ".1", "-precedent")):
        if not os.path.exists(source):
            continue
        cible = os.path.join(dossier, "machitool-journal-%s%s.log" % (quand, suffixe))
        try:
            shutil.copyfile(source, cible)
            poses.append(cible)
        except Exception as e:
            return None, str(e)[:120]
    if not poses:
        return None, "le journal est vide pour l'instant"
    return poses, None


def rapporter_plantage(e):
    """Un demarrage qui echoue ne doit pas disparaitre en silence.

    Sans console, une exception non rattrapee tue le processus sans un mot :
    l'icone ne parait jamais, rien ne s'ouvre, et il ne reste rien a montrer
    a personne. C'est exactement ce qu'on voit de l'exterieur -- « ca plante
    quand je l'ouvre » -- et c'est la seule chose qu'on ne peut pas
    diagnostiquer.

    On ecrit donc la trace complete dans le journal, et on la MONTRE : la
    premiere ligne de l'erreur, et le chemin du fichier a envoyer.
    """
    trace = traceback.format_exc()
    try:
        with open(FICHIER_JOURNAL, "a", encoding="utf-8") as f:
            f.write("\n--- PLANTAGE AU DEMARRAGE %s v%s ---\n%s\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), VERSION, trace))
    except Exception:
        pass
    print(trace)
    dialogue(NOM_APP,
             "%s %s n'a pas pu demarrer.\n\n%s : %s\n\n"
             "Le detail est dans :\n%s\n\n"
             "Si ca se reproduit, envoie ce fichier."
             % (NOM_APP, VERSION, type(e).__name__, str(e)[:200], FICHIER_JOURNAL))


if __name__ == "__main__":
    # Le processus du moteur de dictee : ni icone, ni installation, ni verrou
    # d'instance unique — il attend un son et rend un texte, rien d'autre.
    if DICTEE_ENFANT_ARG in sys.argv:
        _i = sys.argv.index(DICTEE_ENFANT_ARG)
        moteur_dictee_enfant(sys.argv[_i + 1], sys.argv[_i + 2])
        sys.exit(0)
    # Le processus de l'oreille de Jarvis : le micro, le mot d'eveil, rien d'autre.
    if JARVIS_ENFANT_ARG in sys.argv:
        oreille_enfant_depuis_argv()
        sys.exit(0)
    # Le processus de sa voix : la voix chargee, des phrases a dire.
    if VOIX_ENFANT_ARG in sys.argv:
        _i = sys.argv.index(VOIX_ENFANT_ARG)
        _jv.voix_enfant(sys.argv[_i + 1], sys.argv[_i + 2])
        sys.exit(0)
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:                 # noqa: BLE001 - dernier filet
        rapporter_plantage(e)
        sys.exit(1)
