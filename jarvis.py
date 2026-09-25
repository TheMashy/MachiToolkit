# -*- coding: utf-8 -*-
"""
JARVIS -- ON L'APPELLE, IL ECOUTE, IL FAIT OU IL REPOND.

Ce fichier porte tout ce qui ne depend pas de Windows : le detecteur du mot
d'eveil, la fin de phrase, la lecture des commandes, les sons, les couleurs
d'etat, et le processus qui tient le micro. Machi Tool (machi_tool.py) s'en
sert pour le reste : la transcription (le moteur de la dictee), la guirlande,
la voix, le compagnon.

CE QUI EST PROMIS, ET QUE CE CODE TIENT :
  - le micro n'est ouvert que si la personne a coche « Ecouter Jarvis », et
    Windows affiche alors son temoin de micro comme pour n'importe quelle app ;
  - AVANT le mot d'eveil, rien ne sort du processus de l'oreille : ni son, ni
    texte. Le detecteur ne fait pas de transcription -- il compare des
    empreintes acoustiques de 80 ms a celles du mot « Jarvis ». Ce qui est dit
    dans la piece n'est jamais transcrit tant que personne n'a appele Jarvis ;
  - le son n'est JAMAIS ecrit sur le disque ; la phrase qui suit l'eveil est
    transcrite sur ce poste, par le meme moteur que la dictee ;
  - ce qui est dit n'est jamais journalise : le journal note « commande
    lumiere », jamais la phrase ;
  - aucun crochet clavier, aucun raccourci global.

LE MOT D'EVEIL, DEUX CHEMINS.
  « Hey Jarvis » : le modele pre-entraine d'openWakeWord (David Scripka,
  code Apache-2.0, modeles CC BY-NC-SA 4.0 -- usage personnel), reimplemente
  ici avec onnxruntime seul : le paquet officiel tire scipy et scikit-learn,
  soit cent Mo de plus dans l'exe. Verifie identique a la reference a 5e-5
  pres. Mais il a appris l'anglais : prononce a la francaise, il ne reagit
  presque pas, et « Jarvis » tout seul ne le declenche jamais.

  « Jarvis » : la voix de la personne. Elle le dit trois fois, on garde
  l'EMPREINTE de chaque fois (les vecteurs de 96 nombres que calcule le
  modele d'openWakeWord toutes les 80 ms -- pas le son, qu'on ne peut pas
  reconstruire a partir d'eux), et on reconnait ensuite le mot par
  alignement dynamique (DTW). Ca marche dans n'importe quelle langue, avec
  n'importe quel accent, parce que c'est SA facon de le dire qui sert de
  modele.
"""

import base64
import io
import json
import math
import os
import queue
import re
import socket
import struct
import threading
import time
import unicodedata
import wave
from collections import deque

FREQ = 16000
TRAME = 1280                      # 80 ms : le pas du modele d'openWakeWord
TRAME_S = TRAME / FREQ

MODELES_SOURCE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
MODELES = ("melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx")
MODELES_TAILLE_KO = 3600

# Le gabarit d'un mot appris : des trames qui commencent un peu APRES le debut
# de la parole (les premieres embrassent encore le silence d'avant, et
# changeraient selon ce qui precede) et finissent un peu apres sa fin (la
# fenetre du modele couvre 775 ms : le mot entier n'y est qu'une fois fini).
GABARIT_DEBUT = 3
GABARIT_FIN = 4
GABARIT_MIN = 4
GABARIT_MAX = 30
# « IL FAUT QU'IL REPONDE PLUS FACILEMENT A "JARVIS ?" ». Les premieres trames
# d'un gabarit portent encore ce qui PRECEDAIT le mot (la fenetre du modele
# couvre 775 ms) : appris dans le silence, « ok Jarvis », « euh Jarvis ? » ou
# « dis Jarvis » s'en ecartaient de 0,07 a 0,08 -- au-dessus du seuil. Le mot est
# donc aussi compare SANS ses 240 premieres ms, et la fenetre ecoutee est plus
# longue, pour un « Jarviiis ? » qui traine. Mesure (espeak, gabarits appris a
# la francaise, dont un dit comme une question) : quinze facons de l'appeler
# toutes sous 0,047 ; vingt-neuf mots voisins dits par deux voix, rien sous
# 0,055 sauf « Marvis » et « jars vides », qui sont presque son nom.
GABARIT_SAUT = 3
PRESQUE_FACTEUR = 1.7         # jusqu'ou un mot « presque reconnu » est signale
FENETRE_FACTEUR = 2.2

# Parole : au-dessus de trois fois le bruit de fond de la piece, et au-dessus
# d'un plancher absolu (en unites int16), pour qu'une piece silencieuse ne
# prenne pas le moindre froissement pour une phrase.
PAROLE_MIN = 300.0
PAROLE_FACTEUR = 3.0


def seuil_gabarit(sensibilite):
    """0 = strict, 1 = permissif. Mesure sur voix de synthese : le mot appris
    tombe vers 0,02, les mots voisins (« j'arrive », « Travis », « j'avais
    dit ») au-dessus de 0,07. 0,05 au milieu."""
    s = max(0.0, min(1.0, float(sensibilite)))
    return 0.03 + 0.04 * s


# ======================================================================
#  LE DETECTEUR
# ======================================================================

def _options():
    import onnxruntime as rt
    o = rt.SessionOptions()
    o.intra_op_num_threads = 1
    o.inter_op_num_threads = 1
    o.enable_cpu_mem_arena = False
    return o


class Empreintes:
    """Le son, trame par trame, devient une empreinte de 96 nombres (et, si
    le modele est la, un score « hey jarvis »).

    Meme calcul que openwakeword.utils.AudioFeatures en flux : melspectre sur
    les 1280 + 480 derniers echantillons, /10 + 2, fenetre de 76 trames mel,
    empreinte, et le classifieur sur les 16 dernieres empreintes."""

    def __init__(self, dossier, avec_hey=True):
        import numpy as np
        import onnxruntime as rt
        self.np = np
        o = _options()
        p = ["CPUExecutionProvider"]
        self.mel_m = rt.InferenceSession(os.path.join(dossier, MODELES[0]), o, providers=p)
        self.emb_m = rt.InferenceSession(os.path.join(dossier, MODELES[1]), o, providers=p)
        self.hey_m = None
        chemin_hey = os.path.join(dossier, MODELES[2])
        if avec_hey and os.path.isfile(chemin_hey):
            self.hey_m = rt.InferenceSession(chemin_hey, o, providers=p)
            self.hey_in = self.hey_m.get_inputs()[0].name
        self.brut = np.zeros(0, np.int16)
        self.mel = np.ones((76, 32), np.float32)
        # La reference amorce avec quatre secondes de bruit : les seize
        # premieres empreintes du classifieur viennent de la.
        bruit = np.random.default_rng(0).integers(-1000, 1000, FREQ * 4).astype(np.int16)
        self.emp = self._empreintes_bloc(bruit)
        self.n = 0

    def _melspectre(self, x):
        np = self.np
        sortie = self.mel_m.run(None, {"input": x.astype(np.float32)[None]})[0]
        return np.squeeze(sortie) / 10 + 2

    def _empreintes_bloc(self, x):
        np = self.np
        s = self._melspectre(x)
        fen = [s[i:i + 76] for i in range(0, s.shape[0], 8) if s[i:i + 76].shape[0] == 76]
        lot = np.array(fen, np.float32)[..., None]
        return self.emb_m.run(None, {"input_1": lot})[0].squeeze()

    def trame(self, x):
        """x : 1280 echantillons int16. Rend (score hey jarvis, empreinte)."""
        np = self.np
        self.brut = np.concatenate((self.brut, x))[-(TRAME + 480):]
        self.mel = np.vstack((self.mel, self._melspectre(self.brut)))[-76:]
        e = self.emb_m.run(None, {"input_1": self.mel[None, :, :, None].astype(np.float32)})[0]
        e = e.reshape(-1)
        self.emp = np.vstack((self.emp, e))[-120:]
        self.n += 1
        score = 0.0
        if self.hey_m is not None:
            score = float(self.hey_m.run(None, {self.hey_in: self.emp[-16:][None].astype(np.float32)})[0].reshape(-1)[0])
            if self.n <= 5:          # la reference ignore les cinq premieres
                score = 0.0
        return score, e


def normer(v):
    import numpy as np
    v = np.asarray(v, dtype=np.float32)
    if v.ndim == 1:
        return v / max(float(np.linalg.norm(v)), 1e-6)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-6)


def distance_gabarit(g, x):
    """Alignement dynamique : le gabarit ENTIER contre la fin de la fenetre
    recente, debut libre. Distance cosinus moyenne le long du chemin.

    g : (T, 96) normees ; x : (M, 96) normees, la derniere est « maintenant »."""
    import numpy as np
    c = (1.0 - np.asarray(g) @ np.asarray(x).T).tolist()
    n, m = len(c), len(c[0]) if c else 0
    if not n or not m:
        return 9.0
    inf = float("inf")
    prec_d = [0.0] * (m + 1)             # ligne 0 : on peut commencer n'importe ou
    prec_l = [0] * (m + 1)
    for i in range(1, n + 1):
        ci = c[i - 1]
        d = [inf] * (m + 1)
        lo = [0] * (m + 1)
        for j in range(1, m + 1):
            a, b, e = prec_d[j - 1], prec_d[j], d[j - 1]
            if a <= b and a <= e:
                d[j], lo[j] = a + ci[j - 1], prec_l[j - 1] + 1
            elif b <= e:
                d[j], lo[j] = b + ci[j - 1], prec_l[j] + 1
            else:
                d[j], lo[j] = e + ci[j - 1], lo[j - 1] + 1
        prec_d, prec_l = d, lo
    return prec_d[m] / max(1, prec_l[m])


def distance_eveil(g, fen):
    """Le gabarit entier, ou sans ses premieres trames -- celles qui portent
    le silence d'avant (voir GABARIT_SAUT) ; la plus proche des deux."""
    d = distance_gabarit(g, fen)
    if len(g) - GABARIT_SAUT >= GABARIT_MIN:
        d = min(d, distance_gabarit(g[GABARIT_SAUT:], fen))
    return d


class Detecteur:
    """Ecoute la piece et dit quand on a appele Jarvis.

    Garde aussi les deux dernieres secondes de son : c'est de la que part la
    phrase, pour que « Jarvis, allume la lumiere » dit d'une traite ne perde
    pas son debut."""

    def __init__(self, empreintes, gabarits=(), sensibilite=0.5, seuil_hey=0.5):
        self.e = empreintes
        self.gabarits = [normer(g) for g in gabarits if len(g) >= GABARIT_MIN]
        self.seuil = seuil_gabarit(sensibilite)
        self.seuil_hey = seuil_hey
        self.avant = deque(maxlen=25)           # 2 s de son
        self.emps = deque(maxlen=48)
        self.niveaux = deque(maxlen=48)
        self.plancher = None
        self.n = 0
        self.repos_jusqua = 0
        self.derniere_parole = -999
        self.plus_proche = None       # la distance du dernier mot compare, pour « presque »

    def parle(self, rms):
        return rms > max(PAROLE_FACTEUR * (self.plancher or PAROLE_MIN), PAROLE_MIN)

    def _suivre_plancher(self, rms):
        if self.plancher is None:
            self.plancher = max(rms, 20.0)
        elif rms < 1.5 * self.plancher:
            self.plancher = max(20.0, 0.95 * self.plancher + 0.05 * rms)
        else:
            # Un ventilateur qu'on allume : le fond remonte, lentement, pour
            # qu'une longue phrase ne passe pas pour du bruit.
            self.plancher *= 1.0005

    def trame(self, x, chercher=True):
        """Rend None, ou (« hey » | « voix », score) quand Jarvis est appele."""
        import numpy as np
        self.n += 1
        rms = float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))
        self._suivre_plancher(rms)
        score, e = self.e.trame(x)
        self.avant.append(np.asarray(x, dtype=np.int16))
        self.emps.append(normer(e))
        self.niveaux.append(rms)
        if self.parle(rms):
            self.derniere_parole = self.n
        if not chercher or self.n < self.repos_jusqua:
            return None
        if self.e.hey_m is not None and score >= self.seuil_hey:
            self.repos_jusqua = self.n + 25
            return ("hey", score)
        if not self.gabarits:
            return None
        # Rien a comparer si personne n'a parle a l'instant : economise le
        # calcul, et un silence ne peut pas ressembler a un mot.
        if self.n - self.derniere_parole > GABARIT_FIN + 3:
            return None
        x_ = np.array(self.emps)
        meilleur = 9.0
        self.plus_proche = None
        for g in self.gabarits:
            fen = x_[-(int(FENETRE_FACTEUR * len(g)) + 1):]
            if len(fen) < len(g) // 2:
                continue
            meilleur = min(meilleur, distance_eveil(g, fen))
        self.plus_proche = meilleur if meilleur < 9.0 else None
        if meilleur <= self.seuil:
            self.repos_jusqua = self.n + 25
            return ("voix", meilleur)
        return None

    def son_d_avant(self):
        import numpy as np
        return np.concatenate(list(self.avant)) if self.avant else np.zeros(0, np.int16)


def gabarit_depuis(emps, niveaux, parle):
    """Le gabarit d'un mot, a partir des empreintes et niveaux captures
    pendant qu'on l'a dit. Rend None si on n'y trouve pas un mot."""
    idx = [i for i, r in enumerate(niveaux) if parle(r)]
    if not idx:
        return None
    d, f = idx[0], idx[-1]
    g = list(emps[d + GABARIT_DEBUT:f + GABARIT_FIN + 1])
    if not (GABARIT_MIN <= len(g) <= GABARIT_MAX):
        return None
    return [[round(float(v), 5) for v in ligne] for ligne in normer(g)]


def coherence(gabarits):
    """La plus grande distance entre deux gabarits appris. Au-dessus de 0,1,
    ce ne sont probablement pas les memes mots (ou pas le meme micro)."""
    pire = 0.0
    for i, a in enumerate(gabarits):
        for b in gabarits[i + 1:]:
            pire = max(pire, distance_gabarit(normer(a), normer(b)))
    return pire


# ======================================================================
#  LA FIN DE PHRASE
# ======================================================================

class Phrase:
    """Ce qui suit l'eveil, jusqu'a ce que la personne se taise.

    Le carillon joue au moment de l'eveil, et le micro l'entend : les
    premieres 300 ms ne DECLENCHENT donc pas la parole. Mais « Jarvis stop »
    dit d'une traite tombe justement dedans -- une parole precoce compte,
    avec une attente plus longue ensuite pour laisser le temps de commencer
    si ce n'etait que le carillon."""

    def __init__(self, parle, avant=None, attente=5.0, silence_fin=0.9,
                 duree_max=15.0, ignorer=0.3):
        import numpy as np
        self.np = np
        self.parle = parle
        self.morceaux = [avant] if avant is not None and len(avant) else []
        self.t = 0.0
        self.attente, self.silence_fin = attente, silence_fin
        self.duree_max, self.ignorer = duree_max, ignorer
        self.parole = False
        self.precoce = 0
        self.silence = 0.0

    def trame(self, x, rms):
        """Rend None tant que ca continue, « fini » ou « vide »."""
        self.morceaux.append(self.np.asarray(x, dtype=self.np.int16))
        self.t += TRAME_S
        p = self.parle(rms)
        if self.t <= self.ignorer:
            self.precoce += 1 if p else 0
            return None
        if p:
            self.parole, self.silence = True, 0.0
        else:
            self.silence += TRAME_S
        if self.parole and self.silence >= self.silence_fin:
            return "fini"
        if not self.parole and self.precoce >= 2 and self.silence >= self.silence_fin + 0.5:
            return "fini"
        if not self.parole and self.t >= self.attente:
            return "vide"
        if self.t >= self.duree_max:
            return "fini" if (self.parole or self.precoce >= 2) else "vide"
        return None

    def wav(self):
        return wav_de(self.np.concatenate(self.morceaux) if self.morceaux
                      else self.np.zeros(0, self.np.int16))


def wav_de(echantillons, frequence=FREQ):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frequence)
        w.writeframes(echantillons.astype("<i2").tobytes())
    return buf.getvalue()


# ======================================================================
#  LES SONS
# ======================================================================

SONS = {
    # (frequence Hz, duree s) ; 0 = silence
    "eveil":    [(880, 0.055), (1320, 0.07)],
    "fait":     [(1320, 0.06)],
    "erreur":   [(440, 0.09), (330, 0.12)],
    "bip":      [(1000, 0.09)],
    "fin":      [(990, 0.05), (660, 0.07)],
    "minuteur": [(880, 0.12), (0, 0.08), (1175, 0.12), (0, 0.25)] * 3,
}


def carillon(genre, volume=0.22, frequence=22050):
    """Un petit son, fabrique en memoire : aucun fichier."""
    notes = SONS.get(genre, SONS["bip"])
    amorti = int(0.008 * frequence)
    ech = []
    for f, d in notes:
        n = int(d * frequence)
        for i in range(n):
            env = min(1.0, i / amorti, (n - 1 - i) / amorti) if amorti else 1.0
            v = math.sin(2 * math.pi * f * i / frequence) * volume * max(0.0, env) if f else 0.0
            ech.append(int(v * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frequence)
        w.writeframes(struct.pack("<%dh" % len(ech), *ech))
    return buf.getvalue()


def duree_son(genre):
    return sum(d for _, d in SONS.get(genre, SONS["bip"]))


def jouer(genre):
    """Joue un son, sans attendre. Windows seulement ; ailleurs, rien."""
    try:
        import winsound
    except ImportError:
        return False
    octets = carillon(genre)
    # SND_MEMORY ne se joue pas en asynchrone : un fil a part.
    threading.Thread(target=lambda: winsound.PlaySound(octets, winsound.SND_MEMORY),
                     daemon=True).start()
    return True


# ======================================================================
#  LES COULEURS D'ETAT
# ======================================================================

# DEUX MODES, DEUX COULEURS. Jarvis est orange ; le mode psychologue -- le
# compagnon de BrainDebugger -- est bleu. L'etat (il ecoute, il transcrit, il
# reflechit, il parle) se lit dans le MOUVEMENT de la couleur, le mode dans sa
# teinte : d'un coup d'oeil, on sait a qui on parle.
COULEURS_MODE = {"jarvis": "#FF7A00", "psy": "#2563EB"}
COULEURS_REFLEXION = {"jarvis": "#FFC04D", "psy": "#7C3AED"}
COULEURS = {
    "fait":     "#22C55E",    # commande faite : vert, un instant
    "erreur":   "#EF4444",    # rate : rouge, un instant
    "minuteur": "#FFB000",    # un minuteur sonne : ambre qui clignote
}
ETATS_DU_MODE = ("ecoute", "comprend", "pense", "parle", "apprend")


def _hex(h):
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def couleur_etat(etat, t, couleurs=None, mode="jarvis"):
    """(r, v, b), gain pour l'etat donne a l'instant t (en secondes depuis
    son debut), dans le mode donne. Rend None pour un etat sans couleur.

    `couleurs` remplace ce qu'on veut : {"jarvis": "#...", "psy": "#...",
    "fait": ..., "erreur": ..., "minuteur": ...}."""
    perso = couleurs or {}
    mode = mode if mode in COULEURS_MODE else "jarvis"
    if etat in ETATS_DU_MODE:
        rvb = _hex(perso.get(mode, COULEURS_MODE[mode]))
    elif etat in COULEURS:
        rvb = _hex(perso.get(etat, COULEURS[etat]))
    else:
        return None
    if etat in ("ecoute", "apprend"):
        gain = 0.78 + 0.22 * math.sin(2 * math.pi * 0.8 * t)
    elif etat == "comprend":
        gain = 0.55 + 0.45 * abs(math.sin(math.pi * 1.4 * t))
    elif etat == "pense":
        # La reflexion : la teinte glisse vers sa voisine et revient, l'eclat
        # ondule. C'est l'etat qui dure, il doit se voir vivant.
        k = 0.5 + 0.5 * math.sin(2 * math.pi * 0.35 * t)
        autre = _hex(COULEURS_REFLEXION[mode])
        rvb = tuple(a + (b - a) * k for a, b in zip(rvb, autre))
        gain = 0.5 + 0.5 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.9 * t))
    elif etat == "parle":
        gain = 0.72 + 0.28 * abs(math.sin(2 * math.pi * 2.6 * t) * math.sin(2 * math.pi * 0.7 * t))
    elif etat == "minuteur":
        gain = 1.0 if int(t * 4) % 2 == 0 else 0.25
    else:
        gain = 1.0
    return tuple(float(c) for c in rvb), max(0.05, min(1.0, gain))


# ======================================================================
#  CE QUE LA PERSONNE A DIT
# ======================================================================

def sans_accents(s):
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def normaliser(texte):
    t = sans_accents(texte).lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9' -]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_EVEIL = re.compile(r"^(?:d?[jg]h?[ae]r+v[iy]+[sc]*e?|jarvi|jervis|arvis)$")


def retirer_mot_eveil(texte):
    """« Hey Jarvis, allume la lumiere. » -> « allume la lumiere. »

    La phrase part de deux secondes AVANT l'eveil : le mot y est, parfois
    precede d'un bout de conversation. On coupe tout jusqu'au mot, s'il est
    dans les huit premiers ; sinon on ne touche a rien."""
    mots = str(texte or "").split()
    for i, m in enumerate(mots[:8]):
        brut = normaliser(m).replace("'", "")
        if _EVEIL.match(brut):
            reste = " ".join(mots[i + 1:])
            return re.sub(r"^[\s,.;:!?…-]+", "", reste).strip()
    return str(texte or "").strip()


_UNITES = {"zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
           "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
           "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16}
_DIZAINES = {"vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60}


def nombre_fr(mots):
    """Lit un nombre au debut de la liste de mots (« 10 », « dix-sept »,
    « vingt et une », « quarante-cinq »). Rend (valeur, mots lus)."""
    if not mots:
        return None, 0
    if re.fullmatch(r"\d+(?:[.,]\d+)?", mots[0]):
        return float(mots[0].replace(",", ".")), 1
    morceaux = [(p, i) for i, m in enumerate(mots[:4]) for p in m.split("-") if p]
    if not morceaux:
        return None, 0
    p0 = morceaux[0][0]
    suivant = lambda k: morceaux[k][0] if k < len(morceaux) else ""
    if p0 in _DIZAINES:
        val, k = _DIZAINES[p0], 1
        if suivant(k) == "et" and suivant(k + 1) in ("un", "une"):
            val, k = val + 1, k + 2
        elif 1 <= _UNITES.get(suivant(k), 0) <= 9:
            val, k = val + _UNITES[suivant(k)], k + 1
    elif p0 in _UNITES:
        val, k = _UNITES[p0], 1
        if val == 10 and suivant(k) in ("sept", "huit", "neuf"):
            val, k = val + _UNITES[suivant(k)], k + 1
    else:
        return None, 0
    return float(val), morceaux[k - 1][1] + 1


def duree_fr(texte):
    """« 10 minutes », « une heure et demie », « un quart d'heure », « 30 s »
    -> secondes. None si on n'y lit pas de duree."""
    t = normaliser(texte)
    if re.search(r"\bdemi[- ]?heure\b", t):
        return 1800.0
    if re.search(r"\bquart d'?heure\b", t):
        return 900.0 * (3 if re.search(r"\btrois quarts?\b", t) else 1)
    mots = t.split()
    total, trouve, i = 0.0, False, 0
    while i < len(mots):
        v, n = nombre_fr(mots[i:])
        if v is None:
            i += 1
            continue
        unite = mots[i + n] if i + n < len(mots) else ""
        if re.fullmatch(r"h|heures?", unite):
            total += v * 3600
            trouve = True
            i += n + 1
            if i < len(mots) - 1 and mots[i] == "et" and mots[i + 1] in ("demie", "demi"):
                total += 1800
                i += 2
        elif re.fullmatch(r"min|mn|minutes?", unite):
            total += v * 60
            trouve = True
            i += n + 1
        elif re.fullmatch(r"s|sec|secondes?", unite):
            total += v
            trouve = True
            i += n + 1
        else:
            i += n
    return total if trouve and total > 0 else None


# ---------- ET EN ANGLAIS ----------
# « And in English as well » : Jarvis repond en anglais, et on peut lui parler
# dans les deux langues -- les commandes se lisent en francais ET en anglais,
# quelle que soit la langue de ses reponses.

_UNITS_EN = {"zero": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
             "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
             "eighteen": 18, "nineteen": 19}
_TENS_EN = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
            "eighty": 80, "ninety": 90}


def nombre_en(mots):
    """« 10 », « twenty-five », « an » (an hour) -> (valeur, mots lus)."""
    if not mots:
        return None, 0
    if re.fullmatch(r"\d+(?:[.,]\d+)?", mots[0]):
        return float(mots[0].replace(",", ".")), 1
    morceaux = [(p, i) for i, m in enumerate(mots[:3]) for p in m.split("-") if p]
    if not morceaux:
        return None, 0
    p0 = morceaux[0][0]
    if p0 in _TENS_EN:
        val, k = _TENS_EN[p0], 1
        if k < len(morceaux) and 1 <= _UNITS_EN.get(morceaux[k][0], 0) <= 9 and morceaux[k][0] not in ("a", "an"):
            val, k = val + _UNITS_EN[morceaux[k][0]], k + 1
    elif p0 in _UNITS_EN:
        val, k = _UNITS_EN[p0], 1
    else:
        return None, 0
    return float(val), morceaux[k - 1][1] + 1


def duree_en(texte):
    """« 10 minutes », « an hour and a half », « half an hour », « a quarter of
    an hour », « 90 seconds », « a ten minute timer » -> secondes, ou None."""
    t = normaliser(texte).replace("-", " ")
    if re.search(r"\bhalf an hour\b|\bhalf hour\b", t) and not re.search(r"\band a half\b", t):
        return 1800.0
    if re.search(r"\bquarter of an hour\b|\bquarter hour\b", t):
        return 900.0 * (3 if re.search(r"\bthree quarters?\b", t) else 1)

    # « one and a half hours » : la demie AVANT l'unite
    def _demie(m):
        v, n = nombre_en([m.group(1)])
        return "%g %s" % (v + 0.5, m.group(2)) if v is not None else m.group(0)
    t = re.sub(r"\b(\d+|[a-z]+) and a half (hours?|hrs?|minutes?|mins?)\b", _demie, t)
    mots = t.split()
    total, trouve, i = 0.0, False, 0
    while i < len(mots):
        v, n = nombre_en(mots[i:])
        if v is None:
            i += 1
            continue
        unite = mots[i + n] if i + n < len(mots) else ""
        # « an hour and a half » : la demie APRES l'unite
        demi = mots[i + n + 1:i + n + 4] == ["and", "a", "half"]
        if re.fullmatch(r"h|hrs?|hours?", unite):
            total += v * 3600 + (1800 if demi else 0)
            trouve, i = True, i + n + (4 if demi else 1)
        elif re.fullmatch(r"mins?|minutes?", unite):
            total += v * 60 + (30 if demi else 0)
            trouve, i = True, i + n + (4 if demi else 1)
        elif re.fullmatch(r"s|secs?|seconds?", unite):
            total += v
            trouve, i = True, i + n + 1
        else:
            i += n
    return total if trouve and total > 0 else None


def duree(texte):
    """Une duree dite en francais ou en anglais."""
    return duree_fr(texte) or duree_en(texte)


def dire_duree(secondes, langue="fr"):
    s = int(round(secondes))
    h, reste = divmod(s, 3600)
    m, s = divmod(reste, 60)
    morceaux = []
    if langue == "en":
        if h:
            morceaux.append("%d hour%s" % (h, "s" if h > 1 else ""))
        if m:
            morceaux.append("%d minute%s" % (m, "s" if m > 1 else ""))
        if s and not h:
            morceaux.append("%d second%s" % (s, "s" if s > 1 else ""))
        return " and ".join(morceaux) or "0 seconds"
    if h:
        morceaux.append("%d heure%s" % (h, "s" if h > 1 else ""))
    if m:
        morceaux.append("%d minute%s" % (m, "s" if m > 1 else ""))
    if s and not h:
        morceaux.append("%d seconde%s" % (s, "s" if s > 1 else ""))
    return " et ".join(morceaux) or "0 seconde"


COULEURS_NOMMEES = {
    "rouge": "#FF1A1A", "orange": "#FF7A00", "jaune": "#FFD000", "vert": "#22E052",
    "bleu": "#1E5BFF", "cyan": "#00D5FF", "turquoise": "#16E0C0", "violet": "#8B3DFF",
    "mauve": "#B266FF", "rose": "#FF4FA3", "magenta": "#FF00C8", "blanc": "#FFFFFF",
    "ambre": "#FFB000", "indigo": "#4B3DFF", "or": "#FFC21A", "dore": "#FFC21A",
}

# Les memes couleurs, dites en anglais : le nom francais reste celui qu'affiche
# le panneau.
COULEURS_EN = {"red": "rouge", "orange": "orange", "yellow": "jaune", "green": "vert", "blue": "bleu",
               "cyan": "cyan", "turquoise": "turquoise", "purple": "violet", "violet": "violet",
               "mauve": "mauve", "pink": "rose", "magenta": "magenta", "white": "blanc", "amber": "ambre",
               "indigo": "indigo", "gold": "or", "golden": "or"}


def _couleur_nommee(mot):
    """bleue, vertes, violette, blanche, blue -> la couleur."""
    if mot in COULEURS_EN:
        return COULEURS_EN[mot]
    for c in (mot, mot.rstrip("s"), mot.rstrip("s").rstrip("e"),
              re.sub(r"(?:te|che)s?$", lambda m_: "c" if m_.group(0).startswith("ch") else "", mot)):
        if c in COULEURS_NOMMEES:
            return c
    return None


_LUMIERE = r"(?:lumieres?|guirlandes?|leds?|lampes?|lumiere)"
_MODES = {"ecran": "ecran", "son": "son", "musique": "son", "application": "applications",
          "applications": "applications", "appli": "applications", "applis": "applications",
          "regle": "applications", "regles": "applications", "mixte": "mixte"}

_SILENCE = {"stop", "tais toi", "tais-toi", "chut", "silence", "arrete", "ca suffit",
            "arrete de parler", "stop stop", "c'est bon arrete", "ta gueule", "ferme la",
            "shut up", "quiet", "be quiet", "hush", "enough", "that's enough", "stop talking",
            "okay stop", "ok stop", "stop it"}
# LA FIN D'UNE CONVERSATION. « Non rien », « oublie », « degage » : on se tait,
# on n'ecoute plus la suite, et le mode psychologue se referme. Une phrase
# COURTE, faite de ces mots-la et de politesses autour -- « non merci c'est
# tout » oui, « j'ai rien fait de la journee » non.
_FIN = re.compile(
    r"^(?:(?:non|bon|ben|euh|ah|oh|finalement|en fait|merci|pardon|ok|okay|d'accord|"
    r"c'est bon|jarvis|bah)\s+)*"
    r"(?:non|merci|rien(?: du tout)?|c'est rien|oublie(?: ca| tout| c'est pas grave)?|"
    r"laisse(?: tomber| beton| moi)?|degage|casse toi|va t'en|dehors|du vent|"
    r"c'est tout|c'est bon|ca ira|ca va aller|pas besoin|au revoir|a plus|salut|bye|"
    r"fin de (?:la )?conversation|termine|annule|annuler|fausse alerte|non merci|"
    r"rien merci|rien de rien|c'est fini)"
    r"(?:\s+(?:merci|jarvis|c'est bon|ca ira|c'est tout|laisse|pour l'instant|pour le moment))*$")
# Et en anglais : « never mind », « forget it », « that'll be all »...
_FIN_EN = re.compile(
    r"^(?:(?:no|well|oh|um|uh|actually|thanks|thank you|okay|ok|sorry|jarvis|right)\s+)*"
    r"(?:no|nope|nothing(?: at all)?|never ?mind|forget it|forget about it|forget that|"
    r"cancel|that's all|that is all|that'll be all|that will be all|that's it|go away|leave it|"
    r"leave me alone|dismissed|goodbye|good bye|bye(?: bye)?|see you(?: later)?|false alarm|"
    r"end (?:the )?conversation|we're done|i'm done|all good|i'm good|no thanks|no thank you|"
    r"nothing thanks|it's nothing)"
    r"(?:\s+(?:thanks|thank you|jarvis|for now|that's all|then))*$")


# LE RENVOYER. « Quand je lui dis "degage" il devrait partir, pareil pour
# "pars" ou "get away" ou "stop" ou "re-pars". » Plus sec que la fin d'une
# conversation : il se tait sur-le-champ, n'ecoute plus la suite, et meme au
# psychologue il ne dit rien en partant (« au revoir », lui, laisse le
# majordome placer un mot). Seul, ou presque seul : « degage » oui,
# « je voudrais que tu degages ce bug » non. La transcription ecrit « pars »
# comme elle l'entend -- « part », « par » -- et « degage » parfois en deux
# mots ; une phrase faite de ce seul mot ne peut vouloir dire que ca.
_RENVOI = re.compile(
    r"^(?:(?:allez|aller|bon|ben|bah|hop|allez hop|ok|okay|non|oh|eh|jarvis|mais|maintenant|"
    r"alright|okay|now|just|come on|oh|jarvis)\s+)*"
    r"(?:degage[sz]?|degager|de gage|des gages|"
    r"pars|part|par|repars|repart|re pars|re part|re par|vas y pars|va t'en|va t en|vas t'en|"
    r"casse toi|barre toi|tire toi|fous le camp|fiche le camp|file|ouste|disparais|du balai|"
    r"stop|stop stop|arrete tout|"
    r"get away|go away|get lost|get out|leave|leave now|scram|beat it|begone|buzz off|"
    r"off you go|piss off|shoo)"
    r"(?:\s+(?:jarvis|maintenant|tout de suite|merci|s'il te plait|stp|now|please|thanks|"
    r"right now|then|alors|allez|toi|d'ici|from here|la))*$")


def renvoi(texte):
    """« Degage », « pars », « get away », « stop », « re-pars » : il part."""
    t = normaliser(texte).replace("-", " ").strip(" '")
    return bool(t) and len(t.split()) <= 6 and bool(_RENVOI.match(t))


# L'AU REVOIR. « Jarvis devrait pouvoir s'eteindre lorsqu'il repond "a bientot
# monsieur" ou "au revoir monsieur", apres que l'utilisateur lui a dit "salut"
# ou "au revoir". » Ces mots-la meritent une reponse -- puis il n'ecoute plus.
# `adieu` rend ce qu'on lui a dit, pour qu'il reponde sur le meme ton : une
# bonne nuit appelle une bonne nuit.
_ADIEU = re.compile(
    r"^(?:(?:bon|ben|allez|ok|okay|alors|bah|merci|thanks|thank you|well|right|jarvis)\s+)*"
    r"(au revoir|salut|bye|bye bye|a plus(?: tard)?|a tout(?: a l'heure)?|a bientot|a demain|bonne nuit|"
    r"bonne soiree|bonne journee|ciao|tchao|goodbye|good bye|good night|goodnight|see you(?: later| soon)?|"
    r"see ya|later|farewell)"
    r"(?:\s+(?:jarvis|merci|thanks|thank you|a plus|a bientot|a demain|bonne nuit|et merci|"
    r"mon ami|buddy|pal|then|alors))*$")


def adieu(texte):
    """« Salut », « au revoir », « bonne nuit », « goodbye »... : rend le mot
    qu'on lui a dit (normalise), ou None."""
    t = normaliser(texte).replace("-", " ").strip(" '")
    if not t or len(t.split()) > 6:
        return None
    m = _ADIEU.match(t)
    return m.group(1) if m else None


def fin_de_conversation(texte):
    t = normaliser(texte).replace("-", " ").strip(" '")
    return bool(t) and len(t.split()) <= 7 and bool(_FIN.match(t) or _FIN_EN.match(t))


# LES MODES. « Psychologue », « notes psy », « notes » : la conversation passe
# au compagnon de BrainDebugger (bleu). « Mode Jarvis », « quitte le mode
# psy » : retour a Jarvis (orange). Rend (mode, reste) -- le reste est ce qui
# suit dans la meme phrase, a envoyer tel quel -- ou None.
# « IL FAUT FAIRE GAFFE QUE LE MODE PSYCHOLOGUE N'ARRIVE PAS TROP FACILEMENT. »
# Il arrivait sur tout ce qui COMMENCAIT par ces mots : « psychologie de la
# foule, c'est quoi ? », « le psy m'a dit de dormir plus », « therapy is
# expensive », « notes de frais a rendre » -- et la phrase partait au journal.
# On n'y passe plus que si on le DEMANDE : la phrase entiere est la demande
# (« psychologue », « passe en mode psy »), elle commence par un verbe de
# bascule (« passe en mode psy, j'ai mal dormi »), ou le mot est une
# APOSTROPHE, suivi d'une virgule ou d'un point dans ce que la transcription
# a ecrit (« Psychologue, j'ai mal dormi »). Parler DU psy ne suffit pas.
_POLI = r"(?:\s+(?:s'il te plait|s'il vous plait|stp|svp|merci|maintenant|please|thanks|now))*"
_MOT_PSY = r"(?:psychologue|psy|therapeute|therapist|therapy|psych|psychologist|counsell?or)"
_BASCULE_PSY = (r"(?:passe|passons|mets toi|mets-toi|bascule|va|on passe|je veux|je voudrais|"
                r"je veux parler (?:a|au)|switch|go|change|put me|let's go|i want|take me)")
_VERS_PSY_SEUL = re.compile(
    r"^(?:" + _BASCULE_PSY + r"\s+(?:back\s+)?(?:en\s+|au\s+|a la\s+|a\s+|to\s+|into\s+|in\s+)?)?"
    r"(?:le\s+|la\s+|the\s+)?(?:mode\s+)?" + _MOT_PSY + r"(?:\s+mode)?" + _POLI + "$")
_VERS_PSY_VERBE = re.compile(
    r"^(?:(?:passe|passons|mets toi|mets-toi|bascule|on passe)\s+(?:en|au)\s+(?:mode\s+)?"
    r"(?:psychologue|psy|therapeute)|mode\s+(?:psychologue|psy)"
    r"|(?:switch|go|change|put me|take me)\s+(?:back\s+)?(?:to|into)\s+(?:the\s+)?"
    r"(?:therapist|therapy|psych|psy)\s+mode|(?:therapist|psych)\s+mode)\b")
_APOSTROPHE_PSY = re.compile(r"^\s*(?:psychologue|psy|th[eé]rapeute|therapist)\s*[,:;.!?\u2026]", re.I)
_VERS_NOTES_PSY = re.compile(r"^(?:mes\s+|les\s+|my\s+)?(?:notes?\s+(?:psy|psychologue|de psy)|"
                             r"(?:psych|psy|therapy|therapist)\s+notes?|"
                             r"(?:une\s+|a\s+)?notes?\s+(?:pour|au|a|for)\s+(?:le\s+|la\s+|mon\s+|ma\s+|my\s+|the\s+)?"
                             r"(?:psy|psychologue|therapist|therapy))\b")
# UNE NOTE, SI ON LA DEMANDE : « note que... », « prends une note », « take a
# note » -- pas « notes de frais » ni « noter les courses ».
_VERS_NOTES = re.compile(
    r"^(?:notes?" + _POLI + r"$|note (?:que|qu'|ca|cela|dans mon journal|pour moi|that)\b|"
    r"prends? note\b|(?:prends|prend|fais|ajoute|ecris|take|make|add|write)\s+"
    r"(?:une\s+|des\s+|a\s+|some\s+)?notes?\b)")
# ET ON EN SORT FACILEMENT : « retourne au mode Jarvis », « pars du mode
# psychologue », « sors du psy », « plus de psy », « back to Jarvis ».
_AVANT = r"^(?:(?:ok|okay|bon|allez|bah|ben|euh|jarvis|non|alors|maintenant|stp|please)\s+)*"
_VERS_JARVIS = re.compile(
    _AVANT + r"(?:"
    r"(?:(?:passe|reviens|repasse|retour|retourne|bascule|on repasse|redeviens|reprends|remets toi|"
    r"je veux|je veux parler a|go|switch|change|get|go back|come back|take me back)\s+"
    r"(?:back\s+)?(?:en\s+|a\s+|au\s+|le\s+|to\s+)?)?(?:(?:le\s+|the\s+)?mode\s+)?"
    r"(?:jarvis|normal)(?:\s+mode)?"
    r"|(?:quitte|quitter|sors|sort|sortir|pars|part|partir|arrete|arreter|stop|ferme|fermer|termine|"
    r"fin|laisse tomber|oublie|exit|leave|quit|close|end)\s+(?:du\s+|de\s+|le\s+|la\s+|avec le\s+|"
    r"the\s+)?(?:mode\s+)?(?:psy|psychologue|psychologie|therapeute|therapist|therapy|psych)(?:\s+mode)?"
    r"|(?:plus de|assez de|fini le|fini la|c'est fini le|c'est bon pour le|no more)\s+"
    r"(?:mode\s+)?(?:psy|psychologue|therapist|therapy)"
    # « Jarvis ? Re ! » : de retour aupres du majordome (le mot d'eveil est deja
    # retire -- il reste « re »)
    r"|re|re jarvis|jarvis re|me revoila|je suis de retour|c'est re moi|i'm back|im back|"
    r"back to jarvis|back to normal|normal mode|jarvis mode)" + _POLI + "$")


def _apres(texte, n_mots):
    """Le texte original moins ses n premiers mots (comptes comme normaliser)."""
    mots = [m for m in str(texte).split() if normaliser(m)]
    reste = " ".join(mots[n_mots:])
    return re.sub(r"^[\s,.;:!?\u2026-]+", "", reste).strip()


def note_a_ecrire(texte):
    """« Note que... », « prends une note », « ecris une note » -- mais pas
    « note pour le psy » ni « notes psy ». Avec ses mains ouvertes, Jarvis
    l'ecrit lui-meme (et la depose chez le psychologue, sauf une liste de
    courses ou une petite note pratique) ; mains fermees, elle part au
    psychologue comme avant."""
    t = normaliser(texte).strip(" -'")
    return bool(t) and bool(_VERS_NOTES.match(t)) and not _VERS_NOTES_PSY.match(t) and not _VERS_PSY_VERBE.match(t)


def changement_de_mode(texte):
    t = normaliser(texte).strip(" -'")
    if not t:
        return None
    if _VERS_JARVIS.match(t):
        return ("jarvis", "")
    if _VERS_PSY_SEUL.match(t):
        return ("psy", "")
    m = _APOSTROPHE_PSY.match(str(texte))
    if m:
        reste = str(texte)[m.end():].strip()
        return ("psy", "" if normaliser(reste) in ("", "s'il te plait", "stp", "merci") else reste)
    for motif, garder in ((_VERS_PSY_VERBE, False), (_VERS_NOTES_PSY, False), (_VERS_NOTES, True)):
        m = motif.match(t)
        if m:
            # « Note que j'ai mal dormi » : la phrase entiere part au journal,
            # c'est une note. « Psychologue, j'ai mal dormi » : le mot de
            # bascule n'en fait pas partie.
            if garder:
                return ("psy", str(texte).strip() if t != m.group(0) else "")
            reste = _apres(texte, len(m.group(0).split()))
            if normaliser(reste) in ("", "s'il te plait", "stp", "merci", "s'il vous plait", "svp"):
                reste = ""
            return ("psy", reste)
    return None


_LUMIERE_EN = r"(?:lights?|leds?|lamps?|garland|light strip|strip)"
_MODES_EN = {"screen": "ecran", "sound": "son", "music": "son", "audio": "son", "app": "applications",
             "apps": "applications", "application": "applications", "applications": "applications",
             "rules": "applications", "mixed": "mixte", "mix": "mixte"}


def _comprendre_en(t, mots):
    """Les memes commandes, dites en anglais -- et aussi prudent : une phrase
    courte, qui commence comme une commande. `t` est deja normalise."""
    L = _LUMIERE_EN
    if len(mots) <= 22:
        m = re.match(r"^(?:set|start|put|make|run)?\s*(?:me\s+)?(?:up\s+)?(?:a|an|the)?\s*(?:timer|countdown)"
                     r"\s+(?:for|of|on)?\s*(.+)$", t)
        if m and duree_en(m.group(1)):
            return {"action": "minuteur", "secondes": duree_en(m.group(1)), "quoi": ""}
        m = re.match(r"^(?:set|start|put|make|run)?\s*(?:me\s+)?(?:a|an|the)?\s*(.+?)\s+timer$", t)
        if m and duree_en(m.group(1)):
            return {"action": "minuteur", "secondes": duree_en(m.group(1)), "quoi": ""}
        m = re.match(r"^remind me\s+(.+)$", t)
        if m:
            reste = m.group(1)
            q = re.match(r"^in\s+(.+?)\s+(?:to|that|about)\s+(.+)$", reste)
            q2 = re.match(r"^(?:to|that|about)\s+(.+?)\s+in\s+(.+)$", reste)
            if q and duree_en(q.group(1)):
                return {"action": "minuteur", "secondes": duree_en(q.group(1)), "quoi": q.group(2)}
            if q2 and duree_en(q2.group(2)):
                return {"action": "minuteur", "secondes": duree_en(q2.group(2)), "quoi": q2.group(1)}
            q3 = re.match(r"^in\s+(.+)$", reste)
            if q3 and duree_en(q3.group(1)):
                return {"action": "minuteur", "secondes": duree_en(q3.group(1)), "quoi": ""}
        if re.match(r"^(?:cancel|stop|clear|delete|kill|remove)\s+(?:the\s+|my\s+|all\s+(?:the\s+|my\s+)?)?"
                    r"(?:timers?|reminders?|countdowns?)$", t):
            return {"action": "minuteurs_annuler"}
    if len(mots) > 12:
        return None
    if re.match(r"^(?:stop listening|go to sleep|sleep mode|go to standby|mute yourself|"
                r"turn off (?:the )?(?:microphone|mic))$", t):
        return {"action": "dormir"}
    if re.match(r"^(?:what time is it|what's the time|what is the time|tell me the time|do you have the time|"
                r"time please|current time)\b", t):
        return {"action": "heure"}
    if re.match(r"^(?:what's the date|what is the date|what day is it|what's today's date|what is today's date|"
                r"what date is it|today's date|what day is today)\b", t):
        return {"action": "date"}
    m = re.match(r"^(?:switch|change|set|put|go)\s+(?:the\s+)?(?:lights?\s+)?(?:to|into|in)\s+(\w+)\s+mode$", t) \
        or re.match(r"^(\w+)\s+mode$", t)
    if m and m.group(1) in _MODES_EN:
        return {"action": "mode", "mode": _MODES_EN[m.group(1)]}
    qui = r"(?:the |my |all the )?"
    if re.match(r"^(?:(?:turn|switch|shut|put)\s+off\s+" + qui + L + r"|(?:turn|switch|shut|put)\s+" + qui + L
                + r"\s+off|" + L + r"\s+off|kill " + qui + L + r"|lights? out)$", t):
        return {"action": "lumiere_off"}
    if re.match(r"^(?:(?:turn|switch|put)\s+on\s+" + qui + L + r"|(?:turn|switch|put)\s+" + qui + L + r"\s+on|"
                + L + r"\s+on)$", t):
        return {"action": "lumiere_on"}
    if re.match(r"^(?:(?:set|put|turn|switch|reset|bring)\s+" + qui + L + r"\s+(?:back\s+)?(?:to\s+)?"
                r"(?:normal|auto|automatic)|" + L + r"\s+(?:back\s+)?(?:to\s+)?(?:normal|auto|automatic)|normal "
                + L + r"|reset " + qui + L + r"|automatic " + L + r")$", t):
        return {"action": "lumiere_normale"}
    m = re.match(r"^(?:(?:make|turn|set|change|switch|paint|put)\s+)?" + qui + L + r"\s+(?:to\s+|in\s+)?(\w+)$", t) \
        or re.match(r"^(?:make it|go|turn|set it to|change to)\s+(\w+)$", t) \
        or re.match(r"^(\w+)\s+" + L + r"$", t)
    nom = _couleur_nommee(m.group(1)) if m else None
    if nom:
        return {"action": "lumiere_couleur", "couleur": COULEURS_NOMMEES[nom], "nom": nom}
    if re.match(r"^(?:open|show|launch|pull up|bring up)\s+(?:me\s+)?(?:my |the )?"
                r"(?:braindebugger|brain debugger|brain|journal|diary|site)$", t):
        return {"action": "ouvrir_site"}
    if re.match(r"^(?:open|show)\s+(?:me\s+)?(?:the )?(?:machi ?tool|machitool|panel|settings)$", t):
        return {"action": "ouvrir_panneau"}
    if re.match(r"^(?:sync|synchronise|synchronize|send my day|upload my day|sync my day)\b", t):
        return {"action": "synchro"}
    return None


def comprendre(texte, raccourcis=()):
    """La commande locale que dit ce texte, ou None : alors c'est pour le
    compagnon.

    PRUDENT PAR CONSTRUCTION : une commande est une phrase COURTE qui
    commence comme une commande. « Je me sens eteint, coupe de tout » ne doit
    pas eteindre la lumiere -- c'est au compagnon qu'on vient de le dire."""
    t = normaliser(texte).strip(" -'")
    if not t:
        return None
    t = re.sub(r"^(?:s'il te plait|stp|dis|dis moi|est ce que tu peux|tu peux|peux tu|"
               r"tu pourrais|pourrais tu|please|could you|can you|would you|will you)\s+", "", t)
    t = re.sub(r"\s+(?:s'il te plait|stp|merci|please|thanks|thank you)$", "", t)
    mots = t.split()

    if t in _SILENCE:
        return {"action": "silence"}
    if fin_de_conversation(texte):
        return {"action": "fin"}

    for r in raccourcis or ():
        dit = normaliser(r.get("dit", ""))
        if dit and (t == dit or t.startswith(dit + " ")) and r.get("ouvre"):
            return {"action": "ouvrir", "cible": str(r["ouvre"]), "nom": r.get("dit", "")}

    # « Juste "Jarvis" » : il faut qu'il connaisse la voix de la personne -- on
    # le lui demande a voix haute.
    if re.match(r"^(?:apprends?|retiens|enregistre)\s+(?:ma voix|mon jarvis|a reconnaitre ma voix)$"
                r"|^(?:learn|remember)\s+my\s+(?:voice|jarvis)$", t):
        return {"action": "apprendre"}

    # « Verrouille » : ses mains sur le PC se referment tout de suite, sans
    # attendre la fin des dix minutes.
    if re.match(r"^(?:verrouille|reverrouille|ferme|referme)(?:\s+(?:l'acces|tout|les acces|l'ordi|le pc))?$"
                r"|^(?:lock|lock (?:it|access|everything|up))$", t):
        return {"action": "verrouiller"}

    # « Mets Get Lucky sur YouTube » : ici, sans passer par le modele -- plus
    # vite, et il ne peut pas se tromper d'outil.
    m = re.match(r"^(?:mets?|lance|joue|passe|ouvre|cherche|trouve)(?: moi)?(?: (?:la|une|le|un) "
                 r"(?:video|musique|chanson|clip|morceau))?(?: de| du| des)? (.+?) sur (?:youtube|you tube)$"
                 r"|^(?:youtube|you tube) (.+)$"
                 r"|^(?:play|put on|open|search)(?: me)? (.+?) on (?:youtube|you tube)$", t.replace("-", " "))
    if m:
        q = next(g for g in m.groups() if g).strip()
        if q and len(q.split()) <= 14:
            return {"action": "youtube", "recherche": q}

    en = _comprendre_en(t, mots)
    if en:
        return en

    # Minuteurs et rappels : peuvent etre un peu plus longs.
    if len(mots) <= 22:
        m = re.match(r"^(?:mets|lance|demarre|programme|fais)?\s*(?:moi\s+)?(?:un|le)?\s*"
                     r"(?:minuteur|timer|chrono(?:metre)?|compte a rebours)\s+(?:de|d'|pour|sur)?\s*(.+)$", t)
        if m:
            s = duree_fr(m.group(1))
            if s:
                return {"action": "minuteur", "secondes": s, "quoi": ""}
        m = re.match(r"^rappelle(?:[- ]moi)?\s+(.+)$", t)
        if m:
            reste = m.group(1)
            q = re.match(r"^(?:dans|d'ici)\s+(.+?)\s+(?:de|d'|qu'|que)\s*(.+)$", reste)
            q2 = re.match(r"^(?:de|d'|qu'|que)\s*(.+?)\s+(?:dans|d'ici)\s+(.+)$", reste)
            if q and duree_fr(q.group(1)):
                return {"action": "minuteur", "secondes": duree_fr(q.group(1)), "quoi": q.group(2)}
            if q2 and duree_fr(q2.group(2)):
                return {"action": "minuteur", "secondes": duree_fr(q2.group(2)), "quoi": q2.group(1)}
            q3 = re.match(r"^(?:dans|d'ici)\s+(.+)$", reste)
            if q3 and duree_fr(q3.group(1)):
                return {"action": "minuteur", "secondes": duree_fr(q3.group(1)), "quoi": ""}
        if re.match(r"^(?:annule|arrete|stoppe|coupe)\s+(?:le|les|mon|mes)\s+(?:minuteurs?|timers?|rappels?)$", t):
            return {"action": "minuteurs_annuler"}

    if len(mots) > 12:
        return None

    if re.match(r"^(?:arrete|arreter|desactive|coupe|mets toi en veille|va dormir)\b.*"
                r"\b(?:d'ecouter|ecouter|l'ecoute|le micro|jarvis)$", t) or \
            t in ("va dormir", "mets toi en veille", "dors", "arrete d'ecouter"):
        return {"action": "dormir"}

    if re.match(r"^(?:quelle heure|il est quelle heure|l'heure|donne moi l'heure|t'as l'heure|tu as l'heure)", t):
        return {"action": "heure"}
    if re.match(r"^(?:on est quel jour|quel jour|quelle date|on est le combien|c'est quel jour|"
                r"quel jour on est|on est quelle date)", t):
        return {"action": "date"}

    m = re.match(r"^(?:passe|mets|change|bascule)\s+(?:(?:la\s+)?(?:lumiere|guirlande)\s+)?(?:en|au|sur)\s+mode\s+(\w+)$", t) \
        or re.match(r"^mode\s+(\w+)$", t)
    if m and m.group(1) in _MODES:
        return {"action": "mode", "mode": _MODES[m.group(1)]}

    if re.match(r"^(?:eteins?|eteint|coupe|ferme)\s+(?:la |les |ma |mes )?" + _LUMIERE + r"$", t):
        return {"action": "lumiere_off"}
    m = re.match(r"^(?:(?:mets|passe|allume|change|colore)\s+)?(?:(?:la |les |ma |mes )?" + _LUMIERE +
                 r"\s+)?(?:en\s+)?(?:couleur\s+)?([a-z]+)$", t)
    nom = _couleur_nommee(m.group(1)) if m else None
    if nom and len(mots) >= 2:
        return {"action": "lumiere_couleur", "couleur": COULEURS_NOMMEES[nom], "nom": nom}
    if re.match(r"^(?:(?:remets|rends|reprends|lumiere|couleur)\b.*\bnormale?s?|relache\b.*|"
                r"remets .*comme avant|lumiere automatique)$", t):
        return {"action": "lumiere_normale"}
    if re.match(r"^(?:allume|rallume)\s+(?:la |les |ma |mes )?" + _LUMIERE + r"$", t):
        return {"action": "lumiere_on"}

    if re.match(r"^(?:ouvre|affiche|montre)\s+(?:moi\s+)?(?:le |mon |la )?"
                r"(?:braindebugger|brain debugger|brain|journal|site)$", t):
        return {"action": "ouvrir_site"}
    if re.match(r"^(?:ouvre|affiche|montre)\s+(?:moi\s+)?(?:le |la |les )?"
                r"(?:machi ?tool|machitool|panneau|reglages)$", t):
        return {"action": "ouvrir_panneau"}
    if re.match(r"^(?:synchronise|synchro|lance la synchro|envoie ma journee|synchronise ma journee)\b", t):
        return {"action": "synchro"}
    return None


def pour_la_voix(texte, plafond=1200, lien="le lien"):
    """Le texte d'une reponse, tel qu'on peut le lire a voix haute : sans
    markdown, sans liens, sans emojis, et coupe a une fin de phrase."""
    t = str(texte or "")
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", lien, t)
    t = re.sub(r"[*_`#>|~]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = "".join(c for c in t if not (unicodedata.category(c) in ("So", "Cs", "Sk")
                                     or 0x1F000 <= ord(c) <= 0x1FAFF))
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > plafond:
        coupe = max(t.rfind(". ", 0, plafond), t.rfind("? ", 0, plafond), t.rfind("! ", 0, plafond))
        t = t[:coupe + 1] if coupe > plafond // 3 else t[:plafond].rsplit(" ", 1)[0] + "…"
    return t


# ======================================================================
#  LA VOIX -- PIPER, UNE SYNTHESE NEURONALE QUI TOURNE SUR LE POSTE
#
#  La voix de Windows (SAPI) lit, mais elle sonne comme un GPS de 2008. Piper
#  (github.com/rhasspy/piper, MIT ; il appelle espeak-ng, GPL, en programme a
#  part) lit avec une vraie voix, sur le processeur, vingt fois plus vite que
#  le temps reel. Rien ne part sur Internet : le texte entre dans piper.exe,
#  le son en sort, et va aux haut-parleurs sans passer par le disque.
#
#  « Comme Jarvis » : une voix d'homme posee, un debit un peu lent, des
#  silences entre les phrases. PAS la voix d'un acteur : imiter la voix d'une
#  personne reelle, c'est lui prendre quelque chose qui est a elle.
# ======================================================================

PIPER_MOTEUR = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
PIPER_VOIX_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
PIPER_VOIX_GITHUB = "https://github.com/rhasspy/piper/releases/download/v0.0.2/"

VOIX_PIPER = {
    "fr_FR-tom-medium":   {"nom": "Tom -- francais, homme, pose", "hf": "fr/fr_FR/tom/medium/"},
    "fr_FR-gilles-low":   {"nom": "Gilles -- francais, homme, plus leger", "hf": "fr/fr_FR/gilles/low/",
                           "github": "voice-fr-gilles-low"},
    "fr_FR-upmc-medium":  {"nom": "Pierre -- francais, homme, clair", "hf": "fr/fr_FR/upmc/medium/",
                           "locuteur": "pierre"},
    "fr_FR-siwis-medium": {"nom": "Siwis -- francais, femme", "hf": "fr/fr_FR/siwis/medium/",
                           "github": "voice-fr-siwis-medium"},
    "en_GB-alan-medium":  {"nom": "Alan -- anglais britannique, homme (lit le francais avec un accent)",
                           "hf": "en/en_GB/alan/medium/"},
}
VOIX_DEFAUT = "fr_FR-tom-medium"
VOIX_SECOURS = "fr_FR-gilles-low"       # aussi publiee sur GitHub, si Hugging Face ne repond pas


def frequence_du_modele(chemin_json, defaut=22050):
    try:
        with open(chemin_json, encoding="utf-8") as f:
            return int(json.load(f)["audio"]["sample_rate"])
    except Exception:
        return defaut


class Phonemiseur:
    """Le texte devient des phonemes (API) par espeak-ng -- la bibliotheque
    livree avec Piper, appelee directement : c'est ce que fait piper.exe, sans
    relancer un programme a chaque phrase.

    Meme decoupage que piper-phonemize : une proposition a la fois, sa
    ponctuation ajoutee a la fin, un espace entre deux propositions, et une
    phrase par ligne de sortie (chacune se synthetise a part, la premiere
    sonne pendant que la suivante se calcule)."""

    PONCTUATION = {".": ".", "?": "?", "!": "!", ",": ",", ":": ":", ";": ";",
                   "\u2026": ".", "\u00bb": "", "\u00ab": ""}

    # ESPEAK-NG N'A QU'UNE VOIX PAR PROCESSUS. La bibliotheque garde sa langue
    # en etat global : deux phonemiseurs (le francais du mode psy, l'anglais de
    # Jarvis) dans le meme processus se la voleraient -- le second chargeait
    # l'anglais, et le premier lisait alors le francais avec. Elle est donc
    # initialisee UNE fois, et chaque phonemiseur remet SA voix, sous verrou,
    # a chaque proposition.
    _BIBLIS = {}
    _VERROU = threading.Lock()

    def __init__(self, bibliotheque, dossier_donnees, voix="fr"):
        import ctypes
        self.ct = ctypes
        self.voix = voix.encode("ascii")
        with Phonemiseur._VERROU:
            cle = (os.path.abspath(bibliotheque), os.path.abspath(dossier_donnees))
            deja = Phonemiseur._BIBLIS.get(cle)
            if deja is None:
                lib = ctypes.cdll.LoadLibrary(bibliotheque)
                lib.espeak_Initialize.restype = ctypes.c_int
                lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
                lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
                lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
                lib.espeak_TextToPhonemes.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int]
                # 2 = AUDIO_OUTPUT_SYNCHRONOUS : espeak ne touche a aucun peripherique.
                # Le chemin dans l'encodage du systeme : espeak l'ouvre avec fopen().
                chemin = dossier_donnees.encode("mbcs" if os.name == "nt" else "utf-8")
                if lib.espeak_Initialize(2, 0, chemin, 0) < 0:
                    raise RuntimeError("espeak-ng ne s'initialise pas (%s)" % dossier_donnees)
                deja = Phonemiseur._BIBLIS[cle] = {"lib": lib, "voix": None}
            self.partage = deja
            self.lib = deja["lib"]
            self._poser_voix()

    def _poser_voix(self):
        """A appeler sous le verrou."""
        if self.partage["voix"] != self.voix:
            if self.lib.espeak_SetVoiceByName(self.voix) != 0:
                self.partage["voix"] = None
                raise RuntimeError("voix espeak-ng inconnue : %s" % self.voix.decode())
            self.partage["voix"] = self.voix

    def _proposition(self, texte):
        ct = self.ct
        tampon = ct.create_string_buffer(texte.encode("utf-8"))
        ptr = ct.c_void_p(ct.addressof(tampon))
        morceaux = []
        with Phonemiseur._VERROU:
            self._poser_voix()
            while ptr.value:
                r = self.lib.espeak_TextToPhonemes(ct.byref(ptr), 1, 0x02)   # UTF-8 -> API
                if r:
                    morceaux.append(r.decode("utf-8"))
        return " ".join(m.strip() for m in morceaux if m.strip())

    def phrases(self, texte):
        """[[phonemes de la phrase 1], [phrase 2], ...] -- des caracteres NFD."""
        sortie, courante = [], ""
        for bout, ponct in re.findall(r"([^.?!,:;\u2026]+)([.?!,:;\u2026]*)", texte):
            if not bout.strip():
                continue
            p = self._proposition(bout.strip())
            if not p:
                continue
            signe = self.PONCTUATION.get(ponct[:1], "") if ponct else ""
            courante += p + signe
            if ponct[:1] in (".", "?", "!", "\u2026"):
                sortie.append(list(unicodedata.normalize("NFD", courante)))
                courante = ""
            else:
                courante += " "
        if courante.strip():
            sortie.append(list(unicodedata.normalize("NFD", courante.rstrip())))
        return sortie


class Synthese:
    """Une voix Piper (un modele VITS en ONNX), chargee UNE fois : chaque phrase
    ne coute plus que son calcul -- quelques dizaines de millisecondes."""

    def __init__(self, modele, phonemiseur, fils=2, locuteur=0):
        import numpy as np
        import onnxruntime as rt
        self.np = np
        with open(modele + ".json", encoding="utf-8") as f:
            self.config = json.load(f)
        o = rt.SessionOptions()
        o.intra_op_num_threads = max(1, int(fils))
        o.inter_op_num_threads = 1
        self.session = rt.InferenceSession(modele, o, providers=["CPUExecutionProvider"])
        self.entrees = {i.name for i in self.session.get_inputs()}
        self.ids = self.config["phoneme_id_map"]
        self.frequence = int(self.config["audio"]["sample_rate"])
        inf = self.config.get("inference", {})
        self.bruit = float(inf.get("noise_scale", 0.667))
        self.bruit_w = float(inf.get("noise_w", 0.8))
        self.multi = int(self.config.get("num_speakers", 1)) > 1
        self.phonemiseur = phonemiseur
        self.locuteur = int(locuteur or 0)
        # la langue de ce qu'on lui donne a lire -- voir `texte_pour_piper`
        self.langue = "en" if str((self.config.get("espeak") or {}).get("voice", "")).startswith("en") else "fr"

    def identifiants(self, phonemes):
        """Comme piper : ^ _ p1 _ p2 _ ... pn _ $ ; un phoneme inconnu est saute."""
        pad, ids = self.ids["_"], list(self.ids["^"]) + list(self.ids["_"])
        for p in phonemes:
            if p in self.ids:
                ids += list(self.ids[p]) + list(pad)
        return ids + list(self.ids["$"])

    def phrase(self, phonemes, lenteur=1.0, bruit=None, bruit_w=None, locuteur=None):
        """Le son d'une phrase : int16 normalise comme piper (crete a 32767)."""
        np = self.np
        ids = self.identifiants(phonemes)
        entrees = {"input": np.array([ids], dtype=np.int64),
                   "input_lengths": np.array([len(ids)], dtype=np.int64),
                   "scales": np.array([self.bruit if bruit is None else bruit, float(lenteur),
                                       self.bruit_w if bruit_w is None else bruit_w], dtype=np.float32)}
        if self.multi and "sid" in self.entrees:
            entrees["sid"] = np.array([self.locuteur if locuteur is None else int(locuteur)],
                                      dtype=np.int64)
        son = self.session.run(None, entrees)[0].reshape(-1)
        crete = max(0.01, float(np.max(np.abs(son))))
        return np.clip(son * (32767.0 / crete), -32768, 32767).astype(np.int16)

    def phrases(self, texte, lenteur=1.0, **kw):
        """Genere le son phrase par phrase : on joue la premiere pendant que
        la suivante se calcule."""
        for ph in self.phonemiseur.phrases(texte):
            yield self.phrase(ph, lenteur, **kw)


_FIN_DE_PHRASE = re.compile(r"(?<=[.!?\u2026])\s+")


def decouper_phrases(texte):
    """Le texte en phrases -- pour reprendre la ou on lui a coupe la parole."""
    return [p.strip() for p in _FIN_DE_PHRASE.split(str(texte or "")) if p.strip()]


def texte_pour_piper(texte, langue="fr"):
    """Une seule ligne (piper lit ligne par ligne) et des nombres qui se disent.
    « 18h30 » est francais : en anglais, espeak lit « 18:30 » tout seul."""
    t = pour_la_voix(texte, lien="the link" if langue == "en" else "le lien")
    if langue != "en":
        t = re.sub(r"(\d{1,2})\s*h\s*(\d{2})\b", r"\1 heures \2", t)
    return t.replace("\n", " ").strip()


# ======================================================================
#  LA VOIX DE JARVIS -- KOKORO, EN ANGLAIS BRITANNIQUE
#
#  « The voice is very bad », « it's robotic as well » : Piper lit juste, mais
#  il lit. Kokoro-82M (hexgrad, Apache-2.0 ; l'export ONNX de thewh1teagle/
#  kokoro-onnx, MIT) est d'une autre generation -- une voix qui respire, qui
#  place l'accent de phrase -- et il a des voix d'hommes britanniques.
#
#  « Comme Jarvis », toujours PAS la voix de l'acteur : on prend deux voix du
#  modele, Fable et un peu de Lewis, melangees (la moyenne de leurs vecteurs de
#  style) pour un timbre pose, un peu grave -- 116 Hz de fondamentale mesures,
#  contre 122 pour Fable seul. Une voix de majordome britannique, celle de
#  personne.
#
#  LE FLOAT32 ET PAS L'INT8. Mesure sur un Xeon a 2,1 GHz : l'int8 met 1,2 a
#  1,4 fois la duree de la phrase a la calculer (plus lent que la parole), le
#  float32 0,29 fois avec quatre fils. La quantification dynamique ne paie que
#  sur un processeur qui a VNNI, et on ne sait pas sur quoi Jarvis tourne. 310
#  Mo telecharges une fois, contre des phrases qui arrivent a l'heure.
#
#  Les phonemes viennent du meme espeak-ng que Piper (livre dans son archive),
#  en anglais britannique -- ce que kokoro-onnx fait aussi.
# ======================================================================

KOKORO_SOURCE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_MODELE = "kokoro-v1.0.onnx"
KOKORO_VOIX = "voices-v1.0.bin"
# La taille exacte de chaque fichier : un telechargement coupe ne passe jamais
# pour complet, et un fichier remplace en amont se voit.
KOKORO_TAILLES = {KOKORO_MODELE: 325532387, KOKORO_VOIX: 28214398}
KOKORO_FREQ = 24000
KOKORO_ESPEAK = "en"          # espeak-ng : lang/gmw/en, l'anglais de Grande-Bretagne
KOKORO_MAX = 510              # jetons par passe : la longueur de la table des styles

VOIX_KOKORO = {
    "jarvis":    {"nom": "Jarvis -- britannique, homme, pose (Fable et un peu de Lewis)",
                  "melange": {"bm_fable": 0.7, "bm_lewis": 0.3}},
    "bm_fable":  {"nom": "Fable -- britannique, homme, clair", "melange": {"bm_fable": 1.0}},
    "bm_george": {"nom": "George -- britannique, homme, plus aigu", "melange": {"bm_george": 1.0}},
    "bm_daniel": {"nom": "Daniel -- britannique, homme", "melange": {"bm_daniel": 1.0}},
    "bm_lewis":  {"nom": "Lewis -- britannique, homme, tres grave", "melange": {"bm_lewis": 1.0}},
}
KOKORO_DEFAUT = "jarvis"

# SA VOIX FRANCAISE, PAR KOKORO AUSSI. « Can you have a french voice for
# jarvis ? » -- Piper lisait juste, mais il lisait. Kokoro-82M parle francais
# (espeak-ng « fr » pour les phonemes) ; sa seule voix francaise, Siwis, est
# une voix de femme. Melangee aux voix d'hommes britanniques du Jarvis anglais,
# elle garde l'accent et prend leur timbre. MESURE (six phrases de Jarvis,
# relues par Whisper small ; hauteur mediane) : Siwis seule 218 Hz, 14 % de
# mots rates ; Lewis seul 103 Hz mais 42 % -- un Anglais qui lit du francais ;
# Siwis 0,3 + Lewis 0,7 : 141 Hz, 17 %. Un homme, qu'on comprend.
KOKORO_ESPEAK_FR = "fr"       # espeak-ng : lang/roa/fr, le francais de France
VOIX_KOKORO_FR = {
    "fr_jarvis": {"nom": "Jarvis -- homme, grave, pose (Siwis et Lewis)",
                  "melange": {"ff_siwis": 0.3, "bm_lewis": 0.7}},
    "fr_jarvis_clair": {"nom": "Jarvis clair -- homme, plus leger (Siwis, Fable et Lewis)",
                        "melange": {"ff_siwis": 0.3, "bm_fable": 0.35, "bm_lewis": 0.35}},
    "fr_daniel": {"nom": "Daniel -- homme, net (Siwis et Daniel)",
                  "melange": {"ff_siwis": 0.2, "bm_daniel": 0.8}},
    "fr_siwis": {"nom": "Siwis -- femme, la plus naturelle", "melange": {"ff_siwis": 1.0}},
}
KOKORO_FR_DEFAUT = "fr_jarvis"

# LE VOCABULAIRE DU MODELE : un phoneme, un jeton. Recopie du config.json de
# Kokoro-82M ; un test le compare au fichier quand il est la. Le tilde
# combinant (U+0303, les nasales) est un symbole a lui seul.
_KOKORO_SYMBOLES = (';:,.!?—…"()“” ̃ʣʥʦʨᵝꭧAIOQSTWYᵊabcdefhijk'
                    'lmnopqrstuvwxyzɑɐɒæβɔɕçɖðʤəɚɛɜɟɡɥɨɪʝɯɰŋɳɲɴøɸθœɹɾɻʁɽʂʃʈʧʊʋʌɣɤχʎʒʔˈˌːʰʲ↓→↗↘ᵻ')
_KOKORO_IDS = (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 31,
               33, 35, 36, 39, 41, 42, 43, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59,
               60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 75, 76, 77, 78, 80, 81, 82, 83, 85,
               86, 87, 90, 92, 99, 101, 102, 103, 110, 111, 112, 113, 114, 115, 116, 118, 119, 120, 123,
               125, 126, 128, 129, 130, 131, 132, 133, 135, 136, 138, 139, 140, 142, 143, 147, 148, 156,
               157, 158, 162, 164, 169, 171, 172, 173, 177)
KOKORO_VOCAB = dict(zip(_KOKORO_SYMBOLES, _KOKORO_IDS))


def style_kokoro(pack, voix):
    """La table des styles d'une voix du catalogue : (510, 1, 256), un vecteur
    par longueur de phrase. Un melange est la moyenne ponderee des tables."""
    entree = VOIX_KOKORO.get(voix) or VOIX_KOKORO_FR.get(voix) or VOIX_KOKORO[KOKORO_DEFAUT]
    total = sum(entree["melange"].values())
    style = None
    for nom, poids in entree["melange"].items():
        s = pack[nom].astype("float32") * (poids / total)
        style = s if style is None else style + s
    return style


def phonemes_kokoro(liste):
    """Les phonemes d'une phrase (la liste de caracteres du Phonemiseur), tels
    que Kokoro les lit : sans les marques de changement de langue d'espeak
    (« (fr) », « (en) » -- les parentheses sont dans son vocabulaire, et il
    les aurait lues), les espaces ramasses."""
    p = unicodedata.normalize("NFC", "".join(liste))
    p = re.sub(r"\([a-z]{2,3}(?:-[a-z0-9]+)*\)", "", p)
    return re.sub(r"\s+", " ", p).strip()


def morceaux_kokoro(phonemes, plafond=KOKORO_MAX):
    """Une phrase trop longue pour une passe, coupee a une virgule, sinon a un
    espace, sinon net."""
    reste, sortie = phonemes, []
    while len(reste) > plafond:
        coupe = max(reste.rfind(", ", 0, plafond), reste.rfind("; ", 0, plafond))
        if coupe < plafond // 3:
            coupe = reste.rfind(" ", 0, plafond)
        if coupe < plafond // 3:
            coupe = plafond - 1
        sortie.append(reste[:coupe + 1].strip())
        reste = reste[coupe + 1:].strip()
    if reste:
        sortie.append(reste)
    return sortie


class SyntheseKokoro:
    """Kokoro-82M, charge UNE fois. Meme interface que `Synthese` : la Bouche
    ne sait pas laquelle elle fait parler."""

    # UN MODELE POUR DEUX LANGUES : l'anglais et le francais de Jarvis sont le
    # meme reseau de 310 Mo avec deux styles -- charge une fois par processus,
    # pas une fois par langue.
    _SESSIONS = {}
    _VERROU = threading.Lock()

    def __init__(self, modele, fichier_voix, phonemiseur, voix=KOKORO_DEFAUT, fils=4, langue="en"):
        import numpy as np
        import onnxruntime as rt
        self.np = np
        with SyntheseKokoro._VERROU:
            cle = os.path.abspath(modele)
            self.session = SyntheseKokoro._SESSIONS.get(cle)
            if self.session is None:
                o = rt.SessionOptions()
                o.intra_op_num_threads = max(1, int(fils))
                o.inter_op_num_threads = 1
                self.session = rt.InferenceSession(modele, o, providers=["CPUExecutionProvider"])
                SyntheseKokoro._SESSIONS[cle] = self.session
        noms = {i.name for i in self.session.get_inputs()}
        # « tokens » dans l'export v1.0, « input_ids » dans les suivants
        self.entree = "input_ids" if "input_ids" in noms else "tokens"
        with np.load(fichier_voix) as pack:
            self.styles = style_kokoro(pack, voix)
        self.phonemiseur = phonemiseur
        self.frequence = KOKORO_FREQ
        self.langue = "fr" if langue == "fr" else "en"

    def jetons(self, phonemes):
        return [KOKORO_VOCAB[c] for c in phonemes if c in KOKORO_VOCAB]

    def phrase(self, phonemes, lenteur=1.0):
        """Le son d'une phrase : int16, crete normalisee comme Piper. `lenteur`
        est celle de Piper (1,1 = plus lent) ; Kokoro veut une vitesse."""
        np = self.np
        ids = self.jetons(phonemes)[:KOKORO_MAX]
        if not ids:
            return np.zeros(0, dtype=np.int16)
        # Un vecteur de style par longueur : n phonemes, la ligne n - 1.
        style = self.styles[min(len(ids), len(self.styles)) - 1].reshape(1, -1).astype(np.float32)
        vitesse = 1.0 / max(0.5, min(2.0, float(lenteur or 1.0)))
        son = self.session.run(None, {self.entree: np.array([[0] + ids + [0]], dtype=np.int64),
                                      "style": style,
                                      "speed": np.array([vitesse], dtype=np.float32)})[0].reshape(-1)
        crete = max(0.01, float(np.max(np.abs(son))))
        return np.clip(son * (32767.0 / crete), -32768, 32767).astype(np.int16)

    def phrases(self, texte, lenteur=1.0, **kw):
        for ph in self.phonemiseur.phrases(texte):
            for bout in morceaux_kokoro(phonemes_kokoro(ph)):
                son = self.phrase(bout, lenteur)
                if len(son):
                    yield son


# ======================================================================
#  LA DOUBLE TRANSMISSION -- LUI COUPER LA PAROLE
#
#  « Il faut que ce soit une discussion a double transmission, comme les
#  modeles de ChatGPT, pour pouvoir couper la parole. » Pendant que Jarvis
#  parle, l'oreille ecoute toujours ; si la personne parle PAR-DESSUS, il se
#  tait et l'ecoute.
#
#  LE PIEGE, C'EST SA PROPRE VOIX : le micro entend les haut-parleurs. On
#  garde donc ce que les haut-parleurs jouent -- la REFERENCE, le loopback de
#  Windows, le son qui sort, musique comprise -- et on apprend, bande par
#  bande, comment il revient dans le micro : un petit filtre sur les
#  puissances (NLMS, 30 prises de 20 ms = 600 ms : le retard et l'echo de la
#  piece). Ce que l'echo n'explique pas, c'est peut-etre la personne.
#
#  LA MARGE EST MESUREE, PAS DEVINEE. Pendant que Jarvis parle seul, on releve
#  de combien l'echo depasse ce que le filtre en predit, et la marge de chaque
#  bande est le 99e centile de cet ecart. Une marge fixe coupait pour rien :
#  l'echo d'une piece fluctue au hasard autour de ce qu'on en attend.
#
#  PEUT-ETRE, parce qu'un clavier non plus, l'echo ne l'explique pas. Ce qui
#  depasse ne compte que si c'est une VOIX : aussi forte que lui a 10 dB pres
#  (on hausse le ton pour couper quelqu'un), et qui VIBRE -- une hauteur tenue
#  sur 80 ms, mesuree sur le micro dont on a retire Jarvis ; le « toc » d'une
#  touche s'eteint en quelques millisecondes. Et s'il coupe pour rien quand
#  meme, personne ne parle ensuite : il reprend sa phrase.
#
#  MESURE, en simulation : 240 pieces tirees au sort (retard 10 a 150 ms,
#  reverberation 0,15 a 0,8 s, niveaux, bruit ; les deux horloges qui trainent
#  et arrivent par rafales ; Jarvis par Kokoro, la personne par huit voix
#  francaises et anglaises), quatre reponses chacune :
#    - sa propre voix : aucune coupure pour rien en 960 reponses ; avec le
#      volume monte de 10 dB entre deux reponses, une ;
#    - quelqu'un qui parle par-dessus, de 3 dB sous l'echo a 12 dB au-dessus :
#      entendu 221 fois sur 240, en une demi-seconde (mediane) ; des la
#      premiere seconde de sa reponse, 212 ; de 0 a 10 dB SOUS l'echo (un
#      portable, les haut-parleurs contre le micro), deux fois sur trois ;
#    - taper au clavier pendant qu'il parle : 1,4 % des reponses coupees pour
#      rien -- 7 % avec un clavier dont toutes les touches sonnent a la meme
#      hauteur, tape vite. Il reprend alors sa phrase.
#  Et « Jarvis ! » par-dessus le coupe toujours, par le mot d'eveil.
#
#  CE QUI NE CHANGE PAS : la reference ne sert qu'a ca, en memoire et en
#  puissances par bande ; elle n'est ni transcrite, ni gardee, ni envoyee, et
#  on ne l'ouvre que pendant que Jarvis parle.
# ======================================================================

COUPURE_SF = 320                   # une sous-trame : 20 ms a 16 kHz
COUPURE_PAS = COUPURE_SF / float(FREQ)
_COUPURE_NFFT = 512
_COUPURE_BORNES = (150, 250, 350, 450, 570, 700, 840, 1000, 1170, 1370, 1600, 1850, 2150, 2500, 2900,
                   3400, 4000, 4800, 5800, 7000)
_COUPURE_BANDES = []


def _bandes_coupure():
    if not _COUPURE_BANDES:
        import numpy as np
        f = np.fft.rfftfreq(_COUPURE_NFFT, 1.0 / FREQ)
        _COUPURE_BANDES.extend((int(np.searchsorted(f, _COUPURE_BORNES[i])),
                                int(np.searchsorted(f, _COUPURE_BORNES[i + 1])))
                               for i in range(len(_COUPURE_BORNES) - 1))
    return _COUPURE_BANDES


class _HorlogeDeFlux:
    """DATER UN FLUX PAR SON RANG ET PAS PAR SON ARRIVEE. Un bloc arrive quand
    le systeme et le fil le veulent -- a 10 ou 20 ms pres --, mais il a ete
    capte a la cadence de l'horloge du son. Un flux continu est donc date par
    le temps qu'il a deja fourni, depuis une origine qui est la mediane des
    arrivees recentes : la gigue disparait. Mesure : avec la date d'arrivee,
    dans une piece seche, l'echo suit la reference a la milliseconde et dix
    millisecondes d'erreur suffisaient a rendre la coupure sourde. Un trou (le
    loopback se tait quand rien ne joue) remet l'origine a zero."""

    def __init__(self):
        self.fourni = 0.0
        self.origines = deque(maxlen=48)
        self.derniere = None

    def dater(self, t_arrivee, duree):
        if self.derniere is not None and (t_arrivee - self.derniere > duree + 0.25
                                          or t_arrivee < self.derniere - 0.25):
            self.fourni = 0.0
            self.origines.clear()
        self.derniere = t_arrivee
        self.fourni += duree
        self.origines.append(t_arrivee - self.fourni)
        o = sorted(self.origines)
        return o[len(o) // 2] + self.fourni


class Coupure:
    """Decide, 20 ms par 20 ms, si la personne parle par-dessus Jarvis.

    `reference(x, t_fin)` : un bloc de ce que jouent les haut-parleurs ;
    `micro(x, t_fin)` : une trame du micro -- rend True quand il faut couper.
    Les deux en float32 a 16 kHz, dates a leur FIN par la meme horloge. Ce
    qu'il a appris de la piece reste d'une reponse a l'autre : la premiere
    reponse lui sert a l'apprendre."""

    def __init__(self, seuil=0.35, part=0.3, n_on=6, fenetre=9, niveau_min=1e-5, prises=30, mu=0.25,
                 appris_min=50, centile=99.0, marge_min=2.0, marge_max=60.0, rapide=3, fort=0.65,
                 regul=0.03, rodage=10, volume=True, vol_rodage=15, vol_attente=1.5, vol_centile=70.0,
                 niv_rel=10.0, vois_suite=4, vois_seuil=0.5):
        import numpy as np
        self.np = np
        self.bandes = _bandes_coupure()
        self.nb = len(self.bandes)
        self.fen = np.hanning(COUPURE_SF).astype(np.float32)
        self.seuil, self.part, self.n_on, self.niveau_min = seuil, part, n_on, niveau_min
        self.L, self.mu, self.appris_min = prises, mu, appris_min
        self.centile, self.marge_min, self.marge_max = centile, marge_min, marge_max
        self.rapide, self.fort = rapide, fort
        self.w = np.zeros((self.nb, prises))
        # LE FILTRE SE REGLE SUR LES CRETES DE LA REFERENCE, pas sur sa moyenne :
        # la toute premiere trame apprise etait un debut de mot presque muet
        # (1e-13) face au bruit du micro, et diviser par presque rien donnait a
        # la prise zero un poids de 3000 -- deux reponses plus tard il en
        # restait 10 a 180 au lieu de 0,1. L'echo predit etait cent fois trop
        # fort pendant qu'il parle : sourd sur ses syllabes, il n'entendait la
        # personne que dans ses silences. Et les dix premieres trames ne font
        # que prendre la mesure de la reference (`rodage`).
        self.regul, self.rodage = regul, rodage
        self.norme_crete = np.zeros(self.nb)
        self.vus = 0
        self.marges = np.full(self.nb, 3.0)
        self.erreurs = deque(maxlen=400)       # 8 s de « echo / prediction », Jarvis seul
        self.n_erreurs = 0
        self.calibree = False
        # LE VOLUME QU'ON MONTE ENTRE DEUX REPONSES. Le loopback est pris avant
        # le volume : seul l'echo grossit, et le filtre -- qui apprend avec
        # 1,5 s de retard -- le predit trop faible. Mesure : 6 dB de plus, une
        # reponse sur six coupee pour rien ; 10 dB, presque toutes. Or au debut
        # d'une reponse on l'ecoute : passe le premier mot (`vol_rodage` trames,
        # ou le filtre annonce de l'echo qui n'est pas encore arrive), une
        # demi-seconde de « micro / echo predit », bande par bande, dit de
        # combien il a grossi (le 70e centile : ni les attaques de mots, qui
        # tirent vers le bas, ni quelqu'un qui parlerait deja). La prediction
        # est montee d'autant pour toute la reponse -- jamais baissee. Pas de
        # decision avant cette mesure, sauf sans echo du tout (casque) : alors
        # au bout de `vol_attente`.
        self.volume, self.vol_rodage, self.vol_attente, self.vol_centile = volume, vol_rodage, vol_attente, vol_centile
        self.gains = []
        self.g_vol = 1.0
        self.vol_vus = self.vol_trames = 0
        self.vol_fait = False
        # ET SI ELLE COUPE POUR RIEN QUAND MEME, elle ne doit pas recommencer a
        # la reponse suivante : une coupure met de cote ce qu'elle allait
        # apprendre (la voix de la personne y est, peut-etre) ; si personne n'a
        # parle ensuite (`fausse_coupure`), c'etait de l'echo, et il s'apprend.
        self.de_cote = []
        # UNE VOIX, PAS UN CLAVIER -- voir l'en-tete. `niv_rel` : de combien de
        # dB la voix peut etre plus basse que l'echo habituel ; `vois_suite` :
        # combien de trames de 20 ms elle doit tenir sa hauteur.
        self.niv_rel, self.vois_suite, self.vois_seuil = niv_rel, vois_suite, vois_seuil
        self.echo_typ = deque(maxlen=100)      # 2 s de « combien d'echo quand il parle »
        self.suite_voisee, self.lag_prec, self.voisee_max = 0, 0, 0
        f = np.fft.rfftfreq(_COUPURE_NFFT, 1.0 / FREQ)
        self.bande_du_bin = np.clip(np.searchsorted([b for _, b in self.bandes], np.arange(len(f)), side="right"),
                                    0, self.nb - 1)
        self.fen_rac = np.sqrt(np.hanning(COUPURE_SF + 1)[:COUPURE_SF])
        self.ola = np.zeros(COUPURE_SF)
        self.entree = np.zeros(COUPURE_SF // 2)
        self.nette = np.zeros(2 * COUPURE_SF)  # les 40 dernieres ms du micro, sans Jarvis
        self.grille = {}                       # la reference, rangee par tranche de 20 ms
        self.dernier = None
        self.passe_M = deque(maxlen=100)       # 2 s de micro : le bruit de fond est leur minimum
        self.passe_ms = deque(maxlen=100)
        self.bruit = np.full(self.nb, 1e-12)
        self.bruit_ms = 1e-12
        self.hist = deque(maxlen=fenetre)
        self.suite_forte = 0
        self.arme = False
        self.t_arme = 0.0
        self.appris = 0
        self.horloge_ref = _HorlogeDeFlux()
        self.horloge_micro = _HorlogeDeFlux()
        # APPRENDRE AVEC DU RETARD. Les trames d'avant la decision contiennent
        # deja la voix de la personne : apprises tout de suite, elles entraient
        # dans l'echo et les marges, et chaque interruption rendait la suivante
        # plus difficile (mesure : trois coupures, et des marges au plafond).
        # Elles attendent donc 1,5 s ; une coupure les met de cote, une fin
        # normale les garde.
        self.retard = 1.5
        self.en_attente = deque()

    def _puissances(self, x):
        np = self.np
        X = np.fft.rfft(x * self.fen, _COUPURE_NFFT)
        p = (X.real ** 2 + X.imag ** 2) / float(COUPURE_SF * COUPURE_SF)
        return np.array([p[a:b].sum() for a, b in self.bandes])

    def _sans_echo(self, s, M, E):
        """Ce que le micro entend MOINS Jarvis : chaque bande attenuee de ce que
        l'echo predit y prend (jusqu'a sa marge), en fenetres de 20 ms qui se
        chevauchent de moitie pour que le son reste un son (10 ms de retard).
        Sans ca, la voix de Jarvis dans le micro « tenait sa hauteur » a la
        place de la personne."""
        np = self.np
        g = np.clip(1.0 - self.marges * E / np.maximum(M, 1e-20), 0.0, 1.0)[self.bande_du_bin]
        x = np.concatenate([self.entree, s.astype(np.float64)])
        pas = COUPURE_SF // 2
        sortie = np.zeros(COUPURE_SF)
        for k in range(2):
            trame = x[k * pas:k * pas + COUPURE_SF] * self.fen_rac
            self.ola += np.fft.irfft(np.fft.rfft(trame, _COUPURE_NFFT) * g, _COUPURE_NFFT)[:COUPURE_SF] * self.fen_rac
            sortie[k * pas:(k + 1) * pas] = self.ola[:pas]
            self.ola = np.concatenate([self.ola[pas:], np.zeros(pas)])
        self.entree = x[-pas:]
        return sortie

    def _voisement(self, x):
        """La voix qui vibre : la meilleure autocorrelation entre 80 et 400 Hz
        sur 40 ms, et a quel retard (la hauteur). Un claquement n'en a pas."""
        np = self.np
        x = x - float(np.mean(x))
        n = len(x)
        r = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * n)) ** 2)[:n]
        if r[0] <= 0:
            return 0.0, 0
        tau = np.arange(40, 201)
        v = r[tau] / r[0] * n / (n - tau)
        i = int(np.argmax(v))
        return float(v[i]), int(tau[i])

    def _suivre_la_hauteur(self, parle):
        """Combien de trames de suite ce qui depasse vibre, a la meme hauteur
        (a 20 % pres, ou a l'octave : l'autocorrelation trouve parfois le
        double de la periode) : une voix tient la sienne ; le « toc » d'un
        clavier s'eteint en quelques millisecondes."""
        v, lag = self._voisement(self.nette) if parle else (0.0, 0)
        if parle and v >= self.vois_seuil:
            tenue = self.suite_voisee > 0 and any(abs(lag * f - self.lag_prec) <= 0.2 * self.lag_prec
                                                  for f in (1.0, 2.0, 0.5))
            self.suite_voisee = self.suite_voisee + 1 if tenue else 1
        else:
            self.suite_voisee = 0
        self.lag_prec = lag
        self.voisee_max = max(self.voisee_max, self.suite_voisee)

    def reference(self, x, t_fin):
        n = len(x) // COUPURE_SF
        t_fin = self.horloge_ref.dater(t_fin, n * COUPURE_PAS)
        for i in range(n):
            t = t_fin - (n - i - 1) * COUPURE_PAS
            if self.dernier is not None and t < self.dernier - 1.0:
                self.grille.clear()            # l'horloge a recule : on repart de zero
            self.dernier = t
            self.grille[int(round(t / COUPURE_PAS))] = self._puissances(x[i * COUPURE_SF:(i + 1) * COUPURE_SF])
        plus_vieux = int(round(t_fin / COUPURE_PAS)) - self.L - 50
        for k in [k for k in self.grille if k < plus_vieux]:
            del self.grille[k]

    def armer(self, t):
        self.arme, self.t_arme = True, t
        self.hist.clear()
        self.suite_forte = 0
        self.suite_voisee = self.voisee_max = 0
        self.gains = []
        self.g_vol = 1.0
        self.vol_vus = self.vol_trames = 0
        self.vol_fait = False
        self.de_cote = []

    def desarmer(self, garder=True):
        """Il a fini de parler (garder) -- ou on vient de lui couper la parole,
        et ce qui attendait contient peut-etre la voix de la personne : mis de
        cote, jusqu'a savoir (`fausse_coupure`)."""
        self.arme = False
        self.hist.clear()
        self.suite_forte = 0
        if garder:
            self._apprendre_jusqua(float("inf"))
        else:
            self.de_cote = list(self.en_attente)
            self.en_attente.clear()

    def fausse_coupure(self):
        """Personne n'a parle apres la coupure : ce qui attendait etait de
        l'echo -- au nouveau volume, peut-etre. Il s'apprend."""
        for _, M, E, X, forme in self.de_cote:
            self._apprendre(M, E, X, forme)
        self.de_cote = []

    def pret(self):
        return self.appris >= self.appris_min and self.calibree

    def _apprendre(self, M, E, X, forme):
        """`E` est l'echo que le filtre predisait AU MOMENT de la trame -- celui
        sur lequel on a decide. Les marges se mesurent donc sur lui, mais
        seulement s'il sortait d'un filtre deja forme (`forme`) : avec le
        retard, les premieres predictions venaient d'un filtre vide ou en
        pleine transitoire, et les marges tombaient au plancher."""
        np = self.np
        if forme:
            ok = (E > 2.0 * self.bruit) & (M > 2.0 * self.bruit)
            self.erreurs.append(np.where(ok, M / np.maximum(E, 1e-20), np.nan))
            self.n_erreurs += 1
            if self.n_erreurs >= 40 and self.n_erreurs % 10 == 0:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    q = np.nanpercentile(np.array(self.erreurs), self.centile, axis=0)
                self.marges = np.clip(np.where(np.isnan(q), self.marge_max, q), self.marge_min, self.marge_max)
                self.calibree = True
        norme = np.einsum("bk,bk->b", X, X)
        self.norme_crete = np.maximum(norme, 0.999 * self.norme_crete)
        self.vus += 1
        if self.vus <= self.rodage:
            return
        err = M - np.einsum("bk,bk->b", self.w, X)
        self.w += self.mu * (err / (norme + self.regul * self.norme_crete + 1e-30))[:, None] * X
        np.maximum(self.w, 0.0, out=self.w)
        self.appris += 1

    def _apprendre_jusqua(self, t):
        while self.en_attente and self.en_attente[0][0] <= t:
            _, M, E, X, forme = self.en_attente.popleft()
            self._apprendre(M, E, X, forme)

    def _mesurer_le_volume(self, M, E, X):
        """Voir `volume` : rend la prediction corrigee, et si on peut decider."""
        np = self.np
        if X.sum() > 1e-14:
            self.vol_vus += 1
        if self.vol_vus > self.vol_rodage and not self.vol_fait:
            ok = (E > 4.0 * self.bruit) & (M > 4.0 * self.bruit)
            self.gains.extend(np.log(M[ok] / E[ok]).tolist())
            self.vol_trames += 1
            if len(self.gains) >= 150 or self.vol_trames >= 25:
                self.vol_fait = True
                if len(self.gains) >= 30:
                    self.g_vol = max(1.0, float(np.exp(np.percentile(self.gains, self.vol_centile))))
        return E * self.g_vol, self.vol_fait

    def micro(self, x, t_fin):
        np = self.np
        n = len(x) // COUPURE_SF
        t_fin = self.horloge_micro.dater(t_fin, n * COUPURE_PAS)
        coupe = False
        for i in range(n):
            t = t_fin - (n - i - 1) * COUPURE_PAS
            s = x[i * COUPURE_SF:(i + 1) * COUPURE_SF]
            M = self._puissances(s)
            ms = float(np.mean(s.astype(np.float64) ** 2))
            self.passe_M.append(M)
            self.passe_ms.append(ms)
            if len(self.passe_M) >= 10:
                self.bruit = np.min(np.array(self.passe_M), axis=0) * 1.5
                self.bruit_ms = min(self.passe_ms) * 1.5
            k = int(round(t / COUPURE_PAS))
            X = np.zeros((self.nb, self.L))
            for j in range(self.L):
                P = self.grille.get(k - j)
                if P is not None:
                    X[:, j] = P
            E = np.einsum("bk,bk->b", self.w, X)      # l'echo que la piece devrait rendre
            sur = True
            if self.volume:
                E, mesure = self._mesurer_le_volume(M, E, X)
                sur = mesure or t - self.t_arme > self.vol_attente
            if E.sum() > 4.0 * self.bruit.sum():
                self.echo_typ.append(float(E.sum()))
            if self.vois_suite:
                self.nette = np.concatenate([self.nette[COUPURE_SF:], self._sans_echo(s, M, E)])
            parle = False
            if self.arme and self.pret() and sur:
                limite = self.marges * E + 2.0 * self.bruit
                exces = np.maximum(0.0, M - limite)
                score = exces.sum() / max(M.sum(), 1e-15)
                part = (M > limite)[:15].mean()       # 150 Hz - 4 kHz : la voix
                parle = (score > self.seuil and part >= self.part
                         and score * ms > max(self.niveau_min, 6.0 * self.bruit_ms))
                # aussi forte que lui, a `niv_rel` dB pres
                if parle and self.niv_rel is not None and self.echo_typ:
                    parle = exces.sum() >= float(np.median(self.echo_typ)) * 10 ** (-self.niv_rel / 10.0)
                if self.vois_suite:
                    self._suivre_la_hauteur(parle)
                self.hist.append(parle)
                # la voie rapide : nettement au-dessus de l'echo, trois fois de suite
                self.suite_forte = self.suite_forte + 1 if (parle and score > self.fort and part >= 0.5) else 0
                une_voix = not self.vois_suite or self.voisee_max >= self.vois_suite
                if ((sum(self.hist) >= self.n_on or (self.rapide and self.suite_forte >= self.rapide))
                        and t - self.t_arme > 0.2 and une_voix):
                    coupe = True
                if not any(self.hist):
                    self.voisee_max = 0
            # APPRENDRE, quand Jarvis parle et que la personne se tait -- avec
            # du retard, voir `retard`
            if not parle and X.sum() > 1e-14:
                self.en_attente.append((t, M, E, X, self.appris >= self.appris_min))
            self._apprendre_jusqua(t - self.retard)
            if coupe:
                break
        if coupe:
            self.desarmer(garder=False)
        return coupe


def haut_parleurs_windows():
    """Ce que jouent les haut-parleurs par defaut (le loopback de WASAPI),
    en 16 kHz mono, par blocs de 20 ms."""
    import soundcard as sc
    hp = sc.default_speaker()
    return sc.get_microphone(id=str(hp.name), include_loopback=True).recorder(
        samplerate=FREQ, channels=1, blocksize=COUPURE_SF)


class Loopback:
    """La reference, dans son fil, OUVERTE SEULEMENT PENDANT QUE JARVIS PARLE.
    `ouvrir()` rend un gestionnaire de contexte qui a `record(numframes)`."""

    def __init__(self, ouvrir=None, horloge=None):
        self.ouvrir = ouvrir or haut_parleurs_windows
        self.horloge = horloge or time.perf_counter
        self.blocs = deque(maxlen=400)
        self.actif = threading.Event()
        self.fil = None
        self.erreur = None

    def demarrer(self):
        self.actif.set()
        if self.fil is None or not self.fil.is_alive():
            self.fil = threading.Thread(target=self._tourner, daemon=True)
            self.fil.start()

    def arreter(self):
        self.actif.clear()

    def _tourner(self):
        import numpy as np
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0)     # COM, dans ce fil aussi
            except Exception:
                pass
        try:
            with self.ouvrir() as rec:
                while self.actif.is_set():
                    b = rec.record(numframes=COUPURE_SF)
                    t = self.horloge()
                    mono = b[:, 0] if getattr(b, "ndim", 1) > 1 else b
                    self.blocs.append((t, np.asarray(mono, dtype=np.float32)))
        except Exception as e:
            self.erreur = "%s : %s" % (type(e).__name__, str(e)[:120])


# ======================================================================
#  L'OREILLE -- LE PROCESSUS QUI TIENT LE MICRO
#
#  A part, comme le moteur de la dictee : s'il tombe (micro debranche,
#  pilote qui plante), Machi Tool reste debout et le relance.
# ======================================================================

def envoyer(s, objet, verrou=None):
    octets = json.dumps(objet).encode("utf-8") if objet is not None else b""
    paquet = struct.pack(">I", len(octets)) + octets
    if verrou is not None:
        with verrou:
            s.sendall(paquet)
    else:
        s.sendall(paquet)


def recevoir(s, plafond=8 * 1024 * 1024):
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
    return json.loads(exactement(n).decode("utf-8")) if n else None


def choisir_micro(micros, voulu, defaut):
    """LE MICRO CHOISI DANS LES REGLAGES, par son identifiant Windows (stable,
    et deux micros peuvent porter le meme nom), a defaut par son nom -- ou
    celui de Windows. Rend (micro, trouve) : `trouve` est faux quand le micro
    choisi n'est plus branche, pour que Machi Tool le dise au lieu d'ecouter
    ailleurs en silence."""
    voulu = str(voulu or "")
    if not voulu:
        return defaut(), True
    for cle in ("id", "name"):
        for m in micros():
            if str(getattr(m, cle, "")) == voulu:
                return m, True
    return defaut(), False


def micro_windows(nom="", annoncer=None):
    """Les trames du micro, 1280 echantillons int16 a 16 kHz. WASAPI convertit
    lui-meme la frequence (soundcard ouvre le flux avec AUTOCONVERTPCM)."""
    import numpy as np
    import soundcard as sc
    micro, trouve = choisir_micro(sc.all_microphones, nom, sc.default_microphone)
    if annoncer:
        annoncer(str(getattr(micro, "name", "")), trouve)
    with micro.recorder(samplerate=FREQ, channels=1, blocksize=TRAME) as r:
        while True:
            b = r.record(numframes=TRAME)
            mono = b[:, 0] if getattr(b, "ndim", 1) > 1 else b
            yield (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)


class Oreille:
    """La machine a etats de l'oreille, sans socket ni micro : testable.

    `sortie(evenement)` recoit ce qui doit partir vers Machi Tool ;
    `jouer(genre)` joue un son."""

    def __init__(self, empreintes, sortie, jouer_son=None, loopback=None, horloge=None):
        self.e = empreintes
        self.sortie = sortie
        self.jouer = jouer_son or (lambda g: None)
        self.reglages = {"gabarits": [], "sensibilite": 0.5, "hey": True, "son": True, "couper": True}
        self.det = Detecteur(empreintes)
        self.etat = "veille"
        self.phrase = None
        self.appris = None
        self.niveau_vu = 0.0
        # LA DOUBLE TRANSMISSION : pendant que Jarvis parle, on ecoute s'il se
        # fait couper -- voir `Coupure`. Sans reference, il n'y a que le mot d'eveil.
        self.loopback = loopback
        self.horloge = horloge or time.perf_counter
        self.coupure = None
        self.parole = False
        self.apres_coupure = False

    def _arreter_parole(self):
        self.parole = False
        if self.coupure is not None:
            self.coupure.desarmer()
        if self.loopback is not None:
            self.loopback.arreter()

    def _coupe(self, x):
        """Jarvis parle : la personne vient-elle de lui couper la parole ?"""
        import numpy as np
        c = self.coupure
        if c is None or self.loopback is None:
            return False
        while True:
            try:
                t_b, b = self.loopback.blocs.popleft()
            except IndexError:
                break
            c.reference(b, t_b)
        return c.micro(np.asarray(x, dtype=np.float32) / 32768.0, self.horloge())

    def etat_coupure(self):
        if not self.reglages.get("couper", True):
            return "coupee"
        if self.loopback is None:
            return "sans reference"
        if self.loopback.erreur:
            return "reference impossible : " + self.loopback.erreur
        if self.coupure is None or not self.coupure.pret():
            return "apprend la piece"
        return "prete"

    def configurer(self, r):
        self.reglages.update({k: v for k, v in r.items() if k != "cmd"})
        self.det.gabarits = [normer(g) for g in self.reglages.get("gabarits") or []
                             if len(g) >= GABARIT_MIN]
        self.det.seuil = seuil_gabarit(self.reglages.get("sensibilite", 0.5))
        self.det.seuil_hey = 0.5 if self.reglages.get("hey", True) else 9.0

    def commande(self, c):
        cmd = (c or {}).get("cmd")
        if cmd == "config":
            self.configurer(c)
        elif cmd == "ecouter":
            # La suite d'une conversation : on ecoute sans mot d'eveil.
            self.phrase = Phrase(self.det.parle, attente=float(c.get("attente", 5.0)),
                                 ignorer=float(c.get("ignorer", 0.35)))
            self.etat = "phrase"
            self.apres_coupure = False
        elif cmd == "fausse_coupure":
            # La phrase d'apres la coupure etait vide de mots (Machi Tool l'a
            # transcrite) : c'etait de l'echo, qui s'apprend.
            if self.coupure is not None:
                self.coupure.fausse_coupure()
        elif cmd == "annuler":  # l'oreille : on laisse tomber ce qu'on ecoutait
            self.phrase, self.appris, self.etat = None, None, "veille"
        elif cmd == "parole":
            # Jarvis commence ou finit de parler (le processus de la voix le dit)
            if c.get("actif") and self.reglages.get("couper", True) and self.loopback is not None:
                if self.coupure is None:
                    self.coupure = Coupure()
                self.loopback.blocs.clear()
                self.loopback.demarrer()
                self.coupure.armer(self.horloge())
                self.parole = True
            else:
                self._arreter_parole()
        elif cmd == "apprendre":
            # PAS DE BIP ICI : la fenetre du modele couvre 775 ms, un bip juste
            # avant le mot entrerait dans le gabarit -- et il n'y est jamais
            # quand on appelle Jarvis pour de vrai. Le signal est visuel.
            self.appris = {"emps": [], "niveaux": [], "t": 0.0, "parole": False, "silence": 0.0}
            self.etat = "apprendre"

    def trame(self, x):
        import numpy as np
        rms = float(np.sqrt(np.mean(np.asarray(x, dtype=np.float64) ** 2)))
        ev = self.det.trame(x, chercher=(self.etat == "veille"))
        # « IL SEMBLE AVOIR OUBLIE MON JARVIS » : quand le mot appris passe PRES
        # du seuil sans le franchir, on le dit -- un NOMBRE, rien d'autre ne
        # sort d'ici avant l'eveil. Machi Tool l'affiche : monter la
        # sensibilite, ou reapprendre avec ce micro.
        d = getattr(self.det, "plus_proche", None)
        if (ev is None and d is not None and self.etat == "veille" and d < self.det.seuil * PRESQUE_FACTEUR
                and self.det.n - getattr(self, "_presque_n", -999) > 40):
            self._presque_n = self.det.n
            self.sortie({"evt": "presque", "distance": round(float(d), 4), "seuil": round(float(self.det.seuil), 4)})
        if ev is not None:
            self._arreter_parole()
            if self.reglages.get("son", True):
                self.jouer("eveil")
            avant = self.det.son_d_avant()
            self.phrase = Phrase(self.det.parle, avant=avant[:-TRAME] if len(avant) > TRAME else None)
            # La trame courante est dans « avant » : on ne la compte pas deux fois,
            # mais elle ne fait pas partie de la fenetre d'apres-carillon non plus.
            self.phrase.morceaux.append(np.asarray(x, dtype=np.int16))
            self.etat = "phrase"
            self.apres_coupure = False
            self.sortie({"evt": "reveil", "par": ev[0], "score": round(float(ev[1]), 4)})
            return
        if self.parole and self.etat == "veille" and self._coupe(x):
            # ON LUI COUPE LA PAROLE : il se tait (Machi Tool s'en charge), et la
            # phrase commence un peu AVANT la decision -- la voix y etait deja.
            # Si personne ne parle dans la seconde et demie, c'etait pour rien :
            # « vide », et Jarvis reprend sa phrase.
            self._arreter_parole()
            self.sortie({"evt": "coupure"})
            avant = self.det.son_d_avant()
            self.phrase = Phrase(self.det.parle, avant=avant[-int(0.6 * FREQ):], attente=1.5, ignorer=0.0)
            self.etat = "phrase"
            self.apres_coupure = True
            return
        if self.etat == "phrase" and self.phrase is not None:
            fin = self.phrase.trame(x, rms)
            if fin in ("fini", "vide"):
                apres, self.apres_coupure = self.apres_coupure, False
                ev = {"evt": "vide"}
                if fin == "fini":
                    ev = {"evt": "phrase", "wav": base64.b64encode(self.phrase.wav()).decode("ascii")}
                elif apres and self.coupure is not None:
                    self.coupure.fausse_coupure()      # personne n'a parle : c'etait de l'echo
                if apres:
                    ev["apres_coupure"] = True
                self.phrase, self.etat = None, "veille"
                self.sortie(ev)
        elif self.etat == "apprendre" and self.appris is not None:
            a = self.appris
            a["emps"].append(self.det.emps[-1])
            a["niveaux"].append(rms)
            a["t"] += TRAME_S
            p = self.det.parle(rms)
            if p:
                a["parole"], a["silence"] = True, 0.0
            elif a["parole"]:
                a["silence"] += TRAME_S
            fini = (a["parole"] and a["silence"] >= 0.55) or a["t"] >= 4.0
            if fini:
                self.appris, self.etat = None, "veille"
                if not a["parole"]:
                    self.sortie({"evt": "gabarit", "erreur": "rien entendu"})
                    return
                g = gabarit_depuis(a["emps"], a["niveaux"], self.det.parle)
                if g is None:
                    self.sortie({"evt": "gabarit", "erreur": "trop court ou trop long -- dis juste « Jarvis »"})
                else:
                    self.sortie({"evt": "gabarit", "vecteurs": g})
        # Un niveau par seconde : le panneau montre que le micro vit.
        now = time.time()
        if now - self.niveau_vu >= 1.0:
            self.niveau_vu = now
            db = 20 * math.log10(max(rms, 1.0) / 32768.0)
            self.sortie({"evt": "niveau", "db": round(db, 1), "etat": self.etat, "coupure": self.etat_coupure()})


def oreille_enfant(port, secret, dossier, source=None, jouer_son=None, loopback=None):
    """Le processus de l'oreille. S'en va quand Machi Tool ferme la connexion."""
    if os.name != "nt":
        try:
            os.nice(5)
        except Exception:
            pass
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=30)
    s.settimeout(None)
    s.sendall(struct.pack(">I", len(secret)) + str(secret).encode())
    verrou = threading.Lock()
    commandes = queue.Queue()
    vivant = threading.Event()
    vivant.set()

    def lire():
        try:
            while True:
                c = recevoir(s)
                if c is None:
                    break
                commandes.put(c)
        except Exception:
            pass
        vivant.clear()

    threading.Thread(target=lire, daemon=True).start()

    def sortie(ev):
        try:
            envoyer(s, ev, verrou)
        except Exception:
            vivant.clear()

    # La reference pour lui couper la parole : ce que jouent les haut-parleurs,
    # ouverte seulement pendant qu'il parle (Windows ; ailleurs, le mot d'eveil
    # seul le coupe).
    if loopback is None and source is None and os.name == "nt":
        loopback = Loopback()
    try:
        oreille = Oreille(Empreintes(dossier), sortie, jouer_son or jouer, loopback)
    except Exception as e:
        sortie({"evt": "erreur", "message": "modeles illisibles : %s" % str(e)[:160]})
        return
    # Le micro voulu : celui des reglages (Machi Tool l'envoie avec le reste),
    # ou celui de Windows. Le premier `config` arrive juste apres la poignee de
    # main : on l'attend un instant pour ne pas ouvrir le mauvais micro d'abord.
    for _ in range(0 if source else 20):
        try:
            oreille.commande(commandes.get(timeout=0.05))
            break
        except queue.Empty:
            continue
    micro_voulu = lambda: str(oreille.reglages.get("micro") or "")
    while vivant.is_set():
        flux = None
        try:
            nom = micro_voulu()
            if source:
                flux = source()
                sortie({"evt": "pret"})
            else:
                flux = micro_windows(nom, lambda n, ok: sortie({"evt": "pret", "micro": n, "trouve": ok}))
            for x in flux:
                while True:
                    try:
                        c = commandes.get_nowait()
                    except queue.Empty:
                        break
                    oreille.commande(c)
                if not vivant.is_set():
                    break
                # UN AUTRE MICRO A ETE CHOISI : on referme celui-ci et on
                # ouvre l'autre, sans redemarrer l'oreille.
                if not source and micro_voulu() != nom:
                    break
                oreille.trame(x)
            if flux is not None and hasattr(flux, "close"):
                flux.close()
            if source:
                break
        except Exception as e:
            sortie({"evt": "erreur", "message": "micro : %s" % str(e)[:160]})
            for _ in range(30):
                if not vivant.is_set():
                    break
                time.sleep(0.1)
    if loopback is not None:
        loopback.arreter()
    try:
        s.close()
    except Exception:
        pass


# ======================================================================
#  LA VOIX -- LE PROCESSUS QUI PARLE
#
#  Le modele reste charge tant que Jarvis ecoute : une reponse ne paie plus
#  le demarrage d'un programme ni le chargement d'une voix, seulement le
#  calcul de sa premiere phrase (trente millisecondes pour une voix legere),
#  pendant que la suivante se calcule. « Stop » coupe au dixieme de seconde.
# ======================================================================

def haut_parleur_windows(frequence):
    import soundcard as sc
    return sc.default_speaker().player(samplerate=frequence, channels=1)


class Bouche:
    """Dit des textes, un a la fois, et s'arrete net quand on le lui demande.
    `lecteur(frequence)` rend un gestionnaire de contexte qui a `play(float32)`.

    PLUSIEURS VOIX, UNE BOUCHE : Jarvis parle anglais avec Kokoro, le mode psy
    francais avec Piper. `syntheses` est {cle: synthese} (une synthese seule
    est rangee sous sa langue), et chaque « dire » nomme la sienne."""

    def __init__(self, syntheses, sortie, lecteur=None, silence=0.2):
        if not isinstance(syntheses, dict):
            syntheses = {getattr(syntheses, "langue", "fr"): syntheses}
        self.syns = dict(syntheses)
        self.sortie = sortie
        self.lecteur = lecteur or haut_parleur_windows
        self.silence = silence
        self.couper = threading.Event()

    @property
    def syn(self):
        return next(iter(self.syns.values()))

    def dire(self, ident, texte, lenteur=1.0, cle=None):
        """Phrase par phrase : si on lui coupe la parole, « fini » dit ce qui
        restait (`reste`, a partir de la phrase coupee) -- et s'il s'avere que
        personne n'avait parle, Jarvis reprend la."""
        import numpy as np
        syn = self.syns.get(cle) or self.syn
        langue = getattr(syn, "langue", "fr")
        self.couper.clear()
        file_ = queue.Queue(maxsize=3)
        fin = object()
        phrases = decouper_phrases(texte) or [texte]

        def produire():
            try:
                for k, bout in enumerate(phrases):
                    for son in syn.phrases(texte_pour_piper(bout, langue), lenteur):
                        if self.couper.is_set():
                            break
                        file_.put((k, son))
                    if self.couper.is_set():
                        break
            except Exception as e:
                file_.put(e)
            file_.put(fin)

        threading.Thread(target=produire, daemon=True).start()
        pas = syn.frequence // 10
        coupe, premiere, en_cours = False, True, 0
        with self.lecteur(syn.frequence) as hp:
            while True:
                son = file_.get()
                if son is fin:
                    break
                if isinstance(son, Exception):
                    self.sortie({"evt": "erreur", "message": "synthese : %s" % str(son)[:160]})
                    break
                en_cours, son = son
                if premiere:
                    self.sortie({"evt": "debut", "id": ident})
                    premiere = False
                son = np.concatenate([son, np.zeros(int(self.silence * self.syn.frequence), np.int16)])
                for i in range(0, len(son), pas):
                    if self.couper.is_set():
                        coupe = True
                        break
                    hp.play(son[i:i + pas].astype(np.float32) / 32768.0)
                if coupe:
                    break
        # Le producteur peut attendre une place dans la file : on la vide.
        while not file_.empty():
            try:
                file_.get_nowait()
            except queue.Empty:
                break
        ev = {"evt": "fini", "id": ident, "coupe": coupe}
        if coupe:
            ev["reste"] = " ".join(phrases[en_cours:])
        self.sortie(ev)


def voix_enfant(port, secret, lecteur=None):
    """Le processus de la voix. Attend « charger », puis des « dire »."""
    s = socket.create_connection(("127.0.0.1", int(port)), timeout=30)
    s.settimeout(None)
    s.sendall(struct.pack(">I", len(secret)) + str(secret).encode())
    verrou = threading.Lock()
    commandes = queue.Queue()
    etat = {"bouche": None}

    def sortie(ev):
        try:
            envoyer(s, ev, verrou)
        except Exception:
            pass

    def lire():
        try:
            while True:
                c = recevoir(s)
                if c is None:
                    break
                # « taire » n'attend pas son tour : il coupe la phrase en cours.
                if c.get("cmd") == "taire":
                    if etat["bouche"] is not None:
                        etat["bouche"].couper.set()
                    while True:
                        try:
                            commandes.get_nowait()
                        except queue.Empty:
                            break
                    continue
                commandes.put(c)
        except Exception:
            pass
        if etat["bouche"] is not None:
            etat["bouche"].couper.set()
        commandes.put(None)

    threading.Thread(target=lire, daemon=True).start()
    while True:
        c = commandes.get()
        if c is None:
            break
        try:
            if c.get("cmd") == "charger":
                # UNE VOIX PAR LANGUE, chargees l'une apres l'autre : l'anglais
                # de Jarvis (Kokoro) et le francais du mode psy (Piper).
                cle = str(c.get("cle") or "fr")
                ph = Phonemiseur(c["bibliotheque"], c["donnees"], c.get("espeak", "fr"))
                if c.get("moteur") == "kokoro":
                    syn = SyntheseKokoro(c["modele"], c["voix_fichier"], ph, c.get("voix", KOKORO_DEFAUT),
                                         c.get("fils", 4), c.get("langue", "en"))
                else:
                    syn = Synthese(c["modele"], ph, c.get("fils", 2), c.get("locuteur", 0))
                if etat["bouche"] is None:
                    etat["bouche"] = Bouche({cle: syn}, sortie, lecteur, float(c.get("silence", 0.2)))
                else:
                    etat["bouche"].syns[cle] = syn
                sortie({"evt": "pret", "cle": cle, "frequence": syn.frequence})
            elif c.get("cmd") == "dire" and etat["bouche"] is not None:
                etat["bouche"].dire(c.get("id"), c.get("texte", ""), float(c.get("lenteur", 1.0)),
                                    c.get("cle"))
        except Exception as e:
            sortie({"evt": "erreur", "cle": c.get("cle") if c.get("cmd") == "charger" else None,
                    "message": "%s : %s" % (type(e).__name__, str(e)[:160])})
            if c.get("cmd") == "dire":
                sortie({"evt": "fini", "id": c.get("id"), "coupe": False, "rate": True})
    try:
        s.close()
    except Exception:
        pass


# ======================================================================
#  SES MAINS SUR LE PC -- CE QUI NE DEPEND PAS DE WINDOWS
#
#  « Donne l'acces total a Jarvis, qu'il puisse interagir avec Spotify ou
#  creer des dossiers, decouvrir l'arborescence du PC ; lorsqu'il doit
#  interagir il demande un code d'acces a l'oral avant d'effectuer
#  l'operation. » BrainDebugger decrit les outils au modele ; Machi Tool les
#  execute ici, sur le poste, et c'est lui qui demande le code, a voix haute,
#  et le verifie ici : le code ne quitte jamais le PC.
#
#  CE QU'IL N'A PAS : supprimer, deplacer, renommer, ecrire dans un fichier,
#  lancer une commande. Ce qui ne se defait pas n'est pas dans la boite.
# ======================================================================

import hashlib
import hmac

_CHIFFRES_DITS = {
    "zero": "0", "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6",
    "sept": "7", "huit": "8", "neuf": "9", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "seven": "7", "eight": "8", "nine": "9", "oh": "0",
}


def normaliser_code(texte):
    """Le code tel qu'on le compare : les chiffres dits en lettres deviennent
    des chiffres (« un deux trois quatre », « 1, 2, 3, 4 », « 1234. » -- la
    transcription ecrit l'un ou l'autre), sans espaces ni ponctuation. Un mot
    de passe (« abricot ») reste un mot."""
    mots = normaliser(texte).replace("-", " ").split()
    return "".join(_CHIFFRES_DITS.get(m, m) for m in mots).replace("'", "")


def empreinte_code(code, sel):
    """Ce qu'on garde du code : une empreinte lente (PBKDF2, 200 000 tours),
    jamais le code."""
    return hashlib.pbkdf2_hmac("sha256", normaliser_code(code).encode("utf-8"),
                               bytes.fromhex(sel), 200000).hex()


def code_juste(dit, sel, empreinte):
    if not sel or not empreinte or not normaliser_code(dit):
        return False
    return hmac.compare_digest(empreinte_code(dit, sel), str(empreinte))


# Les noms qu'on donne aux dossiers, dans les deux langues -- sans accents.
ALIAS_DOSSIERS = {
    "accueil": "home", "home": "home", "~": "home", "mon dossier": "home", "profil": "home",
    "documents": "documents", "mes documents": "documents",
    "bureau": "desktop", "desktop": "desktop",
    "telechargements": "downloads", "mes telechargements": "downloads", "downloads": "downloads",
    "images": "pictures", "mes images": "pictures", "pictures": "pictures", "photos": "pictures",
    "musique": "music", "ma musique": "music", "music": "music",
    "videos": "videos", "mes videos": "videos",
}


def resoudre_chemin(chemin, bases):
    """« Documents\\Projets », « téléchargements », « C: », « D:\\Jeux », « ~ »
    -> un chemin absolu. `bases` : {"home": ..., "documents": ..., ...}."""
    brut = str(chemin or "").strip().strip('"').replace("\\", "/").replace("/", os.sep)
    if not brut:
        return bases.get("home", os.path.expanduser("~"))
    if re.fullmatch(r"[A-Za-z]:\\?", brut):
        return brut[0].upper() + ":" + os.sep
    tete, _, queue = brut.partition(os.sep)
    alias = ALIAS_DOSSIERS.get(sans_accents(tete).lower().strip())
    if alias and alias in bases:
        return os.path.normpath(os.path.join(bases[alias], queue)) if queue else bases[alias]
    if brut.startswith("~"):
        return os.path.normpath(os.path.join(bases.get("home", os.path.expanduser("~")), brut[1:].lstrip(os.sep)))
    return os.path.normpath(os.path.abspath(brut))


def chemin_protege(chemin, protegees):
    """Dans un dossier du systeme (Windows, Program Files...) : on n'y cree rien."""
    c = os.path.normcase(os.path.abspath(chemin))
    return any(c == os.path.normcase(p) or c.startswith(os.path.normcase(p).rstrip(os.sep) + os.sep)
               for p in protegees if p)


def _cache(nom, chemin=None):
    if nom.startswith(".") or nom.lower() in ("desktop.ini", "thumbs.db", "$recycle.bin",
                                              "system volume information"):
        return True
    try:
        attr = os.stat(chemin).st_file_attributes if chemin else 0
        return bool(attr & 0x6)          # cache ou systeme (Windows)
    except Exception:
        return False


def lister_dossier(chemin, profondeur=1, plafond=120):
    """Les NOMS de ce que contient un dossier, dossiers d'abord, sur un ou deux
    niveaux -- ni tailles, ni contenus. Rend un texte pour le modele."""
    if not os.path.isdir(chemin):
        raise FileNotFoundError("pas de dossier ici : %s" % chemin)
    lignes, compte = [], {"dossiers": 0, "fichiers": 0}

    def un(ch, niveau, marge):
        try:
            noms = sorted(os.listdir(ch), key=str.lower)
        except PermissionError:
            lignes.append(marge + "(acces refuse)")
            return
        dossiers = [n for n in noms if os.path.isdir(os.path.join(ch, n)) and not _cache(n, os.path.join(ch, n))]
        fichiers = [n for n in noms if not os.path.isdir(os.path.join(ch, n)) and not _cache(n, os.path.join(ch, n))]
        for d in dossiers:
            compte["dossiers"] += 1
            if len(lignes) < plafond:
                lignes.append(marge + d + "\\")
            if niveau < profondeur:
                un(os.path.join(ch, d), niveau + 1, marge + "  ")
        for f in fichiers:
            compte["fichiers"] += 1
            if len(lignes) < plafond:
                lignes.append(marge + f)

    un(chemin, 1, "")
    tete = "%s : %d dossiers, %d fichiers%s." % (chemin, compte["dossiers"], compte["fichiers"],
                                                  "" if profondeur == 1 else " (sur deux niveaux)")
    reste = compte["dossiers"] + compte["fichiers"] - len(lignes)
    return tete + "\n" + "\n".join(lignes) + ("\n... et %d de plus." % reste if reste > 0 else "")


_SAUTES = {"appdata", "node_modules", ".git", "$recycle.bin", "windows", "program files",
           "program files (x86)", "programdata", "system volume information", "__pycache__"}


# ECRIRE : DES FICHIERS NEUFS, DES NOTES. « Est-ce possible que Jarvis puisse
# ecrire dans un bloc-notes, ou creer des fichiers ? » Oui, prudemment :
#   - un fichier NEUF, jamais par-dessus un fichier qui existe (« (2) ») ;
#   - du texte seulement (.txt, .md, .csv...) : jamais un script ni un
#     programme -- « ouvre-le » ne doit jamais lancer ce que le modele a ecrit ;
#   - ses notes vont dans SON dossier, et c'est la seule chose qu'il complete.

EXTENSIONS_TEXTE = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".css", ".yaml", ".yml",
                    ".log", ".ini", ".rtf", ".srt"}
ECRIT_MAX = 200_000                      # caracteres


def nom_sur(nom, defaut="Note"):
    """Un nom de fichier que Windows accepte : sans \\ / : * ? " < > |, pas trop long."""
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", str(nom or "")).strip(" .")
    n = re.sub(r"\s+", " ", n)[:80].strip(" .")
    if n.upper().split(".")[0] in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT1"):
        n = "_" + n
    return n or defaut


def chemin_libre(chemin):
    """Le chemin, ou « nom (2).ext », « nom (3).ext »... s'il est pris."""
    if not os.path.exists(chemin):
        return chemin
    base, ext = os.path.splitext(chemin)
    for i in range(2, 1000):
        c = "%s (%d)%s" % (base, i, ext)
        if not os.path.exists(c):
            return c
    raise FileExistsError("trop de fichiers de ce nom : %s" % chemin)


def _texte_a_ecrire(contenu):
    t = str(contenu if contenu is not None else "")
    if len(t) > ECRIT_MAX:
        raise ValueError("trop long (%d caracteres, %d au plus)" % (len(t), ECRIT_MAX))
    return t.replace("\r\n", "\n").replace("\n", "\r\n") if os.name == "nt" else t


def preparer_fichier(chemin, contenu, protegees=()):
    """Ce qu'il faudra ecrire pour un fichier texte NEUF : (chemin libre,
    texte, encodage). N'ecrit rien -- ce module ne touche pas au disque
    (l'oreille en depend) : machi_tool.py ecrit."""
    ext = os.path.splitext(chemin)[1].lower()
    if not ext:
        chemin, ext = chemin + ".txt", ".txt"
    if ext not in EXTENSIONS_TEXTE:
        raise PermissionError("seulement des fichiers texte (%s), pas « %s »"
                              % (" ".join(sorted(EXTENSIONS_TEXTE)), ext))
    dossier = os.path.dirname(chemin) or "."
    chemin = os.path.join(dossier, nom_sur(os.path.splitext(os.path.basename(chemin))[0]) + ext)
    if chemin_protege(chemin, protegees):
        raise PermissionError("dossier du systeme : on n'y ecrit rien (%s)" % dossier)
    return (chemin_libre(chemin), _texte_a_ecrire(contenu),
            "utf-8-sig" if ext in (".txt", ".csv", ".tsv") else "utf-8")


def preparer_note(dossier, texte, titre="", ajouter_a="", maintenant=None):
    """Ce qu'il faudra ecrire pour une note : neuve (titre, sinon la date), ou
    ajoutee a la fin d'une note deja la. Rend (chemin, texte, mode "x" ou
    "a", encodage)."""
    t = time.localtime(time.time() if maintenant is None else maintenant)
    if not str(texte or "").strip():
        raise ValueError("rien a ecrire")
    if ajouter_a:
        notes = [f for f in (os.listdir(dossier) if os.path.isdir(dossier) else [])
                 if f.lower().endswith((".txt", ".md"))]
        trouves = choisir(ajouter_a, notes, nom=lambda f: os.path.splitext(f)[0], seuil=40)
        if not trouves:
            raise LookupError("aucune note ne s'appelle « %s » (il y a : %s)"
                              % (ajouter_a, ", ".join(os.path.splitext(f)[0] for f in sorted(notes)[:15]) or "aucune"))
        return (os.path.join(dossier, trouves[0]),
                _texte_a_ecrire("\n\n-- %s --\n%s\n" % (time.strftime("%d/%m/%Y %H:%M", t), str(texte).strip())),
                "a", "utf-8")
    nom = nom_sur(titre, defaut="Note du %s" % time.strftime("%Y-%m-%d %Hh%M", t))
    chemin, contenu, encodage = preparer_fichier(os.path.join(dossier, nom + ".txt"), str(texte).strip() + "\n")
    return chemin, contenu, "x", encodage


# LA RECHERCHE QU'ON AFFINE. « J'ai 523 fichiers qui mentionnent unit » --
# « rajoute stage » -- « j'en ai 3 » -- « ouvre-les ». Les criteres : des mots
# (tous, dans le chemin sous le dossier de depart : le nom du fichier ou de ses
# dossiers), un type, une anciennete. Les resultats sont numerotes du plus
# recent au plus ancien, pour « ouvre le 2 ».

TYPES_FICHIERS = {
    "pdf": {".pdf"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff", ".svg"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v"},
    "audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"},
    "document": {".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pages"},
    "tableur": {".xls", ".xlsx", ".xlsm", ".csv", ".ods", ".numbers"},
    "presentation": {".ppt", ".pptx", ".odp", ".key"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "code": {".py", ".js", ".ts", ".cs", ".cpp", ".c", ".h", ".java", ".html", ".css", ".json", ".unity"},
}
_NOMS_TYPES = {"pdf": "PDF", "image": "images", "video": "videos", "audio": "sons", "document": "documents",
               "tableur": "tableurs", "presentation": "presentations", "archive": "archives",
               "code": "code", "dossier": "dossiers"}


def criteres(mots="", type_="", jours=None):
    t = str(type_ or "").strip().lower()
    if t and t not in TYPES_FICHIERS and t != "dossier":
        raise ValueError("type inconnu : %s (%s)" % (t, ", ".join(list(TYPES_FICHIERS) + ["dossier"])))
    j = int(jours) if jours else None
    return {"mots": [m for m in _mots(mots) if len(m) > 1], "type": t, "jours": j if j and j > 0 else None}


def correspond(relatif, est_dossier, mtime, crit, maintenant):
    if crit["type"] == "dossier" and not est_dossier:
        return False
    if crit["type"] and crit["type"] != "dossier" and (
            est_dossier or os.path.splitext(relatif)[1].lower() not in TYPES_FICHIERS[crit["type"]]):
        return False
    if crit["jours"] and mtime < maintenant - crit["jours"] * 86400:
        return False
    chemin = sans_accents(relatif).lower()
    return all(m in chemin for m in crit["mots"])


def trouver_fichiers(racine, crit, plafond=5000, delai=6.0, profondeur_max=8, horloge=time.monotonic,
                     maintenant=None):
    """([(chemin, est_dossier, mtime)] du plus recent au plus ancien, coupe).
    Borne en nombre, en profondeur et en temps."""
    if not os.path.isdir(racine):
        raise FileNotFoundError("pas de dossier ici : %s" % racine)
    if not crit["mots"] and not crit["type"] and not crit["jours"]:
        raise ValueError("rien a chercher")
    maintenant = time.time() if maintenant is None else maintenant
    trouve, fin, coupe = [], horloge() + delai, False
    base = racine.rstrip(os.sep).count(os.sep)
    for ch, dossiers, fichiers in os.walk(racine):
        if horloge() > fin:
            coupe = True
            break
        dossiers[:] = [d for d in dossiers if d.lower() not in _SAUTES and not _cache(d)
                       and ch.count(os.sep) - base < profondeur_max]
        for n in dossiers + fichiers:
            if _cache(n):
                continue
            chemin = os.path.join(ch, n)
            try:
                mtime = os.stat(chemin).st_mtime
            except OSError:
                continue
            if correspond(os.path.relpath(chemin, racine), n in dossiers, mtime, crit, maintenant):
                trouve.append((chemin, n in dossiers, mtime))
        if len(trouve) >= plafond:
            coupe = True
            break
    trouve.sort(key=lambda x: -x[2])
    return trouve[:plafond], coupe


def resume_recherche(racine, crit, resultats, coupe, montrer=10):
    quoi = " ".join(crit["mots"])
    bouts = ["« %s »" % quoi] if quoi else []
    if crit["type"]:
        bouts.append(_NOMS_TYPES[crit["type"]])
    if crit["jours"]:
        bouts.append("des %d derniers jours" % crit["jours"])
    n_dos = sum(1 for _, d, _ in resultats if d)
    tete = "%d resultat%s (%d dossier%s, %d fichier%s) pour %s sous %s%s." % (
        len(resultats), "s" if len(resultats) > 1 else "", n_dos, "s" if n_dos > 1 else "",
        len(resultats) - n_dos, "s" if len(resultats) - n_dos > 1 else "", ", ".join(bouts), racine,
        " (recherche arretee avant la fin : il y en a peut-etre plus)" if coupe else "")
    if not resultats:
        return tete
    lignes = ["%d. %s%s -- %s" % (i, chemin, os.sep if d else "", time.strftime("%d/%m/%Y", time.localtime(t)))
              for i, (chemin, d, t) in enumerate(resultats[:montrer], 1)]
    reste = len(resultats) - montrer
    return tete + " Les plus recents :\n" + "\n".join(lignes) + ("\n... et %d de plus." % reste if reste > 0 else "")


def affiner(recherche, ajouter="", retirer="", type_=None, jours=None, maintenant=None):
    """Les criteres de `recherche` modifies, et s'il suffit de filtrer ce qu'on
    a deja (on resserre, et la recherche d'avant etait complete) ou s'il faut
    tout reparcourir. Rend (criteres, resultats ou None)."""
    c = dict(recherche["criteres"], mots=list(recherche["criteres"]["mots"]))
    resserre = True
    for m in criteres(ajouter)["mots"]:
        if m not in c["mots"]:
            c["mots"].append(m)
    otes = set(criteres(retirer)["mots"])
    if otes & set(c["mots"]):
        c["mots"] = [m for m in c["mots"] if m not in otes]
        resserre = False
    if type_ is not None:
        t = criteres(type_=type_)["type"]
        if c["type"] and t != c["type"]:
            resserre = False
        c["type"] = t
    if jours is not None:
        j = criteres(jours=jours)["jours"]
        if c["jours"] and (not j or j > c["jours"]):
            resserre = False
        c["jours"] = j
    if resserre and not recherche.get("coupe"):
        maintenant = time.time() if maintenant is None else maintenant
        garde = [r for r in recherche["resultats"]
                 if correspond(os.path.relpath(r[0], recherche["racine"]), r[1], r[2], c, maintenant)]
        return c, garde
    return c, None


def creer_dossier(chemin, protegees=()):
    if chemin_protege(chemin, protegees):
        raise PermissionError("dossier du systeme : on n'y cree rien (%s)" % chemin)
    if os.path.exists(chemin):
        return "Il existe deja : %s" % chemin
    os.makedirs(chemin)
    return "Cree : %s" % chemin


# ======================================================================
#   CE QU'IL RETIENT DE TOI, CE QUE TU AS VU SUR LE WEB
# ======================================================================
#
# « Il faudrait que Jarvis retienne des preferences, et qu'il ait acces a
# l'historique pour retrouver une video ou un lien, ou qu'il puisse faire une
# recherche internet sur Google Chrome. »
#
# LES PREFERENCES : des phrases courtes qu'il retient quand on le lui demande
# (« retiens que je prefere les reponses courtes »). Elles vivent dans la
# config, sur le poste, et partent avec chaque question a Jarvis -- c'est ce
# qui les lui fait connaitre. Reglages > Jarvis les montre et les efface.
#
# L'HISTORIQUE : lu SUR LE POSTE, a la demande seulement, dans une copie
# temporaire effacee aussitot. Ce qui part a Jarvis, ce sont les quelques pages
# qui correspondent a la recherche (dix au plus) -- jamais l'historique entier.
# Rien n'est garde. Les parametres d'adresse qui ressemblent a des jetons
# (token, session, code...) sont retires avant de partir.

PREFERENCES_MAX = 40
PREFERENCE_LONGUEUR = 200
_MOTS_VIDES = frozenset(
    "le la les l de d des du un une et en a au aux sur pour avec que qui ce cette ces mon ma mes "
    "the an of on in to for and my".split())


def _mots(texte):
    return [m for m in normaliser(texte).replace("'", " ").split() if m not in _MOTS_VIDES]


def ajouter_preference(liste, texte):
    """Rend la liste avec la preference en dernier (sans doublon, 40 au plus :
    la plus ancienne s'en va)."""
    t = " ".join(str(texte or "").split())[:PREFERENCE_LONGUEUR]
    if not _mots(t):
        raise ValueError("preference vide")
    liste = [p for p in (liste or []) if normaliser(p) != normaliser(t)]
    return (liste + [t])[-PREFERENCES_MAX:]


def retirer_preference(liste, texte="", tout=False):
    """Rend (liste restante, preferences retirees). La designation est quelques
    mots : on retire celle(s) qui en partagent le plus, s'il y en a assez."""
    liste = list(liste or [])
    if tout:
        return [], liste
    cible = set(_mots(texte))
    if not cible:
        return liste, []
    scores = [len(cible & set(_mots(p))) / len(cible) for p in liste]
    meilleur = max(scores, default=0)
    if meilleur < 0.5:
        return liste, []
    retirees = [p for p, s in zip(liste, scores) if s == meilleur]
    return [p for p, s in zip(liste, scores) if s != meilleur], retirees


_EPOQUE_CHROME = 11644473600          # secondes entre 1601 (Chrome) et 1970


def fichiers_historique(env=None):
    """Les historiques des navigateurs du poste : [(navigateur, genre, chemin)]."""
    env = os.environ if env is None else env
    local, roaming = env.get("LOCALAPPDATA", ""), env.get("APPDATA", "")
    out = []
    for nom, parties in (("Chrome", ("Google", "Chrome")), ("Edge", ("Microsoft", "Edge")),
                         ("Brave", ("BraveSoftware", "Brave-Browser"))):
        base = os.path.join(local, *parties, "User Data") if local else ""
        if not base or not os.path.isdir(base):
            continue
        for profil in sorted(os.listdir(base)):
            f = os.path.join(base, profil, "History")
            if (profil == "Default" or profil.startswith("Profile ")) and os.path.isfile(f):
                out.append((nom, "chromium", f))
    ff = os.path.join(roaming, "Mozilla", "Firefox", "Profiles") if roaming else ""
    if ff and os.path.isdir(ff):
        for profil in sorted(os.listdir(ff)):
            f = os.path.join(ff, profil, "places.sqlite")
            if os.path.isfile(f):
                out.append(("Firefox", "firefox", f))
    return out


def lire_historique(genre, chemin, depuis, plafond=50000):
    """[(url, titre, quand)] depuis `depuis` (secondes, epoque Unix), lu en
    lecture seule. Machi Tool lui passe une copie du fichier (le navigateur
    tient l'original) : ce module-ci n'ecrit rien sur le disque."""
    import sqlite3
    from urllib.parse import quote
    con = sqlite3.connect("file:%s?mode=ro" % quote(os.path.abspath(chemin).replace(os.sep, "/")), uri=True)
    try:
        if genre == "chromium":
            lignes = con.execute(
                "SELECT url, title, last_visit_time FROM urls WHERE last_visit_time >= ? "
                "ORDER BY last_visit_time DESC LIMIT ?",
                (int((depuis + _EPOQUE_CHROME) * 1000000), plafond)).fetchall()
            return [(u, t or "", q / 1e6 - _EPOQUE_CHROME) for u, t, q in lignes]
        lignes = con.execute(
            "SELECT url, title, last_visit_date FROM moz_places WHERE last_visit_date >= ? "
            "ORDER BY last_visit_date DESC LIMIT ?", (int(depuis * 1000000), plafond)).fetchall()
        return [(u, t or "", q / 1e6) for u, t, q in lignes]
    finally:
        con.close()


_PARAM_SECRET = re.compile(r"token|session|sess|auth|code|key|sig|secret|pass|pwd|ticket|otp|jwt", re.I)


def adresse_propre(url):
    """L'adresse sans son ancre, ni les parametres qui ressemblent a des secrets."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    try:
        p = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _PARAM_SECRET.search(k)]
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))[:400]
    except ValueError:
        return url[:400]


def _quand(t, maintenant):
    import datetime
    jours = (datetime.date.fromtimestamp(maintenant) - datetime.date.fromtimestamp(t)).days
    if jours <= 0:
        return "aujourd'hui"
    if jours == 1:
        return "hier"
    if jours < 60:
        return "il y a %d jours" % jours
    return time.strftime("%d/%m/%Y", time.localtime(t))


def chercher_historique(recherche, fichiers, jours=90, plafond=10, maintenant=None, lire=None):
    """Les pages dont le titre ou l'adresse contient tous les mots (ou tous
    sauf un, a defaut), les plus recentes d'abord. Rend un texte pour Jarvis."""
    mots = _mots(recherche)
    if not mots:
        raise ValueError("rien a chercher")
    if not fichiers:
        return "Aucun historique de navigateur trouve sur ce PC (Chrome, Edge, Brave, Firefox)."
    maintenant = time.time() if maintenant is None else maintenant
    jours = max(1, min(3650, int(jours or 90)))
    depuis = maintenant - jours * 86400
    trouves, lus, rates = {}, [], []
    for nav, genre, chemin in fichiers:
        try:
            lignes = (lire or lire_historique)(genre, chemin, depuis)
        except Exception:
            rates.append(nav)
            continue
        if nav not in lus:
            lus.append(nav)
        for url, titre, quand in lignes:
            if not str(url).startswith(("http://", "https://")):
                continue
            botte = normaliser(titre + " " + url.split("://", 1)[-1].replace("/", " ").replace(".", " "))
            score = sum(1 for m in mots if m in botte)
            if score and (url not in trouves or quand > trouves[url][2]):
                trouves[url] = (score, titre, quand, nav)
    complets = [(u, v) for u, v in trouves.items() if v[0] == len(mots)]
    partiels = False
    if not complets and len(mots) > 1:
        complets = [(u, v) for u, v in trouves.items() if v[0] >= len(mots) - 1]
        partiels = bool(complets)
    if not lus:
        return "Impossible de lire l'historique (%s)." % ", ".join(rates)
    if not complets:
        return "Rien dans l'historique (%s, %d derniers jours) pour « %s »." % (
            ", ".join(lus), jours, " ".join(mots))
    complets.sort(key=lambda x: -x[1][2])
    lignes = ["%d page%s trouvee%s (%s, %d derniers jours)%s ; les plus recentes :" % (
        len(complets), "s" if len(complets) > 1 else "", "s" if len(complets) > 1 else "",
        ", ".join(lus), jours, ", sans tous les mots" if partiels else "")]
    for url, (_, titre, quand, nav) in complets[:plafond]:
        lignes.append("- « %s » -- %s -- %s" % ((titre or "(sans titre)")[:160], _quand(quand, maintenant),
                                                adresse_propre(url)))
    return "\n".join(lignes)


def lien_permis(url):
    """Une adresse web qu'on peut ouvrir : http(s), un domaine, pas d'espace."""
    from urllib.parse import urlsplit
    u = str(url or "").strip()
    try:
        p = urlsplit(u)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc) and not re.search(r"\s", u) and len(u) <= 2000


def adresse_google(recherche):
    from urllib.parse import quote_plus
    q = " ".join(str(recherche or "").split())[:300]
    if not q:
        raise ValueError("rien a chercher")
    return "https://www.google.com/search?q=" + quote_plus(q)


# ======================================================================
#   LE PC EN ENTIER : APPLIS, JEUX, FENETRES, SON, YOUTUBE, SPOTIFY
# ======================================================================
#
# « J'aimerais avoir un compagnon qui peut interagir le plus possible avec
# mon PC. » Sans souris ni clavier simules : par Windows et par les
# applications elles-memes. Ici, ce qui se teste sans Windows ; les appels au
# systeme sont dans machi_tool.py.

_MOTS_APPLI_VIDES = _MOTS_VIDES | frozenset("jeu jeux appli application logiciel programme app game".split())
_RACCOURCIS_IGNORES = re.compile(
    r"uninstall|d[eé]sinstall|readme|lisez|help|aide|manual|manuel|license|licence|website|site web|"
    r"release notes|documentation|support|report a bug", re.I)
_STEAM_IGNORES = re.compile(r"redistributable|steamworks|proton|steam linux runtime|directx|vcredist", re.I)


def _chaines_vdf(texte):
    """Les paires « "cle" "valeur" » d'un fichier Valve (acf, vdf), dans l'ordre."""
    return [(k.lower(), v.replace("\\\\", "\\"))
            for k, v in re.findall(r'"([^"]+)"\s+"((?:[^"\\]|\\.)*)"', texte)]


def jeux_steam(racine):
    """[(nom, "steam://rungameid/ID", "jeu")] pour chaque jeu installe, dans
    toutes les bibliotheques Steam."""
    if not racine or not os.path.isdir(racine):
        return []
    biblis = [racine]
    try:
        with open(os.path.join(racine, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            biblis += [v for k, v in _chaines_vdf(f.read()) if k == "path"]
    except OSError:
        pass
    vus, jeux = set(), []
    for b in biblis:
        dossier = os.path.join(b, "steamapps")
        if os.path.normcase(os.path.abspath(dossier)) in vus or not os.path.isdir(dossier):
            continue
        vus.add(os.path.normcase(os.path.abspath(dossier)))
        for f in sorted(os.listdir(dossier)):
            if not (f.startswith("appmanifest_") and f.endswith(".acf")):
                continue
            try:
                with open(os.path.join(dossier, f), encoding="utf-8", errors="replace") as fh:
                    paires = dict(_chaines_vdf(fh.read()))
            except OSError:
                continue
            nom, ident = paires.get("name", ""), paires.get("appid", "")
            if nom and ident.isdigit() and not _STEAM_IGNORES.search(nom):
                jeux.append((nom, "steam://rungameid/" + ident, "jeu"))
    return jeux


def raccourcis_menu(dossiers):
    """[(nom, chemin du raccourci, "appli")] du menu Demarrer, sans les
    desinstalleurs ni les « lisez-moi »."""
    out, vus = [], set()
    for d in dossiers:
        if not d or not os.path.isdir(d):
            continue
        for racine, _, fichiers in os.walk(d):
            for f in sorted(fichiers):
                base, ext = os.path.splitext(f)
                if ext.lower() not in (".lnk", ".url") or _RACCOURCIS_IGNORES.search(base):
                    continue
                if normaliser(base) in vus:
                    continue
                vus.add(normaliser(base))
                out.append((base, os.path.join(racine, f), "appli"))
    return out


def _mots_appli(texte):
    return [m for m in re.sub(r"['_-]", " ", normaliser(texte)).split() if m not in _MOTS_APPLI_VIDES]


def score_nom(demande, nom):
    """0 a 100 : a quel point `nom` est ce qu'on a demande."""
    d, n = " ".join(_mots_appli(demande)), " ".join(_mots_appli(nom))
    if not d or not n:
        return 0
    if d == n:
        return 100
    if len(d) >= 3 and (" " + d + " ") in (" " + n + " "):
        return 90 - min(20, len(n) - len(d))
    if len(d) >= 4 and d in n.replace(" ", ""):
        return 75 - min(20, len(n) - len(d))
    md, mn = set(d.split()), set(n.split())
    commun = len(md & mn)
    return int(60 * commun / len(md)) if commun else 0


def choisir(demande, elements, nom=lambda e: e[0], seuil=45, tous=False):
    """Les elements qui correspondent le mieux (ex aequo compris), ou [].
    `tous` : tous ceux qui passent le seuil, les meilleurs d'abord."""
    notes = [(score_nom(demande, nom(e)), e) for e in elements]
    if tous:
        return [e for s, e in sorted(notes, key=lambda x: -x[0]) if s >= seuil]
    meilleur = max((s for s, _ in notes), default=0)
    if meilleur < seuil:
        return []
    return [e for s, e in notes if s == meilleur]


def nouveau_niveau(actuel, action, niveau=None, pas=10):
    """Le volume (ou la luminosite) apres « regler », « monter », « baisser »,
    de 0 a 100."""
    actuel = float(actuel)
    if action == "regler":
        if niveau is None:
            raise ValueError("quel niveau ?")
        v = float(niveau)
    elif action == "monter":
        v = actuel + (float(niveau) if niveau else pas)
    elif action == "baisser":
        v = actuel - (float(niveau) if niveau else pas)
    else:
        raise ValueError("action inconnue : %s" % action)
    return int(round(max(0.0, min(100.0, v))))


_SITES = (
    ("YouTube", ("youtube.com", "youtu.be")),
    ("Musique", ("open.spotify.com", "soundcloud.com", "deezer.com", "music.apple.com", "bandcamp.com")),
    ("Reddit", ("reddit.com", "redd.it")),
    ("Instagram", ("instagram.com",)),
    ("TikTok", ("tiktok.com",)),
    ("X", ("x.com", "twitter.com")),
    ("Facebook", ("facebook.com", "messenger.com")),
    ("Twitch", ("twitch.tv",)),
    ("Discord", ("discord.com",)),
    ("Mails", ("mail.google.com", "outlook.live.com", "outlook.office.com", "outlook.office365.com")),
)


def site_de(domaine):
    """La famille d'un onglet : YouTube, Reddit, Instagram... ou « Autres »."""
    d = str(domaine or "").lower().removeprefix("www.").removeprefix("m.")
    if d == "music.youtube.com":
        return "Musique"
    for nom, domaines in _SITES:
        if any(d == x or d.endswith("." + x) for x in domaines):
            return nom
    return "Autres"


def ranger_onglets(onglets, domaine=lambda o: o.get("domaine", "")):
    """[(famille, [onglets])] dans l'ordre de _SITES, « Autres » a la fin."""
    ordre = [n for n, _ in _SITES] + ["Autres"]
    rangs = {}
    for o in onglets:
        rangs.setdefault(site_de(domaine(o)), []).append(o)
    return [(n, rangs[n]) for n in ordre if n in rangs]


def onglets_a_fermer(onglets, action, gardes=None):
    """Les onglets a fermer pour « ferme a gauche / a droite » (de l'onglet
    affiche) et « garde que ceux-la / garde celui-ci », dans la fenetre du
    moment. Jamais un onglet epingle. `gardes` : ceux a garder (sinon
    l'onglet affiche)."""
    if not onglets:
        return []
    fen = [o for o in onglets if o.get("fenetre_courante")] or onglets
    actif = next((o for o in fen if o.get("actif")), None)
    ferme = [o for o in fen if not o.get("epingle")]
    if action in ("fermer_gauche", "fermer_droite"):
        if actif is None or actif.get("position") is None:
            return []
        p = actif["position"]
        return [o["id"] for o in ferme if (o.get("position", p) < p if action == "fermer_gauche"
                                           else o.get("position", p) > p)]
    if action == "garder":
        garde = {o["id"] for o in (gardes if gardes is not None else ([actif] if actif else []))}
        if not garde:
            return []
        return [o["id"] for o in ferme if o["id"] not in garde]
    raise ValueError("action inconnue : %s" % action)


def premiere_video_youtube(html):
    """(identifiant, titre) de la premiere video d'une page de resultats
    YouTube -- pas une publicite, pas une chaine. None sinon."""
    m = re.search(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', html or "")
    if not m:
        return None
    titre = ""
    t = re.search(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', html[m.end():m.end() + 6000])
    if t:
        try:
            titre = json.loads('"' + t.group(1) + '"')
        except ValueError:
            titre = t.group(1)
    return m.group(1), titre


# --------------------------- SPOTIFY -----------------------------------
#
# L'API officielle, avec le compte de la personne : elle cree une app
# developpeur Spotify (gratuite), colle son Client ID dans Machi Tool, et se
# connecte une fois (PKCE : pas de secret a garder). Le jeton de
# renouvellement reste dans la config, sur le PC. Lancer la lecture demande
# Spotify Premium -- c'est une regle de Spotify.

SPOTIFY_PORT = 8765
SPOTIFY_RETOUR = "http://127.0.0.1:%d/callback" % SPOTIFY_PORT
SPOTIFY_PORTEES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
                   "user-library-modify user-library-read playlist-read-private")
_SPOTIFY_API = "https://api.spotify.com/v1"
_SPOTIFY_COMPTES = "https://accounts.spotify.com"


def _b64url(octets):
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode("ascii")


def pkce_paire():
    """(verificateur, defi) : le defi part avec l'autorisation, le
    verificateur avec l'echange du code."""
    verif = _b64url(os.urandom(64))
    return verif, _b64url(hashlib.sha256(verif.encode("ascii")).digest())


def spotify_url_autorisation(client_id, defi, etat):
    from urllib.parse import urlencode
    return _SPOTIFY_COMPTES + "/authorize?" + urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": SPOTIFY_RETOUR,
        "code_challenge_method": "S256", "code_challenge": defi, "scope": SPOTIFY_PORTEES, "state": etat})


def http_json(methode, url, entetes=None, corps=None, delai=10):
    """(statut, reponse JSON ou None). `corps` : un dict (JSON) ou des octets."""
    import urllib.request
    import urllib.error
    donnees = None
    entetes = dict(entetes or {})
    if isinstance(corps, dict):
        donnees = json.dumps(corps).encode("utf-8")
        entetes.setdefault("Content-Type", "application/json")
    elif corps is not None:
        donnees = corps
    req = urllib.request.Request(url, data=donnees, headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            brut = r.read()
            statut = r.status
    except urllib.error.HTTPError as e:
        brut, statut = e.read(), e.code
    try:
        return statut, (json.loads(brut.decode("utf-8")) if brut else None)
    except ValueError:
        return statut, None


class ErreurSpotify(Exception):
    pass


class Spotify:
    """Le compte Spotify de la personne, par l'API Web. `http` et `dormir` se
    remplacent dans les tests ; `sauver(refresh)` garde un nouveau jeton de
    renouvellement quand Spotify en donne un."""

    def __init__(self, client_id, refresh, http=http_json, sauver=None, dormir=time.sleep):
        self.client_id, self.refresh = client_id, refresh
        self.http, self.sauver, self.dormir = http, sauver, dormir
        self.acces, self.expire = None, 0.0

    @staticmethod
    def echanger_code(client_id, code, verif, http=http_json):
        from urllib.parse import urlencode
        statut, r = http("POST", _SPOTIFY_COMPTES + "/api/token",
                         {"Content-Type": "application/x-www-form-urlencoded"},
                         urlencode({"grant_type": "authorization_code", "code": code,
                                    "redirect_uri": SPOTIFY_RETOUR, "client_id": client_id,
                                    "code_verifier": verif}).encode("ascii"))
        if statut != 200 or not (r or {}).get("refresh_token"):
            raise ErreurSpotify("Spotify a refuse la connexion (%s)." % ((r or {}).get("error_description")
                                                                       or (r or {}).get("error") or statut))
        return r

    def jeton(self):
        if self.acces and time.time() < self.expire - 60:
            return self.acces
        from urllib.parse import urlencode
        statut, r = self.http("POST", _SPOTIFY_COMPTES + "/api/token",
                              {"Content-Type": "application/x-www-form-urlencoded"},
                              urlencode({"grant_type": "refresh_token", "refresh_token": self.refresh,
                                         "client_id": self.client_id}).encode("ascii"))
        if statut != 200 or not (r or {}).get("access_token"):
            raise ErreurSpotify("La connexion a Spotify a expire : reconnecte-le dans Machi Tool "
                                "(Reglages > Jarvis > Spotify).")
        self.acces, self.expire = r["access_token"], time.time() + float(r.get("expires_in") or 3600)
        if r.get("refresh_token") and r["refresh_token"] != self.refresh:
            self.refresh = r["refresh_token"]
            if self.sauver:
                self.sauver(self.refresh)
        return self.acces

    def api(self, methode, chemin, params=None, corps=None):
        from urllib.parse import urlencode
        url = _SPOTIFY_API + chemin + ("?" + urlencode(params) if params else "")
        for essai in (0, 1):
            statut, r = self.http(methode, url, {"Authorization": "Bearer " + self.jeton()}, corps)
            if statut == 401 and not essai:
                self.acces = None
                continue
            return statut, r
        return statut, r

    def appareil(self):
        statut, r = self.api("GET", "/me/player/devices")
        appareils = [a for a in (r or {}).get("devices") or [] if a and not a.get("is_restricted")]
        if not appareils:
            return None
        for cle in (lambda a: a.get("is_active"), lambda a: a.get("type") == "Computer", lambda a: True):
            for a in appareils:
                if cle(a):
                    return a
        return None

    def attendre_appareil(self, ouvrir_appli=None, secondes=8):
        a = self.appareil()
        if a or not ouvrir_appli:
            return a
        ouvrir_appli()
        for _ in range(int(secondes)):
            self.dormir(1.0)
            a = self.appareil()
            if a:
                return a
        return None

    def chercher(self, recherche, genre):
        """(uri, nom a dire, est_un_contexte)."""
        q = " ".join(str(recherche or "").split())
        if not q:
            raise ErreurSpotify("Que faut-il mettre ?")
        if genre == "playlist":
            statut, r = self.api("GET", "/me/playlists", {"limit": 50})
            miennes = [p for p in (r or {}).get("items") or [] if p]
            trouvees = choisir(q, miennes, nom=lambda p: p.get("name") or "")
            if trouvees:
                return trouvees[0]["uri"], "ta playlist « %s »" % trouvees[0]["name"], True
        type_ = {"titre": "track", "album": "album", "artiste": "artist", "playlist": "playlist"}.get(genre, "track")
        statut, r = self.api("GET", "/search", {"q": q, "type": type_, "limit": 5, "market": "from_token"})
        items = [i for i in ((r or {}).get(type_ + "s") or {}).get("items") or [] if i]
        if not items:
            raise ErreurSpotify("Rien trouve sur Spotify pour « %s »." % q)
        i = items[0]
        if type_ == "track":
            return i["uri"], "« %s » de %s" % (i.get("name"), ", ".join(a.get("name", "") for a in i.get("artists") or [])), False
        if type_ == "album":
            return i["uri"], "l'album « %s » de %s" % (i.get("name"), ", ".join(a.get("name", "") for a in i.get("artists") or [])), True
        if type_ == "artist":
            return i["uri"], i.get("name", ""), True
        return i["uri"], "la playlist « %s »" % i.get("name"), True

    def jouer(self, recherche, genre="titre", file=False, ouvrir_appli=None):
        uri, dit, contexte = self.chercher(recherche, genre)
        a = self.attendre_appareil(ouvrir_appli)
        if not a:
            raise ErreurSpotify("Spotify n'est ouvert nulle part : ouvre l'application, puis redemande.")
        if file:
            if contexte:
                raise ErreurSpotify("On ne peut mettre dans la file qu'un titre, pas un album ni une playlist.")
            statut, r = self.api("POST", "/me/player/queue", {"uri": uri, "device_id": a["id"]})
            fait = "Ajoute a la file : %s." % dit
        else:
            statut, r = self.api("PUT", "/me/player/play", {"device_id": a["id"]},
                                 {"context_uri": uri} if contexte else {"uris": [uri]})
            fait = "Lecture : %s, sur %s." % (dit, a.get("name") or "Spotify")
        if statut == 403:
            raise ErreurSpotify("Spotify refuse : lancer la lecture a distance demande un compte Premium.")
        if statut not in (200, 202, 204):
            raise ErreurSpotify("Spotify a repondu %s." % (((r or {}).get("error") or {}).get("message") or statut))
        return fait

    def en_cours(self):
        statut, r = self.api("GET", "/me/player/currently-playing")
        item = (r or {}).get("item") if statut == 200 else None
        if not item:
            return None
        artistes = ", ".join(a.get("name", "") for a in item.get("artists") or [])
        return {"id": item.get("id"), "uri": item.get("uri"), "titre": item.get("name"),
                "artistes": artistes, "lecture": bool((r or {}).get("is_playing"))}

    def aimer(self):
        c = self.en_cours()
        if not c or not c.get("id"):
            raise ErreurSpotify("Rien ne joue sur Spotify.")
        statut, _ = self.api("PUT", "/me/tracks", {"ids": c["id"]})
        if statut in (404, 410):
            statut, _ = self.api("PUT", "/me/library", {"uris": c["uri"]})
        if statut not in (200, 201, 204):
            raise ErreurSpotify("Spotify n'a pas pu l'ajouter aux titres likes (%s)." % statut)
        return "Ajoute a tes titres likes : « %s » de %s." % (c["titre"], c["artistes"])


# --------------------------- GOOGLE AGENDA ------------------------------
#
# « Est-ce que tu peux lier Google Agenda pour qu'il puisse poser des
# reperes ? » L'API officielle : un acces « application de bureau » que la
# personne cree dans la console Google Cloud (ID client + code secret), une
# connexion PKCE sur 127.0.0.1:8765, et une seule permission -- creer et
# modifier des evenements (calendar.events). Jarvis en POSE ; il n'en lit ni
# n'en efface aucun.

GOOGLE_PORTEE = "https://www.googleapis.com/auth/calendar.events"
_GOOGLE_COMPTES = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_JETON = "https://oauth2.googleapis.com/token"
_GOOGLE_AGENDA = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def google_url_autorisation(client_id, defi, etat):
    from urllib.parse import urlencode
    return _GOOGLE_COMPTES + "?" + urlencode({
        "client_id": client_id, "redirect_uri": SPOTIFY_RETOUR, "response_type": "code",
        "scope": GOOGLE_PORTEE, "code_challenge": defi, "code_challenge_method": "S256", "state": etat,
        "access_type": "offline", "prompt": "consent"})


def moment_google(texte):
    """« 2026-09-26 » -> toute la journee ; « 2026-09-26T14:00 » -> cette heure-la,
    a l'heure du PC (avec son decalage). Rend (dict pour l'API, datetime, journee)."""
    import datetime
    t = str(texte or "").strip().replace(" ", "T", 1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        d = datetime.date.fromisoformat(t)
        return {"date": d.isoformat()}, d, True
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise ValueError("date illisible : « %s » (AAAA-MM-JJ ou AAAA-MM-JJTHH:MM)" % texte)
    dt = dt.astimezone() if dt.tzinfo is None else dt
    return {"dateTime": dt.isoformat(timespec="seconds")}, dt, False


_JOURS_COURTS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def evenement_google(titre, debut, fin="", duree=60, description="", lieu="", rappel=None):
    """Le corps d'un evenement pour l'API, et la phrase qui le decrit."""
    import datetime
    titre = " ".join(str(titre or "").split())[:200]
    if not titre:
        raise ValueError("il faut un titre")
    d, d_dt, journee = moment_google(debut)
    if fin:
        f, f_dt, f_journee = moment_google(fin)
        if f_journee != journee:
            raise ValueError("debut et fin : tous deux des jours, ou tous deux des heures")
        if journee:
            f = {"date": (f_dt + datetime.timedelta(days=1)).isoformat()}     # la fin est exclue
        elif f_dt <= d_dt:
            raise ValueError("la fin est avant le debut")
    elif journee:
        f = {"date": (d_dt + datetime.timedelta(days=1)).isoformat()}
    else:
        minutes = max(5, min(24 * 60, int(duree or 60)))
        f_dt = d_dt + datetime.timedelta(minutes=minutes)
        f = {"dateTime": f_dt.isoformat(timespec="seconds")}
    corps = {"summary": titre, "start": d, "end": f}
    if description:
        corps["description"] = str(description)[:4000]
    if lieu:
        corps["location"] = str(lieu)[:300]
    if rappel is not None:
        corps["reminders"] = {"useDefault": False,
                              "overrides": [{"method": "popup", "minutes": max(0, min(40320, int(rappel)))}]}
    quand = "%s %s" % (_JOURS_COURTS[d_dt.weekday()], d_dt.strftime("%d/%m"))
    if not journee:
        quand += " a %s" % d_dt.strftime("%H:%M")
    return corps, "« %s », %s" % (titre, quand)


class GoogleAgenda:
    """Le Google Agenda de la personne, par l'API. `http` se remplace dans les tests."""

    def __init__(self, client_id, secret, refresh, http=http_json):
        self.client_id, self.secret, self.refresh, self.http = client_id, secret, refresh, http
        self.acces, self.expire = None, 0.0

    @staticmethod
    def echanger_code(client_id, secret, code, verif, http=http_json):
        from urllib.parse import urlencode
        statut, r = http("POST", _GOOGLE_JETON, {"Content-Type": "application/x-www-form-urlencoded"},
                         urlencode({"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                    "client_secret": secret, "redirect_uri": SPOTIFY_RETOUR,
                                    "code_verifier": verif}).encode("ascii"))
        if statut != 200 or not (r or {}).get("refresh_token"):
            raise ErreurSpotify("Google a refuse la connexion (%s)." % ((r or {}).get("error_description")
                                                                      or (r or {}).get("error") or statut))
        return r

    def jeton(self):
        if self.acces and time.time() < self.expire - 60:
            return self.acces
        from urllib.parse import urlencode
        statut, r = self.http("POST", _GOOGLE_JETON, {"Content-Type": "application/x-www-form-urlencoded"},
                              urlencode({"grant_type": "refresh_token", "refresh_token": self.refresh,
                                         "client_id": self.client_id, "client_secret": self.secret}).encode("ascii"))
        if statut != 200 or not (r or {}).get("access_token"):
            raise ErreurSpotify("La connexion a Google Agenda a expire : reconnecte-le dans Machi Tool "
                                "(Reglages > Jarvis > Google Agenda).")
        self.acces, self.expire = r["access_token"], time.time() + float(r.get("expires_in") or 3600)
        return self.acces

    def poser(self, titre, debut, fin="", duree=60, description="", lieu="", rappel=None):
        corps, dit = evenement_google(titre, debut, fin, duree, description, lieu, rappel)
        for essai in (0, 1):
            statut, r = self.http("POST", _GOOGLE_AGENDA, {"Authorization": "Bearer " + self.jeton()}, corps)
            if statut == 401 and not essai:
                self.acces = None
                continue
            break
        if statut not in (200, 201):
            raise ErreurSpotify("Google Agenda a repondu %s." % (((r or {}).get("error") or {}).get("message") or statut))
        return "Repere pose dans Google Agenda : %s." % dit
