// lot_eau_ciel.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
// Sous l'eau (recif, abysses, banc, kelp, baleine) et le ciel et l'eau (nuages,
// orage, pluie sur la vitre, surface, etang, plage, cascade). Chaque moteur suit
// son jumeau numpy ; ce qui ne depend que de x ou de y est sorti des boucles,
// et les sinus « d'une somme » (rayons, caustiques, houle) passent par des
// tables par ligne et par colonne : sin(a + b) = sin a cos b + cos a sin b.
#pragma once

// --- les outils du lot ------------------------------------------------------

// le modulo de Python (toujours positif pour m > 0)
inline float ec_pymod(float a, float m) { return a - m * floorf(a / m); }

// _rayons_d_eau, en tables : le sinus de (colonne + ligne) sans sinus par pixel
void ec_rayons(float t, float force, float r = 150, float v = 220, float b = 255) {
  float sx[64], cx[64];
  for (int x = 0; x < 64; x++) {
    const float a = x * 0.22f + t * 0.35f + sinf(x * 0.05f + t * 0.2f) * 2;
    sx[x] = sinf(a);
    cx[x] = cosf(a);
  }
  for (int y = 0; y < 60; y++) {   // a partir de 60, plus rien
    const float sy = sinf(y * 0.09f), cy = cosf(y * 0.09f), f = (1 - y / 60.0f) * force;
    for (int x = 0; x < 64; x++) {
      const float s = 0.5f + 0.5f * (sx[x] * cy + cx[x] * sy);
      const float s2 = s * s, s4 = s2 * s2;
      ajouter(y, x, s4 * s4 * f, r, v, b);
    }
  }
}

// _caustiques, en tables (une fois par image) : a = sin(x + P(y)), b = sin(y + Q(x))
struct ec_caus { float s1[64], c1[64], sq[64], cq[64], sp[64], cp[64], sy[64], cy[64]; };
void ec_caus_preparer(ec_caus &k, float t, float ech, int y0 = 0) {
  for (int x = 0; x < 64; x++) {
    k.s1[x] = sinf(x * 0.32f * ech);
    k.c1[x] = cosf(x * 0.32f * ech);
    const float q = sinf(x * 0.24f * ech - t * 0.7f) * 1.8f - t * 0.3f;
    k.sq[x] = sinf(q);
    k.cq[x] = cosf(q);
  }
  for (int y = y0; y < 64; y++) {
    const float p = sinf(y * 0.21f * ech + t * 0.9f) * 1.8f + t * 0.4f;
    k.sp[y] = sinf(p);
    k.cp[y] = cosf(p);
    k.sy[y] = sinf(y * 0.3f * ech);
    k.cy[y] = cosf(y * 0.3f * ech);
  }
}
inline float ec_caus_val(const ec_caus &k, int x, int y) {
  const float a = k.s1[x] * k.cp[y] + k.c1[x] * k.sp[y];
  const float b = k.sy[y] * k.cq[x] + k.cy[y] * k.sq[x];
  const float c = borne(1 - fabsf(a + b) * 0.9f, 0, 1);
  return c * c * c;
}

// _fenetre : les poids des quatre voisines, une fois par image (k : un facteur en plus)
struct ec_fen { int x0, y0; float a, b, c, d; };
ec_fen ec_fen_placer(float ox, float oy, float k = 1.0f) {
  ec_fen f;
  f.x0 = (int)floorf(ox);
  f.y0 = (int)floorf(oy);
  const float fx = ox - f.x0, fy = oy - f.y0;
  k *= 1.0f / 65535.0f;
  f.a = (1 - fx) * (1 - fy) * k;
  f.b = fx * (1 - fy) * k;
  f.c = (1 - fx) * fy * k;
  f.d = fx * fy * k;
  return f;
}
// ajoute la ligne y de la fenetre a sortie[64]
void ec_fen_ligne(const uint16_t *champ, int taille, const ec_fen &f, int y, float *sortie) {
  const int m = taille - 1;
  const uint16_t *l0 = champ + ((y + f.y0) & m) * taille, *l1 = champ + ((y + f.y0 + 1) & m) * taille;
  for (int x = 0; x < 64; x++) {
    const int xa = (x + f.x0) & m, xb = (x + f.x0 + 1) & m;
    sortie[x] += l0[xa] * f.a + l0[xb] * f.b + l1[xa] * f.c + l1[xb] * f.d;
  }
}
inline float ec_fen_val(const uint16_t *champ, int taille, const ec_fen &f, int x, int y) {
  const int m = taille - 1;
  const uint16_t *l0 = champ + ((y + f.y0) & m) * taille, *l1 = champ + ((y + f.y0 + 1) & m) * taille;
  const int xa = (x + f.x0) & m, xb = (x + f.x0 + 1) & m;
  return l0[xa] * f.a + l0[xb] * f.b + l1[xa] * f.c + l1[xb] * f.d;
}

// un ±1 au hasard
inline float ec_signe() { return (aleatoire() >> 16) & 1 ? 1.0f : -1.0f; }

// --- le recif de corail -------------------------------------------------------

static const float ec_recif_couleurs[5][3] = {{255, 110, 120}, {255, 170, 70}, {190, 90, 255}, {255, 90, 190}, {90, 230, 200}};

// humeurs : 0 = tropical, 1 = nuit
struct E_recif {
  float cx[9], cy[9], cr[9];
  uint8_t cc[9];
  float px[8], py[8], ps[8], pv[8], pp[8];
  uint8_t pc[8];
  float kx[60], ky[60], kp[60];   // le plancton (la nuit)
  Bulles bu;
};
void s_recif(int humeur, bool debut, float t, float ecoule, float dt) {
  E_recif &e = etat_ecran<E_recif>(debut);
  (void)ecoule;
  const bool nuit = humeur == 1;
  if (debut) {
    for (int i = 0; i < 9; i++) {
      e.cx[i] = hasard(0, 64); e.cy[i] = hasard(50, 60); e.cr[i] = hasard(3, 7); e.cc[i] = i % 5;
    }
    for (int i = 0; i < 8; i++) {
      e.px[i] = hasard(0, 64); e.py[i] = hasard(10, 46); e.ps[i] = ec_signe(); e.pv[i] = hasard(5, 12);
      e.pc[i] = aleatoire() % 5; e.pp[i] = hasard(0, 6);
    }
    for (int i = 0; i < 60; i++) { e.kx[i] = hasard(0, 64); e.ky[i] = hasard(0, 56); e.kp[i] = hasard(0, 6); }
    semer_bulles(e.bu, 8);
  }
  if (!nuit) {
    degrade2(40, 165, 200, 4, 36, 78);
    ec_rayons(t, 0.35f);
    for (int x = 0; x < 64; x++) {   // la surface qui scintille
      const float k = 0.5f + 0.5f * sinf(x * 0.7f + t * 2);
      ajouter(0, x, k, 60, 80, 70);
      ajouter(1, x, k, 60, 80, 70);
    }
  } else {
    degrade2(6, 18, 44, 0, 3, 12);
  }
  float sable[64];
  for (int x = 0; x < 64; x++) sable[x] = 58 + 2 * sinf(x * 0.15f) + sinf(x * 0.4f);
  if (!nuit) peindre_sous(sable, 150, 130, 90);
  else peindre_sous(sable, 14, 14, 22);
  for (int i = 0; i < 9; i++) {   // des coraux en boule, et leurs branches
    const float cx = e.cx[i], cy = e.cy[i], r = e.cr[i];
    const float *c = ec_recif_couleurs[e.cc[i]];
    const float lueur = nuit ? (0.6f + 0.4f * sinf(t * 1.5f + cx)) * 0.9f : 0.85f;
    const int x0 = max(0, (int)ceilf(cx - r)), x1 = min(63, (int)floorf(cx + r));
    const int y0 = max(0, (int)ceilf(cy - r / 1.3f)), y1 = min(63, (int)floorf(cy + r / 1.3f));
    for (int y = y0; y <= y1; y++)
      for (int x = x0; x <= x1; x++) {
        const float dx = x - cx, dy = (y - cy) * 1.3f, d = sqrtf(dx * dx + dy * dy);
        if (d > r || (d >= r * 0.6f && sinf(x * 1.7f + y * 1.1f) <= -0.4f)) continue;
        const float k = (0.7f + 0.3f * (1 - d / r)) * lueur;
        peindre(y, x, c[0] * k, c[1] * k, c[2] * k);
      }
  }
  const float ka = nuit ? 0.9f : 0.75f;
  for (int i = 0; i < 6; i++)   // des anemones qui ondulent
    for (int k = 0; k < 6; k++)
      pointer(58 - k, 6 + i * 11 + sinf(t * 1.4f + i + k * 0.4f) * k * 0.35f, 255 * ka, 140 * ka, 180 * ka);
  const float kp = nuit ? 1.3f : 1.0f;
  for (int i = 0; i < 8; i++) {
    e.px[i] += e.ps[i] * e.pv[i] * dt;
    if (e.px[i] > 70 || e.px[i] < -6) e.ps[i] = -e.ps[i];
    const float *c = ec_recif_couleurs[e.pc[i]];
    poisson(e.px[i], e.py[i] + sinf(t * 1.3f + e.pp[i]) * 1.2f, (int)e.ps[i], c[0] * kp, c[1] * kp, c[2] * kp);
  }
  if (nuit)   // le plancton qui scintille
    for (int i = 0; i < 60; i++) {
      const float s = fmaxf(0.0f, sinf(t * 1.7f + e.kp[i] * 3)), k = s * s;
      pointer(e.ky[i] + sinf(t * 0.3f + e.kp[i]) * 2, e.kx[i] + cosf(t * 0.2f + e.kp[i]) * 2, 60 * k, 220 * k, 255 * k);
    }
  bulles(e.bu, t, dt);
}

// --- les abysses --------------------------------------------------------------

// humeurs : 0 = bleu, 1 = violet
struct E_abysses { float nx[50], ny[50], nv[50], ex[90], ey[90], ep[90]; };
void s_abysses(int humeur, bool debut, float t, float ecoule, float dt) {
  E_abysses &e = etat_ecran<E_abysses>(debut);
  (void)ecoule;
  const float tr = humeur == 1 ? 200 : 40, tv = humeur == 1 ? 80 : 200, tb = 255;
  if (debut) {
    for (int i = 0; i < 50; i++) { e.nx[i] = hasard(0, 64); e.ny[i] = hasard(0, 64); e.nv[i] = hasard(0.5f, 2); }
    for (int i = 0; i < 90; i++) { e.ex[i] = hasard(0, 64); e.ey[i] = hasard(0, 64); e.ep[i] = hasard(0, 6); }
  }
  degrade2(2, 6, 16, 0, 0, 3);
  for (int i = 0; i < 50; i++) {   // la neige marine
    e.ny[i] = fmodf(e.ny[i] + e.nv[i] * dt, 64);
    pointer(e.ny[i], e.nx[i] + sinf(t * 0.4f + e.ny[i] * 0.2f), 30, 34, 40);
  }
  // le poisson-lanterne : sa lumiere qui se balance, son corps a peine devine
  const float lx = 32 + 20 * sinf(t * 0.13f);
  const float ly = 30 + 8 * sinf(t * 0.21f) + sinf(t * 1.7f) * 1.5f;
  halo(lx, ly, 3.5f, tr, tv, tb, (0.8f + 0.2f * sinf(t * 3)) * 1.1f);
  const float sens = cosf(t * 0.13f) > 0 ? 1.0f : -1.0f;
  const float bx = lx - sens * 7, by = ly + 4;
  for (int y = max(0, (int)ceilf(by - 3.5f)); y <= min(63, (int)floorf(by + 3.5f)); y++)
    for (int x = max(0, (int)ceilf(bx - 6)); x <= min(63, (int)floorf(bx + 6)); x++) {
      const float u = (x - bx) / 6.0f, v = (y - by) / 3.5f;
      if (u * u + v * v <= 1) pointer(y, x, tr * 0.2f, tv * 0.2f, tb * 0.2f);
    }
  for (int k = 0; k < 5; k++) pointer(ly + 1 + k * 0.6f, lx - sens * k * 1.2f, tr * 0.25f, tv * 0.25f, tb * 0.25f);
  for (int i = 0; i < 90; i++) {   // des vagues de plancton qui s'allument
    const float s = fmaxf(0.0f, sinf(t * 0.7f - e.ex[i] * 0.12f + e.ep[i] * 0.3f));
    const float k = 0.15f + 0.85f * s * s * s;
    pointer(e.ey[i] + sinf(t * 0.2f + e.ep[i]) * 3, e.ex[i], tr * k, tv * k, tb * k);
  }
}

// --- le banc de poissons ------------------------------------------------------

// humeurs : 0 = lagune, 1 = ocean
struct E_banc { float ox[70], oy[70], ph[70], ec[70]; Bulles bu; };
void s_banc(int humeur, bool debut, float t, float ecoule, float dt) {
  E_banc &e = etat_ecran<E_banc>(debut);
  (void)ecoule;
  const bool lagune = humeur == 0;
  if (debut) {
    for (int i = 0; i < 70; i++) { e.ox[i] = hasard(-1, 1); e.oy[i] = hasard(-1, 1); e.ph[i] = hasard(0, 6); e.ec[i] = hasard(0.6f, 1.4f); }
    semer_bulles(e.bu, 6);
  }
  if (lagune) degrade2(60, 190, 200, 10, 70, 110);
  else degrade2(14, 50, 100, 2, 8, 30);
  ec_rayons(t, lagune ? 0.3f : 0.2f);
  const float cx = 32 + 16 * sinf(t * 0.23f), cy = 30 + 10 * sinf(t * 0.31f);   // le banc suit un chemin lent
  const float rayon = 13 + 5 * sinf(t * 0.4f);                                  // il se serre, s'ecarte
  const float va = cosf(t * 0.23f) * 16 * 0.23f;
  const float cr = lagune ? 210 : 170, cv = lagune ? 235 : 200, cb = lagune ? 240 : 230;
  for (int i = 0; i < 70; i++) {
    const float a = t * 0.9f + e.ph[i], ca = cosf(a), sa = sinf(a);
    const float px = cx + (e.ox[i] * rayon + ca * 3) * e.ec[i];
    const float py = cy + (e.oy[i] * rayon * 0.6f + sinf(a * 1.3f) * 2) * e.ec[i];
    const float s = va - sa * 2.7f + 1e-6f, sens = s > 0 ? 1.0f : s < 0 ? -1.0f : 0.0f;
    const float k = 0.6f + 0.4f * sinf(a * 2 + t);   // des flancs qui brillent en tournant
    pointer(py, px, cr * k, cv * k, cb * k);
    pointer(py, px - sens, cr * k * 0.75f, cv * k * 0.75f, cb * k * 0.75f);
    pointer(py, px - 2 * sens, cr * k * 0.45f, cv * k * 0.45f, cb * k * 0.45f);
  }
  for (int x = 0; x < 64; x++) {
    const float fond = lagune ? 58 + 1.5f * sinf(x * 0.17f) : 60 + sinf(x * 0.2f);
    for (int y = max(0, (int)ceilf(fond)); y < 64; y++) {
      if (lagune) peindre(y, x, 200, 190, 140);
      else peindre(y, x, 4, 10, 20);
    }
  }
  bulles(e.bu, t, dt);
}

// --- la foret de kelp ---------------------------------------------------------

// humeurs : 0 = emeraude, 1 = dore
struct E_kelp {
  float ax[15], aph[15], asomb[15], ahaut[15];
  float px[5], py[5], ps[5], pv[5], pp[5];
  float sy[64], cy[64];   // sin, cos (y * 0.12)
};
void s_kelp(int humeur, bool debut, float t, float ecoule, float dt) {
  E_kelp &e = etat_ecran<E_kelp>(debut);
  (void)ecoule;
  const bool dore = humeur == 1;
  if (debut) {
    for (int i = 0; i < 15; i++) { e.ax[i] = hasard(-2, 66); e.aph[i] = hasard(0, 6); e.asomb[i] = hasard(0.6f, 1.0f); e.ahaut[i] = hasard(4, 22); }
    for (int i = 0; i < 5; i++) { e.px[i] = hasard(0, 64); e.py[i] = hasard(12, 44); e.ps[i] = ec_signe(); e.pv[i] = hasard(3, 7); e.pp[i] = hasard(0, 6); }
    for (int y = 0; y < 64; y++) { e.sy[y] = sinf(y * 0.12f); e.cy[y] = cosf(y * 0.12f); }
  }
  if (dore) { degrade2(150, 170, 90, 20, 40, 30); ec_rayons(t, 0.4f, 255, 220, 140); }
  else { degrade2(30, 120, 110, 2, 24, 30); ec_rayons(t, 0.4f, 160, 255, 220); }
  for (int i = 0; i < 15; i++) {   // les algues, et leurs feuilles de part et d'autre
    const float q = t * 0.7f + e.aph[i], sq = sinf(q), cq = cosf(q);
    const float r = (dore ? 120 : 40) * e.asomb[i], v = (dore ? 140 : 150) * e.asomb[i], b = (dore ? 40 : 70) * e.asomb[i];
    for (int y = (int)e.ahaut[i]; y < 64; y++) {
      const float x = e.ax[i] + (e.sy[y] * cq + e.cy[y] * sq) * (64 - y) * 0.09f;
      pointer(y, x - 1, r * 0.7f, v * 0.7f, b * 0.7f);
      pointer(y, x, r, v, b);
      pointer(y, x + 1, r, v, b);
      pointer(y, x + 2, r * 0.7f, v * 0.7f, b * 0.7f);
      if (y % 5 == 0)
        for (int k = 0; k < 3; k++) {
          pointer(y - k, x + 3 + k, r * 1.2f, v * 1.2f, b * 1.2f);
          pointer(y + 2 - k, x - 2 - k, r * 1.1f, v * 1.1f, b * 1.1f);
        }
    }
  }
  for (int i = 0; i < 5; i++) {
    e.px[i] += e.ps[i] * e.pv[i] * dt;
    if (e.px[i] > 70 || e.px[i] < -6) e.ps[i] = -e.ps[i];
    const float y = e.py[i] + sinf(t + e.pp[i]) * 1.5f;
    if (dore) poisson(e.px[i], y, (int)e.ps[i], 230, 200, 120, 3);
    else poisson(e.px[i], y, (int)e.ps[i], 180, 220, 230, 3);
  }
  for (int x = 0; x < 64; x++) {
    const float fond = 61 + sinf(x * 0.3f);
    for (int y = max(0, (int)ceilf(fond)); y < 64; y++) {
      if (dore) peindre(y, x, 30, 30, 20);
      else peindre(y, x, 6, 18, 16);
    }
  }
}

// --- la baleine ---------------------------------------------------------------

// humeurs : 0 = bleu, 1 = plancton
struct E_baleine {
  float px[420], py[420], pp[420];
  float sx[64];               // sin(x * 1.2) : le ventre
  uint8_t masque[64 * 64];    // sa silhouette (elle cache le plancton)
};
void s_baleine(int humeur, bool debut, float t, float ecoule, float dt) {
  E_baleine &e = etat_ecran<E_baleine>(debut);
  (void)ecoule; (void)dt;
  const bool plancton = humeur == 1;
  const int n = plancton ? 420 : 220;
  if (debut) {
    for (int i = 0; i < n; i++) { e.px[i] = hasard(0, 64); e.py[i] = hasard(0, 64); e.pp[i] = hasard(0, 6); }
    for (int x = 0; x < 64; x++) e.sx[x] = sinf(x * 1.2f);
  }
  if (!plancton) { degrade2(30, 110, 170, 2, 20, 50); ec_rayons(t, 0.35f); }
  else degrade2(3, 10, 26, 0, 2, 8);
  // elle traverse en 40 s, puis revient de l'autre cote
  const float cycle = fmodf(t * 0.03f + 0.25f, 1.0f);
  const float bx = -30 + cycle * 124, by = 34 + 4 * sinf(t * 0.25f), houle = sinf(t * 0.8f) * 1.5f;
  const float tr = plancton ? 4 : 16, tv = plancton ? 10 : 30, tb = plancton ? 18 : 46;
  memset(e.masque, 0, sizeof e.masque);
  const int y0 = max(0, (int)floorf(by - 9)), y1 = min(63, (int)ceilf(by + 12));
  const int x0 = max(0, (int)floorf(bx - 31)), x1 = min(63, (int)ceilf(bx + 25));
  for (int y = y0; y <= y1; y++) {
    const float Y = (float)y, ombre = 1 + 0.25f * borne((by - Y) / 6, 0, 1);
    for (int x = x0; x <= x1; x++) {
      const float X = (float)x, dx = X - bx;
      const float u = dx / 22.0f, v = (Y - by - dx * 0.05f) / 6.5f;
      bool m = u * u + v * v <= 1;   // le corps
      if (!m && X < bx - 18 && X > bx - 30)   // la queue
        m = fabsf(Y - by - houle * (bx - 18 - X) / 12) <= (bx - 18 - X) * 0.35f;
      if (!m) {   // la tete
        const float a = (X - bx - 16) / 8.0f, b = (Y - by - 1) / 5.0f;
        m = a * a + b * b <= 1;
      }
      if (!m)   // la nageoire
        m = fabsf(X - bx - 4) < 5 && Y > by + 3 && Y < by + 9 + houle && Y - by - 3 < (X - bx + 2) * 0.9f;
      if (!m) continue;
      e.masque[y * 64 + x] = 1;
      const float k = (Y > by + 2 && e.sx[x] > 0.3f) ? 1.6f : ombre;
      peindre(y, x, tr * k, tv * k, tb * k);
    }
  }
  const float cr = plancton ? 80 : 200, cv = 230, cb = plancton ? 255 : 240;
  for (int i = 0; i < n; i++) {   // le plancton : pres d'elle, il s'allume
    const float qx = e.px[i] + sinf(t * 0.2f + e.pp[i]) * 2, qy = e.py[i] + cosf(t * 0.15f + e.pp[i]) * 2;
    const int ix = min(63, max(0, (int)qx)), iy = min(63, max(0, (int)qy));
    if (e.masque[iy * 64 + ix]) continue;   // sa silhouette le cache
    float lum = 0.25f;
    if (plancton) {
      const float a = (qx - bx) / 30.0f, b = (qy - by) / 12.0f;
      lum = 0.3f + 1.1f * expf(-(a * a + b * b));
    }
    const float k = lum * (0.6f + 0.4f * sinf(t * 2 + e.pp[i] * 3));
    pointer(qy, qx, cr * k, cv * k, cb * k);
  }
}

// --- les nuages ---------------------------------------------------------------

// (ciel haut, ciel bas, nuage eclaire, nuage ombre, soleil) -- NUAGES_HUMEURS ; pas de soleil si rouge < 0
static const float ec_nuages_humeurs[4][5][3] = {
  {{60, 130, 220}, {150, 200, 245}, {250, 250, 255}, {150, 165, 190}, {255, 250, 220}},
  {{60, 40, 110}, {250, 140, 90}, {255, 190, 150}, {120, 60, 100}, {255, 200, 120}},
  {{40, 44, 54}, {80, 86, 96}, {150, 156, 168}, {30, 32, 40}, {-1, 0, 0}},
  {{20, 6, 40}, {90, 20, 90}, {255, 60, 170}, {40, 10, 70}, {-1, 0, 0}},
};

// humeurs : 0 = ete, 1 = coucher, 2 = orage, 3 = neon
struct E_nuages { uint16_t a[128 * 128], b[128 * 128]; };
void s_nuages(int humeur, bool debut, float t, float ecoule, float dt) {
  E_nuages &e = etat_ecran<E_nuages>(debut);
  (void)ecoule; (void)dt;
  const float (*h)[3] = ec_nuages_humeurs[humeur];
  const bool orage = humeur == 2, neon = humeur == 3;
  if (debut) { brume_n(e.a, 128, 26); brume_n(e.b, 128, 9); }
  degrade2(h[0][0], h[0][1], h[0][2], h[1][0], h[1][1], h[1][2]);
  if (h[4][0] >= 0)   // le soleil, et sa lueur
    for (int y = 0; y < 43; y++)
      for (int x = 24; x < 64; x++) {
        const float d = hypotf(x - 46.0f, y - 20.0f);
        if (d <= 4.5f) { peindre(y, x, h[4][0], h[4][1], h[4][2]); continue; }
        const float g = borne(1 - d / 22, 0, 1);
        if (g > 0) ajouter(y, x, g * g, 60, 50, 20);
      }
  const ec_fen fa = ec_fen_placer(t * 1.2f, 10, 0.75f), fb = ec_fen_placer(t * 2.0f, 30 + t * 0.2f, 0.25f);
  const float seuil = 0.55f + 0.1f * sinf(t * 0.12f);   // ils se forment, et se defont
  float eclair = 0;
  if (orage) {   // un eclair dans les nuages, de temps en temps
    const float s = sinf(t * 0.9f), s2 = s * s, s4 = s2 * s2, s8 = s4 * s4, s16 = s8 * s8, s32 = s16 * s16;
    eclair = s32 * s8 * (0.5f + 0.5f * sinf(t * 23));
  }
  // le champ f, ligne par ligne ; « dessus » le compare a la ligne deux plus haut (np.roll, qui boucle)
  float f[4][64];
  for (int k = 62; k < 64; k++) {
    for (int x = 0; x < 64; x++) f[k & 3][x] = 0;
    ec_fen_ligne(e.a, 128, fa, k, f[k & 3]);
    ec_fen_ligne(e.b, 128, fb, k, f[k & 3]);
  }
  const float ombre[3] = {h[3][0], h[3][1], h[3][2]};
  const float ecart[3] = {h[2][0] - h[3][0], h[2][1] - h[3][1], h[2][2] - h[3][2]};
  for (int y = 0; y < 64; y++) {
    float *ici = f[y & 3];
    const float *avant = f[(y + 2) & 3];   // la ligne y - 2
    for (int x = 0; x < 64; x++) ici[x] = 0;
    ec_fen_ligne(e.a, 128, fa, y, ici);
    ec_fen_ligne(e.b, 128, fb, y, ici);
    const float hy = borne(1.3f - y / 64.0f, 0, 1), cyan = borne((y - 20) / 44.0f, 0, 1) * 0.4f;
    for (int x = 0; x < 64; x++) {
      const float nuage = borne((ici[x] - seuil) * 6, 0, 1) * hy;
      if (nuage <= 0) continue;
      const float dessus = borne((ici[x] - avant[x]) * 8 + 0.5f, 0, 1);   // le haut d'un nuage, eclaire
      float c[3];
      for (int k = 0; k < 3; k++) c[k] = ombre[k] + ecart[k] * dessus;
      if (neon) {   // la ville les eclaire par en dessous, en cyan et magenta
        c[0] = c[0] * 0.6f;
        c[1] = c[1] * 0.6f + 220 * cyan;
        c[2] = c[2] * 0.6f + 255 * cyan;
      }
      float *p = scene[y][x];
      for (int k = 0; k < 3; k++) p[k] = p[k] * (1 - nuage) + c[k] * nuage;
      if (orage) ajouter(y, x, nuage * eclair, 120, 120, 160);
    }
  }
  if (neon)   // la ville, en contrebas
    for (int x = 0; x < 64; x++) {
      const int haut = 56 + (int)rintf(sinf(x * 0.9f) * 2 + sinf(x * 0.33f) * 3);
      for (int y = max(0, haut); y < 64; y++) peindre(y, x, 10, 4, 20);
    }
}

// --- l'orage ------------------------------------------------------------------

// humeurs : 0 = campagne, 1 = ville
struct E_orage {
  Pluie pl;
  float eclair_t, eclair_debut, ex[50];   // _eclair : le prochain, le dernier, son trace
  int nb;
  uint8_t ix[12], il[12], ih[12];         // les immeubles (x, largeur, haut)
};
void s_orage(int humeur, bool debut, float t, float ecoule, float dt) {
  E_orage &e = etat_ecran<E_orage>(debut);
  (void)t;
  const bool ville = humeur == 1;
  if (debut) {
    semer_pluie(e.pl, 70);
    e.eclair_t = 1.5f;
    e.eclair_debut = -9;
    e.nb = 0;
    for (int x0 = 0; x0 < 64 && e.nb < 12;) {
      const int larg = 5 + aleatoire() % 5;
      e.ix[e.nb] = x0; e.il[e.nb] = larg; e.ih[e.nb] = 36 + aleatoire() % 18;
      e.nb++;
      x0 += larg + 1;
    }
  }
  if (ecoule >= e.eclair_t) {   // un eclair : un trace en zigzag qui descend
    e.eclair_t = ecoule + hasard(2.5f, 6.0f);
    float x = hasard(10, 54);
    for (int y = 0; y < 50; y++) { x += hasard(-1.3f, 1.3f); e.ex[y] = x; }
    e.eclair_debut = ecoule;
  }
  const float age = ecoule - e.eclair_debut;
  const bool trace = age <= 0.35f;
  const float eclat = trace ? (1 - age / 0.35f) * (0.6f + 0.4f * sinf(age * 60)) : 0.0f;
  degrade2(14 + 90 * eclat, 16 + 90 * eclat, 24 + 120 * eclat, 40 + 90 * eclat, 44 + 90 * eclat, 58 + 120 * eclat);
  if (trace) {
    const float k = fminf(1.0f, eclat * 1.5f);
    for (int y = 0; y < 50; y++) pointer(y, e.ex[y], 230 * k, 230 * k, 255 * k);
  }
  if (ville) {
    for (int i = 0; i < e.nb; i++) {
      const int x0 = e.ix[i], x1 = min(64, x0 + e.il[i]), h = e.ih[i];
      for (int y = h; y < 64; y++)
        for (int x = x0; x < x1; x++) peindre(y, x, 10 + 50 * eclat, 11 + 50 * eclat, 18 + 70 * eclat);
      for (int y = h + 2; y < 62; y++)
        if (y % 3 == 0)
          for (int x = x0 + 1; x < x1; x++)
            if (x % 2 == 1 && (y * 7 + x * 13) % 5 == 0) peindre(y, x, 200, 160, 80);
    }
  } else {
    float colline[64];
    for (int x = 0; x < 64; x++) colline[x] = 50 + 3 * sinf(x * 0.08f + 1) + 1.5f * sinf(x * 0.3f);
    peindre_sous(colline, 8 + 40 * eclat, 12 + 50 * eclat, 10 + 40 * eclat);
    for (int y = 34; y < 50; y++)   // l'arbre
      for (int x = 0; x < 64; x++)
        if (fabsf(x - 46.0f) <= (y - 34) * 0.35f) peindre(y, x, 6 + 20 * eclat, 8 + 24 * eclat, 8 + 20 * eclat);
  }
  pluie(e.pl, dt, 110, 120, 160);
}

// --- la pluie sur la vitre ----------------------------------------------------

static const float ec_vitre_couleurs[3][4][3] = {
  {{255, 40, 140}, {0, 220, 255}, {250, 240, 90}, {160, 60, 255}},
  {{255, 160, 60}, {255, 120, 40}, {255, 210, 120}, {200, 90, 50}},
  {{80, 140, 255}, {120, 200, 255}, {200, 220, 255}, {60, 90, 200}},
};

// humeurs : 0 = neon, 1 = ambre, 2 = bleu
struct E_pluie_vitre {
  float bx[22], by[22], br[22], bp[22];
  uint8_t bc[22];
  float gx[26], gy[26], gv[26], gp[26];   // les gouttes : x, y, vitesse (0 = posee), attente
};
void s_pluie_vitre(int humeur, bool debut, float t, float ecoule, float dt) {
  E_pluie_vitre &e = etat_ecran<E_pluie_vitre>(debut);
  (void)ecoule;
  if (debut) {
    for (int i = 0; i < 22; i++) {
      e.bx[i] = hasard(0, 64); e.by[i] = hasard(8, 60); e.br[i] = hasard(2.5f, 6); e.bc[i] = aleatoire() % 4; e.bp[i] = hasard(0, 6);
    }
    for (int i = 0; i < 26; i++) { e.gx[i] = hasard(0, 64); e.gy[i] = hasard(0, 64); e.gv[i] = 0; e.gp[i] = hasard(0, 1); }
  }
  degrade2(8, 6, 16, 20, 14, 30);
  for (int i = 0; i < 22; i++) {   // les lumieres floues de la ville
    const float cx = e.bx[i] + sinf(t * 0.1f + e.bp[i]) * 2, cy = e.by[i], r = e.br[i];
    const float f = 0.35f + 0.15f * sinf(t * 0.6f + e.bp[i]);
    const float *c = ec_vitre_couleurs[humeur][e.bc[i]];
    for (int y = max(0, (int)floorf(cy - r)); y <= min(63, (int)ceilf(cy + r)); y++)
      for (int x = max(0, (int)floorf(cx - r)); x <= min(63, (int)ceilf(cx + r)); x++) {
        const float d = hypotf(x - cx, y - cy), k = borne((r - d) / 1.5f, 0, 1);
        if (k > 0) ajouter(y, x, k * f, c[0], c[1], c[2]);
      }
  }
  for (int i = 0; i < 26; i++) {   // les gouttes : posees, puis elles glissent
    e.gp[i] += dt * 0.12f;
    if (e.gp[i] > 1) { e.gv[i] = hasard(6, 16); e.gp[i] = -hasard(0, 2); }
    if (e.gv[i] > 0) {
      e.gy[i] += e.gv[i] * dt;
      e.gx[i] += sinf(e.gy[i] * 0.5f) * 0.1f * dt * 30;   // 0.1 par image, a 30 images/s
      if (e.gy[i] > 66) { e.gx[i] = hasard(0, 64); e.gy[i] = hasard(-4, 30); e.gv[i] = 0; }
      for (int k = 1; k < 6; k++) {   // la trainee, plus claire
        const float q = 1 - k / 6.0f;
        pointer(e.gy[i] - k * 1.5f, e.gx[i], 70 * q, 70 * q, 90 * q);
      }
    }
    pointer(e.gy[i], e.gx[i], 190, 200, 220);
    pointer(e.gy[i] + 1, e.gx[i], 120, 130, 150);
  }
}

// --- la surface de l'eau ------------------------------------------------------

// humeurs : 0 = piscine, 1 = lagon, 2 = lune
struct E_surface {
  ec_caus ca;
  float ox[5], oy[5], op[5];      // l'ombre des poissons (le lagon)
  float rx[6], ry[6], rd[6];      // les ronds : ou, depuis quand
  int nr;
  float ronds_t;
};
void s_surface(int humeur, bool debut, float t, float ecoule, float dt) {
  E_surface &e = etat_ecran<E_surface>(debut);
  if (debut) {
    for (int i = 0; i < 5; i++) { e.ox[i] = hasard(0, 64); e.oy[i] = hasard(0, 64); e.op[i] = hasard(0, 6); }
    e.nr = 0;
    e.ronds_t = 1.0f;
  }
  ec_caus_preparer(e.ca, t, 1.0f);
  if (humeur == 0) {   // la piscine : les joints du carrelage qui ondulent
    float jx[64];
    for (int x = 0; x < 64; x++) jx[x] = 0.6f * sinf(x * 0.3f + t);
    for (int y = 0; y < 64; y++) {
      const float jy = 0.6f * sinf(y * 0.3f + t);
      for (int x = 0; x < 64; x++) {
        const bool joint = ec_pymod(x + jy, 8) < 0.7f || ec_pymod(y + jx[x], 8) < 0.7f;
        const float c = ec_caus_val(e.ca, x, y);
        if (joint) peindre(y, x, 20 + 150 * c, 110 + 220 * c, 160 + 230 * c);
        else peindre(y, x, 30 + 150 * c, 150 + 220 * c, 200 + 230 * c);
      }
    }
  } else if (humeur == 1) {   // le lagon
    for (int y = 0; y < 64; y++) {
      const float k = y / 64.0f;
      const float r = 40 - 20 * k, v = 190 - 70 * k, b = 200 - 30 * k;
      for (int x = 0; x < 64; x++) {
        const float c = ec_caus_val(e.ca, x, y);
        peindre(y, x, r + 120 * c, v + 200 * c, b + 190 * c);
      }
    }
    for (int i = 0; i < 5; i++) {   // l'ombre des poissons sur le sable
      e.ox[i] = fmodf(e.ox[i] + dt * 4, 70);
      const float cx = e.ox[i], cy = e.oy[i] + sinf(t * 0.5f + e.op[i]) * 3;
      for (int y = max(0, (int)ceilf(cy - 1.3f)); y <= min(63, (int)floorf(cy + 1.3f)); y++)
        for (int x = max(0, (int)ceilf(cx - 3)); x <= min(63, (int)floorf(cx + 3)); x++) {
          const float u = (x - cx) / 3.0f, v = (y - cy) / 1.3f;
          if (u * u + v * v <= 1)
            for (int k = 0; k < 3; k++) scene[y][x][k] *= 0.65f;
        }
    }
  } else {   // la lune, son reflet qui tremble
    for (int y = 0; y < 64; y++) {
      const float m = 34 + sinf(y * 0.6f + t * 1.5f) * 2, q = (y - 30) / 22.0f, ry = expf(-q * q);
      for (int x = 0; x < 64; x++) {
        const float c = ec_caus_val(e.ca, x, y), u = (x - m) / 6.0f;
        float r = 6 + 10 * c, v = 12 + 20 * c, b = 28 + 40 * c;
        if (u * u < 30) {
          const float k = expf(-u * u) * ry * (0.4f + 0.6f * c);
          r += 200 * k; v += 210 * k; b += 230 * k;
        }
        peindre(y, x, r, v, b);
      }
    }
  }
  if (ecoule >= e.ronds_t) {   // une goutte, un rond qui s'elargit
    e.ronds_t = ecoule + hasard(1.5f, 4.0f);
    if (e.nr < 6) { e.rx[e.nr] = hasard(8, 56); e.ry[e.nr] = hasard(8, 56); e.rd[e.nr] = ecoule; e.nr++; }
  }
  int garde = 0;
  for (int i = 0; i < e.nr; i++)
    if (ecoule - e.rd[i] < 3.0f) { e.rx[garde] = e.rx[i]; e.ry[garde] = e.ry[i]; e.rd[garde] = e.rd[i]; garde++; }
  e.nr = garde;
  for (int i = 0; i < e.nr; i++) {
    const float age = ecoule - e.rd[i], R = age * 7, fondu = 1 - age / 3.0f, cx = e.rx[i], cy = e.ry[i];
    const float lim = R + 4.5f * 0.9f;
    for (int y = max(0, (int)floorf(cy - lim)); y <= min(63, (int)ceilf(cy + lim)); y++)
      for (int x = max(0, (int)floorf(cx - lim)); x <= min(63, (int)ceilf(cx + lim)); x++) {
        const float q = (hypotf(x - cx, y - cy) - R) / 0.9f;
        if (q * q < 20) ajouter(y, x, expf(-q * q) * fondu, 90, 110, 120);
      }
  }
}

// --- l'etang aux carpes -------------------------------------------------------

static const float ec_koi_couleurs[3][3] = {{255, 120, 40}, {250, 245, 240}, {255, 200, 60}};

// humeurs : 0 = jour, 1 = nuit
struct E_etang {
  ec_caus ca;
  float kr[5], kph[5], kv[5], ks[5];
  float nx[6], ny[6], nr[6], nph[6];
};
void s_etang(int humeur, bool debut, float t, float ecoule, float dt) {
  E_etang &e = etat_ecran<E_etang>(debut);
  (void)ecoule; (void)dt;
  const bool nuit = humeur == 1;
  if (debut) {
    for (int i = 0; i < 5; i++) { e.kr[i] = hasard(8, 20); e.kph[i] = hasard(0, 6); e.kv[i] = hasard(0.25f, 0.45f); e.ks[i] = ec_signe(); }
    for (int i = 0; i < 6; i++) { e.nx[i] = hasard(4, 60); e.ny[i] = hasard(4, 60); e.nr[i] = hasard(3, 6); e.nph[i] = hasard(0, 6); }
  }
  ec_caus_preparer(e.ca, t * 0.6f, 0.7f);
  const float fr = nuit ? 4 : 20, fv = nuit ? 10 : 60, fb = nuit ? 18 : 50;
  const float cr = nuit ? 8 : 30, cv = nuit ? 14 : 60, cb = nuit ? 24 : 50;
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float c = ec_caus_val(e.ca, x, y);
      peindre(y, x, fr + cr * c, fv + cv * c, fb + cb * c);
    }
  float ondule[10];
  for (int k = 0; k < 10; k++) ondule[k] = sinf(t * 4 + k * 0.6f) * k * 0.08f;
  for (int i = 0; i < 5; i++) {   // les koi : un corps qui ondule, la queue plus fine
    const float a = t * e.kv[i] * e.ks[i] + e.kph[i], ca = cosf(a), sa = sinf(a);
    const float cx = 32 + e.kr[i] * ca, cy = 32 + e.kr[i] * 0.8f * sa;
    float dx = -sa * e.ks[i], dy = ca * 0.8f * e.ks[i];
    float n = hypotf(dx, dy);
    if (n == 0) n = 1;
    dx /= n; dy /= n;
    const float *c = ec_koi_couleurs[i % 3];
    for (int k = 0; k < 10; k++) {
      const float ox = cx - dx * k * 0.9f + ondule[k] * (-dy), oy = cy - dy * k * 0.9f + ondule[k] * dx;
      const float lum = (1 - k / 12.0f) * (nuit ? 0.55f : 1.0f);
      pointer(oy, ox, c[0] * lum, c[1] * lum, c[2] * lum);
      if (k < 7) {
        const float l = lum * 0.85f;
        pointer(oy + 0.8f * dx, ox - 0.8f * dy, c[0] * l, c[1] * l, c[2] * l);
        pointer(oy - 0.8f * dx, ox + 0.8f * dy, c[0] * l, c[1] * l, c[2] * l);
      }
    }
  }
  const float cos_encoche = cosf(0.35f);
  for (int i = 0; i < 6; i++) {   // les nenuphars, et leur encoche
    const float nx = e.nx[i], ny = e.ny[i], r = e.nr[i], ux = cosf(e.nph[i]), uy = sinf(e.nph[i]);
    for (int y = max(0, (int)ceilf(ny - r)); y <= min(63, (int)floorf(ny + r)); y++)
      for (int x = max(0, (int)ceilf(nx - r)); x <= min(63, (int)floorf(nx + r)); x++) {
        const float dx = x - nx, dy = y - ny, d = sqrtf(dx * dx + dy * dy);
        if (d > r) continue;
        if (!(dx * ux + dy * uy > d * cos_encoche)) {
          if (nuit) peindre(y, x, 10, 34, 20);
          else peindre(y, x, 40, 120, 50);
        }
        if (!nuit && r > 4.5f && d <= 1.3f) peindre(y, x, 255, 170, 210);   // une fleur
      }
  }
  if (nuit)   // des lanternes qui se refletent
    for (int l = 0; l < 2; l++) {
      const float lx = l ? 50.0f : 12.0f, f = 0.8f + 0.2f * sinf(t * 3 + lx);
      for (int y = 0; y <= 32; y++) {
        const float dy = y - 10 - sinf(y * 0.5f + t * 2) * 0.5f;
        for (int x = max(0, (int)lx - 22); x <= min(63, (int)lx + 22); x++) {
          const float dx = x - lx;
          ajouter(y, x, expf(-sqrtf(dx * dx + dy * dy) / 3.0f) * f, 255, 160, 70);
        }
      }
    }
}

// --- la plage -----------------------------------------------------------------

// humeurs : 0 = jour
struct E_plage {
  uint16_t dentelle[128 * 128];   // l'ecume
  uint16_t grain[64 * 64];        // le grain du sable
  float sx[64], ss[64], cs[64];   // sin(x * 0.2), et le sinus et cosinus de celui-ci (la houle)
};
void s_plage(int humeur, bool debut, float t, float ecoule, float dt) {
  E_plage &e = etat_ecran<E_plage>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) {
    brume_n(e.dentelle, 128, 2);
    brume_n(e.grain, 64, 1);
    for (int x = 0; x < 64; x++) { e.sx[x] = sinf(x * 0.2f); e.ss[x] = sinf(e.sx[x]); e.cs[x] = cosf(e.sx[x]); }
  }
  const float s = sinf(fmodf(t * 0.16f, 1.0f) * 3.14159265f);   // une vague toutes les 6 s
  const float avance = s > 0 ? powf(s, 1.6f) : 0.0f;
  float bord[64];
  for (int x = 0; x < 64; x++) bord[x] = 22 + avance * 15 + 2.5f * sinf(x * 0.16f + t * 0.4f) + 1.5f * sinf(x * 0.43f - t * 0.3f);
  const float brille = 1 - avance * 0.5f, largeur = 2 + 5 * (1 - avance);
  const ec_fen fd = ec_fen_placer(t * 2, -t * 3);
  for (int y = 0; y < 64; y++) {
    const float a = y * 0.7f - t * 1.4f, sa = sinf(a), ca = cosf(a);
    for (int x = 0; x < 64; x++) {
      const float b = bord[x], g = 0.92f + 0.08f * e.grain[y * 64 + x] * (1.0f / 65535.0f);
      float r, v, bl, ecume = 0;
      if (y < b) {   // l'eau : turquoise au bord, bleu au large
        const float prof = borne((b - y) / 26, 0, 1), houle = 0.9f + 0.1f * (sa * e.cs[x] + ca * e.ss[x]);
        r = (70 + (16 - 70) * prof) * houle;
        v = (200 + (80 - 200) * prof) * houle;
        bl = (190 + (130 - 190) * prof) * houle;
        const float q = (b - y) / largeur;
        if (q < 4.5f) ecume = borne((ec_fen_val(e.dentelle, 128, fd, x, y) - 0.42f) * 4, 0, 1) * expf(-q * q);
      } else if (y < 40 + 2 * e.sx[x]) {   // le sable mouille, qui brille
        const float k = borne(1 - (y - b) / 12, 0, 1) * brille;
        r = 214 * g * 0.68f + 40 * k;
        v = 190 * g * 0.68f + 60 * k;
        bl = 140 * g * 0.68f + 70 * k;
      } else {
        r = 214 * g; v = 190 * g; bl = 140 * g;
      }
      const float q2 = y - b;
      if (q2 * q2 < 20) ecume += expf(-q2 * q2) * 0.9f;   // la dentelle au bord
      if (ecume > 0) {
        const float k = 1 - ecume * 0.85f, c = ecume * 0.85f;
        r = r * k + 245 * c; v = v * k + 250 * c; bl = bl * k + 250 * c;
      }
      peindre(y, x, r, v, bl);
    }
  }
}

// --- la cascade ---------------------------------------------------------------

// humeurs : 0 = jungle, 1 = lune
struct E_cascade {
  uint16_t eau[128 * 64];        // le bruit des filets
  uint16_t feuilles[64 * 64];    // les feuillages
  float bordk[44][25];           // 0.75 + 0.25 * bord ** 0.4 (lignes 6-49, colonnes 20-44)
  float an_s[14 * 64], an_c[14 * 64], an_e[14 * 64];   // les anneaux du bassin : sin, cos de leur phase, leur fondu
  float gx[30], gy[30], vx[30], vy[30];
  ec_caus ca;
};
void s_cascade(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cascade &e = etat_ecran<E_cascade>(debut);
  (void)ecoule;
  const bool lune = humeur == 1;
  if (debut) {
    for (int i = 0; i < 128 * 64; i++) e.eau[i] = (uint16_t)(aleatoire() >> 16);
    brume_n(e.feuilles, 64, 2);
    for (int i = 0; i < 30; i++) { e.gx[i] = hasard(20, 44); e.gy[i] = hasard(40, 52); e.vx[i] = hasard(-6, 6); e.vy[i] = hasard(-14, -4); }
    for (int y = 6; y < 50; y++) {
      const float larg = 8 + (y - 6) * 0.1f;
      for (int x = 20; x < 45; x++) {
        const float u = borne(1 - fabsf(x - 32.0f) / (larg + 0.5f), 0, 1);
        e.bordk[y - 6][x - 20] = 0.75f + 0.25f * (u > 0 ? powf(u, 0.4f) : 0.0f);
      }
    }
    for (int y = 50; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float dx = x - 32.0f, dy = y - 50.0f, ph = hypotf(dx * 0.5f, dy * 1.6f) * 1.2f;
        const int i = (y - 50) * 64 + x;
        e.an_s[i] = sinf(ph);
        e.an_c[i] = cosf(ph);
        e.an_e[i] = expf(-hypotf(dx, dy * 2) / 14);
      }
  }
  const float er = lune ? 150 : 215, ev = lune ? 180 : 240, eb = lune ? 220 : 245;   // l'eau
  const float rr = lune ? 12 : 46, rv = lune ? 18 : 52, rb = lune ? 26 : 44;        // la roche
  const float h0[3] = {lune ? 20.0f : 150.0f, lune ? 40.0f : 200.0f, lune ? 70.0f : 190.0f};
  const float h1[3] = {lune ? 40.0f : 70.0f, lune ? 70.0f : 130.0f, lune ? 90.0f : 110.0f};
  ec_caus_preparer(e.ca, t * 1.5f, 1.4f, 50);
  float sommet[64], touffe_k[64], brume_x[64], brume_y[64];
  int col[64];
  for (int x = 0; x < 64; x++) {
    sommet[x] = 4 + 3 * sinf(x * 0.2f);
    touffe_k[x] = 0.9f + 0.1f * sinf(t * 0.8f + x * 0.3f);
    const float q = (x - 32) / 15.0f;
    brume_x[x] = expf(-q * q) * (0.75f + 0.25f * sinf(t * 0.9f + x * 0.2f));
    const int c = (int)((x - 32) * 2.2f + 32);
    col[x] = ((c % 64) + 64) % 64;   // des filets : etires a la verticale
  }
  for (int y = 0; y < 64; y++) {
    const float q = (y - 49) / 5.0f;
    brume_y[y] = q * q < 40 ? expf(-q * q) : 0.0f;
  }
  const float s3 = sinf(t * 3), c3 = cosf(t * 3);
  for (int y = 0; y < 64; y++) {
    const float k = y / 64.0f;
    const float ciel[3] = {h0[0] + (h1[0] - h0[0]) * k, h0[1] + (h1[1] - h0[1]) * k, h0[2] + (h1[2] - h0[2]) * k};
    const float larg = 8 + (y - 6) * 0.1f;
    const float gauche = 32 - larg - 1 - 2 * sinf(y * 0.3f), droite = 32 + larg + 1 + 2 * sinf(y * 0.37f + 1);
    const bool chute = y >= 6 && y < 50;
    const int ligne = chute ? (int)ec_pymod(y * 0.35f - t * 14, 128) : 0, ligne2 = (ligne + 40) & 127;
    for (int x = 0; x < 64; x++) {
      float r, v, b;
      if (y >= 50) {   // le bassin, ses caustiques, les ronds de l'eau qui tombe
        const int i = (y - 50) * 64 + x;
        const float a = borne(e.an_s[i] * c3 - e.an_c[i] * s3, 0, 1), a2 = a * a;
        const float k2 = ec_caus_val(e.ca, x, y) * 0.5f + a2 * a2 * e.an_e[i] * 0.5f;
        r = (lune ? 30 : 40) + er * k2;
        v = (lune ? 60 : 120) + ev * k2;
        b = (lune ? 90 : 120) + eb * k2;
      } else {
        r = ciel[0]; v = ciel[1]; b = ciel[2];
        if (chute && fabsf(x - 32.0f) <= larg) {   // l'eau qui tombe en filets
          const float filets = (e.eau[ligne * 64 + col[x]] + e.eau[ligne2 * 64 + ((col[x] + 7) & 63)]) * (0.5f / 65535.0f);
          const float k2 = (0.5f + 0.5f * filets) * e.bordk[y - 6][x - 20];
          r = er * k2; v = ev * k2; b = eb * k2;
        }
        if ((x < gauche || x > droite) && y > sommet[x]) {   // les falaises
          const float f = e.feuilles[y * 64 + x] * (1.0f / 65535.0f);
          if (!lune && f > 0.52f && y < 48) {   // les feuillages, en touffes eclairees par le haut
            const float l = borne((f - 0.52f) * 4, 0, 1), m = touffe_k[x];
            r = (30 + 80 * l) * m; v = (90 + 100 * l) * m; b = (40 + 40 * l) * m;
          } else {
            const float m = 0.8f + 0.3f * f;
            r = rr * m; v = rv * m; b = rb * m;
          }
        }
        if (lune && hypotf(x - 52.0f, y - 8.0f) <= 3) { r = 230; v = 230; b = 210; }
      }
      const float br = brume_y[y] * brume_x[x];   // la brume au pied
      if (br > 0) {
        const float k2 = 1 - br * 0.7f, c = br * 0.85f;
        r = r * k2 + er * c; v = v * k2 + ev * c; b = b * k2 + eb * c;
      }
      peindre(y, x, r, v, b);
    }
  }
  const float pas = fminf(dt, 0.1f);   // des gouttes qui rejaillissent
  for (int i = 0; i < 30; i++) {
    e.vy[i] += 30 * pas;
    e.gx[i] += e.vx[i] * pas;
    e.gy[i] += e.vy[i] * pas;
    if (e.gy[i] > 52) { e.gx[i] = hasard(24, 40); e.gy[i] = 50; e.vx[i] = hasard(-8, 8); e.vy[i] = hasard(-16, -6); }
    pointer(e.gy[i], e.gx[i], er, ev, eb);
  }
}
