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
        self.assertEqual((n["coucher"], n["reveil"]), ("12:00", "21:00"),
                         "sans rythme, le plus long gagne -- documente")
        n = self.nuit("00:00", "23:00", [("12:00", "21:00")])
        self.assertEqual((n["coucher"], n["reveil"]), ("12:00", "21:00"), "seul candidat")

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
        self.assertEqual(len(complets), 8)
        self.assertEqual([d["poste"]["reveil"] for d in complets][:2], ["16:10", "16:11"])
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
