// lot_villes_paysages.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10) : les villes (la
// ville, l'autoroute, la grille neon, le train de nuit) et les paysages (les collines en couches, la tour
// du nord, le feu de camp, le ble, les dunes, les cerisiers, les champignons, les cristaux, le volcan, le
// phare, les etourneaux, le village sous la neige). Chaque moteur suit son jumeau numpy (_scene_<moteur>)
// pas a pas ; ce qui ne bouge pas (les halos fixes, les champs) est calcule au debut, ce qui ne depend que
// de x ou de y est sorti des boucles.
#pragma once

// --- les outils du lot (prefixe vp_) --------------------------------------------

// le % de Python : du signe du diviseur
inline float vp_mod(float a, float m) { return a - m * floorf(a / m); }
inline float vp_sat(float v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

// _poser : un point qui ecrase ce qui est dessous ; comme astype(int) (vers zero : -0.5 tombe en 0)
inline void vp_poser(float yf, float xf, float r, float v, float b) {
  const int y = (int)yf, x = (int)xf;
  if (y < 0 || y >= H || x < 0 || x >= W) return;
  peindre(y, x, r, v, b);
}

// _degrade, les couleurs en tableaux
inline void vp_degrade(const float *h, const float *b, float y0 = 0, float y1 = 64) {
  degrade2(h[0], h[1], h[2], b[0], b[1], b[2], y0, y1);
}

// _peindre_sous : sous la crete (une hauteur par colonne), jusqu'a `haut` (exclu)
void vp_sous(const float *crete, float r, float v, float b, int haut = 64) {
  for (int x = 0; x < W; x++)
    for (int y = max(0, (int)ceilf(crete[x])); y < haut; y++) peindre(y, x, r, v, b);
}

// un disque plein (un astre) : hypot(X - cx, Y - cy) <= r
void vp_disque(float cx, float cy, float r, float cr, float cv, float cb) {
  const int y0 = max(0, (int)floorf(cy - r)), y1 = min(H - 1, (int)ceilf(cy + r));
  const int x0 = max(0, (int)floorf(cx - r)), x1 = min(W - 1, (int)ceilf(cx + r));
  for (int y = y0; y <= y1; y++)
    for (int x = x0; x <= x1; x++)
      if ((x - cx) * (x - cx) + (y - cy) * (y - cy) <= r * r) peindre(y, x, cr, cv, cb);
}

// l'aureole d'un astre : += clip(1 - d / rayon, 0, 1) ** 2 * couleur, au-dessus de la ligne `fin`
void vp_aureole(float cx, float cy, float rayon, float cr, float cv, float cb, int fin = 64) {
  const int y0 = max(0, (int)floorf(cy - rayon)), y1 = min(fin - 1, (int)ceilf(cy + rayon));
  const int x0 = max(0, (int)floorf(cx - rayon)), x1 = min(W - 1, (int)ceilf(cx + rayon));
  const float inv = 1.0f / rayon, r2 = rayon * rayon;
  for (int y = y0; y <= y1; y++)
    for (int x = x0; x <= x1; x++) {
      const float d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy);
      if (d2 >= r2) continue;
      const float q = 1 - sqrtf(d2) * inv;
      ajouter(y, x, q * q, cr, cv, cb);
    }
}

// _halo, borne la ou la lueur tombe sous un quart de niveau (dans la fenetre de _halo) : on ne calcule
// que ce qui se voit
void vp_halo(float x, float y, float rayon, float r, float v, float b, float force, float aplati = 1.0f) {
  const float m = fmaxf(r, fmaxf(v, b)) * force * 4.0f;
  if (m <= 1.0f) return;
  const float inv = 1.0f / fmaxf(rayon, 1e-3f), portee = rayon * logf(m), p2 = portee * portee;
  const int e = (int)(rayon * 6) + 1;
  const int ex = min(e, (int)portee + 1), ey = min(e, (int)(portee / aplati) + 1);
  const int x0 = max(0, (int)x - ex), x1 = min(W, (int)x + ex + 1);
  const int y0 = max(0, (int)y - ey), y1 = min(H, (int)y + ey + 1);
  for (int yy = y0; yy < y1; yy++) {
    const float dy = (yy - y) * aplati, dy2 = dy * dy;
    if (dy2 > p2) continue;
    for (int xx = x0; xx < x1; xx++) {
      const float dx = xx - x, d2 = dx * dx + dy2;
      if (d2 > p2) continue;
      ajouter(yy, xx, expf(-sqrtf(d2) * inv) * force, r, v, b);
    }
  }
}

// une ligne de _fenetre : le champ (taille x taille) vu depuis (ox, oy), ligne y, dans sortie[64]
void vp_fenetre_ligne(const uint16_t *c, int taille, float ox, float oy, int y, float *sortie) {
  const int x0 = (int)floorf(ox), y0 = (int)floorf(oy), m = taille - 1;
  const float fx = ox - x0, fy = oy - y0, k = 1.0f / 65535;
  const uint16_t *a = c + ((y + y0) & m) * taille, *b = c + ((y + y0 + 1) & m) * taille;
  for (int x = 0; x < W; x++) {
    const int i = (x + x0) & m, j = (x + x0 + 1) & m;
    const float h = a[i] + (a[j] - a[i]) * fx, l = b[i] + (b[j] - b[i]) * fx;
    sortie[x] = (h + (l - h) * fy) * k;
  }
}

// =====================================================================================================
// LES VILLES
// =====================================================================================================

// --- la ville : ses fenetres qui s'allument et s'eteignent, la rue, ses phares et ses feux ---
// humeurs : 0 = nuit, 1 = neon, 2 = aube, 3 = brume
const float VP_VILLE[4][4][3] = {   // VILLE_HUMEURS : (ciel haut, ciel bas, immeubles, fenetres)
  {{4, 8, 24}, {24, 34, 64}, {10, 12, 22}, {255, 200, 110}},
  {{16, 4, 34}, {70, 14, 80}, {12, 6, 24}, {120, 220, 255}},
  {{90, 110, 170}, {250, 170, 140}, {40, 40, 64}, {255, 220, 160}},
  {{60, 30, 20}, {230, 120, 50}, {24, 14, 14}, {255, 170, 80}},
};
const float VP_ENSEIGNES[4][3][3] = {   // les enseignes (le neon, la brume)
  {{0, 0, 0}, {0, 0, 0}, {0, 0, 0}},
  {{255, 40, 140}, {0, 220, 255}, {250, 240, 90}},
  {{0, 0, 0}, {0, 0, 0}, {0, 0, 0}},
  {{255, 90, 40}, {255, 200, 120}, {0, 0, 0}},
};
const int VP_NB_ENSEIGNES[4] = {0, 3, 0, 2};
struct E_ville {
  int n;                                   // les immeubles (_immeubles) : x, largeur, haut, graine
  int x0[16], larg[16], haut[16];
  float g[16];
  int8_t enseigne[16];                     // son enseigne (-1 : aucune), et le halo de chacune
  uint8_t lueur[5][64 * 64];               // exp(-d / 5), x255 : elles ne bougent pas
  float vx[7], vs[7], vv[7];               // les voitures : x, sens, vitesse
  Pluie pluie;
};
void s_ville(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ville &e = etat_ecran<E_ville>(debut);
  (void)ecoule;
  const float(*c)[3] = VP_VILLE[humeur];
  const int ne = VP_NB_ENSEIGNES[humeur], sol = 52;
  if (debut) {
    e.n = 0;
    for (int x0 = -2; x0 < 64 && e.n < 16;) {
      const int larg = 5 + (int)(aleatoire() % 6);
      e.x0[e.n] = x0;
      e.larg[e.n] = larg;
      e.haut[e.n] = 14 + (int)(aleatoire() % (sol - 8 - 14));
      e.g[e.n] = hasard(0, 100);
      e.n++;
      x0 += larg + (int)(aleatoire() % 2);
    }
    int k = 0;
    for (int i = 0; i < e.n; i++) {
      e.enseigne[i] = -1;
      const int xa = max(0, e.x0[i]), xb = min(64, e.x0[i] + e.larg[i]);
      if (!ne || e.larg[i] < 7 || i % 3 || xa >= xb || k >= 5) continue;
      e.enseigne[i] = (int8_t)k;
      const float cx = (xa + xb) * 0.5f, cy = e.haut[i] + 4.0f;
      for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
          e.lueur[k][y * 64 + x] = (uint8_t)(expf(-sqrtf((x - cx) * (x - cx) + (y - cy) * (y - cy)) / 5.0f) * 255 + 0.5f);
      k++;
    }
    for (int i = 0; i < 7; i++) {
      e.vx[i] = hasard(0, 64);
      e.vs[i] = (aleatoire() & 1) ? 1.0f : -1.0f;
      e.vv[i] = hasard(10, 20);
    }
    if (humeur == 1) semer_pluie(e.pluie, 40);
  }
  vp_degrade(c[0], c[1], 0, sol);
  if (humeur == 3)   // une brume ambree, epaisse, et deux projecteurs qui balaient
    for (int k = 0; k < 2; k++) {
      const float x0 = k ? 46.0f : 14.0f, pente = tanf(0.4f * sinf(t * 0.3f + k * 2));
      for (int y = 0; y < sol; y++) {
        const float d = (float)(sol - y), xc = x0 + d * pente, l = 1.5f + d * 0.06f;
        const int xa = max(0, (int)floorf(xc - 3.5f * l)), xb = min(W - 1, (int)ceilf(xc + 3.5f * l));
        for (int x = xa; x <= xb; x++) {
          const float u = (x - xc) / l;
          ajouter(y, x, expf(-u * u) * 0.5f, 120, 70, 30);
        }
      }
    }
  for (int i = 0; i < e.n; i++) {
    const int xa = max(0, e.x0[i]), xb = min(64, e.x0[i] + e.larg[i]), h = e.haut[i];
    if (xa >= xb) continue;
    const float loin = (i % 2) ? 0.75f : 1.0f, g = e.g[i];
    for (int y = h; y < sol; y++)
      for (int x = xa; x < xb; x++) peindre(y, x, c[2][0] * loin, c[2][1] * loin, c[2][2] * loin);
    int rang = 0;
    for (int y = h + 2; y < sol - 1; y += 2, rang++) {   // chaque fenetre, allumee ou non, change lentement
      const float k = (0.6f + 0.4f * sinf(g + rang)) * loin;
      for (int x = xa + 1; x < xb - 1; x += 2)
        if (sinf(y * 12.9898f + x * 78.233f + g + floorf(t / 6 + (y * x) % 7) * 1.7f) > 0.25f)
          peindre(y, x, c[3][0] * k, c[3][1] * k, c[3][2] * k);
    }
    if (e.enseigne[i] >= 0) {   // une enseigne qui clignote, et sa lueur
      const float *ec = VP_ENSEIGNES[humeur][i % ne];
      const float allumee = sinf(t * (2 + i) + g) > -0.6f ? 1.0f : 0.4f;
      for (int y = h + 4; y < h + 6; y++)
        for (int x = xa + 1; x < xb - 1; x++) peindre(y, x, ec[0] * allumee, ec[1] * allumee, ec[2] * allumee);
      const uint8_t *l = e.lueur[(int)e.enseigne[i]];
      const float f = allumee * 0.35f / 255;
      for (int p = 0; p < 64 * 64; p++)
        if (l[p]) ajouter(p >> 6, p & 63, l[p] * f, ec[0], ec[1], ec[2]);
    }
  }
  const bool aube = humeur == 2;
  for (int y = sol; y < H; y++)
    for (int x = 0; x < W; x++) peindre(y, x, aube ? 50 : 14, aube ? 48 : 14, aube ? 60 : 20);
  for (int x = 0; x < W; x++)   // les pointilles de la route
    if (x % 6 < 3) peindre(sol + 5, x, 120, 120, 110);
  for (int i = 0; i < 7; i++) {
    e.vx[i] += e.vs[i] * e.vv[i] * dt;
    if (e.vx[i] > 70 || e.vx[i] < -6) {
      e.vx[i] = e.vs[i] > 0 ? -5.0f : 69.0f;
      e.vv[i] = hasard(10, 20);
    }
    const float x = e.vx[i], s = e.vs[i];
    const int y = s > 0 ? sol + 3 : sol + 8;
    pointer(y, x, 30, 30, 40);
    pointer(y, x - s * 3, 30, 30, 40);
    pointer(y, x + s, 255, 250, 220);   // les phares devant, les feux derriere
    pointer(y, x + s * 2, 140, 140, 120);
    pointer(y, x - s * 4, 200, 30, 30);
  }
  if (humeur == 1) {
    pluie(e.pluie, dt, 110, 90, 160, 0.15f);
    for (int k = 0; k < 6; k++)   // la chaussee mouillee reflete les enseignes
      for (int x = 0; x < W; x++)
        for (int q = 0; q < 3; q++)
          scene[sol + 1 + k][x][q] = fmaxf(scene[sol + 1 + k][x][q], scene[sol - 1 - k][x][q] * 0.35f);
  }
}

// --- l'autoroute la nuit, vers l'horizon : des phares qui viennent, des feux qui s'en vont ---
// humeurs : 0 = nuit, 1 = neon
struct E_autoroute {
  uint8_t hauts[64];                       // la ville au loin : des immeubles de 4 colonnes
  uint8_t vitres[26 * 64];                 // et ses fenetres allumees
  float cp[10], cs[10], cv[10];            // les voitures : ou (0 au loin, 1 tout pres), sens, vitesse
};
void s_autoroute(int humeur, bool debut, float t, float ecoule, float dt) {
  E_autoroute &e = etat_ecran<E_autoroute>(debut);
  (void)ecoule;
  const bool neon = humeur == 1;
  const int hz = 26;
  if (debut) {
    for (int b = 0; b < 16; b++) {
      const uint8_t h = (uint8_t)(2 + aleatoire() % 8);
      for (int k = 0; k < 4; k++) e.hauts[b * 4 + k] = h;
    }
    for (int y = 0; y < hz; y++)
      for (int x = 0; x < W; x++)
        e.vitres[y * 64 + x] = hasard(0, 1) > 0.7f && y % 2 == 0 && x % 2 == 1 && y > hz - e.hauts[x] + 1;
    for (int i = 0; i < 10; i++) {
      e.cp[i] = hasard(0, 1);
      e.cs[i] = (aleatoire() & 1) ? 1.0f : -1.0f;
      e.cv[i] = hasard(0.15f, 0.3f);
    }
  }
  degrade2(4, 4, 16, neon ? 40 : 20, neon ? 20 : 30, neon ? 70 : 60, 0, hz);
  for (int y = 0; y <= hz; y++) {   // la lueur de la ville sur l'horizon
    const float u = (y - hz) / 5.0f, k = expf(-u * u);
    for (int x = 0; x < W; x++) ajouter(y, x, k, neon ? 200 : 160, neon ? 50 : 110, neon ? 160 : 60);
  }
  for (int x = 0; x < W; x++)
    for (int y = hz - e.hauts[x]; y < hz; y++) peindre(y, x, 8, neon ? 6 : 10, neon ? 18 : 20);
  for (int y = 0; y < hz; y++)
    for (int x = 0; x < W; x++)
      if (e.vitres[y * 64 + x]) peindre(y, x, 150, neon ? 60 : 120, neon ? 170 : 70);
  const float br = neon ? 200 : 120, bv = neon ? 60 : 120, bb = neon ? 200 : 100;
  for (int y = hz + 1; y < H; y++) {   // le sol, la route, ses bandes, ses pointilles qui defilent
    const float prof = (y - hz) / (float)(64 - hz), l = 3 + prof * 40, trait = 0.6f + prof;
    const bool tiret = sinf(3 / prof + t * 9) > 0.3f;
    const float lt = 0.3f + prof * 0.8f;
    for (int x = 0; x < W; x++) {
      const float dx = x - 32.0f;
      float r = 6, v = 6, b = 12;
      if (fabsf(dx) <= l) { r = 16; v = 16; b = 24; }
      if (fabsf(dx + l) < trait || fabsf(dx - l) < trait) { r = br; v = bv; b = bb; }
      if (tiret && fabsf(dx) < lt) { r = 220; v = 220; b = 180; }
      peindre(y, x, r, v, b);
    }
  }
  const float lv = neon ? 120 : 190, lb = neon ? 220 : 110;
  for (int k = 0; k < 6; k++) {   // les reverberes qui viennent vers nous
    const float zl = 1 + vp_mod(k * 1.5f - t * 1.4f, 9.0f), q = 1 / zl, y0 = hz + q * (64 - hz);
    for (int bord = -1; bord <= 1; bord += 2) {
      const float x0 = 32 + bord * (4 + q * 40);
      if (fabsf(x0 - 32) > 40) continue;   // deja passe a cote de nous
      const float h = 2 + q * 30, l = 0.5f + q * 0.6f;
      for (int y = max(0, (int)ceilf(y0 - h)); y <= min(H - 1, (int)floorf(y0)); y++)
        for (int x = max(0, (int)ceilf(x0 - l)); x <= min(W - 1, (int)floorf(x0 + l)); x++)
          if (fabsf(x - x0) < l) peindre(y, x, neon ? 70 : 60, neon ? 50 : 60, neon ? 90 : 70);
      const float force = fminf(1.0f, 0.45f + q * 2);
      vp_halo(x0 - bord * (1 + q * 6), y0 - h, 0.5f + q * 2.5f, 255, lv, lb, 1.6f * force);
      vp_halo(x0 - bord * q * 8, y0 + 0.5f, 0.6f + q * 4, 255, lv, lb, 0.5f * force, 4);   // sa flaque
    }
  }
  for (int i = 0; i < 10; i++) {   // les phares blancs qui viennent, les feux rouges qui s'en vont
    e.cp[i] += e.cv[i] * dt * e.cs[i];
    if (e.cp[i] > 1 || e.cp[i] < 0) e.cp[i] = e.cs[i] > 0 ? 0.0f : 1.0f;
    const float q = e.cp[i] * e.cp[i];   // la perspective : lents au loin, vite tout pres
    const float y = hz + 1 + q * (63 - hz), x = 32 - e.cs[i] * (1.5f + q * 18), ec = 0.5f + q * 3;
    const bool blanc = e.cs[i] > 0;
    for (int cote = -1; cote <= 1; cote += 2)
      vp_halo(x + cote * ec / 2, y, 0.35f + q * 1.2f, blanc ? 255 : 230, blanc ? 250 : 40, blanc ? 230 : 40, 0.9f, 1.5f);
  }
}

// --- la grille neon : un soleil a rayures, des montagnes en fil de fer, une grille qui defile ---
// humeurs : 0 = magenta, 1 = cyan
struct E_synthwave { char rien; };
void s_synthwave(int humeur, bool debut, float t, float ecoule, float dt) {
  E_synthwave &e = etat_ecran<E_synthwave>(debut);
  (void)e; (void)ecoule; (void)dt;
  const bool cyan = humeur == 1;
  const int hz = 38;
  degrade2(20, 4, 40, cyan ? 20 : 140, cyan ? 60 : 30, cyan ? 120 : 110, 0, hz);
  const float hs[3] = {cyan ? 160.0f : 255.0f, cyan ? 255.0f : 230.0f, cyan ? 250.0f : 90.0f};
  const float bs[3] = {cyan ? 40.0f : 255.0f, cyan ? 120.0f : 40.0f, cyan ? 255.0f : 140.0f};
  for (int y = 0; y < hz; y++) {   // le soleil, ses rayures qui descendent, sa lueur
    const float dy = y - 28.0f, k = vp_sat((y - 14) / 22.0f);
    const bool raye = y > 26 && vp_mod(y - t * 2, 4) < 1 + (y - 26) * 0.12f;
    const float sr = hs[0] * (1 - k) + bs[0] * k, sv = hs[1] * (1 - k) + bs[1] * k, sb = hs[2] * (1 - k) + bs[2] * k;
    for (int x = 0; x < W; x++) {
      const float d2 = (x - 32.0f) * (x - 32.0f) + dy * dy;
      if (d2 >= 26 * 26) continue;
      const float d = sqrtf(d2), g = 1 - d / 26;
      if (d <= 14 && !raye) peindre(y, x, sr, sv, sb);
      ajouter(y, x, g * g * 0.25f, bs[0], bs[1], bs[2]);
    }
  }
  for (int x = 0; x < W; x++) {   // les montagnes, et leur arete
    const float m = hz - borne(10 - fabsf(x - 10.0f) * 0.9f, 0, 10) - borne(13 - fabsf(x - 54.0f), 0, 13);
    for (int y = max(0, (int)ceilf(m)); y < hz; y++) {
      if (y < m + 1.2f) peindre(y, x, cyan ? 60 : 255, cyan ? 220 : 60, cyan ? 255 : 200);
      else peindre(y, x, cyan ? 4 : 14, cyan ? 14 : 4, 30);
    }
  }
  for (int y = hz; y < H; y++)
    for (int x = 0; x < W; x++) peindre(y, x, cyan ? 2 : 10, cyan ? 8 : 2, 22);
  const float cr = cyan ? 60 : 255, cv = cyan ? 230 : 50, cb = cyan ? 255 : 200, h = (float)(64 - hz);
  for (int n = 0; n < 14; n++) {   // les lignes qui viennent vers soi, en perspective
    const float z = 1 + n - vp_mod(t * 1.5f, 1), y = hz + h / z;
    if (y >= 64) continue;
    const float k = fminf(1.0f, 1.4f / powf(z, 0.6f));
    for (int x = 0; x < W; x++) pointer(y, x, cr * k, cv * k, cb * k);
  }
  for (int k = -12; k <= 12; k++)   // celles qui filent vers l'horizon
    for (int y = hz; y < H; y++) {
      const float q = (y - hz) / h, f = 0.35f + 0.65f * q;
      pointer(y, 32 + k * 9 * q, cr * f, cv * f, cb * f);
    }
  for (int x = 0; x < W; x++) peindre(hz, x, cr * 0.9f, cv * 0.9f, cb * 0.9f);
}

// --- le train de nuit sur son viaduc, ses fenetres allumees ; la lune, les collines ---
// humeurs : 0 = nuit, 1 = neige
struct E_train { float fx[60], fy[60], fv[60]; };
void s_train(int humeur, bool debut, float t, float ecoule, float dt) {
  E_train &e = etat_ecran<E_train>(debut);
  (void)ecoule;
  const bool neige = humeur == 1;
  const int tablier = 36;
  if (debut) {
    if (!neige) semer_ciel(40, 30);
    else
      for (int i = 0; i < 60; i++) { e.fx[i] = hasard(0, 64); e.fy[i] = hasard(0, 64); e.fv[i] = hasard(5, 12); }
  }
  if (neige) degrade2(40, 50, 70, 110, 120, 140);
  else {
    degrade2(6, 10, 26, 30, 40, 70);
    etoiles_du_ciel(t);
    vp_disque(50, 9, 3.5f, 230, 230, 210);
  }
  for (int x = 0; x < W; x++) {   // les collines
    const float c = 44 + 4 * sinf(x * 0.07f + 1) + 2 * sinf(x * 0.21f);
    for (int y = (int)ceilf(c); y < H; y++) peindre(y, x, neige ? 170 : 14, neige ? 178 : 18, neige ? 196 : 30);
  }
  for (int y = tablier; y < tablier + 2; y++)
    for (int x = 0; x < W; x++) peindre(y, x, neige ? 60 : 20, neige ? 64 : 20, neige ? 80 : 30);
  for (int x0 = 2; x0 < 64; x0 += 12)   // les arches du viaduc
    for (int y = tablier + 2; y < H; y++)
      for (int x = x0; x <= min(W - 1, x0 + 12); x++) {
        const float dx = x - x0 - 6.0f, dy = y - tablier - 9.0f;
        if (dx * dx + dy * dy > 5.5f * 5.5f) peindre(y, x, neige ? 70 : 16, neige ? 74 : 16, neige ? 92 : 26);
      }
  if (!neige)   // les lampes du viaduc, entre deux trains
    for (int x0 = 2; x0 < 64; x0 += 12) vp_halo(x0, tablier - 3, 1.6f, 255, 190, 110, 0.9f);
  const float tete = -10 + vp_mod(t, 26) / 26 * 160;   // un train toutes les 26 s
  float lueur[64];
  for (int y = 0; y < H; y++) {
    const float u = (y - tablier + 3) / 6.0f;
    lueur[y] = expf(-u * u) * 0.12f;
  }
  for (int k = 0; k < 5; k++) {   // cinq voitures
    const float x0 = tete - k * 15;
    for (int x = max(0, (int)floorf(x0) - 13); x <= min(W - 1, (int)floorf(x0)); x++) {
      const bool vitre = vp_mod(x0 - x, 4) >= 2;
      for (int y = tablier - 6; y < tablier; y++) {
        if (y == tablier - 6) peindre(y, x, neige ? 110 : 80, neige ? 50 : 86, neige ? 56 : 104);   // le toit
        else if ((y == tablier - 4 || y == tablier - 3) && vitre) peindre(y, x, 255, 210, 120);
        else peindre(y, x, neige ? 60 : 44, neige ? 30 : 48, neige ? 34 : 66);
      }
      for (int y = 0; y < H; y++) ajouter(y, x, lueur[y], 255, 200, 120);
    }
  }
  if (tete > -2 && tete < 66) pointer(tablier - 2, tete + 1, 255, 255, 210);
  if (neige)
    for (int i = 0; i < 60; i++) {
      e.fy[i] = vp_mod(e.fy[i] + e.fv[i] * dt, 64);
      pointer(e.fy[i], vp_mod(e.fx[i] + sinf(t + e.fy[i] * 0.2f), 64), 240, 244, 255);
    }
}

// =====================================================================================================
// LES PAYSAGES
// =====================================================================================================

// --- des montagnes et des forets en couches, la brume entre elles, des oiseaux ---
// humeurs : 0 = automne, 1 = lavande, 2 = nuit, 3 = nordique
const float VP_COUCHES[4][4][3] = {   // COUCHES_HUMEURS : (ciel haut, couche la plus lointaine, la plus proche, astre)
  {{255, 210, 140}, {245, 130, 80}, {40, 14, 20}, {255, 240, 200}},
  {{200, 170, 235}, {230, 150, 170}, {30, 18, 50}, {255, 235, 240}},
  {{10, 30, 50}, {40, 90, 110}, {4, 10, 18}, {230, 240, 230}},
  {{150, 165, 180}, {200, 210, 220}, {30, 40, 50}, {0, 0, 0}},   // le nord : pas d'astre
};
struct E_couches { float ph1[5], ph2[5], ox[4], oy[4], ov[4], op[4]; };
void s_couches(int humeur, bool debut, float t, float ecoule, float dt) {
  E_couches &e = etat_ecran<E_couches>(debut);
  (void)ecoule;
  const float *haut = VP_COUCHES[humeur][0], *loin = VP_COUCHES[humeur][1], *pres = VP_COUCHES[humeur][2];
  const float *astre = VP_COUCHES[humeur][3];
  if (debut) {
    for (int i = 0; i < 5; i++) { e.ph1[i] = hasard(0, 6); e.ph2[i] = hasard(0, 6); }
    for (int i = 0; i < 4; i++) { e.ox[i] = hasard(0, 64); e.oy[i] = hasard(6, 22); e.ov[i] = hasard(3, 6); e.op[i] = hasard(0, 6); }
  }
  vp_degrade(haut, loin, 0, 44);
  if (humeur != 3) {
    vp_aureole(20, 16, 20, astre[0] * 0.25f, astre[1] * 0.25f, astre[2] * 0.25f);
    vp_disque(20, 16, 4, astre[0], astre[1], astre[2]);
  }
  for (int i = 0; i < 5; i++) {
    const float k = (i + 1) / 5.0f, derive = t * (0.3f + i * 0.5f), base = 24.0f + i * 8;   // le plus proche bouge le plus
    const float cr = loin[0] * (1 - k) + pres[0] * k, cv = loin[1] * (1 - k) + pres[1] * k, cb = loin[2] * (1 - k) + pres[2] * k;
    const bool enneigee = humeur == 3 && i == 1;
    for (int x = 0; x < W; x++) {
      const float xd = x + derive;
      float crete;
      if (i < 2)   // des montagnes au loin
        crete = base - 8 * fabsf(sinf(xd * 0.05f + e.ph1[i])) - 3 * sinf(xd * 0.17f + e.ph2[i]);
      else {       // puis des forets : des pointes de sapins
        const float dent = fabsf(vp_mod(xd * 0.45f + e.ph1[i], 2) - 1);
        crete = base - 3 * sinf(xd * 0.09f + e.ph2[i]) - (1 - dent) * (3 + i);
      }
      const bool cime = enneigee && crete < base - 6;   // des sommets enneiges, seulement les plus hauts
      for (int y = max(0, (int)ceilf(crete)); y < H; y++) {
        if (cime && y < crete + 3) peindre(y, x, 235, 240, 245);
        else peindre(y, x, cr, cv, cb);
      }
    }
    float col[64];
    for (int x = 0; x < W; x++) col[x] = (0.25f + 0.15f * sinf(x * 0.1f + t * 0.3f + i)) * 0.5f;
    const int yb = (int)base + 2;
    for (int y = max(0, yb - 9); y <= min(H - 1, yb + 9); y++) {   // la brume au pied de la couche
      const float u = (y - base - 2) / 3.0f, by = expf(-u * u);
      for (int x = 0; x < W; x++) {
        const float b = by * col[x];
        float *p = scene[y][x];
        p[0] += (loin[0] - p[0]) * b;
        p[1] += (loin[1] - p[1]) * b;
        p[2] += (loin[2] - p[2]) * b;
      }
    }
  }
  for (int i = 0; i < 4; i++) {   // les oiseaux
    e.ox[i] = vp_mod(e.ox[i] + e.ov[i] * dt, 74);
    const int aile = (int)(t * 4 + e.op[i]) % 2;
    const float r = pres[0] * 0.6f, v = pres[1] * 0.6f, b = pres[2] * 0.6f;
    vp_poser(e.oy[i] - aile, e.ox[i] - 1, r, v, b);
    vp_poser(e.oy[i], e.ox[i], r, v, b);
    vp_poser(e.oy[i] - aile, e.ox[i] + 1, r, v, b);
  }
}

// --- le grand nord : des pics enneiges dans la brume, des sapins, une tour de pierre et sa torche ---
// humeurs : 0 = aube, 1 = tempete, 2 = crepuscule
const float VP_NORD[3][2][3] = {
  {{140, 155, 175}, {220, 200, 190}}, {{60, 66, 76}, {110, 116, 126}}, {{40, 50, 80}, {170, 110, 90}}};
struct E_nordique {
  int n;                                   // les flocons
  float fx[90], fy[90], fv[90];
  float sx[9], sh[9];                      // les sapins
  uint8_t lueur[64 * 64];                  // la lueur de la torche : exp(-d / 4), x255
};
void s_nordique(int humeur, bool debut, float t, float ecoule, float dt) {
  E_nordique &e = etat_ecran<E_nordique>(debut);
  (void)ecoule;
  const float *ch = VP_NORD[humeur][0], *cb = VP_NORD[humeur][1];
  if (debut) {
    for (int i = 0; i < 9; i++) { e.sx[i] = hasard(0, 64); e.sh[i] = hasard(8, 16); }
    e.n = humeur == 1 ? 90 : 40;
    for (int i = 0; i < e.n; i++) { e.fx[i] = hasard(0, 64); e.fy[i] = hasard(0, 64); e.fv[i] = hasard(6, 14); }
    for (int y = 0; y < H; y++)
      for (int x = 0; x < W; x++)
        e.lueur[y * 64 + x] = (uint8_t)(expf(-sqrtf((x - 49.5f) * (x - 49.5f) + (y - 41.0f) * (y - 41.0f)) / 4) * 255 + 0.5f);
  }
  vp_degrade(ch, cb, 0, 40);
  for (int x = 0; x < W; x++) {
    const float l = 30 - 14 * fabsf(sinf(x * 0.06f + 0.7f)) - 5 * fabsf(sinf(x * 0.17f + 2));
    const float n = l + 4 + 2 * sinf(x * 0.5f);   // les neiges eternelles
    for (int y = max(0, (int)ceilf(l)); y < H; y++) {
      if (y < n) peindre(y, x, 225, 230, 238);
      else peindre(y, x, cb[0] * 0.6f, cb[1] * 0.6f, cb[2] * 0.6f);
    }
    const float p = 44 - 10 * fabsf(sinf(x * 0.09f + 3)) - 3 * sinf(x * 0.31f);
    for (int y = max(0, (int)ceilf(p)); y < H; y++) {
      if (y < p + 2) peindre(y, x, 190, 198, 210);
      else peindre(y, x, 40, 46, 56);
    }
  }
  float bx[64];
  for (int x = 0; x < W; x++) bx[x] = 0.55f + 0.2f * sinf(x * 0.08f + t * 0.25f);
  for (int y = 26; y <= 54; y++) {   // la brume dans la vallee
    const float u = (y - 40) / 5.0f, by = expf(-u * u) * 0.6f;
    for (int x = 0; x < W; x++) {
      const float b = by * bx[x];
      float *q = scene[y][x];
      q[0] += (cb[0] - q[0]) * b;
      q[1] += (cb[1] - q[1]) * b;
      q[2] += (cb[2] - q[2]) * b;
    }
  }
  const bool soir = humeur == 2;
  for (int x = 0; x < W; x++) {
    const float s = 54 + sinf(x * 0.2f);
    for (int y = (int)ceilf(s); y < H; y++) peindre(y, x, soir ? 120 : 200, soir ? 110 : 206, soir ? 130 : 216);
  }
  for (int i = 0; i < 9; i++) {   // les sapins, la neige a leur pointe
    const float sommet = 56 - e.sh[i];
    for (int y = max(0, (int)ceilf(sommet)); y <= 58; y++) {
      const float l = (y - sommet) * 0.35f + 0.5f;
      const bool blanc = y <= sommet + 3;
      for (int x = max(0, (int)ceilf(e.sx[i] - l)); x <= min(W - 1, (int)floorf(e.sx[i] + l)); x++) {
        if (blanc) peindre(y, x, 180, 190, 200);
        else peindre(y, x, 16, 26, 26);
      }
    }
  }
  for (int y = 36; y < 52; y++)   // la tour de pierre
    for (int x = 47; x < 52; x++) peindre(y, x, 52, 54, 62);
  for (int y = 34; y < 36; y++)
    for (int x = 46; x < 53; x++) peindre(y, x, 60, 62, 70);
  for (int x = 46; x < 53; x += 2) peindre(33, x, 60, 62, 70);
  const float feu = 0.75f + 0.25f * sinf(t * 9) * sinf(t * 5.3f);
  peindre(40, 49, 255 * feu, 180 * feu, 80 * feu);
  peindre(41, 49, 255 * feu, 180 * feu, 80 * feu);
  const float f = feu * 0.6f / 255;
  for (int p = 0; p < 64 * 64; p++)
    if (e.lueur[p]) ajouter(p >> 6, p & 63, e.lueur[p] * f, 255, 140, 50);
  const float vent = humeur == 1 ? 0.6f : 0.1f;
  for (int i = 0; i < e.n; i++) {
    e.fy[i] = vp_mod(e.fy[i] + e.fv[i] * dt, 64);
    e.fx[i] = vp_mod(e.fx[i] + e.fv[i] * vent * dt, 64);
    pointer(e.fy[i], e.fx[i], 235, 240, 248);
  }
}

// --- un feu de camp sous les etoiles : les flammes, les etincelles qui montent, la lueur sur le sol ---
// humeurs : 0 = foret, 1 = desert, 2 = neige
struct E_feu_camp {
  float ex[20], ey[20], ev[20], ep[20];    // les etincelles
  uint16_t lueur[64 * 64];                 // la lueur du feu : exp(-hypot(0.7 dx, 1.3 dy) / 10), x65535
};
void s_feu_camp(int humeur, bool debut, float t, float ecoule, float dt) {
  E_feu_camp &e = etat_ecran<E_feu_camp>(debut);
  (void)ecoule;
  if (debut) {
    semer_ciel(60, 40);
    for (int i = 0; i < 20; i++) { e.ex[i] = hasard(28, 36); e.ey[i] = hasard(20, 54); e.ev[i] = hasard(6, 14); e.ep[i] = hasard(0, 6); }
    for (int y = 0; y < H; y++)
      for (int x = 0; x < W; x++) {
        const float a = (x - 32) * 0.7f, b = (y - 53) * 1.3f;
        e.lueur[y * 64 + x] = (uint16_t)(expf(-sqrtf(a * a + b * b) / 10) * 65535 + 0.5f);
      }
  }
  degrade2(2, 4, 14, 22, 30, 60);
  etoiles_du_ciel(t);
  for (int x = 0; x < W; x++) {
    float s;
    if (humeur == 1) s = 46 + 3 * sinf(x * 0.08f + 1) + 2 * sinf(x * 0.2f);
    else if (humeur == 2) s = 48 + sinf(x * 0.1f);
    else s = 50 + sinf(x * 0.15f);
    for (int y = (int)ceilf(s); y < H; y++) {
      if (humeur == 1) peindre(y, x, 40, 28, 30);
      else if (humeur == 2) peindre(y, x, 60, 66, 84);
      else peindre(y, x, 12, 14, 10);
    }
  }
  if (humeur == 0) {   // les sapins autour
    static const float sapins[5][2] = {{6, 30}, {14, 22}, {54, 28}, {61, 20}, {47, 16}};
    for (int i = 0; i < 5; i++) {
      const float sx = sapins[i][0], sommet = 50 - sapins[i][1];
      for (int y = (int)sommet; y <= 51; y++) {
        const float l = (y - sommet) * 0.32f + 0.5f;
        for (int x = max(0, (int)ceilf(sx - l)); x <= min(W - 1, (int)floorf(sx + l)); x++) peindre(y, x, 4, 7, 8);
      }
    }
  }
  const float f = (0.75f + 0.15f * sinf(t * 7) + 0.1f * sinf(t * 13)) / 65535;
  for (int p = 0; p < 64 * 64; p++) ajouter(p >> 6, p & 63, e.lueur[p] * f, 255, 120, 40);
  for (int y = 54; y < 56; y++)   // les buches
    for (int x = 27; x < 37; x++) peindre(y, x, 50, 30, 20);
  for (int x = 29; x < 35; x++) peindre(53, x, 70, 40, 24);
  static const float fdx[3] = {0, -2, 2}, fw[3] = {3.5f, 2.5f, 2.5f};
  float hk[3];
  for (int k = 0; k < 3; k++) hk[k] = 9 + 3 * sinf(t * 6 + k * 2) + 2 * sinf(t * 11 + k);
  for (int y = 40; y <= 54; y++) {   // les trois flammes
    float acc[64];
    for (int x = 0; x < W; x++) acc[x] = 0;
    bool rien = true;
    for (int k = 0; k < 3; k++) {
      const float yy = (54 - y) / hk[k];
      if (yy >= 1) continue;
      const float l = fw[k] * (1 - yy) * (1 + 0.2f * sinf(y * 0.9f - t * 12 + k));
      const float c = 32 + fdx[k] + sinf(y * 0.5f - t * 8 + k) * yy * 1.5f, a = 1 - yy * 0.6f;
      for (int x = max(0, (int)floorf(c - l)); x <= min(W - 1, (int)ceilf(c + l)); x++)
        if (fabsf(x - c) < l) { acc[x] += a; rien = false; }
    }
    if (rien) continue;
    for (int x = 0; x < W; x++) {
      if (acc[x] <= 0) continue;
      const float q = fminf(acc[x], 1.0f);
      peindre(y, x, 255, 90 + 140 * q, 20 + 100 * q);
    }
  }
  for (int i = 0; i < 20; i++) {   // les etincelles qui montent
    e.ey[i] -= e.ev[i] * dt;
    if (e.ey[i] < 14) { e.ey[i] = 52; e.ex[i] = hasard(29, 35); }
    const float vie = vp_sat((e.ey[i] - 14) / 38);
    pointer(e.ey[i], e.ex[i] + sinf(t * 2 + e.ep[i]) * (52 - e.ey[i]) * 0.08f, 255 * vie, 170 * vie, 60 * vie);
  }
}

// --- un champ de ble sous le vent : des vagues sur les epis ; le soir dore, ou la nuit et ses lucioles ---
// humeurs : 0 = or, 1 = nuit
struct E_ble {
  uint8_t epis[64 * 128];                  // des traits verticaux : des tiges (x255)
  float bosquets[64];                      // la haie au bout du champ
  float tx[24], th[24];                    // quelques grands epis devant
  float lx[14], ly[14], lp[14];            // les lucioles
};
void s_ble(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ble &e = etat_ecran<E_ble>(debut);
  (void)ecoule; (void)dt;
  const bool nuit = humeur == 1;
  if (debut) {
    float g[64];
    for (int x = 0; x < 128; x++) {   // (g + roll(g, 1, 0) + roll(g, 2, 0)) / 3
      for (int y = 0; y < 64; y++) g[y] = hasard(0, 1);
      for (int y = 0; y < 64; y++) e.epis[y * 128 + x] = (uint8_t)((g[y] + g[(y + 63) & 63] + g[(y + 62) & 63]) / 3 * 255 + 0.5f);
    }
    const float ph = hasard(0, 6);
    for (int x = 0; x < W; x++) e.bosquets[x] = 29 - 2.5f * borne(sinf(x * 0.21f + ph) + sinf(x * 0.53f), 0, 2);
    for (int i = 0; i < 24; i++) { e.tx[i] = hasard(0, 64); e.th[i] = hasard(9, 17); }
    if (nuit) {
      semer_ciel(40, 26);
      for (int i = 0; i < 14; i++) { e.lx[i] = hasard(0, 64); e.ly[i] = hasard(30, 56); e.lp[i] = hasard(0, 6); }
    }
  }
  const float cb[3] = {nuit ? 30.0f : 255.0f, nuit ? 40.0f : 150.0f, nuit ? 80.0f : 80.0f};
  degrade2(nuit ? 6 : 250, nuit ? 10 : 190, nuit ? 30 : 110, cb[0], cb[1], cb[2], 0, 30);
  if (!nuit) {
    vp_aureole(44, 24, 24, 60, 40, 10);
    vp_disque(44, 24, 5, 255, 230, 170);
  } else {
    etoiles_du_ciel(t);
    vp_disque(44, 10, 3, 230, 230, 200);
  }
  vp_sous(e.bosquets, nuit ? 10 : 70, nuit ? 12 : 40, nuit ? 22 : 30);
  const float clair[3] = {nuit ? 95.0f : 255.0f, nuit ? 100.0f : 205.0f, nuit ? 120.0f : 100.0f};
  const float ombre[3] = {nuit ? 18.0f : 150.0f, nuit ? 20.0f : 80.0f, nuit ? 30.0f : 35.0f};
  float vague63[64];
  for (int y = 30; y < H; y++) {   // le champ : le vent qui passe, des tiges plus grosses devant, la brume au loin
    const float prof = (y - 30) / 34.0f, rel = 7 / (prof + 0.2f) - t * 1.4f, ech = 0.4f + 0.8f * (1 - prof);
    const float q = 1 - prof, voile = q * q * q * 0.6f;
    const uint8_t *ligne = e.epis + y * 128;
    for (int x = 0; x < W; x++) {
      const float vague = 0.5f + 0.5f * sinf(x * 0.1f + rel);
      if (y == 63) vague63[x] = vague;
      const int col = ((int)(x * ech + vague * 3 * prof)) & 127;
      const float a = vp_sat(0.25f + 0.45f * vague + 0.35f / 255 * ligne[col]);
      const float r = ombre[0] + (clair[0] - ombre[0]) * a, v = ombre[1] + (clair[1] - ombre[1]) * a;
      const float b = ombre[2] + (clair[2] - ombre[2]) * a;
      peindre(y, x, r + (cb[0] - r) * voile, v + (cb[1] - v) * voile, b + (cb[2] - b) * voile);
    }
  }
  for (int i = 0; i < 24; i++) {   // quelques grands epis devant, penches par la vague
    const float sh = e.th[i], pench = (vague63[(int)e.tx[i] % 64] - 0.5f) * 6;
    for (int j = 0; j < 18 && j < sh; j++) {
      const float y = 63.0f - j, x = e.tx[i] + pench * (j / sh) * (j / sh);
      if (j >= sh - 4) {
        pointer(y, x, clair[0] * 1.05f, clair[1] * 1.05f, clair[2] * 1.05f);
        pointer(y, x + 1, clair[0] * 0.8f, clair[1] * 0.8f, clair[2] * 0.8f);
      } else {
        pointer(y, x, ombre[0] * 0.9f, ombre[1] * 0.9f, ombre[2] * 0.9f);
      }
    }
  }
  if (nuit)
    for (int i = 0; i < 14; i++) {
      const float s = fmaxf(0.0f, sinf(t * 1.3f + e.lp[i] * 2)), l = s * s;
      pointer(e.ly[i] + sinf(t * 0.5f + e.lp[i]) * 3, e.lx[i] + cosf(t * 0.4f + e.lp[i]) * 4, 200 * l, 255 * l, 100 * l);
    }
}

// --- des dunes, leurs cretes vives et leurs flancs a l'ombre ; le sable que le vent arrache ---
// humeurs : 0 = midi, 1 = nuit, 2 = mars
const float VP_DUNES[3][4][3] = {   // DUNES_HUMEURS : (ciel haut, ciel bas, sable eclaire, sable a l'ombre)
  {{80, 150, 220}, {230, 200, 160}, {240, 190, 110}, {180, 110, 60}},
  {{4, 8, 24}, {30, 40, 70}, {90, 100, 130}, {30, 34, 56}},
  {{120, 70, 50}, {220, 140, 90}, {200, 90, 50}, {110, 40, 30}},
};
const float VP_DUNES_RANGS[3][4] = {{34, 6, 0.035f, 0.1f}, {43, 8, 0.03f, 0.55f}, {54, 9, 0.025f, 0.8f}};
struct E_dunes { float gx[40], gv[40], gp[40]; };
void s_dunes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_dunes &e = etat_ecran<E_dunes>(debut);
  (void)ecoule; (void)dt;
  const float *haut = VP_DUNES[humeur][0], *bas = VP_DUNES[humeur][1], *clair = VP_DUNES[humeur][2];
  const float *ombre = VP_DUNES[humeur][3];
  if (debut) {
    if (humeur == 1) semer_ciel(70, 34);
    for (int i = 0; i < 40; i++) { e.gx[i] = hasard(0, 64); e.gv[i] = hasard(0, 1); e.gp[i] = hasard(0, 6); }
  }
  vp_degrade(haut, bas, 0, 36);
  if (humeur == 1) {
    etoiles_du_ciel(t);
    vp_disque(14, 10, 3, 235, 235, 215);
  } else if (humeur == 2) {   // deux lunes
    vp_disque(48, 12, 2.5f, 220, 200, 180);
    vp_disque(20, 8, 1.5f, 220, 200, 180);
  } else {
    vp_disque(14, 10, 4, 255, 250, 230);
  }
  // par rang et par colonne : la crete, la lumiere sur le flanc, sa couleur, la phase des rides
  float crete[3][64], lum[3][64], flanc[3][64][3], ps[3][64], pc[3][64];
  for (int i = 0; i < 3; i++) {
    const float base = VP_DUNES_RANGS[i][0], amp = VP_DUNES_RANGS[i][1], f = VP_DUNES_RANGS[i][2], ph = VP_DUNES_RANGS[i][3];
    for (int x = 0; x < W; x++) {
      const float u = vp_mod((x + t * 0.25f * (i + 1)) * f + ph, 1);
      const float profil = u < 0.72f ? u / 0.72f : (1 - u) / 0.28f;   // montee douce au vent, chute raide dessous
      crete[i][x] = base - amp * powf(profil, 1.3f);
    }
    for (int x = 0; x < W; x++) {
      const float *c = crete[i];
      const float pente = x == 0 ? c[1] - c[0] : x == 63 ? c[63] - c[62] : (c[x + 1] - c[x - 1]) * 0.5f;   // np.gradient
      const float l = vp_sat(0.5f - pente * 0.9f);
      lum[i][x] = l;
      for (int q = 0; q < 3; q++) flanc[i][x][q] = ombre[q] + (clair[q] - ombre[q]) * l;
      const float b = x * 0.25f - c[x] * 1.7f;   // sin(sous * 1.7 + x * 0.25) = sin(1.7 y + b)
      ps[i][x] = sinf(b);
      pc[i][x] = cosf(b);
    }
  }
  float mi[3];
  for (int q = 0; q < 3; q++) mi[q] = (clair[q] + ombre[q]) * 0.5f;
  for (int y = 25; y < H; y++) {
    const float sy = sinf(y * 1.7f), cy = cosf(y * 1.7f);
    for (int x = 0; x < W; x++) {
      int i0 = 0;   // un rang qui couvre tout le pixel cache ceux d'avant
      for (int i = 2; i > 0; i--)
        if (y - crete[i][x] >= 0.5f) { i0 = i; break; }
      float *p = scene[y][x];
      for (int i = i0; i < 3; i++) {
        const float sous = y - crete[i][x];
        if (sous <= -0.5f) continue;
        const float couvre = fminf(1.0f, sous + 0.5f), w = vp_sat(sous / 12) * 0.55f, k = 0.7f + 0.15f * i;
        const float rides = (1 + 0.07f * (sy * pc[i][x] + cy * ps[i][x]) * lum[i][x]) * k;   // les rides du vent
        for (int q = 0; q < 3; q++) {
          const float c = (flanc[i][x][q] + (mi[q] - flanc[i][x][q]) * w) * rides;
          p[q] += (c - p[q]) * couvre;
        }
      }
    }
  }
  for (int i = 0; i < 40; i++) {   // le vent sur les cretes
    const float gx = vp_mod(e.gx[i] + t * 14 * (0.6f + e.gv[i]), 70) - 3;
    const float gy = 28 + e.gv[i] * 30 + sinf(t * 2 + e.gp[i]) * 1.5f, k = (0.4f + 0.4f * e.gv[i]) * 1.1f;
    pointer(gy, gx, clair[0] * k, clair[1] * k, clair[2] * k);
  }
}

// --- un jardin japonais : un arbre en fleurs (ou en feuilles rouges), un torii, des petales qui volent ---
// humeurs : 0 = printemps, 1 = nuit, 2 = automne
const float VP_CERISIERS[3][4][3] = {   // (ciel haut, ciel bas, fleurs, sol)
  {{170, 210, 240}, {250, 225, 230}, {255, 170, 200}, {120, 160, 110}},
  {{8, 12, 34}, {40, 40, 80}, {230, 140, 190}, {20, 26, 30}},
  {{240, 180, 130}, {250, 220, 180}, {220, 70, 40}, {140, 100, 60}},
};
const float VP_COURONNE[6][3] = {{16, 18, 9}, {7, 24, 6}, {26, 22, 7}, {12, 9, 6}, {23, 12, 5.5f}, {4, 15, 4.5f}};
const float VP_BRANCHES[3][4] = {{15, 34, 26, 22}, {15, 36, 6, 25}, {14, 30, 13, 14}};
struct E_cerisiers {
  uint16_t feuillage[64 * 64];             // _brume(rng, 2, 64)
  uint8_t tombes[9 * 64];                  // les petales tombes (lignes 55 a 63)
  float px[30], py[30], pv[30], pp[30];    // les petales qui volent
  float lueur[64 * 64];                    // la lueur des deux lanternes (la nuit)
};
void s_cerisiers(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cerisiers &e = etat_ecran<E_cerisiers>(debut);
  (void)ecoule;
  const bool nuit = humeur == 1;
  const float(*c)[3] = VP_CERISIERS[humeur];
  const float *fleur = c[2];
  if (debut) {
    if (nuit) semer_ciel(40, 24);
    brume_n(e.feuillage, 64, 2);
    for (int i = 0; i < 30; i++) { e.px[i] = hasard(0, 64); e.py[i] = hasard(0, 64); e.pv[i] = hasard(4, 9); e.pp[i] = hasard(0, 6); }
    for (int p = 0; p < 9 * 64; p++) e.tombes[p] = hasard(0, 1) > 0.93f;
    if (nuit)
      for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
          const float a = sqrtf((x - 29.5f) * (x - 29.5f) + (y - 45.0f) * (y - 45.0f));
          const float b = sqrtf((x - 57.5f) * (x - 57.5f) + (y - 45.0f) * (y - 45.0f));
          e.lueur[y * 64 + x] = (expf(-a / 4) + expf(-b / 4)) * 0.6f;
        }
  }
  vp_degrade(c[0], c[1]);
  if (nuit) {
    etoiles_du_ciel(t);
    vp_disque(50, 9, 3.5f, 240, 240, 220);
  }
  for (int y = 54; y < H; y++)
    for (int x = 0; x < W; x++) peindre(y, x, c[3][0], c[3][1], c[3][2]);
  const float rr = nuit ? 90 : 190, rv = nuit ? 20 : 40, rb = nuit ? 20 : 30;   // le torii
  for (int y = 30; y < 54; y++)
    for (int x = 0; x < 2; x++) { peindre(y, 36 + x, rr, rv, rb); peindre(y, 50 + x, rr, rv, rb); }
  for (int y = 28; y < 30; y++)
    for (int x = 33; x < 55; x++) peindre(y, x, 40, 20, 20);
  for (int x = 35; x < 53; x++) peindre(33, x, rr, rv, rb);
  const float br = nuit ? 30 : 50, bv = nuit ? 20 : 30, bb = nuit ? 26 : 30;   // le bois
  for (int y = 24; y < 55; y++) {   // le tronc
    const float cx = 14 + (54 - y) * 0.12f, l = 1.2f + (y - 24) * 0.05f;
    for (int x = max(0, (int)ceilf(cx - l)); x <= (int)floorf(cx + l); x++) peindre(y, x, br, bv, bb);
  }
  for (int b = 0; b < 3; b++) {   // les branches
    const float *s = VP_BRANCHES[b];
    for (int j = 0; j < 16; j++) {
      const float k = j / 15.0f;
      const int y = (int)(s[1] + (s[3] - s[1]) * k), x = (int)(s[0] + (s[2] - s[0]) * k);
      peindre(y, x, br, bv, bb);
      peindre(y, x + 1, br, bv, bb);
    }
  }
  const float kt = nuit ? 0.5f : 0.8f;   // les petales tombes
  for (int p = 0; p < 9 * 64; p++)
    if (e.tombes[p]) peindre(55 + (p >> 6), p & 63, fleur[0] * kt, fleur[1] * kt, fleur[2] * kt);
  const float balance = sinf(t * 0.6f) * 0.8f;   // la couronne se balance un peu
  for (int y = 0; y < 35; y++) {
    const float bal = balance * vp_sat((34 - y) / 30.0f);
    for (int x = 0; x < 38; x++) {
      const float f = e.feuillage[y * 64 + x] * (1.0f / 65535), ech = 0.85f + 0.35f * f;
      float couronne = 0;
      for (int k = 0; k < 6; k++) {
        const float cx = VP_COURONNE[k][0], cy = VP_COURONNE[k][1], r = VP_COURONNE[k][2];
        const float dx = x - cx - bal, dy = (y - cy) * 1.1f, rr2 = r * ech;
        if (dx * dx + dy * dy >= rr2 * rr2) continue;
        couronne = fmaxf(couronne, borne(0.75f - (x - cx) / r * 0.25f - (y - cy) / r * 0.45f, 0.3f, 1.2f));   // eclairee d'en haut a gauche
      }
      if (couronne <= 0) continue;
      const float k = couronne * (0.8f + 0.35f * f) * (nuit ? 0.8f : 1.0f);
      peindre(y, x, fleur[0] * k, fleur[1] * k, fleur[2] * k);
    }
  }
  if (nuit) {   // des lanternes
    for (int lx = 30; lx <= 58; lx += 28) {
      const float k = 0.85f + 0.15f * sinf(t * 3 + lx);
      for (int y = 44; y < 47; y++)
        for (int x = lx - 1; x < lx + 1; x++) peindre(y, x, 255 * k, 170 * k, 80 * k);
    }
    for (int p = 0; p < 64 * 64; p++) ajouter(p >> 6, p & 63, e.lueur[p], 255, 140, 60);
  }
  const float vent = (6 + 3 * sinf(t * 0.5f)) * dt;
  for (int i = 0; i < 30; i++) {   // les petales qui volent
    e.py[i] += e.pv[i] * dt;
    e.px[i] += vent;
    if (e.py[i] > 64 || e.px[i] > 66) { e.py[i] = hasard(8, 30); e.px[i] = hasard(0, 30); }
    pointer(e.py[i] + sinf(t * 2 + e.pp[i]), e.px[i], fleur[0] * 1.05f, fleur[1] * 1.05f, fleur[2] * 1.05f);
  }
}

// --- une foret la nuit, ses champignons qui luisent et respirent ; des spores qui montent ---
// humeurs : 0 = bleu, 1 = rose
const float VP_CHAMPIGNONS[2][3][3] = {   // CHAMPIGNONS_HUMEURS : (chapeaux, spores, mousse)
  {{60, 190, 255}, {130, 255, 230}, {20, 70, 80}}, {{255, 80, 190}, {255, 190, 240}, {70, 30, 70}}};
const float VP_PIEDS[8][5] = {   // (x, pied, rayon du chapeau, hauteur, phase)
  {9, 56, 5, 7, 0.0f}, {17, 57, 3, 4, 1.3f}, {29, 58, 7, 9, 2.1f}, {38, 56, 3, 5, 0.7f},
  {46, 57, 6, 6, 3.4f}, {56, 58, 4, 8, 4.4f}, {23, 60, 2, 3, 5.0f}, {61, 61, 2, 3, 2.7f}};
struct E_champignons {
  uint8_t halo[8][64 * 64];                // la lueur de chaque champignon (x255) : elle respire avec lui
  float sol[64];
  float sx[50], sy[50], sv[50], sp[50];    // les spores
};
void s_champignons(int humeur, bool debut, float t, float ecoule, float dt) {
  E_champignons &e = etat_ecran<E_champignons>(debut);
  (void)ecoule;
  const float *chapeau = VP_CHAMPIGNONS[humeur][0], *spore = VP_CHAMPIGNONS[humeur][1], *mousse = VP_CHAMPIGNONS[humeur][2];
  if (debut) {
    for (int x = 0; x < W; x++) e.sol[x] = 54 + 1.5f * sinf(x * 0.2f) + sinf(x * 0.53f);
    for (int k = 0; k < 8; k++) {
      const float cx = VP_PIEDS[k][0], r = VP_PIEDS[k][2], haut = VP_PIEDS[k][1] - VP_PIEDS[k][3];
      for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++) {
          const float a = x - cx, b = (y - haut + r * 0.2f) * 1.3f;
          e.halo[k][y * 64 + x] = (uint8_t)(expf(-sqrtf(a * a + b * b) / (r * 0.9f + 1.5f)) * 255 + 0.5f);
        }
    }
    for (int i = 0; i < 50; i++) { e.sx[i] = hasard(0, 64); e.sy[i] = hasard(0, 64); e.sv[i] = hasard(1.5f, 4); e.sp[i] = hasard(0, 6); }
  }
  degrade2(2, 4, 10, 8, 14, 22);
  static const float troncs[6][2] = {{4, 4}, {15, 2}, {24, 5}, {41, 3}, {52, 6}, {60, 2}};   // les troncs, au loin
  for (int i = 0; i < 6; i++)
    for (int y = 0; y < 56; y++)
      for (int x = max(0, (int)ceilf(troncs[i][0] - troncs[i][1] / 2)); x <= min(W - 1, (int)floorf(troncs[i][0] + troncs[i][1] / 2)); x++)
        peindre(y, x, 12, 18, 26);
  const float m = 0.7f + 0.3f * sinf(t * 0.7f);
  for (int x = 0; x < W; x++)
    for (int y = (int)ceilf(e.sol[x]); y < H; y++) {
      if (y < e.sol[x] + 2) peindre(y, x, mousse[0] * m, mousse[1] * m, mousse[2] * m);
      else peindre(y, x, 6, 9, 12);
    }
  float souffle[8];
  for (int k = 0; k < 8; k++) {
    const int cx = (int)VP_PIEDS[k][0], cy = (int)VP_PIEDS[k][1], haut = cy - (int)VP_PIEDS[k][3];
    const float r = VP_PIEDS[k][2], s = 0.65f + 0.35f * sinf(t * 0.8f + VP_PIEDS[k][4]);   // chacun respire a son rythme
    souffle[k] = s;
    const float pied = fmaxf(0.5f, r * 0.18f);
    for (int y = haut; y <= cy; y++)
      for (int x = max(0, (int)ceilf(cx - pied)); x <= min(W - 1, (int)floorf(cx + pied)); x++) peindre(y, x, 150, 160, 170);
    const float ry = r * 0.6f;
    for (int y = max(0, (int)ceilf(haut - ry)); y <= haut; y++)
      for (int x = max(0, (int)ceilf(cx - r)); x <= min(W - 1, (int)floorf(cx + r)); x++) {
        const float a = (x - cx) / r, b = (y - haut) / ry;
        if (a * a + b * b > 1) continue;
        if (((x - cx + y) % 3 + 3) % 3 == 0 && y - haut < -1)   // des pois plus clairs sur le chapeau
          peindre(y, x, fminf(255, chapeau[0] * s * 1.4f + 40), fminf(255, chapeau[1] * s * 1.4f + 40), fminf(255, chapeau[2] * s * 1.4f + 40));
        else
          peindre(y, x, chapeau[0] * s, chapeau[1] * s, chapeau[2] * s);
      }
  }
  for (int p = 0; p < 64 * 64; p++) {   // leur lueur a tous
    float h = 0;
    for (int k = 0; k < 8; k++) h += e.halo[k][p] * souffle[k];
    h = fminf(h * (1.0f / 255), 1.2f) * 0.45f;
    ajouter(p >> 6, p & 63, h, chapeau[0], chapeau[1], chapeau[2]);
  }
  for (int i = 0; i < 50; i++) {
    e.sy[i] -= e.sv[i] * dt;
    e.sx[i] += sinf(t * 0.6f + e.sp[i]) * 0.3f * dt * 10;
    if (e.sy[i] < 0) e.sy[i] = hasard(52, 62);
    e.sx[i] = vp_mod(e.sx[i], 64);
    const float l = 0.4f + 0.6f * vp_sat(sinf(t * 1.7f + e.sp[i] * 3));
    pointer(e.sy[i], e.sx[i], spore[0] * l, spore[1] * l, spore[2] * l);
  }
}

// --- une grotte de cristaux : des prismes, un reflet qui court sur leurs facettes, des gouttes ---
// humeurs : 0 = amethyste, 1 = emeraude
const float VP_CRISTAUX[2][3][3] = {   // CRISTAUX_HUMEURS : (cristal clair, cristal sombre, lueur de la grotte)
  {{210, 140, 255}, {90, 40, 150}, {40, 10, 60}}, {{120, 255, 180}, {20, 110, 80}, {8, 40, 30}}};
const float VP_PRISMES[10][6] = {   // (x, base, hauteur, largeur, pente, depuis le sol)
  {10, 58, 30, 3.2f, -0.25f, 1}, {18, 59, 18, 2.2f, 0.3f, 1}, {30, 60, 38, 4.2f, 0.08f, 1}, {37, 59, 20, 2.4f, 0.45f, 1},
  {48, 58, 28, 3.6f, -0.15f, 1}, {57, 59, 16, 2.6f, 0.35f, 1}, {5, 58, 12, 1.8f, 0.5f, 1}, {24, 8, 13, 2.2f, 0.15f, 0},
  {44, 9, 17, 2.6f, -0.2f, 0}, {56, 8, 9, 1.6f, 0.1f, 0}};
struct E_cristaux {
  uint8_t fond[64 * 64][3];                // la grotte, sa roche
  uint8_t facette[64 * 64];                // 0 : roche ; 1 : face a l'ombre ; 2 : face eclairee
  float halo[64 * 64];                     // le halo des cristaux sur la roche
  uint16_t roche[64 * 64];
  float gx[4], gy[4];                      // les gouttes
};
void s_cristaux(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cristaux &e = etat_ecran<E_cristaux>(debut);
  (void)ecoule;
  const float *clair = VP_CRISTAUX[humeur][0], *sombre = VP_CRISTAUX[humeur][1], *lueur = VP_CRISTAUX[humeur][2];
  if (debut) {
    brume_n(e.roche, 64, 3);
    for (int x = 0; x < W; x++) {
      const float plafond = 7 + 4 * sinf(x * 0.2f) + 2 * sinf(x * 0.5f), sol = 55 + 2 * sinf(x * 0.15f + 1) + sinf(x * 0.6f);
      for (int y = 0; y < H; y++) {
        uint8_t *f = e.fond[y * 64 + x];
        if (y >= sol) { f[0] = 10; f[1] = 8; f[2] = 12; continue; }
        if (y <= plafond) { f[0] = 8; f[1] = 6; f[2] = 10; continue; }
        const float k = y / 64.0f, g = (0.6f + 0.5f * e.roche[y * 64 + x] * (1.0f / 65535)) * (0.4f + 0.6f * k);
        for (int q = 0; q < 3; q++) f[q] = (uint8_t)(lueur[q] * g + 0.5f);
      }
    }
    for (int i = 0; i < 10; i++) {
      const float *p = VP_PRISMES[i];
      const float sens = p[5] > 0 ? -1.0f : 1.0f;   // vers le haut depuis le sol, vers le bas depuis le plafond
      for (int y = 0; y < H; y++) {
        const float le_long = (y - p[1]) * sens;   // 0 a la base, la hauteur a la pointe
        if (le_long < 0 || le_long > p[2]) continue;
        const float axe = p[0] + le_long * p[4], demi = p[3] * vp_sat((p[2] - le_long) / (p[3] * 1.6f));
        for (int x = 0; x < W; x++)
          if (fabsf(x - axe) <= demi) e.facette[y * 64 + x] = x < axe ? 1 : 2;
      }
    }
    float *a = &scene[0][0][0], *b = a + 4096;   // le brouillon : la scene, qu'on repeint de toute facon
    for (int p = 0; p < 4096; p++) a[p] = e.facette[p] == 2 ? 1.0f : e.facette[p] ? 0.55f : 0.0f;
    for (int k = 0; k < 5; k++) {
      for (int y = 0; y < 64; y++)
        for (int x = 0; x < 64; x++)
          b[y * 64 + x] = (a[y * 64 + x] + a[((y + 63) & 63) * 64 + x] + a[((y + 1) & 63) * 64 + x] + a[y * 64 + ((x + 63) & 63)] +
                           a[y * 64 + ((x + 1) & 63)]) / 5.0f;
      float *c = a; a = b; b = c;
    }
    for (int p = 0; p < 4096; p++) e.halo[p] = a[p];
    for (int i = 0; i < 4; i++) { e.gx[i] = hasard(4, 60); e.gy[i] = hasard(0, 64); }
  }
  const float pouls = 0.8f + 0.2f * sinf(t * 0.9f), kh = 0.55f * pouls, kc = 0.75f + 0.25f * pouls;
  float face[2][3];
  for (int q = 0; q < 3; q++) {
    face[0][q] = (sombre[q] * 0.45f + clair[q] * 0.55f) * kc;
    face[1][q] = clair[q] * kc;
  }
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      const int p = y * 64 + x;
      if (e.facette[p]) {   // le reflet qui court sur les facettes
        const float *c = face[e.facette[p] - 1];
        const float reflet = vp_sat(1 - fabsf(vp_mod(x + y * 0.6f - t * 18, 110) - 20) / 5) * 120;
        peindre(y, x, c[0] + reflet, c[1] + reflet, c[2] + reflet);
      } else {
        const float h = e.halo[p] * kh;
        const uint8_t *f = e.fond[p];
        peindre(y, x, f[0] + h * clair[0], f[1] + h * clair[1], f[2] + h * clair[2]);
      }
    }
  for (int i = 0; i < 4; i++) {
    e.gy[i] += 22 * dt;
    if (e.gy[i] > 58) { e.gy[i] = hasard(8, 14); e.gx[i] = hasard(4, 60); }
    pointer(e.gy[i], e.gx[i], clair[0] * 0.8f, clair[1] * 0.8f, clair[2] * 0.8f);
  }
}

// --- un volcan qui crache, ses coulees ; devant, une riviere de lave dont la croute se fend et derive ---
// humeurs : 0 = rouge, 1 = bleu
const float VP_LAVE[2][5][3] = {   // LAVE_HUMEURS : (ciel haut, ciel bas, lave chaude, lave tiede, croute)
  {{8, 2, 4}, {70, 16, 8}, {255, 220, 90}, {230, 70, 10}, {34, 14, 10}},
  {{4, 2, 14}, {30, 14, 60}, {190, 255, 255}, {40, 120, 255}, {14, 12, 30}},
};
struct E_lave {
  uint16_t champ[128 * 128], fumee[128 * 128];   // _brume(rng, 4), _brume(rng, 9)
  uint8_t lueur[64 * 64];                         // la lueur du cratere : exp(-d / 7), x255
  float bx[26], by[26], vx[26], vy[26];           // les projections
};
void s_lave(int humeur, bool debut, float t, float ecoule, float dt) {
  E_lave &e = etat_ecran<E_lave>(debut);
  (void)ecoule;
  const float *haut = VP_LAVE[humeur][0], *bas = VP_LAVE[humeur][1], *chaud = VP_LAVE[humeur][2];
  const float *tiede = VP_LAVE[humeur][3], *croute = VP_LAVE[humeur][4];
  if (debut) {
    brume_n(e.champ, 128, 4);
    brume_n(e.fumee, 128, 9);
    for (int i = 0; i < 26; i++) { e.bx[i] = 0; e.by[i] = -1; e.vx[i] = 0; e.vy[i] = 0; }
    for (int y = 0; y < H; y++)
      for (int x = 0; x < W; x++)
        e.lueur[y * 64 + x] = (uint8_t)(expf(-sqrtf((x - 40.0f) * (x - 40.0f) + (y - 21.0f) * (y - 21.0f)) / 7) * 255 + 0.5f);
  }
  vp_degrade(haut, bas, 0, 44);
  float l[64];
  for (int y = 5; y < 46; y++) {   // la fumee monte, eclairee par en dessous (le cone couvre tout dessous)
    const float k = fminf(1.0f, (y - 4) / 40.0f) * 2.2f * 0.5f;
    vp_fenetre_ligne(e.fumee, 128, t * 1.5f, t * 4, y, l);
    for (int x = 0; x < W; x++)
      if (l[x] > 0.45f) ajouter(y, x, (l[x] - 0.45f) * k, tiede[0], tiede[1], tiede[2]);
  }
  for (int x = 0; x < W; x++) {   // le volcan et son cratere
    const float d = fabsf(x - 40.0f), cone = d < 3 ? 22 + d * 0.3f : 46 - borne(26 - d * 1.05f, 0, 24);
    for (int y = (int)ceilf(cone); y < H; y++) peindre(y, x, croute[0] * 0.6f, croute[1] * 0.6f, croute[2] * 0.6f);
  }
  for (int j = 0; j < 2; j++) {   // deux coulees sur ses flancs
    const float c0 = j ? 42.5f : 37.5f, ph = j ? 2.0f : 0.0f, sens = j ? 1.0f : -1.0f;
    for (int y = 23; y < 47; y++) {
      const float x = c0 + sens * (y - 23) * 0.55f + sinf(y * 0.4f + ph) * 1.2f, vif = 0.6f + 0.4f * sinf(y * 0.5f - t * 3 + ph);
      pointer(y, x, tiede[0] * vif, tiede[1] * vif, tiede[2] * vif);
    }
  }
  for (int y = 21; y <= 23; y++)
    for (int x = 38; x <= 42; x++) peindre(y, x, chaud[0], chaud[1], chaud[2]);
  for (int i = 0; i < 26; i++) {   // les projections du cratere
    e.vy[i] += 18 * dt;
    e.bx[i] += e.vx[i] * dt;
    e.by[i] += e.vy[i] * dt;
    if (e.by[i] > 46 || e.by[i] < -0.5f) {
      e.bx[i] = 40 + hasard(-1.5f, 1.5f);
      e.by[i] = 21;
      e.vx[i] = hasard(-9, 9);
      e.vy[i] = hasard(-24, -10);
    }
    pointer(e.by[i], e.bx[i], chaud[0], chaud[1], chaud[2]);
    pointer(e.by[i] + 1, e.bx[i] - e.vx[i] * 0.05f, tiede[0] * 0.7f, tiede[1] * 0.7f, tiede[2] * 0.7f);
  }
  const float kl = (0.7f + 0.3f * sinf(t * 5)) * 0.6f / 255;
  for (int p = 0; p < 64 * 64; p++)
    if (e.lueur[p]) ajouter(p >> 6, p & 63, e.lueur[p] * kl, tiede[0], tiede[1], tiede[2]);
  float riv[64], onde[64];   // la riviere de lave, devant
  for (int x = 0; x < W; x++) {
    riv[x] = 47 + sinf(x * 0.12f + 1) * 1.5f;
    onde[x] = 0.85f + 0.15f * sinf(t * 2 + x * 0.1f);
  }
  for (int y = 45; y < H; y++) {
    vp_fenetre_ligne(e.champ, 128, t * 7, 0, y, l);
    for (int x = 0; x < W; x++) {
      if (y < riv[x]) continue;
      const float c = l[x], a = vp_sat((0.56f - c) / 0.12f);   // 1 : croute ; 0 : lave a nu
      const float fente = vp_sat(1 - fabsf(c - 0.56f) / 0.025f), g = (1 - a) * vp_sat(0.5f - c) * 1.2f;
      const bool berge = y < riv[x] + 1.2f;
      for (int q = 0; q < 3; q++) {
        float v = (tiede[q] * (1 - a) + croute[q] * a + fente * chaud[q] * 0.8f + g * chaud[q]) * onde[x];
        if (berge) v = v * 0.5f + chaud[q] * 0.5f;
        scene[y][x][q] = v;
      }
    }
  }
}

// --- un phare sur son rocher : le faisceau qui tourne, la mer qui bat ; la tempete, ou une nuit calme ---
// humeurs : 0 = tempete, 1 = calme
struct E_phare {
  uint16_t nuees[128 * 128];               // _brume(rng, 7)
  float ex[30], ey[30], vx[30], vy[30];    // les embruns
  Pluie pluie;
};
void s_phare(int humeur, bool debut, float t, float ecoule, float dt) {
  E_phare &e = etat_ecran<E_phare>(debut);
  (void)ecoule;
  const bool tempete = humeur == 0;
  if (debut) {
    if (tempete) {
      brume_n(e.nuees, 128, 7);
      semer_pluie(e.pluie, 60);
    } else {
      semer_ciel(50, 40);
    }
    for (int i = 0; i < 30; i++) { e.ex[i] = 0; e.ey[i] = 70; e.vx[i] = 0; e.vy[i] = 0; }
  }
  if (tempete) {
    degrade2(14, 18, 26, 44, 52, 64, 0, 44);
    float l[64];
    for (int y = 0; y < 50; y++) {   // les nuees qui filent
      vp_fenetre_ligne(e.nuees, 128, t * 6, 0, y, l);
      for (int x = 0; x < W; x++) {
        const float n = l[x];
        if (n > 0.4f) ajouter(y, x, (n - 0.4f) * 1.6f, 40, 44, 52);
        else ajouter(y, x, (n - 0.4f) * 1.5f, 12, 14, 18);
      }
    }
  } else {
    degrade2(4, 8, 22, 24, 36, 66, 0, 44);
    etoiles_du_ciel(t);
    vp_disque(52, 9, 3, 235, 235, 210);
  }
  const float phi = t * 1.1f, s = cosf(phi), as = fabsf(s), longueur = 6 + 70 * as;   // le faisceau tourne
  const float fa = (0.35f + 0.4f * as) * (tempete ? 1.4f : 1.0f) * 0.55f;
  if (s != 0)
    for (int x = 0; x < W; x++) {
      const float dx = x - 16.0f;
      if ((s > 0 ? dx : -dx) <= 0) continue;
      const float k = expf(-fabsf(dx) / longueur) * fa, demi = fabsf(dx) * 0.09f + 1.2f, c = 17 + dx * 0.04f;
      for (int y = max(0, (int)floorf(c - demi)); y <= min(H - 1, (int)ceilf(c + demi)); y++)
        if (fabsf(y - c) < demi) ajouter(y, x, k, 255, 240, 190);
    }
  const float sp = fmaxf(0.0f, sinf(phi)), s2 = sp * sp, face = s2 * s2 * s2;   // quand il regarde vers nous : l'eclat
  vp_halo(16, 17, 2 + 6 * face, 255, 240, 190, face);
  const float amp = tempete ? 1.6f : 0.6f;   // la mer
  const float m0[3] = {tempete ? 20.0f : 12.0f, tempete ? 34.0f : 22.0f, tempete ? 52.0f : 44.0f};
  const float m1[3] = {tempete ? 6.0f : 4.0f, tempete ? 12.0f : 8.0f, tempete ? 22.0f : 20.0f};
  const float ad[3] = {tempete ? 70.0f : 30.0f, tempete ? 90.0f : 40.0f, tempete ? 110.0f : 70.0f};
  float mer[64], ondx[64];
  for (int x = 0; x < W; x++) {
    mer[x] = 48 + sinf(x * 0.3f - t * 1.6f) * amp;
    ondx[x] = sinf(x * 0.11f + t * 0.7f);
  }
  for (int y = 46; y < H; y++) {
    const float k = vp_sat((y - 46) / 18.0f), rx = 52 - sinf(y * 1.3f + t * 2) * 1.5f;
    const float br = m0[0] + (m1[0] - m0[0]) * k, bv = m0[1] + (m1[1] - m0[1]) * k, bb = m0[2] + (m1[2] - m0[2]) * k;
    for (int x = 0; x < W; x++) {
      if (y < mer[x]) continue;
      const float houle = sinf(x * 0.35f - t * 1.6f + y * 0.9f) * ondx[x], hp = fmaxf(0.0f, houle);
      float r = br + hp * ad[0], v = bv + hp * ad[1], b = bb + hp * ad[2];
      if (tempete) {
        if (houle > 0.7f) { r = 150; v = 170; b = 185; }   // l'ecume sur les cretes
      } else if (y > 48 && fabsf(x - rx) < 1.5f) {        // la lune dans l'eau
        r += 90; v += 90; b += 70;
      }
      peindre(y, x, r, v, b);
    }
  }
  for (int x = 0; x < W; x++) {   // le rocher
    const float bosse = borne(9 - fabsf(x - 15.0f) * 0.6f, 0, 9) + borne(4 - fabsf(x - 27.0f) * 0.7f, 0, 4);
    if (bosse <= 0.3f) continue;
    for (int y = (int)ceilf(51 - bosse); y < H; y++) peindre(y, x, 22, 22, 26);
  }
  for (int y = 19; y <= 42; y++) {   // la tour, ses rayures
    const float l = 2.5f - (50 - y) * 0.04f;
    const bool raye = ((y - 19) / 5) % 2 == 1;
    for (int x = 12; x <= 18; x++)
      if (fabsf(x - 15.0f) <= l) {
        if (raye) peindre(y, x, 180, 40, 36);
        else peindre(y, x, 220, 220, 215);
      }
  }
  const float kl = 0.7f + 0.3f * face;   // la lanterne
  for (int y = 15; y < 19; y++)
    for (int x = 13; x < 18; x++) peindre(y, x, 255 * kl, 240 * kl, 190 * kl);
  for (int x = 13; x < 18; x++) peindre(14, x, 40, 40, 44);
  for (int x = 14; x < 17; x++) peindre(13, x, 40, 40, 44);
  for (int x = 12; x < 19; x++) peindre(19, x, 40, 40, 44);
  const bool vague = tempete ? sinf(t * 1.6f) > 0.96f : sinf(t * 1.1f) > 0.995f;   // la mer qui se brise sur le rocher
  for (int i = 0; i < 30; i++) {
    e.vy[i] += 30 * dt;
    e.ex[i] += e.vx[i] * dt;
    e.ey[i] += e.vy[i] * dt;
    if (e.ey[i] > 100) { e.ey[i] = 100; e.vy[i] = 0; }   // hors du panneau : il attend la prochaine vague
    if (vague && e.ey[i] > 50) {
      e.ex[i] = hasard(20, 30);
      e.ey[i] = 47;
      e.vx[i] = hasard(-6, 4);
      e.vy[i] = hasard(-26, -8) * (tempete ? 1.0f : 0.5f);
    }
    pointer(e.ey[i], e.ex[i], 200, 215, 225);
  }
  if (tempete) pluie(e.pluie, dt, 120, 135, 160, 0.35f);
}

// --- une nuee d'etourneaux au crepuscule : des centaines d'oiseaux qui se plient comme un seul ---
// humeurs : 0 = coucher, 1 = ville
struct E_murmuration {
  float u[420], v[420], ph[420];           // la nuee : chaque oiseau, sa place dans le disque, sa phase
  uint8_t compte[64 * 64];
  float toits[64];                         // la ville
  uint8_t fenetres[64 * 64];
  float rx[14], rh[14], rp[14];            // les roseaux (au couchant)
};
void s_murmuration(int humeur, bool debut, float t, float ecoule, float dt) {
  E_murmuration &e = etat_ecran<E_murmuration>(debut);
  (void)ecoule; (void)dt;
  const bool ville = humeur == 1;
  if (debut) {
    for (int i = 0; i < 420; i++) {
      const float a = hasard(0, PI2), r = sqrtf(hasard(0, 1));
      e.u[i] = r * cosf(a);
      e.v[i] = r * sinf(a);
      e.ph[i] = hasard(0, 6);
    }
    if (ville) {
      static const int toits[10][3] = {{0, 7, 12}, {6, 5, 16}, {11, 9, 10}, {19, 4, 20}, {23, 8, 13},
                                       {31, 6, 18}, {37, 10, 11}, {47, 5, 22}, {52, 7, 14}, {59, 5, 17}};
      for (int x = 0; x < W; x++) e.toits[x] = 64;
      for (int i = 0; i < 10; i++)
        for (int x = toits[i][0]; x < min(64, toits[i][0] + toits[i][1]); x++) e.toits[x] = fminf(e.toits[x], 64.0f - toits[i][2]);
      for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
          e.fenetres[y * 64 + x] = hasard(0, 1) > 0.82f && y % 3 == 1 && x % 2 == 0 && y > e.toits[x] + 1;
    } else {
      for (int i = 0; i < 14; i++) { e.rx[i] = hasard(14, 46); e.rh[i] = hasard(3, 8); e.rp[i] = hasard(0, 6); }
    }
  }
  if (ville) degrade2(40, 50, 100, 240, 150, 120, 0, 50);
  else {
    degrade2(90, 110, 170, 255, 170, 90, 0, 54);
    vp_aureole(20, 50, 26, 60, 40, 0);
    vp_disque(20, 50, 5, 255, 220, 150);
  }
  const float T = t * 0.18f;
  const float cx = 32 + 10 * sinf(T * 0.9f) + 4 * sinf(T * 2.1f), cy = 24 + 5 * sinf(T * 1.3f + 1);   // le centre derive
  const float rot = 0.6f * sinf(T * 0.7f), sx = 15 + 7 * sinf(T * 1.7f), sy = 8 + 4 * sinf(T * 1.1f + 2);   // elle s'etire...
  const float pli = 0.7f * sinf(T * 2.3f), sT = sinf(T), signe = sT > 0 ? 1.0f : sT < 0 ? -1.0f : 0.0f;   // ... et se plie
  const float cr = cosf(rot), sr = sinf(rot);
  for (int i = 0; i < 420; i++) {
    const float xu = e.u[i] * sx, u3 = e.u[i] * 3, yv = e.v[i] * sy + pli * u3 * u3 * signe + 3 * sinf(u3 + T * 3);
    const float px = cx + xu * cr - yv * sr + sinf(t * 3 + e.ph[i]) * 0.4f;
    const float py = cy + xu * sr + yv * cr + cosf(t * 2.6f + e.ph[i]) * 0.4f;
    if (px < 0 || px >= 64 || py < 0 || py >= 64) continue;
    uint8_t &n = e.compte[(int)py * 64 + (int)px];
    if (n < 255) n++;
  }
  for (int p = 0; p < 64 * 64; p++) {
    if (!e.compte[p]) continue;
    const float k = 1 - (1 - expf(-e.compte[p] * 0.55f)) * 0.88f;
    float *q = scene[p >> 6][p & 63];
    q[0] *= k; q[1] *= k; q[2] *= k;
    e.compte[p] = 0;
  }
  if (ville) {
    vp_sous(e.toits, 20, 18, 30);
    for (int y = 46; y <= 51; y++)   // un dome et sa lanterne
      for (int x = 22; x <= 32; x++)
        if ((x - 27) * (x - 27) + (y - 51) * (y - 51) <= 25) peindre(y, x, 20, 18, 30);
    for (int y = 43; y < 47; y++) peindre(y, 27, 20, 18, 30);
    for (int p = 0; p < 64 * 64; p++)
      if (e.fenetres[p]) peindre(p >> 6, p & 63, 255, 200, 120);
  } else {
    for (int x = 0; x < W; x++) {
      const float s = 57 + sinf(x * 0.3f);
      for (int y = (int)ceilf(s); y < H; y++) peindre(y, x, 30, 20, 26);
    }
    static const float arbres[3][2] = {{7, 6}, {50, 4.5f}, {58, 7}};   // quelques arbres
    for (int i = 0; i < 3; i++) {
      const float ax = arbres[i][0], ar = arbres[i][1], ay = 57 - ar * 1.6f;
      for (int y = max(0, (int)floorf(ay - ar)); y < H; y++)
        for (int x = max(0, (int)floorf(ax - ar)); x <= min(W - 1, (int)ceilf(ax + ar)); x++) {
          const float dx = x - ax, dy = (y - ay) * 1.1f;
          if (dx * dx + dy * dy <= ar * ar || (fabsf(dx) <= 0.5f && y >= 57 - ar)) peindre(y, x, 30, 20, 26);
        }
    }
    for (int i = 0; i < 14; i++) {   // les roseaux, qui se penchent
      const float pench = sinf(t * 0.8f + e.rp[i]) * 0.8f / e.rh[i];
      for (int j = 0; j < 9 && j < e.rh[i]; j++) vp_poser(57.0f - j, e.rx[i] + pench * j, 30, 20, 26);
    }
  }
}

// --- un village sous la neige, la nuit : les fenetres chaudes, la fumee des cheminees, la neige ---
const float VP_MAISONS[4][4] = {{10, 9, 7, 0.0f}, {24, 7, 6, 1.7f}, {39, 10, 8, 3.1f}, {54, 8, 6, 4.4f}};   // (x, largeur, hauteur, phase)
const float VP_SAPINS_VILLAGE[5][2] = {{3, 9}, {16, 7}, {30, 10}, {46, 8}, {60, 11}};
struct E_village_neige {
  float colline[64], sol[64];
  float fa[40], fv[40], fp[40];            // la fumee
  float gx[70], gy[70], gz[70], gp[70];    // les flocons : deux profondeurs
};
void s_village_neige(int humeur, bool debut, float t, float ecoule, float dt) {
  E_village_neige &e = etat_ecran<E_village_neige>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    for (int x = 0; x < W; x++) {
      e.colline[x] = 40 + 4 * sinf(x * 0.07f + 0.5f) + 2 * sinf(x * 0.19f + 2);
      e.sol[x] = 50 + 2 * sinf(x * 0.11f + 1) + sinf(x * 0.31f);
    }
    for (int i = 0; i < 40; i++) { e.fa[i] = hasard(0, 1); e.fv[i] = hasard(0, 1); e.fp[i] = hasard(0, 6); }
    for (int i = 0; i < 70; i++) { e.gx[i] = hasard(0, 64); e.gy[i] = hasard(0, 64); e.gz[i] = hasard(0, 1); e.gp[i] = hasard(0, 6); }
    semer_ciel(50, 36);
  }
  degrade2(8, 12, 32, 44, 52, 90, 0, 44);
  etoiles_du_ciel(t);
  vp_halo(50, 9, 2.2f, 120, 120, 110, 0.9f);   // la lune et son halo
  vp_disque(50, 9, 3, 235, 235, 215);
  vp_sous(e.colline, 70, 80, 112);   // la colline au loin, enneigee dans la nuit
  for (int x = 0; x < W; x++)
    for (int y = (int)ceilf(e.sol[x]); y < H; y++) {
      const float k = fminf(40.0f, (y - e.sol[x]) * 3);
      peindre(y, x, 120 + k, 132 + k, 170 + k);
    }
  for (int i = 0; i < 5; i++) {   // des sapins (leurs etages de neige ne s'allument jamais dans le numpy : sommet n'est pas entier)
    const float sx = VP_SAPINS_VILLAGE[i][0], base = e.sol[(int)sx], sommet = base - VP_SAPINS_VILLAGE[i][1];
    for (int y = max(0, (int)ceilf(sommet)); y <= (int)floorf(base); y++) {
      const float l = (y - sommet) * 0.4f + 0.5f;
      for (int x = max(0, (int)ceilf(sx - l)); x <= min(W - 1, (int)floorf(sx + l)); x++) peindre(y, x, 14, 30, 32);
    }
  }
  float chx[4], chy[4], fx[8], fy[8], fc[8];
  for (int m = 0; m < 4; m++) {
    const float mx = VP_MAISONS[m][0], larg = VP_MAISONS[m][1], haut = VP_MAISONS[m][2], ph = VP_MAISONS[m][3];
    const int base = (int)e.sol[(int)mx] + 1;
    for (int y = max(0, (int)ceilf(base - haut)); y < base; y++)   // les murs
      for (int x = max(0, (int)ceilf(mx - larg / 2)); x <= min(W - 1, (int)floorf(mx + larg / 2)); x++) peindre(y, x, 52, 40, 48);
    const float toit_haut = base - haut - larg * 0.55f;
    for (int y = max(0, (int)ceilf(toit_haut)); y < base - haut + 1; y++) {   // le toit sous la neige
      const float l = (y - toit_haut) * 1.05f + 0.6f;
      for (int x = max(0, (int)ceilf(mx - l)); x <= min(W - 1, (int)floorf(mx + l)); x++) {
        if (y >= base - haut) peindre(y, x, 150, 160, 190);
        else peindre(y, x, 205, 215, 235);
      }
    }
    const float cx = mx + larg * 0.25f;   // la cheminee
    for (int y = max(0, (int)ceilf(toit_haut + 1)); y < base - haut - 1; y++)
      for (int x = (int)ceilf(cx - 0.6f); x <= (int)floorf(cx + 0.6f); x++) peindre(y, x, 60, 44, 44);
    const float chaud = 0.85f + 0.1f * sinf(t * 1.3f + ph) + 0.05f * sinf(t * 3.7f + ph * 2);   // le feu dedans, qui vit
    for (int j = 0; j < 2; j++) {
      const float wx = mx + (j ? 0.25f : -0.25f) * larg, wy = base - haut * 0.55f;
      peindre((int)wy - 1, (int)wx, 255 * chaud, 190 * chaud, 100 * chaud);
      peindre((int)wy, (int)wx, 255 * chaud, 190 * chaud, 100 * chaud);
      fx[m * 2 + j] = wx + 0.5f;
      fy[m * 2 + j] = wy - 0.5f;
      fc[m * 2 + j] = chaud;
    }
    chx[m] = cx;
    chy[m] = toit_haut;
  }
  for (int i = 0; i < 8; i++) {   // les fenetres eclairent la neige
    vp_halo(fx[i], fy[i], 1.6f, 255, 150, 60, 0.5f * fc[i]);
    vp_halo(fx[i], fy[i] + 4, 1.2f, 255, 150, 60, 0.15f * fc[i], 0.5f);
  }
  for (int i = 0; i < 40; i++) {   // la fumee : elle monte, s'elargit, s'efface
    const float age = vp_mod(e.fa[i] + t * 0.07f * (0.7f + 0.6f * e.fv[i]), 1.0f);
    const int q = i % 4;
    const float sy = chy[q] - age * 22, sx = chx[q] + age * 9 + sinf(age * 6 + e.fp[i]) * age * 2.5f;
    const float g = (1 - age) * sqrtf(1 - age) * 0.55f;
    pointer(sy, sx, 150 * g, 150 * g, 165 * g);
    pointer(sy, sx + 1, 90 * g, 90 * g, 99 * g);
  }
  for (int i = 0; i < 70; i++) {   // la neige
    e.gy[i] = vp_mod(e.gy[i] + (4 + e.gz[i] * 7) * dt, 64);
    e.gx[i] = vp_mod(e.gx[i] + sinf(t * 0.7f + e.gp[i]) * (0.3f + e.gz[i] * 0.5f) * dt * 4, 64);
    const float k = 0.45f + e.gz[i] * 0.55f;
    pointer(e.gy[i], e.gx[i], 235 * k, 240 * k, 255 * k);
  }
}
