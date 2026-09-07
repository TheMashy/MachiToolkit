# -*- coding: utf-8 -*-
"""
CE QUI DOIT ARRIVER QUAND UNE ETAPE DU DEMARRAGE ECHOUE.

Un plantage au demarrage est le seul defaut qu'on ne peut pas diagnostiquer :
sans console, l'exception tue le processus sans une fenetre, sans une icone et
sans une ligne. De l'exterieur ca donne « ca plante quand je l'ouvre », et il
n'y a rien a regarder.

Ces cas-la tiennent la seule regle qui compte : RIEN DE FACULTATIF NE DOIT
EMPECHER L'APPLICATION DE S'OUVRIR. L'icone porte « Quitter » et « Installer la
mise a jour » ; sans elle, une application qui tourne ne peut etre ni arretee,
ni reparee, ni mise a jour.

    python outils/test_demarrage.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def charger_module(dossier):
    os.environ["LOCALAPPDATA"] = dossier
    spec = importlib.util.spec_from_file_location("mt_essai", os.path.join(RACINE, "machi_tool.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Demarrage(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def ecrire_config(self, contenu):
        with open(self.mt.FICHIER_CONFIG, "w", encoding="utf-8") as f:
            f.write(contenu if isinstance(contenu, str) else json.dumps(contenu))

    # ---------------- la configuration ----------------

    def test_config_absente(self):
        cfg = self.mt.charger_config()
        self.assertEqual(cfg["config_version"], 3)

    def test_config_illisible_ne_tue_pas(self):
        """Une ecriture interrompue laisse du JSON tronque. On repart des
        valeurs d'usine : ca se repare en trois clics, un demarrage qui
        n'arrive pas ne se repare pas."""
        self.ecrire_config('{"adresse": "AA:BB", "mode":')
        cfg = self.mt.charger_config()
        self.assertEqual(cfg["mode"], self.mt.CONFIG_DEFAUT["mode"])

    def test_config_qui_est_une_liste(self):
        self.ecrire_config("[1, 2, 3]")
        self.assertIsInstance(self.mt.charger_config(), dict)

    def test_valeurs_de_travers_dans_la_migration(self):
        """`int(cfg.get(...))` levait sur null, sur "" et sur "trois" — en
        plein chemin de demarrage, hors de tout filet."""
        for mauvaise in (None, "", "trois", [], {}):
            self.ecrire_config({"config_version": mauvaise,
                                "pont_intervalle": mauvaise,
                                "maj_intervalle_heures": mauvaise})
            cfg = self.mt.charger_config()
            self.assertEqual(cfg["config_version"], 3, repr(mauvaise))

    def test_entier(self):
        self.assertEqual(self.mt.entier("7", 3), 7)
        self.assertEqual(self.mt.entier(None, 3), 3)
        self.assertEqual(self.mt.entier("", 3), 3)
        self.assertEqual(self.mt.entier("trois", 3), 3)
        self.assertEqual(self.mt.entier([], 3), 3)

    # ---------------- l'ecriture qui echoue ----------------

    def test_sauver_config_ne_leve_pas(self):
        """LE PLANTAGE. `sauver_config` levait ; le premier appel vient de
        `jeton_courant`, dans le serveur local — allume chez tout le monde
        depuis la 1.20 — donc avant que l'icone existe."""
        self.mt.FICHIER_CONFIG = os.path.join(self.dossier, "introuvable", "config.json")
        self.assertIs(self.mt.sauver_config({"a": 1}), False)

    def test_jeton_survit_a_une_ecriture_impossible(self):
        self.mt.FICHIER_CONFIG = os.path.join(self.dossier, "introuvable", "config.json")
        cfg = {"api_active": True}
        jeton = self.mt.jeton_courant(cfg)
        self.assertTrue(jeton, "la cle doit valoir pour la session en cours")
        self.assertEqual(self.mt.jeton_courant(cfg), jeton, "et rester la meme")

    def test_demarrer_api_ne_tue_pas_le_demarrage(self):
        self.mt.FICHIER_CONFIG = os.path.join(self.dossier, "introuvable", "config.json")
        self.mt.demarrer_api({"api_active": True, "api_port": "pas un port"})
        self.assertIn("api", self.mt.ETAT)
        self.mt.arreter_api()

    def test_config_ecrite_entierement_ou_pas_du_tout(self):
        """On ecrit a cote puis on remplace : une coupure ne laisse pas
        derriere elle le fichier a moitie ecrit qu'on relira au demarrage."""
        self.assertTrue(self.mt.sauver_config({"mode": "ecran", "_prive": 1}))
        with open(self.mt.FICHIER_CONFIG, encoding="utf-8") as f:
            garde = json.load(f)
        self.assertEqual(garde["mode"], "ecran")
        self.assertNotIn("_prive", garde, "les cles privees ne sont pas enregistrees")
        self.assertFalse(os.path.exists(self.mt.FICHIER_CONFIG + ".part"))

    # ---------------- le filet ----------------

    def test_sans_faute_rend_la_main(self):
        def casse():
            raise RuntimeError("boum")
        self.assertIsNone(self.mt.sans_faute("essai", casse))
        self.assertEqual(self.mt.sans_faute("essai", lambda x: x + 1, 41), 42)

    def test_un_plantage_est_ecrit_dans_le_journal(self):
        try:
            raise ValueError("la panne qu'on cherche")
        except ValueError as e:
            self.mt.SILENCIEUX = True          # pas de fenetre pendant les tests
            self.mt.rapporter_plantage(e)
        with open(self.mt.FICHIER_JOURNAL, encoding="utf-8") as f:
            journal = f.read()
        self.assertIn("PLANTAGE AU DEMARRAGE", journal)
        self.assertIn("la panne qu'on cherche", journal)
        self.assertIn("Traceback", journal, "sans la trace, le journal ne sert a rien")


if __name__ == "__main__":
    unittest.main(verbosity=2)
