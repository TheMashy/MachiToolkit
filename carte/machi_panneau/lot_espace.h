// lot_espace.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
// L'espace : la planete a anneaux, le trou noir et son disque, la galaxie spirale, et les huit
// scenes de « L'ESPACE, EN GRAND » -- le trou noir et ses centaines de particules en vraie
// gravitation, deux galaxies qui se croisent, la Voie lactee sur son arbre, l'eclipse, le soleil
// de pres, la comete, la Terre vue d'orbite, les constellations. Chacun suit son jumeau numpy ; ce
// qui ne bouge pas est precalcule au debut, et les exp/sin des boucles par pixel sont les versions
// rapides du lot (spa_exp, spa_sin : justes a quelques 1e-6 pres, sans libm).
#pragma once

// ===== les outils du lot =====================================================================

const float SPA_PI = 3.14159265f;

inline int spa_plancher(float x) {
  const int i = (int)x;
  return x < (float)i ? i - 1 : i;
}
// le % de Python (m > 0) : toujours entre 0 et m
inline float spa_mod(float a, float m) { return a - m * (float)spa_plancher(a / m); }
// un angle ramene dans [-pi, pi), comme (d + pi) % 2pi - pi
inline float spa_enroule(float d) { return spa_mod(d + SPA_PI, 2 * SPA_PI) - SPA_PI; }

// exp(x), rapide : 2^i par l'exposant, e^f (|f| <= 0.35) par son developpement
inline float spa_exp(float x) {
  if (x < -87.0f) return 0.0f;
  if (x > 87.0f) x = 87.0f;
  const float z = x * 1.44269504f;
  const int i = spa_plancher(z + 0.5f);
  const float f = (z - (float)i) * 0.69314718f;
  const float p = 1.0f + f * (1.0f + f * (0.5f + f * (0.16666667f + f * (0.041666668f + f * 0.0083333338f))));
  int32_t bits;
  memcpy(&bits, &p, 4);
  bits += i * 8388608;
  float r;
  memcpy(&r, &bits, 4);
  return r;
}

// sin(x), rapide : ramene a un quart de tour, puis son developpement
inline float spa_sin(float x) {
  float q = x * 0.15915494f;
  q -= (float)spa_plancher(q + 0.5f);
  if (q > 0.25f) q = 0.5f - q;
  else if (q < -0.25f) q = -0.5f - q;
  const float a = q * 6.2831853f, a2 = a * a;
  return a * (1.0f + a2 * (-0.16666667f + a2 * (0.0083333333f + a2 * (-0.00019841270f + a2 * 2.7557319e-6f))));
}
inline float spa_cos(float x) { return spa_sin(x + 1.5707963f); }

// une loi normale (Box-Muller)
float spa_normale(float sigma) {
  const float u1 = 1.0f - hasard(0, 1), u2 = hasard(0, 1);
  return sigma * sqrtf(-2.0f * logf(u1)) * cosf(PI2 * u2);
}

// _espace_lire sur un champ d'octets (taille : une puissance de deux), qui se raccorde
inline float spa_lire8(const uint8_t *c, int taille, float u, float v) {
  const int m = taille - 1;
  const int u0 = spa_plancher(u), v0 = spa_plancher(v);
  const float fu = u - u0, fv = v - v0;
  const int i0 = u0 & m, i1 = (u0 + 1) & m, j0 = (v0 & m) * taille, j1 = ((v0 + 1) & m) * taille;
  const float a = c[j0 + i0], b = c[j0 + i1], d = c[j1 + i0], e = c[j1 + i1];
  const float haut = a + (b - a) * fu, bas = d + (e - d) * fu;
  return (haut + (bas - haut) * fv) * (1.0f / 255.0f);
}

// un ajout de lumiere dans la scene, hors champ ignore
inline void spa_ajout(int y, int x, float k, float r, float v, float b) {
  if ((unsigned)y < 64u && (unsigned)x < 64u) {
    float *p = scene[y][x];
    p[0] += k * r;
    p[1] += k * v;
    p[2] += k * b;
  }
}
// le « net » de _espace_tacher : 4 (f^4 / (f^4 + (1-f)^4)) ou 25 (l'exposant 2.5)
inline float spa_net(float f, int net) {
  const float g = 1 - f;
  float a, b;
  if (net == 4) {
    a = f * f; a *= a;
    b = g * g; b *= b;
  } else {
    a = f * f * sqrtf(f);
    b = g * g * sqrtf(g);
  }
  return a / (a + b);
}
// _espace_tacher : un point a une position pas forcement entiere, reparti sur ses quatre voisins
void spa_tacher(float y, float x, float r, float v, float b, int net = 1) {
  if (!(y > -1.0f && y < 64.0f && x > -1.0f && x < 64.0f)) return;
  const int x0 = spa_plancher(x), y0 = spa_plancher(y);
  float fx = x - x0, fy = y - y0;
  if (net != 1) { fx = spa_net(fx, net); fy = spa_net(fy, net); }
  spa_ajout(y0, x0, (1 - fx) * (1 - fy), r, v, b);
  spa_ajout(y0, x0 + 1, fx * (1 - fy), r, v, b);
  spa_ajout(y0 + 1, x0, (1 - fx) * fy, r, v, b);
  spa_ajout(y0 + 1, x0 + 1, fx * fy, r, v, b);
}

// _espace_etoiles : un fond d'etoiles de tailles et de couleurs variees, qui scintillent
const float SPA_TEINTES_ET[4][3] = {{200, 215, 255}, {235, 235, 245}, {255, 235, 200}, {255, 205, 160}};
template <int NE> struct SpaEtoiles { int n; uint8_t y[NE], x[NE], c[NE]; float l[NE], p[NE], w[NE]; };
template <int NE> void spa_semer_etoiles(SpaEtoiles<NE> &s, int haut = 0, int bas = 64) {
  s.n = NE;
  for (int i = 0; i < NE; i++) {
    s.y[i] = (uint8_t)(haut + (int)(aleatoire() % (uint32_t)(bas - haut)));
    s.x[i] = (uint8_t)(aleatoire() % 64);
    const float r = hasard(0, 1), q = hasard(0, 1);
    s.l[i] = 0.22f + 0.78f * r * r * sqrtf(r);
    s.c[i] = q < 0.35f ? 0 : q < 0.7f ? 1 : q < 0.88f ? 2 : 3;
    s.p[i] = hasard(0, PI2);
    s.w[i] = hasard(0.6f, 2.0f);
  }
}
template <int NE> void spa_etoiles(const SpaEtoiles<NE> &s, float t, float eclat, float scint) {
  for (int i = 0; i < s.n; i++) {
    const float k = s.l[i] * eclat * (1 - scint + scint * spa_sin(t * s.w[i] + s.p[i]));
    const float *c = SPA_TEINTES_ET[s.c[i]];
    pointer(s.y[i], s.x[i], k * c[0], k * c[1], k * c[2]);
  }
}

// _espace_flou deux fois (b = 0.4 a + 0.15 (ses quatre voisins), bords non raccordes), fait en
// place sur la scene, rangee par rangee : pour chaque pixel, faire(y, x, avant, flou) recoit la
// valeur d'origine et la valeur deux fois floue, et ecrit scene[y][x]
struct SpaFlou { float a[3][64][3], b[3][64][3]; };
inline void spa_flou_rangee(const float (*haut)[3], const float (*ici)[3], const float (*bas)[3], float (*sortie)[3]) {
  for (int x = 0; x < 64; x++)
    for (int c = 0; c < 3; c++) {
      float s = (x > 0 ? ici[x - 1][c] : 0.0f) + (x < 63 ? ici[x + 1][c] : 0.0f);
      if (haut) s += haut[x][c];
      if (bas) s += bas[x][c];
      sortie[x][c] = 0.4f * ici[x][c] + 0.15f * s;
    }
}
template <class F> void spa_flou2(SpaFlou &f, F faire) {
  memcpy(f.a[0], scene[0], sizeof f.a[0]);
  memcpy(f.a[1], scene[1], sizeof f.a[1]);
  spa_flou_rangee(nullptr, f.a[0], f.a[1], f.b[0]);
  for (int y = 0; y < 64; y++) {
    if (y + 2 < 64) memcpy(f.a[(y + 2) % 3], scene[y + 2], sizeof f.a[0]);
    if (y + 1 < 64) spa_flou_rangee(f.a[y % 3], f.a[(y + 1) % 3], y + 2 < 64 ? f.a[(y + 2) % 3] : nullptr, f.b[(y + 1) % 3]);
    const float (*avant)[3] = y > 0 ? f.b[(y + 2) % 3] : nullptr;
    const float (*ici)[3] = f.b[y % 3];
    const float (*apres)[3] = y < 63 ? f.b[(y + 1) % 3] : nullptr;
    for (int x = 0; x < 64; x++) {
      float flou[3];
      for (int c = 0; c < 3; c++) {
        float s = (x > 0 ? ici[x - 1][c] : 0.0f) + (x < 63 ? ici[x + 1][c] : 0.0f);
        if (avant) s += avant[x][c];
        if (apres) s += apres[x][c];
        flou[c] = 0.4f * ici[x][c] + 0.15f * s;
      }
      faire(y, x, f.a[y % 3][x], flou);
    }
  }
}

// ===== la planete a anneaux (_scene_planete) ==================================================

const float SPA_PLANETE[2][4][3] = {{{235, 210, 160}, {180, 140, 90}, {210, 190, 150}, {2, 2, 8}},
                                    {{200, 235, 255}, {90, 140, 200}, {170, 210, 240}, {2, 4, 12}}};
const int SPA_PL_MAX = 800;

// humeurs : 0 = saturne, 1 = glace
struct E_planete {
  uint8_t fond[4096][3];     // le ciel et les anneaux, qui ne bougent pas (tronques, comme l'image numpy)
  uint8_t ciel_ici[4096];    // 1 : du ciel, ou les etoiles se voient
  int n;                     // le disque : ses pixels, et ce qui n'y depend pas du temps
  uint16_t ou[SPA_PL_MAX];
  float a[SPA_PL_MAX], lon3[SPA_PL_MAX], lum[SPA_PL_MAX];
};
void s_planete(int humeur, bool debut, float t, float ecoule, float dt) {
  E_planete &e = etat_ecran<E_planete>(debut);
  (void)ecoule; (void)dt;
  const float (*hu)[3] = SPA_PLANETE[humeur ? 1 : 0];
  const float cx = 34, cy = 34, R = 15, inc = 0.28f, tilt = -0.35f;
  const float ct = cosf(tilt), st = sinf(tilt);
  if (debut) {
    semer_ciel(60, 64);
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const int i = y * 64 + x;
        const float dx = x - cx, dy = y - cy;
        const float ax = dx * ct + dy * st, ay = (-dx * st + dy * ct) / inc;   // dans le repere des anneaux
        const float ra = sqrtf(ax * ax + ay * ay) / R;
        const bool bandes = ra > 1.25f && ra < 2.05f, devant = ay > 0;
        float rayure = 0.6f + 0.25f * sinf(ra * 38) + 0.15f * sinf(ra * 91);
        if (ra > 1.62f && ra < 1.68f) rayure *= 0.15f;                        // la division
        const float d = sqrtf(dx * dx + dy * dy) / R;
        const bool disque = d <= 1;
        float k = 0;
        int genre = 0;
        if (bandes && !devant && !disque) { k = rayure * 0.85f; genre = 1; }
        if (disque) genre = 2;
        if (bandes && devant) {                                                 // la planete fait de l'ombre aux anneaux
          const bool ombre = ax < 0 && fabsf(ay * inc) < R * 0.9f && ra < 1.7f;
          k = rayure * (ombre ? 0.4f : 1.0f);
          genre = 1;
        }
        for (int j = 0; j < 3; j++) e.fond[i][j] = (uint8_t)borne(genre == 1 ? k * hu[2][j] : hu[3][j], 0, 255);
        e.ciel_ici[i] = genre == 0;
        if (genre == 2 && e.n < SPA_PL_MAX) {
          const float nz = sqrtf(borne(1 - d * d, 0, 1));
          const float lat = (-dx * st + dy * ct) / R;                          // les bandes suivent l'equateur des anneaux
          const float lon = atan2f((dx * ct + dy * st) / R, nz + 1e-6f);
          const float lu = borne(0.15f + 0.9f * (-dx * 0.6f - dy * 0.35f + nz * 0.7f * R) / R, 0.05f, 1.1f);
          const float ombre = borne(1 - fabsf(lat + 0.12f) * 14, 0, 1) * 0.5f;   // l'ombre des anneaux
          e.ou[e.n] = (uint16_t)i;
          e.a[e.n] = lat * 11 + 0.3f * sinf(lat * 29);
          e.lon3[e.n] = lon * 3;
          e.lum[e.n] = lu * (1 - ombre);
          e.n++;
        }
      }
  }
  for (int i = 0; i < 4096; i++) peindre(i >> 6, i & 63, e.fond[i][0], e.fond[i][1], e.fond[i][2]);
  for (int k = 0; k < ciel.n; k++) {
    if (!e.ciel_ici[ciel.y[k] * 64 + ciel.x[k]]) continue;
    const float l = ciel.l[k] * (0.55f + 0.45f * spa_sin(t * 2.1f + ciel.p[k]));
    pointer(ciel.y[k], ciel.x[k], 205 * l, 210 * l, 235 * l);
  }
  const float *claire = hu[0], *sombre = hu[1], tb = t * 0.15f;
  for (int j = 0; j < e.n; j++) {                                               // ses bandes tournent
    const float b = 0.5f + 0.5f * spa_sin(e.a[j] + 0.6f * spa_sin(e.lon3[j] - tb)), l = e.lum[j];
    const int i = e.ou[j];
    peindre(i >> 6, i & 63, (sombre[0] + (claire[0] - sombre[0]) * b) * l, (sombre[1] + (claire[1] - sombre[1]) * b) * l,
            (sombre[2] + (claire[2] - sombre[2]) * b) * l);
  }
  const float a = t * 0.11f, ca = cosf(a), sa = sinf(a);                      // une lune sur son orbite
  const float mx = cx + ca * 27 * ct - sa * 27 * inc * st, my = cy + ca * 27 * st + sa * 27 * inc * ct;
  if (sa > 0 || hypotf(mx - cx, my - cy) > R + 2)
    for (int y = (int)my - 2; y <= (int)my + 2; y++)
      for (int x = (int)mx - 2; x <= (int)mx + 2; x++) {
        if (y < 0 || y >= 64 || x < 0 || x >= 64 || hypotf(x - mx, y - my) > 1.8f) continue;
        const float k = x < mx ? 1.0f : 0.6f;
        peindre(y, x, 200 * k, 200 * k, 205 * k);
      }
}

// ===== le trou noir et son disque (_scene_trou_noir) ==========================================

const float SPA_TROU[2][3][3] = {{{255, 245, 210}, {255, 170, 70}, {150, 50, 10}},
                                 {{230, 245, 255}, {110, 160, 255}, {40, 30, 140}}};   // le plus chaud, le disque, le bord
const int SPA_TN_D = 700, SPA_TN_A = 500;

inline void spa_tn_teinte(float k, const float (*h)[3], float *o) {
  k = borne(k, 0, 1.3f);
  if (k > 0.6f) {
    const float q = borne((k - 0.6f) / 0.6f, 0, 1);
    for (int c = 0; c < 3; c++) o[c] = h[1][c] + (h[0][c] - h[1][c]) * q;
  } else {
    const float q = k / 0.6f;
    for (int c = 0; c < 3; c++) o[c] = h[2][c] + (h[1][c] - h[2][c]) * q;
  }
}

// humeurs : 0 = or, 1 = bleu
struct E_trou_noir {
  float ey[70], ex[70], ep[70], el[70];   // les etoiles, deviees pres du trou
  float photon[4096];                     // l'anneau de photons (il ne bouge pas)
  int nd, milieu, na;                     // le disque (derriere, puis devant a partir de `milieu`), l'anneau courbe
  uint16_t di[SPA_TN_D];
  float dth[SPA_TN_D], dw[SPA_TN_D], drd[SPA_TN_D], dk[SPA_TN_D];
  uint16_t ai[SPA_TN_A];
  float a4[SPA_TN_A], ak[SPA_TN_A];
};
void s_trou_noir(int humeur, bool debut, float t, float ecoule, float dt) {
  E_trou_noir &e = etat_ecran<E_trou_noir>(debut);
  (void)ecoule; (void)dt;
  const float (*hu)[3] = SPA_TROU[humeur ? 1 : 0];
  const float cx = 32, cy = 32, ombre = 7.5f, plat = 0.2f;
  if (debut) {
    for (int k = 0; k < 70; k++) {
      const float y = (float)(aleatoire() % 64), x = (float)(aleatoire() % 64);
      e.ep[k] = hasard(0, PI2);
      e.el[k] = hasard(0.3f, 1.0f);
      const float vx = x - cx, vy = y - cy, rr = sqrtf(vx * vx + vy * vy) + 1e-6f;
      const float pousse = 1 + 40 / (rr * rr + 4);
      e.ey[k] = cy + vy * pousse;
      e.ex[k] = cx + vx * pousse;
    }
    e.milieu = -1;
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const int i = y * 64 + x;
        const float dx = x - cx, dy = y - cy, r = sqrtf(dx * dx + dy * dy);
        const float rd = sqrtf(dx * dx + (dy / plat) * (dy / plat));        // le disque, vu presque par la tranche
        e.photon[i] = r > ombre ? expf(-fabsf(r - ombre - 0.6f) * 2.2f) * 0.8f : 0.0f;
        if (rd > 9 && rd < 29 && (dy >= 0 || r > ombre) && e.nd < SPA_TN_D) {
          if (dy >= 0 && e.milieu < 0) e.milieu = e.nd;
          const float th = atan2f(dy / plat, dx);
          e.di[e.nd] = (uint16_t)i;
          e.dth[e.nd] = th;
          e.dw[e.nd] = 18 / (rd + 6);                                          // le centre tourne plus vite
          e.drd[e.nd] = rd;
          e.dk[e.nd] = borne(1 - (rd - 9) / 20, 0, 1) * (1 + 0.55f * cosf(th + SPA_PI)) * 0.85f;   // chaleur, doppler
          e.nd++;
        }
        const float anneau = borne(1 - fabsf(r - 9.5f) / 2.6f, 0, 1);         // le dessus et le dessous du disque, courbes
        if (anneau > 0 && e.na < SPA_TN_A) {
          const float phi = atan2f(dy, dx);
          e.ai[e.na] = (uint16_t)i;
          e.a4[e.na] = 4 * phi;
          e.ak[e.na] = anneau * (1 + 0.35f * cosf(phi + SPA_PI));
          e.na++;
        }
      }
    if (e.milieu < 0) e.milieu = e.nd;
  }
  for (int i = 0; i < 4096; i++) peindre(i >> 6, i & 63, 1, 1, 4);
  for (int k = 0; k < 70; k++) {
    const float l = e.el[k] * (0.55f + 0.45f * spa_sin(t * 2 + e.ep[k]));
    pointer(e.ey[k], e.ex[k], 200 * l, 205 * l, 230 * l);
  }
  float c[3];
  const float ta = t * 6.4f;
  for (int j = 0; j < e.na; j++) {
    const float k = e.ak[j] * (0.75f + 0.25f * spa_sin(e.a4[j] - ta));
    spa_tn_teinte(k, hu, c);
    const int i = e.ai[j];
    ajouter(i >> 6, i & 63, borne(k * 1.4f, 0, 1), c[0], c[1], c[2]);
  }
  for (int pas = 0; pas < 3; pas++) {
    if (pas == 1) {                                                              // l'ombre
      for (int y = 24; y <= 40; y++)
        for (int x = 24; x <= 40; x++)
          if (hypotf(x - cx, y - cy) <= ombre) peindre(y, x, 0, 0, 0);
      continue;
    }
    const int j0 = pas == 0 ? 0 : e.milieu, j1 = pas == 0 ? e.milieu : e.nd;
    for (int j = j0; j < j1; j++) {
      const float tourne = e.dth[j] - t * e.dw[j], rd = e.drd[j];
      const float stries = 0.6f + 0.25f * spa_sin(tourne * 3 + rd * 0.7f) + 0.15f * spa_sin(tourne * 7 - rd * 1.3f);
      const float k = e.dk[j] * stries;
      spa_tn_teinte(k, hu, c);
      const float f = borne(k * 1.6f, 0, 1);
      float *p = scene[e.di[j] >> 6][e.di[j] & 63];
      for (int q = 0; q < 3; q++) p[q] = fmaxf(p[q], c[q] * f);
    }
  }
  for (int i = 0; i < 4096; i++)
    if (e.photon[i] > 0) ajouter(i >> 6, i & 63, e.photon[i], hu[0][0], hu[0][1], hu[0][2]);
}

// ===== la galaxie spirale (_scene_galaxie) ====================================================

const float SPA_GALAXIE[2][4][3] = {{{255, 230, 180}, {110, 160, 255}, {255, 110, 170}, {20, 10, 20}},
                                    {{255, 240, 200}, {255, 180, 90}, {255, 90, 60}, {24, 10, 4}}};   // coeur, bras, nebuleuses, poussiere
const int SPA_GAL_N = 380;

// humeurs : 0 = bleu, 1 = or
struct E_galaxie {
  int16_t cp[4096], sp[4096];               // cos, sin de 2 (th - 2.3 log(r + 1)) : les bras
  uint16_t e15[4096], coeur[4096], lane[4096];
  float ra[SPA_GAL_N], ta[SPA_GAL_N], kind[SPA_GAL_N], col[SPA_GAL_N][3];
};
void s_galaxie(int humeur, bool debut, float t, float ecoule, float dt) {
  E_galaxie &e = etat_ecran<E_galaxie>(debut);
  (void)ecoule; (void)dt;
  const float (*hu)[3] = SPA_GALAXIE[humeur ? 1 : 0];
  const float cx = 32, cy = 32, inc = 0.55f, tilt = 0.45f, ct = cosf(tilt), st = sinf(tilt);
  if (debut) {
    semer_ciel(50, 64);
    for (int i = 0; i < 4096; i++) {
      const float dx = (i & 63) - cx, dy = (i >> 6) - cy;
      const float u = dx * ct + dy * st, v = (-dx * st + dy * ct) / inc;
      const float r = sqrtf(u * u + v * v) + 1e-6f, th = atan2f(v, u);
      const float ph = 2 * (th - 2.3f * logf(r + 1));
      e.cp[i] = (int16_t)roundf(cosf(ph) * 32767);
      e.sp[i] = (int16_t)roundf(sinf(ph) * 32767);
      e.e15[i] = (uint16_t)roundf(expf(-r / 15) * 65535);
      e.coeur[i] = (uint16_t)roundf(expf(-(r / 3.2f) * (r / 3.2f)) * 65535);
      e.lane[i] = (uint16_t)(r > 4 ? roundf(expf(-r / 14) * 65535) : 0);
    }
    for (int k = 0; k < SPA_GAL_N; k++) {
      const float ra = -10 * logf(1 - hasard(0, 1)) + 2;
      const int bras = aleatoire() & 1;
      e.ra[k] = ra;
      e.ta[k] = bras * SPA_PI + 2.3f * logf(ra + 1) + spa_normale(0.25f);
      e.kind[k] = hasard(0, 1);
      const float c0 = e.kind[k] > 0.88f ? hu[2][0] : e.kind[k] > 0.5f ? hu[1][0] * 1.3f : 230;
      const float c1 = e.kind[k] > 0.88f ? hu[2][1] : e.kind[k] > 0.5f ? hu[1][1] * 1.3f : 230;
      const float c2 = e.kind[k] > 0.88f ? hu[2][2] : e.kind[k] > 0.5f ? hu[1][2] * 1.3f : 255;
      const float f = expf(-ra / 30);
      e.col[k][0] = c0 * f; e.col[k][1] = c1 * f; e.col[k][2] = c2 * f;
    }
  }
  for (int i = 0; i < 4096; i++) peindre(i >> 6, i & 63, 2, 2, 6);
  etoiles_du_ciel(t);
  const float w = t * 0.08f, cw = cosf(w), sw = sinf(w), c55 = cosf(0.55f), s55 = sinf(0.55f);   // les bras tournent d'un bloc
  const float *bras = hu[1], *coeur = hu[0], *pous = hu[3];
  for (int i = 0; i < 4096; i++) {
    const float c0 = e.cp[i] * (1.0f / 32767), s0 = e.sp[i] * (1.0f / 32767);
    const float motif = c0 * cw + s0 * sw, sinus = s0 * cw - c0 * sw;
    const float lr = motif * c55 + sinus * s55;
    float lane = 0;
    if (lr > 0 && e.lane[i]) {
      const float l2 = lr * lr;
      lane = l2 * l2 * l2 * e.lane[i] * (1.0f / 65535);
    }
    const float m = motif > 0 ? motif : 0;
    const float dens = e.e15[i] * (1.0f / 65535) * (0.15f + 0.85f * m * m) * 1.8f, co = e.coeur[i] * (1.1f / 65535);
    const float sombre = 1 - fminf(lane * 1.5f, 0.7f), poussiere = lane * 0.3f;   // les bandes de poussiere
    float *p = scene[i >> 6][i & 63];
    for (int c = 0; c < 3; c++) p[c] = (p[c] + dens * bras[c] + co * coeur[c]) * sombre + poussiere * pous[c];
  }
  const float base = t * 0.04f, f15 = t * 1.5f;                                 // et chaque etoile a sa vitesse
  for (int k = 0; k < SPA_GAL_N; k++) {
    const float ang = e.ta[k] + base + t * 0.6f / (e.ra[k] + 3);
    const float su = e.ra[k] * spa_cos(ang), sv = e.ra[k] * spa_sin(ang) * inc;
    const float sx = cx + su * ct - sv * st, sy = cy + su * st + sv * ct;
    const float f = 0.5f + 0.5f * spa_sin(f15 + e.kind[k] * 20);
    pointer(sy, sx, e.col[k][0] * f + 30, e.col[k][1] * f + 30, e.col[k][2] * f + 30);
  }
}

// ===== 1. le trou noir et ses particules (_scene_gravite) =====================================
// De la vraie gravitation : une masse au centre, 260 grains qui n'en ont pas, un leger freinage qui
// les fait spiraler vers l'horizon, et leurs trainees qui s'effacent (gardees en x128 sur 16 bits).

const float SPA_GM = 900.0f, SPA_HORIZON = 6.2f, SPA_OMBRE = 4.8f;
const int SPA_GN = 260, SPA_GC = 300;
const float SPA_GPAL[6][4] = {{0.0f, 200, 60, 25}, {0.25f, 255, 125, 40}, {0.48f, 255, 195, 110},
                              {0.66f, 255, 245, 225}, {0.82f, 175, 210, 255}, {1.0f, 75, 135, 255}};

struct E_gravite {
  float px[SPA_GN], py[SPA_GN], vx[SPA_GN], vy[SPA_GN], ne[SPA_GN], lum[SPA_GN], frein[SPA_GN];
  float coul[SPA_GN][3], eclat[SPA_GN];
  float age;
  uint16_t trace[4096][3];      // la lumiere deposee pas a pas, x128
  float vers[1024];             // 255 (1 - exp(-(T / 170)^1.5)), pour T = i / 2 : les trainees, sans brulure
  uint16_t lueur[4096];         // la lueur diffuse, x65535
  float sx[40], sy[40], sp[40], sl[40];   // les etoiles du fond, deviees
  int nc;                       // le centre : l'ombre et l'anneau de photons
  uint16_t ci[SPA_GC];
  float com[SPA_GC], can[SPA_GC], cs2[SPA_GC], cc2[SPA_GC];
};

void spa_gravite_nee(E_gravite &e, int i, bool pres) {
  const float r = pres ? hasard(6.5f, 50) : hasard(44, 54), a = hasard(0, PI2);   // au depart : deja l'equilibre
  const float vc = sqrtf(SPA_GM / r), tang = vc * hasard(0.88f, 1.02f), rad = -vc * hasard(0, 0.1f);
  const float ca = cosf(a), sa = sinf(a);
  e.px[i] = r * ca;
  e.py[i] = r * sa;
  e.vx[i] = -sa * tang + ca * rad;
  e.vy[i] = ca * tang + sa * rad;
}
inline void spa_gravite_couleur(float chaud, float *o) {
  int k = 0;
  while (k < 4 && chaud > SPA_GPAL[k + 1][0]) k++;
  const float q = (chaud - SPA_GPAL[k][0]) / (SPA_GPAL[k + 1][0] - SPA_GPAL[k][0]);
  for (int j = 0; j < 3; j++) o[j] = SPA_GPAL[k][j + 1] + (SPA_GPAL[k + 1][j + 1] - SPA_GPAL[k][j + 1]) * q;
}
inline void spa_trace_coin(uint16_t *p, float w, const float *c) {
  for (int j = 0; j < 3; j++) {
    const int v = p[j] + (int)(w * c[j] + 0.5f);
    p[j] = (uint16_t)(v > 65535 ? 65535 : v);
  }
}
void spa_trace_point(E_gravite &e, float y, float x, const float *c) {
  if (!(y > -1.0f && y < 64.0f && x > -1.0f && x < 64.0f)) return;
  const int x0 = spa_plancher(x), y0 = spa_plancher(y);
  const float fx = x - x0, fy = y - y0;
  if (y0 >= 0 && x0 >= 0) spa_trace_coin(e.trace[y0 * 64 + x0], (1 - fx) * (1 - fy), c);
  if (y0 >= 0 && x0 < 63) spa_trace_coin(e.trace[y0 * 64 + x0 + 1], fx * (1 - fy), c);
  if (y0 < 63 && x0 >= 0) spa_trace_coin(e.trace[(y0 + 1) * 64 + x0], (1 - fx) * fy, c);
  if (y0 < 63 && x0 < 63) spa_trace_coin(e.trace[(y0 + 1) * 64 + x0 + 1], fx * fy, c);
}
// _gravite_avancer : `duree` secondes par petits pas (`cadence` par seconde), la lumiere deposee a
// chaque pas ; la trace oublie d'un coup (oubli^n), chaque pas depose avec oubli^(n - k)
void spa_gravite_avancer(E_gravite &e, float duree, float cadence) {
  const int n_pas = (int)ceilf(duree * cadence - 1e-3f);
  if (n_pas <= 0) return;
  const float h = duree / n_pas, oubli = expf(-h / 1.4f);
  const uint32_t m = (uint32_t)(powf(oubli, (float)n_pas) * 65536.0f);
  uint16_t *tr = &e.trace[0][0];
  for (int i = 0; i < 4096 * 3; i++) tr[i] = (uint16_t)((tr[i] * m) >> 16);
  float poids = h * 0.6f * 128.0f;
  for (int k = 1; k < n_pas; k++) poids *= oubli;
  const float inv_o = 1.0f / oubli;
  for (int k = 1; k <= n_pas; k++, poids *= inv_o) {
    e.age += h;
    for (int i = 0; i < SPA_GN; i++) {
      float x = e.px[i], y = e.py[i], vx = e.vx[i], vy = e.vy[i];
      const float r2 = x * x + y * y, q = r2 + 1;
      const float g = SPA_GM * h / (q * sqrtf(q));                             // la gravite (adoucie au tout pres)
      vx -= x * g;
      vy -= y * g;
      const float f = spa_exp(-h * e.frein[i] / fmaxf(sqrtf(r2), 4.0f));      // le freinage : ~1 px/s vers le centre
      vx *= f;
      vy *= f;
      x += vx * h;
      y += vy * h;
      const float r = sqrtf(x * x + y * y), v = sqrtf(vx * vx + vy * vy);
      float *c = e.coul[i];
      spa_gravite_couleur(borne((v - 4.3f) / 9.0f, 0, 1), c);                // vite (pres) : bleu-blanc ; lent : rouge
      const float ec = e.lum[i] * borne((r - SPA_HORIZON) / 2.2f, 0, 1) * borne(e.age - e.ne[i], 0, 2) * 0.5f;
      e.eclat[i] = ec;
      const float w = ec * v * poids;
      if (w > 0) {
        const float d[3] = {c[0] * w, c[1] * w, c[2] * w};
        spa_trace_point(e, 31.5f + y, 31.5f + x, d);
      }
      e.px[i] = x; e.py[i] = y; e.vx[i] = vx; e.vy[i] = vy;
      if (r < SPA_HORIZON || r > 70) {                                          // avalee : une autre arrive de loin
        spa_gravite_nee(e, i, false);
        e.ne[i] = e.age;
        const float u = hasard(0, 1);
        e.lum[i] = 0.25f + 0.75f * u * sqrtf(u);
        e.frein[i] = hasard(0.3f, 0.9f);
      }
    }
  }
}
void s_gravite(int humeur, bool debut, float t, float ecoule, float dt) {
  E_gravite &e = etat_ecran<E_gravite>(debut);
  (void)humeur; (void)ecoule;
  const float cx = 31.5f, cy = 31.5f;
  if (debut) {
    for (int i = 0; i < SPA_GN; i++) {
      spa_gravite_nee(e, i, true);
      const float u = hasard(0, 1);
      e.lum[i] = 0.25f + 0.75f * u * sqrtf(u);
      e.frein[i] = hasard(0.3f, 0.9f);
    }
    e.age = 10;
    for (int i = 0; i < 1024; i++) {
      const float q = i * 0.5f / 170.0f;
      e.vers[i] = 255 * (1 - expf(-q * sqrtf(q)));
    }
    for (int k = 0; k < 40; k++) {
      const float x = hasard(0, 64), y = hasard(0, 64), u = hasard(0, 1);
      e.sp[k] = hasard(0, PI2);
      e.sl[k] = 0.2f + 0.8f * u * u * u;
      const float vx = x - cx, vy = y - cy, rr = sqrtf(vx * vx + vy * vy) + 1e-6f, pousse = 1 + 30 / (rr * rr + 4);
      e.sx[k] = cx + vx * pousse;
      e.sy[k] = cy + vy * pousse;
    }
    for (int i = 0; i < 4096; i++) {
      const float dx = (i & 63) - cx, dy = (i >> 6) - cy, r = sqrtf(dx * dx + dy * dy);
      e.lueur[i] = (uint16_t)roundf(expf(-fmaxf(r - 6, 0.0f) / 6.0f) * 65535);
      if (r < 8.5f && e.nc < SPA_GC) {
        const float phi = atan2f(dy, dx), q = (r - SPA_OMBRE - 0.6f) / 0.6f;
        e.ci[e.nc] = (uint16_t)i;
        e.com[e.nc] = borne(r - SPA_OMBRE + 0.3f, 0, 1);
        e.can[e.nc] = expf(-q * q);
        e.cs2[e.nc] = sinf(2 * phi);
        e.cc2[e.nc] = cosf(2 * phi);
        e.nc++;
      }
    }
    spa_gravite_avancer(e, 2.5f, 30);                                            // la pose a deja commence : les arcs sont la
  }
  spa_gravite_avancer(e, fminf(dt, 0.5f), 60);
  for (int i = 0; i < 4096; i++) peindre(i >> 6, i & 63, 2, 2, 7);
  for (int k = 0; k < 40; k++) {
    const float l = e.sl[k] * (0.6f + 0.4f * spa_sin(t * 1.3f + e.sp[k]));
    pointer(e.sy[k], e.sx[k], 130 * l, 140 * l, 180 * l);
  }
  for (int i = 0; i < 4096; i++) {
    float *p = scene[i >> 6][i & 63];
    const float g = e.lueur[i] * (1.0f / 65535);
    const uint16_t *tr = e.trace[i];
    for (int c = 0; c < 3; c++) {
      const int j = (tr[c] + 32) >> 6;
      p[c] += e.vers[j > 1023 ? 1023 : j];
    }
    p[0] += g * 10; p[1] += g * 8; p[2] += g * 22;
  }
  for (int i = 0; i < SPA_GN; i++)
    if (e.eclat[i] > 0) spa_tacher(cy + e.py[i], cx + e.px[i], e.coul[i][0] * e.eclat[i], e.coul[i][1] * e.eclat[i], e.coul[i][2] * e.eclat[i]);
  const float c9 = cosf(t * 0.9f), s9 = sinf(t * 0.9f);
  for (int j = 0; j < e.nc; j++) {                                              // l'ombre, et l'anneau de photons
    float *p = scene[e.ci[j] >> 6][e.ci[j] & 63];
    const float k = e.com[j], a = e.can[j] * (0.85f + 0.15f * (e.cs2[j] * c9 - e.cc2[j] * s9)) * 0.85f;
    p[0] = p[0] * k + a * 255; p[1] = p[1] * k + a * 225; p[2] = p[2] * k + a * 180;
  }
}

// ===== 2. deux galaxies en collision (_scene_collision) =======================================
// Deux noyaux massifs qui s'attirent, 2 x 600 etoiles sans masse ; la maree les arrache en deux
// queues ; les noyaux fusionnent, et une autre rencontre arrive en fondu.

const int SPA_CN = 600;
const float SPA_C_DUREE = 42, SPA_C_FONDU = 9, SPA_C_VITESSE = 0.8f, SPA_C_FROT = 0.1f, SPA_C_R0 = 34;
const float SPA_C_FROIDES[2][2][3] = {{{140, 180, 255}, {255, 120, 190}}, {{185, 160, 255}, {110, 225, 255}}};
const float SPA_C_CHAUDES[2][2][3] = {{{255, 200, 120}, {255, 130, 80}}, {{255, 175, 140}, {255, 110, 160}}};
const float SPA_C_COEURS[2][3] = {{255, 236, 205}, {255, 222, 180}};

struct SpaRencontre {
  float age;
  uint8_t vivante, passe, premiere;
  float m[2], c[2][3], vc[2][3];
  float base[2][3], vif[2][3];             // la couleur de chaque galaxie, et celle de ses amas
  float vue, tourne;
  float pos[2 * SPA_CN][3], vel[2 * SPA_CN][3];
  int16_t k[2 * SPA_CN];                   // l'eclat de l'etoile, x8192 ; negatif : un amas de jeunes etoiles
};
struct E_collision {
  SpaRencontre r[2];
  int derniere;
  SpaEtoiles<45> fond;
  SpaFlou fl;
  float ton[1025];                         // 255 (1 - exp(-(f / 300)^0.7)), pour sqrt(f) = i / 8
};

void spa_collision_neuve(SpaRencontre &s, bool premiere) {
  const float m1 = hasard(150, 190), m2 = m1 * hasard(0.65f, 1.0f);
  const float rp = hasard(11.0f, 13.5f), ex = hasard(0.9f, 1.0f);              // le passage au plus pres, l'excentricite
  const float p_orb = rp * (1 + ex), r0 = SPA_C_R0;
  const float f = -acosf(borne((p_orb / r0 - 1) / ex, -1, 1));                // elles arrivent l'une vers l'autre
  const float kk = sqrtf((m1 + m2) / p_orb), cf = cosf(f), sf = sinf(f);
  const float rel[3] = {cf * r0, sf * r0, 0};
  const float vrel[3] = {cf * kk * ex * sf - sf * kk * (1 + ex * cf), sf * kk * ex * sf + cf * kk * (1 + ex * cf), 0};
  const float M = m1 + m2;
  s.age = 0;
  s.vivante = 1;
  s.passe = 0;
  s.premiere = premiere;
  s.m[0] = m1;
  s.m[1] = m2;
  for (int j = 0; j < 3; j++) {
    s.c[0][j] = -rel[j] * m2 / M; s.c[1][j] = rel[j] * m1 / M;
    s.vc[0][j] = -vrel[j] * m2 / M; s.vc[1][j] = vrel[j] * m1 / M;
  }
  const float (*paire[2])[3] = {SPA_C_FROIDES[aleatoire() & 1], SPA_C_CHAUDES[aleatoire() & 1]};
  if (hasard(0, 1) < 0.5f) { const float (*q)[3] = paire[0]; paire[0] = paire[1]; paire[1] = q; }
  for (int g = 0; g < 2; g++) {
    for (int j = 0; j < 3; j++) { s.base[g][j] = paire[g][0][j]; s.vif[g][j] = paire[g][1][j]; }
    const float masse = s.m[g], rayon = g == 0 ? hasard(8, 10) : hasard(6.5f, 8.5f);
    const float sens = (g == 0 || hasard(0, 1) < 0.8f) ? 1.0f : -1.0f;      // surtout dans le sens de l'orbite : les queues
    const float incl = hasard(0.3f, g == 0 ? 0.9f : 1.2f), noeud = hasard(0, PI2);
    const float ci = cosf(incl), si = sinf(incl), cn = cosf(noeud), sn = sinf(noeud);
    // rot = Rz(noeud)^T . Rx(incl) . Rz(noeud) : le disque incline dans l'espace
    const float rz[3][3] = {{cn, -sn, 0}, {sn, cn, 0}, {0, 0, 1}}, rx[3][3] = {{1, 0, 0}, {0, ci, -si}, {0, si, ci}};
    const float rzt[3][3] = {{cn, sn, 0}, {-sn, cn, 0}, {0, 0, 1}};
    float a[3][3], rot[3][3];
    for (int i = 0; i < 3; i++)
      for (int j = 0; j < 3; j++) a[i][j] = rx[i][0] * rz[0][j] + rx[i][1] * rz[1][j] + rx[i][2] * rz[2][j];
    for (int i = 0; i < 3; i++)
      for (int j = 0; j < 3; j++) rot[i][j] = rzt[i][0] * a[0][j] + rzt[i][1] * a[1][j] + rzt[i][2] * a[2][j];
    for (int n = 0; n < SPA_CN; n++) {
      const int i = g * SPA_CN + n;
      const float r = 1.2f + (rayon - 1.2f) * powf(hasard(0, 1), 1.1f);     // etendu : ses bords feront les queues
      const float an = hasard(0, PI2), ca = cosf(an), sa = sinf(an), q = r * r + 1;
      const float v = sqrtf(masse * r * r / (q * sqrtf(q)));
      const float p[3] = {r * ca, r * sa, spa_normale(0.25f)}, w[3] = {-sa * v * sens, ca * v * sens, 0};
      for (int j = 0; j < 3; j++) {
        s.pos[i][j] = rot[j][0] * p[0] + rot[j][1] * p[1] + rot[j][2] * p[2] + s.c[g][j];
        s.vel[i][j] = rot[j][0] * w[0] + rot[j][1] * w[1] + s.vc[g][j];
      }
      const float bord = 0.55f + 0.9f * sqrtf(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]) / rayon;   // les bords un peu plus vifs
      const bool rose = hasard(0, 1) < 0.12f;                                  // quelques amas de jeunes etoiles
      const float u = hasard(0, 1);
      const float k = (rose ? 1.0f : hasard(0.75f, 1.1f)) * (0.35f + 0.65f * u * sqrtf(u)) * bord;
      s.k[i] = (int16_t)(borne(k, 0, 3.99f) * 8192 * (rose ? -1 : 1));
    }
  }
  s.vue = hasard(0.35f, 0.8f);                                                   // on voit le plan de l'orbite de biais
  s.tourne = hasard(0, PI2);
}
void spa_collision_avancer(SpaRencontre &s, float duree) {
  const int n_pas = (int)ceilf(duree * 40 - 1e-3f);
  if (n_pas <= 0) return;
  const float h = duree / n_pas, m0 = s.m[0], m1 = s.m[1], M = m0 + m1;
  for (int pas = 0; pas < n_pas; pas++) {
    float d[3], rel[3];
    for (int j = 0; j < 3; j++) d[j] = s.c[1][j] - s.c[0][j];
    const float r2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2], q = r2 + 2;
    const float a = h / (q * sqrtf(q));
    for (int j = 0; j < 3; j++) {
      s.vc[0][j] += d[j] * a * m1;
      s.vc[1][j] -= d[j] * a * m0;
      rel[j] = s.vc[1][j] - s.vc[0][j];
    }
    if (!s.passe && d[0] * rel[0] + d[1] * rel[1] + d[2] * rel[2] > 0) s.passe = 1;   // le premier passage au plus pres
    if (s.passe && r2 < 900) {                                                   // puis le frottement : elles fusionnent
      const float perte = 1 - expf(-h * SPA_C_FROT * (1 - r2 / 900));
      for (int j = 0; j < 3; j++) {
        s.vc[0][j] += rel[j] * perte * m1 / M;
        s.vc[1][j] -= rel[j] * perte * m0 / M;
      }
    }
    for (int j = 0; j < 3; j++) { s.c[0][j] += s.vc[0][j] * h; s.c[1][j] += s.vc[1][j] * h; }
    const float ax = s.c[0][0], ay = s.c[0][1], az = s.c[0][2], bx = s.c[1][0], by = s.c[1][1], bz = s.c[1][2];
    for (int i = 0; i < 2 * SPA_CN; i++) {
      float *p = s.pos[i], *v = s.vel[i];
      const float dx0 = p[0] - ax, dy0 = p[1] - ay, dz0 = p[2] - az;
      const float dx1 = p[0] - bx, dy1 = p[1] - by, dz1 = p[2] - bz;
      const float q0 = dx0 * dx0 + dy0 * dy0 + dz0 * dz0 + 1, q1 = dx1 * dx1 + dy1 * dy1 + dz1 * dz1 + 1;
      const float f0 = m0 * h / (q0 * sqrtf(q0)), f1 = m1 * h / (q1 * sqrtf(q1));
      v[0] -= dx0 * f0 + dx1 * f1;
      v[1] -= dy0 * f0 + dy1 * f1;
      v[2] -= dz0 * f0 + dz1 * f1;
      p[0] += v[0] * h;
      p[1] += v[1] * h;
      p[2] += v[2] * h;
    }
  }
}
// projette une rencontre (de biais) et depose ses etoiles dans la scene
void spa_collision_dessiner(const SpaRencontre &s, float force) {
  const float cv = cosf(s.vue), sv = sinf(s.vue), ct = cosf(s.tourne), st = sinf(s.tourne);
  for (int i = 0; i < 2 * SPA_CN; i++) {
    const float *q = s.pos[i];
    const float x = q[0], y = q[1] * cv - q[2] * sv;
    const float X = 32 + x * ct - y * st, Y = 32 + x * st + y * ct;
    if (!(Y > -1.0f && Y < 64.0f && X > -1.0f && X < 64.0f)) continue;
    const float a0 = q[0] - s.c[0][0], b0 = q[1] - s.c[0][1], a1 = q[0] - s.c[1][0], b1 = q[1] - s.c[1][1];
    const float loin = sqrtf(fminf(a0 * a0 + b0 * b0, a1 * a1 + b1 * b1));
    const float k = s.k[i] * (1.0f / 8192) * force * spa_exp(-loin / 40.0f);   // ce qui s'eparpille palit
    const float *c = k < 0 ? s.vif[i >= SPA_CN] : s.base[i >= SPA_CN];
    const float ka = fabsf(k);
    spa_tacher(Y, X, c[0] * ka, c[1] * ka, c[2] * ka);
  }
}
void s_collision(int humeur, bool debut, float t, float ecoule, float dt) {
  E_collision &e = etat_ecran<E_collision>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    spa_semer_etoiles(e.fond);
    spa_collision_neuve(e.r[0], true);
    e.derniere = 0;
    for (int i = 0; i <= 1024; i++) {
      const float f = (i / 8.0f) * (i / 8.0f) / 300.0f;
      e.ton[i] = 255 * (1 - expf(-powf(f, 0.7f)));
    }
  }
  const float pas = fminf(dt, 0.5f);
  for (int g = 0; g < 2; g++)
    if (e.r[g].vivante) {
      spa_collision_avancer(e.r[g], pas * SPA_C_VITESSE);
      e.r[g].age += pas;
    }
  if (e.r[e.derniere].age >= SPA_C_DUREE - SPA_C_FONDU) {                        // la suivante arrive pendant que celle-ci s'efface
    e.derniere = 1 - e.derniere;
    spa_collision_neuve(e.r[e.derniere], false);
  }
  float force[2] = {0, 0};
  for (int g = 0; g < 2; g++) {
    SpaRencontre &s = e.r[g];
    if (s.vivante && s.age >= SPA_C_DUREE) s.vivante = 0;
    if (!s.vivante) continue;
    const float entree = s.premiere ? 1.0f : borne(s.age / SPA_C_FONDU, 0, 1);
    const float sortie = borne((SPA_C_DUREE - s.age) / SPA_C_FONDU, 0, 1);
    force[g] = entree * sortie > 0 ? powf(entree * sortie, 1.2f) : 0.0f;
  }
  memset(scene, 0, sizeof scene);
  for (int g = 0; g < 2; g++)
    if (force[g] > 0.002f) spa_collision_dessiner(e.r[g], force[g]);
  const float *ton = e.ton;
  spa_flou2(e.fl, [ton](int y, int x, const float *a, const float *f) {
    const float l0 = (a[0] * 0.6f + f[0]) * 0.25f, l1 = (a[1] * 0.6f + f[1]) * 0.25f, l2 = (a[2] * 0.6f + f[2]) * 0.25f;
    const float fort = fmaxf(l0, fmaxf(l1, l2));                                  // adoucir sans blanchir : la teinte reste
    float *p = scene[y][x];
    p[0] = 3; p[1] = 2; p[2] = 8;
    if (fort > 1e-3f) {
      const float s = sqrtf(fort) * 8;
      float g;
      if (s >= 1024) g = 255;
      else {
        const int i = (int)s;
        g = ton[i] + (ton[i + 1] - ton[i]) * (s - i);
      }
      g /= fort;
      p[0] += l0 * g; p[1] += l1 * g; p[2] += l2 * g;
    }
  });
  for (int g = 0; g < 2; g++) {                                                  // les noyaux
    if (force[g] <= 0.002f) continue;
    const SpaRencontre &s = e.r[g];
    const float cv = cosf(s.vue), sv = sinf(s.vue), ct = cosf(s.tourne), st = sinf(s.tourne);
    for (int n = 0; n < 2; n++) {
      const float x = s.c[n][0], y = s.c[n][1] * cv - s.c[n][2] * sv;
      const float nx = 32 + x * ct - y * st, ny = 32 + x * st + y * ct, k = force[g] * s.m[n] / 170;
      for (int yy = (int)ny - 8; yy <= (int)ny + 9; yy++)
        for (int xx = (int)nx - 8; xx <= (int)nx + 9; xx++) {
          if (yy < 0 || yy >= 64 || xx < 0 || xx >= 64) continue;
          const float d2 = (xx - nx) * (xx - nx) + (yy - ny) * (yy - ny);
          if (d2 > 80) continue;
          const float noyau = (spa_exp(-d2 / 2.5f) * 0.6f + spa_exp(-d2 / 12.0f) * 0.15f) * k;
          ajouter(yy, xx, noyau, SPA_C_COEURS[n][0], SPA_C_COEURS[n][1], SPA_C_COEURS[n][2]);
        }
    }
  }
  // le fond d'etoiles (pose sur le noir avant la lumiere) : ce qu'il ajoute au-dessus du fond, le plus vif par pixel
  const float fond[3] = {3, 2, 8};
  const SpaEtoiles<45> &et = e.fond;
  for (int i = 0; i < et.n; i++) {
    bool deja = false;
    for (int j = 0; j < i && !deja; j++) deja = et.y[j] == et.y[i] && et.x[j] == et.x[i];
    if (deja) continue;
    float m[3] = {0, 0, 0};
    for (int j = i; j < et.n; j++) {
      if (et.y[j] != et.y[i] || et.x[j] != et.x[i]) continue;
      const float k = et.l[j] * 0.55f * (0.75f + 0.25f * spa_sin(t * et.w[j] + et.p[j]));
      for (int c = 0; c < 3; c++) m[c] = fmaxf(m[c], k * SPA_TEINTES_ET[et.c[j]][c]);
    }
    for (int c = 0; c < 3; c++) scene[et.y[i]][et.x[i]][c] += fmaxf(m[c] - fond[c], 0.0f);
  }
}

// ===== 3. la Voie lactee au-dessus d'un arbre seul (_scene_voie_lactee) =======================
// Tout ce qui tourne avec le ciel (les nuages de la bande, ses poussieres, son bulbe, les
// nebuleuses roses) ne depend que de la position dans le repere de la bande : une texture,
// calculee au debut, qu'on lit tournee a chaque image.

const float SPA_V_PX = 30, SPA_V_PY = 27, SPA_V_TOUR = 900;
const int SPA_VT = 100;                    // la texture : u, v de -50 a 49
const float SPA_V_TEINTES[4][3] = {{200, 215, 255}, {240, 238, 245}, {255, 230, 190}, {255, 200, 150}};
const int SPA_V_N = 300;

struct E_voie_lactee {
  uint8_t tex[SPA_VT * SPA_VT * 3];
  uint16_t brouillon[128 * 128];           // les champs de _brume, le temps de les lire
  uint8_t masque[4096];                    // la colline et l'arbre
  uint8_t lueur[4096];                     // la lueur de l'horizon, x255
  float su[SPA_V_N], sv[SPA_V_N], sl[SPA_V_N], sp[SPA_V_N], sw[SPA_V_N];
  uint8_t sc[SPA_V_N];
  float fil[7], prochaine;
  bool filante;
};

void spa_voie_texture(E_voie_lactee &e) {
  uint8_t *tx = e.tex;
  uint16_t *b = e.brouillon;
  brume_n(b, 128, 9);                                                            // large
  for (int iv = 0; iv < SPA_VT; iv++)
    for (int iu = 0; iu < SPA_VT; iu++) {
      const float u = iu - 50.0f, v = iv - 50.0f;
      tx[3 * (iv * SPA_VT + iu) + 2] = (uint8_t)(fenetre_n(b, 128, u * 0.7f + 30, v * 0.7f + 90, 0, 0) * 255 + 0.5f);
    }
  brume_n(b, 128, 3);                                                            // fin
  for (int iv = 0; iv < SPA_VT; iv++)
    for (int iu = 0; iu < SPA_VT; iu++) {
      const float u = iu - 50.0f, v = iv - 50.0f;
      const int q = (int)(fenetre_n(b, 128, u * 0.9f + 64, v * 0.9f + 64, 0, 0) * 65535 + 0.5f);
      tx[3 * (iv * SPA_VT + iu)] = (uint8_t)(q >> 8);
      tx[3 * (iv * SPA_VT + iu) + 1] = (uint8_t)(q & 255);
    }
  brume_n(b, 128, 2);                                                            // le grain
  for (int iv = 0; iv < SPA_VT; iv++)
    for (int iu = 0; iu < SPA_VT; iu++) {
      const float u = iu - 50.0f, v = iv - 50.0f;
      uint8_t *o = tx + 3 * (iv * SPA_VT + iu);
      const float nf = (o[0] * 256 + o[1]) * (1.0f / 65535), nl = o[2] * (1.0f / 255);
      const float ng = fenetre_n(b, 128, u * 1.3f + 10, v * 1.3f + 40, 0, 0);
      const float bulbe = spa_exp(-(u * u + (v * 1.5f) * (v * 1.5f)) / (2 * 7.5f * 7.5f));
      const float largeur = 6.5f + 4 * spa_exp(-(u / 16) * (u / 16));
      const float bande = spa_exp(-(v / largeur) * (v / largeur)) * (0.55f + 0.45f * spa_exp(-(u / 40) * (u / 40)));
      float nuages = bande * (0.3f + 1.1f * powf(nf, 1.6f) * (0.6f + 0.8f * nl)) + bulbe * 0.8f;
      const float q = (v - 1.2f - 2.0f * sinf(u * 0.11f) - 4 * (nl - 0.5f)) / (1.6f + 0.8f * nl);
      const float rift = spa_exp(-q * q);
      const float pous = borne(rift * (0.65f + 0.9f * ng) + borne(nl - 0.6f, 0, 1) * 2.4f * bande, 0, 0.92f);
      nuages *= 1 - pous;                                                        // les poussieres sombres
      const float chaud = borne(bulbe * 1.6f, 0, 1), rose = borne(nf - 0.78f, 0, 1) * 5 * bande * (1 - pous);
      const float teinte[3] = {120 + 135 * chaud, 130 + 75 * chaud, 175 - 25 * chaud}, roses[3] = {150, 40, 80};
      for (int c = 0; c < 3; c++) o[c] = (uint8_t)(borne(nuages * teinte[c] * 0.62f + rose * roses[c], 0, 255) + 0.5f);
    }
}
void spa_voie_arbre(E_voie_lactee &e) {
  float crete[64];
  for (int x = 0; x < 64; x++)
    crete[x] = 53 + 2.2f * sinf(x * 0.055f + 0.8f) + 1.3f * sinf(x * 0.16f + 2.0f) - 2.2f * expf(-((x - 46) / 11.0f) * ((x - 46) / 11.0f));
  const float pied = crete[46];
  brume_n(e.brouillon, 64, 2);                                                   // les feuilles
  const float touffes[8][3] = {{39, -16, 4.2f}, {46, -20, 4.8f}, {53, -17, 4.4f}, {42, -21, 3.5f}, {50, -22, 3.6f},
                               {35, -15, 2.8f}, {57, -15, 2.8f}, {46, -15, 3.5f}};
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      bool m = y >= crete[x];
      const float h = pied - y;
      if (fabsf(x - 46 - h * 0.06f) <= 1.2f - h * 0.05f && y <= pied + 1 && y >= pied - 12) m = true;   // le tronc
      float tf = -1;
      for (int k = 0; k < 8; k++) tf = fmaxf(tf, 1 - hypotf(x - touffes[k][0], (y - pied - touffes[k][1]) * 1.15f) / touffes[k][2]);
      if (tf + (e.brouillon[i] * (1.0f / 65535) - 0.5f) * 0.5f > 0.1f) m = true;   // des bords feuillus, quelques trous
      e.masque[i] = m;
      e.lueur[i] = (uint8_t)(expf(-fmaxf(crete[x] - y, 0.0f) / 5.0f) * 255 + 0.5f);
    }
  const float branches[5][4] = {{46, pied - 7, 39, pied - 14}, {46.5f, pied - 9, 53, pied - 15}, {46, pied - 11, 46, pied - 18},
                                {41, pied - 12, 36, pied - 14}, {51, pied - 13, 56, pied - 14}};
  for (int b = 0; b < 5; b++)
    for (int k = 0; k < 30; k++) {
      const float q = k / 29.0f;
      const int yy = (int)roundf(branches[b][1] + (branches[b][3] - branches[b][1]) * q);
      const int xx = (int)roundf(branches[b][0] + (branches[b][2] - branches[b][0]) * q);
      e.masque[(yy < 0 ? 0 : yy > 63 ? 63 : yy) * 64 + (xx < 0 ? 0 : xx > 63 ? 63 : xx)] = 1;
    }
}
void s_voie_lactee(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voie_lactee &e = etat_ecran<E_voie_lactee>(debut);
  (void)humeur;
  if (debut) {
    spa_voie_texture(e);
    spa_voie_arbre(e);
    for (int k = 0; k < SPA_V_N; k++) {
      const bool dans = hasard(0, 1) < 0.55f;                                  // plus d'etoiles dans la bande
      e.su[k] = hasard(-48, 48);
      e.sv[k] = dans ? spa_normale(5.5f) : hasard(-48, 48);
      e.sl[k] = 0.18f + 0.82f * powf(hasard(0, 1), 3.2f);
      const float q = hasard(0, 1);
      e.sc[k] = q < 0.3f ? 0 : q < 0.7f ? 1 : q < 0.9f ? 2 : 3;
      e.sp[k] = hasard(0, PI2);
      e.sw[k] = hasard(0.5f, 1.6f);
    }
    e.filante = false;
    e.prochaine = ecoule + hasard(6, 14);
  }
  const float th = PI2 * spa_mod(t / SPA_V_TOUR, 1) + 0.6f, c = cosf(th), s = sinf(th);   // le ciel tourne, tres lentement
  for (int y = 0; y < 64; y++) {
    const float k = borne(y / 54.0f, 0, 1);
    const float g0 = 3 + 10 * k, g1 = 4 + 11 * k, g2 = 14 + 16 * k;
    const float dy = y - SPA_V_PY;
    float u = -SPA_V_PX * c + dy * s + 50, v = SPA_V_PX * s + dy * c + 50;
    for (int x = 0; x < 64; x++, u += c, v -= s) {
      const int i = y * 64 + x;
      if (e.masque[i]) { peindre(y, x, 3, 4, 8); continue; }
      const int u0 = (int)u, v0 = (int)v;
      const float fu = u - u0, fv = v - v0;
      const uint8_t *a = e.tex + 3 * (v0 * SPA_VT + u0), *bb = a + 3 * SPA_VT;
      const float l = e.lueur[i] * (1.0f / 255);
      float o[3];
      for (int q = 0; q < 3; q++) {
        const float haut = a[q] + (a[q + 3] - a[q]) * fu, bas = bb[q] + (bb[q + 3] - bb[q]) * fu;
        o[q] = haut + (bas - haut) * fv;
      }
      peindre(y, x, g0 + l * 16 + o[0], g1 + l * 12 + o[1], g2 + l * 18 + o[2]);
    }
  }
  for (int k = 0; k < SPA_V_N; k++) {                                            // les etoiles tournent avec le ciel
    const float ex = SPA_V_PX + e.su[k] * c - e.sv[k] * s, ey = SPA_V_PY + e.su[k] * s + e.sv[k] * c;
    if (!(ex > -1 && ex < 65 && ey > -1 && ey < 65)) continue;
    const float l = e.sl[k] * (0.72f + 0.28f * spa_sin(t * e.sw[k] * 2.0f + e.sp[k]));
    const float *col = SPA_V_TEINTES[e.sc[k]];
    spa_tacher(ey, ex, col[0] * l, col[1] * l, col[2] * l, 4);
    if (e.sl[k] > 0.8f) {                                                        // les plus vives, une petite croix
      const float q = l * 0.22f;
      spa_tacher(ey, ex + 1, col[0] * q, col[1] * q, col[2] * q, 4);
      spa_tacher(ey, ex - 1, col[0] * q, col[1] * q, col[2] * q, 4);
      spa_tacher(ey + 1, ex, col[0] * q, col[1] * q, col[2] * q, 4);
      spa_tacher(ey - 1, ex, col[0] * q, col[1] * q, col[2] * q, 4);
    }
  }
  if (!e.filante && ecoule >= e.prochaine) {
    const float a = hasard(0.35f, 0.75f) * (hasard(0, 1) < 0.5f ? -1.0f : 1.0f);
    e.fil[0] = hasard(10, 54); e.fil[1] = hasard(4, 22);
    e.fil[2] = cosf(a) * (a < 0 ? -1.0f : 1.0f); e.fil[3] = fabsf(sinf(a));
    e.fil[4] = hasard(26, 36); e.fil[5] = hasard(1.0f, 1.5f); e.fil[6] = 0;
    e.filante = true;
  }
  if (e.filante) {                                                               // une etoile filante, douce
    e.fil[6] += fminf(dt, 0.5f);
    const float k = e.fil[6] / e.fil[5];
    if (k >= 1) {
      e.filante = false;
      e.prochaine = ecoule + hasard(14, 34);
    } else {
      const float tete = e.fil[4] * k, sk = sinf(SPA_PI * k), fk = sk * sqrtf(sk);
      for (int j = 0; j < 20; j++) {
        const float d = fmaxf(tete - j * 0.5f, 0.0f), q = 1 - j * 0.05f, f = fk * q * sqrtf(q);
        spa_tacher(e.fil[1] + e.fil[3] * d, e.fil[0] + e.fil[2] * d, 172 * f, 176 * f, 191 * f);
      }
    }
  }
  for (int i = 0; i < 4096; i++)
    if (e.masque[i]) peindre(i >> 6, i & 63, 3, 4, 8);
}

// ===== 4. une eclipse totale (_scene_eclipse) =================================================

const float SPA_E_CYCLE = 48, SPA_E_R = 10.5f, SPA_E_C = 31.5f;
const float SPA_JETS[8][4] = {{0.35f, 1.0f, 0.22f, 0.10f}, {1.25f, 0.8f, 0.18f, -0.08f}, {2.05f, 0.65f, 0.26f, 0.12f},
                              {2.75f, 0.95f, 0.2f, -0.1f}, {3.6f, 0.75f, 0.24f, 0.07f}, {4.35f, 1.0f, 0.2f, -0.12f},
                              {5.15f, 0.7f, 0.28f, 0.09f}, {5.8f, 0.55f, 0.16f, -0.05f}};   // (angle, force, largeur, courbe)
const int SPA_E_ANN = 900;

struct E_eclipse {
  float th[4096], r[4096], e8[4096];       // l'angle, la distance au centre, exp(-hauteur / 8) dehors
  uint16_t diam[4096];                     // l'anneau de diamant, x16384
  uint8_t jets[4096];                      // les jets qui comptent ici (un bit chacun)
  int na;                                  // l'anneau ou vivent les protuberances
  uint16_t ai[SPA_E_ANN];
  float as[SPA_E_ANN], ac[SPA_E_ANN], abas[SPA_E_ANN], acote[SPA_E_ANN];
  float pa[5], ph0[5], pw[5], pph[5], pv[5];
  SpaEtoiles<30> et;
  int vy, vx;
  float fib[513];                          // les fibres de la couronne, par angle (refaites a chaque image)
};
void s_eclipse(int humeur, bool debut, float t, float ecoule, float dt) {
  E_eclipse &e = etat_ecran<E_eclipse>(debut);
  (void)humeur; (void)dt;
  const float R = SPA_E_R;
  if (debut) {
    const float bx = SPA_E_C + cosf(-0.8f) * (R + 0.3f), by = SPA_E_C + sinf(-0.8f) * (R + 0.3f);
    for (int i = 0; i < 4096; i++) {
      const float X = (float)(i & 63), Y = (float)(i >> 6), dx = X - SPA_E_C, dy = Y - SPA_E_C;
      const float r = sqrtf(dx * dx + dy * dy), th = atan2f(dy, dx), h = fmaxf(r - R, 0.0f);
      e.th[i] = th;
      e.r[i] = r;
      e.e8[i] = r > R ? expf(-h / 8.0f) : 0.0f;
      int bits = 0;
      const float q = 1.3f - 0.6f * borne(h / 22, 0, 1);
      for (int j = 0; j < 8; j++) {
        const float d = spa_enroule(th - SPA_JETS[j][0] - SPA_JETS[j][3] * h * 0.08f);
        if (fabsf(d) < 0.25f + 3.8f * SPA_JETS[j][2] * q) bits |= 1 << j;
      }
      e.jets[i] = (uint8_t)bits;
      const float lune = borne(R + 0.5f - r, 0, 1);
      const float d = hypotf(X - bx, Y - by), ey = fabsf(Y - by), ex = fabsf(X - bx);
      const float croix = expf(-ey * 1.5f - ex / 9) + expf(-ex * 1.5f - ey / 9);
      const float dm = (expf(-d / 1.3f) + 0.35f * expf(-d / 5.0f) + croix * 0.5f) * (1 - 0.92f * lune);
      e.diam[i] = (uint16_t)borne(dm * 16384 + 0.5f, 0, 65535);
      if (r > R - 1 && r < R + 8 && e.na < SPA_E_ANN) {                        // la ou vivent les protuberances
        const float c = spa_enroule(th + 0.8f);
        e.ai[e.na] = (uint16_t)i;
        e.as[e.na] = sinf(h * 1.2f);
        e.ac[e.na] = cosf(h * 1.2f);
        e.abas[e.na] = expf(-(h / 0.8f) * (h / 0.8f));
        e.acote[e.na] = expf(-c * c / 0.4f);
        e.na++;
      }
    }
    float angles[6];
    for (int k = 0; k < 6; k++) angles[k] = k * PI2 / 6 + hasard(-0.3f, 0.3f);
    for (int k = 5; k > 0; k--) {                                                // melangees : cinq des six
      const int j = (int)(aleatoire() % (uint32_t)(k + 1));
      const float a = angles[k]; angles[k] = angles[j]; angles[j] = a;
    }
    for (int k = 0; k < 5; k++) {
      e.pa[k] = angles[k];
      e.ph0[k] = hasard(2.0f, 3.8f);
      e.pw[k] = hasard(0.1f, 0.22f);
      e.pph[k] = hasard(0, 6);
      e.pv[k] = hasard(0.1f, 0.2f);
    }
    e.vy = 6 + (int)(aleatoire() % 8);
    e.vx = 44 + (int)(aleatoire() % 14);
    spa_semer_etoiles(e.et);
  }
  const float k = spa_mod(ecoule / SPA_E_CYCLE, 1);
  const float d1 = 0.5f - 0.5f * cosf(PI2 * k), d2 = d1 * d1, diamant = d2 * d2 * d2;   // rare, et tres doux
  for (int y = 0; y < 64; y++) {                                                // le ciel en plein jour eteint, un voile bleute
    const float q = y / 64.0f, g0 = 6 + 8 * q, g1 = 9 + 7 * q, g2 = 30 + 10 * q;
    for (int x = 0; x < 64; x++) {
      const float e8 = e.e8[y * 64 + x], v = 0.25f * e8 * e8;
      peindre(y, x, g0 + v * 120, g1 + v * 150, g2 + v * 255);
    }
  }
  spa_etoiles(e.et, t, 0.75f, 0.25f);
  peindre(e.vy, e.vx, 255, 250, 225);                                           // une planete, tres vive
  pointer(e.vy, e.vx - 1, 90, 88, 80); pointer(e.vy, e.vx + 1, 90, 88, 80);
  pointer(e.vy - 1, e.vx, 90, 88, 80); pointer(e.vy + 1, e.vx, 90, 88, 80);
  float bal[8], fj[8], inv[8];
  for (int j = 0; j < 8; j++) {                                                  // les jets de la couronne, qui ondulent
    const float a0 = SPA_JETS[j][0];
    bal[j] = 0.14f * sinf(t * 0.17f + a0 * 3) + 0.06f * sinf(t * 0.37f + a0);
    fj[j] = SPA_JETS[j][1] * (0.85f + 0.15f * sinf(t * 0.4f + a0 * 5));
    inv[j] = 1.0f / SPA_JETS[j][2];
  }
  const float s11 = t * 0.11f, s09 = t * 0.09f;
  for (int b = 0; b <= 512; b++) {
    const float a = -SPA_PI + b * (PI2 / 512);
    e.fib[b] = 0.8f + 0.2f * spa_sin(a * 23 + spa_sin(a * 3 + s11) * 2) * spa_sin(a * 9 - s09);
  }
  float hk[5], cph[5], sph[5];
  for (int j = 0; j < 5; j++) {
    hk[j] = 1.0f / (e.ph0[j] * (0.7f + 0.3f * sinf(t * e.pv[j] + e.pph[j])));
    cph[j] = cosf(t * 0.45f + e.pph[j]);
    sph[j] = sinf(t * 0.45f + e.pph[j]);
  }
  const float att = 1 - 0.25f * diamant, dk = diamant * 1.5f / 16384;
  int cur = 0;
  for (int i = 0; i < 4096; i++) {
    float *p = scene[i >> 6][i & 63];
    const float r = e.r[i];
    const bool anneau = cur < e.na && e.ai[cur] == i;
    if (anneau) cur++;
    if (r <= R - 0.5f) {                                                         // dans la lune
      p[0] = 3; p[1] = 3; p[2] = 6;
    } else {
      const float e8 = e.e8[i], h = fmaxf(r - R, 0.0f), th = e.th[i];
      if (e8 > 0) {
        float rayons = 0.22f;
        const int bits = e.jets[i];
        const float q = 1.0f / (1.3f - 0.6f * fminf(h / 22, 1.0f)), hc = h * 0.08f;
        for (int j = 0; j < 8 && (bits >> j); j++) {
          if (!((bits >> j) & 1)) continue;
          float d = th - SPA_JETS[j][0] - SPA_JETS[j][3] * hc;               // ils se courbent en montant
          while (d < -SPA_PI) d += PI2;
          while (d >= SPA_PI) d -= PI2;
          const float x = (d - bal[j]) * inv[j] * q, x2 = x * x;
          if (x2 < 14) rayons += spa_exp(-x2) * fj[j];
        }
        const float fb = (th + SPA_PI) * (512 / PI2);
        const int ib = fb >= 512 ? 511 : (int)fb;
        const float fibres = e.fib[ib] + (e.fib[ib + 1] - e.fib[ib]) * (fb - ib);
        const float e2 = e8 * e8;
        const float couronne = (0.6f * e2 * e2 + 0.75f * e8 * rayons * fibres) * att;
        p[0] += couronne * 235; p[1] += couronne * 238; p[2] += couronne * 255;
      }
      if (anneau) {                                                              // les protuberances, qui montent et retombent
        const int j = cur - 1;
        float protu = 0;
        for (int n = 0; n < 5; n++) {
          float d = th - e.pa[n];
          while (d < -SPA_PI) d += PI2;
          while (d >= SPA_PI) d -= PI2;
          const float w = e.pw[n] * (1 + 0.4f * (e.as[j] * cph[n] + e.ac[j] * sph[n]));
          const float a = d / w, b = h * hk[n], z = a * a + b * b;
          if (z < 14) protu += spa_exp(-z);
        }
        if (r > R - 0.2f) {
          const float rose = borne(protu * 1.1f + e.abas[j] * (0.3f + 0.7f * diamant * e.acote[j]), 0, 1);
          const float g = 1 - rose * 0.8f;
          p[0] = p[0] * g + rose * 255; p[1] = p[1] * g + rose * 60; p[2] = p[2] * g + rose * 115;
        }
      }
      const float lune = borne(R + 0.5f - r, 0, 1);
      if (lune > 0) {
        p[0] += (3 - p[0]) * lune; p[1] += (3 - p[1]) * lune; p[2] += (6 - p[2]) * lune;
      }
    }
    if (diamant > 0.003f) {                                                      // l'anneau de diamant
      const float q = e.diam[i] * dk;
      p[0] += q * 255; p[1] += q * 250; p[2] += q * 235;
    }
  }
}

// ===== 5. le soleil de pres (_scene_soleil) ===================================================
// Le bord du disque en arc, ses granules (deux couches qui glissent), l'assombrissement du bord ;
// au-dessus, les boucles de plasma et leur halo (le flou en place sur la scene).

const float SPA_S_CX = 10, SPA_S_CY = 88, SPA_S_R = 58;
const float SPA_BOUCLES[5][6] = {{-1.44f, -1.1f, 21, 0, 0.07f, 0.25f}, {-1.0f, -0.84f, 12, 2, 0.09f, -0.15f},
                                 {-0.72f, -0.62f, 8, 4.1f, 0.11f, 0.2f}, {-1.66f, -1.56f, 7, 1, 0.1f, -0.3f},
                                 {-0.56f, -0.47f, 6, 5.3f, 0.12f, 0}};   // (pied, pied, hauteur, phase, vitesse, penche)
const int SPA_S_NS = 140, SPA_S_NB = 400;
const float SPA_S_SU0 = -120;              // les tables par position le long du bord : de su = -120, par quarts

struct SpaSoleilPx { int16_t su[4096]; uint16_t sv[4096]; float rho[4096]; };   // su x128, sv x512
struct E_soleil {
  uint8_t g1[128 * 128], g2[128 * 128], g3[64 * 64];   // les granules (g3 : la grande echelle, a demi-resolution)
  union { uint16_t brouillon[128 * 128]; SpaSoleilPx px; } u;
  SpaFlou fl;
  float lmu[3][257];                       // 0.32 + 0.72 mu^0.7, mu^0.8, 0.55 (1 - mu)^1.5
  float voile[SPA_S_NB + 1], flamme[SPA_S_NB + 1];
  float arche[SPA_S_NS], a08[SPA_S_NS], a2[SPA_S_NS], fs[SPA_S_NS], fc[SPA_S_NS];
  float by[SPA_S_NS], bx[SPA_S_NS];
  float vis0, vis1, fr0, fr1;
};
void s_soleil(int humeur, bool debut, float t, float ecoule, float dt) {
  E_soleil &e = etat_ecran<E_soleil>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float R = SPA_S_R, cx = SPA_S_CX, cy = SPA_S_CY;
  if (debut) {
    brume_n(e.u.brouillon, 128, 14);                                             // la grande echelle, moyennee 2 x 2
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const uint16_t *b = e.u.brouillon + (2 * y) * 128 + 2 * x;
        e.g3[y * 64 + x] = (uint8_t)((b[0] + b[1] + b[128] + b[129]) / (4.0f * 257) + 0.5f);
      }
    brume_n(e.u.brouillon, 128, 3);
    for (int i = 0; i < 16384; i++) e.g1[i] = (uint8_t)(e.u.brouillon[i] / 257.0f + 0.5f);
    brume_n(e.u.brouillon, 128, 4);
    for (int i = 0; i < 16384; i++) e.g2[i] = (uint8_t)(e.u.brouillon[i] / 257.0f + 0.5f);
    float mn = 1e9f, mx = -1e9f;
    for (int i = 0; i < 4096; i++) {                                             // la surface vue en sphere
      const float dx = (i & 63) - cx, dy = (i >> 6) - cy, rho = sqrtf(dx * dx + dy * dy);
      const float su = R * atan2f(dy, dx), sv = R * asinf(borne(rho / R, 0, 1));
      e.u.px.su[i] = (int16_t)roundf(su * 128);
      e.u.px.sv[i] = (uint16_t)roundf(sv * 512);
      e.u.px.rho[i] = rho;
      if (rho <= R) { mn = fminf(mn, su); mx = fmaxf(mx, su); }
    }
    e.vis0 = mn - 8;
    e.vis1 = mx + 8;
    for (int k = 0; k <= 256; k++) {
      const float mu = k / 256.0f;
      e.lmu[0][k] = 0.32f + 0.72f * powf(mu, 0.7f);
      e.lmu[1][k] = powf(mu, 0.8f);
      e.lmu[2][k] = 2.5f * 0.22f * powf(1 - mu, 1.5f);
    }
    for (int j = 0; j < SPA_S_NS; j++) {
      const float s = j / (float)(SPA_S_NS - 1), a = sinf(SPA_PI * s);
      e.arche[j] = a;
      e.a08[j] = powf(fmaxf(a, 0.0f), 0.8f);
      e.a2[j] = a * a;
      e.fs[j] = sinf(fabsf(s - 0.5f) * 20);
      e.fc[j] = cosf(fabsf(s - 0.5f) * 20);
    }
    e.fr0 = hasard(0, PI2);
    e.fr1 = hasard(0, PI2);
  }
  // les tables le long du bord : le voile de la couronne, la frange de flammeches
  const float vs = 0.5f * sinf(t * 0.05f), f1 = e.fr0 + t * 0.25f, f2 = e.fr1 - t * 0.15f;
  for (int b = 0; b <= SPA_S_NB; b++) {
    const float su = SPA_S_SU0 + b * 0.25f;
    e.voile[b] = 0.75f + 0.25f * spa_sin(su * 0.35f + 1.0f + vs) * spa_sin(su * 0.13f - 0.7f);
    e.flamme[b] = 0.5f + 0.5f * spa_sin(su * 1.3f + f1) * spa_sin(su * 0.47f + f2);
  }
  // les boucles de plasma, deposees dans la scene (puis floues en place)
  memset(scene, 0, sizeof scene);
  for (int l = 0; l < 5; l++) {
    const float *B = SPA_BOUCLES[l];
    const float h = B[2] * (0.6f + 0.4f * sinf(t * B[4] + B[3])), kap = B[5] * h / R;
    for (int brin = 0; brin < 2; brin++) {
      const float plus = brin ? 0.9f : 0.0f, decal = brin ? 1.7f : 0.0f, force = brin ? 0.55f : 1.0f;
      const float phi = -t * 1.3f + B[3] + decal, cp = cosf(phi), sp = sinf(phi);
      for (int j = 0; j < SPA_S_NS; j++) {
        const float s = j / (float)(SPA_S_NS - 1);
        const float ang = B[0] + (B[1] - B[0]) * s + kap * e.a2[j];
        const float rr = R + 0.2f + (h + plus) * e.a08[j];
        e.by[j] = cy + rr * spa_sin(ang);
        e.bx[j] = cx + rr * spa_cos(ang);
      }
      for (int j = 0; j < SPA_S_NS; j++) {
        const int a = j < SPA_S_NS - 1 ? j : j - 1;                             // par longueur
        const float pas = hypotf(e.by[a + 1] - e.by[a], e.bx[a + 1] - e.bx[a]);
        const float flux = 0.5f + 0.5f * (e.fs[j] * cp + e.fc[j] * sp);         // le plasma qui redescend
        const float w = flux * pas * force;
        spa_tacher(e.by[j], e.bx[j], 255 * w, 160 * w, 80 * w);
      }
    }
  }
  // la surface
  const float tour = spa_mod(t * 0.16f, 128), ta = spa_mod(t * 0.13f, 128), tb = 70 - spa_mod(t * 0.11f, 128);
  const float periode = 128 / 0.55f;
  float tache[2] = {1e9f, 1e9f};
  const float taches[2][3] = {{-20.0f, 38.0f, 1.0f}, {-14.0f, 41.0f, 0.7f}};
  for (int k = 0; k < 2; k++) {                                                  // deux taches, emportees par la rotation
    const float centre = spa_mod(taches[k][0] - tour / 0.55f + periode / 2, periode) - periode / 2;
    if (e.vis0 < centre && centre < e.vis1) tache[k] = centre;
  }
  const E_soleil &ec = e;
  spa_flou2(e.fl, [&ec, R, tour, ta, tb, &tache, &taches](int y, int x, const float *a, const float *f) {
    const int i = y * 64 + x;
    const float rho = ec.u.px.rho[i], su = ec.u.px.su[i] * (1.0f / 128);
    const float bord = borne(R - rho + 0.5f, 0, 1);
    float o[3] = {0, 0, 0};
    if (bord < 1) {                                                              // l'espace autour : la couronne, la frange
      const float haut = fmaxf(rho - R, 0.0f);
      const float fb = borne((su - SPA_S_SU0) * 4, 0, SPA_S_NB - 0.001f);
      const int ib = (int)fb;
      const float q = fb - ib;
      const float voile = ec.voile[ib] + (ec.voile[ib + 1] - ec.voile[ib]) * q;
      const float flamme = ec.flamme[ib] + (ec.flamme[ib + 1] - ec.flamme[ib]) * q;
      const float cour = rho > R ? spa_exp(-haut / 14.0f) * voile : 0.0f;
      const float chromo = rho > R - 0.5f ? spa_exp(-haut / (0.6f + 1.2f * flamme)) : 0.0f;
      o[0] = cour * 46 + chromo * 191 + 3;
      o[1] = cour * 11 + chromo * 52 + 1;
      o[2] = cour * 7 + chromo * 19 + 2;
    }
    if (bord > 0) {                                                              // le disque
      const float sv = ec.u.px.sv[i] * (1.0f / 512), su55 = su * 0.55f, sv55 = sv * 0.55f;
      const float ga = spa_lire8(ec.g1, 128, su55 + tour, sv55 + ta);
      const float gb = spa_lire8(ec.g2, 128, su55 + (tour * 1.1f + 40), sv55 + tb);
      const float grand = spa_lire8(ec.g3, 64, (su * 0.4f + tour * 0.4f - 0.5f) * 0.5f, (sv * 0.4f - 0.5f) * 0.5f);
      const float cellule = borne((ga * 0.55f + gb * 0.45f - 0.5f) * 3.0f, -1, 1);   // deux couches qui glissent : ca bouillonne
      const float q2 = 1 - (rho / R) * (rho / R);
      const float mu = q2 > 0 ? sqrtf(q2) : 0.0f, fm = mu * 256;
      const int im = fm >= 256 ? 255 : (int)fm;
      const float qm = fm - im;
      const float m06 = ec.lmu[0][im] + (ec.lmu[0][im + 1] - ec.lmu[0][im]) * qm;
      const float m08 = ec.lmu[1][im] + (ec.lmu[1][im + 1] - ec.lmu[1][im]) * qm;
      const float fac = ec.lmu[2][im] + (ec.lmu[2][im + 1] - ec.lmu[2][im]) * qm;
      float lum = m06 * (0.78f + 0.22f * cellule) * (0.92f + 0.16f * grand) + borne(grand - 0.58f, 0, 1) * fac;
      for (int k = 0; k < 2; k++) {
        const float ds = su - tache[k], dv = sv - taches[k][1], lim = 3.6f * taches[k][2];
        if (fabsf(ds) >= lim || fabsf(dv) >= lim) continue;
        const float d = sqrtf(ds * ds + dv * dv) / taches[k][2];
        lum *= 1 - 0.72f * borne(2.2f - d, 0, 1) - 0.3f * borne(3.6f - d, 0, 1) * borne(d - 1.4f, 0, 1);
      }
      const float chaud = borne(m08 * (0.85f + 0.25f * cellule), 0, 1);
      const float s0 = (210 + 45 * chaud) * lum, s1 = (50 + 125 * chaud) * lum, s2 = (2 + 46 * chaud) * lum;
      o[0] += (s0 - o[0]) * bord; o[1] += (s1 - o[1]) * bord; o[2] += (s2 - o[2]) * bord;
    }
    float *p = scene[y][x];
    if (rho > R - 0.3f) {                                                        // les boucles, et leur halo
      p[0] = o[0] + a[0] * 0.9f + f[0] * 1.6f;
      p[1] = o[1] + a[1] * 0.9f + f[1] * 0.9f;
      p[2] = o[2] + a[2] * 0.9f + f[2] * 0.7f;
    } else {
      p[0] = o[0] + f[0] * 0.4f; p[1] = o[1] + f[1] * 0.4f; p[2] = o[2] + f[2] * 0.4f;
    }
  });
}

// ===== 6. une comete (_scene_comete) ==========================================================

const float SPA_CO_PERIODE = 64;
struct E_comete {
  float ch[8][5];                          // les chemins : y0, pente, bombe, axe, courbe
  SpaEtoiles<90> et;
  uint16_t soleil[4096];                   // le soleil, hors champ : sa lueur, x65535
};
// une comete a l'etape s de sa traversee (0 : elle entre a gauche ; 1 : elle sort a droite)
void spa_comete(const float *v, float s, float t) {
  const float hx = -1 + 79 * s;
  if (hx < -40 || hx > 110) return;
  const float k = sinf(SPA_PI * borne(s, 0, 1));
  const float hy = v[0] - v[1] * s - v[2] * k, courbe = v[4];
  const float force = 0.72f + 0.28f * k;                                        // au plus pres du soleil au milieu
  const float th = v[3] + 0.25f * (s - 0.5f), ax = cosf(th), ay = sinf(th);   // la queue fuit le soleil
  const float lq = 30 + 12 * k, ilq = 1 / lq, ilq8 = 1 / (lq * 0.8f), c30 = courbe / 30;
  const float t11 = t * 1.1f, t20 = t * 2.0f;
  for (int y = 0; y < 64; y++) {
    const float ry = y - hy;
    for (int x = 0; x < 64; x++) {
      const float rx = x - hx, ll = rx * ax + ry * ay, tr = -rx * ay + ry * ax, d2 = rx * rx + ry * ry;
      float r = 0, g = 0, b = 0;
      if (d2 < 900) {                                                            // la chevelure
        const float ch = spa_exp(-d2 / 7.0f) * 0.7f + spa_exp(-sqrtf(d2) / 4.5f) * 0.25f;
        r += ch * 104; g += ch * 204; b += ch * 164;
      }
      if (ll > -1.5f) {
        const float devant = fminf(ll + 1.5f, 3.0f) / 3, arr = fmaxf(ll, 0.0f);
        const float w = 0.45f + 0.03f * arr;
        if (fabsf(tr) < 0.5f + 3.8f * w) {                                       // la queue d'ions, droite et bleue
          const float axe = tr - 0.5f * spa_sin(ll * 0.22f - t11) * borne(ll / 25, 0, 1), q = axe / w;
          const float z = arr * ilq + q * q;
          if (z < 14) {
            const float ion = spa_exp(-z) * devant * (0.8f + 0.2f * spa_sin(ll * 0.35f - t20)) * 0.8f;   // des noeuds qui filent
            r += ion * 70; g += ion * 140; b += ion * 255;
          }
        }
        const float ec = tr - c30 * arr * arr, q = ec / (1.0f + 0.24f * arr);   // la poussiere traine, en courbe
        const float z = arr * ilq8 + q * q;
        if (z < 14) {
          const float pous = spa_exp(-z) * devant * (0.85f + 0.15f * spa_sin(q * 3 + ll * 0.08f));
          const float loin = borne(ll / 30, 0, 1);
          r += pous * (255 - 15 * loin); g += pous * (242 - 67 * loin); b += pous * (205 - 110 * loin);
        }
      }
      if (r + g + b > 0) ajouter(y, x, force, r, g, b);
    }
  }
  spa_tacher(hy, hx, 255 * force, 255 * force, 240 * force);
}
void s_comete(int humeur, bool debut, float t, float ecoule, float dt) {
  E_comete &e = etat_ecran<E_comete>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    for (int k = 0; k < 8; k++) {                                                // la poussiere s'incurve vers le bas
      e.ch[k][0] = hasard(40, 52); e.ch[k][1] = hasard(6, 16); e.ch[k][2] = hasard(3, 8);
      e.ch[k][3] = hasard(-2.75f, -2.5f); e.ch[k][4] = -hasard(0.6f, 1.2f);
    }
    spa_semer_etoiles(e.et);
    for (int i = 0; i < 4096; i++)
      e.soleil[i] = (uint16_t)roundf(expf(-hypotf((i & 63) - 76.0f, (i >> 6) - 78.0f) / 22.0f) * 65535);
  }
  for (int y = 0; y < 64; y++) {
    const float q = y / 64.0f, g0 = 3 + 5 * q, g1 = 4 + 4 * q, g2 = 14 + 8 * q;
    for (int x = 0; x < 64; x++) {
      const float s = e.soleil[y * 64 + x] * (1.0f / 65535);
      peindre(y, x, g0 + s * 46, g1 + s * 26, g2 + s * 12);
    }
  }
  spa_etoiles(e.et, t, 1.0f, 0.3f);
  const float q = t / SPA_CO_PERIODE;
  const int n = spa_plancher(q);
  const float s = q - n;
  spa_comete(e.ch[((n % 8) + 8) % 8], s, t);                                    // celle qui passe
  spa_comete(e.ch[(((n - 1) % 8) + 8) % 8], s + 1, t);                          // et la queue de la precedente
}

// ===== 7. la Terre vue d'orbite (_scene_orbite) ===============================================
// Les lumieres des villes : deux cartes 128 x 128 (les amas orange, les blancs), en racine (le
// sombre garde sa finesse) ; leur lueur lointaine et les grands nuages a demi-resolution.

const float SPA_O_CX = 30, SPA_O_CY = 122, SPA_O_R = 82, SPA_O_CYCLE = 96, SPA_O_AUBE = -1.38f;
const float SPA_O_COUCHES[6][4] = {{0.0f, 255, 80, 25}, {1.2f, 255, 150, 50}, {2.4f, 255, 215, 140},
                                   {3.6f, 150, 185, 255}, {5.5f, 55, 100, 255}, {9.0f, 20, 40, 140}};
const float SPA_O_TEINTES[2][3] = {{255, 190, 100}, {235, 235, 210}};
const int SPA_O_SOL0 = 38;                 // la premiere rangee ou la Terre peut etre
const float SPA_O_DA0 = -0.8f, SPA_O_DAS = 1.4f / 256;   // la table par angle, de -0.8 a 0.6

struct SpaOrbitePx {
  int16_t u[4096];                         // 0.9 su, x64
  uint16_t rho[4096];                      // x256
  uint16_t recul[(64 - SPA_O_SOL0) * 64];  // 0.9 recul, x256
  float hl[257][6];                        // selon la hauteur (par quarts) : ligne, verte, couches (3), haut
  float al[257][4];                        // selon l'angle a l'aube, a chaque image
};
struct E_orbite {
  uint8_t vo[128 * 128], vw[128 * 128];    // les villes : 255 sqrt(V / 3), V l'eclat (0.6 points + 1.2 flou)
  uint8_t lo[64 * 64], lw[64 * 64];        // leur lueur de loin, 255 sqrt(L / max)
  uint8_t na[64 * 64], nb[128 * 128];      // les nuages
  union { uint16_t brouillon[128 * 128]; SpaOrbitePx px; } u;
  float lo_k, lw_k;
  SpaEtoiles<50> et;
  uint16_t rangs[3][128];
};

// les amas de villes, rejoues a l'identique (la meme graine) : ne s'ajoutent que ceux de `teinte`
void spa_villes_semer(uint32_t depart, uint16_t *buf, int taille, int teinte, float poids) {
  graine = depart;
  const int dec = taille == 128 ? 0 : 1;
  for (int a = 0; a < 72; a++) {
    const float cx = hasard(0, 128), cy = hasard(0, 128), etale = hasard(0.7f, 2.6f);
    const int n = 5 + (int)(aleatoire() % 27), ici = hasard(0, 1) < 0.75f ? 0 : 1;
    for (int k = 0; k < n; k++) {
      const float xs = cx + spa_normale(etale), ys = cy + spa_normale(etale * 0.8f), l = hasard(0.25f, 0.8f);
      if (ici != teinte) continue;
      const int xi = (spa_plancher(xs) & 127) >> dec, yi = (spa_plancher(ys) & 127) >> dec;
      const int v = buf[yi * taille + xi] + (int)(l * poids * 2048 + 0.5f);
      buf[yi * taille + xi] = (uint16_t)(v > 65535 ? 65535 : v);
    }
  }
}
// le flou de _orbite_villes (2 a + ses quatre voisins) / 6, qui se raccorde, en place
void spa_flou_tore(uint16_t *c, int taille, uint16_t (*rg)[128]) {
  const int m = taille - 1;
  uint16_t *avant = rg[0], *ici = rg[1], *premiere = rg[2];
  for (int x = 0; x < taille; x++) { premiere[x] = c[x]; avant[x] = c[m * taille + x]; }
  for (int y = 0; y < taille; y++) {
    for (int x = 0; x < taille; x++) ici[x] = c[y * taille + x];
    const uint16_t *bas = y == m ? premiere : c + (y + 1) * taille;
    for (int x = 0; x < taille; x++) {
      const int s = 2 * ici[x] + avant[x] + bas[x] + ici[(x + m) & m] + ici[(x + 1) & m];
      c[y * taille + x] = (uint16_t)((s + 3) / 6);
    }
    uint16_t *q = avant; avant = ici; ici = q;
  }
}
// deux cartes d'octets en racine lues au meme endroit (melange des quatre voisines, au carre)
inline void spa_lire_paire(const uint8_t *a, const uint8_t *b, int taille, float u, float v, float &va, float &vb) {
  const int m = taille - 1;
  const int u0 = spa_plancher(u), v0 = spa_plancher(v);
  const float fu = u - u0, fv = v - v0;
  const int i0 = u0 & m, i1 = (u0 + 1) & m, j0 = (v0 & m) * taille, j1 = ((v0 + 1) & m) * taille;
  const float w00 = (1 - fu) * (1 - fv), w01 = fu * (1 - fv), w10 = (1 - fu) * fv, w11 = fu * fv;
  va = w00 * (a[j0 + i0] * a[j0 + i0]) + w01 * (a[j0 + i1] * a[j0 + i1]) + w10 * (a[j1 + i0] * a[j1 + i0]) + w11 * (a[j1 + i1] * a[j1 + i1]);
  vb = w00 * (b[j0 + i0] * b[j0 + i0]) + w01 * (b[j0 + i1] * b[j0 + i1]) + w10 * (b[j1 + i0] * b[j1 + i0]) + w11 * (b[j1 + i1] * b[j1 + i1]);
}
void spa_orbite_preparer(E_orbite &e) {
  const uint32_t depart = aleatoire();
  uint16_t *b = e.u.brouillon;
  for (int T = 0; T < 2; T++) {                                                  // les villes, et leur flou
    uint8_t *dest = T ? e.vw : e.vo;
    memset(b, 0, sizeof e.u.brouillon);
    spa_villes_semer(depart, b, 128, T, 1.0f);
    spa_flou_tore(b, 128, e.rangs);
    spa_flou_tore(b, 128, e.rangs);
    spa_villes_semer(depart, b, 128, T, 0.5f);                                   // V = 1.2 (flou + 0.5 points)
    for (int i = 0; i < 16384; i++) {
      const float V = fminf(1.2f * b[i] / 2048.0f, 3.0f);
      dest[i] = (uint8_t)(255 * sqrtf(V / 3) + 0.5f);
    }
  }
  uint16_t *b64 = b;                                                             // la lueur de loin, a demi-resolution
  for (int T = 0; T < 2; T++) {
    memset(b64, 0, 4096 * sizeof(uint16_t));
    spa_villes_semer(depart, b64, 64, T, 0.25f);
    spa_flou_tore(b64, 64, e.rangs);
    float mx = 1e-6f;
    for (int i = 0; i < 4096; i++) mx = fmaxf(mx, 1.6f * b64[i] / 2048.0f);
    uint8_t *dest = T ? e.lw : e.lo;
    for (int i = 0; i < 4096; i++) dest[i] = (uint8_t)(255 * sqrtf(1.6f * b64[i] / 2048.0f / mx) + 0.5f);
    (T ? e.lw_k : e.lo_k) = mx;
  }
  graine ^= depart;
  brume_n(b, 128, 6);                                                            // les grands nuages, moyennes 2 x 2
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const uint16_t *q = b + (2 * y) * 128 + 2 * x;
      e.na[y * 64 + x] = (uint8_t)((q[0] + q[1] + q[128] + q[129]) / (4.0f * 257) + 0.5f);
    }
  brume_n(b, 128, 3);
  for (int i = 0; i < 16384; i++) e.nb[i] = (uint8_t)(b[i] / 257.0f + 0.5f);
  SpaOrbitePx &px = e.u.px;                                                      // ou chaque pixel tombe sur le sol
  for (int i = 0; i < 4096; i++) {
    const int x = i & 63, y = i >> 6;
    const float dx = x - SPA_O_CX, dy = y - SPA_O_CY, rho = sqrtf(dx * dx + dy * dy);
    px.u[i] = (int16_t)roundf(0.9f * SPA_O_R * atan2f(dy, dx) * 64);
    px.rho[i] = (uint16_t)roundf(rho * 256);
    if (y >= SPA_O_SOL0) {
      const float recul = SPA_O_R * (SPA_PI / 2 - asinf(borne(rho / SPA_O_R, 0, 1)));
      px.recul[(y - SPA_O_SOL0) * 64 + x] = (uint16_t)roundf(0.9f * recul * 256);
    }
  }
  for (int k = 0; k <= 256; k++) {                                               // l'atmosphere en couches
    const float h = k * 0.25f;
    float *o = px.hl[k];
    o[0] = expf(-h / 1.1f) * 0.8f;
    o[1] = expf(-((h - 3.0f) / 0.9f) * ((h - 3.0f) / 0.9f));
    int j = 0;
    while (j < 4 && h > SPA_O_COUCHES[j + 1][0]) j++;
    const float q = borne((h - SPA_O_COUCHES[j][0]) / (SPA_O_COUCHES[j + 1][0] - SPA_O_COUCHES[j][0]), 0, 1), ex = expf(-h / 5.0f);
    for (int c = 0; c < 3; c++) o[2 + c] = (SPA_O_COUCHES[j][c + 1] + (SPA_O_COUCHES[j + 1][c + 1] - SPA_O_COUCHES[j][c + 1]) * q) * ex;
    o[5] = expf(-h / 10.0f);
  }
}
void s_orbite(int humeur, bool debut, float t, float ecoule, float dt) {
  E_orbite &e = etat_ecran<E_orbite>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float R = SPA_O_R;
  if (debut) {
    spa_orbite_preparer(e);
    spa_semer_etoiles(e.et, 0, 35);
  }
  SpaOrbitePx &px = e.u.px;
  const float kc = spa_mod(t / SPA_O_CYCLE, 1);
  const float aube = powf(0.5f - 0.5f * cosf(PI2 * kc), 1.6f);                 // 0 : la nuit ; 1 : le soleil est la
  for (int i = 0; i < 4096; i++) peindre(i >> 6, i & 63, 2, 2, 6);
  spa_etoiles(e.et, t, 1.0f - 0.6f * aube, 0.25f);
  const float w0 = 0.12f + 0.2f * aube, w1 = 0.1f + 0.32f * aube, w3 = 0.25f + 0.4f * aube;
  for (int b = 0; b <= 256; b++) {
    const float da = SPA_O_DA0 + b * SPA_O_DAS;
    float *o = px.al[b];
    o[0] = spa_exp(-(da / w0) * (da / w0)) * aube;                               // pres de l'aube, au sol
    o[1] = spa_exp(-(da / w1) * (da / w1)) * aube;                               // l'aube, couchee sur le limbe
    o[2] = 0.6f + 0.4f * spa_exp(-(da / 0.07f) * (da / 0.07f));
    o[3] = spa_exp(-(da / w3) * (da / w3)) * aube * 0.35f;
  }
  const float leve = borne((aube - 0.62f) / 0.38f, 0, 1);                       // le soleil sort du limbe
  const float rs = R - 2.6f + 3.8f * leve, sx = SPA_O_CX + cosf(SPA_O_AUBE) * rs, sy = SPA_O_CY + sinf(SPA_O_AUBE) * rs;
  const float pente = tanf(SPA_O_AUBE + SPA_PI / 2);
  const float defil = spa_mod(t * 1.6f, 128), dna = spa_mod(t * 0.2f, 128);   // le sol vient du limbe vers nous
  const float kv = 3.0f / 65025, klo = e.lo_k / 65025, klw = e.lw_k / 65025;
  const float *tO = SPA_O_TEINTES[0], *tW = SPA_O_TEINTES[1];
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      float *p = scene[y][x];
      const float rho = px.rho[i] * (1.0f / 256), uu = px.u[i] * (1.0f / 64);
      const float fa = borne((uu / (0.9f * R) - SPA_O_AUBE - SPA_O_DA0) / SPA_O_DAS, 0, 255.999f);
      const int ia = (int)fa;
      const float qa = fa - ia;
      float a[4];
      for (int c = 0; c < 4; c++) a[c] = px.al[ia][c] + (px.al[ia + 1][c] - px.al[ia][c]) * qa;
      const float limbe = borne(R - rho + 0.5f, 0, 1), cie = borne(rho - R + 0.5f, 0, 1);
      if (limbe > 0 && y >= SPA_O_SOL0) {                                        // la Terre, cote nuit
        const float recul = px.recul[(y - SPA_O_SOL0) * 64 + x] * (1.0f / 256), v = recul - defil;
        float VO, VW, LO, LW;
        spa_lire_paire(e.vo, e.vw, 128, uu, v, VO, VW);
        spa_lire_paire(e.lo, e.lw, 64, (uu - 0.5f) * 0.5f, (v - 0.5f) * 0.5f, LO, LW);
        VO *= kv; VW *= kv; LO *= klo; LW *= klw;
        const float q2 = 1 - (rho / R) * (rho / R), cos_t = q2 > 0 ? sqrtf(q2) : 0.0f;
        const float net = fminf(cos_t / 0.55f, 1.0f), vq = fminf(cos_t * 2.2f, 1.0f), voile = vq * sqrtf(vq);
        const float nav = spa_lire8(e.na, 64, (uu * 0.8f + dna - 0.5f) * 0.5f, (v * 0.8f - 0.5f) * 0.5f);
        const float nbv = spa_lire8(e.nb, 128, uu * 1.3f, v * 1.3f + 50);
        const float nuage = borne((nav * 0.75f + nbv * 0.25f - 0.47f) * 3.2f, 0, 1);
        const float pa = a[0], ru = recul / 0.9f;
        const float sol = spa_exp(-ru / 14), brume = spa_exp(-ru / 1.6f);
        const float base[3] = {3, 5, 11}, n1[3] = {14, 17, 26}, n2[3] = {150, 90, 70}, b1[3] = {12, 27, 66}, b2[3] = {120, 120, 160};
        for (int c = 0; c < 3; c++) {
          const float villes = fminf(tO[c] * VO + tW[c] * VW, 255.0f), flou = tO[c] * LO + tW[c] * LW;
          const float lum = villes * net + flou * (1 - net);
          float terre = base[c] + (lum * (1 - 0.88f * nuage) + flou * nuage * 0.45f) * voile;   // sous les nuages
          terre += nuage * (n1[c] * (1 - pa) + n2[c] * pa * sol);
          terre += brume * (b1[c] + b2[c] * pa);
          p[c] += (terre - p[c]) * limbe;
        }
      }
      if (cie > 0) {                                                             // la fine ligne bleue, l'aube sur le limbe
        const float fh = fminf(fmaxf(rho - R, 0.0f) * 4, 255.999f);
        const int ih = (int)fh;
        const float qh = fh - ih;
        float hv[6];
        for (int c = 0; c < 6; c++) hv[c] = px.hl[ih][c] + (px.hl[ih + 1][c] - px.hl[ih][c]) * qh;
        const float bande = a[1] * cie, li = hv[0] * cie * (1 - 0.7f * bande), ve = hv[1] * cie * (1 - aube);
        const float co = bande * a[2], hb = a[3] * hv[5] * cie;
        p[0] += li * 27 + ve * 18 + co * hv[2] + hb * 60;
        p[1] += li * 63 + ve * 48 + co * hv[3] + hb * 100;
        p[2] += li * 153 + ve * 24 + co * hv[4] + hb * 210;
      }
      if (leve > 0) {                                                            // le soleil, son halo, son trait
        const float ddx = x - sx, ddy = y - sy;
        float k = 0;
        if (cie > 0) {
          const float d = sqrtf(ddx * ddx + ddy * ddy);
          const float disque = borne(2.6f - d, 0, 1) * cie;
          if (disque > 0) { p[0] += (255 - p[0]) * disque; p[1] += (245 - p[1]) * disque; p[2] += (215 - p[2]) * disque; }
          k = (d < 26 ? spa_exp(-d / 2.2f) * 0.8f : 0.0f) + spa_exp(-d / 9.0f) * 0.3f;
          k *= leve * cie;
        }
        const float arg = -fabsf(ddy - ddx * pente) * 1.2f - fabsf(ddx) / 14;
        if (arg > -12) k += spa_exp(arg) * leve * 0.45f;
        p[0] += k * 255; p[1] += k * 225; p[2] += k * 170;
      }
    }
}

// ===== 8. des constellations (_scene_constellations) ==========================================

struct SpaModele { int n; float p[10][2]; int nt; int8_t tr[10][2]; float largeur; };
const SpaModele SPA_FIGURES[9] = {
    {7, {{0.0f, 0.18f}, {0.19f, 0.06f}, {0.35f, 0.1f}, {0.5f, 0.22f}, {0.55f, 0.5f}, {0.88f, 0.56f}, {0.93f, 0.25f}},
     7, {{0, 1}, {1, 2}, {2, 3}, {3, 4}, {4, 5}, {5, 6}, {6, 3}}, 34},                                   // la Grande Ourse
    {5, {{0.0f, 0.25f}, {0.24f, 0.68f}, {0.5f, 0.4f}, {0.74f, 0.78f}, {1.0f, 0.3f}}, 4, {{0, 1}, {1, 2}, {2, 3}, {3, 4}}, 30},   // Cassiopee
    {8, {{0.22f, 0.12f}, {0.47f, 0.0f}, {0.76f, 0.16f}, {0.38f, 0.52f}, {0.5f, 0.49f}, {0.62f, 0.46f}, {0.28f, 0.95f}, {0.82f, 0.9f}},
     8, {{0, 1}, {1, 2}, {2, 5}, {5, 4}, {4, 3}, {3, 0}, {3, 6}, {5, 7}}, 26},                           // Orion
    {8, {{0.5f, 0.0f}, {0.5f, 0.33f}, {0.5f, 0.62f}, {0.52f, 1.0f}, {0.1f, 0.22f}, {0.27f, 0.27f}, {0.75f, 0.42f}, {0.95f, 0.5f}},
     7, {{0, 1}, {1, 2}, {2, 3}, {4, 5}, {5, 1}, {1, 6}, {6, 7}}, 26},                                   // le Cygne
    {5, {{0.5f, 0.0f}, {0.32f, 0.3f}, {0.62f, 0.32f}, {0.25f, 0.85f}, {0.58f, 0.92f}},
     6, {{0, 1}, {0, 2}, {1, 2}, {1, 3}, {3, 4}, {4, 2}}, 18},                                           // la Lyre
    {7, {{0.0f, 0.55f}, {0.12f, 0.2f}, {0.3f, 0.02f}, {0.5f, 0.0f}, {0.7f, 0.05f}, {0.86f, 0.22f}, {1.0f, 0.5f}},
     6, {{0, 1}, {1, 2}, {2, 3}, {3, 4}, {4, 5}, {5, 6}}, 22},                                           // la Couronne boreale
    {10, {{0.0f, 0.0f}, {0.08f, 0.22f}, {0.2f, 0.4f}, {0.32f, 0.55f}, {0.42f, 0.72f}, {0.58f, 0.85f}, {0.76f, 0.88f},
          {0.9f, 0.78f}, {0.95f, 0.62f}, {0.86f, 0.55f}},
     9, {{0, 1}, {1, 2}, {2, 3}, {3, 4}, {4, 5}, {5, 6}, {6, 7}, {7, 8}, {8, 9}}, 30},                   // le Scorpion
    {6, {{0.05f, 0.1f}, {0.7f, 0.0f}, {0.75f, 0.62f}, {0.1f, 0.68f}, {0.95f, 0.95f}, {0.0f, 0.98f}},
     6, {{0, 1}, {1, 2}, {2, 3}, {3, 0}, {2, 4}, {3, 5}}, 30},                                           // Pegase
    {8, {{0.0f, 0.6f}, {0.2f, 0.35f}, {0.42f, 0.42f}, {0.55f, 0.2f}, {0.8f, 0.0f}, {1.0f, 0.25f}, {0.88f, 0.62f}, {0.62f, 0.7f}},
     8, {{0, 1}, {1, 2}, {2, 3}, {3, 4}, {4, 5}, {2, 7}, {7, 6}, {6, 5}}, 32}};                          // le Lion
const float SPA_K_PLUME = 6.0f, SPA_K_TENUE = 10.0f, SPA_K_FONDU = 4.0f;

struct SpaFigure { int modele; float x[10], y[10], L[10], eclat[10], phase[10]; float age, fin, cx, cy; };
struct E_constellations {
  uint16_t voile[128 * 128];
  float fig[4096];                         // la figure en cours (en poids : tout y a la couleur du trait)
  SpaFigure f[3];
  int nf;
  int8_t ordre[9];
  int no;
  SpaEtoiles<140> et;
};
// la constellation suivante (dans l'ordre melange), loin de la precedente
void spa_constellation_neuve(E_constellations &e, SpaFigure &f, bool ailleurs, float ax, float ay) {
  if (e.no == 0) {
    for (int i = 0; i < 9; i++) e.ordre[i] = (int8_t)i;
    for (int i = 8; i > 0; i--) {
      const int j = (int)(aleatoire() % (uint32_t)(i + 1));
      const int8_t q = e.ordre[i]; e.ordre[i] = e.ordre[j]; e.ordre[j] = q;
    }
    e.no = 9;
  }
  f.modele = e.ordre[--e.no];
  const SpaModele &m = SPA_FIGURES[f.modele];
  const float a = hasard(-0.35f, 0.35f), ca = cosf(a), sa = sinf(a);
  float lox = 1e9f, loy = 1e9f, hix = -1e9f, hiy = -1e9f;
  for (int k = 0; k < m.n; k++) {
    const float x = m.p[k][0] - 0.5f, y = m.p[k][1] - 0.5f;
    f.x[k] = (x * ca - y * sa) * m.largeur;
    f.y[k] = (x * sa + y * ca) * m.largeur;
    lox = fminf(lox, f.x[k]); hix = fmaxf(hix, f.x[k]); loy = fminf(loy, f.y[k]); hiy = fmaxf(hiy, f.y[k]);
  }
  float cx = 32, cy = 32;
  for (int essai = 0; essai < 12; essai++) {                                     // loin de la precedente, dans le cadre
    cx = hasard(5 - lox, 59 - hix);
    cy = hasard(5 - loy, 56 - hiy);
    if (!ailleurs || hypotf(cx - ax, cy - ay) > 18) break;
  }
  float total = 0;
  for (int k = 0; k < m.n; k++) {
    f.x[k] += cx; f.y[k] += cy;
    f.eclat[k] = 0.6f + 0.4f * hasard(0, 1);
    f.phase[k] = hasard(0, PI2);
  }
  for (int k = 0; k < m.nt; k++) {
    const int i = m.tr[k][0], j = m.tr[k][1];
    f.L[k] = hypotf(f.x[j] - f.x[i], f.y[j] - f.y[i]);
    total += f.L[k];
  }
  f.cx = cx; f.cy = cy;
  f.age = 0;
  f.fin = 2.0f + total / SPA_K_PLUME + SPA_K_TENUE;                            // dessinee, puis tenue : alors elle s'efface
}
// un point du trait, en poids, a la facon de _espace_tacher(net = 2.5)
inline void spa_fig_point(float *fig, float y, float x, float k, int box[4]) {
  if (!(y > -1.0f && y < 64.0f && x > -1.0f && x < 64.0f)) return;
  const int x0 = spa_plancher(x), y0 = spa_plancher(y);
  const float fx = spa_net(x - x0, 25), fy = spa_net(y - y0, 25);
  const float w[4] = {(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy};
  for (int q = 0; q < 4; q++) {
    const int yy = y0 + (q >> 1), xx = x0 + (q & 1);
    if ((unsigned)yy >= 64u || (unsigned)xx >= 64u) continue;
    fig[yy * 64 + xx] += w[q] * k;
    if (yy < box[0]) box[0] = yy;
    if (yy > box[1]) box[1] = yy;
    if (xx < box[2]) box[2] = xx;
    if (xx > box[3]) box[3] = xx;
  }
}
void s_constellations(int humeur, bool debut, float t, float ecoule, float dt) {
  E_constellations &e = etat_ecran<E_constellations>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    brume_n(e.voile, 128, 10);
    spa_semer_etoiles(e.et);
    e.no = 0;
    spa_constellation_neuve(e, e.f[0], false, 0, 0);
    e.f[0].age = 5.0f;                                                           // elle a deja commence
    e.nf = 1;
  }
  const float pas = fminf(dt, 0.5f);
  for (int i = 0; i < e.nf; i++) e.f[i].age += pas;
  const SpaFigure &der = e.f[e.nf - 1];
  if (der.age >= der.fin - 1.0f && e.nf < 3) {                                   // la suivante commence quand celle-ci s'efface
    const float ax = der.cx, ay = der.cy;
    spa_constellation_neuve(e, e.f[e.nf], true, ax, ay);
    e.nf++;
  }
  int garde = 0;
  for (int i = 0; i < e.nf; i++)
    if (e.f[i].age < e.f[i].fin + SPA_K_FONDU) e.f[garde++] = e.f[i];
  e.nf = garde;
  const float ox = t * 0.05f;
  for (int y = 0; y < 64; y++) {
    const float q = y / 64.0f, g0 = 3 + 7 * q, g1 = 4 + 7 * q, g2 = 16 + 16 * q;
    for (int x = 0; x < 64; x++) {
      const float v = fenetre_n(e.voile, 128, ox, 0, x, y), w = v * v * 14;   // un voile a peine
      peindre(y, x, g0 + w * 0.6f, g1 + w * 0.6f, g2 + w);
    }
  }
  spa_etoiles(e.et, t, 0.95f, 0.3f);
  float force[3];
  for (int n = 0; n < e.nf; n++) {                                               // leurs etoiles, un peu plus vives
    const SpaFigure &f = e.f[n];
    const SpaModele &m = SPA_FIGURES[f.modele];
    const float a = f.age, sortie = borne((f.fin + SPA_K_FONDU - a) / SPA_K_FONDU, 0, 1);
    force[n] = borne(a / 2.0f, 0, 1) * sortie;
    const float ka = borne(a / 1.5f, 0, 1) * sqrtf(sortie);
    for (int k = 0; k < m.n; k++) {
      const float l = (0.55f + 0.45f * force[n]) * f.eclat[k] * (0.85f + 0.15f * spa_sin(t * 1.7f + f.phase[k])) * ka;
      const float c0 = 235 * l, c1 = 238 * l, c2 = 255 * l, yy = f.y[k] + 0.5f, xx = f.x[k] + 0.5f;
      pointer(yy, xx, c0, c1, c2);
      pointer(yy, xx + 1, c0 * 0.3f, c1 * 0.3f, c2 * 0.3f);
      pointer(yy, xx - 1, c0 * 0.3f, c1 * 0.3f, c2 * 0.3f);
      pointer(yy + 1, xx, c0 * 0.3f, c1 * 0.3f, c2 * 0.3f);
      pointer(yy - 1, xx, c0 * 0.3f, c1 * 0.3f, c2 * 0.3f);
    }
  }
  for (int n = 0; n < e.nf; n++) {                                               // les traits, d'une etoile a l'autre
    const SpaFigure &f = e.f[n];
    const SpaModele &m = SPA_FIGURES[f.modele];
    float fait = fmaxf(0.0f, f.age - 2.0f) * SPA_K_PLUME;                       // la longueur deja tracee
    if (fait <= 0) continue;
    int box[4] = {64, -1, 64, -1};
    for (int k = 0; k < m.nt && fait > 0; k++, fait -= f.L[k - 1]) {
      const int i = m.tr[k][0], j = m.tr[k][1];
      const float L = f.L[k], kk = fminf(1.0f, fait / L);
      const int nq = (int)(L * 3) > 2 ? (int)(L * 3) : 2;
      const float lim = 0.12f + 0.76f * kk + 1e-6f;                              // le trait s'arrete un peu avant les etoiles
      float ly = 0, lx = 0;
      bool un = false;
      for (int s = 0; s < nq; s++) {
        const float q = 0.12f + 0.76f * s / (nq - 1);
        if (q > lim) break;
        ly = f.y[i] + (f.y[j] - f.y[i]) * q;
        lx = f.x[i] + (f.x[j] - f.x[i]) * q;
        spa_fig_point(e.fig, ly, lx, 0.4f, box);
        un = true;
      }
      if (un && kk < 1) spa_tacher(ly, lx, 200 * force[n], 220 * force[n], 255 * force[n]);   // la pointe du trait, qui brille
    }
    for (int y = box[0]; y <= box[1]; y++)
      for (int x = box[2]; x <= box[3]; x++) {
        float &w = e.fig[y * 64 + x];
        const float k = fminf(w, 0.46f) * force[n];
        w = 0;
        scene[y][x][0] += k * 140; scene[y][x][1] += k * 170; scene[y][x][2] += k * 245;
      }
  }
}
