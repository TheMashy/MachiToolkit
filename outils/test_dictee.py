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
        self.m.DICTEE.update(etat="absent", progres=0.0, source=None, message="", modele=None, vu=0.0)

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

    # ---------- le son ----------

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_le_son_devient_du_texte_et_le_modele_ne_se_charge_qu_une_fois(self):
        self.poser_handy()
        self.m.preparer_dictee()
        faux = FauxModele()
        charges = []
        charger = lambda: charges.append(1) or faux
        self.assertEqual(self.m.transcrire(wav(1.0), charger=charger), "je rentre du boulot")
        self.assertEqual(self.m.transcrire(wav(2.0), charger=charger), "je rentre du boulot")
        self.assertEqual(len(charges), 1, "le modele de 1 Go rechargerait a chaque phrase")
        self.assertEqual(faux.appels[0], (16000, 16000))

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_la_stereo_devient_mono_et_un_clic_ne_reveille_rien(self):
        self.poser_handy()
        self.m.preparer_dictee()
        faux = FauxModele()
        self.m.transcrire(wav(1.0, canaux=2), charger=lambda: faux)
        self.assertEqual(faux.appels[0][0], 16000)
        self.m.DICTEE["modele"] = None
        self.assertEqual(self.m.transcrire(wav(0.05), charger=lambda: 1 / 0), "")

    @unittest.skipUnless(NUMPY, "numpy absent")
    def test_un_wav_8_bits_est_refuse(self):
        self.poser_handy()
        self.m.preparer_dictee()
        with self.assertRaises(ValueError):
            self.m.transcrire(wav(1.0, largeur=1), charger=lambda: FauxModele())

    def test_pas_pret_pas_de_transcription(self):
        with self.assertRaises(RuntimeError):
            self.m.transcrire(wav(1.0), charger=lambda: FauxModele())

    def test_le_moteur_quitte_la_memoire_quand_on_l_oublie(self):
        self.m.DICTEE.update(modele=FauxModele(), vu=1000.0)
        self.assertFalse(self.m.decharger_dictee_si_oubliee(1000.0 + 60))
        self.assertTrue(self.m.decharger_dictee_si_oubliee(1000.0 + self.m.DICTEE_DECHARGER_S + 1))
        self.assertIsNone(self.m.DICTEE["modele"])


class Route(unittest.TestCase):
    """La vraie passerelle, sur un port de test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["APPDATA"] = os.path.join(self.tmp, "appdata")
        self.m = charger_module(self.tmp)
        self.m.DOSSIER = os.path.join(self.tmp, "machi")
        os.makedirs(self.m.DOSSIER)
        self.m.DICTEE.update(etat="absent", progres=0.0, source=None, message="", modele=None, vu=0.0)
        self.m.CFG.clear()
        self.m.CFG.update({"api_origines": ["https://site.example"], "api_jeton": "jeton-local",
                           "pont_cle": "cle-du-pont"})
        self.m.dictee_possible = lambda: True
        self.serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self.m.Passerelle)
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.port = self.serveur.server_address[1]

    def tearDown(self):
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
        self.m.DICTEE.update(etat="pret", modele=FauxModele(texte), vu=0.0)

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
        self.assertEqual((code, rep), (200, {"texte": "une phrase tres privee"}))
        self.assertEqual(sorted(os.walk(self.tmp)), avant, "la dictee a ecrit quelque chose sur le disque")
        self.assertNotIn("privee", journal)

    def test_preparer_part_en_arriere_plan(self):
        self.m.preparer_dictee = lambda ouvrir=None: None
        code, etat = self.appel("POST", "/dictee/preparer")
        self.assertEqual(code, 202)

    def test_une_version_sans_moteur_le_dit(self):
        self.m.dictee_possible = lambda: False
        self.assertEqual(self.appel("POST", "/dictee", wav(1.0))[0], 501)


if __name__ == "__main__":
    unittest.main(verbosity=1)
