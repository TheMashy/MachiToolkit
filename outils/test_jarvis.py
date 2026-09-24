# -*- coding: utf-8 -*-
"""
JARVIS : ON L'APPELLE, IL S'ALLUME, IL FAIT OU IL REPOND.

Demande : « detecte aussi une entree rapide de commande lorsque le micro detecte
"jarvis" ou "hey jarvis !" ; l'utilisateur pourra entrer plein de commandes ou
juste parler au chat bot ; lorsque jarvis s'allume il faut faire un petit son et
mettre les leds d'une couleur en fonction de sa reflexion ; jarvis peut repondre
en tts » -- puis « fais-le parler comme Jarvis, une vraie bonne voix, en local ».

Ce qui est tenu ici :
  - les commandes sont reconnues, et une phrase qui n'en est pas une va au
    compagnon -- surtout une phrase qui parle de soi (« je me sens eteint »
    n'eteint pas la lumiere) ;
  - le mot d'eveil est retire de la phrase ; « Jarvis. » tout seul attend la suite ;
  - la fin de phrase : « Jarvis stop » dit d'une traite n'est pas perdu dans le
    carillon, et le carillon seul n'est pas pris pour une phrase ;
  - AVANT le mot d'eveil, l'oreille ne laisse sortir ni son ni texte ;
  - ce qui est dit n'est jamais journalise ; le son ne touche jamais le disque ;
  - la guirlande a une couleur par etat, et Jarvis passe devant tout ;
  - la voix : Piper telecharge une fois, avec une voix de secours, et la voix
    de Windows si rien n'est la ;
  - aucun crochet clavier.

Les tests ACOUSTIQUES (le vrai detecteur sur de vraies voix de synthese) tournent
quand les modeles d'openWakeWord et espeak-ng sont la (la CI les installe) :

    JARVIS_MODELES=<dossier des 3 .onnx> python outils/test_jarvis.py
"""
import base64
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import wave
import zipfile
from contextlib import redirect_stdout

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

try:
    import numpy as np
    NUMPY = True
except Exception:
    NUMPY = False

import jarvis as J  # noqa: E402

MODELES = os.environ.get("JARVIS_MODELES", "")
ESPEAK = shutil.which("espeak-ng")
try:
    import onnxruntime  # noqa: F401
    ONNX = True
except Exception:
    ONNX = False
ACOUSTIQUE = bool(NUMPY and ONNX and ESPEAK and MODELES and
                  all(os.path.isfile(os.path.join(MODELES, n)) for n in J.MODELES))


# ======================================================================
#  CE QUE LA PERSONNE A DIT
# ======================================================================

class Commandes(unittest.TestCase):
    def action(self, texte):
        a = J.comprendre(texte)
        return a and a["action"]

    def test_la_lumiere(self):
        self.assertEqual(self.action("Allume la lumière."), "lumiere_on")
        self.assertEqual(self.action("éteins la lumière"), "lumiere_off")
        self.assertEqual(self.action("Éteins les LEDs !"), "lumiere_off")
        a = J.comprendre("mets la lumière en bleu")
        self.assertEqual((a["action"], a["couleur"]), ("lumiere_couleur", J.COULEURS_NOMMEES["bleu"]))
        self.assertEqual(J.comprendre("Lumière bleue.")["nom"], "bleu")
        self.assertEqual(J.comprendre("passe la guirlande en violette")["nom"], "violet")
        self.assertEqual(J.comprendre("mets la lumière en blanche")["nom"], "blanc")
        self.assertEqual(self.action("Remets la lumière normale"), "lumiere_normale")
        self.assertEqual(self.action("lumière normale"), "lumiere_normale")

    def test_les_modes(self):
        self.assertEqual(J.comprendre("mode écran")["mode"], "ecran")
        self.assertEqual(J.comprendre("passe en mode musique")["mode"], "son")
        self.assertEqual(J.comprendre("mets la lumière en mode applications")["mode"], "applications")

    def test_minuteurs_et_rappels(self):
        a = J.comprendre("Mets un minuteur de 10 minutes.")
        self.assertEqual((a["action"], a["secondes"]), ("minuteur", 600))
        a = J.comprendre("minuteur de dix-sept minutes")
        self.assertEqual(a["secondes"], 17 * 60)
        a = J.comprendre("rappelle-moi dans vingt minutes de sortir le linge")
        self.assertEqual((a["secondes"], a["quoi"]), (1200, "sortir le linge"))
        a = J.comprendre("Rappelle-moi de prendre mes médicaments dans une heure et demie")
        self.assertEqual((a["secondes"], a["quoi"]), (5400, "prendre mes medicaments"))
        a = J.comprendre("timer 30 secondes")
        self.assertEqual(a["secondes"], 30)
        self.assertEqual(J.comprendre("mets un minuteur d'un quart d'heure")["secondes"], 900)
        self.assertEqual(self.action("annule les minuteurs"), "minuteurs_annuler")

    def test_heure_date_et_le_reste(self):
        self.assertEqual(self.action("Quelle heure est-il ?"), "heure")
        self.assertEqual(self.action("il est quelle heure"), "heure")
        self.assertEqual(self.action("On est quel jour ?"), "date")
        self.assertEqual(self.action("Ouvre BrainDebugger."), "ouvrir_site")
        self.assertEqual(self.action("ouvre Machi Tool"), "ouvrir_panneau")
        self.assertEqual(self.action("synchronise"), "synchro")
        self.assertEqual(self.action("Stop."), "silence")
        self.assertEqual(self.action("tais-toi"), "silence")
        self.assertEqual(self.action("Laisse tomber."), "annuler")
        self.assertEqual(self.action("arrête d'écouter"), "dormir")
        self.assertEqual(self.action("s'il te plaît, quelle heure est-il"), "heure")

    def test_ce_qui_parle_de_soi_va_au_compagnon(self):
        """Le vrai danger : qu'une phrase dite AU COMPAGNON soit prise pour une
        commande, et qu'il ne l'entende jamais."""
        for phrase in (
                "Je me sens éteint, coupé de tout.",
                "J'ai éteint la lumière et je suis resté dans le noir une heure",
                "je vois tout en bleu en ce moment, c'est bizarre",
                "rouge",
                "je suis en mode survie depuis ce matin",
                "j'ai l'impression que le temps s'arrête",
                "arrête, je n'en peux plus de cette journée",
                "je voudrais juste que ça s'arrête",
                "est-ce que tu peux me dire pourquoi je n'arrive pas à dormir",
                "rappelle-moi pourquoi je fais tout ça",
                "j'ai mis un minuteur sur mon téléphone mais je l'ai ignoré",
                # Commence comme une commande, mais c'est une confidence : une
                # commande est une phrase COURTE.
                "quelle heure est-il, je me le demande tout le temps depuis que "
                "je ne dors plus et que les journées se mélangent"):
            self.assertIsNone(J.comprendre(phrase), phrase)

    def test_raccourcis_a_soi(self):
        r = [{"dit": "ouvre Spotify", "ouvre": "spotify:"}]
        a = J.comprendre("Ouvre Spotify.", r)
        self.assertEqual((a["action"], a["cible"]), ("ouvrir", "spotify:"))
        self.assertIsNone(J.comprendre("ouvre spotifyyy", r))


class MotEveil(unittest.TestCase):
    def test_on_coupe_jusqu_au_mot(self):
        self.assertEqual(J.retirer_mot_eveil("Jarvis, allume la lumière."), "allume la lumière.")
        self.assertEqual(J.retirer_mot_eveil("Hey Jarvis ! Quelle heure est-il ?"), "Quelle heure est-il ?")
        self.assertEqual(J.retirer_mot_eveil("oui oui. Djarvis mets un minuteur"), "mets un minuteur")
        self.assertEqual(J.retirer_mot_eveil("J'arvis, stop"), "stop")
        self.assertEqual(J.retirer_mot_eveil("Jarvice, stop"), "stop")
        self.assertEqual(J.retirer_mot_eveil("Jarvis."), "")

    def test_sans_mot_on_ne_touche_a_rien(self):
        self.assertEqual(J.retirer_mot_eveil("allume la lumière"), "allume la lumière")
        # Le mot trop loin : c'est une phrase qui parle de Jarvis, pas un appel.
        loin = "je regardais un film hier soir avec mon frere et Jarvis parlait"
        self.assertEqual(J.retirer_mot_eveil(loin), loin)


class Nombres(unittest.TestCase):
    def test_nombres(self):
        for mots, v in ((["vingt", "et", "une"], 21), (["dix-sept"], 17), (["quarante-cinq"], 45),
                        (["12"], 12), (["une"], 1), (["soixante"], 60), (["trente", "deux"], 32)):
            self.assertEqual(J.nombre_fr(mots)[0], v, mots)
        self.assertEqual(J.nombre_fr(["pomme"]), (None, 0))

    def test_durees(self):
        self.assertEqual(J.duree_fr("10 minutes"), 600)
        self.assertEqual(J.duree_fr("1 h 30"), 3600)      # « 30 » sans unite ne compte pas
        self.assertEqual(J.duree_fr("une heure et demie"), 5400)
        self.assertEqual(J.duree_fr("deux heures et 5 minutes"), 7500)
        self.assertEqual(J.duree_fr("une demi-heure"), 1800)
        self.assertIsNone(J.duree_fr("bientot"))
        self.assertEqual(J.dire_duree(5400), "1 heure et 30 minutes")
        self.assertEqual(J.dire_duree(45), "45 secondes")


class PourLaVoix(unittest.TestCase):
    def test_nettoyage(self):
        t = J.pour_la_voix("**Bien sûr.** Voici :\n- un\n- deux\n[le lien](https://x.y) 🙂 https://a.b/c")
        self.assertNotIn("*", t)
        self.assertNotIn("http", t)
        self.assertNotIn("🙂", t)
        self.assertIn("le lien", t)

    def test_plafond_a_une_fin_de_phrase(self):
        t = J.pour_la_voix("Une phrase. " * 300, plafond=200)
        self.assertLessEqual(len(t), 200)
        self.assertTrue(t.endswith("."))

    def test_piper_une_seule_ligne(self):
        self.assertEqual(J.texte_pour_piper("Il est 14h05.\nVoilà."), "Il est 14 heures 05. Voilà.")


# ======================================================================
#  LES SONS ET LES COULEURS
# ======================================================================

class SonsEtCouleurs(unittest.TestCase):
    def test_les_sons_sont_des_wav_courts(self):
        for genre in J.SONS:
            with wave.open(io.BytesIO(J.carillon(genre))) as w:
                duree = w.getnframes() / w.getframerate()
            self.assertAlmostEqual(duree, J.duree_son(genre), delta=0.01)
        # Le carillon de l'eveil est COURT : l'oreille ne le prend pas pour
        # de la parole (voir Phrase), et il ne doit pas masquer le debut.
        self.assertLess(J.duree_son("eveil"), 0.2)

    def test_une_couleur_par_etat(self):
        vus = set()
        for etat in ("ecoute", "comprend", "pense", "parle", "fait", "erreur"):
            for t in (0.0, 0.3, 1.1, 2.7):
                rvb, gain = J.couleur_etat(etat, t)
                self.assertTrue(0.05 <= gain <= 1.0)
                self.assertTrue(all(0 <= c <= 255 for c in rvb))
            vus.add(J.COULEURS[etat])
        self.assertEqual(len(vus), 6, "chaque etat se distingue a l'oeil")
        self.assertIsNone(J.couleur_etat("inconnu", 0))
        self.assertEqual(J.couleur_etat("fait", 0, {"fait": "#010203"})[0], (1.0, 2.0, 3.0))

    def test_la_reflexion_ondule(self):
        """« En fonction de sa reflexion » : pendant que le compagnon pense,
        la couleur bouge -- sinon on ne distingue pas « il pense » de « fige »."""
        couleurs = {tuple(round(c) for c in J.couleur_etat("pense", t / 4)[0]) for t in range(12)}
        self.assertGreater(len(couleurs), 3)


# ======================================================================
#  LA FIN DE PHRASE
# ======================================================================

@unittest.skipUnless(NUMPY, "numpy absent")
class FinDePhrase(unittest.TestCase):
    PARLE = staticmethod(lambda rms: rms > 300)

    def jouer(self, sequence, **kw):
        """sequence : chaine de « p » (parole) et « . » (silence), 80 ms chacun."""
        ph = J.Phrase(self.PARLE, **kw)
        for i, c in enumerate(sequence):
            fin = ph.trame(np.zeros(J.TRAME, np.int16), 2000.0 if c == "p" else 30.0)
            if fin:
                return fin, round((i + 1) * J.TRAME_S, 2)
        return None, None

    def test_une_phrase_normale(self):
        fin, t = self.jouer("......" + "p" * 15 + "." * 30)
        self.assertEqual(fin, "fini")
        self.assertAlmostEqual(t, (6 + 15 + 12) * 0.08, delta=0.09)   # 0,9 s de silence

    def test_jarvis_stop_dit_d_une_traite(self):
        """« stop » tombe dans les 300 ms du carillon : il compte quand meme."""
        fin, _ = self.jouer("ppp" + "." * 40)
        self.assertEqual(fin, "fini")

    def test_le_carillon_seul_n_est_pas_une_phrase(self):
        fin, t = self.jouer("p" + "." * 80)
        self.assertEqual(fin, "vide")
        self.assertAlmostEqual(t, 5.0, delta=0.09)

    def test_on_laisse_le_temps_de_commencer_apres_le_carillon(self):
        """« Jarvis » ... (carillon) ... « allume la lumiere » : un demi-silence
        apres le carillon ne ferme pas la phrase."""
        fin, t = self.jouer("pp" + "." * 12 + "p" * 10 + "." * 30)
        self.assertEqual(fin, "fini")
        self.assertGreater(t, (2 + 12 + 10) * 0.08)

    def test_une_phrase_sans_fin_s_arrete(self):
        fin, t = self.jouer("p" * 400)
        self.assertEqual(fin, "fini")
        self.assertAlmostEqual(t, 15.0, delta=0.09)

    def test_le_wav_contient_le_debut(self):
        avant = np.full(J.TRAME * 3, 7, np.int16)
        ph = J.Phrase(self.PARLE, avant=avant)
        ph.trame(np.full(J.TRAME, 9, np.int16), 30.0)
        with wave.open(io.BytesIO(ph.wav())) as w:
            self.assertEqual(w.getframerate(), 16000)
            self.assertEqual(w.getnframes(), J.TRAME * 4)


# ======================================================================
#  L'OREILLE, SANS MICRO NI MODELE
# ======================================================================

class FaussesEmpreintes:
    """Un « hey jarvis » la ou la trame porte le marqueur 4242."""
    hey_m = True

    def __init__(self):
        self.rng = np.random.default_rng(3)

    def trame(self, x):
        return (0.95 if int(x[0]) == 4242 else 0.0), self.rng.normal(size=96).astype(np.float32)


def trame(parole=False, marque=False):
    x = (np.sin(np.arange(J.TRAME) * 0.3) * (3000 if parole else 20)).astype(np.int16)
    if marque:
        x[0] = 4242
    return x


@unittest.skipUnless(NUMPY, "numpy absent")
class OreilleSansMicro(unittest.TestCase):
    def setUp(self):
        self.sorties, self.sons = [], []
        self.o = J.Oreille(FaussesEmpreintes(), self.sorties.append, self.sons.append)
        self.o.niveau_vu = float("inf")          # pas de niveaux : on regarde le reste

    def evts(self):
        return [e["evt"] for e in self.sorties]

    def test_avant_l_eveil_rien_ne_sort(self):
        """Le coeur de la promesse : on parle dans la piece, personne n'a
        appele Jarvis -- aucun son, aucun texte ne quitte l'oreille."""
        for i in range(200):
            self.o.trame(trame(parole=(i // 10) % 2 == 0))
        self.assertEqual(self.sorties, [])

    def test_eveil_carillon_phrase(self):
        for _ in range(15):
            self.o.trame(trame())
        self.o.trame(trame(parole=True, marque=True))
        self.assertEqual(self.evts(), ["reveil"])
        self.assertEqual(self.sons, ["eveil"])
        for _ in range(8):
            self.o.trame(trame())
        for _ in range(12):
            self.o.trame(trame(parole=True))
        for _ in range(20):
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["reveil", "phrase"])
        with wave.open(io.BytesIO(base64.b64decode(self.sorties[1]["wav"]))) as w:
            # Les deux secondes d'avant l'eveil sont la : « Jarvis » y est, et
            # la transcription le retire.
            self.assertGreater(w.getnframes() / 16000.0, 2.5)

    def test_sans_son_si_on_l_a_coupe(self):
        self.o.commande({"cmd": "config", "son": False})
        self.o.trame(trame(parole=True, marque=True))
        self.assertEqual(self.sons, [])

    def test_hey_coupe(self):
        self.o.commande({"cmd": "config", "hey": False})
        for _ in range(10):
            self.o.trame(trame(parole=True, marque=True))
        self.assertEqual(self.sorties, [])

    def test_la_suite_sans_mot_d_eveil(self):
        self.o.commande({"cmd": "ecouter", "attente": 2.0})
        for _ in range(40):
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["vide"])

    def test_apprendre_rend_une_empreinte_et_pas_de_son(self):
        self.o.commande({"cmd": "apprendre"})
        self.assertEqual(self.sons, [], "un bip entrerait dans l'empreinte")
        for _ in range(5):
            self.o.trame(trame())
        for _ in range(7):
            self.o.trame(trame(parole=True))
        for _ in range(10):
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["gabarit"])
        g = self.sorties[0]["vecteurs"]
        self.assertTrue(J.GABARIT_MIN <= len(g) <= J.GABARIT_MAX)
        self.assertEqual(len(g[0]), 96)
        self.assertNotIn("wav", self.sorties[0])

    def test_apprendre_sans_rien_dire(self):
        self.o.commande({"cmd": "apprendre"})
        for _ in range(60):
            self.o.trame(trame())
        self.assertEqual(self.sorties[0].get("erreur"), "rien entendu")


class Alignement(unittest.TestCase):
    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_un_mot_contre_lui_meme(self):
        g = J.normer(np.random.default_rng(1).normal(size=(8, 96)))
        self.assertAlmostEqual(J.distance_gabarit(g, g), 0.0, places=5)
        # Etire dans le temps (dit plus lentement) : toujours tres proche.
        lent = np.repeat(g, 2, axis=0)
        self.assertLess(J.distance_gabarit(g, lent), 0.01)
        autre = J.normer(np.random.default_rng(2).normal(size=(12, 96)))
        self.assertGreater(J.distance_gabarit(g, autre), 0.5)

    def test_seuils(self):
        self.assertAlmostEqual(J.seuil_gabarit(0.5), 0.05)
        self.assertLess(J.seuil_gabarit(0), J.seuil_gabarit(1))


class Protocole(unittest.TestCase):
    def test_aller_retour(self):
        a, b = socket.socketpair()
        J.envoyer(a, {"evt": "reveil", "score": 0.9})
        J.envoyer(a, None)
        self.assertEqual(J.recevoir(b), {"evt": "reveil", "score": 0.9})
        self.assertIsNone(J.recevoir(b))
        a.close()
        b.close()


# ======================================================================
#  CE QUE CE CODE NE FAIT PAS
# ======================================================================

class CeQuiNeSeFaitPas(unittest.TestCase):
    def lire(self, nom):
        with open(os.path.join(RACINE, nom), encoding="utf-8") as f:
            return f.read()

    def test_aucun_crochet_clavier(self):
        for nom in ("jarvis.py", "machi_tool.py"):
            src = self.lire(nom).lower()
            for interdit in ("setwindowshookex", "pynput", "import keyboard", "wh_keyboard",
                             "getasynckeystate", "registerhotkey"):
                self.assertNotIn(interdit, src, "%s : %s" % (nom, interdit))

    def test_l_oreille_n_ecrit_rien_sur_le_disque(self):
        src = self.lire("jarvis.py")
        # `wave.open(tampon, "wb")` ecrit dans la memoire ; `open(...)` tout court
        # ecrirait un fichier.
        self.assertNotRegex(src, r"(?<![\w.])open\([^)]*['\"][wa]b?['\"]")
        self.assertNotIn("tofile(", src)


# ======================================================================
#  DANS MACHI TOOL
# ======================================================================

def charger_module(dossier):
    os.environ["LOCALAPPDATA"] = dossier
    spec = importlib.util.spec_from_file_location("mt_jarvis", os.path.join(RACINE, "machi_tool.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FausseReponse(io.BytesIO):
    def __init__(self, octets):
        super().__init__(octets)
        self.headers = {"Content-Length": str(len(octets))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class DansMachiTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.m = charger_module(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        m = self.m
        m.DOSSIER = os.path.join(self.tmp, "machi-%d" % id(self))
        os.makedirs(m.DOSSIER)
        m.CFG.clear()
        m.CFG.update(json.loads(json.dumps(m.CONFIG_DEFAUT)))
        m.CFG.update(pont_site="https://bd.exemple", pont_cle="CLE", jarvis_voix=False)
        m.ETAT["forcage"] = None
        m.JARVIS.update(led=None, led_fin=0.0, minuteurs=[], etat="attente")
        self.dit, self.envoye = [], []
        m.JARVIS_CROCHETS.clear()
        m.JARVIS_CROCHETS["notifier"] = lambda t, x: self.dit.append(x)
        self._origines = {k: getattr(m, k) for k in ("transcrire", "etat_dictee", "parler_au_compagnon",
                                                      "jouer_son", "sauver_config")}
        m.jouer_son = lambda g: None
        m.sauver_config = lambda cfg: True
        m.etat_dictee = lambda: {"etat": "pret", "progres": 1.0}

    def tearDown(self):
        for k, v in self._origines.items():
            setattr(self.m, k, v)

    def test_jarvis_est_eteint_par_defaut(self):
        self.assertFalse(self.m.CONFIG_DEFAUT["jarvis_actif"],
                         "un micro ouvert en permanence se decide, il ne s'impose pas")

    def phrase(self, texte):
        self.m.transcrire = lambda octets: texte
        self.m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), self.m.CFG)

    def test_une_commande_reste_ici(self):
        vus = []
        self.m.parler_au_compagnon = lambda t, cfg: vus.append(t)
        self.phrase("Jarvis, mets la lumière en rouge.")
        self.assertEqual(vus, [])
        self.assertEqual(self.m.ETAT["forcage"]["couleur"], (255, 26, 26))
        self.assertEqual(self.m.JARVIS["led"], "fait")

    def test_le_reste_va_au_compagnon_sans_le_mot(self):
        vus = []
        self.m.parler_au_compagnon = lambda t, cfg: vus.append(t)
        self.phrase("Hey Jarvis, je rentre du sport et je suis crevé.")
        self.assertEqual(vus, ["je rentre du sport et je suis crevé."])

    def test_jarvis_tout_seul_attend_la_suite(self):
        self.phrase("Jarvis.")
        self.assertEqual(self.dit, ["Oui ?"])

    def test_ce_qui_est_dit_n_est_jamais_journalise(self):
        journal = io.StringIO()
        secret = "mon secret intime numero 7"
        self.m.parler_au_compagnon = self._origines["parler_au_compagnon"]
        with mock_urlopen(self.m, {"texte": "Je t'entends."}):
            with redirect_stdout(journal):
                self.phrase("Jarvis, " + secret)
                self.phrase("Jarvis, rappelle-moi dans 10 minutes de " + secret)
        for m_ in self.m.JARVIS["minuteurs"]:
            m_["minuteur"].cancel()
        self.assertNotIn("secret", journal.getvalue())
        self.assertIn("commande minuteur", journal.getvalue())

    def test_le_compagnon_recoit_la_phrase_par_la_cle(self):
        self.m.parler_au_compagnon = self._origines["parler_au_compagnon"]
        with mock_urlopen(self.m, {"texte": "Bonne soirée."}) as req:
            self.phrase("Jarvis, bonne nuit")
        r = req[0]
        self.assertEqual(r.full_url, "https://bd.exemple/api/machitool/parler")
        self.assertEqual(r.get_header("Authorization"), "Bearer CLE")
        self.assertRegex(r.get_header("X-fuseau"), r"^(UTC|Etc/GMT[+-]\d+)$")
        self.assertEqual(json.loads(r.data.decode()), {"texte": "bonne nuit"})
        self.assertEqual(self.dit, ["Bonne soirée."])       # sans voix : une notification

    def test_sans_cle_on_le_dit(self):
        self.m.CFG["pont_cle"] = ""
        self.m.parler_au_compagnon = self._origines["parler_au_compagnon"]
        self.phrase("Jarvis, raconte-moi une histoire")
        self.assertEqual(self.m.JARVIS["etat"], "erreur")
        self.assertIn("clé", self.m.JARVIS["message"])

    def test_l_heure_et_les_minuteurs(self):
        t = time.mktime((2026, 9, 24, 14, 5, 0, 0, 0, -1))
        self.assertEqual(self.m.executer_commande({"action": "heure"}, self.m.CFG, t), "Il est 14 heures 05.")
        self.assertEqual(self.m.executer_commande({"action": "date"}, self.m.CFG, t),
                         "Nous sommes le jeudi 24 septembre.")
        dit = self.m.executer_commande({"action": "minuteur", "secondes": 600, "quoi": ""}, self.m.CFG)
        self.assertEqual(dit, "Minuteur de 10 minutes, lancé.")
        self.assertEqual(len(self.m.JARVIS["minuteurs"]), 1)
        self.assertEqual(self.m.executer_commande({"action": "minuteurs_annuler"}, self.m.CFG), "C'est annulé.")
        self.assertEqual(self.m.JARVIS["minuteurs"], [])

    def test_la_guirlande_passe_devant_puis_rend_la_main(self):
        m = self.m
        self.assertIsNone(m.couleur_jarvis(m.CFG))
        m.poser_led("pense")
        rvb, gain = m.couleur_jarvis(m.CFG)
        self.assertTrue(gain > 0)
        m.CFG["jarvis_leds"] = False
        self.assertIsNone(m.couleur_jarvis(m.CFG), "decoche : la guirlande n'en sait rien")
        m.CFG["jarvis_leds"] = True
        m.poser_led("fait", 1.0)
        self.assertIsNotNone(m.couleur_jarvis(m.CFG))
        self.assertIsNone(m.couleur_jarvis(m.CFG, maintenant=time.time() + 2))
        self.assertIsNone(m.JARVIS["led"])

    def test_la_boucle_des_leds_consulte_jarvis_avant_le_reste(self):
        with open(os.path.join(RACINE, "machi_tool.py"), encoding="utf-8") as f:
            src = f.read()
        corps = src[src.index("async def une_session"):src.index("async def superviseur")]
        self.assertLess(corps.index("couleur_jarvis(cfg)"), corps.index('if mode == "son":'))
        self.assertIn('inactif = (mode != "jarvis"', corps)

    def test_les_modeles_du_mot_d_eveil(self):
        m = self.m
        demandes = []

        def ouvrir(url):
            demandes.append(url)
            return FausseReponse(b"onnx" * 100)
        self.assertTrue(m.preparer_jarvis(ouvrir))
        self.assertTrue(m.modeles_jarvis_prets())
        self.assertEqual(len(demandes), 3)
        self.assertTrue(all(u.startswith(J.MODELES_SOURCE) for u in demandes))

    def test_la_voix_piper_et_son_secours(self):
        """Hugging Face ne repond pas : la voix de secours vient de GitHub."""
        m = self.m
        m.CFG["jarvis_voix_modele"] = "fr_FR-tom-medium"
        zip_ = io.BytesIO()
        with zipfile.ZipFile(zip_, "w") as z:
            z.writestr("piper/piper.exe" if os.name == "nt" else "piper/piper", b"exe")
        tar_ = io.BytesIO()
        with tarfile.open(fileobj=tar_, mode="w:gz") as t:
            for nom, contenu in (("fr-gilles-low.onnx", b"modele"),
                                 ("fr-gilles-low.onnx.json", b'{"audio": {"sample_rate": 16000}}')):
                info = tarfile.TarInfo(nom)
                info.size = len(contenu)
                t.addfile(info, io.BytesIO(contenu))

        def ouvrir(url):
            if url == J.PIPER_MOTEUR:
                return FausseReponse(zip_.getvalue())
            if "huggingface" in url:
                raise OSError("injoignable")
            if url.endswith("voice-fr-gilles-low.tar.gz"):
                return FausseReponse(tar_.getvalue())
            raise OSError("inattendu : " + url)
        m.PIPER["etat"] = "absent"
        self.assertTrue(m.preparer_piper(m.CFG, ouvrir))
        exe, modele, freq = m.piper_pret(m.CFG)
        self.assertTrue(modele.endswith("fr_FR-gilles-low.onnx"))
        self.assertEqual(freq, 16000)
        self.assertIn("secours", m.PIPER["message"])
        m.CFG["jarvis_voix_modele"] = "windows"
        self.assertIsNone(m.piper_pret(m.CFG))

    def test_la_commande_piper(self):
        c = J.commande_piper("piper.exe", "voix.onnx", 1.08)
        self.assertEqual(c[:4], ["piper.exe", "--model", "voix.onnx", "--output_raw"])
        self.assertIn("1.08", c)
        self.assertIn("1.60", J.commande_piper("p", "v", 9))


class mock_urlopen:
    def __init__(self, m, reponse):
        self.m, self.reponse, self.requetes = m, reponse, []

    def __enter__(self):
        self.avant = self.m.urllib.request.urlopen

        def faux(req, timeout=None, context=None):
            self.requetes.append(req)
            return FausseReponse(json.dumps(self.reponse).encode())
        self.m.urllib.request.urlopen = faux
        return self.requetes

    def __exit__(self, *a):
        self.m.urllib.request.urlopen = self.avant
        return False


# ======================================================================
#  POUR DE VRAI : LE DETECTEUR SUR DES VOIX DE SYNTHESE
# ======================================================================

def dire(texte, voix="fr+m3", vitesse=150, hauteur=50):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        chemin = f.name
    try:
        subprocess.run([ESPEAK, "-v", voix, "-s", str(vitesse), "-p", str(hauteur), "-w", chemin, texte],
                       check=True, capture_output=True)
        with wave.open(chemin) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64)
            fr = w.getframerate()
    finally:
        os.remove(chemin)
    idx = np.arange(0, len(a) * 16000 // fr) * fr / 16000
    return np.interp(idx, np.arange(len(a)), a)


def flux(*morceaux, graine=1):
    """Du bruit de piece, les phrases, du bruit : en trames de 80 ms."""
    rng = np.random.default_rng(graine)
    parties = [np.zeros(16000)]
    for m_ in morceaux:
        parties += [m_, np.zeros(12000)]
    a = np.concatenate(parties)
    a = np.clip(a + rng.normal(0, 60, len(a)), -32768, 32767).astype(np.int16)
    return [a[i:i + J.TRAME] for i in range(0, len(a) - J.TRAME + 1, J.TRAME)]


@unittest.skipUnless(ACOUSTIQUE, "modeles d'openWakeWord ou espeak-ng absents")
class PourDeVrai(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.emp = J.Empreintes(MODELES)

    def oreille(self, gabarits=()):
        sorties = []
        o = J.Oreille(J.Empreintes(MODELES), sorties.append, lambda g: None)
        o.niveau_vu = float("inf")
        o.configurer({"gabarits": list(gabarits)})
        return o, sorties

    def reveils(self, o, sorties, son):
        for x in flux(son):
            o.trame(x)
        return [e for e in sorties if e["evt"] == "reveil"]

    def test_hey_jarvis_a_l_anglaise(self):
        o, s = self.oreille()
        r = self.reveils(o, s, dire("hey jarvis", voix="en"))
        self.assertEqual([e["par"] for e in r], ["hey"])

    def test_une_conversation_ne_reveille_pas(self):
        o, s = self.oreille()
        self.assertEqual(self.reveils(o, s, dire("bonjour, comment ça va aujourd'hui ?")), [])

    def test_apprendre_puis_reconnaitre_jarvis_tout_seul(self):
        """La voix apprise : trois fois « Jarvis », a la francaise -- ce que le
        modele anglais ne reconnait pas du tout."""
        o, sorties = self.oreille()
        gabarits = []
        for vitesse, hauteur in ((130, 45), (150, 50), (170, 55)):
            sorties.clear()
            for x in flux(np.zeros(1))[:10]:
                o.trame(x)
            o.commande({"cmd": "apprendre"})
            for x in flux(dire("Jarvis", vitesse=vitesse, hauteur=hauteur))[8:]:
                o.trame(x)
                if any(e["evt"] == "gabarit" for e in sorties):
                    break
            ev = [e for e in sorties if e["evt"] == "gabarit"][0]
            self.assertIn("vecteurs", ev, ev)
            gabarits.append(ev["vecteurs"])
        self.assertLess(J.coherence(gabarits), 0.12)

        for texte, vitesse in (("Jarvis", 140), ("Jarvis, allume la lumière en bleu", 160),
                               ("Jarvis", 180)):
            o, s = self.oreille(gabarits)
            r = self.reveils(o, s, dire(texte, vitesse=vitesse))
            self.assertEqual([e["par"] for e in r], ["voix"], texte)

        for texte in ("j'arrive", "Travis", "service", "jardin", "java", "bonjour comment ça va",
                      "je vais dormir", "garage", "ça va vite", "j'avais dit", "il pleut sur la ville"):
            o, s = self.oreille(gabarits)
            self.assertEqual(self.reveils(o, s, dire(texte)), [], texte)

    def test_la_phrase_suit_l_eveil(self):
        o, s = self.oreille()
        son = np.concatenate([dire("hey jarvis", voix="en"), np.zeros(4000),
                              dire("allume la lumière en bleu s'il te plaît")])
        for x in flux(son) + flux(np.zeros(16000)):
            o.trame(x)
        phrases = [e for e in s if e["evt"] == "phrase"]
        self.assertEqual(len(phrases), 1)
        with wave.open(io.BytesIO(base64.b64decode(phrases[0]["wav"]))) as w:
            self.assertGreater(w.getnframes() / 16000.0, 2.0)


ENFANT = """
import sys, time
sys.path.insert(0, %r)
import numpy as np
import jarvis as J
port, secret, dossier, npy = sys.argv[1:5]
a = np.load(npy)
def source():
    for i in range(0, len(a) - J.TRAME + 1, J.TRAME):
        yield a[i:i + J.TRAME]
    time.sleep(1.5)
J.oreille_enfant(port, secret, dossier, source=source, jouer_son=lambda g: None)
"""


@unittest.skipUnless(ACOUSTIQUE, "modeles d'openWakeWord ou espeak-ng absents")
class ProcessusReel(unittest.TestCase):
    """L'oreille dans SON processus, comme dans l'exe : poignee de main,
    eveil, phrase -- et Machi Tool qui passe a « il t'ecoute »."""

    def test_de_bout_en_bout(self):
        tmp = tempfile.mkdtemp()
        try:
            m = charger_module(tmp)
            m.DOSSIER = tmp
            son = np.concatenate([dire("hey jarvis", voix="en"), np.zeros(3000),
                                  dire("quelle heure est-il"), np.zeros(24000)])
            npy = os.path.join(tmp, "son.npy")
            np.save(npy, np.concatenate([x for x in flux(son)]))
            script = os.path.join(tmp, "enfant.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write(ENFANT % RACINE)
            m.dossier_jarvis = lambda: MODELES
            m._commande_oreille = lambda port, secret: [sys.executable, script, str(port), secret,
                                                        MODELES, npy]
            etats = []
            origine = m.traiter_evenement

            def suivre(ev):
                origine(ev)
                etats.append(m.JARVIS["etat"])
            m.traiter_evenement = suivre
            m.demarrer_oreille(m.CFG)
            fin = time.time() + 60
            while time.time() < fin and not m._JARVIS_TRAVAIL:
                time.sleep(0.1)
            self.assertIn("attente", etats)
            self.assertIn("ecoute", etats)
            self.assertEqual(len(m._JARVIS_TRAVAIL), 1)
            with wave.open(io.BytesIO(base64.b64decode(m._JARVIS_TRAVAIL[0]))) as w:
                self.assertGreater(w.getnframes() / 16000.0, 1.5)
            m.arreter_oreille()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


PIPER_EXE = os.environ.get("JARVIS_PIPER", "")
PIPER_VOIX = os.environ.get("JARVIS_PIPER_VOIX", "")


@unittest.skipUnless(NUMPY and PIPER_EXE and PIPER_VOIX, "JARVIS_PIPER / JARVIS_PIPER_VOIX absents")
class VoixPiper(unittest.TestCase):
    """La vraie synthese, jouee dans un faux haut-parleur : elle arrive par
    morceaux (on parle avant d'avoir tout calcule), et « stop » coupe net."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = charger_module(self.tmp)
        self.joue = []
        test = self

        class Lecteur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def play(self, data):
                test.joue.append(len(data))
                if test.couper_apres and len(test.joue) >= test.couper_apres:
                    test.voix.couper.set()

        class HautParleur:
            def player(self, samplerate, channels=1):
                test.frequence = samplerate
                return Lecteur()

        faux = type(sys)("soundcard")
        faux.default_speaker = lambda: HautParleur()
        self.avant = sys.modules.get("soundcard")
        sys.modules["soundcard"] = faux
        self.voix = self.m.Voix()
        self.couper_apres = 0
        self.moteur = (PIPER_EXE, PIPER_VOIX, J.frequence_du_modele(PIPER_VOIX + ".json"))

    def tearDown(self):
        if self.avant is not None:
            sys.modules["soundcard"] = self.avant
        else:
            sys.modules.pop("soundcard", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_elle_parle_par_morceaux(self):
        r = self.voix._piper(J.texte_pour_piper("Bonjour. Tous les systèmes sont opérationnels."),
                             self.moteur)
        self.assertTrue(r)
        secondes = sum(self.joue) / float(self.moteur[2])
        self.assertGreater(secondes, 1.5)
        self.assertGreater(len(self.joue), 10, "joue au fil de l'eau, pas d'un bloc")

    def test_stop_coupe_net(self):
        self.couper_apres = 3
        r = self.voix._piper("Une tres longue phrase. " * 20, self.moteur)
        self.assertIs(r, False)
        self.assertLessEqual(len(self.joue), 4)


if __name__ == "__main__":
    unittest.main(verbosity=1)
