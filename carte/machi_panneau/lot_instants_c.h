// lot_instants_c.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10) : le quai de gare sous la neige,
// le dernier metro, le toit sur la ville, le carrefour a trois heures. Les « instants » : du pixel art de nuit trame.
// Chacun suit son jumeau _scene_<nom> en numpy : le decor fixe est calcule une fois (en octets, dans E_x), puis a
// chaque image : la copie du fond, les lumieres qui bougent, tramer(), et par-dessus ce qui reste net (silhouettes,
// sprites, flocons). Les cycles (le train, le feu, l'avion...) suivent fmodf(t + decalage, periode) : le decalage
// cale la phase sur celle du jumeau au banc (t = 137 + ecoule) ; sur la carte, t part d'ailleurs, la phase aussi.
#pragma once

// --- les outils du lot -----------------------------------------------------------------------------------------

struct IC_Bord { int dx, dy; float r, v, b, part; };   // un lisere : le cote (a l'ecran), sa lumiere, sa part

inline float ic_lisse(float u) { u = borne(u, 0, 1); return u * u * (3 - 2 * u); }
inline float ic_mod(float a, float m) { const float r = fmodf(a, m); return r < 0 ? r + m : r; }

// garder la scene en octets (le fond fixe), et l'y recopier a chaque image
void ic_garder(uint8_t (*f)[64][3]) {
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) f[y][x][c] = (uint8_t)(borne(scene[y][x][c], 0, 255) + 0.5f);
}
void ic_recopier(const uint8_t (*f)[64][3]) {
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] = f[y][x][c];
}
// le calque net du premier plan : la ou le masque est mis, il ecrase la scene
void ic_calque(const uint8_t (*d)[64][3], const uint8_t (*m)[64], int xmax = 63, int ymin = 0) {
  for (int y = ymin; y < 64; y++)
    for (int x = 0; x <= xmax; x++)
      if (m[y][x]) peindre(y, x, d[y][x][0], d[y][x][1], d[y][x][2]);
}
// un rectangle (bornes comprises) du calque
void ic_rect(uint8_t (*d)[64][3], uint8_t (*m)[64], int x0, int x1, int y0, int y1, int r, int v, int b) {
  for (int y = max(0, y0); y <= min(63, y1); y++)
    for (int x = max(0, x0); x <= min(63, x1); x++) {
      d[y][x][0] = (uint8_t)r; d[y][x][1] = (uint8_t)v; d[y][x][2] = (uint8_t)b;
      m[y][x] = 1;
    }
}

// _halo, borne a 4.5 rayons (au-dela, moins de 1 % : rien apres la trame) : pour les lueurs de chaque image
void ic_halo(float x, float y, float rayon, float r, float v, float b, float force = 1.0f, float aplati = 1.0f) {
  const float portee = rayon * 4.5f, py = portee / aplati;
  const int x0 = max(0, (int)floorf(x - portee)), x1 = min(W - 1, (int)ceilf(x + portee));
  const int y0 = max(0, (int)floorf(y - py)), y1 = min(H - 1, (int)ceilf(y + py));
  const float inv = 1.0f / fmaxf(rayon, 1e-3f), p2 = portee * portee;
  for (int yy = y0; yy <= y1; yy++) {
    const float dy = (yy - y) * aplati;
    for (int xx = x0; xx <= x1; xx++) {
      const float dx = xx - x, d2 = dx * dx + dy * dy;
      if (d2 <= p2) ajouter(yy, xx, expf(-sqrtf(d2) * inv) * force, r, v, b);
    }
  }
}

// _ic_dessiner : un sprite en chaines ('.' transparent), coin haut gauche en (x, y) arrondi ; cles + pal : la
// palette (une lettre absente est transparente) ; miroir ; force < 1 : en fondu ; bords : les liseres eclaires,
// chacun pose sur les points dont le voisin du cote (dx, dy) -- vu a l'ecran -- est vide
void ic_sprite(const char *const *l, int nl, float x, float y, const char *cles, const float (*pal)[3],
               bool miroir = false, float force = 1.0f, const IC_Bord *bords = nullptr, int nb = 0) {
  const int larg = (int)strlen(l[0]);
  const int x0 = (int)floorf(x + 0.5f), y0 = (int)floorf(y + 0.5f);
  for (int r = 0; r < nl; r++)
    for (int c = 0; c < larg; c++) {
      if (l[r][c] == '.') continue;
      const char *k = strchr(cles, l[r][c]);
      if (!k) continue;
      const int sy = y0 + r, sx = x0 + (miroir ? larg - 1 - c : c);
      if (sy < 0 || sy >= H || sx < 0 || sx >= W) continue;
      const float *q = pal[k - cles];
      float *p = scene[sy][sx];
      for (int i = 0; i < 3; i++) p[i] = force >= 1 ? q[i] : p[i] * (1 - force) + q[i] * force;
    }
  for (int j = 0; j < nb; j++) {
    const IC_Bord &bd = bords[j];
    const int sdx = miroir ? -bd.dx : bd.dx;
    const float part = bd.part * fminf(force, 1.0f);
    for (int r = 0; r < nl; r++)
      for (int c = 0; c < larg; c++) {
        if (l[r][c] == '.' || !strchr(cles, l[r][c])) continue;
        const int rr = r + bd.dy, cc = c + sdx;
        if (rr >= 0 && rr < nl && cc >= 0 && cc < larg && l[rr][cc] != '.') continue;
        const int sy = y0 + r, sx = x0 + (miroir ? larg - 1 - c : c);
        if (sy < 0 || sy >= H || sx < 0 || sx >= W) continue;
        float *p = scene[sy][sx];
        p[0] = p[0] * (1 - part) + bd.r * part;
        p[1] = p[1] * (1 - part) + bd.v * part;
        p[2] = p[2] * (1 - part) + bd.b * part;
      }
  }
}

// --- le quai de gare (_scene_quai_gare) -------------------------------------------------------------------------
// humeurs : 0 = - (une seule ambiance)

const int IC_GARE_L = 134;      // la rame : trois voitures de 43 px, 2 px entre elles, la tete a droite
const int IC_GARE_HAUT = 28;    // la ligne du toit de la rame
const float IC_GARE_ARRET = 110;   // sa tete quand elle est arretee (hors champ a droite)
static const float IC_GARE_LAMPES[2][3] = {{10.5f, 9.5f, 9.0f}, {49.0f, 11.5f, 8.0f}};   // reverbere, auvent
static const char *const IC_VOYAGEUR[13] = {   // face a droite ; h bonnet, s visage, e echarpe, k manteau
  "..hhh..", ".hhhhh.", ".hhhss.", "..hss..", ".eeee..", ".kkkkk.", "kkkkkkk", "kkkkkkk", "kkkkk.k", "kkkkk.k",
  "kkkkk.s", ".kkkk..", ".kkkk.."};
static const char *const IC_JAMBES[5][3] = {   // debout, puis quatre poses de marche ; p jambes, b bottes
  {"..p.p..", "..p.p..", ".bb.bb."}, {"..p.p..", ".p...p.", "bb...bb"}, {"...pp..", "..p.p..", "..bbbb."},
  {"..p.p..", "..p..p.", ".bb..bb"}, {"...pp..", "...pp..", "..bbb.."}};
static const char *const IC_VALISE[8] = {"m...", "m...", "vvvv", "vwvv", "vvvv", "vvvv", "vvvv", "o..o"};
static const char IC_GARE_CLES[] = "hsekpbvwmo";
static const float IC_GARE_PAL[10][3] = {{110, 34, 40}, {150, 104, 84}, {40, 70, 96}, {32, 30, 42}, {24, 24, 32},
                                         {14, 14, 18}, {88, 44, 38}, {130, 74, 60}, {60, 60, 70}, {20, 20, 24}};

struct E_quai_gare {
  uint8_t fond[64][64][3], lueurs[64][64][3], dessus[64][64][3], masque[64][64];
  uint8_t rame[23][IC_GARE_L][4];   // la rame, premultipliee (alpha 0 ou 255)
  float vitres[IC_GARE_L];          // la lumiere de ses fenetres, colonne par colonne (pour le quai)
  float eclairage[21][64];          // les lampes du quai eclairent un peu la rame
  float fx[34], fy[34], fv[34], fp[34];   // la neige
};

// la rame vue de cote (_ic_gare_rame)
void ic_gare_rame(E_quai_gare &e) {
  auto coul = [&](int r0, int r1, int u0, int u1, float r, float v, float b) {
    for (int r_ = r0; r_ < r1; r_++)
      for (int u = u0; u < u1; u++) {
        e.rame[r_][u][0] = (uint8_t)(r + 0.5f); e.rame[r_][u][1] = (uint8_t)(v + 0.5f); e.rame[r_][u][2] = (uint8_t)(b + 0.5f);
      }
  };
  auto plein = [&](int r0, int r1, int u0, int u1, uint8_t a) {
    for (int r_ = r0; r_ < r1; r_++)
      for (int u = u0; u < u1; u++) e.rame[r_][u][3] = a;
  };
  for (int v = 0; v < 3; v++) {
    const int u0 = v * 45, u1 = u0 + 43;
    plein(0, 20, u0, u1, 255);
    coul(0, 1, u0, u1, 88, 94, 118);                        // un peu de neige sur le toit
    coul(1, 3, u0, u1, 30, 33, 46);
    coul(3, 20, u0, u1, 44, 50, 70);
    coul(4, 5, u0, u1, 60, 30, 36);                         // le lisere rouge de la livree
    coul(15, 16, u0, u1, 96, 76, 52);                       // et sa bande creme
    coul(19, 20, u0, u1, 22, 24, 34);
    plein(20, 21, u0 + 2, u1 - 2, 255);
    coul(20, 21, u0 + 2, u1 - 2, 16, 16, 22);
    for (int b0 : {u0 + 3, u0 + 33}) {                      // les bogies
      plein(20, 23, b0, b0 + 7, 255);
      coul(20, 23, b0, b0 + 7, 14, 14, 20);
      coul(21, 22, b0 + 1, b0 + 2, 52, 52, 62);
      coul(21, 22, b0 + 5, b0 + 6, 52, 52, 62);
    }
    for (int p0 : {u0 + 9, u0 + 30}) {                      // les portes, leur hublot allume
      coul(5, 19, p0, p0 + 4, 36, 40, 58);
      coul(5, 19, p0, p0 + 1, 24, 26, 38);
      coul(5, 19, p0 + 3, p0 + 4, 24, 26, 38);
      coul(6, 11, p0 + 1, p0 + 3, 236, 186, 116);
      e.vitres[p0 + 1] = e.vitres[p0 + 2] = 0.55f;
    }
    const int fen[3][2] = {{u0 + 2, u0 + 9}, {u0 + 14, u0 + 30}, {u0 + 35, u0 + 42}};
    for (int k = 0; k < 3; k++)
      for (int x = fen[k][0]; x + 5 <= fen[k][1]; x += 6) {
        const float chaud = hasard(0.8f, 1.0f);
        coul(6, 13, x, x + 5, 255 * chaud, 208 * chaud, 128 * chaud);
        coul(6, 7, x, x + 5, 255 * chaud, 224 * chaud, 160 * chaud);   // le plafonnier, plus clair en haut
        for (int u = x; u < x + 5; u++) e.vitres[u] = chaud;
        if (hasard(0, 1) < 0.45f) {                           // un passager : la tete, les epaules
          const int q = x + (int)(aleatoire() % 2);
          coul(8, 10, q + 1, q + 3, 58, 38, 34);
          coul(10, 13, q, q + 4, 50, 34, 32);
        }
      }
  }
  const int u1 = 2 * 45 + 43;                                 // le nez de la voiture de tete
  const int coupe[3] = {5, 2, 1};
  for (int k = 0; k < 3; k++) plein(0, coupe[k], u1 - 1 - k, u1 - k, 0);
  coul(6, 10, u1 - 3, u1, 110, 100, 84);                      // le pare-brise
  coul(13, 15, u1 - 1, u1, 255, 244, 210);                    // le phare
  for (int r = 0; r < 23; r++)
    for (int u = 0; u < IC_GARE_L; u++)
      if (!e.rame[r][u][3]) e.rame[r][u][0] = e.rame[r][u][1] = e.rame[r][u][2] = 0;
}

// le fond fixe, les lueurs des lampes (deja tramees), le calque des silhouettes (_ic_gare_decor)
void ic_gare_decor(E_quai_gare &e) {
  degrade2(5, 6, 17, 30, 34, 56, 4, 34);
  float crete[64];                                            // la foret de sapins, au loin
  for (int x = 0; x < 64; x++) crete[x] = 33 - 1.5f * sinf(x * 0.11f + 0.8f);
  for (float c = 0; c < 66;) {
    const float h = hasard(3, 8);
    for (int x = 0; x < 64; x++) crete[x] = fminf(crete[x], 33 - h + fabsf(x - c) * 1.6f);
    c += hasard(2.5f, 5);
  }
  peindre_sous(crete, 10, 13, 26, 34);
  for (int y = 34; y < 41; y++) {                             // le champ enneige
    const float k = (y - 34) / 7.0f;
    for (int x = 0; x < 64; x++) peindre(y, x, 40 + 10 * k, 44 + 10 * k, 64 + 12 * k);
  }
  const int fermes[2][2] = {{15, 6}, {46, 5}};               // deux fermes, au loin
  for (int f = 0; f < 2; f++) {
    const int hx = fermes[f][0], hl = fermes[f][1];
    for (int x = hx; x < hx + hl; x++) {
      for (int y = 35; y < 39; y++) peindre(y, x, 14, 16, 28);
      peindre(33, x, 64, 70, 96);
    }
    for (int x = hx - 1; x < hx + hl + 1; x++) peindre(34, x, 78, 84, 110);   // la neige sur le toit
  }
  for (int x = 0; x < 64; x++) {
    for (int y = 41; y < 49; y++) peindre(y, x, 22, 22, 32);  // le ballast
    if (x % 4 == 0)
      for (int y = 42; y < 48; y++) peindre(y, x, 30, 32, 44);   // la neige entre les traverses
    peindre(44, x, 70, 72, 90);                               // rail du fond
    peindre(47, x, 84, 86, 104);                              // rail de devant
    peindre(49, x, 14, 14, 22);                               // le flanc du quai
    peindre(50, x, 14, 14, 22);
    peindre(51, x, 120, 118, 108);                            // la bordure
    for (int y = 52; y < 64; y++) {                           // le quai sous la neige
      const float k = (y - 52) / 12.0f;
      peindre(y, x, 30 + 4 * k, 34 + 4 * k, 46 + 2 * k);
    }
  }
  for (int i = 0; i < 2; i++) {                               // les flaques de lumiere sur la neige, et les rails
    halo(IC_GARE_LAMPES[i][0], 59.5f, 8.5f, 255, 196, 120, 0.85f, 2.6f);
    halo(IC_GARE_LAMPES[i][0], 44, 6, 255, 190, 110, 0.28f, 2.0f);
  }
  ic_garder(e.fond);
  memset(scene, 0, sizeof scene);                             // les lueurs dans l'air, tramees une fois
  halo(10.5f, 9.5f, 2.0f, 255, 176, 92, 1.1f);
  halo(10.5f, 9.5f, 6.0f, 255, 160, 80, 0.28f);
  halo(49.0f, 11.5f, 2.0f, 255, 214, 150, 1.0f);
  halo(49.0f, 11.5f, 6.0f, 255, 196, 130, 0.26f);
  tramer(8);
  ic_garder(e.lueurs);
  uint8_t (*d)[64][3] = e.dessus;
  uint8_t (*m)[64] = e.masque;
  ic_rect(d, m, 5, 6, 9, 61, 20, 20, 28);                     // le reverbere
  ic_rect(d, m, 4, 7, 58, 61, 20, 20, 28);
  ic_rect(d, m, 7, 7, 7, 8, 20, 20, 28);
  ic_rect(d, m, 8, 11, 6, 6, 20, 20, 28);
  ic_rect(d, m, 9, 12, 7, 7, 34, 30, 30);
  ic_rect(d, m, 6, 6, 10, 40, 66, 50, 36);                    // son lisere, du cote de la lampe
  ic_rect(d, m, 33, 63, 3, 6, 24, 22, 30);                    // l'auvent
  ic_rect(d, m, 34, 63, 2, 2, 128, 134, 162);                 // la neige sur l'auvent
  for (int x = 34; x < 64; x += 2) ic_rect(d, m, x, x, 7, 7, 24, 22, 30);   // son lambrequin
  ic_rect(d, m, 40, 58, 6, 6, 70, 54, 40);                    // le dessous, eclaire par la lampe
  const int colonnes[2][2] = {{36, 1}, {61, -1}};             // les colonnes en fonte
  for (int k = 0; k < 2; k++) {
    const int cx = colonnes[k][0], cote = colonnes[k][1];
    ic_rect(d, m, cx, cx, 7, 60, 22, 22, 30);
    ic_rect(d, m, cx - 1, cx + 1, 7, 8, 22, 22, 30);
    ic_rect(d, m, cx - 1, cx + 1, 59, 60, 22, 22, 30);
    ic_rect(d, m, cx + cote, cx + cote, 9, 40, 54, 42, 34);
  }
  ic_rect(d, m, 49, 49, 7, 9, 24, 22, 30);                    // la suspension
  ic_rect(d, m, 48, 50, 10, 10, 40, 34, 30);
  ic_rect(d, m, 55, 55, 7, 9, 24, 22, 30);                    // l'horloge
  for (int y = 9; y < 18; y++)
    for (int x = 51; x < 60; x++) {
      const float r = sqrtf((x - 55.0f) * (x - 55.0f) + (y - 13.5f) * (y - 13.5f));
      if (r <= 2.7f) ic_rect(d, m, x, x, y, y, 212, 196, 160);
      else if (r <= 3.6f) ic_rect(d, m, x, x, y, y, 30, 28, 34);
    }
  ic_rect(d, m, 42, 55, 53, 53, 138, 96, 60);                 // le banc
  ic_rect(d, m, 42, 55, 55, 55, 46, 32, 26);
  ic_rect(d, m, 41, 56, 57, 57, 138, 96, 60);
  ic_rect(d, m, 41, 56, 58, 58, 46, 32, 26);
  ic_rect(d, m, 42, 42, 53, 61, 30, 24, 24);
  ic_rect(d, m, 55, 55, 53, 61, 30, 24, 24);
  ic_gare_rame(e);
  for (int r = 0; r < 21; r++)
    for (int x = 0; x < 64; x++) {
      float ec = 1;
      for (int i = 0; i < 2; i++) {
        const float dx = x - IC_GARE_LAMPES[i][0], dy = (r + IC_GARE_HAUT - IC_GARE_LAMPES[i][1]) * 0.8f;
        ec += 0.9f * expf(-sqrtf(dx * dx + dy * dy) / 11);
      }
      e.eclairage[r][x] = ec;
    }
  for (int i = 0; i < 34; i++) { e.fx[i] = hasard(0, 64); e.fy[i] = hasard(0, 64); e.fv[i] = hasard(4, 9); e.fp[i] = hasard(0, 6.3f); }
}

// la moyenne exacte de la rame entre les abscisses a et b, pour ses 21 premieres lignes (un filtre boite : ce qui
// defile glisse sans saccade) ; out[r][0..3] premultiplie, alpha 0-1
void ic_gare_colonne(const E_quai_gare &e, float a, float b, float out[21][4]) {
  memset(out, 0, sizeof(float) * 21 * 4);
  const int i0 = max(0, (int)floorf(a)), i1 = min(IC_GARE_L - 1, (int)floorf(b));
  for (int i = i0; i <= i1; i++) {
    const float w = fminf(b, i + 1.0f) - fmaxf(a, (float)i);
    if (w <= 0) continue;
    for (int r = 0; r < 21; r++)
      for (int c = 0; c < 4; c++) out[r][c] += w * e.rame[r][i][c];
  }
  const float inv = 1.0f / fmaxf(b - a, 1e-6f);
  for (int r = 0; r < 21; r++) {
    for (int c = 0; c < 3; c++) out[r][c] *= inv;
    out[r][3] *= inv / 255.0f;
  }
}

void s_quai_gare(int humeur, bool debut, float t, float ecoule, float dt) {
  E_quai_gare &e = etat_ecran<E_quai_gare>(debut);
  (void)humeur; (void)ecoule;
  if (debut) ic_gare_decor(e);
  const float P = ic_mod(t + 57.0f, 60.0f);                   // la minute du train
  float tete, vit;
  if (P < 20) {                                               // il arrive, de plus en plus lentement
    const float u = P / 20;
    tete = IC_GARE_ARRET - 150 * (1 - u) * (1 - u); vit = 300 * (1 - u) / 20;
  } else if (P < 36) {
    tete = IC_GARE_ARRET; vit = 0;
  } else {                                                    // il repart, de plus en plus vite
    const float u = fminf((P - 36) / 18, 1.0f);
    tete = IC_GARE_ARRET + 96 * u * u; vit = 192 * u / 18;
  }
  ic_recopier(e.fond);
  const float queue = tete - IC_GARE_L;
  const int h0 = IC_GARE_HAUT;
  const float phare = tete < 130 ? borne(1 - (tete - 70) / 60, 0, 1) : 0.0f;
  if (phare > 0) ic_halo(tete + 9, 45, 7, 255, 236, 190, 0.9f * phare, 2.4f);   // le phare, devant, sur la voie
  const bool present = queue < 64 && tete > -2;
  const float m = vit / 30;                                   // le flou du mouvement (une image)
  float ouv = 0;
  if (present) {
    float lum[64];                                            // la lumiere des fenetres, sur la neige du quai
    for (int x = 0; x < 64; x++) {
      const float a = x - queue - m, b = x + 1 - queue;
      float s = 0;
      for (int i = max(0, (int)floorf(a)); i <= min(IC_GARE_L - 1, (int)floorf(b)); i++) {
        const float w = fminf(b, i + 1.0f) - fmaxf(a, (float)i);
        if (w > 0) s += w * e.vitres[i];
      }
      lum[x] = s / fmaxf(b - a, 1e-6f);
    }
    for (int y = 52; y < 62; y++) {
      const float k = 0.38f * expf(-(y - 52) / 3.5f);
      for (int x = 0; x < 64; x++) {
        const int dec = (int)borne(x - (y - 51) * 0.7f, 0, 63);
        ajouter(y, x, lum[dec] * k, 255, 196, 116);
      }
    }
    if (P >= 21 && P < 33) {                                  // la porte s'ouvre (x = 28..31)
      ouv = ic_lisse((P - 21) / 1.2f) * ic_lisse((32 - P) / 1.2f);
      ic_halo(roundf(queue) + 56, 55, 4, 255, 200, 130, 0.6f * ouv, 2.0f);
    }
  }
  tramer(8);
  if (present) {                                              // la rame, en aplats nets, eclairee par les lampes
    float A[21][4];
    for (int x = 0; x < 64; x++) {
      ic_gare_colonne(e, x - queue - m, x + 1 - queue, A);
      for (int r = 0; r < 21; r++) {
        if (A[r][3] <= 0) continue;
        float *p = scene[h0 + r][x];
        const float k = 1 - A[r][3], ec = e.eclairage[r][x];
        for (int c = 0; c < 3; c++) p[c] = p[c] * k + A[r][c] * ec;
      }
    }
    if (ouv > 0) {
      const int px = (int)roundf(queue) + 54;
      for (int y = h0 + 5; y < h0 + 19; y++)
        for (int x = px + 1; x < px + 3; x++)
          if (x >= 0 && x < 64) {
            float *p = scene[y][x];
            p[0] = p[0] * (1 - ouv) + 255 * ouv; p[1] = p[1] * (1 - ouv) + 220 * ouv; p[2] = p[2] * (1 - ouv) + 160 * ouv;
          }
    }
    if (tete > -2 && tete < 66) halo(tete, h0 + 13.5f, 1.4f, 255, 240, 200, phare);
  }
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] += e.lueurs[y][x][c];
  static const uint8_t VY[5] = {36, 37, 36, 32, 33}, VX[5] = {17, 19, 48, 4, 58};   // les fermes, au loin
  for (int i = 0; i < 5; i++)
    if (!present || VX[i] < queue || VX[i] > tete) pointer(VY[i], VX[i], 200, 140, 70);
  ic_calque(e.dessus, e.masque);
  for (int x = 9; x < 12; x++) peindre(9, x, 255, 214, 140);  // les ampoules, nettes
  for (int x = 48; x < 51; x++) peindre(11, x, 255, 230, 180);
  const float heure = 2.75f + t / 3600;                       // l'horloge : sans heure sur la carte, elle tourne
  const float aig[2] = {fmodf(heure * 60, 60) / 60 * PI2, fmodf(heure, 12) / 12 * PI2};
  static const float LONG[2][3] = {{0.9f, 1.9f, 2.6f}, {0.9f, 1.6f, 0}};
  for (int a = 0; a < 2; a++)
    for (int k = 0; k < 3; k++)
      if (LONG[a][k] > 0)
        peindre((int)roundf(13.5f - cosf(aig[a]) * LONG[a][k]), (int)roundf(55 + sinf(aig[a]) * LONG[a][k]), 40, 30, 30);
  peindre(13, 55, 40, 30, 30);
  int vers = 1, pose = 0;                                     // le voyageur
  float px = 24, py = 39, force = 1;
  bool voit = true;
  if (P < 20) vers = -1;                                      // il regarde arriver le train
  else if (P >= 22.5f && P < 25) { px = 24 + 3 * (P - 22.5f) / 2.5f; pose = 1 + (int)(P * 4) % 4; }
  else if (P >= 25 && P < 26.5f) {                            // il monte, et disparait dans la lumiere
    const float u = (P - 25) / 1.5f;
    px = 27; py = 39 - 2 * u; force = 1 - u;
  } else if (P >= 26.5f && P < 38) voit = false;
  else if (P >= 38 && P < 49) { px = -9 + 33 * (P - 38) / 11; pose = 1 + (int)(P * 3.5f) % 4; }   // le suivant
  if (voit) {
    const float k = ic_lisse((P - 14) / 4) * ic_lisse((40 - P) / 4);   // le train, derriere lui, l'eclaire aussi
    const float lr = 230 + 25 * k, lv = 170 + 44 * k, lb = 110 + 40 * k;
    const char *corps[16];
    for (int i = 0; i < 13; i++) corps[i] = IC_VOYAGEUR[i];
    for (int i = 0; i < 3; i++) corps[13 + i] = IC_JAMBES[pose][i];
    const IC_Bord bords[2] = {{-1, 0, lr, lv, lb, 0.55f}, {0, -1, lr, lv, lb, 0.35f}};
    ic_sprite(corps, 16, px, py, IC_GARE_CLES, IC_GARE_PAL, vers < 0, force, bords, 2);
    if (pose == 0) {
      const IC_Bord bv = {-1, 0, lr, lv, lb, 0.4f};
      ic_sprite(IC_VALISE, 8, vers > 0 ? px + 7 : px - 4, py + 8, IC_GARE_CLES, IC_GARE_PAL, vers < 0, force, &bv, 1);
    } else {                                                  // en marchant, elle roule derriere lui
      ic_sprite(IC_VALISE, 8, px - 4, py + 8, IC_GARE_CLES, IC_GARE_PAL, true, force);
    }
    const float souffle = fmodf(P * 0.29f, 1.0f);             // son souffle, dans le froid
    if (pose == 0 && souffle < 0.45f && force >= 1) {
      const float s = souffle / 0.45f, bx = px + (vers > 0 ? 6 : 0) + vers * (0.5f + s * 2.5f);
      pointer(py + 3 - s * 3, bx, 150 * (1 - s), 160 * (1 - s), 180 * (1 - s));
    }
    if (px < 9) ic_calque(e.dessus, e.masque, 12, 9);         // le reverbere reste devant lui
  }
  const float d = fminf(dt, 0.5f);                            // la neige ; pres d'une lampe, elle brille en croix
  for (int i = 0; i < 34; i++) {
    e.fy[i] = ic_mod(e.fy[i] + e.fv[i] * d, 64);
    e.fx[i] = ic_mod(e.fx[i] + (sinf(t * 0.7f + e.fp[i]) * 0.6f + 0.25f) * d * 3, 64);
    const float proche = (e.fv[i] - 4) / 5;
    float eclat = 0.45f + 0.35f * proche;
    bool croix = false;
    for (int l = 0; l < 2; l++) {
      const float dx = e.fx[i] - IC_GARE_LAMPES[l][0], dy = (e.fy[i] - IC_GARE_LAMPES[l][1]) * 0.8f;
      const float dd = sqrtf(dx * dx + dy * dy), r = IC_GARE_LAMPES[l][2];
      eclat += borne(1.4f - dd / r, 0, 1) * 0.6f;
      croix = croix || (dd < r * 0.7f && proche > 0.45f);
    }
    eclat = fminf(eclat, 1.15f);
    const float r = 215 * eclat, v = 222 * eclat, b = 240 * eclat;
    pointer(e.fy[i], e.fx[i], r, v, b);
    if (croix) {
      pointer(e.fy[i] - 1, e.fx[i], r * 0.45f, v * 0.45f, b * 0.45f);
      pointer(e.fy[i] + 1, e.fx[i], r * 0.45f, v * 0.45f, b * 0.45f);
      pointer(e.fy[i], e.fx[i] - 1, r * 0.45f, v * 0.45f, b * 0.45f);
      pointer(e.fy[i], e.fx[i] + 1, r * 0.45f, v * 0.45f, b * 0.45f);
    }
  }
}

// --- le metro (_scene_metro) -------------------------------------------------------------------------------------
// humeurs : 0 = - (une seule ambiance)
// On est sur le quai, on regarde vers le tunnel : tout ce qui longe la voie fuit vers (14, 36). Le decor est lance
// en rayons une fois (profondeur z en metres, ecart lateral, hauteur sous l'oeil) ; la rame est une texture qui
// glisse sur son flanc, moyennee sur ce que voit chaque colonne (aucun stroboscope).

const float IC_M_VX = 14.0f, IC_M_VY = 36.0f, IC_M_F = 40.0f, IC_M_BOUT = 18.0f;
const float IC_M_MUR = -1.2f, IC_M_BORD = 4.8f, IC_M_RAME = 5.2f, IC_M_RAME2 = 8.0f, IC_M_FACE = 9.0f;
const float IC_M_PAS = 0.08f;   // metres par colonne de texture
const float IC_M_LONG = 46.4f;  // trois voitures de 15.2 m, 0.8 m entre elles
const float IC_M_ARRET = -6.0f; // la tete quand elle est arretee (derriere nous)
const int IC_M_N = 580;
static const float IC_M_PORTES[3] = {2.2f, 6.6f, 11.0f};
static const float IC_M_PAL[16][3] = {   // les couleurs du flanc : portes fermees (bas de l'octet), ouvertes (haut)
  {30, 50, 98}, {120, 130, 136}, {206, 214, 180}, {230, 236, 206}, {54, 54, 64}, {48, 48, 58}, {176, 182, 186},
  {18, 20, 28}, {12, 12, 14}, {42, 66, 116}, {190, 200, 172}, {18, 26, 44}, {50, 62, 78}, {226, 230, 204},
  {110, 112, 104}, {140, 140, 128}};
static const char *const IC_PASSANTE[17] = {   // face a droite, la tete penchee sur son telephone ; t : l'ecran
  "..hhh...", ".hhhhh..", ".hhhss..", ".hhsss..", ".hhss...", ".hkkk...", "kkkkkk..", "kkkkkkst", "kkkkkk..",
  "kkkkkk..", "kkkkkk..", "kkkkkk..", ".kkkkk..", ".kkkkk..", "..p.p...", "..p.p...", ".bb.bb.."};
static const char *const IC_PASSANTE_LEVE[17] = {   // elle a leve la tete vers la rame, le telephone baisse
  "..hhh...", ".hhhhh..", ".hhsss..", ".hhsss..", ".hhs....", ".hkkk...", "kkkkkk..", "kkkkkk..", "kkkkks..",
  "kkkkkd..", "kkkkkk..", "kkkkkk..", ".kkkkk..", ".kkkkk..", "..p.p...", "..p.p...", ".bb.bb.."};
static const char IC_M_CLES[] = "hskpbtd";

struct E_metro {
  uint8_t fond[64][64][3];
  float z[64][64];                  // la profondeur de chaque pixel du decor
  uint8_t quoi[64][64];             // ce qu'il voit : 0 notre quai ... 6 le fond, 7-9 le tunnel
  uint8_t ligne[64][64];            // la ligne de texture du flanc qu'il montre (255 : pas de flanc)
  uint8_t reflet[64][64];           // celle que le sol lisse reflete (255 : rien)
  uint8_t sol[64][64];              // le bord du quai qui recoit la lumiere de la rame (x255 ; 0 : rien)
  uint8_t tex[32][IC_M_N];          // le flanc : index de couleur portes fermees | ouvertes << 4
  uint8_t caisse[IC_M_N];           // 1 la ou il y a une voiture
  float lum_f[IC_M_N], lum_o[IC_M_N];   // la lumiere qu'elle jette, portes fermees et ouvertes
  uint8_t ty[128], tx[128], tf[128];    // les tubes de neon (tf = 2 : celui qui gresille)
  int nt;
  float px[6], py[6], pp[6];            // des poussieres qui flottent sous les neons
};

void ic_metro_texture(E_metro &e) {
  static const float GENS[4][2] = {{3.9f, 0}, {9.4f, 1}, {13.2f, 0}, {5.1f, 0}};
  float lum[IC_M_N], pr[IC_M_N];
  for (int i = 0; i < IC_M_N; i++) {
    const float u = (i + 0.5f) * IC_M_PAS, dans = fmodf(u, 16.0f);
    const bool caisse = dans < 15.2f, pilier = fmodf(dans, 1.3f) < 0.3f, cab = u < 1.6f;
    bool porte_col = false, milieu = false;
    for (int p = 0; p < 3; p++) {
      porte_col = porte_col || (dans >= IC_M_PORTES[p] && dans < IC_M_PORTES[p] + 1.3f);
      milieu = milieu || fabsf(dans - IC_M_PORTES[p] - 0.65f) < 0.05f;
    }
    e.caisse[i] = caisse;
    lum[i] = (!pilier && !cab && caisse) ? 1.0f : 0.0f;
    pr[i] = (porte_col && caisse) ? 1.0f : 0.0f;
    for (int r = 0; r < 32; r++) {
      const float h = -2.0f + (r + 0.5f) * 4.6f / 32;
      const bool vitre = h > -1.35f && h < 0.0f;
      int c = 0;
      if (h < -1.85f) c = 1;                                  // le bord du toit
      if (vitre && !pilier) c = h < -1.15f ? 3 : 2;           // les vitres, le plafonnier en haut
      for (int c0 = 0; c0 < 3; c0++)                          // quelques voyageurs, tard le soir
        for (int g = 0; g < 4; g++) {
          if (fmodf(c0 * 16 * 1.7f + GENS[g][0] * 3.1f, 5.0f) >= 2.6f) continue;
          const float x = c0 * 16 + GENS[g][0], hd = GENS[g][1] > 0 ? -0.95f : -0.7f;
          if (vitre && fabsf(u - x) < 0.16f && h > hd && h < hd + 0.3f) c = 4;
          if (vitre && fabsf(u - x) < 0.3f && h >= hd + 0.3f) c = 5;
        }
      if (h >= 0 && h < 0.2f) c = 6;                          // la bande blanche
      if (h >= 1.75f) c = 7;
      if (h >= 2.0f) c = 8;
      int o = c;
      if (porte_col && h > -1.5f && h < 1.7f) {               // les portes : fermees, ou ouvertes sur l'interieur
        c = 9;
        if (h > -1.2f && h < -0.25f && ic_mod(dans - 0.1f, 0.65f) < 0.5f) c = 10;
        if (milieu) c = 11;
        o = 13;
        if (milieu && h > -1.4f) o = 14;
        if (h > 1.4f) o = 15;
      }
      if (cab && vitre) c = o = 12;                           // la cabine de tete
      e.tex[r][i] = (uint8_t)(c | (o << 4));
    }
  }
  for (int i = 0; i < IC_M_N; i++) {                          // adoucie : c'est une lumiere diffuse
    float sf = 0, so = 0;
    for (int k = -4; k <= 4; k++)
      if (i + k >= 0 && i + k < IC_M_N) { sf += lum[i + k] + pr[i + k] * 0.3f; so += lum[i + k] + pr[i + k] * 2.4f; }
    e.lum_f[i] = sf / 9; e.lum_o[i] = so / 9;
  }
}

void ic_metro_decor(E_metro &e) {
  const float f = IC_M_F, zb = IC_M_BOUT, INF = 1e9f;
  float sx = 0, sy = 0;
  int sn = 0;                                                 // le centre de l'affiche, pour sa lueur
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      const float dx = x + 0.5f - IC_M_VX, dy = y + 0.5f - IC_M_VY;
      float zs[10];
      auto plan_h = [&](float h, float l0, float l1, float z0, float z1) {   // un plan horizontal (h > 0 : sous l'oeil)
        const float z = f * h / dy, lat = dx * z / f;
        return (z > z0 && z <= z1 && lat >= l0 && lat <= l1) ? z : INF;
      };
      auto plan_v = [&](float lat, float h0, float h1, float z0, float z1) {   // un plan vertical, le long de la voie
        const float z = f * lat / dx, h = dy * z / f;
        return (z > z0 && z <= z1 && h >= h0 && h <= h1) ? z : INF;
      };
      zs[0] = plan_h(1.6f, IC_M_MUR, IC_M_BORD, 0, zb);       // notre quai
      zs[1] = plan_v(IC_M_BORD, 1.6f, 2.6f, 0, zb);           // son flanc
      zs[2] = plan_h(2.6f, IC_M_BORD, IC_M_FACE, 0, zb);      // la voie
      zs[3] = plan_v(IC_M_FACE, -4.2f, 2.6f, 0, zb);          // le mur d'en face
      zs[4] = plan_v(IC_M_MUR, -4.2f, 1.6f, 0, zb);           // notre mur
      zs[5] = plan_h(-4.2f, IC_M_MUR, IC_M_FACE, 0, zb);      // la voute
      const float lat_b = dx * zb / f, h_b = dy * zb / f;     // le mur du fond, et la bouche du tunnel
      const float q = (lat_b - 6.95f) / 1.95f;
      const float arche = -1.3f - 1.5f * sqrtf(borne(1 - q * q, 0, 1));
      const bool bouche = lat_b >= 5.0f && lat_b <= 8.9f && h_b >= arche && h_b <= 2.6f;
      zs[6] = (lat_b >= IC_M_MUR && lat_b <= IC_M_FACE && h_b >= -4.2f && h_b <= 2.6f && !bouche) ? zb : INF;
      zs[7] = plan_v(8.9f, -2.8f, 2.6f, zb, 90);
      zs[8] = plan_h(2.6f, 5.0f, 8.9f, zb, 90);
      zs[9] = plan_h(-2.8f, 5.0f, 8.9f, zb, 90);
      int quoi = 0;
      for (int k = 1; k < 10; k++) if (zs[k] < zs[quoi]) quoi = k;
      float z = zs[quoi];
      if (z >= INF) { quoi = 7; z = 90; }
      const float lat = dx * z / f, h = dy * z / f;
      e.z[y][x] = z;
      e.quoi[y][x] = (uint8_t)quoi;
      static const float TEINTES[10][3] = {{70, 64, 60}, {20, 20, 22}, {18, 16, 16}, {160, 174, 160}, {96, 106, 96},
                                           {52, 58, 54}, {84, 94, 86}, {12, 12, 14}, {10, 10, 12}, {10, 10, 12}};
      float al[3] = {TEINTES[quoi][0], TEINTES[quoi][1], TEINTES[quoi][2]};
      auto prendre = [&](float r, float v, float b) { al[0] = r; al[1] = v; al[2] = b; };
      if (quoi == 0 && lat > IC_M_BORD - 0.45f) prendre(176, 176, 160);   // le bord du quai, en pierre claire
      if (quoi == 0 && lat > IC_M_BORD - 0.85f && lat <= IC_M_BORD - 0.65f) prendre(130, 116, 64);   // la bande d'eveil
      if (quoi == 2 && (fabsf(lat - 5.85f) < 0.1f || fabsf(lat - 7.35f) < 0.1f)) prendre(120, 126, 126);   // les rails
      if ((quoi == 3 || quoi == 4) && fabsf(h + 2.45f) < 0.13f) prendre(40, 96, 72);   // la frise de carreaux verts
      if (quoi == 3 && h > 1.5f) prendre(60, 64, 60);
      if (quoi == 6 && !bouche && lat_b > 4.6f &&
          sqrtf((lat_b - 6.95f) * (lat_b - 6.95f) + fminf(h_b - arche, 0) * fminf(h_b - arche, 0)) < 2.3f)
        prendre(150, 160, 146);                               // l'encadrement du tunnel
      if (quoi == 4 && h > 0.72f && h < 1.15f && z > 3 && z < 14 && fmodf(z, 0.62f) > 0.1f) prendre(210, 96, 40);   // les sieges
      const bool plaque = quoi == 3 && h > -2.75f && h < -2.1f && z > 6.6f && z < 9.0f;
      if (plaque) prendre(30, 52, 130);                       // la plaque du nom de la station
      if (plaque && h > -2.58f && h < -2.27f && fmodf(z - 6.8f, 0.4f) < 0.26f && z > 6.85f && z < 8.75f)
        prendre(240, 240, 230);
      const float d1 = sqrtf((lat - 1.8f) * (lat - 1.8f) + (h + 4) * (h + 4));   // la lumiere des deux rangees de neons
      const float d2 = sqrtf((lat - 7.4f) * (lat - 7.4f) + (h + 4) * (h + 4));
      float lum = 1.0f / (1 + (d1 / 1.5f) * (d1 / 1.5f)) + 0.8f / (1 + (d2 / 1.5f) * (d2 / 1.5f));
      if (quoi == 0) {                                        // sous chaque tube, une flaque sur le sol
        float flaques = 0;
        for (float zc = 3.2f; zc < zb + 1.2f; zc += 3.5f) flaques += expf(-((z - zc) / 1.5f) * ((z - zc) / 1.5f));
        lum = 0.25f * lum + 0.75f * flaques * expf(-((lat - 1.8f) / 1.9f) * ((lat - 1.8f) / 1.9f));
      }
      lum = (0.05f + 1.2f * lum) * (0.45f + 0.55f * expf(-z / 9));
      if (quoi == 6) lum = 0.5f + 0.4f * expf(-fabsf(h_b + 1.0f) / 2);   // le fond, sous le dernier tube
      if (quoi >= 7) lum = 0.25f;
      float r = al[0] * lum * 0.84f, v = al[1] * lum, b = al[2] * lum * 0.88f;   // un peu verdatre
      if (quoi == 3 && z > 8.4f && z < 12.2f && h > -1.75f && h < 0.35f) {   // l'affiche lumineuse : un coucher de soleil
        const float au = (12.2f - z) / 3.8f, av = (h + 1.75f) / 2.1f, c = borne(av / 0.6f, 0, 1);
        r = 170 * (1 - c) + 255 * c; v = 60 * (1 - c) + 160 * c; b = 100 * (1 - c) + 80 * c;
        if (av > 0.62f) {
          const bool vague = ic_mod((av - 0.6f) * 12 + au * 2, 1.0f) < 0.3f;
          r = 26 + (vague ? 40 : 0); v = 50 + (vague ? 40 : 0); b = 110 + (vague ? 24 : 0);
        }
        if (sqrtf((au - 0.62f) * 1.7f * (au - 0.62f) * 1.7f + (av - 0.5f) * (av - 0.5f)) < 0.15f) { r = 255; v = 236; b = 170; }
        if (au < 0.05f || au > 0.95f || av < 0.08f || av > 0.92f) { r = 64; v = 54; b = 40; }
        sx += x; sy += y; sn++;
      }
      if (quoi == 4 && z > 3.6f && z < 6.4f && h > -1.1f && h < 0.4f) {   // le plan du quartier, eclaire
        const float pu = (z - 3.6f) / 2.8f, pv = (h + 1.1f) / 1.5f;
        r = 128; v = 142; b = 134;
        if (fabsf(pv - 0.35f) < 0.06f) { r = 170; v = 70; b = 64; }
        if (fabsf(pu - 0.45f) < 0.08f) { r = 70; v = 96; b = 160; }
        if (pu < 0.08f || pu > 0.92f || pv < 0.06f || pv > 0.94f) { r = 40; v = 44; b = 48; }
      }
      peindre(y, x, r, v, b);
      // la rame et son reflet : quelle ligne de texture chaque pixel montre
      const float zt = dx > 0.6f ? f * IC_M_RAME / dx : INF, ht = dy * zt / f;
      e.ligne[y][x] = (dx > 0.6f && zt < z && ht >= -2.0f && ht < 2.6f) ? (uint8_t)borne((ht + 2.0f) / 4.6f * 32, 0, 31) : 255;
      const float hr = 3.2f - ht;
      e.reflet[y][x] = (quoi == 0 && dx > 0.6f && hr >= -2.0f && hr < 1.6f) ? (uint8_t)borne((hr + 2.0f) / 4.6f * 32, 0, 31) : 255;
      e.sol[y][x] = (quoi == 0 && lat > 2.2f) ? (uint8_t)fmaxf(1, roundf(255 * expf(-(IC_M_BORD - lat) / 0.9f))) : 0;
    }
  if (sn) halo(sx / sn, sy / sn, 5, 255, 140, 90, 0.3f, 0.9f);
  halo(4, 32, 4, 150, 200, 190, 0.25f, 0.7f);
  halo(6, 45, 5, 150, 200, 190, 0.3f, 2.0f);                  // la lueur du plan sur le sol
  uint8_t (*marque)[64] = (uint8_t (*)[64])&e.tex[0][0];      // les tubes (brouillon : la texture vient apres)
  memset(marque, 0, 64 * 64);                                 // 2.4 m allumes, 1.1 m d'ombre
  const float lignes_t[2] = {1.8f, 7.4f};
  for (int l = 0; l < 2; l++) {
    int compte = 0;
    for (int k = 0; 2.0f + k * 0.03f < zb; k++) {
      const float tz = 2.0f + k * 0.03f;
      if (fmodf(tz, 3.5f) >= 2.4f) continue;
      const float txf = IC_M_VX + f * lignes_t[l] / tz, tyf = IC_M_VY - f * 4.0f / tz;
      if (tyf < 0 || tyf >= 64 || txf < 0 || txf >= 64) continue;
      const int tid = (int)(tz / 3.5f) + (int)(lignes_t[l] * 10 + 0.001f);
      marque[(int)tyf][(int)txf] = tid == 20 ? 2 : 1;
      if (compte % 5 == 0) halo(txf, tyf, 1.6f, 150, 220, 170, 0.10f);   // leur lueur
      compte++;
    }
  }
  e.nt = 0;
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      if (marque[y][x] && e.nt < 128) { e.ty[e.nt] = y; e.tx[e.nt] = x; e.tf[e.nt] = marque[y][x]; e.nt++; }
  ic_garder(e.fond);
}

// la moyenne de la ligne r du flanc entre a et b (en colonnes de texture), portes ouvertes a `ouv`
inline void ic_metro_moyenne(const E_metro &e, int r, float a, float b, float ouv, float out[4]) {
  out[0] = out[1] = out[2] = out[3] = 0;
  const int i0 = max(0, (int)floorf(a)), i1 = min(IC_M_N - 1, (int)floorf(b));
  for (int i = i0; i <= i1; i++) {
    if (!e.caisse[i]) continue;
    const float w = fminf(b, i + 1.0f) - fmaxf(a, (float)i);
    if (w <= 0) continue;
    const uint8_t k = e.tex[r][i];
    const float *cf = IC_M_PAL[k & 15];
    if (ouv > 0) {
      const float *co = IC_M_PAL[k >> 4];
      for (int c = 0; c < 3; c++) out[c] += w * (cf[c] * (1 - ouv) + co[c] * ouv);
    } else {
      for (int c = 0; c < 3; c++) out[c] += w * cf[c];
    }
    out[3] += w;
  }
  const float inv = 1.0f / fmaxf(b - a, 1e-6f);
  for (int c = 0; c < 4; c++) out[c] *= inv;
}

void s_metro(int humeur, bool debut, float t, float ecoule, float dt) {
  E_metro &e = etat_ecran<E_metro>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    ic_metro_decor(e);
    ic_metro_texture(e);
    for (int i = 0; i < 6; i++) { e.px[i] = hasard(18, 62); e.py[i] = hasard(4, 40); e.pp[i] = hasard(0, 6.3f); }
  }
  const float f = IC_M_F;
  const float P = ic_mod(t + 51.0f, 60.0f);
  float sh, v;
  if (P < 16) {                                               // elle arrive du tunnel et ralentit
    const float u = P / 16;
    sh = IC_M_ARRET + 81 * (1 - u) * (1 - u); v = 2 * 81 * (1 - u) / 16;
  } else if (P < 32) {
    sh = IC_M_ARRET; v = 0;
  } else {                                                    // elle repart vers nous
    const float u = fminf((P - 32) / 16, 1.0f);
    sh = IC_M_ARRET - 48 * u * u; v = 2 * 48 * u / 16;
  }
  const float ouv = ic_lisse(P - 17.5f) * ic_lisse(29.0f - P);
  ic_recopier(e.fond);
  const float lueur = sh > 16 ? borne((80 - sh) / 45, 0, 1) : borne((sh - 6) / 10, 0, 1);
  if (lueur > 0) {                                            // les phares eclairent le tunnel avant elle
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        const float zt = e.z[y][x];
        if (e.quoi[y][x] >= 7 && zt < sh + 1) ajouter(y, x, lueur * expf(-fabsf(sh - 2 - zt) / 7.0f), 150, 160, 140);
      }
    ic_halo(IC_M_VX + f * 7 / IC_M_BOUT, IC_M_VY + 2, 4.5f, 200, 210, 180, 0.4f * lueur, 1.2f);
  }
  const bool present = sh + IC_M_LONG > 2.0f;
  float ca[64], cb[64], sombre[64];                           // ce que chaque colonne voit du flanc
  if (present) {
    const float m = v / 30 / 2;                               // et le flou du mouvement
    for (int x = 0; x < 64; x++) {
      const float xs = x - IC_M_VX;
      const float z0 = xs + 1 > 0.6f ? f * IC_M_RAME / fmaxf(xs + 1, 0.6f) : 1e9f;
      const float z1 = xs > 0.3f ? f * IC_M_RAME / fmaxf(xs, 0.3f) : 1e9f;
      ca[x] = (fminf(z0, 400) - sh - m) / IC_M_PAS;
      cb[x] = (fminf(z1, 400) - sh + m) / IC_M_PAS;
      const float zc = x + 0.5f - IC_M_VX > 0.6f ? f * IC_M_RAME / (x + 0.5f - IC_M_VX) : 1e9f;
      sombre[x] = 1 - 0.8f * borne((zc - IC_M_BOUT + 1.5f) / 2, 0, 1);   // dans le tunnel, elle est dans le noir
    }
    float s[4];
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        if (e.reflet[y][x] != 255) {                          // son reflet dans le sol lisse
          ic_metro_moyenne(e, e.reflet[y][x], ca[x], cb[x], ouv, s);
          const float k = 0.16f + 0.12f * borne((e.z[y][x] - 3) / 8, 0, 1);
          ajouter(y, x, k, s[0], s[1], s[2]);
        }
        if (e.sol[y][x]) {                                    // la lumiere qu'elle jette sur le bord du quai
          const float uu = (e.z[y][x] - sh) / IC_M_PAS;
          if (uu >= 0 && uu <= IC_M_N - 1) {
            const int i = min(IC_M_N - 2, (int)uu);
            const float fr = uu - i;
            const float lf = e.lum_f[i] * (1 - fr) + e.lum_f[i + 1] * fr, lo = e.lum_o[i] * (1 - fr) + e.lum_o[i + 1] * fr;
            ajouter(y, x, (lf * (1 - ouv) + lo * ouv) * e.sol[y][x] * (1.0f / 255), 110, 116, 96);
          }
        }
      }
    if (sh > 2.5f && sh < 30) {                               // le faisceau des phares sur la voie, devant
      const float zf = fmaxf(sh - 3.0f, 1.5f);
      ic_halo(IC_M_VX + f * 6.6f / zf, IC_M_VY + f * 2.4f / zf, 1.5f + 12 / zf, 230, 236, 210,
              0.5f * fminf(1.0f, (30 - sh) / 6), 2.0f);
    }
  }
  tramer(10);
  float gres = 1;                                             // les tubes, nets ; l'un gresille rarement
  const float cy = ic_mod(t + 20.0f, 47.0f);
  if (cy < 1.6f) {
    const float s = sinf(cy * 11);
    gres = 1 - 0.45f * sinf(cy / 1.6f * 3.14159265f) * (0.7f + 0.3f * s * s);
  }
  for (int i = 0; i < e.nt; i++) {
    const float k = e.tf[i] == 2 ? gres : 1.0f;
    peindre(e.ty[i], e.tx[i], 200 * k, 255 * k, 220 * k);
  }
  if (present) {                                              // le flanc, en aplats nets
    float s[4];
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        if (e.ligne[y][x] == 255) continue;
        ic_metro_moyenne(e, e.ligne[y][x], ca[x], cb[x], ouv, s);
        if (s[3] <= 0) continue;
        float *p = scene[y][x];
        for (int c = 0; c < 3; c++) p[c] = p[c] * (1 - s[3]) + s[c] * sombre[x];
      }
  }
  if (sh > 2.0f && sh < 60) {                                 // la face avant, qui grandit en sortant du tunnel
    const int xa = max(0, (int)floorf(IC_M_VX + f * IC_M_RAME / sh - 0.5f)), xb = min(63, (int)ceilf(IC_M_VX + f * IC_M_RAME2 / sh));
    const int ya = max(0, (int)floorf(IC_M_VY - f * 2.0f / sh - 0.5f)), yb = min(63, (int)ceilf(IC_M_VY + f * 1.8f / sh));
    const float noir = 1 - 0.75f * borne((sh - IC_M_BOUT + 1) / 3, 0, 1);
    for (int y = ya; y <= yb; y++)
      for (int x = xa; x <= xb; x++) {
        const float lat = (x + 0.5f - IC_M_VX) * sh / f, ha = (y + 0.5f - IC_M_VY) * sh / f;
        if (lat < IC_M_RAME || lat > IC_M_RAME2 || ha < -2.0f || ha > 1.8f || sh >= e.z[y][x]) continue;
        const float la = lat - IC_M_RAME;
        float r = 30, g = 50, b = 98;
        if (ha > -1.3f && ha < -0.3f && fabsf(la - 1.4f) > 0.15f && la > 0.25f && la < 2.55f) { r = 50; g = 62; b = 76; }
        if (ha > -1.8f && ha < -1.45f && la > 0.6f && la < 2.2f) { r = 255; g = 170; b = 60; }   // la girouette
        if (ha > 1.55f) { r = 16; g = 18; b = 24; }
        peindre(y, x, r * noir, g * noir, b * noir);
      }
    const float phares[2] = {IC_M_RAME + 0.5f, IC_M_RAME2 - 0.5f};
    for (int k = 0; k < 2; k++) {
      const float px = IC_M_VX + f * phares[k] / sh, py = IC_M_VY + f * 0.75f / sh;
      if (px >= 0 && px < 64 && py >= 0 && py < 64 && sh < e.z[(int)py][(int)px] + 0.5f) {
        halo(px, py, 0.6f + 3 / sh, 255, 250, 225, 1.0f);
        peindre((int)py, (int)px, 255, 252, 236);
      }
    }
  }
  const float dd = fminf(dt, 0.5f);                          // les poussieres : elles descendent, louvoient, s'eteignent
  for (int i = 0; i < 6; i++) {
    e.py[i] += 0.6f * dd;
    e.px[i] += sinf(t * 0.3f + e.pp[i]) * 0.5f * dd;
    if (e.py[i] > 44) { e.py[i] = hasard(2, 10); e.px[i] = hasard(18, 62); }
    const float k = 0.5f + 0.5f * sinf(t * 0.7f + e.pp[i] * 3);
    pointer(e.py[i], e.px[i], 120 * k, 160 * k, 135 * k);
  }
  float pas[7][3] = {{44, 30, 26}, {150, 112, 96}, {40, 46, 54}, {26, 26, 34}, {14, 14, 18}, {190, 230, 255}, {40, 50, 60}};
  const IC_Bord bords[2] = {{0, -1, 170, 220, 190, 0.45f}, {-1, 0, 140, 190, 160, 0.3f}};
  if (P > 3.0f && P < 22.0f) {                                // elle leve la tete vers la rame
    ic_sprite(IC_PASSANTE_LEVE, 17, 40, 35, IC_M_CLES, pas, true, 1.0f, bords, 2);
  } else {
    pas[1][0] = 120; pas[1][1] = 150; pas[1][2] = 190;        // l'ecran bleuit son visage
    ic_sprite(IC_PASSANTE, 17, 40, 35, IC_M_CLES, pas, true, 1.0f, bords, 2);
    halo(40.5f, 42.5f, 1.0f, 90, 140, 220, 0.5f);
  }
}

// --- le toit (_scene_toit) -----------------------------------------------------------------------------------------
// humeurs : 0 = - (une seule ambiance)
// Le rebord du toit en bas, la ville en contrebas qui s'etale jusqu'a l'horizon et sa brume orangee qui monte, le
// ciel au-dessus ; le chat, sur le pilier d'angle, se decoupe sur cette lueur.

const int IC_T_HZ = 44;   // l'horizon : la ville au-dessous, la lueur juste au-dessus
static const int IC_T_TOURS[6][4] = {   // le centre-ville au loin : x0, x1, sommet, toit (0 plat, 1 antenne,
  {14, 18, 31, 1}, {19, 24, 22, 2}, {25, 28, 33, 0}, {29, 33, 26, 3}, {34, 38, 35, 0}, {39, 41, 38, 0}};   // 2 gradins, 3 pointe
static const char *const IC_CHAT_DOS[14] = {   // assis, de dos, il regarde la ville
  "...k...k...", "...kk.kk...", "...kkkkk...", "..kkkkkkk..", "..kkkkkkk..", "...kkkkk...", "....kkk....",
  "...kkkkk...", "..kkkkkkk..", ".kkkkkkkkk.", ".kkkkkkkkk.", "kkkkkkkkkkk", "kkkkkkkkkkk", ".kkkkkkkkk."};
static const char *const IC_CHAT_TOURNE[14] = {   // il tourne la tete vers la gauche : on voit son museau
  "..k...k....", "..kk.kk....", "..kkkkk....", ".kkkkkkk...", "kkkkkkkk...", "..kkkkk....", "....kkk....",
  "...kkkkk...", "..kkkkkkk..", ".kkkkkkkkk.", ".kkkkkkkkk.", "kkkkkkkkkkk", "kkkkkkkkkkk", ".kkkkkkkkk."};
static const char *const IC_CHEMISE[4] = {"ccccc", "ccccc", ".ccc.", ".ccc."};
static const char *const IC_CHAUSSETTE[3] = {"r.", "r.", "rr"};

struct E_toit {
  uint8_t fond[64][64][3], dessus[64][64][3], masque[64][64];
  uint8_t ey[29], ex0[29], ex1[29], blanc[29];   // les etages des tours
  float periode[29], phase[29], part[29];
  int ne;
  uint8_t ly[2], lx[2];                          // les feux rouges en haut des tours
  uint8_t py[96], px[96], chaud[96];             // les rues, en contrebas
  int np;
  uint8_t sx[14], sy[14];                        // les etoiles
  float sp[14], vapeur[9];
};

void ic_toit_decor(E_toit &e) {
  const int hz = IC_T_HZ;
  degrade2(5, 6, 20, 26, 18, 44, 0, hz);
  for (int y = 0; y <= hz; y++) {                             // la brume orangee qui monte de la ville
    const float k = expf(-(hz - y) / 9.0f);
    for (int x = 0; x < 64; x++) ajouter(y, x, k, 150, 76, 44);
  }
  halo(53, 11, 7, 100, 110, 140, 0.4f);
  for (int y = hz + 1; y < 64; y++) {                         // la ville en contrebas, plus sombre vers nous
    const float k = borne((y - hz) / 10.0f, 0, 1);
    for (int x = 0; x < 64; x++) peindre(y, x, 84 * (1 - k) + 16 * k, 46 * (1 - k) + 12 * k, 50 * (1 - k) + 24 * k);
  }
  e.ne = 0;
  int nl = 0;
  for (int i = 0; i < 6; i++) {
    const int x0 = IC_T_TOURS[i][0], x1 = IC_T_TOURS[i][1], haut = IC_T_TOURS[i][2], toit = IC_T_TOURS[i][3];
    for (int y = max(0, haut - 7); y <= hz; y++)
      for (int x = x0 - 1; x <= x1; x++) {
        bool corps = x >= x0 && x < x1 && y >= haut;
        if (toit == 2) {                                      // un sommet en gradins, un mat
          corps = corps && (y >= haut + 4 || (x >= x0 + 1 && x < x1 - 1));
          corps = corps || (x == (x0 + x1) / 2 && y >= haut - 2 && y < haut);
        }
        if (toit == 3) corps = corps && (y >= haut + 2 || fabsf(x - (x0 + x1 - 1) / 2.0f) <= y - haut + 0.5f);   // en pointe
        if (toit == 1) corps = corps || (x == x0 + 2 && y >= haut - 6 && y < haut);   // une antenne
        if (corps) peindre(y, x, 16, 12, 26);
      }
    if (toit == 2) { e.ly[nl] = haut - 3; e.lx[nl] = (x0 + x1) / 2; nl++; }
    if (toit == 1) { e.ly[nl] = haut - 7; e.lx[nl] = x0 + 2; nl++; }
    for (int fy = haut + 3; fy < hz - 1; fy += 2)            // ses etages, qui s'allument chacun a son tour
      if (e.ne < 29) { e.ey[e.ne] = fy; e.ex0[e.ne] = x0 + 1; e.ex1[e.ne] = x1 - 1; e.ne++; }
  }
  for (int x = 0; x < 42; x++) {                              // la ligne basse des immeubles, a gauche
    const float crete = hz - 2 - (sinf(x * 1.3f) > 0.2f ? 1 : 0) - (sinf(x * 0.55f + 1) > 0.5f ? 2 : 0);
    for (int y = (int)ceilf(crete); y <= hz; y++) peindre(y, x, 20, 14, 30);
  }
  static const int RUES[5][2] = {{45, 2}, {46, 3}, {48, 4}, {50, 5}, {53, 6}};   // les rues : des lampadaires en rangees
  e.np = 0;
  for (int k = 0; k < 5; k++) {
    const int ry = RUES[k][0], pas = RUES[k][1];
    for (int x = (int)(aleatoire() % pas); x < 64; x += pas)
      if (hasard(0, 1) < 0.8f && !(x >= 42 && x <= 58 && ry >= 46) && e.np < 96) {
        e.py[e.np] = ry; e.px[e.np] = x; e.chaud[e.np] = hasard(0, 1) < 0.8f; e.np++;
      }
  }
  for (int i = 0; i < e.ne; i++) {
    e.periode[i] = hasard(50, 220); e.phase[i] = hasard(0, 1); e.part[i] = hasard(0.3f, 0.75f); e.blanc[i] = hasard(0, 1) < 0.3f;
  }
  ic_garder(e.fond);
  uint8_t (*d)[64][3] = e.dessus;
  uint8_t (*m)[64] = e.masque;
  ic_rect(d, m, 0, 63, 55, 63, 26, 20, 30);                   // le rebord : sa face de briques
  for (int y = 57; y < 64; y++)
    for (int x = 0; x < 64; x++)
      if ((y - 57) % 3 == 2 || ((x + (y / 3) * 3) % 7) == 0) ic_rect(d, m, x, x, y, y, 20, 15, 24);
  ic_rect(d, m, 0, 63, 55, 55, 118, 96, 104);                 // sa margelle, que la lueur eclaire
  ic_rect(d, m, 0, 63, 56, 56, 62, 50, 60);
  ic_rect(d, m, 42, 58, 47, 54, 30, 23, 34);                  // le pilier d'angle, ou le chat s'assoit
  for (int y = 49; y <= 54; y += 3) ic_rect(d, m, 42, 58, y, y, 22, 17, 26);
  ic_rect(d, m, 41, 59, 46, 46, 132, 104, 108);
  ic_rect(d, m, 41, 59, 47, 47, 70, 54, 62);
  ic_rect(d, m, 9, 9, 13, 54, 60, 64, 90);                    // l'antenne de television, sur le rebord
  ic_rect(d, m, 7, 11, 14, 14, 60, 64, 90);
  ic_rect(d, m, 6, 12, 17, 17, 60, 64, 90);
  ic_rect(d, m, 5, 13, 20, 20, 60, 64, 90);
  ic_rect(d, m, 23, 27, 49, 54, 34, 26, 36);                  // une cheminee sur le rebord
  for (int y = 51; y <= 54; y += 3) ic_rect(d, m, 23, 27, y, y, 24, 18, 28);
  ic_rect(d, m, 22, 28, 48, 48, 120, 96, 104);
  ic_rect(d, m, 22, 28, 49, 49, 60, 48, 58);
  for (int i = 0; i < 14; i++) { e.sx[i] = aleatoire() % 64; e.sy[i] = 1 + aleatoire() % 19; e.sp[i] = hasard(0, 6.3f); }
  for (int i = 0; i < 9; i++) e.vapeur[i] = hasard(0, 1);
}

void s_toit(int humeur, bool debut, float t, float ecoule, float dt) {
  E_toit &e = etat_ecran<E_toit>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) ic_toit_decor(e);
  const int hz = IC_T_HZ;
  ic_recopier(e.fond);
  float souffle = 0.85f + 0.1f * sinf(t * 0.6f) + 0.05f * sinf(t * 1.7f);   // l'enseigne respire, gresille rarement
  const float cy = ic_mod(t + 28.0f, 41.0f);
  if (cy < 1.2f) souffle *= 1 - 0.4f * sinf(cy / 1.2f * 3.14159265f);
  ic_halo(36, 33, 3.0f, 255, 70, 130, 0.55f * souffle);
  tramer(8);
  for (int i = 0; i < 14; i++) {                              // quelques etoiles, en haut
    const float k = (0.5f + 0.3f * sinf(t * 0.8f + e.sp[i])) * 150;
    pointer(e.sy[i], e.sx[i], k, k, k * 1.15f);
  }
  for (int y = 7; y <= 15; y++)                               // la lune
    for (int x = 49; x <= 57; x++)
      if ((x - 53.0f) * (x - 53.0f) + (y - 11.0f) * (y - 11.0f) <= 3.4f * 3.4f) peindre(y, x, 234, 230, 206);
  peindre(10, 54, 206, 200, 178); peindre(12, 52, 206, 200, 178); peindre(11, 55, 206, 200, 178);
  for (int i = 0; i < e.ne; i++) {                            // les etages des tours, un a un, en fondu
    const float c = ic_mod(t / e.periode[i] + e.phase[i], 1.0f), eps = 1.8f / e.periode[i];
    const float a = ic_lisse(c / eps) * ic_lisse((e.part[i] - c) / eps);
    if (a <= 0.02f) continue;
    const float k = 0.25f + 0.6f * a;
    for (int x = e.ex0[i]; x < e.ex1[i]; x += 2)
      if (e.blanc[i]) pointer(e.ey[i], x, 200 * k, 210 * k, 230 * k);
      else pointer(e.ey[i], x, 255 * k, 184 * k, 100 * k);
  }
  for (int i = 0; i < e.np; i++) {                            // les rues, en contrebas
    const float k = e.py[i] > hz + 4 ? 0.9f : 1.0f;
    if (e.chaud[i]) peindre(e.py[i], e.px[i], 255 * k, 170 * k, 80 * k);
    else peindre(e.py[i], e.px[i], 210 * k, 214 * k, 230 * k);
  }
  static const float AUTOS[4][5] = {{49, 3.0f, 255, 240, 210}, {49, -2.4f, 230, 50, 40}, {52, 4.0f, 255, 240, 210},
                                    {52, -3.2f, 230, 50, 40}};
  for (int k = 0; k < 4; k++) {                               // des voitures, tout en bas, dans les rues
    const float vx = ic_mod(k * 17.0f + t * AUTOS[k][1], 80) - 8;
    if (vx < 41 || vx > 59) pointer(AUTOS[k][0], vx, AUTOS[k][2], AUTOS[k][3], AUTOS[k][4]);
  }
  const float rouge = 0.5f + 0.5f * cosf(borne((ic_mod(t + 2.2f, 2.4f) - 0.6f) / 0.6f, -1, 1) * 3.14159265f);
  for (int i = 0; i < 2; i++) peindre(e.ly[i], e.lx[i], 255 * (0.3f + 0.7f * rouge), 50 * (0.3f + 0.7f * rouge),
                                      40 * (0.3f + 0.7f * rouge));   // les feux des tours
  const float ro = 255 * souffle, vo = 80 * souffle, bo = 140 * souffle;   // l'enseigne, sur le toit de sa tour
  for (int x = 34; x < 38; x++) peindre(33, x, ro, vo, bo);
  peindre(32, 34, ro, vo, bo); peindre(32, 36, ro, vo, bo);
  const float P = ic_mod(t + 13.0f, 70.0f);                   // l'avion, une fois par minute et quelque
  if (P < 46) {
    const float u = P / 46, avx = 68 - 76 * u, avy = 17 - 6 * u;
    const float fl = (ic_mod(t + 1.0f, 1.5f) - 0.2f) / 0.12f, flash = expf(-fl * fl);   // doux : il monte, redescend
    pointer(avy, avx, 255 * 0.7f, 70 * 0.7f, 60 * 0.7f);
    pointer(avy, avx + 1, 255 * (0.2f + 0.8f * flash), 255 * (0.2f + 0.8f * flash), 255 * (0.2f + 0.8f * flash));
    if (flash > 0.3f) {
      const float k = flash - 0.3f;
      pointer(avy - 1, avx + 1, 200 * k, 210 * k, 255 * k); pointer(avy + 1, avx + 1, 200 * k, 210 * k, 255 * k);
      pointer(avy, avx, 200 * k, 210 * k, 255 * k); pointer(avy, avx + 2, 200 * k, 210 * k, 255 * k);
    }
  }
  ic_calque(e.dessus, e.masque);
  const float vent = 0.6f * sinf(t * 0.7f) + 0.4f * sinf(t * 1.27f + 1.0f);
  for (int x = 0; x < 9; x++) peindre((int)roundf(25 + 1.2f * sinf(3.14159265f * x / 9)), x, 70, 70, 92);   // le fil
  struct Linge { const char *const *l; int n, x0; float r, v, b, ph; };
  static const Linge LINGE[3] = {{IC_CHEMISE, 4, 0, 168, 176, 202, 0.0f}, {IC_CHAUSSETTE, 3, 5, 186, 70, 72, 1.3f},
                                 {IC_CHAUSSETTE, 3, 7, 186, 70, 72, 2.1f}};
  for (int i = 0; i < 3; i++) {                               // le linge : le bas bouge plus que le haut
    const Linge &li = LINGE[i];
    const int larg = (int)strlen(li.l[0]);
    const int y0 = (int)roundf(25 + 1.2f * sinf(3.14159265f * (li.x0 + larg / 2.0f) / 9)) + 1;
    const float bat = (vent * cosf(li.ph) + 0.4f * sinf(t * 1.9f + li.ph)) * 1.2f;
    for (int r = 0; r < li.n; r++) {
      const float q = (float)r / li.n, dec = bat * powf(q, 1.3f);
      const float k = 0.85f + (r == 0 ? 0.2f : 0) - (r == li.n - 1 ? 0.15f : 0);
      for (int c = 0; c < larg; c++)
        if (li.l[r][c] != '.') {
          const int xx = (int)floorf(li.x0 + c + dec + 0.5f);
          if (xx >= 0 && xx < 64) peindre(y0 + r, xx, li.r * k, li.v * k, li.b * k);
        }
    }
  }
  for (int i = 0; i < 9; i++) {                               // la vapeur de la cheminee, en bouffees
    const float age = ic_mod(e.vapeur[i] + t / 3.4f, 1.0f);
    const float vx = 25 + age * 6 * (0.6f + 0.4f * vent) + sinf(age * 5 + e.vapeur[i] * 9) * 0.8f, vy = 47 - age * 12;
    const float g = powf(1 - age, 1.2f) * fminf(age * 6, 1.0f) * 0.95f;
    pointer(vy, vx, 200 * g, 192 * g, 206 * g);
    pointer(vy, vx + 1, 200 * g * 0.7f, 192 * g * 0.7f, 206 * g * 0.7f);
    if (age > 0.3f) {
      pointer(vy - 1, vx, 200 * g * 0.6f, 192 * g * 0.6f, 206 * g * 0.6f);
      pointer(vy - 1, vx + 1, 200 * g * 0.45f, 192 * g * 0.45f, 206 * g * 0.45f);
    }
  }
  const float q = sinf(t * 0.8f) * 1.0f + sinf(t * 2.1f) * 0.35f;   // sa queue, posee sur le pilier, le bout qui bat
  const float queue[6][2] = {{54, 45}, {55, 45}, {56, 45}, {57, 44}, {57.6f + q * 0.4f, 43}, {57.8f + q, 42}};
  for (int i = 0; i < 6; i++) peindre((int)queue[i][1], (int)floorf(queue[i][0] + 0.5f), 10, 8, 14);
  static const float NOIR[1][3] = {{10, 8, 14}};              // le chat, sur le pilier, contre la lueur
  const IC_Bord bords[3] = {{0, -1, 236, 150, 96, 0.55f}, {1, 0, 210, 120, 80, 0.45f}, {-1, 0, 210, 120, 80, 0.45f}};
  const bool tourne = ic_mod(t + 14.0f, 23.0f) > 18.5f;
  ic_sprite(tourne ? IC_CHAT_TOURNE : IC_CHAT_DOS, 14, 44, 32, "k", NOIR, false, 1.0f, bords, 3);
}

// --- le carrefour sous la pluie (_scene_carrefour) ------------------------------------------------------------------
// humeurs : 0 = - (une seule ambiance)

const int IC_C_FX = 44, IC_C_FY = 11;     // le coin haut gauche de la tete du feu tricolore
const float IC_C_LX = 14.0f, IC_C_LY = 9.0f;   // la tete du lampadaire
static const float IC_C_COULEURS[3][3] = {{70, 255, 150}, {255, 170, 30}, {255, 50, 40}};   // vert, orange, rouge
static const char *const IC_VOITURE[6] = {   // de profil, vers la droite ; f phare, r feu arriere, w vitre, o roue
  ".....kkkkk......", "....kwwkwwk.....", "..kkkkkkkkkkkk..", ".kkkkkkkkkkkkkkf", "rkkkkkkkkkkkkkkk",
  "..ooo......ooo.."};
static const char *const IC_CHAT_MARCHE[4][5] = {   // quatre poses de marche, vers la droite
  {"k.....k.", ".k...kkk", "..kkkkk.", "..kkkk..", "..k..k.."}, {"k.....k.", ".k...kkk", "..kkkkk.", "..kkkk..", ".k....k."},
  {"k.....k.", ".k...kkk", "..kkkkk.", "..kkkk..", "...kk..."}, {"k.....k.", ".k...kkk", "..kkkkk.", "..kkkk..", ".k...k.."}};

struct E_carrefour {
  uint8_t fond[64][64][3], dessus[64][64][3], masque[64][64];
  uint8_t fy[4], fx[4];                 // quatre insomniaques, a 3 h du matin
  float gx[46], gy[46], gv[46];         // la pluie
  float ex[10], ey[10], ea[10];         // les eclaboussures
};

void ic_carrefour_decor(E_carrefour &e) {
  degrade2(10, 8, 18, 54, 34, 44, 0, 30);                    // un ciel bas, roussi par la ville
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      if (x >= 24 && x < 33 && y >= 6 + (x - 24) * 1.4f && y <= 41 - (x - 24) * 1.5f) peindre(y, x, 12, 11, 18);   // les
      if (x > 33 && x < 42 && y >= 4 + (42 - x) * 1.6f && y <= 41 - (42 - x) * 1.5f) peindre(y, x, 10, 10, 16);   // facades
      if (y > 28 && y <= 41 && fabsf(x - 33.0f) <= (y - 28) * 0.65f) peindre(y, x, 14, 14, 20);   // de la rue au loin
    }
  static const int IMM[2][4] = {{0, 24, 2, 9}, {42, 64, 1, 7}};   // x0, x1, toit, premier rang de fenetres
  static const float FACADE[2][3] = {{31, 29, 46}, {29, 29, 46}};
  static const int COLS[2][5] = {{2, 6, 10, 15, 19}, {44, 48, 52, 56, 60}};
  int fen[30][2], nf = 0;
  for (int i = 0; i < 2; i++) {
    const int x0 = IMM[i][0], x1 = IMM[i][1], toit = IMM[i][2];
    for (int y = toit; y < toit + 5; y++) for (int x = x0; x < x1; x++) peindre(y, x, 20, 20, 30);   // le toit de zinc
    for (int y = toit + 1; y < toit + 4; y++) {               // ses lucarnes
      for (int x = x0 + 4; x < x0 + 6; x++) peindre(y, x, 40, 38, 52);
      for (int x = x1 - 8; x < x1 - 6; x++) peindre(y, x, 40, 38, 52);
    }
    for (int x = x0; x < x1; x++) peindre(toit + 5, x, 52, 48, 62);   // la corniche
    for (int y = toit + 6; y < 41; y++) for (int x = x0; x < x1; x++) peindre(y, x, FACADE[i][0], FACADE[i][1], FACADE[i][2]);
    for (int k = 0; k < 3; k++) {                             // les fenetres, et leurs balcons
      const int ry = IMM[i][3] + 7 * k;
      for (int c = 0; c < 5; c++) {
        for (int y = ry; y < ry + 3; y++) for (int x = COLS[i][c]; x < COLS[i][c] + 2; x++) peindre(y, x, 8, 8, 13);
        fen[nf][0] = ry; fen[nf][1] = COLS[i][c]; nf++;
      }
      for (int x = x0 + 1; x < x1 - 1; x++) peindre(ry + 3, x, 14, 12, 18);
      for (int x = x0 + 1; x < x1 - 1; x += 2) peindre(ry + 2, x, 16, 14, 20);
    }
  }
  for (int y = 0; y < 2; y++) for (int x = 8; x < 10; x++) peindre(y, x, 24, 22, 30);   // des cheminees
  peindre(0, 57, 24, 22, 30); peindre(0, 58, 24, 22, 30);
  for (int k = 0; k < 4; k++) {                               // quatre insomniaques, a 3 h du matin
    int i;
    do { i = aleatoire() % nf; } while (fen[i][0] < 0);
    e.fy[k] = fen[i][0]; e.fx[k] = fen[i][1];
    for (int y = fen[i][0]; y < fen[i][0] + 3; y++) for (int x = fen[i][1]; x < fen[i][1] + 2; x++) peindre(y, x, 110, 76, 42);
    fen[i][0] = -1;
  }
  for (int x = 0; x < 64; x++) {
    peindre(40, x, 34, 32, 46); peindre(41, x, 34, 32, 46);   // le trottoir d'en face
    peindre(42, x, 60, 58, 70);                               // sa bordure
    for (int y = 43; y < 57; y++) peindre(y, x, 14, 15, 21);  // la chaussee mouillee
    peindre(57, x, 66, 64, 74);                               // notre bordure
    for (int y = 58; y < 64; y++) peindre(y, x, 34, 33, 46);  // notre trottoir
  }
  static const int BANDES[5][2] = {{44, 1}, {46, 1}, {48, 2}, {51, 2}, {54, 2}};   // le passage pieton
  for (int k = 0; k < 5; k++) {
    const float q = (BANDES[k][0] - 44) / 10.0f;
    for (int y = BANDES[k][0]; y < BANDES[k][0] + BANDES[k][1]; y++)
      for (int x = (int)(25 - q * 2); x < (int)(42 + q * 2); x++) peindre(y, x, 78, 78, 84);
  }
  for (int x = 0; x < 64; x++) if (x % 7 < 4 && (x < 22 || x > 45)) peindre(49, x, 70, 68, 60);   // la ligne au milieu
  for (int x = 36; x < 47; x++) { peindre(61, x, 20, 22, 30); peindre(62, x, 20, 22, 30); }   // une flaque
  for (int x = 38; x < 45; x++) peindre(60, x, 20, 22, 30);
  for (int y = 32; y < 40; y++)                               // le rideau de fer du cafe, son store replie
    for (int x = 2; x < 22; x++) peindre(y, x, y % 2 ? 40 : 32, y % 2 ? 40 : 32, y % 2 ? 48 : 40);
  for (int y = 30; y < 32; y++) for (int x = 1; x < 23; x++) peindre(y, x, 56, 24, 28);
  for (int y = 33; y < 40; y++) for (int x = 48; x < 61; x++) peindre(y, x, 70, 104, 112);   // une laverie de nuit
  for (int mx = 50; mx <= 58; mx += 4) {
    for (int y = 35; y < 38; y++) for (int x = mx; x < mx + 3; x++) peindre(y, x, 40, 56, 64);
    peindre(36, mx + 1, 120, 160, 170);
  }
  halo(54.5f, 36.5f, 5, 90, 150, 160, 0.35f, 1.2f);
  halo(54.5f, 41, 5, 90, 150, 160, 0.4f, 3);                  // sa lumiere sur le trottoir
  halo(IC_C_LX + 1, 41.5f, 8, 255, 170, 90, 0.55f, 3.0f);     // la flaque du lampadaire
  halo(IC_C_LX, IC_C_LY + 1, 2.2f, 255, 170, 90, 0.9f);       // sa lueur, sur la facade
  halo(IC_C_LX, IC_C_LY + 3, 4.5f, 255, 150, 80, 0.2f);
  halo(33, 30.5f, 1.0f, 255, 180, 100, 0.8f);                 // un reverbere tout au fond de la rue
  ic_garder(e.fond);
  uint8_t (*d)[64][3] = e.dessus;
  uint8_t (*m)[64] = e.masque;
  ic_rect(d, m, 12, 12, 10, 41, 12, 12, 18);                  // le lampadaire, sa crosse
  ic_rect(d, m, 11, 13, 39, 41, 12, 12, 18);
  ic_rect(d, m, 12, 15, 8, 8, 12, 12, 18);
  ic_rect(d, m, 12, 12, 9, 9, 12, 12, 18);
  ic_rect(d, m, 13, 13, 12, 38, 54, 40, 30);
  ic_rect(d, m, IC_C_FX + 2, IC_C_FX + 2, IC_C_FY + 13, 41, 12, 12, 18);   // le poteau du feu
  ic_rect(d, m, IC_C_FX, IC_C_FX + 4, IC_C_FY, IC_C_FY + 12, 20, 20, 24);   // sa tete
  for (int i = 0; i < 46; i++) { e.gx[i] = hasard(0, 64); e.gy[i] = hasard(0, 64); e.gv[i] = hasard(55, 80); }
  for (int i = 0; i < 10; i++) { e.ex[i] = hasard(0, 64); e.ey[i] = hasard(43, 64); e.ea[i] = hasard(0, 1); }
}

// un reflet etire sur l'asphalte mouille : une bande verticale qui ondule, ligne par ligne (lignes 43 a 63)
inline void ic_reflet(float sx, float larg, float r, float v, float b, float force, const float *ride, const float *profil,
                      float onde) {
  for (int y = 43; y < 64; y++) {
    const float c = sx + ride[y - 43] * onde, k = profil[y - 43] * force;
    const int x0 = max(0, (int)floorf(c - 3.2f * larg)), x1 = min(63, (int)ceilf(c + 3.2f * larg));
    for (int x = x0; x <= x1; x++) {
      const float u = (x - c) / larg;
      ajouter(y, x, expf(-u * u) * k, r, v, b);
    }
  }
}

void s_carrefour(int humeur, bool debut, float t, float ecoule, float dt) {
  E_carrefour &e = etat_ecran<E_carrefour>(debut);
  (void)humeur; (void)ecoule;
  if (debut) ic_carrefour_decor(e);
  ic_recopier(e.fond);
  const float Pl = ic_mod(t + 25.0f, 31.5f);                  // le feu : vert 14 s, orange 3.5 s, rouge 14 s
  const float poids[3] = {ic_lisse((14.0f - Pl) / 0.35f) * ic_lisse((Pl + 0.35f) / 0.35f) + ic_lisse((Pl - 31.15f) / 0.35f),
                          ic_lisse((Pl - 14.0f) / 0.35f) * ic_lisse((17.5f - Pl) / 0.35f),
                          ic_lisse((Pl - 17.5f) / 0.35f) * ic_lisse((31.5f - Pl) / 0.35f)};
  float coul[3] = {0, 0, 0};
  for (int k = 0; k < 3; k++) for (int c = 0; c < 3; c++) coul[c] += poids[k] * IC_C_COULEURS[k][c];
  const float fx = IC_C_FX, fy = IC_C_FY;
  const float lampes_y[3] = {fy + 9.5f, fy + 6, fy + 2.5f};   // vert en bas, orange, rouge en haut
  for (int k = 0; k < 3; k++)
    if (poids[k] > 0.01f) {
      ic_halo(fx + 2, lampes_y[k], 2.2f, IC_C_COULEURS[k][0], IC_C_COULEURS[k][1], IC_C_COULEURS[k][2], 0.75f * poids[k]);
      ic_halo(fx + 2, lampes_y[k], 4.5f, IC_C_COULEURS[k][0], IC_C_COULEURS[k][1], IC_C_COULEURS[k][2], 0.1f * poids[k]);
    }
  float ride[21], profil[21];                                 // les reflets etires sur l'asphalte mouille
  for (int i = 0; i < 21; i++) {
    const float y = 43 + i;
    ride[i] = sinf(y * 1.7f + t * 3.1f) * 0.7f + sinf(y * 0.6f - t * 1.3f) * 0.4f;
    profil[i] = expf(-((y - 55) / 6.0f) * ((y - 55) / 6.0f)) * 0.8f + 0.25f * expf(-(y - 43) / 3.0f);
  }
  ic_reflet(fx + 2, 1.1f, coul[0], coul[1], coul[2], 0.9f, ride, profil, 0.6f + 1.1f * 0.3f);
  ic_reflet(IC_C_LX + 1.5f, 1.6f, 255, 170, 90, 0.75f, ride, profil, 0.6f + 1.6f * 0.3f);
  ic_reflet(54.5f, 3.5f, 90, 150, 160, 0.35f, ride, profil, 0.6f + 3.5f * 0.3f);
  ic_reflet(33, 0.8f, 255, 180, 100, 0.4f, ride, profil, 0.6f + 0.8f * 0.3f);
  for (int x = 0; x < 64; x++)
    for (int c = 0; c < 3; c++) scene[57][x][c] = fmaxf(scene[57][x][c], e.fond[57][x][c]);
  const float Pc = ic_mod(t + 1.0f, 47.0f);                   // une voiture, de temps en temps
  const float vx = -26 + Pc * 15.0f;
  if (vx > -40 && vx < 90) {
    ic_halo(vx + 26, 53.5f, 6, 255, 236, 190, 0.75f, 2.6f);   // ses phares balaient la chaussee
    ic_halo(vx + 16, 54, 1.5f, 255, 240, 200, 0.6f);
    float pv[21], pr[21], zero[21];
    for (int i = 0; i < 21; i++) {
      const float y = 43 + i;
      pv[i] = expf(-(y - 58) * (y - 58) / 10.0f); pr[i] = expf(-(y - 57) * (y - 57) / 8.0f); zero[i] = 0;
    }
    ic_reflet(vx + 15.5f, 1.0f, 255, 236, 190, 0.5f, zero, pv, 0);
    ic_reflet(vx, 0.8f, 255, 40, 30, 0.4f, zero, pr, 0);
  }
  tramer(8);
  for (int k = 0; k < 4; k++) {                               // les fenetres allumees, nettes
    for (int y = e.fy[k]; y < e.fy[k] + 3; y++)
      for (int x = e.fx[k]; x < e.fx[k] + 2; x++) peindre(y, x, y == e.fy[k] ? 150 : 200, y == e.fy[k] ? 100 : 140,
                                                            y == e.fy[k] ? 56 : 70);   // le haut du rideau
  }
  ic_calque(e.dessus, e.masque);
  for (int x = 13; x < 16; x++) { peindre(9, x, 255, 200, 120); peindre(8, x, 30, 26, 26); }   // l'ampoule
  for (int k = 0; k < 3; k++) {                               // les trois feux : un allume, deux eteints
    const float q = 0.16f + 0.84f * poids[k];
    const int ly = (int)lampes_y[k];
    for (int y = ly - 1; y <= ly; y++)
      for (int x = IC_C_FX + 1; x < IC_C_FX + 4; x++) peindre(y, x, IC_C_COULEURS[k][0] * q, IC_C_COULEURS[k][1] * q, IC_C_COULEURS[k][2] * q);
  }
  const float Pk = ic_mod(t + 35.0f, 73.0f);
  if (Pk < 9) {                                               // un chat traverse sur le passage pieton
    const float u = Pk / 9, cx = 20 + 22 * u, cy = 52 - 13 * u;
    const char *const *pose = IC_CHAT_MARCHE[(int)(Pk * 6) % 4];
    const char *envers[5] = {pose[4], pose[3], pose[2], pose[1], pose[0]};
    static const float GRIS[1][3] = {{120, 116, 124}}, OMBRE[1][3] = {{40, 38, 46}};
    const IC_Bord bd = {0, -1, 190, 170, 150, 0.5f};
    ic_sprite(pose, 5, cx, cy, "k", GRIS, false, 1.0f, &bd, 1);
    ic_sprite(envers, 5, cx, cy + 5, "k", OMBRE, false, 0.5f);   // son reflet
  }
  if (vx > -20 && vx < 70) {                                  // la voiture
    static const float PAL[5][3] = {{76, 30, 36}, {96, 104, 124}, {255, 250, 220}, {255, 40, 30}, {10, 10, 12}};
    const IC_Bord bd = {0, -1, 200, 150, 110, 0.5f};
    ic_sprite(IC_VOITURE, 6, vx, 50, "kwfro", PAL, false, 1.0f, &bd, 1);
  }
  const float d = fminf(dt, 0.5f);                            // la pluie : de fins traits obliques
  for (int i = 0; i < 46; i++) {
    e.gy[i] = ic_mod(e.gy[i] + e.gv[i] * d, 66);
    e.gx[i] = ic_mod(e.gx[i] + e.gv[i] * 0.18f * d, 64);
    const float ax = e.gx[i] - IC_C_LX, ay = e.gy[i] - IC_C_LY - 6, bx = e.gx[i] - fx - 2, by = e.gy[i] - fy - 6;
    const float pres = expf(-sqrtf(ax * ax + ay * ay) / 9) + expf(-sqrtf(bx * bx + by * by) / 6);
    const float k = 0.35f + 0.65f * fminf(pres, 1.0f);
    for (int j = 0; j < 3; j++) {
      const float c = k * (1 - j * 0.28f);
      pointer(e.gy[i] - j, e.gx[i] - j * 0.18f, 120 * c, 130 * c, 160 * c);
    }
  }
  for (int i = 0; i < 10; i++) {                              // les eclaboussures, au sol
    e.ea[i] += d * 3.0f;
    if (e.ea[i] >= 1) { e.ea[i] -= 1; e.ex[i] = hasard(0, 64); e.ey[i] = hasard(43, 64); }
    if (e.ea[i] < 0.35f && fabsf(e.ey[i] - 57.5f) > 1) {
      const float c = (1 - e.ea[i] / 0.35f) * 0.6f;
      pointer(e.ey[i] - 1, e.ex[i], 150 * c, 160 * c, 190 * c);
      pointer(e.ey[i], e.ex[i] - 1, 150 * c * 0.6f, 160 * c * 0.6f, 190 * c * 0.6f);
      pointer(e.ey[i], e.ex[i] + 1, 150 * c * 0.6f, 160 * c * 0.6f, 190 * c * 0.6f);
    }
  }
}
