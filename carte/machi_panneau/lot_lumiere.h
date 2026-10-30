// lot_lumiere.h -- les jeux de lumiere, portes de machi_tool.py (croquis v10) : les etoiles, la pluie de
// code, le plasma, le feu, le jeu de la vie, le tunnel, la lampe a lave, le feu d'artifice, les tuyaux,
// « MACHI » qui rebondit, les ondes. Chacun suit son jumeau _ecran_<nom> en numpy, sur fond noir (np.zeros)
// sauf ceux qui peignent tout le panneau.
#pragma once

// l'image vide des jeux (np.zeros) : tout le panneau, en noir
inline void lum_noir() { memset(scene, 0, sizeof scene); }

// _teintes, tronquee comme son astype(np.uint8) : la ou numpy remultiplie la couleur entiere
inline void lum_teinte(float h, float s, float v, float *c) {
  float r, g, b;
  teinte(h, s, v, r, g, b);
  c[0] = floorf(r);
  c[1] = floorf(g);
  c[2] = floorf(b);
}

// --- les etoiles : on fonce dedans, de plus en plus vite (_ecran_etoiles) ---
const int LUM_ETOILES = 110;
struct E_j_etoiles { float x[LUM_ETOILES], y[LUM_ETOILES], z[LUM_ETOILES]; };
void j_etoiles(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_etoiles &e = etat_ecran<E_j_etoiles>(debut);
  (void)humeur; (void)t;
  if (debut)
    for (int i = 0; i < LUM_ETOILES; i++) { e.x[i] = hasard(-1, 1); e.y[i] = hasard(-1, 1); e.z[i] = hasard(0.05f, 1.0f); }
  const float vitesse = 0.2f + 0.4f * fminf(1.0f, ecoule / 5.0f);
  lum_noir();
  for (int i = 0; i < LUM_ETOILES; i++) {
    e.z[i] -= vitesse * dt;
    bool hors = e.z[i] <= 0.04f;
    if (!hors) {
      const float sx = 32 + e.x[i] / e.z[i] * 20, sy = 32 + e.y[i] / e.z[i] * 20;
      hors = sx < 0 || sx >= 64 || sy < 0 || sy >= 64;
    }
    if (hors) { e.x[i] = hasard(-1, 1); e.y[i] = hasard(-1, 1); e.z[i] = hasard(0.7f, 1.0f); }
    const float z = e.z[i], lum = borne(1.25f - z, 0.15f, 1.0f), z2 = z + 0.06f, q = lum * 0.45f;
    pointer(32 + e.y[i] / z2 * 20, 32 + e.x[i] / z2 * 20, q * 160, q * 180, q * 255);   // la trainee
    pointer(32 + e.y[i] / z * 20, 32 + e.x[i] / z * 20, lum * 235, lum * 240, lum * 255);
  }
}

// --- la pluie de code verte : des colonnes qui tombent, leur tete blanche (_ecran_matrice) ---
// seules les colonnes paires portent du code : la trace et les glyphes n'en gardent que 32
struct E_j_matrice { float tete[32], vit[32], change, trace[64][32], glyphes[64][32]; };
void j_matrice(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_matrice &e = etat_ecran<E_j_matrice>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    for (int c = 0; c < 32; c++) { e.tete[c] = hasard(-64, 0); e.vit[c] = hasard(12, 30); }
    for (int y = 0; y < 64; y++)
      for (int c = 0; c < 32; c++) e.glyphes[y][c] = hasard(0.3f, 1.0f);
    e.change = 0;
  }
  const float f = expf(-dt * 2.6f);
  for (int y = 0; y < 64; y++)
    for (int c = 0; c < 32; c++) e.trace[y][c] *= f;
  for (int c = 0; c < 32; c++) {
    const float avant = e.tete[c];
    e.tete[c] += e.vit[c] * dt;
    for (int y = max(0, (int)avant); y < min(64, (int)e.tete[c] + 1); y++) e.trace[y][c] = 1.0f;
    if (e.tete[c] > 64 + 20) { e.tete[c] = hasard(-24, 0); e.vit[c] = hasard(12, 30); }
  }
  if (t - e.change > 0.08f) {                           // les caracteres changent
    e.change = t;
    for (int y = 0; y < 64; y++)
      for (int c = 0; c < 32; c++)
        if (hasard(0, 1) < 0.06f) e.glyphes[y][c] = hasard(0.3f, 1.0f);
  }
  for (int y = 0; y < 64; y++)
    for (int c = 0; c < 32; c++) {
      const float v = e.trace[y][c] * e.glyphes[y][c];
      peindre(y, 2 * c, v * 30, v * 255, v * 80);
      peindre(y, 2 * c + 1, 0, 0, 0);
    }
  for (int c = 0; c < 32; c++) {
    const int ty = (int)e.tete[c];
    if (ty >= 0 && ty < 64) peindre(ty, 2 * c, 200, 255, 210);
  }
}

// --- le plasma : des ondes de couleur qui se melangent (_ecran_plasma) ---
const int LUM_RONDE = 4 * 72;                      // le centre reste a 18 px du milieu : jamais plus de 71 px
struct E_j_plasma { char rien; };
void j_plasma(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_plasma &e = etat_ecran<E_j_plasma>(debut);
  (void)e; (void)humeur; (void)ecoule; (void)dt;
  float sx[64], sy[64], sxy[127];                       // les trois ondes droites : par colonne, ligne, diagonale
  for (int i = 0; i < 64; i++) { sx[i] = sinf(i * 0.13f + t * 1.1f); sy[i] = sinf(i * 0.11f - t * 0.9f); }
  for (int i = 0; i < 127; i++) sxy[i] = sinf(i * 0.09f + t * 0.7f);
  float ronde[LUM_RONDE + 2];                           // la ronde, par distance (un quart de pixel), interpolee
  for (int i = 0; i < LUM_RONDE + 2; i++) ronde[i] = sinf(i * 0.25f * 0.17f - t);
  const float cx = 32 + 18 * sinf(t * 0.5f), cy = 32 + 18 * cosf(t * 0.4f), decal = t * 0.05f;
  for (int y = 0; y < 64; y++) {
    const float dy2 = (y - cy) * (y - cy);
    for (int x = 0; x < 64; x++) {
      const float dx = x - cx, q = sqrtf(dx * dx + dy2) * 4;
      const int i = (int)q;
      const float v = sx[x] + sy[y] + sxy[x + y] + ronde[i] + (ronde[i + 1] - ronde[i]) * (q - i);
      float r, g, b;
      teinte(v * 0.125f + decal, 0.85f, 0.85f, r, g, b);
      peindre(y, x, r, g, b);
    }
  }
}

// --- le feu de cheminee, qui monte du bas du panneau (_ecran_feu) ---
struct E_j_feu { float chaleur[72][64], acc; uint8_t palette[256][3]; };
void j_feu(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_feu &e = etat_ecran<E_j_feu>(debut);
  (void)humeur; (void)t; (void)ecoule;
  if (debut)
    for (int i = 0; i < 256; i++) {                     // _palette_feu : noir, rouge, jaune, blanc
      const float x = i / 255.0f;
      e.palette[i][0] = (uint8_t)(borne(x * 3.0f, 0, 1) * 255);
      e.palette[i][1] = (uint8_t)(borne(x * 3.0f - 1.0f, 0, 1) * 0.9f * 255);
      e.palette[i][2] = (uint8_t)(borne(x * 3.0f - 2.0f, 0, 1) * 0.8f * 255);
    }
  e.acc += dt;
  int pas = 0;
  while (e.acc >= 1.0f / 30 && pas < 3) {
    e.acc -= 1.0f / 30;
    pas++;
    for (int y = 70; y < 72; y++)                       // le foyer : des braises
      for (int x = 0; x < 64; x++) e.chaleur[y][x] = hasard(0, 1) < 0.6f ? hasard(0.8f, 1.0f) : 0.0f;
    // chaque case, la moyenne des trois d'en dessous et de celle d'encore en dessous, qui refroidit ; de
    // haut en bas, chaque ligne ne lit que celles d'en dessous, pas encore touchees : comme numpy
    for (int y = 0; y < 70; y++) {
      const float *b1 = e.chaleur[y + 1], *b2 = e.chaleur[y + 2];
      for (int x = 0; x < 64; x++) {
        const float s = b1[(x + 63) & 63] + b1[x] + b1[(x + 1) & 63] + b2[x];
        e.chaleur[y][x] = borne(s * 0.25f * 0.962f - 0.007f, 0, 1);
      }
    }
  }
  for (int y = 0; y < 64; y++)                          // sans les braises brutes
    for (int x = 0; x < 64; x++) {
      const uint8_t *c = e.palette[(int)(e.chaleur[y + 6][x] * 255)];
      peindre(y, x, c[0], c[1], c[2]);
    }
}

// --- le jeu de la vie : les jeunes cyan, les vieilles violettes, un fantome bleu (_ecran_vie) ---
struct E_j_vie {
  uint8_t g[64][64], neuve[64][64], age[64][64];
  float fantome[64][64], acc;
  int pops[24], npops;
  float couleurs[31][3];
};
void j_vie(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_vie &e = etat_ecran<E_j_vie>(debut);
  (void)humeur; (void)t; (void)ecoule;
  if (debut) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) e.g[y][x] = hasard(0, 1) < 0.3f;
    for (int k = 0; k <= 30; k++) lum_teinte(0.5f + k / 30.0f * 0.33f, 0.8f, 1.0f, e.couleurs[k]);
  }
  e.acc += dt;
  while (e.acc >= 0.11f) {
    e.acc -= 0.11f;
    int vivantes = 0;
    for (int y = 0; y < 64; y++) {
      const uint8_t *h = e.g[(y + 63) & 63], *m = e.g[y], *b = e.g[(y + 1) & 63];
      for (int x = 0; x < 64; x++) {
        const int g = (x + 63) & 63, d = (x + 1) & 63;
        const int n = h[g] + h[x] + h[d] + m[g] + m[d] + b[g] + b[x] + b[d];
        const bool nv = n == 3 || (m[x] && n == 2);
        e.neuve[y][x] = nv;
        vivantes += nv;
      }
    }
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const bool nv = e.neuve[y][x];
        e.fantome[y][x] = fmaxf(e.fantome[y][x] * 0.8f, e.g[y][x] && !nv ? 1.0f : 0.0f);
        e.age[y][x] = nv ? (uint8_t)min(255, e.age[y][x] + 1) : 0;
        e.g[y][x] = nv;
      }
    if (e.npops == 24) {                                 // les 24 dernieres populations
      memmove(e.pops, e.pops + 1, 23 * sizeof(int));
      e.npops = 23;
    }
    e.pops[e.npops++] = vivantes;
    int distinctes = 0;
    for (int i = 0; i < e.npops; i++) {
      bool vue = false;
      for (int j = 0; j < i && !vue; j++) vue = e.pops[j] == e.pops[i];
      distinctes += !vue;
    }
    if (vivantes < 60 || (e.npops == 24 && distinctes <= 3)) {   // elle s'eteint ou se fige : on resseme
      for (int y = 0; y < 64; y++)
        for (int x = 0; x < 64; x++)
          if (hasard(0, 1) < 0.18f) e.g[y][x] = 1;
      e.npops = 0;
    }
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      if (e.g[y][x]) {
        const float *c = e.couleurs[min(30, (int)e.age[y][x])];
        peindre(y, x, c[0], c[1], c[2]);
      } else {
        const float f = e.fantome[y][x];
        peindre(y, x, f * 10, f * 30, f * 90);
      }
    }
}

// --- le tunnel en damier qui tourne, ou l'on s'enfonce (_ecran_tunnel) ---
// atan2 en polynome (a 0.0015 rad pres : les cases bougent de moins d'un centieme)
inline float lum_atan2(float y, float x) {
  const float ax = fabsf(x), ay = fabsf(y);
  const float mx = fmaxf(ax, ay), mn = fminf(ax, ay);
  if (mx <= 0) return 0;
  const float a = mn / mx, s = a * a;
  float r = ((-0.0464964749f * s + 0.15931422f) * s - 0.327622764f) * s * a + a;
  if (ay > ax) r = 1.57079637f - r;
  if (x < 0) r = 3.14159274f - r;
  return y < 0 ? -r : r;
}
struct E_j_tunnel { char rien; };
void j_tunnel(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_tunnel &e = etat_ecran<E_j_tunnel>(debut);
  (void)e; (void)humeur; (void)ecoule; (void)dt;
  const float ox = -32 + 6 * sinf(t * 0.7f), oy = -32 + 6 * cosf(t * 0.5f);
  const float tu = t * 0.4f * 2, tv = t * 2.0f, th = t * 0.03f;
  for (int y = 0; y < 64; y++) {
    const float dy = y + oy;
    for (int x = 0; x < 64; x++) {
      const float dx = x + ox;
      const float d = sqrtf(dx * dx + dy * dy) + 0.5f;
      const float u2 = lum_atan2(dy, dx) * (8 / 3.14159265f) + tu, v = 40.0f / d + tv;   // u * 2, v
      const int damier = ((int)floorf(u2) + (int)floorf(v)) & 1;
      const float ombre = fminf(d * (1 / 30.0f), 1.0f);
      float r, g, b;
      teinte(v * 0.05f + th, 0.8f, (damier ? 1.0f : 0.3f) * ombre, r, g, b);
      peindre(y, x, r, g, b);
    }
  }
}

// --- la lampe a lave : des boules qui montent, se touchent et se fondent (_ecran_lave) ---
struct E_j_lave { char rien; };
void j_lave(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_lave &e = etat_ecran<E_j_lave>(debut);
  (void)e; (void)humeur; (void)ecoule; (void)dt;
  static const float BOULES[5][4] = {{9, 0.31f, 0.21f, 0.0f}, {7, 0.23f, 0.17f, 1.7f}, {8, 0.37f, 0.13f, 3.1f},
                                     {6, 0.29f, 0.27f, 4.4f}, {7, 0.19f, 0.11f, 5.6f}};
  float dx2[5][64], by[5], r2[5];                       // les ecarts en x, par colonne
  for (int i = 0; i < 5; i++) {
    const float bx = 32 + 18 * sinf(t * BOULES[i][1] + BOULES[i][3]);
    by[i] = 32 + 26 * sinf(t * BOULES[i][2] + BOULES[i][3] * 1.3f);
    r2[i] = BOULES[i][0] * BOULES[i][0];
    for (int x = 0; x < 64; x++) dx2[i][x] = (x - bx) * (x - bx);
  }
  for (int y = 0; y < 64; y++) {
    float dy2[5];
    for (int i = 0; i < 5; i++) dy2[i] = (y - by[i]) * (y - by[i]) + 1.0f;
    const float fr = 25 + y * 0.4f, fv = 5 + y * 0.1f, fb = 40 + y * 0.3f;
    for (int x = 0; x < 64; x++) {
      float champ = 0;
      for (int i = 0; i < 5; i++) champ += r2[i] / (dx2[i][x] + dy2[i]);
      const float halo = borne((champ - 0.55f) / 0.45f, 0, 1), dedans = borne((champ - 1.0f) / 1.6f, 0, 1);
      const float lv = 70 + 140 * dedans, lb = 30 + 30 * dedans;   // rouge-orange, jaune au coeur
      peindre(y, x, fr + (255 - fr) * halo, fv + (lv - fv) * halo, fb + (lb - fb) * halo);
    }
  }
}

// --- le feu d'artifice : des fusees qui montent et eclatent en couleurs (_ecran_artifice) ---
const int LUM_ETINCELLES = 480, LUM_FUSEES = 8;
struct E_j_artifice {
  uint16_t lueur[64][64][3];                            // la lueur qui s'efface, x256
  float suivante;
  int nf, np;
  float fusee[LUM_FUSEES][5];                           // x, y, vx, vy, hauteur ou elle eclate
  float px[LUM_ETINCELLES], py[LUM_ETINCELLES], pvx[LUM_ETINCELLES], pvy[LUM_ETINCELLES];
  float vie[LUM_ETINCELLES], vie0[LUM_ETINCELLES];
  uint8_t couleur[LUM_ETINCELLES][3];
};
inline void lum_lueur(E_j_artifice &e, float yf, float xf, float r, float v, float b) {   // _pointer sur la lueur
  const int y = (int)yf, x = (int)xf;
  if (y < 0 || y >= 64 || x < 0 || x >= 64) return;
  uint16_t *p = e.lueur[y][x];
  const uint16_t c[3] = {(uint16_t)(r * 256), (uint16_t)(v * 256), (uint16_t)(b * 256)};
  for (int k = 0; k < 3; k++)
    if (c[k] > p[k]) p[k] = c[k];
}
void j_artifice(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_artifice &e = etat_ecran<E_j_artifice>(debut);
  (void)humeur; (void)t;
  const uint32_t passe = (uint32_t)(expf(-dt * 3.5f) * 65536);
  uint16_t *l = &e.lueur[0][0][0];
  for (int i = 0; i < 64 * 64 * 3; i++) l[i] = (uint16_t)((l[i] * passe) >> 16);
  if (ecoule >= e.suivante) {
    e.suivante = ecoule + hasard(0.45f, 1.0f);
    if (e.nf < LUM_FUSEES) {
      float *f = e.fusee[e.nf++];
      f[0] = hasard(10, 54); f[1] = 63; f[2] = hasard(-5, 5); f[3] = -hasard(40, 52); f[4] = hasard(10, 26);
    }
  }
  int garde = 0;
  for (int i = 0; i < e.nf; i++) {
    float *f = e.fusee[i];
    f[0] += f[2] * dt;
    f[1] += f[3] * dt;
    f[3] += 30 * dt;
    if (f[3] >= -4 || f[1] <= f[4]) {                   // au plus haut : elle eclate
      const int n = min(50 + (int)(aleatoire() % 30), LUM_ETINCELLES - e.np);
      const float vitesse = hasard(0.6f, 1.0f), h = hasard(0, 1);
      for (int k = 0; k < n; k++) {
        const int j = e.np++;
        const float a = hasard(0, PI2), v = hasard(10, 26) * vitesse;
        e.px[j] = f[0]; e.py[j] = f[1]; e.pvx[j] = cosf(a) * v; e.pvy[j] = sinf(a) * v;
        e.vie[j] = e.vie0[j] = hasard(1.2f, 2.0f);
        float c[3];
        lum_teinte(h + hasard(-0.04f, 0.04f), 0.6f, 1.0f, c);
        for (int q = 0; q < 3; q++) e.couleur[j][q] = (uint8_t)c[q];
      }
    } else {
      for (int q = 0; q < 5; q++) e.fusee[garde][q] = f[q];
      garde++;
      lum_lueur(e, f[1], f[0], 255, 220, 150);
    }
  }
  e.nf = garde;
  const float freine = expf(-dt * 1.2f);
  garde = 0;
  for (int j = 0; j < e.np; j++) {
    e.px[j] += e.pvx[j] * dt;
    e.py[j] += e.pvy[j] * dt;
    e.pvy[j] += 18 * dt;
    e.pvx[j] *= freine;
    e.vie[j] -= dt;
    if (e.vie[j] <= 0) continue;
    if (garde != j) {
      e.px[garde] = e.px[j]; e.py[garde] = e.py[j]; e.pvx[garde] = e.pvx[j]; e.pvy[garde] = e.pvy[j];
      e.vie[garde] = e.vie[j]; e.vie0[garde] = e.vie0[j];
      for (int q = 0; q < 3; q++) e.couleur[garde][q] = e.couleur[j][q];
    }
    garde++;
  }
  e.np = garde;
  for (int j = 0; j < e.np; j++) {                      // vives, puis elles s'eteignent
    const float reste = fminf(e.vie[j] / e.vie0[j] * 1.6f, 1.0f);
    lum_lueur(e, e.py[j], e.px[j], e.couleur[j][0] * reste, e.couleur[j][1] * reste, e.couleur[j][2] * reste);
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const uint16_t *p = e.lueur[y][x];
      peindre(y, x, p[0] * (1 / 256.0f), p[1] * (1 / 256.0f), p[2] * (1 / 256.0f));
    }
}

// --- les tuyaux : ils poussent, tournent, se croisent, puis on recommence (_ecran_tuyaux) ---
struct LumTuyau { int x, y, d; float c[3]; };
struct E_j_tuyaux { uint8_t img[64][64][3], pris[16][16]; int n; LumTuyau p[3]; float acc; };
const int LUM_DIRECTIONS[4][2] = {{1, 0}, {0, 1}, {-1, 0}, {0, -1}};
void lum_remplir(E_j_tuyaux &e, int y0, int y1, int x0, int x1, const float *c) {   // img[y0:y1, x0:x1] = c
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++)
      for (int k = 0; k < 3; k++) e.img[y][x][k] = (uint8_t)c[k];
}
void lum_nouveau_tuyau(E_j_tuyaux &e) {
  int pris = 0;
  for (int i = 0; i < 256; i++) pris += e.pris[i / 16][i % 16];
  if (pris == 256 || pris > 0.6f * 256) {               // trop plein : on recommence
    memset(e.img, 0, sizeof e.img);
    memset(e.pris, 0, sizeof e.pris);
    pris = 0;
  }
  int k = (int)(aleatoire() % (uint32_t)(256 - pris));
  for (int i = 0; i < 256; i++) {
    if (e.pris[i / 16][i % 16]) continue;
    if (k-- == 0) {
      e.pris[i / 16][i % 16] = 1;
      LumTuyau &p = e.p[e.n++];
      p.x = i % 16; p.y = i / 16;
      lum_teinte(hasard(0, 1), 0.75f, 1.0f, p.c);
      p.d = (int)(aleatoire() % 4);
      return;
    }
  }
}
void j_tuyaux(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_tuyaux &e = etat_ecran<E_j_tuyaux>(debut);
  (void)humeur; (void)t; (void)ecoule;
  while (e.n < 3) lum_nouveau_tuyau(e);
  e.acc += dt;
  while (e.acc >= 0.06f) {
    e.acc -= 0.06f;
    int garde = 0;
    for (int i = 0; i < e.n; i++) {
      LumTuyau p = e.p[i];
      int essais[4], ne = 0;
      if (hasard(0, 1) < 0.7f) essais[ne++] = p.d;      // tout droit, le plus souvent
      int ordre[4] = {0, 1, 2, 3};
      for (int a = 3; a > 0; a--) {
        const int b = (int)(aleatoire() % (uint32_t)(a + 1)), c = ordre[a];
        ordre[a] = ordre[b];
        ordre[b] = c;
      }
      for (int a = 0; a < 4; a++)
        if (ordre[a] != (p.d + 2) % 4 && !(ne && essais[0] == ordre[a])) essais[ne++] = ordre[a];
      int d = -1, nx = 0, ny = 0;
      for (int a = 0; a < ne && d < 0; a++) {
        nx = p.x + LUM_DIRECTIONS[essais[a]][0];
        ny = p.y + LUM_DIRECTIONS[essais[a]][1];
        if (nx >= 0 && nx < 16 && ny >= 0 && ny < 16 && !e.pris[ny][nx]) d = essais[a];
      }
      if (d < 0) continue;                              // coince : il s'arrete la, un autre commence
      const int px0 = p.x * 4 + 1, py0 = p.y * 4 + 1, px1 = nx * 4 + 1, py1 = ny * 4 + 1;
      const int g = min(px0, px1), h = min(py0, py1), gd = max(px0, px1), hb = max(py0, py1);
      float c[3];
      for (int k = 0; k < 3; k++) c[k] = p.c[k] * 0.75f;
      lum_remplir(e, h, hb + 2, g, gd + 2, c);          // l'ombre, puis le tuyau
      for (int k = 0; k < 3; k++) c[k] = fminf(255.0f, p.c[k] * 1.1f);
      lum_remplir(e, h, hb + 1, g, gd + 1, c);
      if (d != p.d) {                                   // un coude
        for (int k = 0; k < 3; k++) c[k] = fminf(255.0f, p.c[k] * 0.9f + 40);
        lum_remplir(e, py0 - 1, py0 + 3, px0 - 1, px0 + 3, c);
      }
      e.pris[ny][nx] = 1;
      p.x = nx; p.y = ny; p.d = d;
      e.p[garde++] = p;
    }
    e.n = garde;
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) peindre(y, x, e.img[y][x][0], e.img[y][x][1], e.img[y][x][2]);
}

// --- « MACHI » qui rebondit d'un bord a l'autre, et change de couleur a chaque bord (_ecran_rebond) ---
// ses lettres, dans la police 5 x 7 du panneau de Jarvis (jarvis._GLYPHES) : une ligne par octet, le bit 4 a gauche
const uint8_t LUM_MACHI[5][7] = {
  {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11},   // M
  {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11},   // A
  {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E},   // C
  {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11},   // H
  {0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E},   // I
};
const int LUM_LARGEUR = 5 * 6 - 1;                 // largeur_5x7("MACHI")
struct E_j_rebond { float x, y, vx, vy, teinte; int n; float sx[40], sy[40], svx[40], svy[40], svie[40]; };
void j_rebond(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_rebond &e = etat_ecran<E_j_rebond>(debut);
  (void)humeur; (void)t; (void)ecoule;
  if (debut) { e.x = hasard(0, 64 - LUM_LARGEUR); e.y = hasard(0, 57); e.vx = 13; e.vy = 9; e.teinte = hasard(0, 1); }
  e.x += e.vx * dt;
  e.y += e.vy * dt;
  int bords = 0;
  if (!(e.x >= 0 && e.x <= 64 - LUM_LARGEUR)) { e.vx = -e.vx; e.x = borne(e.x, 0, 64 - LUM_LARGEUR); bords++; }
  if (!(e.y >= 0 && e.y <= 57)) { e.vy = -e.vy; e.y = borne(e.y, 0, 57); bords++; }
  if (bords) {
    e.teinte += 0.17f + hasard(0, 0.2f);
    e.teinte -= floorf(e.teinte);
  }
  if (bords == 2) {                                     // le coin !
    e.n = 40;
    for (int i = 0; i < 40; i++) {
      const float a = hasard(0, PI2), v = hasard(8, 24);
      e.sx[i] = e.x + LUM_LARGEUR / 2.0f; e.sy[i] = e.y + 3; e.svx[i] = cosf(a) * v; e.svy[i] = sinf(a) * v; e.svie[i] = 1.2f;
    }
  }
  lum_noir();
  int garde = 0;
  for (int i = 0; i < e.n; i++) {
    e.sx[i] += e.svx[i] * dt;
    e.sy[i] += e.svy[i] * dt;
    e.svie[i] -= dt;
    if (e.svie[i] <= 0) continue;
    e.sx[garde] = e.sx[i]; e.sy[garde] = e.sy[i]; e.svx[garde] = e.svx[i]; e.svy[garde] = e.svy[i];
    e.svie[garde] = e.svie[i];
    const float k = e.svie[i] / 1.2f;
    pointer(e.sy[i], e.sx[i], k * 255, k * 240, k * 180);
    garde++;
  }
  e.n = garde;
  float c[3];
  lum_teinte(e.teinte, 0.8f, 1.0f, c);
  const int x0 = (int)rintf(e.x), y0 = (int)rintf(e.y);   // round de Python : au pair
  for (int l = 0; l < 5; l++)
    for (int j = 0; j < 7; j++)
      for (int i = 0; i < 5; i++) {
        const int x = x0 + l * 6 + i, y = y0 + j;
        if (((LUM_MACHI[l][j] >> (4 - i)) & 1) && x >= 0 && x < 64 && y >= 0 && y < 64) peindre(y, x, c[0], c[1], c[2]);
      }
}

// --- des gouttes sur l'eau : des ronds qui s'elargissent et se croisent (_ecran_ondes) ---
struct E_j_ondes { float ch[2][64][64]; int cur; float goutte, acc; };
// une ligne du champ adouci (sans le grain) : (4 a + ses quatre voisines) / 8
inline void lum_lisser(const float (*a)[64], int y, float *sortie) {
  const float *h = a[(y + 63) & 63], *m = a[y], *b = a[(y + 1) & 63];
  for (int x = 0; x < 64; x++) sortie[x] = (4 * m[x] + h[x] + b[x] + m[(x + 63) & 63] + m[(x + 1) & 63]) * 0.125f;
}
void j_ondes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_j_ondes &e = etat_ecran<E_j_ondes>(debut);
  (void)humeur; (void)t;
  if (ecoule >= e.goutte) {                             // une goutte ronde, sans aretes
    e.goutte = ecoule + hasard(0.35f, 0.9f);
    const float gy = hasard(6, 58), gx = hasard(6, 58);
    float (*a)[64] = e.ch[e.cur];
    for (int y = max(0, (int)gy - 8); y <= min(63, (int)gy + 9); y++)
      for (int x = max(0, (int)gx - 8); x <= min(63, (int)gx + 9); x++)
        a[y][x] -= 5.0f * expf(-((x - gx) * (x - gx) + (y - gy) * (y - gy)) / 3.0f);
  }
  e.acc += dt;
  while (e.acc >= 1.0f / 30) {
    e.acc -= 1.0f / 30;
    const float (*a)[64] = e.ch[e.cur];
    float (*b)[64] = e.ch[e.cur ^ 1];                   // l'avant-derniere devient la nouvelle
    for (int y = 0; y < 64; y++) {
      const float *h = a[(y + 63) & 63], *m = a[y], *s = a[(y + 1) & 63];
      for (int x = 0; x < 64; x++)
        b[y][x] = ((h[x] + s[x] + m[(x + 63) & 63] + m[(x + 1) & 63]) * 0.5f - b[y][x]) * 0.975f;
    }
    e.cur ^= 1;
  }
  const float (*a)[64] = e.ch[e.cur];
  float premiere[64], ici[64], dessous[64];
  lum_lisser(a, 0, premiere);
  memcpy(ici, premiere, sizeof ici);
  for (int y = 0; y < 64; y++) {
    if (y < 63) lum_lisser(a, y + 1, dessous);
    else memcpy(dessous, premiere, sizeof dessous);
    for (int x = 0; x < 64; x++) {
      const float pente = ici[(x + 1) & 63] - ici[x] + dessous[x] - ici[x];
      const float l = borne(pente * 0.35f, -1, 1);
      if (l > 0) peindre(y, x, 5 + l * 170, 45 + l * 210, 95 + l * 160);
      else peindre(y, x, 5 + l * 5, 45 + l * 30, 95 + l * 60);
    }
    memcpy(ici, dessous, sizeof ici);
  }
}
