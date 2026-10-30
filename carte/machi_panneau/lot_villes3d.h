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
  float halo[257][2];   // le halo de la lune selon l'ecart angulaire d (0 a 0,9 rad) : les deux exponentielles
  float expn[513];      // exp(-x), x de 0 a 32
  uint8_t ey[50], ex[50];
};

// une table lue en interpolant (x * echelle entre 0 et n)
inline float v3_lire(const float *tab, float x, float echelle, int n) {
  const float f = x * echelle;
  if (f >= n) return tab[n];
  const int i = (int)f;
  return tab[i] + (tab[i + 1] - tab[i]) * (f - i);
}

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
