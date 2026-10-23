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
import unicodedata
import urllib.error
import urllib.request
import urllib.parse
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

    def test_mets_ecrit_mais(self):
        """« Mets un minuteur de dix minutes » transcrit « Mais un minuteur... » :
        la commande partait chez BrainDebugger au lieu de se faire ici."""
        a = J.comprendre("Mais un minuteur de 10 minutes.")
        self.assertEqual((a["action"], a["secondes"]), ("minuteur", 600))
        self.assertEqual(self.action("Mais la lumière en bleu."), "lumiere_couleur")
        self.assertEqual(self.action("Met la lumière en rouge"), "lumiere_couleur")
        self.assertEqual(self.action("Mes la lumière en vert"), "lumiere_couleur")
        # un vrai « mais » reste une phrase pour le compagnon
        self.assertIsNone(J.comprendre("Mais la lumière est déjà allumée ?"))
        self.assertIsNone(J.comprendre("Mais non"))
        self.assertIsNone(J.comprendre("Mais moi je veux dormir"))
        self.assertIsNone(J.comprendre("Mes enfants sont là"))

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

    def test_l_au_revoir(self):
        for t, mot in (("Salut !", "salut"), ("Au revoir.", "au revoir"), ("Au revoir Jarvis", "au revoir"),
                       ("Bonne nuit", "bonne nuit"), ("à plus", "a plus"), ("merci, au revoir", "au revoir"),
                       ("Goodbye, Jarvis", "goodbye"), ("See you later", "see you later"), ("à demain", "a demain")):
            self.assertEqual(J.adieu(t), mot, t)
        for t in ("salut ça va ?", "salut, tu peux allumer la lumière ?", "au revoir à tout le monde dans la vidéo",
                  "comment on dit au revoir en japonais"):
            self.assertIsNone(J.adieu(t), t)

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
                         ("Mes notes.", ""), ("Mets-toi en mode psychologue s'il te plaît", ""),
                         ("Psychologue, j'ai mal dormi cette nuit.", "j'ai mal dormi cette nuit."),
                         ("Note que j'ai pris mon traitement à 9h.", "Note que j'ai pris mon traitement à 9h."),
                         ("Prends une note : appeler le médecin", "Prends une note : appeler le médecin")):
            self.assertEqual(J.changement_de_mode(t), ("psy", reste), t)

    def test_retour_a_jarvis(self):
        # « Qu'il puisse se quitter facilement en disant "retourne au mode
        # jarvis" ou "pars du mode psychologue". »
        for t in ("mode Jarvis", "Quitte le mode psy.", "reviens en mode normal", "sors du mode psychologue",
                  "Retourne au mode Jarvis.", "Pars du mode psychologue.", "ok, retourne au mode Jarvis s'il te plaît",
                  "sors du psy", "plus de psy", "stop le mode psy", "arrête le psychologue", "reviens à Jarvis",
                  "je veux parler à Jarvis", "redeviens normal", "fin du mode psy", "leave therapist mode",
                  "go back to Jarvis", "no more therapy"):
            self.assertEqual(J.changement_de_mode(t), ("jarvis", ""), t)

    def test_pas_de_bascule_par_hasard(self):
        # « Il faut faire gaffe que le mode psychologue n'arrive pas trop
        # facilement » : parler DU psy, de psychologie ou de notes n'y fait
        # pas passer -- le demander, si.
        for t in ("je note que ça va mieux", "les notes de cours", "j'ai vu mon psy hier",
                  "c'est un truc de psychologue ça", "combien font 12 fois 12",
                  "psychologie de la foule, c'est quoi ?", "le psy m'a dit de dormir plus",
                  "la psy c'est cher", "psy trance, tu connais ?", "therapy is expensive",
                  "therapist said I should rest", "notes de frais à rendre demain", "noter les courses",
                  "note bien la date", "mode avion",
                  # « Noté. » est un acquittement ; « Normal. », une reponse
                  "Noté.", "Notes.", "Normal.", "Bon, normal.", "Psy, au revoir", "Psychologue... laisse tomber"):
            self.assertIsNone(J.changement_de_mode(t), t)

    def test_nier_le_psy_n_y_fait_pas_entrer(self):
        # « mode psy off » y faisait ENTRER, et « off » partait au psychologue
        for t in ("mode psy off", "mode psy arrête", "mode psychologue désactivé", "mode psychologue, non !",
                  "therapist mode off", "je veux plus parler au psy", "je veux pas le psy", "pas de psy",
                  "non pas le psy", "désactive le mode psy", "coupe le mode psy", "change de mode",
                  "je veux changer de mode", "mode majordome", "je t'ai pas demandé le psy",
                  "Ça va, j'ai pas besoin d'un psy.", "arrête d'être psy", "Stop being a therapist.",
                  "I don't want therapy.", "comment on sort du mode psy ?", "mode normal", "back to normal"):
            self.assertEqual(J.changement_de_mode(t), ("jarvis", ""), t)
        for t in ("je voulais pas le dire au psy", "la psy c'est cher", "je veux pas en parler"):
            self.assertIsNone(J.changement_de_mode(t), t)

    def test_va_dormir_n_eteint_plus_jarvis(self):
        # « va dormir » : il retourne attendre son nom ; « arrete d'ecouter » :
        # la, il n'ecoute plus du tout
        for t in ("va dormir", "Mets-toi en veille.", "dors", "go to sleep"):
            self.assertEqual(J.comprendre(t), {"action": "fin"}, t)
        for t in ("arrête d'écouter", "Désactive-toi.", "coupe le micro", "stop listening", "éteins-toi"):
            self.assertEqual(J.comprendre(t), {"action": "dormir"}, t)

    def test_plus_de_facons_de_partir(self):
        for t in ("pas maintenant", "plus tard", "Fin.", "On s'arrête là.", "Arrête-toi.", "Thanks.",
                  "Merci beaucoup, au revoir."):
            self.assertTrue(J.fin_de_conversation(t), t)
        for t in ("Stop, stop, stop !", "stoppe", "Arrête-toi."):
            self.assertTrue(J.renvoi(t), t)
        for t in ("ok ça marche", "merci c'est parfait", "c'est gentil", "Thanks a lot."):
            self.assertTrue(J.acquittement(t), t)
        self.assertEqual(J.adieu("Merci beaucoup, au revoir."), "au revoir")
        self.assertEqual(J.adieu("Et bonne nuit."), "bonne nuit")


class SortieDuPsy(unittest.TestCase):
    """« Il est rentre en mode psychologue et j'ai pas reussi a en sortir. »"""

    def test_on_en_sort_en_l_appelant(self):
        for t in ("Reviens en mode Jarvis.", "Passe en mode Jarvis.", "Mode Jarvis.", "Retour à Jarvis.",
                  "Je veux parler à Jarvis.", "Go back to Jarvis.", "Switch to Jarvis mode.", "Jarvis, reviens.",
                  "Reviens en mode Travis.", "Jarvis !", "Jarvis ?", "Jarvis.", "Hey Jarvis.", "OK Jarvis.",
                  "Hé Jarvis !", "Jarvis ? Re !", "Reviens.", "C'est Jarvis que je veux.",
                  "Je veux parler à Jarvis, pas au psy.", "Jarvis, t'es là ?", "Mode majordome.",
                  "Je veux plus du psy.", "Pas le psy.", "Change de mode."):
            self.assertEqual(J.sortie_du_psy(t), "retour", t)

    def test_arrete_tais_toi(self):
        for t in ("Arrête.", "Arrête, Jarvis.", "Tais-toi.", "Chut.", "Ça suffit.", "Stop, stop, stop !",
                  "On arrête là.", "Quitte.", "Fin.", "Enough.", "That's enough.", "Stop it.", "Dégage."):
            self.assertEqual(J.sortie_du_psy(t), "stop", t)

    def test_le_nom_puis_une_demande(self):
        self.assertEqual(J.sortie_du_psy("Jarvis, quelle heure est-il ?"), "appel")
        self.assertEqual(J.sortie_du_psy("Hey Jarvis, mets de la musique."), "appel")

    def test_ce_qui_reste_au_psychologue(self):
        for t in ("J'ai galéré à allumer Jarvis ce matin.", "Je me suis énervé contre Jarvis tout à l'heure.",
                  "J'arrête pas de penser à elle.", "Je veux arrêter de fumer.", "Je sais pas comment sortir de là.",
                  "Comment je sors de là ?", "J'ai envie que tout s'arrête.", "Je veux que ça s'arrête.",
                  "Je veux en finir.", "I can't do this anymore.", "Stop, attends, laisse-moi réfléchir.",
                  "Arrête de me poser des questions.", "Non, c'est pas ça.", "C'est pas ce que je voulais dire.",
                  "C'est pas ce que je voulais.", "Je ne veux pas en parler.", "Tais-toi, je sais.",
                  "Normal.", "Normale, je dirais.", "Ça va, normal.", "Bon, normal.", "Mode survie aujourd'hui.",
                  "Fin de journée difficile.", "Mon père est psychologue.", "Jarvis m'énerve.",
                  "Quelle heure est-il, Jarvis ?"):
            self.assertIsNone(J.sortie_du_psy(t), t)

    def test_pas_ce_que_je_voulais_juste_apres_la_bascule(self):
        self.assertEqual(J.sortie_du_psy("C'est pas ce que je voulais.", debut_de_seance=True), "retour")
        self.assertIsNone(J.sortie_du_psy("C'est pas ce que je voulais."))


@unittest.skipUnless(NUMPY, "numpy absent")
class PresqueReconnu(unittest.TestCase):
    """« Il semble avoir oublie mon Jarvis » : quand le mot appris passe pres du
    seuil sans le franchir, l'oreille le dit -- un nombre, rien d'autre."""

    def test_presque_puis_rien_pendant_trois_secondes(self):
        sorties = []
        o = J.Oreille(object(), sorties.append, lambda g: None)
        o.niveau_vu = float("inf")
        o.det.seuil = 0.05
        o.det.trame = lambda x, chercher=True: None
        for i, d in enumerate((0.2, 0.07, 0.07, 0.07)):
            o.det.n = 100 + i
            o.det.plus_proche, o.det.compare_n = d, o.det.n
            o.trame(np.zeros(J.TRAME, dtype=np.int16))
        presque = [e for e in sorties if e["evt"] == "presque"]
        self.assertEqual(len(presque), 1, "une fois, pas a chaque trame")
        self.assertEqual(presque[0], {"evt": "presque", "distance": 0.07, "seuil": 0.05})
        self.assertEqual(set(presque[0]), {"evt", "distance", "seuil"}, "un nombre, ni son ni texte")


class SesMains(unittest.TestCase):
    """Ce que Jarvis peut faire sur le PC, sans Windows : le code, les
    chemins, les listes, la recherche, les dossiers."""

    def test_le_code_dit_comme_on_veut(self):
        sel = "ab" * 16
        e = J.empreinte_code("4815", sel)
        self.assertNotIn("4815", e)
        for dit in ("4815", "4 8 1 5", "Quatre, huit, un, cinq.", "quatre-huit-un-cinq", "4815."):
            self.assertTrue(J.code_juste(dit, sel, e), dit)
        for dit in ("4816", "", "quatre huit un", "48150"):
            self.assertFalse(J.code_juste(dit, sel, e), dit)
        self.assertTrue(J.code_juste("Abricot !", sel, J.empreinte_code("abricot", sel)))

    def test_les_chemins(self):
        b = {"home": os.sep + "maison", "documents": os.path.join(os.sep + "maison", "Documents"),
             "downloads": os.path.join(os.sep + "maison", "Downloads")}
        self.assertEqual(J.resoudre_chemin("Documents", b), b["documents"])
        self.assertEqual(J.resoudre_chemin("téléchargements", b), b["downloads"])
        self.assertEqual(J.resoudre_chemin("Documents" + os.sep + "Projets", b), os.path.join(b["documents"], "Projets"))
        self.assertEqual(J.resoudre_chemin("~", b), b["home"])
        self.assertEqual(J.resoudre_chemin("", b), b["home"])

    def test_lister_chercher_creer(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "Projets", "Jarvis"))
            os.makedirs(os.path.join(d, "AppData", "projets caches"))
            open(os.path.join(d, "projet.txt"), "w").close()
            open(os.path.join(d, ".secret"), "w").close()
            l = J.lister_dossier(d)
            self.assertIn("2 dossiers, 1 fichiers", l)
            self.assertNotIn(".secret", l)
            self.assertIn("Jarvis", J.lister_dossier(d, 2))
            res, _ = J.trouver_fichiers(d, J.criteres("PROJ"))
            noms = [os.path.basename(c) for c, _, _ in res]
            self.assertIn("projet.txt", noms)
            self.assertNotIn("projets caches", noms, "AppData n'est pas fouille")
            protege = os.path.join(d, "Windows")
            with self.assertRaises(PermissionError):
                J.creer_dossier(os.path.join(protege, "x"), [protege])
            self.assertIn("Cree", J.creer_dossier(os.path.join(d, "Nouveau", "Sous")))
            self.assertIn("existe deja", J.creer_dossier(os.path.join(d, "Nouveau")))
            beaucoup = os.path.join(d, "beaucoup")
            os.makedirs(beaucoup)
            for i in range(200):
                open(os.path.join(beaucoup, "f%03d" % i), "w").close()
            self.assertIn("et 80 de plus", J.lister_dossier(beaucoup))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_les_preferences(self):
        l = J.ajouter_preference([], "  Préfère   les réponses courtes. ")
        self.assertEqual(l, ["Préfère les réponses courtes."])
        l = J.ajouter_preference(l, "Écoute du jazz le soir.")
        l = J.ajouter_preference(l, "prefere les reponses courtes")          # doublon : remonte en dernier
        self.assertEqual(len(l), 2)
        self.assertEqual(l[-1], "prefere les reponses courtes")
        with self.assertRaises(ValueError):
            J.ajouter_preference(l, "  le la ")
        self.assertEqual(len(J.ajouter_preference(["p%d" % i for i in range(40)], "une de plus")), 40)
        self.assertLessEqual(len(J.ajouter_preference([], "x" * 500)[0]), 200)
        reste, retirees = J.retirer_preference(l, "le jazz")
        self.assertEqual(retirees, ["Écoute du jazz le soir."])
        self.assertEqual(reste, ["prefere les reponses courtes"])
        self.assertEqual(J.retirer_preference(l, "la météo")[1], [], "rien qui corresponde : rien ne part")
        self.assertEqual(J.retirer_preference(l, tout=True), ([], l))

    def test_l_historique_des_navigateurs(self):
        import sqlite3
        d = tempfile.mkdtemp()
        try:
            local, roaming = os.path.join(d, "Local"), os.path.join(d, "Roaming")
            chrome = os.path.join(local, "Google", "Chrome", "User Data", "Default")
            profil2 = os.path.join(local, "Google", "Chrome", "User Data", "Profile 2")
            ff = os.path.join(roaming, "Mozilla", "Firefox", "Profiles", "abc.default")
            for x in (chrome, profil2, ff, os.path.join(local, "Google", "Chrome", "User Data", "System Profile")):
                os.makedirs(x)
            maintenant = time.time()
            chromium = lambda t: int((t + 11644473600) * 1000000)
            con = sqlite3.connect(os.path.join(chrome, "History"))
            con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, "
                        "last_visit_time INTEGER, hidden INTEGER DEFAULT 0)")
            con.executemany("INSERT INTO urls (url, title, visit_count, last_visit_time) VALUES (?,?,1,?)", [
                ("https://www.youtube.com/watch?v=aaa", "Le chat qui joue du piano - YouTube", chromium(maintenant - 3 * 86400)),
                ("https://www.youtube.com/watch?v=bbb", "Chat piano 2 : le retour - YouTube", chromium(maintenant - 3600)),
                ("https://exemple.fr/reset?token=SECRET123&page=2#haut", "Piano et chat, réinitialiser", chromium(maintenant - 7200)),
                ("https://vieux.fr", "Chat piano ancien", chromium(maintenant - 400 * 86400)),
                ("chrome://settings", "chat piano réglages", chromium(maintenant)),
            ])
            con.commit()
            con.close()
            open(os.path.join(profil2, "History"), "wb").write(b"pas une base sqlite")
            con = sqlite3.connect(os.path.join(ff, "places.sqlite"))
            con.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT, title TEXT, last_visit_date INTEGER)")
            con.execute("INSERT INTO moz_places (url, title, last_visit_date) VALUES (?,?,?)",
                        ("https://www.youtube.com/watch?v=ccc", "Un chat au piano, en direct", int((maintenant - 86400) * 1e6)))
            con.commit()
            con.close()
            fichiers = J.fichiers_historique({"LOCALAPPDATA": local, "APPDATA": roaming})
            self.assertEqual([(n, g) for n, g, _ in fichiers], [("Chrome", "chromium"), ("Chrome", "chromium"),
                                                                 ("Firefox", "firefox")])
            r = J.chercher_historique("chat piano youtube", fichiers, maintenant=maintenant)
            self.assertIn("3 pages", r)
            self.assertLess(r.index("bbb"), r.index("ccc"), "les plus recentes d'abord")
            self.assertLess(r.index("ccc"), r.index("aaa"))
            self.assertIn("hier", r)
            self.assertIn("il y a 3 jours", r)
            self.assertNotIn("vieux.fr", r, "au-dela de 90 jours")
            self.assertNotIn("chrome://", r)
            r = J.chercher_historique("piano chat", fichiers, maintenant=maintenant)
            self.assertIn("page=2", r)
            self.assertNotIn("SECRET123", r, "un jeton ne part pas")
            self.assertNotIn("#haut", r)
            self.assertIn("vieux.fr", J.chercher_historique("piano chat", fichiers, jours=500, maintenant=maintenant))
            r = J.chercher_historique("chat piano guitare", fichiers, maintenant=maintenant)
            self.assertIn("sans tous les mots", r)
            self.assertIn("Rien", J.chercher_historique("dinosaure", fichiers, maintenant=maintenant))
            self.assertEqual(os.listdir(chrome), ["History"], "la copie temporaire n'est pas laissee a cote")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_liens_et_google(self):
        self.assertTrue(J.lien_permis("https://www.youtube.com/watch?v=abc"))
        for mauvais in ("file:///C:/x", "javascript:alert(1)", "https://", "https://a.fr/x y", "", None):
            self.assertFalse(J.lien_permis(mauvais), mauvais)
        self.assertEqual(J.adresse_google("chat & piano"), "https://www.google.com/search?q=chat+%26+piano")
        with self.assertRaises(ValueError):
            J.adresse_google("  ")

    def test_applis_et_jeux_steam(self):
        d = tempfile.mkdtemp()
        try:
            steam, autre = os.path.join(d, "Steam"), os.path.join(d, "D", "SteamLibrary")
            for x in (os.path.join(steam, "steamapps"), os.path.join(autre, "steamapps")):
                os.makedirs(x)
            open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), "w").write(
                '"libraryfolders"\n{\n "0"\n {\n  "path"  "%s"\n }\n "1"\n {\n  "path"  "%s"\n }\n}\n'
                % (steam.replace("\\", "\\\\"), autre.replace("\\", "\\\\")))
            acf = lambda ident, nom: '"AppState"\n{\n\t"appid"\t\t"%s"\n\t"name"\t\t"%s"\n}\n' % (ident, nom)
            open(os.path.join(steam, "steamapps", "appmanifest_1245620.acf"), "w").write(acf(1245620, "ELDEN RING"))
            open(os.path.join(autre, "steamapps", "appmanifest_228980.acf"), "w").write(
                acf(228980, "Steamworks Common Redistributables"))
            open(os.path.join(autre, "steamapps", "appmanifest_730.acf"), "w").write(acf(730, "Counter-Strike 2"))
            jeux = J.jeux_steam(steam)
            self.assertEqual(sorted(jeux), [("Counter-Strike 2", "steam://rungameid/730", "jeu"),
                                            ("ELDEN RING", "steam://rungameid/1245620", "jeu")])
            menu = os.path.join(d, "Menu")
            os.makedirs(os.path.join(menu, "Discord Inc"))
            for f in ("Discord Inc/Discord.lnk", "Discord Inc/Uninstall Discord.lnk", "OBS Studio.lnk",
                      "Lisez-moi.lnk", "notes.txt", "Visual Studio Code.lnk"):
                open(os.path.join(menu, f), "w").close()
            applis = J.raccourcis_menu([menu, menu])
            self.assertEqual(sorted(n for n, _, _ in applis), ["Discord", "OBS Studio", "Visual Studio Code"])
            tout = jeux + applis
            self.assertEqual(J.choisir("Elden Ring", tout)[0][0], "ELDEN RING")
            self.assertEqual(J.choisir("le jeu elden ring", tout)[0][0], "ELDEN RING")
            self.assertEqual(J.choisir("discord", tout)[0][0], "Discord")
            self.assertEqual(J.choisir("counter strike", tout)[0][0], "Counter-Strike 2")
            self.assertEqual(J.choisir("vs code", tout), [])
            self.assertEqual(J.choisir("visual studio", tout)[0][0], "Visual Studio Code")
            self.assertEqual(J.choisir("photoshop", tout), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_les_niveaux(self):
        self.assertEqual(J.nouveau_niveau(40, "regler", 75), 75)
        self.assertEqual(J.nouveau_niveau(40.4, "monter"), 50)
        self.assertEqual(J.nouveau_niveau(95, "monter", 20), 100)
        self.assertEqual(J.nouveau_niveau(5, "baisser"), 0)
        with self.assertRaises(ValueError):
            J.nouveau_niveau(5, "regler")

    def test_l_ecoute_s_adapte(self):
        # « make it easier to leave Jarvis » : une fenetre courte
        self.assertEqual(J.attente_suite("Il est 14 h."), 4.0)
        self.assertEqual(J.attente_suite("Vous voulez que je le lance ?"), 9.0, "il vient de poser une question")
        self.assertEqual(J.attente_suite("Voila.", echanges=4), 7.0, "la conversation dure")
        self.assertEqual(J.attente_suite("D'accord ?", echanges=10), 10.0, "10 s au plus")
        self.assertEqual(J.attente_suite("Je vous entends.", mode="psy"), 10.0)

    def test_un_acquittement_clot_la_conversation(self):
        for t in ("ok", "Ok, merci.", "Parfait, merci Jarvis.", "super", "nickel", "d'accord", "ça marche",
                  "got it, thanks", "perfect", "sounds good", "très bien merci"):
            self.assertTrue(J.acquittement(t), t)
        for t in ("ok lance la musique", "super, et demain ?", "parfait pour le rendez-vous de jeudi",
                  "quelle heure est-il", ""):
            self.assertFalse(J.acquittement(t), t)

    def test_la_boule_de_jarvis(self):
        # « toujours placee au meme endroit peu importe la resolution de l'ecran »
        for zone in ((0, 0, 1920, 1040), (0, 0, 3840, 2080), (0, 0, 2560, 1400)):
            x, y = J.place_boule(zone, 0.97, 0.90, 44)
            self.assertAlmostEqual((x + 22) / zone[2], 0.97, delta=0.002)
            self.assertAlmostEqual((y + 22) / zone[3], 0.90, delta=0.002)
        self.assertEqual(J.place_boule((100, 50, 800, 600), 1.0, 1.0, 44), (856, 606), "jamais hors de l'ecran")
        self.assertEqual(J.place_boule((-1920, 0, 1920, 1080), 0.0, 0.0, 44), (-1920, 0))
        zone = (0, 0, 1920, 1040)
        self.assertFalse(J.cible_boule("attente", "jarvis", None, zone, 100)[0], "endormi : pas de boule")
        visible, x, y, couleur, _ = J.cible_boule("ecoute", "jarvis", None, zone, 100)
        self.assertTrue(visible)
        self.assertEqual((x, y, couleur), J.place_boule(zone) + ("#FF9A3C",))
        self.assertEqual(J.cible_boule("pense", "psy", None, zone, 100)[3], "#4DA3FF")
        # « la boule se deplace la ou Jarvis doit regarder l'ecran »
        regard = {"ecran": {"left": 1920, "top": 0, "width": 2560, "height": 1440}, "jusqua": 105}
        visible, x, y, _, _ = J.cible_boule("pense", "jarvis", regard, zone, 100)
        self.assertTrue(visible)
        self.assertEqual((x, y), (1920 + 1280 - 22, 57), "en haut, au milieu de l'ecran regarde")
        self.assertEqual(J.cible_boule("pense", "jarvis", regard, zone, 106)[1:3], J.place_boule(zone),
                         "regard fini : elle revient a sa place")

    def test_la_legende_de_la_boule(self):
        # « Jarvis ne devrait afficher que la petite bulle, plus la grande fenetre,
        # le texte peut s'afficher en minuscule a cote (ecran 4K) »
        L = J.legende_boule
        self.assertEqual(L("parle", "fr", dit="Il fait 21 degrés."), "Il fait 21 degrés.")
        long_ = " ".join("mot%d" % i for i in range(80))
        fin = L("parle", "fr", dit=long_)
        self.assertLessEqual(len(fin), J.LEGENDE_SIGNES + 1)
        self.assertTrue(fin.startswith("\u2026") and fin.endswith("mot79"), "la fin de ce qu'il dit")
        self.assertNotIn("\u2026ot", fin, "coupe a un mot")
        self.assertEqual(L("pense", "fr", entendu="mets de la musique"), "\u00ab mets de la musique \u00bb")
        self.assertEqual(L("pense", "fr"), "je réfléchis\u2026")
        self.assertEqual(L("ecoute", "en"), "listening")
        self.assertEqual(L("ecoute", "fr", entendu="mets de\u2026"), "mets de\u2026", "ce qu'il entend deja")
        self.assertEqual(L("erreur", "fr", erreur="BrainDebugger ne répond pas."), "BrainDebugger ne répond pas.")
        self.assertEqual(L("erreur", "en"), "error")
        self.assertEqual(L("parle", "fr"), "", "rien encore de dit : pas d'etiquette vide")
        self.assertEqual(L("attente", "fr"), "")
        for mots in J.MOTS_LEGENDE.values():
            self.assertTrue(all(m == m.lower() for m in mots.values()), "en petit, pas en capitales")
        # une commande faite se lit un instant, la boule seule le montre
        self.assertTrue(J.cible_boule("fait", "jarvis", None, (0, 0, 1920, 1040), 100)[0])

    def test_le_son_appli_par_appli(self):
        # « baisser le son de Spotify, baisser le son de Discord, baisser le son du jeu »
        attendu = {
            "baisse spotify": ("baisser", "spotify", None), "baisse le son de discord": ("baisser", "discord", None),
            "monte le son du jeu": ("monter", "jeu", None), "coupe le jeu": ("couper", "le jeu", None),
            "mets spotify à 30": ("regler", "spotify", 30), "baisse le son": ("baisser", "", None),
            "baisse un peu la musique": ("baisser", "la musique", 5), "remets le son de discord": ("remettre", "discord", None),
            "baisse le son de minecraft de 20": ("baisser", "minecraft", 20), "monte chrome à 80 %": ("regler", "chrome", 80),
            "baisse beaucoup le jeu": ("baisser", "le jeu", 25)}
        for dit, (sens, cible, niveau) in attendu.items():
            self.assertEqual(J.comprendre(dit), {"action": "volume", "sens": sens, "cible": cible, "niveau": niveau}, dit)
        self.assertEqual(J.comprendre("qu'est-ce qui fait du son ?"), {"action": "sons"})
        for dit in ("baisse la lumière", "mets le minuteur à 10", "coupe la lumière", "baisse les bras"):
            self.assertNotEqual((J.comprendre(dit) or {}).get("action"), "volume", dit)
        jeu = r"D:\SteamLibrary\steamapps\common\ELDEN RING\Game\eldenring.exe"
        self.assertTrue(J.est_un_jeu(jeu))
        self.assertTrue(J.est_un_jeu(r"C:\Riot Games\VALORANT\live\VALORANT.exe"))
        self.assertFalse(J.est_un_jeu(r"C:\Program Files (x86)\Steam\steam.exe"))
        self.assertFalse(J.est_un_jeu(r"C:\Program Files (x86)\Steam\steamapps\common\x\steamwebhelper.exe",
                                      "steamwebhelper.exe"), "le lanceur n'est pas le jeu")
        sessions = [("Spotify.exe", r"C:\Users\a\AppData\Roaming\Spotify\Spotify.exe"),
                    ("Discord.exe", r"C:\Users\a\AppData\Local\Discord\app-1\Discord.exe"),
                    ("eldenring.exe", jeu), ("chrome.exe", r"C:\Program Files\Google\Chrome\chrome.exe"),
                    ("msedge.exe", r"C:\Program Files (x86)\Microsoft\Edge\msedge.exe")]
        self.assertEqual(J.cibles_son("le jeu", sessions), [2])
        self.assertEqual(J.cibles_son("jeu", sessions), [2])
        self.assertEqual(J.cibles_son("spotify", sessions), [0])
        self.assertEqual(J.cibles_son("discord", sessions), [1])
        self.assertEqual(J.cibles_son("le navigateur", sessions), [3, 4])
        self.assertEqual(J.cibles_son("youtube", sessions), [3, 4])
        self.assertEqual(J.cibles_son("chrome", sessions), [3], "« chrome » ouvert : Chrome seulement")
        self.assertEqual(J.cibles_son("la musique", sessions), [0])
        self.assertEqual(J.cibles_son("minecraft", sessions), [])

    def test_le_panneau_de_jarvis(self):
        # « le meme qu'ici » : le contenu Jarvis du panneau LED, et sa reponse qui defile
        import numpy as np
        C = J.LED_COULEURS
        allumes = lambda im, c: int(np.all(im == np.array([round(x) for x in c], dtype=np.uint8), axis=2).sum())
        ecoute = J.image_jarvis("ecoute", 0.0)
        self.assertEqual(ecoute.shape, (64, 64, 3))
        self.assertGreater(allumes(ecoute, C["cyan"]), 60, "l'anneau cyan")
        self.assertGreater(int((ecoute[50:57].max(axis=2) > 0).sum()), 40, "LISTENING en bas")
        pense = J.image_jarvis("pense", 0.7, croix=False)
        self.assertGreater(int((pense[:44].max(axis=2) > 0).sum()), 40)
        arc = pense[:44].reshape(-1, 3).astype(int)
        arc = arc[arc.max(axis=1) > 0]
        self.assertTrue(np.all((arc[:, 2] > arc[:, 0]) & (arc[:, 0] > arc[:, 1])), "l'arc, en degrade de violet")
        parle = J.image_jarvis("parle", 1.0)
        self.assertTrue(np.any(np.all(parle[:44] == np.array(C["ambre"], dtype=np.uint8), axis=2)), "les barres")
        muet = J.image_jarvis("parle", 1.0, "")
        self.assertGreater(int((muet[50:57].max(axis=2) > 0).sum()), 40, "SPEAKING sans reponse")
        psy = J.image_jarvis("ecoute", 0.0, mode="psy")
        self.assertEqual(allumes(psy, C["cyan"]), 0, "en mode psychologue, pas le cyan de Jarvis")
        self.assertEqual(J.texte_led("Il fait 21 °C à Lyon — super ! (≈)"), "IL FAIT 21 °C A LYON SUPER ! ( )")
        self.assertEqual(J.largeur_led("AB"), 11)
        dalle = J.dalle_led(ecoute, 5)
        self.assertEqual(dalle.shape, (320, 320, 3))
        self.assertEqual(tuple(dalle[0, 0]), (8, 9, 12), "le fond entre les LED")
        self.assertEqual(tuple(dalle[2, 2]), (18, 20, 26), "une LED eteinte, a peine visible")

    def test_le_panneau_dit_ou_il_en_est(self):
        # « je galere a comprendre quand il m'ecoute ou s'il repond encore »
        import numpy as np
        allume = lambda im: int((im.max(axis=2) > 0).sum())
        ecoute, recu = J.image_jarvis("ecoute", 1.0), J.image_jarvis("comprend", 1.0)
        self.assertGreater(int(np.abs(ecoute.astype(int) - recu.astype(int)).sum()), 5000,
                           "RECU ne ressemble pas a A VOUS")
        self.assertEqual(allume(J.image_jarvis("attente", 1.0)), 0, "rien, et surtout pas DONE en s'effacant")
        plein = J.image_jarvis("ecoute", 1.0, reste=1.0, croix=False)
        vide = J.image_jarvis("ecoute", 1.0, reste=0.0, croix=False)
        self.assertGreater(allume(plein[60:61]), allume(vide[60:61]) - 1)
        self.assertGreater(int(plein[60:61].sum()), int(vide[60:61].sum()), "le temps qu'il attend encore")
        entendu = J.image_jarvis("pense", 1.0, entendu="Allume la lumiere")
        self.assertGreater(allume(entendu[27:60]), allume(J.image_jarvis("pense", 1.0)[27:48]),
                           "ce qu'il a entendu s'ecrit")
        self.assertEqual(J.etat_panneau("ecoute", 10.0), "ecoute")
        self.assertIsNone(J.etat_panneau("attente", 10.0))
        self.assertIsNone(J.etat_panneau("erreur", 10.0), "une erreur de fond ne reste pas a l'ecran")
        self.assertEqual(J.etat_panneau("attente", 10.0, erreur_jusqua=11.0), "erreur")
        self.assertEqual(J.etat_panneau("attente", 10.0, fait_jusqua=11.0), "fait")
        fr = J.image_jarvis("ecoute", 0.0, langue="fr", croix=False)
        en = J.image_jarvis("ecoute", 0.0, langue="en", croix=False)
        self.assertFalse(np.array_equal(fr[50:57], en[50:57]), "A VOUS / LISTENING")

    def test_le_sous_titre_s_ecrit_au_fil_de_la_voix_dans_le_panneau(self):
        # « le texte ecrit en meme temps que Jarvis l'enonce, comme un
        # sous-titre, dans la case du panneau LED uniquement »
        import numpy as np
        phrases = ["Bien sur monsieur.", "Votre rendez-vous est demain a quatorze heures."]
        self.assertEqual(J.texte_dit(phrases, -1, 0.0), "", "rien tant que la voix n'a pas commence")
        self.assertEqual(J.texte_dit(phrases, 0, 0.0), "Bien")
        self.assertEqual(J.texte_dit(phrases, 1, 0.3), "Bien sur monsieur. Votre rendez-vous")
        self.assertEqual(J.texte_dit(phrases, 1, 1.0), " ".join(phrases))
        self.assertEqual(J.texte_dit(phrases, 5, 0.0), " ".join(phrases))
        self.assertEqual(J.lignes_led("Votre rendez-vous est demain", J.LED_N),
                         ["VOTRE", "RENDEZ-", "VOUS EST", "DEMAIN"], "un mot trop long se coupe au trait d'union")
        self.assertTrue(all(J.largeur_led(l) <= J.LED_N - 2 for l in J.lignes_led("A" * 40, J.LED_N)))
        court = J.image_jarvis("parle", 1.0, sous_titre="Bien")
        long_ = J.image_jarvis("parle", 1.0, sous_titre=" ".join(phrases))
        self.assertEqual(court.shape, (64, 64, 3), "dans le panneau, pas a cote")
        texte = lambda im: int((im[16:64].max(axis=2) > 0).sum())
        self.assertGreater(texte(long_), texte(court), "plus il a parle, plus il y a de texte")
        self.assertEqual(int((J.image_jarvis("parle", 1.0)[48:59].max(axis=2) > 0).sum() > 0), 1,
                         "sans texte : SPEAKING")

    def test_l_agenda_jour_par_jour(self):
        rdv = [{"date": "2026-10-02", "heure": "", "label": "Anniversaire de Paul"},
               {"date": "2026-10-02", "heure": "14:30", "label": "Dentiste"},
               {"date": "2026-10-01", "heure": "09:00", "label": "Reunion"},
               {"date": "2026-09-28", "fin": "2026-10-04", "heure": None, "label": "Vacances"},
               {"date": "2026-10-06", "label": "Kine", "heure": "18:00"}, {"label": "sans date"}]
        jours = J.agenda_par_jour(rdv, "2026-10-01")
        self.assertEqual([t for t, _ in jours], ["Aujourd'hui -- jeudi 1 octobre", "Demain -- vendredi 2 octobre",
                                                 "Mardi 6 octobre"])
        self.assertEqual(jours[0][1], [("09:00", "Reunion", ""), ("", "Vacances", "jusqu'au dimanche 4 octobre")],
                         "une periode commencee avant : a aujourd'hui ; les heures d'abord")
        self.assertEqual([x[1] for x in jours[1][1]], ["Dentiste", "Anniversaire de Paul"])
        self.assertEqual(J.agenda_par_jour([], "2026-10-01"), [])

    def test_la_liste_plus_belle_de_l_agenda(self):
        # « rends l'agenda plus beau » : les jours avec leur date, et ce qui reste
        rdv = [{"date": "2026-10-02", "heure": "", "label": "Anniversaire de Paul"},
               {"date": "2026-10-01", "heure": "18:00", "label": "Appeler maman"},
               {"date": "2026-10-01", "heure": "09:00", "label": "Reunion"},
               {"date": "2026-09-28", "fin": "2026-10-04", "label": "Vacances"}, {"label": "sans date"}]
        jours = J.agenda_jours(rdv, "2026-10-01")
        self.assertEqual([j for j, _, _ in jours], ["2026-10-01", "2026-10-02"])
        self.assertEqual([r["label"] for r in jours[0][2]], ["Reunion", "Appeler maman", "Vacances"])
        self.assertEqual(jours[0][2][2]["date"], "2026-09-28", "la periode garde sa vraie date")
        quatorze_h = 14 * 60
        self.assertEqual(J.relatif_aujourdhui("18:00", quatorze_h), "dans 4 h")
        self.assertEqual(J.relatif_aujourdhui("15:10", quatorze_h), "dans 1 h 10")
        self.assertEqual(J.relatif_aujourdhui("14:25", quatorze_h), "dans 25 min")
        self.assertEqual(J.relatif_aujourdhui("13:50", quatorze_h), "maintenant")
        self.assertEqual(J.relatif_aujourdhui("09:00", quatorze_h), "passé")
        self.assertIsNone(J.relatif_aujourdhui("", quatorze_h))

    def test_les_vues_semaine_mois_annee(self):
        # « rajoute une vue a la semaine, au mois et a l'annee »
        self.assertEqual(J.bornes_vue("semaine", "2026-10-21"), ("2026-10-19", "2026-10-25"))
        self.assertEqual(J.bornes_vue("mois", "2026-10-21"), ("2026-09-28", "2026-11-01"))
        self.assertEqual(J.bornes_vue("annee", "2026-10-21"), ("2026-01-01", "2026-12-31"))
        self.assertIsNone(J.bornes_vue("liste", "2026-10-21"))
        self.assertEqual(J.deplacer_vue("mois", "2026-12-15", 1), "2027-01-01")
        self.assertEqual(J.deplacer_vue("mois", "2026-01-31", -1), "2025-12-01")
        self.assertEqual(J.deplacer_vue("semaine", "2026-10-21", -1), "2026-10-14")
        self.assertEqual(J.deplacer_vue("annee", "2026-10-21", 1), "2027-01-01")
        self.assertEqual(J.titre_vue("semaine", "2026-10-29"), "Semaine 44  ·  26 oct. - 1 nov. 2026")
        self.assertEqual(J.titre_vue("mois", "2026-02-03"), "Février 2026")
        semaines = J.grille_mois("2026-10-21")
        self.assertEqual(len(semaines), 5)
        self.assertTrue(all(len(s) == 7 for s in semaines))
        self.assertEqual((semaines[0][0], semaines[-1][-1]), ("2026-09-28", "2026-11-01"))
        rdv = [{"date": "2026-10-20", "fin": "2026-10-23", "label": "Festival"},
               {"date": "2026-10-21", "heure": "18:00", "label": "Appel"},
               {"date": "2026-10-21", "heure": "09:00", "label": "Dentiste"},
               {"date": "2026-10-21", "label": "Anniversaire"}]
        self.assertEqual([r["label"] for r in J.rdv_du_jour(rdv, "2026-10-21")],
                         ["Festival", "Dentiste", "Appel", "Anniversaire"])
        self.assertEqual([r["label"] for r in J.rdv_du_jour(rdv, "2026-10-24")], [])

    def test_la_frise_de_l_agenda(self):
        # « un mode frise », « des rappels pouvant durer plusieurs jours »
        rdv = [{"date": "2026-09-20", "fin": "2026-09-27", "label": "Vacances"},
               {"date": "2026-09-25", "heure": "14:30", "label": "Dentiste"},
               {"date": "2026-09-26", "label": "Anniv"},
               {"date": "2026-09-10", "label": "fini depuis longtemps"},
               {"date": "2026-10-30", "label": "trop loin"}, {"label": "sans date"}]
        v = J.voies_frise(rdv, "2026-09-22", 14)
        self.assertEqual([(x[0], x[1], x[2], x[4]) for x in v],
                         [(0, 0, 5, "Vacances"), (1, 3, 3, "Dentiste"), (1, 4, 4, "Anniv")],
                         "une periode commencee avant est coupee au bord ; hors de la frise : rien")
        # un nom qui deborde garde sa voie jusqu'au bout
        v = J.voies_frise(rdv, "2026-09-22", 14, lambda lib, h: 3)
        self.assertEqual([(x[0], x[4]) for x in v], [(0, "Vacances"), (1, "Dentiste"), (2, "Anniv")])
        self.assertEqual([r["label"] for r in J.en_cours_ou_a_venir(rdv[:5], "2026-09-25")],
                         ["Vacances", "Dentiste", "Anniv", "trop loin"])
        self.assertEqual(J.prochain_rendez_vous(rdv, "2026-09-25", "15:00"),
                         ("Vacances", "en cours, jusqu'a dim. 27 sept."), "la periode en cours ; 14:30 est passe")
        self.assertEqual(J.prochain_rendez_vous(rdv[1:], "2026-09-25", "10:00"), ("Dentiste", "aujourd'hui a 14:30"))
        self.assertEqual(J.prochain_rendez_vous([], "2026-09-25"), None)
        self.assertEqual(J.quand_lisible("2026-09-29", "", "2026-09-25"), "dans 4 jours")
        self.assertEqual(J.quand_lisible("2026-09-20", "", "2026-09-25", "2026-09-25"), "en cours, fini ce soir")
        self.assertEqual(J.jour_court("2026-10-01"), "jeu. 1 oct.")
        self.assertEqual(J.plus_jours("2026-12-30", 3), "2027-01-02")
        self.assertEqual(J.teinte_rendez_vous("Dentiste"), J.teinte_rendez_vous("dentiste"))

    def test_rien_qui_eteigne_le_pc(self):
        for chemin in ("C:\\Windows\\System32\\shutdown.exe", "logoff.exe", "tsdiscon", "rundll32.exe",
                       "SlideToShutDown.exe", "psshutdown64.exe"):
            self.assertTrue(J.touche_a_l_alimentation(chemin), chemin)
        for chemin, contenu in (("a.bat", "shutdown -r -t 0"), ("a.ps1", "Restart-Computer"),
                                ("a.vbs", "ExitWindowsEx"), ("a.cmd", "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"),
                                ("a.bat", "logoff"), ("a.ps1", "Stop-Computer")):
            self.assertTrue(J.touche_a_l_alimentation(chemin, contenu), (chemin, contenu))
        for chemin, contenu in (("notes.txt", "shutdown"), ("a.bat", "echo bonjour"), ("a.md", "logoff")):
            self.assertFalse(J.touche_a_l_alimentation(chemin, contenu), (chemin, contenu))
        self.assertFalse(J.touche_a_l_alimentation("C:\\Program Files\\Discord\\Discord.exe"))

    def test_les_animations_de_lumiere(self):
        e = J.etapes_propres([{"couleur": "#FF0000", "duree": 1, "effet": "fondu"},
                              {"couleur": "#0000FF", "duree": 1, "effet": "clignote"},
                              {"duree": 1, "effet": "arc_en_ciel"}, {"couleur": "n'importe", "duree": 1},
                              {"couleur": "vert", "duree": 99, "luminosite": 7}])
        self.assertEqual([x["effet"] for x in e], ["fondu", "clignote", "arc_en_ciel", "fixe"])
        self.assertEqual((e[3]["duree"], e[3]["luminosite"]), (30.0, 1.0), "bornees")
        r = lambda t: tuple(round(c) for c in J.couleur_animation(e, t))
        self.assertEqual(r(0.0), (0, 0, 0), "le premier fondu part du noir")
        self.assertEqual(r(0.5), (128, 0, 0))
        self.assertEqual(r(1.0), (0, 0, 255))
        self.assertEqual(r(1.3), (0, 0, 0), "clignote : eteint un quart de seconde sur deux")
        self.assertEqual(r(2.0), (255, 0, 0), "l'arc-en-ciel commence au rouge")
        self.assertIsNone(J.couleur_animation(e, 33.1))
        self.assertIsNone(J.couleur_animation([], 0))
        self.assertEqual(J.couleur_lue("#f80"), "#FF8800")
        self.assertEqual(J.couleur_lue("eteint"), "#000000")
        self.assertIsNone(J.couleur_lue("plaid"))
        with self.assertRaises(ValueError):
            J.routine_propre({"nom": "x", "declencheur": {"type": "evenement", "valeur": "anniversaire"},
                              "etapes": [{"couleur": "rouge"}]})
        with self.assertRaises(ValueError):
            J.routine_propre({"nom": "x", "declencheur": {"type": "phrase", "valeur": "ok"}, "etapes": [{"couleur": "rouge"}]})
        r0 = J.routine_propre({"nom": "Salut", "declencheur": {"type": "evenement", "valeur": "au revoir"},
                               "etapes": [{"couleur": "rose"}], "chance": 3})
        self.assertEqual((r0["declencheur"]["valeur"], r0["chance"]), ("au_revoir", 1.0))
        liste = J.ranger_routine([], r0)
        self.assertEqual(len(J.ranger_routine(liste, dict(r0, replique="Ciao"))), 1, "meme nom : remplacee")

    def test_une_explication_longue_ne_montre_que_sa_premiere_phrase(self):
        # « une passe de simplicite partout »
        import importlib.util
        spec = importlib.util.spec_from_file_location("mt_aide", os.path.join(RACINE, "machi_tool.py"))
        src = open(os.path.join(RACINE, "machi_tool.py"), encoding="utf-8").read()
        self.assertIn("def aide_courte(", src)
        self.assertNotIn("def page_calendrier(", src, "les pages mortes sont parties")
        self.assertEqual(src.count("    def peindre_journal("), 1)
        corps = src[src.index("    def page_jarvis(self):"):src.index("    def basculer_jarvis(self):")]
        self.assertGreaterEqual(corps.count("self.repli(page, "), 7, "le detail de Jarvis est replie")

    def test_poser_un_rappel_a_la_main(self):
        a = "2026-09-25"                                    # un vendredi
        for tape, attendu in (("", a), ("demain", "2026-09-26"), ("Après-demain", "2026-09-27"), ("+3", "2026-09-28"),
                              ("lundi", "2026-09-28"), ("ven", "2026-10-02"), ("12/10", "2026-10-12"),
                              ("12/01", "2027-01-12"), ("12.10.26", "2026-10-12"), ("2026-10-12", "2026-10-12"),
                              ("31/02", None), ("n'importe quoi", None)):
            self.assertEqual(J.date_saisie(tape, a), attendu, tape)
        for tape, attendu in (("", ""), ("14h30", "14:30"), ("9h", "09:00"), ("14:05", "14:05"), ("25h", None),
                              ("14h75", None), ("midi", None)):
            self.assertEqual(J.heure_saisie(tape), attendu, tape)

    def test_le_bilan_des_derniers_jours(self):
        # « des infos de quantified self : temps de sommeil, note »
        bilan = {"jours": [{"date": "2026-09-23", "note": 7, "sommeil_h": 6.5, "coucher": "01:00", "lever": "07:30"},
                           {"date": "2026-09-24", "note": None, "sommeil_h": 8.0, "coucher": "23:40", "lever": "07:40"},
                           {"date": "2026-09-25", "note": 5.5, "sommeil_h": None},
                           {"date": "2026-09-26", "note": 9, "sommeil_h": 9}],       # demain : ignore
                 "sommeil_mediane": 7.1}
        b = J.resume_bilan(bilan, "2026-09-25")
        self.assertEqual(b["nuit"], {"date": "2026-09-24", "h": 8.0, "coucher": "23:40", "lever": "07:40"})
        self.assertEqual(b["note"], {"date": "2026-09-25", "n": 5.5})
        self.assertEqual((b["moy_sommeil"], b["moy_note"], b["mediane"]), (7.2, 6.2, 7.1))
        self.assertEqual([x[0] for x in b["serie"]], ["2026-09-23", "2026-09-24", "2026-09-25"])
        vide = J.resume_bilan(None, "2026-09-25")
        self.assertEqual((vide["nuit"], vide["note"], vide["serie"]), (None, None, []))
        self.assertEqual((J.duree_lisible(7.2), J.duree_lisible(None), J.note_lisible(6.5), J.note_lisible(7.0)),
                         ("7 h 12", "--", "6,5", "7"))

    def test_les_temperatures(self):
        import struct as st

        def coretemp(temps, tjmax=100, delta=False, fahrenheit=False, charges=None, coeurs=None):
            v = [0] * 256
            for i, c in enumerate(charges or [10] * len(temps)):
                v[i] = c
            t = [0.0] * 256
            t[:len(temps)] = temps
            return st.pack("<256I128III256fffff100sBB", *v, *([tjmax] * 128), coeurs or len(temps), 1, *t,
                           1.2, 3600.0, 100.0, 36.0, b"Intel Core i7-12700K", int(fahrenheit), int(delta))
        cpu = J.lire_coretemp(coretemp([48.0, 52.0, 61.0, 50.0], charges=[10, 20, 30, 40]))
        self.assertEqual(cpu["nom"], "Intel Core i7-12700K")
        self.assertEqual(cpu["temperatures"], [48.0, 52.0, 61.0, 50.0])
        self.assertEqual(J.lire_coretemp(coretemp([52.0, 39.0], delta=True))["temperatures"], [48.0, 61.0],
                         "« distance a TjMax » : la vraie temperature")
        self.assertEqual(J.lire_coretemp(coretemp([122.0], fahrenheit=True))["temperatures"], [50.0])
        self.assertIsNone(J.lire_coretemp(b"\0" * J.CT_TAILLE), "Core Temp pas lance : rien")
        self.assertIsNone(J.lire_coretemp(None))
        gpus = J.lire_nvidia_smi("NVIDIA GeForce RTX 3070, 47, 5, 1228, 8192\nbad\n")
        self.assertEqual(gpus, [{"nom": "NVIDIA GeForce RTX 3070", "temperature": 47.0, "charge": 5.0,
                                 "memoire": 1228.0, "memoire_totale": 8192.0}])
        texte = J.resume_temperatures(cpu, gpus, [("Intel Core i7-12700K", "CPU Package", 62.0),
                                                  ("NVIDIA GeForce RTX 3070", "GPU Core", 47.0),
                                                  ("Samsung SSD 980", "Temperature", 41.0)])
        self.assertIn("Processeur (Intel Core i7-12700K, Core Temp) : 53 °C en moyenne, 61 °C pour le coeur le plus chaud, charge 25 %", texte)
        self.assertIn("Carte graphique (NVIDIA GeForce RTX 3070, nvidia-smi) : 47 °C, charge 5 %, memoire 1.2 / 8 Go.", texte)
        self.assertIn("Samsung SSD 980 : Temperature 41 °C", texte)
        self.assertEqual(texte.count("RTX 3070"), 1, "pas deux fois la meme carte")
        self.assertEqual(texte.count("i7-12700K"), 1)
        radeon = J.resume_temperatures(None, [], [("AMD Radeon RX 6800", "GPU Core", 55.0), ("AMD Radeon RX 6800", "GPU Hot Spot", 71.0)])
        self.assertIn("le plus chaud : GPU Hot Spot, 71 °C", radeon)
        self.assertIn("lance Core Temp", J.resume_temperatures())

    def test_premiere_video_youtube(self):
        page = ('var ytInitialData = {"contents":[{"adSlotRenderer":{"videoId":"PUBLICITE01"}},'
                '{"channelRenderer":{"title":{"simpleText":"Daft Punk"}}},'
                '{"videoRenderer":{"videoId":"5NV6Rdv1a3I","thumbnail":{},"title":{"runs":[{"text":'
                '"Daft Punk - Get Lucky (Official Audio) ft. Pharrell Williams, Nile Rodgers \\u0026 more"}]}}},'
                '{"videoRenderer":{"videoId":"h5EofwRzit0"}}]};')
        self.assertEqual(J.premiere_video_youtube(page),
                         ("5NV6Rdv1a3I", "Daft Punk - Get Lucky (Official Audio) ft. Pharrell Williams, Nile Rodgers & more"))
        self.assertIsNone(J.premiere_video_youtube("<html>consent.youtube.com</html>"))

    def test_pourquoi_spotify_ne_repond_pas(self):
        # « verifie pourquoi il ne peut pas acceder a l'API Spotify »
        import urllib.request
        import ssl
        vus = []
        vrai = urllib.request.urlopen

        def refuse(req, timeout=None, context=None):
            vus.append(context)
            raise urllib.error.URLError(ssl.SSLCertVerificationError(
                "certificate verify failed: unable to get local issuer certificate"))
        urllib.request.urlopen = refuse
        ancien = J.CONTEXTE_SSL
        try:
            J.CONTEXTE_SSL = lambda: "LE-CONTEXTE"
            statut, r = J.http_json("GET", "https://api.spotify.com/v1/me")
        finally:
            urllib.request.urlopen, J.CONTEXTE_SSL = vrai, ancien
        self.assertEqual(vus, ["LE-CONTEXTE"], "le magasin de certificats de Machi Tool, pas celui par defaut")
        self.assertEqual(statut, 0, "une panne reseau n'est plus une exception")
        self.assertIn("certificat HTTPS est refuse", J.raison_spotify(statut, r))
        self.assertIn("Client ID inconnu", J.raison_spotify(400, {"error": "invalid_client"}))
        self.assertIn("Reconnecte Spotify", J.raison_spotify(400, {"error": "invalid_grant",
                                                                   "error_description": "Refresh token revoked"}))
        self.assertIn(J.SPOTIFY_RETOUR, J.raison_spotify(400, {"error": "invalid_request",
                                                               "error_description": "INVALID_CLIENT: Invalid redirect URI"}))
        self.assertIn("User Management", J.raison_spotify(403, {"error": {"status": 403,
                      "message": "User not registered in the Developer Dashboard"}}))
        # le jeton : plus de faux « expire » quand c'est le reseau
        sp = J.Spotify("CID", "R", http=lambda *a, **k: (0, {"error": "injoignable",
                                                            "error_description": "timed out"}))
        with self.assertRaises(J.ErreurSpotify) as e:
            sp.jeton()
        self.assertIn("injoignable", str(e.exception))
        # le diagnostic, pas a pas
        def http(methode, url, entetes=None, corps=None):
            if url.endswith("/api/token"):
                return 200, {"access_token": "A", "expires_in": 3600}
            if url.endswith("/me"):
                return 200, {"display_name": "Alex", "product": "free"}
            return 200, {"devices": [{"name": "PC-ALEX"}]}
        ok, lignes = J.Spotify("CID", "R", http=http).diagnostic()
        self.assertTrue(ok)
        self.assertEqual(lignes[0], "Jeton : OK.")
        self.assertIn("Alex (free)", lignes[1])
        self.assertIn("Sans Premium", lignes[2])
        self.assertIn("PC-ALEX", lignes[3])
        ok, lignes = J.Spotify("CID", "R", http=lambda *a, **k: (400, {"error": "invalid_client"})).diagnostic()
        self.assertFalse(ok)
        self.assertIn("Client ID inconnu", lignes[-1])

    def test_spotify_par_son_api(self):
        appels, sauves = [], []
        etat = {"appareils": [], "ouvert": False, "play": 204}

        def http(methode, url, entetes=None, corps=None):
            appels.append((methode, url, corps))
            if url.endswith("/api/token"):
                self.assertIn(b"grant_type=refresh_token", corps)
                return 200, {"access_token": "A%d" % len(appels), "expires_in": 3600, "refresh_token": "R2"}
            self.assertTrue(entetes["Authorization"].startswith("Bearer A"))
            if "/me/player/devices" in url:
                return 200, {"devices": etat["appareils"]}
            if "/me/playlists" in url:
                return 200, {"items": [None, {"name": "Sport du matin", "uri": "spotify:playlist:SPORT"}]}
            if "/search" in url:
                if "type=track" in url:
                    return 200, {"tracks": {"items": [{"name": "Get Lucky", "uri": "spotify:track:GL",
                                                       "artists": [{"name": "Daft Punk"}]}]}}
                if "type=playlist" in url:
                    return 200, {"playlists": {"items": [None, {"name": "Chill", "uri": "spotify:playlist:CH"}]}}
                return 200, {"albums": {"items": []}}
            if "/me/player/play" in url:
                return etat["play"], None
            if "/me/player/queue" in url:
                return 204, None
            if "/currently-playing" in url:
                return 200, {"is_playing": True, "item": {"id": "GL", "uri": "spotify:track:GL", "name": "Get Lucky",
                                                          "artists": [{"name": "Daft Punk"}]}}
            if "/me/tracks" in url:
                return 404, None
            if "/me/library" in url:
                return 204, None
            return 500, None

        def ouvrir():
            etat["ouvert"] = True
            etat["appareils"] = [{"id": "PC", "name": "BUREAU", "type": "Computer", "is_active": False}]
        sp = J.Spotify("CID", "R1", http=http, sauver=sauves.append, dormir=lambda s: None)
        self.assertEqual(sp.jouer("get lucky", ouvrir_appli=ouvrir), "Lecture : « Get Lucky » de Daft Punk, sur BUREAU.")
        self.assertTrue(etat["ouvert"], "Spotify ferme : il l'ouvre, puis attend l'appareil")
        self.assertEqual(sauves, ["R2"], "le nouveau jeton de renouvellement est garde")
        play = [a for a in appels if "/me/player/play" in a[1]][-1]
        self.assertIn("device_id=PC", play[1])
        self.assertEqual(play[2], {"uris": ["spotify:track:GL"]})
        self.assertIn("ta playlist « Sport du matin »", sp.jouer("sport", "playlist"))
        self.assertEqual([a for a in appels if "/me/player/play" in a[1]][-1][2], {"context_uri": "spotify:playlist:SPORT"})
        self.assertIn("« Chill »", sp.jouer("chill", "playlist"))
        self.assertIn("file", sp.jouer("get lucky", file=True))
        with self.assertRaises(J.ErreurSpotify):
            sp.jouer("chill", "playlist", file=True)
        with self.assertRaisesRegex(J.ErreurSpotify, "Rien trouve"):
            sp.jouer("xyz", "album")
        self.assertIn("likes", sp.aimer())
        etat["play"] = 403
        with self.assertRaisesRegex(J.ErreurSpotify, "Premium"):
            sp.jouer("get lucky")
        etat["appareils"] = []
        with self.assertRaisesRegex(J.ErreurSpotify, "ouvert nulle part"):
            sp.jouer("get lucky")
        self.assertEqual(sum(1 for a in appels if a[1].endswith("/api/token")), 1, "un seul jeton par heure")
        # « Jarvis ne peut pas interagir avec Spotify » : l'appli ne s'annonce pas
        # -> le morceau s'ouvre directement dedans
        ouverts = []
        self.assertIn("Ouvert dans l'application Spotify", sp.jouer("get lucky", ouvrir_uri=ouverts.append))
        self.assertEqual(ouverts, ["spotify:track:GL"])
        # un appareil endormi (404) : on lui passe la lecture, et on relance
        etat["appareils"] = [{"id": "PC", "name": "BUREAU", "type": "Computer", "is_active": False}]
        reponses = [(404, {"error": {"status": 404, "message": "Device not found"}}), (204, None)]
        vrai = http

        def http2(methode, url, entetes=None, corps=None):
            if "/me/player/play" in url:
                appels.append((methode, url, corps))
                return reponses.pop(0)
            if url.endswith("/me/player"):
                appels.append((methode, url, corps))
                return 204, None
            return vrai(methode, url, entetes, corps)
        sp.http = http2
        self.assertIn("Lecture", sp.jouer("get lucky"))
        transfert = [a for a in appels if a[1].endswith("/me/player")]
        self.assertEqual(transfert[-1][2], {"device_ids": ["PC"], "play": False})
        # un 403 qui n'est pas « Premium » : ce que Spotify a vraiment dit
        reponses[:] = [(403, {"error": {"status": 403, "message": "Player command failed: Restriction violated",
                                         "reason": "UNKNOWN"}})]
        with self.assertRaisesRegex(J.ErreurSpotify, "Restriction violated"):
            sp.jouer("get lucky")
        reponses[:] = [(403, {"error": {"status": 403, "message": "Player command failed: Premium required",
                                         "reason": "PREMIUM_REQUIRED"}})]
        with self.assertRaisesRegex(J.ErreurSpotify, "Premium"):
            sp.jouer("get lucky")

    def test_spotify_connexion_pkce(self):
        import hashlib as h
        verif, defi = J.pkce_paire()
        self.assertTrue(43 <= len(verif) <= 128)
        self.assertEqual(defi, base64.urlsafe_b64encode(h.sha256(verif.encode()).digest()).rstrip(b"=").decode())
        url = J.spotify_url_autorisation("CID", defi, "ETAT")
        self.assertIn("redirect_uri=http%3A%2F%2F127.0.0.1%3A8765%2Fcallback", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("user-modify-playback-state", urllib.parse.unquote_plus(url))
        self.assertNotIn(verif, url, "le verificateur ne part pas avec l'autorisation")
        with self.assertRaises(J.ErreurSpotify):
            J.Spotify.echanger_code("CID", "CODE", verif, http=lambda *a: (400, {"error": "invalid_grant"}))

    def test_youtube_se_comprend_ici(self):
        for dit, q in (("Mets Get Lucky sur YouTube", "get lucky"), ("mets-moi la vidéo de Squeezie sur YouTube.", "squeezie"),
                       ("lance du lo-fi sur youtube", "lo fi"), ("YouTube daft punk around the world", "daft punk around the world"),
                       ("play get lucky on youtube", "get lucky")):
            self.assertEqual(J.comprendre(dit), {"action": "youtube", "recherche": q}, dit)
        for dit in ("j'ai vu une vidéo sur YouTube hier", "c'est quoi youtube premium ?", "tu connais youtube"):
            self.assertNotEqual((J.comprendre(dit) or {}).get("action"), "youtube", dit)

    def test_les_onglets_ranges_par_site(self):
        for d, f in (("www.youtube.com", "YouTube"), ("m.youtube.com", "YouTube"), ("music.youtube.com", "Musique"),
                     ("old.reddit.com", "Reddit"), ("instagram.com", "Instagram"), ("x.com", "X"),
                     ("mail.google.com", "Mails"), ("docs.google.com", "Autres"), ("notyoutube.com", "Autres")):
            self.assertEqual(J.site_de(d), f, d)
        rang = J.ranger_onglets([{"domaine": "docs.python.org"}, {"domaine": "reddit.com"}, {"domaine": "youtube.com"}])
        self.assertEqual([f for f, _ in rang], ["YouTube", "Reddit", "Autres"])

    def test_la_recherche_qu_on_affine(self):
        # « J'ai 523 ... possedant la mention », « rajoute la mention stage »,
        # « j'ai 3 ... de stages », « parfait, ouvre-les » -- pour les fichiers.
        d = tempfile.mkdtemp()
        try:
            maintenant = time.time()
            def f(chemin, age_jours=1):
                p = os.path.join(d, *chemin.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").close()
                for x in (p, os.path.dirname(p)):          # un dossier a l'age de son dernier fichier
                    os.utime(x, (maintenant - age_jours * 86400,) * 2)
            for i in range(30):
                f("Cours/Unit %02d/notes.txt" % i, age_jours=40 + i)
            f("Stage/Rapport Unit.pdf", 2)
            f("Stage/unit tests.docx", 5)
            f("Stage/Convention.pdf", 3)
            f("Stage 2024/Unité 3 - stage.pdf", 400)
            crit = J.criteres("unit")
            res, coupe = J.trouver_fichiers(d, crit, maintenant=maintenant)
            self.assertFalse(coupe)
            r = {"racine": d, "criteres": crit, "resultats": res, "coupe": coupe}
            texte = J.resume_recherche(d, crit, res, coupe)
            self.assertRegex(texte, r"^6\d resultats \(3\d dossiers, 3\d fichiers\)")
            self.assertIn("1. " + os.path.join(d, "Stage", "Rapport Unit.pdf"), texte, "le plus recent en premier")
            self.assertIn("... et", texte)
            c2, garde = J.affiner(r, ajouter="stage", maintenant=maintenant)
            self.assertEqual(c2["mots"], ["unit", "stage"])
            self.assertEqual(sorted(os.path.basename(x) for x, _, _ in garde),
                             ["Rapport Unit.pdf", "Unite 3 - stage.pdf".replace("Unite", "Unité"), "unit tests.docx"],
                             "« stage » : dans le nom ou dans le dossier ; les accents ne comptent pas")
            r2 = dict(r, criteres=c2, resultats=garde)
            c3, garde3 = J.affiner(r2, type_="pdf", jours=30, maintenant=maintenant)
            self.assertEqual([os.path.basename(x) for x, _, _ in garde3], ["Rapport Unit.pdf"])
            _, a_refaire = J.affiner(dict(r2, criteres=c3, resultats=garde3), retirer="unit", maintenant=maintenant)
            self.assertIsNone(a_refaire, "on elargit : il faut tout reparcourir")
            _, a_refaire = J.affiner(dict(r2, coupe=True), ajouter="rapport", maintenant=maintenant)
            self.assertIsNone(a_refaire, "la recherche d'avant etait coupee : on reparcourt")
            with self.assertRaises(ValueError):
                J.criteres("x", type_="chaussette")
            with self.assertRaises(ValueError):
                J.trouver_fichiers(d, J.criteres(""))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_verrouille(self):
        for t in ("verrouille", "Ferme l'accès.", "lock"):
            self.assertEqual(J.comprendre(t)["action"], "verrouiller", t)
        self.assertIsNone(J.comprendre("ferme la fenêtre du salon"))


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
        dossier = os.environ.get("JARVIS_KOKORO_DOSSIER", "")
        conf = os.path.join(dossier, "config.json")
        if dossier and os.path.isfile(conf):
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

    @unittest.skipUnless(NUMPY, "numpy")
    def test_timbre_et_intonation_a_part(self):
        """« Le ton est encore trop britannique » : les 128 premieres valeurs
        (le timbre) d'un melange, les 128 dernieres (l'intonation) d'un autre."""
        pack = {"ff_siwis": np.full((510, 1, 256), 10.0, np.float32),
                "bm_lewis": np.zeros((510, 1, 256), np.float32)}
        s = J.style_kokoro(pack, "fr_jarvis")
        e = J.VOIX_KOKORO_FR["fr_jarvis"]
        self.assertAlmostEqual(float(s[0, 0, 0]), 10 * e["timbre"]["ff_siwis"], places=4)
        self.assertAlmostEqual(float(s[0, 0, 127]), 10 * e["timbre"]["ff_siwis"], places=4)
        self.assertAlmostEqual(float(s[0, 0, 128]), 10 * e["prosodie"]["ff_siwis"], places=4)
        self.assertGreater(e["prosodie"]["ff_siwis"], e["timbre"]["ff_siwis"],
                           "plus d'intonation francaise que de timbre")
        self.assertEqual(J.voix_de_kokoro(e), {"ff_siwis", "bm_lewis"})

    def test_une_erreur_windows_en_francais_se_lit(self):
        """« 'utf-8' codec can't decode byte 0xe8 » : Windows repond dans sa
        langue et son encodage ; on relit les octets au lieu de perdre la cause."""
        brut = "Erreur DML : La procédure spécifiée est introuvable. Accès système.".encode("cp1252")
        try:
            brut.decode("utf-8")
        except UnicodeDecodeError as e:
            r = J.raison_erreur(e)
        if os.name != "nt":
            self.assertIn("procédure spécifiée est introuvable", r)
            self.assertIn("Accès système", r)
        self.assertNotIn("codec can't decode", r)
        self.assertEqual(J.raison_erreur(RuntimeError("une\n  ligne")), "une ligne")

    def test_directml_ne_se_precharge_que_sous_windows(self):
        if os.name != "nt":
            self.assertIsNone(J.precharger_directml(object()))

    def test_la_carte_graphique_d_abord(self):
        dispo = ["DmlExecutionProvider", "CPUExecutionProvider"]
        self.assertEqual(J.accelerateurs_kokoro(dispo, ""), ["DmlExecutionProvider", "CPUExecutionProvider"])
        self.assertEqual(J.accelerateurs_kokoro(["CPUExecutionProvider"], ""), ["CPUExecutionProvider"],
                         "sans carte graphique, le processeur")
        self.assertEqual(J.accelerateurs_kokoro(dispo, "cpu"), ["CPUExecutionProvider"], "on peut s'en passer")
        self.assertEqual(J.accelerateurs_kokoro(dispo, "cuda"), ["CPUExecutionProvider"],
                         "un moteur force mais absent : le processeur")


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
        # Une phrase qui parle DE Jarvis n'est pas un appel (est_une_mention)
        loin = "je regardais un film hier soir avec mon frere et Jarvis parlait"
        self.assertTrue(J.est_une_mention(loin))

    def test_l_appel_au_bout_d_une_longue_phrase(self):
        # la phrase part d'un peu avant l'eveil : ce qui precede le nom n'est
        # pas la demande, meme loin
        self.assertEqual(J.retirer_mot_eveil(
            "je regardais un film hier soir avec mon frere. Jarvis, allume la lumière."), "allume la lumière.")
        self.assertEqual(J.retirer_mot_eveil("Jarvis ? Jarvis ! Allume la lumière."), "Allume la lumière.")
        self.assertEqual(J.retirer_mot_eveil("Jarvis ? Euh, allume la lumière."), "allume la lumière.")
        self.assertEqual(J.retirer_mot_eveil("Jarvis ? Jarvis !"), "")
        self.assertEqual(J.retirer_mot_eveil("Hé Jarvis !"), "")

    def test_le_nom_a_la_fin(self):
        self.assertEqual(J.retirer_mot_eveil("baisse le son, Jarvis"), "baisse le son")
        # ... seulement si on parlait vraiment avant le nom : sinon c'etait la
        # fin de sa reponse d'avant, ou la tele
        self.assertEqual(J.retirer_mot_eveil("baisse le son, Jarvis", garder_avant=False), "")
        self.assertEqual(J.retirer_mot_eveil("il fait beau. Bon, Jarvis"), "")

    def test_une_mention_n_est_pas_un_appel(self):
        for t in ("j'ai l'impression que Jarvis écoute tout le temps", "Jarvis il apparaît pour rien",
                  "le Jarvis que j'ai codé", "Jarvis m'a encore coupé", "Jarvis est nul"):
            self.assertTrue(J.est_une_mention(t), t)
        for t in ("Jarvis est-ce que tu peux baisser le son", "Jarvis allume la lumière",
                  "Jarvis, il fait froid", "baisse le son Jarvis", "Jarvis ?"):
            self.assertFalse(J.est_une_mention(t), t)

    def test_une_question_n_est_pas_une_mention(self):
        # « Jarvis il est quelle heure ? » sans virgule : il se rendormait
        for t in ("Jarvis il est quelle heure ?", "Jarvis il est quelle", "Jarvis elle est où ma clé",
                  "euh Jarvis il fait combien dehors"):
            self.assertFalse(J.est_une_mention(t), t)
        for t in ("Jarvis il apparaît pour rien", "Jarvis il marche pas.", "Jarvis il",
                  "j'ai l'impression que Jarvis écoute tout le temps"):
            self.assertTrue(J.est_une_mention(t), t)
        # le bout de son d'une verification : on ne voit pas encore la suite
        self.assertFalse(J.est_une_mention("Jarvis il", tronque=True))
        self.assertTrue(J.est_une_mention("Jarvis il apparaît", tronque=True))

    def test_une_mention_avec_le_nom_ecorche(self):
        # « Javi » confirme un appel pas net : il doit aussi reconnaitre une mention
        self.assertTrue(J.est_une_mention("le Javi que j'ai codé"))
        self.assertFalse(J.est_une_mention("Javi, allume la lumière"))

    def test_le_nom_au_milieu_de_la_demande(self):
        # « Rappelle-moi Jarvis dans dix minutes... » : le debut etait jete
        t = J.retirer_mot_eveil("Rappelle-moi Jarvis dans dix minutes de sortir le linge", garder_avant=True)
        self.assertEqual(t, "Rappelle-moi dans dix minutes de sortir le linge")
        self.assertEqual(J.comprendre(t)["action"], "minuteur")
        self.assertEqual(J.retirer_mot_eveil("Mets la musique, Jarvis, de Daft Punk"), "Mets la musique de Daft Punk")
        self.assertEqual(J.retirer_mot_eveil("Allume, Jarvis, la lumière."), "Allume la lumière.")
        # ... pas quand la suite est deja une commande, ni sans parole avant le nom
        self.assertEqual(J.retirer_mot_eveil("Il fait beau aujourd hui Jarvis allume la lumière"),
                         "allume la lumière")
        self.assertEqual(J.retirer_mot_eveil("Salut Jarvis, allume la lumière"), "allume la lumière")
        self.assertEqual(J.retirer_mot_eveil("Salut Jarvis, dis-moi une blague"), "dis-moi une blague")
        self.assertEqual(J.retirer_mot_eveil("Rappelle-moi Jarvis dans dix minutes", garder_avant=False),
                         "dans dix minutes")
        # « merci beaucoup » n'est pas la demande : il terminait la conversation
        self.assertEqual(J.retirer_mot_eveil("Baisse le son Jarvis, merci beaucoup."), "Baisse le son")
        self.assertEqual(J.retirer_mot_eveil("Jarvis, allume la lumière."), "allume la lumière.")


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
        # « il galere a comprendre quand je parle » : on vient de commencer, une
        # pause pour chercher ses mots est permise (1 s) ; « plus fluide » : il
        # n'attend plus 1,2 s a la fin de chaque phrase
        fin, t = self.jouer("......" + "p" * 15 + "." * 30)
        self.assertEqual(fin, "fini")
        self.assertAlmostEqual(t, (6 + 15 + 13) * 0.08, delta=0.09)
        # passe deux secondes de parole : 0,75 s suffit
        fin, t = self.jouer("......" + "p" * 30 + "." * 30)
        self.assertEqual(fin, "fini")
        self.assertAlmostEqual(t, (6 + 30 + 10) * 0.08, delta=0.09)

    def test_une_pause_pour_chercher_ses_mots(self):
        # « mets la musique de... Daft Punk » : 0,9 s de pause au debut
        fin, t = self.jouer("......" + "p" * 10 + "." * 11 + "p" * 6 + "." * 30)
        self.assertEqual(fin, "fini")
        self.assertGreater(t, (6 + 10 + 11 + 6) * 0.08, "la suite est prise")

    def test_un_clic_n_est_pas_une_phrase(self):
        # un clavier, une porte : une trame isolee ne compte pas -- un mot, si
        fin, t = self.jouer("......" + "p.." * 30)
        self.assertEqual(fin, "vide")
        self.assertAlmostEqual(t, 5.0, delta=0.09)
        fin, _ = self.jouer("......" + "pppp" + "." * 30)      # un « oui »
        self.assertEqual(fin, "fini")

    def test_la_voix_qui_continue_plus_bas(self):
        # une syllabe plus basse (le « doux ») ne ferme pas la phrase
        doux = lambda rms: rms > 100
        ph = J.Phrase(self.PARLE, doux=doux)
        seq = [2000.0] * 10 + [150.0] * 14 + [2000.0] * 5 + [30.0] * 20
        for i, r in enumerate(seq):
            if ph.trame(np.zeros(J.TRAME, np.int16), r):
                break
        self.assertGreater(i, 10 + 14 + 5, "la syllabe basse n'a pas ferme la phrase")

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
        self.assertAlmostEqual(t, J.PHRASE_MAX_S, delta=0.09)
        fin, t = self.jouer("p" * 900, duree_max=J.PHRASE_PSY_MAX_S)      # le psychologue en laisse plus
        self.assertAlmostEqual(t, J.PHRASE_PSY_MAX_S, delta=0.09)

    def test_un_effleurement_ne_ferme_pas_l_ecoute(self):
        """« Je vous ecoute encore un instant » -- et il se rendormait 1,5 s
        plus tard : la queue de sa voix (une enceinte Bluetooth en retard), la
        reverberation. Un bout de moins de deux trames ne ferme plus la fenetre."""
        for seq in ("...ppp", "....pp"):
            fin, t = self.jouer(seq + "." * 110, attente=8.0, ignorer=0.35)
            self.assertEqual((fin, t), ("vide", 8.0), seq)
        # une vraie reponse, meme courte, apres l'effleurement
        fin, t = self.jouer("....pp" + "." * 20 + "pppp" + "." * 30, attente=8.0, ignorer=0.35)
        self.assertEqual(fin, "fini")
        # et un nom dit a la fin de la demande reste fini
        self.assertEqual(self.jouer(".pp" + "." * 30, deja_dit=True, ignorer=0.0)[0], "fini")

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
        return [e["evt"] for e in self.sorties if e["evt"] not in ("voix_niveau", "essai")]

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
        # reveille par « Hey Jarvis », et on lui a vraiment parle ensuite : cette
        # facon de l'appeler est gardee (l'etalonnage au fil de l'eau)
        self.assertEqual(self.evts(), ["reveil", "phrase", "gabarit_auto"])
        self.assertEqual(len([e for e in self.sorties if e["evt"] == "gabarit_auto"][0]["vecteurs"][0]), 96)
        with wave.open(io.BytesIO(base64.b64decode([e for e in self.sorties if e["evt"] == "phrase"][0]["wav"]))) as w:
            # Les deux secondes d'avant l'eveil sont la : « Jarvis » y est, et
            # la transcription le retire.
            self.assertGreater(w.getnframes() / 16000.0, 2.5)

    def test_un_appel_sans_suite_n_apprend_rien(self):
        for _ in range(15):
            self.o.trame(trame())
        self.o.trame(trame(parole=True, marque=True))
        for _ in range(80):
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["reveil", "vide"], "personne n'a parle apres : rien a garder")

    def test_sans_etalonnage_rien_n_est_garde(self):
        self.o.commande({"cmd": "config", "auto": False})
        for _ in range(15):
            self.o.trame(trame())
        self.o.trame(trame(parole=True, marque=True))
        for _ in range(8):
            self.o.trame(trame())
        for _ in range(12):
            self.o.trame(trame(parole=True))
        for _ in range(20):
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["reveil", "phrase"])

    def test_le_nom_a_la_fin_de_la_demande(self):
        # « baisse le son de Spotify, Jarvis » : la demande est AVANT le nom ;
        # rien ne suit -- c'est une phrase, pas « vide » cinq secondes plus tard
        for _ in range(15):
            self.o.trame(trame())
        for _ in range(28):
            self.o.trame(trame(parole=True))
        self.o.trame(trame(parole=True, marque=True))
        n = 0
        while self.evts()[-1] == "reveil" and n < 100:
            self.o.trame(trame())
            n += 1
        self.assertEqual(self.evts()[:2], ["reveil", "phrase"])
        self.assertLessEqual(n * J.TRAME_S, J.PHRASE_DEJA_DITE_S + 0.2)

    def test_le_nom_seul_attend_la_suite(self):
        for _ in range(40):
            self.o.trame(trame())
        self.o.trame(trame(parole=True, marque=True))
        for _ in range(35):                    # 2,8 s de silence : il attend encore
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["reveil"])

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
        # le son de ce « Jarvis » part a Machi Tool, le temps de lire comment la
        # transcription l'ecrit (voir noms_entendus) ; rien du son n'est garde
        self.assertTrue(base64.b64decode(self.sorties[0]["wav"]).startswith(b"RIFF"))
        self.assertGreater(self.sorties[0]["niveau"], 0, "le niveau de ta voix, pour caler les portes")

    def test_apprendre_sans_rien_dire(self):
        self.o.commande({"cmd": "apprendre"})
        for _ in range(60):
            self.o.trame(trame())
        self.assertEqual(self.sorties[0].get("erreur"), "rien entendu")


# ======================================================================
#  COMMENT IL ECOUTE UNE PHRASE (la fin, la suite, le fond, par-dessus lui)
# ======================================================================

def trame_vad(rms, p, marque=None):
    """Une trame de niveau `rms`, dont le VAD scripte lira la probabilite `p`."""
    x = (np.sin(np.arange(J.TRAME) * 0.3) * rms * np.sqrt(2)).astype(np.int16)
    x[1] = int(round(p * 1000))
    if marque is not None:
        x[5] = marque
    return x


class VadScripte:
    """Le VAD lit la probabilite que le test a mise dans la trame."""
    def trame(self, x):
        return int(x[1]) / 1000.0


class SansMot:
    """Aucun mot d'eveil (pas de « hey », pas de gabarit)."""
    hey_m = None

    def trame(self, x):
        return 0.0, np.zeros(96, np.float32)


def parle_marque(marque):
    x = trame(parole=True)
    x[5] = marque
    return x


def compte(wav64, marque):
    with wave.open(io.BytesIO(base64.b64decode(wav64))) as w:
        s = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return int(np.sum(s == marque))


def duree(wav64):
    with wave.open(io.BytesIO(base64.b64decode(wav64))) as w:
        return w.getnframes() / 16000.0


@unittest.skipUnless(NUMPY, "numpy absent")
class LEcoute(unittest.TestCase):
    def setUp(self):
        self.sorties, self.sons = [], []
        self.o = J.Oreille(FaussesEmpreintes(), self.sorties.append, self.sons.append)
        self.o.niveau_vu = float("inf")
        for _ in range(20):                      # le calme de la piece : le plancher s'y cale
            self.o.trame(trame())

    def evts(self):
        return [e["evt"] for e in self.sorties if e["evt"] not in ("voix_niveau", "essai")]

    def phrases(self):
        return [e for e in self.sorties if e["evt"] == "phrase"]

    def _premiere_partie(self):
        """« Mets la musique de... » : une phrase qui se ferme sur la pause."""
        self.o.commande({"cmd": "ecouter", "attente": 5.0})
        for _ in range(12):
            self.o.trame(trame(parole=True))
        for _ in range(40):
            if "phrase" in self.evts():
                break
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["phrase"])

    def test_la_suite_d_une_phrase_en_suspens_n_est_plus_perdue(self):
        """« ... Daft Punk », dit pendant qu'il transcrivait la premiere moitie :
        il n'ecoutait plus, ces mots tombaient dans le vide. Maintenant la
        suite repart de la fin de la phrase -- et la phrase entiere est devant."""
        self._premiere_partie()
        for _ in range(3):
            self.o.trame(trame())
        for _ in range(3):                       # la personne reprend PENDANT la transcription
            self.o.trame(parle_marque(7003))
        self.o.commande({"cmd": "ecouter", "attente": 3.0, "reprise": True, "ignorer": 0.0})
        for _ in range(10):
            self.o.trame(parle_marque(7003))
        for _ in range(30):
            self.o.trame(trame())
        self.assertEqual(self.evts(), ["phrase", "phrase"])
        suite = self.phrases()[-1]
        self.assertEqual(compte(suite["wav"], 7003), 13, "le trou n'est plus perdu")
        self.assertTrue(suite.get("avec_debut"), "la premiere moitie est devant")
        self.assertGreater(duree(suite["wav"]), duree(self.phrases()[0]["wav"]) + 13 * J.TRAME_S)

    def test_une_suite_deja_finie_quand_il_rouvre(self):
        # toute la suite dite dans le trou : elle n'attend pas trois secondes pour finir « vide »
        self._premiere_partie()
        for _ in range(2):
            self.o.trame(trame())
        for _ in range(6):
            self.o.trame(parle_marque(7004))
        for _ in range(8):
            self.o.trame(trame())
        self.o.commande({"cmd": "ecouter", "attente": 3.0, "reprise": True, "ignorer": 0.0})
        n = 0
        while len(self.evts()) < 2 and n < 60:
            self.o.trame(trame())
            n += 1
        self.assertEqual(self.evts(), ["phrase", "phrase"])
        self.assertLessEqual(n, 8, "la pause etait deja en cours")
        self.assertEqual(compte(self.phrases()[-1]["wav"], 7004), 6)

    def test_apres_une_coupure_la_suite_sans_le_debut(self):
        # « attends... » par-dessus lui : sa voix est dans la phrase d'avant, on ne la remet pas
        self._premiere_partie()
        self.o.commande({"cmd": "ecouter", "attente": 3.0, "reprise": True, "debut": False})
        for _ in range(6):
            self.o.trame(parle_marque(7005))
        for _ in range(20):
            self.o.trame(trame())
        suite = self.phrases()[-1]
        self.assertFalse(suite.get("avec_debut"))
        self.assertLess(duree(suite["wav"]), 3.0)

    def test_le_psychologue_laisse_des_silences(self):
        """« Je me sens... [1,2 s] ...completement vide » : une seule phrase."""
        seq = [True] * 30 + [False] * 15 + [True] * 20 + [False] * 30
        self.o.commande({"cmd": "ecouter", "attente": 10.0, "pause": J.PHRASE_PSY_PAUSE_S})
        for p in seq:
            self.o.trame(trame(parole=p))
        self.assertEqual(self.evts(), ["phrase"])
        self.assertGreater(duree(self.phrases()[0]["wav"]), 5.0, "la pensee entiere")
        # chez le majordome, rien ne change : la pause de 0,75 s ferme
        self.sorties.clear()
        self.o.commande({"cmd": "ecouter", "attente": 10.0})
        for p in seq:
            self.o.trame(trame(parole=p))
        self.assertLess(duree(self.phrases()[0]["wav"]), 3.5)

    def test_ecouter_n_ecrase_pas_la_coupure(self):
        """« Voulez-vous que je le lance ? » -- « Oui ! » : la coupure et la fin
        de sa voix se croisent ; l'« ecouter » qui arrive ne jette plus le debut."""
        o = self.o
        o.phrase = o._nouvelle_phrase(avant=np.zeros(int(0.6 * J.FREQ), np.int16), attente=1.5, ignorer=0.0)
        o.etat, o.apres_coupure = "phrase", True
        o.trame(trame(parole=True))
        o.commande({"cmd": "ecouter", "attente": 5.0})
        for _ in range(10):
            o.trame(trame(parole=True))
        for _ in range(20):
            o.trame(trame())
        self.assertEqual(self.evts(), ["phrase"])
        self.assertTrue(self.phrases()[0].get("apres_coupure"), "toujours la reponse a sa coupure")
        self.assertGreater(duree(self.phrases()[0]["wav"]), 0.6 + 11 * J.TRAME_S)

    # ---------------- la tele, la musique ----------------

    def _oreille_tele(self):
        sorties = []
        o = J.Oreille(SansMot(), sorties.append, lambda g: None)
        o.niveau_vu = float("inf")
        o.det.vad = VadScripte()
        o.commande({"cmd": "config", "niveau_voix": 2500.0})
        rng = np.random.default_rng(5)

        def tele():
            if rng.random() < 0.85:
                return trame_vad(rng.uniform(250, 600), rng.uniform(0.5, 0.95))
            return trame_vad(80, 0.1)
        return o, sorties, tele

    @staticmethod
    def _quand(sorties, trames, oreille, evt=("phrase", "vide")):
        for i, x in enumerate(trames):
            oreille.trame(x)
            fins = [e["evt"] for e in sorties if e["evt"] in evt]
            if fins:
                return fins[0], i + 1
        return None, None

    def test_la_tele_ne_tient_plus_la_phrase_ouverte(self):
        """« Jarvis, baisse le son » avec la tele allumee : la phrase ne se
        fermait qu'a 30 s (la tele parlait encore), et la tele entrait dans
        ta demande."""
        o, sorties, tele = self._oreille_tele()
        for _ in range(150):
            o.trame(tele())                       # il dort, la tele parle
        o.commande({"cmd": "ecouter", "attente": 4.0})
        toi = [trame_vad(2500, 0.95) for _ in range(20)]
        fin, i = self._quand(sorties, toi + [tele() for _ in range(400)], o)
        self.assertEqual(fin, "phrase")
        self.assertLessEqual((i - 20) * J.TRAME_S, 1.2, "fermee %.2f s apres toi" % ((i - 20) * J.TRAME_S))

    def test_la_tele_seule_n_est_pas_une_reponse(self):
        o, sorties, tele = self._oreille_tele()
        for _ in range(150):
            o.trame(tele())
        o.commande({"cmd": "ecouter", "attente": 4.0})
        fin, i = self._quand(sorties, [tele() for _ in range(400)], o)
        self.assertEqual(fin, "vide", "personne ne lui a repondu")
        self.assertAlmostEqual(i * J.TRAME_S, 4.0, delta=0.2)

    def test_ta_voix_plus_basse_ne_ferme_pas_la_phrase(self):
        # 10 dB sous ton « Jarvis », pendant une seconde, la tele derriere
        o, sorties, tele = self._oreille_tele()
        for _ in range(150):
            o.trame(tele())
        o.commande({"cmd": "ecouter", "attente": 4.0})
        toi = [trame_vad(2500, 0.95) for _ in range(10)] + [trame_vad(800, 0.9) for _ in range(12)]
        fin, i = self._quand(sorties, toi + [tele() for _ in range(400)], o)
        self.assertEqual(fin, "phrase")
        self.assertGreater(i, 22, "pas fermee pendant que tu parlais plus bas")
        self.assertLessEqual((i - 22) * J.TRAME_S, 1.2)

    def test_dans_le_calme_rien_ne_change(self):
        o, sorties, _ = self._oreille_tele()
        for _ in range(150):
            o.trame(trame_vad(20, 0.02))
        o.commande({"cmd": "ecouter", "attente": 4.0})
        fin, i = self._quand(sorties, [trame_vad(2500, 0.95)] * 20 + [trame_vad(20, 0.02)] * 60, o)
        self.assertEqual(fin, "phrase")
        self.assertEqual(i, 20 + 13, "la pause de 1 s, comme avant")
        self.assertEqual(o.phrase, None)

    # ---------------- pendant qu'il parle ----------------

    class CoupureStub:
        def __init__(s, coupe=False):
            s.coupe, s.appels = coupe, []

        def armer(s, t):
            pass

        def desarmer(s, garder=True):
            s.appels.append("desarmer")

        def reference(s, x, t):
            pass

        def micro(s, x, t):
            return s.coupe

        def pret(s):
            return True

    def _pendant_qu_il_parle(self, nom, coupe=False, erreur=None):
        sorties, horloge = [], {"t": 100.0}
        lb = FauxLoopback()
        lb.erreur = erreur
        o = J.Oreille(FaussesEmpreintes(), sorties.append, lambda g: None, lb, horloge=lambda: horloge["t"])
        o.niveau_vu = float("inf")
        o.coupure = self.CoupureStub(coupe)
        for _ in range(20):
            o.trame(trame())
        o.commande({"cmd": "parole", "actif": True, "nom": nom})

        def jouer(x):
            horloge["t"] += J.TRAME_S
            lb.blocs.append((horloge["t"], np.zeros(J.TRAME, np.float32)))
            o.trame(x)
        return o, sorties, jouer, horloge, lb

    def test_jarvis_par_dessus_sa_voix_le_coupe(self):
        """Sur un portable, personne ne parle plus fort que son echo : la
        coupure ne l'entendait pas, et le mot d'eveil ne cherchait plus."""
        o, sorties, jouer, _, _ = self._pendant_qu_il_parle(nom=False)
        for _ in range(10):
            jouer(trame())
        jouer(trame(parole=True, marque=True))
        self.assertIn("reveil", [e["evt"] for e in sorties])
        self.assertFalse(o.parole, "il se tait")

    def test_son_propre_nom_ne_le_reveille_pas(self):
        o, sorties, jouer, _, _ = self._pendant_qu_il_parle(nom=True)
        for _ in range(10):
            jouer(trame())
        jouer(trame(parole=True, marque=True))
        self.assertEqual([e["evt"] for e in sorties], [])
        self.assertTrue(o.parole)

    def test_un_appel_pas_net_pendant_qu_il_parle_n_est_pas_verifie(self):
        sorties = []
        o = J.Oreille(FaussesEmpreintes(), sorties.append, lambda g: None, None)
        o.niveau_vu = float("inf")
        for _ in range(20):
            o.trame(trame())
        o.det.seuil_hey = 1.5                    # 0,95 : pas net
        o.commande({"cmd": "parole", "actif": True, "nom": False})
        for _ in range(5):
            o.trame(trame(parole=True))
        o.trame(trame(parole=True, marque=True))
        for _ in range(10):
            o.trame(trame())
        self.assertNotIn("verifier", [e["evt"] for e in sorties], "sa propre voix : rien a verifier")
        o.commande({"cmd": "parole", "actif": False})
        o.det.repos_jusqua = 0
        for _ in range(5):
            o.trame(trame(parole=True))
        o.trame(trame(parole=True, marque=True))
        for _ in range(10):
            o.trame(trame())
        self.assertIn("verifier", [e["evt"] for e in sorties], "il s'est tu : on verifie comme avant")

    def test_sans_reference_vivante_il_ne_se_coupe_pas(self):
        """Une sortie son changee, un loopback tombe : l'echo predit valait
        zero et il se coupait sur sa propre voix, au bout d'une seconde et demie."""
        o, sorties, jouer, horloge, lb = self._pendant_qu_il_parle(nom=True, coupe=True, erreur="OSError : x")
        for _ in range(5):
            jouer(trame(parole=True))
        self.assertNotIn("coupure", [e["evt"] for e in sorties])
        lb.erreur = None                          # rouvert : la coupure revient
        jouer(trame(parole=True))
        self.assertIn("coupure", [e["evt"] for e in sorties])
        # une reference qui n'envoie plus rien depuis plus de 0,3 s
        o, sorties, _, horloge, lb = self._pendant_qu_il_parle(nom=True, coupe=True)
        horloge["t"] += 0.6
        for _ in range(5):
            horloge["t"] += J.TRAME_S
            o.trame(trame(parole=True))
        self.assertNotIn("coupure", [e["evt"] for e in sorties])

    def test_le_loopback_rouvert_oublie_son_erreur(self):
        class Rec:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def record(s, numframes):
                time.sleep(0.002)
                return np.zeros((numframes, 1), np.float32)
        lb = J.Loopback(ouvrir=Rec)
        lb.erreur = "OSError : ancienne"
        lb.demarrer()
        for _ in range(200):
            if lb.blocs:
                break
            time.sleep(0.01)
        lb.arreter()
        lb.fil.join(2)
        self.assertIsNone(lb.erreur)


class EmpreintesEcrites:
    """Des empreintes dictees par le test, trame apres trame (pas de modele)."""
    hey_m = None

    def __init__(self):
        self.a_venir = []
        self.rng = np.random.default_rng(11) if NUMPY else None

    def trame(self, x):
        if self.a_venir:
            return 0.0, self.a_venir.pop(0)
        return 0.0, self.rng.normal(size=96).astype(np.float32)


@unittest.skipUnless(NUMPY, "numpy absent")
class EtalonnageAuFilDeLEau(unittest.TestCase):
    """« Mieux etalonner les Jarvis, de sorte que je puisse l'appeler avec
    beaucoup de tons differents. » Un appel rate de peu, puis repete et
    reconnu : la facon ratee est gardee -- si on lui parle vraiment ensuite."""

    def setUp(self):
        rng = np.random.default_rng(7)
        self.g = J.normer(rng.normal(size=(9, 96)))
        # le meme mot dit autrement : assez loin pour ne pas passer, assez pres
        # pour etre « presque »
        seuil = J.seuil_gabarit(0.5)
        bruit = rng.normal(size=self.g.shape)
        bas, haut = 0.0, 2.0
        for _ in range(40):                          # vise 1,4 fois le seuil
            eps = (bas + haut) / 2
            if J.distance_eveil(self.g, J.normer(self.g + eps * bruit)) > 1.4 * seuil:
                haut = eps
            else:
                bas = eps
        self.autrement = v = J.normer(self.g + eps * bruit)
        self.assertTrue(seuil < J.distance_eveil(self.g, v) < seuil * J.PRESQUE_FACTEUR)
        self.e = EmpreintesEcrites()
        self.sorties = []
        self.o = J.Oreille(self.e, self.sorties.append)
        self.o.niveau_vu = float("inf")
        # l'etalonnage seul : sans la zone tolerante (voir TresTolerant)
        self.o.commande({"cmd": "config", "gabarits": [self.g.tolist()], "son": False, "tolerant": False})

    def dire(self, vecteurs, parole=True):
        for v in vecteurs:
            self.e.a_venir.append(np.asarray(v, dtype=np.float32))
            self.o.trame(trame(parole=parole))

    def silence(self, n):
        self.dire([np.random.default_rng(n).normal(size=96) for _ in range(n)], parole=False)

    def evts(self):
        return [e["evt"] for e in self.sorties if e["evt"] not in ("voix_niveau", "essai")]

    def test_l_appel_rate_puis_repete_est_appris(self):
        self.silence(20)
        self.dire(self.autrement)                    # « Jarviiis ? » : rate de peu
        self.silence(15)
        self.assertNotIn("reveil", self.evts())
        self.dire(self.g)                            # « Jarvis ! » : reconnu
        self.assertIn("reveil", self.evts())
        self.silence(4)
        self.dire([np.random.default_rng(99).normal(size=96)] * 12)      # la demande
        self.silence(20)
        self.assertEqual([e for e in self.evts() if e != "presque"], ["reveil", "phrase", "gabarit_auto"])
        appris = J.normer([e for e in self.sorties if e["evt"] == "gabarit_auto"][0]["vecteurs"])
        self.assertLess(J.distance_gabarit(appris, self.autrement), 0.02, "c'est la facon ratee qu'il garde")
        # et desormais, dite ainsi, elle passe
        self.o.commande({"cmd": "config", "gabarits": [self.g.tolist(), appris.tolist()]})
        self.silence(30)
        n = len(self.sorties)
        self.dire(self.autrement)
        self.assertIn("reveil", [e["evt"] for e in self.sorties[n:]])

    def test_rate_mais_rien_ne_suit_rien_n_est_garde(self):
        self.silence(20)
        self.dire(self.autrement)
        self.silence(15)
        self.dire(self.g)
        self.silence(80)                             # reveille, mais personne ne parle
        self.assertNotIn("gabarit_auto", self.evts())


@unittest.skipUnless(NUMPY, "numpy absent")
class SeulementMaVoix(unittest.TestCase):
    """« Jarvis s'active parfois, fait qu'il n'ecoute que mon micro avec mon
    son, avec le bon volume. » Ta voix apprise : ton « Jarvis » a ton volume le
    reveille ; le meme mot plus bas (la tele, une video plus loin) non, et le
    modele anglais, qui ne connait personne, se tait."""

    NIVEAU = 2000.0

    def setUp(self):
        self.g = J.normer(np.random.default_rng(7).normal(size=(9, 96)))
        self.e = EmpreintesEcrites()
        self.sorties = []
        self.o = J.Oreille(self.e, self.sorties.append)
        self.o.niveau_vu = float("inf")
        self.config(True)

    def config(self, ma_voix, gabarits=True):
        self.o.commande({"cmd": "config", "gabarits": [self.g.tolist()] if gabarits else [], "son": False,
                         "tolerant": False, "niveau_voix": self.NIVEAU, "ma_voix": ma_voix})

    def dire(self, vecteurs, amplitude):
        for v in vecteurs:
            self.e.a_venir.append(np.asarray(v, dtype=np.float32))
            self.o.trame((np.sin(np.arange(J.TRAME) * 0.3) * amplitude).astype(np.int16))

    def silence(self, n):
        self.dire([np.random.default_rng(n).normal(size=96) for _ in range(n)], 20)

    def reveils(self):
        return [e for e in self.sorties if e["evt"] == "reveil"]

    def test_ton_jarvis_a_ton_volume_le_reveille(self):
        self.silence(20)
        self.dire(self.g, 2900)                  # ~2050 de niveau : toi, au micro
        self.assertEqual(len(self.reveils()), 1)

    def test_le_meme_mot_trop_bas_ne_le_reveille_pas(self):
        self.silence(20)
        self.dire(self.g, 700)                   # ~500 : la tele, plus loin
        self.silence(20)
        self.assertEqual(self.reveils(), [])
        self.assertGreater(self.o.det.trop_loin, 0)
        # l'option decochee : le meme son passe, comme avant
        self.config(False)
        self.silence(30)
        self.dire(self.g, 700)
        self.assertEqual(len(self.reveils()), 1)

    def test_sans_voix_apprise_rien_ne_change(self):
        self.config(True, gabarits=False)
        self.assertFalse(self.o.det.seule_ta_voix(), "sans voix apprise, il resterait sourd")

    def test_le_modele_anglais_se_tait(self):
        sorties = []
        o = J.Oreille(FaussesEmpreintes(), sorties.append)
        o.niveau_vu = float("inf")
        o.commande({"cmd": "config", "gabarits": [self.g.tolist()], "son": False, "niveau_voix": 2000.0,
                    "ma_voix": True})
        for _ in range(15):
            o.trame(trame())
        o.trame(trame(parole=True, marque=True))      # « Hey Jarvis » de la tele
        for _ in range(10):
            o.trame(trame())
        self.assertNotIn("reveil", [e["evt"] for e in sorties])
        o.commande({"cmd": "config", "ma_voix": False})
        for _ in range(30):
            o.trame(trame())
        o.trame(trame(parole=True, marque=True))
        self.assertIn("reveil", [e["evt"] for e in sorties])


@unittest.skipUnless(NUMPY, "numpy absent")
class TresTolerant(EtalonnageAuFilDeLEau):
    """« Il ne se declenche pas assez : il faudrait qu'il soit tres tolerant
    au mot Jarvis. » Un appel pas net : ecoute en silence, verifie par
    transcription, reveil seulement si c'etait lui."""

    def setUp(self):
        super().setUp()
        self.sons = []
        self.o.jouer = self.sons.append
        self.o.commande({"cmd": "config", "tolerant": True, "son": True})

    def appel_pas_net(self):
        self.silence(20)
        self.dire(self.autrement)
        self.silence(J.TOLERANCE_ATTENTE + 1)
        self.assertEqual([e for e in self.evts() if e != "presque"], ["verifier"])
        self.assertEqual(self.sons, [], "pas de carillon tant que ce n'est pas sur")
        v = [e for e in self.sorties if e["evt"] == "verifier"][0]
        self.assertTrue(base64.b64decode(v["wav"]).startswith(b"RIFF"), "le son a transcrire")

    def test_confirme_il_se_reveille_et_la_phrase_suit(self):
        self.appel_pas_net()
        self.o.commande({"cmd": "verifie", "ok": True})
        self.assertEqual(self.sons, ["eveil"])
        self.assertEqual([e for e in self.evts() if e != "presque"][-1], "reveil")
        self.assertTrue(self.sorties[-1]["verifie"])
        self.dire([np.random.default_rng(5).normal(size=96)] * 12)
        self.silence(20)
        self.assertIn("phrase", self.evts())

    def test_ecarte_il_se_rendort_sans_un_bruit(self):
        self.appel_pas_net()
        self.o.commande({"cmd": "verifie", "ok": False})
        self.dire([np.random.default_rng(6).normal(size=96)] * 12)
        self.silence(20)
        self.assertEqual([e for e in self.evts() if e not in ("presque", "gabarit_auto")], ["verifier"])
        self.assertEqual(self.sons, [])
        self.assertEqual(self.o.etat, "veille")

    def test_la_phrase_finie_avant_le_verdict_l_attend(self):
        self.appel_pas_net()
        self.dire([np.random.default_rng(7).normal(size=96)] * 12)
        self.silence(30)
        self.assertNotIn("phrase", self.evts(), "pas avant le verdict")
        self.o.commande({"cmd": "verifie", "ok": True})
        self.assertEqual([e for e in self.evts() if e not in ("presque", "gabarit_auto")],
                         ["verifier", "reveil", "phrase"])

    def test_net_il_se_reveille_tout_de_suite(self):
        self.silence(20)
        self.dire(self.g)
        self.assertIn("reveil", self.evts())
        self.assertEqual(self.sons, ["eveil"])

    def test_sans_reponse_il_laisse_tomber(self):
        self.appel_pas_net()
        self.silence(J.VERIF_ATTENTE_TRAMES + 5)
        self.assertIsNone(self.o.doute)
        self.assertNotIn("reveil", self.evts())

    # l'heritage : ces deux-la ne valent que sans zone tolerante
    test_l_appel_rate_puis_repete_est_appris = None
    test_rate_mais_rien_ne_suit_rien_n_est_garde = None


@unittest.skipUnless(NUMPY, "numpy absent")
class UnBruitNEstPasUnMot(EtalonnageAuFilDeLEau):
    """« Il se declenche tout seul des qu'il y a un bruit dans le micro. » Un
    mot a une duree : il faut au moins TRAMES_VOISEES_MIN trames de parole ;
    un clic ou un claquement d'une trame ne reveille rien, meme s'il
    « ressemble »."""

    def test_un_bruit_bref_qui_ressemble_ne_reveille_pas(self):
        self.o.commande({"cmd": "config", "tolerant": True})
        self.silence(20)
        # les empreintes du mot, mais un seul coup de son fort (un claquement)
        for i, v in enumerate(self.g):
            self.e.a_venir.append(np.asarray(v, dtype=np.float32))
            self.o.trame(trame(parole=(i == len(self.g) - 1)))
        self.silence(10)
        self.assertEqual([e for e in self.evts() if e != "presque"], [])

    def test_une_variante_raccourcie_n_est_jamais_minuscule(self):
        g = J.normer(np.random.default_rng(2).normal(size=(10, 96)))
        fen = J.normer(np.random.default_rng(3).normal(size=(20, 96)))
        fen[-5:] = g[3:8]                          # cinq trames du mot, pas plus
        self.assertGreater(J.distance_eveil(g, fen), J.seuil_gabarit(1.0))

    test_l_appel_rate_puis_repete_est_appris = None
    test_rate_mais_rien_ne_suit_rien_n_est_garde = None


class LeNomDansLaTranscription(unittest.TestCase):
    def test_contient_nom(self):
        for t in ("Jarvis, allume", "Jervis ?", "charvis", "bon jar vis mets la musique", "Jarvi", "hé Djarvis"):
            self.assertTrue(J.contient_nom(t), t)
        for t in ("je vais dormir", "Travis Scott", "service", "j'arrive", "garage", "", "j'avais dit",
                  "javel", "Gervais", "jardin", "archives"):
            self.assertFalse(J.contient_nom(t), t)

    def test_comme_la_transcription_l_a_ecrit_a_l_apprentissage(self):
        # « Jarvis galere vraiment a reconnaitre ma voix » : si le moteur ecrit
        # son « Jarvis » « Travis », c'est son nom a lui
        noms = J.noms_entendus("Travis.")
        self.assertIn("travis", noms)
        self.assertTrue(J.contient_nom("travis mets de la musique", noms))
        self.assertFalse(J.contient_nom("travis mets de la musique"))
        self.assertEqual(J.noms_entendus("et oh"), [], "pas les tout petits mots")

    def test_une_phrase_de_calibration_n_apprend_que_le_nom(self):
        # « au bout d'un moment il s'active tout seul » : « Calibrer encore »
        # fait dire le nom au milieu d'une phrase ; seuls les mots proches de
        # « jarvis » deviennent son nom, jamais « lumiere » ni « musique »
        self.assertEqual(J.noms_entendus("Allume la lumiere et Travis mets la musique"), ["travis"])
        self.assertEqual(J.noms_entendus("allume la lumiere et mets la musique"), [])
        self.assertEqual(J.noms_entendus("bon jar vis"), ["jarvis"])
        self.assertFalse(J.contient_nom("mets la musique", ["musique", "lumiere"]),
                         "des noms pollues (v1.59) ne confirment plus rien")
        self.assertEqual(J.nom_trouve("euh Jervis la lumiere"), "jervis")


@unittest.skipUnless(NUMPY, "numpy absent")
class SeuilsDeTaVoix(unittest.TestCase):
    """« Il me faudrait un indicateur de detection, plus de facons de calibrer,
    et un moyen de baisser le seuil. » Les seuils se calent sur l'ecart entre
    TES « Jarvis », et la facilite les deplace."""

    def voix(self, ecart, n=6, graine=4):
        rng = np.random.default_rng(graine)
        base = rng.normal(size=(9, 96))
        return [J.normer(base + ecart * rng.normal(size=base.shape)).tolist() for _ in range(n)]

    def test_le_seuil_personnel_suit_l_ecart_de_ta_voix(self):
        self.assertIsNone(J.seuil_personnel(self.voix(0.3, n=2)), "pas assez de facons")
        reguliere, variable = J.seuil_personnel(self.voix(0.1)), J.seuil_personnel(self.voix(0.5))
        self.assertLess(reguliere, variable)

    def test_une_voix_qui_varie_elargit_la_zone_verifiee(self):
        sans = J.seuils_detection(0.5)
        avec = J.seuils_detection(0.5, 0.14)
        self.assertGreater(avec[1], sans[1])
        self.assertLessEqual(avec[0], J.SEUIL_DIRECT_MAX, "le reveil direct reste prudent")
        self.assertLessEqual(avec[0], avec[1])

    def test_la_facilite_deplace_les_deux_seuils(self):
        bas, milieu, haut = (J.seuils_detection(s, 0.14) for s in (0.0, 0.5, 1.0))
        self.assertLess(bas[1], milieu[1])
        self.assertLess(milieu[1], haut[1])
        self.assertLessEqual(bas[0], haut[0])
        self.assertLessEqual(J.seuils_detection(1.0, 5.0)[1], J.SEUIL_VERIFIE_MAX, "jamais n'importe quoi")
        self.assertGreaterEqual(J.seuils_detection(0.0)[1], J.SEUIL_VERIFIE_MIN)

    def test_sans_zone_tolerante_un_seul_seuil(self):
        d, v = J.seuils_detection(0.5, 0.14, tolerant=False)
        self.assertEqual(d, v)
        self.assertLessEqual(d, J.SEUIL_DIRECT_MAX)

    def test_l_oreille_recoit_ses_seuils(self):
        o = J.Oreille(EmpreintesEcrites(), lambda e: None)
        o.commande({"cmd": "config", "gabarits": self.voix(0.3), "sensibilite": 0.8,
                    "seuil_perso": 0.14, "niveau_voix": 200.0})
        self.assertEqual((o.det.seuil, o.det.seuil_verifie), J.seuils_detection(0.8, 0.14))
        self.assertEqual(o.det.niveau_appris, 200.0)
        # un micro faible, une piece calme : sa voix passe les portes de parole
        o.det.plancher = 30.0
        self.assertTrue(o.det.parle(120.0))
        o.commande({"cmd": "config", "niveau_voix": None})
        self.assertFalse(o.det.parle(120.0))


@unittest.skipUnless(NUMPY, "numpy absent")
class LIndicateurDeDetection(EtalonnageAuFilDeLEau):
    """Chaque mot proche de « Jarvis » : sa distance, et ce qui en est sorti."""

    def essais(self):
        return [e for e in self.sorties if e["evt"] == "essai"]

    def test_un_appel_rate_est_signale_avec_sa_distance(self):
        self.silence(20)
        self.dire(self.autrement)
        self.silence(20)
        (e,) = self.essais()
        self.assertEqual(e["issue"], "rate")
        self.assertAlmostEqual(e["d"], J.distance_eveil(self.g, self.autrement), places=2)
        self.assertGreater(e["d"], e["direct"])

    def test_un_appel_reconnu_est_signale(self):
        self.silence(20)
        self.dire(self.g)
        e = self.essais()[-1]
        self.assertEqual((e["issue"], e["par"]), ("reveil", "voix"))
        self.assertLessEqual(e["d"], e["direct"])

    def test_un_rate_est_signale_meme_quand_la_distance_reste_en_place(self):
        # dans le silence, le detecteur ne compare plus : sa derniere distance
        # reste, et ne doit pas tenir l'essai ouvert indefiniment
        self.silence(20)
        self.dire(self.autrement)
        n = len(self.essais())
        self.silence(J.GABARIT_FIN + 6)
        self.assertEqual(len(self.essais()), n + 1)

    def test_le_bruit_ne_remplit_pas_l_indicateur(self):
        self.silence(60)
        self.assertEqual(self.essais(), [])

    test_l_appel_rate_puis_repete_est_appris = None
    test_rate_mais_rien_ne_suit_rien_n_est_garde = None


class SesTachesEtTesProjets(unittest.TestCase):
    """« Que Jarvis puisse accomplir des taches (rechercher des choses sur le
    cote ?) et reflechir avec un peu de contexte des projets. »"""

    def test_une_note_se_range_sous_son_projet(self):
        texte = "Irontide :\n  - jeu de robots sous Godot\n\nMachi Tool :\n  - la guirlande\n"
        t = J.ajouter_note_projet(texte, "irontide", "ajouter un mode coop")
        self.assertEqual(t.split("\n")[:3], ["Irontide :", "  - jeu de robots sous Godot", "  - ajouter un mode coop"])
        self.assertIn("Machi Tool :\n  - la guirlande", t)
        t = J.ajouter_note_projet(t, "BrainDebugger", "la carte des fonctionnements")
        self.assertTrue(t.rstrip().endswith("BrainDebugger :\n  - la carte des fonctionnements"))
        self.assertEqual(J.ajouter_note_projet("", "Irontide", "x"), "Irontide :\n  - x\n")
        # « - Irontide (jeu) » ou « ## Irontide » : reconnus aussi ; « Irontides » non
        self.assertIn("## Irontide\n  - y", J.ajouter_note_projet("## Irontide\nautre", "Irontide", "y"))
        self.assertIn("Irontide :\n  - z", J.ajouter_note_projet("Irontides :\n", "Irontide", "z"))
        with self.assertRaises(ValueError):
            J.ajouter_note_projet("x", "", "note")
        with self.assertRaises(ValueError):
            J.ajouter_note_projet("a" * J.PROJETS_MAX, "Irontide", "trop")

    def test_la_liste_et_l_annonce(self):
        t0 = 1_000_000.0
        taches = [{"id": "a", "titre": "Cartes graphiques", "etat": "fini", "debut": t0 - 600,
                   "resume": "La 5070 est le meilleur choix.", "genre": "recherche"},
                  {"id": "b", "titre": "Mode coop", "etat": "en_cours", "debut": t0 - 60, "genre": "reflexion"},
                  {"id": "c", "titre": "Horaires", "etat": "erreur", "debut": t0 - 7200 * 2, "erreur": "credit"}]
        l = J.lister_taches(taches, t0)
        self.assertEqual(l.split("\n")[0], "1. Mode coop (en cours, il y a 1 min)")
        self.assertIn("2. Cartes graphiques (finie, il y a 10 min) : La 5070", l)
        self.assertIn("3. Horaires (echouee, il y a 4 h) : credit", l)
        self.assertIn("Aucune", J.lister_taches([]))
        a = J.annonce_tache(taches[0])
        self.assertIn("La recherche sur « Cartes graphiques » est prete. La 5070", a)
        self.assertIn("Ma reflexion sur", J.annonce_tache(dict(taches[1], etat="fini")))
        self.assertIn("n'ait pas abouti", J.annonce_tache(taches[2]))
        self.assertIn("is ready", J.annonce_tache(taches[0], "en"))
        self.assertTrue(J.nom_fichier_tache("Cartes : 600 € / RTX?", t0).endswith("cartes 600 rtx.md"))


@unittest.skipUnless(NUMPY, "numpy absent")
class LaVoixNeGresillePlus(unittest.TestCase):
    """« Le TTS gresille. » Pas a pleine echelle (le reechantillonnage de
    Windows ecretait), et pas de clic aux bords."""

    def test_crete_et_fondus(self):
        son = np.sin(np.linspace(0, 400, 24000)).astype(np.float32) * 3.0
        out = J.son_propre(son, 24000)
        self.assertEqual(out.dtype, np.int16)
        self.assertLessEqual(int(np.max(np.abs(out))), int(0.81 * 32767))
        self.assertGreater(int(np.max(np.abs(out))), int(0.75 * 32767))
        self.assertLess(abs(int(out[0])), 200)
        self.assertLess(abs(int(out[-1])), 200)
        self.assertEqual(len(J.son_propre(np.zeros(0))), 0)
        self.assertEqual(len(J.son_propre(np.ones(3))), 3, "un son minuscule ne casse rien")


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

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_noyau_d_une_voix(self):
        # ce que la capture montrait : trois « Jarvis » a 0,14 l'un de l'autre,
        # et tout etait jete (la limite etait 0,12)
        rng = np.random.default_rng(8)
        base = rng.normal(size=(9, 96))
        bruit = lambda e: (base + rng.normal(scale=e, size=base.shape)).tolist()
        vrais = [bruit(0.45) for _ in range(5)]
        coh = J.coherence(vrais[:3])
        self.assertGreater(coh, 0.12, "aussi ecartes que sur la capture")
        gardes, c, ecartes = J.choisir_gabarits(vrais, 5)
        self.assertEqual((len(gardes), ecartes), (5, 0))
        self.assertLessEqual(c, J.NOYAU_REJET)
        # un intrus parmi les normaux : ecarte, pas tout jeter
        gardes, _, ecartes = J.choisir_gabarits(vrais[:4] + [rng.normal(size=(9, 96)).tolist()], 5)
        self.assertEqual((len(gardes), ecartes), (4, 1))
        self.assertEqual(J.choisir_gabarits([rng.normal(size=(9, 96)).tolist() for _ in range(5)], 5)[0], None)
        self.assertEqual(J.choisir_gabarits(vrais[:2], 5)[0], None, "moins de trois : rien a comparer")

    def test_seuils(self):
        self.assertAlmostEqual(J.seuil_gabarit(0.5), 0.05)
        self.assertLess(J.seuil_gabarit(0), J.seuil_gabarit(1))
        self.assertEqual((J.seuil_hey(0.5), J.seuil_hey(1.0), J.seuil_hey(0.0), J.seuil_hey(0.5, False)),
                         (0.5, 0.35, 0.65, 9.0), "« Hey Jarvis » suit la meme sensibilite")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_dans_une_phrase(self):
        # « Jarvis baisse le son » d'une traite : les deux dernieres trames du
        # gabarit (le silence d'apres) sont remplacees par la suite de la phrase
        rng = np.random.default_rng(5)
        g = J.normer(rng.normal(size=(12, 96)))
        avant = J.normer(rng.normal(size=(6, 96)))
        q = J.GABARIT_QUEUE
        suite = J.normer(rng.normal(size=(q, 96)))
        fen = np.vstack((avant, g[:-q], suite))
        # au moment ou le mot vient de finir, la suite arrive deja
        entier = J.distance_gabarit(g, fen)
        self.assertGreater(entier, J.seuil_gabarit(1.0), "le gabarit entier ne le reconnait pas")
        d, queue = J.distance_eveil(g, fen[:-q], detail=True)
        self.assertLess(d, 0.01, "sans sa queue, si -- avant que la suite l'efface")
        self.assertEqual(queue, q, "et l'on sait combien de trames du mot restent a venir")


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
#  SES NOUVEAUX POUVOIRS : les decisions (jarvis.py, sans disque ni Windows)
# ======================================================================

class SesNouveauxPouvoirs(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.d, ignore_errors=True))
        d = self.d
        self.home = os.path.join(d, "Users", "moi")
        self.docs = os.path.join(self.home, "Documents")
        self.machi = os.path.join(self.home, "AppData", "Local", "MachiTool")
        self.windows = os.path.join(d, "Windows")
        self.prog = os.path.join(d, "Program Files")
        self.startup = os.path.join(self.home, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu",
                                    "Programs", "Startup")
        for p in (self.docs, self.machi, self.windows, self.prog, self.startup,
                  os.path.join(self.home, "Desktop", "Démarrage"), os.path.join(self.docs, "Rangement")):
            os.makedirs(p, exist_ok=True)
        self.systeme = J.dossiers_systeme({"SystemRoot": self.windows, "ProgramFiles": self.prog,
                                           "APPDATA": os.path.join(self.home, "AppData", "Roaming")})
        self.bases = [self.home, self.docs]
        self.gardes = (self.systeme, self.bases, [self.machi])

    def fichier(self, *chemin, contenu="x"):
        p = os.path.join(*chemin)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(contenu)
        return p

    def test_le_palier_de_chaque_outil(self):
        # « selon la gravite » : le code pour les fichiers et Windows, un oui
        # avant ce qui ne s'annule pas, le reste directement
        sans = {"musique", "lumiere"}
        P = J.palier_outil
        self.assertEqual(P("musique", {}, sans), "direct")
        self.assertEqual(P("lumiere", {}, sans), "direct")
        for nom in J.OUTILS_FICHIERS:
            self.assertEqual(P(nom, {}, sans), "code", nom)
        for a in ("lire", "lister"):
            self.assertEqual(P("reglage_windows", {"action": a}, sans), "direct", a)
        for a in ("activer", "desactiver", "choisir"):
            self.assertEqual(P("reglage_windows", {"action": a}, sans), "code", a)
        self.assertEqual(P("forcer_fermeture", {"cible": "Discord"}, sans), "oui")
        self.assertEqual(P("installer_appli", {"action": "chercher"}, sans), "direct")
        for a in ("installer", "mettre_a_jour"):
            self.assertEqual(P("installer_appli", {"action": a}, sans), "oui", a)
        self.assertEqual(J.groupe_outil("corbeille"), "fichiers")
        self.assertEqual(J.groupe_outil("installer_appli"), "windows")
        self.assertIsNone(J.groupe_outil("ouvrir"))
        self.assertEqual(J.question_oui([("forcer", "Discord")]), "Je ferme de force Discord ?")
        self.assertEqual(J.question_oui([("installer", "VLC")]), "J'installe VLC ?")
        self.assertEqual(J.question_oui([("forcer", "Discord"), ("mettre_a_jour", "VLC")]),
                         "Je ferme de force Discord, puis je mets à jour VLC ?")
        self.assertEqual(J.question_oui([("installer", "VLC")], "en"), "Shall I install VLC?")

    def test_jamais_le_systeme_ni_les_dossiers_de_base(self):
        R = lambda ch, source=True: J.refus_chemin(ch, *self.gardes, source=source)
        self.assertIsNone(R(self.fichier(self.docs, "a.txt")))
        self.assertIn("racine", R(os.path.abspath(os.sep)))
        self.assertIn("systeme", R(self.fichier(self.windows, "win.ini")))
        self.assertIn("systeme", R(os.path.join(self.prog, "Appli")))
        self.assertIn("je n'y touche pas", R(self.fichier(self.startup, "lance.lnk")))
        self.assertIn("Demarrage", R(self.fichier(self.home, "Desktop", "Démarrage", "x.txt")))
        self.assertIn("Machi Tool", R(self.fichier(self.machi, "config.json")))
        for base in (self.home, self.docs):
            self.assertIn("dossier de base", R(base), base)
        self.assertIn("dossier de base", R(os.path.dirname(self.home)), "ce qui contient un dossier de base")
        self.assertIn("dossier de base", R(os.path.join(self.home, "AppData")), "ce qui contient Machi Tool")
        self.assertIsNone(R(self.docs, source=False), "on peut y ranger")
        self.assertIn("systeme", R(self.windows, source=False), "mais jamais vers le systeme")

    def test_deplacer_et_renommer_sans_ecraser_ni_creer_un_programme(self):
        a = self.fichier(self.docs, "notes.txt")
        rang = os.path.join(self.docs, "Rangement")
        self.assertEqual(J.preparer_deplacement(a, rang, *self.gardes), (a, os.path.join(rang, "notes.txt")))
        self.fichier(rang, "notes.txt")
        self.assertEqual(J.preparer_deplacement(a, rang, *self.gardes)[1], os.path.join(rang, "notes (2).txt"),
                         "jamais par-dessus : un nom libre")
        self.assertEqual(J.preparer_deplacement(a, os.path.join(rang, "idees.md"), *self.gardes)[1],
                         os.path.join(rang, "idees.md"), "un chemin complet : le nouveau nom")
        with self.assertRaises(PermissionError):
            J.preparer_deplacement(a, self.windows, *self.gardes)
        with self.assertRaises(PermissionError):
            J.preparer_deplacement(a, self.startup, *self.gardes)
        with self.assertRaises(PermissionError):
            J.preparer_deplacement(a, self.machi, *self.gardes)
        with self.assertRaises(PermissionError):
            J.preparer_deplacement(self.docs, rang, *self.gardes)
        with self.assertRaises(PermissionError):
            J.preparer_deplacement(a, os.path.join(rang, "notes.bat"), *self.gardes)
        with self.assertRaises(ValueError):
            J.preparer_deplacement(rang, os.path.join(rang, "dedans"), *self.gardes)
        with self.assertRaises(FileNotFoundError):
            J.preparer_deplacement(os.path.join(self.docs, "absent.txt"), rang, *self.gardes)
        with self.assertRaises(FileNotFoundError):
            J.preparer_deplacement(a, os.path.join(self.docs, "Nulle part", "x.txt"), *self.gardes)
        script = self.fichier(self.docs, "outil.bat")
        self.assertTrue(J.preparer_deplacement(script, rang, *self.gardes), "un script deja script se range")
        # renommer
        self.assertEqual(J.preparer_renommage(a, "Idees.txt", *self.gardes)[1], os.path.join(self.docs, "Idees.txt"))
        self.fichier(self.docs, "pris.txt")
        self.assertEqual(J.preparer_renommage(a, "pris.txt", *self.gardes)[1], os.path.join(self.docs, "pris (2).txt"))
        for mauvais in ("..\\ailleurs.txt", "a/b.txt", "", "CON.txt", "..", "x?.txt"):
            with self.assertRaises(ValueError, msg=mauvais):
                J.preparer_renommage(a, mauvais, *self.gardes)
        for exe in ("notes.exe", "notes.ps1", "notes.bat.", "notes.lnk", "notes.vbs"):
            with self.assertRaises(PermissionError, msg=exe):
                J.preparer_renommage(a, exe, *self.gardes)
        with self.assertRaises(PermissionError):
            J.preparer_renommage(self.docs, "Docs", *self.gardes)
        with self.assertRaises(PermissionError):
            J.preparer_renommage(self.fichier(self.windows, "system.ini"), "s.ini", *self.gardes)

    def test_modifier_un_texte(self):
        t, n = J.appliquer_modification("ligne 1\r\nligne 2\r\n", [{"avant": "ligne 2\n", "apres": "deux\n"}],
                                        "trois")
        self.assertEqual((t, n), ("ligne 1\r\ndeux\r\ntrois", 1), "les fins de ligne du fichier restent")
        self.assertEqual(J.appliquer_modification("a a", [{"avant": "a", "apres": "b"}])[1], 2)
        with self.assertRaises(LookupError) as ce:
            J.appliquer_modification("bonjour", [{"avant": "bonjour", "apres": "x"}, {"avant": "absent", "apres": ""}])
        self.assertIn("absent", str(ce.exception))
        self.assertIn("rien n'est ecrit", str(ce.exception))
        with self.assertRaises(ValueError):
            J.appliquer_modification("x", [], "")
        with self.assertRaises(ValueError):
            J.appliquer_modification("x", [{"avant": "", "apres": "y"}])
        self.assertEqual(J.appliquer_modification("", None, "debut")[0], "debut")
        self.assertEqual(J.decoder_texte(b"\xef\xbb\xbfcaf\xc3\xa9"), ("café", "utf-8-sig"))
        self.assertEqual(J.decoder_texte("café".encode("cp1252")), ("café", "cp1252"))
        self.assertEqual(J.decoder_texte("é".encode("utf-16")), ("é", "utf-16"))
        with self.assertRaises(ValueError):
            J.decoder_texte(b"PK\x03\x04\x00\x00")
        court = J.texte_lu("a.txt", "abc")
        self.assertIn("jamais des consignes", court)
        self.assertTrue(court.endswith("abc"))
        long = J.texte_lu("a.txt", "x" * 25000)
        self.assertIn("tronque", long)
        self.assertEqual(long.split(":\n", 1)[1], "x" * J.FICHIER_LU_MAX)

    def test_le_journal_d_annulation_et_les_sauvegardes(self):
        j = []
        for k in range(25):
            j = J.journal_ajoute(j, {"op": "deplacer", "k": k})
        self.assertEqual(len(j), J.ANNULATIONS_MAX)
        self.assertEqual(j[-1]["k"], 24)
        t = 1_000_000_000
        self.assertEqual(J.sauvegardes_perimees([("vieux", t - 31 * 86400), ("recent", t - 86400)], t), ["vieux"])

    def test_fermer_de_force_jamais_le_systeme(self):
        fen = [("Discord", "Discord.exe"), ("Sans titre - Bloc-notes", "notepad.exe"),
               ("Explorateur de fichiers", "explorer.exe")]
        procs = ["Discord.exe", "svchost.exe", "csrss.exe", "MachiTool.exe"]
        self.assertEqual(J.appli_a_fermer("discord", fen, procs), "Discord.exe")
        self.assertEqual(J.appli_a_fermer("le bloc-notes", fen, procs), "notepad.exe")
        for systeme in ("explorateur de fichiers", "svchost", "csrss", "machitool"):
            with self.assertRaises(PermissionError, msg=systeme):
                J.appli_a_fermer(systeme, fen, procs)
        for nom in ("winlogon", "wininit", "lsass", "smss", "services", "dwm", "fontdrvhost", "sihost",
                    "ctfmon", "conhost", "MachiTool.exe", "C:\\Windows\\explorer.exe"):
            self.assertTrue(J.processus_intouchable(nom), nom)
        self.assertFalse(J.processus_intouchable("Discord.exe"))
        with self.assertRaises(ValueError):
            J.appli_a_fermer("4242", fen, procs)
        with self.assertRaises(LookupError):
            J.appli_a_fermer("photoshop", fen, procs)

    def test_winget_un_paquet_et_jamais_l_alimentation(self):
        sortie = ("\r-\r\\\r   \r"
                  "Name                  Id                  Version  Match      Source\n"
                  "---------------------------------------------------------------------\n"
                  "VLC media player      VideoLAN.VLC        3.0.21   Moniker: vlc winget\n"
                  "VLC UWP               9NBLGGH4VVNH        Unknown             msstore\n"
                  "\n2 packages\n")
        res = J.lire_winget(sortie)
        self.assertEqual([(r["nom"], r["id"], r["version"]) for r in res],
                         [("VLC media player", "VideoLAN.VLC", "3.0.21"), ("VLC UWP", "9NBLGGH4VVNH", "Unknown")])
        fr = ("Nom       ID               Version Source\n---------------------------------------\n"
              "Discord   Discord.Discord  1.0.9   winget\n")
        self.assertEqual(J.lire_winget(fr)[0]["id"], "Discord.Discord")
        self.assertEqual(J.lire_winget("Aucun package ne correspond"), [])
        self.assertEqual(J.choisir_paquet("VideoLAN.VLC", res)["id"], "VideoLAN.VLC")
        self.assertEqual(J.choisir_paquet("vlc media player", res)["id"], "VideoLAN.VLC")
        with self.assertRaises(LookupError):
            J.choisir_paquet("vlc", res)                       # deux candidats : lequel ?
        with self.assertRaises(LookupError):
            J.choisir_paquet("rien", [])
        for p in ("Shutdown Timer Classic", "Wise Auto Shutdown", "Microsoft.PowerToys", "Sleep Timer",
                  "Minuteur d'arrêt", "Hibernate Trigger"):
            self.assertTrue(J.paquet_touche_a_l_alimentation(p), p)
        for p in ("VideoLAN.VLC", "Discord", "7zip.7zip"):
            self.assertFalse(J.paquet_touche_a_l_alimentation(p), p)
        for plusieurs in ("vlc, discord", "vlc et discord", "--all", "all", "tout"):
            with self.assertRaises(ValueError, msg=plusieurs):
                J.nom_de_paquet(plusieurs)
        self.assertEqual(J.nom_de_paquet("--id VideoLAN.VLC"), "id VideoLAN.VLC", "pas d'option cachee")

    def test_les_reglages_de_windows_une_liste_fermee(self):
        self.assertEqual(J.reglage_windows_valide("Wi-Fi", "activer"), ("wifi", "activer"))
        self.assertEqual(J.reglage_windows_valide("sortie audio", "lister"), ("sortie_audio", "lister"))
        with self.assertRaises(ValueError):
            J.reglage_windows_valide("pare-feu", "desactiver")
        with self.assertRaises(ValueError):
            J.reglage_windows_valide("wifi", "lister")
        s = J.script_radio("bluetooth", True)
        self.assertIn("'Bluetooth'", s)
        self.assertIn("SetStateAsync('On')", s)
        self.assertNotIn("SetStateAsync", J.script_radio("wifi"))
        self.assertFalse(J._ALIMENTATION_TEXTE.search(s))
        for r in J.REGLAGES_WINDOWS:
            self.assertTrue(J.PAGES_PARAMETRES[r].startswith("ms-settings:"))
            self.assertFalse(J.touche_a_l_alimentation(J.PAGES_PARAMETRES[r]))

    def test_la_porte_de_la_parole_spontanee(self):
        t = 1_000_000.0
        s = {"maintenant": t, "actif": True, "etat": "attente", "mode": "jarvis", "heure": 15, "inactivite_s": 5}
        R = J.parole_spontanee_refusee
        self.assertIsNone(R(s))
        for cle, val, raison in (("actif", False, "eteint"), ("etat", "ecoute", "occupe"), ("mode", "psy", "psy"),
                                 ("en_attente", True, "attend une reponse"), ("voix_occupee", True, "parle deja"),
                                 ("plein_ecran", True, "plein ecran"), ("calme_jusqua", t + 60, "calme"),
                                 ("grave_jusqua", t + 60, "apres une seance grave"), ("heure", 23, "nuit"),
                                 ("heure", 7, "nuit"), ("inactivite_s", 301, "absent"),
                                 ("recentes", [t - 100, t - 200, t - 300], "plafond")):
            self.assertEqual(R(dict(s, **{cle: val})), raison, cle)
        self.assertIsNone(R(dict(s, heure=2), nuit_permise=True))
        self.assertIsNone(R(dict(s, recentes=[t - 4000] * 5)), "le plafond est par heure")

    def test_chaque_initiative(self):
        t = 1_000_000.0
        s = {"maintenant": t, "heure": 15}
        C = J.choisir_initiative
        self.assertIsNone(C(s, {}))
        c = C(dict(s, temp_cpu=96, tjmax=100), {})
        self.assertEqual((c["cle"], c["nuit_permise"]), ("surchauffe", True))
        self.assertIn("processeur est à 96 °C", c["texte"])
        self.assertIsNone(C(dict(s, temp_cpu=85, tjmax=100), {}))
        self.assertEqual(C(dict(s, temp_cpu=82, tjmax=85), {})["cle"], "surchauffe", "pres de sa limite")
        self.assertIn("carte graphique", C(dict(s, temp_gpu=90), {})["texte"])
        self.assertIsNone(C(dict(s, temp_gpu=90), {"surchauffe": t - 60}), "pas deux fois en une demi-heure")
        self.assertIsNone(C(dict(s, volume=80), {}), "l'apres-midi, le volume est a toi")
        c = C(dict(s, heure=23, volume=80), {})
        self.assertEqual((c["cle"], c["volume"]), ("volume_soir", 40))
        self.assertEqual(c["texte"], "Il est tard : j'ai baissé le volume à 40 %.")
        self.assertIsNone(C(dict(s, heure=23, volume=55), {}))
        self.assertIsNone(C(dict(s, heure=0, volume=80), {"volume_soir": t - 3600}))
        c = C(dict(s, activite_continue_s=2 * 3600 + 1), {})
        self.assertEqual(c["cle"], "pause")
        self.assertIsNone(C(dict(s, activite_continue_s=3 * 3600), {"pause": t - 3600}), "une fois")
        self.assertIn("break", C(dict(s, activite_continue_s=3 * 3600, langue="en"), {})["texte"])

    def test_tous_les_reglages_mais_ses_droits_se_confirment(self):
        # « Fait en sorte que Jarvis puisse changer n'importe quel setting de l'application »
        D = {"jarvis_fichiers": False, "jarvis_windows": False, "jarvis_initiatives": False, "veille_minutes": 5,
             "jarvis_repliques_spontanees": False, "jarvis_code_actif": False, "maj_installation_auto": True,
             "pont_cle": "", "pont_site": "", "jarvis_code_empreinte": "", "regles": []}
        for cle in ("jarvis_fichiers", "jarvis_windows", "jarvis_initiatives", "jarvis_code_actif",
                    "maj_installation_auto", "veille_minutes", "jarvis_repliques_spontanees"):
            self.assertTrue(J.reglage_modifiable(cle, D), cle)
        # jamais : les cles, les codes, l'adresse ou part le journal, les listes
        for cle in ("pont_cle", "pont_site", "jarvis_code_empreinte", "regles"):
            self.assertFalse(J.reglage_modifiable(cle, D), cle)
        # ses droits : la personne confirme a chaque fois ; le reste, directement
        P = lambda cle: J.palier_application("reglages_machi", {"action": "changer", "cle": cle, "valeur": "oui"})
        for cle in ("jarvis_pc", "jarvis_fichiers", "jarvis_windows", "jarvis_ecran", "jarvis_code_actif",
                    "jarvis_initiatives", "jarvis_journal", "collecte_envoi"):
            self.assertEqual(P(cle), J.PALIER_POUVOIR, cle)
        self.assertIsNone(P("veille_minutes"))
        self.assertIsNone(J.palier_application("reglages_machi", {"action": "lire", "cle": "jarvis_pc"}))
        # une mise a jour : l'application redemarre, « oui ? » avant
        self.assertEqual(J.palier_application("mise_a_jour", {"action": "installer"}), J.PALIER_OUI)
        self.assertIsNone(J.palier_application("mise_a_jour", {"action": "verifier"}))
        self.assertEqual(J.question_oui([("reglage", J.libelle_reglage("jarvis_fichiers", True))]),
                         "J'active l'accès aux fichiers ?")
        self.assertEqual(J.question_oui([("reglage", J.libelle_reglage("jarvis_code_actif", False, "en"))], "en"),
                         "Shall I turn off the access code?")
        self.assertEqual(J.question_oui([("maj_machi", "1.68.0")]),
                         "J'installe Machi Tool 1.68.0 (il redémarre un instant) ?")
        self.assertIn("1.68.0", J.annonce_maj("disponible", "1.68.0"))
        self.assertIn("installer", J.annonce_maj("disponible", "1.68.0"))
        self.assertIn("reviens", J.annonce_maj("pose", "1.68.0"))
        self.assertIn("version 1.68.0", J.annonce_maj("posee", "1.68.0", "en"))


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
            # « il y a un Ctrl+J maintenant » : un raccourci global (RegisterHotKey)
            # est permis -- il ne voit que sa combinaison. Lire le clavier, non :
            # rien de tout ca n'en a besoin.
            for interdit in ("setwindowshookex", "pynput", "import keyboard", "wh_keyboard",
                             "getasynckeystate"):
                self.assertNotIn(interdit, src, "%s : %s" % (nom, interdit))
        self.assertNotIn("registerhotkey", self.lire("jarvis.py").lower())

    def test_l_oreille_n_ecrit_rien_sur_le_disque(self):
        src = self.lire("jarvis.py")
        # `wave.open(tampon, "wb")` ecrit dans la memoire ; `open(...)` tout court
        # ecrirait un fichier.
        self.assertNotRegex(src, r"(?<![\w.])open\([^)]*['\"][wax]b?['\"]")
        self.assertNotIn("tofile(", src)
        for ecrit in ("shutil.copy", ".write_text(", ".write_bytes("):
            self.assertNotIn(ecrit, src, ecrit)


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
        # rien ne part au journal de BrainDebugger d'un test a l'autre (voir
        # test_les_discussions_vont_au_journal)
        m.CFG.update(pont_site="https://bd.exemple", pont_cle="CLE", jarvis_voix=False, jarvis_journal=False)
        m.ETAT["forcage"] = None
        m.JARVIS.update(led=None, led_fin=0.0, minuteurs=[], etat="attente", mode="jarvis",
                        mode_vu=0.0, historique=[], vu=0.0, propose_psy=False,
                        psy_echange=[], psy_grave=False, reveil_par=None,
                        attente_code=None, acces_jusqua=0.0, verrou_jusqua=0.0, suite_active=False,
                        entendu="", calme_jusqua=0.0, reveil_verifie=False, souci=None, fait_jusqua=0.0,
                        erreur_jusqua=0.0, propose_psy_phrase="", psy_raison=None,
                        transcription_absente_dite=False, suspens=None, agenda_change=0.0,
                        voix_lisse_boule=0.0, derniere_erreur=None, coupe_contexte="", ecoute_avant=0.0,
                        muet_depuis=None, avance=None, dictee_dite=0.0,
                        attente_oui=None)
        del m.ANNONCES[:]
        # ses nouveaux pouvoirs : ni journal d'annulation ni initiatives d'un test a l'autre
        m.ANNULATIONS["liste"] = None
        m.INITIATIVES.update(recentes=[], deja={}, actif_depuis=None, grave_jusqua=0.0, mesures={},
                             mesure_t=0.0, mesure_en_cours=False)
        m._WINGET["recherches"].clear()
        m.ONGLETS.update(file=[], resultats={}, vu=0.0)      # pas d'extension d'un test a l'autre
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
                v = file_.pop(0)
                m._GABARIT_RECU["evt"] = v if isinstance(v, dict) else {"evt": "gabarit", "vecteurs": v}
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

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_diagnostic_spotify_de_machi_tool(self):
        m = self.m
        self.assertIn("Pas de Client ID", m.diagnostic_spotify(m.CFG))
        m.CFG.update(spotify_client_id="CID")
        self.assertIn("Pas encore connecte", m.diagnostic_spotify(m.CFG))
        m.CFG.update(spotify_refresh="R", jarvis_pc=False)
        vrai = m._SPOTIFY["client"]
        self.addCleanup(lambda: m._SPOTIFY.update(client=None, cle=None))

        class Faux:
            def diagnostic(self):
                return True, ["Jeton : OK."]
        m._SPOTIFY.update(client=Faux(), cle=("CID", "R"))
        r = m.diagnostic_spotify(m.CFG)
        self.assertIn("Il peut agir sur le PC", r, "sans ses mains, Jarvis ne s'en sert pas : on le dit")
        self.assertFalse(r.startswith("OK."))
        m.CFG["jarvis_pc"] = True
        self.assertEqual(m.diagnostic_spotify(m.CFG), "OK. Jeton : OK.")
        self.assertIs(m._jv.CONTEXTE_SSL, m._contexte_ssl, "Spotify passe par le magasin de Machi Tool")

    def test_un_raccourci_pris_par_une_autre_appli_est_retente(self):
        # « Handy avait pris control shift espace, je l'ai eteint, retente »
        m = self.m
        tenu = {m.CTRL_MAJ_ESPACE_ID}
        combos = [(m.CTRL_J_ID, 2, 0x4A, "Ctrl+J"), (m.CTRL_MAJ_ESPACE_ID, 6, 0x20, "Ctrl+Maj+Espace")]
        enregistrer = lambda i, mods, vk: i not in tenu
        restent = m.prendre_raccourcis(combos, enregistrer)
        self.assertEqual([c[3] for c in restent], ["Ctrl+Maj+Espace"])
        self.assertEqual(m.prendre_raccourcis(restent, enregistrer, bavard=False), restent, "Handy le tient encore")
        tenu.clear()
        self.assertEqual(m.prendre_raccourcis(restent, enregistrer, bavard=False), [], "libere : Jarvis le prend")

    def test_ctrl_maj_espace_note_au_carnet_et_jarvis_repond(self):
        # « il faut que control shift espace remplisse un systeme de notes » puis
        # « je veux que jarvis puisse repondre au lieu de dire note, aussi que
        # ca note dans brain debugger » -- et « bon, j'y vais » ne le congedie pas
        m = self.m
        noms = ("oreille_vivante", "poser_led", "declencher_routines", "_requete_bd", "_cle_presente",
                "_en_fond", "parler_a_jarvis", "souci")
        vrais = {k: getattr(m, k) for k in noms}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        self.addCleanup(lambda: m.NOTES_EN_ATTENTE.clear())
        poses, questions, soucis, panne = [], [], [], []

        def bd(chemin, corps, cfg, delai, **k):
            if panne:
                raise OSError("hors ligne")
            poses.append((chemin, corps["texte"]))
            return {"ok": True}
        m.oreille_vivante, m.poser_led = (lambda: True), (lambda *a, **k: None)
        m.declencher_routines = lambda *a, **k: None
        m.prechauffer_dictee = lambda: None
        m.envoyer_oreille = lambda o: self.envoye.append(o) or True
        m._requete_bd, m._cle_presente, m._en_fond = bd, (lambda cfg: True), (lambda f: f())
        m.parler_a_jarvis = lambda texte, cfg, conv=None, notee=False: questions.append((texte, notee))
        m.souci = soucis.append
        m.CFG["jarvis_actif"] = True
        m.JARVIS.update(etat="attente", mode="jarvis")
        self.assertEqual(m.reveil_au_clavier(m.CFG, attendre_oreille_s=0, note=True), "reveille")
        self.assertIn("pause", self.envoye[-1], "il laisse le temps de dicter")
        dit = "Le garage-témoin rappelle demain, bon j'y vais, au revoir."
        m._traiter_texte(dit, m.CFG, m.JARVIS["tour"], None, False, False, False, "fr")
        self.assertEqual(poses, [("/api/machitool/note", dit)], "au carnet, telle quelle")
        self.assertEqual(questions, [(dit, True)], "et Jarvis y repond, en sachant qu'elle y est")
        self.assertIsNone(m.JARVIS.get("note_tour"), "une seule phrase est une note")
        # la suite de la conversation n'est plus une note
        m._traiter_texte("Et quelle heure est-il ?", m.CFG, m.JARVIS["tour"], None, False, False, False, "fr")
        self.assertEqual(len(poses), 1)
        # BrainDebugger injoignable : la note est gardee (dit sur sa page), et part avec la suivante
        panne.append(1)
        self.assertEqual(m.poser_notes("note-témoin une", m.CFG), 0)
        self.assertTrue(soucis and "1 gardee" in soucis[-1])
        panne.clear()
        self.assertEqual(m.poser_notes("note-témoin deux", m.CFG), 2)
        self.assertEqual([t for _, t in poses[1:]], ["note-témoin une", "note-témoin deux"])
        self.assertEqual(m.NOTES_EN_ATTENTE, [])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_panneau_led_dessine_l_heure_et_rien_de_personnel(self):
        # « tu peux faire passer ca dans machitool automatiquement ? »
        m = self.m
        t = time.mktime((2026, 10, 21, 21, 47, 30, 0, 0, -1))
        bleu = (40, 120, 255)
        img = m.image_panneau("horloge", t, accent=bleu)
        self.assertEqual(img.shape, (64, 64, 3))
        heure = img[10:24]
        self.assertGreater(int((heure == bleu).all(axis=2).sum()), 150, "l'heure, aux couleurs de la guirlande")
        self.assertTrue((img[0:9] == 0).all() and (img[61:] == 0).all(), "les bords restent noirs")
        self.assertGreater(int((img[32:37] == (150, 150, 165)).all(axis=2).sum()), 20, "la date")
        self.assertFalse((img[44:49] != 0).any(), "pas de minuteur : rien a cette ligne")
        # « possible que machitool envoie du 30 fps ? » : la barre des secondes
        # glisse -- a 30 s et demie, le 31e pixel est a moitie allume
        demi = m.image_panneau("horloge", t + 0.5, accent=bleu)
        self.assertEqual(tuple(img[60, 31]), tuple(int(c * 0.6) for c in bleu), "30 secondes pleines")
        self.assertEqual(tuple(img[60, 32]), tuple(int(c * 0.15) for c in bleu))
        self.assertTrue(img[60, 32, 2] < demi[60, 32, 2] < int(bleu[2] * 0.6), "le bout s'allume en cours de seconde")
        self.assertEqual(m.PANNEAU_IPS, 30)
        minuteur = [{"genre": "minuteur", "fin": t + 523, "quoi": "nom-temoin", "duree": 600}]
        avec = m.image_panneau("horloge", t, accent=bleu, minuteurs=minuteur)
        self.assertGreater(int((avec[44:49] == (255, 150, 40)).all(axis=2).sum()), 15, "le minuteur, sans son nom")
        self.assertEqual(m._prochain_chrono(minuteur, t), ("minuteur", "08:43"))
        self.assertTrue((m.image_panneau("eteint", t) == 0).all())
        ambiance = m.image_panneau("ambiance", t, accent=(255, 0, 0))
        self.assertEqual(tuple(ambiance[0, 0]), (255, 0, 0))
        self.assertLess(int(ambiance[63, 0, 0]), 120, "elle s'assombrit vers le bas")
        # RGB565, poids fort d'abord : ce que lit le croquis
        donnees = m.rgb565(ambiance)
        self.assertEqual(len(donnees), 8192)
        self.assertEqual(donnees[:2], b"\xf8\x00")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_machi_tool_qui_s_eteint_eteint_le_panneau(self):
        # « quand Machi Tool s'eteint, eteins automatiquement le panneau (comme la guirlande) »
        m = self.m
        vrais = (m.trouver_panneau, m.ouvrir_panneau)
        self.addCleanup(lambda: (setattr(m, "trouver_panneau", vrais[0]), setattr(m, "ouvrir_panneau", vrais[1]),
                                 m.PANNEAU.update(fini=False, lien=None)))
        m.PANNEAU.update(fini=False, lien=None)
        self.assertFalse(m.eteindre_panneau(), "rien de branche : rien a eteindre")
        m.PANNEAU["fini"] = False

        class Carte:
            def __init__(self):
                self.ecrit = []

            def write(self, octets):
                self.ecrit.append(bytes(octets))
                self.vu_lien = m.PANNEAU.get("lien")

            def flush(self):
                pass

            def close(self):
                pass
        carte = Carte()
        m.trouver_panneau = lambda: "COM7"
        m.ouvrir_panneau = lambda p: carte
        cfg = {"panneau_actif": True, "panneau_contenu": "horloge", "panneau_luminosite": 64}
        m.piloter_panneau(cfg, tours=1)
        self.assertIs(carte.vu_lien, carte, "le fil laisse sa liaison a l'extinction")
        self.assertIsNone(m.PANNEAU["lien"], "fil arrete : plus de liaison")
        m.PANNEAU["lien"] = carte                 # le fil tourne encore
        del carte.ecrit[:]
        self.assertTrue(m.eteindre_panneau())
        self.assertEqual(carte.ecrit, [b"MB\x00", b"MF" + bytes(8192)], "luminosite 0, image noire")
        # et le fil n'ecrit plus rien par-dessus
        m.PANNEAU["lien"] = carte
        del carte.ecrit[:]
        m.piloter_panneau(cfg, tours=2)
        self.assertEqual(carte.ecrit, [])
        # les deux sorties : quitter Machi Tool et l'arret de Windows
        src = open(m.__file__, encoding="utf-8").read()
        self.assertEqual(src.count("eteindre_panneau()\n                eteindre_guirlande()"), 1, "l'arret de Windows")
        self.assertEqual(src.count("eteindre_en_partant()\n                eteindre_guirlande()"), 1,
                         "quitter : noir, sauf pour une mise a jour (voir test_les_mises_a_jour_sur_le_panneau)")

    def test_le_panneau_dit_qui_ralentit_et_reconnait_son_croquis(self):
        # « ca tombe a 5 fps parfois, tu pourrais fixer ca ? »
        m = self.m
        avant = dict(m.PANNEAU)
        self.addCleanup(lambda: (m.PANNEAU.clear(), m.PANNEAU.update(avant)))

        class Carte:
            def __init__(self, reponse):
                self.reponse, self.attente = reponse, b""

            def reset_input_buffer(self):
                self.attente = b""

            def write(self, octets):
                if octets == b"MV":
                    self.attente += self.reponse

            @property
            def in_waiting(self):
                return len(self.attente)

            def read(self, n):
                lu, self.attente = self.attente[:n], self.attente[n:]
                return lu
        self.assertEqual(m.version_croquis(Carte(b"MACHI 3\r\n"), calme=0), 3)
        self.assertEqual(m.version_croquis(Carte(b"MACHI 2\r\n"), calme=0), 2)
        self.assertEqual(m.version_croquis(Carte(b""), attente=0.05, calme=0), 1, "la v1 ne repond rien")
        self.assertEqual(m.version_croquis(object()), 1)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(m.__file__), "carte", "machi_panneau",
                                                    "machi_panneau.ino")), "le croquis v2 est dans le depot")
        m.PANNEAU.update(etat="connecte", port="COM4", ips=29.0, croquis=1)
        self.assertIn("ancien croquis", m.etat_panneau_lisible()[0])
        self.assertIn("version 1", m.etat_panneau_lisible()[0])
        m.PANNEAU.update(croquis=2)
        self.assertIn("ancien croquis (version 2)", m.etat_panneau_lisible()[0], "la v2 : passer a la v3")
        m.PANNEAU.update(croquis=m.PANNEAU_CROQUIS, ips=5.0, calcul_ms=3.0, envoi_ms=180.0, carte_jetees=None)
        self.assertIn("la carte qui suit mal", m.etat_panneau_lisible()[0])
        m.PANNEAU.update(calcul_ms=190.0, envoi_ms=4.0)
        self.assertIn("le PC qui ralentit", m.etat_panneau_lisible()[0])
        m.PANNEAU.update(ips=30.0)
        self.assertEqual(m.etat_panneau_lisible()[0], "Branche sur COM4  ·  30 im/s (reglee 30)")
        # « j'ai des artefacts depuis le dernier flash » : la carte dit combien d'images elle a jetees
        m.PANNEAU["_recu"] = b""

        class Bilan:
            in_waiting = 30

            def read(self, n):
                return b"STATS 812 3\nSTATS 9"
        m.lire_bilan_carte(Bilan())
        self.assertEqual((m.PANNEAU["carte_recues"], m.PANNEAU["carte_jetees"]), (812, 3))
        self.assertEqual(m.PANNEAU["_recu"], b"STATS 9", "la ligne pas finie attend la suite")
        self.assertIn("3 images abimees jetees par la carte", m.etat_panneau_lisible()[0])
        m.lire_bilan_carte(object())                  # une carte sans tampon (les faux des tests)

    def test_le_resume_du_jour_attend_le_demarrage_et_une_minute_d_activite(self):
        # « lorsque l'ordinateur est demarre et que Machi Tool s'ouvre, Jarvis resume la
        # journee si des choses sont prevues » -- « il doit detecter un debut d'activite
        # sur le PC (au moins 1 minute d'activite) »
        m, J = self.m, self.m._jv
        vrais = {k: getattr(m, k) for k in ("sauver_config", "lire_agenda_synchro")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        m.sauver_config = lambda cfg: True
        self.addCleanup(lambda: (m.RESUME.update(attendu=False, lance=False, actif_depuis=None),
                                 m.PANNEAU.update(programme=None, agenda=None, jarvis=None), m.ANNONCES.clear()))
        t = time.mktime((2026, 10, 22, 9, 52, 0, 0, 0, -1))
        cfg = dict(m.CONFIG_DEFAUT, jarvis_actif=True, jarvis_appellation="Monsieur", jarvis_langue="fr")
        # Machi Tool relance 2 h apres le PC (une mise a jour) : pas de resume
        self.assertFalse(m.preparer_resume_du_jour(cfg, t, demarrage_pc=t - 7200))
        # deja fait il y a une heure (deux demarrages rapproches) : non plus
        self.assertFalse(m.preparer_resume_du_jour(dict(cfg, jarvis_resume_dernier=t - 3600), t, demarrage_pc=t - 60))
        self.assertFalse(m.preparer_resume_du_jour(dict(cfg, jarvis_resume_du_jour=False), t, demarrage_pc=t - 60))
        # le PC vient de demarrer : le resume attend
        self.assertTrue(m.preparer_resume_du_jour(cfg, t, demarrage_pc=t - 90))
        lances = []
        # personne au clavier : rien ; 59 s d'activite : rien ; une pause de 40 s : on repart de zero
        self.assertFalse(m.veiller_resume_du_jour(cfg, t, inactivite=600, lancer=lances.append))
        self.assertFalse(m.veiller_resume_du_jour(cfg, t + 1, inactivite=0, lancer=lances.append))
        self.assertFalse(m.veiller_resume_du_jour(cfg, t + 60, inactivite=3, lancer=lances.append))
        self.assertFalse(m.veiller_resume_du_jour(cfg, t + 61, inactivite=40, lancer=lances.append))
        self.assertFalse(m.veiller_resume_du_jour(cfg, t + 70, inactivite=0, lancer=lances.append))
        self.assertFalse(m.veiller_resume_du_jour(dict(cfg, jarvis_actif=False), t + 200, inactivite=0,
                                                  lancer=lances.append), "Jarvis coupe : rien")
        self.assertEqual(lances, [])
        # une minute pleine : il part, une seule fois, et c'est note
        self.assertTrue(m.veiller_resume_du_jour(cfg, t + 130, inactivite=2, lancer=lances.append))
        self.assertFalse(m.veiller_resume_du_jour(cfg, t + 500, inactivite=0, lancer=lances.append))
        self.assertEqual(len(lances), 1)
        self.assertEqual(cfg["jarvis_resume_dernier"], t + 130)
        # ce qu'il dit : ce qui reste aujourd'hui (le footing de 8 h 30 est passe)
        journee = [{"id": 1, "date": "2026-10-22", "label": "Anniversaire-témoin"},
                   {"id": 2, "date": "2026-10-22", "heure": "08:30", "label": "Footing-témoin"},
                   {"id": 3, "date": "2026-10-22", "heure": "14:30", "label": "Réunion-témoin"},
                   {"id": 4, "date": "2026-10-22", "heure": "10:15", "label": "Dentiste-témoin"},
                   {"id": 5, "date": "2026-10-23", "heure": "09:00", "label": "Demain-témoin"}]
        m.lire_agenda_synchro = lambda cfg, depuis, jours, bilan=False: ({"rendezVous": journee}, None)
        m.ANNONCES.clear()
        texte = m.faire_resume_du_jour(cfg, t)
        self.assertEqual(texte, "Bonjour, Monsieur. Au programme aujourd'hui : Dentiste-témoin à 10 h 15, "
                                "Réunion-témoin à 14 h 30 ; et toute la journée : Anniversaire-témoin.")
        self.assertEqual(len(m.ANNONCES), 1, "il le dira des qu'il est libre, de sa vraie voix")
        avec = m.ANNONCES[0][3]
        self.assertEqual([r["id"] for r in avec["programme"]], [4, 3, 1], "a heure, puis toute la journee")
        self.assertEqual(len(avec["journee"]), 4, "toute la journee, pour les couleurs")
        # dit : le panneau montre le programme, pas le visage de Jarvis
        vraie = (m.VOIX.dire, m.VOIX.peut_parler, m.charges_voix, m.voix_prete)
        self.addCleanup(lambda: (setattr(m.VOIX, "dire", vraie[0]), setattr(m.VOIX, "peut_parler", vraie[1]),
                                 setattr(m, "charges_voix", vraie[2]), setattr(m, "voix_prete", vraie[3])))
        dits = []
        m.VOIX.dire = lambda texte, fin=None, langue="fr", **k: dits.append(texte)
        m.VOIX.peut_parler = lambda: True
        m.charges_voix = lambda cfg: [{"cle": "fr"}]
        m.voix_prete = lambda cle=None: True
        m.CFG["jarvis_voix"] = True
        m.JARVIS["etat"] = "attente"
        m.PANNEAU.update(programme=None, jarvis=None)
        m.dire_les_annonces()
        self.assertEqual(dits, [texte])
        self.assertIsNone(m.PANNEAU["jarvis"])
        self.assertEqual([r["id"] for r in m.PANNEAU["programme"]["rdv"]], [4, 3, 1])
        img = m.image_du_panneau({"panneau_contenu": "horloge", "panneau_suit_eclat": False}, "horloge",
                                 m.PANNEAU["programme"]["debut"] + 1)
        self.assertTrue((img == m.image_programme(avec["programme"], m.PANNEAU["programme"]["debut"] + 1,
                                                  avec["journee"], 1)).all(), "le programme a l'ecran")
        # il reste 20 s au moins, puis l'horloge revient
        self.assertIsNone(m.programme_au_panneau(m.PANNEAU["programme"]["debut"] + 60))
        # rien de prevu : il se tait
        m.ANNONCES.clear()
        m.lire_agenda_synchro = lambda cfg, depuis, jours, bilan=False: ({"rendezVous": [journee[1]]}, None)
        self.assertIsNone(m.faire_resume_du_jour(cfg, t))
        self.assertEqual(m.ANNONCES, [])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_resume_se_rejoue_sur_demande(self):
        # « fais en sorte de pouvoir rejouer le resume sur demande (lorsqu'on demande a Jarvis) »
        m = self.m
        vrais = {k: getattr(m, k) for k in ("lire_agenda_synchro",)}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        self.addCleanup(lambda: m.PANNEAU.update(programme=None, agenda=None, jarvis=None, agenda_synchro=False))
        etat = m.JARVIS.get("etat")
        self.addCleanup(lambda: m.JARVIS.update(etat=etat))
        if time.localtime().tm_hour * 60 + time.localtime().tm_min >= 23 * 60 + 50:
            self.skipTest("trop tard : le rendez-vous de 23 h 58 serait passe")
        jour = time.strftime("%Y-%m-%d")
        journee = [{"id": 1, "date": jour, "heure": "23:58", "label": "Tard-témoin"},
                   {"id": 2, "date": jour, "label": "Journée-témoin"}]
        m.lire_agenda_synchro = lambda cfg, depuis, jours, bilan=False: ({"rendezVous": journee}, None)
        cfg = dict(m.CONFIG_DEFAUT, jarvis_pc=False, jarvis_code_actif=True, jarvis_langue="fr")
        o = {"id": 7, "nom": "resume_du_jour", "entree": {}}
        self.assertEqual(m._palier(o, cfg), m._jv.PALIER_DIRECT, "sans mains, code ferme : direct")
        m.PANNEAU["programme"] = None
        r = m.executer_outil(o, cfg)
        self.assertIn("Tard-témoin à 23 h 58", r["texte"])
        self.assertIn("Journée-témoin", r["texte"])
        p = m.PANNEAU["programme"]
        self.assertEqual([x["id"] for x in p["rdv"]], [1, 2], "le programme sur le panneau")
        # il est actif (il parle) : le programme passe devant son visage, une minute au plus
        m.JARVIS["etat"] = "parle"
        cfg_p = {"panneau_contenu": "horloge", "panneau_suit_eclat": False}
        img = m.image_du_panneau(cfg_p, "horloge", p["debut"] + 2)
        self.assertTrue((img == m.image_programme(p["rdv"], p["debut"] + 2, p["journee"], 2)).all())
        vrai_parle = m.VOIX.parle
        self.addCleanup(lambda: setattr(m.VOIX, "parle", vrai_parle))
        m.VOIX.parle = True
        self.assertIsNotNone(m.programme_au_panneau(p["debut"] + 50))
        self.assertIsNone(m.programme_au_panneau(p["debut"] + 61), "une conversation qui dure : son visage revient")
        # rien de prevu : il le dit, et le panneau ne change pas
        m.PANNEAU["programme"] = None
        m.lire_agenda_synchro = lambda cfg, depuis, jours, bilan=False: ({"rendezVous": []}, None)
        self.assertEqual(m.executer_outil(o, cfg)["texte"], "Rien d'autre de prévu aujourd'hui.")
        self.assertIsNone(m.PANNEAU["programme"])

    def test_un_rendez_vous_change_par_jarvis_se_relit_au_panneau(self):
        # « Jarvis doit pouvoir modifier ou supprimer des rendez-vous » : BrainDebugger le fait,
        # et previent (agenda_modifie) -- le panneau relit son agenda tout de suite
        m = self.m
        vrai = m.lire_agenda_synchro
        self.addCleanup(lambda: setattr(m, "lire_agenda_synchro", vrai))
        self.addCleanup(lambda: m.PANNEAU.update(agenda=None, agenda_synchro=False))
        fait = threading.Event()
        m.lire_agenda_synchro = lambda cfg, depuis, jours, bilan=False: (fait.set(), ({"rendezVous": []}, None))[1]
        m.PANNEAU.update(agenda={"jour": "x", "lu": time.time(), "rdv": [{"label": "vieux"}]}, agenda_synchro=False)
        m.relire_agenda_au_fond(dict(m.CONFIG_DEFAUT))
        self.assertTrue(fait.wait(5))
        for _ in range(50):
            if not m.PANNEAU.get("agenda_synchro"):
                break
            time.sleep(0.02)
        self.assertIsNone(m.PANNEAU["agenda"], "la copie gardee par le panneau est jetee")
        src = open(m.__file__, encoding="utf-8").read()
        i = src.index('if donnees.get("agenda_modifie"):')
        self.assertIn("relire_agenda_au_fond(cfg)", src[i:i + 300])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_cycle_sous_la_date(self):
        # « rajoute des cycles en dessous de la date : un cycle qui fade sur la meteo, puis un
        # fade sur un petit egaliseur avec le nom de la musique (quand Spotify change de
        # musique), puis un petit bonhomme qui marche (selon l'heure de la journee), puis
        # l'heure a nouveau »
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("cycle", "meteo", "musique_vue", "morceau", "musique_saut", "cretes")}
        sauve_audio = {k: m.AUDIO.get(k) for k in ("actif", "spectre")}
        self.addCleanup(lambda: (m.PANNEAU.update(sauve), m.AUDIO.update(sauve_audio)))
        tous = ["heure", "meteo", "musique", "bonhomme"]
        m.PANNEAU["cycle"] = None
        t0 = 1_800_000_000.0
        vu = lambda t, d=tous, **k: m.cycle_du_panneau(t, d, **k)
        # « ralentis le fade, fais un fade toutes les 30 s » : 30 s par vue, 3 s de fondu
        self.assertEqual(vu(t0)["actuel"], "heure")
        self.assertEqual(vu(t0 + 29)["actuel"], "heure")
        c = vu(t0 + 30)
        self.assertEqual((c["actuel"], c["precedent"], c["fondu"]), ("meteo", "heure", 0.0), "le fondu commence")
        self.assertAlmostEqual(vu(t0 + 31.5)["fondu"], 0.5, msg="lent : a mi-chemin apres 1,5 s")
        self.assertEqual(vu(t0 + 33)["fondu"], 1.0)
        self.assertEqual(vu(t0 + 60)["actuel"], "musique")
        self.assertEqual(vu(t0 + 90)["actuel"], "bonhomme")
        self.assertEqual(vu(t0 + 120)["actuel"], "heure", "puis l'heure a nouveau")
        # rien ne joue : la musique est sautee ; pas de meteo : elle aussi
        self.assertEqual(vu(t0 + 150, ["heure", "bonhomme"])["actuel"], "bonhomme")
        # un morceau qui change : le cycle y saute ; un minuteur qui va sonner : l'heure reste
        self.assertEqual(vu(t0 + 151, tous, saut="musique")["actuel"], "musique")
        self.assertEqual(vu(t0 + 152, tous, urgent=True)["actuel"], "heure")
        self.assertEqual(vu(t0 + 400, tous, urgent=True)["actuel"], "heure", "fige tant que ca presse")
        # qui est disponible
        m.PANNEAU.update(meteo=None, musique_vue=0)
        self.assertEqual(m.cycle_disponible(t0), ["heure", "bonhomme", "chat", "maid"])
        m.PANNEAU.update(meteo={"temp": 12, "code": 3, "quand": t0 - 60}, musique_vue=t0 - 3)
        self.assertEqual(m.cycle_disponible(t0), tous + ["chat", "maid"])
        self.assertEqual(m.cycle_disponible(t0 + 4 * 3600), ["heure", "bonhomme", "chat", "maid"],
                         "une vieille meteo, la musique tue")
        self.assertTrue(m.cycle_urgent([{"genre": "minuteur", "fin": t0 + 200}], [], t0))
        self.assertFalse(m.cycle_urgent([{"genre": "minuteur", "fin": t0 + 900}], [], t0))

        # les dessins, sous la date (lignes 39 a 58), le haut ne bouge pas
        acc = (255, 170, 40)
        t = time.mktime((2026, 10, 22, 9, 41, 20, 0, 0, -1))
        heure = m.image_panneau("horloge", t, accent=acc)
        vue = lambda nom, ecoule=0.0, **k: m.image_panneau("horloge", k.pop("t", t), accent=acc, cycle=dict(
            {"actuel": nom, "precedent": None, "fondu": 1.0, "ecoule": ecoule}, **k))
        m.CFG["jarvis_langue"] = "fr"
        m.PANNEAU["meteo"] = {"temp": 12.4, "code": 61, "jour": True, "min": 8, "max": 15, "quand": t}
        meteo = vue("meteo")
        self.assertTrue((meteo[:39] == heure[:39]).all() and (meteo[59:] == heure[59:]).all())
        self.assertTrue((meteo[42:49] == (235, 235, 245)).all(axis=2).any(), "la temperature")
        self.assertTrue((meteo[39:59] == m.GOUTTE).all(axis=2).any(), "il pleut : des gouttes")
        self.assertTrue((meteo[52:57] == (150, 150, 165)).all(axis=2).any(), "« PLUIE »")
        m.AUDIO.update(actif=True, spectre=[1.0] + [0.1] * 11)
        m.PANNEAU.update(morceau={"titre": "Midnight City", "artistes": "M83"}, cretes=[0.0] * 12)
        musique = vue("musique")
        hauteur = lambda x: int((musique[39:51, x] != 0).any(axis=1).sum())
        self.assertGreater(hauteur(4), hauteur(59) + 5, "la premiere bande, a fond, monte bien plus haut")
        self.assertTrue((musique[53:58] == m.TITRE_RDV).all(axis=2).any(), "le titre du morceau")
        def x_du_bonhomme(h):
            img = vue("bonhomme", t=time.mktime((2026, 10, 22, h, 0, 0, 0, 0, -1)))
            return int(np.nonzero((img[39:56] == acc).all(axis=2).any(axis=0))[0].min())     # son t-shirt
        self.assertLess(x_du_bonhomme(6) + 20, x_du_bonhomme(18), "il marche avec la journee, de gauche a droite")
        # le fondu : a mi-chemin, la moyenne des deux
        mi = vue("musique", precedent="meteo", fondu=0.5)
        m.PANNEAU["cretes"] = [0.0] * 12
        a, b = vue("meteo")[39:59].astype(int), vue("musique")[39:59].astype(int)
        self.assertLessEqual(int(np.abs(mi[39:59].astype(int) - (a + b) / 2).max()), 1)
        # par la boucle : un morceau qui vient de changer, et la vue saute dessus
        m.PANNEAU.update(cycle=None, musique_vue=t, musique_saut=t)
        m.image_du_panneau({"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False}, "horloge", t)
        self.assertEqual(m.PANNEAU["cycle"]["actuel"], "musique")
        self.assertIsNone(m.PANNEAU["musique_saut"], "le saut ne sert qu'une fois")

    def test_le_cycle_se_regle(self):
        # « au pire rajoute tout ca en settings dans le tab panel de Machi Tool, comme ca je
        # peux gerer l'affichage du panneau comme je veux »
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("cycle", "meteo", "musique_vue", "musique_saut")}
        self.addCleanup(lambda: m.PANNEAU.update(sauve))
        self.assertEqual(m.reglages_cycle({}), (30.0, 3.0), "par defaut : 30 s par vue, 3 s de fondu")
        self.assertEqual(m.reglages_cycle({"panneau_cycle_duree": 500, "panneau_cycle_fondu": "abime"}), (120, 3.0))
        self.assertEqual(m.reglages_cycle({"panneau_cycle_duree": 1, "panneau_cycle_fondu": -2}), (5, 0.0))
        for cle in ("panneau_cycle_duree", "panneau_cycle_fondu", "panneau_cycle_meteo", "panneau_cycle_musique",
                    "panneau_cycle_bonhomme", "panneau_cycle_saut"):
            self.assertIn(cle, m.CONFIG_DEFAUT)
        t0 = 1_800_000_000.0
        m.PANNEAU.update(meteo={"temp": 12, "code": 3, "quand": t0}, musique_vue=t0)
        self.assertEqual(m.cycle_disponible(t0, {"panneau_cycle_meteo": False, "panneau_cycle_bonhomme": False,
                                                 "panneau_cycle_chat": False, "panneau_cycle_maid": False}),
                         ["heure", "musique"], "des vues decochees : sautees ; l'heure reste")
        # 10 s par vue, sans fondu : un changement net a 10 s
        m.PANNEAU["cycle"] = None
        m.cycle_du_panneau(t0, ["heure", "bonhomme"], duree=10, fondu_s=0)
        self.assertEqual(m.cycle_du_panneau(t0 + 9, ["heure", "bonhomme"], duree=10, fondu_s=0)["actuel"], "heure")
        c = m.cycle_du_panneau(t0 + 10, ["heure", "bonhomme"], duree=10, fondu_s=0)
        self.assertEqual((c["actuel"], c["fondu"]), ("bonhomme", 1.0))
        # par la boucle : la duree reglee, et le saut sur un nouveau morceau qu'on peut couper
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False,
               "panneau_cycle_duree": 15, "panneau_cycle_meteo": False}
        m.PANNEAU.update(cycle=None, musique_saut=None)
        m.image_du_panneau(cfg, "horloge", t0)
        m.PANNEAU["musique_vue"] = t0 + 14                 # quelque chose joue
        m.image_du_panneau(cfg, "horloge", t0 + 15)
        self.assertEqual(m.PANNEAU["cycle"]["actuel"], "musique", "15 s, et la meteo decochee est sautee")
        m.PANNEAU.update(cycle=None, musique_saut=t0 + 16)
        m.image_du_panneau(dict(cfg, panneau_cycle_saut=False), "horloge", t0 + 16)
        self.assertEqual(m.PANNEAU["cycle"]["actuel"], "heure", "saut coupe : le cycle suit son cours")
        self.assertIsNone(m.PANNEAU["musique_saut"])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_petit_3_et_la_sensibilite_de_l_egaliseur(self):
        # « rajoute un petit :3 qui arrive (qui cligne des yeux de temps en temps) » --
        # « aussi rajoute une sensibilite pour l'egaliseur »
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("cycle", "cretes", "morceau")}
        sauve_audio = {k: m.AUDIO.get(k) for k in ("actif", "spectre")}
        self.addCleanup(lambda: (m.PANNEAU.update(sauve), m.AUDIO.update(sauve_audio)))
        acc = (255, 170, 40)
        t = time.mktime((2026, 10, 22, 9, 41, 1, 0, 0, -1)) + 0.5     # yeux ouverts
        self.assertFalse(m.chat_cligne(t))
        self.assertTrue(m.chat_cligne(t - 1.45), "un clin toutes les 4 s")
        fermes = sum(m.chat_cligne(t + k * 0.05) for k in range(2400))     # deux minutes
        self.assertTrue(30 <= fermes <= 160, "les yeux clignent un peu, pas tout le temps : %d" % fermes)
        c = lambda nom, ecoule, **k: dict({"actuel": nom, "precedent": None, "fondu": 1.0, "ecoule": ecoule}, **k)
        colonnes = lambda img: np.nonzero((img[39:59] != 0).any(axis=2).any(axis=0))[0]
        arrive = colonnes(m.image_panneau("horloge", t, accent=acc, cycle=c("chat", 0.3)))
        pose = colonnes(m.image_panneau("horloge", t, accent=acc, cycle=c("chat", 3.0)))
        self.assertGreater(arrive.min(), pose.min() + 8, "il arrive de la droite")
        self.assertLess(abs((pose.min() + pose.max()) / 2 - 31.5), 2, "puis se pose au milieu")
        ouvert = m.image_panneau("horloge", t, accent=acc, cycle=c("chat", 3.0))
        ferme = m.image_panneau("horloge", t - 1.45, accent=acc, cycle=c("chat", 3.0))
        # « le :3 doit etre a l'endroit » : deux yeux cote a cote, la bouche dessous
        yeux = (ouvert[43:46] == acc).all(axis=2).any(axis=0)
        blocs = int(np.sum(yeux[1:] & ~yeux[:-1]) + yeux[0])
        self.assertEqual(blocs, 2, "deux yeux sur la meme ligne")
        bouche = (ouvert[49:55] == acc).all(axis=2)
        self.assertTrue(bouche.any() and not (ouvert[46:49] != 0).any(), "la bouche sous les yeux, un vide entre")
        self.assertEqual(int((ferme[43] == acc).all(axis=1).sum()), 0, "fermes : un trait au milieu, pas de haut")
        self.assertGreater(int((ferme[44] == acc).all(axis=1).sum()), 0)
        self.assertGreater(int((ouvert[39:59] != 0).any(axis=2).sum()), int((ferme[39:59] != 0).any(axis=2).sum()),
                           "yeux fermes : moins de points allumes")
        # la sensibilite : le meme son, des barres plus ou moins hautes
        m.AUDIO.update(actif=True, spectre=[0.5] * 12)
        m.PANNEAU["morceau"] = None
        def hauteur(sens):
            m.PANNEAU["cretes"] = [0.0] * 12
            img = m.image_panneau("horloge", t, accent=acc, cycle=c("musique", 0.0, sensibilite=sens))
            return int((img[39:57, 4] == 0).all(axis=1).__invert__().sum())
        self.assertLess(hauteur(0.5), hauteur(1.0))
        self.assertLess(hauteur(1.0), hauteur(2.0))
        self.assertEqual(m.sensibilite_eq({}), 1.0)
        self.assertEqual(m.sensibilite_eq({"panneau_eq_sensibilite": 9}), 3.0)
        self.assertEqual(m.sensibilite_eq({"panneau_eq_sensibilite": "abime"}), 1.0)
        # par la boucle : la sensibilite reglee arrive jusqu'au dessin
        vrai = m.image_panneau
        self.addCleanup(lambda: setattr(m, "image_panneau", vrai))
        vus = []
        m.image_panneau = lambda *a, **k: (vus.append(k.get("cycle")), vrai(*a, **k))[1]
        m.PANNEAU["cycle"] = None
        m.image_du_panneau({"panneau_contenu": "horloge", "panneau_eq_sensibilite": 2.5, "panneau_rdv": False}, "horloge", t)
        self.assertEqual(vus[-1]["sensibilite"], 2.5)
        self.assertTrue(m.CONFIG_DEFAUT["panneau_cycle_chat"])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_bonhomme_marche_en_douceur(self):
        # « tu peux rendre le petit bonhomme plus sympa avec un peu plus de fps sur l'animation ? »
        m = self.m
        acc = (255, 170, 40)
        t0 = time.mktime((2026, 10, 22, 14, 20, 0, 0, 0, -1)) + 0.5     # yeux ouverts
        zone = lambda t, ecoule=10.0: m._zone_du_cycle("bonhomme", t, acc, [], [], ecoule)
        # avant : deux dessins, quatre fois par seconde ; maintenant une pose par image, 30 par seconde
        images = [zone(t0 + k / 30.0) for k in range(31)]
        self.assertEqual(len({i.tobytes() for i in images[:30]}), 30, "chaque image de la seconde est neuve")
        for a, b in zip(images, images[1:]):
            change = int((a.astype(int) != b.astype(int)).any(axis=2).sum())
            self.assertTrue(0 < change < 80, "d'une image a l'autre, il bouge un peu, sans sauter : %d" % change)
        hanches = [m.bonhomme_pose(30.0, t0 + k / 30.0)["hanche"][1] for k in range(34)]
        self.assertGreater(max(hanches) - min(hanches), 0.3, "il rebondit a chaque pas")
        p = m.bonhomme_pose(30.0, t0)
        self.assertLessEqual(max(p["cheville0"][1], p["cheville1"][1]), m.BONHOMME_SOL - 0.8,
                             "le pied le plus bas touche le chemin, sans s'y enfoncer")
        # habille : son t-shirt de la couleur de la guirlande, la peau, le jean, les baskets
        img = images[0]
        for couleur in (acc, m.PEAU, m.JEAN, m.BASKETS):     # (sur un pas ; a peu pres : les bords sont adoucis)
            ecart = np.abs(np.stack(images)[:, 39:56].astype(int) - np.array(couleur)).max(axis=3)
            self.assertTrue((ecart <= 40).any(), couleur)
        self.assertTrue((img[:39] == 0).all() and (img[59:] == 0).all(), "il tient sous la date")
        # un coucou par passage : il se tourne vers nous et leve la main au-dessus de la tete
        coucou = m.bonhomme_pose(30.0, t0, ecoule=5.0)
        self.assertTrue(coucou["face"])
        self.assertLess(coucou["main1"][1], coucou["tete"][1])
        self.assertFalse(m.bonhomme_pose(30.0, t0, ecoule=10.0)["face"], "puis il repart")
        self.assertFalse(m.bonhomme_pose(30.0, t0, ecoule=None)["face"], "pas pendant un fondu")
        main = [m.bonhomme_pose(30.0, t0 + k / 30.0, ecoule=5.0)["main1"][0] for k in range(10)]
        self.assertGreater(max(main) - min(main), 1.0, "la main s'agite")
        face = zone(t0, 5.0)
        self.assertGreaterEqual(int((face[39:59] == (30, 20, 20)).all(axis=2).sum()), 2, "de face : deux yeux")
        # minuit, 23 h 59 : il entre et sort par les bords sans rien casser
        for h, mi in ((0, 0), (23, 59)):
            bord = zone(time.mktime((2026, 10, 22, h, mi, 59, 0, 0, -1)))
            self.assertTrue((bord[39:56] != 0).any())

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_chaton_maid(self):
        # « tu peux faire un petit chat ? en maid ? genre femboy ? » -- « avec des cheveux
        # noirs et un costume de maid noir et blanc :) » -- « la maid ne tient rien dans la
        # main, elle marche vers la droite » -- « fais marcher la maid sur place en fonction
        # de l'avancement de la journee, comme avec le bonhomme »
        m = self.m
        acc = (255, 170, 40)
        t0 = time.mktime((2026, 10, 22, 14, 20, 0, 0, 0, -1))
        t0 = (t0 // m.MAID_ENVIE_S) * m.MAID_ENVIE_S + 4.2      # hors de ses petites envies...
        while m.chat_cligne(t0 + 0.9) or m.chat_cligne(t0 + 1.9):  # ... les yeux ouverts
            t0 += m.MAID_ENVIE_S
        self.assertEqual(m.maid_envie(t0, 0), (None, 0.0))
        zone = lambda t: m._zone_du_cycle("maid", t, acc, [], [], 10.0)
        proche = lambda img, couleur, tol=30: (np.abs(img[39:59].astype(int) - np.array(couleur)).max(axis=2) <= tol)
        repos = zone(t0)
        self.assertTrue((repos[:39] == 0).all() and (repos[59:] == 0).all(), "elle tient sous la date")
        self.assertTrue(proche(repos, m.NOIR_CHAT).sum() >= 15, "les cheveux, les oreilles, la queue : noirs")
        self.assertTrue(proche(repos, m.ROBE).sum() >= 4, "la robe noire")
        self.assertTrue(proche(repos, m.TABLIER, 60).sum() >= 6, "le tablier, la coiffe, les chaussettes : blancs")
        self.assertTrue(proche(repos, m.ROSE_OREILLE, 60).any(), "le dedans de l'oreille, rose")
        self.assertTrue(proche(repos, acc, 0).any(), "le ruban, de la couleur de la guirlande")
        self.assertLess(max(m.NOIR_CHAT + m.ROBE), 90, "du noir, mais pas une LED eteinte")
        self.assertGreater(min(m.NOIR_CHAT + m.ROBE), 30)
        # sur le chemin de la journee, comme le bonhomme : sa place, c'est l'heure
        decor = np.zeros_like(repos)
        x = m.chemin_de_la_journee(decor, t0, acc)
        self.assertTrue((repos[m.BONHOMME_SOL] == decor[m.BONHOMME_SOL]).all(axis=1).sum() >= 50, "le chemin")
        self.assertTrue((repos == m.SOLEIL).all(axis=2).any(), "l'apres-midi, le soleil")
        self.assertAlmostEqual(m.maid_pose(x, t0)["hanche"][0], x)
        x_a = lambda h: m.chemin_de_la_journee(np.zeros_like(repos), time.mktime((2026, 10, 22, h, 0, 0, 0, 0, -1)), acc)
        self.assertLess(x_a(6) + 20, x_a(18), "elle avance avec la journee")
        cols = np.nonzero(proche(repos, m.NOIR_CHAT)[:16].any(axis=0))[0]      # (au-dessus du chemin)
        self.assertTrue(x - 7 <= cols.min() and cols.max() <= x + 5, "et elle est bien la ou en est la journee")
        plus_tard = m.chemin_de_la_journee(np.zeros_like(repos), t0 + 3, acc)
        self.assertLess(abs(m.maid_pose(plus_tard, t0 + 3)["hanche"][0] - x), 0.01, "elle reste sur place")
        # rien dans les mains : devant elle, plus rien (ni plateau, ni tasse)
        self.assertTrue((repos[46:56, int(x) + 6:] == 0).all())
        # « pas d'anti-aliasing : du pixel art net, avec un contour net » -- adoucie, elle en avait 85
        boite = repos[39:56, int(x) - 9:int(x) + 9]
        teintes = {tuple(int(v) for v in p) for p in boite.reshape(-1, 3)} - {(0, 0, 0)}
        self.assertLessEqual(len(teintes), 20, "pas de demi-teintes : quelques couleurs franches")
        self.assertGreaterEqual(int((boite == m.MAID_CONTOUR).all(axis=2).sum()), 20, "un trait autour d'elle")
        self.assertTrue((repos[m.BONHOMME_SOL] != m.MAID_CONTOUR).any(axis=1).all(), "le trait ne mord pas le chemin")
        # elle marche sur place : les pieds passent sous elle, se levent, touchent le chemin
        poses = [m.maid_pose(x, t0 + k / 60.0) for k in range(60)]
        pieds = [p["cheville0"][0] - x for p in poses]
        self.assertGreater(max(pieds) - min(pieds), 2.5, "un pas")
        self.assertTrue(any(p["cheville0"][1] < m.MAID_SOL - 1.5 for p in poses), "leve, il monte")
        self.assertAlmostEqual(max(max(p["cheville0"][1], p["cheville1"][1]) for p in poses), m.MAID_SOL - 0.9)
        # 30 images par seconde
        images = [zone(t0 + k / 30.0) for k in range(30)]
        self.assertEqual(len({i.tobytes() for i in images}), 30, "chaque image de la seconde est neuve")
        # elle cligne des yeux : un grand oeil de deux pixels, un trait ferme
        ouvert = int(proche(repos, m.YEUX_CHAT, 0).sum())
        cligne = next(t0 + k / 100.0 for k in range(400) if m.chat_cligne(t0 + k / 100.0 + 0.9))
        self.assertIsNone(m.maid_envie(cligne, 0)[0])
        ferme = int(proche(zone(cligne), m.YEUX_CHAT, 0).sum())
        self.assertEqual((ouvert, ferme), (2, 1))
        # de temps en temps, un petit coeur s'envole derriere elle
        coeur = next(n * m.MAID_ENVIE_S + 0.9 for n in range(int(t0 // m.MAID_ENVIE_S), int(t0 // m.MAID_ENVIE_S) + 500)
                     if m.maid_envie(n * m.MAID_ENVIE_S + 0.9, 0)[0] == "coeur")
        def rose(img):                                        # du rose (qui s'efface), derriere elle
            r, g, b = (img[39:59].astype(int)[..., i] for i in range(3))
            derriere = np.arange(m.PANNEAU_L) < x - 2
            return int(((r > 40) & (r > 2 * g) & (b > g) & derriere).sum())
        self.assertGreaterEqual(rose(zone(coeur)), 12, "le coeur")
        self.assertEqual(rose(repos), 0)
        # au petit matin, pres du bord : le coeur passe devant elle ; minuit, 23 h 59 : rien ne casse
        matin = time.mktime((2026, 10, 22, 0, 30, 0, 0, 0, -1))
        m.PANNEAU["present"] = False                         # (pas de veille : rien que le coeur en rose)
        self.addCleanup(m.PANNEAU.pop, "present", None)
        matin = next(n * m.MAID_ENVIE_S + 0.9 for n in range(int(matin // m.MAID_ENVIE_S), int(matin // 9) + 2000)
                     if m.maid_envie(n * m.MAID_ENVIE_S + 0.9, 1)[0] == "coeur")
        img = zone(matin)
        r, g, b = (img[39:59].astype(int)[..., i] for i in range(3))
        self.assertGreaterEqual(int(((r > 40) & (r > 2 * g) & (b > g)).sum()), 12)
        for h, mi in ((0, 0), (23, 59)):
            self.assertTrue((zone(time.mktime((2026, 10, 22, h, mi, 59, 0, 0, -1)))[39:56] != 0).any())
        # dans le cycle, apres le :3, et une case pour la garder ou non
        self.assertTrue(m.CONFIG_DEFAUT["panneau_cycle_maid"])
        self.assertEqual(m.CYCLE_ORDRE[-1], "maid")
        m.PANNEAU["cycle"] = {"actuel": "chat", "precedent": None, "depuis": t0 - 31}
        self.addCleanup(lambda: m.PANNEAU.update(cycle=None))
        c = m.cycle_du_panneau(t0, m.cycle_disponible(t0))
        self.assertEqual(c["actuel"], "maid")
        self.assertEqual(c["ecoule_precedent"], 31, "la vue qui s'en va garde son temps : elle ne saute pas")
        self.assertNotIn("maid", m.cycle_disponible(t0, {"panneau_cycle_maid": False}))

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_maid_la_nuit_et_ses_envies(self):
        # « rajoute aussi une interface de nuit lorsque je veille tard pour la maid » -- « rajoute
        # plusieurs animations en fonction de la fatigue, ou des petites animations random »
        m = self.m
        acc = (255, 170, 40)
        sauve = {k: m.PANNEAU.get(k) for k in ("present", "debout_depuis")}
        self.addCleanup(lambda: m.PANNEAU.update(sauve))
        heure = lambda h, mi=0: time.mktime((2026, 10, 22, h, mi, 0, 0, 0, -1))
        # la fatigue : l'heure, puis les heures devant le PC sans pause
        self.assertEqual(m.fatigue_maid(heure(14)), 0.0)
        self.assertTrue(0 < m.fatigue_maid(heure(22)) < 0.3)
        self.assertGreaterEqual(m.fatigue_maid(heure(1)), 0.6)
        self.assertEqual(m.fatigue_maid(heure(4)), 1.0)
        self.assertEqual(m.fatigue_maid(heure(8)), 0.0)
        self.assertAlmostEqual(m.fatigue_maid(heure(14), heure(14) - 6 * 3600), 0.3, msg="six heures sans pause")
        self.assertEqual([m.niveau_fatigue(f) for f in (0.0, 0.5, 0.9)], [0, 1, 2])
        self.assertLess(m.MAID_PAS_S[0], m.MAID_PAS_S[2], "epuisee, elle traine des pieds")
        # es-tu la ? le clavier et la souris le disent
        m.PANNEAU.update(present=None, debout_depuis=None)
        self.assertTrue(m.suivre_presence(heure(1), inactivite=10))
        self.assertEqual(m.PANNEAU["debout_depuis"], heure(1) - 10)
        self.assertFalse(m.suivre_presence(heure(1), inactivite=400))
        self.assertIsNone(m.PANNEAU["debout_depuis"])
        # l'interface de nuit : tard, et seulement si tu veilles
        self.assertTrue(m.maid_veille(heure(1), True) and m.maid_veille(heure(23, 30), True))
        self.assertFalse(m.maid_veille(heure(1), False), "tu dors : pas d'interface de nuit")
        self.assertFalse(m.maid_veille(heure(22), True) or m.maid_veille(heure(6), True))
        # les envies : tirees au sort -- le meme instant donne la meme --, selon la fatigue
        def envies(niveau):
            return {m.maid_envie(heure(12) + k * m.MAID_ENVIE_S + 0.5, niveau)[0] for k in range(400)}
        self.assertEqual(m.maid_envie(heure(12) + 0.5, 0), m.maid_envie(heure(12) + 0.5, 0))
        en_forme, fatiguee, epuisee = envies(0), envies(1), envies(2)
        self.assertEqual(en_forme, {"saut", "derriere", "coeur", "reverence", None})
        self.assertTrue({"baille", "frotte"} <= fatiguee and not {"zzz", "pique"} & fatiguee)
        self.assertTrue({"pique", "zzz", "baille"} <= epuisee and "saut" not in epuisee)
        self.assertIsNone(m.maid_envie(heure(12) + 4.5, 2)[0], "entre deux envies, elle marche")

        def instant(nom, niveau, u=0.5, h=14):
            for n in range(int(heure(h) // m.MAID_ENVIE_S), int(heure(h) // m.MAID_ENVIE_S) + 4000):
                t = n * m.MAID_ENVIE_S + u * m.MAID_ENVIES[nom]
                if m.maid_envie(t, niveau)[0] == nom:
                    return t
            self.fail(nom)
        x = 30.0
        fatigues = (0.0, 0.5, 0.9)
        pose = lambda nom, niveau=0, u=0.5: m.maid_pose(x, instant(nom, niveau, u=u), fatigues[niveau])
        calme = (heure(14) // m.MAID_ENVIE_S) * m.MAID_ENVIE_S + 5.0
        repos = m.maid_pose(x, calme)
        self.assertEqual((repos["envie"], repos["calme"], repos["oreilles"]), (None, 0.0, 0.0))
        # en forme : un petit saut, se retourner, un coeur (sans s'arreter), une reverence
        saut = pose("saut")
        self.assertLess(saut["hanche"][1], repos["hanche"][1] - 1.5)
        self.assertEqual(saut["yeux"], "contents")
        self.assertTrue(pose("derriere")["miroir"] and not repos["miroir"])
        coeur = pose("coeur")
        self.assertEqual((coeur["calme"], coeur["yeux"]), (0.0, "contents"))
        rev = pose("reverence")
        self.assertGreater(rev["tete"][0], repos["tete"][0] + 1)
        self.assertGreater(rev["tete"][1], repos["tete"][1] + 0.5)
        # fatiguee : les paupieres lourdes, les oreilles basses ; elle baille, se frotte l'oeil
        lourde = m.maid_pose(x, calme + 0.3 if not m.chat_cligne(calme + 1.2) else calme + 2.3, 0.5)
        self.assertEqual((lourde["yeux"], lourde["oreilles"]), ("lourds", 0.6))
        baille = pose("baille", 1)
        self.assertEqual((baille["bouche"], baille["yeux"]), ("ouverte", "fermes"))
        dist = lambda a, b: float(np.hypot(a[0] - b[0], a[1] - b[1]))
        self.assertLess(dist(baille["main1"], (baille["tete"][0] + 2.4, baille["tete"][1] + 2.2)), 0.1,
                        "la main devant la bouche")
        frotte = pose("frotte", 1)
        self.assertLess(dist(frotte["main1"], (frotte["tete"][0] + 1.9, frotte["tete"][1] + 0.9)), 0.5)
        # epuisee : elle pique du nez (la tete tombe puis se releve), s'endort debout
        tombe, releve = pose("pique", 2, 0.7), pose("pique", 2, 0.95)
        self.assertGreater(tombe["tete"][1], releve["tete"][1] + 1.0)
        self.assertEqual(tombe["oreilles"], 1.1)
        m.PANNEAU["present"] = False
        img = m._zone_du_cycle("maid", instant("zzz", 2, h=3, u=0.4), acc, [], [], 10.0)
        r, g, b = (img[39:59].astype(int)[..., i] for i in range(3))
        self.assertGreaterEqual(int(((r > 100) & (r == g) & (b > r + 25)).sum()), 8, "des « z » qui montent")
        # la nuit, si tu veilles : des etoiles, la chemise de nuit, le bonnet
        proche = lambda img, couleur, tol=30: (np.abs(img[39:59].astype(int) - np.array(couleur)).max(axis=2) <= tol)
        nuit_t = (heure(1) // m.MAID_ENVIE_S) * m.MAID_ENVIE_S + 5.0
        m.PANNEAU.update(present=True, debout_depuis=None)
        veille = m._zone_du_cycle("maid", nuit_t, acc, [], [], 10.0)
        m.PANNEAU["present"] = False
        dort = m._zone_du_cycle("maid", nuit_t, acc, [], [], 10.0)
        etoiles = lambda img: sum(bool(img[y, x_].any()) for x_, y in m._ETOILES)
        self.assertGreaterEqual(etoiles(veille), 8)
        self.assertLessEqual(etoiles(dort), 2, "tu dors : pas d'etoiles")
        self.assertGreaterEqual(int(proche(veille, m.PYJAMA, 20).sum()), 6, "la chemise de nuit")
        self.assertEqual(int(proche(dort, m.PYJAMA, 20).sum()), 0)
        self.assertGreaterEqual(int(proche(veille, acc, 60).sum()), 6, "le bonnet de nuit")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_bulle_de_claude_code(self):
        # « tu peux ajouter une bulle de statut quand Claude est en train de reflechir ? rouge lorsque
        # quelque chose est bloque et demande une confirmation de l'utilisateur, jaune quand Claude
        # travaille et vert lorsque c'est fini »
        m = self.m
        self.addCleanup(lambda: (m.CLAUDE_CODE["sessions"].clear(), m.CLAUDE_CODE.update(vu=0.0)))
        m.CLAUDE_CODE["sessions"].clear()
        t = 1_800_000_000.0
        evt = lambda nom, **k: dict({"hook_event_name": nom, "session_id": "s1",
                                     "cwd": "C:\\Users\\moi\\MachiToolkit"}, **k)
        # ce que disent les crochets de Claude Code
        self.assertEqual(m.etat_de_claude_code(evt("UserPromptSubmit", prompt="ma demande")), "travaille")
        self.assertEqual(m.etat_de_claude_code(evt("PreToolUse", tool_name="Bash")), "travaille")
        self.assertEqual(m.etat_de_claude_code(evt("PostToolUse", tool_name="Bash")), "travaille")
        self.assertEqual(m.etat_de_claude_code(evt("PreToolUse", tool_name="AskUserQuestion")), "bloque")
        self.assertEqual(m.etat_de_claude_code(evt("PreToolUse", tool_name="ExitPlanMode")), "bloque")
        self.assertEqual(m.etat_de_claude_code(evt("Notification", notification_type="permission_prompt")), "bloque")
        self.assertEqual(m.etat_de_claude_code(evt("Notification", message="Claude needs your permission to use Bash")),
                         "bloque")
        self.assertIsNone(m.etat_de_claude_code(evt("Notification", notification_type="idle_prompt",
                                                    message="Claude is waiting for your input")))
        self.assertEqual(m.etat_de_claude_code(evt("Stop")), "fini")
        self.assertEqual(m.etat_de_claude_code(evt("SessionEnd")), "termine")
        # une session : jaune, rouge (il attend ton accord), jaune (accorde), vert ; puis plus rien
        self.assertIsNone(m.etat_claude(t))
        m.recevoir_claude_code(evt("UserPromptSubmit", prompt="ma demande"), t)
        self.assertEqual(m.etat_claude(t), "travaille")
        self.assertNotIn("ma demande", json.dumps(m.CLAUDE_CODE), "la demande n'est pas gardee")
        self.assertEqual(m.CLAUDE_CODE["sessions"]["s1"]["dossier"], "MachiToolkit")
        m.recevoir_claude_code(evt("Notification", notification_type="permission_prompt"), t + 5)
        self.assertEqual(m.etat_claude(t + 5), "bloque")
        m.recevoir_claude_code(evt("PostToolUse", tool_name="Bash"), t + 9)
        self.assertEqual(m.etat_claude(t + 9), "travaille")
        m.recevoir_claude_code(evt("Stop"), t + 20)
        self.assertEqual(m.etat_claude(t + 20), "fini")
        self.assertIsNone(m.etat_claude(t + 21 + m.CLAUDE_VERT_S), "vert dix minutes, puis plus rien")
        # deux sessions : la plus pressante l'emporte ; une session fermee s'efface
        m.recevoir_claude_code(dict(evt("UserPromptSubmit"), session_id="s2"), t + 30)
        m.recevoir_claude_code(evt("PreToolUse", tool_name="AskUserQuestion"), t + 32)
        self.assertEqual(m.etat_claude(t + 33), "bloque")
        m.recevoir_claude_code(evt("SessionEnd"), t + 34)
        self.assertEqual(m.etat_claude(t + 35), "travaille")
        self.assertIsNone(m.etat_claude(t + 31 + m.CLAUDE_OUBLI_S), "sans nouvelles en plein travail : on ne sait plus")
        # sur le panneau : en haut a droite, au-dessus de l'heure, de la couleur de l'etat
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False, "panneau_cycle": False}
        m.CLAUDE_CODE["sessions"].clear()
        coin = lambda img: img[0:9, 50:64]
        sans = m.image_du_panneau(cfg, "horloge", t)
        self.assertFalse(coin(sans).any())
        for nom, etat in (("UserPromptSubmit", "travaille"), ("Stop", "fini")):
            m.recevoir_claude_code(evt(nom), t)
            img = m.image_du_panneau(cfg, "horloge", t)
            self.assertGreaterEqual(int((coin(img) == m.CLAUDE_COULEURS[etat]).all(axis=2).sum()), 40, etat)
            self.assertTrue((img[9:] == sans[9:]).all(), "le reste ne bouge pas")
        m.recevoir_claude_code(evt("Notification", notification_type="permission_prompt"), t)
        rouges = [coin(m.image_du_panneau(cfg, "horloge", t + k / 10.0)) for k in range(7)]
        self.assertGreater(len({r.tobytes() for r in rouges}), 2, "rouge : elle bat")
        r = rouges[0].astype(int)
        self.assertGreaterEqual(int(((r[..., 0] > 100) & (r[..., 1] < r[..., 0] // 2)).sum()), 40)
        m.recevoir_claude_code(evt("UserPromptSubmit"), t)
        points = {coin(m.image_du_panneau(cfg, "horloge", t + k / 10.0)).tobytes() for k in range(10)}
        self.assertGreaterEqual(len(points), 3, "jaune : les trois points sautillent")
        self.assertFalse(coin(m.image_du_panneau(dict(cfg, panneau_claude=False), "horloge", t)).any(), "decochee")
        self.assertTrue(m.CONFIG_DEFAUT["panneau_claude"])
        # par le serveur local : la cle exigee, et rien en retour (ce qu'un crochet ecrit, Claude Code le lit)
        m.CLAUDE_CODE["sessions"].clear()
        garde = m.CFG.get("api_jeton")
        m.CFG["api_jeton"] = "cle-locale"
        self.addCleanup(m.CFG.__setitem__, "api_jeton", garde)
        serveur = m.http.server.ThreadingHTTPServer(("127.0.0.1", 0), m.Passerelle)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (serveur.shutdown(), serveur.server_close()))
        port = serveur.server_address[1]

        def poster(jeton):
            req = urllib.request.Request("http://127.0.0.1:%d/claude" % port, method="POST",
                                         data=json.dumps(evt("UserPromptSubmit")).encode(),
                                         headers={"Content-Type": "application/json", "X-Jeton": jeton})
            try:
                with urllib.request.urlopen(req, timeout=5) as rep:
                    return rep.status, rep.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        self.assertEqual(poster("faux")[0], 401)
        self.assertIsNone(m.etat_claude())
        self.assertEqual(poster("cle-locale"), (204, b""))
        self.assertEqual(m.etat_claude(), "travaille")
        # brancher : nos crochets dans les reglages de Claude Code, le reste intact ; puis les retirer
        dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dossier, True)
        chemin = os.path.join(dossier, ".claude", "settings.json")
        os.makedirs(os.path.dirname(chemin))
        a_toi = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo fini"}]}]}}
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(a_toi, f)
        cfg = {"api_port": port, "api_jeton": "cle-locale"}
        m.brancher_claude_code(cfg, chemin)
        m.brancher_claude_code(cfg, chemin)                  # deux fois : pas de doublon
        with open(chemin, encoding="utf-8") as f:
            r = json.load(f)
        self.assertEqual(r["model"], "opus")
        self.assertEqual(set(r["hooks"]), set(m.CLAUDE_EVENEMENTS))
        self.assertEqual(r["hooks"]["Stop"][0]["hooks"][0]["command"], "echo fini", "ton crochet reste")
        self.assertEqual(sum(m._crochet_a_nous(g) for g in r["hooks"]["Stop"]), 1)
        self.assertEqual(r["hooks"]["PreToolUse"][0]["matcher"], "*")
        commande = r["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("X-Jeton: cle-locale", commande)
        self.assertIn("127.0.0.1:%d/claude" % port, commande)
        self.assertTrue(m.claude_code_branche(chemin))
        self.assertTrue(os.path.exists(chemin + ".machitool.bak"))
        if shutil.which("curl") and shutil.which("bash"):
            # la vraie commande, comme Claude Code la lance : ce qu'il lui donne arrive, rien ne ressort
            m.CLAUDE_CODE["sessions"].clear()
            sortie = subprocess.run(["bash", "-c", commande], input=json.dumps(evt("Stop")), capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual((sortie.returncode, sortie.stdout), (0, ""))
            self.assertEqual(m.etat_claude(), "fini")
        m.brancher_claude_code(cfg, chemin, brancher=False)
        with open(chemin, encoding="utf-8") as f:
            self.assertEqual(json.load(f), a_toi, "debranche : comme avant")
        self.assertFalse(m.claude_code_branche(chemin))
        # un fichier qui ne se lit pas n'est pas ecrase ; pas de fichier du tout : il le cree
        with open(chemin, "w", encoding="utf-8") as f:
            f.write("{ abime")
        self.assertRaises(ValueError, m.brancher_claude_code, cfg, chemin)
        with open(chemin, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{ abime")
        neuf = os.path.join(dossier, "autre", ".claude", "settings.json")
        m.brancher_claude_code(cfg, neuf)
        self.assertTrue(m.claude_code_branche(neuf))

    def test_la_bulle_des_sessions_cloud(self):
        # « on peut partir sur le lien des sessions cloud, avec la variable d'environnement » :
        # les crochets du depot posent l'etape chez BrainDebugger, Machi Tool la releve
        m = self.m
        self.addCleanup(lambda: (m.CLAUDE_CODE["sessions"].clear(), m.CLAUDE_CODE.update(distantes={}, vu_cloud=0.0)))
        m.CLAUDE_CODE["sessions"].clear()
        # la cle de la bulle : la meme que BrainDebugger calcule (vecteur commun, voir son test)
        self.assertEqual(m.cle_bulle_claude({"pont_cle": "cle-de-test"}), "bbb1f950f42614c413242a554340eaac")
        self.assertEqual(m.cle_bulle_claude({"pont_cle": ""}), "")
        # ce que BrainDebugger rend : la derniere etape de chaque session, et son age
        t = 1_800_000_000.0
        rendu = {"sessions": [
            {"hook_event_name": "PreToolUse", "session_id": "c1", "tool_name": "Bash", "age_s": 3, "dossier": "MachiToolkit"},
            {"hook_event_name": "Stop", "session_id": "c2", "age_s": 30}]}
        self.assertEqual(m.relever_bulle_distante({}, t, lire=lambda cfg: rendu), 2)
        self.assertEqual(m.etat_claude(t), "travaille")
        self.assertEqual(m.CLAUDE_CODE["distantes"]["c1"]["quand"], t - 3)
        rendu["sessions"][0] = {"hook_event_name": "Notification", "session_id": "c1",
                                "notification_type": "permission_prompt", "age_s": 1}
        m.relever_bulle_distante({}, t, lire=lambda cfg: rendu)
        self.assertEqual(m.etat_claude(t), "bloque", "une session cloud attend ton accord : rouge")
        m.relever_bulle_distante({}, t, lire=lambda cfg: {"sessions": [rendu["sessions"][1]]})
        self.assertEqual(m.etat_claude(t), "fini", "chaque releve remplace la precedente")
        m.relever_bulle_distante({}, t, lire=lambda cfg: {"sessions": []})
        self.assertIsNone(m.etat_claude(t))
        # les sessions locales comptent toujours, avec celles du cloud
        m.recevoir_claude_code({"hook_event_name": "UserPromptSubmit", "session_id": "local"}, t)
        m.relever_bulle_distante({}, t, lire=lambda cfg: {"sessions": [rendu["sessions"][1]]})
        self.assertEqual(m.etat_claude(t), "travaille")
        # le fil : seulement la passerelle reglee ; un BrainDebugger d'avant ne casse rien
        vrai = m._lire_bulle_distante
        self.addCleanup(lambda: setattr(m, "_lire_bulle_distante", vrai))
        lus = []
        m._lire_bulle_distante = lambda cfg: lus.append(1) or {"sessions": []}
        m.veiller_bulle_distante({"pont_cle": "", "pont_site": "https://x"}, tours=1)
        self.assertEqual(lus, [], "sans cle de passerelle : rien")
        m.veiller_bulle_distante({"pont_cle": "k", "pont_site": "https://x", "panneau_claude": False}, tours=1)
        self.assertEqual(lus, [], "bulle decochee : rien")
        m.veiller_bulle_distante({"pont_cle": "k", "pont_site": "https://x"}, tours=1)
        self.assertEqual(lus, [1])

        def introuvable(cfg):
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        m._lire_bulle_distante = introuvable
        m.veiller_bulle_distante({"pont_cle": "k", "pont_site": "https://x"}, tours=1)
        # les crochets du depot : le script, tel que Claude Code le lance dans le cloud
        with open(os.path.join(RACINE, ".claude", "settings.json"), encoding="utf-8") as f:
            reglages = json.load(f)
        self.assertEqual(set(reglages["hooks"]), set(m.CLAUDE_EVENEMENTS))
        commande = reglages["hooks"]["Stop"][0]["hooks"][0]["command"]
        self.assertIn(".claude/bulle_claude.py", commande)
        self.assertTrue(commande.endswith("|| true"), "jamais d'erreur dans Claude Code")
        recus = []

        class Faux(m.http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                corps = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                recus.append((self.headers.get("X-Machitool-Bulle"), json.loads(corps)))
                self.send_response(204)
                self.end_headers()
        serveur = m.http.server.ThreadingHTTPServer(("127.0.0.1", 0), Faux)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (serveur.shutdown(), serveur.server_close()))
        script = os.path.join(RACINE, ".claude", "bulle_claude.py")

        dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dossier, True)

        def crochet(evenement, cle="la-cle", nom="MACHITOOL_BULLE_CLE", fichier=os.path.join(dossier, "absent")):
            env = dict(os.environ, MACHITOOL_BULLE_URL="http://127.0.0.1:%d/api/machitool/claude"
                       % serveur.server_address[1], NO_PROXY="127.0.0.1", no_proxy="127.0.0.1",
                       MACHITOOL_BULLE_FICHIER=fichier)
            env.pop("MACHITOOL_BULLE_CLE", None)
            if cle:
                env[nom] = cle
            r = subprocess.run([sys.executable, script], input=json.dumps(evenement), capture_output=True,
                               text=True, env=env, timeout=10)
            self.assertEqual((r.returncode, r.stdout), (0, ""), "il ne dit rien a Claude Code")
        crochet({"hook_event_name": "PreToolUse", "session_id": "c1", "cwd": "/home/user/MachiToolkit",
                 "tool_name": "Write", "tool_input": {"content": "un secret"}, "transcript_path": "/x"})
        self.assertEqual(recus, [("la-cle", {"hook_event_name": "PreToolUse", "session_id": "c1",
                                             "dossier": "MachiToolkit", "tool_name": "Write"})])
        self.assertNotIn("secret", json.dumps(recus))
        crochet({"hook_event_name": "UserPromptSubmit", "session_id": "c1", "prompt": "ma demande"})
        self.assertNotIn("ma demande", json.dumps(recus), "la demande ne part pas")
        n = len(recus)
        crochet({"hook_event_name": "Notification", "session_id": "c1", "notification_type": "idle_prompt",
                 "message": "Claude is waiting for your input"})
        crochet({"hook_event_name": "Stop", "session_id": "c1"}, cle="")
        self.assertEqual(len(recus), n, "rien a dire, ou pas de cle : rien ne part")
        crochet({"hook_event_name": "Notification", "session_id": "c1", "notification_type": "permission_prompt",
                 "message": "Claude needs your permission to use Bash"})
        self.assertEqual(m.etat_de_claude_code(recus[-1][1]), "bloque")
        # « \ufeffMACHITOOL_BULLE_CLE=... » : la marque d'encodage qu'un copier-coller laissait devant
        crochet({"hook_event_name": "Stop", "session_id": "c1"}, cle=" la-cle\n", nom="\ufeffMACHITOOL_BULLE_CLE")
        self.assertEqual(recus[-1][0], "la-cle", "la variable est trouvee quand meme")
        # une session ouverte avant la variable : la cle dans .claude/bulle_cle.local (jamais commite)
        fichier = os.path.join(dossier, "bulle_cle.local")
        with open(fichier, "w", encoding="utf-8-sig") as f:
            f.write("MACHITOOL_BULLE_CLE=cle-du-fichier\n")
        crochet({"hook_event_name": "Stop", "session_id": "c1"}, cle="", fichier=fichier)
        self.assertEqual(recus[-1][0], "cle-du-fichier")
        with open(os.path.join(RACINE, ".gitignore"), encoding="utf-8") as f:
            self.assertIn(".claude/bulle_cle.local", f.read(), "un secret : jamais dans le depot")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_les_notifications_discord(self):
        # « tu peux faire en sorte que ca detecte quand j'ai une notification en attente sur Discord ? »
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("discord", "etat")}
        self.addCleanup(lambda: m.PANNEAU.update(sauve))
        lis = m.notifications_discord_du_titre
        self.assertEqual(lis("(3) Discord | #general | Mon serveur"), 3)
        self.assertEqual(lis("(12) Discord"), 12)
        self.assertEqual(lis("Discord"), 0)
        self.assertEqual(lis("• Discord | #general"), 0, "des messages non lus, mais rien qui t'attende")
        self.assertEqual(lis("Discord Updater"), 0)
        self.assertEqual(m.lire_discord(["Discord", "(2) Discord | @ami"]), 2, "le plus grand des titres")
        self.assertIsNone(m.lire_discord([]), "Discord n'est pas ouvert")
        # le fil des sources : toutes les cinq secondes, panneau branche
        vrai = m.lire_discord
        self.addCleanup(lambda: setattr(m, "lire_discord", vrai))
        m.lire_discord = lambda titres=None: 4
        m.PANNEAU.update(etat="connecte", discord=None)
        m.veiller_sources_panneau({"panneau_contenu": "ambiance"}, tours=1, maintenant=100.0)
        self.assertEqual(m.PANNEAU["discord"], 4)
        m.PANNEAU["discord"] = None
        m.veiller_sources_panneau({"panneau_contenu": "ambiance", "panneau_discord": False}, tours=1, maintenant=200.0)
        self.assertIsNone(m.PANNEAU["discord"], "decochee : il ne lit rien")
        # sur le panneau : la pastille violette en haut a gauche, le nombre en blanc
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False, "panneau_cycle": False}
        t = 1_800_000_000.0
        coin = lambda img: img[0:9, 0:14]
        m.PANNEAU["discord"] = 0
        sans = m.image_du_panneau(cfg, "horloge", t)
        self.assertFalse(coin(sans).any())
        m.PANNEAU["discord"] = 3
        img = m.image_du_panneau(cfg, "horloge", t)
        self.assertGreaterEqual(int((coin(img) == m.DISCORD_VIOLET).all(axis=2).sum()), 15)
        self.assertGreaterEqual(int((coin(img) == (255, 255, 255)).all(axis=2).sum()), 5, "le 3")
        self.assertTrue((img[9:] == sans[9:]).all(), "le reste ne bouge pas")
        m.PANNEAU["discord"] = 12
        large = m.image_du_panneau(cfg, "horloge", t)
        self.assertGreater(int((large[0:9] == m.DISCORD_VIOLET).all(axis=2).sum()),
                           int((img[0:9] == m.DISCORD_VIOLET).all(axis=2).sum()), "« 9+ » : plus large")
        self.assertIn("+", m._PETITE_3X5, "le « + » s'ecrit")
        self.assertFalse(coin(m.image_du_panneau(dict(cfg, panneau_discord=False), "horloge", t)).any())
        self.assertTrue(m.CONFIG_DEFAUT["panneau_discord"])

    def test_les_notifications_discord_par_windows(self):
        # « le panneau n'affiche pas les notifs Discord » : l'appli ne met pas toujours le compte dans
        # son titre -- les notifications de Discord du centre de Windows, arrivees depuis qu'on l'a vu
        import sqlite3
        import tempfile
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("discord", "discord_vu", "etat")}
        vraie_fenetre = m.fenetre_active
        self.addCleanup(lambda: (m.PANNEAU.update(sauve), setattr(m, "fenetre_active", vraie_fenetre)))
        self.addCleanup(lambda: m._DISCORD_CENTRE.update(signature=None, lu=0.0, arrivees=None, dit=None))
        lis = m.notifications_discord_du_titre
        self.assertEqual(lis("• (2) Discord | #general"), 2, "non lus ET mentions")
        self.assertEqual(m.forme_du_titre("(3) Discord | #general | Mon serveur - Discord"),
                         "(3) Discord | #… | … - Discord", "le journal : la forme, pas les noms")
        # une base comme celle de Windows : Discord, une autre appli, une notification expiree
        t = 1_800_000_000.0
        ft = lambda s: int((s + 11644473600) * 10_000_000)
        dossier = tempfile.mkdtemp()
        base = os.path.join(dossier, "wpndatabase.db")
        con = sqlite3.connect(base)
        con.executescript("CREATE TABLE NotificationHandler (RecordId INTEGER PRIMARY KEY, PrimaryId TEXT);"
                          "CREATE TABLE Notification (Id INTEGER PRIMARY KEY, HandlerId INTEGER, Type TEXT,"
                          " Payload BLOB, ArrivalTime INTEGER, ExpiryTime INTEGER);")
        con.executemany("INSERT INTO NotificationHandler VALUES (?, ?)",
                        [(7, "com.squirrel.Discord.Discord"), (8, "Microsoft.WindowsStore_8wekyb3d8bbwe!App")])
        con.executemany("INSERT INTO Notification (HandlerId, Type, Payload, ArrivalTime, ExpiryTime) VALUES (?,?,?,?,?)",
                        [(7, "toast", b"<toast>secret</toast>", ft(t - 600), ft(t + 86400)),
                         (7, "toast", b"<toast>secret</toast>", ft(t - 60), ft(t + 86400)),
                         (7, "toast", b"<toast>vieux</toast>", ft(t - 4 * 86400), ft(t - 3600)),   # expiree
                         (7, "tile", b"", ft(t - 30), ft(t + 86400)),
                         (8, "toast", b"<toast>store</toast>", ft(t - 30), ft(t + 86400))])
        con.commit()
        con.close()
        avant = set(os.listdir(tempfile.gettempdir()))
        arrivees = m.toasts_discord(base, maintenant=t)
        self.assertEqual(sorted(round(a) for a in arrivees), [round(t - 600), round(t - 60)])
        self.assertEqual(set(os.listdir(tempfile.gettempdir())) - avant, set(), "la copie est jetee aussitot")
        self.assertIsNone(m.toasts_discord(os.path.join(dossier, "absente.db"), maintenant=t))
        # ce qui attend : arrive depuis la derniere fois que Discord etait devant toi
        m.PANNEAU["discord_vu"] = None
        centre = lambda: [t - 600, t - 60, t - 13 * 3600]
        self.assertEqual(m.suivre_discord(lire=lambda: 0, centre=centre, maintenant=t), 2,
                         "deux recentes ; celle d'il y a 13 h n'attend plus")
        m.PANNEAU["discord_vu"] = t - 300
        self.assertEqual(m.suivre_discord(lire=lambda: 0, centre=centre, maintenant=t), 1, "tu l'as ouvert depuis")
        self.assertEqual(m.suivre_discord(lire=lambda: 5, centre=centre, maintenant=t), 5, "le titre, s'il en dit plus")
        self.assertEqual(m.suivre_discord(lire=lambda: None, centre=centre, maintenant=t), 1, "Discord ferme")
        self.assertIsNone(m.suivre_discord(lire=lambda: None, centre=lambda: None, maintenant=t))
        # le fil des sources voit quand Discord est devant toi
        m.fenetre_active = lambda: "discord.exe | (2) discord | #general"
        m.PANNEAU.update(etat="connecte", discord_vu=None)
        m.veiller_sources_panneau({"panneau_contenu": "ambiance", "panneau_discord": False}, tours=1, maintenant=t)
        self.assertEqual(m.PANNEAU["discord_vu"], t)
        m.fenetre_active = lambda: "chrome.exe | youtube"
        m.veiller_sources_panneau({"panneau_contenu": "ambiance", "panneau_discord": False}, tours=1, maintenant=t + 9)
        self.assertEqual(m.PANNEAU["discord_vu"], t)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_pastille_de_discord_sur_la_barre_des_taches(self):
        # « tu peux link autrement Discord ? j'ai une notif en attente qui ne s'affiche pas » -- la
        # capture : la pastille rouge « 1 » sur l'icone de Discord, dans la barre des taches
        import numpy as np
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("discord", "discord_vu")}
        self.addCleanup(lambda: m.PANNEAU.update(sauve))
        self.addCleanup(lambda: m._DISCORD_CENTRE.update(signature=None, lu=0.0, arrivees=None, dit=None, barre=None))
        # l'icone de Discord : violette, et la pastille rouge en bas a droite (comme la capture)
        icone = np.zeros((48, 44, 3), np.uint8)
        icone[10:38, 8:36] = (88, 101, 242)
        avec = icone.copy()
        yy, xx = np.mgrid[0:48, 0:44]
        avec[(yy - 31) ** 2 + (xx - 31) ** 2 <= 49] = (242, 63, 66)
        avec[28:35, 30:32] = (255, 255, 255)                   # le « 1 »
        self.assertEqual(m.rouge_de_pastille(icone), 0, "le violet de l'icone n'est pas la pastille")
        self.assertGreater(m.rouge_de_pastille(avec), m.DISCORD_ROUGE_MIN)
        rect = (100, 1000, 144, 1048)
        barre = m.pastille_discord_barre
        # la description de la pastille (le texte que lit le Narrateur) dit le nombre
        self.assertEqual(barre(boutons=[("1 unread message", rect)], capture=lambda r: icone), 1)
        self.assertEqual(barre(boutons=[("12 notifications", rect)], capture=lambda r: icone), 12)
        # sans nombre lisible : la pastille se voit
        self.assertEqual(barre(boutons=[("", rect)], capture=lambda r: avec), -1)
        self.assertEqual(barre(boutons=[("", rect)], capture=lambda r: icone), 0)
        self.assertEqual(barre(boutons=[("", rect)], capture=lambda r: None), 0, "la barre ne se voit pas")
        self.assertEqual(barre(boutons=[], capture=lambda r: avec), 0, "Discord n'est pas sur la barre")
        self.assertIsNone(barre(boutons=None) if m.os.name != "nt" else None, "hors de Windows")
        # la requete a UI Automation : les boutons de chaque barre, nom, aide et place en cache
        import types
        demandes = []

        class Rect:
            left, top, right, bottom = rect

        class Element:
            def __init__(self, nom, aide):
                self.CachedName, self.CachedHelpText, self.CachedBoundingRectangle = nom, aide, Rect()

        class Tableau:
            def __init__(self, elements):
                self.elements, self.Length = elements, len(elements)

            def GetElement(self, i):
                return self.elements[i]

        class Barre:
            def __init__(self, h):
                self.h = h

            def FindAllBuildCache(self, portee, condition, cache):
                demandes.append((self.h, portee, condition))
                return Tableau([Element("Demarrer", ""), Element("Discord - 1 running window", "1 unread"),
                                Element("Spotify - 1 running window", "")] if self.h == 1 else
                               [Element("discord", "")])

        class Auto:
            def CreateCacheRequest(self):
                return types.SimpleNamespace(AddProperty=lambda p: demandes_cache.append(p))

            def CreatePropertyCondition(self, propriete, valeur):
                return ("condition", propriete, valeur)

            def ElementFromHandle(self, h):
                return Barre(h)
        demandes_cache = []
        trouves = m.boutons_discord_barre(uia=(Auto(), types.SimpleNamespace(TreeScope_Descendants=4)), barres=[1, 2])
        self.assertEqual(trouves, [("1 unread", rect), ("", rect)], "la barre principale et la secondaire")
        self.assertEqual(sorted(demandes_cache), [30001, 30005, 30013], "nom, aide, place : une requete")
        self.assertEqual([d[:3] for d in demandes], [(1, 4, ("condition", 30003, 50000)),
                                                     (2, 4, ("condition", 30003, 50000))], "les boutons seulement")

        def casse():
            raise OSError("UIA indisponible")
        vrai = m.boutons_discord_barre
        self.addCleanup(lambda: setattr(m, "boutons_discord_barre", vrai))
        m.boutons_discord_barre = casse
        self.assertIsNone(barre(), "une barre illisible ne casse rien")
        # avec les autres sources : un nombre l'emporte, sinon « il y a quelque chose »
        t = 1_800_000_000.0
        rien = lambda: None
        self.assertEqual(m.suivre_discord(lire=lambda: 0, centre=lambda: [], barre=lambda: -1, maintenant=t), -1)
        self.assertEqual(m.suivre_discord(lire=lambda: 3, centre=rien, barre=lambda: -1, maintenant=t), 3)
        self.assertEqual(m.suivre_discord(lire=rien, centre=rien, barre=lambda: 2, maintenant=t), 2)
        self.assertEqual(m.suivre_discord(lire=lambda: 0, centre=rien, barre=lambda: 0, maintenant=t), 0)
        # sur le panneau : la pastille violette, un point blanc au lieu du nombre
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False, "panneau_cycle": False,
               "panneau_claude": False}
        m.PANNEAU["discord"] = -1
        img = m.image_du_panneau(cfg, "horloge", t)
        coin = img[0:9, 0:14]
        self.assertGreaterEqual(int((coin == m.DISCORD_VIOLET).all(axis=2).sum()), 20)
        self.assertEqual(int((coin == (255, 255, 255)).all(axis=2).sum()), 6, "un point, pas un chiffre")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_les_journees_a_noter(self):
        # « rajoute une interface sur le panneau quand des notes ne sont pas encore posees sur des journees »
        m = self.m
        sauve_pont = m.PONT.get("a_noter")
        sauve = {k: m.PANNEAU.get(k) for k in ("cycle",)}
        self.addCleanup(lambda: (m.PONT.__setitem__("a_noter", sauve_pont), m.PANNEAU.update(sauve)))
        midi = time.mktime(time.strptime("2026-10-23 15:00:00", "%Y-%m-%d %H:%M:%S"))
        soir = midi + 6 * 3600                              # 21 h
        # ce que BrainDebugger envoie : des dates, filtrees
        r = m.recevoir_a_noter({"aujourdhui": "2026-10-23", "aujourdhui_notee": False,
                                "jours": ["2026-10-22", "2026-10-18", "pas une date", 3, "2026-10-21"]}, maintenant=midi)
        self.assertEqual(r["jours"], ["2026-10-22", "2026-10-18", "2026-10-21"])
        n = m.journees_a_noter(midi)
        self.assertFalse(n["aujourdhui_du"], "l'apres-midi, aujourd'hui n'est pas encore a noter")
        self.assertTrue(m.journees_a_noter(soir)["aujourdhui_du"], "le soir, si")
        nuit = midi + 12 * 3600 - 60                        # 2 h 59 : la journee vecue n'est pas finie
        m.recevoir_a_noter({"aujourdhui": "2026-10-23", "aujourdhui_notee": False, "jours": []}, maintenant=nuit)
        self.assertTrue(m.journees_a_noter(nuit)["aujourdhui_du"], "et la nuit, jusqu'au coucher")
        m.recevoir_a_noter({"aujourdhui": "2026-10-23", "aujourdhui_notee": False, "jours": ["2026-10-22"]},
                           maintenant=midi)
        self.assertIsNone(m.journees_a_noter(midi + m.NOTES_VIEILLES_S + 1), "un vieux releve : on ne sait plus")
        m.recevoir_a_noter({"aujourdhui": "2026-10-23", "aujourdhui_notee": True, "jours": []}, maintenant=midi)
        self.assertIsNone(m.journees_a_noter(soir), "tout est note : rien a montrer")
        m.recevoir_a_noter({"aujourdhui": "2026-10-23", "aujourdhui_notee": False, "jours": []}, maintenant=midi)
        self.assertIsNone(m.journees_a_noter(midi))
        self.assertIsNotNone(m.journees_a_noter(soir), "seulement aujourd'hui, le soir")
        # une vue du cycle, juste apres l'heure -- seulement s'il y a quelque chose a noter
        self.assertEqual(m.CYCLE_ORDRE[:2], ("heure", "notes"))
        self.assertIn("notes", m.cycle_disponible(soir, {}))
        self.assertNotIn("notes", m.cycle_disponible(midi, {}))
        self.assertNotIn("notes", m.cycle_disponible(soir, {"panneau_cycle_notes": False}), "decochee")
        self.assertTrue(m.CONFIG_DEFAUT["panneau_cycle_notes"])
        # la vue : « A NOTER », et une case ambre par journee qui attend
        m.recevoir_a_noter({"aujourdhui": "2026-10-23", "aujourdhui_notee": False,
                            "jours": ["2026-10-22", "2026-10-18"]}, maintenant=midi)
        ambre = lambda img: (img == m.NOTES_AMBRE).all(axis=2)
        cases = lambda img: sum(1 for i in range(8) if img[47:53, 4 + 7 * i:10 + 7 * i].any(axis=2).sum() >= 18
                                and not img[48:52, 5 + 7 * i:9 + 7 * i].any())
        vue = m._zone_du_cycle("notes", soir, (120, 200, 255), [], [], 5.0)
        self.assertGreater(int(ambre(vue[39:46]).sum()), 15, "« A NOTER »")
        self.assertEqual(cases(vue), 3, "le 18, le 22, et ce soir le 23")
        self.assertEqual(cases(m._zone_du_cycle("notes", midi, (120, 200, 255), [], [], 5.0)), 2, "l'apres-midi")
        self.assertFalse(vue[:39].any() or vue[59:].any(), "rien hors de sa zone")
        # elles arrivent l'une apres l'autre
        debut = m._zone_du_cycle("notes", soir, (120, 200, 255), [], [], 0.0)
        self.assertLess(int(debut[47:59].any(axis=2).sum()), int(vue[47:59].any(axis=2).sum()))
        # sur le panneau, quand le cycle en est la
        img = m.image_panneau("horloge", soir, cycle={"actuel": "notes", "precedent": None, "fondu": 1.0,
                                                       "ecoule": 5.0})
        self.assertTrue((img[m.ZONE_CYCLE] == vue[m.ZONE_CYCLE]).all())

    def test_le_releve_du_site_apporte_les_journees_a_noter(self):
        import io
        m = self.m
        sauve = {k: m.PONT.get(k) for k in ("a_noter", "etat", "message", "vu_le")}
        vrais = (m.urllib.request.urlopen, m.synchroniser_activite)
        self.addCleanup(lambda: (m.PONT.update(sauve), setattr(m.urllib.request, "urlopen", vrais[0]),
                                 setattr(m, "synchroniser_activite", vrais[1])))
        m.synchroniser_activite = lambda cfg, minimum=0: None
        reponse = {"rappels": [], "jours": [], "reperes": [],
                   "a_noter": {"aujourdhui": "2026-10-23", "aujourdhui_notee": False, "jours": ["2026-10-21"]}}

        class Reponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        m.urllib.request.urlopen = lambda requete, timeout=None, context=None: Reponse(json.dumps(reponse).encode())
        self.assertTrue(m.relever_le_site({"pont_site": "https://exemple.test", "pont_cle": "cle"}))
        self.assertEqual(m.PONT["a_noter"]["jours"], ["2026-10-21"])
        self.assertEqual(m.PONT["a_noter"]["aujourdhui"], "2026-10-23")
        # un BrainDebugger d'avant ne l'envoie pas : rien ne casse, rien ne s'invente
        m.PONT["a_noter"] = None
        del reponse["a_noter"]
        self.assertTrue(m.relever_le_site({"pont_site": "https://exemple.test", "pont_cle": "cle"}))
        self.assertIsNone(m.PONT["a_noter"])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_vue_fl_studio(self):
        # « tu peux detecter quand je vais sur FL Studio et me faire une interface dediee ? »
        import numpy as np
        m = self.m
        cles = ("fl", "fl_cretes", "fl_pics", "etat", "discord")
        sauve = {k: m.PANNEAU.get(k) for k in cles}
        sauve_audio = {k: m.AUDIO.get(k) for k in ("actif", "brut", "spectre20", "gauche", "droite", "onde")}
        sauve_son = m.SON.get("panneau")
        vrais = {n: getattr(m, n) for n in ("fenetre_active", "demarrer_audio", "arreter_audio", "lire_discord")}
        def remettre():
            for n, f in vrais.items():
                setattr(m, n, f)
            for k in cles:
                m.PANNEAU.pop(k, None)
            m.PANNEAU.update({k: v for k, v in sauve.items() if v is not None})
            m.AUDIO.update(sauve_audio)
            m.SON["panneau"] = sauve_son
        self.addCleanup(remettre)
        # qui est FL Studio : le processus d'abord, le titre s'il est inconnu
        est = m.est_fl_studio
        self.assertTrue(est("fl64.exe | nuit blanche.flp - fl studio 21"))
        self.assertTrue(est("fl64 (scaled).exe | untitled - fl studio 2024"))
        self.assertTrue(est(" | ma prod - fl studio 21"), "processus illisible : le titre suffit")
        self.assertFalse(est("chrome.exe | fl studio 21 tutorial - youtube"), "un tuto n'est pas FL Studio")
        self.assertFalse(est("chrome.exe | ma prod - fl studio 21"))
        self.assertFalse(est(""))
        self.assertFalse(est("explorer.exe | musique"))
        # le projet, d'apres le titre
        projet = m.projet_fl
        self.assertEqual(projet("fl64.exe | nuit blanche v3.flp - fl studio 21"), "nuit blanche v3")
        self.assertEqual(projet("fl64.exe | *nuit blanche.flp - fl studio 21"), "nuit blanche", "modifie, pas enregistre")
        self.assertEqual(projet("fl64.exe | untitled - fl studio 21"), "")
        self.assertEqual(projet("fl64.exe | fl studio 21"), "")
        self.assertEqual(projet("fl64.exe | beat - remix.flp - fl studio 2024"), "beat")
        # la seance : un coup d'oeil ailleurs ne la coupe pas, une demi-heure ailleurs la remet a 0
        m.PANNEAU["fl"] = None
        titre = "fl64.exe | nuit blanche.flp - fl studio 21"
        self.assertTrue(m.suivre_fl_studio(1000.0, titre))
        self.assertTrue(m.suivre_fl_studio(1600.0, titre))
        self.assertEqual(m.PANNEAU["fl"]["depuis"], 1000.0)
        self.assertFalse(m.suivre_fl_studio(1603.0, "chrome.exe | youtube"))
        self.assertIsNotNone(m.fl_au_premier_plan(1603.0 + m.FL_GRACE_S - 4), "huit secondes de grace")
        self.assertIsNone(m.fl_au_premier_plan(1600.0 + m.FL_GRACE_S + 1))
        m.suivre_fl_studio(1700.0, titre)
        self.assertEqual(m.PANNEAU["fl"]["depuis"], 1000.0, "revenu vite : la meme seance")
        m.suivre_fl_studio(1700.0 + m.FL_SEANCE_S + 1, titre)
        self.assertEqual(m.PANNEAU["fl"]["depuis"], 1700.0 + m.FL_SEANCE_S + 1, "une demi-heure ailleurs : on repart")
        # les mesures : un son de synthese (une basse, une voix, des aigus), la droite plus faible
        x = np.arange(2048) / 48000.0
        g = 0.6 * np.sin(2 * np.pi * 80 * x) + 0.25 * np.sin(2 * np.pi * 660 * x) + 0.08 * np.sin(2 * np.pi * 5000 * x)
        bloc = np.stack([g, 0.5 * g], axis=1)
        spectre = np.abs(np.fft.rfft(bloc.mean(axis=1) * np.hanning(2048)))
        freqs = np.fft.rfftfreq(2048, 1 / 48000.0)
        memo = {}
        m.AUDIO.update(gauche=0.0, droite=0.0)
        for _ in range(12):
            m.mesures_studio(bloc, spectre, freqs, memo)
        s20 = m.AUDIO["spectre20"]
        self.assertEqual(len(s20), 20)
        bande = lambda f: int(np.searchsorted(memo["bornes"], f)) - 1
        for f in (80, 660, 5000):
            self.assertGreater(s20[bande(f)], 0.6, "%d Hz se voit" % f)
        self.assertLess(s20[bande(2000)], 0.3, "un seul gain pour toutes : un trou reste un trou")
        self.assertGreater(m.AUDIO["gauche"], 0.9)
        self.assertAlmostEqual(m.AUDIO["droite"], m.AUDIO["gauche"] * 0.5, delta=0.08)
        onde = m.AUDIO["onde"]
        self.assertEqual(len(onde), 64)
        self.assertLessEqual(max(abs(o) for o in onde), 1.0)
        self.assertLess(abs(onde[0]), 0.2, "calee sur un passage par zero")
        self.assertGreater(onde[1], onde[0], "en montant")
        m.mesures_studio(np.zeros(2048), np.zeros_like(spectre), freqs, {})
        self.assertEqual(m.AUDIO["onde"], [0.0] * 64, "le silence : une ligne plate, sans division par zero")
        # la vue : le projet en orange, le spectre, l'oscilloscope, les VU, le temps
        m.mesures_studio(bloc, spectre, freqs, memo)
        m.AUDIO.update(actif=True, brut=1.0)
        m.PANNEAU.update(fl={"depuis": 1_800_000_000.0 - 25 * 60, "vu": 1_800_000_000.0, "projet": "nuit"},
                         discord=None)
        m.PANNEAU.pop("fl_cretes", None)
        m.PANNEAU.pop("fl_pics", None)
        t = 1_800_000_000.0
        img = m.image_fl_studio(t, m.PANNEAU["fl"])
        self.assertEqual(img.shape, (64, 64, 3))
        self.assertGreater(int((img[0:8] == m.FL_ORANGE).all(axis=2).sum()), 20, "le nom du projet")
        verts = (img[9:31] == (60, 220, 90)).all(axis=2).sum()
        self.assertGreater(int(verts), 40, "le spectre")
        self.assertGreater(int((img[32:47] == m.FL_ORANGE).all(axis=2).sum()), 30, "l'oscilloscope")
        g_vu = int((img[48] != m.FL_GRIS).any(axis=1)[2:62].sum())
        d_vu = int((img[51] != m.FL_GRIS).any(axis=1)[2:62].sum())
        self.assertGreater(g_vu, d_vu, "la gauche plus forte que la droite")
        self.assertGreaterEqual(int((img[57:62, 2:5] == (60, 220, 90)).all(axis=2).sum()), 6, "▶ : ca joue")
        self.assertGreater(int((img[57:62, 8:30] == m.FL_ORANGE).all(axis=2).sum()), 15, "0H25")
        m.AUDIO.update(brut=0.0)
        pause = m.image_fl_studio(t, m.PANNEAU["fl"])
        self.assertFalse((pause[57:62, 2:5] == (60, 220, 90)).all(axis=2).any(), "‖ : rien ne sort")
        self.assertFalse((pause[32:47] == m.FL_ORANGE).all(axis=2).any(), "l'oscilloscope au repos")
        sombre = m.image_fl_studio(t, m.PANNEAU["fl"], eclat=0.3)
        self.assertLess(int(sombre.sum()), int(pause.sum()), "elle suit l'eclat de la guirlande")
        # sur le panneau : devant l'horloge, sous les pastilles ; decochee, l'horloge revient
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False, "panneau_cycle": False,
               "panneau_claude": False}
        m.AUDIO.update(brut=1.0)
        studio = m.image_du_panneau(cfg, "horloge", t)
        self.assertGreater(int((studio[0:8] == m.FL_ORANGE).all(axis=2).sum()), 20)
        horloge = m.image_du_panneau(dict(cfg, panneau_fl=False), "horloge", t)
        self.assertFalse((horloge[0:8] == m.FL_ORANGE).all(axis=2).sum() > 20)
        m.PANNEAU["discord"] = 2
        avec = m.image_du_panneau(cfg, "horloge", t)
        self.assertTrue((avec[0:9, 0:14] == m.DISCORD_VIOLET).all(axis=2).any(), "la pastille Discord par-dessus")
        m.PANNEAU["discord"] = None
        self.assertFalse(m.image_du_panneau(cfg, "eteint", t).any(), "eteint reste eteint")
        m.PANNEAU["fl"]["vu"] = t - m.FL_GRACE_S - 1
        self.assertFalse((m.image_du_panneau(cfg, "horloge", t)[0:8] == m.FL_ORANGE).all(axis=2).sum() > 20,
                         "FL quitte : l'horloge revient")
        # le fil des sources : il regarde la fenetre, et ecoute le son tant que FL est devant
        lancees = []
        m.demarrer_audio = lambda cfg: lancees.append("demarre")
        m.arreter_audio = lambda: lancees.append("arrete")
        m.lire_discord = lambda titres=None: None
        m.fenetre_active = lambda: titre
        m.PANNEAU.update(etat="connecte", fl=None)
        m.SON["panneau"] = False
        m.veiller_sources_panneau({"panneau_contenu": "ambiance"}, tours=1, maintenant=5000.0)
        self.assertIsNotNone(m.fl_au_premier_plan(5000.0))
        self.assertEqual(lancees, ["demarre"], "hors horloge, FL devant : le son s'ecoute quand meme")
        m.fenetre_active = lambda: "chrome.exe | youtube"
        m.veiller_sources_panneau({"panneau_contenu": "ambiance"}, tours=1, maintenant=5004.0)
        self.assertEqual(lancees, ["demarre"], "un coup d'oeil ailleurs : on ecoute toujours")
        m.veiller_sources_panneau({"panneau_contenu": "ambiance"}, tours=1, maintenant=5020.0)
        self.assertEqual(lancees, ["demarre", "arrete"], "FL parti : la capture s'arrete")
        m.PANNEAU["fl"] = None
        m.fenetre_active = lambda: titre
        m.veiller_sources_panneau({"panneau_contenu": "ambiance", "panneau_fl": False}, tours=1, maintenant=6000.0)
        self.assertIsNone(m.PANNEAU["fl"], "decochee : il ne regarde rien")
        m.veiller_sources_panneau({"panneau_contenu": "eteint"}, tours=1, maintenant=6001.0)
        self.assertIsNone(m.PANNEAU["fl"], "panneau eteint : rien a montrer")
        m.PANNEAU["etat"] = "absent"
        m.veiller_sources_panneau({"panneau_contenu": "ambiance"}, tours=1, maintenant=6002.0)
        self.assertIsNone(m.PANNEAU["fl"], "pas de panneau : rien a regarder")
        self.assertTrue(m.CONFIG_DEFAUT["panneau_fl"])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_les_mises_a_jour_sur_le_panneau(self):
        # « rajoute un effet sur le panneau lorsqu'une maj est en cours sur Machi Tool »
        m = self.m
        sauve_maj = dict(m.MAJ)
        sauve = {k: m.PANNEAU.get(k) for k in ("etat", "bienvenue", "fini")}
        self.addCleanup(lambda: (m.MAJ.clear(), m.MAJ.update(sauve_maj), m.PANNEAU.update(sauve)))
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_rdv": False, "panneau_cycle": False}
        t = 1_800_000_000.0
        m.PANNEAU.update(bienvenue=None, etat="connecte")
        m.MAJ.update(etat="a_jour", pose_lancee=None)
        normale = m.image_du_panneau(cfg, "horloge", t)
        # le telechargement : une barre en bas, a la mesure de ce qui est arrive, et « MAJ » en haut
        def barre(p):
            m.MAJ.update(etat="telechargement", progression=p)
            img = m.image_du_panneau(cfg, "horloge", t)
            return img, int((img[62:64] != (30, 34, 48)).any(axis=2).any(axis=0)[2:62].sum())
        a, quart = barre(0.25)
        _, trois_quarts = barre(0.75)
        self.assertTrue(10 <= quart < trois_quarts <= 50, (quart, trois_quarts))
        self.assertTrue(a[0:8].any() and not normale[0:8].any(), "« MAJ » en haut")
        self.assertTrue((a[9:60] == normale[9:60]).all(), "l'heure reste lisible")
        # la pose : l'anneau tourne autour de « MAJ » et de la version, plein ecran
        m.MAJ.update(etat="a_poser", version="9.9.9", pose_lancee=t)
        poses = [m.image_du_panneau(cfg, "horloge", t + k / 4.0) for k in range(4)]
        self.assertEqual(len({p.tobytes() for p in poses}), 4, "l'anneau tourne")
        self.assertTrue(poses[0][22:29].any() and not (poses[0] == normale).all())
        self.assertTrue(((poses[0] == m.MAJ_TEINTE).all(axis=2)).any())
        # la pose attend deux secondes que l'anneau se voie (panneau branche), puis part ;
        # en partant, le panneau garde l'anneau au lieu de noircir
        vrais = (m.lancer_installeur_maj, m.eteindre_panneau)
        self.addCleanup(lambda: (setattr(m, "lancer_installeur_maj", vrais[0]),
                                 setattr(m, "eteindre_panneau", vrais[1])))
        lances, noircis = [], []
        m.lancer_installeur_maj = lambda: lances.append(1) or True
        m.eteindre_panneau = lambda: noircis.append(1) or True
        m.MAJ.update(pose_lancee=None)
        self.assertFalse(m.tenter_la_pose(False, maintenant=t))
        self.assertEqual(m.MAJ["pose_lancee"], t)
        self.assertFalse(m.tenter_la_pose(False, maintenant=t + 1.0))
        self.assertTrue(m.tenter_la_pose(False, maintenant=t + m.MAJ_EFFET_S + 0.1))
        self.assertEqual(lances, [1])
        self.assertFalse(m.eteindre_en_partant())
        self.assertEqual(noircis, [], "l'anneau reste")
        m.MAJ.update(etat="a_jour", pose_lancee=None)
        m.eteindre_en_partant()
        self.assertEqual(noircis, [1], "un depart ordinaire : noir, comme avant")
        # la nouvelle version : une coche, son numero ; seulement panneau branche ; puis l'heure en fondu
        m.PANNEAU.update(etat="absent", bienvenue={"de": "9.9.8", "vers": "9.9.9", "debut": None})
        self.assertIsNone(m.image_maj_du_moment(t), "personne ne la verrait : elle attend")
        m.PANNEAU["etat"] = "connecte"
        debut = m.image_du_panneau(cfg, "horloge", t)
        milieu = m.image_du_panneau(cfg, "horloge", t + 1.5)
        self.assertTrue(((milieu == (60, 220, 90)).all(axis=2)).sum() >= 20, "la coche")
        self.assertFalse((debut == milieu).all())
        fin = m.image_du_panneau(cfg, "horloge", t + m.MAJ_BIENVENUE_S - 0.1)
        self.assertGreater(int(np.abs(fin.astype(int) - normale.astype(int)).sum()), 0)
        apres = m.image_du_panneau(cfg, "horloge", t + m.MAJ_BIENVENUE_S + 0.1)
        self.assertTrue((apres[:60] == normale[:60]).all(), "puis l'heure, comme avant (les secondes ont avance)")
        self.assertIsNone(m.PANNEAU["bienvenue"])
        # decochee : rien de tout ca
        m.MAJ.update(etat="telechargement", progression=0.5)
        self.assertTrue((m.image_du_panneau(dict(cfg, panneau_maj=False), "horloge", t) == normale).all())
        self.assertTrue(m.CONFIG_DEFAUT["panneau_maj"])

    def test_les_sources_du_cycle(self):
        m = self.m
        sauve = {k: m.PANNEAU.get(k) for k in ("meteo", "musique_vue", "morceau", "morceau_cle", "musique_saut",
                                               "etat", "meteo_a_relire", "present", "debout_depuis")}
        vrais = {k: getattr(m, k) for k in ("demarrer_audio", "sauver_config", "morceau_en_cours", "_lire_url_json",
                                            "secondes_inactivite")}
        son = dict(m.SON)
        self.addCleanup(lambda: (m.PANNEAU.update(sauve), m.SON.update(son),
                                 [setattr(m, k, v) for k, v in vrais.items()]))
        m.sauver_config = lambda cfg: True
        demandes = []

        def lire(url):
            demandes.append(url.split("?")[0])
            if "geocoding" in url:
                return {"results": [{"name": "Lyon", "latitude": 45.76, "longitude": 4.84}]}
            if "ipapi" in url:
                return {"city": "Paris", "latitude": 48.85, "longitude": 2.35}
            return {"current": {"temperature_2m": 11.6, "weather_code": 3, "is_day": 1},
                    "daily": {"temperature_2m_min": [7.9], "temperature_2m_max": [14.2]}}
        cfg = {"meteo_ville": "Lyon"}
        m.rafraichir_meteo(cfg, lire, maintenant=100.0)
        self.assertEqual(m.PANNEAU["meteo"]["temp"], 11.6)
        self.assertEqual((m.PANNEAU["meteo"]["lieu"], m.PANNEAU["meteo"]["min"]), ("Lyon", 7.9))
        demandes.clear()
        m.rafraichir_meteo(cfg, lire)
        self.assertEqual(demandes, ["https://api.open-meteo.com/v1/forecast"], "la ville situee est gardee")
        cfg["meteo_ville"] = ""
        m.rafraichir_meteo(cfg, lire)
        self.assertEqual(cfg["meteo_lieu"]["nom"], "Paris", "vide : d'apres la connexion")
        self.assertEqual(m._jv.meteo_lisible(0, False), ("lune", "NUIT CLAIRE"))
        self.assertEqual(m._jv.meteo_lisible(95, True, "en"), ("orage", "STORM"))
        # un morceau qui change : le cycle y sautera ; le meme : non
        m.PANNEAU.update(morceau_cle=None, musique_saut=None)
        m.suivre_musique({}, 10.0, {"titre": "Midnight City", "artistes": "M83"})
        self.assertEqual((m.PANNEAU["musique_vue"], m.PANNEAU["musique_saut"]), (10.0, 10.0))
        m.PANNEAU["musique_saut"] = None
        m.suivre_musique({}, 15.0, {"titre": "Midnight City", "artistes": "M83"})
        self.assertIsNone(m.PANNEAU["musique_saut"])
        # le fil : panneau branche, il ecoute le son ; le mode de la guirlande ne la coupe pas
        lances = []
        m.demarrer_audio = lambda cfg: lances.append(1)
        m.morceau_en_cours = lambda cfg: None
        m._lire_url_json = lire
        m.SON.update(panneau=False, marche=True)
        m.PANNEAU.update(etat="connecte", debout_depuis=None)
        m.secondes_inactivite = lambda: 42.0
        m.veiller_sources_panneau({"panneau_contenu": "horloge", "meteo_ville": "Lyon"}, tours=1, maintenant=200.0)
        self.assertTrue(m.SON["panneau"])
        self.assertEqual((m.PANNEAU["present"], m.PANNEAU["debout_depuis"]), (True, 158.0), "la maid sait si tu es la")
        self.assertEqual(lances, [1])
        m.arreter_audio()
        self.assertTrue(m.SON["marche"], "la guirlande quitte le mode son : l'egaliseur garde la capture")
        m.PANNEAU["etat"] = "absent"
        m.veiller_sources_panneau({"panneau_contenu": "horloge", "mode": "ecran"}, tours=1, maintenant=300.0)
        self.assertFalse(m.SON["panneau"] or m.SON["marche"], "plus de panneau : la capture s'arrete")

    def test_le_resume_se_dit_bien(self):
        J = self.m._jv
        r = [{"label": "Dentiste", "heure": "10:15"}, {"label": "Anniversaire de Paul"}]
        self.assertEqual(J.resume_journee(r, 9 * 60, "fr"),
                         "Bonjour. Au programme aujourd'hui : Dentiste à 10 h 15 ; et toute la journée : "
                         "Anniversaire de Paul.")
        self.assertEqual(J.resume_journee(r, 19 * 60, "fr", "Madame")[:16], "Bonsoir, Madame.")
        self.assertEqual(J.resume_journee([r[1]], 9 * 60, "fr"), "Bonjour. Aujourd'hui : Anniversaire de Paul.")
        self.assertEqual(J.resume_journee(r, 9 * 60, "en"),
                         "Good morning. On today's schedule: Dentiste at 10:15; and all day: Anniversaire de Paul.")
        beaucoup = [{"label": "R%d" % k, "heure": "%02d:00" % (10 + k)} for k in range(7)]
        self.assertTrue(J.resume_journee(beaucoup, 0, "fr").endswith("R4 à 14 h, et 2 autres."))
        self.assertIsNone(J.resume_journee([], 0, "fr"))
        self.assertEqual(J.restants_du_jour([{"heure": "08:00"}, {"heure": "12:00"}, {}], 9 * 60),
                         [{"heure": "12:00"}, {}])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_prochain_rendez_vous_au_dessus_des_secondes(self):
        # « lorsqu'un evenement arrive, le montrer a partir d'une heure avant sur le panneau
        # (au-dessus de la ligne des secondes) »
        m = self.m
        jour = [{"date": "2026-10-22", "heure": "08:30", "label": "Footing"},
                {"date": "2026-10-22", "heure": "14:30", "label": "Reunion projet LED Wall"},
                {"date": "2026-10-22", "label": "Anniversaire"}]

        def a(h, mn, sec=0):
            return time.mktime((2026, 10, 22, h, mn, sec, 0, 0, -1))
        self.assertIsNone(m.prochain_rdv(jour, a(13, 29)), "1 h 01 avant : pas encore")
        r, avant, couleur = m.prochain_rdv(jour, a(13, 30))
        self.assertEqual((r["label"], avant), ("Reunion projet LED Wall", 3600))
        self.assertEqual(m.prochain_rdv(jour, a(14, 34))[0]["label"], "Reunion projet LED Wall", "encore 5 min apres")
        self.assertIsNone(m.prochain_rdv(jour, a(14, 36)))
        self.assertEqual(m.prochain_rdv(jour, a(8, 0))[0]["label"], "Footing")
        self.assertEqual(couleur, m.COULEURS_RDV[1], "la 2e de la journee : sa couleur, partout la meme")
        # dessine au-dessus des secondes (ligne 52 a 56), rien au-dessus sans rendez-vous proche
        avec = m.image_panneau("horloge", a(14, 0), accent=(255, 160, 0), rdv=jour)
        sans = m.image_panneau("horloge", a(12, 0), accent=(255, 160, 0), rdv=jour)
        self.assertTrue((avec[52:57] == couleur).all(axis=2).any(), "son heure, dans sa couleur")
        self.assertTrue((avec[52:57] == m.TITRE_RDV).all(axis=2).any(), "son titre")
        self.assertFalse((sans[50:58] != 0).any())
        # un titre long defile : il part de son debut, et s'y arrete 1,5 s
        img0, img1 = np.zeros((64, 64, 3), np.uint8), np.zeros((64, 64, 3), np.uint8)
        m.ecrire_tenant(img0, "REUNION PROJET LED WALL", 26, 62, 0, (255, 255, 255), 0.0)
        m.ecrire_tenant(img1, "REUNION PROJET LED WALL", 26, 62, 0, (255, 255, 255), 1.4)
        coupe = np.zeros((64, 64, 3), np.uint8)
        m.ecrire_tenant(coupe, "REUNION PROJET LED WALL", 26, 62, 0, (255, 255, 255))
        self.assertTrue((img0 == coupe).all() and (img1 == coupe).all())
        img2 = np.zeros((64, 64, 3), np.uint8)
        m.ecrire_tenant(img2, "REUNION PROJET LED WALL", 26, 62, 0, (255, 255, 255), 3.0)
        self.assertFalse((img2 == coupe).all(), "puis il defile")
        # le programme : la date, la frise, une ligne par rendez-vous ; « +N » au-dela de 7
        prog = m.image_programme(jour, a(9, 0))
        self.assertTrue((prog[1:6] == (150, 150, 165)).all(axis=2).any())
        self.assertTrue((prog[8:13] == m.COULEURS_RDV[1]).all(axis=2).any(), "la reunion sur la frise")
        self.assertTrue((prog[7:14] == (240, 240, 248)).all(axis=2).any(), "maintenant")
        dix = [{"heure": "%02d:00" % (8 + k), "label": "R%d" % k} for k in range(10)]
        prog = m.image_programme(dix, a(7, 0))
        self.assertTrue((prog[58:63] != 0).any())
        # a l'horloge, case decochee : rien
        m.PANNEAU["agenda"] = {"jour": time.strftime("%Y-%m-%d", time.localtime(a(14, 0))), "lu": a(14, 0),
                               "rdv": jour}
        self.addCleanup(lambda: m.PANNEAU.update(agenda=None))
        cfg = {"panneau_contenu": "horloge", "panneau_suit_eclat": False, "panneau_cycle": False}
        self.assertTrue((m.image_du_panneau(cfg, "horloge", a(14, 0))[52:57] != 0).any())
        self.assertFalse((m.image_du_panneau(dict(cfg, panneau_rdv=False), "horloge", a(14, 0))[50:58] != 0).any())

    def test_jarvis_pose_minuteurs_alarmes_et_chronos_sans_permission(self):
        # « verifie bien que Jarvis puisse declencher un minuteur de lui-meme : qu'il
        # ait les droits, pareil pour les alarmes et les chronometres »
        m = self.m
        avant = list(m.JARVIS["minuteurs"])
        self.addCleanup(lambda: (m.annuler_chronos(None, None, "fr"), m.JARVIS["minuteurs"].extend(avant)))
        m.JARVIS["minuteurs"][:] = []
        entrees = [{"action": "minuteur", "secondes": 600, "nom": "pates"},
                   {"action": "alarme", "heure": "07:30", "nom": "reveil"},
                   {"action": "chrono_lancer", "nom": "course"},
                   {"action": "lister"},
                   {"action": "chrono_arreter", "nom": "course"},
                   {"action": "annuler", "tout": True}]
        # sans ses mains sur le PC, et avec le code d'acces actif et ferme : direct, sans question
        for cfg in (dict(m.CONFIG_DEFAUT, jarvis_pc=False),
                    dict(m.CONFIG_DEFAUT, jarvis_pc=True, jarvis_code_actif=True)):
            for e in entrees:
                self.assertEqual(m._palier({"nom": "minuteurs", "entree": e}, cfg), m._jv.PALIER_DIRECT, e)
        cfg = dict(m.CONFIG_DEFAUT, jarvis_pc=False)
        genres = []
        for i, e in enumerate(entrees):
            r = m.executer_outil({"id": i, "nom": "minuteurs", "entree": e}, cfg)
            self.assertNotIn("erreur", r, (e, r))
            genres.append(sorted(x["genre"] for x in m.JARVIS["minuteurs"]))
        self.assertEqual(genres[2], ["alarme", "chrono", "minuteur"], "les trois tournent en fond")
        self.assertEqual(genres[-1], [], "et s'annulent")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_panneau_led_tourne_pour_une_carte_posee_de_travers(self):
        # « add a way to rotate the display by 90° (I have installed the board at a 90° angle) »
        m = self.m
        import numpy as np
        vrais = (m.trouver_panneau, m.ouvrir_panneau, m.image_panneau)
        self.addCleanup(lambda: (setattr(m, "trouver_panneau", vrais[0]), setattr(m, "ouvrir_panneau", vrais[1]),
                                 setattr(m, "image_panneau", vrais[2])))
        ecrit = []

        class Carte:
            def write(self, octets):
                ecrit.append(bytes(octets))

            def close(self):
                pass
        m.trouver_panneau = lambda: "COM7"
        m.ouvrir_panneau = lambda p: Carte()
        img = np.zeros((64, 64, 3), np.uint8)
        img[0, 0] = (255, 0, 0)
        m.image_panneau = lambda *a, **k: img

        def ou_est_le_rouge(cfg):
            del ecrit[:]
            m.piloter_panneau(cfg, tours=1)
            mots = np.frombuffer([o for o in ecrit if o[:2] == b"MF"][-1][2:], ">u2").reshape(64, 64)
            return tuple(int(v) for v in np.argwhere(mots == 0xF800)[0])
        cfg = {"panneau_actif": True, "panneau_contenu": "horloge", "panneau_luminosite": 64,
               "panneau_rouge": 100, "panneau_vert": 100, "panneau_bleu": 100}
        self.assertEqual(ou_est_le_rouge(cfg), (0, 0), "sans rotation : tel quel")
        for degres, attendu in ((90, (0, 63)), (180, (63, 63)), (270, (63, 0))):
            cfg["panneau_rotation"] = degres
            self.assertEqual(ou_est_le_rouge(cfg), attendu, "%d° dans le sens horaire" % degres)
        self.assertIs(m.tourner_panneau(img, "n'importe quoi"), img, "une valeur abimee : pas de rotation")
        self.assertEqual(m.CONFIG_DEFAUT["panneau_rotation"], 0)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_l_heure_suit_la_luminosite_de_la_guirlande(self):
        # « peux-tu faire varier la luminosite de l'heure et de la date en fonction de la guirlande aussi ? »
        m = self.m
        avant = {k: m.ETAT.get(k) for k in ("connecte", "couleur")}
        self.addCleanup(lambda: (m.ETAT.update(avant), m.PANNEAU.update(teinte=None, mire=False, jarvis=None)))
        m.PANNEAU.update(teinte=None, mire=False, jarvis=None)
        avant_j = m.JARVIS.get("etat")
        self.addCleanup(lambda: m.JARVIS.update(etat=avant_j))
        m.JARVIS["etat"] = "attente"

        def lumiere(v):                               # ce que l'ecran montre -> la lumiere
            x = v / 255.0
            return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
        t = time.mktime((2026, 10, 22, 0, 25, 30, 0, 0, -1))
        cfg = {"panneau_contenu": "horloge"}
        chiffre = (12, 6)                             # un pixel allume du premier « 0 » (y, x)
        m.ETAT.update(connecte=True, couleur=(255, 120, 0))
        plein = m.image_du_panneau(cfg, "horloge", t)
        self.assertEqual(m.eclat_guirlande(), 1.0)
        self.assertEqual(tuple(plein[chiffre]), m.accent_panneau(), "guirlande a fond : l'heure aussi")
        # la guirlande a un quart de sa lumiere (la meme teinte) : l'heure et la date aussi
        m.ETAT["couleur"] = (64, 30, 0)
        quart = m.image_du_panneau(cfg, "horloge", t)
        self.assertAlmostEqual(m.eclat_guirlande(), 64 / 255.0)
        for i in range(3):
            self.assertAlmostEqual(lumiere(quart[chiffre][i]), lumiere(plein[chiffre][i]) * 64 / 255.0, delta=0.01)
        self.assertTrue((plein[32:37] > 0).any() and (quart[32:37] < plein[32:37]).any(), "la date aussi")
        self.assertGreater(int(quart[chiffre][0]), 0)
        self.assertEqual(sorted(range(3), key=lambda i: quart[chiffre][i]),
                         sorted(range(3), key=lambda i: plein[chiffre][i]), "la teinte ne bouge pas")
        # eteinte ou presque : le plancher, l'heure reste lisible
        m.ETAT["couleur"] = (0, 0, 0)
        nuit = m.image_du_panneau(cfg, "horloge", t)
        self.assertAlmostEqual(lumiere(nuit[chiffre][0]), lumiere(plein[chiffre][0]) * m.PANNEAU_ECLAT_MIN, delta=0.01)
        self.assertGreater(int(nuit[chiffre][0]), 40, "lisible")
        # debranchee, ou case decochee : pleine lumiere
        m.ETAT["couleur"] = (64, 30, 0)
        self.assertTrue((m.image_du_panneau(dict(cfg, panneau_suit_eclat=False), "horloge", t) == plein).all())
        m.ETAT["connecte"] = False
        self.assertEqual(m.eclat_guirlande(), 1.0)
        self.assertTrue((m.assombrir(plein, 1.0) is plein))
        self.assertTrue(m.CONFIG_DEFAUT["panneau_suit_eclat"])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_panneau_led_a_la_couleur_de_la_guirlande(self):
        # « Cheque bien que la couleur actuelle de la guirlande matche la couleur du panneau »
        m = self.m
        avant = {k: m.ETAT.get(k) for k in ("connecte", "couleur")}
        self.addCleanup(lambda: (m.ETAT.update(avant), m.PANNEAU.update(teinte=None)))
        m.PANNEAU["teinte"] = None
        # la guirlande recoit de la lumiere lineaire : l'ecran la montre par vu_a_l_oeil (le graphe)
        m.ETAT.update(connecte=True, couleur=(255, 120, 0))
        jaune = m.accent_panneau()
        self.assertEqual(jaune, m.vu_a_l_oeil((255, 120, 0)), "la couleur du graphe, pas la valeur brute")
        self.assertGreater(jaune[1], 170, "un jaune reste jaune (120 tel quel le faisait orange)")
        # tamisee (la veille, la nuit) : la meme teinte -- plus le blanc chaud sous 40
        m.ETAT["couleur"] = (34, 16, 0)
        self.assertEqual(m.accent_panneau(), jaune)
        m.ETAT["couleur"] = (6, 0, 8)
        violet = m.accent_panneau()
        self.assertEqual(violet[1], 0)
        self.assertGreater(violet[2], violet[0])
        # noire : la derniere teinte ; debranchee : le blanc chaud
        m.ETAT["couleur"] = (0, 0, 0)
        self.assertEqual(m.accent_panneau(), violet)
        m.ETAT["connecte"] = False
        self.assertEqual(m.accent_panneau(), m.PANNEAU_BLANC_CHAUD)

        # et la carte eclaire comme la guirlande : la bibliotheque HUB75 applique
        # CIE 1931 (lumConvTab) a ce qu'elle recoit -- les memes proportions de lumiere
        def lumiere(v):
            clarte = v * 100.0 / 255
            return ((clarte + 16) / 116) ** 3 if clarte > 8 else clarte / 903.3
        mot = int.from_bytes(m.rgb565(m.image_panneau("ambiance", 0, accent=jaune))[:2], "big")
        r5, v6 = mot >> 11, (mot >> 5) & 0x3F
        r8, v8 = (r5 << 3) | (r5 >> 2), (v6 << 2) | (v6 >> 4)
        self.assertAlmostEqual(lumiere(v8) / lumiere(r8), 120 / 255.0, delta=0.02)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_panneau_de_jarvis_passe_sur_le_panneau_led(self):
        # « lorsque Jarvis parle, il faut montrer l'interface du petit panneau de
        # Jarvis sur le panneau plutot que la montrer sur l'ecran »
        m = self.m
        avant = {k: m.JARVIS.get(k) for k in ("etat", "fait_jusqua", "erreur_jusqua", "sous_titre", "mode")}
        self.addCleanup(lambda: (m.JARVIS.update(avant), m.PANNEAU.update(jarvis=None, etat="absent")))
        m.JARVIS.update(etat="attente", fait_jusqua=0, erreur_jusqua=0, sous_titre=None, mode="jarvis")
        m.PANNEAU["jarvis"] = None
        cfg = {"panneau_actif": True, "panneau_contenu": "horloge", "panneau_jarvis": True}
        t = time.time()
        self.assertIsNone(m.etat_jarvis_pour_le_panneau(cfg, t), "il dort : l'horloge")
        # il t'ecoute : SON image, celle de la fenetre a l'ecran, sans la croix (on ne clique pas un mur)
        m.JARVIS["etat"] = "ecoute"
        self.assertEqual(m.etat_jarvis_pour_le_panneau(cfg, t), "ecoute")
        img = m.image_du_panneau(cfg, "horloge", t)
        attendu = m._jv.image_jarvis("ecoute", t, "", "jarvis", "", niveau=m.niveau_de_la_voix(t),
                                     langue=m.langue_jarvis(cfg), croix=False)
        self.assertTrue((img == attendu).all())
        self.assertTrue((m.image_jarvis_du_moment("ecoute", t, cfg)[2:6, 58:62] > 0).any(), "a l'ecran : la croix")
        self.assertFalse((img[2:6, 58:62] > 0).any())
        # decoche, ou panneau eteint : rien de Jarvis
        self.assertIsNone(m.etat_jarvis_pour_le_panneau(dict(cfg, panneau_jarvis=False), t))
        self.assertTrue((m.image_du_panneau(cfg, "eteint", t) == 0).all())
        # la fenetre a l'ecran s'efface seulement si le panneau le montre vraiment
        m.PANNEAU["etat"] = "absent"
        self.assertFalse(m.jarvis_sur_le_panneau_led(cfg), "pas de panneau branche : l'ecran")
        m.PANNEAU["etat"] = "connecte"
        self.assertTrue(m.jarvis_sur_le_panneau_led(cfg))
        self.assertFalse(m.jarvis_sur_le_panneau_led(dict(cfg, panneau_contenu="eteint")))
        self.assertFalse(m.jarvis_sur_le_panneau_led(dict(cfg, panneau_jarvis=False)))
        # IL PARLE DE LUI-MEME (un minuteur) : il n'est pas « actif », on montre « parle »
        m.JARVIS["etat"] = "attente"
        vrai_parle = m.VOIX.parle
        self.addCleanup(lambda: setattr(m.VOIX, "parle", vrai_parle))
        m.VOIX.parle = True
        m.montrer_au_panneau("Votre  minuteur est terminé.")
        self.assertEqual(m.PANNEAU["jarvis"]["texte"], "Votre minuteur est terminé.")
        debut = m.PANNEAU["jarvis"]["debut"]
        self.assertEqual(m.etat_jarvis_pour_le_panneau(cfg, debut + 30), "parle", "tant que sa voix sonne")
        m.VOIX.parle = False
        self.assertEqual(m.etat_jarvis_pour_le_panneau(cfg, debut + 31), "parle", "et le temps de lire la fin")
        self.assertIsNone(m.etat_jarvis_pour_le_panneau(cfg, debut + 33), "puis l'horloge revient")
        self.assertIsNone(m.PANNEAU["jarvis"])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_mire_et_la_balance_des_couleurs(self):
        # « j'utilise maintenant le panneau uniquement en USB-C, fais en sorte que les
        # couleurs matchent ce qui est affiche a l'ecran ; c'est un peu rouge »
        m = self.m
        self.addCleanup(lambda: m.PANNEAU.update(mire=False))
        cfg = {"panneau_contenu": "horloge"}
        self.assertEqual(m.balance_panneau(cfg), (0.70, 0.85, 1.0), "sur l'USB-C : moins de rouge, un peu moins de vert")
        self.assertEqual(m.balance_panneau({"panneau_rouge": 250, "panneau_vert": "abime", "panneau_bleu": -3}),
                         (1.0, 0.85, 0.0))
        # la balance agit sur la LUMIERE : 50 % de rouge, c'est la moitie de sa lumiere
        def lumiere(v):
            clarte = v * 100.0 / 255
            return ((clarte + 16) / 116) ** 3 if clarte > 8 else clarte / 903.3
        import numpy as np
        blanc = np.full((64, 64, 3), 255, np.uint8)
        mot = int.from_bytes(m.rgb565(blanc, (0.5, 1.0, 1.0))[:2], "big")
        r5, v6, b5 = mot >> 11, (mot >> 5) & 0x3F, mot & 0x1F
        self.assertAlmostEqual(lumiere((r5 << 3) | (r5 >> 2)), 0.5, delta=0.03)
        self.assertEqual((v6, b5), (63, 31))
        self.assertEqual(m.rgb565(blanc, (1, 1, 1)), m.rgb565(blanc), "a 100 % : rien ne change")
        # la mire : blanc, rouge, vert, bleu, six gris, la guirlande -- pendant un reglage
        mire = m.image_mire((10, 20, 30))
        self.assertEqual(tuple(mire[8, 30]), (255, 255, 255))
        self.assertEqual((tuple(mire[24, 10]), tuple(mire[24, 30]), tuple(mire[24, 50])),
                         ((255, 0, 0), (0, 255, 0), (0, 0, 255)))
        self.assertEqual(tuple(mire[55, 30]), (10, 20, 30))
        t = time.time()
        # « montre la mire uniquement si je clique ; un toggle, qu'on peut re-desactiver »
        m.PANNEAU["mire"] = False
        self.assertNotEqual(tuple(m.image_du_panneau(cfg, "horloge", t)[8, 30]), (255, 255, 255))

        class Faux:
            bouton_mire = None
            _texte_mire = staticmethod(m.Panneau._texte_mire)

            def _peindre_panneau(self):
                pass
        faux = Faux()
        self.assertEqual(faux._texte_mire(), "Montrer la mire")
        m.Panneau.basculer_mire(faux)
        self.assertTrue(m.PANNEAU["mire"])
        self.assertEqual(faux._texte_mire(), "Cacher la mire")
        self.assertEqual(tuple(m.image_du_panneau(cfg, "horloge", t + 3600)[8, 30]), (255, 255, 255),
                         "elle reste tant qu'on ne la cache pas")
        m.Panneau.basculer_mire(faux)
        self.assertFalse(m.PANNEAU["mire"])
        self.assertNotEqual(tuple(m.image_du_panneau(cfg, "horloge", t)[8, 30]), (255, 255, 255))
        # bouger une reglette de balance ne l'allume plus
        src = open(m.__file__, encoding="utf-8").read()
        i = src.index("    def _panneau_balance_bientot")
        self.assertNotIn('PANNEAU["mire"]', src[i:i + 600])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_panneau_led_se_branche_seul_et_envoie_un_flux(self):
        m = self.m
        vrais = (m.trouver_panneau, m.ouvrir_panneau, m.image_panneau)
        self.addCleanup(lambda: (setattr(m, "trouver_panneau", vrais[0]), setattr(m, "ouvrir_panneau", vrais[1]),
                                 setattr(m, "image_panneau", vrais[2])))
        import numpy as np

        class Carte:
            def __init__(self):
                self.ecrit, self.ferme, self.panne = [], False, False

            def write(self, octets):
                if self.panne:
                    raise OSError("debranchee")
                self.ecrit.append(bytes(octets))

            def close(self):
                self.ferme = True
        cartes, port = [], ["COM7"]
        m.trouver_panneau = lambda: port[0]
        m.ouvrir_panneau = lambda p: cartes.append(Carte()) or cartes[-1]
        image = [np.zeros((64, 64, 3), np.uint8)]
        m.image_panneau = lambda *a, **k: image[0]
        cfg = {"panneau_actif": True, "panneau_contenu": "horloge", "panneau_luminosite": 80}
        m.PANNEAU.update(etat="absent", port=None, envoyees=0)
        m.piloter_panneau(cfg, tours=3)
        self.assertEqual(m.PANNEAU["etat"], "connecte")
        self.assertEqual(m.PANNEAU["port"], "COM7")
        genres = [o[:2] for o in cartes[0].ecrit]
        # « j'ai l'impression que c'est pas a 30 fps » : chaque image part, meme identique
        self.assertEqual(genres, [b"MB", b"MF", b"MF", b"MF"], "la luminosite une fois, puis un flux")
        self.assertEqual(cartes[0].ecrit[0], b"MB" + bytes([80]))
        self.assertEqual(len(cartes[0].ecrit[1]), 2 + 8192)
        self.assertGreater(m.PANNEAU["ips"], 0, "le debit tenu, affiche sur la page")
        self.assertIn("im/s", m.etat_panneau_lisible()[0])
        # une image qui ne passe pas a temps (la carte deborde) ne coupe pas la liaison
        class SerialTimeoutException(Exception):
            pass
        lente, ouvertures = Carte(), []
        lente.write = lambda octets: (_ for _ in ()).throw(SerialTimeoutException()) if octets[:2] == b"MF" else None
        m.ouvrir_panneau = lambda p: ouvertures.append(p) or lente
        perdues = m.PANNEAU.get("perdues", 0)
        m.piloter_panneau(cfg, tours=3)
        self.assertEqual(m.PANNEAU["etat"], "connecte")
        self.assertEqual(len(ouvertures), 1, "pas de rebranchement")
        self.assertEqual(m.PANNEAU["perdues"], perdues + 3)
        m.ouvrir_panneau = lambda p: cartes.append(Carte()) or cartes[-1]
        # debranchee en cours de route : la liaison se ferme, l'etat le dit
        images = iter([np.zeros((64, 64, 3), np.uint8), np.full((64, 64, 3), 9, np.uint8)] * 4)
        m.image_panneau = lambda *a, **k: next(images)
        ecrire_vrai = Carte.write

        def ecrire(self_, octets):
            if len(self_.ecrit) >= 2:
                raise OSError("debranchee")
            ecrire_vrai(self_, octets)
        Carte.write = ecrire
        self.addCleanup(lambda: setattr(Carte, "write", ecrire_vrai))
        m.piloter_panneau(cfg, tours=3)
        self.assertTrue(cartes[-1].ferme)
        self.assertEqual(m.PANNEAU["etat"], "absent")
        Carte.write = ecrire_vrai
        # rebranchee : il la retrouve seul
        m.piloter_panneau(cfg, tours=1)
        self.assertEqual(m.PANNEAU["etat"], "connecte")
        # « Machi Tool pilote le panneau » decoche : le port est rendu (Arduino peut televerser)
        cfg["panneau_actif"] = False
        m.piloter_panneau(cfg, tours=1)
        self.assertEqual(m.PANNEAU["etat"], "coupe")
        # rien de branche
        cfg["panneau_actif"], port[0] = True, None
        m.piloter_panneau(cfg, tours=1)
        self.assertEqual(m.PANNEAU["etat"], "absent")
        self.assertIn("Je la cherche", m.etat_panneau_lisible()[0])

    def test_l_agenda_synchro_meme_hors_ligne(self):
        # « fait en sorte que l'agenda soit synchro sur brain debugger »
        m = self.m
        dossier = tempfile.mkdtemp()
        vrais = (m.FICHIER_AGENDA, m._requete_bd, m._cle_presente)
        self.addCleanup(lambda: (setattr(m, "FICHIER_AGENDA", vrais[0]), setattr(m, "_requete_bd", vrais[1]),
                                 setattr(m, "_cle_presente", vrais[2])))
        m.FICHIER_AGENDA = os.path.join(dossier, "agenda.json")
        m._cle_presente = lambda cfg: True
        base = [{"id": 1, "date": "2026-10-22", "heure": "09:00", "label": "Dentiste-témoin"},
                {"id": 2, "date": "2026-10-25", "label": "Anniversaire-témoin"}]
        envoyes, panne = [], []

        def bd(chemin, corps, cfg, delai, **k):
            if panne:
                raise OSError("injoignable")
            if corps is None:
                return {"rendezVous": [dict(r) for r in base], "bilan": None}
            envoyes.append(corps)
            return {"ok": True, "texte": "fait"}
        m._requete_bd = bd
        r, hors = m.lire_agenda_synchro(m.CFG, "2026-10-20", 14)
        self.assertIsNone(hors)
        self.assertEqual(len(r["rendezVous"]), 2)
        # BrainDebugger tombe : la copie, et ce qu'on fait attend dans la file
        panne.append(1)
        r, hors = m.lire_agenda_synchro(m.CFG, "2026-10-20", 14)
        self.assertIn("copie du", hors)
        self.assertEqual([x["label"] for x in r["rendezVous"]], ["Dentiste-témoin", "Anniversaire-témoin"])
        m.mettre_en_attente({"op": "poser", "titre": "Kiné-témoin", "date": "2026-10-23", "heure": "18:00"})
        m.mettre_en_attente({"op": "supprimer", "id": 2})
        m.mettre_en_attente({"op": "modifier", "id": 1, "titre": "Dentiste-témoin", "date": "2026-10-22",
                             "heure": "10:30", "fin": None})
        r, _ = m.lire_agenda_synchro(m.CFG, "2026-10-20", 14)
        vus = {x["label"]: x for x in r["rendezVous"]}
        self.assertEqual(sorted(vus), ["Dentiste-témoin", "Kiné-témoin"], "la copie montre deja ce qui attend")
        self.assertEqual(vus["Dentiste-témoin"]["heure"], "10:30")
        self.assertTrue(vus["Kiné-témoin"]["attente"])
        # il repond : la file part, dans l'ordre, puis se vide
        panne.clear()
        m.lire_agenda_synchro(m.CFG, "2026-10-20", 14)
        self.assertEqual([("supprimer" in c, c.get("id"), c.get("titre")) for c in envoyes],
                         [(False, None, "Kiné-témoin"), (True, None, None), (False, 1, "Dentiste-témoin")])
        self.assertEqual(envoyes[1]["supprimer"], 2)
        self.assertEqual(m.agenda_local()["attente"], [])

    def test_minuteurs_alarmes_et_chronos_tournent_en_fond(self):
        # « fait en sorte que je puisse demander a jarvis de mettre un minuteur,
        # un chronometre ou une alarme qui tourne en fond »
        m = self.m
        self.addCleanup(lambda: m.annuler_chronos())
        vrais = (m.annoncer, m.poser_led, m._cle_presente)
        self.addCleanup(lambda: (setattr(m, "annoncer", vrais[0]), setattr(m, "poser_led", vrais[1]),
                                 setattr(m, "_cle_presente", vrais[2])))
        dits = []
        m.annoncer = lambda texte, langue="fr": dits.append(texte)
        m.poser_led = lambda *a, **k: None
        m._cle_presente = lambda cfg: False
        m.annuler_chronos()
        o = lambda **e: m.outil_minuteurs(e, m.CFG)
        self.assertIn("« pates »", o(action="minuteur", secondes=600, nom="pates"))
        self.assertIn("Alarme", o(action="alarme", heure="7:00", nom="se lever"))
        self.assertEqual(o(action="chrono_lancer", nom="course"), "Chronomètre lancé.")
        genres = sorted(x["genre"] for x in m.JARVIS["minuteurs"])
        self.assertEqual(genres, ["alarme", "chrono", "minuteur"])
        liste = o(action="lister")
        self.assertRegex(liste, r"minuteur « pates » : reste 09:5\d|minuteur « pates » : reste 10:00")
        self.assertIn("chronometre « course »", liste)
        # garde dans la config : un redemarrage ne les perd pas
        self.assertEqual(len(m.CFG["jarvis_chronos"]), 3)
        self.assertNotIn("minuteur", m.CFG["jarvis_chronos"][0], "l'objet Timer ne va pas dans la config")
        # « annule les minuteurs » : pas l'alarme de demain matin
        m.executer_commande({"action": "minuteurs_annuler"}, m.CFG)
        self.assertEqual(sorted(x["genre"] for x in m.JARVIS["minuteurs"]), ["alarme", "chrono"])
        # le chrono s'arrete et dit le temps ecoule
        m.JARVIS["minuteurs"][-1]["debut"] -= 125
        self.assertIn("2 minutes et 5 secondes", o(action="chrono_arreter", nom="course"))
        # l'alarme sonne : son nom, a voix haute
        alarme = m.JARVIS["minuteurs"][0]
        alarme["minuteur"].cancel()
        alarme["minuteur"].function()
        self.assertRegex(dits[-1], r"^Il est \d+ h(?: \d\d)? : se lever\.$")
        self.assertEqual(m.JARVIS["minuteurs"], [])
        self.assertEqual(m.CFG["jarvis_chronos"], [])
        with self.assertRaises(LookupError):
            o(action="annuler", nom="rien")

    def test_l_heure_d_une_alarme(self):
        m = self.m
        base = time.mktime((2026, 10, 21, 22, 0, 0, 0, 0, -1))
        self.assertEqual(time.localtime(m.fin_d_alarme("23:30", maintenant=base))[2:5], (21, 23, 30))
        self.assertEqual(time.localtime(m.fin_d_alarme("7h", maintenant=base))[2:5], (22, 7, 0), "demain matin")
        self.assertEqual(time.localtime(m.fin_d_alarme("7:15", "2026-10-25", maintenant=base))[1:5], (10, 25, 7, 15))
        for faux in ("25:00", "midi", "7:75"):
            with self.assertRaises(ValueError):
                m.fin_d_alarme(faux, maintenant=base)

    def test_au_redemarrage_ce_qui_tournait_reprend(self):
        m = self.m
        self.addCleanup(lambda: m.annuler_chronos())
        notifs = []
        m.JARVIS_CROCHETS["notifier"] = lambda t, x: notifs.append(x)
        m.annuler_chronos()
        t = time.time()
        m.CFG["jarvis_chronos"] = [
            {"id": 1, "genre": "minuteur", "fin": t + 300, "duree": 600, "quoi": "pates"},
            {"id": 2, "genre": "chrono", "debut": t - 60, "quoi": ""},
            {"id": 3, "genre": "alarme", "fin": t - 120, "duree": 3600, "quoi": "reunion"}]
        self.assertEqual(m.restaurer_chronos(m.CFG), 1, "l'alarme a sonne pendant que c'etait ferme")
        self.assertEqual(sorted(x["id"] for x in m.JARVIS["minuteurs"]), [1, 2])
        self.assertIn("« reunion » a sonne", notifs[-1])
        self.assertEqual(len(m.CFG["jarvis_chronos"]), 2)

    def test_jarvis_se_souvient_de_la_conversation_meme_congedie(self):
        # « fais en sorte que jarvis se souvienne beaucoup mieux des conversations
        # passees [...] pouvant reprendre un fil de discussion s'il est eteint ou
        # interrompu » -- congedie, la conversation est resumee, plus jetee
        m = self.m
        vrais = (m._en_fond, m._requete_bd, m._cle_presente, m.poser_led)
        self.addCleanup(lambda: (setattr(m, "_en_fond", vrais[0]), setattr(m, "_requete_bd", vrais[1]),
                                 setattr(m, "_cle_presente", vrais[2]), setattr(m, "poser_led", vrais[3])))
        envoyes = []

        def bd(chemin, corps, cfg, delai, **k):
            envoyes.append((chemin, corps))
            return {"texte": "A cherche un garage-témoin ouvert le samedi : le garage Martin-témoin, "
                             "rue des Lilas-témoin, 9 h-12 h. Reste a appeler pour le devis. " * 3}
        m._en_fond, m._requete_bd, m._cle_presente = (lambda f: f()), bd, (lambda cfg: True)
        m.poser_led = lambda *a, **k: None
        m.CFG["jarvis_souvenirs"] = []
        m.JARVIS.update(mode="jarvis", psy_echange=[], historique=[
            {"role": "user" if i % 2 == 0 else "assistant", "texte": "replique %d" % i} for i in range(50)])
        m.terminer_conversation()
        self.assertEqual(m.JARVIS["historique"], [])
        resume = [c for ch, c in envoyes if c.get("transition") == "resume"]
        self.assertEqual(len(resume), 1, "la conversation congediee est resumee")
        self.assertEqual(len(resume[0]["historique"]), m.HISTORIQUE_JARVIS)
        self.assertEqual(resume[0]["historique"][-1]["texte"], "replique 49")
        souvenir = m.CFG["jarvis_souvenirs"][-1]["texte"]
        self.assertGreater(len(souvenir), 200, "le souvenir garde les details")
        self.assertLessEqual(len(souvenir), m.SOUVENIR_SIGNES)

    def test_ctrl_j_le_reveille_et_un_second_appui_le_congedie(self):
        # « Ctrl+J n'allume rien, j'entends juste le bruit de notif »
        m = self.m
        vrais = (m.oreille_vivante, m.poser_led, m.declencher_routines, m.terminer_conversation)
        self.addCleanup(lambda: (setattr(m, "oreille_vivante", vrais[0]), setattr(m, "poser_led", vrais[1]),
                                 setattr(m, "declencher_routines", vrais[2]),
                                 setattr(m, "terminer_conversation", vrais[3])))
        congedies = []
        m.oreille_vivante, m.poser_led = (lambda: True), (lambda *a, **k: None)
        m.declencher_routines = lambda *a, **k: None
        m.terminer_conversation = lambda: congedies.append(1)
        m.prechauffer_dictee = lambda: None
        m.envoyer_oreille = lambda o: self.envoye.append(o) or True
        m.CFG["jarvis_actif"] = False
        m.JARVIS.update(etat="eteint", mode="jarvis", suite_active=False)
        self.assertEqual(m.reveil_au_clavier(m.CFG, attendre_oreille_s=0), "reveille")
        self.assertTrue(m.CFG["jarvis_actif"], "eteint, il s'allume d'abord")
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        self.assertTrue(m.JARVIS["suite_active"], "pas besoin de dire son nom : on l'a appele au clavier")
        self.assertEqual([o["cmd"] for o in self.envoye], ["ecouter"])
        self.assertEqual(m.reveil_au_clavier(m.CFG, attendre_oreille_s=0), "congedie")
        self.assertEqual(congedies, [1])
        # pendant qu'il ouvre le micro, un appui ne le congedie pas : il l'attend
        m.JARVIS.update(etat="demarrage")
        m.oreille_vivante = lambda: False
        self.assertEqual(m.reveil_au_clavier(m.CFG, attendre_oreille_s=0), "sans_oreille")
        self.assertEqual(congedies, [1])

    def test_un_appel_pas_net_est_verifie_par_transcription(self):
        m = self.m
        envoye = []
        m.envoyer_oreille = envoye.append
        m.transcrire = lambda o: "Jervis, mets de la musique"
        self.assertTrue(m.verifier_appel(base64.b64encode(b"RIFF").decode()))
        self.assertEqual(envoye[-1], {"cmd": "verifie", "ok": True})
        m.transcrire = lambda o: "j'arrive dans deux minutes"
        self.assertFalse(m.verifier_appel(base64.b64encode(b"RIFF").decode()))
        self.assertEqual(envoye[-1], {"cmd": "verifie", "ok": False})
        m.etat_dictee = lambda: {"etat": "absent", "progres": 0.0}
        self.assertFalse(m.verifier_appel(""), "sans transcription, on ne se reveille pas au hasard")
        self.assertTrue(m.config_oreille(m.CFG)["tolerant"])

    def test_un_jarvis_dit_seul_et_ecorche_confirme_l_appel(self):
        # « J'ai galere a ce qu'il s'allume » : Parakeet ecrit un « Jarvis » dit
        # seul « Javi », « Chavis », « É Javi » -- c'est bien lui
        m = self.m
        envoye = []
        m.envoyer_oreille = envoye.append
        for t in ("Javi ?", "Chavis.", "É Javi.", "Ok, Javi.", "Jarbis"):
            m.transcrire = lambda o, t=t: t
            self.assertTrue(m.verifier_appel(base64.b64encode(b"RIFF").decode(), n=7), t)
            self.assertEqual(envoye[-1], {"cmd": "verifie", "ok": True, "n": 7})
        for t in ("j'avais dit", "java", "j'arrive", "le Javi que j'ai codé"):
            m.transcrire = lambda o, t=t: t
            self.assertFalse(m.verifier_appel(base64.b64encode(b"RIFF").decode()), t)
            self.assertIs(envoye[-1]["ok"], False, t)

    def test_le_bout_de_son_coupe_apres_le_nom_n_est_pas_une_mention(self):
        # « Jarvis il est quelle heure ? » d'une traite : le bout de son a
        # verifier finit sur « Jarvis il » -- ce n'est pas « Jarvis il plante »
        m = self.m
        envoye = []
        m.envoyer_oreille = envoye.append
        for t in ("Jarvis il", "Jarvis elle est", "Jarvis il est quelle"):
            m.transcrire = lambda o, t=t: t
            self.assertTrue(m.verifier_appel(base64.b64encode(b"RIFF").decode()), t)
        m.transcrire = lambda o: "Jarvis il apparaît pour rien"
        self.assertFalse(m.verifier_appel(base64.b64encode(b"RIFF").decode()))

    def test_sans_transcription_l_appel_est_illisible_pas_ecarte(self):
        # « illisible » : l'oreille laisse le score trancher (tout pres du seuil,
        # c'etait lui) -- un « non » rejetait TOUT appel pas net, sans un mot
        m = self.m
        envoye = []
        m.envoyer_oreille = envoye.append
        m.etat_dictee = lambda: {"etat": "absent", "progres": 0.0}
        self.assertFalse(m.verifier_appel(base64.b64encode(b"RIFF").decode(), n=3))
        self.assertEqual(envoye[-1], {"cmd": "verifie", "ok": None, "n": 3})
        m.etat_dictee = lambda: {"etat": "pret", "progres": 1.0}

        def plus_de_memoire(o):
            raise m.DicteeImpossible("memoire")
        m.transcrire = plus_de_memoire
        self.assertFalse(m.verifier_appel(base64.b64encode(b"RIFF").decode()))
        self.assertIsNone(envoye[-1]["ok"])

    def test_la_verification_lente_se_voit(self):
        m = self.m
        m.JARVIS["essais"] = [{"d": 0.2, "issue": "verifier"}]
        m.traiter_evenement({"evt": "essai", "maj": True, "issue": "lent"})
        self.assertEqual(m.JARVIS["essais"], [{"d": 0.2, "issue": "lent"}], "une mise a jour, pas un essai de plus")
        m.traiter_evenement({"evt": "essai", "maj": True, "issue": "sans_lecture"})
        self.assertEqual(m.JARVIS["essais"][-1]["issue"], "sans_lecture")

    def test_ses_phrases_ne_disent_jamais_son_nom(self):
        # « Mes mains sont fermees : Reglages, Jarvis. » -- sans double
        # transmission, sa propre voix le reveillait
        for cle, textes in self.m._PHRASES.items():
            for t in textes:
                if t:
                    self.assertIsNone(self.m._jv.nom_verifie(t), (cle, t))
                    self.assertFalse(self.m._jv.contient_nom(t), (cle, t))

    def test_le_sous_titre_suit_la_voix(self):
        m = self.m
        m.SOUS_TITRES.clear()
        m.SOUS_TITRES[7] = {"phrases": ["Bien sur monsieur.", "Il fait beau."], "k": -1}
        m.JARVIS["sous_titre"] = None
        self.assertEqual(m.sous_titre_courant(), "")
        m.JARVIS["sous_titre"] = m.SOUS_TITRES[7]
        self.assertEqual(m.sous_titre_courant(), "", "la voix n'a pas encore commence")
        t = time.time()
        m.SOUS_TITRES[7].update(k=1, t0=t, duree=2.0)
        self.assertEqual(m.sous_titre_courant(t + 0.1), "Bien sur monsieur. Il")
        self.assertEqual(m.sous_titre_courant(t + 3.0), "Bien sur monsieur. Il fait beau.")
        # la voix de Windows ne dit rien : au debit moyen
        m.JARVIS["sous_titre"] = {"phrases": ["un deux trois quatre cinq six"], "k": -1, "estime": True, "t0": t}
        self.assertEqual(m.sous_titre_courant(t + 0.7), "un deux trois")
        self.assertEqual(m.sous_titre_courant(t + 60), "un deux trois quatre cinq six")

    def test_sa_boule_lit_l_enveloppe_de_sa_voix(self):
        # « un petit peu de jazz » : le niveau de SA voix, relu au fil du temps
        m = self.m
        m.SOUS_TITRES.clear()
        m.SOUS_TITRES[8] = {"phrases": ["Tres bien monsieur."], "k": -1}
        m.JARVIS["sous_titre"] = None
        self.assertEqual(m.niveau_de_sa_voix(), 0.0, "rien encore : elle respire")
        m.JARVIS["sous_titre"] = m.SOUS_TITRES[8]
        self.assertEqual(m.niveau_de_sa_voix(), 0.0, "la voix n'a pas encore commence")
        a, b = socket.socketpair()
        try:
            J.envoyer(a, {"evt": "dit", "id": 8, "phrase": 0, "duree": 0.3,
                          "env": [0, 99, 99, 0, 0, 0], "pas": 0.05}, threading.Lock())
            a.close()
            avant = time.time()
            m._lire_voix(b)
        finally:
            b.close()
        st = m.SOUS_TITRES[8]
        self.assertEqual(st["k"], 0, "le sous-titre, comme avant")
        t0, pas, env = st["enveloppe"]
        self.assertGreaterEqual(t0, avant)
        self.assertEqual((pas, env), (0.05, [0, 99, 99, 0, 0, 0]))
        lat = J.VOIX_LATENCE_S
        self.assertAlmostEqual(m.niveau_de_sa_voix(t0 + lat + 0.09), 1.0, places=6, msg="la tranche forte")
        self.assertEqual(m.niveau_de_sa_voix(t0 + lat + 0.01), 0.0, "le blanc du debut")
        self.assertEqual(m.niveau_de_sa_voix(t0 + lat + 3.0), 0.0, "la phrase finie")
        self.assertGreater(m.niveau_de_sa_voix(t0 + lat + 0.2), 0.3, "il retombe en douceur")
        # la voix de Windows ne dit rien de son son : None, et la boule swingue sans elle
        m.JARVIS["sous_titre"] = {"phrases": ["Oui."], "k": -1, "estime": True, "t0": time.time()}
        self.assertIsNone(m.niveau_de_sa_voix())

    def test_l_aide_courte(self):
        m = self.m
        long = ("Avant le mot d'eveil, rien ne sort du micro. Apres, la phrase est transcrite sur ce PC, "
                "par le moteur de la dictee, telecharge une fois quand tu coches la case.")
        self.assertEqual(m.aide_courte(long), "Avant le mot d'eveil, rien ne sort du micro.   plus \u203a")
        self.assertIsNone(m.aide_courte("Court."), "court : entier")
        tres_long = "mot " * 80
        c = m.aide_courte(tres_long)
        self.assertTrue(c.endswith("\u2026   plus \u203a") and len(c) < m.AIDE_LONGUE + 15)

    def test_jamais_eteindre_redemarrer_mettre_en_veille_ni_fermer_la_session(self):
        m = self.m
        m.CFG["jarvis_pc"] = True
        ouverts = []
        avait = hasattr(m.os, "startfile")
        vrai = getattr(m.os, "startfile", None)
        m.os.startfile = ouverts.append
        self.addCleanup(lambda: setattr(m.os, "startfile", vrai) if avait else delattr(m.os, "startfile"))
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        for a in ("veille", "eteindre", "redemarrer", "deconnecter"):
            self.assertIn("ni fermer la session", ex("pc", {"action": a})["erreur"], a)
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        bat = os.path.join(d, "dodo.bat")
        with open(bat, "w") as f:
            f.write("@echo off\r\nshutdown /s /t 0\r\n")
        texte = os.path.join(d, "liste.txt")
        with open(texte, "w") as f:
            f.write("shutdown, c'est le titre d'un film")
        self.assertIn("ni fermer la session", ex("ouvrir", {"chemin": bat})["erreur"])
        self.assertIn("Ouvert", ex("ouvrir", {"chemin": texte})["texte"], "un texte qui en parle s'ouvre")
        r = ex("creer_fichier", {"chemin": os.path.join(d, "eteins.ps1"), "contenu": "Stop-Computer -Force"})
        self.assertIn("ni fermer la session", r["erreur"])
        self.assertFalse(os.path.exists(os.path.join(d, "eteins.ps1")), "et le script n'est pas ecrit")
        vraies = m.applis_installees
        self.addCleanup(lambda: setattr(m, "applis_installees", vraies))
        m.applis_installees = lambda frais=False: [("Arreter le PC", r"C:\Windows\System32\shutdown.exe", "appli")]
        self.assertIn("ni fermer la session", ex("lancer_appli", {"nom": "arreter le PC"})["erreur"])
        self.assertEqual(ouverts, [texte], "rien d'autre n'a ete lance")
        src = open(os.path.join(RACINE, "machi_tool.py"), encoding="utf-8").read()
        for appel in ("SetSuspendState", "ExitWindowsEx", "InitiateSystemShutdown", "mettre_en_veille", "Stop-Computer"):
            self.assertNotIn(appel, src, appel)

    def test_l_etalonnage_au_fil_de_l_eau(self):
        m = self.m
        m.envoyer_oreille = lambda c: self.envoye.append(c)
        rng = np.random.default_rng(3)
        g = J.normer(rng.normal(size=(9, 96)))
        m.sauver_gabarits([g.tolist()])
        proche = lambda k: J.normer(g + 0.03 * np.random.default_rng(100 + k).normal(size=g.shape)).tolist()
        self.assertTrue(m.ajouter_gabarit_auto(proche(0)))
        self.assertEqual(len(m.gabarits_auto()), 1)
        self.assertFalse(m.ajouter_gabarit_auto(proche(0)), "deja connue")
        self.assertFalse(m.ajouter_gabarit_auto(J.normer(rng.normal(size=(9, 96))).tolist()), "un autre mot")
        self.assertFalse(m.ajouter_gabarit_auto([[0.1] * 96] * 2), "trop court")
        cfg = m.config_oreille(m.CFG)
        # a part : une facon apprise seul ne reveille jamais sans verification
        self.assertEqual((len(cfg["gabarits"]), len(cfg["gabarits_auto"]), cfg["auto"]), (1, 1, True))
        for k in range(1, 10):
            m.ajouter_gabarit_auto(proche(k))
        self.assertEqual(len(m.gabarits_auto()), J.AUTO_PLAFOND, "les plus anciennes s'en vont")
        self.assertEqual(len(m.gabarits_jarvis()), 1, "celles apprises a la main ne bougent pas")
        # par l'evenement de l'oreille : gardee, et l'oreille la recoit
        m.sauver_gabarits([g.tolist()], garder_auto=False)
        self.assertEqual(m.gabarits_auto(), [], "tout reappris : ce qu'il avait garde seul s'en va")
        m.traiter_evenement({"evt": "gabarit_auto", "vecteurs": proche(20)})
        self.assertEqual(m.gabarits_auto(), [], "pas encore : la phrase n'est pas transcrite")
        self.assertEqual(m.garder_facons("mets de la musique"), 0, "sans son nom dans la phrase : un bruit")
        self.assertEqual(m.gabarits_auto(), [])
        m.traiter_evenement({"evt": "gabarit_auto", "vecteurs": proche(20)})
        self.assertEqual(m.garder_facons("Jarvis, mets de la musique"), 1)
        self.assertEqual(len(m.gabarits_auto()), 1)
        self.assertEqual(len(self.envoye[-1]["gabarits"]) + len(self.envoye[-1]["gabarits_auto"]), 2)
        m.sauver_gabarits([g.tolist(), proche(30)], garder_auto=True)
        self.assertEqual(len(m.gabarits_auto()), 1, "une facon de plus : on garde le reste")
        # « il se declenche tout seul des qu'il y a un bruit » : les facons
        # apprises seul avant la v1.58 sont effacees une fois ; les tiennes restent
        m.CFG["jarvis_auto_purge"] = 0
        self.assertTrue(m.purger_facons_douteuses(m.CFG))
        self.assertEqual(m.gabarits_auto(), [])
        self.assertEqual(len(m.gabarits_jarvis()), 2)
        self.assertFalse(m.purger_facons_douteuses(m.CFG), "une seule fois")
        # coupe : plus rien n'est garde, et l'oreille ne recoit que celles apprises
        m.CFG["jarvis_auto_etalonnage"] = False
        self.assertFalse(m.ajouter_gabarit_auto(proche(40)))
        cfg = m.config_oreille(m.CFG)
        self.assertEqual((len(cfg["gabarits"]), cfg["auto"]), (2, False))

    def test_huit_fois_sur_des_tons_differents(self):
        # « que je puisse l'appeler avec beaucoup de tons differents » et « plus
        # de tolerance, plus de tests » : cinq fois normalement, puis la
        # question, plus fort, plus bas
        rng = np.random.default_rng(3)
        base = rng.normal(size=(8, 96))
        proche = lambda e: (base + rng.normal(scale=e, size=base.shape)).tolist()
        essais = [proche(0.3) for _ in range(5)] + [proche(0.5), proche(0.5), proche(0.5)]
        ok, consignes, gardes = self.apprentissage(essais)
        self.assertTrue(ok)
        self.assertEqual(len(gardes), 8)
        self.assertEqual(len(consignes), 8)
        self.assertIn("question", consignes[5])
        self.assertIn("fort", consignes[6])
        self.assertIn("bas", consignes[7])
        self.assertIn("Appris (8 facons)", self.m.JARVIS["apprentissage"]["message"])
        # UN ESSAI RATE (une toux, une porte) parmi les normaux : on ne jette plus
        # tout -- il est ecarte, le reste est garde
        autre = rng.normal(size=(8, 96)).tolist()
        ok, _, gardes = self.apprentissage([proche(0.3), autre, proche(0.3), proche(0.3), proche(0.3),
                                            proche(0.5), rng.normal(size=(8, 96)).tolist(), proche(0.5)])
        self.assertTrue(ok)
        self.assertEqual(len(gardes), 6)
        self.assertIn("2 essais ecartes", self.m.JARVIS["apprentissage"]["message"])
        # que du bruit : la, on refait
        ok, _, _ = self.apprentissage([rng.normal(size=(8, 96)).tolist() for _ in range(8)])
        self.assertFalse(ok)
        self.assertIn("ne se ressemblent pas du tout", self.m.JARVIS["apprentissage"]["message"])
        # « Ajouter une facon » : une de plus, avec les autres ; pas un autre mot.
        self.apprentissage(essais)
        ok, _, gardes = self.apprentissage([proche(0.5)], total=1, ajouter=True)
        self.assertTrue(ok)
        self.assertEqual(len(gardes), 9)
        ok, _, gardes = self.apprentissage([rng.normal(size=(8, 96)).tolist()], total=1, ajouter=True)
        self.assertFalse(ok)
        self.assertEqual(len(gardes), 9)

    def test_calibrer_encore_niveau_et_nom_de_ta_voix(self):
        # « Jarvis galere vraiment a reconnaitre ma voix » : l'apprentissage garde
        # le niveau de ta voix et comment la transcription ecrit ton « Jarvis »,
        # et l'oreille recoit un seuil cale sur l'ecart entre tes « Jarvis »
        m = self.m
        rng = np.random.default_rng(8)
        base = rng.normal(size=(8, 96))
        proche = lambda e: (base + rng.normal(scale=e, size=base.shape)).tolist()
        m.etat_dictee = lambda: {"etat": "pret", "progres": 1.0}
        m.transcrire = lambda o: "Travis."
        wav = base64.b64encode(b"RIFF").decode()
        evs = [{"evt": "gabarit", "vecteurs": proche(0.3), "niveau": 180.0 + k, "wav": wav} for k in range(8)]
        ok, _, gardes = self.apprentissage(evs)
        self.assertTrue(ok)
        self.assertEqual(m.niveau_voix_appris(), 184.0)
        self.assertIn("travis", m.noms_appris())
        cfg = m.config_oreille(m.CFG)
        self.assertEqual(cfg["niveau_voix"], 184.0)
        self.assertIsNotNone(cfg["seuil_perso"])
        self.assertIn("verifie jusqu'a", m.JARVIS["apprentissage"]["message"])
        # une verification entendue « Travis » : c'est bien lui
        envoye = []
        m.envoyer_oreille = envoye.append
        m.transcrire = lambda o: "Travis, la lumiere"
        self.assertTrue(m.verifier_appel(wav))
        # « Calibrer encore » : les tons de TONS_CALIBRATION, ajoutes aux autres
        m.transcrire = lambda o: "Jarvis"
        ok, consignes, apres = self.apprentissage([proche(0.4) for _ in m.TONS_CALIBRATION],
                                                  total=len(m.TONS_CALIBRATION), ajouter=True,
                                                  tons=m.TONS_CALIBRATION)
        self.assertTrue(ok)
        self.assertEqual(len(apres), len(gardes) + len(m.TONS_CALIBRATION))
        self.assertIn("milieu d'une phrase", consignes[1])
        self.assertEqual(m.niveau_voix_appris(), 184.0, "garde quand on ajoute")
        self.assertIn("travis", m.noms_appris())

    def test_une_tache_de_fond_de_bout_en_bout(self):
        """Jarvis la lance (sans les mains sur le PC), un fil la suit, le texte
        est range, la notification part, et il l'annonce une fois libre."""
        m = self.m
        m.CFG.update(jarvis_pc=False, jarvis_actif=True, jarvis_langue="fr",
                     jarvis_projets="Irontide :\n  - robots\n")
        envois, sondes = [], [{"etat": "en_cours"}, {}, {"etat": "fini", "resume": "La 5070.",
                                                        "texte": "## Comparatif\nDetail."}]

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            envois.append((chemin, charge))
            if charge is not None:
                return {"id": "T1", "etat": "en_cours"}
            r = sondes.pop(0)
            if not r:
                raise OSError("reseau")          # un reseau qui tousse ne l'arrete pas
            return r
        vrai = m._requete_bd
        self.addCleanup(lambda: setattr(m, "_requete_bd", vrai))
        m._requete_bd = bd
        m.TACHES_PRETES.clear()
        suivre = m.suivre_tache
        m.suivre_tache = lambda *a, **k: None       # le fil : suivi a la main, plus bas
        self.addCleanup(lambda: setattr(m, "suivre_tache", suivre))
        r = m.executer_outil({"id": "x", "nom": "lancer_tache",
                              "entree": {"demande": "Compare les cartes a 600 euros", "genre": "recherche",
                                         "titre": "Cartes graphiques"}}, m.CFG)
        self.assertIn("Tache lancee : « Cartes graphiques »", r["texte"])
        self.assertEqual(envois[0][0], "/api/machitool/tache")
        self.assertIn("Irontide", envois[0][1]["projets"], "le contexte des projets part avec")
        # le suivi (sans attendre pour de vrai)
        suivre("T1", m.CFG, dormir=lambda s: None)
        t = m.lire_taches()[0]
        self.assertEqual((t["etat"], t["resume"]), ("fini", "La 5070."))
        with open(t["fichier"], encoding="utf-8") as f:
            contenu = f.read()
        self.assertIn("# Cartes graphiques", contenu)
        self.assertIn("## Comparatif", contenu)
        self.assertIn("est prete", self.dit[-1], "la notification")
        # occupe (il parle) : pas d'annonce ; libre : l'annonce
        m.JARVIS["etat"] = "parle"
        self.assertIsNone(m.annoncer_taches(m.CFG))
        m.JARVIS["etat"] = "attente"
        self.assertIn("La recherche sur « Cartes graphiques » est prete", m.annoncer_taches(m.CFG))
        self.assertIsNone(m.annoncer_taches(m.CFG), "une seule fois")
        # « qu'as-tu trouve ? »
        lu = m.executer_outil({"id": "y", "nom": "taches", "entree": {"action": "lire"}}, m.CFG)
        self.assertIn("Detail.", lu["texte"])
        self.assertIn("1. Cartes graphiques (finie",
                      m.executer_outil({"id": "z", "nom": "taches", "entree": {"action": "lister"}}, m.CFG)["texte"])
        self.assertIn("numero 4", m.executer_outil({"id": "w", "nom": "taches",
                                                    "entree": {"action": "lire", "numero": 4}}, m.CFG)["erreur"])
        # BrainDebugger pas encore redeploye : on le dit
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"{}"))

        def ancien(*a, **k):
            raise err
        m._requete_bd = ancien
        r = m.executer_outil({"id": "v", "nom": "lancer_tache", "entree": {"demande": "x"}}, m.CFG)
        self.assertIn("redeployer", r["erreur"])

    def test_noter_un_projet_et_les_capacites(self):
        m = self.m
        m.CFG.update(jarvis_pc=False, jarvis_projets="")
        r = m.executer_outil({"id": "p", "nom": "noter_projet",
                              "entree": {"projet": "Irontide", "note": "un mode coop a deux"}}, m.CFG)
        self.assertNotIn("erreur", r)
        self.assertEqual(m.CFG["jarvis_projets"], "Irontide :\n  - un mode coop a deux\n")
        c = m.capacites_jarvis(m.CFG)
        self.assertTrue(c["taches"])
        self.assertIn("un mode coop", c["projets"])
        self.assertFalse(_jv_modifiable := J.reglage_modifiable("jarvis_projets", m.CONFIG_DEFAUT),
                         "reglages_machi ne peut pas effacer tes projets")

    def test_un_outil_qui_echoue_dit_pourquoi(self):
        m = self.m
        m.CFG.update(jarvis_pc=True, spotify_client_id="CID", spotify_refresh="R")

        class Casse:
            def jouer(self, *a, **k):
                raise J.ErreurSpotify("Spotify refuse (403 : Restriction violated).")
        vrai = m.spotify_de
        self.addCleanup(lambda: setattr(m, "spotify_de", vrai))
        m.spotify_de = lambda cfg: Casse()
        r = m.executer_outil({"id": "s", "nom": "spotify_jouer", "entree": {"recherche": "get lucky"}}, m.CFG)
        self.assertEqual(r["erreur"], "Spotify refuse (403 : Restriction violated).", "sans « ErreurSpotify : »")
        self.assertIn("Restriction violated", m.JARVIS["spotify_message"], "et on le voit sous « Spotify »")

    def test_on_voit_ce_qui_calcule_la_voix(self):
        """L'exe n'a pas de console : le moteur de Kokoro se lit dans le panneau."""
        m = self.m
        self.addCleanup(lambda: m.KOKORO.__setitem__("calcul", {}))
        self.assertEqual(m.texte_calcul_kokoro("fr"), "", "rien de rapporte, rien d'affiche")
        m.KOKORO["calcul"] = {"fr": {"moteur": "DmlExecutionProvider", "rtf": 0.04, "refus": []}}
        t = m.texte_calcul_kokoro("fr")
        self.assertIn("carte graphique (DirectML)", t)
        self.assertIn("0.04 s par seconde de parole", t)
        m.KOKORO["calcul"] = {"en": {"moteur": "CPUExecutionProvider", "rtf": 0.3,
                                     "refus": ["DmlExecutionProvider : pas de carte"]}}
        t = m.texte_calcul_kokoro("en")
        self.assertIn("le processeur", t)
        self.assertIn("pas de carte", t, "et pourquoi la carte graphique n'a pas servi")

    def test_les_noms_pollues_sont_ecartes_a_la_lecture(self):
        m = self.m
        m.sauver_gabarits([[[0.1] * 96] * 8] * 3, noms=["travis", "lumiere", "musique", "jarvi"])
        self.assertEqual(m.noms_appris(), ["travis", "jarvi"])
        envoye = []
        m.envoyer_oreille = envoye.append
        m.transcrire = lambda o: "mets la musique"
        self.assertFalse(m.verifier_appel(base64.b64encode(b"RIFF").decode()))

    def test_le_chien_de_garde_de_l_oreille(self):
        m = self.m
        t = time.time()
        m.JARVIS["niveau_t"] = t
        self.assertFalse(m.oreille_muette(t + 10))
        self.assertTrue(m.oreille_muette(t + m.OREILLE_MUETTE_S + 1))
        m.traiter_evenement({"evt": "niveau", "db": -40})
        self.assertFalse(m.oreille_muette(), "chaque seconde, elle dit qu'elle vit")
        m.JARVIS.pop("niveau_t")
        self.assertFalse(m.oreille_muette(), "pas encore demarree : rien a surveiller")

    def test_l_indicateur_garde_les_derniers_essais(self):
        m = self.m
        m.JARVIS["essais"] = []
        for k in range(15):
            m.traiter_evenement({"evt": "essai", "d": 0.1 + k / 100, "issue": "rate", "direct": 0.05, "verifie": 0.1})
        self.assertEqual(len(m.JARVIS["essais"]), 12)
        self.assertAlmostEqual(m.JARVIS["essais"][-1]["d"], 0.24)

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

    def mains(self, reponses, code="4815", ecran=False, code_actif=True):
        """Jarvis avec ses mains : BrainDebugger est remplace par `reponses` (une
        liste, une par requete), le PC par un dossier temporaire. Rend la liste
        des requetes envoyees et le dossier."""
        m = self.m
        envoyes = []
        file_ = list(reponses)

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            envoyes.append(json.loads(json.dumps(charge)))
            return file_.pop(0)
        maison = tempfile.mkdtemp(dir=self.tmp)
        os.makedirs(os.path.join(maison, "Documents"))
        vrais = {k: getattr(m, k) for k in ("_requete_bd", "bases_dossiers", "touche_media", "capturer_ecran",
                                            "capturer_ecrans")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        m._requete_bd = bd
        m.bases_dossiers = lambda: {"home": maison, "documents": os.path.join(maison, "Documents")}
        m.touche_media = lambda action: "Piste suivante." if action == "suivant" else "Fait."
        m.capturer_ecran = lambda n: ("QUJD", int(n or 1), 2)
        m.capturer_ecrans = lambda ns: [("QUFB" if n == 1 else "QUJD", n, 2) for n in
                                        ([1, 2] if 0 in [int(x or 0) for x in ns] else [int(x) for x in ns])]
        m.envoyer_oreille = lambda o: True
        m.CFG.update(jarvis_pc=True, jarvis_ecran=ecran, jarvis_langue="fr", jarvis_code_actif=code_actif)
        m.poser_code(m.CFG, code)
        m.JARVIS.update(acces_jusqua=0.0, verrou_jusqua=0.0, attente_code=None)
        return envoyes, maison

    @staticmethod
    def outil(nom, entree, ident="t1"):
        return {"texte": "", "mode": "jarvis", "outils": [{"id": ident, "nom": nom, "entree": entree}],
                "suite": [{"role": "user", "content": "x"},
                          {"role": "assistant", "content": [{"type": "tool_use", "id": ident, "name": nom,
                                                             "input": entree}]}]}

    def test_il_comprend_qu_on_veut_le_psychologue(self):
        # « s'il comprend que c'est ce que je veux » : BrainDebugger a passe la
        # phrase au compagnon ; on reste en mode psy -- sans le silence du grave
        self.mains([{"texte": "Je t'écoute. Qu'est-ce qui s'est passé ?", "mode": "psy", "raison": "demande"}])
        self.phrase("Jarvis, j'ai eu une journée horrible, j'ai besoin d'en parler")
        self.assertEqual(self.m.JARVIS["mode"], "psy")
        self.assertFalse(self.m.JARVIS["psy_grave"])
        self.assertEqual(self.m.JARVIS["psy_echange"][-1]["texte"], "Je t'écoute. Qu'est-ce qui s'est passé ?")
        # le grave, lui, garde son silence a l'au revoir
        self.m.poser_mode("jarvis")
        self.mains([{"texte": "Je suis là.", "mode": "psy", "raison": "grave"}])
        self.phrase("Jarvis, je n'en peux plus")
        self.assertTrue(self.m.JARVIS["psy_grave"])

    def test_ses_mains_demandent_le_code_a_voix_haute(self):
        # « Lorsqu'il doit interagir il demande un code d'acces a l'oral avant
        # d'effectuer l'operation. »
        envoyes, maison = self.mains([self.outil("creer_dossier", {"chemin": "Documents\\Projets 2026"}),
                                      {"texte": "C'est fait.", "mode": "jarvis"}])
        cible = os.path.join(maison, "Documents", "Projets 2026")
        self.phrase("Jarvis, crée un dossier Projets 2026 dans mes documents")
        self.assertTrue(envoyes[0]["outils"], "Machi Tool annonce ses mains")
        self.assertFalse(envoyes[0]["ecran"], "l'ecran n'est pas permis")
        self.assertEqual(self.dit[-1], "Code d'accès ?")
        self.assertFalse(os.path.exists(cible), "rien avant le code")
        self.phrase("1 2 3 4")
        self.assertEqual(self.dit[-1], "Ce n'est pas le bon code. Encore une fois ?")
        self.assertFalse(os.path.exists(cible))
        self.phrase("Quatre, huit, un, cinq.")
        self.assertTrue(os.path.isdir(cible), "le code juste : c'est fait")
        self.assertEqual(self.dit[-1], "C'est fait.")
        self.assertEqual(envoyes[1]["resultats"][0]["id"], "t1")
        self.assertIn("Projets 2026", envoyes[1]["resultats"][0]["texte"])
        tout = json.dumps(envoyes)
        for dit in ("4815", "Quatre, huit", "1 2 3 4", "1234"):
            self.assertNotIn(dit, tout, "le code ne part jamais")
        self.assertNotIn("4815", json.dumps(self.m.CFG), "on ne garde que l'empreinte")

    def test_dix_minutes_ouvert_puis_verrouille(self):
        envoyes, maison = self.mains([self.outil("lister_dossier", {"chemin": "Documents"}),
                                      {"texte": "Un dossier, vide.", "mode": "jarvis"},
                                      self.outil("lister_dossier", {"chemin": "~"}, "t2"),
                                      {"texte": "Voila.", "mode": "jarvis"},
                                      self.outil("lister_dossier", {"chemin": "~"}, "t3")])
        self.phrase("Jarvis, qu'est-ce qu'il y a dans mes documents ?")
        self.phrase("4 8 1 5")
        self.assertEqual(self.dit[-1], "Un dossier, vide.")
        # la session est ouverte : pas de code a la seconde
        self.phrase("Jarvis, et dans mon dossier ?")
        self.assertEqual(self.dit[-1], "Voila.")
        self.assertIn("Documents", envoyes[3]["resultats"][0]["texte"])
        # « verrouille » : on redemande
        self.phrase("Jarvis, verrouille.")
        self.assertEqual(self.dit[-1], "Accès verrouillé.")
        self.phrase("Jarvis, et dans mon dossier ?")
        self.assertEqual(self.dit[-1], "Code d'accès ?")

    def test_trois_codes_faux_ferment_cinq_minutes(self):
        envoyes, _ = self.mains([self.outil("ouvrir", {"chemin": "Documents"}),
                                 self.outil("ouvrir", {"chemin": "Documents"}, "t2"),
                                 {"texte": "L'accès est verrouillé pour l'instant.", "mode": "jarvis"}])
        self.phrase("Jarvis, ouvre mes documents")
        for faux in ("1111", "2222", "3333"):
            self.phrase(faux)
        self.assertEqual(self.dit[-1], "Accès refusé.")
        self.assertIsNone(self.m.JARVIS["attente_code"])
        self.phrase("Jarvis, ouvre mes documents")
        self.assertIn("verrouille", envoyes[-1]["resultats"][0]["erreur"])
        self.assertNotEqual(self.dit[-1], "Code d'accès ?", "verrouille : il ne redemande pas")

    def test_sans_code_regle_les_fichiers_restent_fermes(self):
        envoyes, maison = self.mains([self.outil("creer_dossier", {"chemin": "Documents\\X"}),
                                      {"texte": "Il me faut d'abord un code d'accès.", "mode": "jarvis"}], code="")
        self.phrase("Jarvis, crée un dossier X dans mes documents")
        self.assertIn("Aucun code", envoyes[1]["resultats"][0]["erreur"])
        self.assertFalse(os.path.exists(os.path.join(maison, "Documents", "X")))

    def test_sans_code_par_defaut_il_agit_directement(self):
        # « Faire en sorte qu'il n'y ait plus de code d'acces a demander. »
        self.assertFalse(self.m.CONFIG_DEFAUT["jarvis_code_actif"])
        envoyes, maison = self.mains([self.outil("creer_dossier", {"chemin": "Documents\\Direct"}),
                                      {"texte": "C'est fait.", "mode": "jarvis"}], code_actif=False)
        self.phrase("Jarvis, crée un dossier Direct dans mes documents")
        self.assertNotIn("Code d'accès ?", self.dit)
        self.assertTrue(os.path.isdir(os.path.join(maison, "Documents", "Direct")))
        self.assertEqual(self.dit[-1], "C'est fait.")

    def test_la_musique_sans_code(self):
        envoyes, _ = self.mains([self.outil("musique", {"action": "suivant"}),
                                 {"texte": "Piste suivante.", "mode": "jarvis"}])
        self.phrase("Jarvis, musique suivante")
        self.assertEqual(envoyes[1]["resultats"][0]["texte"], "Piste suivante.")
        self.assertNotIn("Code d'accès ?", self.dit)

    def test_l_ecran_seulement_s_il_est_permis(self):
        envoyes, _ = self.mains([self.outil("regarder_ecran", {"ecran": 2}),
                                 {"texte": "Vous perdez, et avec panache.", "mode": "jarvis"}], ecran=True)
        self.phrase("Jarvis, regarde mon écran 2")
        self.assertTrue(envoyes[0]["ecran"])
        self.phrase("4815")
        self.assertEqual(envoyes[1]["resultats"][0]["image"], "QUJD")
        self.assertEqual(self.dit[-1], "Vous perdez, et avec panache.")
        # les deux d'un coup : « plutot que demander ce que vous faites »
        r = self.m.executer_outil({"id": "x", "nom": "regarder_ecran", "entree": {"ecran": 0}}, self.m.CFG)
        self.assertEqual(r["images"], ["QUFB", "QUJD"])
        self.assertIn("ecran 1, ecran 2", r["texte"])
        r = self.m.executer_outil({"id": "x", "nom": "regarder_ecran", "entree": {}}, self.m.CFG)
        self.assertEqual(len(r["images"]), 2, "sans numero : les deux")
        # l'ecran decoche : meme demande, refus
        self.m.CFG["jarvis_ecran"] = False
        self.assertIn("pas permis", self.m.executer_outil({"id": "x", "nom": "regarder_ecran", "entree": {}},
                                                          self.m.CFG)["erreur"])

    def test_sans_les_mains_rien_ne_s_execute(self):
        envoyes, maison = self.mains([self.outil("creer_dossier", {"chemin": "Documents\\Y"}),
                                      {"texte": "Mes mains sont fermées.", "mode": "jarvis"}])
        self.m.CFG["jarvis_pc"] = False
        self.phrase("Jarvis, crée un dossier Y")
        self.assertFalse(envoyes[0]["outils"])
        self.assertFalse(os.path.exists(os.path.join(maison, "Documents", "Y")))
        self.assertIn("fermees", envoyes[1]["resultats"][0]["erreur"])
        self.assertFalse(envoyes[1]["outils"], "la suite ne rouvre pas les mains")
        self.assertEqual(self.dit[-1], "Mes mains sont fermées.")

    def test_il_retient_une_preference_meme_sans_les_mains(self):
        # « Il faudrait que Jarvis retienne des preferences. »
        envoyes, _ = self.mains([self.outil("retenir", {"preference": "Prefere les reponses courtes."}),
                                 {"texte": "Noté.", "mode": "jarvis"},
                                 {"texte": "Bien sûr.", "mode": "jarvis"},
                                 self.outil("oublier", {"preference": "reponses courtes"}, "t2"),
                                 {"texte": "Oublié.", "mode": "jarvis"}])
        self.m.CFG["jarvis_pc"] = False
        self.phrase("Jarvis, retiens que je préfère les réponses courtes")
        self.assertTrue(envoyes[0]["memoire"])
        self.assertEqual(envoyes[0]["preferences"], [])
        self.assertEqual(self.m.CFG["jarvis_preferences"], ["Prefere les reponses courtes."])
        self.assertIn("Retenu", envoyes[1]["resultats"][0]["texte"])
        self.assertEqual(envoyes[1]["preferences"], ["Prefere les reponses courtes."])
        self.assertEqual(self.dit[-1], "Noté.")
        self.phrase("Jarvis, tu peux m'aider ?")
        self.assertEqual(envoyes[2]["preferences"], ["Prefere les reponses courtes."], "elle part avec chaque question")
        self.phrase("Jarvis, oublie que je préfère les réponses courtes")
        self.assertEqual(self.m.CFG["jarvis_preferences"], [])
        self.assertEqual(self.dit[-1], "Oublié.")

    def test_google_et_les_liens_dans_chrome(self):
        m = self.m
        ouverts = []
        vrai = m.ouvrir_dans_chrome
        self.addCleanup(lambda: setattr(m, "ouvrir_dans_chrome", vrai))
        m.ouvrir_dans_chrome = lambda url: ouverts.append(url) or "Chrome"
        envoyes, _ = self.mains([self.outil("rechercher_google", {"recherche": "météo Lyon demain"}),
                                 {"texte": "C'est ouvert.", "mode": "jarvis"}])
        self.phrase("Jarvis, cherche la météo de Lyon demain sur Google")
        self.assertEqual(ouverts, ["https://www.google.com/search?q=m%C3%A9t%C3%A9o+Lyon+demain"])
        self.assertNotIn("Code d'accès ?", self.dit, "ouvrir une recherche ne demande pas de code")
        ex = lambda e: m.executer_outil({"id": "x", "nom": "lien", "entree": e}, m.CFG)
        self.assertIn("Ouvert", ex({"url": "https://www.youtube.com/watch?v=abc"})["texte"])
        self.assertIn("refusee", ex({"url": "file:///C:/Windows/system32/cmd.exe"})["erreur"])
        self.assertIn("refusee", ex({"url": "javascript:alert(1)"})["erreur"])
        self.assertEqual(ouverts[-1], "https://www.youtube.com/watch?v=abc")
        m.CFG["jarvis_pc"] = False
        self.assertIn("fermees", ex({"url": "https://exemple.fr"})["erreur"])

    def test_l_historique_seulement_s_il_est_coche(self):
        m = self.m
        envoyes, _ = self.mains([{"texte": "Bonjour.", "mode": "jarvis"}, {"texte": "Bonjour.", "mode": "jarvis"}],
                                code_actif=False)
        self.phrase("Jarvis, bonjour")
        self.assertFalse(envoyes[0]["navigation"])
        m.CFG["jarvis_historique"] = True
        self.phrase("Jarvis, bonjour")
        self.assertTrue(envoyes[1]["navigation"])
        vrai = m._jv.fichiers_historique
        self.addCleanup(lambda: setattr(m._jv, "fichiers_historique", vrai))
        m._jv.fichiers_historique = lambda env=None: []
        r = m.executer_outil({"id": "x", "nom": "chercher_historique", "entree": {"recherche": "chat"}}, m.CFG)
        self.assertIn("Aucun historique", r["texte"])
        m.CFG["jarvis_historique"] = False
        r = m.executer_outil({"id": "x", "nom": "chercher_historique", "entree": {"recherche": "chat"}}, m.CFG)
        self.assertIn("pas permis", r["erreur"])

    def test_chercher_affiner_ouvrir(self):
        m = self.m
        ouverts = []
        vrai = getattr(os, "startfile", None)
        os.startfile = ouverts.append
        self.addCleanup(lambda: setattr(os, "startfile", vrai) if vrai else delattr(os, "startfile"))
        envoyes, maison = self.mains([], code_actif=False)
        docs = os.path.join(maison, "Documents")
        for i in range(14):
            open(os.path.join(docs, "unit %02d.txt" % i), "w").close()
        os.makedirs(os.path.join(docs, "Stage"))
        for n in ("unit rapport.pdf", "unit notes.txt"):
            open(os.path.join(docs, "Stage", n), "w").close()
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        self.assertIn("16 resultats", ex("chercher_fichiers", {"mots": "unit", "dans": "Documents"})["texte"])
        self.assertIn("trop pour tout ouvrir", ex("ouvrir_resultats", {})["erreur"])
        self.assertEqual(ouverts, [])
        self.assertIn("2 resultats", ex("affiner_recherche", {"ajouter": "stage"})["texte"])
        self.assertIn("Ouverts", ex("ouvrir_resultats", {})["texte"])
        self.assertEqual(sorted(os.path.basename(o) for o in ouverts), ["unit notes.txt", "unit rapport.pdf"])
        self.assertIn("1 resultat ", ex("affiner_recherche", {"type": "pdf"})["texte"])
        self.assertIn("pas de numero 4", ex("ouvrir_resultats", {"numeros": [4]})["erreur"])
        self.assertIn("16 resultats", ex("affiner_recherche", {"retirer": "stage", "type": ""})["texte"])
        self.assertIn("unit 00.txt", ex("chercher_fichiers", {"nom": "unit 00", "dans": "Documents"})["texte"],
                      "l'ancien parametre « nom » marche encore")

    def test_je_reste_a_l_ecoute(self):
        # « ... ou demande meme au bout d'un moment : je dois me desactiver ? »
        m = self.m
        ordres = []
        vrais = (m.oreille_vivante, m._en_fond)
        self.addCleanup(lambda: (setattr(m, "oreille_vivante", vrais[0]), setattr(m, "_en_fond", vrais[1])))
        m.oreille_vivante, m._en_fond = (lambda: True), (lambda f: None)
        m.envoyer_oreille = lambda o: ordres.append(o) or True
        m.CFG["jarvis_langue"] = "fr"
        vus = self.espions()
        m.JARVIS["historique"] = [{"role": "user", "texte": "a"}, {"role": "assistant", "texte": "b"}] * 3
        # « rend-le plus fluide » : devoir redire « Jarvis » a chaque phrase --
        # il ecoute la suite apres chaque reponse, compte a rebours au panneau
        m.dire("Voila ce que j'en pense.", suite=True)
        self.assertEqual([o for o in ordres if o.get("cmd") == "ecouter"][-1]["attente"], 6.0)
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        self.assertGreater(m.JARVIS["ecoute_fin"], time.time())
        m.traiter_evenement({"evt": "vide"})
        # ... ou, si on le prefere, seulement apres une question
        m.CFG["jarvis_suite_questions"] = True
        self.addCleanup(lambda: m.CFG.pop("jarvis_suite_questions", None))
        del ordres[:]
        m.dire("Voila ce que j'en pense.", suite=True)
        self.assertEqual([o for o in ordres if o.get("cmd") == "ecouter"], [])
        self.assertEqual(m.JARVIS["etat"], "attente")
        m.dire("Voila ce que j'en pense. On essaie ?", suite=True)
        attente = [o for o in ordres if o.get("cmd") == "ecouter"][-1]["attente"]
        self.assertEqual(attente, 10.0, "une question, trois echanges : il ecoute un peu plus longtemps")
        self.assertGreater(m.JARVIS["ecoute_fin"], time.time(), "le compte a rebours du panneau")
        # « make it easier to leave Jarvis » : le silence suffit -- pas de question
        n = len(self.dit)
        m.traiter_evenement({"evt": "vide"})
        self.assertEqual(len(self.dit), n, "il se rendort sans un mot")
        self.assertEqual(m.JARVIS["etat"], "attente")
        # « ok merci » apres une reponse : fini, rien ne part au modele
        m.dire("Il est 14 h.", suite=True)
        self.phrase("ok merci")
        self.assertEqual(vus["jarvis"], [], "« ok » ne part pas au modele")
        self.assertEqual(m.JARVIS["historique"], [], "la conversation est close")
        # ... mais apres une question, « ok » est un oui
        m.dire("Je lance la playlist ?", suite=True)
        self.phrase("ok")
        self.assertEqual(vus["jarvis"], ["ok"])

    def test_les_discussions_vont_au_journal(self):
        # « Fait en sorte que les discussions de Jarvis aillent aussi dans le journal ! »
        m = self.m
        vrais = (m._en_fond, m._requete_bd)
        self.addCleanup(lambda: (setattr(m, "_en_fond", vrais[0]), setattr(m, "_requete_bd", vrais[1])))
        m._en_fond = lambda f: f()
        envoyes, reponses = [], []

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            envoyes.append((chemin, json.loads(json.dumps(charge))))
            if chemin == "/api/machitool/journal":
                return {"ok": True}
            return reponses.pop(0)
        m._requete_bd = bd
        m.CFG["jarvis_journal"] = True
        reponses += [{"texte": "Gris et doux, Monsieur.", "mode": "jarvis"}]
        self.phrase("Jarvis, quel temps fait-il à Nantes ?")
        journal = [c for chemin, c in envoyes if chemin == "/api/machitool/journal"]
        self.assertEqual(journal, [{"dit": "quel temps fait-il à Nantes ?", "repondu": "Gris et doux, Monsieur."}])
        # le grave part au compagnon, qui le range lui-meme : rien de plus
        reponses += [{"texte": "Je suis la.", "mode": "psy"}]
        self.phrase("Jarvis, je n'en peux plus")
        self.assertEqual(len([1 for chemin, _ in envoyes if chemin == "/api/machitool/journal"]), 1)
        # decoche : plus rien
        m.poser_mode("jarvis")
        m.CFG["jarvis_journal"] = False
        reponses += [{"texte": "Il est midi.", "mode": "jarvis"}]
        self.phrase("Jarvis, quelle heure est-il ?")
        self.assertEqual(len([1 for chemin, _ in envoyes if chemin == "/api/machitool/journal"]), 1)
        self.assertFalse(m.verser_au_journal("x", "y", m.CFG))
        # un BrainDebugger d'avant (404) : rien ne casse, rien a voix haute
        m.CFG["jarvis_journal"] = True

        def ancien(chemin, charge, cfg, delai, sur_debut=None):
            raise m.urllib.error.HTTPError(chemin, 404, "Not Found", {}, None)
        m._requete_bd = ancien
        self.assertTrue(m.verser_au_journal("x", "y", m.CFG))
        # il peut le changer, mais la personne confirme
        self.assertIn("jarvis_journal", J.REGLAGES_POUVOIRS)

    def test_il_se_souvient_de_vos_conversations(self):
        # « Il faut que Jarvis se souvienne des anciennes discussions, mais simplement. »
        m = self.m
        vrais = (m._en_fond, m._requete_bd)
        self.addCleanup(lambda: (setattr(m, "_en_fond", vrais[0]), setattr(m, "_requete_bd", vrais[1])))
        m._en_fond = lambda f: f()
        envoyes, reponses = [], []

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            envoyes.append(json.loads(json.dumps(charge)))
            return reponses.pop(0)
        m._requete_bd = bd
        m.CFG["jarvis_souvenirs"] = []
        reponses += [{"texte": "Un italien ouvert lundi ? Aucun, je le crains.", "mode": "jarvis"},
                     {"texte": "A cherche un restaurant italien ouvert le lundi a Lyon, sans succes."}]
        self.phrase("Jarvis, un italien ouvert lundi à Lyon ?")
        self.assertEqual(envoyes[0]["souvenirs"], [])
        self.phrase("Jarvis, non rien, merci")          # fin de la conversation
        self.assertEqual(envoyes[1]["transition"], "resume")
        self.assertEqual([h["role"] for h in envoyes[1]["historique"]], ["user", "assistant"])
        self.assertEqual(len(m.CFG["jarvis_souvenirs"]), 1)
        self.assertEqual(m.CFG["jarvis_souvenirs"][0]["texte"],
                         "A cherche un restaurant italien ouvert le lundi a Lyon, sans succes.")
        reponses += [{"texte": "Mardi, oui : Da Marco.", "mode": "jarvis"}]
        self.phrase("Jarvis, et mardi ?")
        self.assertRegex(envoyes[2]["souvenirs"][0], r"^\d\d/\d\d : A cherche un restaurant italien")
        # rien a retenir : pas de souvenir vide
        reponses += [{"texte": ""}]
        m.clore_historique()
        self.assertEqual(len(m.CFG["jarvis_souvenirs"]), 1)
        # grave : bascule au compagnon, et cette conversation-la n'est pas resumee
        reponses += [{"texte": "Je suis la.", "mode": "psy"}]
        n = len(envoyes)
        self.phrase("Jarvis, je n'en peux plus")
        self.assertEqual(len(envoyes), n + 1, "aucune demande de resume")
        self.assertEqual(m.JARVIS["historique"], [])
        # le mode psychologue ne laisse pas de souvenir
        m.JARVIS["historique"] = [{"role": "user", "texte": "x"}]
        m.clore_historique()
        self.assertEqual(len(envoyes), n + 1)
        # SOUVENIRS_MAX au plus (40), SOUVENIRS_ENVOYES envoyes (20)
        n_max = m.SOUVENIRS_MAX
        m.CFG["jarvis_souvenirs"] = [{"date": "2026-09-%02d" % (1 + i % 28), "texte": "s%d" % i}
                                     for i in range(n_max)]
        m.JARVIS["mode"] = "jarvis"
        m.JARVIS["historique"] = [{"role": "user", "texte": "y"}]
        reponses += [{"texte": "Nouveau."}]
        m.clore_historique()
        self.assertEqual(len(m.CFG["jarvis_souvenirs"]), n_max)
        self.assertEqual(m.CFG["jarvis_souvenirs"][-1]["texte"], "Nouveau.")
        self.assertEqual(len(m.capacites_jarvis(m.CFG)["souvenirs"]), m.SOUVENIRS_ENVOYES)
        r = m.executer_outil({"id": "x", "nom": "oublier", "entree": {"conversations": True}}, m.CFG)
        self.assertIn("%d souvenirs" % n_max, r["texte"])
        self.assertEqual(m.CFG["jarvis_souvenirs"], [])

    def test_les_onglets_par_l_extension(self):
        # « Il faut qu'il puisse fermer ou ouvrir des onglets. »
        m = self.m
        envoyes, _ = self.mains([], code_actif=False)
        ex = lambda e: m.executer_outil({"id": "x", "nom": "onglets", "entree": e}, m.CFG)
        m.ONGLETS.update(file=[], resultats={}, vu=0.0)
        self.assertIn("pas branchee", ex({"action": "lister"})["erreur"])
        self.assertFalse(m.capacites_jarvis(m.CFG)["onglets"])
        onglets = [{"id": 11, "titre": "Lo-fi beats - YouTube", "url": "https://www.youtube.com/watch?v=a", "son": True},
                   {"id": 12, "titre": "Vaporwave mix - YouTube", "url": "https://www.youtube.com/watch?v=b"},
                   {"id": 13, "titre": "Boîte de réception", "url": "https://mail.google.com/mail/u/0/#inbox"}]
        recu, arret = [], threading.Event()

        def extension():                         # ce que fait fond.js, sans Chrome
            while not arret.is_set():
                c = m.prochaine_commande_onglets(0.2)
                if c is None:
                    continue
                recu.append(c)
                if c["action"] == "lister":
                    m.resultat_onglets({"id": c["id"], "onglets": onglets})
                elif c["action"] == "fermer" and 99 in c["ids"]:
                    m.resultat_onglets({"id": c["id"], "erreur": "No tab with id: 99."})
                else:
                    m.resultat_onglets({"id": c["id"], "texte": "fait"})
        t = threading.Thread(target=extension, daemon=True)
        t.start()
        self.addCleanup(lambda: (arret.set(), t.join(2)))
        time.sleep(0.3)
        self.assertTrue(m.capacites_jarvis(m.CFG)["onglets"], "l'extension demande : elle est branchee")
        l = ex({"action": "lister"})["texte"]
        self.assertTrue(l.startswith("3 onglets. YouTube (2) : « Lo-fi beats - YouTube » -- joue du son"), l)
        self.assertIn("| Mails (1) : « Boîte de réception » (mail.google.com)", l)
        self.assertTrue(m.onglets_du_moment().startswith("3 onglets. YouTube (2) : « Lo-fi beats"))
        self.assertNotIn("#inbox", l, "vers Jarvis : le domaine, pas l'adresse")
        self.assertIn("Ferme", ex({"action": "fermer", "cible": "youtube", "tous": True})["texte"])
        self.assertEqual(sorted(recu[-1]["ids"]), [11, 12])
        ex({"action": "fermer", "cible": "vaporwave"})
        self.assertEqual(recu[-1]["ids"], [12])
        ex({"action": "couper_son", "cible": "lo-fi"})
        self.assertEqual((recu[-1]["action"], recu[-1]["ids"], recu[-1]["muet"]), ("muet", [11], True))
        self.assertIn("Nouvel onglet : google.com", ex({"action": "ouvrir", "recherche": "meteo Lyon"})["texte"])
        self.assertTrue(recu[-1]["url"].startswith("https://www.google.com/search?q="))
        n = len(recu)
        self.assertIn("http(s)", ex({"action": "ouvrir", "url": "file:///C:/x"})["erreur"])
        self.assertEqual(len(recu), n, "une adresse refusee ne part pas a Chrome")
        self.assertIn("Aucun onglet", ex({"action": "fermer", "cible": "twitch"})["erreur"])

    def test_ecrire_des_fichiers_neufs_et_des_notes(self):
        # « Est-ce possible que Jarvis puisse ecrire dans un bloc-notes, ou creer des fichiers ? »
        d = tempfile.mkdtemp()
        try:
            c = self.m.creer_fichier(os.path.join(d, "courses"), "pain\nlait")
            self.assertEqual(os.path.basename(c), "courses.txt", "sans extension : du texte")
            self.assertIn("lait", open(c, encoding="utf-8-sig").read())
            c2 = self.m.creer_fichier(os.path.join(d, "courses.txt"), "autre chose")
            self.assertEqual(os.path.basename(c2), "courses (2).txt")
            self.assertIn("pain", open(c, encoding="utf-8-sig").read(), "jamais par-dessus un fichier existant")
            for ext in (".bat", ".cmd", ".ps1", ".vbs", ".js", ".py", ".exe", ".lnk", ".reg", ".hta", ".scr", ".url"):
                with self.assertRaises(PermissionError, msg=ext):
                    self.m.creer_fichier(os.path.join(d, "x" + ext), "echo")
            self.assertEqual(sorted(os.listdir(d)), ["courses (2).txt", "courses.txt"], "aucun script n'a ete ecrit")
            self.assertEqual(os.path.basename(self.m.creer_fichier(os.path.join(d, 'a:b*c?.md'), "# t")), "a b c.md")
            with self.assertRaises(PermissionError):
                self.m.creer_fichier(os.path.join(d, "Windows", "x.txt"), "x", [os.path.join(d, "Windows")])
            with self.assertRaises(ValueError):
                self.m.creer_fichier(os.path.join(d, "gros.txt"), "x" * (J.ECRIT_MAX + 1))
            notes = os.path.join(d, "Notes de Jarvis")
            n1, neuve = self.m.ecrire_note(notes, "Appeler le garagiste.", "Idées de la semaine")
            self.assertTrue(neuve)
            self.assertEqual(os.path.basename(n1), "Idées de la semaine.txt")
            n2, neuve = self.m.ecrire_note(notes, "Acheter des ampoules.", ajouter_a="idees semaine")
            self.assertFalse(neuve)
            self.assertEqual(n1, n2)
            contenu = open(n1, encoding="utf-8-sig").read()
            self.assertLess(contenu.index("garagiste"), contenu.index("ampoules"), "ajoute a la fin")
            n3, _ = self.m.ecrire_note(notes, "Sans titre.", maintenant=time.mktime((2026, 9, 25, 14, 30, 0, 0, 0, -1)))
            self.assertEqual(os.path.basename(n3), "Note du 2026-09-25 14h30.txt")
            with self.assertRaisesRegex(LookupError, "Idées de la semaine"):
                self.m.ecrire_note(notes, "x", ajouter_a="liste de noel")
            with self.assertRaises(ValueError):
                self.m.ecrire_note(notes, "   ")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_note_que_passe_par_jarvis_si_ses_mains_sont_ouvertes(self):
        # « Rajoute bien le mode ecrire une note, qui fait que Jarvis envoie une
        # note au psychologue automatiquement. »
        vus = self.espions()
        self.m.CFG["jarvis_pc"] = True
        self.phrase("Jarvis, note que je me suis senti fier de ma présentation")
        self.assertEqual(vus["psy"], [])
        self.assertEqual(vus["jarvis"], ["note que je me suis senti fier de ma présentation"])
        self.assertEqual(self.m.JARVIS["mode"], "jarvis")
        self.phrase("Jarvis, note pour le psy : j'ai bien dormi")
        self.assertEqual(len(vus["psy"]), 1, "« note pour le psy » : directement au psychologue")
        for t in ("note que j'ai rendez-vous", "prends une note", "écris une note"):
            self.assertTrue(J.note_a_ecrire(t), t)
        for t in ("notes psy", "note pour le psy : ça va", "je note que ça va mieux"):
            self.assertFalse(J.note_a_ecrire(t), t)

    def test_une_note_dans_le_bloc_notes(self):
        m = self.m
        ouverts = []
        vrai = getattr(os, "startfile", None)
        os.startfile = ouverts.append
        self.addCleanup(lambda: setattr(os, "startfile", vrai) if vrai else delattr(os, "startfile"))
        envoyes, maison = self.mains([self.outil("ecrire_note", {"texte": "Rappeler Paul.", "titre": "A faire"}),
                                      {"texte": "C'est noté.", "mode": "jarvis"}], code_actif=False)
        self.phrase("Jarvis, note que je dois rappeler Paul")
        note = os.path.join(maison, "Documents", "Notes de Jarvis", "A faire.txt")
        self.assertTrue(os.path.isfile(note))
        self.assertEqual(ouverts, [note], "la note s'ouvre dans le bloc-notes")
        self.assertIn("Note ecrite", envoyes[1]["resultats"][0]["texte"])
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        r = ex("creer_fichier", {"chemin": "Documents\\liste.csv", "contenu": "a;b"})
        self.assertIn("liste.csv", r["texte"])
        self.assertIn("PermissionError", ex("creer_fichier", {"chemin": "Documents\\x.bat", "contenu": "del *"})["erreur"])
        self.assertFalse(os.path.exists(os.path.join(maison, "Documents", "x.bat")))
        m.CFG["jarvis_pc"] = False
        self.assertIn("fermees", ex("ecrire_note", {"texte": "x"})["erreur"])

    def test_youtube_sans_passer_par_le_modele(self):
        m = self.m
        ouvertes = []
        vrai = m.ouvrir_youtube
        self.addCleanup(lambda: setattr(m, "ouvrir_youtube", vrai))
        m.ouvrir_youtube = lambda q: ouvertes.append(q) or "Video ouverte dans Chrome : « x »."
        envoyes, _ = self.mains([], code_actif=False)
        self.phrase("Jarvis, mets-moi Get Lucky sur YouTube")
        self.assertEqual(ouvertes, ["get lucky"])
        self.assertEqual(envoyes, [], "rien ne part au modele")
        self.assertEqual(self.dit[-1], "C'est lancé.")
        m.CFG["jarvis_pc"] = False
        self.phrase("Jarvis, lance la vidéo de chat qui joue du piano sur YouTube")
        self.assertEqual(len(ouvertes), 1, "mains fermees : rien ne s'ouvre")
        self.assertIn("fermées", self.dit[-1])

    def test_ferme_a_gauche_a_droite_garde(self):
        m = self.m
        envoyes, _ = self.mains([], code_actif=False)
        onglets = [
            {"id": 1, "titre": "Epingle", "url": "https://a.fr", "position": 0, "epingle": True, "fenetre_courante": True},
            {"id": 2, "titre": "Reddit Unity", "url": "https://www.reddit.com/r/unity3d", "position": 1, "fenetre_courante": True},
            {"id": 3, "titre": "Doc Python", "url": "https://docs.python.org", "position": 2, "actif": True, "fenetre_courante": True},
            {"id": 4, "titre": "Lo-fi - YouTube", "url": "https://www.youtube.com/watch?v=a", "position": 3, "fenetre_courante": True},
            {"id": 5, "titre": "Vaporwave - YouTube", "url": "https://www.youtube.com/watch?v=b", "position": 4, "fenetre_courante": True},
            {"id": 6, "titre": "Autre fenetre", "url": "https://b.fr", "position": 0, "actif": True, "fenetre_courante": False}]
        a_fermer = lambda action, gardes=None: sorted(J.onglets_a_fermer(onglets, action, gardes))
        self.assertEqual(a_fermer("fermer_gauche"), [2], "jamais l'epingle, jamais l'autre fenetre")
        self.assertEqual(a_fermer("fermer_droite"), [4, 5])
        self.assertEqual(a_fermer("garder"), [2, 4, 5], "garde cet onglet")
        self.assertEqual(a_fermer("garder", [onglets[3], onglets[4]]), [2, 3])
        fermes, arret = [], threading.Event()

        def extension():
            while not arret.is_set():
                c = m.prochaine_commande_onglets(0.2)
                if c is None:
                    continue
                if c["action"] == "fermer":
                    fermes.append(sorted(c["ids"]))
                m.resultat_onglets({"id": c["id"], "onglets": onglets} if c["action"] == "lister"
                                   else {"id": c["id"], "texte": "fait"})
        t = threading.Thread(target=extension, daemon=True)
        t.start()
        self.addCleanup(lambda: (arret.set(), t.join(2)))
        time.sleep(0.3)
        ex = lambda e: m.executer_outil({"id": "x", "nom": "onglets", "entree": e}, m.CFG)
        self.assertEqual(ex({"action": "garder", "cible": "youtube"})["texte"], "2 onglets fermes.")
        self.assertEqual(fermes[-1], [2, 3])
        n = len(fermes)
        self.assertIn("je n'en ferme aucun", ex({"action": "garder", "cible": "twitch"})["erreur"])
        self.assertEqual(len(fermes), n, "rien ne correspond : rien n'est ferme")
        ex({"action": "fermer_droite"})
        self.assertEqual(fermes[-1], [4, 5])

    def test_l_extension_et_ses_routes(self):
        m = self.m
        dossier = m.preparer_extension(m.CFG, os.path.join(self.tmp, "ext-%d" % id(self)))
        cle = m.CFG["onglets_cle"]
        self.assertTrue(cle)
        manifeste = json.load(open(os.path.join(dossier, "manifest.json"), encoding="utf-8"))
        self.assertEqual(manifeste["manifest_version"], 3)
        self.assertEqual(sorted(manifeste["permissions"]), ["alarms", "tabs"], "rien de plus que les onglets")
        self.assertEqual(manifeste["host_permissions"], ["http://127.0.0.1/*"])
        self.assertIn(json.dumps(cle), open(os.path.join(dossier, "config.js"), encoding="utf-8").read())
        if shutil.which("node"):
            r = subprocess.run(["node", "--check", os.path.join(dossier, "fond.js")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        vrai = m.ONGLETS_ATTENTE_S
        m.ONGLETS_ATTENTE_S = 0.2
        self.addCleanup(lambda: setattr(m, "ONGLETS_ATTENTE_S", vrai))
        m.ONGLETS.update(file=[], resultats={}, vu=0.0)
        serveur = m.http.server.ThreadingHTTPServer(("127.0.0.1", 0), m.Passerelle)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (serveur.shutdown(), serveur.server_close()))
        base = "http://127.0.0.1:%d/onglets/" % serveur.server_address[1]

        def appel(chemin, entetes, corps=None):
            req = urllib.request.Request(base + chemin, data=json.dumps(corps).encode() if corps else None,
                                         headers=entetes, method="POST" if corps else "GET")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        self.assertEqual(appel("attente", {})[0], 401)
        self.assertEqual(appel("attente", {"X-Onglets-Cle": "faux"})[0], 401)
        self.assertEqual(appel("attente", {"X-Onglets-Cle": cle, "Origin": "https://site-quelconque.fr"})[0], 401,
                         "une page web ne se fait pas passer pour l'extension")
        self.assertEqual(appel("attente", {"X-Onglets-Cle": cle, "Origin": "chrome-extension://abc"})[0], 204)
        self.assertTrue(m.extension_branchee())
        resultat = {}
        t = threading.Thread(target=lambda: resultat.update(r=m.commande_onglets("lister", delai=3)))
        t.start()
        statut, corps = appel("attente", {"X-Onglets-Cle": cle})
        self.assertEqual(statut, 200)
        c = json.loads(corps)
        self.assertEqual(c["action"], "lister")
        self.assertEqual(appel("resultat", {"X-Onglets-Cle": cle, "Content-Type": "application/json"},
                               {"id": c["id"], "onglets": []})[0], 200)
        t.join(3)
        self.assertEqual(resultat["r"]["onglets"], [])

    def test_le_retour_de_connexion_oauth(self):
        m = self.m
        recus, messages = [], []
        t = m.attendre_retour_oauth("ETAT", recus.append, messages.append, delai=5, service="Spotify")
        base = "http://127.0.0.1:%d/callback" % m._jv.SPOTIFY_PORT
        lire = lambda q: urllib.request.urlopen(base + q, timeout=5).read().decode("utf-8")
        self.assertIn("Reponse inattendue", lire("?state=AUTRE&code=X"))
        self.assertEqual(recus, [], "un « state » etranger : aucun echange")
        self.assertIn("Spotify est connecte", lire("?state=ETAT&code=CODE"))
        t.join(3)
        self.assertEqual(recus, ["CODE"])
        self.assertFalse(t.is_alive(), "une fois connecte, le serveur s'arrete")

    def test_les_temperatures_dans_machi_tool(self):
        m = self.m
        vrais = (m.memoire_coretemp, m.sortie_nvidia_smi, m.capteurs_wmi)
        self.addCleanup(lambda: (setattr(m, "memoire_coretemp", vrais[0]), setattr(m, "sortie_nvidia_smi", vrais[1]),
                                 setattr(m, "capteurs_wmi", vrais[2])))
        m.memoire_coretemp, m.sortie_nvidia_smi = (lambda: None), (lambda: "RTX 3070, 71, 98, 7000, 8192")
        m.capteurs_wmi = lambda: []
        envoyes, _ = self.mains([self.outil("temperatures", {}), {"texte": "71 degres, elle travaille.", "mode": "jarvis"}])
        self.phrase("Jarvis, elle chauffe ma carte graphique ?")
        self.assertNotIn("Code d'accès ?", self.dit, "lire des temperatures ne demande pas de code")
        self.assertIn("RTX 3070, nvidia-smi) : 71 °C, charge 98 %", envoyes[1]["resultats"][0]["texte"])

    def test_il_dit_pourquoi_braindebugger_refuse(self):
        # « J'ai "BrainDebugger a repondu par une erreur 502" » : la cause, pas le numero.
        import urllib.error
        m = self.m
        vrai = m._requete_bd
        self.addCleanup(lambda: setattr(m, "_requete_bd", vrai))
        m.CFG["jarvis_langue"] = "fr"
        corps = {}

        def refus(chemin, charge, cfg, delai, sur_debut=None):
            raise urllib.error.HTTPError(chemin, 502, "Bad Gateway", {}, io.BytesIO(json.dumps(corps).encode()))
        m._requete_bd = refus
        corps.update(error="401 authentication_error: invalid x-api-key", raison="cle")
        self.phrase("Jarvis, raconte-moi une blague sur les pingouins")
        self.assertIn("refuse la clé API", m.JARVIS["message"])
        self.assertIn("ANTHROPIC_API_KEY", m.JARVIS["message"])
        corps.update(error="Your credit balance is too low", raison="credit")
        self.phrase("Jarvis, raconte-moi une blague sur les pingouins")
        self.assertEqual(m.JARVIS["message"], "Le crédit de la clé API Claude est épuisé.")
        corps.update(error="quelque chose d'inattendu", raison="autre")
        self.phrase("Jarvis, raconte-moi une blague sur les pingouins")
        # le detail brut du serveur ne se lit plus a voix haute : il est sur sa page
        self.assertEqual(m.JARVIS["message"], "BrainDebugger a répondu par une erreur 502.")
        self.assertIn("quelque chose d'inattendu", m.texte_derniere_erreur())
        corps.clear()
        self.phrase("Jarvis, raconte-moi une blague sur les pingouins")
        self.assertEqual(m.JARVIS["message"], "BrainDebugger a répondu par une erreur 502.", "un 502 de Railway, sans JSON")

    def test_baisse_spotify_sans_le_modele(self):
        m = self.m
        faits = []
        vrai = m.regler_son
        self.addCleanup(lambda: setattr(m, "regler_son", vrai))
        m.regler_son = lambda sens, cible, niveau: faits.append((sens, cible, niveau)) or "Volume de Spotify à 40 %."
        envoyes, _ = self.mains([], code_actif=True)
        self.phrase("Jarvis, baisse Spotify")
        self.phrase("Jarvis, coupe le jeu")
        self.assertEqual(faits, [("baisser", "spotify", None), ("couper", "le jeu", None)])
        self.assertEqual(envoyes, [], "rien ne part au modele")
        self.assertNotIn("Code d'accès ?", self.dit, "le son ne demande pas de code")
        m.regler_son = lambda *a: (_ for _ in ()).throw(LookupError("Rien ne fait du son sous ce nom (jeu) ; en ce moment : Spotify."))
        self.phrase("Jarvis, baisse le jeu")
        self.assertIn("Rien ne fait du son", self.dit[-1] if self.dit else m.JARVIS.get("message", ""))
        m.CFG["jarvis_pc"] = False
        n = len(faits)
        self.phrase("Jarvis, baisse Spotify")
        self.assertEqual(len(faits), n, "mains fermees : rien")

    def test_sa_reponse_va_au_panneau(self):
        m = self.m
        m.dire("Il fait 21 degrés à Lyon.")
        self.assertEqual(m.JARVIS["reponse_affichee"], "Il fait 21 degrés à Lyon.")
        # « que la petite bulle, plus la grande fenetre » : la boule seule, et sa legende
        self.assertFalse(m.CONFIG_DEFAUT["jarvis_panneau"])
        self.assertTrue(m.CONFIG_DEFAUT["jarvis_legende"])

    def test_oust_degage_casse_toi_il_part(self):
        # « Quand je dis oust, degage, casse-toi... il dit "oui" ou "je m'efface", mais reste. »
        m = self.m
        ordres = []
        vrais = (m.oreille_vivante, m._en_fond)
        self.addCleanup(lambda: (setattr(m, "oreille_vivante", vrais[0]), setattr(m, "_en_fond", vrais[1])))
        m.oreille_vivante, m._en_fond = (lambda: True), (lambda f: None)
        m.envoyer_oreille = lambda o: ordres.append(o) or True
        vus = self.espions()
        for dit in ("Oust !", "Dégage, Jarvis", "dégage jarvis", "Jarvis, casse-toi", "fous-moi la paix",
                    "laisse-moi tranquille", "tu peux disposer", "vas-y dégage"):
            ordres.clear()
            m.JARVIS["historique"] = [{"role": "user", "texte": "a"}, {"role": "assistant", "texte": "b"}]
            self.phrase(dit)
            self.assertIn({"cmd": "annuler"}, ordres, dit)
            self.assertNotIn("ecouter", [o.get("cmd") for o in ordres], dit + " : il n'ecoute plus")
            self.assertEqual(m.JARVIS["historique"], [], dit)
        self.assertEqual(vus["jarvis"], [], "rien de tout ca ne part au modele")
        self.assertNotIn("Oui ?", self.dit)
        # ce que Machi Tool ne reconnait pas : le modele se retire, et il part vraiment
        m.parler_a_jarvis = vrai_parler = self._origines["parler_a_jarvis"]
        envoyes, _ = self.mains([{"texte": "Je me retire.", "mode": "jarvis", "fin": True}], code_actif=False)
        m.envoyer_oreille = lambda o: ordres.append(o) or True
        ordres.clear()
        self.phrase("Jarvis, va donc jouer ailleurs, veux-tu")
        self.assertEqual(self.dit[-1], "Je me retire.")
        self.assertIn({"cmd": "annuler"}, ordres)
        self.assertNotIn("ecouter", [o.get("cmd") for o in ordres], "« je m'efface » et il reste : plus jamais")

    def test_jarvis_montre_l_agenda(self):
        # « L'agenda de Machi Tool pourra etre visible et montre par Jarvis (fenetre qui s'ouvre). »
        m = self.m
        envoyes, _ = self.mains([self.outil("montrer_agenda", {}), {"texte": "Le voici.", "mode": "jarvis"}])
        m.JARVIS["montrer_agenda"] = 0
        self.phrase("Jarvis, montre-moi mon agenda")
        self.assertTrue(envoyes[0]["fenetre_agenda"])
        self.assertNotIn("Code d'accès ?", self.dit)
        self.assertGreater(m.JARVIS["montrer_agenda"], 0, "la fenetre s'ouvrira au prochain passage de l'interface")
        self.assertEqual(envoyes[1]["resultats"][0]["texte"], "Agenda ouvert a l'ecran.")
        self.assertNotIn("agenda", m.capacites_jarvis(m.CFG), "plus de Google Agenda")
        vu = {}
        vrai = m._requete_bd
        self.addCleanup(lambda: setattr(m, "_requete_bd", vrai))
        m._requete_bd = lambda chemin, charge, cfg, delai, sur_debut=None: vu.update(chemin=chemin, charge=charge) or {"rendezVous": []}
        m.lire_agenda(m.CFG)
        self.assertRegex(vu["chemin"], r"^/api/machitool/agenda\?depuis=\d{4}-\d{2}-\d{2}&jours=14$")
        self.assertIsNone(vu["charge"], "une lecture : GET, sans corps")

    def test_le_pc_entier_sans_code(self):
        # « J'aimerais avoir un compagnon qui peut interagir le plus possible avec mon PC. »
        m = self.m
        lances = []
        vrai = getattr(os, "startfile", None)
        os.startfile = lances.append
        self.addCleanup(lambda: setattr(os, "startfile", vrai) if vrai else delattr(os, "startfile"))
        m._APPLIS.update(liste=[("ELDEN RING", "steam://rungameid/1245620", "jeu"),
                                ("Discord", "C:/Menu/Discord.lnk", "appli")], quand=time.time())
        envoyes, _ = self.mains([self.outil("lancer_appli", {"nom": "elden ring"}),
                                 {"texte": "Bon courage.", "mode": "jarvis"}])
        self.phrase("Jarvis, lance Elden Ring")
        self.assertEqual(lances, ["steam://rungameid/1245620"])
        self.assertNotIn("Code d'accès ?", self.dit, "lancer une appli ne demande pas de code")
        self.assertIn("Steam", envoyes[1]["resultats"][0]["texte"])
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        self.assertIn("Aucune appli", ex("lancer_appli", {"nom": "photoshop"})["erreur"])
        self.assertIn("pas connecte", ex("spotify_jouer", {"recherche": "get lucky"})["erreur"])
        self.assertFalse(envoyes[0]["spotify"])
        m.CFG.update(spotify_client_id="CID", spotify_refresh="R1")
        self.assertTrue(m.capacites_jarvis(m.CFG)["spotify"])
        m.CFG["jarvis_pc"] = False
        self.assertFalse(m.capacites_jarvis(m.CFG)["spotify"], "sans les mains, pas de Spotify")
        self.assertIn("fermees", ex("son", {"action": "couper"})["erreur"])

    def test_presque_reconnu_et_le_micro_de_l_apprentissage(self):
        m = self.m
        m.traiter_evenement({"evt": "presque", "distance": 0.07, "seuil": 0.05})
        self.assertEqual(m.JARVIS["presque"][:2], (0.07, 0.05))
        m.JARVIS["micro"] = "Micro casque"
        m.sauver_gabarits([[[0.1] * 96] * 6])
        self.assertEqual(m.micro_des_gabarits(), "Micro casque", "on sait avec quel micro on l'a appris")

    def test_claude_consulte_le_texte_complet_au_presse_papiers(self):
        copies = []
        vrai = self.m.copier_presse_papiers
        self.m.copier_presse_papiers = lambda t: copies.append(t) or True
        try:
            with mock_urlopen(self.m, {"texte": "Claude a écrit le script.", "mode": "jarvis",
                                       "detail": "import os\n# tout le script"}):
                self.phrase("Jarvis, demande à Claude un script pour renommer mes photos")
        finally:
            self.m.copier_presse_papiers = vrai
        self.assertEqual(copies, ["import os\n# tout le script"])
        self.assertIn("presse-papiers", " ".join(self.dit))
        self.assertIn("Claude a écrit le script.", self.dit)

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

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_capture_de_l_egaliseur_a_de_la_marge(self):
        # le journal : « data discontinuity in recording », 31 785 fois en 53 minutes -- le
        # tampon de Windows faisait la taille d'une lecture, le moindre retard jetait du son
        import types
        import warnings
        m = self.m
        ouverts, lus = [], []

        class Enregistreur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def record(self, numframes):
                lus.append(numframes)
                m.SON["marche"] = False
                return np.zeros((numframes, 2), dtype=np.float32)

        class Boucle:
            def recorder(self, samplerate, blocksize=None, **k):
                ouverts.append(blocksize)
                return Enregistreur()
        faux = types.SimpleNamespace(default_speaker=lambda: types.SimpleNamespace(name="Haut-parleurs"),
                                     get_microphone=lambda nom, include_loopback=False: Boucle())
        vrai = sys.modules.get("soundcard")
        sys.modules["soundcard"] = faux
        self.addCleanup(lambda: sys.modules.__setitem__("soundcard", vrai) if vrai else sys.modules.pop("soundcard"))
        sauve = (m.SON.get("marche"), dict(m.AUDIO))
        self.addCleanup(lambda: (m.SON.__setitem__("marche", sauve[0]), m.AUDIO.update(sauve[1])))
        m.SON["marche"] = True
        with warnings.catch_warnings():
            warnings.simplefilter("always")          # ce que soundcard pose en s'important
            m.fil_audio({})
            filtre = warnings.filters[0]
        self.assertEqual(lus, [2048])
        self.assertGreaterEqual(ouverts[0], 8 * lus[0], "huit lectures d'avance")
        self.assertEqual(filtre[0], "once", "une fois par processus, pas a chaque paquet")
        self.assertTrue(filtre[1].match("data discontinuity in recording"))

    def test_le_micro_choisi_se_retrouve_par_son_nom(self):
        # « Jarvis n'est plus detecte, et le micro peut-etre non plus » : au redemarrage du PC,
        # le micro choisi avait un autre identifiant, et celui de Windows ne rendait que du silence
        m = self.m
        sauve = {k: m.CFG.get(k) for k in ("jarvis_micro", "jarvis_micro_nom")}
        sauve_j = {k: m.JARVIS.get(k) for k in ("micro", "micro_absent", "souci", "muet_depuis")}
        ecrits = []
        vrai = m.sauver_config
        m.sauver_config = lambda cfg: ecrits.append(dict(cfg)) or True
        self.addCleanup(lambda: (setattr(m, "sauver_config", vrai), m.CFG.update(sauve), m.JARVIS.update(sauve_j)))
        self.assertEqual(m.CONFIG_DEFAUT["jarvis_micro_nom"], "")
        m.CFG.update(jarvis_micro="{A}", jarvis_micro_nom="")
        self.assertEqual(m.config_oreille(m.CFG)["micro_nom"], "")
        # le micro choisi s'ouvre : son nom est retenu (une config d'avant ne l'avait pas)
        m.traiter_evenement({"evt": "pret", "micro": "Microphone (Blue Yeti)", "trouve": True})
        self.assertEqual(m.CFG["jarvis_micro_nom"], "Microphone (Blue Yeti)")
        self.assertEqual(m.config_oreille(m.CFG)["micro_nom"], "Microphone (Blue Yeti)", "l'oreille le recoit")
        self.assertEqual(len(ecrits), 1)
        m.traiter_evenement({"evt": "pret", "micro": "Microphone (Blue Yeti)", "trouve": True})
        self.assertEqual(len(ecrits), 1, "rien de neuf : rien d'ecrit")
        # retrouve par son nom sous un autre identifiant : le nouveau est retenu, et l'oreille le recoit
        envois = []
        vrai_envoi = m.envoyer_oreille
        m.envoyer_oreille = lambda c: envois.append(c) or True
        self.addCleanup(lambda: setattr(m, "envoyer_oreille", vrai_envoi))
        m.traiter_evenement({"evt": "pret", "micro": "Microphone (2- Blue Yeti)", "trouve": True, "micro_id": "{B}"})
        self.assertEqual(m.CFG["jarvis_micro"], "{B}")
        self.assertEqual([c.get("micro") for c in envois if c.get("cmd") == "config"], ["{B}"])
        self.assertEqual(m.CFG["jarvis_micro_nom"], "Microphone (2- Blue Yeti)")
        self.assertFalse(m.JARVIS["micro_absent"])
        # celui de Windows (aucun choisi) : rien a retenir
        m.CFG.update(jarvis_micro="", jarvis_micro_nom="")
        m.traiter_evenement({"evt": "pret", "micro": "Realtek", "trouve": True})
        self.assertEqual(m.CFG["jarvis_micro_nom"], "")
        # introuvable, et celui de Windows muet : la page dit quoi faire
        m.CFG["jarvis_micro"] = "{Z}"
        m.JARVIS.update(souci=None, muet_depuis=None)
        m.traiter_evenement({"evt": "pret", "micro": "Realtek", "trouve": False})
        self.assertEqual(m.CFG["jarvis_micro"], "{Z}", "absent : on garde le choix")
        m.suivre_micro_muet(-120.0, 1000.0)
        m.suivre_micro_muet(-120.0, 1000.0 + m.MICRO_MUET_S + 1)
        self.assertEqual(m.JARVIS["souci"][0], m.MICRO_ABSENT_MESSAGE)
        self.assertIn("choisis-le de nouveau", m.MICRO_ABSENT_MESSAGE)
        self.assertTrue(m.micro_muet_signale())
        m.suivre_micro_muet(-30.0, 1000.0 + m.MICRO_MUET_S + 2)
        self.assertIsNone(m.JARVIS["souci"], "un vrai son l'efface")

    def test_jarvis_est_eteint_par_defaut(self):
        self.assertFalse(self.m.CONFIG_DEFAUT["jarvis_actif"],
                         "un micro ouvert en permanence se decide, il ne s'impose pas")

    def phrase(self, texte, reveil_verifie=True, **kw):
        """Une phrase comme l'oreille l'envoie : juste apres un reveil (verifie
        par defaut), ou -- chez le psychologue, au code -- pendant l'ecoute de
        suite, sans le nom."""
        m = self.m
        m.transcrire = lambda octets: texte
        if m.JARVIS.get("mode") == "psy" or m.JARVIS.get("attente_code"):
            m.JARVIS["suite_active"] = True
        m.JARVIS["reveil_verifie"] = reveil_verifie
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, **kw)

    def espions(self):
        vus = {"jarvis": [], "psy": []}
        self.m.parler_a_jarvis = lambda t, cfg, *a: vus["jarvis"].append(t)
        self.m.parler_au_compagnon = lambda t, cfg, *a: vus["psy"].append(t)
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
        self.assertEqual(self.dit, ["Mode psychologue. Je vous écoute. Appelez-moi par mon nom pour revenir."])
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

    def test_salut_il_repond_puis_s_eteint(self):
        # « Jarvis devrait pouvoir s'eteindre lorsqu'il repond "a bientot
        # monsieur" ou "au revoir monsieur", apres que l'utilisateur lui a dit
        # "salut" ou "au revoir". » Monsieur seulement si on le lui a demande.
        dits = []
        vraie_dire = self.m.dire
        self.m.dire = lambda texte, suite=False, langue=None, **kw: dits.append((texte, suite))
        try:
            for appellation, t in (("", "Salut !"), ("Monsieur", "Au revoir."), ("Monsieur", "Bonne nuit, Jarvis")):
                vus = self.espions()
                envoye = []
                self.m.envoyer_oreille = lambda o, e=envoye: e.append(o) or True
                self.m.CFG.update(jarvis_appellation=appellation, jarvis_langue="fr")
                # « salut » ne dit au revoir qu'en cours de conversation (voir plus bas)
                self.m.JARVIS["suite_active"] = t == "Salut !"
                self.phrase(t)
                self.assertEqual(vus, {"jarvis": [], "psy": []}, t)
                self.assertIn({"cmd": "annuler"}, envoye, "il n'ecoute plus la suite")
            self.assertIn(dits[0][0], ("À bientôt.", "Au revoir."))
            self.assertIn(dits[1][0], ("À bientôt, Monsieur.", "Au revoir, Monsieur."))
            self.assertEqual(dits[2][0], "Bonne nuit, Monsieur.")
            self.assertFalse(any(suite for _, suite in dits), "puis il s'eteint : pas de suite")
            self.assertNotIn("Monsieur", dits[0][0], "jamais Monsieur d'office")
        finally:
            self.m.dire = vraie_dire

    def test_salut_jarvis_pour_ouvrir_c_est_bonjour(self):
        # « Salut Jarvis ! » en l'appelant : il ne repondait « À bientôt » et s'eteignait
        self.m.CFG["jarvis_langue"] = "en"
        self.phrase("Salut Jarvis !")
        self.assertEqual(self.m.JARVIS["reponse_affichee"], "Yes?")

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
        self.assertEqual(self.m.JARVIS["reponse_affichee"], "Yes?")
        self.assertEqual(self.dit, [], "sans voix, pas une notification pour un « Oui ? »")
        self.m.CFG["jarvis_langue"] = "fr"
        self.phrase("Jarvis.")
        self.assertEqual(self.m.JARVIS["reponse_affichee"], "Oui ?")

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
            self.phrase("bonne nuit a toi aussi, j'ai passe une bonne soiree")
        r = req[0]
        self.assertEqual(r.full_url, "https://bd.exemple/api/machitool/parler")
        self.assertEqual(r.get_header("Authorization"), "Bearer CLE")
        self.assertRegex(r.get_header("X-fuseau"), r"^(UTC|Etc/GMT[+-]\d+)$")
        self.assertEqual(json.loads(r.data.decode()), {"texte": "bonne nuit a toi aussi, j'ai passe une bonne soiree"})
        self.assertEqual(self.dit, ["Bonne soirée."])       # sans voix : une notification

    def test_sans_cle_on_le_dit(self):
        self.m.CFG["pont_cle"] = ""
        self.phrase("Jarvis, raconte-moi une histoire")
        self.assertGreater(self.m.JARVIS["erreur_jusqua"], time.time(), "ERREUR au panneau, un instant")
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
        self.assertEqual(self.m.executer_commande({"action": "minuteurs_annuler"}, self.m.CFG), "Annulé.")
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

    # ---- v1.63 : « qu'il n'apparaisse pas pour rien », comprendre, quitter, le psy ----

    def test_sans_son_nom_apres_un_reveil_pas_verifie_il_se_rendort(self):
        vus = self.espions()
        self.phrase("et après il est rentré chez lui", reveil_verifie=False)
        self.assertEqual(vus, {"jarvis": [], "psy": []}, "la tele n'est pas une demande")
        self.assertEqual(self.m.JARVIS["etat"], "attente")
        self.assertEqual(self.dit, [])
        self.phrase("Jarvis, quelle heure est-il ?", reveil_verifie=False)
        self.assertEqual(self.m.JARVIS["etat"], "attente")
        self.assertEqual(len(self.dit), 1, "son nom y est : il repond")
        self.phrase("Javi, mets de la musique", reveil_verifie=False)
        self.assertEqual(vus["jarvis"], ["mets de la musique"], "le nom ecorche compte, et s'enleve")

    def test_parler_de_lui_n_est_pas_l_appeler(self):
        vus = self.espions()
        self.phrase("j'ai l'impression que Jarvis écoute tout le temps")
        self.assertEqual(vus, {"jarvis": [], "psy": []})
        self.assertEqual(self.dit, [])

    def test_on_sort_du_psy_en_l_appelant(self):
        for t in ("Jarvis !", "Reviens en mode Jarvis.", "Mode Jarvis.", "Je veux parler à Jarvis.",
                  "Reviens.", "Je veux plus du psy.", "Change de mode.", "Jarvis ? Re !"):
            vus = self.espions()
            self.m.poser_mode("psy")
            self.dit.clear()
            with mock_urlopen(self.m, {"texte": "ne doit pas servir"}) as req:
                self.phrase(t)
            self.assertEqual(self.m.JARVIS["mode"], "jarvis", t)
            self.assertEqual(vus, {"jarvis": [], "psy": []}, t)
            self.assertEqual(req, [], "tout de suite, sans BrainDebugger : " + t)
            self.assertEqual(self.dit, ["Welcome back."], t)

    def test_arrete_tais_toi_sortent_du_psy_sans_un_mot(self):
        for t in ("Arrête.", "Tais-toi.", "Chut.", "Stop, stop, stop !", "On arrête là.", "Enough."):
            vus = self.espions()
            self.m.poser_mode("psy")
            envoye = []
            self.m.envoyer_oreille = lambda o, e=envoye: e.append(o) or True
            self.phrase(t)
            self.assertEqual(self.m.JARVIS["mode"], "jarvis", t)
            self.assertEqual(vus, {"jarvis": [], "psy": []}, t)
            self.assertIn({"cmd": "annuler"}, envoye, t)

    def test_ce_qui_reste_au_psychologue(self):
        for t in ("J'ai galéré à allumer Jarvis ce matin.", "Je veux que ça s'arrête.", "Normal."):
            vus = self.espions()
            self.m.poser_mode("psy")
            self.phrase(t)
            self.assertEqual(vus["psy"], [t], t)
            self.assertEqual(self.m.JARVIS["mode"], "psy", t)

    def test_appele_pendant_la_seance_le_majordome_reprend(self):
        self.m.CFG["jarvis_langue"] = "fr"
        self.m.poser_mode("psy")
        self.phrase("Jarvis, quelle heure est-il ?")
        self.assertEqual(self.m.JARVIS["mode"], "jarvis")
        self.assertTrue(self.dit[-1].startswith("Il est"), self.dit)

    def test_le_silence_apres_le_psy_referme_la_seance(self):
        m = self.m
        m.poser_mode("psy")
        m.JARVIS["etat"] = "ecoute"
        m.traiter_evenement({"evt": "vide"})
        self.assertEqual(m.JARVIS["mode"], "jarvis")
        self.assertEqual(m.JARVIS["etat"], "attente")

    def test_va_dormir_ne_l_eteint_plus(self):
        self.m.CFG["jarvis_actif"] = True
        self.addCleanup(lambda: self.m.CFG.update(jarvis_actif=False))
        self.phrase("Jarvis, va dormir")
        self.assertTrue(self.m.CFG["jarvis_actif"], "il retourne attendre son nom")
        self.m.poser_mode("psy")
        self.phrase("arrête d'écouter")
        self.assertFalse(self.m.CFG["jarvis_actif"], "la, il n'ecoute plus")
        self.assertEqual(self.m.JARVIS["mode"], "jarvis", "et le psy s'est referme")

    def test_la_proposition_du_psy_est_une_vraie_question(self):
        m = self.m
        vus = {"psy": []}
        m.parler_au_compagnon = lambda t, cfg, *a: vus["psy"].append(t)
        with mock_urlopen(m, {"texte": "Vous n'êtes plus en mode psychologue. Autre chose ?", "mode": "jarvis"}):
            self.phrase("Jarvis, pourquoi t'es passé en psy ?")
        self.assertFalse(m.JARVIS["propose_psy"], "il en parle, il ne le propose pas")
        with mock_urlopen(m, {"texte": "Voulez-vous que je passe en mode psychologue ?", "mode": "jarvis",
                              "propose_psy": True}):
            self.phrase("Jarvis, j'ai eu une journée pourrie, j'ai besoin d'en parler")
        self.assertTrue(m.JARVIS["propose_psy"])
        m.JARVIS["suite_active"] = True
        self.phrase("oui")
        self.assertEqual(m.JARVIS["mode"], "psy")
        self.assertEqual(vus["psy"], ["j'ai eu une journée pourrie, j'ai besoin d'en parler"],
                         "la phrase qui l'avait fait proposer part au psychologue")

    def test_congedie_pendant_qu_il_reflechit_il_ne_repond_plus(self):
        m = self.m
        pret, lache = threading.Event(), threading.Event()

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            pret.set()
            lache.wait(5)
            return {"texte": "Une reponse d'avant.", "mode": "jarvis"}
        vrai = m._requete_bd
        self.addCleanup(lambda: setattr(m, "_requete_bd", vrai))
        m._requete_bd = bd
        m.transcrire = lambda o: "Jarvis, raconte-moi une histoire"
        m.JARVIS["reveil_verifie"] = True
        fil = threading.Thread(target=m.traiter_phrase, args=(base64.b64encode(b"RIFF").decode(), m.CFG))
        fil.start()
        self.assertTrue(pret.wait(5))
        m.terminer_conversation()                    # un clic sur son panneau, « laisse tomber »
        fil.join(2)
        self.assertFalse(fil.is_alive(), "il n'attend plus BrainDebugger")
        lache.set()
        self.assertEqual(self.dit, [], "la reponse arrivee ensuite ne se dit pas")

    def test_le_couper_en_l_appelant(self):
        m = self.m
        voix, oreille = self._jarvis_parle()
        m.transcrire = lambda octets: "Jarvis ?"
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
        self.assertNotIn({"cmd": "fausse_coupure"}, oreille, "ta voix n'est pas de l'echo")
        self.assertIsNone(m.VOIX.reprise)
        self.assertEqual(voix[-1]["texte"], "Yes?")

    # ---------------- CE QU'ON DIT PAR-DESSUS SA VOIX ----------------

    def test_sa_propre_voix_au_debut_de_la_phrase_coupee(self):
        """La phrase d'apres une coupure commence avant la decision : sa voix
        y est, et la transcription l'ecrit."""
        ctx = "All systems are operational. Your calendar is clear."
        self.assertEqual(J.sans_sa_voix("operational. Stop.", ctx), "Stop.")
        self.assertEqual(J.sans_sa_voix("systems are operational", ctx), "")
        self.assertEqual(J.sans_sa_voix("What time is it?", ctx), "What time is it?")
        self.assertEqual(J.sans_sa_voix("Clear the calendar", ctx), "Clear the calendar", "tes mots a toi restent")
        self.assertEqual(J.sans_sa_voix("clear. Jarvis, stop.", ctx), "Jarvis, stop.")

    def test_une_toux_pendant_qu_il_parle_il_reprend(self):
        # la transcription n'est pas vide (sa voix y est), mais personne n'a parle
        m = self.m
        voix, oreille = self._jarvis_parle()
        vus = self.espions()
        m.transcrire = lambda octets: "systems are operational"
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, breve=True, apres_coupure=True)
        self.assertEqual(vus["jarvis"], [], "il ne repond pas a sa propre phrase")
        self.assertIn({"cmd": "fausse_coupure"}, oreille)
        self.assertEqual(voix[-1]["texte"], "All systems are operational. Your calendar is clear.")

    def test_stop_par_dessus_sa_voix(self):
        m = self.m
        voix, oreille = self._jarvis_parle()
        vus = self.espions()
        m.transcrire = lambda octets: "operational. Stop."
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, breve=True, apres_coupure=True)
        self.assertEqual(vus["jarvis"], [], "« stop », pas une question")
        self.assertIn({"cmd": "annuler"}, oreille)
        self.assertEqual(m.JARVIS["etat"], "attente")

    def test_un_mm_hmm_par_dessus_lui_il_continue(self):
        """« Mm-hmm », « d'accord » dits par-dessus lui : continue -- pas une
        nouvelle question, pas la fin de la conversation."""
        m = self.m
        for dit in ("Mm-hmm.", "D'accord.", "Oui."):
            voix, oreille = self._jarvis_parle()
            vus = self.espions()
            m.transcrire = lambda octets, d=dit: d
            m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
            self.assertEqual(vus["jarvis"], [], dit)
            self.assertEqual(voix[-1]["texte"], "All systems are operational. Your calendar is clear.", dit)
            self.assertNotIn({"cmd": "fausse_coupure"}, oreille, "c'etait toi, pas de l'echo")
            self.assertNotIn({"cmd": "annuler"}, oreille, dit)
        self.assertIsNone(J.nature_coupure("oui oui oui"), "repete, ca veut dire « ca suffit »")
        self.assertIsNone(J.nature_coupure("Attends, mets plutôt Lyon"))

    def test_attends_par_dessus_lui(self):
        """« Attends... » : il se tait et ecoute la suite sans repondre ; si
        rien ne suit, il reprend sa phrase."""
        m = self.m
        vrai = m.oreille_vivante
        self.addCleanup(lambda: setattr(m, "oreille_vivante", vrai))
        m.oreille_vivante = lambda: True
        voix, oreille = self._jarvis_parle()
        vus = self.espions()
        m.transcrire = lambda octets: "Attends..."
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
        self.assertEqual(vus["jarvis"], [])
        self.assertEqual(oreille[-1]["cmd"], "ecouter")
        self.assertEqual(oreille[-1]["attente"], J.SUSPENS_ECOUTE_S)
        self.assertEqual((oreille[-1]["reprise"], oreille[-1]["debut"]), (True, False))
        self.assertIsNotNone(m.VOIX.reprise, "sa reponse est gardee")
        m.traiter_evenement({"evt": "vide"})
        self.assertEqual(voix[-1]["texte"], "All systems are operational. Your calendar is clear.")
        # ... ou la suite vient : elle part, avec le debut, et il ne reprend pas
        voix, oreille = self._jarvis_parle()
        m.transcrire = lambda octets: "Wait,"
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
        m.transcrire = lambda octets: "what's the weather tomorrow?"
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(vus["jarvis"], ["Wait, what's the weather tomorrow?"])
        self.assertIsNone(m.VOIX.reprise)

    # ---------------- LA PHRASE EN SUSPENS ----------------

    def test_la_suite_en_suspens_repart_de_la_fin_de_la_phrase(self):
        m = self.m
        dits, ecoutes = self._voix_et_bd(lambda *a, **k: {"texte": "Bien.", "mode": "jarvis"})
        vus = self.espions()
        self.phrase("Jarvis, raconte-moi l'histoire de")
        e = ecoutes()[-1]
        self.assertTrue(e["reprise"], "l'oreille reprend depuis la fin de la phrase")
        self.assertEqual(e["ignorer"], 0.0, "pas de carillon : rien a ignorer")
        # l'oreille a mis la phrase entiere devant : on la lit telle quelle
        m.transcrire = lambda octets: "Jarvis, raconte-moi l'histoire de la tour Eiffel."
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, avec_debut=True)
        self.assertEqual(vus["jarvis"], ["raconte-moi l'histoire de la tour Eiffel."])
        # sans elle, deux textes recolles -- et redire tout, guide par le « toc », ne double rien
        self.phrase("Jarvis, mets la musique de")
        m.transcrire = lambda octets: "Mets la musique de Daft Punk."
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(J.joindre_suspens("mets la musique de", "Mets la musique de Daft Punk."),
                         "Mets la musique de Daft Punk.")

    def test_le_petit_mot_mal_ecrit(self):
        # la transcription ecrit « de » ou « a » suivi d'un silence en un autre mot
        for t in ("Baisse le sonde.", "Allume la lumière dent.", "Ouvre le dossier d'e.",
                  "Ouvre le dossier d'eux.", "Envoie un message A.", "Mets la musique dent"):
            self.assertTrue(J.phrase_suspendue(t), t)
        for t in ("Il y en a.", "il a", "Je me brosse les dents.", "Rappelle-moi donc.", "Cherche des vidéos sûres.",
                  "Baisse le son de Discord.", "Allume la lumière.", "Il y en a plus d'un.", "Va voir la sonde."):
            self.assertFalse(J.phrase_suspendue(t), t)

    def test_chez_le_psychologue_il_laisse_des_silences(self):
        m = self.m
        ordres = []
        vrai = m.oreille_vivante
        self.addCleanup(lambda: setattr(m, "oreille_vivante", vrai))
        m.oreille_vivante = lambda: True
        m.envoyer_oreille = lambda o: ordres.append(o) or True
        m.dire("Je vous entends.", suite=True)
        self.assertNotIn("pause", ordres[-1], "chez le majordome, la pause d'avant")
        m.JARVIS["mode"] = "psy"
        m.dire("Je vous entends.", suite=True)
        self.assertEqual(ordres[-1]["pause"], J.PHRASE_PSY_PAUSE_S)
        self.assertEqual(ordres[-1]["duree_max"], J.PHRASE_PSY_MAX_S)
        m._suspendre("je me sens un peu comme", m.CFG, m.JARVIS.get("tour"), None, True, False, "fr")
        self.assertEqual(ordres[-1]["pause"], J.PHRASE_PSY_PAUSE_S)

    # ---------------- LA FENETRE DE SUITE ----------------

    def _fenetre(self, reponse):
        m = self.m
        ordres = []
        vrai = m.oreille_vivante
        self.addCleanup(lambda: setattr(m, "oreille_vivante", vrai))
        m.oreille_vivante = lambda: True
        m.envoyer_oreille = lambda o: ordres.append(o) or True
        m.dire(reponse, suite=True)
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        del m._JARVIS_TRAVAIL[:]
        m.traiter_evenement({"evt": "phrase", "wav": base64.b64encode(b"RIFF....").decode()})
        return ordres, m._JARVIS_TRAVAIL.pop()

    def test_la_fin_de_sa_voix_n_est_pas_ta_reponse(self):
        """« Je vous ecoute encore un instant » -- la fenetre entendait la fin de
        SA phrase (« sir. »), l'envoyait comme ta reponse, ou se refermait."""
        m = self.m
        vus = self.espions()
        ordres, item = self._fenetre("Very good, sir.")
        m.transcrire = lambda octets: "sir."
        m.traiter_phrase(item["wav"], m.CFG, tour=item["tour"])
        self.assertEqual(vus["jarvis"], [])
        self.assertEqual(m.JARVIS["etat"], "ecoute", "il ecoute encore")
        self.assertEqual(ordres[-1]["cmd"], "ecouter")
        self.assertEqual(ordres[-1]["ignorer"], 0.0)
        self.assertLessEqual(ordres[-1]["attente"], ordres[0]["attente"])
        # un bruit sans mots dans la fenetre : pareil, tant qu'il reste du temps
        ordres, item = self._fenetre("Voila qui est fait.")
        m.transcrire = lambda octets: ""
        m.traiter_phrase(item["wav"], m.CFG, tour=item["tour"])
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        self.assertEqual(ordres[-1]["cmd"], "ecouter")
        # apres une question, « du cafe » est bien ta reponse
        self.assertFalse(J.queue_de_sa_voix("du café", "Du thé ou du café ?"))

    # ---------------- LE MICRO MUET ----------------

    def test_le_micro_qui_ne_rend_que_du_silence_est_signale(self):
        """Micro refuse par Windows, touche « micro coupe » : il n'entendait
        plus rien, et rien ne disait pourquoi."""
        m = self.m
        horloge = {"t": 1000.0}

        class Horloge:
            def __getattr__(s, n):
                return getattr(time, n)

            def time(s):
                return horloge["t"]
        vrai = m.time
        self.addCleanup(lambda: setattr(m, "time", vrai))
        m.time = Horloge()
        m.envoyer_oreille = lambda o: True
        for _ in range(int(m.MICRO_MUET_S) + 2):
            horloge["t"] += 1.0
            m.traiter_evenement({"evt": "niveau", "db": -90.3})
        self.assertEqual(m.JARVIS["souci"][0], m.MICRO_MUET_MESSAGE)
        m.traiter_evenement({"evt": "pret", "vad": True})     # l'oreille rouvre le micro
        self.assertEqual(m.JARVIS["souci"][0], m.MICRO_MUET_MESSAGE, "rouvrir ne l'efface pas")
        m.traiter_evenement({"evt": "niveau", "db": -60.0})
        self.assertIsNone(m.JARVIS["souci"], "un vrai son l'efface")

    def test_son_nom_dans_ce_qu_il_dit(self):
        m = self.m
        m.SOUS_TITRES[991] = {"phrases": ["Ouvrez les Réglages, Jarvis."], "k": -1}
        m.SOUS_TITRES[992] = {"phrases": ["Il pleut."], "k": -1}
        self.addCleanup(lambda: (m.SOUS_TITRES.pop(991, None), m.SOUS_TITRES.pop(992, None)))
        self.assertTrue(m.nom_dans_sa_voix(991))
        self.assertFalse(m.nom_dans_sa_voix(992))
        self.assertTrue(m.nom_dans_sa_voix(12345), "inconnu : l'oreille ne cherche pas")

    def test_le_micro_qui_se_rouvre_ne_coupe_pas_la_conversation(self):
        m = self.m
        m.JARVIS["etat"] = "ecoute"
        m.traiter_evenement({"evt": "pret", "micro": "x", "trouve": True})
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        m.traiter_evenement({"evt": "erreur", "message": "micro : debranche"})
        self.assertEqual(m.JARVIS["etat"], "ecoute", "un souci de fond ne s'affiche pas au panneau")
        self.assertIn("debranche", m.JARVIS["souci"][0])

    def test_l_au_revoir_sonne_apres_son_mot(self):
        m = self.m
        sons, fins = [], []
        m.jouer_son = sons.append
        m.VOIX = type("V", (), {"peut_parler": lambda s: True, "taire": lambda s, **k: None,
                                "dire": lambda s, t, fin, l: fins.append(fin)})()
        m.CFG["jarvis_voix"] = True
        m.dire_adieu("au revoir", m.CFG)
        self.assertNotIn("fin", sons, "pas par-dessus « Au revoir »")
        fins[-1]()
        self.assertIn("fin", sons)

    def _seance(self):
        m = self.m
        m.envoyer_oreille = lambda o: True
        m.poser_mode("psy")
        echange = [{"role": "user", "texte": "j'ai raté mon gâteau"}, {"role": "assistant", "texte": "Ça arrive."}]
        m.JARVIS["psy_echange"] = list(echange)
        return echange

    def test_au_revoir_au_psy_un_mot_leger_au_plus(self):
        echange = self._seance()
        # le mot de la fin s'ecrit en arriere-plan : la seance, elle, est close tout de suite
        vrai = self.m._en_fond
        self.addCleanup(lambda: setattr(self.m, "_en_fond", vrai))
        self.m._en_fond = lambda f: f()
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
        n = len(self.dit)
        self.phrase("Hey Jarvis.")
        self.assertEqual(m.JARVIS["reponse_affichee"], "Yes?")
        self.assertEqual(len(self.dit), n, "une fois seulement")

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

    # ---------------- « REND JARVIS PLUS FLUIDE » ----------------

    def _voix_et_bd(self, bd):
        """Sa voix neuronale, l'oreille vivante, et BrainDebugger remplace par `bd`."""
        m = self.m
        voix, oreille = [], []
        vrais = (m._requete_bd, m.oreille_vivante)
        self.addCleanup(lambda: (setattr(m, "_requete_bd", vrais[0]), setattr(m, "oreille_vivante", vrais[1])))
        m.envoyer_voix = lambda o: voix.append(o) or True
        m.envoyer_oreille = lambda o: oreille.append(o) or True
        m.voix_prete = lambda cle=None: True
        m.oreille_vivante = lambda: True
        m.prechauffer_dictee = lambda: None
        m.VOIX = m.Voix()
        m.CFG.update(jarvis_voix=True, jarvis_langue="fr")
        m._requete_bd = bd
        dits = lambda: [v for v in voix if v.get("cmd") == "dire"]
        ecoutes = lambda: [o for o in oreille if o.get("cmd") == "ecouter"]
        return dits, ecoutes

    def test_un_rappel_va_aussi_dans_l_agenda(self):
        # « Assure-toi que rajouter un rappel rajoute un element a l'agenda aussi. »
        m = self.m
        vrais = (m._en_fond, m._requete_bd)
        self.addCleanup(lambda: (setattr(m, "_en_fond", vrais[0]), setattr(m, "_requete_bd", vrais[1])))
        m._en_fond = lambda f: f()
        poses = []
        m._requete_bd = lambda chemin, charge, cfg, delai, sur_debut=None: poses.append((chemin, charge)) or {"texte": "Ajouté."}
        self.addCleanup(lambda: [e["minuteur"].cancel() for e in m.JARVIS["minuteurs"]])
        avant = time.time()
        m.executer_commande(J.comprendre("rappelle-moi dans 2 heures d'appeler maman"), m.CFG)
        self.assertEqual(len(poses), 1, "le rappel est pose dans l'agenda")
        chemin, charge = poses[0]
        self.assertEqual(chemin, "/api/machitool/agenda")
        fin = time.localtime(avant + 7200)
        self.assertEqual(charge["date"], time.strftime("%Y-%m-%d", fin))
        self.assertIn(charge["heure"], (time.strftime("%H:%M", fin), time.strftime("%H:%M", time.localtime(avant + 7260))))
        self.assertEqual(charge["titre"], "Appeler maman")
        self.assertGreater(m.JARVIS["agenda_change"], 0, "la fenetre Agenda se relit")
        # un simple minuteur n'encombre pas l'agenda
        m.executer_commande(J.comprendre("minuteur de 10 minutes"), m.CFG)
        self.assertEqual(len(poses), 1)
        # Jarvis qui l'a pose lui-meme (chez BrainDebugger) : la fenetre se relit aussi
        m.JARVIS["agenda_change"] = 0.0
        m.JARVIS["tour"] = 7
        m.recevoir_jarvis("mets kine mercredi", {"texte": "C'est note pour mercredi.", "agenda_modifie": True},
                          m.CFG, 1, 7)
        self.assertGreater(m.JARVIS["agenda_change"], 0)

    def test_il_parle_des_sa_premiere_phrase(self):
        # « Il met du temps a repondre » : la premiere phrase sonne pendant que
        # le modele ecrit la suite ; la reponse entiere ne la redit pas.
        m = self.m
        pendant = []

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            self.assertTrue(charge.get("flux") is None and sur_debut is not None)
            sur_debut("Il pleut à Paris.")
            pendant.append(len(dits()))
            return {"texte": "Il pleut à Paris. Prenez un parapluie, il y en a pour la journée.", "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, quel temps fait-il à Paris ?")
        self.assertEqual(pendant, [1], "elle sonnait avant que la reponse entiere arrive")
        premier, suite = dits()
        self.assertIn("Il pleut", premier["texte"])
        self.assertNotIn("Il pleut", suite["texte"], "pas redite")
        self.assertIn("parapluie", suite["texte"])
        self.assertEqual(m.JARVIS["historique"][-1]["texte"],
                         "Il pleut à Paris. Prenez un parapluie, il y en a pour la journée.")
        # l'ecoute d'apres attend la FIN de la reponse, pas la fin de la premiere phrase
        m.VOIX.fini(premier["id"], False)
        self.assertEqual(ecoutes(), [])
        self.assertEqual(m.JARVIS["etat"], "parle")
        m.VOIX.fini(suite["id"], False)
        self.assertEqual(len(ecoutes()), 1, "puis il ecoute la suite, sans qu'on redise son nom")
        self.assertEqual(m.JARVIS["etat"], "ecoute")

    def test_la_premiere_phrase_dite_avant_que_la_suite_arrive(self):
        m = self.m

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("Je regarde cela.")
            m.VOIX.fini(dits()[0]["id"], False)          # dite, et la suite n'est pas la
            etats.append(m.JARVIS["etat"])
            return {"texte": "Je regarde cela.Grand soleil demain.", "mode": "jarvis"}
        etats = []
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, quel temps fera-t-il demain ?")
        self.assertEqual(etats, ["pense"], "entre les deux, il reflechit (il ne parle plus)")
        self.assertEqual(len(dits()), 2)
        self.assertIn("Grand soleil", dits()[1]["texte"])
        m.VOIX.fini(dits()[1]["id"], False)
        self.assertEqual(len(ecoutes()), 1)

    def test_rien_apres_la_premiere_phrase(self):
        m = self.m

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("C'est entendu.")
            return {"texte": "C'est entendu.", "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, souviens-toi de ça pour plus tard.")
        self.assertEqual(len(dits()), 1, "rien a ajouter : une seule phrase")
        self.assertEqual(ecoutes(), [], "il parle encore")
        m.VOIX.fini(dits()[0]["id"], False)
        self.assertEqual(len(ecoutes()), 1, "l'ecoute part quand elle est dite")

    def test_un_vieux_braindebugger_sans_avance(self):
        def bd(chemin, charge, cfg, delai, sur_debut=None):
            return {"texte": "Il pleut. Prenez un parapluie.", "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, quel temps fait-il ?")
        self.assertEqual(len(dits()), 1)
        self.assertIn("parapluie", dits()[0]["texte"])

    def test_coupe_pendant_une_reponse_en_deux_temps(self):
        # on lui coupe la parole pendant sa premiere phrase, pour rien : il
        # reprend, et la suite de SA reponse avec
        m = self.m

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("Il pleut à Paris.")
            return {"texte": "Il pleut à Paris. Prenez un parapluie.", "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, quel temps fait-il à Paris ?")
        premier = dits()[0]["id"]
        m.traiter_evenement({"evt": "coupure"})
        self.assertIn("parapluie", m.VOIX.reprise["texte"])
        m.VOIX.fini(premier, True, "Il pleut à Paris.")
        m.traiter_evenement({"evt": "vide", "apres_coupure": True})
        self.assertIn("Il pleut", dits()[-1]["texte"])
        self.assertIn("parapluie", dits()[-1]["texte"])
        m.VOIX.fini(dits()[-1]["id"], False)
        self.assertEqual(m.JARVIS["etat"], "ecoute", "et il ecoute la suite, comme prevu")

    # ---- « je lui coupe la parole pendant sa premiere phrase » (v1.64) ----

    def _coupe_pendant_l_avance(self, reponse="Il pleut à Paris. Prenez un parapluie."):
        """BrainDebugger ecrit encore quand on coupe la premiere phrase : la
        reponse entiere arrive APRES la coupure."""
        m = self.m
        del m._JARVIS_TRAVAIL[:]
        self.addCleanup(lambda: m._JARVIS_TRAVAIL.clear())
        etats = []

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("Il pleut à Paris.")
            premier = dits()[0]["id"]
            m.traiter_evenement({"evt": "coupure"})
            m.VOIX.fini(premier, True, "Il pleut à Paris.")
            etats.append(m.JARVIS["etat"])
            return {"texte": reponse, "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, quel temps fait-il à Paris ?")
        self.assertEqual(etats, ["ecoute"])
        return dits, ecoutes

    def test_coupe_pendant_l_avance_la_suite_ne_se_dit_pas(self):
        m = self.m
        dits, ecoutes = self._coupe_pendant_l_avance()
        self.assertEqual(len(dits()), 1, "la suite n'est pas dite par-dessus celui qui lui parle")
        self.assertEqual(m.JARVIS["etat"], "ecoute", "il t'ecoute toujours (pas « parle »)")
        self.assertEqual(ecoutes(), [])
        self.assertIn("parapluie", m.VOIX.reprise["texte"], "elle attend la reprise")
        # c'etait pour rien (un bruit bref, sans mots : le vrai chemin de l'oreille)
        m.transcrire = lambda octets: ""
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True, breve=True)
        self.assertEqual(len(dits()), 2)
        self.assertEqual(dits()[-1]["texte"], "Il pleut à Paris. Prenez un parapluie.", "dans l'ordre, une fois")
        m.VOIX.fini(dits()[-1]["id"], False)
        self.assertEqual(len(ecoutes()), 1, "puis l'ecoute d'apres, une fois")
        self.assertEqual(m.JARVIS["etat"], "ecoute")

    def test_coupe_pendant_l_avance_pour_de_vrai(self):
        m = self.m
        dits, ecoutes = self._coupe_pendant_l_avance()
        m.transcrire = lambda octets: "Non attends, je voulais dire Lyon."
        m.JARVIS["reveil_verifie"] = True
        vus = self.espions()
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True)
        self.assertFalse(any("parapluie" in d["texte"] for d in dits()), "la suite de l'ancienne reponse : jamais")
        self.assertEqual(vus["jarvis"], ["Non attends, je voulais dire Lyon."])
        self.assertIsNone(m.VOIX.reprise)

    def test_coupe_pendant_l_avance_sans_suite(self):
        # la reponse, c'etait la premiere phrase : la coupure ne fait pas partir l'ecoute
        m = self.m
        dits, ecoutes = self._coupe_pendant_l_avance("Il pleut à Paris.")
        self.assertEqual(ecoutes(), [], "pas de carillon d'ecoute par-dessus la coupure")
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        m.transcrire = lambda octets: ""
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG, True, breve=True)
        m.VOIX.fini(dits()[-1]["id"], False)
        self.assertEqual(len(ecoutes()), 1)

    def test_coupe_pendant_l_avance_la_reprise_avant_la_suite(self):
        # l'autre ordre : personne ne parlait, il reprend sa premiere phrase
        # AVANT que la suite arrive -- elle se dit derriere, puis il ecoute
        m = self.m
        del m._JARVIS_TRAVAIL[:]
        self.addCleanup(lambda: m._JARVIS_TRAVAIL.clear())

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("Il pleut à Paris.")
            m.traiter_evenement({"evt": "coupure"})
            m.VOIX.fini(dits()[0]["id"], True, "Il pleut à Paris.")
            m.traiter_evenement({"evt": "vide", "apres_coupure": True})
            return {"texte": "Il pleut à Paris. Prenez un parapluie.", "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        self.phrase("Jarvis, quel temps fait-il à Paris ?")
        self.assertEqual([d["texte"] for d in dits()], ["Il pleut à Paris.", "Il pleut à Paris.",
                                                        "Prenez un parapluie."])
        m.VOIX.fini(dits()[1]["id"], False)
        self.assertEqual(ecoutes(), [])
        m.VOIX.fini(dits()[2]["id"], False)
        self.assertEqual(len(ecoutes()), 1)
        self.assertEqual(m.JARVIS["etat"], "ecoute")

    def test_interrompu_pour_de_vrai_il_n_attend_plus_braindebugger(self):
        # des mots par-dessus sa premiere phrase : la requete en vol ne retient
        # plus la phrase qui l'a interrompu
        m = self.m
        del m._JARVIS_TRAVAIL[:]
        self.addCleanup(lambda: m._JARVIS_TRAVAIL.clear())
        rendu = threading.Event()

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("Il pleut à Paris.")
            m.traiter_evenement({"evt": "coupure"})
            m.VOIX.fini(dits()[0]["id"], True, "Il pleut à Paris.")
            m.traiter_evenement({"evt": "phrase", "wav": "UklGRg==", "apres_coupure": True})
            time.sleep(1.5)
            rendu.set()
            return {"texte": "Il pleut à Paris. Prenez un parapluie.", "mode": "jarvis"}
        dits, ecoutes = self._voix_et_bd(bd)
        t0 = time.time()
        self.phrase("Jarvis, quel temps fait-il à Paris ?")
        self.assertLess(time.time() - t0, 1.2, "il n'a pas attendu la fin de BrainDebugger")
        self.assertFalse(rendu.is_set())
        self.assertEqual(len(m._JARVIS_TRAVAIL), 1, "la phrase qui l'a interrompu est la suivante")
        self.assertEqual(m.JARVIS["historique"][-2:], [
            {"role": "user", "texte": "quel temps fait-il à Paris ?"},
            {"role": "assistant", "texte": "Il pleut à Paris. [interrompu]"}])
        rendu.wait(3)
        self.assertEqual(len(dits()), 1, "la suite n'arrive jamais")
        # et si ce n'etaient pas des mots, il reprend sa phrase et ne reste pas « parle »
        m.transcrire = lambda octets: ""
        item = m._JARVIS_TRAVAIL.pop(0)
        m.traiter_phrase(item["wav"], m.CFG, True, tour=item["tour"])
        self.assertEqual(dits()[-1]["texte"], "Il pleut à Paris.")
        m.VOIX.fini(dits()[-1]["id"], False)
        self.assertEqual(m.JARVIS["etat"], "attente")

    def test_l_ecoute_attend_que_la_voix_ait_tout_dit(self):
        # « il m'ecoute alors qu'il parle encore » : un minuteur dit derriere sa
        # reponse passe AVANT l'ecoute d'apres
        m = self.m
        dits, ecoutes = self._voix_et_bd(lambda *a, **k: {"texte": "Bien, monsieur.", "mode": "jarvis"})
        self.phrase("Jarvis, ça va ?")
        reponse = dits()[-1]["id"]
        m.VOIX.dire("Votre minuteur est terminé.", None, "fr")
        minuteur = dits()[-1]["id"]
        m.VOIX.fini(reponse, False)
        self.assertEqual(ecoutes(), [], "le minuteur se dit encore")
        self.assertEqual(m.JARVIS["etat"], "parle")
        m.VOIX.fini(minuteur, False)
        self.assertEqual(len(ecoutes()), 1)
        self.assertEqual(m.JARVIS["etat"], "ecoute")

    def test_un_minuteur_ne_parle_pas_par_dessus_la_conversation(self):
        m = self.m
        dits, ecoutes = self._voix_et_bd(lambda *a, **k: {"texte": "Bien.", "mode": "jarvis"})
        oreille = []
        m.envoyer_oreille = lambda o: oreille.append(o) or True
        m.JARVIS.update(etat="pense")
        self.addCleanup(lambda: m.PANNEAU.update(jarvis=None))
        m.PANNEAU["jarvis"] = None
        self.assertFalse(m.annoncer("Votre minuteur est terminé.", "fr"))
        self.assertEqual(dits(), [], "il reflechit a ta question : pas maintenant")
        self.assertIsNone(m.PANNEAU["jarvis"], "le panneau non plus")
        m.dire_les_annonces()
        self.assertEqual(dits(), [])
        m.JARVIS.update(etat="attente")
        m.dire_les_annonces()
        self.assertEqual([d["texte"] for d in dits()], ["Votre minuteur est terminé."])
        self.assertEqual(m.PANNEAU["jarvis"]["texte"], "Votre minuteur est terminé.", "dit de lui-meme : le panneau le montre")
        # une fenetre d'ecoute d'apres, ou personne ne parle : il la ferme, et le dit
        m.JARVIS.update(etat="ecoute", suite_active=True, parole_vue=0.0)
        self.assertTrue(m.annoncer("Votre rappel.", "fr"))
        self.assertEqual(m.JARVIS["etat"], "attente")
        self.assertIn({"cmd": "annuler"}, oreille)
        self.assertEqual(dits()[-1]["texte"], "Votre rappel.")
        # tu parlais : ca attend
        m.JARVIS.update(etat="ecoute", suite_active=True, parole_vue=time.time())
        self.assertFalse(m.annoncer("Encore un.", "fr"))
        self.assertEqual(len(m.ANNONCES), 1)
        # le minuteur lui-meme : le son et la notification tout de suite, la phrase plus tard
        m.JARVIS.update(etat="comprend")
        m.poser_minuteur(600, "", "fr")
        e = m.JARVIS["minuteurs"][-1]
        e["minuteur"].cancel()
        n, self.dit[:] = len(dits()), []
        e["minuteur"].function()
        self.assertEqual(len(dits()), n, "pas par-dessus ta phrase")
        self.assertEqual(len(self.dit), 1, "la notification, elle, tout de suite")
        self.assertEqual(len(m.ANNONCES), 2)

    def test_entre_sa_premiere_phrase_et_la_suite_il_parle_toujours(self):
        # l'oreille ne croit pas qu'il s'est tu entre deux textes qui se suivent
        # (elle guette toujours qu'on lui coupe la parole) ; et « rate » arrive
        m = self.m
        oreille, voix = [], []
        m.envoyer_oreille = lambda o: oreille.append(o) or True
        m.envoyer_voix = lambda o: voix.append(o) or True
        m.voix_prete = lambda cle=None: True
        m.VOIX = m.Voix()
        m.VOIX.disponible = False
        a, b = m.VOIX.dire("Il pleut.", None), m.VOIX.dire("Prenez un parapluie.", None)
        s1, s2 = socket.socketpair()
        J.envoyer(s2, {"evt": "fini", "id": a, "coupe": False})
        J.envoyer(s2, {"evt": "fini", "id": b, "coupe": False, "rate": True, "reste": "Prenez un parapluie."})
        J.envoyer(s2, None)
        m._lire_voix(s1)
        s1.close()
        s2.close()
        self.assertEqual([o for o in oreille if o.get("cmd") == "parole"], [{"cmd": "parole", "actif": False}])
        self.assertEqual(self.dit, ["Prenez un parapluie."], "la voix a rate : la notification le montre")

    def test_la_voix_en_echec_n_est_pas_une_reponse(self):
        # le casque debranche en pleine phrase : pas de silence suivi du
        # carillon d'ecoute -- la voix de Windows dit ce qui manquait, puis il ecoute
        m = self.m
        dits, ecoutes = self._voix_et_bd(lambda *a, **k: {"texte": "Il pleut. Prenez un parapluie.",
                                                          "mode": "jarvis"})
        par_windows = []
        m.VOIX._par_windows = lambda texte, fin, langue: par_windows.append((texte, fin, langue))
        m.VOIX.disponible = True
        self.phrase("Jarvis, quel temps fait-il ?")
        ident = dits()[-1]["id"]
        m.VOIX.fini(ident, False, "Prenez un parapluie.", rate=True)
        self.assertEqual(ecoutes(), [], "il n'a pas repondu : il n'ecoute pas encore")
        self.assertEqual([(t, l) for t, f, l in par_windows], [("Prenez un parapluie.", "fr")])
        par_windows[0][1]()
        self.assertEqual(len(ecoutes()), 1, "dit par la voix de Windows : la suite reprend")
        # sans voix de Windows : la notification montre la reponse, et le souci le dit
        m.VOIX.disponible = False
        self.dit.clear()
        self.phrase("Jarvis, quel temps fait-il ?")
        m.VOIX.fini(dits()[-1]["id"], False, None, rate=True)
        self.assertEqual(self.dit, ["Il pleut. Prenez un parapluie."])
        self.assertIn("voix", m.JARVIS["souci"][0])
        # la voix tombee toute seule : ce qu'elle avait a dire passe a Windows
        m.VOIX.disponible = True
        par_windows.clear()
        self.phrase("Jarvis, quel temps fait-il ?")
        n = len(ecoutes())
        m.VOIX.enfant_perdu(redire=True)
        self.assertEqual([t for t, f, l in par_windows], ["Il pleut. Prenez un parapluie."])
        self.assertEqual(len(ecoutes()), n)
        m.VOIX.enfant_perdu()
        self.assertEqual(len(par_windows), 1, "arretee expres : rien a redire")

    def test_la_reponse_en_flux(self):
        # BrainDebugger en flux : l'avance, puis la reponse entiere ; ou l'erreur
        m = self.m

        class Reponse:
            def __init__(self, lignes, type_="application/x-ndjson; charset=utf-8"):
                self.lignes, self.headers = lignes, {"Content-Type": type_}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                return iter(self.lignes)

            def read(self):
                return b"".join(self.lignes)
        vraie = urllib.request.urlopen
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", vraie))
        envoyes, avance = [], []
        rep = {}
        urllib.request.urlopen = lambda req, **k: envoyes.append(json.loads(req.data)) or rep["r"]
        rep["r"] = Reponse([b'{"debut": "Bonsoir."}\n', b"\n", b'{"fin": {"texte": "Bonsoir. Tout va bien."}}\n'])
        r = m._requete_bd("/api/machitool/jarvis", {"texte": "salut"}, m.CFG, 5, sur_debut=avance.append)
        self.assertEqual(r, {"texte": "Bonsoir. Tout va bien."})
        self.assertEqual(avance, ["Bonsoir."])
        self.assertIs(envoyes[-1]["flux"], True, "il demande le flux")
        rep["r"] = Reponse([b'{"texte": "Bonsoir."}'], "application/json; charset=utf-8")
        self.assertEqual(m._requete_bd("/x", {"texte": "salut"}, m.CFG, 5, sur_debut=avance.append),
                         {"texte": "Bonsoir."}, "un BrainDebugger d'avant : du JSON tout court")
        m._requete_bd("/x", {"a": 1}, m.CFG, 5)
        self.assertNotIn("flux", envoyes[-1], "sans avance demandee, pas de flux")
        rep["r"] = Reponse([b'{"erreur": {"error": "cle refusee", "raison": "cle"}, "statut": 502}\n'])
        with self.assertRaises(urllib.error.HTTPError) as e:
            m._requete_bd("/x", {"texte": "salut"}, m.CFG, 5, sur_debut=avance.append)
        self.assertEqual(e.exception.code, 502)
        self.assertEqual(m._corps_http(e.exception)["raison"], "cle")
        rep["r"] = Reponse([b'{"debut": "Bonsoir."}\n'])
        with self.assertRaises(ConnectionError):
            m._requete_bd("/x", {"texte": "salut"}, m.CFG, 5, sur_debut=avance.append)

    def test_une_phrase_en_suspens_attend_la_suite(self):
        # « mets la musique de... » : il ne repond pas a la moitie
        m = self.m
        dits, ecoutes = self._voix_et_bd(lambda *a, **k: {"texte": "Bien.", "mode": "jarvis"})
        vus = self.espions()
        self.phrase("Jarvis, raconte-moi l'histoire de")
        self.assertEqual(vus["jarvis"], [], "rien n'est parti")
        self.assertEqual(ecoutes()[-1]["attente"], J.SUSPENS_ECOUTE_S)
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        self.assertTrue(m.JARVIS["entendu"].startswith("raconte-moi l'histoire de"), m.JARVIS["entendu"])
        m.transcrire = lambda octets: "la tour Eiffel."
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(vus["jarvis"], ["raconte-moi l'histoire de la tour Eiffel."])

    def test_une_phrase_en_suspens_puis_rien(self):
        m = self.m
        dits, ecoutes = self._voix_et_bd(lambda *a, **k: {"texte": "Bien.", "mode": "jarvis"})
        vus = self.espions()
        del m._JARVIS_TRAVAIL[:]
        self.phrase("Jarvis, explique-moi la différence entre")
        self.assertEqual(vus["jarvis"], [])
        m.traiter_evenement({"evt": "vide"})
        item = m._JARVIS_TRAVAIL.pop()
        m.traiter_phrase(item["wav"], m.CFG, tour=item["tour"])
        self.assertEqual(vus["jarvis"], ["explique-moi la différence entre"], "elle part telle quelle")
        # deux reprises au plus
        self.phrase("Jarvis, parle-moi de")
        for bout in ("la ville de", "Paris et"):
            m.transcrire = lambda octets, b=bout: b
            m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(vus["jarvis"][-1], "parle-moi de la ville de Paris et")

    def test_ce_qui_n_est_pas_en_suspens(self):
        for t in ("Mets-la.", "Allume la lumière du salon.", "C'est qui ?", "J'en prends une.", "Il y en a.",
                  "Tu peux me dire de quoi ?"):
            self.assertFalse(J.phrase_suspendue(t), t)
        for t in ("Mets la musique de", "je pense que...", "C'est l'", "euh"):
            self.assertTrue(J.phrase_suspendue(t), t)
        self.assertTrue(J.phrase_suspendue("Play some music by the", "en"))
        self.assertFalse(J.phrase_suspendue("il a", "fr"))
        self.assertEqual(J.reste_a_dire("Il pleut.  Prenez un   parapluie.", "Il pleut."), "Prenez un parapluie.")
        self.assertEqual(J.reste_a_dire("Autre chose.", "Il pleut."), "Autre chose.", "jamais une phrase perdue")

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
        # son nom seul, MAIS pas apres une coupure : « Yes? », comme avant
        m.transcrire = lambda octets: "Jarvis ?"
        m.JARVIS["reveil_verifie"] = True
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

    def test_jarvis_maitre_de_l_application(self):
        # « Jarvis a tous les droits au niveau de l'application : il peut
        # controler et rajouter des petites sous-routines de lumieres, avec des
        # habitudes / running gags. »
        m = self.m
        vrais = (m.dire, m.transcrire)

        def remettre():
            m.dire, m.transcrire = vrais
            m.ANIMATION["etapes"] = []
            m.ROUTINES_VUES["dernieres"].clear()
            m.ETAT["forcage"] = None
            m.CFG["jarvis_actif"] = False
        self.addCleanup(remettre)
        m.CFG["jarvis_pc"] = False               # l'application, pas le PC : sans ses mains
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        self.assertIn("#FF7A00", ex("lumiere", {"action": "couleur", "couleur": "orange"})["texte"])
        self.assertEqual(m.ETAT["forcage"]["couleur"], (255, 122, 0))
        ex("lumiere", {"action": "normale"})
        self.assertIsNone(m.ETAT["forcage"])
        r = ex("lumiere", {"action": "animation", "etapes": [{"couleur": "rouge", "duree": 0.5, "effet": "clignote"},
                                                            {"couleur": "bleu", "duree": 0.5, "effet": "fondu"}],
                           "repetitions": 2})
        self.assertIn("Animation lancee", r["texte"])
        t0 = m.ANIMATION["t0"]
        self.assertEqual(tuple(round(c) for c in m.couleur_de_l_animation(t0)), (255, 26, 26))
        self.assertIsNone(m.couleur_de_l_animation(t0 + 2.1), "finie")
        self.assertIn("erreur", ex("lumiere", {"action": "animation", "etapes": [{"couleur": "pas une couleur"}]}))
        # une routine : habitude du soir, qui tient sa couleur
        r = ex("routine_lumiere", {"action": "creer", "nom": "Bonne nuit",
                                   "declencheur": {"type": "phrase", "valeur": "je vais me coucher"},
                                   "etapes": [{"couleur": "ambre", "duree": 3, "effet": "fondu", "luminosite": 0.3}],
                                   "tenir": True, "replique": "Je tamise, monsieur. Bonne nuit."})
        self.assertIn("Routine gardee", r["texte"])
        self.assertTrue(m.CFG["routines_lumiere"][0]["par_jarvis"])
        self.assertIn("Bonne nuit", ex("routine_lumiere", {"action": "lister"})["texte"])
        self.assertIn("erreur", ex("routine_lumiere", {"action": "creer", "nom": "x",
                                                      "declencheur": {"type": "heure", "valeur": "27h"},
                                                      "etapes": [{"couleur": "bleu"}]}))
        dits = []
        m.dire = lambda texte, **k: dits.append(texte)
        m.transcrire = lambda o: "Bon, je vais me coucher"
        m.JARVIS["reveil_verifie"] = True
        m.traiter_phrase(base64.b64encode(b"RIFF").decode(), m.CFG)
        self.assertEqual(dits, ["Je tamise, monsieur. Bonne nuit."], "la replique, sans passer par BrainDebugger")
        self.assertEqual(m.ANIMATION["nom"], "Bonne nuit")
        self.assertIsNone(m.couleur_de_l_animation(m.ANIMATION["t0"] + 5))
        self.assertEqual(m.ETAT["forcage"]["couleur"], (76, 53, 0), "la couleur du soir reste, tamisee")
        # un running gag : quand League s'ouvre, une fois sur deux, pas plus d'une fois par heure
        ex("routine_lumiere", {"action": "creer", "nom": "Encore League",
                               "declencheur": {"type": "appli", "valeur": "League of Legends"},
                               "etapes": [{"couleur": "rouge", "duree": 1, "effet": "pulse"}], "repetitions": 3,
                               "chance": 0.5, "pause_min": 60, "replique": "Encore, monsieur ?"})
        m.CFG["jarvis_actif"] = True
        m.JARVIS["etat"] = "attente"
        dits.clear()
        t = time.time()
        self.assertIsNone(m.declencher_routines("appli", "League of Legends (TM) Client", m.CFG, t, alea=0.9),
                          "pas cette fois : la chance")
        self.assertEqual(m.declencher_routines("appli", "League of Legends (TM) Client", m.CFG, t, alea=0.1)["nom"],
                         "Encore League")
        # « surtout qu'il n'apparaisse pas pour rien » : la lumiere, pas la replique...
        self.assertEqual(dits, [], "une appli qui passe devant : il ne parle pas sans qu'on l'appelle")
        # ... sauf si on le lui a permis
        m.CFG["jarvis_repliques_spontanees"] = True
        m.ROUTINES_VUES["dernieres"].clear()
        m.declencher_routines("appli", "League of Legends (TM) Client", m.CFG, t, alea=0.1)
        self.assertEqual(dits, ["Encore, monsieur ?"])
        m.JARVIS["calme_jusqua"] = t + 600
        m.ROUTINES_VUES["dernieres"].clear()
        dits.clear()
        m.declencher_routines("appli", "League of Legends (TM) Client", m.CFG, t, alea=0.1)
        self.assertEqual(dits, [], "juste apres l'avoir congedie : rien")
        m.JARVIS["calme_jusqua"] = 0.0
        self.assertIsNone(m.declencher_routines("appli", "League of Legends", m.CFG, t + 600, alea=0.1),
                          "dix minutes apres : trop tot")
        self.assertIsNotNone(m.declencher_routines("appli", "League of Legends", m.CFG, t + 3700, alea=0.1))
        # a l'heure, les jours dits
        ex("routine_lumiere", {"action": "creer", "nom": "Pause", "declencheur": {"type": "heure", "valeur": "16h",
                                                                                "jours": ["lundi", "fri"]},
                               "etapes": [{"couleur": "vert", "duree": 2, "effet": "respire"}]})
        lundi16 = time.struct_time((2026, 9, 28, 16, 0, 0, 0, 271, -1))
        mardi16 = time.struct_time((2026, 9, 29, 16, 0, 0, 1, 272, -1))
        self.assertEqual(m.declencher_routines("heure", lundi16, m.CFG, t)["nom"], "Pause")
        self.assertIsNone(m.declencher_routines("heure", mardi16, m.CFG, t + 99999))
        self.assertIn("desactivee", ex("routine_lumiere", {"action": "desactiver", "nom": "pause"})["texte"])
        self.assertIn("supprimee", ex("routine_lumiere", {"action": "supprimer", "nom": "Encore League"})["texte"])
        self.assertEqual([r["nom"] for r in m.CFG["routines_lumiere"]], ["Bonne nuit", "Pause"])
        # les reglages de l'application
        self.assertIn("mode = ", ex("reglages_machi", {"action": "lire", "cle": "mode"})["texte"])
        self.assertNotIn("pont_cle", ex("reglages_machi", {"action": "lire"})["texte"])
        self.assertIn("veille_minutes = 10", ex("reglages_machi", {"action": "changer", "cle": "veille_minutes",
                                                                   "valeur": "10"})["texte"])
        self.assertEqual(m.CFG["veille_minutes"], 10)
        self.assertIn("reaction_processeur = False", ex("reglages_machi", {"action": "changer",
                                                                           "cle": "reaction_processeur",
                                                                           "valeur": "non"})["texte"])
        for interdit in ("pont_cle", "pont_site", "jarvis_code_empreinte", "api_origines", "adresse"):
            self.assertIn("erreur", ex("reglages_machi", {"action": "changer", "cle": interdit, "valeur": "1"}), interdit)
        self.assertIn("erreur", ex("reglages_machi", {"action": "changer", "cle": "son_bande", "valeur": "fort"}))
        r = ex("reglages_machi", {"action": "couleur_appli", "nom": "Discord", "couleur": "vert"})
        # Discord vit dans la regle « Discussion » (avec Slack, Teams...) : il a la sienne, en tete
        self.assertIn("Nouvelle regle : Discord en #22E052", r["texte"])
        r = ex("reglages_machi", {"action": "couleur_appli", "nom": "discord", "couleur": "cyan"})
        self.assertIn("Discord passe en #00D5FF", r["texte"])
        r = ex("reglages_machi", {"action": "couleur_appli", "nom": "Elden Ring", "couleur": "#aa3300",
                                  "mots": ["eldenring"]})
        self.assertEqual(m.CFG["regles"][0], {"nom": "Elden Ring", "couleur": "#AA3300", "mots": ["eldenring"]},
                         "une regle neuve passe en tete")
        cap = m.capacites_jarvis(m.CFG)
        self.assertTrue(cap["application"])
        self.assertIn("Bonne nuit", cap["routines"])

    def test_la_boucle_des_leds_consulte_jarvis_avant_le_reste(self):
        with open(os.path.join(RACINE, "machi_tool.py"), encoding="utf-8") as f:
            src = f.read()
        corps = src[src.index("async def une_session"):src.index("async def superviseur")]
        self.assertLess(corps.index("couleur_jarvis(cfg)"), corps.index('if mode == "son":'))
        self.assertIn('inactif = (mode not in ("jarvis", "routine")', corps)
        # ses animations passent par-dessus Jarvis, avant le son et l'ecran
        self.assertLess(corps.index("couleur_jarvis(cfg)"), corps.index("couleur_de_l_animation()"))
        self.assertLess(corps.index("couleur_de_l_animation()"), corps.index('if mode == "son":'))

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

    # ---- la transcription telle que Jarvis s'en sert ----

    def remplacer(self, **kw):
        for nom, valeur in kw.items():
            self.addCleanup(setattr, self.m, nom, getattr(self.m, nom))
            setattr(self.m, nom, valeur)

    def moteur_factice(self, vu):
        """Un moteur « vivant » sans processus : de quoi juger l'entretien."""
        m = self.m

        class Proc:
            pid = 1

            def poll(self):
                return None
        self.addCleanup(m._MOTEUR.update, proc=None, sock=None, vu=0.0, charge=False)
        m._MOTEUR.update(proc=Proc(), sock=object(), vu=vu, charge=True)

    def test_le_moteur_se_precharge_apres_le_demarrage_de_l_oreille(self):
        """« Le premier Jarvis paie le deballage et 652 Mo de modele » : rien ne
        chargeait le moteur avant qu'on ait parle. L'oreille prete, il se
        charge ~45 s plus tard -- si la memoire le permet encore, lui charge."""
        m = self.m
        lances = []
        self.remplacer(dictee_possible=lambda: True, envoyer_oreille=lambda o: True)
        self.addCleanup(m._ENTRETIEN.update, prechauffe_a=0.0, en_cours=False)
        m._ENTRETIEN.update(prechauffe_a=0.0, en_cours=False)
        m.CFG["jarvis_actif"] = True
        t0 = time.time()
        m.traiter_evenement({"evt": "pret", "micro": "x", "trouve": True})
        self.assertIsNone(m.entretenir_dictee(m.CFG, t0 + 1, lances.append), "pas pendant que le PC demarre")
        self.remplacer(memoire_libre_mo=lambda: 3700)
        self.assertEqual(m.entretenir_dictee(m.CFG, t0 + 60, lances.append), "prechauffe")
        self.assertEqual(lances, [m.prechauffer_dictee])
        self.assertIsNone(m.entretenir_dictee(m.CFG, t0 + 120, lances.append), "une seule fois par oreille")
        # peu de memoire : 1 Go de plus gelerait le PC -- il attendra qu'on l'appelle
        m.traiter_evenement({"evt": "pret", "micro": "x", "trouve": True})
        self.remplacer(memoire_libre_mo=lambda: 3000)
        self.assertIsNone(m.entretenir_dictee(m.CFG, t0 + 200, lances.append))
        self.assertEqual(len(lances), 1)
        # Jarvis decoche : rien
        m.CFG["jarvis_actif"] = False
        m.traiter_evenement({"evt": "pret", "micro": "x", "trouve": True})
        self.assertIsNone(m.entretenir_dictee(m.CFG, t0 + 900, lances.append))

    def test_le_moteur_est_entretenu_tant_que_la_memoire_le_permet(self):
        m = self.m
        lances = []
        self.remplacer(dictee_possible=lambda: True, memoire_libre_mo=lambda: 2600)
        self.addCleanup(m._ENTRETIEN.update, prechauffe_a=0.0, en_cours=False)
        m.CFG["jarvis_actif"] = True
        t = time.time()
        self.moteur_factice(vu=t - 5 * 60)
        self.assertIsNone(m.entretenir_dictee(m.CFG, t, lances.append), "servi il y a 5 min : rien a faire")
        m._MOTEUR["vu"] = t - 21 * 60
        self.assertEqual(m.entretenir_dictee(m.CFG, t, lances.append), "entretien")
        self.assertEqual(lances, [m.garder_au_chaud])
        self.assertIsNone(m.entretenir_dictee(m.CFG, t, lances.append), "un entretien a la fois")
        m._ENTRETIEN["en_cours"] = False
        # la memoire se resserre (un jeu) : plus d'entretien, il partira de lui-meme
        self.remplacer(memoire_libre_mo=lambda: 2100)
        self.assertIsNone(m.entretenir_dictee(m.CFG, t, lances.append))
        self.assertEqual(len(lances), 1)

    def test_le_delai_de_dechargement_reste_fini(self):
        m = self.m
        self.assertEqual(m.delai_dechargement({"jarvis_actif": True}, libre=4000), m.DICTEE_GARDER_JARVIS_S)
        self.assertEqual(m.delai_dechargement({"jarvis_actif": True}, libre=2100), 30 * 60,
                         "Jarvis ecoute, encore de la marge : une demi-heure, pas dix minutes")
        self.assertEqual(m.delai_dechargement({"jarvis_actif": True}, libre=1600), m.DICTEE_DECHARGER_S)
        self.assertEqual(m.delai_dechargement({"jarvis_actif": False}, libre=9000), m.DICTEE_DECHARGER_S)

    def test_presque_reconnu_reveille_le_moteur(self):
        m = self.m
        lances = []
        self.remplacer(dictee_possible=lambda: True, memoire_libre_mo=lambda: 8000,
                       prechauffer_dictee=lambda: lances.append(1))
        m.CFG["jarvis_actif"] = True
        m.traiter_evenement({"evt": "presque", "distance": 0.2, "seuil": 0.18})
        fin = time.time() + 2
        while not lances and time.time() < fin:
            time.sleep(0.01)
        self.assertEqual(lances, [1])

    def test_un_modele_rate_se_retente_de_plus_en_plus_lentement(self):
        """« Un telechargement rate rend Jarvis sourd pour de bon. »"""
        m = self.m
        lances = []
        self.remplacer(dictee_possible=lambda: True)
        self.addCleanup(m._DICTEE_RELANCE.update, prochain=0.0, n=0)
        self.addCleanup(m.DICTEE.update, etat="absent")
        m._DICTEE_RELANCE.update(prochain=0.0, n=0)
        m.DICTEE.update(etat="erreur", message="delai depasse")
        t = 1000.0
        self.assertFalse(m.relancer_dictee_si_ratee(t, lances.append))
        self.assertFalse(m.relancer_dictee_si_ratee(t + 30, lances.append))
        self.assertTrue(m.relancer_dictee_si_ratee(t + 61, lances.append), "une minute apres")
        self.assertEqual(lances, [m.preparer_dictee])
        self.assertFalse(m.relancer_dictee_si_ratee(t + 200, lances.append))
        self.assertTrue(m.relancer_dictee_si_ratee(t + 61 + 301, lances.append), "puis cinq")
        self.assertFalse(m.relancer_dictee_si_ratee(t + 61 + 301 + 600, lances.append))
        self.assertTrue(m.relancer_dictee_si_ratee(t + 61 + 301 + 1801, lances.append), "puis trente")
        self.assertEqual(len(lances), 3)

    def test_un_appel_sans_transcription_ne_fait_pas_parler_dans_le_vide(self):
        m = self.m
        envoye = []
        self.remplacer(prechauffer_dictee=lambda: None)
        m.envoyer_oreille = envoye.append
        m.etat_dictee = lambda: {"etat": "preparation", "progres": 0.42}
        m.traiter_evenement({"evt": "reveil", "par": "voix", "score": 0.1})
        self.assertNotEqual(m.JARVIS["etat"], "ecoute")
        self.assertIn({"cmd": "annuler"}, envoye)
        self.assertIn("42", m.JARVIS["message"])

    def test_la_transcription_absente_se_dit_encore_apres_la_premiere_fois(self):
        m = self.m
        self.addCleanup(m.DICTEE.update, etat="absent")
        sons = []
        m.jouer_son = sons.append
        m.etat_dictee = lambda: {"etat": "erreur", "progres": 0.0}
        vus = self.espions()
        for _ in range(3):
            m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
            self.assertEqual(m.JARVIS["message"], m.phrase("transcription_reessaie", m.langue_du_mode()),
                             "il se taisait des la deuxieme fois")
        self.assertEqual(sons.count("erreur"), 3)
        self.assertEqual(vus, {"jarvis": [], "psy": []})
        # deux minutes plus tard, il le redit a voix haute
        dit = m.JARVIS["dictee_dite"]
        m.JARVIS["dictee_dite"] = dit - 121
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertGreater(m.JARVIS["dictee_dite"], dit - 121)

    def test_une_panne_de_moteur_se_dit_court_et_dans_sa_langue(self):
        """La phrase technique (150 caracteres, en francais meme en anglais)
        n'est plus lue : elle va au journal."""
        m = self.m
        m.CFG["jarvis_langue"] = "en"

        def panne(octets):
            raise m.DicteeImpossible("pas assez de memoire libre pour la dictee (900 Mo, il en faut 1500)",
                                     cle="memoire_pleine")
        m.transcrire = panne
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(m.JARVIS["message"], m.phrase("memoire_pleine", "en"))
        self.assertNotIn("Mo", m.JARVIS["message"])

    def test_le_moteur_froid_se_voit_au_panneau(self):
        m = self.m
        vus = []
        self.remplacer(dictee_possible=lambda: True)
        m.transcrire = lambda octets: vus.append(m.JARVIS["message"]) or "Jarvis, quelle heure est-il ?"
        self.espions()
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(vus, ["Je prepare la transcription..."])
        vus.clear()
        self.moteur_factice(vu=time.time())
        m.traiter_phrase(base64.b64encode(b"RIFF....").decode(), m.CFG)
        self.assertEqual(vus, ["Je transcris..."])

    def test_la_porteuse_part_avec_une_phrase_francaise(self):
        m = self.m
        self.addCleanup(m._PORTEUSE.update, fr=None, demande=0.0)
        self.addCleanup(m._VOIX_ENFANT.update, charge=None)
        m._PORTEUSE.update(fr=None, demande=0.0)
        m._VOIX_ENFANT["charge"] = "fr:kokoro:fr_jarvis"
        vus, envoye = [], []
        m.transcrire = lambda octets, porteuse=None: vus.append(porteuse) or "Non."
        # pas encore rendue : on la demande a la voix, au plus une fois par minute
        m.voix_prete = lambda cle=None: True
        m.envoyer_voix = lambda o: envoye.append(o) or True
        self.assertTrue(m.demander_porteuse(1000.0))
        self.assertEqual(envoye, [{"cmd": "rendre", "id": "porteuse", "cle": "fr", "texte": "Je vous écoute."}])
        self.assertFalse(m.demander_porteuse(1030.0))
        self.assertEqual(m.transcrire_phrase(b"RIFF", "fr"), "Non.")
        self.assertEqual(vus, [None])
        porteuse = J.wav_de(np.zeros(8000, np.int16)) if NUMPY else b""
        if not NUMPY:
            return
        self.assertTrue(m.recevoir_porteuse({"evt": "rendu", "cle": "fr",
                                             "wav": base64.b64encode(porteuse).decode()}))
        m.transcrire_phrase(b"RIFF", "fr")
        m.transcrire_phrase(b"RIFF", "en")
        self.assertEqual(vus[1:], [porteuse, None], "en francais seulement")
        self.assertFalse(m.demander_porteuse(2000.0), "deja la")
        # une autre voix chargee : cette porteuse ne vaut plus
        m._VOIX_ENFANT["charge"] = "fr:piper:gilles"
        self.assertIsNone(m.porteuse_pour("fr"))

    # ---------- ses nouveaux pouvoirs, dans Machi Tool ----------

    def pouvoirs(self, fichiers=True, windows=True):
        """Les mains ouvertes, un faux PC : un dossier personnel temporaire,
        une fausse corbeille. Rend (ex, maison, corbeille)."""
        m = self.m
        maison = tempfile.mkdtemp(dir=self.tmp)
        for d in ("Documents", "Desktop", "Downloads"):
            os.makedirs(os.path.join(maison, d))
        bac = tempfile.mkdtemp(dir=self.tmp)
        vrais = {k: getattr(m, k) for k in ("bases_dossiers", "envoyer_a_la_corbeille", "restaurer_de_la_corbeille")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        self.vrais_pouvoirs = vrais
        m.bases_dossiers = lambda: {"home": maison, "documents": os.path.join(maison, "Documents"),
                                    "desktop": os.path.join(maison, "Desktop"),
                                    "downloads": os.path.join(maison, "Downloads")}

        def jeter(ch):
            shutil.move(ch, os.path.join(bac, os.path.basename(ch)))

        def restaurer(ch):
            shutil.move(os.path.join(bac, os.path.basename(ch)), ch)
            return True
        m.envoyer_a_la_corbeille, m.restaurer_de_la_corbeille = jeter, restaurer
        m.CFG.update(jarvis_pc=True, jarvis_fichiers=fichiers, jarvis_windows=windows)
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        return ex, maison, bac

    def ecrire(self, chemin, contenu="bonjour\n"):
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)
        return chemin

    def test_ses_nouveaux_pouvoirs_sont_fermes_par_defaut(self):
        m = self.m
        for cle in ("jarvis_fichiers", "jarvis_windows", "jarvis_initiatives"):
            self.assertIs(m.CONFIG_DEFAUT[cle], False, cle)
        c = m.capacites_jarvis(m.CFG)
        self.assertEqual((c["fichiers"], c["windows"], c["initiatives"]), (False, False, False))
        m.CFG.update(jarvis_pc=True, jarvis_fichiers=True, jarvis_windows=True, jarvis_initiatives=True)
        c = m.capacites_jarvis(m.CFG)
        self.assertEqual((c["fichiers"], c["windows"], c["initiatives"]), (True, True, True))
        m.CFG["jarvis_pc"] = False
        c = m.capacites_jarvis(m.CFG)
        self.assertEqual((c["fichiers"], c["windows"]), (False, False), "sans ses mains, rien")
        # ...il peut se les donner, mais la personne confirme : le code s'il est
        # demande, sinon « oui ? » (voir test_il_se_donne_un_droit_si_tu_dis_oui)
        ex = lambda nom, e: m.executer_outil({"id": "x", "nom": nom, "entree": e}, m.CFG)
        pal = lambda cle: m._palier({"nom": "reglages_machi",
                                     "entree": {"action": "changer", "cle": cle, "valeur": "oui"}}, m.CFG)
        for cle in ("jarvis_fichiers", "jarvis_windows", "jarvis_initiatives"):
            m.CFG["jarvis_code_actif"] = False
            self.assertEqual(pal(cle), J.PALIER_OUI, cle)
            m.CFG["jarvis_code_actif"] = True
            self.assertEqual(pal(cle), J.PALIER_CODE, cle)
        self.assertEqual(pal("jarvis_repliques_spontanees"), J.PALIER_DIRECT)
        # une session de code ouverte ne le couvre jamais : la question, nommee
        m.CFG["jarvis_code_actif"] = True
        m.JARVIS["acces_jusqua"] = time.time() + 300
        self.assertEqual(pal("jarvis_fichiers"), J.PALIER_OUI)
        m.JARVIS["acces_jusqua"] = 0.0
        m.CFG["jarvis_code_actif"] = False
        m.CFG["jarvis_pc"] = True
        m.CFG["jarvis_fichiers"] = m.CFG["jarvis_windows"] = False
        self.assertIn("pas permis", ex("corbeille", {"chemin": "Documents\\a.txt"})["erreur"])
        self.assertIn("pas permis", ex("reglage_windows", {"reglage": "wifi", "action": "lire"})["erreur"])

    @unittest.skipIf(os.name == "nt", "hors Windows seulement")
    def test_hors_windows_une_erreur_claire(self):
        ex, _, _ = self.pouvoirs()
        for nom, e in (("reglage_windows", {"reglage": "wifi", "action": "activer"}),
                       ("reglage_windows", {"reglage": "sortie_audio", "action": "lister"}),
                       ("forcer_fermeture", {"cible": "Discord"}),
                       ("installer_appli", {"action": "chercher", "nom": "vlc"})):
            self.assertIn("Windows", ex(nom, e)["erreur"], nom)

    def test_ranger_les_fichiers_et_tout_annuler(self):
        m = self.m
        ex, maison, bac = self.pouvoirs()
        docs = os.path.join(maison, "Documents")
        a = self.ecrire(os.path.join(docs, "facture.txt"))
        os.makedirs(os.path.join(docs, "Factures"))
        # deplacer, puis annuler
        r = ex("deplacer", {"source": "Documents\\facture.txt", "destination": "Documents\\Factures"})
        self.assertIn("Deplace", r["texte"])
        self.assertTrue(os.path.isfile(os.path.join(docs, "Factures", "facture.txt")))
        self.assertIn("revenu", ex("annuler_fichier", {})["texte"])
        self.assertTrue(os.path.isfile(a))
        # renommer, puis annuler
        self.assertIn("Renomme", ex("renommer", {"chemin": "Documents\\facture.txt", "nouveau_nom": "f.txt"})["texte"])
        self.assertTrue(os.path.isfile(os.path.join(docs, "f.txt")))
        ex("annuler_fichier", {})
        self.assertTrue(os.path.isfile(a))
        # modifier (une copie d'avant), puis annuler
        r = ex("modifier_fichier", {"chemin": a, "remplacements": [{"avant": "bonjour", "apres": "bonsoir"}],
                                    "ajouter_a_la_fin": "merci"})
        self.assertIn("annulable", r["texte"])
        with open(a, encoding="utf-8") as f:
            self.assertEqual(f.read(), "bonsoir\nmerci")
        sauvegardes = os.listdir(m.dossier_sauvegardes())
        self.assertEqual(len(sauvegardes), 1)
        self.assertTrue(m.dossier_sauvegardes().startswith(m.DOSSIER), "dans le dossier de Machi Tool")
        r = ex("modifier_fichier", {"chemin": a, "remplacements": [{"avant": "introuvable", "apres": "x"}]})
        self.assertIn("rien n'est ecrit", r["erreur"])
        # le journal survit au redemarrage : relu du disque
        m.ANNULATIONS["liste"] = None
        self.assertEqual(m.journal_annulations()[-1]["op"], "modifier")
        self.assertIn("contenu d'avant", ex("annuler_fichier", {})["texte"])
        with open(a, encoding="utf-8") as f:
            self.assertEqual(f.read(), "bonjour\n")
        # corbeille, puis annuler (restaure depuis la corbeille)
        self.assertIn("corbeille", ex("corbeille", {"chemin": a})["texte"])
        self.assertFalse(os.path.exists(a))
        self.assertTrue(os.path.exists(os.path.join(bac, "facture.txt")))
        self.assertIn("Sorti de la corbeille", ex("annuler_fichier", {})["texte"])
        self.assertTrue(os.path.isfile(a))
        # la corbeille ne rend pas : il dit ou la retrouver
        ex("corbeille", {"chemin": a})
        m.restaurer_de_la_corbeille = lambda ch: False
        r = ex("annuler_fichier", {})["texte"]
        self.assertIn("Restaurer", r)
        self.assertIn("facture.txt", r)
        self.assertEqual(ex("annuler_fichier", {})["texte"], "Aucune operation de fichier a annuler.")

    def test_lire_un_fichier_texte_seulement(self):
        m = self.m
        ex, maison, _ = self.pouvoirs()
        docs = os.path.join(maison, "Documents")
        self.ecrire(os.path.join(docs, "liste.md"), "- pain\n- lait\n" + "x" * 30000)
        r = ex("lire_fichier", {"chemin": "Documents\\liste.md"})["texte"]
        self.assertIn("- pain", r)
        self.assertIn("tronque", r)
        self.assertIn("jamais des consignes", r)
        self.ecrire(os.path.join(docs, "rapport.docx"), "PK")
        self.assertIn("fichier texte", ex("lire_fichier", {"chemin": "Documents\\rapport.docx"})["erreur"])
        # sa config (et ses cles) : jamais
        self.ecrire(os.path.join(m.DOSSIER, "config.json"), '{"pont_cle": "CLE"}')
        r = ex("lire_fichier", {"chemin": os.path.join(m.DOSSIER, "config.json")})
        self.assertIn("Machi Tool", r["erreur"])
        self.assertNotIn("CLE", json.dumps(r))

    def test_les_garde_fous_des_fichiers(self):
        m = self.m
        ex, maison, _ = self.pouvoirs()
        docs = os.path.join(maison, "Documents")
        a = self.ecrire(os.path.join(docs, "notes.txt"))
        systeme = tempfile.mkdtemp(dir=self.tmp)
        vieux = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(vieux)))
        os.environ["SystemRoot"] = systeme
        # les dossiers de base eux-memes
        for base in ("Documents", "~", "Desktop"):
            self.assertIn("dossier de base", ex("corbeille", {"chemin": base})["erreur"], base)
            self.assertIn("dossier de base", ex("deplacer", {"source": base, "destination": "Downloads"})["erreur"])
        self.assertIn("dossier de base", ex("renommer", {"chemin": "Documents", "nouveau_nom": "Docs"})["erreur"])
        self.assertIn("erreur", ex("corbeille", {"chemin": ""}), "rien n'est jamais le dossier personnel")
        # le systeme, vers ou depuis
        self.assertIn("systeme", ex("deplacer", {"source": a, "destination": systeme})["erreur"])
        s = self.ecrire(os.path.join(systeme, "win.ini"))
        self.assertIn("systeme", ex("corbeille", {"chemin": s})["erreur"])
        self.assertIn("systeme", ex("modifier_fichier", {"chemin": s, "ajouter_a_la_fin": "x"})["erreur"])
        # Machi Tool
        c = self.ecrire(os.path.join(m.DOSSIER, "config.json"), "{}")
        self.assertIn("Machi Tool", ex("corbeille", {"chemin": c})["erreur"])
        self.assertIn("Machi Tool", ex("deplacer", {"source": a, "destination": m.DOSSIER})["erreur"])
        # une extension de programme
        self.assertIn("programme", ex("renommer", {"chemin": a, "nouveau_nom": "notes.bat"})["erreur"])
        self.assertIn("programme", ex("deplacer", {"source": a, "destination": os.path.join(docs, "n.ps1")})["erreur"])
        # modifier : un fichier texte seulement
        exe = self.ecrire(os.path.join(docs, "outil.exe"), "MZ")
        self.assertIn("fichier texte", ex("modifier_fichier", {"chemin": exe, "ajouter_a_la_fin": "x"})["erreur"])
        bat = self.ecrire(os.path.join(docs, "outil.bat"), "echo")
        self.assertIn("fichier texte", ex("modifier_fichier", {"chemin": bat, "ajouter_a_la_fin": "shutdown"})["erreur"])
        self.assertTrue(os.path.isfile(a), "rien n'a bouge")
        self.assertEqual(m.journal_annulations(), [])

    def test_la_corbeille_hors_windows_le_dit(self):
        m = self.m
        ex, maison, _ = self.pouvoirs()
        a = self.ecrire(os.path.join(maison, "Documents", "a.txt"))
        m.envoyer_a_la_corbeille = self.vrais_pouvoirs["envoyer_a_la_corbeille"]
        r = ex("corbeille", {"chemin": a})
        self.assertIn("Windows", r["erreur"])
        self.assertTrue(os.path.isfile(a), "jamais de suppression")

    def test_les_paliers_code_direct_oui(self):
        m = self.m
        envoyes, maison = self.mains([self.outil("deplacer", {"source": "Documents\\a.txt",
                                                              "destination": "Documents\\Rangement"}),
                                      {"texte": "Rangé.", "mode": "jarvis"},
                                      self.outil("reglage_windows", {"reglage": "wifi", "action": "lire"}, "t2"),
                                      {"texte": "Le Wi-Fi est actif.", "mode": "jarvis"},
                                      self.outil("lumiere", {"action": "couleur", "couleur": "rouge"}, "t3"),
                                      {"texte": "Rouge.", "mode": "jarvis"}])
        m.CFG.update(jarvis_fichiers=True, jarvis_windows=True)
        self.ecrire(os.path.join(maison, "Documents", "a.txt"))
        os.makedirs(os.path.join(maison, "Documents", "Rangement"))
        vrai = m.reglage_windows
        self.addCleanup(lambda: setattr(m, "reglage_windows", vrai))
        m.reglage_windows = lambda r, a="lire", appareil="": "Wi-Fi active."
        # les fichiers : le code
        self.phrase("Jarvis, range a.txt dans Rangement")
        self.assertEqual(self.dit[-1], "Code d'accès ?")
        self.assertTrue(os.path.isfile(os.path.join(maison, "Documents", "a.txt")), "rien avant le code")
        self.phrase("4 8 1 5")
        self.assertTrue(os.path.isfile(os.path.join(maison, "Documents", "Rangement", "a.txt")))
        # lire un reglage de Windows, la lumiere : directement, meme session fermee
        m.JARVIS["acces_jusqua"] = 0.0
        self.phrase("Jarvis, le wifi est allumé ?")
        self.assertEqual(envoyes[3]["resultats"][0]["texte"], "Wi-Fi active.")
        self.phrase("Jarvis, fais une ambiance de feu")
        self.assertIn("Guirlande", envoyes[5]["resultats"][0]["texte"])
        self.assertEqual(self.dit[-1], "Rouge.")
        self.assertEqual(self.dit.count("Code d'accès ?"), 1)

    def fermer_discord(self, reponses, **kw):
        m = self.m
        tues = []
        vrais = {k: getattr(m, k) for k in ("fenetres_ouvertes", "processus_ouverts", "terminer_processus")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        m.fenetres_ouvertes = lambda: [(1, "Discord", "Discord.exe"), (2, "Explorateur", "explorer.exe")]
        m.processus_ouverts = lambda: [(10, "Discord.exe"), (11, "Discord.exe"), (4, "explorer.exe")]
        m.terminer_processus = lambda pids: tues.extend(pids) or len(pids)
        envoyes, maison = self.mains(reponses, **kw)
        m.CFG.update(jarvis_fichiers=True, jarvis_windows=True)
        return envoyes, tues, maison

    def test_le_oui_avant_de_fermer_de_force(self):
        m = self.m
        envoyes, tues, _ = self.fermer_discord([self.outil("forcer_fermeture", {"cible": "Discord"}),
                                                {"texte": "Discord est fermé.", "mode": "jarvis"}], code_actif=False)
        self.phrase("Jarvis, Discord est planté, occupe-t'en")
        self.assertEqual(self.dit[-1], "Je ferme de force Discord ?")
        self.assertEqual(tues, [], "rien avant le oui")
        self.assertTrue(m.JARVIS["attente_oui"])
        self.phrase("Oui, vas-y.")
        self.assertEqual(sorted(tues), [10, 11])
        self.assertIn("Ferme de force", envoyes[1]["resultats"][0]["texte"])
        self.assertEqual(self.dit[-1], "Discord est fermé.")
        self.assertIsNone(m.JARVIS["attente_oui"])

    def test_il_se_donne_un_droit_si_tu_dis_oui(self):
        # « Fait en sorte que Jarvis puisse changer n'importe quel setting de l'application »
        m = self.m
        envoyes, _ = self.mains([self.outil("reglages_machi", {"action": "changer", "cle": "jarvis_fichiers",
                                                               "valeur": "oui"}),
                                 {"texte": "C'est fait : je range vos fichiers.", "mode": "jarvis"},
                                 self.outil("reglages_machi", {"action": "changer", "cle": "jarvis_windows",
                                                               "valeur": "oui"}),
                                 {"texte": "Bien, je n'y touche pas.", "mode": "jarvis"},
                                 self.outil("reglages_machi", {"action": "changer", "cle": "veille_minutes",
                                                               "valeur": "12"}),
                                 {"texte": "Douze minutes.", "mode": "jarvis"}], code_actif=False)
        m.CFG.update(jarvis_fichiers=False, jarvis_windows=False)
        self.phrase("Jarvis, donne-toi l'accès aux fichiers")
        self.assertEqual(self.dit[-1], "J'active l'accès aux fichiers ?")
        self.assertFalse(m.CFG["jarvis_fichiers"], "rien avant le oui")
        self.phrase("oui")
        self.assertTrue(m.CFG["jarvis_fichiers"])
        self.assertEqual(self.dit[-1], "C'est fait : je range vos fichiers.")
        self.phrase("Jarvis, prends aussi Windows")
        self.phrase("non")
        self.assertFalse(m.CFG["jarvis_windows"])
        self.assertEqual(envoyes[3]["resultats"][0]["erreur"], m.REFUS_OUI)
        # un reglage ordinaire : directement
        self.phrase("Jarvis, mets la veille à 12 minutes")
        self.assertEqual(m.CFG["veille_minutes"], 12)
        self.assertEqual(self.dit[-1], "Douze minutes.")

    def test_il_annonce_et_lance_une_mise_a_jour(self):
        # « Ainsi qu'annoncer une mise a jour (il peut la lancer) »
        m = self.m
        vrais = {k: getattr(m, k) for k in ("FIGE", "verifier_maj", "annoncer")}
        garde_maj = dict(m.MAJ)
        self.addCleanup(lambda: ([setattr(m, k, v) for k, v in vrais.items()], m.MAJ.update(garde_maj),
                                 m.DECLENCHER_MAJ.__setitem__(0, None), m.MAJ_ANNONCEES.clear()))
        m.MAJ_ANNONCEES.clear()
        dits = []
        m.annoncer = lambda texte, langue="fr": dits.append(texte) or True
        m.CFG.update(jarvis_actif=True, jarvis_annoncer_maj=True, jarvis_maj_a_voix_haute=True)
        self.addCleanup(m.CFG.__setitem__, "jarvis_maj_a_voix_haute", False)
        # l'annonce : une fois par version
        self.assertTrue(m.annoncer_maj("disponible", "9.9.9"))
        self.assertFalse(m.annoncer_maj("disponible", "9.9.9"))
        self.assertEqual(len(dits), 1)
        self.assertIn("9.9.9", dits[0])
        m.CFG["jarvis_annoncer_maj"] = False
        self.assertFalse(m.annoncer_maj("disponible", "9.9.10"), "decoche : il se tait")
        m.CFG["jarvis_annoncer_maj"] = True
        # « Me revoila » attend que sa voix soit prete
        n = len(m.ANNONCES)
        m.annoncer_maj("posee", "9.9.9")
        self.assertEqual(len(m.ANNONCES), n + 1)
        del m.ANNONCES[n:]
        # verifier : GitHub, et ce qu'il en dit
        def verifier(cfg):
            m.MAJ.update(etat="disponible", version="9.9.9", notes="La boule seule.",
                         message="Version 9.9.9 disponible (installee : %s)." % m.VERSION)
            return {"version": "9.9.9"}
        m.verifier_maj = verifier
        r = m.outil_mise_a_jour("verifier", m.CFG)
        self.assertIn("Nouvelle version : 9.9.9", r)
        self.assertIn("La boule seule.", r)
        # installer : « oui ? », puis le meme chemin que le bouton
        lances = []
        m.DECLENCHER_MAJ[0] = lances.append
        m.FIGE = True
        envoyes, _ = self.mains([self.outil("mise_a_jour", {"action": "installer"}),
                                 {"texte": "Je lance la mise à jour.", "mode": "jarvis"}], code_actif=False)
        self.phrase("Jarvis, installe la mise à jour")
        self.assertEqual(self.dit[-1], "J'installe Machi Tool 9.9.9 (il redémarre un instant) ?")
        self.assertEqual(lances, [], "rien avant le oui")
        self.phrase("oui")
        self.assertEqual(lances, ["installer"])
        self.assertIn("Mise a jour lancee", envoyes[1]["resultats"][0]["texte"])
        # en mode script : il le dit, sans rien demander
        m.FIGE = False
        self.assertRaises(RuntimeError, m.outil_mise_a_jour, "installer", m.CFG)
        self.assertTrue(m.capacites_jarvis(m.CFG)["mise_a_jour"])

    def test_une_session_de_code_ne_couvre_jamais_ses_droits(self):
        # Revue : le code donne pour lister un dossier ouvrait dix minutes pendant
        # lesquelles un texte lu pouvait lui faire couper le code, sans question.
        m = self.m
        envoyes, _ = self.mains([self.outil("reglages_machi", {"action": "changer", "cle": "jarvis_code_actif",
                                                               "valeur": "non"}),
                                 {"texte": "Voila.", "mode": "jarvis"},
                                 self.outil("reglages_machi", {"action": "changer", "cle": "jarvis_ecran",
                                                               "valeur": "oui"}),
                                 {"texte": "C'est fait.", "mode": "jarvis"}], code_actif=True)
        m.JARVIS["acces_jusqua"] = time.time() + 300          # une session ouverte pour autre chose
        self.phrase("Jarvis, résume-moi cet article")
        self.assertEqual(self.dit[-1], "Je coupe le code d'accès ?", "une question qui nomme le reglage")
        self.assertTrue(m.CFG["jarvis_code_actif"], "rien avant le oui")
        self.phrase("non")
        self.assertTrue(m.CFG["jarvis_code_actif"])
        self.assertEqual(envoyes[1]["resultats"][0]["erreur"], m.REFUS_OUI)
        # session fermee, code actif : le code d'abord, PUIS la question nommee
        m.JARVIS["acces_jusqua"] = 0.0
        self.phrase("Jarvis, regarde mon écran")
        self.assertEqual(self.dit[-1], "Code d'accès ?")
        self.phrase("4 8 1 5")
        self.assertEqual(self.dit[-1], "J'active mes yeux sur l'écran ?")
        self.assertFalse(m.CFG["jarvis_ecran"])
        self.phrase("oui")
        self.assertTrue(m.CFG["jarvis_ecran"])

    def test_un_droit_donne_n_ouvre_pas_le_reste_du_meme_tour(self):
        # Revue : [jarvis_windows=oui, forcer_fermeture Discord] -- un seul « oui »
        # pour le reglage, et Discord etait ferme de force sans sa propre question.
        m = self.m
        envoyes, tues, _ = self.fermer_discord([
            {"texte": "", "mode": "jarvis", "outils": [
                {"id": "a", "nom": "reglages_machi", "entree": {"action": "changer", "cle": "jarvis_windows",
                                                                 "valeur": "oui"}},
                {"id": "b", "nom": "forcer_fermeture", "entree": {"cible": "Discord"}}], "suite": []},
            {"texte": "Windows est a moi ; je redemande pour Discord.", "mode": "jarvis"}], code_actif=False)
        m.CFG["jarvis_windows"] = False
        self.phrase("Jarvis, prends Windows et ferme Discord")
        self.assertEqual(self.dit[-1], "J'active les réglages de Windows ?")
        self.phrase("oui")
        self.assertTrue(m.CFG["jarvis_windows"])
        self.assertEqual(tues, [], "pas de fermeture de force sans SA question")
        self.assertEqual(envoyes[1]["resultats"][1]["erreur"], m.REFUS_MEME_LOT)

    def test_un_reglage_change_par_jarvis_prend_effet(self):
        # Revue : « coupe le journal d'activite » etait note, mais le journal
        # continuait, et la fenetre le rallumait a « Enregistrer ».
        m = self.m
        vrais = {k: getattr(m, k) for k in ("demarrer_activite", "demarrer_api", "_en_fond")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        faits = []
        m.demarrer_activite = lambda cfg: faits.append(("activite", cfg.get("collecte_active")))
        m.demarrer_api = lambda cfg: faits.append(("api", cfg.get("api_active")))
        m._en_fond = lambda f: f()
        m.envoyer_oreille = lambda o: True
        m.REGLAGES_A_RELIRE.clear()
        m.CFG.update(collecte_active=True, collecte_envoi=True, api_active=True)
        m.outil_application("reglages_machi", {"action": "changer", "cle": "collecte_active", "valeur": "non"}, m.CFG)
        m.outil_application("reglages_machi", {"action": "changer", "cle": "api_active", "valeur": "non"}, m.CFG)
        self.assertEqual(faits, [("activite", False), ("api", False)])
        self.assertFalse(m.CFG["collecte_envoi"], "un seul interrupteur, comme dans la fenetre")
        self.assertTrue({"collecte_active", "collecte_envoi", "api_active"} <= m.REGLAGES_A_RELIRE)
        # rien ne bouge : rien a relancer
        faits.clear()
        m.outil_application("reglages_machi", {"action": "changer", "cle": "api_active", "valeur": "non"}, m.CFG)
        self.assertEqual(faits, [])
        m.JARVIS["acces_jusqua"] = time.time() + 300
        m.CFG["jarvis_pc"] = True
        m.outil_application("reglages_machi", {"action": "changer", "cle": "jarvis_pc", "valeur": "non"}, m.CFG)
        self.assertEqual(m.JARVIS["acces_jusqua"], 0.0, "ses mains fermees : la session aussi")
        m.REGLAGES_A_RELIRE.clear()

    def test_les_mises_a_jour_gardees(self):
        m = self.m
        vrais = {k: getattr(m, k) for k in ("FIGE", "verifier_maj", "annoncer")}
        garde_maj = dict(m.MAJ)
        self.addCleanup(lambda: ([setattr(m, k, v) for k, v in vrais.items()], m.MAJ.update(garde_maj),
                                 m.DECLENCHER_MAJ.__setitem__(0, None), m.MAJ_ANNONCEES.clear()))
        # une version qui attend d'etre posee ne redevient pas « disponible »
        verifs = []
        m.verifier_maj = lambda cfg: verifs.append(1)
        for etat in ("a_poser", "prete"):
            m.MAJ.update(etat=etat, version="9.9.9")
            m.outil_mise_a_jour("verifier", m.CFG)
            self.assertEqual(m.MAJ["etat"], etat)
        self.assertEqual(verifs, [])
        # la case decochee : ni proposee, ni lancee
        m.CFG["jarvis_annoncer_maj"] = False
        m.FIGE = True
        m.DECLENCHER_MAJ[0] = lambda q: self.fail("lancee malgre la case decochee")
        m.MAJ.update(etat="disponible")
        self.assertFalse(m.capacites_jarvis(m.CFG)["mise_a_jour"])
        self.assertRaises(RuntimeError, m.outil_mise_a_jour, "installer", m.CFG)
        self.assertRaises(RuntimeError, m.geste_oui, {"nom": "mise_a_jour", "entree": {"action": "installer"}})
        # et la recocher se confirme
        self.assertEqual(m._palier({"nom": "reglages_machi", "entree": {"action": "changer",
                                    "cle": "jarvis_annoncer_maj", "valeur": "oui"}}, m.CFG), J.PALIER_OUI)
        for cle in ("maj_installation_auto", "maj_verifier", "maj_prereleases"):
            self.assertEqual(J.palier_application("reglages_machi", {"action": "changer", "cle": cle}),
                             J.PALIER_POUVOIR, cle)
        # une annonce ne tombe ni chez le psychologue, ni pendant une question
        m.CFG.update(jarvis_annoncer_maj=True, jarvis_actif=True, jarvis_maj_a_voix_haute=True)
        self.addCleanup(m.CFG.__setitem__, "jarvis_maj_a_voix_haute", False)
        dits = []
        m.annoncer = lambda texte, langue="fr": dits.append(texte) or True
        m.MAJ_ANNONCEES.clear()
        m.JARVIS["mode"] = "psy"
        self.assertFalse(m.annoncer_maj("disponible", "9.9.9"))
        m.JARVIS["mode"] = "jarvis"
        m.JARVIS["attente_oui"] = {"tour_oui": 0}
        self.assertFalse(m.annoncer_maj("disponible", "9.9.9"))
        m.JARVIS["attente_oui"] = None
        self.assertTrue(m.annoncer_maj("disponible", "9.9.9"), "et plus tard, elle est dite")
        self.assertEqual(len(dits), 1)

    def test_une_mise_a_jour_se_pose_en_silence(self):
        # « fais en sorte que Jarvis puisse deployer des MAJ sans l'annoncer audiblement
        # (comme avant, sans qu'il parle) »
        m = self.m
        vrais = {k: getattr(m, k) for k in ("annoncer", "FIGE")}
        garde = {k: m.CFG.get(k) for k in ("jarvis_actif", "jarvis_annoncer_maj", "jarvis_maj_a_voix_haute")}
        self.addCleanup(lambda: ([setattr(m, k, v) for k, v in vrais.items()], m.CFG.update(garde),
                                 m.MAJ_ANNONCEES.clear(), m.DECLENCHER_MAJ.__setitem__(0, None)))
        self.assertIs(m.CONFIG_DEFAUT["jarvis_maj_a_voix_haute"], False, "en silence, par defaut")
        self.assertIs(m.CONFIG_DEFAUT["jarvis_annoncer_maj"], True, "mais il peut toujours les lancer")
        dits = []
        m.annoncer = lambda texte, langue="fr": dits.append(texte) or True
        m.MAJ_ANNONCEES.clear()
        m.CFG.update(jarvis_actif=True, jarvis_annoncer_maj=True)
        m.CFG.pop("jarvis_maj_a_voix_haute", None)              # une config d'avant n'a pas la cle
        n = len(m.ANNONCES)
        for quoi in ("disponible", "pose", "posee"):
            self.assertFalse(m.annoncer_maj(quoi, "9.9.9"), quoi)
        self.assertEqual((dits, len(m.ANNONCES)), ([], n), "ni « j'installe », ni « me revoila »")
        # il peut toujours la lancer, quand on la lui demande
        self.assertTrue(m.capacites_jarvis(m.CFG)["mise_a_jour"])
        m.FIGE = True
        lances = []
        m.DECLENCHER_MAJ[0] = lances.append
        self.addCleanup(m.MAJ.update, dict(m.MAJ))
        m.MAJ.update(etat="disponible", version="9.9.9")
        m.outil_mise_a_jour("installer", m.CFG)
        self.assertEqual(lances, ["installer"])
        # la case cochee : il retrouve la parole
        m.CFG["jarvis_maj_a_voix_haute"] = True
        self.assertTrue(m.annoncer_maj("pose", "9.9.9"))
        self.assertEqual(len(dits), 1)
        # un reglage simple, qu'il peut changer sans code ni « oui ? »
        self.assertTrue(J.reglage_modifiable("jarvis_maj_a_voix_haute", m.CONFIG_DEFAUT))
        self.assertIsNone(J.palier_application("reglages_machi", {"action": "changer",
                                                                  "cle": "jarvis_maj_a_voix_haute"}))

    def test_le_journal_et_son_envoi_un_seul_interrupteur(self):
        # Contre-revue : « J'active le journal d'activite ? » allumait aussi l'envoi
        # au site sans le nommer ; couper l'envoi seul decochait la case unique.
        m = self.m
        vrais = {k: getattr(m, k) for k in ("demarrer_activite",)}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        faits = []
        m.demarrer_activite = lambda cfg: faits.append(cfg.get("collecte_active"))
        envoyes, _ = self.mains([self.outil("reglages_machi", {"action": "changer", "cle": "collecte_active",
                                                               "valeur": "oui"}),
                                 {"texte": "C'est fait.", "mode": "jarvis"}], code_actif=False)
        m.CFG.update(collecte_active=False, collecte_envoi=False)
        self.phrase("Jarvis, active le journal d'activité")
        self.assertIn("envoi", self.dit[-1], "la question nomme l'envoi")
        self.phrase("oui")
        self.assertEqual((m.CFG["collecte_active"], m.CFG["collecte_envoi"]), (True, True))
        self.assertEqual(faits, [True])
        # l'envoi seul : c'est le meme interrupteur, le journal suit
        m.outil_application("reglages_machi", {"action": "changer", "cle": "collecte_envoi", "valeur": "non"}, m.CFG)
        self.assertEqual((m.CFG["collecte_active"], m.CFG["collecte_envoi"]), (False, False))
        self.assertEqual(faits, [True, False])
        m.REGLAGES_A_RELIRE.clear()

    def test_la_source_d_ecran_se_valide(self):
        # Contre-revue : « écran 2 » en toutes lettres faisait planter « Enregistrer ».
        D = {"ecran_source": "actif"}
        self.assertEqual(J.valeur_reglage("ecran_source", D, "écran 2"), 2)
        self.assertEqual(J.valeur_reglage("ecran_source", D, "2"), 2)
        self.assertEqual(J.valeur_reglage("ecran_source", D, "actif"), "actif")
        self.assertRaises(ValueError, J.valeur_reglage, "ecran_source", D, "deux")
        self.assertRaises(ValueError, J.valeur_reglage, "ecran_source", D, "0")

    def test_la_pose_ne_coupe_pas_une_seance(self):
        # Contre-revue : chez le psychologue, la pose partait sans un mot.
        m = self.m
        garde = {k: m.JARVIS.get(k) for k in ("mode", "etat")}
        self.addCleanup(lambda: m.JARVIS.update(garde))
        m.JARVIS.update(mode="psy", etat="ecoute")
        t0 = time.monotonic()
        m.attendre_jarvis_libre(borne=0.3, pas=0.01)
        self.assertGreaterEqual(time.monotonic() - t0, 0.3, "en seance : la pose attend")
        # et une fois posee, elle se dit (seule « disponible » se tait en seance)
        vrai = m.annoncer
        self.addCleanup(lambda: setattr(m, "annoncer", vrai))
        dits = []
        m.annoncer = lambda texte, langue="fr": dits.append(texte) or True
        m.MAJ_ANNONCEES.clear()
        m.CFG.update(jarvis_actif=True, jarvis_annoncer_maj=True, jarvis_maj_a_voix_haute=True)
        self.addCleanup(m.CFG.__setitem__, "jarvis_maj_a_voix_haute", False)
        self.assertTrue(m.annoncer_maj("pose", "9.9.9"))
        self.assertFalse(m.annoncer_maj("disponible", "9.9.9"))
        self.assertEqual(len(dits), 1)
        m.MAJ_ANNONCEES.clear()

    def test_je_reviens_attend_qu_il_ait_fini(self):
        m = self.m
        m.JARVIS["etat"] = "attente"
        t0 = time.monotonic()
        m.attendre_jarvis_libre(borne=5, pas=0.01)
        self.assertLess(time.monotonic() - t0, 0.5, "libre : pas d'attente")
        m.JARVIS["etat"] = "parle"
        t0 = time.monotonic()
        m.attendre_jarvis_libre(borne=0.3, pas=0.01)
        self.assertGreaterEqual(time.monotonic() - t0, 0.3, "il parle : on attend (borne)")
        m.JARVIS["etat"] = "attente"

    def test_les_annonces_attendent_sa_vraie_voix(self):
        # Revue : sous Windows, peut_parler() est toujours vrai -- « Me revoila »
        # partait dans la voix de Windows avant que la sienne soit chargee.
        m = self.m
        vrais = {k: getattr(m, k) for k in ("charges_voix", "voix_prete")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        vraie_peut = m.VOIX.peut_parler
        self.addCleanup(lambda: setattr(m.VOIX, "peut_parler", vraie_peut))
        dits = []
        vrai_dire = m.VOIX.dire
        self.addCleanup(lambda: setattr(m.VOIX, "dire", vrai_dire))
        m.VOIX.dire = lambda texte, fin=None, langue="fr", **k: dits.append(texte)
        m.VOIX.peut_parler = lambda: True
        m.charges_voix = lambda cfg: [{"cle": "fr"}]
        prete = {"v": False}
        m.voix_prete = lambda cle=None: prete["v"]
        m.CFG["jarvis_voix"] = True
        m.JARVIS["etat"] = "attente"
        del m.ANNONCES[:]
        m.ANNONCES.append(("Me revoilà, en version 9.9.9.", "fr", time.time()))
        m.dire_les_annonces()
        self.assertEqual(dits, [], "sa voix se charge : ca attend")
        prete["v"] = True
        m.dire_les_annonces()
        self.assertEqual(dits, ["Me revoilà, en version 9.9.9."])
        # jamais chargee : la voix de Windows la dit apres le delai
        prete["v"] = False
        m.ANNONCES.append(("Bonjour.", "fr", time.time() - m.ANNONCE_VOIX_ATTENTE_S - 1))
        m.dire_les_annonces()
        self.assertEqual(dits[-1], "Bonjour.")
        del m.ANNONCES[:]

    def test_le_oui_refuse_ou_autre_chose(self):
        m = self.m
        for reponse in ("non", "euh attends, quelle heure est-il ?"):
            self.dit.clear()
            envoyes, tues, _ = self.fermer_discord([self.outil("forcer_fermeture", {"cible": "Discord"}),
                                                    {"texte": "Très bien, je n'y touche pas.", "mode": "jarvis"}],
                                                   code_actif=False)
            self.phrase("Jarvis, Discord est planté, occupe-t'en")
            self.assertEqual(self.dit[-1], "Je ferme de force Discord ?")
            self.phrase(reponse)
            self.assertEqual(tues, [], reponse)
            self.assertEqual(envoyes[1]["resultats"][0]["erreur"], m.REFUS_OUI, reponse)
            self.assertEqual(self.dit[-1], "Très bien, je n'y touche pas.")

    def test_le_oui_expire(self):
        m = self.m
        envoyes, tues, _ = self.fermer_discord([self.outil("forcer_fermeture", {"cible": "Discord"}),
                                                {"texte": "Oui ?", "mode": "jarvis"}], code_actif=False)
        self.phrase("Jarvis, Discord est planté, occupe-t'en")
        m.JARVIS["attente_oui"]["expire"] = time.time() - 1
        m.veiller_initiatives(m.CFG)                  # la veille le laisse tomber
        self.assertIsNone(m.JARVIS["attente_oui"])
        self.phrase("Jarvis, oui")
        self.assertEqual(tues, [], "vingt secondes passees : rien")
        # un nouvel appel aussi l'efface
        m.JARVIS["attente_oui"] = {"tour_oui": m.JARVIS["tour"] - 1, "expire": time.time() + 20}
        self.assertFalse(m.oui_en_attente())

    def test_jamais_un_processus_du_systeme(self):
        m = self.m
        envoyes, tues, _ = self.fermer_discord([self.outil("forcer_fermeture", {"cible": "explorateur"}),
                                                {"texte": "Je ne peux pas.", "mode": "jarvis"}], code_actif=False)
        self.phrase("Jarvis, l'explorateur est planté, occupe-t'en")
        self.assertNotIn("Je ferme", " ".join(self.dit), "refuse d'avance : il ne demande rien")
        self.assertIn("jamais de force", envoyes[1]["resultats"][0]["erreur"])
        self.assertEqual(tues, [])

    def test_le_code_d_abord_puis_le_oui(self):
        m = self.m
        envoyes, tues, maison = self.fermer_discord([
            {"texte": "", "mode": "jarvis",
             "outils": [{"id": "a", "nom": "corbeille", "entree": {"chemin": "Documents\\vieux.txt"}},
                        {"id": "b", "nom": "forcer_fermeture", "entree": {"cible": "Discord"}}],
             "suite": [{"role": "user", "content": "x"}]},
            {"texte": "Voilà.", "mode": "jarvis"}])
        bac = []
        vrai = m.envoyer_a_la_corbeille
        self.addCleanup(lambda: setattr(m, "envoyer_a_la_corbeille", vrai))
        m.envoyer_a_la_corbeille = lambda ch: (bac.append(ch), os.remove(ch))
        v = self.ecrire(os.path.join(maison, "Documents", "vieux.txt"))
        self.phrase("Jarvis, fais le ménage comme convenu")
        self.assertEqual(self.dit[-1], "Code d'accès ?")
        self.phrase("4815")
        self.assertEqual(self.dit[-1], "Je ferme de force Discord ?")
        self.assertEqual((bac, tues), ([], []), "tout attend le oui")
        self.phrase("oui")
        self.assertEqual((bac, sorted(tues)), ([v], [10, 11]))
        self.assertEqual([r["id"] for r in envoyes[1]["resultats"]], ["a", "b"])
        self.assertEqual(self.dit[-1], "Voilà.")

    def test_installer_une_appli_avec_un_oui(self):
        m = self.m
        commandes, fonds = [], []
        vrais = {k: getattr(m, k) for k in ("_winget", "_en_fond")}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])

        def winget(args, delai):
            commandes.append(list(args))
            if args[0] == "search":
                if "shutdown" in args[1].lower():
                    return 0, "Name Id Version\n------------------\nShutdown Timer  Timer.Arret  1.0\n"
                return 0, ("Name              Id            Version\n------------------------------------\n"
                           "VLC media player  VideoLAN.VLC  3.0.21\n")
            return 0, "Installe"
        m._winget = winget
        m._en_fond = fonds.append
        installation = lambda: [f for f in fonds if "installer_appli" in f.__qualname__]
        envoyes, maison = self.mains([self.outil("installer_appli", {"action": "chercher", "nom": "vlc"}),
                                      {"texte": "Je trouve VLC.", "mode": "jarvis"},
                                      self.outil("installer_appli", {"action": "installer", "nom": "vlc"}, "t2"),
                                      {"texte": "C'est lancé.", "mode": "jarvis"},
                                      self.outil("installer_appli", {"action": "installer", "nom": "shutdown timer"}, "t3"),
                                      {"texte": "Non.", "mode": "jarvis"}], code_actif=False)
        m.CFG.update(jarvis_windows=True)
        self.phrase("Jarvis, occupe-toi de VLC")
        self.assertIn("VideoLAN.VLC", envoyes[1]["resultats"][0]["texte"], "chercher : directement")
        self.phrase("Jarvis, occupe-toi de VLC pour de bon")
        self.assertEqual(self.dit[-1], "J'installe VLC media player ?")
        self.assertFalse(any(c[0] == "install" for c in commandes))
        self.phrase("oui")
        self.assertEqual(len(installation()), 1)
        installation()[0]()                                # l'installation, en fond
        (install,) = [c for c in commandes if c[0] == "install"]
        self.assertEqual(install[:4], ["install", "--id", "VideoLAN.VLC", "--exact"])
        self.assertIn("--silent", install)
        self.assertFalse(any("--all" in c or "all" in c for c in commandes), "jamais tout d'un coup")
        self.assertEqual(self.dit[-1], "C'est fait : VLC media player est installé.")
        self.phrase("Jarvis, occupe-toi du minuteur")
        self.assertIn("ni fermer la session", envoyes[5]["resultats"][0]["erreur"])
        self.assertEqual(self.dit.count("J'installe VLC media player ?"), 1)
        self.assertEqual(len([d for d in self.dit if d.startswith("J'installe")]), 1, "pas de question")

    def initiative(self, t, **signaux):
        self.m.CFG["jarvis_langue"] = "fr"
        s = dict({"actif": True, "etat": "attente", "mode": "jarvis", "en_attente": False, "voix_occupee": False,
                  "plein_ecran": False, "calme_jusqua": 0.0, "heure": 15, "inactivite_s": 5}, **signaux)
        return self.m.veiller_initiatives(self.m.CFG, maintenant=t, signaux=s)

    def test_la_porte_des_initiatives(self):
        m = self.m
        t = time.time()
        chaud = {"temp_cpu": 96, "tjmax": 100}
        self.assertIsNone(self.initiative(t, **chaud), "pas permises par defaut")
        m.CFG["jarvis_initiatives"] = True
        for raison, s in (("psy", {"mode": "psy"}), ("plein ecran", {"plein_ecran": True}),
                          ("parle", {"voix_occupee": True}), ("calme", {"calme_jusqua": t + 60}),
                          ("absent", {"inactivite_s": 600}), ("code", {"en_attente": True})):
            self.assertIsNone(self.initiative(t, **dict(chaud, **s)), raison)
        m.INITIATIVES["actif_depuis"] = t - 3 * 3600
        self.assertIsNone(self.initiative(t, heure=2), "la nuit, pas de pause proposee")
        self.assertIn("pause", self.initiative(t, heure=15))
        m.INITIATIVES.update(recentes=[], deja={}, actif_depuis=None)
        # une seance grave : une heure de silence
        m.JARVIS["psy_grave"] = True
        self.initiative(t)
        m.JARVIS["psy_grave"] = False
        self.assertIsNone(self.initiative(t + 60, **chaud), "juste apres une seance grave")
        m.INITIATIVES["grave_jusqua"] = 0.0
        # la surchauffe parle, meme la nuit ; trois par heure au plus
        self.assertIn("processeur", self.initiative(t, heure=3, **chaud))
        self.assertIn("processeur", self.dit[-1], "annoncee (notification : la voix est coupee)")
        m.INITIATIVES["deja"].clear()
        self.assertTrue(self.initiative(t + 1, temp_gpu=95))
        m.INITIATIVES["deja"].clear()
        self.assertTrue(self.initiative(t + 2, **chaud))
        m.INITIATIVES["deja"].clear()
        self.assertIsNone(self.initiative(t + 3, **chaud), "plafond : trois par heure")
        m.INITIATIVES["deja"].clear()
        self.assertTrue(self.initiative(t + 3601, **chaud))

    def test_chaque_initiative_dans_machi_tool(self):
        m = self.m
        m.CFG["jarvis_initiatives"] = True
        regle = []
        vrai = m.regler_son
        self.addCleanup(lambda: setattr(m, "regler_son", vrai))
        m.regler_son = lambda action, appli="", niveau=None: regle.append((action, appli, niveau)) or "ok"
        t = time.time()
        # tard le soir, trop fort : il baisse a 40 % et le dit
        self.assertIsNone(self.initiative(t, heure=23, volume=55))
        self.assertEqual(self.initiative(t, heure=23, volume=80), "Il est tard : j'ai baissé le volume à 40 %.")
        self.assertEqual(regle, [("regler", "", 40)])
        self.assertEqual(self.dit[-1], "Il est tard : j'ai baissé le volume à 40 %.")
        self.assertIsNone(self.initiative(t + 60, heure=23, volume=80), "une fois par soiree")
        # deux heures sans pause : il la propose, une fois
        t = t + 10000
        m.INITIATIVES["actif_depuis"] = None
        self.assertIsNone(self.initiative(t))
        self.assertIn("pause", self.initiative(t + 2 * 3600 + 5))
        self.assertIsNone(self.initiative(t + 2 * 3600 + 900), "une seule fois")
        self.initiative(t + 3 * 3600, inactivite_s=900)                # une vraie pause
        self.initiative(t + 3 * 3600 + 10)
        self.assertIsNone(self.initiative(t + 4 * 3600))
        self.assertIn("pause", self.initiative(t + 5 * 3600 + 20))
        # sans signaux injectes (hors Windows) : rien ne casse
        m.INITIATIVES["deja"]["pause"] = t
        self.assertIsNone(m.veiller_initiatives(m.CFG))


class TranscriptionAncree(unittest.TestCase):
    """« Non » transcrit « Não », « Ouais » transcrit « Wait » : une porteuse
    francaise devant la reponse ancre la langue ; on ne garde que ce qui suit."""

    def test_le_texte_apres_la_porteuse(self):
        jetons = ["▁Je", "▁vous", "▁é", "coute", ".", "▁Non", "."]
        dates = [0.1, 0.3, 0.5, 0.6, 1.2, 1.9, 2.1]
        self.assertEqual(J.texte_apres(jetons, dates, 1.6), "Non.")
        # le point final de la porteuse deborde la coupure
        self.assertEqual(J.texte_apres(jetons, dates, 1.1), "Non.")
        # onnx-asr a deja change « ▁ » en espace
        self.assertEqual(J.texte_apres([" Oui", ",", " mer", "ci", "."], [2.0, 2.2, 2.3, 2.4, 2.5], 1.6),
                         "Oui, merci.")
        self.assertEqual(J.texte_apres(jetons, dates, 5.0), "")
        self.assertEqual(J.texte_apres(None, None, 0), "")

    def test_seulement_pour_une_parole_courte(self):
        self.assertTrue(J.parole_courte([]))
        self.assertTrue(J.parole_courte([3.1, 3.3]))
        self.assertFalse(J.parole_courte([0.5, 0.9, 1.3, 1.8]))
        # mesure : le point de « Não. » est date 1,5 s apres le mot
        self.assertTrue(J.parole_courte([1.0, 2.6], jetons=["▁Não", "."]))

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_reconnaitre_ancre_seulement_ce_qui_est_court(self):
        class R:
            def __init__(self, texte, jetons, dates):
                self.text, self.tokens, self.timestamps = texte, jetons, dates

        class Faux:
            """Sans contexte, il derive ; avec la porteuse (un son plus long), il lit juste."""
            def __init__(self, court=True):
                self.court, self.sons = court, []

            def with_timestamps(self):
                return self

            def recognize(self, son, sample_rate=16000):
                self.sons.append(len(son))
                if len(self.sons) == 1:
                    if not self.court:
                        return R("Non c'est bon.", [" Non", " c", "'", "est", " bon", "."], [1.0, 1.4, 1.5, 1.7, 2.2, 2.6])
                    return R("Não.", [" Não", "."], [2.0, 2.2])
                t0 = porteuse_s
                return R("Je vous écoute. Non.", [" Je", " vous", " écoute", ".", " Non", "."],
                         [0.1, 0.3, 0.5, t0 + 0.05, t0 + 0.4, t0 + 0.6])
        porteuse_s = 1.0
        son = np.zeros(16000 * 3, np.float32)
        son[32000:36000] = 0.3
        porteuse = np.full(16000, 0.5, np.float32)
        f = Faux()
        self.assertEqual(J.reconnaitre(f, son, 16000, porteuse), "Non.")
        # la porteuse est pres du mot : le son d'avant (l'attente) est coupe
        self.assertLess(f.sons[1], len(porteuse) + len(son))
        f = Faux(court=False)
        self.assertEqual(J.reconnaitre(f, son, 16000, porteuse), "Non c'est bon.")
        self.assertEqual(len(f.sons), 1, "une phrase longue ne paie pas un second passage")
        class Nu:
            def recognize(self, son, sample_rate=16000):
                return "Não."
        self.assertEqual(J.reconnaitre(Nu(), son, 16000, None), "Não.", "sans porteuse, comme avant")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_porteuse_rendue_en_memoire(self):
        class Syn:
            frequence, langue = 24000, "fr"

            def phrases(self, texte, lenteur=1.0):
                yield np.full(12000, 1000, np.int16)
                yield np.full(12000, -1000, np.int16)
        w = J.rendre_en_memoire(Syn(), "Je vous écoute.")
        with wave.open(io.BytesIO(w)) as ww:
            self.assertEqual((ww.getframerate(), ww.getnframes()), (16000, 16000))

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
#  ROBUSTESSE ET DIAGNOSTIC : le chronometre, la patience, les echecs
# ======================================================================

class RobustesseEtDiagnostic(unittest.TestCase):
    """« Il met une plombe a repondre », « je lui parle et plus rien » : ou
    passe le temps d'un echange, ce qu'il fait quand BrainDebugger tarde, et
    ce qu'on sait d'un echec."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.m = charger_module(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        DansMachiTool.setUp(self)
        m = self.m
        m.CHRONO["courant"] = None
        m.CHRONOS.clear()
        m._EN_VOL.clear()
        del m._JARVIS_TRAVAIL[:]
        m.CFG["jarvis_langue"] = "fr"
        m._TRAVAIL_COURANT.update(tour=None, t=0.0)
        m._GARDE.update(cle=None, sans_raison=None)
        m._ONGLETS_AVANCE.update(fil=None, boite=None, t=0.0)
        m.VOIX = m.Voix()
        m.VOIX.disponible = False
        self.sons = []
        m.jouer_son = self.sons.append
        consts = ("PATIENCE_S", "PATIENCE_REDIRE_S", "PATIENCE_DIRE_S", "ATTENTE_BD_MAX_S", "REESSAI_BD_S",
                  "_requete_bd", "extension_branchee", "commande_onglets")
        vrais = {k: getattr(m, k) for k in consts}
        self.addCleanup(lambda: [setattr(m, k, v) for k, v in vrais.items()])
        vraie = urllib.request.urlopen
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", vraie))
        m.REESSAI_BD_S = 0.0

    def tearDown(self):
        DansMachiTool.tearDown(self)

    def journal(self, faire):
        import contextlib
        sortie = io.StringIO()
        with contextlib.redirect_stdout(sortie):
            faire()
        return sortie.getvalue()

    # --- le chronometre ---

    def test_chaque_echange_est_chronometre_sans_rien_de_dit(self):
        import socket as socket_
        m = self.m

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            time.sleep(0.05)
            sur_debut("Volontiers.")
            time.sleep(0.05)
            return {"texte": "Volontiers. Un pingouin entre dans un bar.", "mode": "jarvis"}
        dits, _ = DansMachiTool._voix_et_bd(self, bd)
        m.transcrire = lambda octets: "Jarvis, raconte-moi une blague sur les pingouins"
        m.JARVIS["reveil_verifie"] = True
        m.traiter_evenement({"evt": "phrase", "wav": base64.b64encode(b"RIFF....").decode(),
                             "pause": 0.75, "fin_t": time.time() - 0.75})
        item = m._JARVIS_TRAVAIL.pop(0)

        def echange():
            m.traiter_phrase(item["wav"], m.CFG, tour=item["tour"])
            # la voix : la premiere phrase, puis la suite -- et c'est fini
            a, b = socket_.socketpair()
            for ev in ({"evt": "debut", "id": 1}, {"evt": "fini", "id": 1},
                       {"evt": "debut", "id": 2}, {"evt": "fini", "id": 2}):
                J.envoyer(a, ev)
            a.close()
            m._lire_voix(b)
            b.close()
        journal = self.journal(echange)
        self.assertEqual([d["id"] for d in dits()], [1, 2])
        self.assertEqual(len(m.CHRONOS), 1, journal)
        r = m.CHRONOS[-1]
        self.assertEqual((r["chemin"], r["issue"]), ("bd", "dit"))
        for k in ("fin_de_phrase", "transcription", "contexte", "bd", "bd_fin", "voix", "premier_son", "total"):
            self.assertIsNotNone(r[k], k)
            self.assertGreaterEqual(r[k], 0.0, k)
        self.assertGreaterEqual(r["fin_de_phrase"], 0.7)
        self.assertGreaterEqual(r["bd"], 0.04, "BrainDebugger : jusqu'a sa premiere phrase")
        self.assertGreaterEqual(r["bd_fin"], r["bd"])
        self.assertGreaterEqual(r["premier_son"], r["fin_de_phrase"] + r["bd"])
        self.assertLessEqual(r["premier_son"], r["total"])
        ligne = [x for x in journal.splitlines() if "echange de" in x]
        self.assertEqual(len(ligne), 1, journal)
        for mot in ("blague", "pingouin", "Volontiers", "bar"):
            self.assertNotIn(mot, ligne[0], "le journal ne garde jamais ce qui a ete dit")
        self.assertRegex(m.texte_dernier_echange(),
                         r"^Dernier echange \(\d\d:\d\d\) : fin de phrase 0,[78] s · transcription \d+,\d s · "
                         r"(contexte \d+,\d s · )?BrainDebugger 0,\d s · voix \d+,\d s -- premier son a \d+,\d s\.$")

    def test_le_chronometre_ne_grossit_pas(self):
        m = self.m
        def echanges():
            for i in range(25):
                m.JARVIS["tour"] = i
                m.noter_temps("phrase", 0.5)
                m.noter_temps("transcrit")
            m.clore_temps("dit")
        self.journal(echanges)
        self.assertEqual(len(m.CHRONOS), 10)
        self.assertEqual([r["issue"] for r in m.CHRONOS][-2:], ["interrompu", "dit"])
        m.noter_temps("voix")                     # plus d'echange en cours : rien
        self.assertIsNone(m.CHRONO["courant"])

    # --- quand BrainDebugger tarde ---

    def test_il_patiente_d_un_petit_son_quand_bd_tarde(self):
        m = self.m
        m.PATIENCE_S, m.PATIENCE_REDIRE_S, m.PATIENCE_DIRE_S = 0.1, 10.0, 100.0
        m._requete_bd = lambda chemin, charge, cfg, delai, sur_debut=None: (
            time.sleep(0.45), {"texte": "Voila.", "mode": "jarvis"})[1]
        tour = m.JARVIS["tour"]
        self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, tour))
        self.assertEqual(self.sons.count("patience"), 1, self.sons)
        self.assertEqual(self.dit, ["Voila."])

        def bd(chemin, charge, cfg, delai, sur_debut=None):
            sur_debut("Alors.")
            time.sleep(0.45)
            return {"texte": "Alors. Voila.", "mode": "jarvis"}
        self.sons.clear()
        m._requete_bd = bd
        self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, tour))
        self.assertNotIn("patience", self.sons, "sa premiere phrase est la : pas de signe")

    def test_un_instant_une_fois_si_ca_dure(self):
        m = self.m
        dits, _ = DansMachiTool._voix_et_bd(self, lambda chemin, charge, cfg, delai, sur_debut=None: (
            time.sleep(0.7), {"texte": "Voila.", "mode": "jarvis"})[1])
        m.PATIENCE_S, m.PATIENCE_REDIRE_S, m.PATIENCE_DIRE_S = 0.1, 0.1, 0.2
        tour = m.JARVIS["tour"]

        def ecouter_la_voix():
            # la voix dit vite : « fini » arrive avant le signe suivant
            while not m.VOIX.attentes:
                time.sleep(0.01)
            m.VOIX.fini(min(m.VOIX.attentes), False)
        threading.Thread(target=ecouter_la_voix, daemon=True).start()
        self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, tour))
        textes = [d["texte"] for d in dits()]
        self.assertEqual(textes.count("Un instant."), 1, textes)
        self.assertEqual(textes[-1], "Voila.")

    def test_bd_muet_il_laisse_tomber_et_le_dit(self):
        m = self.m
        m.ATTENTE_BD_MAX_S = 0.3
        m._requete_bd = lambda chemin, charge, cfg, delai, sur_debut=None: time.sleep(3) or {"texte": "trop tard"}
        t0 = time.monotonic()
        journal = self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, m.JARVIS["tour"]))
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertEqual(m.JARVIS["message"], "BrainDebugger ne répond pas.")
        self.assertIn("BDMuet", m.JARVIS["derniere_erreur"][1])
        self.assertIn("BDMuet", journal)

    def test_une_requete_abandonnee_est_fermee(self):
        m = self.m
        fermee, lu = threading.Event(), threading.Event()

        class Bloquee:
            headers = {"Content-Type": "application/x-ndjson"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def __iter__(self):
                yield b'{"debut": "Alors."}\n'
                lu.set()
                fermee.wait(5)             # BrainDebugger ecrit encore la suite

            def close(self):
                fermee.set()
        urllib.request.urlopen = lambda req, **k: Bloquee()
        tour = m.JARVIS["tour"]
        threading.Timer(0.3, lambda: m.JARVIS.update(tour=tour + 1)).start()
        with self.assertRaises(m.Annule):
            m._requete_bd_annulable("/api/machitool/jarvis", {"texte": "x"}, m.CFG, 5, tour, sur_debut=lambda t: None)
        self.assertTrue(lu.is_set())
        self.assertTrue(fermee.wait(1.0), "la requete orpheline est fermee")
        for _ in range(50):
            if not m._EN_VOL:
                break
            time.sleep(0.02)
        self.assertEqual(m._EN_VOL, {}, "le fil n'y reste pas pendu")

    def test_il_reessaie_seulement_quand_c_est_sur(self):
        import http.client
        m = self.m
        appels = []

        def ouvrir(erreurs):
            def faux(req, timeout=None, context=None):
                appels.append(req)
                if erreurs:
                    raise erreurs.pop(0)
                return FausseReponse(json.dumps({"texte": "Voila."}).encode())
            return faux

        def essai(*erreurs):
            appels.clear()
            urllib.request.urlopen = ouvrir(list(erreurs))
            res = {}

            def faire():
                try:
                    res["r"] = m._requete_bd("/x", {"a": 1}, m.CFG, 5)
                except BaseException as e:
                    res["r"] = type(e).__name__
            self.journal(faire)
            return res["r"], len(appels)
        # la connexion n'a pas pu se faire : rien n'est parti, il reessaie
        self.assertEqual(essai(urllib.error.URLError(ConnectionRefusedError())), ({"texte": "Voila."}, 2))
        self.assertEqual(essai(urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))),
                         ({"texte": "Voila."}, 2))
        # une page 502 du bord de Railway (pas du JSON), tout de suite : il reessaie
        page = urllib.error.HTTPError("/x", 502, "Bad Gateway", {}, io.BytesIO(b"<html>Application failed</html>"))
        self.assertEqual(essai(page), ({"texte": "Voila."}, 2))
        # une erreur de BrainDebugger lui-meme, une coupure apres l'envoi : jamais
        bd = urllib.error.HTTPError("/x", 502, "Bad Gateway", {}, io.BytesIO(b'{"error": "claude"}'))
        self.assertEqual(essai(bd), ("HTTPError", 1))
        self.assertEqual(essai(http.client.RemoteDisconnected("fermee")), ("RemoteDisconnected", 1))
        self.assertEqual(essai(urllib.error.URLError(ConnectionResetError())), ("URLError", 1))
        # une seule fois
        self.assertEqual(essai(urllib.error.URLError(ConnectionRefusedError()),
                               urllib.error.URLError(ConnectionRefusedError())), ("URLError", 2))

    # --- les echecs ---

    def test_un_echec_dit_court_et_garde_la_cause(self):
        m = self.m

        def panne(e):
            def bd(chemin, charge, cfg, delai, sur_debut=None):
                raise e
            return bd
        m._requete_bd = panne(urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed")))
        journal = self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, m.JARVIS["tour"]))
        self.assertEqual(m.JARVIS["message"], "Je n'arrive pas à joindre BrainDebugger.")
        self.assertIn("gaierror", journal)
        self.assertIn("getaddrinfo failed", m.texte_derniere_erreur())
        m._requete_bd = panne(socket.timeout("timed out"))
        self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, m.JARVIS["tour"]))
        self.assertEqual(m.JARVIS["message"], "BrainDebugger ne répond pas.", "un silence n'est pas « injoignable »")
        self.assertIn("timed out", m.texte_derniere_erreur())
        self.assertEqual(m.texte_derniere_erreur(time.time() + 3600), "", "une demi-heure, pas plus")

    def test_une_panne_de_transcription_se_dit_dans_la_langue(self):
        # en anglais, la voix anglaise lisait 160 signes de francais technique
        m = self.m
        m.CFG["jarvis_langue"] = "en"

        def casse(octets):
            raise m.DicteeImpossible("le moteur de dictee s'est arrete en pleine transcription")
        m.transcrire = casse
        self.journal(lambda: m.traiter_phrase(base64.b64encode(b"RIFF").decode(), m.CFG))
        self.assertEqual(m.JARVIS["message"], "Sorry, I couldn't make that out.")
        self.assertIn("moteur de dictee", m.JARVIS["derniere_erreur"][1])

    # --- avant la question ---

    def test_le_contexte_ssl_se_construit_une_fois(self):
        import ssl
        m = self.m
        n = []
        vraie = ssl.create_default_context
        self.addCleanup(lambda: setattr(ssl, "create_default_context", vraie))
        ssl.create_default_context = lambda *a, **k: n.append(1) or vraie(*a, **k)
        m._oublier_contexte_ssl()
        with mock_urlopen(m, {"texte": "Voila."}):
            m._requete_bd("/x", {"a": 1}, m.CFG, 5)
            apres_un = len(n)
            m._requete_bd("/x", {"a": 1}, m.CFG, 5)
        self.assertGreaterEqual(apres_un, 1)
        self.assertEqual(len(n), apres_un, "le magasin de certificats n'est pas relu a chaque question")
        self.assertIs(m._contexte_ssl(), m._contexte_ssl())

    def test_les_onglets_ne_retardent_pas_la_question(self):
        m = self.m
        m.CFG["jarvis_pc"] = True
        m.extension_branchee = lambda: True
        lent = {"s": 1.5}
        m.commande_onglets = lambda quoi, **k: time.sleep(lent["s"]) or {
            "onglets": [{"titre": "Lo-fi beats", "url": "https://www.youtube.com/watch?v=1"}]}
        vus = []
        m._requete_bd = lambda chemin, charge, cfg, delai, sur_debut=None: (
            vus.append((time.monotonic(), charge["onglets_ouverts"])), {"texte": "Voila.", "mode": "jarvis"})[1]
        t0 = time.monotonic()
        self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, m.JARVIS["tour"]))
        self.assertLess(vus[-1][0] - t0, 0.8, "l'extension lente ne fait plus attendre la question")
        self.assertEqual(vus[-1][1], "")
        # demandee pendant la transcription, elle est la a temps
        lent["s"] = 0.05
        m.lancer_onglets(m.CFG)
        time.sleep(0.2)
        self.journal(lambda: m.parler_a_jarvis("une question", m.CFG, m.JARVIS["tour"]))
        self.assertIn("Lo-fi beats", vus[-1][1])

    # --- le garde-fou des etats ---

    def test_un_etat_sans_raison_revient_a_l_attente(self):
        m = self.m
        m.JARVIS.update(etat="parle", message="Je reponds.")
        self.assertFalse(m.surveiller_etats(100.0), "un etat tout neuf a sa chance")
        self.assertFalse(m.surveiller_etats(101.0))
        journal = self.journal(lambda: self.assertTrue(m.surveiller_etats(105.1)))
        self.assertIn("garde-fou", journal)
        self.assertEqual(m.JARVIS["etat"], "attente")

    def test_un_etat_qui_a_une_raison_reste(self):
        m = self.m
        m.JARVIS.update(etat="pense", message="Jarvis reflechit...")
        m._TRAVAIL_COURANT["tour"] = m.JARVIS["tour"]            # il y travaille
        for t in range(0, 40, 1):
            self.assertFalse(m.surveiller_etats(200.0 + t))
        m._TRAVAIL_COURANT["tour"] = None
        m.VOIX.attentes[7] = None                              # il a encore a dire
        m.JARVIS.update(etat="parle", message="Je reponds.")
        for t in range(0, 40, 1):
            self.assertFalse(m.surveiller_etats(300.0 + t))
        m.VOIX.attentes.clear()
        self.assertFalse(m.surveiller_etats(341.0))
        self.assertTrue(m.surveiller_etats(346.0))

    def test_rappele_pendant_les_outils_il_ne_repasse_pas_a_pense(self):
        # « Jarvis, qu'est-ce qui joue ? » -- un outil lent -- « Jarvis » : la
        # boule restait sur « il reflechit » jusqu'au prochain appel
        m = self.m
        tour = m.JARVIS["tour"]
        m.JARVIS.update(tour=tour + 1, etat="ecoute", message="Je vous ecoute.")
        with self.assertRaises(m.Annule):
            m.continuer_jarvis({"texte": "x", "suite": [], "conv": tour, "tour": 1}, [], m.CFG)
        self.assertEqual(m.JARVIS["etat"], "ecoute")
        # et si l'etat etait deja ecrit trop tard, le garde-fou le rattrape
        m.JARVIS.update(etat="pense", message="Jarvis agit...")
        m.surveiller_etats(0.0)
        m.surveiller_etats(1.0)
        self.journal(lambda: m.surveiller_etats(11.5))
        self.assertEqual(m.JARVIS["etat"], "attente")


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
        # la voix humaine (Silero VAD), comme sur le PC, quand le modele est la
        o.det.vad = J.charger_vad(MODELES)
        o.configurer({"gabarits": list(gabarits)})
        return o, sorties

    @staticmethod
    def ecouter(o, sorties, trames, texte=None):
        """Les trames, une a une ; un appel pas net est verifie comme Machi Tool
        le fait (la transcription contient-elle son nom ?) -- ici, le texte dit."""
        for x in trames:
            n = len(sorties)
            o.trame(x)
            if any(e["evt"] == "verifier" for e in sorties[n:]):
                o.commande({"cmd": "verifie", "ok": bool(texte) and J.contient_nom(texte)})

    def reveils(self, o, sorties, son, texte=None):
        self.ecouter(o, sorties, flux(son), texte)
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
            r = self.reveils(o, s, dire(texte, vitesse=vitesse), texte)
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
            r = self.reveils(o, s, dire(texte, vitesse=vitesse, hauteur=hauteur), texte)
            self.assertEqual([e["par"] for e in r], ["voix"], texte)
        for texte in ("j'arrive", "Travis", "service", "jardin", "java", "bonjour comment ça va",
                      "je vais dormir", "garage", "ça va vite", "j'avais dit", "il pleut sur la ville",
                      "Jacques a dit", "j'ai un avis", "t'as vu ?", "Charles vise", "archives",
                      "j'arrive vite", "Gervais", "tu arrives ?"):
            o, s = self.oreille(gabarits)
            self.assertEqual(self.reveils(o, s, dire(texte)), [], texte)

    def test_jarvis_seul_laisse_le_temps_de_parler(self):
        """« Il galere a comprendre » : « Jarvis » dit seul comptait ses propres
        premieres syllabes comme une demande deja dite, et l'ecoute se fermait
        au bout de 2 s. Seul : 5 s pour parler ; dans une phrase : c'est dit."""
        o, sorties = self.oreille()
        gabarits = []
        for texte, vitesse, hauteur in (("Jarvis", 130, 45), ("Jarvis", 150, 50), ("Jarvis", 170, 55)):
            sorties.clear()
            for x in flux(np.zeros(1))[:10]:
                o.trame(x)
            o.commande({"cmd": "apprendre"})
            for x in flux(dire(texte, vitesse=vitesse, hauteur=hauteur))[8:]:
                o.trame(x)
                if any(e["evt"] == "gabarit" for e in sorties):
                    break
            gabarits.append([e for e in sorties if e["evt"] == "gabarit"][0]["vecteurs"])
        for vitesse in (110, 150, 190):
            o, s = self.oreille(gabarits)
            self.reveils(o, s, dire("Jarvis", vitesse=vitesse), "Jarvis")
            r = [e for e in s if e["evt"] == "reveil"]
            self.assertEqual([e["attente"] for e in r], [5.0], vitesse)
        o, s = self.oreille(gabarits)
        self.reveils(o, s, dire("baisse le son de Spotify, Jarvis", vitesse=165), "baisse le son de Spotify, Jarvis")
        self.assertEqual([e["attente"] for e in s if e["evt"] == "reveil"], [J.PHRASE_DEJA_DITE_S])

    def test_des_tons_differents_et_dans_une_phrase(self):
        """« Mieux etalonner les Jarvis, que je puisse l'appeler avec beaucoup
        de tons differents ou dans une phrase. » Six tons appris (a plat, en
        question, fort, bas) ; puis appele sur d'autres tons, en debut ou en
        fin de phrase -- et toujours rien sur les mots voisins."""
        o, sorties = self.oreille()
        gabarits = []
        for texte, vitesse, hauteur, fort in (("Jarvis", 130, 45, 1), ("Jarvis", 150, 50, 1), ("Jarvis", 170, 55, 1),
                                              ("Jarviis ?", 125, 55, 1), ("Jarvis !", 165, 65, 1.8),
                                              ("jarvis", 150, 35, 0.35)):
            sorties.clear()
            for x in flux(np.zeros(1))[:10]:
                o.trame(x)
            o.commande({"cmd": "apprendre"})
            for x in flux(dire(texte, vitesse=vitesse, hauteur=hauteur) * fort)[8:]:
                o.trame(x)
                if any(e["evt"] == "gabarit" for e in sorties):
                    break
            gabarits.append([e for e in sorties if e["evt"] == "gabarit"][0]["vecteurs"])

        def entendu(texte, vitesse=150, hauteur=50):
            o, s = self.oreille(gabarits)
            o.configurer({"hey": False})
            self.ecouter(o, s, flux(dire(texte, vitesse=vitesse, hauteur=hauteur)) + flux(np.zeros(40000)), texte)
            return [e["evt"] for e in s if e["evt"] in ("reveil", "phrase", "vide")]
        for texte, vitesse, hauteur in (("Jarvis", 120, 30), ("Jarvis", 190, 70), ("Jarvis ?", 140, 75),
                                        ("JARVIS", 160, 60), ("Jaaarvis", 130, 50), ("Jarvis", 200, 50)):
            self.assertEqual(entendu(texte, vitesse, hauteur)[:1], ["reveil"], (texte, vitesse, hauteur))
        for texte in ("baisse le son de Spotify, Jarvis", "Jarvis baisse le son", "tu peux baisser le son Jarvis ?",
                      "mets la musique Jarvis"):
            self.assertEqual(entendu(texte, 165), ["reveil", "phrase"], texte)
        for texte in ("j'arrive", "Travis", "service", "jardin", "java", "garage", "j'avais dit", "Jacques a dit",
                      "Charles vise", "archives", "Gervais", "tu arrives ?", "on part en vacances demain",
                      "j'ai vu Marvin hier"):
            self.assertEqual(entendu(texte), [], texte)

    def test_tres_tolerant_au_mot_jarvis(self):
        """« Il ne se declenche pas assez : il faudrait qu'il soit tres tolerant
        au mot Jarvis. » Des « Jarvis » difficiles (tres grave, tres aigu, tres
        bas, tres lent) : ratés en strict, entendus en tolerant -- nets ou a
        verifier. Les mots voisins, eux, ne le reveillent jamais directement."""
        o, sorties = self.oreille()
        gab = []
        for texte, vitesse, hauteur in (("Jarvis", 130, 45), ("Jarvis", 150, 50), ("Jarvis", 170, 55),
                                        ("Jarvis", 140, 48), ("Jarvis", 160, 52)):
            sorties.clear()
            for x in flux(np.zeros(1))[:10]:
                o.trame(x)
            o.commande({"cmd": "apprendre"})
            for x in flux(dire(texte, vitesse=vitesse, hauteur=hauteur))[8:]:
                o.trame(x)
                if any(e["evt"] == "gabarit" for e in sorties):
                    break
            gab.append([e for e in sorties if e["evt"] == "gabarit"][0]["vecteurs"])

        def entendu(texte, vitesse, hauteur, fort, tolerant):
            o, s = self.oreille(gab)
            o.configurer({"tolerant": tolerant, "hey": False})
            for x in flux(dire(texte, vitesse=vitesse, hauteur=hauteur) * fort) + flux(np.zeros(20000)):
                o.trame(x)
            ev = [e["evt"] for e in s if e["evt"] in ("reveil", "verifier")]
            return ev[0] if ev else "-"
        durs = [("Jarvis", 100, 20, 0.25), ("Jarvis", 200, 80, 1.0), ("Jarvis", 100, 80, 0.25),
                ("Jarvis", 200, 20, 0.25), ("jarvis", 90, 25, 0.2), ("JARVIS !", 190, 75, 2.0)]
        stricts = [entendu(*d, tolerant=False) for d in durs]
        tolerants = [entendu(*d, tolerant=True) for d in durs]
        self.assertGreater(sum(r != "-" for r in tolerants), sum(r != "-" for r in stricts))
        self.assertGreaterEqual(sum(r != "-" for r in tolerants), len(durs) - 1)
        for texte in ("j'arrive", "Travis", "service", "jardin", "garage", "Gervais", "on part en vacances demain"):
            self.assertNotEqual(entendu(texte, 150, 50, 1.0, True), "reveil", texte)

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

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_un_micro_muet_ou_change_est_rouvert(self):
        """« Au bout d'un moment il ne se detecte plus » : un micro qui ne rend
        que des zeros, ou le micro de Windows qui change, et le flux s'arrete
        -- l'oreille le rouvre."""
        import types
        etat = {"defaut": self.Micro("{A}", "Casque"), "son": 0.0}
        test = self

        class Enregistreur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def record(self, numframes):
                return np.full((numframes, 1), etat["son"], dtype=np.float32)

        test.Micro.recorder = lambda self, **k: Enregistreur()
        self.addCleanup(lambda: delattr(test.Micro, "recorder"))
        faux = types.SimpleNamespace(all_microphones=lambda: [etat["defaut"]],
                                     default_microphone=lambda: etat["defaut"])
        vrai = sys.modules.get("soundcard")
        sys.modules["soundcard"] = faux
        self.addCleanup(lambda: sys.modules.__setitem__("soundcard", vrai) if vrai else sys.modules.pop("soundcard"))
        horloge = {"t": 0.0}
        vraie = J.time.monotonic
        J.time.monotonic = lambda: horloge["t"]
        self.addCleanup(lambda: setattr(J.time, "monotonic", vraie))

        def lire(n):
            flux, lus = J.micro_windows(""), 0
            for _ in flux:
                lus += 1
                horloge["t"] += 0.08
                if lus >= n:
                    return lus, False
            return lus, True                   # le flux s'est arrete de lui-meme
        etat["son"] = 0.1
        self.assertEqual(lire(1000), (1000, False), "un vrai son : il continue")
        etat["son"] = 0.0
        lus, fini = lire(10000)
        self.assertTrue(fini)
        self.assertAlmostEqual(lus * 0.08, J.MICRO_MUET_S, delta=1.0)
        etat["son"] = 0.1
        flux = J.micro_windows("")
        next(flux)
        horloge["t"] += J.MICRO_VERIFIE_S + 1
        etat["defaut"] = self.Micro("{B}", "Webcam")      # Windows a change de micro
        self.assertEqual(list(flux), [], "il s'arrete pour rouvrir le nouveau")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_pret_seulement_une_fois_le_micro_ouvert(self):
        """Un micro refuse (confidentialite de Windows) : « pret » partait avant
        l'ouverture, et effacait l'erreur qui suivait, toutes les 3 s."""
        import types

        def refuse(self, **k):
            raise OSError("acces refuse")
        test = self
        test.Micro.recorder = refuse
        self.addCleanup(lambda: delattr(test.Micro, "recorder"))
        m = self.Micro("{A}", "Casque")
        faux = types.SimpleNamespace(all_microphones=lambda: [m], default_microphone=lambda: m)
        vrai = sys.modules.get("soundcard")
        sys.modules["soundcard"] = faux
        self.addCleanup(lambda: sys.modules.__setitem__("soundcard", vrai) if vrai else sys.modules.pop("soundcard"))
        annonces = []
        with self.assertRaises(OSError):
            next(J.micro_windows("", lambda n, ok: annonces.append(n)))
        self.assertEqual(annonces, [])

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
        # « Jarvis n'est plus detecte, et le micro non plus » : au redemarrage du PC, un autre
        # identifiant (pilote mis a jour, autre port USB) -- son nom, retenu, le retrouve
        self.assertEqual(J.choisir_micro(tous, "{Z}", defaut, "Micro casque"), (a, True))
        yeti = self.Micro("{Y2}", "Microphone (2- Blue Yeti)")
        avec = lambda: [a, b, yeti]
        self.assertEqual(J.choisir_micro(avec, "{Y1}", defaut, "Microphone (Blue Yeti)"), (yeti, True),
                         "Windows l'a renumerote : « 2- » devant son nom")
        self.assertEqual(J.choisir_micro(avec, "{Y1}", defaut, "microphone ( 3-  blue yeti)"), (yeti, True))
        self.assertEqual(J.choisir_micro(avec, "{Y1}", defaut, "Micro USB"), (a, False), "un autre nom : absent")
        self.assertEqual(J.choisir_micro(avec, "{Y1}", defaut, ""), (a, False), "sans nom retenu : comme avant")
        self.assertEqual(J.choisir_micro(avec, "{C}", defaut, "Microphone (Blue Yeti)"), (yeti, True))
        self.assertEqual(J.choisir_micro(lambda: [a, c], "{C}", defaut, "Micro casque"), (c, True),
                         "l'identifiant passe avant le nom")

    def test_l_oreille_change_de_micro_sans_redemarrer(self):
        ouverts = []

        retenus = []

        def faux_micro(nom="", annoncer=None, nom_retenu=""):
            ouverts.append(nom)
            retenus.append(nom_retenu)
            if annoncer and nom == "{VIEUX}":        # retrouve par son nom, sous un autre identifiant
                annoncer(nom_retenu, True, "{NEUF}")
            elif annoncer:
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
            self.assertEqual(attendre_pret(), {"evt": "pret", "micro": "Micro {A}", "trouve": True, "vad": False},
                             "le micro des reglages des la premiere ouverture")
            J.envoyer(conn, {"cmd": "config", "micro": "{B}"})
            self.assertEqual(attendre_pret()["micro"], "Micro {B}")
            J.envoyer(conn, {"cmd": "config", "micro": "absent"})
            self.assertFalse(attendre_pret()["trouve"])
            # « Jarvis n'est plus detecte » : un nouvel identifiant au redemarrage, le nom le retrouve
            J.envoyer(conn, {"cmd": "config", "micro": "{VIEUX}", "micro_nom": "Micro casque"})
            ev = attendre_pret()
            self.assertTrue(ev["trouve"])
            self.assertEqual(ev["micro_id"], "{NEUF}", "Machi Tool apprend son nouvel identifiant")
            self.assertEqual(retenus[-1], "Micro casque")
            conn.close()
            fil.join(10)
            self.assertFalse(fil.is_alive())
            self.assertEqual(ouverts, ["{A}", "{B}", "absent", "{VIEUX}"], "jamais le mauvais micro d'abord")
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
            # la transcription prete (sans elle, un reveil ne fait plus parler
            # dans le vide depuis la v1.65) -- sans lancer de vrai moteur
            m.etat_dictee = lambda: {"etat": "pret", "progres": 1.0}
            m.prechauffer_dictee = lambda: None
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
            item = m._JARVIS_TRAVAIL[0]
            wav64, apres_coupure = item["wav"], item["apres_coupure"]
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
        self.assertEqual([e["evt"] for e in evts if e["evt"] != "dit"], ["debut", "fini"])
        self.assertTrue(evts[-1]["coupe"])
        self.assertEqual(evts[-1]["reste"], "Tous les systemes sont operationnels. Autre chose ?")
        self.assertEqual(len(hp.morceaux), 15)
        evts.clear()
        self.bouche = J.Bouche(syn, evts.append, FauxHautParleur())
        self.bouche.dire(10, "Bonjour. Au revoir.")
        self.assertEqual(evts[-1], {"evt": "fini", "id": 10, "coupe": False}, "rien a reprendre quand il a fini")
        self.assertEqual(syn.lues[-2:], ["Bonjour.", "Au revoir."], "une phrase a la fois")
        # les sous-titres : chaque phrase dit quand elle commence et combien elle dure
        dits = [e for e in evts if e["evt"] == "dit"]
        self.assertEqual([(e["id"], e["phrase"]) for e in dits], [(10, 0), (10, 1)])
        self.assertAlmostEqual(dits[0]["duree"], 16000 / float(syn.frequence), places=2)
        self.assertLess(evts.index(dits[0]), evts.index(evts[-1]))

    def test_les_phrases(self):
        self.assertEqual(J.decouper_phrases("Good evening. All systems go! Is 3.5 enough? Yes\u2026 Fine"),
                         ["Good evening.", "All systems go!", "Is 3.5 enough?", "Yes\u2026", "Fine"])
        self.assertEqual(J.decouper_phrases(""), [])


class HautParleurEnTempsReel(FauxHautParleur):
    """Joue au rythme du son (un dixieme de seconde prend un dixieme de
    seconde), note quand chaque morceau commence, et compte ses ouvertures.
    `panne` : les numeros de morceaux (a partir de 1) ou play() leve."""

    def __init__(self, panne=(), temps_reel=True):
        FauxHautParleur.__init__(self)
        self.debuts, self.ouvertures, self.panne, self.temps_reel, self.n = [], 0, set(panne), temps_reel, 0

    def __enter__(self):
        self.ouvertures += 1
        return self

    def play(self, data):
        self.n += 1
        if self.n in self.panne or "toujours" in self.panne:
            raise RuntimeError("AUDCLNT_E_DEVICE_INVALIDATED")
        self.debuts.append(time.time())
        self.morceaux.append(len(data))
        if self.temps_reel:
            time.sleep(len(data) / float(self.frequence))


class SyntheseLente(SyntheseFactice):
    """Une seconde de son par phrase, calculee en `cout` secondes ; `rate` :
    la phrase qui ne se calcule pas."""

    def __init__(self, cout=0.6, rate=None):
        SyntheseFactice.__init__(self)
        self.cout, self.rate = cout, rate

    def phrases(self, texte, lenteur=1.0, **kw):
        self.lues.append(texte)
        if self.rate and self.rate in texte:
            raise RuntimeError("onnxruntime")
        time.sleep(self.cout)
        yield (np.sin(np.arange(16000) / 5.0) * 8000).astype(np.int16)


def _voix_enfant_de_test(test, lecteur, syn=None):
    """Le processus de la voix, dans un fil, sur une vraie socket ; sa synthese
    chargee par un « charger » (Phonemiseur et Synthese remplaces)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    fil = threading.Thread(target=J.voix_enfant, args=(srv.getsockname()[1], "S3CRET", lecteur), daemon=True)
    fil.start()
    c, _ = srv.accept()
    srv.close()
    c.recv(4 + len("S3CRET"))
    test.addCleanup(lambda: (J.envoyer(c, None), c.close(), fil.join(5)))
    return c, fil


@unittest.skipUnless(NUMPY, "numpy absent")
class LaVoixEnchaine(unittest.TestCase):
    """« Un blanc d'une seconde entre sa premiere phrase et la suite », « il
    se tait puis le carillon, comme s'il avait repondu », « la voix francaise
    jamais chargee »."""

    def setUp(self):
        vrais = (J.Phonemiseur, J.Synthese)
        self.addCleanup(lambda: (setattr(J, "Phonemiseur", vrais[0]), setattr(J, "Synthese", vrais[1])))
        self.syn = SyntheseLente()

        class Ph:
            def __init__(ph, *a, **k):
                time.sleep(0.3)                      # une voix qui se charge
        J.Phonemiseur = Ph
        J.Synthese = lambda *a, **k: self.syn

    def evenements(self, c, jusqu_a, delai=15):
        evts = []
        fin = time.time() + delai
        c.settimeout(delai)
        while time.time() < fin:
            e = J.recevoir(c)
            if e is None:
                break
            evts.append(e)
            if jusqu_a(e):
                break
        return evts

    def test_la_suite_se_calcule_pendant_que_la_premiere_phrase_sonne(self):
        hp = HautParleurEnTempsReel()
        c, fil = _voix_enfant_de_test(self, hp)
        J.envoyer(c, {"cmd": "charger", "cle": "fr", "bibliotheque": "", "donnees": "", "modele": "x"})
        self.assertEqual(J.recevoir(c)["evt"], "pret")
        J.envoyer(c, {"cmd": "dire", "id": 1, "texte": "Très bien, monsieur."})
        time.sleep(0.1)
        J.envoyer(c, {"cmd": "dire", "id": 2, "texte": "Le minuteur est lancé."})
        evts = self.evenements(c, lambda e: e.get("evt") == "fini" and e.get("id") == 2)
        self.assertEqual([(e["evt"], e["id"]) for e in evts if e["evt"] != "dit"],
                         [("debut", 1), ("fini", 1), ("debut", 2), ("fini", 2)])
        # 10 dixiemes de son + 2 de silence par phrase ; le blanc entre les deux
        # textes est celui d'entre deux phrases, pas le calcul de la suite
        self.assertEqual(len(hp.debuts), 24)
        blanc = hp.debuts[12] - (hp.debuts[11] + 0.1)
        self.assertLess(blanc, 0.25, "%.2f s de blanc entre la premiere phrase et la suite" % blanc)
        self.assertEqual(hp.ouvertures, 1, "le haut-parleur reste ouvert entre les deux")

    def test_taire_ne_jette_pas_une_voix_qui_se_charge(self):
        c, fil = _voix_enfant_de_test(self, HautParleurEnTempsReel(temps_reel=False))
        J.envoyer(c, {"cmd": "charger", "cle": "en", "bibliotheque": "", "donnees": "", "modele": "x"})
        J.envoyer(c, {"cmd": "charger", "cle": "fr", "bibliotheque": "", "donnees": "", "modele": "x"})
        J.envoyer(c, {"cmd": "dire", "id": 1, "texte": "Jetee."})
        J.envoyer(c, {"cmd": "taire"})           # « Jarvis » dit pendant qu'elles se chargent
        evts = self.evenements(c, lambda e: e.get("cle") == "fr", delai=5)
        self.assertEqual([(e["evt"], e.get("cle")) for e in evts], [("pret", "en"), ("pret", "fr")])
        self.assertEqual(self.syn.lues, [], "le texte qui attendait, lui, est jete")

    def test_une_phrase_qui_ne_se_calcule_pas(self):
        syn, evts, hp = SyntheseLente(cout=0.0, rate="Deux"), [], HautParleurEnTempsReel(temps_reel=False)
        J.Bouche(syn, evts.append, hp).dire(3, "Un. Deux. Trois.")
        self.assertEqual(evts[-1], {"evt": "fini", "id": 3, "coupe": False, "rate": True, "reste": "Deux. Trois."})
        self.assertIn("erreur", [e["evt"] for e in evts])

    def test_le_haut_parleur_change_en_route(self):
        # un casque debranche : on rouvre celui de Windows, et on continue
        syn, evts = SyntheseLente(cout=0.0), []
        hp = HautParleurEnTempsReel(panne={5}, temps_reel=False)
        J.Bouche(syn, evts.append, hp).dire(4, "Un. Deux.")
        self.assertEqual(evts[-1], {"evt": "fini", "id": 4, "coupe": False})
        self.assertEqual(len(hp.morceaux), 24, "rien de perdu")
        self.assertEqual(hp.ouvertures, 2)

    def test_plus_de_haut_parleur_du_tout(self):
        syn, evts = SyntheseLente(cout=0.0), []
        avant = threading.active_count()
        hp = HautParleurEnTempsReel(panne={"toujours"}, temps_reel=False)
        J.Bouche(syn, evts.append, hp).dire(5, "Un. Deux. Trois. Quatre. Cinq. Six.")
        self.assertEqual(evts[-1], {"evt": "fini", "id": 5, "coupe": False, "rate": True,
                                    "reste": "Un. Deux. Trois. Quatre. Cinq. Six."})
        fin = time.time() + 2
        while threading.active_count() > avant and time.time() < fin:
            time.sleep(0.05)
        self.assertEqual(threading.active_count(), avant, "le calcul ne reste pas bloque pour toujours")

    def test_taire_arrete_aussi_ce_qui_se_calculait(self):
        b = J.Bouche(SyntheseLente(cout=0.2), lambda e: None, HautParleurEnTempsReel(temps_reel=False))
        t1, t2 = b.preparer(1, "Un. Deux."), b.preparer(2, "Trois.")
        b.taire()
        self.assertTrue(t1["arret"].is_set() and t2["arret"].is_set())
        # le texte suivant ne ranime pas ceux qu'on a coupes
        b.dire(3, "Quatre.")
        self.assertTrue(t1["arret"].is_set())


class LesNombresSeDisent(unittest.TestCase):
    """« 45.5 », « 6:30 », « 1,500 », « 3,5 », « 14h », « 45°C », « M. Dupont »."""

    def test_une_ponctuation_collee_ne_coupe_pas(self):
        ph = J.Phonemiseur.__new__(J.Phonemiseur)
        ph._proposition = lambda t: t
        for t in ("Your GPU is at 45.5 degrees.", "It's 6:30 in the evening.", "That's 1,500 euros.",
                  "Il fait 3,5 degrés."):
            self.assertEqual(len(ph.phrases(t)), 1, t)
        self.assertEqual([unicodedata.normalize("NFC", "".join(p))
                          for p in ph.phrases("Bonjour, monsieur. Ça va ? Oui : bien.")],
                         ["Bonjour, monsieur.", "Ça va?", "Oui: bien."])
        self.assertEqual(ph.phrases("..."), [])

    @unittest.skipUnless(bibli_de_test(), "espeak-ng absent")
    def test_espeak_lit_le_nombre_entier(self):
        en = J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, "en")
        self.assertIn("pɔɪnt", "".join(en.phrases("Your GPU is at 45.5 degrees.")[0]))
        fr = J.Phonemiseur(bibli_de_test(), PIPER_DOSSIER, "fr")
        self.assertIn("viʁɡyl", unicodedata.normalize("NFC", "".join(fr.phrases("Il fait 3,5 degrés.")[0])))

    def test_le_texte_pour_la_voix(self):
        self.assertEqual(J.texte_pour_piper("à 14h."), "à 14 heures.")
        self.assertEqual(J.texte_pour_piper("à 1h du matin"), "à 1 heure du matin")
        self.assertEqual(J.texte_pour_piper("Il est 14h05."), "Il est 14 heures 05.")
        self.assertEqual(J.texte_pour_piper("2 hommes, 3 heures"), "2 hommes, 3 heures")
        self.assertEqual(J.texte_pour_piper("Il fait 45°C."), "Il fait 45 degrés.")
        self.assertEqual(J.texte_pour_piper("It's 45° outside.", "en"), "It's 45 degrees outside.")
        self.assertEqual(J.decouper_phrases(J.texte_pour_piper("M. Dupont arrive. Bien.")),
                         ["monsieur Dupont arrive.", "Bien."])
        self.assertEqual(J.texte_pour_piper("Mr. Smith is here.", "en"), "Mister Smith is here.")
        self.assertEqual(J.texte_pour_piper("Voici :\n1. Ouvre Spotify.\n2. Lance la musique."),
                         "Voici : Ouvre Spotify. Lance la musique.")


@unittest.skipUnless(NUMPY, "numpy absent")
class LeMajordomeJazzy(unittest.TestCase):
    """« Un petit peu de jazz » : sa boule et son panneau jouent avec SA voix,
    pas avec un sinus -- l'enveloppe part avec chaque phrase."""

    def test_chaque_phrase_part_avec_son_enveloppe(self):
        syn = SyntheseFactice()
        hp, evts = FauxHautParleur(), []
        J.Bouche(syn, evts.append, hp).dire(3, "Bonsoir monsieur. Un peu de musique ?")
        dits = [e for e in evts if e["evt"] == "dit"]
        self.assertEqual(len(dits), 2)
        for d in dits:
            self.assertEqual(d["pas"], J.VOIX_ENVELOPPE_PAS)
            self.assertEqual(len(d["env"]), int(np.ceil(d["duree"] / d["pas"] - 1e-9)), "une valeur par 50 ms")
            self.assertTrue(all(isinstance(v, int) and 0 <= v <= 99 for v in d["env"]))
            self.assertGreater(min(d["env"]), 60, "un son soutenu : haut")
        self.assertEqual(len(hp.morceaux), 2 * 12, "la lecture garde ses tranches de 100 ms et ses 0,2 s de blanc")
        self.assertEqual([e["evt"] for e in evts if e["evt"] != "dit"], ["debut", "fini"])
        json.dumps(evts)                                   # passe tel quel dans la prise

    def test_l_enveloppe(self):
        f = 24000
        self.assertEqual(J.enveloppe_voix(np.zeros(f, np.int16), f), [0] * 20, "le silence : zero")
        self.assertEqual(J.enveloppe_voix(np.zeros(0, np.int16), f), [])
        fort = (np.sin(np.arange(f) / 3.0) * 26000).astype(np.int16)
        son = np.concatenate([fort[:f // 2], np.zeros(f // 2 + 100, np.int16)])
        env = J.enveloppe_voix(son, f)
        self.assertEqual(len(env), 21, "la derniere tranche, entamee, compte")
        self.assertTrue(all(v >= 95 for v in env[:10]), env)
        self.assertEqual(env[10:], [0] * 11)
        faible = J.enveloppe_voix((fort // 30).astype(np.int16), f)
        self.assertTrue(20 < faible[5] < env[5], "plus doux, plus bas")

    def test_le_niveau_a_l_instant(self):
        env, pas = [0, 0, 99, 99, 0, 0, 0, 0], 0.05
        niv = lambda t: J.niveau_enveloppe(env, pas, t)
        self.assertEqual(niv(-0.01), 0.0, "avant sa voix : rien")
        self.assertEqual(niv(0.05), 0.0)
        self.assertAlmostEqual(niv(0.14), 1.0, places=6, msg="le pic sur les tranches fortes")
        self.assertLess(niv(0.101), 0.2, "l'attaque, courte")
        # la relache : il retombe, doucement, sans remonter
        chute = [niv(0.2 + k * 0.03) for k in range(10)]
        self.assertTrue(all(a > b for a, b in zip(chute, chute[1:])), chute)
        self.assertGreater(chute[1], 0.5)
        self.assertLess(chute[-1], 0.2)
        self.assertEqual(niv(5.0), 0.0, "longtemps apres : rien")
        self.assertEqual(J.niveau_enveloppe([], pas, 0.1), 0.0)
        # sans memoire : le meme instant, le meme niveau, quelle que soit la cadence
        self.assertEqual(niv(0.23), niv(0.23))

    def test_le_swing_et_les_touches(self):
        T = J.JAZZ_TEMPS_S
        # la croche longue (sur le temps) puis la courte, aux 2/3 du temps : ternaire
        self.assertAlmostEqual(J.niveau_swing(0.0), 1.0)
        self.assertGreater(J.niveau_swing(2 * T / 3 + 0.001), J.niveau_swing(2 * T / 3 - 0.001))
        self.assertLess(J.niveau_swing(2 * T / 3 + 0.001), J.niveau_swing(T + 0.001), "l'accent est sur le temps")
        self.assertTrue(all(0.35 <= J.niveau_swing(k * 0.013) <= 1.0 for k in range(200)))
        self.assertEqual(J.touches_piano(0.0, 1.0), [0.0] * 7, "au silence, tout repose")
        t = J.touches_piano(1.0, 0.0)
        self.assertEqual([i for i, v in enumerate(t) if v == 1.0], [0, 1, 3], "Dm7 : re, fa, do")
        self.assertEqual(len(J.touches_piano(0.5, 0.0, 12)), 12)
        self.assertNotEqual(J.touches_piano(1.0, 0.0), J.touches_piano(1.0, 2 * T), "l'accord change")

    def test_les_barres_du_panneau_suivent_sa_voix(self):
        allume = lambda im: int((im[:44].max(axis=2) > 0).sum())
        muet, fort = J.image_jarvis("parle", 1.0, niveau=0.0), J.image_jarvis("parle", 1.0, niveau=1.0)
        self.assertGreater(allume(fort), allume(muet) + 100, "sa voix leve les barres")
        self.assertTrue(np.any(np.all(fort[:44] == np.array(J.LED_COULEURS["ambre"], np.uint8), axis=2)))
        self.assertGreater(int((muet[50:57].max(axis=2) > 0).sum()), 40, "SPEAKING, toujours")
        st0 = J.image_jarvis("parle", 1.0, sous_titre="Bien", niveau=0.0)
        st1 = J.image_jarvis("parle", 1.0, sous_titre="Bien", niveau=1.0)
        self.assertGreater(allume(st1[:14]), allume(st0[:14]), "au-dessus du sous-titre aussi")
        self.assertTrue(np.array_equal(J.image_jarvis("parle", 1.0), J.image_jarvis("parle", 1.0, niveau=None)),
                        "sans niveau : le sinus d'avant")


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
        self.assertAlmostEqual(int(np.max(np.abs(premiere))), int(J.VOIX_CRETE * 32767), delta=2,
                               msg="crete normalisee (80 % : pas d'ecretage au reechantillonnage)")

    def test_la_bouche_parle_par_morceaux_et_se_tait(self):
        hp = FauxHautParleur()
        evts = []
        self.bouche = J.Bouche(self.syn, evts.append, hp)
        self.bouche.dire(7, "Bonjour. Tous les systèmes sont opérationnels.")
        self.assertEqual([e["evt"] for e in evts if e["evt"] != "dit"], ["debut", "fini"])
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
        ev = J.recevoir(c)
        while ev.get("evt") == "dit":          # ou il en est, phrase par phrase (les sous-titres)
            ev = J.recevoir(c)
        self.assertEqual(ev, {"evt": "fini", "id": 1, "coupe": False})
        J.envoyer(c, None)
        c.close()
        fil.join(5)
        self.assertFalse(fil.is_alive())

    def test_la_porteuse_rendue_par_le_processus_de_la_voix(self):
        """La porteuse de la transcription (« Non » lu « Não ») : dite en
        memoire par la voix francaise, a 16 kHz -- jamais au haut-parleur."""
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
        J.envoyer(c, {"cmd": "rendre", "id": "porteuse", "cle": "fr", "texte": "Je vous écoute."})
        ev = J.recevoir(c)
        self.assertEqual((ev["evt"], ev["id"], ev["cle"]), ("rendu", "porteuse", "fr"))
        with wave.open(io.BytesIO(base64.b64decode(ev["wav"]))) as w:
            self.assertEqual(w.getframerate(), 16000)
            self.assertGreater(w.getnframes(), 8000)
        self.assertEqual(hp.morceaux, [], "la porteuse ne passe pas par le haut-parleur")
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
        evts = [e["evt"] for e in sorties if e["evt"] not in ("voix_niveau", "essai")]
        self.assertEqual(evts, ["coupure", "phrase"])
        wav = base64.b64decode([e for e in sorties if e["evt"] == "phrase"][0]["wav"])
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
        # « stop » dit par-dessus sa voix est souvent DEJA fini quand la coupure
        # se decide : ce petit bout part quand meme a la transcription --
        # Machi Tool n'y cherche qu'un conge, sinon il dit « fausse_coupure »
        self.assertEqual({k: v for k, v in sorties[-1].items() if k != "wav"},
                         {"evt": "phrase", "breve": True, "apres_coupure": True})
        self.assertTrue(base64.b64decode(sorties[-1]["wav"]).startswith(b"RIFF"))
        self.assertNotIn("fausse_coupure", o.coupure.appels, "c'est Machi Tool qui le dira")
        o.coupure.appels.clear()
        o.commande({"cmd": "fausse_coupure"})     # Machi Tool : la phrase n'avait pas de mots
        self.assertEqual(o.coupure.appels, ["fausse_coupure"])
        o.commande({"cmd": "ecouter", "attente": 0.5})
        for _ in range(int(1.0 / J.TRAME_S)):
            o.trame(silence)
        self.assertEqual(sorties[-1], {"evt": "vide"}, "une ecoute ordinaire n'est pas une coupure")

    def test_sans_reference_il_ne_se_coupe_pas_lui_meme(self):
        """Le loopback tombe apres que la piece a ete apprise : l'echo predit
        vaut zero, et sa voix passait pour quelqu'un au bout de 1,6 s."""
        for graine, lat, rt, db in self.PIECES:
            p, c = PieceSimulee(graine, lat, rt, db), J.Coupure()
            p.passage(c, self.jarvis[0])
            p.passage(c, self.jarvis[1])
            _, mic, _, _ = p.signaux(self.jarvis[2])
            p.t += 30.0
            c.armer(p.t)
            for i in range(0, len(mic) - J.TRAME, J.TRAME):
                self.assertFalse(c.micro(mic[i:i + J.TRAME].astype(np.float32), p.t + (i + J.TRAME) / 16000.0),
                                 "piece %d : coupe a %.2f s sans reference" % (graine, i / 16000.0))

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
                for nom in J.voix_de_kokoro(entree):
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
        self.assertAlmostEqual(int(np.max(np.abs(sons[0]))), int(J.VOIX_CRETE * 32767), delta=2,
                               msg="crete normalisee (80 % : pas d'ecretage au reechantillonnage)")

    def test_il_dit_ce_qui_le_calcule_et_a_quelle_vitesse(self):
        self.assertIn(self.syn.moteur(), ("CPUExecutionProvider", "DmlExecutionProvider",
                                          "CUDAExecutionProvider", "CoreMLExecutionProvider"))
        rtf = self.syn.mesurer()
        self.assertTrue(rtf is not None and 0 < rtf < 10, rtf)

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
        self.assertEqual([e["evt"] for e in evts if e["evt"] != "dit"], ["debut", "fini", "debut", "fini"])


class AppelPerduDerriereUnDoute(TresTolerant):
    """« J'ai galere a ce qu'il s'allume. » Un « Jarvis ? » pas net part a la
    verification (moteur froid : rien ne revient a temps) ; « JARVIS ! » dit
    net juste apres le reveille -- sa demande doit partir, et ni le verdict en
    retard du premier appel ni son delai ne doivent la jeter."""

    def test_un_appel_net_ne_se_perd_pas_derriere_un_appel_pas_net(self):
        self.appel_pas_net()
        self.silence(70)                              # rien pour lui : pas de carillon
        self.dire(self.g)                             # « JARVIS ! » net
        self.assertEqual(self.sons, ["eveil"])
        self.silence(3)
        self.dire([np.random.default_rng(5).normal(size=96)] * 20)
        self.silence(25)
        self.assertIn("phrase", self.evts(), "la demande de l'appel net part")
        self.o.commande({"cmd": "verifie", "ok": False})             # le verdict du premier, en retard
        self.assertEqual(self.evts().count("phrase"), 1)

    def test_la_suite_ne_se_perd_pas_derriere_un_verdict_en_retard(self):
        self.appel_pas_net()
        self.silence(70)
        self.o.commande({"cmd": "ecouter", "attente": 5.0})         # apres une reponse
        self.silence(3)
        self.dire([np.random.default_rng(6).normal(size=96)] * 8)
        self.o.commande({"cmd": "verifie", "ok": False})             # l'ancien appel : ecarte
        self.dire([np.random.default_rng(6).normal(size=96)] * 8)
        self.silence(25)
        self.assertIn("phrase", self.evts(), "ce qu'on repond a Jarvis part")

    def test_un_appel_net_pendant_la_verification_reveille_tout_de_suite(self):
        self.appel_pas_net()
        self.silence(22)
        self.dire(self.g)                             # « JARVIS ! », net, pendant la verification
        self.assertEqual(self.sons, ["eveil"], "le carillon, tout de suite")
        self.assertEqual([e for e in self.evts() if e != "presque"][-1], "reveil")
        self.dire([np.random.default_rng(8).normal(size=96)] * 12)
        self.silence(25)
        self.assertIn("phrase", self.evts())

    def test_moteur_trop_lent_un_appel_pas_tout_pres_ne_passe_pas(self):
        self.appel_pas_net()                          # ~1,4 x le seuil direct
        self.silence(J.VERIF_ATTENTE_TRAMES + 5)
        self.assertNotIn("reveil", self.evts(), "1,4 x le seuil, sans lecture : on ne devine pas")

    def test_impossible_de_lire_un_appel_tout_pres_passe(self):
        self.appel_pas_net()
        self.o.doute["reveil"]["score"] = 1.2 * self.o.det.seuil
        self.o.commande({"cmd": "verifie", "ok": None})               # la transcription n'a pas pu tourner
        self.assertIn("reveil", self.evts())
        self.assertEqual(self.sons, ["eveil"])

    test_confirme_il_se_reveille_et_la_phrase_suit = None
    test_ecarte_il_se_rendort_sans_un_bruit = None
    test_la_phrase_finie_avant_le_verdict_l_attend = None
    test_net_il_se_reveille_tout_de_suite = None
    test_sans_reponse_il_laisse_tomber = None


class LeReveilQuiRatait(TresTolerant):
    """« J'ai galere a ce qu'il s'allume » -- et « surtout qu'il n'apparaisse
    pas pour rien ». Les appels pas nets qu'il perdait, sans en accepter plus."""

    def verifier(self):
        return [e for e in self.sorties if e["evt"] == "verifier"]

    def test_redire_son_nom_juste_apres_un_appel_pas_net(self):
        # « Jarvis ? ... JARVIS ! » : 2 s de surdite apres le premier
        self.appel_pas_net()
        self.silence(3)
        self.dire(self.g)
        self.assertIn("reveil", self.evts())
        self.assertEqual(self.sons, ["eveil"])

    def test_un_second_appel_pas_net_est_verifie_aussi(self):
        self.appel_pas_net()
        self.silence(12)
        self.dire(self.autrement)                     # « Jarvis ? » encore, pas net
        self.silence(J.TOLERANCE_ATTENTE + 1)
        v = self.verifier()
        self.assertEqual(len(v), 2, "le second appel part aussi a la verification")
        self.o.commande({"cmd": "verifie", "ok": False, "n": v[0]["n"]})   # le premier, mal lu
        self.assertNotIn("reveil", self.evts(), "l'autre attend encore sa lecture")
        self.assertIsNotNone(self.o.doute)
        self.o.commande({"cmd": "verifie", "ok": True, "n": v[1]["n"]})
        self.assertIn("reveil", self.evts())

    def test_deux_non_et_il_se_rendort(self):
        self.appel_pas_net()
        self.silence(12)
        self.dire(self.autrement)
        self.silence(J.TOLERANCE_ATTENTE + 1)
        v = self.verifier()
        self.o.commande({"cmd": "verifie", "ok": False, "n": v[1]["n"]})
        self.o.commande({"cmd": "verifie", "ok": False, "n": v[0]["n"]})
        self.assertIsNone(self.o.doute)
        self.assertNotIn("reveil", self.evts())

    def test_pas_de_carillon_au_milieu_de_la_phrase(self):
        # « Jarvis, mets de la musique de Daft Punk » d'une traite : le verdict
        # arrive pendant « musique »
        self.appel_pas_net()
        self.dire([np.random.default_rng(5).normal(size=96)] * 12)
        self.o.commande({"cmd": "verifie", "ok": True})
        self.assertEqual(self.sons, [], "pas de « a vous » par-dessus la personne")
        self.assertEqual([e for e in self.evts() if e != "presque"][-1], "reveil")
        self.silence(25)
        self.assertIn("phrase", self.evts())
        self.assertEqual(self.sons, ["capte"])

    def test_lecture_lente_tout_pres_il_n_attend_pas(self):
        # le moteur de transcription demarre a froid : un appel tout pres du
        # seuil ne reste pas 20 s dans le silence
        self.appel_pas_net()
        n = self.verifier()[0]["n"]
        self.o.doute["reveil"]["score"] = 1.2 * self.o.det.seuil
        self.silence(J.VERIF_REPLI_TRAMES + 2)
        self.assertIn("reveil", self.evts())
        r = [e for e in self.sorties if e["evt"] == "reveil"][-1]
        self.assertTrue(r["repli"])
        self.assertFalse(r["verifie"], "rien n'a ete lu : la phrase devra contenir son nom")
        self.assertEqual(self.sons, ["eveil"])
        self.assertIn("sans_lecture", [e.get("issue") for e in self.sorties if e.get("maj")])
        self.o.commande({"cmd": "verifie", "ok": False, "n": n})           # la lecture, en retard
        self.assertEqual(self.o.etat, "phrase", "un verdict en retard ne coupe pas l'ecoute")

    def test_lecture_lente_trop_loin_il_attend_encore(self):
        self.appel_pas_net()                          # ~1,4 x le seuil direct
        self.silence(J.VERIF_REPLI_TRAMES + 2)
        self.assertNotIn("reveil", self.evts())
        self.assertIsNotNone(self.o.doute, "il attend toujours la lecture")
        self.assertIn("lent", [e.get("issue") for e in self.sorties if e.get("maj")], "et ca se voit")
        self.o.commande({"cmd": "verifie", "ok": True})
        self.assertIn("reveil", self.evts())

    def test_sa_propre_voix_ne_le_reveille_pas(self):
        # sans double transmission : « ... Reglages, Jarvis. » dans sa voix
        self.silence(20)
        self.o.commande({"cmd": "parole", "actif": True})
        self.dire(self.autrement)
        self.silence(2)
        self.o.commande({"cmd": "parole", "actif": False})
        self.silence(10)
        self.assertEqual(self.verifier(), [])
        # ... mais TON « Jarvis » appris, net, le reveille par-dessus lui
        self.o.commande({"cmd": "parole", "actif": True})
        self.dire(self.g)
        self.assertIn("reveil", self.evts())

    test_confirme_il_se_reveille_et_la_phrase_suit = None
    test_ecarte_il_se_rendort_sans_un_bruit = None
    test_la_phrase_finie_avant_le_verdict_l_attend = None
    test_net_il_se_reveille_tout_de_suite = None
    test_sans_reponse_il_laisse_tomber = None


class LeNomEcorche(unittest.TestCase):
    def test_ce_que_parakeet_ecrit_d_un_jarvis_dit_seul(self):
        for t in ("Javis", "Jaavis", "Chavis", "Harvis", "Yarvis", "Jarbis", "É Javi.", "Ajarvis",
                  "Charvi allume la lumiere", "Djavis", "J'ai revie", "Ok, Javi."):
            self.assertTrue(J.nom_verifie(t), t)

    def test_jamais_des_mots_de_tous_les_jours(self):
        for t in ("j'arrive", "ok j'arrive", "j'avais dit", "j'ai vu", "j'ai visé", "je vis ici", "j'avise",
                  "j'avoue", "javel", "java", "Gervais", "Travis Scott", "Davis", "service", "déjà vu",
                  "j'y vais", "la vie", "Javier", "Harvey", "j'ai révisé mes cours", ""):
            self.assertIsNone(J.nom_verifie(t), t)


if __name__ == "__main__":
    unittest.main(verbosity=1)
