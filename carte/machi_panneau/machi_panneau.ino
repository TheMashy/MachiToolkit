// Le croquis du panneau LED de Machi Tool (Machi LED Wall), version 7.
// Un panneau 64x64 sur une Adafruit MatrixPortal S3, nourri par USB :
//   "MG" + 8 192 octets (RGB565, poids fort d'abord) + 2 octets de controle
//        (Fletcher-16, poids fort d'abord) = une image controlee,
//   "MF" + 8 192 octets = une image sans controle (Machi Tool avant la v1.90),
//   "MB" + 1 octet = la luminosite (0-255, jamais au-dessus de PLAFOND),
//   "MV"           = il repond "MACHI 7" (Machi Tool sait quel croquis il a),
//   "MS"           = il repond "STATS recues jetees" (les images abimees),
//   "MA" + 12 octets + 2 de controle = les reglages des ecrans de veille
//                    (gardes dans la carte : ils survivent a une coupure),
//   "MW"           = les ecrans de veille, tout de suite (Windows s'arrete),
//   "MO"           = au prochain silence, noir et pas d'ecran de veille
//                    (on a quitte Machi Tool : le panneau s'eteint avec lui).
//
// v2 : « ca tombe a 5 fps parfois ». La v1 redessinait les 4 096 pixels a
// chaque image : a 30 images/s la carte prenait du retard, et le PC attendait
// qu'elle suive. La v2 ne redessine que les pixels qui ont change.
//
// v3 : « j'ai des artefacts depuis le dernier flash ». Une image arrivee
// abimee (envoyee a moitie, decalee) etait dessinee, et ce qui ne changeait
// plus restait faux. Chaque image porte maintenant sa somme de controle :
// abimee, elle est jetee (et comptee). Et deux lignes sont redessinees
// d'office a chaque image : tout le panneau est refait en une seconde,
// quoi qu'il ait pu s'y glisser.
//
// v4 : « lorsque j'eteins le PC, le panneau ressemble a ca ». Eteint, le PC
// garde souvent l'USB alimente : la carte continue, avec la derniere image --
// ou, si elle redemarre, la mire, pour toujours. Maintenant, sans image
// depuis 5 s (PC eteint, Machi Tool ferme ou plante, « pilote le panneau »
// decoche), le panneau s'eteint de lui-meme. Au demarrage, la mire ne
// reste que ces 5 s.
//
// v5 : « desactiver la mire qui s'allume en permanence quand l'ordi est
// eteint ou quand Machi Tool n'est pas detecte ». Plus de mire au demarrage :
// la carte demarre noire et le reste jusqu'a la premiere image. (Sur l'USB
// d'un PC eteint, ses grands aplats lumineux pouvaient faire flancher
// l'alimentation : la carte redemarrait, remontrait la mire, et ainsi de
// suite.) Pour verifier le cablage et les couleurs, le bouton « Montrer la
// mire » de Machi Tool l'envoie toujours.
//
// v6 : « il y a toujours un probleme de stutter » -- et la page : 30 images/s,
// mais des centaines d'images abimees jetees par la carte. Chaque image jetee
// laisse la precedente a l'ecran : c'est la saccade. La v5 lisait chaque image
// octet par octet (readBytes) : 8 192 lectures, chacune a travers la file de
// l'USB. Quand le dessin prenait du temps (les ecrans plein panneau changent
// tous les pixels), la reserve de 16 Ko debordait, et l'USB de l'ESP32 jetait
// ce qui ne tenait plus : une image amputee. La v6 lit par blocs, avec 64 Ko
// de reserve (huit images), et n'abandonne une image qu'apres 200 ms sans
// rien recevoir.
//
// v7 : « c'est possible que tu laisses les screen savers meme a l'arret du
// PC ? » -- « keep only atmospheric effects ». Le PC eteint (ou en veille),
// l'USB reste alimente : la carte dessine elle-meme les ambiances de Machi
// Tool -- l'aurore, l'aurore sur le lac, le coucher de soleil, les lucioles,
// la nebuleuse, les etoiles filantes, les meduses, les lanternes, le ciel qui
// tourne, la neige --, chacune son tour, en fondu. Machi Tool lui dit
// lesquelles, combien de temps chacune, a quelle luminosite, et quand
// s'arreter ("MA") ; sans ses reglages, elle reste noire comme la v6.
// L'alimentation d'un PC eteint est maigre : des ciels sombres, une
// luminosite a part (basse), et une carte qui a redemarre faute de tension
// (ESP_RST_BROWNOUT) reste noire jusqu'au retour du PC -- plus jamais la
// boucle de la v5.
#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>
#include <Preferences.h>
#include <esp_system.h>
#include <math.h>

// Les broches HUB75 de la MatrixPortal S3 (celles d'Adafruit)
HUB75_I2S_CFG::i2s_pins PINS = {
  42, 41, 40, 38, 39, 37,   // R1 G1 B1 R2 G2 B2
  45, 36, 48, 35, 21,       // A B C D E
  47, 14, 2                 // LAT OE CLK
};

// Option A (USB seul) : 96 sur un port USB-C, 57 sur un port USB-A.
// Option B (alimentation 5 V separee) : 255.
const uint8_t PLAFOND = 96;

const int W = 64, H = 64, N = W * H * 2;
MatrixPanel_I2S_DMA *panneau;
uint8_t image[N];
uint8_t affichee[N];           // ce que le panneau montre deja
bool tout_redessiner = true;
uint32_t recues = 0, jetees = 0;
const unsigned long SILENCE_MS = 5000;   // sans image depuis 5 s : noir (ou les ecrans de veille)
const unsigned long ATTENTE_MS = 200;    // une image sans un octet depuis 200 ms : abandonnee
unsigned long derniere_ms = 0;

// Ce que montre le panneau : les images du PC, du noir, ou ses ecrans de veille
enum Etat { NOIR, PC, VEILLE };
Etat etat = NOIR;
bool veille_permise = true;    // non apres « MO », apres l'arret programme, apres une baisse de tension
uint8_t lum_pc = 40;           // la luminosite que le PC a demandee

// Les reglages des ecrans de veille ("MA"), gardes dans la memoire de la carte
struct Reglages {
  uint8_t actif = 0, lum = 32;
  uint16_t masque = 0x3FF, duree_s = 120, arret_min = 0;
  uint8_t rouge = 100, vert = 100, bleu = 100;
};
Reglages reglages;
uint8_t reglages_bruts[12];    // tels que Machi Tool les a envoyes : ce que la carte garde
const int NB_ECRANS = 10;      // l'ordre des ambiances de Machi Tool (ECRANS_AMBIANCES)
Preferences memoire;

void eteindre() {
  panneau->clearScreen();
  memset(affichee, 0, N);      // ce que le panneau montre : du noir
  etat = NOIR;
}

// Fletcher-16, comme Machi Tool la calcule (fletcher16 dans machi_tool.py)
uint16_t fletcher16(const uint8_t *d, int n) {
  uint16_t a = 0, b = 0;
  for (int i = 0; i < n; i++) {
    a = (a + d[i]) % 255;
    b = (b + a) % 255;
  }
  return (b << 8) | a;
}

// Lit n octets par blocs -- Serial.read(tampon, n) prend tout ce qui est
// arrive d'un coup, quand readBytes les prenait un par un. Abandonne apres
// ATTENTE_MS sans rien recevoir. Rend le nombre d'octets lus.
size_t lire(uint8_t *d, size_t n) {
  size_t fait = 0;
  unsigned long vu = millis();
  while (fait < n) {
    long k = (long)Serial.read(d + fait, n - fait);
    if (k > 0 && (size_t)k <= n - fait) {
      fait += k;
      vu = millis();
    } else if (millis() - vu > ATTENTE_MS) {
      break;
    } else {
      yield();
    }
  }
  return fait;
}

void dessiner() {
  // deux lignes d'office a chaque image : 32 images, et tout le panneau est refait
  static uint32_t passages = 0;
  const int bande = passages++ % (H / 2);
  for (int p = 0, i = 0; p < W * H; p++, i += 2) {
    const bool force = tout_redessiner || (p / W) / 2 == bande;
    if (!force && image[i] == affichee[i] && image[i + 1] == affichee[i + 1]) continue;
    panneau->drawPixel(p % W, p / W, (uint16_t)(image[i] << 8 | image[i + 1]));
  }
  memcpy(affichee, image, N);
  tout_redessiner = false;
}

// ---------------------------------------------------------------------------
// LES ECRANS DE VEILLE. Chacun peint une scene en flottants (0-255, sRGB),
// comme ses jumeaux en numpy dans machi_tool.py ; puis la meme conversion
// que Machi Tool (rgb565) : la balance du panneau, appliquee a la lumiere, et
// la clarte CIE que la bibliotheque attend.

float scene[64][64][3];
uint8_t lut[3][256];
const float PI2 = 6.2831853f;

void preparer_lut() {
  const float balance[3] = {reglages.rouge / 100.0f, reglages.vert / 100.0f, reglages.bleu / 100.0f};
  for (int c = 0; c < 3; c++) {
    for (int v = 0; v < 256; v++) {
      const float x = v / 255.0f;
      const float lin = (x <= 0.04045f ? x / 12.92f : powf((x + 0.055f) / 1.055f, 2.4f)) * balance[c];
      const float clarte = lin > 0.008856f ? 116.0f * cbrtf(lin) - 16.0f : 903.3f * lin;
      const float o = roundf(clarte * 2.55f);
      lut[c][v] = (uint8_t)(o < 0 ? 0 : o > 255 ? 255 : o);
    }
  }
}

// le hasard (xorshift) : rien a garder, rien a attendre
uint32_t graine = 0x2545F491u;
uint32_t aleatoire() {
  graine ^= graine << 13;
  graine ^= graine >> 17;
  graine ^= graine << 5;
  return graine;
}
float hasard(float a, float b) { return a + (b - a) * (aleatoire() >> 8) * (1.0f / 16777216.0f); }

inline float borne(float v, float a, float b) { return v < a ? a : v > b ? b : v; }

void peindre(int y, int x, float r, float v, float b) {
  scene[y][x][0] = r;
  scene[y][x][1] = v;
  scene[y][x][2] = b;
}

void ajouter(int y, int x, float k, float r, float v, float b) {
  scene[y][x][0] += k * r;
  scene[y][x][1] += k * v;
  scene[y][x][2] += k * b;
}

// un point allume (le plus clair l'emporte) ; hors du panneau, ignore
void pointer(float yf, float xf, float r, float v, float b) {
  const int y = (int)yf, x = (int)xf;
  if (y < 0 || y >= H || x < 0 || x >= W) return;
  float *p = scene[y][x];
  if (r > p[0]) p[0] = r;
  if (v > p[1]) p[1] = v;
  if (b > p[2]) p[2] = b;
}

// un ciel en degrade : (r0 + y*dr, v0 + y*dv, b0 + y*db)
void degrade(float r0, float dr, float v0, float dv, float b0, float db) {
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) peindre(y, x, r0 + y * dr, v0 + y * dv, b0 + y * db);
}

// des etoiles fixes qui scintillent, au-dessus de la ligne `bas`
struct Ciel { int n; uint8_t y[70], x[70]; float p[70], l[70]; };
Ciel ciel;
void semer_ciel(int n, int bas) {
  ciel.n = n;
  for (int i = 0; i < n; i++) {
    ciel.y[i] = aleatoire() % bas;
    ciel.x[i] = aleatoire() % W;
    ciel.p[i] = hasard(0, PI2);
    ciel.l[i] = hasard(0.35f, 1.0f);
  }
}
void etoiles_du_ciel(float t) {
  for (int i = 0; i < ciel.n; i++) {
    const float k = ciel.l[i] * (0.55f + 0.45f * sinf(t * 2.1f + ciel.p[i]));
    pointer(ciel.y[i], ciel.x[i], 205 * k, 210 * k, 235 * k);
  }
}

// un champ doux (0 a 1) qui se raccorde sur ses bords : du hasard, lisse ; le
// brouillon est la scene elle-meme, qu'on repeint de toute facon
uint16_t champs[4][64 * 64];
void brume(uint16_t *sortie, int flou) {
  float *a = &scene[0][0][0], *b = a + 4096;
  for (int i = 0; i < 4096; i++) a[i] = hasard(0, 1);
  for (int k = 0; k < flou; k++) {
    for (int y = 0; y < 64; y++)
      for (int x = 0; x < 64; x++)
        b[y * 64 + x] = (a[y * 64 + x] + a[((y + 63) & 63) * 64 + x] + a[((y + 1) & 63) * 64 + x]
                         + a[y * 64 + ((x + 63) & 63)] + a[y * 64 + ((x + 1) & 63)]) / 5.0f;
    float *c = a; a = b; b = c;
  }
  float mn = a[0], mx = a[0];
  for (int i = 0; i < 4096; i++) { mn = fminf(mn, a[i]); mx = fmaxf(mx, a[i]); }
  for (int i = 0; i < 4096; i++) sortie[i] = (uint16_t)(65535.0f * (a[i] - mn) / fmaxf(1e-9f, mx - mn));
}
inline float champ(const uint16_t *c, int x, int y) { return c[(y & 63) * 64 + (x & 63)] * (1.0f / 65535.0f); }
// le champ vu par une fenetre placee en (ox, oy), pas forcement entiere : ca glisse sans a-coups
inline float fenetre(const uint16_t *c, float ox, float oy, int x, int y) {
  const int x0 = (int)floorf(ox), y0 = (int)floorf(oy);
  const float fx = ox - x0, fy = oy - y0;
  const float a = champ(c, x + x0, y + y0), b = champ(c, x + x0 + 1, y + y0);
  const float d = champ(c, x + x0, y + y0 + 1), e = champ(c, x + x0 + 1, y + y0 + 1);
  return (a * (1 - fx) + b * fx) * (1 - fy) + (d * (1 - fx) + e * fx) * fy;
}

// les rideaux d'une aurore : chacun une bande qui ondule, plus vive a son bord bas
// (l'aurore seule et celle du lac n'ondulent pas tout a fait pareil, comme dans machi_tool.py)
void rideaux(float t, const float (*r)[5], int n, float force, bool lac) {
  const float a1 = lac ? 5 : 7, a2 = lac ? 3 : 4, v1 = lac ? 0.45f : 0.5f, v2 = lac ? 0.7f : 0.8f;
  const float w1 = lac ? 0.09f : 0.08f, w2 = lac ? 0.23f : 0.21f, pente = lac ? 8.0f : 9.0f, bord = lac ? 2.2f : 2.5f;
  for (int k = 0; k < n; k++) {
    const float decal = r[k][0], haut = r[k][4];
    for (int x = 0; x < W; x++) {
      const float base = 30 + haut + a1 * sinf(x * w1 + t * v1 + decal) + a2 * sinf(x * w2 - t * v2 + decal);
      const float rideau = lac
          ? 0.5f + 0.5f * sinf(x * 0.55f + t * 1.5f + sinf(x * 0.12f + t * 0.8f + decal) * 3)
          : 0.55f + 0.45f * sinf(x * 0.5f + t * 1.7f + sinf(x * 0.1f + t + decal) * 3);
      for (int y = 0; y < H; y++) {
        const float profil = y <= base ? expf(-(base - y) / pente) : expf(-((y - base) / bord) * ((y - base) / bord));
        ajouter(y, x, profil * rideau * force, r[k][1], r[k][2], r[k][3]);
      }
    }
  }
}

// --- l'aurore boreale ---
struct { uint8_t y[45], x[45]; float p[45]; } aur;
void ecran_aurore(bool debut, float t, float) {
  if (debut)
    for (int i = 0; i < 45; i++) { aur.y[i] = aleatoire() % 64; aur.x[i] = aleatoire() % 64; aur.p[i] = hasard(0, PI2); }
  degrade(2, 0, 4, 0, 14, 0);
  for (int i = 0; i < 45; i++) {
    const float k = 0.5f + 0.5f * sinf(t * 2 + aur.p[i]);
    peindre(aur.y[i], aur.x[i], 150 * k, 150 * k, 170 * k);
  }
  static const float r[2][5] = {{0.0f, 60, 255, 140, 0.0f}, {2.1f, 150, 70, 255, -9.0f}};
  rideaux(t, r, 2, 0.9f, false);
}

// --- l'aurore sur le lac ---
void ecran_aurore_lac(bool debut, float t, float) {
  if (debut) semer_ciel(40, 30);
  const int horizon = 46;
  degrade(2, 0.1f, 4, 0.22f, 14, 0.4f);
  etoiles_du_ciel(t);
  static const float r[3][5] = {{0.0f, 60, 255, 140, 0.0f}, {2.4f, 140, 80, 255, -8.0f}, {4.1f, 40, 190, 255, -14.0f}};
  rideaux(t, r, 3, 0.8f, true);
  for (int x = 0; x < W; x++) {
    const float crete = 38 + 4 * sinf(x * 0.12f + 0.5f) + 2.5f * sinf(x * 0.29f + 2.0f) + 1.2f * sinf(x * 0.71f);
    for (int y = 0; y < horizon; y++)
      if (y >= crete) peindre(y, x, 3, 5, 10);
  }
  for (int y = horizon; y < H; y++) {   // le lac : le ciel a l'envers, qui ondule
    const int src = 2 * horizon - 1 - y;
    const int decal = (int)roundf(sinf(y * 0.9f + t * 2.0f) * (0.4f + (y - horizon) * 0.06f));
    for (int x = 0; x < W; x++) {
      const float *s = scene[src][((x - decal) % 64 + 64) % 64];
      const float k = 0.42f * (0.85f + 0.15f * sinf(x * 0.5f + y * 1.3f + t * 3));
      peindre(y, x, s[0] * k, s[1] * k, s[2] * k);
    }
  }
}

// --- le coucher de soleil sur la mer ---
void ecran_coucher(bool, float t, float) {
  const int horizon = 40;
  const float sy = 21 + fminf(t, 60) * 0.3f;            // il descend
  const float visible = borne((horizon - (sy - 8)) / 16, 0, 1);
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      const float k = borne(y / (float)horizon, 0, 1);
      float r, v, b;
      if (k < 0.55f) { const float q = k / 0.55f; r = 30 + 135 * q; v = 16 + 39 * q; b = 62 + 43 * q; }
      else { const float q = (k - 0.55f) / 0.45f; r = 165 + 90 * q; v = 55 + 95 * q; b = 105 - 45 * q; }
      const float d = hypotf(x - 32.0f, y - sy);
      const float halo = borne(1 - d / 24, 0, 1);
      r += halo * halo * 90; v += halo * halo * 55; b += halo * halo * 10;
      if (d <= 8 && y < horizon) { r = 255; v = borne(235 - (y - sy + 8) * 5, 0, 255); b = borne(130 - (y - sy + 8) * 6, 0, 255); }
      if (y >= horizon) {
        const float p = (y - horizon) / (float)(H - horizon);
        r = 70 * (1 - p * 0.65f); v = 32 * (1 - p * 0.65f); b = 72 * (1 - p * 0.65f);
        const float largeur = 2.5f + (y - horizon) * 0.45f;
        const float ondes = 0.5f + 0.5f * sinf(y * 2.1f + t * 3 + sinf(x * 0.7f + t) * 2);
        const float traits = expf(-((x - 32) / largeur) * ((x - 32) / largeur)) * ondes * ondes * visible;
        const float vagues = (0.5f + 0.5f * sinf(x * 0.4f + y * 1.9f - t * 1.4f)) * 0.12f;
        r += traits * 255 + vagues * 255; v += traits * 170 + vagues * 120; b += traits * 80 + vagues * 120;
      }
      peindre(y, x, fminf(r, 255), fminf(v, 255), fminf(b, 255));
    }
  }
  for (int i = 0; i < 2; i++) {                          // deux oiseaux au loin
    const float bx = fmodf(8 + i * 17 + t * (2.5f + i), 80) - 8;
    const float by = 11 + i * 6 + sinf(t * 0.7f + i) * 1.5f;
    const int aile = (int)(t * 3 + i) % 2;
    pointer(by - aile, bx - 1, 40, 20, 40);
    pointer(by, bx, 40, 20, 40);
    pointer(by - aile, bx + 1, 40, 20, 40);
  }
}

// --- les lucioles ---
struct { float x[24], y[24], p[24][4], w[24], b[24], v[24]; } luc;
void ecran_lucioles(bool debut, float t, float) {
  if (debut) {
    for (int i = 0; i < 24; i++) {
      luc.x[i] = hasard(4, 60); luc.y[i] = hasard(14, 54);
      for (int k = 0; k < 4; k++) luc.p[i][k] = hasard(0, PI2);
      luc.w[i] = hasard(0.6f, 1.4f); luc.b[i] = hasard(0, PI2); luc.v[i] = hasard(0.7f, 1.6f);
    }
    semer_ciel(25, 18);
  }
  degrade(6, 0.12f, 12, 0.28f, 26, 0.12f);              // un ciel de lune, vert-bleu
  etoiles_du_ciel(t);
  static const float sapins[4][3] = {{4, 22, 10}, {14, 36, 7}, {53, 18, 11}, {62, 32, 8}};
  for (int s = 0; s < 4; s++)
    for (int y = (int)sapins[s][1]; y < H; y++)
      for (int x = 0; x < W; x++)
        if (fabsf(x - sapins[s][0]) <= (y - sapins[s][1]) * sapins[s][2] / (64 - sapins[s][1]) + 0.5f) peindre(y, x, 2, 6, 5);
  for (int x = 0; x < W; x++) {                           // l'herbe
    const float herbe = 57 + 2 * sinf(x * 1.7f) + sinf(x * 0.6f + t * 1.2f);
    for (int y = 0; y < H; y++)
      if (y >= herbe) peindre(y, x, 3, 10, 6);
  }
  static float lueur[64][64];
  memset(lueur, 0, sizeof lueur);
  float lx[24], ly[24], li[24];
  for (int i = 0; i < 24; i++) {
    lx[i] = luc.x[i] + 6 * sinf(t * 0.31f * luc.w[i] + luc.p[i][0]) + 3 * sinf(t * 0.73f * luc.w[i] + luc.p[i][1]);
    ly[i] = luc.y[i] + 4 * sinf(t * 0.27f * luc.w[i] + luc.p[i][2]) + 2 * sinf(t * 0.61f * luc.w[i] + luc.p[i][3]);
    const float s = borne(sinf(t * luc.v[i] + luc.b[i]), 0, 1);
    li[i] = s * s * s;
    if (li[i] <= 0.02f) continue;
    for (int y = (int)ly[i] - 8; y <= (int)ly[i] + 8; y++)
      for (int x = (int)lx[i] - 8; x <= (int)lx[i] + 8; x++)
        if (y >= 0 && y < H && x >= 0 && x < W)
          lueur[y][x] += li[i] * expf(-((x - lx[i]) * (x - lx[i]) + (y - ly[i]) * (y - ly[i])) / 6.0f);
  }
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) ajouter(y, x, fminf(lueur[y][x], 1.4f), 170, 235, 70);
  for (int i = 0; i < 24; i++) pointer(ly[i], lx[i], li[i] * 255, li[i] * 255, li[i] * 190);
}

// --- la nebuleuse ---
struct { uint8_t x[3], y[3]; float p[3]; } phares;
void ecran_nebuleuse(bool debut, float t, float) {
  if (debut) {
    brume(champs[0], 30); brume(champs[1], 18); brume(champs[2], 40); brume(champs[3], 60);
    semer_ciel(55, 64);
    for (int i = 0; i < 3; i++) { phares.x[i] = 6 + aleatoire() % 52; phares.y[i] = 6 + aleatoire() % 52; phares.p[i] = hasard(0, 6); }
  }
  const float respire = 0.85f + 0.15f * sinf(t * 0.4f);
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      const float a = fenetre(champs[0], 30 + t * 0.9f, 20 + t * 0.4f, x, y);
      const float b = fenetre(champs[1], 70 - t * 0.6f, 50 + t * 0.7f, x, y);
      const float c = fenetre(champs[2], 10 + t * 0.3f, 90 - t * 0.5f, x, y);
      const float vide = borne((fenetre(champs[3], 50 + t * 0.2f, 40, x, y) - 0.25f) * 2.2f, 0, 1) * respire;
      const float va = a * a * a, vb = b * b * b * b, vc = c * c * sqrtf(c);
      peindre(y, x, fminf(255, (va * 150 + vb * 30 + vc * 240) * vide), fminf(255, (va * 50 + vb * 170 + vc * 80) * vide),
              fminf(255, (va * 210 + vb * 200 + vc * 150) * vide));
    }
  }
  etoiles_du_ciel(t);
  static const int8_t croix[8][2] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}, {2, 0}, {-2, 0}, {0, 2}, {0, -2}};
  for (int i = 0; i < 3; i++) {                           // trois etoiles plus vives, et leur croix
    const float f = 0.7f + 0.3f * sinf(t * 1.3f + phares.p[i]);
    peindre(phares.y[i], phares.x[i], 255, 255, 255);
    for (int k = 0; k < 8; k++) {
      const float g = (k < 4 ? 0.55f : 0.25f) * f;
      pointer(phares.y[i] + croix[k][1], phares.x[i] + croix[k][0], 220 * g, 225 * g, 255 * g);
    }
  }
}

// --- les etoiles filantes ---
struct Filante { float x, y, vx, vy, age, vie; };
struct { Filante f[16]; int n; float suivante; } fil;
void ecran_filantes(bool debut, float t, float dt) {
  if (debut) { brume(champs[0], 3); semer_ciel(70, 50); fil.n = 0; fil.suivante = 0.5f; }
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      const float q = (x - y * 0.8f - 6) / 13;
      const float bande = expf(-q * q) * (0.35f + 0.65f * champ(champs[0], x, y));   // la voie lactee
      peindre(y, x, 3 + y * 0.08f + bande * 50, 5 + y * 0.12f + bande * 44, 18 + y * 0.33f + bande * 66);
    }
  etoiles_du_ciel(t);
  if (t >= fil.suivante && fil.n < 16) {
    fil.suivante = t + hasard(0.6f, 1.6f);
    fil.f[fil.n++] = {hasard(20, 75), hasard(-4, 22), -hasard(55, 85), hasard(22, 38), 0.0f, hasard(0.5f, 0.9f)};
  }
  int garde = 0;
  for (int i = 0; i < fil.n; i++) {
    Filante &f = fil.f[i];
    f.x += f.vx * dt; f.y += f.vy * dt; f.age += dt;
    if (f.age >= f.vie) continue;
    fil.f[garde++] = f;
    const float vie = 1 - f.age / f.vie;
    for (int k = 0; k < 14; k++) {
      const float q = powf(1 - k / 14.0f, 1.6f) * vie;
      pointer(f.y - f.vy * k * 0.007f, f.x - f.vx * k * 0.007f, 255 * q, 245 * q, 225 * q);
    }
  }
  fil.n = garde;
  for (int x = 0; x < W; x++) {                           // la colline
    const float colline = 53 + 3 * sinf(x * 0.08f + 1) + 1.5f * sinf(x * 0.25f);
    for (int y = 0; y < H; y++)
      if (y >= colline) peindre(y, x, 4, 6, 11);
  }
  for (int y = 47; y < 53; y++)                           // la cabane, son toit, sa fenetre allumee
    for (int x = 44; x < 51; x++) peindre(y, x, 6, 8, 12);
  for (int i = 0; i < 4; i++)
    for (int x = 43 + i; x < 52 - i; x++) peindre(46 - i, x, 6, 8, 12);
  const float f = 0.85f + 0.15f * sinf(t * 3.1f);
  for (int y = 49; y < 51; y++)
    for (int x = 46; x < 48; x++) peindre(y, x, 255 * f, 185 * f, 90 * f);
}

// --- les meduses ---
struct Meduse { float x, y, p, r, v, b; };
struct { Meduse m[3]; float nx[40], ny[40], nv[40]; } med;
void ecran_meduses(bool debut, float t, float dt) {
  static const float couleurs[3][3] = {{255, 120, 200}, {90, 220, 255}, {190, 140, 255}};
  if (debut) {
    for (int i = 0; i < 3; i++)
      med.m[i] = {hasard(10, 54), hasard(16, 66), hasard(0, PI2), couleurs[i][0], couleurs[i][1], couleurs[i][2]};
    for (int i = 0; i < 40; i++) { med.nx[i] = hasard(0, 64); med.ny[i] = hasard(0, 64); med.nv[i] = hasard(0.6f, 2.5f); }
  }
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      const float s = 0.5f + 0.5f * sinf(x * 0.22f + y * 0.1f + t * 0.35f);
      const float s2 = s * s, rayon = s2 * s2 * s2 * expf(-y / 28.0f);
      peindre(y, x, rayon * 25, 8 + (64 - y) * 0.5f + rayon * 70, 20 + (64 - y) * 0.85f + rayon * 90);
    }
  for (int i = 0; i < 40; i++) {                          // la neige marine, qui descend
    med.ny[i] = fmodf(med.ny[i] + med.nv[i] * dt, 64);
    pointer(med.ny[i], fmodf(fmodf(med.nx[i] + sinf(t * 0.5f + med.ny[i] * 0.2f), 64) + 64, 64), 40, 70, 90);
  }
  for (int i = 0; i < 3; i++) {
    Meduse &m = med.m[i];
    const float cycle = t * 0.9f + m.p, serre = 0.5f + 0.5f * sinf(cycle);
    m.y -= dt * (2.0f + 5.0f * fmaxf(0.0f, cosf(cycle)));  // elle monte en se serrant
    m.x += sinf(t * 0.3f + m.p) * dt * 1.5f;
    if (m.y < -14) { m.y = hasard(70, 80); m.x = hasard(10, 54); }
    const float w = 6 + 1.8f * (1 - serre), h = 3.5f + 1.2f * serre;
    for (int y = (int)(m.y - 4 * h) - 1; y <= (int)(m.y + 2); y++)
      for (int x = (int)(m.x - 4 * w) - 1; x <= (int)(m.x + 4 * w) + 1; x++) {
        if (y < 0 || y >= H || x < 0 || x >= W || y > m.y + 2) continue;
        const float cloche = ((x - m.x) / w) * ((x - m.x) / w) + ((y - m.y) / h) * ((y - m.y) / h);
        const bool dedans = cloche <= 1 && y <= m.y + 1;
        const float k = expf(-fmaxf(cloche - 1, 0) * 2.5f) * 0.25f + (dedans ? 0.35f : 0) + (dedans && cloche > 0.55f ? 0.45f : 0);
        ajouter(y, x, k, m.r, m.v, m.b);
      }
    for (int k = 0; k < 4; k++) {                         // les tentacules
      const float ecart = k == 0 ? -4.0f : k == 1 ? -1.5f : k == 2 ? 1.5f : 4.0f;
      for (int ys = (int)m.y + 1; ys < (int)m.y + 13; ys++) {
        const float xs = m.x + ecart * (0.75f + 0.25f * serre) + sinf(ys * 0.45f - t * 2.5f + k) * 1.3f;
        const float q = (1 - (ys - m.y) / 14) * 0.55f;
        pointer(ys, xs, m.r * q, m.v * q, m.b * q);
      }
    }
  }
}

// --- les lanternes celestes ---
struct { float x[16], y[16], d[16], p[16]; } lan;
void ecran_lanternes(bool debut, float t, float dt) {
  if (debut) {
    for (int i = 0; i < 16; i++) { lan.x[i] = hasard(2, 62); lan.y[i] = hasard(-4, 56); lan.d[i] = hasard(0.3f, 1.0f); lan.p[i] = hasard(0, PI2); }
    semer_ciel(35, 30);
  }
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      const float k = y / 52.0f;
      peindre(y, x, 8 * (1 - k) + 60 * k, 10 * (1 - k) + 30 * k, 36 * (1 - k) + 70 * k);
    }
  etoiles_du_ciel(t);
  static float lueur[64][64];
  memset(lueur, 0, sizeof lueur);
  float f[16];
  for (int i = 0; i < 16; i++) {
    lan.y[i] -= (2.0f + 4.0f * lan.d[i]) * dt;
    lan.x[i] += sinf(t * 0.5f + lan.p[i]) * 0.6f * dt;
    if (lan.y[i] < -5) { lan.y[i] = 55; lan.x[i] = hasard(2, 62); }
    f[i] = lan.d[i] * (0.8f + 0.2f * sinf(t * 6 + lan.p[i] * 3));
    const float etale = 1.5f + 3 * lan.d[i];
    for (int y = (int)lan.y[i] - 8; y <= (int)lan.y[i] + 8; y++)
      for (int x = (int)lan.x[i] - 8; x <= (int)lan.x[i] + 8; x++)
        if (y >= 0 && y < H && x >= 0 && x < W)
          lueur[y][x] += f[i] * expf(-((x - lan.x[i]) * (x - lan.x[i]) + (y - lan.y[i]) * (y - lan.y[i])) / etale);
  }
  for (int x = 0; x < W; x++) {
    float reflet = 0;                                     // chaque lanterne, en trait tremblant sur l'eau
    for (int y = 0; y < H; y++) reflet += lueur[y][x];
    reflet *= 0.25f;
    const float colline = 52 + 2 * sinf(x * 0.1f) + sinf(x * 0.3f + 1);
    for (int y = 0; y < H; y++) {
      ajouter(y, x, fminf(lueur[y][x], 1.3f) * 0.6f, 255, 120, 40);
      if (y >= colline) peindre(y, x, 10, 8, 22);         // les collines
      if (y >= 57) {
        const float k = reflet * (0.5f + 0.5f * sinf(y * 2.3f + t * 3));
        peindre(y, x, 12 + k * 255, 10 + k * 140, 30 + k * 60);
      }
    }
  }
  for (int i = 0; i < 16; i++) {
    const float x = lan.x[i], y = lan.y[i], c = f[i];
    if (lan.d[i] > 0.65f) {
      pointer(y - 1, x, 255 * c, 150 * c, 50 * c); pointer(y - 1, x + 1, 255 * c, 150 * c, 50 * c);
      pointer(y, x, 255 * c, 150 * c, 50 * c); pointer(y, x + 1, 255 * c, 150 * c, 50 * c);
      pointer(y + 1, x, 255 * c, 225 * c, 130 * c); pointer(y + 1, x + 1, 255 * c, 225 * c, 130 * c);
    } else {
      pointer(y, x, 255 * c, 150 * c, 50 * c);
    }
  }
}

// --- le ciel qui tourne autour de l'etoile polaire, en pose longue ---
uint16_t trace[64][64][3];                                // les sillages, x256
struct { float r[95], a[95], l[95]; uint8_t teinte[95]; } sil;
void sillages_poser(float t) {
  static const float teintes[3][3] = {{215, 220, 255}, {255, 200, 150}, {160, 190, 255}};
  for (int i = 0; i < 95; i++) {
    const float a = sil.a[i] + 0.12f * t;
    const int x = (int)(50 + sil.r[i] * cosf(a)), y = (int)(8 + sil.r[i] * sinf(a) * 0.9f);
    if (y < 0 || y >= H || x < 0 || x >= W) continue;
    for (int c = 0; c < 3; c++) {
      const uint16_t v = (uint16_t)(sil.l[i] * teintes[sil.teinte[i]][c] * 0.9f * 256);
      if (v > trace[y][x][c]) trace[y][x][c] = v;
    }
  }
}
void sillages_passer(float dt) {
  const float f = expf(-dt * 0.25f);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++)
      for (int c = 0; c < 3; c++) trace[y][x][c] = (uint16_t)(trace[y][x][c] * f);
}
void ecran_sillages(bool debut, float t, float dt) {
  if (debut) {
    memset(trace, 0, sizeof trace);
    for (int i = 0; i < 95; i++) {
      sil.r[i] = hasard(3, 85); sil.a[i] = hasard(0, PI2); sil.l[i] = hasard(0.3f, 1.0f);
      const float q = hasard(0, 1);
      sil.teinte[i] = q < 0.7f ? 0 : q < 0.9f ? 1 : 2;
    }
    for (int k = 60; k > 0; k--) { sillages_passer(0.05f); sillages_poser(t - k * 0.05f); }   // la pose a deja commence
  }
  sillages_passer(dt);
  sillages_poser(t);
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++)
      peindre(y, x, 3 + y * 0.07f + trace[y][x][0] / 256.0f, 4 + y * 0.1f + trace[y][x][1] / 256.0f,
              14 + y * 0.3f + trace[y][x][2] / 256.0f);
  for (int x = 0; x < W; x++) {
    const float sol = 55 + 2.5f * sinf(x * 0.07f + 2) + sinf(x * 0.3f);
    for (int y = 0; y < H; y++)
      if (y >= sol) peindre(y, x, 5, 6, 10);
  }
  for (int i = 0; i < 6; i++) {                           // la tente, eclairee de l'interieur
    const float k = (0.35f + 0.05f * sinf(t * 2.5f)) * (0.6f + i * 0.08f);
    for (int x = 12 - i; x < 14 + i; x++) peindre(50 + i, x, 255 * k, 160 * k, 70 * k);
  }
  for (int y = 50; y < 56; y++)
    for (int x = 12; x < 14; x++) peindre(y, x, 40, 22, 12);
}

// --- la neige, la nuit, sous la lune ---
struct { float x[120], y[120], v[120], p[120], sol[64]; } nei;
void ecran_neige(bool debut, float t, float dt) {
  if (debut) {
    for (int i = 0; i < 120; i++) { nei.x[i] = hasard(0, 64); nei.y[i] = hasard(-64, 64); nei.v[i] = hasard(5, 16); nei.p[i] = hasard(0, PI2); }
    for (int x = 0; x < 64; x++) nei.sol[x] = 0;
  }
  for (int i = 0; i < 120; i++) {
    nei.y[i] += nei.v[i] * dt;
    nei.x[i] = fmodf(fmodf(nei.x[i] + sinf(t * 1.3f + nei.p[i]) * 6 * dt, 64) + 64, 64);
    const int c = (int)nei.x[i] % 64;
    if (nei.y[i] >= 63 - nei.sol[c]) {                    // elle se pose, et la suivante tombe
      nei.sol[c] = fminf(14.0f, nei.sol[c] + 0.35f);
      nei.y[i] = hasard(-8, 0);
      nei.x[i] = hasard(0, 64);
    }
  }
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      const float lune = hypotf(x - 50.0f, y - 11.0f);
      const float halo = borne(1 - (lune - 4) / 6, 0, 1);
      if (lune <= 4) peindre(y, x, 230, 230, 200);
      else peindre(y, x, 4 + y * 0.15f + halo * 40, 6 + y * 0.2f + halo * 40, 26 + y * 0.45f + halo * 30);
      if (y >= 64 - (nei.sol[x] + sinf(x * 0.7f) * 0.6f)) peindre(y, x, 215, 225, 245);
    }
  for (int i = 0; i < 120; i++) {
    const float l = (0.5f + 0.5f * (nei.v[i] - 5) / 11) * 255;
    pointer(nei.y[i], nei.x[i], l, l, l);
  }
}

typedef void (*Ecran)(bool, float, float);
const Ecran ECRANS[NB_ECRANS] = {ecran_aurore, ecran_aurore_lac, ecran_coucher, ecran_lucioles, ecran_nebuleuse,
                                 ecran_filantes, ecran_meduses, ecran_lanternes, ecran_sillages, ecran_neige};

int ecran = -1;
bool ecran_neuf = false;
unsigned long ecran_debut = 0, veille_depuis = 0, veille_image = 0;

uint16_t masque_veille() { return reglages.masque & ((1u << NB_ECRANS) - 1); }

void prochain_ecran() {
  // chacun son tour, jamais deux fois de suite (s'il y en a plus d'un)
  int choix[NB_ECRANS], n = 0;
  for (int i = 0; i < NB_ECRANS; i++)
    if ((masque_veille() >> i) & 1) choix[n++] = i;
  if (n == 0) return;
  graine ^= millis() * 2654435761u;
  int suivant = choix[aleatoire() % n];
  if (n > 1)
    while (suivant == ecran) suivant = choix[aleatoire() % n];
  ecran = suivant;
  ecran_neuf = true;
  ecran_debut = millis();
}

bool veille_possible() { return veille_permise && reglages.actif && masque_veille(); }

void commencer_veille() {
  etat = VEILLE;
  veille_depuis = veille_image = millis();
  panneau->setBrightness8(min(reglages.lum, PLAFOND));
  ecran = -1;
  prochain_ecran();
  tout_redessiner = true;
}

// la scene, en fondu (k), vers le panneau : la balance et la clarte de Machi Tool
void poser_scene(float k) {
  for (int p = 0, i = 0; p < W * H; p++, i += 2) {
    const float *s = scene[p / W][p % W];
    const uint8_t r = lut[0][(int)borne(s[0] * k, 0, 255)];
    const uint8_t v = lut[1][(int)borne(s[1] * k, 0, 255)];
    const uint8_t b = lut[2][(int)borne(s[2] * k, 0, 255)];
    const uint16_t c = ((r & 0xF8) << 8) | ((v & 0xFC) << 3) | (b >> 3);
    image[i] = c >> 8;
    image[i + 1] = c & 0xFF;
  }
  dessiner();
}

void veiller(unsigned long maintenant) {
  if (reglages.arret_min && maintenant - veille_depuis >= reglages.arret_min * 60000UL) {
    eteindre();                // l'heure d'arret : noir jusqu'au retour du PC
    veille_permise = false;
    return;
  }
  if (maintenant - veille_image < 33 && !ecran_neuf) return;   // 30 images par seconde
  const float dt = fminf(0.2f, (maintenant - veille_image) / 1000.0f);
  veille_image = maintenant;
  const float duree = reglages.duree_s;
  if ((maintenant - ecran_debut) / 1000.0f >= duree) prochain_ecran();
  const float ecoule = (maintenant - ecran_debut) / 1000.0f;
  const bool debut = ecran_neuf;
  ecran_neuf = false;
  ECRANS[ecran](debut, ecoule, debut ? 0.0f : dt);
  poser_scene(fminf(1.0f, fminf(ecoule / 1.0f, (duree - ecoule) / 1.0f)));
}

// "MA" : 12 octets -- format, actif, luminosite, ecrans (16 bits), duree d'un
// ecran (s, 16 bits), arret apres (min, 16 bits, 0 = jamais), balance r v b
// -- puis leur Fletcher-16. Abimes : ignores.
void decoder(const uint8_t *d) {
  reglages.actif = d[1] & 1;
  reglages.lum = d[2];
  reglages.masque = d[3] << 8 | d[4];
  const int duree = d[5] << 8 | d[6];
  reglages.duree_s = duree < 10 ? 10 : duree;
  reglages.arret_min = d[7] << 8 | d[8];
  reglages.rouge = min((uint8_t)100, d[9]);
  reglages.vert = min((uint8_t)100, d[10]);
  reglages.bleu = min((uint8_t)100, d[11]);
  preparer_lut();
}

bool lire_reglages() {
  uint8_t d[14];
  if (lire(d, 14) != 14 || fletcher16(d, 12) != (uint16_t)(d[12] << 8 | d[13]) || d[0] != 1) return false;
  if (memcmp(d, reglages_bruts, 12) != 0) {
    memcpy(reglages_bruts, d, 12);
    memoire.putBytes("veille", reglages_bruts, 12);   // seulement s'ils changent : la flash s'use
    decoder(d);
    if (etat == VEILLE) {
      if (!veille_possible()) eteindre();
      else panneau->setBrightness8(min(reglages.lum, PLAFOND));
    }
  }
  return true;
}

void setup() {
  Serial.setRxBufferSize(65536);   // huit images de reserve : le temps de dessiner sans rien perdre
  Serial.begin(115200);        // USB : la vitesse est ignoree
  Serial.setTimeout(ATTENTE_MS);

  HUB75_I2S_CFG cfg(W, H, 1, PINS);
  cfg.clkphase = false;        // sans elle, l'image est decalee d'un pixel sur x
  // cfg.driver = HUB75_I2S_CFG::FM6126A;   // si le panneau reste noir
  panneau = new MatrixPanel_I2S_DMA(cfg);
  panneau->begin();
  panneau->setBrightness8(min(lum_pc, PLAFOND));
  eteindre();                  // noir jusqu'a la premiere image : plus de mire

  memoire.begin("machi", false);
  if (memoire.getBytes("veille", reglages_bruts, 12) == 12 && reglages_bruts[0] == 1) decoder(reglages_bruts);
  else memset(reglages_bruts, 0, 12);
  preparer_lut();
  // redemarree faute de tension (les ecrans de veille sur un USB trop faible) : noire jusqu'au PC
  veille_permise = esp_reset_reason() != ESP_RST_BROWNOUT;
  derniere_ms = millis();
}

void loop() {
  const unsigned long maintenant = millis();
  if (etat == PC && maintenant - derniere_ms > SILENCE_MS) eteindre();
  if (etat == NOIR && veille_possible() && maintenant - derniere_ms > SILENCE_MS) commencer_veille();
  if (etat == VEILLE) veiller(maintenant);
  if (Serial.available() < 2) return;
  if (Serial.read() != 'M') return;
  int genre = Serial.read();
  if (genre == 'B') {
    uint8_t b;
    if (lire(&b, 1) == 1) {
      lum_pc = b;
      if (etat != VEILLE) panneau->setBrightness8(min(b, PLAFOND));
    }
  } else if (genre == 'V') {
    Serial.println("MACHI 7");
  } else if (genre == 'S') {
    Serial.printf("STATS %lu %lu\n", (unsigned long)recues, (unsigned long)jetees);
  } else if (genre == 'A') {
    if (lire_reglages()) Serial.printf("VEILLE %u %u\n", (unsigned)reglages.actif, (unsigned)masque_veille());
  } else if (genre == 'W') {
    veille_permise = true;     // Windows s'arrete : la carte prend le relais
    if (veille_possible()) commencer_veille();
  } else if (genre == 'O') {
    veille_permise = false;    // on quitte Machi Tool : au prochain silence, noir
    if (etat == VEILLE) eteindre();
  } else if (genre == 'F' || genre == 'G') {
    if (lire(image, N) != (size_t)N) { jetees++; return; }
    if (genre == 'G') {
      uint8_t c[2];
      if (lire(c, 2) != 2 || fletcher16(image, N) != (uint16_t)(c[0] << 8 | c[1])) {
        jetees++;              // abimee : jetee, le panneau garde la precedente
        return;
      }
    }
    recues++;
    derniere_ms = millis();
    veille_permise = true;
    if (etat != PC) {          // le PC est la : ses images, a sa luminosite
      etat = PC;
      panneau->setBrightness8(min(lum_pc, PLAFOND));
      tout_redessiner = true;
    }
    dessiner();
  }
}
