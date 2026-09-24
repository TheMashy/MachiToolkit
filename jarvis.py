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
        for g in self.gabarits:
            fen = x_[-(int(1.6 * len(g)) + 1):]
            if len(fen) < len(g) // 2:
                continue
            meilleur = min(meilleur, distance_gabarit(g, fen))
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

COULEURS = {
    "ecoute":   "#22D3EE",    # il t'entend : cyan qui respire
    "comprend": "#3B82F6",    # il transcrit, sur ce poste : bleu
    "pense":    "#A855F7",    # le compagnon reflechit : violet qui ondule
    "parle":    "#F59E0B",    # il repond a voix haute : ambre
    "fait":     "#22C55E",    # commande faite : vert, un instant
    "erreur":   "#EF4444",    # rate : rouge, un instant
    "apprend":  "#22D3EE",
    "minuteur": "#FFB000",
}


def _hex(h):
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def couleur_etat(etat, t, couleurs=None):
    """(r, v, b), gain pour l'etat donne a l'instant t (en secondes depuis
    son debut). Rend None pour un etat sans couleur."""
    tab = dict(COULEURS)
    tab.update(couleurs or {})
    if etat not in tab:
        return None
    rvb = _hex(tab[etat])
    if etat in ("ecoute", "apprend"):
        gain = 0.78 + 0.22 * math.sin(2 * math.pi * 0.8 * t)
    elif etat == "comprend":
        gain = 0.55 + 0.45 * abs(math.sin(math.pi * 1.4 * t))
    elif etat == "pense":
        # La reflexion : la teinte glisse du violet a l'indigo et revient,
        # l'eclat ondule. C'est l'etat qui dure, il doit se voir vivant.
        k = 0.5 + 0.5 * math.sin(2 * math.pi * 0.35 * t)
        autre = _hex("#6366F1")
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


def dire_duree(secondes):
    s = int(round(secondes))
    h, reste = divmod(s, 3600)
    m, s = divmod(reste, 60)
    morceaux = []
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

def _couleur_nommee(mot):
    """bleue, vertes, violette, blanche -> la couleur."""
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
            "arrete de parler", "stop stop", "c'est bon arrete", "ta gueule", "ferme la"}
_ANNULER = {"annule", "annuler", "laisse tomber", "rien", "non rien", "oublie", "c'est bon",
            "non merci", "rien du tout", "pardon rien", "non", "merci", "merci c'est bon",
            "c'est rien", "fausse alerte"}


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
               r"tu pourrais|pourrais tu)\s+", "", t)
    t = re.sub(r"\s+(?:s'il te plait|stp|merci)$", "", t)
    mots = t.split()

    if t in _SILENCE:
        return {"action": "silence"}
    if t in _ANNULER:
        return {"action": "annuler"}

    for r in raccourcis or ():
        dit = normaliser(r.get("dit", ""))
        if dit and (t == dit or t.startswith(dit + " ")) and r.get("ouvre"):
            return {"action": "ouvrir", "cible": str(r["ouvre"]), "nom": r.get("dit", "")}

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


def pour_la_voix(texte, plafond=1200):
    """Le texte d'une reponse, tel qu'on peut le lire a voix haute : sans
    markdown, sans liens, sans emojis, et coupe a une fin de phrase."""
    t = str(texte or "")
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", "le lien", t)
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
    "fr_FR-siwis-medium": {"nom": "Siwis -- francais, femme", "hf": "fr/fr_FR/siwis/medium/",
                           "github": "voice-fr-siwis-medium"},
    "en_GB-alan-medium":  {"nom": "Alan -- anglais britannique, homme (lit le francais avec un accent)",
                           "hf": "en/en_GB/alan/medium/"},
}
VOIX_DEFAUT = "fr_FR-tom-medium"
VOIX_SECOURS = "fr_FR-gilles-low"       # aussi publiee sur GitHub, si Hugging Face ne repond pas


def commande_piper(exe, modele, lenteur=1.08, silence=0.3):
    """La ligne de commande : son brut 16 bits mono sur la sortie standard,
    que l'on joue au fur et a mesure (la premiere phrase sonne avant que la
    derniere soit calculee)."""
    return [exe, "--model", modele, "--output_raw",
            "--length_scale", "%.2f" % max(0.6, min(1.6, float(lenteur))),
            "--sentence_silence", "%.2f" % max(0.0, min(1.5, float(silence)))]


def frequence_du_modele(chemin_json, defaut=22050):
    try:
        with open(chemin_json, encoding="utf-8") as f:
            return int(json.load(f)["audio"]["sample_rate"])
    except Exception:
        return defaut


def texte_pour_piper(texte):
    """Une seule ligne (piper lit ligne par ligne) et des nombres qui se disent."""
    t = pour_la_voix(texte)
    t = re.sub(r"(\d{1,2})\s*h\s*(\d{2})\b", r"\1 heures \2", t)
    return t.replace("\n", " ").strip()


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


def micro_windows(nom=""):
    """Les trames du micro, 1280 echantillons int16 a 16 kHz. WASAPI convertit
    lui-meme la frequence (soundcard ouvre le flux avec AUTOCONVERTPCM)."""
    import numpy as np
    import soundcard as sc
    micro = None
    if nom:
        try:
            micro = sc.get_microphone(nom)
        except Exception:
            micro = None
    micro = micro or sc.default_microphone()
    with micro.recorder(samplerate=FREQ, channels=1, blocksize=TRAME) as r:
        while True:
            b = r.record(numframes=TRAME)
            mono = b[:, 0] if getattr(b, "ndim", 1) > 1 else b
            yield (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)


class Oreille:
    """La machine a etats de l'oreille, sans socket ni micro : testable.

    `sortie(evenement)` recoit ce qui doit partir vers Machi Tool ;
    `jouer(genre)` joue un son."""

    def __init__(self, empreintes, sortie, jouer_son=None):
        self.e = empreintes
        self.sortie = sortie
        self.jouer = jouer_son or (lambda g: None)
        self.reglages = {"gabarits": [], "sensibilite": 0.5, "hey": True, "son": True}
        self.det = Detecteur(empreintes)
        self.etat = "veille"
        self.phrase = None
        self.appris = None
        self.niveau_vu = 0.0

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
        elif cmd == "annuler":
            self.phrase, self.appris, self.etat = None, None, "veille"
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
        if ev is not None:
            if self.reglages.get("son", True):
                self.jouer("eveil")
            avant = self.det.son_d_avant()
            self.phrase = Phrase(self.det.parle, avant=avant[:-TRAME] if len(avant) > TRAME else None)
            # La trame courante est dans « avant » : on ne la compte pas deux fois,
            # mais elle ne fait pas partie de la fenetre d'apres-carillon non plus.
            self.phrase.morceaux.append(np.asarray(x, dtype=np.int16))
            self.etat = "phrase"
            self.sortie({"evt": "reveil", "par": ev[0], "score": round(float(ev[1]), 4)})
            return
        if self.etat == "phrase" and self.phrase is not None:
            fin = self.phrase.trame(x, rms)
            if fin == "fini":
                wav = self.phrase.wav()
                self.phrase, self.etat = None, "veille"
                self.sortie({"evt": "phrase", "wav": base64.b64encode(wav).decode("ascii")})
            elif fin == "vide":
                self.phrase, self.etat = None, "veille"
                self.sortie({"evt": "vide"})
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
            self.sortie({"evt": "niveau", "db": round(db, 1), "etat": self.etat})


def oreille_enfant(port, secret, dossier, source=None, jouer_son=None):
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

    try:
        oreille = Oreille(Empreintes(dossier), sortie, jouer_son or jouer)
    except Exception as e:
        sortie({"evt": "erreur", "message": "modeles illisibles : %s" % str(e)[:160]})
        return
    while vivant.is_set():
        try:
            flux = source() if source else micro_windows()
            sortie({"evt": "pret"})
            for x in flux:
                while True:
                    try:
                        c = commandes.get_nowait()
                    except queue.Empty:
                        break
                    oreille.commande(c)
                if not vivant.is_set():
                    break
                oreille.trame(x)
            if source:
                break
        except Exception as e:
            sortie({"evt": "erreur", "message": "micro : %s" % str(e)[:160]})
            for _ in range(30):
                if not vivant.is_set():
                    break
                time.sleep(0.1)
    try:
        s.close()
    except Exception:
        pass
