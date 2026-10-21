// Le croquis du panneau LED de Machi Tool (Machi LED Wall), version 2.
// Un panneau 64x64 sur une Adafruit MatrixPortal S3, nourri par USB :
//   "MF" + 8 192 octets (RGB565, poids fort d'abord) = une image,
//   "MB" + 1 octet = la luminosite (0-255, jamais au-dessus de PLAFOND),
//   "MV"           = il repond "MACHI 2" (Machi Tool sait quel croquis il a).
//
// v2 : « ca tombe a 5 fps parfois ». La v1 redessinait les 4 096 pixels a
// chaque image : a 30 images/s la carte prenait du retard, et le PC attendait
// qu'elle suive. La v2 ne redessine que les pixels qui ont change (l'horloge :
// quelques dizaines par image).
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

const int W = 64, H = 64;
MatrixPanel_I2S_DMA *panneau;
uint8_t image[W * H * 2];
uint8_t affichee[W * H * 2];   // ce que le panneau montre deja
bool tout_redessiner = true;

// La mire : rouge en haut a gauche, vert en haut a droite,
// bleu en bas a gauche, blanc en bas a droite, un cadre orange.
void mire() {
  panneau->fillRect(0, 0, 32, 32, panneau->color565(255, 0, 0));
  panneau->fillRect(32, 0, 32, 32, panneau->color565(0, 255, 0));
  panneau->fillRect(0, 32, 32, 32, panneau->color565(0, 0, 255));
  panneau->fillRect(32, 32, 32, 32, panneau->color565(255, 255, 255));
  panneau->drawRect(0, 0, 64, 64, panneau->color565(255, 140, 0));
}

void setup() {
  Serial.setRxBufferSize(16384);
  Serial.begin(115200);        // USB : la vitesse est ignoree
  Serial.setTimeout(200);

  HUB75_I2S_CFG cfg(W, H, 1, PINS);
  cfg.clkphase = false;        // sans elle, l'image est decalee d'un pixel sur x
  // cfg.driver = HUB75_I2S_CFG::FM6126A;   // si le panneau reste noir
  panneau = new MatrixPanel_I2S_DMA(cfg);
  panneau->begin();
  panneau->setBrightness8(min((uint8_t)40, PLAFOND));
  panneau->clearScreen();
  mire();
}

void loop() {
  if (Serial.available() < 2) return;
  if (Serial.read() != 'M') return;
  int genre = Serial.read();
  if (genre == 'B') {
    uint8_t b;
    if (Serial.readBytes(&b, 1) == 1) panneau->setBrightness8(min(b, PLAFOND));
  } else if (genre == 'V') {
    Serial.println("MACHI 2");
  } else if (genre == 'F') {
    if (Serial.readBytes(image, sizeof image) != sizeof image) return;
    for (int p = 0, i = 0; p < W * H; p++, i += 2) {
      if (!tout_redessiner && image[i] == affichee[i] && image[i + 1] == affichee[i + 1]) continue;
      panneau->drawPixel(p % W, p / W, (uint16_t)(image[i] << 8 | image[i + 1]));
    }
    memcpy(affichee, image, sizeof image);
    tout_redessiner = false;
  }
}
