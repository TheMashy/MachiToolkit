// lot_instants_a.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
// « Les instants », lot A : la rue la nuit, en pixel art trame. Un arret de bus sous la neige, une superette sous
// la pluie, un distributeur de boissons au coin d'une rue, une cabine telephonique dans la neige. Comme en numpy :
// le decor fixe calcule au debut (garde en uint8 dans E_x), puis a chaque image : le decor + les lumieres qui
// bougent -> tramer(8) -> les figures nettes (sprites en chaines) et les flocons ou les gouttes par-dessus. Les
// cycles (le bus, le client, le passant, le chat, les gestes au telephone) se calent sur `t`, comme en numpy.
#pragma once

// ===========================================================================
// LES OUTILS DU LOT (prefixe ia_)

static const float IA_NIV[8] = {0.0f, 5.2f, 20.8f, 46.8f, 83.3f, 130.1f, 187.3f, 255.0f};   // les marches de tramer(8)
const float IA_PI = 3.14159265f;

struct IaC { float r, g, b; };

// _ia_niv : une teinte posee sur la marche i de la trame (fois k)
static IaC ia_niv(float r, float g, float b, int i, float k = 1.0f) {
  const float s = IA_NIV[i] / fmaxf(r, fmaxf(g, b)) * k;
  return {r * s, g * s, b * s};
}

// un rectangle [y0, y1) x [x0, x1) de la scene, borne au panneau
static void ia_rect(int y0, int y1, int x0, int x1, float r, float g, float b) {
  y0 = max(y0, 0); y1 = min(y1, 64); x0 = max(x0, 0); x1 = min(x1, 64);
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++) peindre(y, x, r, g, b);
}
static void ia_rect(int y0, int y1, int x0, int x1, IaC c) { ia_rect(y0, y1, x0, x1, c.r, c.g, c.b); }

// le decor fixe : la scene gardee en uint8 (arrondie), et reprise a chaque image
static void ia_garder(uint8_t (*f)[64][3]) {
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) f[y][x][c] = (uint8_t)(borne(scene[y][x][c], 0, 255) + 0.5f);
}
static void ia_reprendre(const uint8_t (*f)[64][3]) {
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      for (int c = 0; c < 3; c++) scene[y][x][c] = f[y][x][c];
}

// _halo, borne la ou il apporte encore quelque chose (moins d'un tiers de niveau au-dela)
static void ia_halo(float x, float y, float rayon, float r, float g, float b, float force = 1.0f, float aplati = 1.0f) {
  const float fort = fmaxf(r, fmaxf(g, b)) * force;
  if (fort <= 0.3f) return;
  const float dmax = rayon * logf(fort / 0.3f);
  const int e = (int)(rayon * 6) + 1;
  const int ex = min(e, (int)dmax + 1), ey = min(e, (int)(dmax / aplati) + 1);
  const int x0 = max(0, (int)x - ex), x1 = min(64, (int)x + ex + 1);
  const int y0 = max(0, (int)y - ey), y1 = min(64, (int)y + ey + 1);
  const float inv = 1.0f / fmaxf(rayon, 1e-3f), d2max = dmax * dmax;
  for (int yy = y0; yy < y1; yy++) {
    const float dy = (yy - y) * aplati;
    for (int xx = x0; xx < x1; xx++) {
      const float dx = xx - x, d2 = dx * dx + dy * dy;
      if (d2 < d2max) ajouter(yy, xx, expf(-sqrtf(d2) * inv) * force, r, g, b);
    }
  }
}

// --- les sprites en chaines de caracteres ('.' transparent) ---
struct IaSprite { const char *const *l; int h; };
struct IaTeinte { char c; float r, g, b, a; };

// _ia_peindre : coin haut-gauche en (x, y) (arrondi), une palette {lettre: couleur (, alpha)} ; une lettre absente
// n'est pas peinte ; la boite [bx0, bx1) x [by0, by1) borne le dessin ; `renverse` : les lignes de bas en haut
// (le reflet), `hmax` lignes au plus
static void ia_peindre(const IaSprite &s, const IaTeinte *pal, int np, float x, float y, bool miroir = false,
                       int bx0 = 0, int bx1 = 64, int by0 = 0, int by1 = 64, bool renverse = false, int hmax = 99) {
  const int h = min(s.h, hmax);
  int larg = 0;
  for (int r = 0; r < h; r++) larg = max(larg, (int)strlen(s.l[renverse ? s.h - 1 - r : r]));
  const int x0 = (int)floorf(x + 0.5f), y0 = (int)floorf(y + 0.5f);
  bx0 = max(bx0, 0); bx1 = min(bx1, 64); by0 = max(by0, 0); by1 = min(by1, 64);
  for (int r = 0; r < h; r++) {
    const int yy = y0 + r;
    if (yy < by0 || yy >= by1) continue;
    const char *ligne = s.l[renverse ? s.h - 1 - r : r];
    for (int c = 0; ligne[c]; c++) {
      if (ligne[c] == '.') continue;
      const int xx = x0 + (miroir ? larg - 1 - c : c);
      if (xx < bx0 || xx >= bx1) continue;
      for (int k = 0; k < np; k++)
        if (pal[k].c == ligne[c]) {
          const float a = pal[k].a;
          if (a > 0) {
            float *p = scene[yy][xx];
            p[0] += (pal[k].r - p[0]) * a;
            p[1] += (pal[k].g - p[1]) * a;
            p[2] += (pal[k].b - p[2]) * a;
          }
          break;
        }
    }
  }
}

// --- la neige : des flocons de 1 px qui tombent jusqu'a leur sol (leur profondeur) ; dans la lumiere (`lumi`,
// 0-255 par pixel) ils prennent la teinte de la lampe, et les plus proches y font une petite croix ---
struct IaFlocons { float x[50], y[50], z[50], p[50], sol[50]; };
static void ia_semer_flocons(IaFlocons &f, int n, float sol0, float sol1) {
  for (int i = 0; i < n; i++) {
    f.z[i] = hasard(0, 1);
    f.x[i] = hasard(0, 64);
    f.y[i] = hasard(-4, 64);
    f.p[i] = hasard(0, 6.3f);
    f.sol[i] = sol0 + (sol1 - sol0) * borne(f.z[i] + hasard(-0.15f, 0.15f), 0, 1);
  }
}
static void ia_flocons(IaFlocons &f, int n, float t, float dt, const uint8_t (*lumi)[64], IaC teinte, IaC froid) {
  const float pas = fminf(dt, 0.5f);
  for (int i = 0; i < n; i++) {
    f.y[i] += (2.5f + f.z[i] * 4.5f) * pas;                        // les proches tombent plus vite
    f.x[i] += (sinf(t * 0.9f + f.p[i]) * 0.6f + 0.25f) * (0.5f + f.z[i]) * pas * 2;
    if (f.y[i] > f.sol[i]) {
      f.y[i] = hasard(-6, -1);
      f.x[i] = hasard(-4, 64);
    }
    f.x[i] = fmodf(fmodf(f.x[i], 64) + 64, 64);
    const int yi = (int)floorf(f.y[i]), xi = (int)floorf(f.x[i]) & 63;
    if (yi < 0 || yi >= 64) continue;
    const float lu = lumi[yi][xi] * (1.0f / 255), k = (0.45f + 0.55f * f.z[i]) * (1 - lu);
    const float r = froid.r * k + teinte.r * lu, g = froid.g * k + teinte.g * lu, b = froid.b * k + teinte.b * lu;
    pointer(yi, xi, r, g, b);
    if (lu > 0.45f && f.z[i] > 0.5f) {
      pointer(yi - 1, xi, r * 0.5f, g * 0.5f, b * 0.5f);
      pointer(yi + 1, xi, r * 0.5f, g * 0.5f, b * 0.5f);
      pointer(yi, xi - 1, r * 0.5f, g * 0.5f, b * 0.5f);
      pointer(yi, xi + 1, r * 0.5f, g * 0.5f, b * 0.5f);
    }
  }
}

// --- les gens ---
static const char *const IA_FACE[] = {   // de face, qui attend (h = bonnet, f = visage, s = echarpe, c = manteau)
  "..HHH..", ".hhhhh.", ".hfffh.", "..fff..", ".sssss.", "CCCsCCC", "dccsccd",
  "dcccccd", "dcccccd", "dcccccd", ".ccccc.", "..p.p..", "..p.p..", ".bb.bb."};
static const char *const IA_FACE2[] = {  // le poids sur l'autre pied
  "...HHH.", "..hhhhh", "..hfffh", "...fff.", "..sssss", ".CCCsCC", ".dccscd",
  ".dccccd", ".dccccd", ".dccccd", "..cccc.", "..p..p.", "..p..p.", ".bb..bb"};
static const char *const IA_DOS0[] = {   // de dos (deux pas)
  "..HHH..", ".hhhhh.", ".hhhhh.", "..hhh..", ".sssss.", "CCCCCCC", "dcccccd",
  "dcccccd", "dcccccd", "dcccccd", ".ccccc.", "..p.p..", "..p.p..", ".bb.bb."};
static const char *const IA_DOS1[] = {
  "..HHH..", ".hhhhh.", ".hhhhh.", "..hhh..", ".sssss.", "CCCCCCC", "dcccccd",
  "dcccccd", "dcccccd", "dcccccd", ".ccccc.", "..p.p..", "..p.b..", ".bb...."};
static const char *const IA_MARCHE0[] = {   // de profil vers la droite : quatre poses de marche
  "..HHH..", ".hhhhh.", ".hhhff.", "..hff..", "..sss..", ".CCCCC.", ".ccdcc.",
  ".ccdcc.", ".ccdcc.", ".ccdcc.", ".ccccc.", "...pp..", "...pp..", "...bbb."};
static const char *const IA_MARCHE1[] = {
  "..HHH..", ".hhhhh.", ".hhhff.", "..hff..", "..sss..", ".CCCCC.", ".cccdc.",
  ".ccccd.", ".ccccd.", ".ccccc.", ".ccccc.", "..p.p..", ".p...p.", "bb...bb"};
static const char *const IA_MARCHE2[] = {
  "..HHH..", ".hhhhh.", ".hhhff.", "..hff..", "..sss..", ".CCCCC.", ".ccdcc.",
  ".ccdcc.", ".ccdcc.", ".ccdcc.", ".ccccc.", "...pp..", "...pp..", "..bbb.."};
static const char *const IA_MARCHE3[] = {
  "..HHH..", ".hhhhh.", ".hhhff.", "..hff..", "..sss..", ".CCCCC.", ".cdccc.",
  ".dcccc.", ".dcccc.", ".ccccc.", ".ccccc.", "..p.p..", ".p...p.", "bb...bb"};
static const char *const IA_PLUIE[] = {   // de face, sans bonnet, qui tient son parapluie
  "..hhh..", ".hhhhh.", ".hfffh.", "..fff..", ".CCCCC.", "CCcccCC", "dcccccd",
  "dcccccd", "dcccccd", "dcccccd", ".ccccc.", "..p.p..", "..p.p..", ".bb.bb."};
static const char *const IA_ACHAT0[] = {  // de dos devant la machine : il appuie...
  "..hhh..", ".hhhhh.", ".hhhhh.", "..hhh..", ".CCCCCm", "CccccdC", "dcccccd",
  "dcccccd", "dcccccd", "dcccccd", ".ccccc.", "..p.p..", "..p.p..", ".bb.bb."};
static const char *const IA_ACHAT1[] = {  // ...puis se penche pour ramasser
  ".......", ".......", ".......", ".......", "..hhh..", ".hhhhh.", ".CCCCC.",
  "CcccccC", "dcccccd", "dccccmd", ".ccccc.", ".ppppp.", ".p...p.", "bb...bb"};
static const char *const IA_PARA[] = {"...LLL...", ".uuuuuuu.", "uuuuuuuuu", "U.U.U.U.U", "....i....", "....i...."};
static const char *const IA_PARA_MI[] = {"...u...", "..uuu..", ".uuuuu.", ".U.U.U.", "...i...", "...i..."};
static const char *const IA_VENDEUR0[] = {"..hhh..", ".hhhhh.", ".hfffh.", "..fff..", ".vwwwv.", "vvvwvvv", "vvvvvvv"};
static const char *const IA_VENDEUR1[] = {".......", "..hhh..", ".hhhhh.", ".hhffh.", ".vwffv.", "vvvwvvv", "vvvvvvv"};
static const char *const IA_CHAT_ASSIS[] = {".k.k..", ".kkk..", ".yky..", "..kk..", "..kkk.", ".lkkk.", ".lkkkk"};
static const char *const IA_CHAT_LECHE[] = {"......", ".k.k..", ".kkk..", ".lkkk.", "..kkk.", ".lkkk.", ".lkkkk"};
static const char *const IA_CHAT_LECHE2[] = {"......", ".k.k..", ".kkk..", "lkkkk.", ".lkkk.", ".lkkk.", ".lkkkk"};
static const char *const IA_CHAT_MARCHE1[] = {"........", "......k.k", "kk....kkk", "..kkkkkky", "..lkkkkk.", "..k.k.k.k",
                                              "..k...k.."};
static const char *const IA_CHAT_MARCHE2[] = {"........", "......k.k", ".k....kkk", "k.kkkkkky", "..lkkkkk.", "...kk..kk",
                                              "...k...k."};
static const char *const IA_QUEUE0[] = {"...", "...", "...", "...", "kkk"};   // la queue : couchee, qui se releve...
static const char *const IA_QUEUE1[] = {"...", "...", "..k", "..k", "kk."};
static const char *const IA_QUEUE2[] = {"...", ".k.", "..k", ".k.", "k.."};
static const char *const IA_QUEUE3[] = {"...", "..k", ".k.", ".k.", "k.."};
static const char *const IA_TEL_P0[] = {   // de profil vers le fond de la cabine, le combine a l'oreille
  "...hhh.", "..hhhhh", "..hhhff", ".mrhhff", ".a.hff.", ".aCCCC.", "..ccccc", "..cccc.", "..cccc.", "..cccc.",
  "..cccc.", "..cccc."};
static const char *const IA_TEL_P1[] = {   // il baisse la tete
  ".......", "...hhh.", "..hhhhh", ".mrhhff", ".a.hhff", ".aCCCC.", "..ccccc", "..cccc.", "..cccc.", "..cccc.",
  "..cccc.", "..cccc."};
static const char *const IA_TEL_F0[] = {   // tourne vers la vitre, le combine a l'oreille
  "..hhh..", ".hhhhh.", ".hfffhr", "..fffrm", ".CCCCCa", "CcccccC", "dcccccd", "dcccccd", "dcccccd", "dcccccd",
  ".ccccc.", ".ccccc."};

#define IA_SP(tab) IaSprite{tab, (int)(sizeof(tab) / sizeof(tab[0]))}
static const IaSprite IA_S_FACE = IA_SP(IA_FACE), IA_S_FACE2 = IA_SP(IA_FACE2);
static const IaSprite IA_S_DOS[2] = {IA_SP(IA_DOS0), IA_SP(IA_DOS1)};
static const IaSprite IA_S_MARCHE[4] = {IA_SP(IA_MARCHE0), IA_SP(IA_MARCHE1), IA_SP(IA_MARCHE2), IA_SP(IA_MARCHE3)};
static const IaSprite IA_S_PLUIE = IA_SP(IA_PLUIE), IA_S_PARA = IA_SP(IA_PARA), IA_S_PARA_MI = IA_SP(IA_PARA_MI);
static const IaSprite IA_S_ACHAT[2] = {IA_SP(IA_ACHAT0), IA_SP(IA_ACHAT1)};
static const IaSprite IA_S_VENDEUR[2] = {IA_SP(IA_VENDEUR0), IA_SP(IA_VENDEUR1)};
static const IaSprite IA_S_CHAT_ASSIS = IA_SP(IA_CHAT_ASSIS), IA_S_CHAT_LECHE = IA_SP(IA_CHAT_LECHE),
                      IA_S_CHAT_LECHE2 = IA_SP(IA_CHAT_LECHE2), IA_S_CHAT_MARCHE1 = IA_SP(IA_CHAT_MARCHE1),
                      IA_S_CHAT_MARCHE2 = IA_SP(IA_CHAT_MARCHE2);
static const IaSprite IA_S_QUEUE[4] = {IA_SP(IA_QUEUE0), IA_SP(IA_QUEUE1), IA_SP(IA_QUEUE2), IA_SP(IA_QUEUE3)};
static const IaSprite IA_S_TEL_P[2] = {IA_SP(IA_TEL_P0), IA_SP(IA_TEL_P1)};
static const IaSprite IA_S_TEL_F = IA_SP(IA_TEL_F0);
#undef IA_SP

// ===========================================================================
// 1. L'ARRET DE BUS SOUS LA NEIGE (_scene_arret_bus). De profil : la rue en travers, le lampadaire au sodium et sa
// flaque creme, quelqu'un qui attend dedans, l'abri a droite. Chaque minute un bus glisse depuis la gauche,
// s'arrete porte devant la personne, elle monte, il repart ; puis quelqu'un d'autre arrive a pied par la droite.

const float IA_BUS_P = 60.0f;   // un bus par minute
const int IA_BUS_L = 44, IA_BUS_HT = 21, IA_BUS_Y = 22, IA_BUS_ARRET = 41, IA_BUS_X = 30, IA_BUS_PIEDS = 52;
const float IA_LX = 33.5f, IA_LY = 10.5f;   // la vitre du lampadaire
static const float IA_HABITS[5][3][3] = {   // (manteau, bonnet, echarpe) d'un voyageur a l'autre
  {{96, 40, 38}, {64, 70, 104}, {196, 164, 92}},
  {{40, 64, 72}, {150, 52, 46}, {180, 74, 60}},
  {{92, 74, 44}, {44, 52, 80}, {200, 196, 184}},
  {{58, 52, 80}, {186, 146, 64}, {150, 56, 56}},
  {{34, 52, 42}, {196, 186, 166}, {96, 124, 156}}};

struct E_arret_bus {
  uint8_t fond[64][64][3];               // le decor et la lumiere de la lampe, avant la trame
  uint8_t lumi[64][64];                  // la lumiere de la lampe (0-255) : pour les flocons
  uint8_t bus[21][44][3], bus_m[21][44]; // le bus, et ou il est
  IaFlocons neige;
};

// _ia_gens_palette : le voyageur k, eclaire d'en haut par la lampe (lumiere 0-1)
static int ia_pal_gens(IaTeinte *p, int k, float lumiere) {
  const float *ma = IA_HABITS[k % 5][0], *bo = IA_HABITS[k % 5][1], *ec = IA_HABITS[k % 5][2];
  const float q = 0.5f + 0.5f * lumiere, cr = 255, cg = 196, cb = 120;
  p[0] = {'H', bo[0] * 0.55f + cr * 0.42f * lumiere, bo[1] * 0.55f + cg * 0.42f * lumiere, bo[2] * 0.55f + cb * 0.42f * lumiere, 1};
  p[1] = {'h', bo[0] * q * 0.8f, bo[1] * q * 0.8f, bo[2] * q * 0.8f, 1};
  p[2] = {'f', 200 * q, 150 * q, 116 * q, 1};
  p[3] = {'s', ec[0] * q * 0.9f, ec[1] * q * 0.9f, ec[2] * q * 0.9f, 1};
  p[4] = {'C', ma[0] * 0.75f + cr * 0.38f * lumiere, ma[1] * 0.75f + cg * 0.38f * lumiere, ma[2] * 0.75f + cb * 0.38f * lumiere, 1};
  p[5] = {'c', ma[0] * q, ma[1] * q, ma[2] * q, 1};
  p[6] = {'d', ma[0] * q * 0.6f, ma[1] * q * 0.6f, ma[2] * q * 0.6f, 1};
  p[7] = {'p', 30 * q, 30 * q, 42 * q, 1};
  p[8] = {'b', 16 + 10 * q, 14 + 10 * q, 20 + 10 * q, 1};
  return 9;
}

// _ia_bus_sprite : le bus vu du cote des portes, l'avant a droite
static void ia_bus_sprite(E_arret_bus &e) {
  auto pose = [&](int y0, int y1, int x0, int x1, int r, int g, int b, bool m) {
    for (int y = y0; y < y1; y++)
      for (int x = x0; x < x1; x++) {
        e.bus[y][x][0] = (uint8_t)r; e.bus[y][x][1] = (uint8_t)g; e.bus[y][x][2] = (uint8_t)b;
        if (m) e.bus_m[y][x] = 1;
      }
  };
  const int L = IA_BUS_L;
  pose(2, 17, 0, L, 40, 62, 80, true);                                 // la caisse
  pose(2, 3, 1, L - 1, 88, 104, 118, false);                           // l'arete du toit
  pose(2, 3, 0, 1, 0, 0, 0, false); e.bus_m[2][0] = 0;
  pose(2, 3, L - 1, L, 0, 0, 0, false); e.bus_m[2][L - 1] = 0;
  pose(0, 1, 3, L - 4, 196, 200, 220, true);                           // la neige sur le toit
  pose(1, 2, 1, L - 2, 150, 158, 184, true);
  pose(3, 4, 9, 27, 26, 22, 22, false);                                // la girouette de cote
  for (int x = 10; x < 26; x += 2) pose(3, 4, x, x + 1, 255, 160, 56, false);
  pose(13, 17, 0, L, 24, 34, 46, false);                               // la jupe
  pose(12, 13, 0, L, 140, 58, 44, false);                              // le lisere
  for (int i = 0; i < 6; i++) {                                        // les fenetres allumees
    const int a = 1 + i * 5;
    pose(4, 11, a, a + 4, 232, 196, 128, false);
    pose(4, 5, a, a + 4, 255, 230, 170, false);
    pose(10, 11, a, a + 4, 150, 112, 70, false);
  }
  pose(3, 17, 31, 38, 22, 28, 38, false);                              // la porte
  pose(4, 16, 32, 37, 196, 160, 104, false);
  pose(4, 16, 34, 35, 120, 96, 66, false);
  pose(3, 11, 38, 43, 120, 118, 98, false);                            // le pare-brise
  pose(4, 10, 39, 42, 170, 156, 118, false);
  pose(3, 4, 39, 43, 255, 170, 60, false);
  pose(3, 13, 43, 44, 28, 40, 52, false);
  pose(3, 4, 43, 44, 0, 0, 0, false); e.bus_m[3][43] = 0;
  pose(14, 15, 42, 44, 255, 246, 220, false);                          // le phare
  pose(13, 15, 0, 1, 210, 34, 30, false);                              // le feu arriere
  for (int k = 0; k < 2; k++) {                                        // les roues dans leurs passages
    const float cx = k ? 27.5f : 8.5f;
    for (int y = 0; y < IA_BUS_HT; y++)
      for (int x = 0; x < L; x++) {
        const float d = hypotf(x - cx, y - 17.0f);
        if (d < 3.8f && y >= 13) pose(y, y + 1, x, x + 1, 10, 12, 16, true);
        if (d < 2.9f) pose(y, y + 1, x, x + 1, 24, 24, 30, true);
        if (d < 1.2f) pose(y, y + 1, x, x + 1, 96, 98, 110, false);
      }
  }
}

// _ia_arret_fond : le decor fixe (dans la scene, puis garde) et la carte de la lumiere de la lampe
static void ia_arret_fond(E_arret_bus &e) {
  const IaC nuit = ia_niv(60, 80, 160, 2);
  for (int y = 0; y < 64; y++) {
    const float k = borne(0.45f + y / 20.0f, 0, 1);                    // le ciel, plus noir tout en haut
    for (int x = 0; x < 64; x++) peindre(y, x, nuit.r * k, nuit.g * k, nuit.b * k);
  }
  halo(14, 33, 12, 44, 30, 40, 0.55f, 2.6f);                           // la lueur de la ville
  const IaC murs = ia_niv(60, 64, 96, 2), neige = ia_niv(150, 160, 196, 3), faite4 = ia_niv(150, 160, 196, 4);
  static const int MAISONS[3][4] = {{-3, 11, 27, 21}, {22, 34, 28, 23}, {50, 66, 26, 20}};
  for (int i = 0; i < 3; i++) {                                        // des maisons basses sous la neige
    const int x0 = MAISONS[i][0], x1 = MAISONS[i][1], bas = MAISONS[i][2], faite = MAISONS[i][3];
    const float cx = (x0 + x1) / 2.0f;
    ia_rect(bas, 34, x0, x1, murs);
    for (int y = faite; y < bas; y++)
      for (int x = 0; x < 64; x++)
        if (fabsf(x - cx) <= (y - faite) * 1.25f + 1.5f) {
          const IaC c = y == faite ? faite4 : neige;
          peindre(y, x, c.r, c.g, c.b);
        }
  }
  static const int FEN[4][2] = {{3, 29}, {7, 29}, {27, 30}, {56, 28}};
  const IaC chaud = ia_niv(255, 170, 80, 6);
  for (int i = 0; i < 4; i++) {
    ia_rect(FEN[i][1], FEN[i][1] + 2, FEN[i][0], FEN[i][0] + 2, chaud);
    halo(FEN[i][0] + 1, FEN[i][1] + 1, 1.5f, 160, 100, 40, 0.4f);
  }
  static const float SAPINS[3][2] = {{13.5f, 13}, {39, 15}, {43, 11}};
  const IaC sapin = ia_niv(20, 44, 48, 2);
  for (int i = 0; i < 3; i++) {                                        // des sapins sombres, un peu de neige
    const float sx = SAPINS[i][0];
    const int sh = (int)SAPINS[i][1];
    for (int y = 34 - sh; y < 34; y++)
      for (int x = 0; x < 64; x++)
        if (fabsf(x - sx) <= (y - (34 - sh)) * 0.38f + 0.5f) {
          if ((y - (34 - sh)) % 3 == 2 && x < sx) peindre(y, x, neige.r * 0.8f, neige.g * 0.8f, neige.b * 0.8f);
          else peindre(y, x, sapin.r, sapin.g, sapin.b);
        }
  }
  ia_rect(33, 36, 0, 64, neige);                                       // le trottoir d'en face
  ia_rect(23, 34, 18, 19, ia_niv(60, 56, 60, 2));                      // un lampadaire, la-bas
  ia_rect(22, 23, 17, 19, ia_niv(255, 190, 110, 6));
  halo(17.5f, 22.5f, 1.6f, 200, 130, 60, 0.5f);
  halo(17.5f, 34.5f, 3.2f, 200, 140, 70, 0.5f, 2.5f);
  ia_rect(36, 43, 0, 64, ia_niv(52, 56, 76, 2, 1.35f));                // la rue, deux ornieres
  ia_rect(37, 39, 0, 64, ia_niv(52, 56, 76, 2));
  ia_rect(40, 42, 0, 64, ia_niv(52, 56, 76, 2));
  ia_rect(43, 44, 0, 64, ia_niv(150, 158, 190, 3, 1.4f));              // la bordure
  ia_rect(44, 64, 0, 64, neige);                                       // le trottoir enneige
  ia_rect(44, 47, 0, 64, ia_niv(150, 160, 196, 3, 0.8f));
  ia_rect(45, 51, 47, 64, ia_niv(60, 64, 90, 2, 1.3f));                // sous l'abri
  for (int y = 0; y < 64; y++)                                         // la lampe : lueur, cone, flaque creme
    for (int x = 0; x < 64; x++) {
      const float dx = x - IA_LX, dy = y - IA_LY;
      float l = expf(-sqrtf(dx * dx + dy * dy) / 3.6f) * 0.95f;
      if (y > IA_LY && y < 50) {
        const float cone = borne(1 - fabsf(dx) / (1.5f + dy * 0.40f), 0, 1);
        l += cone * 0.16f * borne(dy / 8, 0, 1);
      }
      if (y >= 44) l += expf(-powf(hypotf(dx / 11.5f, (y - 51.5f) / 5.0f), 1.7f)) * 1.1f;
      if (y >= 36 && y < 44) {
        const float a = dx / 14.0f, b = (y - 41) / 4.0f;
        l += expf(-(a * a + b * b)) * 0.3f;
      }
      ajouter(y, x, l, 205, 150, 88);
      e.lumi[y][x] = (uint8_t)(borne(l, 0, 1) * 255 + 0.5f);
    }
  halo(IA_LX, IA_LY, 11, 40, 26, 14, 0.8f);
  halo(55.5f, 47.5f, 3.0f, 40, 60, 80, 0.7f, 2.4f);                    // l'affiche de l'abri, sur la neige
  ia_garder(e.fond);
  ia_bus_sprite(e);
}

// _ia_arret_avant : l'abri (vitre, affiche, banc, toit enneige) et le lampadaire, devant le bus
static void ia_arret_avant() {
  for (int y = 30; y < 47; y++)                                        // la vitre du fond de l'abri
    for (int x = 48; x < 64; x++) {
      float *p = scene[y][x];
      p[0] = p[0] * 0.7f + 14; p[1] = p[1] * 0.7f + 20; p[2] = p[2] * 0.7f + 30;
    }
  for (int y = 31; y < 46; y++) ajouter(y, 50, 1, 16, 18, 22);
  ia_rect(33, 43, 53, 58, 118, 136, 150);                              // l'affiche allumee
  ia_rect(34, 40, 54, 57, 54, 80, 108);
  ia_rect(35, 37, 55, 56, 190, 118, 72);
  ia_rect(41, 42, 54, 57, 96, 106, 120);
  ia_rect(42, 43, 59, 64, 64, 48, 40);                                 // le banc
  ia_rect(43, 47, 61, 62, 26, 24, 28);
  ia_rect(26, 30, 45, 64, 34, 40, 54);                                 // le toit
  ia_rect(24, 26, 45, 64, 170, 178, 204);
  ia_rect(24, 26, 45, 49, 214, 196, 170);
  peindre(24, 45, 150, 132, 116);
  ia_rect(30, 31, 45, 64, 20, 22, 32);
  ia_rect(30, 50, 47, 48, 22, 26, 36);                                 // le poteau
  ia_rect(30, 50, 46, 47, 52, 50, 56);
  ia_rect(49, 51, 45, 49, 140, 146, 176);
  ia_rect(12, 48, 44, 45, 26, 26, 32);                                 // le mat du lampadaire
  ia_rect(12, 46, 43, 44, 92, 72, 54);
  ia_rect(46, 48, 42, 46, 34, 32, 38);
  ia_rect(45, 46, 42, 46, 150, 144, 140);
  ia_rect(10, 11, 38, 44, 36, 34, 40);                                 // la crosse
  ia_rect(11, 12, 43, 45, 36, 34, 40);
  ia_rect(8, 10, 30, 38, 40, 36, 40);                                  // la tete
  ia_rect(7, 8, 31, 37, 196, 194, 212);
  ia_rect(10, 11, 31, 37, 255, 236, 186);                              // la vitre
  ia_rect(11, 12, 32, 36, 255, 206, 136);
}

// _ia_bus_poser : le bus (son avant en xf), ses voyageurs (selon le passage k), sa porte ouverte de `porte`
static void ia_bus_poser(const E_arret_bus &e, float xf, float porte, int k, bool monte) {
  const int x0 = (int)floorf(xf + 0.5f) - IA_BUS_L + 1;
  if (x0 + IA_BUS_L <= 0 || x0 >= 64) return;
  for (int y = 0; y < IA_BUS_HT; y++)
    for (int c = 0; c < IA_BUS_L; c++) {
      const int x = x0 + c;
      if (x < 0 || x >= 64 || !e.bus_m[y][c]) continue;
      float r = e.bus[y][c][0], g = e.bus[y][c][1], b = e.bus[y][c][2];
      if (y < 3) {                                                     // la neige du toit prend la creme de la lampe
        const float w = expf(-fabsf(x - IA_LX) / 7.0f) * 0.75f, mx = fmaxf(r, fmaxf(g, b)) / 220;
        r = r * (1 - w) + 255 * w * mx; g = g * (1 - w) + 222 * w * mx; b = b * (1 - w) + 168 * w * mx;
      }
      peindre(IA_BUS_Y + y, x, r, g, b);
    }
  auto px = [&](int y0, int y1, int c0, int c1, float r, float g, float b) {   // une retouche, en coordonnees du bus
    for (int y = y0; y < y1; y++)
      for (int c = c0; c < c1; c++) {
        const int x = x0 + c;
        if (x >= 0 && x < 64) peindre(IA_BUS_Y + y, x, r, g, b);
      }
  };
  const uint32_t h = (uint32_t)k * 2654435761u + 12345u;
  for (int i = 0; i < 6; i++) {                                        // les voyageurs assis : des silhouettes
    if ((h >> (i * 3)) % 3 == 0) continue;
    const int a = 1 + i * 5, dx = a + (int)((h >> (i * 2 + 7)) % 2);
    const bool brun = (h >> (i + 11)) % 2;
    const float r = brun ? 78 : 56, g = brun ? 56 : 50, b = brun ? 50 : 64;
    px(6, 8, dx, dx + 2, r, g, b);
    px(8, 10, max(a, dx - 1), dx + 3, r * 0.85f, g * 0.85f, b * 0.85f);
  }
  if (monte) {                                                         // celui qui vient de monter, debout
    px(5, 7, 28, 30, 70, 50, 46);
    px(7, 11, 27, 30, 60, 44, 42);
  }
  if (porte > 0) {                                                     // la porte : les deux vantaux s'ecartent
    px(4, 16, 32, 37, 255, 234, 180);
    px(15, 16, 32, 37, 130, 104, 70);
    if ((int)roundf(porte * 2) < 2) {
      px(4, 16, 32, 33, 196, 160, 104);
      px(4, 16, 36, 37, 196, 160, 104);
    }
  }
}

// _ia_traces : les pas dans la neige, que la neige recouvre ; tout se deduit de l'heure
static void ia_trace(float x, float y, float n, float s) {
  const float age = fmodf(fmodf(s - n, IA_BUS_P) + IA_BUS_P, IA_BUS_P), a = 1 - age / 36.0f;
  if (a <= 0) return;
  const int yi = (int)y, xi = (int)x;
  for (int xx = xi; xx < xi + 2 && xx < 64; xx++)
    for (int c = 0; c < 3; c++) scene[yi][xx][c] *= 1 - 0.4f * a;
}
static void ia_traces(float s) {
  for (int j = 0; IA_BUS_X + 3.0f + j * 2.5f < 66.0f; j++) {          // en venant : un pas tous les 2,5 px
    const float x = IA_BUS_X + 3.0f + j * 2.5f;
    ia_trace(x, IA_BUS_PIEDS + (j % 2), 49 + (66 - x) / (66 - IA_BUS_X) * 11, s);
  }
  ia_trace(IA_BUS_X + 1.5f, IA_BUS_PIEDS + 1, 34, s);                 // l'attente
  ia_trace(IA_BUS_X + 4.5f, IA_BUS_PIEDS, 34, s);
  for (int j = 0; j < 4; j++) ia_trace(IA_BUS_X + 2 + (j % 2) * 2, IA_BUS_PIEDS - 2 - j * 2, 29.6f + j * 0.6f, s);
}

void s_arret_bus(int humeur, bool debut, float t, float ecoule, float dt) {
  E_arret_bus &e = etat_ecran<E_arret_bus>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    ia_arret_fond(e);
    ia_semer_flocons(e.neige, 46, 34, 64);
  }
  ia_reprendre(e.fond);
  const float u = t / IA_BUS_P;
  const int k = (int)floorf(u);
  const float s = (u - k) * IA_BUS_P;                                  // ou en est la minute
  // le bus : il arrive en freinant (18-28 s), attend porte ouverte, repart en accelerant (36-47 s)
  bool bus = true;
  float xf = 0;
  if (s >= 18 && s < 28) { const float a = (s - 18) / 10; xf = -3 + (IA_BUS_ARRET + 3) * (1 - (1 - a) * (1 - a)); }
  else if (s >= 28 && s < 36) xf = IA_BUS_ARRET;
  else if (s >= 36 && s < 47) { const float a = (s - 36) / 11; xf = IA_BUS_ARRET + 72 * a * a; }
  else bus = false;
  const float porte = borne((s - 28.6f) / 0.8f, 0, 1) * borne((34.4f - s) / 0.8f, 0, 1);
  if (bus) {                                                           // ses lumieres sur la rue et sur la neige
    const float x0 = xf - IA_BUS_L + 1;
    ia_halo(xf + 7, 41.5f, 5.0f, 255, 226, 160, 0.85f, 1.6f);
    ia_halo(xf + 1, 36.5f, 1.6f, 255, 240, 200, 0.9f);
    ia_halo(x0, 35.5f, 1.6f, 220, 30, 20, 0.7f);
    for (int i = 0; i < 6; i++) ia_halo(x0 + 3 + i * 5, 45.5f, 2.0f, 150, 116, 66, 0.6f, 2.6f);
    if (porte > 0) ia_halo(x0 + 34, 46, 2.4f, 255, 220, 150, 0.9f * porte, 1.6f);
  }
  tramer(8);
  ia_traces(s);
  if (bus) ia_bus_poser(e, xf, porte, k, s >= 34.4f);
  ia_arret_avant();
  // la personne : elle attend (0-29.2 s), monte (29.2-33.2 s) ; une autre arrive par la droite (49-60 s)
  IaTeinte pal[9];
  const float y0 = IA_BUS_PIEDS - 13;
  if (s < 29.2f) {
    ia_pal_gens(pal, k, 1.0f);
    ia_peindre(fmodf(t * 0.45f, 2) < 1 ? IA_S_FACE : IA_S_FACE2, pal, 9, IA_BUS_X, y0);
    const float souffle = fmodf(t * 0.29f, 1);                         // le souffle, dans le froid
    if (souffle < 0.5f) {
      const float a = souffle / 0.5f, bx = IA_BUS_X + 4.5f + a * 3.5f, by = y0 + 3 - a * 3.5f;
      const float c = powf(1 - a, 1.2f) * 0.7f;
      pointer(by, bx, 236 * c, 220 * c, 190 * c);
      pointer(by - 1, bx + 1, 236 * c * 0.75f, 220 * c * 0.75f, 190 * c * 0.75f);
      pointer(by - 0.4f, bx + 1.6f, 236 * c * 0.5f, 220 * c * 0.5f, 190 * c * 0.5f);
    }
  } else if (s < 33.2f) {
    const float a = fminf(1.0f, (s - 29.2f) / 2.6f);
    const float y = y0 - a * 8 - fminf(1.0f, fmaxf(0.0f, s - 31.8f) / 0.6f) * 6;   // vers la porte, puis la marche
    const float dx = -fmaxf(0.0f, s - 32.4f) * 7;                      // et il disparait dans le bus
    const int pas = a < 1 ? (int)fmodf(s * 2.6f, 2) : 0;
    const int porte_x = IA_BUS_ARRET - IA_BUS_L + 1 + 32;              // vu dans l'encadrement de la porte
    ia_pal_gens(pal, k, 1.0f - a * 0.5f);
    if (s > 32.0f) ia_peindre(IA_S_DOS[pas], pal, 9, IA_BUS_X + dx, y, false, porte_x, porte_x + 5, IA_BUS_Y + 4, IA_BUS_Y + 16);
    else ia_peindre(IA_S_DOS[pas], pal, 9, IA_BUS_X + dx, y);
  }
  if (s >= 49) {
    const float a = (s - 49) / 11, x = 68 + (IA_BUS_X - 68) * a;
    ia_pal_gens(pal, k + 1, borne(1 - fabsf(x - IA_BUS_X) / 22, 0.15f, 1));
    ia_peindre(IA_S_MARCHE[(int)(s * 3.0f) % 4], pal, 9, x, y0, true);
  }
  ia_flocons(e.neige, 46, t, dt, e.lumi, IaC{255, 226, 170}, IaC{150, 160, 195});
}

// ===========================================================================
// 2. LA SUPERETTE SOUS LA PLUIE (_scene_superette). De face : la vitrine blanche un peu cyan, les rayonnages, le
// vendeur ; le trottoir mouille qui la reflete en long ; la pluie dans la lumiere, les gouttes de l'auvent. Un client
// arrive sous son parapluie, entre, fait ses courses derriere la vitre, paie, ressort et s'en va.

const float IA_SUP_P = 80.0f;   // une visite toutes les 80 s
const int IA_SUP_SOL = 47, IA_SUP_PIEDS = 53, IA_SUP_P0 = 42, IA_SUP_P1 = 56;
const float IA_NEON_R = 205, IA_NEON_G = 238, IA_NEON_B = 248;
static const float IA_SUP_HABITS[4][3][3] = {   // (manteau, cheveux, parapluie)
  {{60, 64, 92}, {40, 30, 26}, {210, 52, 56}},
  {{96, 80, 60}, {24, 22, 26}, {226, 190, 70}},
  {{40, 70, 64}, {90, 56, 36}, {170, 196, 210}},
  {{84, 44, 60}, {30, 26, 30}, {60, 90, 170}}};
const int IA_VY = 20, IA_VX = 3, IA_VH = 28, IA_VL = 56;   // la vitrine qui bouge : lignes 20-47, colonnes 3-58

struct E_superette {
  uint8_t fond[64][64][3];               // la facade, le trottoir, la lumiere dehors (avant la trame)
  uint8_t net[64][64][3];                // le calque net : l'etage, l'enseigne, la vitrine
  uint8_t m[64][64];                     // 1 : calque net ; 2 : devant (cadres, affiche) ; 4 : flaque
  uint8_t lumi[64][64];                  // la ou la pluie se voit
  uint8_t vit[28][56][3];                // la vitrine de cette image (vendeur, client, porte)
  float px[60], py[60], pv[60], pz[60];  // la pluie
  float g[14][3];                        // les eclaboussures : x, y, naissance
};

// le calque net de la superette : un rectangle (couleur + masque)
static void ia_net(E_superette &e, int y0, int y1, int x0, int x1, float r, float g, float b) {
  for (int y = max(y0, 0); y < min(y1, 64); y++)
    for (int x = max(x0, 0); x < min(x1, 64); x++) {
      e.net[y][x][0] = (uint8_t)(borne(r, 0, 255) + 0.5f);
      e.net[y][x][1] = (uint8_t)(borne(g, 0, 255) + 0.5f);
      e.net[y][x][2] = (uint8_t)(borne(b, 0, 255) + 0.5f);
      e.m[y][x] |= 1;
    }
}
static void ia_net_mul(E_superette &e, int y0, int y1, int x0, int x1, float k, float plus) {
  for (int y = y0; y < y1; y++)
    for (int x = x0; x < x1; x++)
      for (int c = 0; c < 3; c++) e.net[y][x][c] = (uint8_t)(borne(e.net[y][x][c] * k + plus, 0, 255) + 0.5f);
}

static void ia_sup_fond(E_superette &e) {
  const IaC mur = ia_niv(70, 60, 74, 2);
  ia_rect(0, 64, 0, 64, mur);
  for (int y = 1; y < 12; y += 3) ia_rect(y, y + 1, 0, 64, mur.r * 0.55f, mur.g * 0.55f, mur.b * 0.55f);   // le bardage
  ia_rect(3, 48, 61, 62, ia_niv(60, 66, 74, 3, 0.8f));                 // la gouttiere
  ia_rect(3, 48, 62, 63, ia_niv(60, 66, 74, 2));
  ia_rect(20, 48, 0, 3, ia_niv(80, 84, 96, 2, 1.2f));                  // le rideau baisse du voisin
  for (int y = 21; y < 48; y += 2) ia_rect(y, y + 1, 0, 3, ia_niv(80, 84, 96, 2, 0.6f));
  ia_rect(IA_SUP_SOL, IA_SUP_SOL + 1, 0, 64, ia_niv(90, 100, 120, 3)); // la marche
  ia_rect(48, 64, 0, 64, ia_niv(30, 44, 80, 2));                       // le trottoir mouille
  ia_rect(60, 61, 0, 64, ia_niv(80, 90, 110, 3));                      // la bordure
  ia_rect(61, 64, 0, 64, ia_niv(30, 40, 70, 1));                       // la chaussee
  for (int y = 0; y < 64; y++)                                         // la lumiere de la vitrine, dehors
    for (int x = 0; x < 64; x++) {
      float l = 0;
      if (y >= 48 && y < 60) l += expf(-powf(hypotf((x - 30) / 27.0f, (y - 48) / 4.0f), 1.5f)) * 0.45f;
      if (x < 3 || x > 58) {
        const float a = (x - 30) / 30.0f, b = (y - 34) / 16.0f;
        l += expf(-(a * a + b * b)) * 0.25f;
      }
      ajouter(y, x, l, 140, 178, 190);
      const float a = (x - 30) / 30.0f, b = (y - 40) / 18.0f;
      const float lp = (y > 19 ? expf(-(a * a + b * b)) * 0.95f : 0.0f) + 0.08f;
      e.lumi[y][x] = (uint8_t)(borne(lp, 0, 1) * 255 + 0.5f);
    }
  halo(31, 12, 9, 60, 70, 110, 0.5f, 2.2f);                            // l'enseigne eclaire le mur
  ia_garder(e.fond);
  // le calque net : l'etage (rideau, une plante), le climatiseur, l'enseigne, la vitrine
  ia_net(e, 2, 11, 6, 17, 40, 32, 34);
  ia_net(e, 3, 9, 7, 16, 214, 140, 72);
  ia_net(e, 3, 9, 7, 10, 160, 82, 56);
  ia_net(e, 3, 9, 11, 12, 40, 32, 34);
  ia_net(e, 6, 7, 7, 16, 40, 32, 34);
  ia_net(e, 3, 4, 12, 16, 240, 176, 96);
  ia_net(e, 7, 9, 13, 15, 36, 40, 30);
  ia_net(e, 6, 7, 12, 13, 36, 40, 30);
  ia_net(e, 6, 7, 14, 15, 36, 40, 30);
  ia_net(e, 5, 6, 13, 14, 36, 40, 30);
  ia_net(e, 9, 11, 5, 18, 76, 68, 76);
  ia_net(e, 10, 11, 5, 18, 50, 44, 50);
  ia_net(e, 3, 9, 46, 56, 58, 60, 68);                                 // le climatiseur
  ia_net(e, 4, 8, 47, 52, 34, 36, 42);
  for (int x = 47; x < 52; x += 2) ia_net(e, 4, 8, x, x + 1, 66, 68, 76);
  ia_net(e, 3, 4, 46, 56, 88, 90, 100);
  ia_net(e, 12, 20, 2, 61, 26, 30, 42);                                // l'enseigne : un caisson bleu nuit
  ia_net(e, 13, 19, 3, 60, 30, 56, 104);
  ia_net(e, 13, 14, 3, 60, 60, 96, 150);
  ia_net(e, 14, 18, 6, 10, 250, 214, 110);                             // son croissant de lune
  static const int CREUX[8][2] = {{14, 6}, {17, 6}, {15, 8}, {15, 9}, {16, 8}, {16, 9}, {14, 9}, {17, 9}};
  for (int i = 0; i < 8; i++) ia_net(e, CREUX[i][0], CREUX[i][0] + 1, CREUX[i][1], CREUX[i][1] + 1, 30, 56, 104);
  for (int x = 13; x < 46; x += 2) {                                   // un nom, en traits
    ia_net(e, 16, 17, x, x + 1, 190, 210, 226);
    const int y = x % 4 == 1 ? 15 : 17;
    ia_net(e, y, y + 1, x, x + 1, 190, 210, 226);
  }
  ia_net(e, 12, 19, 49, 58, 196, 56, 48);                              // et un cartouche rouge : 24
  static const char *const VINGT4[5] = {"XXX.X.X", "..X.X.X", "XXX.XXX", "X.....X", "XXX...X"};
  for (int yy = 0; yy < 5; yy++)
    for (int xx = 0; xx < 7; xx++)
      if (VINGT4[yy][xx] == 'X') ia_net(e, 13 + yy, 14 + yy, 50 + xx, 51 + xx, 250, 236, 220);
  ia_net(e, 19, 20, 2, 61, 20, 22, 28);                                // l'auvent, mince
  const float nr = IA_NEON_R, ng = IA_NEON_G, nb = IA_NEON_B;
  ia_net(e, 20, 48, 3, 59, 0, 0, 0);
  ia_net(e, 20, 47, 3, 59, nr * 0.5f, ng * 0.5f, nb * 0.5f);           // le fond du magasin
  ia_net(e, 21, 22, 4, 58, 240, 252, 255);                             // les tubes au plafond
  ia_net(e, 22, 23, 4, 58, nr * 0.8f, ng * 0.8f, nb * 0.8f);
  ia_net(e, 23, 24, 4, 58, nr * 0.62f, ng * 0.62f, nb * 0.62f);
  ia_net(e, 43, 47, 3, 59, nr * 0.66f, ng * 0.66f, nb * 0.66f);        // le carrelage
  ia_net(e, 45, 46, 3, 59, nr * 0.58f, ng * 0.58f, nb * 0.58f);
  static const float PRODUITS[8][3] = {{220, 60, 60}, {240, 190, 60}, {70, 150, 220}, {90, 190, 110},
                                       {236, 236, 226}, {230, 120, 50}, {160, 90, 180}, {250, 150, 160}};
  static const int RAYONS[2][2] = {{22, 40}, {45, 55}};
  for (int i = 0; i < 2; i++) {                                        // les rayonnages (vitrine, et par la porte)
    const int x0 = RAYONS[i][0], x1 = RAYONS[i][1];
    ia_net(e, 24, 43, x0, x1, nr * 0.36f, ng * 0.36f, nb * 0.36f);
    for (int ry = 25; ry <= 40; ry += 5) {
      ia_net(e, ry + 2, ry + 3, x0, x1, nr * 0.72f, ng * 0.72f, nb * 0.72f);   // la tablette
      for (int x = x0; x < x1; x++)
        if (hasard(0, 1) < 0.85f) {
          const int h = hasard(0, 1) < 0.6f ? 2 : 1;
          const float *c = PRODUITS[aleatoire() % 8];
          const float k = hasard(0.6f, 0.9f);
          ia_net(e, ry + 2 - h, ry + 2, x, x + 1, c[0] * k, c[1] * k, c[2] * k);
        }
    }
    ia_net(e, 24, 43, x0 - 1, x0, nr * 0.3f, ng * 0.3f, nb * 0.3f);
  }
  ia_net(e, 32, 46, 4, 20, 92, 70, 58);                                // le comptoir
  ia_net(e, 32, 33, 4, 20, 176, 160, 146);
  ia_net(e, 34, 44, 5, 19, 74, 56, 48);
  ia_net(e, 29, 32, 15, 19, 34, 36, 44);                               // la caisse
  ia_net(e, 30, 31, 16, 18, 90, 220, 140);
  ia_net(e, 24, 30, 4, 9, 176, 166, 132);                              // une affiche au mur
  ia_net(e, 25, 28, 5, 8, 200, 100, 72);
  ia_net(e, 20, 21, 3, 59, 30, 34, 40);                                // les cadres de la vitrine et de la porte
  ia_net(e, 20, 48, 3, 4, 30, 34, 40);
  ia_net(e, 20, 48, 40, 42, 30, 34, 40);
  ia_net(e, 20, 48, 56, 59, 30, 34, 40);
  ia_net(e, 46, 47, 3, 41, 30, 34, 40);
  ia_net(e, 38, 43, 24, 31, 220, 200, 120);                            // une affiche collee sur la vitre
  ia_net(e, 39, 42, 25, 30, 190, 70, 56);
  ia_net(e, 40, 41, 26, 29, 240, 220, 180);
  ia_net_mul(e, 20, 46, 4, 40, 0.93f, 0);                              // la vitre, un rien plus terne
  for (int i = 0; i < 6; i++) ia_net_mul(e, 24 + i * 3, 27 + i * 3, 33 - i, 34 - i, 1, 22);   // un reflet en biais
  for (int y = 0; y < 64; y++)                                         // devant (cadres, affiche), et les flaques
    for (int x = 0; x < 64; x++) {
      const bool devant = (y >= 20 && y < 48 && (x == 3 || x == 40 || x == 41 || (x >= 56 && x < 59))) ||
                          (y == 46 && x >= 3 && x < 41) || (y >= 38 && y < 43 && x >= 24 && x < 31) ||
                          (y == 20 && x >= 3 && x < 59);
      if (devant) e.m[y][x] |= 2;
      const float a = (x - 19) / 9.0f, b = (y - 53.5f) / 2.2f, c = (x - 47) / 7.0f, d = (y - 57) / 1.8f;
      if (a * a + b * b < 1 || c * c + d * d < 1) e.m[y][x] |= 4;
    }
}

// _ia_sup_client : ou est le client a l'instant s du cycle (ou : 0 absent, 1 dehors, 2 porte, 3 dedans)
struct IaClient { int ou; float x, y; const IaSprite *sp; bool miroir; float ouvert; };
static IaClient ia_sup_client(float s) {
  const float px = 46, pieds = IA_SUP_PIEDS, dedans = IA_SUP_SOL - 2;
  const IaSprite *marche = &IA_S_MARCHE[(int)(s * 3) % 4];
  if (s < 9) return {1, 68 + (px - 68) * s / 9, pieds, marche, true, 1};              // il arrive sous son parapluie
  if (s < 10.5f) return {1, px, pieds, &IA_S_DOS[0], false, 1 - (s - 9) / 1.5f};        // il le replie
  if (s < 12.5f) return {2, px, pieds + (dedans - pieds) * (s - 10.5f) / 2, &IA_S_DOS[(int)(s * 3) % 2], false, 0};
  if (s < 57) {                                                        // dedans : les rayons, la caisse, la porte
    static const float TRAJET[9][2] = {{12.5f, 46}, {17, 32}, {29, 32}, {31, 26}, {40, 26}, {43, 20}, {51, 20},
                                       {56, 46}, {57, 46}};
    for (int i = 0; i < 8; i++) {
      const float a = TRAJET[i][0], xa = TRAJET[i][1], b = TRAJET[i + 1][0], xb = TRAJET[i + 1][1];
      if (s >= a && s < b) {
        const float x = xa + (xb - xa) * (s - a) / (b - a);
        if (xa == xb) return {3, x, dedans, xa == 20 ? &IA_S_MARCHE[0] : &IA_S_DOS[0], xa == 20, 0};
        return {3, x, dedans, marche, xb < xa, 0};
      }
    }
  }
  if (s < 59) return {2, px, dedans + (pieds - dedans) * (s - 57) / 2, &IA_S_PLUIE, false, 0};   // il ressort
  if (s < 60.5f) return {1, px, pieds, &IA_S_PLUIE, false, (s - 59) / 1.5f};                     // rouvre son parapluie
  if (s < 73) return {1, px + (-12 - px) * (s - 60.5f) / 12.5f, pieds, marche, true, 1};        // et s'en va
  return {0, 0, 0, nullptr, false, 0};
}

// _ia_sup_palette : le client k, en contre-jour devant la vitrine (lumiere = le bord eclaire) ; `ombre` : son reflet
static int ia_pal_client(IaTeinte *p, int k, float lumiere, float ombre = 1, float alpha = 1) {
  const float *ma = IA_SUP_HABITS[k % 4][0], *ch = IA_SUP_HABITS[k % 4][1], *pa = IA_SUP_HABITS[k % 4][2];
  const float q = 0.45f + 0.35f * lumiere, nr = IA_NEON_R, ng = IA_NEON_G, nb = IA_NEON_B, o = ombre;
  p[0] = {'H', (ch[0] * 0.6f + nr * 0.35f * lumiere) * o, (ch[1] * 0.6f + ng * 0.35f * lumiere) * o, (ch[2] * 0.6f + nb * 0.35f * lumiere) * o, alpha};
  p[1] = {'h', ch[0] * q * o, ch[1] * q * o, ch[2] * q * o, alpha};
  p[2] = {'f', 190 * q * 0.9f * o, 146 * q * 0.9f * o, 116 * q * 0.9f * o, alpha};
  p[3] = {'s', ma[0] * q * 1.1f * o, ma[1] * q * 1.1f * o, ma[2] * q * 1.1f * o, alpha};
  p[4] = {'C', (ma[0] * 0.6f + nr * 0.3f * lumiere) * o, (ma[1] * 0.6f + ng * 0.3f * lumiere) * o, (ma[2] * 0.6f + nb * 0.3f * lumiere) * o, alpha};
  p[5] = {'c', ma[0] * q * o, ma[1] * q * o, ma[2] * q * o, alpha};
  p[6] = {'d', ma[0] * q * 0.6f * o, ma[1] * q * 0.6f * o, ma[2] * q * 0.6f * o, alpha};
  p[7] = {'p', 30 * q * o, 30 * q * o, 42 * q * o, alpha};
  p[8] = {'b', (14 + 8 * q) * o, (14 + 8 * q) * o, (20 + 8 * q) * o, alpha};
  p[9] = {'u', pa[0] * (0.55f + 0.25f * lumiere) * o, pa[1] * (0.55f + 0.25f * lumiere) * o, pa[2] * (0.55f + 0.25f * lumiere) * o, alpha};
  p[10] = {'U', pa[0] * 0.4f * o, pa[1] * 0.4f * o, pa[2] * 0.4f * o, alpha};
  p[11] = {'i', 50 * o, 50 * o, 56 * o, alpha};
  p[12] = {'L', (pa[0] * 0.6f + nr * 0.3f * lumiere) * o, (pa[1] * 0.6f + ng * 0.3f * lumiere) * o, (pa[2] * 0.6f + nb * 0.3f * lumiere) * o, alpha};
  return 13;
}

// _ia_sup_porte : les deux vantaux vitres de la porte automatique, ecartes de o (0 ferme .. 1 ouvert)
static void ia_sup_porte(float o) {
  const int d = (int)roundf(o * 6);
  const int A[2] = {IA_SUP_P0 - d, IA_SUP_P0 + 7 + d}, B[2] = {IA_SUP_P0 + 7 - d, IA_SUP_P1 + d};
  const int BORD[2] = {IA_SUP_P0 + 6 - d, IA_SUP_P0 + 7 + d};
  for (int i = 0; i < 2; i++) {
    const int a = max(A[i], IA_SUP_P0), b = min(B[i], IA_SUP_P1);
    for (int y = 21; y < 46; y++)
      for (int x = a; x < b; x++) {
        float *p = scene[y][x];
        p[0] = p[0] * 0.86f + 10; p[1] = p[1] * 0.86f + 16; p[2] = p[2] * 0.86f + 20;
      }
    if (BORD[i] >= IA_SUP_P0 && BORD[i] < IA_SUP_P1) ia_rect(21, 46, BORD[i], BORD[i] + 1, 40, 46, 54);
  }
}

void s_superette(int humeur, bool debut, float t, float ecoule, float dt) {
  E_superette &e = etat_ecran<E_superette>(debut);
  (void)humeur;
  if (debut) {
    ia_sup_fond(e);
    for (int i = 0; i < 14; i++) { e.g[i][0] = 0; e.g[i][1] = 0; e.g[i][2] = -9; }
    for (int i = 0; i < 60; i++) {
      e.px[i] = hasard(0, 64); e.py[i] = hasard(-4, 64); e.pv[i] = hasard(42, 62); e.pz[i] = hasard(0, 1);
    }
  }
  const float u = t / IA_SUP_P;
  const int k = (int)floorf(u);
  const float s = (u - k) * IA_SUP_P;
  // la scene : le decor, puis la vitrine nette, que le vendeur, le client et la porte modifient
  ia_reprendre(e.fond);
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++)
      if (e.m[y][x] & 1) peindre(y, x, e.net[y][x][0], e.net[y][x][1], e.net[y][x][2]);
  const bool lit = fmodf(t * 0.07f, 1) < 0.62f && !(s >= 42 && s < 52);   // le vendeur lit, leve la tete
  const IaTeinte vend[4] = {{'h', 40, 32, 30, 1}, {'f', 196, 150, 120, 1}, {'v', 40, 110, 104, 1}, {'w', 220, 226, 226, 1}};
  ia_peindre(IA_S_VENDEUR[lit ? 1 : 0], vend, 4, 8, 26);
  const float ph = fmodf(t / 37.0f, 1);                                // le 24 gresille, rarement et doucement
  float f24 = 1;
  if (ph < 0.06f) { const float sn = sinf(IA_PI * ph / 0.03f); f24 = 1 - 0.28f * sn * sn; }
  const IaClient cl = ia_sup_client(s);
  IaTeinte pal[13];
  if (cl.ou == 3) {                                                    // derriere la vitre : une silhouette
    ia_pal_client(pal, k, 0.2f);
    ia_peindre(*cl.sp, pal, 13, cl.x - 3, cl.y - 13, cl.miroir, 4, 56, 21, 47);
    for (int y = 20; y < 48; y++)
      for (int x = 3; x < 59; x++)
        if (e.m[y][x] & 2) peindre(y, x, e.net[y][x][0], e.net[y][x][1], e.net[y][x][2]);
  }
  const float o = borne(fminf((s - 9.6f) / 0.8f, (13.2f - s) / 0.8f), 0, 1) +   // la porte : ouverte pour entrer,
                  borne(fminf((s - 56.4f) / 0.8f, (60.0f - s) / 0.8f), 0, 1);   // puis pour sortir
  ia_sup_porte(o);
  for (int y = 0; y < IA_VH; y++)                                      // la vitrine de cette image, gardee nette
    for (int x = 0; x < IA_VL; x++)
      for (int c = 0; c < 3; c++) e.vit[y][x][c] = (uint8_t)(borne(scene[IA_VY + y][IA_VX + x][c], 0, 255) + 0.5f);
  // le trottoir mouille : chaque colonne de la vitrine s'y etire en un long reflet, que la pluie fait trembler
  float col[64][3];
  for (int x = 0; x < 64; x++) {
    col[x][0] = col[x][1] = col[x][2] = 0;
    if (x < IA_VX || x >= IA_VX + IA_VL) continue;
    for (int y = 24; y < 46; y++)
      for (int c = 0; c < 3; c++) col[x][c] += scene[y][x][c];
    for (int c = 0; c < 3; c++) col[x][c] *= 1.0f / 22;
  }
  float onde[64];
  for (int x = 0; x < 64; x++) onde[x] = sinf(x * 0.45f + t * 0.3f) * 1.5f;
  for (int y = 48; y < 60; y++) {
    const float d = y - 48.0f, k0 = expf(-d / 7.0f) * 0.8f;
    for (int x = 0; x < 64; x++) {
      if (x < IA_VX || x >= IA_VX + IA_VL) continue;
      const float tremble = 0.6f + 0.4f * sinf(d * 1.9f - t * 2.2f + onde[x]);
      ajouter(y, x, k0 * tremble, col[x][0], col[x][1], col[x][2]);
    }
  }
  for (int y = 61; y < 64; y++)
    for (int x = IA_VX; x < IA_VX + IA_VL; x++) ajouter(y, x, 0.12f, col[x][0], col[x][1], col[x][2]);
  if (o > 0) ia_halo(49, 49.5f, 3.5f, 150, 190, 200, 0.6f * o, 1.6f);  // la porte ouverte : plus de lumiere dehors
  tramer(8);
  for (int y = 0; y < 64; y++)                                         // la vitrine reste nette
    for (int x = 0; x < 64; x++) {
      if (!(e.m[y][x] & 1)) continue;
      if (y >= IA_VY && y < IA_VY + IA_VH && x >= IA_VX && x < IA_VX + IA_VL) {
        const uint8_t *v = e.vit[y - IA_VY][x - IA_VX];
        peindre(y, x, v[0], v[1], v[2]);
      } else {
        const float k24 = (y >= 12 && y < 19 && x >= 49 && x < 58) ? f24 : 1.0f;
        peindre(y, x, e.net[y][x][0] * k24, e.net[y][x][1] * k24, e.net[y][x][2] * k24);
      }
    }
  for (int y = 48; y < 64; y++) {                                      // dans les flaques, un vrai miroir qui ondule
    const int ond = (int)rintf(sinf(y * 2.3f + t * 2.0f) * 0.7f);
    const int sy = (int)borne(IA_SUP_SOL - (y - IA_SUP_SOL) / 2 - 1, 21, 46);
    for (int x = 0; x < 64; x++) {
      if (!(e.m[y][x] & 4)) continue;
      const int sx = min(max(x + ond, 0), 63);
      float v[3] = {0, 0, 0};
      if (sx >= IA_VX && sx < IA_VX + IA_VL)
        for (int c = 0; c < 3; c++) v[c] = e.vit[sy - IA_VY][sx - IA_VX][c];
      float *p = scene[y][x];
      for (int c = 0; c < 3; c++) p[c] = p[c] * 0.35f + v[c] * 0.5f;
    }
  }
  if (cl.ou == 1 || cl.ou == 2) {                                      // le client dehors (en contre-jour), son reflet
    const float lum = borne(1.2f - fabsf(cl.x - 30) / 34, 0.2f, 1);
    const bool boite = cl.ou == 2 && cl.y < IA_SUP_PIEDS - 3;
    if (!boite) {
      ia_pal_client(pal, k, lum, 0.5f, 0.55f);
      ia_peindre(*cl.sp, pal, 13, cl.x - 3, cl.y + 1, cl.miroir, 0, 64, 0, 64, true, 7);
    }
    ia_pal_client(pal, k, lum);
    if (boite) ia_peindre(*cl.sp, pal, 13, cl.x - 3, cl.y - 13, cl.miroir, IA_SUP_P0, IA_SUP_P1, 21, 64);
    else ia_peindre(*cl.sp, pal, 13, cl.x - 3, cl.y - 13, cl.miroir);
    if (cl.ouvert > 0.66f) ia_peindre(IA_S_PARA, pal, 13, cl.x - 4, cl.y - 18, cl.miroir);
    else if (cl.ouvert > 0.2f) ia_peindre(IA_S_PARA_MI, pal, 13, cl.x - 3, cl.y - 17, cl.miroir);
  }
  static const float GOUTTES[5][2] = {{7, 1.7f}, {16, 2.3f}, {27, 1.9f}, {36, 2.6f}, {58, 1.5f}};
  for (int i = 0; i < 5; i++) {                                        // les gouttes qui tombent de l'auvent
    const int gx = (int)GOUTTES[i][0];
    const float ph2 = fmodf(t / GOUTTES[i][1] + i * 0.37f, 1);
    if (ph2 < 0.5f) pointer(20, gx, 120 * ph2 * 2, 150 * ph2 * 2, 160 * ph2 * 2);
    else {
      const float a = (ph2 - 0.5f) / 0.5f, gy = 20 + 27 * a * a;
      if (gy < 47) {
        pointer(gy, gx, 230, 246, 255);
        if (a > 0.4f) pointer(gy - 1, gx, 110, 130, 140);
      }
    }
  }
  // la pluie : des traits fins, qu'on ne voit vraiment que dans la lumiere ; une eclaboussure ou elle touche
  const float pas = fminf(dt, 0.5f);
  int gicle = 0;
  for (int i = 0; i < 60; i++) {
    e.py[i] += e.pv[i] * pas;
    e.px[i] += e.pv[i] * 0.12f * pas;
    if (e.py[i] > 48 + e.pz[i] * 14) {
      if (gicle < 4) {
        int j = 0;
        for (int q = 1; q < 14; q++) if (e.g[q][2] < e.g[j][2]) j = q;
        e.g[j][0] = e.px[i]; e.g[j][1] = 48 + e.pz[i] * 14; e.g[j][2] = ecoule;
        gicle++;
      }
      e.py[i] -= 66 + hasard(0, 6);
    }
    e.px[i] = fmodf(fmodf(e.px[i], 64) + 64, 64);
  }
  for (int i = 0; i < 60; i++)
    for (int j = 0; j < 3; j++) {
      const int yy = (int)floorf(e.py[i] - j), xx = ((int)floorf(e.px[i] - j * 0.12f) + 64) & 63;
      if (yy < 0 || yy >= 64) continue;
      const float lu = e.lumi[yy][xx] * (1.0f / 255), k1 = (0.5f + 0.5f * e.pz[i]) * (1 - j * 0.28f);
      pointer(yy, xx, (60 + 170 * lu) * k1, (74 + 205 * lu) * k1, (96 + 215 * lu) * k1);
    }
  for (int i = 0; i < 14; i++) {
    const float age = ecoule - e.g[i][2];
    if (age < 0 || age >= 0.3f) continue;
    const float gx = e.g[i][0], gy = e.g[i][1];
    const float lu = e.lumi[((int)gy) & 63][((int)gx) & 63] * (1.0f / 255), c = (0.35f + 0.65f * lu) * (1 - age / 0.3f);
    if (age < 0.12f) pointer(gy - 1, gx, 150 * c, 186 * c, 200 * c);
    else {
      pointer(gy - 1, gx - 1, 150 * c, 186 * c, 200 * c);
      pointer(gy - 1, gx + 1, 150 * c, 186 * c, 200 * c);
    }
  }
}

// ===========================================================================
// 3. LE DISTRIBUTEUR AU COIN DE LA RUE (_scene_distributeur). Une rue endormie facon Japon : un mur de parpaings,
// un poteau et ses fils, un miroir de virage ; le distributeur luit tout seul. Des papillons de nuit tournent
// autour ; un chat noir assis a cote bouge la queue, se leche, s'en va et revient ; parfois un passant achete a boire.

const int IA_DX = 21, IA_DY = 16;     // le coin haut-gauche du distributeur (18 x 35)
const float IA_DIS_P = 70.0f, IA_CHAT_P = 97.0f;
const int IA_CHAT_X = 42;

struct E_distributeur {
  uint8_t fond[64][64][3];               // la rue et toute la lumiere du distributeur (avant la trame)
  uint8_t net[64][64][3];                // le distributeur, le poteau, les fils, le miroir, une fenetre
  uint8_t m[64][64];                     // 1 : calque net ; 2 : ciel libre
  uint8_t ey[22], ex[22];                // les etoiles
  float ep[22], el[22];
  float mites[5][4];                     // les papillons de nuit
};

static void ia_dnet(E_distributeur &e, int y0, int y1, int x0, int x1, float r, float g, float b) {
  for (int y = max(y0, 0); y < min(y1, 64); y++)
    for (int x = max(x0, 0); x < min(x1, 64); x++) {
      e.net[y][x][0] = (uint8_t)(borne(r, 0, 255) + 0.5f);
      e.net[y][x][1] = (uint8_t)(borne(g, 0, 255) + 0.5f);
      e.net[y][x][2] = (uint8_t)(borne(b, 0, 255) + 0.5f);
      e.m[y][x] |= 1;
    }
}

static void ia_dis_fond(E_distributeur &e) {
  for (int y = 0; y < 64; y++) {                                       // le ciel
    const float k = powf(borne(y / 30.0f, 0, 1), 1.6f);
    for (int x = 0; x < 64; x++) {
      peindre(y, x, 6 + 22 * k, 8 + 28 * k, 20 + 50 * k);
      e.m[y][x] = 2;
    }
  }
  static const float ARBRES[2][3] = {{-6, 22, 15}, {41, 70, 17}};
  for (int i = 0; i < 2; i++) {                                        // les arbres du jardin, derriere le mur
    const float x0 = ARBRES[i][0], x1 = ARBRES[i][1], h = ARBRES[i][2], cx = (x0 + x1) / 2;
    for (int x = 0; x < 64; x++) {
      if (x < x0 || x >= x1) continue;
      const float bosse = h + 2.5f * sinf(x * 0.7f + cx) + 1.5f * sinf(x * 1.9f + 1) + fabsf(x - cx) * 0.3f;
      for (int y = 0; y < 64; y++)
        if (y >= bosse) { peindre(y, x, 9, 15, 16); e.m[y][x] = 0; }
    }
  }
  for (int x = 13; x < 50; x++) {                                      // une maison au toit de tuiles
    const float toit = 20 + fabsf(x - 31) * 0.16f;
    for (int y = 0; y < 64; y++) {
      if (y < toit) continue;
      peindre(y, x, 14, 16, 24);
      e.m[y][x] = 0;
      if (y < toit + 1.2f && x > 13 && x < 49) peindre(y, x, 30, 34, 48);
    }
  }
  ia_rect(24, 30, 14, 48, 13, 12, 14);
  // le mur de parpaings et l'asphalte, eclaires par le distributeur
  for (int y = 30; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float r = 104, g = 106, b = 114;                                 // le mur
      if (y == 30) { r = 150; g = 152; b = 158; }                      // son chaperon
      else if (y < 50) {
        const bool joint = (y >= 33 && y % 3 == 0) ||
                           ((y % 3 == 1 || y % 3 == 2) && (x - (((y - (y % 3 == 2 ? 1 : 0)) / 3) % 2) * 4) % 8 == 0 &&
                            x >= (((y - (y % 3 == 2 ? 1 : 0)) / 3) % 2) * 4);
        if (joint) { r = 62; g = 62; b = 70; }
      } else if (y == 50) { r = 36; g = 36; b = 46; }                  // le caniveau
      else if (y == 59 || y == 60) { r = 170; g = 170; b = 160; }      // la ligne blanche
      else { r = 66; g = 68; b = 84; }                                 // l'asphalte
      const float bx = borne(x, IA_DX, IA_DX + 19), by = borne(y, IA_DY, IA_DY + 34);
      const float dbord = hypotf(x - bx, y - by);
      float l = expf(-powf(hypotf((x - 29.5f) / 16.0f, (y - 32) / 16.0f), 1.2f)) * 1.15f;
      l += expf(-dbord / 4.5f) * 0.7f;                                 // tout pres, le mur est inonde
      if (y >= 50) l += expf(-powf(hypotf((x - 29.5f) / 14.0f, (y - 52.5f) / 4.2f), 1.3f)) * 1.5f;
      peindre(y, x, r * (0.2f + l * 1.15f), g * (0.2f + l * 1.32f), b * (0.2f + l * 1.55f));
    }
  for (int y = 0; y < 30; y++)                                         // sa lueur dans l'air
    for (int x = 0; x < 64; x++) {
      const float bx = borne(x, IA_DX, IA_DX + 19), by = borne(y, IA_DY, IA_DY + 34);
      ajouter(y, x, expf(-hypotf(x - bx, y - by) / 3.0f), 60, 80, 110);
    }
  ia_garder(e.fond);
  // le distributeur (ses canettes : tirees une fois)
  const int x0 = IA_DX, y0 = IA_DY;
  ia_dnet(e, y0, y0 + 35, x0, x0 + 18, 40, 70, 120);                   // la caisse, bleue
  ia_dnet(e, y0, y0 + 35, x0 + 18, x0 + 20, 22, 34, 56);               // son flanc, dans l'ombre
  ia_dnet(e, y0, y0 + 1, x0, x0 + 18, 70, 100, 150);
  ia_dnet(e, y0 + 1, y0 + 5, x0 + 1, x0 + 17, 214, 236, 255);          // le bandeau lumineux
  ia_dnet(e, y0 + 3, y0 + 4, x0 + 1, x0 + 17, 80, 150, 220);
  ia_dnet(e, y0 + 2, y0 + 3, x0 + 3, x0 + 6, 220, 70, 70);
  ia_dnet(e, y0 + 6, y0 + 22, x0 + 1, x0 + 17, 196, 222, 246);         // la vitrine des boissons
  static const float CANETTES[9][3] = {{220, 50, 50}, {250, 200, 60}, {60, 120, 220}, {240, 240, 236}, {80, 180, 100},
                                       {250, 130, 50}, {130, 70, 150}, {50, 60, 70}, {220, 100, 140}};
  for (int r = 0; r < 3; r++) {
    const int ry = y0 + 7 + r * 5;
    for (int c = 0; c < 5; c++) {
      const int cx = x0 + 2 + c * 3;
      const float *k = CANETTES[aleatoire() % 9];
      ia_dnet(e, ry, ry + 3, cx, cx + 2, k[0], k[1], k[2]);
      ia_dnet(e, ry, ry + 1, cx, cx + 2, k[0] * 0.6f + 100, k[1] * 0.6f + 100, k[2] * 0.6f + 100);   // le couvercle
      ia_dnet(e, ry + 3, ry + 4, cx, cx + 2, 90, 110, 140);           // le bouton
    }
    ia_dnet(e, ry + 4, ry + 5, x0 + 1, x0 + 17, 150, 176, 206);
  }
  ia_dnet(e, y0 + 22, y0 + 23, x0, x0 + 18, 30, 50, 90);
  ia_dnet(e, y0 + 23, y0 + 28, x0 + 1, x0 + 17, 44, 74, 126);          // monnaie, billets, afficheur
  ia_dnet(e, y0 + 24, y0 + 26, x0 + 13, x0 + 16, 30, 36, 50);
  ia_dnet(e, y0 + 24, y0 + 25, x0 + 14, x0 + 15, 120, 200, 255);
  ia_dnet(e, y0 + 27, y0 + 28, x0 + 13, x0 + 16, 60, 200, 120);
  ia_dnet(e, y0 + 24, y0 + 27, x0 + 3, x0 + 9, 190, 200, 210);         // une petite affiche
  ia_dnet(e, y0 + 25, y0 + 26, x0 + 4, x0 + 8, 210, 70, 60);
  ia_dnet(e, y0 + 29, y0 + 33, x0 + 2, x0 + 16, 16, 18, 26);           // la trappe
  ia_dnet(e, y0 + 29, y0 + 30, x0 + 2, x0 + 16, 70, 84, 104);
  ia_dnet(e, y0 + 33, y0 + 35, x0, x0 + 18, 24, 30, 44);               // le socle
  ia_dnet(e, 0, 51, 53, 56, 18, 18, 24);                               // le poteau, ses fils, le miroir
  ia_dnet(e, 0, 51, 53, 54, 40, 42, 52);
  ia_dnet(e, 26, 51, 53, 54, 66, 80, 104);
  ia_dnet(e, 5, 7, 48, 61, 20, 20, 26);
  ia_dnet(e, 9, 15, 56, 59, 34, 36, 44);                               // le transformateur
  ia_dnet(e, 9, 10, 56, 59, 60, 64, 76);
  static const float FILS[3][2] = {{5, 6}, {6, 9}, {10, 4}};
  for (int i = 0; i < 3; i++)                                          // les fils, qui pendent un peu
    for (int x = 0; x < 64; x++) {
      if (x >= 48 && x < 61) continue;
      const float u = x < 48 ? (48 - x) / 48.0f : 0.0f;
      const int y = (int)roundf(FILS[i][0] + FILS[i][1] * 4 * u * (1 - u) + u * 4 + (x > 60 ? (x - 60) * 0.4f : 0.0f));
      if (y >= 0 && y < 64 && !(e.m[y][x] & 1)) ia_dnet(e, y, y + 1, x, x + 1, 26, 26, 36);
    }
  ia_dnet(e, 21, 51, 9, 10, 130, 60, 30);                              // le miroir de virage
  for (int y = 12; y < 24; y++)
    for (int x = 3; x < 15; x++) {
      const float d = hypotf(x - 9.0f, y - 18.0f);
      if (d < 3.6f) ia_dnet(e, y, y + 1, x, x + 1, 190, 90, 40);
      if (d < 2.6f) ia_dnet(e, y, y + 1, x, x + 1, hypotf(x - 10.0f, y - 19.0f) < 1.2f ? 150 : 40,
                            hypotf(x - 10.0f, y - 19.0f) < 1.2f ? 180 : 56, hypotf(x - 10.0f, y - 19.0f) < 1.2f ? 220 : 90);
    }
  ia_dnet(e, 25, 28, 44, 46, 196, 130, 70);                            // une fenetre encore allumee, la-bas
  for (int i = 0; i < 5; i++)
    for (int j = 0; j < 4; j++) e.mites[i][j] = hasard(0, 6.3f);
  for (int i = 0; i < 22; i++) {                                       // des etoiles, dans le ciel libre seulement
    int y, x, essais = 0;
    do { y = aleatoire() % 22; x = aleatoire() % 64; } while ((!(e.m[y][x] & 2) || (e.m[y][x] & 1)) && ++essais < 200);
    e.ey[i] = (uint8_t)y; e.ex[i] = (uint8_t)x;
    e.ep[i] = hasard(0, 6.3f); e.el[i] = hasard(0.3f, 1.0f);
  }
}

// _ia_chat : le chat a l'instant s de sa vie ; renvoie false s'il n'est pas la
static bool ia_chat(float s, float &x, const IaSprite *&sp, bool &miroir, bool &assis) {
  const bool pas1 = fmodf(s * 3, 2) < 1;
  if (s < 30 || (s >= 38 && s < 60) || s >= 88) { x = IA_CHAT_X; sp = &IA_S_CHAT_ASSIS; miroir = false; assis = true; return true; }
  if (s < 38) { x = IA_CHAT_X; sp = fmodf(s * 1.6f, 2) < 1 ? &IA_S_CHAT_LECHE : &IA_S_CHAT_LECHE2; miroir = false; assis = true; return true; }
  if (s < 66) { x = IA_CHAT_X + (s - 60) * 4.4f; sp = pas1 ? &IA_S_CHAT_MARCHE1 : &IA_S_CHAT_MARCHE2; miroir = false; assis = false; return true; }
  if (s < 80) return false;
  const float a = fminf(1.0f, (s - 80) / 6.5f);                        // il revient, et se rassoit
  if (a < 1) { x = IA_CHAT_X + 26 * (1 - a); sp = pas1 ? &IA_S_CHAT_MARCHE1 : &IA_S_CHAT_MARCHE2; miroir = true; assis = false; return true; }
  x = IA_CHAT_X; sp = &IA_S_CHAT_ASSIS; miroir = false; assis = true;
  return true;
}

// _ia_passant : il vient de la gauche, achete, repart a droite ; renvoie false s'il n'est pas la
static bool ia_passant(float s, float &x, const IaSprite *&sp) {
  const float xa = 26;
  if (s < 9) { x = -9 + (xa + 9) * s / 9; sp = &IA_S_MARCHE[(int)(s * 3) % 4]; return true; }
  if (s < 11 || (s >= 12 && s < 13.5f) || (s >= 15.5f && s < 16.5f)) { x = xa; sp = &IA_S_DOS[0]; return true; }
  if (s < 12) { x = xa; sp = &IA_S_ACHAT[0]; return true; }           // il appuie sur un bouton
  if (s < 15.5f) { x = xa; sp = &IA_S_ACHAT[1]; return true; }        // il se penche, ramasse sa canette
  if (s < 28) { x = xa + (70 - xa) * (s - 16.5f) / 11.5f; sp = &IA_S_MARCHE[(int)(s * 3) % 4]; return true; }
  return false;
}

void s_distributeur(int humeur, bool debut, float t, float ecoule, float dt) {
  E_distributeur &e = etat_ecran<E_distributeur>(debut);
  (void)humeur; (void)ecoule; (void)dt;
  if (debut) ia_dis_fond(e);
  ia_reprendre(e.fond);
  const int x0 = IA_DX, y0 = IA_DY;
  const float u = t / IA_DIS_P, s = (u - floorf(u)) * IA_DIS_P;
  const float c0 = borne(1 - fabsf(s - 13.0f) / 1.3f, 0, 1), clac = c0 * sqrtf(c0);   // la canette tombe
  if (clac > 0) ia_halo(x0 + 9, y0 + 36, 3, 90, 120, 160, 0.5f * clac, 2.0f);
  tramer(8);
  for (int i = 0; i < 22; i++) {                                       // les etoiles
    const float k = e.el[i] * (0.6f + 0.4f * sinf(t * 0.7f + e.ep[i]));
    pointer(e.ey[i], e.ex[i], 150 * k, 160 * k, 200 * k);
  }
  for (int y = 0; y < 64; y++)                                         // le distributeur et le reste, nets
    for (int x = 0; x < 64; x++)
      if (e.m[y][x] & 1) peindre(y, x, e.net[y][x][0], e.net[y][x][1], e.net[y][x][2]);
  if (clac > 0)                                                        // la trappe s'eclaire
    for (int y = y0 + 30; y < y0 + 33; y++)
      for (int x = x0 + 3; x < x0 + 15; x++) ajouter(y, x, clac, 110, 140, 180);
  const float led = 0.5f + 0.5f * sinf(t * 1.1f);                      // un voyant rouge qui respire
  ia_rect(y0 + 20, y0 + 21, x0 + 8, x0 + 10, 90 * (1 - led) + 255 * led, 110 * (1 - led) + 70 * led, 140 * (1 - led) + 60 * led);
  // le chat (sa propre horloge, plus lente)
  const float uc = (t + 41) / IA_CHAT_P;
  float cx;
  const IaSprite *sp;
  bool miroir, assis;
  if (ia_chat((uc - floorf(uc)) * IA_CHAT_P, cx, sp, miroir, assis)) {
    const bool clin = fmodf(t * 0.17f, 1) < 0.03f;                     // il cligne des yeux, rarement
    const IaTeinte pal[3] = {{'k', 14, 14, 20, 1}, {'l', 92, 120, 164, 1}, {'y', clin ? 14.0f : 200.0f, clin ? 14.0f : 226.0f, clin ? 20.0f : 96.0f, 1}};
    const float cy = 51 - sp->h;
    ia_peindre(*sp, pal, 3, cx, cy, miroir);
    if (assis) {                                                       // la queue : un geste lent, puis le repos
      const float g = sinf(t * 0.55f) * 1.6f + sinf(t * 1.7f) * 0.5f;
      const int q = g < -0.2f ? 0 : g < 0.6f ? 1 : g < 1.2f ? 2 : 3;
      ia_peindre(IA_S_QUEUE[q], pal, 3, cx + 5, cy + 2);
    }
  }
  // le passant, en contre-jour devant la machine
  float px;
  const IaSprite *ps;
  if (ia_passant(s, px, ps)) {
    const float devant = borne(1 - fabsf(px + 3.5f - 29.5f) / 12, 0, 1), b = 0.35f + 0.65f * devant, f = 0.6f - 0.3f * devant;
    const IaTeinte pal[10] = {{'h', 16, 14, 18, 1}, {'H', 16, 14, 18, 1}, {'f', 170 * f, 130 * f, 108 * f, 1},
                              {'s', 40, 42, 52, 1}, {'c', 30, 32, 44, 1}, {'C', 110 * b, 150 * b, 200 * b, 1},
                              {'d', 18, 20, 28, 1}, {'p', 22, 22, 30, 1}, {'b', 10, 10, 14, 1}, {'m', 105, 84, 70, 1}};
    ia_peindre(*ps, pal, 10, px, 56 - 13);
  }
  // les papillons de nuit autour du bandeau : sombres devant la lumiere, clairs ailleurs
  for (int i = 0; i < 5; i++) {
    const float *M = e.mites[i];
    const float mx = x0 + 9 + 10.5f * sinf(t * (0.8f + M[0] * 0.15f) + M[1]) + 2.0f * sinf(t * 2.3f + M[2] * 3);
    const float my = y0 + 1 + 4.5f * sinf(t * (1.1f + M[3] * 0.12f) + M[2]) + 1.5f * cosf(t * 2.7f + M[0] * 2);
    const int yi = (int)floorf(my), xi = (int)floorf(mx);
    const int aile = sinf(t * 9 + M[1] * 5) > 0 ? 1 : -1;              // les ailes : un pixel d'un cote ou de l'autre
    for (int k = 0; k < 2; k++) {
      const int xx = xi + k * aile;
      if (yi < 0 || yi >= 64 || xx < 0 || xx >= 64) continue;
      const float poids = k ? 0.55f : 1.0f;
      const float *p = scene[yi][xx];
      if (fmaxf(p[0], fmaxf(p[1], p[2])) > 150) {
        const float d = k ? 1.1965f : 1.0f;                            // 1 / 0.55 ** 0.3
        peindre(yi, xx, 50 * d, 60 * d, 84 * d);
      } else pointer(yi, xx, 226 * poids, 232 * poids, 250 * poids);
    }
  }
}

// ===========================================================================
// 4. LA CABINE TELEPHONIQUE DANS LA NEIGE (_scene_cabine). La campagne sous la lune : une route en lacet vers un
// village, des poteaux et leurs fils, des sapins ; au bord, une cabine allumee ou quelqu'un telephone derriere la
// buee (il se retourne, l'essuie, regarde dehors) ; sa lumiere pose un rectangle trame sur la neige. Parfois une
// voiture s'eloigne vers le village, ses feux rouges qui rapetissent.

const float IA_CAB_P = 75.0f;
const int IA_CF = 12, IA_CC = 22, IA_CS = 27, IA_CB = 52;   // la cabine : x de la face, du coin, du flanc, y du pied
const float IA_CAB_R = 255, IA_CAB_G = 214, IA_CAB_B = 150;

struct E_cabine {
  uint8_t fond[64][64][3];               // la campagne, la lune, la lumiere de la cabine (avant la trame)
  uint8_t net[64][64][3];                // sapins, poteaux, fils, la cabine (sans ce qui bouge dedans)
  uint8_t m[64][64];
  uint8_t lumi[64][64];                  // pour les flocons
  float buee[18][14];                    // la buee de base sur les vitres (sans le frisson ni la trouee)
  IaFlocons neige;
};

// _ia_cab_route : un point de la route (u = 0 au bord droit, 1 au village) : x, y, largeur
static void ia_cab_route(float u, float &x, float &y, float &w) {
  static const float P[5][2] = {{70, 50}, {44, 45}, {34, 40}, {44, 37}, {51, 35.2f}};
  u = borne(u, 0, 1) * 4;
  const int i = min((int)floorf(u), 3);
  float f = u - i;
  f = f * f * (3 - 2 * f);
  x = P[i][0] * (1 - f) + P[i + 1][0] * f;
  y = P[i][1] * (1 - f) + P[i + 1][1] * f;
  w = 0.8f * (y - 34.5f);
}

static void ia_cnet(E_cabine &e, int y0, int y1, int x0, int x1, float r, float g, float b) {
  for (int y = max(y0, 0); y < min(y1, 64); y++)
    for (int x = max(x0, 0); x < min(x1, 64); x++) {
      e.net[y][x][0] = (uint8_t)(borne(r, 0, 255) + 0.5f);
      e.net[y][x][1] = (uint8_t)(borne(g, 0, 255) + 0.5f);
      e.net[y][x][2] = (uint8_t)(borne(b, 0, 255) + 0.5f);
      e.m[y][x] = 1;
    }
}

static void ia_cab_fond(E_cabine &e) {
  const IaC nuit = ia_niv(24, 36, 90, 2, 0.8f);
  for (int y = 0; y < 64; y++) {                                       // la nuit bleue
    const float k = powf(borne((y - 8) / 26.0f, 0, 1), 1.5f);
    for (int x = 0; x < 64; x++) peindre(y, x, nuit.r + 10 * k, nuit.g + 17 * k, nuit.b + 34 * k);
  }
  halo(46, 9, 5, 70, 84, 120, 0.8f);                                   // la lune, son halo, son croissant
  for (int y = 4; y < 15; y++)
    for (int x = 41; x < 52; x++)
      if (hypotf(x - 46.0f, y - 9.0f) < 2.8f) {
        if (hypotf(x - 47.4f, y - 8.2f) < 2.4f) peindre(y, x, 24, 32, 62);
        else peindre(y, x, 226, 232, 214);
      }
  float colline[64];
  for (int x = 0; x < 64; x++) {
    const float a = (x - 12) / 9.0f;
    colline[x] = 33.5f + 1.8f * sinf(x * 0.08f + 0.4f) + 1.2f * sinf(x * 0.21f + 2) - 2.5f * expf(-a * a);
  }
  const IaC loin = ia_niv(110, 130, 190, 3), crete = ia_niv(130, 150, 210, 4, 0.8f);
  for (int x = 0; x < 64; x++)
    for (int y = 0; y < 64; y++)
      if (y >= colline[x]) { const IaC c = y < colline[x] + 1 ? crete : loin; peindre(y, x, c.r, c.g, c.b); }
  static const int BOIS[5][2] = {{3, 6}, {6, 4}, {9, 7}, {58, 5}, {61, 7}};
  const IaC bois = ia_niv(20, 36, 50, 2);
  for (int i = 0; i < 5; i++) {                                        // des bois au loin, sur les cretes
    const float c = colline[BOIS[i][0]], bh = BOIS[i][1];
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++)
        if (y >= c - bh && y < c + 1 && fabsf(x - (float)BOIS[i][0]) <= (y - c + bh) * 0.35f) peindre(y, x, bois.r, bois.g, bois.b);
  }
  const IaC clair = ia_niv(110, 130, 190, 4), ombre = ia_niv(100, 120, 180, 3);
  ia_rect(37, 64, 0, 64, clair);                                       // la neige du champ, bleue de lune
  ia_rect(37, 40, 0, 64, (clair.r + ombre.r) / 2, (clair.g + ombre.g) / 2, (clair.b + ombre.b) / 2);
  static const float CONGERES[4][3] = {{44, 48, 9}, {57, 55, 7}, {40, 60, 6}, {31, 43, 5}};
  for (int i = 0; i < 4; i++)                                          // des congeres : leur ombre douce
    for (int x = 0; x < 64; x++) {
      const float cx = CONGERES[i][0], cy = CONGERES[i][1], dx = CONGERES[i][2];
      if (fabsf(x - cx) >= dx) continue;
      const float a = (x - cx) / dx, yc = cy - a * a * 1.5f;
      for (int y = 37; y < 64; y++)
        if (fabsf(y - yc) < 0.5f) peindre(y, x, ombre.r, ombre.g, ombre.b);
    }
  for (int d = 1; d < 8; d++)                                          // l'ombre de la cabine sous la lune
    ia_rect(IA_CB + d / 2, IA_CB + d / 2 + 1, max(0, IA_CF - d * 2), max(0, IA_CS - d * 2 - 3), ombre);
  const IaC route = ia_niv(80, 92, 130, 3), orn = ia_niv(60, 70, 104, 3, 0.75f);
  for (int passe = 0; passe < 2; passe++)                              // la route, puis ses deux ornieres
    for (int i = 0; i < 400; i++) {
      float x, y, w;
      ia_cab_route(i / 399.0f, x, y, w);
      const int yi = (int)roundf(y);
      if (passe == 0) {
        const int a = (int)roundf(x - w / 2), b = (int)roundf(x + w / 2);
        ia_rect(yi, yi + 1, max(a, 0), max(min(b + 1, 64), 0), route);
      } else if (w > 4)
        for (int k = 0; k < 2; k++) {
          const int xo = (int)roundf(x + (k ? 0.25f : -0.25f) * w);
          if (xo >= 0 && xo < 64) peindre(yi, xo, orn.r, orn.g, orn.b);
        }
    }
  ia_rect(33, 36, 46, 57, 16, 18, 30);                                 // le village : maisons, clocher, fenetres
  ia_rect(27, 33, 51, 52, 16, 18, 30);
  ia_rect(30, 33, 50, 53, 16, 18, 30);
  ia_rect(32, 34, 47, 50, 16, 18, 30);
  ia_rect(31, 33, 54, 56, 16, 18, 30);
  static const int FEN[5][2] = {{47, 34}, {50, 35}, {53, 34}, {55, 35}, {48, 33}};
  const IaC chaud = ia_niv(255, 190, 100, 6);
  for (int i = 0; i < 5; i++) {
    peindre(FEN[i][1], FEN[i][0], chaud.r, chaud.g, chaud.b);
    halo(FEN[i][0] + 0.5f, FEN[i][1] + 0.5f, 1.3f, 120, 80, 40, 0.35f);
  }
  // la lumiere de la cabine : le rectangle des vitres qui s'evase sur la neige, une lueur autour, au pied
  for (int y = 0; y < 64; y++)
    for (int x = 0; x < 64; x++) {
      float l = 0;
      if (y > IA_CB) {
        const float d = y - IA_CB, a = IA_CF - d * 0.3f, b = IA_CC + 1 + d * 0.55f, u = (x - a) / fmaxf(b - a, 1);
        const float q = (u - 0.5f) / 0.06f;
        const float bande = borne(fminf(u, 1 - u) * 8, 0, 1) * (1 - 0.55f * expf(-q * q));
        l += bande * expf(-d / 8.0f) * 1.05f;
      }
      l += expf(-powf(hypotf((x - 19) / 9.0f, (y - 36) / 13.0f), 1.4f)) * 0.35f;
      if (y > IA_CB) l += expf(-powf(hypotf((x - 19.5f) / 11.0f, (y - IA_CB - 1) / 2.5f), 1.5f)) * 0.45f;
      ajouter(y, x, l * 0.85f, IA_CAB_R, IA_CAB_G, IA_CAB_B);
      const float lf = expf(-powf(hypotf((x - 19) / 10.0f, (y - 38) / 15.0f), 1.4f)) * 1.2f + l * 0.5f;
      e.lumi[y][x] = (uint8_t)(borne(lf, 0, 1) * 255 + 0.5f);
    }
  ia_garder(e.fond);
  // le calque net : des sapins (la neige cote lune), les poteaux et leurs fils, la cabine
  static const float SAPINS[5][3] = {{2.5f, 55, 24}, {7.5f, 50, 15}, {31, 42, 9}, {35, 41.5f, 7}, {-1, 60, 30}};
  for (int i = 0; i < 5; i++) {
    const float sx = SAPINS[i][0], sb = SAPINS[i][1], sh = SAPINS[i][2];
    const int haut = (int)(sb - sh);
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++) {
        if (!(y >= sb - sh && y < sb && fabsf(x - sx) <= (y - (sb - sh)) * 0.33f + 0.5f)) continue;
        const int etage = (y - haut) % 4;
        if (etage == 1 && x <= sx + 0.5f) ia_cnet(e, y, y + 1, x, x + 1, 120, 140, 186);
        else if (etage == 2 && x < sx - 0.5f) ia_cnet(e, y, y + 1, x, x + 1, 70, 86, 126);
        else ia_cnet(e, y, y + 1, x, x + 1, 10, 22, 26);
      }
  }
  float sx[6], sy[6];
  static const float POTEAUX[5] = {0.08f, 0.3f, 0.52f, 0.72f, 0.9f};
  for (int i = 0; i < 5; i++) {                                        // les poteaux, le long de la route
    float x, y, w;
    ia_cab_route(POTEAUX[i], x, y, w);
    x = x + w * 0.6f + 1;
    y = y - w * 0.12f;
    const float h = 1.25f * (y - 34.5f) + 1;
    if (x < 63) {
      ia_cnet(e, (int)(y - h), (int)y + 1, (int)x, (int)x + 1, 26, 26, 34);
      if (h > 8) ia_cnet(e, (int)(y - h) + 1, (int)(y - h) + 2, (int)x - 2, (int)x + 3, 26, 26, 34);
    }
    sx[i] = x; sy[i] = y - h + 1;
  }
  sx[5] = IA_CS; sy[5] = 25;                                           // et le fil de la cabine
  for (int i = 0; i < 6; i++)                                          // ranges de gauche a droite
    for (int j = i + 1; j < 6; j++)
      if (sx[j] < sx[i]) { float a = sx[i]; sx[i] = sx[j]; sx[j] = a; a = sy[i]; sy[i] = sy[j]; sy[j] = a; }
  for (int i = 0; i < 5; i++) {                                        // les fils, qui pendent entre deux poteaux
    const float xa = sx[i], ya = sy[i], xb = sx[i + 1], yb = sy[i + 1];
    for (int x = (int)ceilf(xa); x <= (int)xb; x++) {
      const float f = (x - xa) / fmaxf(xb - xa, 1e-6f);
      const int y = (int)roundf(ya + (yb - ya) * f + 4 * f * (1 - f) * fminf(3.0f, (xb - xa) * 0.12f));
      if (y >= 0 && y < 64 && x >= 0 && x < 64 && !e.m[y][x]) ia_cnet(e, y, y + 1, x, x + 1, 30, 32, 44);
    }
  }
  ia_cnet(e, 20, IA_CB + 1, IA_CF, IA_CS + 1, 30, 34, 40);             // la cabine
  ia_cnet(e, 20, 21, IA_CF + 1, IA_CS, 200, 208, 230);                 // la neige sur le toit
  ia_cnet(e, 19, 20, IA_CF + 2, IA_CS - 1, 160, 170, 204);
  ia_cnet(e, 21, 23, IA_CF, IA_CS + 1, 44, 46, 52);
  ia_cnet(e, 23, 26, IA_CF + 1, IA_CC, 240, 200, 110);                 // le bandeau allume, son petit combine
  ia_cnet(e, 24, 25, IA_CF + 3, IA_CF + 8, 60, 50, 40);
  ia_cnet(e, 23, 24, IA_CF + 3, IA_CF + 4, 60, 50, 40);
  ia_cnet(e, 23, 24, IA_CF + 7, IA_CF + 8, 60, 50, 40);
  ia_cnet(e, 23, 26, IA_CC + 1, IA_CS, 170, 136, 80);
  for (int y = 0; y < 18; y++)                                         // la buee de base : laiteuse en bas, plus dense
    for (int x = 0; x < 14; x++) {                                     // la ou il souffle
      const float yy = 28 + y, xx = IA_CF + 1 + x, a = (xx - (IA_CF + 5)) / 4.0f, b = (yy - 36) / 3.0f;
      e.buee[y][x] = 0.2f + 0.45f * powf(borne((yy - 27) / 18.0f, 0, 1), 1.3f) + 0.18f * expf(-a * a - b * b);
    }
}

// _ia_cab_dedans : l'interieur (lumiere, telephone, la personne), la buee et sa trouee, puis les montants
static void ia_cab_dedans(const E_cabine &e, float t, float s) {
  const int y0 = 27, y1 = 45;
  for (int y = y0; y <= y1; y++) {                                     // le fond eclaire, le flanc de biais
    const float k = 0.7f - 0.016f * (y - y0);
    for (int x = IA_CF + 1; x < IA_CC; x++) peindre(y, x, IA_CAB_R * k, IA_CAB_G * k, IA_CAB_B * k);
    for (int x = IA_CC + 1; x < IA_CS; x++) peindre(y, x, IA_CAB_R * 0.42f, IA_CAB_G * 0.42f, IA_CAB_B * 0.42f);
  }
  ia_rect(y0, y0 + 1, IA_CF + 1, IA_CC, 255, 242, 214);                // la lampe du plafond
  ia_rect(31, 35, IA_CC - 2, IA_CC, 44, 40, 40);                       // le telephone, au mur de droite
  peindre(32, IA_CC - 2, 160, 150, 130);
  ia_rect(35, 40, IA_CC - 1, IA_CC, 34, 30, 30);                       // son fil
  const IaTeinte pal[8] = {{'h', 40, 30, 28, 1}, {'f', 214, 164, 124, 1}, {'r', 26, 26, 30, 1}, {'m', 200, 152, 118, 1},
                           {'a', 40, 48, 76, 1}, {'C', 120, 110, 120, 1}, {'c', 44, 54, 86, 1}, {'d', 30, 36, 60, 1}};
  if (s >= 14 && s < 40) {                                             // tourne vers la vitre ; il essuie la buee
    const int dx = (s > 27 && fmodf(s * 0.4f, 2) < 1) ? 1 : 0;
    ia_peindre(IA_S_TEL_F, pal, 8, IA_CF + 1 + dx, 33, false, IA_CF + 1, IA_CC, y0 + 1, y1 + 1);
    if (s >= 22 && s < 25.5f) {                                        // sa main, en rond sur la vitre
      const float w = (s - 22) * 5.0f;
      const int hx = (int)(IA_CF + 4.5f + 1.8f * cosf(w)), hy = (int)(37.5f + 1.2f * sinf(w));
      ia_rect(hy, hy + 2, hx, hx + 2, 200, 152, 118);
    }
  } else {                                                             // de profil ; il baisse la tete, s'appuie
    const bool baisse = fmodf(s * 0.21f, 1) < 0.3f;
    const int appui = (s >= 46 && s < 54) ? 1 : 0;
    ia_peindre(IA_S_TEL_P[baisse ? 1 : 0], pal, 8, IA_CF + 1 + appui, 33, false, IA_CF + 1, IA_CC, y0 + 1, y1 + 1);
  }
  // la buee : son frisson ; la trouee qui grandit sous la main (22-25 s) puis se referme (32 s)
  const float k = borne((s - 22) / 3.0f, 0, 1);
  float trou_k = 0;
  if (s >= 22) {
    const float age = s - 25.0f, refait = age > 0 ? borne(age / 32.0f, 0, 1) : 0.0f;
    trou_k = powf(1 - refait, 0.8f);
  }
  const float rx = 1.0f / (3.2f * k + 0.6f), ry = 1.0f / (2.6f * k + 0.6f);
  for (int y = 0; y < 18; y++)
    for (int x = 0; x < 14; x++) {
      const float yy = y0 + 1 + y, xx = IA_CF + 1 + x;
      float a = e.buee[y][x] * (0.9f + 0.1f * sinf(xx * 1.1f + yy * 0.5f + t * 0.15f));
      if (trou_k > 0) {
        const float trou = borne(1.6f - hypotf((xx - (IA_CF + 4.5f)) * rx, (yy - 37.5f) * ry), 0, 1);
        a *= 1 - trou * trou_k;
      }
      a = borne(a, 0, 0.85f);
      float *p = scene[(int)yy][(int)xx];
      p[0] += (200 - p[0]) * a; p[1] += (204 - p[1]) * a; p[2] += (206 - p[2]) * a;
    }
  ia_rect(y0, IA_CB + 1, IA_CF, IA_CF + 1, 30, 34, 40);                // les montants, la traverse, le bas plein
  ia_rect(y0, IA_CB + 1, IA_CC, IA_CC + 1, 44, 48, 56);
  ia_rect(y0, IA_CB + 1, IA_CS, IA_CS + 1, 22, 24, 30);
  ia_rect(31, 32, IA_CF, IA_CC, 40, 44, 52);
  ia_rect(31, 32, IA_CC, IA_CS, 32, 34, 40);
  ia_rect(y1 + 1, IA_CB + 1, IA_CF, IA_CS + 1, 40, 44, 54);
  ia_rect(y1 + 1, y1 + 2, IA_CF, IA_CS + 1, 64, 66, 74);
  ia_rect(y1 + 2, IA_CB, IA_CC + 1, IA_CS, 30, 32, 40);
  ia_rect(IA_CB, IA_CB + 1, IA_CF - 1, IA_CS + 2, 150, 160, 196);      // la neige au pied
}

void s_cabine(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cabine &e = etat_ecran<E_cabine>(debut);
  (void)humeur; (void)ecoule;
  if (debut) {
    ia_cab_fond(e);
    ia_semer_flocons(e.neige, 50, 36, 64);
  }
  ia_reprendre(e.fond);
  const float u = t / IA_CAB_P, s = (u - floorf(u)) * IA_CAB_P;
  bool voiture = false;
  float vx = 0, vy = 0, vw = 0, fin = 0;
  if (s >= 28 && s < 44) {                                             // une voiture s'en va vers le village
    const float a = (s - 28) / 16, uu = 1 - (1 - a) * (1 - a);         // elle ralentit en s'eloignant
    ia_cab_route(uu, vx, vy, vw);
    fin = fminf(1.0f, (1 - a) / 0.25f);                                // et s'efface dans les lumieres du village
    float hx, hy, hw;
    ia_cab_route(fminf(1.0f, uu + 0.12f), hx, hy, hw);
    ia_halo(hx, hy, 2.0f + vw * 0.25f, 255, 226, 170, 0.6f * (1 - a * 0.6f) * fin, 1.6f);
    ia_halo(vx, vy, 0.8f + vw * 0.2f, 220, 40, 30, 0.5f * (1 - a * 0.5f) * fin);
    voiture = true;
  }
  tramer(8);
  if (voiture) {                                                       // vue de derriere : une ombre, deux feux
    const float w = fmaxf(vw * 0.62f, 0.8f);
    if (w >= 2.5f) {
      const int h = max(1, (int)roundf(w * 0.35f)), xa = (int)roundf(vx - w / 2), xb = (int)roundf(vx + w / 2);
      ia_rect((int)vy - h, (int)vy + 1, xa, xb + 1, 14, 16, 26);
      const int c = max(1, (int)roundf(w * 0.3f));
      ia_rect((int)vy - h - c, (int)vy - h, xa + 1, xb, 20, 22, 34);
      pointer(vy - 1, xa, 255, 50, 40);
      pointer(vy - 1, xb, 255, 50, 40);
    } else {
      const float k = (0.4f + 0.6f * fin) * fin;
      pointer(vy, vx, 255 * k, 60 * k, 40 * k);
    }
  }
  for (int y = 0; y < 64; y++)                                         // devant elle : sapins, poteaux, la cabine
    for (int x = 0; x < 64; x++)
      if (e.m[y][x]) peindre(y, x, e.net[y][x][0], e.net[y][x][1], e.net[y][x][2]);
  ia_cab_dedans(e, t, s);
  ia_flocons(e.neige, 50, t, dt, e.lumi, IaC{255, 226, 176}, IaC{170, 184, 225});
}
