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
  - « MF » (Machi Tool d'avant) reste accepte.

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

// Le port serie : tout le flux d'un coup, et des « pauses » (plus longues que
// le delai de la carte) ou readBytes rend ce qu'il a, comme sur la vraie.
struct FauxSerial {
  std::vector<uint8_t> entree; size_t pos = 0;
  std::vector<size_t> pauses; std::string sortie;
  void setRxBufferSize(int) {} void begin(long) {} void setTimeout(long) {}
  int available() { return (int)(entree.size() - pos); }
  int read() { return pos < entree.size() ? entree[pos++] : -1; }
  size_t readBytes(uint8_t *d, size_t n) {
    size_t fin = std::min(entree.size(), pos + n);
    for (size_t p : pauses) if (p > pos && p < fin) { fin = p; break; }
    size_t k = fin - pos;
    memcpy(d, entree.data() + pos, k);
    pos = fin;
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
  for (int i = 3; i < argc; i++) Serial.pauses.push_back((size_t)atol(argv[i]));
  setup();
  long avant = panneau->dessins;
  while (Serial.available() >= 2) loop();
  FILE *o = fopen(argv[2], "wb");
  for (int i = 0; i < 64 * 64; i++) { fputc(panneau->px[i] >> 8, o); fputc(panneau->px[i] & 0xFF, o); }
  fclose(o);
  printf("%sDESSINS %ld\n", Serial.sortie.c_str(), panneau->dessins - avant);
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
        with open(os.path.join(cls.dossier, "ESP32-HUB75-MatrixPanel-I2S-DMA.h"), "w") as f:
            f.write(ENTETE)
        source = os.path.join(cls.dossier, "principal.cpp")
        with open(source, "w") as f:
            f.write(PRINCIPAL)
        cls.carte = os.path.join(cls.dossier, "carte")
        r = subprocess.run([COMPILATEUR, "-std=c++17", "-O1", "-Wall", "-I", cls.dossier, "-I", CROQUIS,
                            source, "-o", cls.carte], capture_output=True, text=True)
        if r.returncode:
            raise AssertionError("le croquis ne compile pas :\n" + r.stderr)
        cls.avertissements = r.stderr

    def envoyer(self, flux, pauses=()):
        """Le flux a la carte ; rend (ce que le panneau montre, en RGB565 64 x 64,
        ce qu'elle a repondu, le nombre de pixels dessines apres la mire)."""
        entree = os.path.join(self.dossier, "entree.bin")
        sortie = os.path.join(self.dossier, "panneau.bin")
        with open(entree, "wb") as f:
            f.write(flux)
        r = subprocess.run([self.carte, entree, sortie] + [str(p) for p in pauses],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(sortie, "rb") as f:
            panneau = np.frombuffer(f.read(), ">u2").reshape(64, 64)
        dessins = int(r.stdout.rsplit("DESSINS ", 1)[1])
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
        self.assertIn("MACHI 3", reponses)
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

    def test_la_luminosite_reste_sous_le_plafond(self):
        _, reponses, _ = self.envoyer(b"MB\xff" + self.M.trame_image(self.image(6), 3) + b"MS")
        self.assertIn("STATS 1 0", reponses, "« MB » ne derange pas les images qui suivent")


if __name__ == "__main__":
    unittest.main(verbosity=1)
