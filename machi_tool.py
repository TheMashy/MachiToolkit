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
import subprocess
import http.server
import urllib.error
import urllib.request

VERSION = "1.4.0"

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
    "api_active": False,
    "api_port": 7373,
    "api_jeton": "",
    "api_origines": ["https://braindebugger-production.up.railway.app",
                     "http://localhost:3000"],

    # Mises a jour depuis les publications GitHub du depot.
    "maj_verifier": True,             # regarder si une version plus recente existe
    "maj_installation_auto": False,   # poser la mise a jour sans rien demander
    "maj_prereleases": False,         # accepter aussi les pre-versions
    "maj_intervalle_heures": 6,       # delai entre deux verifications
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
}

CFG = {}

ACCENT_DEPART = "#B79CF5"   # accent au repos, avant la premiere couleur


def charger_config():
    cfg = json.loads(json.dumps(CONFIG_DEFAUT))
    enregistre = {}
    if os.path.exists(FICHIER_CONFIG):
        try:
            with open(FICHIER_CONFIG, encoding="utf-8") as f:
                enregistre = json.load(f)
            cfg.update(enregistre)
        except Exception as e:
            print("config.json illisible :", e)

    # ecran_suit_luminance a ete remplace par ecran_cible en 1.3. Une case
    # decochee doit le rester apres la mise a jour. La question se pose sur
    # ce qui est ecrit dans le fichier, pas sur cfg : les valeurs par defaut
    # y sont deja, ecran_cible y serait donc toujours present.
    if "ecran_cible" not in enregistre and \
            enregistre.get("ecran_suit_luminance") is False:
        cfg["ecran_cible"] = "rien"
    cfg.pop("ecran_suit_luminance", None)
    return cfg


def sauver_config(cfg):
    propre = {k: v for k, v in cfg.items() if not k.startswith("_")}
    with open(FICHIER_CONFIG, "w", encoding="utf-8") as f:
        json.dump(propre, f, indent=2, ensure_ascii=False)


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


def fenetre_active():
    """'processus.exe | titre', en minuscules. Le titre d'un navigateur
    contient le nom du site, ce qui suffit a distinguer Netflix de GitHub
    sans avoir a lire la barre d'adresse."""
    try:
        import win32gui, win32process, psutil
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ""
        titre = win32gui.GetWindowText(hwnd) or ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            nom = psutil.Process(pid).name()
        except Exception:
            nom = ""
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
        if poids < 0.4:                        # ecran quasi gris ou noir
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
    except ImportError as e:
        AUDIO["message"] = f"bibliotheque manquante ({e.name})"
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
    if not cfg.get("api_jeton"):
        cfg["api_jeton"] = secrets.token_urlsafe(12)
        sauver_config(cfg)
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
        self.send_header("Access-Control-Allow-Headers", "content-type, x-jeton")
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

        if chemin == "/relacher":
            ETAT["forcage"] = None
            return self.repondre(200, {"ok": True})

        return self.repondre(404, {"erreur": "route inconnue"})


def demarrer_api(cfg):
    arreter_api()
    if not cfg.get("api_active"):
        ETAT["api"] = "arretee"
        return
    jeton_courant(cfg)
    try:
        port = int(cfg.get("api_port", 7373))
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
            await client.write_gatt_char(UUID_ECRITURE, TRAME_ON, response=False)
            await asyncio.sleep(0.15)
            # Luminosite materielle au maximum : la modulation se fait dans les
            # valeurs RGB, ce qui donne des fondus continus au lieu des 15
            # paliers du controleur.
            await client.write_gatt_char(UUID_ECRITURE, trame_lum(15), response=False)

            depart = time.time()
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
                if forcage and time.time() < forcage["expire"]:
                    rc, vc, bc = forcage["couleur"]
                    nom = forcage["nom"]
                    mode = "force"
                elif forcage:
                    ETAT["forcage"] = None

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

                await asyncio.sleep(intervalle)

    except Exception as e:
        ETAT["message"] = f"Deconnectee ({str(e)[:55]})"
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


def activer_dpi():
    """A appeler avant la premiere fenetre, sinon Windows l'ignore."""
    if os.name != "nt":
        return
    import ctypes
    # -4 = par ecran, version 2 : suit le facteur de chaque moniteur, y
    # compris quand la fenetre est deplacee de l'un a l'autre.
    for tentative in (
            lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(
                ctypes.c_void_p(-4)),
            lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
            lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            tentative()
            return
        except Exception:
            continue


def echelle_ecran(racine, forcee=0.0):
    """Facteur a appliquer aux tailles en pixels. 1.0 = ecran 96 ppp."""
    try:
        if forcee and float(forcee) > 0:
            return max(0.75, min(4.0, float(forcee)))
    except (TypeError, ValueError):
        pass
    try:
        return max(1.0, min(4.0, racine.winfo_fpixels("1i") / 96.0))
    except Exception:
        return 1.0


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
SECTIONS = [("accueil",   "Accueil"),
            ("",          "Lumiere"),
            ("etat",      "Etat"),
            ("regles",    "Regles"),
            ("ecran",     "Ecran"),
            ("son",       "Son"),
            ("reglages",  "Reglages"),
            ("site",      "Site web"),
            ("appairage", "Appairage"),
            ("",          "Application"),
            ("maj",       "Mises a jour")]


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
        self.section = "etat"
        self.reglettes = []
        self.accent = ACCENT_DEPART
        self.phase = 0.0
        # Remplace par lancer() : le panneau demande, la boucle principale agit.
        self.declencher_maj = lambda quoi="verifier": None

        self.root = tk.Tk()
        self.echelle = echelle_ecran(self.root, self.cfg.get("echelle_interface", 0.0))
        # tk scaling est le nombre de pixels par point : il fait grandir les
        # caracteres, dont la taille est donnee en points.
        try:
            self.root.tk.call("tk", "scaling", self.echelle * 96.0 / 72.0)
        except Exception:
            pass

        self.root.title(NOM_APP)
        self.root.geometry("%dx%d" % (self.px(780), self.px(700)))
        self.root.minsize(self.px(720), self.px(640))
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

        self.page_accueil()
        self.page_etat()
        self.page_regles()
        self.page_ecran()
        self.page_son()
        self.page_reglages()
        self.page_maj()
        self.page_site()
        self.page_appairage()
        self.aller("accueil")

        self.animer()
        self.rafraichir()

    def px(self, n):
        """Convertit une mesure pensee en 96 ppp vers l'ecran reel."""
        return max(1, int(round(n * self.echelle)))

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
        self.root.after(70, self.animer)

    # ------------------------------------------------------------------
    #  Rail de navigation
    # ------------------------------------------------------------------

    def construire_rail(self):
        tk = self.tk
        tk.Frame(self.rail, bg=NUIT, height=self.px(10)).pack()
        for cle, libelle in SECTIONS:
            if not cle:                       # intitule de groupe, non cliquable
                self.titre(self.rail, libelle).pack(
                    fill="x", padx=17, pady=(14, 4))
                continue
            rang = tk.Frame(self.rail, bg=NUIT, cursor="hand2")
            rang.pack(fill="x")
            barre = tk.Frame(rang, bg=NUIT, width=3)
            barre.pack(side="left", fill="y")
            etiq = tk.Label(rang, text=libelle, bg=NUIT, fg=BRUME, anchor="w",
                            font=(self.f_ui, 10), padx=14, pady=9)
            etiq.pack(side="left", fill="x", expand=True)
            for w in (rang, etiq):
                w.bind("<Button-1>", lambda e, c=cle: self.aller(c))
                w.bind("<Enter>", lambda e, r=rang, l=etiq, c=cle:
                       self.survol(r, l, c, True))
                w.bind("<Leave>", lambda e, r=rang, l=etiq, c=cle:
                       self.survol(r, l, c, False))
            self.onglets[cle] = (rang, barre, etiq)

    def survol(self, rang, etiq, cle, dedans):
        if cle == self.section:
            return
        fond = VELOURS if dedans else NUIT
        rang.configure(bg=fond)
        etiq.configure(bg=fond, fg=CRAIE if dedans else BRUME)

    def aller(self, cle):
        self.section = cle
        for c, (rang, barre, etiq) in self.onglets.items():
            actif = c == cle
            fond = VELOURS if actif else NUIT
            rang.configure(bg=fond)
            etiq.configure(bg=fond, fg=CRAIE if actif else BRUME,
                           font=(self.f_ui, 10, "bold" if actif else "normal"))
            barre.configure(bg=self.accent if actif else fond)
        for c, page in self.pages.items():
            page.pack_forget()
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

    def poser_jauge(self, j, valeur, pilotee):
        largeur = max(self.px(20), j["toile"].winfo_width())
        valeur = max(0.0, min(1.0, float(valeur)))
        haut, bas = self.px(4), self.px(12)
        j["toile"].coords(j["rail"], 0, haut, largeur, bas)
        j["toile"].coords(j["plein"], 0, haut, largeur * valeur, bas)
        j["toile"].itemconfig(j["plein"], fill=self.accent if pilotee else FIL)
        j["val"].configure(text="%3d %%" % round(valeur * 100))
        j["source"].configure(text="pilotee par le son" if pilotee else "fixe",
                              fg=CRAIE if pilotee else BRUME)

    def separateur(self, parent, haut=14, bas=14):
        self.tk.Frame(parent, bg=FIL, height=1).pack(fill="x", pady=(haut, bas))

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

        carte = tk.Frame(f, bg=VELOURS, padx=18, pady=16)
        carte.pack(fill="x")
        self.titre(carte, "source de la couleur").pack(fill="x")
        self.txt_regle = tk.Label(carte, text="", bg=VELOURS, fg=CRAIE,
                                  font=(self.f_titre, 17), anchor="w")
        self.txt_regle.pack(fill="x", pady=(4, 6))
        self.txt_contexte = tk.Label(carte, text="", bg=VELOURS, fg=BRUME,
                                     font=(self.f_mono, 8), anchor="w")
        self.txt_contexte.pack(fill="x")

        self.separateur(f)

        info = tk.Frame(f, bg=NUIT)
        info.pack(fill="x")
        self.titre(info, "guirlande").pack(fill="x")
        self.txt_adresse = tk.Label(info, text="", bg=NUIT, fg=CRAIE,
                                    font=(self.f_mono, 10), anchor="w")
        self.txt_adresse.pack(fill="x", pady=(3, 0))
        self.txt_detail = self.texte(info, "", BRUME, 8)
        self.txt_detail.pack(fill="x", pady=(3, 0))

        self.separateur(f)

        self.titre(f, "activite recente").pack(fill="x", pady=(0, 5))
        self.bande = tk.Canvas(f, height=self.px(26), bg=ENCRE, highlightthickness=0)
        self.bande.pack(fill="x")
        self.historique = []
        self.traits = []

        self.separateur(f)

        self.var_pause = tk.IntVar(value=0)
        self.case(f, "Mettre en pause — fige la couleur actuelle",
                  self.var_pause, self.basculer_pause).pack(fill="x")
        self.var_demarrage = tk.IntVar(value=1 if os.path.exists(chemin_demarrage()) else 0)
        self.case(f, "Lancer au demarrage de Windows",
                  self.var_demarrage, self.basculer_demarrage).pack(fill="x", pady=(4, 0))

        self.texte(f, f"Version {VERSION} — {DOSSIER}", BRUME, 8).pack(
            fill="x", side="bottom", pady=(12, 0))

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
        self.root.after(4000, relever)

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
            f, "images_par_seconde", "Images par seconde", 2, 30, 1,
            "Cadence de capture et d'ecriture. Depuis que la capture passe "
            "par une vignette, 20 a 30 tiennent sans effort en mode Ecran ; "
            "15 a 20 suffisent pour le son. Baisse si la guirlande saccade.",
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
        self.var_cpu = tk.IntVar(value=1 if self.cfg.get("reaction_processeur", True) else 0)
        self.case(f, "La charge du processeur module la luminosite — mode Regles",
                  self.var_cpu).pack(fill="x")

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
        self.bouton(barre, "Verifier maintenant",
                    lambda: self.declencher_maj("verifier"),
                    compact=True).pack(side="left")
        self.bouton(barre, "Telecharger et installer",
                    lambda: self.declencher_maj("installer"),
                    compact=True).pack(side="left", padx=8)

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
            value=1 if self.cfg.get("maj_installation_auto", False) else 0)
        self.case(f, "Poser la mise a jour sans rien demander — l'application "
                     "se ferme et redemarre seule, les reglages sont conserves",
                  self.var_maj_auto, self.options_maj).pack(fill="x", pady=(4, 0))
        self.var_maj_pre = tk.IntVar(
            value=1 if self.cfg.get("maj_prereleases", False) else 0)
        self.case(f, "Accepter aussi les pre-versions",
                  self.var_maj_pre, self.options_maj).pack(fill="x", pady=(4, 0))

        self.separateur(f)

        self.texte(f, "Les versions viennent des publications de github.com/"
                      + DEPOT_GITHUB + ". La verification est une simple lecture "
                      "de l'API publique de GitHub : rien de la machine n'est "
                      "envoye. Le nouvel exe remplace l'ancien dans "
                      + DOSSIER + " et config.json n'est jamais touche.",
                   BRUME, 8, largeur=460).pack(fill="x")

    def options_maj(self):
        self.cfg["maj_verifier"] = bool(self.var_maj_verifier.get())
        self.cfg["maj_installation_auto"] = bool(self.var_maj_auto.get())
        self.cfg["maj_prereleases"] = bool(self.var_maj_pre.get())
        sauver_config(self.cfg)

    # ------------------------------------------------------------------
    #  Page Site web
    # ------------------------------------------------------------------

    def page_site(self):
        tk = self.tk
        f = self.nouvelle_page("site", defilante=True)

        self.texte(f, "Ouvre un petit serveur sur ta machine. Un site que tu "
                      "developpes peut alors imposer une couleur, avec une date "
                      "de peremption : s'il arrete d'emettre, la guirlande revient "
                      "seule au mode normal.", BRUME, 8, largeur=500).pack(fill="x")

        self.separateur(f, 12, 10)

        self.var_api = tk.IntVar(value=1 if self.cfg.get("api_active") else 0)
        self.case(f, "Activer la passerelle locale", self.var_api).pack(fill="x")
        self.txt_api = self.texte(f, "", BRUME, 8)
        self.txt_api.pack(fill="x", pady=(4, 0))

        rang = tk.Frame(f, bg=NUIT)
        rang.pack(fill="x", pady=(12, 0))
        self.texte(rang, "Port", CRAIE, 9, True).pack(side="left")
        self.champ_port = self.champ(rang, str(self.cfg.get("api_port", 7373)), 7)
        self.champ_port.pack(side="left", padx=10)
        self.texte(rang, "Jeton", CRAIE, 9, True).pack(side="left", padx=(16, 0))
        self.champ_jeton = self.champ(
            rang, self.cfg.get("api_jeton") or secrets.token_urlsafe(12), 20)
        self.champ_jeton.pack(side="left", padx=10)
        self.bouton(rang, "Copier", self.copier_jeton, compact=True).pack(side="left")
        self.bouton(rang, "Regenerer", self.regenerer_jeton,
                    compact=True).pack(side="left", padx=6)

        self.titre(f, "sites autorises").pack(fill="x", pady=(16, 4))
        self.texte(f, "Une origine par virgule, protocole compris. Toute autre "
                      "page recevra une erreur.", BRUME, 8).pack(fill="x", pady=(0, 4))
        self.champ_origines = self.champ(
            f, ", ".join(self.cfg.get("api_origines", [])), 10)
        self.champ_origines.pack(fill="x")

        self.separateur(f, 14, 8)
        self.titre(f, "a coller dans ton site").pack(fill="x", pady=(0, 5))
        pied = tk.Frame(f, bg=NUIT)
        pied.pack(fill="x", side="bottom", pady=(8, 0))
        self.bouton(pied, "Copier le code", self.copier_code,
                    compact=True).pack(side="left")

        self.code = tk.Text(f, height=8, bg=ENCRE, fg=BRUME, relief="flat", bd=8,
                            font=(self.f_mono, 8), wrap="none", highlightthickness=0,
                            insertbackground=CRAIE)
        self.code.pack(fill="both", expand=True)
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
        self.bouton(pied, "Reconnecter", self.reconnecter, compact=True).pack(side="left", padx=8)
        self.bouton(pied, "Quitter", self.quitter_tout, compact=True).pack(side="right")
        self.bouton(pied, "Reduire", self.cacher, compact=True).pack(side="right", padx=8)

    # ------------------------------------------------------------------
    #  Actions
    # ------------------------------------------------------------------

    def basculer_pause(self):
        ETAT["pause"] = bool(self.var_pause.get())

    def basculer_demarrage(self):
        if self.var_demarrage.get():
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

    # ------------------------------------------------------------------
    #  Rafraichissement
    # ------------------------------------------------------------------

    def rafraichir(self):
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
                "mixte": "mode Mixte"}.get(self.cfg.get("mode", "applications"), "")
        self.txt_detail.configure(
            text=f"{mode} — {ETAT['ecrans']} ecran(s) — "
                 f"{self.cfg.get('images_par_seconde', 8)} images par seconde")

        self.tracer_bande(hexa)

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
        notes = (MAJ.get("notes") or "").strip()
        self.txt_notes.configure(text=notes[:1500] if notes else "-")

        self.txt_audio.configure(text="Capture " + AUDIO.get("message", "arretee"))

        cible_ecran = self.cfg.get("ecran_cible", "luminosite")
        en_ecran = self.cfg.get("mode") in ("ecran", "mixte")
        self.poser_jauge(self.jauge_ecran_entree,
                         ETAT["ecran_luminance"] if en_ecran else 0.0, en_ecran)
        self.poser_jauge(
            self.jauge_ecran_lum,
            ETAT["ecran_gain"] if en_ecran
            else self.cfg.get("ecran_luminosite_base", 1.0),
            en_ecran and cible_ecran in ("luminosite", "les_deux"))
        self.poser_jauge(
            self.jauge_ecran_sat, ETAT["ecran_sat"] if en_ecran else 0.0,
            en_ecran and cible_ecran in ("saturation", "les_deux"))

        cible = self.cfg.get("son_cible", "luminosite")
        en_son = self.cfg.get("mode") == "son" and AUDIO.get("actif")
        self.poser_jauge(
            self.jauge_lum,
            AUDIO["gain"] if en_son else self.cfg.get("son_luminosite_fixe", 1.0),
            cible in ("luminosite", "les_deux"))
        self.poser_jauge(
            self.jauge_sat,
            AUDIO["saturation"] if en_son else self.cfg.get("son_saturation_fixe", 0.92),
            cible in ("saturation", "les_deux"))
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

        self.root.after(400, self.rafraichir)

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
    return (tuple(nombres[:3]), 0 if pre else 1, pre)


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
        "User-Agent": "MachiToolkit/" + VERSION,
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
    MAJ["message"] = "Version %s disponible (installee : %s)." % (
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
                     "L'application demarre maintenant avec Windows.\n"
                     "Son icone est en bas a droite, pres de l'horloge.")
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


def lancer():
    global CFG
    identite_barre_taches()
    activer_dpi()
    CFG = charger_config()
    premiere_fois = not str(CFG.get("adresse", "")).strip()
    nettoyer_maj()      # efface l'exe telecharge par la mise a jour precedente

    boucle = asyncio.new_event_loop()

    def fil_ble():
        asyncio.set_event_loop(boucle)
        try:
            boucle.run_until_complete(superviseur(CFG))
        except Exception as e:
            print("Fil Bluetooth arrete :", e)

    threading.Thread(target=fil_ble, daemon=True).start()
    demarrer_api(CFG)
    if CFG.get("mode") == "son":
        demarrer_audio(CFG)

    demande_ouverture = threading.Event()
    demande_arret = threading.Event()

    import pystray
    panneau = Panneau(CFG, lambda: demande_arret.set())

    icone = pystray.Icon("machitool", image_icone((139, 92, 246)), NOM_APP)

    # ---- mise a jour -------------------------------------------------
    # Tout passe par un fil separe : une requete reseau dans le fil de
    # tkinter figerait la fenetre, et dans celui de pystray le menu.

    def notifier(titre, texte):
        try:
            icone.notify(texte, titre)
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
        if CFG.get("maj_installation_auto", False):
            travail_maj("installer")
        else:
            notifier("Mise a jour disponible",
                     "Version %s. Clic droit sur l'icone pour l'installer."
                     % publication["version"])

    def declencher_maj(quoi="verifier"):
        if MAJ["etat"] in ("verification", "telechargement"):
            return
        threading.Thread(target=travail_maj, args=(quoi,), daemon=True).start()

    def veille_maj():
        """Premiere verification peu apres le demarrage, puis a intervalle."""
        attente = 30.0
        while ETAT["en_marche"]:
            fin = time.time() + attente
            while ETAT["en_marche"] and time.time() < fin:
                time.sleep(2)
            if not ETAT["en_marche"]:
                return
            if FIGE and CFG.get("maj_verifier", True) \
                    and MAJ["etat"] not in ("verification", "telechargement"):
                travail_maj("verifier")
            attente = max(1, int(CFG.get("maj_intervalle_heures", 6))) * 3600

    panneau.declencher_maj = declencher_maj
    threading.Thread(target=veille_maj, daemon=True).start()

    def libelle_maj(*_):
        if MAJ["etat"] == "prete":
            return "Installer la version %s" % MAJ["version"]
        if MAJ["etat"] == "disponible":
            return "Mettre a jour vers la version %s" % MAJ["version"]
        if MAJ["etat"] == "telechargement":
            return "Telechargement en cours..."
        if MAJ["etat"] == "verification":
            return "Verification en cours..."
        return "Rechercher une mise a jour"

    icone.menu = pystray.Menu(
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
    threading.Thread(target=icone.run, daemon=True).start()

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
            arreter_api()
            arreter_audio()
            try:
                icone.stop()
            except Exception:
                pass
            panneau.root.destroy()
            return
        if demande_ouverture.is_set():
            demande_ouverture.clear()
            panneau.afficher()
        if time.time() - dernier[0] > 2.0:
            dernier[0] = time.time()
            try:
                icone.icon = image_icone(ETAT["couleur"])
            except Exception:
                pass
        if MAJ["etat"] != dernier_etat_maj[0]:
            dernier_etat_maj[0] = MAJ["etat"]
            try:
                icone.update_menu()
            except Exception:
                pass
        panneau.root.after(150, surveiller)

    panneau.root.after(150, surveiller)
    panneau.root.mainloop()


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
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

    if FIGE:
        if installer_ou_mettre_a_jour():
            return
        if deja_lance():
            return
    lancer()


if __name__ == "__main__":
    main()
