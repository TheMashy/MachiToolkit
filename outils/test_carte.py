# -*- coding: utf-8 -*-
"""
LE CROQUIS DE LA CARTE, COMPILE ET NOURRI COMME PAR MACHI TOOL.

Demande : « j'ai des artefacts depuis le dernier flash arduino ». Le croquis
(carte/machi_panneau/machi_panneau.ino) tourne ici sur le PC : compile avec
g++, une fausse bibliotheque HUB75 qui garde les pixels en memoire, un faux
port serie qui peut couper un envoi en plein milieu (le delai de 200 ms de la
carte). On lui envoie les trames que Machi Tool fabrique (rgb565, fletcher16,
trame_image) et on regarde ce que le panneau montre.

Tenu ici :
  - une image controlee (« MG ») s'affiche exactement ; « MV » et « MS » repondent ;
  - une image abimee est jetee (et comptee) : le panneau garde la precedente ;
  - un envoi coupe ou decale se rattrape, sans pixel faux a la fin ;
  - deux lignes redessinees d'office par image : tout le panneau en 32 images ;
  - « MF » (Machi Tool d'avant) reste accepte ;
  - v7 : PC eteint, la carte dessine elle-meme les ambiances (« MA », gardes
    dans sa memoire ; « MW », « MO »), et reste noire apres une baisse de tension.

    python outils/test_carte.py        (sans g++ ou sans numpy, il se saute)
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROQUIS = os.path.join(RACINE, "carte", "machi_panneau")

try:
    import numpy as np
except ImportError:
    np = None

COMPILATEUR = shutil.which("g++")

# La fausse bibliotheque : juste ce que le croquis appelle.
ENTETE = r'''
#pragma once
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdarg>
#include <string>
#include <vector>
#include <algorithm>
using std::min;

struct HUB75_I2S_CFG {
  struct i2s_pins { int8_t r1, g1, b1, r2, g2, b2, a, b, c, d, e, lat, oe, clk; };
  enum shift_driver { SHIFTREG = 0, FM6124, FM6126A };
  int w, h, chain; i2s_pins pins; bool clkphase = true; shift_driver driver = SHIFTREG;
  HUB75_I2S_CFG(int w_, int h_, int c_, i2s_pins p_) : w(w_), h(h_), chain(c_), pins(p_) {}
};

struct MatrixPanel_I2S_DMA {
  uint16_t px[64 * 64] = {0};
  long dessins = 0;
  uint8_t lum = 0;
  MatrixPanel_I2S_DMA(const HUB75_I2S_CFG &) {}
  bool begin() { return true; }
  void setBrightness8(uint8_t b) { lum = b; }
  void clearScreen() { memset(px, 0, sizeof px); }
  uint16_t color565(uint8_t r, uint8_t g, uint8_t b) { return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3); }
  void drawPixel(int16_t x, int16_t y, uint16_t c) {
    if (x >= 0 && x < 64 && y >= 0 && y < 64) { px[y * 64 + x] = c; dessins++; }
  }
  void fillRect(int x, int y, int w, int h, uint16_t c) {
    for (int j = y; j < y + h; j++) for (int i = x; i < x + w; i++) drawPixel(i, j, c);
  }
  void drawRect(int x, int y, int w, int h, uint16_t c) {
    for (int i = x; i < x + w; i++) { drawPixel(i, y, c); drawPixel(i, y + h - 1, c); }
    for (int j = y; j < y + h; j++) { drawPixel(x, j, c); drawPixel(x + w - 1, j, c); }
  }
};

// Le temps : il avance avec les octets recus (250 Ko/s, le debit de Machi
// Tool), et d'un coup a chaque pause.
unsigned long horloge_ms = 0;
inline unsigned long millis() { return horloge_ms; }
inline void yield() {}

// Le port serie : tout le flux d'un coup, et des « pauses » (plus longues que
// le delai de la carte) ou readBytes rend ce qu'il a, comme sur la vraie.
struct FauxSerial {
  std::vector<uint8_t> entree; size_t pos = 0;
  std::vector<std::pair<size_t, unsigned long>> pauses; size_t passees = 0; std::string sortie;
  void setRxBufferSize(int) {} void begin(long) {} void setTimeout(long) {}
  void avancer(size_t nouvelle) {
    horloge_ms += (nouvelle / 250) - (pos / 250);
    pos = nouvelle;
  }
  void franchir() {             // une pause atteinte : le temps passe
    while (passees < pauses.size() && pauses[passees].first <= pos) horloge_ms += pauses[passees++].second;
  }
  int available() { franchir(); return (int)(entree.size() - pos); }
  long unitaires = 0;           // les lectures octet par octet (la v5 n'en faisait que ca)
  int read() { unitaires++; franchir(); if (pos >= entree.size()) return -1; int c = entree[pos]; avancer(pos + 1); return c; }
  // par blocs (la v6) : ce qui est arrive, jusqu'a la prochaine pause -- une pause, c'est un trou
  // dans le flux : rien n'arrive pendant qu'elle dure ; plus rien a lire, le temps passe aussi
  size_t read(uint8_t *d, size_t n) {
    if (passees < pauses.size() && pauses[passees].first <= pos) { horloge_ms += pauses[passees++].second; return 0; }
    if (pos >= entree.size()) { horloge_ms += 1; return 0; }
    size_t fin = std::min(entree.size(), pos + n);
    for (size_t i = passees; i < pauses.size(); i++)
      if (pauses[i].first > pos && pauses[i].first < fin) { fin = pauses[i].first; break; }
    size_t k = fin - pos;
    memcpy(d, entree.data() + pos, k);
    avancer(fin);
    return k;
  }
  size_t readBytes(uint8_t *d, size_t n) {
    franchir();
    size_t fin = std::min(entree.size(), pos + n);
    for (size_t i = passees; i < pauses.size(); i++)
      if (pauses[i].first > pos && pauses[i].first < fin) { fin = pauses[i].first; break; }
    size_t k = fin - pos;
    memcpy(d, entree.data() + pos, k);
    avancer(fin);
    return k;
  }
  void println(const char *s) { sortie += s; sortie += "\r\n"; }
  int printf(const char *f, ...) {
    char b[160]; va_list a; va_start(a, f); int n = vsnprintf(b, sizeof b, f, a); va_end(a);
    sortie += b; return n;
  }
};
extern FauxSerial Serial;
'''

# La memoire de la carte (NVS) : un fichier par cle (NVS=chemin), pour qu'elle
# survive a un « redemarrage » -- un second lancement du programme.
PREFERENCES = r'''
#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>
struct Preferences {
  std::map<std::string, std::vector<uint8_t>> cles;
  std::string dossier;
  long ecritures = 0;
  bool begin(const char *, bool = false) { const char *f = getenv("NVS"); if (f) dossier = f; return true; }
  size_t getBytes(const char *cle, void *d, size_t n) {
    std::vector<uint8_t> v;
    if (!dossier.empty()) {
      FILE *h = fopen((dossier + "." + cle).c_str(), "rb");
      if (!h) return 0;
      int c;
      while ((c = fgetc(h)) != EOF) v.push_back((uint8_t)c);
      fclose(h);
    } else if (cles.count(cle)) {
      v = cles[cle];
    }
    if (v.size() > n) return 0;
    memcpy(d, v.data(), v.size());
    return v.size();
  }
  size_t putBytes(const char *cle, const void *d, size_t n) {
    ecritures++;
    cles[cle].assign((const uint8_t *)d, (const uint8_t *)d + n);
    if (!dossier.empty()) {
      FILE *h = fopen((dossier + "." + cle).c_str(), "wb");
      fwrite(d, 1, n, h);
      fclose(h);
    }
    return n;
  }
};
'''

# Pourquoi la carte a (re)demarre : RESET=9, une baisse de tension.
ESP_SYSTEM = r'''
#pragma once
#include <cstdlib>
enum esp_reset_reason_t { ESP_RST_UNKNOWN = 0, ESP_RST_POWERON = 1, ESP_RST_BROWNOUT = 9 };
inline esp_reset_reason_t esp_reset_reason() {
  const char *r = getenv("RESET");
  return r ? (esp_reset_reason_t)atoi(r) : ESP_RST_POWERON;
}
'''

PRINCIPAL = r'''
#include "ESP32-HUB75-MatrixPanel-I2S-DMA.h"
#include <cstdlib>
FauxSerial Serial;
#include "machi_panneau.ino"

int main(int argc, char **argv) {
  FILE *f = fopen(argv[1], "rb");
  int c;
  while ((c = fgetc(f)) != EOF) Serial.entree.push_back((uint8_t)c);
  fclose(f);
  // les pauses : « position » (300 ms) ou « position:ms » ; « +ms » : le silence apres le flux
  unsigned long apres = 0;
  for (int i = 3; i < argc; i++) {
    if (argv[i][0] == '+') { apres = strtoul(argv[i] + 1, nullptr, 10); continue; }
    char *deux = strchr(argv[i], ':');
    Serial.pauses.push_back({(size_t)atol(argv[i]), deux ? strtoul(deux + 1, nullptr, 10) : 300});
  }
  setup();
  long avant = panneau->dessins;
  while (Serial.available() >= 2) loop();
  for (unsigned long fait = 0; fait < apres; fait += 100) { horloge_ms += 100; loop(); }
  FILE *o = fopen(argv[2], "wb");
  for (int i = 0; i < 64 * 64; i++) { fputc(panneau->px[i] >> 8, o); fputc(panneau->px[i] & 0xFF, o); }
  fclose(o);
  printf("%sUNITAIRES %ld\nDESSINS %ld\nLUM %d\nECRITURES %ld\n", Serial.sortie.c_str(), Serial.unitaires,
         panneau->dessins - avant, (int)panneau->lum, memoire.ecritures);
  return 0;
}
'''


def charger_module(dossier):
    os.environ["LOCALAPPDATA"] = dossier
    spec = importlib.util.spec_from_file_location("mt_carte", os.path.join(RACINE, "machi_tool.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(COMPILATEUR and np is not None, "g++ ou numpy absent")
class LaCarte(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.M = charger_module(tempfile.mkdtemp())
        cls.dossier = tempfile.mkdtemp()
        for nom, texte in (("ESP32-HUB75-MatrixPanel-I2S-DMA.h", ENTETE), ("Preferences.h", PREFERENCES),
                           ("esp_system.h", ESP_SYSTEM)):
            with open(os.path.join(cls.dossier, nom), "w") as f:
                f.write(texte)
        source = os.path.join(cls.dossier, "principal.cpp")
        with open(source, "w") as f:
            f.write(PRINCIPAL)
        cls.carte = os.path.join(cls.dossier, "carte")
        r = subprocess.run([COMPILATEUR, "-std=c++17", "-O1", "-Wall", "-I", cls.dossier, "-I", CROQUIS,
                            source, "-o", cls.carte], capture_output=True, text=True)
        if r.returncode:
            raise AssertionError("le croquis ne compile pas :\n" + r.stderr)
        cls.avertissements = r.stderr

    def envoyer(self, flux, pauses=(), nvs=None, reset=None):
        """Le flux a la carte ; rend (ce que le panneau montre, en RGB565 64 x 64,
        ce qu'elle a repondu, le nombre de pixels dessines apres la mire).
        `nvs` : le fichier de sa memoire ; `reset` : pourquoi elle a demarre."""
        entree = os.path.join(self.dossier, "entree.bin")
        sortie = os.path.join(self.dossier, "panneau.bin")
        with open(entree, "wb") as f:
            f.write(flux)
        env = dict(os.environ)
        env.pop("NVS", None)
        if nvs:
            env["NVS"] = nvs
        if reset is not None:
            env["RESET"] = str(reset)
        r = subprocess.run([self.carte, entree, sortie] + [str(p) for p in pauses],
                           capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(sortie, "rb") as f:
            panneau = np.frombuffer(f.read(), ">u2").reshape(64, 64)
        dessins = int(r.stdout.rsplit("DESSINS ", 1)[1].split()[0])
        return panneau, r.stdout, dessins

    def image(self, graine):
        """Une image d'horloge du vrai Machi Tool, a un instant donne (et, pour
        varier, une couleur), encodee comme il l'envoie."""
        img = self.M.image_panneau("horloge", 1_761_000_000 + graine * 37, accent=(255, 120 + graine % 100, 40))
        return self.M.rgb565(img)

    @staticmethod
    def attendu(donnees):
        return np.frombuffer(donnees, ">u2").reshape(64, 64)

    def test_compile_sans_avertissement(self):
        self.assertNotIn("warning", self.avertissements)

    def test_la_meme_somme_de_controle_des_deux_cotes(self):
        # la carte jette une image dont la somme ne colle pas : celle de Python doit
        # etre exactement la sienne, sinon toutes les images seraient jetees
        def a_la_main(d):
            a = b = 0
            for o in d:
                a = (a + o) % 255
                b = (b + a) % 255
            return (b << 8) | a
        for donnees in (bytes(8192), b"\xff" * 8192, os.urandom(8192), self.image(3)):
            self.assertEqual(self.M.fletcher16(donnees), a_la_main(donnees))

    def test_une_image_controlee_s_affiche_exactement(self):
        donnees = self.image(1)
        flux = b"MV" + self.M.trame_image(donnees, 3) + b"MS"
        panneau, reponses, _ = self.envoyer(flux)
        self.assertTrue((panneau == self.attendu(donnees)).all())
        self.assertIn("MACHI 7", reponses)
        self.assertIn("STATS 1 0", reponses)
        self.assertEqual(self.M.trame_image(donnees, 3)[:2], b"MG")
        self.assertEqual(self.M.trame_image(donnees, 2)[:2], b"MF", "a un croquis v2 : l'ancienne trame")

    def test_une_image_abimee_est_jetee(self):
        a, b = self.image(1), self.image(2)
        abimee = bytearray(self.M.trame_image(b, 3))
        abimee[2 + 4000] ^= 0x10                     # un bit qui saute en route
        panneau, reponses, _ = self.envoyer(self.M.trame_image(a, 3) + bytes(abimee) + b"MS")
        self.assertTrue((panneau == self.attendu(a)).all(), "le panneau garde la bonne image")
        self.assertIn("STATS 1 1", reponses)

    def test_un_envoi_coupe_puis_decale_se_rattrape_sans_pixel_faux(self):
        # ce qui arrive vraiment : une ecriture du PC coupee a mi-image (delai
        # depasse), la suite repart ; la carte lit une image decalee, se perd,
        # retrouve un en-tete -- a la fin, rien de faux ne doit rester affiche
        images = [self.image(k) for k in range(40)]
        trames = [self.M.trame_image(d, 3) for d in images]
        coupee = trames[5][:3000]                   # la 6e n'est partie qu'a moitie
        flux = b"".join(trames[:5]) + coupee + b"".join(trames[6:]) + b"MS"
        panneau, reponses, _ = self.envoyer(flux)
        self.assertTrue((panneau == self.attendu(images[-1])).all(), "la derniere image, exacte")
        recues, jetees = map(int, reponses.rsplit("STATS ", 1)[1].split()[:2])
        self.assertGreaterEqual(jetees, 1, "l'image coupee a ete jetee, pas dessinee")
        self.assertGreaterEqual(recues, 30)

    def test_vingt_coupures_au_hasard_ne_laissent_aucun_pixel_faux(self):
        import random
        alea = random.Random(7)
        images = [self.image(k) for k in range(40)]
        trames = [self.M.trame_image(d, 3) for d in images]
        for _ in range(20):
            coupe, n = alea.randint(3, 30), alea.randint(1, 8193)
            flux = b"".join(trames[:coupe]) + trames[coupe][:n] + b"".join(trames[coupe + 1:])
            panneau, _, _ = self.envoyer(flux)
            self.assertTrue((panneau == self.attendu(images[-1])).all(), (coupe, n))

    def test_une_pause_au_milieu_d_une_image_ne_laisse_rien(self):
        # la meme chose quand le PC s'arrete net au milieu (la carte attend
        # 200 ms puis abandonne l'image)
        images = [self.image(k) for k in range(10)]
        trames = [self.M.trame_image(d, 3) for d in images]
        flux = b"".join(trames[:3]) + trames[3][:5000]
        pause = len(flux)
        flux += b"".join(trames[4:])
        panneau, _, _ = self.envoyer(flux, pauses=[pause])
        self.assertTrue((panneau == self.attendu(images[-1])).all())

    def test_tout_le_panneau_est_redessine_en_32_images(self):
        # la meme image 32 fois : seulement les deux lignes d'office a chaque fois,
        # soit chaque pixel une fois -- ce qui se serait glisse de faux s'efface
        d = self.image(4)
        _, _, une = self.envoyer(self.M.trame_image(d, 3))
        _, _, n = self.envoyer(self.M.trame_image(d, 3) * 33)
        self.assertEqual(une, 64 * 64, "la premiere : tout")
        self.assertEqual(n - une, 32 * 2 * 64, "puis deux lignes par image")

    def test_l_ancienne_trame_reste_acceptee(self):
        # une version mal lue (« MV » perdu) : Machi Tool envoie « MF », la v3
        # l'affiche -- jamais un panneau fige
        d = self.image(5)
        panneau, reponses, _ = self.envoyer(self.M.trame_image(d, 1) + b"MS")
        self.assertTrue((panneau == self.attendu(d)).all())
        self.assertIn("STATS 1 0", reponses)

    def test_sans_image_le_panneau_s_eteint_seul(self):
        # « lorsque j'eteins le PC, le panneau ressemble a ca » : l'USB reste alimente,
        # la carte continue -- sans image depuis 5 s, elle s'eteint d'elle-meme
        d = self.image(7)
        trame = self.M.trame_image(d, 3)
        tient, _, _ = self.envoyer(trame, ["+4000"])
        self.assertTrue((tient == self.attendu(d)).all(), "4 s sans image : il garde l'image (un a-coup du PC)")
        noir, _, _ = self.envoyer(trame, ["+6000"])
        self.assertFalse(noir.any(), "6 s : noir")
        # et la suivante repart, exacte, sur ce noir
        e = self.image(8)
        retour, _, _ = self.envoyer(trame + self.M.trame_image(e, 3), ["%d:6000" % len(trame)])
        self.assertTrue((retour == self.attendu(e)).all())

    def test_au_demarrage_le_panneau_reste_noir(self):
        # « desactiver la mire qui s'allume en permanence quand l'ordi est eteint ou quand
        # Machi Tool n'est pas detecte » : la carte (re)demarre noire, et le reste
        for apres in ("+1000", "+6000"):
            noir, _, dessins = self.envoyer(b"", [apres])
            self.assertFalse(noir.any(), apres)
        # puis la premiere image s'affiche, exacte
        donnees = self.image(4)
        panneau, _, _ = self.envoyer(self.M.trame_image(donnees, 3))
        self.assertTrue((panneau == self.attendu(donnees)).all())

    def test_la_v6_lit_les_images_par_blocs(self):
        # « il y a toujours un probleme de stutter » -- 863 images abimees jetees par la carte : la v5
        # lisait chaque image octet par octet, la reserve de l'USB debordait. La v6 lit par blocs :
        # quelques lectures unitaires par image (l'en-tete), plus 8 192.
        images = [self.image(k) for k in range(10)]
        flux = b"".join(self.M.trame_image(d, 3) for d in images) + b"MS"
        panneau, reponses, _ = self.envoyer(flux)
        self.assertTrue((panneau == self.attendu(images[-1])).all())
        self.assertIn("STATS 10 0", reponses)
        unitaires = int(reponses.split("UNITAIRES ", 1)[1].split()[0])
        self.assertLess(unitaires, 10 * 10, "l'en-tete seulement, pas les pixels")
        with open(os.path.join(CROQUIS, "machi_panneau.ino"), encoding="utf-8") as f:
            croquis = f.read()
        self.assertNotIn("Serial.readBytes", croquis)
        self.assertIn("setRxBufferSize(65536)", croquis, "huit images de reserve")

    def test_la_luminosite_reste_sous_le_plafond(self):
        _, reponses, _ = self.envoyer(b"MB\xff" + self.M.trame_image(self.image(6), 3) + b"MS")
        self.assertIn("STATS 1 0", reponses, "« MB » ne derange pas les images qui suivent")


    # ---------------- v7 : les ecrans de veille, PC eteint ----------------

    def veille(self, **reglages):
        cfg = {"panneau_veille": True, "panneau_veille_luminosite": 30, "panneau_rouge": 100, "panneau_vert": 100,
               "panneau_bleu": 100}
        cfg.update(reglages)
        return self.M.trame_veille(cfg)

    @staticmethod
    def chiffre(reponses, nom):
        return int(reponses.rsplit(nom + " ", 1)[1].split()[0])

    def test_pc_eteint_la_carte_montre_ses_ambiances(self):
        # « c'est possible que tu laisses les screen savers meme a l'arret du PC ? »
        d = self.image(7)
        flux = self.veille() + self.M.trame_image(d, 3)
        tient, reponses, _ = self.envoyer(flux, ["+4000"])
        self.assertIn("VEILLE 1 1023", reponses, "les reglages recus : actif, les dix ambiances")
        self.assertTrue((tient == self.attendu(d)).all(), "4 s sans image : il garde l'image (un a-coup du PC)")
        veille, reponses, _ = self.envoyer(flux, ["+9000"])
        self.assertGreater(int((veille != 0).sum()), 2000, "PC eteint : une ambiance, tout le panneau")
        self.assertFalse((veille == self.attendu(d)).all())
        self.assertEqual(self.chiffre(reponses, "LUM"), 30, "a sa luminosite a elle")

    def test_decochee_ou_sans_ambiance_elle_reste_noire(self):
        d = self.M.trame_image(self.image(7), 3)
        for reglage in ({"panneau_veille": False}, {"panneau_veille_sans": list(self.M.ECRANS_AMBIANCES)}):
            with self.subTest(**{k: str(v)[:20] for k, v in reglage.items()}):
                noir, _, _ = self.envoyer(self.veille(**reglage) + d, ["+9000"])
                self.assertFalse(noir.any())

    def test_quitter_machi_tool_laisse_le_noir(self):
        # « quand Machi Tool s'eteint, eteins le panneau » : « MO », et pas d'ambiance au silence
        noir = bytes(8192)
        flux = self.veille() + self.M.trame_image(self.image(7), 3) + b"MB\x00" + b"MF" + noir + b"MO"
        panneau, _, _ = self.envoyer(flux, ["+9000"])
        self.assertFalse(panneau.any())

    def test_windows_qui_s_arrete_passe_la_main_tout_de_suite(self):
        d = self.image(7)
        panneau, _, _ = self.envoyer(self.veille() + self.M.trame_image(d, 3) + b"MW", ["+600"])
        self.assertFalse((panneau == self.attendu(d)).all(), "« MW » : l'ambiance, sans attendre 5 s")
        self.assertGreater(int((panneau != 0).sum()), 2000, "en fondu, deja la")

    def test_le_pc_revient_et_reprend_le_panneau(self):
        a, b = self.image(1), self.image(2)
        flux = b"MB\x50" + self.veille() + self.M.trame_image(a, 3) + b"MW"
        pause = len(flux)
        flux += self.M.trame_image(b, 3) + b"MS"
        panneau, reponses, _ = self.envoyer(flux, ["%d:3000" % pause])
        self.assertTrue((panneau == self.attendu(b)).all(), "son image, exacte")
        self.assertEqual(self.chiffre(reponses, "LUM"), 0x50, "a la luminosite du PC")

    def test_l_arret_programme(self):
        flux = self.veille(panneau_veille_arret_h=1) + b"MW"
        allume, _, _ = self.envoyer(flux, ["+3500000"])
        self.assertTrue(allume.any(), "58 min : encore la")
        noir, _, _ = self.envoyer(flux, ["+3700000"])
        self.assertFalse(noir.any(), "une heure : noir, jusqu'au retour du PC")

    def test_ses_reglages_survivent_a_une_coupure_mais_pas_une_baisse_de_tension(self):
        nvs = os.path.join(tempfile.mkdtemp(), "nvs")
        _, reponses, _ = self.envoyer(self.veille(), nvs=nvs)
        self.assertIn("VEILLE 1", reponses)
        noir, _, _ = self.envoyer(b"", ["+9000"], nvs=nvs, reset=9)
        self.assertFalse(noir.any(), "redemarree faute de tension : noire (plus jamais la boucle de la v5)")
        veille, _, _ = self.envoyer(b"", ["+9000"], nvs=nvs, reset=1)
        self.assertTrue(veille.any(), "rebranchee : ses ambiances, sans le PC")
        neuve, _, _ = self.envoyer(b"", ["+9000"])
        self.assertFalse(neuve.any(), "une carte sans reglages : noire, comme la v6")

    def test_des_reglages_abimes_sont_ignores(self):
        abimee = bytearray(self.veille())
        abimee[5] ^= 0x01
        noir, reponses, _ = self.envoyer(bytes(abimee) + self.M.trame_image(self.image(3), 3), ["+9000"])
        self.assertNotIn("VEILLE", reponses)
        self.assertFalse(noir.any())

    def test_la_memoire_ne_s_ecrit_que_si_ca_change(self):
        _, reponses, _ = self.envoyer(self.veille() * 3)
        self.assertEqual(self.chiffre(reponses, "ECRITURES"), 1, "la flash s'use : une fois")
        _, reponses, _ = self.envoyer(self.veille() + self.veille(panneau_veille_luminosite=20))
        self.assertEqual(self.chiffre(reponses, "ECRITURES"), 2)

    def test_jamais_au_dessus_du_plafond(self):
        d = bytes([1, 1, 255, 3, 255, 0, 120, 0, 0, 100, 100, 100])
        _, reponses, _ = self.envoyer(b"MA" + d + self.M.fletcher16(d).to_bytes(2, "big") + b"MW", ["+500"])
        self.assertEqual(self.chiffre(reponses, "LUM"), 96, "PLAFOND, meme si on lui demande 255")

    def test_la_balance_du_panneau_vaut_aussi_pour_elles(self):
        def rouge(r):
            panneau, _, _ = self.envoyer(self.veille(panneau_rouge=r, panneau_veille_sans=["aurore_lac"] + [
                n for n in self.M.ECRANS_AMBIANCES if n not in ("coucher", "aurore_lac")]) + b"MW", ["+2000"])
            return int((panneau >> 11).sum()), int(((panneau >> 5) & 0x3F).sum())
        (r100, v100), (r50, v50) = rouge(100), rouge(50)
        self.assertLess(r50, r100 * 0.85, "le rouge baisse, comme sur les images du PC")
        self.assertEqual(v50, v100, "le vert ne bouge pas")

    def test_chaque_ambiance_se_dessine_et_bouge(self):
        # « keep only atmospheric effects » : les dix ambiances de Machi Tool, et elles seules
        self.assertEqual(len(self.M.ECRANS_AMBIANCES), 10)
        for i, nom in enumerate(self.M.ECRANS_AMBIANCES):
            with self.subTest(ambiance=nom):
                flux = self.veille(panneau_veille_sans=[n for n in self.M.ECRANS_AMBIANCES if n != nom]) + b"MW"
                _, reponses, _ = self.envoyer(flux)
                self.assertIn("VEILLE 1 %d" % (1 << i), reponses)
                a, _, _ = self.envoyer(flux, ["+3000"])
                b, _, _ = self.envoyer(flux, ["+4500"])
                self.assertGreater(int((a != 0).sum()), 1500, "elle se voit")
                self.assertFalse((a == b).all(), "elle bouge")
        with open(os.path.join(CROQUIS, "machi_panneau.ino"), encoding="utf-8") as f:
            croquis = f.read()
        for absent in ("matrice", "feu", "plasma", "tunnel"):
            self.assertNotIn("ecran_" + absent, croquis, "pas de jeux de lumiere a l'arret")


if __name__ == "__main__":
    unittest.main(verbosity=1)
