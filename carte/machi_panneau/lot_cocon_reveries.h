// lot_cocon_reveries.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
// LE COCON (des bougies, une cheminee, un the sous la pluie, la poussiere dans un rayon de soleil, une lampe a
// fibres, une boule plasma, un vinyle) et LES REVERIES (des rubans de soie, l'encre dans l'eau, des courants de
// lumiere, un kaleidoscope, un pendule de sable, un flocon qui pousse, un vortex). Chacun une seule ambiance.
#pragma once

// --- les outils du lot (prefixe cr_) ------------------------------------------------------------------------------

// min, max, hypot en ligne (fminf, fmaxf, hypotf sont des appels de bibliotheque, chers dans les boucles)
inline float cr_min(float a, float b) { return a < b ? a : b; }
inline float cr_max(float a, float b) { return a > b ? a : b; }
inline float cr_hypot(float a, float b) { return sqrtf(a * a + b * b); }

// exp, sin, cos, log rapides : les jumeaux de numpy a 1e-6 pres, sans les 100-300 cycles de la carte
inline float cr_exp(float x) {
  float y = x * 1.44269504f;
  if (y < -125.0f) return 0.0f;
  if (y > 125.0f) y = 125.0f;
  const int n = (int)(y + 126.5f) - 126;              // l'entier le plus proche
  const float f = y - (float)n;                       // dans [-0.5, 0.5]
  const float p = 1.0f + f * (0.693147181f + f * (0.240226507f + f * (0.0555041087f + f * (0.00961812911f
                  + f * (0.00133335581f + f * 0.000154035304f)))));
  const uint32_t bits = (uint32_t)(n + 127) << 23;
  float deux;
  memcpy(&deux, &bits, 4);
  return p * deux;
}
inline float cr_sin(float x) {
  float k = x * 0.159154943f;                          // en tours
  k -= (float)(int)(k + (k >= 0 ? 0.5f : -0.5f));     // dans [-0.5, 0.5]
  if (k > 0.25f) k = 0.5f - k;
  else if (k < -0.25f) k = -0.5f - k;
  const float z = k * 6.28318531f, z2 = z * z;
  return z * (1.0f + z2 * (-0.166666667f + z2 * (0.00833333333f + z2 * (-0.000198412698f + z2 * 2.75573192e-6f))));
}
inline float cr_cos(float x) { return cr_sin(x + 1.57079633f); }
inline float cr_log(float x) {                         // x > 0
  uint32_t bits;
  memcpy(&bits, &x, 4);
  const int ex = (int)((bits >> 23) & 255) - 127;
  bits = (bits & 0x007FFFFFu) | 0x3F800000u;
  float m;
  memcpy(&m, &bits, 4);                                // dans [1, 2)
  const float s = (m - 1.0f) / (m + 1.0f), s2 = s * s; // ln m = 2 atanh(s)
  return ex * 0.693147181f + 2.0f * s * (1.0f + s2 * (0.333333333f + s2 * (0.2f + s2 * (0.142857143f + s2 * 0.111111111f))));
}
inline float cr_atan2(float y, float x) {
  const float ax = fabsf(x), ay = fabsf(y);
  const float mx = cr_max(ax, ay), mn = cr_min(ax, ay);
  if (mx <= 0.0f) return 0.0f;
  const float a = mn / mx, s = a * a;
  float r = a * (0.99997726f + s * (-0.33262347f + s * (0.19354346f + s * (-0.11643287f + s * (0.05265332f - s * 0.01172120f)))));
  if (ay > ax) r = 1.57079633f - r;
  if (x < 0) r = 3.14159265f - r;
  return y < 0 ? -r : r;
}
inline float cr_clip01(float v) { return v < 0 ? 0.0f : v > 1 ? 1.0f : v; }
inline float cr_ramp(float v) { return v < 0 ? 0.0f : v; }

// une valeur qui s'efface (x k), mise a zero quand elle ne compte plus : sinon elle finit en nombre denormal,
// et chaque operation sur elle coute des centaines de cycles
inline float cr_efface(float v, float k) { v *= k; return v < 1e-9f ? 0.0f : v; }

// un point pose entre les pixels, partage sur ses quatre voisins (_cocon_tamponner) ; hors du panneau, perdu
__attribute__((always_inline)) inline void cr_tamponner(float y, float x, float r, float v, float b) {
  if (!(y > -1 && y < 64 && x > -1 && x < 64)) return;
  const int y0 = (int)(y + 1.0f) - 1, x0 = (int)(x + 1.0f) - 1;   // floor, pour y > -1
  const float fy = y - y0, fx = x - x0;
  if ((unsigned)y0 < 63u && (unsigned)x0 < 63u) {        // les quatre voisins dans le panneau
    float *p = scene[y0][x0], *q = scene[y0 + 1][x0];
    const float a = (1 - fy) * (1 - fx), c = (1 - fy) * fx, d = fy * (1 - fx), g = fy * fx;
    p[0] += a * r; p[1] += a * v; p[2] += a * b; p[3] += c * r; p[4] += c * v; p[5] += c * b;
    q[0] += d * r; q[1] += d * v; q[2] += d * b; q[3] += g * r; q[4] += g * v; q[5] += g * b;
    return;
  }
  const float w[4] = {(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx};
  for (int k = 0; k < 4; k++) {
    const int yy = y0 + (k >> 1), xx = x0 + (k & 1);
    if (yy < 0 || yy > 63 || xx < 0 || xx > 63) continue;
    float *p = scene[yy][xx];
    p[0] += w[k] * r; p[1] += w[k] * v; p[2] += w[k] * b;
  }
}
// la meme chose dans un tampon d'une couleur (64 x 64)
inline void cr_tamponner1(float *buf, float y, float x, float v) {
  const float fy0 = floorf(y), fx0 = floorf(x);
  const int y0 = (int)fy0, x0 = (int)fx0;
  if (y0 < -1 || y0 > 63 || x0 < -1 || x0 > 63) return;
  const float fy = y - fy0, fx = x - fx0;
  if (y0 >= 0) {
    if (x0 >= 0) buf[y0 * 64 + x0] += (1 - fy) * (1 - fx) * v;
    if (x0 < 63) buf[y0 * 64 + x0 + 1] += (1 - fy) * fx * v;
  }
  if (y0 < 63) {
    if (x0 >= 0) buf[(y0 + 1) * 64 + x0] += fy * (1 - fx) * v;
    if (x0 < 63) buf[(y0 + 1) * 64 + x0 + 1] += fy * fx * v;
  }
}
// et dans un tampon de trois couleurs (64 x 64 x 3)
inline void cr_tamponner3(float *buf, float y, float x, float r, float v, float b) {
  if (!(y > -1 && y < 64 && x > -1 && x < 64)) return;
  const int y0 = (int)(y + 1.0f) - 1, x0 = (int)(x + 1.0f) - 1;   // floor, pour y > -1
  const float fy = y - y0, fx = x - x0;
  if (y0 >= 0 && y0 < 63 && x0 >= 0 && x0 < 63) {        // les quatre voisins dans le panneau
    float *p = buf + (y0 * 64 + x0) * 3, *q = p + 192;
    const float a = (1 - fy) * (1 - fx), c = (1 - fy) * fx, d = fy * (1 - fx), g = fy * fx;
    p[0] += a * r; p[1] += a * v; p[2] += a * b; p[3] += c * r; p[4] += c * v; p[5] += c * b;
    q[0] += d * r; q[1] += d * v; q[2] += d * b; q[3] += g * r; q[4] += g * v; q[5] += g * b;
    return;
  }
  const float w[4] = {(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx};
  for (int k = 0; k < 4; k++) {
    const int yy = y0 + (k >> 1), xx = x0 + (k & 1);
    if (yy < 0 || yy > 63 || xx < 0 || xx > 63) continue;
    float *p = buf + (yy * 64 + xx) * 3;
    p[0] += w[k] * r; p[1] += w[k] * v; p[2] += w[k] * b;
  }
}

// _cocon_flou : [1 2 1] / 4 sur les deux axes, n fois, les bords ne se raccordent pas (au-dela : zero) ;
// en place, sur un tampon de c couleurs (entrelacees), dans la boite [y0, y1) x [x0, x1) (dehors : zero)
void cr_flou_cocon(float *a, int c, int n, int y0 = 0, int y1 = 64, int x0 = 0, int x1 = 64) {
  float avant[64 * 3];
  for (int pas = 0; pas < n; pas++) {
    for (int y = y0; y < y1; y++) {                    // les lignes
      float *l = a + (y * 64) * c;
      for (int k = 0; k < c; k++) {
        float g = 0, m = l[x0 * c + k];
        for (int x = x0; x < x1; x++) {
          const float d = x + 1 < x1 ? l[(x + 1) * c + k] : 0.0f;
          l[x * c + k] = (g + 2 * m + d) * 0.25f;
          g = m; m = d;
        }
      }
    }
    for (int i = 0; i < 64 * c; i++) avant[i] = 0;     // les colonnes
    for (int y = y0; y < y1; y++) {
      float *l = a + (y * 64) * c;
      const float *s = y + 1 < y1 ? a + ((y + 1) * 64) * c : nullptr;
      for (int i = x0 * c; i < x1 * c; i++) {
        const float m = l[i];
        l[i] = (avant[i] + 2 * m + (s ? s[i] : 0.0f)) * 0.25f;
        avant[i] = m;
      }
    }
  }
}
// _reveries_flou : le meme, les bords recopies (la lumiere ne fuit pas), sur un tampon de taille x taille
void cr_flou_rev(float *a, int c, int n, int taille = 64, int y0 = 0, int y1 = -1) {
  // (y0, y1) : seules ces lignes sont traitees -- les autres sont nulles et doivent le rester (marge >= n)
  if (y1 < 0) y1 = taille;
  float avant[64 * 3];
  const int m1 = taille - 1;
  for (int pas = 0; pas < n; pas++) {
    for (int y = y0; y < y1; y++) {
      float *l = a + (y * taille) * c;
      if (c == 3) {                                      // les trois couleurs ensemble
        float g0 = l[0], g1 = l[1], g2 = l[2], m0 = g0, m1c = g1, m2 = g2;
        for (int x = 0; x < taille; x++) {
          const float *n = l + (x < m1 ? x + 1 : m1) * 3;
          const float d0 = n[0], d1 = n[1], d2 = n[2];
          l[3 * x] = (g0 + 2 * m0 + d0) * 0.25f; l[3 * x + 1] = (g1 + 2 * m1c + d1) * 0.25f; l[3 * x + 2] = (g2 + 2 * m2 + d2) * 0.25f;
          g0 = m0; g1 = m1c; g2 = m2; m0 = d0; m1c = d1; m2 = d2;
        }
        continue;
      }
      for (int k = 0; k < c; k++) {
        float g = l[k], m = l[k];
        for (int x = 0; x < taille; x++) {
          const float d = l[(x < m1 ? x + 1 : m1) * c + k];
          l[x * c + k] = (g + 2 * m + d) * 0.25f;
          g = m; m = d;
        }
      }
    }
    for (int i = 0; i < taille * c; i++) avant[i] = a[(y0 > 0 ? y0 - 1 : 0) * taille * c + i];
    for (int y = y0; y < y1; y++) {
      float *l = a + (y * taille) * c;
      const float *s = a + ((y < m1 ? y + 1 : m1) * taille) * c;
      for (int i = 0; i < taille * c; i++) {
        const float m = l[i];
        l[i] = (avant[i] + 2 * m + s[i]) * 0.25f;
        avant[i] = m;
      }
    }
  }
}

// _reveries_halo : un grand halo pas cher -- a demi-taille (32 x 32 x 3), flou n fois, remis a la taille du
// panneau et flou une fois (ce qui revient a l'agrandir en melangeant 1/4 - 3/4) ; ajoute k * halo a la scene
// (multiplie, s'il est donne, par mult[pixel])
// (avec loin : ajoute aussi un fond, f0 + loin[pixel] * f1)
void cr_agrandir(const float *petit, float k, const float *mult = nullptr, const float *loin = nullptr,
                 const float *f0 = nullptr, const float *f1 = nullptr);
void cr_halo_rev(const float *src, float *petit, int n, float k) {
  for (int y = 0; y < 32; y++)
    for (int x = 0; x < 32; x++)
      for (int c = 0; c < 3; c++) {
        const float *p = src + ((2 * y) * 64 + 2 * x) * 3 + c;
        petit[(y * 32 + x) * 3 + c] = (p[0] + p[3] + p[192] + p[195]) * 0.25f;
      }
  cr_flou_rev(petit, 3, n, 32);
  cr_agrandir(petit, k);
}
void cr_agrandir(const float *petit, float k, const float *mult, const float *loin, const float *f0, const float *f1) {
  float ligne[34 * 3];                                   // une ligne a demi-taille, ses bouts recopies
  for (int y = 0; y < 64; y++) {
    const int ya = y & 1 ? y >> 1 : max(0, (y >> 1) - 1), yb = y & 1 ? min(31, (y >> 1) + 1) : y >> 1;
    const float wa = (y & 1 ? 0.75f : 0.25f) * k, wb = k - wa;
    const float *p = petit + ya * 96, *q = petit + yb * 96;
    for (int i = 0; i < 96; i++) ligne[i + 3] = wa * p[i] + wb * q[i];   // d'abord entre les deux lignes
    for (int c = 0; c < 3; c++) { ligne[c] = ligne[3 + c]; ligne[99 + c] = ligne[96 + c]; }
    float *o = scene[y][0];
    const float *m = mult ? mult + y * 64 : nullptr;
    if (loin) {
      const float *lo = loin + y * 64;
      for (int i = 0; i < 32; i++, o += 6) {
        const float *g = ligne + 3 * i, *c = g + 3, *d = g + 6, la = lo[2 * i], lb = lo[2 * i + 1];
        o[0] += 0.25f * g[0] + 0.75f * c[0] + f0[0] + la * f1[0]; o[1] += 0.25f * g[1] + 0.75f * c[1] + f0[1] + la * f1[1];
        o[2] += 0.25f * g[2] + 0.75f * c[2] + f0[2] + la * f1[2];
        o[3] += 0.75f * c[0] + 0.25f * d[0] + f0[0] + lb * f1[0]; o[4] += 0.75f * c[1] + 0.25f * d[1] + f0[1] + lb * f1[1];
        o[5] += 0.75f * c[2] + 0.25f * d[2] + f0[2] + lb * f1[2];
      }
    } else if (!m)
      for (int i = 0; i < 32; i++, o += 6) {             // puis entre les deux colonnes : 1/4 - 3/4, 3/4 - 1/4
        const float *g = ligne + 3 * i, *c = g + 3, *d = g + 6;
        o[0] += 0.25f * g[0] + 0.75f * c[0]; o[1] += 0.25f * g[1] + 0.75f * c[1]; o[2] += 0.25f * g[2] + 0.75f * c[2];
        o[3] += 0.75f * c[0] + 0.25f * d[0]; o[4] += 0.75f * c[1] + 0.25f * d[1]; o[5] += 0.75f * c[2] + 0.25f * d[2];
      }
    else
      for (int i = 0; i < 32; i++, o += 6) {
        const float *g = ligne + 3 * i, *c = g + 3, *d = g + 6;
        const float ma = m[2 * i], mb = m[2 * i + 1];
        o[0] += ma * (0.25f * g[0] + 0.75f * c[0]); o[1] += ma * (0.25f * g[1] + 0.75f * c[1]); o[2] += ma * (0.25f * g[2] + 0.75f * c[2]);
        o[3] += mb * (0.75f * c[0] + 0.25f * d[0]); o[4] += mb * (0.75f * c[1] + 0.25f * d[1]); o[5] += mb * (0.75f * c[2] + 0.25f * d[2]);
      }
  }
}

// _reveries_lumiere : de la lumiere qui s'additionne -> des couleurs, qui saturent en douceur
inline void cr_lumiere(float *l, float k) {
  const float m = cr_max(l[0], cr_max(l[1], l[2]));
  if (m <= 1e-6f) { l[0] = l[1] = l[2] = 0; return; }
  const float f = 255.0f * (1 - cr_exp(-m / k)) / m;
  l[0] *= f; l[1] *= f; l[2] *= f;
}

// _reveries_palette : une palette en boucle, sans couture
inline void cr_palette_rev(const float (*pal)[3], int n, float k, float *out, bool doux = true) {
  k = (k - floorf(k)) * n;
  const float fk = floorf(k);
  int i = (int)fk % n;
  if (i < 0) i += n;
  float f = k - fk;
  if (doux) f = f * f * (3 - 2 * f);
  const float *a = pal[i], *b = pal[(i + 1) % n];
  for (int c = 0; c < 3; c++) out[c] = a[c] * (1 - f) + b[c] * f;
}

// _cocon_palette : une valeur (0..1) -> une couleur, le long d'une suite (np.interp, borne aux deux bouts)
inline void cr_palette_cocon(const float *pas, const float (*coul)[3], int n, float v, float *out) {
  if (v <= pas[0]) { out[0] = coul[0][0]; out[1] = coul[0][1]; out[2] = coul[0][2]; return; }
  for (int i = 1; i < n; i++)
    if (v <= pas[i]) {
      const float f = (v - pas[i - 1]) / (pas[i] - pas[i - 1]);
      for (int c = 0; c < 3; c++) out[c] = coul[i - 1][c] + (coul[i][c] - coul[i - 1][c]) * f;
      return;
    }
  out[0] = coul[n - 1][0]; out[1] = coul[n - 1][1]; out[2] = coul[n - 1][2];
}

// _fenetre sur un champ en uint16 : la partie fractionnaire est la meme partout, on la prepare une fois
struct cr_Fen { const uint16_t *c; int m, sh, x0, y0; float fx, fy; };
inline cr_Fen cr_fen(const uint16_t *c, int taille, float ox, float oy) {
  cr_Fen f;
  f.c = c; f.m = taille - 1; f.sh = taille == 128 ? 7 : 6;
  const float a = floorf(ox), b = floorf(oy);
  f.x0 = (int)a; f.y0 = (int)b; f.fx = ox - a; f.fy = oy - b;
  return f;
}
inline float cr_lire(const cr_Fen &f, int x, int y) {
  const int xa = (x + f.x0) & f.m, xb = (x + f.x0 + 1) & f.m;
  const int ya = ((y + f.y0) & f.m) << f.sh, yb = ((y + f.y0 + 1) & f.m) << f.sh;
  const float a = f.c[ya + xa], b = f.c[ya + xb], d = f.c[yb + xa], g = f.c[yb + xb];
  const float h = a + (b - a) * f.fx, l = d + (g - d) * f.fx;
  return (h + (l - h) * f.fy) * (1.0f / 65535.0f);
}

// --- les bougies -------------------------------------------------------------------------------------------------

static const float CR_BOUGIES[4][7] = {   // x de la meche, demi-largeur, haut de la cire, pied, couleur de la cire
  {12.5f, 3.5f, 31.0f, 57.0f, 236, 214, 178}, {25.5f, 4.5f, 41.0f, 59.0f, 238, 196, 168},
  {39.0f, 3.0f, 23.0f, 56.0f, 238, 222, 192}, {51.5f, 4.0f, 36.0f, 58.0f, 232, 172, 96}};
static const float CR_LOINTAINES[4][3] = {{5, 20, 3.2f}, {33, 9, 2.6f}, {58, 15, 3.6f}, {46, 26, 2.4f}};

// humeurs : 0 = (une seule ambiance)
struct E_bougies {
  float f[4][5], ph[4][6], fs[4], ps[4];   // les rythmes de chaque flamme
  float lph[4], lvit[4];                   // les bougies lointaines
  float fk[28], fteinte[28][3];            // le filet de fumee : (1 - k/28)^1.3, sa teinte
  uint16_t grain[4096];
  uint16_t fond[4096][3];                  // le mur et la table, x 256
};
void s_bougies(int humeur, bool debut, float t, float ecoule, float dt) {
  E_bougies &e = etat_ecran<E_bougies>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    static const float lo[5] = {1.1f, 2.4f, 4.4f, 0.35f, 1.3f}, hi[5] = {1.7f, 3.3f, 6.0f, 0.6f, 2.0f};
    for (int c = 0; c < 4; c++) {
      for (int k = 0; k < 5; k++) e.f[c][k] = hasard(lo[k], hi[k]);
      for (int k = 0; k < 6; k++) e.ph[c][k] = hasard(0, PI2);
      e.fs[c] = hasard(0.05f, 0.085f);
      e.ps[c] = hasard(0, PI2);
    }
    brume_n(e.grain, 64, 2);
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        float c[3];
        if (y == 53) { c[0] = 30; c[1] = 18; c[2] = 12; }
        else if (y > 53) {                                 // la table, son bois
          const float k = (y - 53) / 11.0f, b = 0.88f + 0.12f * sinf(y * 2.3f + sinf(x * 0.13f) * 2);
          c[0] = (28 + (11 - 28) * k) * b; c[1] = (16 + (6 - 16) * k) * b; c[2] = (10 + (4 - 10) * k) * b;
        } else {                                           // le mur, plus sombre dans les coins
          const float k = y / 53.0f;
          const float coin = cr_clip01(1 - cr_hypot((x - 32) / 44.0f, (y - 40) / 52.0f));
          const float m = (0.85f + 0.3f * e.grain[y * 64 + x] / 65535.0f) * (0.55f + 0.45f * coin);
          c[0] = (5 + 8 * k) * m; c[1] = (3 + 5 * k) * m; c[2] = (4 + 4 * k) * m;
        }
        for (int k = 0; k < 3; k++) e.fond[y * 64 + x][k] = (uint16_t)(c[k] * 256 + 0.5f);
      }
    for (int i = 0; i < 4; i++) { e.lph[i] = hasard(0, PI2); e.lvit[i] = hasard(0.25f, 0.5f); }
    for (int k = 0; k < 28; k++) {
      e.fk[k] = powf(1 - k / 28.0f, 1.3f);
      const float proche = expf(-k / 6.0f);
      e.fteinte[k][0] = 150 * proche + 80 * (1 - proche);
      e.fteinte[k][1] = 112 * proche + 80 * (1 - proche);
      e.fteinte[k][2] = 84 * proche + 92 * (1 - proche);
    }
  }
  const float s1 = cr_max(0.0f, sinf(t * 0.083f + 1.0f));
  const float vent = 0.22f * sinf(t * 0.19f) * s1 * s1;                 // un courant d'air, parfois
  float h[4], pente[4], eclat[4], fumee[4], yf[4], yc[4], gx[4], k45[4];
  for (int c = 0; c < 4; c++) {
    const float *f = e.f[c], *ph = e.ph[c], hw = CR_BOUGIES[c][1];
    fumee[c] = cr_clip01((sinf(t * e.fs[c] + e.ps[c]) - 0.74f) / 0.26f);   // de temps en temps elle fume
    const float vie = 1 + 0.07f * sinf(t * f[0] + ph[0]) + 0.045f * sinf(t * f[1] + ph[1]) + 0.025f * sinf(t * f[2] + ph[2]);
    h[c] = (6.0f + hw * 0.6f) * vie * (1 - 0.15f * fumee[c]);
    pente[c] = 0.12f * sinf(t * f[3] + ph[3]) + 0.06f * sinf(t * f[4] + ph[4]) + vent;
    eclat[c] = vie * (1 - 0.12f * fumee[c]);
    yf[c] = CR_BOUGIES[c][2] - 1.2f;
    yc[c] = yf[c] - h[c] * 0.35f;
    gx[c] = CR_BOUGIES[c][0] + pente[c] * h[c] * 0.2f;
    k45[c] = eclat[c] * 0.45f;
  }
  // le mur et la table, eclaires par les flammes
  for (int y = 0; y < 64; y++) {
    float dy2[4], dt2[4];
    for (int c = 0; c < 4; c++) {
      dy2[c] = (y - yc[c]) * (y - yc[c]);
      dt2[c] = (y - CR_BOUGIES[c][3]) * 1.6f * (y - CR_BOUGIES[c][3]) * 1.6f;
    }
    for (int x = 0; x < 64; x++) {
      float l = 0;
      for (int c = 0; c < 4; c++) {
        const float dx = x - gx[c];
        l += k45[c] * cr_exp(-sqrtf(dx * dx + dy2[c]) * 0.1f);
      }
      if (y >= 53)
        for (int c = 0; c < 4; c++) {                  // sur la table
          const float dx = (x - CR_BOUGIES[c][0]) * 0.55f;
          l += k45[c] * cr_exp(-sqrtf(dx * dx + dt2[c]) * (1.0f / 6.0f));
        }
      const uint16_t *f = e.fond[y * 64 + x];
      const float m = (1 + 5 * l) * (1.0f / 256.0f), a = l * 0.42f;
      peindre(y, x, f[0] * m + a * 255, f[1] * m + a * 125, f[2] * m + a * 50);
    }
  }
  for (int i = 0; i < 4; i++) {                          // d'autres bougies, loin, floues
    const float cx = CR_LOINTAINES[i][0], cy = CR_LOINTAINES[i][1], r = CR_LOINTAINES[i][2];
    const float w = 0.11f + 0.025f * sinf(t * e.lvit[i] + e.lph[i]);
    for (int y = max(0, (int)(cy - r) - 1); y <= min(63, (int)(cy + r) + 1); y++)
      for (int x = max(0, (int)(cx - r) - 1); x <= min(63, (int)(cx + r) + 1); x++) {
        const float k = cr_clip01((r - cr_hypot(x - cx, y - cy)) / 1.6f) * w;
        if (k > 0) ajouter(y, x, k, 255, 150, 70);
      }
  }
  for (int c = 0; c < 4; c++) {                          // chaque bougie : on ne travaille que pres d'elle
    const float cx = CR_BOUGIES[c][0], hw = CR_BOUGIES[c][1], haut = CR_BOUGIES[c][2], pied = CR_BOUGIES[c][3];
    const float *cire = CR_BOUGIES[c] + 4;
    const int y0 = max(0, (int)(yf[c] - h[c] * 1.3f) - 2), x0 = max(0, (int)(cx - hw - 4));
    const int y1 = (int)pied + 1, x1 = min(64, (int)(cx + hw + 5));
    const float wfl = 1.2f + hw * 0.13f;
    const float bord_k = 0.62f + 0.2f * eclat[c], cuv_k = 0.8f + 0.2f * eclat[c];
    const float hw1 = hw - 1.0f;
    for (int y = y0; y < y1; y++) {
      const float dy = y - yc[c], dy2 = dy * dy;
      const float dessous = cr_exp(-(y - haut) / 6.0f) * eclat[c];  // la cire s'allume sous la flamme
      const float s = (yf[c] - y) / h[c];                // la flamme : 0 au pied, 1 a la pointe
      const float q = cr_clip01((s + 0.25f) / 1.25f);
      const float larg = wfl * 2.6f * sqrtf(q) * (1 - q) + 1e-3f;
      const float sc = cr_clip01(s);
      const float axe = cx + pente[c] * sc * sc * h[c];
      const bool flamme = q > 0 && q < 1;
      const float coeur_k = cr_clip01((0.62f - s) / 0.3f) * cr_clip01((s + 0.05f) / 0.2f);
      const float coeur_l = larg * 0.55f + 0.3f;
      const float by = (y - haut) / 1.3f, cy = (y - haut) / 0.7f;
      for (int x = x0; x < x1; x++) {
        float *w = scene[y][x];
        const float dx = x - gx[c];
        const float g = eclat[c] * 0.4f * cr_exp(-sqrtf(dx * dx + dy2) * (1.0f / 2.6f));   // l'eclat autour
        w[0] += g * 255; w[1] += g * 150; w[2] += g * 60;
        const float xn = (x - cx) / hw;
        if (fabsf(xn) <= 1.0f && y >= haut && y <= pied) {   // le corps : un cylindre de cire
          const float cyl = sqrtf(cr_clip01(1 - xn * xn));
          const float a = 0.12f + 0.24f * cyl, d = dessous * (0.25f + 0.75f * cyl * sqrtf(cyl)) * 0.9f;
          w[0] = cire[0] * 0.95f * a + d * 255; w[1] = cire[1] * 0.72f * a + d * 160; w[2] = cire[2] * 0.5f * a + d * 75;
        }
        if (xn * xn + by * by <= 1 && y < haut + 0.5f) {
          w[0] = cire[0] * bord_k; w[1] = cire[1] * 0.86f * bord_k; w[2] = cire[2] * 0.7f * bord_k;
        }
        const float cu = (x - cx) / hw1;
        if (cu * cu + cy * cy <= 1) { w[0] = 255 * cuv_k; w[1] = 190 * cuv_k; w[2] = 100 * cuv_k; }   // la cire fondue
        const float ecart = fabsf(x - axe);
        const float inten = flamme ? cr_clip01(1.15f - ecart / larg) : 0.0f;
        const float coeur = coeur_k > 0 ? cr_clip01(1.0f - ecart / coeur_l) * coeur_k : 0.0f;
        if (inten > 0 || coeur > 0) {
          const float m = cr_clip01(inten * 1.4f - 0.25f - sc * 0.5f);
          const float k = 1 - 0.7f * inten;
          w[0] = w[0] * k + 255 * inten + coeur * 204;
          w[1] = w[1] * k + (115 + 90 * m) * inten + coeur * 196;
          w[2] = w[2] * k + (25 + 75 * m) * inten + coeur * 176;
        }
      }
    }
  }
  for (int c = 0; c < 4; c++) {                          // un filet de fumee qui monte en ondulant
    if (fumee[c] <= 0.01f) continue;
    const float phf = e.ph[c][5];
    for (int k = 0; k < 28; k++) {
      const float ys = yf[c] - h[c] * 0.98f - 0.5f - k * 0.9f;
      const float xs = CR_BOUGIES[c][0] + pente[c] * h[c] + sinf(k * 0.27f - t * 1.3f + phf) * (0.15f + k * 0.07f)
                       + k * k * 0.006f * (vent * 4 + 0.3f);
      const float force = fumee[c] * e.fk[k] * (0.6f + 0.4f * sinf(k * 0.45f - t * 2.0f + phf)) * cr_clip01(k / 3.0f);
      cr_tamponner(ys, xs, e.fteinte[k][0] * force, e.fteinte[k][1] * force, e.fteinte[k][2] * force);
    }
  }
}

// --- la cheminee -------------------------------------------------------------------------------------------------

static const float CR_BUCHES[3][5] = {{17.0f, 47.5f, 47.0f, 46.5f, 3.0f}, {16.0f, 54.0f, 42.0f, 51.0f, 2.9f},
                                      {48.0f, 55.0f, 35.0f, 49.0f, 2.2f}};   // le bout coupe, l'autre, le rayon
static const float CR_FEU_PAS[6] = {0.0f, 0.16f, 0.38f, 0.6f, 0.8f, 1.0f};
static const float CR_FEU[6][3] = {{0, 0, 0}, {110, 14, 2}, {220, 60, 6}, {255, 140, 30}, {255, 200, 80}, {255, 236, 160}};

struct CR_Ecorce { uint16_t i; uint8_t buche, drapeaux; int8_t ny; uint8_t rb, ec[3]; };   // drapeaux : 1 fente, 2 bout, 4 cerne
struct CR_Braise { uint16_t i; float b; };

// humeurs : 0 = (une seule ambiance)
struct E_cheminee {
  uint16_t base[4096][3], vive[4096][3];   // la piece : base + vif * vive (x 32)
  uint16_t souffle[4096], flamA[4096], flamB[4096], tmp[4096];
  uint8_t masque[4096];                    // au semis : 1 joint, 2 objet, 4 ouverture
  CR_Ecorce ecorce[640];
  CR_Braise braise[160];
  int necorce, nbraise, debut_buche[4];
  float haut_ouv[64];
  float etin[11][6];                       // les etincelles : x, y, vy, age, vie, phase
};

inline bool cr_ouverture(float hauts, int x, int y) { return fabsf(x - 32.0f) <= 18.5f && y >= hauts && y <= 57; }

void cr_cheminee_preparer(E_cheminee &e) {
  float *alb = &scene[0][0][0];                          // l'albedo, le temps du semis
  for (int i = 0; i < 4096; i++) { alb[3 * i] = 26; alb[3 * i + 1] = 18; alb[3 * i + 2] = 16; }
  uint8_t *mq = e.masque;
  int y = 14;
  while (y < 64) {                                       // des assises de pierres, des blocs decales
    const int hh = 5 + (int)(aleatoire() % 3);
    float x0 = -hasard(0, 9);
    while (x0 < 64) {
      const float w = hasard(6, 13);
      const float k = hasard(0, 1), g = hasard(0.68f, 1.12f);
      const float c[3] = {(122 * (1 - k) + 134 * k) * g, (112 * (1 - k) + 104 * k) * g, (102 * (1 - k) + 82 * k) * g};
      for (int yy = y; yy < min(64, y + hh); yy++)
        for (int x = 0; x < 64; x++)
          if (x >= x0 && x < x0 + w) {
            const float m = yy == y + 1 ? 1.15f : yy == y + hh - 1 ? 0.8f : 1.0f;
            for (int j = 0; j < 3; j++) alb[(yy * 64 + x) * 3 + j] = c[j] * m;
          }
      const int cxa = (int)ceilf(x0) + 1, cxb = (int)ceilf(x0 + w) - 1;
      for (int cy : {y + 1, y + hh - 1})                // des coins arrondis
        for (int cx : {cxa, cxb})
          if (cy >= 0 && cy < 64 && cx >= 0 && cx < 64) mq[cy * 64 + cx] |= 1;
      const int xc = (int)ceilf(x0);
      if (xc >= 0 && xc < 64)
        for (int yy = y; yy < min(64, y + hh); yy++) mq[yy * 64 + xc] |= 1;
      x0 += w;
    }
    for (int x = 0; x < 64; x++) mq[y * 64 + x] |= 1;
    y += hh;
  }
  brume_n(e.tmp, 64, 1);
  for (int i = 14 * 64; i < 4096; i++) {
    const float m = 0.85f + 0.3f * e.tmp[i] / 65535.0f;
    for (int j = 0; j < 3; j++) alb[3 * i + j] *= m;
    if (mq[i] & 1) { alb[3 * i] = 44; alb[3 * i + 1] = 38; alb[3 * i + 2] = 34; }
  }
  auto poser_alb = [&](int yy, int xx, float r, float v, float b) {
    float *p = alb + (yy * 64 + xx) * 3; p[0] = r; p[1] = v; p[2] = b;
  };
  for (int yy = 8; yy <= 13; yy++)                       // le manteau, une poutre
    for (int x = 0; x < 64; x++) {
      const float k = 0.82f + 0.18f * sinf(x * 0.7f + sinf(yy * 1.9f) * 2);
      if (yy == 8) poser_alb(yy, x, 120, 76, 44);
      else if (yy == 13) poser_alb(yy, x, 60, 36, 20);
      else poser_alb(yy, x, 84 * k, 50 * k, 28 * k);
    }
  for (int yy = 0; yy < 64; yy++)                         // sur le manteau : une pendule, un vase, un cadre
    for (int x = 0; x < 64; x++) {
      const float px = (x - 32) / 3.2f, py = (yy - 3.2f) / 2.4f;
      const bool pendule = (abs(x - 32) <= 3 && yy >= 3 && yy <= 7) || px * px + py * py <= 1;
      const bool vase = (cr_hypot(x - 12.0f, (yy - 5.5f) * 1.2f) <= 2.2f || (fabsf(x - 12.0f) <= 0.8f && yy >= 2 && yy <= 4)) && yy <= 7;
      const bool cadre = x >= 48 && x <= 54 && yy >= 2 && yy <= 7;
      if (pendule) poser_alb(yy, x, 92, 58, 34);
      if (cr_hypot(x - 32.0f, yy - 3.6f) <= 1.7f) poser_alb(yy, x, 200, 186, 150);
      if (vase) poser_alb(yy, x, 70, 96, 104);
      if (cadre) poser_alb(yy, x, 130, 100, 56);
      if (x >= 49 && x <= 53 && yy >= 3 && yy <= 6) poser_alb(yy, x, 56, 60, 70);
      if (pendule || vase || cadre) mq[yy * 64 + x] |= 2;
    }
  poser_alb(3, 32, 60, 40, 30);
  static const int8_t branches[5][2] = {{10, 0}, {11, 1}, {13, 0}, {14, 1}, {12, 0}};   // quelques branches seches
  for (auto &b : branches) { poser_alb(b[1], b[0], 110, 80, 50); mq[b[1] * 64 + b[0]] |= 2; }
  for (int x = 0; x < 64; x++) {
    const float u = (x - 32) / 18.5f;
    e.haut_ouv[x] = 22 + 4.5f * u * u * u * u;
  }
  for (int yy = 58; yy < 64; yy++)
    for (int x = 0; x < 64; x++) {
      if (abs(x - 32) <= 30) { if (yy >= 60) poser_alb(yy, x, 96, 86, 78); else poser_alb(yy, x, 150, 136, 122); }
      else poser_alb(yy, x, 16, 12, 11);
    }
  // la lumiere de la piece : base + vif * vive ; dans l'atre, son fond noirci
  static const float B5[5] = {1 / 16.0f, 4 / 16.0f, 6 / 16.0f, 4 / 16.0f, 1 / 16.0f};
  static const float chaud[3] = {1.55f, 0.78f, 0.36f}, k0[3] = {0.11f, 0.1f, 0.11f};
  for (int yy = 0; yy < 64; yy++)
    for (int x = 0; x < 64; x++) {
      const int i = yy * 64 + x;
      float b[3], v[3];
      if (cr_ouverture(e.haut_ouv[x], x, yy)) {
        const float k = cr_clip01((yy - 22) / 35.0f);
        float f[3] = {12 + 12 * k, 7 + 6 * k, 6 + 3 * k};
        if (yy % 3 == 0 || (x + ((yy / 3) % 2) * 3) % 6 == 0) for (int j = 0; j < 3; j++) f[j] *= 0.7f;
        const float jo = cr_clip01(fabsf(x - 32.0f) / 18.5f), m = 1 - 0.6f * jo * jo * jo;
        const float li = expf(-cr_hypot(x - 32.0f, (yy - 49) * 1.3f) / 9.0f);
        for (int j = 0; j < 3; j++) { b[j] = f[j] * m * 0.6f; v[j] = f[j] * m * li * 3.2f * chaud[j]; }
        mq[i] |= 4;
      } else {
        float pres = 0;                                   // les pierres au bord de l'atre (le flou de l'ouverture)
        for (int a = -2; a <= 2; a++)
          for (int c = -2; c <= 2; c++) {
            const int ya = yy + a, xc = x + c;
            if (ya >= 0 && ya < 64 && xc >= 0 && xc < 64 && cr_ouverture(e.haut_ouv[xc], xc, ya)) pres += B5[a + 2] * B5[c + 2];
          }
        const float d = cr_hypot((x - 32) * 0.75f, (yy - 46) * 0.95f);
        const float lp = expf(-d / 13.0f) + 0.3f * expf(-d / 34.0f) + pres * 1.3f + (yy == 13) * 0.35f
                         + ((mq[i] & 2) ? 0.3f : 0.0f) + (yy < 8) * 0.08f;
        for (int j = 0; j < 3; j++) { b[j] = alb[3 * i + j] * k0[j]; v[j] = alb[3 * i + j] * lp * chaud[j]; }
      }
      for (int j = 0; j < 3; j++) {
        e.base[i][j] = (uint16_t)cr_min(65535.0f, b[j] * 32 + 0.5f);
        e.vive[i][j] = (uint16_t)cr_min(65535.0f, v[j] * 32 + 0.5f);
      }
    }
  // le lit de braises
  brume_n(e.tmp, 64, 1);
  e.nbraise = 0;
  for (int yy = 54; yy <= 57; yy++)
    for (int x = 14; x <= 50; x++) {
      const float u = (x - 32) / 17.0f;
      if (yy >= 54.5f + 2 * u * u && e.nbraise < 160)
        e.braise[e.nbraise++] = {(uint16_t)(yy * 64 + x), cr_clip01((e.tmp[yy * 64 + x] / 65535.0f - 0.28f) * 1.9f)};
    }
  brume_n(e.souffle, 64, 5);
  brume_n(e.flamA, 64, 5);
  brume_n(e.flamB, 64, 2);
  // les buches : leur ecorce, leurs fentes, leur bout coupe et ses cernes
  brume_n(e.tmp, 64, 1);
  e.necorce = 0;
  for (int b = 0; b < 3; b++) {
    e.debut_buche[b] = e.necorce;
    const float ax = CR_BUCHES[b][0], ay = CR_BUCHES[b][1], bx = CR_BUCHES[b][2], by = CR_BUCHES[b][3], r = CR_BUCHES[b][4];
    const float vx = bx - ax, vy = by - ay, l2 = vx * vx + vy * vy, l = sqrtf(l2);
    for (int yy = 40; yy < 64; yy++)
      for (int x = 0; x < 64; x++) {
        const float u = cr_clip01(((x - ax) * vx + (yy - ay) * vy) / l2);
        const float px = x - (ax + u * vx), py = yy - (ay + u * vy), d = cr_hypot(px, py);
        const float rb = cr_hypot((x - ax) * 1.25f, yy - ay) / r;
        const bool bout = rb * r <= r * 1.02f;
        if (!(d <= r || bout) || e.necorce >= 640) continue;
        const float ny = cr_max(-1.0f, cr_min(1.0f, py / r));
        const float cyl = sqrtf(cr_clip01(1 - (d / r) * (d / r)));
        const float sillons = 0.75f + 0.25f * sinf(ny * 5.5f + sinf(u * l * 0.35f) * 1.3f);   // l'ecorce, en long
        const float k = (0.35f + 0.65f * cyl) * sillons;
        CR_Ecorce &c = e.ecorce[e.necorce++];
        c.i = (uint16_t)(yy * 64 + x);
        c.buche = (uint8_t)b;
        c.ny = (int8_t)lrintf(ny * 127);
        c.rb = (uint8_t)cr_min(255.0f, rb * 200 + 0.5f);
        c.ec[0] = (uint8_t)(74 * k + 0.5f); c.ec[1] = (uint8_t)(44 * k + 0.5f); c.ec[2] = (uint8_t)(24 * k + 0.5f);
        c.drapeaux = 0;
        if (e.tmp[c.i] > 0.66f * 65535 && ny > 0.05f && d <= r) c.drapeaux |= 1;
        if (bout) {
          c.drapeaux |= 2;
          if (fabsf(rb - 0.55f) < 0.17f || rb < 0.15f) c.drapeaux |= 4;
        }
      }
  }
  e.debut_buche[3] = e.necorce;
}

void cr_buche(E_cheminee &e, int b, float vif, const cr_Fen &souffle) {
  for (int n = e.debut_buche[b]; n < e.debut_buche[b + 1]; n++) {
    const CR_Ecorce &c = e.ecorce[n];
    const int y = c.i >> 6, x = c.i & 63;
    float col[3];
    if (c.drapeaux & 2) {                                // le bout coupe, clair, et ses cernes
      const float k = (0.75f + 0.25f * vif) * (1.05f - 0.35f * c.rb / 200.0f) * ((c.drapeaux & 4) ? 0.6f : 1.0f);
      col[0] = 170 * k; col[1] = 110 * k; col[2] = 62 * k;
    } else {
      const float so = cr_lire(souffle, x, y);
      if (c.drapeaux & 1) {
        const float k = 0.3f + 0.7f * so;
        col[0] = 255 * k; col[1] = 110 * k; col[2] = 25 * k;
      } else {
        const float ny = c.ny / 127.0f;
        const float dessus = cr_clip01(-ny - 0.2f) * vif * 0.85f, dessous = cr_clip01(ny - 0.2f) * so * 0.55f;
        col[0] = c.ec[0] + dessus * 255 + dessous * 255;
        col[1] = c.ec[1] + dessus * 125 + dessous * 80;
        col[2] = c.ec[2] + dessus * 45 + dessous * 15;
      }
    }
    peindre(y, x, col[0], col[1], col[2]);
  }
}

void s_cheminee(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cheminee &e = etat_ecran<E_cheminee>(debut);
  (void)humeur; (void)ecoule;
  if (debut) cr_cheminee_preparer(e);
  const float vif = 0.84f + 0.07f * sinf(t * 2.3f) + 0.05f * sinf(t * 3.7f + 1.3f) + 0.04f * sinf(t * 6.1f + 0.4f);
  for (int i = 0; i < 4096; i++) {
    const uint16_t *b = e.base[i], *v = e.vive[i];
    float *p = &scene[0][0][0] + 3 * i;
    p[0] = (b[0] + vif * v[0]) * (1 / 32.0f);
    p[1] = (b[1] + vif * v[1]) * (1 / 32.0f);
    p[2] = (b[2] + vif * v[2]) * (1 / 32.0f);
  }
  const cr_Fen souffle = cr_fen(e.souffle, 64, t * 2.2f, t * 1.4f);   // les braises respirent, par vagues
  for (int n = 0; n < e.nbraise; n++) {
    const int y = e.braise[n].i >> 6, x = e.braise[n].i & 63;
    float c[3];
    cr_palette_cocon(CR_FEU_PAS, CR_FEU, 6, e.braise[n].b * (0.35f + 0.8f * cr_lire(souffle, x, y)) * 0.85f, c);
    peindre(y, x, c[0] + 34, c[1] + 6, c[2] + 2);
  }
  cr_buche(e, 0, vif, souffle);
  // les flammes : des langues qui montent des buches, rongees par un bruit qui file vers le haut
  float haut[64];
  for (int x = 0; x < 64; x++) haut[x] = 0;
  static const float langues[5][3] = {{21, 14, 3.2f}, {26, 22, 3.6f}, {31.5f, 27, 4.0f}, {37, 21, 3.6f}, {42.5f, 14, 3.2f}};
  for (int j = 0; j < 5; j++) {
    const float c = langues[j][0] + 1.5f * sinf(t * (0.5f + 0.13f * j) + j * 1.7f);
    const float hj = langues[j][1] * (0.74f + 0.15f * sinf(t * (1.7f + 0.31f * j) + j * 2.3f) + 0.11f * sinf(t * (3.9f + 0.43f * j) + j));
    const float iw = 1.0f / langues[j][2];
    for (int x = 0; x < 64; x++) {
      const float u = (x - c) * iw;
      if (u * u < 30) haut[x] = cr_max(haut[x], hj * cr_exp(-u * u));
    }
  }
  const cr_Fen n1 = cr_fen(e.flamA, 64, 10 + sinf(t * 0.3f) * 4, 30 + t * 15);
  const cr_Fen n2 = cr_fen(e.flamB, 64, 50, 70 + t * 24);
  for (int y = 18; y < 54; y++) {
    const float hgt = 50.5f - y;
    const float decal = (1.3f * cr_sin(y * 0.42f + t * 3.1f) + 0.6f * cr_sin(y * 0.9f - t * 5.3f)) * cr_clip01(hgt / 14);
    for (int x = 13; x < 52; x++) {
      if (!cr_ouverture(e.haut_ouv[x], x, y)) continue;
      float xd = x + decal;                              // np.interp : borne aux deux bouts
      xd = cr_max(0.0f, cr_min(63.0f, xd));
      const int xi = min(62, (int)xd);
      const float hx = haut[xi] + (haut[xi + 1] - haut[xi]) * (xd - xi);
      if (hx <= 0) continue;
      const float r = hgt / (hx + 0.6f);
      const float f = (1 - r) * 1.25f - (0.55f * cr_lire(n1, x, y) + 0.45f * cr_lire(n2, x, y)) * (0.25f + 0.9f * cr_clip01(r));
      const float flamme = cr_clip01(f) * cr_clip01(hx / 7);
      if (flamme <= 0) continue;
      float c[3];
      cr_palette_cocon(CR_FEU_PAS, CR_FEU, 6, flamme * 0.97f, c);
      const float k = 1 - 0.5f * cr_clip01(flamme * 2);
      float *z = scene[y][x];
      z[0] = z[0] * k + c[0]; z[1] = z[1] * k + c[1]; z[2] = z[2] * k + c[2];
    }
  }
  cr_buche(e, 1, vif, souffle);
  cr_buche(e, 2, vif, souffle);
  // des etincelles qui montent en voletant, s'eteignent, et repartent des buches
  if (debut)
    for (auto &s : e.etin) {
      const float vie = hasard(1.2f, 2.6f), age = hasard(0, 1) * vie, vy = -hasard(8, 15);
      s[0] = hasard(22, 42); s[1] = hasard(45, 49) + vy * age; s[2] = vy; s[3] = age; s[4] = vie; s[5] = hasard(0, 6);
    }
  float reste = cr_min(dt, 1.0f);
  while (reste > 1e-6f) {
    const float hp = cr_min(reste, 0.05f), amorti = expf(-hp * 0.35f);
    reste -= hp;
    for (auto &s : e.etin) {
      s[0] += sinf(s[3] * 3.1f + s[5]) * 5.0f * hp;
      s[1] += s[2] * hp;
      s[2] *= amorti;
      s[3] += hp;
    }
  }
  for (auto &s : e.etin)
    if (s[3] >= s[4]) { s[0] = hasard(22, 42); s[1] = hasard(45, 49); s[2] = -hasard(8, 15); s[3] = 0; s[4] = hasard(1.2f, 2.6f); s[5] = hasard(0, 6); }
  for (auto &s : e.etin) {
    const float vie = cr_clip01((1 - s[3] / s[4]) * 2.5f) * (0.85f + 0.15f * sinf(s[3] * 9 + s[5]));
    const int xi = max(0, min(63, (int)s[0]));
    if (!(s[1] > e.haut_ouv[xi] + 1)) continue;
    pointer(s[1] + 1, s[0], vie * 200, vie * 90, vie * 30);   // une courte trainee
    pointer(s[1], s[0], vie * 255, vie * 205, vie * 120);
  }
}

// --- le the sous la pluie ----------------------------------------------------------------------------------------

static const float CR_THE_LUMIERES[5][3] = {{255, 170, 70}, {255, 214, 160}, {70, 190, 215}, {255, 96, 120}, {150, 130, 255}};

// humeurs : 0 = (une seule ambiance)
struct E_the {
  uint8_t coul[4096][3];                   // la ville floue derriere la vitre, ou la couleur fixe (l'interieur)
  uint8_t fixe[4096];                      // 1 : l'interieur, la lampe, la tasse (rien n'y bouge)
  float halo[4096];                        // la lumiere de la lampe
  uint16_t buee[4096], volutes[4096];
  float trace[44 * 64];                    // ou les gouttes qui glissent ont nettoye la buee
  float bx[13], by[13], br[13], bc[13][3], bp[13];   // les lumieres floues de la ville
  float gx[16], gy[16], gl[16];            // les gouttes posees sur la vitre
  float glisse[3][4], prochaine;
  int nglisse;
  Pluie pluie;
};

void cr_the_preparer(E_the &e) {
  float *d = &scene[0][0][0];                            // dehors, le temps du semis
  float toits[64];
  for (int x = 0; x < 64; x++) toits[x] = 64;
  int x0 = -3;
  while (x0 < 64) {                                      // des immeubles au loin
    const int l = 5 + (int)(aleatoire() % 6);
    const float h = hasard(15, 30);
    for (int x = max(0, x0); x < min(64, max(0, x0 + l)); x++) toits[x] = h;
    x0 += l;
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float *p = d + (y * 64 + x) * 3;
      const float k = cr_clip01(y / 43.0f);              // le ciel de ville, plus clair en bas
      p[0] = 7 + 27 * k; p[1] = 9 + 15 * k; p[2] = 24 + 22 * k;
      if (y >= toits[x]) {
        p[0] = 14 + (y - 16) * 0.3f; p[1] = 13 + (y - 16) * 0.2f; p[2] = 28 + (y - 16) * 0.3f;
        const bool fen = y % 3 == 0 && x % 3 == 1 && hasard(0, 1) < 0.35f;
        const bool chaude = hasard(0, 1) < 0.75f;
        if (fen) {
          if (chaude) { p[0] = 200; p[1] = 140; p[2] = 70; }
          else { p[0] = 110; p[1] = 150; p[2] = 190; }
        }
      }
    }
  cr_flou_cocon(d, 3, 2);                                // tout est flou, derriere la buee
  for (int i = 0; i < 13; i++) {
    e.bx[i] = hasard(4, 62); e.by[i] = hasard(20, 43); e.br[i] = hasard(2.0f, 4.2f);
    const float *c = CR_THE_LUMIERES[aleatoire() % 5];
    const float k = hasard(0.3f, 0.5f);
    for (int j = 0; j < 3; j++) e.bc[i][j] = c[j] * k;
    e.bp[i] = hasard(0, 6);
  }
  brume_n(e.buee, 64, 4);
  brume_n(e.volutes, 64, 3);
  const float cx = 42.5f, haut = 42.0f, bas = 53.0f, hw = 5.6f;
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const float halo = expf(-cr_hypot(x - 12.0f, (y - 32) * 1.1f) / 11.0f);
      e.halo[i] = halo;
      const float b = cr_clip01(0.3f + 0.5f * e.buee[i] / 65535.0f + 0.3f * cr_clip01((y - 20) / 23.0f));
      e.buee[i] = (uint16_t)(b * 65535 + 0.5f);
      const bool vitre = y <= 43 && x >= 3;
      const bool cadre = y <= 43 && (x <= 2 || (x >= 27 && x <= 28) || (y >= 15 && y <= 16));
      // l'interieur : le cadre, le rebord profond (vu d'en haut), son chant, le mur dessous
      float c[3] = {0, 0, 0};
      const float lum_r = 0.1f + 1.25f * expf(-cr_hypot((x - 12) * 0.85f, (y - 47) * 1.2f) / 10.0f)
                          + 0.35f * expf(-cr_hypot(x - 20.0f, y - 50.0f) / 22.0f);
      if (cadre) {
        const float k = (0.9f + 0.1f * sinf(x * 0.8f + y * 0.3f)) * (0.25f + 0.9f * halo);
        c[0] = 70 * k; c[1] = 42 * k; c[2] = 24 * k;
      }
      if (y >= 44 && y <= 55) {
        const float k = (0.9f + 0.1f * sinf(y * 2.6f + sinf(x * 0.2f) * 1.5f)) * lum_r * (y == 44 ? 0.55f : 1.0f);
        c[0] = 118 * k; c[1] = 74 * k; c[2] = 42 * k;
        const float ox = (x - 52) / 8.0f, oy = (y - 53) / 2.2f;
        if (ox * ox + oy * oy <= 1) for (int j = 0; j < 3; j++) c[j] *= 0.5f;   // l'ombre de la tasse
      }
      if (y >= 56 && y <= 58) {
        const float k = 0.75f * lum_r * (y == 56 ? 1.3f : 1.0f);
        c[0] = 84 * k; c[1] = 52 * k; c[2] = 30 * k;
      }
      if (y >= 59) {
        const float k = 0.18f + 0.4f * expf(-cr_hypot(x - 12.0f, y - 52.0f) / 12.0f);
        c[0] = 40 * k; c[1] = 26 * k; c[2] = 22 * k;
      }
      static const float livres[2][6] = {{52, 50, 54, 34, 74, 70}, {54, 46, 49, 118, 34, 34}};   // deux livres, dans le coin
      for (auto &l : livres)
        if (x >= l[0] && y >= l[1] && y <= l[2]) {
          float k[3] = {l[3], l[4], l[5]};
          if (y == l[1]) { k[0] = 150; k[1] = 130; k[2] = 100; }   // la tranche des pages, vue d'en haut
          else if (y == l[1] + 2 && x > l[0] + 1) { k[0] = l[3] * 0.6f + 90; k[1] = l[4] * 0.6f + 70; k[2] = l[5] * 0.6f + 20; }
          const float m = lum_r * 1.1f + 0.08f;
          for (int j = 0; j < 3; j++) c[j] = k[j] * m;
        }
      // la lampe, au fond du rebord : un abat-jour qui luit, un pied fin
      const float rel = (y - 27) / 8.0f;
      const bool abat = rel >= 0 && rel <= 1 && fabsf(x - 12.0f) <= 3.5f + rel * 2.6f;
      const float px = (x - 12) / 3.2f, py = (y - 46.3f) / 1.1f;
      const bool pied = (fabsf(x - 12.0f) < 0.6f && y > 35 && y < 46) || px * px + py * py <= 1;
      const bool interieur = !vitre || cadre;
      if (abat) {
        const float k = (0.55f + 0.45f * rel) * (0.92f + 0.08f * sinf(x * 1.9f));
        c[0] = 255 * k; c[1] = 172 * k; c[2] = 88 * k;
      }
      if (pied) { c[0] = 60; c[1] = 40; c[2] = 24; }
      for (int j = 0; j < 3; j++) c[j] += halo * 0.22f * (j == 0 ? 255 : j == 1 ? 160 : 80);
      // la tasse, devant : un cylindre creme eclaire de la gauche, son anse, sa soucoupe, le the dedans
      const float xn = (x - cx) / hw;
      const float lam = cr_clip01(-0.75f * xn + 0.66f * sqrtf(cr_clip01(1 - xn * xn)));
      static const float creme[3] = {232, 214, 186};
      const bool corps = fabsf(xn) <= 1 && y >= haut && y <= bas;
      float an = (x - (cx + hw + 1.4f)) / 2.9f, an2 = (y - 47) / 3.1f;
      an = an * an + an2 * an2;
      const bool anse = an <= 1 && an >= 0.3f && x > cx + hw - 0.5f;
      const float su = (x - cx) / 8.6f, sv = (y - bas - 0.4f) / 1.5f;
      const bool soucoupe = su * su + sv * sv <= 1 && !corps;
      const float bv = (y - haut) / 1.45f;
      const bool bord = xn * xn + bv * bv <= 1;
      const float tu = (x - cx) / (hw - 1.1f), tv = (y - haut) / 0.8f;
      const bool the = tu * tu + tv * tv <= 1;
      if (corps) {
        const float k = 0.12f + 0.66f * lam - 0.06f * (y - haut) / (bas - haut);
        for (int j = 0; j < 3; j++) c[j] = creme[j] * k;
        if (fabsf(xn + 0.45f) < 0.1f && y >= haut + 1 && y <= bas - 3) for (int j = 0; j < 3; j++) c[j] = creme[j] * 0.97f;
      } else if (anse || soucoupe || bord || the) {
        for (int j = 0; j < 3; j++) c[j] = 0;
      }
      if (anse) for (int j = 0; j < 3; j++) c[j] = creme[j] * 0.2f;
      if (soucoupe) { const float k = 0.16f + 0.42f * cr_clip01(-(x - cx) / 8.6f + 0.5f); for (int j = 0; j < 3; j++) c[j] = creme[j] * k; }
      if (bord) { const float k = 0.32f + 0.55f * cr_clip01(0.6f - xn); for (int j = 0; j < 3; j++) c[j] = creme[j] * k; }
      if (the) { c[0] = 96; c[1] = 46; c[2] = 16; }
      if (y == (int)haut && x == (int)cx - 2) { c[0] = 220; c[1] = 150; c[2] = 80; }   // la lampe dans le the
      const bool objet = corps || anse || soucoupe || bord;
      e.fixe[i] = interieur || abat || pied || objet;
      if (e.fixe[i]) for (int j = 0; j < 3; j++) e.coul[i][j] = (uint8_t)cr_min(255.0f, c[j] + 0.5f);
      else for (int j = 0; j < 3; j++) e.coul[i][j] = (uint8_t)cr_min(255.0f, d[3 * i + j] + 0.5f);
    }
  for (int i = 0; i < 16; i++) { e.gx[i] = hasard(4, 62); e.gy[i] = hasard(1, 42); e.gl[i] = hasard(0.35f, 0.7f); }
  semer_pluie(e.pluie, 40);
}

void s_the(int humeur, bool debut, float t, float ecoule, float dt) {
  E_the &e = etat_ecran<E_the>(debut);
  (void)humeur;
  if (debut) cr_the_preparer(e);
  for (int i = 0; i < 4096; i++) {                        // la ville, derriere la vitre
    float *p = &scene[0][0][0] + 3 * i;
    p[0] = e.coul[i][0]; p[1] = e.coul[i][1]; p[2] = e.coul[i][2];
  }
  for (int i = 0; i < 13; i++) {                         // les lumieres floues qui respirent
    const float w = 0.8f + 0.2f * sinf(t * 0.4f + e.bp[i]);
    const float r = e.br[i];
    for (int y = max(0, (int)(e.by[i] - r) - 1); y <= min(63, (int)(e.by[i] + r) + 1); y++)
      for (int x = max(0, (int)(e.bx[i] - r) - 1); x <= min(63, (int)(e.bx[i] + r) + 1); x++) {
        const float k = cr_clip01((r - cr_hypot(x - e.bx[i], y - e.by[i])) / 1.4f) * w;
        if (k > 0) ajouter(y, x, k, e.bc[i][0], e.bc[i][1], e.bc[i][2]);
      }
  }
  static const float voitures[2][6] = {{23.0f, 38.0f, 1, 255, 225, 170}, {31.0f, 40.5f, -1, 255, 60, 50}};
  for (auto &v : voitures) {                              // une voiture passe, en bas, de temps en temps
    const float k = fmodf(t / v[0], 1.0f);
    const float xv = v[2] > 0 ? -12 + k * 100 : 76 - k * 100;
    for (float dx : {0.0f, 5.0f}) {
      const float cxv = xv + dx;
      if (cxv < -3 || cxv > 67) continue;
      for (int y = (int)v[1] - 3; y <= (int)v[1] + 3; y++)
        for (int x = max(0, (int)cxv - 3); x <= min(63, (int)cxv + 3); x++) {
          const float a = cr_clip01((2.4f - cr_hypot(x - cxv, y - v[1])) / 1.3f) * 0.42f;
          if (a > 0) ajouter(y, x, a, v[3], v[4], v[5]);
        }
    }
  }
  pluie(e.pluie, dt, 46, 52, 78, 0.12f);
  // la buee : elle voile et eclaircit la ville ; la lampe l'eclaire ; les gouttes qui glissent la nettoient
  const float pas = cr_min(dt, 1.0f), efface = expf(-pas / 18.0f);
  for (int i = 0; i < 44 * 64; i++) e.trace[i] = cr_efface(e.trace[i], efface);
  if (ecoule >= e.prochaine && e.nglisse < 3) {
    e.prochaine = ecoule + hasard(2.5f, 7.0f);
    float *g = e.glisse[e.nglisse++];
    g[0] = hasard(5, 62); g[1] = hasard(2, 24); g[2] = hasard(3.5f, 7.0f); g[3] = hasard(0, 6);
  }
  int restent = 0;
  for (int n = 0; n < e.nglisse; n++) {
    float *g = e.glisse[n];
    const float y0 = g[1];
    g[1] += g[2] * pas;
    g[0] += sinf(g[1] * 0.6f + g[3]) * 0.08f;
    const int col = (((int)lrintf(g[0])) % 64 + 64) % 64;
    for (int y = max(0, (int)y0); y <= min(43, (int)g[1]); y++) e.trace[y * 64 + col] = 1.0f;
    if (g[1] < 43) for (int j = 0; j < 4; j++) e.glisse[restent][j] = g[j];
    if (g[1] < 43) restent++;
  }
  e.nglisse = restent;
  for (int i = 0; i < 4096; i++) {
    float *p = &scene[0][0][0] + 3 * i;
    if (e.fixe[i]) { p[0] = e.coul[i][0]; p[1] = e.coul[i][1]; p[2] = e.coul[i][2]; continue; }
    const float b = e.buee[i] * (1.0f / 65535.0f) * (i < 44 * 64 ? 1 - 0.8f * e.trace[i] : 1.0f);
    const float h = e.halo[i], k = 1 - 0.6f * b;
    p[0] = p[0] * k + (18 + h * 93.5f) * b + h * 56.1f;
    p[1] = p[1] * k + (18 + h * 57.75f) * b + h * 35.2f;
    p[2] = p[2] * k + (28 + h * 33.0f) * b + h * 17.6f;
  }
  for (int i = 0; i < 16; i++) {                         // les gouttes posees sur la vitre
    const int y = (int)e.gy[i], x = (int)e.gx[i];
    if (e.fixe[y * 64 + x]) continue;
    const float h = e.halo[y * 64 + x], g = e.gl[i];
    pointer(y, x, g * (70 + h * 200) + h * 56.1f, g * (72 + h * 130) + h * 35.2f, g * (90 + h * 70) + h * 17.6f);
  }
  for (int n = 0; n < e.nglisse; n++)
    for (int k = 0; k < 2; k++) {
      const int y = (int)(e.glisse[n][1] + k), x = (int)e.glisse[n][0];
      if (y < 0 || y > 63 || x < 0 || x > 63 || e.fixe[y * 64 + x]) continue;
      const float h = e.halo[y * 64 + x];
      if (k == 0) pointer(y, x, 150 + h * 56.1f, 155 + h * 35.2f, 175 + h * 17.6f);
      else pointer(y, x, 90 + h * 56.1f, 95 + h * 35.2f, 120 + h * 17.6f);
    }
  // la vapeur : deux volutes qui montent en ondulant, s'elargissent et s'effacent
  const cr_Fen vol = cr_fen(e.volutes, 64, 7, 40 + t * 3.1f);
  static const float volutes[2][3] = {{41.0f, 0.0f, 3.4f}, {44.0f, 2.1f, 2.9f}};
  float derive[2], respire[2];
  for (int j = 0; j < 2; j++) { derive[j] = sinf(t * 0.11f + j * 2); respire[j] = 0.75f + 0.25f * sinf(t * 0.3f + j * 1.3f); }
  for (int y = 2; y <= 41; y++) {
    const float hh = 41.5f - y;
    float xc[2], iw[2], k[2];
    int xa = 62, xb = 23;
    for (int j = 0; j < 2; j++) {
      const float phase = hh - volutes[j][2] * t;
      xc[j] = volutes[j][0] + (0.4f + hh * 0.12f) * sinf(phase * 0.26f + volutes[j][1]) + hh * 0.07f * derive[j];
      const float w = 0.9f + hh * 0.05f;
      iw[j] = 1.0f / w;
      const float bouffee = cr_max(cr_clip01(0.35f + 0.8f * sinf(phase * 0.3f + volutes[j][1] * 1.7f)), cr_clip01(1 - hh / 6) * 0.85f);
      k[j] = cr_clip01(hh / 2.0f) * expf(-hh / 15.0f) * bouffee * respire[j];
      if (k[j] > 0) { xa = min(xa, (int)(xc[j] - 4.5f * w)); xb = max(xb, (int)(xc[j] + 4.5f * w) + 1); }
    }
    for (int x = max(24, xa); x <= min(61, xb); x++) {
      float v = 0;
      for (int j = 0; j < 2; j++) {
        const float u = (x - xc[j]) * iw[j];
        if (k[j] > 0 && u * u < 20) v += k[j] * cr_exp(-u * u);
      }
      if (v <= 1e-4f) continue;
      v = cr_min(1.3f, v * (0.55f + 0.6f * cr_lire(vol, x, y))) * 1.1f;
      ajouter(y, x, v, 215, 200, 185);
    }
  }
}

// --- la poussiere dans la lumiere --------------------------------------------------------------------------------

static const float CR_FENETRE[4] = {7.0f, 6.0f, 16.0f, 23.0f};     // la vitre : x, y, largeur, hauteur

// la vitre laisse-t-elle passer le soleil en (x, y) ?
inline bool cr_jour(float x, float y) {
  if (!(x >= 7 && x < 23 && y >= 6 && y < 29)) return false;
  if ((x >= 14 && x < 16) || (y >= 16 && y < 18)) return false;   // le croisillon
  const float dx = x - 19.5f;                            // un vase a long col, sur l'appui
  if (cr_hypot(dx, (y - 25.6f) * 1.1f) <= 2.5f || (fabsf(dx) <= 0.8f && y >= 20.5f) || (fabsf(dx) <= 1.3f && y >= 20.2f && y < 21.2f))
    return false;
  return true;
}

// la n-ieme plus petite valeur (quickselect, en place)
float cr_nieme(float *a, int n, int k) {
  int g = 0, d = n - 1;
  while (g < d) {
    const float pivot = a[(g + d) / 2];
    int i = g, j = d;
    while (i <= j) {
      while (a[i] < pivot) i++;
      while (a[j] > pivot) j--;
      if (i <= j) { const float c = a[i]; a[i] = a[j]; a[j] = c; i++; j--; }
    }
    if (k <= j) d = j;
    else if (k >= i) g = i;
    else return a[k];
  }
  return a[k];
}

// humeurs : 0 = (une seule ambiance)
struct E_poussiere {
  uint16_t piece[4096][3];                 // la piece (x 256)
  uint16_t lum0[4096];                     // clarte + 2.2 tache + 0.9 rebond (x 16384)
  uint16_t tache[4096];                    // la tache de soleil au sol (x 65535)
  int16_t dtache[4096];                    // tache douce - tache (x 32767)
  uint16_t rayon[4096];                    // le rayon (x 50000)
  int16_t drayon[4096];                    // rayon doux - rayon (x 27000)
  uint8_t drapeaux[4096];                  // 1 la vitre, 2 le rideau
  float puiss[257];                        // x^0.9 sur [0, 1.2]
  float g[130][7];                         // les poussieres
};

void cr_poussiere_preparer(E_poussiere &e) {
  float *ray = &scene[0][0][0], *tmp = ray + 4096, *tmp2 = ray + 8192;
  for (int i = 0; i < 4096; i++) ray[i] = 0;
  // le rayon : chaque point de la vitre, tire jusqu'a sa tache au sol ; ce qui s'empile fait la densite
  for (int iv = 0; iv < 80; iv++)
    for (int iu = 0; iu < 56; iu++) {
      const float u = iu / 55.0f, v = iv / 79.0f;
      const float wx = 7 + u * 16, wy = 6 + v * 23;
      if (!cr_jour(wx, wy)) continue;
      const float fy = 62 - v * 15, fx = 22 + (fy - 47) * 0.9f + u * (15 + (fy - 47) * 0.6f);
      for (int k = 0; k < 40; k++) {
        const float s = 0.02f + 0.96f * k / 39.0f;
        cr_tamponner1(ray, wy + s * (fy - wy), wx + s * (fx - wx), 1.0f);
      }
    }
  cr_flou_cocon(ray, 1, 1);
  int n = 0;
  for (int i = 0; i < 4096; i++) if (ray[i] > 0) tmp2[n++] = ray[i];   // np.percentile(rayon[rayon > 0], 92)
  const float pos = 0.92f * (n - 1);
  const int lo = (int)pos;
  const float a = cr_nieme(tmp2, n, lo), b = lo + 1 < n ? cr_nieme(tmp2, n, lo + 1) : a;
  const float p92 = a + (b - a) * (pos - lo);
  for (int i = 0; i < 4096; i++) ray[i] = cr_min(1.2f, cr_max(0.0f, ray[i] / p92));
  for (int i = 0; i < 4096; i++) tmp[i] = ray[i];
  cr_flou_cocon(tmp, 1, 2);                              // le rayon doux (sous un nuage)
  for (int i = 0; i < 4096; i++) {
    e.rayon[i] = (uint16_t)(ray[i] * 50000 + 0.5f);
    e.drayon[i] = (int16_t)lrintf((tmp[i] - ray[i]) * 27000);
  }
  // la tache au sol : pour chaque pixel du plancher, le point de la vitre qu'il voit (sur-echantillonne)
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float s = 0;
      for (int oy = -1; oy <= 1; oy++)
        for (int ox = -1; ox <= 1; ox++) {
          const float yy = y + oy * 0.33f, xx = x + ox * 0.33f;
          if (yy < 44) continue;
          const float vv = (62 - yy) / 15, x0 = 22 + (yy - 47) * 0.9f;
          const float uu = (xx - x0) / cr_max(15 + (yy - 47) * 0.6f, 1.0f);
          s += cr_jour(7 + uu * 16, 6 + vv * 23) ? 1.0f / 9 : 0.0f;
        }
      ray[y * 64 + x] = s;
    }
  for (int i = 0; i < 4096; i++) tmp[i] = ray[i];
  cr_flou_cocon(tmp, 1, 1);                              // la tache douce
  for (int i = 0; i < 4096; i++) {
    e.tache[i] = (uint16_t)(ray[i] * 65535 + 0.5f);
    e.dtache[i] = (int16_t)lrintf((tmp[i] - ray[i]) * 32767);
  }
  cr_flou_cocon(ray, 1, 6);                              // le rebond, partout
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const float clarte = 0.5f * expf(-cr_hypot(x - 15.0f, y - 18.0f) / 16.0f);   // le jour autour de la fenetre
      e.lum0[i] = (uint16_t)cr_min(65535.0f, (clarte + 2.2f * e.tache[i] / 65535.0f + 0.9f * ray[i]) * 16384 + 0.5f);
    }
  // la piece : un mur a rayures discretes, une plinthe, un plancher dont les lames filent vers le fond
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      float c[3];
      const bool vitre = cr_jour(x, y);
      if (y >= 44) {
        const float pas = 7.0f * cr_max(y - 6.0f, 1.0f) / 38.0f, k = (x - 33) / pas, lame = floorf(k + 0.5f);
        const bool joint = fabsf(k - lame) * pas < 0.5f;
        const float s = sinf(lame * 12.9898f), m = (0.85f + 0.15f * s * s) * (joint ? 0.55f : 1.0f);
        c[0] = 62 * m; c[1] = 38 * m; c[2] = 22 * m;
      } else {
        const float k = cr_clip01(y / 42.0f), m = 0.95f + 0.05f * sinf(x * 1.25f);
        c[0] = (24 + 6 * k) * m; c[1] = (17 + 4 * k) * m; c[2] = (15 + 2 * k) * m;
      }
      if (y >= 41 && y <= 43) { c[0] = 40; c[1] = 28; c[2] = 22; }   // la plinthe
      if (y == 41) { c[0] = 52; c[1] = 38; c[2] = 30; }
      if (x >= 6 && x <= 23 && y >= 5 && y <= 29 && !vitre) { c[0] = 44; c[1] = 28; c[2] = 18; }
      if (y >= 29 && y <= 30 && x >= 4 && x <= 25) { c[0] = 70; c[1] = 48; c[2] = 30; }   // l'appui
      const bool rideau = x <= 4.5f - 0.06f * cr_max(0.0f, y - 30.0f) && y >= 3 && y <= 42;
      if (rideau) {
        const float p = 0.75f + 0.25f * sinf(x * 1.5f + 0.5f + sinf(y * 0.15f) * 0.6f);
        c[0] = 96 * p; c[1] = 40 * p; c[2] = 44 * p;
      }
      if (y == 3 && x <= 26) { c[0] = 60; c[1] = 44; c[2] = 30; }   // la tringle
      if (x >= 45 && x <= 56 && y >= 11 && y <= 21) { c[0] = 48; c[1] = 34; c[2] = 22; }   // un petit tableau
      if (x >= 46 && x <= 55 && y >= 12 && y <= 20) {
        const float k = (y - 12) / 8.0f;
        c[0] = 40 + 14 * k; c[1] = 52 + 6 * k; c[2] = 64 - 24 * k;
        if (y >= 17 && y <= 18 + sinf(x * 0.9f)) { c[0] = 70; c[1] = 64; c[2] = 40; }
      }
      for (int j = 0; j < 3; j++) e.piece[i][j] = (uint16_t)(c[j] * 256 + 0.5f);
      e.drapeaux[i] = (vitre ? 1 : 0) | (rideau ? 2 : 0);
    }
  for (int k = 0; k <= 256; k++) e.puiss[k] = powf(k * (1.2f / 256), 0.9f);
  for (auto &g : e.g) {
    g[0] = hasard(-4, 70); g[1] = hasard(0, 66); g[2] = hasard(0, PI2); g[3] = hasard(0.4f, 2.4f);
    g[4] = hasard(0.12f, 0.45f) * (aleatoire() & 1 ? 1 : -1); g[5] = hasard(0.4f, 1.3f); g[6] = hasard(0.35f, 1.0f);
  }
}

void s_poussiere(int humeur, bool debut, float t, float ecoule, float dt) {
  E_poussiere &e = etat_ecran<E_poussiere>(debut);
  (void)humeur; (void)ecoule;
  if (debut) cr_poussiere_preparer(e);
  const float v = sinf(t * 0.105f + 1.0f) * 0.6f + sinf(t * 0.043f + 2.0f) * 0.4f;
  float nuage = cr_clip01((v - 0.3f) / 0.45f);
  nuage = nuage * nuage * (3 - 2 * nuage);               // un nuage passe devant le soleil
  const float soleil = 1 - 0.62f * nuage;
  const float ciel[3] = {236 * (1 - nuage) + 160 * nuage, 214 * (1 - nuage) + 166 * nuage, 170 * (1 - nuage) + 184 * nuage};
  const float kv = 0.62f + 0.38f * soleil;
  float rideau[5];
  for (int x = 0; x < 5; x++) rideau[x] = 1 + 1.2f * soleil * expf(-(4.5f - x) / 1.5f);   // le bord du rideau, dans le jour
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      if (e.drapeaux[i] & 1) {
        const float k = kv * (0.9f + 0.1f * (y - 6) / 23.0f);
        peindre(y, x, ciel[0] * k, ciel[1] * k, ciel[2] * k);
        continue;
      }
      const float dta = e.dtache[i] * (1.0f / 32767);
      const float tache = e.tache[i] * (1.0f / 65535) + nuage * dta;   // sous le nuage, l'ombre s'adoucit
      const float rayon = e.rayon[i] * (1.0f / 50000) + nuage * e.drayon[i] * (1.0f / 27000);
      const float lum = 0.62f + soleil * (e.lum0[i] * (1.0f / 16384) + nuage * 2.2f * dta);
      const float ts = tache * soleil;
      float m = lum * (1.0f / 256);
      if (e.drapeaux[i] & 2) m *= rideau[x];
      const float q = cr_max(0.0f, cr_min(1.2f, rayon)) * (256 / 1.2f);
      const int qi = min(255, (int)q);
      const float r = (e.puiss[qi] + (e.puiss[qi + 1] - e.puiss[qi]) * (q - qi)) * 0.3f * soleil;
      const float tr = (e.drapeaux[i] & 2) ? rideau[x] : 1.0f;
      peindre(y, x, e.piece[i][0] * m + ts * 40 * tr + r * 255, e.piece[i][1] * m * 0.93f + ts * 30 * tr + r * 214,
              e.piece[i][2] * m * 0.82f + ts * 14 * tr + r * 150);
    }
  const float pas = cr_min(dt, 0.5f);                     // les poussieres : elles derivent et tournoient
  for (auto &g : e.g) {
    g[0] += (0.7f * sinf(g[1] * 0.11f + t * 0.09f + g[2]) + 0.3f * sinf(t * 0.05f + g[2] * 3)) * pas;
    g[1] += (0.5f * cosf(g[0] * 0.09f - t * 0.07f + g[2]) + 0.12f) * pas;
    g[0] = fmodf(fmodf(g[0] + 4, 74) + 74, 74) - 4;
    g[1] = fmodf(fmodf(g[1], 66) + 66, 66);
    const float px = g[0] + g[3] * cosf(t * g[4] + g[2]);
    const float py = g[1] + g[3] * sinf(t * g[4] * 1.1f + g[2]) * 0.8f;
    if (!(px >= 0 && px < 64 && py >= 0 && py < 64)) continue;
    const int i = (int)py * 64 + (int)px;
    if (e.drapeaux[i] & 1) continue;
    const float rayon = e.rayon[i] * (1.0f / 50000) + nuage * e.drayon[i] * (1.0f / 27000);
    const float s = 0.5f + 0.5f * sinf(t * g[5] + g[2] * 2);
    const float eclat = g[6] * cr_clip01((rayon - 0.1f) * 2.2f) * soleil * s * s * 1.25f;
    if (eclat > 0) cr_tamponner(py, px, eclat * 255, eclat * 226, eclat * 165);
  }
}

// --- la lampe a fibres optiques ----------------------------------------------------------------------------------

// humeurs : 0 = (une seule ambiance)
struct E_fibres {
  float th[72], l[72], ph[72], u[72], x0[72];   // chaque fibre : son angle, sa longueur, sa teinte, son pied
  float s14[30], longs[30];                     // le long d'une fibre : sa courbure, son eclat
  float px[72][30], py[72][30];                 // ses points, a cette image
  float coul[72][3];                            // sa couleur, a cette image
  float p[4096 * 3];                            // les pointes, puis leur halo, puis les fils
};
void s_fibres(int humeur, bool debut, float t, float ecoule, float dt) {
  E_fibres &e = etat_ecran<E_fibres>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    for (int i = 0; i < 72; i++) {                       // reparties, un peu au hasard, plus nombreuses au centre
      const float r = cr_max(-1.0f, cr_min(1.0f, -1 + 2.0f * i / 71 + hasard(-0.6f, 0.6f) / 72 * 2));
      e.th[i] = (r < 0 ? -1 : r > 0 ? 1 : 0) * powf(fabsf(r), 0.8f) * 1.3f;
    }
    for (int i = 71; i > 0; i--) {
      const int j = aleatoire() % (i + 1);
      const float c = e.th[i]; e.th[i] = e.th[j]; e.th[j] = c;
    }
    for (int i = 0; i < 72; i++) {
      e.l[i] = (41 - 11 * fabsf(e.th[i]) / 1.3f) * powf(hasard(0.5f, 1.0f), 0.7f);
      e.ph[i] = hasard(0, PI2);
      e.u[i] = (e.th[i] + 1.3f) / 2.6f + hasard(-0.05f, 0.05f);
      e.x0[i] = hasard(-1, 1);
    }
    for (int k = 0; k < 30; k++) {
      const float s = k / 29.0f;
      e.s14[k] = 0.06f + 2.1f * powf(s, 1.4f);            // elles partent droites, puis s'ouvrent et retombent
      e.longs[k] = 0.035f + 0.12f * (1 - s) * (1 - s) * (1 - s);
    }
  }
  float (*coul)[3] = e.coul, moy[3] = {0, 0, 0};
  const float oscille = 0.04f * sinf(t * 0.27f);
  for (int i = 0; i < 72; i++) {
    const float th = e.th[i] + 0.05f * cr_sin(t * 0.5f + e.th[i] * 2.5f) + 0.025f * cr_sin(t * 0.83f + e.ph[i]) + oscille;
    const float pas = e.l[i] / 30;
    float x = 32 + e.x0[i] * 0.5f, y = 49.8f;
    for (int k = 0; k < 30; k++) {
      const float phi = th * e.s14[k];
      x += cr_sin(phi) * pas; y -= cr_cos(phi) * pas;
      e.px[i][k] = x; e.py[i][k] = y;
    }
    float h = e.u[i] * 0.85f + t * 0.025f;               // le degrade arc-en-ciel, qui tourne
    float r, g, b;
    teinte(h - floorf(h), 0.72f, 1.0f, r, g, b);
    coul[i][0] = floorf(r); coul[i][1] = floorf(g); coul[i][2] = floorf(b);
    for (int c = 0; c < 3; c++) moy[c] += coul[i][c] / 72;
  }
  for (int y = 0; y < 64; y++) {
    float f[3];
    if (y < 58) { const float k = cr_min(1.0f, y / 56.0f); f[0] = 4 + 6 * k; f[1] = 3 + 5 * k; f[2] = 10 + 8 * k; }
    else if (y == 58) { f[0] = 26; f[1] = 22; f[2] = 32; }
    else { const float k = (y - 58) / 6.0f; f[0] = 18 - 11 * k; f[1] = 15 - 9 * k; f[2] = 24 - 14 * k; }
    for (int x = 0; x < 64; x++) peindre(y, x, f[0], f[1], f[2]);
  }
  // les pointes : un point de lumiere (1.25), son halo (le flou [1 2 1], 0.9), la couleur qui baigne la piece
  // (six flous, 2.4) -- chaque pointe posee d'un coup avec ce noyau (separable terme a terme) : pas de flou a faire
  static const float B2[3] = {0.25f, 0.5f, 0.25f};
  static const float B12[13] = {1 / 4096.0f, 12 / 4096.0f, 66 / 4096.0f, 220 / 4096.0f, 495 / 4096.0f, 792 / 4096.0f, 924 / 4096.0f,
                                792 / 4096.0f, 495 / 4096.0f, 220 / 4096.0f, 66 / 4096.0f, 12 / 4096.0f, 1 / 4096.0f};
  for (int i = 0; i < 72; i++) {
    const float k = 0.8f + 0.2f * cr_sin(t * 1.1f + e.ph[i] * 3);
    const float x = e.px[i][29], y = e.py[i][29];
    const float fy0 = floorf(y), fx0 = floorf(x);
    const int y0 = (int)fy0, x0 = (int)fx0;
    const float fy = y - fy0, fx = x - fx0;
    float v[3][14], h[3][14];                            // les profils (lignes y0-6 .. y0+7), pour chaque terme
    for (int j = 0; j < 14; j++) {
      for (int m = 0; m < 3; m++) v[m][j] = h[m][j] = 0;
      const int o = j - 6;                               // decalage par rapport a y0
      if (o == 0) { v[0][j] = 1 - fy; h[0][j] = 1 - fx; }
      if (o == 1) { v[0][j] = fy; h[0][j] = fx; }
      if (o >= -1 && o <= 1) { v[1][j] += (1 - fy) * B2[o + 1]; h[1][j] += (1 - fx) * B2[o + 1]; }
      if (o >= 0 && o <= 2) { v[1][j] += fy * B2[o]; h[1][j] += fx * B2[o]; }
      if (o >= -6 && o <= 6) { v[2][j] += (1 - fy) * B12[o + 6]; h[2][j] += (1 - fx) * B12[o + 6]; }
      if (o >= -5 && o <= 7) { v[2][j] += fy * B12[o + 5]; h[2][j] += fx * B12[o + 5]; }
    }
    const float r = coul[i][0] * k, g = coul[i][1] * k, b = coul[i][2] * k;
    for (int j = 0; j < 14; j++) {
      const int yy = y0 - 6 + j;
      if (yy < 0 || yy > 63) continue;
      const float a0 = 1.25f * v[0][j], a1 = 0.9f * v[1][j], a2 = 2.4f * v[2][j];
      for (int m = 0; m < 14; m++) {
        const int xx = x0 - 6 + m;
        if (xx < 0 || xx > 63) continue;
        const float s = a0 * h[0][m] + a1 * h[1][m] + a2 * h[2][m];
        float *p = scene[yy][xx];
        p[0] += s * r; p[1] += s * g; p[2] += s * b;
      }
    }
  }
  // les fibres : fines, sombres, plus claires au pied
  for (int i = 0; i < 4096 * 3; i++) e.p[i] = 0;
  for (int i = 0; i < 72; i++)
    for (int k = 0; k < 29; k++)
      cr_tamponner3(e.p, e.py[i][k], e.px[i][k], coul[i][0] * e.longs[k], coul[i][1] * e.longs[k], coul[i][2] * e.longs[k]);
  for (int i = 0; i < 4096 * 3; i++) (&scene[0][0][0])[i] += cr_min(e.p[i], 55.0f);
  // le socle : un dome noir et brillant, eclaire de la couleur du moment
  for (int y = 50; y <= 58; y++) {
    const float rel = (y - 50) / 8.0f, larg = 2.2f + 4.4f * sqrtf(rel), dome = 0.3f * cr_clip01(1 - rel * 1.5f);
    for (int x = 0; x < 64; x++) {
      if (fabsf(x - 32.0f) > larg) continue;
      const float q = ((x - 32) / larg + 0.42f) / 0.16f, l = expf(-q * q);
      peindre(y, x, 14 + 70 * l + moy[0] * dome, 12 + 70 * l + moy[1] * dome, 20 + 80 * l + moy[2] * dome);
    }
  }
  for (int y = 42; y <= 58; y++)                          // la lumiere du socle
    for (int x = 18; x <= 46; x++) {
      const float k = 0.8f * cr_exp(-cr_hypot(x - 32.0f, (y - 50) * 1.8f) / 2.0f);
      ajouter(y, x, k, moy[0] * 0.6f + 90, moy[1] * 0.6f + 90, moy[2] * 0.6f + 90);
    }
  for (int y = 58; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float k = 0.7f * cr_exp(-cr_hypot((x - 32) / 3.2f, (y - 59.5f) / 0.8f) / 2.6f);
      ajouter(y, x, k, moy[0], moy[1], moy[2]);
    }
}

// --- la boule plasma ---------------------------------------------------------------------------------------------

static const float CR_PLASMA_CX = 32.0f, CR_PLASMA_CY = 28.0f, CR_PLASMA_R = 21.5f;

// humeurs : 0 = (une seule ambiance)
struct E_boule_plasma {
  uint8_t fond[4096][3];                   // le fond, le verre, le socle, et la lueur de l'electrode (hors socle)
  uint8_t genre[4096];                     // 1 dans la boule, 2 le socle, 4 pres de l'electrode
  float a0[7], w[7][2], ph[7][8], br[7][2][2];
  float fil[4096], impact[4096];
};

// la main invisible : (force 0..1, angle) ; elle se pose sur le verre de temps en temps
inline float cr_plasma_main(float t, float &cote) {
  const float k = floorf(t / 38.0f), f = t / 38.0f - k;
  float h = sinf(k * 12.9898f) * 43758.5453f;
  h -= floorf(h);
  cote = 0;
  if (h > 0.5f) return 0;
  static const float cotes[7] = {-0.35f, -2.75f, -1.0f, 0.35f, -2.2f, 2.9f, -0.7f};
  const float a = cr_min(cr_clip01((f - 0.25f) / 0.15f), cr_clip01((0.75f - f) / 0.15f));
  cote = cotes[(int)(h * 14) % 7];
  return a * a * (3 - 2 * a);
}

void s_boule_plasma(int humeur, bool debut, float t, float ecoule, float dt) {
  E_boule_plasma &e = etat_ecran<E_boule_plasma>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float cx = CR_PLASMA_CX, cy = CR_PLASMA_CY, R = CR_PLASMA_R;
  if (debut) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const int i = y * 64 + x;
        const float d = cr_hypot(x - cx, y - cy), k = y / 60.0f > 1 ? 1.0f : y / 60.0f;
        float c[3];
        if (d < R) {                                     // le gaz, un peu plus clair au centre
          const float g = cr_clip01(1 - d / R);
          c[0] = 14 + 16 * g; c[1] = 4 + 6 * g; c[2] = 26 + 26 * g;
        } else {
          const float g = expf(-(d - R) / 7.0f);
          c[0] = 5 + 4 * k + 34 * g; c[1] = 3 + 2 * k + 12 * g; c[2] = 11 + 5 * k + 50 * g;
        }
        const float ang = atan2f(y - cy, x - cx);
        const float verre = cr_clip01(1 - fabsf(d - R + 0.3f) / 1.1f);
        const float reflet = cr_clip01(1 - fabsf(d - R + 2.6f)) * cr_clip01(1 - fabsf(ang + 2.3f) / 0.38f);
        c[0] += verre * 60 + reflet * 90; c[1] += verre * 44 + reflet * 84; c[2] += verre * 96 + reflet * 114;
        if (fabsf(x - cx) < 0.7f && y > cy + 3 && y < 48) { c[0] = 34; c[1] = 22; c[2] = 44; }   // la tige de verre
        const float rel = (y - 46) / 15.0f, lg = 8.5f + rel * 6;
        const bool socle = rel >= 0 && rel <= 1 && fabsf(x - cx) <= lg;
        if (socle) {                                     // le socle noir
          const float q = ((x - cx) / lg + 0.45f) / 0.2f;
          const float b = (1 - 0.35f * rel) * (0.7f + 0.5f * expf(-q * q));
          c[0] = 20 * b; c[1] = 15 * b; c[2] = 28 * b;
          if (y <= 47) { c[0] = 58; c[1] = 36; c[2] = 82; }   // le col, eclaire par la boule
          if (fabsf(x - cx - 5) < 0.8f && fabsf(y - 55.0f) < 0.8f) { c[0] = 90; c[1] = 50; c[2] = 120; }   // le bouton
        }
        if (y >= 61) { c[0] = 10; c[1] = 7; c[2] = 14; }
        e.genre[i] = (d < R - 0.4f ? 1 : 0) | (socle ? 2 : 0) | (d < 3.6f ? 4 : 0);
        if (!socle) {                                    // la lueur de l'electrode
          const float g = expf(-d / 4.5f) * 0.45f;
          c[0] += g * 210; c[1] += g * 120; c[2] += g * 255;
        }
        for (int j = 0; j < 3; j++) e.fond[i][j] = (uint8_t)cr_min(255.0f, c[j] + 0.5f);
      }
    for (int k = 0; k < 7; k++) {
      e.a0[k] = PI2 * k / 7 + hasard(-0.3f, 0.3f);
      e.w[k][0] = hasard(0.07f, 0.16f); e.w[k][1] = hasard(0.22f, 0.4f);
      for (int j = 0; j < 8; j++) e.ph[k][j] = hasard(0, PI2);
      for (int j = 0; j < 2; j++) { e.br[k][j][0] = hasard(0.45f, 0.75f); e.br[k][j][1] = hasard(0.12f, 0.32f); }
      e.br[k][1][1] *= -1;                               // une branche de chaque cote
    }
  }
  float cote;
  const float force = cr_plasma_main(t, cote);
  for (int i = 0; i < 4096; i++) e.fil[i] = e.impact[i] = 0;
  const float r0 = 3.4f, r1 = R - 1.2f;
  for (int k = 0; k < 7; k++) {
    float alpha = e.a0[k] + 0.55f * sinf(t * e.w[k][0] + e.ph[k][0]) + 0.3f * sinf(t * e.w[k][1] + e.ph[k][1]);
    float ecart = cote - alpha + 3.14159265f;
    ecart = ecart - PI2 * floorf(ecart / PI2) - 3.14159265f;
    const float tire = force * cr_clip01(1.2f - fabsf(ecart) / 1.5f);   // la main tire les filaments les plus proches
    alpha += ecart * tire * 0.95f;
    const float ca = cosf(alpha), sa = sinf(alpha);
    float fx[46], fy[46];
    for (int j = 0; j < 46; j++) {                       // des filaments qui serpentent
      const float s = j / 45.0f;
      const float sp = cr_sin(3.14159265f * s);
      const float ondule = (sp > 0 ? powf(sp, 0.7f) : 0.0f)
          * (2.0f * cr_sin(s * 4.1f + t * 0.55f + e.ph[k][2]) + 1.0f * cr_sin(s * 9.3f - t * 1.0f + e.ph[k][3])
             + 0.45f * cr_sin(s * 19.0f + t * 1.7f + e.ph[k][4])) * (1 - 0.7f * tire);
      const float rr = r0 + s * (r1 - r0);
      fx[j] = cx + rr * ca - ondule * sa; fy[j] = cy + rr * sa + ondule * ca;
      cr_tamponner1(e.fil, fy[j], fx[j], (0.2f + 0.24f * s * s) * (1 + 0.35f * tire));
    }
    cr_tamponner1(e.impact, fy[45], fx[45], (1.3f + 2.0f * tire) * (0.85f + 0.15f * sinf(t * 1.3f + k)));
    for (int j = 0; j < 2; j++) {                        // les ramifications, pres du verre
      const float db = e.br[k][j][1] * (1 - 0.7f * tire);
      const int i0 = (int)(e.br[k][j][0] * 45);
      const float bx = fx[i0], by = fy[i0];
      const float ex = cx + r1 * cosf(alpha + db), ey = cy + r1 * sinf(alpha + db);
      const float nx = -(ey - by), ny = ex - bx, ln = cr_hypot(nx, ny) + 1e-6f;
      for (int m = 0; m < 18; m++) {
        const float q = m / 17.0f;
        const float tort = cr_sin(3.14159265f * q) * 0.9f * cr_sin(q * 7 + t * 0.9f + e.ph[k][5 + j]);
        cr_tamponner1(e.fil, by + (ey - by) * q + tort * ny / ln, bx + (ex - bx) * q + tort * nx / ln,
                      0.2f * (0.5f + 0.5f * q) * (1 - 0.5f * tire));
      }
      cr_tamponner1(e.impact, ey, ex, 0.6f * (1 - 0.6f * tire) * (0.85f + 0.15f * sinf(t * 1.3f + (j + 1) * 7 + k)));
    }
  }
  for (int i = 0; i < 4096; i++) {
    float *p = &scene[0][0][0] + 3 * i;
    p[0] = e.fond[i][0]; p[1] = e.fond[i][1]; p[2] = e.fond[i][2];
    if ((e.genre[i] & 3) == 1) {
      const float f = cr_min(e.fil[i], 1.2f) * 0.7f;
      p[0] += f * 255; p[1] += f * 185; p[2] += f * 255;
    }
  }
  // les halos : le filament flou, puis tres flou ; l'impact, et sa lueur
  const int y0 = 1, y1 = 56, x0 = 5, x1 = 60;
  static const float halos[4][4] = {{200 * 0.75f, 80 * 0.75f, 255 * 0.75f, 1}, {280, 72, 450, 3},
                                    {255 * 1.5f, 190 * 1.5f, 250 * 1.5f, 1}, {255 * 2.4f, 70 * 2.4f, 190 * 2.4f, 2}};
  for (int h = 0; h < 4; h++) {
    float *buf = h < 2 ? e.fil : e.impact;
    cr_flou_cocon(buf, 1, (int)halos[h][3], y0, y1, x0, x1);
    for (int y = y0; y < y1; y++)
      for (int x = x0; x < x1; x++) {
        const int i = y * 64 + x;
        if ((e.genre[i] & 3) == 1) ajouter(y, x, buf[i], halos[h][0], halos[h][1], halos[h][2]);
      }
  }
  for (int y = 24; y <= 32; y++)                          // l'electrode, une bille qui luit
    for (int x = 28; x <= 36; x++) {
      const int i = y * 64 + x;
      if (!(e.genre[i] & 4)) continue;
      const float d = cr_hypot(x - cx, y - cy), b = cr_clip01(3.6f - d), g = expf(-d / 4.5f) * 0.45f;
      const float c = cr_clip01(1 - d / 2.6f);
      float *p = scene[y][x];
      p[0] = (p[0] - g * 210) * (1 - b) + b * (200 + 55 * c) + g * 210;
      p[1] = (p[1] - g * 120) * (1 - b) + b * (120 + 120 * c) + g * 120;
      p[2] = (p[2] - g * 255) * (1 - b) + b * 255 + g * 255;
    }
  if (force > 0)
    for (int i = 0; i < 4096; i++)
      if (e.genre[i] & 2) { float *p = &scene[0][0][0] + 3 * i; p[0] += force * 12; p[1] += force * 12; p[2] += force * 12; }
}

// --- le vinyle ---------------------------------------------------------------------------------------------------

static const float CR_DISQUE_CX = 27.0f, CR_DISQUE_CY = 35.0f, CR_DISQUE_K = 0.56f;
static const int8_t CR_NOTE[8][2] = {{0, 1}, {0, 2}, {1, 1}, {2, 1}, {3, 0}, {3, 1}, {4, 0}, {4, 1}};   // une croche

struct CR_Sillon { uint16_t i; uint8_t ajout[3]; float r, th, a, b, sill, mul, lampe; };

// humeurs : 0 = (une seule ambiance)
struct E_vinyle {
  uint8_t fixe[4096][3];                   // tout ce qui ne tourne pas
  CR_Sillon d[900];                        // le disque, pixel par pixel
  int nd;
  float eq[7][3], glint[3];
};

void s_vinyle(int humeur, bool debut, float t, float ecoule, float dt) {
  E_vinyle &e = etat_ecran<E_vinyle>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float cx = CR_DISQUE_CX, cy = CR_DISQUE_CY, kd = CR_DISQUE_K, angle_l = -1.94f;
  if (debut) {
    const float px = 52.5f, py = 20.5f;                  // le bras : un pivot, un contrepoids, un tube fin
    const float hx = cx + 16.0f * cosf(0.22f), hy = cy + 16.0f * kd * sinf(0.22f);
    const float lx = hx - px, ly = hy - py, lg = cr_hypot(lx, ly);
    e.nd = 0;
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const int i = y * 64 + x;
        const float lampe = 0.16f + expf(-cr_hypot(x - 5.0f, y - 5.0f) / 24.0f);
        const float k = y / 64.0f;
        float c[3] = {10 + 4 * k, 7 + 2 * k, 10};
        const float a = expf(-cr_hypot(x - 5.0f, (y - 7) * 1.2f) / 9.0f) * 0.5f;
        c[0] += a * 255; c[1] += a * 150; c[2] += a * 70;
        if (y > 10) {                                    // la lumiere qui tombe de l'abat-jour
          const float cone = cr_clip01(1 - fabsf((x - 4) - (y - 10) * 0.55f) / (2 + (y - 10) * 0.45f)) * expf(-(y - 10) / 14.0f) * 0.22f;
          c[0] += cone * 255; c[1] += cone * 170; c[2] += cone * 90;
        }
        const float rel = cr_clip01((y - 15) / 39.0f);   // le socle : un plateau de noyer en perspective
        if (y >= 15 && y <= 54 && x >= 8 - rel * 6 && x <= 58 + rel * 4) {
          const float g = (0.86f + 0.14f * sinf(y * 1.7f + sinf(x * 0.21f + y * 0.1f) * 2.2f)) * lampe * (y == 15 ? 1.3f : 1.0f);
          c[0] = 96 * g; c[1] = 58 * g; c[2] = 32 * g;
        }
        const bool face = y >= 55 && y <= 60 && x >= 2 && x <= 62;
        if (face) {
          const float g = 0.45f + 0.4f * lampe;
          c[0] = 46 * g; c[1] = 28 * g; c[2] = 16 * g;
          if (y == 55) { c[0] = 120; c[1] = 80; c[2] = 48; }
        }
        if (y >= 60 && !face) { c[0] = 8; c[1] = 6; c[2] = 8; }
        if (y >= 1 && y <= 9 && x <= 7.5f + (y - 1) * 0.75f) {   // l'abat-jour de la lampe, dans le coin
          const float g = (0.55f + 0.45f * (y / 9.0f)) * (0.9f + 0.1f * sinf(x * 2.1f));
          c[0] = 255 * g; c[1] = 176 * g; c[2] = 92 * g;
          if (y == 9) { c[0] = 255; c[1] = 220; c[2] = 160; }
          if (y == 1) { c[0] = 150; c[1] = 90; c[2] = 50; }
        }
        if (y == 0 && x >= 3 && x <= 4) { c[0] = 40; c[1] = 30; c[2] = 26; }   // sa tige
        const float u = x - cx, v = (y - cy) / kd, r = cr_hypot(u, v), th = atan2f(v, u);
        if (cr_hypot(u, (y - cy - 1.6f) / kd) <= 23.0f && r > 23.0f) { c[0] = 34; c[1] = 34; c[2] = 38; }   // l'epaisseur
        if (r <= 23.0f && r > 21.3f) {                   // la jante
          const float g = 0.55f + 0.45f * cr_clip01(-sinf(th + 0.9f)) + 0.25f * lampe;
          c[0] = 120 * g; c[1] = 120 * g; c[2] = 126 * g;
          if (fabsf(th - 1.0f) < 0.06f) { c[0] = 255; c[1] = 120; c[2] = 60; }   // le point du stroboscope
        }
        const float q = cr_clip01(((x - px) * lx + (y - py) * ly) / (lg * lg));
        const float bras = cr_clip01(1.25f - cr_hypot(x - px - q * lx, y - py - q * ly)) * (q > 0.08f);
        const float ombre = cr_clip01(1.2f - cr_hypot(x - px - q * lx + 1.5f, y - py - q * ly - 2.2f)) * (q > 0.15f);
        const bool tete = fabsf((x - hx) * lx + (y - hy) * ly) / lg <= 1.6f && fabsf((x - hx) * ly - (y - hy) * lx) / lg <= 1.3f;
        const bool pivot = cr_hypot(x - px, (y - py) * 1.2f) <= 3.2f;
        const bool poids = cr_hypot(x - px - 3.2f, (y - py + 3.6f) * 1.2f) <= 2.1f;
        const float mul = (1 - 0.55f * ombre) * (1 - bras), bl = 0.6f + 0.4f * lampe;
        const float ajout[3] = {bras * 186 * bl, bras * 184 * bl, bras * 190 * bl};
        for (int j = 0; j < 3; j++) c[j] = c[j] * mul + ajout[j];
        const bool fige = tete || pivot || poids;
        if (tete) { c[0] = 150; c[1] = 148; c[2] = 156; }
        if (pivot) { c[0] = 96; c[1] = 96; c[2] = 104; }
        if (poids) { c[0] = 60; c[1] = 60; c[2] = 66; }
        if (pivot && y < 20 && x < 52) { c[0] = 170; c[1] = 170; c[2] = 178; }
        for (int j = 0; j < 3; j++) e.fixe[i][j] = (uint8_t)cr_min(255.0f, c[j] + 0.5f);
        if (r <= 21.3f && !fige && e.nd < 900) {           // le disque : ce qui tourne
          CR_Sillon &s = e.d[e.nd++];
          s.i = (uint16_t)i; s.r = r; s.th = th; s.mul = mul; s.lampe = lampe;
          for (int j = 0; j < 3; j++) s.ajout[j] = (uint8_t)cr_min(255.0f, ajout[j] + 0.5f);
          s.sill = 0.9f + 0.1f * sinf(r * 3.3f) + 0.1f * (fabsf(r - 12) < 0.5f) + 0.1f * (fabsf(r - 16) < 0.5f) + 0.12f * (r > 20.4f);
          float ecart = th - angle_l + 3.14159265f;
          ecart = ecart - PI2 * floorf(ecart / PI2) - 3.14159265f;
          const float e1 = ecart / 0.22f, e2 = (fabsf(ecart) - 3.14159265f) / 0.22f;
          const float l1 = ecart / 0.7f, l2 = (fabsf(ecart) - 3.14159265f) / 0.7f;
          const float noeud = expf(-e1 * e1) + 0.6f * expf(-e2 * e2);   // le reflet en noeud papillon
          const float lustre = expf(-l1 * l1) + 0.6f * expf(-l2 * l2);
          const float radial = (0.35f + 0.65f * cr_clip01((r - 7) / 14)) * (r > 7.3f);
          s.a = noeud * radial; s.b = 0.18f * lustre * radial;
        }
      }
    for (auto &q : e.eq) { q[0] = hasard(0.6f, 1.2f); q[1] = hasard(1.3f, 2.4f); q[2] = hasard(0, PI2); }
    for (auto &g : e.glint) g = hasard(0, PI2);
  }
  for (int i = 0; i < 4096; i++) {
    float *p = &scene[0][0][0] + 3 * i;
    p[0] = e.fixe[i][0]; p[1] = e.fixe[i][1]; p[2] = e.fixe[i][2];
  }
  float gx[3], gy[3], gp[3];                             // des poussieres qui brillent au passage du reflet
  static const float rayons_g[3] = {9.5f, 14.0f, 18.5f};
  for (int j = 0; j < 3; j++) {
    const float ag = e.glint[j] + t * 2.3f;
    gx[j] = cx + rayons_g[j] * cosf(ag); gy[j] = cy + rayons_g[j] * kd * sinf(ag);
    float ec = ag - angle_l + 3.14159265f;
    ec = (ec - PI2 * floorf(ec / PI2) - 3.14159265f) / 0.5f;
    gp[j] = expf(-ec * ec) + 0.15f;
  }
  const float tt = t * 2.3f;
  for (int n = 0; n < e.nd; n++) {
    const CR_Sillon &s = e.d[n];
    const int y = s.i >> 6, x = s.i & 63;
    const float tour = s.th - tt;                        // l'angle, dans le repere du disque qui tourne
    float c[3];
    if (s.r < 0.9f) { c[0] = 200; c[1] = 200; c[2] = 205; }
    else if (s.r <= 7.0f) {                              // l'etiquette, qui tourne avec le disque
      const float tm = tour - PI2 * floorf(tour / PI2);
      const bool secteur = tm < 1.1f && s.r > 2.0f;
      float tx = tour * 5 / 3.14159265f;
      tx -= 2 * floorf(tx / 2);
      const bool texte = fabsf(s.r - 4.6f) < 0.55f && tx < 0.8f;
      if (secteur) { c[0] = 236; c[1] = 200; c[2] = 140; } else { c[0] = 196; c[1] = 66; c[2] = 44; }
      if (texte) for (int j = 0; j < 3; j++) c[j] *= 0.6f;
      if (fabsf(s.r - 6.4f) < 0.5f) { c[0] = 236 * 0.8f; c[1] = 200 * 0.8f; c[2] = 140 * 0.8f; }
      const float l = 0.5f + 0.35f * s.lampe;
      for (int j = 0; j < 3; j++) c[j] *= l;
    } else {
      const float sn = cr_sin(s.r * 3.3f + 0.9f * cr_sin(tour * 2 + s.r * 0.4f));   // les sillons, qui frissonnent
      const float reflet = (s.a * (0.45f + 0.55f * sn * sn) + s.b) * 0.72f;
      c[0] = 14 * s.sill + reflet * 214; c[1] = 13 * s.sill + reflet * 172; c[2] = 17 * s.sill + reflet * 128;
      float g = 0;
      for (int j = 0; j < 3; j++) {
        const float dx = x - gx[j], dy = y - gy[j];
        if (fabsf(dx) < 4.5f && fabsf(dy) < 4.5f) g += cr_exp(-(dx * dx + dy * dy) / 1.2f) * gp[j];
      }
      c[0] += g * 132; c[1] += g * 114; c[2] += g * 90;
    }
    peindre(y, x, c[0] * s.mul + s.ajout[0], c[1] * s.mul + s.ajout[1], c[2] * s.mul + s.ajout[2]);
  }
  for (int j = 0; j < 7; j++) {                          // le petit egaliseur, sur la facade
    const float bat = 0.5f + 0.5f * sinf(t * PI2 * 1.55f), b2 = bat * bat, b6 = b2 * b2 * b2;
    const float niv = cr_max(0.05f, cr_min(1.0f, 0.45f + 0.25f * sinf(t * e.eq[j][0] + e.eq[j][2])
                         + 0.2f * sinf(t * e.eq[j][1] * 1.7f + e.eq[j][2] * 2) + 0.25f * b6 * (j < 3))) * 4;
    for (int i = 0; i < 4; i++) {
      const float k = 0.12f + 0.68f * cr_clip01(niv - i);
      if (i < 2) pointer(59 - i, 44 + 2 * j, 60 * k, 210 * k, 150 * k);
      else if (i < 3) pointer(59 - i, 44 + 2 * j, 230 * k, 200 * k, 70 * k);
      else pointer(59 - i, 44 + 2 * j, 255 * k, 120 * k, 50 * k);
    }
  }
  for (int j = 0; j < 2; j++) {                          // des notes qui montent, tres discretes
    const float cycle = t / 9.0f + j * 0.5f, n = floorf(cycle), f = cycle - n;
    float h = sinf(n * 78.233f + j * 3.1f) * 43758.5453f;
    h -= floorf(h);
    const float x0 = 10 + h * 26 + sinf(f * 5 + j) * 1.5f, y0 = 24 - f * 18;
    const float s = sinf(3.14159265f * f), force = s * s * 0.5f;
    for (auto &p : CR_NOTE) cr_tamponner(y0 + p[0], x0 + p[1], 255 * force, 196 * force, 130 * force);
  }
}

// --- les rubans de soie ------------------------------------------------------------------------------------------

static const float CR_SOIE[3][3][3] = {   // par ruban : la face, le reflet qui glisse le long, le revers
  {{255, 95, 140}, {255, 170, 90}, {130, 45, 120}}, {{50, 180, 255}, {90, 250, 210}, {50, 60, 190}},
  {{180, 110, 255}, {255, 140, 215}, {80, 50, 160}}};
static const float CR_SOIE_FORME[3][3] = {{0.0f, -0.40f, 6.5f}, {2.2f, 0.32f, 6.0f}, {4.1f, 0.02f, 5.5f}};   // phase, angle, demi-largeur
const int CR_RUBAN_N = 192;               // les echantillons le long d'un ruban (un tous les 0,5 pixel : 89 pixels au plus)

// humeurs : 0 = (une seule ambiance)
struct E_rubans {
  // tout ce qui ne depend que de U (le long du ruban) : sa ligne, sa largeur, sa torsion, devant/derriere, sa couleur
  float f[3][CR_RUBAN_N], h[3][CR_RUBAN_N], st[3][CR_RUBAN_N], act[3][CR_RUBAN_N], z[3][CR_RUBAN_N], g[3][CR_RUBAN_N];
  uint8_t dessus[3][CR_RUBAN_N];
  float fond[4096];                        // ce que les rubans laissent voir du fond
  float petit[32 * 32 * 3];                // leur halo, a demi-taille
};
void s_rubans(int humeur, bool debut, float t, float ecoule, float dt) {
  E_rubans &e = etat_ecran<E_rubans>(debut);
  (void)humeur; (void)ecoule; (void)dt; (void)debut;
  float ca[3], sa[3], ox[3], oy[3], umin[3];
  for (int i = 0; i < 3; i++) {
    const float ph = CR_SOIE_FORME[i][0], w = CR_SOIE_FORME[i][2];
    const float ang = CR_SOIE_FORME[i][1] + 0.3f * sinf(t * 0.043f + ph);   // le ruban pivote, tres lentement
    ca[i] = cosf(ang); sa[i] = sinf(ang);
    ox[i] = 32 + 8 * sinf(t * 0.047f + ph);
    oy[i] = 32 + 13 * sinf(t * 0.061f + ph * 1.3f);
    float a = 1e9f, b = -1e9f;
    for (int c = 0; c < 4; c++) {
      const float u = ((c & 1) * 63 - ox[i]) * ca[i] + ((c >> 1) * 63 - oy[i]) * sa[i];
      a = cr_min(a, u); b = cr_max(b, u);
    }
    umin[i] = a - 0.5f;
    const int n = min(CR_RUBAN_N, (int)((b - a) * 2) + 4);
    const float k1 = 0.075f + 0.012f * i, k2 = 0.16f - 0.018f * i;
    const float q1 = t * 0.26f - ph, q2 = t * 0.17f + 2 * ph, q3 = t * 0.18f - ph, q4 = t * 0.15f + ph, q5 = t * 0.09f + 2 * ph;
    for (int k = 0; k < n; k++) {
      const float U = umin[i] + k * 0.5f;
      const float p1 = U * k1 - q1, p2 = U * k2 + q2;
      e.f[i][k] = 7.0f * cr_sin(p1) + 2.5f * cr_sin(p2);                    // sa ligne, qui ondule
      const float fp = 7.0f * k1 * cr_cos(p1) + 2.5f * k2 * cr_cos(p2);
      const float tors = U * 0.05f + 1.3f * cr_sin(U * 0.04f - q3) + q4;   // la torsion, qui court le long
      const float ct = cr_cos(tors), act = fabsf(ct);
      e.h[i][k] = w * act * sqrtf(1 + fp * fp);                             // de face : large ; par la tranche : un fil
      e.st[i][k] = 0.75f * cr_sin(tors);
      e.act[i][k] = act;
      e.z[i][k] = cr_sin(U * 0.035f + q5);                                  // devant, derriere : ca change le long
      e.g[i][k] = 0.5f + 0.5f * cr_sin(U * 0.06f - q3);
      e.dessus[i][k] = ct >= 0;
    }
  }
  for (int i = 0; i < 32 * 32 * 3; i++) e.petit[i] = 0;
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float A[3], Z[3], col[3][3];
      for (int i = 0; i < 3; i++) {
        const float dx = x - ox[i], dy = y - oy[i];
        const float U = dx * ca[i] + dy * sa[i], V = dy * ca[i] - dx * sa[i];
        const float q = (U - umin[i]) * 2;
        const int k = (int)q;
        const float fr = q - k;
        const float f = e.f[i][k] + (e.f[i][k + 1] - e.f[i][k]) * fr, h = e.h[i][k] + (e.h[i][k + 1] - e.h[i][k]) * fr;
        const float dv = V - f;
        A[i] = cr_clip01(h + 0.6f - fabsf(dv)) * 0.92f;
        if (A[i] <= 0) { Z[i] = 0; continue; }
        const float st = e.st[i][k] + (e.st[i][k + 1] - e.st[i][k]) * fr;
        const float act = e.act[i][k] + (e.act[i][k + 1] - e.act[i][k]) * fr;
        const float z = e.z[i][k] + (e.z[i][k + 1] - e.z[i][k]) * fr;
        const float g = e.g[i][k] + (e.g[i][k + 1] - e.g[i][k]) * fr;
        const float v = cr_max(-1.0f, cr_min(1.0f, dv / (h + 0.3f)));
        const float qq = v - st;
        const float reflet = cr_exp(-qq * qq * 6.25f) * act;               // le lustre de la soie, qui suit la torsion
        const float a1 = 1 - act, tr = a1 * a1 * a1;
        const float lum = ((0.3f + 0.7f * act) * (1 - 0.25f * v * v) + 0.55f * reflet + 0.6f * tr * tr) * (0.8f + 0.2f * z);
        const bool dessus = e.dessus[i][fr < 0.5f ? k : k + 1];
        for (int c = 0; c < 3; c++)
          col[i][c] = lum * (dessus ? CR_SOIE[i][0][c] * (1 - g) + CR_SOIE[i][1][c] * g : CR_SOIE[i][2][c]);
        Z[i] = z;
      }
      float fond = 1, s[3] = {0, 0, 0}, hl[3] = {0, 0, 0};
      for (int i = 0; i < 3; i++) {
        if (A[i] <= 0) continue;
        fond *= 1 - A[i];
        float vu = A[i];                                 // ce qu'on voit : ceux devant cachent
        for (int j = 0; j < 3; j++)
          if (j != i && Z[j] > Z[i]) vu *= 1 - A[j];
        for (int c = 0; c < 3; c++) { s[c] += col[i][c] * vu; hl[c] += col[i][c] * A[i]; }
      }
      e.fond[y * 64 + x] = fond;
      peindre(y, x, s[0], s[1], s[2]);
      float *p = e.petit + ((y >> 1) * 32 + (x >> 1)) * 3;
      p[0] += hl[0] * 0.25f; p[1] += hl[1] * 0.25f; p[2] += hl[2] * 0.25f;
    }
  for (int y = 0; y < 64; y++) {                         // le fond, et le halo des rubans, la ou on les voit
    const float k = y / 64.0f, b[3] = {7 - 4 * k, 4 - 1 * k, 16 - 6 * k};
    for (int x = 0; x < 64; x++) ajouter(y, x, e.fond[y * 64 + x], b[0], b[1], b[2]);
  }
  cr_flou_rev(e.petit, 3, 2, 32);
  cr_agrandir(e.petit, 0.4f, e.fond);
}

// --- l'encre dans l'eau ------------------------------------------------------------------------------------------

static const float CR_ENCRE[6][3] = {{255, 60, 150}, {90, 200, 255}, {255, 160, 40}, {150, 80, 255}, {40, 235, 170}, {255, 90, 70}};
const float CR_ENCRE_ECH = 4096.0f;        // l'encre est gardee en uint16, x 4096
const int CR_ENCRE_D = 8;                  // le plus grand deplacement d'un pas (pixels) ; au-dela, borne
const int CR_ENCRE_K = CR_ENCRE_D + 2;     // les lignes en attente d'etre ecrites

struct CR_Goutte { float x, y, v, v0, age, ph, vi, c[3]; };

// humeurs : 0 = (une seule ambiance)
struct E_encre {
  uint16_t m[4096][3];                     // l'encre, sur la grille du panneau
  uint16_t av[4096][3];                    // l'aller du MacCormack ; puis la lumiere de l'encre (x 256)
  int16_t vit[4096][2];                    // le deplacement d'un pas, en x et en y (x 4000)
  float psi[3][64];                        // trois lignes de la fonction de courant
  uint16_t a[4096], b[4096];               // les deux champs qui font le courant de fond
  uint16_t file[CR_ENCRE_K][64][3];        // les lignes calculees, pas encore ecrites (on lit encore l'ancienne)
  float ex[64], sx[64], cx[64];
  uint8_t plein[64];                       // les lignes ou il y a de l'encre
  uint8_t vit_ok[64];                      // les lignes dont le deplacement est a jour
  int vit_pas;
  float vit_h;
  CR_Goutte g[8];
  int ng, teinte, avance;
  float horloge, prochaine, force;
};

// _encre_lire : l'encre (dans les unites du tampon) a une position non entiere (melange des quatre voisins),
// de l'eau claire hors du panneau
inline void cr_encre_lire(const uint16_t (*m)[3], float sx, float sy, float *v) {
  const float dehors = cr_max(cr_max(-sx, sx - 63), cr_max(-sy, sy - 63));
  const float eau = cr_clip01(1 - dehors);
  sx = cr_max(0.0f, cr_min(62.99999f, sx)); sy = cr_max(0.0f, cr_min(62.99999f, sy));
  const int x0 = (int)sx, y0 = (int)sy, i = y0 * 64 + x0;
  const float fx = sx - x0, fy = sy - y0;
  for (int c = 0; c < 3; c++) {
    const float a = m[i][c], b = m[i + 1][c], d = m[i + 64][c], g = m[i + 65][c];
    const float ab = a + (b - a) * fx, dg = d + (g - d) * fx;
    v[c] = (ab + (dg - ab) * fy) * eau;
  }
}
// un point de lecture : ses quatre voisins (i, i + 1, i + 64, i + 65), ses poids, l'eau claire hors du panneau
struct CR_Lecture { int i; float fx, fy, eau; };
inline void cr_encre_point(CR_Lecture &l, float sx, float sy) {
  if (sx >= 0 && sx <= 62.99999f && sy >= 0 && sy <= 62.99999f) l.eau = 1;
  else {
    l.eau = cr_clip01(1 - cr_max(cr_max(-sx, sx - 63), cr_max(-sy, sy - 63)));
    sx = cr_max(0.0f, cr_min(62.99999f, sx)); sy = cr_max(0.0f, cr_min(62.99999f, sy));
  }
  const int x0 = (int)sx, y0 = (int)sy;
  l.i = y0 * 64 + x0; l.fx = sx - x0; l.fy = sy - y0;
}
inline float cr_encre_melange(const CR_Lecture &l, float a, float b, float d, float g) {
  const float ab = a + (b - a) * l.fx, dg = d + (g - d) * l.fx;
  return (ab + (dg - ab) * l.fy) * l.eau;
}
inline void cr_encre_lire(const uint16_t (*m)[3], float sx, float sy, uint16_t *v) {
  float f[3];
  cr_encre_lire(m, sx, sy, f);
  for (int c = 0; c < 3; c++) v[c] = (uint16_t)(f[c] + 0.5f);   // un melange : jamais au-dela de 65535
}

void cr_encre_pas(E_encre &e, float h) {
  e.horloge += h;
  const float c = e.horloge;
  if (c >= e.prochaine && e.ng < 8) {                    // une goutte d'une autre couleur
    e.prochaine = c + hasard(5.5f, 8.0f);
    e.teinte = (e.teinte + 1 + (int)(aleatoire() % 5)) % 6;
    CR_Goutte &g = e.g[e.ng++];
    g.v0 = g.v = hasard(13, 17);
    g.x = hasard(18, 46); g.y = -1.5f; g.age = 0; g.ph = hasard(0, 6.3f); g.vi = g.v;
    for (int j = 0; j < 3; j++) g.c[j] = CR_ENCRE[e.teinte][j] / 255.0f;
  }
  float gs[8], gk[8], gx[8], gy[8];
  const int ng = e.ng;                                   // le courant voit les gouttes d'avant ce pas
  for (int n = 0; n < ng; n++) {
    CR_Goutte &g = e.g[n];
    gs[n] = 3.4f + 2.8f * (1 - g.v / g.v0);              // il s'elargit en ralentissant
    g.vi = g.v + 2.8f * expf(-g.age / 6.0f);             // il tourne encore un peu quand il a freine
    gk[n] = gs[n] * g.vi;
    gx[n] = g.x; gy[n] = g.y;
  }
  for (int n = 0; n < ng; n++) {
    CR_Goutte &g = e.g[n];
    if (g.age < 0.55f) {                                 // elle lache son encre en entrant
      const float q = 1 - g.age / 0.55f, k = 46.0f * h * q * q * CR_ENCRE_ECH;
      for (int y = max(0, (int)floorf(g.y) - 8); y <= min(63, (int)floorf(g.y) + 9); y++)
        for (int x = max(0, (int)g.x - 8); x <= min(63, (int)g.x + 9); x++) {
          const float r2 = (x - g.x) * (x - g.x) + (y - g.y) * (y - g.y);
          if (r2 > 60) continue;
          const float a = cr_exp(-r2 / 6.0f) * k;
          uint16_t *p = e.m[y * 64 + x];
          for (int j = 0; j < 3; j++) p[j] = (uint16_t)cr_min(65535.0f, p[j] + a * g.c[j] + 0.5f);
          e.plein[y] = 1;
        }
    }
    g.y += g.vi * h;
    g.x += sinf(g.age * 2.2f + g.ph) * 2.5f * h;         // elle ne tombe pas tout a fait droit
    g.v *= expf(-h / 2.6f);
    g.age += h;
  }
  int garde = 0;
  for (int n = 0; n < e.ng; n++) if (e.g[n].age < 14) e.g[garde++] = e.g[n];
  e.ng = garde;
  // ou il y a de l'encre : une ligne dont aucune voisine (a un pas pres) n'en a ne recoit rien, et n'a pas
  // besoin du courant
  // Le courant est refait tous les 1/15 s (le pas de numpy) : entre deux, le deplacement d'un pas est reutilise, et
  // seules les lignes que l'encre vient d'atteindre sont calculees
  uint8_t proche[64], besoin[64], calcul[64];
  const bool neuf = e.vit_pas % 2 == 0 || h != e.vit_h;
  e.vit_pas++;
  e.vit_h = h;
  for (int y = 0; y < 64; y++) {
    proche[y] = 0;
    for (int r = max(0, y - CR_ENCRE_D - 1); r <= min(63, y + CR_ENCRE_D + 1); r++) proche[y] |= e.plein[r];
    besoin[y] = proche[y] && (neuf || !e.vit_ok[y]);
    if (neuf) e.vit_ok[y] = 0;
  }
  for (int y = 0; y < 64; y++) calcul[y] = besoin[y] | (y > 0 && besoin[y - 1]) | (y < 63 && besoin[y + 1]);
  // le courant : deux champs doux qui glissent, un tournoiement, et chaque goutte, un anneau de tourbillons
  const cr_Fen fa = cr_fen(e.a, 64, 30 + c * 0.55f, 10 + c * 0.3f), fb = cr_fen(e.b, 64, 70 - c * 0.4f, 50 + c * 0.5f);
  const float tourne = 0.04f * sinf(c * 0.05f);
  auto ligne = [&](int y, float *psi) {                  // une ligne de la fonction de courant
    if (!calcul[y]) return;
    const float dy = y - 32.0f, ty = tourne * e.ex[y];
    float gy2[8];
    for (int n = 0; n < ng; n++) gy2[n] = (y - gy[n]) * (y - gy[n]) + 3.0f;
    const uint16_t *a0 = e.a + (((y + fa.y0) & 63) << 6), *a1 = e.a + (((y + fa.y0 + 1) & 63) << 6);
    const uint16_t *b0 = e.b + (((y + fb.y0) & 63) << 6), *b1 = e.b + (((y + fb.y0 + 1) & 63) << 6);
    const float kf = e.force * (1.0f / 65535.0f);
    for (int x = 0; x < 64; x++) {
      const int xa = (x + fa.x0) & 63, xa1 = (xa + 1) & 63, xb = (x + fb.x0) & 63, xb1 = (xb + 1) & 63;
      const float ha = a0[xa] + (a0[xa1] - (float)a0[xa]) * fa.fx, la = a1[xa] + (a1[xa1] - (float)a1[xa]) * fa.fx;
      const float hb = b0[xb] + (b0[xb1] - (float)b0[xb]) * fb.fx, lb = b1[xb] + (b1[xb1] - (float)b1[xb]) * fb.fx;
      const float dx = x - 32.0f;
      float p = kf * ((ha + (la - ha) * fa.fy) - (hb + (lb - hb) * fb.fy)) + ty * e.ex[x] * (dx * dx + dy * dy);
      for (int n = 0; n < ng; n++) {
        const float u = x - gx[n], a = u - gs[n], b = u + gs[n];
        p += gk[n] * cr_log((a * a + gy2[n]) / (b * b + gy2[n]));
      }
      psi[x] = p;
    }
  };
  // le courant sans source ni puits (np.gradient de psi : centre, d'un cote aux bords) -> le deplacement d'un pas
  const float D = (float)CR_ENCRE_D, kv = 4000.0f;   // 8 x 4000 : dans un int16
  ligne(0, e.psi[0]);
  ligne(1, e.psi[1]);
  for (int y = 0; y < 64; y++) {
    if (y >= 1 && y + 1 < 64) ligne(y + 1, e.psi[(y + 1) % 3]);
    if (!besoin[y]) continue;
    e.vit_ok[y] = 1;
    const float *av = e.psi[(y + 2) % 3], *ic = e.psi[y % 3], *ap = e.psi[(y + 1) % 3];
    for (int x = 0; x < 64; x++) {
      float vx = y == 0 ? ap[x] - ic[x] : y == 63 ? ic[x] - av[x] : (ap[x] - av[x]) * 0.5f;
      float vy = -(x == 0 ? ic[1] - ic[0] : x == 63 ? ic[63] - ic[62] : (ic[x + 1] - ic[x - 1]) * 0.5f);
      vx = cr_max(-D, cr_min(D, vx * h)); vy = cr_max(-D, cr_min(D, vy * h));
      e.vit[y * 64 + x][0] = (int16_t)(vx * kv); e.vit[y * 64 + x][1] = (int16_t)(vy * kv);
    }
  }
  // l'encre suit le courant : on remonte le courant, puis on corrige l'aller-retour (MacCormack)
  const float iv = 1.0f / kv;
  for (int y = 0; y < 64; y++) {
    if (!proche[y]) { memset(e.av[y * 64], 0, 64 * 3 * sizeof(uint16_t)); continue; }
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      CR_Lecture l;
      cr_encre_point(l, x - e.vit[i][0] * iv, y - e.vit[i][1] * iv);
      const uint16_t *q0 = e.m[l.i], *q1 = e.m[l.i + 64];
      if (!(q0[0] | q0[1] | q0[2] | q0[3] | q0[4] | q0[5] | q1[0] | q1[1] | q1[2] | q1[3] | q1[4] | q1[5])) {
        e.av[i][0] = e.av[i][1] = e.av[i][2] = 0;
        continue;
      }
      for (int j = 0; j < 3; j++) e.av[i][j] = (uint16_t)(cr_encre_melange(l, q0[j], q0[j + 3], q1[j], q1[j + 3]) + 0.5f);
    }
  }
  const float dilue = expf(-h / 17.0f), perd = 0.01f * h * CR_ENCRE_ECH - 0.5f;   // (+ 0.5 : l'arrondi)
  for (int y = 0; y < 64 + CR_ENCRE_K - 1; y++) {
    if (y < 64 && !proche[y]) memset(e.file[y % CR_ENCRE_K], 0, sizeof(e.file[0]));
    else if (y < 64)
      for (int x = 0; x < 64; x++) {
        const int i = y * 64 + x;
        const float vx = e.vit[i][0] * iv, vy = e.vit[i][1] * iv;
        CR_Lecture l;                                    // les bornes : les quatre voisins de l'aller
        cr_encre_point(l, x - vx, y - vy);
        uint16_t *o = e.file[y % CR_ENCRE_K][x];
        const uint16_t *q0 = e.m[l.i], *q1 = e.m[l.i + 64];
        int bas[3], haut[3];
        for (int j = 0; j < 3; j++) {
          const int a = q0[j], b = q0[j + 3], d = q1[j], g = q1[j + 3];
          const int ab = a < b ? a : b, dg = d < g ? d : g, AB = a > b ? a : b, DG = d > g ? d : g;
          bas[j] = ab < dg ? ab : dg; haut[j] = AB > DG ? AB : DG;
        }
        if (!(haut[0] | haut[1] | haut[2])) {           // les quatre voisins sont vides : borne a zero
          o[0] = o[1] = o[2] = 0;
          continue;
        }
        CR_Lecture r;
        cr_encre_point(r, x + vx, y + vy);
        const uint16_t *r0 = e.av[r.i], *r1 = e.av[r.i + 64];
        for (int j = 0; j < 3; j++) {
          const float retour = cr_encre_melange(r, r0[j], r0[j + 3], r1[j], r1[j + 3]);
          const float m = cr_max(bas[j] * l.eau, cr_min((float)haut[j], e.av[i][j] + (e.m[i][j] - retour) * 0.5f));
          o[j] = (uint16_t)cr_max(0.0f, m * dilue - perd);   // tres diluee, elle disparait : pas de voile
        }
      }
    const int pret = y - (CR_ENCRE_K - 1);               // plus personne ne lira cette ligne de l'ancienne encre
    if (pret >= 0) {
      memcpy(e.m[pret * 64], e.file[pret % CR_ENCRE_K], sizeof(e.file[0]));
      uint32_t tout = 0;
      const uint16_t *v = e.m[pret * 64];
      for (int k = 0; k < 64 * 3; k++) tout |= v[k];
      e.plein[pret] = tout != 0;
    }
  }
}

void s_encre(int humeur, bool debut, float t, float ecoule, float dt) {
  E_encre &e = etat_ecran<E_encre>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    brume_n(e.a, 64, 22);
    brume_n(e.b, 64, 34);
    double s = 0, s2 = 0;                                // la force : un courant de fond de vitesse choisie
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float gx = (e.a[y * 64 + ((x + 1) & 63)] - (float)e.a[y * 64 + ((x + 63) & 63)]) * (0.5f / 65535);
        const float gy = (e.a[((y + 1) & 63) * 64 + x] - (float)e.a[((y + 63) & 63) * 64 + x]) * (0.5f / 65535);
        const float g = sqrtf(gx * gx + gy * gy);
        s += g; s2 += g * g;
      }
    const float moy = (float)(s / 4096), ec = sqrtf(cr_max(0.0f, (float)(s2 / 4096) - moy * moy));
    e.force = 2.5f / cr_max(1e-6f, ec * 2);
    for (int i = 0; i < 64; i++) {
      e.ex[i] = expf(-(i - 32.0f) * (i - 32.0f) / 900.0f);
      e.sx[i] = sinf(i * 0.2f); e.cx[i] = cosf(i * 0.2f);
    }
    e.teinte = (int)(aleatoire() % 6);
    e.avance = 26;                                       // la premiere goutte est deja entree : 26 pas d'avance
    for (int k = 0; k < 8; k++, e.avance--) cr_encre_pas(e, 0.12f);
  }
  if (e.avance > 0) {                                    // le reste de l'avance, pendant que l'ecran s'allume
    for (int k = 0; k < 2 && e.avance > 0; k++, e.avance--) cr_encre_pas(e, 0.12f);
  }
  const float reste = cr_min(dt, 0.5f);
  const int n = (int)ceilf(reste * 15 - 1e-3f);
  for (int k = 0; k < n; k++) cr_encre_pas(e, reste / n);
  // la lumiere de l'encre, et ses deux halos : 0.7 L + 0.35 flou(L) + 0.2 flou3(L) = 0.7 L + flou(0.35 L + 0.2 flou2(L))
  float *sc = &scene[0][0][0];
  int ya = 64, yb = -1;
  for (int i = 0; i < 4096; i++) {
    if (!(e.m[i][0] | e.m[i][1] | e.m[i][2])) {
      sc[3 * i] = sc[3 * i + 1] = sc[3 * i + 2] = 0;
      e.av[i][0] = e.av[i][1] = e.av[i][2] = 0;
      continue;
    }
    float l[3] = {e.m[i][0] * (255 / CR_ENCRE_ECH), e.m[i][1] * (255 / CR_ENCRE_ECH), e.m[i][2] * (255 / CR_ENCRE_ECH)};
    cr_lumiere(l, 120);
    for (int j = 0; j < 3; j++) { sc[3 * i + j] = l[j]; e.av[i][j] = (uint16_t)(l[j] * 256 + 0.5f); }
    ya = min(ya, i >> 6); yb = max(yb, i >> 6);
  }
  const int y0 = max(0, ya - 3), y1 = min(64, yb + 4);   // les halos ne debordent pas de trois lignes
  if (yb >= 0) {
    cr_flou_rev(sc, 3, 2, 64, y0, y1);
    for (int i = y0 * 64; i < y1 * 64; i++)
      for (int j = 0; j < 3; j++) sc[3 * i + j] = 0.2f * sc[3 * i + j] + 0.35f / 256 * e.av[i][j];
    cr_flou_rev(sc, 3, 1, 64, y0, y1);
  }
  const float ph = t * 0.2f, sp = sinf(ph), cp = cosf(ph);
  for (int y = 0; y < 64; y++) {
    const float k = y / 64.0f, jour = expf(-y / 14.0f);
    const float sb = sinf(y * 0.08f), cb = cosf(y * 0.08f);
    const float sy = sb * cp + cb * sp, cy = cb * cp - sb * sp;   // sin et cos de y * 0.08 + t * 0.2
    for (int x = 0; x < 64; x++) {
      const float s = 0.5f + 0.5f * (e.sx[x] * cy + e.cx[x] * sy), s2 = s * s, rais = s2 * s2 * jour;   // un peu de jour, d'en haut
      const uint16_t *l = e.av[y * 64 + x];
      float *p = scene[y][x];
      p[0] += 10 - 7 * k + rais * 10 + 0.7f / 256 * l[0];
      p[1] += 16 - 11 * k + rais * 18 + 0.7f / 256 * l[1];
      p[2] += 34 - 21 * k + rais * 26 + 0.7f / 256 * l[2];
    }
  }
  for (int n2 = 0; n2 < e.ng; n2++) {                     // la goutte, encore ronde, qui tombe
    const CR_Goutte &g = e.g[n2];
    if (g.age >= 0.7f) continue;
    const float k = 1 - g.age / 0.7f;
    pointer(g.y, g.x, cr_min(255.0f, g.c[0] * 255 + 90) * k, cr_min(255.0f, g.c[1] * 255 + 90) * k, cr_min(255.0f, g.c[2] * 255 + 90) * k);
  }
}

// --- les courants de lumiere -------------------------------------------------------------------------------------

static const float CR_COURANTS[4][3] = {{30, 200, 190}, {60, 130, 255}, {170, 90, 255}, {255, 100, 170}};
static const int8_t CR_VAGUES[8][2] = {{1, 0}, {0, 1}, {1, 1}, {1, -1}, {2, 1}, {1, 2}, {2, -1}, {1, -2}};
const int CR_FLUX_N = 450;

// humeurs : 0 = (une seule ambiance)
struct E_flux {
  float trace[4096 * 3];                   // les trainees de lumiere
  float x[CR_FLUX_N], y[CR_FLUX_N], age[CR_FLUX_N], vie[CR_FLUX_N];
  float amp[8], w[8], ph[8];
  float decal;
  float petit[32 * 32 * 3];
};

// le courant en (x, y) a l'instant t : quelques grandes vagues de tourbillons, raccordees sur les bords
// (cos de kx X + ky Y + phase : la partie reelle de A^kx B^ky e^(i phase), avec A = e^(iX), B = e^(iY) -- les
// vecteurs d'onde sont de petits entiers : deux sinus au lieu de huit)
// (co : par vague, cos(phase) amp ky k, sin(phase) amp ky k, cos(phase) amp kx k, sin(phase) amp kx k)
inline void cr_flux_vitesse(const float (*co)[8], float x, float y, float &ux, float &uy) {
  const float k = PI2 / 64;
  const float ar = cr_cos(x * k), ai = cr_sin(x * k), br = cr_cos(y * k), bi = cr_sin(y * k);
  const float a2r = ar * ar - ai * ai, a2i = 2 * ar * ai, b2r = br * br - bi * bi, b2i = 2 * br * bi;
  float zr[8], zi[8];                                    // A, B, AB, A/B, A2 B, A B2, A2/B, A/B2
  zr[0] = ar; zi[0] = ai; zr[1] = br; zi[1] = bi;
  zr[2] = ar * br - ai * bi; zi[2] = ar * bi + ai * br;
  zr[3] = ar * br + ai * bi; zi[3] = ai * br - ar * bi;
  zr[4] = a2r * br - a2i * bi; zi[4] = a2r * bi + a2i * br;
  zr[5] = ar * b2r - ai * b2i; zi[5] = ar * b2i + ai * b2r;
  zr[6] = a2r * br + a2i * bi; zi[6] = a2i * br - a2r * bi;
  zr[7] = ar * b2r + ai * b2i; zi[7] = ai * b2r - ar * b2i;
  ux = 0; uy = 0;
  for (int v = 0; v < 8; v++) {
    ux += zr[v] * co[0][v] - zi[v] * co[1][v];
    uy -= zr[v] * co[2][v] - zi[v] * co[3][v];
  }
  const float s = sqrtf(ux * ux + uy * uy);
  const float m = 1 - cr_exp(-2 * s / 12.0f);            // tanh(s / 12)
  const float f = (3.0f + 15.0f * m / (2 - m)) / cr_max(s, 1e-6f);   // jamais tout a fait immobile
  ux *= f; uy *= f;
}

// un pas : les particules suivent le courant et deposent leur lumiere ; les trainees s'effacent (ou, pendant
// l'avance du debut, le depot est deja diminue de ce qu'il perdra d'ici la fin de l'avance : le meme resultat)
void cr_flux_pas(E_flux &e, float t, float h, bool efface = true, float garde = 1.0f) {
  float co[4][8];
  for (int v = 0; v < 8; v++) {
    const float ph = fmodf(e.w[v] * t + e.ph[v], PI2), a = e.amp[v] * (PI2 / 64);
    co[0][v] = cosf(ph) * a * CR_VAGUES[v][1]; co[1][v] = sinf(ph) * a * CR_VAGUES[v][1];
    co[2][v] = cosf(ph) * a * CR_VAGUES[v][0]; co[3][v] = sinf(ph) * a * CR_VAGUES[v][0];
  }
  if (efface) {
    const float k = cr_exp(-h * 0.55f);                  // les trainees s'effacent
    for (int i = 0; i < 4096 * 3; i++) e.trace[i] = cr_efface(e.trace[i], k);
  }
  const float depot = 1.5f / 255 * h * garde;
  for (int i = 0; i < CR_FLUX_N; i++) {
    float ux, uy;
    cr_flux_vitesse(co, e.x[i], e.y[i], ux, uy);
    float x = e.x[i] + ux * h, y = e.y[i] + uy * h;
    x -= 64 * floorf(x / 64); y -= 64 * floorf(y / 64);  // le courant se raccorde sur les bords
    e.x[i] = x; e.y[i] = y;
    e.age[i] += h;
    const float vit = sqrtf(ux * ux + uy * uy);         // (la vitesse, deja normalisee)
    const float vie = cr_clip01(cr_min(e.age[i] / 1.5f, (e.vie[i] - e.age[i]) / 1.5f));   // nees et eteintes en fondu
    float coul[3];
    cr_palette_rev(CR_COURANTS, 4, cr_atan2(uy, ux) / PI2 + e.decal, coul);   // la couleur dit ou va le courant
    const float p = vie * cr_max(0.04f, cr_min(1.8f, cr_exp(1.8f * cr_log(cr_max(vit, 1e-6f) / 12.0f)))) * depot;   // les vifs brillent
    if (p > 0) cr_tamponner3(e.trace, y, x, coul[0] * p, coul[1] * p, coul[2] * p);
    if (e.age[i] > e.vie[i]) { e.x[i] = hasard(0, 64); e.y[i] = hasard(0, 64); e.age[i] = 0; e.vie[i] = hasard(6, 12); }
  }
}

void s_flux(int humeur, bool debut, float t, float ecoule, float dt) {
  E_flux &e = etat_ecran<E_flux>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    for (int v = 0; v < 8; v++) {
      const float kx = CR_VAGUES[v][0], ky = CR_VAGUES[v][1];
      e.amp[v] = hasard(0.6f, 1.0f) / powf(cr_hypot(kx, ky), 1.3f) * (aleatoire() & 1 ? 1 : -1);
      e.w[v] = hasard(0.05f, 0.12f) * (aleatoire() & 1 ? 1 : -1);
      e.ph[v] = hasard(0, PI2);
    }
    double s2 = 0;                                       // une vitesse moyenne choisie
    const float k = PI2 / 64;
    for (int gy = 0; gy < 64; gy += 4)
      for (int gx = 0; gx < 64; gx += 4) {
        float ux = 0, uy = 0;
        for (int v = 0; v < 8; v++) {
          const float c = cosf((gx * CR_VAGUES[v][0] + gy * CR_VAGUES[v][1]) * k + e.ph[v]) * e.amp[v];
          ux += c * CR_VAGUES[v][1] * k; uy += c * CR_VAGUES[v][0] * k;
        }
        s2 += ux * ux + uy * uy;
      }
    const float norme = 11.0f / cr_max(1e-6f, sqrtf((float)(s2 / 256)));
    for (int v = 0; v < 8; v++) e.amp[v] *= norme;
    for (int i = 0; i < CR_FLUX_N; i++) {
      e.x[i] = hasard(0, 64); e.y[i] = hasard(0, 64); e.age[i] = hasard(0, 10); e.vie[i] = hasard(6, 12);
      e.age[i] = cr_min(e.age[i], e.vie[i] - 0.5f);
    }
    for (int j = 0; j < 36; j++)                         // les trainees sont deja la
      cr_flux_pas(e, t - 3.0f + j / 12.0f, 1 / 12.0f, false, expf(-0.55f / 12 * (35 - j)));
  }
  e.decal = 0.06f * sinf(t * 0.021f) + fmodf(t * 0.004f, 1.0f);
  const float reste = cr_min(dt, 0.5f);
  const int n = (int)ceilf(reste * 30 - 1e-3f);
  for (int j = 0; j < n; j++) cr_flux_pas(e, t - reste + (j + 1) * reste / n, reste / n);
  for (int i = 0; i < 4096; i++) {
    float l[3] = {e.trace[3 * i] * 255, e.trace[3 * i + 1] * 255, e.trace[3 * i + 2] * 255};
    cr_lumiere(l, 150);
    float *p = &scene[0][0][0] + 3 * i;
    p[0] = l[0]; p[1] = l[1]; p[2] = l[2];
  }
  cr_halo_rev(&scene[0][0][0], e.petit, 1, 0.15f);
  for (int y = 0; y < 64; y++) {
    const float k = y / 64.0f;
    for (int x = 0; x < 64; x++) { float *p = scene[y][x]; p[0] += 4 + 2 * k; p[1] += 5 - k; p[2] += 14; }
  }
}

// --- le kaleidoscope ---------------------------------------------------------------------------------------------

static const float CR_VERRES[7][3] = {{235, 40, 80}, {255, 150, 30}, {250, 210, 60}, {40, 190, 110}, {30, 140, 230},
                                      {120, 70, 230}, {220, 60, 190}};   // rubis, ambre, or, emeraude, saphir...

// humeurs : 0 = (une seule ambiance)
struct E_kaleidoscope {
  float th[4096], r[4096];                 // l'angle et la distance au centre de chaque pixel
  float r0[7], ra[7], wr[7], pr[7], wa[7], pa[7], h0[7];   // les verres : ou, combien, a quel rythme, de quel cote
};
void s_kaleidoscope(int humeur, bool debut, float t, float ecoule, float dt) {
  E_kaleidoscope &e = etat_ecran<E_kaleidoscope>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float s = PI2 / 6;
  if (debut) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float dx = x - 31.5f, dy = y - 31.5f;
        e.th[y * 64 + x] = atan2f(dy, dx);
        e.r[y * 64 + x] = sqrtf(dx * dx + dy * dy);
      }
    int perm[7] = {0, 1, 2, 3, 4, 5, 6};
    for (int i = 6; i > 0; i--) { const int j = aleatoire() % (i + 1); const int c = perm[i]; perm[i] = perm[j]; perm[j] = c; }
    for (int k = 0; k < 7; k++) {
      e.r0[k] = 7 + 33.0f * k / 6 + hasard(-2, 2); e.ra[k] = hasard(2.5f, 6);
      e.wr[k] = hasard(0.04f, 0.08f); e.pr[k] = hasard(0, PI2);
      e.wa[k] = hasard(0.03f, 0.065f); e.pa[k] = hasard(0, PI2);
      e.h0[k] = perm[k] / 7.0f + hasard(0, 0.05f);
    }
  }
  float su[8], sw[8], coul[8][3];
  const float glisse = fmodf(t * 0.005f, 1.0f);
  for (int k = 0; k < 7; k++) {                          // les verres glissent entre les miroirs
    const float sr = cr_max(4.0f, e.r0[k] + e.ra[k] * sinf(t * e.wr[k] + e.pr[k]));
    const float sa = s / 2 * (0.5f + 0.47f * sinf(t * e.wa[k] + e.pa[k]));
    su[k] = sr * cosf(sa); sw[k] = sr * sinf(sa);
    cr_palette_rev(CR_VERRES, 7, e.h0[k] + glisse, coul[k]);
  }
  su[7] = sw[7] = 0;                                     // et la rosace du centre, plus large
  cr_palette_rev(CR_VERRES, 7, 0.37f + glisse, coul[7]);
  float inv[8][8];
  for (int p = 0; p < 8; p++)
    for (int q = 0; q < 8; q++) inv[p][q] = 1.0f / (2 * cr_max(cr_hypot(su[p] - su[q], sw[p] - sw[q]), 1e-3f));
  const float rot = t * 0.025f;
  float cb[6], sb[6];
  for (int j = 0; j < 6; j++) { cb[j] = cosf(rot + j * s + s / 2); sb[j] = sinf(rot + j * s + s / 2); }
  const float vphase = t * 0.3f, is = 1.0f / s;
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const float dx = x - 31.5f, dy = y - 31.5f, r = e.r[i];
      int j = (int)floorf((e.th[i] - rot) * is) % 6;       // replie dans un secteur, en miroir
      if (j < 0) j += 6;
      const float u = dx * cb[j] + dy * sb[j], w = fabsf(dy * cb[j] - dx * sb[j]);
      float d1 = 1e30f, d2 = 1e30f;
      int p = 0, q = 0;
      for (int k = 0; k < 8; k++) {
        const float a = u - su[k], b = w - sw[k];
        const float d = a * a + b * b - (k == 7 ? 30.0f : 0.0f);
        if (d < d1) { d2 = d1; q = p; d1 = d; p = k; }
        else if (d < d2) { d2 = d; q = k; }
      }
      const float plomb = cr_clip01(((d2 - d1) * inv[p][q] - 0.3f) / 0.8f);   // le plomb, entre deux verres
      const float eclat = 0.55f + 0.45f * cr_exp(-sqrtf(cr_max(d1 + (p == 7 ? 30.0f : 0.0f), 0.0f)) / 7.0f);
      const float vague = 0.78f + 0.22f * cr_sin(r * 0.16f - vphase);   // la lumiere derriere, qui respire
      const float k = eclat * vague * plomb, ombre = cr_max(0.45f, cr_min(1.0f, 1.25f - r / 44.0f));
      const float f = 1 - plomb;
      peindre(y, x, (coul[p][0] * k + 6 * f) * ombre, (coul[p][1] * k + 5 * f) * ombre, (coul[p][2] * k + 9 * f) * ombre);
    }
}

// --- le pendule de sable -----------------------------------------------------------------------------------------

static const float CR_DESSINS[8][5] = {   // rapport des deux mouvements, sens du second, desaccord, part du premier, rotation
  {4, -1, 0.05f, 0.6f, 0}, {5, -1, 0.08f, 0.65f, 0}, {3, -1, 0.12f, 0.55f, 0}, {4, -1, 0, 0.6f, 0.09f},
  {5, -1, 0, 0.65f, 0.07f}, {3.5f, -1, 0.04f, 0.55f, 0}, {4, -1, 0.1f, 0.6f, 0}, {6, -1, 0.035f, 0.7f, 0}};
static const float CR_SABLES[5][3] = {{255, 196, 120}, {255, 140, 170}, {120, 205, 255}, {190, 160, 255}, {140, 240, 190}};
const float CR_PENDULE_DUREE = 44.0f;

// humeurs : 0 = (une seule ambiance)
struct E_pendule {
  float trace[2][4096];                    // le dessin en cours, et l'ancien qui s'efface
  float frais[4096];                       // le sable tout juste tombe
  uint16_t sable[4096][3];                 // le sable, sous une lampe (x 256)
  float w[2], a[2], p[2], sens, d[2], rot, c[3], cancien[3];
  float tau;
  int dessin, teinte, cur;
  bool ancien;
};

void cr_pendule_nouveau(E_pendule &e) {
  const float *m = CR_DESSINS[e.dessin % 8];
  e.dessin += 1 + (int)(aleatoire() % 2);
  const float w = hasard(0.6f, 0.7f);
  e.w[0] = w; e.w[1] = w * m[0] * (1 + m[2] * hasard(0.8f, 1.2f));
  e.a[0] = 27.5f * m[3]; e.a[1] = 27.5f * (1 - m[3]);
  e.p[0] = hasard(0, PI2); e.p[1] = hasard(0, PI2);
  e.sens = m[1];
  const float k = hasard(0.9f, 1.1f);
  e.d[0] = 0.026f * k; e.d[1] = 0.04f * k;
  e.rot = m[4] * (aleatoire() & 1 ? 1 : -1);
  for (int j = 0; j < 3; j++) e.c[j] = CR_SABLES[e.teinte % 5][j];
  e.teinte++;
  e.tau = -1.5f;                                         // une pause : l'ancien commence a s'effacer
  e.cur = 1 - e.cur;
  for (int i = 0; i < 4096; i++) e.trace[e.cur][i] = 0;
}

// ou tombe le sable a l'instant tau : deux mouvements en rond qui s'amortissent, et le tout qui tourne
inline void cr_pendule_point(const E_pendule &e, float tau, float &y, float &x) {
  float X = 0, Y = 0;
  for (int k = 0; k < 2; k++) {
    const float env = e.a[k] * cr_exp(-e.d[k] * tau), ph = e.w[k] * tau + e.p[k];
    X += env * cr_sin(ph);
    Y += env * (k == 0 ? cr_cos(ph) : e.sens * cr_cos(ph));   // sin(ph + sens * pi/2)
  }
  const float c = cr_cos(e.rot * tau), s = cr_sin(e.rot * tau);
  y = 31.5f + X * s + Y * c;
  x = 31.5f + X * c - Y * s;
}

void cr_pendule_tracer(E_pendule &e, float jusqu_a) {   // un trait continu, sans trous
  const float debut = cr_max(0.0f, e.tau);
  if (jusqu_a <= debut) { e.tau = jusqu_a; return; }
  const float vmax = e.a[0] * e.w[0] + e.a[1] * e.w[1] + 30 * fabsf(e.rot);
  const int n = (int)ceilf((jusqu_a - debut) * vmax / 0.35f) + 1;
  float py, px;
  cr_pendule_point(e, debut, py, px);
  for (int i = 1; i <= n; i++) {
    float y, x;
    cr_pendule_point(e, debut + (jusqu_a - debut) * i / n, y, x);
    const float pas = cr_hypot(y - py, x - px);
    cr_tamponner1(e.trace[e.cur], y, x, pas);
    cr_tamponner1(e.frais, y, x, pas);
    py = y; px = x;
  }
  e.tau = jusqu_a;
}

void s_pendule(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pendule &e = etat_ecran<E_pendule>(debut);
  (void)humeur; (void)ecoule; (void)t;
  if (debut) {
    e.dessin = (int)(aleatoire() % 8);
    e.teinte = (int)(aleatoire() % 5);
    cr_pendule_nouveau(e);
    cr_pendule_tracer(e, 12.0f);                         // le dessin a deja commence
    for (int i = 0; i < 4096; i++) e.frais[i] = 0;
    uint16_t *b = e.sable[0];                            // (le grain du sable, le temps du semis)
    brume_n(b, 64, 4);
    for (int i = 4095; i >= 0; i--) {                    // a l'envers : on lit b[i] avant d'ecrire sable[i]
      const float g = 0.8f + 0.4f * b[i] / 65535.0f;
      const float dx = (i & 63) - 31.5f, dy = (i >> 6) - 31.5f;
      const float l = cr_clip01(1 - sqrtf(dx * dx + dy * dy) / 50), lampe = l * sqrtf(l);
      e.sable[i][0] = (uint16_t)((10 + lampe * 34) * g * 256);
      e.sable[i][1] = (uint16_t)((8 + lampe * 24) * g * 256);
      e.sable[i][2] = (uint16_t)((8 + lampe * 15) * g * 256);
    }
  }
  const float pas = cr_min(dt, 0.5f);
  if (e.tau + pas > CR_PENDULE_DUREE) {                  // fini : il s'efface, un autre commence
    e.ancien = true;
    for (int j = 0; j < 3; j++) e.cancien[j] = e.c[j];
    cr_pendule_nouveau(e);
  }
  const float frais = cr_exp(-pas * 1.6f);
  for (int i = 0; i < 4096; i++) e.frais[i] = cr_efface(e.frais[i], frais);
  cr_pendule_tracer(e, e.tau + pas);
  const float fondu = cr_min(1.0f, cr_max(0.0f, e.tau) / 2.0f);
  const float cm = cr_max(e.c[0], cr_max(e.c[1], e.c[2])), k1 = cm / 170, kc = 255 / cm;
  const float ca = cr_max(e.cancien[0], cr_max(e.cancien[1], e.cancien[2])), k2 = ca / 170, ka = 255 / ca;
  const float efface = cr_exp(-pas * 0.5f);
  float *ancien = e.trace[1 - e.cur], plus = 0;
  for (int i = 0; i < 4096; i++) {
    float *o = &scene[0][0][0] + 3 * i;
    o[0] = e.sable[i][0] * (1 / 256.0f); o[1] = e.sable[i][1] * (1 / 256.0f); o[2] = e.sable[i][2] * (1 / 256.0f);
    const float l = (e.trace[e.cur][i] * 0.6f + e.frais[i] * 0.9f) * fondu;
    if (l > 0) {                                         // _reveries_lumiere d'une seule couleur
      const float v = (1 - cr_exp(-l * k1)) * kc;
      o[0] += e.c[0] * v; o[1] += e.c[1] * v; o[2] += e.c[2] * v;
    }
    if (e.ancien) {
      ancien[i] = cr_efface(ancien[i], efface);
      plus = cr_max(plus, ancien[i]);
      const float la = ancien[i] * 0.6f;
      if (la > 0) {
        const float v = (1 - cr_exp(-la * k2)) * ka;
        o[0] += e.cancien[0] * v; o[1] += e.cancien[1] * v; o[2] += e.cancien[2] * v;
      }
    }
  }
  if (e.ancien && plus < 0.02f) e.ancien = false;
  float y, x;                                            // la ou le sable tombe : une petite lueur
  cr_pendule_point(e, cr_max(0.0f, e.tau), y, x);
  const float g[3] = {cr_min(255.0f, e.c[0] * 0.6f + 100), cr_min(255.0f, e.c[1] * 0.6f + 100), cr_min(255.0f, e.c[2] * 0.6f + 100)};
  for (int yy = max(0, (int)y - 8); yy <= min(63, (int)y + 9); yy++)
    for (int xx = max(0, (int)x - 8); xx <= min(63, (int)x + 9); xx++) {
      const float d2 = (xx - x) * (xx - x) + (yy - y) * (yy - y);
      if (d2 < 70) ajouter(yy, xx, cr_exp(-d2 / 5.0f) * 0.35f * fondu, g[0], g[1], g[2]);
    }
}

// --- le flocon qui pousse ----------------------------------------------------------------------------------------

const float CR_FLOCON_CYCLE = 42.0f, CR_FLOCON_POUSSE = 24.0f, CR_FLOCON_FONTE = 34.0f;   // il pousse, il brille, il fond
static const float CR_GLACE[4][3] = {{150, 210, 255}, {130, 190, 255}, {170, 200, 255}, {120, 225, 255}};

struct CR_Flocon {
  float naissance, R, plaque, bout, epais, rot, teinte[3], eclats[6];
  float pos[5], L[5];                      // ses branches : ou, combien
  float ram[10][3];                        // leurs rameaux : (branche, ou, combien)
  int nb, nram;
};

// humeurs : 0 = (une seule ambiance)
struct E_flocon {
  float th[4096];                          // l'angle de chaque pixel autour du centre
  CR_Flocon f[2];
  int nf;
  float horloge;
  float nx[22], ny[22], nv[22];            // quelques flocons flous, au loin
};

void cr_flocon_nouveau(CR_Flocon &f, float naissance) {
  f.naissance = naissance;
  f.R = hasard(23.5f, 27.5f);
  const int genre = (int)(aleatoire() % 4);              // sapin, fougere, etoile, plume
  f.plaque = genre == 2 ? hasard(5.0f, 7.0f) : hasard(2.5f, 5.5f);   // l'etoile : une large plaque au coeur
  f.nb = genre != 2 ? 3 + (int)(aleatoire() % 3) : 3 + (int)(aleatoire() % 2);
  for (int k = 0; k < f.nb; k++) f.pos[k] = f.plaque + 3 + (f.R - 4 - f.plaque - 3) * k / (f.nb - 1) + hasard(-1, 1);
  const float u = genre == 0 ? hasard(0.6f, 0.8f) : genre == 1 ? hasard(0.35f, 0.45f) : genre == 3 ? hasard(0.45f, 0.6f) : 0;
  for (int k = 0; k < f.nb; k++) {
    float L;
    if (genre == 0) L = (f.R - f.pos[k]) * u;
    else if (genre == 1) L = sinf(3.14159265f * (f.pos[k] - f.plaque) / (f.R - f.plaque)) * f.R * u;
    else if (genre == 2) L = hasard(3.0f, 6.0f);
    else L = f.pos[k] * u;
    f.L[k] = cr_min(L, f.pos[k] * 0.9f);
  }
  f.nram = 0;
  if (genre != 2)
    for (int k = 0; k < f.nb; k++)
      for (float m : {0.45f, 0.75f})
        if (f.L[k] * m > 3) { f.ram[f.nram][0] = k; f.ram[f.nram][1] = f.L[k] * m; f.ram[f.nram][2] = f.L[k] * hasard(0.22f, 0.32f); f.nram++; }
  if (genre == 2) f.bout = hasard(2.2f, 3.0f);
  else f.bout = hasard(0, 1) < 0.35f ? hasard(1.5f, 2.4f) : 0.0f;
  f.epais = hasard(0.45f, 0.75f);
  f.rot = hasard(0, 3.14159265f / 3);
  const float *c = CR_GLACE[aleatoire() % 4];
  for (int j = 0; j < 3; j++) f.teinte[j] = c[j];
  for (int j = 0; j < 6; j++) f.eclats[j] = hasard(0, PI2);
}

// la distance (signee) a un hexagone pointe le long du bras, centre en (cx, 0)
inline float cr_hexagone(float u, float w, float cx, float r) {
  float px = fabsf(u - cx), py = fabsf(w);
  const float k = cr_min(-0.866025f * px + 0.5f * py, 0.0f);   // replie sur un sixieme d'hexagone
  px += 2 * k * 0.866025f; py -= 2 * k * 0.5f;
  const float qx = px - cr_max(-0.57735f * r, cr_min(0.57735f * r, px)), qy = py - r;
  const float d = sqrtf(qx * qx + qy * qy);
  return qy > 0 ? d : qy < 0 ? -d : 0.0f;
}

void cr_flocon_dessiner(E_flocon &e, const CR_Flocon &f, float age, float t) {
  const float g = 1 - cr_clip01(age / CR_FLOCON_POUSSE);
  const float pousse = 1 - powf(g, 2.2f);                 // vite au debut, puis il ralentit
  const float fonte = cr_clip01((age - CR_FLOCON_FONTE) / (CR_FLOCON_CYCLE - CR_FLOCON_FONTE));
  const float rot = f.rot + t * 0.012f, s = 3.14159265f / 3;
  const float retrait = 1 - 0.25f * fonte;
  const float R = cr_max(0.5f, f.R * pousse * retrait);
  const float ep = f.epais * (1 - 0.55f * fonte);
  float bx[5], bl[5], ext = R;                          // les branches (depuis le bras, a 60 degres)
  int nb = 0;
  for (int k = 0; k < f.nb; k++) {
    const float l = powf(cr_clip01((f.R * pousse - f.pos[k]) / (f.L[k] * 1.1f + 1.5f)), 0.8f) * f.L[k] * retrait;
    if (l > 0.05f) { bx[nb] = f.pos[k] * retrait; bl[nb] = l; nb++; }
    ext = cr_max(ext, cr_hypot(f.pos[k] * retrait + 0.5f * l, 0.866025f * l));
  }
  float rx[10], ry[10], rl[10];
  int nr = 0;
  for (int n = 0; n < f.nram; n++) {
    const int k = (int)f.ram[n][0];
    const float m = f.ram[n][1], l = f.ram[n][2];
    const float lk0 = powf(cr_clip01((f.R * pousse - f.pos[k]) / (f.L[k] * 1.1f + 1.5f)), 0.8f) * f.L[k];
    const float lk = cr_clip01((lk0 - m) / (l * 1.1f + 1.0f)) * l * retrait;
    if (lk > 0.05f) {
      rx[nr] = f.pos[k] * retrait + 0.5f * m * retrait; ry[nr] = 0.866025f * m * retrait; rl[nr] = lk;
      ext = cr_max(ext, cr_hypot(rx[nr] + lk, ry[nr]));
      nr++;
    }
  }
  const float plaque = f.plaque * cr_min(1.0f, age / 3.0f + 0.15f) * retrait;
  const bool a_bout = f.bout > 0 && pousse > 0.6f;
  const float b = a_bout ? f.bout * cr_clip01((pousse - 0.6f) / 0.3f) * retrait : 0.0f;
  ext = cr_max(ext, cr_max(plaque, R + b) * 1.16f) + ep * 1.2f;
  const float vie = powf(1 - fonte, 1.4f);
  const float echelle = 1.6f + 2.5f * fonte, ie = 1.0f / echelle;
  const float ah = (0.55f + 0.6f * fonte) * vie * (0.5f + 0.5f * pousse) * 0.28f;   // le halo, sa force
  const float portee = echelle * logf(cr_max(1.0f, ah * 255 / 0.05f)) + 1;   // au-dela, le halo ne se voit plus
  const float rmax = ext + portee, rmax2 = rmax * rmax;
  const float hs = s / 2, ihs = 1.0f / hs;
  float cb[12], sb[12], sg[12];                          // les douze demi-secteurs : vers le bras le plus proche
  for (int h = 0; h < 12; h++) {
    const float beta = rot + ((h + 1) / 2) * s;
    cb[h] = cosf(beta); sb[h] = sinf(beta); sg[h] = h % 2 ? -1.0f : 1.0f;
  }
  const float *c = f.teinte;
  const float balaye0 = age * 0.45f;
  const float iR = 1.0f / cr_max(R, 1.0f);
  for (int y = 0; y < 64; y++) {
    const float dy = y - 31.5f;
    for (int x = 0; x < 64; x++) {
      const float dx = x - 31.5f;
      if (dx * dx + dy * dy > rmax2) continue;
      const int i = y * 64 + x;
      int h = (int)floorf((e.th[i] - rot) * ihs) % 12;     // 0 sur un bras, pi/6 entre deux bras
      if (h < 0) h += 12;
      const float u = dx * cb[h] + dy * sb[h], w = sg[h] * (dy * cb[h] - dx * sb[h]);
      const float qa = cr_max(0.0f, cr_min(R, u));
      float d = sqrtf((u - qa) * (u - qa) + w * w) - ep * (1.15f - 0.4f * cr_clip01(u * iR));
      float m2 = 1e30f;
      for (int k = 0; k < nb; k++) {
        const float q = cr_max(0.0f, cr_min(bl[k], (u - bx[k]) * 0.5f + w * 0.866025f));
        const float a1 = u - bx[k] - 0.5f * q, a2 = w - 0.866025f * q;
        m2 = cr_min(m2, a1 * a1 + a2 * a2);
      }
      if (nb) d = cr_min(d, sqrtf(m2) - ep * 0.8f);
      m2 = 1e30f;
      for (int k = 0; k < nr; k++) {
        const float a2 = w - ry[k];
        if (a2 * a2 >= m2) continue;
        const float q = cr_max(0.0f, cr_min(rl[k], u - rx[k]));
        const float a1 = u - rx[k] - q;
        m2 = cr_min(m2, a1 * a1 + a2 * a2);
      }
      if (nr) d = cr_min(d, sqrtf(m2) - ep * 0.6f);
      const float hp = cr_hexagone(u, w, 0, plaque);
      d = cr_min(d, fabsf(hp) - ep * 0.7f);                 // le bord de la plaque
      float remplir = 0;
      if (hp < 0.5f) {                                    // un hexagone dans la plaque
        const float arete = cr_clip01(1 - fabsf(cr_hexagone(u, w, 0, plaque * 0.5f)) / 0.8f);
        remplir = cr_clip01(0.5f - hp) * (0.32f + 0.25f * arete);
      }
      if (a_bout) {
        const float hb = cr_hexagone(u, w, R, b);
        d = cr_min(d, fabsf(hb) - ep * 0.6f);
        remplir = cr_max(remplir, cr_clip01(0.5f - hb) * 0.35f);
      }
      const float trait = cr_max(cr_clip01(0.5f - d), remplir) * vie;
      const float halo = cr_exp(-cr_max(d, 0.0f) * ie) * ah;
      float *o = scene[y][x];
      o[0] += halo * c[0]; o[1] += halo * c[1]; o[2] += halo * c[2];
      if (trait > 0) {
        float bal = e.th[i] - balaye0;                   // un reflet qui fait le tour
        bal -= PI2 * floorf(bal / PI2);
        const float q = (bal - 3.14159265f) / 0.5f, k = trait * (1 + 0.55f * cr_exp(-q * q)), blanc = 60 * trait;
        o[0] += k * (c[0] * 0.75f + blanc); o[1] += k * (c[1] * 0.75f + blanc); o[2] += k * (c[2] * 0.75f + blanc);
      }
    }
  }
  for (int j = 0; j < 6; j++) {                          // les pointes scintillent, chacune a son tour
    const float sn = cr_clip01(sinf(t * 0.8f + f.eclats[j])), s2 = sn * sn, s4 = s2 * s2, s8 = s4 * s4;
    const float k = s8 * s2 * vie * cr_min(1.0f, R / 15);
    if (k <= 0.02f) continue;
    const float py = 31.5f + R * sinf(rot + j * s), px = 31.5f + R * cosf(rot + j * s);
    cr_tamponner(py, px, 255 * k, 255 * k, 255 * k);
    cr_tamponner(py - 1, px, 150 * k, 200 * k, 255 * k);
    cr_tamponner(py + 1, px, 150 * k, 200 * k, 255 * k);
    cr_tamponner(py, px - 1, 150 * k, 200 * k, 255 * k);
    cr_tamponner(py, px + 1, 150 * k, 200 * k, 255 * k);
  }
}

void s_flocon(int humeur, bool debut, float t, float ecoule, float dt) {
  E_flocon &e = etat_ecran<E_flocon>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) e.th[y * 64 + x] = atan2f(y - 31.5f, x - 31.5f);
    e.horloge = 14.0f;
    e.nf = 1;
    cr_flocon_nouveau(e.f[0], 0.0f);
    for (int i = 0; i < 22; i++) { e.nx[i] = hasard(0, 64); e.ny[i] = hasard(0, 64); e.nv[i] = hasard(1.0f, 2.5f); }
  }
  const float pas = cr_min(dt, 0.5f);
  e.horloge += pas;
  const float c = e.horloge;
  if (c - e.f[e.nf - 1].naissance >= CR_FLOCON_CYCLE - 2.0f && e.nf < 2) {   // le suivant pousse quand l'autre a fondu
    cr_flocon_nouveau(e.f[e.nf], c);
    e.nf++;
  }
  int garde = 0;
  for (int n = 0; n < e.nf; n++) if (c - e.f[n].naissance < CR_FLOCON_CYCLE) e.f[garde++] = e.f[n];
  e.nf = garde;
  for (int y = 0; y < 64; y++) {
    const float k = y / 64.0f;
    for (int x = 0; x < 64; x++) peindre(y, x, 3 + 5 * k, 6 + 6 * k, 20 + 12 * k);
  }
  // quelques flocons flous, au loin : chacun pose entre les pixels, puis flou [1 2 1] (bords recopies)
  static const float B3[3] = {0.25f, 0.5f, 0.25f};
  for (int i = 0; i < 22; i++) {
    e.ny[i] += e.nv[i] * pas;
    e.ny[i] -= 66 * floorf(e.ny[i] / 66);
    float px = e.nx[i] + 2 * sinf(t * 0.3f + e.nx[i]);
    px -= 64 * floorf(px / 64);
    const float py = cr_max(-1.0f, cr_min(63.99999f, e.ny[i] - 1));
    const float fy0 = floorf(py), fx0 = floorf(px);
    const int y0 = (int)fy0, x0 = (int)fx0;
    const float fy = py - fy0, fx = px - fx0;
    for (int a = 0; a < 2; a++)
      for (int bb = 0; bb < 2; bb++) {
        const int yy = y0 + a, xx = x0 + bb;
        if (yy < 0 || yy > 63 || xx < 0 || xx > 63) continue;
        const float wgt = (a ? fy : 1 - fy) * (bb ? fx : 1 - fx);
        for (int oy = -1; oy <= 1; oy++)
          for (int ox = -1; ox <= 1; ox++) {
            const float k = wgt * B3[oy + 1] * B3[ox + 1];
            ajouter(max(0, min(63, yy + oy)), max(0, min(63, xx + ox)), k, 40, 55, 80);
          }
      }
  }
  for (int n = 0; n < e.nf; n++) cr_flocon_dessiner(e, e.f[n], c - e.f[n].naissance, t);
}

// --- le vortex de lumiere ----------------------------------------------------------------------------------------

static const float CR_VORTEX[5][3] = {{80, 140, 255}, {170, 80, 255}, {255, 80, 170}, {255, 180, 80}, {60, 220, 230}};
const int CR_VORTEX_N = 1200;
const float CR_VORTEX_LOIN = 16.0f, CR_VORTEX_PRES = 0.4f, CR_VORTEX_VITESSE = 0.08f;   // tours de tunnel par seconde

// humeurs : 0 = (une seule ambiance)
struct E_vortex {
  float a0[CR_VORTEX_N], rr[CR_VORTEX_N], q0[CR_VORTEX_N], vk[CR_VORTEX_N], lum0[CR_VORTEX_N];   // angle, rayon, ou, vitesse, eclat
  float cd[CR_VORTEX_N], sd[CR_VORTEX_N], iro[CR_VORTEX_N], sig[CR_VORTEX_N];   // d'un point de la trainee au suivant
  float iro11[CR_VORTEX_N];                // ... et du premier au dernier
  float poids[12];                         // l'eclat le long de la trainee
  float petit[32 * 32 * 3];
  float loin[4096];                        // exp(-d / 26) autour de la lueur, pour le fond
  float t78[200];                          // exp(-d / 78), d de 0 a 99.5 par demi-pixel
  float tg[330];                           // exp(-u^2), u^2 de 0 a 20.5 par seizieme
};
void s_vortex(int humeur, bool debut, float t, float ecoule, float dt) {
  E_vortex &e = etat_ecran<E_vortex>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float etendue = logf(CR_VORTEX_PRES / CR_VORTEX_LOIN), lloin = logf(CR_VORTEX_LOIN);
  if (debut) {
    for (int i = 0; i < CR_VORTEX_N; i++) {
      e.a0[i] = hasard(0, PI2);
      const float u1 = hasard(1e-7f, 1), u2 = hasard(0, PI2);   // une loi normale (Box-Muller)
      e.rr[i] = 14.0f * cr_max(0.45f, cr_min(1.5f, 1 + 0.16f * sqrtf(-2 * logf(u1)) * cosf(u2)));   // (x 14)
      e.q0[i] = hasard(0, 1);
      e.vk[i] = hasard(0.85f, 1.15f);
      const float l = hasard(0.3f, 1.0f);
      e.lum0[i] = l * sqrtf(l);
      // le long de la trainee (retard 0.05 s par point) : l'angle tourne, la profondeur recule, l'eclat baisse
      const float delta = -0.05f * (0.15f - CR_VORTEX_VITESSE * e.vk[i] * etendue);
      const float lrho = -0.05f * CR_VORTEX_VITESSE * e.vk[i] * etendue;
      e.cd[i] = cosf(delta); e.sd[i] = sinf(delta);
      e.iro[i] = expf(-lrho); e.sig[i] = expf(-1.3f * lrho); e.iro11[i] = expf(-11 * lrho);
    }
    for (int j = 0; j < 12; j++) { const float k = 1 - j / 12.0f; e.poids[j] = k * sqrtf(k); }
    for (int k = 0; k < 200; k++) e.t78[k] = expf(-k * 0.5f / 78.0f);
    for (int k = 0; k < 330; k++) e.tg[k] = expf(-k / 16.0f);
  }
  const float bx = 9 * sinf(t * 0.071f), by = 7 * sinf(t * 0.053f + 1.0f);   // le tunnel se courbe
  const float avance = fmodf(t * CR_VORTEX_VITESSE, 1.0f);
  const float derive = fmodf(t * 0.013f, 1.0f);          // les couleurs glissent : jamais le meme tour
  const float tour = t * 0.15f;
  for (int i = 0; i < 4096 * 3; i++) (&scene[0][0][0])[i] = 0;
  for (int i = 0; i < CR_VORTEX_N; i++) {                // chaque etincelle et sa trainee
    float propre = t * CR_VORTEX_VITESSE * (e.vk[i] - 1);
    propre -= floorf(propre);
    float q = e.q0[i] + avance + propre;
    q -= floorf(q);                                      // chacune a sa vitesse, sans saut au bouclage
    const float fondu = cr_clip01((q - 0.33f) / 0.32f), f15 = fondu * sqrtf(fondu) * cr_clip01((1 - q) / 0.06f);
    if (f15 <= 0) continue;                              // au fond : la lueur seule
    // (q > 0.33 : la trainee, 11 x 0.05 s en arriere, ne traverse jamais le bouclage)
    const float bande = q - avance;                      // la place dans le tunnel : les anneaux
    const float an = 0.5f + 0.5f * cr_cos(PI2 * bande * 5), an2 = an * an;
    const float base = e.lum0[i] * f15 * (0.15f + 0.85f * an2 * an2);
    float coul[3];
    cr_palette_rev(CR_VORTEX, 5, bande * 2.0f + derive, coul);
    const float lz = lloin + q * etendue;                // log de la profondeur
    float iz = cr_exp(-lz);
    float g = cr_exp(1.3f * (0.693147f - lz));            // (2 / z)^1.3
    const float th = e.a0[i] + tour - lz;                // une spirale, plus serree au fond
    float cs = cr_cos(th), sn = cr_sin(th);
    // la courbure du tunnel, (1 - PRES / z)^1.5 : exacte aux deux bouts de la trainee, lineaire entre
    const float ta = 1 - CR_VORTEX_PRES * iz, tb = 1 - CR_VORTEX_PRES * iz * e.iro11[i];
    const float ka = ta * sqrtf(ta), dk = (tb * sqrtf(tb) - ka) * (1.0f / 11);
    const float cd = e.cd[i], sd = e.sd[i], iro = e.iro[i], sig = e.sig[i], rr = e.rr[i];
    const float c0 = coul[0] * 0.7f * base, c1 = coul[1] * 0.7f * base, c2 = coul[2] * 0.7f * base;
    for (int j = 0; j < 12; j++) {
      const float k = ka + dk * j, rayon = rr * iz;
      const float y = 31.5f + by * k + rayon * sn, x = 31.5f + bx * k + rayon * cs;
      const int yi = (int)(y + 64.0f) - 64, xi = (int)(x + 64.0f) - 64;   // floor (|y|, |x| < 64 + 52)
      if ((unsigned)yi < 63u && (unsigned)xi < 63u) {     // le cas courant : les quatre voisins dans le panneau
        const float l = cr_min(g, 2.5f) * e.poids[j];   // de pres plus vives
        const float fy = y - yi, fx = x - xi, ly = l * fy, lh = l - ly;
        const float a = lh - lh * fx, c = lh * fx, d = ly - ly * fx, w = ly * fx;
        float *p = scene[yi][xi], *u = p + 192;
        p[0] += a * c0; p[1] += a * c1; p[2] += a * c2; p[3] += c * c0; p[4] += c * c1; p[5] += c * c2;
        u[0] += d * c0; u[1] += d * c1; u[2] += d * c2; u[3] += w * c0; u[4] += w * c1; u[5] += w * c2;
      } else if (yi >= -1 && yi <= 63 && xi >= -1 && xi <= 63) {
        const float l = cr_min(g, 2.5f) * e.poids[j];
        cr_tamponner(y, x, c0 * l, c1 * l, c2 * l);
      }
      const float c2 = cs * cd - sn * sd;
      sn = sn * cd + cs * sd; cs = c2;
      iz *= iro; g *= sig;
    }
  }
  const float fx = 31.5f + bx, fy = 31.5f + by;
  for (int k = 0; k < 5; k++) {                          // les anneaux de lumiere qui passent
    float qa = k / 5.0f + avance;
    qa -= floorf(qa);
    const float f = cr_clip01(qa / 0.2f) * cr_clip01((1 - qa) / 0.25f) * 0.45f;
    if (f <= 0) continue;
    const float z = CR_VORTEX_LOIN * expf(qa * etendue), t1 = 1 - CR_VORTEX_PRES / z, kk = t1 * sqrtf(t1);
    const float rayon = 14.0f / z, large = 0.6f + rayon * 0.05f, il = 1.0f / large;
    const float cx = 31.5f + bx * kk, cy = 31.5f + by * kk;
    float teinte[3];
    cr_palette_rev(CR_VORTEX, 5, k / 5.0f * 2.0f + derive, teinte);
    const float ext = rayon + 4.5f * large, inte = cr_max(0.0f, rayon - 4.5f * large);
    for (int y = max(0, (int)(cy - ext)); y <= min(63, (int)(cy + ext) + 1); y++) {
      const float dy = y - cy, dy2 = dy * dy;
      if (dy2 > ext * ext) continue;
      const float xo = sqrtf(ext * ext - dy2), xi = inte * inte > dy2 ? sqrtf(inte * inte - dy2) : -1.0f;
      for (int x = max(0, (int)(cx - xo)); x <= min(63, (int)(cx + xo) + 1); x++) {
        const float dx = x - cx;
        if (fabsf(dx) < xi) continue;                    // le trou de l'anneau
        const float u = (sqrtf(dx * dx + dy2) - rayon) * il, q = u * u * 16;
        if (q >= 328) continue;                          // exp(-20.5) : rien
        const int qi = (int)q;
        const float a = (e.tg[qi] + (e.tg[qi + 1] - e.tg[qi]) * (q - qi)) * f;
        float *o = scene[y][x];
        o[0] += a * teinte[0]; o[1] += a * teinte[1]; o[2] += a * teinte[2];
      }
    }
  }
  // la lueur au fond, puis la lumiere qui sature (_reveries_lumiere), dans le meme passage
  const float souffle = 0.85f + 0.15f * sinf(t * 0.5f);
  float fondc[3];
  cr_palette_rev(CR_VORTEX, 5, -avance * 2.0f + derive, fondc);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float d = cr_hypot(x - fx, y - fy);
      float *o = scene[y][x];
      const float dq = d * 2;                            // (d < 91 : dans la table)
      const int di = (int)dq;
      const float e1 = e.t78[di] + (e.t78[di + 1] - e.t78[di]) * (dq - di), e3 = e1 * e1 * e1, e4 = e3 * e1, e8 = e4 * e4;   // exp(-d/78)^n
      e.loin[y * 64 + x] = e3;                           // exp(-d / 26), pour le fond
      const float a = e8 * e4 * e1 * 0.35f * souffle;     // exp(-d / 6)
      o[0] += a * fondc[0]; o[1] += a * fondc[1]; o[2] += a * fondc[2];
      if (d < 16) { const float b = cr_exp(-d / 1.6f) * 1.4f * souffle; o[0] += b * 235; o[1] += b * 225; o[2] += b * 255; }
      cr_lumiere(o, 200);
    }
  // son halo, et le fond, une lueur violette autour du bout du tunnel
  for (int y = 0; y < 32; y++)
    for (int x = 0; x < 32; x++)
      for (int c = 0; c < 3; c++) {
        const float *p = &scene[2 * y][2 * x][c];
        e.petit[(y * 32 + x) * 3 + c] = (p[0] + p[3] + p[192] + p[195]) * 0.25f;
      }
  cr_flou_rev(e.petit, 3, 2, 32);
  static const float f0[3] = {3, 2, 10}, f1[3] = {12, 6, 26};   // et le fond : une lueur violette au bout du tunnel
  cr_agrandir(e.petit, 0.3f, nullptr, e.loin, f0, f1);
}
