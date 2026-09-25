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
        self.assertEqual(self.action("Laisse tomber."), "fin")
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


class FinEtModes(unittest.TestCase):
    def test_la_fin_d_une_conversation(self):
        for t in ("Non rien.", "Oublie.", "Dégage !", "non merci c'est tout", "laisse tomber",
                  "rien", "merci Jarvis", "Non, c'est bon.", "oublie ça", "Casse-toi.", "au revoir",
                  "bon, rien", "ça ira, merci"):
            self.assertTrue(J.fin_de_conversation(t), t)
        for t in ("j'ai rien fait de la journée", "oublie pas de me rappeler le rendez-vous",
                  "rien ne va aujourd'hui", "je voudrais que tu dégages ce bug de mon code",
                  "merci pour tout ce que tu fais, vraiment, ça compte beaucoup pour moi"):
            self.assertFalse(J.fin_de_conversation(t), t)

    def test_le_renvoyer(self):
        # « Quand je lui dis "degage" il devrait partir, pareil pour "pars" ou
        # "get away" ou "stop" ou "re-pars". »
        for t in ("Dégage !", "dégage", "Pars.", "Part.", "Re-pars !", "repars", "Get away!", "stop",
                  "Stop.", "Jarvis, dégage.", "allez, dégage", "Va-t'en !", "go away Jarvis",
                  "Des gages.", "Casse-toi.", "Get lost.", "leave", "stop, Jarvis"):
            self.assertTrue(J.renvoi(t), t)
        for t in ("je voudrais que tu dégages ce bug de mon code", "pars du principe que c'est vrai",
                  "stop le minuteur", "une part de gâteau", "par exemple", "leave the lights on",
                  "stop listening", "je pars demain à Lyon", "get away from the screen for an hour"):
            self.assertFalse(J.renvoi(t), t)

    def test_vers_le_mode_psy(self):
        for t, reste in (("Psychologue.", ""), ("Passe en mode psy", ""), ("notes psy", ""),
                         ("Notes.", ""), ("Mets-toi en mode psychologue s'il te plaît", ""),
                         ("Psychologue, j'ai mal dormi cette nuit.", "j'ai mal dormi cette nuit."),
                         ("Note que j'ai pris mon traitement à 9h.", "Note que j'ai pris mon traitement à 9h."),
                         ("Prends une note : appeler le médecin", "Prends une note : appeler le médecin")):
            self.assertEqual(J.changement_de_mode(t), ("psy", reste), t)

    def test_retour_a_jarvis(self):
        for t in ("mode Jarvis", "Quitte le mode psy.", "reviens en mode normal", "sors du mode psychologue"):
            self.assertEqual(J.changement_de_mode(t), ("jarvis", ""), t)

    def test_pas_de_bascule_par_hasard(self):
        for t in ("je note que ça va mieux", "les notes de cours", "j'ai vu mon psy hier",
                  "c'est un truc de psychologue ça", "combien font 12 fois 12"):
            self.assertIsNone(J.changement_de_mode(t), t)


class EnAnglais(unittest.TestCase):
    """« And in English as well » : on peut lui parler anglais -- les commandes
    se lisent dans les deux langues, et une phrase sur soi n'en devient pas une."""

    def action(self, texte):
        a = J.comprendre(texte)
        return a and a["action"]

    def test_la_lumiere(self):
        for t, a in (("Turn off the lights.", "lumiere_off"), ("lights off", "lumiere_off"),
                     ("Turn the lights off", "lumiere_off"), ("kill the lights", "lumiere_off"),
                     ("Turn on the lights", "lumiere_on"), ("lights on please", "lumiere_on"),
                     ("Lights back to normal", "lumiere_normale"), ("normal lights", "lumiere_normale")):
            self.assertEqual(self.action(t), a, t)
        a = J.comprendre("Make the lights blue.")
        self.assertEqual((a["action"], a["nom"]), ("lumiere_couleur", "bleu"))
        self.assertEqual(J.comprendre("set the lights to red")["nom"], "rouge")
        self.assertEqual(J.comprendre("purple lights")["nom"], "violet")

    def test_minuteurs_et_rappels(self):
        a = J.comprendre("Set a timer for ten minutes")
        self.assertEqual((a["action"], a["secondes"]), ("minuteur", 600))
        self.assertEqual(J.comprendre("a 5 minute timer")["secondes"], 300)
        self.assertEqual(J.comprendre("timer for an hour and a half")["secondes"], 5400)
        a = J.comprendre("Remind me in 20 minutes to take the laundry out")
        self.assertEqual((a["secondes"], a["quoi"]), (1200, "take the laundry out"))
        a = J.comprendre("remind me to call mum in half an hour")
        self.assertEqual((a["secondes"], a["quoi"]), (1800, "call mum"))
        self.assertEqual(self.action("cancel the timers"), "minuteurs_annuler")

    def test_heure_date_et_le_reste(self):
        for t, a in (("What time is it?", "heure"), ("what's the date", "date"), ("What day is it today", "date"),
                     ("stop listening", "dormir"), ("screen mode", "mode"), ("switch to music mode", "mode"),
                     ("open BrainDebugger", "ouvrir_site"), ("open machi tool", "ouvrir_panneau"),
                     ("sync my day", "synchro"), ("shut up", "silence"), ("never mind", "fin"),
                     ("learn my voice", "apprendre"), ("Apprends ma voix.", "apprendre")):
            self.assertEqual(self.action(t), a, t)
        self.assertEqual(J.comprendre("switch to music mode")["mode"], "son")

    def test_ce_qui_parle_de_soi_va_a_jarvis(self):
        for t in ("I feel switched off today", "the lights in my head are off", "what a day it has been",
                  "tell me a joke about timers", "why is the sky blue", "go home and rest"):
            self.assertIsNone(J.comprendre(t), t)

    def test_durees(self):
        for t, s in (("10 minutes", 600), ("ten minutes", 600), ("twenty-five minutes", 1500),
                     ("an hour", 3600), ("half an hour", 1800), ("a quarter of an hour", 900),
                     ("an hour and a half", 5400), ("one and a half hours", 5400), ("90 seconds", 90),
                     ("two hours and thirty minutes", 9000)):
            self.assertEqual(J.duree_en(t), s, t)
        self.assertIsNone(J.duree_en("a nice day"))
        self.assertEqual(J.duree("dix minutes"), 600)
        self.assertEqual(J.duree("ten minutes"), 600)
        self.assertEqual(J.dire_duree(5400, "en"), "1 hour and 30 minutes")
        self.assertEqual(J.dire_duree(45, "en"), "45 seconds")

    def test_fin_et_modes(self):
        for t in ("never mind", "Forget it.", "no thanks", "that'll be all, Jarvis", "goodbye", "nothing"):
            self.assertTrue(J.fin_de_conversation(t), t)
        self.assertFalse(J.fin_de_conversation("nothing works on my computer today"))
        self.assertEqual(J.changement_de_mode("therapist mode"), ("psy", ""))
        self.assertEqual(J.changement_de_mode("switch to therapist mode, I slept badly"), ("psy", "I slept badly"))
        self.assertEqual(J.changement_de_mode("take a note that I took my meds"),
                         ("psy", "take a note that I took my meds"))
        self.assertEqual(J.changement_de_mode("back to Jarvis"), ("jarvis", ""))
        self.assertEqual(J.changement_de_mode("exit therapist mode"), ("jarvis", ""))
        self.assertIsNone(J.changement_de_mode("shrink the window"))

    def test_jarvis_re(self):
        """« Jarvis ? Re ! » : de retour aupres du majordome -- le mot d'eveil
        retire, il reste « re »."""
        self.assertEqual(J.changement_de_mode(J.retirer_mot_eveil("Jarvis ? Re !")), ("jarvis", ""))
        for t in ("re", "Ré !", "je suis de retour", "I'm back"):
            self.assertEqual(J.changement_de_mode(t), ("jarvis", ""), t)
        for t in ("regarde ça", "recommence", "respire"):
            self.assertIsNone(J.changement_de_mode(t), t)


class Kokoro(unittest.TestCase):
    """La voix anglaise, sans le modele : son vocabulaire, ses phonemes, ses
    morceaux et le melange des voix."""

    def test_le_vocabulaire(self):
        v = J.KOKORO_VOCAB
        self.assertEqual(len(v), 114)
        self.assertEqual((v[";"], v[" "], v["̃"], v["ᵻ"]), (1, 16, 17, 177))
        self.assertEqual(len(set(v.values())), 114)
        # Le fichier de Kokoro-82M, quand il est la : la table recopiee lui est identique.
        conf = os.path.join(os.environ.get("JARVIS_KOKORO_DOSSIER", ""), "config.json")
        if os.path.isfile(conf):
            with open(conf, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["vocab"], v)

    def test_les_phonemes(self):
        import unicodedata
        self.assertEqual(J.phonemes_kokoro(list("həlˈəʊ  (fr)wˈɜːld.")), "həlˈəʊ wˈɜːld.")
        # « ç » est un symbole du vocabulaire : decompose, la cedille s'y perdait
        self.assertEqual(J.phonemes_kokoro(list(unicodedata.normalize("NFD", "ça"))), "ça")

    def test_une_phrase_trop_longue_en_morceaux(self):
        long_ = ", ".join(["wˈʌn tˈuː θɹˈiː fˈɔː"] * 60)
        bouts = J.morceaux_kokoro(long_)
        self.assertGreater(len(bouts), 1)
        self.assertTrue(all(len(b) <= J.KOKORO_MAX for b in bouts))
        self.assertEqual("".join(bouts).replace(" ", "").replace(",", ""),
                         long_.replace(" ", "").replace(",", ""))

    @unittest.skipUnless(NUMPY, "numpy")
    def test_le_melange_des_voix(self):
        pack = {"bm_fable": np.ones((510, 1, 256), np.float32), "bm_lewis": 2 * np.ones((510, 1, 256), np.float32)}
        s = J.style_kokoro(pack, "jarvis")
        self.assertEqual(s.shape, (510, 1, 256))
        self.assertAlmostEqual(float(s[0, 0, 0]), 0.7 * 1 + 0.3 * 2, places=5)
        self.assertAlmostEqual(float(J.style_kokoro(pack, "bm_fable")[3, 0, 7]), 1.0)
        # une voix inconnue : celle de Jarvis
        self.assertAlmostEqual(float(J.style_kokoro(pack, "nimporte")[0, 0, 0]), 1.3, places=5)


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

    def test_jarvis_orange_psy_bleu(self):
        """« De base Jarvis est orange, le mode psychologue est bleu. » L'etat
        se lit dans le mouvement, le mode dans la teinte."""
        for etat in ("ecoute", "comprend", "pense", "parle"):
            for t in (0.0, 0.3, 1.1, 2.7):
                (r, v, b), gain = J.couleur_etat(etat, t, mode="jarvis")
                self.assertTrue(0.05 <= gain <= 1.0)
                self.assertGreater(r, b, "orange : %s" % etat)
                (r, v, b), _ = J.couleur_etat(etat, t, mode="psy")
                self.assertGreater(b, r, "bleu : %s" % etat)
        # Le mouvement differe d'un etat a l'autre.
        gains = {e: tuple(round(J.couleur_etat(e, t / 7.0)[1], 3) for t in range(14))
                 for e in ("ecoute", "comprend", "pense", "parle")}
        self.assertEqual(len(set(gains.values())), 4)
        self.assertNotEqual(J.COULEURS["fait"], J.COULEURS["erreur"])
        self.assertIsNone(J.couleur_etat("inconnu", 0))
        self.assertEqual(J.couleur_etat("fait", 0, {"fait": "#010203"})[0], (1.0, 2.0, 3.0))
        self.assertEqual(J.couleur_etat("ecoute", 0.3125, {"psy": "#00FF00"}, "psy")[0], (0.0, 255.0, 0.0))

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
        m.JARVIS.update(led=None, led_fin=0.0, minuteurs=[], etat="attente", mode="jarvis",
                        mode_vu=0.0, historique=[], vu=0.0, propose_psy=False,
                        psy_echange=[], psy_grave=False, reveil_par=None)
        self.dit, self.envoye = [], []
        m.JARVIS_CROCHETS.clear()
        m.JARVIS_CROCHETS["notifier"] = lambda t, x: self.dit.append(x)
        self._origines = {k: getattr(m, k) for k in ("transcrire", "etat_dictee", "parler_au_compagnon",
                                                      "parler_a_jarvis", "jouer_son", "sauver_config",
                                                      "prechauffer_dictee", "apprendre_a_voix_haute",
                                                      "gabarits_jarvis", "envoyer_voix", "voix_prete",
                                                      "envoyer_oreille", "VOIX")}
        m.jouer_son = lambda g: None
        m.sauver_config = lambda cfg: True
        m.etat_dictee = lambda: {"etat": "pret", "progres": 1.0}

    def tearDown(self):
        for k, v in self._origines.items():
            setattr(self.m, k, v)

    def apprentissage(self, vecteurs, **kw):
        """apprendre_voix, l'oreille remplacee : chaque « apprendre » recoit le
        gabarit suivant de `vecteurs`. Rend (reussi, consignes, gabarits gardes)."""
        m = self.m
        file_ = list(vecteurs)
        consignes = []

        def oreille(o):
            if o.get("cmd") == "apprendre":
                consignes.append(m.JARVIS["apprentissage"]["message"])
                m._GABARIT_RECU["evt"] = {"evt": "gabarit", "vecteurs": file_.pop(0)}
                m._GABARIT_RECU["signal"].set()
            return True

        class SansAttente:
            def __getattr__(self, n):
                return getattr(time, n)

            def sleep(self, s):
                pass
        vrais = (m.time, m.oreille_vivante, m.poser_led)
        m.time, m.oreille_vivante, m.envoyer_oreille = SansAttente(), (lambda: True), oreille
        m.poser_led = lambda *a, **k: None
        try:
            ok = m.apprendre_voix(**kw)
        finally:
            m.time, m.oreille_vivante, m.poser_led = vrais
        return ok, consignes, m.gabarits_jarvis()

    def test_quatre_fois_la_derniere_comme_une_question(self):
        rng = np.random.default_rng(3)
        base = rng.normal(size=(8, 96))
        proche = lambda e: (base + rng.normal(scale=e, size=base.shape)).tolist()
        ok, consignes, gardes = self.apprentissage([proche(0.3), proche(0.3), proche(0.3), proche(0.5)])
        self.assertTrue(ok)
        self.assertEqual(len(gardes), 4)
        self.assertIn("question", consignes[-1])
        # Une « question » qui est un autre mot : on garde les trois, sans tout refaire.
        autre = rng.normal(size=(8, 96)).tolist()
        ok, _, gardes = self.apprentissage([proche(0.3), proche(0.3), proche(0.3), autre])
        self.assertTrue(ok)
        self.assertEqual(len(gardes), 3)
        # « Ajouter une facon » : une de plus, avec les autres ; pas un autre mot.
        ok, _, gardes = self.apprentissage([proche(0.5)], total=1, ajouter=True)
        self.assertTrue(ok)
        self.assertEqual(len(gardes), 4)
        ok, _, gardes = self.apprentissage([rng.normal(size=(8, 96)).tolist()], total=1, ajouter=True)
        self.assertFalse(ok)
        self.assertEqual(len(gardes), 4)

    def test_sa_voix_francaise_par_kokoro_sinon_piper(self):
        m = self.m
        origines = (m.kokoro_present, m.bibli_espeak, m.piper_pret)
        m.bibli_espeak = lambda: __file__           # un fichier qui existe
        m.piper_pret = lambda cfg: {"nom": "fr_FR-tom-medium", "modele": "tom.onnx", "locuteur": 0}
        try:
            m.kokoro_present = lambda: True
            m.CFG["jarvis_langue"] = "fr"
            self.assertEqual(m.voix_fr_choisie(m.CFG), "fr_jarvis", "Kokoro par defaut")
            (fr,) = m.charges_voix(m.CFG)
            self.assertEqual((fr["cle"], fr["moteur"], fr["espeak"], fr["langue"], fr["voix"]),
                             ("fr", "kokoro", "fr", "fr", "fr_jarvis"))
            self.assertTrue(m.kokoro_voulu(m.CFG), "Jarvis en francais fait venir Kokoro")
            # Kokoro pas encore la : Piper parle en attendant
            m.kokoro_present = lambda: False
            (fr,) = m.charges_voix(m.CFG)
            self.assertEqual(fr["moteur"], "piper")
            # Piper choisi : Kokoro ne sert plus, s'il ne parle pas anglais
            m.kokoro_present = lambda: True
            m.CFG["jarvis_voix_fr"] = "piper"
            (fr,) = m.charges_voix(m.CFG)
            self.assertEqual(fr["moteur"], "piper")
            self.assertFalse(m.kokoro_voulu(m.CFG))
            m.CFG["jarvis_voix_fr"] = "n'importe quoi"
            self.assertEqual(m.voix_fr_choisie(m.CFG), "fr_jarvis")
        finally:
            m.kokoro_present, m.bibli_espeak, m.piper_pret = origines

    def test_le_micro_choisi_part_a_l_oreille_et_revient(self):
        m = self.m
        self.assertEqual(m.config_oreille(m.CFG)["micro"], "", "par defaut, celui de Windows")
        m.CFG["jarvis_micro"] = "{B}"
        self.assertEqual(m.config_oreille(m.CFG)["micro"], "{B}")
        m.traiter_evenement({"evt": "pret", "micro": "Micro casque", "trouve": False})
        self.assertEqual(m.JARVIS["micro"], "Micro casque")
        self.assertTrue(m.JARVIS["micro_absent"], "debranche : il le dit")
        m.traiter_evenement({"evt": "pret", "micro": "Webcam", "trouve": True})
        self.assertFalse(m.JARVIS["micro_absent"])

    def test_jarvis_est_eteint_par_defaut(self):
        self.assertFalse(self.m.CONFIG_DEFAUT["jarvis_actif"],
                         "un micro ouvert en permanence se decide, il ne s'impose pas")

    def phrase(self, texte):
        self.m.transcrire = lambda octets: texte
        self.m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), self.m.CFG)

    def espions(self):
        vus = {"jarvis": [], "psy": []}
        self.m.parler_a_jarvis = lambda t, cfg: vus["jarvis"].append(t)
        self.m.parler_au_compagnon = lambda t, cfg: vus["psy"].append(t)
        return vus

    def test_une_commande_reste_ici(self):
        vus = self.espions()
        self.phrase("Jarvis, mets la lumière en rouge.")
        self.assertEqual(vus, {"jarvis": [], "psy": []})
        self.assertEqual(self.m.ETAT["forcage"]["couleur"], (255, 26, 26))
        self.assertEqual(self.m.JARVIS["led"], "fait")

    def test_par_defaut_c_est_le_majordome(self):
        vus = self.espions()
        self.phrase("Hey Jarvis, combien de mégaoctets dans un gigaoctet ?")
        self.assertEqual(vus["jarvis"], ["combien de mégaoctets dans un gigaoctet ?"])
        self.assertEqual(vus["psy"], [])

    def test_psychologue_passe_au_compagnon_et_en_bleu(self):
        vus = self.espions()
        self.phrase("Jarvis, psychologue.")
        self.assertEqual(self.m.JARVIS["mode"], "psy")
        self.assertEqual(self.dit, ["Mode psychologue. Je vous écoute."])
        self.phrase("je rentre du sport et je suis crevé")
        self.assertEqual(vus["psy"], ["je rentre du sport et je suis crevé"])
        # La guirlande : bleu en mode psy, orange en mode Jarvis.
        self.m.poser_led("ecoute")
        (r, v, b), _ = self.m.couleur_jarvis(self.m.CFG)
        self.assertGreater(b, r)
        self.m.poser_mode("jarvis")
        (r, v, b), _ = self.m.couleur_jarvis(self.m.CFG)
        self.assertGreater(r, b)

    def test_une_note_part_entiere_au_journal(self):
        vus = self.espions()
        self.phrase("Jarvis, note que j'ai pris mon traitement à 9 heures.")
        self.assertEqual(vus["psy"], ["note que j'ai pris mon traitement à 9 heures."])
        self.assertEqual(self.m.JARVIS["mode"], "psy")

    def test_non_rien_oublie_degage_terminent(self):
        for fin in ("Jarvis, non rien.", "oublie", "Dégage !", "non merci c'est tout"):
            vus = self.espions()
            self.m.poser_mode("psy")
            envoye = []
            self.m.envoyer_oreille = lambda o, e=envoye: e.append(o) or True
            self.phrase(fin)
            self.assertEqual(vus, {"jarvis": [], "psy": []}, fin)
            self.assertEqual(self.m.JARVIS["mode"], "jarvis", fin)
            self.assertIn({"cmd": "annuler"}, envoye, "il n'ecoute plus la suite")
        self.assertEqual(self.dit, [], "on se tait, on ne repond pas « au revoir »")

    def test_degage_pars_stop_le_renvoient_sans_un_mot(self):
        # Meme au psychologue : « au revoir » laisse le majordome placer un
        # mot, « degage » non -- BrainDebugger n'est meme pas appele.
        demandes = []
        vraie = self.m._requete_bd
        self.m._requete_bd = lambda *a, **k: demandes.append(a) or {"texte": "Bonne soirée.", "mode": "jarvis"}
        try:
            for t in ("Dégage !", "Pars.", "Re-pars", "Get away!", "Stop."):
                vus = self.espions()
                self.m.poser_mode("psy")
                self.m.JARVIS["psy_echange"] = [{"role": "user", "texte": "bonjour"},
                                                {"role": "assistant", "texte": "Bonjour."}]
                envoye = []
                self.m.envoyer_oreille = lambda o, e=envoye: e.append(o) or True
                self.phrase(t)
                self.assertEqual(vus, {"jarvis": [], "psy": []}, t)
                self.assertEqual(self.m.JARVIS["mode"], "jarvis", t)
                self.assertEqual(self.m.JARVIS["psy_echange"], [], t)
                self.assertIn({"cmd": "annuler"}, envoye, "il n'ecoute plus la suite")
        finally:
            self.m._requete_bd = vraie
        self.assertEqual(demandes, [], "il part sans demander de mot de la fin")
        self.assertEqual(self.dit, [])

    def test_oui_apres_la_proposition(self):
        vus = self.espions()
        self.m.JARVIS["propose_psy"] = True
        self.phrase("Oui vas-y.")
        self.assertEqual(self.m.JARVIS["mode"], "psy")
        self.assertEqual(vus, {"jarvis": [], "psy": []})
        # Sans proposition, « oui » est une phrase comme une autre.
        self.m.poser_mode("jarvis")
        self.phrase("oui")
        self.assertEqual(vus["jarvis"], ["oui"])

    def test_le_mode_psy_se_referme_seul(self):
        self.m.poser_mode("psy")
        self.assertEqual(self.m.mode_courant(), "psy")
        self.assertEqual(self.m.mode_courant(time.time() + self.m.PSY_DUREE_S + 1), "jarvis")

    def test_le_majordome_par_la_cle_avec_la_conversation(self):
        self.m.CFG["jarvis_appellation"] = "Alex"
        with mock_urlopen(self.m, {"texte": "Mille vingt-quatre.", "mode": "jarvis"}) as req:
            self.phrase("Jarvis, combien de mégaoctets dans un gigaoctet")
            self.phrase("Jarvis, et en kilo ?")
        self.assertEqual(req[0].full_url, "https://bd.exemple/api/machitool/jarvis")
        self.assertEqual(req[0].get_header("Authorization"), "Bearer CLE")
        premier, second = (json.loads(r.data.decode()) for r in req)
        self.assertEqual(premier["historique"], [])
        self.assertEqual(premier["appellation"], "Alex")
        self.assertEqual([h["role"] for h in second["historique"]], ["user", "assistant"])
        self.assertEqual(self.dit, ["Mille vingt-quatre.", "Mille vingt-quatre."])

    def test_grave_le_majordome_passe_la_main(self):
        with mock_urlopen(self.m, {"texte": "Je suis là. On en parle ?", "mode": "psy"}):
            self.phrase("Jarvis, j'ai envie de mourir")
        self.assertEqual(self.m.JARVIS["mode"], "psy")
        self.assertEqual(self.dit, ["Je suis là. On en parle ?"])

    def test_il_propose_le_mode_psy_et_on_s_en_souvient(self):
        with mock_urlopen(self.m, {"texte": "Voulez-vous que je passe en mode psychologue ?",
                                   "mode": "jarvis"}):
            self.phrase("Jarvis, j'ai mal dormi")
        self.assertTrue(self.m.JARVIS["propose_psy"])

    def test_jarvis_tout_seul_attend_la_suite(self):
        self.phrase("Jarvis.")
        self.assertEqual(self.dit, ["Yes?"])
        self.m.CFG["jarvis_langue"] = "fr"
        self.phrase("Jarvis.")
        self.assertEqual(self.dit, ["Yes?", "Oui ?"])

    def test_ce_qui_est_dit_n_est_jamais_journalise(self):
        journal = io.StringIO()
        secret = "mon secret intime numero 7"
        with mock_urlopen(self.m, {"texte": "Je t'entends.", "mode": "jarvis"}):
            with redirect_stdout(journal):
                self.phrase("Jarvis, " + secret)
                self.phrase("Jarvis, rappelle-moi dans 10 minutes de " + secret)
                self.phrase("Jarvis, psychologue, " + secret)
        for m_ in self.m.JARVIS["minuteurs"]:
            m_["minuteur"].cancel()
        self.assertNotIn("secret", journal.getvalue())
        self.assertIn("commande minuteur", journal.getvalue())

    def test_le_compagnon_recoit_la_phrase_par_la_cle(self):
        self.m.poser_mode("psy")
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
        self.phrase("Jarvis, raconte-moi une histoire")
        self.assertEqual(self.m.JARVIS["etat"], "erreur")
        self.assertIn("BrainDebugger key", self.m.JARVIS["message"])
        self.m.CFG["jarvis_langue"] = "fr"
        self.phrase("Jarvis, raconte-moi une histoire")
        self.assertIn("clé", self.m.JARVIS["message"])

    def test_l_heure_et_les_minuteurs(self):
        self.m.CFG["jarvis_langue"] = "fr"
        t = time.mktime((2026, 9, 24, 14, 5, 0, 0, 0, -1))
        self.assertEqual(self.m.executer_commande({"action": "heure"}, self.m.CFG, t), "Il est 14 heures 05.")
        self.assertEqual(self.m.executer_commande({"action": "date"}, self.m.CFG, t),
                         "Nous sommes le jeudi 24 septembre.")
        dit = self.m.executer_commande({"action": "minuteur", "secondes": 600, "quoi": ""}, self.m.CFG)
        self.assertEqual(dit, "Minuteur de 10 minutes, lancé.")
        self.assertEqual(len(self.m.JARVIS["minuteurs"]), 1)
        self.assertEqual(self.m.executer_commande({"action": "minuteurs_annuler"}, self.m.CFG), "C'est annulé.")
        self.assertEqual(self.m.JARVIS["minuteurs"], [])

    def test_jarvis_parle_anglais_par_defaut(self):
        m = self.m
        self.assertEqual(m.CONFIG_DEFAUT["jarvis_langue"], "en")
        t = time.mktime((2026, 9, 24, 14, 5, 0, 0, 0, -1))
        self.assertEqual(m.executer_commande({"action": "heure"}, m.CFG, t), "It's 2:05 in the afternoon.")
        self.assertEqual(m.executer_commande({"action": "heure"}, m.CFG, time.mktime((2026, 9, 24, 18, 0, 0, 0, 0, -1))),
                         "It's 6 o'clock in the evening.")
        self.assertEqual(m.executer_commande({"action": "date"}, m.CFG, t), "It's Thursday, the 24th of September.")
        self.assertEqual(m.executer_commande({"action": "minuteur", "secondes": 600, "quoi": ""}, m.CFG),
                         "Timer set for 10 minutes.")
        self.assertEqual(m.executer_commande({"action": "minuteurs_annuler"}, m.CFG), "Cancelled.")
        # le mode psy, lui, reste francais
        m.poser_mode("psy")
        self.assertEqual(m.executer_commande({"action": "minuteurs_annuler"}, m.CFG),
                         "Il n'y avait aucun minuteur en cours.")

    def test_le_reveil_remet_toujours_en_mode_jarvis(self):
        """« Quand Jarvis s'allume il doit toujours etre en mode Jarvis (meme
        s'il etait en psychologue avant). »"""
        m = self.m
        m.prechauffer_dictee = lambda: None
        m.envoyer_oreille = lambda o: True
        m.poser_mode("psy")
        m.traiter_evenement({"evt": "reveil", "par": "voix", "score": 0.1})
        self.assertEqual(m.JARVIS["mode"], "jarvis")

    def test_jarvis_re_revient_du_psy(self):
        vus = self.espions()
        self.m.poser_mode("psy")
        self.phrase("Jarvis ? Re !")
        self.assertEqual(self.m.JARVIS["mode"], "jarvis")
        self.assertEqual(self.dit, ["Welcome back."])
        self.assertEqual(vus, {"jarvis": [], "psy": []})

    def _seance(self):
        m = self.m
        m.envoyer_oreille = lambda o: True
        m.poser_mode("psy")
        echange = [{"role": "user", "texte": "j'ai raté mon gâteau"}, {"role": "assistant", "texte": "Ça arrive."}]
        m.JARVIS["psy_echange"] = list(echange)
        return echange

    def test_au_revoir_au_psy_un_mot_leger_au_plus(self):
        echange = self._seance()
        with mock_urlopen(self.m, {"texte": "Back to business. Shall I order a cake?", "mode": "jarvis"}) as req:
            self.phrase("Au revoir.")
        self.assertEqual(req[0].full_url, "https://bd.exemple/api/machitool/jarvis")
        corps = json.loads(req[0].data.decode())
        self.assertEqual((corps["transition"], corps["psy"], corps["langue"]), ("fin_psy", echange, "en"))
        self.assertEqual(self.dit, ["Back to business. Shall I order a cake?"])
        self.assertEqual(self.m.JARVIS["mode"], "jarvis")
        self.assertEqual(self.m.JARVIS["psy_echange"], [], "la seance ne reste pas en memoire")

    def test_au_revoir_au_psy_brain_debugger_choisit_le_silence(self):
        self._seance()
        with mock_urlopen(self.m, {"texte": "", "mode": "jarvis"}):
            self.phrase("au revoir")
        self.assertEqual(self.dit, [])
        self.assertEqual(self.m.JARVIS["mode"], "jarvis")

    def test_au_revoir_au_psy_apres_un_message_grave_il_se_tait_sans_demander(self):
        self._seance()
        self.m.JARVIS["psy_grave"] = True
        with mock_urlopen(self.m, {"texte": "Ha, splendid.", "mode": "jarvis"}) as req:
            self.phrase("Au revoir.")
        self.assertEqual(req, [], "il ne demande meme pas")
        self.assertEqual(self.dit, [])

    def test_la_seance_psy_en_memoire_et_le_grave_retenu(self):
        m = self.m
        m.poser_mode("psy")
        with mock_urlopen(m, {"texte": "Je vous entends."}):
            m.parler_au_compagnon("journée difficile", m.CFG)
        self.assertEqual(m.JARVIS["psy_echange"], [{"role": "user", "texte": "journée difficile"},
                                                   {"role": "assistant", "texte": "Je vous entends."}])
        m.poser_mode("jarvis")
        with mock_urlopen(m, {"texte": "Je suis là.", "mode": "psy"}):
            self.phrase("Jarvis, j'ai envie de mourir")
        self.assertEqual(m.JARVIS["mode"], "psy")
        self.assertTrue(m.JARVIS["psy_grave"])

    def test_apprends_ma_voix_a_voix_haute(self):
        lance = threading.Event()
        self.m.apprendre_a_voix_haute = lambda cfg: lance.set()
        self.phrase("Jarvis, learn my voice.")
        self.assertTrue(lance.wait(2.0))

    def test_l_astuce_pour_jarvis_tout_seul_une_seule_fois(self):
        m = self.m
        m.gabarits_jarvis = lambda: []
        m.JARVIS["reveil_par"] = "hey"
        self.phrase("Hey Jarvis.")
        self.assertIn("learn my voice", self.dit[-1])
        self.assertTrue(m.CFG["jarvis_astuce_voix"])
        self.phrase("Hey Jarvis.")
        self.assertEqual(self.dit[-1], "Yes?")

    def _jarvis_parle(self):
        """Jarvis repond a voix haute (sa voix neuronale), puis on lui coupe la
        parole pendant sa deuxieme phrase."""
        m = self.m
        voix, oreille = [], []
        m.envoyer_voix = lambda o: voix.append(o) or True
        m.envoyer_oreille = lambda o: oreille.append(o) or True
        m.voix_prete = lambda cle=None: True
        m.prechauffer_dictee = lambda: None
        m.VOIX = m.Voix()
        m.CFG["jarvis_voix"] = True
        m.dire("Good evening. All systems are operational. Your calendar is clear.", langue="en")
        ident = voix[-1]["id"]
        self.assertEqual(m.JARVIS["etat"], "parle")
        m.traiter_evenement({"evt": "coupure"})
        self.assertEqual(voix[-1], {"cmd": "taire"})
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        # la voix s'est tue au milieu de la deuxieme phrase, et le dit
        m.VOIX.fini(ident, True, "All systems are operational. Your calendar is clear.")
        return voix, oreille

    def test_coupe_pour_rien_il_reprend_sa_phrase(self):
        """Un clavier, une porte : l'oreille coupe, puis personne ne parle.
        Jarvis reprend a la phrase coupee -- et termine comme avant."""
        m = self.m
        voix, oreille = self._jarvis_parle()
        m.traiter_evenement({"evt": "vide", "apres_coupure": True})
        self.assertEqual(voix[-1]["cmd"], "dire")
        self.assertEqual(voix[-1]["texte"], "All systems are operational. Your calendar is clear.")
        self.assertEqual(voix[-1]["cle"], "en")
        self.assertEqual(m.JARVIS["etat"], "parle")
        m.VOIX.fini(voix[-1]["id"], False)
        self.assertEqual(m.JARVIS["etat"], "attente", "la fin d'avant : il a fini de parler")
        n = len(voix)
        m.traiter_evenement({"evt": "vide", "apres_coupure": True})
        self.assertEqual(len(voix), n, "on ne reprend qu'une fois")

    def test_coupe_avec_une_suite_en_attente_il_reprend_celle_qui_sonnait(self):
        m = self.m
        voix, oreille = [], []
        m.envoyer_voix = lambda o: voix.append(o) or True
        m.envoyer_oreille = lambda o: oreille.append(o) or True
        m.voix_prete = lambda cle=None: True
        m.prechauffer_dictee = lambda: None
        m.VOIX = m.Voix()
        m.CFG["jarvis_voix"] = True
        m.dire("First answer. Still the first one.", langue="en")
        m.dire("A second one, waiting its turn.", langue="en")
        premier = voix[0]["id"]
        m.traiter_evenement({"evt": "coupure"})
        self.assertEqual(m.VOIX.reprise["id"], premier, "celle qui sonnait, pas celle qui attendait")
        self.assertEqual(m.VOIX.en_cours, {}, "la voix a jete celle qui attendait : rien ne traine")
        m.VOIX.fini(premier, True, "Still the first one.")
        m.traiter_evenement({"evt": "vide", "apres_coupure": True})
        self.assertEqual(voix[-1]["texte"], "Still the first one.")

    def test_coupe_par_un_bruit_sans_mots_il_reprend_aussi(self):
        """La phrase d'apres la coupure n'avait pas de mots (le micro a entendu
        quelque chose) : l'oreille apprend que c'etait de l'echo, il reprend."""
        m = self.m
        voix, oreille = self._jarvis_parle()
        m.transcrire = lambda octets: ""
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
        self.assertIn({"cmd": "fausse_coupure"}, oreille)
        self.assertEqual(voix[-1]["texte"], "All systems are operational. Your calendar is clear.")

    def test_coupe_pour_de_vrai_il_ecoute_et_ne_reprend_pas(self):
        m = self.m
        voix, oreille = self._jarvis_parle()
        m.transcrire = lambda octets: "What time is it?"
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
        self.assertNotIn({"cmd": "fausse_coupure"}, oreille)
        self.assertIsNone(m.VOIX.reprise)
        textes = [v.get("texte", "") for v in voix if v.get("cmd") == "dire"]
        self.assertNotIn("All systems are operational. Your calendar is clear.", textes)
        self.assertTrue(textes[-1].startswith("It's"), textes[-1])
        # une phrase sans mots, MAIS pas apres une coupure : « Yes? », comme avant
        m.transcrire = lambda octets: ""
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(voix[-1]["texte"], "Yes?")

    def test_une_voix_par_langue(self):
        """L'anglais a Kokoro, le francais a Piper ; sans la voix anglaise, la
        voix de Windows EN ANGLAIS plutot que Piper qui lirait de l'anglais."""
        m = self.m
        envoyes = []
        m.envoyer_voix = lambda o: envoyes.append(o) or True
        m.voix_prete = lambda cle=None: cle in (None, "en", "fr")
        v = m.Voix()
        v.disponible = False
        v.dire("Good evening.", None, "en")
        v.dire("Bonsoir.", None, "fr")
        self.assertEqual([(e["cle"], e["texte"]) for e in envoyes], [("en", "Good evening."), ("fr", "Bonsoir.")])
        m.voix_prete = lambda cle=None: cle in (None, "fr")
        v = m.Voix()
        v.disponible = True
        v.fil = type("Vivant", (), {"is_alive": lambda self: True})()
        v.dire("Good evening.", None, "en")
        self.assertEqual(len(envoyes), 2, "pas de Piper francais pour lire de l'anglais")
        self.assertEqual(v.file[0][0::2], ("Good evening.", "en"))

    def test_la_voix_anglaise_telechargee_a_l_octet_pres(self):
        m = self.m
        tailles = dict(J.KOKORO_TAILLES)
        J.KOKORO_TAILLES.update({J.KOKORO_MODELE: 12, J.KOKORO_VOIX: 7})
        try:
            zip_ = io.BytesIO()
            with zipfile.ZipFile(zip_, "w") as z:
                z.writestr("piper/" + os.path.basename(m.bibli_espeak()), b"dll")
                z.writestr("piper/espeak-ng-data/phontab", b"donnees")
            demandes = []

            def ouvrir(url):
                demandes.append(url)
                if url == J.PIPER_MOTEUR:
                    return FausseReponse(zip_.getvalue())
                if url == J.KOKORO_SOURCE + J.KOKORO_MODELE:
                    return FausseReponse(b"m" * 12)
                if url == J.KOKORO_SOURCE + J.KOKORO_VOIX:
                    return FausseReponse(b"v" * 7)
                raise OSError("inattendu : " + url)
            m.KOKORO.update(etat="absent")
            self.assertTrue(m.preparer_kokoro(m.CFG, ouvrir))
            self.assertTrue(m.kokoro_present())
            k = m.kokoro_pret(m.CFG)
            self.assertEqual((k["cle"], k["moteur"], k["espeak"], k["voix"]), ("en", "kokoro", "en", "jarvis"))
            self.assertEqual(m.charges_voix(m.CFG)[0]["cle"], "en")
            # Coupe en route : il ne passe pas pour complet.
            os.remove(m.fichier_kokoro(J.KOKORO_MODELE))

            def coupe(url):
                return FausseReponse(b"m" * 5)
            self.assertFalse(m.preparer_kokoro(m.CFG, coupe))
            self.assertFalse(m.kokoro_present())
            self.assertEqual(m.KOKORO["etat"], "erreur")
            # Jarvis en francais : la voix anglaise ne se charge pas.
            m.CFG["jarvis_langue"] = "fr"
            self.assertIsNone(m.kokoro_pret(m.CFG))
        finally:
            J.KOKORO_TAILLES.clear()
            J.KOKORO_TAILLES.update(tailles)

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
            z.writestr("piper/" + os.path.basename(m.bibli_espeak()), b"dll")
            z.writestr("piper/espeak-ng-data/phontab", b"donnees")
        tar_ = io.BytesIO()
        with tarfile.open(fileobj=tar_, mode="w:gz") as t:
            for nom, contenu in (("fr-gilles-low.onnx", b"modele"),
                                 ("fr-gilles-low.onnx.json",
                                  b'{"audio": {"sample_rate": 16000}, "espeak": {"voice": "fr"}}')):
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
        moteur = m.piper_pret(m.CFG)
        self.assertTrue(moteur["modele"].endswith("fr_FR-gilles-low.onnx"))
        self.assertEqual(moteur["frequence"], 16000)
        self.assertEqual(moteur["espeak"], "fr")
        self.assertTrue(os.path.isdir(os.path.join(moteur["donnees"], "espeak-ng-data")))
        self.assertIn("secours", m.PIPER["message"])
        m.CFG["jarvis_voix_modele"] = "windows"
        self.assertIsNone(m.piper_pret(m.CFG))

    def test_un_locuteur_pour_les_voix_a_plusieurs(self):
        m = self.m
        m.CFG["jarvis_voix_modele"] = "fr_FR-upmc-medium"
        os.makedirs(os.path.dirname(m.bibli_espeak()))
        open(m.bibli_espeak(), "wb").write(b"dll")
        f = m.fichier_voix("fr_FR-upmc-medium")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        open(f, "wb").write(b"modele")
        with open(f + ".json", "w") as fj:
            json.dump({"audio": {"sample_rate": 22050}, "espeak": {"voice": "fr"},
                       "speaker_id_map": {"jessica": 0, "pierre": 1}}, fj)
        self.assertEqual(m.piper_pret(m.CFG)["locuteur"], 1)


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

    def test_jarvis_point_d_interrogation(self):
        """« Il faut qu'il reponde plus facilement a "Jarvis ?" ». Appris quatre
        fois, la derniere comme une question -- et il repond aussi quand le nom
        vient apres un autre mot, ou qu'il traine."""
        o, sorties = self.oreille()
        gabarits = []
        for texte, vitesse, hauteur in (("Jarvis", 130, 45), ("Jarvis", 150, 50), ("Jarvis", 170, 55),
                                        ("Jarviis ?", 125, 55)):
            sorties.clear()
            for x in flux(np.zeros(1))[:10]:
                o.trame(x)
            o.commande({"cmd": "apprendre"})
            for x in flux(dire(texte, vitesse=vitesse, hauteur=hauteur))[8:]:
                o.trame(x)
                if any(e["evt"] == "gabarit" for e in sorties):
                    break
            gabarits.append([e for e in sorties if e["evt"] == "gabarit"][0]["vecteurs"])
        for texte, vitesse, hauteur in (("Jarvis ?", 170, 60), ("Jarvis ?", 120, 40), ("Jarviiis ?", 150, 50),
                                        ("Jaaarvis ?", 150, 50), ("euh Jarvis ?", 150, 50),
                                        ("ok Jarvis", 150, 50), ("bon, Jarvis ?", 150, 50),
                                        ("hé Jarvis", 150, 50), ("dis Jarvis", 150, 50)):
            o, s = self.oreille(gabarits)
            r = self.reveils(o, s, dire(texte, vitesse=vitesse, hauteur=hauteur))
            self.assertEqual([e["par"] for e in r], ["voix"], texte)
        for texte in ("j'arrive", "Travis", "service", "jardin", "java", "bonjour comment ça va",
                      "je vais dormir", "garage", "ça va vite", "j'avais dit", "il pleut sur la ville",
                      "Jacques a dit", "j'ai un avis", "t'as vu ?", "Charles vise", "archives",
                      "j'arrive vite", "Gervais", "tu arrives ?"):
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


class LeMicroChoisi(unittest.TestCase):
    """« Add a way to change the input audio » : le micro des reglages, par son
    identifiant Windows, et l'oreille qui en change sans redemarrer."""

    class Micro:
        def __init__(self, ident, nom):
            self.id, self.name = ident, nom

    def test_par_identifiant_puis_par_nom_sinon_celui_de_windows(self):
        a, b, c = self.Micro("{A}", "Micro casque"), self.Micro("{B}", "Webcam"), self.Micro("{C}", "Webcam")
        tous = lambda: [a, b, c]
        defaut = lambda: a
        self.assertEqual(J.choisir_micro(tous, "", defaut), (a, True))
        self.assertEqual(J.choisir_micro(tous, "{C}", defaut), (c, True),
                         "deux micros du meme nom : l'identifiant les distingue")
        self.assertEqual(J.choisir_micro(tous, "Webcam", defaut), (b, True))
        self.assertEqual(J.choisir_micro(tous, "{Z}", defaut), (a, False),
                         "debranche : celui de Windows, et on le sait")

    def test_l_oreille_change_de_micro_sans_redemarrer(self):
        ouverts = []

        def faux_micro(nom="", annoncer=None):
            ouverts.append(nom)
            if annoncer:
                annoncer("Micro " + (nom or "Windows"), nom != "absent")
            while True:                   # un micro ne s'arrete pas tout seul
                time.sleep(0.002)
                yield b"\0" * (2 * J.TRAME)

        class FausseOreille:
            def __init__(self, *a):
                self.reglages = {}

            def commande(self, c):
                if c.get("cmd") == "config":
                    self.reglages.update({k: v for k, v in c.items() if k != "cmd"})

            def trame(self, x):
                pass

        origines = (J.micro_windows, J.Oreille, J.Empreintes)
        J.micro_windows, J.Oreille, J.Empreintes = faux_micro, FausseOreille, lambda d: None
        serveur = socket.socket()
        serveur.bind(("127.0.0.1", 0))
        serveur.listen(1)
        port = serveur.getsockname()[1]
        fil = threading.Thread(target=J.oreille_enfant, args=(port, "secret", "."),
                               kwargs={"jouer_son": lambda g: None}, daemon=True)
        try:
            fil.start()
            conn, _ = serveur.accept()
            conn.settimeout(10)
            n = int.from_bytes(conn.recv(4), "big")
            self.assertEqual(conn.recv(n), b"secret")
            J.envoyer(conn, {"cmd": "config", "micro": "{A}"})
            prets = []

            def attendre_pret():
                while True:
                    ev = J.recevoir(conn)
                    if ev.get("evt") == "pret":
                        prets.append(ev)
                        return ev
            self.assertEqual(attendre_pret(), {"evt": "pret", "micro": "Micro {A}", "trouve": True},
                             "le micro des reglages des la premiere ouverture")
            J.envoyer(conn, {"cmd": "config", "micro": "{B}"})
            self.assertEqual(attendre_pret()["micro"], "Micro {B}")
            J.envoyer(conn, {"cmd": "config", "micro": "absent"})
            self.assertFalse(attendre_pret()["trouve"])
            conn.close()
            fil.join(10)
            self.assertFalse(fil.is_alive())
            self.assertEqual(ouverts, ["{A}", "{B}", "absent"], "jamais le mauvais micro d'abord")
        finally:
            J.micro_windows, J.Oreille, J.Empreintes = origines
            serveur.close()


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
            wav64, apres_coupure = m._JARVIS_TRAVAIL[0]
            self.assertFalse(apres_coupure, "reveille par son nom, pas apres une coupure")
            with wave.open(io.BytesIO(base64.b64decode(wav64))) as w:
                self.assertGreater(w.getnframes() / 16000.0, 1.5)
            m.arreter_oreille()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


PIPER_DOSSIER = os.environ.get("JARVIS_PIPER_DOSSIER", "")     # le dossier « piper » de l'archive
PIPER_VOIX = os.environ.get("JARVIS_PIPER_VOIX", "")
PIPER = bool(NUMPY and ONNX and PIPER_DOSSIER and PIPER_VOIX and os.path.isfile(PIPER_VOIX))


def bibli_de_test():
    for nom in ("libespeak-ng.so.1", "espeak-ng.dll", "libespeak-ng.dylib"):
        if os.path.isfile(os.path.join(PIPER_DOSSIER, nom)):
            return os.path.join(PIPER_DOSSIER, nom)
    return ""


class FauxHautParleur:
    def __init__(self, test=None, couper_apres=0):
        self.morceaux, self.test, self.couper_apres, self.frequence = [], test, couper_apres, None

    def __call__(self, frequence):
        self.frequence = frequence
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def play(self, data):
        self.morceaux.append(len(data))
        if self.couper_apres and len(self.morceaux) >= self.couper_apres:
            self.test.bouche.couper.set()


class SyntheseFactice:
    """Une seconde de son par phrase : la Bouche sans Piper, au dixieme pres."""
    frequence, langue = 16000, "fr"

    def __init__(self):
        self.lues = []

    def phrases(self, texte, lenteur=1.0, **kw):
        self.lues.append(texte)
        yield (np.sin(np.arange(16000) / 5.0) * 8000).astype(np.int16)


@unittest.skipUnless(NUMPY, "numpy absent")
class ReprendreOuIlEnEtait(unittest.TestCase):
    """Coupe pour rien, Jarvis reprend sa phrase : la voix dit ce qui restait,
    a partir de la phrase qui se disait -- pas celle d'apres, pas le debut."""

    def test_coupee_en_route_elle_dit_ce_qui_restait(self):
        syn = SyntheseFactice()
        # une phrase = 10 dixiemes de son + 2 de silence : coupee au 3e de la deuxieme
        hp, evts = FauxHautParleur(self, couper_apres=12 + 3), []
        self.bouche = J.Bouche(syn, evts.append, hp)
        self.bouche.dire(9, "Bonjour. Tous les systemes sont operationnels. Autre chose ?")
        self.assertEqual([e["evt"] for e in evts], ["debut", "fini"])
        self.assertTrue(evts[-1]["coupe"])
        self.assertEqual(evts[-1]["reste"], "Tous les systemes sont operationnels. Autre chose ?")
        self.assertEqual(len(hp.morceaux), 15)
        evts.clear()
        self.bouche = J.Bouche(syn, evts.append, FauxHautParleur())
        self.bouche.dire(10, "Bonjour. Au revoir.")
        self.assertEqual(evts[-1], {"evt": "fini", "id": 10, "coupe": False}, "rien a reprendre quand il a fini")
        self.assertEqual(syn.lues[-2:], ["Bonjour.", "Au revoir."], "une phrase a la fois")

    def test_les_phrases(self):
        self.assertEqual(J.decouper_phrases("Good evening. All systems go! Is 3.5 enough? Yes\u2026 Fine"),
                         ["Good evening.", "All systems go!", "Is 3.5 enough?", "Yes\u2026", "Fine"])
        self.assertEqual(J.decouper_phrases(""), [])


@unittest.skipUnless(PIPER, "JARVIS_PIPER_DOSSIER / JARVIS_PIPER_VOIX absents")
class VoixEnMemoire(unittest.TestCase):
    """La voix de Jarvis : Piper, le modele charge UNE fois, espeak-ng appele
    directement. Les memes phonemes que piper.exe, la premiere phrase prete en
    quelques dizaines de millisecondes, et « stop » qui coupe net."""

    @classmethod
    def setUpClass(cls):
        cls.ph = J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, "fr")
        cls.syn = J.Synthese(PIPER_VOIX, cls.ph)

    def test_les_phonemes_de_piper(self):
        """Releves sur piper.exe --debug : « Bonjour, monsieur. »"""
        phrases = self.ph.phrases("Bonjour, monsieur.")
        self.assertEqual(len(phrases), 1)
        self.assertEqual(self.syn.identifiants(phrases[0]),
                         [1, 0, 15, 0, 54, 0, 108, 0, 120, 0, 33, 0, 94, 0, 8, 0, 3, 0, 25, 0, 59, 0,
                          31, 0, 22, 0, 120, 0, 42, 0, 10, 0, 2])

    def test_une_phrase_a_la_fois_et_vite(self):
        sons = self.syn.phrases("Très bien. Minuteur de dix minutes, lancé. Autre chose ?", 0.95)
        t0 = time.time()
        premiere = next(sons)
        delai = time.time() - t0
        self.assertEqual(len(list(sons)), 2, "trois phrases, trois morceaux")
        self.assertGreater(len(premiere) / float(self.syn.frequence), 0.3)
        self.assertLess(delai, 1.0, "la premiere phrase doit etre prete tout de suite")
        self.assertGreater(int(np.max(np.abs(premiere))), 30000, "crete normalisee, comme piper")

    def test_la_bouche_parle_par_morceaux_et_se_tait(self):
        hp = FauxHautParleur()
        evts = []
        self.bouche = J.Bouche(self.syn, evts.append, hp)
        self.bouche.dire(7, "Bonjour. Tous les systèmes sont opérationnels.")
        self.assertEqual([e["evt"] for e in evts], ["debut", "fini"])
        self.assertFalse(evts[-1]["coupe"])
        self.assertGreater(len(hp.morceaux), 15, "joue par dixiemes de seconde")
        hp2 = FauxHautParleur(self, couper_apres=3)
        evts.clear()
        self.bouche = J.Bouche(self.syn, evts.append, hp2)
        self.bouche.dire(8, "Une tres longue phrase. " * 12)
        self.assertEqual({k: v for k, v in evts[-1].items() if k != "reste"}, {"evt": "fini", "id": 8, "coupe": True})
        self.assertLessEqual(len(hp2.morceaux), 4)
        # coupee au premier dixieme de seconde : tout reste a dire, depuis la phrase coupee
        self.assertEqual(evts[-1]["reste"], " ".join(["Une tres longue phrase."] * 12))

    def test_le_processus_de_la_voix(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        hp = FauxHautParleur()
        fil = threading.Thread(target=J.voix_enfant, args=(srv.getsockname()[1], "S3CRET", hp), daemon=True)
        fil.start()
        c, _ = srv.accept()
        srv.close()
        taille = int.from_bytes(c.recv(4), "big")
        self.assertEqual(c.recv(taille), b"S3CRET")
        J.envoyer(c, {"cmd": "charger", "bibliotheque": bibli_de_test(), "donnees": PIPER_DOSSIER,
                      "modele": PIPER_VOIX, "espeak": "fr"})
        self.assertEqual(J.recevoir(c)["evt"], "pret")
        J.envoyer(c, {"cmd": "dire", "id": 1, "texte": "Mode psychologue. Je vous écoute."})
        self.assertEqual(J.recevoir(c), {"evt": "debut", "id": 1})
        self.assertEqual(J.recevoir(c), {"evt": "fini", "id": 1, "coupe": False})
        J.envoyer(c, None)
        c.close()
        fil.join(5)
        self.assertFalse(fil.is_alive())

    def test_de_machi_tool_a_la_voix(self):
        """Machi Tool lance le processus de la voix, la voix se charge, une
        phrase part, et la fin revient -- c'est elle qui relance l'ecoute."""
        tmp = tempfile.mkdtemp()
        try:
            m = charger_module(tmp)
            m.DOSSIER = tmp
            script = os.path.join(tmp, "voix.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write("import sys\nsys.path.insert(0, %r)\nsys.path.insert(0, %r)\n"
                        "import jarvis as J\nfrom test_jarvis import FauxHautParleur\n"
                        "J.voix_enfant(sys.argv[1], sys.argv[2], FauxHautParleur())\n"
                        % (RACINE, os.path.dirname(os.path.abspath(__file__))))
            m._commande_voix = lambda port, secret: [sys.executable, script, str(port), secret]
            m.piper_pret = lambda cfg: {"nom": "essai", "bibliotheque": bibli_de_test(),
                                        "donnees": PIPER_DOSSIER, "modele": PIPER_VOIX,
                                        "frequence": 16000, "espeak": "fr", "locuteur": 0}
            self.assertTrue(m.demarrer_voix(m.CFG))
            fin = time.time() + 30
            while time.time() < fin and not m.voix_prete():
                time.sleep(0.05)
            self.assertTrue(m.voix_prete())
            dit = threading.Event()
            t0 = time.time()
            m.VOIX.dire("Bonjour. Tous les systèmes sont opérationnels.", dit.set)
            self.assertTrue(dit.wait(20))
            self.assertLess(time.time() - t0, 5)
            m.arreter_voix()
            self.assertFalse(m.voix_prete())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ======================================================================
#  LA DOUBLE TRANSMISSION : ON LUI COUPE LA PAROLE
# ======================================================================

def _rir(rng, rt60, d0_ms=6):
    """Une piece : le son direct, puis une queue qui decroit de 60 dB en rt60."""
    n = int(16000 * min(1.2, rt60 * 1.3))
    t = np.arange(n) / 16000.0
    h = rng.standard_normal(n) * np.exp(-6.9 * t / rt60) * 0.35
    d0 = int(d0_ms * 16)
    h[:d0] = 0
    h[d0] += 1.0
    return h / np.sqrt((h ** 2).sum())


def _conv(a, b):
    n = len(a) + len(b) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, N) * np.fft.rfft(b, N), N)[:n]


class PieceSimulee:
    """Des haut-parleurs, une piece, un micro : ce que joue Jarvis revient,
    en retard, reverbere, plus ou moins fort -- et la personne parle, ou pas."""

    def __init__(self, graine, latence, rt60, echo_db):
        self.rng = np.random.default_rng(graine)
        self.h = _rir(self.rng, rt60)
        self.lat = int(latence * 16000)
        self.echo_db = echo_db
        self.t = 100.0                      # l'horloge : elle ne recule jamais

    def signaux(self, ref, voix=None, debut_voix=1.5, ser_db=6.0, musique=None, volume_db=0.0, en_plus=None):
        """(reference, micro, voix seule) en float, et l'instant ou la voix commence.
        `volume_db` : le volume monte -- l'echo grossit, pas la reference (le
        loopback est pris avant le volume). `en_plus` : un autre bruit de la
        piece, deja au micro (un clavier)."""
        ref = ref.astype(np.float64)
        if musique is not None:
            ref = ref + musique[:len(ref)]
        db = self.echo_db + volume_db
        echo = _conv(ref, self.h)
        echo = echo / max(np.sqrt(np.mean(echo[:len(ref)] ** 2)), 1e-9) * 10 ** (db / 20)
        mic = np.zeros(len(ref) + self.lat + len(self.h))
        mic[self.lat:self.lat + len(echo)] += echo
        seule = np.zeros(len(mic))
        if voix is not None:
            v = voix / 32768.0
            v = v / np.sqrt(np.mean(v[np.abs(v) > 0.01] ** 2)) * 10 ** ((db + ser_db) / 20)
            s = int(debut_voix * 16000)
            e = min(len(mic), s + len(v))
            seule[s:e] = v[:e - s]
            mic += seule
        if en_plus is not None:
            n = min(len(mic), len(en_plus))
            mic[:n] += en_plus[:n]
        mic += self.rng.standard_normal(len(mic)) * 10 ** (-62 / 20)
        return ref, mic, seule, (debut_voix if voix is not None else 0.0)

    def passage(self, c, ref, **kw):
        """Joue une reponse ; rend l'instant de la coupure, compte depuis le debut
        de la voix (depuis le debut tout court sans voix), ou None. L'oreille
        desarme quand la voix dit « fini » : un quart de seconde apres son
        dernier son (le silence de fin de phrase, et le son qui s'ecoule)."""
        ref, mic, _, t_voix = self.signaux(ref, **kw)
        self.t += 30.0
        c.armer(self.t)
        coupe = None
        for i in range(0, min(len(mic) - J.TRAME, len(ref) + 4000), J.TRAME):
            t_fin = self.t + (i + J.TRAME) / 16000.0
            bloc = ref[i:i + J.TRAME]
            if len(bloc) == J.TRAME:
                c.reference(bloc.astype(np.float32), t_fin + self.rng.uniform(-0.01, 0.01))
            if c.micro(mic[i:i + J.TRAME].astype(np.float32), t_fin):
                coupe = (t_fin - self.t) - t_voix
                break
        c.desarmer()
        return coupe


def frappe_de_test(n, rng, h, crete_db, toc_hz=300.0):
    """Quelqu'un tape pendant qu'il parle : 4 a 9 touches par seconde, appui et
    relachement, des pauses ; chaque touche un claquement clair et le « toc » du
    clavier -- LE MEME pour toutes ses touches, a 5 % pres --, dans la piece."""
    x = np.zeros(n)
    t = np.arange(400) / 16000.0
    f = np.fft.rfftfreq(400, 1 / 16000.0)
    crete, cadence, instant = 10 ** (crete_db / 20), rng.uniform(4, 9), rng.uniform(0.0, 0.3)
    while instant < n / 16000.0 - 0.05:
        for dt, force in ((0.0, 1.0), (rng.uniform(0.04, 0.11), rng.uniform(0.4, 0.8))):
            i = int((instant + dt) * 16000)
            if i >= n:
                break
            b = rng.standard_normal(400) * np.exp(-t / rng.uniform(0.002, 0.008))
            b = np.fft.irfft(np.fft.rfft(b) * (f > rng.uniform(600, 2000)), 400)
            b += np.sin(2 * np.pi * toc_hz * rng.uniform(0.95, 1.05) * t) * np.exp(-t / 0.015) * np.max(np.abs(b))
            b *= crete * force / max(np.max(np.abs(b)), 1e-9)
            e = min(n, i + 400)
            x[i:e] += b[:e - i]
        instant += rng.gamma(2.0, 1.0 / (2.0 * cadence))
        if rng.random() < 0.08:
            instant += rng.uniform(0.3, 1.2)
    return _conv(x, h)[:n]


class FauxLoopback:
    erreur = None

    def __init__(self):
        from collections import deque
        self.blocs, self.demarre, self.arrete = deque(), 0, 0

    def demarrer(self):
        self.demarre += 1

    def arreter(self):
        self.arrete += 1


def musique_de_test(n, graine=9):
    """Des accords qui changent toutes les demi-secondes, et une percussion
    tous les quarts : ce qui passe dans les haut-parleurs pendant qu'il parle."""
    rng = np.random.default_rng(graine)
    t = np.arange(n) / 16000.0
    accords = ((220, 277, 330), (196, 247, 294), (175, 220, 262), (247, 311, 370))
    m = np.zeros(n)
    for k in range(int(n / 8000) + 1):
        sel = (t >= k * 0.5) & (t < (k + 1) * 0.5)
        for f in accords[k % len(accords)]:
            m[sel] += np.sin(2 * np.pi * f * t[sel])
    for k in range(int(n / 4000) + 1):
        a = k * 4000
        b = min(n, a + 1600)
        m[a:b] += rng.standard_normal(b - a) * np.exp(-np.arange(b - a) / 300.0) * 2.0
    return m / np.sqrt(np.mean(m ** 2)) * 0.05


@unittest.skipUnless(NUMPY and ESPEAK, "numpy ou espeak-ng absents")
class DoubleTransmission(unittest.TestCase):
    """« Une discussion a double transmission, comme les modeles de ChatGPT,
    pour pouvoir couper la parole. » Jarvis ne se coupe pas sur sa propre voix
    revenue par les haut-parleurs, ni sur la musique ; la personne qui parle
    par-dessus le coupe -- dans quatre pieces : proche et seche, loin et
    reverberante, discrete, forte."""

    PIECES = ((1, 0.03, 0.25, -24.0), (2, 0.12, 0.6, -14.0), (3, 0.07, 0.4, -30.0), (4, 0.15, 0.75, -18.0))

    @classmethod
    def setUpClass(cls):
        cls.jarvis = [dire(t, voix="en-gb+m3", vitesse=165) / 32768.0 for t in (
            "Good evening. All systems are operational, and your calendar is clear for the rest of the day.",
            "The download is at sixty percent. At this rate it should finish in about four minutes.",
            "Certainly. A binary search halves the list at every step, so a million items take twenty steps.",
            "I'm afraid the printer is offline again. It may simply need to be switched off and on.")]
        cls.voix = [dire(t, voix=v) for t, v in (
            ("Attends, stop, mets plutôt un minuteur de dix minutes.", "fr+f3"),
            ("No, wait, I meant the other printer upstairs.", "en-us+f2"),
            ("Non, je voulais dire la lumière du salon.", "fr+m1"))]

    def test_sa_propre_voix_ne_le_coupe_pas(self):
        for graine, lat, rt, db in self.PIECES:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            p.passage(c, self.jarvis[0])          # la premiere reponse : il apprend la piece
            self.assertTrue(c.pret(), "il a appris la piece %d" % graine)
            for ref in self.jarvis[1:]:
                self.assertIsNone(p.passage(c, ref), "coupe sur sa propre voix (piece %d)" % graine)

    def test_parler_par_dessus_le_coupe(self):
        """A 10 dB au-dessus de l'echo : on hausse le ton pour couper quelqu'un.
        Plus bas, la simulation en entend huit sur dix -- et « Jarvis ! » reste la."""
        for graine, lat, rt, db in self.PIECES:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            p.passage(c, self.jarvis[0])
            for k, voix in enumerate(self.voix):
                d = p.passage(c, self.jarvis[1 + k], voix=voix, ser_db=10.0)
                self.assertIsNotNone(d, "pas coupe (piece %d, voix %d)" % (graine, k))
                self.assertTrue(0.0 <= d < 1.5, "coupe a %.2f s (piece %d, voix %d)" % (d, graine, k))

    def test_la_musique_ne_le_coupe_pas(self):
        """Elle est dans la reference (le loopback prend TOUT ce qui sort) :
        elle revient dans le micro, et elle est expliquee."""
        for graine, lat, rt, db in self.PIECES[:2]:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            m = musique_de_test(16000 * 12, graine)
            p.passage(c, self.jarvis[0], musique=m)
            for ref in self.jarvis[1:]:
                self.assertIsNone(p.passage(c, ref, musique=m), "coupe sur la musique (piece %d)" % graine)

    def test_au_casque_il_coupe_vite(self):
        p, c = PieceSimulee(5, 0.05, 0.3, -95.0), J.Coupure()
        p.passage(c, self.jarvis[0])
        d = p.passage(c, self.jarvis[1], voix=self.voix[0], ser_db=70.0)
        self.assertIsNotNone(d)
        self.assertLess(d, 0.6, "sans echo, la voix se voit tout de suite")

    def test_l_oreille_coupe_et_ecoute(self):
        """De bout en bout dans l'oreille : Jarvis parle (« parole »), la
        reference arrive par le loopback, la personne parle par-dessus --
        « coupure », puis sa phrase part comme une autre."""
        sorties, horloge = [], {"t": 500.0}
        lb = FauxLoopback()
        o = J.Oreille(FaussesEmpreintes(), sorties.append, lambda g: None, lb, horloge=lambda: horloge["t"])
        o.niveau_vu = float("inf")
        p = PieceSimulee(2, 0.08, 0.5, -20.0)

        def jouer(ref, voix=None):
            ref, mic, seule, _ = p.signaux(ref, voix=voix, ser_db=8.0)
            o.commande({"cmd": "parole", "actif": True})
            coupe_a = None
            for i in range(0, len(mic) - J.TRAME, J.TRAME):
                horloge["t"] += J.TRAME / 16000.0
                if coupe_a is None:
                    bloc = ref[i:i + J.TRAME]
                    if len(bloc) == J.TRAME:
                        lb.blocs.append((horloge["t"], bloc.astype(np.float32)))
                    x = mic[i:i + J.TRAME]
                else:
                    # il s'est tu : il ne reste que la personne et la piece
                    x = seule[i:i + J.TRAME] + p.rng.standard_normal(J.TRAME) * 10 ** (-62 / 20)
                o.trame(np.clip(x * 32768, -32768, 32767).astype(np.int16))
                if coupe_a is None and any(e["evt"] == "coupure" for e in sorties):
                    coupe_a = i
            for _ in range(30):                   # puis le calme : la phrase se termine
                horloge["t"] += J.TRAME / 16000.0
                o.trame((p.rng.standard_normal(J.TRAME) * 20).astype(np.int16))
            o.commande({"cmd": "parole", "actif": False})
            return coupe_a
        self.assertIsNone(jouer(self.jarvis[0]), "la premiere reponse : il apprend, il ne coupe pas")
        self.assertIsNone(jouer(self.jarvis[1]))
        self.assertEqual(sorties, [], "sa propre voix ne fait rien sortir")
        self.assertIsNotNone(jouer(self.jarvis[2], voix=self.voix[1]))
        evts = [e["evt"] for e in sorties]
        self.assertEqual(evts, ["coupure", "phrase"])
        wav = base64.b64decode(sorties[1]["wav"])
        with wave.open(io.BytesIO(wav)) as w:
            self.assertGreater(w.getnframes() / 16000.0, 1.5, "la phrase de la personne, entiere")
        self.assertGreaterEqual(lb.demarre, 3)
        self.assertGreaterEqual(lb.arrete, 3, "la reference se referme apres chaque reponse")
        self.assertFalse(o.parole)

    def test_il_apprend_la_piece_et_pas_le_bruit(self):
        """Ce qu'il predit, c'est l'echo de la piece : le gain et le retard. La
        toute premiere trame apprise etait un debut de mot presque muet face au
        bruit du micro -- elle donnait a la prise zero un poids de 3000, et deux
        reponses plus tard il predisait l'echo cent fois trop fort, a retard nul."""
        for graine, lat, rt, db in self.PIECES:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            # comme Kokoro : la reponse commence par un souffle presque muet,
            # bien sous le bruit du micro
            souffle = np.random.default_rng(graine).standard_normal(1600) * 10 ** (-110 / 20)
            p.passage(c, np.concatenate([souffle, self.jarvis[0]]))
            p.passage(c, self.jarvis[1])
            vrai = 10 ** (db / 10) / np.mean(self.jarvis[1] ** 2)
            gain = float(np.median(c.w.sum(axis=1)))
            self.assertTrue(vrai / 2 < gain < vrai * 2, "piece %d : gain %.3g, vrai %.3g" % (graine, gain, vrai))
            prise = float(np.median(np.argmax(c.w, axis=1)))
            self.assertTrue(lat / 0.02 - 1 <= prise <= lat / 0.02 + 3,
                            "piece %d : l'echo a %.0f ms, pas a la prise %.0f" % (graine, lat * 1000, prise))

    def test_on_monte_le_volume_entre_deux_reponses(self):
        """Le loopback est pris avant le volume : 10 dB de plus, seul l'echo
        grossit. Il le mesure au debut de la reponse -- et on le coupe encore."""
        for graine, lat, rt, db in self.PIECES:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            p.passage(c, self.jarvis[0])
            self.assertIsNone(p.passage(c, self.jarvis[1]))
            for ref in self.jarvis[2:]:
                self.assertIsNone(p.passage(c, ref, volume_db=10.0), "piece %d, +10 dB" % graine)
            d = p.passage(c, self.jarvis[1], volume_db=10.0, voix=self.voix[1], ser_db=10.0)
            self.assertIsNotNone(d, "piece %d : plus fort, on le coupe encore" % graine)

    def test_taper_au_clavier_ne_le_coupe_pas(self):
        """Un clavier, l'echo ne l'explique pas non plus. Mais il ne VIBRE pas --
        son « toc » s'eteint en quelques millisecondes, une voix tient sa
        hauteur -- et il est plus bas qu'une voix qui coupe la parole."""
        for graine, lat, rt, db in self.PIECES:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            p.passage(c, self.jarvis[0])
            for k, ref in enumerate(self.jarvis[1:]):
                touches = frappe_de_test(len(ref) + p.lat + len(p.h), np.random.default_rng(10 * graine + k),
                                         p.h, db + 3.0, toc_hz=180.0 + 60 * k)
                self.assertIsNone(p.passage(c, ref, en_plus=touches), "piece %d, reponse %d" % (graine, k + 1))
            # et quelqu'un qui parle en tapant le coupe toujours
            touches = frappe_de_test(len(self.jarvis[1]) + p.lat + len(p.h), np.random.default_rng(graine),
                                     p.h, db + 3.0)
            self.assertIsNotNone(p.passage(c, self.jarvis[1], en_plus=touches, voix=self.voix[0], ser_db=10.0))

    def test_une_voix_tient_sa_hauteur(self):
        c = J.Coupure()
        t = np.arange(640) / 16000.0
        voyelle = sum(np.sin(2 * np.pi * 125 * k * t) / k for k in range(1, 12))
        v, lag = c._voisement(voyelle)
        self.assertGreater(v, 0.8)
        self.assertEqual(round(16000 / lag), 125)
        clic = np.zeros(640)
        clic[100:140] = np.random.default_rng(1).standard_normal(40)
        self.assertLess(c._voisement(clic)[0], 0.5, "un claquement n'a pas de hauteur")
        # quatre trames de suite a la meme hauteur ; une qui saute repart de un
        c.nette = voyelle
        for _ in range(4):
            c._suivre_la_hauteur(True)
        self.assertEqual((c.suite_voisee, c.voisee_max), (4, 4))
        c.nette = sum(np.sin(2 * np.pi * 190 * k * t) / k for k in range(1, 8))
        c._suivre_la_hauteur(True)
        self.assertEqual(c.suite_voisee, 1)

    def test_coupe_pour_rien_il_apprend_ce_qu_il_avait_mis_de_cote(self):
        p, c = PieceSimulee(2, 0.12, 0.6, -14.0), J.Coupure()
        p.passage(c, self.jarvis[0])
        ref, mic, _, _ = p.signaux(self.jarvis[1])
        p.t += 30.0
        c.armer(p.t)
        for i in range(0, 1280 * 30, 1280):
            c.reference(ref[i:i + 1280].astype(np.float32), p.t + (i + 1280) / 16000.0)
            c.micro(mic[i:i + 1280].astype(np.float32), p.t + (i + 1280) / 16000.0)
        c.desarmer(garder=False)                   # « coupe » : ce qui attendait est mis de cote
        mis_de_cote, avant = len(c.de_cote), c.appris
        self.assertGreater(mis_de_cote, 50)
        c.fausse_coupure()                         # personne n'a parle : c'etait de l'echo
        self.assertEqual(c.appris - avant, mis_de_cote, "tout ce qui etait de cote s'apprend")
        self.assertEqual(c.de_cote, [])
        c.armer(p.t + 60)
        self.assertEqual(c.de_cote, [], "une nouvelle reponse oublie ce qui restait de cote")

    def test_l_oreille_dit_quand_personne_n_a_parle_apres_la_coupure(self):
        sorties = []

        class CoupureQuiCoupe:
            def __init__(s):
                s.appels = []

            def armer(s, t):
                s.appels.append("armer")

            def desarmer(s, garder=True):
                s.appels.append("desarmer")

            def reference(s, x, t):
                pass

            def micro(s, x, t):
                return True

            def pret(s):
                return True

            def fausse_coupure(s):
                s.appels.append("fausse_coupure")
        o = J.Oreille(FaussesEmpreintes(), sorties.append, lambda g: None, FauxLoopback())
        o.niveau_vu = float("inf")
        o.coupure = CoupureQuiCoupe()
        o.commande({"cmd": "parole", "actif": True})
        silence = np.zeros(J.TRAME, dtype=np.int16)
        o.trame(silence)
        self.assertEqual(sorties, [{"evt": "coupure"}])
        for _ in range(int(2.0 / J.TRAME_S)):
            o.trame(silence)
        self.assertEqual(sorties[-1], {"evt": "vide", "apres_coupure": True},
                         "une seconde et demie sans personne : c'etait pour rien")
        self.assertIn("fausse_coupure", o.coupure.appels, "et ce qui etait de cote s'apprend")
        o.coupure.appels.clear()
        o.commande({"cmd": "fausse_coupure"})     # Machi Tool : la phrase n'avait pas de mots
        self.assertEqual(o.coupure.appels, ["fausse_coupure"])
        o.commande({"cmd": "ecouter", "attente": 0.5})
        for _ in range(int(1.0 / J.TRAME_S)):
            o.trame(silence)
        self.assertEqual(sorties[-1], {"evt": "vide"}, "une ecoute ordinaire n'est pas une coupure")

    def test_sans_reference_seul_le_mot_d_eveil_le_coupe(self):
        sorties = []
        o = J.Oreille(FaussesEmpreintes(), sorties.append, lambda g: None, None)
        o.niveau_vu = float("inf")
        o.commande({"cmd": "parole", "actif": True})
        self.assertFalse(o.parole)
        self.assertEqual(o.etat_coupure(), "sans reference")


KOKORO_DOSSIER = os.environ.get("JARVIS_KOKORO_DOSSIER", "")   # kokoro-v1.0.onnx et voices-v1.0.bin
KOKORO = bool(NUMPY and ONNX and PIPER_DOSSIER and bibli_de_test()
              and all(os.path.isfile(os.path.join(KOKORO_DOSSIER, n)) for n in (J.KOKORO_MODELE, J.KOKORO_VOIX)))


def hauteur_mediane(son, fr):
    """La hauteur mediane d'une voix, par autocorrelation sur 40 ms (70-400 Hz)."""
    x = son.astype(np.float64) / 32768
    n, hauteurs = int(0.04 * fr), []
    for i in range(0, len(x) - n, n // 2):
        seg = x[i:i + n] - np.mean(x[i:i + n])
        if np.sqrt(np.mean(seg ** 2)) < 0.05:
            continue
        ac = np.correlate(seg, seg, "full")[n - 1:]
        lo, hi = int(fr / 400), int(fr / 70)
        l_ = lo + int(np.argmax(ac[lo:hi]))
        if ac[l_] > 0.4 * ac[0]:
            hauteurs.append(fr / l_)
    return float(np.median(hauteurs)) if hauteurs else 0.0


@unittest.skipUnless(KOKORO, "JARVIS_KOKORO_DOSSIER / JARVIS_PIPER_DOSSIER absents")
class VoixFrancaise(unittest.TestCase):
    """« Can you have a french voice for jarvis ? » : Kokoro en francais, une
    voix d'homme melangee a partir de Siwis -- et le meme modele que l'anglais."""

    @classmethod
    def setUpClass(cls):
        cls.fr = J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, J.KOKORO_ESPEAK_FR)
        cls.modele = os.path.join(KOKORO_DOSSIER, J.KOKORO_MODELE)
        cls.voix = os.path.join(KOKORO_DOSSIER, J.KOKORO_VOIX)

    def test_les_melanges_existent(self):
        with np.load(self.voix) as pack:
            for cle, entree in J.VOIX_KOKORO_FR.items():
                for nom in entree["melange"]:
                    self.assertIn(nom, pack.files, cle)

    def test_les_phonemes_francais(self):
        p = J.phonemes_kokoro(self.fr.phrases("Bonjour. Que puis-je faire pour vous ?")[0])
        self.assertIn("ʁ", p)
        self.assertTrue(all(c in J.KOKORO_VOCAB for c in p), p)

    def test_un_homme_et_le_meme_modele(self):
        en = J.SyntheseKokoro(self.modele, self.voix, J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, "en"),
                              "jarvis", 2)
        homme = J.SyntheseKokoro(self.modele, self.voix, self.fr, "fr_jarvis", 2, "fr")
        femme = J.SyntheseKokoro(self.modele, self.voix, self.fr, "fr_siwis", 2, "fr")
        self.assertIs(homme.session, en.session, "un seul modele de 310 Mo pour les deux langues")
        self.assertEqual(homme.langue, "fr")
        texte = "Bonjour. Tous les systèmes sont opérationnels. Que puis-je faire pour vous ?"
        h = hauteur_mediane(np.concatenate(list(homme.phrases(texte, 1.0))), J.KOKORO_FREQ)
        f = hauteur_mediane(np.concatenate(list(femme.phrases(texte, 1.0))), J.KOKORO_FREQ)
        self.assertLess(h, 160, "sa voix francaise est une voix d'homme (%.0f Hz)" % h)
        self.assertGreater(f, 190, "Siwis seule, une voix de femme (%.0f Hz)" % f)


@unittest.skipUnless(KOKORO, "JARVIS_KOKORO_DOSSIER / JARVIS_PIPER_DOSSIER absents")
class VoixAnglaise(unittest.TestCase):
    """« The voice is very bad », « it's robotic as well » : la voix anglaise de
    Jarvis, Kokoro, en memoire, avec l'espeak-ng de Piper -- et les deux langues
    dans le meme processus sans se voler leur voix."""

    @classmethod
    def setUpClass(cls):
        cls.en = J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, J.KOKORO_ESPEAK)
        cls.syn = J.SyntheseKokoro(os.path.join(KOKORO_DOSSIER, J.KOKORO_MODELE),
                                   os.path.join(KOKORO_DOSSIER, J.KOKORO_VOIX), cls.en, "jarvis", 2)

    def test_les_phonemes_anglais(self):
        p = J.phonemes_kokoro(self.en.phrases("Good evening.")[0])
        self.assertEqual(p, "ɡˈʊd ˈiːvnɪŋ.")
        self.assertTrue(all(c in J.KOKORO_VOCAB for c in p), "rien ne se perd en route")

    def test_il_parle_anglais_une_phrase_a_la_fois(self):
        sons = list(self.syn.phrases("Good evening. All systems are operational.", 0.95))
        self.assertEqual(len(sons), 2, "deux phrases, deux morceaux")
        for s in sons:
            d = len(s) / float(J.KOKORO_FREQ)
            self.assertTrue(0.4 < d < 6, d)
            self.assertGreater(float(np.sqrt(np.mean(s.astype(np.float64) ** 2))), 1500, "il parle, il ne souffle pas")
        self.assertGreater(int(np.max(np.abs(sons[0]))), 30000, "crete normalisee, comme piper")

    def test_deux_langues_dans_un_processus(self):
        """espeak-ng n'a qu'une voix par processus : le francais du mode psy
        et l'anglais de Jarvis ne doivent pas se voler la leur."""
        fr = J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, "fr")
        avant = self.en.phrases("Hello there.")
        bonjour = fr.phrases("Bonjour.")
        apres = self.en.phrases("Hello there.")
        self.assertEqual(avant, apres, "l'anglais reste anglais apres le francais")
        self.assertIn("ʁ", "".join(bonjour[0]), "le francais reste francais")
        self.assertNotEqual(avant, fr.phrases("Hello there."))

    @unittest.skipUnless(PIPER, "JARVIS_PIPER_VOIX absent")
    def test_une_bouche_deux_voix(self):
        piper = J.Synthese(PIPER_VOIX, J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, "fr"))
        hp, evts = FauxHautParleur(), []
        b = J.Bouche({"en": self.syn, "fr": piper}, evts.append, hp)
        b.dire(1, "Good evening.", 1.0, "en")
        self.assertEqual(hp.frequence, J.KOKORO_FREQ)
        b.dire(2, "Bonsoir.", 1.0, "fr")
        self.assertEqual(hp.frequence, piper.frequence)
        self.assertEqual([e["evt"] for e in evts], ["debut", "fini", "debut", "fini"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
