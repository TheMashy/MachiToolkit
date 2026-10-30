// lot_villes_paysages.h -- les ecrans de ce lot, portes de machi_tool.py (croquis v10).
#pragma once

// humeurs : 0 = nuit, 1 = neon, 2 = aube, 3 = brume
struct E_ville { char rien; };
void s_ville(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ville &e = etat_ecran<E_ville>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = nuit, 1 = neon
struct E_autoroute { char rien; };
void s_autoroute(int humeur, bool debut, float t, float ecoule, float dt) {
  E_autoroute &e = etat_ecran<E_autoroute>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = magenta, 1 = cyan
struct E_synthwave { char rien; };
void s_synthwave(int humeur, bool debut, float t, float ecoule, float dt) {
  E_synthwave &e = etat_ecran<E_synthwave>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = nuit, 1 = neige
struct E_train { char rien; };
void s_train(int humeur, bool debut, float t, float ecoule, float dt) {
  E_train &e = etat_ecran<E_train>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = automne, 1 = lavande, 2 = nuit, 3 = nordique
struct E_couches { char rien; };
void s_couches(int humeur, bool debut, float t, float ecoule, float dt) {
  E_couches &e = etat_ecran<E_couches>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = aube, 1 = tempete, 2 = crepuscule
struct E_nordique { char rien; };
void s_nordique(int humeur, bool debut, float t, float ecoule, float dt) {
  E_nordique &e = etat_ecran<E_nordique>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = foret, 1 = desert, 2 = neige
struct E_feu_camp { char rien; };
void s_feu_camp(int humeur, bool debut, float t, float ecoule, float dt) {
  E_feu_camp &e = etat_ecran<E_feu_camp>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = or, 1 = nuit
struct E_ble { char rien; };
void s_ble(int humeur, bool debut, float t, float ecoule, float dt) {
  E_ble &e = etat_ecran<E_ble>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = midi, 1 = nuit, 2 = mars
struct E_dunes { char rien; };
void s_dunes(int humeur, bool debut, float t, float ecoule, float dt) {
  E_dunes &e = etat_ecran<E_dunes>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = printemps, 1 = nuit, 2 = automne
struct E_cerisiers { char rien; };
void s_cerisiers(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cerisiers &e = etat_ecran<E_cerisiers>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = bleu, 1 = rose
struct E_champignons { char rien; };
void s_champignons(int humeur, bool debut, float t, float ecoule, float dt) {
  E_champignons &e = etat_ecran<E_champignons>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = amethyste, 1 = emeraude
struct E_cristaux { char rien; };
void s_cristaux(int humeur, bool debut, float t, float ecoule, float dt) {
  E_cristaux &e = etat_ecran<E_cristaux>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = rouge, 1 = bleu
struct E_lave { char rien; };
void s_lave(int humeur, bool debut, float t, float ecoule, float dt) {
  E_lave &e = etat_ecran<E_lave>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = tempete, 1 = calme
struct E_phare { char rien; };
void s_phare(int humeur, bool debut, float t, float ecoule, float dt) {
  E_phare &e = etat_ecran<E_phare>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

// humeurs : 0 = coucher, 1 = ville
struct E_murmuration { char rien; };
void s_murmuration(int humeur, bool debut, float t, float ecoule, float dt) {
  E_murmuration &e = etat_ecran<E_murmuration>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}

struct E_village_neige { char rien; };
void s_village_neige(int humeur, bool debut, float t, float ecoule, float dt) {
  E_village_neige &e = etat_ecran<E_village_neige>(debut);
  (void)e; (void)humeur; (void)t; (void)ecoule; (void)dt;
  degrade2(20, 20, 30, 40, 40, 60);   // A PORTER
}
