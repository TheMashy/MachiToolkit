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

// --- La mer de nuages : des rangees de moutons qui s'eloignent, au couchant ---
// humeurs : 0 = Mer de nuages
const int NF_MDN_N = 40;            // rangees de moutons entre nous et l'horizon
const float NF_MDN_PAS = 0.5f;      // leur ecart, en profondeur
const float NF_MDN_HZ = 25.0f, NF_MDN_SX = 40.0f, NF_MDN_SY = 23.0f;

struct NF_MdnRangees { float cretes[NF_MDN_N][64], lisse[NF_MDN_N][64]; };
union NF_MdnTravail {               // le brouillon : les bosses au debut, puis les rangees a chaque image
  NF_MdnRangees r;
  float h[4096];
};
struct E_mer_de_nuages {
  uint16_t prof[4097];               // le long profil des moutons (0-1)
  uint8_t som[64 * 64][3];           // l'image des deux sommets
  uint8_t op[2][64 * 64];            // leurs opacites, du plus loin au plus pres
  int oy[2][2];                      // les lignes ou elles ne sont pas nulles
  float ciel[25 * 64][3];            // le ciel au-dessus de l'horizon
  float lut06[66];                   // x^0.6
  NF_MdnTravail w;
  float z[NF_MDN_N];
  int ordre[NF_MDN_N], fin[NF_MDN_N], npop[NF_MDN_N], r0[NF_MDN_N];
  float couv[64], roc[64], corps[64], tranche[64], loin[64];
};

// une bosse (un demi-cercle) sur le profil : dessous(j) * kd + r * haut * sqrt(1 - d^2)
void nf_mdn_bosse(float *h, const uint16_t *dessous, float kd, float c, float r, float haut) {
  const int i0 = (int)((c - r) * 64) - 1, i1 = (int)((c + r) * 64) + 2;
  for (int i = i0; i < i1; i++) {
    const float d = (i / 64.0f - c) / r;
    if (fabsf(d) >= 1) continue;
    const int j = ((i % 4096) + 4096) % 4096;
    const float v = (dessous ? dessous[j] * (kd / 65535.0f) : 0.0f) + r * haut * sqrtf(1 - d * d);
    if (v > h[j]) h[j] = v;
  }
}

void nf_mdn_preparer(E_mer_de_nuages &e) {
  // _mer_de_nuages_bosses : des demi-cercles qui se chevauchent, des petits par-dessus ; ca se raccorde
  float *h = e.w.h;
  for (int i = 0; i < 4096; i++) h[i] = 0;
  float c = 0;
  while (c < 64) {
    const float r = hasard(0.2f, 0.62f);
    nf_mdn_bosse(h, nullptr, 0, c, r, hasard(0.55f, 0.95f));
    c += r * hasard(0.9f, 1.6f);
  }
  for (int i = 0; i < 4096; i++) e.prof[i] = (uint16_t)(borne(h[i], 0, 1) * 65535);   // (les gros, un moment)
  for (int k = 0; k < 170; k++) {
    const float cc = hasard(0, 64);
    nf_mdn_bosse(h, e.prof, 0.92f, cc, hasard(0.06f, 0.15f), 0.7f);
  }
  for (int i = 0; i < 4096; i++) e.prof[i] = (uint16_t)(borne(h[i], 0, 1) * 65535);
  e.prof[4096] = e.prof[0];
  // _mer_de_nuages_sommets : deux sommets qui percent la mer de nuages, a contre-jour
  uint16_t *roche = (uint16_t *)e.w.h;
  brume_n(roche, 64, 5);
  for (int i = 0; i < 64 * 64; i++) e.som[i][0] = e.som[i][1] = e.som[i][2] = 0;
  static const float SOM[2][5] = {{15.0f, 12.0f, 11.0f, 1.35f, 1.0f}, {57.0f, 18.5f, 6.0f, 0.8f, 1.3f}};
  static const float EPAULES[2][3][3] = {{{-6, 2.6f, 2.5f}, {5, 1.8f, 2.0f}, {10, 2.4f, 3.0f}}, {{-5, 1.8f, 2.5f}, {-11, 1.4f, 3.0f}, {0, 0, 1}}};
  for (int s = 0; s < 2; s++) {
    const float x0 = SOM[s][0], y0 = SOM[s][1], z = SOM[s][2], pg = SOM[s][3], pd = SOM[s][4];
    const float base = NF_MDN_HZ + 40.0f / z;
    float crete[64], pente[64];
    for (int x = 0; x < 64; x++) {
      float cr = y0 + (x < x0 ? (x0 - x) * pg : (x - x0) * pd);
      for (int k = 0; k < 3; k++) cr -= EPAULES[s][k][1] * borne(1 - fabsf(x - x0 - EPAULES[s][k][0]) / EPAULES[s][k][2], 0, 1);
      cr += 0.45f * sinf(x * 2.1f + x0) * borne(fabsf(x - x0) / 3, 0, 1);
      crete[x] = cr;
    }
    for (int x = 0; x < 64; x++)
      pente[x] = fabsf(x == 0 ? crete[1] - crete[0] : x == 63 ? crete[63] - crete[62] : (crete[x + 1] - crete[x - 1]) * 0.5f);
    const float vs = x0 < NF_MDN_SX ? 1.0f : -1.0f;
    const float loin = 0.12f + 0.25f * fminf(1.0f, z / 12);
    // l'ordre : du plus loin (z = 11) au plus pres (z = 6)
    e.oy[s][0] = 64; e.oy[s][1] = 0;
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float opac = borne(y - crete[x] + 0.5f, 0, 1) * (y < base + 4 ? 1.0f : 0.0f);
        e.op[s][y * 64 + x] = (uint8_t)roundf(opac * 255);
        if (!e.op[s][y * 64 + x]) continue;
        e.oy[s][0] = min(e.oy[s][0], y); e.oy[s][1] = max(e.oy[s][1], y + 1);
        const float face = borne((x - x0) * vs * 0.3f + 0.5f, 0, 1);
        const float couloirs = borne((roche[y * 64 + x] / 65535.0f - 0.45f) * 3 + sinf((x - x0) * 0.9f + y * 0.45f * vs) * 0.5f, 0, 1);
        const float kc = couloirs * borne(1 - (y - crete[x]) / 10, 0, 1), kb = borne((y - y0) / 18, 0, 1);
        float c[3] = {42 + kc * 22 + kb * 30 + face * 24, 33 + kc * 18 + kb * 16 + face * 10, 76 + kc * 34 + kb * 26 + face * 12};
        const float fil = borne(1.2f + pente[x] * 0.8f - (y - crete[x]), 0, 1) * (0.2f + 0.8f * face);
        static const float DORE[3] = {255, 182, 122}, LOIN[3] = {215, 130, 135};
        for (int k = 0; k < 3; k++) {
          c[k] = c[k] * (1 - fil) + DORE[k] * fil;
          c[k] = c[k] * (1 - loin) + LOIN[k] * loin;
          const float v = e.som[y * 64 + x][k] * (1 - opac) + c[k] * opac;
          e.som[y * 64 + x][k] = (uint8_t)borne(roundf(v), 0, 255);
        }
      }
  }
  // le ciel, son soleil bas sur l'horizon
  static const float CC[4] = {0.0f, 0.5f, 0.85f, 1.0f};
  static const float CIEL[4][3] = {{14, 18, 54}, {96, 52, 118}, {225, 120, 110}, {255, 170, 105}};
  for (int y = 0; y < 25; y++) {
    float r, g, b;
    nf_palette(y / NF_MDN_HZ, 4, CC, CIEL, r, g, b);
    for (int x = 0; x < 64; x++) {
      const float d = sqrtf((x - NF_MDN_SX) * (x - NF_MDN_SX) + (y - NF_MDN_SY) * 1.7f * (y - NF_MDN_SY) * 1.7f);
      const float a = expf(-d / 9.0f), bb = expf(-d / 26.0f);
      const float disque = borne(3.4f - sqrtf((x - NF_MDN_SX) * (x - NF_MDN_SX) + (y - NF_MDN_SY) * (y - NF_MDN_SY)), 0, 1);
      float *p = e.ciel[y * 64 + x];
      p[0] = r + a * 110 + bb * 40 + disque * 255;
      p[1] = g + a * 75 + bb * 18 + disque * 240;
      p[2] = b + a * 25 + disque * 190;
    }
  }
  for (int i = 0; i <= 65; i++) e.lut06[i] = powf(fminf(i / 64.0f, 1.0f), 0.6f);
}

void s_mer_de_nuages(int humeur, bool debut, float t, float ecoule, float dt) {
  E_mer_de_nuages &e = etat_ecran<E_mer_de_nuages>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) nf_mdn_preparer(e);
  const float hz = NF_MDN_HZ, v = 0.06f, pas = NF_MDN_PAS;
  const float derive = fmodf(t * 0.012f, 64.0f);
  NF_MdnRangees &R = e.w.r;
  // les rangees : leur crete, colonne par colonne ; chacune garde son dessin tant qu'elle vit
  for (int i = 0; i < NF_MDN_N; i++) {
    const float s = i - v * t;
    const float gen = floorf(s / NF_MDN_N);
    e.z[i] = 0.55f + (s - gen * NF_MDN_N) * pas;
    const long ident = (long)gen * NF_MDN_N + i;
    const long im = ((ident % 4096) + 4096) % 4096;
    const float decal = (float)((im * 7919) % 4096) / 64.0f;
    const float id = (float)ident;
    const float z = e.z[i];
    float mn = 1e9f;
    for (int x = 0; x < 64; x++) {
      const float uw = (x - 32.0f) / 40.0f * z + derive;
      float pos = uw + decal;
      pos = (pos - 64.0f * floorf(pos * (1.0f / 64))) * 64.0f;
      const int j = min(4095, (int)pos);
      const float f = pos - j;
      float h = (e.prof[j] * (1 - f) + e.prof[j + 1] * f) * (1.0f / 65535.0f);
      h = h * (0.75f + 0.25f * nf_sin(uw * 0.31f + id * 0.7f)) + 0.09f * nf_sin(uw * 0.53f - id * 1.3f);
      R.cretes[i][x] = hz + 40.0f * (1 - h) / z;
      mn = fminf(mn, R.cretes[i][x]);
    }
    e.r0[i] = max(0, (int)mn);
    for (int x = 0; x < 64; x++) {          // la crete sans ses creux : un creux reste dans l'ombre
      float l = R.cretes[i][x];
      for (int k = -2; k <= 2; k++) l = fminf(l, R.cretes[i][min(63, max(0, x + k))]);
      R.lisse[i][x] = l;
    }
  }
  // de la plus lointaine a la plus proche
  for (int i = 0; i < NF_MDN_N; i++) e.ordre[i] = i;
  for (int i = 1; i < NF_MDN_N; i++)
    for (int j = i; j > 0 && e.z[e.ordre[j]] > e.z[e.ordre[j - 1]]; j--) { const int q = e.ordre[j]; e.ordre[j] = e.ordre[j - 1]; e.ordre[j - 1] = q; }
  int cm = 1 << 20;                          // dessous : tout est deja couvert par les plus proches
  for (int j = NF_MDN_N - 1; j >= 0; j--) {
    e.fin[j] = j == NF_MDN_N - 1 ? 64 : cm;
    float mx = -1e9f;
    for (int x = 0; x < 64; x++) mx = fmaxf(mx, R.cretes[e.ordre[j]][x]);
    cm = min(cm, (int)ceilf(mx + 0.5f));
  }
  static const float ZS[2] = {11.0f, 6.0f};
  bool voile[NF_MDN_N];                      // juste devant un sommet : elle ne couvre pas tout
  for (int j = 0; j < NF_MDN_N; j++) {
    const float zi = e.z[e.ordre[j]];
    e.npop[j] = (ZS[0] > zi ? 1 : 0) + (ZS[1] > zi ? 1 : 0);
    voile[j] = false;
    for (int p = 0; p < e.npop[j]; p++) voile[j] |= ZS[p] - zi < 0.8f;
  }
  const float etoile = 0.75f + 0.25f * sinf(t * 1.3f);
  // colonne par colonne : on peint des grandeurs (lumiere, tranche, distance), la couleur vient a la fin
  for (int x = 0; x < 64; x++) {
    for (int y = 0; y < 64; y++) {
      const float sous = y >= hz ? 1.0f : 0.0f;
      e.couv[y] = sous; e.roc[y] = 0; e.corps[y] = sous * 0.5f; e.tranche[y] = 0; e.loin[y] = sous;
    }
    // dans cette colonne, sous la crete d'une rangee plus proche, tout est recouvert : inutile d'y peindre
    int finx[NF_MDN_N], cmx = 64;
    for (int j = NF_MDN_N - 1; j >= 0; j--) {
      finx[j] = cmx;
      if (!voile[j]) cmx = min(cmx, (int)ceilf(R.cretes[e.ordre[j]][x] + 0.5f));
    }
    int pop = 0;
    for (int j = 0; j < NF_MDN_N; j++) {
      const int i = e.ordre[j];
      const float zi = e.z[i];
      while (pop < e.npop[j]) {                // un sommet, entre deux rangees
        for (int y = e.oy[pop][0]; y < e.oy[pop][1]; y++) {
          const float a = e.op[pop][y * 64 + x] * (1.0f / 255);
          e.couv[y] = e.couv[y] * (1 - a) + a;
          e.roc[y] = e.roc[y] * (1 - a) + a;
        }
        pop++;
      }
      const int r1 = min(min(64, e.fin[j]), finx[j]);
      if (e.r0[i] >= r1) continue;
      const float cr = R.cretes[i][x], lis = R.lisse[i][x];
      const int ys = max(e.r0[i], (int)ceilf(cr - 0.5f));
      const float creux = cr - lis, kz = zi / 40.0f / 0.16f, ic2 = 1.0f / fmaxf(0.9f, 2.0f / zi);
      const float lo = fminf(1.0f, (zi - 0.55f) / 13.0f);
      for (int y = ys; y < r1; y++) {
        const float dy = y - cr;
        float a = borne(dy + 0.5f, 0, 1);
        for (int p = 0; p < pop; p++)          // juste devant un sommet : elle apparait doucement
          if (ZS[p] - zi < 0.8f) a *= 1 - e.op[p][y * 64 + x] * (1.0f / 255) * (1 - (ZS[p] - zi) / 0.8f);
        if (a <= 0) continue;
        const float b = 1 - a;
        e.couv[y] = e.couv[y] * b + a;
        e.roc[y] *= b;
        e.corps[y] = e.corps[y] * b + nf_exp(-(y - lis) * kz) * a;
        e.tranche[y] = e.tranche[y] * b + nf_exp(-fmaxf(dy, 0.0f) * ic2 - creux * 0.6f) * a;
        e.loin[y] = e.loin[y] * b + lo * a;
      }
    }
    while (pop < 2) {                          // (un sommet plus proche que toutes les rangees)
      for (int y = e.oy[pop][0]; y < e.oy[pop][1]; y++) {
        const float a = e.op[pop][y * 64 + x] * (1.0f / 255);
        e.couv[y] = e.couv[y] * (1 - a) + a;
        e.roc[y] = e.roc[y] * (1 - a) + a;
      }
      pop++;
    }
    const float sx = expf(-((x - NF_MDN_SX) / 16.0f) * ((x - NF_MDN_SX) / 16.0f));
    const float rim[3] = {250 * (1 - sx) + 255 * sx, 140 * (1 - sx) + 208 * sx, 160 * (1 - sx) + 140 * sx};
    for (int y = 0; y < 64; y++) {
      const float cv = e.couv[y], rc = e.roc[y];
      float r = 0, g = 0, b = 0;
      if (y < 25 && cv < 1) {
        const float *c = e.ciel[y * 64 + x];
        float cr = c[0], cg = c[1], cb = c[2];
        if (y == 5 && x == 9) { cr = fmaxf(cr, 230 * etoile); cg = fmaxf(cg, 225 * etoile); cb = fmaxf(cb, 240 * etoile); }   // l'etoile du berger
        r = cr * (1 - cv); g = cg * (1 - cv); b = cb * (1 - cv);
      }
      const float kn = cv - rc;
      if (kn > 0) {
        const float lo = borne(e.loin[y], 0, 1), qi = lo * 64;
        const int ii = min(63, (int)qi);
        const float gg = e.lut06[ii] + (e.lut06[ii + 1] - e.lut06[ii]) * (qi - ii);
        const float co = e.corps[y], tr = e.tranche[y], br = 0.5f * lo * gg;
        const float fond[3] = {46 + 144 * gg, 28 + 78 * gg, 78 + 46 * gg};
        const float mil[3] = {132 + 98 * gg, 72 + 66 * gg, 128 + 0 * gg};
        const float chaud[3] = {70, 42, 8}, brume[3] = {240, 155, 125};
        float n[3];
        for (int k = 0; k < 3; k++) {
          n[k] = fond[k] + co * (mil[k] - fond[k] + sx * (1 - 0.5f * gg) * chaud[k]);
          n[k] = n[k] * (1 - tr * 0.85f) + rim[k] * tr * (0.6f + 0.4f * gg);
          n[k] = n[k] * (1 - br) + brume[k] * br;
        }
        r += n[0] * kn; g += n[1] * kn; b += n[2] * kn;
      }
      if (rc > 0) { const uint8_t *s = e.som[y * 64 + x]; r += s[0] * rc; g += s[1] * rc; b += s[2] * rc; }
      peindre(y, x, r, g, b);
    }
  }
}

// --- Le hublot de nuit : la mer de nuages sous la lune, l'aile et son feu ---
// humeurs : 0 = Hublot de nuit
struct E_hublot {
  uint8_t base[64 * 64][3];          // ce qui ne bouge pas : la cabine, l'aile, le reflet (deja vus par la vitre)
  uint8_t poids[64 * 64];            // la part de la vue, x255 : la vitre, moins l'aile
  uint16_t g1[64 * 64], g2[64 * 64]; // les lueurs du feu, x16384 (deja vues par la vitre)
  uint8_t ciel[31 * 64][3];          // la vue du ciel, la lune comprise
  float ex[16], ey[16], ep[16], el[16];
  float ka[9], kb[9], ph[9], amp[9], lk[9], somme;
};
static inline float nf_hublot_q(float x, float y) {
  return powf(powf(fabsf((x - 33.0f) / 17.0f), 3.2f) + powf(fabsf((y - 32.0f) / 23.5f), 3.2f), 1 / 3.2f);
}
void nf_hublot_preparer(E_hublot &e) {
  const float hz = 30.0f, lx = 27.0f, ly = 18.5f, cx = 33.0f;
  static const float AC[3] = {0.0f, 0.35f, 1.0f};
  static const float AILE[3][3] = {{44, 50, 70}, {26, 29, 42}, {15, 16, 24}};
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float q = nf_hublot_q(x, y);
      float vitre = borne((1 - q) * 17 + 0.5f, 0, 1);
      float cab[3] = {17 + y / 64.0f * 8, 16 + y / 64.0f * 6, 22 + y / 64.0f * 4};
      const float gx = x == 0 ? nf_hublot_q(1, y) - q : x == 63 ? q - nf_hublot_q(62, y) : (nf_hublot_q(x + 1, y) - nf_hublot_q(x - 1, y)) * 0.5f;
      const float gy = y == 0 ? nf_hublot_q(x, 1) - q : y == 63 ? q - nf_hublot_q(x, 62) : (nf_hublot_q(x, y + 1) - nf_hublot_q(x, y - 1)) * 0.5f;
      const float lune = borne((gx * 0.55f + gy * 0.65f) / (sqrtf(gx * gx + gy * gy) + 1e-9f), 0, 1);
      if (q >= 0.98f && q < 1.2f) {               // le cadre, sa tranche qui voit la lune
        const float k = lune * borne((1.2f - q) / 0.22f, 0, 1);
        cab[0] = 30 + k * 50; cab[1] = 30 + k * 56; cab[2] = 38 + k * 78;
      }
      if (q >= 1.2f && q < 1.27f) { cab[0] = 9; cab[1] = 9; cab[2] = 13; }   // le joint
      if (q >= 0.98f && q < 1.04f) { cab[0] = cab[0] * 0.7f + 18; cab[1] = cab[1] * 0.7f + 18.6f; cab[2] = cab[2] * 0.7f + 22.8f; }
      if (y < 12.6f && q < 1.02f) { cab[0] = 36 + (y - 8) * 1.2f; cab[1] = 35 + (y - 8) * 1.2f; cab[2] = 42 + (y - 8) * 1.2f; }   // le store
      if (y >= 11.6f && y < 12.6f && q < 1.02f) { cab[0] = 62; cab[1] = 61; cab[2] = 70; }
      if (y >= 12.6f && y < 13.6f && fabsf(x - cx) < 2.5f) { cab[0] = 54; cab[1] = 53; cab[2] = 62; }
      if (y < 12.6f) vitre = 0;
      // l'aile, vue d'au-dessus
      const float attaque = 39.0f + (x - 21.0f) * 0.19f, fuite = 41.4f + (x - 23.0f) * 0.6f;
      float aile = borne(fminf(fminf(y - attaque, fuite - y), (x - 20.6f) * 2) + 0.5f, 0, 1);
      const float ailette = y < 40 ? borne(fminf(fminf(x - 20.4f - (39.5f - y) * 0.2f, 22.2f - x + (39.5f - y) * 0.08f), y - 34.0f) + 0.5f, 0, 1) : 0.0f;
      aile = fmaxf(aile, ailette);
      float ca[3];
      nf_palette(borne((y - attaque) / fmaxf(1.0f, fuite - attaque), 0, 1), 3, AC, AILE, ca[0], ca[1], ca[2]);
      const float ba = borne(1.1f - fabsf(y - attaque - 0.3f), 0, 1);
      const float bt = y < 40 ? borne(1 - fabsf(x - 20.9f - (39.5f - y) * 0.2f), 0, 1) : 0.0f;
      ca[0] += ba * 70 + bt * 50; ca[1] += ba * 78 + bt * 56; ca[2] += ba * 104 + bt * 76;
      if (fabsf(y - (fuite - 2.4f)) < 0.5f && x > 28) { ca[0] *= 0.55f; ca[1] *= 0.55f; ca[2] *= 0.55f; }
      const float refl = vitre * borne(1 - fabsf(x - y * 0.45f - 22) / 3.0f, 0, 1) * 0.05f;
      const float rc[3] = {120, 120, 140};
      for (int k = 0; k < 3; k++)
        e.base[y * 64 + x][k] = (uint8_t)borne(roundf(cab[k] * (1 - vitre) + vitre * aile * ca[k] + refl * rc[k]), 0, 255);
      e.poids[y * 64 + x] = (uint8_t)roundf(vitre * (1 - aile) * 255);
      const float df = sqrtf((x - 21.4f) * (x - 21.4f) + (y - 39.6f) * (y - 39.6f));
      e.g1[y * 64 + x] = (uint16_t)roundf(vitre * (expf(-df / 1.4f) * 1.4f + expf(-df / 5.0f) * 0.3f) * 16384);
      e.g2[y * 64 + x] = (uint16_t)roundf(vitre * expf(-df / 7.0f) * aile * 0.8f * 16384);
      if (y <= 30) {                               // la vue du ciel : la lune, son halo
        const float k = borne((y - 12.0f) / (hz - 12.0f), 0, 1);
        const float dl = sqrtf((x - lx) * (x - lx) + (y - ly) * (y - ly));
        const float a = expf(-dl / 3.5f), b = expf(-dl / 14.0f), m = borne(3.0f - dl, 0, 1);
        const float v[3] = {4 + 22 * k + a * 45 + b * 14, 7 + 29 * k + a * 50 + b * 18, 20 + 50 * k + a * 66 + b * 32};
        const float l[3] = {235, 235, 215};
        for (int c = 0; c < 3; c++) e.ciel[y * 64 + x][c] = (uint8_t)borne(roundf(v[c] + m * (l[c] - v[c])), 0, 255);
      }
    }
  for (int i = 0; i < 16; i++) { e.ex[i] = hasard(17, 50); e.ey[i] = hasard(14, hz - 2); e.ep[i] = hasard(0, PI2); e.el[i] = hasard(0.3f, 1); }
  static const float K[9] = {2.0f, 2.9f, 4.2f, 6.0f, 8.5f, 12.0f, 17.0f, 24.0f, 33.0f};
  e.somme = 0;
  for (int i = 0; i < 9; i++) {
    const float th = hasard(0, NF_PI);
    e.ka[i] = K[i] * cosf(th); e.kb[i] = K[i] * sinf(th) * 0.55f;   // un peu etirees en profondeur
    e.amp[i] = powf(K[i], -0.45f);
    e.lk[i] = (-0.5f * e.ka[i] + 0.85f * e.kb[i]) / K[i];             // la pente vers la lune
    e.ph[i] = hasard(0, PI2);
    e.somme += e.amp[i];
  }
}
void s_hublot(int humeur, bool debut, float t, float ecoule, float dt) {
  E_hublot &e = etat_ecran<E_hublot>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) nf_hublot_preparer(e);
  const float hz = 30.0f, lx = 27.0f, ly = 18.5f;
  // la vue : le ciel jusqu'a l'horizon, puis la mer de nuages qui glisse vers l'arriere
  for (int y = 13; y < 57; y++) {
    if (y < 30) {
      for (int x = 0; x < 64; x++) {
        const uint8_t *c = e.ciel[y * 64 + x];
        peindre(y, x, c[0], c[1], c[2]);
      }
      continue;
    }
    if (y == 30) {                               // a moitie ciel, a moitie mer de nuages, au loin
      for (int x = 0; x < 64; x++) {
        const uint8_t *c = e.ciel[y * 64 + x];
        peindre(y, x, c[0] * 0.5f + 18, c[1] * 0.5f + 23, c[2] * 0.5f + 40);
      }
      continue;
    }
    const float z = 20.0f / (y - hz);
    float pw[9], lw[9], s[9], c[9], sb[9], cb[9];
    int n = 0;
    for (int i = 0; i < 9; i++) {
      const float finesse = fmaxf(fabsf(e.ka[i]) * (z / 40.0f), fabsf(e.kb[i]) * (z * z / 20.0f)) / PI2;
      const float w = borne(1.6f - finesse * 4.0f, 0, 1) * e.amp[i];   // au-dela d'1/4 de cycle par pixel : effacee
      if (w <= 0) continue;
      const float decal = fmodf(e.ka[i] * (t * 0.05f), PI2);
      const float a = e.ka[i] * (-33.0f) * z / 40.0f + e.kb[i] * z + e.ph[i] + decal, b = e.ka[i] * z / 40.0f;
      pw[n] = w / e.somme * 1.6f; lw[n] = e.lk[i] * w / e.somme;
      s[n] = sinf(a); c[n] = cosf(a); sb[n] = sinf(b); cb[n] = cosf(b);
      n++;
    }
    const float loin = borne((z - 2.5f) / 7.0f, 0, 1), dg = 2.0f + (y - hz) * 0.5f, kg = borne((y - hz) / 4, 0, 1);
    for (int x = 0; x < 64; x++) {
      float f = 0.5f, relief = 0;
      for (int k = 0; k < n; k++) {
        f += pw[k] * s[k];
        relief += lw[k] * c[k];
        const float ns = s[k] * cb[k] + c[k] * sb[k];
        c[k] = c[k] * cb[k] - s[k] * sb[k];
        s[k] = ns;
      }
      const float dens = borne((f - 0.44f) * 3.5f, 0, 1);
      const float gq = (x - lx) / dg;
      const float glade = gq * gq < 16 ? nf_exp(-gq * gq) * kg : 0.0f;
      const float lum = (dens > 0 ? nf_exp(0.8f * logf(dens)) : 0.0f) * borne(0.55f + relief * 2.0f + 0.4f * glade, 0.15f, 1.3f);
      peindre(y, x, (7 + lum * 120) * (1 - loin) + 36 * loin, (10 + lum * 132) * (1 - loin) + 46 * loin,
              (24 + lum * 170) * (1 - loin) + 80 * loin);
    }
  }
  for (int i = 0; i < 16; i++) {                 // les etoiles, loin de la lune
    const float d = sqrtf((e.ex[i] - lx) * (e.ex[i] - lx) + (e.ey[i] - ly) * (e.ey[i] - ly));
    const float k = e.el[i] * (0.6f + 0.4f * sinf(t * 1.7f + e.ep[i])) * borne((d - 4) / 6, 0, 1);
    pointer(e.ey[i], e.ex[i], 190 * k, 195 * k, 220 * k);
  }
  // l'aile, la cabine, et le feu qui clignote doucement
  const float ph = fmodf(t / 2.6f, 1.0f) - 0.3f;
  const float feu = 0.12f + 0.88f * expf(-(ph / 0.075f) * (ph / 0.075f));
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const uint8_t *b = e.base[i];
      float r = b[0], g = b[1], bl = b[2];
      if (e.poids[i]) {
        const float w = e.poids[i] * (1.0f / 255);
        r += scene[y][x][0] * w; g += scene[y][x][1] * w; bl += scene[y][x][2] * w;
      }
      if (e.g1[i] | e.g2[i]) {
        const float a = e.g1[i] * (feu / 16384.0f), c = e.g2[i] * (feu / 16384.0f);
        r += a * 255 + c * 120; g += a * 40 + c * 14; bl += a * 30 + c * 10;
      }
      peindre(y, x, r, g, bl);
    }
}

// --- L'arc-en-ciel : apres l'averse, l'arc (et son second) respire au-dessus de la prairie ---
// humeurs : 0 = Arc-en-ciel
struct E_arc_en_ciel {
  uint16_t na[128 * 128], nb[128 * 128];   // les nuees qui s'en vont
  uint8_t env[2][64 * 64];                 // l'enveloppe des deux arcs, x255
  float gauss[640];                        // l'averse au loin : exp(-((x - 50 + 0.2 y) / 10)^2), par 5 x + y
  float gx[14], gy[14], gv[14];
  float fx[16], fy[16];
  uint8_t fc[16];
  float loin[64];
};
void s_arc_en_ciel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_arc_en_ciel &e = etat_ecran<E_arc_en_ciel>(debut);
  (void)humeur;
  const float cx = 32.0f, cy = 70.0f, R = 47.0f, R2 = 58.0f;
  if (debut) {
    brume_n(e.na, 128, 16);
    brume_n(e.nb, 128, 6);
    for (int i = 0; i < 14; i++) { e.gx[i] = hasard(0, 64); e.gy[i] = hasard(-20, 50); e.gv[i] = hasard(30, 42); }
    for (int i = 0; i < 16; i++) { e.fx[i] = hasard(2, 62); e.fy[i] = hasard(56, 63); e.fc[i] = aleatoire() % 3; }
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float r = sqrtf((x - cx) * (x - cx) + (y - cy) * (y - cy));
        const float d1 = R - r, d2 = r - R2;
        e.env[0][y * 64 + x] = d1 > 0 && d1 < 6 ? (uint8_t)roundf(powf(sinf(NF_PI * d1 / 6), 0.7f) * 255) : 0;
        e.env[1][y * 64 + x] = d2 > 0 && d2 < 7 ? (uint8_t)roundf(powf(sinf(NF_PI * d2 / 7), 0.7f) * 255) : 0;
      }
    for (int i = 0; i < 640; i++) { const float u = (i - 250) / 5.0f / 10.0f; e.gauss[i] = expf(-u * u); }
    for (int x = 0; x < 64; x++) e.loin[x] = 45.0f + 2.2f * sinf(x * 0.08f + 0.7f) + 1.2f * sinf(x * 0.23f + 2);
  }
  static const float ARC[6][3] = {{255, 45, 40}, {255, 135, 30}, {250, 225, 60}, {60, 205, 80}, {50, 110, 255}, {130, 60, 210}};
  static const float IDX[6] = {0, 1, 2, 3, 4, 5};
  const float soleil = 0.5f + 0.5f * sinf(t * 0.11f);         // le soleil qui perce, puis se voile un peu (57 s)
  const float seuil = 0.53f + 0.07f * soleil;
  const float force = (0.4f + 0.6f * soleil) * fminf(1.0f, 0.3f + ecoule / 6.0f);
  const float kn = 0.85f + 0.2f * soleil;
  const float st = sinf(t * 0.21f), ct = cosf(t * 0.21f);
  float sA[64], cA[64], ombre[64], pres[64];
  for (int x = 0; x < 64; x++) {
    const float a = x * 1.7f + sinf(x * 0.21f) * 3;
    sA[x] = sinf(a); cA[x] = cosf(a);
    ombre[x] = 0.78f + 0.22f * soleil * (0.5f + 0.5f * sinf(x * 0.09f - t * 0.25f + sinf(x * 0.04f + t * 0.05f) * 2));
    const float herbe = 0.9f * sinf(x * 2.3f) + 0.6f * sinf(x * 3.7f + 1) + 0.5f * sinf(t * 1.4f + x * 0.25f);
    pres[x] = 52.0f + 1.5f * sinf(x * 0.06f + 2.5f) + 0.8f * sinf(x * 0.31f) - fmaxf(herbe, 0.0f) * 0.9f;
  }
  const float ox_a = -t * 0.9f + 17, ox_b = -t * 1.3f;
  static const float CC[2] = {0.0f, 46.0f};
  static const float CIEL[2][3] = {{40, 74, 128}, {128, 142, 158}};
  static const float CL[2] = {0.0f, 10.0f};
  static const float COLL[2][3] = {{70, 132, 70}, {44, 96, 52}};
  static const float FC[2] = {-3.0f, 3.0f};
  static const float FEU[2][3] = {{80, 140, 70}, {30, 70, 40}};
  static const float PC[3] = {0.0f, 2.0f, 12.0f};
  static const float PRE[3][3] = {{140, 205, 80}, {92, 172, 58}, {56, 124, 42}};
  const float ay = e.loin[50] - 4.0f;                           // un arbre seul, sur la colline
  for (int y = 0; y < 64; y++) {
    const float rideau = expf(-((y - 36) / 11.0f) * ((y - 36) / 11.0f));   // l'averse qui s'en va, derriere l'arc
    float cr, cg, cb;
    nf_palette(y, 2, CC, CIEL, cr, cg, cb);
    cr *= 1 - 0.42f * rideau; cg *= 1 - 0.42f * rideau; cb *= 1 - 0.42f * rideau;
    const float b = y * 0.32f - t * 4.0f, sB = sinf(b), cB = cosf(b);
    const float haut = borne(1.25f - y / 30.0f, 0, 1);
    for (int x = 0; x < 64; x++) {
      float r = cr, g = cg, bl = cb;
      const float pl = rideau * 0.1f * e.gauss[5 * x + y];
      if (pl > 1e-4f) {
        float s = borne(sA[x] * cB + cA[x] * sB, 0, 1);
        s = s * s * s; s *= s;
        r += s * pl * 150; g += s * pl * 160; bl += s * pl * 180;
      }
      if (haut > 0) {                                            // les nuees, qui s'en vont vers la droite
        const float f = fenetre_n(e.na, 128, ox_a, 9, x, y) * 0.8f + fenetre_n(e.nb, 128, ox_b, 40, x, y) * 0.2f;
        const float ep = borne((f - seuil) * 4.0f, 0, 1) * haut;
        if (ep > 0) {
          const float co = borne((f - seuil) * 2.2f, 0, 1);
          const float nr = (205 * (1 - co) + 78 * co) * kn, ng = (208 * (1 - co) + 84 * co) * kn, nb = (218 * (1 - co) + 102 * co) * kn;
          r += (nr - r) * ep; g += (ng - g) * ep; bl += (nb - bl) * ep;
        }
      }
      // l'arc, puis le second (couleurs inversees, pale), et la bande sombre entre les deux
      const float dx = x - cx, dy = cy - y;
      const float rr = sqrtf(dx * dx + dy * dy);
      const float dedans = borne((R - 6 - rr) / 6, 0, 1) * borne((rr - 25) / 10, 0, 1);
      const float entre = rr > R && rr < R2 ? 1.0f : 0.0f;
      const float k = 1 + force * (0.14f * dedans - 0.12f * entre);
      r *= k; g *= k; bl *= k;
      const int i = y * 64 + x;
      for (int a = 0; a < 2; a++) {
        if (!e.env[a][i]) continue;
        const float sn = dx / rr, cs = dy / rr;
        const float s3 = 3 * sn - 4 * sn * sn * sn, c3 = 4 * cs * cs * cs - 3 * cs;
        const float souffle = 0.75f + 0.25f * (s3 * ct - c3 * st);
        const float bande = a == 0 ? borne((R - rr) / 6.0f, 0, 1) : borne((rr - R2) / 7.0f, 0, 1);
        float ar, ag, ab;
        nf_palette(bande * 5.0f, 6, IDX, ARC, ar, ag, ab);
        const float al = e.env[a][i] * (1.0f / 255) * (a == 0 ? 1.0f : 0.34f) * souffle * force;
        r = r * (1 - al * 0.45f) + ar * al * 0.85f;
        g = g * (1 - al * 0.45f) + ag * al * 0.85f;
        bl = bl * (1 - al * 0.45f) + ab * al * 0.85f;
      }
      // la prairie : la colline au loin et son arbre, le pre devant ; l'ombre des nuages qui passe dessus
      const float lo = e.loin[x];
      float al = borne(y - lo + 0.5f, 0, 1);
      float kr, kg, kb;
      nf_palette(y - lo, 2, CL, COLL, kr, kg, kb);
      const float hq = 3.3f - sqrtf((x - 50.0f) * (x - 50.0f) + (y - ay) * 1.1f * (y - ay) * 1.1f);
      if (hq > 0) {
        const float houppe = fminf(hq, 1.0f);
        float fr, fg, fb;
        nf_palette(y - ay, 2, FC, FEU, fr, fg, fb);
        kr += (fr - kr) * houppe; kg += (fg - kg) * houppe; kb += (fb - kb) * houppe;
        al = fmaxf(al, houppe);
      }
      if (x == 50 && y >= (int)ay + 3 && y <= lo) { kr = 40; kg = 34; kb = 26; al = 1; }
      if (al > 0) {
        const float o = al * ombre[x];
        r = r * (1 - al) + kr * o; g = g * (1 - al) + kg * o; bl = bl * (1 - al) + kb * o;
      }
      const float ap = borne(y - pres[x] + 0.5f, 0, 1);
      if (ap > 0) {
        float pr, pg, pb;
        nf_palette(y - pres[x], 3, PC, PRE, pr, pg, pb);
        const float o = ombre[x] * 1.05f * ap;
        r = r * (1 - ap) + pr * o; g = g * (1 - ap) + pg * o; bl = bl * (1 - ap) + pb * o;
      }
      peindre(y, x, r, g, bl);
    }
  }
  static const float TEINTES[3][3] = {{255, 240, 140}, {250, 250, 245}, {255, 140, 175}};
  const float kf = 0.75f + 0.25f * soleil;
  for (int i = 0; i < 16; i++) {
    const float *c = TEINTES[e.fc[i]];
    pointer(e.fy[i], e.fx[i] + sinf(t * 1.4f + e.fx[i] * 0.25f) * 0.6f, c[0] * kf, c[1] * kf, c[2] * kf);
  }
  for (int i = 0; i < 14; i++) {                                 // les dernieres gouttes
    e.gy[i] += e.gv[i] * dt;
    e.gx[i] += e.gv[i] * 0.12f * dt;
    if (e.gy[i] > 58) { e.gy[i] -= 80; e.gx[i] = hasard(0, 64); }
    e.gx[i] = fmodf(e.gx[i], 64.0f);
    nf_tache(e.gy[i], e.gx[i], 140 * 0.6f, 150 * 0.6f, 170 * 0.6f);
    nf_tache(e.gy[i] - 1.2f, e.gx[i] - 0.15f, 70 * 0.6f, 76 * 0.6f, 90 * 0.6f);
  }
}

// --- Le lever de lune : une grande lune orange se leve sur la mer, puis tout recommence, dans un fondu ---
// humeurs : 0 = Lever de lune
const float NF_LUNE_CYCLE = 110.0f, NF_LUNE_FONDU = 0.07f;
struct E_lever_de_lune {
  uint16_t texture[128 * 128];
  uint16_t mers[32 * 32];
  float sx[40], sy[40], sp[40], sl[40];
  float vph[3];
  float go[161], gp[161], gf[161];
  uint16_t autre[64 * 64][3];       // l'image du lever suivant, pour le fondu (x32)
};
void nf_lune_image(E_lever_de_lune &e, float t, float ph) {
  const float hz = 40.0f;
  const float u = fminf(1.0f, ph / (1 - NF_LUNE_FONDU));
  const float xc = 32.0f, yc = 45.0f - 30.0f * (u > 0 ? powf(u, 0.8f) : 0.0f), R = 8.2f - 1.6f * u;
  const float haut = borne((hz - yc) / 24.0f, 0, 1);
  const float tasse = 1 - 0.16f * (1 - haut) * (1 - haut) * (1 - haut);      // basse, elle s'ecrase un peu
  static const float LC[4] = {0.0f, 0.25f, 0.55f, 1.0f};
  static const float LUNE[4][3] = {{255, 118, 40}, {255, 165, 80}, {252, 214, 150}, {236, 236, 222}};
  float lr, lg, lb;
  nf_palette(haut, 4, LC, LUNE, lr, lg, lb);
  lr *= 0.82f + 0.18f * haut; lg *= 0.82f + 0.18f * haut; lb *= 0.82f + 0.18f * haut;
  const float k1 = 0.32f - 0.12f * haut, k2 = 0.16f - 0.08f * haut, it = 1 / tasse;
  for (int y = 0; y < 40; y++) {                       // le ciel, chaud en bas tant qu'elle est basse
    const float q = y / hz, ch = q * sqrtf(q) * (1 - haut);
    const float cr = 5 + 13 * q + 46 * ch, cg = 7 + 15 * q + 14 * ch, cb = 26 + 32 * q + 6 * ch;
    const float dy = (y - yc) * it, dy2 = (y - yc) * 2;
    for (int x = 0; x < 64; x++) {
      const float dx = x - xc;
      const float d = sqrtf(dx * dx + dy * dy);
      const float h = nf_exp(-fmaxf(d - R, 0.0f) / 6.0f) * k1 + nf_exp(-sqrtf(dx * dx + dy2 * dy2) / 28.0f) * k2;
      peindre(y, x, cr + h * lr, cg + h * lg, cb + h * lb);
    }
  }
  for (int i = 0; i < 40; i++) {
    const float d = sqrtf((e.sx[i] - xc) * (e.sx[i] - xc) + (e.sy[i] - yc) * (e.sy[i] - yc));
    const float k = e.sl[i] * (0.6f + 0.4f * sinf(t * 1.9f + e.sp[i])) * (0.35f + 0.65f * haut) * borne((d - R - 3) / 12, 0, 1);
    pointer(e.sy[i], e.sx[i], 200 * k, 205 * k, 230 * k);
  }
  // le disque, ses mers, son bord plus sombre ; coupe par l'horizon
  const int ya = max(0, (int)(yc - R - 2)), yb = min((int)hz + 1, (int)(yc + R + 3));
  const int xa = max(0, (int)(xc - R - 2)), xb = min(64, (int)(xc + R + 3));
  for (int y = ya; y < yb; y++)
    for (int x = xa; x < xb; x++) {
      const float dx = x - xc, dy = (y - yc) * it;
      const float rho = sqrtf(dx * dx + dy * dy) / R;
      const float couv = borne((1 - rho) * R + 0.5f, 0, 1) * borne(hz - y, 0, 1);
      if (couv <= 0) continue;
      const float mers = nf_lire(e.mers, 32, 16 + dy / R * 7, 16 + dx / R * 7);
      const float rc = borne(rho, 0, 1);
      const float k = 1 - 0.26f * borne((mers - 0.5f) * 3, 0, 1) - 0.22f * rc * rc;
      nf_melanger(y, x, couv, lr * k, lg * k, lb * k);
    }
  // les nuages fins qui passent devant, eclaires par la lune quand ils la frolent
  static const float VOILES[3][4] = {{19.0f, 34.0f, 1.3f, 0.55f}, {27.0f, 46.0f, 1.0f, 0.4f}, {33.5f, 26.0f, 0.9f, 0.7f}};
  for (int v = 0; v < 3; v++) {
    const float y0 = VOILES[v][0], larg = VOILES[v][1], ep = VOILES[v][2], vit = VOILES[v][3], ph0 = e.vph[v];
    const float tour = 64 + larg + 30;
    const float cx = fmodf(t * vit + ph0, tour) - larg / 2 - 15;
    const float ox = fmodf(t * vit + ph0, 128.0f), oy = y0 * 3;
    const int ra = max(0, (int)(y0 - 4 * ep - 2)), rb = min(64, (int)(y0 + 4 * ep + 3));
    const int xa2 = max(0, (int)floorf(cx - larg / 2)), xb2 = min(64, (int)ceilf(cx + larg / 2) + 1);
    for (int x = xa2; x < xb2; x++) {
      const float w = borne(1 - fabsf(x - cx) / (larg / 2), 0, 1);
      if (w <= 0) continue;
      const float w6 = nf_exp(0.6f * logf(w)), yo = y0 + 0.9f * sinf(x * 0.13f + ph0);
      for (int y = ra; y < rb; y++) {
        const float q = (y - yo) / ep;
        float vo = nf_exp(-q * q) * w6 * (0.5f + 0.5f * fenetre_n(e.texture, 128, ox, oy, x, y));
        vo = fminf(vo, 0.9f) * 0.8f;
        if (vo <= 0) continue;
        const float dx = x - xc, dy = (y - yc) * it;
        const float d = sqrtf(dx * dx + dy * dy);
        const float ec = nf_exp(-fmaxf(d - R * 0.6f, 0.0f) / 8.0f) + 0.12f * nf_exp(-fmaxf(d - R, 0.0f) / 30.0f);
        nf_melanger(y, x, vo, 26 + ec * lr * 0.95f, 24 + ec * lg * 0.95f, 50 + ec * lb * 0.95f);
      }
    }
  }
  // la mer : sombre, un reflet chaud au loin, le chemin de lumiere sous la lune
  const float sortie = borne(1.25f - (yc + R - hz) / (2 * R), 0, 1);       // la part de la lune sortie de l'eau
  static const float MC[3] = {0.0f, 0.25f, 1.0f};
  static const float MER[3][3] = {{22, 22, 52}, {9, 14, 36}, {3, 6, 18}};
  for (int y = 40; y < 64; y++) {
    const float prof = borne((y - hz) / 24.0f, 0, 1);
    float er, eg, eb;
    nf_palette(prof, 3, MC, MER, er, eg, eb);
    const float rf = expf(-(y - hz) / 2.5f) * (1 - haut);
    er += rf * 60; eg += rf * 28; eb += rf * 30;
    const float z = 24.0f / (y - hz + 0.5f);
    const float larg = 0.6f + (y - hz) * (0.18f + 0.32f * haut);
    const float force = (0.5f + 0.5f * haut) * (1 - 0.35f * prof) * sortie * 0.3f;
    for (int x = 0; x < 64; x++) {
      float r = er, g = eg, b = eb;
      const float q = (x - xc) / larg;
      if (q * q < 16 && force > 0) {
        const float houle = 0.85f + 0.15f * nf_sin(z * 3.0f - t * 0.9f + nf_sin(x * 0.2f / z + t * 0.3f) * 1.5f);
        const float k = nf_exp(-q * q) * force * houle;
        r += k * lr; g += k * lg; b += k * lb;
      }
      peindre(y, x, r, g, b);
    }
  }
  for (int i = 0; i < 161; i++) {                     // les paillettes du chemin de lune
    const float gy = 41.0f + i / 7;
    const float lg2 = 0.6f + (gy - hz) * (0.18f + 0.32f * haut);
    const float gxx = xc + e.go[i] * lg2 + sinf(t * 0.4f + e.gp[i]) * 0.6f;
    float s = 0.5f + 0.5f * sinf(t * e.gf[i] + e.gp[i]);
    s *= s; s *= s;
    const float fg = s * expf(-e.go[i] * e.go[i]) * (0.5f + 0.5f * haut) * (0.75f - 0.2f * (gy - hz) / 24.0f) * sortie * 1.1f;
    if (fg <= 0) continue;
    nf_tache(gy, gxx - 0.5f, fg * lr, fg * lg, fg * lb);
    nf_tache(gy, gxx + 0.5f, fg * lr, fg * lg, fg * lb);
  }
}
void s_lever_de_lune(int humeur, bool debut, float t, float ecoule, float dt) {
  E_lever_de_lune &e = etat_ecran<E_lever_de_lune>(debut);
  (void)humeur; (void)dt;
  if (debut) {
    brume_n(e.mers, 32, 5);
    brume_n(e.texture, 128, 6);
    for (int i = 0; i < 40; i++) { e.sx[i] = hasard(0, 64); e.sy[i] = hasard(0, 37); e.sp[i] = hasard(0, 6.3f); e.sl[i] = hasard(0.3f, 1); }
    for (int i = 0; i < 3; i++) e.vph[i] = hasard(0, 100);
    for (int i = 0; i < 161; i++) { e.go[i] = nf_normal(0.8f); e.gp[i] = hasard(0, 6.3f); e.gf[i] = hasard(1.2f, 3.2f); }
  }
  const float ph = fmodf((ecoule + 24.0f) / NF_LUNE_CYCLE, 1.0f);   // l'ecran s'ouvre sur une lune deja sortie de l'eau
  if (ph > 1 - NF_LUNE_FONDU) {                                     // le fondu vers le debut du lever suivant
    nf_lune_image(e, t, 0.0f);
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++)
        for (int c = 0; c < 3; c++) e.autre[y * 64 + x][c] = (uint16_t)(borne(scene[y][x][c], 0, 2047) * 32);
    nf_lune_image(e, t, ph);
    float k = (ph - 1 + NF_LUNE_FONDU) / NF_LUNE_FONDU;
    k = k * k * (3 - 2 * k);
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++)
        for (int c = 0; c < 3; c++) scene[y][x][c] = scene[y][x][c] * (1 - k) + e.autre[y * 64 + x][c] * (k / 32.0f);
  } else {
    nf_lune_image(e, t, ph);
  }
}

// ===========================================================================
// LES GRANDS PAYSAGES

// --- Les herbes au vent : au ras du sol, a contre-jour ---
// humeurs : 0 = Herbes au vent
// (brins, hauteur min, max, demi-largeur au pied, a la pointe, teinte (3), lumiere qui passe, vent, courbure,
//  part d'epis, taille d'epi, teinte d'epi (3), lumiere de l'epi (3))
static const float NF_HERBES[3][19] = {
  {70, 6, 16, 0.32f, 0.2f, 104, 62, 40, 0.62f, 0.5f, 0.15f, 0.0f, 0.0f, 0, 0, 0, 0, 0, 0},
  {44, 13, 30, 0.42f, 0.24f, 48, 27, 22, 0.45f, 0.75f, 0.3f, 0.35f, 0.75f, 70, 44, 30, 240, 196, 130},
  {18, 26, 54, 0.7f, 0.22f, 12, 7, 9, 0.2f, 1.0f, 0.55f, 0.5f, 1.05f, 24, 14, 12, 330, 250, 150},
};
struct E_herbes {
  uint16_t fond[64 * 64][3];         // x64
  uint16_t jour[64 * 64];            // x65535
  float couv[64 * 64];
  float x0[132], h[132], pied[132], incl[132], courbe[132], ph[132], fr[132];
  uint8_t epi[132];
  float gx0[14], gy0[14], gv[14], gp[14], gk[14];
  float bx[7], by[7], br[7], ba[7], bp[7];
};
void s_herbes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_herbes &e = etat_ecran<E_herbes>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    float jmax = 0;
    for (int y = 0; y < 64; y++) {
      const float k = borne(y / 46.0f, 0, 1);
      for (int x = 0; x < 64; x++) {
        float c[3] = {44 + 192 * k, 26 + 124 * k, 52 + 12 * k};
        const float d = sqrtf((x - 40.0f) * (x - 40.0f) + (y - 37.0f) * 1.2f * (y - 37.0f) * 1.2f);
        const float g = borne(1 - d / 38, 0, 1), g2 = g * g, ex = expf(-(d / 8) * (d / 8));
        c[0] += g2 * 60 + ex * 40; c[1] += g2 * 48 + ex * 46; c[2] += g2 * 20 + ex * 34;
        const float so = borne(5.5f - d, 0, 1);
        c[0] += (255 - c[0]) * so; c[1] += (238 - c[1]) * so; c[2] += (190 - c[2]) * so;
        const float haie = 42 + 2.5f * sinf(x * 0.13f + 1) + 1.5f * sinf(x * 0.37f);   // des arbres au loin, flous
        const float a = borne((y - haie) / 3.0f + 0.5f, 0, 1) * 0.55f;
        c[0] += (96 - c[0]) * a; c[1] += (54 - c[1]) * a; c[2] += (34 - c[2]) * a;
        const float pre = borne((y - 47) / 17.0f, 0, 1) * 0.75f;                     // le pre, flou, plus sombre devant
        c[0] += (30 - c[0]) * pre; c[1] += (18 - c[1]) * pre; c[2] += (12 - c[2]) * pre;
        for (int i = 0; i < 3; i++) e.fond[y * 64 + x][i] = (uint16_t)roundf(borne(c[i], 0, 1023) * 64);
        const float j = (c[0] + c[1] + c[2]) / 3;
        e.couv[y * 64 + x] = j;
        jmax = fmaxf(jmax, j);
      }
    }
    for (int i = 0; i < 4096; i++) e.jour[i] = (uint16_t)roundf(e.couv[i] / jmax * 65535);
    int n = 0;
    for (int c = 0; c < 3; c++) {
      const float *C = NF_HERBES[c];
      for (int i = 0; i < (int)C[0]; i++, n++) {
        e.x0[n] = hasard(-6, 70); e.h[n] = hasard(C[1], C[2]); e.pied[n] = 64 + hasard(0, 3);
        e.incl[n] = hasard(-0.15f, 0.2f);
        e.courbe[n] = (aleatoire() & 1 ? 1.0f : -1.0f) * hasard(C[10] * 0.35f, C[10]);
        e.ph[n] = hasard(0, PI2); e.fr[n] = hasard(0.7f, 1.4f); e.epi[n] = hasard(0, 1) < C[11];
      }
    }
    for (int i = 0; i < 14; i++) { e.gx0[i] = hasard(0, 84); e.gy0[i] = hasard(8, 46); e.gv[i] = hasard(1.5f, 4.5f); e.gp[i] = hasard(0, 6); e.gk[i] = hasard(0.35f, 1.0f); }
    for (int i = 0; i < 7; i++) { e.bx[i] = hasard(4, 60); e.by[i] = hasard(18, 46); e.br[i] = hasard(1.8f, 3.6f); e.ba[i] = hasard(0.12f, 0.25f); e.bp[i] = hasard(0, 6); }
  }
  for (int i = 0; i < 4096; i++) {
    const uint16_t *f = e.fond[i];
    peindre(i >> 6, i & 63, f[0] * (1.0f / 64), f[1] * (1.0f / 64), f[2] * (1.0f / 64));
  }
  const float ij = 1.0f / 65535;
  for (int k = 0; k < 7; k++) {                                   // des taches de lumiere floues
    const float cx = e.bx[k] + 3 * sinf(t * 0.07f + e.bp[k]), cy = e.by[k] + 2 * sinf(t * 0.05f + e.bp[k] * 2), r = e.br[k];
    const float f = e.ba[k] * (0.7f + 0.3f * sinf(t * 0.4f + e.bp[k]));
    const int ya = (int)fmaxf(0, cy - r - 3), yb = (int)fminf(64, cy + r + 4), xa = (int)fmaxf(0, cx - r - 3), xb = (int)fminf(64, cx + r + 4);
    for (int y = ya; y < yb; y++)
      for (int x = xa; x < xb; x++) {
        const float d = sqrtf((x - cx) * (x - cx) + (y - cy) * (y - cy)), q = (d - r + 0.4f) / 0.8f;
        const float ta = (borne(r + 0.5f - d, 0, 1) * 0.6f + nf_exp(-q * q) * 0.4f) * f * e.jour[y * 64 + x] * ij;
        ajouter(y, x, ta, 255, 205, 130);
      }
  }
  const float rf = 0.7f + 0.3f * sinf(t * 0.09f);
  int n0 = 0;
  for (int c = 0; c < 3; c++) {
    const float *C = NF_HERBES[c];
    const int nb = (int)C[0], np = (int)C[2] + 2;
    const float vent = C[9];
    memset(e.couv, 0, sizeof e.couv);
    float lam[70];
    for (int b = 0; b < nb; b++) {
      const int i = n0 + b;
      const float u = (e.x0[i] + c * 6) * 0.05f - t * 0.5f;      // le vent passe en vagues, de gauche a droite
      float raf = 0.5f + 0.5f * sinf(u + 0.7f * sinf(u * 0.43f + 1.1f));
      raf = raf * raf * raf * rf;
      lam[b] = e.incl[i] + vent * (raf * 0.9f - 0.1f) + 0.07f * vent * sinf(t * 1.6f * e.fr[i] + e.ph[i]) + e.courbe[i];
      const float k16 = 1 - 0.16f * lam[b] * lam[b];
      for (int k = 0; k < np; k++) {
        const float s = k / (float)(np - 1);
        nf_brin(e.couv, e.x0[i] + lam[b] * e.h[i] * 0.55f * s * s, e.pied[i] - e.h[i] * s * k16, C[3] + (C[4] - C[3]) * s,
                1.1f * lam[b] * s / k16);
      }
    }
    for (int p = 0; p < 4096; p++) {
      const float a = e.couv[p];
      if (a <= 0) continue;
      const float j = e.jour[p] * ij * C[8];
      nf_melanger(p >> 6, p & 63, a, C[5] + j * 255, C[6] + j * 196, C[7] + j * 110);
    }
    if (C[11] > 0) {                                              // les epis, qui s'allument a contre-jour
      memset(e.couv, 0, sizeof e.couv);
      for (int b = 0; b < nb; b++) {
        const int i = n0 + b;
        if (!e.epi[i]) continue;
        const float k16 = 1 - 0.16f * lam[b] * lam[b];
        for (int k = 0; k < np; k++) {
          const float s = k / (float)(np - 1);
          if (s <= 0.76f) continue;
          const float de = C[12] * powf(sinf(NF_PI * borne((s - 0.76f) / 0.24f, 0, 1)), 0.7f);
          nf_brin(e.couv, e.x0[i] + lam[b] * e.h[i] * 0.55f * s * s, e.pied[i] - e.h[i] * s * k16, de + 0.15f, 1.1f * lam[b] * s / k16);
        }
      }
      for (int p = 0; p < 4096; p++) {
        const float a = e.couv[p];
        if (a <= 0) continue;
        float j = e.jour[p] * ij;
        if (c >= 2) j = powf(j, 2.2f);
        nf_melanger(p >> 6, p & 63, a, C[13] + j * C[16], C[14] + j * C[17], C[15] + j * C[18]);
      }
    }
    n0 += nb;
  }
  for (int i = 0; i < 14; i++) {                                  // des graines portees par le vent
    const float gx = fmodf(e.gx0[i] + t * e.gv[i], 84.0f) - 10;
    const float gy = e.gy0[i] + 4 * sinf(t * 0.23f + e.gp[i]) + 1.5f * sinf(t * 0.71f + e.gp[i] * 2.3f);
    const float lum = e.jour[(int)borne(gy, 0, 63) * 64 + (int)borne(gx, 0, 63)] * ij;
    const float k = (0.25f + 0.85f * lum) * e.gk[i];
    nf_tache(gy, gx, 255 * k, 236 * k, 190 * k);
  }
  for (int k = 0; k < 4; k++) {                                   // des moucherons qui dansent dans la lumiere
    const float mx = 44 + 6 * sinf(t * 0.37f + k * 1.7f) + 1.5f * sinf(t * 2.9f + k * 3);
    const float my = 31 + 3 * sinf(t * 0.53f + k * 2.2f) + 1.2f * sinf(t * 3.7f + k);
    nf_tache(my, mx, 230, 215, 180);
  }
}

// --- La grande plaine : un terrain vu en perspective, les ombres des nuages qui glissent dessus ---
// humeurs : 0 = Grande plaine
const float NF_PL_H = 30.0f, NF_PL_F = 40.0f, NF_PL_OEIL = 1.6f, NF_PL_NUAGES = 6.0f, NF_PL_S = 3.2f, NF_PL_G = 5.5f;
static inline float nf_pl_relief(float w, float z, float *dw = nullptr, float *dz = nullptr) {
  const float a1 = 0.45f * w + 0.31f * z + 0.6f, a2 = 0.17f * z + 0.2f * w, a3 = 0.2f * w - 0.45f * z + 2.0f, a4 = 1.1f * w + 0.7f * z;
  const float s1 = sinf(a1), s2 = sinf(a2), s3 = sinf(a3), s4 = sinf(a4);
  if (dw) {
    const float c1 = cosf(a1), c2 = cosf(a2), c3 = cosf(a3), c4 = cosf(a4);
    *dw = 0.42f * (0.45f * c1 * (0.6f + 0.4f * s2) + s1 * 0.08f * c2) + 0.044f * c3 + 0.11f * c4;
    *dz = 0.42f * (0.31f * c1 * (0.6f + 0.4f * s2) + s1 * 0.068f * c2) - 0.099f * c3 + 0.07f * c4;
  }
  return 0.42f * s1 * (0.6f + 0.4f * s2) + 0.22f * s3 + 0.1f * s4;
}
struct NF_PlaineFin {
  uint16_t Z[64 * 64], W[64 * 64];   // la profondeur (x163.8 ; 65535 : le ciel), le cote ((w + 128) x 256)
  uint8_t herbe[64 * 64][3];
  uint8_t voile[64 * 64];
};
union NF_PlaineTravail {
  NF_PlaineFin f;
  uint16_t brume5[128 * 128];         // (le second champ des nuages, le temps de les meler)
};
struct E_plaine {
  uint16_t champ[128 * 128];         // les nuages, et leurs ombres au sol
  NF_PlaineTravail w;
  uint8_t ciel[32 * 64][3];
  uint16_t feuilles[64 * 64];
  float ax, ay, bx[7], by[7], bz[7];
};
void nf_plaine_preparer(E_plaine &e) {
  brume_n(e.champ, 128, 20);
  brume_n(e.w.brume5, 128, 5);
  for (int i = 0; i < 128 * 128; i++) e.champ[i] = (uint16_t)(e.champ[i] * 0.8f + e.w.brume5[i] * 0.2f);
  uint16_t mn = 65535, mx = 0;
  for (int i = 0; i < 128 * 128; i++) { mn = min(mn, e.champ[i]); mx = max(mx, e.champ[i]); }
  for (int i = 0; i < 128 * 128; i++) e.champ[i] = (uint16_t)((e.champ[i] - mn) * (65535.0f / fmaxf(1.0f, (float)(mx - mn))));
  NF_PlaineFin &P = e.w.f;
  uint16_t *taches = e.feuilles;      // des pres plus jaunes, d'autres plus sombres (un moment)
  brume_n(taches, 64, 4);
  for (int i = 0; i < 4096; i++) { P.Z[i] = 65535; P.W[i] = 32768; P.voile[i] = 0; P.herbe[i][0] = P.herbe[i][1] = P.herbe[i][2] = 0; }
  float ybuf[64];
  for (int x = 0; x < 64; x++) ybuf[x] = 64.0f;
  for (int k = 0; k < 220; k++) {     // du plus pres au plus loin, colonne par colonne
    const float z = 1.2f * powf(160.0f / 1.2f, k / 219.0f);
    for (int x = 0; x < 64; x++) {
      const float w = (x - 31.5f) * z / NF_PL_F;
      float hw, hz;
      const float h = nf_pl_relief(w, z, &hw, &hz);
      const float ys = NF_PL_H + (NF_PL_OEIL - h) * NF_PL_F / z;
      const float lum = borne((0.6f * hw + 0.6f + 0.5f * hz) / sqrtf(1 + hw * hw + hz * hz), 0, 1);   // le soleil a gauche, en face
      const int y0 = max(0, (int)ceilf(ys - 0.5f));
      for (int y = y0; y < 64 && y < ybuf[x] - 0.5f; y++) {
        const int i = y * 64 + x;
        P.Z[i] = (uint16_t)roundf(z * 163.8375f);
        P.W[i] = (uint16_t)roundf(borne((w + 128) * 256, 0, 65535));
        const float tq = nf_lire(taches, 64, z * 2.0f, w * 2.0f);
        const float kt = 0.86f + 0.28f * tq;
        P.herbe[i][0] = (uint8_t)borne(roundf((26 + 86 * lum) * kt), 0, 255);
        P.herbe[i][1] = (uint8_t)borne(roundf((64 + 102 * lum) * kt), 0, 255);
        P.herbe[i][2] = (uint8_t)borne(roundf((34 + 24 * lum) * kt), 0, 255);
        P.voile[i] = (uint8_t)roundf((1 - expf(-z / 38.0f)) * 255);
      }
      ybuf[x] = fminf(ybuf[x], ys);
    }
  }
  for (int y = 0; y < 32; y++) {
    const float k = borne(y / NF_PL_H, 0, 1);
    const float hz = expf(-((y - NF_PL_H + 6) / 4.5f) * ((y - NF_PL_H + 6) / 4.5f)) * 0.22f;
    for (int x = 0; x < 64; x++) {
      float c[3] = {28 + 118 * k, 64 + 116 * k, 140 + 60 * k};
      float g = borne(1 - sqrtf((x + 6.0f) * (x + 6.0f) + (y + 6.0f) * (y + 6.0f)) / 44, 0, 1);   // le soleil, hors champ
      g *= g;
      c[0] += g * 70; c[1] += g * 60; c[2] += g * 26;
      c[0] += hz * (235 - c[0]); c[1] += hz * (238 - c[1]); c[2] += hz * (240 - c[2]);     // des nuages au loin, fondus
      for (int i = 0; i < 3; i++) e.ciel[y * 64 + x][i] = (uint8_t)borne(roundf(c[i]), 0, 255);
    }
  }
  const float tz = 6.4f, tw = 2.2f;                                 // l'arbre seul, sur une butte
  e.ax = 31.5f + tw * NF_PL_F / tz;
  e.ay = NF_PL_H + (NF_PL_OEIL - nf_pl_relief(tw, tz)) * NF_PL_F / tz;
  static const float ZL[7] = {14, 18, 22, 27, 33, 40, 52};          // quelques arbres au loin
  for (int i = 0; i < 7; i++) {
    const float wl = hasard(-0.35f, 0.35f) * ZL[i];
    e.bx[i] = 31.5f + wl * NF_PL_F / ZL[i];
    e.by[i] = NF_PL_H + (NF_PL_OEIL - nf_pl_relief(wl, ZL[i])) * NF_PL_F / ZL[i];
    e.bz[i] = ZL[i];
  }
  brume_n(e.feuilles, 64, 2);
}
void s_plaine(int humeur, bool debut, float t, float ecoule, float dt) {
  E_plaine &e = etat_ecran<E_plaine>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) nf_plaine_preparer(e);
  NF_PlaineFin &P = e.w.f;
  const float dx = t * 0.22f, dz = -t * 0.07f;                      // le vent pousse les nuages vers la droite
  const float S = NF_PL_S, G = NF_PL_G, K = NF_PL_F * (NF_PL_NUAGES - NF_PL_OEIL);
  for (int y = 0; y < 64; y++) {
    const float zc = K / fmaxf(NF_PL_H - y, 0.5f), zh = K / fmaxf(NF_PL_H - y - 1.5f, 0.5f), zb = K / fmaxf(NF_PL_H - y + 1.5f, 0.5f);
    const float haut = borne((NF_PL_H - 9 - y) / 8, 0, 1);         // vers l'horizon, les nuages se fondent dans la brume
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const bool sol = y > NF_PL_H - 2 && P.Z[i] != 65535;
      if (!sol) {
        const uint8_t *c = e.ciel[min(y, 31) * 64 + x];
        float r = c[0], g = c[1], b = c[2];
        if (haut > 0) {                                              // le dessus des nuages au soleil, le dessous gris
          const float u = (x - 31.5f) / NF_PL_F * S;
          const float F = nf_lire(e.champ, 128, (zc + dz) * S, zc * u + dx * S);
          const float a = borne((F - 0.5f) * 4.0f, 0, 1) * haut * 0.96f;
          if (a > 0) {
            const float Fh = nf_lire(e.champ, 128, (zh + dz) * S, zh * u + dx * S);
            const float Fb = nf_lire(e.champ, 128, (zb + dz) * S, zb * u + dx * S);
            const float rl = borne(0.55f + (Fb - Fh) * 7 + (F - 0.5f) * 1.2f, 0, 1);
            r += (118 + 120 * rl - r) * a; g += (128 + 110 * rl - g) * a; b += (160 + 74 * rl - b) * a;
          }
        }
        peindre(y, x, r, g, b);
        continue;
      }
      const float Z = P.Z[i] * (1.0f / 163.8375f), Wv = P.W[i] * (1.0f / 256) - 128;
      const float F = nf_lire(e.champ, 128, (Z + dz) * G, (Wv + 0.8f + dx) * G);
      const float dens = borne((F - 0.5f) * 4.0f, 0, 1);
      const float ombre = dens > 0 && Z < 40 ? dens * nf_exp(-(Z / 11) * (Z / 11)) : 0.0f;
      float vague = 0;
      if (Z < 20) {                                                   // le vent passe en vagues dans l'herbe, par rafales
        float v = 0.5f + 0.5f * nf_sin(3.6f * Wv - 2.7f * Z - t * 1.5f + 1.2f * nf_sin(0.5f * Wv + 0.4f * Z + t * 0.05f));
        v *= v; v *= v;
        vague = v * nf_exp(-(Z / 6) * (Z / 6)) * (0.35f + 0.65f * (0.5f + 0.5f * nf_sin(0.45f * Wv - 0.35f * Z - t * 0.3f)));
      }
      const float ko = 1 - 0.55f * ombre, kv = vague * (1 - 0.6f * ombre), vo = P.voile[i] * (1.0f / 255);
      const uint8_t *h = P.herbe[i];
      peindre(y, x, (h[0] * ko + kv * 46) * (1 - vo) + 150 * vo, (h[1] * ko + kv * 54) * (1 - vo) + 178 * vo,
              (h[2] * ko + kv * 18) * (1 - vo) + 190 * vo);
    }
  }
  for (int i = 0; i < 7; i++) {
    const float h = 0.55f * NF_PL_F / e.bz[i], q = e.bz[i] / 70;
    const float tr[1][6] = {{e.by[i] - h * 0.4f, e.bx[i], e.by[i] - h * 1.2f, e.bx[i], h * 0.55f, h * 0.4f}};
    nf_traits(tr, 1, 30 * (1 - q) + 150 * q, 66 * (1 - q) + 178 * q, 40 * (1 - q) + 190 * q);
  }
  const float ax = e.ax, ay = e.ay;                                 // l'arbre : son ombre, son tronc, sa couronne
  for (int y = max(0, (int)(ay - 1)); y < min(64, (int)(ay + 3)); y++)
    for (int x = max(0, (int)(ax - 1)); x < min(64, (int)(ax + 9)); x++) {
      const float d = sqrtf(((x - ax - 3.5f) / 4.2f) * ((x - ax - 3.5f) / 4.2f) + ((y - ay - 0.7f) / 1.2f) * ((y - ay - 0.7f) / 1.2f));
      const float k = 1 - 0.4f * borne((1 - d) * 2, 0, 1);
      scene[y][x][0] *= k; scene[y][x][1] *= k; scene[y][x][2] *= k;
    }
  const float tronc[3][6] = {{ay + 0.3f, ax, ay - 5.0f, ax - 0.2f, 0.7f, 0.45f}, {ay - 4, ax, ay - 6.5f, ax + 1.8f, 0.35f, 0.25f},
                             {ay - 4.5f, ax - 0.2f, ay - 6.8f, ax - 2.0f, 0.3f, 0.25f}};
  nf_traits(tronc, 3, 36, 28, 22);
  const float cy = ay - 9.0f, bouge = 1 + 0.15f * sinf(t * 0.7f), fo = t * 0.6f;
  for (int y = max(0, (int)(cy - 7)); y < min(64, (int)(cy + 8)); y++)
    for (int x = max(0, (int)(ax - 8)); x < min(64, (int)(ax + 9)); x++) {
      const float d = sqrtf((x - ax) * 0.88f * (x - ax) * 0.88f + (y - cy) * (y - cy));
      if (d > 6.6f) continue;
      const float phi = atan2f(y - cy, x - ax);
      const float bord = 5.4f + 0.55f * sinf(phi * 5 + bouge) + 0.3f * sinf(phi * 9 + 2);
      const float co = borne(bord + 0.5f - d, 0, 1);
      if (co <= 0) continue;
      const float fe = fenetre_n(e.feuilles, 64, fo, 0, x, y);
      const float lum = borne(0.5f - (x - ax) * 0.09f - (y - cy) * 0.09f + (fe - 0.5f) * 0.7f, 0.08f, 1);
      nf_melanger(y, x, co, 18 + lum * 76, 40 + lum * 104, 22 + lum * 42);
    }
  const float k = t * 0.25f;                                        // un rapace qui tourne tres haut
  const float oy = 10 + 3 * sinf(k), ox = 16 + 8 * cosf(k), aile = 0.5f + 0.5f * sinf(t * 0.8f);
  poser(oy - aile, ox - 1, 40, 50, 70); poser(oy, ox, 40, 50, 70); poser(oy - aile, ox + 1, 40, 50, 70);
}

// --- La montagne : l'alpenglow glisse sur ses faces au fil d'un long cycle ---
// humeurs : 0 = Montagne et alpenglow
const float NF_MONT_PERIODE = 120.0f;
static const float NF_MONT_LUM_C[5] = {0.0f, 0.4f, 0.65f, 0.85f, 1.0f};
static const float NF_MONT_LUM[5][3] = {{255, 230, 194}, {255, 190, 130}, {252, 146, 126}, {240, 104, 126}, {200, 88, 140}};
static const float NF_MONT_AMB_C[4] = {0.0f, 0.6f, 0.85f, 1.0f};
static const float NF_MONT_AMB[4][3] = {{80, 94, 130}, {82, 78, 124}, {98, 74, 128}, {60, 66, 118}};
static const float NF_MONT_HAUT_C[3] = {0.0f, 0.55f, 1.0f};
static const float NF_MONT_HAUT[3][3] = {{44, 84, 148}, {42, 52, 112}, {10, 12, 40}};
static const float NF_MONT_BAS_C[4] = {0.0f, 0.5f, 0.8f, 1.0f};
static const float NF_MONT_BAS[4][3] = {{236, 200, 162}, {248, 158, 126}, {150, 88, 136}, {48, 42, 92}};
struct E_montagne {
  uint16_t nuees[128 * 128], vallee[128 * 128];
  uint8_t dedans[64 * 64], face[64 * 64];   // face x170
  uint8_t albedo[64 * 64][3];              // x255
  float loin[64], pres[64], devant[64];
  float ex[40], ey[40], ep[40], el[40];
  float cx[5], cy[5], cp[5];
};
void nf_montagne_preparer(E_montagne &e) {
  uint16_t *tex = e.vallee;                 // (un moment : les eboulis)
  brume_n(tex, 64, 2);
  static const float LANGUES[9][4] = {{8, -0.5f, 6, 2.5f}, {14, -0.45f, 9, 3.0f}, {20.5f, -0.3f, 12, 3.2f}, {26, -0.15f, 7, 2.2f},
                                      {35, 0.2f, 11, 3.0f}, {41, 0.3f, 8, 2.6f}, {47, 0.4f, 10, 3.0f}, {54, 0.5f, 7, 2.6f}, {60, 0.55f, 5, 2.4f}};
  static const float COTES[3][4] = {{11, 25.5f, 19, 20.5f}, {12, 35, 20, 39.5f}, {17, 46, 23, 50}};
  float crete[64];
  for (int x = 0; x < 64; x++) {
    float c = x < 30 ? 4 + (30 - x) * 1.15f : fminf(4 + (x - 30) * 1.3f, 15 + fabsf(x - 46.0f) * 0.8f);
    c += 0.7f * sinf(x * 1.3f + 0.5f) * borne(fabsf(x - 30.0f) / 5, 0, 1) * borne(fabsf(x - 46.0f) / 3, 0.3f, 1);
    crete[x] = c;
    e.loin[x] = 22 + fabsf(x - 6.0f) * 0.8f + 0.6f * sinf(x * 1.1f);   // un sommet plus loin, a gauche
  }
  for (int y = 0; y < 64; y++) {
    const float ag = 30 + (y - 4) * 0.13f + 0.6f * sinf(y * 0.45f);       // l'arete : la face au soleil, la face a l'ombre
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      e.dedans[i] = (uint8_t)roundf(borne(y - crete[x] + 0.5f, 0, 1) * 255);
      float face = 0.3f + 0.7f * borne((ag - x) / 1.2f + 0.5f, 0, 1);
      face += 0.12f * borne(1 - fabsf(x - ag + 0.6f) / 0.8f, 0, 1);       // l'arete accroche la lumiere
      face += 0.35f * borne(1 - fabsf(x - 45.5f + (y - 15) * 0.3f) / 1.0f, 0, 1) * borne((25 - y) / 6.0f, 0, 1);
      e.face[i] = (uint8_t)roundf(borne(face, 0, 1.5f) * 170);
      float lim = 19.5f + 1.8f * sinf(x * 0.3f + 1) + 1.0f * sinf(x * 0.9f);   // le bas du champ de neige, ses langues
      for (int k = 0; k < 9; k++) {
        const float dx = fabsf(x - LANGUES[k][0] - LANGUES[k][1] * (y - 19.5f)) / LANGUES[k][3];
        const float q = borne(1 - dx, 0, 1);
        if (q > 0) lim += LANGUES[k][2] * powf(q, 1.6f);
      }
      float neige = borne((lim - y) / 1.1f, 0, 1);
      for (int k = 0; k < 3; k++) {                                     // des cotes de rocher trop raides pour la neige
        const float y0 = COTES[k][0], x0 = COTES[k][1], y1 = COTES[k][2], x1 = COTES[k][3];
        const float u = borne(((x - x0) * (x1 - x0) + (y - y0) * (y1 - y0)) / ((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0)), 0, 1);
        const float d = sqrtf((x - x0 - u * (x1 - x0)) * (x - x0 - u * (x1 - x0)) + (y - y0 - u * (y1 - y0)) * (y - y0 - u * (y1 - y0)));
        neige *= 0.35f + 0.65f * borne(d / 0.9f, 0, 1);
      }
      if (y > 8) neige *= borne(fabsf(x - ag - 0.9f) / 0.6f, 0, 1);       // l'arete, rocheuse cote ombre
      const float gorges = nf_lire(tex, 64, y * 0.3f, x * 1.2f);           // des eboulis, en long ; des strates
      const float kr = 0.8f + 0.3f * gorges + 0.08f * sinf(y * 0.9f + x * 0.25f);
      const float bas = borne((y - 34) / 10.0f, 0, 1);                    // en bas, les alpages et les forets
      const float roche[3] = {0.36f * kr * (1 - bas) + 0.15f * bas, 0.33f * kr * (1 - bas) + 0.21f * bas, 0.33f * kr * (1 - bas) + 0.17f * bas};
      const float blanc[3] = {0.78f, 0.81f, 0.87f};
      for (int c = 0; c < 3; c++) e.albedo[i][c] = (uint8_t)roundf(borne(roche[c] * (1 - neige) + blanc[c] * neige, 0, 1) * 255);
    }
  }
  float base[64], b2[64];
  for (int x = 0; x < 64; x++) { base[x] = 48 + 1.2f * sinf(x * 0.15f); b2[x] = 59.5f + 1.5f * sinf(x * 0.2f + 1); }
  nf_cimes(34, base, 2, 5, 0.9f, false, e.pres);
  nf_cimes(18, b2, 4, 9, 0.65f, false, e.devant);
  for (int i = 0; i < 40; i++) { e.ex[i] = hasard(0, 64); e.ey[i] = hasard(0, 30); e.ep[i] = hasard(0, 6); e.el[i] = hasard(0.4f, 1); }
  for (int i = 0; i < 5; i++) {
    e.cx[i] = hasard(4, 60);
    e.cy[i] = fminf(e.devant[(int)e.cx[i]] - 2, 53 + hasard(0, 2));
    e.cp[i] = hasard(0, 6);
  }
  brume_n(e.nuees, 128, 7);
  brume_n(e.vallee, 128, 10);
}
void s_montagne(int humeur, bool debut, float t, float ecoule, float dt) {
  E_montagne &e = etat_ecran<E_montagne>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) nf_montagne_preparer(e);
  const float s = 0.5f - 0.5f * cosf(PI2 * (t / NF_MONT_PERIODE));   // 0 : plein jour dore ; 1 : l'heure bleue
  const float m = s > 0 ? powf(s, 0.6f) : 0.0f;                     // la lumiere s'attarde sur les hauteurs
  float lu[3], am[3], cb[3], ch[3];
  nf_palette(m, 5, NF_MONT_LUM_C, NF_MONT_LUM, lu[0], lu[1], lu[2]);
  nf_palette(s, 4, NF_MONT_AMB_C, NF_MONT_AMB, am[0], am[1], am[2]);
  nf_palette(s, 4, NF_MONT_BAS_C, NF_MONT_BAS, cb[0], cb[1], cb[2]);
  nf_palette(s, 3, NF_MONT_HAUT_C, NF_MONT_HAUT, ch[0], ch[1], ch[2]);
  degrade2(ch[0], ch[1], ch[2], cb[0], cb[1], cb[2], 0, 46);
  const float nuit = borne((s - 0.8f) / 0.15f, 0, 1);
  if (nuit > 0)
    for (int i = 0; i < 40; i++) {
      const float k = e.el[i] * nuit * (0.6f + 0.4f * sinf(t * 1.9f + e.ep[i]));
      pointer(e.ey[i], e.ex[i], 210 * k, 210 * k, 240 * k);
    }
  const float kr = fminf(1.0f, m * 2.5f);
  const float fo = t * 1.8f, fv = t * 0.15f, vo = t * 0.7f;
  for (int x = 0; x < 64; x++) {
    const float ligne = 52 - m * 50 + 2.0f * sinf(x * 0.09f + 1);    // l'ombre de la terre qui monte, puis redescend
    const float lo = e.loin[x];
    const float pq = (x - 30) * 0.2f, pw = 1.0f + fabsf(x - 30.0f) * 0.1f;
    const float pk = borne((x - 27) / 4.0f, 0, 1) * expf(-fmaxf(x - 30.0f, 0.0f) / 20);
    for (int y = 0; y < 64; y++) {
      float *p = scene[y][x];
      const float ec = borne((ligne - y) / 3.0f, 0, 1);
      const float rose = borne(1 - fabsf(y - ligne) / 9, 0, 1) * kr * 0.3f;   // tout pres de la limite, la lumiere rougit
      const float l[3] = {lu[0] * (1 - rose) + 255 * rose, lu[1] * (1 - rose) + 96 * rose, lu[2] * (1 - rose) + 120 * rose};
      const float c = borne(y - lo + 0.5f, 0, 1);                     // le sommet du fond, voile par l'air
      if (c > 0) {
        const float nl = borne((29 - y) / 3.0f, 0, 1) * 0.35f;
        const float lc[3] = {0.5f + nl, 0.52f + nl, 0.56f + nl};
        for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - c) + (lc[k] * (am[k] + ec * l[k] * 0.7f) * 0.6f + cb[k] * 0.4f) * c;
      }
      const int i = y * 64 + x;
      const float a = e.dedans[i] * (1.0f / 255);
      if (a > 0) {
        const float fe = e.face[i] * (1.0f / 170) * ec * 0.78f;
        for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - a) + e.albedo[i][k] * (1.0f / 255) * (am[k] + fe * l[k]) * a;
      }
      const float pd = (y - 5.5f - pq) / pw;
      if (pk > 0 && pd * pd < 16) {                                   // la banniere de nuage, accrochee au sommet
        const float F = fenetre_n(e.nuees, 128, fo, fv, x, y);
        const float an = borne((F * 1.4f - 0.35f) * 2.4f, 0, 1) * nf_exp(-pd * pd) * pk * 0.9f;
        if (an > 0) {
          const float ln = borne((ligne + 3 - y) / 4.0f, 0, 1) * 0.8f;
          for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - an) + (am[k] * 1.3f + ln * lu[k]) * an;
        }
      }
      const float vl = borne((y - 38) / 10.0f, 0, 1) * 0.55f;        // l'air de la vallee, au pied
      if (vl > 0)
        for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - vl) + (cb[k] * 0.5f + am[k] * 0.5f) * vl;
      const float sp = borne(y - e.pres[x] + 0.5f, 0, 1);
      if (sp > 0) {
        const float pc[3] = {am[0] * 0.38f + 2, am[1] * 0.38f + 10, am[2] * 0.38f + 8};
        for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - sp) + pc[k] * sp;
      }
      const float q = (y - 52.5f) / 3.0f;                            // la brume de la vallee
      if (q * q < 16) {
        const float V = fenetre_n(e.vallee, 128, vo, 0, x, y);
        const float av = nf_exp(-q * q) * (0.3f + 0.55f * V);
        for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - av) + (cb[k] * 0.6f + am[k] * 0.5f) * av;
      }
    }
  }
  const float soir = borne((s - 0.72f) / 0.15f, 0, 1);              // a l'heure bleue, les chalets s'allument
  if (soir > 0)
    for (int i = 0; i < 5; i++) {
      const float v = soir * (0.85f + 0.15f * sinf(t * 1.3f + e.cp[i]));
      const float xi = e.cx[i], yi = e.cy[i];
      for (int y = max(0, (int)yi - 6); y < min(64, (int)yi + 7); y++)
        for (int x = max(0, (int)xi - 6); x < min(64, (int)xi + 7); x++)
          ajouter(y, x, nf_exp(-((x - xi) * (x - xi) + (y - yi) * (y - yi)) / 2.5f) * v * 0.45f, 255, 160, 70);
      pointer(yi, xi, 255 * v, 205 * v, 130 * v);
    }
  nf_sous(e.devant, am[0] * 0.16f + 2, am[1] * 0.16f + 6, am[2] * 0.16f + 5);
}

// --- La savane : le grand soleil qui descend, l'acacia, les girafes ---
// humeurs : 0 = Savane au couchant
const float NF_SAV_H = 46.0f;
void nf_girafe(float x, float sol, float k, float pas, float sens, const float *c) {
  if (x + 9 * k < 0 || x - 9 * k > 64) return;
  const float s = sens, hoche = 0.5f * k * sinf(2 * pas);           // le cou se balance avec les pas
  float tr[9][6] = {
    {sol - 8.7f * k, x - 2.4f * k * s, sol - 9.7f * k, x + 2.3f * k * s, 1.45f * k, 1.6f * k},                       // le corps
    {sol - 9.9f * k, x + 2.5f * k * s, sol - 17.6f * k, x + (4.9f * k + hoche) * s, 0.95f * k, 0.5f * k},            // le cou
    {sol - 17.8f * k, x + (4.8f * k + hoche) * s, sol - 17.0f * k, x + (6.7f * k + hoche) * s, 0.6f * k, 0.35f * k},
    {sol - 18.0f * k, x + (5.0f * k + hoche) * s, sol - 19.2f * k, x + (4.8f * k + hoche) * s, 0.2f, 0.2f},
    {sol - 9.2f * k, x - 3.7f * k * s, sol - 5.6f * k, x - 4.2f * k * s, 0.2f, 0.25f}};                               // la queue
  static const float PATTES[4][2] = {{-2.3f, 0.0f}, {-1.9f, NF_PI}, {2.0f, 0.0f}, {2.4f, NF_PI}};   // l'amble
  for (int j = 0; j < 4; j++) {
    const float ph = pas + PATTES[j][1];
    const float pied = x + (PATTES[j][0] + 1.2f * sinf(ph)) * k * s;
    const float leve = fmaxf(0.0f, cosf(ph)) * 0.7f * k;
    const float p[6] = {sol - 8.2f * k, x + PATTES[j][0] * k * s, sol - leve, pied, 0.42f * k, 0.28f * k};
    for (int q = 0; q < 6; q++) tr[5 + j][q] = p[q];
  }
  nf_traits(tr, 9, c[0], c[1], c[2]);
}
struct E_savane {
  uint16_t stries[128 * 128];
  uint8_t acacia[64 * 64], buissons[64 * 64];
  float couv[64 * 64];
  float ox0[5], oy0[5], op[5];
  float tx[26], th[26], tc[26], tp[26];
};
void s_savane(int humeur, bool debut, float t, float ecoule, float dt) {
  E_savane &e = etat_ecran<E_savane>(debut);
  (void)humeur; (void)dt;
  const float H = NF_SAV_H;
  if (debut) {
    static const float HOUPPES[4][4] = {{50, 28.6f, 13.0f, 2.4f}, {43.5f, 30.0f, 6.5f, 2.0f}, {57.5f, 30.2f, 6.0f, 1.9f}, {50.5f, 27.2f, 8.5f, 1.6f}};
    memset(e.couv, 0, sizeof e.couv);
    const float tronc[5][6] = {{H + 0.5f, 49.0f, 36.0f, 49.4f, 1.0f, 0.75f}, {37.5f, 49.4f, 31.0f, 44.0f, 0.6f, 0.4f},
                               {37.5f, 49.4f, 30.5f, 55.0f, 0.6f, 0.4f}, {40.0f, 49.2f, 31.0f, 50.5f, 0.45f, 0.35f},
                               {34.0f, 46.0f, 31.0f, 40.0f, 0.35f, 0.3f}};
    nf_traits(tronc, 5, 1, 1, 1, 1.0f, e.couv);
    float bx[6], by[6], br[6];
    for (int i = 0; i < 6; i++) { bx[i] = hasard(2, 62); by[i] = H + hasard(1.5f, 4); br[i] = hasard(1.0f, 2.0f); }
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        float a = e.couv[y * 64 + x];                                // l'acacia : un masque fixe
        for (int k = 0; k < 4; k++) {
          const float bord = 1 + 0.12f * sinf(x * 1.3f + HOUPPES[k][1]) + 0.1f * sinf(x * 2.9f);
          const float qx = (x - HOUPPES[k][0]) / HOUPPES[k][2], qy = (y - HOUPPES[k][1]) / HOUPPES[k][3];
          a = fmaxf(a, borne((bord - qx * qx - qy * qy) * HOUPPES[k][3] * 1.2f, 0, 1));
        }
        e.acacia[y * 64 + x] = (uint8_t)roundf(a * 255);
        float b = 0;                                                 // des buissons epars
        for (int k = 0; k < 6; k++)
          if (y <= by[k] + 0.5f) b = fmaxf(b, borne(br[k] + 0.5f - sqrtf((x - bx[k]) * 0.7f * (x - bx[k]) * 0.7f + (y - by[k]) * (y - by[k])), 0, 1));
        e.buissons[y * 64 + x] = (uint8_t)roundf(b * 255);
      }
    brume_n(e.stries, 128, 6);
    for (int i = 0; i < 5; i++) { e.ox0[i] = hasard(0, 90); e.oy0[i] = hasard(6, 22); e.op[i] = hasard(0, 6); }
    for (int i = 0; i < 26; i++) {                                    // des touffes d'herbe au premier plan
      e.tx[i] = i < 13 ? hasard(-2, 16) : hasard(46, 66);
      e.th[i] = hasard(4, 11); e.tc[i] = hasard(-0.5f, 0.5f); e.tp[i] = hasard(0, 6);
    }
  }
  const float descente = fminf(fmaxf(ecoule, 0.0f), 120.0f) / 120.0f;   // il descend, puis se pose sur l'horizon
  const float sy = 26 + descente * 15, r = 10.5f;
  const float coeur[3] = {255, 214 - 44 * descente, 120 - 40 * descente}, bordc[3] = {248 - 22 * descente, 110 - 40 * descente, 46 - 6 * descente};
  const float kh = 1 - descente * 0.3f;
  for (int y = 0; y < 64; y++) {
    float c[3];
    if (y < 30) { const float k = y / 30.0f; c[0] = 44 + 116 * k; c[1] = 12 + 34 * k; c[2] = 40; }
    else { const float k = borne((y - 30) / 16.0f, 0, 1); c[0] = 160 + 90 * k; c[1] = 46 + 78 * k; c[2] = 40 + 4 * k; }
    for (int x = 0; x < 64; x++) {
      const float d = sqrtf((x - 25.0f) * (x - 25.0f) + (y - sy) * (y - sy));
      float g = borne(1 - d / 34, 0, 1);
      g = g * g * kh;
      float p[3] = {c[0] + g * 90, c[1] + g * 40, c[2] + g * 6};
      const float di = borne(r + 0.5f - d, 0, 1);
      if (di > 0) {
        const float k = borne(d / r, 0, 1), k2 = k * k;
        for (int i = 0; i < 3; i++) p[i] = p[i] * (1 - di) + (coeur[i] * (1 - k2) + bordc[i] * k2) * di;
      }
      peindre(y, x, p[0], p[1], p[2]);
    }
  }
  static const float STRIES[3][4] = {{20.0f, 1.0f, 0.25f, 0.0f}, {29.5f, 0.8f, 0.4f, 40.0f}, {35.0f, 1.3f, 0.3f, 80.0f}};
  for (int k = 0; k < 3; k++) {                                       // de longs nuages fins devant le soleil
    const float yk = STRIES[k][0], ep = STRIES[k][1], v = STRIES[k][2], ph = STRIES[k][3];
    for (int x = 0; x < 64; x++) {
      const float lg = borne((nf_lire(e.stries, 128, ph, x * 0.8f - t * v) - 0.42f) * 3, 0, 1) * 0.75f;
      if (lg <= 0) continue;
      const float yc = yk + 0.8f * sinf(x * 0.07f + ph);
      for (int y = max(0, (int)(yc - 4 * ep)); y < min(64, (int)(yc + 4 * ep) + 2); y++) {
        const float q = (y - yc) / ep;
        nf_melanger(y, x, nf_exp(-q * q) * lg, 70, 20, 42);
      }
    }
  }
  float crete[64];
  for (int x = 0; x < 64; x++) {                                      // des collines plates, dans la brume chaude
    const float mesa = fminf(borne(9 - fabsf(x - 10.0f) * 0.9f, 0, 4.5f), 4.5f) + borne(5 - fabsf(x - 60.0f) * 0.6f, 0, 3);
    crete[x] = H - mesa - 0.3f * sinf(x * 0.7f);
  }
  nf_sous(crete, 120, 42, 46);
  for (int yy = (int)H - 8; yy <= (int)H; yy++) {                     // l'air chaud fait trembler l'horizon
    const float f = 0.35f * sinf(t * 2.6f + yy * 1.7f) * (yy - H + 9) / 9;
    const float af = fabsf(f);
    float ligne[64][3];
    memcpy(ligne, scene[yy], sizeof ligne);
    for (int x = 0; x < 64; x++) {
      const float *v = ligne[f > 0 ? (x + 63) & 63 : (x + 1) & 63];
      for (int c = 0; c < 3; c++) scene[yy][x][c] = ligne[x][c] * (1 - af) + v[c] * af;
    }
  }
  float sol[64];
  for (int x = 0; x < 64; x++) sol[x] = H + 0.4f * sinf(x * 0.9f) + 0.3f * sinf(x * 2.3f);
  nf_sous(sol, 34, 12, 16);
  for (int y = (int)H + 2; y < 64; y++) {
    const float k = (y - H) / 18.0f;
    for (int x = 0; x < 64; x++) peindre(y, x, 38 - 26 * k, 13 - 8 * k, 18 - 10 * k);
  }
  for (int x = 0; x < 64; x++)                                        // le bord de l'herbe accroche la lumiere
    for (int y = max(0, (int)(sol[x] - 1)); y < min(64, (int)(sol[x] + 3)); y++) {
      const float l = borne(1 - fabsf(y - sol[x] - 0.5f), 0, 1) * 0.5f;
      if (l > 0) nf_melanger(y, x, l, 170, 60, 36);
    }
  const float SIL[3] = {16, 6, 12};
  for (int i = 0; i < 4096; i++) {
    if (e.buissons[i]) nf_melanger(i >> 6, i & 63, e.buissons[i] * (1.0f / 255), SIL[0] * 1.3f, SIL[1] * 1.3f, SIL[2] * 1.3f);
    if (e.acacia[i]) nf_melanger(i >> 6, i & 63, e.acacia[i] * (1.0f / 255), SIL[0], SIL[1], SIL[2]);
  }
  static const float GIRAFES[5][5] = {{92.0f, 1.0f, -1, 1.1f, 0}, {92.0f, 0.72f, -1, 1.1f, 9}, {92.0f, 0.95f, -1, 1.1f, 23},
                                      {-30.0f, 0.5f, 1, 0.55f, 0}, {-30.0f, 0.42f, 1, 0.55f, 6}};
  for (int g = 0; g < 5; g++) {
    const float x0 = GIRAFES[g][0], k = GIRAFES[g][1], sens = GIRAFES[g][2], v = GIRAFES[g][3], ecart = GIRAFES[g][4];
    const float q = fmodf(t * v + (sens < 0 ? 0 : 37), 150.0f);
    nf_girafe(x0 + sens * q - ecart * sens, H + (k > 0.6f ? 4.0f : 0.5f) * k + 0.5f, k, q * 1.15f / k + ecart, sens, SIL);
  }
  memset(e.couv + 48 * 64, 0, 16 * 64 * sizeof(float));             // les touffes devant, qui bougent a peine
  for (int i = 0; i < 26; i++) {
    const float lam = e.tc[i] + 0.12f * sinf(t * 0.9f + e.tp[i]);
    for (int k = 0; k < 12; k++) {
      const float s = k / 11.0f;
      nf_brin(e.couv, e.tx[i] + lam * e.th[i] * s * s, 64.5f - e.th[i] * s, 0.45f - 0.25f * s, 2 * lam * s);
    }
  }
  for (int y = 48; y < 64; y++) {
    const float po = borne((64 - y) / 9.0f, 0, 1), p2 = po * po;    // leurs pointes prennent un peu de lumiere
    for (int x = 0; x < 64; x++) {
      const float a = e.couv[y * 64 + x];
      if (a > 0) nf_melanger(y, x, a, 10 + p2 * 110, 4 + p2 * 40, 7 + p2 * 22);
    }
  }
  for (int i = 0; i < 5; i++) {                                       // des oiseaux qui passent
    const float bx = fmodf(e.ox0[i] + t * 3.2f, 100.0f) - 18;
    const float by = e.oy0[i] + sinf(t * 0.4f + e.op[i]) * 1.5f;
    const float aile = 0.5f + 0.5f * sinf(t * 5 + e.op[i] * 3);
    poser(by - aile, bx - 1, SIL[0] * 2, SIL[1] * 2, SIL[2] * 2);
    poser(by, bx, SIL[0] * 2, SIL[1] * 2, SIL[2] * 2);
    poser(by - aile, bx + 1, SIL[0] * 2, SIL[1] * 2, SIL[2] * 2);
  }
}

// --- Les eoliennes au crepuscule : les pales tournent, les feux s'allument ensemble ---
// humeurs : 0 = Eoliennes au crepuscule
// (x du pied, y du pied, hauteur du mat, longueur des pales, vitesse (rad/s), profondeur 0 loin .. 1 pres)
static const float NF_EOL[5][6] = {{8.0f, 46.5f, 7.5f, 3.4f, 0.55f, 0.12f}, {27.0f, 46.0f, 9.5f, 4.3f, 0.62f, 0.22f},
                                   {60.0f, 47.0f, 9.0f, 4.0f, 0.5f, 0.2f}, {46.5f, 50.0f, 18.0f, 7.6f, 0.47f, 0.55f},
                                   {18.0f, 58.5f, 34.0f, 13.5f, 0.4f, 1.0f}};
struct E_eoliennes {
  uint16_t stratus[128 * 128];
  uint16_t ciel[64 * 64][3];         // x64
  uint8_t lune[64 * 64];
  float lueurs[64 * 64];
  float ex[45], ey[45], ep[45], el[45];
  float vx[7], vp[7], rotors[5];
};
void s_eoliennes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_eoliennes &e = etat_ecran<E_eoliennes>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        float c[3];
        if (y < 30) { const float k = y / 30.0f; c[0] = 10 + 60 * k; c[1] = 12 + 32 * k; c[2] = 40 + 56 * k; }
        else { const float k = borne((y - 30) / 17.0f, 0, 1); c[0] = 70 + 156 * k; c[1] = 44 + 72 * k; c[2] = 96 - 20 * k; }
        float g = borne(1 - sqrtf((x - 44) * 0.6f * (x - 44) * 0.6f + (y - 47.0f) * (y - 47.0f)) / 22, 0, 1);
        g *= g;
        const float dl = sqrtf((x - 11.0f) * (x - 11.0f) + (y - 9.0f) * (y - 9.0f));
        const float h = expf(-dl / 4) * 0.25f;
        c[0] += g * 70 + h * 120; c[1] += g * 40 + h * 110; c[2] += g * 10 + h * 90;
        for (int i = 0; i < 3; i++) e.ciel[y * 64 + x][i] = (uint16_t)roundf(borne(c[i], 0, 1023) * 64);
        const float l = borne(2.8f - dl, 0, 1) * (1 - borne(2.6f - sqrtf((x - 12.4f) * (x - 12.4f) + (y - 8.2f) * (y - 8.2f)), 0, 1));
        e.lune[y * 64 + x] = (uint8_t)roundf(l * 255);
      }
    brume_n(e.stratus, 128, 9);
    for (int i = 0; i < 45; i++) { e.ex[i] = hasard(0, 64); e.ey[i] = hasard(0, 34); e.ep[i] = hasard(0, 6); e.el[i] = hasard(0.3f, 1); }
    for (int i = 0; i < 7; i++) { e.vx[i] = hasard(30, 62); e.vp[i] = hasard(0, 6); }
    for (int i = 0; i < 5; i++) e.rotors[i] = hasard(0, PI2);
  }
  for (int i = 0; i < 4096; i++) {
    const uint16_t *c = e.ciel[i];
    peindre(i >> 6, i & 63, c[0] * (1.0f / 64), c[1] * (1.0f / 64), c[2] * (1.0f / 64));
  }
  for (int i = 0; i < 45; i++) {
    const float k = e.el[i] * borne(1 - e.ey[i] / 34, 0, 1) * (0.55f + 0.45f * sinf(t * 2.1f + e.ep[i]));
    pointer(e.ey[i], e.ex[i], 200 * k, 205 * k, 235 * k);
  }
  for (int i = 0; i < 4096; i++)
    if (e.lune[i]) nf_melanger(i >> 6, i & 63, e.lune[i] * (1.0f / 255), 235, 225, 190);
  for (int y = 21; y < 50; y++) {                                  // de longs nuages fins, roses par dessous
    const float q = (y - 35) / 4.5f, g = expf(-q * q) * 0.7f;
    for (int x = 0; x < 64; x++) {
      const float a = borne((nf_lire(e.stratus, 128, y * 1.6f, x * 0.35f + t * 0.6f) - 0.5f) * 2.5f, 0, 1) * g;
      if (a > 0) nf_melanger(y, x, a, 210, 104, 108);
    }
  }
  float cr[64];
  for (int x = 0; x < 64; x++) cr[x] = 45 + 1.5f * sinf(x * 0.09f + 1) + 0.8f * sinf(x * 0.27f);
  nf_sous(cr, 46, 32, 62);
  for (int i = 0; i < 7; i++) {                                    // un village au loin
    const float k = 0.6f + 0.15f * sinf(t * 0.7f + e.vp[i]);
    pointer(47.2f + sinf(e.vx[i]), e.vx[i], 255 * k, 190 * k, 110 * k);
  }
  for (int x = 0; x < 64; x++) cr[x] = 49 + 1.2f * sinf(x * 0.12f + 3) + 0.6f * sinf(x * 0.4f);
  nf_sous(cr, 28, 20, 42);
  const float c0 = 0.5f - 0.5f * cosf(PI2 * t / 2.4f);
  const float feu = c0 * c0 * sqrtf(c0);                           // le balisage : tous ensemble, doucement
  if (feu > 1e-4f) memset(e.lueurs, 0, sizeof e.lueurs);
  for (int i = 0; i < 5; i++) {
    const float px = NF_EOL[i][0], py = NF_EOL[i][1], mat = NF_EOL[i][2], pale = NF_EOL[i][3], v = NF_EOL[i][4], prof = NF_EOL[i][5];
    if (prof > 0.9f) {                                             // la colline devant
      for (int x = 0; x < 64; x++) cr[x] = 57.5f + 0.004f * (x - 18) * (x - 18) + 0.6f * sinf(x * 0.3f);
      nf_sous(cr, 12, 10, 22);
    }
    const float te[3] = {150 * (1 - prof) + 136 * prof, 108 * (1 - prof) + 128 * prof, 124 * (1 - prof) + 160 * prof};
    const float hy = py - mat, k = fmaxf(prof, 0.3f);
    const float mt[1][6] = {{py, px, hy, px, 0.75f * k + 0.1f, 0.4f * k + 0.1f}};
    nf_traits(mt, 1, te[0] * 0.85f, te[1] * 0.85f, te[2] * 0.85f);
    const float a0 = t * v + e.rotors[i];
    float pales[3][6];
    for (int j = 0; j < 3; j++) {
      const float a = a0 + j * PI2 / 3;
      const float p[6] = {hy, px, hy - cosf(a) * pale, px + sinf(a) * pale, 0.6f * k + 0.1f, 0.1f + 0.08f * k};
      for (int q = 0; q < 6; q++) pales[j][q] = p[q];
    }
    nf_traits(pales, 3, te[0], te[1], te[2]);
    const float na[1][6] = {{hy, px - 0.2f, hy, px + 0.2f, 0.6f * k + 0.25f, 0.6f * k + 0.25f}};
    nf_traits(na, 1, te[0] * 1.1f, te[1] * 1.1f, te[2] * 1.1f);
    if (feu <= 1e-4f) continue;
    for (int l = 0; l < (prof > 0.9f ? 2 : 1); l++) {              // la grande en a un second, a mi-hauteur
      const float ly = l == 0 ? hy - 0.8f * k : py - mat * 0.5f, s = l == 0 ? 0.8f + 4 * prof : 1.5f, f = l == 0 ? 0.6f + 0.4f * prof : 0.5f;
      const int rr = (int)ceilf(sqrtf(s * 12)) + 1;
      for (int y = max(0, (int)ly - rr); y < min(64, (int)ly + rr + 1); y++)
        for (int x = max(0, (int)px - rr); x < min(64, (int)px + rr + 1); x++)
          e.lueurs[y * 64 + x] += nf_exp(-((x - px) * (x - px) + (y - ly) * (y - ly)) / s) * f;
    }
  }
  if (feu > 1e-4f)
    for (int i = 0; i < 4096; i++)
      if (e.lueurs[i] > 0) ajouter(i >> 6, i & 63, fminf(e.lueurs[i], 1.2f) * feu, 255, 40, 24);
}

// --- Les montgolfieres au lever du soleil ---
// humeurs : 0 = Montgolfieres a l'aube
// (profondeur 0 loin .. 1 pres, depart, altitude, periode du bruleur) ; leurs fuseaux
static const float NF_MG[5][4] = {{0.2f, 10.0f, 15.0f, 11.0f}, {0.32f, 50.0f, 24.0f, 13.0f}, {0.42f, 30.0f, 9.0f, 9.5f},
                                  {0.6f, 0.0f, 22.0f, 12.0f}, {1.0f, 40.0f, 29.0f, 10.5f}};
static const int NF_MG_N[5] = {2, 2, 2, 2, 3};
static const float NF_MG_C[5][3][3] = {{{70, 130, 215}, {235, 232, 222}, {0, 0, 0}}, {{232, 70, 58}, {250, 200, 70}, {0, 0, 0}},
                                       {{128, 74, 186}, {244, 156, 196}, {0, 0, 0}}, {{40, 164, 124}, {246, 152, 52}, {0, 0, 0}},
                                       {{222, 52, 72}, {250, 220, 92}, {60, 112, 204}}};
static inline void nf_mg_ciel(int x, int y, float *c) {
  if (y < 30) { const float k = y / 30.0f; c[0] = 54 + 142 * k; c[1] = 78 + 74 * k; c[2] = 132 + 30 * k; }
  else { const float k = borne((y - 30) / 12.0f, 0, 1); c[0] = 196 + 56 * k; c[1] = 152 + 44 * k; c[2] = 162 - 26 * k; }
  const float d = sqrtf((x - 50.0f) * (x - 50.0f) + (y - 38.0f) * (y - 38.0f));
  float g = borne(1 - d / 30, 0, 1);
  g *= g;
  c[0] += g * 60; c[1] += g * 40; c[2] += g * 10;
  const float so = borne(4.6f - d, 0, 1);
  c[0] += (255 - c[0]) * so; c[1] += (238 - c[1]) * so; c[2] += (190 - c[2]) * so;
}
struct E_montgolfieres {
  uint16_t brume[128 * 128];
  uint16_t decor[64 * 64][3];        // x64
  float p1[64], p2[64], p3[64];
  float fuseaux[5];
};
void s_montgolfieres(int humeur, bool debut, float t, float ecoule, float dt) {
  E_montgolfieres &e = etat_ecran<E_montgolfieres>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        float c[3];
        nf_mg_ciel(x, y, c);
        const float mont = 39.5f + 2.2f * sinf(x * 0.07f + 2) + 1.0f * sinf(x * 0.23f);   // les monts au loin
        const float a = borne(y - mont + 0.5f, 0, 1);
        c[0] += (166 - c[0]) * a; c[1] += (136 - c[1]) * a; c[2] += (166 - c[2]) * a;
        for (int i = 0; i < 3; i++) e.decor[y * 64 + x][i] = (uint16_t)roundf(borne(c[i], 0, 1023) * 64);
      }
    float b1[64], b2[64], b3[64];
    for (int x = 0; x < 64; x++) {
      b1[x] = fminf(43.5f + x * 0.3f + 0.8f * sinf(x * 0.5f), 46 + (63 - x) * 0.26f + 0.8f * sinf(x * 0.4f + 1));
      b2[x] = fminf(51 + x * 0.25f, 56 + (63 - x) * 0.28f);
      b3[x] = x > 34 ? 62.5f - (x - 34) * 0.3f : 66.0f;           // une butte, devant
    }
    nf_cimes(30, b1, 0.8f, 2.0f, 0, true, e.p1);
    nf_cimes(22, b2, 1.5f, 3.5f, 0, true, e.p2);
    nf_cimes(14, b3, 2.0f, 4.5f, 0, true, e.p3);
    brume_n(e.brume, 128, 9);
    for (int i = 0; i < 5; i++) e.fuseaux[i] = hasard(0, 1);
  }
  const float o1 = t * 0.5f, o2 = 60 - t * 0.35f;
  for (int y = 0; y < 64; y++) {
    const float q1 = (y - 51) / 4.5f, g1 = q1 * q1 < 16 ? expf(-q1 * q1) : 0.0f;
    const float q2 = (y - 59) / 3.5f, g2 = q2 * q2 < 16 ? expf(-q2 * q2) : 0.0f;
    for (int x = 0; x < 64; x++) {
      const uint16_t *d = e.decor[y * 64 + x];
      float p[3] = {d[0] * (1.0f / 64), d[1] * (1.0f / 64), d[2] * (1.0f / 64)};
      float a = borne(y - e.p1[x] + 0.5f, 0, 1);                   // la pente d'en face
      if (a > 0) { p[0] += (112 - p[0]) * a; p[1] += (98 - p[1]) * a; p[2] += (128 - p[2]) * a; }
      if (g1 > 0) {                                                 // la brume, doree du cote du soleil
        a = fminf(g1 * (0.45f + 0.6f * fenetre_n(e.brume, 128, o1, 10, x, y)), 0.92f);
        const float l = borne(1 - fabsf(x - 50.0f) / 40, 0, 1);
        p[0] += (236 + 19 * l - p[0]) * a; p[1] += (196 + 22 * l - p[1]) * a; p[2] += (200 - 24 * l - p[2]) * a;
      }
      a = borne(y - e.p2[x] + 0.5f, 0, 1);
      if (a > 0) { p[0] += (58 - p[0]) * a; p[1] += (54 - p[1]) * a; p[2] += (80 - p[2]) * a; }
      if (g2 > 0) {
        a = fminf(g2 * (0.3f + 0.5f * fenetre_n(e.brume, 128, o2, 40, x, y)), 0.8f);
        p[0] += (228 - p[0]) * a; p[1] += (190 - p[1]) * a; p[2] += (196 - p[2]) * a;
      }
      a = borne(y - e.p3[x] + 0.5f, 0, 1);
      if (a > 0) { p[0] += (28 - p[0]) * a; p[1] += (28 - p[1]) * a; p[2] += (44 - p[2]) * a; }
      peindre(y, x, p[0], p[1], p[2]);
    }
  }
  for (int i = 0; i < 5; i++) {                                     // du plus loin au plus pres
    const float prof = NF_MG[i][0], x0 = NF_MG[i][1], alt = NF_MG[i][2], periode = NF_MG[i][3];
    const int nc = NF_MG_N[i];
    const float R = 2.0f + 7.2f * prof, m = 2.2f * R + 4;
    const float cx = fmodf(x0 + t * (0.12f + 0.5f * prof), 64 + 2 * m) - m;
    const float cy = alt + 1.6f * sinf(t * 0.11f + i * 2.1f);
    float brule = borne((sinf(PI2 * t / periode + i * 1.7f) - 0.86f) / 0.1f, 0, 1);
    brule *= 0.8f + 0.2f * sinf(t * 17 + i) * sinf(t * 7.3f);
    const int ya = (int)fmaxf(0, cy - R - 2), yb = (int)fminf(64, cy + 2.1f * R + 2), xa = (int)fmaxf(0, cx - R - 2), xb = (int)fminf(64, cx + R + 3);
    if (ya >= yb || xa >= xb) continue;
    const float br = (1 - prof) * 0.5f;                             // au loin, elles se fondent dans le ciel
    const int n = R < 5 ? 6 : 8;
    for (int y = ya; y < yb; y++)
      for (int x = xa; x < xb; x++) {
        const float u = (x - cx) / R, v = (y - cy) / R;
        const float demi = v < 0.35f ? sqrtf(borne(1 - v * v, 0, 1)) : 0.94f - (v - 0.35f) * 0.56f;
        const float couv = borne((demi - fabsf(u)) * R + 0.5f, 0, 1) * borne((1.45f - v) * R + 0.5f, 0, 1) * borne((v + 1) * R + 0.5f, 0, 1);
        float ciel[3] = {0, 0, 0};
        if (br > 0) nf_mg_ciel(x, y, ciel);
        if (couv > 0) {
          const float sn = borne(u / fmaxf(demi, 1e-3f), -1, 1);
          const int f = ((int)floorf((asinf(sn) / NF_PI + 0.5f) * n + e.fuseaux[i])) % nc;   // les fuseaux se resserrent sur les bords
          const float nz = sqrtf(borne(1 - sn * sn, 0, 1));
          const float lum = 0.34f + 0.8f * borne(sn * 0.7f - borne(v, -1, 0.4f) * 0.35f + nz * 0.55f, 0, 1);   // le soleil a droite
          const float bv = brule * 0.75f * borne(v + 0.2f, 0, 1.2f);    // le bruleur l'eclaire du dedans
          float c[3] = {NF_MG_C[i][f][0] * lum + bv * 255, NF_MG_C[i][f][1] * lum + bv * 150, NF_MG_C[i][f][2] * lum + bv * 60};
          for (int k = 0; k < 3; k++) c[k] = c[k] * (1 - br) + ciel[k] * br;
          nf_melanger(y, x, couv, c[0], c[1], c[2]);
        }
        const float nacelle = borne((0.24f - fabsf(u)) * R + 0.5f, 0, 1) * borne((v - 1.62f) * R + 0.5f, 0, 1) * borne((1.95f - v) * R + 0.5f, 0, 1);
        const float corde = R > 5 && v > 1.45f && v < 1.65f ? borne(0.5f - fabsf(fabsf(u) - 0.27f + (v - 1.45f) * 0.3f) * R, 0, 1) : 0.0f;
        const float nac = fmaxf(nacelle, corde * 0.8f);
        if (nac > 0) nf_melanger(y, x, nac, 64 * (1 - br) + ciel[0] * br, 42 * (1 - br) + ciel[1] * br, 34 * (1 - br) + ciel[2] * br);
        if (brule > 0.02f) {
          const float fu = u / 0.12f, fv = (v - 1.42f) / 0.12f;
          const float fl = nf_exp(-(fu * fu + fv * fv) * 0.5f * R / 3) * brule * 1.2f;
          ajouter(y, x, fl, 255, 210, 120);
        }
      }
  }
}

// --- Le voilier : il glisse au coucher du soleil ; on le suit, l'eau defile ---
// humeurs : 0 = Voilier au couchant
const float NF_VOIL_H = 36.0f;
// _voilier_formes : (coque, liston, mat, grand-voile, foc) en bits, dans le repere du bateau
static inline int nf_voilier_formes(float lx, float ly, float gonfle) {
  if (ly < -23.0f || ly > 1.0f || lx < -9.0f || lx > 10.0f) return 0;
  int f = 0;
  const float pont = -1.8f - 0.07f * lx;
  if (ly >= pont && ly <= 0.7f && lx >= -8.2f + (ly + 1.8f) * 0.4f && lx <= 8.8f - (ly - pont) * 1.1f) {
    f |= 1;
    if (ly < pont + 0.7f) f |= 2;
  }
  if ((fabsf(lx - 1.0f) <= 0.45f && ly >= -22.5f && ly < pont) || (fabsf(ly + 3.0f) <= 0.45f && lx <= 0.6f && lx >= -8.4f)) f |= 4;
  if (ly >= -21.0f && ly <= -3.2f && lx <= 0.55f && lx >= -10.5f) {
    const float q = borne((ly + 21.0f) / 18.0f, 0, 1);
    if (lx >= 0.5f - 8.6f * q - gonfle * 1.7f * nf_sin(NF_PI * q)) f |= 8;   // la chute de la grand-voile, bombee
  }
  if (ly >= -19.0f && ly <= -2.6f - 0.05f * lx && lx >= 1.5f) {
    const float r = borne((ly + 19.0f) / 16.2f, 0, 1);
    if (lx <= 1.5f + 6.9f * r && lx >= 1.5f + 0.9f * r + gonfle * 1.5f * nf_sin(NF_PI * r)) f |= 16;
  }
  return f;
}
struct E_voilier {
  uint16_t rides[128 * 128], nuages[128 * 128];
  uint16_t ciel[36 * 64][3];         // x64
  float mph[3], mvit[3];
};
void s_voilier(int humeur, bool debut, float t, float ecoule, float dt) {
  E_voilier &e = etat_ecran<E_voilier>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const float H = NF_VOIL_H;
  if (debut) {
    for (int y = 0; y < 36; y++)
      for (int x = 0; x < 64; x++) {
        float c[3];
        if (y < 26) { const float k = y / 26.0f; c[0] = 34 + 162 * k; c[1] = 22 + 62 * k; c[2] = 64 + 32 * k; }
        else { const float k = borne((y - 26) / 10.0f, 0, 1); c[0] = 196 + 56 * k; c[1] = 84 + 76 * k; c[2] = 96 - 20 * k; }
        const float d = sqrtf((x - 45.0f) * (x - 45.0f) + (y - 30.0f) * (y - 30.0f));
        float g = borne(1 - d / 30, 0, 1);
        g *= g;
        c[0] += g * 80; c[1] += g * 50; c[2] += g * 10;
        const float so = borne(5.0f - d, 0, 1);
        c[0] += (255 - c[0]) * so; c[1] += (228 - c[1]) * so; c[2] += (160 - c[2]) * so;
        for (int i = 0; i < 3; i++) e.ciel[y * 64 + x][i] = (uint16_t)roundf(borne(c[i], 0, 1023) * 64);
      }
    brume_n(e.rides, 128, 4);
    brume_n(e.nuages, 128, 7);
    for (int i = 0; i < 3; i++) { e.mph[i] = hasard(0, 6); e.mvit[i] = hasard(0.6f, 1.2f); }
  }
  const float k64 = 1.0f / 64;
  for (int y = 0; y < 36; y++) {
    const float hn = borne(1 - fabsf(y - 17.0f) / 10, 0, 1) * 0.75f;
    for (int x = 0; x < 64; x++) {
      const uint16_t *c = e.ciel[y * 64 + x];
      float p[3] = {c[0] * k64, c[1] * k64, c[2] * k64};
      if (hn > 0) {                                                  // de longs nuages, eclaires par dessous
        const float fx = x * 0.45f + t * 0.5f;
        const float N = nf_lire(e.nuages, 128, y * 2.4f + 9, fx);
        const float a = borne((N - 0.45f) * 2.2f, 0, 1) * hn;
        if (a > 0) {
          const float Nb = nf_lire(e.nuages, 128, y * 2.4f + 11.4f, fx);
          const float lu = borne(1 - sqrtf((x - 45.0f) * (x - 45.0f) + (y - 30.0f) * (y - 30.0f)) / 34, 0, 1);
          const float de = borne((N - Nb) * 5 + lu * 0.9f, 0, 1);
          p[0] += (96 + 159 * de - p[0]) * a; p[1] += (40 + 116 * de - p[1]) * a; p[2] += (82 + 30 * de - p[2]) * a;
        }
      }
      peindre(y, x, p[0], p[1], p[2]);
    }
  }
  for (int y = 36; y < 64; y++) {                                   // la mer en perspective : les rides defilent
    const float dy = y - H + 0.6f, z = 30.0f / dy;
    const float km = (y - H) / 28.0f;
    const float mr = 100 - 82 * km, mg = 54 - 40 * km, mb = 96 - 52 * km;
    const float prof = borne((y - H + 0.5f) / 28.0f, 0, 1);
    const float calme = expf(-z / 8);                               // au loin, les rides se fondent
    const int ym = (int)borne(2 * H - 1 - y, 0, H - 1);
    const float large = 1.5f + (y - H) * 0.42f, kc = 1 - prof * 0.4f;
    for (int x = 0; x < 64; x++) {
      const float R = nf_lire(e.rides, 128, z * 4.0f, (x - 32) / dy * 6 + t * 2.0f);
      const float ride = (R - 0.5f) * calme;
      const float km2 = borne(0.35f + ride * 1.6f, 0, 1) * 0.5f;
      const uint16_t *m = e.ciel[ym * 64 + x];
      float r = mr * (1 - 0.6f * ride) + m[0] * k64 * km2, g = mg * (1 - 0.6f * ride) + m[1] * k64 * km2, b = mb * (1 - 0.6f * ride) + m[2] * k64 * km2;
      const float q = (x - 45) / large;
      if (q * q < 20) {
        float c = borne(R * 2 - 0.75f, 0, 1);
        const float ch = nf_exp(-q * q) * (c * c * calme + (1 - calme) * 0.35f) * kc;
        r += ch * 255; g += ch * 190; b += ch * 100;
      }
      peindre(y, x, r, g, b);
    }
  }
  const float vx = fmodf(t * 0.15f + 20, 100.0f) - 18;               // une voile au loin, sur l'horizon
  pointer(H - 1, vx, 230, 170, 150); pointer(H - 2, vx, 230, 170, 150); pointer(H - 2, vx + 1, 230, 170, 150);
  const float bx = 25 + 5 * sinf(t * 0.031f) + 2 * sinf(t * 0.07f);   // on le suit : il derive a peine
  const float by = 50.5f + 0.5f * sinf(t * 0.9f + 0.8f);
  const float ang = 0.05f * sinf(t * 0.9f) + 0.02f * sinf(t * 1.63f);
  const float gonfle = 0.85f + 0.15f * sinf(t * 0.37f);
  for (int k = 0; k < 16; k++) {                                    // le sillage, qui s'ouvre derriere lui
    const float f = powf(1 - k / 16.0f, 1.2f) * (0.35f + 0.3f * sinf(k * 0.9f + t * 2.4f));
    for (int sg = -1; sg <= 1; sg += 2) nf_tache(by + 0.9f + sg * k * 0.24f, bx - 8.5f - k * 1.4f, 90 * f, 76 * f, 96 * f);
  }
  const int ya = (int)(by - 25), yb = min(64, (int)(by + 12)), xa = max(0, (int)(bx - 13)), xb = min(64, (int)(bx + 13));
  const float ca = cosf(ang), sa = sinf(ang);
  static const float OFF[4][2] = {{-0.25f, -0.25f}, {-0.25f, 0.25f}, {0.25f, -0.25f}, {0.25f, 0.25f}};
  for (int y = max(0, ya); y < yb; y++) {
    float tremble[2];
    for (int k = 0; k < 2; k++) tremble[k] = 0.8f * sinf((y + (k ? 0.25f : -0.25f)) * 1.6f + t * 2.5f);
    for (int x = xa; x < xb; x++) {
      float couv[5] = {0, 0, 0, 0, 0}, refl[5] = {0, 0, 0, 0, 0};
      for (int s = 0; s < 4; s++) {                                  // quatre echantillons par pixel
        const float oy = OFF[s][0], ox = OFF[s][1];
        const float dx = x + ox - bx, dy = y + oy - by;
        const float lx = dx * ca + dy * sa, ly = -dx * sa + dy * ca;
        const int f = nf_voilier_formes(lx, ly, gonfle);
        for (int k = 0; k < 5; k++) if (f >> k & 1) couv[k] += 0.25f;
        if (y + oy > by + 0.7f) {
          const int g = nf_voilier_formes(lx + tremble[oy > 0], -ly + 1.4f, gonfle);
          for (int k = 0; k < 5; k++) if (g >> k & 1) refl[k] += 0.25f;
        }
      }
      if (couv[0] + couv[1] + couv[2] + couv[3] + couv[4] + refl[0] + refl[3] + refl[4] <= 0) continue;
      const float dx = x - bx, dy = y - by;
      const float lx = dx * ca + dy * sa, ly = -dx * sa + dy * ca;
      const float q = borne((ly + 21) / 18, 0, 1);
      const float kv = (0.62f + 0.38f * borne((lx + 8) / 9, 0, 1)) * (1 - 0.15f * q), kf = 0.7f + 0.3f * borne((8 - lx) / 6, 0, 1);
      const float te[5][3] = {{30, 20, 40}, {210, 150, 120}, {50, 34, 48}, {255 * kv, 196 * kv, 150 * kv}, {255 * kf, 210 * kf, 160 * kf}};
      static const int ORDRE[5] = {3, 4, 2, 0, 1};
      for (int k = 0; k < 5; k++) {
        const int j = ORDRE[k];
        if (couv[j] > 0) nf_melanger(y, x, couv[j], te[j][0], te[j][1], te[j][2]);
      }
      if (y > by + 0.7f) {
        const float kr = 0.4f * expf(-(y - by) / 9);
        static const int REF[3] = {3, 4, 0};
        for (int k = 0; k < 3; k++) {
          const int j = REF[k];
          if (refl[j] > 0) nf_melanger(y, x, refl[j] * kr, te[j][0] * 0.55f, te[j][1] * 0.55f, te[j][2] * 0.55f);
        }
      }
    }
  }
  for (int i = 0; i < 3; i++) {                                     // des mouettes qui tournent, et planent
    const float mx = 14 + i * 17 + 12 * sinf(t * 0.07f * e.mvit[i] + e.mph[i]);
    const float my = 7 + i * 4 + 3 * sinf(t * 0.11f * e.mvit[i] + e.mph[i] * 2);
    const float bat = sinf(t * 0.3f + e.mph[i]) > 0.3f ? 0.9f * sinf(t * 5 + i) : 0.0f;
    poser(my - 1 + bat, mx - 2, 64, 36, 62); poser(my - 0.2f + bat * 0.4f, mx - 1, 64, 36, 62); poser(my + 0.3f, mx, 64, 36, 62);
    poser(my - 0.2f + bat * 0.4f, mx + 1, 64, 36, 62); poser(my - 1 + bat, mx + 2, 64, 36, 62);
  }
}

// --- Les rayons en foret, au petit matin ---
// humeurs : 0 = Rayons en foret
const float NF_FOR_SY = -26.0f, NF_FOR_SX = -10.0f;    // le soleil, hors champ en haut a gauche
static const float NF_FOR_RAYONS[6][3] = {{0.64f, 0.035f, 0.9f}, {0.76f, 0.055f, 0.75f}, {0.86f, 0.03f, 1.0f},
                                          {0.96f, 0.065f, 0.7f}, {1.07f, 0.04f, 0.85f}, {1.17f, 0.03f, 0.6f}};
struct E_foret_rayons {
  uint16_t brume[128 * 128];         // (au debut : le brouillon)
  uint8_t fond[64 * 64][3];
  uint8_t milieu[64 * 64], devant[64 * 64], ecorce[64 * 64], ombre[64 * 64], canopee[64 * 64], tapis[64 * 64], fougeres[64 * 64];
  int8_t cote[64 * 64];
  uint16_t angle[64 * 64];           // x32768
  float sols[3][64];
  float px0[80], py0[80], pv[80], pp[80];
  float ix[5], iy[5], iv[5], ip[5];
  float phases[6];
  float ra[6], rf[6];                // les rayons de cette image : leur angle, leur force
};
void nf_foret_preparer(E_foret_rayons &e) {
  float *A = (float *)e.brume, *Bf = A + 4096;
  for (int x = 0; x < 64; x++) {
    e.sols[0][x] = 47 + 1.0f * sinf(x * 0.2f + 2);
    e.sols[1][x] = 51 + 1.5f * sinf(x * 0.13f + 4) + 0.6f * sinf(x * 0.45f);
    e.sols[2][x] = 55.5f + 2.0f * sinf(x * 0.11f + 1) + 0.8f * sinf(x * 0.37f);
  }
  for (int i = 0; i < 4096; i++) { A[i] = 1; Bf[i] = 1; e.milieu[i] = 0; e.devant[i] = 0; e.cote[i] = 0; e.ecorce[i] = 217; }
  uint8_t *occulte = e.ombre;
  memset(occulte, 0, 4096);
  for (int plan = 0; plan < 3; plan++) {
    const int n = plan == 0 ? 13 : plan == 1 ? 5 : 3;
    for (int k = 0; k < n; k++) {
      float xc, l;
      if (plan == 2) {
        static const float XS[3] = {3.5f, 41.0f, 61.5f}, LS[3] = {7.5f, 4.0f, 8.5f};
        xc = XS[k] + hasard(-1.5f, 1.5f); l = LS[k] * hasard(0.9f, 1.1f);
      } else {
        xc = (k + hasard(0.2f, 0.8f)) / n * 68 - 2;
        l = plan == 0 ? hasard(0.8f, 1.6f) : hasard(1.8f, 3.0f);
      }
      const float pied = e.sols[plan][(int)borne(xc, 0, 63)] + (plan < 2 ? 0.5f : 4.0f);
      const float pa = hasard(-0.05f, 0.05f);
      for (int y = 0; y < 64; y++) {
        const float axe = xc + pa * (y - pied);
        const float r = borne((y - pied + 4 + plan) / (4.0f + plan), 0, 1);
        const float demi = l / 2 * (1 + (0.5f + 0.4f * plan) * r * r);   // les racines
        const float cy = borne(pied + 0.5f - y, 0, 1);
        for (int x = 0; x < 64; x++) {
          const float c = borne(demi + 0.5f - fabsf(x - axe), 0, 1) * cy;
          if (c <= 0) continue;
          const int i = y * 64 + x;
          if (plan == 0) A[i] *= 1 - 0.5f * c * 0.45f * borne((y + 16) / 50.0f, 0, 1);   // les troncs du fond assombrissent la brume
          else if (plan == 1) { Bf[i] *= 1 - c * 0.92f; occulte[i] = max(occulte[i], (uint8_t)roundf(c * 255)); }
          else {                                                     // les grands troncs : leur cote au soleil, leur ecorce
            e.devant[i] = max(e.devant[i], (uint8_t)roundf(c * 255));
            e.cote[i] = (int8_t)roundf(borne((axe - x) / fmaxf(demi, 0.5f), -1, 1) * 127);
            e.ecorce[i] = (uint8_t)roundf((0.85f + 0.15f * sinf((x - axe) * 2.3f + sinf(y * 0.3f) * 1.5f)) * 255);
          }
        }
      }
    }
  }
  for (int y = 0; y < 64; y++) {
    const float k = borne(y / 50.0f, 0, 1);
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const float g = expf(-sqrtf((x - 2.0f) * (x - 2.0f) + (y - 2.0f) * (y - 2.0f)) / 22);   // la lueur du soleil
      e.fond[i][0] = (uint8_t)borne(roundf((50 - 16 * k + g * 130) * A[i]), 0, 255);
      e.fond[i][1] = (uint8_t)borne(roundf((70 - 22 * k + g * 122) * A[i]), 0, 255);
      e.fond[i][2] = (uint8_t)borne(roundf((66 - 20 * k + g * 72) * A[i]), 0, 255);
      e.milieu[i] = (uint8_t)roundf((1 - Bf[i]) * 255);
      e.angle[i] = (uint16_t)roundf(atan2f(y - NF_FOR_SY, x - NF_FOR_SX) * 32768);
    }
  }
  // l'ombre des troncs dans la brume, vers le bas a droite
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float uy = NF_FOR_SY - y, ux = NF_FOR_SX - x;
      const float nrm = sqrtf(uy * uy + ux * ux);
      uy /= nrm; ux /= nrm;
      uint8_t o = 0;
      for (int j = 2; j < 70; j += 2) {
        const int py = (int)rintf(y + uy * j), px = (int)rintf(x + ux * j);
        if (py >= 0 && px >= 0 && px < 64 && py < 64) o = max(o, occulte[py * 64 + px]);
      }
      A[y * 64 + x] = o;
    }
  for (int i = 0; i < 4096; i++) e.ombre[i] = (uint8_t)A[i];
  uint16_t *feuilles = (uint16_t *)Bf;
  brume_n(feuilles, 64, 3);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float ouvert = borne(1 - sqrtf((x + 2.0f) * (x + 2.0f) + (y + 2.0f) * (y + 2.0f)) / 24, 0, 1);   // le feuillage s'ouvre ou entre le soleil
      const float c = borne((0.62f - feuilles[y * 64 + x] / 65535.0f - (y - 3) * 0.06f - 0.5f * ouvert) * 5, 0, 1) * borne((12 - y) / 5.0f, 0, 1);
      e.canopee[y * 64 + x] = (uint8_t)roundf(c * 255);
    }
  for (int i = 0; i < 4096; i++) A[i] = 0;
  for (int f = 0; f < 5; f++) {                                     // des fougeres sur la mousse
    const float fx = hasard(8, 58), fy = e.sols[2][(int)fx] + 1.5f;
    for (int k = -2; k <= 2; k++) {
      const float a = k * 0.42f + hasard(-0.1f, 0.1f);
      const float l = hasard(4, 6.5f) * (1 - 0.15f * abs(k));
      const float mx = fx + sinf(a) * l * 0.55f, my = fy - cosf(a) * l * 0.7f;
      const float tr[2][6] = {{fy, fx, my, mx, 0.45f, 0.4f}, {my, mx, my + 0.6f + abs(k) * 0.5f, mx + sinf(a) * l * 0.5f, 0.4f, 0.2f}};
      nf_traits(tr, 2, 1, 1, 1, 1.0f, A);
    }
  }
  for (int i = 0; i < 4096; i++) e.fougeres[i] = (uint8_t)roundf(borne(A[i], 0, 1) * 255);
  uint16_t *tapis = (uint16_t *)Bf;
  brume_n(tapis, 64, 1);
  for (int i = 0; i < 4096; i++) e.tapis[i] = (uint8_t)(tapis[i] >> 8);
  brume_n(e.brume, 128, 10);
  for (int i = 0; i < 80; i++) { e.px0[i] = hasard(0, 64); e.py0[i] = hasard(0, 64); e.pv[i] = hasard(0.6f, 1.4f); e.pp[i] = hasard(0, 6); }
  for (int i = 0; i < 5; i++) { e.ix[i] = hasard(10, 54); e.iy[i] = hasard(16, 46); e.iv[i] = hasard(0.7f, 1.3f); e.ip[i] = hasard(0, 6); }
  for (int i = 0; i < 6; i++) e.phases[i] = hasard(0, PI2);
}
// les rayons en (x, y), B : la brume qui derive, en ce point
static inline float nf_foret_rayon(const E_foret_rayons &e, int x, int y, float B) {
  const int i = y * 64 + x;
  const float an = e.angle[i] * (1.0f / 32768);
  float r = 0;
  for (int k = 0; k < 6; k++) {
    const float q = (an - e.ra[k]) / NF_FOR_RAYONS[k][1];
    if (q * q < 14) r += nf_exp(-q * q) * e.rf[k];
  }
  const float profil = borne((y - 1) / 12.0f, 0, 1) * (0.75f + 0.35f * y / 64);
  return r * profil * (1 - 0.6f * e.ombre[i] * (1.0f / 255)) * (0.5f + 0.7f * B);
}
void s_foret_rayons(int humeur, bool debut, float t, float ecoule, float dt) {
  E_foret_rayons &e = etat_ecran<E_foret_rayons>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) nf_foret_preparer(e);
  for (int k = 0; k < 6; k++) {                                     // chaque rayon respire a son rythme
    const float souffle = 0.5f + 0.5f * sinf(PI2 * t / 17 + e.phases[k]);
    e.ra[k] = NF_FOR_RAYONS[k][0] + 0.012f * sinf(t * 0.05f + e.phases[k]);
    e.rf[k] = NF_FOR_RAYONS[k][2] * (0.35f + 0.65f * souffle);
  }
  const float bx = t * 0.4f, by = t * 0.1f;                          // la brume qui derive
  float lumiere[64];                                                 // les taches de soleil sur la mousse
  for (int x = 0; x < 64; x++) {
    const int y = (int)borne((int)e.sols[2][x] - 1, 0, 63);
    lumiere[x] = borne(nf_foret_rayon(e, x, y, fenetre_n(e.brume, 128, bx, by, x, y)), 0, 1.2f);
  }
  const float k255 = 1.0f / 255;
  for (int y = 0; y < 64; y++) {
    const float ks = borne(y / 52.0f, 0, 1);
    const float so[3] = {60 - 36 * ks, 76 - 42 * ks, 70 - 38 * ks};   // plus haut, plus de brume
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      const float B = fenetre_n(e.brume, 128, bx, by, x, y), kb = 0.9f + 0.2f * B;
      const float kf = 0.85f + 0.3f * B;
      float p[3] = {e.fond[i][0] * kf, e.fond[i][1] * kf, e.fond[i][2] * kf};
      float a = borne(y - e.sols[0][x] + 0.5f, 0, 1);
      if (a > 0) { p[0] += (46 * kb - p[0]) * a; p[1] += (62 * kb - p[1]) * a; p[2] += (54 * kb - p[2]) * a; }
      a = e.milieu[i] * k255;
      if (a > 0) for (int c = 0; c < 3; c++) p[c] += (so[c] * kb - p[c]) * a;
      a = borne(y - e.sols[1][x] + 0.5f, 0, 1);
      if (a > 0) { p[0] += (30 * kb - p[0]) * a; p[1] += (46 * kb - p[1]) * a; p[2] += (32 * kb - p[2]) * a; }
      const float ra = nf_foret_rayon(e, x, y, B);
      const float rc = fminf(fmaxf(ra, 0.0f), 1.4f) * 0.8f;
      p[0] += rc * 255; p[1] += rc * 224; p[2] += rc * 156;
      for (int s = 0; s < 2; s++) {                                  // la brume posee sur le sol
        const float q = (y - e.sols[s][x]) / 2.2f;
        if (q * q > 16) continue;
        a = nf_exp(-q * q) * (0.3f + 0.4f * B) * (s ? 0.3f : 0.35f) * 2;
        p[0] += (110 - p[0]) * a; p[1] += (132 - p[1]) * a; p[2] += (114 - p[2]) * a;
      }
      const float dv = e.sols[2][x];
      a = borne(y - dv + 0.5f, 0, 1);
      if (a > 0) {                                                   // la mousse, ses taches de soleil
        const float l = lumiere[x] * nf_exp(-fmaxf(y - dv, 0.0f) / 5), kt = 0.7f + 0.6f * e.tapis[i] * k255;
        p[0] += ((26 + l * 110) * kt - p[0]) * a; p[1] += ((50 + l * 140) * kt - p[1]) * a; p[2] += ((20 + l * 46) * kt - p[2]) * a;
      }
      a = e.fougeres[i] * k255 * 0.95f;
      if (a > 0) {
        const float r1 = borne(ra, 0, 1);
        p[0] += (14 + r1 * 40 - p[0]) * a; p[1] += (34 + r1 * 70 - p[1]) * a; p[2] += (14 + r1 * 20 - p[2]) * a;
      }
      a = e.devant[i] * k255;
      if (a > 0) {                                                   // les grands troncs devant, eclaires du cote du soleil
        const float co = e.cote[i] * (1.0f / 127), ec = e.ecorce[i] * k255;
        const float kt = (0.75f + 0.35f * co) * ec, ks2 = borne(co - 0.6f, 0, 1) * 2.5f * (0.35f + ra);
        const float mo = borne(y - dv + 8, 0, 8) / 8 * 0.7f;          // de la mousse au pied
        p[0] += (16 * kt + ks2 * 110 + mo * 20 - p[0]) * a;
        p[1] += (19 * kt + ks2 * 96 + mo * 42 - p[1]) * a;
        p[2] += (16 * kt + ks2 * 50 + mo * 12 - p[2]) * a;
      }
      a = e.canopee[i] * k255;
      if (a > 0) { p[0] += (10 - p[0]) * a; p[1] += (18 - p[1]) * a; p[2] += (12 - p[2]) * a; }
      peindre(y, x, p[0], p[1], p[2]);
    }
  }
  for (int i = 0; i < 80; i++) {                                    // les poussieres : visibles dans les rayons seulement
    float px = e.px0[i] + t * 0.3f + 1.5f * sinf(t * 0.11f * e.pv[i] + e.pp[i]);
    float py = e.py0[i] + t * 0.15f + 2 * sinf(t * 0.07f * e.pv[i] + e.pp[i] * 2);
    px -= 64 * floorf(px / 64); py -= 64 * floorf(py / 64);
    const int xi = min(63, (int)px), yi = min(63, (int)py);
    const float r = nf_foret_rayon(e, xi, yi, fenetre_n(e.brume, 128, bx, by, xi, yi));
    const float b = borne(r, 0, 1.4f) * (0.55f + 0.45f * sinf(t * 0.9f * e.pv[i] + e.pp[i] * 3));
    if (b > 0) nf_tache(py, px, 255 * b, 236 * b, 190 * b);
  }
  for (int i = 0; i < 5; i++) {                                     // des insectes qui volent, et brillent dans la lumiere
    const float qx = e.ix[i] + 8 * sinf(t * 0.21f * e.iv[i] + e.ip[i]) + 2 * sinf(t * 1.3f * e.iv[i] + e.ip[i] * 2);
    const float qy = e.iy[i] + 5 * sinf(t * 0.17f * e.iv[i] + e.ip[i] * 3) + 1.5f * sinf(t * 1.7f * e.iv[i]);
    const int xi = (int)borne(qx, 0, 63), yi = (int)borne(qy, 0, 63);
    const float r = nf_foret_rayon(e, xi, yi, fenetre_n(e.brume, 128, bx, by, xi, yi));
    const float k = 0.25f + 1.1f * borne(r, 0, 1);
    nf_tache(qy, qx, 255 * k, 240 * k, 200 * k);
  }
}

// --- Le jardin zen, vu de haut : le sable ratisse, un rateau invisible, une feuille d'erable ---
// humeurs : 0 = Jardin zen
static const float NF_JARDIN_PIERRES[3][3] = {{19.5f, 22.0f, 6.0f}, {44.5f, 37.0f, 4.4f}, {26.5f, 48.5f, 2.9f}};
const float NF_JARDIN_PAS = 3.4f, NF_JARDIN_PASSAGE = 40.0f, NF_JARDIN_TERRASSE = 56.5f;
struct E_jardin_zen {
  int16_t gmin[64 * 64];             // la distance aux anneaux autour des pierres (x1024 ; 32767 : hors des anneaux)
  int8_t grx[64 * 64], gry[64 * 64]; // leur direction (x127)
  int8_t nx[64 * 64], ny[64 * 64], nz[64 * 64];   // la normale des pierres (x127)
  uint8_t pierre[64 * 64], ilot[64 * 64], mousse[64 * 64], tex[64 * 64];
  uint8_t bois[8 * 64][3];           // la terrasse, lignes 56 a 63
  float formes[3][7];                // x, y, rayon, et quatre phases
  float fx[32], fy[32], fr[32];
  uint16_t tmp[64 * 64];
};
void nf_jardin_preparer(E_jardin_zen &e) {
  brume_n(e.tmp, 64, 2);
  for (int i = 0; i < 4096; i++) e.tex[i] = (uint8_t)(e.tmp[i] >> 8);
  float *gmin = nullptr;
  (void)gmin;
  for (int i = 0; i < 4096; i++) { e.gmin[i] = 32767; e.grx[i] = 0; e.gry[i] = 0; e.nx[i] = 0; e.ny[i] = 0; e.nz[i] = 127; e.pierre[i] = 0; e.ilot[i] = 0; }
  static float gm[64 * 64];
  (void)gm;
  for (int s = 0; s < 3; s++) {
    const float cx = NF_JARDIN_PIERRES[s][0], cy = NF_JARDIN_PIERRES[s][1], r = NF_JARDIN_PIERRES[s][2];
    float a[4];
    for (int k = 0; k < 4; k++) a[k] = hasard(0, 6);
    e.formes[s][0] = cx; e.formes[s][1] = cy; e.formes[s][2] = r;
    for (int k = 0; k < 4; k++) e.formes[s][3 + k] = a[k];
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const int i = y * 64 + x;
        const float phi = atan2f(y - cy, x - cx), d = sqrtf((x - cx) * (x - cx) + (y - cy) * (y - cy));
        const float bord = r * (1 + 0.12f * sinf(2 * phi + a[0]) + 0.07f * sinf(3 * phi + a[1]) + 0.04f * sinf(5 * phi + a[2]));
        const float rho = d / bord, c = borne(bord - d + 0.5f, 0, 1);
        const float hz = sqrtf(borne(1 - rho * rho, 0, 1));
        if (c * 255 > e.pierre[i] + 0.5f) {
          const float nx = (x - cx) / bord, ny = (y - cy) / bord, nz = hz * 1.2f + 0.1f;
          const float n = sqrtf(nx * nx + ny * ny + nz * nz);
          e.nx[i] = (int8_t)roundf(nx / n * 127); e.ny[i] = (int8_t)roundf(ny / n * 127); e.nz[i] = (int8_t)roundf(nz / n * 127);
          e.pierre[i] = (uint8_t)roundf(c * 255);
        }
        const float mb = bord + 2.0f + 0.7f * sinf(4 * phi + a[3]) + 0.5f * e.tex[i] / 255.0f;
        e.ilot[i] = max(e.ilot[i], (uint8_t)roundf(borne(mb - d + 0.5f, 0, 1) * 255));
        const float g = d - (r + 2.6f) - (bord - r) * expf(-fmaxf(d - r, 0.0f) / 6);   // les anneaux s'arrondissent en s'eloignant
        if (g < NF_JARDIN_PAS * 3.0f && g * 1024 < e.gmin[i]) {
          e.gmin[i] = (int16_t)roundf(g * 1024);
          e.grx[i] = (int8_t)roundf((x - cx) / fmaxf(d, 0.1f) * 127);
          e.gry[i] = (int8_t)roundf((y - cy) / fmaxf(d, 0.1f) * 127);
        }
      }
  }
  brume_n(e.tmp, 64, 1);                                            // de la mousse par plaques, sur le dessus
  for (int i = 0; i < 4096; i++)
    e.mousse[i] = (uint8_t)roundf(borne((e.tmp[i] / 65535.0f - 0.6f) * 6, 0, 1) * borne((e.nz[i] / 127.0f - 0.55f) * 4, 0, 1) * 255);
  brume_n(e.tmp, 64, 2);                                            // la terrasse en bois, au bas du jardin
  for (int y = 56; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float veine = nf_lire(e.tmp, 64, y * 1.0f, x * 0.25f);
      float lame = fmodf(y - NF_JARDIN_TERRASSE, 3.0f);
      if (lame < 0) lame += 3;
      float k = (0.75f + 0.45f * veine) * (1 - 0.45f * (lame < 0.6f ? 1 : 0));
      k *= 1 + 0.2f * sinf(floorf((y - NF_JARDIN_TERRASSE) / 3) * 2.7f + 1);   // chaque lame sa teinte
      e.bois[(y - 56) * 64 + x][0] = (uint8_t)borne(roundf(96 * k), 0, 255);
      e.bois[(y - 56) * 64 + x][1] = (uint8_t)borne(roundf(64 * k), 0, 255);
      e.bois[(y - 56) * 64 + x][2] = (uint8_t)borne(roundf(40 * k), 0, 255);
    }
  // ou la feuille peut se poser : loin des ilots
  int n = 0;
  for (int pass = 0; pass < 2; pass++) {
    int pris[32];
    for (int k = 0; k < 32 && pass == 1; k++) pris[k] = n ? (int)(aleatoire() % n) : 0;
    int j = 0;
    for (int y = 9; y < 53; y++)
      for (int x = 15; x < 58; x++) {
        static const int8_t V[9][2] = {{0, 0}, {3, 0}, {-3, 0}, {0, 3}, {0, -3}, {2, 2}, {-2, 2}, {2, -2}, {-2, -2}};
        bool loin = true;
        for (int k = 0; k < 9 && loin; k++) loin = e.ilot[((y - V[k][0]) & 63) * 64 + ((x - V[k][1]) & 63)] < 3;
        if (!loin) continue;
        if (pass == 1)
          for (int k = 0; k < 32; k++)
            if (pris[k] == j) { e.fx[k] = x + 0.5f; e.fy[k] = y + 0.5f; }
        j++;
      }
    if (pass == 0) n = j;
  }
  if (!n)
    for (int k = 0; k < 32; k++) { e.fx[k] = 40.5f; e.fy[k] = 20.5f; }
  for (int k = 0; k < 32; k++) e.fr[k] = hasard(0, 6);
}
// le relief d'un sillon : (la pente vers la lumiere, le creux)
static inline void nf_jardin_relief(const E_jardin_zen &e, int i, int x, int y, int motif, float lx, float ly, float &pente, float &creux) {
  float g, gx, gy;
  if (e.gmin[i] != 32767) { g = e.gmin[i] * (1.0f / 1024); gx = e.grx[i] * (1.0f / 127); gy = e.gry[i] * (1.0f / 127); }
  else if (motif) { g = y + 2.2f * nf_sin(x * 0.2f + 0.9f); gx = 0.44f * nf_cos(x * 0.2f + 0.9f); gy = 1; }
  else { g = (float)y; gx = 0; gy = 1; }
  const float w = PI2 * g / NF_JARDIN_PAS;
  pente = nf_sin(w) * (gx * lx + gy * ly) * 0.9f;
  creux = nf_cos(w);
}
void s_jardin_zen(int humeur, bool debut, float t, float ecoule, float dt) {
  E_jardin_zen &e = etat_ecran<E_jardin_zen>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) nf_jardin_preparer(e);
  const float th = PI2 * t / 150.0f + 0.7f;                         // la lumiere tourne autour du jardin
  const float lx = cosf(th), ly = sinf(th);
  const float passage = t / NF_JARDIN_PASSAGE;
  const int n = (int)floorf(passage);
  const float q = passage - n, front = -4 + q * 72;                // le rateau avance, ligne apres ligne
  const float vitesse = 72 / NF_JARDIN_PASSAGE;
  const int ma = n & 1, mb = (n + 1) & 1;
  const float k255 = 1.0f / 255, k127 = 1.0f / 127;
  for (int y = 0; y < 64; y++) {
    const float neuf = borne((front - y) / 2.5f, 0, 1);
    const float age = y < front ? (front - y) / vitesse : (front - y) / vitesse + NF_JARDIN_PASSAGE;
    const float net = 0.7f + 0.3f * expf(-age / 30);
    const float remue = 0.1f * expf(-(y - front) * (y - front));    // le sable fraichement remue
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      float pa = 0, ca = 0, pb = 0, cb = 0;
      if (neuf < 1) nf_jardin_relief(e, i, x, y, ma, lx, ly, pa, ca);
      if (neuf > 0) nf_jardin_relief(e, i, x, y, mb, lx, ly, pb, cb);
      const float pente = pa * (1 - neuf) + pb * neuf, creux = ca * (1 - neuf) + cb * neuf;
      const float clair = 0.82f + 0.22f * borne(((x - 32) * lx + (y - 32) * ly) / 45, -1, 1);   // le cote eclaire du jardin
      const float sable = (1 + net * (0.3f * pente + 0.08f * creux)) * clair + remue;
      peindre(y, x, sable * 150, sable * 140, sable * 122);
    }
  }
  // l'ombre des pierres, a l'oppose de la lumiere : dans un brouillon d'un octet par pixel
  uint8_t *ombre = (uint8_t *)e.tmp;
  memset(ombre, 0, 4096);
  for (int s = 0; s < 3; s++) {
    const float cx = e.formes[s][0], cy = e.formes[s][1], r = e.formes[s][2];
    const float ox0 = cx - lx * r * 0.6f, oy0 = cy - ly * r * 0.6f, rr = r * 1.45f + 1;
    for (int y = max(0, (int)(oy0 - rr)); y < min(64, (int)(oy0 + rr) + 1); y++)
      for (int x = max(0, (int)(ox0 - rr)); x < min(64, (int)(ox0 + rr) + 1); x++) {
        const float ox = x - ox0, oy = y - oy0;
        const float d = sqrtf(ox * ox + oy * oy);
        if (d > rr) continue;
        const float phi = atan2f(oy, ox);
        const float bord = r * (1.25f + 0.12f * nf_sin(2 * phi + e.formes[s][3]) + 0.07f * nf_sin(3 * phi + e.formes[s][4]));
        const float o = borne((bord - d) / 1.6f, 0, 1);
        ombre[y * 64 + x] = max(ombre[y * 64 + x], (uint8_t)roundf(o * 255));
      }
  }
  const float oty = 1.6f * fmaxf(0.0f, ly);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const int i = y * 64 + x;
      float *p = scene[y][x];
      const float om = ombre[i] * k255;
      const float ko = 1 - 0.45f * om;
      p[0] *= ko; p[1] *= ko; p[2] *= ko;
      const float clair = 0.82f + 0.22f * borne(((x - 32) * lx + (y - 32) * ly) / 45, -1, 1);
      const float tx = e.tex[i] * k255;
      const float il = e.ilot[i] * k255;
      if (il > 0) {
        const float kv = (0.7f + 0.5f * tx) * (0.8f + 0.2f * clair) * (1 - 0.5f * om);
        nf_melanger(y, x, il, 62 * kv, 100 * kv, 40 * kv);
      }
      const float pc = e.pierre[i] * k255;
      if (pc > 0) {
        const float lam = borne((e.nx[i] * lx * 0.8f + e.ny[i] * ly * 0.8f + e.nz[i] * 0.6f) * k127, 0, 1);
        const float m = e.mousse[i] * k255, kr = 0.8f + 0.35f * tx, km = 0.8f + 0.4f * tx, kl = 0.34f + 0.85f * lam;
        nf_melanger(y, x, pc, (132 * kr * (1 - m) + 78 * km * m) * kl, (126 * kr * (1 - m) + 122 * km * m) * kl,
                    (118 * kr * (1 - m) + 46 * km * m) * kl);
      }
      if (y < NF_JARDIN_TERRASSE) {                                 // la terrasse fait de l'ombre
        const float ot = borne(y - NF_JARDIN_TERRASSE + oty + 0.5f, 0, 1);
        p[0] *= 1 - 0.4f * ot; p[1] *= 1 - 0.4f * ot; p[2] *= 1 - 0.4f * ot;
      }
      const float a = borne(y - NF_JARDIN_TERRASSE + 0.5f, 0, 1);
      if (a > 0) {
        const uint8_t *b = e.bois[(y - 56) * 64 + x];
        const float kb = 0.75f + 0.3f * clair;
        nf_melanger(y, x, a, b[0] * kb, b[1] * kb, b[2] * kb);
      }
    }
  // la feuille d'erable : elle tombe, se pose, s'envole
  const float cycle = 34.0f;
  const int k = (int)floorf(t / cycle);
  const float phase = t - k * cycle;
  if (phase < 30) {
    const int f = ((k % 32) + 32) % 32;
    const float chute = borne(1 - phase / 7, 0, 1);
    const float hauteur = chute * sqrtf(chute) * 12;
    float x = e.fx[f] - chute * 24 + 2.5f * sinf(phase * 2.2f) * chute;
    float y = e.fy[f] - chute * 17;
    const float vue = fminf(fminf(1.0f, phase / 1.5f), (30 - phase) / 1.5f);   // elle arrive d'en haut, et repart, en fondu
    float tourne = e.fr[f] + phase * 2.5f * chute + 0.5f * (1 - chute);
    if (phase > 24) {
      const float g = phase - 24;
      x += g * g * 1.3f; y += g * g * 0.25f; tourne += g * 0.8f;
    }
    const float echelle = 2.9f * (1 + hauteur / 30);
    const float cq = cosf(tourne + NF_PI / 2), sq = sinf(tourne + NF_PI / 2);
    for (int pass = 0; pass < 2; pass++) {                           // son ombre, puis elle
      const float cxl = x + (pass ? 0.0f : -lx * hauteur * 0.5f), cyl = y + (pass ? 0.0f : -ly * hauteur * 0.5f);
      const int ya = (int)fmaxf(0, cyl - 5), yb = (int)fminf(64, cyl + 6), xa = (int)fmaxf(0, cxl - 5), xb = (int)fminf(64, cxl + 6);
      for (int yy = ya; yy < yb; yy++)
        for (int xx = xa; xx < xb; xx++) {
          const float dx = xx - cxl, dy = yy - cyl;
          const float phi = atan2f(dy, dx) - tourne;
          const float lobe = fabsf(cosf(2.5f * (phi + NF_PI / 2)));   // cinq lobes, le plus grand en haut
          const float rr = echelle * (0.38f + 0.62f * lobe * sqrtf(lobe)) * (1 - 0.25f * borne(sinf(phi), 0, 1));
          float c = borne(rr - sqrtf(dx * dx + dy * dy) + 0.5f, 0, 1);
          const float queue = borne(0.55f - fabsf(dx * sq - dy * cq), 0, 1);
          const float vers = dx * cq + dy * sq;
          if (vers > 0 && vers < echelle * 1.1f) c = fmaxf(c, queue);   // et sa queue
          c *= vue;
          if (c <= 0) continue;
          if (!pass) {
            float *p = scene[yy][xx];
            p[0] *= 1 - 0.35f * c; p[1] *= 1 - 0.35f * c; p[2] *= 1 - 0.35f * c;
          } else {
            const float vif = 0.8f + 0.25f * borne(-(dx * lx + dy * ly) / 2, -1, 1);
            nf_melanger(yy, xx, c, 214 * vif, 46 * vif, 28 * vif);
          }
        }
    }
  }
}
