// lot_neufs.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
// « Le ciel, la mer et ses betes » (la grande meduse, la manta, la tortue, la mer
// de nuages, le hublot, l'arc-en-ciel, le lever de lune) et « les grands
// paysages » (les herbes, la plaine, la montagne, la savane, les eoliennes, les
// montgolfieres, le voilier, la foret, le jardin zen). Les passages des betes et
// le cycle du lever de lune se calent sur `ecoule`, comme en numpy.
#pragma once

// ===========================================================================
// LES OUTILS DU LOT (prefixe nf_)

const float NF_PI = 3.14159265f;

// un sinus rapide (polynome de degre 9, ~4e-6 pres) pour les boucles chaudes
static inline float nf_sin(float x) {
  x -= PI2 * floorf(x * (1.0f / PI2) + 0.5f);
  if (x > 1.5707963f) x = NF_PI - x;
  else if (x < -1.5707963f) x = -NF_PI - x;
  const float x2 = x * x;
  return x * (1 + x2 * (-0.16666667f + x2 * (0.0083333310f + x2 * (-0.00019840874f + x2 * 2.7525562e-6f))));
}
static inline float nf_cos(float x) { return nf_sin(x + 1.5707963f); }

// une exponentielle rapide (~2e-4 pres en relatif) pour les boucles chaudes
static inline float nf_exp(float x) {
  if (x < -80.0f) return 0.0f;
  if (x > 80.0f) x = 80.0f;
  const float kx = x * 1.44269504f;
  const float n = floorf(kx);
  const float f = kx - n;
  const float p = 1 + f * (0.69314718f + f * (0.24022651f + f * (0.05550411f + f * (0.00961813f + f * 0.00133336f))));
  const uint32_t bits = (uint32_t)((int)n + 127) << 23;
  float deux;
  memcpy(&deux, &bits, 4);
  return p * deux;
}

// p = p*(1-a) + couleur*a
static inline void nf_melanger(int y, int x, float a, float r, float g, float b) {
  float *p = scene[y][x];
  p[0] += (r - p[0]) * a;
  p[1] += (g - p[1]) * a;
  p[2] += (b - p[2]) * a;
}

// _ciel_mer_tache / _paysages_points : un point pose entre les pixels, reparti sur ses quatre voisins
void nf_tache(float yf, float xf, float r, float g, float b) {
  if (!(yf > -1.0f && yf < 64.0f && xf > -1.0f && xf < 64.0f)) return;
  const float y0 = floorf(yf), x0 = floorf(xf);
  const float fy = yf - y0, fx = xf - x0;
  const int yi = (int)y0, xi = (int)x0;
  const float w[4] = {(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx};
  for (int k = 0; k < 4; k++) {
    const int yy = yi + (k >> 1), xx = xi + (k & 1);
    if (yy >= 0 && yy < 64 && xx >= 0 && xx < 64) ajouter(yy, xx, w[k], r, g, b);
  }
}

// _ciel_mer_palette / _paysages_nuancier : une couleur le long d'une palette (np.interp, borne aux bouts)
void nf_palette(float k, int n, const float *cles, const float (*c)[3], float &r, float &g, float &b) {
  if (!(k > cles[0])) { r = c[0][0]; g = c[0][1]; b = c[0][2]; return; }
  for (int i = 1; i < n; i++)
    if (k < cles[i]) {
      const float f = (k - cles[i - 1]) / (cles[i] - cles[i - 1]);
      r = c[i - 1][0] + (c[i][0] - c[i - 1][0]) * f;
      g = c[i - 1][1] + (c[i][1] - c[i - 1][1]) * f;
      b = c[i - 1][2] + (c[i][2] - c[i - 1][2]) * f;
      return;
    }
  r = c[n - 1][0]; g = c[n - 1][1]; b = c[n - 1][2];
}

// _ciel_mer_lire / _paysages_lire : un champ qui se raccorde, lu n'importe ou (taille : une puissance de 2)
static inline float nf_lire(const uint16_t *c, int taille, float fy, float fx) {
  const float y0 = floorf(fy), x0 = floorf(fx);
  const float ay = fy - y0, ax = fx - x0;
  const int m = taille - 1;
  const int yi = (int)y0 & m, xi = (int)x0 & m, yj = (yi + 1) & m, xj = (xi + 1) & m;
  const float a = c[yi * taille + xi], b = c[yi * taille + xj], d = c[yj * taille + xi], f = c[yj * taille + xj];
  return ((a * (1 - ax) + b * ax) * (1 - ay) + (d * (1 - ax) + f * ax) * ay) * (1.0f / 65535.0f);
}
// la meme chose pour un champ de flottants 64 x 64
static inline float nf_lire64(const float *c, float fy, float fx) {
  const float y0 = floorf(fy), x0 = floorf(fx);
  const float ay = fy - y0, ax = fx - x0;
  const int yi = (int)y0 & 63, xi = (int)x0 & 63, yj = (yi + 1) & 63, xj = (xi + 1) & 63;
  return (c[yi * 64 + xi] * (1 - ax) + c[yi * 64 + xj] * ax) * (1 - ay) + (c[yj * 64 + xi] * (1 - ax) + c[yj * 64 + xj] * ax) * ay;
}

// _paysages_sous : sous la crete (une hauteur par colonne), le bord adouci ; force : l'opacite
void nf_sous(const float *crete, float r, float g, float b, float force = 1.0f) {
  for (int x = 0; x < 64; x++) {
    const float c0 = crete[x];
    if (!(c0 < 64.5f)) continue;
    for (int y = max(0, (int)floorf(c0 - 0.5f)); y < 64; y++) {
      const float c = borne(y - c0 + 0.5f, 0, 1) * force;
      if (c > 0) nf_melanger(y, x, c, r, g, b);
    }
  }
}

// _paysages_traits : des traits adoucis (y0, x0, y1, x1, demi-largeur au depart, a l'arrivee), d'une couleur ;
// le plus couvrant l'emporte. Avec `masque` (64 x 64), la couverture s'y pose au lieu de la scene.
void nf_traits(const float (*tr)[6], int n, float r, float g, float b, float force = 1.0f, float *masque = nullptr) {
  float ya = 1e9f, yb = -1e9f, xa = 1e9f, xb = -1e9f, marge = 0;
  for (int i = 0; i < n; i++) {
    ya = fminf(ya, fminf(tr[i][0], tr[i][2])); yb = fmaxf(yb, fmaxf(tr[i][0], tr[i][2]));
    xa = fminf(xa, fminf(tr[i][1], tr[i][3])); xb = fmaxf(xb, fmaxf(tr[i][1], tr[i][3]));
    marge = fmaxf(marge, fmaxf(tr[i][4], tr[i][5]));
  }
  marge += 1.5f;
  const int y0 = (int)fmaxf(0.0f, floorf(ya - marge)), y1 = (int)fminf(64.0f, ceilf(yb + marge) + 1);
  const int x0 = (int)fmaxf(0.0f, floorf(xa - marge)), x1 = (int)fminf(64.0f, ceilf(xb + marge) + 1);
  if (y0 >= y1 || x0 >= x1) return;
  float dx[16], dy[16], inv[16], bya[16], byb[16], bxa[16], bxb[16];
  for (int i = 0; i < n && i < 16; i++) {
    dx[i] = tr[i][3] - tr[i][1]; dy[i] = tr[i][2] - tr[i][0];
    inv[i] = 1.0f / (dx[i] * dx[i] + dy[i] * dy[i] + 1e-9f);
    const float m = fmaxf(tr[i][4], tr[i][5]) + 0.5f;    // au-dela, ce trait ne couvre rien
    bya[i] = fminf(tr[i][0], tr[i][2]) - m; byb[i] = fmaxf(tr[i][0], tr[i][2]) + m;
    bxa[i] = fminf(tr[i][1], tr[i][3]) - m; bxb[i] = fmaxf(tr[i][1], tr[i][3]) + m;
  }
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) {
      float c = 0;
      for (int i = 0; i < n && i < 16; i++) {
        if (y < bya[i] || y > byb[i] || x < bxa[i] || x > bxb[i]) continue;
        const float ex = x - tr[i][1], ey = y - tr[i][0];
        const float u = borne((ex * dx[i] + ey * dy[i]) * inv[i], 0, 1);
        const float px = ex - u * dx[i], py = ey - u * dy[i];
        const float v = tr[i][4] + (tr[i][5] - tr[i][4]) * u + 0.5f - sqrtf(px * px + py * py);
        if (v > c) c = v;
      }
      if (c <= 0) continue;
      c = fminf(c, 1.0f) * force;
      if (masque) masque[y * 64 + x] += (1 - masque[y * 64 + x]) * c;
      else nf_melanger(y, x, c, r, g, b);
    }
}

// _paysages_brins : un echantillon de trait presque vertical, pose dans une couverture (le plus couvrant l'emporte)
static inline void nf_brin(float *couv, float xs, float ys, float demi, float pente) {
  if (!(ys > -0.5f && ys < 63.5f && xs > -3.0f && xs < 67.0f)) return;
  const float ap = fabsf(pente) * 0.5f;
  const float a = xs - demi - ap, b = xs + demi + ap;
  const float dens = fminf(1.0f, 2 * demi * sqrtf(1 + pente * pente) / (b - a));
  const int ligne = (int)rintf(ys);
  if (ligne < 0 || ligne > 63) return;
  const int j0 = (int)floorf(xs);
  for (int k = -2; k <= 2; k++) {
    const int j = j0 + k;
    if (j < 0 || j > 63) continue;
    const float part = borne(fminf(j + 0.5f, b) - fmaxf(j - 0.5f, a), 0, 1) * dens;
    if (part > 0.01f && part > couv[ligne * 64 + j]) couv[ligne * 64 + j] = part;
  }
}

// _paysages_cimes : une ligne d'arbres au-dessus du sol `base` (sapins en pointe, ou feuillus en boule)
void nf_cimes(int n, const float *base, float h0, float h1, float pente, bool ronds, float *sortie) {
  for (int x = 0; x < 64; x++) sortie[x] = base[x];
  for (int i = 0; i < n; i++) {
    const float xi = hasard(-4, 68), hi = hasard(h0, h1);
    const float pied = base[(int)borne(xi, 0, 63)];
    for (int x = 0; x < 64; x++) {
      float c;
      if (ronds) {
        const float r = hi * 1.1f, dx = x - xi;
        if (fabsf(dx) >= r) continue;
        c = pied - hi * sqrtf(fmaxf(0.0f, 1 - (dx / r) * (dx / r)));
      } else {
        c = pied - hi + fabsf(x - xi) * pente;
      }
      if (c < sortie[x]) sortie[x] = c;
    }
  }
}

// un hasard gaussien (Box-Muller)
float nf_normal(float sigma) {
  const float u = hasard(1e-7f, 1.0f), v = hasard(0, PI2);
  return sigma * sqrtf(-2.0f * logf(u)) * cosf(v);
}

// ===========================================================================
// LE CIEL, LA MER ET SES BETES

// --- La grande meduse : elle pulse, monte, sort par le haut et revient par le bas ---
// humeurs : 0 = Grande meduse
const float NF_MED_POULS = 3.2f, NF_MED_PAS = 4.8f, NF_MED_TOUR = 18.0f;

void nf_med_battement(float t, float &serre, float &avance, float &elan) {
  const float n = floorf(t / NF_MED_POULS);
  const float ph = t / NF_MED_POULS - n;
  serre = ph < 0.3f ? 0.5f - 0.5f * cosf(NF_PI * ph / 0.3f) : 0.5f + 0.5f * cosf(NF_PI * (ph - 0.3f) / 0.7f);
  const float g = fminf(ph, 0.45f);
  const float poussee = g / 2 - 0.45f / (4 * NF_PI) * sinf(PI2 * g / 0.45f);
  avance = (fmodf(n, NF_MED_TOUR) + (0.25f * ph + 1.75f * poussee) / 0.64375f) * NF_MED_PAS;
  if (ph < 0.45f) { const float s = sinf(NF_PI * ph / 0.45f); elan = s * s; } else elan = 0;
}
static inline float nf_med_x(float t) { return 32 + 6.0f * sinf(t * 0.07f) + 2.5f * sinf(t * 0.19f + 1.3f); }

struct E_grande_meduse {
  float nx[46], ny[46], nv[46], np[46];
  float fu[11], fl[11], fp[11];
  float bs[30], be[30], bx[30];      // les bras : leur battement en retard
  float fs[43], fe[43], fx[43];      // les tentacules fins
  float halo[64 * 64];
};
void s_grande_meduse(int humeur, bool debut, float t, float ecoule, float dt) {
  E_grande_meduse &e = etat_ecran<E_grande_meduse>(debut);
  (void)humeur;
  if (debut) {
    for (int i = 0; i < 46; i++) { e.nx[i] = hasard(0, 64); e.ny[i] = hasard(0, 64); e.nv[i] = hasard(0.2f, 0.7f); e.np[i] = hasard(0, 6.3f); }
    for (int i = 0; i < 11; i++) { e.fu[i] = hasard(-1.3f, 1.3f); e.fl[i] = hasard(26, 38); e.fp[i] = hasard(0, 6.3f); }
  }
  degrade2(4, 12, 34, 1, 3, 12);
  const float tm = ecoule + 21.0f;                 // son horloge : l'ecran s'ouvre sur elle, deja entree
  float serre, avance, elan;
  nf_med_battement(tm, serre, avance, elan);
  const float tour = NF_MED_TOUR * NF_MED_PAS;
  const float y0 = 78.0f - avance;
  const float xc = nf_med_x(tm);
  const float incl = 0.45f * atan2f(nf_med_x(tm + 0.5f) - nf_med_x(tm - 0.5f), 1.5f);
  const float Wm = 12.5f * (1 - 0.2f * serre), Hm = 12.0f * (1 + 0.12f * serre);
  const float lum = 0.85f + 0.25f * serre;
  const float ca = cosf(incl), sa = sinf(incl);
  for (int i = 0; i < 46; i++) e.ny[i] = fmodf(e.ny[i] + e.nv[i] * dt, 64.0f);
  memset(e.halo, 0, sizeof e.halo);
  float sr, av, er;
  for (int j = 0; j < 30; j++) {
    const float r = tm - j * 0.7f * 0.05f;
    nf_med_battement(r, sr, av, er);
    e.bs[j] = sr; e.be[j] = er; e.bx[j] = nf_med_x(r) - xc;
  }
  for (int j = 0; j < 43; j++) {
    const float r = tm - j * 0.9f * 0.055f;
    nf_med_battement(r, sr, av, er);
    e.fs[j] = sr; e.fe[j] = er; e.fx[j] = nf_med_x(r) - xc;
  }
  static const float BORD[3] = {150, 215, 255}, CORPS[3] = {50, 60, 165}, GONADE[3] = {255, 120, 205};
  static const float BRAS[3] = {235, 120, 245}, FIL[3] = {110, 150, 255};
  const float yc3[3] = {y0, y0 - tour, y0 + tour};
  for (int p = 0; p < 3; p++) {
    const float yc = yc3[p];
    if (yc - Hm - 30 > 64 || yc + 48 < 0) continue;     // (son halo se voit avant elle)
    const float iW = 1 / Wm, iH = 1 / (1.1f * Hm), k5 = Wm / 5;
    for (int y = 0; y < 64; y++) {
      const float dy = y - yc;
      for (int x = 0; x < 64; x++) {
        const float dx = x - xc;
        const float uu = (dx * ca + dy * sa) * iW, vv = (-dx * sa + dy * ca + Hm * 0.3f) * iH;
        e.halo[y * 64 + x] += nf_exp(-fmaxf(sqrtf(uu * uu + vv * vv) - 1, 0.0f) * k5) * lum;
      }
    }
    // l'ombrelle : seulement autour d'elle
    const int ya = max(0, (int)(yc - Hm - 4)), yb = min(64, (int)(yc + 3));
    const int xa = max(0, (int)(xc - Wm - 4)), xb = min(64, (int)(xc + Wm + 5));
    const float S2 = 0.70710678f;
    const float gcos[4] = {S2, -S2, -S2, S2}, gsin[4] = {S2, S2, -S2, -S2};
    for (int y = ya; y < yb; y++)
      for (int x = xa; x < xb; x++) {
        const float dx = x - xc, dy = y - yc;
        const float uu = dx * ca + dy * sa, vv = -dx * sa + dy * ca;
        const float s = borne((vv + Hm) / Hm, 0, 1);
        const float Wl = Wm * (1 - 0.32f * serre * s * s * s);
        const float vh = fminf(vv, 0.0f) / Hm;
        const float rho = sqrtf((uu / Wl) * (uu / Wl) + vh * vh);
        const float couv = borne((1 - rho) * Wm * 0.8f + 0.5f, 0, 1) * borne(0.8f - vv, 0, 1);
        const float fr = (fabsf(vv) < 4.0f && fabsf(uu) < Wl + 0.5f) ? nf_exp(-(vv / 0.9f) * (vv / 0.9f)) * (0.6f + 0.4f * nf_sin(uu * 2.2f)) : 0.0f;
        if (couv <= 0 && fr <= 0) continue;
        float r = fr * lum * 0.9f * BORD[0], g = fr * lum * 0.9f * BORD[1], b = fr * lum * 0.9f * BORD[2];
        if (couv > 0) {
          const float bord = nf_exp(-borne(1 - rho, 0, 1) * Wm / 1.6f);
          const float m = borne(uu / fmaxf(Wl * sqrtf(borne(1 - vh * vh, 0, 1)), 0.5f), -1, 1);
          float mer = 0;
          if (vv < -1) {                       // |cos(6 asin m)|^8, en polynome
            const float c2 = 1 - m * m;
            float c6 = ((32 * c2 - 48) * c2 + 18) * c2 - 1;
            c6 *= c6; c6 *= c6; mer = c6 * c6;
          }
          const float qx = uu / (Wl - 2.2f), qy = fminf(vv + 0.5f, 0.0f) / (Hm - 4.0f);
          const bool creux = qx * qx + qy * qy < 1;
          float gon = 0;
          for (int k = 0; k < 4; k++) {           // les quatre anneaux, en trefle, vus un peu d'en haut
            const float ax = (uu - gcos[k] * 0.36f * Wl) / (0.21f * Wm), ay = (vv + 0.5f * Hm - gsin[k] * 0.15f * Hm) / (0.14f * Hm);
            const float r2 = ax * ax + ay * ay;
            if (r2 > 9) continue;
            const float rg = sqrtf(r2), q = (rg - 1) / 0.45f;
            gon += (nf_exp(-q * q) + 0.3f * nf_exp(-r2)) * (0.8f + 0.2f * gsin[k]);
          }
          gon = fminf(gon, 1.2f) * 0.7f;
          const float kc = (0.55f - (creux ? 0.25f : 0.0f)), kb = bord * 0.95f + mer * 0.18f;
          r += (CORPS[0] * kc + BORD[0] * kb + GONADE[0] * gon) * lum * couv;
          g += (CORPS[1] * kc + BORD[1] * kb + GONADE[1] * gon) * lum * couv;
          b += (CORPS[2] * kc + BORD[2] * kb + GONADE[2] * gon) * lum * couv;
        }
        scene[y][x][0] += r; scene[y][x][1] += g; scene[y][x][2] += b;
      }
    // les bras, frises, au centre ; les tentacules fins, depuis le bord : ils suivent en retard
    static const float BU[4] = {-2.2f, -0.8f, 0.8f, 2.2f};
    for (int j = 0; j < 4; j++)
      for (int i = 0; i < 30; i++) {
        const float ks = i * 0.7f;
        const float ox = e.bx[i] + BU[j] * (1 - 0.25f * e.bs[i]) * (1 + ks * 0.03f) + sinf(ks * 0.42f - t * 1.3f + j * 1.7f) * (0.5f + ks * 0.06f);
        const float larg = 1.1f * (1 - ks / 26), frise = 0.6f + 0.4f * sinf(ks * 1.6f + j + t);
        for (int cote = -1; cote <= 1; cote++) {
          const float o = ox + cote * larg * frise;
          const float xx = xc + o * ca - (ks - 2) * sa, yy = yc + o * sa + (ks - 2) * ca * (0.95f + 0.1f * e.be[i]);
          const float k = (1 - ks / 23) * (cote ? 0.3f : 0.42f) * lum;
          nf_tache(yy, xx, BRAS[0] * k, BRAS[1] * k, BRAS[2] * k);
        }
      }
    for (int f = 0; f < 11; f++)
      for (int i = 0; i < 43; i++) {
        const float k = i * 0.9f;
        if (k >= e.fl[f]) break;
        const float ox = e.fx[i] + e.fu[f] * Wm / 1.3f * (1 - 0.32f * e.fs[i]) * 0.93f + sinf(k * 0.21f - t * 1.6f + e.fp[f]) * (k / e.fl[f]) * 1.8f;
        const float yy = yc + 0.6f + k * (0.9f + 0.12f * e.fe[i]);
        const float xx = xc + ox * ca - (k + 0.6f) * sa;
        const float c = powf(1 - k / e.fl[f], 1.2f) * 0.5f * lum;
        nf_tache(yy + ox * sa, xx, FIL[0] * c, FIL[1] * c, FIL[2] * c);
      }
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) ajouter(y, x, fminf(e.halo[y * 64 + x], 1.2f), 18, 40, 100);
  // la neige marine, eclairee quand elle passe pres d'elle
  for (int i = 0; i < 46; i++) {
    const float qx = fmodf(e.nx[i] + sinf(t * 0.3f + e.np[i]) * 1.5f + 64.0f, 64.0f);
    const float eclat = borne(nf_lire64(e.halo, e.ny[i], qx) * 3, 0, 1.4f);
    const float k = 0.18f + 0.8f * eclat;
    nf_tache(e.ny[i], qx, 110 * k, 140 * k, 170 * k);
  }
}

// --- La raie manta : elle plane au-dessus du sable, traverse, puis revient ---
// humeurs : 0 = Raie manta
const float NF_MANTA_TRAVERSEE = 40.0f, NF_MANTA_ENVERGURE = 20.0f;

// _ciel_mer_aller_retour : (aller ?, s de 0 a 1 le long du passage)
static bool nf_aller_retour(float t, float traversee, float vif, float &s) {
  const float ph = fmodf(t / traversee, 2.0f);
  const float q = ph - floorf(ph);
  s = q + vif * sinf(PI2 * q) / PI2;
  return ph < 1.0f;
}

// _manta_forme : la distance au bord (> 0 dedans), et s (0 au dos, 1 au bout de l'aile)
static inline float nf_manta_dist(float u, float v, float S, float batt, float souple, bool queue, float &s) {
  const float av = fabsf(v);
  s = fminf(av / S, 1.2f);
  const float onde = 2.0f * nf_sin(batt - 1.3f * s) * s * s;
  const float q = fmaxf(s - 0.15f, 0.0f) / 0.85f;
  const float avant = 6.0f - 12.0f * (q > 0 ? q * nf_exp(0.15f * logf(q)) : 0.0f) + onde;
  const float arriere = -9.0f + 16.0f * s - 13.0f * s * s + onde;
  float dist = fminf(fminf(u - arriere, avant - u), (1 - s) * S * 0.5f);
  const float cornes = fminf(fminf(u - 5.5f, 9.0f - u - (av - 2.8f) * (av - 2.8f) * 0.6f), fminf(av - 1.6f, 3.9f - av));
  dist = fmaxf(dist, cornes);
  if (queue) {
    const float w = u + 8;
    dist = fmaxf(dist, fminf(fminf(u + 19.0f, -8.0f - u), 0.6f + w * 0.02f - fabsf(v - souple * w * w)));
  }
  return dist;
}

struct E_manta {
  uint8_t sable[64 * 64][3];
  float ombre[64 * 64];
  float fx[7], fy[7], fp[7];
};
void s_manta(int humeur, bool debut, float t, float ecoule, float dt) {
  E_manta &e = etat_ecran<E_manta>(debut);
  (void)humeur; (void)dt;
  if (debut) {
    uint16_t *tache = (uint16_t *)e.ombre;        // (un brouillon : l'ombre est refaite a chaque image)
    brume_n(tache, 64, 6);
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float rides = sinf((x * 0.75f + y * 0.42f) * 0.95f + 1.2f * sinf(y * 0.13f + x * 0.05f));
        const float k = 0.9f + 0.08f * rides + 0.18f * (tache[y * 64 + x] / 65535.0f - 0.5f);
        const float q = fminf(sqrtf(((x - 32) / 44.0f) * ((x - 32) / 44.0f) + ((y - 32) / 44.0f) * ((y - 32) / 44.0f)), 1.0f);
        const float bord = q * q;
        const float c[3] = {136 * k * (1 - 0.5f * bord) + 12 * 0.5f * bord, 138 * k * (1 - 0.5f * bord) + 44 * 0.5f * bord,
                            106 * k * (1 - 0.5f * bord) + 74 * 0.5f * bord};
        for (int i = 0; i < 3; i++) e.sable[y * 64 + x][i] = (uint8_t)borne(roundf(c[i]), 0, 255);
      }
    for (int i = 0; i < 7; i++) { e.fx[i] = hasard(-3.5f, 3.5f); e.fy[i] = hasard(-2.5f, 2.5f); e.fp[i] = hasard(0, 6.3f); }
  }
  // la manta : son chemin (aller, retour), son cap, son battement
  float q;
  const bool aller = nf_aller_retour(ecoule + 9.0f, NF_MANTA_TRAVERSEE, 0.35f, q);   // l'ecran s'ouvre sur elle
  float mx, my, dmx, dmy;
  if (aller) {
    mx = -19 + q * 102; my = 30 + 9 * sinf(q * NF_PI * 1.5f + 0.4f);
    dmx = 102.0f; dmy = 9 * NF_PI * 1.5f * cosf(q * NF_PI * 1.5f + 0.4f);
  } else {
    mx = 83 - q * 102; my = 34 - 8 * sinf(q * NF_PI * 1.3f + 0.9f);
    dmx = -102.0f; dmy = -8 * NF_PI * 1.3f * cosf(q * NF_PI * 1.3f + 0.9f);
  }
  const float cap = atan2f(dmy, dmx), cc = cosf(cap), ss = sinf(cap);
  const float batt = t * PI2 / 4.4f;
  const float haut = 1.0f + 0.25f * sinf(t * 0.17f);
  const float sb = sinf(batt), S = NF_MANTA_ENVERGURE * (1 - 0.12f * sb * sb);
  // son ombre sur le sable : decalee, floue
  memset(e.ombre, 0, sizeof e.ombre);
  {
    const float ox = mx + 5.0f * haut, oy = my + 7.0f * haut;
    const int y0 = max(0, (int)(oy - 25)), y1 = min(64, (int)(oy + 25) + 1), x0 = max(0, (int)(ox - 25)), x1 = min(64, (int)(ox + 25) + 1);
    float s;
    for (int y = y0; y < y1; y++)
      for (int x = x0; x < x1; x++) {
        const float u = (x - ox) * cc + (y - oy) * ss, v = -(x - ox) * ss + (y - oy) * cc;
        if (u > 10.7f || u < -13.7f || fabsf(v) > S + 3.3f) continue;
        e.ombre[y * 64 + x] = borne(nf_manta_dist(u, v, S, batt, 0.0f, false, s) / (2.0f + haut) + 0.5f, 0, 1) * 0.62f;
      }
  }
  // le fond : le sable, les caustiques (trois ondes croisees, deformees, plus vives par plaques), les rayons
  float sA1[64], cA1[64], sA2[64], cA2[64], sI[64], cI[64], sP1[64], cP1[64], sP2[64], cP2[64], sR[64], cR[64];
  for (int x = 0; x < 64; x++) {
    sA1[x] = sinf(x * 0.42f + t * 0.6f); cA1[x] = cosf(x * 0.42f + t * 0.6f);
    const float a2 = -0.21f * x + sinf(x * 0.15f - t * 0.4f) * 1.6f - t * 0.5f;
    sA2[x] = sinf(a2); cA2[x] = cosf(a2);
    sI[x] = sinf(x * 0.1f); cI[x] = cosf(x * 0.1f);
    sP1[x] = sinf(x * 0.09f); cP1[x] = cosf(x * 0.09f);
    sP2[x] = sinf(-x * 0.04f); cP2[x] = cosf(-x * 0.04f);
    sR[x] = sinf(x * 0.16f); cR[x] = cosf(x * 0.16f);
  }
  for (int y = 0; y < 64; y++) {
    const float b1 = sinf(y * 0.18f + t * 0.5f) * 1.6f, sB1 = sinf(b1), cB1 = cosf(b1);
    const float sB2 = sinf(0.36f * y), cB2 = cosf(0.36f * y);
    const float sJ = sinf(y * 0.2f + t * 0.3f), cJ = cosf(y * 0.2f + t * 0.3f);
    const float b3 = -0.36f * y + t * 0.45f;
    const float q1 = y * 0.06f + t * 0.12f, sQ1 = sinf(q1), cQ1 = cosf(q1);
    const float q2 = y * 0.11f - t * 0.09f, sQ2 = sinf(q2), cQ2 = cosf(q2);
    const float r1 = -y * 0.1f + t * 0.25f + sinf(y * 0.05f + t * 0.1f) * 2, sRy = sinf(r1), cRy = cosf(r1);
    for (int x = 0; x < 64; x++) {
      const float w1 = sA1[x] * cB1 + cA1[x] * sB1;
      const float w2 = sA2[x] * cB2 + cA2[x] * sB2;
      const float inner = sI[x] * cJ + cI[x] * sJ;
      const float w3 = nf_sin(-0.21f * x + b3 + inner * 1.4f);
      const float w = w1 + w2 + w3;
      const float plaques = 0.5f + 0.5f * (sP1[x] * cQ1 + cP1[x] * sQ1) * (sP2[x] * cQ2 + cP2[x] * sQ2);
      float c = borne(1 - fabsf(w), 0, 1);
      const float caus = c * c * c * plaques;
      float r = 0.5f + 0.5f * (sR[x] * cRy + cR[x] * sRy);
      r = r * r * r; r *= r;
      const float o = e.ombre[y * 64 + x];
      const uint8_t *sb8 = e.sable[y * 64 + x];
      const float kc = caus * (1 - o * 1.3f) * 0.55f;
      peindre(y, x, sb8[0] * (1 - o) + kc * 120 + r * 18, sb8[1] * (1 - o) + kc * 150 + r * 30, sb8[2] * (1 - o) + kc * 120 + r * 30);
    }
  }
  // un petit banc de poissons qui passe, et leur ombre
  const float fq = fmodf(t / 27.0f, 1.0f);
  const float bx = 78 - fq * 100, by = 6 + fq * 46;
  static const float FK[4] = {1.0f, 0.95f, 0.75f, 0.5f};
  for (int i = 0; i < 7; i++) {
    const float px = bx + e.fx[i] * 2.4f + sinf(t * 1.5f + e.fp[i]) * 0.6f;
    const float py = by + e.fy[i] * 1.8f + cosf(t * 1.2f + e.fp[i]) * 0.6f;
    for (int k = 0; k < 4; k++) nf_tache(py - 0.4f * k + 2.0f, px + 0.92f * k + 1.6f, -26 * FK[k], -28 * FK[k], -24 * FK[k]);
    for (int k = 0; k < 4; k++) nf_tache(py - 0.4f * k, px + 0.92f * k, 176 * FK[k], 165 * FK[k], 98 * FK[k]);
  }
  // la manta
  const float souple = 0.004f * sinf(t * 0.9f);
  const int y0 = max(0, (int)(my - 23)), y1 = min(64, (int)(my + 23) + 1), x0 = max(0, (int)(mx - 23)), x1 = min(64, (int)(mx + 23) + 1);
  static const float CLES[3] = {0.0f, 0.45f, 1.0f};
  static const float DOS[3][3] = {{18, 22, 32}, {30, 36, 50}, {46, 54, 70}};
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) {
      const float u = (x - mx) * cc + (y - my) * ss, v = -(x - mx) * ss + (y - my) * cc;
      if (u > 9.6f || u < -19.6f || fabsf(v) > S + 1.0f) continue;
      float s;
      const float dist = nf_manta_dist(u, v, S, batt, souple, true, s);
      const float couv = borne(dist + 0.5f, 0, 1);
      if (couv <= 0) continue;
      const float vague = 1 + 0.4f * nf_sin(batt - 2.2f * s) * s;   // la lumiere qui court sur l'aile qui ondule
      float r, g, b;
      nf_palette(s, 3, CLES, DOS, r, g, b);
      const float bd = borne(1.5f - dist, 0, 1);
      r = r * vague + bd * 36; g = g * vague + bd * 42; b = b * vague + bd * 50;
      const float av = fabsf(v);
      const float corps = borne(1.5f - sqrtf(((u + 1.5f) / 8.0f) * ((u + 1.5f) / 8.0f) + (v / 4.2f) * (v / 4.2f)) * 1.5f, 0, 1);
      const float kc = borne(1 - av * 1.2f, 0, 1) * corps;
      r = r * (1 - 0.3f * corps) + kc * 16; g = g * (1 - 0.3f * corps) + kc * 18; b = b * (1 - 0.3f * corps) + kc * 22;
      if (av > 2.2f) {
        const float eu = (u - 2.2f + (av - 4.0f) * 0.6f) / 1.3f, ev = (av - 5.0f) / 2.6f;
        const float ep = borne(1.3f - sqrtf(eu * eu + ev * ev), 0, 1) * 0.8f;
        r = r * (1 - ep) + 165 * ep; g = g * (1 - ep) + 172 * ep; b = b * (1 - ep) + 178 * ep;
      }
      nf_melanger(y, x, couv, r, g, b);
    }
}

// --- La tortue de mer : elle nage dans le bleu, traverse, puis revient ---
// humeurs : 0 = Tortue de mer
const float NF_TORTUE_TRAVERSEE = 46.0f;

// _tortue_nageoire : la distance au bord d'une nageoire effilee (> 0 dedans), et k (0 a l'epaule, 1 au bout) ;
// renvoie -9 tout de suite quand le point en est loin
static inline float nf_nageoire(float u, float v, float pu, float pv, float ca, float sa, float longueur, float racine,
                                float courbe, float &k) {
  const float du = u - pu, dv = v - pv;
  const float a = -du * ca + dv * sa, b = du * sa + dv * ca;
  k = 0;
  if (a < -1.0f || a > longueur + 0.5f || fabsf(b) > racine + fabsf(courbe) + 1.0f) return -9.0f;
  k = borne(a / longueur, 0, 1);
  const float k6 = k > 0 ? nf_exp(0.6f * logf(k)) : 0.0f;
  const float sn = nf_sin(NF_PI * k6);
  const float demi = 0.45f + racine * (sn > 0 ? nf_exp(0.9f * logf(sn)) : 0.0f);
  return fminf(fminf(a + 0.5f, longueur - a), demi - fabsf(b - courbe * k * k));
}

void nf_tortue_dessin(int y0, int y1, int x0, int x1, float xc, float yc, float sens, float tangage, float batt) {
  const float ca = cosf(tangage), sa = sinf(tangage);
  static const float PEAU[3] = {98, 112, 70}, EC_C[3] = {190, 132, 52}, EC_F[3] = {92, 60, 28}, JOINT[3] = {34, 24, 14};
  const float angle = 0.15f + 0.75f * sinf(batt);
  const float a1 = angle - 0.15f, c1 = cosf(a1), s1 = sinf(a1);
  const float a2 = 0.5f + 0.25f * sinf(batt + 1.0f), c2 = cosf(a2), s2 = sinf(a2);
  const float c3 = cosf(angle), s3 = sinf(angle);
  const float hu = 15.0f, hv = -0.6f + 0.4f * sinf(batt * 0.5f);
  const float L = 12.5f;
  static const float RANGS[3][4] = {{0.0f, 0.34f, 0.37f, 0.0f}, {0.34f, 0.78f, 0.33f, 0.165f}, {0.78f, 1.01f, 0.14f, 0.07f}};
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) {
      const float dx = (x - xc) * sens, dy = y - yc;
      const float u = dx * ca - dy * sa, v = dx * sa + dy * ca;   // dans son repere : u vers l'avant, v vers le bas
      float k, dist, al;
      // la nageoire de l'autre cote, derriere la carapace ; la patte arriere
      dist = nf_nageoire(u, v, 6.0f, -0.5f, c1, s1, 12.0f, 2.0f, 1.4f, k);
      al = borne(dist + 0.5f, 0, 1);
      if (al > 0) nf_melanger(y, x, al, PEAU[0] * 0.55f, PEAU[1] * 0.55f, PEAU[2] * 0.55f);
      dist = nf_nageoire(u, v, -10.0f, 2.2f, c2, s2, 5.5f, 1.5f, 0.6f, k);
      al = borne(dist + 0.5f, 0, 1);
      if (al > 0) nf_melanger(y, x, al, PEAU[0] * 0.85f, PEAU[1] * 0.85f, PEAU[2] * 0.85f);
      // la tete, le cou, l'oeil
      if (u > 8.0f && u < 20.0f && v > hv - 3.5f && v < 3.0f) {
        const float tete = sqrtf(((u - hu) / 3.8f) * ((u - hu) / 3.8f) + ((v - hv) / 2.5f) * ((v - hv) / 2.5f));
        const float cou = fminf(fminf(u - 9.0f, 14.0f - u), 1.9f - fabsf(v - 0.3f));
        al = borne(fmaxf((1 - tete) * 2.5f, cou) + 0.5f, 0, 1);
        if (al > 0) {
          const float kp = 1.15f - 0.3f * borne((v - hv + 2.5f) / 5, 0, 1);
          float r = PEAU[0] * kp, g = PEAU[1] * kp, b = PEAU[2] * kp;
          if (tete < 0.9f && nf_sin(u * 2.2f) * nf_sin(v * 2.4f) > 0.55f) { r = r * 0.6f + 76; g = g * 0.6f + 76; b = b * 0.6f + 56; }
          nf_melanger(y, x, al, r, g, b);
        }
        const float oe = borne(1.0f - sqrtf((u - hu - 1.4f) * (u - hu - 1.4f) + (v - hv + 0.6f) * (v - hv + 0.6f)) / 0.75f, 0, 1);
        if (oe > 0) nf_melanger(y, x, oe, 12, 12, 8);
      }
      // la carapace : un dome, ses ecailles (une rangee sur le dos, une sur les flancs, la bordure)
      if (fabsf(u) < L + 0.5f && v > -8.2f && v < 4.5f) {
        const float a = borne(u / L, -1, 1), q = borne(1 - a * a, 0, 1);
        const float dessus = -7.0f * (q > 0 ? nf_exp(0.55f * logf(q)) : 0.0f) * (1 + 0.08f * a);
        const float dessous = 2.6f * sqrtf(q);
        al = borne(fminf(fminf(v - dessus, dessous - v), (L - fabsf(u)) * 1.2f) + 0.5f, 0, 1);
        if (al > 0) {
          const float hauteur = fmaxf(dessous - dessus, 0.5f);
          const float bb = borne((v - dessus) / hauteur, 0, 1);
          float centre = 0, joint = 0;
          for (int i = 0; i < 3; i++) {
            const float b0 = RANGS[i][0], b1 = RANGS[i][1], largeur = RANGS[i][2], decal = RANGS[i][3];
            if (bb < b0 || bb >= b1) continue;
            const float c = (u / L + decal + 0.09f * (bb - 0.5f)) / largeur;
            const float fr = c - floorf(c);
            const float dj = fminf(fr, 1 - fr) * largeur * L, db = fminf(bb - b0, b1 - bb) * hauteur;
            joint = borne(1.2f - (b0 > 0 ? fminf(dj, db) : dj) * 1.6f, 0, 1);
            centre = (1 - fabsf(fr - 0.5f) * 2) * borne(db / 2.2f, 0, 1);
          }
          const float kb = 1.15f - 0.45f * bb, kj = joint * 0.75f, lu = borne(1.3f - (v - dessus), 0, 1);
          const float r = (EC_F[0] + (EC_C[0] - EC_F[0]) * centre) * kb * (1 - kj) + JOINT[0] * kj + lu * 60;
          const float g = (EC_F[1] + (EC_C[1] - EC_F[1]) * centre) * kb * (1 - kj) + JOINT[1] * kj + lu * 70;
          const float b = (EC_F[2] + (EC_C[2] - EC_F[2]) * centre) * kb * (1 - kj) + JOINT[2] * kj + lu * 50;
          nf_melanger(y, x, al, r, g, b);
        }
        if (fabsf(u) < L - 2) {
          const float pl = borne(fminf(v - dessous + 0.6f, dessous + 1.3f - v) + 0.5f, 0, 1);
          if (pl > 0) nf_melanger(y, x, pl, 175, 160, 98);
        }
      }
      // la nageoire avant, de ce cote : elle bat devant la carapace
      dist = nf_nageoire(u, v, 6.5f, 1.2f, c3, s3, 14.0f, 2.5f, 1.6f, k);
      al = borne(dist + 0.5f, 0, 1);
      if (al > 0) {
        const float kp = 1.1f - 0.35f * k, kd = borne(1.2f - dist, 0, 1);
        float r = PEAU[0] * kp + kd * 40, g = PEAU[1] * kp + kd * 44, b = PEAU[2] * kp + kd * 30;
        if (nf_sin(u * 2.6f + v * 1.1f) * nf_sin(v * 2.9f - u * 0.8f) > 0.5f) { r = r * 0.7f + 54; g = g * 0.7f + 54; b = b * 0.7f + 39; }
        nf_melanger(y, x, al, r, g, b);
      }
    }
}

struct E_tortue {
  float hx[46], hh[46], hp[46], hs[46];
  float bx[9], by[9], bv[9], bp[9];
  float sx[3], sy[3], sp[3], sq[3];
  float ang[64 * 64];                    // l'angle des rayons, vu de leur source
  float pa[16 * 64], ps[16 * 64][3];     // _ciel_mer_peindre, sur les 16 lignes du bas
};
void s_tortue(int humeur, bool debut, float t, float ecoule, float dt) {
  E_tortue &e = etat_ecran<E_tortue>(debut);
  (void)humeur;
  if (debut) {
    for (int i = 0; i < 46; i++) { e.hx[i] = hasard(-2, 66); e.hh[i] = hasard(5, 14); e.hp[i] = hasard(0, 6.3f); e.hs[i] = hasard(0.6f, 1.0f); }
    for (int i = 0; i < 9; i++) { e.bx[i] = hasard(0, 64); e.by[i] = hasard(0, 64); e.bv[i] = hasard(5, 9); e.bp[i] = hasard(0, 6.3f); }
    for (int i = 0; i < 3; i++) { e.sx[i] = 70; e.sy[i] = 70; e.sp[i] = hasard(0, 6.3f); e.sq[i] = ecoule + (i == 0 ? 1.0f : i == 1 ? 1.4f : 1.7f); }
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) e.ang[y * 64 + x] = atan2f(x - 8.0f, y + 46.0f);
  }
  static const float FC[3] = {0.0f, 20.0f, 64.0f};
  static const float FOND[3][3] = {{34, 120, 160}, {14, 70, 112}, {4, 26, 52}};
  for (int y = 0; y < 64; y++) {
    float r, g, b;
    nf_palette(y, 3, FC, FOND, r, g, b);
    const float bas = borne(1.1f - y / 58.0f, 0, 1);
    for (int x = 0; x < 64; x++) {
      const float a = e.ang[y * 64 + x];
      float s = 0.5f + 0.5f * nf_sin(a * 26 + nf_sin(a * 7 + t * 0.23f) * 2.2f + t * 0.12f);
      const float s2 = s * s, s4 = s2 * s2;
      const float k = s4 * s2 * s * bas;
      float rr = r + k * 33, gg = g + k * 60, bb = b + k * 66;
      if (y < 2) {
        const float h = 0.5f + 0.5f * sinf(x * 0.6f + t * 1.5f + sinf(x * 0.17f - t) * 2);
        rr += h * 40; gg += h * 60; bb += h * 60;
      }
      peindre(y, x, rr, gg, bb);
    }
  }
  // l'herbier, au fond : des brins qui ondulent sous une houle lente
  for (int x = 0; x < 64; x++) {
    const float sol = 61.0f + 1.2f * sinf(x * 0.2f) + 0.6f * sinf(x * 0.53f);
    for (int y = 0; y < 64; y++)
      if (y >= sol) peindre(y, x, 16, 40, 46);
  }
  memset(e.pa, 0, sizeof e.pa);
  memset(e.ps, 0, sizeof e.ps);
  for (int i = 0; i < 46; i++) {
    const float p1 = 0.05f * sinf(t * 0.8f - e.hx[i] * 0.09f + e.hp[i] * 0.3f) + 0.012f * sinf(t * 2.1f + e.hp[i]);
    for (int j = 0; j < 18; j++) {
      const float k = j * 0.8f;
      if (k >= e.hh[i]) break;
      const float q = k / e.hh[i];
      const float cr = (22 + 58 * q) * e.hs[i], cg = (64 + 86 * q) * e.hs[i], cb = (44 + 40 * q) * e.hs[i];
      const float yf = 63.5f - k, xf = e.hx[i] + p1 * k * k;
      const float y0 = floorf(yf), x0 = floorf(xf);
      const float fy = yf - y0, fx = xf - x0;
      const float w[4] = {(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx};
      for (int c = 0; c < 4; c++) {
        const int yy = (int)y0 + (c >> 1), xx = (int)x0 + (c & 1);
        if (yy < 48 || yy > 63 || xx < 0 || xx > 63) continue;
        const int n = (yy - 48) * 64 + xx;
        e.pa[n] += w[c]; e.ps[n][0] += w[c] * cr; e.ps[n][1] += w[c] * cg; e.ps[n][2] += w[c] * cb;
      }
    }
  }
  for (int n = 0; n < 16 * 64; n++) {
    if (e.pa[n] <= 0) continue;
    const float couv = fminf(e.pa[n] * 1.3f, 1.0f), inv = 1.0f / fmaxf(e.pa[n], 1e-6f);
    nf_melanger(48 + n / 64, n % 64, couv, e.ps[n][0] * inv, e.ps[n][1] * inv, e.ps[n][2] * inv);
  }
  // la tortue : son chemin, aller puis retour
  float q;
  const bool aller = nf_aller_retour(ecoule + 13.0f, NF_TORTUE_TRAVERSEE, 0.3f, q);   // l'ecran s'ouvre sur elle
  const float sens = aller ? 1.0f : -1.0f;
  const float om = PI2 / 3.8f;
  float xc = aller ? (-21 + q * 106) : (85 - q * 106);
  xc += 0.8f * sinf(t * om - 0.6f) * sens;          // chaque coup de nageoire la pousse un peu
  float yc = aller ? (28 + 4 * sinf(q * NF_PI * 1.4f)) : (34 - 4 * sinf(q * NF_PI * 1.2f + 0.5f));
  yc += 0.5f * sinf(t * om + 1.4f);
  const float tangage = -0.06f * cosf(q * NF_PI * 1.4f) * sens + 0.04f * cosf(t * om + 1.4f);
  const float tete_x = xc + 15.5f * sens, tete_y = yc - 1.0f;
  const int y0 = max(0, (int)(yc - 11)), y1 = min(64, (int)(yc + 19)), x0 = max(0, (int)(xc - 23)), x1 = min(64, (int)(xc + 24));
  if (y0 < y1 && x0 < x1) nf_tortue_dessin(y0, y1, x0, x1, xc, yc, sens, tangage, t * om);
  // les bulles : de l'herbier, et parfois de son nez
  for (int i = 0; i < 9; i++) {
    e.by[i] -= e.bv[i] * dt;
    if (e.by[i] < -2) { e.by[i] = hasard(58, 66); e.bx[i] = hasard(0, 64); }
    const float k = 0.4f + 0.25f * sinf(e.bp[i]);
    nf_tache(e.by[i], e.bx[i] + sinf(t * 2.5f + e.bp[i]) * 0.7f, 170 * k, 220 * k, 240 * k);
  }
  for (int j = 0; j < 3; j++) {
    e.sy[j] -= 7.0f * dt;
    if (e.sy[j] < -2 && ecoule >= e.sq[j] && tete_x > 2 && tete_x < 62) {
      e.sx[j] = tete_x + hasard(-0.5f, 0.5f); e.sy[j] = tete_y - hasard(0, 1.5f);
      e.sq[j] = ecoule + 6.0f + hasard(0, 3);
    }
    nf_tache(e.sy[j], e.sx[j] + sinf(t * 3 + e.sp[j]) * 0.6f, 150 * 0.55f, 200 * 0.55f, 225 * 0.55f);
  }
}

// ===========================================================================
// (la suite : a porter)

struct E_mer_de_nuages { char rien; };
void s_mer_de_nuages(int humeur, bool debut, float t, float ecoule, float dt) {
  E_mer_de_nuages &e = etat_ecran<E_mer_de_nuages>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_hublot { char rien; };
void s_hublot(int humeur, bool debut, float t, float ecoule, float dt) {
  E_hublot &e = etat_ecran<E_hublot>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_arc_en_ciel { char rien; };
void s_arc_en_ciel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_arc_en_ciel &e = etat_ecran<E_arc_en_ciel>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_lever_de_lune { char rien; };
void s_lever_de_lune(int humeur, bool debut, float t, float ecoule, float dt) {
  E_lever_de_lune &e = etat_ecran<E_lever_de_lune>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_herbes { char rien; };
void s_herbes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_herbes &e = etat_ecran<E_herbes>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_plaine { char rien; };
void s_plaine(int humeur, bool debut, float t, float ecoule, float dt) {
  E_plaine &e = etat_ecran<E_plaine>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_montagne { char rien; };
void s_montagne(int humeur, bool debut, float t, float ecoule, float dt) {
  E_montagne &e = etat_ecran<E_montagne>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_savane { char rien; };
void s_savane(int humeur, bool debut, float t, float ecoule, float dt) {
  E_savane &e = etat_ecran<E_savane>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_eoliennes { char rien; };
void s_eoliennes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_eoliennes &e = etat_ecran<E_eoliennes>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_montgolfieres { char rien; };
void s_montgolfieres(int humeur, bool debut, float t, float ecoule, float dt) {
  E_montgolfieres &e = etat_ecran<E_montgolfieres>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_voilier { char rien; };
void s_voilier(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voilier &e = etat_ecran<E_voilier>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_foret_rayons { char rien; };
void s_foret_rayons(int humeur, bool debut, float t, float ecoule, float dt) {
  E_foret_rayons &e = etat_ecran<E_foret_rayons>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_jardin_zen { char rien; };
void s_jardin_zen(int humeur, bool debut, float t, float ecoule, float dt) {
  E_jardin_zen &e = etat_ecran<E_jardin_zen>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
