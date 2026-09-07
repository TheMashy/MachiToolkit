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




class ExeTelecharge(unittest.TestCase):
    """CE QUI SE PASSE QUAND ON DOUBLE-CLIQUE UN EXE GARDE SUR LE BUREAU.

    Il vieillit : l'application se met a jour seule, ce fichier-la reste a la
    version du jour ou on l'a telecharge. Il montrait alors « une version plus
    recente est deja installee » a chaque clic — un reproche pour un geste qui
    n'a rien de fautif — et un fichier de meme version se reinstallait
    par-dessus lui-meme en annoncant une mise a jour qui n'en etait pas une.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def test_le_mot_pour_se_montrer(self):
        """Si l'application tourne deja, le mutex renvoie la seconde copie
        sans un mot : le double-clic ne ferait rien du tout."""
        self.assertFalse(self.mt.relever_demande_panneau())
        self.assertTrue(self.mt.demander_panneau())
        self.assertTrue(self.mt.relever_demande_panneau())
        self.assertFalse(self.mt.relever_demande_panneau(),
                         "le mot est efface en le lisant : une demande, une ouverture")

    def test_comparaison_des_versions(self):
        """La regle : ce qui n'apporte rien de neuf ouvre l'installee."""
        plus_recente = self.mt.plus_recente
        self.assertTrue(plus_recente("1.20.1", "1.20.0"), "un exe plus neuf installe")
        self.assertFalse(plus_recente("1.20.0", "1.20.1"), "un exe plus vieux ouvre")
        self.assertFalse(plus_recente("1.20.1", "1.20.1"), "le meme exe ouvre, il ne reinstalle pas")
        self.assertTrue(plus_recente("1.21.0-dev.1", "1.20.1"))
        self.assertFalse(plus_recente("1.20.1-dev.9", "1.20.1"),
                         "une pre-version passe avant la finale du meme numero")


class Echelle(unittest.TestCase):
    """LA FENETRE COINCEE ENTRE DEUX ECRANS.

    Rebatir l'interface la redimensionne ; a cheval sur un 4K et un 1080p, la
    nouvelle taille change le moniteur majoritaire, donc la mesure, donc
    l'echelle voulue — et on repart, deux fois et demie par seconde.

    On rejoue la sequence sur un faux panneau : la mesure alterne comme elle le
    ferait a cheval, puis se pose. Rien ne doit bouger pendant l'alternance, et
    tout doit suivre une fois la fenetre posee.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def faux_panneau(self, mesures, a_cheval):
        mt, cas = self.mt, self

        class Faux:
            ECHELLE_TICS = mt.Panneau.ECHELLE_TICS
            suivre_ecran = mt.Panneau.suivre_ecran

            def __init__(self):
                self.echelle = 1.0
                self._ech_vue, self._ech_tics = None, 0
                self.root = object()
                self.refaits = []

            def refaire_interface(self, e):
                self.refaits.append(e)
                self.echelle = e

        p = Faux()
        suite = list(mesures)
        mt.echelle_ecran = lambda racine, forcee=0.0: suite.pop(0) if suite else p.echelle
        mt.fenetre_a_cheval = lambda racine: a_cheval.pop(0) if a_cheval else False
        return p

    def test_l_ancienne_regle_bouclait_vraiment(self):
        """La preuve du defaut, pas seulement de la correction.

        L'ancienne regle tenait en une ligne : « la mesure a change, refais
        l'interface ». Rejouee sur les mesures qu'une fenetre a cheval renvoie,
        elle reconstruit a CHAQUE passage — vingt fois en huit secondes. C'est
        ce que la fenetre faisait a l'ecran.
        """
        echelle, refaits = 1.0, []
        for voulue in [2.0, 1.0] * 10:
            if abs(voulue - echelle) > 0.05:
                refaits.append(voulue)
                echelle = voulue
        self.assertEqual(len(refaits), 20, "l'ancienne regle doit boucler ici")

        p = self.faux_panneau([2.0, 1.0] * 10, [True] * 20)
        for _ in range(20):
            p.suivre_ecran()
        self.assertEqual(p.refaits, [], "la nouvelle ne bouge pas sur les memes mesures")

    def test_a_cheval_rien_ne_bouge(self):
        # La mesure saute d'un ecran a l'autre vingt fois : c'est exactement ce
        # que voyait la boucle. La fenetre deborde, donc on ne touche a rien.
        p = self.faux_panneau([2.0, 1.0] * 10, [True] * 20)
        for _ in range(20):
            p.suivre_ecran()
        self.assertEqual(p.refaits, [], "l'interface a ete refaite %d fois" % len(p.refaits))
        self.assertEqual(p.echelle, 1.0)

    def test_une_fois_posee_elle_suit(self):
        p = self.faux_panneau([2.0] * 6, [False] * 6)
        for _ in range(6):
            p.suivre_ecran()
        self.assertEqual(p.refaits, [2.0], "une seule reconstruction, a la bonne echelle")

    def test_une_mesure_isolee_ne_suffit_pas(self):
        """Traverser l'autre ecran en deplacant la fenetre ne doit pas
        redessiner l'interface au passage."""
        p = self.faux_panneau([2.0, 1.0, 2.0, 1.0], [False] * 4)
        for _ in range(4):
            p.suivre_ecran()
        self.assertEqual(p.refaits, [])

    def test_le_reglage_manuel_a_le_dernier_mot(self):
        self.assertEqual(self.mt.echelle_ecran(None, 2.5), 2.5)
        self.assertEqual(self.mt.echelle_ecran(None, 99), 4.0, "borne haute")
        self.assertEqual(self.mt.echelle_ecran(None, 0.1), 0.75, "borne basse")


class TailleDeFenetre(unittest.TestCase):
    """LA FINESSE N'EST PAS LA PLACE.

    L'echelle ne se deduisait que des points par pouce. Un 4K a 180 ppp donne
    1,875, soit une fenetre de 1443 par 1295 : elle tient largement sur le 4K,
    et elle est plus haute que l'ecran 1080p d'a cote. On la voyait deborder,
    tronquee par le bas, avec des caracteres enormes.

    Deux moniteurs peuvent avoir la meme finesse et pas du tout la meme
    surface. L'echelle se borne donc a ce que la zone de travail accepte.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def poser_ecran(self, largeur, hauteur, barre=40):
        """Un faux moniteur : (ecran, zone de travail, cadre de la fenetre)."""
        class Rect:
            def __init__(self, l, t, r, b):
                self.left, self.top, self.right, self.bottom = l, t, r, b
        ecran = Rect(0, 0, largeur, hauteur)
        travail = Rect(0, 0, largeur, hauteur - barre)
        self.mt._ecran_de_la_fenetre = lambda racine: (ecran, travail, ecran)

    def test_le_1080p_ne_recoit_pas_la_taille_du_4k(self):
        self.poser_ecran(1920, 1080)
        tenable = self.mt.echelle_tenable(None, 1.875)
        base_l, base_h = self.mt.FENETRE_BASE
        self.assertLess(tenable, 1.875, "l'echelle du 4K doit etre rabaissee")
        self.assertLessEqual(base_h * tenable, 1080 - 40,
                             "la fenetre depasse encore la zone de travail")
        self.assertLessEqual(base_l * tenable, 1920)

    def test_le_4k_garde_son_echelle(self):
        self.poser_ecran(3840, 2160)
        self.assertAlmostEqual(self.mt.echelle_tenable(None, 1.875), 1.875, places=3)

    def test_jamais_sous_un(self):
        """Sous 1, l'interface ne se lit plus : une fenetre trop grande qu'on
        peut deplacer vaut mieux qu'illisible."""
        self.poser_ecran(800, 600)
        self.assertEqual(self.mt.echelle_tenable(None, 1.5), 1.0)

    def test_le_reglage_manuel_est_borne_lui_aussi(self):
        self.poser_ecran(1920, 1080)
        forcee = self.mt.echelle_ecran(None, 4.0)
        self.assertLess(forcee, 4.0, "personne ne veut d'une fenetre plus grande que son ecran")

    def test_sans_ecran_lisible_on_ne_touche_a_rien(self):
        self.mt._ecran_de_la_fenetre = lambda racine: None
        self.assertEqual(self.mt.echelle_tenable(None, 1.875), 1.875)


class FinesseDEcran(unittest.TestCase):
    """LES TROIS APPELS NE LEVENT PAS QUAND ILS ECHOUENT : ILS RENDENT FAUX.

    La boucle attrapait donc une exception qui ne venait jamais et sortait sur
    la premiere tentative, meme refusee. Le processus restait aveugle a la
    finesse des ecrans — d'ou la fenetre qui garde la taille du 4K sur le
    1080p.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    # Attention : les trois fonctions ne parlent pas la meme langue.
    # SetProcessDpiAwarenessContext et SetProcessDPIAware rendent un BOOL
    # (0 = refus), SetProcessDpiAwareness un HRESULT (0 = pose). Confondre les
    # deux, c'est refaire le defaut a l'envers.
    ECHEC_BOOL = 0
    ECHEC_HRESULT = -2147024809          # E_INVALIDARG
    DEJA_POSE = -2147024891              # E_ACCESSDENIED

    def rejouer(self, reponses):
        """Rejoue activer_dpi contre des reponses connues. Rend l'ordre des
        appels effectivement tentes."""
        essais = []

        def faux(nom, valeur):
            def appel(*_):
                essais.append(nom)
                if isinstance(valeur, Exception):
                    raise valeur
                return valeur
            return appel

        class FauxUser32:
            SetProcessDpiAwarenessContext = staticmethod(faux("v2", reponses[0]))
            SetProcessDPIAware = staticmethod(faux("systeme", reponses[2]))
            GetThreadDpiAwarenessContext = staticmethod(lambda: 0)
            GetAwarenessFromDpiAwarenessContext = staticmethod(lambda c: 2)

        class FauxShcore:
            SetProcessDpiAwareness = staticmethod(faux("par ecran", reponses[1]))

        class FauxWindll:
            user32 = FauxUser32
            shcore = FauxShcore

        # `windll` n'existe pas hors de Windows : on le pose le temps du cas,
        # et on le retire ensuite pour ne rien laisser derriere.
        import ctypes
        avait = hasattr(ctypes, "windll")
        garde = getattr(ctypes, "windll", None)
        ctypes.windll = FauxWindll
        nom_os, os.name = os.name, "nt"
        try:
            self.mt.activer_dpi()
        finally:
            if avait:
                ctypes.windll = garde
            else:
                del ctypes.windll
            os.name = nom_os
        return essais

    def test_le_premier_qui_marche_gagne(self):
        self.assertEqual(self.rejouer([1, self.ECHEC_HRESULT, self.ECHEC_BOOL]), ["v2"])

    def test_UN_REFUS_PASSE_AU_SUIVANT(self):
        # C'est le defaut : 0 est un refus, et il etait lu comme un succes.
        self.assertEqual(self.rejouer([self.ECHEC_BOOL, self.ECHEC_HRESULT, 1]),
                         ["v2", "par ecran", "systeme"])

    def test_zero_est_un_succes_pour_celle_qui_rend_un_hresult(self):
        """Le piege symetrique : refaire le defaut a l'envers."""
        self.assertEqual(self.rejouer([self.ECHEC_BOOL, 0, 1]), ["v2", "par ecran"])

    def test_deja_pose_par_quelqu_un_d_autre_compte_comme_pose(self):
        # SetProcessDpiAwareness rend E_ACCESSDENIED quand c'est deja fait.
        self.assertEqual(self.rejouer([self.ECHEC_BOOL, self.DEJA_POSE, 1]),
                         ["v2", "par ecran"])

    def test_une_fonction_absente_ne_bloque_pas(self):
        self.assertEqual(self.rejouer([AttributeError("trop ancien"), self.ECHEC_HRESULT, 1]),
                         ["v2", "par ecran", "systeme"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
