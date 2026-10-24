// Le croquis du panneau LED de Machi Tool (Machi LED Wall), version 6.
// Un panneau 64x64 sur une Adafruit MatrixPortal S3, nourri par USB :
//   "MG" + 8 192 octets (RGB565, poids fort d'abord) + 2 octets de controle
//        (Fletcher-16, poids fort d'abord) = une image controlee,
//   "MF" + 8 192 octets = une image sans controle (Machi Tool avant la v1.90),
//   "MB" + 1 octet = la luminosite (0-255, jamais au-dessus de PLAFOND),
//   "MV"           = il repond "MACHI 6" (Machi Tool sait quel croquis il a),
//   "MS"           = il repond "STATS recues jetees" (les images abimees).
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
#include <ESP32-HUB75-MatrixPanel-I2S-DMA.h>

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
const unsigned long SILENCE_MS = 5000;   // sans image depuis 5 s : noir
const unsigned long ATTENTE_MS = 200;    // une image sans un octet depuis 200 ms : abandonnee
unsigned long derniere_ms = 0;
bool eteint = false;

void eteindre() {
  panneau->clearScreen();
  memset(affichee, 0, N);      // ce que le panneau montre : du noir
  eteint = true;
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
  const int bande = recues % (H / 2);
  for (int p = 0, i = 0; p < W * H; p++, i += 2) {
    const bool force = tout_redessiner || (p / W) / 2 == bande;
    if (!force && image[i] == affichee[i] && image[i + 1] == affichee[i + 1]) continue;
    panneau->drawPixel(p % W, p / W, (uint16_t)(image[i] << 8 | image[i + 1]));
  }
  memcpy(affichee, image, N);
  tout_redessiner = false;
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
  panneau->setBrightness8(min((uint8_t)40, PLAFOND));
  eteindre();                  // noir jusqu'a la premiere image : plus de mire
  derniere_ms = millis();
}

void loop() {
  if (!eteint && millis() - derniere_ms > SILENCE_MS) eteindre();
  if (Serial.available() < 2) return;
  if (Serial.read() != 'M') return;
  int genre = Serial.read();
  if (genre == 'B') {
    uint8_t b;
    if (lire(&b, 1) == 1) panneau->setBrightness8(min(b, PLAFOND));
  } else if (genre == 'V') {
    Serial.println("MACHI 6");
  } else if (genre == 'S') {
    Serial.printf("STATS %lu %lu\n", (unsigned long)recues, (unsigned long)jetees);
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
    eteint = false;
    dessiner();
  }
}
