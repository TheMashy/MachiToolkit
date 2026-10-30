// lot_villes3d.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
// LES VILLES EN 3D : la ville cyberpunk (un rayon par colonne, de case en case), le survol de la
// ville, la ruelle neon, le pare-brise sous la pluie, le pont suspendu, la grande roue -- et deux vols
// hors des villes : les montagnes en « voxel space » et l'ocean au clair de lune. Chacun est porte de
// son jumeau numpy (bloc « LES VILLES EN 3D » de machi_tool.py) ; ce qui ne bouge pas est calcule a
// la premiere image, ce qui ne depend que d'une colonne (ou d'une ligne) est sorti des boucles.
#pragma once

// --- les outils du lot ---------------------------------------------------------------

const float V3_PI = 3.14159265f;

// _v3d_hasard : un hasard fixe par triplet d'entiers. On garde ses 32 bits : v3_u -> 0-1, et
// v3_frac(n, k) = (r * 2^k) % 1 sans perdre de precision (un float n'a que 24 bits)
inline uint32_t v3_bits(int32_t a, int32_t b, int32_t c) {
  uint32_t n = (uint32_t)a * 374761393u + (uint32_t)b * 668265263u + (uint32_t)c * 1274126177u;
  n = (n ^ (n >> 13)) * 1540483477u;
  n = (n ^ (n >> 15)) * 668265261u;
  return n ^ (n >> 16);
}
inline float v3_u(uint32_t n) { return (n >> 8) * (1.0f / 16777216.0f); }
inline float v3_frac(uint32_t n, int k) { return ((n << k) >> 8) * (1.0f / 16777216.0f); }
inline float v3_hasard(int32_t a, int32_t b, int32_t c) { return v3_u(v3_bits(a, b, c)); }
inline float v3_01(float v) { return v < 0 ? 0 : v > 1 ? 1 : v; }
inline int v3_mod(int a, int n) { return ((a % n) + n) % n; }
inline float v3_fmod(float a, float n) { return a - floorf(a / n) * n; }   // le % de Python (positif)

// atan et atan2 rapides (erreur ~1e-5 rad) : l'ocean en fait deux par pixel
inline float v3_atan(float x) {   // |x| <= 1
  const float z = x * x;
  return x * (0.99997726f + z * (-0.33262347f + z * (0.19354346f + z * (-0.11643287f + z * (0.05265332f - z * 0.01172120f)))));
}
inline float v3_atan2(float y, float x) {
  const float ax = fabsf(x), ay = fabsf(y);
  const float mx = fmaxf(ax, ay);
  if (mx <= 0) return 0;
  float a = v3_atan(fminf(ax, ay) / mx);
  if (ay > ax) a = 1.57079633f - a;
  if (x < 0) a = V3_PI - a;
  return y < 0 ? -a : a;
}

// _v3d_flou : un flou en boites successives (rayon r <= 7, n fois), les bords prolonges, sur une image
// larg x haut x 3 (larg, haut <= 64). Les boites en lignes et en colonnes commutent : on fait les n
// passes d'une ligne d'un coup, dans une ligne de travail prolongee de ses bords (pas de min/max).
inline void v3_boites(float *o, int n, int r, int passes, float *l) {
  const float k = 1.0f / (2 * r + 1);
  for (int it = 0; it < passes; it++) {
    for (int i = 0; i <= r; i++) {
      l[i * 3] = o[0]; l[i * 3 + 1] = o[1]; l[i * 3 + 2] = o[2];
      float *d = l + (n + r + 1 + i) * 3;
      d[0] = o[(n - 1) * 3]; d[1] = o[(n - 1) * 3 + 1]; d[2] = o[(n - 1) * 3 + 2];
    }
    memcpy(l + (r + 1) * 3, o, n * 3 * sizeof(float));
    float s0 = 0, s1 = 0, s2 = 0;
    for (int j = 1; j <= 2 * r + 1; j++) { s0 += l[j * 3]; s1 += l[j * 3 + 1]; s2 += l[j * 3 + 2]; }
    const float *ad = l + (2 * r + 2) * 3, *su = l + 3;
    for (int x = 0; x < n; x++, ad += 3, su += 3) {
      o[x * 3] = s0 * k; o[x * 3 + 1] = s1 * k; o[x * 3 + 2] = s2 * k;
      s0 += ad[0] - su[0]; s1 += ad[1] - su[1]; s2 += ad[2] - su[2];
    }
  }
}
template <class T> inline T v3_ranger(float v);
template <> inline float v3_ranger<float>(float v) { return v; }
template <> inline uint16_t v3_ranger<uint16_t>(float v) { return (uint16_t)(v + 0.5f); }
template <class T> void v3_flou_t(T *a, int larg, int haut, int r, int n) {
  float l[(64 + 16) * 3], o[64 * 3];
  for (int y = 0; y < haut; y++) {
    T *p = a + y * larg * 3;
    for (int i = 0; i < larg * 3; i++) o[i] = p[i];
    v3_boites(o, larg, r, n, l);
    for (int i = 0; i < larg * 3; i++) p[i] = v3_ranger<T>(o[i]);
  }
  const int pas = larg * 3;
  for (int x = 0; x < larg; x++) {
    T *p = a + x * 3;
    for (int y = 0; y < haut; y++) { o[y * 3] = p[y * pas]; o[y * 3 + 1] = p[y * pas + 1]; o[y * 3 + 2] = p[y * pas + 2]; }
    v3_boites(o, haut, r, n, l);
    for (int y = 0; y < haut; y++) {
      p[y * pas] = v3_ranger<T>(o[y * 3]); p[y * pas + 1] = v3_ranger<T>(o[y * 3 + 1]); p[y * pas + 2] = v3_ranger<T>(o[y * 3 + 2]);
    }
  }
}
inline void v3_flou(float *a, int larg, int haut, int r, int n) { v3_flou_t<float>(a, larg, haut, r, n); }
// le meme sur des entiers (uint16, a l'echelle qu'on veut) : deux fois moins de memoire
inline void v3_flou16(uint16_t *a, int larg, int haut, int r, int n) { v3_flou_t<uint16_t>(a, larg, haut, r, n); }

// _v3d_tache : une lumiere ronde et douce (gaussienne) ajoutee a img, une image 64 colonnes x 3 dont
// la premiere ligne est y_lo et qui a nl lignes (pour peindre dans une demi-image)
void v3_tache(float *img, int y_lo, int nl, float y, float x, float rayon, float cr, float cg, float cb, float force) {
  if (!(y > -20 && y < 84 && x > -20 && x < 84)) return;
  const int r = (int)(rayon * 2.2f) + 1;
  const int ya = max(y_lo, (int)y - r), yb = min(y_lo + nl, (int)y + r + 2);
  const int xa = max(0, (int)x - r), xb = min(64, (int)x + r + 2);
  if (ya >= yb || xa >= xb || xb - xa > 16) return;
  const float q = 1.0f / (2 * rayon * rayon);
  float kx[16];
  for (int xx = xa; xx < xb; xx++) { const float d = xx + 0.5f - x; kx[xx - xa] = expf(-d * d * q); }
  for (int yy = ya; yy < yb; yy++) {
    const float d = yy + 0.5f - y, ky = expf(-d * d * q) * force;
    float *p = img + (yy - y_lo) * 192;
    for (int xx = xa; xx < xb; xx++) {
      const float k = ky * kx[xx - xa];
      p[xx * 3] += k * cr; p[xx * 3 + 1] += k * cg; p[xx * 3 + 2] += k * cb;
    }
  }
}

// _pont_semer : un point a une position pas entiere, partage entre ses quatre voisins (des traits lisses)
inline void v3_semer(float *img, int y_lo, int nl, float ys, float xs, float r, float g, float b) {
  if (!(ys > -4 && ys < 68 && xs > -4 && xs < 68)) return;
  ys -= 0.5f; xs -= 0.5f;
  const float fy0 = floorf(ys), fx0 = floorf(xs);
  const int y0 = (int)fy0, x0 = (int)fx0;
  const float fy = ys - fy0, fx = xs - fx0;
  for (int dy = 0; dy < 2; dy++) {
    const int yy = y0 + dy;
    if (yy < y_lo || yy >= y_lo + nl) continue;
    const float wy = dy ? fy : 1 - fy;
    for (int dx = 0; dx < 2; dx++) {
      const int xx = x0 + dx;
      if (xx < 0 || xx >= 64) continue;
      const float w = wy * (dx ? fx : 1 - fx);
      float *p = img + ((yy - y_lo) * 64 + xx) * 3;
      p[0] += w * r; p[1] += w * g; p[2] += w * b;
    }
  }
}

// _pont_trait : un trait le long de n points serres (point(i, y, x) les donne) ; chacun pese la longueur
// qu'il couvre a l'ecran (np.gradient : centre au milieu, d'un cote aux bouts)
template <class P> void v3_trait(float *img, int y_lo, int nl, int n, P point, float r, float g, float b) {
  if (n < 2) return;
  float y0, x0, y1, x1, y2, x2;
  point(0, y1, x1);
  point(1, y2, x2);
  y0 = y1; x0 = x1;
  for (int i = 0; i < n; i++) {
    float gy, gx;
    if (i == 0) { gy = y2 - y1; gx = x2 - x1; }
    else if (i == n - 1) { gy = y1 - y0; gx = x1 - x0; }
    else { gy = (y2 - y0) * 0.5f; gx = (x2 - x0) * 0.5f; }
    const float pas = sqrtf(gy * gy + gx * gx);
    v3_semer(img, y_lo, nl, y1, x1, pas * r, pas * g, pas * b);
    y0 = y1; x0 = x1; y1 = y2; x1 = x2;
    if (i + 2 < n) point(i + 2, y2, x2);
  }
}

// un tirage normal (Box-Muller), pour rng.normal
inline float v3_normal() {
  const float u = hasard(1e-7f, 1), v = hasard(0, 1);
  return sqrtf(-2 * logf(u)) * cosf(6.2831853f * v);
}

// --- 1. la ville cyberpunk en 3D ---------------------------------------------------------

struct E_cyber_3d { char rien; };
void s_cyber_3d(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cyber_3d &e = etat_ecran<E_cyber_3d>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_survol { char rien; };
void s_survol(int humeur, bool debut, float t, float ecoule, float dt) {
  E_survol &e = etat_ecran<E_survol>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_ruelle { char rien; };
void s_ruelle(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ruelle &e = etat_ecran<E_ruelle>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_pare_brise { char rien; };
void s_pare_brise(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pare_brise &e = etat_ecran<E_pare_brise>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// --- 5. le pont suspendu ------------------------------------------------------------------
// Une vraie perspective (le pont s'eloigne vers la gauche), dessinee deux fois a la premiere image :
// telle qu'on la voit, et retournee sous l'eau (y -> -y) pour son reflet. A chaque image : les etoiles,
// l'onde qui parcourt les cables, les feux des pylones, les voitures, et l'eau qui ondule et etire.

const float V3_PONT_F = 34, V3_PONT_HZ = 40, V3_PONT_CY = 0.6f, V3_PONT_HAUT = 20, V3_PONT_TAB = 5;
inline float v3_pont_x(float s, float lat) { return 2.0f + s * 0.95f + lat * 0.31f; }
inline float v3_pont_z(float s, float lat) { return 30.0f - s * 0.31f + lat * 0.95f; }
inline float v3_pont_col(float x, float z) { return 32 + x * V3_PONT_F / z; }
inline float v3_pont_lig(float y, float z, bool miroir) { return V3_PONT_HZ - ((miroir ? -y : y) - V3_PONT_CY) * V3_PONT_F / z; }
inline float v3_pont_cable(float s) {   // la hauteur du cable porteur a l'abscisse s
  const float sp = 17, a = fabsf(s);
  if (a <= sp) return V3_PONT_TAB + 1.2f + (V3_PONT_HAUT - V3_PONT_TAB - 1.2f) * (s / sp) * (s / sp);
  const float q = borne((48 - a) / (48 - sp), 0, 1);
  return V3_PONT_TAB + 0.5f + (V3_PONT_HAUT - V3_PONT_TAB - 0.5f) * (q > 0 ? expf(1.7f * logf(q)) : 0);
}

struct E_pont {
  uint8_t base[64][64][3];          // ce qu'on voit au-dessus de l'eau, sans ce qui bouge
  float refl[32][64][3];            // le monde retourne sous l'eau (lignes 32 a 63)
  union {
    float dyn[32][64][3];           // a chaque image : le reflet et ses lumieres qui bougent
    struct { uint8_t couv[64][64], ville[64][64][3], vmasque[64][64]; } p;   // a la premiere image
  } u;
  float echant[27][64][3];          // l'eau : ce qu'elle reflete, lignes 37 a 63
  float ep[40], voies[4][7], vit[4];
  uint8_t ey[40], ex[40];
  int ne;
};

// _pont_structure : le pont fixe dans `coul` (couleur + lumieres, en flottants) et `couv` (0-255)
void v3_pont_structure(bool miroir, float *coul, uint8_t (*couv)[64]) {
  const float F = V3_PONT_F;
  memset(coul, 0, 64 * 64 * 3 * sizeof(float));
  memset(couv, 0, 64 * 64);
  float (*c)[64][3] = (float (*)[64][3])coul;
  // le tablier, colonne par colonne
  for (int x = 0; x < 64; x++) {
    const float u = x + 0.5f - 32;
    const float ax = 2.0f - 1.5f * 0.31f, az = 30.0f - 1.5f * 0.95f;
    const float s = borne((u * az - F * ax) / (F * 0.95f + u * 0.31f), -50, 42);
    const float z = v3_pont_z(s, -1.5f);
    const float y1 = v3_pont_lig(V3_PONT_TAB + 0.4f, z, miroir), y2 = v3_pont_lig(V3_PONT_TAB - 0.5f, z, miroir);
    const float haut = fminf(y1, y2), bas = fmaxf(y1, y2);
    for (int y = max(0, (int)haut - 1); y < min(64, (int)bas + 2); y++) {
      const float k = borne(fminf(y + 1.0f, bas) - fmaxf((float)y, haut), 0, 1);
      if (k > 0) { couv[y][x] = (uint8_t)(k * 255 + 0.5f); c[y][x][0] = 16; c[y][x][1] = 16; c[y][x][2] = 26; }
    }
  }
  // les pylones : deux jambes, eclairees par en dessous
  for (int p = 0; p < 2; p++) {
    const float sp = p ? 17.0f : -17.0f;
    for (int l = 0; l < 2; l++) {
      const float lat = l ? 1.6f : -1.6f;
      const float px = v3_pont_x(sp, lat), pz = v3_pont_z(sp, lat);
      const float cx = v3_pont_col(px, pz), w = 0.9f * F / pz;
      const float yt = v3_pont_lig(V3_PONT_HAUT, pz, miroir), yb = v3_pont_lig(0, pz, miroir);
      const float haut = fminf(yt, yb), bas = fmaxf(yt, yb);
      for (int y = 0; y < 64; y++) {
        const float ky = borne(fminf(y + 1.0f, bas) - fmaxf((float)y, haut), 0, 1);
        if (ky <= 0) continue;
        const float hauteur = borne(fabsf(V3_PONT_HZ + V3_PONT_CY * F / pz - (y + 0.5f)) * pz / F / V3_PONT_HAUT, 0, 1);
        for (int x = 0; x < 64; x++) {
          const float k = borne(fminf(x + 1.0f, cx + w / 2) - fmaxf((float)x, cx - w / 2), 0, 1) * ky * (l ? 0.999f : 1.0f);
          if (k <= 0) continue;
          const float eclat = (0.95f - 0.6f * hauteur + 0.25f * borne(1 - fabsf(x + 0.5f - cx + w * 0.25f) / fmaxf(w * 0.3f, 0.4f), 0, 1))
                              * (l ? 0.85f : 1.0f);
          c[y][x][0] = c[y][x][0] * (1 - k) + 255 * eclat * k;
          c[y][x][1] = c[y][x][1] * (1 - k) + 195 * eclat * k;
          c[y][x][2] = c[y][x][2] * (1 - k) + 120 * eclat * k;
          couv[y][x] = max(couv[y][x], (uint8_t)(k * 255 + 0.5f));
        }
      }
    }
  }
  // les cables porteurs et les suspentes
  for (int l = 0; l < 2; l++) {
    const float lat = l ? 1.6f : -1.6f, f = l ? 0.15f : 0.3f;
    v3_trait(coul, 0, 64, 900, [&](int i, float &y, float &x) {
      const float s = -50 + 92.0f * i / 899, z = v3_pont_z(s, lat);
      y = v3_pont_lig(v3_pont_cable(s), z, miroir); x = v3_pont_col(v3_pont_x(s, lat), z);
    }, 150 * f, 160 * f, 190 * f);
    const float g = 0.12f * (l ? 0.6f : 1.0f);
    for (int n = 0; n < 55; n++) {
      const float sl = -46 + 1.6f * n, yl = v3_pont_cable(sl);
      if (yl <= V3_PONT_TAB + 0.8f) continue;
      const float x = v3_pont_x(sl, lat), z = v3_pont_z(sl, lat), cx = v3_pont_col(x, z);
      v3_trait(coul, 0, 64, 14, [&](int i, float &yy, float &xx) {
        yy = v3_pont_lig(V3_PONT_TAB + 0.4f + (yl - V3_PONT_TAB - 0.4f) * i / 13.0f, z, miroir); xx = cx;
      }, 110 * g, 120 * g, 150 * g);
    }
  }
  // les lumieres : la ligne de diodes du tablier, les traverses des pylones
  int i0 = 1400, i1 = 0;
  for (int i = 0; i < 1400; i++) {
    const float s = -50 + 92.0f * i / 1399, c0 = v3_pont_col(v3_pont_x(s, -1.5f), v3_pont_z(s, -1.5f));
    if (c0 >= -1 && c0 < 65) { i0 = min(i0, i); i1 = max(i1, i + 1); }
  }
  v3_trait(coul, 0, 64, i1 - i0, [&](int i, float &y, float &x) {
    const float s = -50 + 92.0f * (i + i0) / 1399, z = v3_pont_z(s, -1.5f);
    y = v3_pont_lig(V3_PONT_TAB - 0.15f, z, miroir); x = v3_pont_col(v3_pont_x(s, -1.5f), z);
  }, 60 * 0.35f, 140 * 0.35f, 255 * 0.35f);
  for (int p = 0; p < 2; p++) {
    const float sp = p ? 17.0f : -17.0f;
    for (int h = 0; h < 2; h++) {
      const float yt = h ? V3_PONT_TAB + 6 : V3_PONT_HAUT - 2;
      const float za = v3_pont_z(sp, -1.6f), zb = v3_pont_z(sp, 1.6f);
      const float ca = v3_pont_col(v3_pont_x(sp, -1.6f), za), cb = v3_pont_col(v3_pont_x(sp, 1.6f), zb);
      const float ya = v3_pont_lig(yt, za, miroir), yb = v3_pont_lig(yt, zb, miroir);
      for (int k = 0; k < 30; k++) {
        const float q = k / 29.0f;
        v3_semer(coul, 0, 64, ya + (yb - ya) * q, ca + (cb - ca) * q, 255 * 0.12f, 190 * 0.12f, 110 * 0.12f);
      }
    }
  }
}

// la ville sur l'autre rive, loin (z = 70) : des tours aux fenetres allumees au hasard
void v3_pont_ville(bool miroir, uint8_t (*ville)[64][3], uint8_t (*vm)[64]) {
  memset(ville, 0, 64 * 64 * 3);
  memset(vm, 0, 64 * 64);
  float x = -150;
  while (x < 150) {
    const float w = hasard(2.5f, 7), h = hasard(3, 16) * (fabsf(x) < 50 ? 1.3f : 0.8f);
    const float eclat = 0.5f + 0.5f * hasard(0, 1);
    const float ca = v3_pont_col(x, 70), cb = v3_pont_col(x + w, 70);
    const float yt = v3_pont_lig(h, 70, miroir), yb = v3_pont_lig(0, 70, miroir);
    const float haut = fminf(yt, yb), bas = fmaxf(yt, yb);
    const int c0 = max(0, (int)floorf(ca)), c1 = min(64, (int)ceilf(cb));
    for (int cx = c0; cx < c1; cx++) {
      const float kx = borne(fminf(cx + 1.0f, cb) - fmaxf((float)cx, ca), 0, 1);
      for (int y = max(0, (int)haut - 1); y < min(64, (int)bas + 2); y++) {
        const float k = kx * borne(fminf(y + 1.0f, bas) - fmaxf((float)y, haut), 0, 1);
        if (k <= 0) continue;
        const bool fen = v3_hasard(cx + (int)(x * 10), y, 41) > 0.88f;
        const float col[3] = {14 + (fen ? 150 * eclat : 0), 14 + (fen ? 120 * eclat : 0), 28 + (fen ? 80 * eclat : 0)};
        for (int c = 0; c < 3; c++) ville[y][cx][c] = (uint8_t)(ville[y][cx][c] * (1 - k) + k * col[c] + 0.5f);
        vm[y][cx] = 1;
      }
    }
    x += w + hasard(0, 2);
  }
}

void s_pont(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pont &e = etat_ecran<E_pont>(debut);
  (void)humeur; (void)ecoule;
  const float hz = V3_PONT_HZ;
  float *img = &scene[0][0][0];
  if (debut) {
    const uint32_t g0 = graine;
    // le reflet : la ville et le pont retournes (sans ciel : l'eau est noire dessous)
    v3_pont_structure(true, img, e.u.p.couv);
    v3_pont_ville(true, e.u.p.ville, e.u.p.vmasque);
    for (int y = 32; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float k = 1 - e.u.p.couv[y][x] / 255.0f;
        for (int c = 0; c < 3; c++) e.refl[y - 32][x][c] = e.u.p.ville[y][x][c] * k + scene[y][x][c];
      }
    graine = g0;   // la meme ville, a l'endroit
    v3_pont_structure(false, img, e.u.p.couv);
    v3_pont_ville(false, e.u.p.ville, e.u.p.vmasque);
    int libres = 0;
    for (int y = 0; y < 64; y++) {
      const float k = borne(y / hz, 0, 1), lueur = y < hz ? expf(-(hz - y) / 6.0f) : 0;
      const float ciel[3] = {4 + 30 * k + lueur * 60, 6 + 24 * k + lueur * 34, 20 + 46 * k + lueur * 40};
      for (int x = 0; x < 64; x++) {
        const float a = 1 - e.u.p.couv[y][x] / 255.0f;
        for (int c = 0; c < 3; c++) {
          const float f = e.u.p.vmasque[y][x] ? e.u.p.ville[y][x][c] : ciel[c];
          e.base[y][x][c] = (uint8_t)borne(f * a + scene[y][x][c] + 0.5f, 0, 255);
        }
        if (e.u.p.couv[y][x] < 13 && !e.u.p.vmasque[y][x] && y < hz - 2) libres++;
      }
    }
    // des etoiles, la ou le ciel est libre
    e.ne = 0;
    for (int essai = 0; essai < 4000 && e.ne < 40 && libres > 0; essai++) {
      const int y = aleatoire() % 38, x = aleatoire() % 64;
      if (e.u.p.couv[y][x] >= 13 || e.u.p.vmasque[y][x]) continue;
      bool deja = false;
      for (int i = 0; i < e.ne; i++) deja |= e.ey[i] == y && e.ex[i] == x;
      if (deja) continue;
      e.ey[e.ne] = y; e.ex[e.ne] = x; e.ep[e.ne] = hasard(0, 6); e.ne++;
    }
    for (int v = 0; v < 4; v++)
      for (int i = 0; i < 7; i++) e.voies[v][i] = hasard(-50, 42);
    for (int v = 0; v < 4; v++) e.vit[v] = hasard(3.0f, 4.5f);
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] = e.base[y][x][c];
  memcpy(e.u.dyn, e.refl, sizeof e.refl);
  float *dyn = &e.u.dyn[0][0][0];
  for (int i = 0; i < e.ne; i++) {
    const float k = (0.5f + 0.5f * sinf(t * 1.9f + e.ep[i])) * 70;
    float *p = scene[e.ey[i]][e.ex[i]];
    p[0] += k * 0.9f; p[1] += k * 0.9f; p[2] += k;
  }
  // les lumieres des cables : une onde lente qui les parcourt ; les feux rouges en haut des pylones
  for (int l = 0; l < 2; l++) {
    const float lat = l ? 1.6f : -1.6f;
    for (int i = 0; i < 29; i++) {
      const float sk = -46 + 3.0f * i, yk = v3_pont_cable(sk);
      const float x = v3_pont_x(sk, lat), z = v3_pont_z(sk, lat), cx = v3_pont_col(x, z);
      const float f = (0.45f + 0.55f * sinf(sk * 0.22f - t * 0.7f)) * (l ? 0.3f : 1.0f) * borne((44 - fabsf(sk)) / 16, 0.2f, 1);
      v3_semer(img, 0, 64, v3_pont_lig(yk + 0.1f, z, false), cx, 210 * f, 230 * f, 255 * f);
      v3_semer(dyn, 32, 32, v3_pont_lig(yk + 0.1f, z, true), cx, 210 * f, 230 * f, 255 * f);
    }
  }
  for (int p = 0; p < 2; p++) {
    const float sp = p ? 17.0f : -17.0f;
    const float x = v3_pont_x(sp, -1.6f), z = v3_pont_z(sp, -1.6f), cx = v3_pont_col(x, z);
    const float f = 0.5f + 0.5f * sinf(t * 1.5f + sp);
    v3_tache(img, 0, 64, v3_pont_lig(V3_PONT_HAUT + 0.6f, z, false), cx, 0.7f, 255, 40, 30, f);
    v3_tache(dyn, 32, 32, v3_pont_lig(V3_PONT_HAUT + 0.6f, z, true), cx, 0.7f, 255, 40, 30, f);
  }
  // les voitures : des phares blancs vers la droite, des feux rouges vers la gauche
  static const float voies[4][2] = {{-0.9f, 1}, {-0.35f, 1}, {0.35f, -1}, {0.9f, -1}};
  for (int v = 0; v < 4; v++) {
    const float lat = voies[v][0], sens = voies[v][1];
    for (int i = 0; i < 7; i++) {
      float &s = e.voies[v][i];
      s += sens * e.vit[v] * fminf(dt, 0.5f);
      if (s > 42) s -= 92;
      else if (s < -50) s += 92;
      const float x = v3_pont_x(s, lat), z = v3_pont_z(s, lat), cx = v3_pont_col(x, z);
      const float k = borne(30.0f / z, 0.4f, 1);
      const float r = 255 * k, g = (sens > 0 ? 240 : 40) * k, b = (sens > 0 ? 210 : 40) * k;
      v3_semer(img, 0, 64, v3_pont_lig(V3_PONT_TAB + 0.75f, z, false), cx, r * 0.9f, g * 0.9f, b * 0.9f);
      v3_semer(dyn, 32, 32, v3_pont_lig(V3_PONT_TAB + 0.75f, z, true), cx, r * 0.8f, g * 0.8f, b * 0.8f);
    }
  }
  // l'eau : le reflet, etire vers le bas, qui ondule de plus en plus fort pres de nous
  float onde_x[64];
  for (int x = 0; x < 64; x++) onde_x[x] = sinf(x * 0.21f + t * 0.6f) * 1.5f;
  for (int y = 37; y < 64; y++) {
    const float prof = borne((y + 0.5f - hz) / (64 - hz), 0, 1), ampl = 0.3f + 2.2f * prof;
    const float lent = 0.6f * sinf(y * 0.7f - t * 0.9f);
    for (int x = 0; x < 64; x++) {
      const float dx = ampl * sinf(y * 1.9f + t * 1.4f + onde_x[x]) + lent;
      const int sx = min(63, max(0, (int)(x + dx)));
      const int sy = min(63, max(32, (int)(y + (prof > 0 ? sinf(x * 0.4f + y * 1.3f + t * 2.1f) * prof * 1.2f : 0))));
      memcpy(e.echant[y - 37][x], e.u.dyn[sy - 32][sx], 3 * sizeof(float));
    }
  }
  for (int y = (int)hz; y < 64; y++) {
    const float prof = borne((y + 0.5f - hz) / (64 - hz), 0, 1), k = 0.75f - 0.35f * prof;
    const float fond[3] = {6 * (1 - prof) + 3 * prof, 10 * (1 - prof) + 5 * prof, 26 * (1 - prof) + 14 * prof};
    const float vague = sinf(y * 0.5f + t) * 2;
    for (int x = 0; x < 64; x++) {
      const float s = 0.5f + 0.5f * sinf(x * 0.9f + y * 2.3f - t * 2.0f + vague);
      const float s2 = s * s, sc = s2 * s2 * s2 * 12;
      const float sc3[3] = {0.6f, 0.7f, 1.0f};
      for (int c = 0; c < 3; c++) {
        const float *q = &e.echant[y - 37][x][c];
        const float r = q[0] * 0.45f + (q[0] + q[-192] + q[-384] + q[-576]) * 0.25f * 0.55f;
        scene[y][x][c] = fond[c] + r * k + sc * sc3[c];
      }
    }
  }
}

// --- 6. la grande roue -------------------------------------------------------------------
// Tout en coordonnees polaires autour du moyeu (gardees pour chaque pixel de la roue) : les rayons et
// la jante portent des ampoules, quatre motifs de lumiere se relaient en fondu, les nacelles pendent.

struct V3Roue { uint16_t i; float r, a, amp; };
struct E_grande_roue {
  uint8_t fond[64][64][3];
  uint16_t halo[64][64][3];     // la lueur, x32
  V3Roue roue[1400];            // les pixels a moins de 20,3 du moyeu
  float ep[40], phase;
  uint8_t ey[40], ex[40];
  int nroue, ne;
};

void s_grande_roue(int humeur, bool debut, float t, float ecoule, float dt) {
  E_grande_roue &e = etat_ecran<E_grande_roue>(debut);
  (void)humeur; (void)dt;
  const float cx = 32, cy = 24, R = 19.5f, sol = 53, pas = 2 * V3_PI / 16;
  if (debut) {
    static const float baraques[2][6] = {{3, 13, 47, 255, 160, 80}, {51, 61, 48, 255, 120, 170}};
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float k = borne(y / sol, 0, 1);
        float c[3] = {6 + 34 * k, 6 + 14 * k, 24 + 34 * k};
        if (y < sol) { const float g = expf(-(sol - y) / 7.0f); c[0] += g * 40; c[1] += g * 18; c[2] += g * 30; }
        for (int p = 0; p < 2; p++) {   // la charpente : deux jambes du moyeu au sol
          const float pied = p ? cx + 12 : cx - 12;
          const float d = fabsf((x + 0.5f - cx) * (sol - cy) - (pied - cx) * (y + 0.5f - cy)) / hypotf(sol - cy, pied - cx);
          const float j = (y + 0.5f > cy && y < sol) ? borne(1.2f - d, 0, 1) : 0;
          c[0] = c[0] * (1 - j) + 20 * j; c[1] = c[1] * (1 - j) + 16 * j; c[2] = c[2] * (1 - j) + 30 * j;
        }
        for (int b = 0; b < 2; b++) {   // et des baraques
          const int x0 = (int)baraques[b][0], x1 = (int)baraques[b][1], h = (int)baraques[b][2];
          const float *cc = &baraques[b][3];
          if (x >= x0 && x < x1 && y >= h && y < sol) { c[0] = 10; c[1] = 8; c[2] = 18; }
          if (x >= x0 - 1 && x < x1 + 1 && y >= h - 2 && y < h && !(y == h - 2 && (x == x0 - 1 || x == x1))) {
            const int q = (x - x0 + 2) / 2 - 1;
            const bool rouge = v3_mod(q, 2) == 0;
            c[0] = rouge ? 85 : 95; c[1] = rouge ? 20 : 90; c[2] = rouge ? 30 : 85;
          }
          if (x >= x0 + 1 && x < x1 - 1 && y >= h + 1 && y < h + 3)
            for (int i = 0; i < 3; i++) c[i] = cc[i] * 0.55f;
          if (y >= h + 3) {
            const float dx = (x + 0.5f - (x0 + x1) / 2.0f) / 6, dy = (y + 0.5f - h - 3) / 3;
            const float g = expf(-dx * dx - dy * dy) * 0.12f;
            for (int i = 0; i < 3; i++) c[i] += g * cc[i];
          }
        }
        for (int i = 0; i < 3; i++) e.fond[y][x][i] = (uint8_t)borne(c[i] + 0.5f, 0, 255);
      }
    e.ne = 0;
    for (int i = 0; i < 40; i++) {
      const int y = aleatoire() % 40, x = aleatoire() % 64;
      if (hypotf(x - cx, y - cy) <= R + 3) continue;
      e.ey[e.ne] = y; e.ex[e.ne] = x; e.ep[e.ne] = hasard(0, 6); e.ne++;
    }
    e.nroue = 0;
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float r = hypotf(x + 0.5f - cx, y + 0.5f - cy);
        if (r >= 20.3f || e.nroue >= 1400) continue;
        e.roue[e.nroue++] = {(uint16_t)(y * 64 + x), r, atan2f(y + 0.5f - cy, x + 0.5f - cx), 0.55f + 0.45f * cosf(2 * V3_PI * r / 2.6f)};
      }
    e.phase = hasard(0, 6.3f);
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] = e.fond[y][x][c];
  for (int i = 0; i < e.ne; i++) {
    const float k = (0.5f + 0.5f * sinf(t * 1.7f + e.ep[i])) * 80;
    float *p = scene[e.ey[i]][e.ex[i]];
    p[0] += k * 0.85f; p[1] += k * 0.85f; p[2] += k;
  }
  const float th = ecoule * 2 * V3_PI / 110 + e.phase;    // un tour en 110 s
  // quatre motifs, en fondu enchaine : arc-en-ciel qui tourne, vagues vers le dehors, rayons alternes, spirale
  const float m = v3_fmod(ecoule / 16 + e.phase, 4);
  float poids[4];
  for (int i = 0; i < 4; i++) { const float d = fabsf(m - i); poids[i] = borne(1 - fminf(d, 4 - d), 0, 1); }
  const float alt_t = cosf(t * 0.7f);
  float c3[16][3], v3[16];
  for (int k = 0; k < 16; k++) {
    const float alt = 0.5f + 0.5f * (k & 1 ? -alt_t : alt_t);
    c3[k][0] = 255 * alt + 50 * (1 - alt); c3[k][1] = 50 * alt + 210 * (1 - alt); c3[k][2] = 170 * alt + 255 * (1 - alt);
    v3[k] = 0.6f + 0.4f * sinf(t * 1.2f + k * 0.4f);
  }
  for (int n = 0; n < e.nroue; n++) {
    const V3Roue &q = e.roue[n];
    const float r = q.r, ath = q.a - th;
    float da = ath + pas / 2;
    da -= floorf(da / pas) * pas;
    da -= pas / 2;
    const float da2 = da * da, sda = da * (1 - da2 * (1.0f / 6 - da2 * (1.0f / 120)));   // |da| < 0,2 : sin(da)
    const float rayon = (r > 2.5f && r < R) ? borne(1.25f - fabsf(r * sda) / 0.6f, 0, 1) : 0;
    const float jante = borne(1 - fabsf(r - R) / 0.7f, 0, 1) + 0.55f * borne(1 - fabsf(r - R + 2.2f) / 0.6f, 0, 1);
    const float moyeu = borne(2.2f - r, 0, 1);
    if (rayon <= 0 && jante <= 0 && moyeu <= 0) continue;
    float valeur = 0, col[3] = {0, 0, 0};
    if (poids[0] > 0) {
      float a, b, c;
      teinte(ath / (2 * V3_PI) + t * 0.04f, 0.75f, 1.0f, a, b, c);
      col[0] += floorf(a) * poids[0]; col[1] += floorf(b) * poids[0]; col[2] += floorf(c) * poids[0];
      valeur += poids[0];
    }
    if (poids[1] > 0) {
      const float v = fmaxf(0.0f, cosf(2 * V3_PI * (r / 7.0f - t * 0.35f)));
      col[0] += 255 * poids[1]; col[1] += 200 * poids[1]; col[2] += 120 * poids[1];
      valeur += (0.4f + 0.9f * v * v) * poids[1];
    }
    if (poids[2] > 0) {
      const int k = v3_mod((int)rintf((ath - da) / pas), 16);
      for (int i = 0; i < 3; i++) col[i] += c3[k][i] * poids[2];
      valeur += v3[k] * poids[2];
    }
    if (poids[3] > 0) {
      float a, b, c;
      teinte(0.55f + 0.25f * sinf(r / R * 3 - t * 0.3f), 0.6f, 1.0f, a, b, c);
      col[0] += floorf(a) * poids[3]; col[1] += floorf(b) * poids[3]; col[2] += floorf(c) * poids[3];
      const float v = fmaxf(0.0f, cosf(2 * V3_PI * (r / R * 0.9f + ath / (2 * V3_PI) - t * 0.12f)));
      valeur += (0.2f + 0.8f * v * v * v) * poids[3];
    }
    const float kr = rayon * q.amp * valeur * 1.25f;
    const float kj = jante > 0 ? jante * (0.45f + 0.55f * (0.5f + 0.5f * cosf(ath * 48))) * (0.6f + 0.4f * valeur) : 0;
    const float km = moyeu * 0.8f, att = 1 - borne(rayon + jante, 0, 1) * 0.7f;
    float *p = &scene[0][0][0] + q.i * 3;
    p[0] = p[0] * att + kr * col[0] + kj * 255 + km * 255;
    p[1] = p[1] * att + kr * col[1] + kj * 215 + km * 220;
    p[2] = p[2] * att + kr * col[2] + kj * 150 + km * 170;
  }
  // les nacelles : accrochees a la jante, elles pendent droit
  static const float tons_n[4][3] = {{255, 70, 90}, {255, 190, 60}, {70, 200, 255}, {190, 100, 255}};
  static const float cabine[4][4] = {{0, 1, 1, 0}, {0.5f, 2, 2, 0.5f}, {0.5f, 2, 2, 0.5f}, {0, 0.6f, 0.6f, 0}};
  for (int k = 0; k < 16; k++) {
    const float ak = th + k * pas;
    const float x0 = cx + R * cosf(ak) - 1.5f, y0 = cy + R * sinf(ak) + 1.0f;
    const int xa = (int)floorf(x0), ya = (int)floorf(y0);
    if (xa < 0 || ya < 0 || xa + 4 > 64 || ya + 4 > 64) continue;
    const float fx = x0 - xa, fy = y0 - ya;
    const float wx[4] = {1 - fx, 1, 1, fx}, wy[4] = {1 - fy, 1, 1, fy};
    for (int j = 0; j < 4; j++)
      for (int i = 0; i < 4; i++) {
        const float cab = cabine[j][i];
        if (cab <= 0) continue;
        const float w = wy[j] * wx[i];
        float c[3];
        for (int q = 0; q < 3; q++) c[q] = cab > 1.5f ? (q == 0 ? 255 : q == 1 ? 205 : 130) * 0.7f : tons_n[k % 4][q] * cab * 0.6f;
        float *p = scene[ya + j][xa + i];
        for (int q = 0; q < 3; q++) p[q] = p[q] * (1 - w) + c[q] * w;
      }
  }
  // des guirlandes entre des mats : les couleurs passent d'ampoule en ampoule, en fondu
  static const float tons[4][3] = {{255, 70, 60}, {255, 210, 70}, {80, 255, 140}, {80, 160, 255}};
  for (int g = 0; g < 2; g++) {
    const float x0 = g ? 44.0f : 0.0f, x1 = g ? 64.0f : 20.0f, y0 = g ? 43.0f : 42.0f;
    for (int i = 0; i < 9; i++) {
      const float s = i / 8.0f, gx = x0 + (x1 - x0) * s;
      const float gy = y0 + 12.0f * s * (1 - s) + 0.3f * sinf(t * 0.9f + gx * 0.2f);
      const float ph = i + t * 1.2f, fl = floorf(ph);
      float f = ph - fl;
      f = f * f * (3 - 2 * f);
      const int n = (int)fl;
      float c[3];
      for (int q = 0; q < 3; q++) c[q] = tons[n % 4][q] * (1 - f) + tons[(n + 1) % 4][q] * f;
      pointer(gy, gx, c[0] * 0.9f, c[1] * 0.9f, c[2] * 0.9f);
      pointer(gy, gx + 1, c[0] * 0.25f, c[1] * 0.25f, c[2] * 0.25f);
    }
  }
  // la lueur de tout ce qui brille
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) e.halo[y][x][c] = (uint16_t)(borne(scene[y][x][c] - 60, 0, 2000) * 32);
  v3_flou16(&e.halo[0][0][0], 64, 64, 2, 2);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] += e.halo[y][x][c] * (0.6f / 32);
  // le sol mouille : le reflet de tout cela, retourne, sombre, qui ondule
  float sb[64], cb[64], sd[64], cd[64];       // sin(a + b) = sin a cos b + cos a sin b : une table par colonne
  for (int x = 0; x < 64; x++) { sb[x] = sinf(x * 0.5f); cb[x] = cosf(x * 0.5f); sd[x] = sinf(x * 0.15f); cd[x] = cosf(x * 0.15f); }
  for (int y = (int)sol; y < 64; y++) {
    const float k = 0.5f - (y - sol) * 0.025f;
    const float sa = sinf(y * 1.3f + t * 1.6f), ca = cosf(y * 1.3f + t * 1.6f);
    const float sc = sinf(y * 1.7f - t * 1.2f), cc = cosf(y * 1.7f - t * 1.2f);
    for (int x = 0; x < 64; x++) {
      const int yy = min((int)sol - 1, max(0, 2 * (int)sol - 1 - y + (int)rintf((sa * cb[x] + ca * sb[x]) * 0.6f)));
      const int xx = min(63, max(0, x + (int)rintf((sc * cd[x] + cc * sd[x]) * (y - sol) * 0.12f)));
      scene[y][x][0] = 8 + scene[yy][xx][0] * k;
      scene[y][x][1] = 6 + scene[yy][xx][1] * k;
      scene[y][x][2] = 16 + scene[yy][xx][2] * k;
    }
  }
}

struct E_voxel { char rien; };
void s_voxel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voxel &e = etat_ecran<E_voxel>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// --- 8. l'ocean au clair de lune -----------------------------------------------------------
// Chaque pixel sous l'horizon voit un point de la mer, une somme de dix vagues (leur pente donne la
// normale) ; on renvoie le ciel dans la direction du reflet, et la lune quand il la vise. Au loin, les
// vagues trop petites pour un pixel sont retirees et leur pente passe dans le flou du reflet. Le long
// d'une ligne, la phase d'une vague avance d'un pas fixe : on la tourne au lieu d'appeler cosf.

struct E_ocean {
  float kx[10], kz[10], amp[10], om[10], ph[10];
  float ep[50], el[50];
  uint8_t ey[50], ex[50];
};

// le ciel de l'ocean dans une direction (azimut, hauteur), en radians
inline void v3_ocean_ciel(float az, float el, float *c) {
  const float k = v3_01(el / 0.5f), a = (1 - k) * (1 - k);
  c[0] = 30 * a + 5 * (1 - a); c[1] = 40 * a + 7 * (1 - a); c[2] = 72 * a + 20 * (1 - a);
  const float da = az - 0.13f, de = el - 0.24f, d2 = da * da + de * de;
  if (d2 < 1.0f) {
    const float d = sqrtf(d2), h = expf(-d / 0.12f), l = expf(-d / 0.035f) * 40;
    c[0] += h * 40 + l; c[1] += h * 46 + l; c[2] += h * 60 + l;
  }
}

void s_ocean(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ocean &e = etat_ecran<E_ocean>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float F = 40, ma = 0.13f, mh = 0.24f;
  if (debut) {
    for (int i = 0; i < 10; i++) {   // de la houle aux vaguelettes ; elles viennent vers nous, un peu de biais
      float lam = 14.0f;
      for (int j = 0; j < i; j++) lam *= 0.62f;
      const float ang = 1.75f + v3_normal() * 0.45f, k = 2 * V3_PI / lam;
      e.kx[i] = k * cosf(ang); e.kz[i] = k * sinf(ang);
      e.amp[i] = lam * hasard(0.011f, 0.02f); e.om[i] = sqrtf(3.2f * k); e.ph[i] = hasard(0, 2 * V3_PI);
    }
    for (int i = 0; i < 50; i++) { e.ey[i] = aleatoire() % 22; e.ex[i] = aleatoire() % 64; e.ep[i] = hasard(0, 6); e.el[i] = hasard(0.3f, 1); }
  }
  const float cy = 3.0f + 0.12f * sinf(t * 0.37f), hz = 25.0f + 0.5f * sinf(t * 0.29f);
  // le ciel : bleu nuit, plus clair vers l'horizon ; la lune et son halo
  const int y_mer = max(0, (int)floorf(hz - 1) + 1);       // la premiere ligne ou la mer se voit
  for (int x = 0; x < 64; x++) {
    const float dx = (x + 0.5f - 32) / F, az = v3_atan(dx), hc = 1.0f / sqrtf(dx * dx + 1);
    for (int y = 0; y < min(64, (int)hz + 1); y++) {
      const float el = v3_atan(-(y + 0.5f - hz) / F * hc);
      v3_ocean_ciel(az, el, scene[y][x]);
    }
  }
  for (int i = 0; i < 50; i++) {
    const float k = e.el[i] * (0.5f + 0.5f * sinf(t * 1.8f + e.ep[i])) * 160;
    pointer(e.ey[i], e.ex[i], k * 0.9f, k * 0.92f, k);
  }
  const float lx = 32 + tanf(ma) * F, ly = hz - tanf(mh) * F;
  for (int y = max(0, (int)ly - 4); y < min(64, (int)ly + 5); y++)
    for (int x = max(0, (int)lx - 4); x < min(64, (int)lx + 5); x++) {
      const float d = hypotf(x + 0.5f - lx, y + 0.5f - ly), disque = v3_01(3.3f - d);
      if (disque <= 0) continue;
      const float mers = 0.82f + 0.18f * sinf((x - lx) * 1.7f + 1) * sinf((y - ly) * 2.1f);   // ses mers, a peine
      scene[y][x][0] = scene[y][x][0] * (1 - disque) + disque * 235 * mers;
      scene[y][x][1] = scene[y][x][1] * (1 - disque) + disque * 232 * mers;
      scene[y][x][2] = scene[y][x][2] * (1 - disque) + disque * 215 * mers;
    }
  // la mer
  for (int y = y_mer; y < 64; y++) {
    const float sy = y + 0.5f - hz;
    if (sy <= -0.5f) continue;
    const float s = cy * F / fmaxf(sy, 0.05f), pied_x = s / F, pied_z = s * s / (F * cy);
    const float couv = v3_01(sy + 0.5f);
    // les vagues qui tiennent dans un pixel : leur phase au bord gauche et son pas d'une colonne a l'autre
    float A[10], co[10], si[10], cd[10], sd[10], var_x = 0, var_z = 0;
    int na = 0, idx[10];
    for (int i = 0; i < 10; i++) {
      const float alias = (fabsf(e.kx[i]) * pied_x + fabsf(e.kz[i]) * pied_z) / 2.2f;
      const float garde = alias < 5 ? expf(-alias * alias) : 0;
      const float perdu = e.amp[i] * e.amp[i] * 0.5f * (1 - garde * garde);
      var_x += perdu * e.kx[i] * e.kx[i];
      var_z += perdu * e.kz[i] * e.kz[i];
      const float a = e.amp[i] * garde;
      if (a * (fabsf(e.kx[i]) + fabsf(e.kz[i])) < 1e-4f) continue;
      const float pas = e.kx[i] * s / F;
      const float p0 = e.kx[i] * (0.5f - 32) * s / F + e.kz[i] * s - e.om[i] * t + e.ph[i];
      A[na] = a; co[na] = cosf(p0); si[na] = sinf(p0); cd[na] = cosf(pas); sd[na] = sinf(pas); idx[na] = i;
      na++;
    }
    const float sa = 0.0011f + 4 * var_x, se = 0.0045f + 4 * var_z;
    const float norme = expf(0.22f * logf(0.0011f * 0.0045f / (sa * se))), i2sa = 0.5f / sa, i2se = 0.5f / se;
    const float ge = 4.5f * pied_z / 2.2f, garde_e = ge < 4 ? expf(-ge * ge) : 0;   // des eclats qui courent en travers
    for (int x = 0; x < 64; x++) {
      const float sx = x + 0.5f - 32;
      float dhx = 0, dhz = 0;
      for (int j = 0; j < na; j++) {
        const float c = co[j] * A[j];
        dhx += c * e.kx[idx[j]];
        dhz += c * e.kz[idx[j]];
        const float c2 = co[j] * cd[j] - si[j] * sd[j];
        si[j] = si[j] * cd[j] + co[j] * sd[j];
        co[j] = c2;
      }
      const float inv = 1.0f / sqrtf(dhx * dhx + 1 + dhz * dhz);
      const float nx = -dhx * inv, ny = inv, nz = -dhz * inv;
      const float il = 1.0f / sqrtf(sx * sx + sy * sy + F * F);
      const float vx = sx * il, vy = -sy * il, vz = F * il;
      const float dn = vx * nx + vy * ny + vz * nz;
      const float rx = vx - 2 * dn * nx, ry = fabsf(vy - 2 * dn * ny), rz = vz - 2 * dn * nz;
      const float q = v3_01(1 + dn), q2 = q * q, fres = 0.02f + 0.98f * q2 * q2 * q;
      const float az = v3_atan2(rx, rz), el = v3_atan2(ry, sqrtf(rx * rx + rz * rz));
      float ciel[3];
      v3_ocean_ciel(az, el, ciel);
      const float da = az - ma, de = el - mh, ex = da * da * i2sa + de * de * i2se;
      float eclat = ex < 30 ? expf(-ex) * norme : 0;
      if (eclat > 0 && garde_e > 1e-3f) {
        const float gx = sx * s / F;
        eclat *= 1 + 0.9f * garde_e * sinf(s * 4.5f - t * 1.7f + 2 * sinf(gx * 1.3f + t * 0.6f));
      }
      const float dos = v3_01(-dhz * 3) * 6;   // les dos des vagues, un rien plus clairs
      const float eau[3] = {3 * (1 - fres) + ciel[0] * fres * 0.7f + eclat * 255 * 1.6f + dos * 0.4f,
                            7 * (1 - fres) + ciel[1] * fres * 0.7f + eclat * 240 * 1.6f + dos * 0.7f,
                            18 * (1 - fres) + ciel[2] * fres * 0.7f + eclat * 205 * 1.6f + dos};
      for (int c = 0; c < 3; c++) scene[y][x][c] = scene[y][x][c] * (1 - couv) + eau[c] * couv;
    }
  }
}
