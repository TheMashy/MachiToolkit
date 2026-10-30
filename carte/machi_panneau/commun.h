// LES OUTILS COMMUNS DES ECRANS (croquis v10). Les jumeaux en C++ des helpers
// de machi_tool.py (_degrade, _peindre_sous, _halo, _brume, _fenetre, _pluie,
// _caustiques...) : chaque lot d'ecrans s'en sert. Tout se peint dans `scene`
// (64 x 64, flottants 0-255, sRGB), comme les images numpy de Machi Tool.
//
// LA MEMOIRE D'UN ECRAN. Un seul ecran tourne a la fois : son etat (ses
// particules, ses champs, ses trainees) vit dans l'« arene », reservee une
// fois au demarrage (dans la PSRAM de la MatrixPortal S3 quand il y en a).
// Chaque moteur declare sa struct E_<moteur> et la recoit, remise a zero au
// debut de l'ecran : `E_recif &e = etat_ecran<E_recif>(debut);`. Le registre ne
// propose pas un ecran dont l'etat ne tient pas dans l'arene.
#pragma once
#include <new>
#if defined(ARDUINO_ARCH_ESP32)
#include <esp_heap_caps.h>
#endif

uint8_t *arene = nullptr;
size_t arene_taille = 0;

void preparer_arene() {
  static const size_t TAILLES[] = {192 * 1024, 96 * 1024, 48 * 1024};
  for (size_t taille : TAILLES) {
#if defined(ARDUINO_ARCH_ESP32)
    arene = (uint8_t *)heap_caps_malloc(taille, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!arene && taille <= 96 * 1024) arene = (uint8_t *)malloc(taille);
#else
    arene = (uint8_t *)malloc(taille);
#endif
    if (arene) {
      arene_taille = taille;
      return;
    }
  }
}

template <class T> T &etat_ecran(bool debut) {
  T *p = reinterpret_cast<T *>(arene);
  if (debut) new (p) T();   // remis a zero : chaque ecran repart de rien
  return *p;
}

// --- les couleurs ---------------------------------------------------------

// le degrade de _degrade : (haut) en y0, (bas) en y1, borne entre les deux
void degrade2(float r0, float v0, float b0, float r1, float v1, float b1, float y0 = 0, float y1 = 64) {
  const float h = fmaxf(1.0f, y1 - y0);
  for (int y = 0; y < H; y++) {
    const float k = borne((y - y0) / h, 0, 1);
    const float r = r0 + (r1 - r0) * k, v = v0 + (v1 - v0) * k, b = b0 + (b1 - b0) * k;
    for (int x = 0; x < W; x++) peindre(y, x, r, v, b);
  }
}

// _teintes : HSV (0-1) -> RGB (0-255)
void teinte(float h, float s, float v, float &r, float &g, float &b) {
  h = (h - floorf(h)) * 6.0f;
  const int i = (int)h % 6;
  const float f = h - floorf(h);
  const float p = v * (1 - s), q = v * (1 - s * f), u = v * (1 - s * (1 - f));
  float rr, gg, bb;
  switch (i) {
    case 0: rr = v; gg = u; bb = p; break;
    case 1: rr = q; gg = v; bb = p; break;
    case 2: rr = p; gg = v; bb = u; break;
    case 3: rr = p; gg = q; bb = v; break;
    case 4: rr = u; gg = p; bb = v; break;
    default: rr = v; gg = p; bb = q; break;
  }
  r = borne(rr, 0, 1) * 255; g = borne(gg, 0, 1) * 255; b = borne(bb, 0, 1) * 255;
}

// --- les points et les formes -----------------------------------------------

// _poser : un point qui ecrase ce qui est dessous (meme sombre) ; hors champ, ignore
void poser(float yf, float xf, float r, float v, float b) {
  const int y = (int)yf, x = (int)xf;
  if (yf < 0 || xf < 0 || y >= H || x >= W) return;
  peindre(y, x, r, v, b);
}

// _peindre_sous : tout ce qui est sous la crete (64 hauteurs, une par colonne),
// jusqu'a `haut` (exclu), prend la couleur ; `masque` (4 096 octets), s'il est
// donne, garde ou l'on a peint
void peindre_sous(const float *crete, float r, float v, float b, float haut = 64, uint8_t *masque = nullptr) {
  if (masque) memset(masque, 0, 4096);
  for (int x = 0; x < W; x++)
    for (int y = 0; y < H; y++)
      if (y >= crete[x] && y < haut) {
        peindre(y, x, r, v, b);
        if (masque) masque[y * 64 + x] = 1;
      }
}

// _halo : une lueur exp(-d / rayon) autour de (x, y), seulement la ou elle compte
void halo(float x, float y, float rayon, float r, float v, float b, float force = 1.0f, float aplati = 1.0f) {
  const int e = (int)(rayon * 6) + 1;
  const int x0 = max(0, (int)x - e), x1 = min(W, (int)x + e + 1);
  const int y0 = max(0, (int)y - e), y1 = min(H, (int)y + e + 1);
  const float inv = 1.0f / fmaxf(rayon, 1e-3f);
  for (int yy = y0; yy < y1; yy++)
    for (int xx = x0; xx < x1; xx++) {
      const float dx = xx - x, dy = (yy - y) * aplati;
      ajouter(yy, xx, expf(-sqrtf(dx * dx + dy * dy) * inv) * force, r, v, b);
    }
}

// --- les champs doux (_brume, _fenetre) en n'importe quelle taille (64 ou 128) ---

// un champ doux (0-1, en uint16) de taille x taille qui se raccorde sur ses
// bords ; le flou en croix de _brume, fait en place ligne par ligne (trois
// lignes de reserve) : pas de grand brouillon
void brume_n(uint16_t *sortie, int taille, int flou) {
  for (int i = 0; i < taille * taille; i++) sortie[i] = (uint16_t)(aleatoire() >> 16);
  static float avant[128], ici[128], premiere[128];
  const int m = taille - 1;
  for (int k = 0; k < flou; k++) {
    for (int x = 0; x < taille; x++) { premiere[x] = sortie[x]; avant[x] = sortie[m * taille + x]; }
    for (int y = 0; y < taille; y++) {
      for (int x = 0; x < taille; x++) ici[x] = sortie[y * taille + x];
      const uint16_t *dessous = y == m ? nullptr : sortie + (y + 1) * taille;
      for (int x = 0; x < taille; x++) {
        const float bas = dessous ? dessous[x] : premiere[x];
        const float s = ici[x] + avant[x] + bas + ici[(x + m) & m] + ici[(x + 1) & m];
        sortie[y * taille + x] = (uint16_t)(s / 5.0f);
      }
      for (int x = 0; x < taille; x++) avant[x] = ici[x];
    }
  }
  uint16_t mn = 65535, mx = 0;
  for (int i = 0; i < taille * taille; i++) { mn = min(mn, sortie[i]); mx = max(mx, sortie[i]); }
  const float k = 65535.0f / fmaxf(1.0f, (float)(mx - mn));
  for (int i = 0; i < taille * taille; i++) sortie[i] = (uint16_t)((sortie[i] - mn) * k);
}
inline float champ_n(const uint16_t *c, int taille, int x, int y) {
  const int m = taille - 1;
  return c[(y & m) * taille + (x & m)] * (1.0f / 65535.0f);
}
// la fenetre de _fenetre : le champ vu depuis (ox, oy), pas forcement entiers
inline float fenetre_n(const uint16_t *c, int taille, float ox, float oy, int x, int y) {
  const int x0 = (int)floorf(ox), y0 = (int)floorf(oy);
  const float fx = ox - x0, fy = oy - y0;
  const float a = champ_n(c, taille, x + x0, y + y0), b = champ_n(c, taille, x + x0 + 1, y + y0);
  const float d = champ_n(c, taille, x + x0, y + y0 + 1), e = champ_n(c, taille, x + x0 + 1, y + y0 + 1);
  return (a * (1 - fx) + b * fx) * (1 - fy) + (d * (1 - fx) + e * fx) * fy;
}

// --- l'eau ---------------------------------------------------------------

// _rayons_d_eau : les rayons du soleil a travers la surface, plus faibles en profondeur
inline float rayon_d_eau(int y, int x, float t) {
  const float s = 0.5f + 0.5f * sinf(x * 0.22f + y * 0.09f + t * 0.35f + sinf(x * 0.05f + t * 0.2f) * 2);
  const float s2 = s * s, s4 = s2 * s2;
  return s4 * s4 * borne(1 - y / 60.0f, 0, 1);
}
void rayons_d_eau(float t, float force = 0.35f, float r = 150, float v = 220, float b = 255) {
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) ajouter(y, x, rayon_d_eau(y, x, t) * force, r, v, b);
}

// _caustiques : le reseau de lumiere au fond de l'eau (0-1)
inline float caustique(float x, float y, float t, float echelle = 1.0f) {
  const float a = sinf(x * 0.32f * echelle + sinf(y * 0.21f * echelle + t * 0.9f) * 1.8f + t * 0.4f);
  const float b = sinf(y * 0.3f * echelle + sinf(x * 0.24f * echelle - t * 0.7f) * 1.8f - t * 0.3f);
  const float c = borne(1 - fabsf(a + b) * 0.9f, 0, 1);
  return c * c * c;
}

// _poisson : un petit poisson, un corps, une queue qui bat
void poisson(float x, float y, int sens, float r, float v, float b, int longueur = 4) {
  const int xi = (int)roundf(x), yi = (int)roundf(y);
  for (int k = 0; k < longueur; k++) {
    const float c = k ? 1.0f : 1.15f;
    pointer(yi, xi - sens * k, r * c, v * c, b * c);
  }
  pointer(yi - 1, xi - sens * longueur, r * 0.8f, v * 0.8f, b * 0.8f);   // la queue
  pointer(yi + 1, xi - sens * longueur, r * 0.8f, v * 0.8f, b * 0.8f);
  if (longueur > 3) pointer(yi - 1, xi - sens, r * 0.9f, v * 0.9f, b * 0.9f);   // le dos
}

// _bulles : des bulles qui montent en zigzag et repartent du fond (n <= 24)
struct Bulles { int n; float x[24], y[24], v[24], p[24]; };
void semer_bulles(Bulles &b, int n) {
  b.n = n;
  for (int i = 0; i < n; i++) { b.x[i] = hasard(0, 64); b.y[i] = hasard(0, 64); b.v[i] = hasard(4, 9); b.p[i] = hasard(0, 6); }
}
void bulles(Bulles &b, float t, float dt, float r = 170, float v = 220, float bl = 255) {
  for (int i = 0; i < b.n; i++) {
    b.y[i] -= b.v[i] * dt;
    if (b.y[i] < -2) b.y[i] = 64 + hasard(0, 10);
    const float k = 0.5f + 0.5f * sinf(b.p[i]);
    pointer(b.y[i], b.x[i] + sinf(t * 3 + b.p[i]) * 0.8f, r * k, v * k, bl * k);
  }
}

// _pluie : la pluie en traits obliques (n <= 120)
struct Pluie { int n; float x[120], y[120], v[120]; };
void semer_pluie(Pluie &p, int n) {
  p.n = n;
  for (int i = 0; i < n; i++) { p.x[i] = hasard(0, 64); p.y[i] = hasard(0, 64); p.v[i] = hasard(45, 70); }
}
void pluie(Pluie &p, float dt, float r = 140, float v = 160, float b = 200, float vent = 0.25f) {
  for (int i = 0; i < p.n; i++) {
    p.y[i] += p.v[i] * dt;
    p.x[i] += p.v[i] * vent * dt;
    if (p.y[i] > 64) p.y[i] -= 70;
    p.x[i] = fmodf(fmodf(p.x[i], 64) + 64, 64);
    for (int k = 0; k < 3; k++) {
      const float c = 1 - k * 0.3f;
      pointer(p.y[i] - k, fmodf(p.x[i] - k * vent + 64, 64), r * c, v * c, b * c);
    }
  }
}
