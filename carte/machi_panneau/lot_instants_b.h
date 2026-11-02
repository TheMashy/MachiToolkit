// lot_instants_b.h -- les instants, lot B (croquis v10) : l'echoppe de ramen, la laverie, le petit cafe ouvert
// tard, la station-service au milieu de rien. Portes de machi_tool.py (_scene_ramen, _scene_laverie, _scene_diner,
// _scene_station_service). Comme en numpy : un decor fixe calcule au debut -- la lumiere (a tramer) et le calque
// net (pose par-dessus la trame), ranges ensemble dans un fond en octets et un masque -- puis, a chaque image, la
// lumiere qui bouge, la trame de Bayer, les sprites (des chaines de caracteres), la vapeur, la bruine.
#pragma once

// --- les outils du lot -------------------------------------------------------------------------------------------

static const uint8_t IB_BAYER[4][4] = {{0, 8, 2, 10}, {12, 4, 14, 6}, {3, 11, 1, 9}, {15, 7, 13, 5}};
static const float IB_MARCHES[8] = {0.0f, 5.2040816f, 20.816326f, 46.836735f, 83.265306f, 130.10204f, 187.34694f,
                                    255.0f};   // les marches de tramer(8)

// la trame de tramer(8) pour un pixel d'eclat v (> 0) en (y, x) : la couleur fois ce facteur tombe sur une marche
inline float ib_marche(float v, int y, int x) {
  float q = floorf(sqrtf(v * (1.0f / 255)) * 7 + 0.5f + IB_BAYER[y & 3][x & 3] * (1.0f / 16) - 15.0f / 32);
  q = borne(q, 0, 7);
  return q * q * (255.0f / 49) / v;
}

// _ib_niv : la couleur ramenee pile sur la marche k (un aplat qui reste uni une fois trame)
struct IbC { float r, v, b; };
inline IbC ib_niv(float r, float v, float b, int k) {
  const float m = IB_MARCHES[k] / fmaxf(r, fmaxf(v, b));
  return {r * m, v * m, b * m};
}

// le decor d'un ecran : la lumiere (octets) et, la ou le masque est mis, la couleur du calque net
struct IbDecor { uint8_t fond[64][64][3]; uint64_t masque[64]; };

inline uint8_t ib_octet(float v) { return (uint8_t)borne(v + 0.5f, 0, 255); }

// la scene (la lumiere en flottants, construite au debut) -> le fond, masque vide
void ib_garder_lumiere(IbDecor &d) {
  for (int y = 0; y < 64; y++) {
    d.masque[y] = 0;
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) d.fond[y][x][c] = ib_octet(scene[y][x][c]);
  }
}

// un pixel du calque net (hors champ ignore)
inline void ib_net(IbDecor &d, int y, int x, float r, float v, float b) {
  if (y < 0 || y >= 64 || x < 0 || x >= 64) return;
  d.fond[y][x][0] = ib_octet(r);
  d.fond[y][x][1] = ib_octet(v);
  d.fond[y][x][2] = ib_octet(b);
  d.masque[y] |= 1ull << x;
}
// un rectangle du calque net, bornes comprises
void ib_net_rect(IbDecor &d, int y0, int y1, int x0, int x1, float r, float v, float b) {
  for (int y = y0; y <= y1; y++)
    for (int x = x0; x <= x1; x++) ib_net(d, y, x, r, v, b);
}
inline void ib_net_rect(IbDecor &d, int y0, int y1, int x0, int x1, IbC c) { ib_net_rect(d, y0, y1, x0, x1, c.r, c.v, c.b); }

// chaque image : le fond dans la scene (la lumiere, a laquelle on ajoute ce qui bouge)
void ib_poser_fond(const IbDecor &d) {
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] = d.fond[y][x][c];
}

// _tramer(img, 8), puis img[masque] = net[masque] : la trame sur la lumiere, le calque net par-dessus
void ib_composer(const IbDecor &d) {
  for (int y = 0; y < 64; y++) {
    const uint64_t m = d.masque[y];
    for (int x = 0; x < 64; x++) {
      float *p = scene[y][x];
      if ((m >> x) & 1) {
        p[0] = d.fond[y][x][0]; p[1] = d.fond[y][x][1]; p[2] = d.fond[y][x][2];
        continue;
      }
      p[0] = borne(p[0], 0, 255); p[1] = borne(p[1], 0, 255); p[2] = borne(p[2], 0, 255);
      const float v = fmaxf(p[0], fmaxf(p[1], p[2]));
      if (v <= 0) continue;
      const float k = ib_marche(v, y, x);
      p[0] *= k; p[1] *= k; p[2] *= k;
    }
  }
}

// _halo dans un rectangle de la scene seulement (y0 <= y < y1) : les lumieres du decor, construites par morceaux
void ib_halo_lignes(float x, float y, float rayon, float r, float v, float b, float force, float aplati, int ly0,
                    int ly1) {
  const int e = (int)(rayon * 6) + 1;
  const int x0 = max(0, (int)x - e), x1 = min(W, (int)x + e + 1);
  const int y0 = max(ly0, max(0, (int)y - e)), y1 = min(ly1, min(H, (int)y + e + 1));
  const float inv = 1.0f / rayon;
  for (int yy = y0; yy < y1; yy++)
    for (int xx = x0; xx < x1; xx++) {
      const float dx = xx - x, dy = (yy - y) * aplati;
      ajouter(yy, xx, expf(-sqrtf(dx * dx + dy * dy) * inv) * force, r, v, b);
    }
}

// la valeur de _halo en un point (0 hors de sa fenetre, comme numpy)
inline float ib_halo_val(int xx, int yy, float x, float y, float rayon, float aplati) {
  const int e = (int)(rayon * 6) + 1;
  if (xx < (int)x - e || xx >= (int)x + e + 1 || yy < (int)y - e || yy >= (int)y + e + 1) return 0;
  const float dx = xx - x, dy = (yy - y) * aplati;
  return expf(-sqrtf(dx * dx + dy * dy) / rayon);
}

// _ib_lueur : une lueur ronde a bord fini ((1 - d / rayon)^2), ajoutee dans la scene
void ib_lueur(float x, float y, float rayon, float r, float v, float b, float force = 1.0f, float aplati = 1.0f,
              int ly0 = 0, int ly1 = 64) {
  const int e = (int)rayon + 1;
  const int x0 = max(0, (int)x - e), x1 = min(64, (int)x + e + 2);
  const int y0 = max(ly0, max(0, (int)(y - e / aplati) - 1)), y1 = min(ly1, min(64, (int)(y + e / aplati) + 2));
  const float inv = 1.0f / rayon;
  for (int yy = y0; yy < y1; yy++)
    for (int xx = x0; xx < x1; xx++) {
      const float dx = xx - x, dy = (yy - y) * aplati;
      const float k = 1 - sqrtf(dx * dx + dy * dy) * inv;
      if (k > 0) ajouter(yy, xx, k * k * force, r, v, b);
    }
}

// un sprite en chaines de caracteres ('.' transparent), son coin haut-gauche en (x, y) arrondis, la palette
// {caractere, couleur} ; dans la scene, ou dans le calque net d'un decor
struct IbPal { char c; float r, v, b; };
void ib_dessin(const char *const *l, int n, float xf, float yf, const IbPal *pal, int np, bool miroir = false,
               IbDecor *d = nullptr) {
  const int x0 = (int)floorf(xf + 0.5f), y0 = (int)floorf(yf + 0.5f), larg = (int)strlen(l[0]);
  for (int i = 0; i < n; i++) {
    const int y = y0 + i;
    for (int j = 0; j < larg; j++) {
      const char c = l[i][j];
      if (c == '.') continue;
      const int x = x0 + (miroir ? larg - 1 - j : j);
      for (int k = 0; k < np; k++)
        if (pal[k].c == c) {
          if (d) ib_net(*d, y, x, pal[k].r, pal[k].v, pal[k].b);
          else if (y >= 0 && y < 64 && x >= 0 && x < 64) peindre(y, x, pal[k].r, pal[k].v, pal[k].b);
          break;
        }
    }
  }
}
template <int n, int np>
inline void ib_sprite(const char *const (&l)[n], float x, float y, const IbPal (&pal)[np], bool miroir = false,
                      IbDecor *d = nullptr) {
  ib_dessin(l, n, x, y, pal, np, miroir, d);
}

// _ib_trait : un trait d'un pixel entre deux points
void ib_trait(float x0, float y0, float x1, float y1, float r, float v, float b, IbDecor *d = nullptr) {
  const int n = (int)fmaxf(fabsf(x1 - x0), fabsf(y1 - y0)) + 2;
  for (int i = 0; i < n; i++) {
    const float s = i / (float)(n - 1);
    const float y = floorf(y0 + (y1 - y0) * s + 0.5f), x = floorf(x0 + (x1 - x0) * s + 0.5f);
    if (d) ib_net(*d, (int)y, (int)x, r, v, b);
    else poser(y, x, r, v, b);
  }
}

// _ib_tamponner : un point pose entre les pixels, partage sur ses quatre voisins
inline void ib_tampon(float (*buf)[64], float y, float x, float a) {
  const int y0 = (int)floorf(y), x0 = (int)floorf(x);
  const float fy = y - y0, fx = x - x0;
  for (int dy = 0; dy < 2; dy++)
    for (int dx = 0; dx < 2; dx++) {
      const int yy = y0 + dy, xx = x0 + dx;
      if (yy < 0 || yy >= 64 || xx < 0 || xx >= 64) continue;
      buf[yy][xx] += a * (dy ? fy : 1 - fy) * (dx ? fx : 1 - fx);
    }
}

// _ib_vapeur : des bouffees qui montent, s'elargissent, ondulent et s'effilochent (tout en fonction de t)
struct IbBouffee { float ph, dx, pp, vv; };
void ib_semer_vapeur(IbBouffee *b, int n) {
  for (int i = 0; i < n; i++) b[i] = {hasard(0, 1), hasard(-1, 1), hasard(0, PI2), hasard(0.75f, 1.25f)};
}
void ib_vapeur(float (*buf)[64], const IbBouffee *b, int n, float t, float x, float y, float haut, float vitesse,
               float larg, float vent, float force) {
  for (int i = 0; i < n; i++) {
    const float age = fmodf(b[i].ph + t * vitesse * b[i].vv, 1.0f);
    const float ys = y - age * haut;
    const float ondule = sinf(age * 7 + b[i].pp + t * 0.8f) * (0.4f + age * larg)
                         + sinf(age * 3.1f - t * 0.5f + b[i].pp * 2) * age * 1.5f;
    const float xs = x + b[i].dx * larg * 0.35f + vent * age * sqrtf(age) * haut / 10 + ondule;
    const float s = fmaxf(0.0f, sinf(3.1415927f * fminf(age * 1.6f, 1.0f)));
    const float a = powf(s, 0.7f) * powf(1 - age, 1.3f) * force;
    ib_tampon(buf, ys, xs, a);
    if (age > 0.25f) {                                   // en montant, la bouffee s'etale sur ses voisins
      const float w = a * borne(age * 1.2f - 0.2f, 0, 0.6f);
      ib_tampon(buf, ys, xs - 1, w);
      ib_tampon(buf, ys, xs + 1, w);
      ib_tampon(buf, ys - 1, xs, w);
    }
  }
}
// la vapeur tramee a part (_tramer de sa propre image), ajoutee par-dessus : couleur = min(v, plafond) * teinte
inline void ib_vapeur_pixel(float v, float plafond, float r, float g, float b, int y, int x) {
  if (v <= 0) return;
  const float k = fminf(v, plafond);
  const float cr = borne(k * r, 0, 255), cg = borne(k * g, 0, 255), cb = borne(k * b, 0, 255);
  const float m = fmaxf(cr, fmaxf(cg, cb));
  if (m <= 0) return;
  const float q = ib_marche(m, y, x);
  ajouter(y, x, q, cr, cg, cb);
}

inline float ib_mod(float a, float m) { return a - floorf(a / m) * m; }   // le % de python (toujours positif)
inline int ib_rond(float v) { return (int)floorf(v + 0.5f); }

// --- 1. L'echoppe de ramen sous la bruine (_scene_ramen) ---------------------------------------------------------
// humeurs : 0 = -

const int IB_RAMEN_SOL = 52;
static const char *const IB_RAMEN_NOREN[4][3] = {
    {"www", "..w", ".w."}, {"...", "www", "..."}, {"w..", ".w.", "w.w"}, {"w..", "..w", "ww."}};
static const char *const IB_RAMEN_TETE[] = {"..rrr..", ".rhhhr.", ".hhhhh.", ".hhhhh.", "..hhh.."};
static const char *const IB_RAMEN_DOS[] = {
    "....nnn....", "..rjjjjjr..", ".rjjjjjjjq.", ".jjjjjjjjq.", ".jjjjjjjjq.", ".jjjjjjjjq.", "..jjjjjjq..",
    "..jjjjjjq..", "..jjjjjjq..", "..jjjjjjq..", "..ppppppp..", "..ppppppp.."};
static const char *const IB_RAMEN_CUISINIER[] = {
    "..cccc..", ".wwwwwwh", "..pppp.h", "..oppo..", "...oo...", ".jjjjjj.", "jjjaajjj", "jJjaajJj",
    "jJaaaaJj", "jJaaaaJj", "jJaaaaJj", "jJaaaaJj", "jJaaaaJj", "jJaaaaJj", "jJaaaaJj", "jJaaaaJj"};
static const char *const IB_RAMEN_LANTERNE[] = {".kkk.", "rRRRr", "RLLLR", "RLWLR", "rLWLr",
                                                "RLWLR", "RLLLR", "rRRRr", ".kkk.", "..t.."};

struct E_ramen {
  IbDecor d;
  uint8_t sol[64 - IB_RAMEN_SOL][64][3];   // la flaque et le reflet de l'interieur sur la chaussee
  uint8_t eclair[64][64];                  // l'eclairage (x255) : il colore la vapeur
  float vap[64][64];
  IbBouffee marmite[56], bol[8];
  float bx[46], by[46], bv[46];            // la bruine
};

void ib_ramen_decor(E_ramen &e) {
  const int S = IB_RAMEN_SOL;
  IbDecor &d = e.d;
  const IbC c1 = ib_niv(8, 9, 20, 1);                          // le ciel de la ville, sa lueur derriere les toits
  degrade2(c1.r, c1.v, c1.b, 15, 13, 28, 0, 18);
  static const int IMM[8][3] = {{0, 4, 10}, {4, 11, 15}, {11, 20, 5}, {20, 30, 7}, {30, 41, 3}, {41, 49, 6},
                                {49, 56, 9}, {56, 64, 4}};
  const IbC im = ib_niv(8, 8, 14, 1);                          // les immeubles du fond, en silhouette
  for (int i = 0; i < 8; i++)
    for (int y = IMM[i][2]; y < S; y++)
      for (int x = IMM[i][0]; x < IMM[i][1]; x++) peindre(y, x, im.r, im.v, im.b);
  static const int FEN[23][3] = {{13, 1, 0}, {19, 1, 2}, {25, 1, 0}, {18, 6, 1}, {18, 8, 2}, {24, 6, 0},
                                 {24, 8, 0}, {30, 8, 2}, {36, 6, 1}, {8, 14, 0}, {8, 17, 2}, {9, 24, 1},
                                 {9, 27, 0}, {5, 34, 2}, {5, 37, 0}, {8, 44, 1}, {11, 51, 0}, {7, 58, 0},
                                 {7, 61, 2}, {13, 58, 2}, {13, 61, 1}, {19, 61, 0}, {25, 58, 0}};
  static const float FC[3][3] = {{110, 74, 34}, {46, 60, 104}, {24, 20, 26}};
  for (int i = 0; i < 23; i++)                                 // des fenetres, quelques-unes allumees
    for (int k = 0; k < 2; k++) {
      const float *c = FC[FEN[i][2]];
      peindre(FEN[i][0] + k, FEN[i][1], c[0], c[1], c[2]);
    }
  const IbC ch = ib_niv(10, 10, 16, 2);                        // la chaussee mouillee
  for (int y = S; y < 64; y++)
    for (int x = 0; x < 64; x++) peindre(y, x, ch.r, ch.v, ch.b);
  const IbC mb = ib_niv(40, 24, 14, 2);                        // l'interieur : le mur sous l'ampoule
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const bool dedans = x >= 10 && x <= 48 && y >= 13 && y <= 34;
      // l'eclairage : le mur (si dedans) et la flaque de lumiere (partout)
      float mur = 0;
      if (dedans) {
        const float h = ib_halo_val(x, y, 29, 11, 7.5f, 1.0f) * 1.3f;
        const float r = mb.r + h * 255, g = mb.v + h * 160, b = mb.b + h * 76;
        peindre(y, x, r, g, b);
        mur = fmaxf(r, fmaxf(g, b));
      }
      const float hs = ib_halo_val(x, y, 29, (float)S, 9, 2.4f) * 0.75f;
      float sr = hs * 255, sg = hs * 140, sb = hs * 60;
      if (y >= S) {
        const float ax = borne(1 - fabsf(x - 29.0f) / 21, 0, 1);
        const float refl = expf(-(y - S) / 6.0f) * (ax > 0 ? powf(ax, 0.7f) : 0);
        sr += refl * 150 * 0.9f; sg += refl * 86 * 0.9f; sb += refl * 40 * 0.9f;
        e.sol[y - S][x][0] = ib_octet(sr); e.sol[y - S][x][1] = ib_octet(sg); e.sol[y - S][x][2] = ib_octet(sb);
      }
      const float ecl = (dedans ? borne(mur / 190, 0, 1) : 0) + borne(fmaxf(sr, fmaxf(sg, sb)) / 60, 0, 1) * 0.4f;
      e.eclair[y][x] = ib_octet(ecl * 255);
    }
  for (int x = 6; x < 53; x++) {                               // le comptoir : son dessus eclaire, sa facade
    const float k = 0.5f + 0.5f * expf(-fabsf(x - 29.0f) / 13);
    peindre(35, x, 180 * k, 116 * k, 62 * k);
  }
  const IbC c36 = ib_niv(34, 20, 13, 2), cf = ib_niv(36, 22, 15, 2), cd = ib_niv(14, 10, 12, 1);
  for (int x = 6; x < 53; x++) peindre(36, x, c36.r, c36.v, c36.b);
  for (int y = 37; y < 47; y++)
    for (int x = 8; x < 51; x++) peindre(y, x, cf.r, cf.v, cf.b);
  for (int y = 47; y < S; y++)
    for (int x = 8; x < 51; x++) peindre(y, x, cd.r, cd.v, cd.b);
  ib_garder_lumiere(d);
  // le calque net : toit, poteaux, rideaux, etagere, marmite, roues, tabourets, parapluie
  static const int TOIT[5][6] = {{9, 11, 47, 34, 22, 18}, {10, 9, 49, 44, 28, 21}, {11, 7, 51, 52, 33, 24},
                                 {12, 6, 52, 118, 72, 40}, {13, 9, 49, 56, 32, 20}};
  for (int i = 0; i < 5; i++) ib_net_rect(d, TOIT[i][0], TOIT[i][0], TOIT[i][1], TOIT[i][2], TOIT[i][3], TOIT[i][4], TOIT[i][5]);
  for (int x = 13; x <= 47; x += 4) ib_net(d, 9, x, 60, 40, 30);   // les planches du toit
  ib_net_rect(d, 12, 12, 52, 54, 70, 44, 28);                 // le bras qui porte la lanterne
  ib_net_rect(d, 13, 36, 9, 9, 30, 19, 14);
  ib_net_rect(d, 13, 36, 49, 49, 30, 19, 14);
  for (int i = 0; i < 4; i++) {                                // les noren : quatre pans d'indigo
    const int x0 = 10 + i * 10;
    ib_net_rect(d, 14, 18, x0, x0 + 8, 24, 26, 62);
    ib_net_rect(d, 17, 18, x0, x0 + 8, 34, 36, 84);           // le bas, que la lampe traverse
    for (int x = x0 + 1; x <= x0 + 8; x += 3) ib_net(d, 18, x, 44, 46, 102);
    for (int gy = 0; gy < 3; gy++)
      for (int gx = 0; gx < 3; gx++)
        if (IB_RAMEN_NOREN[i][gy][gx] == 'w') ib_net(d, 15 + gy, x0 + 3 + gx, 190, 178, 156);
  }
  ib_net_rect(d, 25, 25, 10, 48, 46, 27, 17);                 // l'etagere et ses bols
  static const int BOLS[5][2] = {{11, 2}, {13, 3}, {40, 2}, {42, 3}, {45, 2}};
  for (int i = 0; i < 5; i++) {
    ib_net_rect(d, 25 - BOLS[i][1], 24, BOLS[i][0], BOLS[i][0] + 1, 190, 170, 140);
    ib_net_rect(d, 25 - BOLS[i][1], 25 - BOLS[i][1], BOLS[i][0], BOLS[i][0] + 1, 226, 210, 182);
  }
  for (int x = 36; x < 48; x += 2) {                          // le menu : des fiches de bois au mur
    ib_net_rect(d, 19, 22, x, x, 170, 142, 98);
    ib_net(d, 20 + (x / 2) % 2, x, 74, 42, 26);
  }
  for (int y = 28; y <= 34; y++)                               // la grande marmite
    for (int x = 0; x < 64; x++) {
      if (fabsf(x - 16.0f) > 4.5f - (y >= 33)) continue;
      float r = 62, g = 62, b = 68;
      if (x <= 13) { r = 134; g = 130; b = 124; }              // son flanc qui prend la lampe
      if (x == 14) { r = 96; g = 94; b = 96; }
      if (y == 30) { r = 44; g = 44; b = 50; }
      ib_net(d, y, x, r, g, b);
    }
  ib_net_rect(d, 28, 28, 11, 21, 204, 194, 172);               // le bord, brillant
  ib_net_rect(d, 27, 27, 13, 19, 90, 88, 90);
  ib_net(d, 26, 21, 150, 146, 140);                            // le manche de la louche
  ib_net(d, 25, 22, 150, 146, 140);
  for (int x = 8; x <= 50; x += 7) ib_net_rect(d, 37, 46, x, x, 20, 12, 9);
  ib_net_rect(d, 41, 41, 8, 50, 24, 15, 11);
  for (int k = 0; k < 2; k++) {                                // les roues
    const float rx = k ? 43.5f : 14.5f;
    for (int y = 44; y <= 53; y++)
      for (int x = (int)rx - 4; x <= (int)rx + 5; x++) {
        const float dd = sqrtf((x - rx) * (x - rx) + (y - 49.0f) * (y - 49.0f));
        if (dd <= 3.6f && dd >= 2.4f) {
          if (y <= 47) ib_net(d, y, x, 70, 46, 31);
          else ib_net(d, y, x, 44, 29, 21);
        }
        if (dd < 1.0f) ib_net(d, y, x, 58, 38, 27);
      }
  }
  for (int k = 0; k < 2; k++) {                                // les tabourets
    const int sx = k ? 35 : 17;
    ib_net_rect(d, 44, S - 1, sx + 1, sx + 1, 56, 35, 24);
    ib_net_rect(d, 44, S - 1, sx + 5, sx + 5, 56, 35, 24);
    ib_net_rect(d, 43, 43, sx, sx + 6, 104, 66, 40);
  }
  ib_trait(53, 39, 55, S - 1, 30, 30, 52, &d);               // un parapluie ferme, appuye au comptoir
  ib_trait(54, 40, 55, 46, 44, 44, 76, &d);
  ib_net(d, 38, 52, 70, 52, 40);
  ib_net(d, 37, 52, 70, 52, 40);
  ib_net(d, 37, 51, 70, 52, 40);
}

// le cuisinier derriere le comptoir : il remue la marmite, egoutte les nouilles, essuie le comptoir
void ib_ramen_cuisinier(float t) {
  const int cx = 25, hy = 19;
  static const IbPal PAL[] = {{'c', 24, 17, 15}, {'w', 228, 222, 206}, {'h', 184, 178, 164}, {'p', 218, 162, 114},
                              {'o', 160, 106, 72}, {'j', 182, 172, 150}, {'J', 130, 120, 104}, {'a', 36, 38, 76}};
  const float ph = ib_mod(t / 30.0f, 1.0f);                     // son cycle : 30 s
  float mgx, mgy, mdx, mdy;
  int outil = 0, regard = 0;                                   // 1 louche, 2 tamis, 3 torchon
  if (ph < 0.38f) {                                            // il remue le bouillon a la louche
    const float a = t * 2.2f;
    mgx = 20.5f + 1.4f * cosf(a); mgy = 26.0f + 0.6f * sinf(a);
    mdx = cx + 7; mdy = hy + 15;
    outil = 1; regard = 1;
  } else if (ph < 0.55f) {                                     // il egoutte les nouilles, d'un coup sec
    mgx = 20; mgy = ib_mod(t * 2.6f, 1.0f) < 0.5f ? 21 : 23.4f;
    mdx = cx + 7; mdy = hy + 15;
    outil = 2; regard = 1;
  } else if (ph < 0.84f) {                                     // il essuie le comptoir, d'un geste lent
    mgx = cx; mgy = hy + 15;
    mdx = cx + 10 + 3.0f * sinf(t * 1.2f); mdy = hy + 15;
    outil = 3;
  } else {                                                     // il souffle, les mains sur le comptoir
    mgx = cx - 1; mgy = hy + 15;
    mdx = cx + 8; mdy = hy + 15;
  }
  ib_sprite(IB_RAMEN_CUISINIER, cx, hy, PAL);
  if (regard) {                                                // la tete tournee vers la marmite
    poser(hy + 2, cx + 5, 160, 106, 72);
    poser(hy + 3, cx + 5, 160, 106, 72);
  }
  const float ep[2][2] = {{(float)cx, hy + 6.0f}, {cx + 7.0f, hy + 6.0f}}, main_[2][2] = {{mgx, mgy}, {mdx, mdy}};
  for (int k = 0; k < 2; k++) {
    const float sx = ep[k][0], sy = ep[k][1], mx = main_[k][0], my = main_[k][1];
    const float ex = sx + (mx - sx) * 0.4f + (mx < sx ? -1 : 1);
    const float ey = sy + fmaxf(3.0f, (my - sy) * 0.6f);
    ib_trait(sx, sy, ex, ey, 176, 166, 146);
    ib_trait(ex, ey, mx, my, 176, 166, 146);
    poser(ib_rond(my), ib_rond(mx), 218, 162, 114);
  }
  const int mx = ib_rond(outil == 3 || outil == 0 ? mdx : mgx), my = ib_rond(outil == 3 || outil == 0 ? mdy : mgy);
  if (outil == 1) {
    ib_trait(mx, my + 1, mx - 1, my + 3, 176, 172, 164);
  } else if (outil == 2) {
    ib_trait(mx - 1, my + 1, mx - 2, my + 2, 150, 140, 120);
    poser(my + 3, mx - 3, 208, 192, 150); poser(my + 3, mx - 2, 208, 192, 150); poser(my + 4, mx - 3, 208, 192, 150);
  } else if (outil == 3) {
    poser(my, mx - 1, 222, 218, 202); poser(my, mx + 1, 222, 218, 202);
  }
}

// le client, de dos sur son tabouret : il pioche, porte les baguettes a la bouche, boit le bouillon
void ib_ramen_client(float t, float rouge) {
  const int x0 = 33, y0 = 29;
  const float qr = 40 + 150 * rouge, qv = 46 + 40 * rouge, qb = 50 + 26 * rouge;
  const IbPal pal[] = {{'h', 16, 13, 16}, {'r', 150, 96, 54}, {'n', 24, 36, 40}, {'j', 30, 46, 50}, {'q', qr, qv, qb},
                       {'p', 18, 18, 26}};
  const float cyc = t / 6.0f, ph = ib_mod(cyc, 1.0f);
  const int n = (int)floorf(cyc);
  int dy = 0, nc = 0, coudes[2][2];
  if (n % 5 == 2) {                                            // il leve le bol a deux mains, et boit
    if (ph > 0.12f && ph < 0.8f) {
      dy = -1;
      coudes[0][0] = x0; coudes[0][1] = y0 + 2; coudes[1][0] = x0 + 10; coudes[1][1] = y0 + 2; nc = 2;
    }
  } else if (ph < 0.14f || (ph > 0.40f && ph < 0.54f)) {       // il pioche dans le bol
    dy = 1;
    coudes[0][0] = x0 + 10; coudes[0][1] = y0 + 4; nc = 1;
  } else if (ph < 0.28f || (ph > 0.54f && ph < 0.68f)) {       // les baguettes a la bouche
    coudes[0][0] = x0 + 10; coudes[0][1] = y0 + 2; nc = 1;
  }
  ib_sprite(IB_RAMEN_DOS, x0, y0, pal);
  ib_sprite(IB_RAMEN_TETE, x0 + 2, y0 - 5 + dy, pal);
  for (int k = 0; k < nc; k++) {
    const int cx = coudes[k][0], cy = coudes[k][1];
    poser(cy, cx, 30, 46, 50);
    poser(cy + 1, cx, 30, 46, 50);
    if (cx > x0 + 5) poser(cy - 1, cx, qr, qv, qb);
    else poser(cy - 1, cx, 150, 96, 54);
  }
}

void s_ramen(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ramen &e = etat_ecran<E_ramen>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const int S = IB_RAMEN_SOL;
  if (debut) {
    ib_ramen_decor(e);
    ib_semer_vapeur(e.marmite, 56);
    ib_semer_vapeur(e.bol, 8);
    for (int i = 0; i < 46; i++) { e.bx[i] = hasard(0, 64); e.by[i] = hasard(0, 72); e.bv[i] = hasard(0.8f, 1.2f); }
  }
  const float theta = 0.17f * sinf(t * 0.83f) + 0.06f * sinf(t * 1.91f + 1.3f);   // la lanterne : un pendule lent
  const float piv_x = 53.5f, piv_y = 12.0f, st = sinf(theta), ct = cosf(theta);
  const float lx = piv_x + st * 7.5f, ly = piv_y + ct * 7.5f;
  const float souffle = 0.92f + 0.05f * sinf(t * 2.3f) + 0.03f * sinf(t * 5.1f);  // la bougie dedans respire
  ib_poser_fond(e.d);
  halo(lx, ly, 5.0f, 255, 70, 36, 0.8f * souffle);
  float onde[64];                                              // des rides lentes cassent les reflets
  for (int x = 0; x < 64; x++) onde[x] = sinf(x * 0.3f + t * 0.4f) * 1.5f;
  for (int y = S; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float rides = 0.62f + 0.38f * sinf(y * 1.7f - t * 1.1f + onde[x]);
      const float l = ib_halo_val(x, y, lx, S + 1.0f, 4.5f, 2.5f) * 0.35f * souffle   // sa flaque, son reflet
                      + ib_halo_val(x, y, lx, S + 6.0f, 2.0f, 0.22f) * 0.30f * souffle;
      const uint8_t *s = e.sol[y - S][x];
      ajouter(y, x, rides, l * 255 + s[0], l * 60 + s[1], l * 30 + s[2]);
    }
  ib_composer(e.d);
  const float rouge = souffle * borne(1.1f - fabsf(lx - 53.5f) * 0.08f, 0, 1);
  ib_ramen_cuisinier(t);
  ib_ramen_client(t, rouge);
  const IbPal pal[] = {{'r', 168 * souffle, 34 * souffle, 26 * souffle}, {'R', 232 * souffle, 58 * souffle, 38 * souffle},
                       {'L', 255 * souffle, 132 * souffle, 70 * souffle}, {'W', 255 * souffle, 196 * souffle, 120 * souffle},
                       {'k', 34, 14, 12}, {'t', 150, 30, 24}};
  const float hx = piv_x - 2.5f + st * 7.5f, hy = piv_y + 3 * ct;
  ib_trait(piv_x - 0.5f, piv_y + 1, ib_rond(hx) + 2, ib_rond(hy) - 1, 64, 42, 34);   // la ficelle
  ib_sprite(IB_RAMEN_LANTERNE, hx, hy, pal);
  // la vapeur : la marmite, le bol du client ; tramee a part, ajoutee par-dessus
  memset(e.vap, 0, sizeof e.vap);
  ib_vapeur(e.vap, e.marmite, 56, t, 16.0f, 27.0f, 30, 0.17f, 3.2f, 5.0f, 2.4f);
  ib_vapeur(e.vap, e.bol, 8, t, 38.5f, 25.0f, 9, 0.26f, 1.0f, 1.5f, 0.5f);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float k = e.eclair[y][x] * (1.0f / 255);           // la lampe la colore
      ib_vapeur_pixel(e.vap[y][x], 1.3f, 84 + 160 * k, 82 + 130 * k, 86 + 100 * k, y, x);
    }
  // la bruine : de fins traits, qu'on ne voit que dans la lumiere ; une eclaboussure ou elle touche. L'eclat
  // de la scene est lu avant de poser la premiere goutte, comme en numpy
  int gy[46][2], gx[46][2], ey[46], ex[46];
  float lu[46][2], le[46];
  for (int i = 0; i < 46; i++) {
    const float yy = ib_mod(e.by[i] + t * 26 * e.bv[i], 72.0f) - 4, xx = ib_mod(e.bx[i] - t * 3.0f * e.bv[i], 64.0f);
    const int pied = S + 1 + i % 11;
    for (int k = 0; k < 2; k++) {
      gy[i][k] = ib_rond(yy - k);
      gx[i][k] = ib_rond(xx + k * 0.12f) & 63;
      lu[i][k] = -1;
      if (gy[i][k] >= 0 && gy[i][k] < pied) {
        const float *p = scene[gy[i][k]][gx[i][k]];
        lu[i][k] = borne(fmaxf(p[0], fmaxf(p[1], p[2])), 0, 255);
      }
    }
    le[i] = -1;
    if (yy >= pied && yy < pied + 3) {
      ey[i] = pied;
      ex[i] = ib_rond(xx) & 63;
      const float *p = scene[pied][ex[i]];
      le[i] = borne(fmaxf(p[0], fmaxf(p[1], p[2])), 0, 255);
    }
  }
  for (int k = 0; k < 2; k++)
    for (int i = 0; i < 46; i++)
      if (lu[i][k] >= 0) {
        const float l = lu[i][k] * 0.42f;
        ajouter(gy[i][k], gx[i][k], k ? 0.55f : 1.0f, 16 + l, 18 + l, 26 + l);
      }
  for (int i = 0; i < 46; i++)
    if (le[i] >= 0) {
      const float l = le[i] * 0.5f;
      pointer(ey[i] - 1, ex[i] - 1, 20 + l, 20 + l, 28 + l);
      pointer(ey[i] - 1, ex[i] + 1, 20 + l, 20 + l, 28 + l);
    }
}

// --- 2. La laverie automatique, vue du trottoir (_scene_laverie) ------------------------------------------------
// humeurs : 0 = -

const int IB_LAV_SOL = 43;
static const int IB_LAV_X[4] = {6, 15, 24, 33};
static const float IB_LAV_LINGE[8][3] = {{200, 62, 60}, {214, 170, 62}, {84, 146, 214}, {222, 220, 212},
                                         {86, 164, 104}, {214, 110, 170}, {120, 90, 190}, {60, 190, 196}};
static const char *const IB_LAV_DEBOUT[] = {"...hhh.", "..hhhhh", ".sshhhh", "..sshh.", "...cc..", "..cccc.",
                                            "..cacc.", "..cacc.", "..cmcc.", "..jjjj.", "..jjjj.", "...jj..",
                                            "...jj..", "...jj..", "...jj..", "..kkk.."};
static const char *const IB_LAV_MARCHE[] = {"...hhh.", "..hhhhh", ".sshhhh", "..sshh.", "...cc..", "..cccc.",
                                            "..cacc.", "..cacc.", "..cmcc.", "..jjjj.", "..jjjj.", "..j..j.",
                                            ".jj..jj", ".j....j", "jj....j", "kk....k"};
static const char *const IB_LAV_ASSISE[] = {"....hhh.", "...hhhhh", "..sshhhh", "...sshh.", "....cc..", "...cccc.",
                                            "...cacc.", "...cacc.", "...jjjjj", ".jjjjjjj", ".jj.....", ".jj.....",
                                            ".jj.....", "kkk....."};
static const char *const IB_LAV_ACCROUPIE[] = {"...hhh.", "..hhhhh", ".sshhhh", "..sshh.", "...cc..", "..ccccc",
                                               "..caccc", "..jjjjj", ".jjj.jj", ".jj..jj", "kkk.kkk"};
static const char *const IB_LAV_CHAT[] = {"k...k..", "kkkkk..", "kkkkk..", ".kkk...", "kkkkk..", "kkkkkk.", "kkkkkk."};

enum { IB_LIT, IB_PLIE, IB_DEBOUT, IB_MARCHE, IB_TEND, IB_ACCROUPIE, IB_RIEN };

// l'histoire de la cliente sur un cycle de 200 s, en fonction de t seul (_ib_lav_histoire)
struct IbLavH {
  int pose, sens;
  float x, ph, lave, seche, bras, panier, sac;
  bool lave_tourne, essore_l, fini_l, seche_tourne, fini_s, porte_l, porte_s, tient_sac, tient_panier;
};
inline float ib_rampe(float ph, float a, float b, float v0, float v1) {
  return v0 + (v1 - v0) * borne((ph - a) / (b - a), 0, 1);
}
// se lever, marcher jusqu'a dest, ..., revenir s'asseoir (IB_RIEN : elle est arrivee, a la scene de choisir)
void ib_lav_aller(float ph, float debut, float dest, float retour, float fin, IbLavH &h) {
  const float duree = fabsf(46 - dest) / 5;
  h.sens = -1;
  if (ph < debut + 1.2f) { h.pose = IB_DEBOUT; h.x = 46; }
  else if (ph < debut + 1.2f + duree) { h.pose = IB_MARCHE; h.x = 46 + (dest - 46) * (ph - debut - 1.2f) / duree; }
  else if (ph < retour) { h.pose = IB_RIEN; h.x = dest; }
  else if (ph < retour + duree) { h.pose = IB_MARCHE; h.x = dest + (46 - dest) * (ph - retour) / duree; h.sens = 1; }
  else if (ph < fin) { h.pose = IB_DEBOUT; h.x = 46; }
  else { h.pose = IB_LIT; h.x = 46; }
}
IbLavH ib_lav_histoire(float t) {
  IbLavH h = {};
  const float ph = ib_mod(t, 200.0f);
  h.ph = ph;
  // C [0, 22) : elle charge le lave-linge 2 ; A [72, 94) : du lave-linge au sechoir ; B [150, 170) : elle vide
  // le sechoir dans le panier ; puis elle plie et range dans le sac [170, 196)
  h.sac = ph < 100 ? ib_rampe(ph, 7, 13, 1, 0) : ib_rampe(ph, 172, 192, 0, 1);
  h.lave = ib_rampe(ph, 7, 13, 0, 1) - ib_rampe(ph, 77, 82, 0, 1);
  h.bras = ib_rampe(ph, 77, 82, 0, 1) - ib_rampe(ph, 84, 87, 0, 1);
  h.seche = ib_rampe(ph, 84, 87, 0, 1) - ib_rampe(ph, 156, 161, 0, 1);
  h.panier = ib_rampe(ph, 156, 161, 0, 1) - ib_rampe(ph, 172, 192, 0, 1);
  h.lave_tourne = ph > 14.5f && ph < 64;
  h.essore_l = ph > 56 && ph < 64;
  h.fini_l = ph >= 64 && ph < 76.5f;
  h.seche_tourne = ph > 88 && ph < 142;
  h.fini_s = ph >= 142 && ph < 155.5f;
  if (ph < 22) {
    ib_lav_aller(ph, 0, 31, 15, 20.5f, h);
    if (h.pose == IB_RIEN) h.pose = ph < 14 ? IB_ACCROUPIE : IB_DEBOUT;
    h.porte_l = ph > 6.5f && ph < 13.5f;
    h.tient_sac = ph < 7;
  } else if (ph >= 72 && ph < 94) {
    ib_lav_aller(ph, 72, 31, 88, 93.5f, h);
    if (h.pose == IB_RIEN) h.pose = ph < 82.5f ? IB_ACCROUPIE : IB_TEND;
    h.porte_l = ph > 76.5f && ph < 82.5f;
    h.porte_s = ph > 83.5f && ph < 87.5f;
  } else if (ph >= 150 && ph < 170) {
    ib_lav_aller(ph, 150, 31, 162, 168.5f, h);
    if (h.pose == IB_RIEN) h.pose = ph < 161.2f ? IB_TEND : IB_DEBOUT;
    h.porte_s = ph > 155.5f && ph < 161.2f;
    h.tient_panier = ph > 155 && ph < 168;
  } else {
    h.pose = ph < 196 ? IB_PLIE : IB_LIT;
    h.x = 46;
    h.sens = -1;
  }
  return h;
}

struct IbMachine { float per, ph0, q; uint8_t coul[3]; };
struct E_laverie {
  IbDecor d;               // ici tout le decor fixe, deja trame (le masque est plein)
  IbMachine mach[8];
  int8_t hdy[21], hdx[21];
  float hang[21];          // les pixels d'un hublot et leur angle
};

void ib_lav_decor(E_laverie &e) {
  const int S = IB_LAV_SOL;
  IbDecor &d = e.d;
  const IbC fa = ib_niv(14, 16, 26, 1), mu = ib_niv(84, 100, 106, 4), ca = ib_niv(80, 90, 96, 4);
  const IbC ba = ib_niv(20, 24, 34, 2), tr = ib_niv(16, 18, 26, 2), ch = ib_niv(10, 10, 16, 1), bo = ib_niv(40, 44, 52, 3);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float r = fa.r, g = fa.v, b = fa.b;                    // la facade dans la nuit
      if (x >= 4 && x <= 59 && y >= 11 && y <= S + 1) {       // la vitre : le mur du fond, sous le neon
        if (y >= S - 1) { r = ca.r; g = ca.v; b = ca.b; }    // le carrelage
        else {
          float h = 0;
          for (int k = 0; k < 3; k++) h += ib_halo_val(x, y, 13.0f + 18 * k, 12, 3.2f, 1.0f) * 0.9f;
          r = mu.r + h * 70; g = mu.v + h * 84; b = mu.b + h * 84;
        }
      }
      if (y >= 1 && y <= 8 && x >= 5 && x <= 58) { r = ba.r; g = ba.v; b = ba.b; }   // le bandeau de l'enseigne
      if (y >= 47 && y < 58) {                               // le trottoir, et la vitre posee dessus
        const float el = borne((y - 47) / 9.0f, 0, 1), gauche = 4 - el * 6, droite = 59 + el * 6;
        const float bord = borne(fminf(x - gauche, droite - x) / 3 + 0.3f, 0, 1);
        const float ombre = borne(1 - fabsf(x - 32.0f) / (0.8f + el * 1.5f), 0, 1);
        const float tache = powf(borne(1 - el, 0, 1), 1.6f) * bord * (1 - 0.6f * ombre);
        r = tr.r + tache * 62; g = tr.v + tache * 76; b = tr.b + tache * 80;
      }
      if (y >= 58) { r = ch.r; g = ch.v; b = ch.b; }         // la chaussee, plus bas
      if (y == 58) {                                         // le bord du trottoir
        const float k = 1 + 0.6f * borne(1 - fabsf(x - 32.0f) / 34, 0, 1);
        r = bo.r * k; g = bo.v * k; b = bo.b * k;
      }
      peindre(y, x, r, g, b);
    }
  ib_halo_lignes(17, 5, 2.2f, 60, 170, 230, 0.8f, 1.0f, 0, 10);   // le neon de l'enseigne et sa lueur
  ib_halo_lignes(38, 5, 3.2f, 120, 200, 230, 0.45f, 0.5f, 0, 10);
  ib_garder_lumiere(d);
  // le calque net
  ib_net_rect(d, 10, S + 3, 3, 3, 44, 48, 58);                 // le cadre de la vitrine
  ib_net_rect(d, 10, S + 3, 60, 60, 44, 48, 58);
  ib_net_rect(d, 10, 10, 3, 60, 44, 48, 58);
  ib_net_rect(d, 10, S + 3, 32, 32, 36, 40, 50);
  ib_net_rect(d, S + 2, 46, 3, 60, 30, 32, 40);               // le soubassement
  ib_net_rect(d, 46, 46, 2, 61, 52, 56, 64);
  static const int TUBES[3][2] = {{7, 19}, {24, 38}, {43, 56}};   // les tubes au plafond
  for (int k = 0; k < 3; k++) {
    ib_net_rect(d, 12, 12, TUBES[k][0], TUBES[k][1], 226, 240, 240);
    ib_net_rect(d, 11, 11, TUBES[k][0], TUBES[k][1], 90, 100, 104);
  }
  for (int y = 2; y <= 8; y++)                                // l'enseigne : une machine en neon...
    for (int x = 14; x <= 20; x++) {
      const int dd = max(abs(x - 17), abs(y - 5));
      const float hh = sqrtf((x - 17.0f) * (x - 17.0f) + (y - 5.5f) * (y - 5.5f));
      if (dd == 3 || (hh < 1.6f && hh > 0.6f)) ib_net(d, y, x, 90, 200, 255);
    }
  for (int x = 24; x < 54; x++) {                             // ... et une ecriture penchee, illisible
    const int y = (int)rintf(5 + 1.6f * sinf(x * 1.25f) + 0.5f * sinf(x * 0.4f));
    ib_net(d, y, x, 190, 236, 250);
    if (x == 25 || x == 31 || x == 38 || x == 44 || x == 50) ib_net_rect(d, 2, y, x, x, 190, 236, 250);
  }
  for (int y = S - 1; y <= S + 1; y++)
    for (int x = 4; x <= 59; x++)
      if ((x + y) % 2 == 0) ib_net(d, y, x, 64, 72, 78);
  for (int i = 0; i < 4; i++)                                  // les machines : sechoir sur lave-linge
    for (int k = 0; k < 2; k++) {
      const int mx = IB_LAV_X[i], y0 = k ? 33 : 22;
      ib_net_rect(d, y0, y0 + 9, mx, mx + 7, 168, 176, 180);
      ib_net_rect(d, y0, y0 + 9, mx + 7, mx + 7, 124, 132, 138);
      ib_net_rect(d, y0 + 9, y0 + 9, mx, mx + 7, 110, 118, 124);
      ib_net_rect(d, y0, y0, mx, mx + 7, 196, 204, 206);
      ib_net_rect(d, y0 + 1, y0 + 1, mx + 1, mx + 4, 70, 78, 86);   // le panneau de commande
      for (int y = y0; y <= y0 + 9; y++)                       // le hublot (le verre a part)
        for (int x = mx; x <= mx + 7; x++) {
          const float dd = sqrtf((x - mx - 3.5f) * (x - mx - 3.5f) + (y - y0 - 5.5f) * (y - y0 - 5.5f));
          if (dd <= 3.4f && dd > 2.4f) {
            if (y < y0 + 4 && x < mx + 4) ib_net(d, y, x, 150, 160, 168);
            else ib_net(d, y, x, 96, 104, 112);
          }
        }
    }
  ib_net_rect(d, 32, 32, 5, 41, 60, 66, 72);                  // la tablette entre les deux
  ib_net_rect(d, 37, 37, 44, 58, 120, 92, 64);                // le banc
  ib_net_rect(d, 38, 38, 44, 58, 84, 64, 46);
  ib_net_rect(d, 39, S, 45, 45, 60, 60, 66);
  ib_net_rect(d, 39, S, 57, 57, 60, 60, 66);
  ib_net_rect(d, 21, 24, 41, 43, 214, 206, 160);              // des affichettes au mur
  ib_net_rect(d, 22, 24, 45, 46, 196, 210, 220);
  ib_net_rect(d, 26, 27, 42, 44, 222, 160, 150);
  ib_net(d, 22, 42, 120, 110, 90);
  ib_net_rect(d, S - 3, S, 57, 58, 150, 84, 60);              // une plante en pot
  static const int FEUILLES[8][2] = {{4, 57}, {5, 58}, {6, 57}, {5, 56}, {7, 58}, {4, 59}, {8, 57}, {6, 59}};
  for (int k = 0; k < 8; k++) ib_net(d, S - FEUILLES[k][0], FEUILLES[k][1], 70, 140, 84);
  for (int y = 16; y <= 22; y++)                               // l'horloge
    for (int x = 49; x <= 55; x++) {
      const float dd = sqrtf((x - 52.0f) * (x - 52.0f) + (y - 19.0f) * (y - 19.0f));
      if (dd <= 1.9f) ib_net(d, y, x, 210, 214, 210);
      else if (dd <= 2.6f) ib_net(d, y, x, 60, 64, 70);
    }
  // tout est fixe : la trame une fois pour toutes, les reflets obliques sur la vitre, et le tout dans le fond
  ib_poser_fond(d);
  ib_composer(d);
  for (int y = 11; y < 24; y++)
    for (int x = 37; x <= 59; x++)
      if (x + y == 66 || x + y == 68 || x + y == 71) ajouter(y, x, 1, 14, 14, 14);
  ib_garder_lumiere(d);
  for (int y = 0; y < 64; y++) d.masque[y] = ~0ull;
  for (int i = 0; i < 8; i++) {
    e.mach[i] = {hasard(38, 70), hasard(0, 1), 0, {0, 0, 0}};
    for (int k = 0; k < 3; k++) e.mach[i].coul[k] = aleatoire() % 8;
    e.mach[i].q = hasard(0.55f, 0.9f);
  }
  int n = 0;
  for (int dy = -3; dy <= 3; dy++)
    for (int dx = -3; dx <= 3; dx++)
      if (dx * dx + dy * dy <= 5.3f) { e.hdy[n] = dy; e.hdx[n] = dx; e.hang[n] = atan2f((float)dy, (float)dx); n++; }
}

// le hublot d'une machine : le linge qui tourne (mode 1), essore (2), repose (0) ; ou la porte ouverte
void ib_lav_hublot(const E_laverie &e, int mx, int y0, float q, int mode, const uint8_t *couleurs, float t,
                   bool ouvert) {
  const int cx = mx + 3, cy = y0 + 5;
  float phi = 0, w = 0;
  if (mode == 1) { phi = 0.55f * sinf(t * 0.7f) + 0.6f; w = t * 2.6f; }   // le tas penche dans le sens du tambour
  else if (mode == 2) w = t * 9.0f;
  const float niveau = 1.6f - 3.6f * q, cp = cosf(phi), sp = sinf(phi);
  float moy[3] = {0, 0, 0};
  for (int k = 0; k < 3; k++)
    for (int c = 0; c < 3; c++) moy[c] += IB_LAV_LINGE[couleurs[k]][c] / 3;
  const float kc = ouvert ? 0.85f : 0.72f;
  for (int i = 0; i < 21; i++) {
    const int dy = e.hdy[i], dx = e.hdx[i];
    const bool haut = mode == 2 ? (dx * dx + dy * dy >= 2.5f && q > 0.05f) : dy * cp - dx * sp >= niveau;
    if (haut) {
      const int k = (int)floorf(ib_mod((e.hang[i] - w) / PI2 * 3, 3.0f));
      const float *c = IB_LAV_LINGE[couleurs[min(k, 2)]];
      if (mode == 2) poser(cy + dy, cx + dx, c[0] * kc * 0.3f + moy[0] * 0.45f, c[1] * kc * 0.3f + moy[1] * 0.45f,
                           c[2] * kc * 0.3f + moy[2] * 0.45f);
      else poser(cy + dy, cx + dx, c[0] * kc, c[1] * kc, c[2] * kc);
    } else if (ouvert) poser(cy + dy, cx + dx, 18, 18, 22);
    else poser(cy + dy, cx + dx, 34, 40, 48);
  }
  if (!ouvert) poser(cy - 2, cx - 1, 206, 222, 230);         // l'eclat sur le verre
  else {                                                      // la porte ouverte, vue de profil
    for (int k = -3; k <= 3; k++) poser(cy + k, cx - 5, 150, 158, 166);
    for (int k = -2; k <= 2; k++) poser(cy + k, cx - 4, 90, 98, 106);
  }
}

void s_laverie(int humeur, bool debut, float t, float ecoule, float dt) {
  E_laverie &e = etat_ecran<E_laverie>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const int S = IB_LAV_SOL;
  if (debut) ib_lav_decor(e);
  const IbLavH h = ib_lav_histoire(t);
  ib_poser_fond(e.d);
  const float sg = sinf(t * 0.21f);                           // le tube de droite gresille, rarement
  if (sg > 0) {
    const float s2 = sg * sg, s4 = s2 * s2, s8 = s4 * s4, s16 = s8 * s8, s32 = s16 * s16;
    const float gres = s32 * s16 * s8 * s4 * (0.5f + 0.5f * sinf(t * 7.0f));
    for (int x = 43; x < 57; x++)
      for (int c = 0; c < 3; c++) scene[12][x][c] *= 1 - 0.45f * gres;
  }
  for (int i = 0; i < 4; i++)                                  // les machines
    for (int j = 0; j < 2; j++) {
      const IbMachine &m = e.mach[i * 2 + j];
      const int mx = IB_LAV_X[i], y0 = j ? 33 : 22;
      float q = m.q, lr = 34, lv = 40, lb = 44;
      int mode = 0;
      bool ouvert = false;
      const uint8_t *coul = m.coul;
      static const uint8_t COUL_L[3] = {0, 2, 1}, COUL_S[3] = {0, 2, 3};
      if (i == 2) {                                            // la paire de la cliente
        const bool tourne = j ? h.lave_tourne : h.seche_tourne, fini = j ? h.fini_l : h.fini_s;
        q = j ? h.lave : h.seche;
        mode = tourne ? (j && h.essore_l ? 2 : 1) : 0;
        ouvert = j ? h.porte_l : h.porte_s;
        if (tourne) { lr = 60; lv = 220; lb = 120; }
        else if (fini) { lr = 255; lv = 150; lb = 40; }
        coul = j ? COUL_L : COUL_S;
      } else if (i == 0 && j == 1) {                           // une machine libre, vide
        q = 0;
      } else {                                                 // les autres tournent, s'arretent, repartent
        const float c = ib_mod(t / m.per + m.ph0, 1.0f);
        mode = c < 0.62f ? 1 : (c < 0.72f ? 2 : 0);
        if (c < 0.72f) { lr = 60; lv = 220; lb = 120; }
        else { lr = 255; lv = 150; lb = 40; }
      }
      if (lr == 255) {
        const float k = 0.75f + 0.25f * sinf(t * 2.2f);
        lr *= k; lv *= k; lb *= k;
      }
      ib_lav_hublot(e, mx, y0, q, mode, coul, t, ouvert);
      poser(y0 + 1, mx + 6, lr, lv, lb);
    }
  // l'horloge (sur la carte, t ne dit pas l'heure : elle tourne quand meme)
  const float hm = ib_mod(t / 3600.0f, 12.0f), am = ib_mod(t / 3600.0f, 1.0f) * PI2, ah = hm / 12 * PI2;
  poser(ib_rond(19 - cosf(ah) * 1.2f), ib_rond(52 + sinf(ah) * 1.2f), 40, 40, 44);
  poser(ib_rond(19 - cosf(am) * 1.9f), ib_rond(52 + sinf(am) * 1.9f), 70, 70, 76);
  poser(19, 52, 40, 40, 44);
  // la cliente, et ce qu'elle porte
  static const IbPal PAL[] = {{'h', 70, 40, 30}, {'s', 214, 168, 132}, {'c', 176, 64, 70}, {'a', 130, 44, 52},
                              {'m', 214, 168, 132}, {'j', 52, 62, 96}, {'k', 30, 30, 34}};
  const float x = h.x;
  if (h.pose == IB_LIT || h.pose == IB_PLIE) {
    ib_sprite(IB_LAV_ASSISE, 45, S - 13, PAL);
    if (h.pose == IB_LIT) {                                    // le livre ouvert, une page tourne parfois
      const bool tourne = ib_mod(t, 9.0f) < 0.5f;
      poser(S - 8, 44, 226, 222, 206);
      if (tourne) poser(S - 8, 45, 240, 236, 220);
      else poser(S - 8, 45, 196, 192, 178);
      poser(S - 7, 44, 60, 90, 140);
      poser(S - 7, 45, 60, 90, 140);
      poser(S - 7, 46, 214, 168, 132);
    } else {                                                   // elle plie : les mains vont et viennent
      const int g = ib_rond(sinf(t * 2.4f));
      const float *c = IB_LAV_LINGE[((int)(t / 2.6f) % 3) * 2 % 8];
      poser(S - 6, 44 + g, c[0], c[1], c[2]);
      poser(S - 6, 45 + g, c[0], c[1], c[2]);
      poser(S - 7, 46 + g, 214, 168, 132);
    }
  } else {
    const bool pas = h.pose == IB_MARCHE && ib_mod(t * 3.2f, 1.0f) < 0.5f;
    if (h.pose == IB_ACCROUPIE) ib_sprite(IB_LAV_ACCROUPIE, x - 1, S - 11 + 1, PAL, h.sens > 0);
    else if (pas) ib_sprite(IB_LAV_MARCHE, x - 1, S - 16 + 1, PAL, h.sens > 0);
    else ib_sprite(IB_LAV_DEBOUT, x - 1, S - 16 + 1, PAL, h.sens > 0);
    if (h.pose == IB_TEND) {                                   // le bras tendu vers le sechoir
      ib_trait(x + 1, S - 11, x - 1, S - 14, 130, 44, 52);
      poser(S - 15, x - 2, 214, 168, 132);
    }
    if (h.pose == IB_ACCROUPIE) poser(S - 5, x - 1, 214, 168, 132);
    if (h.bras > 0.02f || h.tient_panier) {                    // une brassee de linge, ou le panier
      const float bx = h.sens < 0 ? x - 2 : x + 4, by = S - 9;
      const float(*L)[3] = IB_LAV_LINGE;
      if (h.tient_panier) {
        for (int k = -1; k <= 1; k++) { poser(by + 1, bx + k, 110, 170, 210); poser(by + 2, bx + k, 110, 170, 210); }
        poser(by, bx - 1, L[1][0], L[1][1], L[1][2]);
        poser(by, bx + 1, L[3][0], L[3][1], L[3][2]);
      } else {
        poser(by, bx, L[0][0], L[0][1], L[0][2]);
        poser(by, bx + 1, L[2][0], L[2][1], L[2][2]);
        poser(by + 1, bx, L[1][0], L[1][1], L[1][2]);
      }
    }
    if (h.tient_sac) {
      poser(S - 7, x + 4, 170, 150, 110); poser(S - 6, x + 4, 170, 150, 110);
      poser(S - 6, x + 5, 170, 150, 110); poser(S - 5, x + 4, 170, 150, 110);
    }
  }
  if (!h.tient_panier) {                                       // le panier sur le banc, sauf quand elle le porte
    for (int k = 53; k <= 56; k++) { poser(35, k, 110, 170, 210); poser(36, k, 110, 170, 210); }
    static const int ORDRE[4] = {0, 3, 2, 1};
    const int n = ib_rond(h.panier * 4);
    for (int k = 0; k < n; k++) {
      const float *c = IB_LAV_LINGE[ORDRE[k]];
      poser(34, 53 + k, c[0], c[1], c[2]);
    }
  }
  if (!h.tient_sac) {                                          // un sac de toile, plus ou moins plein
    const int hs = ib_rond(1 + h.sac * 3);
    for (int k = 0; k < hs; k++) {
      const int larg = (k > 0 && k < hs - 1) || hs <= 2 ? 3 : 2;
      for (int i = 0; i < larg; i++) {
        if (k < hs - 1) poser(S - k, 54 + i, 170, 150, 110);
        else poser(S - k, 54 + i, 196, 178, 136);
      }
    }
  }
  // le chat, dehors, qui regarde tourner le linge ; sa queue bat lentement
  const int cx = 13, cy = 48;
  static const IbPal CHAT[] = {{'k', 12, 12, 18}};
  ib_sprite(IB_LAV_CHAT, cx, cy, CHAT);
  poser(cy, cx, 110, 128, 134); poser(cy, cx + 4, 110, 128, 134);    // le bord des oreilles, de la tete, eclaire
  for (int k = 1; k <= 3; k++) poser(cy + 1, cx + k, 110, 128, 134);
  poser(cy + 4, cx, 60, 70, 74); poser(cy + 4, cx + 4, 60, 70, 74);
  const float q = sinf(t * 0.9f) + 0.3f * sinf(t * 2.3f);
  poser(cy + 6, cx + 6, 12, 12, 18);
  poser(cy + 5, cx + 7 + (q > 0.2f), 12, 12, 18);
  poser(cy + 4 - (q > 0.8f), cx + 7 + (q > -0.3f), 12, 12, 18);
}

// --- 3. Le petit cafe ouvert tard, vu par-dessus la rue mouillee (_scene_diner) ----------------------------------
// humeurs : 0 = -

const int IB_CAFE_RUE = 50;
static const char *const IB_CAFE_LETTRES[4][5] = {{".www", "w...", "w...", "w...", ".www"},
                                                 {".ww.", "w..w", "wwww", "w..w", "w..w"},
                                                 {"wwww", "w...", "www.", "w...", "w..."},
                                                 {"wwww", "w...", "www.", "w...", "wwww"}};
static const char *const IB_CAFE_TASSE[] = {"..w.w..", ".w.w...", "wwwwww.", "w....ww", "w....w.", ".wwww.."};
static const char *const IB_CAFE_SERVEUR[] = {"..hhh..", ".hhhhh.", ".spsps.", ".sssss.", "..sss..",
                                              ".wwrww.", "wwvvvww", "wwvvvww", "wwvvvww", "wwvvvww"};
static const char *const IB_CAFE_DOS_A[] = {"..hh...", ".hhhh..", ".hhhhh.", ".hhhhh.", "..ss...", ".ccccc.",
                                            "ccccccc", "ccccccc", "ccccccc", ".ccccc.", ".jjjjj."};
static const char *const IB_CAFE_DOS_B[] = {".qqqq..", "qqqqqq.", ".hhhh..", ".hhhh..", "..ss...", "ccccccc",
                                            "ccccccc", "ccccccc", "ccccccc", ".ccccc.", ".jjjjj."};
static const char *const IB_CAFE_PROFIL[] = {"..hhh..", ".hhhhh.", ".hhhss.", "..hsss.", "...ss..", "..cccc.", ".cccccc",
                                             ".ccccc.", ".cccc..", ".jjjjjj", ".jj..jj", ".j....j", ".j....j", "kk...kk"};
static const char *const IB_CAFE_PASSANT[] = {"..hhh..", ".hhhhh.", ".hhhhs.", ".hhhss.", "..ccc..", ".ccccc.",
                                              ".ccccc.", ".ccccc.", ".ccccc.", ".ccccc.", "..jjj..", "..jjj..",
                                              "..j.j..", "..j.j..", "..j.j..", ".kk.kk."};
static const char *const IB_CAFE_PASSANT_PAS[] = {"..hhh..", ".hhhhh.", ".hhhhs.", ".hhhss.", "..ccc..", ".ccccc.",
                                                  ".ccccc.", ".ccccc.", ".ccccc.", ".ccccc.", "..jjj..", "..jjj..",
                                                  ".j...j.", ".j...j.", "j.....j", "k.....k"};
static const char *const IB_CAFE_CHIEN[] = {"....kk", "k..kkk", ".kkkk.", ".k..k."};
static const char *const IB_CAFE_CHIEN_PAS[] = {"....kk", "k..kkk", ".kkkk.", "k....k"};

struct E_diner {
  IbDecor d;
  uint8_t lueur[22][64][3];                        // le halo du neon sur la brique
  uint8_t vitre[64 - IB_CAFE_RUE][64][3];          // le reflet de la vitrine dans la rue mouillee
  uint8_t neon[64 - IB_CAFE_RUE][64][3];           // celui de l'enseigne (rose) et de la tasse (bleue)
  float vap[64][64];
  IbBouffee fen[14], comp[10], tasse[6], perco[8];
  float gp[5], g0[5];                              // les gouttes qui tombent de la marquise
};

void ib_cafe_decor(E_diner &e) {
  const int R = IB_CAFE_RUE;
  IbDecor &d = e.d;
  memset(scene, 0, sizeof scene);                              // d'abord le halo du neon, range a part
  ib_halo_lignes(34, 13, 5, 255, 70, 160, 0.6f, 0.55f, 0, 22);
  ib_halo_lignes(19, 13, 3, 60, 170, 255, 0.5f, 0.8f, 0, 22);
  for (int y = 0; y < 22; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) e.lueur[y][x][c] = ib_octet(scene[y][x][c]);
  // la lumiere : la brique, la fenetre de l'etage, la vitrine chaude, le trottoir, la rue
  const IbC br = ib_niv(30, 16, 20, 2), ci = ib_niv(10, 10, 22, 1), et = ib_niv(150, 96, 50, 4);
  const IbC mu = ib_niv(224, 170, 100, 5), la = ib_niv(150, 90, 50, 4), ca = ib_niv(40, 76, 74, 3);
  const IbC tr = ib_niv(24, 22, 30, 2), bo = ib_niv(60, 50, 54, 3), ru = ib_niv(12, 10, 22, 1);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      IbC c = br;
      if (y < 2) c = ci;
      if (y >= 2 && y < 9 && x >= 46 && x < 53) c = et;
      const bool vitrine = x >= 2 && x <= 48 && y >= 22 && y <= 43, porte = x >= 51 && x <= 58 && y >= 23 && y <= 45;
      if (vitrine || porte) {                                  // le mur du fond, chaud, sous les suspensions
        c = mu;
        for (int k = 0; k < 3; k++) {
          const float lx = 10.0f + 14 * k, dx = x - lx, dy = (y - 27) * 0.9f;
          const float q = 1 - sqrtf(dx * dx + dy * dy) / 7;
          if (q > 0 && x >= (int)lx - 8 && x < (int)lx + 10 && y >= 17 && y < 37) {
            c.r += q * q * 0.75f * 255; c.v += q * q * 0.75f * 200; c.b += q * q * 0.75f * 120;
          }
        }
        if (y >= 33 && y < 37) c = la;                         // le lambris
        if (y == 37) {                                         // le zinc du comptoir
          c = {196, 136, 74};
          for (int k = 0; k < 3; k++)
            if (x >= max(0, 10 + 14 * k - 5) && x < 10 + 14 * k + 6) c = {236, 176, 100};
        }
        if (y >= 38 && y < 44) c = x < 14 ? la : ca;           // la facade du comptoir, carrelee
        if (porte && y >= 38) c = la;
      }
      if (y >= 46 && y < R) {                                  // le trottoir, et la vitrine posee dessus
        const float s = ib_halo_val(x, y, 25, 46, 9, 3.0f) * 0.5f + ib_halo_val(x, y, 55, 46, 4, 3.0f) * 0.4f;
        c = {tr.r + s * 255, tr.v + s * 170, tr.b + s * 90};
      }
      if (y == R - 1) c = bo;                                  // le bord du trottoir
      if (y >= R) c = ru;                                      // la rue mouillee
      peindre(y, x, c.r, c.v, c.b);
    }
  ib_garder_lumiere(d);
  // les reflets : des trainees verticales sous chaque lumiere, que les rides casseront
  float poids[64] = {};
  for (int i = 0; i < 4; i++)
    for (int x = 0; x < 4; x++)
      for (int r = 0; r < 5; r++) poids[25 + i * 6 + x] += IB_CAFE_LETTRES[i][r][x] == 'w';
  for (int y = R; y < 64; y++) {
    const float prof = borne((y - R) / 14.0f, 0, 1), bande = expf(-((y - R - 6) / 5.0f) * ((y - R - 6) / 5.0f));
    for (int x = 0; x < 64; x++) {
      float r = 0, g = 0, b = 0;
      if (x >= 2 && x <= 48) {
        const float k = expf(-prof * 2.2f) * (0.7f + 0.3f * cosf(x * 0.42f));
        r += k * 120; g += k * 76; b += k * 36;
      }
      if (x >= 51 && x <= 58) {
        const float k = expf(-prof * 2.0f);
        r += k * 110; g += k * 70; b += k * 34;
      }
      e.vitre[y - R][x][0] = ib_octet(r); e.vitre[y - R][x][1] = ib_octet(g); e.vitre[y - R][x][2] = ib_octet(b);
      const float kn = poids[x] / 5 * bande, kt = fabsf(x - 19.0f) < 2.5f ? bande : 0;
      e.neon[y - R][x][0] = ib_octet(kn * 255 + kt * 50);
      e.neon[y - R][x][1] = ib_octet(kn * 70 + kt * 150);
      e.neon[y - R][x][2] = ib_octet(kn * 160 + kt * 255);
    }
  }
  // le calque net
  for (int y = 17; y <= 21; y++)                               // la marquise rayee, festonnee
    for (int x = 0; x <= 60; x++) {
      const bool raie = (x / 3) % 2 == 0;
      if (y < 21) {
        if (y == 17) ib_net(d, y, x, raie ? 160 : 216, raie ? 52 : 196, raie ? 66 : 170);
        else ib_net(d, y, x, raie ? 128 : 186, raie ? 32 : 166, raie ? 44 : 140);
      } else if (raie && x % 3 != 2) ib_net(d, y, x, 100, 24, 34);
      else if (!raie && x % 3 == 1) ib_net(d, y, x, 150, 132, 112);
    }
  static const int CADRE[4] = {1, 49, 50, 59};
  for (int k = 0; k < 4; k++) ib_net_rect(d, 22, 45, CADRE[k], CADRE[k], 44, 30, 30);
  ib_net_rect(d, 22, 43, 25, 25, 54, 38, 36);                 // le meneau
  ib_net_rect(d, 44, 45, 1, 49, 36, 22, 24);                  // le soubassement
  ib_net_rect(d, 34, 34, 52, 53, 200, 180, 120);              // la poignee de la porte
  ib_net_rect(d, 2, 8, 45, 45, 40, 26, 26);                   // la fenetre de l'etage
  ib_net_rect(d, 2, 8, 53, 53, 40, 26, 26);
  ib_net_rect(d, 1, 1, 45, 53, 40, 26, 26);
  ib_net_rect(d, 9, 9, 44, 54, 74, 54, 50);                   // son rebord, ses rideaux, un pot de fleurs
  ib_net_rect(d, 2, 8, 46, 46, 110, 40, 44);
  ib_net_rect(d, 2, 8, 52, 52, 110, 40, 44);
  ib_net_rect(d, 2, 4, 47, 47, 110, 40, 44);
  ib_net_rect(d, 2, 4, 51, 51, 110, 40, 44);
  ib_net_rect(d, 8, 8, 48, 50, 60, 36, 30);
  ib_net(d, 7, 48, 40, 90, 50);
  ib_net(d, 7, 50, 40, 90, 50);
  ib_net(d, 6, 49, 200, 90, 110);
  for (int k = 0; k < 3; k++) {                                // les suspensions
    const int lx = 10 + 14 * k;
    ib_net_rect(d, 22, 23, lx, lx, 40, 30, 26);
    ib_net_rect(d, 24, 24, lx - 1, lx + 1, 34, 74, 54);
    ib_net_rect(d, 25, 25, lx - 2, lx + 2, 46, 96, 70);
    ib_net_rect(d, 26, 26, lx - 1, lx + 1, 255, 228, 170);
  }
  ib_net_rect(d, 27, 27, 41, 47, 90, 56, 34);                 // les etageres, leurs tasses et leurs bocaux
  ib_net(d, 26, 42, 230, 222, 206);
  ib_net(d, 26, 44, 230, 222, 206);
  ib_net_rect(d, 25, 26, 46, 46, 200, 160, 70);
  ib_net_rect(d, 27, 27, 14, 20, 90, 56, 34);
  ib_net_rect(d, 25, 26, 15, 15, 150, 90, 60);
  ib_net(d, 26, 17, 230, 222, 206);
  ib_net(d, 26, 19, 230, 222, 206);
  ib_net_rect(d, 30, 36, 33, 38, 150, 150, 158);              // le percolateur, chrome
  ib_net_rect(d, 30, 36, 33, 33, 210, 210, 214);
  ib_net_rect(d, 30, 30, 33, 38, 190, 190, 196);
  ib_net_rect(d, 34, 35, 34, 37, 60, 50, 50);
  ib_net(d, 29, 34, 230, 222, 206);
  ib_net(d, 29, 36, 230, 222, 206);
  ib_net_rect(d, 31, 32, 38, 38, 100, 70, 50);
  ib_net_rect(d, 37, 43, 7, 8, 60, 40, 30);                   // la table de la fenetre
  ib_net_rect(d, 36, 36, 4, 12, 176, 120, 70);
  ib_net_rect(d, 43, 43, 6, 9, 60, 40, 30);
  ib_net_rect(d, 40, 40, 27, 30, 190, 50, 50);                // un tabouret libre
  ib_net_rect(d, 41, 43, 28, 28, 170, 170, 176);
  ib_net_rect(d, 38, 38, 14, 48, 24, 50, 50);                 // l'ombre sous le zinc
  ib_semer_vapeur(e.fen, 14);
  ib_semer_vapeur(e.comp, 10);
  ib_semer_vapeur(e.tasse, 6);
  ib_semer_vapeur(e.perco, 8);
  for (int k = 0; k < 5; k++) { e.gp[k] = hasard(3.5f, 7); e.g0[k] = hasard(0, 1); }
}

// l'enseigne : la tasse bleue, et CAFE en tubes roses qui ronronnent ; le E faiblit parfois, en douceur
void ib_cafe_neon(float t, float ron) {
  const float ph = ib_mod(t / 47.0f, 1.0f);
  const float a = sinf(3.1415927f * borne((ph - 0.5f) / 0.04f, 0, 1)), b = sinf(3.1415927f * borne((ph - 0.56f) / 0.03f, 0, 1));
  const float faible = 1 - 0.55f * a * a - 0.35f * b * b;
  for (int i = 0; i < 4; i++) {
    const float k = ron * (i == 3 ? faible : 1.0f);
    const IbPal pal[] = {{'w', 255 * k, 96 * k, 186 * k}};
    ib_dessin(IB_CAFE_LETTRES[i], 5, 25 + i * 6, 11, pal, 1);
  }
  const IbPal tasse[] = {{'w', 90 * ron, 196 * ron, 255 * ron}};
  ib_sprite(IB_CAFE_TASSE, 16, 10, tasse);
}

// le serveur qui essuie le zinc et sert, deux clients de dos, un client a la fenetre ; rend la place du serveur
// et s'il verse le cafe
int ib_cafe_gens(float t, bool &verse) {
  const float ph = ib_mod(t / 44.0f, 1.0f) * 44;
  float sxf = 23;
  int geste = 0;                                              // 0 marche, 1 essuie, 2 verse, 3 sert, 4 attend
  if (ph < 18) geste = 1;                                      // il essuie, va au percolateur, sert, revient
  else if (ph < 20) sxf = 23 + (ph - 18) / 2 * 4;
  else if (ph < 25) { sxf = 27; geste = 2; }
  else if (ph < 28) sxf = 27 - (ph - 25) / 3 * 8;
  else if (ph < 31) { sxf = 19; geste = 3; }
  else if (ph < 33) sxf = 19 + (ph - 31) / 2 * 4;
  else geste = 4;
  static const IbPal SERV[] = {{'h', 34, 24, 20}, {'s', 220, 170, 126}, {'p', 160, 108, 80}, {'w', 236, 232, 222},
                               {'r', 40, 20, 24}, {'v', 34, 30, 36}};
  const int sx = (int)rintf(sxf);
  ib_sprite(IB_CAFE_SERVEUR, sx, 27, SERV);
  if (geste == 1) {                                            // le torchon va et vient sur le zinc
    const int mx = sx + 3 + (int)rintf(3.2f * sinf(t * 1.4f));
    ib_trait(sx + (mx < sx + 3 ? 0 : 6), 33, mx, 36, 236, 232, 222);
    poser(36, mx - 1, 250, 250, 244);
    poser(36, mx, 250, 250, 244);
  } else if (geste == 2) {                                     // la tasse sous le percolateur
    ib_trait(sx + 6, 33, sx + 7, 35, 236, 232, 222);
    poser(35, sx + 8, 230, 222, 206);
  } else if (geste == 3) {                                     // il pose la tasse pres de la cliente
    ib_trait(sx + 6, 33, sx + 7, 36, 236, 232, 222);
    poser(36, sx + 8, 230, 222, 206);
  } else if (geste == 4) {
    poser(33, sx, 236, 232, 222); poser(34, sx, 236, 232, 222);
    poser(33, sx + 6, 236, 232, 222); poser(34, sx + 6, 236, 232, 222);
  }
  // la cliente A, de dos : elle porte sa tasse a ses levres, tourne la tete vers son voisin
  const float ca = ib_mod(t / 13.0f, 1.0f);
  static const IbPal PA[] = {{'h', 60, 34, 26}, {'s', 200, 150, 110}, {'c', 40, 54, 92}, {'j', 28, 28, 36}};
  ib_sprite(IB_CAFE_DOS_A, 13, 30, PA);
  if (ca > 0.55f && ca < 0.72f) {
    poser(33, 19, 40, 54, 92); poser(34, 19, 40, 54, 92); poser(32, 18, 230, 222, 206);
  } else poser(36, 20, 230, 222, 206);                         // sa tasse sur le zinc
  if (ca > 0.2f && ca < 0.35f) poser(32, 18, 200, 150, 110);   // elle tourne la tete : une joue
  for (int y = 39; y <= 43; y++) poser(y, 16, 170, 170, 176);
  poser(40, 14, 190, 50, 50); poser(40, 18, 190, 50, 50);
  // le client B, de dos, accoude, sa casquette
  static const IbPal PB[] = {{'q', 150, 60, 44}, {'h', 40, 30, 26}, {'s', 190, 140, 100}, {'c', 60, 70, 50},
                             {'j', 30, 30, 34}};
  const int hoche = ib_mod(t / 7.0f, 1.0f) < 0.12f ? 1 : 0;
  ib_dessin(IB_CAFE_DOS_B, 5, 40, 29 + hoche, PB, 5);
  ib_dessin(IB_CAFE_DOS_B + 5, 6, 40, 34, PB, 5);
  poser(36, 47, 60, 70, 50); poser(37, 47, 60, 70, 50);      // son coude sur le zinc
  poser(36, 39, 230, 222, 206);                                // sa tasse
  for (int y = 41; y <= 43; y++) poser(y, 43, 170, 170, 176);
  // le client de la fenetre, de profil : il boit son cafe de temps en temps
  static const IbPal PC[] = {{'h', 90, 80, 70}, {'s', 210, 160, 120}, {'c', 120, 70, 50}, {'j', 40, 40, 50},
                             {'k', 26, 22, 22}};
  ib_sprite(IB_CAFE_PROFIL, 1, 30, PC);
  const float cc = ib_mod(t / 11.0f, 1.0f);
  if (cc > 0.3f && cc < 0.5f) {
    ib_trait(5, 36, 6, 33, 120, 70, 50);
    poser(33, 7, 236, 230, 214);
  } else {
    ib_trait(5, 36, 7, 36, 120, 70, 50);
    poser(35, 9, 236, 230, 214); poser(35, 10, 236, 230, 214);
  }
  verse = geste == 2;
  return sx;
}

void s_diner(int humeur, bool debut, float t, float ecoule, float dt) {
  E_diner &e = etat_ecran<E_diner>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const int R = IB_CAFE_RUE;
  if (debut) ib_cafe_decor(e);
  const float ron = 0.93f + 0.04f * sinf(t * 1.7f) + 0.03f * sinf(t * 6.3f);   // le neon ronronne
  ib_poser_fond(e.d);
  for (int y = 0; y < 22; y++)
    for (int x = 0; x < 64; x++) {
      const uint8_t *l = e.lueur[y][x];
      ajouter(y, x, ron, l[0], l[1], l[2]);
    }
  float o1[64], o2[64];                                        // la rue mouillee : les reflets, que les rides cassent
  for (int x = 0; x < 64; x++) { o1[x] = sinf(x * 0.25f + t * 0.3f) * 1.2f; o2[x] = sinf(x * 0.31f - t * 0.5f) * 1.6f; }
  for (int y = R; y < 64; y++) {
    const int l = y - R;                                       // chaque rang du reflet ondule un peu
    const int dec = (int)rintf(0.9f * sinf(l * 1.1f + t * 1.2f) + 0.5f * sinf(l * 0.37f - t * 0.7f));
    for (int x = 0; x < 64; x++) {
      const float rides = 0.6f + 0.4f * sinf(y * 1.9f - t * 1.3f + o1[x]);
      const float rides2 = (0.55f + 0.45f * sinf(y * 2.3f - t * 1.0f + o2[x])) * ron;
      const int c = min(63, max(0, x + dec));
      const uint8_t *v = e.vitre[l][c], *n = e.neon[l][c];
      scene[y][x][0] += v[0] * rides + n[0] * rides2;
      scene[y][x][1] += v[1] * rides + n[1] * rides2;
      scene[y][x][2] += v[2] * rides + n[2] * rides2;
    }
  }
  ib_composer(e.d);
  ib_cafe_neon(t, ron);
  bool verse = false;
  const int sx = ib_cafe_gens(t, verse);
  memset(e.vap, 0, sizeof e.vap);                              // les tasses qui fument
  ib_vapeur(e.vap, e.fen, 14, t, 9.5f, 34.0f, 9, 0.22f, 0.9f, 1.0f, 1.5f);
  ib_vapeur(e.vap, e.comp, 10, t, 35.5f, 28.5f, 6, 0.25f, 0.8f, -1.0f, 1.0f);
  ib_vapeur(e.vap, e.tasse, 6, t, 39.0f, 35.0f, 6, 0.3f, 0.6f, 0.5f, 0.6f);
  if (verse) ib_vapeur(e.vap, e.perco, 8, t, sx + 8.0f, 34.0f, 6, 0.4f, 0.8f, 0.5f, 0.7f);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) ib_vapeur_pixel(e.vap[y][x], 1.2f, 150, 130, 110, y, x);
  // un passant et son chien, de temps en temps, sur le trottoir (devant la vitrine)
  const float cyc = ib_mod(t / 70.0f, 1.0f);
  if (cyc < 0.32f) {
    const float px = -8 + cyc / 0.32f * 80;
    const bool pas = ib_mod(t * 2.6f, 1.0f) < 0.5f;
    const char *const *corps = pas ? IB_CAFE_PASSANT_PAS : IB_CAFE_PASSANT;
    static const IbPal PP[] = {{'h', 14, 12, 16}, {'s', 90, 60, 44}, {'c', 16, 14, 20}, {'j', 12, 12, 16},
                               {'k', 10, 10, 12}};
    ib_dessin(corps, 16, px, 32, PP, 5);
    const int pr = (int)floorf(px + 0.5f);
    poser(32, pr + 2, 150, 100, 60); poser(33, pr + 1, 150, 100, 60); poser(34, pr + 1, 150, 100, 60);   // son bord
    const float cx = px + 9;
    static const IbPal CH[] = {{'k', 14, 12, 16}};
    ib_dessin(pas ? IB_CAFE_CHIEN_PAS : IB_CAFE_CHIEN, 4, cx, 44, CH, 1);
    ib_trait(px + 5, 40, cx + 4, 44, 60, 44, 40);
    for (int ys = 9; ys < 16; ys++)                            // son reflet sombre, la tete en bas
      for (int xs = 0; xs < 7; xs++) {
        const int xx = pr + xs, yy = R + 15 - ys;
        if (corps[ys][xs] == '.' || xx < 0 || xx >= 64) continue;
        for (int c = 0; c < 3; c++) scene[yy][xx][c] *= 0.35f;
      }
  }
  for (int k = 0; k < 5; k++) {                                // des gouttes qui tombent encore de la marquise
    static const float GX[5] = {6, 17, 31, 44, 57};
    const float per = e.gp[k], a = ib_mod(t / per + e.g0[k], 1.0f) * per, x = GX[k];
    if (a < 0.6f) {
      const float y = 22 + 25 * (a / 0.6f) * (a / 0.6f);
      pointer(y, x, 230, 190, 140);
      pointer(y - 1, x, 120, 90, 70);
    } else if (a < 0.75f) {
      pointer(47, x - 1, 160, 120, 90);
      pointer(47, x + 1, 160, 120, 90);
    } else if (a > per - 1.2f) {                               // la goutte suivante grossit
      const float k2 = (a - per + 1.2f) / 1.2f;
      pointer(22, x, 200 * k2, 160 * k2, 120 * k2);
    }
  }
}

// --- 4. La station-service au milieu de nulle part (_scene_station_service) ---------------------------------------
// humeurs : 0 = -

const int IB_ST_HORIZON = 38, IB_ST_PISTE = 48, IB_ST_ROUTE = 52;
static const char *const IB_ST_VOITURE[] = {".......rrrrrrrr.......", "......rgGgggrgggr.....", "....rrgggggrggggrr....",
                                            ".bbbbbbbbbbbbbbbbbbbb.", "Hbbbbbbbbbbbbbbbbbbbbt", "bbbkkkbbbbbbbbbbkkkbbb",
                                            "...kkk..........kkk..."};
static const char *const IB_ST_HOMME[] = {".hh.", "shh.", ".cc.", "cccc", "cacc", ".cc.", ".jj.", ".jj.", ".jj.", ".kk."};
static const char *const IB_ST_HOMME_PAS[] = {".hh.", "shh.", ".cc.", "cccc", "cacc", ".cc.", ".jj.", "j..j", "j..j",
                                              "k..k"};
static const char *const IB_ST_POMPE[] = {"vvvv", "wwwW", "wddW", "wwwW", "wnwW", "wnwW", "wwwW", "wwwW", "ssss"};
static const char *const IB_ST_VENDEUR[] = {".kk.", ".kk.", "kkkk", "kkkk"};

struct E_station_service {
  IbDecor d;
  uint8_t ey[60], ex[60];
  float ep[60], el[60];                            // les etoiles
  float pa[11], pv[11], px[11], pp[11];            // les papillons de nuit
};

// la voiture sur son cycle (c en s) : sa place (x de son nez, y de ses roues), ses phares, ses feux stop, et le
// temps depuis l'arret (< 0 : elle roule) ; faux si elle n'est pas la
bool ib_st_trajet(float c, float &x, float &y, float &phares, bool &stop, float &plein) {
  const float P = IB_ST_PISTE, R = IB_ST_ROUTE;
  plein = -1; stop = false; phares = 1;
  if (c < 9.0f) {                                              // elle arrive par la droite et ralentit
    const float k = c / 9.0f;
    x = 70 - (70 - 13) * (1 - powf(1 - k, 2.2f));
    const float u = borne((48 - x) / 26, 0, 1);
    y = R - (R - P) * u * u * (3 - 2 * u);
    stop = k > 0.55f;
    return true;
  }
  if (c < 33.0f) {                                             // a l'arret, le plein
    phares = c < 9.6f ? 1.0f : (c < 32.2f ? 0.25f : 1.0f);
    x = 13; y = P; plein = c - 9.0f;
    return true;
  }
  if (c < 43.0f) {                                             // elle repart vers la gauche, dans la nuit
    const float k = (c - 33.0f) / 10.0f;
    x = 13 - 60 * powf(k, 1.8f);
    const float u = borne((8 - x) / 14, 0, 1);
    y = P + (R - P) * u * u * (3 - 2 * u);
    return true;
  }
  return false;
}

void ib_st_decor(E_station_service &e) {
  const int H_ = IB_ST_HORIZON, P = IB_ST_PISTE, R = IB_ST_ROUTE;
  IbDecor &d = e.d;
  const IbC c0 = ib_niv(6, 8, 22, 1), pl = ib_niv(10, 10, 14, 1), bi = ib_niv(22, 22, 28, 2), bc = ib_niv(10, 12, 12, 1);
  degrade2(c0.r, c0.v, c0.b, 18, 26, 44, 24, H_);              // le ciel, plus clair vers l'horizon
  for (int y = H_; y < 64; y++) {
    const IbC c = y >= R + 3 ? bc : (y >= P - 3 ? bi : pl);    // la plaine noire, le bitume, le bas-cote
    for (int x = 0; x < 64; x++) peindre(y, x, c.r, c.v, c.b);
  }
  ib_lueur(28, 46, 30, 150, 220, 180, 1.0f, 2.6f, P - 3);     // la lumiere de l'auvent sur la piste
  ib_lueur(28, 52, 30, 90, 130, 110, 0.45f, 1.8f, P - 3);     // et jusque sur la route
  ib_lueur(28, 24, 22, 70, 110, 90, 0.75f, 1.0f, 22, P - 1);  // dans l'air, sous l'auvent
  ib_lueur(54, 46, 12, 200, 170, 110, 0.55f, 2.4f, P - 3);    // la vitrine de la boutique sur le sol
  const IbC vi = ib_niv(210, 196, 150, 5);                     // la vitrine de la boutique
  for (int y = 36; y <= 42; y++)
    for (int x = 49; x <= 57; x++) peindre(y, x, vi.r, vi.v, vi.b);
  ib_lueur(53, 37, 6, 40, 40, 30, 1.0f, 1.0f, 36, 43);
  ib_lueur(7, 9, 9, 40, 70, 60, 0.6f);                          // le halo du panneau
  peindre(37, 3, 90, 70, 40);                                   // des fermes, tres loin
  peindre(37, 58, 90, 70, 40);
  peindre(37, 43, 90, 70, 40);
  ib_garder_lumiere(d);
  // le calque net
  ib_net_rect(d, 18, 18, 9, 47, 40, 46, 50);                   // l'auvent : sa tranche, sa bande verte
  ib_net_rect(d, 19, 20, 9, 47, 52, 196, 128);
  ib_net_rect(d, 21, 21, 9, 47, 176, 188, 184);
  ib_net_rect(d, 22, 22, 10, 46, 70, 80, 78);
  for (int x0 = 12; x0 <= 39; x0 += 9) ib_net_rect(d, 22, 22, x0, x0 + 5, 226, 255, 236);   // les tubes dessous
  for (int k = 0; k < 2; k++) {                                // les piliers
    const int x = k ? 44 : 12;
    for (int y = 23; y <= P - 4; y++)
      if (y % 3 == 0) ib_net(d, y, x, 130, 146, 140);
      else ib_net(d, y, x, 96, 110, 106);
  }
  ib_net_rect(d, P - 5, P - 4, 16, 33, 120, 130, 124);         // l'ilot des pompes
  ib_net_rect(d, P - 5, P - 5, 16, 33, 170, 182, 176);
  static const IbPal POMPE[] = {{'v', 52, 196, 128}, {'w', 176, 188, 184}, {'W', 118, 128, 124}, {'d', 20, 40, 40},
                                {'n', 34, 36, 40}, {'s', 90, 98, 96}};
  ib_sprite(IB_ST_POMPE, 19, P - 13, POMPE, false, &d);
  ib_sprite(IB_ST_POMPE, 27, P - 13, POMPE, false, &d);
  ib_trait(23, P - 9, 24, P - 6, 30, 32, 36, &d);             // le tuyau de la premiere pompe
  for (int y = 33; y <= P - 4; y++)                            // la boutique
    for (int x = 47; x <= 62; x++) {
      const bool vit = x >= 49 && x <= 57 && y >= 36 && y <= 42, porte = x >= 59 && x <= 61 && y >= 37;
      if (!vit && !porte) ib_net(d, y, x, 54, 52, 50);
    }
  ib_net_rect(d, 33, 33, 46, 63, 84, 82, 78);
  ib_net_rect(d, 34, 34, 47, 62, 40, 38, 38);
  ib_net_rect(d, 37, P - 4, 59, 61, 150, 140, 110);            // la porte vitree
  ib_net(d, 42, 59, 60, 60, 60);
  ib_net_rect(d, 35, 43, 48, 48, 70, 68, 64);                  // le cadre de la vitrine
  ib_net_rect(d, 35, 43, 58, 58, 70, 68, 64);
  ib_net_rect(d, 35, 35, 48, 58, 70, 68, 64);
  ib_net_rect(d, 43, 43, 48, 58, 70, 68, 64);
  static const float PA[4][3] = {{200, 60, 60}, {60, 140, 200}, {220, 180, 60}, {80, 170, 90}};
  static const float PB[4][3] = {{220, 180, 60}, {200, 60, 60}, {80, 170, 90}, {60, 140, 200}};
  for (int x = 50; x < 57; x += 2) {                           // les rayons et leurs produits
    const float *a = PA[(x / 2) % 4], *b = PB[(x / 2) % 4];
    ib_net(d, 40, x, a[0], a[1], a[2]);
    ib_net(d, 38, x + 1, b[0], b[1], b[2]);
  }
  ib_net_rect(d, 42, 42, 49, 57, 120, 100, 70);                // le comptoir
  ib_net_rect(d, 17, P - 3, 7, 7, 60, 64, 66);                 // le mat du panneau
  ib_net_rect(d, 4, 11, 3, 11, 60, 66, 66);
  ib_net_rect(d, 5, 10, 4, 10, 176, 190, 186);
  for (int y = 4; y <= 11; y++)                                // une goutte verte
    for (int x = 3; x <= 11; x++) {
      const float dd = sqrtf((x - 7.0f) * (x - 7.0f) + (y - 8.6f) * (y - 8.6f));
      if (dd < 1.9f || (x == 7 && y >= 6 && y <= 7)) ib_net(d, y, x, 40, 170, 110);
    }
  ib_net_rect(d, 12, 16, 3, 11, 24, 26, 28);                   // les prix : des chiffres qui suggerent
  for (int y = 13; y <= 15; y += 2)
    for (int x = 5; x <= 9; x += 2) {
      ib_net(d, y, x, 255, 168, 60);
      if (x != 9) ib_net(d, y, x + 1, 200, 120, 40);
    }
  for (int x = 1; x < 64; x += 6) ib_net_rect(d, R + 1, R + 1, x, x + 2, 90, 88, 70);   // les pointilles de la route
  bool pris[64] = {};
  for (int n = 0; n < 7;) {                                    // des touffes d'herbe au premier plan
    const int x = 2 + aleatoire() % 60;
    if (pris[x]) continue;
    pris[x] = true;
    n++;
    static const int TOUFFE[3][2] = {{-1, 1}, {0, 3}, {1, 2}};
    for (int k = 0; k < 3; k++) {
      const int xx = x + TOUFFE[k][0], h = TOUFFE[k][1];
      ib_net_rect(d, 63 - h, 63, xx, xx, 14, 20, 16);
      ib_net(d, 63 - h, xx, 30, 40, 32);
    }
  }
  for (int i = 0; i < 60; i++) {
    e.ey[i] = aleatoire() % (H_ - 6); e.ex[i] = aleatoire() % 64; e.ep[i] = hasard(0, PI2); e.el[i] = hasard(0.3f, 1.0f);
  }
  for (int i = 0; i < 11; i++) {
    e.pa[i] = hasard(0, PI2); e.pv[i] = hasard(0.5f, 1.6f); e.px[i] = hasard(12, 44); e.pp[i] = hasard(0, 1);
  }
}

void s_station_service(int humeur, bool debut, float t, float ecoule, float dt) {
  E_station_service &e = etat_ecran<E_station_service>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  const int H_ = IB_ST_HORIZON, P = IB_ST_PISTE;
  if (debut) ib_st_decor(e);
  ib_poser_fond(e.d);
  const float c = ib_mod(t, 80.0f);
  float vx, vy, ph, plein;
  bool stop;
  const bool la = ib_st_trajet(c, vx, vy, ph, stop, plein);
  if (la) {                                                    // les phares devant elle, sur le bitume
    ib_lueur(vx - 10, vy, 13 * ph, 255, 236, 190, 0.55f * ph, 2.8f);
    ib_lueur(vx - 1, vy - 3, 4 * ph, 255, 240, 200, 0.5f * ph);
    if (stop || c > 33) ib_lueur(vx + 23, vy - 3, 3.5f, 255, 30, 20, 0.45f);
  }
  const float loin = ib_mod(t / 47.0f, 1.0f), fx = 66 - loin / 0.45f * 70;   // une autre voiture, tres loin
  if (loin < 0.45f) ib_lueur(fx, H_ - 0.5f, 2.2f, 255, 220, 160, 0.35f, 1.5f);
  ib_composer(e.d);
  for (int i = 0; i < 60; i++) {                               // les etoiles, qui scintillent doucement
    const float k = e.el[i] * (0.6f + 0.4f * sinf(t * 1.3f + e.ep[i]));
    pointer(e.ey[i], e.ex[i], 200 * k, 210 * k, 236 * k);
  }
  if (loin < 0.45f) {
    pointer(H_ - 1, fx, 255, 230, 180);
    pointer(H_ - 1, fx + 1, 255, 230, 180);
  }
  if (la) {                                                    // la voiture : sous l'auvent, elle prend la lumiere
    const float a = borne(1 - fabsf(vx + 11 - 28) / 26, 0, 1), dessous = a > 0 ? powf(a, 0.7f) : 0;
    const float cr = 44 + 90 * dessous, cv = 20 + 28 * dessous, cb = 28 + 34 * dessous, hk = 0.45f + 0.55f * ph;
    const bool rouge = stop || c > 33;
    const IbPal pal[] = {{'r', cr * 1.15f + 60 * dessous, cv * 1.15f + 80 * dessous, cb * 1.15f + 70 * dessous},
                         {'g', 18, 24, 30}, {'G', 30 + 90 * dessous, 40 + 120 * dessous, 50 + 110 * dessous},
                         {'b', cr, cv, cb}, {'k', 12, 12, 14}, {'H', 255 * hk, 240 * hk, 200 * hk},
                         {'t', rouge ? 255.0f : 150.0f, rouge ? 40.0f : 20.0f, rouge ? 30.0f : 20.0f}};
    ib_sprite(IB_ST_VOITURE, vx, vy - 6, pal);
    if (plein >= 0) {                                          // la portiere, le conducteur, le tuyau
      static const IbPal PC[] = {{'h', 40, 32, 28}, {'s', 210, 176, 140}, {'c', 176, 140, 64}, {'a', 130, 100, 44},
                                 {'m', 210, 176, 140}, {'j', 44, 50, 70}, {'k', 20, 20, 22}};
      if (plein > 1.0f && plein < 23.0f) {
        float ddx;
        if (plein < 2.5f || plein > 21.5f) {
          for (int k = 3; k <= 5; k++) poser(P - k, vx + 9, 150, 170, 160);   // la portiere ouverte
          ddx = vx + 10;
        } else if (plein < 4.5f) ddx = vx + 10 + (plein - 2.5f) / 2 * 13;
        else if (plein < 19.5f) ddx = vx + 23;
        else ddx = vx + 23 - (plein - 19.5f) / 2 * 13;
        const bool marche = (plein > 2.5f && plein < 4.5f) || (plein > 19.5f && plein < 21.5f);
        if (marche && ib_mod(t * 3, 1.0f) < 0.5f) ib_sprite(IB_ST_HOMME_PAS, ddx, P - 9, PC, plein > 2.5f && plein < 4.5f);
        else ib_sprite(IB_ST_HOMME, ddx, P - 9, PC, plein > 2.5f && plein < 4.5f);
        if (plein >= 4.5f && plein < 19.5f) {                  // le pistolet dans le reservoir
          ib_trait(31, P - 9, ddx - 1, P - 5, 30, 32, 36);
          poser(P - 5, ddx, 210, 176, 140);
        }
      }
      if (plein >= 4.5f && plein < 19.5f) {                    // le compteur de la pompe defile
        const int n = (int)((plein - 4.5f) * 3);
        poser(P - 11, 28, (n >> 2) & 1 ? 80 : 30, (n >> 2) & 1 ? 255 : 90, (n >> 2) & 1 ? 170 : 70);
        poser(P - 11, 29, (n >> 3) & 1 ? 80 : 30, (n >> 3) & 1 ? 255 : 90, (n >> 3) & 1 ? 170 : 70);
      }
    }
  }
  // le vendeur, derriere sa vitrine, qui va et vient lentement
  static const IbPal VEND[] = {{'k', 56, 50, 44}};
  ib_sprite(IB_ST_VENDEUR, 51.5f + 2.5f * sinf(t * 0.13f) + 0.6f * sinf(t * 0.41f), 38, VEND);
  for (int i = 0; i < 11; i++) {                               // les papillons de nuit, qui tournent sous les tubes
    const float ang = e.pa[i] + t * e.pv[i] * 2.2f;
    const float bx = e.px[i] + sinf(ang) * 2.5f + sinf(t * 3.1f + e.pp[i] * 9) * 1.0f;
    const float by = 24.5f + fabsf(cosf(ang * 1.3f)) * 2.4f + sinf(t * 2.3f + e.pp[i] * 7) * 0.8f + e.pp[i] * 1.5f;
    const float k = 0.55f + 0.45f * fabsf(sinf(t * 9 + e.pp[i] * 20));
    pointer(by, bx, 210 * k, 220 * k, 200 * k);
  }
}
