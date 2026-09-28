# -*- coding: utf-8 -*-
"""
LA DICTEE : LA VOIX DEVIENT DU TEXTE SUR CE POSTE, ET NULLE PART AILLEURS.

Demande : integrer a Machi Tool le moteur local de Handy (Parakeet V3, en
ONNX) pour dicter dans BrainDebugger. Ces cas tiennent ce qui a ete promis :

  - le modele de Handy est REPRIS s'il existe (liens durs, zero octet de plus),
    sinon telecharge une fois, et un telechargement coupe ne passe jamais pour
    un modele complet ;
  - la config qui fait lire 128 bandes a Parakeet est posee — sans elle le
    modele se charge et rend du charabia ;
  - le son ne touche jamais le disque, et le texte n'est jamais journalise ;
  - la route exige la cle, refuse un son vide ou enorme, et dit quand le
    modele n'est pas pret ;
  - le moteur (1 Go) quitte la memoire quand on ne s'en sert plus.

Le vrai modele ne se telecharge pas ici : un faux tient sa place, avec la
meme interface (`recognize(son, sample_rate=...)`).

    python outils/test_dictee.py
"""
import http.client
import http.server
import importlib.util
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest
import wave

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import numpy  # noqa: F401
    NUMPY = True
except Exception:
    NUMPY = False


def charger_module(dossier):
    os.environ["LOCALAPPDATA"] = dossier
    spec = importlib.util.spec_from_file_location("mt_dictee", os.path.join(RACINE, "machi_tool.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wav(secondes=1.0, frequence=16000, canaux=1, largeur=2):
    tampon = io.BytesIO()
    n = int(secondes * frequence)
    with wave.open(tampon, "wb") as w:
        w.setnchannels(canaux)
        w.setsampwidth(largeur)
        w.setframerate(frequence)
        w.writeframes(struct.pack("<%dh" % (n * canaux), *([1000] * n * canaux)) if largeur == 2
                      else b"\x80" * n * canaux)
    return tampon.getvalue()


class FauxModele:
    def __init__(self, texte="je rentre du boulot"):
        self.texte = texte
        self.appels = []

    def recognize(self, son, sample_rate=16000):
        self.appels.append((len(son), sample_rate))
        return self.texte


class FausseReponse(io.BytesIO):
    def __init__(self, octets):
        super().__init__(octets)
        self.headers = {"Content-Length": str(len(octets))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Dictee(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.appdata = os.path.join(self.tmp, "appdata")
        os.makedirs(self.appdata)
        os.environ["APPDATA"] = self.appdata
        self.m = charger_module(self.tmp)
        self.m.DOSSIER = os.path.join(self.tmp, "machi")
        os.makedirs(self.m.DOSSIER)
        self.m.DICTEE.update(etat="absent", progres=0.0, source=None, message="")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def poser_handy(self, niveau_de_plus=False):
        d = os.path.join(self.appdata, "com.pais.handy", "models", self.m.DICTEE_MODELE)
        if niveau_de_plus:
            d = os.path.join(d, "parakeet")
        os.makedirs(d)
        for nom in self.m.DICTEE_FICHIERS:
            with open(os.path.join(d, nom), "wb") as f:
                f.write(nom.encode() * 10)
        return d

    # ---------- le modele ----------

    def test_le_modele_de_handy_est_repris_sans_rien_telecharger(self):
        source = self.poser_handy()
        def interdit(url):
            raise AssertionError("telechargement alors que Handy avait le modele : " + url)
        self.assertEqual(self.m.preparer_dictee(ouvrir=interdit), "pret")
        self.assertEqual(self.m.DICTEE["source"], "handy")
        cible = self.m.dossier_dictee()
        for nom in self.m.DICTEE_FICHIERS:
            a, b = os.stat(os.path.join(source, nom)), os.stat(os.path.join(cible, nom))
            self.assertEqual((a.st_ino, a.st_dev), (b.st_ino, b.st_dev),
                             "%s copie au lieu d'etre lie : 456 Mo de plus sur le disque" % nom)

    def test_handy_avec_un_dossier_de_plus_dans_l_archive(self):
        self.poser_handy(niveau_de_plus=True)
        self.assertTrue(self.m.dossier_modele_handy())
        self.assertEqual(self.m.preparer_dictee(ouvrir=lambda u: 1 / 0), "pret")

    def test_la_config_des_128_bandes_est_posee(self):
        self.poser_handy()
        self.m.preparer_dictee()
        with open(os.path.join(self.m.dossier_dictee(), "config.json"), encoding="utf-8") as f:
            config = json.load(f)
        self.assertEqual(config["features_size"], 128)
        self.assertEqual(config["model_type"], "nemo-conformer-tdt")

    def test_sans_handy_on_telecharge_les_trois_fichiers(self):
        vus = []
        def ouvrir(url):
            vus.append(url)
            return FausseReponse(b"x" * 5000)
        self.assertEqual(self.m.preparer_dictee(ouvrir=ouvrir), "pret")
        self.assertEqual(self.m.DICTEE["source"], "telechargement")
        self.assertEqual(sorted(u.rsplit("/", 1)[1] for u in vus), sorted(self.m.DICTEE_FICHIERS))
        self.assertEqual(self.m.DICTEE["progres"], 1.0)
        restes = [f for f in os.listdir(self.m.dossier_dictee()) if f.endswith(".part")]
        self.assertEqual(restes, [])

    def test_un_telechargement_coupe_ne_passe_pas_pour_un_modele(self):
        compte = {"n": 0}
        class Coupe(FausseReponse):
            def read(self, n=-1):
                compte["n"] += 1
                if compte["n"] > 2:
                    raise ConnectionResetError("coupure")
                return super().read(1000)
        self.assertEqual(self.m.preparer_dictee(ouvrir=lambda u: Coupe(b"x" * 50000)), "erreur")
        self.assertFalse(self.m.dossier_complet(self.m.dossier_dictee()))
        self.assertNotEqual(self.m.etat_dictee()["etat"], "pret")

    def test_pas_pret_pas_de_transcription(self):
        with self.assertRaises(RuntimeError):
            self.m.transcrire(wav(1.0))


# Un faux moteur, lance comme le vrai : un processus a part, qui se connecte a
# Machi Tool et rend un texte. FAUX_MOURIR le fait tomber en pleine phrase,
# FAUX_SECRET lui fait donner un mauvais secret.
FAUX_ENFANT = r"""
import importlib.util, os, sys, time
spec = importlib.util.spec_from_file_location("mt_enfant", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
N = [0]
class Faux:
    def recognize(self, son, sample_rate=16000):
        N[0] += 1
        if os.environ.get("FAUX_MOURIR"):
            os._exit(3)
        une_fois = os.environ.get("FAUX_MOURIR_UNE_FOIS")
        if une_fois and not os.path.exists(une_fois):
            open(une_fois, "w").close()
            os._exit(3)
        if os.environ.get("FAUX_DORMIR") and N[0] >= 2:
            time.sleep(float(os.environ["FAUX_DORMIR"]))
        return "%s|%d|%d|%d" % (os.environ.get("FAUX_TEXTE", "bonjour"), len(son), sample_rate, os.getpid())
class R:
    def __init__(self, text, tokens, timestamps):
        self.text, self.tokens, self.timestamps = text, tokens, timestamps
class Ancre:
    # sans contexte il derive ; avec la porteuse devant (un son plus long), il lit juste
    def with_timestamps(self):
        return Dates()
    def recognize(self, son, sample_rate=16000):
        return Dates().recognize(son, sample_rate).text
class Dates:
    def recognize(self, son, sample_rate=16000):
        if len(son) <= sample_rate * 1.0:
            return R("Não.", ["▁Não", "."], [0.3, 0.9])
        return R("Je vous écoute. Non.", ["▁Je", "▁vous", "▁écoute", ".", "▁Non", "."],
                 [0.1, 0.3, 0.5, 1.02, 1.5, 1.7])
secret = os.environ.get("FAUX_SECRET") or sys.argv[3]
m.moteur_dictee_enfant(sys.argv[2], secret, charger=lambda: Ancre() if os.environ.get("FAUX_ANCRE") else Faux())
"""


class MoteurAPart(unittest.TestCase):
    """Le moteur dans son propre processus : s'il tombe, Machi Tool reste."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["APPDATA"] = os.path.join(self.tmp, "appdata")
        self.m = charger_module(self.tmp)
        self.m.DOSSIER = os.path.join(self.tmp, "machi")
        d = self.m.dossier_dictee()
        os.makedirs(d)
        for nom in self.m.DICTEE_FICHIERS:
            with open(os.path.join(d, nom), "wb") as f:
                f.write(b"x")
        self.m.DICTEE.update(etat="pret")
        self.script = os.path.join(self.tmp, "faux_moteur.py")
        with open(self.script, "w", encoding="utf-8") as f:
            f.write(FAUX_ENFANT)
        self.lances = []
        self.vraie_commande = self.m._commande_moteur
        def commande(port, secret):
            self.lances.append(port)
            return [sys.executable, self.script, os.path.join(RACINE, "machi_tool.py"), str(port), secret]
        self.m._commande_moteur = commande
        self.m.memoire_libre_mo = lambda: 8000
        for k in ("FAUX_MOURIR", "FAUX_SECRET", "FAUX_TEXTE"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.m._arreter_moteur()
        for k in ("FAUX_MOURIR", "FAUX_SECRET", "FAUX_TEXTE"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_texte_vient_d_un_autre_processus_lance_une_seule_fois(self):
        texte, n, freq, pid = self.m.transcrire(wav(1.0)).split("|")
        self.assertEqual((texte, int(n), int(freq)), ("bonjour", 16000, 16000))
        self.assertNotEqual(int(pid), os.getpid(), "le moteur tourne DANS Machi Tool")
        pid2 = self.m.transcrire(wav(2.0)).split("|")[3]
        self.assertEqual(pid, pid2, "un nouveau moteur a chaque phrase : 1 Go recharge a chaque fois")
        self.assertEqual(len(self.lances), 1)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_stereo_devient_mono(self):
        self.assertEqual(self.m.transcrire(wav(1.0, canaux=2)).split("|")[1], "16000")

    def test_un_wav_8_bits_ou_illisible_est_refuse_sans_lancer_le_moteur(self):
        with self.assertRaises(ValueError):
            self.m.transcrire(wav(1.0, largeur=1))
        with self.assertRaises(ValueError):
            self.m.transcrire(b"pas du tout un wav")
        self.assertEqual(self.lances, [])

    def test_un_clic_ne_reveille_rien(self):
        self.assertEqual(self.m.transcrire(wav(0.05)), "")
        self.assertEqual(self.lances, [])

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_si_le_moteur_tombe_machi_tool_reste_debout_et_le_dit(self):
        os.environ["FAUX_MOURIR"] = "1"
        with self.assertRaises(self.m.DicteeImpossible) as e:
            self.m.transcrire(wav(1.0))
        self.assertIn("tourne toujours", str(e.exception))
        self.assertIsNone(self.m._MOTEUR["proc"])
        # un moteur qui tombe est relance une fois pour la meme phrase (v1.65) :
        # qui retombe, c'est fini pour cette phrase -- deux lancements
        self.assertEqual(len(self.lances), 2)
        # ...et la phrase suivante relance un moteur neuf.
        os.environ.pop("FAUX_MOURIR")
        self.assertTrue(self.m.transcrire(wav(1.0)).startswith("bonjour|"))
        self.assertEqual(len(self.lances), 3)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_un_moteur_qui_tombe_en_pleine_phrase_est_relance_et_la_phrase_lue(self):
        """La phrase etait perdue : il fallait rappeler Jarvis, et payer quand
        meme un moteur froid."""
        os.environ["FAUX_MOURIR_UNE_FOIS"] = os.path.join(self.tmp, "deja_tombe")
        self.addCleanup(os.environ.pop, "FAUX_MOURIR_UNE_FOIS", None)
        self.assertTrue(self.m.transcrire(wav(1.0)).startswith("bonjour|"))
        self.assertEqual(len(self.lances), 2)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_un_moteur_charge_qui_cale_ne_bloque_pas_cinq_minutes(self):
        """300 s de delai pour chaque phrase : un moteur qui calait tenait
        Jarvis « Je transcris... » cinq minutes. Charge, il a bien moins -- et
        on ne relance pas un moteur qui cale (sous une memoire qui pagine,
        recharger 1 Go aggraverait tout)."""
        os.environ["FAUX_DORMIR"] = "4"
        self.addCleanup(os.environ.pop, "FAUX_DORMIR", None)
        self.m.DICTEE_REPONSE_CHAUD_S = 0.5
        self.m.DICTEE_REPONSE_PAR_S = 0.0
        self.m.transcrire(wav(1.0))                  # le chargement : la premiere reponse
        self.assertTrue(self.m.moteur_chaud())
        t0 = time.time()
        with self.assertRaises(self.m.DicteeImpossible):
            self.m.transcrire(wav(1.0))
        self.assertLess(time.time() - t0, 2.5)
        self.assertEqual(len(self.lances), 1, "un moteur qui cale n'est pas relance")

    def test_la_priorite_remonte_une_fois_le_modele_charge(self):
        vus = []

        class FauxPsutil:
            NORMAL_PRIORITY_CLASS = 32

            class Process:
                def __init__(self, pid):
                    self.pid = pid

                def nice(self, v):
                    vus.append((self.pid, v))

        class Proc:
            pid = 4242

            def poll(self):
                return 0
        self.m._MOTEUR.update(proc=Proc(), charge=False)
        self.assertTrue(self.m._moteur_charge(FauxPsutil, windows=True))
        self.assertFalse(self.m._moteur_charge(FauxPsutil, windows=True))
        self.assertEqual(vus, [(4242, 32)], "une seule fois, apres le chargement")
        self.m._MOTEUR["charge"] = False
        self.assertFalse(self.m._moteur_charge(FauxPsutil, windows=False))
        self.assertEqual(len(vus), 1)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_porteuse_ancre_la_langue_d_une_reponse_courte(self):
        """« Non » transcrit « Não » : avec la porteuse, « Non »."""
        os.environ["FAUX_ANCRE"] = "1"
        self.addCleanup(os.environ.pop, "FAUX_ANCRE", None)
        self.assertEqual(self.m.transcrire(wav(1.0)), "Não.")
        self.assertEqual(self.m.transcrire(wav(1.0), porteuse=wav(1.0)), "Non.")
        # une porteuse a une autre frequence ne part pas
        self.assertEqual(self.m.transcrire(wav(1.0), porteuse=wav(1.0, frequence=22050)), "Não.")
        self.assertEqual(len(self.lances), 1)

    def test_pas_assez_de_memoire_on_ne_lance_rien(self):
        self.m.memoire_libre_mo = lambda: 600
        with self.assertRaises(self.m.DicteeImpossible) as e:
            self.m.transcrire(wav(1.0))
        self.assertIn("600 Mo", str(e.exception))
        self.assertIn("Handy", str(e.exception))
        self.assertEqual(e.exception.cle, "memoire_pleine", "Jarvis dit une phrase courte, pas celle-ci")
        self.assertEqual(self.lances, [], "le moteur a ete lance malgre le manque de memoire")

    def test_un_imposteur_sans_le_secret_est_refuse(self):
        os.environ["FAUX_SECRET"] = "0" * 32
        with self.assertRaises(self.m.DicteeImpossible):
            self.m.transcrire(wav(1.0))
        self.assertIsNone(self.m._MOTEUR["sock"])

    def test_un_moteur_qui_ne_demarre_pas_ne_bloque_pas_pour_toujours(self):
        self.m.DICTEE_DEMARRAGE_S = 1
        self.m._commande_moteur = lambda port, secret: [sys.executable, "-c", "import time; time.sleep(30)"]
        with self.assertRaises(self.m.DicteeImpossible) as e:
            self.m.transcrire(wav(1.0))
        self.assertIn("pas demarre", str(e.exception))

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_oublie_le_moteur_s_en_va_et_rend_sa_memoire(self):
        self.m.transcrire(wav(1.0))
        proc = self.m._MOTEUR["proc"]
        self.assertFalse(self.m.decharger_dictee_si_oubliee(time.time() + 60))
        self.assertTrue(self.m.decharger_dictee_si_oubliee(time.time() + self.m.DICTEE_DECHARGER_S + 1))
        self.assertIsNotNone(proc.wait(timeout=10), "le processus du moteur ne s'est pas arrete")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_vrai_point_d_entree_lance_le_moteur_et_rien_d_autre(self):
        """Machi Tool relance avec --moteur-dictee ne doit pas ouvrir une
        seconde icone : il repond au son. Sans modele ici, il repond une
        erreur — la preuve qu'il a bien tourne comme moteur."""
        self.m._commande_moteur = self.vraie_commande
        self.m.DICTEE_DEMARRAGE_S = 30
        with self.assertRaises(self.m.DicteeImpossible) as e:
            self.m.transcrire(wav(1.0))
        self.assertIn("a echoue", str(e.exception), str(e.exception))


try:
    import onnxruntime  # noqa: F401
    ONNX = True
except Exception:
    ONNX = False


class Discretion(unittest.TestCase):
    """Par defaut onnxruntime prend TOUS les coeurs : le PC gelait pendant la
    dictee. La moitie, et pas d'arene gardee apres usage."""

    @unittest.skipUnless(ONNX, "onnxruntime absent")
    def test_le_moteur_ne_prend_que_la_moitie_des_coeurs(self):
        tmp = tempfile.mkdtemp()
        try:
            m = charger_module(tmp)
            vus = {}
            import onnx_asr
            vrai = onnx_asr.load_model
            onnx_asr.load_model = lambda *a, **k: vus.update(k) or "modele"
            try:
                m._charger_modele_dictee()
            finally:
                onnx_asr.load_model = vrai
            o = vus["sess_options"]
            self.assertLessEqual(o.intra_op_num_threads, max(1, (os.cpu_count() or 2) // 2))
            self.assertGreaterEqual(o.intra_op_num_threads, 1)
            self.assertFalse(o.enable_cpu_mem_arena)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Rapidite(unittest.TestCase):
    def test_savoir_si_le_moteur_est_la_ne_le_charge_pas(self):
        """« es-tu la ? » doit repondre tout de suite : charger onnxruntime
        prenait assez longtemps pour que la page conclue a une panne."""
        tmp = tempfile.mkdtemp()
        try:
            m = charger_module(tmp)
            for nom in [k for k in sys.modules if k.split(".")[0] in ("onnx_asr", "onnxruntime")]:
                del sys.modules[nom]
            m.dictee_possible()
            charges = [k for k in sys.modules if k.split(".")[0] in ("onnx_asr", "onnxruntime")]
            self.assertEqual(charges, [], "dictee_possible a importe le moteur")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Route(unittest.TestCase):
    """La vraie passerelle, sur un port de test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["APPDATA"] = os.path.join(self.tmp, "appdata")
        self.m = charger_module(self.tmp)
        self.m.DOSSIER = os.path.join(self.tmp, "machi")
        os.makedirs(self.m.DOSSIER)
        self.m.DICTEE.update(etat="absent", progres=0.0, source=None, message="")
        self.m.CFG.clear()
        self.m.CFG.update({"api_origines": ["https://site.example"], "api_jeton": "jeton-local",
                           "pont_cle": "cle-du-pont"})
        self.m.dictee_possible = lambda: True
        self.serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self.m.Passerelle)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.port = self.serveur.server_address[1]

    def tearDown(self):
        self.m._arreter_moteur()
        os.environ.pop("FAUX_TEXTE", None)
        os.environ.pop("FAUX_MOURIR", None)
        self.serveur.shutdown()
        self.serveur.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def appel(self, methode, chemin, corps=None, cle="cle-du-pont", origine="https://site.example"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Origin": origine}
        if cle:
            h["X-Machitool-Cle"] = cle
        if corps is not None:
            h["Content-Type"] = "audio/wav"
        c.request(methode, chemin, body=corps, headers=h)
        r = c.getresponse()
        charge = json.loads(r.read() or b"{}")
        c.close()
        return r.status, charge

    def rendre_pret(self, texte="je rentre du boulot"):
        d = self.m.dossier_dictee()
        os.makedirs(d)
        for nom in self.m.DICTEE_FICHIERS:
            with open(os.path.join(d, nom), "wb") as f:
                f.write(b"x")
        self.m.DICTEE.update(etat="pret")
        script = os.path.join(self.tmp, "faux_moteur.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(FAUX_ENFANT)
        os.environ["FAUX_TEXTE"] = texte
        self.m.memoire_libre_mo = lambda: 8000
        self.m._commande_moteur = lambda port, secret: [
            sys.executable, script, os.path.join(RACINE, "machi_tool.py"), str(port), secret]

    def test_sans_la_cle_rien(self):
        self.assertEqual(self.appel("GET", "/dictee", cle=None)[0], 401)
        self.assertEqual(self.appel("POST", "/dictee", wav(1.0), cle="mauvaise")[0], 401)

    def test_une_origine_inconnue_est_refusee(self):
        self.assertEqual(self.appel("POST", "/dictee", wav(1.0), origine="https://ailleurs.example")[0], 403)

    def test_l_etat_dit_s_il_faut_telecharger(self):
        code, etat = self.appel("GET", "/dictee")
        self.assertEqual(code, 200)
        self.assertEqual(etat["etat"], "absent")
        self.assertEqual(etat["taille_mo"], 456)
        self.assertFalse(etat["handy"])

    def test_pas_pret_la_route_le_dit(self):
        code, etat = self.appel("POST", "/dictee", wav(1.0))
        self.assertEqual(code, 409)
        self.assertEqual(etat["etat"], "absent")

    def test_un_son_vide_ou_enorme_est_refuse(self):
        self.rendre_pret()
        self.assertEqual(self.appel("POST", "/dictee", b"")[0], 413)
        self.m.DICTEE_MAX_OCTETS = 1000
        self.assertEqual(self.appel("POST", "/dictee", wav(1.0))[0], 413)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_texte_revient_et_rien_n_est_ecrit_ni_journalise(self):
        self.rendre_pret("une phrase tres privee")
        avant = sorted(os.walk(self.tmp))
        sortie, sys.stdout = sys.stdout, io.StringIO()
        try:
            code, rep = self.appel("POST", "/dictee", wav(1.5))
            journal = sys.stdout.getvalue()
        finally:
            sys.stdout = sortie
        self.assertEqual(code, 200)
        self.assertEqual(rep["texte"].split("|")[0], "une phrase tres privee")
        self.assertEqual(sorted(os.walk(self.tmp)), avant, "la dictee a ecrit quelque chose sur le disque")
        self.assertNotIn("privee", journal)

    def test_preparer_part_en_arriere_plan(self):
        self.m.preparer_dictee = lambda ouvrir=None: None
        code, etat = self.appel("POST", "/dictee/preparer")
        self.assertEqual(code, 202)

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_un_moteur_qui_tombe_se_dit_en_clair_et_la_passerelle_repond_encore(self):
        self.rendre_pret()
        os.environ["FAUX_MOURIR"] = "1"
        code, rep = self.appel("POST", "/dictee", wav(1.0))
        self.assertEqual(code, 503)
        self.assertIn("tourne toujours", rep["erreur"])
        self.assertEqual(self.appel("GET", "/dictee")[0], 200, "la passerelle ne repond plus")

    def test_une_version_sans_moteur_le_dit(self):
        self.m.dictee_possible = lambda: False
        self.assertEqual(self.appel("POST", "/dictee", wav(1.0))[0], 501)


if __name__ == "__main__":
    unittest.main(verbosity=1)
