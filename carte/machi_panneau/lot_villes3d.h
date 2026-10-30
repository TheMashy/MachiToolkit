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
inline float v3_mn(float a, float b) { return a < b ? a : b; }   // fminf/fmaxf sans leurs NaN : plus vites
inline float v3_mx(float a, float b) { return a > b ? a : b; }
inline int v3_mod(int a, int n) { return ((a % n) + n) % n; }
inline float v3_fmod(float a, float n) { return a - floorf(a / n) * n; }   // le % de Python (positif)

// sinus et exponentielle rapides (erreur ~1e-5) : sinf et expf coutent cher sur la carte
inline float v3_sin(float x) {
  x -= 6.28318531f * floorf(x * 0.15915494f + 0.5f);   // dans [-pi, pi]
  if (x > 1.57079633f) x = V3_PI - x;
  else if (x < -1.57079633f) x = -V3_PI - x;
  const float z = x * x;
  return x * (1 + z * (-0.16666667f + z * (0.0083333333f + z * (-0.00019841270f + z * 2.7557319e-6f))));
}
inline float v3_cos(float x) { return v3_sin(x + 1.57079633f); }
inline float v3_exp(float x) {
  if (x < -80) return 0;
  if (x > 80) x = 80;
  const float y = x * 1.44269504f, fi = floorf(y), f = y - fi;
  const float p = 1 + f * (0.69314718f + f * (0.24022651f + f * (0.055504109f + f * (0.0096181291f + f * (0.0013333558f + f * 0.00015403530f)))));
  int32_t b;
  memcpy(&b, &p, 4);
  b += (int32_t)((uint32_t)(int32_t)fi << 23);
  float r;
  memcpy(&r, &b, 4);
  return r;
}

// une table lue en interpolant (x * echelle entre 0 et n)
inline float v3_lire(const float *tab, float x, float echelle, int n) {
  const float f = x * echelle;
  if (f >= n) return tab[n];
  const int i = (int)f;
  return tab[i] + (tab[i + 1] - tab[i]) * (f - i);
}

// atan et atan2 rapides (erreur ~1e-5 rad) : l'ocean en fait deux par pixel
inline float v3_atan(float x) {   // |x| <= 1
  const float z = x * x;
  return x * (0.99997726f + z * (-0.33262347f + z * (0.19354346f + z * (-0.11643287f + z * (0.05265332f - z * 0.01172120f)))));
}
inline float v3_atan2(float y, float x) {
  const float ax = fabsf(x), ay = fabsf(y);
  const float mx = ax > ay ? ax : ay, mn = ax > ay ? ay : ax;
  if (mx <= 0) return 0;
  float a = v3_atan(mn / mx);
  if (ay > ax) a = 1.57079633f - a;
  if (x < 0) a = V3_PI - a;
  return y < 0 ? -a : a;
}

// _v3d_creneau : un creneau periodique (allume sur d au milieu) moyenne sur une largeur w autour de
// x : des fenetres sans scintillement, nettes de pres, fondues de loin
inline float v3_cumul(float x, float d) { const float f = floorf(x); return f * d + borne(x - f - (0.5f - d / 2), 0, d); }
inline float v3_creneau(float x, float d, float w) {
  w = v3_mx(w, 1e-3f);
  return (v3_cumul(x + w / 2, d) - v3_cumul(x - w / 2, d)) / w;
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

// Les grands flous (une boite de 9) se font sur une demi-image : la scene reduite (2 x 2 -> 1), deux
// boites de 3, puis relue en bilineaire -- un ecart-type de 2,6 pixels, celui de la boite de 9.
void v3_reduire(float (*d)[32][3]) {
  for (int j = 0; j < 32; j++)
    for (int i = 0; i < 32; i++)
      for (int c = 0; c < 3; c++)
        d[j][i][c] = 0.25f * (scene[2 * j][2 * i][c] + scene[2 * j][2 * i + 1][c] + scene[2 * j + 1][2 * i][c] + scene[2 * j + 1][2 * i + 1][c]);
  v3_flou(&d[0][0][0], 32, 32, 1, 2);
}
struct V3Relire { uint8_t a[64], b[64]; float w[64]; };   // pour chaque ligne (ou colonne) : ses deux voisines et leur poids
inline void v3_relire_prep(V3Relire &r) {
  for (int i = 0; i < 64; i++) {
    const float f = i * 0.5f - 0.25f;
    const int a = (int)floorf(f);
    r.a[i] = (uint8_t)max(0, a); r.b[i] = (uint8_t)min(31, a + 1); r.w[i] = f - a;
  }
}
// Le meme flou en boites, mais « eparpille » : quand peu de pixels brillent, chacun repand sa lumiere sur
// ses voisins avec les poids exacts du flou (bords prolonges compris), au lieu de flouter toute l'image.
struct V3Noyau { float w[64][5]; };   // ce que le pixel i donne au pixel i + d - 2 (boite de 3, deux fois)
void v3_noyau_prep(V3Noyau &k) {
  float o[64 * 3], l[(64 + 16) * 3];
  for (int i = 0; i < 64; i++) {
    for (int j = 0; j < 64 * 3; j++) o[j] = 0;
    o[i * 3] = 1;
    v3_boites(o, 64, 1, 2, l);
    for (int d = 0; d < 5; d++) { const int j = i + d - 2; k.w[i][d] = (j >= 0 && j < 64) ? o[j * 3] : 0; }
  }
}
// repand (r, g, b) du pixel (y, x) dans acc
inline void v3_repandre(float (*acc)[64][3], const V3Noyau &k, int y, int x, float r, float g, float b) {
  if (y >= 2 && y < 62 && x >= 2 && x < 62) {   // loin des bords : le noyau entier, sans tests
    const float *wx = k.w[x];
    for (int dy = 0; dy < 5; dy++) {
      const float wy = k.w[y][dy], ry = wy * r, gy = wy * g, by = wy * b;
      float *p = acc[y + dy - 2][x - 2];
      for (int dx = 0; dx < 5; dx++, p += 3) { p[0] += wx[dx] * ry; p[1] += wx[dx] * gy; p[2] += wx[dx] * by; }
    }
    return;
  }
  for (int dy = 0; dy < 5; dy++) {
    const int yy = y + dy - 2;
    const float wy = k.w[y][dy];
    if (wy == 0) continue;
    for (int dx = 0; dx < 5; dx++) {
      const int xx = x + dx - 2;
      const float w = wy * k.w[x][dx];
      if (w == 0) continue;
      float *p = acc[yy][xx];
      p[0] += w * r; p[1] += w * g; p[2] += w * b;
    }
  }
}
inline void v3_relire(const float (*d)[32][3], const V3Relire &r, int y, int x, float *o) {
  const float *p00 = d[r.a[y]][r.a[x]], *p01 = d[r.a[y]][r.b[x]], *p10 = d[r.b[y]][r.a[x]], *p11 = d[r.b[y]][r.b[x]];
  const float wy = r.w[y], wx = r.w[x];
  for (int c = 0; c < 3; c++) {
    const float h = p00[c] + (p01[c] - p00[c]) * wx, b = p10[c] + (p11[c] - p10[c]) * wx;
    o[c] = h + (b - h) * wy;
  }
}

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

// On vole dans une avenue-canyon. La ville est une grille de cases (une tour par case, des rues en
// travers) ; chaque colonne lance son rayon de case en case et garde la plus proche tour qui couvre
// chaque pixel. Tout ce qui ne depend que de la tour (sa hauteur, ses tirages, ses neons, la largeur
// d'un pixel sur sa facade) est calcule une fois par colonne ; par pixel il reste l'etage, la fenetre,
// la brume. Par-dessus : les enseignes en drapeau et les passerelles (du plus proche au plus loin), les
// voitures volantes, la lueur des neons (en demi-image) et la pluie.

const float V3_CY_F = 30, V3_CY_VITESSE = 0.75f;
const int V3_CY_K = 32;
const float V3_CY_NEONS[6][3] = {{255, 40, 170}, {40, 225, 255}, {255, 205, 50}, {255, 40, 170}, {40, 225, 255}, {170, 80, 255}};
const float V3_CY_VITRES[4][3] = {{255, 175, 90}, {90, 205, 255}, {255, 110, 190}, {230, 235, 255}};

struct V3Auto { float x, y, z, vx, vz, vie; int genre; };
struct V3Objet { float zs, xa, xb, v0, v1, c[3], q; int32_t ident; int genre; };
struct E_cyber_3d {
  uint16_t brume[64 * 64];
  float zbuf[64][64];
  float lum[32][32][3];        // ce qui brille, en demi-image : la lueur
  uint64_t pris[64];           // les pixels deja pris par une enseigne plus proche
  float puiss[257];            // r^1,3
  V3Relire relire;
  V3Auto autos[4];
  float px[55], py[55], pv[55];
  float fz0, phase;
  int32_t g, bz0;
};

inline float v3_cy_hauteur(const E_cyber_3d &e, int32_t ix, int32_t iz) {   // _cyber_hauteurs (0 : une rue)
  const int m = v3_mod(ix, 10);
  if (m == 9 || m == 0 || v3_hasard(iz, 7, e.g + 2) < 0.16f) return 0;   // l'avenue, une avenue en travers, une rue
  const float r = v3_hasard(ix, iz, e.g), r2 = v3_hasard(ix, iz, e.g + 1);
  const bool bord = ix == -2 || ix == 1;                                    // les murs de l'avenue
  float h = bord ? 2.8f + 4.0f * r : 1.0f + 5.5f * v3_lire(e.puiss, r, 256, 256);
  if (bord && r2 < 0.12f) h = 1.2f + 0.8f * r;                             // une tour basse : on voit derriere
  if (r2 > 0.93f) h += 4.5f;                                                 // quelques geantes
  return h;
}
// ajoute a la lueur (demi-image) ce qu'un pixel emet
inline void v3_cy_lueur(E_cyber_3d &e, int y, int x, float r, float g, float b) {
  float *p = e.lum[y >> 1][x >> 1];
  p[0] += r * 0.25f; p[1] += g * 0.25f; p[2] += b * 0.25f;
}

void s_cyber_3d(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cyber_3d &e = etat_ecran<E_cyber_3d>(debut);
  (void)humeur;
  const float F = V3_CY_F;
  if (debut) {
    e.g = (int32_t)(aleatoire() >> 12);
    const float z0 = hasard(0, 3000);
    e.bz0 = (int32_t)floorf(z0); e.fz0 = z0 - e.bz0;
    e.phase = hasard(0, 100);
    brume_n(e.brume, 64, 5);
    for (int i = 0; i < 55; i++) { e.px[i] = hasard(0, 64); e.py[i] = hasard(0, 64); e.pv[i] = hasard(55, 80); }
    for (int i = 0; i < 4; i++) { e.autos[i].vie = -1; e.autos[i].genre = i % 2; }
    for (int i = 0; i <= 256; i++) e.puiss[i] = i ? expf(1.3f * logf(i / 256.0f)) : 0;
    v3_relire_prep(e.relire);
  }
  const int32_t g = e.g;
  // la camera avance dans l'avenue en ondulant doucement ; le nez suit la trajectoire
  const float tau = ecoule + e.phase;
  const float cz = e.fz0 + ecoule * V3_CY_VITESSE;   // (par rapport a la case de depart)
  const float cx = 0.2f * sinf(tau * 0.17f) + 0.07f * sinf(tau * 0.43f + 1.3f);
  const float vx = 0.2f * 0.17f * cosf(tau * 0.17f) + 0.07f * 0.43f * cosf(tau * 0.43f + 1.3f);
  const float cy = 2.7f + 0.5f * sinf(tau * 0.11f + 0.7f) + 0.12f * sinf(tau * 0.31f);
  const float cap = 1.4f * vx / V3_CY_VITESSE, sc = sinf(cap), cc = cosf(cap);
  const float hz = 27.0f + 1.5f * sinf(tau * 0.09f);
  memset(e.lum, 0, sizeof e.lum);
  memset(e.pris, 0, sizeof e.pris);
  // la brume : sa fenetre glisse
  const float box = t * 1.3f, boy = t * 0.4f;
  const int bix = (int)floorf(box), biy = (int)floorf(boy);
  const float bfx = box - bix, bfy = boy - biy;
  // le sol (la rue, noyee de brume) et le ciel ne dependent que de la ligne
  float sg_l[64], tsol_l[64], ciel_l[64][3];
  for (int y = 0; y < 64; y++) {
    const float yc = y + 0.5f, kc = v3_01(yc / v3_mx(hz, 1.0f));
    ciel_l[y][0] = 14 + 82 * kc; ciel_l[y][1] = 7 + 25 * kc; ciel_l[y][2] = 32 + 72 * kc;
    sg_l[y] = cy * F / v3_mx(yc - hz, 0.5f); tsol_l[y] = expf(-sg_l[y] / 8.0f);
  }
  const float fcx = floorf(cx), fcz = floorf(cz);
  for (int col = 0; col < 64; col++) {
    const float sx = col - 31.5f;
    const float dx = sc + cc * sx / F, dz = cc - sc * sx / F, dxs = fabsf(dx) < 1e-6f ? 1e-6f : dx;
    const float lg = sqrtf(dx * dx + dz * dz);
    // les rayons, de case en case : les traversees de lignes x et z, dans l'ordre (a egalite, x d'abord)
    const int pas = dx > 0 ? 1 : -1;
    float ex = (fcx + (pas > 0) - cx) / dxs, ez = (fcz + 1 - cz) / dz;
    const float pex = fabsf(1 / dxs), pez = 1 / dz;
    int ix = (int)fcx, iz = (int)fcz, nx = 0;
    struct Case { float s, h, haut, bas; int32_t ix, iz; bool cote; } cs[V3_CY_K];
    float S = ex <= ez ? ex : ez;
    uint8_t quelle[64];
    int cur = 64;
    float m = 1e30f;
    for (int k = 0; k < V3_CY_K; k++) {
      const bool cote = ex <= ez && nx <= V3_CY_K;
      if (cote) { ix += pas; ex += pex; nx++; } else { iz += 1; ez += pez; }
      const float s_out = ex <= ez ? ex : ez;
      Case &c = cs[k];
      c.ix = ix; c.iz = iz; c.cote = cote;
      c.s = v3_mx(S, 0.05f);
      c.h = v3_cy_hauteur(e, ix, iz + e.bz0);
      c.haut = hz - (c.h - cy) * F / c.s;
      c.bas = hz + cy * F / c.s;   // le pied des tours, qui remonte au loin
      if (c.h > 0) m = v3_mn(m, v3_mn(c.haut, hz - (c.h - cy) * F / s_out));   // avec le toit s'il est sous nous
      S = s_out;
      const float q = m - 0.5f;
      const int r = q <= 0 ? 0 : q >= 64 ? 64 : (int)q + ((float)(int)q < q ? 1 : 0);
      while (cur > r) quelle[--cur] = (uint8_t)k;
    }
    // ce qui ne depend que de la tour vue : calcule a sa premiere ligne dans cette colonne
    int kc = -1;
    float u = 0, pied_v = 0, pied_u = 0, forme_u = 0, dens = 0, net = 0, arete_u = 0, face = 1, latt = 1;
    int32_t tx = 0, tz = 0, bxa = 0, bza = 0;
    const float *teinte_t = V3_CY_VITRES[0];
    bool mur = false, ecran = false;
    float ne_c[2][3], ne_hn[2], ne_h[2], ne_v0[2], ne_vert[2], ec_c[3], ec_in = 0;
    for (int y = 0; y < 64; y++) {
      const float yc = y + 0.5f;
      float *p = scene[y][col];
      const int k = y >= cur ? quelle[y] : -1;
      if (k < 0 || yc >= cs[k].bas) {   // pas de tour : le ciel, ou la rue tout en bas et ses files de feux
        if (yc > hz + 0.5f) {
          const float sg = sg_l[y], ts = tsol_l[y], gx = cx + dx * sg, gz = cz + dz * sg, pg = sg / F;
          const float xl = floorf((gx + 1) / 0.5f) * 0.5f - 0.75f;   // quatre voies
          float feux = 0;
          if (fabsf(gx) < 1) {
            const float lat = v3_01(1 - fabsf(gx - xl) / v3_mx(pg * 1.2f, 0.06f));
            const float sens = xl < 0 ? 1.0f : -1.0f, ph = gz * 0.9f + sens * t * 2.2f + xl * 7.3f, fp = ph - floorf(ph);
            feux = lat * (0.3f + 0.7f * v3_01(1 - fabsf(fp - 0.5f) / v3_mx(0.12f, pg * sg / cy * 0.9f)));
          }
          const float fr = xl < 0 ? 255.0f : 255.0f, fg = xl < 0 ? 235.0f : 45.0f, fb = xl < 0 ? 200.0f : 55.0f;
          p[0] = (18 + feux * fr * 0.55f) * ts + 110 * (1 - ts);
          p[1] = (9 + feux * fg * 0.55f) * ts + 30 * (1 - ts);
          p[2] = (26 + feux * fb * 0.55f) * ts + 100 * (1 - ts);
          if (feux > 0) v3_cy_lueur(e, y, col, feux * fr * 0.3f * ts, feux * fg * 0.3f * ts, feux * fb * 0.3f * ts);
          e.zbuf[y][col] = sg;
        } else {
          p[0] = ciel_l[y][0]; p[1] = ciel_l[y][1]; p[2] = ciel_l[y][2];
          e.zbuf[y][col] = 1e9f;
        }
        continue;
      }
      const Case &c = cs[k];
      const float s = c.s, h = c.h;
      e.zbuf[y][col] = s;
      if (k != kc) {
        kc = k;
        bxa = c.ix; bza = c.iz + e.bz0;
        const uint32_t hb = v3_bits(bxa, bza, g + 3);   // un tirage par tour, decline
        u = c.cote ? cz + dz * s - c.iz : cx + dx * s - c.ix;   // ou l'on est sur la facade
        pied_v = s / F;
        pied_u = pied_v * lg / v3_mx((c.cote ? fabsf(dx) : fabsf(dz)) / lg, 0.06f);
        const int nf = 3 + (int)(v3_u(hb) * 4);
        dens = 0.1f + 0.3f * v3_frac(hb, 8);
        const float fu = u * nf;
        forme_u = v3_creneau(fu, 0.6f, pied_u * nf);
        net = v3_01(2.0f - 2.0f * v3_mx(pied_v / 0.2f, pied_u * nf));
        tx = bxa * 1009 + (int32_t)floorf(fu) * 7 + (c.cote ? 3 : 0); tz = bza * 4099;
        teinte_t = V3_CY_VITRES[(int)(v3_frac(hb, 16) * 3)];
        face = c.cote ? 1.0f : 1.4f;
        arete_u = v3_01(1 - v3_mn(u, 1 - u) / v3_mx(pied_u, 0.02f)) * 0.6f;   // les coins des tours
        latt = v3_exp(-s / 18.0f);
        // les tubes de neon sur les murs de l'avenue
        mur = c.cote && (bxa == -2 || bxa == 1);
        if (mur)
          for (int j = 0; j < 2; j++) {
            const uint32_t r = v3_bits(bxa * 31 + j, bza, g + 8 + j);
            const float rv = v3_u(r);
            const float *nc = V3_CY_NEONS[(int)(v3_frac(r, 8) * 6)];
            for (int q = 0; q < 3; q++) ne_c[j][q] = nc[q];
            ne_hn[j] = 0.6f + v3_frac(r, 16) * v3_mx(h - 1.0f, 0.2f);
            ne_h[j] = rv < 0.45f ? 1.0f : 0.0f;
            const float u0 = 0.15f + 0.7f * v3_frac(r, 12);
            ne_v0[j] = 0.5f + v3_frac(r, 20) * v3_mx(h - 2.2f, 0.1f);
            ne_vert[j] = rv > 0.62f ? v3_01(1 - fabsf(u - u0) / v3_mx(pied_u, 0.03f)) * borne(0.06f / pied_v, 0.35f, 1) : 0;
          }
        // les ecrans geants sur les faces qui nous regardent, au bout des rues en travers
        ecran = !c.cote && v3_frac(hb, 12) < 0.3f && fabsf(u - 0.5f) < 0.38f;
        if (ecran) {
          const float *nc = V3_CY_NEONS[(int)(v3_frac(hb, 20) * 6)];
          for (int q = 0; q < 3; q++) ec_c[q] = nc[q];
          ec_in = -t * 0.6f + bxa * 2.1f + v3_sin(u * 3 + t * 0.4f) * 1.5f;
        }
      }
      const float v = cy - (yc - hz) * s / F;   // la hauteur dans le monde
      // la brume mange le lointain : rose pres de la rue, violette en haut
      const int bx = (col + bix) & 63, by = (y + biy) & 63, bx1 = (bx + 1) & 63, by1 = (by + 1) & 63;
      const float b0 = e.brume[by * 64 + bx] + (e.brume[by * 64 + bx1] - (float)e.brume[by * 64 + bx]) * bfx;
      const float b1 = e.brume[by1 * 64 + bx] + (e.brume[by1 * 64 + bx1] - (float)e.brume[by1 * 64 + bx]) * bfx;
      const float brume = (b0 + (b1 - b0) * bfy) * (1.0f / 65535);
      const float transp = v3_exp(-s / (12.0f * (0.8f + 0.4f * brume))), hv = v3_01(v / 7.0f);
      float surf[3], lum[3] = {0, 0, 0};
      if (yc < c.haut) { surf[0] = 14; surf[1] = 10; surf[2] = 26; }   // le toit
      else {
        // les fenetres : allumees au hasard ; fondues en une lueur moyenne quand elles deviennent trop petites
        const float fv = v * 5, fl = floorf(fv);
        const uint32_t tn = v3_bits(tx, tz + (int32_t)fl, g + 4);
        const float tirage = v3_u(tn);
        float fen = tirage < dens ? v3_creneau(fv, 0.5f, pied_v * 5) * forme_u * (0.45f + 0.55f * v3_frac(tn, 8)) : 0;
        fen = dens * 0.216f + (fen - dens * 0.216f) * net;
        const float *te = v3_frac(tn, 16) < 0.25f ? V3_CY_VITRES[3] : teinte_t;
        const float lu = v3_exp(-v3_mx(v, 0) / 1.4f);
        const float arete = v3_mx(arete_u, v3_01(1 - (h - v) / pied_v));   // et leur sommet
        surf[0] = 7 * face + lu * 38 + fen * te[0] * 0.8f + arete * 34;
        surf[1] = 5 * face + lu * 8 + fen * te[1] * 0.8f + arete * 18;
        surf[2] = 15 * face + lu * 44 + fen * te[2] * 0.8f + arete * 52;
        if (mur)
          for (int j = 0; j < 2; j++) {
            float a = 0;
            if (ne_h[j] > 0) {
              const float cv = v3_mx(0.0f, v3_mn(ne_hn[j] + 0.035f, v + pied_v / 2) - v3_mx(ne_hn[j] - 0.035f, v - pied_v / 2)) / pied_v;
              a = v3_mn(cv * 1.4f, 1);
            }
            if (ne_vert[j] > 0 && v > ne_v0[j] && v < ne_v0[j] + 1.5f) a += ne_vert[j];
            if (a > 0) { lum[0] += a * ne_c[j][0]; lum[1] += a * ne_c[j][1]; lum[2] += a * ne_c[j][2]; }
          }
        if (ecran && v > h * 0.45f && v < h * 0.45f + 1.1f) {
          const float d = 0.5f + 0.5f * v3_sin(v * 5 + ec_in);
          for (int q = 0; q < 3; q++) lum[q] += (ec_c[q] * d + V3_CY_NEONS[1][q] * (1 - d)) * 0.55f;
        }
      }
      const float cb[3] = {110 * (1 - hv) + 58 * hv, 30 * (1 - hv) + 22 * hv, 100 * (1 - hv) + 84 * hv};
      for (int q = 0; q < 3; q++) p[q] = surf[q] * transp + cb[q] * (1 - transp) + lum[q] * latt;
      if (lum[0] + lum[1] + lum[2] > 0) v3_cy_lueur(e, y, col, lum[0] * latt, lum[1] * latt, lum[2] * latt);
    }
  }
  // les passerelles au-dessus de l'avenue, et les enseignes en drapeau accrochees aux murs
  V3Objet obj[48];
  int nobj = 0;
  const int32_t iz0 = (int32_t)fcz;
  for (int n = 0; n < 22; n++) {
    const int32_t rang = iz0 + n, ra = rang + e.bz0;
    for (int m2 = 0; m2 < 2; m2++) {
      const int32_t bxm = m2 ? 1 : -2;
      const float xm = m2 ? 1.0f : -1.0f, sens = m2 ? -1.0f : 1.0f;
      const float hm = v3_cy_hauteur(e, bxm, ra);
      const uint32_t qn = v3_bits(bxm * 13 + 1, ra, g + 20);
      const float q = v3_u(qn);
      if (!(q < 0.6f && hm > 2.0f) || nobj >= 48) continue;
      const float q1 = v3_frac(qn, 6), q2 = v3_frac(qn, 12), q3 = v3_frac(qn, 18), q4 = v3_frac(qn, 24);
      const float v0 = 0.7f + q2 * v3_mn(hm - 1.9f, 3.4f), v1 = v3_mn(v0 + 0.7f + 1.1f * q3, hm - 0.1f);
      const float *nc = V3_CY_NEONS[(int)(q3 * 97) % 6];
      obj[nobj++] = {rang + 0.2f + 0.6f * q1, xm, xm + sens * (0.24f + 0.16f * q4), v0, v1, {nc[0], nc[1], nc[2]}, q1, ra * 2 + bxm, 0};
    }
    const uint32_t qn = v3_bits(ra, 5, g + 23);
    const float q = v3_u(qn);
    if (q < 0.09f && nobj < 48) {
      const float r1 = v3_frac(qn, 8), r2 = v3_frac(qn, 16), v0 = r2 < 0.75f ? 4.4f + 1.2f * r1 : 0.9f;
      const float *nc = V3_CY_NEONS[(int)(r1 * 97) % 6];
      obj[nobj++] = {rang + 0.5f, -1.0f, 1.0f, v0, v0 + 0.22f, {nc[0], nc[1], nc[2]}, r2, ra, 1};
    }
  }
  for (int i = 1; i < nobj; i++)   // du plus proche au plus loin : le plus proche l'emporte sur chaque pixel
    for (int j = i; j > 0 && obj[j].zs < obj[j - 1].zs; j--) { const V3Objet o = obj[j]; obj[j] = obj[j - 1]; obj[j - 1] = o; }
  for (int i = 0; i < nobj; i++) {
    const V3Objet &o = obj[i];
    const float rza = o.zs - cz;
    float ca = 32 + ((o.xa - cx) * cc - rza * sc) * F / v3_mx((o.xa - cx) * sc + rza * cc, 1e-3f), da = (o.xa - cx) * sc + rza * cc;
    float cb = 32 + ((o.xb - cx) * cc - rza * sc) * F / v3_mx((o.xb - cx) * sc + rza * cc, 1e-3f), db = (o.xb - cx) * sc + rza * cc;
    const bool ret = ca > cb;
    if (ret) { float w = ca; ca = cb; cb = w; w = da; da = db; db = w; }
    if (!(da > 0.35f && db > 0.35f)) continue;
    const int c0 = (int)borne(floorf(ca - 0.5f), 0, 64), c1 = (int)borne(ceilf(cb - 0.5f), -1, 63);
    const float hs = o.v1 - o.v0, larg = fabsf(o.xb - o.xa), nr = v3_mx(2.0f, rintf(hs / 0.17f));
    const float souffle = 0.88f + 0.12f * sinf(t * (0.6f + o.q) + o.q * 20);   // certaines respirent, doucement
    for (int col = c0; col <= c1; col++) {
      const float lam = v3_01((col + 0.5f - ca) / v3_mx(cb - ca, 1e-6f)), inv = (1 - lam) / da + lam / db, d = 1 / inv;
      float a = (lam / db) / inv;   // en travers, juste en perspective
      if (ret) a = 1 - a;
      const float haut = hz - (o.v1 - cy) * F / d, bas = hz - (o.v0 - cy) * F / d;
      const float kx = v3_01(v3_mn(col + 1.0f, cb) - v3_mx((float)col, ca));
      if (kx <= 0) continue;
      const float pied = v3_mx(d / F, 0.02f), brouille = v3_exp(-d / 18.0f);
      const float bord_a = v3_01(1 - v3_mn(a, 1 - a) * larg / pied);
      const float netg = v3_01(1.5f - 1.5f * v3_mx(pied * nr / hs, pied * 3 / larg));
      const float lampe_a = 0.7f + 0.3f * v3_sin(a * 40 + t * 1.5f);
      for (int y = max(0, (int)floorf(haut)); y < min(64, (int)ceilf(bas) + 1); y++) {
        const float k = v3_01(v3_mn(y + 1.0f, bas) - v3_mx((float)y, haut)) * kx;
        if (k <= 0 || !(d < e.zbuf[y][col]) || (e.pris[y] >> col & 1)) continue;
        e.pris[y] |= (uint64_t)1 << col;
        const float b = v3_01((y + 0.5f - haut) / v3_mx(bas - haut, 1e-3f));
        float coul[3], em[3];
        if (o.genre == 1) {   // une passerelle : sombre, une rangee de lampes
          const float l = v3_01(1 - fabsf(b - 0.75f) * 0.22f / pied) * lampe_a * 0.9f * brouille;
          static const float sombre[3] = {10, 8, 20}, loin[3] = {40, 16, 60};
          for (int q = 0; q < 3; q++) { em[q] = l * o.c[q]; coul[q] = em[q] + sombre[q] * brouille + (1 - brouille) * loin[q]; }
        } else {   // une enseigne : son cadre vif, ses lignes de caracteres
          const float bord = v3_mx(bord_a, v3_01(1 - v3_mn(b, 1 - b) * hs / pied));
          const float j = floorf(b * nr);
          const float glyphe = v3_hasard(o.ident * 64 + (int32_t)j, (int32_t)(a * 3), g + 22) > 0.4f ? v3_01((0.4f - fabsf(b * nr - j - 0.5f)) / 0.1f + 0.5f) : 0;
          const float force = v3_mx(bord, (0.42f + (glyphe - 0.42f) * netg) * 0.85f) * souffle;
          for (int q = 0; q < 3; q++) em[q] = coul[q] = (o.c[q] * (0.15f + 0.85f * force) + 80 * bord * bord * souffle) * brouille;
        }
        float *p = scene[y][col];
        for (int q = 0; q < 3; q++) p[q] = p[q] * (1 - k) + coul[q] * k;
        v3_cy_lueur(e, y, col, em[0] * k * 0.9f, em[1] * k * 0.9f, em[2] * k * 0.9f);
        if (k > 0.5f) e.zbuf[y][col] = d;
      }
    }
  }
  // les voitures volantes : deux qui traversent l'avenue par les rues en travers, deux qui la suivent
  for (int i = 0; i < 4; i++) {
    V3Auto &a = e.autos[i];
    if (a.vie < 0) {
      if (a.genre == 0) {
        int32_t rues[14];
        int n = 0;
        for (int32_t r = (int32_t)cz + 6; r < (int32_t)cz + 20; r++)
          if (v3_hasard(r + e.bz0, 7, g + 2) < 0.16f) rues[n++] = r;
        const float zr = n ? rues[min(n - 1, (int)hasard(0, (float)n))] + 0.5f : cz + 12;
        const float sens = hasard(0, 1) < 0.5f ? -1.0f : 1.0f;
        a.x = -9.0f * sens; a.y = hasard(1.8f, 4.2f); a.z = zr; a.vx = sens * hasard(1.6f, 2.4f); a.vz = 0; a.vie = 0;
      } else {
        const bool vient = hasard(0, 1) < 0.5f;
        a.x = hasard(-0.6f, 0.6f); a.y = cy + hasard(-0.8f, 0.9f); a.vx = 0; a.vie = 0;
        a.z = cz + (vient ? 24.0f : -1.5f);
        a.vz = vient ? -hasard(0.8f, 1.6f) : V3_CY_VITESSE + hasard(0.5f, 1.0f);
      }
    }
    a.vie += dt; a.x += a.vx * dt; a.z += a.vz * dt;
    const float prof = (a.x - cx) * sc + (a.z - cz) * cc;
    if (fabsf(a.x) > 9.5f || prof > 26 || (prof < 0.3f && a.vie > 1) || a.vie > 40) { a.vie = -1; continue; }
    float pts[7][6];   // x, dy, couleur, force
    int np = 0;
    if (a.genre == 0) {   // vue de cote : phare devant, feu derriere, et sa trainee
      const float sg = a.vx > 0 ? 1.0f : -1.0f;
      const float p0[3][6] = {{a.x + 0.16f * sg, 0, 255, 245, 225, 1.0f}, {a.x - 0.16f * sg, 0, 255, 40, 50, 0.8f}, {a.x, -0.05f, 60, 140, 255, 0.5f}};
      for (int q = 0; q < 3; q++) memcpy(pts[np++], p0[q], sizeof p0[q]);
      for (int k = 1; k < 4; k++) { const float tr[6] = {a.x - (0.16f + 0.12f * k) * sg, 0, 255, 40, 50, 0.35f / k}; memcpy(pts[np++], tr, sizeof tr); }
    } else {
      const bool face = a.vz < 0;
      const float p0[3][6] = {{a.x - 0.11f, 0, 255, face ? 245.0f : 35.0f, face ? 225.0f : 45.0f, 1.0f},
                              {a.x + 0.11f, 0, 255, face ? 245.0f : 35.0f, face ? 225.0f : 45.0f, 1.0f}, {a.x, -0.06f, 60, 140, 255, 0.4f}};
      for (int q = 0; q < 3; q++) memcpy(pts[np++], p0[q], sizeof p0[q]);
    }
    for (int q = 0; q < np; q++) {
      const float rx = pts[q][0] - cx, rz = a.z - cz, d = rx * sc + rz * cc;
      if (d < 0.3f) continue;
      const float sxp = 32 + (rx * cc - rz * sc) * F / d, syp = hz - (a.y + pts[q][1] - cy) * F / d;
      const int iy = (int)floorf(syp), ix = (int)floorf(sxp);
      if (iy >= 0 && iy < 64 && ix >= 0 && ix < 64 && e.zbuf[iy][ix] < d) continue;
      const float rayon = borne(0.05f * F / d, 0.45f, 1.3f);
      const float f = pts[q][5] * v3_exp(-d / 18.0f) * v3_mn(1.0f, 0.25f + 0.25f * a.vie) * v3_mn(1.0f, d / 1.5f)
                      * v3_mn(1.0f, v3_mx(0.0f, (26.0f - prof) / 4));   // elle s'efface avant de disparaitre
      v3_tache(&scene[0][0][0], 0, 64, syp, sxp, rayon, pts[q][2], pts[q][3], pts[q][4], f);
      // et sa lueur, dans la demi-image
      const int rr = (int)(rayon * 2.2f) + 1;
      const float qq = 1.0f / (2 * rayon * rayon);
      for (int yy = max(0, (int)syp - rr); yy < min(64, (int)syp + rr + 2); yy++)
        for (int xx = max(0, (int)sxp - rr); xx < min(64, (int)sxp + rr + 2); xx++) {
          const float ddy = yy + 0.5f - syp, ddx = xx + 0.5f - sxp, w = v3_exp(-(ddx * ddx + ddy * ddy) * qq) * f * 0.6f;
          v3_cy_lueur(e, yy, xx, w * pts[q][2], w * pts[q][3], w * pts[q][4]);
        }
    }
  }
  // la lueur des neons : la demi-image floutee, relue en bilineaire
  v3_flou(&e.lum[0][0][0], 32, 32, 1, 3);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float l[3];
      v3_relire(e.lum, e.relire, y, x, l);
      scene[y][x][0] += l[0] * 0.75f; scene[y][x][1] += l[1] * 0.75f; scene[y][x][2] += l[2] * 0.75f;
    }
  // la pluie fine, qui s'allume dans les neons
  for (int i = 0; i < 55; i++) {
    e.py[i] += e.pv[i] * dt;
    e.px[i] += e.pv[i] * 0.12f * dt;
    e.py[i] = v3_fmod(e.py[i] + 4, 70) - 4;
    e.px[i] = v3_fmod(e.px[i], 64);
    for (int j = 0; j < 3; j++) {
      const int yy = (int)(e.py[i] - j), xx = v3_mod((int)(e.px[i] - j * 0.12f), 64);
      if (yy < 0 || yy >= 64) continue;
      float *p = scene[yy][xx];
      const float ecl = borne((p[0] + p[1] + p[2]) / 3, 0, 160) * 0.35f, k = 1 - j * 0.3f;
      p[0] += (24 + ecl) * k; p[1] += (26 + ecl) * k; p[2] += (40 + ecl) * k;
    }
  }
}

// --- 2. le survol de la ville ---------------------------------------------------------------
// La meme idee de rayons par colonne, vue d'en haut : chaque case est un pate de maisons (un bloc en
// retrait, la rue autour). On voit les toits, les facades tournees vers nous, et dans les rues les
// files de phares et de feux arriere sous les reverberes ; un horizon brumeux, ambre.

const int V3_SV_K = 44;
struct E_survol {
  float lumiere[64][64][3];   // ce qui brille, pour la lueur
  V3Noyau noyau;
  float puiss[257];           // r^1,6
  float phase, fx0, fz0;
  int32_t g, bx0, bz0;        // le hasard de la ville, la case de depart (les positions restent petites)
};
inline float v3_sv_hauteur(const E_survol &e, int32_t ix, int32_t iz) {   // _survol_hauteurs (0 : un parc)
  const uint32_t n = v3_bits(ix, iz, e.g);
  if (v3_frac(n, 16) < 0.07f) return 0;
  if (v3_frac(n, 12) > 0.93f) return 1.3f + 0.9f * v3_frac(n, 8);
  return 0.2f + 0.75f * v3_lire(e.puiss, v3_u(n), 256, 256);
}

void s_survol(int humeur, bool debut, float t, float ecoule, float dt) {
  E_survol &e = etat_ecran<E_survol>(debut);
  (void)humeur; (void)dt;
  const float F = 30, marge = 0.16f, hz = 10;
  if (debut) {
    e.g = (int32_t)(aleatoire() >> 12);
    const float z0 = hasard(0, 3000), x0 = hasard(-500, 500);
    e.bz0 = (int32_t)floorf(z0); e.fz0 = z0 - e.bz0;
    e.bx0 = (int32_t)floorf(x0); e.fx0 = x0 - e.bx0;
    e.phase = hasard(0, 100);
    for (int i = 0; i <= 256; i++) e.puiss[i] = i ? expf(1.6f * logf(i / 256.0f)) : 0;
    v3_noyau_prep(e.noyau);
  }
  const int32_t g = e.g;
  const float tau = ecoule + e.phase;
  const float cx = e.fx0 + 0.3f * sinf(tau * 0.05f), cz = e.fz0 + ecoule * 0.42f;   // (par rapport a la case de depart)
  const float cy = 3.4f + 0.2f * sinf(tau * 0.07f);
  const float cap = 0.32f * sinf(tau * 0.031f) + 0.1f * sinf(tau * 0.083f), sc = sinf(cap), cc = cosf(cap);
  const float s0 = 0.85f * cy * F / (64 - hz);   // rien de plus pres n'est a l'ecran
  // le sol ne depend que de la ligne : sa distance, la largeur d'un pixel, la brume
  struct Sol { float sg, pied, pz, ipied, ipz, ilat, ilg_ns, ilg_ew, k_ns, k_ew, voile, ke, cb[3]; } sol[64];
  for (int y = 0; y < 64; y++) {
    Sol &q = sol[y];
    const float yc = y + 0.5f, sg = v3_mx(cy * F / v3_mx(yc - hz, 0.3f), s0);
    q.sg = sg; q.pied = sg / F; q.pz = q.pied * sg / cy; q.ipied = 1 / q.pied; q.ipz = 1 / q.pz;
    q.ilat = 1 / v3_mx(q.pied * 1.1f, 0.03f);
    const float lns = v3_mx(0.1f, q.pz * 1.6f), lew = v3_mx(0.1f, q.pied * 1.6f);
    q.ilg_ns = 1 / lns; q.ilg_ew = 1 / lew; q.k_ns = v3_mn(1.0f, 0.16f / lns); q.k_ew = v3_mn(1.0f, 0.16f / lew);
    q.voile = 1 - expf(-sg / 14.0f); q.ke = expf(-sg / 24.0f);
    const float a = v3_01((sg - 9.0f) / 16), ph = a * sqrtf(a);
    q.cb[0] = 16 + 84 * ph; q.cb[1] = 20 + 48 * ph; q.cb[2] = 42 + 12 * ph;
  }
  struct File { int32_t ident; float v, d; } files[4];
  for (int l = 0; l < 4; l++) files[l].ident = INT32_MIN;
  struct Feu { int32_t x, z; float h; } feux[48];
  int nfeux = 0;
  for (int col = 0; col < 64; col++) {
    const float sx = col - 31.5f;
    const float dx = sc + cc * sx / F, dz = cc - sc * sx / F, dxs = fabsf(dx) < 1e-6f ? 1e-6f : dx;
    const float lg = sqrtf(dx * dx + dz * dz);
    // les cases traversees, de pres vers le loin (la premiere : la ou le rayon entre a l'ecran)
    const float x0 = cx + dx * s0, z0 = cz + dz * s0;
    const int pas = dx > 0 ? 1 : -1;
    int ix = (int)floorf(x0), iz = (int)floorf(z0);
    float ex = s0 + ((float)ix + (pas > 0) - x0) / dxs, ez = s0 + ((float)iz + 1 - z0) / dz;
    const float pex = fabsf(1 / dxs), pez = 1 / dz, idx = 1 / dxs, idz = 1 / dz;
    int nx = 0, nz = 0;
    struct Case { float s, h, haut, bas, hb, voile, ke, cb[3]; int32_t ix, iz; bool cote; } cs[V3_SV_K + 1];
    uint8_t quelle[64];
    int cur = 64;
    float m = 1e30f;
    for (int k = 0; k <= V3_SV_K; k++) {
      if (k > 0) {   // la traversee suivante (a egalite, celle en x d'abord)
        if (ex <= ez && nx < V3_SV_K) { ix += pas; ex += pex; nx++; }
        else { iz += 1; ez += pez; nz++; }
      }
      Case &c = cs[k];
      c.ix = ix; c.iz = iz;
      const float H = v3_sv_hauteur(e, ix + e.bx0, iz + e.bz0);
      // le bloc en retrait dans sa case : par ou le rayon entre, par ou il sort
      const float ax = (ix + marge - cx) * idx, bx_ = (ix + 1 - marge - cx) * idx;
      const float az = (iz + marge - cz) * idz, bz_ = (iz + 1 - marge - cz) * idz;
      const float tminx = v3_mn(ax, bx_), tminz = v3_mn(az, bz_);
      float sa = v3_mx(tminx, tminz);
      const float sb = v3_mn(v3_mx(ax, bx_), v3_mx(az, bz_));
      const bool touche = H > 0 && sa < sb && sa > 0.1f;
      sa = v3_mx(sa, 0.1f);
      c.s = sa; c.h = H; c.cote = tminx > tminz;
      c.haut = hz + (cy - H) * F / sa;
      c.bas = touche ? hz + cy * F / sa : -1e9f;
      c.hb = v3_hasard(ix + e.bx0, iz + e.bz0, g + 3);
      if (touche) {
        c.voile = 1 - v3_exp(-sa / 14.0f); c.ke = v3_exp(-sa / 24.0f);   // la brume, a la distance du bloc
        const float q = v3_01((sa - 9.0f) / 16), ph = q * sqrtf(q);
        c.cb[0] = 16 + 84 * ph; c.cb[1] = 20 + 48 * ph; c.cb[2] = 42 + 12 * ph;
        m = v3_mn(m, v3_mn(c.haut, hz + (cy - H) * F / v3_mx(sb, 0.1f)));
        if (H > 1.25f && nfeux < 48) {   // le feu rouge au sommet des tours
          bool deja = false;
          for (int i = 0; i < nfeux; i++) deja |= feux[i].x == ix && feux[i].z == iz;
          if (!deja) feux[nfeux++] = {ix, iz, H};
        }
      }
      const float q = m - 0.5f;
      const int r = q <= 0 ? 0 : q >= 64 ? 64 : (int)q + ((float)(int)q < q ? 1 : 0);
      while (cur > r) quelle[--cur] = (uint8_t)k;
    }
    // ce qui ne depend que de la case vue (pour cette colonne) : calcule a sa premiere ligne
    int kc = -1;
    float forme_u = 0, dens = 0, net = 0, pv75 = 0, fface = 1;
    int32_t tx = 0, tz = 0;
    int32_t parc_x = 1 << 30, parc_z = 0;
    bool parc = false;
    for (int y = 0; y < 64; y++) {
      const float yc = y + 0.5f;
      float *p = scene[y][col];
      if (yc < hz) {   // le ciel
        const float k = v3_01((hz - yc) / hz), a = (1 - k) * (1 - k) * (1 - k);
        p[0] = 100 * a + 8 * (1 - a); p[1] = 72 * a + 12 * (1 - a); p[2] = 64 * a + 32 * (1 - a);
        continue;
      }
      float img[3], em[3] = {0, 0, 0};
      const bool vu = y >= cur && yc < cs[quelle[y]].bas;
      if (vu) {
        const Case &c = cs[quelle[y]];
        const float s = c.s, h = c.h;
        if (quelle[y] != kc) {
          kc = quelle[y];
          const float u = c.cote ? cz + dz * s - c.iz : cx + dx * s - c.ix;
          const float pied_v = s / F, pied_u = pied_v * lg / v3_mx((c.cote ? fabsf(dx) : fabsf(dz)) / lg, 0.08f);
          const float fu = (u - marge) / (1 - 2 * marge) * 5, lu = pied_u * 5 / (1 - 2 * marge);
          pv75 = pied_v / 0.075f;
          forme_u = v3_creneau(fu, 0.64f, lu);
          dens = 0.12f + 0.3f * v3_frac(v3_bits(c.ix + e.bx0, c.iz + e.bz0, g + 3), 8);
          net = v3_01(2.0f - 2.0f * v3_mx(pv75, lu));
          tx = (c.ix + e.bx0) * 977 + (int32_t)floorf(fu) * 5 + (c.cote ? 2 : 0);
          tz = (c.iz + e.bz0) * 3001;
          fface = c.cote ? 1.0f : 1.3f;
        }
        if (yc < c.haut) {   // les toits : bleu nuit, leur rebord un peu plus clair
          const float sr = (cy - h) * F / v3_mx(yc - hz, 0.3f);
          const float rx = cx + dx * sr - c.ix, rz = cz + dz * sr - c.iz;
          const float rb = v3_01(1 - v3_mn(v3_mn(rx - marge, 1 - marge - rx), v3_mn(rz - marge, 1 - marge - rz)) / v3_mx(sr / F, 0.02f));
          const float k = 0.8f + 0.4f * c.hb;
          img[0] = 9 * k + rb * 16; img[1] = 11 * k + rb * 16; img[2] = 21 * k + rb * 26;
        } else {   // les facades : des etages de fenetres chaudes, fondues en lueur quand elles sont trop petites
          img[0] = 14 * fface; img[1] = 14 * fface; img[2] = 26 * fface;
          const float fv = (cy - (yc - hz) * s / F) * (1 / 0.075f), fl = floorf(fv);
          float fen = 0;
          const uint32_t tn = v3_bits(tx, tz + (int32_t)fl, g + 4);
          if (v3_u(tn) < dens && fl >= 1) fen = v3_creneau(fv - 0.05f, 0.4f, pv75) * forme_u * (0.6f + 0.6f * v3_frac(tn, 8));
          fen = dens * 0.1f + (fen - dens * 0.1f) * net;
          if (v3_frac(tn, 16) < 0.1f) { em[0] = fen * 200; em[1] = fen * 215; em[2] = fen * 255; }
          else { em[0] = fen * 255; em[1] = fen * 175; em[2] = fen * 90; }
        }
      } else {   // le sol : les rues, leurs reverberes, et les phares qui coulent
        const Sol &q = sol[y];
        const float gx = cx + dx * q.sg, gz = cz + dz * q.sg;
        const float rgx = rintf(gx), rgz = rintf(gz), fx = gx - rgx, fz = gz - rgz;
        const int32_t px = (int32_t)floorf(gx), pz = (int32_t)floorf(gz);
        if (px != parc_x || pz != parc_z) { parc_x = px; parc_z = pz; parc = v3_sv_hauteur(e, px + e.bx0, pz + e.bz0) == 0; }
        if (parc) { img[0] = 7; img[1] = 14; img[2] = 12; }
        else {
          img[0] = 10; img[1] = 10; img[2] = 17;
          const float afx = fabsf(fx), afz = fabsf(fz);
          const float b1 = v3_mx(0.0f, v3_mn(marge, afx + q.pied * 0.5f) - v3_mx(-marge, afx - q.pied * 0.5f)) * q.ipied;
          const float b2 = v3_mx(0.0f, v3_mn(marge, afz + q.pz * 0.5f) - v3_mx(-marge, afz - q.pz * 0.5f)) * q.ipz;
          const float rv = v3_mx(b1, b2) * 0.42f + b1 * b2 * 0.5f;   // la lumiere orangee des reverberes
          em[0] = rv * 200; em[1] = rv * 110; em[2] = rv * 40;
        }
        for (int l = 0; l < 4; l++) {   // quatre files : deux sens dans les rues nord-sud, deux dans les autres
          const bool ns = l < 2;
          const float alat = ns ? fx : fz;
          if (fabsf(alat) >= marge) continue;
          const float voie = (l & 1) ? -0.055f : 0.055f, lat = v3_01(1 - fabsf(alat - voie) * q.ilat);
          if (lat <= 0) continue;
          const float sens = (l == 0 || l == 3) ? 1.0f : -1.0f;
          const int32_t ident = (int32_t)(ns ? rgx : rgz) + (ns ? e.bx0 : e.bz0), isens = (int32_t)sens;
          File &f = files[l];
          if (f.ident != ident) {   // la vitesse et le decalage de cette file : un tirage par rue
            f.ident = ident;
            f.v = sens * t * (0.55f + 0.25f * v3_hasard(ident, isens * 3, g + 9));
            f.d = v3_hasard(ident, isens, g + 8) * 7;
          }
          const float ph = (ns ? gz : gx) * 1.6f - f.v + f.d, fph = ph - floorf(ph);
          const float il = ns ? q.ilg_ns : q.ilg_ew;
          float voit = v3_01(1 - fabsf(fph - 0.5f) * il) * (ns ? q.k_ns : q.k_ew);
          if (voit > 0 && v3_hasard(ident * 7 + (int32_t)floorf(ph), isens, g + 10) >= 0.7f) voit = 0;
          const float k = lat * (0.12f + 1.1f * voit);
          if (sens > 0) { em[0] += k * 255; em[1] += k * 240; em[2] += k * 215; }
          else { em[0] += k * 255; em[1] += k * 45; em[2] += k * 35; }
        }
      }
      // la brume de l'horizon, ambre au loin, bleu nuit en haut
      float voile, ke;
      const float *cb;
      if (vu) { const Case &c = cs[quelle[y]]; voile = c.voile; ke = c.ke; cb = c.cb; }
      else { voile = sol[y].voile; ke = sol[y].ke; cb = sol[y].cb; }
      for (int c = 0; c < 3; c++) p[c] = img[c] * (1 - voile) + cb[c] * voile + em[c] * ke;
    }
  }
  for (int i = 0; i < nfeux; i++) {   // le feu rouge au sommet des tours, qui respire
    const float rx = feux[i].x + 0.5f - cx, rz = feux[i].z + 0.5f - cz, pr = rx * sc + rz * cc;
    if (pr <= 0.5f) continue;
    const float colx = 32 + (rx * cc - rz * sc) * F / pr, lig = hz - (feux[i].h + 0.03f - cy) * F / pr;
    const float f = (0.5f + 0.5f * sinf(t * 1.4f + (feux[i].x + e.bx0) * 1.7f + (feux[i].z + e.bz0))) * expf(-pr / 13.0f);
    pointer(lig, colx, f * 255, f * 40, f * 30);
  }
  // la lueur de ce qui brille (peu de pixels : repandue de chacun)
  memset(e.lumiere, 0, sizeof e.lumiere);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float *p = scene[y][x];
      if (p[0] > 90 || p[1] > 90 || p[2] > 90)
        v3_repandre(e.lumiere, e.noyau, y, x, v3_mx(p[0] - 90, 0) * 0.7f, v3_mx(p[1] - 90, 0) * 0.7f, v3_mx(p[2] - 90, 0) * 0.7f);
    }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] += e.lumiere[y][x][c];
}

// --- 3. la ruelle neon sous la pluie ----------------------------------------------------------
// La camera ne bouge pas : toute la geometrie (les deux murs, le sol, le bout de la rue), l'eclairage
// fixe et les enseignes (leur dessin, leur halo, la lumiere qu'elles jettent) sont calcules a la
// premiere image. A chaque image : les enseignes qui gresillent, le sol mouille qui les reflete (le
// reflet d'un mur dans le sol, c'est le mur retourne autour de son pied), les ronds des gouttes, la
// vapeur, un passant, la pluie.

const float V3_RL_F = 32, V3_RL_HZ = 29, V3_RL_CX = 0.15f, V3_RL_CY = 0.8f, V3_RL_XG = -1.0f, V3_RL_XD = 1.1f, V3_RL_BOUT = 9.0f;
// les enseignes en drapeau : z, x du mur, saillie, y bas, y haut, couleur, defaillante
const float V3_RL_DRAPEAUX[4][9] = {{3.4f, -1.0f, 0.45f, 1.05f, 2.35f, 255, 45, 160, 0}, {2.3f, 1.1f, -0.42f, 1.35f, 2.75f, 255, 185, 50, 0},
                                    {5.4f, 1.1f, -0.36f, 0.95f, 1.9f, 50, 220, 255, 1}, {6.9f, -1.0f, 0.32f, 1.45f, 2.4f, 170, 90, 255, 0}};
// les enseignes a plat sur les murs : mur, z0, z1, y0, y1, couleur, defaillante
const float V3_RL_PLATES[3][9] = {{0, 4.6f, 6.0f, 1.6f, 2.0f, 40, 230, 255, 0}, {1, 3.1f, 4.5f, 2.4f, 2.8f, 255, 60, 150, 1},
                                  {0, 7.7f, 8.6f, 1.15f, 1.45f, 255, 120, 60, 0}};
const float V3_RL_ALBEDO[6][3] = {{0, 0, 0}, {0.62f, 0.45f, 0.55f}, {0.5f, 0.45f, 0.62f}, {1.0f, 0.9f, 1.1f}, {0.42f, 0.4f, 0.48f}, {0.55f, 0.5f, 0.55f}};
const float V3_RL_GMAX = 2.2f;   // le plus fort eclairage d'une enseigne (fois l'albedo) : l'echelle des tables

struct V3RlGeo {   // ce que voit un pixel de la ruelle
  bool gauche, mur, face, sol;
  float sx, sy, s_mur, y_mur, haut_mur, s_sol, y_face, x_face, gx, gz, pied, P[3], N[3];
};
void v3_rl_geo(int y, int x, V3RlGeo &g) {
  const float F = V3_RL_F, cx = V3_RL_CX, cy = V3_RL_CY;
  g.sx = x + 0.5f - 32; g.sy = y + 0.5f - V3_RL_HZ;
  g.gauche = g.sx < 0;
  g.s_mur = g.gauche ? (cx - V3_RL_XG) * F / fmaxf(-g.sx, 1e-6f) : (V3_RL_XD - cx) * F / fmaxf(g.sx, 1e-6f);
  g.y_mur = cy - g.sy * g.s_mur / F;
  g.haut_mur = g.gauche ? (g.s_mur < 6 ? 3.6f : 3.0f) : (g.s_mur < 4.2f ? 4.3f : 3.7f);
  g.mur = g.s_mur < V3_RL_BOUT && g.y_mur < g.haut_mur && g.y_mur > -0.01f;
  g.s_sol = g.sy > 0 ? cy * F / fmaxf(g.sy, 1e-6f) : 1e9f;
  const float s_face = V3_RL_BOUT + 1.5f;
  g.y_face = cy - g.sy * s_face / F; g.x_face = cx + g.sx * s_face / F;
  g.face = !g.mur && g.y_face < 4.6f && g.y_face >= 0 && s_face < g.s_sol;
  g.sol = !g.mur && !g.face && g.sy > 0;
  g.gx = cx + g.sx * g.s_sol / F; g.gz = g.s_sol;
  g.N[0] = g.N[1] = g.N[2] = 0;
  if (g.mur) { g.P[0] = g.gauche ? V3_RL_XG : V3_RL_XD; g.P[1] = g.y_mur; g.P[2] = g.s_mur; g.N[0] = g.gauche ? 1 : -1; }
  else if (g.face) { g.P[0] = g.x_face; g.P[1] = g.y_face; g.P[2] = s_face; g.N[2] = -1; }
  else { g.P[0] = g.gx; g.P[1] = 0; g.P[2] = fminf(g.gz, 60); if (g.sol) g.N[1] = 1; }
  g.pied = (g.mur ? g.s_mur : g.sol ? g.s_sol : s_face) / F;
}
// _ruelle_lumiere : ce qu'une lampe en L donne au point du pixel (sans sa couleur)
inline float v3_rl_lumiere(const V3RlGeo &g, float lx, float ly, float lz, float force, float rayon) {
  const float d[3] = {lx - g.P[0], ly - g.P[1], lz - g.P[2]};
  const float d2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2];
  const float face = v3_01((d[0] * g.N[0] + d[1] * g.N[1] + d[2] * g.N[2]) / sqrtf(d2 + 1e-6f)) * 0.75f + 0.25f;
  return force * face * expf(-1.3f * logf(1 + d2 / (rayon * rayon)));
}

struct V3Boite { int16_t x0, y0, w, h; uint16_t off; };   // un petit rectangle de l'ecran, range dans la reserve
struct E_ruelle {
  uint8_t base[64][64][3];      // l'eclairage fixe, les fenetres, le ciel, les fils, la bouche d'egout
  uint8_t genre[64][64];        // 0 ciel, 1 mur gauche, 2 mur droit, 3 corniche, 4 sol, 5 facade du bout
  uint8_t jet[7][64][64];       // la lumiere que chaque enseigne jette (fois l'albedo), racine, sur 255
  uint8_t flaque[64][64];       // 0-255
  uint8_t brume[64][64];        // la vapeur
  int16_t bloc[37][64][3];      // le reflet du sol (lignes 27 a 63), puis le flou sous la vapeur
  uint8_t reserve[16384];       // les enseignes (couverture, dessin, halo), les lampes, les reflets fixes
  V3Boite ens[7], emis, refl;
  uint16_t couverts[600];       // les pixels qu'une enseigne couvre
  float yref[64];               // le pied des murs, par colonne : y_reflet = arrondi(yref - y - 0.5)
  float gouttes[14][4];         // x, z, naissance, force
  float px[50], py[50], pv[50];
  float suivante;
  int ncouverts, libre;
};

// range une boite (x0, y0, w, h) de `octets` par pixel dans la reserve
bool v3_rl_ranger(E_ruelle &e, V3Boite &b, int x0, int y0, int x1, int y1, int octets) {
  x0 = max(0, x0); y0 = max(0, y0); x1 = min(64, x1); y1 = min(64, y1);
  b.x0 = x0; b.y0 = y0; b.w = max(0, x1 - x0); b.h = max(0, y1 - y0); b.off = e.libre;
  const int n = b.w * b.h * octets;
  if (e.libre + n > (int)sizeof e.reserve) { b.w = b.h = 0; return false; }
  e.libre += n;
  return true;
}
// la plus petite boite des pixels non nuls de la scene (servant de brouillon)
void v3_rl_cadre(int &x0, int &y0, int &x1, int &y1) {
  x0 = 64; y0 = 64; x1 = 0; y1 = 0;
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      if (scene[y][x][0] > 0.5f || scene[y][x][1] > 0.5f || scene[y][x][2] > 0.5f) { x0 = min(x0, x); x1 = max(x1, x + 1); y0 = min(y0, y); y1 = max(y1, y + 1); }
}

void v3_rl_preparer(E_ruelle &e) {
  const float F = V3_RL_F, hz = V3_RL_HZ, cx = V3_RL_CX, cy = V3_RL_CY;
  // les deux champs de hasard : les taches des murs et du sol, les flaques (brouillon : la scene)
  uint16_t *tache = (uint16_t *)&scene[0][0][0], *flaques = tache + 4096;
  brume_n(tache, 64, 4);
  brume_n(flaques, 64, 6);
  static const float lampes[3][8] = {{-0.93f, 1.35f, 2.5f, 255, 165, 80, 1.6f, 0.6f}, {1.03f, 1.3f, 7.45f, 255, 165, 80, 1.4f, 0.6f},
                                     {0.05f, 0.9f, 10.3f, 230, 165, 110, 1.5f, 2.0f}};
  static const float fenetres[7][4] = {{6.3f, 2.5f, 1, 1}, {3.0f, 3.2f, 0, 1}, {8.1f, 2.2f, 1, 1}, {2.6f, 2.95f, 1, 0}, {6.0f, 2.6f, 1, 0},
                                       {8.3f, 2.7f, 0, 0}, {4.1f, 3.5f, 1, 0}};
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      V3RlGeo g;
      v3_rl_geo(y, x, g);
      const float tc = tache[y * 64 + x] * (1.0f / 65535);
      // les matieres : brique sombre, taches, portes en retrait ; l'asphalte ; la facade d'en face
      const float yv = g.y_mur, z = g.s_mur;
      const float brique = 0.92f + 0.08f * borne(sinf(yv * 2 * V3_PI / 0.16f) * 3, -1, 1) * v3_01(1 - g.pied / 0.06f);
      int genre = g.mur ? (g.gauche ? 1 : 2) : g.sol ? 4 : g.face ? 5 : 0;
      float a = brique * (0.7f + 0.6f * tc);
      if (g.mur && ((g.gauche && fabsf(z - 2.5f) < 0.32f) || (!g.gauche && fabsf(z - 7.45f) < 0.28f)) && yv < 1.15f) a *= 0.3f;   // les portes
      if (g.mur && fabsf(yv - g.haut_mur + 0.06f) < fmaxf(g.pied * 0.7f, 0.05f)) { genre = 3; a = 1; }                       // la corniche
      if (g.sol) a = 0.75f + 0.5f * tc;
      if (g.face) a = 1;
      e.genre[y][x] = genre;
      const float *alb = V3_RL_ALBEDO[genre == 0 ? (g.gauche ? 1 : 2) : genre];
      // l'eclairage fixe : la lueur du ciel, les lampes des portes, la lumiere du bout de la rue
      float ecl[3];
      const float amb = 1.15f - 0.55f * v3_01(g.P[1] / 4);
      ecl[0] = 44 * amb; ecl[1] = 32 * amb; ecl[2] = 66 * amb;
      for (int l = 0; l < 3; l++) {
        const float k = v3_rl_lumiere(g, lampes[l][0], lampes[l][1], lampes[l][2], lampes[l][6], lampes[l][7]);
        for (int c = 0; c < 3; c++) ecl[c] += k * lampes[l][3 + c];
      }
      float img[3];
      for (int c = 0; c < 3; c++) img[c] = alb[c] * a * ecl[c];
      for (int f = 0; f < 7; f++) {   // les fenetres : sombres
        const bool cote = fenetres[f][3] > 0;
        if (g.mur && g.gauche == cote && fabsf(z - fenetres[f][0]) < 0.3f && fabsf(yv - fenetres[f][1]) < 0.28f) { img[0] = 6; img[1] = 5; img[2] = 10; }
      }
      if (genre == 0) {   // le ciel : une bande etroite entre les toits, rougie par la ville
        const float kc = v3_01(y / 22.0f);
        img[0] = 14 + 56 * kc; img[1] = 10 + 24 * kc; img[2] = 30 + 50 * kc;
      }
      float fl = 0;
      if (g.sol) {   // les flaques, la bouche d'egout
        const int fy = (int)v3_fmod(g.gz * 5, 64) % 64, fx = (int)v3_fmod(g.gx * 9, 64) % 64;
        fl = v3_01((flaques[fy * 64 + fx] * (1.0f / 65535) - 0.42f) / 0.08f);
        const float u = (g.gx - 0.35f) / 0.32f, v = (g.gz - 3.2f) / 0.22f, trou = u * u + v * v;
        if (trou < 1) {
          for (int c = 0; c < 3; c++) img[c] *= 0.45f;
          if (trou > 0.6f) { img[0] += 14; img[1] += 12; img[2] += 18; }
        }
        if (trou < 1.2f) fl = 0;
      }
      e.flaque[y][x] = (uint8_t)(fl * 255 + 0.5f);
      for (int c = 0; c < 3; c++) e.base[y][x][c] = (uint8_t)borne(img[c] + 0.5f, 0, 255);
      // la lumiere de chaque enseigne sur ce pixel (fois son albedo), en racine sur 255
      for (int k = 0; k < 7; k++) {
        float L[3], force, rayon;
        if (k < 4) {
          const float *d = V3_RL_DRAPEAUX[k];
          L[0] = d[1] + d[2] / 2; L[1] = (d[3] + d[4]) / 2; L[2] = d[0]; force = 1.6f; rayon = 0.95f;
        } else {
          const float *d = V3_RL_PLATES[k - 4];
          L[0] = d[0] == 0 ? V3_RL_XG + 0.15f : V3_RL_XD - 0.15f; L[1] = (d[3] + d[4]) / 2; L[2] = (d[1] + d[2]) / 2; force = 1.3f; rayon = 0.9f;
        }
        const float j = genre ? v3_rl_lumiere(g, L[0], L[1], L[2], force, rayon) * a : 0;
        e.jet[k][y][x] = (uint8_t)(sqrtf(v3_01(j / V3_RL_GMAX)) * 255 + 0.5f);
      }
    }
  // les fils qui traversent le ciel (chaque pixel assombri une fois par fil)
  static const float fils[2][6] = {{-1.0f, 3.3f, 1.1f, 3.6f, 0.4f, 3.9f}, {-1.0f, 2.9f, 1.1f, 3.1f, 0.25f, 7.8f}};
  for (int f = 0; f < 2; f++) {
    uint8_t vu[64][8];
    memset(vu, 0, sizeof vu);
    for (int i = 0; i < 120; i++) {
      const float k = i / 119.0f, wx = fils[f][0] + (fils[f][2] - fils[f][0]) * k;
      const float wy = fils[f][1] + (fils[f][3] - fils[f][1]) * k - fils[f][4] * 4 * k * (1 - k), zf = fils[f][5];
      const int c = (int)(32 + (wx - cx) * F / zf), r = (int)(hz - (wy - cy) * F / zf);
      if (r < 0 || r >= 64 || c < 0 || c >= 64 || (vu[r][c >> 3] >> (c & 7) & 1)) continue;
      vu[r][c >> 3] |= 1 << (c & 7);
      V3RlGeo g;
      v3_rl_geo(r, c, g);
      if (e.genre[r][c] == 0 || g.s_mur > zf)
        for (int q = 0; q < 3; q++) e.base[r][c][q] = (uint8_t)(e.base[r][c][q] * 0.45f + 4 + 0.5f);
    }
  }
  // le pied des murs, par colonne (le reflet retourne l'image autour de lui)
  for (int x = 0; x < 64; x++) {
    V3RlGeo g;
    v3_rl_geo(40, x, g);
    const float s_pied = g.s_mur < V3_RL_BOUT ? g.s_mur : V3_RL_BOUT + 1.5f;
    e.yref[x] = 2 * (hz + cy * F / s_pied) - 0.5f;
  }
  // ce qui brille sans bouger : les fenetres allumees, les ampoules, la vitrine du bout, la guirlande
  memset(scene, 0, sizeof(float) * 64 * 64 * 3);
  float *img = &scene[0][0][0];
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      V3RlGeo g;
      v3_rl_geo(y, x, g);
      float *p = scene[y][x];
      for (int f = 0; f < 7; f++) {
        const bool cote = fenetres[f][3] > 0;
        if (fenetres[f][2] > 0 && g.mur && g.gauche == cote && fabsf(g.s_mur - fenetres[f][0]) < 0.3f && fabsf(g.y_mur - fenetres[f][1]) < 0.28f) {
          const float store = 0.7f + 0.3f * (sinf(g.y_mur * 2 * V3_PI / 0.1f) > 0 ? 1 : 0) * v3_01(1 - g.pied / 0.05f);
          p[0] = 255 * 0.55f * store; p[1] = 165 * 0.55f * store; p[2] = 85 * 0.55f * store;
        }
      }
    }
  for (int l = 0; l < 2; l++)   // les ampoules des portes
    v3_tache(img, 0, 64, hz - (lampes[l][1] - cy) * F / lampes[l][2], 32 + (lampes[l][0] - cx) * F / lampes[l][2], 0.6f, 255, 200, 130, 1.0f);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      V3RlGeo g;
      v3_rl_geo(y, x, g);
      if (!g.face) continue;
      float *p = scene[y][x];
      const float xf = g.x_face, yf = g.y_face;
      if (fabsf(xf - 0.05f) < 0.8f && yf > 0.15f && yf < 1.0f) { p[0] = 220; p[1] = 160; p[2] = 100; }
      if (fabsf(yf - 1.35f) < 0.08f && fabsf(xf - 0.05f) < 0.6f) { p[0] = 60; p[1] = 230; p[2] = 200; }
      if (fabsf(v3_fmod(yf - 2, 0.8f) - 0.3f) < 0.18f && fabsf(v3_fmod(xf + 2, 0.7f) - 0.35f) < 0.15f && yf > 1.8f && sinf(xf * 9.1f + yf * 3.7f) > 0.2f) {
        p[0] = 110; p[1] = 85; p[2] = 60;
      }
    }
  static const float guirlande[3][3] = {{255, 200, 120}, {255, 120, 160}, {140, 220, 255}};
  for (int i = 0; i < 9; i++) {   // la guirlande d'ampoules, en travers de la ruelle
    const float kk = 0.06f + 0.88f * i / 8, wx = V3_RL_XG + (V3_RL_XD - V3_RL_XG) * kk, wy = 2.75f - 0.32f * 4 * kk * (1 - kk), wz = 4.4f + 0.3f * kk;
    v3_tache(img, 0, 64, hz - (wy - cy) * F / wz, 32 + (wx - cx) * F / wz, 0.55f, guirlande[i % 3][0], guirlande[i % 3][1], guirlande[i % 3][2], 0.9f);
  }
  int x0, y0, x1, y1;
  v3_rl_cadre(x0, y0, x1, y1);
  if (v3_rl_ranger(e, e.emis, x0, y0, x1, y1, 3))
    for (int y = 0; y < e.emis.h; y++)
      for (int x = 0; x < e.emis.w; x++)
        for (int c = 0; c < 3; c++) e.reserve[e.emis.off + (y * e.emis.w + x) * 3 + c] = (uint8_t)borne(scene[y + e.emis.y0][x + e.emis.x0][c] + 0.5f, 0, 255);
  memset(scene, 0, sizeof(float) * 64 * 64 * 3);
  for (int i = 0; i < 9; i++) {   // et son reflet dans le sol mouille
    const float kk = 0.06f + 0.88f * i / 8, wx = V3_RL_XG + (V3_RL_XD - V3_RL_XG) * kk, wy = 2.75f - 0.32f * 4 * kk * (1 - kk), wz = 4.4f + 0.3f * kk;
    v3_tache(img, 0, 64, hz + (wy + cy) * F / wz, 32 + (wx - cx) * F / wz, 0.7f, guirlande[i % 3][0], guirlande[i % 3][1], guirlande[i % 3][2], 0.35f);
  }
  v3_rl_cadre(x0, y0, x1, y1);
  if (v3_rl_ranger(e, e.refl, x0, y0, x1, y1, 3))
    for (int y = 0; y < e.refl.h; y++)
      for (int x = 0; x < e.refl.w; x++)
        for (int c = 0; c < 3; c++) e.reserve[e.refl.off + (y * e.refl.w + x) * 3 + c] = (uint8_t)borne(scene[y + e.refl.y0][x + e.refl.x0][c] + 0.5f, 0, 255);
  // les enseignes : leur couverture, leur dessin, leur halo (le dessin flou) -- chacune a part
  e.ncouverts = 0;
  for (int k = 0; k < 7; k++) {
    memset(scene, 0, sizeof(float) * 64 * 64 * 3);
    uint8_t couv[64][64];
    memset(couv, 0, sizeof couv);
    int cx0 = 64, cy0 = 64, cx1 = 0, cy1 = 0;
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        V3RlGeo g;
        float cv = 0, d[3] = {0, 0, 0};
        if (k < 4) {
          const float *q = V3_RL_DRAPEAUX[k], zs = q[0];
          const float xa = fminf(q[1], q[1] + q[2]), xb = fmaxf(q[1], q[1] + q[2]);
          const float ca = 32 + (xa - cx) * F / zs, cb = 32 + (xb - cx) * F / zs, ha = hz - (q[4] - cy) * F / zs, ba = hz - (q[3] - cy) * F / zs;
          cv = v3_01(fminf(x + 1.0f, cb) - fmaxf((float)x, ca)) * v3_01(fminf(y + 1.0f, ba) - fmaxf((float)y, ha));
          if (cv <= 0) continue;
          v3_rl_geo(y, x, g);
          if (g.mur && !(zs < g.s_mur)) continue;
          const float a = v3_01((x + 0.5f - ca) / (cb - ca)), b = v3_01((y + 0.5f - ha) / (ba - ha));
          const float bord = fmaxf(v3_01(1.5f - fminf(a, 1 - a) * (cb - ca)), v3_01(1.5f - fminf(b, 1 - b) * (ba - ha)));
          const float nr = fmaxf(3.0f, rintf((q[4] - q[3]) / 0.2f)), j = floorf(b * nr);
          const float glyphe = (v3_hasard((int32_t)(j + zs * 100), (int32_t)(a * 3), 31) > 0.35f && fabsf(b * nr - j - 0.5f) < 0.32f) ? 1 : 0;
          for (int c = 0; c < 3; c++) d[c] = (q[5 + c] * (0.12f + 0.8f * fmaxf(bord, glyphe * 0.9f)) + 70 * bord * bord) * cv;
        } else {
          const float *q = V3_RL_PLATES[k - 4];
          v3_rl_geo(y, x, g);
          const float z = g.s_mur, yv = g.y_mur;
          if (!(g.mur && g.gauche == (q[0] == 0) && z > q[1] && z < q[2] && yv > q[3] && yv < q[4])) continue;
          cv = 1;
          const float pz = g.pied * fmaxf(fabsf(g.sx) / 4, 1);
          const bool bord = fminf(z - q[1], q[2] - z) < fmaxf(pz, 0.05f) || fminf(yv - q[3], q[4] - yv) < fmaxf(g.pied, 0.04f);
          const bool lettres = sinf((z - q[1]) * 2 * V3_PI / 0.22f) > 0.1f && fabsf(yv - (q[3] + q[4]) / 2) < (q[4] - q[3]) * 0.28f;
          const float m = fmaxf(bord ? 1.0f : 0.0f, lettres ? borne(1.5f - pz / 0.08f, 0.3f, 1) : 0.0f);
          for (int c = 0; c < 3; c++) d[c] = q[5 + c] * (0.15f + 0.85f * m) + (bord ? 50 : 0);
        }
        couv[y][x] = (uint8_t)(cv * 255 + 0.5f);
        for (int c = 0; c < 3; c++) scene[y][x][c] = d[c];
        cx0 = min(cx0, x); cy0 = min(cy0, y); cx1 = max(cx1, x + 1); cy1 = max(cy1, y + 1);
      }
    V3Boite &b = e.ens[k];
    if (cx1 <= cx0 || !v3_rl_ranger(e, b, cx0 - 4, cy0 - 4, cx1 + 4, cy1 + 4, 7)) { b.w = b.h = 0; continue; }
    uint8_t *r = e.reserve + b.off;
    const int n = b.w * b.h;
    for (int y = 0; y < b.h; y++)
      for (int x = 0; x < b.w; x++) {
        const int i = y * b.w + x, Y = y + b.y0, X = x + b.x0;
        r[i] = couv[Y][X];
        for (int c = 0; c < 3; c++) r[n + i * 3 + c] = (uint8_t)borne(scene[Y][X][c] * 0.8f + 0.5f, 0, 255);
        if (couv[Y][X]) {
          bool deja = false;
          for (int j = 0; j < e.ncouverts; j++) deja |= e.couverts[j] == Y * 64 + X;
          if (!deja && e.ncouverts < 600) e.couverts[e.ncouverts++] = Y * 64 + X;
        }
      }
    v3_flou(img, 64, 64, 2, 2);   // le halo
    for (int y = 0; y < b.h; y++)
      for (int x = 0; x < b.w; x++)
        for (int c = 0; c < 3; c++) r[4 * n + (y * b.w + x) * 3 + c] = (uint8_t)borne(scene[y + b.y0][x + b.x0][c] * 0.8f + 0.5f, 0, 255);
  }
  // la vapeur
  uint16_t *v = (uint16_t *)&scene[0][0][0];
  brume_n(v, 64, 4);
  for (int i = 0; i < 4096; i++) e.brume[i >> 6][i & 63] = (uint8_t)(v[i] >> 8);
}

void s_ruelle(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ruelle &e = etat_ecran<E_ruelle>(debut);
  (void)humeur;
  const float F = V3_RL_F, hz = V3_RL_HZ, cx = V3_RL_CX, cy = V3_RL_CY;
  if (debut) {
    e.libre = 0;
    v3_rl_preparer(e);
    for (int i = 0; i < 14; i++) e.gouttes[i][2] = -100;
    for (int i = 0; i < 50; i++) { e.px[i] = hasard(0, 64); e.py[i] = hasard(0, 64); e.pv[i] = hasard(50, 75); }
    e.suivante = 0;
  }
  // les enseignes qui gresillent ; deux faiblissent par moments, en douceur
  float f[7], fc[7][3];
  for (int i = 0; i < 7; i++) {
    f[i] = 0.9f + 0.05f * sinf(t * 1.3f + i * 2.1f) + 0.03f * sinf(t * 7.9f + i) + 0.02f * sinf(t * 13.1f + i * 3);
    const float *q = i < 4 ? V3_RL_DRAPEAUX[i] : V3_RL_PLATES[i - 4];
    if (q[8] > 0) {
      const float ph = v3_fmod(t / (6.3f + i) + i * 0.37f, 1);
      const float a = sinf(V3_PI * v3_01(ph / 0.07f)), b = sinf(V3_PI * v3_01((ph - 0.09f) / 0.05f));
      f[i] *= 1 - 0.5f * a * a - 0.3f * b * b;
    }
    for (int c = 0; c < 3; c++) fc[i][c] = f[i] * q[5 + c] * (V3_RL_GMAX / 65025.0f);
  }
  // l'eclairage fixe, et la lumiere des enseignes (racine -> carre)
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float acc[3] = {0, 0, 0};
      for (int k = 0; k < 7; k++) {
        const int q = e.jet[k][y][x];
        if (!q) continue;
        const float w = (float)(q * q);
        acc[0] += w * fc[k][0]; acc[1] += w * fc[k][1]; acc[2] += w * fc[k][2];
      }
      const float *alb = V3_RL_ALBEDO[e.genre[y][x]];
      for (int c = 0; c < 3; c++) scene[y][x][c] = e.base[y][x][c] + alb[c] * acc[c];
    }
  for (int k = 0; k < 7; k++) {   // les halos
    const V3Boite &b = e.ens[k];
    const uint8_t *h = e.reserve + b.off + 4 * b.w * b.h;
    const float g = f[k] * 1.25f;
    for (int y = 0; y < b.h; y++)
      for (int x = 0; x < b.w; x++)
        for (int c = 0; c < 3; c++) scene[y + b.y0][x + b.x0][c] += h[(y * b.w + x) * 3 + c] * g;
  }
  for (int i = 0; i < e.ncouverts; i++) {   // sous les enseignes : dans l'ordre, chacune couvre ce qui est derriere
    const int Y = e.couverts[i] >> 6, X = e.couverts[i] & 63;
    const float *alb = V3_RL_ALBEDO[e.genre[Y][X]];
    float v[3] = {(float)e.base[Y][X][0], (float)e.base[Y][X][1], (float)e.base[Y][X][2]};
    for (int k = 0; k < 7; k++) {
      const float w = (float)(e.jet[k][Y][X] * e.jet[k][Y][X]);
      for (int c = 0; c < 3; c++) v[c] += alb[c] * w * fc[k][c];
      const V3Boite &b = e.ens[k];
      const int x = X - b.x0, y = Y - b.y0;
      if (x < 0 || y < 0 || x >= b.w || y >= b.h) continue;
      const int n = b.w * b.h, j = y * b.w + x;
      const uint8_t *r = e.reserve + b.off;
      const float cv = r[j] * (1.0f / 255), g = f[k] * 1.25f;
      for (int c = 0; c < 3; c++) v[c] = v[c] * (1 - cv) + (r[n + j * 3 + c] + r[4 * n + j * 3 + c]) * g;
    }
    for (int c = 0; c < 3; c++) scene[Y][X][c] = v[c];
  }
  {   // ce qui brille sans bouger
    const V3Boite &b = e.emis;
    const uint8_t *r = e.reserve + b.off;
    for (int y = 0; y < b.h; y++)
      for (int x = 0; x < b.w; x++)
        for (int c = 0; c < 3; c++) scene[y + b.y0][x + b.x0][c] += r[(y * b.w + x) * 3 + c];
  }
  // un passant sous son parapluie, de temps en temps, dans la rue du bout
  const float cycle = v3_fmod(t / 34.0f, 1);
  if (cycle < 0.62f) {
    const float wx = -2.2f + cycle / 0.62f * 4.6f, wz = V3_RL_BOUT + 0.9f;
    const float col = 32 + (wx - cx) * F / wz, k = F / wz, pas = sinf(t * 5.0f) * 0.04f;
    for (int y = max(0, (int)(hz - 1.6f * k)); y < min(64, (int)(hz + k) + 2); y++)
      for (int x = max(0, (int)(col - 0.4f * k) - 1); x < min(64, (int)(col + 0.4f * k) + 2); x++) {
        const float X = x + 0.5f, Y = y + 0.5f, u = (X - col) / (0.34f * k), v = (Y - (hz - (1.2f - cy) * k)) / (0.16f * k);
        const bool corps = fabsf(X - col) < 0.13f * k + 0.25f && Y > hz - (1.0f - cy) * k && Y < hz + cy * k - pas * k;
        const bool pluie_ = u * u + v * v < 1 && Y > hz - (1.36f - cy) * k;
        const int gn = e.genre[y][x];
        const bool loin = gn != 1 && gn != 2 && gn != 3 && !(gn == 4 && y + 0.5f - hz >= cy * F / 9.6f);
        if ((corps || pluie_) && loin) {
          float *p = scene[y][x];
          p[0] = p[0] * 0.12f + 6; p[1] = p[1] * 0.12f + 5; p[2] = p[2] * 0.12f + 10;
        }
      }
  }
  // les ronds des gouttes dans les flaques
  if (ecoule >= e.suivante) {
    e.suivante = ecoule + hasard(0.08f, 0.22f);
    int i = 0;
    for (int j = 1; j < 14; j++) if (e.gouttes[j][2] < e.gouttes[i][2]) i = j;
    e.gouttes[i][0] = hasard(-0.9f, 1.0f); e.gouttes[i][1] = hasard(1.0f, 6.5f); e.gouttes[i][2] = t; e.gouttes[i][3] = hasard(0.6f, 1.0f);
  }
  // l'onde du sol (dans le premier canal du bloc, x 8192) : la pluie fine, plus les ronds. Le long d'une
  // ligne, gx avance d'un pas fixe : on tourne le sinus au lieu de le recalculer
  const float O = 8192;
  for (int y = 27; y < 64; y++) {
    const float sy = y + 0.5f - hz;
    if (sy <= 0) { for (int x = 0; x < 64; x++) e.bloc[y - 27][x][0] = 0; continue; }
    const float gz = cy * F / sy, a = 0.3f * v3_sin(gz * 6 + t * 1.3f) * O;
    const float p0 = (cx + (0.5f - 32) * gz / F) * 7 - t * 0.9f, dp = 7 * gz / F;
    float sn = v3_sin(p0), cs = v3_cos(p0);
    const float sd = v3_sin(dp), cd = v3_cos(dp);
    for (int x = 0; x < 64; x++) {
      e.bloc[y - 27][x][0] = (int16_t)(a * sn);
      const float s2 = sn * cd + cs * sd;
      cs = cs * cd - sn * sd;
      sn = s2;
    }
  }
  for (int i = 0; i < 14; i++) {
    const float x0 = e.gouttes[i][0], z0 = e.gouttes[i][1], age = t - e.gouttes[i][2], a0 = e.gouttes[i][3];
    if (!(age >= 0 && age < 1.4f)) continue;
    const float R = age * 0.35f + 0.25f, amp = a0 * (1 - age / 1.4f);
    const int ya = max(27, (int)(hz + cy * F / (z0 + R)) - 1), yb = min(64, (int)(hz + cy * F / fmaxf(z0 - R, 0.3f)) + 2);
    for (int y = ya; y < yb; y++) {
      const float sy = y + 0.5f - hz;
      if (sy <= 0) continue;
      const float gz = cy * F / sy;
      if (fabsf(gz - z0) > R) continue;
      const int xa = max(0, (int)((x0 - R - cx) * F / gz + 32) - 1), xb = min(64, (int)((x0 + R - cx) * F / gz + 32) + 2);
      for (int x = xa; x < xb; x++) {
        const float gx = cx + (x + 0.5f - 32) * gz / F, d = hypotf(gx - x0, gz - z0) - age * 0.35f, q = d / 0.06f;
        if (q * q > 12) continue;
        const float o = e.bloc[y - 27][x][0] + amp * v3_sin(d * 40) * v3_exp(-q * q) * O;
        e.bloc[y - 27][x][0] = (int16_t)borne(o, -32000, 32000);
      }
    }
  }
  // le reflet dans le sol mouille : l'image retournee autour du pied des murs, que l'onde fait onduler
  float dra[4][4];   // le reflet de chaque drapeau : ses lignes et ses colonnes a l'ecran
  for (int k = 0; k < 4; k++) {
    const float *q = V3_RL_DRAPEAUX[k], zs = q[0];
    dra[k][0] = hz + (q[3] + cy) * F / zs; dra[k][1] = hz + (q[4] + cy) * F / zs;
    dra[k][2] = 32 + (v3_mn(q[1], q[1] + q[2]) - cx) * F / zs; dra[k][3] = 32 + (v3_mx(q[1], q[1] + q[2]) - cx) * F / zs;
  }
  for (int y = 27; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float onde = e.bloc[y - 27][x][0] * (1 / O);
      const int dy = (int)rintf(onde * 1.3f), dxp = (int)rintf(onde * 0.8f);
      const int yr = (int)borne(rintf(e.yref[x] - y - 0.5f), -1, 63) + dy, xr = min(63, max(0, x + dxp));
      float r[3];
      if (yr >= 0) {
        const int yc = min(63, yr);
        if (e.genre[yc][xr] == 4) r[0] = r[1] = r[2] = 0;
        else { r[0] = scene[yc][xr][0]; r[1] = scene[yc][xr][1]; r[2] = scene[yc][xr][2]; }
      } else { r[0] = 40; r[1] = 20; r[2] = 50; }
      const int ys = min(63, max(0, y + dy));   // et les reflets des enseignes, de la guirlande
      const V3Boite &b = e.refl;
      if (ys >= b.y0 && ys < b.y0 + b.h && xr >= b.x0 && xr < b.x0 + b.w) {
        const uint8_t *q = e.reserve + b.off + ((ys - b.y0) * b.w + xr - b.x0) * 3;
        r[0] += q[0]; r[1] += q[1]; r[2] += q[2];
      }
      if (e.genre[ys][xr] == 4)
        for (int k = 0; k < 4; k++) {
          const float ky = v3_mn(ys + 1.0f, dra[k][1]) - v3_mx((float)ys, dra[k][0]);
          if (ky <= 0) continue;
          const float kx = v3_mn(xr + 1.0f, dra[k][3]) - v3_mx((float)xr, dra[k][2]);
          if (kx <= 0) continue;
          const float *q = V3_RL_DRAPEAUX[k], k2 = v3_mn(ky, 1) * v3_mn(kx, 1) * 0.5625f * f[k];
          r[0] += q[5] * k2; r[1] += q[6] * k2; r[2] += q[7] * k2;
        }
      for (int c = 0; c < 3; c++) e.bloc[y - 27][x][c] = (int16_t)borne(r[c] * 32, 0, 32000);
      if (e.genre[y][x] == 4) {
        const float k = e.flaque[y][x] * (0.7f / 255);
        for (int c = 0; c < 3; c++) scene[y][x][c] += r[c] * k;
      }
    }
  v3_flou16((uint16_t *)&e.bloc[0][0][0], 64, 37, 1, 2);
  for (int y = 29; y < 64; y++)
    for (int x = 0; x < 64; x++)
      if (e.genre[y][x] == 4) {
        const float k = (1 - e.flaque[y][x] * (1.0f / 255)) * (0.2f / 32);
        for (int c = 0; c < 3; c++) scene[y][x][c] += e.bloc[y - 27][x][c] * k;
      }
  // la vapeur qui monte de la bouche d'egout, eclairee par les neons
  const float bx = 32 + (0.35f - cx) * F / 3.2f, by = hz + cy * F / 3.2f;
  float v_centre[23], v_larg[23], v_haut[23];   // le panache, ligne par ligne (14 a 36)
  int vx0 = 64, vx1 = 0;
  for (int y = 14; y < 37; y++) {
    const float hauteur = v3_01((by - y) / 24.0f);
    v_haut[y - 14] = (y >= by || hauteur >= 1) ? 0 : expf(1.1f * logf(1 - hauteur));
    v_larg[y - 14] = 1.8f + hauteur * 9;
    v_centre[y - 14] = bx + sinf(y * 0.15f - t * 0.6f) * hauteur * 3 + hauteur * 5;
    if (v_haut[y - 14] <= 0) continue;
    vx0 = min(vx0, max(0, (int)(v_centre[y - 14] - 1.7f * v_larg[y - 14])));
    vx1 = max(vx1, min(64, (int)(v_centre[y - 14] + 1.7f * v_larg[y - 14]) + 2));
  }
  // l'image un peu floue sous la vapeur (dans le bloc, x 32), seulement la ou elle passe (et 2 de marge)
  const int bx0 = max(0, vx0 - 2), bx1 = min(64, vx1 + 2), bw = max(1, bx1 - bx0);
  int16_t *bl = &e.bloc[0][0][0];
  for (int y = 12; y < 39; y++)
    for (int x = bx0; x < bx1; x++)
      for (int c = 0; c < 3; c++) bl[((y - 12) * bw + x - bx0) * 3 + c] = (int16_t)borne(scene[y][x][c] * 32, 0, 32000);
  if (bx1 > bx0) v3_flou16((uint16_t *)bl, bw, 27, 2, 1);
  const float ox = t * 0.6f, oy = t * 6.0f, fx = ox - floorf(ox), fy = oy - floorf(oy);
  const int ix = (int)floorf(ox), iy = (int)floorf(oy);
  for (int y = 14; y < 37; y++) {
    const float haut = v_haut[y - 14], larg = v_larg[y - 14], centre = v_centre[y - 14];
    if (haut <= 0) continue;
    for (int x = max(vx0, (int)(centre - 1.7f * larg)); x < min(vx1, (int)(centre + 1.7f * larg) + 2); x++) {
      const float u = (x - centre) / larg, panache = v3_exp(-u * u) * haut;
      const float b00 = e.brume[(y + iy) & 63][(x + ix) & 63], b01 = e.brume[(y + iy) & 63][(x + ix + 1) & 63];
      const float b10 = e.brume[(y + iy + 1) & 63][(x + ix) & 63], b11 = e.brume[(y + iy + 1) & 63][(x + ix + 1) & 63];
      const float br = ((b00 * (1 - fx) + b01 * fx) * (1 - fy) + (b10 * (1 - fx) + b11 * fx) * fy) * (1.0f / 255);
      const float vap = borne(panache * (0.35f + br) - 0.08f, 0, 0.9f);
      if (vap <= 0) continue;
      float *p = scene[y][x];
      static const float teinte_v[3] = {84, 74, 100};
      const int16_t *q = bl + ((y - 12) * bw + x - bx0) * 3;
      for (int c = 0; c < 3; c++) p[c] = p[c] * (1 - vap * 0.55f) + (teinte_v[c] + q[c] * (0.8f / 32)) * vap * 0.9f;
    }
  }
  // la pluie, qu'on ne voit que dans la lumiere
  for (int i = 0; i < 50; i++) {
    e.py[i] += e.pv[i] * dt;
    e.px[i] += e.pv[i] * 0.08f * dt;
    e.py[i] = v3_fmod(e.py[i] + 4, 70) - 4;
    e.px[i] = v3_fmod(e.px[i], 64);
    for (int j = 0; j < 3; j++) {
      const int yy = (int)(e.py[i] - j), xx = v3_mod((int)(e.px[i] - j * 0.08f), 64);
      if (yy < 0 || yy >= 64) continue;
      float *p = scene[yy][xx];
      const float eclaire = fminf(150.0f, fmaxf(0.0f, (p[0] + p[1] + p[2]) / 3)) * 0.45f, k = 1 - j * 0.3f;
      p[0] += (14 + eclaire) * k; p[1] += (15 + eclaire) * k; p[2] += (22 + eclaire) * k;
    }
  }
}

// --- 4. le pare-brise sous la pluie ----------------------------------------------------------
// Derriere la vitre, la ville floue (des disques de lumiere et leurs reflets sur la chaussee) ; sur la
// vitre, une carte de l'eau (chaque goutte y pose son disque, son reflet vif, son bord sombre) que
// l'essuie-glace efface la ou il passe, en laissant un film d'eau un instant.

struct E_pare_brise {
  uint8_t eau[64][64], film[64][64], hi[64][64], rim[64][64];   // 0-255
  float flou[64][64][3];                                        // le fond un peu flou (ce que voit le film d'eau)
  float large[32][32][3];                                       // tres flou, en demi-image (ce que voit une goutte)
  float lueur[4][64], bord[64];                                 // le tableau de bord
  V3Relire relire;
  float vx[26], vy[26], vr[26], vp[26];
  float angle, phase;
};

inline float v3_pb_angle(float ecoule) {   // les essuie-glaces : au repos couches a droite, un aller-retour de 3,2 s
  const float ph = v3_fmod(ecoule, 8.0f);
  if (ph >= 3.2f) return 0.12f;
  const float s = sinf(V3_PI * ph / 3.2f);
  return 0.12f + (2.75f - 0.12f) * s * s;
}

void v3_pb_goutte(E_pare_brise &e) {   // une goutte se pose : son disque, son reflet vif en haut a gauche, son bord sombre
  const float x0 = hasard(0, 64), y0 = hasard(0, 56), r = hasard(0.9f, 2.1f);
  const int ya = max(0, (int)(y0 - r - 1)), yb = min(64, (int)(y0 + r + 2));
  const int xa = max(0, (int)(x0 - r - 1)), xb = min(64, (int)(x0 + r + 2));
  for (int y = ya; y < yb; y++)
    for (int x = xa; x < xb; x++) {
      const float yy = y + 0.5f, xx = x + 0.5f, d = hypotf(xx - x0, yy - y0);
      const float disque = v3_01(r - d + 0.5f);
      const float hi = v3_01(1 - hypotf(xx - x0 + r * 0.35f, yy - y0 + r * 0.35f) / 0.8f);
      const float rim = disque * v3_01((yy - y0) / r * 1.4f - 0.3f) * v3_01(1 - (r - d) / 1.2f);
      e.eau[y][x] = max(e.eau[y][x], (uint8_t)(disque * 255 + 0.5f));
      e.hi[y][x] = max(e.hi[y][x], (uint8_t)(hi * 255 + 0.5f));
      e.rim[y][x] = max(e.rim[y][x], (uint8_t)(rim * 255 + 0.5f));
    }
}

struct V3Disque { float x, y, r, c[3], f; };

void s_pare_brise(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pare_brise &e = etat_ecran<E_pare_brise>(debut);
  (void)humeur;
  const float hz = 33;
  if (debut) {
    e.angle = v3_pb_angle(ecoule);
    e.phase = hasard(0, 60);
    for (int i = 0; i < 30; i++) v3_pb_goutte(e);   // la pluie a deja commence
    for (int i = 0; i < 26; i++) { e.vx[i] = hasard(0, 64); e.vy[i] = hasard(10, 31); e.vr[i] = hasard(0.8f, 1.8f); e.vp[i] = hasard(0, 6); }
    v3_relire_prep(e.relire);
    for (int i = 0; i < 64; i++) {
      const float a = (i - 16) / 8.0f, b = (i - 59) / 3.0f, c = (i - 36) / 5.0f, d = (i - 59) / 2.5f;
      e.lueur[0][i] = expf(-a * a); e.lueur[1][i] = expf(-b * b); e.lueur[2][i] = 0.6f * expf(-c * c); e.lueur[3][i] = expf(-d * d);
      e.bord[i] = 55.5f - 2.0f * sinf(v3_01((i + 0.5f) / 64) * V3_PI);
    }
  }
  dt = fminf(dt, 0.5f);
  const float tau = ecoule + e.phase;
  // derriere la vitre : la rue de nuit, floue
  for (int y = 0; y < 64; y++) {
    const float k = borne(y / hz, 0, 1);
    const float r = y < hz ? 8 + 26 * k : 14, g = y < hz ? 8 + 12 * k : 11, b = y < hz ? 22 + 18 * k : 22;
    for (int x = 0; x < 64; x++) { scene[y][x][0] = r; scene[y][x][1] = g; scene[y][x][2] = b; }
  }
  const float feu = v3_fmod(tau / 46.0f, 1);   // le feu : rouge longtemps, puis vert, orange
  const float rouge = v3_01(feu / 0.02f) * v3_01((0.62f - feu) / 0.02f);
  const float vert = v3_01((feu - 0.63f) / 0.02f) * v3_01((0.92f - feu) / 0.02f);
  const float orange = v3_01((feu - 0.93f) / 0.01f) * v3_01((1.0f - feu) / 0.02f);
  V3Disque d[52];
  int n = 0;
  for (int i = 0; i < 26; i++) {   // des fenetres floues, loin
    const bool chaud = e.vp[i] < 4;
    d[n++] = {e.vx[i], e.vy[i], e.vr[i], {chaud ? 255.0f : 150.0f, chaud ? 190.0f : 200.0f, chaud ? 120.0f : 255.0f},
              0.13f + 0.03f * sinf(t * 0.3f + e.vp[i])};
  }
  static const float fixes[9][7] = {{5, 5, 4.2f, 255, 150, 60, 0.6f}, {15, 13, 3.0f, 255, 150, 60, 0.55f}, {22, 19, 2.1f, 255, 160, 70, 0.5f},
                                    {27, 23, 1.5f, 255, 160, 70, 0.45f}, {60, 4, 4.5f, 255, 150, 60, 0.6f}, {50, 12, 3.2f, 255, 150, 60, 0.55f},
                                    {3, 27, 5.5f, 255, 40, 150, 0.4f}, {61, 24, 5.0f, 40, 200, 255, 0.4f}, {55, 29, 3.0f, 170, 80, 255, 0.35f}};
  for (int i = 0; i < 9; i++) d[n++] = {fixes[i][0], fixes[i][1], fixes[i][2], {fixes[i][3], fixes[i][4], fixes[i][5]}, fixes[i][6]};
  d[n++] = {44, 6, 2.4f, {255, 40, 40}, 0.95f * rouge + 0.07f};
  d[n++] = {44, 11.5f, 2.4f, {255, 170, 30}, 0.95f * orange + 0.05f};
  d[n++] = {44, 17, 2.4f, {40, 255, 140}, 0.95f * vert + 0.05f};
  for (int k = 0; k < 3; k++) {   // les voitures qui croisent, pendant notre rouge
    const float cyc = v3_fmod(tau / 9.0f + k / 3.0f, 1);
    const float sens = k % 2 ? 1.0f : -1.0f, x = sens > 0 ? -14 + cyc * 92 : 78 - cyc * 92, y = 31.0f + k % 2;
    const float sn = fmaxf(0.0f, sinf(V3_PI * cyc)), f = rouge * (sn > 0 ? expf(0.3f * logf(sn)) : 0);
    d[n++] = {x, y, 2.2f, {255, 245, 220}, 0.75f * f};
    d[n++] = {x - 5 * sens, y, 1.9f, {255, 245, 220}, 0.65f * f};
    d[n++] = {x - 17 * sens, y, 1.6f, {255, 40, 40}, 0.4f * f};
  }
  const float freins = 0.5f + 0.5f * v3_01(1 - vert * 1.5f);   // la voiture devant : ses feux stop
  const int n_avant = n;
  d[n++] = {23, 36, 3.0f, {255, 30, 30}, 0.9f * freins};
  d[n++] = {41, 36, 3.0f, {255, 30, 30}, 0.9f * freins};
  d[n++] = {32, 39, 1.4f, {230, 220, 200}, 0.2f};
  for (int i = 0; i < n; i++) {
    if (i == n_avant)   // la caisse de la voiture devant
      for (int y = 27; y < 42; y++) {
        const float demi = 13 - fmaxf(31.0f - y, 0) * 0.8f, ar = (y - 36) / 4.0f, stop = 30 * freins * expf(-ar * ar);
        for (int x = 0; x < 64; x++)
          if (fabsf(x + 0.5f - 32) < demi) {
            float *p = scene[y][x];
            p[0] = p[0] * 0.25f + 14 + stop; p[1] = p[1] * 0.25f + 10 + stop * (8.0f / 30); p[2] = p[2] * 0.25f + 20 + stop * (10.0f / 30);
          }
      }
    const V3Disque &q = d[i];
    if (q.f <= 0.01f) continue;
    const int xa = max(0, (int)(q.x - q.r - 2)), xb = min(64, (int)(q.x + q.r + 3));
    const int ya = max(0, (int)(q.y - q.r - 2)), yb = min(64, (int)(q.y + q.r + 3));
    if (xa >= xb) continue;
    const float ir = 1 / q.r;
    for (int y = ya; y < yb; y++)   // un bokeh : un disque net, au bord plus vif
      for (int x = xa; x < xb; x++) {
        const float ddx = x + 0.5f - q.x, ddy = y + 0.5f - q.y, dd = sqrtf(ddx * ddx + ddy * ddy), u = dd * ir;
        const float k = v3_01((q.r - dd) / 0.9f + 0.5f) * (0.75f + 0.25f * u * u) * q.f;
        if (k <= 0) continue;
        float *p = scene[y][x];
        p[0] += k * q.c[0]; p[1] += k * q.c[1]; p[2] += k * q.c[2];
      }
    if (q.f > 0.15f && q.r > 1.4f) {   // son reflet sur la chaussee mouillee
      const float y1 = q.y > hz - 6 ? fmaxf(q.y + q.r + 1, hz + 1) : hz + (hz - q.y) * 0.35f, lg = 3 + q.r * 1.6f;
      const int ra = (int)fmaxf(hz, y1 - 1), rb = (int)fminf(54, y1 + lg * 2.2f);
      float kx[24];
      for (int x = xa; x < xb && x - xa < 24; x++) { const float u = (x + 0.5f - q.x) / (0.55f * q.r); kx[x - xa] = expf(-u * u); }
      for (int y = ra; y < rb; y++) {
        const float ys = y + 0.5f, v = (ys - y1) / lg;
        const float ky = expf(-v * v) * (0.75f + 0.25f * sinf(ys * 1.7f + t * 2.0f + q.x)) * q.f * 0.4f;
        for (int x = xa; x < xb && x - xa < 24; x++) {
          const float k = ky * kx[x - xa];
          float *p = scene[y][x];
          p[0] += k * q.c[0]; p[1] += k * q.c[1]; p[2] += k * q.c[2];
        }
      }
    }
  }
  // un peu de flou leve la lumiere
  v3_reduire(e.large);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float l[3];
      v3_relire(e.large, e.relire, y, x, l);
      for (int c = 0; c < 3; c++) scene[y][x][c] += l[c] * 0.3f;
    }
  // la pluie qui arrive sur la vitre (Poisson, 7 par seconde)
  if (dt > 0) {
    const float seuil = expf(-7 * dt);
    float p = hasard(0, 1);
    while (p > seuil) { v3_pb_goutte(e); p *= hasard(0, 1); }
  }
  // l'essuie-glace efface l'eau la ou il passe, et laisse un film
  const float a0 = e.angle, a1 = v3_pb_angle(ecoule);
  e.angle = a1;
  const float fondu = expf(-dt / 0.5f);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) e.film[y][x] = (uint8_t)(e.film[y][x] * fondu);
  static const float pivots[2][3] = {{14, 71, 50}, {44, 70, 42}};
  if (fabsf(a1 - a0) > 1e-4f) {
    const float lo = fminf(a0, a1) - 0.03f, hi = fmaxf(a0, a1) + 0.03f;
    const float cl = cosf(lo), sl = sinf(lo), ch = cosf(hi), sh = sinf(hi);
    for (int p = 0; p < 2; p++) {
      const float px = pivots[p][0], py = pivots[p][1], L = pivots[p][2];
      for (int y = 0; y < 64; y++) {
        const float dy = py - (y + 0.5f);   // toujours > 0 : les angles restent entre 0 et pi
        for (int x = 0; x < 64; x++) {
          const float dx = x + 0.5f - px, r2 = dx * dx + dy * dy;
          if (r2 >= (L + 1) * (L + 1) || r2 <= 64) continue;
          if (cl * dy - sl * dx < 0 || ch * dy - sh * dx > 0) continue;   // ang >= lo et ang <= hi
          e.eau[y][x] = e.hi[y][x] = e.rim[y][x] = 0;
          e.film[y][x] = 255;
        }
      }
    }
  }
  memcpy(e.flou, scene, sizeof e.flou);
  v3_flou(&e.flou[0][0][0], 64, 64, 1, 2);
  v3_reduire(e.large);   // une goutte voit large : elle ramasse la lumiere
  // les balais (leur angle), la lueur du tableau de bord
  const float ca = cosf(a1), sa = -sinf(a1);
  float lueur_x[64], lueur_y[64];
  for (int i = 0; i < 64; i++) {
    const float u = (i - 18) / 14.0f, v = (i - 52) / 3.0f;
    lueur_x[i] = expf(-u * u); lueur_y[i] = expf(-v * v) * 0.22f;
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float *p = scene[y][x];
      const uint8_t g8 = e.eau[y][x], h8 = e.hi[y][x], r8 = e.rim[y][x], f8 = e.film[y][x];
      if (g8 | h8 | r8 | f8) {   // la vitre seche ne change rien
        const float g = g8 * (1.0f / 255), h = h8 * (1.0f / 255), rim = r8 * (1.0f / 255), f = f8 * (1.0f / 255);
        const float base[3] = {5, 5, 9}, eclat[3] = {16, 17, 24}, fil[3] = {8, 8, 12};
        float lg[3];
        if (g8 | h8) v3_relire(e.large, e.relire, y, x, lg);
        else lg[0] = lg[1] = lg[2] = 0;
        for (int c = 0; c < 3; c++) {
          float v = p[c] * (1 - g) + (lg[c] * 1.5f + base[c]) * g + h * (lg[c] * 2.4f + eclat[c]);
          v *= 1 - rim * 0.5f;
          p[c] = v * (1 - f * 0.3f) + e.flou[y][x][c] * f * 0.3f + f * fil[c];
        }
      }
      for (int b = 0; b < 2; b++) {
        const float dx = x + 0.5f - pivots[b][0], dy = y + 0.5f - pivots[b][1];
        const float u = dx * ca + dy * sa;   // le long du balai
        if (u <= 9 || u >= pivots[b][2]) continue;
        const float v = -dx * sa + dy * ca;   // en travers
        const float balai = v3_01(1.6f - fabsf(v + 0.3f)), reflet = v3_01(1 - fabsf(v - 1.2f)) * 0.25f;
        p[0] = p[0] * (1 - balai * 0.93f) + balai * 8 + reflet * 40;
        p[1] = p[1] * (1 - balai * 0.93f) + balai * 8 + reflet * 40;
        p[2] = p[2] * (1 - balai * 0.93f) + balai * 12 + reflet * 52;
      }
      const float l = lueur_y[y] * lueur_x[x];
      p[0] += l * 60; p[1] += l * 160; p[2] += l * 200;
    }
  // l'habitacle : le haut du pare-brise et le retroviseur, les montants, le tableau de bord et sa lueur
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float X = x + 0.5f, Y = y + 0.5f, u = (X - 32) / 32;
      const float r1 = (X - 33) / 6.0f, r2 = (Y - 3.0f) / 3.6f, r3 = (X - 33) / 4.8f, r4 = (Y - 3.3f) / 2.5f;
      float *p = scene[y][x];
      if (Y < 1.6f + u * u * 2.5f || X < (64 - y) * 0.05f || X > 64 - (64 - y) * 0.05f || r1 * r1 + r2 * r2 < 1) {
        p[0] = 6; p[1] = 6; p[2] = 9;
      }
      if (r3 * r3 + r4 * r4 < 1) { p[0] = 22; p[1] = 16; p[2] = 28; }   // ce que le retroviseur voit
      const float bord = e.bord[x];
      if (Y > bord) {
        const float lueur = e.lueur[0][x] * e.lueur[1][y] + e.lueur[2][x] * e.lueur[3][y];
        p[0] = 8 + lueur * 30; p[1] = 8 + lueur * 110; p[2] = 12 + lueur * 140;
        if (Y < bord + 1) { p[0] += 14; p[1] += 18; p[2] += 26; }   // le rebord, qui accroche la lumiere
      }
    }
  pointer(59, 13, 120, 230, 255);
  pointer(59, 19, 120, 230, 255);
  pointer(60, 36, 255, 170, 80);
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

// --- 7. les montagnes en « voxel space » ------------------------------------------------------
// Une carte des hauteurs et une carte de l'eclairage (le soleil couchant, ombres portees comprises),
// faites a la premiere image : 128 x 128 cases de 2 unites (la periode de 256 du numpy), le relief tire
// comme en numpy (un spectre en 1/k^2 sans les plus grandes ondes, ici une transformee de Fourier
// creuse), puis deux cartes adoucies pour le lointain. Pour chaque colonne on lit le terrain de pres
// vers le loin ; une demi-ligne montre le premier relief qui monte jusqu'a elle ; la brume prend la
// couleur du ciel.

const int V3_VX_K = 120;                // les distances lues par colonne : 1,2 x 1,042^k
const float V3_VX_F = 40, V3_VX_SOLEIL = 2.6f, V3_VX_EAU = 4.0f;
const int V3_VX_NF = 1700;              // les frequences gardees (|i, j| <= 32)

struct E_voxel {
  union {
    float hf[128 * 128];                // a la premiere image : le relief en flottants
    struct { uint16_t h[128 * 128]; uint8_t s[128 * 128], p[128 * 128]; } n;   // hauteur (0-50), soleil, pente
  } c0;
  union {
    struct {
      uint16_t h1[64 * 64]; uint8_t s1[64 * 64], p1[64 * 64], l1[64 * 64];      // adoucie une fois (cases de 4)
      uint16_t h2[32 * 32]; uint8_t s2[32 * 32], p2[32 * 32], l2[32 * 32];      // deux fois (cases de 8)
    } m;
    struct { float cr[V3_VX_NF], ci[V3_VX_NF]; int8_t i[V3_VX_NF], j[V3_VX_NF]; } dft;
  } c1;
  float Z[V3_VX_K], voile[V3_VX_K], lev[V3_VX_K];
  float x0, y0, ph, hmax;
  uint16_t h_eau;
};

struct V3Terrain { float h, s, p, lac; };
// lit le terrain en (u, v) (en cases du niveau 0) au niveau de douceur lev (0-2) : bilineaire, raccorde
inline void v3_vx_lire_niveau(const E_voxel &e, int niv, float u, float v, V3Terrain &o, bool tout) {
  const int n = 128 >> niv, m = n - 1;
  if (niv) { const float sc = 1.0f / (1 << niv), dec = (niv == 1 ? 0.5f : 1.5f); u = (u - dec) * sc; v = (v - dec) * sc; }
  const int iu = (int)u, iv = (int)v;   // u, v > 0 (decales de 256 cases) : la troncature est le plancher
  const float fu = u - iu, fv = v - iv;
  const int x0 = iu & m, y0 = iv & m, x1 = (x0 + 1) & m, y1 = (y0 + 1) & m;
  const int i00 = y0 * n + x0, i01 = y0 * n + x1, i10 = y1 * n + x0, i11 = y1 * n + x1;
  const float w00 = (1 - fu) * (1 - fv), w01 = fu * (1 - fv), w10 = (1 - fu) * fv, w11 = fu * fv;
  const uint16_t *H = niv == 0 ? e.c0.n.h : niv == 1 ? e.c1.m.h1 : e.c1.m.h2;
  o.h = (H[i00] * w00 + H[i01] * w01 + H[i10] * w10 + H[i11] * w11) * (50.0f / 65535);
  if (!tout) return;
  const uint8_t *S = niv == 0 ? e.c0.n.s : niv == 1 ? e.c1.m.s1 : e.c1.m.s2;
  const uint8_t *P = niv == 0 ? e.c0.n.p : niv == 1 ? e.c1.m.p1 : e.c1.m.p2;
  o.s = (S[i00] * w00 + S[i01] * w01 + S[i10] * w10 + S[i11] * w11) * (1.0f / 255);
  o.p = (P[i00] * w00 + P[i01] * w01 + P[i10] * w10 + P[i11] * w11) * (1.0f / 255);
  if (niv == 0) {
    const uint16_t q = e.h_eau;
    o.lac = (H[i00] <= q ? w00 : 0) + (H[i01] <= q ? w01 : 0) + (H[i10] <= q ? w10 : 0) + (H[i11] <= q ? w11 : 0);
  } else {
    const uint8_t *L = niv == 1 ? e.c1.m.l1 : e.c1.m.l2;
    o.lac = (L[i00] * w00 + L[i01] * w01 + L[i10] * w10 + L[i11] * w11) * (1.0f / 255);
  }
}
inline void v3_vx_lire(const E_voxel &e, float lev, float u, float v, V3Terrain &o, bool tout) {
  const int l0 = min(1, (int)lev);
  const float fl = lev - l0;
  v3_vx_lire_niveau(e, l0, u, v, o, tout);
  if (fl <= 0.001f) return;
  V3Terrain b;
  v3_vx_lire_niveau(e, l0 + 1, u, v, b, tout);
  o.h += (b.h - o.h) * fl;
  if (tout) { o.s += (b.s - o.s) * fl; o.p += (b.p - o.p) * fl; o.lac += (b.lac - o.lac) * fl; }
}
// la couleur du terrain : l'albedo (herbe, roche dans les pentes, neige en haut) sous le soleil et le ciel
inline void v3_vx_couleur(const V3Terrain &t, float *c) {
  const float hn = t.h * (1.0f / 50), p = t.p;
  const float neige = v3_01((hn - 0.58f) / 0.12f) * (1 - p * 0.5f);
  const float amb = 0.55f + 0.45f * hn;
  const float a0 = (0.42f + 0.2f * p) * (1 - neige) + neige, a1 = (0.46f + 0.06f * p) * (1 - neige) + 0.95f * neige;
  const float a2 = (0.34f + 0.12f * p) * (1 - neige) + 0.98f * neige;
  c[0] = a0 * (t.s * 382.5f + 48 * amb); c[1] = a1 * (t.s * 240 + 48 * amb); c[2] = a2 * (t.s * 120 + 104 * amb);
  if (t.lac > 0) {   // les lacs : le ciel rose dedans
    c[0] += (150 - c[0]) * t.lac; c[1] += (80 - c[1]) * t.lac; c[2] += (95 - c[2]) * t.lac;
  }
}

void v3_vx_cartes(E_voxel &e) {
  // le relief : des ondes de frequence (i, j) (en tours par 256 unites), d'amplitude 1/k^2 sans les plus grandes
  int nf = 0;
  for (int i = 0; i <= 32; i++)
    for (int j = -32; j <= 32; j++) {
      if ((i == 0 && j <= 0) || i * i + j * j > 32 * 32 || nf >= V3_VX_NF) continue;
      const float k = sqrtf((float)(i * i + j * j)) / 256, q = k / 0.016f;
      const float a = sqrtf(-2 * logf(hasard(1e-7f, 1))) / (k * k) * (1 - expf(-q * q)), ph = hasard(0, 2 * V3_PI);
      e.c1.dft.cr[nf] = a * cosf(ph); e.c1.dft.ci[nf] = a * sinf(ph); e.c1.dft.i[nf] = i; e.c1.dft.j[nf] = j;
      nf++;
    }
  float cs[128], sn[128];
  for (int n = 0; n < 128; n++) { cs[n] = cosf(2 * V3_PI * n / 128); sn[n] = sinf(2 * V3_PI * n / 128); }
  float mn = 1e30f, mx = -1e30f;
  for (int y = 0; y < 128; y++) {
    float Cr[33], Ci[33];   // ligne par ligne : la somme sur j, puis sur i le long de la ligne
    for (int i = 0; i < 33; i++) Cr[i] = Ci[i] = 0;
    for (int f = 0; f < nf; f++) {
      const int a = (e.c1.dft.j[f] * y) & 127, i = e.c1.dft.i[f];
      Cr[i] += e.c1.dft.cr[f] * cs[a] - e.c1.dft.ci[f] * sn[a];
      Ci[i] += e.c1.dft.cr[f] * sn[a] + e.c1.dft.ci[f] * cs[a];
    }
    for (int x = 0; x < 128; x++) {
      float h = 0;
      for (int i = 0, a = 0; i < 33; i++, a = (a + x) & 127) h += Cr[i] * cs[a] - Ci[i] * sn[a];
      e.c0.hf[y * 128 + x] = h;
      mn = fminf(mn, h); mx = fmaxf(mx, h);
    }
  }
  // des sommets, des vallees ; les lacs au fond (en uint16, sur 50)
  const float ech = 1.0f / fmaxf(mx - mn, 1e-9f);
  for (int i = 0; i < 128 * 128; i++) {
    const float n = (e.c0.hf[i] - mn) * ech, h = fmaxf(n > 0 ? expf(1.6f * logf(n)) * 50 : 0, V3_VX_EAU);
    e.c0.n.h[i] = (uint16_t)(h * (65535 / 50.0f) + 0.5f);
  }
  e.h_eau = (uint16_t)(V3_VX_EAU * (65535 / 50.0f) + 0.5f);
  uint16_t hm = 0;
  for (int i = 0; i < 128 * 128; i++) hm = max(hm, e.c0.n.h[i]);
  e.hmax = hm * (50.0f / 65535);
  // l'eclairage : le soleil bas, a l'azimut 2,6 ; une ombre portee le long de ses rayons
  const float sxs = cosf(V3_VX_SOLEIL), sys = sinf(V3_VX_SOLEIL), elev = 0.16f, ce = cosf(elev), se = sinf(elev), te = tanf(elev);
  const uint16_t *H = e.c0.n.h;
  const float u = 50.0f / 65535;
  int8_t ox[20], oy[20];
  for (int k = 0; k < 20; k++) { const float d = 1 + 2 * k; ox[k] = (int8_t)rintf(d * sxs / 2); oy[k] = (int8_t)rintf(d * sys / 2); }
  for (int y = 0; y < 128; y++)
    for (int x = 0; x < 128; x++) {
      const float h = H[y * 128 + x] * u;
      const float gx = (H[y * 128 + ((x + 1) & 127)] - H[y * 128 + ((x + 127) & 127)]) * u / 4;
      const float gy = (H[((y + 1) & 127) * 128 + x] - H[((y + 127) & 127) * 128 + x]) * u / 4;
      const float nz = 1 / sqrtf(gx * gx + gy * gy + 1);
      const float lambert = v3_01((-gx * sxs - gy * sys) * nz * ce + nz * se);
      float ombre = 0;
      for (int k = 0; k < 20 && ombre < 1; k++) {
        const float dec = H[((y + oy[k]) & 127) * 128 + ((x + ox[k]) & 127)] * u;
        ombre = fmaxf(ombre, v3_01((dec - h - (1 + 2 * k) * te) / 3));
      }
      e.c0.n.s[y * 128 + x] = (uint8_t)(lambert * (1 - ombre) * 255 + 0.5f);
      e.c0.n.p[y * 128 + x] = (uint8_t)(v3_01(sqrtf(gx * gx + gy * gy) / 2.5f) * 255 + 0.5f);
    }
  // les cartes adoucies : chaque case, la moyenne des quatre du dessous
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int a = (2 * y) * 128 + 2 * x, b = a + 1, c = a + 128, d = a + 129, i = y * 64 + x;
      e.c1.m.h1[i] = (uint16_t)((H[a] + H[b] + H[c] + H[d] + 2) >> 2);
      e.c1.m.s1[i] = (uint8_t)((e.c0.n.s[a] + e.c0.n.s[b] + e.c0.n.s[c] + e.c0.n.s[d] + 2) >> 2);
      e.c1.m.p1[i] = (uint8_t)((e.c0.n.p[a] + e.c0.n.p[b] + e.c0.n.p[c] + e.c0.n.p[d] + 2) >> 2);
      e.c1.m.l1[i] = (uint8_t)(((H[a] <= e.h_eau) + (H[b] <= e.h_eau) + (H[c] <= e.h_eau) + (H[d] <= e.h_eau)) * 255 / 4);
    }
  for (int y = 0; y < 32; y++)
    for (int x = 0; x < 32; x++) {
      const int a = (2 * y) * 64 + 2 * x, b = a + 1, c = a + 64, d = a + 65, i = y * 32 + x;
      e.c1.m.h2[i] = (uint16_t)((e.c1.m.h1[a] + e.c1.m.h1[b] + e.c1.m.h1[c] + e.c1.m.h1[d] + 2) >> 2);
      e.c1.m.s2[i] = (uint8_t)((e.c1.m.s1[a] + e.c1.m.s1[b] + e.c1.m.s1[c] + e.c1.m.s1[d] + 2) >> 2);
      e.c1.m.p2[i] = (uint8_t)((e.c1.m.p1[a] + e.c1.m.p1[b] + e.c1.m.p1[c] + e.c1.m.p1[d] + 2) >> 2);
      e.c1.m.l2[i] = (uint8_t)((e.c1.m.l1[a] + e.c1.m.l1[b] + e.c1.m.l1[c] + e.c1.m.l1[d] + 2) >> 2);
    }
}

void s_voxel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voxel &e = etat_ecran<E_voxel>(debut);
  (void)humeur; (void)t; (void)dt;
  const float F = V3_VX_F;
  if (debut) {
    v3_vx_cartes(e);
    e.x0 = hasard(0, 256); e.y0 = hasard(0, 256); e.ph = hasard(0, 100);
    float z = 1.2f;
    for (int k = 0; k < V3_VX_K; k++, z *= 1.042f) {
      e.Z[k] = z;
      e.voile[k] = expf(1.3f * logf(1 - expf(-z / 190.0f)));
      e.lev[k] = z * 0.055f > 1 ? fminf(1.999f, fmaxf(0.0f, log2f(z * 0.055f) - 2)) : 0;   // la douceur, selon la distance
    }
  }
  const float tau = ecoule + e.ph, cap0 = V3_VX_SOLEIL - 0.95f;   // le soleil sur le cote : il dore les pentes
  const float ux = cosf(cap0), uy = sinf(cap0), wx = -uy, wy = ux, v = 7.0f;
  const float lat = 40 * sinf(tau * 0.045f) + 7 * sinf(tau * 0.12f), dlat = 40 * 0.045f * cosf(tau * 0.045f) + 7 * 0.12f * cosf(tau * 0.12f);
  // (ramenee dans la carte, qui se raccorde tous les 256 : les flottants restent precis)
  const float cx = v3_fmod(e.x0 + ux * v * tau + wx * lat, 256), cy = v3_fmod(e.y0 + uy * v * tau + wy * lat, 256);
  const float cap = cap0 + atan2f(dlat, v), fx = cosf(cap), fy = sinf(cap);
  float haut = -1e9f;   // on suit le relief, en voyant venir les cretes
  static const float dd[5] = {0, 10, 20, 32, 45};
  for (int i = 0; i < 5; i++) {
    V3Terrain o;
    v3_vx_lire(e, 1.5f, (cx + fx * dd[i]) * 0.5f + 256, (cy + fy * dd[i]) * 0.5f + 256, o, false);
    haut = fmaxf(haut, o.h - dd[i] * 0.1f);
  }
  haut += 12.0f;
  const float hz = 21.0f + 1.5f * sinf(tau * 0.07f);
  // le ciel : du violet au rose, orange vers le soleil ; il ne depend que de la demi-ligne et de la colonne
  float kc3[128], kcm[128], kc[128], nuage_el[128];
  for (int r = 0; r < 128; r++) {
    const float el = (hz - (r + 0.5f) * 0.5f) / F, k = v3_01(el / 0.55f), q = 1 - k;
    kc[r] = k; kc3[r] = q * q * q;
    kcm[r] = fmaxf(0.0f, (q > 0 ? expf(1.2f * logf(q)) : 0) - kc3[r]) * 1.3f;
    const float b = (el - 0.12f) / 0.06f;
    nuage_el[r] = b * b < 16 ? expf(-b * b) * 1.6f * 0.5f : 0;
  }
  const bool soleil_vu = fabsf(V3_VX_SOLEIL - cap) < 1.2f;
  const float soleil_x = 31.5f + tanf(V3_VX_SOLEIL - cap) * F, soleil_y = hz - 0.07f * F;
  float nb_s[128], nb_c[128], nc_s[128], nc_c[128];   // les nuages : sin(a + b) = sin a cos b + cos a sin b
  for (int r = 0; r < 128; r++) {
    if (nuage_el[r] <= 0) continue;
    const float el = (hz - (r + 0.5f) * 0.5f) / F;
    nb_s[r] = v3_sin(el * 4); nb_c[r] = v3_cos(el * 4); nc_s[r] = v3_sin(el * 60); nc_c[r] = v3_cos(el * 60);
  }
  for (int col = 0; col < 64; col++) {
    const float sx = (col - 31.5f) / F, az = cap + atanf(sx);
    const float na = az * 9 + v3_sin(az * 3) * 2, na_s = v3_sin(na), na_c = v3_cos(na), nd_s = v3_sin(az * 4), nd_c = v3_cos(az * 4);
    const float vs0 = v3_01(cosf(az - V3_VX_SOLEIL)), vs = vs0 * vs0 * vs0;
    const float brume[3] = {200 * (0.45f + 0.55f * vs) + 20, 120 * (0.45f + 0.55f * vs) + 10, 100 * (0.45f + 0.55f * vs) + 30};
    // les rayons, de pres vers le loin : la premiere demi-ligne que chaque relief atteint
    const float dx = fx - fy * sx, dy = fy + fx * sx;
    uint8_t quelle[128];
    int cur = 128;
    float m = 1e30f;
    const float u0 = cx * 0.5f + 256, v0 = cy * 0.5f + 256, du = dx * 0.5f, dv = dy * 0.5f;
    for (int k = 0; k < V3_VX_K && cur > 0; k++) {
      const float Z = e.Z[k];
      if (hz + (haut - e.hmax) * F / Z >= m) continue;   // meme le plus haut sommet ne monterait pas plus haut
      V3Terrain o;
      v3_vx_lire(e, e.lev[k], u0 + Z * du, v0 + Z * dv, o, false);
      m = v3_mn(m, hz + (haut - o.h) * F / Z);
      const float q = m * 2 - 0.5f;
      const int r = q <= 0 ? 0 : q >= 128 ? 128 : (int)q + ((float)(int)q < q ? 1 : 0);   // ceil, borne a 0-128
      while (cur > r) quelle[--cur] = (uint8_t)k;
    }
    float img2[2][3];
    int dernier = -1;
    float terrain[3] = {0, 0, 0};
    for (int r = 127; r >= 0; r--) {
      float *c = img2[r & 1];
      if (r >= cur) {
        const int k = quelle[r];
        if (k != dernier) {
          dernier = k;
          const float Z = e.Z[k];
          V3Terrain o;
          v3_vx_lire(e, e.lev[k], u0 + Z * du, v0 + Z * dv, o, true);
          float coul[3];
          v3_vx_couleur(o, coul);
          const float w = e.voile[k];
          for (int q = 0; q < 3; q++) terrain[q] = coul[q] * (1 - w) + brume[q] * w;
        }
        c[0] = terrain[0]; c[1] = terrain[1]; c[2] = terrain[2];
      } else {
        const float a = kc3[r] * (0.55f + 0.45f * vs), b = kcm[r], k = kc[r];
        c[0] = 255 * a + 150 * b + 22 * k; c[1] = 140 * a + 70 * b + 22 * k; c[2] = 70 * a + 110 * b + 62 * k;
        if (soleil_vu) {
          const float ddx = col + 0.5f - soleil_x, ddy = (r + 0.5f) * 0.5f - soleil_y, d = sqrtf(ddx * ddx + ddy * ddy);
          const float disque = v3_01(3.2f - d), g = v3_exp(-d / 7.0f);
          c[0] += disque * 255 + g * 120; c[1] += disque * 230 + g * 60; c[2] += disque * 170 + g * 25;
        }
        if (nuage_el[r] > 0) {
          const float n = 0.5f + 0.5f * (na_s * nb_c[r] + na_c * nb_s[r]) * (nc_s[r] * nd_c + nc_c[r] * nd_s);
          if (n > 0.55f) {
            const float k2 = (n - 0.55f) * nuage_el[r];
            c[0] += k2 * 255; c[1] += k2 * 120; c[2] += k2 * 110;
          }
        }
      }
      if (!(r & 1)) for (int q = 0; q < 3; q++) scene[r >> 1][col][q] = (img2[0][q] + img2[1][q]) * 0.5f;
    }
  }
}

// --- 8. l'ocean au clair de lune -----------------------------------------------------------
// Chaque pixel sous l'horizon voit un point de la mer, une somme de dix vagues (leur pente donne la
// normale) ; on renvoie le ciel dans la direction du reflet, et la lune quand il la vise. Au loin, les
// vagues trop petites pour un pixel sont retirees et leur pente passe dans le flou du reflet. Le long
// d'une ligne, la phase d'une vague avance d'un pas fixe : on la tourne au lieu d'appeler cosf.

struct E_ocean {
  float kx[10], kz[10], amp[10], om[10], ph[10];
  float ep[50], el[50];
  float halo[257][2];   // le halo de la lune selon l'ecart angulaire d (0 a 0,9 rad) : les deux exponentielles
  float expn[513];      // exp(-x), x de 0 a 32
  uint8_t ey[50], ex[50];
};

// le ciel de l'ocean dans une direction (azimut, hauteur), en radians
inline void v3_ocean_ciel(const E_ocean &e, float az, float el, float *c) {
  const float k = v3_01(el * 2), a = (1 - k) * (1 - k);
  c[0] = 5 + 25 * a; c[1] = 7 + 33 * a; c[2] = 20 + 52 * a;
  const float da = az - 0.13f, de = el - 0.24f, d2 = da * da + de * de;
  if (d2 < 0.81f) {                                           // au-dela, le halo ne compte plus
    const float f = sqrtf(d2) * (256 / 0.9f);
    const int i = min(255, (int)f);
    const float q = f - i, h = e.halo[i][0] + (e.halo[i + 1][0] - e.halo[i][0]) * q;
    const float l = e.halo[i][1] + (e.halo[i + 1][1] - e.halo[i][1]) * q;
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
    for (int i = 0; i <= 256; i++) {
      const float d = i * (0.9f / 256);
      e.halo[i][0] = expf(-d / 0.12f); e.halo[i][1] = expf(-d / 0.035f) * 40;
    }
    for (int i = 0; i <= 512; i++) e.expn[i] = expf(-i / 16.0f);
  }
  const float cy = 3.0f + 0.12f * sinf(t * 0.37f), hz = 25.0f + 0.5f * sinf(t * 0.29f);
  // le ciel : bleu nuit, plus clair vers l'horizon ; la lune et son halo
  const int y_mer = max(0, (int)floorf(hz - 1) + 1);       // la premiere ligne ou la mer se voit
  for (int x = 0; x < 64; x++) {
    const float dx = (x + 0.5f - 32) / F, az = v3_atan(dx), hc = 1.0f / sqrtf(dx * dx + 1);
    for (int y = 0; y < min(64, (int)hz + 1); y++) {
      const float el = v3_atan(-(y + 0.5f - hz) / F * hc);
      v3_ocean_ciel(e, az, el, scene[y][x]);
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
    float akx[10], akz[10], co[10], si[10], cd[10], sd[10], var_x = 0, var_z = 0;
    int na = 0;
    for (int i = 0; i < 10; i++) {
      const float alias = (fabsf(e.kx[i]) * pied_x + fabsf(e.kz[i]) * pied_z) / 2.2f;
      const float garde = alias < 5 ? expf(-alias * alias) : 0;
      const float perdu = e.amp[i] * e.amp[i] * 0.5f * (1 - garde * garde);
      var_x += perdu * e.kx[i] * e.kx[i];
      var_z += perdu * e.kz[i] * e.kz[i];
      const float a = e.amp[i] * garde;
      if (a * (fabsf(e.kx[i]) + fabsf(e.kz[i])) < 2e-3f) continue;   // une pente de 0,002 : rien a l'ecran
      const float pas = e.kx[i] * s / F;
      const float p0 = e.kx[i] * (0.5f - 32) * s / F + e.kz[i] * s - e.om[i] * t + e.ph[i];
      akx[na] = a * e.kx[i]; akz[na] = a * e.kz[i];
      co[na] = cosf(p0); si[na] = sinf(p0); cd[na] = cosf(pas); sd[na] = sinf(pas);
      na++;
    }
    const float sa = 0.0011f + 4 * var_x, se = 0.0045f + 4 * var_z;
    const float norme = expf(0.22f * logf(0.0011f * 0.0045f / (sa * se))), i2sa = 0.5f / sa, i2se = 0.5f / se;
    const float ge = 4.5f * pied_z / 2.2f, garde_e = ge < 4 ? expf(-ge * ge) : 0;   // des eclats qui courent en travers
    for (int x = 0; x < 64; x++) {
      const float sx = x + 0.5f - 32;
      float dhx = 0, dhz = 0;
      for (int j = 0; j < na; j++) {
        const float c = co[j], sn = si[j];
        dhx += c * akx[j];
        dhz += c * akz[j];
        co[j] = c * cd[j] - sn * sd[j];
        si[j] = sn * cd[j] + c * sd[j];
      }
      const float inv = 1.0f / sqrtf(dhx * dhx + 1 + dhz * dhz);
      const float nx = -dhx * inv, ny = inv, nz = -dhz * inv;
      const float il = 1.0f / sqrtf(sx * sx + sy * sy + F * F);
      const float vx = sx * il, vy = -sy * il, vz = F * il;
      const float dn = vx * nx + vy * ny + vz * nz;
      const float rx = vx - 2 * dn * nx, ry = fabsf(vy - 2 * dn * ny), rz = vz - 2 * dn * nz;
      const float q = v3_01(1 + dn), q2 = q * q, fres = 0.02f + 0.98f * q2 * q2 * q;
      // le rayon est unitaire : sa hauteur est asin(ry) (un polynome tant qu'il reste bas)
      const float az = rz > fabsf(rx) ? v3_atan(rx / rz) : v3_atan2(rx, rz);
      const float r2 = ry * ry;
      const float el = ry < 0.5f ? ry * (1 + r2 * (0.16666667f + r2 * (0.075f + r2 * (0.044642857f + r2 * 0.030381944f))))
                                 : v3_atan2(ry, sqrtf(rx * rx + rz * rz));
      float ciel[3];
      v3_ocean_ciel(e, az, el, ciel);
      const float da = az - ma, de = el - mh, ex = da * da * i2sa + de * de * i2se;
      float eclat = ex < 30 ? v3_lire(e.expn, ex, 16, 512) * norme : 0;
      if (eclat > 1e-4f && garde_e > 1e-3f) {
        const float gx = sx * s / F;
        eclat *= 1 + 0.9f * garde_e * v3_sin(s * 4.5f - t * 1.7f + 2 * v3_sin(gx * 1.3f + t * 0.6f));
      }
      const float dos = v3_01(-dhz * 3) * 6;   // les dos des vagues, un rien plus clairs
      const float eau[3] = {3 * (1 - fres) + ciel[0] * fres * 0.7f + eclat * 255 * 1.6f + dos * 0.4f,
                            7 * (1 - fres) + ciel[1] * fres * 0.7f + eclat * 240 * 1.6f + dos * 0.7f,
                            18 * (1 - fres) + ciel[2] * fres * 0.7f + eclat * 205 * 1.6f + dos};
      float *p = scene[y][x];
      if (couv >= 1) { p[0] = eau[0]; p[1] = eau[1]; p[2] = eau[2]; }
      else for (int c = 0; c < 3; c++) p[c] = p[c] * (1 - couv) + eau[c] * couv;
    }
  }
}
