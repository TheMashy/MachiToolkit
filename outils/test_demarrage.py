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
import io
import json
import os
import sys
import shutil
import tempfile
import threading
import time
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
        self.assertEqual(cfg["config_version"], 4)

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

    def test_la_migration_v4_allume_les_titres_et_le_dit(self):
        """Elle desserre une regle que le fichier tenait depuis le debut (« on
        garde OU on etait, jamais QUOI ») : elle doit donc s'annoncer, et rester
        annulable. Une migration silencieuse qui ouvre une collecte serait la
        seule chose de ce fichier qu'on n'aurait pas le droit de faire."""
        self.ecrire_config({"config_version": 3, "collecte_titres_complets": False})
        cfg = self.mt.charger_config()
        self.assertTrue(cfg["collecte_titres_complets"])
        self.assertEqual(cfg["config_version"], 4)
        # Et une fois passee, elle ne repasse plus : quelqu'un qui decoche la
        # case ne doit pas la retrouver cochee au lancement suivant.
        self.ecrire_config(dict(cfg, collecte_titres_complets=False))
        self.assertFalse(self.mt.charger_config()["collecte_titres_complets"])

    def test_valeurs_de_travers_dans_la_migration(self):
        """`int(cfg.get(...))` levait sur null, sur "" et sur "trois" — en
        plein chemin de demarrage, hors de tout filet."""
        for mauvaise in (None, "", "trois", [], {}):
            self.ecrire_config({"config_version": mauvaise,
                                "pont_intervalle": mauvaise,
                                "maj_intervalle_heures": mauvaise})
            cfg = self.mt.charger_config()
            self.assertEqual(cfg["config_version"], 4, repr(mauvaise))

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

    def test_on_ne_repose_pas_ce_qui_est_pose(self):
        """Windows refuse de changer d'avis une fois la finesse posee : un
        second appel echouerait, et ferait ecrire au journal un mode qui n'est
        pas celui en vigueur. `main` la pose avant les fenetres de
        l'installeur, `lancer` la redemande — une seule doit compter."""
        self.assertEqual(self.rejouer([1, self.ECHEC_HRESULT, self.ECHEC_BOOL]), ["v2"])
        self.assertEqual(self.rejouer([1, self.ECHEC_HRESULT, self.ECHEC_BOOL]), [],
                         "le second appel ne doit rien tenter")

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


class Onglets(unittest.TestCase):
    """CE QU'ON REGARDE : l'onglet au premier plan, et de quoi il parle.

    Windows ne rend que le titre de la fenetre de premier plan -- mais chez un
    navigateur, c'est exactement le titre de l'ONGLET ACTIF suivi du nom du
    programme. Compter le temps par onglet ne demande donc aucune extension :
    il suffit de decouper correctement, ce qui n'etait pas fait.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def test_le_premier_mot_n_est_pas_le_site(self):
        """LE DEFAUT. La regle etait « pour un navigateur, le premier mot du
        titre, qui porte le site ». Il ne le porte pas : un titre d'onglet
        commence par le sujet de la page. Le journal se remplissait de « my »,
        « i », « they » -- les premiers mots de titres en anglais -- et des
        heures de YouTube comptaient sous cinq noms dont aucun n'existait."""
        cat = self.mt.categorie_activite
        self.assertEqual(cat("chrome.exe | voices of the void - kerfur acquired - youtube - google chrome"),
                         "web:youtube")
        self.assertEqual(cat("chrome.exe | my whole life - r/confession - reddit - google chrome"),
                         "web:reddit")
        self.assertEqual(cat("chrome.exe | i think they are wrong - youtube - google chrome"),
                         "web:youtube")
        for mauvais in ("web:my", "web:i", "web:they", "web:voices"):
            self.assertNotIn(mauvais, [cat("chrome.exe | my whole life - youtube - google chrome"),
                                       cat("chrome.exe | i think - youtube - google chrome")])

    def test_le_nom_du_navigateur_et_le_profil_tombent(self):
        t = self.mt._titre_onglet
        self.assertEqual(t("api keys | claude platform - profil 1 - microsoft edge"),
                         "api keys | claude platform")
        self.assertEqual(t("(3) boite de reception - gmail - google chrome"),
                         "boite de reception - gmail")
        self.assertEqual(t("un titre sans navigateur"), "un titre sans navigateur")

    def test_un_site_inconnu_ne_devient_pas_une_phrase(self):
        """La regle du produit : on garde OU on etait, jamais CE QU'ON lisait.
        Le repli sur le dernier morceau du titre pouvait faire entrer une phrase
        entiere dans le journal — et de la, dans ce qui part au site."""
        cat = self.mt.categorie_activite
        self.assertEqual(cat("chrome.exe | i think they are wrong about all of this - google chrome"),
                         "web:autre")
        # Un vrai nom de site, court, passe.
        self.assertEqual(cat("chrome.exe | mon compte - impots.gouv.fr - google chrome"),
                         "web:impots.gouv.fr")

    def test_les_thematiques_se_lisent_sur_le_titre(self):
        th = self.mt.theme_activite
        for contexte, attendu in [
            ("chrome.exe | urbex : hopital abandonne depuis 40 ans - youtube - google chrome", "urbex"),
            ("chrome.exe | elden ring boss fight no commentary - youtube - google chrome", "jeu"),
            ("chrome.exe | campagne dnd - session 4 - youtube - google chrome", "rp"),
            ("chrome.exe | combat footage frontline - youtube - google chrome", "guerre"),
            ("chrome.exe | debat politique sur la reforme - youtube - google chrome", "politique"),
            ("chrome.exe | storytime : ma journee - youtube - google chrome", "influenceurs"),
            ("chrome.exe | blender tuto rigging - youtube - google chrome", "creation"),
            ("chrome.exe | mon compte - paypal - google chrome", "argent"),
        ]:
            self.assertEqual(th(contexte), attendu, contexte)

    def test_le_support_n_est_pas_un_sujet(self):
        """« video » et « social » raflaient tout ce que les familles precises
        n'avaient pas pris : une heure d'urbex mal orthographiee finissait en
        « video », c'est-a-dire nulle part en ayant l'air d'etre quelque part.
        Savoir qu'on etait sur YouTube ne dit rien de plus que la premiere barre
        de l'ecran, qui l'affiche deja."""
        th = self.mt.theme_activite
        self.assertIsNone(th("chrome.exe | voices of the void - kerfur - youtube - google chrome"))
        self.assertIsNone(th("chrome.exe | (3) r/confession - reddit - google chrome"))
        self.assertNotIn("video", [n for n, _ in self.mt.THEMES_ACTIVITE])
        self.assertNotIn("social", [n for n, _ in self.mt.THEMES_ACTIVITE])

    def test_ce_qui_est_consulte_sur_internet_compte_a_part(self):
        """Une heure de « creation » passee DANS Blender et une heure passee a
        regarder un tuto de Blender ne sont pas la meme heure : l'une est du
        travail, l'autre de la consultation. Melangees, « de quoi parle ce que je
        regarde » n'a plus de reponse."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        # Les ecarts restent sous 180 s : au-dela, un echantillon manquant veut
        # dire que personne ne mesurait, et le versement est plafonne — c'est
        # voulu, et une fixture qui l'ignore mesure le plafond, pas la regle.
        for contexte, t in [
            ("blender.exe | projet.blend", 1000),
            ("blender.exe | projet.blend", 1150),          # 150 s de creation, hors web
            ("chrome.exe | blender tuto rigging - youtube - google chrome", 1150),
            ("chrome.exe | blender tuto rigging - youtube - google chrome", 1270),  # 120 s, web
        ]:
            mt.activite_note(contexte, True, maintenant=t)
        self.assertEqual(round(mt.ACTIVITE["themes"]["creation"]), 270, "tout confondu")
        self.assertEqual(round(mt.ACTIVITE["themes_web"]["creation"]), 120, "sur internet seulement")

    def test_le_titre_derriere_le_theme_rend_la_mesure_refutable(self):
        """Un camembert qui dit « 40 min de guerre » laisse seul devant le
        chiffre. Le titre le rend VERIFIABLE, donc refutable : on doit pouvoir
        regarder la liste et dire « ca, ce n'etait pas de la guerre ». Sans elle,
        une table de mots-cles devient une autorite qu'on ne peut pas contredire."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        vu = "chrome.exe | combat footage frontline - youtube - google chrome"
        mt.activite_note(vu, True, titres_complets=True, maintenant=1000.0)
        mt.activite_note(vu, True, titres_complets=True, maintenant=1150.0)
        mt.activite_note("code.exe | machi_tool.py", True, titres_complets=True, maintenant=1150.0)
        r = mt.resume_activite()
        self.assertEqual(r["titres_par_theme"]["guerre"], {"combat footage frontline - youtube": 150})
        # Sans le reglage, rien n'est garde : c'est le sens du reglage.
        mt._reinit_jour(maintenant=2000.0)
        mt.ACTIVITE["active"] = True
        mt.activite_note(vu, True, maintenant=2000.0)
        mt.activite_note(vu, True, maintenant=2150.0)
        self.assertNotIn("titres_par_theme", mt.resume_activite())

    def test_un_titre_vu_trois_secondes_ne_compte_pas(self):
        """Cent onglets ouverts trois secondes ne disent rien de ce qu'on a
        regarde, et les envoyer ferait grossir chaque journee sans rien
        apprendre a personne."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        vu = "chrome.exe | urbex : un lieu abandonne - youtube - google chrome"
        mt.activite_note(vu, True, titres_complets=True, maintenant=1000.0)
        mt.activite_note(vu, True, titres_complets=True, maintenant=1010.0)   # 10 s
        self.assertNotIn("titres_par_theme", mt.resume_activite())

    def test_un_titre_qui_ne_dit_rien_n_est_classe_nulle_part(self):
        """Inventer une thematique serait pire que ne rien dire : un theme faux
        se lit comme une mesure, et personne n'ira le verifier."""
        self.assertIsNone(self.mt.theme_activite("chrome.exe | une page quelconque - google chrome"))
        self.assertIsNone(self.mt.theme_activite(""))

    def test_le_temps_va_au_theme_de_la_fenetre_QU_ON_QUITTE(self):
        """Le meme raisonnement que `avant` pour la categorie. Le confondre
        ferait glisser chaque minute d'un cran, et les cinq heures de YouTube
        atterriraient sous le theme de l'onglet ouvert juste apres."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        for contexte, t in [
            ("chrome.exe | urbex : hopital abandonne - youtube - google chrome", 1000),
            ("chrome.exe | urbex : hopital abandonne - youtube - google chrome", 1120),
            ("code.exe | machi_tool.py", 1120),
            ("code.exe | machi_tool.py", 1180),
            ("chrome.exe | (3) r/confession - reddit - google chrome", 1180),
            ("chrome.exe | (3) r/confession - reddit - google chrome", 1300),
        ]:
            mt.activite_note(contexte, True, maintenant=t)
        self.assertEqual({k: round(v) for k, v in mt.ACTIVITE["temps"].items()},
                         {"web:youtube": 120, "code": 60, "web:reddit": 120})
        self.assertEqual({k: round(v) for k, v in mt.ACTIVITE["themes"].items()},
                         {"urbex": 120},
                         "ni les 60 s de code ni les 120 s de reddit ne sont classees : "
                         "« social » est un SUPPORT, pas un sujet — la premiere barre de "
                         "l'ecran dit deja qu'on etait sur reddit")


class SousCategories(unittest.TestCase):
    """DANS UN SUJET, DE QUOI IL S'AGIT.

    Le theme est la maille grossiere : « 40 min de guerre ». La sous-categorie
    affine sans reclasser -- et surtout, elle a le droit de ne rien dire. Ces
    tests fixent ce qu'elle ne fera jamais autant que ce qu'elle fait.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def test_la_sous_categorie_affine_le_theme(self):
        st = self.mt.sous_theme_activite
        for theme, contexte, attendu in [
            ("guerre", "chrome.exe | carte du front en ukraine - youtube - google chrome", "ukraine"),
            ("guerre", "chrome.exe | la situation a gaza - le monde - firefox", "proche-orient"),
            ("guerre", "chrome.exe | documentaire seconde guerre mondiale - youtube", "archives"),
            ("jeu", "chrome.exe | elden ring : la fin du jeu - youtube - google chrome", "solo"),
            ("jeu", "chrome.exe | valorant ranked highlights - twitch - google chrome", "competitif"),
            ("creation", "blender.exe | scene.blend", "3d"),
            ("dev", "chrome.exe | typeerror python traceback - stack overflow - firefox", "erreur"),
            ("sante", "chrome.exe | insomnie : que faire - google chrome", "sommeil"),
            ("urbex", "chrome.exe | hopital abandonne en normandie - youtube", "batiment"),
        ]:
            self.assertEqual(st(theme, contexte), attendu, contexte)

    def test_un_titre_qui_n_affine_rien_reste_dans_son_theme(self):
        """La sous-categorie a le droit de ne rien dire. La ranger de force dans
        la plus large ferait une barre pleine et un chiffre faux."""
        st = self.mt.sous_theme_activite
        self.assertIsNone(st("guerre", "chrome.exe | reportage - youtube - google chrome"))
        self.assertIsNone(st(None, "chrome.exe | n importe quoi"))
        self.assertIsNone(st("guerre", ""))

    def test_adulte_n_a_pas_de_sous_categorie(self):
        """DELIBERE. Le theme dit deja ce qui est utile ; le detailler
        transformerait un compteur grossier en un releve des gouts sexuels de
        quelqu'un, range dans son journal."""
        self.assertNotIn("adulte", self.mt.SOUS_THEMES)
        self.assertIsNone(self.mt.sous_theme_activite("adulte", "chrome.exe | pornhub - google chrome"))

    def test_sante_ne_nomme_jamais_un_trouble(self):
        """Une etiquette clinique posee par une table de mots-clefs, et qui
        remonte au site, est exactement ce que ce produit refuse de faire."""
        noms = [n for n, _ in self.mt.SOUS_THEMES["sante"]]
        for interdit in ("tdah", "adhd", "autisme", "depression", "bipolaire", "anxiete",
                         "trouble", "burnout", "symptome", "diagnostic"):
            self.assertNotIn(interdit, noms)

    def test_aucune_sous_categorie_ne_nomme_quelqu_un(self):
        """Le theme protegeait deja QUI on regardait. L'affiner au point de le
        nommer defait la regle du produit."""
        for theme, sous in self.mt.SOUS_THEMES.items():
            for nom, mots in sous:
                self.assertRegex(nom, r"^[a-z0-9-]+$", "%s/%s" % (theme, nom))
                self.assertLessEqual(len(nom), 14, "%s/%s" % (theme, nom))

    def test_la_table_reste_lisible(self):
        """Trois a six sous-categories par theme. Au-dela ce n'est plus une
        lecture, c'est une taxonomie."""
        for theme, sous in self.mt.SOUS_THEMES.items():
            self.assertIn(theme, [n for n, _ in self.mt.THEMES_ACTIVITE], theme)
            noms = [n for n, _ in sous]
            self.assertEqual(len(noms), len(set(noms)), theme)
            self.assertGreaterEqual(len(noms), 3, theme)
            self.assertLessEqual(len(noms), 6, theme)

    def test_le_temps_web_se_repartit_sous_son_theme(self):
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        ukr = "chrome.exe | carte du front en ukraine - youtube - google chrome"
        gaza = "chrome.exe | la situation a gaza - le monde - google chrome"
        flou = "chrome.exe | guerre : reportage - youtube - google chrome"
        for contexte, t in [(ukr, 1000), (ukr, 1120), (gaza, 1120), (gaza, 1240),
                            (flou, 1240), (flou, 1300)]:
            mt.activite_note(contexte, True, maintenant=t)
        r = mt.resume_activite()
        self.assertEqual(r["temps_par_theme_web_s"]["guerre"], 300)
        self.assertEqual(r["temps_par_sous_theme_web_s"]["guerre"],
                         {"ukraine": 120, "proche-orient": 120})
        classe = sum(r["temps_par_sous_theme_web_s"]["guerre"].values())
        self.assertLess(classe, r["temps_par_theme_web_s"]["guerre"],
                        "les 60 s que rien n'affine restent dans le theme, "
                        "comptees une seule fois")

    def test_une_application_ne_nourrit_pas_les_sous_categories_web(self):
        """Une heure passee DANS Blender et une heure a regarder un tuto de
        Blender ne sont pas la meme heure. La regle vaut aussi ici."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        for t in (1000, 1120, 1180):
            mt.activite_note("blender.exe | scene.blend", True, maintenant=t)
        r = mt.resume_activite()
        self.assertNotIn("temps_par_sous_theme_web_s", r)
        self.assertIn("creation", r["temps_par_theme_s"])

    def test_le_changement_de_jour_remet_les_sous_categories_a_zero(self):
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        mt.activite_note("chrome.exe | ukraine - youtube - google chrome", True, maintenant=1000.0)
        mt.activite_note("chrome.exe | ukraine - youtube - google chrome", True, maintenant=1120.0)
        self.assertTrue(mt.ACTIVITE["sous_themes_web"])
        mt._reinit_jour(maintenant=2000.0)
        self.assertEqual(mt.ACTIVITE["sous_themes_web"], {})
        self.assertIsNone(mt.ACTIVITE["sous_courant"])

    def test_un_sigle_de_trois_lettres_ne_se_cherche_pas_en_sous_chaine(self):
        """QUATRE MAUVAIS CLASSEMENTS, TROUVES EN RELISANT LA TABLE.

        « donbass » et « coinbase » contiennent « nba », « commande » contient
        « mma », « osteo » commence par « ost » : la guerre, l'argent et la
        sante partaient dans le sport et la musique. Trois lettres suffisent a
        un sigle et ne suffisent jamais a une recherche en sous-chaine.
        """
        th = self.mt.theme_activite
        for contexte, attendu in [
            ("chrome.exe | avancee dans le donbass - youtube - google chrome", "guerre"),
            ("chrome.exe | coinbase - mon portefeuille - google chrome", "argent"),
            ("chrome.exe | suivi de ma commande - amazon - google chrome", "achat"),
            ("chrome.exe | rendez vous osteo chez le kine - google chrome", "sante"),
        ]:
            self.assertEqual(th(contexte), attendu, contexte)
        # Et les vrais sigles passent toujours.
        self.assertEqual(th("chrome.exe | resume nba lakers - youtube"), "sport")
        self.assertEqual(th("chrome.exe | ufc 300 : le combat - youtube"), "sport")

    def test_un_mot_clef_n_attrape_pas_du_francais_ordinaire(self):
        """« meme » nu attrapait « même » ecrit sans accent — omnipresent dans
        les titres francais. La sous-categorie aurait double de taille pour
        rien, et « humour » aurait eu l'air d'etre partout."""
        st = self.mt.sous_theme_activite
        self.assertIsNone(st("humour", "chrome.exe | je ne sais meme pas quoi dire - youtube"))
        self.assertEqual(st("humour", "chrome.exe | best of memes 2026 - youtube"), "meme")

    def test_une_sous_categorie_ne_reprend_pas_les_mots_de_son_theme(self):
        """Une sous-categorie faite des mots qui declenchent son theme est un
        SUPPORT deguise en sujet : presque tout le theme y tomberait, et elle ne
        dirait rien de plus que lui. C'etait le cas de « actu/france »."""
        for theme, mots_theme in self.mt.THEMES_ACTIVITE:
            declencheurs = set(mots_theme)
            for nom, mots in self.mt.SOUS_THEMES.get(theme, ()):
                communs = declencheurs & set(mots)
                # Partager quelques mots est normal et utile : « ukraine »
                # declenche « guerre » ET la precise. Ce qui ne l'est pas, c'est
                # de n'etre fait QUE de mots du theme : la sous-categorie
                # ramasse alors ce que le theme ramasse deja et ne dit rien de
                # plus que lui — un SUPPORT deguise en sujet. C'etait
                # « actu/france », fait des journaux qui declenchent « actu »,
                # et trois autres. La regle : au moins la moitie de ses mots
                # doivent etre a elle. Et depuis qu'une sous-categorie implique
                # son theme, lui retirer un mot partage ne perd rien : le theme
                # se declenche toujours dessus.
                propres = len(mots) - len(communs)
                self.assertGreaterEqual(propres, len(mots) / 2,
                                        "%s/%s n'a que %d mots a elle sur %d : %s viennent du theme"
                                        % (theme, nom, propres, len(mots), sorted(communs)))

    def test_un_nom_de_sous_categorie_n_est_pas_un_mot_clef_d_une_soeur(self):
        """« endurance » etait un mot-clef de sport/moteur ET le nom de
        sport/endurance, qui vient apres : « sport d'endurance » tombait dans
        « moteur »."""
        for theme, sous in self.mt.SOUS_THEMES.items():
            noms = {n for n, _ in sous}
            for nom, mots in sous:
                for m in mots:
                    self.assertNotIn(m.strip(), noms - {nom},
                                     "%s/%s : « %s » est le nom d'une soeur" % (theme, nom, m))

    def test_le_titre_envoye_est_celui_de_l_onglet(self):
        """Il partait brut, avec « - Profil 1 - Microsoft Edge » colle derriere :
        a l'ecran, c'est le nom du navigateur qui tenait la ligne, pas la page."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["active"] = True
        vu = "chrome.exe | carte du front en ukraine - youtube - profil 1 - microsoft edge"
        for t in (1000, 1120):
            mt.activite_note(vu, True, titres_complets=True, maintenant=t)
        titres = mt.resume_activite()["titres"]["web:youtube"]
        self.assertEqual(list(titres), ["carte du front en ukraine - youtube"])

    def test_une_journee_reprise_ne_compte_pas_deux_fois_la_meme_page(self):
        """Les entrees ecrites brutes par une version d'avant se replient sur la
        version propre au lieu de faire deux lignes pour la meme page."""
        mt = self.mt
        mt._reinit_jour(maintenant=1000.0)
        mt.ACTIVITE["titres"] = {"web:youtube": {
            "carte du front en ukraine - youtube - google chrome": 300.0,
            "carte du front en ukraine - youtube": 120.0,
        }}
        titres = mt.resume_activite()["titres"]["web:youtube"]
        self.assertEqual(titres, {"carte du front en ukraine - youtube": 420})


class MiseAJourQuiDisparait(unittest.TestCase):
    """ELLE S'EST ETEINTE TOUTE SEULE, SANS RIEN AFFICHER.

    Le fil de la mise a jour posait l'installeur puis tuait l'application, deux
    secondes apres une bulle de notification. Au demarrage de Windows cette
    bulle n'arrive nulle part -- l'assistant de concentration l'avale a
    l'ouverture de session -- et quelqu'un qui cliquait l'icone a cet instant
    voyait sa fenetre s'ouvrir PUIS le processus mourir dessous. De l'exterieur
    c'est un plantage. L'application faisait exactement ce qu'on lui avait
    demande, sans que rien ne le dise.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)
        # `charger_module` deplace LOCALAPPDATA, mais hors de Windows le dossier
        # de l'application retombe sur le depot : une config laissee par un
        # essai precedent ferait passer un premier demarrage pour une reprise.
        # On repart donc d'un dossier vide, explicitement.
        self.mt.DOSSIER = self.dossier
        self.mt.FICHIER_CONFIG = os.path.join(self.dossier, "config.json")
        self.mt.FICHIER_JOURNAL = os.path.join(self.dossier, "journal.log")
        self.mt.MAJ.update(etat="repos", differee=False, version="9.9.9")

    def test_rien_a_poser_ne_pose_rien(self):
        self.assertFalse(self.mt.poser_la_maj(False))
        self.assertFalse(self.mt.MAJ["differee"])

    def test_la_fenetre_ouverte_retient_la_pose(self):
        """Le coeur du correctif : on ne tue pas l'application sous les doigts
        de quelqu'un qui vient de l'ouvrir."""
        mt = self.mt
        mt.MAJ["etat"] = "a_poser"
        self.assertFalse(mt.poser_la_maj(True))
        self.assertTrue(mt.MAJ["differee"], "et le panneau doit pouvoir le dire")
        self.assertEqual(mt.MAJ["etat"], "a_poser", "la pose attend, elle n'est pas annulee")

    def test_la_fenetre_fermee_laisse_partir_la_pose(self):
        mt = self.mt
        mt.MAJ["etat"] = "a_poser"
        self.assertTrue(mt.poser_la_maj(False))
        self.assertFalse(mt.MAJ["differee"])

    def test_refermer_la_fenetre_libere_la_pose(self):
        """La sequence complete : elle attend, puis elle part."""
        mt = self.mt
        mt.MAJ["etat"] = "a_poser"
        self.assertFalse(mt.poser_la_maj(True))
        self.assertFalse(mt.poser_la_maj(True))
        self.assertTrue(mt.poser_la_maj(False))

    def test_une_guirlande_qui_retombe_aussitot_espace_ses_tentatives(self):
        """UNE GUIRLANDE QUI CLIGNOTE, C'EST UNE SESSION QUI NE TIENT PAS.

        Dix secondes fixes entre deux tentatives : une guirlande qui tombe
        aussitot connectee se rallume et s'eteint toutes les dix secondes, sans
        fin. C'est ce qu'on voit — elle clignote — et c'est aussi ce qui
        martele la pile Bluetooth de Windows.
        """
        mt = self.mt
        mt.ETAT["echecs_ble"] = 0
        attentes = [mt.attente_apres_session(0.4) for _ in range(5)]
        self.assertEqual(attentes, [10.0, 25.0, 60.0, 60.0, 60.0],
                         "dix secondes pour le premier echec — un simple rate ne "
                         "doit pas coûter une minute — puis vingt-cinq, puis une "
                         "minute, et ça s'y tient")
        self.assertEqual(mt.ETAT["echecs_ble"], 3, "le compteur est borne")

    def test_une_session_qui_tient_remet_le_compteur_a_zero(self):
        """Le cas normal ne paie rien : ce sont les echecs consecutifs qui
        s'espacent, pas les sessions qui se terminent normalement."""
        mt = self.mt
        mt.ETAT["echecs_ble"] = 0
        for _ in range(3):
            mt.attente_apres_session(0.4)
        self.assertGreater(mt.ETAT["echecs_ble"], 0)
        self.assertEqual(mt.attente_apres_session(mt.SESSION_TENUE + 1), 10.0)
        self.assertEqual(mt.ETAT["echecs_ble"], 0)

    def test_on_ne_renonce_jamais_a_la_guirlande(self):
        """Une guirlande eteinte parce qu'elle etait hors de portee doit
        revenir quand elle rentre : l'attente plafonne, elle ne s'arrete pas."""
        mt = self.mt
        mt.ETAT["echecs_ble"] = 0
        for _ in range(50):
            self.assertLessEqual(mt.attente_apres_session(0.1), 60.0)
        self.assertLessEqual(max(mt.ATTENTE_BLE), 60.0)

    def test_un_installeur_qui_ne_part_pas_ne_fait_pas_quitter(self):
        """En mode script -- et chaque fois que le fichier telecharge a disparu
        -- l'installeur ne part pas. L'application ne doit alors surtout pas
        s'arreter : elle resterait fermee, sans rien pour la relancer. Et
        l'etat bascule en « erreur », sinon la boucle de surveillance
        reessaierait toutes les cent cinquante millisecondes."""
        mt = self.mt
        mt.MAJ.update(etat="a_poser", fichier="")
        self.assertFalse(mt.lancer_installeur_maj())
        self.assertEqual(mt.MAJ["etat"], "erreur")
        self.assertFalse(mt.poser_la_maj(False), "l'etat a change : plus rien a poser")

    def test_un_arret_laisse_une_trace_datee(self):
        """Un redemarrage pour mise a jour et un plantage laissaient la meme
        trace : aucune. Vu de l'exterieur les deux se ressemblent."""
        mt = self.mt
        mt.journaliser_arret("mise a jour vers 9.9.9")
        with open(mt.FICHIER_JOURNAL, encoding="utf-8") as f:
            journal = f.read()
        self.assertIn("ARRET", journal)
        self.assertIn("mise a jour vers 9.9.9", journal)
        self.assertIn(mt.VERSION, journal)

    def test_au_retour_l_application_dit_qu_elle_a_ete_mise_a_jour(self):
        """Sans ca, rien au redemarrage ne distingue « je viens de me mettre a
        jour » de « je viens de planter »."""
        mt = self.mt
        cfg = mt.charger_config()
        self.assertEqual(cfg["derniere_version"], mt.VERSION)
        mt.sauver_config(cfg)
        # On rejoue un demarrage venant d'une version d'avant.
        with open(mt.FICHIER_CONFIG, encoding="utf-8") as f:
            enregistre = json.load(f)
        enregistre["derniere_version"] = "1.0.0"
        with open(mt.FICHIER_CONFIG, "w", encoding="utf-8") as f:
            json.dump(enregistre, f)
        mt.MAJ.update(etat="repos", message="Aucune verification depuis le demarrage.")
        mt.charger_config()
        self.assertEqual(mt.MAJ["etat"], "a_jour")
        self.assertIn("1.0.0", mt.MAJ["message"])
        self.assertIn(mt.VERSION, mt.MAJ["message"])

    def test_un_premier_demarrage_n_annonce_aucune_mise_a_jour(self):
        mt = self.mt
        mt.MAJ.update(etat="repos", message="Aucune verification depuis le demarrage.")
        mt.charger_config()
        self.assertEqual(mt.MAJ["etat"], "repos",
                         "il n'y a pas eu de version d'avant : il n'y a rien a annoncer")


class Nuits(unittest.TestCase):
    """LA NUIT DE QUELQU'UN QUI SE LEVE A 16 H.

    Le 7 septembre : debout a minuit, PC eteint a 05:26, rallume a 16:20. Le
    site a affiche « lever 00:00, coucher 19:47 ». Trois defauts se cumulaient :
    la reprise apres l'allumage n'etait vue par rien (pas de trou, et les
    demarrages du poste ignores des que le clavier avait dit UN mot) ; une nuit
    devait finir avant 16:00 -- une borne d'heure civile, pas de duree ; et sans
    nuit, le repli rendait la premiere minute du fichier civil comme reveil.

    Ici la nuit est le plus long silence qui se termine par une reprise du
    clavier dans la journee, 2 h a 16 h, sur trente-six heures ; le rythme de
    la personne departage ; et sans nuit, il n'y a pas de lever du tout.
    """
    JOUR = "2026-09-07"
    VEILLE = "2026-09-06"

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)
        self.mt._jour_courant = lambda: self.JOUR
        # En mode script, DOSSIER est le depot : les fichiers de donnees vont
        # dans le dossier du cas, pas dans les sources ni dans le cas voisin.
        for nom in ("FICHIER_ACTIVITE", "FICHIER_SESSIONS", "FICHIER_BATTEMENT",
                    "FICHIER_MIGRATION", "FICHIER_ENVOI"):
            setattr(self.mt, nom, os.path.join(self.dossier, os.path.basename(getattr(self.mt, nom))))

    # ---- le decor ----
    def ts(self, hhmm, jour=None):
        import time
        return time.mktime(time.strptime("%s %s" % (jour or self.JOUR, hhmm), "%Y-%m-%d %H:%M"))

    def digest(self, date, de, a, trous=(), poste=None):
        d = {"date": date, "plage": {"de": de, "a": a},
             "trous": [{"de": t[0], "a": t[1],
                        "minutes": self.mt._minutes(t[1]) - self.mt._minutes(t[0])} for t in trous],
             "temps_par_contexte_s": {"code": 60}, "actif_minutes": 1, "bascules_fenetre": 0}
        if poste:
            d["poste"] = poste
        return d

    def ecrire_digests(self, digests):
        with open(self.mt.FICHIER_ACTIVITE, "w", encoding="utf-8") as f:
            for d in digests:
                f.write(json.dumps(d) + "\n")

    def lire_digests(self):
        with open(self.mt.FICHIER_ACTIVITE, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def ecrire_sessions(self, evts):
        """evts : (genre, hhmm[, jour[, extra]])."""
        with open(self.mt.FICHIER_SESSIONS, "w", encoding="utf-8") as f:
            for e in evts:
                genre, hhmm = e[0], e[1]
                jour = e[2] if len(e) > 2 else self.JOUR
                ev = {"genre": genre, "quand": "%s %s" % (jour, hhmm), "ts": round(self.ts(hhmm, jour))}
                if len(e) > 3:
                    ev.update(e[3])
                f.write(json.dumps(ev) + "\n")

    def nuit(self, de, a, trous=(), veille=("00:00", "23:59"), rythme="auto"):
        historique = [d for d in self.lire_digests() if d["date"] != self.VEILLE] \
            if os.path.exists(self.mt.FICHIER_ACTIVITE) else []
        self.ecrire_digests(historique + [self.digest(self.VEILLE, veille[0], veille[1])])
        d = self.digest(self.JOUR, de, a, trous)
        return self.mt.sommeil_estime(self.JOUR, plage=d["plage"], trous=d["trous"], rythme=rythme)

    def jour_decale(self, date, c="05:26", r="16:15"):
        """Un digest complet d'une nuit decalee -- ce qui nourrit le rythme."""
        return self.digest(date, "00:00", "23:59", [(c, r)],
                           poste={"coucher": c, "reveil": r, "sommeil_h": 10.8, "source": "clavier"})

    def _jour_moins(self, i):
        j = self.JOUR
        for _ in range(i):
            j = self.mt._jour_avant(j)
        return j

    # ---- sommeil_estime : le clavier ----

    def test_lever_a_16h20_apres_coucher_a_05h26(self):
        """LE CAS. 16:20 est apres 16:00 : l'ancienne borne jetait la nuit et
        le repli rendait « reveil 00:00 »."""
        n = self.nuit("00:00", "22:10", [("05:26", "16:20")])
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"], n["source"]),
                         ("05:26", "16:20", 10.9, "clavier"))

    def test_pc_allume_toute_la_nuit(self):
        n = self.nuit("00:00", "19:47", [("05:10", "16:05")])
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"]), ("05:10", "16:05", 10.9))

    def test_windows_redemarre_seul_a_03h30(self):
        """Une extinction est une fin de plus, jamais une preuve qu'on etait
        debout : l'ancien `connus` la contenait, et le coucher tombait a 03:30."""
        self.ecrire_sessions([("extinction", "03:30"), ("demarrage", "03:31")])
        n = self.nuit("08:00", "12:00", veille=("08:00", "23:30"))
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"]), ("23:30", "08:00", 8.5))

    def test_journee_en_cours_sans_coucher_invente(self):
        """Debout a 04:18, pas encore couche : rien a dire, et surtout pas
        « reveil 00:00 » qui partait au site a l'envoi de 04:18."""
        self.assertIsNone(self.nuit("00:00", "04:18", veille=("16:20", "23:59")))
        self.mt.ACTIVITE.update(active=True, jour=self.JOUR, premiere="00:00", derniere="04:18", trous=[])
        self.assertNotIn("poste", self.mt.resume_activite())

    def test_le_cas_reel_du_7_septembre(self):
        self.ecrire_sessions([("extinction", "05:26", self.JOUR, {"deduit": True}),
                              ("demarrage", "16:20")])
        # Tel qu'enregistre par l'ancienne version, sans trou de reprise : pas de
        # nuit recevable, donc pas de lever -- pas 00:00.
        self.assertIsNone(self.nuit("00:00", "19:47"))
        # Avec le trou que la reprise ouvre desormais (R7) : la vraie nuit.
        n = self.nuit("00:00", "19:47", [("05:26", "16:20")])
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"], n["source"]),
                         ("05:26", "16:20", 10.9, "clavier"))

    def test_deux_fins_pour_la_meme_reprise(self):
        """Derniere touche 05:20, extinction 05:26 : deux candidats, le plus
        long gagne, et la source reste le clavier."""
        self.ecrire_sessions([("extinction", "05:26", self.JOUR, {"deduit": True}),
                              ("demarrage", "16:15")])
        n = self.nuit("00:00", "19:47", [("05:20", "16:16")], veille=("16:10", "23:59"))
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"], n["source"]),
                         ("05:20", "16:16", 10.9, "clavier"))
        n = self.nuit("00:00", "19:47", [("05:20", "15:31")], veille=("16:10", "23:59"))
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"]), ("05:20", "15:31", 10.2))

    def test_extinction_seule_le_coucher_vient_du_poste(self):
        self.ecrire_sessions([("extinction", "23:30", self.VEILLE)])
        n = self.nuit("08:02", "23:41", veille=("08:00", "23:00"))
        self.assertEqual((n["coucher"], n["reveil"], n["source"]), ("23:00", "08:02", "clavier"))
        n = self.nuit("08:02", "23:41", veille=("08:00", "23:25"))
        self.assertEqual(n["coucher"], "23:25")
        # Sans derniere touche connue la veille, l'extinction est la seule fin.
        self.ecrire_digests([])
        d = self.digest(self.JOUR, "08:02", "23:41")
        n = self.mt.sommeil_estime(self.JOUR, plage=d["plage"], trous=[], rythme=None)
        self.assertEqual((n["coucher"], n["reveil"], n["source"]), ("23:30", "08:02", "poste"))

    def test_un_reboot_de_mise_a_jour_ne_coupe_pas_la_nuit(self):
        self.ecrire_sessions([("extinction", "09:00", self.JOUR, {"deduit": True}),
                              ("demarrage", "09:01")])
        n = self.nuit("00:00", "19:47", [("05:26", "16:15")])
        self.assertEqual((n["coucher"], n["reveil"]), ("05:26", "16:15"))

    def test_verre_d_eau_sieste_et_silence_de_vingt_heures(self):
        n = self.nuit("00:00", "19:47", [("05:26", "09:00"), ("09:10", "16:15")])
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"]), ("05:26", "16:15", 10.7))
        n = self.nuit("00:00", "23:00", [("05:26", "16:15"), ("18:00", "21:00")], rythme=None)
        self.assertEqual((n["coucher"], n["reveil"]), ("05:26", "16:15"))
        self.assertIsNone(self.nuit("23:00", "23:59", veille=("00:00", "03:00")),
                          "vingt heures de silence, ce n'est pas une nuit")

    # ---- le rythme ----

    def test_le_rythme_departage(self):
        self.ecrire_digests([self.jour_decale(j) for j in [self._jour_moins(i) for i in range(8, 1, -1)]])
        n = self.nuit("00:00", "23:00", [("05:30", "16:00"), ("19:00", "21:30")])
        self.assertEqual((n["coucher"], n["reveil"]), ("05:30", "16:00"), "la sieste n'est pas la nuit")
        n = self.nuit("00:00", "23:00", [("05:30", "10:00"), ("12:00", "21:00")])
        self.assertEqual((n["coucher"], n["reveil"]), ("05:30", "10:00"),
                         "avec un rythme connu, l'absence de neuf heures n'est pas la nuit")
        n = self.nuit("00:00", "23:00", [("05:30", "10:00"), ("12:00", "21:00")], rythme=None)
        self.assertEqual((n["coucher"], n["reveil"]), ("05:30", "10:00"),
                         "sans rythme, le PREMIER gagne : meme reponse qu'avec le rythme")
        self.assertTrue(n["incertain"], "deux reprises, aucun rythme : c'est un pari")
        n = self.nuit("00:00", "23:00", [("12:00", "21:00")])
        self.assertEqual((n["coucher"], n["reveil"]), ("12:00", "21:00"), "seul candidat")

    def test_le_salarie_ne_dort_pas_au_bureau(self):
        """LE CAS QUI CASSAIT TOUT. Fixe laisse allume : silence de 09:00 a
        19:00, dix heures, contre une vraie nuit de 23:30 a 07:15, sept heures
        trois quarts. La duree elisait le bureau ; le PREMIER silence est la
        nuit. Et comme rien ne le prouve, on le dit : `incertain`."""
        n = self.nuit("07:15", "23:30", [("09:00", "19:00")],
                      veille=("07:20", "23:30"), rythme=None)
        self.assertEqual((n["coucher"], n["reveil"], n["sommeil_h"]), ("23:30", "07:15", 7.8))
        self.assertTrue(n["incertain"], "deux reprises, aucun rythme : c'est un pari")
        # Le week-end : un seul silence recevable, rien a departager.
        w = self.nuit("07:40", "23:59", veille=("08:00", "23:30"), rythme=None)
        self.assertEqual((w["coucher"], w["reveil"]), ("23:30", "07:40"))
        self.assertNotIn("incertain", w, "un seul candidat n'est pas une devinette")

    def test_une_nuit_devinee_ne_nourrit_pas_le_rythme(self):
        """Vingt jours de bureau devines contre huit week-ends surs : c'est le
        week-end qui doit faire le rythme. Avant la marque, les vingt journees
        de bureau entraient et le rythme confirmait le bureau."""
        jours = [self._jour_moins(i) for i in range(30, 0, -1)]
        digests = []
        for i, j in enumerate(jours):
            if i % 7 < 5:   # cinq jours ouvres : le bureau, devine
                digests.append(self.digest(j, "07:15", "23:30", [("09:00", "19:00")],
                                           poste={"coucher": "09:00", "reveil": "19:00",
                                                  "sommeil_h": 10.0, "source": "clavier",
                                                  "incertain": True}))
            else:           # le week-end : sur
                digests.append(self.digest(j, "07:40", "23:59", [],
                                           poste={"coucher": "23:30", "reveil": "07:40",
                                                  "sommeil_h": 8.2, "source": "clavier"}))
        self.ecrire_digests(digests)
        c, l = self.mt._rythme_connu(self.JOUR)
        self.assertTrue(1400 <= c <= 1420, ("coucher", c))
        self.assertTrue(455 <= l <= 465, ("lever", l))
        # Et ce rythme-la retrouve la vraie nuit du jour ambigu.
        n = self.nuit("07:15", "23:30", [("09:00", "19:00")], veille=("07:20", "23:30"))
        self.assertEqual((n["coucher"], n["reveil"]), ("23:30", "07:15"))
        self.assertNotIn("incertain", n, "tranchee par le rythme, elle est sure")

    def test_rythme_connu_ignore_les_postes_sans_coucher(self):
        mt = self.mt
        jours = [self._jour_moins(i) for i in range(31, 0, -1)]
        digests = []
        for i, j in enumerate(jours[:30]):
            if i % 3 == 2:
                digests.append(self.digest(j, "00:00", "19:47", poste={"reveil": "00:00", "source": "clavier"}))
            else:
                digests.append(self.jour_decale(j, "05:%02d" % (20 + i % 7), "16:%02d" % (10 + i % 5)))
        # Le digest du jour demande lui-meme n'entre pas.
        digests.append(self.jour_decale(self.JOUR, "12:00", "23:00"))
        self.ecrire_digests(digests)
        c, l = mt._rythme_connu(self.JOUR)
        self.assertTrue(320 <= c <= 330, c)
        self.assertTrue(970 <= l <= 980, l)
        self.ecrire_digests(digests[:6] + [d for d in digests[6:] if "coucher" not in (d.get("poste") or {})])
        self.assertEqual(mt._rythme_connu(self.JOUR), (None, None), "six nuits ne font pas un rythme")

    def test_mediane_horaire_sur_le_cercle(self):
        m = self.mt._mediane_horaire
        self.assertEqual(m([23 * 60 + 30, 30]), 0)
        self.assertEqual(m([326, 290, 360, 1410, 310, 340, 300]), 310)
        self.assertIsNone(m([]))
        self.assertEqual(self.mt._ecart_circulaire(1430, 10), 20)

    # ---- la reprise est un trou ----

    def journal_vif(self):
        self.mt.ACTIVITE["active"] = True

    def test_trou_de_reprise(self):
        mt = self.mt
        self.ecrire_digests([self.digest(self.JOUR, "00:00", "05:26")])
        self.journal_vif()
        mt._reinit_jour(reprendre=True, maintenant=self.ts("16:15"))
        self.assertEqual(mt.ACTIVITE["trou_depuis"], self.ts("05:26"))
        mt.activite_note("code.exe", True, maintenant=self.ts("16:16"))
        self.assertEqual(mt.ACTIVITE["trous"], [{"de": "05:26", "a": "16:16", "minutes": 650}])
        self.assertEqual(mt.ACTIVITE["trou_depuis"], 0.0)
        self.assertFalse(mt.ACTIVITE["reprise"])
        # Relance deux minutes apres la derniere touche : pas un trou.
        self.ecrire_digests([self.digest(self.JOUR, "00:00", "14:58")])
        mt._reinit_jour(reprendre=True, maintenant=self.ts("15:00"))
        mt.activite_note("code.exe", True, maintenant=self.ts("15:00"))
        self.assertEqual(mt.ACTIVITE["trous"], [])

    def test_pas_de_trou_artefact_a_la_relance_ni_a_minuit(self):
        mt = self.mt
        self.journal_vif()
        mt._reinit_jour(reprendre=True, maintenant=self.ts("00:31"))
        mt.activite_note("explorer.exe", False, maintenant=self.ts("00:31"))
        mt.activite_note("explorer.exe", False, maintenant=self.ts("00:35"))
        self.assertEqual(mt.ACTIVITE["trou_depuis"], 0.0, "personne devant : rien a ouvrir")
        mt.activite_note("code.exe", True, maintenant=self.ts("08:00"))
        self.assertEqual((mt.ACTIVITE["trous"], mt.ACTIVITE["premiere"]), ([], "08:00"))
        # Minuit : actif a 23:59 la veille, inactif a 00:00:02, touche a 07:00.
        mt._jour_courant = lambda: self.VEILLE
        mt._reinit_jour(maintenant=self.ts("23:00", self.VEILLE))
        mt.activite_note("code.exe", True, maintenant=self.ts("23:59", self.VEILLE))
        mt._jour_courant = lambda: self.JOUR
        mt.activite_note("code.exe", False, maintenant=self.ts("00:00") + 2)
        self.assertEqual(mt.ACTIVITE["jour"], self.JOUR)
        self.assertEqual(mt.ACTIVITE["trou_depuis"], 0.0)
        mt.activite_note("code.exe", True, maintenant=self.ts("07:00"))
        self.assertEqual((mt.ACTIVITE["trous"], mt.ACTIVITE["premiere"]), ([], "07:00"))
        self.assertEqual(mt._digest_enregistre(self.VEILLE)["plage"]["a"], "23:59")

    def test_un_gel_est_un_trou(self):
        mt = self.mt
        self.journal_vif()
        mt._reinit_jour(maintenant=self.ts("05:25"))
        mt.activite_note("code.exe", True, maintenant=self.ts("05:26"))
        mt.activite_note("code.exe", True, maintenant=self.ts("05:27"))
        mt.activite_note("code.exe", True, maintenant=self.ts("16:15"))   # la machine dormait
        self.assertEqual(mt.ACTIVITE["trous"], [{"de": "05:27", "a": "16:15", "minutes": 648}])
        # Deja inactif avant la veille : le trou ouvert est garde.
        mt._reinit_jour(maintenant=self.ts("04:29"))
        mt.activite_note("code.exe", True, maintenant=self.ts("04:30"))
        mt.activite_note("code.exe", True, maintenant=self.ts("04:45"))
        mt.activite_note("code.exe", True, maintenant=self.ts("04:59"))
        mt.activite_note("code.exe", False, maintenant=self.ts("05:00"))
        mt.activite_note("code.exe", True, maintenant=self.ts("16:15"))
        self.assertEqual(mt.ACTIVITE["trous"], [{"de": "05:00", "a": "16:15", "minutes": 675}])

    # ---- le journal du poste ----

    def lire_sessions(self):
        with open(self.mt.FICHIER_SESSIONS, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_deux_extinctions_a_trois_secondes_font_une_ligne(self):
        t = self.ts("23:30")
        self.mt.noter_session("extinction", quand_ts=t)
        self.mt.noter_session("extinction", quand_ts=t + 3)
        self.mt.noter_session("demarrage", quand_ts=t + 60)
        self.assertEqual([e["genre"] for e in self.lire_sessions()], ["extinction", "demarrage"])

    def test_le_coucher_perdu_est_note_avant_que_le_fil_ne_batte(self):
        """La course : le fil ecrivait battement.txt a son premier tour, pendant
        que fermer_session_perdue le lisait -- extinction a l'heure de l'allumage
        ou pas d'extinction du tout. Le fil ne part qu'apres."""
        mt = self.mt
        mt._fil_activite = lambda cfg: mt.battre()      # ce que fait le vrai fil en premier
        cfg = {"collecte_active": True, "collecte_envoi": False}
        for _ in range(200):
            with open(mt.FICHIER_BATTEMENT, "w") as f:
                f.write(str(round(self.ts("05:26"))))
            self.ecrire_sessions([("demarrage", "16:00", self.VEILLE)])
            with open(mt.FICHIER_MIGRATION, "w") as f:
                f.write("x")
            mt.SESSION["notee"] = False
            mt.BATTEMENT["dernier"] = 0.0
            mt.ouvrir_journal_du_poste(cfg)
            fil = mt.MOTEUR_ACTIVITE.get("fil")
            mt.arreter_activite()
            if fil:
                fil.join(5)
            evts = self.lire_sessions()
            self.assertEqual([e["genre"] for e in evts], ["demarrage", "extinction", "demarrage"])
            self.assertEqual(evts[1]["ts"], round(self.ts("05:26")))
            self.assertTrue(evts[1].get("deduit"))

    # ---- l'envoi ----

    def capter_envois(self):
        envois = []

        class Reponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"{}"

        def urlopen(requete, timeout=None, context=None):
            envois.append(json.loads(requete.data.decode("utf-8")))
            return Reponse()
        self.mt.urllib.request.urlopen = urlopen
        return envois

    def test_l_envoi_porte_la_veille_et_le_jour(self):
        mt = self.mt
        envois = self.capter_envois()
        cfg = {"pont_site": "http://site", "collecte_envoi": True}
        mt.ACTIVITE.update(active=True, jour=self.JOUR, premiere="00:00", derniere="19:47",
                           trous=[{"de": "05:26", "a": "16:20", "minutes": 654}])
        self.assertTrue(mt.envoyer_activite_au_site(cfg))
        self.assertEqual([d["date"] for d in envois[-1]["jours"]], [self.JOUR], "pas de veille : le jour seul")
        self.ecrire_digests([self.digest(self.VEILLE, "16:10", "23:59", [("18:00", "21:00")])])
        self.assertTrue(mt.envoyer_activite_au_site(cfg))
        jours = envois[-1]["jours"]
        self.assertEqual([d["date"] for d in jours], [self.VEILLE, self.JOUR])
        self.assertEqual(jours[0]["plage"]["a"], "23:59", "la veille part telle qu'elle est sur le disque")
        self.assertTrue(all(d["version"] == mt.VERSION for d in jours))
        self.assertEqual(jours[1]["poste"]["reveil"], "16:20")
        self.assertEqual(mt.SYNC["poste_envoye"], json.dumps(jours[1]["poste"], sort_keys=True))

    def test_le_fil_renvoie_quand_le_lever_change(self):
        mt = self.mt
        appels = []
        mt.fenetre_active = lambda: "code.exe"
        mt.secondes_inactivite = lambda: 0
        mt.synchroniser_activite = lambda cfg, minimum=120: appels.append(minimum)
        poste = {"coucher": "05:26", "reveil": "16:16", "sommeil_h": 10.8, "source": "clavier"}

        def un_tour():
            mt.MOTEUR_ACTIVITE["marche"] = False
            return {"date": self.JOUR, "poste": poste}
        mt.sauver_activite = un_tour
        mt.ACTIVITE.update(active=True, jour=self.JOUR)
        cfg = {"collecte_envoi": True}
        for attendu in ([120], [120, 120]):   # le poste n'est pas encore parti : envoi
            mt.MOTEUR_ACTIVITE.update(marche=True, sauve_le=0)
            mt._fil_activite(cfg)
            self.assertEqual(appels, attendu)
        mt.SYNC["poste_envoye"] = json.dumps(poste, sort_keys=True)
        for _ in range(2):                     # deja parti : rien
            mt.MOTEUR_ACTIVITE.update(marche=True, sauve_le=0)
            mt._fil_activite(cfg)
        self.assertEqual(appels, [120, 120])

    def test_la_consigne_d_envoi_survit_a_une_fermeture(self):
        """Le marqueur postes_v2 dit « c'est recalcule », pas « c'est arrive au
        site ». En memoire seule, une fermeture avant le premier envoi reussi
        perdait la consigne pour toujours : le recalcul ne repartait plus, et le
        site gardait ses vieilles nuits fausses, sans rien pour le signaler."""
        mt = self.mt
        jours = [self._jour_moins(i) for i in range(6, -1, -1)]
        self.ecrire_digests([self.jour_decale(j) for j in jours])
        cfg = {"pont_site": "http://site", "collecte_envoi": True, "collecte_active": True}
        self.assertTrue(mt.migrer_postes(cfg))
        self.assertTrue(cfg["historique_a_pousser"], "la consigne n'est pas allee sur le disque")
        # L'application se ferme : la memoire disparait, les reglages restent.
        mt.SYNC["tout_a_pousser"] = False
        relu = mt.charger_config()
        self.assertTrue(relu.get("historique_a_pousser"), "config.json ne porte pas la consigne")
        mt.ouvrir_journal_du_poste(dict(relu, collecte_active=False))
        self.assertTrue(mt.SYNC["tout_a_pousser"], "au relancement, l'historique ne repart pas")
        # Et l'envoi reussi l'efface, une fois.
        envois = self.capter_envois()
        mt.ACTIVITE.update(active=True, jour=self.JOUR)
        self.assertTrue(mt.envoyer_activite_au_site(relu))
        self.assertEqual(len(envois[-1]["jours"]), 7)
        self.assertFalse(relu["historique_a_pousser"])
        self.assertFalse(mt.charger_config().get("historique_a_pousser"))

    def test_migration_des_postes(self):
        mt = self.mt
        jours = [self._jour_moins(i) for i in range(11, -1, -1)]
        digests = []
        for i, j in enumerate(jours):
            if i % 3 == 2:
                digests.append(self.digest(j, "00:00", "23:59"))
            else:
                digests.append(self.digest(j, "00:00", "23:59", [("05:%02d" % (20 + i), "16:%02d" % (10 + i))],
                                           poste={"reveil": "00:00", "source": "clavier"}))
        self.ecrire_digests(digests)
        cfg = {"pont_site": "http://site", "collecte_envoi": True, "collecte_active": True}
        self.assertTrue(mt.migrer_postes(cfg))
        apres = self.lire_digests()
        complets = [d for d in apres if "coucher" in (d.get("poste") or {})]
        # Huit jours portent un trou de nuit, mais le PREMIER du journal n'a pas
        # de veille : on ne sait pas ou sa periode eveillee a fini, donc on ne
        # place pas sa nuit. Sept, et le premier jour reste vide -- c'est le
        # prix de ne plus lire une soiree dehors comme un sommeil.
        self.assertEqual(len(complets), 7)
        self.assertEqual([d["poste"]["reveil"] for d in complets][:2], ["16:11", "16:13"])
        self.assertNotIn("poste", apres[0], "le premier jour du journal n'a pas de veille")
        self.assertFalse(any("poste" in d and "coucher" not in d["poste"] for d in apres),
                         "plus aucun reveil sans coucher")
        self.assertTrue(os.path.exists(mt.FICHIER_MIGRATION))
        self.assertTrue(mt.SYNC["tout_a_pousser"])
        envois = self.capter_envois()
        mt.ACTIVITE.update(active=True, jour=self.JOUR)
        self.assertTrue(mt.envoyer_activite_au_site(cfg))
        self.assertEqual(len(envois[-1]["jours"]), 12, "tout l'historique, une fois")
        self.assertFalse(mt.SYNC["tout_a_pousser"])
        self.assertFalse(mt.migrer_postes(cfg), "le second lancement ne refait rien")


class AtelierGDI:
    """UN WINDOWS DE LABORATOIRE QUI COMPTE SES HANDLES.

    Une fuite de handles GDI ne se mesure pas sous Linux : ni win32gui, ni
    win32ui, ni quota de 10 000 objets. Ce qui se mesure, en revanche, c'est
    la seule chose qui compte ici -- que chaque objet CREE soit RENDU. On pose
    donc de faux modules win32 qui distribuent des numeros et les reprennent,
    et on regarde le registre a la fin. Un objet encore inscrit est un handle
    perdu ; sous Windows, c'est un de moins sur les 10 000 du processus.

    Ce que ce banc NE prouve PAS, et qu'aucun test ne prouvera d'ici :
      - que DeleteObject rende vraiment le handle cote Windows ;
      - que Tk meure sur un pixmap nul. Ces deux-la se verifient sur la
        machine de l'utilisateur, par le compteur pose dans le journal.
    """

    def __init__(self, casse_a=None):
        self.vivants = {}          # numero -> ce que c'est
        self.suivant = 100
        self.casse_a = casse_a     # nom de l'appel qui doit echouer
        self.faits = []

    def naitre(self, quoi):
        self.suivant += 1
        self.vivants[self.suivant] = quoi
        return self.suivant

    def mourir(self, numero):
        self.vivants.pop(numero, None)

    def etape(self, nom):
        self.faits.append(nom)
        if nom == self.casse_a:
            raise RuntimeError("Could not create DC.")

    # ---- les faux modules ----

    def poser(self, sys_modules):
        atelier = self

        class FauxBitmap:
            def __init__(self):
                self.numero = 0

            def CreateCompatibleBitmap(self, dc, c, l):
                atelier.etape("CreateCompatibleBitmap")
                self.taille = (c, l)
                self.numero = atelier.naitre("bitmap")

            def GetHandle(self):
                return self.numero

            def GetBitmapBits(self, _):
                atelier.etape("GetBitmapBits")
                c, l = self.taille
                return bytes([30, 20, 10, 0] * (c * l))

        class FauxDC:
            def __init__(self, numero, propre):
                self.numero, self.propre = numero, propre

            def CreateCompatibleDC(self):
                atelier.etape("CreateCompatibleDC")
                return FauxDC(atelier.naitre("dc memoire"), True)

            def DeleteDC(self):
                atelier.mourir(self.numero)

            def SelectObject(self, _):
                atelier.etape("SelectObject")

            def SetStretchBltMode(self, _):
                pass

            def StretchBlt(self, *_):
                atelier.etape("StretchBlt")

        class FauxWin32gui:
            @staticmethod
            def GetDesktopWindow():
                return 1

            @staticmethod
            def GetWindowDC(_):
                atelier.etape("GetWindowDC")
                return atelier.naitre("dc ecran")

            @staticmethod
            def ReleaseDC(_, numero):
                atelier.mourir(numero)

            @staticmethod
            def DeleteObject(numero):
                atelier.mourir(numero)

        class FauxWin32ui:
            @staticmethod
            def CreateDCFromHandle(numero):
                atelier.etape("CreateDCFromHandle")
                # Enveloppe le MEME handle que dc_ecran : rien de neuf.
                return FauxDC(numero, False)

            @staticmethod
            def CreateBitmap():
                return FauxBitmap()

        class FauxWin32con:
            SRCCOPY = 0x00CC0020
            HALFTONE = 4
            COLORONCOLOR = 3

        sys_modules["win32gui"] = FauxWin32gui
        sys_modules["win32ui"] = FauxWin32ui
        sys_modules["win32con"] = FauxWin32con


ZONE = {"left": 0, "top": 0, "width": 1920, "height": 1080}


class FuiteDeHandles(unittest.TestCase):
    """LE BITMAP DE LA VIGNETTE N'ETAIT DETRUIT PAR PERSONNE.

    pywin32 cree le CBitmap sans drapeau de destruction et n'appelle jamais
    ::DeleteObject : le ramasse-miettes ne rend pas le handle. _liberer_gdi
    rendait le contexte memoire et le contexte d'ecran, et laissait le bitmap.
    Une garde refaite par image -- ce que fait le chemin « Capture GDI perdue »
    -- perdait donc un objet par image, huit fois par seconde.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)
        self.faux = []

    def tearDown(self):
        for nom in ("win32gui", "win32ui", "win32con"):
            sys.modules.pop(nom, None)

    def atelier(self, casse_a=None):
        a = AtelierGDI(casse_a)
        a.poser(sys.modules)
        return a

    def test_un_cycle_complet_ne_laisse_aucun_handle(self):
        a = self.atelier()
        pixels = self.mt._vignette_gdi(ZONE, 4, 2)
        self.assertEqual(len(pixels), 8)
        self.assertEqual(pixels[0], (10, 20, 30), "BGRA relu a l'endroit")
        self.assertEqual(len(a.vivants), 3, "un dc d'ecran, un dc memoire, un bitmap")
        self.mt._liberer_gdi(self.mt._local.gdi)
        self.assertEqual(a.vivants, {}, "tout doit etre rendu, le bitmap compris")

    def test_le_bitmap_est_detruit_et_pas_seulement_les_contextes(self):
        """Le cas exact du plantage : les deux contextes etaient rendus, le
        bitmap non. Un seul objet oublie suffit -- c'est huit par seconde."""
        a = self.atelier()
        self.mt._vignette_gdi(ZONE, 4, 2)
        self.mt._liberer_gdi(self.mt._local.gdi)
        self.assertNotIn("bitmap", a.vivants.values())

    def test_mille_contextes_perdus_ne_coutent_pas_un_handle(self):
        """LE REGIME QUI A VIDE LE QUOTA. Session verrouillee ou changement de
        resolution : StretchBlt echoue, la garde est jetee, la suivante la
        refait. Mille images, c'est deux minutes a huit par seconde -- et
        c'etait mille handles perdus, soit un dixieme du quota du processus."""
        a = self.atelier(casse_a="StretchBlt")
        for _ in range(1000):
            self.assertIsNone(self.mt._vignette_gdi(ZONE, 4, 2))
        self.assertEqual(a.vivants, {},
                         "mille pertes de contexte, zero handle en fuite")

    def test_un_echec_en_cours_de_construction_ne_laisse_rien(self):
        """L'ancienne version ne rattrapait QUE le contexte d'ecran. Quand
        l'echec arrivait plus tard -- le bitmap qui ne s'alloue plus, ce qui
        est exactement ce qui arrive a court de handles -- le contexte memoire
        restait derriere, un par image."""
        for etape in ("CreateCompatibleDC", "CreateCompatibleBitmap",
                      "SelectObject"):
            with self.subTest(etape=etape):
                self.mt._local.gdi = None
                a = self.atelier(casse_a=etape)
                self.assertIsNone(self.mt._vignette_gdi(ZONE, 4, 2))
                self.assertEqual(a.vivants, {}, "echec en %s" % etape)

    def test_le_cas_du_journal_ne_laisse_rien_a_rendre(self):
        """« Could not create DC. » : GetWindowDC a rendu NULL sans poser
        d'erreur, donc rien n'avait ete acquis. Ce chemin-la ne fuit pas -- il
        crie. C'est ce que le journal de l'utilisateur montrait, et c'est
        pourquoi la fuite etait DEJA finie quand il l'a envoye."""
        a = self.atelier(casse_a="CreateDCFromHandle")
        self.assertIsNone(self.mt._vignette_gdi(ZONE, 4, 2))
        self.assertEqual(a.vivants, {})

    def test_changer_la_finesse_rend_l_ancienne_garde(self):
        """Le curseur « Finesse » change la taille de la vignette, donc jette
        la garde. Rare, mais c'est le meme chemin."""
        a = self.atelier()
        self.mt._vignette_gdi(ZONE, 4, 2)
        self.mt._vignette_gdi(ZONE, 8, 4)
        self.assertEqual(len(a.vivants), 3, "une seule garde a la fois")


class CoupeCircuitEcran(unittest.TestCase):
    """RIEN NE COMPTAIT LES ECHECS DE CAPTURE.

    La guirlande espace ses reconnexions depuis 1.24.3 ; l'ecran, lui,
    retentait a la cadence video, indefiniment. Huit fois par seconde, des
    heures durant : c'est ce qui transforme un incident borne -- un ecran
    verrouille -- en epuisement du quota graphique du processus.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def test_trois_rates_suspendent_la_capture(self):
        mt = self.mt
        self.assertTrue(mt.capture_autorisee())
        for _ in range(2):
            mt.echec_capture(True)
            self.assertTrue(mt.capture_autorisee(),
                            "un rate isole ne coupe rien : un changement de "
                            "resolution dure une image")
        mt.echec_capture(True)
        self.assertFalse(mt.capture_autorisee())

    def test_l_attente_grandit_puis_plafonne_a_une_minute(self):
        mt = self.mt
        attentes = []
        for _ in range(6):
            mt.echec_capture(True)
            if mt.ETAT["ecran"]["suspendue"]:
                attentes.append(round(mt.ETAT["ecran"]["reprise"]
                                      - time.monotonic()))
        self.assertEqual(attentes, [5, 15, 60, 60],
                         "cinq secondes de rattrapage, puis quinze, puis une "
                         "minute -- le meme plafond que la guirlande")

    def test_une_capture_qui_marche_remet_tout_a_zero(self):
        mt = self.mt
        for _ in range(5):
            mt.echec_capture(True)
        self.assertFalse(mt.capture_autorisee())
        mt.echec_capture(False)
        self.assertTrue(mt.capture_autorisee())
        self.assertEqual(mt.ETAT["ecran"]["echecs"], 0)

    def test_on_ne_renonce_jamais_a_l_ecran(self):
        """Une session verrouillee se deverrouille, un ecran en veille se
        rallume : on suspend, on n'abandonne pas. Apres l'attente, la
        capture repart d'elle-meme."""
        mt = self.mt
        for _ in range(50):
            mt.echec_capture(True)
        self.assertFalse(mt.capture_autorisee())
        mt.ETAT["ecran"]["reprise"] = time.monotonic() - 0.001
        self.assertTrue(mt.capture_autorisee())
        self.assertLessEqual(max(mt.ATTENTE_ECRAN), 60.0)

    def test_le_journal_ne_repete_pas_la_meme_panne(self):
        """DES CENTAINES DE FOIS DEUX PHRASES IDENTIQUES. C'est ce que
        l'utilisateur a envoye : 16 lignes par seconde, 4 Mo par heure, et
        pas un mot de plus qu'a la premiere. Une panne, une ligne."""
        mt = self.mt
        sortie = io.StringIO()
        vrai, sys.stdout = sys.stdout, sortie
        try:
            for _ in range(500):
                mt.signaler_capture("Capture GDI indisponible",
                                    "Could not create DC.")
            mt.signaler_capture("Capture ecran impossible", "GetWindowDC")
        finally:
            sys.stdout = vrai
        lignes = [l for l in sortie.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lignes), 2, "une ligne par panne, pas par image")
        self.assertIn("objets du processus", lignes[0],
                      "le compteur, seule mesure qui tranche entre « plus de "
                      "handles » et « plus de bureau »")

    def test_DEUX_phrases_qui_alternent_se_taisent_aussi(self):
        """C'est la forme EXACTE du journal recu, et le piege du correctif.

        Le chemin GDI echoue, le repli mss echoue derriere lui : deux phrases
        differentes, image apres image. Ne retenir que la DERNIERE dite ne
        deduplique alors rien du tout -- chacune differe toujours de celle
        d'avant -- et les deux repartent huit fois par seconde. C'est ce que
        montre le journal de l'utilisateur, et un correctif qui ne tient pas
        ce cas-la ne corrige rien de ce qu'on a vu."""
        mt = self.mt
        sortie = io.StringIO()
        vrai, sys.stdout = sys.stdout, sortie
        try:
            for _ in range(300):
                mt.signaler_capture("Capture GDI indisponible", "Could not create DC.")
                mt.signaler_capture("Capture ecran impossible", "GetWindowDC")
        finally:
            sys.stdout = vrai
        lignes = [l for l in sortie.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lignes), 2,
                         "600 appels, deux pannes, deux lignes")

    def test_une_panne_qui_revient_se_redit(self):
        """Sinon un deuxieme episode, des jours plus tard, serait muet."""
        mt = self.mt
        sortie = io.StringIO()
        vrai, sys.stdout = sys.stdout, sortie
        try:
            mt.signaler_capture("Capture GDI perdue", "x")
            mt.echec_capture(False)
            mt.signaler_capture("Capture GDI perdue", "x")
        finally:
            sys.stdout = vrai
        self.assertEqual(len(sortie.getvalue().splitlines()), 2)

    def test_le_compteur_d_objets_ne_leve_pas_hors_windows(self):
        """Il est appele depuis un chemin d'erreur : s'il levait, il
        remplacerait la panne a diagnostiquer par la sienne."""
        self.assertEqual(self.mt.objets_gdi(), (-1, -1))


class UnSeulFilDeCapture(unittest.TestCase):
    """Les caches de capture sont thread-local. Sur le pool par defaut ils se
    dupliquent par fil -- le journal de l'utilisateur en montre quatre -- et
    personne ne les rend jamais. La boucle attend chaque image avant de
    demander la suivante : un fil suffit."""

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)

    def test_l_executeur_de_capture_n_a_qu_un_fil(self):
        self.assertEqual(self.mt.EXECUTEUR_CAPTURE._max_workers, 1)

    def test_le_meme_fil_sert_toujours(self):
        fils = {self.mt.EXECUTEUR_CAPTURE.submit(
            threading.current_thread).result().name for _ in range(200)}
        self.assertEqual(len(fils), 1, "un seul jeu de contextes GDI")



if __name__ == "__main__":
    unittest.main(verbosity=2)


class JournalAPorteeDeClic(unittest.TestCase):
    """QUAND L'APPLICATION DISPARAIT, CE FICHIER EST LA SEULE CHOSE QUI PARLE.

    C'est lui qui a nomme la violation d'acces de la v1.24.4 -- et il a fallu
    expliquer un chemin entre %LOCALAPPDATA% et un dossier cache pour
    l'obtenir. Le prochain rapport ne doit pas demander ca.
    """

    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.mt = charger_module(self.dossier)
        self.jrn = os.path.join(self.dossier, "journal.log")
        self.mt.FICHIER_JOURNAL = self.jrn

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def test_la_copie_est_une_COPIE_pas_le_fichier_tenu_en_ecriture(self):
        """Le journal est ouvert en ecriture toute la vie du processus.

        L'envoyer tel quel, c'est envoyer un fichier qui bouge encore -- et
        sous Windows certains outils refusent de le lire pendant qu'il est
        tenu. La copie est figee ; on verifie qu'elle est bien un autre
        fichier, avec le meme contenu.
        """
        io.open(self.jrn, "w", encoding="utf-8").write("une ligne de panne\n")
        poses, souci = self.mt.journal_pour_partage(self.dossier)
        self.assertIsNone(souci)
        self.assertEqual(len(poses), 1)
        self.assertNotEqual(os.path.abspath(poses[0]), os.path.abspath(self.jrn),
                            "ce doit etre une copie, pas le fichier lui-meme")
        self.assertIn("une ligne de panne",
                      io.open(poses[0], encoding="utf-8").read())

    def test_LE_JOURNAL_PRECEDENT_PART_AVEC(self):
        """Une panne d'avant le dernier demarrage n'est plus dans le fichier
        courant -- la rotation l'a poussee dans .1 -- et c'est souvent
        celle-la qu'on cherche."""
        io.open(self.jrn, "w", encoding="utf-8").write("aujourd hui\n")
        io.open(self.jrn + ".1", "w", encoding="utf-8").write("la vraie panne\n")
        poses, souci = self.mt.journal_pour_partage(self.dossier)
        self.assertIsNone(souci)
        self.assertEqual(len(poses), 2, "les deux doivent partir")
        ensemble = "".join(io.open(p, encoding="utf-8").read() for p in poses)
        self.assertIn("la vraie panne", ensemble)

    def test_la_copie_porte_sa_date_dans_son_nom(self):
        """Deux copies faites deux jours de suite ne doivent pas s'ecraser :
        celle d'hier est parfois la seule qui porte la panne."""
        io.open(self.jrn, "w", encoding="utf-8").write("x\n")
        poses, _ = self.mt.journal_pour_partage(self.dossier)
        self.assertRegex(os.path.basename(poses[0]),
                         r"^machitool-journal-\d{8}-\d{4}\.log$")

    def test_un_journal_absent_le_dit_au_lieu_de_lever(self):
        """Le bouton est sur un chemin d'erreur : s'il levait, il remplacerait
        la panne a diagnostiquer par la sienne."""
        poses, souci = self.mt.journal_pour_partage(self.dossier)
        self.assertIsNone(poses)
        self.assertTrue(souci)

    def test_ouvrir_ce_qui_n_existe_pas_rend_une_raison(self):
        """Une ouverture qui echoue en silence laisse quelqu'un cliquer trois
        fois avant de comprendre qu'il ne se passera rien."""
        souci = self.mt.ouvrir_dans_l_explorateur(os.path.join(self.dossier, "absent.log"))
        self.assertTrue(souci)
