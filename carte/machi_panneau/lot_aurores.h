// lot_aurores.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
//
// LES AURORES. Le moteur des aurores de Machi Tool : _ecran_boreal (les seize
// aurores, chacune son ciel, ses etoiles, son aurore -- des rideaux, des rideaux
// fins, un voile, un ruban, une couronne, une spirale --, sa lune, son paysage et
// son detail) et _tunnel_boreal (les cinq tunnels). `humeur` est l'index dans la
// liste de _presets_boreaux() : 0-15 les aurores (l'ordre d'AURORES_UNIQUES),
// 16-20 les tunnels (celui de TUNNELS_UNIQUES).
//
// Le budget : les sinus, les exponentielles et les arctangentes de chaque pixel
// passent par des polynomes (bor_sint, bor_exp, bor_atan2 : moins de 1e-5 d'ecart
// sur le sinus et l'exponentielle, 2e-4 rad sur l'angle) ; les profils des rideaux,
// par colonne, par recurrence (une exponentielle par colonne, pas par pixel) ; ce
// qui ne bouge pas (les cretes, les sapins, la lave, les grains) se calcule au debut.
#pragma once

// --- les tables de machi_tool.py ---------------------------------------------

struct BorPalette { uint8_t n; uint8_t c[4][3]; };
const BorPalette BOR_COULEURS[10] = {   // AURORE_COULEURS : les couleurs des rideaux, du bas vers le haut
  {3, {{60, 255, 140}, {40, 205, 110}, {110, 255, 180}, {0, 0, 0}}},          // 0 emeraude
  {2, {{60, 255, 140}, {150, 70, 255}, {0, 0, 0}, {0, 0, 0}}},                // 1 emeraude et violet
  {2, {{255, 90, 170}, {190, 80, 255}, {0, 0, 0}, {0, 0, 0}}},                // 2 rose
  {2, {{40, 220, 255}, {60, 255, 190}, {0, 0, 0}, {0, 0, 0}}},                // 3 turquoise
  {2, {{170, 60, 255}, {255, 70, 150}, {0, 0, 0}, {0, 0, 0}}},                // 4 pourpre
  {2, {{60, 255, 140}, {255, 60, 70}, {0, 0, 0}, {0, 0, 0}}},                 // 5 rouge et vert
  {4, {{60, 255, 140}, {40, 190, 255}, {150, 70, 255}, {255, 90, 170}}},      // 6 multicolore
  {2, {{110, 190, 255}, {190, 235, 255}, {0, 0, 0}, {0, 0, 0}}},              // 7 glacier
  {2, {{190, 255, 80}, {60, 255, 140}, {0, 0, 0}, {0, 0, 0}}},                // 8 vert tendre
  {2, {{255, 60, 200}, {40, 220, 255}, {0, 0, 0}, {0, 0, 0}}},                // 9 magenta et cyan
};
enum { BOR_EMERAUDE, BOR_EMERAUDE_VIOLET, BOR_ROSE, BOR_TURQUOISE, BOR_POURPRE, BOR_ROUGE_VERT, BOR_MULTICOLORE,
       BOR_GLACIER, BOR_VERT_TENDRE, BOR_MAGENTA_CYAN };

const uint8_t BOR_CIELS[5][2][3] = {    // AURORE_CIELS : (le haut, l'horizon)
  {{2, 4, 16}, {12, 24, 52}},
  {{0, 1, 6}, {6, 10, 28}},
  {{8, 6, 28}, {52, 30, 70}},
  {{1, 7, 18}, {16, 44, 64}},
  {{6, 2, 18}, {32, 14, 56}},
};

struct BorPaysage { const char *cle, *nom; uint8_t horizon; };
const BorPaysage BOR_PAYSAGES[16] = {   // AURORE_PAYSAGES : (cle, nom, ligne d'horizon)
  {"montagnes", "Montagnes", 44}, {"lac", "Lac", 40}, {"fjord", "Fjord", 42}, {"mer", "Mer", 46},
  {"banquise", "Banquise", 48}, {"plaine", "Plaine", 50}, {"foret", "Foret", 50}, {"cabane", "Cabane", 50},
  {"tente", "Bivouac", 52}, {"phare", "Phare", 47}, {"village", "Village", 50}, {"igloo", "Igloo", 50},
  {"volcan", "Volcan", 48}, {"sommet", "Sommet", 64}, {"foret_lac", "Foret et lac", 42}, {"ciel", "Ciel", 64},
};
enum { BOR_MONTAGNES, BOR_LAC, BOR_FJORD, BOR_MER, BOR_BANQUISE, BOR_PLAINE, BOR_FORET, BOR_CABANE, BOR_TENTE,
       BOR_PHARE, BOR_VILLAGE, BOR_IGLOO, BOR_VOLCAN, BOR_SOMMET, BOR_FORET_LAC, BOR_CIEL };
enum { BOR_RIDEAUX, BOR_RIDEAUX_FINS, BOR_VOILE, BOR_RUBAN, BOR_COURONNE, BOR_SPIRALE };   // AURORE_STYLES (+ la spirale)
enum { BOR_SANS_LUNE, BOR_CROISSANT, BOR_PLEINE };
enum { BOR_SANS_DETAIL, BOR_FILANTES, BOR_NEIGE, BOR_BRUME };
enum { BOR_ROND, BOR_CARRE, BOR_EN_SPIRALE, BOR_ANNEAUX, BOR_VER };                          // TUNNEL_FORMES

struct BorUnique { uint8_t paysage, couleurs, style, ciel, lune, detail; float vitesse; };
const int BOR_NB_AURORES = 16, BOR_NB_TUNNELS = 5;
const BorUnique BOR_AURORES_UNIQUES[BOR_NB_AURORES] = {   // AURORES_UNIQUES : (paysage, couleurs, style, ciel, lune, detail, vitesse)
  {BOR_MONTAGNES, BOR_EMERAUDE, BOR_RIDEAUX, 0, BOR_CROISSANT, BOR_FILANTES, 1.0f},
  {BOR_LAC, BOR_EMERAUDE_VIOLET, BOR_RIDEAUX, 1, BOR_SANS_LUNE, BOR_SANS_DETAIL, 0.9f},
  {BOR_FJORD, BOR_TURQUOISE, BOR_RUBAN, 3, BOR_SANS_LUNE, BOR_BRUME, 1.0f},
  {BOR_MER, BOR_MULTICOLORE, BOR_VOILE, 2, BOR_PLEINE, BOR_SANS_DETAIL, 1.1f},
  {BOR_BANQUISE, BOR_GLACIER, BOR_RIDEAUX_FINS, 1, BOR_SANS_LUNE, BOR_NEIGE, 0.9f},
  {BOR_PLAINE, BOR_ROUGE_VERT, BOR_COURONNE, 0, BOR_SANS_LUNE, BOR_FILANTES, 1.0f},
  {BOR_FORET, BOR_VERT_TENDRE, BOR_RIDEAUX_FINS, 3, BOR_CROISSANT, BOR_SANS_DETAIL, 1.25f},
  {BOR_CABANE, BOR_ROSE, BOR_RUBAN, 4, BOR_SANS_LUNE, BOR_NEIGE, 0.8f},
  {BOR_TENTE, BOR_POURPRE, BOR_RIDEAUX, 2, BOR_CROISSANT, BOR_FILANTES, 1.0f},
  {BOR_PHARE, BOR_MAGENTA_CYAN, BOR_VOILE, 4, BOR_SANS_LUNE, BOR_BRUME, 1.1f},
  {BOR_VILLAGE, BOR_EMERAUDE, BOR_RUBAN, 0, BOR_PLEINE, BOR_NEIGE, 0.9f},
  {BOR_IGLOO, BOR_EMERAUDE_VIOLET, BOR_RIDEAUX_FINS, 1, BOR_SANS_LUNE, BOR_FILANTES, 1.0f},
  {BOR_VOLCAN, BOR_ROSE, BOR_RIDEAUX, 2, BOR_SANS_LUNE, BOR_BRUME, 1.0f},
  {BOR_SOMMET, BOR_MULTICOLORE, BOR_SPIRALE, 1, BOR_SANS_LUNE, BOR_SANS_DETAIL, 0.8f},
  {BOR_FORET_LAC, BOR_TURQUOISE, BOR_RIDEAUX, 3, BOR_PLEINE, BOR_SANS_DETAIL, 1.0f},
  {BOR_CIEL, BOR_MAGENTA_CYAN, BOR_COURONNE, 2, BOR_SANS_LUNE, BOR_FILANTES, 1.1f},
};
const uint8_t BOR_TUNNELS_UNIQUES[BOR_NB_TUNNELS][2] = {   // TUNNELS_UNIQUES : (forme, couleurs)
  {BOR_ROND, BOR_EMERAUDE_VIOLET}, {BOR_CARRE, BOR_MAGENTA_CYAN}, {BOR_EN_SPIRALE, BOR_MULTICOLORE},
  {BOR_ANNEAUX, BOR_TURQUOISE}, {BOR_VER, BOR_ROSE},
};

// _presets_boreaux() : les reglages de la preset `humeur` (les aurores, puis les tunnels)
struct BorReglages {
  bool tunnel;
  uint8_t paysage, horizon, palette, style, ciel, lune, detail;   // les aurores
  uint8_t forme;                                                  // les tunnels
  float sens, vitesse;
  int variante;
};
BorReglages bor_reglages(int humeur) {
  BorReglages r = {};
  humeur = max(0, min(humeur, BOR_NB_AURORES + BOR_NB_TUNNELS - 1));
  if (humeur < BOR_NB_AURORES) {
    const BorUnique &u = BOR_AURORES_UNIQUES[humeur];
    r.paysage = u.paysage;
    r.horizon = BOR_PAYSAGES[u.paysage].horizon;
    r.palette = u.couleurs;
    r.style = u.style;
    r.ciel = u.ciel;
    r.lune = u.lune;
    r.detail = u.detail;
    r.vitesse = u.vitesse;
    r.variante = humeur;
  } else {
    const int j = humeur - BOR_NB_AURORES;
    r.tunnel = true;
    r.forme = BOR_TUNNELS_UNIQUES[j][0];
    r.palette = BOR_TUNNELS_UNIQUES[j][1];
    r.sens = 1;
    r.vitesse = 1.0f;
    r.variante = j;
  }
  return r;
}

// --- les outils du lot ---------------------------------------------------------

const float BOR_PI = 3.14159265f, BOR_TOUR = 0.15915494f;   // pi, 1 / (2 pi)

// sin(2 pi q), q en tours (|q| < 4e6) : un polynome (ecart < 4e-6), pas de sinf
inline float bor_sint(float q) {
  const float u = q + 0.5f;
  int k = (int)u;                                          // floor(q + 1/2), sans floorf
  if (u < k) k--;
  q -= k;                                                  // [-1/2, 1/2[
  const float a = fabsf(q), b = fminf(a, 0.5f - a);        // sin(2 pi a) = sin(2 pi (1/2 - a))
  const float z = copysignf(b, q) * PI2, z2 = z * z;
  return z * (1 + z2 * (-0.16666667f + z2 * (8.3333333e-3f + z2 * (-1.9841270e-4f + z2 * 2.7557319e-6f))));
}
inline float bor_sin(float x) { return bor_sint(x * BOR_TOUR); }

// exp(x) : 2^n par les bits, e^f par un polynome (ecart relatif < 3e-6)
inline float bor_exp(float x) {
  if (x < -87.0f) return 0.0f;
  if (x > 88.0f) x = 88.0f;
  const float k = x * 1.44269504f;
  const int n = (int)(k + (k >= 0 ? 0.5f : -0.5f));
  const float f = (k - n) * 0.69314718f;
  const float p = 1 + f * (1 + f * (0.5f + f * (0.16666667f + f * (0.041666667f + f * 0.0083333333f))));
  const int32_t bits = (int32_t)(n + 127) << 23;
  float s;
  memcpy(&s, &bits, sizeof s);
  return p * s;
}

// atan2(y, x) en radians, dans ]-pi, pi] comme numpy (ecart < 2e-4 rad)
inline float bor_atan2(float y, float x) {
  const float ax = fabsf(x), ay = fabsf(y);
  const float mx = fmaxf(ax, ay), mn = fminf(ax, ay);
  const float a = mx > 0 ? mn / mx : 0.0f, s = a * a;
  float r = ((-0.0464964749f * s + 0.15931422f) * s - 0.327622764f) * s * a + a;
  if (ay > ax) r = 1.57079633f - r;
  if (x < 0) r = BOR_PI - r;
  return y < 0 ? -r : r;
}

// x ** 1.3 pour x entre 0 et 1 : une table de 257 valeurs, lue en lineaire
void bor_table13(float *table) {
  for (int i = 0; i <= 256; i++) table[i] = powf(i / 256.0f, 1.3f);
  table[257] = 1.0f;
}
inline float bor_p13(const float *table, float x) {
  const float u = borne(x, 0, 1) * 256.0f;
  const int i = (int)u;
  return table[i] + (table[i + 1] - table[i]) * (u - i);
}

// col[y] += k * exp(-((y - c) / s)^2) pour y dans [y0, y1), la ou ca compte (|y - c| <= 4 s) :
// une recurrence (le rapport de deux lignes voisines change d'un facteur constant)
void bor_gauss(float *col, float c, float s, float k, int y0, int y1) {
  const int a = max(y0, (int)ceilf(c - 4 * s)), b = min(y1, (int)floorf(c + 4 * s) + 1);
  if (a >= b) return;
  const float is = 1.0f / s, u = (a - c) * is;
  float g = k * expf(-u * u), r = expf(-(2 * u + is) * is);
  const float q = expf(-2 * is * is);
  for (int y = a; y < b; y++) {
    col[y] += g;
    g *= r;
    r *= q;
  }
}

// la silhouette de _faites : de la crete (par colonne) jusqu'a `bas` (exclu)
void bor_faites(const float *crete, int bas, float r, float v, float b) {
  for (int x = 0; x < W; x++)
    for (int y = max(0, (int)ceilf(crete[x])); y < bas && y < H; y++) peindre(y, x, r, v, b);
}

// la crete de cretes() dans _paysage_boreal
void bor_cretes(float *crete, float h0, float amp, float f, bool pointu = true, float graine = 0.0f) {
  for (int x = 0; x < W; x++) {
    const float s = sinf(x * f + 1.3f + graine);
    crete[x] = h0 - amp * (pointu ? fabsf(s) : 0.5f + 0.5f * s) - amp * 0.35f * sinf(x * f * 2.7f + graine);
  }
}

// --- les aurores (_ecran_boreal) -----------------------------------------------

const int BOR_BRUME_L = 35;               // les lignes de la brume que sa fenetre lit (le reste ne se voit pas)
const int BOR_RT = 258;                   // la table de la couronne : r de 0 a 64, par quarts de pixel

struct E_boreal {
  uint16_t voile[2][128 * 128];           // les deux champs du voile (_voile_boreal), 128 x 128
  uint16_t brume[BOR_BRUME_L * 128];      // la bande de la brume (_detail_boreal), ses lignes utiles
  int brume_y;                            // la ligne de l'ecran de sa premiere ligne
  float brume_g[BOR_BRUME_L];             // sa gaussienne, par ligne (x 0.6)
  float fond[64][3];                      // le ciel, par ligne
  float sx[64], cx[64];                   // sin, cos(0.5 x) : le frisson des reflets, les vagues
  float sn[64], cn[64], sl[64], cl[64];   // sin, cos(1.3 x), sin, cos(2.1 y) : le grain de la neige
  float crete[2][64];                     // les silhouettes (montagnes, rives, sapins, colline, cone, pic)
  float blocs[4][64], bloc_x[4];          // la banquise : les cretes des blocs de glace
  int maisons;                            // le village
  uint8_t mx[12], ml[12], mh[12];
  float mp[12];
  float fumee[8];                         // la cabane : les phases de la fumee
  float lave[27][21], coulee[27][21];     // le volcan : la lave et sa coulee (sans le temps)
  float fil[4][6];                        // les etoiles filantes (x, y, vx, vy, age, vie)
  int nfil;
  float suivante;
  float trainee[10];                      // (1 - k / 10) ** 1.6
  float fx[45], fy[45], fv[45], fp[45];   // les flocons
  float p13[258];                         // x ** 1.3
  float rt[BOR_RT][4];                    // la couronne, selon r : cos, sin (du pli ou de la spirale), le fond, le coeur
};

void bor_semer(E_boreal &e, const BorReglages &p) {
  const int hz = p.horizon;
  // le ciel : du haut vers l'horizon
  const float h = fmaxf(20.0f, fminf((float)hz, 60.0f));
  for (int y = 0; y < H; y++) {
    const float k = borne(y / h, 0, 1);
    for (int c = 0; c < 3; c++) e.fond[y][c] = BOR_CIELS[p.ciel][0][c] * (1 - k) + BOR_CIELS[p.ciel][1][c] * k;
  }
  semer_ciel(p.style == BOR_COURONNE ? 70 : 50, max(8, min(hz - 4, 64)));
  for (int i = 0; i < 64; i++) {
    e.sx[i] = sinf(i * 0.5f); e.cx[i] = cosf(i * 0.5f);
    e.sn[i] = sinf(i * 1.3f); e.cn[i] = cosf(i * 1.3f);
    e.sl[i] = sinf(i * 2.1f); e.cl[i] = cosf(i * 2.1f);
  }
  bor_table13(e.p13);
  for (int i = 0; i < BOR_RT; i++) {   // le fond exp(-r / 26) de la couronne, et son coeur 0.3 exp(-r / 5)
    e.rt[i][2] = expf(-i * 0.25f / 26.0f);
    e.rt[i][3] = 0.3f * expf(-i * 0.25f / 5.0f);
  }
  for (int k = 0; k < 10; k++) e.trainee[k] = powf(1 - k / 10.0f, 1.6f);
  // la brume d'abord : elle emprunte la place du voile le temps de naitre (128 x 128), puis n'en garde que sa bande
  if (p.detail == BOR_BRUME) {
    brume_n(e.voile[0], 128, 10);
    const int c = min((int)hz, 60) - 2;
    e.brume_y = c - BOR_BRUME_L / 2;
    for (int j = 0; j < BOR_BRUME_L; j++) {
      const int y = e.brume_y + j;
      memcpy(e.brume + j * 128, e.voile[0] + ((y + 30) & 127) * 128, 128 * sizeof(uint16_t));
      const float u = (y - c) / 5.0f;
      e.brume_g[j] = expf(-u * u) * 0.6f;
    }
  }
  if (p.style == BOR_VOILE) {
    brume_n(e.voile[0], 128, 12);
    brume_n(e.voile[1], 128, 24);
  }
  switch (p.paysage) {
    case BOR_MONTAGNES:
      bor_cretes(e.crete[0], hz, 14, 0.09f);
      bor_cretes(e.crete[1], hz + 6, 8, 0.15f, true, 2.0f);
      break;
    case BOR_LAC:
      bor_cretes(e.crete[0], hz, 10, 0.12f);
      break;
    case BOR_FJORD:
      for (int x = 0; x < W; x++) {
        const float g = borne(1 - x / 20.0f, 0, 1), d = borne((x - 44) / 20.0f, 0, 1);
        e.crete[0][x] = fminf(hz - 2 - 26 * powf(g, 1.3f), hz - 2 - 30 * powf(d, 1.3f)) + 1.5f * sinf(x * 0.7f);
      }
      break;
    case BOR_BANQUISE:
      for (int i = 0; i < 4; i++) {
        const float bx = hasard(4, 60), hb = hasard(4, 9), pente = hasard(0.9f, 1.8f);
        e.bloc_x[i] = bx;
        for (int x = 0; x < W; x++) e.blocs[i][x] = hz - hb + fabsf(x - bx) * pente + 0.8f * fabsf(sinf(x * 1.7f + bx));
      }
      break;
    case BOR_PLAINE:
      bor_cretes(e.crete[0], hz - 1, 3, 0.07f, false);
      break;
    case BOR_FORET:
    case BOR_FORET_LAC: {
      // les sapins : chacun un triangle jusqu'a base + 1 ; leur union est une crete par colonne
      const int n = p.paysage == BOR_FORET ? 18 : 16;
      const float hmin = p.paysage == BOR_FORET ? 8 : 6, hmax = p.paysage == BOR_FORET ? 22 : 16;
      for (int x = 0; x < W; x++) e.crete[0][x] = 1e9f;
      for (int i = 0; i < n; i++) {
        const float sx = hasard(0, 64), hs = hasard(hmin, hmax), w = hasard(0.32f, 0.45f);
        const float sommet = hz - hs;
        for (int x = 0; x < W; x++)
          e.crete[0][x] = fminf(e.crete[0][x], sommet + fmaxf(0.0f, (fabsf(x - sx) - 0.5f) / w));
      }
      break;
    }
    case BOR_CABANE:
      for (int x = 0; x < W; x++) {
        const float u = (x - 40) / 16.0f;
        e.crete[0][x] = hz + 3 - 5 * expf(-u * u);
      }
      for (int k = 0; k < 8; k++) e.fumee[k] = hasard(0, 6);
      break;
    case BOR_VILLAGE: {
      float x0 = 2.0f;
      e.maisons = 0;
      while (x0 < 60 && e.maisons < 12) {
        const int larg = 6 + (int)(aleatoire() % 4);
        e.mx[e.maisons] = (uint8_t)x0;
        e.ml[e.maisons] = (uint8_t)larg;
        e.mh[e.maisons] = (uint8_t)(4 + aleatoire() % 4);
        e.mp[e.maisons] = hasard(0, 6);
        e.maisons++;
        x0 += larg + hasard(1, 5);
      }
      break;
    }
    case BOR_VOLCAN:
      for (int x = 0; x < W; x++) e.crete[0][x] = hz - borne(24 - fabsf(x - 32.0f) * 1.2f, 0, 22);
      for (int j = 0; j < 27; j++) {
        const int y = hz - 23 + j;
        for (int i = 0; i < 21; i++) {
          const int x = 22 + i;
          const float c = x - 32 - sinf(y * 0.4f) * 2;
          e.lave[j][i] = expf(-((x - 32.0f) * (x - 32.0f)) / 6.0f - ((y - (hz - 21.0f)) * (y - (hz - 21.0f))) / 4.0f);
          e.coulee[j][i] = (y > hz - 20 && y < hz + 4) ? expf(-(c * c) / 1.5f) * 0.5f : 0.0f;
        }
      }
      break;
    case BOR_SOMMET:
      for (int x = 0; x < W; x++) e.crete[0][x] = 64 - borne(30 - fabsf(x - 14.0f) * 1.6f, 0, 30);
      break;
    default:
      break;
  }
  if (p.detail == BOR_FILANTES) {
    e.nfil = 0;
    e.suivante = 1.0f;
  } else if (p.detail == BOR_NEIGE) {
    for (int i = 0; i < 45; i++) e.fx[i] = hasard(0, 64);
    for (int i = 0; i < 45; i++) e.fy[i] = hasard(0, 64);
    for (int i = 0; i < 45; i++) e.fv[i] = hasard(4, 10);
    for (int i = 0; i < 45; i++) e.fp[i] = hasard(0, 6);
  }
}

// la lune (pleine ou en croissant) et son halo, sur le ciel
void bor_lune(const BorReglages &p) {
  const float lx = p.variante % 2 ? 50.0f : 13.0f, ly = p.variante % 2 ? 9.0f : 10.0f;
  for (int y = max(0, (int)ly - 10); y <= (int)ly + 10 && y < H; y++)
    for (int x = max(0, (int)lx - 10); x <= (int)lx + 10 && x < W; x++) {
      const float dx = x - lx, dy = y - ly, d = sqrtf(dx * dx + dy * dy);
      const float h = borne(1 - (d - 3) / 7, 0, 1);
      if (h > 0) ajouter(y, x, h, 26, 26, 22);
      if (d <= 3.2f) {
        const float ex = dx - 1.6f, ey = dy + 0.8f;
        if (p.lune != BOR_CROISSANT || sqrtf(ex * ex + ey * ey) > 2.9f) peindre(y, x, 225, 225, 200);
      }
    }
}

// _rideaux_boreaux : ajoute 0.85 x la lumiere au-dessus de l'horizon ; `somme` recoit la lumiere des lignes [h0, hz)
void bor_rideaux(const BorPalette &pal, float t, float base_y, int hz, bool fins, bool ruban, float v, int h0,
                 float *somme) {
  const int n = pal.n;
  const float pente = ruban ? 5.0f : fins ? 6.0f : 9.0f, bord = ruban ? 1.6f : 2.2f;
  const float q = expf(-1.0f / pente);
  float col[64];
  for (int i = 0; i < n; i++) {
    const float decal = 1.7f * i + 0.4f;
    const float haut = ruban ? -3.0f * i : -7.0f * i;
    const float poids = ruban ? 0.95f - 0.12f * i : (n == 1 ? 1.0f : 0.95f - 0.1f * i);
    const float cr = pal.c[i][0], cv = pal.c[i][1], cb = pal.c[i][2];
    float s = 0;
    for (int x = 0; x < W; x++) {
      float base, rideau;
      if (ruban) {
        base = base_y + haut + 9 * bor_sin(x * 0.06f + t * 0.35f * v + decal) + 4 * bor_sin(x * 0.17f - t * 0.6f * v);
        rideau = 0.65f + 0.35f * bor_sin(x * 0.25f + t * 0.9f * v + decal);
      } else {
        const float amp = fins ? 4.0f : 6.0f, w = fins ? 0.13f : 0.08f;
        base = base_y + haut + amp * bor_sin(x * w + t * 0.5f * v + decal) + 3 * bor_sin(x * 0.23f - t * 0.7f * v + decal);
        const float plis = x * (fins ? 1.1f : 0.5f) + t * (fins ? 2.2f : 1.5f) * v + bor_sin(x * 0.1f + t * 0.8f * v + decal) * 3;
        rideau = 0.5f + 0.5f * bor_sin(plis);
        if (fins) rideau = rideau * rideau * (0.7f + 0.3f * bor_sin(x * 2.3f + t * 4 * v + decal));
      }
      // le profil : au-dessus de la base exp(-(base - y) / pente), en dessous la gaussienne du bord
      for (int y = 0; y < hz; y++) col[y] = 0;
      const int yb = (int)floorf(base);
      const int y0 = min(yb, hz - 1);
      if (y0 >= 0) {
        float g = expf(-(base - y0) / pente);
        for (int y = y0; y >= 0; y--) {
          col[y] = g;
          g *= q;
        }
      }
      bor_gauss(col, base, bord, 1.0f, yb + 1, hz);
      if (ruban) bor_gauss(col, base, 0.9f, 0.6f, 0, hz);   // la crete vive du ruban
      const float k = rideau * poids, k85 = k * 0.85f;
      for (int y = 0; y < hz; y++) ajouter(y, x, col[y] * k85, cr, cv, cb);
      float sc = 0;
      for (int y = h0; y < hz; y++) sc += col[y];
      s += sc * k;
    }
    somme[0] += s * cr;
    somme[1] += s * cv;
    somme[2] += s * cb;
  }
}

// _voile_boreal : un champ doux qui derive, en bande au-dessus de l'horizon
void bor_voile(const E_boreal &e, const BorPalette &pal, float t, float base_y, int hz, float v, int h0, float *somme) {
  const uint8_t *bas = pal.c[0], *haut = pal.c[pal.n - 1];
  float stries[64];
  for (int x = 0; x < W; x++) stries[x] = 0.7f + 0.3f * bor_sin(x * 1.3f + bor_sin(x * 0.21f + t * 0.6f * v) * 3 + t * 1.1f * v);
  // les deux fenetres : (ox, oy) = (2.2 t v, 6 + 0.3 t) et (40 - 1.4 t v, 20)
  const float oxa = t * 2.2f * v, oya = 6 + t * 0.3f, oxb = 40 - t * 1.4f * v, oyb = 20;
  const int xa = (int)floorf(oxa), ya = (int)floorf(oya), xb = (int)floorf(oxb), yb = (int)floorf(oyb);
  const float fxa = oxa - xa, fya = oya - ya, fxb = oxb - xb, fyb = oyb - yb;
  const float norme = 1.0f / 65535.0f;
  for (int y = 0; y < hz; y++) {
    const float u = (y - base_y + 6) / 11.0f, bande = expf(-u * u);
    const float k = borne((base_y - y) / 22.0f, 0, 1);
    const float g = bande * 1.3f;
    const float cr = (bas[0] * (1 - k) + haut[0] * k) * g, cv = (bas[1] * (1 - k) + haut[1] * k) * g,
                cb = (bas[2] * (1 - k) + haut[2] * k) * g;
    const uint16_t *a0 = e.voile[0] + ((y + ya) & 127) * 128, *a1 = e.voile[0] + ((y + ya + 1) & 127) * 128;
    const uint16_t *b0 = e.voile[1] + ((y + yb) & 127) * 128, *b1 = e.voile[1] + ((y + yb + 1) & 127) * 128;
    float s = 0;
    for (int x = 0; x < W; x++) {
      const int i = (x + xa) & 127, i1 = (x + xa + 1) & 127, j = (x + xb) & 127, j1 = (x + xb + 1) & 127;
      const float a = ((a0[i] * (1 - fxa) + a0[i1] * fxa) * (1 - fya) + (a1[i] * (1 - fxa) + a1[i1] * fxa) * fya) * norme;
      const float b = ((b0[j] * (1 - fxb) + b0[j1] * fxb) * (1 - fyb) + (b1[j] * (1 - fxb) + b1[j1] * fxb) * fyb) * norme;
      const float nappe = a * a * 0.7f + b * sqrtf(b) * 0.5f;
      const float l = nappe * stries[x];
      ajouter(y, x, l * 0.85f, cr, cv, cb);
      s += l;
    }
    if (y >= h0) {
      somme[0] += s * cr;
      somme[1] += s * cv;
      somme[2] += s * cb;
    }
  }
}

// _couronne_boreale : l'aurore juste au-dessus de soi, ses rayons qui partent d'un point ; ou une spirale.
// Les sinus de l'angle (sin(11 a + p), sin(7 a + p), sin(3 a + p)) viennent des puissances de la direction
// e^(i a) = (dx, dy) / |d| : pas d'arctangente, pas de sinus par pixel ; ce qui ne depend que de r (le pli
// des rayons, la phase de la spirale, le fond, le coeur) se lit dans une table par quart de pixel.
inline void bor_mul(float ar, float ai, float br, float bi, float &cr, float &ci) {
  cr = ar * br - ai * bi;
  ci = ar * bi + ai * br;
}
void bor_couronne(E_boreal &e, const BorPalette &pal, float t, bool spirale, float v, float cy, int hz, int h0,
                  float *somme) {
  const uint8_t *in = pal.c[0], *ex = pal.c[pal.n - 1];
  const float cx = 32 + 4 * sinf(t * 0.2f);
  const float force = (0.85f + 0.15f * sinf(t * 0.7f)) * (spirale ? 1.25f : 1.7f);
  for (int i = 0; i < BOR_RT; i++) {   // le pli des rayons (a + 0.25 sin(0.07 r + ...)) ou la phase de la spirale
    const float r = i * 0.25f;
    const float ph = spirale ? r * 0.28f - t * 0.9f * v : 0.25f * bor_sin(r * 0.07f + t * 0.35f * v);
    e.rt[i][0] = bor_sint(ph * BOR_TOUR + 0.25f);
    e.rt[i][1] = bor_sint(ph * BOR_TOUR);
  }
  const float p11 = t * 0.4f * v, p7 = -t * 0.3f * v + 1.3f, p3 = t * 0.5f * v;
  const float c11 = cosf(p11), s11 = sinf(p11), c7 = cosf(p7), s7 = sinf(p7), c3 = cosf(p3), s3 = sinf(p3);
  for (int y = 0; y < hz; y++) {
    const float dy = y - cy, dy2 = dy * dy;
    float sr = 0, sv = 0, sb = 0;
    for (int x = 0; x < W; x++) {
      const float dx = x - cx;
      const float rho = sqrtf(dx * dx + dy2), inv = 1.0f / fmaxf(rho, 1e-6f);
      const float ca = dx * inv, sa = dy * inv;   // e^(i a)
      const float r = rho + 0.5f, u = r * 4;
      const int i = min((int)u, BOR_RT - 2);
      const float f = u - i, *A = e.rt[i], *B = e.rt[i + 1];
      const float pc = A[0] + (B[0] - A[0]) * f, ps = A[1] + (B[1] - A[1]) * f;
      float motif;
      if (spirale) {
        float z2r, z2i, z3r, z3i;
        bor_mul(ca, sa, ca, sa, z2r, z2i);
        bor_mul(z2r, z2i, ca, sa, z3r, z3i);
        const float m = 0.5f + 0.5f * (z3r * ps + z3i * pc);   // sin(3 a + 0.28 r - 0.9 t v)
        motif = m * m * m;
      } else {
        float zr, zi, z2r, z2i, z3r, z3i, z4r, z4i, z7r, z7i, z8r, z8i, z11r, z11i;
        bor_mul(ca, sa, pc, ps, zr, zi);   // les rayons se plient, comme des rideaux vus d'en dessous
        bor_mul(zr, zi, zr, zi, z2r, z2i);
        bor_mul(z2r, z2i, zr, zi, z3r, z3i);
        bor_mul(z2r, z2i, z2r, z2i, z4r, z4i);
        bor_mul(z4r, z4i, z3r, z3i, z7r, z7i);
        bor_mul(z4r, z4i, z4r, z4i, z8r, z8i);
        bor_mul(z8r, z8i, z3r, z3i, z11r, z11i);
        const float rayons = (0.5f + 0.5f * (z11r * s11 + z11i * c11)) * (0.5f + 0.5f * (z7r * s7 + z7i * c7));
        motif = bor_p13(e.p13, rayons) * (0.7f + 0.3f * (z3r * s3 + z3i * c3));
      }
      const float fond = r > 2.5f ? A[2] + (B[2] - A[2]) * f : 0.0f;
      const float k = fminf(r * (1.0f / 34.0f), 1.0f);
      const float lum = motif * fond * force, coeur = A[3] + (B[3] - A[3]) * f;
      const float lr = lum * (in[0] + (ex[0] - in[0]) * k) + coeur * in[0];
      const float lv = lum * (in[1] + (ex[1] - in[1]) * k) + coeur * in[1];
      const float lb = lum * (in[2] + (ex[2] - in[2]) * k) + coeur * in[2];
      ajouter(y, x, 0.85f, lr, lv, lb);
      sr += lr; sv += lv; sb += lb;
    }
    if (y >= h0) {
      somme[0] += sr;
      somme[1] += sv;
      somme[2] += sb;
    }
  }
}

// --- le paysage (_paysage_boreal) ---

// neige() : le sol enneige, eclaire par l'aurore, et son grain
void bor_neige(const E_boreal &e, int depuis, float force, const float *refl) {
  const float h = fmaxf(1.0f, 64.0f - depuis);
  for (int y = max(depuis, 0); y < H; y++) {
    const float k = borne((y - depuis) / h, 0, 1), f = force * (1 - 0.5f * k);
    const float r = 18 + refl[0] * f, v = 24 + refl[1] * f, b = 38 + refl[2] * f;
    for (int x = 0; x < W; x++) {
      const float g = 0.9f + 0.1f * (e.sn[x] * e.cl[y] + e.cn[x] * e.sl[y]);   // sin(1.3 x + 2.1 y)
      peindre(y, x, r * g, v * g, b * g);
    }
  }
}

// reflet() : le ciel a l'envers sous l'horizon, decale ligne par ligne, qui frissonne
void bor_reflet(const E_boreal &e, int hz, float t, float force, float frisson) {
  for (int y = hz; y < H; y++) {
    const int src = max(0, 2 * hz - 1 - y);
    const int d = (int)rintf(sinf(y * 0.9f + t * 2.0f) * (0.4f + (y - hz) * 0.06f) * frisson);
    const float ph = y * 1.3f + t * 3, sp = sinf(ph), cp = cosf(ph);
    for (int x = 0; x < W; x++) {
      const float m = force * (0.85f + 0.15f * (e.sx[x] * cp + e.cx[x] * sp));   // sin(0.5 x + ph)
      const float *s = scene[src][(x - d) & 63];
      peindre(y, x, s[0] * m, s[1] * m, s[2] * m);
    }
  }
}

// un rectangle [y0, y1) x [x0, x1), borne au panneau
void bor_rect(int y0, int y1, int x0, int x1, float r, float v, float b) {
  for (int y = max(0, y0); y < min(H, y1); y++)
    for (int x = max(0, x0); x < min(W, x1); x++) peindre(y, x, r, v, b);
}

void bor_paysage(const E_boreal &e, const BorReglages &p, float t, const float *refl) {
  const int hz = p.horizon;
  switch (p.paysage) {
    case BOR_MONTAGNES:
      bor_faites(e.crete[0], 64, 6, 8, 16);
      bor_faites(e.crete[1], 64, 4, 6, 12);
      break;
    case BOR_LAC:
      bor_faites(e.crete[0], hz, 4, 6, 12);
      bor_reflet(e, hz, t, 0.45f, 1.0f);
      break;
    case BOR_FJORD:
      bor_faites(e.crete[0], hz, 4, 6, 12);
      bor_reflet(e, hz, t, 0.5f, 1.0f);
      break;
    case BOR_MER: {
      bor_reflet(e, hz, t, 0.4f, 1.6f);
      for (int y = hz; y < H; y++) {   // les vagues : 0.5 + 0.5 sin(0.5 x + 2.2 y - 1.5 t)
        const float ph = y * 2.2f - t * 1.5f, sp = sinf(ph), cp = cosf(ph);
        for (int x = 0; x < W; x++) ajouter(y, x, 0.5f + 0.5f * (e.sx[x] * cp + e.cx[x] * sp), 8, 14, 24);
      }
      break;
    }
    case BOR_BANQUISE:
      bor_neige(e, hz, 0.45f, refl);
      for (int i = 0; i < 4; i++) {
        const float r = 80 + refl[0] * 0.35f, v = 120 + refl[1] * 0.35f, b = 160 + refl[2] * 0.35f;
        for (int x = 0; x < W; x++) {
          const float cote = x < e.bloc_x[i] ? 1.0f : 0.6f;   // le cote qui regarde l'aurore, plus clair
          for (int y = max(0, (int)ceilf(e.blocs[i][x])); y <= hz && y < H; y++) peindre(y, x, r * cote, v * cote, b * cote);
        }
      }
      break;
    case BOR_PLAINE:
      bor_neige(e, hz, 0.35f, refl);
      bor_faites(e.crete[0], hz + 1, 10, 14, 26);
      break;
    case BOR_FORET:
      bor_neige(e, hz, 0.35f, refl);
      bor_faites(e.crete[0], hz + 2, 2, 6, 6);
      break;
    case BOR_FORET_LAC:
      bor_faites(e.crete[0], hz + 2, 2, 6, 6);
      bor_reflet(e, hz, t, 0.4f, 1.0f);
      break;
    case BOR_CABANE: {
      bor_neige(e, hz, 0.35f, refl);
      bor_faites(e.crete[0], hz + 2, 22 + refl[0] * 0.3f, 28 + refl[1] * 0.3f, 44 + refl[2] * 0.3f);
      bor_rect(hz - 6, hz - 1, 34, 43, 6, 8, 12);
      for (int i = 0; i < 4; i++) bor_rect(hz - 7 - i, hz - 6 - i, 33 + i, 44 - i, 6, 8, 12);
      const float f = 0.85f + 0.15f * sinf(t * 3.1f);
      bor_rect(hz - 4, hz - 2, 36, 38, 255 * f, 185 * f, 90 * f);
      bor_rect(hz - 4, hz - 2, 40, 42, 255 * f, 185 * f, 90 * f);
      for (int k = 0; k < 8; k++) {   // la fumee de la cheminee
        const float age = fmodf(t * 0.5f + e.fumee[k], 6.0f), c = 1 - age / 6;
        pointer(hz - 12 - age * 3, 41 + sinf(age * 1.3f + k) * 1.5f + age * 0.8f, 60 * c, 60 * c, 70 * c);
      }
      bor_rect(hz - 12, hz - 8, 40, 42, 6, 8, 12);
      break;
    }
    case BOR_TENTE: {
      bor_neige(e, hz, 0.35f, refl);
      const float f = 0.35f + 0.05f * sinf(t * 2.5f);
      for (int i = 0; i < 7; i++) {
        const float k = f * (0.6f + i * 0.07f);
        bor_rect(hz - 7 + i, hz - 6 + i, 30 - i, 32 + i, 255 * k, 160 * k, 70 * k);
      }
      bor_rect(hz - 3, hz, 30, 32, 40, 22, 12);
      break;
    }
    case BOR_PHARE: {
      bor_reflet(e, hz, t, 0.4f, 1.4f);
      for (int x = 0; x < 26; x++)   // le rocher
        for (int y = max(0, (int)ceilf(hz - 4 + 3 * fabsf((x - 12) / 12.0f))); y < H; y++) peindre(y, x, 4, 6, 12);
      bor_rect(hz - 22, hz - 4, 10, 14, 14, 14, 22);
      bor_rect(hz - 22, hz - 19, 9, 15, 20, 20, 30);
      const float lampe = 0.6f + 0.4f * cosf(t * 1.4f), l = 0.5f + 0.5f * lampe;
      bor_rect(hz - 21, hz - 19, 11, 13, 255 * l, 235 * l, 160 * l);
      const float ca = cosf(t * 1.4f);   // le faisceau qui tourne
      if (ca > 0) {
        const float pente = sinf(t * 1.4f) * 0.35f;
        float col[64];
        for (int x = 14; x < W; x++) {
          const float fx = x - 12.0f, c = hz - 20 + fx * pente, s = 1.2f + fx * 0.06f;
          const int y0 = max(0, (int)ceilf(c - 4 * s)), y1 = min(H, (int)floorf(c + 4 * s) + 1);
          if (y0 >= y1) continue;
          for (int y = y0; y < y1; y++) col[y] = 0;
          bor_gauss(col, c, s, ca * expf(-fx / 40.0f), y0, y1);
          for (int y = y0; y < y1; y++) ajouter(y, x, col[y], 90, 85, 60);
        }
      }
      break;
    }
    case BOR_VILLAGE:
      bor_neige(e, hz, 0.35f, refl);
      for (int i = 0; i < e.maisons; i++) {
        const int mx = e.mx[i], larg = e.ml[i], h = e.mh[i];
        bor_rect(hz - h, hz + 1, mx, mx + larg, 8, 9, 16);
        for (int k = 0; k <= larg / 2; k++) bor_rect(hz - h - 1 - k, hz - h - k, mx + k, mx + larg - k, 8, 9, 16);
        if (sinf(t * 0.13f + e.mp[i]) > -0.6f)
          bor_rect(hz - h + 2, hz - h + 3, mx + larg / 2 - 1, mx + larg / 2 + 1, 255 * 0.9f, 190 * 0.9f, 100 * 0.9f);
      }
      break;
    case BOR_IGLOO: {
      bor_neige(e, hz, 0.35f, refl);
      const float porte = 0.8f + 0.2f * sinf(t * 2);
      for (int y = max(0, hz - 8); y <= hz && y < H; y++)
        for (int x = 21; x <= 43; x++) {
          const float u = (x - 32) / 11.0f, w = (y - hz) / 8.0f, d = u * u + w * w;
          bool anneau = false;
          for (int k = 0; k < 3; k++) anneau = anneau || fabsf(d - (0.35f + k * 0.25f)) < 0.04f;
          if (anneau) peindre(y, x, 40 + refl[0] * 0.3f, 56 + refl[1] * 0.3f, 80 + refl[2] * 0.3f);
          else if (abs(x - 32) <= 2 && y >= hz - 3) peindre(y, x, 255 * porte, 170 * porte, 80 * porte);
          else if (d <= 1) peindre(y, x, 60 + refl[0] * 0.45f, 80 + refl[1] * 0.45f, 110 + refl[2] * 0.45f);
        }
      break;
    }
    case BOR_VOLCAN: {
      bor_faites(e.crete[0], 64, 8, 6, 10);
      bor_rect(hz + 4, 64, 0, 64, 6, 6, 10);
      const float pouls = 0.75f + 0.25f * sinf(t * 2.3f);
      for (int j = 0; j < 27; j++) {
        const int y = hz - 23 + j;
        if (y < 0 || y >= H) continue;
        for (int i = 0; i < 21; i++) ajouter(y, 22 + i, e.lave[j][i] * pouls + e.coulee[j][i], 255, 90, 30);
      }
      break;
    }
    case BOR_SOMMET:
      bor_faites(e.crete[0], 64, 8, 10, 18);
      for (int x = 0; x < W; x++) {   // la calotte de neige
        const float pic = e.crete[0][x], bas = pic + 2 + fmaxf(52 - pic, 0.0f) * 0.25f;
        for (int y = max(0, (int)ceilf(pic)); y < H && y < bas; y++)
          peindre(y, x, 46 + refl[0] * 0.3f, 56 + refl[1] * 0.3f, 78 + refl[2] * 0.3f);
      }
      break;
    default:   // le ciel : rien que le ciel
      break;
  }
}

// _detail_boreal : des etoiles filantes, de la neige qui tombe, une brume au ras du sol
void bor_detail(E_boreal &e, const BorReglages &p, float t, float ecoule, float dt) {
  if (p.detail == BOR_FILANTES) {
    if (ecoule >= e.suivante) {
      e.suivante = ecoule + hasard(2.0f, 5.0f);
      if (e.nfil < 4) {
        float *f = e.fil[e.nfil++];
        f[0] = hasard(20, 70); f[1] = hasard(0, 16); f[2] = -hasard(50, 80); f[3] = hasard(18, 30);
        f[4] = 0; f[5] = hasard(0.5f, 0.8f);
      }
    }
    int garde = 0;
    for (int i = 0; i < e.nfil; i++) {
      float *f = e.fil[i];
      f[0] += f[2] * dt;
      f[1] += f[3] * dt;
      f[4] += dt;
      if (f[4] >= f[5]) continue;
      const float vie = 1 - f[4] / f[5];
      for (int k = 0; k < 10; k++) {
        const float q = e.trainee[k] * vie;
        pointer(f[1] - f[3] * k * 0.008f, f[0] - f[2] * k * 0.008f, 255 * q, 245 * q, 225 * q);
      }
      if (garde != i) memcpy(e.fil[garde], f, sizeof e.fil[0]);
      garde++;
    }
    e.nfil = garde;
  } else if (p.detail == BOR_NEIGE) {
    for (int i = 0; i < 45; i++) {
      e.fy[i] = fmodf(e.fy[i] + e.fv[i] * dt, 64.0f);
      const float l = 0.4f + 0.6f * (e.fv[i] - 4) / 6;
      const float x = fmodf(fmodf(e.fx[i] + sinf(t * 1.1f + e.fp[i]) * 2, 64.0f) + 64.0f, 64.0f);
      pointer(e.fy[i], x, 210 * l, 220 * l, 240 * l);
    }
  } else if (p.detail == BOR_BRUME) {
    const float ox = t * 1.5f;
    const int x0 = (int)floorf(ox);
    const float fx = ox - x0, norme = 1.0f / 65535.0f;
    for (int j = 0; j < BOR_BRUME_L; j++) {
      const int y = e.brume_y + j;
      if (y < 0 || y >= H) continue;
      const uint16_t *ligne = e.brume + j * 128;
      const float g = e.brume_g[j] * norme;
      for (int x = 0; x < W; x++) {
        const float b = (ligne[(x + x0) & 127] * (1 - fx) + ligne[(x + x0 + 1) & 127] * fx) * g;
        ajouter(y, x, b, 70, 80, 100);
      }
    }
  }
}

void s_tunnel_boreal(int humeur, bool debut, float t, float ecoule, float dt);

// humeurs : 0 = montagnes, 1 = lac, 2 = fjord, 3 = mer, 4 = banquise, 5 = plaine, 6 = foret, 7 = cabane,
// 8 = tente, 9 = phare, 10 = village, 11 = igloo, 12 = volcan, 13 = sommet, 14 = foret_lac, 15 = ciel
// (l'index dans _presets_boreaux() ; 16-20, les tunnels, vont a s_tunnel_boreal)
void s_boreal(int humeur, bool debut, float t, float ecoule, float dt) {
  if (humeur >= BOR_NB_AURORES) {   // _ecran_boreal : une preset de tunnel, c'est le tunnel
    s_tunnel_boreal(humeur, debut, t, ecoule, dt);
    return;
  }
  E_boreal &e = etat_ecran<E_boreal>(debut);
  const BorReglages p = bor_reglages(humeur);
  if (debut) bor_semer(e, p);
  const int hz = p.horizon;
  // le ciel, ses etoiles, sa lune
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) peindre(y, x, e.fond[y][0], e.fond[y][1], e.fond[y][2]);
  etoiles_du_ciel(t);
  if (p.lune) bor_lune(p);
  // l'aurore (derriere l'horizon : rien), et ce qu'elle jette sur la neige (la moyenne des 14 lignes sur l'horizon)
  const BorPalette &pal = BOR_COULEURS[p.palette];
  const float base = hz < 64 ? fminf((float)hz, 52.0f) - 14 : 34.0f;
  const int h0 = max(0, hz - 14);
  float refl[3] = {0, 0, 0};
  switch (p.style) {
    case BOR_RIDEAUX:
    case BOR_RIDEAUX_FINS:
    case BOR_RUBAN:
      bor_rideaux(pal, t, base, hz, p.style == BOR_RIDEAUX_FINS, p.style == BOR_RUBAN, p.vitesse, h0, refl);
      break;
    case BOR_VOILE:
      bor_voile(e, pal, t, base + 4, hz, p.vitesse, h0, refl);
      break;
    default:
      bor_couronne(e, pal, t, p.style == BOR_SPIRALE, p.vitesse, hz < 64 ? 14.0f : 26.0f, hz, h0, refl);
      break;
  }
  for (int c = 0; c < 3; c++) refl[c] = hz < 64 ? refl[c] / ((hz - h0) * 64.0f) : 0.0f;
  bor_paysage(e, p, t, refl);
  bor_detail(e, p, t, ecoule, dt);
}

// --- les tunnels (_tunnel_boreal) ------------------------------------------------

struct E_tunnel_boreal {
  float ca[40], sa[40], pz[40];   // les poussieres : leur direction, leur profondeur
  float p13[258];                 // x ** 1.3
};

// l'image du tunnel, une forme a la fois (F : BOR_ROND... BOR_VER)
template <int F>
void bor_tunnel_image(const E_tunnel_boreal &e, const float (*couleurs)[3], int n, float t, float cx, float cy, float v,
                      float sens) {
  const float prof_k = F == BOR_ANNEAUX ? 40.0f : 26.0f, prof_inv = 1.0f / (F == BOR_ANNEAUX ? 16.0f : 24.0f);
  const float defile = sens * t * 1.4f * v, tourne = t * 0.03f * sens, plis = F == BOR_CARRE ? 4.0f : 6.0f;
  const float inv_n = 1.0f / n, ondule = t * 0.7f;
  const float bout_r = couleurs[0][0] * 0.8f, bout_v = couleurs[0][1] * 0.8f, bout_b = couleurs[0][2] * 0.8f;
  for (int y = 0; y < H; y++) {
    const float dy = y - cy;
    for (int x = 0; x < W; x++) {
      const float dx = x - cx;
      const float d = (F == BOR_CARRE ? fmaxf(fabsf(dx), fabsf(dy)) : sqrtf(dx * dx + dy * dy)) + 0.6f;
      float r = 0, g = 0, b = 0;
      const float pr = (d - 1.5f) * prof_inv;   // le fond se perd dans le noir
      if (pr > 0) {
        const float profondeur = bor_p13(e.p13, pr);
        const float z = prof_k / d + defile;   // la profondeur, qui defile
        float tour = bor_atan2(dy, dx) * BOR_TOUR + tourne;   // le tour de la paroi, de 0 a 1
        if (F == BOR_EN_SPIRALE) tour += z * 0.18f;
        if (F == BOR_VER) tour += bor_sin(z * 0.6f + ondule) * 0.08f;
        float te = z * 0.35f;   // la couleur change en profondeur : (z * 0.35) % n
        te -= n * (float)(int)(te * inv_n);
        if (te < 0) te += n;
        int i0 = (int)te;
        if (i0 > n - 1) i0 = n - 1;
        const float f = te - i0, *c0 = couleurs[i0], *c1 = couleurs[i0 + 1];
        const float ri = 0.5f + 0.5f * bor_sint(tour * plis + bor_sin(z * 0.9f + tour * 6) * (1.6f * BOR_TOUR));
        const float paroi = ri * ri;   // les rideaux
        const float an = 0.5f + 0.5f * bor_sint(z + 0.25f);   // cos(2 pi z)
        float motif;
        if (F == BOR_ANNEAUX) {
          const float an2 = an * an;
          motif = an2 * an2 * an * (0.5f + 0.5f * paroi);
        } else {   // les anneaux font la profondeur, les rideaux la paroi
          motif = (0.2f + 0.8f * an * an * an) * (0.3f + 0.7f * paroi);
        }
        const float k = motif * profondeur;
        r = k * (c0[0] + (c1[0] - c0[0]) * f);
        g = k * (c0[1] + (c1[1] - c0[1]) * f);
        b = k * (c0[2] + (c1[2] - c0[2]) * f);
      }
      if (F == BOR_VER && d < 27) {   // une lumiere tout au bout (au-dela de 27 px : moins de 0.05)
        const float l = bor_exp(-d * (1.0f / 3.0f));
        r += l * bout_r;
        g += l * bout_v;
        b += l * bout_b;
      }
      peindre(y, x, r, g, b);
    }
  }
}

// humeurs : 16 = rond, 17 = carre, 18 = spirale, 19 = anneaux, 20 = ver (l'index dans _presets_boreaux())
void s_tunnel_boreal(int humeur, bool debut, float t, float ecoule, float dt) {
  E_tunnel_boreal &e = etat_ecran<E_tunnel_boreal>(debut);
  (void)ecoule; (void)dt;
  const BorReglages p = bor_reglages(humeur < BOR_NB_AURORES ? BOR_NB_AURORES + humeur % BOR_NB_TUNNELS : humeur);
  if (debut) {
    for (int i = 0; i < 40; i++) {
      const float a = hasard(0, PI2);
      e.ca[i] = cosf(a);
      e.sa[i] = sinf(a);
    }
    for (int i = 0; i < 40; i++) e.pz[i] = hasard(0, 1);
    bor_table13(e.p13);
  }
  const int forme = p.forme;
  const float v = p.vitesse, sens = p.sens;
  const BorPalette &pal = BOR_COULEURS[p.palette];
  const int n = pal.n;
  float couleurs[5][3];   // la palette, et sa premiere couleur encore apres la derniere (le tour des teintes)
  for (int i = 0; i <= n; i++)
    for (int c = 0; c < 3; c++) couleurs[i][c] = pal.c[i % n][c];
  const float errance = forme == BOR_VER ? 8.0f : 4.0f;
  const float cx = 32 - errance * sinf(t * 0.6f * v), cy = 32 - errance * cosf(t * 0.45f * v);
  switch (forme) {
    case BOR_CARRE: bor_tunnel_image<BOR_CARRE>(e, couleurs, n, t, cx, cy, v, sens); break;
    case BOR_EN_SPIRALE: bor_tunnel_image<BOR_EN_SPIRALE>(e, couleurs, n, t, cx, cy, v, sens); break;
    case BOR_ANNEAUX: bor_tunnel_image<BOR_ANNEAUX>(e, couleurs, n, t, cx, cy, v, sens); break;
    case BOR_VER: bor_tunnel_image<BOR_VER>(e, couleurs, n, t, cx, cy, v, sens); break;
    default: bor_tunnel_image<BOR_ROND>(e, couleurs, n, t, cx, cy, v, sens); break;
  }
  const float avance = t * 0.22f * v * sens;   // des poussieres qui filent vers soi
  for (int i = 0; i < 40; i++) {
    float q = e.pz[i] + avance;
    q -= floorf(q);
    const float rr = 2 + q * q * 44, k = q * sqrtf(q);
    pointer(cy + rr * e.sa[i], cx + rr * e.ca[i], 200 * k, 220 * k, 255 * k);
  }
}
