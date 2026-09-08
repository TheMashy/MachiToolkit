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
import sys
import os
import json
import time
import math
import shutil
import secrets
import colorsys
import threading
import traceback
import subprocess
import http.server
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.22.0"

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
try:
    if sys.stdout is None or not hasattr(sys.stdout, "write"):
        _j = open(FICHIER_JOURNAL, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = _j
        print(f"\n--- demarrage {time.strftime('%Y-%m-%d %H:%M:%S')} v{VERSION} ---")
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
    "collecte_titres_complets": False,   # garder le titre entier des fenetres
    "collecte_envoi": False,             # pousser le digest au site
    "collecte_intervalle_heures": 6,

    # Mises a jour depuis les publications GitHub du depot.
    "config_version": 3,              # sert aux migrations, voir charger_config
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

ACCENT_DEPART = "#B79CF5"   # accent au repos, avant la premiere couleur


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
    cfg["config_version"] = 3
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
    "themes": {},         # secondes par thematique de ce qu'on regardait
    "theme_courant": None,
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

ET LE TITRE NE QUITTE JAMAIS LA MACHINE. C'est ici, en local, que le theme est
calcule ; seul le theme part au site. Le nom de la video, le canal, le pseudo
de la personne d'en face restent sur le poste -- c'est la meme regle que pour
`categorie_activite` depuis le debut, et l'ajout des thematiques ne la desserre
pas d'un cran.
"""
THEMES_ACTIVITE = [
    ("dev",      ("github", "stack overflow", "stackoverflow", " npm", "pypi", "documentation",
                  "docs.", "localhost", "pull request", "commit", "python", "javascript", "api ")),
    ("jeu",      ("gameplay", "speedrun", "let's play", "lets play", "walkthrough", "no commentary",
                  "steam", "twitch", "minecraft", "fortnite", "valorant", "league of legends",
                  "elden ring", "boss fight", "modded", "playthrough")),
    ("rp",       ("roleplay", "role play", " rp ", "jdr", "dungeons", "donjons", "dnd", "d&d",
                  "campagne", "one shot rp")),
    ("urbex",    ("urbex", "abandoned", "abandonne", "abandonné", "exploration urbaine",
                  "lieu abandonne", "lost place", "derelict")),
    ("conflit",  ("war footage", "combat footage", "frontline", "ukraine", "gaza", "guerre",
                  "drone strike", "bodycam", "conflit arme")),
    ("actu",     ("actualite", "actualité", "info", "le monde", "bfm", "france info", "news",
                  "reportage", "journal televise")),
    ("musique",  ("spotify", "soundcloud", "bandcamp", "playlist", "album", " ost", "official video",
                  "live session", "concert", "remix", "lofi")),
    ("creation", ("artstation", "deviantart", "blender", "photoshop", "after effects", "davinci",
                  "tutorial", "tuto", "speedpaint", "timelapse", "fl studio")),
    ("achat",    ("amazon", "leboncoin", "aliexpress", "panier", "checkout", "commande",
                  "livraison", "prix")),
    ("argent",   ("paypal", "banque", "assurance", "impots", "impôts", "coinbase", "binance",
                  "virement", "facture")),
    ("social",   ("discord", "reddit", "instagram", "tiktok", "facebook", "twitter", "x.com",
                  "linkedin", "snapchat", "messages")),
    ("video",    ("youtube", "netflix", "disney+", "prime video", "twitch", "vimeo", "dailymotion",
                  "episode", "épisode", "saison", "film complet")),
]


def theme_activite(contexte):
    """La thematique de ce qu'on regarde, ou None quand rien ne correspond."""
    contexte = (contexte or "").strip().lower()
    if not contexte:
        return None
    proc, _, titre = contexte.partition("|")
    # Le titre entier, pas seulement le site : c'est lui qui porte le sujet.
    plein = " " + " ".join((_titre_onglet(titre) + " " + proc.strip()).split()) + " "
    for nom, mots in THEMES_ACTIVITE:
        for mot in mots:
            if mot in plein:
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
                    temps={}, titres={}, themes={}, bascules=0,
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
    if avant:
        ecoule = min(max(0.0, maintenant - ACTIVITE["depuis"]), 180.0)
        ACTIVITE["temps"][avant] = ACTIVITE["temps"].get(avant, 0.0) + ecoule
        if theme_avant:
            ACTIVITE.setdefault("themes", {})
            ACTIVITE["themes"][theme_avant] = ACTIVITE["themes"].get(theme_avant, 0.0) + ecoule
        if actif:
            ACTIVITE["actif_s"] += ecoule
        if titres_complets and ACTIVITE["titre_courant"]:
            par_titre = ACTIVITE["titres"].setdefault(avant, {})
            t = ACTIVITE["titre_courant"][:80]
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
    if ACTIVITE["titres"]:
        resume["titres"] = {cat: {t: round(s) for t, s in d.items()}
                            for cat, d in ACTIVITE["titres"].items()}
    themes = {k: round(v) for k, v in sorted(
        (ACTIVITE.get("themes") or {}).items(), key=lambda kv: -kv[1]) if v >= 1}
    if themes:
        resume["temps_par_theme_s"] = themes
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
        fenetre = dc_ecran = None
        try:
            fenetre = win32gui.GetDesktopWindow()
            dc_ecran = win32gui.GetWindowDC(fenetre)
            source = win32ui.CreateDCFromHandle(dc_ecran)
            memoire = source.CreateCompatibleDC()
            image = win32ui.CreateBitmap()
            image.CreateCompatibleBitmap(source, colonnes, lignes)
            memoire.SelectObject(image)
            garde = {"fenetre": fenetre, "dc": dc_ecran, "source": source,
                     "memoire": memoire, "image": image,
                     "taille": (colonnes, lignes)}
            _local.gdi = garde
        except Exception as e:
            # Le contexte a pu etre obtenu avant l'echec. Sans cette
            # liberation il fuit, et comme le cache reste vide la capture
            # suivante recommence : un contexte perdu par image, jusqu'a
            # epuisement du quota GDI du processus.
            if dc_ecran:
                try:
                    win32gui.ReleaseDC(fenetre, dc_ecran)
                except Exception:
                    pass
            print("Capture GDI indisponible :", e)
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
        print("Capture GDI perdue :", e)
        _liberer_gdi(garde)
        _local.gdi = None
        return None

    # GetBitmapBits rend du BGRA, ligne par ligne.
    return [(octets[i + 2], octets[i + 1], octets[i])
            for i in range(0, len(octets), 4)]


def _liberer_gdi(garde):
    try:
        garde["memoire"].DeleteDC()
    except Exception:
        pass
    try:
        import win32gui
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
        print("Capture ecran impossible :", e)
        return None


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

    # ---------- routes ----------

    def do_GET(self):
        chemin = self.path.split("?")[0].rstrip("/") or "/"
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
        if not self.origine_permise():
            return self.repondre(403, {"erreur": "origine non autorisee"})
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

                if mode == "son":
                    if AUDIO["actif"]:
                        (rc, vc, bc), gain = couleur_son(cfg, (ra, va, ba))
                        nom = "Son \u00b7 " + cfg.get("son_bande", "graves")
                        douceur = 1.0      # l'enveloppe est deja faite cote audio
                    else:
                        nom = "Son indisponible"

                if mode in ("ecran", "mixte"):
                    resultat = await boucle.run_in_executor(
                        None, couleur_ecran,
                        cfg.get("ecran_source", "actif"),
                        float(cfg.get("ecran_saturation", 1.5)),
                        int(cfg.get("ecran_finesse", 4)))
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

                inactif = secondes_inactivite() > float(cfg.get("veille_minutes", 6)) * 60
                if inactif:
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
            await une_session(cfg)
            for _ in range(100):
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
#  Direction : la fenetre porte la lumiere de l'objet qu'elle pilote.
#  Un brin d'ampoules vivant tient l'en-tete et donne son accent au reste
#  de l'interface — onglet actif, bouton principal, liseres. Tout le reste
#  reste sourd pour que le brin soit la seule chose qui brille.
# ==========================================================================

NUIT    = "#140E1C"   # fond, presque noir violace
VELOURS = "#1E1530"   # panneaux
ENCRE   = "#191024"   # champs et creux
FIL     = "#3B2A55"   # filets, comme le cable de la guirlande
CRAIE   = "#EDE4F2"   # texte
BRUME   = "#9683AA"   # texte secondaire
VIF     = "#5CE6A4"   # connecte
ALERTE  = "#FF8A6B"   # deconnecte

NUIT_RGB = hex_vers_rgb(NUIT)

# Le rail suit l'idee du toolkit : l'accueil en haut, puis les pages du
# module ouvert. Une entree ("", "Titre") est un intitule de groupe, pas
# une page — c'est ce qui fera la separation le jour ou un deuxieme
# module viendra s'ajouter sous le premier.
# Le rail portait neuf entrees a plat. Il en porte quatre, dont trois se
# deplient : on voit d'abord de quoi il s'agit, le detail vient si on le
# demande. Le groupe de la page ouverte se deplie tout seul.
MENU = [
    ("page", "accueil", "Accueil", "\u2302", None),
    ("groupe", "lampe", "Lampe", "\u2600", [
        ("etat",      "Etat",      "\u25cf"),   # \u25cf
        ("ecran",     "Ecran",     "\u25ad"),   # \u25ad
        ("son",       "Son",       "\u266a"),   # \u266a
        ("appairage", "Appairage", "\u21c4"),   # \u21c4
    ]),
    ("groupe", "pont", "BrainDebugger", "\u25c9", [
        ("passerelle", "Passerelle",      "\u25c8"),   # \u25c8
        ("activite",   "Quantified Self", "\u25a4"),   # \u25a4
    ]),
    ("groupe", "app", "Application", "\u2699", [
        ("reglages", "Reglages",     "\u2630"),   # \u2630
        ("maj",      "Mises a jour", "\u21bb"),   # \u21bb
    ]),
]

# Ou se range chaque page, pour deplier le bon groupe en y arrivant.
GROUPE_DE = {}
for _e in MENU:
    if _e[0] == "groupe":
        for _entree in _e[4]:
            GROUPE_DE[_entree[0]] = _e[1]

# Page sans entree dans le rail : on y arrive depuis le mode Regles de la
# page Ecran, ou depuis l'appairage d'une fenetre. Elle appartient quand
# meme au module Lampe, pour que le bandeau la coiffe aussi.
GROUPE_DE["regles"] = "lampe"


def melange(avant, arriere, part):
    """Simule une transparence : tkinter ne connait pas le canal alpha."""
    return rgb_vers_hex(tuple(avant[i] * part + arriere[i] * (1 - part) for i in range(3)))


def lisible(rgb):
    """Remonte la valeur d'une couleur trop sombre pour servir d'accent."""
    h, s, v = colorsys.rgb_to_hsv(*[c / 255 for c in rgb])
    r, g, b = colorsys.hsv_to_rgb(h, s, max(0.72, v))
    return rgb_vers_hex((r * 255, g * 255, b * 255))


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

        self.rail = tk.Frame(corps, bg=NUIT, width=self.px(152))
        self.rail.pack(side="left", fill="y")
        self.rail.pack_propagate(False)
        self.construire_rail()

        tk.Frame(corps, bg=FIL, width=1).pack(side="left", fill="y")

        self.zone = tk.Frame(corps, bg=NUIT)
        self.zone.pack(side="left", fill="both", expand=True)
        self.construire_bandeau()
        self.construire_bandeau_pont()

        self.page_accueil()
        self.page_etat()
        self.page_regles()
        self.page_ecran()
        self.page_son()
        self.page_reglages()
        self.page_maj()
        self.page_passerelle()
        self.page_calendrier()
        self.page_moi()
        self.page_activite()
        self.page_appairage()
        self.aller(self.section if self.section in self.pages else "accueil")

        self.animer()
        self.rafraichir()

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
    #  Signature : le brin d'ampoules
    # ------------------------------------------------------------------

    def construire_entete(self):
        tk = self.tk
        bande = tk.Frame(self.root, bg=NUIT)
        bande.pack(fill="x")

        self.brin = tk.Canvas(bande, height=self.px(104), bg=NUIT, highlightthickness=0)
        self.brin.pack(fill="x")
        self.n_bulbes = 26
        self.cable = self.brin.create_line(0, 0, 0, 0, fill=FIL, width=1, smooth=True)
        self.bulbes = []
        for _ in range(self.n_bulbes):
            halos = [self.brin.create_oval(0, 0, 0, 0, outline="", fill=NUIT)
                     for _ in (19, 13, 8)]
            coeur = self.brin.create_oval(0, 0, 0, 0, outline="", fill=NUIT)
            self.bulbes.append([halos, coeur, 0.0, 0.0])
        self.brin.bind("<Configure>", lambda e: self.placer_bulbes(e.width))

        ligne = tk.Frame(self.root, bg=NUIT, padx=22)
        ligne.pack(fill="x", pady=(0, 12))
        self.txt_titre = tk.Label(ligne, text="M A C H I   T O O L", bg=NUIT, fg=CRAIE,
                                  font=(self.f_titre, 19), anchor="w")
        self.txt_titre.pack(side="left")
        self.txt_trame = tk.Label(ligne, text="", bg=NUIT, fg=BRUME,
                                  font=(self.f_mono, 9), anchor="e")
        self.txt_trame.pack(side="right")
        self.txt_statut = tk.Label(ligne, text="", bg=NUIT, fg=BRUME,
                                   font=(self.f_ui, 9), anchor="w")
        self.txt_statut.pack(side="left", padx=(14, 0))

        tk.Frame(self.root, bg=FIL, height=1).pack(fill="x")

    def placer_bulbes(self, largeur):
        marge, creux = self.px(30), self.px(21)
        pas = (largeur - 2 * marge) / max(1, self.n_bulbes - 1)
        points = []
        rayons = [self.px(19), self.px(13), self.px(8)]
        coeur = self.px(34) / 10.0
        for i, bulbe in enumerate(self.bulbes):
            x = marge + i * pas
            y = self.px(47) + math.sin(i / (self.n_bulbes - 1) * math.pi) * creux
            bulbe[2], bulbe[3] = x, y
            points += [x, y]
            for r, h in zip(rayons, bulbe[0]):
                self.brin.coords(h, x - r, y - r, x + r, y + r)
            self.brin.coords(bulbe[1], x - coeur, y - coeur, x + coeur, y + coeur)
        if len(points) >= 4:
            self.brin.coords(self.cable, *points)

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
        couleur = ETAT["couleur"]
        vive = hex_vers_rgb(self.accent)
        eteinte = max(couleur) < 6
        for i, (halos, coeur, _, _) in enumerate(self.bulbes):
            if not ETAT["connecte"]:
                force = 0.10 + 0.06 * math.sin(self.phase * 0.5 + i * 0.4)
                teinte = (90, 74, 110)
            else:
                onde = math.sin(self.phase * 0.7 - i * 0.26)
                force = 0.74 + 0.26 * onde
                teinte = vive if eteinte else couleur
            for part, h in zip((0.14, 0.28, 0.48), halos):
                self.brin.itemconfig(h, fill=melange(teinte, NUIT_RGB, part * force))
            self.brin.itemconfig(coeur, fill=melange(teinte, NUIT_RGB,
                                                     min(1.0, 0.4 + 0.6 * force)))
        self.peindre_vumetre()
        self.root.after(70, lambda: g == self.generation and self.animer())

    # ------------------------------------------------------------------
    #  Rail de navigation
    # ------------------------------------------------------------------

    def construire_rail(self):
        tk = self.tk
        tk.Frame(self.rail, bg=NUIT, height=self.px(10)).pack()
        self.entetes = {}      # cle de groupe -> (rang, etiquette, cadre)

        for genre, cle, libelle, icone, enfants in MENU:
            if genre == "page":
                self.rang_page(self.rail, cle, libelle, retrait=0, icone=icone)
                continue

            rang = tk.Frame(self.rail, bg=NUIT, cursor="hand2")
            rang.pack(fill="x")
            marque = tk.Label(rang, text=icone, bg=NUIT, fg=CRAIE,
                              font=(self.f_icone, 12), width=2)
            marque.pack(side="left", padx=(self.px(8), 0))
            etiq = tk.Label(rang, text=libelle, bg=NUIT, fg=CRAIE,
                            anchor="w", font=(self.f_ui, 10, "bold"),
                            padx=self.px(4), pady=self.px(9))
            etiq.pack(side="left", fill="x", expand=True)
            fleche = tk.Label(rang, text="\u203a", bg=NUIT, fg=BRUME,
                              font=(self.f_ui, 11), padx=10)
            fleche.pack(side="right")

            cadre = tk.Frame(self.rail, bg=NUIT)
            for sous_cle, sous_libelle, sous_icone in enfants:
                self.rang_page(cadre, sous_cle, sous_libelle, retrait=1,
                               icone=sous_icone)

            for w in (rang, etiq, fleche, marque):
                w.bind("<Button-1>", lambda e, g=cle: self.basculer_groupe(g))
                w.bind("<Enter>", lambda e, r=rang, l=etiq, f=fleche, m=marque:
                       [x.configure(bg=VELOURS) for x in (r, l, f, m)])
                w.bind("<Leave>", lambda e, r=rang, l=etiq, f=fleche, m=marque:
                       [x.configure(bg=NUIT) for x in (r, l, f, m)])
            self.entetes[cle] = (rang, etiq, fleche, cadre)

        for cle in self.entetes:
            self.poser_groupe(cle)

        # Pastille « mise a jour disponible » sur le groupe Application : visible
        # meme quand le groupe est replie, elle s'allume des qu'une version ou un
        # build attend, et mene a la page Mises a jour. rafraichir la pilote.
        rang_app = self.entetes["app"][0]
        self.badge_maj = self.tk.Label(rang_app, text="●", bg=NUIT, fg=VIF,
                                       font=(self.f_ui, 10), cursor="hand2")
        self.badge_maj.bind("<Button-1>", lambda e: self.aller("maj"))
        # non posee par defaut ; rafraichir la montre quand une maj attend

    def rang_page(self, parent, cle, libelle, retrait=0, icone=None):
        """Une ligne cliquable menant a une page."""
        tk = self.tk
        rang = tk.Frame(parent, bg=NUIT, cursor="hand2")
        rang.pack(fill="x")
        barre = tk.Frame(rang, bg=NUIT, width=self.px(3))
        barre.pack(side="left", fill="y")
        if icone:
            tk.Label(rang, text=icone, bg=NUIT, fg=BRUME,
                     font=(self.f_icone, 12), width=2).pack(
                         side="left", padx=(self.px(5), 0))
        etiq = tk.Label(rang, text=libelle, bg=NUIT, fg=BRUME, anchor="w",
                        font=(self.f_ui, 10),
                        padx=self.px(4 if icone else 14 + 12 * retrait),
                        pady=self.px(7))
        etiq.pack(side="left", fill="x", expand=True)
        for w in (rang, etiq):
            w.bind("<Button-1>", lambda e, c=cle: self.aller(c))
            w.bind("<Enter>", lambda e, r=rang, l=etiq, c=cle:
                   self.survol(r, l, c, True))
            w.bind("<Leave>", lambda e, r=rang, l=etiq, c=cle:
                   self.survol(r, l, c, False))
        self.onglets[cle] = (rang, barre, etiq)
        return rang

    def basculer_groupe(self, cle):
        self.groupes[cle] = not self.groupes.get(cle, False)
        self.poser_groupe(cle)

    def poser_groupe(self, cle):
        rang, etiq, fleche, cadre = self.entetes[cle]
        ouvert = self.groupes.get(cle, False)
        fleche.configure(text="\u2039" if ouvert else "\u203a")
        if ouvert:
            cadre.pack(fill="x", after=rang)
        else:
            cadre.pack_forget()

    def survol(self, rang, etiq, cle, dedans):
        if cle == self.section:
            return
        fond = VELOURS if dedans else NUIT
        rang.configure(bg=fond)
        etiq.configure(bg=fond, fg=CRAIE if dedans else BRUME)

    def aller(self, cle):
        self.section = cle
        # Arriver sur une page par un autre chemin que le rail — l'accueil,
        # une notification — doit deplier le groupe qui la contient.
        groupe = GROUPE_DE.get(cle)
        if groupe and not self.groupes.get(groupe):
            self.groupes[groupe] = True
            self.poser_groupe(groupe)
        for c, (rang, barre, etiq) in self.onglets.items():
            actif = c == cle
            fond = VELOURS if actif else NUIT
            rang.configure(bg=fond)
            etiq.configure(bg=fond, fg=CRAIE if actif else BRUME,
                           font=(self.f_ui, 10, "bold" if actif else "normal"))
            barre.configure(bg=self.accent if actif else fond)
        for c, page in self.pages.items():
            page.pack_forget()
        # Le bandeau ne concerne que la lampe, et doit rester au-dessus.
        self.bandeau.pack_forget()
        self.bandeau_pont.pack_forget()
        if GROUPE_DE.get(cle) == "lampe":
            self.bandeau.pack(fill="x")
        elif cle in ("calendrier", "moi"):
            self.bandeau_pont.pack(fill="x")
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
            fg=("#140E1C" if principal else CRAIE),
            activebackground=(self.accent if principal else FIL),
            activeforeground=("#140E1C" if principal else CRAIE),
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
        return self.tk.Label(parent, text=txt, bg=parent["bg"], fg=couleur,
                             font=(self.f_ui, taille, "bold" if gras else "normal"),
                             anchor="w", justify="left", wraplength=self.px(largeur))

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

        self.bande = tk.Canvas(self.bandeau, height=self.px(22), bg=ENCRE,
                               highlightthickness=0)
        self.bande.pack(fill="x", pady=(self.px(8), 0))

        # Reconnecter ne concerne que la guirlande : il n'avait rien a
        # faire dans le pied, ou il suivait jusqu'aux pages du site.
        self.bouton(self.bandeau, "Reconnecter", self.reconnecter,
                    compact=True).pack(anchor="w", pady=(self.px(8), 0))
        self.historique = []
        self.traits = []

    def construire_bandeau_pont(self):
        """Relever et ouvrir le site valaient pour Calendrier comme pour
        Moi : les repeter sur chaque page en faisait quatre boutons pour
        deux actions. Ils coiffent le groupe, comme l'etat coiffe la
        lampe."""
        tk = self.tk
        self.bandeau_pont = tk.Frame(self.zone, bg=NUIT, padx=self.px(24),
                                     pady=self.px(14))
        barre = tk.Frame(self.bandeau_pont, bg=NUIT)
        barre.pack(fill="x")
        self.bouton(barre, "Relever", self.relever_pont,
                    compact=True).pack(side="left")
        self.bouton(barre, "Ouvrir le site", self.ouvrir_site,
                    compact=True).pack(side="left", padx=self.px(8))
        self.btn_lu = self.bouton(barre, "Tout marquer comme lu",
                                  self.vider_rappels, compact=True)
        self.txt_pont = tk.Label(self.bandeau_pont, text="", bg=NUIT, fg=BRUME,
                                 font=(self.f_ui, 9), anchor="w",
                                 justify="left", wraplength=self.px(520))
        self.txt_pont.pack(fill="x", pady=(self.px(8), 0))

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
        teinte = ETAT["couleur"] if vif else hex_vers_rgb(self.accent)
        sourd = (110, 92, 132)
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
                          fill=melange((190, 175, 205), arriere, 0.5), width=e(3))
        c.create_arc(e(39), e(92), e(57), e(102), start=180, extent=180,
                     outline="", fill=melange((190, 175, 205), arriere, 0.4))

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
        f = self.nouvelle_page("ecran", defilante=True)

        self.texte(f, "Le controleur n'accepte qu'une seule couleur pour tout le brin : "
                      "le gauche bleu et le droit vert sont impossibles. En revanche "
                      "l'ecran choisi pilote l'ensemble.", BRUME, 8, largeur=490).pack(fill="x")

        self.separateur(f, 14, 10)
        self.titre(f, "mode").pack(fill="x", pady=(0, 4))
        self.var_mode = tk.StringVar(value=self.cfg.get("mode", "applications"))
        self.radio(f, "Regles — couleur fixe par programme ou site",
                   self.var_mode, "applications").pack(fill="x")
        self.radio(f, "Ecran — couleur dominante de l'ecran, en direct",
                   self.var_mode, "ecran").pack(fill="x")
        self.radio(f, "Mixte — moitie regle, moitie ecran",
                   self.var_mode, "mixte").pack(fill="x")
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
        self.var_finesse = self.reglette(
            f, "ecran_finesse", "Finesse de la capture", 2, 16, 1,
            "Colonnes de la vignette lue sur l'ecran. 4 donne une douzaine "
            "de pixels moyennes, largement assez pour une couleur dominante. "
            "Monter affine le vote des petites zones colorees ; le cout reste "
            "negligeable, c'est la vignette elle-meme qui fait la vitesse.",
            entier=True)

        self.separateur(f, 14, 10)
        self.titre(f, "ce que la luminosite de l'ecran fait bouger").pack(
            fill="x", pady=(0, 4))
        self.var_cible_ecran = tk.StringVar(
            value=self.cfg.get("ecran_cible", "luminosite"))
        for cle, libelle in (
                ("luminosite", "La luminosite — scene sombre, guirlande sombre"),
                ("saturation", "La saturation — eclat constant, couleur qui palit "
                               "sur les scenes sombres"),
                ("les_deux",   "Les deux"),
                ("rien",       "Rien — la guirlande garde la luminosite de base")):
            self.radio(f, libelle, self.var_cible_ecran, cle).pack(fill="x")

        self.separateur(f, 14, 8)
        self.titre(f, "etalonnage de l'ecran").pack(fill="x", pady=(0, 6))
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

        self.separateur(f, 14, 8)
        self.titre(f, "balance des blancs").pack(fill="x", pady=(0, 6))
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

        self.separateur(f, 14, 8)
        self.titre(f, "effet de l'ecran en direct").pack(fill="x", pady=(0, 6))
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
        f = self.nouvelle_page("son", defilante=True)

        self.radio(f, "Son \u2014 la musique pilote la guirlande",
                   self.var_mode, "son").pack(fill="x")
        self.txt_audio = self.texte(f, "", BRUME, 8)
        self.txt_audio.pack(fill="x", pady=(4, 0))
        self.texte(f, "Capte la sortie des haut-parleurs, pas le micro. "
                      "Monte la cadence a 15-20 images par seconde dans Reglages "
                      "pour que ca colle au rythme.", BRUME, 8,
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

        self.separateur(f, 12, 8)
        self.titre(f, "ce que le son fait bouger").pack(fill="x", pady=(0, 4))
        self.var_cible = tk.StringVar(value=self.cfg.get("son_cible", "luminosite"))
        for cle, libelle in (
                ("luminosite", "La luminosite \u2014 couleur franche en permanence, "
                               "seul l'eclat suit la musique"),
                ("saturation", "La saturation \u2014 eclat constant, la couleur palit "
                               "dans les passages calmes"),
                ("les_deux",   "Les deux \u2014 la guirlande s'eteint et se delave "
                               "ensemble")):
            self.radio(f, libelle, self.var_cible, cle).pack(fill="x")

        self.separateur(f, 12, 6)
        self.var_sat_fixe = self.reglette(
            f, "son_saturation_fixe", "Saturation", 0.0, 1.0, 0.02,
            "Valeur tenue quand le son ne pilote pas la saturation. Quand il "
            "la pilote, elle sert de plafond. 0 = blanc, 1 = couleur pure.")
        self.var_lum_fixe = self.reglette(
            f, "son_luminosite_fixe", "Luminosite", 0.05, 1.0, 0.05,
            "Valeur tenue quand le son ne pilote pas la luminosite.")

        self.separateur(f, 12, 8)
        self.titre(f, "effet du son en direct").pack(fill="x", pady=(0, 6))
        self.jauge_lum = self.jauge(f, "Luminosite envoyee")
        self.jauge_sat = self.jauge(f, "Saturation envoyee")
        self.texte(f, "Barre en couleur : le son la pilote. Barre sourde : "
                      "elle est tenue a sa valeur fixe.", BRUME, 8,
                   largeur=500).pack(fill="x")

        self.separateur(f, 12, 6)
        self.var_sens = self.reglette(f, "son_sensibilite", "Sensibilite", 0.3, 3.0, 0.1,
                                      "Multiplie le niveau apres gain automatique.")
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
    #  Page Reglages
    # ------------------------------------------------------------------

    def page_reglages(self):
        tk = self.tk
        f = self.nouvelle_page("reglages", defilante=True)
        self.curseurs = {}
        self.curseurs["douceur"] = self.reglette(
            f, "douceur", "Douceur du fondu", 0.01, 0.4, 0.01,
            "Mode Regles. Bas = transition lente et fluide, haut = changement sec.")
        self.curseurs["luminosite_min"] = self.reglette(
            f, "luminosite_min", "Luminosite au repos", 0.05, 1.0, 0.05,
            "Niveau quand le processeur ne fait rien.")
        self.curseurs["luminosite_max"] = self.reglette(
            f, "luminosite_max", "Luminosite a pleine charge", 0.1, 1.0, 0.05,
            "Niveau quand le processeur est a 100 %.")
        self.curseurs["amplitude_respiration"] = self.reglette(
            f, "amplitude_respiration", "Respiration", 0.0, 0.4, 0.02,
            "Oscillation lente permanente. Ignoree en mode Ecran.")
        self.curseurs["veille_minutes"] = self.reglette(
            f, "veille_minutes", "Veille apres", 1, 60, 1,
            "Minutes sans clavier ni souris avant de basculer en braise sourde.",
            entier=True)
        self.curseurs["images_par_seconde"] = self.reglette(
            f, "images_par_seconde", "Images par seconde", 2, 60, 1,
            "Cadence de capture et d'ecriture. La capture par vignette tient "
            "60 sans effort ; c'est le controleur Bluetooth qui plafonne, "
            "souvent vers 30. Au dela, les trames s'accumulent et la "
            "guirlande retarde au lieu d'aller plus vite. Monte "
            "progressivement et redescends des que ca saccade.",
            entier=True)

        self.separateur(f, 14, 8)
        self.titre(f, "affichage").pack(fill="x", pady=(0, 6))
        self.texte(f, "Detectee sur l'ecran au demarrage. A forcer seulement si "
                      "l'interface sort trop petite ou trop grande — un ecran 4K "
                      "qui se declare a tort en 96 points par pouce, par exemple. "
                      "Le changement prend effet au prochain lancement.",
                   BRUME, 8, largeur=490).pack(fill="x", pady=(0, 10))
        self.var_echelle = self.reglette(
            f, "echelle_interface", "Echelle de l'interface", 0.0, 3.0, 0.25,
            "0 = automatique. 1.00 = ecran classique, 1.50 = 4K a 150 %%, "
            "2.00 = 4K a 200 %%. Detectee ici : %.2f." % self.echelle)

        self.separateur(f, 14, 8)
        self.var_eteindre = tk.IntVar(
            value=1 if self.cfg.get("eteindre_en_partant", True) else 0)
        self.case(f, "Eteindre la guirlande en quittant et a l'arret de Windows",
                  self.var_eteindre).pack(fill="x", pady=(0, 8))

        self.var_cpu = tk.IntVar(value=1 if self.cfg.get("reaction_processeur", True) else 0)
        self.case(f, "La charge du processeur module la luminosite — mode Regles",
                  self.var_cpu).pack(fill="x")

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
                couleur = ETAT["couleur"]
                vif = ETAT["connecte"] and max(couleur) > 6
                corps = couleur if vif else (90, 74, 110)
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

    def page_calendrier(self):
        tk = self.tk
        f = self.nouvelle_page("calendrier", defilante=True)

        self.texte(f, "Les journees et les reperes viennent de BrainDebugger. "
                      "L'application ne les invente pas et ne les stocke pas : "
                      "elle affiche ce que le site lui a envoye.",
                   BRUME, 9, largeur=500).pack(fill="x")

        self.separateur(f)
        self.titre(f, "journees").pack(fill="x", pady=(0, 6))
        self.liste_jours = tk.Frame(f, bg=NUIT)
        self.liste_jours.pack(fill="x")

        self.separateur(f)
        self.titre(f, "reperes").pack(fill="x", pady=(0, 6))
        self.liste_reperes = tk.Frame(f, bg=NUIT)
        self.liste_reperes.pack(fill="x")

        self._signature_journal = None

    def peindre_journal(self):
        """Ne redessine que si le contenu a change : la boucle passe ici
        deux fois par seconde."""
        signature = (len(PONT["jours"]), len(PONT["reperes"]),
                     PONT["vu_le"])
        if signature == getattr(self, "_signature_journal", None):
            return
        self._signature_journal = signature
        tk = self.tk

        for cadre, source, cles, vide in (
                (self.liste_jours, PONT["jours"], ("date", "note"),
                 "Aucune journee recue. Le site n'a encore rien envoye."),
                (self.liste_reperes, PONT["reperes"], ("date", "titre"),
                 "Aucun repere recu.")):
            for enfant in cadre.winfo_children():
                enfant.destroy()
            if not source:
                self.texte(cadre, vide, FIL, 9).pack(fill="x")
                continue
            for entree in source[:40]:
                rang = tk.Frame(cadre, bg=ENCRE)
                rang.pack(fill="x", pady=(0, self.px(3)))
                teinte = str(entree.get("couleur") or "").strip()
                pastille = tk.Frame(rang, bg=teinte if teinte.startswith("#") else FIL,
                                    width=self.px(4))
                pastille.pack(side="left", fill="y")
                tk.Label(rang, text=str(entree.get(cles[0], ""))[:16], bg=ENCRE,
                         fg=BRUME, font=(self.f_mono, 9), anchor="w",
                         padx=self.px(10), pady=self.px(7)).pack(side="left")
                tk.Label(rang, text=str(entree.get(cles[1], ""))[:90], bg=ENCRE,
                         fg=CRAIE, font=(self.f_ui, 9), anchor="w",
                         justify="left").pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------
    #  Page Moi
    # ------------------------------------------------------------------

    def page_moi(self):
        tk = self.tk
        f = self.nouvelle_page("moi", defilante=True)

        carte = tk.Frame(f, bg=VELOURS, padx=18, pady=16)
        carte.pack(fill="x")
        self.titre(carte, "humeur du moment").pack(fill="x")
        haut = tk.Frame(carte, bg=VELOURS)
        haut.pack(fill="x", pady=(6, 0))
        self.txt_humeur = tk.Label(haut, text="\u2014", bg=VELOURS, fg=CRAIE,
                                   font=(self.f_titre, 20), anchor="w")
        self.txt_humeur.pack(side="left")
        self.apercu_humeur = self.apercu_couleur(haut, 52, VELOURS)
        self.apercu_humeur.pack(side="right")
        self.txt_humeur_date = tk.Label(carte, text="", bg=VELOURS, fg=BRUME,
                                        font=(self.f_mono, 8), anchor="w")
        self.txt_humeur_date.pack(fill="x", pady=(6, 0))

        self.separateur(f)
        self.titre(f, "rappels du site").pack(fill="x", pady=(0, 6))
        self.liste_rappels = tk.Frame(f, bg=NUIT)
        self.liste_rappels.pack(fill="x")
        self._signature_rappels = None



    def peindre_moi(self):
        humeur = PONT.get("humeur") or {}
        libelle = str(humeur.get("libelle") or "").strip()
        self.txt_humeur.configure(text=libelle or "\u2014")
        self.txt_humeur_date.configure(
            text=str(humeur.get("date") or "") if libelle
            else "Le site n'a pas encore envoye d'humeur.")

        signature = (len(PONT["rappels"]),
                     PONT["rappels"][0]["id"] if PONT["rappels"] else None)
        if signature != getattr(self, "_signature_rappels", None):
            self._signature_rappels = signature
            tk = self.tk
            for enfant in self.liste_rappels.winfo_children():
                enfant.destroy()
            if not PONT["rappels"]:
                self.texte(self.liste_rappels, "Aucun rappel en attente.",
                           FIL, 9).pack(fill="x")
            for rappel in PONT["rappels"]:
                bloc = tk.Frame(self.liste_rappels, bg=ENCRE, padx=self.px(12),
                                pady=self.px(9))
                bloc.pack(fill="x", pady=(0, self.px(4)))
                tk.Label(bloc, text=rappel["titre"], bg=ENCRE, fg=CRAIE,
                         font=(self.f_ui, 9, "bold"), anchor="w").pack(fill="x")
                tk.Label(bloc, text=rappel["texte"], bg=ENCRE, fg=BRUME,
                         font=(self.f_ui, 9), anchor="w", justify="left",
                         wraplength=self.px(460)).pack(fill="x")

    def peindre_pont(self):
        """Le bandeau du pont, commun a Calendrier et a Moi."""
        self.txt_pont.configure(
            text=PONT["message"],
            fg=ALERTE if PONT["etat"] == "erreur" else BRUME)
        # Un bouton qui n'a rien a effacer est du bruit.
        if PONT["rappels"]:
            self.btn_lu.pack(side="left", padx=self.px(8))
        else:
            self.btn_lu.pack_forget()

    # ------------------------------------------------------------------
    #  Actions du pont
    # ------------------------------------------------------------------

    def relever_pont(self):
        threading.Thread(target=relever_le_site, args=(self.cfg,),
                         daemon=True).start()

    def vider_rappels(self):
        PONT["rappels"].clear()
        self._signature_rappels = None

    def ouvrir_site(self):
        import webbrowser
        adresse = str(self.cfg.get("pont_site", "")).strip()
        if adresse:
            webbrowser.open(adresse)

    # ------------------------------------------------------------------
    #  Page Mises a jour
    # ------------------------------------------------------------------

    def page_maj(self):
        tk = self.tk
        f = self.nouvelle_page("maj", defilante=True)

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
        self.case(f, "Poser la mise a jour sans rien demander — l'application "
                     "se ferme et redemarre seule, les reglages sont conserves",
                  self.var_maj_auto, self.options_maj).pack(fill="x", pady=(4, 0))
        self.var_maj_pre = tk.IntVar(
            value=1 if self.cfg.get("maj_prereleases", False) else 0)
        self.case(f, "Accepter les builds de developpement — chaque fusion "
                     "sur main en produit un, sans attendre une version "
                     "stable. Decoche pour ne recevoir que les stables.",
                  self.var_maj_pre, self.options_maj).pack(fill="x", pady=(4, 0))

        self.separateur(f)

        self.texte(f, "Les versions viennent des publications de github.com/"
                      + DEPOT_GITHUB + ". La verification est une simple lecture "
                      "de l'API publique de GitHub : rien de la machine n'est "
                      "envoye. Le nouvel exe remplace l'ancien dans "
                      + DOSSIER + " et config.json n'est jamais touche.",
                   BRUME, 8, largeur=460).pack(fill="x")

    def action_maj(self):
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
                                selectforeground="#140E1C", highlightthickness=0,
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
        accent = lisible((r, v, b)) if max(r, v, b) > 8 else ACCENT_DEPART
        if accent != self.accent:
            self.accent = accent
            self.appliquer_accent()

        self.txt_statut.configure(text=ETAT["message"],
                                  fg=VIF if ETAT["connecte"] else ALERTE)
        self.txt_trame.configure(text=f"55 07 01 {r:02x} {v:02x} {b:02x}   {hexa}")
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

        self.tracer_bande(hexa)
        self.peindre_apercus()
        self.txt_apercu_ecran.configure(text=hexa)
        if self.section == "calendrier":
            self.peindre_journal()
        if self.section == "moi":
            self.peindre_moi()
        if self.section in ("calendrier", "moi"):
            self.peindre_pont()
        if self.section == "passerelle":
            self.peindre_etat_pont()
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

        if self.section == "accueil":
            # Repeindre hors de l'accueil ne servirait a rien : la tuile
            # n'est pas a l'ecran.
            self._dessiner_ampoule(self._fond_ampoule)
            self.etat_tuile.configure(
                text=("connectee \u2014 " + hexa) if ETAT["connecte"]
                else "hors ligne",
                fg=VIF if ETAT["connecte"] else ALERTE)

        self.txt_maj.configure(
            text=MAJ["message"],
            fg=VIF if MAJ["etat"] in ("disponible", "prete") else BRUME)
        pret = MAJ["etat"] in ("disponible", "prete")
        occupe = MAJ["etat"] in ("verification", "telechargement")
        self.btn_maj.configure(
            text=("Installer " + MAJ["version"]) if pret
            else ("En cours..." if occupe else "Verifier maintenant"),
            state="disabled" if occupe else "normal")
        # La pastille du rail s'allume des qu'une maj attend, meme groupe replie.
        if pret and not self.badge_maj.winfo_ismapped():
            self.badge_maj.pack(side="right", padx=(0, 2))
        elif not pret and self.badge_maj.winfo_ismapped():
            self.badge_maj.pack_forget()

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

    def tracer_bande(self, hexa):
        """Un trait par mesure : environ une minute d'historique visible."""
        self.historique.append(hexa)
        largeur = max(1, self.bande.winfo_width())
        capacite = max(20, largeur // self.px(4))
        del self.historique[:-capacite]
        while len(self.traits) < capacite:
            self.traits.append(self.bande.create_rectangle(
                0, 0, 0, 0, outline="", fill=ENCRE))
        pas = largeur / capacite
        debut = capacite - len(self.historique)
        for i, trait in enumerate(self.traits[:capacite]):
            j = i - debut
            couleur = self.historique[j] if 0 <= j < len(self.historique) else ENCRE
            x = i * pas
            self.bande.coords(trait, x, 0, x + pas + 1, self.px(26))
            self.bande.itemconfig(trait, fill=couleur)

    def appliquer_accent(self):
        try:
            self.bouton_principal.configure(bg=self.accent, activebackground=self.accent)
            self.boite.configure(selectbackground=self.accent)
            rang, barre, etiq = self.onglets[self.section]
            barre.configure(bg=self.accent)
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
    # repos | verification | a_jour | disponible | telechargement | prete | erreur
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
    img = Image.new("RGB", (64, 64), (23, 16, 31))
    d = ImageDraw.Draw(img)
    r, v, b = [max(30, int(c)) for c in rgb]
    for i, x in enumerate(range(9, 60, 11)):
        y = 26 + int(10 * math.sin(i * 1.1))
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(r, v, b))
    return img


def ecrire_icone(chemin):
    """Genere icone.ico pour la compilation."""
    from PIL import Image, ImageDraw
    grand = Image.new("RGB", (256, 256), (23, 16, 31))
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
    TRAY["icone"] = pystray.Icon("machitool", image_icone((139, 92, 246)), NOM_APP)

    # ---- mise a jour -------------------------------------------------
    # Tout passe par un fil separe : une requete reseau dans le fil de
    # tkinter figerait la fenetre, et dans celui de pystray le menu.

    def notifier(titre, texte):
        try:
            TRAY["icone"].notify(texte, titre)
        except Exception:
            print(titre, ":", texte)

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
            notifier(NOM_APP,
                     "Installation de la version %s, l'application redemarre."
                     % MAJ["version"])
            time.sleep(2)
            if lancer_installeur_maj():
                demande_arret.set()
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
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(libelle_maj,
                         lambda *_: declencher_maj(
                             "installer" if MAJ["etat"] in ("disponible", "prete")
                             else "verifier"),
                         enabled=lambda *_: MAJ["etat"] not in ("verification",
                                                                "telechargement")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", lambda *_: demande_arret.set()),
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
                TRAY["icone"] = pystray.Icon("machitool", image_icone(ETAT["couleur"]), NOM_APP)
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
        if time.time() - dernier[0] > 2.0:
            dernier[0] = time.time()
            try:
                TRAY["icone"].icon = image_icone(ETAT["couleur"])
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
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:                 # noqa: BLE001 - dernier filet
        rapporter_plantage(e)
        sys.exit(1)
